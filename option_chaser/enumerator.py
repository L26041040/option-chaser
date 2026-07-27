"""Pure enumeration utilities for Option Chaser MVP V2.

This module must remain independent from market-data downloads, legacy filters,
UI code, and persistence.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
import re


_TARGET_MONTH_PATTERN = re.compile(
    r"^(?P<year>\d{4})(?P<separator>[-/])(?P<month>\d{1,2})$"
)
_EXPIRY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_SELECTED_EXPIRIES = 5
_EXPIRIES_PER_SIDE = 2


class TargetMonthError(ValueError):
    """Raised when a target-month value cannot be normalized."""


class ExpiryResolutionError(ValueError):
    """Raised when available option expiries cannot be resolved."""


def normalize_target_month(value: str) -> str:
    """Normalize a supported target-month string to ``YYYY-MM``.

    Accepted input formats:

    - ``YYYY/M``
    - ``YYYY/MM``
    - ``YYYY-M``
    - ``YYYY-MM``

    Leading and trailing whitespace is ignored.

    Args:
        value: User-supplied target month.

    Returns:
        The normalized target month in ``YYYY-MM`` format.

    Raises:
        TargetMonthError: If the input is not a string, has an unsupported
            format, or contains an invalid year or month.
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


def resolve_expiries(
    target_month: str,
    available_expiries: Iterable[str],
) -> list[str]:
    """Select up to five actual expiries around a requested target month.

    The third Friday of the target month is used as the deterministic
    reference date because it represents the conventional monthly-expiry
    position within the month.

    Selection rules:

    1. Find the actual expiry nearest to the target month's third Friday.
    2. If two expiries are equally near, prefer the later expiry.
    3. Include up to two expiries before the baseline.
    4. Include up to two expiries after the baseline.
    5. If one side is short, fill from the nearest remaining expiries.
    6. Remove duplicates and return results chronologically.
    7. Never invent an expiry date.

    Args:
        target_month: Target month accepted by ``normalize_target_month``.
        available_expiries: Actual expiry strings in ``YYYY-MM-DD`` format.

    Returns:
        Up to five unique expiry strings in chronological order.

    Raises:
        TargetMonthError: If ``target_month`` is invalid.
        ExpiryResolutionError: If the expiry collection is empty, malformed,
            or contains an invalid expiry.
    """

    normalized_month = normalize_target_month(target_month)

    if isinstance(available_expiries, (str, bytes)):
        raise ExpiryResolutionError(
            "available_expiries must be an iterable of expiry strings, "
            "not one plain string"
        )

    try:
        raw_expiries = list(available_expiries)
    except TypeError as exc:
        raise ExpiryResolutionError(
            "available_expiries must be an iterable of expiry strings"
        ) from exc

    if not raw_expiries:
        raise ExpiryResolutionError(
            "available_expiries must contain at least one expiry"
        )

    parsed_expiries = sorted(
        {_parse_expiry(raw_expiry) for raw_expiry in raw_expiries}
    )

    year_text, month_text = normalized_month.split("-")
    reference_date = _third_friday(
        year=int(year_text),
        month=int(month_text),
    )

    baseline = min(
        parsed_expiries,
        key=lambda expiry: (
            abs((expiry - reference_date).days),
            -expiry.toordinal(),
        ),
    )
    baseline_index = parsed_expiries.index(baseline)

    selected: set[date] = {baseline}

    selected.update(
        parsed_expiries[
            max(0, baseline_index - _EXPIRIES_PER_SIDE) : baseline_index
        ]
    )
    selected.update(
        parsed_expiries[
            baseline_index + 1 : baseline_index + 1 + _EXPIRIES_PER_SIDE
        ]
    )

    if len(selected) < _MAX_SELECTED_EXPIRIES:
        remaining = [
            expiry
            for expiry in parsed_expiries
            if expiry not in selected
        ]
        remaining.sort(
            key=lambda expiry: (
                abs((expiry - baseline).days),
                expiry,
            )
        )

        spaces_remaining = _MAX_SELECTED_EXPIRIES - len(selected)
        selected.update(remaining[:spaces_remaining])

    return [
        expiry.isoformat()
        for expiry in sorted(selected)
    ]


def _parse_expiry(value: object) -> date:
    """Parse one strict ISO expiry string."""

    if not isinstance(value, str):
        raise ExpiryResolutionError(
            f"expiry must be a YYYY-MM-DD string: {value!r}"
        )

    stripped_value = value.strip()

    if _EXPIRY_PATTERN.fullmatch(stripped_value) is None:
        raise ExpiryResolutionError(
            f"expiry must use YYYY-MM-DD format: {value!r}"
        )

    try:
        return date.fromisoformat(stripped_value)
    except ValueError as exc:
        raise ExpiryResolutionError(
            f"expiry contains an invalid calendar date: {value!r}"
        ) from exc


def _third_friday(year: int, month: int) -> date:
    """Return the third Friday of a calendar month."""

    first_day = date(year, month, 1)
    friday_weekday = 4
    days_until_first_friday = (
        friday_weekday - first_day.weekday()
    ) % 7

    return first_day + timedelta(
        days=days_until_first_friday + 14
    )