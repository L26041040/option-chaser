"""Price×date P/L matrix engine (spec §5). Pure functions, deterministic."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Callable

# QA-FIX-5（QA-01）：GUI Heatmap 的日期欄距上限（日曆日）。
#
# 舊行為是固定七欄、與天期無關，長天期因此被拉得極稀疏——實測 2.4 年
# LEAPS 平均 143 天／欄（4.7 個月），使用者看不出中間發生什麼事。
# 需求方裁示：GUI 欄距上限約一個月、至少維持七個時間點、today 與
# expiry 必須保留。31 是「一個日曆月的上限」，代入三個驗收情境剛好
# 命中裁示的目標欄數：
#   ~3 個月（103 天）→ 7 點（沿用下限，不因新規則變粗）
#   ~1 年（365 天）  → 13 點
#   ~2.4 年（859 天）→ 29 點
#
# **只有 GUI 用它**：CLI 文字報告維持既有低密度（`date_axis` 不傳這個
# 參數就是原本的七欄），否則每行會爆到 230+ 字元，且四份 golden
# fixture 會產生與這次修正無關的漂移。密度是呼叫端的顯示決策，因此
# 參數化在這裡，不是讓前端拿到資料後自己重新抽樣（前端零金融計算）。
GUI_MAX_GAP_DAYS = 31


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
    best_price: float | None = None, worst_price: float | None = None,
) -> list[tuple[float, str, float]]:
    """價格軸：錨點 {現價, 目標, 最好, 最差}，範圍由劇本區間 ±10% 決定。

    **QA 修正（需求方裁示）**：上限＝劇本區間高端×1.10、下限＝低端×0.90，
    而且原本的 `<超標>`（目標×1.15）與 `<深跌>`（現價×0.90）兩個標記整個
    移除——它們是憑空生出來的價位，對使用者沒有意義。改放使用者自己填的
    最好／最差價位。

    「劇本區間高端／低端」取的是 {現價, 目標, 最好, 最差} 已知值的**極值**，
    不是字面上的 `max(最好, 現價)`：看跌劇本的「最好」是低價、「最差」是
    高價，照字面取會把最差價位擠出圖外。取聯集極值在看漲情形下與需求方
    給的算式完全一致（看漲時最好恆為最高、最差恆為最低），看跌也成立。

    兩端都沒填時（劇本沒有區間可用）沿用既有上下限算式：看漲 ＝
    [現價×0.90, 目標×1.15]、看跌 ＝ [目標×0.85, 現價×1.10]。這條路徑
    同樣不標 `<超標>`／`<深跌>`——標記是無條件移除的。

    決策 M（#109）：第三個元素 `move_pct` 是該價位相對 `spot` 的變動分數
    （`<現價>` 那一列恆為 0）——跟 cell 的估值同一個 `spot`、同一次呼叫算出來，
    不是另外重算的第二份數字。GUI 只格式化顯示。
    """
    anchors = sorted({spot, target}
                     | {v for v in (best_price, worst_price) if v is not None})
    lo_raw, hi_raw = min(anchors), max(anchors)
    if best_price is None and worst_price is None:
        # 既有預設：把兩個推導價位納入範圍（但不再當成有名字的錨點）
        lo_raw = min(lo_raw, spot * (0.90 if bullish else 1.0),
                     target * (1.0 if bullish else 0.85))
        hi_raw = max(hi_raw, spot * (1.0 if bullish else 1.10),
                     target * (1.15 if bullish else 1.0))
    else:
        lo_raw, hi_raw = lo_raw * 0.90, hi_raw * 1.10
    lo = max(lo_raw, 0.01 * spot)
    hi = hi_raw
    pts = [lo + (hi - lo) * i / 10.0 for i in range(11)]
    vals = _insert_anchors(pts, anchors)

    def label(v: float) -> str:
        s = ""
        if v == spot:
            s += "<現價>"
        if v == target:
            s += "<目標>"
        if best_price is not None and v == best_price:
            s += "<最好>"
        if worst_price is not None and v == worst_price:
            s += "<最差>"
        return s

    return [(v, label(v), (v - spot) / spot) for v in vals]


def date_axis(today: date, expiry: date,
              max_gap_days: float | None = None) -> list[tuple[date, str]]:
    """日期軸＝今天 → 該合約自身的到期日，等分成欄。

    附錄 A2.3：年月語意下不存在「目標日」那一欄，原本的「*」標記連同它所需的
    日期映射一併移除。標籤欄保留（恆為空字串）以維持與價格軸相同的欄位形狀。

    `max_gap_days`（QA-FIX-5／QA-01）：欄距上限。`None`＝維持既有行為
    （固定七欄，CLI 文字報告用）；給值則在「至少七個時間點」的下限之上
    加密到欄距不超過這個天數（GUI 用 `GUI_MAX_GAP_DAYS`）。無論哪種
    密度，首欄恆為 `today`、末欄恆為 `expiry`——加密只是在中間多插點，
    不動兩個端點。
    """
    total = (expiry - today).days
    # 六個區間＝七個時間點，是既有行為也是裁示的下限；短天期因此不會
    # 因為「欄距上限」這條新規則反而變得比原本粗。
    intervals = 6
    if max_gap_days is not None and total > 0:
        intervals = max(intervals, math.ceil(total / max_gap_days))
    pts = [today + timedelta(days=round(total * i / intervals))
           for i in range(intervals + 1)]
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
