"""Expiry selection for Option Chaser MVP V2."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
import re

from option_chaser.v2.months import normalize_target_month
from option_chaser.v2.settings import DEFAULT_V2_SETTINGS


_EXPIRY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ExpiryResolutionError(ValueError):
    """Raised when available option expiries cannot be resolved."""


def resolve_expiries(
    target_month: str,
    available_expiries: Iterable[str],
    *,
    max_expiries: int = DEFAULT_V2_SETTINGS.max_expiries,
) -> list[str]:
    """Select actual expiries around a requested target month.

    The actual expiry nearest to the target month's third Friday becomes the
    baseline. Ties prefer the later expiry. The remaining capacity is divided
    around the baseline; when ``max_expiries`` is even, the later side receives
    the extra preferred slot. If either side is short, the nearest remaining
    actual expiries fill the unused capacity.
    """

    normalized_month = normalize_target_month(target_month)
    normalized_limit = _normalize_max_expiries(max_expiries)

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

    remaining_preferred_slots = normalized_limit - 1
    before_quota = remaining_preferred_slots // 2
    after_quota = remaining_preferred_slots - before_quota

    selected: set[date] = {baseline}
    selected.update(
        parsed_expiries[
            max(0, baseline_index - before_quota) : baseline_index
        ]
    )
    selected.update(
        parsed_expiries[
            baseline_index + 1 : baseline_index + 1 + after_quota
        ]
    )

    if len(selected) < normalized_limit:
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

        spaces_remaining = normalized_limit - len(selected)
        selected.update(remaining[:spaces_remaining])

    return [
        expiry.isoformat()
        for expiry in sorted(selected)
    ]


def _normalize_max_expiries(value: object) -> int:
    """Validate the caller-selected expiry limit."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExpiryResolutionError(
            "max_expiries must be a positive integer"
        )

    return value


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
