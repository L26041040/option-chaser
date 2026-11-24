"""目前股價、報價日期與目標漲跌幅（V2-05／#407，母票 #389）。

**股價來自股票掃描階段**（分析師共識更新）：`YahooAnalystSource` 本來就為了
分割日曆與週線收盤抓 chart 端點，它回應的 `meta.regularMarketPrice`／
`regularMarketTime` 順手帶出來，**不多打任何上游**；選擇權搜尋帶回的 spot
不拿來當這個數字。更新時以 `quote_record()` 跟共識 Snapshot 一起存（快照
JSON 的 `quote` 鍵，additive），清單／詳細／搜尋結果讀取時以
`upside_fields()` 產生畫面欄位。

口徑：
- 目標漲跌幅 = (平均目標價 ÷ 目前股價 − 1) × 100，`Decimal` 計算、
  **四捨五入到小數一位（整好一半時遠離零，ROUND_HALF_UP）**，不會出現 `-0.0`。
- **分割基準**：平均目標價是共識資料日（`as_of`）的分割基準（引擎把
  `effective_on ≤ as_of` 的分割都換算進去）；Yahoo 的 `regularMarketPrice`
  是報價當下的實際成交價，只反映 `effective_on ≤ 報價日` 的分割。兩個日期之間
  （較早的不含、較晚的含）如果有分割，兩個數字基準不同——**不換算、不相除**，
  回報 `split_mismatch`（畫面「分割基準不一致，暫不計算」）。不換算是因為
  分割生效當天盤前 Yahoo 的 meta 價是否已調整無從確認，猜錯就會算出十倍的數字。
- **股價過舊**：報價日之後到「今天」（美東）已經過了超過
  `STALE_AFTER_TRADING_DAYS`（3）個交易日 → 不算漲跌幅（`price_stale`），
  股價與日期照實顯示。交易日只排除週末（本站不維護美股假日曆，與
  `consensus_cache.trading_day()` 同一套）；假日因此會被多算一天，只會讓
  「過舊」提早出現，不會把舊價格當成新的。3 天＝容得下週末＋一次更新失敗：
  每日更新在美東盤前跑，正常情況報價是前一個交易日的收盤（距離 1）。
- 缺資料原因（依序判斷，第一個成立的回報）：`no_price`（尚未取得股價）、
  `no_mean`（沒有平均目標價）、`split_mismatch`、`price_stale`。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

from option_chaser.consensus import SplitEvent

STALE_AFTER_TRADING_DAYS = 3
REASONS = ("no_price", "no_mean", "split_mismatch", "price_stale")
_NY = ZoneInfo("America/New_York")
_SESSION_CLOSE = time(16, 0)
_ONE_DECIMAL = Decimal("0.1")


@dataclass(frozen=True)
class PriceQuote:
    """一檔股票的最新成交價與它的時間（時區感知）。"""

    price: Decimal
    at: datetime


def target_upside_pct(mean: Decimal, price: Decimal) -> Decimal:
    """(mean ÷ price − 1) × 100，四捨五入到小數一位（一半遠離零）。"""
    pct = ((mean / price) - 1) * 100
    rounded = pct.quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
    return rounded.copy_abs() if rounded.is_zero() else rounded


def trading_days_after(earlier: date, later: date) -> int:
    """`earlier` 之後、到 `later`（含）為止的平日數；週末不算。"""
    days, d = 0, earlier + timedelta(days=1)
    while d <= later:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def _split_between(splits: Iterable[SplitEvent], a: date, b: date) -> bool:
    lo, hi = min(a, b), max(a, b)
    return any(lo < s.effective_on <= hi for s in splits)


def quote_record(quote: PriceQuote | None, splits: Iterable[SplitEvent],
                 as_of: date) -> dict | None:
    """存進共識快照的報價（Decimal 存字串）。`as_of`＝這次更新的資料日（美東，
    也就是抓取日）。報價日早於抓取日、或時間已過 16:00 美東 → 那天的收盤；
    否則是盤中價。"""
    if quote is None:
        return None
    local = quote.at.astimezone(_NY)
    on = local.date()
    kind = "close" if on < as_of or local.time() >= _SESSION_CLOSE else "intraday"
    return {"price": str(quote.price),
            "at": quote.at.astimezone(timezone.utc).isoformat(),
            "date": on.isoformat(), "kind": kind,
            "split_basis_mismatch": _split_between(splits, on, as_of)}


def upside_fields(quote: dict | None, mean: Decimal | None, today: date) -> dict:
    """清單／詳細／搜尋結果共用的股價欄位。缺資料時數字一律 `None`，
    `target_upside_reason` 寫原因代碼（`REASONS`）。"""
    out = {"price": None, "price_date": None, "price_at": None, "price_kind": None,
           "target_upside_pct": None, "target_upside_reason": None}
    if quote is None:
        out["target_upside_reason"] = "no_price"
        return out
    price = Decimal(quote["price"])
    out.update(price=float(price), price_date=quote["date"],
               price_at=quote["at"], price_kind=quote["kind"])
    if mean is None:
        reason = "no_mean"
    elif quote.get("split_basis_mismatch"):
        reason = "split_mismatch"
    elif trading_days_after(date.fromisoformat(quote["date"]), today) > STALE_AFTER_TRADING_DAYS:
        reason = "price_stale"
    else:
        out["target_upside_pct"] = float(target_upside_pct(mean, price))
        return out
    out["target_upside_reason"] = reason
    return out
