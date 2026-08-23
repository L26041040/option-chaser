"""option_chaser/ivtrend.py 純函式（HIVT-02／#153、HIVT-03／#154）。"""
from datetime import date, timedelta
from statistics import mean, stdev

import pytest

from option_chaser.ivtrend import (IV_TREND_LOOKBACK_DAYS,
                                   IV_TREND_MAX_HISTORY_DAYS,
                                   IV_TREND_MIN_OBSERVATIONS_FOR_BANDS,
                                   bollinger_bands, current_zscore, delta_4w,
                                   historical_percentile, history_span_days,
                                   moving_average, trim_to_window)


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


# ---------- 統計量共用 fixture（HIVT-03／#154） ----------

def _daily(start: date, ivs: list[float | None]) -> list[tuple[str, float | None]]:
    """從 `start` 起連續每日一筆——大多數統計量測試不關心抽樣間隔，只
    要「同一天視窗內剛好有這些值」，連續日期最容易手算對照。"""
    return [((start + timedelta(days=i)).isoformat(), iv)
            for i, iv in enumerate(ivs)]


def test_lookback_constant_is_30():
    assert IV_TREND_LOOKBACK_DAYS == 30


def test_min_observations_for_bands_constant_is_5():
    assert IV_TREND_MIN_OBSERVATIONS_FOR_BANDS == 5


# ---------- moving_average ----------

def test_moving_average_is_none_below_the_minimum_observation_count():
    """前四天視窗內都不滿 5 筆——序列起始端天然的空窗，不是特例。"""
    points = _daily(date(2026, 8, 1), [0.10, 0.12, 0.14, 0.16])
    got = moving_average(points)
    assert all(v is None for _, v in got)


def test_moving_average_matches_hand_calculated_mean_once_enough_observations():
    ivs = [0.10, 0.12, 0.14, 0.16, 0.18]
    points = _daily(date(2026, 8, 1), ivs)
    got = moving_average(points)
    assert got[-1] == (points[-1][0], mean(ivs))


def test_moving_average_only_emits_a_point_for_dates_with_a_valid_iv():
    points = [("2026-08-01", 0.10), ("2026-08-02", None), ("2026-08-03", 0.12),
             ("2026-08-04", 0.13), ("2026-08-05", 0.14), ("2026-08-06", 0.15)]
    got = moving_average(points)
    assert [d for d, _ in got] == ["2026-08-01", "2026-08-03", "2026-08-04",
                                   "2026-08-05", "2026-08-06"]


def test_moving_average_excludes_points_older_than_the_window():
    """視窗外那一筆存在，但不該被算進最新一點的平均——用它去把平均拉走
    很遠，若混進來手算值就會對不上。"""
    old = [("2020-01-01", 999.0)]
    recent = _daily(date(2026, 8, 1), [0.10, 0.12, 0.14, 0.16, 0.18])
    got = moving_average(old + recent, window_days=30)
    assert got[-1] == (recent[-1][0], mean(iv for _, iv in recent))


def test_moving_average_boundary_day_exactly_at_window_edge_is_included():
    points = _daily(date(2026, 7, 1), [0.10] * 5) + [("2026-07-31", 0.20)]
    # 2026-07-01 距 2026-07-31 恰好 30 天——window_days=30 該含進去
    got = moving_average(points, window_days=30)
    assert got[-1][1] == mean([0.10] * 5 + [0.20])


def test_moving_average_boundary_with_date_gaps_and_edge_observation():
    """PERF-04（#180）重構前的特徵化測試：真實資料含缺口（週末／假日／
    缺席觀測，不是連續每日）時，卡在視窗邊界的觀測仍要被含入——雙指標
    重構後這條必須維持逐位元相同的斷言。"""
    points = [
        ("2026-06-30", 999.0),  # 31 天前，超出視窗；若誤含會把平均拉爆
        ("2026-07-01", 0.10),   # 恰好 30 天前，邊界含入
        ("2026-07-03", 0.11),   # 缺口（跳過週末）
        ("2026-07-06", 0.12),   # 缺口（跳過假日）
        ("2026-07-10", 0.14),   # 缺口（缺席觀測）
        ("2026-07-20", 0.16),
        ("2026-07-31", 0.20),   # 視窗右端
    ]
    got = moving_average(points, window_days=30)
    ivs = [0.10, 0.11, 0.12, 0.14, 0.16, 0.20]
    assert got[-1] == ("2026-07-31", mean(ivs))


def test_moving_average_respects_a_custom_window_days():
    points = _daily(date(2026, 8, 1), [0.10, 0.12, 0.14, 0.16, 0.18, 0.20])
    got = moving_average(points, window_days=2)
    # window_days=2：最後一點只看得到往前 2 天（含當天）共 3 筆，仍 ≥5 門檻不成立
    assert got[-1][1] is None


# ---------- bollinger_bands ----------

def test_bollinger_bands_are_none_below_the_minimum_observation_count():
    points = _daily(date(2026, 8, 1), [0.10, 0.12, 0.14])
    got = bollinger_bands(points)
    assert got["upper"][-1] == (points[-1][0], None)
    assert got["lower"][-1] == (points[-1][0], None)


def test_bollinger_bands_match_hand_calculated_mean_plus_minus_two_std():
    ivs = [0.10, 0.12, 0.14, 0.16, 0.18]
    points = _daily(date(2026, 8, 1), ivs)
    got = bollinger_bands(points)
    m, s = mean(ivs), stdev(ivs)
    assert got["upper"][-1][1] == m + 2 * s
    assert got["lower"][-1][1] == m - 2 * s


def test_bollinger_bands_also_returns_the_mean_and_std_series():
    """spec #151 §3 明文簽章：`{upper, lower, mean, std}` 四條序列，不是
    只有上下界。"""
    ivs = [0.10, 0.12, 0.14, 0.16, 0.18]
    points = _daily(date(2026, 8, 1), ivs)
    got = bollinger_bands(points)
    m, s = mean(ivs), stdev(ivs)
    assert got["mean"][-1] == (points[-1][0], m)
    assert got["std"][-1] == (points[-1][0], s)


def test_bollinger_bands_mean_and_std_are_none_below_the_minimum_observation_count():
    points = _daily(date(2026, 8, 1), [0.10, 0.12, 0.14])
    got = bollinger_bands(points)
    assert got["mean"][-1] == (points[-1][0], None)
    assert got["std"][-1] == (points[-1][0], None)


def test_bollinger_bands_are_centered_on_the_same_mean_as_moving_average():
    ivs = [0.10, 0.15, 0.11, 0.20, 0.09, 0.17]
    points = _daily(date(2026, 8, 1), ivs)
    bands = bollinger_bands(points)
    ma = moving_average(points)
    last_upper, last_lower = bands["upper"][-1][1], bands["lower"][-1][1]
    assert (last_upper + last_lower) / 2 == ma[-1][1]


def test_bollinger_bands_respect_a_custom_num_std():
    ivs = [0.10, 0.12, 0.14, 0.16, 0.18]
    points = _daily(date(2026, 8, 1), ivs)
    got = bollinger_bands(points, num_std=1.0)
    m, s = mean(ivs), stdev(ivs)
    assert got["upper"][-1][1] == m + s


# ---------- current_zscore ----------

def test_zscore_is_none_for_an_empty_series():
    assert current_zscore([]) is None


def test_zscore_is_none_below_the_minimum_observation_count():
    points = _daily(date(2026, 8, 1), [0.10, 0.12])
    assert current_zscore(points) is None


def test_zscore_matches_hand_calculated_value():
    ivs = [0.10, 0.12, 0.14, 0.16, 0.30]
    points = _daily(date(2026, 8, 1), ivs)
    m, s = mean(ivs), stdev(ivs)
    assert current_zscore(points) == (ivs[-1] - m) / s


def test_zscore_is_zero_when_the_window_has_no_dispersion():
    points = _daily(date(2026, 8, 1), [0.20] * 6)
    assert current_zscore(points) == 0.0


def test_zscore_uses_the_same_mean_and_std_as_the_last_bollinger_point():
    ivs = [0.10, 0.15, 0.11, 0.20, 0.09, 0.17, 0.22]
    points = _daily(date(2026, 8, 1), ivs)
    z = current_zscore(points)
    bands = bollinger_bands(points)
    upper, lower = bands["upper"][-1][1], bands["lower"][-1][1]
    m, s = (upper + lower) / 2, (upper - lower) / 4
    assert z == pytest.approx((ivs[-1] - m) / s)


# ---------- historical_percentile ----------

def test_percentile_uses_the_inclusive_le_definition():
    """全同值序列回 1.0，不是 0.0——跟 `ivhistory.percentile()` 同一個
    定義選擇：「跟過去一樣」不該被說成「處於歷史最低」。"""
    points = [("2026-08-0" + str(i + 1), 0.20) for i in range(5)]
    assert historical_percentile(points, 0.20) == 1.0


def test_percentile_is_none_when_current_is_none():
    points = [("2026-08-01", 0.20)]
    assert historical_percentile(points, None) is None


def test_percentile_is_none_for_an_empty_series():
    assert historical_percentile([], 0.20) is None


def test_percentile_ignores_null_iv_points():
    points = [("2026-08-01", None), ("2026-08-02", 0.10), ("2026-08-03", 0.30)]
    assert historical_percentile(points, 0.10) == 0.5


def test_percentile_has_no_minimum_observation_gate():
    """單一筆歷史也給百分位——不因為點數少就藏起來（spec AC14）。"""
    points = [("2026-08-01", 0.20)]
    assert historical_percentile(points, 0.20) == 1.0


# ---------- delta_4w ----------

def test_delta_4w_matches_hand_calculated_median_baseline():
    today = date(2026, 8, 17)
    base = [0.10, 0.20, 0.30]   # 中位數 0.20
    points = [((today - timedelta(days=30)).isoformat(), base[0]),
             ((today - timedelta(days=28)).isoformat(), base[1]),
             ((today - timedelta(days=25)).isoformat(), base[2])]
    assert delta_4w(points, latest=0.50, today=today) == 0.50 - 0.20


def test_delta_4w_is_none_when_latest_is_none():
    today = date(2026, 8, 17)
    points = [((today - timedelta(days=28)).isoformat(), 0.20)]
    assert delta_4w(points, latest=None, today=today) is None


def test_delta_4w_is_none_when_the_window_has_no_observations():
    today = date(2026, 8, 17)
    points = [(today.isoformat(), 0.30)]   # 今天，不在 [42,21] 窗內
    assert delta_4w(points, latest=0.30, today=today) is None


def test_delta_4w_ignores_points_outside_the_42_to_21_day_window():
    today = date(2026, 8, 17)
    points = [((today - timedelta(days=50)).isoformat(), 999.0),   # 窗外太遠
             ((today - timedelta(days=28)).isoformat(), 0.20),     # 窗內
             ((today - timedelta(days=1)).isoformat(), 888.0)]     # 窗外太近
    assert delta_4w(points, latest=0.40, today=today) == 0.40 - 0.20


def test_delta_4w_boundary_days_are_inclusive():
    today = date(2026, 8, 17)
    points = [((today - timedelta(days=42)).isoformat(), 0.10),
             ((today - timedelta(days=21)).isoformat(), 0.30)]
    assert delta_4w(points, latest=0.50, today=today) == 0.50 - 0.20


# ---------- 隔離紅線（spec #151 §7／Testing Decisions）----------

def test_this_module_never_imports_ivhistory():
    """雙向零耦合的另一半（HIVT-02 docstring 的宣稱，這裡變成可以紅燈的
    斷言）：exact-contract 家族不 import (tenor,delta) 重錨定家族，即使
    演算法定義沿用同一份邏輯（percentile／trend_4w），也是各自重新實作
    （見本檔案模組 docstring），不是共用同一份程式碼路徑。

    只檢查真正的 `import` 陳述式（用 AST），不是整份原始碼的字串比對——
    模組 docstring 本身就會提到 `ivhistory.py` 這個名字（解釋為什麼不
    import 它），字串式比對會把這句說明文字誤判成違規。
    """
    import ast

    import option_chaser.ivtrend as ivtrend_module

    src = open(ivtrend_module.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any("ivhistory" in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "ivhistory" not in node.module


def test_ranking_and_filters_do_not_depend_on_this_module():
    """spec #117 §5 的既有紅線延伸到新家族：排序與過濾一樣不 import
    `ivtrend`（比照 `tests/test_ivhistory.py` 同名測試對舊家族的斷言）。"""
    import option_chaser.filters as filters
    import option_chaser.ranking as ranking

    for mod in (ranking, filters):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "ivtrend" not in src
