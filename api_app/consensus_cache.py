"""分析師共識的全站快取、每日更新與清單 view（OS-03／#392，母票 #389 §3／§7／§8）。

三件事，都只透過 `Storage` 與注入的 `AnalystSource`，數值一律交給
`option_chaser.consensus`（本模組不做任何共識計算）：

1. **更新**（`refresh_symbols()`，給 `GET /api/cron/consensus-refresh` 與
   SU／SA 的 `POST /api/opportunity/consensus/update`，兩者同一套核心）：
   - **成功**的 symbol 同一交易日不再抓；**失敗**的同一交易日內可以有限次
     重試（`RefreshPolicy`，LIVE-T3／#398 經 LIVE-TICKET-CORRECTION-001
     修正）：每次重試前要過冷卻；429 有 `Retry-After` 時取它和冷卻較長者，
     沒有就用 429 專用冷卻；重試用完改到下一個交易日（`trading_day()`：
     週末算前一個週五）；遇到 429 整個來源暫停（`pause_source()`），這次
     立刻停、暫停期間不打上游；
   - 每次上游呼叫先在全站共用的每日上限（沿用 `rate_limits` 計數）扣一次——
     重試也算，扣不到就停止並回報，不打上游；
   - 同一 symbol 同一時間只有一次上游呼叫：先取「處理中」標記（有逾時），
     取到後**重讀狀態**再確認一次（別人可能剛抓完）；兩次上游呼叫之間有間隔；
   - 成功 → 以 `compute_snapshot()` 算出當天的 Snapshot，寫一筆
     (symbol, as_of)；失敗 → 只記錄嘗試（`ConsensusRefreshState.error`），
     **上一份成功的 Snapshot 原樣保留**，清單照實標出它的 as_of；
   - **進度游標**＝每個 symbol 的嘗試紀錄：每次呼叫依**公平輪替**
     （`rotation_key()`：從沒嘗試過 → 最久沒嘗試 → 同日嘗試的資料最舊者，
     V2-02／#403）處理，受時間預算（與 SU 端點的每批檔數）約束；
     跑不完的放 `remaining`，由下一次呼叫（前端自動續跑或明天的 cron）接續。
   狀態 API 用 `refresh_status()`。
2. **清單**（`consensus_view()`，給 `GET /api/opportunity/consensus`）：只讀
   快取、不打上游；讀取時才以使用者的兩道門檻 `evaluate_gate()`——改門檻
   立即生效，不必重抓。
3. **每日摘要統計**（`digest_counts()`）與**排程執行紀錄**（`cron_view()`）。

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

from . import metrics, search_universe
from .price_quote import quote_record, upside_fields
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
# 每日更新範圍的總上限（V2-02／#403）：S&P 500（約 503 檔）＋約兩份滿額
# （各 `CUSTOM_SYMBOLS_MAX`＝50 檔）的成分股以外自訂清單。超出的照實列為
# `out_of_scope`。可用 `create_app(consensus_refresh_symbol_cap=)` 或
# `CONSENSUS_REFRESH_SYMBOL_CAP` 覆寫。
DEFAULT_REFRESH_SYMBOL_CAP = 600
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
    """每日更新的母體 = 預設掃描範圍（S&P 500 成分股，V2-01／#404）∪
    **目前權限為 SU／SA** 的 owner 的自訂清單（#392；Normal 寫不進、也不會
    被併入——`Storage.opportunity_custom_symbols()` 只回特權 owner 的清單）。

    總數不超過 `cap`（預設 600：整份成分股＋約兩份滿額的自訂清單，V2-02／
    #403；超出的照實列為 `out_of_scope`）。這裡的順序**只**決定超出上限時
    誰被截掉，而且是決定性的（同一份資料每天選出同一批）；每次續跑先抓誰
    由公平輪替決定（`rotation_key()`），與這個順序無關：
    1. `REFRESH_PRIORITY`（原大型股樣本 50 檔，全是成分股）；
    2. 自訂清單，canonical 化後依代號排序——維持 #392 起「自訂清單一定在
       樣本之後、成分股其餘之前」的承諾，不會被 500 檔擠掉；
    3. 其餘成分股，依清單順序。"""
    custom = search_universe.canonical_symbols(storage.opportunity_custom_symbols())
    default = search_universe.resolve_universe(None).symbols
    ordered = [*search_universe.REFRESH_PRIORITY, *sorted(custom), *default]
    return list(dict.fromkeys(ordered))[:cap]


def out_of_scope(search_symbols: Sequence[str],
                 refresh_symbols: Sequence[str]) -> list[str]:
    """使用者母體裡、不在每日更新母體（`refresh_universe()`，有上限）的代號——
    它們永遠不會被更新，進度與「建立中」不能等它們（母體順序）。"""
    allowed = set(refresh_symbols)
    return [s for s in dict.fromkeys(search_symbols) if s not in allowed]


@dataclass(frozen=True)
class RefreshPolicy:
    """更新的重試／限流參數（LIVE-T3／#398，全部可設定、有明確預設）。

    `create_app(consensus_refresh_policy=)` 注入；沒注入時 `from_env()` 讀
    `CONSENSUS_*` 環境變數，再落回這裡的預設。時間單位都是秒。"""

    max_retries: int = 3                     # 失敗後同一交易日最多再試幾次
    retry_cooldown_seconds: int = 900        # 每次重試前的冷卻（15 分）
    rate_limit_cooldown_seconds: int = 1800  # 429 沒給 Retry-After 時（30 分）
    # 每日上游呼叫上限（一次＝一檔 fetch，約 2 個 HTTP 請求）。V2-02／#403：
    # 900＝每日更新範圍上限 600 × 1.5——一整輪（最多 600 檔）之外還留給失敗
    # 重試約 300 次；實測見 docs/spec/options-scanner/daily-rotation.md。
    daily_upstream_cap: int = 900
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
CRON_RUN_METRIC = "consensus_cron_run_count"
NOT_RETRYABLE_STAGE = "consensus_not_retryable"
DAILY_CAP_STAGE = "consensus_daily_cap"
DAILY_CAP_MESSAGE = "今日分析師資料的上游呼叫已達每日上限，下一個交易日自動恢復"
RATE_LIMITED_STAGE = "consensus_rate_limited"
RATE_LIMITED_MESSAGE = ("資料來源回應限流（429），所有分析師資料更新暫停到冷卻結束，"
                        "期間不會再呼叫來源")
# 429 後的全站暫停：存在既有的「處理中」標記表裡一個保留鍵（不是合法代號，
# 不會跟任何 symbol 撞），到期時間＝暫停結束——不用新表，memory／Postgres
# 同一套語意。
_PAUSE_KEY = "!rate_limited:{source}"
_PAUSE_HOLDER = "source-pause"
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
    """美東 `day` 的零時（UTC）——「下一個交易日再試」與每日上限（仍以美東
    日曆日計）的界線。"""
    return datetime.combine(day, datetime.min.time(), tzinfo=_EASTERN).astimezone(
        timezone.utc)


def trading_day(day: date) -> date:
    """美東日期 `day` 所屬的交易日：週六、週日算前一個週五。本站不維護美股
    假日表（比照 `option_chaser.ivpipeline._most_recent_trading_day_before`），
    假日照平日算——最多多抓一次，不會漏抓。"""
    return day - timedelta(days=max(0, day.weekday() - 4))


def next_trading_day(day: date) -> date:
    """`day` 之後的第一個交易日（週五、週六、週日 → 下週一）。"""
    nxt = trading_day(day) + timedelta(days=1)
    return nxt + timedelta(days=7 - nxt.weekday()) if nxt.weekday() >= 5 else nxt


def _same_trading_day(attempted_day: str, today: date) -> bool:
    return trading_day(date.fromisoformat(attempted_day)) == trading_day(today)


def _upstream_bucket(source: AnalystSource, today: date,
                     policy: RefreshPolicy) -> RateLimitBucket:
    """每日上游呼叫上限的計數格：沿用 `rate_limits`（SECURITY-FIX-02）的原子
    「檢查＋扣一次」，鍵＝來源名稱＋美東日；過期列由既有清理 cron 刪掉。"""
    return RateLimitBucket(_UPSTREAM_SCOPE, source.name, _DAY_SECONDS,
                           int(_day_start(today).timestamp()),
                           policy.daily_upstream_cap)


def _rate_limit_cooldown(policy: RefreshPolicy, retry_after: int | None) -> int:
    """429 的冷卻秒數：有 `Retry-After` 取它和一般冷卻較長者，沒有用 429 專用
    冷卻（預設 30 分）。單檔的下次重試與全站暫停用同一條規則。"""
    if retry_after is None:
        return policy.rate_limit_cooldown_seconds
    return max(policy.retry_cooldown_seconds, retry_after)


def rate_limited_until(storage: Storage, source: AnalystSource, *,
                       now: float) -> float | None:
    """這個來源的 429 全站暫停到什麼時候（epoch 秒）；沒有暫停回 `None`。"""
    return storage.consensus_refresh_leases(now=now).get(
        _PAUSE_KEY.format(source=source.name))


def pause_source(storage: Storage, source: AnalystSource, *, now: float,
                 seconds: float) -> None:
    """429 之後暫停這個來源的所有上游呼叫 `seconds` 秒；已經有更晚結束的暫停
    就沿用它（只延長、不縮短）。"""
    current = rate_limited_until(storage, source, now=now)
    if current is not None and current >= now + seconds:
        return
    key = _PAUSE_KEY.format(source=source.name)
    storage.release_consensus_refresh_lease(key, _PAUSE_HOLDER)
    storage.acquire_consensus_refresh_lease(key, _PAUSE_HOLDER, now=now,
                                            ttl_seconds=seconds)


def _own(st: ConsensusRefreshState | None,
         source: AnalystSource) -> ConsensusRefreshState | None:
    """只認目前來源寫的狀態——換來源等於從沒試過。"""
    return st if st is not None and st.source == source.name else None


def _classify(st: ConsensusRefreshState | None, today: date, now: float,
              policy: RefreshPolicy) -> str:
    """一檔現在的狀態（不含處理中標記）：`pending`（這個交易日還沒試過）／
    `done`（這個交易日已成功）／`cooling`（失敗、冷卻中）／`retry_ready`（失敗、
    冷卻已過、還有重試次數）／`exhausted`（這個交易日重試用完）。「今天」以
    交易日（`trading_day()`）比較：週五成功，週末不重抓。"""
    if st is None or not _same_trading_day(st.attempted_day, today):
        return "pending"
    if st.error is None:
        return "done"
    if st.attempts >= 1 + policy.max_retries:
        return "exhausted"
    if st.next_retry_at is not None and now < _epoch(st.next_retry_at):
        return "cooling"
    return "retry_ready"


def rotation_key(symbol: str, st: ConsensusRefreshState | None) -> tuple:
    """公平輪替的順序（V2-02／#403）：cron 與 SU「繼續更新」每次呼叫都依它挑
    下一檔，不再是固定的清單順序。

    1. 從沒嘗試過的先（`attempted_day` 空字串最小）；
    2. 最久沒嘗試的先（以嘗試的美東日比）；
    3. 同一天嘗試過的，資料最舊的先（從沒成功過＝最舊）；
    4. 再依嘗試時刻、代號——決定性的。

    為什麼每一檔都會在 N＝ceil(範圍／每日處理量) 個交易日內輪到：某檔 X 上次
    在第 d 天被嘗試後，排在它前面的只可能是「嘗試日 ≤ d」的那些（至多 範圍−1
    檔）；X 沒被輪到的每一個交易日都有「每日處理量」檔排在它前面的被嘗試、
    嘗試日變成今天、從此排到 X 後面。所以 X 最多被跳過 floor((範圍−1)／處理量)
    個交易日。同一交易日的失敗重試（嘗試日＝今天）一定排在所有還沒輪到的
    後面，重試不會吃掉首次嘗試的名額。"""
    if st is None:
        return ("", "", "", symbol)
    return (st.attempted_day, (st.last_success_at or "")[:10], st.attempted_at, symbol)


def _skip(symbol: str, state: str, st: ConsensusRefreshState | None) -> dict:
    return {"symbol": symbol, "state": state,
            "next_retry_at": st.next_retry_at if st is not None and st.error else None,
            "message": _SKIP_MESSAGES.get(state, state)}


def _refresh_one(storage: Storage, source: AnalystSource, symbol: str,
                 today: date, rules: ConsensusRules, now: float,
                 previous: ConsensusRefreshState | None,
                 policy: RefreshPolicy) -> tuple[str, int | None]:
    """抓一檔、存結果；回傳 (`"ok"`（成功算出 Snapshot，不論資料品質）／
    `"failed"`（來源回報錯誤或丟例外）／`"rate_limited"`（429），429 的冷卻
    秒數)。失敗時依重試規則寫下次可重試時間。"""
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
                if previous is not None and _same_trading_day(previous.attempted_day, today)
                else 1)
    if error is None:
        snap = consensus.compute_snapshot(
            result.records, result.splits, today, rules, symbol=symbol,
            coverage=result.coverage, source=source.name,
            cross_check=result.cross_check, computed_at=at,
            weekly_closes=result.weekly_closes)
        stored = snapshot_to_dict(snap)
        # V2-05（#407）：同一次抓取的目前股價跟快照一起存（JSON 欄位，additive；
        # 舊快照沒有這個鍵 → 畫面「尚未取得股價」）。
        stored["quote"] = quote_record(result.quote, result.splits, today)
        storage.save_consensus_snapshot(ConsensusSnapshotRecord(
            symbol=symbol, as_of=day, source=source.name,
            is_fixture=bool(source.is_fixture), snapshot=stored,
            computed_at=at.isoformat()))
        save_detail(storage, source, snap)
        next_retry_at, last_success_at = None, at.isoformat()
    else:
        if attempts >= 1 + policy.max_retries:
            # 重試用完：改到下一個交易日（那天 attempts 歸零重算）。
            next_retry_at = _day_start(next_trading_day(today)).isoformat()
        elif rate_limited:
            next_retry_at = _iso(int(now) + _rate_limit_cooldown(policy, retry_after))
        else:
            next_retry_at = _iso(int(now) + max(policy.retry_cooldown_seconds,
                                                retry_after or 0))
        last_success_at = previous.last_success_at if previous is not None else None
    storage.save_consensus_refresh_state(ConsensusRefreshState(
        symbol=symbol, source=source.name, attempted_day=day,
        attempted_at=at.isoformat(), error=error, attempts=attempts,
        next_retry_at=next_retry_at, last_success_at=last_success_at))
    if error is None:
        return "ok", None
    if rate_limited:
        return "rate_limited", _rate_limit_cooldown(policy, retry_after)
    return "failed", None


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
    上限已滿；`"rate_limited"`＝來源回 429，或 429 的全站暫停還沒結束，
    `rate_limited_until` 是暫停結束時間；`message` 說明）與今天已用的上游
    呼叫數。

    429 不只冷卻那一檔：整個來源暫停（`pause_source()`），這次呼叫立刻停下、
    剩下的不打；暫停期間的續跑、cron 與重試都不呼叫上游。"""
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
    pending.sort(key=lambda s: rotation_key(s, own[s]))
    done_today = sum(1 for s in wanted
                     if own[s] and _same_trading_day(own[s].attempted_day, today))

    holder = uuid.uuid4().hex
    bucket = _upstream_bucket(source, today, policy)
    succeeded = failed = calls = 0
    processed: list[str] = []
    stopped_reason = message = None
    index = 0
    paused_until = None
    while index < len(pending):
        if processed and (budget_exhausted() or (batch_limit is not None
                                                 and len(processed) >= batch_limit)):
            break
        paused_until = rate_limited_until(storage, source, now=clock())
        if paused_until is not None:
            stopped_reason, message = "rate_limited", RATE_LIMITED_MESSAGE
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
            outcome, pause_seconds = _refresh_one(storage, source, symbol, today,
                                                  rules, clock(), current, policy)
            if outcome == "rate_limited":
                pause_source(storage, source, now=clock(), seconds=pause_seconds)
        finally:
            storage.release_consensus_refresh_lease(symbol, holder)
        processed.append(symbol)
        index += 1
        if outcome == "ok":
            succeeded += 1
        else:
            failed += 1
        if outcome == "rate_limited":
            paused_until = rate_limited_until(storage, source, now=clock())
            stopped_reason, message = "rate_limited", RATE_LIMITED_MESSAGE
            break
    return {"source": source.name, "as_of": day, "processed": len(processed),
            "processed_symbols": processed,
            "succeeded": succeeded, "failed": failed,
            "already_attempted_today": done_today,
            "remaining": pending[index:], "skipped": skipped,
            "stopped_reason": stopped_reason, "message": message,
            "rate_limited_until": _iso(paused_until) if paused_until is not None else None,
            "upstream_calls_today": storage.rate_limit_count(bucket),
            "daily_cap": policy.daily_upstream_cap}


def refresh_status(storage: Storage, source: AnalystSource | None,
                   symbols: Sequence[str], today: date, *, now: float,
                   policy: RefreshPolicy = DEFAULT_POLICY,
                   search_symbols: Sequence[str] = ()) -> dict:
    """狀態 API（`GET /api/opportunity/consensus/status`，只限 SU／SA）：每檔
    最後成功／嘗試時間、失敗原因、今日已重試次數、下次可重試時間；全體進度、
    資料日期與今天已用的上游呼叫數。

    `symbols` 是每日更新母體，進度只算它；`search_symbols`（這位使用者的
    母體）裡超出更新母體的另外列在 `out_of_scope`／`out_of_scope_symbols`。"""
    outside = out_of_scope(search_symbols, symbols) if source is not None else []
    base = {"today": today.isoformat(), "now": _iso(now), "policy": policy.view(),
            "daily_cap": policy.daily_upstream_cap, "cron": cron_view(storage, today),
            "out_of_scope": len(outside), "out_of_scope_symbols": outside}
    if source is None:
        return {**base, "source": {"configured": False, "name": None,
                                   "is_fixture": False},
                "progress": _progress([]), "symbols": [], "data_as_of": None,
                "upstream_calls_today": 0, "rate_limited_until": None}
    wanted = list(dict.fromkeys(symbols))
    states = storage.consensus_refresh_states()
    leases = storage.consensus_refresh_leases(now=now)
    snaps = storage.latest_consensus_snapshots(wanted, source=source.name)
    rows = []
    for symbol in wanted:
        st = _own(states.get(symbol), source)
        state = "in_progress" if symbol in leases else _classify(st, today, now, policy)
        attempts_today = (st.attempts if st and _same_trading_day(st.attempted_day, today)
                          else 0)
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
                _upstream_bucket(source, today, policy)),
            "rate_limited_until": (_iso(paused) if (paused := rate_limited_until(
                storage, source, now=now)) is not None else None)}


def cron_view(storage: Storage, today: date) -> dict:
    """排程實際執行的紀錄（V2-02／#403）：今天授權成功的執行次數、處理的檔數，
    以及保留窗內（`metrics.RETENTION_DAYS`）最近一次執行的美東日。

    只有 `GET /api/cron/consensus-refresh` 授權成功才會留紀錄（被 401 的呼叫
    什麼都不寫），所以 `last_run_day: None` 就是「排程尚未執行」——正式站沒設
    `CRON_SECRET` 時就是這樣，畫面與摘要照實顯示，不假裝排程正常。"""
    entries = [e for e in storage.metric_summary()
               if e.metric == CRON_RUN_METRIC and e.count > 0]
    day = today.isoformat()
    return {"runs_today": sum(e.count for e in entries if e.bucket == day),
            "symbols_today": int(sum(e.total for e in entries if e.bucket == day)),
            "last_run_day": max((e.bucket for e in entries), default=None),
            "lookback_days": metrics.RETENTION_DAYS}


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
          target_month: str | None = None,
          quote: dict | None = None, today: date | None = None) -> dict:
    """清單項目的唯一形狀（有無 Snapshot 都走這裡，鍵不會分家）。沒有
    Snapshot 時數值一律 `None`、人數與歷史點數為 0。股價欄位（`price`…
    `target_upside_reason`，V2-05／#407）見 `price_quote.upside_fields()`。"""
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
            "refresh_error": None,
            **upside_fields(quote, snap.mean if snap else None, today)}


def _empty_item(symbol: str, status: str, reason: str) -> dict:
    return _item(symbol, status, reasons=[reason],
                 gate={"first": False, "second": False, "selected": False,
                       "reasons": [reason]})


def _snapshot_item(snap: ConsensusSnapshot, today: date, p_max: Decimal,
                   d_max: Decimal, target_month_rule: str,
                   quote: dict | None = None) -> dict:
    try:
        month = consensus.target_month(snap, today, target_month_rule)
    except ValueError:
        month = None
    return _item(snap.symbol, snap.status, reasons=snap.reasons, snap=snap,
                 gate=_gate_view(consensus.evaluate_gate(snap, p_max, d_max)),
                 target_month=month, quote=quote, today=today)


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
                              target_month_rule, quote=rec.snapshot.get("quote"))
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
                   target_month_rule: str = DEFAULT_TARGET_MONTH_RULE,
                   refresh_symbols: Sequence[str] | None = None) -> dict:
    """`GET /api/opportunity/consensus` 的完整回應。`opportunity` 是
    `opportunity_settings.effective()` 的輸出（門檻為百分比 0–100）。

    `refresh_symbols`＝每日更新母體（`refresh_universe()`）：使用者母體裡不在
    其中的代號永遠不會被更新，不算 `not_built`，另列在 `out_of_scope`／
    `out_of_scope_symbols`。`None`＝不區分（全部視為在更新範圍內）。"""
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
    outside = (out_of_scope(universe.symbols, refresh_symbols)
               if refresh_symbols is not None and source is not None else [])
    outside_set = set(outside)
    with_data = [i for i in items if i["status"] not in ("no_data", "source_error")]
    coverage = {c: 0 for c in ("complete", "partial", "unknown")}
    for i in with_data:
        coverage[i["coverage"]] = coverage.get(i["coverage"], 0) + 1
    body = {
        "source": source_view,
        "universe": {"id": universe.id, "label": universe.label,
                     "provisional": universe.provisional,
                     # 清單版本日期（S&P 500 成分股，#404）；自訂清單為 null。
                     "version_date": universe.version_date,
                     "symbols": len(universe.symbols),
                     "with_data": len(with_data),
                     "insufficient": sum(1 for i in with_data
                                         if i["status"] in _INSUFFICIENT),
                     # 還沒建立（沒有快取、也還沒失敗過）的檔數（LIVE-T4／
                     # #400）：搜尋頁據此顯示「資料建立中」，不顯示空結果。
                     # 超出每日更新母體的不算（它們不會被建立，`out_of_scope`）。
                     "not_built": sum(1 for i in items
                                      if i["reasons"] == [_NOT_REFRESHED]
                                      and i["symbol"] not in outside_set),
                     "out_of_scope": len(outside),
                     "out_of_scope_symbols": outside,
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
                  today: date, universe: Sequence[str] = ()) -> dict | None:
    """今天（同一來源）的更新統計；來源未設定回 `None`。入選數以預設門檻
    （#389 §6：20%／10%）計算——門檻是每位使用者自己的設定，摘要只看全站。

    V2-02／#403：`universe`＝每日更新範圍（`refresh_universe()`）；
    `not_reached`＝其中這個交易日還沒被嘗試過的檔數（公平輪替還沒輪到）；
    `cron`＝排程實際執行的紀錄（`cron_view()`）。"""
    if source is None:
        return None
    states = storage.consensus_refresh_states()
    wanted = list(dict.fromkeys(universe))
    not_reached = sum(
        1 for s in wanted
        if (st := _own(states.get(s), source)) is None
        or not _same_trading_day(st.attempted_day, today))
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
                            if consensus.evaluate_gate(s, p_max, d_max).selected),
            "universe": len(wanted), "not_reached": not_reached,
            "cron": cron_view(storage, today)}
