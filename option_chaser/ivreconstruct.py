"""Historical IV reconstruction：raw quote series → reconstructed IV series
（HIVR-05／#164，spec #159）。

**canonical series 的產生方式**：這裡是唯一會產生它的地方。輸入是
`option_chaser/data/marketdata.py::fetch_contract_history()`（HIVR-04／
#163）回傳的寬版 quote dict 序列——`date`／`updated`／`dte`／`bid`／
`ask`／`mid`／`underlying_price`／`vendor_iv`；輸出是重新反解出來的
`(date, iv)` 序列，形狀跟 `ivtrend.py` 既有統計函式吃的輸入**完全相同**
——`moving_average`／`bollinger_bands`／`current_zscore`／
`historical_percentile`／`delta_4w` 因此一行都不用改，只是原料換了。

**`vendor_iv` 永遠不進 canonical series，即使該筆非 null**——這是「全期間
同一把尺」的紅線（spec #159 §2）：混用 vendor 給的與自己反解的 IV，會讓
「方法論切換」被誤讀成「市場變動」。`vendor_iv` 只在別的地方（#168 的
benchmark／診斷路徑）派上用場，這個模組完全不讀它。

Recipe（已由 `docs/research/historical-iv-reconstruction-corrected-
calibration-results.md` 578 筆真實觀測驗證，verdict STRONG_PASS）：

- price：vendor `mid`；缺席時退回 `(bid+ask)/2`。**絕不用 last**
  （HIVR-04 的寬版 quote dict 結構上根本沒有 `last` 欄位，這條紅線因此
  是結構性保證，不只是這裡的邏輯）
- quote 合法性：`bid`／`ask` 皆存在、皆為正、未倒掛（`ask >= bid`）。
  不合法就是缺席觀測，**不論 vendor 的 `mid` 是否剛好存在**——crossed
  quote 是資料品質訊號，不能因為另一個欄位看似可用就繞過
- `S`：同一筆觀測自己的 `underlying_price`（跟 price 同一個時刻）
- `T`：`days_between(該筆觀測日, expiration) / DAYS_PER_YEAR`（既有
  day-count 常數，不引入新慣例）；`T<=0` 讓 `implied_vol()` 自然回
  `None`，不在這裡另外分類
- `r`／`q`：呼叫端逐筆觀測日算好、以 `{date: value}` 傳入——**這個模組
  不抓取**（#160／#161 是產生這兩個 mapping 的地方，不是這裡）
- model：既有 `valuation.implied_vol()`（BS93／Bjerksund-Stensland
  1993 反解）。不重選、不引入新模型

**失敗即缺席，絕不外插、絕不用鄰近點頂替、絕不換合約、絕不退回
`vendor_iv`**——任一筆觀測的必要輸入缺席、或反解無解，那一筆的輸出就是
`(date, None)`，不影響其他筆。四種失敗原因（詳見下方常數）逐一計數，
供呼叫端組出「vendor 回 N 筆，究竟卡在哪一站」的帳本（#166）。

純函式：無 I/O、無 wall-clock、無全域狀態——跟 `ivtrend.py` 同一套
紀律。物理上不 import `ivhistory.py`（spec #151 §0／§7 隔離紅線的延伸：
exact-contract 家族不吃 (tenor,delta) 重錨定家族的任何程式碼路徑）。
"""
from __future__ import annotations

from datetime import date

from .valuation import DAYS_PER_YEAR, days_between, implied_vol

# 四種失敗原因（spec #159／issue #164 逐字列出的分類，不多不少）——
# named constants 而非隨手字串，避免呼叫端與這裡各自維護一份可能漂移
# 的拼法。
FAILURE_UNUSABLE_QUOTE = "unusable_quote"
FAILURE_NO_RATE = "no_rate"
FAILURE_NO_DIVIDEND_YIELD = "no_dividend_yield"
FAILURE_INVERSION_FAILED = "inversion_failed"

FAILURE_REASONS = (FAILURE_UNUSABLE_QUOTE, FAILURE_NO_RATE,
                   FAILURE_NO_DIVIDEND_YIELD, FAILURE_INVERSION_FAILED)

# HIVR-08（#167）：近到期反解病態的門檻——單一具名常數，不是散落各處
# 的字面值。依 calibration 文件實測：3-DTE 深度價內合約，1 分錢報價
# 誤差可讓反解 IV 移動 3.5–9 個 vol 點，時間價值 <$0.10 組的殘差是
# ≥$0.10 組的 14 倍。這只是資訊品質標記——不刪點、不改統計、不影響
# ranking／filtering／candidate selection（那些路徑本來就不 import
# 這個模組，見下方 `test_ranking_and_filters_do_not_depend_on_this_
# module`）。
LOW_CONFIDENCE_DTE_THRESHOLD = 14


def is_low_confidence(observation_date: str, expiration: str) -> bool:
    """`observation_date` 距 `expiration` 少於
    `LOW_CONFIDENCE_DTE_THRESHOLD` 天＝True。純粹的天數比較，不讀取
    price／IV，因此對任一觀測日皆可呼叫（含反解失敗、`iv` 為 `None`
    的缺席觀測）。"""
    dte = days_between(date.fromisoformat(observation_date),
                       date.fromisoformat(expiration))
    return dte < LOW_CONFIDENCE_DTE_THRESHOLD


def _quote_price(quote: dict) -> float | None:
    """price 優先序：vendor `mid` → `(bid+ask)/2` 退回。兩者皆不可得回
    `None`。HIVR-04 的 `_num()` 缺值口徑已經在解析層把非正值收斂成
    `None`，這裡不必重新驗證 `mid` 本身的正負號。"""
    mid = quote.get("mid")
    if mid is not None:
        return mid
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2.0


def _quote_is_valid(quote: dict) -> bool:
    """quote 合法性：`bid`／`ask` 皆存在、皆為正、未倒掛。獨立於 price
    是否能算出來——crossed quote 即使剛好有 vendor `mid` 也不採信。"""
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is None or ask is None:
        return False
    return bid > 0.0 and ask > 0.0 and ask >= bid


def reconstruct_iv_series(
    option_type: str, strike: float, expiration: str, quotes: list[dict],
    rate_by_date: dict[str, float | None],
    dividend_yield_by_date: dict[str, float | None],
) -> tuple[list[tuple[str, float | None]], dict[str, int]]:
    """一張 exact contract 的寬版 quote 序列 → `(date, iv)` 序列 ＋
    逐原因失敗計數。

    `option_type`／`strike`／`expiration` 是這張合約本身固定不變的身分
    （單一合約的一整段序列共用同一組），不隨觀測日改變——跟 `quotes`
    裡逐筆變動的欄位（`date`／`bid`／`ask`／`mid`／`underlying_price`）
    刻意分開。

    `rate_by_date`／`dividend_yield_by_date`：呼叫端逐一觀測日算好的
    point-in-time r／q（#160／#161 的產出），鍵是 `quote["date"]` 同一個
    ISO 日期字串。缺這把鑰匙或值本身是 `None`，效果相同——那筆觀測記成
    `no_rate`／`no_dividend_yield`，不當 KeyError 處理。

    輸出序列與輸入 `quotes` **逐筆一一對應**（一筆壞觀測只讓那一筆的
    輸出是 `(date, None)`，不影響其他筆，也不改變輸出筆數）；順序與
    輸入順序一致，不預先排序（呼叫端已排序時不會被打亂，`ivtrend.py`
    的既有函式本來就不要求輸入已排序）。
    """
    exp_date = date.fromisoformat(expiration)
    series: list[tuple[str, float | None]] = []
    failure_counts: dict[str, int] = {}

    def _fail(reason: str) -> None:
        failure_counts[reason] = failure_counts.get(reason, 0) + 1

    for quote in quotes:
        d = quote["date"]
        spot = quote.get("underlying_price")
        if not _quote_is_valid(quote) or spot is None:
            _fail(FAILURE_UNUSABLE_QUOTE)
            series.append((d, None))
            continue
        price = _quote_price(quote)
        if price is None:
            _fail(FAILURE_UNUSABLE_QUOTE)
            series.append((d, None))
            continue

        r = rate_by_date.get(d)
        if r is None:
            _fail(FAILURE_NO_RATE)
            series.append((d, None))
            continue
        q = dividend_yield_by_date.get(d)
        if q is None:
            _fail(FAILURE_NO_DIVIDEND_YIELD)
            series.append((d, None))
            continue

        T = days_between(date.fromisoformat(d), exp_date) / DAYS_PER_YEAR
        iv = implied_vol(option_type, price, spot, strike, T, r, q)
        if iv is None:
            _fail(FAILURE_INVERSION_FAILED)
            series.append((d, None))
            continue
        series.append((d, iv))

    return series, failure_counts
