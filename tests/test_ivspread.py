"""option_chaser/ivspread.py 純函式（SIG-01／#172，spec #171）。"""
import pytest

from option_chaser.ivspread import (IV_GAP_RATIO_MIN_BASE, STATUS_NEAR_ZERO_BASE,
                                    STATUS_NO_BASELINE, STATUS_OK,
                                    STATUS_SIGN_FLIP, align_spread_gap,
                                    spread_delta_4w_ratio_status)


# ---------- align_spread_gap ----------

def test_gap_is_sell_minus_buy_on_overlapping_dates():
    buy = [("2026-08-01", 0.20), ("2026-08-02", 0.22)]
    sell = [("2026-08-01", 0.30), ("2026-08-02", 0.35)]
    got = align_spread_gap(buy, sell)
    assert [d for d, _ in got] == ["2026-08-01", "2026-08-02"]
    assert [g for _, g in got] == pytest.approx([0.10, 0.13])


def test_a_day_with_only_one_leg_valued_is_absent_from_output():
    buy = [("2026-08-01", 0.20), ("2026-08-02", None)]
    sell = [("2026-08-01", None), ("2026-08-02", 0.35)]
    assert align_spread_gap(buy, sell) == []


def test_a_day_with_neither_leg_valued_is_absent_from_output():
    buy = [("2026-08-01", None)]
    sell = [("2026-08-01", None)]
    assert align_spread_gap(buy, sell) == []


def test_gap_field_is_never_null_never_appears_as_a_null_observation():
    buy = [("2026-08-01", 0.20), ("2026-08-02", None)]
    sell = [("2026-08-01", 0.30), ("2026-08-02", 0.35)]
    got = align_spread_gap(buy, sell)
    assert all(gap is not None for _, gap in got)
    assert len(got) == 1


def test_output_is_sorted_ascending_even_when_inputs_are_unsorted():
    buy = [("2026-08-03", 0.20), ("2026-08-01", 0.18), ("2026-08-02", 0.19)]
    sell = [("2026-08-02", 0.30), ("2026-08-03", 0.31), ("2026-08-01", 0.29)]
    got = align_spread_gap(buy, sell)
    assert [d for d, _ in got] == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_last_point_is_the_formal_source_of_the_current_gap():
    """契約鎖定：`points[-1]` 就是「目前 IV Gap 現值」——這裡直接鎖住
    「輸出遞增排序、最後一筆是日期最新的一筆」這個順序保證。"""
    buy = [("2026-08-03", 0.20), ("2026-08-01", 0.18)]
    sell = [("2026-08-03", 0.25), ("2026-08-01", 0.30)]
    got = align_spread_gap(buy, sell)
    d, gap = got[-1]
    assert d == "2026-08-03"
    assert gap == pytest.approx(0.05)


def test_duplicate_date_within_a_single_leg_fails_fast():
    buy = [("2026-08-01", 0.20), ("2026-08-01", 0.21)]
    sell = [("2026-08-01", 0.30)]
    with pytest.raises(AssertionError):
        align_spread_gap(buy, sell)


def test_duplicate_date_in_the_sell_leg_also_fails_fast():
    buy = [("2026-08-01", 0.20)]
    sell = [("2026-08-01", 0.30), ("2026-08-01", 0.31)]
    with pytest.raises(AssertionError):
        align_spread_gap(buy, sell)


def test_empty_inputs_yield_empty_output():
    assert align_spread_gap([], []) == []


# ---------- spread_delta_4w_ratio_status ----------

def test_no_delta_means_no_baseline():
    ratio, status = spread_delta_4w_ratio_status(0.10, None)
    assert (ratio, status) == (None, STATUS_NO_BASELINE)


def test_near_zero_baseline_is_guarded():
    # baseline_gap = current_gap - delta_4w = 0.10 - 0.098 = 0.002 < 0.005
    ratio, status = spread_delta_4w_ratio_status(0.10, 0.098)
    assert (ratio, status) == (None, STATUS_NEAR_ZERO_BASE)


def test_baseline_exactly_at_the_threshold_is_not_near_zero():
    """嚴格 `<` 比較——恰好等於門檻不算近零。"""
    current_gap = 0.10
    delta_4w = current_gap - IV_GAP_RATIO_MIN_BASE  # baseline_gap == 0.005 恰好
    ratio, status = spread_delta_4w_ratio_status(current_gap, delta_4w)
    assert status == STATUS_OK
    assert ratio == pytest.approx(delta_4w / IV_GAP_RATIO_MIN_BASE)


def test_sign_flip_when_baseline_and_current_have_opposite_signs():
    # baseline_gap = 0.10 - 0.20 = -0.10（負），current_gap = 0.10（正）
    ratio, status = spread_delta_4w_ratio_status(0.10, 0.20)
    assert (ratio, status) == (None, STATUS_SIGN_FLIP)


def test_current_gap_exactly_zero_with_non_near_zero_baseline_is_sign_flip():
    # baseline_gap = 0 - 0.10 = -0.10（非近零），current_gap 恰好 0
    ratio, status = spread_delta_4w_ratio_status(0.0, 0.10)
    assert (ratio, status) == (None, STATUS_SIGN_FLIP)


def test_ok_status_ratio_is_delta_over_absolute_baseline_not_times_100():
    # baseline_gap = 0.10 - 0.02 = 0.08
    ratio, status = spread_delta_4w_ratio_status(0.10, 0.02)
    assert status == STATUS_OK
    assert ratio == pytest.approx(0.02 / 0.08)
    assert ratio < 1  # 沒有被誤乘 100


def test_ok_status_with_matching_negative_signs():
    # baseline_gap = -0.10 - (-0.02) = -0.08，兩者同為負號
    ratio, status = spread_delta_4w_ratio_status(-0.10, -0.02)
    assert status == STATUS_OK
    assert ratio == pytest.approx(-0.02 / 0.08)


# ---------- 隔離紅線（spec #151 §7／spec #171 沿用同一套紀律）----------

def test_this_module_never_imports_ivhistory():
    import ast

    import option_chaser.ivspread as ivspread_module

    src = open(ivspread_module.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any("ivhistory" in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "ivhistory" not in node.module


def test_ranking_and_filters_do_not_depend_on_this_module():
    import option_chaser.filters as filters
    import option_chaser.ranking as ranking

    for mod in (ranking, filters):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "ivspread" not in src
