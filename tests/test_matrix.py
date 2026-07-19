from datetime import date
from option_chaser.matrix import price_axis, date_axis, matrix_lines


def test_price_axis_len_anchors_and_positivity():
    rows = price_axis(100.0, 120.0)
    prices = [v for v, _ in rows]
    assert len(rows) == 11 and prices == sorted(prices)
    assert 100.0 in prices and 120.0 in prices
    labels = dict(rows)
    assert labels[100.0] == "<現價>" and labels[120.0] == "<目標>"
    # low-target put scenario: floor at 0.01*spot
    rows2 = price_axis(10.0, 0.5)
    assert min(v for v, _ in rows2) >= 0.01 * 10.0 - 1e-12


def test_price_axis_collision_spot_near_target():
    rows = price_axis(100.0, 100.5)
    prices = [v for v, _ in rows]
    assert len(rows) == 11 and 100.0 in prices and 100.5 in prices


def test_price_axis_spot_equals_target_dual_label():
    rows = price_axis(100.0, 100.0)
    labels = dict(rows)
    assert labels[100.0] == "<現價><目標>"
    assert len(rows) == 11


def test_date_axis_endpoints_and_anchor():
    cols = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    ds = [d for d, _ in cols]
    assert ds[0] == date(2026, 7, 15) and ds[-1] == date(2026, 10, 16)
    assert date(2026, 8, 28) in ds
    assert dict(cols)[date(2026, 8, 28)] == "*"


def test_date_axis_target_equals_expiry_shares_column():
    cols = date_axis(date(2026, 7, 15), date(2026, 10, 16), date(2026, 10, 16))
    ds = [d for d, _ in cols]
    assert ds[-1] == date(2026, 10, 16) and dict(cols)[date(2026, 10, 16)] == "*"


def test_matrix_lines_shape_and_determinism():
    prices = price_axis(100.0, 120.0)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))

    def fn(S, d):  # deterministic dummy
        return max(S - 110.0, 0.0)

    a = matrix_lines(fn, 3.0, prices, dates)
    b = matrix_lines(fn, 3.0, prices, dates)
    assert a == b
    assert len(a) == 1 + 11  # header + one line per price row
    assert not any(0x2500 <= ord(ch) <= 0x257F for line in a for ch in line)
