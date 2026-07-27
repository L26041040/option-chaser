from dataclasses import FrozenInstanceError

import pytest

from option_chaser.v2.settings import (
    DEFAULT_V2_SETTINGS,
    SettingsError,
    V2Settings,
)


def test_v2_settings_defaults() -> None:
    assert DEFAULT_V2_SETTINGS == V2Settings()
    assert DEFAULT_V2_SETTINGS.max_expiries == 5
    assert DEFAULT_V2_SETTINGS.top_spreads_per_expiry == 10


def test_v2_settings_accepts_custom_positive_integers() -> None:
    settings = V2Settings(
        max_expiries=7,
        top_spreads_per_expiry=25,
    )

    assert settings.max_expiries == 7
    assert settings.top_spreads_per_expiry == 25


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, True, "5", None])
def test_v2_settings_rejects_invalid_max_expiries(
    bad_value: object,
) -> None:
    with pytest.raises(SettingsError):
        V2Settings(max_expiries=bad_value)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, True, "10", None])
def test_v2_settings_rejects_invalid_top_spreads(
    bad_value: object,
) -> None:
    with pytest.raises(SettingsError):
        V2Settings(top_spreads_per_expiry=bad_value)  # type: ignore[arg-type]


def test_v2_settings_is_immutable() -> None:
    settings = V2Settings()

    with pytest.raises(FrozenInstanceError):
        settings.max_expiries = 9  # type: ignore[misc]
