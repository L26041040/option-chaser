#!/usr/bin/env python
"""V2-07（#409）跨日續跑：用**剛建好的真實資料**（`oc409` 的複本）＋推進的時鐘驗證輪替。

和 cron／SU「繼續更新」同一個核心 `consensus_cache.refresh_symbols()`，分析師來源是
**真實 Yahoo**（`YahooAnalystSource`，不是假來源；需要的天數才打上游）。只寫
`--dsn` 指定的本機複本（主機必須是 127.0.0.1／localhost；拒絕其他主機）。

1. 同一個真實交易日再跑：今天已成功的一檔都不重抓。
2. 把時鐘推到後面的日子（每日上限 `--cap` 遠小於 503）：
   週二 → 週五（中間兩天排程沒跑）→ 週六 → 週日 → 週一。
   - 每天抓的正是「輪替順序」（`rotation_key`）最前面的 `--cap` 檔：最久沒嘗試的先；
   - 週六、週日算週五（交易日），不重抓週五已成功的；
   - 每天的摘要數字（成功／失敗／符合條件／尚未輪到）與從狀態表自己算的一致。
3. 從最後的狀態投影：每天處理量 T 時每一檔在第幾個交易日輪到，N＝ceil(範圍／T)，
   沒有任何一檔被跳過超過 N 個交易日。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/live409_rotation_sim.py --dsn postgresql://postgres@127.0.0.1:55432/oc409_sim \\
        --cap 40 --out /path/live409_rotation_sim.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from api_app import consensus_cache, opportunity_settings
from api_app.analyst_source import YahooAnalystSource
from api_app.clock import ny_today
from api_app.consensus_cache import RefreshPolicy, rotation_key, trading_day
from option_chaser.data.yahoo_analyst import FIRM_ALIASES, UrllibTransport
from option_chaser.consensus import ConsensusRules

EASTERN = ZoneInfo("America/New_York")
TAIPEI = ZoneInfo("Asia/Taipei")


def tw(epoch: float | None = None) -> str:
    at = datetime.fromtimestamp(epoch if epoch is not None else time.time(), TAIPEI)
    return at.strftime("%Y-%m-%d %H:%M:%S") + " (台灣)"


class CountingTransport(UrllibTransport):
    def __init__(self):
        super().__init__()
        self.requests = 0
        self.status = Counter()

    def get(self, url):
        self.requests += 1
        resp = super().get(url)
        self.status[str(resp.status)] += 1
        return resp


class CountingSource(YahooAnalystSource):
    def __init__(self, transport):
        super().__init__(transport)
        self.calls: list[tuple[str, str]] = []

    def fetch(self, symbol, today):
        self.calls.append((symbol, today.isoformat()))
        return super().fetch(symbol, today)


def at_ny(day: date, hour: int, minute: int = 0) -> float:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=EASTERN).timestamp()


def own_counts(storage, source, universe, day: date, opp, rules) -> dict:
    """從狀態表與快照自己算當天的摘要數字（跟 `digest_counts`／狀態 API 對照）。"""
    states = storage.consensus_refresh_states()
    td = trading_day(day)
    tried = {s: st for s in universe if (st := states.get(s)) and st.source == source.name
             and trading_day(date.fromisoformat(st.attempted_day)) == td}
    ok = [s for s, st in tried.items() if st.error is None]
    view = consensus_cache.consensus_view(storage, source, opp, day, rules=rules,
                                          refresh_symbols=universe)
    return {"succeeded_this_trading_day": len(ok),
            "failed_this_trading_day": len(tried) - len(ok),
            "not_reached": len(universe) - len(tried),
            "selected_default_gate_all_data": sum(1 for i in view["items"] if i["gate"]["selected"]),
            "selected_default_gate_fresh_today": sum(
                1 for i in view["items"] if i["gate"]["selected"] and i["symbol"] in ok)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--cap", type=int, default=40)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    host = urlsplit(args.dsn).hostname or ""
    if host not in {"127.0.0.1", "localhost"}:
        sys.exit(f"拒絕：DSN 主機 {host!r} 不是本機")

    from api_app.storage.postgres import PostgresStorage
    storage = PostgresStorage(args.dsn)
    transport = CountingTransport()
    source = CountingSource(transport)
    rules = ConsensusRules(aliases=FIRM_ALIASES)
    opp = opportunity_settings.effective(None)          # 預設門檻 PR≥80／10%
    universe = consensus_cache.refresh_universe(storage, cap=consensus_cache.DEFAULT_REFRESH_SYMBOL_CAP)
    report: dict = {"started_tw": tw(), "dsn_host": host, "db": urlsplit(args.dsn).path.lstrip("/"),
                    "universe": len(universe), "cap": args.cap, "source": source.name,
                    "is_fixture": bool(source.is_fixture), "days": []}

    states0 = storage.consensus_refresh_states()
    day1 = Counter(st.attempted_day for st in states0.values())
    report["day1_attempted_days"] = dict(day1)
    real_today = ny_today()
    report["real_ny_today"] = real_today.isoformat()

    # ---------- 1. 同一個真實交易日再跑 ----------
    ok_today = {s for s, st in states0.items()
                if st.error is None and trading_day(date.fromisoformat(st.attempted_day))
                == trading_day(real_today)}
    calls0, req0 = len(source.calls), transport.requests
    same = consensus_cache.refresh_symbols(
        storage, source, universe, real_today, budget_exhausted=lambda: False, rules=rules,
        policy=RefreshPolicy(), batch_limit=None)
    refetched_ok = [s for s, _d in source.calls[calls0:] if s in ok_today]
    report["same_day"] = {"ny_day": real_today.isoformat(), "succeeded_today_before": len(ok_today),
                          "processed": same["processed"], "processed_symbols": same["processed_symbols"],
                          "refetched_already_succeeded": refetched_ok,
                          "http_requests": transport.requests - req0,
                          "skipped_states": dict(Counter(s["state"] for s in same["skipped"]))}
    print("同日重跑", json.dumps(report["same_day"], ensure_ascii=False)[:400])

    # ---------- 2. 推進時鐘 ----------
    policy = RefreshPolicy(daily_upstream_cap=args.cap)
    base = trading_day(real_today)
    nxt = consensus_cache.next_trading_day(base)                 # 週二
    friday = nxt + timedelta(days=(4 - nxt.weekday()) % 7)        # 同週週五
    plan = [nxt, friday, friday + timedelta(days=1), friday + timedelta(days=2),
            friday + timedelta(days=3)]
    history: dict[str, list[str]] = {s: [] for s in universe}     # 每檔被嘗試的（模擬）日子
    for st in states0.values():
        if st.symbol in history:
            history[st.symbol].append(trading_day(date.fromisoformat(st.attempted_day)).isoformat())
    for day in plan:
        states = storage.consensus_refresh_states()
        now0 = at_ny(day, 10)
        eligible = []
        for s in universe:
            st = states.get(s)
            st = st if st is not None and st.source == source.name else None
            if consensus_cache._classify(st, day, now0, policy) in consensus_cache._ELIGIBLE:
                eligible.append(s)
        expected = sorted(eligible, key=lambda s: rotation_key(s, states.get(s)))[:args.cap]
        calls_before, req_before = len(source.calls), transport.requests
        runs = []
        for run in range(3):                        # 一天三個 cron 時段（第三個應該什麼都不做）
            now = now0 + run * 1800
            r = consensus_cache.refresh_symbols(
                storage, source, universe, day, budget_exhausted=lambda: False, rules=rules,
                policy=policy, clock=lambda now=now: now, batch_limit=None)
            runs.append({"slot_ny": f"{day} {10 + run // 2}:{'30' if run % 2 else '00'}",
                         "processed": r["processed"], "succeeded": r["succeeded"],
                         "failed": r["failed"], "stopped_reason": r["stopped_reason"],
                         "upstream_calls_today": r["upstream_calls_today"]})
        fetched = [s for s, _d in source.calls[calls_before:]]
        for s in fetched:
            history[s].append(trading_day(day).isoformat())
        after = storage.consensus_refresh_states()
        prev_attempt_day = {s: (states[s].attempted_day if s in states else None) for s in fetched}
        status = consensus_cache.refresh_status(storage, source, universe, day,
                                                now=now0 + 3 * 1800, policy=policy)
        digest = consensus_cache.digest_counts(storage, source, day, universe)
        mine = own_counts(storage, source, universe, day, opp, rules)
        entry = {
            "ny_day": day.isoformat(), "weekday": day.strftime("%a"),
            "trading_day": trading_day(day).isoformat(), "runs": runs,
            "fetched": len(fetched), "http_requests": transport.requests - req_before,
            "fetched_equals_rotation_head": fetched == expected,
            "fetched_first10": fetched[:10],
            "previous_attempt_days_of_fetched": dict(Counter(v for v in prev_attempt_day.values())),
            "eligible_before": len(eligible),
            "refetched_same_trading_day": [s for s in fetched if states.get(s) and trading_day(
                date.fromisoformat(states[s].attempted_day)) == trading_day(day)],
            "status_progress": status["progress"], "status_upstream_calls_today": status["upstream_calls_today"],
            "digest": {k: digest[k] for k in ("succeeded", "failed", "insufficient", "selected",
                                              "universe", "not_reached")},
            "own": mine,
            "fetch_errors": [(s, after[s].error) for s in fetched if after[s].error],
        }
        entry["status_matches_own"] = (status["progress"]["done"] == mine["succeeded_this_trading_day"]
                                       and status["progress"]["failed"] == mine["failed_this_trading_day"]
                                       and status["progress"]["pending"] == mine["not_reached"])
        entry["digest_matches_own"] = (digest["succeeded"] == mine["succeeded_this_trading_day"]
                                       and digest["failed"] == mine["failed_this_trading_day"]
                                       and digest["not_reached"] == mine["not_reached"]
                                       and digest["selected"] == mine["selected_default_gate_fresh_today"])
        report["days"].append(entry)
        print(day, day.strftime("%a"), "fetched", len(fetched), "head_ok", entry["fetched_equals_rotation_head"],
              "status_ok", entry["status_matches_own"], "digest_ok", entry["digest_matches_own"],
              json.dumps(entry["digest"]), json.dumps(mine))

    # ---------- 3. 投影：每一檔在第幾個交易日輪到 ----------
    states = storage.consensus_refresh_states()
    order = sorted(universe, key=lambda s: rotation_key(s, states.get(s)))
    T = args.cap
    n_bound = math.ceil(len(universe) / T)
    projected_day_index = {s: i // T + 1 for i, s in enumerate(order)}   # 從下一個交易日起算
    # 每檔「上次嘗試」到「投影的下次嘗試」相隔幾個交易日（含已模擬的天）
    sim_days = [trading_day(d) for d in plan]
    last_sim = max(sim_days)

    def tdays_between(a: date, b: date) -> int:
        n, d = 0, a
        while d < b:
            d += timedelta(days=1)
            if d.weekday() < 5:
                n += 1
        return n

    gaps = []
    for s in universe:
        last = date.fromisoformat(max(history[s]))
        gap = tdays_between(last, last_sim) + projected_day_index[s]
        gaps.append(gap)
    report["projection"] = {
        "T_per_trading_day": T, "N_bound_ceil_universe_over_T": n_bound,
        "max_projected_index": max(projected_day_index.values()),
        "max_gap_trading_days_between_attempts": max(gaps),
        "gap_histogram": dict(sorted(Counter(gaps).items())),
        "never_attempted_in_projection": [s for s in universe if not history[s] and projected_day_index[s] > n_bound],
        "production_T": "min(daily cap 900, 32 slots × ~27 symbols ≈ 870) ≥ 503 → N = 1",
    }
    report["totals"] = {"upstream_fetches": len(source.calls), "http_requests": transport.requests,
                        "http_status": dict(transport.status), "http_429": transport.status.get("429", 0)}
    report["finished_tw"] = tw()
    with open(args.out, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["projection"], ensure_ascii=False))
    print(json.dumps(report["totals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
