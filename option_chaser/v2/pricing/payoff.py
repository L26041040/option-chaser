"""Strategy payoff calculations for Option Chaser MVP V2.

This module calculates expiry payoff values only. It does not calculate
market quotes, entry costs, returns, rankings, or recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from option_chaser.v2.models import (
    SpreadPair,
    SpreadStrategy,
)


class PayoffCalculationError(ValueError):
    """Raised when payoff inputs are malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class SpreadPayoff:
    """Payoff-derived values for one structurally valid debit spread."""

    spread_width: float
    target_payoff: float
    max_payoff: float


def calculate_spread_payoff(
    pair: SpreadPair,
    target_price: float,
) -> SpreadPayoff:
    """Calculate target and maximum payoff at expiry.

    The calculation depends only on strategy, strikes, and target price.
    Market quotes and liquidity data are intentionally ignored.
    """

    if not isinstance(pair, SpreadPair):
        raise PayoffCalculationError(
            "pair must be a SpreadPair"
        )

    normalized_target_price = _normalize_target_price(target_price)

    if pair.strategy is SpreadStrategy.BULL_CALL:
        spread_width = pair.short_strike - pair.long_strike
        uncapped_payoff = max(
            normalized_target_price - pair.long_strike,
            0.0,
        )

    elif pair.strategy is SpreadStrategy.BEAR_PUT:
        spread_width = pair.long_strike - pair.short_strike
        uncapped_payoff = max(
            pair.long_strike - normalized_target_price,
            0.0,
        )

    else:
        raise PayoffCalculationError(
            f"unsupported spread strategy: {pair.strategy!r}"
        )

    target_payoff = min(
        uncapped_payoff,
        spread_width,
    )

    return SpreadPayoff(
        spread_width=spread_width,
        target_payoff=target_payoff,
        max_payoff=spread_width,
    )


def _normalize_target_price(value: object) -> float:
    """Normalize one positive finite target price."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise PayoffCalculationError(
            "target_price must be a positive finite number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise PayoffCalculationError(
            "target_price must be a positive finite number"
        )

    return normalized_value