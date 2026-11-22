#!/usr/bin/env python
"""本機實測：真實分析師資料＋真實選擇權報價，走完整條機會搜尋（LIVE-T4／#400）。

和 SU 在機會搜尋頁操作完全同一條程式路徑：

1. `POST /api/opportunity/consensus/update`（#398 的正式更新路徑，真實 Yahoo
   `upgradeDowngradeHistory`），依 `remaining` 續跑到完（同一交易日已成功的
   檔不會重抓）。
2. 每組門檻：`PUT /api/settings` 設定兩道門檻 → `GET /api/opportunity/consensus`
   的入選清單 → `POST /api/opportunity/search` 依 `remaining` 續跑到完。抓鏈走
   **既有**預設路徑（`fetch` 不覆寫：Cboe → yfinance 降級鏈、Global Vendor
   Fuse、429 退避），只在 Cboe 與 yfinance 兩個呼叫點外面量時間、記下
   `ChainSnapshot.source`——不改它們回傳的任何東西。

最後印出（並以 `--out` 存 JSON）：每組門檻的入選檔數、搜尋成功檔數與每檔
家族數、零候選／抓鏈失敗的檔數與原因、每檔耗時、報價來源分布、跨股票排行
前 10 名。

**只寫本機資料庫**：`--dsn` 的主機必須是 127.0.0.1／localhost／::1，否則
直接拒絕——絕不連 Production。不需要任何金鑰或密碼。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/opportunity_live_search.py \\
        --dsn postgresql://postgres@127.0.0.1:55432/oclive400 \\
        --thresholds 20/10 --thresholds 50/20
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import consensus_cache
from api_app.analyst_source import YahooAnalystSource
from api_app.main import create_app
from option_chaser.consensus import ConsensusRules
from option_chaser.data import yf as yf_module
from option_chaser.data.yahoo_analyst import FIRM_ALIASES
from scripts.consensus_live_build import CountingTransport, require_local

_DEFAULT = {"mode": "default", "provider": None}
OWNER = "live-search"


class ChainProbe:
    """記下每次真正打上游的抓鏈：哪個來源、耗時、成功與否、合約數。"""

    def __init__(self):
        self.calls: list[dict] = []

    def wrap(self, name: str, fn):
        def fetch(symbol):
            t0 = time.monotonic()
            try:
                snap = fn(symbol)
            except Exception as e:  # noqa: BLE001 — 照原樣往外拋，只記錄
                self.calls.append({"symbol": symbol, "attempt": name, "ok": False,
                                   "seconds": round(time.monotonic() - t0, 2),
                                   "error": str(e)[:200]})
                raise
            self.calls.append({"symbol": symbol, "attempt": name, "ok": True,
                               "seconds": round(time.monotonic() - t0, 2),
                               "source": snap.source, "contracts": len(snap.contracts),
                               "expiries": len({c.expiry for c in snap.contracts}),
                               "spot": snap.spot, "fetched_at": snap.fetched_at})
            return snap
        return fetch


def build_consensus(client: TestClient) -> dict:
    started = time.monotonic()
    calls = 0
    while True:
        r = client.post("/api/opportunity/consensus/update", json={})
        r.raise_for_status()
        body = r.json()
        calls += 1
        if body["stopped_reason"] or not body["remaining"] or body["processed"] == 0:
            break
    status = client.get("/api/opportunity/consensus/status").json()
    return {"api_calls": calls, "seconds": round(time.monotonic() - started, 1),
            "progress": status["progress"], "data_as_of": status["data_as_of"],
            "upstream_calls_today": status["upstream_calls_today"],
            "failed": [{"symbol": s["symbol"], "error": s["error"]}
                       for s in status["symbols"] if s["error"]]}


def run_search(client: TestClient, probe: ChainProbe, p_max: float, d_max: float) -> dict:
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "sample-large-cap",
                               "percentile_max": p_max, "dispersion_max": d_max}})
    r.raise_for_status()
    consensus = client.get("/api/opportunity/consensus").json()
    items = consensus["items"]
    selected = [i for i in items if i["gate"]["selected"]]
    status_counts = Counter(i["status"] for i in items)
    gate_fail = Counter()
    for i in items:
        if i["status"] == "ok" and not i["gate"]["selected"]:
            key = ("both" if not (i["gate"]["first"] or i["gate"]["second"])
                   else "percentile" if not i["gate"]["first"] else "dispersion")
            gate_fail[key] += 1

    rows: list[dict] = []
    failures: list[dict] = []
    incomplete: list[dict] = []
    per_symbol: list[dict] = []
    body: dict = {}
    started = time.monotonic()
    while True:
        mark = len(probe.calls)
        t0 = time.monotonic()
        r = client.post("/api/opportunity/search", json=body)
        if r.status_code != 200:
            failures.append({"symbol": "*", "reason": f"http_{r.status_code}",
                             "message": r.text[:300]})
            break
        out = r.json()
        elapsed = round(time.monotonic() - t0, 2)
        fetches = probe.calls[mark:]
        for symbol in out["processed"]:
            mine = [c for c in fetches if c["symbol"] == symbol]
            ok = next((c for c in mine if c["ok"]), None)
            per_symbol.append({
                "symbol": symbol, "seconds": elapsed,
                "fetch_seconds": round(sum(c["seconds"] for c in mine), 2),
                "source": ok["source"] if ok else None,
                "attempts": [f"{c['attempt']}:{'ok' if c['ok'] else 'fail'}" for c in mine],
                "contracts": ok["contracts"] if ok else None,
                "expiries": ok["expiries"] if ok else None,
                "families": sorted(row["family"] for row in out["rows"]
                                   if row["symbol"] == symbol)})
        rows.extend(out["rows"])
        failures.extend(out["failures"])
        incomplete.extend(out.get("incomplete", []))
        if out["stopped_reason"]:
            failures.append({"symbol": "*", "reason": out["stopped_reason"],
                             "message": out["message"]})
            break
        if not out["remaining"]:
            if out["deferred"]:
                body = {"symbols": out["deferred"]}
                continue
            break
        body = {"symbols": out["remaining"]}
    rows.sort(key=lambda row: (-row["target_return"], row["symbol"], row["family"]))
    return {
        "thresholds": {"percentile_max": p_max, "dispersion_max": d_max},
        "status_counts": dict(status_counts),
        "ok_but_gate_failed": dict(gate_fail),
        "selected": [{"symbol": i["symbol"], "mean": i["mean"],
                      "dispersion": i["dispersion"], "percentile": i["percentile"],
                      "n_analysts": i["n_analysts"], "target_month": i["target_month"]}
                     for i in selected],
        "search_seconds": round(time.monotonic() - started, 1),
        "succeeded": sorted({row["symbol"] for row in rows}),
        "failures": failures,
        "incomplete": incomplete,
        "per_symbol": per_symbol,
        "top10": [{k: row[k] for k in ("symbol", "family", "subtype", "expiry",
                                       "target_return", "entry_cost",
                                       "max_loss_per_contract", "breakeven",
                                       "buffer_days", "target_month")}
                  | {"target_price": row["scenario"]["target_price"],
                     "legs": row["legs"]}
                  for row in rows[:10]],
    }


def print_report(report: dict) -> None:
    build = report["consensus_build"]
    print(f"\n===== 分析師資料（#398 更新路徑）=====\n{json.dumps(build, ensure_ascii=False)}")
    for run in report["runs"]:
        th = run["thresholds"]
        print(f"\n===== 門檻 百分位 ≤ {th['percentile_max']}%、分歧度 ≤ "
              f"{th['dispersion_max']}% =====")
        print(f"共識狀態：{run['status_counts']}；ok 但沒過門檻：{run['ok_but_gate_failed']}")
        print(f"入選 {len(run['selected'])} 檔：{[s['symbol'] for s in run['selected']]}")
        print(f"搜尋成功 {len(run['succeeded'])} 檔；失敗 {len(run['failures'])} 筆；"
              f"總耗時 {run['search_seconds']} 秒")
        sources = Counter(p["source"] for p in run["per_symbol"])
        print(f"報價來源：{dict(sources)}")
        for p in run["per_symbol"]:
            print(f"  {p['symbol']:6} {p['seconds']:6.2f}s（抓鏈 {p['fetch_seconds']:5.2f}s）"
                  f" source={p['source']} attempts={p['attempts']} "
                  f"合約 {p['contracts']}／到期日 {p['expiries']} 家族 {p['families']}")
        for f in run["failures"]:
            print(f"  失敗 {f['symbol']} [{f['reason']}] {f['message']}")
        for f in run["incomplete"]:
            print(f"  缺家族 {f['symbol']} {f['families']}：{f['message']}")
        print("跨股票排行前 10：")
        for n, row in enumerate(run["top10"], 1):
            print(f"  {n:2}. {row['symbol']:6} {row['subtype']:18} 到期 {row['expiry']} "
                  f"報酬 {row['target_return']:.4f} 成本 {row['entry_cost']:.2f} "
                  f"最大損失/口 {row['max_loss_per_contract']:.0f} 目標 "
                  f"{row['target_price']:.2f}@{row['target_month']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--thresholds", action="append", default=None,
                        help="百分位/分歧度（百分比），可重複；預設 20/10")
    parser.add_argument("--out", help="把完整結果存成 JSON")
    args = parser.parse_args()
    host = require_local(args.dsn)
    thresholds = [tuple(float(x) for x in t.split("/")) for t in
                  (args.thresholds or ["20/10"])]

    from api_app.storage.postgres import PostgresStorage
    from tests._role_session import grant_role

    storage = PostgresStorage(args.dsn)
    grant_role(storage, "superuser", owner_id=OWNER)
    probe = ChainProbe()
    from option_chaser.data import cboe as cboe_module
    real_yf = yf_module.fetch_chain
    yf_module.fetch_chain = probe.wrap("yfinance", real_yf)
    try:
        client = TestClient(create_app(
            identity_resolver=lambda: OWNER, storage=storage,
            analyst_source=YahooAnalystSource(CountingTransport()),
            consensus_rules=ConsensusRules(aliases=FIRM_ALIASES),
            consensus_refresh_policy=consensus_cache.RefreshPolicy.from_env(),
            cboe_fetch=probe.wrap("cboe", cboe_module.fetch_chain)))
        print(f"DSN 主機 {host}（本機）")
        report = {"dsn_host": host, "consensus_build": build_consensus(client),
                  "runs": [run_search(client, probe, p, d) for p, d in thresholds]}
    finally:
        yf_module.fetch_chain = real_yf
    print_report(report)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
