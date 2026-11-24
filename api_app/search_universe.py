"""掃描股票範圍（Search Universe）登錄表（OS-02／#391 → V2-01／#404，母票 #389 §6）。

「這位使用者要在哪些股票裡找機會」的唯一答案來源。後續票（共識清單、
搜尋）只呼叫 `resolve_universe()`，不自己讀 settings 裡的鍵、也不自己
維護任何 ticker 清單——清單寫兩份遲早會漂移。

兩種範圍：

- `sp500`（**預設**）：S&P 500 成分股，約 503 檔（GOOGL／GOOG、BRK.B、
  BF.B 等多股權類別各自一檔）。清單是 repo 內帶版本日期的
  `api_app/sp500_constituents.py`（來源 Wikipedia，CC BY-SA 4.0），由
  `scripts/update_sp500_constituents.py` 手動更新；執行期不連網。
- `custom`：使用者自訂清單（最多 `CUSTOM_SYMBOLS_MAX` 檔），驗證與正規化
  在 `api_app/opportunity_settings.py`，這裡只負責照順序交出去。

舊的「大型股樣本」（`sample-large-cap`，約 50 檔暫定清單）已退役：存著這個
值的舊設定一律讀成 `sp500`（`normalize_universe_id()`），不會壞。那 50 檔
改當 `REFRESH_PRIORITY`——每日更新母體超過上限時一定保留的那一批（只影響
截斷，不影響每次先抓誰；見常數註解）。

代號一律 canonical 點寫法（`BRK.B`），各資料來源的寫法由
`option_chaser.symbols` 轉換。
"""
from __future__ import annotations

import re
from typing import Mapping, NamedTuple

from option_chaser.symbols import canonical_symbol

from . import sp500_constituents

SP500 = "sp500"
CUSTOM = "custom"
UNIVERSE_IDS = (SP500, CUSTOM)
DEFAULT_UNIVERSE_ID = SP500
# 已退役的大型股樣本：只在讀舊設定／舊前端送來時認得，一律換成預設。
LEGACY_SAMPLE_LARGE_CAP = "sample-large-cap"

CUSTOM_SYMBOLS_MAX = 50

# 與 `api_app/main.py::_SYMBOL` 同一組字元（symbol 會被代入資料源的 URL），
# 但這裡要求**已經是 canonical**（大寫、點寫法）、且以字母開頭——檢查的是
# 存進設定的值。使用者輸入的大小寫、`BRK-B`／`brk/b` 由後端先以
# `option_chaser.symbols.canonical_symbol()` 正規化，再用這條規則驗證
# （`opportunity_settings`，#404）。
_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")

_SP500_LABEL = "S&P 500 成分股"
_CUSTOM_LABEL = "自訂清單"

SP500_SYMBOLS: tuple[str, ...] = tuple(s for s, _ in sp500_constituents.CONSTITUENTS)
SP500_VERSION: str = sp500_constituents.VERSION

# 每日更新母體超過上限（`consensus_cache.DEFAULT_REFRESH_SYMBOL_CAP`）時**一定
# 留在範圍內**的大型股（原「大型股樣本」，依名稱熟悉度挑，不代表排名或權重；
# 全部是 S&P 500 成分股，有測試守門）。#403 之後它不再決定每次先抓誰（那由
# 公平輪替 `consensus_cache.rotation_key()` 決定），只決定截斷時的保留順序：
# 這 50 檔 → 自訂清單 → 其餘成分股。預設上限 600 容得下整份成分股時，它不影響
# 任何結果；上限被調低時才會用到。
REFRESH_PRIORITY: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "LLY",
    "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV", "MRK",
    "WMT", "NFLX", "CRM", "BAC", "KO", "PEP", "ORCL", "CVX", "ADBE", "AMD",
    "TMO", "CSCO", "MCD", "ABT", "DIS", "WFC", "INTC", "QCOM", "TXN", "IBM",
    "CAT", "GS", "NKE", "AMGN", "HON", "PFE", "UNP", "LOW", "SBUX", "BA",
)


class ResolvedUniverse(NamedTuple):
    """`resolve_universe()` 的回傳值。`provisional` 為真表示清單來源
    尚未定案，畫面必須照實標示（目前兩種範圍都不是暫定）。
    `version_date`：清單版本日期（S&P 500 成分股）；自訂清單為 `None`。"""
    id: str
    label: str
    provisional: bool
    symbols: tuple[str, ...]
    version_date: str | None = None


def is_valid_ticker(symbol: object) -> bool:
    return isinstance(symbol, str) and _TICKER_RE.fullmatch(symbol) is not None


def normalize_universe_id(universe_id: object) -> str:
    """舊值（`sample-large-cap`）、不認得的值一律換成預設 `sp500`。"""
    return universe_id if universe_id in UNIVERSE_IDS else DEFAULT_UNIVERSE_ID


def canonical_symbols(symbols) -> tuple[str, ...]:
    """canonical 化並去重（保留順序）：舊設定裡的 `BRK-B` 與 `BRK.B` 是同一檔。"""
    return tuple(dict.fromkeys(canonical_symbol(s) for s in symbols))


def resolve_universe(settings: Mapping | None) -> ResolvedUniverse:
    """依使用者的 `opportunity_search` 設定（已正規化的 dict，或 `None`
    ＝未設定）決定掃描股票範圍。

    自訂清單**只在**選 `custom` 時使用；選 S&P 500 時就算 settings 裡還留著
    上次的自訂清單也不拿來搜（切回 custom 時清單仍在）。"""
    universe_id = normalize_universe_id((settings or {}).get("universe_id"))
    if universe_id == CUSTOM:
        symbols = canonical_symbols((settings or {}).get("custom_symbols") or ())
        return ResolvedUniverse(CUSTOM, _CUSTOM_LABEL, False, symbols)
    return ResolvedUniverse(SP500, _SP500_LABEL, False, SP500_SYMBOLS, SP500_VERSION)


def universe_options() -> list[dict]:
    """設定頁的範圍選項（顯示文字由後端給，前端不自己寫一份）。
    `symbol_count`／`version_date` 對 custom 而言沒有固定值，回 `None`。"""
    return [
        {"id": SP500, "label": _SP500_LABEL, "provisional": False,
         "symbol_count": len(SP500_SYMBOLS), "version_date": SP500_VERSION},
        {"id": CUSTOM, "label": _CUSTOM_LABEL, "provisional": False,
         "symbol_count": None, "version_date": None},
    ]
