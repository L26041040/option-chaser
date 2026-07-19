"""Black-Scholes valuation, Greeks, scenario/stress/guidance. Stdlib math only."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .models import AnalysisParams, OptionContract

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


def days_between(d1: date, d2: date) -> int:
    return (d2 - d1).days


@dataclass(frozen=True)
class ContractValuation:
    contract: OptionContract
    mid: float
    spread: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float
    breakeven: float
    breakeven_vs_spot: float
    breakeven_vs_target: float
    effective_leverage: float
    floor_value: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    stress_half: float
    stress_delay: float | None
    stress_flat: float
    l1: float
    l2: float
    l3: float


def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams
) -> ContractValuation:
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    iv = c.implied_volatility
    expiry = date.fromisoformat(c.expiry)
    target = date.fromisoformat(p.target_date)

    g = call_greeks(spot, c.strike, days_between(today, expiry) / DAYS_PER_YEAR,
                    p.rate, iv)

    t_rem = days_between(target, expiry) / DAYS_PER_YEAR
    floor_value = max(p.target_price - c.strike, 0.0)
    scenario_values = tuple(
        (shift, bs_call(p.target_price, c.strike, t_rem, p.rate, iv * (1.0 + shift)))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]

    half_price = spot + 0.5 * (p.target_price - spot)
    stress_half = bs_call(half_price, c.strike, t_rem, p.rate, iv)
    stress_flat = bs_call(spot, c.strike, t_rem, p.rate, iv)
    stress_delay = None
    if p.delay_days > 0:
        t_delay = (days_between(target, expiry) - p.delay_days) / DAYS_PER_YEAR
        stress_delay = bs_call(p.target_price, c.strike, t_delay, p.rate, iv)

    # Price guidance (spec §5.7): L1 <= L2 <= baseline; L3 <= baseline.
    l1 = floor_value
    l2 = bs_call(p.target_price, c.strike, t_rem, p.rate,
                 iv * (1.0 + min(p.iv_shifts)))
    l3 = baseline_value / (1.0 + p.min_return)

    breakeven = c.strike + mid
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven,
        breakeven_vs_spot=(breakeven - spot) / spot,
        breakeven_vs_target=(p.target_price - breakeven) / p.target_price,
        effective_leverage=g.delta * spot / mid,
        floor_value=floor_value,
        scenario_values=scenario_values,
        baseline_value=baseline_value,
        stress_half=stress_half, stress_delay=stress_delay, stress_flat=stress_flat,
        l1=l1, l2=l2, l3=l3,
    )


def _shift_label(shift: float) -> str:
    if shift == 0.0:
        return "shift=0，即基準"
    return f"shift={shift * 100:+g}%"


def guidance_judgments(v: ContractValuation, p: AnalysisParams) -> list[str]:
    """Spec §5.7: independent per-ceiling judgments against current Ask."""
    ask = v.contract.ask
    msgs: list[str] = []
    if ask > v.l1:
        msgs.append("超過劇本內在價值，獲利需時間價值/IV 配合")
    if ask > v.l2:
        msgs.append(
            f"劇本成立但最保守 IV 情境（{_shift_label(min(p.iv_shifts))}）下仍虧損"
        )
    if ask > v.l3:
        msgs.append("以 Ask 進場達不到你設定的最低報酬（min-return）")
    return msgs


def bs_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put. T <= 0 -> intrinsic (spec §3.1)."""
    if T <= 0.0:
        return max(K - S, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    return bs_call(S, K, T, r, sigma) if option_type == "call" else bs_put(S, K, T, r, sigma)


def intrinsic_value(option_type: str, S: float, K: float) -> float:
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def clamped_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Spec §3.2: American no-arbitrage floor applied to every valuation output."""
    return max(bs_price(option_type, S, K, T, r, sigma), intrinsic_value(option_type, S, K), 0.0)


def leg_greeks(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §3.1. Caller guarantees T > 0."""
    g = call_greeks(S, K, T, r, sigma)
    if option_type == "call":
        return g
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year_put = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm_cdf(-d2)
    )
    return Greeks(
        delta=g.delta - 1.0,
        gamma=g.gamma,
        theta_per_day=theta_year_put / DAYS_PER_YEAR,
        vega_per_pct=g.vega_per_pct,
    )
