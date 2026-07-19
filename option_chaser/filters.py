"""Sequential hard filters with per-stage rejection counts (spec §4)."""
from __future__ import annotations

from datetime import date
from itertools import combinations
from typing import Iterable

from .models import AnalysisParams, FilterReport, FilterStageResult, OptionContract, PairReport, leg_option_type


def apply_filters(
    contracts: Iterable[OptionContract], p: AnalysisParams, today: date
) -> tuple[list[OptionContract], FilterReport]:
    side = leg_option_type(p.strategy)
    remaining = [c for c in contracts if c.option_type == side]
    total = len(remaining)
    target = date.fromisoformat(p.target_date)
    min_expiry_2 = date.fromisoformat(p.min_expiry) if p.min_expiry else None

    def expiry_ok(c: OptionContract) -> bool:
        e = date.fromisoformat(c.expiry)
        return e >= target and (min_expiry_2 is None or e >= min_expiry_2)

    def quote_ok(c: OptionContract) -> bool:
        return c.bid is not None and c.ask is not None and c.bid > 0 and c.ask >= c.bid

    def iv_ok(c: OptionContract) -> bool:
        return c.implied_volatility is not None and 0.01 <= c.implied_volatility <= 5.0

    def oi_volume_ok(c: OptionContract) -> bool:
        return c.open_interest >= p.min_oi and c.volume >= p.min_volume

    def spread_ok(c: OptionContract) -> bool:
        mid = (c.bid + c.ask) / 2.0
        return (c.ask - c.bid) <= max(p.spread_floor, p.max_spread_pct * mid)

    stages = (
        ("到期日不符", expiry_ok),
        ("報價異常", quote_ok),
        ("IV 異常", iv_ok),
        ("OI/成交量不足", oi_volume_ok),
        ("Spread 過寬", spread_ok),
    )
    results: list[FilterStageResult] = []
    for label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        results.append(FilterStageResult(label=label, removed=len(remaining) - len(kept)))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))


def generate_spread_pairs(
    legs: list[OptionContract], p: AnalysisParams
) -> tuple[list[tuple[OptionContract, OptionContract]], PairReport]:
    """Spec §4.2: same-expiry exhaustive pairing over qualified legs + sanity."""
    by_expiry: dict[str, list[OptionContract]] = {}
    for c in legs:
        by_expiry.setdefault(c.expiry, []).append(c)
    long_is_lower = p.strategy == "bull-call-spread"
    total = 0
    removed = 0
    out: list[tuple[OptionContract, OptionContract]] = []
    for expiry in sorted(by_expiry):
        group = sorted(by_expiry[expiry], key=lambda c: (c.strike, c.contract_symbol))
        for a, b in combinations(group, 2):  # a.strike <= b.strike
            if a.strike == b.strike:
                continue
            total += 1
            lng, sht = (a, b) if long_is_lower else (b, a)
            width = abs(sht.strike - lng.strike)
            net_mid = (lng.bid + lng.ask) / 2.0 - (sht.bid + sht.ask) / 2.0
            net_worst = lng.ask - sht.bid
            if net_mid <= 0 or net_worst >= width:
                removed += 1
                continue
            out.append((lng, sht))
    return out, PairReport(total_pairs=total, removed_sanity=removed, passed=len(out))
