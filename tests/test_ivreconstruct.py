"""option_chaser/ivreconstruct.py 純函式（HIVR-05／#164，spec #159）。

Round-trip style：大部分「reconstruct 出正確 IV」的測試不硬編一個
猜測的 sigma 當期望值，而是先用既有 `valuation.american_price()`
從一個已知 sigma 算出對應的市場價，餵給 `reconstruct_iv_series()`，
再驗證反解回來的 sigma 貼近原始值——這是驗證一個反解函式最直接的
方式（跟 `test_valuation.py`／`test_american_pricing.py` 既有慣例
一致）。
"""
from datetime import date, timedelta

import pytest

from option_chaser.ivreconstruct import (FAILURE_INVERSION_FAILED,
                                         FAILURE_NO_DIVIDEND_YIELD,
                                         FAILURE_NO_RATE,
                                         FAILURE_UNUSABLE_QUOTE,
                                         LOW_CONFIDENCE_DTE_THRESHOLD,
                                         VENDOR_IV_BENCHMARK_MAX,
                                         VENDOR_IV_BENCHMARK_MIN,
                                         is_low_confidence,
                                         reconstruct_iv_series,
                                         vendor_iv_is_benchmarkable)
from option_chaser.valuation import (DAYS_PER_YEAR, american_price,
                                     days_between)

EXPIRATION = "2027-06-18"
OBS_DATE = "2026-06-18"           # 整整一年前
K = 100.0
S = 95.0
R = 0.04
Q = 0.02
TRUE_SIGMA = 0.22


def _T(obs_date=OBS_DATE, expiration=EXPIRATION):
    return days_between(date.fromisoformat(obs_date),
                        date.fromisoformat(expiration)) / DAYS_PER_YEAR


def _true_price(option_type="call", sigma=TRUE_SIGMA, obs_date=OBS_DATE):
    return american_price(option_type, S, K, _T(obs_date), R, Q, sigma)


def _quote(date_str=OBS_DATE, *, bid=None, ask=None, mid=None,
          underlying_price=S, vendor_iv=None, extra=None):
    q = {"date": date_str, "updated": 1, "dte": 365, "bid": bid, "ask": ask,
        "mid": mid, "underlying_price": underlying_price,
        "vendor_iv": vendor_iv}
    if extra:
        q.update(extra)
    return q


# ---------- 快樂路徑：round-trip 反解 ----------

def test_reconstructs_a_known_sigma_via_round_trip_through_the_pricer():
    price = _true_price()
    quotes = [_quote(bid=price - 0.01, ask=price + 0.01, mid=price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert len(series) == 1
    assert series[0][0] == OBS_DATE
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


def test_reconstructs_a_known_sigma_for_a_put_too():
    price = _true_price(option_type="put")
    quotes = [_quote(bid=price - 0.01, ask=price + 0.01, mid=price)]
    series, failures = reconstruct_iv_series(
        "put", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


def test_one_bad_point_costs_only_that_one_point():
    """三筆觀測，中間一筆缺利率——輸出仍是三筆，壞的那筆是 `None`，
    其餘兩筆的反解結果不受影響。"""
    good_price = _true_price()
    quotes = [
        _quote("2026-06-16", bid=good_price - 0.01, ask=good_price + 0.01,
              mid=good_price),
        _quote("2026-06-17", bid=good_price - 0.01, ask=good_price + 0.01,
              mid=good_price),
        _quote("2026-06-18", bid=good_price - 0.01, ask=good_price + 0.01,
              mid=good_price),
    ]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={"2026-06-16": R, "2026-06-18": R},   # 中間那天缺
        dividend_yield_by_date={"2026-06-16": Q, "2026-06-17": Q,
                                "2026-06-18": Q})
    assert len(series) == 3
    assert series[0][1] is not None
    assert series[1] == ("2026-06-17", None)
    assert series[2][1] is not None
    assert failures == {FAILURE_NO_RATE: 1}


# ---------- price：mid 優先，缺席才退回 bid/ask 中點 ----------

def test_vendor_mid_is_preferred_over_the_bid_ask_midpoint_when_they_differ():
    price = _true_price()
    # bid/ask 中點（price - 2.0）刻意跟 vendor mid（price）不同——如果
    # 模組誤用中點而非 vendor mid，反解出來的 sigma 就不會貼近 TRUE_SIGMA。
    quotes = [_quote(bid=price - 5.0, ask=price + 1.0, mid=price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


def test_falls_back_to_the_bid_ask_midpoint_when_vendor_mid_is_absent():
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=None)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


def test_a_stray_last_field_is_ignored_even_if_present():
    """`_quote` fixture 本身結構上沒有 `last` 欄位（HIVR-04 的寬版 quote
    dict 就是這樣設計的），這裡額外塞一個完全不合理的 `last` 值，確認
    就算某個未來呼叫端不小心夾帶了它，這個模組也不會被牽著走。"""
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=price,
                     extra={"last": 999.0})]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


# ---------- quote 合法性：缺席／非正／倒掛一律視為缺席觀測 ----------

@pytest.mark.parametrize("bid,ask", [
    (None, 5.0),
    (4.0, None),
    (None, None),
    (0.0, 5.0),
    (-1.0, 5.0),
    (4.0, 0.0),
    (4.0, -1.0),
    (5.0, 4.0),        # 倒掛：ask < bid
])
def test_an_invalid_quote_produces_a_missing_point(bid, ask):
    quotes = [_quote(bid=bid, ask=ask, mid=None)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_UNUSABLE_QUOTE: 1}


def test_a_crossed_quote_is_rejected_even_when_vendor_mid_is_present():
    """crossed quote 是資料品質訊號——即使 vendor 剛好給了一個 `mid`，
    也不能因為那個欄位可用就繞過 bid/ask 本身不合法這件事。"""
    quotes = [_quote(bid=5.0, ask=4.0, mid=4.5)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_UNUSABLE_QUOTE: 1}


def test_missing_underlying_price_produces_a_missing_point():
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=price,
                     underlying_price=None)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_UNUSABLE_QUOTE: 1}


# ---------- r／q：呼叫端逐筆觀測日供給，模組本身不抓取 ----------

def test_missing_rate_for_the_observation_date_produces_a_missing_point():
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_NO_RATE: 1}


def test_explicit_none_rate_is_the_same_as_a_missing_key():
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: None}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_NO_RATE: 1}


def test_missing_dividend_yield_for_the_observation_date_produces_a_missing_point():
    price = _true_price()
    quotes = [_quote(bid=price - 0.5, ask=price + 0.5, mid=price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_NO_DIVIDEND_YIELD: 1}


def test_rate_and_dividend_yield_are_looked_up_per_observation_date_not_shared():
    """兩筆觀測各自不同日期，各自的 r／q 各自查表——不是整批共用同一組
    數字。用不同 r 反解同一個已知價格會得到不同 sigma，藉此證明真的有
    逐筆查表，不是只認第一筆或某個預設值。"""
    price_low_r = american_price("call", S, K, _T("2026-06-16"), 0.01, Q,
                                 TRUE_SIGMA)
    price_high_r = american_price("call", S, K, _T("2026-06-17"), 0.08, Q,
                                  TRUE_SIGMA)
    quotes = [
        _quote("2026-06-16", bid=price_low_r - 0.01, ask=price_low_r + 0.01,
              mid=price_low_r),
        _quote("2026-06-17", bid=price_high_r - 0.01, ask=price_high_r + 0.01,
              mid=price_high_r),
    ]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={"2026-06-16": 0.01, "2026-06-17": 0.08},
        dividend_yield_by_date={"2026-06-16": Q, "2026-06-17": Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)
    assert series[1][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


# ---------- T：從該筆觀測自己的日期算，不是 today ----------

def test_time_to_expiry_is_measured_from_each_observations_own_date():
    """兩筆觀測分屬不同日期、因此不同 T——各自代入自己的 T 反解同一個
    已知 sigma 才會準；如果模組錯用同一個 T（例如都用 today 或都用
    第一筆的日期），其中一筆的反解會明顯偏離 TRUE_SIGMA。"""
    early_date, late_date = "2026-01-01", "2026-06-01"
    price_early = american_price("call", S, K, _T(early_date), R, Q,
                                 TRUE_SIGMA)
    price_late = american_price("call", S, K, _T(late_date), R, Q,
                                TRUE_SIGMA)
    quotes = [
        _quote(early_date, bid=price_early - 0.01, ask=price_early + 0.01,
              mid=price_early),
        _quote(late_date, bid=price_late - 0.01, ask=price_late + 0.01,
              mid=price_late),
    ]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={early_date: R, late_date: R},
        dividend_yield_by_date={early_date: Q, late_date: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)
    assert series[1][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


# ---------- 反解無解 ----------

def test_an_unsolvable_target_price_produces_a_missing_point_not_a_guess():
    """價格高到連 `implied_vol` 搜尋上界（sigma=5.0）都算不出這麼貴——
    數學上無解，不得外插或硬湊一個數字。"""
    absurd_price = S + K   # 遠高於任何合理的時間價值上限
    quotes = [_quote(bid=absurd_price - 1.0, ask=absurd_price + 1.0,
                     mid=absurd_price)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert series == [(OBS_DATE, None)]
    assert failures == {FAILURE_INVERSION_FAILED: 1}


# ---------- vendor_iv：canonical series 絕不採用 ----------

def test_vendor_iv_is_never_used_even_when_present_and_non_null():
    """`vendor_iv` 故意設成一個跟真實反解結果差很多的數字——輸出必須
    是反解出來的值，不是 vendor 給的那個。"""
    price = _true_price()
    quotes = [_quote(bid=price - 0.01, ask=price + 0.01, mid=price,
                     vendor_iv=0.99)]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)
    assert series[0][1] != pytest.approx(0.99, abs=0.01)


def test_reconstruction_works_even_without_a_vendor_iv_key_at_all():
    """結構性佐證：這個模組壓根不需要讀 `vendor_iv` 這把鑰匙——就算
    quote dict 完全不帶它，反解照常成立。"""
    price = _true_price()
    quote = {"date": OBS_DATE, "updated": 1, "dte": 365,
             "bid": price - 0.01, "ask": price + 0.01, "mid": price,
             "underlying_price": S}   # 沒有 "vendor_iv" 這把鑰匙
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, [quote],
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    assert failures == {}
    assert series[0][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


# ---------- 輸出形狀：ivtrend.py 既有統計函式直接吃得下 ----------

def test_output_is_directly_consumable_by_the_existing_statistics_functions():
    """不重測 `ivtrend.py` 本身的邏輯（那是它自己的測試範圍）——這裡只
    證明輸出形狀真的能餵給既有函式，不需要任何轉接層。"""
    from option_chaser.ivtrend import historical_percentile, trim_to_window

    price = _true_price()
    quotes = [_quote(bid=price - 0.01, ask=price + 0.01, mid=price)]
    series, _ = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})

    trimmed = trim_to_window(series, today=date(2026, 8, 17))
    assert trimmed == series
    assert historical_percentile(series, series[0][1]) == 1.0


# ---------- 逐原因計數 ----------

def test_failure_counts_are_tallied_by_distinct_reason():
    p2 = _true_price(obs_date="2026-06-02")
    p3 = _true_price(obs_date="2026-06-03")
    p5 = _true_price(obs_date="2026-06-05")
    quotes = [
        _quote("2026-06-01", bid=None, ask=None),                    # unusable
        _quote("2026-06-02", bid=p2 - 0.5, ask=p2 + 0.5, mid=p2),    # no rate
        _quote("2026-06-03", bid=p3 - 0.5, ask=p3 + 0.5, mid=p3),    # no q
        _quote("2026-06-04", bid=S + K - 1.0, ask=S + K + 1.0,
              mid=S + K),                                            # inversion
        _quote("2026-06-05", bid=p5 - 0.5, ask=p5 + 0.5, mid=p5),    # ok
    ]
    series, failures = reconstruct_iv_series(
        "call", K, EXPIRATION, quotes,
        rate_by_date={"2026-06-01": R, "2026-06-03": R, "2026-06-04": R,
                      "2026-06-05": R},
        dividend_yield_by_date={"2026-06-01": Q, "2026-06-02": Q,
                                "2026-06-04": Q, "2026-06-05": Q})
    assert len(series) == 5
    assert failures == {FAILURE_UNUSABLE_QUOTE: 1, FAILURE_NO_RATE: 1,
                        FAILURE_NO_DIVIDEND_YIELD: 1,
                        FAILURE_INVERSION_FAILED: 1}
    assert series[0] == ("2026-06-01", None)
    assert series[1] == ("2026-06-02", None)
    assert series[2] == ("2026-06-03", None)
    assert series[3] == ("2026-06-04", None)
    assert series[4][1] == pytest.approx(TRUE_SIGMA, abs=1e-6)


# ---------- 近到期 low-confidence 標記（HIVR-08／#167） ----------

def test_points_at_or_beyond_the_threshold_are_not_flagged():
    exp = "2027-06-18"
    # 恰好等於門檻的那一天不算 low confidence（AC：「等於門檻」不算）。
    threshold_date = date.fromisoformat(exp)
    at_threshold = threshold_date - timedelta(days=LOW_CONFIDENCE_DTE_THRESHOLD)
    well_before = threshold_date - timedelta(days=LOW_CONFIDENCE_DTE_THRESHOLD + 30)
    assert is_low_confidence(at_threshold.isoformat(), exp) is False
    assert is_low_confidence(well_before.isoformat(), exp) is False


def test_points_inside_the_threshold_are_flagged():
    exp = "2027-06-18"
    threshold_date = date.fromisoformat(exp)
    one_day_inside = threshold_date - timedelta(
        days=LOW_CONFIDENCE_DTE_THRESHOLD - 1)
    on_expiry_day = threshold_date
    assert is_low_confidence(one_day_inside.isoformat(), exp) is True
    assert is_low_confidence(on_expiry_day.isoformat(), exp) is True


def test_the_threshold_is_a_single_named_constant():
    assert LOW_CONFIDENCE_DTE_THRESHOLD == 14


def test_low_confidence_can_be_evaluated_for_a_missing_observation_too():
    """反解失敗、`iv` 是 `None` 的觀測，天數比較照樣成立——這個函式不讀
    price／IV，純粹是天數比較，呼叫端可以對序列裡每一筆（不論成敗）
    一視同仁地套用。"""
    assert is_low_confidence("2027-06-17", "2027-06-18") is True
    assert is_low_confidence("2026-01-01", "2027-06-18") is False


# ---------- vendor IV benchmark 合理性 gate（HIVR-09／#168） ----------

def test_the_bounds_are_the_documented_constants():
    assert VENDOR_IV_BENCHMARK_MIN == 0.01
    assert VENDOR_IV_BENCHMARK_MAX == 5.0


def test_a_real_observed_degenerate_value_is_excluded():
    """真實 calibration 資料裡出現過的退化值（`ORCL260821C00136000`
    的 `vendor_iv=0.0001`）——比下界還低了兩個數量級，必須被排除。"""
    assert vendor_iv_is_benchmarkable(0.0001) is False


def test_values_at_the_bounds_are_benchmarkable():
    """AC「等於門檻」不算超界——上下界本身都在合理範圍內。"""
    assert vendor_iv_is_benchmarkable(VENDOR_IV_BENCHMARK_MIN) is True
    assert vendor_iv_is_benchmarkable(VENDOR_IV_BENCHMARK_MAX) is True


def test_values_just_outside_the_bounds_are_excluded():
    assert vendor_iv_is_benchmarkable(VENDOR_IV_BENCHMARK_MIN - 0.001) is False
    assert vendor_iv_is_benchmarkable(VENDOR_IV_BENCHMARK_MAX + 0.001) is False


def test_a_typical_value_well_inside_the_bounds_is_benchmarkable():
    assert vendor_iv_is_benchmarkable(0.22) is True


def test_a_missing_vendor_iv_is_not_benchmarkable_either():
    """`None`＝vendor 對這天沒有值，不是退化值，但同樣不可比較——不是
    `True`（沒東西可比較），也不該讓呼叫端自己去猜怎麼比較 `None`。"""
    assert vendor_iv_is_benchmarkable(None) is False


def test_the_upper_bound_matches_the_solvers_own_search_ceiling():
    """上界不是憑空挑的：跟 `implied_vol()` 自己的搜尋上限（`hi=5.0`）
    對齊——這個模組本身的反解結構上不可能回超過這個值，這裡直接讀
    `implied_vol` 的預設參數值來鎖住這個關聯，而不是抄一份可能漂移的
    數字。"""
    import inspect

    from option_chaser.valuation import implied_vol

    hi_default = inspect.signature(implied_vol).parameters["hi"].default
    assert VENDOR_IV_BENCHMARK_MAX == hi_default


def test_the_gate_never_alters_the_canonical_series():
    """AC：同樣的報價序列，唯一差別是其中一筆的 `vendor_iv` 換成一個
    退化值（gate 會排除的那種）——canonical series 必須逐位元相同。這個
    模組物理上不讀 `vendor_iv`（見 `reconstruct_iv_series` 本身與模組
    開頭說明），這裡直接跑一次證明給定輸入確實如此，不是憑空宣稱。"""
    price = _true_price()
    quote_kwargs = dict(bid=price - 0.01, ask=price + 0.01, mid=price)

    with_degenerate_vendor_iv = [_quote(**quote_kwargs, vendor_iv=0.0001)]
    with_normal_vendor_iv = [_quote(**quote_kwargs, vendor_iv=0.25)]
    with_no_vendor_iv = [_quote(**quote_kwargs, vendor_iv=None)]

    series_degenerate, _ = reconstruct_iv_series(
        "call", K, EXPIRATION, with_degenerate_vendor_iv,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    series_normal, _ = reconstruct_iv_series(
        "call", K, EXPIRATION, with_normal_vendor_iv,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})
    series_absent, _ = reconstruct_iv_series(
        "call", K, EXPIRATION, with_no_vendor_iv,
        rate_by_date={OBS_DATE: R}, dividend_yield_by_date={OBS_DATE: Q})

    assert series_degenerate == series_normal == series_absent


# ---------- 隔離紅線（spec #151 §7／Testing Decisions 延伸） ----------

def test_this_module_never_imports_ivhistory():
    import ast

    import option_chaser.ivreconstruct as ivreconstruct_module

    src = open(ivreconstruct_module.__file__, encoding="utf-8").read()
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
        assert "ivreconstruct" not in src
