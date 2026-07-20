"""v4 spec §2.1/§2.2: seven-scenario resilience vector."""
from datetime import date

import pytest

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.scenarios import ScenarioVector, scenario_vector
from option_chaser.valuation import (evaluate_contract, evaluate_spread,
                                     scenario_leg_value, spread_scenario_value)


def _p(**kw):
    base = dict(strategy="long-call", target_price=105.0,
                target_date="2028-01-01", min_return=0.0)
    base.update(kw)
    return AnalysisParams(**base)


def _call(strike, expiry, bid, ask, iv, volume=10, oi=100):
    return OptionContract(
        contract_symbol=f"XYZ{expiry}C{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=oi, implied_volatility=iv, option_type="call")


TODAY = date(2026, 7, 1)
SPOT = 84.52


def test_single_leg_seven_entries_match_engine():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert [code for code, _ in sv.entries] == [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    tgt = date.fromisoformat(p.target_date)
    mid = v.mid
    # S1: S=spot at target_date, base IV
    exp_s1 = (scenario_leg_value(c, SPOT, tgt, p) - mid) / mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    # S2/S3: completion 50%/75%
    s50 = SPOT + 0.5 * (p.target_price - SPOT)
    s75 = SPOT + 0.75 * (p.target_price - SPOT)
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(c, s50, tgt, p) - mid) / mid)
    assert dict(sv.entries)["S3"] == pytest.approx(
        (scenario_leg_value(c, s75, tgt, p) - mid) / mid)
    # S6: envelope min over ALL iv_shifts (incl. base)
    exp_s6 = min(
        scenario_leg_value(c, p.target_price, tgt, p, sh) for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx((exp_s6 - mid) / mid)
    # S7: Natural cost (=Ask), base value at target
    base_val = scenario_leg_value(c, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base_val - c.ask) / c.ask)
    # worst = min, code = first minimum in S1..S7 order
    rets = [r for _, r in sv.entries]
    assert sv.worst_return == pytest.approx(min(rets))
    assert sv.worst_code == sv.entries[rets.index(min(rets))][0]


def test_delay_scenarios_arrive_before_expiry():
    """S4: expiry >= target+30 -> valued at arrive date with S=target."""
    c = _call(93.0, "2028-12-15", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = date.fromisoformat(p.target_date) + timedelta(days=30)
    exp = (scenario_leg_value(c, p.target_price, arrive, p) - v.mid) / v.mid
    assert dict(sv.entries)["S4"] == pytest.approx(exp)


def test_delay_scenario_expiry_before_arrive_interpolates():
    """v4 spec §2.2: expiry < target+90 -> payoff at interpolated price at expiry."""
    expiry = date(2028, 1, 21)          # target 2028-01-01 + 90 > expiry
    c = _call(93.0, expiry.isoformat(), 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = date.fromisoformat(p.target_date) + timedelta(days=90)
    frac = (expiry - TODAY).days / (arrive - TODAY).days
    s_at_expiry = SPOT + (p.target_price - SPOT) * frac
    exp = (scenario_leg_value(c, s_at_expiry, expiry, p) - v.mid) / v.mid
    assert dict(sv.entries)["S5"] == pytest.approx(exp)


def test_spread_vector_uses_spread_engine_and_natural_cost():
    lng = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    p = _p(strategy="bull-call-spread")
    sv_val = evaluate_spread(lng, sht, SPOT, TODAY, p)
    sv = scenario_vector(sv_val, SPOT, TODAY, p)
    tgt = date.fromisoformat(p.target_date)
    exp_s1 = (spread_scenario_value(lng, sht, SPOT, tgt, p) - sv_val.net_mid) / sv_val.net_mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    natural = lng.ask - sht.bid
    base = spread_scenario_value(lng, sht, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base - natural) / natural)
    # S6 envelope: min over shifts of spread value (net vega can flip sign)
    exp_s6 = min(spread_scenario_value(lng, sht, p.target_price, tgt, p, sh)
                 for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx(
        (exp_s6 - sv_val.net_mid) / sv_val.net_mid)


def test_bearish_completion_mirrors():
    """target < spot: S2 is halfway DOWN."""
    put = OptionContract(
        contract_symbol="XYZP70", strike=80.0, expiry="2028-01-21",
        bid=3.0, ask=3.4, last=3.2, volume=5, open_interest=50,
        implied_volatility=0.25, option_type="put")
    p = _p(strategy="long-put", target_price=70.0)
    v = evaluate_contract(put, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    s50 = SPOT + 0.5 * (70.0 - SPOT)
    tgt = date.fromisoformat(p.target_date)
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(put, s50, tgt, p) - v.mid) / v.mid)
