"""Return calculations for Option Chaser MVP V2.

This module combines quote-derived and payoff-derived values. It does not
calculate market quotes, option payoffs, rankings, or recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from option_chaser.v2.pricing.payoff import SpreadPayoff
from option_chaser.v2.pricing.quote import SpreadQuote


class ReturnCalculationError(ValueError):
    """Raised when return inputs are malformed."""


@dataclass(frozen=True, slots=True)
class SpreadReturn:
    """Return-derived values for one debit spread."""

    entry_cost: float | None
    ask_return: float | None
    ask_return_percent: float | None
    rankable: bool


def calculate_spread_return(
    quote: SpreadQuote,
    payoff: SpreadPayoff,
    *,
    contract_multiplier: float = 100,
) -> SpreadReturn:
    """Calculate expiry return using the executable spread ask.

    ``spread_ask`` represents the estimated debit paid to enter the spread.
    ``target_payoff`` represents the spread value at the target price at
    expiry.

    A result is rankable only when entry cost is strictly positive. Negative
    returns remain rankable because they are valid, although unattractive,
    economic outcomes.
    """

    if not isinstance(quote, SpreadQuote):
        raise ReturnCalculationError(
            "quote must be a SpreadQuote"
        )

    if not isinstance(payoff, SpreadPayoff):
        raise ReturnCalculationError(
            "payoff must be a SpreadPayoff"
        )

    normalized_multiplier = _normalize_positive_number(
        contract_multiplier,
        field_name="contract_multiplier",
    )

    spread_ask = _normalize_optional_finite_number(
        quote.spread_ask,
        field_name="quote.spread_ask",
    )
    target_payoff = _normalize_non_negative_number(
        payoff.target_payoff,
        field_name="payoff.target_payoff",
    )

    if spread_ask is None:
        return SpreadReturn(
            entry_cost=None,
            ask_return=None,
            ask_return_percent=None,
            rankable=False,
        )

    entry_cost = spread_ask * normalized_multiplier
    ask_return = (
        target_payoff * normalized_multiplier
        - entry_cost
    )

    if entry_cost <= 0:
        return SpreadReturn(
            entry_cost=entry_cost,
            ask_return=ask_return,
            ask_return_percent=None,
            rankable=False,
        )

    ask_return_percent = (
        ask_return / entry_cost
    ) * 100.0

    return SpreadReturn(
        entry_cost=entry_cost,
        ask_return=ask_return,
        ask_return_percent=ask_return_percent,
        rankable=True,
    )


def _normalize_optional_finite_number(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize one optional finite number."""

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ReturnCalculationError(
            f"{field_name} must be a finite number or None"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value):
        raise ReturnCalculationError(
            f"{field_name} must be a finite number or None"
        )

    return normalized_value


def _normalize_non_negative_number(
    value: object,
    *,
    field_name: str,
) -> float:
    """Normalize one finite non-negative number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ReturnCalculationError(
            f"{field_name} must be a finite non-negative number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value < 0:
        raise ReturnCalculationError(
            f"{field_name} must be a finite non-negative number"
        )

    return normalized_value


def _normalize_positive_number(
    value: object,
    *,
    field_name: str,
) -> float:
    """Normalize one finite positive number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ReturnCalculationError(
            f"{field_name} must be a finite positive number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise ReturnCalculationError(
            f"{field_name} must be a finite positive number"
        )

    return normalized_value