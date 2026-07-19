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


def price_axis(spot: float, target: float) -> list[tuple[float, str]]:
    pad = 0.10 * spot
    lo = max(min(spot, target) - pad, 0.01 * spot)
    hi = max(spot, target) + pad
    pts = [lo + (hi - lo) * i / 10.0 for i in range(11)]
    anchors = sorted({spot, target})
    vals = _insert_anchors(pts, anchors)

    def label(v: float) -> str:
        s = ""
        if v == spot:
            s += "<現價>"
        if v == target:
            s += "<目標>"
        return s

    return [(v, label(v)) for v in vals]


def date_axis(today: date, target_date: date, expiry: date) -> list[tuple[date, str]]:
    total = (expiry - today).days
    pts = [today + timedelta(days=round(total * i / 6.0)) for i in range(7)]
    pts[-1] = expiry
    uniq = sorted(set(pts))
    if target_date not in uniq:
        interior = [i for i in range(len(uniq)) if 0 < i < len(uniq) - 1]
        if interior:
            best = min((abs((uniq[i] - target_date).days), i) for i in interior)[1]
            uniq[best] = target_date
            uniq = sorted(set(uniq))
    return [(d, "*" if d == target_date else "") for d in uniq]


def matrix_grid(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str]], dates: list[tuple[date, str]],
) -> tuple[tuple[float, ...], ...]:
    """Structured cell returns (v3 spec §2.3): single data source for CLI and GUI."""
    return tuple(
        tuple((value_fn(price, d) - cost) / cost for d, _ in dates)
        for price, _ in prices
    )


def matrix_lines(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str]], dates: list[tuple[date, str]],
) -> list[str]:
    grid = matrix_grid(value_fn, cost, prices, dates)
    header = "價格".ljust(10) + " ".join(
        (d.strftime("%m/%d") + lbl).rjust(7) for d, lbl in dates
    )
    lines = [header]
    for i in range(len(prices) - 1, -1, -1):
        price, plabel = prices[i]
        cells = [f"{grid[i][j] * 100:+.0f}%".rjust(7) for j in range(len(dates))]
        lines.append(f"{price:8.2f}{plabel}".ljust(10) + " ".join(cells))
    return lines
