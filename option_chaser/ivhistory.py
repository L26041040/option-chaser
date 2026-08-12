"""(tenor, delta) 座標上的 IV 重錨定與相對位置（#126／#114）。

**為什麼要重錨定**：一張固定合約的 IV 序列，意義會隨合約變老而漂移
——今天的 90 天 25-delta，三個月後變成 0 天的深價外，兩者的 IV 不是
同一種東西，畫在同一條線上是誤導。所以歷史序列不是「這張合約過去的
IV」，而是「過去每一天，那天的鏈上與今天這個候選**同樣座標**的那個
IV 是多少」。

**紅線（spec #117 §5）**：這個模組只做 enrichment。本檔案是純函式，
不碰排序、不碰過濾、不碰候選選取——`ranking.py`／`filters.py` 都不
import 它，#118 的選取身份回歸守門因此在結構上就不可能被它影響。

**不外插**：座標落在當日資料的網格之外時回 `None`，呼叫端據此標成
「超出可比網格」。刻意不拿最近的一格頂替——那會讓一個其實沒有可比
基準的數字看起來跟其他日子一樣可信。
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass


@dataclass(frozen=True)
class SurfacePoint:
    """某一天的鏈上，一個合約的座標與 IV。

    `dte` ＝距到期天數（tenor），`delta` 取絕對值（呼叫端負責只餵同一
    種權別進來，call 與 put 的 delta 不可混在同一個網格裡插值）。
    """
    dte: int
    delta: float
    iv: float


def _interp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """兩點線性插值。x0 == x1 時退化成 y0（呼叫端已確保 x 落在兩者之間）。"""
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _iv_at_delta(points: list[SurfacePoint], delta: float) -> float | None:
    """同一個 tenor 上，沿 delta 軸插出目標 delta 的 IV。

    需要**左右都有**資料點才插——只有單邊就是外插，回 `None`。
    """
    if not points:
        return None
    ordered = sorted(points, key=lambda p: p.delta)
    deltas = [p.delta for p in ordered]
    if delta < deltas[0] or delta > deltas[-1]:
        return None
    i = bisect_left(deltas, delta)
    if i < len(deltas) and deltas[i] == delta:
        return ordered[i].iv
    lo, hi = ordered[i - 1], ordered[i]
    return _interp(delta, lo.delta, lo.iv, hi.delta, hi.iv)


def iv_at(points: list[SurfacePoint], *, tenor_days: int,
          delta: float) -> float | None:
    """某一天的鏈上，(tenor, delta) 這個座標的 IV。

    兩軸都要求在網格**之內**（左右各有資料），任一軸落在外面就回
    `None`——這正是「超出可比網格」那個狀態，不外插也不拿最長天期頂替。
    """
    if not points:
        return None
    by_tenor: dict[int, list[SurfacePoint]] = {}
    for p in points:
        by_tenor.setdefault(p.dte, []).append(p)

    tenors = sorted(by_tenor)
    if tenor_days < tenors[0] or tenor_days > tenors[-1]:
        return None

    if tenor_days in by_tenor:
        return _iv_at_delta(by_tenor[tenor_days], delta)

    i = bisect_left(tenors, tenor_days)
    lo_t, hi_t = tenors[i - 1], tenors[i]
    lo_iv = _iv_at_delta(by_tenor[lo_t], delta)
    hi_iv = _iv_at_delta(by_tenor[hi_t], delta)
    # 任一端在 delta 軸上就已經出界時，這個座標沒有完整的四角可插——
    # 用單邊硬湊出一個值等於偷偷外插。
    if lo_iv is None or hi_iv is None:
        return None
    return _interp(tenor_days, lo_t, lo_iv, hi_t, hi_iv)


# ATM 的操作型定義：|delta| ≈ 0.5。用 delta 而不是「履約價最接近現價」
# ——整個模組都活在 (tenor, delta) 座標系裡，換一套座標定義 ATM 會讓
# 分母與分子量的不是同一個東西。
ATM_DELTA = 0.5


def normalized_skew(*, sell_iv: float | None, buy_iv: float | None,
                    atm_iv: float | None) -> float | None:
    """賣腿 IV 減買腿 IV，除以當日 ATM 水準（#114 的頭條數字）。

    除以 ATM 是為了讓不同時期可比：整體波動抬高時，兩腿的絕對價差會
    跟著放大，但那不代表 skew 變陡。任一項缺值或 ATM 為零就回 `None`
    ——湊不出來就說湊不出來。
    """
    if sell_iv is None or buy_iv is None or not atm_iv:
        return None
    return (sell_iv - buy_iv) / atm_iv


def percentile(series: list[float], value: float) -> float | None:
    """`value` 在 `series` 裡的百分位（0–1）。

    用「小於等於的比例」，含等於——這樣一組全同值的序列會回 1.0 而不是
    0.0，而後者會把「跟過去一樣」說成「處於歷史最低」。空序列回 `None`。
    """
    if not series:
        return None
    return sum(1 for x in series if x <= value) / len(series)


@dataclass(frozen=True)
class Coordinate:
    """一條腿在 (tenor, delta) 座標系上的位置。"""
    tenor_days: int
    delta: float


def leg_coordinate(*, option_type: str, strike: float, iv: float | None,
                   spot: float, days_to_expiry: int, rate: float = 0.0,
                   q: float = 0.0) -> Coordinate | None:
    """一條腿現在落在哪個 (tenor, delta) 座標。

    delta 由既有的 `valuation.call_greeks` 算（put 用 call-put parity：
    |Δ_put| = 1 - Δ_call，取絕對值後與 call 的網格同一種量），**不另外
    實作一份 Black-Scholes**——多一份就多一個會跟主路徑漂移的來源。

    缺 IV、天期非正、履約價或現價非正時回 `None`：算不出座標就沒有這
    條腿的歷史序列可言，不硬湊一個。
    """
    if not iv or days_to_expiry <= 0 or strike <= 0 or spot <= 0:
        return None
    from .valuation import DAYS_PER_YEAR, call_greeks

    delta = call_greeks(spot, strike, days_to_expiry / DAYS_PER_YEAR, rate,
                        iv, q).delta
    if option_type == "put":
        delta = 1.0 - delta
    return Coordinate(tenor_days=days_to_expiry, delta=abs(delta))


def trading_days_back(today, window_days: int) -> list[str]:
    """從今天往回數 `window_days` 個曆日，濾掉週末，回 ISO 日期（由舊到新）。

    只濾週末、不處理美股假日：多打幾天假日的代價是那幾天回空（呼叫端
    當斷點處理），比內建一份會過期的假日表可靠。**今天不含**——當日的
    EOD 資料通常還沒結算，拿到的會是半天的東西。
    """
    from datetime import timedelta

    out = []
    for back in range(window_days, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() < 5:
            out.append(day.isoformat())
    return out


def spread_coordinates(candidate: dict, *, spot: float) -> dict | None:
    """候選的兩條腿各自的 (tenor, delta) 座標。

    以 view dict 裡那一份腿資料為準（`iv`／`strike`／`option_type`／
    `expiry`），不重新去快照裡找——同一個候選在同一份 view 裡只能有一組
    座標，兩處各算一次遲早會漂。

    買腿＝先出現的那條（引擎既有慣例，`legs[0]` 是買腿）。任一腿算不出
    座標就整組回 `None`：skew 是兩腿之差，缺一邊就沒有那個數字。
    """
    legs = candidate.get("legs") or []
    if len(legs) < 2:
        return None   # 單腳沒有 skew 可言（MVP 範圍限 Spread）
    dte = candidate.get("days_to_expiry")
    if not dte:
        return None

    buy, sell = legs[0], legs[1]
    coords = {}
    for name, leg in (("buy", buy), ("sell", sell)):
        got = leg_coordinate(option_type=leg.get("option_type", "call"),
                             strike=leg.get("strike", 0.0), iv=leg.get("iv"),
                             spot=spot, days_to_expiry=int(dte))
        if got is None:
            return None
        coords[name] = got
    return coords


def reanchor_spread(surface: dict, coords: dict) -> dict:
    """某一天的鏈上，兩腿座標與 ATM 各自的 IV，以及當日的 normalized skew。

    `surface` 是 `{"call": [SurfacePoint], "put": [...]}`。權別取買腿那一
    種——同一組 spread 的兩腿權別相同（MVP 只有 bull call spread），
    call 與 put 的 delta 網格不可混插。
    """
    points = surface.get("call") or []
    tenor = coords["buy"].tenor_days
    buy_iv = iv_at(points, tenor_days=tenor, delta=coords["buy"].delta)
    sell_iv = iv_at(points, tenor_days=tenor, delta=coords["sell"].delta)
    atm = iv_at(points, tenor_days=tenor, delta=ATM_DELTA)
    return {"buy_iv": buy_iv, "sell_iv": sell_iv, "atm_iv": atm,
            "normalized_skew": normalized_skew(sell_iv=sell_iv, buy_iv=buy_iv,
                                               atm_iv=atm)}


def percentiles_of(points: list[dict]) -> dict:
    """序列最後一筆在整段歷史裡的百分位，逐項算。

    出界（`None`）的日子不進母體——把它們當成某個數值會污染分位數；
    整段都出界時該項回 `None`（＝「超出可比網格」，呼叫端據此留白）。
    """
    out: dict[str, float | None] = {}
    for field in ("normalized_skew", "buy_iv", "sell_iv", "atm_iv"):
        series = [p[field] for p in points if p.get(field) is not None]
        latest = next((p[field] for p in reversed(points)
                       if p.get(field) is not None), None)
        out[field] = percentile(series, latest) if latest is not None else None
    return out
