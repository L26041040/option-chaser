from __future__ import annotations

import pytest

from option_chaser.enumerator import (
    ExpiryResolutionError,
    TargetMonthError,
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