# tests/test_put_bs.py
import math
from option_chaser.valuation import (
    bs_call, bs_put, bs_price, intrinsic_value, clamped_price, leg_greeks,
)


def test_hull_put_value():
    # Hull S=42,K=40,T=0.5,r=0.10,sigma=0.20: C≈4.76, parity → P≈0.81
    assert abs(bs_put(42, 40, 0.5, 0.10, 0.20) - 0.81) < 0.01


def test_put_call_parity_via_bs_put():
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.35
    c = bs_call(S, K, T, r, sigma)
    p = bs_put(S, K, T, r, sigma)
    assert abs((c - p) - (S - K * math.exp(-r * T))) < 1e-9


def test_put_t_zero_intrinsic():
    assert bs_put(80, 120, 0.0, 0.04, 0.4) == 40.0
    assert bs_put(130, 120, 0.0, 0.04, 0.4) == 0.0


def test_deep_itm_european_put_below_intrinsic_and_clamp():
    # deep ITM put: European BS < intrinsic (K discounting); clamp restores floor
    S, K, T, r, sigma = 80.0, 120.0, 0.5, 0.04, 0.2
    raw = bs_put(S, K, T, r, sigma)
    assert raw < K - S  # the very defect §3.2 exists for
    assert clamped_price("put", S, K, T, r, sigma) == K - S


def test_clamp_noop_for_call_with_positive_rate():
    S, K, T, r, sigma = 120.0, 100.0, 0.5, 0.04, 0.3
    assert clamped_price("call", S, K, T, r, sigma) == bs_call(S, K, T, r, sigma)


def test_bs_price_dispatch_and_intrinsic():
    assert bs_price("call", 42, 40, 0.5, 0.10, 0.20) == bs_call(42, 40, 0.5, 0.10, 0.20)
    assert bs_price("put", 42, 40, 0.5, 0.10, 0.20) == bs_put(42, 40, 0.5, 0.10, 0.20)
    assert intrinsic_value("call", 120, 110) == 10.0
    assert intrinsic_value("put", 80, 120) == 40.0


def test_put_greeks():
    g = leg_greeks("put", 42, 40, 0.5, 0.10, 0.20)
    gc = leg_greeks("call", 42, 40, 0.5, 0.10, 0.20)
    assert abs(g.delta - (gc.delta - 1.0)) < 1e-12   # put delta = call delta − 1
    assert -1.0 < g.delta < 0.0
    assert abs(g.gamma - gc.gamma) < 1e-12
    assert abs(g.vega_per_pct - gc.vega_per_pct) < 1e-12
    # put theta_year = call theta_year + r·K·e^{−rT} (differentiate parity)
    expected = gc.theta_per_day + (0.10 * 40 * math.exp(-0.05)) / 365.0
    assert abs(g.theta_per_day - expected) < 1e-9
