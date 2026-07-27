"""Structural spread pairing for Option Chaser MVP V2."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from option_chaser.v2.models import (
    ContractEnumerationError,
    OptionContract,
    SpreadPair,
    SpreadStrategy,
)


def enumerate_contract_pairs(
    contracts: Iterable[OptionContract],
    strategy: SpreadStrategy | str,
) -> list[SpreadPair]:
    """Generate every structurally valid pair for one expiry.

    For ``N`` distinct strikes, this function returns ``N(N - 1) / 2`` pairs.
    Liquidity fields and quote widths never remove a structural pair.
    """

    normalized_strategy = _normalize_strategy(strategy)

    if isinstance(contracts, (str, bytes)):
        raise ContractEnumerationError(
            "contracts must be an iterable of OptionContract values"
        )

    try:
        raw_contracts = list(contracts)
    except TypeError as exc:
        raise ContractEnumerationError(
            "contracts must be an iterable of OptionContract values"
        ) from exc

    contracts_by_strike: dict[float, OptionContract] = {}

    for contract in raw_contracts:
        if not isinstance(contract, OptionContract):
            raise ContractEnumerationError(
                "every contract must be an OptionContract"
            )

        if contract.strike in contracts_by_strike:
            raise ContractEnumerationError(
                f"duplicate strike in one expiry chain: {contract.strike}"
            )

        contracts_by_strike[contract.strike] = contract

    ordered_contracts = [
        contracts_by_strike[strike]
        for strike in sorted(contracts_by_strike)
    ]

    pairs: list[SpreadPair] = []

    for lower_contract, higher_contract in combinations(
        ordered_contracts,
        2,
    ):
        if normalized_strategy is SpreadStrategy.BULL_CALL:
            long_leg = lower_contract
            short_leg = higher_contract
        else:
            long_leg = higher_contract
            short_leg = lower_contract

        pairs.append(
            SpreadPair(
                strategy=normalized_strategy,
                long_leg=long_leg,
                short_leg=short_leg,
            )
        )

    return pairs


def _normalize_strategy(
    value: SpreadStrategy | str,
) -> SpreadStrategy:
    """Normalize one supported strategy value."""

    if isinstance(value, SpreadStrategy):
        return value

    if isinstance(value, str):
        try:
            return SpreadStrategy(value.strip().lower())
        except ValueError as exc:
            raise ContractEnumerationError(
                "strategy must be bull_call or bear_put"
            ) from exc

    raise ContractEnumerationError(
        "strategy must be bull_call or bear_put"
    )
