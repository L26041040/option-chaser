"""Black-Scholes valuation, Greeks, scenario/stress/guidance. Stdlib math only."""
from __future__ import annotations

import math

DAYS_PER_YEAR = 365.0


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call. Spec §5.1: T <= 0 -> intrinsic (BS undefined at T=0)."""
    if T <= 0.0:
        return max(S - K, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
