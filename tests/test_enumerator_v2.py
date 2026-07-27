from __future__ import annotations

import pytest

from option_chaser.enumerator import (
    ContractEnumerationError,
    ExpiryResolutionError,
    OptionContract,
    SpreadStrategy,
    TargetMonthError,
    enumerate_contract_pairs,
    normalize_target_month,
    resolve_expiries,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("2028/1", "2028-01"),
        ("2028/01", "2028-01"),
        ("2028-1", "2028-01"),
        ("2028-01", "2028-01"),
        ("  2028/1  ", "2028-01"),
    ],
)
def test_normalize_target_month_accepts_supported_formats(
    raw_value: str,
    expected: str,
) -> None:
    assert normalize_target_month(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "2028",
        "2028/0",
        "2028/13",
        "2028/001",
        "28/1",
        "2028.01",
        "2028/1/1",
        "0000/1",
    ],
)
def test_normalize_target_month_rejects_invalid_strings(
    raw_value: str,
) -> None:
    with pytest.raises(TargetMonthError):
        normalize_target_month(raw_value)


@pytest.mark.parametrize(
    "raw_value",
    [
        None,
        202801,
        2028.01,
    ],
)
def test_normalize_target_month_rejects_non_strings(
    raw_value: object,
) -> None:
    with pytest.raises(TargetMonthError):
        normalize_target_month(raw_value)  # type: ignore[arg-type]


def test_normalize_target_month_is_idempotent() -> None:
    normalized = normalize_target_month("2028/1")

    assert normalize_target_month(normalized) == normalized


def test_resolve_expiries_selects_baseline_and_two_on_each_side() -> None:
    available_expiries = [
        "2028-06-16",
        "2028-03-17",
        "2027-11-19",
        "2028-01-21",
        "2028-02-18",
        "2027-12-17",
    ]

    assert resolve_expiries(
        "2028/1",
        available_expiries,
    ) == [
        "2027-11-19",
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
    ]


def test_resolve_expiries_fills_from_later_side() -> None:
    available_expiries = [
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
        "2028-06-16",
        "2028-09-15",
    ]

    assert resolve_expiries(
        "2028-01",
        available_expiries,
    ) == [
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
        "2028-06-16",
    ]


def test_resolve_expiries_fills_from_earlier_side() -> None:
    available_expiries = [
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
        "2028-04-21",
        "2028-05-19",
        "2028-06-16",
        "2028-07-21",
    ]

    assert resolve_expiries(
        "2028-06",
        available_expiries,
    ) == [
        "2028-03-17",
        "2028-04-21",
        "2028-05-19",
        "2028-06-16",
        "2028-07-21",
    ]


def test_resolve_expiries_returns_all_when_fewer_than_five_exist() -> None:
    assert resolve_expiries(
        "2028-01",
        [
            "2028-03-17",
            "2027-12-17",
            "2028-01-21",
        ],
    ) == [
        "2027-12-17",
        "2028-01-21",
        "2028-03-17",
    ]


def test_resolve_expiries_removes_duplicates() -> None:
    assert resolve_expiries(
        "2028-01",
        [
            "2027-12-17",
            "2028-01-21",
            "2028-01-21",
            "2028-02-18",
            "2028-03-17",
            "2028-06-16",
        ],
    ) == [
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
        "2028-06-16",
    ]


def test_resolve_expiries_prefers_later_baseline_on_equal_distance() -> None:
    assert resolve_expiries(
        "2028-01",
        [
            "2028-01-18",
            "2028-01-19",
            "2028-01-20",
            "2028-01-22",
            "2028-01-23",
            "2028-01-24",
        ],
    ) == [
        "2028-01-19",
        "2028-01-20",
        "2028-01-22",
        "2028-01-23",
        "2028-01-24",
    ]


@pytest.mark.parametrize(
    "bad_expiry",
    [
        "2028/01/21",
        "2028-1-21",
        "2028-02-30",
        20280121,
    ],
)
def test_resolve_expiries_rejects_invalid_expiry_values(
    bad_expiry: object,
) -> None:
    with pytest.raises(ExpiryResolutionError):
        resolve_expiries(
            "2028-01",
            [bad_expiry],  # type: ignore[list-item]
        )


def test_resolve_expiries_rejects_empty_collection() -> None:
    with pytest.raises(ExpiryResolutionError):
        resolve_expiries("2028-01", [])


def test_resolve_expiries_rejects_one_plain_string() -> None:
    with pytest.raises(ExpiryResolutionError):
        resolve_expiries(
            "2028-01",
            "2028-01-21",  # type: ignore[arg-type]
        )


def test_enumerate_contract_pairs_generates_all_ten_pairs_from_five_contracts() -> None:
    contracts = [
        OptionContract(strike=90),
        OptionContract(strike=95),
        OptionContract(strike=100),
        OptionContract(strike=105),
        OptionContract(strike=110),
    ]

    pairs = enumerate_contract_pairs(
        contracts,
        SpreadStrategy.BULL_CALL,
    )

    assert len(pairs) == 10


def test_enumerate_contract_pairs_orders_bull_call_legs() -> None:
    pairs = enumerate_contract_pairs(
        [
            OptionContract(strike=110),
            OptionContract(strike=90),
            OptionContract(strike=100),
        ],
        "bull_call",
    )

    assert all(
        pair.long_strike < pair.short_strike
        for pair in pairs
    )


def test_enumerate_contract_pairs_orders_bear_put_legs() -> None:
    pairs = enumerate_contract_pairs(
        [
            OptionContract(strike=110),
            OptionContract(strike=90),
            OptionContract(strike=100),
        ],
        "bear_put",
    )

    assert all(
        pair.long_strike > pair.short_strike
        for pair in pairs
    )


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
        OptionContract(
            strike=100,
            bid=2.00,
            ask=2.10,
            open_interest=500,
            volume=100,
        ),
        OptionContract(
            strike=110,
            bid=0.90,
            ask=1.00,
            open_interest=1000,
            volume=500,
        ),
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


@pytest.mark.parametrize(
    "contracts",
    [
        [],
        [OptionContract(strike=100)],
    ],
)
def test_enumerate_contract_pairs_returns_empty_for_fewer_than_two_contracts(
    contracts: list[OptionContract],
) -> None:
    assert enumerate_contract_pairs(
        contracts,
        SpreadStrategy.BULL_CALL,
    ) == []


def test_enumerate_contract_pairs_rejects_duplicate_strikes() -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [
                OptionContract(strike=100),
                OptionContract(strike=100),
            ],
            SpreadStrategy.BULL_CALL,
        )


@pytest.mark.parametrize(
    "bad_strike",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        True,
        "100",
    ],
)
def test_option_contract_rejects_invalid_strikes(
    bad_strike: object,
) -> None:
    with pytest.raises(ContractEnumerationError):
        OptionContract(strike=bad_strike)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_strategy",
    [
        "call",
        "",
        None,
    ],
)
def test_enumerate_contract_pairs_rejects_invalid_strategy(
    bad_strategy: object,
) -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [
                OptionContract(strike=90),
                OptionContract(strike=100),
            ],
            bad_strategy,  # type: ignore[arg-type]
        )


def test_enumerate_contract_pairs_rejects_non_contract_items() -> None:
    with pytest.raises(ContractEnumerationError):
        enumerate_contract_pairs(
            [90, 100],  # type: ignore[list-item]
            SpreadStrategy.BULL_CALL,
        )