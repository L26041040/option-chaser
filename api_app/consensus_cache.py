"""分析師共識的全站快取、每日更新與清單 view（OS-03／#392，母票 #389 §3／§7／§8）。

三件事，都只透過 `Storage` 與注入的 `AnalystSource`，數值一律交給
`option_chaser.consensus`（本模組不做任何共識計算）：

1. **更新**（`refresh_symbols()`，給 `GET /api/cron/consensus-refresh` 與
   SU／SA 的 `POST /api/opportunity/consensus/update`，兩者同一套核心）：
   - **成功**的 symbol 同一交易日不再抓；**失敗**的同一交易日內可以有限次
     重試（`RefreshPolicy`，LIVE-T3／#398 經 LIVE-TICKET-CORRECTION-001
     修正）：每次重試前要過冷卻；429 有 `Retry-After` 時取它和冷卻較長者，
     沒有就用 429 專用冷卻；重試用完改到下一個美東日；
   - 每次上游呼叫先在全站共用的每日上限（沿用 `rate_limits` 計數）扣一次——
     重試也算，扣不到就停止並回報，不打上游；
   - 同一 symbol 同一時間只有一次上游呼叫：先取「處理中」標記（有逾時），
     取到後**重讀狀態**再確認一次（別人可能剛抓完）；兩次上游呼叫之間有間隔；
   - 成功 → 以 `compute_snapshot()` 算出當天的 Snapshot，寫一筆
     (symbol, as_of)；失敗 → 只記錄嘗試（`ConsensusRefreshState.error`），
     **上一份成功的 Snapshot 原樣保留**，清單照實標出它的 as_of；
   - **進度游標**＝每個 symbol 的 `attempted_day`：每次呼叫依「從沒嘗試過
     → 最久沒嘗試」的順序處理，受時間預算（與 SU 端點的每批檔數）約束；
     跑不完的放 `remaining`，由下一次呼叫（前端自動續跑或明天的 cron）接續。
   狀態 API 用 `refresh_status()`。
2. **清單**（`consensus_view()`，給 `GET /api/opportunity/consensus`）：只讀
   快取、不打上游；讀取時才以使用者的兩道門檻 `evaluate_gate()`——改門檻
   立即生效，不必重抓。
3. **每日摘要統計**（`digest_counts()`）。

只採用**目前設定的來源**產生的快取（`source` 名稱比對）：來源換掉之後，
舊來源（例如測試資料）的 Snapshot 不會被當成新來源的結果顯示。
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from option_chaser import consensus
from option_chaser.consensus import ConsensusCrossCheck, ConsensusRules, ConsensusSnapshot

from . import search_universe
from .opportunity_settings import DEFAULT_DISPERSION_MAX, DEFAULT_PERCENTILE_MAX
from .analyst_source import AnalystSource
from .storage import (ConsensusDetailRecord, ConsensusRefreshState,
                      ConsensusSnapshotRecord, RateLimitBucket, Storage)

# 資料品質規則 R 與 target_month 規則：全站一份（不在使用者設定，#389 §6），
# 數值待 #385／#381。這裡只是**暫定預設**——實際值由
# `create_app(consensus_rules=, target_month_rule=)` 注入、一路傳進本模組，
# 改規則不必改程式（user story 40）。
DEFAULT_RULES = ConsensusRules()
DEFAULT_TARGET_MONTH_RULE = "fixed_12m"
# 每日更新母體的總上限（樣本優先；數值待 #386，`create_app(
# consensus_refresh_symbol_cap=)` 可覆寫）。
DEFAULT_REFRESH_SYMBOL_CAP = 200
NOT_CONFIGURED_MESSAGE = "尚未設定分析師資料來源"
_NOT_REFRESHED = "no_data: 尚未更新"
# 「有資料但不足」：資料品質規則沒過（不含完全沒資料、來源失敗）。
_INSUFFICIENT = ("insufficient_analysts", "insufficient_history", "stale",
                 "split_unresolved")


# ---------- Snapshot ⇄ JSON（Decimal 存字串，不失精度） ----------

def _decimal_to_str(x: Decimal | None) -> str | None:
    return None if x is None else str(x)


def snapshot_to_dict(s: ConsensusSnapshot) -> dict:
    return {
        "symbol": s.symbol, "as_of": s.as_of.isoformat(), "status": s.status,
        "n_analysts": s.n_analysts, "mean": _decimal_to_str(s.mean),
        "stdev": _decimal_to_str(s.stdev),
        "dispersion": _decimal_to_str(s.dispersion),
        "high": _decimal_to_str(s.high), "low": _decimal_to_str(s.low),
        "history_points": s.history_points,
        "percentile": _decimal_to_str(s.percentile),
        "history": [[t.isoformat(), str(d)] for t, d in s.history],
        "reasons": list(s.reasons),
        "freshness_share": _decimal_to_str(s.freshness_share),
        "median_published_on": (s.median_published_on.isoformat()
                                if s.median_published_on else None),
        "coverage": s.coverage, "source": s.source,
        "rules_version": s.rules_version,
        "cross_check": ({"consensus_mean_from_source":
                             _decimal_to_str(s.cross_check.consensus_mean_from_source),
                         "n_from_source": s.cross_check.n_from_source}
                        if s.cross_check else None),
        "computed_at": s.computed_at.isoformat() if s.computed_at else None,
    }


def _str_to_decimal(x: str | None) -> Decimal | None:
    return None if x is None else Decimal(x)


def snapshot_from_dict(d: dict) -> ConsensusSnapshot:
    cross = d.get("cross_check")
    return ConsensusSnapshot(
        symbol=d["symbol"], as_of=date.fromisoformat(d["as_of"]), status=d["status"],
        n_analysts=d["n_analysts"], mean=_str_to_decimal(d["mean"]),
        stdev=_str_to_decimal(d["stdev"]),
        dispersion=_str_to_decimal(d["dispersion"]),
        high=_str_to_decimal(d["high"]), low=_str_to_decimal(d["low"]),
        history_points=d["history_points"],
        percentile=_str_to_decimal(d["percentile"]),
        history=tuple((date.fromisoformat(t), Decimal(v)) for t, v in d["history"]),
        reasons=tuple(d["reasons"]),
        freshness_share=_str_to_decimal(d["freshness_share"]),
        median_published_on=(date.fromisoformat(d["median_published_on"])
                             if d.get("median_published_on") else None),
        coverage=d["coverage"], source=d["source"], rules_version=d["rules_version"],
        cross_check=(ConsensusCrossCheck(
            _str_to_decimal(cross["consensus_mean_from_source"]),
            cross["n_from_source"]) if cross else None),
        computed_at=(datetime.fromisoformat(d["computed_at"])
                     if d.get("computed_at") else None))


# ---------- 個股明細 ⇄ JSON（LIVE-T2／#399） ----------

def detail_to_dict(s: ConsensusSnapshot) -> dict:
    """`compute_snapshot()` 同一次計算的有效集合與每月序列（Decimal 存字串）。
    與 Snapshot 分開存：清單一次讀幾百檔的 Snapshot，不該拖著明細。"""
    return {
        "effective": [{"analyst_key": e.analyst_key, "firm": e.firm,
                       "target_price": str(e.target_price),
                       "adjusted_price": str(e.adjusted_price),
                       "published_on": e.published_on.isoformat(),
                       "action": e.action,
                       "prior_target": _decimal_to_str(e.prior_target)}
                      for e in s.effective],
        "series": [{"on": p.on.isoformat(), "n_analysts": p.n_analysts,
                    "mean": _decimal_to_str(p.mean), "stdev": _decimal_to_str(p.stdev),
                    "dispersion": _decimal_to_str(p.dispersion),
                    "qualified": p.qualified, "reason": p.reason}
                   for p in s.series],
    }


# ---------- 更新 ----------

def refresh_universe(storage: Storage, *,
                     cap: int = DEFAULT_REFRESH_SYMBOL_CAP) -> list[str]:
    """每日更新的母體 = 大型股樣本 ∪ **目前權限為 SU／SA** 的 owner 的自訂
    清單（#392；Normal 寫不進、也不會被併入——
    `Storage.opportunity_custom_symbols()` 只回特權 owner 的清單）。

    總數不超過 `cap`：樣本永遠排最前面，自訂清單依代號排序接在後面——
    決定性，同一份資料每天選出同一批，不會因為某位使用者的清單很長就把
    樣本擠出去。"""
    sample = search_universe.resolve_universe(None).symbols
    custom = storage.opportunity_custom_symbols()
    return list(dict.fromkeys([*sample, *sorted(custom)]))[:cap]


@dataclass(frozen=True)
class RefreshPolicy:
    """更新的重試／限流參數（LIVE-T3／#398，全部可設定、有明確預設）。

    `create_app(consensus_refresh_policy=)` 注入；沒注入時 `from_env()` 讀
    `CONSENSUS_*` 環境變數，再落回這裡的預設。時間單位都是秒。"""

    max_retries: int = 3                     # 失敗後同一交易日最多再試幾次
    retry_cooldown_seconds: int = 900        # 每次重試前的冷卻（15 分）
    rate_limit_cooldown_seconds: int = 1800  # 429 沒給 Retry-After 時（30 分）
    daily_upstream_cap: int = 400            # 每日上游呼叫上限（一次＝一檔 fetch）
    lease_seconds: int = 120                 # 處理中標記逾時（> 函式 maxDuration 60）
    call_spacing_seconds: float = 1.0        # 同一次呼叫裡兩次上游呼叫的間隔
    batch_size: int = 10                     # SU 端點每次呼叫最多處理幾檔

    @classmethod
    def from_env(cls, env=None) -> "RefreshPolicy":
        """讀不懂或低於下限的值一律用預設——打錯字不會變成「無上限」或
        「不冷卻」。"""
        env = os.environ if env is None else env
        values = {}
        for field_name, (name, kind, minimum) in _POLICY_ENV.items():
            raw = (env.get(name) or "").strip()
            try:
                value = kind(raw)
            except ValueError:
                continue
            if value >= minimum:
                values[field_name] = value
        return cls(**values)

    def view(self) -> dict:
        return asdict(self)


_POLICY_ENV = {
    "max_retries": ("CONSENSUS_MAX_RETRIES", int, 0),
    "retry_cooldown_seconds": ("CONSENSUS_RETRY_COOLDOWN_SECONDS", int, 0),
    "rate_limit_cooldown_seconds": ("CONSENSUS_RATE_LIMIT_COOLDOWN_SECONDS", int, 0),
    "daily_upstream_cap": ("CONSENSUS_DAILY_UPSTREAM_CAP", int, 1),
    "lease_seconds": ("CONSENSUS_LEASE_SECONDS", int, 1),
    "call_spacing_seconds": ("CONSENSUS_CALL_SPACING_SECONDS", float, 0),
    "batch_size": ("CONSENSUS_REFRESH_BATCH_SIZE", int, 1),
}
DEFAULT_POLICY = RefreshPolicy()
NOT_RETRYABLE_STAGE = "consensus_not_retryable"
DAILY_CAP_STAGE = "consensus_daily_cap"
DAILY_CAP_MESSAGE = "今日分析師資料的上游呼叫已達每日上限，下一個交易日自動恢復"
_UPSTREAM_SCOPE = "consensus_upstream"
_DAY_SECONDS = 86400
_EASTERN = ZoneInfo("America/New_York")
# 現在可以抓的狀態（其餘：done／cooling／exhausted／in_progress）。
_ELIGIBLE = ("pending", "retry_ready")
_FAILED_STATES = ("cooling", "retry_ready", "exhausted")
_SKIP_MESSAGES = {
    "done": "今天已經更新成功，同一交易日不再重抓",
    "cooling": "上次失敗，冷卻中",
    "exhausted": "今天的重試次數已用完，下一個交易日再試",
    "in_progress": "另一個更新正在處理這一檔",
}


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _day_start(day: date) -> datetime:
    """美東 `day` 的零時（UTC）——「下一個交易日再試」與每日上限的界線。"""
    return datetime.combine(day, datetime.min.time(), tzinfo=_EASTERN).astimezone(
        timezone.utc)


def _upstream_bucket(source: AnalystSource, today: date,
                     policy: RefreshPolicy) -> RateLimitBucket:
    """每日上游呼叫上限的計數格：沿用 `rate_limits`（SECURITY-FIX-02）的原子
    「檢查＋扣一次」，鍵＝來源名稱＋美東日；過期列由既有清理 cron 刪掉。"""
    return RateLimitBucket(_UPSTREAM_SCOPE, source.name, _DAY_SECONDS,
                           int(_day_start(today).timestamp()),
                           policy.daily_upstream_cap)


def _own(st: ConsensusRefreshState | None,
         source: AnalystSource) -> ConsensusRefreshState | None:
    """只認目前來源寫的狀態——換來源等於從沒試過。"""
    return st if st is not None and st.source == source.name else None


def _classify(st: ConsensusRefreshState | None, today: date, now: float,
              policy: RefreshPolicy) -> str:
    """一檔現在的狀態（不含處理中標記）：`pending`（今天還沒試過）／`done`
    （今天已成功）／`cooling`（失敗、冷卻中）／`retry_ready`（失敗、冷卻已過、
    還有重試次數）／`exhausted`（今天重試用完）。"""
    if st is None or st.attempted_day != today.isoformat():
        return "pending"
    if st.error is None:
        return "done"
    if st.attempts >= 1 + policy.max_retries:
        return "exhausted"
    if st.next_retry_at is not None and now < _epoch(st.next_retry_at):
        return "cooling"
    return "retry_ready"


def _skip(symbol: str, state: str, st: ConsensusRefreshState | None) -> dict:
    return {"symbol": symbol, "state": state,
            "next_retry_at": st.next_retry_at if st is not None and st.error else None,
            "message": _SKIP_MESSAGES.get(state, state)}


def _refresh_one(storage: Storage, source: AnalystSource, symbol: str,
                 today: date, rules: ConsensusRules, now: float,
                 previous: ConsensusRefreshState | None,
                 policy: RefreshPolicy) -> str:
    """抓一檔、存結果；回傳 `"ok"`（成功算出 Snapshot，不論資料品質）或
    `"failed"`（來源回報錯誤或丟例外）。失敗時依重試規則寫下次可重試時間。"""
    rate_limited, retry_after = False, None
    try:
        result = source.fetch(symbol, today)
        error = result.error
        rate_limited, retry_after = result.rate_limited, result.retry_after
    except Exception as e:  # noqa: BLE001 — 來源出錯一律收斂成失敗，不讓 cron 炸掉
        result, error = None, f"資料來源丟出例外：{e}"
    at = datetime.fromtimestamp(int(now), timezone.utc)
    day = today.isoformat()
    attempts = (previous.attempts + 1
                if previous is not None and previous.attempted_day == day else 1)
    if error is None:
        snap = consensus.compute_snapshot(
            result.records, result.splits, today, rules, symbol=symbol,
            coverage=result.coverage, source=source.name,
            cross_check=result.cross_check, computed_at=at)
        storage.save_consensus_snapshot(ConsensusSnapshotRecord(
            symbol=symbol, as_of=day, source=source.name,
            is_fixture=bool(source.is_fixture), snapshot=snapshot_to_dict(snap),
            computed_at=at.isoformat()))
        save_detail(storage, source, snap)
        next_retry_at, last_success_at = None, at.isoformat()
    else:
        if attempts >= 1 + policy.max_retries:
            # 重試用完：改到下一個美東日（那天 attempts 歸零重算）。
            next_retry_at = _day_start(today + timedelta(days=1)).isoformat()
        elif rate_limited and retry_after is None:
            next_retry_at = _iso(int(now) + policy.rate_limit_cooldown_seconds)
        else:
            next_retry_at = _iso(int(now) + max(policy.retry_cooldown_seconds,
                                                retry_after or 0))
        last_success_at = previous.last_success_at if previous is not None else None
    storage.save_consensus_refresh_state(ConsensusRefreshState(
        symbol=symbol, source=source.name, attempted_day=day,
        attempted_at=at.isoformat(), error=error, attempts=attempts,
        next_retry_at=next_retry_at, last_success_at=last_success_at))
    return "ok" if error is None else "failed"


def refresh_symbols(storage: Storage, source: AnalystSource, symbols: Sequence[str],
                    today: date, *, budget_exhausted: Callable[[], bool],
                    rules: ConsensusRules = DEFAULT_RULES,
                    policy: RefreshPolicy = DEFAULT_POLICY,
                    clock: Callable[[], float] = time.time,
                    sleep: Callable[[float], None] = time.sleep,
                    batch_limit: int | None = None) -> dict:
    """處理 `symbols` 裡現在可以抓的（今天還沒試過，或失敗後冷卻已過、還有
    重試次數），最久沒嘗試的先；每處理完一檔檢查一次預算與 `batch_limit`
    （至少處理一檔）。

    回傳本次統計、`remaining`（可以抓、這次沒輪到的，依處理順序）、
    `skipped`（現在不能抓的與原因）、`stopped_reason`（`"daily_cap"`＝每日
    上限已滿，`message` 說明）與今天已用的上游呼叫數。"""
    day = today.isoformat()
    states = storage.consensus_refresh_states()
    leases = storage.consensus_refresh_leases(now=clock())
    wanted = list(dict.fromkeys(symbols))
    own = {s: _own(states.get(s), source) for s in wanted}

    skipped: list[dict] = []
    pending: list[str] = []
    for symbol in wanted:
        state = ("in_progress" if symbol in leases
                 else _classify(own[symbol], today, clock(), policy))
        if state in _ELIGIBLE:
            pending.append(symbol)
        else:
            skipped.append(_skip(symbol, state, own[symbol]))
    pending.sort(key=lambda s: (own[s].attempted_day if own[s] else "", s))
    done_today = sum(1 for s in wanted if own[s] and own[s].attempted_day == day)

    holder = uuid.uuid4().hex
    bucket = _upstream_bucket(source, today, policy)
    succeeded = failed = calls = 0
    processed: list[str] = []
    stopped_reason = message = None
    index = 0
    while index < len(pending):
        if processed and (budget_exhausted() or (batch_limit is not None
                                                 and len(processed) >= batch_limit)):
            break
        symbol = pending[index]
        if not storage.acquire_consensus_refresh_lease(
                symbol, holder, now=clock(), ttl_seconds=policy.lease_seconds):
            skipped.append(_skip(symbol, "in_progress", None))
            index += 1
            continue
        try:
            # 取得標記後重讀：別人可能在我們排隊時剛抓完（成功或失敗）。
            current = _own(storage.get_consensus_refresh_state(symbol), source)
            state = _classify(current, today, clock(), policy)
            if state not in _ELIGIBLE:
                skipped.append(_skip(symbol, state, current))
                index += 1
                continue
            if storage.rate_limit_consume([bucket]) is not None:
                stopped_reason, message = "daily_cap", DAILY_CAP_MESSAGE
                break
            # 間隔是對上游的禮貌；測試資料（`is_fixture`）沒有上游，不等。
            if calls and policy.call_spacing_seconds > 0 and not source.is_fixture:
                sleep(policy.call_spacing_seconds)
            calls += 1
            outcome = _refresh_one(storage, source, symbol, today, rules, clock(),
                                   current, policy)
        finally:
            storage.release_consensus_refresh_lease(symbol, holder)
        processed.append(symbol)
        index += 1
        if outcome == "ok":
            succeeded += 1
        else:
            failed += 1
    return {"source": source.name, "as_of": day, "processed": len(processed),
            "processed_symbols": processed,
            "succeeded": succeeded, "failed": failed,
            "already_attempted_today": done_today,
            "remaining": pending[index:], "skipped": skipped,
            "stopped_reason": stopped_reason, "message": message,
            "upstream_calls_today": storage.rate_limit_count(bucket),
            "daily_cap": policy.daily_upstream_cap}


def refresh_status(storage: Storage, source: AnalystSource | None,
                   symbols: Sequence[str], today: date, *, now: float,
                   policy: RefreshPolicy = DEFAULT_POLICY) -> dict:
    """狀態 API（`GET /api/opportunity/consensus/status`，只限 SU／SA）：每檔
    最後成功／嘗試時間、失敗原因、今日已重試次數、下次可重試時間；全體進度、
    資料日期與今天已用的上游呼叫數。"""
    base = {"today": today.isoformat(), "now": _iso(now), "policy": policy.view(),
            "daily_cap": policy.daily_upstream_cap}
    if source is None:
        return {**base, "source": {"configured": False, "name": None,
                                   "is_fixture": False},
                "progress": _progress([]), "symbols": [], "data_as_of": None,
                "upstream_calls_today": 0}
    wanted = list(dict.fromkeys(symbols))
    states = storage.consensus_refresh_states()
    leases = storage.consensus_refresh_leases(now=now)
    snaps = storage.latest_consensus_snapshots(wanted, source=source.name)
    rows = []
    for symbol in wanted:
        st = _own(states.get(symbol), source)
        state = "in_progress" if symbol in leases else _classify(st, today, now, policy)
        attempts_today = st.attempts if st and st.attempted_day == today.isoformat() else 0
        rec = snaps.get(symbol)
        rows.append({
            "symbol": symbol, "state": state,
            "last_success_at": st.last_success_at if st else None,
            "last_attempt_at": st.attempted_at if st else None,
            "error": st.error if st else None,
            "retries_today": max(0, attempts_today - 1),
            "next_retry_at": (st.next_retry_at
                              if st and st.error and state in ("cooling", "exhausted")
                              else None),
            "retryable_now": state in _ELIGIBLE,
            "as_of": rec.as_of if rec else None})
    return {**base,
            "source": {"configured": True, "name": source.name,
                       "is_fixture": bool(source.is_fixture)},
            "progress": _progress(rows), "symbols": rows,
            "data_as_of": max((r["as_of"] for r in rows if r["as_of"]), default=None),
            "upstream_calls_today": storage.rate_limit_count(
                _upstream_bucket(source, today, policy))}


def _progress(rows: Sequence[dict]) -> dict:
    """全體進度：已完成（今天成功）／失敗（今天失敗：冷卻中、可重試、用完）／
    還沒試／處理中。"""
    count = {"done": 0, "failed": 0, "pending": 0, "in_progress": 0}
    for r in rows:
        count["failed" if r["state"] in _FAILED_STATES else r["state"]] += 1
    return {"total": len(rows), **count}


# ---------- 清單 view ----------

def _decimal_to_float(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


def _pct_to_ratio(pct) -> Decimal:
    return Decimal(str(pct)) / 100


def rules_view(rules: ConsensusRules = DEFAULT_RULES,
               target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> dict:
    """清單回應的 `rules` 區塊——照實回報**這個 app 實際注入**的規則。"""
    return {"rules_version": rules.version, "provisional": True,
            "n_min": rules.n_min, "validity_months": rules.validity_months,
            "freshness_days": rules.freshness_days,
            "freshness_min_share": float(rules.freshness_min_share),
            "h_min": rules.h_min, "stdev_kind": rules.stdev_kind,
            "lookback_points": rules.lookback_points, "sampling": "month_end",
            "target_month_rule": target_month_rule}


def _gate_view(gate: consensus.GateResult) -> dict:
    return {"first": gate.first, "second": gate.second, "selected": gate.selected,
            "reasons": list(gate.reasons)}


def _item(symbol: str, status: str, *, reasons: Sequence[str], gate: dict,
          snap: ConsensusSnapshot | None = None,
          target_month: str | None = None) -> dict:
    """清單項目的唯一形狀（有無 Snapshot 都走這裡，鍵不會分家）。沒有
    Snapshot 時數值一律 `None`、人數與歷史點數為 0。"""
    def number(name: str) -> float | None:
        return _decimal_to_float(getattr(snap, name)) if snap else None
    return {"symbol": symbol, "status": status,
            "as_of": snap.as_of.isoformat() if snap else None,
            "n_analysts": snap.n_analysts if snap else 0,
            "mean": number("mean"), "stdev": number("stdev"),
            "dispersion": number("dispersion"), "percentile": number("percentile"),
            "history_points": snap.history_points if snap else 0,
            "coverage": snap.coverage if snap else None,
            "freshness_share": number("freshness_share"),
            "high": number("high"), "low": number("low"),
            "median_published_on": (snap.median_published_on.isoformat()
                                    if snap and snap.median_published_on else None),
            "reasons": list(reasons), "gate": gate,
            "target_month": target_month,
            "rules_version": snap.rules_version if snap else None,
            "refresh_error": None}


def _empty_item(symbol: str, status: str, reason: str) -> dict:
    return _item(symbol, status, reasons=[reason],
                 gate={"first": False, "second": False, "selected": False,
                       "reasons": [reason]})


def _snapshot_item(snap: ConsensusSnapshot, today: date, p_max: Decimal,
                   d_max: Decimal, target_month_rule: str) -> dict:
    try:
        month = consensus.target_month(snap, today, target_month_rule)
    except ValueError:
        month = None
    return _item(snap.symbol, snap.status, reasons=snap.reasons, snap=snap,
                 gate=_gate_view(consensus.evaluate_gate(snap, p_max, d_max)),
                 target_month=month)


def _items(storage: Storage, source: AnalystSource, symbols: Sequence[str],
           today: date, p_max: Decimal, d_max: Decimal,
           target_month_rule: str) -> list[dict]:
    snapshots = storage.latest_consensus_snapshots(symbols, source=source.name)
    states = storage.consensus_refresh_states()
    items = []
    for symbol in symbols:
        rec = snapshots.get(symbol)
        st = states.get(symbol)
        failure = st if (st is not None and st.source == source.name
                         and st.error is not None) else None
        if rec is None:
            items.append(_empty_item(symbol, "source_error",
                                     f"source_error: {failure.error}")
                         if failure else _empty_item(symbol, "no_data", _NOT_REFRESHED))
            continue
        item = _snapshot_item(snapshot_from_dict(rec.snapshot), today, p_max, d_max,
                              target_month_rule)
        if failure is not None and failure.attempted_day > rec.as_of:
            # 最新一次嘗試失敗：沿用上一份成功資料，as_of 照實是那一天。
            item["refresh_error"] = {"day": failure.attempted_day,
                                     "message": failure.error}
        items.append(item)
    return items


def _universe_items(storage: Storage, source: AnalystSource,
                    opportunity: dict, today: date,
                    target_month_rule: str) -> list[dict]:
    """這位使用者母體裡每一檔的清單項目（含依其門檻算出的 `gate`）——
    共識清單與搜尋（`selected_items()`）共用同一份，入選集合不會分家。"""
    universe = search_universe.resolve_universe(opportunity)
    return _items(storage, source, universe.symbols, today,
                  _pct_to_ratio(opportunity["percentile_max"]),
                  _pct_to_ratio(opportunity["dispersion_max"]), target_month_rule)


def selected_items(storage: Storage, source: AnalystSource,
                   opportunity: dict, today: date, *,
                   target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> list[dict]:
    """共識清單裡 `gate.selected` 的項目（母體順序）——機會搜尋（OS-04／
    #393）省略 `symbols` 時的預設集合，與 `consensus_view()` 逐項相同。"""
    return [i for i in _universe_items(storage, source, opportunity, today,
                                       target_month_rule)
            if i["gate"]["selected"]]


def consensus_view(storage: Storage, source: AnalystSource | None,
                   opportunity: dict, today: date, *,
                   rules: ConsensusRules = DEFAULT_RULES,
                   target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> dict:
    """`GET /api/opportunity/consensus` 的完整回應。`opportunity` 是
    `opportunity_settings.effective()` 的輸出（門檻為百分比 0–100）。"""
    universe = search_universe.resolve_universe(opportunity)
    thresholds = {"percentile_max": opportunity["percentile_max"],
                  "dispersion_max": opportunity["dispersion_max"]}
    if source is None:
        items: list[dict] = []
        source_view = {"configured": False, "name": None, "is_fixture": False}
    else:
        items = _universe_items(storage, source, opportunity, today,
                                target_month_rule)
        source_view = {"configured": True, "name": source.name,
                       "is_fixture": bool(source.is_fixture)}
    with_data = [i for i in items if i["status"] not in ("no_data", "source_error")]
    coverage = {c: 0 for c in ("complete", "partial", "unknown")}
    for i in with_data:
        coverage[i["coverage"]] = coverage.get(i["coverage"], 0) + 1
    body = {
        "source": source_view,
        "universe": {"id": universe.id, "label": universe.label,
                     "provisional": universe.provisional,
                     "symbols": len(universe.symbols),
                     "with_data": len(with_data),
                     "insufficient": sum(1 for i in with_data
                                         if i["status"] in _INSUFFICIENT),
                     # 還沒建立（沒有快取、也還沒失敗過）的檔數（LIVE-T4／
                     # #400）：搜尋頁據此顯示「資料建立中」，不顯示空結果。
                     "not_built": sum(1 for i in items
                                      if i["reasons"] == [_NOT_REFRESHED]),
                     "coverage": coverage,
                     "as_of": max((i["as_of"] for i in items if i["as_of"]),
                                  default=None)},
        "thresholds": thresholds,
        "rules": rules_view(rules, target_month_rule),
        "items": items,
    }
    if source is None:
        body["message"] = NOT_CONFIGURED_MESSAGE
    return body


# ---------- 個股詳細資料（LIVE-T2／#399） ----------

def save_detail(storage: Storage, source: AnalystSource, snap: ConsensusSnapshot) -> None:
    """與 Snapshot 同一次計算的明細，每個 symbol 只留最新一筆。"""
    storage.save_consensus_detail(ConsensusDetailRecord(
        symbol=snap.symbol, as_of=snap.as_of.isoformat(), source=source.name,
        detail=detail_to_dict(snap),
        computed_at=(snap.computed_at or datetime.now(timezone.utc)).isoformat()))


def _float_fields(row: dict, names: Sequence[str]) -> dict:
    return {k: (float(v) if k in names and v is not None else v) for k, v in row.items()}


def detail_view(storage: Storage, source: AnalystSource | None, symbol: str,
                opportunity: dict, today: date, *,
                rules: ConsensusRules = DEFAULT_RULES,
                target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> dict:
    """`GET /api/opportunity/consensus-detail/{symbol}` 的完整回應——只讀快取。

    `item` 與共識清單的項目同一個形狀、同一份計算（含依這位使用者門檻的
    `gate`）；`effective`／`series` 來自同一次更新寫下的明細。明細與 Snapshot
    不是同一天、或不是同一個來源（例如明細寫入前中斷）時不拿來冒充目前的
    明細：`detail_available: false`、兩個清單為空，摘要數字照常。"""
    thresholds = {"percentile_max": opportunity["percentile_max"],
                  "dispersion_max": opportunity["dispersion_max"]}
    body: dict = {"symbol": symbol, "thresholds": thresholds,
                  "rules": rules_view(rules, target_month_rule),
                  "item": None, "effective": [], "series": [],
                  "qualified_points": 0, "detail_available": False}
    if source is None:
        body["source"] = {"configured": False, "name": None, "is_fixture": False}
        body["message"] = NOT_CONFIGURED_MESSAGE
        return body
    body["source"] = {"configured": True, "name": source.name,
                      "is_fixture": bool(source.is_fixture)}
    [item] = _items(storage, source, [symbol], today,
                    _pct_to_ratio(opportunity["percentile_max"]),
                    _pct_to_ratio(opportunity["dispersion_max"]), target_month_rule)
    body["item"] = item
    rec = storage.get_consensus_detail(symbol)
    if rec is None or rec.source != source.name or rec.as_of != item["as_of"]:
        return body
    body["effective"] = [_float_fields(e, ("target_price", "adjusted_price",
                                           "prior_target"))
                         for e in rec.detail["effective"]]
    body["series"] = [_float_fields(p, ("mean", "stdev", "dispersion"))
                      for p in rec.detail["series"]]
    body["qualified_points"] = sum(1 for p in rec.detail["series"] if p["qualified"])
    body["detail_available"] = True
    return body


# ---------- 每日摘要 ----------

def digest_counts(storage: Storage, source: AnalystSource | None,
                  today: date) -> dict | None:
    """今天（同一來源）的更新統計；來源未設定回 `None`。入選數以預設門檻
    （#389 §6：20%／10%）計算——門檻是每位使用者自己的設定，摘要只看全站。"""
    if source is None:
        return None
    p_max = _pct_to_ratio(DEFAULT_PERCENTILE_MAX)
    d_max = _pct_to_ratio(DEFAULT_DISPERSION_MAX)
    day = today.isoformat()
    attempted = [st for st in storage.consensus_refresh_states().values()
                 if st.source == source.name and st.attempted_day == day]
    ok_symbols = [st.symbol for st in attempted if st.error is None]
    snaps = storage.latest_consensus_snapshots(ok_symbols, source=source.name)
    todays = [snapshot_from_dict(r.snapshot) for r in snaps.values() if r.as_of == day]
    return {"source": source.name, "is_fixture": bool(source.is_fixture),
            "succeeded": len(ok_symbols),
            "failed": len(attempted) - len(ok_symbols),
            "insufficient": sum(1 for s in todays if s.status != "ok"),
            "selected": sum(1 for s in todays
                            if consensus.evaluate_gate(s, p_max, d_max).selected)}
