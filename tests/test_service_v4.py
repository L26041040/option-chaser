"""v4 spec §3.1: CandidateView scenario fields (fixture snapshot, offline)."""
from datetime import date, timedelta

import pytest

from option_chaser import service
from option_chaser.scenarios import (completion_scan, friction, natural_cost,
                                     scenario_vector, _grid_price, _value_fn)
from option_chaser.valuation import SpreadValuation, leg_greeks
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _request(strategies=("long-call", "bull-call-spread")):
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=strategies)


def test_candidate_view_scenario_fields_consistent():
    result = service.run_offline(_request(), SNAP)
    ok = [r for r in result.results if r.status == "ok"]
    assert ok
    for res in ok:
        for cv in res.candidates:
            spot = result.snapshot.spot
            p = _params_for(result, res.strategy)
            expect = scenario_vector(cv.valuation, spot, result.today, p)
            assert cv.scenario == expect
            assert cv.friction == pytest.approx(friction(cv.valuation))
            mid_cost = (cv.valuation.net_mid
                        if isinstance(cv.valuation, SpreadValuation)
                        else cv.valuation.mid)
            assert cv.friction_amount == pytest.approx(
                natural_cost(cv.valuation) - mid_cost)
            k, be = completion_scan(cv.valuation, spot, result.today, p)
            assert cv.completion_threshold == k
            assert cv.breakeven_at_target == be
            assert cv.retention == pytest.approx(
                1.0 + dict(cv.scenario.entries)["S1"])
            expiry = (cv.valuation.long_leg.expiry
                      if hasattr(cv.valuation, "long_leg")
                      else cv.valuation.contract.expiry)
            # 參考日＝日曆錨點（附錄 A9），不是任何被發明出來的目標日
            assert cv.buffer_days == (
                date.fromisoformat(expiry) - p.anchor).days
    assert result.meta.target_move == pytest.approx(
        (120.0 - result.snapshot.spot) / result.snapshot.spot)


def _params_for(result, strategy):
    import dataclasses
    return dataclasses.replace(result.request.base_params, strategy=strategy)


def test_natural_return_merged_into_baseline():
    """T12（附錄 A14.2）：主數字改最差口徑後與原 natural_return 重合，
    欄位合併——CandidateView / ComparisonRow 均不再有 natural_return。"""
    result = service.run_offline(_request(), SNAP)
    cv = next(r for r in result.results if r.status == "ok").candidates[0]
    assert not hasattr(cv, "natural_return")
    assert not hasattr(cv, "worst_return")
    row = result.comparison[0]
    assert not hasattr(row, "natural_return")


def test_quote_warning_friction_over_25pct():
    result = service.run_offline(_request(), SNAP)
    for res in result.results:
        for cv in res.candidates:
            legs_zero = _any_zero_volume(cv.valuation)
            assert cv.quote_warning == (legs_zero or cv.friction > 0.25)


def _any_zero_volume(val):
    if hasattr(val, "long_leg"):
        return val.long_leg.volume == 0 or val.short_leg.volume == 0
    return val.contract.volume == 0


def test_theta_vega_decay_match_direct_engine_recomputation():
    """Interfaces §: theta_day_rate / vega_per_pt / decay_30d_return must
    match direct recomputation via valuation.leg_greeks / scenarios._value_fn,
    independent of service internals."""
    result = service.run_offline(_request(), SNAP)
    ok = [r for r in result.results if r.status == "ok"]
    assert ok
    for res in ok:
        for cv in res.candidates:
            val = cv.valuation
            spot = result.snapshot.spot
            today = result.today
            p = _params_for(result, res.strategy)

            if isinstance(val, SpreadValuation):
                mid_cost = val.net_mid
                expiry = date.fromisoformat(val.long_leg.expiry)
                t_now = (expiry - today).days / 365.0
                g_l = leg_greeks(val.long_leg.option_type, spot,
                                 val.long_leg.strike, t_now, p.rate,
                                 val.long_leg.implied_volatility)
                g_s = leg_greeks(val.short_leg.option_type, spot,
                                 val.short_leg.strike, t_now, p.rate,
                                 val.short_leg.implied_volatility)
                net_theta = g_l.theta_per_day - g_s.theta_per_day
                net_vega = g_l.vega_per_pct - g_s.vega_per_pct
            else:
                mid_cost = val.mid
                net_theta = val.theta_per_day
                net_vega = val.vega_per_pct

            assert cv.theta_day_rate == pytest.approx(
                abs(net_theta) / mid_cost)
            assert cv.vega_per_pt == pytest.approx(net_vega / mid_cost)

            fn, mid, _, expiry_iso = _value_fn(val)
            expiry = date.fromisoformat(expiry_iso)
            d30 = min(today + timedelta(days=30), expiry)
            expect_decay = (fn(spot, d30, p) - mid_cost) / mid_cost
            assert cv.decay_30d_return == pytest.approx(expect_decay)


def test_completion_prices_precomputed_in_service():
    """Red-line: the GUI must not compute the completion-curve price column
    itself — service._v4_fields precomputes `completion_prices` via
    scenarios._grid_price, one price per completion_curve (k, return) pair."""
    result = service.run_offline(_request(), SNAP)
    ok = [r for r in result.results if r.status == "ok"]
    assert ok
    for res in ok:
        for cv in res.candidates:
            spot = result.snapshot.spot
            p = _params_for(result, res.strategy)
            expect = tuple(_grid_price(spot, p.target_price, k)
                          for k, _ in cv.completion_curve)
            assert cv.completion_prices == expect
            assert len(cv.completion_prices) == 5
