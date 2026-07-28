"""Framework-neutral JSON contract for Option Chaser MVP V2.

This module accepts JSON-compatible request mappings, delegates evaluation to
the V2 application service, and returns JSON-compatible response dictionaries.

It does not implement HTTP routing, market-data fetching, ranking, filtering,
recommendations, persistence, or user-interface rendering.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from numbers import Real

from option_chaser.v2.evaluation import (
    CandidateEvaluationError,
    CandidateEvaluationResult,
    evaluate_candidates,
)
from option_chaser.v2.models import OptionContract
from option_chaser.v2.priced import PricedSpread


API_SCHEMA_VERSION = 1

_REQUEST_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "strategy",
        "expiry",
        "target_price",
        "contracts",
    }
)

_REQUEST_OPTIONAL_KEYS = frozenset(
    {
        "contract_multiplier",
    }
)

_CONTRACT_REQUIRED_KEYS = frozenset(
    {
        "strike",
    }
)

_CONTRACT_OPTIONAL_KEYS = frozenset(
    {
        "bid",
        "ask",
        "implied_volatility",
        "open_interest",
        "volume",
    }
)


class ApiContractError(ValueError):
    """Raised when an API request or response violates schema version 1."""


def evaluate_api_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate and evaluate one JSON-compatible candidate request.

    The request schema is::

        {
            "schema_version": 1,
            "strategy": "bull_call" | "bear_put",
            "expiry": "YYYY-MM-DD",
            "target_price": positive number,
            "contract_multiplier": positive number,  # optional, default 100
            "contracts": [
                {
                    "strike": positive number,
                    "bid": non-negative number | null,
                    "ask": non-negative number | null,
                    "implied_volatility": non-negative number | null,
                    "open_interest": non-negative number | null,
                    "volume": non-negative number | null
                }
            ]
        }
    """

    if not isinstance(payload, Mapping):
        raise ApiContractError(
            "payload must be a JSON object"
        )

    _validate_object_keys(
        payload,
        required_keys=_REQUEST_REQUIRED_KEYS,
        optional_keys=_REQUEST_OPTIONAL_KEYS,
        field_name="payload",
    )

    schema_version = payload["schema_version"]

    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != API_SCHEMA_VERSION
    ):
        raise ApiContractError(
            f"schema_version must be {API_SCHEMA_VERSION}"
        )

    strategy = _require_string(
        payload["strategy"],
        field_name="strategy",
    )
    expiry = _require_string(
        payload["expiry"],
        field_name="expiry",
    )
    target_price = _normalize_positive_finite_number(
        payload["target_price"],
        field_name="target_price",
    )
    contract_multiplier = _normalize_positive_finite_number(
        payload.get("contract_multiplier", 100),
        field_name="contract_multiplier",
    )
    contracts = _parse_contracts(payload["contracts"])

    try:
        result = evaluate_candidates(
            contracts,
            strategy,
            expiry=expiry,
            target_price=target_price,
            contract_multiplier=contract_multiplier,
        )
    except CandidateEvaluationError as exc:
        raise ApiContractError(
            f"invalid evaluation request: {exc}"
        ) from exc

    return serialize_evaluation_result(result)


def serialize_evaluation_result(
    result: CandidateEvaluationResult,
) -> dict[str, object]:
    """Serialize one evaluation result into JSON-native data only."""

    if not isinstance(result, CandidateEvaluationResult):
        raise ApiContractError(
            "result must be a CandidateEvaluationResult"
        )

    return {
        "schema_version": API_SCHEMA_VERSION,
        "strategy": result.strategy.value,
        "expiry": result.expiry,
        "target_price": result.target_price,
        "contract_multiplier": result.contract_multiplier,
        "source_contract_count": result.source_contract_count,
        "candidate_count": result.candidate_count,
        "rankable_count": result.rankable_count,
        "unrankable_count": result.unrankable_count,
        "candidates": [
            _serialize_candidate(candidate)
            for candidate in result.candidates
        ],
    }


def _parse_contracts(
    value: object,
) -> tuple[OptionContract, ...]:
    """Parse one JSON array of option-contract objects."""

    if not isinstance(value, list):
        raise ApiContractError(
            "contracts must be a JSON array"
        )

    contracts: list[OptionContract] = []

    for index, raw_contract in enumerate(value):
        field_name = f"contracts[{index}]"

        if not isinstance(raw_contract, Mapping):
            raise ApiContractError(
                f"{field_name} must be a JSON object"
            )

        _validate_object_keys(
            raw_contract,
            required_keys=_CONTRACT_REQUIRED_KEYS,
            optional_keys=_CONTRACT_OPTIONAL_KEYS,
            field_name=field_name,
        )

        strike = _normalize_positive_finite_number(
            raw_contract["strike"],
            field_name=f"{field_name}.strike",
        )

        contracts.append(
            OptionContract(
                strike=strike,
                bid=_normalize_optional_nonnegative_number(
                    raw_contract.get("bid"),
                    field_name=f"{field_name}.bid",
                ),
                ask=_normalize_optional_nonnegative_number(
                    raw_contract.get("ask"),
                    field_name=f"{field_name}.ask",
                ),
                implied_volatility=(
                    _normalize_optional_nonnegative_number(
                        raw_contract.get("implied_volatility"),
                        field_name=(
                            f"{field_name}.implied_volatility"
                        ),
                    )
                ),
                open_interest=_normalize_optional_nonnegative_number(
                    raw_contract.get("open_interest"),
                    field_name=f"{field_name}.open_interest",
                ),
                volume=_normalize_optional_nonnegative_number(
                    raw_contract.get("volume"),
                    field_name=f"{field_name}.volume",
                ),
            )
        )

    return tuple(contracts)


def _serialize_candidate(
    candidate: PricedSpread,
) -> dict[str, object]:
    """Serialize one priced-spread aggregate."""

    return {
        "candidate_key": _candidate_key(candidate),
        "pair": {
            "strategy": candidate.pair.strategy.value,
            "long_leg": _serialize_contract(
                candidate.pair.long_leg
            ),
            "short_leg": _serialize_contract(
                candidate.pair.short_leg
            ),
        },
        "quote": {
            "long_mid": candidate.quote.long_mid,
            "short_mid": candidate.quote.short_mid,
            "spread_bid": candidate.quote.spread_bid,
            "spread_mid": candidate.quote.spread_mid,
            "spread_ask": candidate.quote.spread_ask,
        },
        "payoff": {
            "spread_width": candidate.payoff.spread_width,
            "target_payoff": candidate.payoff.target_payoff,
            "max_payoff": candidate.payoff.max_payoff,
        },
        "return_metrics": {
            "entry_cost": candidate.return_metrics.entry_cost,
            "ask_return": candidate.return_metrics.ask_return,
            "ask_return_percent": (
                candidate.return_metrics.ask_return_percent
            ),
            "rankable": candidate.return_metrics.rankable,
        },
    }


def _serialize_contract(
    contract: OptionContract,
) -> dict[str, object]:
    """Serialize one option contract with normalized numeric fields."""

    return {
        "strike": float(contract.strike),
        "bid": _serialize_optional_nonnegative_number(
            contract.bid,
            field_name="contract.bid",
        ),
        "ask": _serialize_optional_nonnegative_number(
            contract.ask,
            field_name="contract.ask",
        ),
        "implied_volatility": (
            _serialize_optional_nonnegative_number(
                contract.implied_volatility,
                field_name="contract.implied_volatility",
            )
        ),
        "open_interest": _serialize_optional_nonnegative_number(
            contract.open_interest,
            field_name="contract.open_interest",
        ),
        "volume": _serialize_optional_nonnegative_number(
            contract.volume,
            field_name="contract.volume",
        ),
    }


def _candidate_key(
    candidate: PricedSpread,
) -> str:
    """Return one deterministic API candidate identifier."""

    return "|".join(
        (
            candidate.pair.strategy.value,
            candidate.expiry,
            _number_token(candidate.pair.long_strike),
            _number_token(candidate.pair.short_strike),
        )
    )


def _number_token(value: float) -> str:
    """Format one deterministic finite numeric identity token."""

    return format(float(value), ".15g")


def _validate_object_keys(
    value: Mapping[object, object],
    *,
    required_keys: frozenset[str],
    optional_keys: frozenset[str],
    field_name: str,
) -> None:
    """Reject missing, non-string, and unknown object keys."""

    raw_keys = tuple(value.keys())

    if not all(isinstance(key, str) for key in raw_keys):
        raise ApiContractError(
            f"{field_name} keys must be strings"
        )

    keys = set(raw_keys)
    missing_keys = sorted(required_keys - keys)
    unknown_keys = sorted(
        keys - required_keys - optional_keys
    )

    if missing_keys:
        raise ApiContractError(
            f"{field_name} is missing required fields: "
            + ", ".join(missing_keys)
        )

    if unknown_keys:
        raise ApiContractError(
            f"{field_name} contains unknown fields: "
            + ", ".join(unknown_keys)
        )


def _require_string(
    value: object,
    *,
    field_name: str,
) -> str:
    """Require one JSON string."""

    if not isinstance(value, str):
        raise ApiContractError(
            f"{field_name} must be a string"
        )

    return value


def _normalize_positive_finite_number(
    value: object,
    *,
    field_name: str,
) -> float:
    """Normalize one positive finite JSON number."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ApiContractError(
            f"{field_name} must be a positive finite number"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value <= 0:
        raise ApiContractError(
            f"{field_name} must be a positive finite number"
        )

    return normalized_value


def _normalize_optional_nonnegative_number(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize one nullable finite, non-negative JSON number."""

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ApiContractError(
            f"{field_name} must be a finite non-negative number or null"
        )

    normalized_value = float(value)

    if not isfinite(normalized_value) or normalized_value < 0:
        raise ApiContractError(
            f"{field_name} must be a finite non-negative number or null"
        )

    return normalized_value


def _serialize_optional_nonnegative_number(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Validate and serialize one nullable numeric contract field."""

    return _normalize_optional_nonnegative_number(
        value,
        field_name=field_name,
    )
