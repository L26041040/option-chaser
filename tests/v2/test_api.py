from __future__ import annotations

import ast
import copy
import json
from math import isfinite
from pathlib import Path

import pytest

from option_chaser.v2.api import (
    API_SCHEMA_VERSION,
    ApiContractError,
    evaluate_api_payload,
    serialize_evaluation_result,
)
from option_chaser.v2.evaluation import evaluate_candidates
from option_chaser.v2.models import (
    OptionContract,
    SpreadStrategy,
)


def _request_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "strategy": "bull_call",
        "expiry": "2028-01-21",
        "target_price": 108,
        "contracts": [
            {
                "strike": 90,
                "bid": 12,
                "ask": None,
                "implied_volatility": 0.30,
                "open_interest": 1200,
                "volume": 300,
            },
            {
                "strike": 100,
                "bid": 6,
                "ask": 6.5,
                "implied_volatility": 0.25,
                "open_interest": 900,
                "volume": 200,
            },
            {
                "strike": 110,
                "bid": 2,
                "ask": 2.5,
                "implied_volatility": 0.20,
                "open_interest": 700,
                "volume": 100,
            },
        ],
    }


def _assert_json_native(value: object) -> None:
    if value is None or isinstance(
        value,
        (str, int, bool),
    ):
        return

    if isinstance(value, float):
        assert isfinite(value)
        return

    if isinstance(value, list):
        for item in value:
            _assert_json_native(item)
        return

    if isinstance(value, dict):
        assert all(
            isinstance(key, str)
            for key in value
        )
        for item in value.values():
            _assert_json_native(item)
        return

    raise AssertionError(
        f"non-JSON-native value: {type(value).__name__}"
    )


def test_evaluates_request_and_returns_json_native_response() -> None:
    response = evaluate_api_payload(
        _request_payload()
    )

    assert response["schema_version"] == API_SCHEMA_VERSION
    assert response["strategy"] == "bull_call"
    assert response["expiry"] == "2028-01-21"
    assert response["target_price"] == 108.0
    assert response["contract_multiplier"] == 100.0
    assert response["source_contract_count"] == 3
    assert response["candidate_count"] == 3
    assert response["rankable_count"] == 1
    assert response["unrankable_count"] == 2

    _assert_json_native(response)

    encoded = json.dumps(
        response,
        ensure_ascii=False,
        allow_nan=False,
    )

    assert json.loads(encoded) == response


def test_response_preserves_structural_candidate_order() -> None:
    response = evaluate_api_payload(
        _request_payload()
    )

    candidates = response["candidates"]

    assert isinstance(candidates, list)

    assert [
        candidate["candidate_key"]
        for candidate in candidates
    ] == [
        "bull_call|2028-01-21|90|100",
        "bull_call|2028-01-21|90|110",
        "bull_call|2028-01-21|100|110",
    ]


def test_response_preserves_missing_quote_as_null() -> None:
    response = evaluate_api_payload(
        _request_payload()
    )

    candidates = response["candidates"]
    first_candidate = candidates[0]

    assert (
        first_candidate["pair"]["long_leg"]["ask"]
        is None
    )
    assert (
        first_candidate["quote"]["spread_ask"]
        is None
    )
    assert (
        first_candidate["return_metrics"]["entry_cost"]
        is None
    )
    assert (
        first_candidate["return_metrics"]["rankable"]
        is False
    )


def test_response_contract_has_exact_key_sets() -> None:
    response = evaluate_api_payload(
        _request_payload()
    )

    assert set(response) == {
        "schema_version",
        "strategy",
        "expiry",
        "target_price",
        "contract_multiplier",
        "source_contract_count",
        "candidate_count",
        "rankable_count",
        "unrankable_count",
        "candidates",
    }

    candidate = response["candidates"][0]

    assert set(candidate) == {
        "candidate_key",
        "pair",
        "quote",
        "payoff",
        "return_metrics",
    }

    assert set(candidate["pair"]) == {
        "strategy",
        "long_leg",
        "short_leg",
    }

    assert set(candidate["pair"]["long_leg"]) == {
        "strike",
        "bid",
        "ask",
        "implied_volatility",
        "open_interest",
        "volume",
    }

    assert set(candidate["quote"]) == {
        "long_mid",
        "short_mid",
        "spread_bid",
        "spread_mid",
        "spread_ask",
    }

    assert set(candidate["payoff"]) == {
        "spread_width",
        "target_payoff",
        "max_payoff",
    }

    assert set(candidate["return_metrics"]) == {
        "entry_cost",
        "ask_return",
        "ask_return_percent",
        "rankable",
    }


def test_request_is_not_mutated() -> None:
    payload = _request_payload()
    original = copy.deepcopy(payload)

    evaluate_api_payload(payload)

    assert payload == original


def test_optional_numbers_are_normalized_to_float() -> None:
    response = evaluate_api_payload(
        _request_payload()
    )

    long_leg = response["candidates"][0]["pair"]["long_leg"]

    assert isinstance(long_leg["strike"], float)
    assert isinstance(long_leg["bid"], float)
    assert isinstance(long_leg["implied_volatility"], float)
    assert isinstance(long_leg["open_interest"], float)
    assert isinstance(long_leg["volume"], float)


def test_custom_contract_multiplier_is_supported() -> None:
    payload = _request_payload()
    payload["contract_multiplier"] = 50

    response = evaluate_api_payload(payload)

    assert response["contract_multiplier"] == 50.0

    rankable = [
        candidate
        for candidate in response["candidates"]
        if candidate["return_metrics"]["rankable"]
    ]

    assert len(rankable) == 1
    assert (
        rankable[0]["return_metrics"]["entry_cost"]
        == pytest.approx(225.0)
    )


def test_preserves_all_pairs_without_future_ranking_limit() -> None:
    payload = {
        "schema_version": 1,
        "strategy": "bull_call",
        "expiry": "2028-01-21",
        "target_price": 115,
        "contracts": [
            {"strike": 80, "bid": 36, "ask": 37},
            {"strike": 90, "bid": 27, "ask": 28},
            {"strike": 100, "bid": 19, "ask": 20},
            {"strike": 110, "bid": 12, "ask": 13},
            {"strike": 120, "bid": 7, "ask": 8},
            {"strike": 130, "bid": 3, "ask": 4},
        ],
    }

    response = evaluate_api_payload(payload)

    assert response["source_contract_count"] == 6
    assert response["candidate_count"] == 15
    assert len(response["candidates"]) == 15


@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        [],
        "payload",
        123,
    ],
)
def test_rejects_non_object_payload(
    bad_payload: object,
) -> None:
    with pytest.raises(ApiContractError):
        evaluate_api_payload(
            bad_payload,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "schema_version",
        "strategy",
        "expiry",
        "target_price",
        "contracts",
    ],
)
def test_rejects_missing_required_request_field(
    missing_field: str,
) -> None:
    payload = _request_payload()
    del payload[missing_field]

    with pytest.raises(
        ApiContractError,
        match="missing required fields",
    ):
        evaluate_api_payload(payload)


def test_rejects_unknown_request_field() -> None:
    payload = _request_payload()
    payload["unexpected"] = True

    with pytest.raises(
        ApiContractError,
        match="unknown fields",
    ):
        evaluate_api_payload(payload)


@pytest.mark.parametrize(
    "bad_schema_version",
    [
        None,
        True,
        False,
        0,
        2,
        "1",
        1.0,
    ],
)
def test_rejects_unsupported_schema_version(
    bad_schema_version: object,
) -> None:
    payload = _request_payload()
    payload["schema_version"] = bad_schema_version

    with pytest.raises(
        ApiContractError,
        match="schema_version must be 1",
    ):
        evaluate_api_payload(payload)


@pytest.mark.parametrize(
    "bad_contracts",
    [
        None,
        (),
        {},
        "contracts",
        123,
    ],
)
def test_rejects_non_array_contracts(
    bad_contracts: object,
) -> None:
    payload = _request_payload()
    payload["contracts"] = bad_contracts

    with pytest.raises(
        ApiContractError,
        match="contracts must be a JSON array",
    ):
        evaluate_api_payload(payload)


def test_rejects_non_object_contract_item() -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {"strike": 100},
        "not a contract",
    ]

    with pytest.raises(
        ApiContractError,
        match=r"contracts\[1\] must be a JSON object",
    ):
        evaluate_api_payload(payload)


def test_rejects_contract_without_strike() -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {
            "bid": 1.0,
            "ask": 1.2,
        }
    ]

    with pytest.raises(
        ApiContractError,
        match="missing required fields",
    ):
        evaluate_api_payload(payload)


def test_rejects_unknown_contract_field() -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {
            "strike": 100,
            "expiry": "2028-01-21",
        }
    ]

    with pytest.raises(
        ApiContractError,
        match="unknown fields",
    ):
        evaluate_api_payload(payload)


@pytest.mark.parametrize(
    "bad_strike",
    [
        None,
        True,
        False,
        0,
        -1,
        float("nan"),
        float("inf"),
        "100",
    ],
)
def test_rejects_invalid_contract_strike(
    bad_strike: object,
) -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {
            "strike": bad_strike,
        }
    ]

    with pytest.raises(
        ApiContractError,
        match="strike must be a positive finite number",
    ):
        evaluate_api_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("bid", -1),
        ("ask", float("nan")),
        ("implied_volatility", float("inf")),
        ("open_interest", True),
        ("volume", "100"),
    ],
)
def test_rejects_invalid_optional_contract_number(
    field_name: str,
    bad_value: object,
) -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {
            "strike": 100,
            field_name: bad_value,
        }
    ]

    with pytest.raises(ApiContractError):
        evaluate_api_payload(payload)


def test_wraps_duplicate_strike_error() -> None:
    payload = _request_payload()
    payload["contracts"] = [
        {"strike": 100},
        {"strike": 100},
    ]

    with pytest.raises(
        ApiContractError,
        match="duplicate strike",
    ):
        evaluate_api_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("target_price", 0),
        ("target_price", float("nan")),
        ("target_price", True),
        ("contract_multiplier", -1),
        ("contract_multiplier", "100"),
    ],
)
def test_rejects_invalid_positive_request_number(
    field_name: str,
    bad_value: object,
) -> None:
    payload = _request_payload()
    payload[field_name] = bad_value

    with pytest.raises(ApiContractError):
        evaluate_api_payload(payload)


def test_serializer_rejects_wrong_result_type() -> None:
    with pytest.raises(
        ApiContractError,
        match="CandidateEvaluationResult",
    ):
        serialize_evaluation_result(
            "not a result",  # type: ignore[arg-type]
        )


def test_serializer_rejects_invalid_liquidity_data() -> None:
    result = evaluate_candidates(
        [
            OptionContract(
                strike=100,
                bid=4.0,
                ask=4.2,
                volume="bad",  # type: ignore[arg-type]
            ),
            OptionContract(
                strike=110,
                bid=1.0,
                ask=1.2,
            ),
        ],
        SpreadStrategy.BULL_CALL,
        expiry="2028-01-21",
        target_price=108,
    )

    with pytest.raises(
        ApiContractError,
        match="contract.volume",
    ):
        serialize_evaluation_result(result)


def test_api_module_does_not_cross_architecture_boundaries() -> None:
    source_path = Path("option_chaser/v2/api.py")
    tree = ast.parse(
        source_path.read_text(encoding="utf-8")
    )

    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name
                for alias in node.names
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
        ):
            imported_modules.add(node.module)

    forbidden_fragments = (
        "option_chaser.service",
        "option_chaser.store",
        "option_chaser.ranking",
        "option_chaser.filters",
        "option_chaser.report",
        "webapp",
        "streamlit",
        "yfinance",
    )

    violations = sorted(
        module
        for module in imported_modules
        if any(
            fragment in module
            for fragment in forbidden_fragments
        )
    )

    assert not violations
