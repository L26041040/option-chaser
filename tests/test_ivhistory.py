"""(tenor, delta) 重錨定與相對位置的純函式（#126／#114／#138）。

重點在**邊界**：不外插、不拿最長天期頂替、湊不出來就回 None。這幾條
是 #114 AC 明文要求的，不是實作細節。
"""
from datetime import date, timedelta

import pytest

from option_chaser.ivhistory import (ATM_DELTA, SurfacePoint,
                                     leg_coordinate, iv_at,
                                     nearby_expirations, normalized_skew,
                                     percentile, reanchor_spread,
                                     spread_coordinates, trend_4w)


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


# ---------- Long Call 單腳座標路徑（#139／spec #137）----------

def _single_leg_candidate(*, option_type="call", rate_used=0.04, dte=400):
    return {
        "days_to_expiry": dte,
        "rate_used": rate_used,
        "legs": [{"option_type": option_type, "strike": 95.0, "iv": 0.22}],
    }


def test_single_leg_candidate_gets_a_buy_coordinate():
    """新增能力：現況 `len(legs) < 2` 直接回 None（MVP V3 明文只做
    Spread）——這是那個限制的解除。"""
    coords = spread_coordinates(_single_leg_candidate(), spot=100.0)
    assert coords is not None
    assert "buy" in coords


def test_single_leg_candidate_has_no_sell_coordinate():
    """沒有賣腿就沒有這個座標——誠實的『沒有這個量』，不是缺陷。"""
    coords = spread_coordinates(_single_leg_candidate(), spot=100.0)
    assert "sell" not in coords


def test_single_leg_coordinates_carry_the_leg_option_type():
    call_coords = spread_coordinates(_single_leg_candidate(option_type="call"),
                                     spot=100.0)
    put_coords = spread_coordinates(_single_leg_candidate(option_type="put"),
                                    spot=100.0)
    assert call_coords["option_type"] == "call"
    assert put_coords["option_type"] == "put"


def test_single_leg_candidate_inherits_the_rate_used_redline():
    """#134 的紅線不因單腳而不同：座標要跟正式估值管線用同一個利率。"""
    with_real_rate = spread_coordinates(
        _single_leg_candidate(rate_used=0.04), spot=100.0)
    with_zero_rate = spread_coordinates(
        _single_leg_candidate(rate_used=0.0), spot=100.0)
    assert with_real_rate["buy"].delta != with_zero_rate["buy"].delta


def test_no_parallel_implementation_same_buy_leg_yields_the_same_coordinate():
    """#139 AC：單腳與兩腿候選的買腿座標必須一模一樣——同一組買腿參數，
    不因為候選是單腳還是兩腿而走出兩套不同的計算路徑。"""
    buy_leg = {"option_type": "call", "strike": 95.0, "iv": 0.22}
    two_leg = {"days_to_expiry": 400, "rate_used": 0.04,
              "legs": [buy_leg, {"option_type": "call", "strike": 105.0,
                                 "iv": 0.20}]}
    one_leg = {"days_to_expiry": 400, "rate_used": 0.04, "legs": [buy_leg]}

    two_leg_coords = spread_coordinates(two_leg, spot=100.0)
    one_leg_coords = spread_coordinates(one_leg, spot=100.0)
    assert two_leg_coords["buy"] == one_leg_coords["buy"]


def _grid_by_type():
    """call 與 put 用不同的 IV 水準，讓測試能分辨「用哪一張網格查」。
    delta 蓋到 0.1–0.9：測試候選（strike 95／spot 100／dte 30）算出來的
    call delta ≈0.82、put delta ≈0.18，網格太窄會插不出值。"""
    call_pts = [SurfacePoint(dte=30, delta=d, iv=0.20)
               for d in (0.1, 0.25, 0.5, 0.75, 0.9)]
    put_pts = [SurfacePoint(dte=30, delta=d, iv=0.50)
              for d in (0.1, 0.25, 0.5, 0.75, 0.9)]
    return {"call": call_pts, "put": put_pts}


def test_reanchor_single_leg_reads_the_leg_own_option_type_grid():
    """Long Put 的買腿要用 put 網格查，不能沿用寫死的 call（會查到錯的
    網格、算出一個看起來正常但其實錯誤的數字——比誠實回 None 更糟）。"""
    put_coords = spread_coordinates(_single_leg_candidate(option_type="put",
                                                          dte=30), spot=100.0)
    got = reanchor_spread(_grid_by_type(), put_coords)
    assert got["buy_iv"] == pytest.approx(0.50)   # 來自 put 網格，不是 call 的 0.20


def test_reanchor_single_leg_has_no_sell_iv_or_skew():
    call_coords = spread_coordinates(_single_leg_candidate(dte=30), spot=100.0)
    got = reanchor_spread(_grid_by_type(), call_coords)
    assert got["buy_iv"] is not None
    assert got["sell_iv"] is None
    assert got["normalized_skew"] is None


def test_reanchor_two_leg_call_spread_is_unchanged_by_the_option_type_lookup():
    """兩腿路徑（既有 bull call spread）的數值不因這次修改而變——買腿是
    call，`coords["option_type"]` 算出來也是 call，跟修正前寫死 call
    完全同一個結果。"""
    two_leg = _candidate(dte=30)
    coords = spread_coordinates(two_leg, spot=100.0)
    got = reanchor_spread(_grid_by_type(), coords)
    assert got["buy_iv"] == pytest.approx(0.20)
    assert got["sell_iv"] == pytest.approx(0.20)


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


# ---------- Δ4w 趨勢統計量（#138／spec #137 Gate 2）----------

_TODAY = date(2026, 8, 12)


def _iso(days_ago):
    return (_TODAY - timedelta(days=days_ago)).isoformat()


def test_delta_4w_is_latest_minus_the_window_median():
    """基準＝[today-42, today-21] 窗內觀測的中位數，不是單一最近點。"""
    obs = [(_iso(35), 0.20), (_iso(28), 0.22), (_iso(21), 0.24),
          (_iso(3), 0.30)]
    delta, base_count = trend_4w(obs, latest=0.30, today=_TODAY)
    # 窗內三筆：0.20, 0.22, 0.24 → 中位數 0.22
    assert delta == pytest.approx(0.30 - 0.22)
    assert base_count == 3


def test_delta_4w_median_absorbs_a_single_outlier_in_the_window():
    """Gate 2 決策的守門測試：基準若取單一最近點，一筆離群報價就能憑空
    捏造整個趨勢數字；中位數對窗內 1–2 筆離群觀測穩健。"""
    # 窗內四筆乾淨觀測（都在 0.20 附近）＋一筆離群報價（0.90，且是窗內
    # 離 28 天前最近的一點——若基準取單點會直接選中它）。
    clean = [(_iso(40), 0.19), (_iso(35), 0.20), (_iso(30), 0.21),
            (_iso(25), 0.20)]
    outlier_day = _iso(28)   # 離 today-28 最近
    with_outlier = clean + [(outlier_day, 0.90)]

    delta_clean, _ = trend_4w(clean, latest=0.30, today=_TODAY)
    delta_with_outlier, base_count = trend_4w(with_outlier, latest=0.30,
                                              today=_TODAY)

    # 中位數幾乎不被那一筆離群值移動——遠遠不到「單點基準取中離群值」
    # 會產生的差距（0.30-0.90 = -0.60 vs 乾淨基準的正常量級）。
    assert delta_with_outlier == pytest.approx(delta_clean, abs=0.02)
    assert base_count == 5
    # 反證：如果基準是單點（挑窗內離 28 天前最近的那筆），離群值會被
    # 選中，Δ4w 會變成一個離譜的負值——確認乾淨版本本身不是那個量級。
    single_point_would_be = 0.30 - 0.90
    assert abs(delta_with_outlier - single_point_would_be) > 0.3


def test_delta_4w_is_none_when_the_window_has_no_observation():
    """窗內一筆有效觀測都沒有 → None，不外推、不拿窗外較近的點頂替。"""
    obs = [(_iso(50), 0.20), (_iso(10), 0.30)]   # 都在 [21,42] 窗外
    delta, base_count = trend_4w(obs, latest=0.30, today=_TODAY)
    assert delta is None
    assert base_count == 0


def test_delta_4w_ignores_none_values_inside_the_window():
    obs = [(_iso(30), None), (_iso(25), 0.22)]
    delta, base_count = trend_4w(obs, latest=0.30, today=_TODAY)
    assert delta == pytest.approx(0.30 - 0.22)
    assert base_count == 1


def test_delta_4w_is_none_when_there_is_no_latest_value():
    """欄位完全沒有觀測（`value` 為 None）時，趨勢也是 None——沒有『最新
    觀測』就沒有『減去基準』這件事。"""
    obs = [(_iso(30), 0.20)]
    delta, base_count = trend_4w(obs, latest=None, today=_TODAY)
    assert delta is None
    assert base_count == 0


def test_delta_4w_window_boundaries_are_inclusive():
    """窗口是 [today-42, today-21]（兩端含），不是開區間。"""
    at_far_edge = trend_4w([(_iso(42), 0.20)], latest=0.30, today=_TODAY)
    at_near_edge = trend_4w([(_iso(21), 0.20)], latest=0.30, today=_TODAY)
    just_outside_far = trend_4w([(_iso(43), 0.20)], latest=0.30, today=_TODAY)
    just_outside_near = trend_4w([(_iso(20), 0.20)], latest=0.30, today=_TODAY)

    assert at_far_edge[1] == 1
    assert at_near_edge[1] == 1
    assert just_outside_far[1] == 0
    assert just_outside_near[1] == 0


def test_ranking_and_filters_do_not_depend_on_this_module():
    """spec #117 §5 的硬紅線在結構上成立：排序與過濾根本不 import 它，
    所以「移除整個 IV 模組後每個候選的命運與順序不變」不是靠測試巡邏，
    是靠沒有那條邊。"""
    import option_chaser.filters as filters
    import option_chaser.ranking as ranking

    for mod in (ranking, filters):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "ivhistory" not in src
