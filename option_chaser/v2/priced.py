"""Priced-spread aggregate for Option Chaser MVP V2.

This module composes one structural spread pair with its expiry, scenario
inputs, quote result, payoff result, and return result.

It evaluates one candidate only. It does not enumerate contracts, rank
candidates, filter candidates, or make trade recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from numbers import Real
import re

from option_chaser.v2.models import SpreadPair
from option_chaser.v2.pricing.payoff import (
    SpreadPayoff,
    calculate_spread_payoff,
)
from option_chaser.v2.pricing.quote import (
    SpreadQuote,
    calculate_spread_quote,
)
from option_chaser.v2.pricing.returns import (
    SpreadReturn,
    calculate_spread_return,
)


_EXPIRY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PricedSpreadError(ValueError):
    """Raised when a priced-spread aggregate cannot be constructed."""


@dataclass(frozen=True, slots=True)
class PricedSpread:
    """One fully evaluated spread candidate for one expiry and scenario.

    The nested calculation objects remain separate so their original
    responsibility boundaries are preserved:

    - ``pair`` contains structural strategy and leg data.
    - ``quote`` contains market-quote calculations.
    - ``payoff`` contains expiry-payoff calculations.
    - ``return_metrics`` contains entry-cost and return calculations.

    Use :func:`price_spread` for normal construction.
    """

    pair: SpreadPair
    expiry: str
    target_price: float
    contract_multiplier: float
    quote: SpreadQuote
    payoff: SpreadPayoff
    return_metrics: SpreadReturn

    def __post_init__(self) -> None:
        if not isinstance(self.pair, SpreadPair):
            raise PricedSpreadError(
                "pair must be a SpreadPair"
            )

        if not isinstance(self.quote, SpreadQuote):
            raise PricedSpreadError(
                "quote must be a SpreadQuote"
            )

        if not isinstance(self.payoff, SpreadPayoff):
            raise PricedSpreadError(
                "payoff must be a SpreadPayoff"
            )

        if not isinstance(self.return_metrics, SpreadReturn):
            raise PricedSpreadError(
                "return_metrics must be a SpreadReturn"
            )

        object.__setattr__(
            self,
            "expiry",
            _normalize_expiry(self.expiry),
        )
        object.__setattr__(
            self,
            "target_price",
            _normalize_positive_finite_number(
                self.target_price,
                field_name="target_price",
            ),
        )
        object.__setattr__(
            self,
            "contract_multiplier",
            _normalize_positive_finite_number(
                self.contract_multiplier,
                field_name="contract_multiplier",
            ),
        )


def price_spread(
    pair: SpreadPair,
    *,
    expiry: str,
    target_price: float,
    contract_multiplier: float = 100,
) -> PricedSpread:
    """Evaluate one spread candidate and return its immutable aggregate.

    The function deliberately performs no filtering. A candidate whose quote
    is incomplete or whose executable debit is non-positive is still returned;
    its ``return_metrics.rankable`` value communicates whether it can enter a
    later ranking stage.
    """

    if not isinstance(pair, SpreadPair):
        raise PricedSpreadError(
            "pair must be a SpreadPair"
        )

    normalized_expiry = _normalize_expiry(expiry)
    normalized_target_price = _normalize_positive_finite_number(
        target_price,
        field_name="target_price",
    )
    normalized_contract_multiplier = _normalize_positive_finite_number(
        contract_multiplier,
        field_name="contract_multiplier",
    )

    quote = calculate_spread_quote(pair)
    payoff = calculate_spread_payoff(
        pair,
        normalized_target_price,
    )
    return_metrics = calculate_spread_return(
        quote,
        payoff,
        contract_multiplier=normalized_contract_multiplier,
    )

    return PricedSpread(
        pair=pair,
        expiry=normalized_expiry,
        target_price=normalized_target_price,
        contract_multiplier=normalized_contract_multiplier,
        quote=quote,
        payoff=payoff,
        return_metrics=return_metrics,
    )


def _normalize_expiry(value: object) -> str:
    """Normalize one strict ISO calendar expiry."""

    if not isinstance(value, str):
        raise PricedSpreadError(
            "expiry must be a YYYY-MM-DD string"
        )

    normalized_value = value.strip()

    if _EXPIRY_PATTERN.fullmatch(normalized_value) is None:
        raise PricedSpreadError(
            "expiry must use YYYY-MM-DD format"
        )

    try:
        parsed_expiry = date.fromisoformat(normalized_value)
    except ValueError as exc:
        raise PricedSpreadError(
            "expiry must contain a valid calendar date"
        ) from exc

    return parsed_expiry.isoformat()


def _normalize_positive_finite_number(
    value: object,
    *,
    field_name: str,
) -> float:
    """Normalize one positive finite real number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise PricedSpreadError(
            f"{field_name} must be a positive finite number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise PricedSpreadError(
            f"{field_name} must be a positive finite number"
        )

    return normalized_value