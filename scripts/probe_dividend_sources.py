#!/usr/bin/env python
"""#120（spec #117 §3）：q 資料源 production 探測腳本。

**這支腳本本身不能在本 repo 的 agent 沙箱跑**——沙箱出口政策封鎖
`query2.finance.yahoo.com`／`api.nasdaq.com`／`financialmodelingprep.com`
這三個網域（已用 curl 直接驗證：CONNECT 407/403），這是沙箱代理層的
政策，不代表 Vercel production 或需求方本機打不到，兩件事不可混為
一談（本 repo 一貫的誠實揭露紀律，見
`docs/research/interest-rate-source-selection.md` §0）。

**用法**：在 Vercel（或任何可連網環境）跑：

    python3 scripts/probe_dividend_sources.py

輸出每個 URL 的狀態碼／`Content-Type`／前 500 bytes body 到 stdout（純
文字，方便貼進 issue／研究文件）。跑完把結果貼回
`docs/research/dividend-yield-source-selection.md` 的探測結果章節，
依 §6.3（沿用自 `interest-rate-source-selection.md`）的紀律：

- 每個 URL 至少測兩次（平日盤中/盤後一次、週末或假日一次），確認
  「假日該端點是回舊資料還是回錯誤」
- 記下原始回應，不是只記「成功/失敗」
- **不得**在沒有成功呼叫過的情況下宣稱「vendor 已確認」（#120／#111
  兩張票共同的既有紀律）

探測項目對應研究文件 §12.3 第 1、2、6 項（第 5／7 項需要金鑰／人工
比對，不在本腳本範圍；第 3／4／8 項需要人工核對發行商官網或跨假日
重跑，同樣不在本腳本範圍）。

純 stdlib，比照 `option_chaser/data/cboe.py`／`treasury.py` 的既有
慣例（`urllib.request`，逾時 15 秒，不吞例外——探測腳本要看到真正的
錯誤，不是靜默降級）。
"""
from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_TIMEOUT_SECONDS = 15.0
_USER_AGENT = "option-chaser-probe/1"

PROBES = [
    {
        "id": 1,
        "name": "Yahoo chart events（配息標的，本推薦的關鍵未知）",
        "url": ("https://query2.finance.yahoo.com/v8/finance/chart/TLT"
               "?range=2y&interval=1d&events=div,splits,capitalGains"),
        "pass_criteria": ("200 + JSON + chart.result[0].events.dividends "
                          "非空，每筆含 amount/date"),
        "yahoo_dividend_check": True,
    },
    {
        "id": 2,
        "name": "Yahoo chart events（非配息標的，確認「明確無配息」的形狀）",
        "url": ("https://query2.finance.yahoo.com/v8/finance/chart/YETI"
               "?range=2y&interval=1d&events=div,splits,capitalGains"),
        "pass_criteria": "200 + events 缺 dividends 鍵或為空",
    },
    {
        "id": 6,
        "name": "Nasdaq 免鑰（backup #2）",
        "url": "https://api.nasdaq.com/api/quote/TLT/dividends?assetclass=etf",
        "pass_criteria": ("200 + data.dividends.rows 非空 + "
                          "data.annualizedDividend 存在"),
        "extra_headers": {
            "Accept": "application/json",
        },
    },
]


def _yahoo_dividend_diagnostics(body: bytes) -> dict | None:
    """#120 AC 直接判讀：events.dividends 是否存在／近 365 天筆數／
    每筆 amount+ex-date 形狀——不能只看 500 bytes 前綴（2y 日線的
    indicators 陣列很大，events 通常排在後面，preview 常常看不到）。"""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    result = (parsed.get("chart", {}).get("result") or [None])[0]
    if not result:
        return {"has_events_key": False}
    events = result.get("events")
    if not events or "dividends" not in events:
        return {"has_events_key": bool(events), "has_dividends_key": False}
    divs = events["dividends"]
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=365)
    entries = []
    within_365d = 0
    sum_365d = 0.0
    for ts_key, d in divs.items():
        ex_date = datetime.datetime.fromtimestamp(int(ts_key), tz=datetime.timezone.utc)
        if ex_date >= cutoff:
            within_365d += 1
            sum_365d += d.get("amount") or 0.0
        entries.append({"amount": d.get("amount"), "ex_date": ex_date.date().isoformat()})
    entries.sort(key=lambda e: e["ex_date"], reverse=True)
    splits = events.get("splits")
    return {
        "has_dividends_key": True,
        "total_dividend_entries": len(entries),
        "within_365d_count": within_365d,
        "sum_amount_within_365d": round(sum_365d, 6),
        "sample_recent_entries": entries[:6],
        "has_splits_key": bool(splits),
        "splits_in_window": splits if splits else None,
    }


def _probe(spec: dict) -> dict:
    headers = {"User-Agent": _USER_AGENT, **spec.get("extra_headers", {})}
    req = Request(spec["url"], headers=headers)
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = resp.read()
            out = {
                "id": spec["id"], "name": spec["name"], "url": spec["url"],
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type"),
                "body_preview": body[:500].decode("utf-8", errors="replace"),
                "error": None,
            }
            if spec.get("yahoo_dividend_check"):
                out["dividend_diagnostics"] = _yahoo_dividend_diagnostics(body)
            return out
    except HTTPError as e:
        body = e.read(500) if e.fp else b""
        return {
            "id": spec["id"], "name": spec["name"], "url": spec["url"],
            "status": e.code, "content_type": e.headers.get("Content-Type")
            if e.headers else None,
            "body_preview": body.decode("utf-8", errors="replace"),
            "error": f"HTTPError {e.code}",
        }
    except URLError as e:
        return {
            "id": spec["id"], "name": spec["name"], "url": spec["url"],
            "status": None, "content_type": None, "body_preview": "",
            "error": f"URLError: {e.reason}",
        }


def main() -> None:
    results = [_probe(spec) for spec in PROBES]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("\n---\n", file=sys.stderr)
    for r in results:
        status = r["error"] or f"HTTP {r['status']}"
        print(f"[{r['id']}] {r['name']}: {status}", file=sys.stderr)


if __name__ == "__main__":
    main()
