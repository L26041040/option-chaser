#!/usr/bin/env python
"""HIVT-01 (#152): Market Data App exact-contract historical endpoint probe.

Runs only against real vendor responses. 2xx responses are accepted because
Market Data App legitimately returns 203 for delayed option data.
The token is never printed.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://api.marketdata.app/v1"
TIMEOUT = 30.0
SYMBOL = "TLT"


def _get(url: str, token: str | None) -> tuple[int, dict | str, dict]:
    headers = {
        "User-Agent": "option-chaser-hivt01-probe",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            hdrs = {k: v for k, v in resp.headers.items()}
            status = resp.status
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw, {k: v for k, v in e.headers.items()}
    except (URLError, OSError) as e:
        return 0, f"connection failed: {type(e).__name__}: {e}", {}
    try:
        return status, json.loads(raw), hdrs
    except json.JSONDecodeError:
        return status, raw, hdrs


def _vendor_ok(status: int, body: dict | str) -> bool:
    """Market Data App may return 203 for delayed-but-valid data."""
    return 200 <= status < 300 and isinstance(body, dict) and body.get("s") == "ok"


def _ratelimit(headers: dict) -> dict:
    return {
        k: v
        for k, v in headers.items()
        if "ratelimit" in k.lower() or "credit" in k.lower()
    }


def probe_auth_failure_mode() -> dict:
    status, body, headers = _get(f"{BASE}/options/expirations/{SYMBOL}/", None)
    return {
        "step": "auth failure mode (no token)",
        "endpoint": f"/v1/options/expirations/{SYMBOL}/",
        "http_status": status,
        "body_sample": body,
        "ratelimit_headers": _ratelimit(headers),
    }


def find_leaps_contract(token: str) -> dict:
    status, body, headers = _get(f"{BASE}/options/expirations/{SYMBOL}/", token)
    if not _vendor_ok(status, body):
        return {
            "ok": False,
            "step": "expiration list",
            "http_status": status,
            "body_sample": body,
            "ratelimit_headers": _ratelimit(headers),
        }

    expiries = sorted(body.get("expirations") or [])
    if not expiries:
        return {"ok": False, "step": "expiration list", "note": "no expirations"}
    leaps_expiry = expiries[-1]

    status2, chain, headers2 = _get(
        f"{BASE}/options/chain/{SYMBOL}/?expiration={leaps_expiry}", token
    )
    if not _vendor_ok(status2, chain):
        return {
            "ok": False,
            "step": "LEAPS chain",
            "http_status": status2,
            "body_sample": chain,
            "leaps_expiry": leaps_expiry,
            "ratelimit_headers": _ratelimit(headers2),
        }

    symbols = chain.get("optionSymbol") or []
    strikes = chain.get("strike") or []
    sides = chain.get("side") or []
    calls = [
        (sym, strike)
        for sym, strike, side in zip(symbols, strikes, sides)
        if side == "call"
    ]
    if not calls:
        return {
            "ok": False,
            "step": "select call",
            "leaps_expiry": leaps_expiry,
            "note": "no calls in chain",
        }

    calls_sorted = sorted(calls, key=lambda t: t[1])
    occ_symbol, strike = calls_sorted[len(calls_sorted) // 2]
    return {
        "ok": True,
        "leaps_expiry": leaps_expiry,
        "all_expiries_count": len(expiries),
        "occ_symbol": occ_symbol,
        "strike": strike,
        "expirations_http_status": status,
        "chain_http_status": status2,
        "ratelimit_headers": _ratelimit(headers2),
    }


def _summarize_history(step: str, url: str, status: int, body: dict | str, headers: dict) -> dict:
    out = {
        "step": step,
        "endpoint": url,
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
        "ok": _vendor_ok(status, body),
    }
    if not out["ok"]:
        out["body_sample"] = body
        return out

    assert isinstance(body, dict)
    out["field_names"] = sorted(body.keys())
    out["field_types"] = {k: type(v).__name__ for k, v in body.items()}
    list_fields = {k: v for k, v in body.items() if isinstance(v, list)}
    out["row_counts_by_field"] = {k: len(v) for k, v in list_fields.items()}
    out["has_iv_field_directly"] = "iv" in body
    out["has_bid_ask_last"] = {
        "bid": "bid" in body,
        "ask": "ask" in body,
        "last": "last" in body,
    }
    out["has_delta"] = "delta" in body
    out["has_dte"] = "dte" in body
    if isinstance(body.get("updated"), list):
        updated = body["updated"]
        out["rows_returned"] = len(updated)
        out["date_sample_first3"] = updated[:3]
        out["date_sample_last3"] = updated[-3:]
    for key in ("iv", "bid", "ask", "last"):
        if isinstance(body.get(key), list):
            out[f"{key}_sample_first3"] = body[key][:3]
    return out


def probe_single_contract_full_year(token: str, occ_symbol: str) -> dict:
    frm = (date.today() - timedelta(days=365)).isoformat()
    to = date.today().isoformat()
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    return _summarize_history(
        "single-contract 1Y historical series (core)", url, status, body, headers
    )


def probe_out_of_range_date(token: str, occ_symbol: str) -> dict:
    frm = (date.today() - timedelta(days=365 * 5)).isoformat()
    to = date.today().isoformat()
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    out = _summarize_history(
        "out-of-range from date (5Y ago)", url, status, body, headers
    )
    if out.get("ok") and isinstance(body, dict):
        updated = body.get("updated") or []
        out["earliest_date_returned"] = min(updated) if updated else None
    return out


def probe_weekend_window(token: str, occ_symbol: str) -> dict:
    today = date.today()
    days_back = (today.weekday() - 5) % 7 or 7
    last_saturday = today - timedelta(days=days_back)
    frm = (last_saturday - timedelta(days=2)).isoformat()
    to = (last_saturday + timedelta(days=3)).isoformat()
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    out = _summarize_history("weekend window", url, status, body, headers)
    if out.get("ok") and isinstance(body, dict):
        out["dates_returned"] = body.get("updated")
        out["expected_calendar_days_in_window"] = (
            date.fromisoformat(to) - date.fromisoformat(frm)
        ).days + 1
    return out


def main() -> None:
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    report: dict = {
        "vendor": "Market Data App",
        "probe_date": date.today().isoformat(),
        "ticket": "HIVT-01 (#152)",
        "symbol": SYMBOL,
        "token_configured": bool(token),
        "steps": [probe_auth_failure_mode()],
    }

    if not token:
        auth_status = report["steps"][0].get("http_status")
        report["blocker"] = {
            "kind": "credential",
            "detail": f"MARKETDATA_APP_TOKEN missing; auth probe status={auth_status}",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    contract = find_leaps_contract(token)
    report["contract_lookup"] = contract
    if not contract.get("ok"):
        report["blocker"] = {
            "kind": "contract_lookup_failed",
            "detail": "authenticated request could not select a TLT LEAPS call; see contract_lookup",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(3)

    occ_symbol = contract["occ_symbol"]
    report["steps"].append(probe_single_contract_full_year(token, occ_symbol))
    report["steps"].append(probe_out_of_range_date(token, occ_symbol))
    report["steps"].append(probe_weekend_window(token, occ_symbol))

    core = report["steps"][1]
    report["verdict"] = {
        "single_contract_history_endpoint_verified": bool(core.get("ok")),
        "can_unlock_hivt02": bool(core.get("ok")),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not core.get("ok"):
        raise SystemExit(4)


if __name__ == "__main__":
    main()
