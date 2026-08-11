from datetime import date
import pytest
from option_chaser.matrix import (price_axis, date_axis, matrix_grid,
                                   matrix_lines, thumbnail_cells)


def test_price_axis_len_anchors_and_positivity():
    rows = price_axis(100.0, 120.0, bullish=True)
    prices = [v for v, _, _ in rows]
    assert len(rows) == 11 and prices == sorted(prices)
    assert 100.0 in prices and 120.0 in prices
    labels = {v: lbl for v, lbl, _ in rows}
    assert labels[100.0] == "<現價>" and labels[120.0] == "<目標>"
    # low-target put scenario: floor at 0.01*spot
    rows2 = price_axis(10.0, 0.5, bullish=False)
    assert min(v for v, _, _ in rows2) >= 0.01 * 10.0 - 1e-12


def test_price_axis_collision_spot_near_target():
    rows = price_axis(100.0, 100.5, bullish=True)
    prices = [v for v, _, _ in rows]
    assert len(rows) == 11 and 100.0 in prices and 100.5 in prices


def test_price_axis_spot_equals_target_dual_label():
    rows = price_axis(100.0, 100.0, bullish=True)
    labels = {v: lbl for v, lbl, _ in rows}
    assert "<現價>" in labels[100.0] and "<目標>" in labels[100.0]
    assert len(rows) == 11


def test_price_axis_default_range_bullish():
    """沒有劇本區間時上下限維持既有算式（QA 修正只拿掉標記，不動範圍）。"""
    spot, target = 84.52, 105.0
    pts = price_axis(spot, target, bullish=True)
    vals = [v for v, _, _ in pts]
    assert len(vals) == 11
    for anchor in (spot, target):
        assert anchor in vals
    assert min(vals) == pytest.approx(spot * 0.90)
    assert max(vals) == pytest.approx(target * 1.15)


def test_price_axis_default_range_bearish():
    spot, target = 84.52, 70.0
    pts = price_axis(spot, target, bullish=False)
    vals = [v for v, _, _ in pts]
    for anchor in (spot, target):
        assert anchor in vals
    assert min(vals) == pytest.approx(target * 0.85)
    assert max(vals) == pytest.approx(spot * 1.10)


# ---------- QA 修正：劇本區間（最高／最低價位）決定上下限 ----------

def test_price_axis_bounds_from_scenario_range():
    """上限＝劇本區間高端×1.10、下限＝低端×0.90（需求方指定的算式）。"""
    spot, target, best, worst = 100.0, 130.0, 150.0, 90.0
    pts = price_axis(spot, target, bullish=True,
                     best_price=best, worst_price=worst)
    vals = [v for v, _, _ in pts]
    assert len(vals) == 11
    assert max(vals) == pytest.approx(best * 1.10)
    assert min(vals) == pytest.approx(worst * 0.90)


def test_price_axis_best_worst_are_anchors_and_labelled():
    spot, target, best, worst = 100.0, 130.0, 150.0, 90.0
    labels = {v: lbl for v, lbl, _ in
              price_axis(spot, target, bullish=True,
                        best_price=best, worst_price=worst)}
    assert labels[spot] == "<現價>"
    assert labels[target] == "<目標>"
    assert labels[best] == "<最高>"
    assert labels[worst] == "<最低>"


def test_price_axis_never_labels_overshoot_or_adverse():
    """〈超標〉〈深跌〉整個消失——有沒有設劇本區間都一樣。"""
    for kwargs in ({}, {"best_price": 150.0, "worst_price": 90.0}):
        labels = "".join(lbl for _, lbl, _ in
                         price_axis(100.0, 130.0, bullish=True, **kwargs))
        assert "<超標>" not in labels and "<深跌>" not in labels
    labels_bear = "".join(lbl for _, lbl, _ in
                          price_axis(100.0, 70.0, bullish=False))
    assert "<超標>" not in labels_bear and "<深跌>" not in labels_bear


def test_price_axis_spot_dominates_when_scenario_range_is_narrow():
    """劇本區間比現價還窄時，現價本身仍要落在圖內——取的是聯集的極值，
    不是只看使用者填的兩個數字。"""
    spot, target, best, worst = 100.0, 104.0, 105.0, 99.0
    pts = price_axis(spot, target, bullish=True,
                     best_price=best, worst_price=worst)
    vals = [v for v, _, _ in pts]
    assert max(vals) == pytest.approx(best * 1.10)
    assert min(vals) == pytest.approx(worst * 0.90)
    assert spot in vals


def test_price_axis_bearish_scenario_range_keeps_both_ends_in_view():
    """看跌劇本的『最高價位』其實是行情往上跑、『最低價位』是往下跑——上下限用聯集極值算，
    兩端才都進得了圖（直接照字面取 max(best, spot) 會把最低價位擠出去）。"""
    spot, target, best, worst = 100.0, 70.0, 60.0, 115.0
    pts = price_axis(spot, target, bullish=False,
                     best_price=best, worst_price=worst)
    vals = [v for v, _, _ in pts]
    assert max(vals) == pytest.approx(worst * 1.10)
    assert min(vals) == pytest.approx(best * 0.90)
    for anchor in (spot, target, best, worst):
        assert anchor in vals


def test_price_axis_only_one_end_set_still_uses_scenario_bounds():
    spot, target, worst = 100.0, 130.0, 85.0
    vals = [v for v, _, _ in price_axis(spot, target, bullish=True,
                                       worst_price=worst)]
    assert len(vals) == 11
    assert min(vals) == pytest.approx(worst * 0.90)
    # 高端沒有使用者輸入可用 → 取劇本已知的最高點（目標價）加一成
    assert max(vals) == pytest.approx(target * 1.10)


def test_price_axis_scenario_bounds_stay_positive():
    """使用者自己填的極低價位照畫（那是他要求看的價位，不該被夾掉），
    但推導出來的格點不會掉到 0 或負數。"""
    rows = price_axis(10.0, 0.5, bullish=False, best_price=0.05)
    vals = [v for v, _, _ in rows]
    assert all(v > 0 for v in vals)
    assert 0.05 in vals
    assert len(vals) == 11


def test_price_axis_v4_positive_clamp():
    pts = price_axis(2.0, 15.0, bullish=True)   # adverse=1.8 > 0.02 so no clamp
    assert all(v > 0 for v, _, _ in pts)


def test_price_axis_anchor_collision_dedup():
    """spot*0.9 colliding with a grid point must not duplicate rows."""
    pts = price_axis(100.0, 110.0, bullish=True)
    vals = [v for v, _, _ in pts]
    assert len(vals) == len(set(vals)) == 11


def test_price_axis_default_anchor_labels():
    """沒有劇本區間時只剩現價與目標兩個標記。"""
    spot, target = 84.52, 105.0
    labels = {v: lbl for v, lbl, _ in price_axis(spot, target, bullish=True)}
    assert labels[spot] == "<現價>"
    assert labels[target] == "<目標>"
    assert sum(1 for lbl in labels.values() if lbl) == 2

    spot2, target2 = 84.52, 70.0
    labels2 = {v: lbl for v, lbl, _ in price_axis(spot2, target2, bullish=False)}
    assert labels2[spot2] == "<現價>"
    assert labels2[target2] == "<目標>"
    assert sum(1 for lbl in labels2.values() if lbl) == 2


# ---------- 決策 M（#109）：右側 ±% 標註（move_pct） ----------

def test_move_pct_formula_matches_price_relative_to_spot():
    spot, target = 84.52, 105.0
    rows = price_axis(spot, target, bullish=True)
    for price, _, move_pct in rows:
        assert move_pct == pytest.approx((price - spot) / spot)


def test_move_pct_zero_at_spot_row():
    spot, target = 100.0, 120.0
    rows = price_axis(spot, target, bullish=True)
    move_pct_by_price = {price: move_pct for price, _, move_pct in rows}
    assert move_pct_by_price[spot] == 0.0


def test_move_pct_sign_matches_overshoot_and_adverse_direction():
    # bullish：超標在現價之上（正）、深跌在現價之下（負）
    spot, target = 84.52, 105.0
    overshoot, adverse = target * 1.15, spot * 0.90
    rows = price_axis(spot, target, bullish=True)
    move_pct_by_price = {price: move_pct for price, _, move_pct in rows}
    assert move_pct_by_price[overshoot] > 0
    assert move_pct_by_price[adverse] < 0

    # bearish：超標在現價之下（負）、深跌在現價之上（正）——標記語意
    # 是「相對現價的距離方向」，不是漲跌的好壞，bullish/bearish 只影響
    # 超標／深跌落在哪一側，move_pct 的正負號永遠只看價格相對 spot 的
    # 位置。
    spot2, target2 = 84.52, 70.0
    overshoot2, adverse2 = target2 * 0.85, spot2 * 1.10
    rows2 = price_axis(spot2, target2, bullish=False)
    move_pct_by_price2 = {price: move_pct for price, _, move_pct in rows2}
    assert move_pct_by_price2[overshoot2] < 0
    assert move_pct_by_price2[adverse2] > 0


def test_thumbnail_cells_indices():
    from option_chaser.matrix import thumbnail_cells
    cells = tuple(tuple(float(r * 10 + c) for c in range(7)) for r in range(11))
    th = thumbnail_cells(cells)
    assert len(th) == 4                     # price rows [10,7,4,1] high-to-low
    assert th[0][0] == 100.0 and th[3][0] == 10.0
    assert len(th[0]) == 5                  # date cols [0, 1, 3, 5, 6] for n=7
    assert th[0] == (100.0, 101.0, 103.0, 105.0, 106.0)


def test_thumbnail_cells_few_dates_dedup():
    cells = tuple(tuple(float(r) for _ in range(2)) for r in range(11))
    th = thumbnail_cells(cells)
    assert len(th[0]) == 2                  # dedup: n=2 -> cols [0, 1]


def test_date_axis_spans_today_to_own_expiry():
    cols = date_axis(date(2026, 7, 15), date(2026, 10, 16))
    ds = [d for d, _ in cols]
    assert ds[0] == date(2026, 7, 15) and ds[-1] == date(2026, 10, 16)
    assert ds == sorted(set(ds)) and len(ds) <= 7


def test_date_axis_has_no_target_marker():
    """A2.3：年月語意下不存在「目標日」欄，「*」標記連同日期映射一併移除。"""
    cols = date_axis(date(2026, 7, 15), date(2026, 10, 16))
    assert {lbl for _, lbl in cols} == {""}


def test_matrix_lines_shape_and_determinism():
    prices = price_axis(100.0, 120.0, bullish=True)
    dates = date_axis(date(2026, 7, 15), date(2026, 10, 16))

    def fn(S, d):  # deterministic dummy
        return max(S - 110.0, 0.0)

    a = matrix_lines(fn, 3.0, prices, dates)
    b = matrix_lines(fn, 3.0, prices, dates)
    assert a == b
    assert len(a) == 1 + 11  # header + one line per price row
    assert not any(0x2500 <= ord(ch) <= 0x257F for line in a for ch in line)


# ---------- QA-FIX-5（QA-01）：GUI 日期軸密度參數化 ----------

def test_date_axis_default_stays_seven_points_for_cli():
    """不傳 `max_gap_days` ＝ 既有行為（固定七欄）。CLI 文字報告靠這個
    維持既有寬度，golden fixture 才不會產生與本次修正無關的漂移。"""
    for expiry in ("2026-11-20", "2027-08-09", "2028-12-15"):
        cols = date_axis(date(2026, 8, 9), date.fromisoformat(expiry))
        assert len(cols) == 7


def test_gui_axis_caps_the_gap_at_about_one_month():
    """GUI 軸：欄距上限約一個月。長天期不再被拉成 4～5 個月一格。"""
    from option_chaser.matrix import GUI_MAX_GAP_DAYS
    today = date(2026, 8, 9)
    for expiry in ("2026-11-20", "2027-08-09", "2028-12-15", "2029-06-15"):
        cols = date_axis(today, date.fromisoformat(expiry),
                         max_gap_days=GUI_MAX_GAP_DAYS)
        days = [d for d, _ in cols]
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        assert max(gaps) <= GUI_MAX_GAP_DAYS


def test_gui_axis_hits_the_agreed_column_counts():
    """需求方裁示的三個驗收情境（QA-01 第 5 項）——短天期不因新規則
    變粗（維持七點），長天期加密到約每月一格。"""
    from option_chaser.matrix import GUI_MAX_GAP_DAYS
    today = date(2026, 8, 9)
    expected = {"2026-11-20": 7,     # ~3 個月：沿用下限，不退化
                "2027-08-09": 13,    # ~1 年
                "2028-12-15": 29}    # ~2.4 年
    for expiry, want in expected.items():
        cols = date_axis(today, date.fromisoformat(expiry),
                         max_gap_days=GUI_MAX_GAP_DAYS)
        assert len(cols) == want, f"{expiry}: {len(cols)} != {want}"


def test_gui_axis_always_keeps_today_and_expiry_and_min_seven_points():
    """加密只在中間插點——兩個端點是硬需求，且至少七個時間點。

    「至少七點」的上限是天期本身：剩五天的合約只有六個日曆日可畫，
    要求七個相異日期在物理上不可能（`sorted(set(...))` 會去重）。這是
    既有行為、非本次改動引入，這裡把真正的不變量寫清楚而不是假裝
    它永遠是 7。
    """
    from option_chaser.matrix import GUI_MAX_GAP_DAYS
    today = date(2026, 8, 9)
    for expiry in ("2026-08-14", "2026-11-20", "2028-12-15"):
        e = date.fromisoformat(expiry)
        cols = date_axis(today, e, max_gap_days=GUI_MAX_GAP_DAYS)
        days = [d for d, _ in cols]
        assert days[0] == today and days[-1] == e
        assert len(cols) >= min(7, (e - today).days + 1)
        assert days == sorted(set(days))       # 嚴格遞增、無重複


def test_gui_axis_density_reaches_the_matrix_cells():
    """密度真的走到 GUI 的格子上（不是只有軸變長、cells 沒跟上），
    而且 CLI 的 `matrix_lines` 仍是七欄——同一份輸入、兩種密度。"""
    from option_chaser.matrix import GUI_MAX_GAP_DAYS
    today, expiry = date(2026, 8, 9), date(2028, 12, 15)
    prices = price_axis(100.0, 120.0, bullish=True)

    def fn(S, d):
        return max(S - 110.0, 0.0)

    gui_dates = date_axis(today, expiry, max_gap_days=GUI_MAX_GAP_DAYS)
    gui_grid = matrix_grid(fn, 3.0, prices, gui_dates)
    assert len(gui_grid) == len(prices)
    assert len(gui_grid[0]) == len(gui_dates) == 29

    cli_lines = matrix_lines(fn, 3.0, prices, date_axis(today, expiry))
    assert len(cli_lines) == 1 + len(prices)
    # CLI 每行寬度沒有因為 GUI 加密而爆開
    assert max(len(line) for line in cli_lines) < 100


def test_thumbnail_keeps_proportional_sampling_on_a_dense_axis():
    """thumbnail 的比例取樣語意不變：不論來源幾欄，一律 4 列 × <=5 欄。"""
    dense = tuple(tuple(float(r * 100 + c) for c in range(29)) for r in range(11))
    th = thumbnail_cells(dense)
    assert len(th) == 4 and len(th[0]) == 5
    # 取的是比例位置（頭、1/4、1/2、3/4、尾），不是前五欄
    assert th[0][0] == dense[10][0] and th[0][-1] == dense[10][28]
