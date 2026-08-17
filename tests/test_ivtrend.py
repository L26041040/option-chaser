"""option_chaser/ivtrend.py 純函式（HIVT-02／#153）。"""
from datetime import date

from option_chaser.ivtrend import (IV_TREND_MAX_HISTORY_DAYS,
                                   history_span_days, trim_to_window)


# ---------- trim_to_window ----------

def test_full_year_history_is_untouched():
    points = [("2025-08-17", 0.12), ("2026-08-17", 0.15)]
    assert trim_to_window(points, today=date(2026, 8, 17)) == points


def test_points_older_than_the_window_are_dropped():
    points = [("2020-01-01", 0.1), ("2026-08-01", 0.2)]
    got = trim_to_window(points, today=date(2026, 8, 17))
    assert got == [("2026-08-01", 0.2)]


def test_partial_history_under_a_year_is_returned_unpadded():
    """掛牌不滿一年——有多少回多少，不補齊到 365 天（spec §4）。"""
    points = [("2026-06-01", 0.1), ("2026-08-01", 0.2)]
    got = trim_to_window(points, today=date(2026, 8, 17))
    assert got == points


def test_boundary_date_exactly_365_days_ago_is_kept():
    """`cutoff` 用 `>=`：正好卡在邊界的那一天算在窗內，不是窗外。"""
    today = date(2026, 8, 17)
    cutoff = today.replace(year=today.year - 1)  # 一年前同一天（近似，測試不依賴精確 leap day 邊界）
    points = [(cutoff.isoformat(), 0.1)]
    got = trim_to_window(points, today=today,
                         max_days=(today - cutoff).days)
    assert got == points


def test_custom_max_days_overrides_the_default():
    points = [("2026-08-01", 0.1), ("2026-08-15", 0.2)]
    got = trim_to_window(points, today=date(2026, 8, 17), max_days=5)
    assert got == [("2026-08-15", 0.2)]


def test_default_constant_is_365():
    assert IV_TREND_MAX_HISTORY_DAYS == 365


def test_null_iv_points_are_trimmed_by_date_like_any_other():
    points = [("2020-01-01", None), ("2026-08-01", None)]
    got = trim_to_window(points, today=date(2026, 8, 17))
    assert got == [("2026-08-01", None)]


# ---------- history_span_days ----------

def test_span_is_zero_for_empty_series():
    assert history_span_days([]) == 0


def test_span_is_zero_for_a_single_observation():
    assert history_span_days([("2026-08-17", 0.1)]) == 0


def test_span_is_the_gap_between_earliest_and_latest():
    points = [("2026-08-17", 0.1), ("2025-08-17", 0.1), ("2026-01-01", 0.1)]
    assert history_span_days(points) == 365


def test_span_counts_null_iv_points_too():
    """跨度是「vendor 給了多長的時間涵蓋範圍」，不管那天 iv 是不是 null。"""
    points = [("2026-01-01", None), ("2026-06-01", 0.2)]
    assert history_span_days(points) == 151


def test_span_does_not_require_pre_sorted_input():
    points = [("2026-08-17", 0.1), ("2026-01-01", 0.2)]
    assert history_span_days(points) == history_span_days(list(reversed(points)))
