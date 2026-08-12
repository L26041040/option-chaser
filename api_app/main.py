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
from datetime import date
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator

from option_chaser import __version__, service, store
from option_chaser.data.snapshot import snapshot_from_dict, snapshot_to_csv
from option_chaser.models import (AnalysisParams, ChainSnapshot, FetchError,
                                  ParamError, STRATEGIES)
from option_chaser.service import DividendLoader, RateCurveLoader
from option_chaser.timeframe import (TargetMonth, calendar_anchor,
                                     ensure_month_open, month_is_over)
from option_chaser.workspace import now_utc_iso, ny_today

from . import providers
from .dividend_cache import cached_loader as cached_dividend_loader
from .rate_cache import cached_loader
from .storage import (DataSourceSettings, ProviderCredential, RateCacheEntry,
                      ResultRecord, ResultSummary, Scenario, ScenarioExists,
                      Storage, UsageSetting)
from .storage.factory import storage_from_env

FetchChain = Callable[[str], ChainSnapshot]

# MVP 範圍（沿用既有 Streamlit 版與 spec #47 的三欄表單）：方向與策略
# 是固定值，不由前端送。需要看空或多策略時再由對應的票加上。
_MVP_DIRECTION = "bullish"
_MVP_STRATEGIES = ("bull-call-spread",)

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
               ) -> FastAPI:
    """`fetch`／`storage`／`rate_loader`／`dividend_loader` 皆可注入：
    測試傳入固定快照、記憶體假體與假來源，因此不打真網路、不碰真資料庫，
    決定性。

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
            snap = fetch(symbol)
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

    # ---------- 設定：資料源與 Provider credential（Settings／#124） ----------

    def _settings_view() -> dict:
        """設定頁的完整 view dict。

        **這裡是 token 的邊界**：回應只帶 `providers.mask_token()` 的遮罩
        形式，完整 token 不曾出現在任何欄位裡（#124 硬性 AC，有測試明文
        斷言）。`credentials` 以 **provider** 為 key，不是以資料用途為
        key——兩列選同一個 Provider 時看到的是同一筆，前端因此不會要求
        使用者輸入同一把 token 兩次。
        """
        db = _db()
        stored = db.get_settings()
        usages = {
            providers.MARKET_DATA:
                stored.market_data if stored else UsageSetting(mode=providers.MODE_DEFAULT),
            providers.HISTORICAL_IV:
                stored.historical_iv if stored else UsageSetting(mode=providers.MODE_DEFAULT),
        }
        creds: dict[str, dict] = {}
        for p in providers.SUPPORTED_PROVIDERS:
            got = db.get_credential(p.id)
            creds[p.id] = ({"configured": False, "masked": None, "updated_at": None}
                           if got is None else
                           {"configured": True,
                            "masked": providers.mask_token(got.token),
                            "updated_at": got.updated_at})
        return {
            "supported_providers": [{"id": p.id, "label": p.label}
                                    for p in providers.SUPPORTED_PROVIDERS],
            **{usage: {"mode": u.mode, "provider": u.provider,
                       "default_label": providers.DEFAULT_LABELS[usage]}
               for usage, u in usages.items()},
            "credentials": creds,
            "updated_at": stored.updated_at if stored else None,
        }

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
