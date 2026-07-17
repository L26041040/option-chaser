"""Black-Scholes valuation, Greeks, scenario/stress/guidance. Stdlib math only."""
from __future__ import annotations

import math
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float


def call_greeks(S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §5.5. Caller guarantees T > 0 (filters ensure expiry > today)."""
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm_cdf(d2)
    )
    return Greeks(
        delta=norm_cdf(d1),
        gamma=norm_pdf(d1) / (S * st),
        theta_per_day=theta_year / DAYS_PER_YEAR,
        vega_per_pct=S * norm_pdf(d1) * math.sqrt(T) / 100.0,
    )
