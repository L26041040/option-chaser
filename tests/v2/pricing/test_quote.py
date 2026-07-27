from __future__ import annotations

import pytest

from option_chaser.v2.models import (
    OptionContract,
    SpreadPair,
    SpreadStrategy,
)
from option_chaser.v2.pricing.quote import (
    QuoteCalculationError,
    SpreadQuote,
    calculate_midpoint,
    calculate_spread_quote,
)


def _bull_call_pair(
    *,
    long_bid: float | None = 11.0,
    long_ask: float | None = 12.0,
    short_bid: float | None = 4.0,
    short_ask: float | None = 5.0,
) -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=90,
            bid=long_bid,
            ask=long_ask,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=short_bid,
            ask=short_ask,
        ),
    )


def _bear_put_pair(
    *,
    long_bid: float | None = 10.0,
    long_ask: float | None = 11.0,
    short_bid: float | None = 3.0,
    short_ask: float | None = 4.0,
) -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BEAR_PUT,
        long_leg=OptionContract(
            strike=110,
            bid=long_bid,
            ask=long_ask,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=short_bid,
            ask=short_ask,
        ),
    )


def test_calculate_midpoint() -> None:
    assert calculate_midpoint(2.0, 4.0) == 3.0


def test_calculate_midpoint_accepts_zero_quote() -> None:
    assert calculate_midpoint(0.0, 2.0) == 1.0


@pytest.mark.parametrize(
    ("bid", "ask"),
    [
        (None, 2.0),
        (1.0, None),
        (None, None),
    ],
)
def test_calculate_midpoint_returns_none_when_source_quote_is_missing(
    bid: float | None,
    ask: float | None,
) -> None:
    assert calculate_midpoint(bid, ask) is None


@pytest.mark.parametrize(
    ("bid", "ask"),
    [
        (-1.0, 2.0),
        (1.0, -2.0),
        (float("nan"), 2.0),
        (1.0, float("nan")),
        (float("inf"), 2.0),
        (1.0, float("inf")),
        (True, 2.0),
        (1.0, False),
        ("1.0", 2.0),
        (1.0, "2.0"),
    ],
)
def test_calculate_midpoint_rejects_malformed_quotes(
    bid: object,
    ask: object,
) -> None:
    with pytest.raises(QuoteCalculationError):
        calculate_midpoint(  # type: ignore[arg-type]
            bid,
            ask,
        )


def test_calculate_bull_call_spread_quote() -> None:
    result = calculate_spread_quote(_bull_call_pair())

    assert result == SpreadQuote(
        long_mid=11.5,
        short_mid=4.5,
        spread_bid=6.0,
        spread_mid=7.0,
        spread_ask=8.0,
    )


def test_calculate_bear_put_spread_quote_uses_same_debit_formulas() -> None:
    result = calculate_spread_quote(_bear_put_pair())

    assert result == SpreadQuote(
        long_mid=10.5,
        short_mid=3.5,
        spread_bid=6.0,
        spread_mid=7.0,
        spread_ask=8.0,
    )


def test_missing_long_bid_only_invalidates_dependent_values() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(long_bid=None)
    )

    assert result.long_mid is None
    assert result.short_mid == 4.5
    assert result.spread_bid is None
    assert result.spread_mid is None
    assert result.spread_ask == 8.0


def test_missing_long_ask_only_invalidates_dependent_values() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(long_ask=None)
    )

    assert result.long_mid is None
    assert result.short_mid == 4.5
    assert result.spread_bid == 6.0
    assert result.spread_mid is None
    assert result.spread_ask is None


def test_missing_short_bid_only_invalidates_dependent_values() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(short_bid=None)
    )

    assert result.long_mid == 11.5
    assert result.short_mid is None
    assert result.spread_bid == 6.0
    assert result.spread_mid is None
    assert result.spread_ask is None


def test_missing_short_ask_only_invalidates_dependent_values() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(short_ask=None)
    )

    assert result.long_mid == 11.5
    assert result.short_mid is None
    assert result.spread_bid is None
    assert result.spread_mid is None
    assert result.spread_ask == 8.0


def test_all_missing_quotes_return_all_none_values() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(
            long_bid=None,
            long_ask=None,
            short_bid=None,
            short_ask=None,
        )
    )

    assert result == SpreadQuote(
        long_mid=None,
        short_mid=None,
        spread_bid=None,
        spread_mid=None,
        spread_ask=None,
    )


def test_zero_quotes_are_not_treated_as_missing() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(
            long_bid=0.0,
            long_ask=0.0,
            short_bid=0.0,
            short_ask=0.0,
        )
    )

    assert result == SpreadQuote(
        long_mid=0.0,
        short_mid=0.0,
        spread_bid=0.0,
        spread_mid=0.0,
        spread_ask=0.0,
    )


def test_negative_derived_spread_is_preserved_for_return_layer() -> None:
    result = calculate_spread_quote(
        _bull_call_pair(
            long_bid=1.0,
            long_ask=2.0,
            short_bid=3.0,
            short_ask=4.0,
        )
    )

    assert result.spread_bid == -3.0
    assert result.spread_mid == -2.0
    assert result.spread_ask == -1.0


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("long_bid", -1.0),
        ("long_ask", float("nan")),
        ("short_bid", float("inf")),
        ("short_ask", True),
    ],
)
def test_calculate_spread_quote_rejects_malformed_leg_quotes(
    field_name: str,
    bad_value: object,
) -> None:
    arguments: dict[str, object] = {
        "long_bid": 11.0,
        "long_ask": 12.0,
        "short_bid": 4.0,
        "short_ask": 5.0,
    }
    arguments[field_name] = bad_value

    pair = _bull_call_pair(
        **arguments,  # type: ignore[arg-type]
    )

    with pytest.raises(QuoteCalculationError):
        calculate_spread_quote(pair)


def test_calculate_spread_quote_rejects_non_pair_value() -> None:
    with pytest.raises(QuoteCalculationError):
        calculate_spread_quote(  # type: ignore[arg-type]
            "not a spread pair"
        )


def test_spread_quote_is_immutable() -> None:
    result = calculate_spread_quote(_bull_call_pair())

    with pytest.raises(AttributeError):
        result.spread_ask = 99.0  # type: ignore[misc]