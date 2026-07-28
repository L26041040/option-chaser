"""Stable public API for the Option Chaser MVP V2 core."""

from option_chaser.v2.expiries import (
    ExpiryResolutionError,
    resolve_expiries,
)
from option_chaser.v2.models import (
    ContractEnumerationError,
    OptionContract,
    SpreadPair,
    SpreadStrategy,
)
from option_chaser.v2.months import (
    TargetMonthError,
    normalize_target_month,
)
from option_chaser.v2.pairing import enumerate_contract_pairs
from option_chaser.v2.priced import (
    PricedSpread,
    PricedSpreadError,
    price_spread,
)
from option_chaser.v2.pricing import (
    PayoffCalculationError,
    QuoteCalculationError,
    ReturnCalculationError,
    SpreadPayoff,
    SpreadQuote,
    SpreadReturn,
    calculate_midpoint,
    calculate_spread_payoff,
    calculate_spread_quote,
    calculate_spread_return,
)
from option_chaser.v2.settings import (
    DEFAULT_V2_SETTINGS,
    SettingsError,
    V2Settings,
)

__all__ = [
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
    "normalize_target_month",
    "price_spread",
    "resolve_expiries",
]