"""HTTP API —— 後端與前端之間的唯一接縫（spec #47）。

薄殼原則：本層不做任何金融計算，也不碰 SQL——只負責 HTTP 邊界（請求
驗證、呼叫引擎、呼叫儲存介面、錯誤映射）。回應主體直接是引擎既有的
view dict（`store.serialize_result`），前端因此也零金融計算。

serverless 前提：全程不碰檔案系統（Vercel 唯讀），走
`service.fetch_chain`＋`service.run_with_snapshot` 這組記憶體路徑；
資料落在可替換的儲存 adapter（`api_app/storage/`）。
"""
from __future__ import annotations

import dataclasses
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator

from option_chaser import (__version__, dividends, ivhistory, ivreconstruct,
                           ivspread, ivtrend, ratecurve, service, store)
from option_chaser.data import treasury as treasury_data
from option_chaser.data.snapshot import snapshot_from_dict, snapshot_to_csv
from option_chaser.models import (AnalysisParams, ChainSnapshot, FetchError,
                                  ParamError, QuotaExhausted, STRATEGIES)
from option_chaser.service import DividendLoader, RateCurveLoader
from option_chaser.timeframe import (TargetMonth, calendar_anchor,
                                     ensure_month_open, month_is_over)
from option_chaser.valuation import DAYS_PER_YEAR, days_between
from option_chaser.workspace import now_utc_iso, ny_today

from . import diagnostics, providers
from . import chain_cache
from .chain_cache import cached_fetch_chain
from .dividend_cache import cached_loader as cached_dividend_loader
from .rate_cache import cached_loader
from .storage import (ContractHistory, DataSourceSettings, IvBackfillRun,
                      IvObservation, ProviderCredential, ProviderVerification,
                      RateCacheEntry, ResultRecord, ResultSummary, Scenario,
                      ScenarioExists, Storage, UsageSetting)
from .storage.factory import database_url_candidates, storage_from_env
from .treasury_cache import cached_rate_curve_rows

FetchChain = Callable[[str], ChainSnapshot]
# 自訂 Provider 的兩條路徑（Settings／#125），皆可注入 → 測試離線。
VerifyProvider = Callable[[str, str], "providers.VerifyOutcome"]
CustomFetch = Callable[[str, str, str], ChainSnapshot]
# (provider, symbol, date, token, expiration=None) ->
#   {"call": [SurfacePoint], "put": [...]}
HistoricalSurface = Callable[..., dict]
# (provider, occ_symbol, from_date, to_date, token) -> [(date, iv|None), ...]
# HIVT-02（#153）：exact-contract 家族，跟上面的 HistoricalSurface（整鏈、
# (tenor, delta) 重錨定家族）是不同的資料語意，不共用型別也不共用注入點。
ContractHistoryFetch = Callable[..., list]
# (from_date, to_date) -> ((curve_date, ((tenor, rate), ...)), ...)
# HIVR-06（#165）：point-in-time 利率查詢用的全部曲線列（HIVR-01／#160
# 的 `ratecurve.curve_asof` 吃這個形狀），跟上面 `RateCurveLoader`（只回
# 「今天」單一曲線，live 分析路徑專用）是不同的資料語意，不共用注入點。
RateCurveRowsFetch = Callable[[date, date], tuple]

# MVP 範圍（沿用既有 Streamlit 版與 spec #47 的三欄表單）：方向與策略
# 是固定值，不由前端送。需要看空或多策略時再由對應的票加上。
_MVP_DIRECTION = "bullish"
_MVP_STRATEGIES = ("bull-call-spread",)

# 每個 symbol 每批最多補幾天（#130）。66 個目標觀測 ÷ 25 ≈ 三天補齊，
# 就是需求方 progressive backfill 草圖裡那三格進度條。
_IV_BACKFILL_PER_RUN = 25

# PERF-05（#181）：cold backfill 同一天內、跨到期日的併發呼叫上限——
# 保守值，不是「猜到期日通常有幾個就設幾個」。到期日梯子
# （`ivhistory.nearby_expirations()`）目前實務上是個位數項目，這個
# 常數的用意是**防禦性上限**：不論梯子未來變多長，一次最多同時有這
# 麼多個尚未完成的呼叫在飛，不是「一次把全部到期日同時發出去」的
# 無上限 fan-out。具名、可調整——沒有查到 vendor 端逐秒配額文件，
# 用一個明顯遠低於「同時炸開全部」的保守數字。
_IV_BACKFILL_DAY_CONCURRENCY = 4

# V1（#48）的一次性分析端點沿用：無劇本身分時的 view dict 欄位值，
# 不影響任何計算。V3 之後前端改走劇本端點，屆時此路徑可移除。
_ADHOC_SCENARIO_ID = "adhoc"

_SYMBOL = Field(pattern=r"^[A-Za-z.\-]{1,10}$")
_MONTH = Field(pattern=r"^\d{4}-\d{2}$")


class AnalyzeRequest(BaseModel):
    # symbol 會被代入資料源的 URL（`data/cboe.py`），因此限制成標的代號
    # 真正可能出現的字元，不讓 `../` 之類的東西有機會進到路徑裡。
    symbol: str = _SYMBOL
    target_price: float = Field(gt=0)
    target_month: str = _MONTH
    strategies: list[Literal[STRATEGIES]] = Field(min_length=1)  # type: ignore[valid-type]

    @field_validator("strategies")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        """同一策略送兩次沒有意義（引擎會重算一遍），去重但保留順序。"""
        return list(dict.fromkeys(v))


class CreateScenarioRequest(BaseModel):
    symbol: str = _SYMBOL
    target_price: float = Field(gt=0)
    target_month: str = _MONTH
    notes: str = ""
    # V7（#55）劇本區間兩端，選填（留白＝未設定，不報錯）。
    best_price: float | None = Field(default=None, gt=0)
    worst_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _ends_must_straddle_the_target(self) -> "CreateScenarioRequest":
        """方向合理性（票上「依工程判斷處理並記錄」的裁示）。

        本輪只有看漲策略（`_MVP_DIRECTION`），所以區間必然是
        最低 <= 目標 <= 最高。填反了幾乎一定是打錯欄位——擋在這裡，
        而不是靜靜算出一組「最高價位比目標價還低」的數字讓人自己看出不對。
        兩端可以等於目標價（等於就是「這一端沒有想像空間」，是有意義的
        主張，不擋）。
        """
        if self.best_price is not None and self.best_price < self.target_price:
            raise ValueError(
                f"最高價位（{self.best_price}）不可低於目標價（{self.target_price}）")
        if self.worst_price is not None and self.worst_price > self.target_price:
            raise ValueError(
                f"最低價位（{self.worst_price}）不可高於目標價（{self.target_price}）")
        return self


class EditScenarioRequest(BaseModel):
    """編輯劇本（#132）。

    **沒有 `symbol` 欄位**——標的不可改不是靠前端把輸入框反灰，而是這個
    請求模型根本沒有那個欄位可以送。要換 underlying 就是另一個劇本。
    """
    target_price: float = Field(gt=0)
    target_month: str = _MONTH
    notes: str = ""
    best_price: float | None = Field(default=None, gt=0)
    worst_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _ends_must_straddle_the_target(self) -> "EditScenarioRequest":
        """與建立同一條規則（`CreateScenarioRequest`）：本輪只有看漲策略，
        區間必然是最低 <= 目標 <= 最高。編輯不該是繞過驗證的後門。"""
        if self.best_price is not None and self.best_price < self.target_price:
            raise ValueError(
                f"最高價位（{self.best_price}）不可低於目標價（{self.target_price}）")
        if self.worst_price is not None and self.worst_price > self.target_price:
            raise ValueError(
                f"最低價位（{self.worst_price}）不可高於目標價（{self.target_price}）")
        return self


class UsageRequest(BaseModel):
    """`Data / API` 其中一列的送出值（Settings／#124）。"""
    mode: Literal[providers.MODES]  # type: ignore[valid-type]
    provider: str | None = None

    @model_validator(mode="after")
    def _provider_matches_mode(self) -> "UsageRequest":
        """自訂**只能**挑已內建 adapter 的資料源——白名單擋在這裡，前端
        送什麼都繞不過去（前端的下拉只是方便，不是防線）。

        預設模式一律把 provider 歸零，不留一個「模式是預設、卻還記著上次
        選的 provider」的狀態——那種資料讀回來時無從判斷該信哪一邊。
        """
        if self.mode == providers.MODE_DEFAULT:
            return self.model_copy(update={"provider": None})
        if self.provider is None:
            raise ValueError("自訂模式必須指定資料源")
        if not providers.is_supported(self.provider):
            raise ValueError(f"不支援的資料源：{self.provider}")
        return self


class SettingsRequest(BaseModel):
    market_data: UsageRequest
    historical_iv: UsageRequest


class CredentialRequest(BaseModel):
    # 前後空白幾乎一定是貼上時多帶的，不是 token 的一部分；留著會讓
    # 驗證莫名其妙失敗。`min_length` 在去空白之後才檢查。
    token: str

    @field_validator("token")
    @classmethod
    def _strip_and_require(cls, v: str) -> str:
        out = v.strip()
        if not out:
            raise ValueError("token 不可為空")
        return out


def _surface_to_rows(surface: dict) -> dict:
    """`SurfacePoint` → 三元組陣列（落盤用）。一天的鏈有數千筆，欄位名
    重複數千次只是在燒儲存空間。"""
    return {side: [[p.dte, p.delta, p.iv] for p in points]
            for side, points in surface.items()}


def _rows_to_surface(rows: dict) -> dict:
    """落盤形式 → `SurfacePoint`。"""
    return {side: [ivhistory.SurfacePoint(dte=int(r[0]), delta=float(r[1]),
                                          iv=float(r[2]))
                   for r in (points or [])]
            for side, points in (rows or {}).items()}


def _leg_contract_identity(leg: dict, underlying: str) -> dict:
    """一條腿的 exact contract identity（HIVT-02／#153，spec #151 §1）。

    **重用既有欄位，不另組 formatter**：每條腿早就帶著 vendor 發的真實
    OCC symbol（`store._leg()` 的 `contract_symbol`），這就是這張合約的
    身分本身——不同 strike／expiry／call-put 天然是不同 symbol，不需要
    另外拼一個複合鍵或反過來從 symbol 解析回四個欄位。`underlying` 不在
    leg dict 上（那是整個候選的標的，不是腿的屬性），由呼叫端傳入
    （`Scenario.symbol`）。
    """
    return {"underlying": underlying, "expiration": leg["expiry"],
           "strike": leg["strike"], "option_type": leg["option_type"],
           "contract_symbol": leg["contract_symbol"]}


def _iv_payload(candidate_key: str, points: list[dict], status: str,
                note: str | None) -> dict:
    """Historical IV 的回應形狀（#133，HIVT-04／#155 裁切後）。

    `status`（ok／quota／vendor）只描述**這次 backfill 嘗試**的結果，
    不用來決定要不要給 percentile——需求方 2026-08-12 二次修正裁示：
    coverage／樣本數不得當作隱藏 percentile 的門檻，「今天補不補得動」
    跟「資料能不能看」是兩件事。

    **HIVT-04（#155）欄位裁切**：舊回應信封裡的 `buy_iv`／`sell_iv`／
    `atm_iv`（`points` 逐日子欄位與 `metrics` 對應項）已被新的逐腿
    exact-contract 卡片（`legs`，HIVT-02／03）取代，這裡不再往外送。
    `normalized_skew` 本身——連同它自己的走勢圖——是 spec #151 §0／§7
    明文保留、繼續獨立運作的既有功能，**不受這次裁切影響**：內部計算
    （`ivhistory.field_metrics()`／`reanchor_spread()`）完全沒動，只是
    信封裡的 `points` 改叫 `normalized_skew_points` 並且只留
    `date`／`normalized_skew` 兩個子欄位——舊的 `points` 這個名字連同它
    夾帶的 buy_iv／sell_iv／atm_iv 子欄位，跟著上面三個 `metrics` 欄位
    一起真正消失，不是換個名字繼續夾帶被取代的資料。這是本票對「移除
    points／metrics.buy_iv／metrics.sell_iv／metrics.atm_iv」與「
    Normalized Skew 卡片不受影響」兩條要求的解讀：字面上點名的
    `points` 這個信封鍵確實消失了，但 Normalized Skew 需要的走勢圖
    資料沒有跟著陪葬。
    """
    metrics = ivhistory.field_metrics(points, today=ny_today())
    return {
        "candidate_key": candidate_key,
        "status": status,
        "normalized_skew_points": [
            {"date": p["date"], "normalized_skew": p["normalized_skew"]}
            for p in points],
        "metrics": {"normalized_skew": metrics["normalized_skew"]},
        "observations": len(points),
        "note": note,
    }


# ---------- Historical IV 診斷接線（DG-03／#146） ----------
#
# 這一段只認識「怎麼把 Historical IV 這條路徑的事件送進 emit()」，不
# 認識 HTTP 或 storage 細節——`iv_history()` 端點負責組出真正寫庫的
# `emit`，這裡的函式都只吃一個 `emit` callable。

class _CollectingDiagnostics:
    """DG-03 的 per-request 緩衝：`emit()` 呼叫這個而不是直接呼叫真正
    的 storage，讓 structured log 照樣每筆都發，但 storage 寫入延後到
    這次 request 結束時才依 severity 取捨、限量落盤（見
    `_select_for_persistence`）。"""

    def __init__(self) -> None:
        self.events: list[diagnostics.DiagnosticEvent] = []

    def append_diagnostic(self, event: diagnostics.DiagnosticEvent) -> None:
        self.events.append(event)


# 一次 backfill 最多 25 天 × 數個到期日，每次 vendor 呼叫又拆成
# vendor_fetch／payload_parse 兩筆——不設限的話，一次 request 就能把
# 全域 200 筆的 retention 上限吃光，把先前的證據全部擠掉。
#
# HIVT-03（#154）之後 `metrics` stage 一次 request 最多可以有：舊
# (tenor,delta) 家族 4 筆（單腳 2 筆）＋新 exact-contract 家族每腿 5 筆
# 統計量（單腳 5 筆／兩腿 10 筆）＝最多 14 筆，全部落在 `_ALWAYS_KEPT_
# STAGES` 的無條件保留名額裡。原本 20 的上限在這個量級下會把
# `vendor_fetch`／`reanchor` 這類高診斷價值的逐次事件整批擠出去——調高
# 到 40，讓兩個家族的彙總結論都保留的同時，仍有餘裕留給其他 stage。
#
# HIVR-03（#162）：這個常數本身**不再調高**——legacy 家族的事件量結構上
# 會隨快照數持續成長，調高上限只是把同一個問題往後延。改成 exact-
# contract／legacy 重錨定各自的 subsystem 各自獨立享有一份完整的
# `cap` 名額（見 `_select_for_persistence`），大量 legacy 事件擠掉的
# 只會是同一個 subsystem 裡優先序較低的其他 legacy 事件，不會波及
# exact-contract 的名額。
_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST = 40


# 這幾個 stage 各自是「這次 request 的彙總結論」——`backfill` 每次至多
# 一筆，`metrics` 每個欄位一筆（舊家族單腳 2 筆／兩腿 4 筆；HIVT-03 起
# 新家族每腿再加 5 筆統計量事件），`reconstruction`／`vendor_benchmark`
# 各自每腿一筆（HIVR-07／#166：「這張圖為什麼這麼稀疏」的帳本；
# HIVR-09／#168：vendor IV 合理性比較）。這些都不跟高流量的逐日／逐次
# 事件（`vendor_fetch`／`payload_parse`／`database_write`／`reanchor`，
# 一次 request 可能各自數十筆）搶名額——施工中發現：若混在同一個優先池
# 裡用 `list[:cap]` 前截斷，事件量一大時彙總結論反而會被排在後面而擠
# 出去，跟「使用者最想先看結論」的初衷相反。`staleness` 刻意不在這裡：
# 它本身量體就很低（每腿至多一筆，只在真的抓到新資料時才發），不需要
# 額外保留名額也不太可能被擠掉。
_ALWAYS_KEPT_STAGES = ("backfill", "metrics", "reconstruction",
                      "vendor_benchmark")


def _select_for_persistence(
        events: list[diagnostics.DiagnosticEvent],
        *, cap: int = _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST,
) -> list[diagnostics.DiagnosticEvent]:
    """哪些 events 真的寫進 storage（#146／#147／#162）。log 不受這條
    限制——`emit()` 呼叫當下就已經全部印出去了，這裡只決定「留誰在
    capped 的 storage 裡」，回傳順序與輸入順序一致。

    HIVR-03（#162）：先依 `event.subsystem` 分組，**每個 subsystem 各自**
    套用 `_select_family_for_persistence()` 的三層優先序、各自享有一份
    完整的 `cap` 名額——exact-contract 與 legacy 重錨定互不相搶，大量
    legacy 事件不會把 exact-contract 的名額擠掉，反之亦然。單一
    subsystem 的情境（目前這裡只有這兩個 subsystem，見
    `diagnostics.SUBSYSTEMS`）分組前後行為完全一致。
    """
    by_subsystem: dict[str, list[diagnostics.DiagnosticEvent]] = {}
    for e in events:
        by_subsystem.setdefault(e.subsystem, []).append(e)
    kept_ids = {
        id(e)
        for family_events in by_subsystem.values()
        for e in _select_family_for_persistence(family_events, cap=cap)
    }
    return [e for e in events if id(e) in kept_ids]


def _select_family_for_persistence(
        events: list[diagnostics.DiagnosticEvent], *, cap: int,
) -> list[diagnostics.DiagnosticEvent]:
    """單一 subsystem 內部的三層優先序（`_select_for_persistence` 對
    每個 subsystem 各自呼叫一次）：

    1. `_ALWAYS_KEPT_STAGES`——保留名額最優先，跟它們自己的 severity
       無關（見上方常數的理由）。
    2. 其餘事件裡的 error／warning——依原始順序，額滿為止。
    3. 其餘事件裡的 info——依原始順序，用剩下的名額補滿。
    """
    if len(events) <= cap:
        return events
    reserved = [e for e in events if e.stage in _ALWAYS_KEPT_STAGES][:cap]
    others = [e for e in events if e.stage not in _ALWAYS_KEPT_STAGES]
    budget = cap - len(reserved)

    important = [e for e in others if e.severity in ("error", "warning")]
    info = [e for e in others if e.severity not in ("error", "warning")]
    kept_others_ids = {id(e) for e in important[:budget]}
    remaining = budget - len(kept_others_ids)
    if remaining > 0:
        kept_others_ids |= {id(e) for e in info[:remaining]}

    keep_ids = {id(e) for e in reserved} | kept_others_ids
    return [e for e in events if id(e) in keep_ids]


def _select_for_storage(
        events: list[diagnostics.DiagnosticEvent],
) -> list[diagnostics.DiagnosticEvent]:
    """PERF-02（#178）：`_select_for_persistence()` 選出「這次回應要
    顯示哪些 events」之後，這裡再決定「其中哪些真的值得寫進資料庫」——
    只有 `warning`／`error`，`info` 事件不落盤。這是**額外一層**、獨立
    於既有三層優先序（`_select_family_for_persistence`）之外的過濾，
    只影響落盤，不影響回應內容（呼叫端仍然用未經這層過濾的 `kept` 組
    回應）。回傳順序與輸入順序一致。"""
    return [e for e in events if e.severity in ("warning", "error")]


def _rate_limit_context(telemetry: dict) -> dict:
    return {k: v for k, v in telemetry.items()
           if k.startswith("X-Api-Ratelimit-")}


def _identity_context(identity: dict) -> dict:
    """`ContractIdentity` 的四個公開欄位（underlying／expiration／
    strike／option_type）——spec #151 §5／issue #153 明文列出這四項要
    additive 進白名單，且每一站 diagnostic event 都要帶得出**可讀的**
    exact contract identity，不能只留 `contract_symbol`（OCC symbol
    本身雖然編碼了這四項，但要求使用者反解 OCC 格式才看得懂身分，違背
    診斷「不必讀程式碼就能看懂」的既有原則，DG-04 帳本的既有精神）。"""
    return {"underlying": identity["underlying"],
            "expiration": identity["expiration"],
            "strike": identity["strike"],
            "option_type": identity["option_type"]}


def _emit_contract_history_telemetry(emit, telemetry: dict, *, provider: str,
                                     identity: dict, requested_from: str,
                                     requested_to: str) -> None:
    """`marketdata.fetch_contract_history` 的 observer callback 落地處
    （HIVT-02／#153）——比照 `_emit_surface_telemetry` 拆成 `vendor_fetch`
    與 `payload_parse` 兩站，但這裡沒有「no_data 是正常結果」那個分支
    （#152 真實驗證：超界／週末窗口皆回 `s=ok`，這個端點不像整鏈查詢
    那樣有 no_data 狀態），`vendor_status != "ok"` 一律是 error。
    """
    vendor_status = telemetry.get("vendor_status")
    emit(stage="vendor_fetch",
        severity="info" if vendor_status == "ok" else "error",
        message=f"vendor 回應 s={vendor_status!r}",
        provider=provider, contract_symbol=identity["contract_symbol"],
        **_identity_context(identity),
        requested_from=requested_from, requested_to=requested_to,
        http_status=telemetry.get("http_status"),
        vendor_status=vendor_status,
        vendor_errmsg=telemetry.get("vendor_errmsg"),
        raw_rows=telemetry.get("raw_rows"),
        **_rate_limit_context(telemetry))
    emit(stage="payload_parse",
        severity="warning" if (telemetry.get("raw_rows") or 0) > 0
                 and (telemetry.get("parsed_rows") or 0) == 0 else "info",
        message="解析單合約歷史欄狀回應",
        provider=provider, contract_symbol=identity["contract_symbol"],
        **_identity_context(identity),
        raw_rows=telemetry.get("raw_rows"),
        parsed_rows=telemetry.get("parsed_rows"),
        null_iv_count=telemetry.get("null_iv_count"),
        dropped_missing_date=telemetry.get("dropped_missing_date"))


def _min_max(values) -> tuple | None:
    values = list(values)
    return (min(values), max(values)) if values else None


def _is_weekend(day: str) -> bool:
    """只濾週末、不維護一份美股假日表——跟 `ivhistory.trading_days_back()`
    既有的同一個判斷（`weekday() < 5`）與其記錄的取捨一致：假日表會過期，
    多打幾天假日的代價（一年裡少數幾筆本可省下的判斷）比維護一份可能
    過期的假日表可靠。少數市場假日因此仍會落進「交易日撲空」那個桶子、
    照常警示——這是本函式刻意接受的已知殘留噪音，不是遺漏。"""
    return date.fromisoformat(day).weekday() >= 5


def _emit_backfill_summary(emit, *, symbol: str, attempted_days: int,
                           saved_days: int, days_with_data: int,
                           days_no_data_expected: int,
                           days_no_data_unexpected: int,
                           aborted_on: str | None, abort_reason: str | None,
                           remaining_gap: int, outcome: str,
                           failed_expiration: str | None = None,
                           in_flight_after_failure_succeeded: int = 0,
                           in_flight_after_failure_failed: int = 0,
                           unstarted_due_to_failure: int = 0) -> None:
    """Backfill 摘要（HIVR-10／#169）：一次批次最多 25 天、每天可能查
    好幾個到期日，舊版逐日／逐到期日各發一筆 `vendor_fetch`／
    `payload_parse`（外加每天一筆 `database_write`），輕鬆破百筆。改成
    批次結束後只發**一筆**摘要，攜帶「有幾天有資料、有幾天沒資料、
    有幾天失敗」（AC 明文的三分類）。

    沒資料的天再分兩種：`days_no_data_expected`（週末／假日，正常現象，
    不該讓使用者對著一個關閉的市場皺眉）與 `days_no_data_unexpected`
    （交易日卻沒資料，值得留意）——`severity` 依這個區分：只有真正
    中止（`aborted_on`）或「交易日卻沒資料」時才是 warning，單純撞到
    週末不是。

    PERF-05（#181）新增四個欄位，皆只在真正中止（`aborted_on` 有值）
    時才有意義（沒中止時維持預設 0／`None`）：`failed_expiration`——
    哪一個到期日觸發了這次失敗；`in_flight_after_failure_succeeded`／
    `_failed`——觸發失敗那一批裡，在它之後才完成的其他呼叫各自成功／
    失敗幾個（bounded concurrency 下這批本來就可能不只一個呼叫在飛）；
    `unstarted_due_to_failure`——因為提早中止，整批原本規劃要抓的
    (日期, 到期日) 組合裡有幾組完全沒被送出去。
    """
    emit(stage="backfill",
        severity="warning" if aborted_on or days_no_data_unexpected > 0
                 else "info",
        message=(f"backfill 在 {aborted_on} 中止：{abort_reason}"
                if aborted_on else "backfill 批次完成"),
        symbol=symbol, attempted_days=attempted_days, saved_days=saved_days,
        days_with_data=days_with_data,
        days_no_data_expected=days_no_data_expected,
        days_no_data_unexpected=days_no_data_unexpected,
        days_failed=1 if aborted_on else 0,
        aborted_on=aborted_on, abort_reason=abort_reason,
        remaining_gap=remaining_gap, outcome=outcome,
        failed_expiration=failed_expiration,
        in_flight_after_failure_succeeded=in_flight_after_failure_succeeded,
        in_flight_after_failure_failed=in_flight_after_failure_failed,
        unstarted_due_to_failure=unstarted_due_to_failure)


def _reanchor_in_grid(reanchored: dict, coords: dict) -> bool:
    """這一天的座標是否至少有一個核心欄位真的查到值（DG-04／#147 既有
    判準原樣保留）：`iv_at()` 誠實回 `None` 且不外插（既有行為，這裡
    不動），這裡只是判斷「今天曲面涵蓋得到候選要查的座標」與否。單腳
    候選（沒有 `sell`）的 `sell_iv`／`normalized_skew` 結構上必為
    `None`，不該被算進「全部落在網格外」的判準，否則每個 Long Call
    候選都會永遠判定為 out-of-grid。
    """
    sell = coords.get("sell")
    core_fields = ("buy_iv", "atm_iv") if sell is None else (
        "buy_iv", "sell_iv", "atm_iv", "normalized_skew")
    return not all(reanchored.get(f) is None for f in core_fields)


def _emit_reanchor_summary(emit, *, coords: dict, in_grid: int,
                           out_of_grid: int) -> None:
    """重錨定摘要（HIVR-10／#169）：舊版逐日重錨定每個歷史快照各發一筆
    `reanchor` 事件——一個累積了一年快照的 Scenario，光是打開頁面就會
    因此炸出幾十筆事件，且沒有一筆描述的是**這次 request** 本身發生了
    什麼。改成一次 request 只發一筆摘要：`total` 個歷史日期裡有幾個落在
    網格內（`in_grid`，`_reanchor_in_grid()` 判準原樣沿用）、幾個落在
    網格外（`out_of_grid`）。查詢座標（`buy_delta`／`sell_delta`／
    `tenor_days`）取自 `coords`——這是這次 request 要查的目標，同一個
    candidate 的每個歷史日期共用同一組，不隨日期改變，因此只在摘要裡
    出現一次。
    """
    buy = coords.get("buy")
    sell = coords.get("sell")
    total = in_grid + out_of_grid
    emit(stage="reanchor",
        severity="warning" if out_of_grid > 0 else "info",
        message=f"{total} 個歷史日期：{in_grid} 個落在網格內／"
                f"{out_of_grid} 個落在網格外",
        total_dates=total, in_grid_dates=in_grid, out_of_grid_dates=out_of_grid,
        tenor_days=buy.tenor_days if buy is not None else None,
        buy_delta=buy.delta if buy is not None else None,
        sell_delta=sell.delta if sell is not None else None)


def _emit_metrics(emit, points: list[dict], coords: dict) -> None:
    """`field_metrics()` 之後（DG-04／#147）：每個欄位各自一筆事件——
    比起一筆合併事件，逐欄位才看得出來是哪一項指標沒有觀測可用。單腳
    候選結構上沒有 `sell_iv`／`normalized_skew`（見 `_reanchor_in_grid`
    同一條理由），這兩項本來就必然 count=0，不進來湊「這個候選是不是
    沒資料」的判斷，否則每個 Long Call 永遠亮 warning。
    """
    metrics = ivhistory.field_metrics(points, today=ny_today())
    applicable = (("buy_iv", "atm_iv") if coords.get("sell") is None
                 else tuple(metrics.keys()))
    for field_name in applicable:
        m = metrics[field_name]
        count = m["count"]
        emit(stage="metrics",
            severity="warning" if count == 0 else "info",
            message=f"{field_name} 沒有有效觀測" if count == 0
                    else f"{field_name} 指標計算完成",
            field=field_name, count=count,
            percentile_available=m["percentile"] is not None,
            trend_base_count=m["trend_base_count"])


def _emit_staleness(emit, *, identity: dict, observation: dict,
                    request_time: str, today: date) -> None:
    """一次歷史抓取回應有多陳舊（HIVR-07／#166）：vendor 文件明載
    professional status 未定的帳號會被靜默降級成至少一天前的資料且
    不報錯，且選擇權要到**次一交易日 9:30:01 ET** 才從 Delayed 轉
    Historical——`s="ok"` 因此不代表新鮮，只有 `updated` 這個時戳才算數
    （見 `option_chaser/data/marketdata.py` 頂端 HTTP 203 註解更正的
    同一條原則）。取這次新抓回來的觀測裡**最新**的一筆代表這次回應的
    新鮮度；`vendor_dte`／`computed_dte` 並列讓兩者的落差不必用猜的。

    `staleness_days <= 1`（次一交易日 rollover 屬既有已知、非異常行為）
    定 info，超過才升級 warning——不是任何陳舊都要驚動使用者，只有
    「比正常 rollover 還舊」才是。
    """
    obs_date = date.fromisoformat(observation["date"])
    exp_date = date.fromisoformat(identity["expiration"])
    staleness_days = (today - obs_date).days
    computed_dte = days_between(obs_date, exp_date)
    emit(stage="staleness",
        severity="info" if staleness_days <= 1 else "warning",
        message=(f"最新觀測 {staleness_days} 天前" if staleness_days > 1
                else "最新觀測新鮮"),
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        date=obs_date.isoformat(), request_time=request_time,
        observation_timestamp=observation.get("updated"),
        staleness_days=staleness_days, vendor_dte=observation.get("dte"),
        computed_dte=computed_dte)


def _emit_reconstruction_ledger(emit, *, identity: dict, fetched: int,
                                series: list[tuple[str, float | None]],
                                failure_counts: dict[str, int]) -> None:
    """Reconstruction 帳本（HIVR-07／#166）：抓到幾筆觀測 → 成功重建
    幾筆 → 逐原因失敗計數 → 最終可用筆數，一筆事件回答「這張圖為什麼
    這麼稀疏」。四個失敗原因全部給（含 0），跟 `ivreconstruct.
    FAILURE_REASONS` 對齊——不是只列有發生的那幾個，讀者才看得出「不是
    敗在這一站」也是有意義的資訊。
    """
    reconstructed = sum(1 for _, iv in series if iv is not None)
    emit(stage="reconstruction",
        severity="info" if reconstructed > 0 else "warning",
        message="重建完成" if reconstructed > 0 else "整段序列沒有任何一筆重建成功",
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        fetched=fetched, reconstructed=reconstructed, usable=reconstructed,
        **{reason: failure_counts.get(reason, 0)
           for reason in ivreconstruct.FAILURE_REASONS})


def _emit_vendor_benchmark(emit, *, identity: dict, quotes: list[dict],
                           series: list[tuple[str, float | None]]) -> None:
    """Vendor IV benchmark 合理性比較（HIVR-09／#168）：canonical series
    （`series`，只由我們自己反解出來，從不讀 `vendor_iv`）跟 vendor 自己
    回報的 `iv` 差多少——只在通過 `ivreconstruct.vendor_iv_is_
    benchmarkable()` 的觀測上比較，門檻外的一律計入 `vendor_iv_excluded_
    degenerate`（可見、不是靜默丟棄），也不進 `mean_abs_diff`。門檻內
    值不受影響：canonical series 本身完全不因這個 gate 而改變，這個 gate
    只決定「這一筆算不算進比較」。
    """
    reconstructed_by_date = dict(series)
    present = 0
    excluded_degenerate = 0
    compared = 0
    total_abs_diff = 0.0
    for q in quotes:
        vendor_iv = q.get("vendor_iv")
        if vendor_iv is None:
            continue
        present += 1
        if not ivreconstruct.vendor_iv_is_benchmarkable(vendor_iv):
            excluded_degenerate += 1
            continue
        reconstructed = reconstructed_by_date.get(q["date"])
        if reconstructed is None:
            continue
        compared += 1
        total_abs_diff += abs(reconstructed - vendor_iv)
    mean_abs_diff = (total_abs_diff / compared) if compared else None
    emit(stage="vendor_benchmark", severity="info",
        message=(f"vendor IV 合理性比較：{present} 筆有值，"
                f"{excluded_degenerate} 筆被 gate 排除，{compared} 筆可比較"),
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        vendor_iv_present=present,
        vendor_iv_excluded_degenerate=excluded_degenerate,
        vendor_iv_compared=compared, mean_abs_diff=mean_abs_diff)


def _timing_json(sc: Scenario, today: date) -> dict:
    """卡片的「距到期天數」（V3／#51）與「是否已過期」（#68）。

    三件事都是領域規則、都不該讓瀏覽器自己猜：錨點＝該月第三個星期五
    （`timeframe.calendar_anchor`），「今天」＝紐約日曆（`ny_today`），
    「已過期」＝目標月最後一天已過完（`timeframe.month_is_over`）。
    已過期就是負數，夾成 0 會讓過期劇本看起來還有救。

    `expired` 與 `days_to_anchor < 0` 是**不同**的判準：後者以日曆錨點
    （第三個星期五）為準，會在月份真正過完之前就先轉負；前者才是
    `ensure_month_open` 與 `refresh_scenario` 用來擋下的那條規則，
    三處必須用同一個判準，否則清單上的「已過期，不再刷新」會跟批次
    刷新實際跳過的對象兜不起來。

    `today` 由呼叫端傳入、整個回應只取一次——沿用專案既有原則
    （`workspace.card_of(observed=...)`、`ensure_month_open(month, today)`、
    儲存層零 wall-clock）：可測，而且跨午夜的請求不會在同一份清單裡
    出現兩個「今天」。

    刻意不放進 `_scenario_json`：那個結構會原樣寫進 `SCENARIO_CREATED`
    事件，而事件是不可變的事實，不能塞「距今幾天」「是否已過期」這種
    隨時間改變的值。
    """
    month = TargetMonth.from_key(sc.target_month)
    anchor = calendar_anchor(month)
    return {"target_anchor": anchor.isoformat(),
            "days_to_anchor": (anchor - today).days,
            "expired": month_is_over(month, today)}


def _scenario_json(sc: Scenario) -> dict:
    return {"id": sc.id, "symbol": sc.symbol, "direction": sc.direction,
            "target_price": sc.target_price, "target_month": sc.target_month,
            "notes": sc.notes, "strategies": list(sc.strategies),
            "created_at": sc.created_at, "archived_at": sc.archived_at,
            "best_price": sc.best_price, "worst_price": sc.worst_price}


def _row_json(sc: Scenario, today: date, *, analyzed_at: str | None,
              best_return: float | None,
              representative_candidate: dict | None,
              spot: float | None = None) -> dict:
    """劇本在清單上的那一列。建立、列出、刷新三處共用同一個組裝函式——
    形狀只要差一個欄位，客戶端就得為同一個東西維護兩種型別。

    `representative_candidate`（MVP-v2／#77、#78）：代表候選的完整身分
    （策略／各腿履約價與權別／實際到期日），與 `best_return` 同一次走訪
    （`store.representative_candidate`），數值上不可能對不上。

    `spot`（QA 修正）：那次分析當下的標的現價，讓清單卡片有比較基準
    ——目標價／最高／最低（後兩者來自 `_scenario_json`）少了現價就只是
    三個孤立數字。尚未分析過時為 `None`。"""
    return {**_scenario_json(sc), **_timing_json(sc, today),
            "latest_analyzed_at": analyzed_at, "best_return": best_return,
            "representative_candidate": representative_candidate,
            "spot": spot}


def _summary_of(latest: ResultRecord | ResultSummary | None) -> dict:
    """從一筆「最新結果」（`ResultRecord` 或 `ResultSummary`，兩者皆有
    `analyzed_at`／`best_return`／`representative_candidate`）取出卡片要的
    欄位；沒有結果（`None`，劇本從未成功分析過）時皆為 `None`——卡片據此
    顯示「—」與「尚未分析」，不是 0 或一組假的候選。列出、詳細頁、刷新
    （含過期短路）共用同一個形狀，不必各自重寫一次 `if x else None`。"""
    return {"analyzed_at": latest.analyzed_at if latest else None,
            "best_return": latest.best_return if latest else None,
            "representative_candidate":
                latest.representative_candidate if latest else None,
            "spot": latest.spot if latest else None}


def _fail(stage: str, status: int, message: str) -> HTTPException:
    """失敗分層（V4／#52）。

    錯誤主體帶 `stage`，而不是只給一句話：「抓不到報價」與「分析失敗」
    使用者能做的處置不同（前者重試有意義、後者沒有），畫面要能分開講。
    `message` 仍是給人看的完整句子——舊的字串型 detail 客戶端照樣可讀。
    """
    return HTTPException(status_code=status,
                         detail={"stage": stage, "message": message})


def create_app(*, fetch: FetchChain = service.fetch_chain,
               storage: Storage | None = None,
               rate_loader: RateCurveLoader = service.default_rate_curve_loader,
               dividend_loader: DividendLoader = service.default_dividend_loader,
               verify_provider: VerifyProvider = providers.default_verify,
               custom_fetch: CustomFetch = providers.default_fetch_chain,
               historical_surface: HistoricalSurface =
                   providers.default_historical_surface,
               contract_history: ContractHistoryFetch =
                   providers.default_contract_history,
               rate_curve_rows: RateCurveRowsFetch =
                   treasury_data.fetch_curve_range,
               chain_cache_ttl: timedelta = chain_cache.CHAIN_CACHE_TTL,
               ) -> FastAPI:
    """`fetch`／`storage`／`rate_loader`／`dividend_loader` 皆可注入：
    測試傳入固定快照、記憶體假體與假來源，因此不打真網路、不碰真資料庫，
    決定性。

    `rate_curve_rows`（HIVR-06／#165）：Historical IV Trend reconstruction
    專用，回傳一段區間**全部**的曲線列（不是只回最新一列的
    `rate_loader`）——`ratecurve.curve_asof()` 用它逐一觀測日查表，
    每筆觀測的利率因此對齊自己的日期，不是套用「今天」的曲線。預設接
    HIVR-01（#160）新增的 `treasury.fetch_curve_range`，是這個參數本身
    收到的**未快取**來源——真正對外生效的是 `_cached_rate_curve_rows()`
    包出來、疊了 PERF-03（#179）年份為鍵持久快取的版本，見下方；失敗
    只讓那幾天的觀測記成 `no_rate`、不擋其餘計算。（HIVR-06 當時的決定
    「不疊持久快取、每次即時抓取」已由 PERF-03 的效能實測結果取代——
    同一 symbol 第二次以後的 iv-history 請求不必再對外打 Treasury 的
    即時 HTTP 請求。）

    `rate_loader`（#67）是資料源本身的介面——目前預設接的
    `service.default_rate_curve_loader`（Treasury）是 #73／#74 選型與
    production 實測後的落地結果（研究見
    `docs/research/interest-rate-source-selection.md`，探測結果見該文
    §6.4）；備援層（FRED／FMP，皆需金鑰）待需求方申請金鑰後再接，
    介面本身已是可替換的。真正對外生效的是 `_rate_curve_loader()`
    包出來、疊了持久快取的版本，見下方。

    `dividend_loader`（#123）同一套設計：預設接
    `service.default_dividend_loader`（Yahoo→FMP→Nasdaq），是 #120
    production 實測後的落地結果（`docs/research/dividend-yield-source-
    selection.md` §12.4）；真正對外生效的是 `_dividend_loader()` 包出來、
    疊了持久快取（per-symbol，90 天陳舊窗）的版本，見下方。
    """
    app = FastAPI(title="Option Chaser API", version=__version__)

    # correlation ID（DG-02／#145）：每個 request 一個，整段處理過程中
    # `diagnostics.emit()` 都讀得到同一個，不必逐層往下傳參數。回應一律
    # 帶 `X-Correlation-Id`，錯誤回應也有——FastAPI 把 `HTTPException`
    # 轉成回應的動作發生在 `call_next()` 之內，這裡看到的已經是那個
    # 回應物件，不是例外本身。
    @app.middleware("http")
    async def _correlation_id_middleware(request: Request, call_next):
        with diagnostics.correlation_scope() as cid:
            response = await call_next(request)
            response.headers["X-Correlation-Id"] = cid
        return response

    # 延遲建構：Postgres adapter 在建構時就連線＋建表，若放在 import 期，
    # 資料庫暫時連不上會讓整個 lambda 起不來——連本來要負責「讓儲存後端
    # 看得見」的 /api/health 都會 500，正好毀掉它的用途。改成第一次真正
    # 用到時才建，並快取起來。
    cached: dict[str, Storage] = {}

    def _db() -> Storage:
        if storage is not None:
            return storage
        if "db" not in cached:
            cached["db"] = storage_from_env()
        return cached["db"]

    # PERF-01（#177）：warm 的 storage-heavy 路徑（例如 `/iv-history`）
    # 一次 request 觸發十幾次 `Storage` method 呼叫，Postgres adapter
    # 原本每次呼叫都各自重新開一條全新連線——這裡在 request 最外層借出
    # 一條共用連線，離開時歸還。`memory.py` 沒有 `request_scope()` 這個
    # 方法（`Storage` Protocol 也沒有這個方法，兩者皆零改動），用
    # `getattr` 拿不到就直接跳過，行為完全比照今天。`_db()` 本身可能
    # 丟出例外（例如環境變數沒設好）——這裡也要容忍，不然會連
    # `/api/health` 這種本來就設計成容忍連不上的端點都被這層擋在前面。
    @app.middleware("http")
    async def _storage_connection_scope_middleware(request: Request, call_next):
        try:
            scope = getattr(_db(), "request_scope", None)
        except Exception:  # noqa: BLE001 — 拿不到 storage 就整個跳過，交給下游端點自己的錯誤處理
            scope = None
        if scope is None:
            return await call_next(request)
        with scope():
            return await call_next(request)

    # 同一個道理：包快取的動作本身不必每次分析重做一次，惰性建一次、
    # 快取物件重用即可（`cached_loader()` 回傳的閉包內部沒有狀態，
    # 重不重建都不影響行為，這裡只是省一次函式呼叫）。
    cached_rate: dict[str, RateCurveLoader] = {}

    def _rate_curve_loader() -> RateCurveLoader:
        if "loader" not in cached_rate:
            cached_rate["loader"] = cached_loader(_db(), rate_loader)
        return cached_rate["loader"]

    cached_dividend: dict[str, DividendLoader] = {}

    def _dividend_loader() -> DividendLoader:
        if "loader" not in cached_dividend:
            cached_dividend["loader"] = cached_dividend_loader(_db(), dividend_loader)
        return cached_dividend["loader"]

    # PERF-03（#179）：同一個惰性建一次、重用閉包的模式，鍵是年份而非
    # 固定一筆／symbol，見 `treasury_cache.cached_rate_curve_rows`。
    cached_treasury_rows: dict[str, Callable] = {}

    def _cached_rate_curve_rows() -> Callable[[date, date, date], tuple]:
        if "fn" not in cached_treasury_rows:
            cached_treasury_rows["fn"] = cached_rate_curve_rows(_db(), rate_curve_rows)
        return cached_treasury_rows["fn"]

    def _fetch_chain(symbol: str) -> ChainSnapshot:
        """依設定挑抓鏈路徑（Settings／#125）。

        Market Data 選「自訂」且該 Provider 有 credential 時先走自訂；
        **失敗就退回預設來源**（`fetch`，即既有的 Cboe → yfinance 降級
        鏈，本身不動），而且把失敗如實記成一次驗證失敗——設定頁的三態
        因此會自己變成「驗證失敗」並說出原因，不需要另一套「上次
        fallback 過」的機制，也不會出現靜默退回。

        自訂成功時同樣記一次成功：那是比任何測試連線都真實的證據。
        """
        db = _db()
        stored = db.get_settings()
        md = stored.market_data if stored else None
        if md is None or md.mode != providers.MODE_CUSTOM or not md.provider:
            return fetch(symbol)

        cred = db.get_credential(md.provider)
        if cred is None:
            # 選了自訂卻沒有 token：不是錯誤，是還沒設定完——照常分析，
            # 設定頁那邊會顯示「尚未設定 token，改用預設來源」。
            return fetch(symbol)

        try:
            snap = custom_fetch(md.provider, symbol, cred.token)
        except FetchError as e:
            db.save_verification(ProviderVerification(
                provider=md.provider, ok=False, reason=str(e),
                checked_at=now_utc_iso()))
            return fetch(symbol)
        db.save_verification(ProviderVerification(
            provider=md.provider, ok=True, reason=None,
            checked_at=now_utc_iso()))
        return snap

    # PERF-06（#182）：同一個道理，惰性建一次、重用閉包——鍵是 symbol，
    # 短效期（`chain_cache.CHAIN_CACHE_TTL`），不是市場日／年份那套
    # 三態設計，見 `chain_cache.cached_fetch_chain` 說明。包住整個
    # `_fetch_chain()`（不管內部走自訂還是預設來源），快取命中時連
    # `_fetch_chain()` 自己的 settings／credential 查詢都省下來。
    cached_chain: dict[str, Callable] = {}

    def _cached_fetch_chain() -> Callable[[str], ChainSnapshot]:
        if "fn" not in cached_chain:
            cached_chain["fn"] = cached_fetch_chain(_db(), _fetch_chain,
                                                    ttl=chain_cache_ttl)
        return cached_chain["fn"]

    def _require(scenario_id: str) -> Scenario:
        sc = _db().get_scenario(scenario_id)
        if sc is None:
            raise HTTPException(status_code=404, detail=f"劇本不存在：{scenario_id}")
        return sc

    def _analyze(*, scenario_id: str, symbol: str, target_price: float,
                 target_month: str, strategies: tuple[str, ...],
                 best_price: float | None = None,
                 worst_price: float | None = None) -> tuple[dict, dict]:
        """跑一次分析，回傳 (view dict, 原始快照 dict)。

        只吃分析真正需要的欄位——不要求一個完整的 `Scenario`，一次性
        分析端點才不必為了呼叫它而捏造一個沒有建立時間的假劇本。
        原始快照一併回傳：view dict 裡沒有逐筆合約報價，而 V8 的
        「原始資料」要的正是那個。"""
        # base_params.strategy 只是引擎逐策略覆寫前的起點（`_analyze` 會
        # 對 `strategies` 每一項各自替換），取第一項即可——與既有
        # `workspace._request_for` 同樣的做法。
        params = AnalysisParams(target_price=target_price,
                                target_month=target_month,
                                strategy=strategies[0],
                                best_price=best_price, worst_price=worst_price)
        req = service.AnalysisRequest(symbol=symbol, base_params=params,
                                      strategies=tuple(strategies))
        # 兩段各自 try：抓鏈與分析是兩個不同的失敗環節（V4／#52），
        # 包在同一個 try 裡就只能事後靠例外型別猜是哪一段出的事。
        try:
            snap = _cached_fetch_chain()(symbol)
        except FetchError as e:
            # 上游報價來源不可用（Cboe 與 yfinance 皆失敗）＝下游依賴問題。
            # 只認 FetchError：把這裡寫成 `except Exception` 的話，我們自己
            # 程式裡的 bug 會被貼上「抓不到報價、可稍後重試」的標籤，正好是
            # 這張票要消滅的那種誤導。其他例外照樣往上走成 500——「不知道
            # 是哪一段」時說不知道，好過說一個錯的分層。
            raise _fail("fetch", 502, f"抓不到 {symbol} 的報價：{e}") from e
        try:
            result = service.run_with_snapshot(
                req, snap, rate_curve_loader=_rate_curve_loader(),
                dividend_loader=_dividend_loader())
        except ParamError as e:
            raise _fail("params", 400, str(e)) from e
        except Exception as e:  # noqa: BLE001 — 引擎任何失敗都要說是哪一段，不留白畫面
            raise _fail("analyze", 500, f"分析失敗：{e}") from e
        return (store.serialize_result(result, scenario_id, capital=None),
                dataclasses.asdict(snap))

    # ---------- 健康檢查 ----------

    @app.get("/api/health")
    def health(request: Request) -> dict:
        # `storage` 如實回報實際用的後端：部署上若因環境變數沒設而落到
        # 記憶體假體，資料不會存活——這一行讓它在畫面上看得見，而不是
        # 靜默丟失（與快照的 `source` 欄位同樣的用意）。
        # `path` 回報 app 收到的路徑，供確認 Vercel rewrite 的行為。
        try:
            kind = _db().kind
        except Exception as e:  # noqa: BLE001 — 連不上也要能回答，這正是本端點的用途
            kind = f"unavailable: {e}"
        # 利率狀態（#67）：最近一次嘗試的結果——尚無任何分析跑過時為
        # `None`（不是「失敗」，是「還沒發生過」）；讀不到快取比照
        # `storage` 的做法，同樣不讓 /api/health 本身炸掉。
        #
        # #123 刻意不比照加一個 `dividend` 區塊：`rate_cache` 是單一
        # 全站狀態，這裡直接讀「那一筆」就是完整答案；`dividend_cache`
        # 是 per-symbol（研究文件 §11 裁示），沒有「那一筆」可讀——秀
        # 任一 symbol 的狀態既武斷又誤導（像是在講全站健康度，其實只是
        # 剛好被誰分析過的某個標的）。運維若要查特定標的的配息快取狀態，
        # 該症狀（q_by_symbol 一直是 None）已經會反映在該劇本自己的
        # 分析結果 `q_note` 欄位裡，不需要另開一條全站端點。
        rate: dict | None = None
        try:
            entry = _db().get_rate_cache()
            if entry is not None:
                rate = {"fetched_at": entry.fetched_at,
                       "ok": entry.curve is not None, "note": entry.note,
                       "last_success_at": entry.last_success_at}
        except Exception:  # noqa: BLE001 — 同上，本端點的用途就是連不上也要能回答
            pass
        return {"status": "ok", "engine_version": __version__,
                "storage": kind, "path": request.url.path, "rate": rate}

    # ---------- Application diagnostics（DG-02／#145） ----------

    @app.get("/api/diagnostics")
    def list_diagnostics(limit: int = 50) -> list[dict]:
        """近期 diagnostic events，最新在最上。`limit` 夾在
        `[1, diagnostics.RETENTION_LIMIT]`——查得到的最多就是留著的
        那些，沒有 pagination、沒有搜尋。"""
        clamped = max(1, min(limit, diagnostics.RETENTION_LIMIT))
        return [dataclasses.asdict(e)
               for e in _db().list_diagnostics(limit=clamped)]

    @app.delete("/api/diagnostics")
    def clear_diagnostics() -> dict:
        """清空，回傳清掉的筆數。"""
        return {"cleared": _db().clear_diagnostics()}

    # ---------- 一次性分析（V1 遺留，前端改走劇本端點後可移除） ----------

    @app.post("/api/analyze")
    def analyze_adhoc(req: AnalyzeRequest) -> dict:
        view, _snapshot = _analyze(
            scenario_id=_ADHOC_SCENARIO_ID, symbol=req.symbol,
            target_price=req.target_price, target_month=req.target_month,
            strategies=tuple(req.strategies))
        return view

    # ---------- 劇本 ----------

    @app.post("/api/scenarios", status_code=201)
    def create_scenario(req: CreateScenarioRequest) -> dict:
        try:
            # 月級驗證（既有規則）：目標月已過完就拒絕——生下來就過期的
            # 劇本不該存在；當月仍允許。
            ensure_month_open(TargetMonth.from_key(req.target_month), ny_today())
        except ParamError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        ts = now_utc_iso()
        sc = Scenario(id=uuid.uuid4().hex[:12], symbol=req.symbol.upper(),
                      direction=_MVP_DIRECTION, target_price=req.target_price,
                      target_month=req.target_month, notes=req.notes,
                      strategies=_MVP_STRATEGIES, created_at=ts,
                      best_price=req.best_price, worst_price=req.worst_price)
        try:
            _db().create_scenario(sc)
        except ScenarioExists as e:   # 48-bit 隨機 id，實務上碰不到；不留 500 的縫
            raise HTTPException(status_code=409, detail=str(e)) from e
        _db().append_event(ts=ts, scenario_id=sc.id,
                           event="SCENARIO_CREATED", payload=_scenario_json(sc))
        # 回傳與清單同一個形狀（含 timing、尚未分析故摘要欄位皆為 None），
        # 客戶端才不必為「剛建立的」與「列出來的」維護兩種型別。
        return _row_json(sc, ny_today(), analyzed_at=None, best_return=None,
                         representative_candidate=None, spot=None)

    @app.patch("/api/scenarios/{scenario_id}")
    def edit_scenario(scenario_id: str, req: EditScenarioRequest) -> dict:
        """編輯劇本的 thesis 欄位（#132）。

        **同一個 id**——不是刪除＋重建。重建會讓所有以 scenario_id 為鍵的
        東西變成孤兒，而使用者只是改了個目標價。標的與建立時間原樣帶回。

        thesis 真的變了就清掉舊結果：目標價餵進 baseline_return、目標月
        決定選哪些到期日，兩者一改，舊結果的每個數字都是對著另一個問題
        算出來的。留著它們就是拿舊結果冒充新的。沒變就什麼都不清——使用者
        可能只是打開表單又存了一次。
        """
        sc = _require(scenario_id)
        try:
            ensure_month_open(TargetMonth.from_key(req.target_month), ny_today())
        except ParamError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        updated = dataclasses.replace(
            sc, target_price=req.target_price, target_month=req.target_month,
            notes=req.notes, best_price=req.best_price,
            worst_price=req.worst_price)
        thesis_changed = (
            (sc.target_price, sc.target_month, sc.best_price, sc.worst_price)
            != (updated.target_price, updated.target_month,
                updated.best_price, updated.worst_price))

        _db().update_scenario(updated)
        if thesis_changed:
            _db().clear_results(scenario_id)
        ts = now_utc_iso()
        _db().append_event(ts=ts, scenario_id=scenario_id,
                           event="SCENARIO_EDITED",
                           payload=_scenario_json(updated))

        latest = None if thesis_changed else _db().latest_result(scenario_id)
        return _row_json(updated, ny_today(), **_summary_of(latest))

    @app.get("/api/scenarios")
    def list_scenarios(include_archived: bool = False) -> list[dict]:
        # 卡片要的兩個數字跟著清單一起回（V3／#51）：否則前端得為每張卡
        # 各打一次 detail，而 detail 會拖回整份 view（十萬字元等級）。
        # 沒跑過的劇本兩欄皆 None ＝ 卡片顯示「—」，不是 0。
        summaries = _db().latest_summaries()
        today = ny_today()          # 整份清單共用同一個「今天」
        rows = []
        for s in _db().list_scenarios(include_archived=include_archived):
            rows.append(_row_json(s, today, **_summary_of(summaries.get(s.id))))
        return rows

    @app.get("/api/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str) -> dict:
        sc = _require(scenario_id)
        latest = _db().latest_result(scenario_id)
        # `best_return` 也要在——detail 少一個欄位的話，客戶端就沒辦法把
        # 同一個型別套用在清單列與詳細回應上（V5 的詳細頁會踩到）。
        return {**_row_json(sc, ny_today(), **_summary_of(latest)),
                "latest_result": latest.view if latest else None}

    @app.post("/api/scenarios/{scenario_id}/archive")
    def archive_scenario(scenario_id: str) -> dict:
        _require(scenario_id)
        ts = now_utc_iso()
        # 重複封存回 False——對呼叫端而言結果相同（已經封存了），因此
        # 視為冪等成功，不當成錯誤。
        if _db().archive_scenario(scenario_id, ts=ts):
            _db().append_event(ts=ts, scenario_id=scenario_id,
                               event="SCENARIO_ARCHIVED", payload={})
        return {"archived": True}

    @app.post("/api/scenarios/{scenario_id}/restore")
    def restore_scenario(scenario_id: str) -> dict:
        """TR2（#89）：垃圾桶單筆還原——清空 `archived_at`，
        results／snapshots／events 不受影響（只是軟刪除的反向操作）。
        還原後 TR1（#88）的硬擋自然解除，不需要另外處理。批量還原不在
        這裡：前端沿用既有序列佇列模式，對選中的每個劇本各打一次這個
        端點（比照批次刷新／批次移入垃圾桶），不新增後端批次端點。

        重複呼叫（本來就不在垃圾桶）視為冪等成功，比照 `archive_
        scenario` 對重複封存的處理——不留一筆沒意義的事件。
        """
        _require(scenario_id)
        ts = now_utc_iso()
        if _db().restore_scenario(scenario_id, ts=ts):
            _db().append_event(ts=ts, scenario_id=scenario_id,
                               event="SCENARIO_RESTORED", payload={})
        return {"restored": True}

    @app.delete("/api/scenarios/{scenario_id}", status_code=204)
    def delete_scenario(scenario_id: str) -> Response:
        """TR3（#90）：永久刪除，cascade 清掉 results／snapshots／events
        （`Storage.delete_scenario` 的職責）。安全閘門：只允許刪除已
        封存的劇本，未封存的回 409——永久刪除必須先進垃圾桶，不能一步
        到位刪掉還在使用中的劇本。不留刪除事件——劇本本身連同它的
        events 一起沒了，繼續保留一筆「它被刪除了」的事件沒有意義。
        批量刪除不在這裡：前端沿用既有序列佇列模式，對選中的每個劇本
        各打一次這個端點，不新增後端批次端點。
        """
        sc = _require(scenario_id)
        # 純字串 detail（不是 `_fail()` 的 `{stage, message}` 分層形狀）：
        # 這不是刷新／分析的失敗分層概念（那組字彙專屬 `RefreshFailure`／
        # `failureLabel`），是這個端點自己的前置條件——沿用
        # `create_scenario` 對驗證錯誤同樣用純字串 `detail` 的既有寫法。
        if sc.archived_at is None:
            raise HTTPException(
                status_code=409,
                detail=f"劇本尚未移入垃圾桶，無法永久刪除：{scenario_id}")
        _db().delete_scenario(scenario_id)
        return Response(status_code=204)

    @app.post("/api/scenarios/{scenario_id}/refresh")
    def refresh_scenario(scenario_id: str) -> dict:
        """單劇本刷新（V4／#52）：抓鏈→分析→結果與原始快照入庫。

        回傳的是**卡片列**而非整份 view：客戶端要依序刷新 N 個劇本、
        每完成一個就更新那張卡，每次拖回十萬字元級的 view 在手機上是
        實打實的浪費。要看完整 view 走 detail 端點。

        本端點是所有刷新入口共用的**唯一**擋點（#68）：目標月已過完的
        劇本直接短路成一次無害的讀取（不抓鏈、不跑引擎、不入庫、不留
        事件），回傳目前既有的卡片列。這裡是唯一必須擋住的地方——批次
        流程本該在排隊前就先篩掉這類劇本以免浪費一趟網路往返，但擋點
        設在這裡才能保證「任何入口都擋得住」，含日後新增的、忘記先篩
        的呼叫端。
        """
        sc = _require(scenario_id)
        # TR1（#88）：垃圾桶劇本硬擋——跟過期擋點（下面）刻意不同，過期
        # 是「還是能看，只是不再花資源更新」的靜默短路（回既有卡片列，
        # 200）；垃圾桶是使用者主動丟掉的，任何背景動作都不該再發生，
        # 錯誤要明確到前端分辨得出「這是因為在垃圾桶」，不是靜靜地回一
        # 份「無害的舊資料」。擋在 `_require` 之後、任何抓鏈／分析動作
        # 之前——不抓鏈、不跑引擎、不入庫、不留事件。
        if sc.archived_at is not None:
            raise _fail("archived", 409, f"劇本已在垃圾桶，不再刷新：{scenario_id}")
        today = ny_today()
        if month_is_over(TargetMonth.from_key(sc.target_month), today):
            latest = _db().latest_result(scenario_id)
            return _row_json(sc, today, **_summary_of(latest))
        view, snapshot = _analyze(
            scenario_id=sc.id, symbol=sc.symbol, target_price=sc.target_price,
            target_month=sc.target_month, strategies=sc.strategies,
            best_price=sc.best_price, worst_price=sc.worst_price)
        analyzed_at = view["analyzed_at"]
        # 兩者同一次走訪（`store.representative_candidate`），`best_return`
        # 由它導出——結構上不可能對不上（MVP-v2／#77、#78）。
        representative_candidate = store.representative_candidate(view)
        best_return = (representative_candidate["baseline_return"]
                       if representative_candidate is not None else None)
        _db().save_result(ResultRecord(
            scenario_id=sc.id, analyzed_at=analyzed_at, view=view,
            best_return=best_return,
            representative_candidate=representative_candidate,
            spot=store.spot(view)))
        _db().save_snapshot(sc.id, analyzed_at, snapshot)
        _db().append_event(ts=now_utc_iso(), scenario_id=sc.id,
                           event="ANALYSIS_COMPLETED",
                           payload={"analyzed_at": analyzed_at,
                                    "snapshot_ref": view["snapshot_ref"]})
        return _row_json(sc, today, analyzed_at=analyzed_at,
                         best_return=best_return,
                         representative_candidate=representative_candidate,
                         spot=store.spot(view))

    @app.get("/api/scenarios/{scenario_id}/results")
    def list_results(scenario_id: str) -> list[dict]:
        """歷史索引：只回時間戳，不回整份 view（一份十萬字元等級）。
        需要單次完整結果時走 detail／後續票的專屬端點。"""
        _require(scenario_id)
        return [{"analyzed_at": r.analyzed_at}
                for r in _db().result_history(scenario_id)]

    @app.get("/api/scenarios/{scenario_id}/history")
    def get_spread_history(scenario_id: str, candidate_key: str) -> dict:
        """V9（#57，T11／#25 既有語意）：跨這個劇本全部歷史結果，依
        Spread 身份鍵（`candidate_key`）聚合成時間序列——唯讀，缺席快照
        如實呈現為斷點（`store.spread_cost_history()`），不插值。

        `result_history()` 回傳的 `ResultRecord.view` 已經是完整 view
        dict，不必額外重算——這條端點只是把既有引擎聚合邏輯接上 HTTP。
        """
        _require(scenario_id)
        views = [r.view for r in _db().result_history(scenario_id)]
        return {"entries": store.spread_cost_history(views, candidate_key)}

    def _load_raw_snapshot(scenario_id: str) -> ChainSnapshot:
        """V8（#56）：原始資料（當次快照）——`refresh_scenario` 早就在
        `save_snapshot` 把它跟結果一起存進去了（`main.py` 既有邏輯，
        `analyzed_at` 是兩者共用的鍵），這裡只是第一次把它讀出來。
        取「最新一次結果」的 `analyzed_at`，不接受呼叫端指定：詳細頁
        只看得到最新一份分析，原始資料照理跟著它走，不需要另開一個
        「選歷史哪一版」的介面。"""
        latest = _db().latest_result(scenario_id)
        if latest is None:
            raise HTTPException(status_code=404,
                                detail=f"劇本尚未分析，無原始資料：{scenario_id}")
        data = _db().get_snapshot(scenario_id, latest.analyzed_at)
        if data is None:
            raise HTTPException(status_code=404,
                                detail=f"找不到原始快照：{scenario_id}")
        return snapshot_from_dict(data)

    @app.get("/api/scenarios/{scenario_id}/raw-data")
    def get_raw_data(scenario_id: str) -> dict:
        """V8（#56）：原始資料表（畫面查看用）——逐筆合約報價，
        「免得你亂掰我卻查不到證據」（QA1-10／#37 原話）。"""
        _require(scenario_id)
        return store.raw_snapshot_json(_load_raw_snapshot(scenario_id))

    @app.get("/api/scenarios/{scenario_id}/raw-data.csv")
    def get_raw_data_csv(scenario_id: str) -> Response:
        """V8（#56）：同一份原始資料的 CSV 下載——內容產生走既有純函式
        `data.snapshot.snapshot_to_csv`（QA1-10／#37 已測試覆蓋內容
        正確性），本端點只負責接線與下載標頭。"""
        _require(scenario_id)
        snap = _load_raw_snapshot(scenario_id)
        csv_text = snapshot_to_csv(snap)
        filename = f"{snap.symbol}_{snap.fetched_at[:10]}_raw.csv"
        return Response(content=csv_text, media_type="text/csv",
                        headers={"Content-Disposition":
                                f'attachment; filename="{filename}"'})

    @app.get("/api/scenarios/{scenario_id}/events")
    def list_events(scenario_id: str) -> list[dict]:
        _require(scenario_id)
        return _db().list_events(scenario_id=scenario_id)

    # ---------- Historical IV：快取、漸進補齊、額度（#126／#130） ----------

    def _credential_map() -> dict[str, ProviderCredential | None]:
        """一次拿齊全部 Provider 的 credential（PERF-01／#177）——
        `_settings_view()`／`_known_secrets()`／iv-history 端點裡挑選中
        Provider 的 token 取得，原本三處各自對 storage 重新查一次同一批
        資料，這裡改成算一次、往下傳給需要的地方使用。兩個參數皆為
        `None` 時的既有呼叫端（Settings 端點等）不受影響——那些端點本來
        就只呼叫一次，沒有重複讀取的問題，不必跟著改。"""
        db = _db()
        return {p.id: db.get_credential(p.id) for p in providers.SUPPORTED_PROVIDERS}

    def _known_secrets(*, credentials: dict[str, ProviderCredential | None] | None = None
                       ) -> tuple[str, ...]:
        """目前現行的祕密值——provider token 與 `DATABASE_URL` 家族環境
        變數的值（DG-03／#146）。這是 redaction 白名單以外的最後一道
        防線：即使某個字串意外落在白名單欄位裡，只要逐字等於這裡的
        任何一個值，一樣會被換成 `[redacted]`。

        `credentials` 可選——傳入時直接使用（PERF-01／#177，呼叫端已經
        算過一次），不傳時照舊自己查一次，行為不變。"""
        creds = credentials if credentials is not None else _credential_map()
        tokens = tuple(cred.token for cred in creds.values() if cred is not None)
        return tokens + database_url_candidates()

    def _backfill_iv(symbol: str, provider: str, token: str,
                     target_expirations: list[str], *, emit
                     ) -> tuple[str, str | None]:
        """把這個 symbol 的歷史觀測往前補一批，回傳 (狀態, 說明)。

        四條規則直接寫在這裡，因為它們決定了會不會白白燒掉使用者的額度：

        1. **已有的日期一次都不重抓**——只補「排程要、快取沒有」的那幾天。
        2. **每個 symbol 每天只跑一批**。同一天多開幾個同 ticker 的
           Scenario 不該各自再燒一批；額度用完時也不必每次都再去撞一次
           才知道。
        3. **每批有上限**。第一次使用一個新 ticker 時不是一口氣抓滿，而是
           分幾天補齊（需求方的 progressive backfill）。
        4. **每天只鎖定 `target_expirations` 這幾個到期日**（#134）——
           不帶 `expiration` 篩選會撲空長天期候選（vendor 預設只回下一
           個月選），帶 `expiration=all` 又會扣光整條鏈的額度；呼叫端
           （`ivhistory.nearby_expirations()`）已經把範圍收斂成離目標
           tenor 最近的少數幾個真實到期日，這裡逐一打、合併成同一天的
           曲面再存一次——**曲面是聯集，不是覆蓋**：同一天原本沒有的
           到期日才會真的觸發 vendor 請求。

        補的順序由新到舊：近期的觀測對「現在的 IV 站在哪」最有用，額度
        中途用完時留下的也是比較有價值的那一段。

        `emit`（DG-03／#146）：**這四條決策規則本身逐字不動**——`emit`
        呼叫只是把已經在發生的事情說出來，不參與任何 if／break 的判斷。

        HIVR-10（#169）：每天每個到期日原本各發一筆 `vendor_fetch`／
        `payload_parse`（外加每天一筆 `database_write`），一次 25 天的
        批次輕鬆破百筆。這裡改成逐日累計、批次結束後只發**一筆**
        `backfill` 摘要——`_emit_surface_telemetry` 那組逐日事件整個
        不再呼叫，取而代之的是本函式自己的計數器。
        """
        db = _db()
        today = ny_today()
        run = db.get_iv_backfill_run(symbol)
        if run is not None and run.ran_on == today.isoformat():
            # 今天已經跑過——直接沿用當時的結論，不再碰 vendor。
            emit(stage="cache", severity="info", message="今天已跑過 backfill，沿用既有結論",
                symbol=symbol, already_ran_today=True, outcome=run.outcome)
            return run.outcome, run.note

        wanted = ivhistory.sampling_schedule(symbol, today)
        have = set(db.iv_observation_dates(symbol))
        missing = [d for d in wanted if d not in have]
        emit(stage="cache", severity="info", message="計算 backfill 缺口",
            symbol=symbol, wanted_days=len(wanted), have_days=len(have),
            missing_days=len(missing), already_ran_today=False)
        # 沒算出目標到期日時退回舊行為（vendor 預設的下一個月選），
        # 好過完全不抓——這種情況只有候選算不出 tenor 才會發生。
        expirations = target_expirations or [None]

        def _fetch_day_bounded(day: str):
            """PERF-05（#181）：一天份的到期日梯子改成有明確保守上限的
            併發呼叫，取代原本逐一序列呼叫——`_IV_BACKFILL_DAY_
            CONCURRENCY` 個一批，上一批全部真正跑完（不論成功失敗）
            才決定要不要送出下一批；批次裡只要有一個失敗，這一批**其餘
            已經送出、還在飛的**呼叫仍讓它們正常跑完（`ThreadPoolExecutor`
            的 `with` 區塊本來就會等全部 submit 的工作做完才離開，
            不強制 cancel），成功的一樣併入這天的 surface；失敗之後
            **不再送出下一批**。用 `as_completed()` 取得真實完成順序，
            才分得出「第一個失敗」跟「同一批裡在它之後才完成的其他
            呼叫」——不是照送出順序猜。

            回傳 `(merged, first_failure, after_ok, after_fail,
            dispatched)`：`first_failure` 是 `(reason, exc, exp) | None`；
            `after_ok`／`after_fail` 是**觸發失敗的那一批**裡，在它之後
            才完成的其他呼叫各自成功／失敗幾個；`dispatched` 是這天總共
            真正送出去幾個呼叫（供批次層級統計「因失敗未啟動幾組」用）。
            """
            merged: dict[str, list] = {"call": [], "put": []}
            first_failure = None
            after_ok = after_fail = dispatched = 0
            idx = 0
            while idx < len(expirations) and first_failure is None:
                batch = expirations[idx: idx + _IV_BACKFILL_DAY_CONCURRENCY]
                idx += len(batch)
                dispatched += len(batch)
                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                    futures = {pool.submit(historical_surface, provider,
                                          symbol, day, token, expiration=exp): exp
                              for exp in batch}
                    for future in as_completed(futures):
                        exp = futures[future]
                        try:
                            got = future.result()
                        except QuotaExhausted as e:
                            if first_failure is None:
                                first_failure = ("quota", e, exp)
                            else:
                                after_fail += 1
                            continue
                        except FetchError as e:
                            if first_failure is None:
                                first_failure = ("vendor", e, exp)
                            else:
                                after_fail += 1
                            continue
                        if first_failure is not None:
                            after_ok += 1
                        merged["call"].extend(got.get("call") or [])
                        merged["put"].extend(got.get("put") or [])
            return merged, first_failure, after_ok, after_fail, dispatched

        outcome, note = "ok", None
        attempted_days = 0
        saved_days = 0
        days_with_data = 0
        days_no_data_expected = 0     # 週末／假日撲空——正常現象
        days_no_data_unexpected = 0   # 交易日撲空——值得留意
        aborted_on: str | None = None
        abort_reason: str | None = None
        failed_expiration = None
        in_flight_after_failure_succeeded = 0
        in_flight_after_failure_failed = 0
        total_dispatched = 0
        schedule = sorted(missing, reverse=True)[:_IV_BACKFILL_PER_RUN]
        for day in schedule:
            attempted_days += 1
            merged, first_failure, after_ok, after_fail, dispatched = \
                _fetch_day_bounded(day)
            total_dispatched += dispatched

            def _save_day(merged=merged, day=day) -> bool:
                """這天的 surface 落盤，回傳是否真的有資料——不論這天
                最終判定為成功還是（部分）失敗；PERF-05 修正版契約第
                5 點：已經成功拿到的資料不為了模擬序列版本的「整天
                作廢」而丟棄。"""
                db.save_iv_observation(IvObservation(
                    symbol=symbol, observed_on=day,
                    surface=_surface_to_rows(merged), fetched_at=now_utc_iso()))
                return bool(merged["call"] or merged["put"])

            if first_failure is not None:
                reason, exc, failed_expiration = first_failure
                outcome, note = reason, str(exc)
                aborted_on, abort_reason = day, reason
                in_flight_after_failure_succeeded += after_ok
                in_flight_after_failure_failed += after_fail
                if merged["call"] or merged["put"]:
                    _save_day()
                    saved_days += 1
                    days_with_data += 1
                break

            if _save_day():
                days_with_data += 1
            elif _is_weekend(day):
                days_no_data_expected += 1
            else:
                days_no_data_unexpected += 1
            saved_days += 1

        # 因失敗而完全沒被送出去的組合數——「這批工作實際要抓哪幾天
        # 哪幾個到期日」跟序列版本完全相同（PERF-05 AC），這裡只是算出
        # 因為提早中止而少送了幾組，不是縮小涵蓋範圍本身。
        total_planned = len(expirations) * len(schedule)
        unstarted_due_to_failure = (total_planned - total_dispatched
                                    if aborted_on else 0)

        _emit_backfill_summary(
            emit, symbol=symbol, attempted_days=attempted_days,
            saved_days=saved_days, days_with_data=days_with_data,
            days_no_data_expected=days_no_data_expected,
            days_no_data_unexpected=days_no_data_unexpected,
            aborted_on=aborted_on, abort_reason=abort_reason,
            remaining_gap=len(missing) - saved_days, outcome=outcome,
            failed_expiration=failed_expiration,
            in_flight_after_failure_succeeded=in_flight_after_failure_succeeded,
            in_flight_after_failure_failed=in_flight_after_failure_failed,
            unstarted_due_to_failure=unstarted_due_to_failure)

        db.save_iv_backfill_run(IvBackfillRun(symbol=symbol,
                                             ran_on=today.isoformat(),
                                             outcome=outcome, note=note))
        return outcome, note

    def _ensure_contract_history(identity: dict, provider: str, token: str, *,
                                 emit) -> tuple[list[dict], str, str | None]:
        """一條腿的 exact contract 歷史：快取命中且今天已嘗試過就不打
        vendor，否則只補 `fetched_through` 之後到今天的缺口（HIVT-02／
        #153）。回傳 `(points, status, note)`——`status` 比照既有
        `_backfill_iv` 的 "ok"／"quota"／"vendor" 詞彙，只描述**這次
        嘗試**，已快取的 points 不因今天補不下去就被藏起來（#133 既有
        原則，同一套邏輯搬到 exact-contract 家族）。`points` 每筆是一個
        quote dict（HIVR-04／#163：`date`／`updated`／`dte`／`bid`／
        `ask`／`mid`／`underlying_price`／`vendor_iv`）。

        跟 `_backfill_iv` 的關鍵差異：那邊一次呼叫只回**一天**的整條鏈，
        這裡一次呼叫回**整段區間**（已由 #152 真實驗證），因此不需要
        `_IV_BACKFILL_PER_RUN` 那種逐日分批機制——缺口不論多長，一次
        請求就補齊。
        """
        db = _db()
        today = ny_today()
        occ_symbol = identity["contract_symbol"]
        cached = db.get_contract_history(occ_symbol)
        today_iso = today.isoformat()

        # HIVR-04（#163）：HIVT-02 時代寫入的舊格式列是 `[date, iv]`
        # 二元組（`list`），不是新版 quote `dict`——結構上缺 reconstruction
        # 必要欄位，繼續當新格式讀會直接讀錯欄位。純快取、可再生，視為
        # cache miss 整批重抓（一次性代價：每張合約 1 credit），而不是
        # 事後遷移一份讀不出原始報價的殘缺資料。
        if cached is not None and cached.points and not isinstance(
                cached.points[0], dict):
            cached = None

        if cached is not None and cached.last_attempt_on == today_iso:
            emit(stage="cache", severity="info",
                message="今天已嘗試過這張合約，沿用既有結論",
                contract_symbol=occ_symbol, **_identity_context(identity),
                already_fetched_today=True,
                fetched_through=cached.fetched_through,
                observations_returned=len(cached.points))
            return list(cached.points), cached.last_status, cached.last_note

        existing_points = list(cached.points) if cached is not None else []
        fetched_through = cached.fetched_through if cached is not None else None
        from_date = ((date.fromisoformat(fetched_through) + timedelta(days=1))
                    .isoformat() if fetched_through
                    else (today - timedelta(days=ivtrend.IV_TREND_MAX_HISTORY_DAYS))
                    .isoformat())
        to_date = today_iso

        emit(stage="cache", severity="info", message="計算歷史缺口",
            contract_symbol=occ_symbol, **_identity_context(identity),
            requested_from=from_date, requested_to=to_date,
            already_fetched_today=False, fetched_through=fetched_through)

        def _observer(telemetry):
            _emit_contract_history_telemetry(
                emit, telemetry, provider=provider, identity=identity,
                requested_from=from_date, requested_to=to_date)

        try:
            new_points = contract_history(provider, occ_symbol, from_date,
                                          to_date, token, observer=_observer)
        except QuotaExhausted as e:
            status, note = "quota", str(e)
        except FetchError as e:
            status, note = "vendor", str(e)
        else:
            merged = {q["date"]: q for q in existing_points}
            merged.update({q["date"]: q for q in new_points})
            merged_points = [merged[d] for d in sorted(merged)]
            db.save_contract_history(ContractHistory(
                contract_symbol=occ_symbol, points=tuple(merged_points),
                fetched_through=to_date, last_attempt_on=today_iso,
                last_status="ok", last_note=None))
            emit(stage="database_write", severity="info",
                message="寫入合約歷史觀測", contract_symbol=occ_symbol,
                **_identity_context(identity),
                observations_returned=len(new_points),
                null_iv_count=sum(1 for q in new_points
                                  if q["vendor_iv"] is None))
            if new_points:
                _emit_staleness(emit, identity=identity,
                                observation=max(new_points, key=lambda q: q["date"]),
                                request_time=now_utc_iso(), today=today)
            return merged_points, "ok", None

        # 失敗路徑：既有觀測原樣保留，只更新「今天嘗試過」的狀態，不
        # 讓下一次同一天的請求再打一次 vendor。
        db.save_contract_history(ContractHistory(
            contract_symbol=occ_symbol, points=tuple(existing_points),
            fetched_through=fetched_through, last_attempt_on=today_iso,
            last_status=status, last_note=note))
        emit(stage="database_write", severity="warning",
            message="vendor 這次嘗試失敗，沿用既有觀測",
            contract_symbol=occ_symbol, **_identity_context(identity),
            observations_returned=len(existing_points))
        return existing_points, status, note

    # 這三個統計量共用同一份 rolling window（`ivtrend._rolling_windows`），
    # available／unavailable 都看**最新那一點**（使用者畫面上看到的
    # 「目前」統計量），是不是有值——不是整條序列有沒有任何一點可用，
    # 序列起始端天然會有空窗，那不代表這個統計量現在不可用。
    _WINDOWED_STAT_FIELDS = frozenset(
        {"moving_average", "bollinger_bands", "current_zscore"})

    def _leg_stat_is_available(field_name: str, value) -> bool:
        if field_name == "moving_average":
            return bool(value) and value[-1][1] is not None
        if field_name == "bollinger_bands":
            upper = (value or {}).get("upper") or []
            return bool(upper) and upper[-1][1] is not None
        return value is not None   # current_zscore／percentile／delta_4w：純量

    def _emit_leg_stat_metrics(emit, *, identity: dict, stats: dict,
                               observation_count: int) -> None:
        """每個統計量各自一筆 `metrics` 事件（HIVT-03／#154）——沿用
        `_emit_metrics()` 在舊 (tenor,delta) 家族建立的既有模式（DG-04：
        一個欄位一筆事件，不合併、資料驅動迴圈而非逐欄位手抄），這裡是
        同一個模式在 exact-contract 家族的版本。`stats` 的 key 就是
        `field` context 的值——呼叫端傳什麼名字，畫面上就看到什麼名字。
        """
        for field_name, value in stats.items():
            available = _leg_stat_is_available(field_name, value)
            windowed = ({"lookback_days": ivtrend.IV_TREND_LOOKBACK_DAYS}
                       if field_name in _WINDOWED_STAT_FIELDS else {})
            emit(stage="metrics",
                severity="info" if available else "warning",
                message=f"{field_name} 計算完成" if available
                        else f"{field_name} 回報 unavailable",
                **_identity_context(identity), field=field_name,
                count=observation_count, **windowed)

    def _fetch_rate_curve_rows(dates: list[str]) -> tuple:
        """HIVR-06（#165）：涵蓋 `dates` 全部日期所需年份的曲線列，供
        `_rate_by_date_for_leg()` 逐一觀測日查表。空輸入或抓取失敗都回
        空 tuple——呼叫端據此讓每一筆觀測記成 `no_rate`，不擋其餘計算
        （這裡刻意不拋出，抓取失敗不是使用者能做什麼的錯誤）。

        PERF-03（#179）：走 `_cached_rate_curve_rows()`（年份為鍵的
        持久快取），不是直接呼叫注入進來的 `rate_curve_rows`——後者是
        快取層底下**未快取**的來源，測試假體也接在這一層（`treasury_
        cache.cached_rate_curve_rows()` 本身對任意 `Callable[[date,
        date], tuple]` 都成立，包括測試的固定回傳假體）。`today` 用
        `ny_today()`（紐約曆日）判斷「今年」——與全站既有市場日語意
        同一個時區基準。
        """
        if not dates:
            return ()
        from_date = date.fromisoformat(min(dates))
        to_date = date.fromisoformat(max(dates))
        try:
            return _cached_rate_curve_rows()(from_date, to_date, ny_today())
        except Exception:  # noqa: BLE001 — 抓不到就讓下游逐筆記 no_rate
            return ()

    def _rate_by_date_for_leg(rows: tuple, quotes: list[dict],
                              expiration: str) -> dict[str, float]:
        """逐一觀測日：那天的曲線（`curve_asof`，找不到就跳過）→ 那天到
        `expiration` 的年期 → 期限對齊利率（`rate_for_tenor`）。跟
        `ivreconstruct.reconstruct_iv_series()` 算 `T` 的方式完全一致
        （同一個 `DAYS_PER_YEAR`／`days_between`），這裡只是預先算好
        逐日的純量利率供它查表，不重算 T 的定義。
        """
        exp_date = date.fromisoformat(expiration)
        out: dict[str, float] = {}
        for q in quotes:
            d = q["date"]
            if d in out:
                continue
            curve = ratecurve.curve_asof(rows, d)
            if curve is None:
                continue
            T = days_between(date.fromisoformat(d), exp_date) / DAYS_PER_YEAR
            out[d] = ratecurve.rate_for_tenor(curve, T)
        return out

    def _dividend_yield_by_date_for_leg(history, quotes: list[dict],
                                        ) -> dict[str, float]:
        """逐一觀測日：那天的 q＝那筆觀測**自己的** `underlying_price`
        （跟 reconstruction 用同一筆報價的原則一致——分母是那個時刻的
        現價，不是另一個時刻的）。`history` 為 `None`（配息資料完全
        抓不到）或 `underlying_price` 缺席時該筆跳過，讓
        `reconstruct_iv_series()` 記成 `no_dividend_yield`。
        """
        if history is None:
            return {}
        out: dict[str, float] = {}
        for q in quotes:
            spot = q.get("underlying_price")
            if spot is None or spot <= 0:
                continue
            d = q["date"]
            out[d] = dividends.compute_q_asof(
                history, spot=spot, observation_date=date.fromisoformat(d))
        return out

    def _reconstruct_leg_series(identity: dict, quotes: list[dict],
                                rate_rows: tuple, dividend_history, *,
                                emit) -> list[tuple[str, float | None]]:
        """HIVR-06（#165）：寬版 quote 序列 → reconstruction（#164）→
        `(date, iv)` 序列，餵給既有 `_leg_historical_iv_payload`／
        `ivtrend` 統計量——**每一筆都重新反解，包含 vendor 剛好給了非
        null `iv` 的那些**（spec #159：全期間同一把尺，不得混用 vendor
        算的與自己算的）。存 raw quote、讀取時重算是既有架構決策
        （spec #159 §3）——這裡就是那個「讀取時」。

        HIVR-07（#166）：重建完後緊接著發一筆帳本事件（`_emit_
        reconstruction_ledger`）——「這張圖為什麼這麼稀疏」的答案就在
        這裡，不必另外讀程式碼推敲。

        HIVR-09（#168）：緊接著再發一筆 vendor IV 合理性比較（`_emit_
        vendor_benchmark`）——單純的診斷比較，`series` 本身（canonical
        series）在這一步之前就已經確定，這個 gate 不回頭改動它。
        """
        rate_by_date = _rate_by_date_for_leg(
            rate_rows, quotes, identity["expiration"])
        q_by_date = _dividend_yield_by_date_for_leg(dividend_history, quotes)
        series, failure_counts = ivreconstruct.reconstruct_iv_series(
            identity["option_type"], identity["strike"], identity["expiration"],
            quotes, rate_by_date, q_by_date)
        _emit_reconstruction_ledger(emit, identity=identity, fetched=len(quotes),
                                    series=series, failure_counts=failure_counts)
        _emit_vendor_benchmark(emit, identity=identity, quotes=quotes,
                               series=series)
        return series

    def _leg_historical_iv_payload(identity: dict, points: list[tuple],
                                   status: str, note: str | None, *,
                                   today, emit) -> dict:
        """`LegHistoricalIv` 的完整形狀（HIVT-02／#153＋HIVT-03／#154，
        spec #151 §4）：原始序列＋描述性欄位（HIVT-02）＋統計量套組
        （HIVT-03）。

        `history_span_days` 用**裁窗後**的序列算——「這張圖實際涵蓋多長
        時間」講的是使用者看到的那段，不是裁窗前 storage 裡累積的全部。
        `observation_count` 只算 `iv` 非 `None` 的那些：null IV 是缺席
        觀測（spec §2／§3 紅線），不進這個計數；`current_percentile`／
        `delta_4w` 的「current」都是這個非 null 集合裡最新一筆，兩者用
        同一個 `latest_iv`，不各自各推一次可能漂移的「最新值」。

        HIVR-08（#167）：每個點額外帶 `low_confidence`（`ivreconstruct.
        is_low_confidence()`，純粹的天數比較）——單純的資訊品質標記，
        點本身依然在 `points` 裡、依然被 `trimmed` 餵給上面這整組統計量，
        不從這裡的計算路徑拿掉任何一筆。
        """
        trimmed = ivtrend.trim_to_window(points, today=today)
        valid = sorted((d, iv) for d, iv in trimmed if iv is not None)
        latest_iv = valid[-1][1] if valid else None

        ma = ivtrend.moving_average(trimmed)
        bands = ivtrend.bollinger_bands(trimmed)
        zscore = ivtrend.current_zscore(trimmed)
        percentile = ivtrend.historical_percentile(trimmed, latest_iv)
        d4w = ivtrend.delta_4w(trimmed, latest=latest_iv, today=today)

        _emit_leg_stat_metrics(
            emit, identity=identity, observation_count=len(valid),
            stats={"moving_average": ma, "bollinger_bands": bands,
                  "current_zscore": zscore,
                  "historical_percentile": percentile, "delta_4w": d4w})

        return {
            "contract": identity,
            "points": [
                {"date": d, "iv": iv,
                 "low_confidence": ivreconstruct.is_low_confidence(
                     d, identity["expiration"])}
                for d, iv in trimmed
            ],
            "moving_average": [{"date": d, "value": v} for d, v in ma],
            "bollinger_upper": [{"date": d, "value": v}
                                for d, v in bands["upper"]],
            "bollinger_lower": [{"date": d, "value": v}
                                for d, v in bands["lower"]],
            "current_percentile": percentile,
            "current_zscore": zscore,
            "delta_4w": d4w,
            "observation_count": len(valid),
            "history_span_days": ivtrend.history_span_days(trimmed),
            "lookback_days_config": ivtrend.IV_TREND_LOOKBACK_DAYS,
            "status": status,
            "note": note,
        }

    def _spread_gap_payload(buy_series: list[tuple[str, float | None]],
                            sell_series: list[tuple[str, float | None]], *,
                            today) -> dict:
        """`spread_gap` 區塊的完整形狀（SIG-01／#172，spec #171）：買賣
        兩腿裁窗前的原始 reconstructed 序列先對齊（`ivspread.
        align_spread_gap`）、再裁窗（既有 `ivtrend.trim_to_window`）——
        順序是先對齊、再裁窗。裁窗後的 Gap 序列直接餵給既有
        `moving_average`／`bollinger_bands`／`historical_percentile`／
        `delta_4w`，這幾個既有函式零修改。

        只要候選有賣腿就一定回傳這個區塊（呼叫端保證），即使
        `observation_count` 是 0——`points`／`moving_average`／
        `bollinger_upper`／`bollinger_lower` 回空陣列，`current_
        percentile`／`delta_4w`／`delta_4w_ratio` 回 `None`、
        `delta_4w_status` 回 `"no_baseline"`、`shared_history_span_days`
        回 0，形狀永遠完整。

        `points[-1]`（對齊後 Gap 序列裡日期最新的一筆）是「目前 IV Gap
        現值」的正式資料來源——`ivspread.align_spread_gap` 已保證輸出
        依 date 嚴格遞增排序，這裡直接取最後一筆，不必另外排序。

        不含 `rolling_window_days`（施工前最終裁示：前端不需要讀這個
        值，直接不序列化）；不含 `current_zscore`；不含 `status`／
        `note`——這幾項是跟既有 `LegHistoricalIv` 的刻意契約差異
        （spec #171 契約清理）。
        """
        aligned = ivspread.align_spread_gap(buy_series, sell_series)
        trimmed = ivtrend.trim_to_window(aligned, today=today)
        current_gap = trimmed[-1][1] if trimmed else None

        ma = ivtrend.moving_average(trimmed)
        bands = ivtrend.bollinger_bands(trimmed)
        percentile = ivtrend.historical_percentile(trimmed, current_gap)
        d4w = ivtrend.delta_4w(trimmed, latest=current_gap, today=today)
        ratio, status = ivspread.spread_delta_4w_ratio_status(current_gap, d4w)

        return {
            "points": [{"date": d, "gap": g} for d, g in trimmed],
            "moving_average": [{"date": d, "value": v} for d, v in ma],
            "bollinger_upper": [{"date": d, "value": v}
                                for d, v in bands["upper"]],
            "bollinger_lower": [{"date": d, "value": v}
                                for d, v in bands["lower"]],
            "current_percentile": percentile,
            "delta_4w": d4w,
            "delta_4w_ratio": ratio,
            "delta_4w_status": status,
            "observation_count": len(trimmed),
            "shared_history_span_days": ivtrend.history_span_days(trimmed),
        }

    def _flush_diagnostics(diag: _CollectingDiagnostics) -> dict:
        """這次 request 收集到的 events 依優先序選出 `kept`（per-request
        上限，#146），組出要塞進回應的 `diagnostics` 欄位——回應永遠用
        完整的 `kept`，畫面上看到的是這次 request 實際發生過的全部
        重要事件。

        PERF-02（#178）：`kept` 不是原封不動全部落盤——`_select_for_
        storage()` 只留 `warning`／`error`，`info` 事件不佔用資料庫寫入
        次數（這個過濾只影響「寫進資料庫」這一步，不影響上面回應用的
        `kept`，也不動 `_select_for_persistence()` 既有的三層優先序）。
        批次寫入取代逐筆呼叫 `append_diagnostic()`。
        """
        kept = _select_for_persistence(diag.events)
        try:
            _db().append_diagnostics(_select_for_storage(kept))
        except Exception:  # noqa: BLE001 — 落盤失敗不影響這次回應
            pass
        return {"correlation_id": diagnostics.current_correlation_id(),
               "events": [dataclasses.asdict(e) for e in kept]}

    @app.get("/api/scenarios/{scenario_id}/iv-history")
    def iv_history(scenario_id: str, candidate_key: str) -> dict:
        """候選的 (tenor, delta) 座標**逐日重錨定**的 IV 序列。

        資料來自 **per-symbol 快取**（#129）：同一 ticker 的所有 Scenario
        共用同一份歷史，各自只是投影到自己的座標。target price／target
        month／scenario id 不同都不會觸發重抓。

        **閘門**：Historical IV 未解鎖時直接 403，一個 vendor 請求都不發。

        回應的 `status`（`ok`／`quota`／`vendor`）只描述**這次 backfill
        嘗試**的結果，不代表資料能不能看——那是兩件事（`unset`／
        `invalid` 兩種在閘門那關就 403 了，畫面連模組都不渲染）。已快取
        的觀測算出的 percentile 不因為今天補不下去就被藏起來，見
        `_iv_payload`。

        **`diagnostics`（DG-03／#146）**：這次 request 產生的 sanitized
        events，跟資料一起回——目前最常見的症狀是 HTTP 200 但資料是空
        的，詳情不夾在回應裡的話，前端得先猜這次的 correlation id 是
        什麼才查得到。
        """
        sc = _require(scenario_id)
        # PERF-01（#177）：這個 request 內 credential 只查一次，往下傳給
        # `_settings_view()`／`_known_secrets()`／挑選中 Provider 的
        # token 取得三處共用——原本各自重新查一次同一批資料。
        credentials = _credential_map()
        settings_view = _settings_view(credentials=credentials)
        if not settings_view["historical_iv_enabled"]:
            raise HTTPException(
                status_code=403,
                detail="Historical IV 未啟用——請在設定頁選擇自訂資料源並通過測試連線")

        diag = _CollectingDiagnostics()
        secrets = _known_secrets(credentials=credentials)

        def _make_emit(subsystem: str):
            def _emit(*, stage: str, severity: str, message: str, **context):
                return diagnostics.emit(diag, subsystem=subsystem,
                                        stage=stage, severity=severity,
                                        message=message, ts=now_utc_iso(),
                                        secrets=secrets, **context)
            return _emit

        # HIVR-03（#162）：exact-contract 與 legacy (tenor,delta) 重錨定
        # 兩個獨立 subsystem 各自的 emit，見 `_select_for_persistence`
        # 的逐 subsystem 保留預算。
        _emit_exact = _make_emit(diagnostics.SUBSYSTEM_EXACT_CONTRACT)
        _emit_legacy = _make_emit(diagnostics.SUBSYSTEM_LEGACY_REANCHOR)

        rec = _db().latest_result(scenario_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="這個劇本還沒有分析結果")
        cand = store.find_candidate(rec.view, candidate_key)
        groups_scanned = sum(len(r.get("expiry_top10") or [])
                             for r in rec.view.get("results") or [])
        _emit_exact(stage="candidate_lookup",
                   severity="info" if cand is not None else "error",
                   message="找到候選" if cand is not None else "找不到候選",
                   scenario_id=scenario_id, candidate_key=candidate_key,
                   found=cand is not None, groups_scanned=groups_scanned)
        if cand is None:
            _flush_diagnostics(diag)
            raise HTTPException(status_code=404,
                                detail=f"找不到候選：{candidate_key}")

        provider = settings_view["historical_iv"]["provider"]
        token = credentials[provider].token

        # Exact-contract 家族（HIVT-02／#153）：跟下面 (tenor, delta)
        # 重錨定家族完全獨立，不吃 `coords`，兩邊都算完才一起回應。
        legs_payload: dict[str, dict] = {}
        candidate_legs = cand.get("legs") or []
        leg_names = ("buy", "sell") if len(candidate_legs) >= 2 else ("buy",)
        leg_fetches = []
        for name, leg in zip(leg_names, candidate_legs):
            identity = _leg_contract_identity(leg, sc.symbol)
            leg_points, leg_status, leg_note = _ensure_contract_history(
                identity, provider, token, emit=_emit_exact)
            leg_fetches.append((name, identity, leg_points, leg_status, leg_note))

        # HIVR-06（#165）：point-in-time r／q 輸入是兩腿共用的——Treasury
        # 曲線與配息紀錄跟哪一條腿無關，一次抓好即可，不必逐腿各抓一次。
        all_dates = [q["date"] for _, _, points, _, _ in leg_fetches
                    for q in points]
        rate_rows = _fetch_rate_curve_rows(all_dates)
        dividend_history, _div_note = _dividend_loader()(sc.symbol, ny_today())

        reconstructed_by_name: dict[str, list[tuple[str, float | None]]] = {}
        for name, identity, leg_points, leg_status, leg_note in leg_fetches:
            reconstructed = _reconstruct_leg_series(
                identity, leg_points, rate_rows, dividend_history,
                emit=_emit_exact)
            reconstructed_by_name[name] = reconstructed
            legs_payload[name] = _leg_historical_iv_payload(
                identity, reconstructed, leg_status, leg_note,
                today=ny_today(), emit=_emit_exact)

        # SIG-01（#172）：Spread IV Gap——只要候選有賣腿就一定存在這個
        # 區塊；單腳候選（`reconstructed_by_name` 沒有 "sell"）完全沒有
        # 這個欄位，不是空區塊。
        spread_gap_payload = None
        if "sell" in reconstructed_by_name:
            spread_gap_payload = _spread_gap_payload(
                reconstructed_by_name["buy"], reconstructed_by_name["sell"],
                today=ny_today())

        # `expiry_counts` 掛在每個策略結果（`results[i]`）底下，不是
        # view 頂層——這裡只要「有哪些到期日」，跨策略去重即可。
        known_expiries = sorted({
            e for r in rec.view.get("results") or []
            for e, _ in r.get("expiry_counts") or []
        })
        target_expirations = ivhistory.nearby_expirations(
            known_expiries, today=ny_today(),
            tenor_days=cand.get("days_to_expiry") or 0)
        outcome, note = _backfill_iv(sc.symbol, provider, token,
                                     target_expirations, emit=_emit_legacy)

        coords = ivhistory.spread_coordinates(cand, spot=rec.view["meta"]["spot"])
        if coords is None:
            diag_payload = _flush_diagnostics(diag)
            return {**_iv_payload(candidate_key, [], outcome,
                                  "這個候選算不出 (tenor, delta) 座標"),
                   "legs": legs_payload,
                   **({"spread_gap": spread_gap_payload}
                      if spread_gap_payload is not None else {}),
                   "diagnostics": diag_payload}

        points = []
        in_grid = 0
        out_of_grid = 0
        for obs in _db().iv_observations(sc.symbol):
            surface = _rows_to_surface(obs.surface)
            reanchored = ivhistory.reanchor_spread(surface, coords)
            if _reanchor_in_grid(reanchored, coords):
                in_grid += 1
            else:
                out_of_grid += 1
            points.append({"date": obs.observed_on, **reanchored})

        _emit_reanchor_summary(_emit_legacy, coords=coords,
                               in_grid=in_grid, out_of_grid=out_of_grid)
        _emit_metrics(_emit_legacy, points, coords)
        diag_payload = _flush_diagnostics(diag)

        return {**_iv_payload(candidate_key, points, outcome, note),
               "legs": legs_payload,
               **({"spread_gap": spread_gap_payload}
                  if spread_gap_payload is not None else {}),
               "diagnostics": diag_payload}

    # ---------- 設定：資料源與 Provider credential（Settings／#124） ----------

    def _settings_view(*, credentials: dict[str, ProviderCredential | None] | None = None
                       ) -> dict:
        """設定頁的完整 view dict。

        **這裡是 token 的邊界**：回應只帶 `providers.mask_token()` 的遮罩
        形式，完整 token 不曾出現在任何欄位裡（#124 硬性 AC，有測試明文
        斷言）。`credentials` 回應欄位以 **provider** 為 key，不是以資料
        用途為 key——兩列選同一個 Provider 時看到的是同一筆，前端因此
        不會要求使用者輸入同一把 token 兩次。

        `credentials` 參數（PERF-01／#177）：呼叫端已經算過一次 provider
        → credential 的對照時可以直接傳進來，不傳就照舊自己查一次
        （`_credential_map()`），行為不變——只有 `credential` 這批資料
        會被重用，`get_verification()` 仍然照舊逐一查（沒有重複讀取的
        問題，`_known_secrets()` 不需要驗證結果）。
        """
        db = _db()
        stored = db.get_settings()
        usages = {
            providers.MARKET_DATA:
                stored.market_data if stored else UsageSetting(mode=providers.MODE_DEFAULT),
            providers.HISTORICAL_IV:
                stored.historical_iv if stored else UsageSetting(mode=providers.MODE_DEFAULT),
        }
        creds_map = credentials if credentials is not None else _credential_map()
        creds: dict[str, dict] = {}
        for p in providers.SUPPORTED_PROVIDERS:
            got = creds_map[p.id]
            checked = db.get_verification(p.id)
            creds[p.id] = {
                "configured": got is not None,
                "masked": providers.mask_token(got.token) if got else None,
                "updated_at": got.updated_at if got else None,
                # 三態（#125）：沒 credential ＝未設定；有 credential 但
                # 沒測過＝尚未驗證；測過就是它的結果。刻意不把「沒測過」
                # 當成「已連線」——那是在替使用者宣稱一件沒驗證過的事。
                "status": ("unset" if got is None
                           else "unverified" if checked is None
                           else "ok" if checked.ok else "failed"),
                "reason": checked.reason if checked else None,
                "checked_at": checked.checked_at if checked else None,
            }

        # Market Data 實際生效的來源（#125）：選了自訂但那家不可用時，
        # 分析走的是預設 Cboe——這件事必須說出來，不能靜默退回。
        md = usages[providers.MARKET_DATA]
        fallback = _market_data_fallback(md, creds)

        return {
            "supported_providers": [{"id": p.id, "label": p.label}
                                    for p in providers.SUPPORTED_PROVIDERS],
            **{usage: {"mode": u.mode, "provider": u.provider,
                       "default_label": providers.DEFAULT_LABELS[usage]}
               for usage, u in usages.items()},
            "credentials": creds,
            "market_data_effective": fallback,
            # #126：Historical IV 模組解不解鎖，由後端算好給一個旗標。
            # 前端不自己重推這條規則——推兩份遲早會漂移，而漂移的後果是
            # 「畫面以為鎖著、其實已經發了請求」這種正好違反 AC 的狀態。
            "historical_iv_enabled": _historical_iv_enabled(
                usages[providers.HISTORICAL_IV], creds),
            "updated_at": stored.updated_at if stored else None,
        }

    def _historical_iv_enabled(iv: UsageSetting, creds: dict[str, dict]) -> bool:
        """Historical IV 模組解鎖的唯一判準（#126）。

        預設（無）＝鎖著；選了自訂但 credential 未設定或驗證沒過，也是
        鎖著——**不進半殘狀態**。這條規則只寫一次，端點的守門與畫面的
        顯示都讀它。
        """
        if iv.mode != providers.MODE_CUSTOM or not iv.provider:
            return False
        return creds.get(iv.provider, {}).get("status") == "ok"

    def _market_data_fallback(md: UsageSetting, creds: dict[str, dict]) -> dict:
        """Market Data 這一列現在實際會用哪個來源，以及（若有）退回的原因。

        判準與 `_chain_fetcher()` 真正執行時走的分支同一套，兩者若分家，
        設定頁就會顯示一個跟實際抓取行為不符的來源。
        """
        default = {"source": providers.DEFAULT_LABELS[providers.MARKET_DATA],
                   "fallback": False, "reason": None}
        if md.mode != providers.MODE_CUSTOM or not md.provider:
            return default
        cred = creds.get(md.provider, {})
        label = providers.label_for(md.provider) or md.provider
        if cred.get("status") == "ok":
            return {"source": label, "fallback": False, "reason": None}
        reason = ({"unset": "尚未設定 token",
                   "unverified": "尚未測試連線"}.get(cred.get("status"))
                  or cred.get("reason") or "驗證失敗")
        return {"source": providers.DEFAULT_LABELS[providers.MARKET_DATA],
                "fallback": True, "reason": f"{label}{reason}，改用預設來源"}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return _settings_view()

    @app.put("/api/settings")
    def put_settings(req: SettingsRequest) -> dict:
        _db().save_settings(DataSourceSettings(
            market_data=UsageSetting(mode=req.market_data.mode,
                                     provider=req.market_data.provider),
            historical_iv=UsageSetting(mode=req.historical_iv.mode,
                                       provider=req.historical_iv.provider),
            updated_at=now_utc_iso()))
        # 刻意不寫事件紀錄：這條路徑上有 provider id 沒問題，但把設定變更
        # 寫進 append-only 紀錄會讓「token 絕不進事件紀錄」這條 AC 從
        # 「結構上不可能」退成「靠這裡沒寫錯」。設定是單一狀態、不是需要
        # 稽核序列的東西，不值得為此擴大 token 的暴露面。
        return _settings_view()

    @app.put("/api/settings/credentials/{provider}")
    def put_credential(provider: str, req: CredentialRequest) -> dict:
        if not providers.is_supported(provider):
            # 自訂不等於任意資料源：不在白名單就是不支援，不接受任何
            # 「先存起來再說」的 provider id。
            raise HTTPException(status_code=400,
                                detail=f"不支援的資料源：{provider}")
        _db().save_credential(ProviderCredential(
            provider=provider, token=req.token, updated_at=now_utc_iso()))
        return _settings_view()

    @app.post("/api/settings/credentials/{provider}/test")
    def test_credential(provider: str) -> dict:
        """測試連線：用已儲存的 token 對該 Provider 做一次真實驗證。

        結果存起來（設定頁重載不必重測）。驗證失敗**不是** HTTP 錯誤——
        「這把 token 不能用」是這個端點的正常答案之一，回 200 帶狀態，
        呼叫端才不必為了讀一個預期內的結果去 catch。
        """
        if not providers.is_supported(provider):
            raise HTTPException(status_code=400,
                                detail=f"不支援的資料源：{provider}")
        cred = _db().get_credential(provider)
        if cred is None:
            raise HTTPException(status_code=400,
                                detail="尚未設定 token，無法測試連線")
        outcome = verify_provider(provider, cred.token)
        _db().save_verification(ProviderVerification(
            provider=provider, ok=outcome.ok, reason=outcome.reason,
            checked_at=now_utc_iso()))
        return _settings_view()

    @app.delete("/api/settings/credentials/{provider}")
    def delete_credential(provider: str) -> dict:
        if not providers.is_supported(provider):
            raise HTTPException(status_code=400,
                                detail=f"不支援的資料源：{provider}")
        _db().delete_credential(provider)
        # 不存在也回 200＋現況：呼叫端要的是「現在沒有這把 credential」，
        # 而那在兩種情況下都已經成立。
        return _settings_view()

    return app


app = create_app()
