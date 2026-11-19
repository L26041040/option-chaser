"""機會搜尋：請求契約與「代表候選 → 結果列」投影（OS-04／#393，母票 #389 §5）。

端點本身（`POST /api/opportunity/search`）在 `api_app/main.py` 的
`create_app()` 裡——它必須走既有的 `_fetch_chain()`（Global Vendor Fuse、
429 退避）與既有的 `_analyze()`（引擎），這兩個都是 closure。這裡只放
不碰 I/O 的部分：

- `SearchRequest`：請求體驗證。
- `rows_for_symbol()`：把一次既有分析的 view，透過**既有**
  `store.representative_candidates_by_family()`（與劇本存檔同一個函式）
  取出每個家族的代表候選，再把同一個候選在 `candidate_pool` 裡的既有
  欄位**原值**搬進結果列。**不做任何損益、報酬、成本或過濾計算**
  （#389 §5.2）——結果列每一個數字都是引擎已經算好的值，只是換個名字。
- `sort_rows()`：依既有欄位排序（不產生新數字）。

欄位對應（結果列 ← 既有來源）：

| 結果列 | 來源 |
|---|---|
| `family` | `representative_candidates_by_family()` 的 key |
| `subtype` | 代表候選 `strategy` |
| `candidate_key`／`legs`／`expiry` | 代表候選同名欄位（原樣） |
| `target_return` | 代表候選 `baseline_return`（與劇本頭條同口徑） |
| `entry_cost` | `candidate_pool[key].natural_cost`（每股，最差成交） |
| `max_loss_per_contract` | `candidate_pool[key].max_loss_per_contract`（每口） |
| `breakeven` | `candidate_pool[key].breakeven` |
| `buffer_days` | `candidate_pool[key].buffer_days` |

欄位名刻意不含 expected／probability／win（#389 §9 語意紀律）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from option_chaser import store
from option_chaser.models import FAMILIES

from .opportunity_settings import SORTS

# 一次搜尋最多處理幾檔（#389 §9，數值待 #386）；`create_app(opportunity_fetch_cap=)`
# 與環境變數 `OPPORTUNITY_FETCH_CAP` 可覆寫。
DEFAULT_FETCH_CAP = 50

FAILURE_REASONS = ("fetch_failed", "no_candidates", "invalid_month",
                   "analysis_failed")


class SearchRequest(BaseModel):
    """`POST /api/opportunity/search` 的請求體；每個欄位都可省略。

    - `symbols`：省略＝目前入選清單；續跑時傳回上次的 `remaining`。
    - `strategies`／`sort`：省略＝使用者的 `opportunity_search` 設定。"""
    model_config = ConfigDict(extra="forbid")

    # 上限＝一次搜尋處理量的十倍，擋掉超長清單（含 400 訊息逐一回顯）。
    symbols: list[str] | None = Field(default=None, min_length=1,
                                      max_length=DEFAULT_FETCH_CAP * 10)
    strategies: list[Literal[FAMILIES]] | None = Field(  # type: ignore[valid-type]
        default=None, min_length=1)
    sort: Literal[SORTS] | None = None  # type: ignore[valid-type]


def scenario_params(symbol: str, item: dict, target_month: str,
                    families: list[str]) -> dict:
    """Consensus Scenario 參數（#389 §5.1）：前端「存成劇本」原封不動送進
    既有 `POST /api/scenarios`；搜尋本身也用同一組參數跑分析。best／worst
    不帶（#383 預設）。"""
    return {"symbol": symbol, "target_price": item["mean"],
            "target_month": target_month, "strategies": list(families)}


def consensus_summary(item: dict) -> dict:
    return {key: item[key] for key in
            ("mean", "n_analysts", "dispersion", "percentile", "as_of", "coverage")}


def rows_for_symbol(view: dict, *, item: dict, scenario: dict) -> list[dict]:
    """一檔股票一次分析的結果列（每個有代表候選的家族一列）。零合格候選
    → 空清單。"""
    pool = view.get("candidate_pool") or {}
    rows = []
    for family, rep in store.representative_candidates_by_family(view).items():
        candidate = pool[rep["candidate_key"]]
        rows.append({
            "symbol": scenario["symbol"],
            "family": family,
            "subtype": rep["strategy"],
            "candidate_key": rep["candidate_key"],
            "legs": rep["legs"],
            "expiry": rep["expiry"],
            "target_month": scenario["target_month"],
            "buffer_days": candidate["buffer_days"],
            "entry_cost": candidate["natural_cost"],
            "max_loss_per_contract": candidate["max_loss_per_contract"],
            "target_return": rep["baseline_return"],
            "breakeven": candidate["breakeven"],
            "consensus": consensus_summary(item),
            "scenario": scenario,
        })
    return rows


_SORT_KEYS = {
    # 目標價情境報酬由高到低（同既有 Scenario Bet Ranking 口徑）。
    "return": lambda r: -r["target_return"],
    "cost": lambda r: r["entry_cost"],
    "max_loss": lambda r: r["max_loss_per_contract"],
}


def sort_rows(rows: list[dict], sort: str) -> list[dict]:
    """依既有欄位排序；同值依 (symbol, family) 保持決定性。"""
    return sorted(rows, key=lambda r: (_SORT_KEYS[sort](r), r["symbol"], r["family"]))
