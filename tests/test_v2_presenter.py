from __future__ import annotations

import copy
import json

import pytest

from option_chaser.v2 import evaluate_api_payload
from webapp.v2_presenter import (
    DEFAULT_CHAIN_ROWS,
    V2PresenterError,
    build_evaluation_payload,
    candidate_display_rows,
)


def test_builds_api_payload_from_default_rows() -> None:
    payload = build_evaluation_payload(
        strategy="bull_call",
        expiry="2028-01-21",
        target_price=115,
        contract_multiplier=100,
        chain_rows=DEFAULT_CHAIN_ROWS,
    )

    assert payload["schema_version"] == 1
    assert payload["strategy"] == "bull_call"
    assert payload["expiry"] == "2028-01-21"
    assert payload["target_price"] == 115.0
    assert payload["contract_multiplier"] == 100.0
    assert len(payload["contracts"]) == 6


def test_default_rows_produce_all_fifteen_candidates() -> None:
    payload = build_evaluation_payload(
        strategy="bull_call",
        expiry="2028-01-21",
        target_price=115,
        contract_multiplier=100,
        chain_rows=DEFAULT_CHAIN_ROWS,
    )

    response = evaluate_api_payload(payload)

    assert response["source_contract_count"] == 6
    assert response["candidate_count"] == 15
    assert len(response["candidates"]) == 15


def test_presenter_does_not_mutate_editor_rows() -> None:
    rows = [dict(row) for row in DEFAULT_CHAIN_ROWS]
    original = copy.deepcopy(rows)

    build_evaluation_payload(
        strategy="bull_call",
        expiry="2028-01-21",
        target_price=115,
        contract_multiplier=100,
        chain_rows=rows,
    )

    assert rows == original


def test_empty_trailing_editor_row_is_ignored() -> None:
    rows = [
        *DEFAULT_CHAIN_ROWS,
        {
            "strike": None,
            "bid": None,
            "ask": None,
            "implied_volatility": None,
            "open_interest": None,
            "volume": None,
        },
    ]

    payload = build_evaluation_payload(
        strategy="bull_call",
        expiry="2028-01-21",
        target_price=115,
        contract_multiplier=100,
        chain_rows=rows,
    )

    assert len(payload["contracts"]) == 6


def test_partial_row_without_strike_is_rejected() -> None:
    rows = [
        *DEFAULT_CHAIN_ROWS,
        {
            "strike": None,
            "bid": 1.0,
        },
    ]

    with pytest.raises(
        V2PresenterError,
        match="缺少履約價",
    ):
        build_evaluation_payload(
            strategy="bull_call",
            expiry="2028-01-21",
            target_price=115,
            contract_multiplier=100,
            chain_rows=rows,
        )


def test_duplicate_strikes_are_rejected() -> None:
    rows = [
        dict(DEFAULT_CHAIN_ROWS[0]),
        dict(DEFAULT_CHAIN_ROWS[0]),
    ]

    with pytest.raises(
        V2PresenterError,
        match="履約價不可重複",
    ):
        build_evaluation_payload(
            strategy="bull_call",
            expiry="2028-01-21",
            target_price=115,
            contract_multiplier=100,
            chain_rows=rows,
        )


def test_requires_at_least_two_contracts() -> None:
    with pytest.raises(
        V2PresenterError,
        match="至少需要兩張",
    ):
        build_evaluation_payload(
            strategy="bull_call",
            expiry="2028-01-21",
            target_price=115,
            contract_multiplier=100,
            chain_rows=[DEFAULT_CHAIN_ROWS[0]],
        )


def test_flattens_candidates_for_display() -> None:
    payload = build_evaluation_payload(
        strategy="bull_call",
        expiry="2028-01-21",
        target_price=115,
        contract_multiplier=100,
        chain_rows=DEFAULT_CHAIN_ROWS,
    )
    response = evaluate_api_payload(payload)

    rows = candidate_display_rows(response)

    assert len(rows) == 15
    assert rows[0]["Long Strike"] == 80.0
    assert rows[0]["Short Strike"] == 90.0
    assert rows[-1]["Long Strike"] == 120.0
    assert rows[-1]["Short Strike"] == 130.0
    assert rows[0]["Candidate Key"] == (
        "bull_call|2028-01-21|80|90"
    )


def test_display_rows_remain_json_serializable() -> None:
    payload = build_evaluation_payload(
        strategy="bear_put",
        expiry="2028-01-21",
        target_price=95,
        contract_multiplier=100,
        chain_rows=DEFAULT_CHAIN_ROWS,
    )
    response = evaluate_api_payload(payload)

    rows = candidate_display_rows(response)

    json.dumps(rows, ensure_ascii=False, allow_nan=False)