"""Application diagnostics（DG-02／spec #143）。

系統在關鍵節點呼叫 `emit()` 產生一筆 `DiagnosticEvent`，同時走兩條路：
寫進（可 capped、可讀回的）diagnostics storage，並印一行 structured
JSON runtime log——兩邊共用同一組 `event_id`／`correlation_id`，讓
「使用者手機畫面上看到的那次錯誤」對得回「Vercel runtime logs 裡的
那一次 request」。

**本檔案不接任何 subsystem**——它只是能力本身。Historical IV 的接線
在別的模組（DG-03／DG-04），透過呼叫 `emit()` 完成，這裡不 import
`option_chaser.data.marketdata` 或任何具體資料源。

**Redaction 用白名單，不是黑名單**：`context` 的 key 不在
`_CONTEXT_KEY_WHITELIST` 一律丟棄（不是遮罩）——「token 進不了
context」因此是結構上不可能，不必靠呼叫端自律。字串值再過
`sanitize_string()`：長度截斷＋樣式遮蔽（`Bearer …`／`token=` 之類的
query 參數／`postgres://` 連線字串）＋呼叫端傳入的已知現行祕密值
（目前設定中的 provider token、`DATABASE_URL` 家族環境變數的值）逐字
比對替換。

**診斷絕不能成為新的故障源**：`emit()` 整個包在 try/except 裡，storage
寫入失敗、序列化失敗都吞掉並繼續——診斷本身失敗不能拖垮它想觀測的
那個主流程。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Iterator

# ---------- 詞彙（單一來源，後端／前端／測試都引用同一份） ----------

# HIVR-03（#162）：exact-contract Historical IV Trend 與 legacy
# (tenor,delta) 重錨定是兩個獨立的 subsystem——每個 subsystem 各自有
# 獨立的 per-request 保留預算（見 `api_app/main.py` 的
# `_select_for_persistence`），大量 legacy 事件不會擠掉 exact-contract
# 事件，反之亦然。命名沿用既有欄位語意：`historical_iv` 是既有名字，
# 未改；`normalized_skew` 借用這條 legacy 路徑本身輸出欄位
# （`normalized_skew_points`／`normalized_skew`）的既有名字，不是新創
# 詞彙。
SUBSYSTEM_EXACT_CONTRACT = "historical_iv"
SUBSYSTEM_LEGACY_REANCHOR = "normalized_skew"

SUBSYSTEMS = (SUBSYSTEM_EXACT_CONTRACT, SUBSYSTEM_LEGACY_REANCHOR)

STAGES = ("candidate_lookup", "cache", "vendor_fetch", "payload_parse",
         "database_write", "backfill", "reanchor", "metrics")

SEVERITIES = ("info", "warning", "error")

# 全域 retention 上限（trim-on-write，見 `api_app/storage/memory.py`／
# `postgres.py` 的 `append_diagnostic()`）。單一處定義，兩個實作與端點
# 的預設 `limit` 都讀這個常數，不會各自維護一份可能漂移的數字。
#
# 選 200、選 trim-on-write 而非日期型 TTL 的理由：serverless 沒有背景
# 排程可以掛清理 job；一次 Historical IV backfill 就可能上百筆事件，
# 日期型 TTL 在單日內仍可無上限成長，擋不住這個風險。trim-on-write 發生
# 在唯一的寫入路徑上，上限因此是結構性的，不是「記得要清」的約定。
RETENTION_LIMIT = 200

_MESSAGE_MAX_LEN = 500
_STRING_MAX_LEN = 500
_TRUNCATION_SUFFIX = "…[截斷]"

# context 白名單——不在這裡的 key 直接丟棄，不落盤也不進 log。刻意保守：
# 之後真的需要新欄位再加，比一開始就開很大的口子安全。
_CONTEXT_KEY_WHITELIST = frozenset({
    # 身分／位置
    "scenario_id", "candidate_key", "provider", "symbol", "date",
    "expiration", "tenor_days", "url",
    # vendor_fetch
    "http_status", "vendor_status", "vendor_errmsg",
    "X-Api-Ratelimit-Limit", "X-Api-Ratelimit-Remaining",
    "X-Api-Ratelimit-Consumed",
    # payload_parse
    "raw_rows", "parsed_call_rows", "parsed_put_rows",
    "dropped_missing_delta", "dropped_missing_iv", "dropped_missing_dte",
    "dropped_unknown_side",
    # candidate_lookup
    "found", "groups_scanned",
    # cache／backfill
    "wanted_days", "have_days", "missing_days", "already_ran_today",
    "attempted_days", "saved_days", "aborted_on", "abort_reason",
    "remaining_gap", "outcome",
    # database_write
    "observed_on", "call_points", "put_points",
    # reanchor
    "buy_delta", "sell_delta", "surface_dte_min", "surface_dte_max",
    "surface_delta_min", "surface_delta_max", "buy_iv_null", "sell_iv_null",
    "atm_iv_null", "normalized_skew_null",
    # metrics
    "field", "count", "percentile_available", "trend_base_count",
    "correlation_id",
    # Exact-contract 歷史 IV（HIVT-02／#153，spec #151 §5）——additive，
    # 不動以上任何既有欄位。contract identity 四項（issue #153 明列的
    # underlying／expiration／strike／option_type）＋vendor 給的真實
    # OCC symbol；requested_from／requested_to 是這次向 vendor 要的區間
    # （跟舊路徑逐日一個 `date` 不同，這裡是一段區間）；parsed_rows／
    # null_iv_count／dropped_missing_date 是單合約回應的筆數帳本；
    # fetched_through／already_fetched_today 是漸進式刷新的快取狀態；
    # `lookback_days` 由 HIVT-03（#154）的 `metrics` stage 事件 emit
    # （moving_average／bollinger_bands／current_zscore 三項統計量各自
    # 的回溯窗天數）。
    "underlying", "expiration", "strike", "option_type", "contract_symbol",
    "requested_from", "requested_to", "parsed_rows", "null_iv_count",
    "dropped_missing_date", "observations_returned", "fetched_through",
    "already_fetched_today", "lookback_days",
})

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?:token|api[_-]?key|apikey)=[^&\s]+", re.IGNORECASE),
    re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE),
)

_logger = logging.getLogger("option_chaser.diagnostics")


@dataclass(frozen=True)
class DiagnosticEvent:
    event_id: str
    correlation_id: str
    ts: str
    subsystem: str
    stage: str
    severity: str
    message: str
    context: dict = field(default_factory=dict)


# ---------- correlation ID：每個 HTTP request 一個，emit() 自己讀 ----------
#
# 不從函式簽章往下傳——否則 `option_chaser/data/marketdata.py` 這種
# 引擎層模組會被迫認識「這次呼叫屬於哪個 HTTP request」，那是 HTTP 概念，
# 不該滲進資料源 adapter。middleware 在 request 開頭把它塞進這裡，
# `emit()` 需要時自己讀。

_correlation_id: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def correlation_scope(cid: str | None = None) -> Iterator[str]:
    """整個 request 的生命週期內，`emit()` 讀到的 correlation id 都是
    這一個——`main.py` 的 middleware 用它包住 `call_next()`。"""
    cid = cid or new_correlation_id()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)


def current_correlation_id() -> str | None:
    return _correlation_id.get()


# ---------- Redaction ----------

def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    # 截斷本身要看得出來，不能悄悄變短——閱讀的人得知道這句話被剪過。
    return value[: limit - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def _mask_patterns(value: str) -> str:
    out = value
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[redacted]", out)
    return out


def _mask_known_secrets(value: str, secrets: tuple[str, ...]) -> str:
    out = value
    for secret in secrets:
        if secret:
            out = out.replace(secret, "[redacted]")
    return out


def sanitize_string(value: str, *, secrets: tuple[str, ...] = ()) -> str:
    """一句話要進 diagnostics（event 的 `message`，或 context 裡任何字串
    值）之前，一律先過這裡：已知祕密值逐字比對替換 → 樣式遮蔽 → 長度
    截斷。三層各自防不同的洩漏方式，缺一層都不夠。"""
    return _truncate(_mask_patterns(_mask_known_secrets(value, secrets)),
                     _STRING_MAX_LEN)


def sanitize_context(context: dict, *, secrets: tuple[str, ...] = ()) -> dict:
    """白名單過濾＋逐一 sanitize 字串值＋丟掉 `None`（#143 Implementation
    Decisions §9：只顯示實際存在的欄位——後端在這裡就把空值拿掉，前端
    不必自己過濾）。"""
    out: dict = {}
    for key, value in context.items():
        if key not in _CONTEXT_KEY_WHITELIST:
            continue
        if value is None:
            continue
        out[key] = (sanitize_string(value, secrets=secrets)
                   if isinstance(value, str) else value)
    return out


# ---------- emit() ----------

class DiagnosticsStorage:
    """`emit()` 需要的最小 storage 介面——鴨子定型，不 import
    `api_app.storage`（避免循環 import；`Storage` protocol 反過來從這裡
    引用 `DiagnosticEvent`）。"""

    def append_diagnostic(self, event: DiagnosticEvent) -> None: ...


def _log_line(event: DiagnosticEvent) -> str:
    return json.dumps(asdict(event), ensure_ascii=False, sort_keys=True)


def emit(storage: DiagnosticsStorage, *, subsystem: str, stage: str,
        severity: str, message: str, ts: str,
        secrets: tuple[str, ...] = (), **context) -> DiagnosticEvent | None:
    """唯一的產生入口。做四件事：組出 event → sanitize → 印 structured
    JSON log → 寫 storage。任何一步失敗都吞掉、**絕不拋出**——診斷不得
    成為新的故障源，呼叫端也不必為了呼叫 `emit()` 額外包 try/except。

    只有「連 event 都組不出來」（sanitize 本身炸掉）才回 `None`；
    log／storage 任一步失敗不影響回傳值——event 物件本身仍照樣給呼叫端，
    因為 DG-03 的 in-response diagnostics（把這次 request 產生的 events
    夾帶進 iv-history 回應）只需要這個記憶體內的物件，不依賴 storage
    寫入成功與否。

    `ts` 由呼叫端傳入（沿用整個專案「儲存層零 wall-clock」的既有慣例，
    測試才有決定性）。`secrets` 是呼叫端目前手上已知的現行祕密值
    （provider token、`DATABASE_URL`……），用於逐字比對替換；
    `sanitize_context()` 的白名單與樣式遮蔽不依賴這份清單也會擋掉常見
    洩漏形式，這是額外一層針對「已知就是這把」的精準防護。
    """
    try:
        event = DiagnosticEvent(
            event_id=uuid.uuid4().hex,
            correlation_id=current_correlation_id() or new_correlation_id(),
            ts=ts, subsystem=subsystem, stage=stage, severity=severity,
            message=sanitize_string(_truncate(message, _MESSAGE_MAX_LEN),
                                    secrets=secrets),
            context=sanitize_context(context, secrets=secrets),
        )
    except Exception:  # noqa: BLE001 — 連組 event 都不能拖垮呼叫端
        _safe_log_exception()
        return None

    _safe_log(event)

    try:
        storage.append_diagnostic(event)
    except Exception:  # noqa: BLE001 — storage 掛了不能讓主流程也掛
        _safe_log_exception()
    return event


def _safe_log(event: DiagnosticEvent) -> None:
    try:
        _logger.info(_log_line(event))
    except Exception:  # noqa: BLE001
        _safe_log_exception()


def _safe_log_exception() -> None:
    try:
        _logger.exception("diagnostics 內部失敗（已吞掉，不影響主流程）")
    except Exception:  # noqa: BLE001 — 連記錄失敗本身都要能失敗得無聲無息
        pass
