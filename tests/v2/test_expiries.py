from __future__ import annotations

from datetime import date

import pytest

from option_chaser.v2.expiries import (
    ExpiryResolutionError,
    resolve_expiries,
)


BASE_EXPIRIES = [
    "2027-11-19",
    "2027-12-17",
    "2028-01-21",
    "2028-02-18",
    "2028-03-17",
    "2028-06-16",
    "2028-09-15",
]


def test_resolve_expiries_uses_default_limit_of_five() -> None:
    assert resolve_expiries("2028/1", reversed(BASE_EXPIRIES)) == [
        "2027-11-19",
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
    ]


@pytest.mark.parametrize(
    ("max_expiries", "expected"),
    [
        (1, ["2028-01-21"]),
        (2, ["2028-01-21", "2028-02-18"]),
        (3, ["2027-12-17", "2028-01-21", "2028-02-18"]),
        (
            4,
            [
                "2027-12-17",
                "2028-01-21",
                "2028-02-18",
                "2028-03-17",
            ],
        ),
        (
            7,
            [
                "2027-11-19",
                "2027-12-17",
                "2028-01-21",
                "2028-02-18",
                "2028-03-17",
                "2028-06-16",
                "2028-09-15",
            ],
        ),
    ],
)
def test_resolve_expiries_honors_configurable_limit(
    max_expiries: int,
    expected: list[str],
) -> None:
    assert resolve_expiries(
        "2028-01",
        BASE_EXPIRIES,
        max_expiries=max_expiries,
    ) == expected


def test_resolve_expiries_fills_from_later_side() -> None:
    assert resolve_expiries(
        "2028-01",
        [
            "2027-12-17",
            "2028-01-21",
            "2028-02-18",
            "2028-03-17",
            "2028-06-16",
            "2028-09-15",
        ],
    ) == [
        "2027-12-17",
        "2028-01-21",
        "2028-02-18",
        "2028-03-17",
        "2028-06-16",
    ]


def test_resolve_expiries_fills_from_earlier_side() -> None:
    assert resolve_expiries(
        "2028-06",
        [
            "2028-01-21",
            "2028-02-18",
            "2028-03-17",
            "2028-04-21",
            "2028-05-19",
            "2028-06-16",
            "2028-07-21",
        ],
    ) == [
        "2028-03-17",
        "2028-04-21",
        "2028-05-19",
        "2028-06-16",
        "2028-07-21",
    ]


def test_resolve_expiries_crosses_year_boundary() -> None:
    assert resolve_expiries(
        "2029-01",
        [
            "2028-11-17",
            "2028-12-15",
            "2029-01-19",
            "2029-02-16",
            "2029-03-16",
            "2029-06-15",
        ],
    ) == [
        "2028-11-17",
        "2028-12-15",
        "2029-01-19",
        "2029-02-16",
        "2029-03-16",
    ]


def test_resolve_expiries_handles_leap_year_february() -> None:
    assert resolve_expiries(
        "2028-02",
        [
            "2028-01-21",
            "2028-02-02",
            "2028-02-16",
            "2028-02-29",
            "2028-03-17",
        ],
        max_expiries=3,
    ) == [
        "2028-02-02",
        "2028-02-16",
        "2028-02-29",
    ]


def test_resolve_expiries_handles_non_leap_year_february() -> None:
    assert resolve_expiries(
        "2029-02",
        [
            "2029-01-19",
            "2029-02-02",
            "2029-02-16",
            "2029-02-28",
            "2029-03-16",
        ],
        max_expiries=3,
    ) == [
        "2029-02-02",
        "2029-02-16",
        "2029-02-28",
    ]


def test_resolve_expiries_when_target_precedes_all_available_dates() -> None:
    assert resolve_expiries(
        "2027-01",
        BASE_EXPIRIES,
        max_expiries=3,
    ) == BASE_EXPIRIES[:3]


def test_resolve_expiries_when_target_follows_all_available_dates() -> None:
    assert resolve_expiries(
        "2031-12",
        BASE_EXPIRIES,
        max_expiries=3,
    ) == BASE_EXPIRIES[-3:]


def test_resolve_expiries_returns_all_when_limit_exceeds_supply() -> None:
    assert resolve_expiries(
        "2028-01",
        ["2027-12-17", "2028-01-21", "2028-02-18"],
        max_expiries=9,
    ) == ["2027-12-17", "2028-01-21", "2028-02-18"]


def test_resolve_expiries_removes_duplicates() -> None:
    result = resolve_expiries(
        "2028-01",
        [
            "2027-12-17",
            "2028-01-21",
            "2028-01-21",
            "2028-02-18",
        ],
    )

    assert result == ["2027-12-17", "2028-01-21", "2028-02-18"]


def test_resolve_expiries_prefers_later_baseline_on_equal_distance() -> None:
    assert resolve_expiries(
        "2028-01",
        ["2028-01-20", "2028-01-22"],
        max_expiries=1,
    ) == ["2028-01-22"]


@pytest.mark.parametrize(
    "bad_expiry",
    ["2028/01/21", "2028-1-21", "2028-02-30", 20280121],
)
def test_resolve_expiries_rejects_invalid_expiry_values(
    bad_expiry: object,
) -> None:
    with pytest.raises(ExpiryResolutionError):
        resolve_expiries(
            "2028-01",
            [bad_expiry],  # type: ignore[list-item]
        )


@pytest.mark.parametrize("bad_limit", [0, -1, 1.5, True, "5", None])
def test_resolve_expiries_rejects_invalid_limits(
    bad_limit: object,
) -> None:
    with pytest.raises(ExpiryResolutionError):
        resolve_expiries(
            "2028-01",
            BASE_EXPIRIES,
            max_expiries=bad_limit,  # type: ignore[arg-type]
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


@pytest.mark.parametrize("year", range(2027, 2032))
@pytest.mark.parametrize("month", range(1, 13))
def test_resolve_expiries_preserves_general_invariants(
    year: int,
    month: int,
) -> None:
    candidates = sorted(
        {
            date(year - 1, 12, 20).isoformat(),
            date(year, 1, 5).isoformat(),
            date(year, month, 1).isoformat(),
            date(year, month, 15).isoformat(),
            date(year, month, 28).isoformat(),
            date(year, 12, 20).isoformat(),
            date(year + 1, 1, 5).isoformat(),
        }
    )

    result = resolve_expiries(
        f"{year}-{month:02d}",
        candidates,
        max_expiries=5,
    )

    assert result == sorted(result)
    assert len(result) == len(set(result))
    assert len(result) <= 5
    assert set(result).issubset(candidates)
