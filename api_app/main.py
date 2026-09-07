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
import os
import time
import uuid
from datetime import date, timedelta
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator

from option_chaser import __version__, ivpipeline, service, store
from option_chaser.data import treasury as treasury_data
from option_chaser.data.snapshot import snapshot_from_dict, snapshot_to_csv
from option_chaser.models import (AnalysisParams, ChainSnapshot, FAMILIES,
                                  FetchError, ParamError, RateLimitedError,
                                  STRATEGIES, normalize_families, subtypes_of)
from option_chaser.service import DividendLoader, RateCurveLoader
from option_chaser.timeframe import (TargetMonth, calendar_anchor,
                                     ensure_month_open, month_is_over)

from . import chain_backoff, diagnostics, metrics, providers
from .clock import now_utc_iso, ny_today
from .dividend_cache import cached_loader as cached_dividend_loader
from .identity import IdentityResolver, default_identity_resolver
from .rate_cache import cached_loader
from .storage import (ContractHistory, DataSourceSettings, IvBackfillRun,
                      IvObservation, NarrowHistoryEntry, ProviderCredential,
                      ProviderVerification, RateCacheEntry, ResultRecord,
                      ResultSummary, Scenario,
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

# 一輪刷新（T07／#193）的 server 端時間預算——明顯小於 serverless 函式
# 的硬性時間上限（CONTEXT.md：60 秒），留出寫回與回應序列化的餘裕。
# 可注入（`create_app()` 既有 DI 慣例）：測試要逼真模擬「預算耗盡→
# 續跑」，靠調小這個值或注入一個處理較久的 `fetch`／分析路徑，不是
# 假裝時間流逝。
REFRESH_RUN_BUDGET = timedelta(seconds=45)

# 2026-08-26 真機驗收反饋：恢復「逐張 Scenario 完成、逐張立即可用」的
# 產品語意（P1-b／PC-05 之前的舊行為），但不退回 N 個獨立 serverless
# invocation——做法是把「一次 HTTP 回應最多處理幾個 symbol 分組」單獨
# 限流，跟既有 `REFRESH_RUN_BUDGET`（安全網，防止單一分組本身耗時過久
# 撞到 60 秒硬上限）分開、互不取代。預設 1：完成一個分組（同一 symbol
# 的全部劇本）就回傳，其餘分組原樣進 `remaining`，交給前端既有的
# Continuation 迴圈立刻打下一次請求。分組本身不會被這個限流切開
# （ADR-0001 的去重範圍只在單一 invocation 內，切開分組等於讓同一組
# 劇本重複抓兩次 Chain）——各自獨立 symbol 的劇本因此天生逐一送達，
# 同一 symbol 的劇本仍共用一次抓取、一起送達（這是分享同一份抓取結果
# 的誠實後果，不是退步）。可注入，測試用小數值＋多 distinct symbol
# 逼出分段，不假裝時間流逝。
REFRESH_RUN_GROUP_LIMIT = 1

# REPAIR-08（#245，FIX-04，#052 audit）：單次分析的 per-subtype／
# per-family soft deadline——safety net 專用，處理異常輸入（例如某個
# symbol 的鏈異常龐大）下的優雅降級，**不是**效能修復的替代方案（正常
# production-scale 規模的效能已由 #240 的 `calibrate_leg` memoization
# 解決）。沿用 `service.ANALYSIS_SOFT_DEADLINE` 同一個數值與推導理由。
# 可注入（既有 DI 慣例），測試用小數值逼出 soft deadline 真的生效。
ANALYSIS_DEADLINE_SECONDS = service.ANALYSIS_SOFT_DEADLINE.total_seconds()

# MVP 範圍（沿用既有 Streamlit 版與 spec #47 的三欄表單）：方向是固定值，
# 不由前端送。需要看空時再由對應的票加上（`direction` 欄位是 legacy
# 遺留，T06／#221 起不再被任何判斷邏輯讀取，見 `_scenario_json`）。
_MVP_DIRECTION = "bullish"

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
    # T10（#227，Initial V2 spec #217）：使用者勾選的 Strategy Family
    # ——白名單本身就是型別（`Literal[FAMILIES]`），前端下拉只是方便，
    # 這裡才是真正的防線；`min_length=1`＝「至少要選一個才能送出」。
    # 與 `AnalyzeRequest.strategies`（`Literal[STRATEGIES]`，具體
    # subtype 白名單）刻意用同一種寫法、不同的白名單來源——那個端點
    # 認 subtype，這裡認 family，兩者是不同層次的詞彙，不共用型別。
    strategies: list[Literal[FAMILIES]] = Field(min_length=1)  # type: ignore[valid-type]
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
    # T10（#227）：編輯時可以增減 family，與建立同一份白名單／同一條
    # 「至少選一個」規則——編輯表單永遠送出目前完整的勾選集合（不是
    # 差異），沒有勾任何一個就是不合法的送出，跟建立時一樣。
    strategies: list[Literal[FAMILIES]] = Field(min_length=1)  # type: ignore[valid-type]
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


class RefreshRunRequest(BaseModel):
    """一輪刷新（T06／#190）的請求體。`scenario_ids` 省略或 `null` ＝
    範圍是全部未過期劇本（開站／頂部刷新鈕）；帶一組 id ＝只刷新這幾個
    （建立新劇本，P4）。"""
    scenario_ids: list[str] | None = None


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
    # REPAIR-02（#239，FIX-01，#052 audit Root Cause A）：全站唯一序列化
    # `Scenario.strategies` 的地方——`_row_json()` 內嵌呼叫它，所以這裡
    # 正規化一次，等於同時修好 `list_scenarios`／`get_scenario` 兩個
    # GET 端點**與** `refresh_scenario`／`refresh_run`（走
    # `_refresh_and_save()` → `_row_json()`）對 legacy 劇本的回應——不是
    # 只挑兩個 GET 端點動。舊（pre-V2）劇本存的是 legacy subtype 字串，
    # 未正規化直接透傳的話，前端 checkbox 判斷式對不上、使用者不改動
    # 任何 checkbox 直接儲存都會被後端 family 白名單拒絕（422）。
    # `create_scenario()`／`edit_scenario()` 寫入前已各自正規化過，這裡
    # 再正規化一次是冪等的（不會改變已經是 family 代碼的值），OD-01：
    # 只修讀取端，不做任何 DB migration，stored 的原始值不受影響。
    return {"id": sc.id, "symbol": sc.symbol, "direction": sc.direction,
            "target_price": sc.target_price, "target_month": sc.target_month,
            "notes": sc.notes, "strategies": list(normalize_families(sc.strategies)),
            "created_at": sc.created_at, "archived_at": sc.archived_at,
            "best_price": sc.best_price, "worst_price": sc.worst_price}


def _row_json(sc: Scenario, today: date, *, analyzed_at: str | None,
              best_return: float | None,
              representative_candidate: dict | None,
              spot: float | None = None,
              family_eligibility: dict | None = None) -> dict:
    """劇本在清單上的那一列。建立、列出、刷新三處共用同一個組裝函式——
    形狀只要差一個欄位，客戶端就得為同一個東西維護兩種型別。

    `representative_candidate`（MVP-v2／#77、#78）：代表候選的完整身分
    （策略／各腿履約價與權別／實際到期日），與 `best_return` 同一次走訪
    （`store.representative_candidate`），數值上不可能對不上。

    `spot`（QA 修正）：那次分析當下的標的現價，讓清單卡片有比較基準
    ——目標價／最高／最低（後兩者來自 `_scenario_json`）少了現價就只是
    三個孤立數字。尚未分析過時為 `None`。

    `family_eligibility`（T10／#227，Initial V2）：最近一次分析當下算出
    的 family 可選／不可選 verdict（`store._family_eligibility_map()`
    的輸出，鍵是 family 代碼）——編輯表單需要它才能顯示「這個 family
    現在為什麼不可選」，不該為此把整份 view 撈回來，與
    `representative_candidate`／`best_return` 同一個模式。尚未分析過
    時為 `None`（沒有可顯示的 verdict，不是假造一份「全部可選」）。"""
    return {**_scenario_json(sc), **_timing_json(sc, today),
            "latest_analyzed_at": analyzed_at, "best_return": best_return,
            "representative_candidate": representative_candidate,
            "spot": spot, "family_eligibility": family_eligibility}


def _summary_of(latest: ResultRecord | ResultSummary | None) -> dict:
    """從一筆「最新結果」（`ResultRecord` 或 `ResultSummary`，兩者皆有
    `analyzed_at`／`best_return`／`representative_candidate`／
    `family_eligibility`）取出卡片要的欄位；沒有結果（`None`，劇本從未
    成功分析過）時皆為 `None`——卡片據此顯示「—」與「尚未分析」，不是
    0 或一組假的候選。列出、詳細頁、刷新（含過期短路）共用同一個形狀，
    不必各自重寫一次 `if x else None`。"""
    return {"analyzed_at": latest.analyzed_at if latest else None,
            "best_return": latest.best_return if latest else None,
            "representative_candidate":
                latest.representative_candidate if latest else None,
            "spot": latest.spot if latest else None,
            "family_eligibility":
                latest.family_eligibility if latest else None}


def _event_json(event: dict) -> dict:
    """`Storage.list_events()` 的原始 dict 直接序列化前先過這裡。

    SCALE-06（#256，Ownership A-1 Expand，`/code-review` Spec 軸抓到
    的真缺口）：`owner_id` 是儲存層的資料 boundary 標記，不是 wire
    contract 的一部分——AC-3「production 行為逐位元不變」要求本票
    純加法欄位不能悄悄變成任何既有 HTTP 回應的一部分。過濾發生在
    序列化邊界，不是在 `Storage.list_events()` 本身（那裡仍然如實
    回傳完整資料，未來需要真的用到 owner_id 的呼叫端不受影響）。"""
    return {k: v for k, v in event.items() if k != "owner_id"}


def _diagnostic_json(event) -> dict:
    """`DiagnosticEvent` 直接序列化前先過這裡——同一個理由、同一個
    修法，見 `_event_json()`。"""
    d = dataclasses.asdict(event)
    d.pop("owner_id", None)
    return d


def _fail(stage: str, status: int, message: str, **extra: object) -> HTTPException:
    """失敗分層（V4／#52）。

    錯誤主體帶 `stage`，而不是只給一句話：「抓不到報價」與「分析失敗」
    使用者能做的處置不同（前者重試有意義、後者沒有），畫面要能分開講。
    `message` 仍是給人看的完整句子——舊的字串型 detail 客戶端照樣可讀。

    `**extra`（SCALE-05／#260）：additive metadata，只有呼叫端明確
    傳入時才會出現在 `detail` 裡——既有三個呼叫端（`params`／
    `analyze`／`archived`）從未傳入，`detail` 因此逐位元不變（AC-1）。
    """
    detail: dict = {"stage": stage, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status, detail=detail)


def _classify_fetch_failure(storage: Storage, e: FetchError, symbol: str) -> HTTPException:
    """抓鏈失敗的**唯一**分類點（SCALE-05／#260，AC-6）——`_analyze()`
    （`refresh_scenario` 走這條）與 `refresh_run` 的 group-level 抓鏈
    共用同一份判準：目前是不是正處於 Cboe 的 provider-global 限流
    封鎖窗（`chain_backoff.status()`），不在兩處各自判斷一次、避免
    兩個端點的分類邏輯漂移。

    是＝`"rate_limited"`（429，附上 `chain_backoff.status()` 給的全部
    結構化事實，AC-2）；否＝維持既有 `"fetch"`（502）分層，逐字不變。
    `.detail` 是純 dict，`refresh_run` 直接拿去併進批次結果的一筆
    失敗項，不必重新包一次 HTTPException。"""
    rl = chain_backoff.status(storage, "cboe")
    if rl is not None:
        return _fail("rate_limited", 429,
                     f"{symbol} 的報價來源目前受限流（Cboe），請稍後再試",
                     **rl)
    return _fail("fetch", 502, f"抓不到 {symbol} 的報價：{e}")


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
               refresh_run_budget: timedelta = REFRESH_RUN_BUDGET,
               refresh_run_group_limit: int = REFRESH_RUN_GROUP_LIMIT,
               analysis_deadline_seconds: float | None = ANALYSIS_DEADLINE_SECONDS,
               cboe_fetch: FetchChain | None = None,
               chain_backoff_default: timedelta = chain_backoff.DEFAULT_BACKOFF,
               identity_resolver: IdentityResolver = default_identity_resolver,
               cron_secret: str | None = None,
               ops_secret: str | None = None,
               enable_metrics: bool = True,
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

    `cboe_fetch`（SCALE-04／#255）：Cboe 這一步本身的抓取函式，預設
    `None`——**故意不直接把預設值定成 `cboe.fetch_chain`**：Python
    的預設參數值只在函式定義當下算一次，若寫成
    `cboe_fetch: FetchChain = cboe.fetch_chain`，之後任何
    `monkeypatch.setattr(cboe, "fetch_chain", ...)` 都會被這個提早
    綁死的參照繞過（既有大量測試正是這樣注入假體，不是透過這個新
    DI 參數）。`None` 時 `_default_fetch()` 內部改用延遲的模組屬性
    查找（`from option_chaser.data import cboe as cboe_module；
    cboe_module.fetch_chain`），行為與 `service.fetch_chain()` 既有
    的 lazy import 手法一致，monkeypatch 才吃得到。只在呼叫端沒有
    覆寫 `fetch` 時才生效（見 `_default_fetch()`）：`fetch` 是完整
    降級鏈（Cboe→yfinance）的複合入口，既有測試普遍直接整組覆寫它
    注入固定快照，那些呼叫根本不會走到 Cboe，backoff 包裝也無從
    套用，這是預期行為（測試決定性、零網路）。只有 production 預設
    （`fetch is service.fetch_chain`，未被覆寫）才會把 Cboe 呼叫點
    包上 provider-global backoff（`api_app.chain_backoff`）。

    `chain_backoff_default`（SCALE-04／#255，AC-7）：Retry-After 缺席時
    要封鎖多久的預設值，`create_app()` 的一般 DI 參數——與
    `refresh_run_budget`／`analysis_deadline_seconds` 同一種「不可變值
    當預設值」寫法，不受前面 `cboe_fetch` 那個 eager-binding 陷阱影響
    （陷阱只發生在把「函式」綁進預設值；`timedelta` 是不可變值，綁死
    在函式定義當下沒有問題）。這是 AC-7「可透過既有設定／DI 停用或設為
    0，作 rollback」字面要求的落地：先前只是
    `chain_backoff.backoff_aware_fetch()` 的私有參數，production 路徑
    完全碰不到；改成 `create_app()` 的建構參數後，未來要停用 backoff
    （例如懷疑它本身在搗亂）只需要用 `create_app(chain_backoff_default=
    timedelta(0))` 重新建構 app，不必修改 `chain_backoff.py` 或
    `main.py` 任何一行程式碼。

    `identity_resolver`（SCALE-06／#256，Ownership A-1 Expand）：這次
    request「屬於誰」——**只是 data boundary 標記，不是 authentication／
    privacy**（那是 out-of-scope 的 A-2）。production 預設
    `default_identity_resolver`，固定回傳單一 `SOLO_OWNER` 值；今天
    唯一存在的呼叫端在解析出這個值後，把它寫進 5 張 row-scoped 表
    （`scenarios`／`results`／`snapshots`／`events`／`diagnostics`）
    新寫入的 `owner_id` 欄位——本票**不**在任何查詢路徑套用過濾，寫入
    的值目前純粹是鋪路。這不是 `cboe_fetch` 那種每次呼叫都要吃一個
    `symbol` 參數的抓取函式，是一個零參數、對整個 app 生命週期只需要
    決定一次語意的函式，直接當一般函式值傳入即可，不受 `cboe_fetch`
    那個 eager-binding 陷阱影響（沒有任何測試需要
    monkeypatch `identity.default_identity_resolver` 這個模組屬性——
    要換身分邏輯，直接透過這個 DI 參數傳一個不同的函式進來就是了，
    這正是它存在的目的）。

    `cron_secret`（SCALE-07／#257，Treasury Cron）：`GET /api/cron/
    warm-rate-cache` 驗證 `Authorization: Bearer <cron_secret>` 用的
    比對值。預設 `None`——production 由呼叫端（`api/index.py`）留白，
    在函式本體裡才惰性讀 `os.environ.get("CRON_SECRET")`（比照
    `database_url()` 既有「呼叫時讀環境變數，可用顯式值覆寫供測試」
    的既有慣例，不是 `cboe_fetch` 那種函式參照的 eager-binding
    陷阱——這裡只是一個設定字串，讀一次環境變數沒有 monkeypatch
    失效的問題，但仍選擇惰性讀取以維持測試決定性：傳入顯式字串
    （含空字串）時完全不去看真實環境變數）。這把 secret 缺失或不符
    一律 401 fail-closed——不像 `provider_credentials` 那種使用者自己
    設定的 token，這是 Vercel 平台層級的基礎設施密鑰，沒有對應的
    Settings UI，本 app 只單純驗證有沒有對上。

    `ops_secret`（SCALE-08／#258，S0 最小可觀測性）：`GET /api/ops/
    metrics` 的授權比對值——與 `cron_secret` 同一套 fail-closed 設計，
    但刻意是**獨立的**環境變數（`OPS_SECRET`），不是重用
    `CRON_SECRET`：一個是「Vercel 排程系統呼叫這個 app」的信任邊界，
    一個是「人類運維人員查詢這個 app」的信任邊界，威脅模型不同，
    輪替其中一把不該連帶影響另一把。

    `enable_metrics`（同票）：整組 S0 觀測的總開關（Rollback Point）。
    關閉時全部七類指標的記錄呼叫直接是 no-op——AC-4 要求觀測 ON/OFF
    對任何既有產品 API 回應的序列化 JSON **逐位元一致**，這個開關本身
    就是那個宣稱的可驗證落地點：兩種狀態下跑同一組請求，除了新增的
    `GET /api/ops/metrics` 端點本身，其餘回應必須無法分辨開關是開是關。
    """
    app = FastAPI(title="Option Chaser API", version=__version__)

    # 延遲建構：Postgres adapter 建構本身不再連線（T02／#186——schema
    # 就緒檢查移到第一次真正呼叫 `_connect()`），這裡的快取純粹是省下
    # 重建物件本身，不是為了避免連線副作用；但保留「延遲」仍然重要，
    # 因為 `storage` 這個依賴注入參數要到 `create_app()` 呼叫時才決定。
    cached: dict[str, Storage] = {}

    def _db() -> Storage:
        if storage is not None:
            return storage
        if "db" not in cached:
            cached["db"] = storage_from_env()
        return cached["db"]

    # SCALE-04（#255）：production 預設抓鏈路徑——Cboe 呼叫點包上
    # provider-global backoff，失敗（含 `RateLimitedError`）原樣退回
    # 既有 yfinance 備援鏈，與 `service.fetch_chain` 逐一對齊，只是
    # Cboe 那一步多了 backoff 檢查與記錄。用 `fetch is service.
    # fetch_chain` 識別呼叫端有沒有覆寫整條複合鏈——覆寫時（幾乎全部
    # 既有測試都這樣做，注入固定快照）直接沿用呼叫端給的 `fetch`，
    # backoff 包裝無從套用也不需要套用。
    def _metered_chain_fetch(fn: FetchChain, source: str) -> FetchChain:
        """S0（SCALE-08／#258）指標 #1／#2：包住一個實際會打上游的抓鏈
        函式，記錄「真的打了一次」與「這次是不是被 429 擋下來」。刻意
        包在這一層、不是包在 `chain_backoff.backoff_aware_fetch()`
        外面——backoff 短路（封鎖窗內、零上游呼叫）時 `fn` 根本不會被
        呼叫到，指標因此天然只計真正發生過的上游請求，不會把「被我們
        自己的 backoff 擋下來」誤算成一次 fetch。"""
        def wrapped(symbol: str) -> ChainSnapshot:
            try:
                snap = fn(symbol)
            except RateLimitedError:
                _record_metric("chain_429_count", ny_today(),
                               source=source, symbol=symbol)
                _record_metric("chain_fetch_count", ny_today(),
                               source=source, symbol=symbol)
                raise
            except Exception:
                _record_metric("chain_fetch_count", ny_today(),
                               source=source, symbol=symbol)
                raise
            _record_metric("chain_fetch_count", ny_today(),
                           source=source, symbol=symbol)
            return snap
        return wrapped

    def _default_fetch(symbol: str) -> ChainSnapshot:
        from option_chaser.data import cboe as cboe_module

        actual_cboe_fetch = _metered_chain_fetch(
            cboe_fetch if cboe_fetch is not None else cboe_module.fetch_chain,
            "cboe")
        try:
            return chain_backoff.backoff_aware_fetch(
                _db(), "cboe", actual_cboe_fetch, symbol,
                default_backoff=chain_backoff_default)
        except FetchError:
            from option_chaser.data import yf

            return _metered_chain_fetch(yf.fetch_chain, "yfinance")(symbol)

    _effective_fetch: FetchChain = (
        _default_fetch if fetch is service.fetch_chain else fetch)

    # SCALE-07（#257）：`None`＝呼叫端沒有覆寫，惰性讀真實環境變數；
    # 顯式傳入（含空字串）時完全採用那個值，測試才有決定性。
    _effective_cron_secret = (cron_secret if cron_secret is not None
                              else os.environ.get("CRON_SECRET"))
    # SCALE-08（#258）：同一套設計，獨立的環境變數。
    _effective_ops_secret = (ops_secret if ops_secret is not None
                             else os.environ.get("OPS_SECRET"))

    def _record_metric(metric: str, today: date, *, source: str = "",
                       symbol: str = "", count: int = 1,
                       amount: float = 0.0) -> None:
        """S0（SCALE-08／#258）的唯一記錄入口——`enable_metrics=False`
        時整組觀測是 no-op（AC-4 的 rollback 開關），開啟時委派給
        `api_app.metrics.record()`（本身已經是 fail-open，這裡不用
        再包一層 try/except）。"""
        if enable_metrics:
            metrics.record(_db(), metric, today, source=source,
                           symbol=symbol, count=count, amount=amount)

    # 合併 correlation id（DG-02／#145）與 storage 連線 scope
    # （PERF-01／#177，T02／#186 修形）成單一層 middleware——原本兩層
    # 各自的 `call_next()` 轉送對大 payload（`/iv-history` 十萬字元級）
    # 是多餘的額外一趟。
    #
    # `_db()` 本身現在是零連線的物件建構（見上），呼叫它拿
    # `request_scope` 不再是「進 scope 前先偷跑一條連線」；`memory.py`
    # 沒有 `request_scope()` 這個方法（`Storage` Protocol 也沒有這個
    # 方法，兩者皆零改動），用 `getattr` 拿不到就直接跳過，行為完全
    # 比照今天。`_db()` 本身可能丟出例外（例如環境變數沒設好）——這裡
    # 也要容忍，不然會連 `/api/health` 這種本來就設計成容忍連不上的
    # 端點都被這層擋在前面。
    #
    # `request_scope()` 現在是**惰性**的（進入不主動開連線，第一次
    # 真正用到 storage 才開）——完全不碰 storage 的 request（例如某些
    # 純驗證錯誤）因此不再付任何連線握手。
    @app.middleware("http")
    async def _request_scope_middleware(request: Request, call_next):
        with diagnostics.correlation_scope() as cid, \
             diagnostics.owner_scope(identity_resolver()):
            try:
                scope = getattr(_db(), "request_scope", None)
            except Exception:  # noqa: BLE001 — 拿不到 storage 就整個跳過，交給下游端點自己的錯誤處理
                scope = None
            if scope is None:
                response = await call_next(request)
            else:
                with scope():
                    response = await call_next(request)
            response.headers["X-Correlation-Id"] = cid
        return response

    # 同一個道理：包快取的動作本身不必每次分析重做一次，惰性建一次、
    # 快取物件重用即可（`cached_loader()` 回傳的閉包內部沒有狀態，
    # 重不重建都不影響行為，這裡只是省一次函式呼叫）。
    cached_rate: dict[str, RateCurveLoader] = {}

    def _metered_rate_loader(today: date) -> tuple:
        """S0（SCALE-08／#258）指標 #4——包在 `rate_loader` 本身（不是
        `cached_loader()` 外面），只在 `cached_loader()` 內部真的判定
        「這是 cache miss，得問一次底層來源」時才會被呼叫到，因此
        天然只計真正的冷抓取，不含快取命中。"""
        _record_metric("cold_miss_count", ny_today(), source="treasury")
        return rate_loader(today)

    def _rate_curve_loader() -> RateCurveLoader:
        if "loader" not in cached_rate:
            cached_rate["loader"] = cached_loader(_db(), _metered_rate_loader)
        return cached_rate["loader"]

    cached_dividend: dict[str, DividendLoader] = {}

    def _metered_dividend_loader(symbol: str, today: date) -> tuple:
        """同上，per-symbol（S0 允許的維度）。"""
        _record_metric("cold_miss_count", ny_today(),
                       source="dividend", symbol=symbol)
        return dividend_loader(symbol, today)

    def _dividend_loader() -> DividendLoader:
        if "loader" not in cached_dividend:
            cached_dividend["loader"] = cached_dividend_loader(
                _db(), _metered_dividend_loader)
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
        **失敗就退回預設來源**（`_effective_fetch`，即既有的 Cboe →
        yfinance 降級鏈，SCALE-04／#255 起 Cboe 那一步多了
        provider-global backoff），而且把失敗如實記成一次驗證失敗——
        設定頁的三態
        因此會自己變成「驗證失敗」並說出原因，不需要另一套「上次
        fallback 過」的機制，也不會出現靜默退回。

        自訂成功時同樣記一次成功：那是比任何測試連線都真實的證據。
        """
        db = _db()
        stored = db.get_settings()
        md = stored.market_data if stored else None
        if md is None or md.mode != providers.MODE_CUSTOM or not md.provider:
            return _effective_fetch(symbol)

        cred = db.get_credential(md.provider)
        if cred is None:
            # 選了自訂卻沒有 token：不是錯誤，是還沒設定完——照常分析，
            # 設定頁那邊會顯示「尚未設定 token，改用預設來源」。
            return _effective_fetch(symbol)

        try:
            snap = custom_fetch(md.provider, symbol, cred.token)
        except FetchError as e:
            db.save_verification(ProviderVerification(
                provider=md.provider, ok=False, reason=str(e),
                checked_at=now_utc_iso()))
            return _effective_fetch(symbol)
        db.save_verification(ProviderVerification(
            provider=md.provider, ok=True, reason=None,
            checked_at=now_utc_iso()))
        return snap

    def _require(scenario_id: str) -> Scenario:
        sc = _db().get_scenario(scenario_id)
        if sc is None:
            raise HTTPException(status_code=404, detail=f"劇本不存在：{scenario_id}")
        return sc

    def _analyze(*, scenario_id: str, symbol: str, target_price: float,
                 target_month: str, strategies: tuple[str, ...],
                 best_price: float | None = None,
                 worst_price: float | None = None,
                 snap: ChainSnapshot | None = None) -> tuple[dict, dict]:
        """跑一次分析，回傳 (view dict, 原始快照 dict)。

        只吃分析真正需要的欄位——不要求一個完整的 `Scenario`，一次性
        分析端點才不必為了呼叫它而捏造一個沒有建立時間的假劇本。
        原始快照一併回傳：view dict 裡沒有逐筆合約報價，而 V8 的
        「原始資料」要的正是那個。

        `snap`（T06／#190）：Refresh Run 批次端點在呼叫這裡之前，已經
        依 symbol 分組抓過一次（ADR-0001，Run 內記憶體去重），這裡就不
        重複抓。單一劇本刷新端點不傳這個參數，走下面的直接抓取——
        chain 快取已隨 ADR-0001 整組移除，重複抓取的去重範圍現在只在
        單一 Refresh Run 內，不再跨 invocation。

        REPAIR-08（#245）：`analysis_deadline_seconds` 的計時點必須在
        抓鏈**之前**就啟動（`/code-review` Spec 軸抓到的真發現）——
        票面點名的異常輸入情境就包含「vendor 回應異常慢」，deadline
        若只在抓鏈之後才起算，抓鏈本身耗時異常時完全不受保護、也讓
        `service.run()` 與這裡宣稱的「同一種寫法」名不符實。`deadline`
        在函式最上方算好絕對時間點，`snap is not None`（Refresh Run
        批次路徑，抓鏈發生在呼叫這裡之前）時同樣適用——差別只是抓鏈
        那段已經花掉的時間發生在呼叫端，這裡起算的時間點本來就已經
        比那更早，涵蓋範圍不會漏掉。"""
        deadline = (time.monotonic() + analysis_deadline_seconds
                   if analysis_deadline_seconds is not None else None)
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
        if snap is None:
            try:
                snap = _fetch_chain(symbol)
            except FetchError as e:
                # 上游報價來源不可用（Cboe 與 yfinance 皆失敗）＝下游依賴
                # 問題。只認 FetchError：把這裡寫成 `except Exception` 的話，
                # 我們自己程式裡的 bug 會被貼上「抓不到報價、可稍後重試」的
                # 標籤，正好是這張票要消滅的那種誤導。其他例外照樣往上走成
                # 500——「不知道是哪一段」時說不知道，好過說一個錯的分層。
                raise _classify_fetch_failure(_db(), e, symbol) from e
        try:
            result = service.run_with_snapshot(
                req, snap, rate_curve_loader=_rate_curve_loader(),
                dividend_loader=_dividend_loader(),
                # `run_with_snapshot()` 要的是**剩餘**秒數（它自己不做
                # 抓鏈，見該函式 docstring），這裡把抓鏈已經花掉的時間
                # 扣掉再傳——負值一樣正確傳達「已經超時」，`_absolute_
                # deadline()` 的加法會把它算回過去的時間點。
                deadline_seconds=(deadline - time.monotonic()
                                  if deadline is not None else None))
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
        #
        # T02（#186）：`kind` 與 `rate` 共用同一個 try/except——`_db()`
        # 建構本身不再連線（schema 就緒檢查移到第一次真正呼叫
        # `_connect()`），`.kind` 因此不再是一次真連線的副作用。改成
        # 靠緊接著的 `get_rate_cache()`（本來就有的真連線）來偵測「連
        # 不上」，`kind` 的成功／失敗跟著同一次嘗試走，維持修正前
        # 「連不上時 storage 欄位如實顯示 unavailable」的既有行為。
        #
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
            db = _db()
            kind = db.kind
            entry = db.get_rate_cache()
            if entry is not None:
                rate = {"fetched_at": entry.fetched_at,
                       "ok": entry.curve is not None, "note": entry.note,
                       "last_success_at": entry.last_success_at}
        except Exception as e:  # noqa: BLE001 — 連不上也要能回答，這正是本端點的用途
            kind = f"unavailable: {e}"
        return {"status": "ok", "engine_version": __version__,
                "storage": kind, "path": request.url.path, "rate": rate}

    # ---------- Treasury Cron 預熱（SCALE-07／#257） ----------

    @app.get("/api/cron/warm-rate-cache")
    def cron_warm_rate_cache(request: Request) -> dict:
        """只做刷新、不服務使用者請求——Vercel Cron 每個市場日觸發一次，
        把 shared `rate_cache` 填新，讓當天第一個真正的使用者不必自己
        承擔 Treasury cold fetch。**只是預熱，不是 correctness 唯一
        來源**：與 `_rate_curve_loader()` 是同一條 canonical live
        loader/cache pipeline（`api_app/rate_cache.py::cached_loader()`
        本已有的既有機制），不另外寫一套 Treasury 解析邏輯——同一市場日
        內既有的 `market_day` 判準本身就讓重複呼叫 idempotent（第二次
        直接命中快取、零 vendor 呼叫），非交易日／vendor 尚未發布時
        loader 既有的 stale／failure 語意原樣適用，不在這裡另外偽造
        「今天已經新鮮」。既有同步 refresh-on-miss＋7 日陳舊備援
        （`api_app/rate_cache.py`）完全不受這個端點存在與否影響——
        Cron 沒跑到或跑失敗，當天第一次真正的分析仍會自己觸發同一條
        pipeline 補救。

        授權失敗（secret 未設定或不符）**先驗證再呼叫 pipeline**——
        不合法的請求零 vendor／cache mutation（AC-2）。
        """
        provided = request.headers.get("authorization")
        if not _effective_cron_secret or provided != f"Bearer {_effective_cron_secret}":
            raise HTTPException(status_code=401, detail="unauthorized")
        curve, note = _rate_curve_loader()(ny_today())
        return {"ok": curve is not None, "note": note}

    # ---------- S0 最小可觀測性（SCALE-08／#258） ----------

    @app.get("/api/ops/metrics")
    def ops_metrics(request: Request) -> dict:
        """七類指標的單一 operator 查詢入口（AC-1），逐一列出：

        1. `chain_fetch_count`——上游抓鏈實際被呼叫的次數（`source`／
           `symbol` 維度）
        2. `chain_429_count`——其中被限流擋下的次數
        3. `stale_serve_count`——這次分析實際用了陳舊利率／股利備援值
           的次數
        4. `cold_miss_count`——Treasury／Dividend 真正問過底層來源
           （快取沒命中）的次數
        5. `refresh_duration_ms`——一次刷新（抓鏈＋分析＋落盤）耗時，
           `count`／`total`／`max_value` 供算平均與量級
        6. `table_size`——`results`／`snapshots` 兩表即時查詢的列數、
           大小、單列大小分布（query-time gauge，不在上面的桶裡）
        7. `history_read_volume`——回答一次 `/history` 請求要撈幾筆
           完整歷史 view（SCALE-14 切換 narrow 讀取路徑後的對照基準）

        **operator-only**（AC-6）：與 cron 端點同一套 fail-closed 設計，
        `OPS_SECRET` 未設定或不符一律 401；不對一般使用者開放，前端
        不會呼叫這個端點。
        """
        provided = request.headers.get("authorization")
        if not _effective_ops_secret or provided != f"Bearer {_effective_ops_secret}":
            raise HTTPException(status_code=401, detail="unauthorized")

        by_metric: dict[str, list[dict]] = {m: [] for m in metrics.PERSISTED_METRICS}
        for e in _db().metric_summary():
            by_metric.setdefault(e.metric, []).append(
                {"bucket": e.bucket, "source": e.source or None,
                 "symbol": e.symbol or None, "count": e.count,
                 "total": e.total, "max_value": e.max_value})
        return {**by_metric, "table_size": _db().table_size_metrics()}

    # ---------- Application diagnostics（DG-02／#145） ----------

    @app.get("/api/diagnostics")
    def list_diagnostics(limit: int = 50) -> list[dict]:
        """近期 diagnostic events，最新在最上。`limit` 夾在
        `[1, diagnostics.RETENTION_LIMIT]`——查得到的最多就是留著的
        那些，沒有 pagination、沒有搜尋。"""
        clamped = max(1, min(limit, diagnostics.RETENTION_LIMIT))
        return [_diagnostic_json(e)
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
        # T10（#227，Initial V2 spec #217）：使用者第一次可以自己決定
        # 要看哪幾類策略——`_MVP_STRATEGIES` 這個寫死的預設值退場，
        # 改存使用者實際勾選的 family 集合（`normalize_families()` 去重
        # 保序，pydantic `Literal[FAMILIES]` 已經擋掉白名單外的字串）。
        sc = Scenario(id=uuid.uuid4().hex[:12], symbol=req.symbol.upper(),
                      direction=_MVP_DIRECTION, target_price=req.target_price,
                      target_month=req.target_month, notes=req.notes,
                      strategies=normalize_families(tuple(req.strategies)),
                      created_at=ts,
                      best_price=req.best_price, worst_price=req.worst_price,
                      owner_id=identity_resolver())
        try:
            _db().create_scenario(sc)
        except ScenarioExists as e:   # 48-bit 隨機 id，實務上碰不到；不留 500 的縫
            raise HTTPException(status_code=409, detail=str(e)) from e
        _db().append_event(ts=ts, scenario_id=sc.id,
                           event="SCENARIO_CREATED", payload=_scenario_json(sc),
                           owner_id=identity_resolver())
        # 回傳與清單同一個形狀（含 timing、尚未分析故摘要欄位皆為 None），
        # 客戶端才不必為「剛建立的」與「列出來的」維護兩種型別。
        return _row_json(sc, ny_today(), analyzed_at=None, best_return=None,
                         representative_candidate=None, spot=None,
                         family_eligibility=None)

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

        # T10（#227）：編輯表單永遠送出目前完整的 family 勾選集合，
        # 正規化去重保序後直接覆蓋——不是差異合併。
        new_strategies = normalize_families(tuple(req.strategies))
        updated = dataclasses.replace(
            sc, target_price=req.target_price, target_month=req.target_month,
            notes=req.notes, best_price=req.best_price,
            worst_price=req.worst_price, strategies=new_strategies)
        # T10：family 選擇改變也視同 thesis 改變——舊結果是對著另一組
        # family 跑出來的，繼續顯示會讓使用者以為新勾選的 family 已經
        # 有結果、或以為剛拿掉的 family 還在生效。舊劇本的 `sc.strategies`
        # 可能仍是遷移前的 legacy subtype 字串（#221），兩邊都先正規化
        # 成 family 再比較——否則「同一個 family、只是舊資料存的是
        # subtype 字串」會被誤判成改變，白白清掉還沒過期的結果。
        # ⚠ 兩側正規化不對稱是刻意、非巧合：`updated.strategies` 已經是
        # `new_strategies`（上面已正規化過），這裡不必再正規化一次；
        # 只有 `sc.strategies`（可能是遷移前的 legacy subtype 字串）
        # 需要正規化才能跟已正規化的 `updated.strategies` 比對。若日後
        # `updated.strategies` 的來源不再保證已正規化（例如 pydantic
        # 白名單放寬），這裡也要同步補上正規化，否則這條不對稱假設會
        # 悄悄失效。
        thesis_changed = (
            (sc.target_price, sc.target_month, sc.best_price, sc.worst_price,
             normalize_families(sc.strategies))
            != (updated.target_price, updated.target_month,
                updated.best_price, updated.worst_price, updated.strategies))

        _db().update_scenario(updated)
        if thesis_changed:
            _db().clear_results(scenario_id)
        ts = now_utc_iso()
        _db().append_event(ts=ts, scenario_id=scenario_id,
                           event="SCENARIO_EDITED",
                           payload=_scenario_json(updated),
                           owner_id=identity_resolver())

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
        # T13（#231，Initial V2）：回應走 `store.project_for_detail()`
        # 傳輸投影，不是落盤的那份原樣——儲存本身（`latest.view`）維持
        # 全保真，只有這個端點回給前端的那份瘦身。
        return {**_row_json(sc, ny_today(), **_summary_of(latest)),
                "latest_result": (store.project_for_detail(latest.view)
                                  if latest else None)}

    @app.post("/api/scenarios/{scenario_id}/archive")
    def archive_scenario(scenario_id: str) -> dict:
        _require(scenario_id)
        ts = now_utc_iso()
        # 重複封存回 False——對呼叫端而言結果相同（已經封存了），因此
        # 視為冪等成功，不當成錯誤。
        if _db().archive_scenario(scenario_id, ts=ts):
            _db().append_event(ts=ts, scenario_id=scenario_id,
                               event="SCENARIO_ARCHIVED", payload={},
                               owner_id=identity_resolver())
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
                               event="SCENARIO_RESTORED", payload={},
                               owner_id=identity_resolver())
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

    def _refresh_and_save(sc: Scenario, today: date, *,
                          snap: ChainSnapshot | None) -> dict:
        """一個劇本的刷新→入庫，`refresh_scenario`／`refresh_run`
        共用的核心（T06／#190 從前者抽出，理由是批次端點需要同一套
        過期短路與落地邏輯，不能各寫一份）。

        目標月已過完的劇本是所有刷新入口共用的**唯一**擋點（#68）：
        直接短路成一次無害的讀取（不抓鏈、不跑引擎、不入庫、不留
        事件），回傳目前既有的卡片列。這裡是唯一必須擋住的地方——批次
        流程本該在排隊前就先篩掉這類劇本以免浪費一趟網路往返，但擋點
        設在這裡才能保證「任何入口都擋得住」，含日後新增的、忘記先篩
        的呼叫端。

        垃圾桶擋點**不**在這裡——`refresh_scenario` 與 `refresh_run`
        對垃圾桶劇本要給的回應形狀不同（前者是一次 HTTP 409、後者是
        批次結果裡的一筆失敗項），各自在呼叫這裡之前自己判斷。

        `snap`：`None` 時直接呼叫 `_analyze()` 自己抓（單一劇本刷新走
        這條）；非 `None` 時是呼叫端已經抓好、要求跳過重複抓取的那份
        （Refresh Run 批次端點走這條，ADR-0001 的 Run 內 symbol 去重）。

        任何分析失敗（`_analyze()` 丟出的 `HTTPException`）原樣往外炸——
        `refresh_scenario` 讓它變成一次 HTTP 錯誤回應，`refresh_run`
        接住它轉成批次結果裡的一筆失敗項，兩邊的失敗語意（`stage`／
        `message`）完全共用同一份，不重複定義。
        """
        if month_is_over(TargetMonth.from_key(sc.target_month), today):
            latest = _db().latest_result(sc.id)
            return _row_json(sc, today, **_summary_of(latest))
        # T06（#221）：`sc.strategies` 存的是 family 代碼（新資料）或
        # legacy subtype 字串（舊資料，無遷移）——這是**唯一**的展開點，
        # 把它換算成 `AnalysisRequest.strategies` 要的具體 subtype 清單。
        subtypes = subtypes_of(normalize_families(sc.strategies))
        # S0（SCALE-08／#258）指標 #5：從真正開始做事（抓鏈＋分析＋
        # 落盤，跳過上面 `month_is_over` 的無害短路）到全部寫完為止，
        # 這是對「一次刷新要花多久」最有用的定義——短路那條路徑不算
        # 一次真正的刷新，混進來只會讓平均值失真。
        _refresh_started = time.monotonic()
        view, snapshot = _analyze(
            scenario_id=sc.id, symbol=sc.symbol, target_price=sc.target_price,
            target_month=sc.target_month, strategies=subtypes,
            best_price=sc.best_price, worst_price=sc.worst_price, snap=snap)
        analyzed_at = view["analyzed_at"]
        # S0 指標 #3：這次分析實際用掉的是不是陳舊的利率／股利備援值
        # ——直接讀 `view["params"]`（`dataclasses.asdict(AnalysisParams)`
        # 的既有欄位，RC1／#87 與 #123 早已存在），不重新判斷一次。
        params = view.get("params") or {}
        if params.get("rate_curve_stale"):
            _record_metric("stale_serve_count", today, source="treasury")
        if params.get("q_stale"):
            _record_metric("stale_serve_count", today, source="dividend",
                           symbol=sc.symbol)
        # T07（#224，Initial V2）：per-family map 只走訪一次
        # （`representative_candidates_by_family`），scalar 冠軍改由它
        # 取 `max()` 導出而非各自獨立呼叫 `store.representative_
        # candidate()` 再走一次——與既有 `best_return` 由
        # `representative_candidate()` 導出、`main.py` 為避免重複走訪
        # 而內聯同一條算式，是同一種既有作法（見 `store.best_return()`
        # docstring）；`store.representative_candidate()` 本身作為獨立
        # 公開純函式維持不變，多處測試仍拿它當交叉驗證的真相來源。
        per_family = store.representative_candidates_by_family(view)
        representative_candidate = (
            max(per_family.values(), key=lambda v: v["baseline_return"])
            if per_family else None)
        best_return = (representative_candidate["baseline_return"]
                       if representative_candidate is not None else None)
        # T10（#227，Initial V2）：`view["family_eligibility"]`（T08 已
        # 算好、隨 `serialize_result()` 寫進 view）額外落到卡片列這個
        # 輕量形狀——編輯表單需要它顯示「這個 family 現在為什麼不可選」，
        # 不必為此把整份 view 撈回來，與 `representative_candidate`／
        # `per_family` 同一個模式，不重算方向、不重呼叫 `family_
        # eligibility()`。
        family_elig = view["family_eligibility"]
        # SCALE-01（#252，Scaling Foundation Stage 1-0）：把這次分析的
        # 完整 resolved params／請求的 subtype 清單／引擎與 view schema
        # 版本／history replay 版本，獨立複製成 `ResultRecord` 的一等
        # 公民欄位（唯一的計算邏輯在 `store.historical_fact_context()`，
        # 這裡與既有資料 backfill 腳本共用同一份，不重寫第二次）。
        # `view` 本身完全不變——這幾個欄位純粹是它的複本。
        fact_context = store.historical_fact_context(view)
        owner_id = identity_resolver()
        _db().save_result(ResultRecord(
            scenario_id=sc.id, analyzed_at=analyzed_at, view=view,
            best_return=best_return,
            representative_candidate=representative_candidate,
            spot=store.spot(view), per_family=per_family or None,
            family_eligibility=family_elig, owner_id=owner_id, **fact_context))
        _db().save_snapshot(sc.id, analyzed_at, snapshot, owner_id=owner_id)
        # SCALE-09（#261，Scaling Foundation Stage 1-1）：dual-write
        # narrow history——只寫 visible candidate 的 non-null cost
        # （`store.visible_candidate_costs()` 即 FR-2.2 定義的聯集），
        # `results.view` 本身完全不受影響。**這裡不切換任何讀取
        # 路徑**——`GET /history` 仍然只讀 `result_history()`（Stage
        # boundary，SCALE-14 才會接線）。
        _db().save_narrow_history(
            NarrowHistoryEntry(scenario_id=sc.id, analyzed_at=analyzed_at,
                              candidate_key=key, cost=cost)
            for key, cost in store.visible_candidate_costs(view).items())
        _db().append_event(ts=now_utc_iso(), scenario_id=sc.id,
                           event="ANALYSIS_COMPLETED",
                           payload={"analyzed_at": analyzed_at,
                                    "snapshot_ref": view["snapshot_ref"]},
                           owner_id=owner_id)
        _record_metric("refresh_duration_ms", ny_today(),
                       amount=(time.monotonic() - _refresh_started) * 1000)
        return _row_json(sc, today, analyzed_at=analyzed_at,
                         best_return=best_return,
                         representative_candidate=representative_candidate,
                         spot=store.spot(view), family_eligibility=family_elig)

    @app.post("/api/scenarios/{scenario_id}/refresh")
    def refresh_scenario(scenario_id: str) -> dict:
        """單劇本刷新（V4／#52）：抓鏈→分析→結果與原始快照入庫。

        回傳的是**卡片列**而非整份 view：客戶端要依序刷新 N 個劇本、
        每完成一個就更新那張卡，每次拖回十萬字元級的 view 在手機上是
        實打實的浪費。要看完整 view 走 detail 端點。

        過期短路與落地邏輯見 `_refresh_and_save()`；這裡只負責垃圾桶
        擋點（下方）與把結果包成單一 HTTP 回應。
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
        return _refresh_and_save(sc, ny_today(), snap=None)

    @app.post("/api/scenarios/refresh-run")
    def refresh_run(body: RefreshRunRequest) -> dict:
        """一輪刷新（E1／#190，T06；Continuation／T07／#193）：批次版的
        `refresh_scenario`。

        `scenario_ids` 省略或為 `null` ＝範圍是全部未過期劇本（開站／
        頂部刷新鈕兩個 Refresh Trigger，CONTEXT.md 的 Refresh Trigger
        定義）；帶一組 id ＝只刷新這幾個（建立新劇本的 Refresh
        Trigger，P4）。垃圾桶劇本不會出現在省略時的預設範圍
        （`list_scenarios()` 預設排除），過期劇本也一併篩掉——不是
        「抓了但短路」，是根本不排進這一輪，省下無謂的一次結果讀取；
        顯式帶 id 時垃圾桶／過期劇本仍可能出現（呼叫端的競態，或就是
        故意要用單一劇本刷新既有的短路讀取行為），照樣個別回報、不
        中止整輪。

        **Run 內 symbol 去重**（ADR-0001）：先把這批劇本依 symbol 分組，
        每個 distinct symbol 只呼叫一次 `_fetch_chain()`，同組全部劇本
        共用那次抓取結果，純記憶體 dict、不寫任何跨 invocation 的快取。
        一個 symbol 抓取失敗時，那一組全部劇本各自記一筆 `stage=fetch`
        的失敗，其他 symbol 不受影響（Partial Success／P2）。

        **Continuation（T07／#193）**：`refresh_run_budget` 是明顯小於
        serverless 函式硬性時間上限（CONTEXT.md：60 秒）的時間預算，
        留出寫回與回應序列化的餘裕。每處理完一個劇本（不論成功失敗）
        就檢查剩餘預算；預算用完時，這個劇本之後的全部劇本（含還沒
        開始的 symbol 分組）一個都不處理，原樣進 `remaining`——不遺漏、
        不重複，呼叫端拿同一組 `remaining` 再打一次這個端點即可接續。
        分組的處理順序等於 `dict` 的插入順序（劇本依 `targets` 原序
        依序分組），因此「已完成」與「remaining」合起來、順序不重疊，
        永遠等於 `targets` 的全集。

        **注意（ADR-0001 的直接後果）**：續跑那次呼叫是全新的
        serverless invocation，這裡的 symbol 去重 dict 不會跨呼叫存活
        ——remaining 裡如果又出現同一個 symbol，續跑那次一樣會重新抓一次
        它的 Chain。這不是 bug，是「去重範圍只在單一 invocation 內」
        這個既有決策在分段時的自然結果，兩次呼叫各自仍然享有「同一次
        invocation 內」的去重。

        **逐組漸進回應**（2026-08-26 真機驗收）：`refresh_run_group_limit`
        （預設 1）限制單次回應最多完成幾個 symbol 分組就要回傳，跟
        `refresh_run_budget` 是兩條獨立的提前返回條件（任一個成立就
        停止取新分組，`or` 關係）——後者是安全網（防止單一分組本身
        耗時過久撞到 60 秒硬上限），前者才是本段真正要的行為：讓前端
        既有的 Continuation 迴圈（`response.remaining` 非空就立刻打下
        一次請求）在**每個分組完成的當下**就拿到那批結果，逐張／逐組
        解鎖顯示，不必等這一整輪全部 targets 都處理完。分組本身不會
        被這個限流從中間切開（下面的迴圈只在**完整處理完一個分組後**
        才檢查是否已達上限）——切開的話 remaining 裡剩下那半個分組
        會在續跑時重新抓一次同一張 Chain，白白多付一次代價。同一個
        symbol 底下的多個劇本因此仍會一起送達（它們本來就共用同一次
        抓取，同時就緒是誠實的結果，不是退步）；不同 symbol 的劇本則
        天生分屬不同分組，各自那組一完成就先送出、不等其餘分組。
        """
        today = ny_today()
        if body.scenario_ids is None:
            targets = [sc for sc in _db().list_scenarios()
                      if not month_is_over(TargetMonth.from_key(sc.target_month), today)]
        else:
            targets = [sc for sc in
                      (_db().get_scenario(sid) for sid in body.scenario_ids)
                      if sc is not None]

        groups: dict[str, list[Scenario]] = {}
        for sc in targets:
            groups.setdefault(sc.symbol, []).append(sc)

        results: list[dict] = []
        remaining: list[str] = []
        deadline = time.monotonic() + refresh_run_budget.total_seconds()
        budget_exhausted = False
        groups_completed = 0
        for symbol, scenarios in groups.items():
            if budget_exhausted or groups_completed >= refresh_run_group_limit:
                remaining.extend(sc.id for sc in scenarios)
                continue
            # 這一組裡有沒有任何劇本真的需要一份 Chain——垃圾桶與過期的
            # 都不需要，全組都不需要時就不必為這個 symbol 打一趟網路。
            needs_chain = any(
                sc.archived_at is None
                and not month_is_over(TargetMonth.from_key(sc.target_month), today)
                for sc in scenarios)
            snap: ChainSnapshot | None = None
            fetch_error: FetchError | None = None
            if needs_chain:
                try:
                    snap = _fetch_chain(symbol)
                except FetchError as e:
                    fetch_error = e
            for sc in scenarios:
                if budget_exhausted:
                    remaining.append(sc.id)
                    continue
                if sc.archived_at is not None:
                    results.append({"scenario_id": sc.id, "ok": False,
                                    "stage": "archived",
                                    "message": f"劇本已在垃圾桶，不再刷新：{sc.id}"})
                elif (fetch_error is not None and not month_is_over(
                        TargetMonth.from_key(sc.target_month), today)):
                    # SCALE-05（#260，AC-6）：與 `_analyze()` 共用同一個
                    # 分類點，不在這裡重新判斷一次「是不是限流」。
                    detail = _classify_fetch_failure(
                        _db(), fetch_error, symbol).detail
                    results.append({"scenario_id": sc.id, "ok": False,
                                    **detail})
                else:
                    try:
                        row = _refresh_and_save(sc, today, snap=snap)
                    except HTTPException as e:
                        detail = e.detail if isinstance(e.detail, dict) else {}
                        results.append({"scenario_id": sc.id, "ok": False,
                                        "stage": detail.get("stage"),
                                        "message": detail.get("message", str(e.detail))})
                    else:
                        results.append({"scenario_id": sc.id, "ok": True, "row": row})
                if time.monotonic() >= deadline:
                    budget_exhausted = True
            groups_completed += 1
        return {"results": results, "remaining": remaining}

    @app.get("/api/scenarios/{scenario_id}/results")
    def list_results(scenario_id: str) -> list[dict]:
        """歷史索引：只回時間戳，不回整份 view（一份十萬字元等級）。
        需要單次完整結果時走 detail／後續票的專屬端點。

        SCALE-02（#253）：索引來源改為 `Storage.result_timestamps()`
        ——主要走 `snapshots` 的主鍵（比對舊版 `result_history()` 快
        約 1.58×，後者連每一列的完整 `view` JSONB 都撈出來，Prototype
        #065 實測那條路徑對未來 narrow 表做 `DISTINCT` 會慢 12.6×，
        本票直接繞開這整條問題路徑），輔以 `results` 表窄查詢 UNION
        補回任何缺 snapshot 的孤兒列（見該方法 docstring）。"""
        _require(scenario_id)
        return [{"analyzed_at": ts} for ts in _db().result_timestamps(scenario_id)]

    @app.get("/api/scenarios/{scenario_id}/history")
    def get_spread_history(scenario_id: str, candidate_key: str) -> dict:
        """V9（#57，T11／#25 既有語意）：跨這個劇本全部歷史結果，依
        Spread 身份鍵（`candidate_key`）聚合成時間序列——唯讀，缺席快照
        如實呈現為斷點（`store.spread_cost_history()`），不插值。

        `result_history()` 回傳的 `ResultRecord.view` 已經是完整 view
        dict，不必額外重算——這條端點只是把既有引擎聚合邏輯接上 HTTP。
        """
        _require(scenario_id)
        rows = _db().result_history(scenario_id)
        # S0（SCALE-08／#258）指標 #7：narrow history 表（SCALE-09）
        # 落地前的等價證明——這裡量的是「答一次 /history 得撈幾筆
        # 完整歷史 view」，SCALE-14 切換讀取路徑後同一個問題該有的
        # 答案會大幅下降，兩者可直接比較。⚠ `count` 在這個指標的語意
        # 刻意是「累積撈了幾筆歷史列（volume）」，不是其餘六個指標
        # 「累積發生了幾次事件」的語意——這個指標的存在理由就是量
        # volume 本身，一次呼叫記 `len(rows)` 才是誠實的量，記 1
        # 反而會錯失這個指標唯一在乎的數字（`/code-review` SCALE-08
        # 已標記這是刻意設計、非命名疏忽）。
        _record_metric("history_read_volume", ny_today(), count=len(rows))
        views = [r.view for r in rows]
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
        return [_event_json(e) for e in _db().list_events(scenario_id=scenario_id)]

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
               "events": [_diagnostic_json(e) for e in kept]}

    def _iv_diagnostics_emitters(
            diag: _CollectingDiagnostics, *,
            credentials: dict[str, ProviderCredential | None] | None = None,
    ) -> tuple[Callable, Callable]:
        """建立 exact-contract／legacy 兩個 subsystem 各自的 emit closure
        （HIVR-03／#162 既有的兩線分離）。T11（#194）從 `iv_history()`
        內嵌的 `_make_emit` 抽出，供新增的 `/iv-history/backfill` 端點
        共用同一套 redaction 邏輯，不必各自重寫一份。"""
        secrets = _known_secrets(credentials=credentials)

        def _make_emit(subsystem: str):
            def _emit(*, stage: str, severity: str, message: str,
                     user_facing: bool | None = None, **context):
                return diagnostics.emit(diag, subsystem=subsystem,
                                        stage=stage, severity=severity,
                                        message=message, ts=now_utc_iso(),
                                        secrets=secrets,
                                        user_facing=user_facing, **context)
            return _emit

        return (_make_emit(diagnostics.SUBSYSTEM_EXACT_CONTRACT),
               _make_emit(diagnostics.SUBSYSTEM_LEGACY_REANCHOR))

    def _iv_history_gate(
            scenario_id: str, candidate_key: str, *,
            diag: _CollectingDiagnostics, emit_exact: Callable,
            credentials: dict[str, ProviderCredential | None] | None = None,
    ) -> tuple:
        """iv-history 相關端點共用的權限 gate＋candidate 查找（T11／#194
        從 `iv_history()` 抽出，供新增的 `/iv-history/backfill` 端點
        共用——兩個端點面對同一個 scenario_id／candidate_key 因此不會
        給出不一致的答案）。

        candidate 找不到時已經把 diagnostics flush 進 storage 才拋
        404（呼叫端不需要再處理這件事）。回傳
        `(sc, rec, cand, provider, token, known_expiries)`。
        """
        sc = _require(scenario_id)
        creds = credentials if credentials is not None else _credential_map()
        settings_view = _settings_view(credentials=creds)
        if not settings_view["historical_iv_enabled"]:
            raise HTTPException(
                status_code=403,
                detail="Historical IV 未啟用——請在設定頁選擇自訂資料源並通過測試連線")

        rec = _db().latest_result(scenario_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="這個劇本還沒有分析結果")
        cand = store.find_candidate(rec.view, candidate_key)
        groups_scanned = sum(len(r.get("expiry_top10") or [])
                             for r in rec.view.get("results") or [])
        emit_exact(stage="candidate_lookup",
                  severity="info" if cand is not None else "error",
                  message="找到候選" if cand is not None else "找不到候選",
                  scenario_id=scenario_id, candidate_key=candidate_key,
                  found=cand is not None, groups_scanned=groups_scanned)
        if cand is None:
            _flush_diagnostics(diag)
            raise HTTPException(status_code=404,
                                detail=f"找不到候選：{candidate_key}")

        provider = settings_view["historical_iv"]["provider"]
        token = creds[provider].token

        # `expiry_counts` 掛在每個策略結果（`results[i]`）底下，不是
        # view 頂層——這裡只要「有哪些到期日」，跨策略去重即可。
        known_expiries = sorted({
            e for r in rec.view.get("results") or []
            for e, _ in r.get("expiry_counts") or []
        })
        return sc, rec, cand, provider, token, known_expiries

    def _iv_pipeline_ports() -> tuple:
        """`ivpipeline` 認得的 Vendor／Storage port 組裝（T11／#194 從
        `iv_history()` 抽出，`/iv-history/backfill` 共用同一套接線，
        兩個端點打到同一組資料源與 storage adapter）。回傳
        `(vendor, storage_ports)`。"""
        db = _db()
        # `ivpipeline` 的 port 型別只認識未包裝的關鍵字參數／原始形狀——
        # `save_contract_history`／`save_iv_backfill_run`／
        # `save_iv_observation` 三個 storage 寫入方法在 `Storage` 這一層
        # 收的是各自的 dataclass，這裡用小轉接 lambda 包起來，模組本身
        # 不需要認識 `api_app.storage` 的型別。
        vendor = ivpipeline.VendorPorts(
            historical_surface=historical_surface,
            contract_history=contract_history,
            rate_curve_rows=_cached_rate_curve_rows(),
            dividend_loader=_dividend_loader(),
        )
        storage_ports = ivpipeline.StoragePorts(
            get_contract_history=db.get_contract_history,
            save_contract_history=lambda **kw:
                db.save_contract_history(ContractHistory(**kw)),
            get_iv_backfill_run=db.get_iv_backfill_run,
            save_iv_backfill_run=lambda symbol, ran_on, outcome, note:
                db.save_iv_backfill_run(IvBackfillRun(
                    symbol=symbol, ran_on=ran_on, outcome=outcome, note=note)),
            iv_observation_dates=db.iv_observation_dates,
            save_iv_observation=lambda symbol, observed_on, surface, fetched_at:
                db.save_iv_observation(IvObservation(
                    symbol=symbol, observed_on=observed_on, surface=surface,
                    fetched_at=fetched_at)),
            iv_observations=db.iv_observations,
        )
        return vendor, storage_ports

    @app.get("/api/scenarios/{scenario_id}/iv-history")
    def iv_history(scenario_id: str, candidate_key: str) -> dict:
        """候選的 Historical IV 完整回應（Exact-Contract Series 逐腿＋
        Legacy (tenor, delta) Re-anchor Series）。

        T10（#192）：金融決策邏輯全部下沉到 `ivpipeline.build_iv_history()`
        （T05／#189 建置、已由 `tests/test_ivpipeline_parity.py` 證明與
        切換前的內嵌編排逐位元一致）——這裡只做 HTTP 邊界的事：權限
        gate、candidate 404、把 `create_app()` 收到的資料源與 storage
        接成 `ivpipeline` 認得的 port 形狀、呼叫模組、把 diagnostics
        信封疊上去。

        資料來自 **per-symbol 快取**（#129）：同一 ticker 的所有 Scenario
        共用同一份 Legacy 家族歷史，各自只是投影到自己的座標；
        Exact-Contract 家族則是逐張合約各自快取（HIVT-02／#153）。

        **閘門**：Historical IV 未解鎖時直接 403，一個 vendor 請求都不發。

        T11（#194，兩段式補建 P3-a）：**Legacy 家族的冷 backfill 不再
        同步夾在這個請求裡**——這裡只讀「今天跑過了嗎」（`backfill_
        pending` 欄位），既有歷史立刻回傳把圖畫出來；真正觸發補建交給
        `POST .../iv-history/backfill`。Exact-Contract 家族的漸進式
        `ensure_contract_history()` 不受影響，仍在這個請求內同步跑
        （成本只補缺口、不是整批冷抓）。

        回應的 `status`（`ok`／`quota`／`vendor`）只描述**最近一次
        backfill 嘗試**的結果，不代表資料能不能看——已快取的觀測算出的
        percentile 不因今天補不下去就被藏起來（#133）。

        **`diagnostics`（DG-03／#146）**：這次 request 產生的 sanitized
        events，跟資料一起回——目前最常見的症狀是 HTTP 200 但資料是空
        的，詳情不夾在回應裡的話，前端得先猜這次的 correlation id 是
        什麼才查得到。
        """
        # PERF-01（#177）：這個 request 內 credential 只查一次，往下傳給
        # `_iv_diagnostics_emitters()`／`_iv_history_gate()` 共用——原本
        # 各自重新查一次同一批資料。
        credentials = _credential_map()
        diag = _CollectingDiagnostics()
        emit_exact, emit_legacy = _iv_diagnostics_emitters(
            diag, credentials=credentials)
        gate = _iv_history_gate(scenario_id, candidate_key,
                                diag=diag, emit_exact=emit_exact,
                                credentials=credentials)
        sc, rec, cand, provider, token, known_expiries = gate

        vendor, storage_ports = _iv_pipeline_ports()
        payload = ivpipeline.build_iv_history(
            symbol=sc.symbol, candidate=cand, spot=rec.view["meta"]["spot"],
            known_expiries=known_expiries, provider=provider, token=token,
            today=ny_today(), now_utc_iso=now_utc_iso,
            vendor=vendor, storage=storage_ports,
            emit_exact=emit_exact, emit_legacy=emit_legacy)

        diag_payload = _flush_diagnostics(diag)
        return {**payload, "diagnostics": diag_payload}

    @app.post("/api/scenarios/{scenario_id}/iv-history/backfill")
    def iv_history_backfill(scenario_id: str, candidate_key: str) -> dict:
        """T11（#194，兩段式補建 P3-a）：Legacy (tenor, delta) 家族的
        獨立補建進入點——`GET .../iv-history` 不再同步觸發這件事（見
        該端點回應裡的 `backfill_pending`），前端在收到 `backfill_
        pending: true` 時另外呼叫這裡，完成後重打一次
        `GET .../iv-history` 就能看到補全後的圖表。

        Progressive Backfill 本身（配額、取樣排程、到期日梯子演算法）
        完全不變——這裡呼叫的就是既有 `backfill_iv()`（`ivpipeline.
        run_legacy_backfill`），連同它既有的「今天已經跑過就直接沿用
        結論」短路：同一個 symbol 同一天重複呼叫這個端點不會重複燒
        vendor 額度，這個保證在引擎層、不是靠這裡另外擋一次。

        閘門與 candidate 查找跟主端點共用同一套規則（`_iv_history_
        gate()`）——未解鎖一樣 403、候選找不到一樣 404，兩個端點面對
        同一個 scenario_id／candidate_key 不會給出不一致的答案。
        """
        credentials = _credential_map()
        diag = _CollectingDiagnostics()
        emit_exact, emit_legacy = _iv_diagnostics_emitters(
            diag, credentials=credentials)
        gate = _iv_history_gate(scenario_id, candidate_key,
                                diag=diag, emit_exact=emit_exact,
                                credentials=credentials)
        sc, rec, cand, provider, token, known_expiries = gate

        vendor, storage_ports = _iv_pipeline_ports()
        target_expirations = ivpipeline.legacy_target_expirations(
            cand, known_expiries, ny_today())
        outcome, note = ivpipeline.run_legacy_backfill(
            sc.symbol, provider, token, target_expirations,
            today=ny_today(), now_utc_iso=now_utc_iso,
            vendor=vendor, storage=storage_ports, emit=emit_legacy)

        diag_payload = _flush_diagnostics(diag)
        return {"outcome": outcome, "note": note, "diagnostics": diag_payload}

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
