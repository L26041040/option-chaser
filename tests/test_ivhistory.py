"""(tenor, delta) 重錨定與相對位置的純函式（#126／#114）。

重點在**邊界**：不外插、不拿最長天期頂替、湊不出來就回 None。這幾條
是 #114 AC 明文要求的，不是實作細節。
"""
import pytest

from option_chaser.ivhistory import (ATM_DELTA, SurfacePoint, iv_at,
                                     normalized_skew, percentile)


def _grid():
    """兩個 tenor × 三個 delta 的最小網格。"""
    return [
        SurfacePoint(dte=30, delta=0.25, iv=0.20),
        SurfacePoint(dte=30, delta=0.50, iv=0.24),
        SurfacePoint(dte=30, delta=0.75, iv=0.30),
        SurfacePoint(dte=60, delta=0.25, iv=0.22),
        SurfacePoint(dte=60, delta=0.50, iv=0.26),
        SurfacePoint(dte=60, delta=0.75, iv=0.32),
    ]


# ---------- 網格內：插得出來 ----------

def test_exact_grid_point_returns_that_iv():
    assert iv_at(_grid(), tenor_days=30, delta=0.50) == 0.24


def test_interpolates_along_the_delta_axis():
    """0.375 落在 0.25 與 0.50 正中間 → (0.20 + 0.24) / 2。"""
    assert iv_at(_grid(), tenor_days=30, delta=0.375) == pytest.approx(0.22)


def test_interpolates_along_the_tenor_axis():
    """45 天落在 30 與 60 正中間 → (0.24 + 0.26) / 2。"""
    assert iv_at(_grid(), tenor_days=45, delta=0.50) == pytest.approx(0.25)


def test_interpolates_on_both_axes_at_once():
    # 45 天、0.375 delta：四角平均
    got = iv_at(_grid(), tenor_days=45, delta=0.375)
    assert got == pytest.approx((0.20 + 0.24 + 0.22 + 0.26) / 4)


# ---------- 網格外：說不知道，不外插 ----------

def test_tenor_beyond_the_longest_is_out_of_grid():
    """#114 AC 明文：不得拿最長天期頂替。"""
    assert iv_at(_grid(), tenor_days=900, delta=0.50) is None


def test_tenor_shorter_than_the_shortest_is_out_of_grid():
    assert iv_at(_grid(), tenor_days=5, delta=0.50) is None


def test_delta_beyond_the_grid_is_out_of_grid():
    assert iv_at(_grid(), tenor_days=30, delta=0.95) is None
    assert iv_at(_grid(), tenor_days=30, delta=0.05) is None


def test_a_tenor_inside_the_range_but_missing_delta_coverage_is_out_of_grid():
    """tenor 軸在範圍內，但其中一端的 delta 軸蓋不到目標——四角湊不齊，
    用單邊硬插等於偷偷外插。"""
    points = [
        SurfacePoint(dte=30, delta=0.25, iv=0.20),
        SurfacePoint(dte=30, delta=0.75, iv=0.30),
        SurfacePoint(dte=60, delta=0.60, iv=0.26),   # 蓋不到 0.30
        SurfacePoint(dte=60, delta=0.75, iv=0.32),
    ]
    assert iv_at(points, tenor_days=45, delta=0.30) is None


def test_empty_day_is_out_of_grid_not_an_error():
    """某一天 vendor 沒回資料，是斷點，不是例外。"""
    assert iv_at([], tenor_days=30, delta=0.5) is None


def test_a_single_point_cannot_support_interpolation():
    assert iv_at([SurfacePoint(dte=30, delta=0.5, iv=0.24)],
                 tenor_days=30, delta=0.4) is None


def test_a_single_point_still_answers_its_own_exact_coordinate():
    assert iv_at([SurfacePoint(dte=30, delta=0.5, iv=0.24)],
                 tenor_days=30, delta=0.5) == 0.24


# ---------- Normalized Skew ----------

def test_normalized_skew_scales_the_leg_gap_by_the_atm_level():
    assert normalized_skew(sell_iv=0.30, buy_iv=0.24, atm_iv=0.24) \
        == pytest.approx(0.25)


def test_the_same_skew_at_a_higher_vol_level_normalises_lower():
    """整體波動抬高時兩腿絕對價差會放大，但那不代表 skew 變陡——這正是
    要除以 ATM 的理由。"""
    calm = normalized_skew(sell_iv=0.30, buy_iv=0.24, atm_iv=0.24)
    wild = normalized_skew(sell_iv=0.60, buy_iv=0.48, atm_iv=0.96)
    assert wild < calm


@pytest.mark.parametrize("kwargs", [
    {"sell_iv": None, "buy_iv": 0.24, "atm_iv": 0.24},
    {"sell_iv": 0.30, "buy_iv": None, "atm_iv": 0.24},
    {"sell_iv": 0.30, "buy_iv": 0.24, "atm_iv": None},
    {"sell_iv": 0.30, "buy_iv": 0.24, "atm_iv": 0.0},
])
def test_normalized_skew_says_it_cannot_be_computed(kwargs):
    assert normalized_skew(**kwargs) is None


def test_atm_is_defined_on_the_delta_axis():
    """整個模組活在 (tenor, delta) 座標系；換一套定義 ATM 會讓分子分母
    量的不是同一個東西。"""
    assert ATM_DELTA == 0.5


# ---------- Percentile ----------

def test_percentile_counts_values_at_or_below():
    assert percentile([0.1, 0.2, 0.3, 0.4], 0.3) == pytest.approx(0.75)


def test_the_lowest_value_is_not_reported_as_zero_percentile():
    assert percentile([0.1, 0.2, 0.3, 0.4], 0.1) == pytest.approx(0.25)


def test_an_unchanged_series_reads_as_the_top_not_the_bottom():
    """全同值的序列若回 0.0，等於把「跟過去一樣」說成「處於歷史最低」。"""
    assert percentile([0.2, 0.2, 0.2], 0.2) == 1.0


def test_empty_history_has_no_percentile():
    assert percentile([], 0.2) is None


# ---------- 紅線：不得參與排序／過濾／選取 ----------

def test_ranking_and_filters_do_not_depend_on_this_module():
    """spec #117 §5 的硬紅線在結構上成立：排序與過濾根本不 import 它，
    所以「移除整個 IV 模組後每個候選的命運與順序不變」不是靠測試巡邏，
    是靠沒有那條邊。"""
    import option_chaser.filters as filters
    import option_chaser.ranking as ranking

    for mod in (ranking, filters):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "ivhistory" not in src
