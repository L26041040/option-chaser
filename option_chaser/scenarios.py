"""v4 spec §2: seven-scenario resilience engine. Pure, deterministic.

Every valuation goes through the existing primitives scenario_leg_value /
spread_scenario_value (American clamp + [0, width] clamp included).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import AnalysisParams
from .valuation import (ContractValuation, SpreadValuation,
                        scenario_leg_value, spread_scenario_value)

SCENARIO_NAMES = {
    "S1": "不漲", "S2": "半程", "S3": "大半程", "S4": "晚30天",
    "S5": "晚90天", "S6": "IV最保守", "S7": "Natural成交",
}


@dataclass(frozen=True)
class ScenarioVector:
    entries: tuple[tuple[str, float], ...]   # (("S1", ret) ... ("S7", ret)) fixed order
    worst_code: str                          # first minimum in S1..S7 order
    worst_return: float


def _value_fn(val):
    """Uniform (S, at, shift) -> value callable for single legs and spreads."""
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        return (lambda S, at, p, shift=0.0:
                spread_scenario_value(lng, sht, S, at, p, shift)), val.net_mid, \
               (lng.ask - sht.bid), lng.expiry
    c = val.contract
    return (lambda S, at, p, shift=0.0:
            scenario_leg_value(c, S, at, p, shift)), val.mid, c.ask, c.expiry


def _delay_value(fn, spot: float, today: date, p: AnalysisParams,
                 expiry: date, delta_days: int) -> float:
    """Spec §2.2: linear path spot->target over [today, target+delta]."""
    arrive = date.fromisoformat(p.target_date) + timedelta(days=delta_days)
    d = min(arrive, expiry)
    frac = (d - today).days / (arrive - today).days
    s_at_d = spot + (p.target_price - spot) * frac
    return fn(s_at_d, d, p)


def scenario_vector(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams) -> ScenarioVector:
    fn, mid, natural, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    tgt = date.fromisoformat(p.target_date)

    def ret(value: float, cost: float) -> float:
        return (value - cost) / cost

    s_half = spot + 0.5 * (p.target_price - spot)
    s_most = spot + 0.75 * (p.target_price - spot)
    values = [
        ("S1", ret(fn(spot, tgt, p), mid)),
        ("S2", ret(fn(s_half, tgt, p), mid)),
        ("S3", ret(fn(s_most, tgt, p), mid)),
        ("S4", ret(_delay_value(fn, spot, today, p, expiry, 30), mid)),
        ("S5", ret(_delay_value(fn, spot, today, p, expiry, 90), mid)),
        ("S6", ret(min(fn(p.target_price, tgt, p, sh) for sh in p.iv_shifts),
                   mid)),
        ("S7", ret(fn(p.target_price, tgt, p), natural)),
    ]
    worst = min(r for _, r in values)
    code = next(c for c, r in values if r == worst)
    return ScenarioVector(entries=tuple(values), worst_code=code,
                          worst_return=worst)
