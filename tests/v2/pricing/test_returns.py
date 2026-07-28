from __future__ import annotations

import pytest

from option_chaser.v2.pricing.payoff import SpreadPayoff
from option_chaser.v2.pricing.quote import SpreadQuote
from option_chaser.v2.pricing.returns import (
    ReturnCalculationError,
    SpreadReturn,
    calculate_spread_return,
)


def _quote(
    *,
    spread_ask: float | None,
) -> SpreadQuote:
    return SpreadQuote(
        long_mid=None,
        short_mid=None,
        spread_bid=None,
        spread_mid=None,
        spread_ask=spread_ask,
    )


def _payoff(
    *,
    target_payoff: float,
) -> SpreadPayoff:
    return SpreadPayoff(
        spread_width=10.0,
        target_payoff=target_payoff,
        max_payoff=10.0,
    )


def test_calculates_positive_ask_return() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=4.0),
        _payoff(target_payoff=7.0),
    )

    assert result == SpreadReturn(
        entry_cost=400.0,
        ask_return=300.0,
        ask_return_percent=75.0,
        rankable=True,
    )


def test_calculates_zero_ask_return() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=5.0),
        _payoff(target_payoff=5.0),
    )

    assert result == SpreadReturn(
        entry_cost=500.0,
        ask_return=0.0,
        ask_return_percent=0.0,
        rankable=True,
    )


def test_negative_return_remains_rankable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=8.0),
        _payoff(target_payoff=5.0),
    )

    assert result == SpreadReturn(
        entry_cost=800.0,
        ask_return=-300.0,
        ask_return_percent=-37.5,
        rankable=True,
    )


def test_missing_spread_ask_is_not_rankable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=None),
        _payoff(target_payoff=7.0),
    )

    assert result == SpreadReturn(
        entry_cost=None,
        ask_return=None,
        ask_return_percent=None,
        rankable=False,
    )


def test_zero_entry_cost_is_not_rankable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=0.0),
        _payoff(target_payoff=7.0),
    )

    assert result == SpreadReturn(
        entry_cost=0.0,
        ask_return=700.0,
        ask_return_percent=None,
        rankable=False,
    )


def test_negative_entry_cost_is_preserved_but_not_rankable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=-1.0),
        _payoff(target_payoff=7.0),
    )

    assert result == SpreadReturn(
        entry_cost=-100.0,
        ask_return=800.0,
        ask_return_percent=None,
        rankable=False,
    )


def test_custom_contract_multiplier() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=4.0),
        _payoff(target_payoff=7.0),
        contract_multiplier=50,
    )

    assert result == SpreadReturn(
        entry_cost=200.0,
        ask_return=150.0,
        ask_return_percent=75.0,
        rankable=True,
    )


def test_fractional_values() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=2.25),
        _payoff(target_payoff=3.75),
    )

    assert result.entry_cost == pytest.approx(225.0)
    assert result.ask_return == pytest.approx(150.0)
    assert result.ask_return_percent == pytest.approx(
        66.66666666666667
    )
    assert result.rankable is True


def test_spread_ask_above_max_payoff_is_still_calculable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=12.0),
        _payoff(target_payoff=10.0),
    )

    assert result == SpreadReturn(
        entry_cost=1200.0,
        ask_return=-200.0,
        ask_return_percent=pytest.approx(
            -16.666666666666668
        ),
        rankable=True,
    )


@pytest.mark.parametrize(
    "bad_multiplier",
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
def test_rejects_invalid_contract_multiplier(
    bad_multiplier: object,
) -> None:
    with pytest.raises(ReturnCalculationError):
        calculate_spread_return(
            _quote(spread_ask=4.0),
            _payoff(target_payoff=7.0),
            contract_multiplier=bad_multiplier,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "bad_spread_ask",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "4",
    ],
)
def test_rejects_malformed_spread_ask(
    bad_spread_ask: object,
) -> None:
    malformed_quote = SpreadQuote(
        long_mid=None,
        short_mid=None,
        spread_bid=None,
        spread_mid=None,
        spread_ask=bad_spread_ask,  # type: ignore[arg-type]
    )

    with pytest.raises(ReturnCalculationError):
        calculate_spread_return(
            malformed_quote,
            _payoff(target_payoff=7.0),
        )


@pytest.mark.parametrize(
    "bad_target_payoff",
    [
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "7",
        None,
    ],
)
def test_rejects_malformed_target_payoff(
    bad_target_payoff: object,
) -> None:
    malformed_payoff = SpreadPayoff(
        spread_width=10.0,
        target_payoff=bad_target_payoff,  # type: ignore[arg-type]
        max_payoff=10.0,
    )

    with pytest.raises(ReturnCalculationError):
        calculate_spread_return(
            _quote(spread_ask=4.0),
            malformed_payoff,
        )


def test_rejects_non_quote_value() -> None:
    with pytest.raises(ReturnCalculationError):
        calculate_spread_return(
            "not a quote",  # type: ignore[arg-type]
            _payoff(target_payoff=7.0),
        )


def test_rejects_non_payoff_value() -> None:
    with pytest.raises(ReturnCalculationError):
        calculate_spread_return(
            _quote(spread_ask=4.0),
            "not a payoff",  # type: ignore[arg-type]
        )


def test_spread_return_is_immutable() -> None:
    result = calculate_spread_return(
        _quote(spread_ask=4.0),
        _payoff(target_payoff=7.0),
    )

    with pytest.raises(AttributeError):
        result.ask_return = 999.0  # type: ignore[misc]