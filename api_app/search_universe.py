"""Search Universe 登錄表（OS-02／#391，母票 #389 §6）。

「這位使用者要在哪些股票裡找機會」的唯一答案來源。後續票（共識清單、
搜尋）只呼叫 `resolve_universe()`，不自己讀 settings 裡的鍵、也不自己
維護任何 ticker 清單——清單寫兩份遲早會漂移。

兩種母體：

- `sample-large-cap`：約 50 檔知名美國大型股的**靜態**清單。這**不是**
  任何指數的成分股，正式清單來源待 #382 決策（也必須 US$0）；在那之前
  一律標示「暫定」，文案絕不稱為 S&P 500——有測試守門。
- `custom`：使用者自訂清單（最多 `CUSTOM_SYMBOLS_MAX` 檔），驗證與正規化
  在 `api_app/opportunity_settings.py`，這裡只負責照順序交出去。
"""
from __future__ import annotations

import re
from typing import Mapping, NamedTuple

SAMPLE_LARGE_CAP = "sample-large-cap"
CUSTOM = "custom"
UNIVERSE_IDS = (SAMPLE_LARGE_CAP, CUSTOM)
DEFAULT_UNIVERSE_ID = SAMPLE_LARGE_CAP

CUSTOM_SYMBOLS_MAX = 50

# 與 `api_app/main.py::_SYMBOL` 同一組字元（symbol 會被代入資料源的 URL），
# 但這裡要求**已經是大寫**、且以字母開頭——存進設定的是正規化後的值，
# 大小寫轉換由前端在送出前做，後端不替使用者猜。
_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")

_SAMPLE_LARGE_CAP_LABEL = "大型股樣本（暫定，清單來源待 #382）"
_CUSTOM_LABEL = "自訂清單"

# 靜態、依名稱熟悉度挑的樣本，不代表任何排名或指數權重。#382 決定正式
# 來源後整份換掉，不在這裡逐檔增刪。
_SAMPLE_LARGE_CAP_SYMBOLS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "LLY",
    "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV", "MRK",
    "WMT", "NFLX", "CRM", "BAC", "KO", "PEP", "ORCL", "CVX", "ADBE", "AMD",
    "TMO", "CSCO", "MCD", "ABT", "DIS", "WFC", "INTC", "QCOM", "TXN", "IBM",
    "CAT", "GS", "NKE", "AMGN", "HON", "PFE", "UNP", "LOW", "SBUX", "BA",
)


class ResolvedUniverse(NamedTuple):
    """`resolve_universe()` 的回傳值；可直接拆成
    `(id, label, provisional, symbols)`。`provisional` 為真表示清單來源
    尚未定案，畫面必須照實標示。"""
    id: str
    label: str
    provisional: bool
    symbols: tuple[str, ...]


def is_valid_ticker(symbol: object) -> bool:
    return isinstance(symbol, str) and _TICKER_RE.fullmatch(symbol) is not None


def resolve_universe(settings: Mapping | None) -> ResolvedUniverse:
    """依使用者的 `opportunity_search` 設定（已正規化的 dict，或 `None`
    ＝未設定）決定搜尋母體。

    自訂清單**只在**選 `custom` 時使用；選樣本時就算 settings 裡還留著
    上次的自訂清單也不拿來搜（切回 custom 時清單仍在）。"""
    universe_id = (settings or {}).get("universe_id", DEFAULT_UNIVERSE_ID)
    if universe_id == CUSTOM:
        symbols = tuple((settings or {}).get("custom_symbols") or ())
        return ResolvedUniverse(CUSTOM, _CUSTOM_LABEL, False, symbols)
    return ResolvedUniverse(SAMPLE_LARGE_CAP, _SAMPLE_LARGE_CAP_LABEL, True,
                            _SAMPLE_LARGE_CAP_SYMBOLS)


def universe_options() -> list[dict]:
    """設定頁的母體選項（顯示文字由後端給，前端不自己寫一份）。
    `symbol_count` 對 custom 而言沒有固定值，回 `None`。"""
    return [
        {"id": SAMPLE_LARGE_CAP, "label": _SAMPLE_LARGE_CAP_LABEL,
         "provisional": True, "symbol_count": len(_SAMPLE_LARGE_CAP_SYMBOLS)},
        {"id": CUSTOM, "label": _CUSTOM_LABEL, "provisional": False,
         "symbol_count": None},
    ]
