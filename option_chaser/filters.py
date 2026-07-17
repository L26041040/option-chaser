"""Sequential hard filters with per-stage rejection counts (spec §4)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from .models import AnalysisParams, FilterReport, FilterStageResult, OptionContract


def apply_filters(
    contracts: Iterable[OptionContract], p: AnalysisParams, today: date
) -> tuple[list[OptionContract], FilterReport]:
    target = date.fromisoformat(p.target_date)
    min_expiry_1 = target + timedelta(days=p.min_days_after)
    min_expiry_2 = date.fromisoformat(p.min_expiry) if p.min_expiry else None

    def expiry_ok(c: OptionContract) -> bool:
        e = date.fromisoformat(c.expiry)
        return e >= min_expiry_1 and (min_expiry_2 is None or e >= min_expiry_2)

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
    remaining = list(contracts)
    total = len(remaining)
    results: list[FilterStageResult] = []
    for label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        results.append(FilterStageResult(label=label, removed=len(remaining) - len(kept)))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))
