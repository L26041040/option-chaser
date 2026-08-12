"""(tenor, delta) 重錨定與相對位置的純函式（#126／#114）。

重點在**邊界**：不外插、不拿最長天期頂替、湊不出來就回 None。這幾條
是 #114 AC 明文要求的，不是實作細節。
"""
from datetime import date

import pytest

from option_chaser.ivhistory import (ATM_DELTA, SurfacePoint,
                                     leg_coordinate, iv_at,
                                     nearby_expirations, normalized_skew,
                                     percentile, spread_coordinates)


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

# ---------- 座標的利率語意（#134）----------

def test_leg_coordinate_defaults_to_zero_rate_when_unspecified():
    """不傳 `rate` 時維持舊行為（r=0）——呼叫端沒給就是沒給，不是這個
    函式自己該去哪裡查表。"""
    zero = leg_coordinate(option_type="call", strike=100.0, iv=0.24,
                          spot=100.0, days_to_expiry=365)
    explicit = leg_coordinate(option_type="call", strike=100.0, iv=0.24,
                              spot=100.0, days_to_expiry=365, rate=0.0)
    assert zero == explicit


def test_leg_coordinate_rate_changes_the_delta():
    """r 進 Black-Scholes 的 d1／d2，改了 r 應該改到 delta——這是後面
    `spread_coordinates` 該不該把 `rate_used` 傳進來的先決條件：如果
    這裡不吃 r，傳不傳都沒差，那條修正就是假的。"""
    at_zero = leg_coordinate(option_type="call", strike=100.0, iv=0.24,
                             spot=100.0, days_to_expiry=365, rate=0.0)
    at_real = leg_coordinate(option_type="call", strike=100.0, iv=0.24,
                             spot=100.0, days_to_expiry=365, rate=0.04)
    assert at_zero.delta != at_real.delta


def _candidate(*, rate_used=0.04, dte=400):
    return {
        "days_to_expiry": dte,
        "rate_used": rate_used,
        "legs": [
            {"option_type": "call", "strike": 95.0, "iv": 0.22},
            {"option_type": "call", "strike": 105.0, "iv": 0.20},
        ],
    }


def test_spread_coordinates_uses_the_candidate_own_rate_used():
    """紅線（#134）：Historical IV 的座標要跟正式估值管線用同一個利率
    ——不是另外取 0。`rate_used` 就是 `leg_rate(p, expiry)` 的查表結果
    （`CandidateView.rate_used`），已經序列化在候選 view dict 裡。"""
    with_real_rate = spread_coordinates(_candidate(rate_used=0.04), spot=100.0)
    with_zero_rate = spread_coordinates(_candidate(rate_used=0.0), spot=100.0)
    assert with_real_rate is not None and with_zero_rate is not None
    assert with_real_rate["buy"].delta != with_zero_rate["buy"].delta


def test_spread_coordinates_tolerates_a_missing_rate_used():
    """舊資料或算不出 `rate_used` 的候選（理論上不該發生，但別因此整組
    炸掉）：退回 r=0，跟修正前的行為一致，不是拋例外。"""
    cand = _candidate()
    del cand["rate_used"]
    assert spread_coordinates(cand, spot=100.0) is not None


# ---------- 歷史回補要鎖定哪些到期日（#134）----------

def test_short_tenor_candidates_get_no_targeted_expirations():
    """vendor 預設（不帶 `expiration`）本就回下一個月選，短天期候選
    原本就抓得到——回空讓呼叫端照舊用那個免費的預設請求。"""
    known = ["2026-09-18", "2026-10-16", "2028-06-16"]
    assert nearby_expirations(known, today=date(2026, 8, 12),
                              tenor_days=20) == []


def test_long_tenor_candidates_get_the_nearest_known_expiries():
    """長天期候選（vendor 預設覆蓋不到）要鎖定離目標 tenor 最近的到期
    日——這正是修正「連線成功但無資料」的機制。"""
    known = ["2026-09-18", "2028-05-19", "2028-06-16", "2028-07-21",
            "2030-01-18"]
    # 今天 + 700 天 ≈ 2028-07-13，離它最近的是 07-21（8 天）與 06-16（27 天）。
    got = nearby_expirations(known, today=date(2026, 8, 12), tenor_days=700,
                             limit=2)
    assert got == ["2028-07-21", "2028-06-16"]


def test_nearby_expirations_never_invents_a_date_not_already_known():
    """只從『這個 Scenario 已經分析過』的到期日裡挑——不額外查
    expirations 清單，這是 credit-conscious 的關鍵：zero 額外 vendor 成本。"""
    known = ["2028-06-16", "2028-07-21"]
    got = nearby_expirations(known, today=date(2026, 8, 12), tenor_days=9999)
    assert set(got) <= set(known)


def test_no_known_expiries_yields_no_targets():
    assert nearby_expirations([], today=date(2026, 8, 12), tenor_days=700) == []


def test_ranking_and_filters_do_not_depend_on_this_module():
    """spec #117 §5 的硬紅線在結構上成立：排序與過濾根本不 import 它，
    所以「移除整個 IV 模組後每個候選的命運與順序不變」不是靠測試巡邏，
    是靠沒有那條邊。"""
    import option_chaser.filters as filters
    import option_chaser.ranking as ranking

    for mod in (ranking, filters):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "ivhistory" not in src
