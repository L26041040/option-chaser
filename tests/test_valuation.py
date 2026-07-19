from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import bs_call, bs_put, evaluate_contract, scenario_leg_value

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28")
P_PUT = AnalysisParams(target_price=80.0, target_date="2026-08-28", strategy="long-put")


def make_contract(**kw):
    base = dict(contract_symbol="XYZ261016C00110000", option_type="call",
                strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25, last=3.1,
                volume=152, open_interest=830, implied_volatility=0.38)
    base.update(kw)
    return OptionContract(**base)


def test_call_anchors_and_scenarios():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    assert v.mid == 3.125 and v.breakeven == 113.125
    assert abs(v.breakeven_vs_spot - 0.13125) < 1e-9
    assert abs(v.breakeven_vs_target - (120 - 113.125) / 120) < 1e-9
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert v.floor_value == 10.0 == v.l1
    for shift, val in v.scenario_values:
        assert abs(val - max(bs_call(120.0, 110.0, t_rem, P.rate, 0.38 * (1 + shift)), 10.0)) < 1e-12
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_put_anchors_mirror():
    c = make_contract(contract_symbol="XYZ261016P00090000", option_type="put",
                      strike=90.0, bid=2.8, ask=3.0, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.breakeven == 90.0 - 2.9
    assert abs(v.breakeven_vs_spot - (100.0 - 87.1) / 100.0) < 1e-9
    assert abs(v.breakeven_vs_target - (87.1 - 80.0) / 80.0) < 1e-9  # put cushion = (BE−target)/target
    assert v.floor_value == 10.0 == v.l1  # max(90−80,0)
    assert v.delta < 0
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_scenario_leg_value_at_and_after_expiry():
    c = make_contract()
    assert scenario_leg_value(c, 120.0, date(2026, 10, 16), P) == 10.0
    assert scenario_leg_value(c, 120.0, date(2026, 11, 1), P) == 10.0  # past expiry -> intrinsic


def test_deep_itm_put_scenario_clamped():
    c = make_contract(contract_symbol="P120", option_type="put", strike=120.0,
                      bid=41.0, ask=41.5, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.baseline_value == 40.0  # BS European below intrinsic -> clamped
