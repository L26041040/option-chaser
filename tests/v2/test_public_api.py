from option_chaser import enumerator
from option_chaser import v2


def test_compatibility_entry_point_reexports_v2_objects() -> None:
    exported_names = [
        "CandidateEvaluationError",
        "CandidateEvaluationResult",
        "ContractEnumerationError",
        "DEFAULT_V2_SETTINGS",
        "ExpiryResolutionError",
        "OptionContract",
        "PayoffCalculationError",
        "PricedSpread",
        "PricedSpreadError",
        "QuoteCalculationError",
        "ReturnCalculationError",
        "SettingsError",
        "SpreadPair",
        "SpreadPayoff",
        "SpreadQuote",
        "SpreadReturn",
        "SpreadStrategy",
        "TargetMonthError",
        "V2Settings",
        "calculate_midpoint",
        "calculate_spread_payoff",
        "calculate_spread_quote",
        "calculate_spread_return",
        "enumerate_contract_pairs",
        "evaluate_candidates",
        "normalize_target_month",
        "price_spread",
        "resolve_expiries",
    ]

    for name in exported_names:
        assert getattr(enumerator, name) is getattr(v2, name)