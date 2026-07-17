import math
from option_chaser.valuation import bs_call, norm_cdf


def _bs_put(S, K, T, r, sigma):
    # local reference implementation for parity check only
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def test_hull_textbook_value():
    # Hull, Options Futures and Other Derivatives: S=42,K=40,T=0.5,r=0.10,sigma=0.20 -> C≈4.76
    assert abs(bs_call(42, 40, 0.5, 0.10, 0.20) - 4.76) < 0.01


def test_zero_rate_atm():
    # S=K=100,T=1,r=0,sigma=0.2 -> 100*(N(0.1)-N(-0.1)) = 7.9656
    assert abs(bs_call(100, 100, 1.0, 0.0, 0.2) - 7.9656) < 1e-3


def test_put_call_parity():
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.35
    c = bs_call(S, K, T, r, sigma)
    p = _bs_put(S, K, T, r, sigma)
    assert abs((c - p) - (S - K * math.exp(-r * T))) < 1e-9


def test_t_zero_returns_intrinsic():
    assert bs_call(120, 110, 0.0, 0.04, 0.38) == 10.0
    assert bs_call(100, 110, 0.0, 0.04, 0.38) == 0.0
    assert bs_call(120, 110, -0.01, 0.04, 0.38) == 10.0


def test_deep_itm_approaches_forward_intrinsic():
    S, K, T, r = 100, 1, 0.5, 0.05
    assert abs(bs_call(S, K, T, r, 0.2) - (S - K * math.exp(-r * T))) < 1e-6


def test_deep_otm_approaches_zero():
    assert bs_call(100, 1000, 0.5, 0.05, 0.2) < 1e-6


def test_t_to_zero_approaches_intrinsic():
    assert abs(bs_call(120, 110, 1e-9, 0.04, 0.38) - 10.0) < 1e-4
