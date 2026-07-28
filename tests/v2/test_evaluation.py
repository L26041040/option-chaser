from __future__ import annotations

from dataclasses import replace

import pytest

from option_chaser.v2.evaluation import (
    CandidateEvaluationError,
    CandidateEvaluationResult,
    evaluate_candidates,
)
from option_chaser.v2.models import (
    ContractEnumerationError,
    OptionContract,
    SpreadStrategy,
)
from option_chaser.v2.pricing.quote import QuoteCalculationError


def _complete_contracts() -> tuple[OptionContract, ...]:
    return (
        OptionContract(
            strike=90,
            bid=12.0,
            ask=12.5,
        ),
        OptionContract(
            strike=100,
            bid=6.0,
            ask=6.5,
        ),
        OptionContract(
            strike=110,
            bid=2.0,
            ask=2.5,
        ),
    )


def test_evaluates_every_bull_call_pair_in_structural_order() -> None:
    result = evaluate_candidates(
        reversed(_complete_contracts()),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    assert isinstance(result, CandidateEvaluationResult)
    assert result.strategy is SpreadStrategy.BULL_CALL
    assert result.expiry == "2028-01-21"
    assert result.target_price == 108.0
    assert result.contract_multiplier == 100.0
    assert result.source_contract_count == 3
    assert result.candidate_count == 3

    assert [
        (
            candidate.pair.long_strike,
            candidate.pair.short_strike,
        )
        for candidate in result.candidates
    ] == [
        (90.0, 100.0),
        (90.0, 110.0),
        (100.0, 110.0),
    ]


def test_evaluates_every_bear_put_pair_in_structural_order() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        "bear_put",
        expiry="2028-06-16",
        target_price=95,
    )

    assert result.strategy is SpreadStrategy.BEAR_PUT

    assert [
        (
            candidate.pair.long_strike,
            candidate.pair.short_strike,
        )
        for candidate in result.candidates
    ] == [
        (100.0, 90.0),
        (110.0, 90.0),
        (110.0, 100.0),
    ]


def test_preserves_rankable_and_unrankable_candidates() -> None:
    contracts = (
        OptionContract(
            strike=90,
            bid=12.0,
            ask=None,
        ),
        OptionContract(
            strike=100,
            bid=6.0,
            ask=6.5,
        ),
        OptionContract(
            strike=110,
            bid=2.0,
            ask=2.5,
        ),
    )

    result = evaluate_candidates(
        contracts,
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    assert result.candidate_count == 3
    assert result.rankable_count == 1
    assert result.unrankable_count == 2

    assert [
        (
            candidate.pair.long_strike,
            candidate.pair.short_strike,
        )
        for candidate in result.rankable_candidates
    ] == [
        (100.0, 110.0),
    ]

    assert [
        (
            candidate.pair.long_strike,
            candidate.pair.short_strike,
        )
        for candidate in result.unrankable_candidates
    ] == [
        (90.0, 100.0),
        (90.0, 110.0),
    ]

    assert len(result.candidates) == 3


@pytest.mark.parametrize(
    "contracts",
    [
        (),
        [],
    ],
)
def test_empty_chain_returns_empty_result(
    contracts: object,
) -> None:
    result = evaluate_candidates(
        contracts,  # type: ignore[arg-type]
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    assert result.source_contract_count == 0
    assert result.candidates == ()
    assert result.candidate_count == 0
    assert result.rankable_count == 0
    assert result.unrankable_count == 0


def test_one_contract_returns_empty_result() -> None:
    result = evaluate_candidates(
        [OptionContract(strike=100, bid=4.0, ask=4.2)],
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    assert result.source_contract_count == 1
    assert result.candidates == ()


def test_contract_generator_is_consumed_once() -> None:
    yielded_strikes: list[float] = []

    def contract_generator():
        for contract in _complete_contracts():
            yielded_strikes.append(contract.strike)
            yield contract

    result = evaluate_candidates(
        contract_generator(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    assert yielded_strikes == [90.0, 100.0, 110.0]
    assert result.source_contract_count == 3
    assert result.candidate_count == 3


def test_custom_multiplier_is_forwarded_to_every_candidate() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
        contract_multiplier=50,
    )

    assert result.contract_multiplier == 50.0
    assert all(
        candidate.contract_multiplier == 50.0
        for candidate in result.candidates
    )


@pytest.mark.parametrize(
    "bad_contracts",
    [
        None,
        123,
        "not contracts",
        b"not contracts",
    ],
)
def test_rejects_non_contract_iterables(
    bad_contracts: object,
) -> None:
    with pytest.raises(CandidateEvaluationError):
        evaluate_candidates(
            bad_contracts,  # type: ignore[arg-type]
            SpreadStrategy.BULL_CALL,
            expiry="2028-01-21",
            target_price=108,
        )


def test_wraps_non_contract_item_error() -> None:
    with pytest.raises(CandidateEvaluationError) as exc_info:
        evaluate_candidates(
            [
                OptionContract(strike=100),
                "not a contract",
            ],  # type: ignore[list-item]
            SpreadStrategy.BULL_CALL,
            expiry="2028-01-21",
            target_price=108,
        )

    assert isinstance(
        exc_info.value.__cause__,
        ContractEnumerationError,
    )


def test_wraps_duplicate_strike_error() -> None:
    with pytest.raises(CandidateEvaluationError) as exc_info:
        evaluate_candidates(
            [
                OptionContract(strike=100),
                OptionContract(strike=100),
            ],
            SpreadStrategy.BULL_CALL,
            expiry="2028-01-21",
            target_price=108,
        )

    assert isinstance(
        exc_info.value.__cause__,
        ContractEnumerationError,
    )


def test_wraps_malformed_quote_error() -> None:
    contracts = [
        OptionContract(
            strike=100,
            ask="bad",  # type: ignore[arg-type]
        ),
        OptionContract(
            strike=110,
            bid=1.0,
        ),
    ]

    with pytest.raises(CandidateEvaluationError) as exc_info:
        evaluate_candidates(
            contracts,
            SpreadStrategy.BULL_CALL,
            expiry="2028-01-21",
            target_price=108,
        )

    assert isinstance(
        exc_info.value.__cause__,
        QuoteCalculationError,
    )


@pytest.mark.parametrize(
    "bad_strategy",
    [
        "",
        "call",
        "bull-call",
        "unsupported",
        None,
        True,
        123,
    ],
)
def test_rejects_invalid_strategy(
    bad_strategy: object,
) -> None:
    with pytest.raises(CandidateEvaluationError):
        evaluate_candidates(
            (),
            bad_strategy,  # type: ignore[arg-type]
            expiry="2028-01-21",
            target_price=108,
        )


@pytest.mark.parametrize(
    "bad_expiry",
    [
        None,
        True,
        20280121,
        "",
        "2028-1-21",
        "2028-02-30",
        "not-a-date",
    ],
)
def test_rejects_invalid_expiry_even_for_empty_chain(
    bad_expiry: object,
) -> None:
    with pytest.raises(CandidateEvaluationError):
        evaluate_candidates(
            (),
            SpreadStrategy.BULL_CALL,
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
def test_rejects_invalid_target_price_even_for_empty_chain(
    bad_target_price: object,
) -> None:
    with pytest.raises(CandidateEvaluationError):
        evaluate_candidates(
            (),
            SpreadStrategy.BULL_CALL,
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
def test_rejects_invalid_multiplier_even_for_empty_chain(
    bad_multiplier: object,
) -> None:
    with pytest.raises(CandidateEvaluationError):
        evaluate_candidates(
            (),
            SpreadStrategy.BULL_CALL,
            expiry="2028-01-21",
            target_price=108,
            contract_multiplier=bad_multiplier,  # type: ignore[arg-type]
        )


def test_result_normalizes_candidate_iterable_to_tuple() -> None:
    original = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    reconstructed = CandidateEvaluationResult(
        strategy=original.strategy,
        expiry=original.expiry,
        target_price=original.target_price,
        contract_multiplier=original.contract_multiplier,
        source_contract_count=original.source_contract_count,
        candidates=list(original.candidates),  # type: ignore[arg-type]
    )

    assert isinstance(reconstructed.candidates, tuple)
    assert reconstructed == original


def test_result_rejects_missing_candidate() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        CandidateEvaluationError,
        match="candidate count is inconsistent",
    ):
        replace(
            result,
            candidates=result.candidates[:-1],
        )


def test_result_rejects_inconsistent_expiry() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        CandidateEvaluationError,
        match="inconsistent expiry",
    ):
        replace(
            result,
            expiry="2028-02-18",
        )


def test_result_rejects_inconsistent_strategy() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        CandidateEvaluationError,
        match="inconsistent strategy",
    ):
        replace(
            result,
            strategy=SpreadStrategy.BEAR_PUT,
        )


def test_result_rejects_inconsistent_target_price() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        CandidateEvaluationError,
        match="inconsistent target_price",
    ):
        replace(
            result,
            target_price=105,
        )


def test_result_rejects_inconsistent_multiplier() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        CandidateEvaluationError,
        match="inconsistent contract_multiplier",
    ):
        replace(
            result,
            contract_multiplier=50,
        )


def test_result_is_immutable() -> None:
    result = evaluate_candidates(
        _complete_contracts(),
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(AttributeError):
        result.target_price = 999.0  # type: ignore[misc]