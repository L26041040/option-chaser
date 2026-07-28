"""Presentation helpers for the Option Chaser MVP V2 Streamlit UI.

This module converts editable-table rows into the V2 JSON API request and
converts API responses into flat display rows.

It contains no Streamlit calls and no financial calculations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from numbers import Real


class V2PresenterError(ValueError):
    """Raised when editable UI data cannot be converted safely."""


DEFAULT_CHAIN_ROWS: tuple[dict[str, object], ...] = (
    {
        "strike": 80.0,
        "bid": 36.0,
        "ask": 37.0,
        "implied_volatility": 0.30,
        "open_interest": 1500.0,
        "volume": 300.0,
    },
    {
        "strike": 90.0,
        "bid": 27.0,
        "ask": 28.0,
        "implied_volatility": 0.28,
        "open_interest": 1400.0,
        "volume": 280.0,
    },
    {
        "strike": 100.0,
        "bid": 19.0,
        "ask": 20.0,
        "implied_volatility": 0.25,
        "open_interest": 1200.0,
        "volume": 250.0,
    },
    {
        "strike": 110.0,
        "bid": 12.0,
        "ask": 13.0,
        "implied_volatility": 0.23,
        "open_interest": 1000.0,
        "volume": 220.0,
    },
    {
        "strike": 120.0,
        "bid": 7.0,
        "ask": 8.0,
        "implied_volatility": 0.21,
        "open_interest": 800.0,
        "volume": 180.0,
    },
    {
        "strike": 130.0,
        "bid": 3.0,
        "ask": 4.0,
        "implied_volatility": 0.20,
        "open_interest": 600.0,
        "volume": 120.0,
    },
)

_CHAIN_FIELDS = (
    "strike",
    "bid",
    "ask",
    "implied_volatility",
    "open_interest",
    "volume",
)


def build_evaluation_payload(
    *,
    strategy: str,
    expiry: str,
    target_price: object,
    contract_multiplier: object,
    chain_rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Convert editable option-chain rows into API schema version 1."""

    normalized_strategy = _require_nonempty_string(
        strategy,
        field_name="strategy",
    )
    normalized_expiry = _require_nonempty_string(
        expiry,
        field_name="expiry",
    )
    normalized_target_price = _positive_number(
        target_price,
        field_name="target_price",
    )
    normalized_multiplier = _positive_number(
        contract_multiplier,
        field_name="contract_multiplier",
    )

    try:
        materialized_rows = tuple(chain_rows)
    except TypeError as exc:
        raise V2PresenterError(
            "chain_rows must be iterable"
        ) from exc

    contracts: list[dict[str, object]] = []

    for index, row in enumerate(materialized_rows):
        if not isinstance(row, Mapping):
            raise V2PresenterError(
                f"chain row {index + 1} must be an object"
            )

        strike = _optional_number(row.get("strike"))

        # Streamlit data_editor may preserve a visually empty row.
        if strike is None:
            if any(
                _optional_number(row.get(field)) is not None
                for field in _CHAIN_FIELDS[1:]
            ):
                raise V2PresenterError(
                    f"第 {index + 1} 列缺少履約價"
                )
            continue

        if strike <= 0:
            raise V2PresenterError(
                f"第 {index + 1} 列履約價必須大於 0"
            )

        contract: dict[str, object] = {
            "strike": strike,
        }

        for field in _CHAIN_FIELDS[1:]:
            value = _optional_number(row.get(field))

            if value is not None and value < 0:
                raise V2PresenterError(
                    f"第 {index + 1} 列的 {field} 不得小於 0"
                )

            contract[field] = value

        contracts.append(contract)

    if len(contracts) < 2:
        raise V2PresenterError(
            "至少需要兩張不同履約價的選擇權合約"
        )

    strikes = [contract["strike"] for contract in contracts]

    if len(strikes) != len(set(strikes)):
        raise V2PresenterError(
            "履約價不可重複"
        )

    return {
        "schema_version": 1,
        "strategy": normalized_strategy,
        "expiry": normalized_expiry,
        "target_price": normalized_target_price,
        "contract_multiplier": normalized_multiplier,
        "contracts": contracts,
    }


def candidate_display_rows(
    response: Mapping[str, object],
) -> list[dict[str, object]]:
    """Flatten API candidates into rows suitable for a Streamlit dataframe."""

    raw_candidates = response.get("candidates")

    if not isinstance(raw_candidates, list):
        raise V2PresenterError(
            "response.candidates must be a list"
        )

    rows: list[dict[str, object]] = []

    for index, candidate in enumerate(raw_candidates):
        if not isinstance(candidate, Mapping):
            raise V2PresenterError(
                f"candidate {index + 1} must be an object"
            )

        pair = _mapping(candidate.get("pair"), field_name="pair")
        long_leg = _mapping(
            pair.get("long_leg"),
            field_name="pair.long_leg",
        )
        short_leg = _mapping(
            pair.get("short_leg"),
            field_name="pair.short_leg",
        )
        quote = _mapping(
            candidate.get("quote"),
            field_name="quote",
        )
        payoff = _mapping(
            candidate.get("payoff"),
            field_name="payoff",
        )
        return_metrics = _mapping(
            candidate.get("return_metrics"),
            field_name="return_metrics",
        )

        rankable = return_metrics.get("rankable")

        if not isinstance(rankable, bool):
            raise V2PresenterError(
                "return_metrics.rankable must be a boolean"
            )

        rows.append(
            {
                "狀態": "可排名" if rankable else "資料不足",
                "Long Strike": long_leg.get("strike"),
                "Short Strike": short_leg.get("strike"),
                "進場成本": return_metrics.get("entry_cost"),
                "目標損益": return_metrics.get("ask_return"),
                "目標報酬率 (%)": return_metrics.get(
                    "ask_return_percent"
                ),
                "Spread Ask": quote.get("spread_ask"),
                "Spread Mid": quote.get("spread_mid"),
                "目標價值": payoff.get("target_payoff"),
                "最大價值": payoff.get("max_payoff"),
                "Candidate Key": candidate.get("candidate_key"),
            }
        )

    return rows


def _mapping(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise V2PresenterError(
            f"{field_name} must be an object"
        )

    return value


def _require_nonempty_string(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V2PresenterError(
            f"{field_name} must be a non-empty string"
        )

    return value.strip()


def _positive_number(
    value: object,
    *,
    field_name: str,
) -> float:
    normalized = _optional_number(value)

    if normalized is None or normalized <= 0:
        raise V2PresenterError(
            f"{field_name} must be a positive finite number"
        )

    return normalized


def _optional_number(
    value: object,
) -> float | None:
    if value is None:
        return None

    # Pandas / Streamlit may represent an empty numeric cell as NaN.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise V2PresenterError(
            "numeric table values must be finite numbers or empty"
        )

    normalized = float(value)

    if not isfinite(normalized):
        return None

    return normalized