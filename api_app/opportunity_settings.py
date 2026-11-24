"""Settings 選填鍵 `opportunity_search` 的契約（OS-02／#391，母票 #389 §6）。

存在既有 per-owner settings JSON 裡（`DataSourceSettings.opportunity_search`），
不加 DDL、不加端點：讀寫都走既有 `GET`／`PUT /api/settings`。

幾條刻意的決定：

- **欄位層級的部分更新**：PUT 裡的 `opportunity_search` 只帶有送的欄位，
  沒送的欄位沿用已存的值（從沒存過就是預設）。兩道 Consensus Gate 門檻
  因此真正「各自存取、互不影響」——存第一道不會順手把第二道蓋回去。
- **門檻是百分比數字 0–100**（20 ＝ 20%），兩端都含；不是 0–1 的比例。
- 驗證錯誤一律 `ValueError`（中文訊息）→ 沿用既有 settings 的 FastAPI
  422 格式；型別錯誤（字串、布林、null）也在 `mode="before"` 擋下，
  不讓 pydantic 把 `"20"` 或 `true` 悄悄轉成數字。
- 資料品質規則 R **不在**這裡（全站規則，#385），使用者只調兩道門檻。
"""
from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from option_chaser.models import FAMILIES

from . import search_universe
from .search_universe import CUSTOM, CUSTOM_SYMBOLS_MAX, UNIVERSE_IDS

DEFAULT_PERCENTILE_MAX = 20.0
DEFAULT_DISPERSION_MAX = 10.0
# 排序方式與顯示文字的唯一來源：設定頁（`options()["sorts"]`）與搜尋頁
# （搜尋回應的 `sort_options`）都讀這份，前端不各自寫一份。
_SORT_LABELS = {"return": "股價達標時的策略報酬（高→低）",
                "cost": "投入成本（低→高）",
                "max_loss": "最大損失（低→高）"}
SORTS = tuple(_SORT_LABELS)
DEFAULT_SORT = "return"

# 用語見 CONTEXT.md：第一道門檻是 Dispersion Percentile（分歧度在自身
# 歷史中的百分位），不是「共識百分位」。畫面用語照 #405（V2-03）：前端以
# PR（＝100 − 百分位）輸入第一道門檻，兩者的合法範圍都是 0–100，所以同一句
# 驗證訊息對 PR 也成立；存的值與單位不變。
_THRESHOLD_LABELS = {"percentile_max": "分歧度歷史排序門檻",
                     "dispersion_max": "分析師分歧率上限"}


def defaults() -> dict:
    """未設定時的完整值（每次回新的 dict，呼叫端改了也不污染下一次）。"""
    return {
        "universe_id": search_universe.DEFAULT_UNIVERSE_ID,
        "custom_symbols": [],
        "percentile_max": DEFAULT_PERCENTILE_MAX,
        "dispersion_max": DEFAULT_DISPERSION_MAX,
        "strategies": list(FAMILIES),
        "sort": DEFAULT_SORT,
    }


def effective(stored: Mapping | None) -> dict:
    """已存的值疊在預設上——讀取端（GET、後續的共識清單／搜尋）一律用
    這個，不各自處理「沒存過」的情況。不認得的鍵直接丟掉。"""
    out = defaults()
    for key, value in (stored or {}).items():
        if key in out:
            out[key] = value
    return out


def sort_options() -> list[dict]:
    return [{"id": key, "label": label} for key, label in _SORT_LABELS.items()]


def options() -> dict:
    """設定頁需要的選項清單與預設值——前端不自己寫一份。"""
    return {
        "universes": search_universe.universe_options(),
        "strategies": list(FAMILIES),
        "sorts": sort_options(),
        "custom_symbols_max": CUSTOM_SYMBOLS_MAX,
        "defaults": defaults(),
    }


class OpportunitySearchRequest(BaseModel):
    """PUT 裡的 `opportunity_search`：每個欄位都可省略（＝沿用已存值），
    但送了就必須合法——明確送 `null` 也是錯，不當成「省略」。"""
    model_config = ConfigDict(extra="forbid")

    universe_id: str | None = None
    custom_symbols: list[str] | None = None
    percentile_max: float | None = None
    dispersion_max: float | None = None
    strategies: list[str] | None = None
    sort: str | None = None

    @field_validator("universe_id", mode="before")
    @classmethod
    def _universe(cls, v: Any) -> str:
        if v not in UNIVERSE_IDS:
            raise ValueError(f"不支援的掃描股票範圍：{v}")
        return v

    @field_validator("custom_symbols", mode="before")
    @classmethod
    def _symbols(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("自訂清單必須是 ticker 陣列")
        out: list[str] = []
        for s in v:
            if not search_universe.is_valid_ticker(s):
                raise ValueError(f"不合法的 ticker：{s}（請用大寫代號，例如 AAPL）")
            if s not in out:
                out.append(s)
        if len(out) > CUSTOM_SYMBOLS_MAX:
            raise ValueError(f"自訂清單最多 {CUSTOM_SYMBOLS_MAX} 檔")
        return out

    @field_validator("percentile_max", "dispersion_max", mode="before")
    @classmethod
    def _threshold(cls, v: Any, info) -> float:
        label = _THRESHOLD_LABELS[info.field_name]
        # bool 是 int 的子類別，`true` 不該被當成 1。
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{label}必須是數字")
        if not 0 <= v <= 100:
            raise ValueError(f"{label}必須介於 0 到 100")
        return float(v)

    @field_validator("strategies", mode="before")
    @classmethod
    def _strategies(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("策略家族必須是陣列")
        unknown = [s for s in v if s not in FAMILIES]
        if unknown:
            raise ValueError(f"不支援的策略家族：{unknown[0]}")
        if not v:
            raise ValueError("至少要選一個策略家族")
        # 依 canonical 順序輸出、去重——同一組選擇只有一種存法。
        return [f for f in FAMILIES if f in v]

    @field_validator("sort", mode="before")
    @classmethod
    def _sort(cls, v: Any) -> str:
        if v not in SORTS:
            raise ValueError(f"不支援的排序方式：{v}")
        return v


class OpportunitySearchInvalid(ValueError):
    """合併後才看得出來的錯（跨欄位）。`field` 是出錯的欄位名，呼叫端用
    它組出與 pydantic 相同形狀的 422。"""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def merge(stored: Mapping | None, req: OpportunitySearchRequest) -> dict:
    """把這次送的欄位疊到已存的值上，回傳要存的完整 dict。

    跨欄位規則在合併**之後**檢查——欄位是分開存的，「選 custom」與
    「清單有東西」可能來自不同次請求。"""
    out = effective(stored)
    out.update(req.model_dump(exclude_unset=True))
    if out["universe_id"] == CUSTOM and not out["custom_symbols"]:
        raise OpportunitySearchInvalid("custom_symbols", "自訂清單至少要有一檔")
    return out
