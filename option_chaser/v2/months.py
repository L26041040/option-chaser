"""Target-month parsing for Option Chaser MVP V2."""

from __future__ import annotations

from datetime import date
import re


_TARGET_MONTH_PATTERN = re.compile(
    r"^(?P<year>\d{4})(?P<separator>[-/])(?P<month>\d{1,2})$"
)


class TargetMonthError(ValueError):
    """Raised when a target-month value cannot be normalized."""


def normalize_target_month(value: str) -> str:
    """Normalize a supported target-month string to ``YYYY-MM``.

    Accepted formats are ``YYYY/M``, ``YYYY/MM``, ``YYYY-M``, and
    ``YYYY-MM``. Leading and trailing whitespace is ignored.
    """

    if not isinstance(value, str):
        raise TargetMonthError("target_month must be a string")

    stripped_value = value.strip()
    match = _TARGET_MONTH_PATTERN.fullmatch(stripped_value)

    if match is None:
        raise TargetMonthError(
            "target_month must use YYYY/M, YYYY/MM, YYYY-M, or YYYY-MM"
        )

    year = int(match.group("year"))
    month = int(match.group("month"))

    try:
        date(year, month, 1)
    except ValueError as exc:
        raise TargetMonthError(
            f"target_month contains an invalid year or month: {value!r}"
        ) from exc

    return f"{year:04d}-{month:02d}"
