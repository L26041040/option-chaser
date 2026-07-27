from __future__ import annotations

import pytest

from option_chaser.v2.models import (
    ContractEnumerationError,
    OptionContract,
    SpreadStrategy,
)
from option_chaser.v2.pairing import enumerate_contract_pairs


def test_enumerate_contract_pairs_generates_all_ten_pairs_from_five_contracts() -> None:
    contracts = [
        OptionContract(strike=90),
        OptionContract(strike=95),
        OptionContract(strike=100),
        OptionContract(strike=105),
        OptionContract(strike=110),
    ]

    assert len(
        enumerate_contract_pairs(contracts, SpreadStrategy.BULL_CALL)
    ) == 10


@pytest.mark.parametrize("contract_count", range(0, 11))
def test_pair_count_matches_combination_formula(
    contract_count: int,
) -> None:
    contracts = [
        OptionContract(strike=80 + index * 5)
        for index in range(contract_count)
    ]

    pairs = enumerate_contract_pairs(
        contracts,
        SpreadStrategy.BULL_CALL,
    )

    assert len(pairs) == contract_count * (contract_count - 1) // 2


def test_enumerate_contract_pairs_orders_bull_call_legs() -> None:
    pairs = enumerate_contract_pairs(
        [
            OptionContract(strike=110),
            OptionContract(strike=90),
            OptionContract(strike=100),
        ],
        "bull_call",
    )

    assert all(pair.long_strike < pair.short_strike for pair in pairs)


def test_enumerate_contract_pairs_orders_bear_put_legs() -> None:
    pairs = enumerate_contract_pairs(
        [
            OptionContract(strike=110),
            OptionContract(strike=90),
            OptionContract(strike=100),
        ],
        "bear_put",
    )

    assert all(pair.long_strike > pair.short_strike for pair in pairs)


def test_enumerate_contract_pairs_is_deterministic_for_unsorted_contracts() -> None:
    pairs = enumerate_contract_pairs(
        [
            OptionContract(strike=110),
            OptionContract(strike=90),
            OptionContract(strike=100),
        ],
        SpreadStrategy.BULL_CALL,
    )

    assert [
        (pair.long_strike, pair.short_strike)
        for pair in pairs
    ] == [
        (90.0, 100.0),
        (90.0, 110.0),
        (100.0, 110.0),
    ]


def test_enumerate_contract_pairs_does_not_filter_liquidity_fields() -> None:
    illiquid_contract = OptionContract(
        strike=90,
        bid=0.01,
        ask=9.99,
        implied_volatility=4.0,
        open_interest=0,
        volume=0,
    )
    contracts = [
        illiquid_contract,
        OptionContract(strike=100, bid=2.00, ask=2.10),
        OptionContract(strike=110, bid=0.90, ask=1.00),
    ]

    pairs = enumerate_contract_pairs(
        contracts,
        SpreadStrategy.BULL_CALL,
    )

    assert len(pairs) == 3
    assert sum(
        illiquid_contract in (pair.long_leg, pair.short_leg)
        for pair in pairs
    ) == 2


def test_enumerate_contract_pairs_rejects_duplicate_strikes() -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [OptionContract(strike=100), OptionContract(strike=100)],
            SpreadStrategy.BULL_CALL,
        )


@pytest.mark.parametrize(
    "bad_strike",
    [0, -1, float("nan"), float("inf"), True, "100"],
)
def test_option_contract_rejects_invalid_strikes(
    bad_strike: object,
) -> None:
    with pytest.raises(ContractEnumerationError):
        OptionContract(strike=bad_strike)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_strategy", ["call", "", None])
def test_enumerate_contract_pairs_rejects_invalid_strategy(
    bad_strategy: object,
) -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [OptionContract(strike=90), OptionContract(strike=100)],
            bad_strategy,  # type: ignore[arg-type]
        )


def test_enumerate_contract_pairs_rejects_non_contract_items() -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [90, 100],  # type: ignore[list-item]
            SpreadStrategy.BULL_CALL,
        )
