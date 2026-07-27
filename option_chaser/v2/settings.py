"""Configuration values for the Option Chaser MVP V2 core."""

from __future__ import annotations

from dataclasses import dataclass


class SettingsError(ValueError):
    """Raised when an MVP V2 setting is invalid."""


def _require_positive_int(value: object, *, field_name: str) -> int:
    """Return one positive integer or raise ``SettingsError``."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SettingsError(f"{field_name} must be a positive integer")

    return value


@dataclass(frozen=True, slots=True)
class V2Settings:
    """Validated settings shared by the MVP V2 service and core modules."""

    max_expiries: int = 5
    top_spreads_per_expiry: int = 10

    def __post_init__(self) -> None:
        _require_positive_int(
            self.max_expiries,
            field_name="max_expiries",
        )
        _require_positive_int(
            self.top_spreads_per_expiry,
            field_name="top_spreads_per_expiry",
        )


DEFAULT_V2_SETTINGS = V2Settings()
