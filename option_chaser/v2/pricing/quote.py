"""Market-quote calculations for Option Chaser MVP V2.

This module calculates quote-derived values only. It does not calculate
payoffs, returns, entry costs, rankings, or trade recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from option_chaser.v2.models import SpreadPair


class QuoteCalculationError(ValueError):
    """Raised when a supplied market quote is malformed."""


@dataclass(frozen=True, slots=True)
class SpreadQuote:
    """Quote-derived values for one structurally valid spread pair.

    Values remain ``None`` when the source quotes required for that specific
    calculation are unavailable.
    """

    long_mid: float | None
    short_mid: float | None
    spread_bid: float | None
    spread_mid: float | None
    spread_ask: float | None


def calculate_midpoint(
    bid: float | None,
    ask: float | None,
) -> float | None:
    """Calculate the midpoint of one option contract quote.

    ``None`` represents an unavailable source quote. If either source quote is
    unavailable, the midpoint is also unavailable.

    Numeric quotes must be finite and non-negative. A zero quote is valid and
    is not treated as missing.
    """

    normalized_bid = _normalize_quote(bid, field_name="bid")
    normalized_ask = _normalize_quote(ask, field_name="ask")

    if normalized_bid is None or normalized_ask is None:
        return None

    return (normalized_bid + normalized_ask) / 2.0


def calculate_spread_quote(pair: SpreadPair) -> SpreadQuote:
    """Calculate executable and midpoint quotes for one debit spread.

    The formulas are identical for Bull Call and Bear Put debit spreads:

    ``spread_ask = long_ask - short_bid``
    ``spread_mid = long_mid - short_mid``
    ``spread_bid = long_bid - short_ask``

    Each output depends only on the source quotes required by its formula.
    Missing data for one output does not unnecessarily invalidate another
    independently calculable output.
    """

    if not isinstance(pair, SpreadPair):
        raise QuoteCalculationError(
            "pair must be a SpreadPair"
        )

    long_bid = _normalize_quote(
        pair.long_leg.bid,
        field_name="long_leg.bid",
    )
    long_ask = _normalize_quote(
        pair.long_leg.ask,
        field_name="long_leg.ask",
    )
    short_bid = _normalize_quote(
        pair.short_leg.bid,
        field_name="short_leg.bid",
    )
    short_ask = _normalize_quote(
        pair.short_leg.ask,
        field_name="short_leg.ask",
    )

    long_mid = _midpoint_from_normalized_quotes(
        long_bid,
        long_ask,
    )
    short_mid = _midpoint_from_normalized_quotes(
        short_bid,
        short_ask,
    )

    spread_bid = _subtract_if_available(
        long_bid,
        short_ask,
    )
    spread_mid = _subtract_if_available(
        long_mid,
        short_mid,
    )
    spread_ask = _subtract_if_available(
        long_ask,
        short_bid,
    )

    return SpreadQuote(
        long_mid=long_mid,
        short_mid=short_mid,
        spread_bid=spread_bid,
        spread_mid=spread_mid,
        spread_ask=spread_ask,
    )


def _normalize_quote(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize one optional finite, non-negative market quote."""

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, Real):
        raise QuoteCalculationError(
            f"{field_name} must be a finite non-negative number or None"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value < 0:
        raise QuoteCalculationError(
            f"{field_name} must be a finite non-negative number or None"
        )

    return normalized_value


def _midpoint_from_normalized_quotes(
    bid: float | None,
    ask: float | None,
) -> float | None:
    """Calculate midpoint from already normalized optional quotes."""

    if bid is None or ask is None:
        return None

    return (bid + ask) / 2.0


def _subtract_if_available(
    minuend: float | None,
    subtrahend: float | None,
) -> float | None:
    """Subtract two values only when both values are available."""

    if minuend is None or subtrahend is None:
        return None

    return minuend - subtrahend