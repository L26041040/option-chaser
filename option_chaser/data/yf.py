"""yfinance adapter: the only networked module. Cleaning rules per spec §2.3."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..models import (SCHEMA_VERSION, ChainSnapshot, FetchError, OptionContract,
                      describe_fetch_exception)


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
            option_type=str(r["option_type"]),
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


def available() -> bool:
    """yfinance 套件有沒有裝。它是選用依賴（pyproject 的 `yf` extra），
    production（Vercel）沒有裝——沒裝時 `fetch_chain()` 不會送出任何
    網路請求，呼叫端可以據此跳過這個 attempt，不必為一個不會發生的
    上游請求扣額度。"""
    import importlib.util

    return importlib.util.find_spec("yfinance") is not None


def fetch_chain(symbol: str) -> ChainSnapshot:
    try:
        import yfinance as yf  # lazy: tests never import the network stack

        t = yf.Ticker(symbol)
        spot = float(t.fast_info["last_price"])
        rows: list[dict] = []
        for expiry in t.options:
            chain = t.option_chain(expiry)
            for side, frame in (("call", chain.calls), ("put", chain.puts)):
                for r in frame.to_dict("records"):
                    r["expiry"] = expiry
                    r["option_type"] = side
                    rows.append(r)
    except Exception as e:  # noqa: BLE001 — any yfinance failure is a fetch failure
        # #345 B-3：訊息會直達 client（見 `describe_fetch_exception`）。
        raise FetchError(f"yfinance 抓取失敗（{symbol}）: {describe_fetch_exception(e)}") from e
    if not rows or spot <= 0 or math.isnan(spot):
        raise FetchError(f"yfinance 回傳資料不足（{symbol}）：無現價或無合約")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return map_rows(symbol, spot, fetched_at, rows)
