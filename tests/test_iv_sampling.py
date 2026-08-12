"""抽樣排程與時間加權 percentile（#128）。

這兩組純函式是 quota 架構的數學核心，因此測的重點是需求方點名的三件
事：抽樣密度改變不該憑空改變 percentile、全同值仍得到合理值、缺漏不被
偷偷插值成假資料。
"""
from datetime import date, timedelta

import pytest

from option_chaser.ivhistory import (coverage_ratio, interval_weights,
                                     sampling_schedule, weighted_percentile)

TODAY = date(2026, 8, 12)


# ---------- 抽樣排程 ----------

def test_schedule_lands_in_the_sixty_to_seventy_range():
    """不是 250+，也不是縮成只有 30D／90D 的那種少。"""
    got = sampling_schedule("TLT", TODAY)
    assert 55 <= len(got) <= 75, len(got)


def test_recent_ninety_days_are_denser_than_the_older_stretch():
    got = [date.fromisoformat(d) for d in sampling_schedule("TLT", TODAY)]
    recent = [d for d in got if (TODAY - d).days <= 90]
    older = [d for d in got if (TODAY - d).days > 90]
    # 每天的密度：近期應該明顯較密（約 2/週 vs 1/週）
    assert len(recent) / 90 > 1.6 * (len(older) / 275)


def test_the_full_year_is_still_covered():
    """核心目的之一是 1Y percentile 的長期脈絡——不得偷偷縮窗。"""
    got = [date.fromisoformat(d) for d in sampling_schedule("TLT", TODAY)]
    assert max((TODAY - d).days for d in got) > 330


def test_schedule_is_deterministic():
    """不決定性的話 backfill 每次都在追一份移動的目標，已抓的全部作廢。"""
    assert sampling_schedule("TLT", TODAY) == sampling_schedule("TLT", TODAY)


def test_different_symbols_get_different_schedules():
    assert sampling_schedule("TLT", TODAY) != sampling_schedule("SPY", TODAY)


def test_no_weekends():
    got = [date.fromisoformat(d) for d in sampling_schedule("TLT", TODAY)]
    assert all(d.weekday() < 5 for d in got)


def test_today_is_not_sampled():
    """當日 EOD 通常還沒結算。"""
    assert TODAY.isoformat() not in sampling_schedule("TLT", TODAY)


def test_the_schedule_does_not_always_land_on_one_weekday():
    """固定星期幾會系統性放大或抹平任何具星期效應的市場結構。"""
    days: list[int] = []
    for sym in ("TLT", "SPY", "QQQ", "IWM", "GLD"):
        days += [date.fromisoformat(d).weekday()
                 for d in sampling_schedule(sym, TODAY)]
    seen = {d: days.count(d) for d in set(days)}
    assert len(seen) == 5, seen                       # 五個交易日都出現過
    assert max(seen.values()) / len(days) < 0.40      # 沒有哪一天獨大


def test_dates_are_sorted_and_unique():
    got = sampling_schedule("TLT", TODAY)
    assert got == sorted(set(got))


# ---------- 時間權重 ----------

def _dates(*offsets):
    return [(TODAY - timedelta(days=o)).isoformat() for o in sorted(offsets, reverse=True)]


def test_evenly_spaced_observations_carry_equal_weight():
    w = interval_weights(_dates(30, 20, 10))
    assert w[0] == pytest.approx(w[-1], abs=1e-9)


def test_a_sparse_observation_represents_more_time_than_a_dense_one():
    # 兩個相鄰一天的點 ＋ 一個遠離的點
    w = interval_weights(_dates(200, 11, 10))
    assert w[0] > w[-1]


def test_one_observation_cannot_speak_for_an_unbounded_gap():
    """長空窗不該由旁邊那一個點代言——那就是插值。"""
    w = interval_weights(_dates(360, 5))
    assert max(w) <= 14.0


def test_coverage_reports_how_much_of_the_window_is_actually_backed():
    """稀疏到不足以支撐 percentile 時，#130 靠這個數字說「資料不足」。"""
    assert coverage_ratio(_dates(300, 200, 100)) < 0.2
    assert coverage_ratio(sampling_schedule("TLT", TODAY)) > 0.8


def test_no_observations_means_no_coverage():
    assert coverage_ratio([]) == 0.0


# ---------- 加權 percentile ----------

def _regime_series():
    """真實情況：近 90 天處於高檔（1.0），更早的 275 天處於低檔（0.0）。

    時間加權的正確答案 ＝ 低檔佔的時間比例 ＝ 275/365 ≈ 0.753。
    """
    out = []
    for age in range(1, 366):
        day = (TODAY - timedelta(days=age)).isoformat()
        out.append((day, 1.0 if age <= 90 else 0.0))
    return out


def _sample(series, keep):
    return [(d, v) for d, v in series if keep(d)]


def test_changing_sampling_density_does_not_move_the_percentile_much():
    """需求方點名的第一條：近期高密度不得把 percentile 拉歪。"""
    truth = _regime_series()
    dense_recent = _sample(truth, lambda d: d in set(sampling_schedule("TLT", TODAY)))
    uniform = [truth[i] for i in range(0, len(truth), 7)]

    a = weighted_percentile(dense_recent, 0.5)
    b = weighted_percentile(uniform, 0.5)
    assert a == pytest.approx(b, abs=0.08), (a, b)


def test_the_weighted_percentile_tracks_real_elapsed_time():
    """275/365 ≈ 0.753。天真等權在這組抽樣下會掉到 0.6 附近。"""
    truth = _regime_series()
    dense_recent = _sample(truth, lambda d: d in set(sampling_schedule("TLT", TODAY)))
    assert weighted_percentile(dense_recent, 0.5) == pytest.approx(0.753, abs=0.08)


def test_naive_equal_weighting_would_have_been_wrong():
    """把上一條的對照組寫出來——這正是不能等權的理由，不是理論顧慮。"""
    truth = _regime_series()
    picked = _sample(truth, lambda d: d in set(sampling_schedule("TLT", TODAY)))
    naive = sum(1 for _, v in picked if v <= 0.5) / len(picked)
    assert abs(naive - 0.753) > 0.1


def test_an_unchanged_history_reads_as_the_top_not_the_bottom():
    """需求方點名的第二條。"""
    same = [(d, 0.2) for d, _ in _regime_series()[:50]]
    assert weighted_percentile(same, 0.2) == 1.0


def test_missing_observations_are_dropped_not_filled():
    """需求方點名的第三條：缺的就是缺的，不用鄰居補。"""
    obs = [(d, None) for d in _dates(300, 250, 200)] \
        + [(d, 0.5) for d in _dates(10, 5)]
    # 只有兩個有值的點，兩個都 <= 0.5 → 1.0；若缺漏被補成 0.0 之類的假值，
    # 這個數字會被稀釋
    assert weighted_percentile(obs, 0.5) == 1.0


def test_all_missing_means_no_percentile_at_all():
    obs = [(d, None) for d in _dates(300, 200, 100)]
    assert weighted_percentile(obs, 0.5) is None


def test_no_percentile_without_a_current_value():
    assert weighted_percentile([(d, 0.2) for d in _dates(10)], None) is None


def test_empty_history_has_no_percentile():
    assert weighted_percentile([], 0.2) is None
