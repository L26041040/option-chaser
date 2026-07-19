"""yfinance adapter: the only networked module. Cleaning rules per spec §2.3."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..models import SCHEMA_VERSION, ChainSnapshot, FetchError, OptionContract


def _clean_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _clean_count(value) -> int:
    f = _clean_float(value)
    return 0 if f is None else int(f)


def map_rows(
    symbol: str, spot: float, fetched_at: str, rows: list[dict]
) -> ChainSnapshot:
    contracts = tuple(
        OptionContract(
            contract_symbol=str(r["contractSymbol"]),
            option_type=str(r.get("option_type", "call")),
            strike=float(r["strike"]),
            expiry=str(r["expiry"]),
            bid=_clean_float(r.get("bid")),
            ask=_clean_float(r.get("ask")),
            last=_clean_float(r.get("lastPrice")),
            volume=_clean_count(r.get("volume")),
            open_interest=_clean_count(r.get("openInterest")),
            implied_volatility=_clean_float(r.get("impliedVolatility")),
        )
        for r in rows
    )
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol=symbol, fetched_at=fetched_at,
        spot=spot, source="yfinance", contracts=contracts,
    )


def fetch_chain(symbol: str) -> ChainSnapshot:
    try:
        import yfinance as yf  # lazy: tests never import the network stack

        t = yf.Ticker(symbol)
        spot = float(t.fast_info["last_price"])
        rows: list[dict] = []
        for expiry in t.options:
            calls = t.option_chain(expiry).calls
            for r in calls.to_dict("records"):
                r["expiry"] = expiry
                rows.append(r)
    except Exception as e:  # noqa: BLE001 — any yfinance failure is a fetch failure
        raise FetchError(f"yfinance 抓取失敗（{symbol}）: {e}") from e
    if not rows or spot <= 0 or math.isnan(spot):
        raise FetchError(f"yfinance 回傳資料不足（{symbol}）：無現價或無合約")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return map_rows(symbol, spot, fetched_at, rows)
