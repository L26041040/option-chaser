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
from pydantic import BaseModel, Field, field_validator

from option_chaser import __version__, service, store
from option_chaser.models import (AnalysisParams, ChainSnapshot, FetchError,
                                  ParamError, STRATEGIES)
from option_chaser.timeframe import (TargetMonth, calendar_anchor,
                                     ensure_month_open)
from option_chaser.workspace import now_utc_iso, ny_today

from .storage import ResultRecord, Scenario, ScenarioExists, Storage
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


def _timing_json(sc: Scenario, today: date) -> dict:
    """卡片的「距到期天數」（V3／#51）。

    兩件事都是領域規則、都不該讓瀏覽器自己猜：錨點＝該月第三個星期五
    （`timeframe.calendar_anchor`），「今天」＝紐約日曆（`ny_today`）。
    已過期就是負數，夾成 0 會讓過期劇本看起來還有救。

    `today` 由呼叫端傳入、整個回應只取一次——沿用專案既有原則
    （`workspace.card_of(observed=...)`、`ensure_month_open(month, today)`、
    儲存層零 wall-clock）：可測，而且跨午夜的請求不會在同一份清單裡
    出現兩個「今天」。

    刻意不放進 `_scenario_json`：那個結構會原樣寫進 `SCENARIO_CREATED`
    事件，而事件是不可變的事實，不能塞「距今幾天」這種隨時間改變的值。
    """
    anchor = calendar_anchor(TargetMonth.from_key(sc.target_month))
    return {"target_anchor": anchor.isoformat(),
            "days_to_anchor": (anchor - today).days}


def _scenario_json(sc: Scenario) -> dict:
    return {"id": sc.id, "symbol": sc.symbol, "direction": sc.direction,
            "target_price": sc.target_price, "target_month": sc.target_month,
            "notes": sc.notes, "strategies": list(sc.strategies),
            "created_at": sc.created_at, "archived_at": sc.archived_at}


def create_app(*, fetch: FetchChain = service.fetch_chain,
               storage: Storage | None = None) -> FastAPI:
    """`fetch` 與 `storage` 皆可注入：測試傳入固定快照與記憶體假體，
    因此不打真網路、不碰真資料庫，決定性。"""
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

    def _require(scenario_id: str) -> Scenario:
        sc = _db().get_scenario(scenario_id)
        if sc is None:
            raise HTTPException(status_code=404, detail=f"劇本不存在：{scenario_id}")
        return sc

    def _analyze(*, scenario_id: str, symbol: str, target_price: float,
                 target_month: str, strategies: tuple[str, ...]
                 ) -> tuple[dict, dict]:
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
                                strategy=strategies[0])
        req = service.AnalysisRequest(symbol=symbol, base_params=params,
                                      strategies=tuple(strategies))
        try:
            snap = fetch(symbol)
            result = service.run_with_snapshot(req, snap)
        except FetchError as e:
            # 上游報價來源不可用（Cboe 與 yfinance 皆失敗）＝下游依賴問題。
            raise HTTPException(status_code=502, detail=str(e)) from e
        except ParamError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
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
        return {"status": "ok", "engine_version": __version__,
                "storage": kind, "path": request.url.path}

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
                      strategies=_MVP_STRATEGIES, created_at=ts)
        try:
            _db().create_scenario(sc)
        except ScenarioExists as e:   # 48-bit 隨機 id，實務上碰不到；不留 500 的縫
            raise HTTPException(status_code=409, detail=str(e)) from e
        _db().append_event(ts=ts, scenario_id=sc.id,
                           event="SCENARIO_CREATED", payload=_scenario_json(sc))
        # 回傳與清單同一個形狀（含 timing、尚未分析故兩個摘要欄位為 None），
        # 客戶端才不必為「剛建立的」與「列出來的」維護兩種型別。
        return {**_scenario_json(sc), **_timing_json(sc, ny_today()),
                "latest_analyzed_at": None, "best_return": None}

    @app.get("/api/scenarios")
    def list_scenarios(include_archived: bool = False) -> list[dict]:
        # 卡片要的兩個數字跟著清單一起回（V3／#51）：否則前端得為每張卡
        # 各打一次 detail，而 detail 會拖回整份 view（十萬字元等級）。
        # 沒跑過的劇本兩欄皆 None ＝ 卡片顯示「—」，不是 0。
        summaries = _db().latest_summaries()
        today = ny_today()          # 整份清單共用同一個「今天」
        rows = []
        for s in _db().list_scenarios(include_archived=include_archived):
            summary = summaries.get(s.id)
            rows.append({
                **_scenario_json(s), **_timing_json(s, today),
                "latest_analyzed_at": summary.analyzed_at if summary else None,
                "best_return": summary.best_return if summary else None,
            })
        return rows

    @app.get("/api/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str) -> dict:
        sc = _require(scenario_id)
        latest = _db().latest_result(scenario_id)
        # `best_return` 也要在——detail 少一個欄位的話，客戶端就沒辦法把
        # 同一個型別套用在清單列與詳細回應上（V5 的詳細頁會踩到）。
        return {**_scenario_json(sc), **_timing_json(sc, ny_today()),
                "latest_analyzed_at": latest.analyzed_at if latest else None,
                "best_return": latest.best_return if latest else None,
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

    @app.post("/api/scenarios/{scenario_id}/analyze")
    def analyze_scenario(scenario_id: str) -> dict:
        sc = _require(scenario_id)
        view, snapshot = _analyze(
            scenario_id=sc.id, symbol=sc.symbol, target_price=sc.target_price,
            target_month=sc.target_month, strategies=sc.strategies)
        analyzed_at = view["analyzed_at"]
        _db().save_result(ResultRecord(scenario_id=sc.id,
                                       analyzed_at=analyzed_at, view=view,
                                       best_return=store.best_return(view)))
        _db().save_snapshot(sc.id, analyzed_at, snapshot)
        _db().append_event(ts=now_utc_iso(), scenario_id=sc.id,
                           event="ANALYSIS_COMPLETED",
                           payload={"analyzed_at": analyzed_at,
                                    "snapshot_ref": view["snapshot_ref"]})
        return view

    @app.get("/api/scenarios/{scenario_id}/results")
    def list_results(scenario_id: str) -> list[dict]:
        """歷史索引：只回時間戳，不回整份 view（一份十萬字元等級）。
        需要單次完整結果時走 detail／後續票的專屬端點。"""
        _require(scenario_id)
        return [{"analyzed_at": r.analyzed_at}
                for r in _db().result_history(scenario_id)]

    @app.get("/api/scenarios/{scenario_id}/events")
    def list_events(scenario_id: str) -> list[dict]:
        _require(scenario_id)
        return _db().list_events(scenario_id=scenario_id)

    return app


app = create_app()
