from option_chaser import enumerator
from option_chaser import v2


def test_compatibility_entry_point_reexports_v2_objects() -> None:
    exported_names = [
        "ContractEnumerationError",
        "DEFAULT_V2_SETTINGS",
        "ExpiryResolutionError",
        "OptionContract",
        "PayoffCalculationError",
        "QuoteCalculationError",
        "SettingsError",
        "SpreadPair",
        "SpreadPayoff",
        "SpreadQuote",
        "SpreadStrategy",
        "TargetMonthError",
        "V2Settings",
        "calculate_midpoint",
        "calculate_spread_payoff",
        "calculate_spread_quote",
        "enumerate_contract_pairs",
        "normalize_target_month",
        "resolve_expiries",
    ]

    for name in exported_names:
        assert getattr(enumerator, name) is getattr(v2, name)