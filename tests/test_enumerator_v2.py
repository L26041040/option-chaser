from __future__ import annotations

import pytest

from option_chaser.enumerator import (
    TargetMonthError,
    normalize_target_month,
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