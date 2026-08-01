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
    l1: float
    l2: float
    l3: float


def scenario_leg_value(
    c: OptionContract, S: float, at: date, p: AnalysisParams, shift: float = 0.0
) -> float:
    """Spec §3 valuation primitive: value of one leg at date `at` with spot S."""
    expiry = date.fromisoformat(c.expiry)
    if at >= expiry:
        return intrinsic_value(c.option_type, S, c.strike)
    T = days_between(at, expiry) / DAYS_PER_YEAR
    return clamped_price(c.option_type, S, c.strike, T, p.rate, c.implied_volatility * (1.0 + shift))


def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams
) -> ContractValuation:
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    expiry = date.fromisoformat(c.expiry)
    target = p.anchor          # 附錄 A9 錨點：估值參考日
    g = leg_greeks(c.option_type, spot, c.strike,
                   days_between(today, expiry) / DAYS_PER_YEAR, p.rate,
                   c.implied_volatility)
    scenario_values = tuple(
        (shift, scenario_leg_value(c, p.target_price, target, p, shift))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]
    floor_value = intrinsic_value(c.option_type, p.target_price, c.strike)
    if c.option_type == "call":
        breakeven = c.strike + mid
        be_vs_spot = (breakeven - spot) / spot
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = c.strike - mid
        be_vs_spot = (spot - breakeven) / spot
        be_vs_target = (breakeven - p.target_price) / p.target_price
    l2 = scenario_leg_value(c, p.target_price, target, p, min(p.iv_shifts))
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven, breakeven_vs_spot=be_vs_spot,
        breakeven_vs_target=be_vs_target,
        effective_leverage=abs(g.delta) * spot / mid,
        floor_value=floor_value, scenario_values=scenario_values,
        baseline_value=baseline_value,
        l1=floor_value, l2=l2, l3=baseline_value / (1.0 + p.min_return),
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


def spread_scenario_value(
    long_leg: OptionContract, short_leg: OptionContract,
    S: float, at: date, p: AnalysisParams, shift: float = 0.0,
) -> float:
    width = abs(short_leg.strike - long_leg.strike)
    raw = (scenario_leg_value(long_leg, S, at, p, shift)
           - scenario_leg_value(short_leg, S, at, p, shift))
    return min(max(raw, 0.0), width)


@dataclass(frozen=True)
class SpreadValuation:
    long_leg: OptionContract
    short_leg: OptionContract
    width: float
    net_mid: float
    net_worst: float
    net_delta: float
    breakeven: float
    breakeven_vs_target: float
    effective_leverage: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l2: float
    l3: float
    max_profit: float


def evaluate_spread(
    long_leg: OptionContract, short_leg: OptionContract,
    spot: float, today: date, p: AnalysisParams,
) -> SpreadValuation:
    width = abs(short_leg.strike - long_leg.strike)
    net_mid = (long_leg.bid + long_leg.ask) / 2.0 - (short_leg.bid + short_leg.ask) / 2.0
    net_worst = long_leg.ask - short_leg.bid
    target = p.anchor          # 附錄 A9 錨點：估值參考日
    expiry = date.fromisoformat(long_leg.expiry)
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    g_l = leg_greeks(long_leg.option_type, spot, long_leg.strike, t_now, p.rate,
                     long_leg.implied_volatility)
    g_s = leg_greeks(short_leg.option_type, spot, short_leg.strike, t_now, p.rate,
                     short_leg.implied_volatility)
    net_delta = g_l.delta - g_s.delta
    scenario_values = tuple(
        (shift, spread_scenario_value(long_leg, short_leg, p.target_price, target, p, shift))
        for shift in p.iv_shifts
    )
    baseline = dict(scenario_values)[0.0]
    if long_leg.option_type == "call":
        breakeven = long_leg.strike + net_mid
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = long_leg.strike - net_mid
        be_vs_target = (breakeven - p.target_price) / p.target_price
    return SpreadValuation(
        long_leg=long_leg, short_leg=short_leg, width=width,
        net_mid=net_mid, net_worst=net_worst, net_delta=net_delta,
        breakeven=breakeven, breakeven_vs_target=be_vs_target,
        effective_leverage=abs(net_delta) * spot / net_mid,
        scenario_values=scenario_values, baseline_value=baseline,
        l2=min(v for _, v in scenario_values),
        l3=baseline / (1.0 + p.min_return),
        max_profit=width - net_mid,
    )


def spread_guidance_judgments(sv: SpreadValuation, p: AnalysisParams) -> list[str]:
    """Spec §3.4: spreads have NO L1; L2 is the scenario envelope minimum."""
    msgs: list[str] = []
    if sv.net_worst > sv.l2:
        msgs.append(f"劇本成立但最保守 IV 情境下仍虧損（IV 情境最低值 ${sv.l2:.2f}）")
    if sv.net_worst > sv.l3:
        msgs.append("以最差進場成本達不到你設定的最低報酬（min-return）")
    return msgs
