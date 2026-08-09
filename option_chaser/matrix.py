"""Price×date P/L matrix engine (spec §5). Pure functions, deterministic."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable


def _insert_anchors(pts: list[float], anchors: list[float]) -> list[float]:
    """Spec §5.1: per-anchor remove nearest unremoved grid point, then insert anchors."""
    removed: set[int] = set()
    for a in anchors:
        best = min(
            (abs(pts[i] - a), i) for i in range(len(pts)) if i not in removed
        )[1]
        removed.add(best)
    vals = [p for i, p in enumerate(pts) if i not in removed] + list(anchors)
    vals.sort()
    return vals


def price_axis(
    spot: float, target: float, bullish: bool,
) -> list[tuple[float, str, float]]:
    """v4 spec §4.3: anchors {spot, target, overshoot, adverse}; range = anchor hull.

    決策 M（#109）：第三個元素 `move_pct` 是該價位相對 `spot` 的變動分數
    （`<現價>` 那一列恆為 0）——跟 cell 的估值同一個 `spot`、同一次呼叫算出來，
    不是另外重算的第二份數字。GUI 只格式化顯示。
    """
    overshoot = target * (1.15 if bullish else 0.85)
    adverse = spot * (0.90 if bullish else 1.10)
    anchors = sorted({spot, target, overshoot, adverse})
    lo = max(min(anchors), 0.01 * spot)
    hi = max(anchors)
    pts = [lo + (hi - lo) * i / 10.0 for i in range(11)]
    vals = _insert_anchors(pts, anchors)

    def label(v: float) -> str:
        s = ""
        if v == spot:
            s += "<現價>"
        if v == target:
            s += "<目標>"
        if v == overshoot:
            s += "<超標>"
        if v == adverse:
            s += "<深跌>"
        return s

    return [(v, label(v), (v - spot) / spot) for v in vals]


def date_axis(today: date, expiry: date) -> list[tuple[date, str]]:
    """日期軸＝今天 → 該合約自身的到期日，等分至多七欄。

    附錄 A2.3：年月語意下不存在「目標日」那一欄，原本的「*」標記連同它所需的
    日期映射一併移除。標籤欄保留（恆為空字串）以維持與價格軸相同的欄位形狀。
    """
    total = (expiry - today).days
    pts = [today + timedelta(days=round(total * i / 6.0)) for i in range(7)]
    pts[-1] = expiry
    return [(d, "") for d in sorted(set(pts))]


def matrix_grid(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str, float]], dates: list[tuple[date, str]],
) -> tuple[tuple[float, ...], ...]:
    """Structured cell returns (v3 spec §2.3): single data source for CLI and GUI."""
    return tuple(
        tuple((value_fn(price, d) - cost) / cost for d, _ in dates)
        for price, _, _ in prices
    )


def matrix_lines(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str, float]], dates: list[tuple[date, str]],
) -> list[str]:
    """CLI 文字報告——不印 `move_pct`（#109 只加 GUI 右側標註，文字報告
    的價格列格式維持既有樣子，golden fixtures 不因此漂移）。"""
    grid = matrix_grid(value_fn, cost, prices, dates)
    header = "價格".ljust(10) + " ".join(
        (d.strftime("%m/%d") + lbl).rjust(7) for d, lbl in dates
    )
    lines = [header]
    for i in range(len(prices) - 1, -1, -1):
        price, plabel, _ = prices[i]
        cells = [f"{grid[i][j] * 100:+.0f}%".rjust(7) for j in range(len(dates))]
        lines.append(f"{price:8.2f}{plabel}".ljust(10) + " ".join(cells))
    return lines


def thumbnail_cells(
    cells: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, ...], ...]:
    """v4 spec §4.4: 4 price rows [10,7,4,1] (high-to-low) x <=5 date cols."""
    n = len(cells[0])
    col_idx = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
    return tuple(
        tuple(cells[r][c] for c in col_idx) for r in (10, 7, 4, 1)
    )
