from __future__ import annotations

import pytest

from option_chaser.v2.models import (
    OptionContract,
    SpreadPair,
    SpreadStrategy,
)
from option_chaser.v2.pricing.payoff import (
    PayoffCalculationError,
    SpreadPayoff,
    calculate_spread_payoff,
)


def _bull_call_pair() -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=90,
            bid=11,
            ask=12,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=4,
            ask=5,
        ),
    )


def _bear_put_pair() -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BEAR_PUT,
        long_leg=OptionContract(
            strike=110,
            bid=10,
            ask=11,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=3,
            ask=4,
        ),
    )


@pytest.mark.parametrize(
    ("target_price", "expected_payoff"),
    [
        (80.0, 0.0),
        (90.0, 0.0),
        (95.0, 5.0),
        (100.0, 10.0),
        (105.0, 10.0),
        (150.0, 10.0),
    ],
)
def test_bull_call_target_payoff(
    target_price: float,
    expected_payoff: float,
) -> None:
    result = calculate_spread_payoff(
        _bull_call_pair(),
        target_price,
    )

    assert result == SpreadPayoff(
        spread_width=10.0,
        target_payoff=expected_payoff,
        max_payoff=10.0,
    )


@pytest.mark.parametrize(
    ("target_price", "expected_payoff"),
    [
        (130.0, 0.0),
        (110.0, 0.0),
        (105.0, 5.0),
        (100.0, 10.0),
        (95.0, 10.0),
        (50.0, 10.0),
    ],
)
def test_bear_put_target_payoff(
    target_price: float,
    expected_payoff: float,
) -> None:
    result = calculate_spread_payoff(
        _bear_put_pair(),
        target_price,
    )

    assert result == SpreadPayoff(
        spread_width=10.0,
        target_payoff=expected_payoff,
        max_payoff=10.0,
    )


def test_payoff_ignores_quotes_and_liquidity_fields() -> None:
    pair = SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=90,
            bid=None,
            ask=None,
            implied_volatility=None,
            open_interest=None,
            volume=None,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=None,
            ask=None,
            implied_volatility=None,
            open_interest=None,
            volume=None,
        ),
    )

    result = calculate_spread_payoff(
        pair,
        target_price=97,
    )

    assert result == SpreadPayoff(
        spread_width=10.0,
        target_payoff=7.0,
        max_payoff=10.0,
    )


def test_fractional_strikes_and_target_price() -> None:
    pair = SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(strike=92.5),
        short_leg=OptionContract(strike=97.5),
    )

    result = calculate_spread_payoff(
        pair,
        target_price=95.25,
    )

    assert result == SpreadPayoff(
        spread_width=5.0,
        target_payoff=2.75,
        max_payoff=5.0,
    )


@pytest.mark.parametrize(
    "bad_target_price",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "100",
        None,
    ],
)
def test_rejects_invalid_target_price(
    bad_target_price: object,
) -> None:
    with pytest.raises(PayoffCalculationError):
        calculate_spread_payoff(
            _bull_call_pair(),
            bad_target_price,  # type: ignore[arg-type]
        )


def test_rejects_non_pair_value() -> None:
    with pytest.raises(PayoffCalculationError):
        calculate_spread_payoff(
            "not a pair",  # type: ignore[arg-type]
            target_price=100,
        )


def test_spread_payoff_is_immutable() -> None:
    result = calculate_spread_payoff(
        _bull_call_pair(),
        target_price=95,
    )

    with pytest.raises(AttributeError):
        result.target_payoff = 99.0  # type: ignore[misc]