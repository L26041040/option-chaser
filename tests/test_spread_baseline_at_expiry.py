"""T3（issue #17）：排名基準估值＝各 Spread 自身到期日的內在價值。

需求 §三：「標的在該 Spread **到期時**等於目標價、持有至到期」。
基準值因此與 `p.anchor`（附錄 A9 的舊表面參考日）無關，也與 IV 無關——
到期時只剩內在價值。Heatmap 的逐格 BS 估值走另一條路徑，不受本票影響。
"""
from datetime import date

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_spread, spread_scenario_value

TODAY = date(2026, 7, 15)

LONG_STRIKE = 110.0
SHORT_STRIKE = 120.0
WIDTH = SHORT_STRIKE - LONG_STRIKE


def params(target_price: float = 120.0) -> AnalysisParams:
    return AnalysisParams(target_price=target_price, target_month="2026-08",
                          strategy="bull-call-spread")


ANCHOR = params().anchor   # 舊的共用估值日；本票之後基準值不該再受它影響


def legs(expiry: str, long_iv: float = 0.30, short_iv: float = 0.30):
    def make(sym, strike, bid, ask, iv):
        return OptionContract(contract_symbol=sym, option_type="call",
                              strike=strike, expiry=expiry, bid=bid, ask=ask,
                              last=None, volume=10, open_interest=100,
                              implied_volatility=iv)
    return (make("L", LONG_STRIKE, 3.0, 3.25, long_iv),
            make("S", SHORT_STRIKE, 0.80, 0.95, short_iv))


def baseline_for(expiry: str, target_price: float = 120.0) -> float:
    lng, sht = legs(expiry)
    return evaluate_spread(lng, sht, spot=100.0, today=TODAY,
                           p=params(target_price)).baseline_value


# --- 估值時點：三種到期日相對錨點的位置 ------------------------------------

def test_expiry_after_the_anchor_uses_its_own_expiry():
    expiry = "2026-10-16"
    assert date.fromisoformat(expiry) > ANCHOR
    assert baseline_for(expiry) == WIDTH


def test_expiry_equal_to_the_anchor():
    assert baseline_for(ANCHOR.isoformat()) == WIDTH


def test_expiry_before_the_anchor():
    expiry = "2026-07-17"
    assert date.fromisoformat(expiry) < ANCHOR
    assert baseline_for(expiry) == WIDTH


def test_all_three_positions_agree():
    """三種到期日位置的基準值一致——證明估值時點不再是那個共用日期。"""
    values = {baseline_for(e) for e in
              ("2026-07-17", ANCHOR.isoformat(), "2026-10-16", "2027-01-15")}
    assert values == {WIDTH}


# --- payoff 三區段 ---------------------------------------------------------

def test_target_above_both_strikes_pays_the_full_width():
    assert baseline_for("2026-10-16", target_price=140.0) == WIDTH


def test_target_between_the_strikes_pays_the_partial_intrinsic():
    assert baseline_for("2026-10-16", target_price=115.0) == 5.0


def test_target_below_both_strikes_pays_nothing():
    assert baseline_for("2026-10-16", target_price=105.0) == 0.0


def test_target_exactly_at_each_strike():
    assert baseline_for("2026-10-16", target_price=LONG_STRIKE) == 0.0
    assert baseline_for("2026-10-16", target_price=SHORT_STRIKE) == WIDTH


def test_baseline_never_leaves_zero_to_width():
    for target in (1.0, 105.0, 110.0, 115.0, 120.0, 500.0):
        assert 0.0 <= baseline_for("2026-10-16", target_price=target) <= WIDTH


# --- 到期＝內在價值，與 IV 無關 --------------------------------------------

def test_baseline_ignores_implied_volatility():
    """到期時沒有時間價值可言，IV 不得影響基準值。"""
    quiet = evaluate_spread(*legs("2026-10-16", long_iv=0.10, short_iv=0.10),
                            spot=100.0, today=TODAY, p=params(115.0))
    wild = evaluate_spread(*legs("2026-10-16", long_iv=1.20, short_iv=1.20),
                           spot=100.0, today=TODAY, p=params(115.0))
    assert quiet.baseline_value == wild.baseline_value == 5.0


def test_iv_scenarios_collapse_at_expiry():
    """持有至到期的情境向量沒有 IV 不確定性，三檔 shift 必然同值。"""
    lng, sht = legs("2026-10-16")
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=params(115.0))
    assert {v for _, v in sv.scenario_values} == {5.0}
    assert sv.l2 == sv.baseline_value


# --- 與 Heatmap 估值路徑分離 ------------------------------------------------

def test_heatmap_path_still_carries_time_value():
    """同一組腳、同一個 spot，在到期**前**估值必須高於到期內在價值。

    這是兩種語意分離的證據：本票只改排名的估值時點，Heatmap 逐格 BS 不動。
    """
    lng, sht = legs("2026-10-16")
    p = params(115.0)
    before_expiry = spread_scenario_value(lng, sht, 115.0, date(2026, 9, 1), p)
    at_expiry = spread_scenario_value(lng, sht, 115.0, date(2026, 10, 16), p)
    assert at_expiry == 5.0
    assert before_expiry != at_expiry
    assert 0.0 <= before_expiry <= WIDTH
