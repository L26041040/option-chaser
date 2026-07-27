"""Core data models for Option Chaser MVP V2 spread enumeration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from numbers import Real


class ContractEnumerationError(ValueError):
    """Raised when option contracts cannot be structurally enumerated."""


class SpreadStrategy(StrEnum):
    """Debit-spread strategies supported by the MVP V2 enumerator."""

    BULL_CALL = "bull_call"
    BEAR_PUT = "bear_put"


@dataclass(frozen=True, slots=True)
class OptionContract:
    """One option contract from a single expiry and option-type chain.

    Liquidity fields are retained as data only. They do not control structural
    pairing in MVP V2.
    """

    strike: float
    bid: float | None = None
    ask: float | None = None
    implied_volatility: float | None = None
    open_interest: float | None = None
    volume: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strike",
            _normalize_positive_finite_number(
                self.strike,
                field_name="strike",
            ),
        )


@dataclass(frozen=True, slots=True)
class SpreadPair:
    """One structurally valid debit-spread pair."""

    strategy: SpreadStrategy
    long_leg: OptionContract
    short_leg: OptionContract

    def __post_init__(self) -> None:
        if (
            self.strategy is SpreadStrategy.BULL_CALL
            and self.long_leg.strike >= self.short_leg.strike
        ):
            raise ContractEnumerationError(
                "bull_call requires long strike < short strike"
            )

        if (
            self.strategy is SpreadStrategy.BEAR_PUT
            and self.long_leg.strike <= self.short_leg.strike
        ):
            raise ContractEnumerationError(
                "bear_put requires long strike > short strike"
            )

    @property
    def long_strike(self) -> float:
        """Return the long-leg strike."""

        return self.long_leg.strike

    @property
    def short_strike(self) -> float:
        """Return the short-leg strike."""

        return self.short_leg.strike


def _normalize_positive_finite_number(
    value: object,
    *,
    field_name: str,
) -> float:
    """Normalize a positive finite real number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ContractEnumerationError(
            f"{field_name} must be a positive finite number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise ContractEnumerationError(
            f"{field_name} must be a positive finite number"
        )

    return normalized_value
