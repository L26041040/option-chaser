from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import bs_call, evaluate_contract

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=23)


def make_contract(**kw):
    base = dict(contract_symbol="XYZ261016C00110000", option_type="call", strike=110.0,
                expiry="2026-10-16", bid=3.0, ask=3.25, last=3.1,
                volume=152, open_interest=830, implied_volatility=0.38)
    base.update(kw)
    return OptionContract(**base)


def test_mid_spread_breakeven_lambda():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    assert v.mid == 3.125
    assert abs(v.spread - 0.25) < 1e-12
    assert v.breakeven == 113.125                       # strike + mid
    assert abs(v.breakeven_vs_spot - 0.13125) < 1e-9    # (be-spot)/spot
    assert abs(v.breakeven_vs_target - (120 - 113.125) / 120) < 1e-9
    assert abs(v.effective_leverage - v.delta * 100.0 / 3.125) < 1e-9


def test_scenario_values_match_bs():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert v.floor_value == 10.0  # max(120-110,0)
    shifts = [s for s, _ in v.scenario_values]
    assert shifts == [-0.2, 0.0, 0.2]
    for shift, val in v.scenario_values:
        expected = bs_call(120.0, 110.0, t_rem, P.rate, 0.38 * (1 + shift))
        assert abs(val - expected) < 1e-12
    assert v.baseline_value == dict(v.scenario_values)[0.0]


def test_stress_scenarios():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert abs(v.stress_half - bs_call(110.0, 110.0, t_rem, P.rate, 0.38)) < 1e-12
    t_delay = (date(2026, 10, 16) - date(2026, 8, 28)).days - 23
    assert abs(v.stress_delay - bs_call(120.0, 110.0, t_delay / 365.0, P.rate, 0.38)) < 1e-12
    assert abs(v.stress_flat - bs_call(100.0, 110.0, t_rem, P.rate, 0.38)) < 1e-12


def test_delay_zero_skips_delay_scenario():
    p0 = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=p0)
    assert v.stress_delay is None


def test_expiry_equals_target_date_uses_intrinsic():
    p0 = AnalysisParams(target_price=120.0, target_date="2026-10-16", delay_days=0)
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=p0)
    assert v.baseline_value == 10.0  # T_rem == 0 -> intrinsic branch


def test_breakeven_above_target_negative_cushion():
    # deep OTM: strike 125, mid 1.0 -> breakeven 126 > target 120 -> negative cushion
    v = evaluate_contract(make_contract(strike=125.0, bid=0.9, ask=1.1),
                          spot=100.0, today=TODAY, p=P)
    assert v.breakeven == 126.0
    assert v.breakeven_vs_target < 0
    assert abs(v.breakeven_vs_target - (120.0 - 126.0) / 120.0) < 1e-9
