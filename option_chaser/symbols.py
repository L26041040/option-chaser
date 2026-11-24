"""股權類別代號的唯一對照規則（V2-01／#404）。

S&P 500 有幾家公司掛兩種股權類別（GOOGL／GOOG、BRK.B、BF.B……），各來源
寫法不同：

| 用途 | 寫法 | 例 |
|---|---|---|
| **canonical**（設定、共識快取、劇本、搜尋結果、成分股清單） | 點 | `BRK.B` |
| Cboe 延遲報價 | 點（canonical 原樣） | `BRK.B` |
| Yahoo（quoteSummary／chart／options、yfinance） | 連字號 | `BRK-B` |

規則：系統內部只存 canonical；**只有組上游 URL 的那一刻**才換成該來源的
寫法（`yahoo_symbol()`／`cboe_symbol()`），回傳的資料一律掛回 canonical。
使用者輸入 `BRK-B`、`brk/b` 也一律正規化成 `BRK.B`，同一檔股票只有一個
鍵。GOOGL 與 GOOG 是兩檔不同的股票，各自保留。

範圍：美國掛牌普通股（本系統只處理美股選擇權）。Yahoo 對非美國交易所用
`.T`、`.DE` 這類後綴，不在支援範圍內。
"""
from __future__ import annotations

_CLASS_SEPARATORS = ("-", "/")


def canonical_symbol(raw: str) -> str:
    """去頭尾空白、轉大寫，股權類別分隔符一律改成 `.`。"""
    out = raw.strip().upper()
    for sep in _CLASS_SEPARATORS:
        out = out.replace(sep, ".")
    return out


def yahoo_symbol(symbol: str) -> str:
    """Yahoo（含 yfinance）的寫法：`BRK.B` → `BRK-B`。"""
    return canonical_symbol(symbol).replace(".", "-")


def cboe_symbol(symbol: str) -> str:
    """Cboe 延遲報價的寫法：與 canonical 相同（`BRK.B`）。"""
    return canonical_symbol(symbol)
