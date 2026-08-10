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
    """Uniform (S, at, shift) -> value callable for single legs and spreads.

    #113：帶上 `val.carry`／`val.long_carry`+`val.short_carry`（每腿只算
    一次，見 `valuation.LegCarry` docstring）——七情境、保本掃描等全部
    共用同一個 closure，不重新反解 IV。
    """
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        lc, sc = val.long_carry, val.short_carry
        return (lambda S, at, p, shift=0.0:
                spread_scenario_value(lng, sht, S, at, p, shift, lc, sc)), \
               val.net_mid, (lng.ask - sht.bid), lng.expiry
    c = val.contract
    carry = val.carry
    return (lambda S, at, p, shift=0.0:
            scenario_leg_value(c, S, at, p, shift, carry)), val.mid, c.ask, c.expiry


def _delay_value(fn, spot: float, today: date, p: AnalysisParams,
                 expiry: date, delta_days: int) -> float:
    """Spec §2.2: linear path spot->target over [today, anchor+delta]."""
    arrive = p.anchor + timedelta(days=delta_days)
    d = min(arrive, expiry)
    frac = (d - today).days / (arrive - today).days
    s_at_d = spot + (p.target_price - spot) * frac
    return fn(s_at_d, d, p)


def scenario_vector(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams) -> ScenarioVector:
    fn, mid, natural, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日

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


def natural_cost(val: ContractValuation | SpreadValuation) -> float:
    if isinstance(val, SpreadValuation):
        return val.long_leg.ask - val.short_leg.bid
    return val.contract.ask


def friction(val: ContractValuation | SpreadValuation) -> float:
    """(Natural - Mid) / Mid. Display cap handled by presentation layers."""
    mid = val.net_mid if isinstance(val, SpreadValuation) else val.mid
    return (natural_cost(val) - mid) / mid


def _grid_price(spot: float, target: float, k: float) -> float:
    """Spec §2.3: positive floor min(0.01*spot, target) keeps k=1 == target."""
    return max(spot + k * (target - spot), min(0.01 * spot, target))


def completion_scan(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams
                    ) -> tuple[float | None, float | None]:
    """Suffix-condition grid scan (spec §2.3): k* = smallest k such that
    value >= Mid cost at EVERY grid point in [k, 1.0]. Walk down from 1.0."""
    fn, mid, _, _ = _value_fn(val)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日
    k_star = None
    for i in range(1000, -201, -1):          # k = 1.000 down to -0.200
        k = i / 1000.0
        s = _grid_price(spot, p.target_price, k)
        if fn(s, tgt, p) < mid:
            break
        k_star = k
    if k_star is None:                        # value(S_1.0) < cost
        return None, None
    return k_star, _grid_price(spot, p.target_price, k_star)


def completion_curve(val: ContractValuation | SpreadValuation, spot: float,
                     today: date, p: AnalysisParams
                     ) -> tuple[tuple[float, float], ...]:
    fn, mid, _, _ = _value_fn(val)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日
    out = []
    for k in (0.0, 0.25, 0.5, 0.75, 1.0):
        s = _grid_price(spot, p.target_price, k)
        out.append((k, (fn(s, tgt, p) - mid) / mid))
    return tuple(out)
