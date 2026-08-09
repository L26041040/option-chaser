from datetime import date
import pytest
from option_chaser.matrix import price_axis, date_axis, matrix_lines, thumbnail_cells


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


def test_price_axis_v4_anchors_bullish():
    spot, target = 84.52, 105.0
    pts = price_axis(spot, target, bullish=True)
    vals = [v for v, _, _ in pts]
    assert len(vals) == 11
    overshoot, adverse = target * 1.15, spot * 0.90
    for anchor in (spot, target, overshoot, adverse):
        assert anchor in vals
    assert min(vals) == pytest.approx(adverse)
    assert max(vals) == pytest.approx(overshoot)


def test_price_axis_v4_anchors_bearish():
    spot, target = 84.52, 70.0
    pts = price_axis(spot, target, bullish=False)
    vals = [v for v, _, _ in pts]
    overshoot, adverse = target * 0.85, spot * 1.10
    for anchor in (spot, target, overshoot, adverse):
        assert anchor in vals
    assert min(vals) == pytest.approx(overshoot)
    assert max(vals) == pytest.approx(adverse)


def test_price_axis_v4_positive_clamp():
    pts = price_axis(2.0, 15.0, bullish=True)   # adverse=1.8 > 0.02 so no clamp
    assert all(v > 0 for v, _, _ in pts)


def test_price_axis_anchor_collision_dedup():
    """spot*0.9 colliding with a grid point must not duplicate rows."""
    pts = price_axis(100.0, 110.0, bullish=True)
    vals = [v for v, _, _ in pts]
    assert len(vals) == len(set(vals)) == 11


def test_price_axis_v4_anchor_labels():
    spot, target = 84.52, 105.0
    overshoot, adverse = target * 1.15, spot * 0.90
    labels = {v: lbl for v, lbl, _ in price_axis(spot, target, bullish=True)}
    assert labels[spot] == "<現價>"
    assert labels[target] == "<目標>"
    assert labels[overshoot] == "<超標>"
    assert labels[adverse] == "<深跌>"

    spot2, target2 = 84.52, 70.0
    overshoot2, adverse2 = target2 * 0.85, spot2 * 1.10
    labels2 = {v: lbl for v, lbl, _ in price_axis(spot2, target2, bullish=False)}
    assert labels2[spot2] == "<現價>"
    assert labels2[target2] == "<目標>"
    assert labels2[overshoot2] == "<超標>"
    assert labels2[adverse2] == "<深跌>"


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
