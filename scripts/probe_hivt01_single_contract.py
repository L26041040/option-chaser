#!/usr/bin/env python
"""HIVT-01（#152）：Market Data App 單合約歷史端點真實驗證。

spec #151 的 canonical series 需要「同一張 exact contract 的歷史 IV」。
這支腳本只問一件事：`/v1/options/quotes/{occSymbol}/?from=&to=` 這個
單合約端點，對一張真實、長天期（LEAPS，對齊 spec 自己的 TLT fixture
案例）的合約，實際回傳什麼。

跟既有 `probe_marketdata_app.py::probe_single_contract_history()`
不同之處：那支挑的是 AAPL 隨機中段到期日（不保證是 LEAPS），且只跑
一次請求；這支專挑 TLT 最長天期到期日，並額外覆蓋 #152 acceptance
criteria 逐項要求的邊界案例（超界日期、週末/假日、認證失敗模式、
rate-limit headers）。

沙箱出口封鎖 api.marketdata.app（已用 curl 複驗，proxy 明確 403 policy
denial），因此必須在可連網環境跑——本 repo 既有慣例的一次性 GitHub
Actions workflow（見 tmp-vendor-probe.yml 等前例）。

    export MARKETDATA_APP_TOKEN=...   # 若未設定，仍會跑不需要真實
                                       # token 的認證失敗模式探測，其餘
                                       # 步驟明確回報 credential missing。

輸出是一份 JSON 報告，直接貼回 issue #152 當驗證紀錄。**不會**把 token
明文印出來（本 repo 既有紀律，#124／#125／probe_marketdata_app.py 一致）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://api.marketdata.app/v1"
TIMEOUT = 30.0
SYMBOL = "TLT"  # 對齊 spec #151 自己的 TLT LEAPS fixture 案例


def _get(url: str, token: str | None) -> tuple[int, dict | str, dict]:
    """回傳 (HTTP 狀態, 解析後主體或原始字串, 回應標頭)。"""
    headers = {"User-Agent": "option-chaser-hivt01-probe",
               "Accept": "application/json"}
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
        return 0, f"連線失敗：{type(e).__name__}: {e}", {}
    try:
        return status, json.loads(raw), hdrs
    except json.JSONDecodeError:
        return status, raw, hdrs


def _ratelimit(headers: dict) -> dict:
    return {k: v for k, v in headers.items()
            if "ratelimit" in k.lower() or "credit" in k.lower()}


def probe_auth_failure_mode() -> dict:
    """認證失敗模式——不需要真實 token，隨時可測。"""
    status, body, headers = _get(f"{BASE}/options/expirations/{SYMBOL}/", None)
    return {
        "step": "認證失敗模式（無 token）",
        "endpoint": f"/v1/options/expirations/{SYMBOL}/",
        "http_status": status,
        "body_sample": body,
        "ratelimit_headers": _ratelimit(headers),
    }


def find_leaps_contract(token: str) -> dict:
    """找 TLT 最長天期到期日與一個近價履約價，組出真實 OCC symbol。"""
    status, body, _ = _get(f"{BASE}/options/expirations/{SYMBOL}/", token)
    if not (status == 200 and isinstance(body, dict) and body.get("s") == "ok"):
        return {"ok": False, "step": "找到期日清單", "http_status": status,
                "body_sample": body}
    expiries = sorted(body.get("expirations") or [])
    if not expiries:
        return {"ok": False, "step": "找到期日清單", "note": "沒有到期日可用"}
    leaps_expiry = expiries[-1]  # 最遠到期日＝LEAPS

    status2, chain, _ = _get(
        f"{BASE}/options/chain/{SYMBOL}/?expiration={leaps_expiry}", token)
    if not (status2 == 200 and isinstance(chain, dict) and chain.get("s") == "ok"):
        return {"ok": False, "step": "取該到期日的鏈", "http_status": status2,
                "body_sample": chain, "leaps_expiry": leaps_expiry}

    symbols = chain.get("optionSymbol") or []
    strikes = chain.get("strike") or []
    sides = chain.get("side") or []
    calls = [(sym, strike) for sym, strike, side in zip(symbols, strikes, sides)
             if side == "call"]
    if not calls:
        return {"ok": False, "step": "篩選 call", "leaps_expiry": leaps_expiry,
                "note": "該到期日沒有 call"}
    # 挑中位數履約價的 call，不刻意挑 deep-OTM/ITM。
    calls_sorted = sorted(calls, key=lambda t: t[1])
    occ_symbol, strike = calls_sorted[len(calls_sorted) // 2]
    return {
        "ok": True,
        "leaps_expiry": leaps_expiry,
        "all_expiries_count": len(expiries),
        "occ_symbol": occ_symbol,
        "strike": strike,
    }


def probe_single_contract_full_year(token: str, occ_symbol: str) -> dict:
    """核心測試：這張 exact contract 的 1 年歷史序列。"""
    frm = (date.today() - timedelta(days=365)).isoformat()
    to = date.today().isoformat()
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    out = {
        "step": "單合約 1 年歷史序列（核心測試）",
        "endpoint": url,
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
    }
    ok = status == 200 and isinstance(body, dict) and body.get("s") == "ok"
    out["ok"] = ok
    if not ok:
        out["body_sample"] = body
        return out
    out["field_names"] = sorted(body.keys())
    out["field_types"] = {k: type(v).__name__ for k, v in body.items()}
    list_fields = {k: v for k, v in body.items() if isinstance(v, list)}
    out["row_counts_by_field"] = {k: len(v) for k, v in list_fields.items()}
    out["has_iv_field_directly"] = "iv" in body
    out["has_bid_ask_last"] = {
        "bid": "bid" in body, "ask": "ask" in body, "last": "last" in body,
    }
    out["has_delta"] = "delta" in body
    out["has_dte"] = "dte" in body
    # 抽前 3、後 3 筆看形狀與真實數值（不含 token，安全可貼回 issue）。
    if "updated" in body and isinstance(body["updated"], list):
        u = body["updated"]
        out["date_sample_first3"] = u[:3]
        out["date_sample_last3"] = u[-3:]
    for key in ("iv", "bid", "ask", "last"):
        if key in body and isinstance(body[key], list):
            out[f"{key}_sample_first3"] = body[key][:3]
    return out


def probe_out_of_range_date(token: str, occ_symbol: str) -> dict:
    """超過一年前（合約掛牌前）的 from 日期會怎樣：截斷？報錯？空陣列？"""
    frm = (date.today() - timedelta(days=365 * 5)).isoformat()
    to = date.today().isoformat()
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    out = {
        "step": "超界日期（5 年前 from）",
        "endpoint": url,
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
    }
    ok = status == 200 and isinstance(body, dict) and body.get("s") == "ok"
    out["ok"] = ok
    if ok:
        u = body.get("updated") or []
        out["rows_returned"] = len(u)
        out["earliest_date_returned"] = min(u) if u else None
    else:
        out["body_sample"] = body
    return out


def probe_weekend_window(token: str, occ_symbol: str) -> dict:
    """涵蓋一段已知週末的窄窗，看週末是靜默跳過還是明確回傳、值為 null。"""
    today = date.today()
    # 找最近一個已過去的週六
    days_back = (today.weekday() - 5) % 7 or 7
    last_saturday = today - timedelta(days=days_back)
    frm = (last_saturday - timedelta(days=2)).isoformat()  # 週四
    to = (last_saturday + timedelta(days=3)).isoformat()  # 下週二
    url = f"{BASE}/options/quotes/{occ_symbol}/?from={frm}&to={to}"
    status, body, headers = _get(url, token)
    out = {
        "step": "週末窗口行為",
        "endpoint": url,
        "http_status": status,
        "ratelimit_headers": _ratelimit(headers),
    }
    ok = status == 200 and isinstance(body, dict) and body.get("s") == "ok"
    out["ok"] = ok
    if ok:
        out["dates_returned"] = body.get("updated")
        out["row_count"] = len(body.get("updated") or [])
        out["expected_calendar_days_in_window"] = (
            date.fromisoformat(to) - date.fromisoformat(frm)).days + 1
    else:
        out["body_sample"] = body
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
        auth_probe_status = report["steps"][0].get("http_status")
        network_reachable = isinstance(auth_probe_status, int) and auth_probe_status != 0
        if network_reachable:
            network_note = (
                f"網路出口本身可達（認證失敗模式探測回真實 HTTP "
                f"{auth_probe_status}，見 steps[0]），這不是網路問題。"
            )
        else:
            network_note = (
                "網路出口本身也不可達（steps[0] 連線失敗，見其 "
                "body_sample）——這個執行環境同時缺網路出口與 credential。"
            )
        report["blocker"] = {
            "kind": "credential" if network_reachable else "credential_and_network",
            "detail": (
                "MARKETDATA_APP_TOKEN 未設定於此執行環境（GitHub Actions "
                f"secret 或本機環境變數皆未提供）。{network_note}缺的是"
                "憑證：需求方需要到 https://www.marketdata.app/ 申請 "
                "token（既有 #111 建議），設為此 workflow 的 "
                "MARKETDATA_APP_TOKEN secret 或本機環境變數後重跑。"
            ),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    contract = find_leaps_contract(token)
    report["contract_lookup"] = contract
    if not contract.get("ok"):
        report["blocker"] = {
            "kind": "contract_lookup_failed",
            "detail": "有 token 但取不到 TLT 的到期日或鏈資料，見 contract_lookup。",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(3)

    occ_symbol = contract["occ_symbol"]
    report["steps"].append(
        probe_single_contract_full_year(token, occ_symbol))
    report["steps"].append(probe_out_of_range_date(token, occ_symbol))
    report["steps"].append(probe_weekend_window(token, occ_symbol))

    # token 絕不進輸出——這份報告是要貼回 issue 的。
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
