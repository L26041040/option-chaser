import re
from datetime import date
from option_chaser.matrix import date_axis, matrix_grid, matrix_lines, price_axis


def _fn(S, d):
    return max(S - 110.0, 0.0)


def test_grid_shape_and_values():
    prices = price_axis(100.0, 120.0, bullish=True)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    grid = matrix_grid(_fn, 3.0, prices, dates)
    assert len(grid) == len(prices) and len(grid[0]) == len(dates)
    for i, (price, _) in enumerate(prices):
        for j, (d, _) in enumerate(dates):
            assert grid[i][j] == (_fn(price, d) - 3.0) / 3.0


def test_lines_formats_grid_cell_for_cell():
    prices = price_axis(100.0, 120.0, bullish=True)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    grid = matrix_grid(_fn, 3.0, prices, dates)
    lines = matrix_lines(_fn, 3.0, prices, dates)
    # data rows are displayed descending; parse each cell and compare to grid
    for row_idx, line in enumerate(lines[1:]):
        i = len(prices) - 1 - row_idx
        cells = re.findall(r"([+-]\d+)%", line)
        assert len(cells) == len(dates)
        for j, cell in enumerate(cells):
            assert cell == f"{grid[i][j] * 100:+.0f}".replace("+-", "-")
