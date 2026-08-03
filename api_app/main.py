"""HTTP API —— 後端與前端之間的唯一接縫（spec #47）。

薄殼原則：本層不做任何金融計算，只負責 HTTP 邊界（請求驗證、呼叫引擎、
錯誤映射）。回應主體直接是引擎既有的 view dict（`store.serialize_result`），
前端因此也零金融計算——每個顯示數字都已由引擎算好。

serverless 前提：全程不碰檔案系統（Vercel 唯讀），走
`service.fetch_chain`＋`service.run_with_snapshot` 這組記憶體路徑。
"""
from __future__ import annotations

from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from option_chaser import __version__, service, store
from option_chaser.models import (AnalysisParams, ChainSnapshot, FetchError,
                                  ParamError, STRATEGIES)

FetchChain = Callable[[str], ChainSnapshot]

# V1（#48）：尚無持久化（V2／#50 才接儲存層），一次性分析用固定的
# scenario_id；資本限制同理暫為未設定。兩者都只是 view dict 的欄位值，
# 不影響任何計算。
_ADHOC_SCENARIO_ID = "adhoc"


class AnalyzeRequest(BaseModel):
    # symbol 會被代入資料源的 URL（`data/cboe.py`），因此限制成標的代號
    # 真正可能出現的字元，不讓 `../` 之類的東西有機會進到路徑裡。
    symbol: str = Field(pattern=r"^[A-Za-z.\-]{1,10}$")
    target_price: float = Field(gt=0)
    target_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    strategies: list[Literal[STRATEGIES]] = Field(min_length=1)  # type: ignore[valid-type]

    @field_validator("strategies")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        """同一策略送兩次沒有意義（引擎會重算一遍），去重但保留順序。"""
        return list(dict.fromkeys(v))


def create_app(*, fetch: FetchChain = service.fetch_chain) -> FastAPI:
    """`fetch` 可注入：測試傳入固定快照，因此不打真網路、決定性。"""
    app = FastAPI(title="Option Chaser API", version=__version__)

    @app.get("/api/health")
    def health(request: Request) -> dict:
        # `path` 回報 app 實際收到的路徑：部署在 Vercel 上時，這是判斷
        # rewrite 究竟送來原始路徑還是改寫後路徑的唯一可靠方式（決定了
        # 端點要用單一 catch-all 函式還是逐路由拆檔）。
        return {"status": "ok", "engine_version": __version__,
                "path": request.url.path}

    @app.post("/api/analyze")
    def analyze(req: AnalyzeRequest) -> dict:
        # base_params.strategy 只是引擎逐策略覆寫前的起點（`_analyze` 會
        # 對 `strategies` 每一項各自替換），取第一項即可——與既有
        # `workspace._request_for` 同樣的做法。
        params = AnalysisParams(target_price=req.target_price,
                                target_month=req.target_month,
                                strategy=req.strategies[0])
        request = service.AnalysisRequest(symbol=req.symbol,
                                          base_params=params,
                                          strategies=tuple(req.strategies))
        try:
            snap = fetch(req.symbol)
            result = service.run_with_snapshot(request, snap)
        except FetchError as e:
            # 上游報價來源不可用（Cboe 與 yfinance 皆失敗）＝下游依賴問題。
            raise HTTPException(status_code=502, detail=str(e)) from e
        except ParamError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return store.serialize_result(result, _ADHOC_SCENARIO_ID, capital=None)

    return app


app = create_app()
