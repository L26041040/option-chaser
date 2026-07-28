from __future__ import annotations

from dataclasses import replace

import pytest

from option_chaser.v2.models import (
    OptionContract,
    SpreadPair,
    SpreadStrategy,
)
from option_chaser.v2.priced import (
    PricedSpread,
    PricedSpreadError,
    price_spread,
)
from option_chaser.v2.pricing.payoff import (
    SpreadPayoff,
    calculate_spread_payoff,
)
from option_chaser.v2.pricing.quote import (
    SpreadQuote,
    calculate_spread_quote,
)
from option_chaser.v2.pricing.returns import (
    SpreadReturn,
    calculate_spread_return,
)


def _bull_call_pair() -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=100,
            bid=4.0,
            ask=4.2,
            implied_volatility=0.25,
            open_interest=1200,
            volume=350,
        ),
        short_leg=OptionContract(
            strike=110,
            bid=1.8,
            ask=2.0,
            implied_volatility=0.22,
            open_interest=900,
            volume=240,
        ),
    )


def _bear_put_pair() -> SpreadPair:
    return SpreadPair(
        strategy=SpreadStrategy.BEAR_PUT,
        long_leg=OptionContract(
            strike=110,
            bid=8.0,
            ask=8.5,
        ),
        short_leg=OptionContract(
            strike=100,
            bid=4.0,
            ask=4.5,
        ),
    )


def test_prices_bull_call_candidate() -> None:
    pair = _bull_call_pair()

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
    )

    assert isinstance(result, PricedSpread)
    assert result.pair is pair
    assert result.expiry == "2028-01-21"
    assert result.target_price == 108.0
    assert result.contract_multiplier == 100.0

    assert result.quote == SpreadQuote(
        long_mid=4.1,
        short_mid=1.9,
        spread_bid=2.0,
        spread_mid=pytest.approx(2.2),
        spread_ask=pytest.approx(2.4),
    )

    assert result.payoff == SpreadPayoff(
        spread_width=10.0,
        target_payoff=8.0,
        max_payoff=10.0,
    )

    assert result.return_metrics.entry_cost == pytest.approx(240.0)
    assert result.return_metrics.ask_return == pytest.approx(560.0)
    assert result.return_metrics.ask_return_percent == pytest.approx(
        233.33333333333334
    )
    assert result.return_metrics.rankable is True


def test_prices_bear_put_candidate() -> None:
    result = price_spread(
        _bear_put_pair(),
        expiry="2028-06-16",
        target_price=102,
    )

    assert result.expiry == "2028-06-16"

    assert result.quote.spread_ask == pytest.approx(4.5)

    assert result.payoff == SpreadPayoff(
        spread_width=10.0,
        target_payoff=8.0,
        max_payoff=10.0,
    )

    assert result.return_metrics.entry_cost == pytest.approx(450.0)
    assert result.return_metrics.ask_return == pytest.approx(350.0)
    assert result.return_metrics.ask_return_percent == pytest.approx(
        77.77777777777779
    )
    assert result.return_metrics.rankable is True


def test_factory_uses_existing_pricing_engines() -> None:
    pair = _bull_call_pair()
    target_price = 108.0
    contract_multiplier = 50.0

    expected_quote = calculate_spread_quote(pair)
    expected_payoff = calculate_spread_payoff(
        pair,
        target_price,
    )
    expected_return = calculate_spread_return(
        expected_quote,
        expected_payoff,
        contract_multiplier=contract_multiplier,
    )

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=target_price,
        contract_multiplier=contract_multiplier,
    )

    assert result.quote == expected_quote
    assert result.payoff == expected_payoff
    assert result.return_metrics == expected_return


def test_custom_contract_multiplier_is_preserved() -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry="2028-01-21",
        target_price=108,
        contract_multiplier=50,
    )

    assert result.contract_multiplier == 50.0
    assert result.return_metrics.entry_cost == pytest.approx(120.0)
    assert result.return_metrics.ask_return == pytest.approx(280.0)
    assert result.return_metrics.ask_return_percent == pytest.approx(
        233.33333333333334
    )


def test_missing_executable_quote_returns_unrankable_candidate() -> None:
    pair = SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=100,
            bid=4.0,
            ask=None,
        ),
        short_leg=OptionContract(
            strike=110,
            bid=1.8,
            ask=2.0,
        ),
    )

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
    )

    assert result.quote.spread_ask is None
    assert result.return_metrics == SpreadReturn(
        entry_cost=None,
        ask_return=None,
        ask_return_percent=None,
        rankable=False,
    )


def test_negative_spread_ask_is_preserved_but_unrankable() -> None:
    pair = SpreadPair(
        strategy=SpreadStrategy.BULL_CALL,
        long_leg=OptionContract(
            strike=100,
            bid=0.5,
            ask=0.75,
        ),
        short_leg=OptionContract(
            strike=110,
            bid=1.0,
            ask=1.25,
        ),
    )

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
    )

    assert result.quote.spread_ask == pytest.approx(-0.25)
    assert result.return_metrics.entry_cost == pytest.approx(-25.0)
    assert result.return_metrics.ask_return == pytest.approx(825.0)
    assert result.return_metrics.ask_return_percent is None
    assert result.return_metrics.rankable is False


def test_expiry_is_normalized() -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry=" 2028-01-21 ",
        target_price=108,
    )

    assert result.expiry == "2028-01-21"


@pytest.mark.parametrize(
    "bad_expiry",
    [
        None,
        True,
        20280121,
        "",
        "2028-1-21",
        "21-01-2028",
        "2028-02-30",
        "not-a-date",
    ],
)
def test_rejects_invalid_expiry(
    bad_expiry: object,
) -> None:
    with pytest.raises(PricedSpreadError):
        price_spread(
            _bull_call_pair(),
            expiry=bad_expiry,  # type: ignore[arg-type]
            target_price=108,
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
        "108",
        None,
    ],
)
def test_rejects_invalid_target_price(
    bad_target_price: object,
) -> None:
    with pytest.raises(PricedSpreadError):
        price_spread(
            _bull_call_pair(),
            expiry="2028-01-21",
            target_price=bad_target_price,  # type: ignore[arg-type]
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
    with pytest.raises(PricedSpreadError):
        price_spread(
            _bull_call_pair(),
            expiry="2028-01-21",
            target_price=108,
            contract_multiplier=bad_multiplier,  # type: ignore[arg-type]
        )


def test_rejects_non_pair_value() -> None:
    with pytest.raises(PricedSpreadError):
        price_spread(
            "not a pair",  # type: ignore[arg-type]
            expiry="2028-01-21",
            target_price=108,
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("pair", "not a pair"),
        ("quote", "not a quote"),
        ("payoff", "not a payoff"),
        ("return_metrics", "not a return"),
    ],
)
def test_direct_aggregate_rejects_wrong_component_types(
    field_name: str,
    bad_value: object,
) -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(PricedSpreadError):
        replace(
            result,
            **{field_name: bad_value},
        )


def test_priced_spread_is_immutable() -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(AttributeError):
        result.target_price = 999.0  # type: ignore[misc]
        
        
def test_rejects_quote_from_different_candidate() -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry="2028-01-21",
        target_price=108,
    )
    other_result = price_spread(
        _bear_put_pair(),
        expiry="2028-01-21",
        target_price=102,
    )

    with pytest.raises(
        PricedSpreadError,
        match="quote is inconsistent",
    ):
        replace(
            result,
            quote=other_result.quote,
        )


def test_rejects_payoff_from_different_target_price() -> None:
    pair = _bull_call_pair()

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
    )
    other_result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=105,
    )

    with pytest.raises(
        PricedSpreadError,
        match="payoff is inconsistent",
    ):
        replace(
            result,
            payoff=other_result.payoff,
        )


def test_rejects_return_from_different_multiplier() -> None:
    pair = _bull_call_pair()

    result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
        contract_multiplier=100,
    )
    other_result = price_spread(
        pair,
        expiry="2028-01-21",
        target_price=108,
        contract_multiplier=50,
    )

    with pytest.raises(
        PricedSpreadError,
        match="return_metrics is inconsistent",
    ):
        replace(
            result,
            return_metrics=other_result.return_metrics,
        )


def test_rejects_valid_pair_with_foreign_components() -> None:
    result = price_spread(
        _bull_call_pair(),
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        PricedSpreadError,
        match="quote is inconsistent",
    ):
        replace(
            result,
            pair=_bear_put_pair(),
        )