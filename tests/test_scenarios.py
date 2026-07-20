"""v4 spec §2.1/§2.2: seven-scenario resilience vector."""
from datetime import date

import pytest

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser import scenarios
from option_chaser.scenarios import (ScenarioVector, scenario_vector,
                                     completion_curve, completion_scan, friction)
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


def _put(strike, expiry, bid, ask, iv, volume=10, oi=100):
    return OptionContract(
        contract_symbol=f"XYZ{expiry}P{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=oi, implied_volatility=iv, option_type="put")


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


def test_completion_scan_suffix_condition_long_call():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, be = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and 0.0 < k <= 1.0
    tgt = date.fromisoformat(p.target_date)
    # suffix property: every grid j in [k, 1] >= cost; k-0.001 violates
    for j in [k, (k + 1.0) / 2, 1.0]:
        s = max(SPOT + j * (p.target_price - SPOT), min(0.01 * SPOT, p.target_price))
        assert scenario_leg_value(c, s, tgt, p) >= v.mid - 1e-12
    s_prev = SPOT + (k - 0.001) * (p.target_price - SPOT)
    assert scenario_leg_value(c, s_prev, tgt, p) < v.mid
    assert be == pytest.approx(SPOT + k * (p.target_price - SPOT))


def test_completion_scan_four_strategies():
    """spec §7.2: one completion_scan case per strategy; suffix property must
    hold for long-call, long-put, bull-call-spread, and bear-put-spread."""
    tgt = date.fromisoformat("2028-01-01")

    def check(val, spot, target_price, value_fn):
        k, be = completion_scan(val, spot, TODAY, _p(target_price=target_price))
        assert k is not None, "fixture must have a completion threshold"
        mid = val.net_mid if hasattr(val, "net_mid") else val.mid
        for j in [k, (k + 1.0) / 2, 1.0]:
            s = scenarios._grid_price(spot, target_price, j)
            assert value_fn(s) >= mid - 1e-12
        if k > -0.2:
            s_prev = scenarios._grid_price(spot, target_price, k - 0.001)
            assert value_fn(s_prev) < mid
        assert be == pytest.approx(scenarios._grid_price(spot, target_price, k))

    # long-call
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p_call = _p(strategy="long-call", target_price=105.0)
    v_call = evaluate_contract(c, SPOT, TODAY, p_call)
    check(v_call, SPOT, 105.0, lambda s: scenario_leg_value(c, s, tgt, p_call))

    # long-put
    put = _put(80.0, "2028-01-21", 3.0, 3.4, 0.25)
    p_put = _p(strategy="long-put", target_price=70.0)
    v_put = evaluate_contract(put, SPOT, TODAY, p_put)
    check(v_put, SPOT, 70.0, lambda s: scenario_leg_value(put, s, tgt, p_put))

    # bull-call-spread
    lng_c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht_c = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    p_bcs = _p(strategy="bull-call-spread", target_price=105.0)
    v_bcs = evaluate_spread(lng_c, sht_c, SPOT, TODAY, p_bcs)
    check(v_bcs, SPOT, 105.0,
          lambda s: spread_scenario_value(lng_c, sht_c, s, tgt, p_bcs))

    # bear-put-spread
    lng_p = _put(85.0, "2028-01-21", 6.0, 6.4, 0.25)
    sht_p = _put(75.0, "2028-01-21", 2.0, 2.4, 0.28)
    p_bps = _p(strategy="bear-put-spread", target_price=70.0)
    v_bps = evaluate_spread(lng_p, sht_p, SPOT, TODAY, p_bps)
    check(v_bps, SPOT, 70.0,
          lambda s: spread_scenario_value(lng_p, sht_p, s, tgt, p_bps))


def test_completion_scan_hopeless_returns_none():
    """Cost above full-completion value -> (None, None)."""
    c = _call(120.0, "2028-01-21", 8.0, 9.0, 0.20)   # deep OTM, huge premium
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    assert completion_scan(v, SPOT, TODAY, p) == (None, None)


def test_completion_scan_already_breakeven_negative_k():
    """Deep ITM low-premium: threshold <= 0 (already at breakeven at k=0)."""
    c = _call(60.0, "2028-01-21", 24.0, 24.6, 0.18)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, _ = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and k <= 0.0


def test_completion_scan_floor_extreme_bullish():
    """target >= 6*spot: k=-0.2 corner triggers floor min(0.01*spot, target)."""
    c = _call(3.0, "2028-01-21", 0.4, 0.6, 0.8)
    p = _p(target_price=15.0)
    spot = 2.0
    v = evaluate_contract(c, spot, TODAY, p)
    k, be = completion_scan(v, spot, TODAY, p)   # must not raise (S<=0 -> BS log)
    assert be is None or be > 0.0


def test_completion_scan_deep_bearish_k1_exact_target():
    """target < 0.01*spot: floor must NOT distort k=1 (S_1 == target exactly).

    Reviewer finding M1: the previous version recomputed the _grid_price
    formula inline and could never fail. Assert against the real
    scenarios._grid_price function directly instead.
    """
    assert scenarios._grid_price(100.0, 0.5, 1.0) == pytest.approx(0.5)
    # floor engages: raw = 1.2*2 - 0.2*15 = -0.6 -> floored to min(0.01*2, 15) = 0.02
    assert scenarios._grid_price(2.0, 15.0, -0.2) == pytest.approx(
        min(0.01 * 2.0, 15.0))


def test_completion_curve_identities():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    curve = completion_curve(v, SPOT, TODAY, p)
    assert [k for k, _ in curve] == [0.0, 0.25, 0.5, 0.75, 1.0]
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert dict(curve)[0.0] == pytest.approx(dict(sv.entries)["S1"])   # k=0 == S1
    tgt = date.fromisoformat(p.target_date)
    base = (scenario_leg_value(c, p.target_price, tgt, p) - v.mid) / v.mid
    assert dict(curve)[1.0] == pytest.approx(base)                     # k=1 == baseline


def test_friction():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    assert friction(v) == pytest.approx((4.4 - 4.2) / 4.2)
    lng = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    sp = evaluate_spread(lng, sht, SPOT, TODAY, _p(strategy="bull-call-spread"))
    assert friction(sp) == pytest.approx(
        ((lng.ask - sht.bid) - sp.net_mid) / sp.net_mid)
