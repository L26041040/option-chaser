"""Candidate-evaluation application service for Option Chaser MVP V2.

This module is the formal application entry point for evaluating every
structurally valid spread candidate in one expiry chain.

It coordinates existing domain components only. It does not rank, filter,
truncate, recommend, fetch market data, or render user-interface output.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from math import isfinite
from numbers import Real
import re

from option_chaser.v2.models import (
    OptionContract,
    SpreadStrategy,
)
from option_chaser.v2.pairing import enumerate_contract_pairs
from option_chaser.v2.priced import (
    PricedSpread,
    price_spread,
)


_EXPIRY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CandidateEvaluationError(ValueError):
    """Raised when a candidate-evaluation request cannot be completed."""


@dataclass(frozen=True, slots=True)
class CandidateEvaluationResult:
    """Immutable result for one strategy and one expiry chain.

    Every structurally valid pair remains in ``candidates``. Rankability is
    descriptive data carried by each candidate; it does not remove candidates
    from this result.
    """

    strategy: SpreadStrategy
    expiry: str
    target_price: float
    contract_multiplier: float
    source_contract_count: int
    candidates: tuple[PricedSpread, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, SpreadStrategy):
            raise CandidateEvaluationError(
                "strategy must be a SpreadStrategy"
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

        if (
            isinstance(self.source_contract_count, bool)
            or not isinstance(self.source_contract_count, int)
            or self.source_contract_count < 0
        ):
            raise CandidateEvaluationError(
                "source_contract_count must be a non-negative integer"
            )

        if isinstance(self.candidates, (str, bytes)):
            raise CandidateEvaluationError(
                "candidates must be an iterable of PricedSpread values"
            )

        try:
            normalized_candidates = tuple(self.candidates)
        except TypeError as exc:
            raise CandidateEvaluationError(
                "candidates must be an iterable of PricedSpread values"
            ) from exc

        object.__setattr__(
            self,
            "candidates",
            normalized_candidates,
        )

        expected_candidate_count = (
            self.source_contract_count
            * (self.source_contract_count - 1)
            // 2
        )

        if len(self.candidates) != expected_candidate_count:
            raise CandidateEvaluationError(
                "candidate count is inconsistent with source_contract_count"
            )

        for index, candidate in enumerate(self.candidates):
            if not isinstance(candidate, PricedSpread):
                raise CandidateEvaluationError(
                    f"candidate at index {index} must be a PricedSpread"
                )

            if candidate.pair.strategy is not self.strategy:
                raise CandidateEvaluationError(
                    f"candidate at index {index} has inconsistent strategy"
                )

            if candidate.expiry != self.expiry:
                raise CandidateEvaluationError(
                    f"candidate at index {index} has inconsistent expiry"
                )

            if candidate.target_price != self.target_price:
                raise CandidateEvaluationError(
                    f"candidate at index {index} has inconsistent target_price"
                )

            if candidate.contract_multiplier != self.contract_multiplier:
                raise CandidateEvaluationError(
                    f"candidate at index {index} has inconsistent "
                    "contract_multiplier"
                )

    @property
    def candidate_count(self) -> int:
        """Return the number of structurally valid evaluated candidates."""

        return len(self.candidates)

    @property
    def rankable_candidates(self) -> tuple[PricedSpread, ...]:
        """Return a nondestructive view of candidates eligible for ranking."""

        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.return_metrics.rankable
        )

    @property
    def unrankable_candidates(self) -> tuple[PricedSpread, ...]:
        """Return a nondestructive view of candidates ineligible for ranking."""

        return tuple(
            candidate
            for candidate in self.candidates
            if not candidate.return_metrics.rankable
        )

    @property
    def rankable_count(self) -> int:
        """Return the number of candidates eligible for later ranking."""

        return len(self.rankable_candidates)

    @property
    def unrankable_count(self) -> int:
        """Return the number of candidates ineligible for later ranking."""

        return len(self.unrankable_candidates)


def evaluate_candidates(
    contracts: Iterable[OptionContract],
    strategy: SpreadStrategy | str,
    *,
    expiry: str,
    target_price: float,
    contract_multiplier: float = 100,
) -> CandidateEvaluationResult:
    """Evaluate every structurally valid spread pair in one expiry chain.

    The returned candidate order is the deterministic structural order produced
    by :func:`enumerate_contract_pairs`. No return-based sorting is applied.
    """

    normalized_contracts = _materialize_contracts(contracts)
    normalized_strategy = _normalize_strategy(strategy)
    normalized_expiry = _normalize_expiry(expiry)
    normalized_target_price = _normalize_positive_finite_number(
        target_price,
        field_name="target_price",
    )
    normalized_contract_multiplier = _normalize_positive_finite_number(
        contract_multiplier,
        field_name="contract_multiplier",
    )

    try:
        pairs = enumerate_contract_pairs(
            normalized_contracts,
            normalized_strategy,
        )

        candidates = tuple(
            price_spread(
                pair,
                expiry=normalized_expiry,
                target_price=normalized_target_price,
                contract_multiplier=normalized_contract_multiplier,
            )
            for pair in pairs
        )
    except ValueError as exc:
        raise CandidateEvaluationError(
            f"candidate evaluation failed: {exc}"
        ) from exc

    return CandidateEvaluationResult(
        strategy=normalized_strategy,
        expiry=normalized_expiry,
        target_price=normalized_target_price,
        contract_multiplier=normalized_contract_multiplier,
        source_contract_count=len(normalized_contracts),
        candidates=candidates,
    )


def _materialize_contracts(
    contracts: Iterable[OptionContract],
) -> tuple[OptionContract, ...]:
    """Materialize one contract iterable exactly once."""

    if isinstance(contracts, (str, bytes)):
        raise CandidateEvaluationError(
            "contracts must be an iterable of OptionContract values"
        )

    try:
        return tuple(contracts)
    except TypeError as exc:
        raise CandidateEvaluationError(
            "contracts must be an iterable of OptionContract values"
        ) from exc


def _normalize_strategy(
    value: SpreadStrategy | str,
) -> SpreadStrategy:
    """Normalize one supported debit-spread strategy."""

    if isinstance(value, SpreadStrategy):
        return value

    if isinstance(value, str):
        try:
            return SpreadStrategy(value.strip().lower())
        except ValueError as exc:
            raise CandidateEvaluationError(
                "strategy must be bull_call or bear_put"
            ) from exc

    raise CandidateEvaluationError(
        "strategy must be bull_call or bear_put"
    )


def _normalize_expiry(value: object) -> str:
    """Normalize one strict ISO calendar expiry."""

    if not isinstance(value, str):
        raise CandidateEvaluationError(
            "expiry must be a YYYY-MM-DD string"
        )

    normalized_value = value.strip()

    if _EXPIRY_PATTERN.fullmatch(normalized_value) is None:
        raise CandidateEvaluationError(
            "expiry must use YYYY-MM-DD format"
        )

    try:
        parsed_expiry = date.fromisoformat(normalized_value)
    except ValueError as exc:
        raise CandidateEvaluationError(
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
        raise CandidateEvaluationError(
            f"{field_name} must be a positive finite number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise CandidateEvaluationError(
            f"{field_name} must be a positive finite number"
        )

    return normalized_value