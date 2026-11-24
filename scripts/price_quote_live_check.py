#!/usr/bin/env python
"""V2-05（#407）本機真實資料核對：目前股價、報價日期、目標漲跌幅與 Yahoo 原值一致。

對幾檔真實股票：

1. **原值**：直接 GET Yahoo chart 端點（獨立的一次請求，不經 adapter），讀
   `meta.regularMarketPrice`／`regularMarketTime`。
2. **流程**：記憶體 storage＋真實 `YahooAnalystSource`，跑共識更新
   （`consensus_cache.refresh_symbols`）再讀清單（`consensus_view`）——畫面
   顯示的就是這裡的 `price`／`price_date`／`target_upside_pct`。
3. 比對股價與日期；目標漲跌幅以 (mean ÷ price − 1) × 100 另算一次核對。
4. 數流程的上游請求：每檔仍是 quoteSummary＋chart 各一次（cookie／crumb
   只在第一檔取一次），每日上游計數每檔扣 1。

不寫任何資料庫、不需要金鑰；只連 Yahoo。沙箱裡要帶代理的 CA：

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. \\
        .venv/bin/python scripts/price_quote_live_check.py AAPL NVDA AVGO
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from api_app import consensus_cache
from api_app.analyst_source import YahooAnalystSource
from api_app.clock import ny_today
from api_app.opportunity_settings import effective
from api_app.storage.memory import MemoryStorage
from option_chaser.data.dividends import _USER_AGENT
from option_chaser.data.yahoo_analyst import CHART_URL, UrllibTransport

NY = ZoneInfo("America/New_York")


class CountingTransport(UrllibTransport):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def get(self, url):
        self.calls.append(url)
        return super().get(url)


def raw_quote(symbol: str) -> tuple[Decimal, datetime]:
    req = urllib.request.Request(CHART_URL.format(symbol=symbol),
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        meta = json.load(resp)["chart"]["result"][0]["meta"]
    return (Decimal(str(meta["regularMarketPrice"])),
            datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=timezone.utc))


def main(symbols: list[str]) -> int:
    today = ny_today()
    raws = {s: raw_quote(s) for s in symbols}
    transport = CountingTransport()
    source = YahooAnalystSource(transport=transport)
    storage = MemoryStorage()
    out = consensus_cache.refresh_symbols(storage, source, symbols, today,
                                          budget_exhausted=lambda: False)
    view = consensus_cache.consensus_view(
        storage, source, effective({"universe_id": "custom", "custom_symbols": symbols}),
        today)
    ok = True
    print(f"today(NY)={today}  upstream_calls_today={out['upstream_calls_today']}  "
          f"http_requests={len(transport.calls)}")
    for item in view["items"]:
        s = item["symbol"]
        price, at = raws[s]
        raw_date = at.astimezone(NY).date().isoformat()
        same = item["price"] == float(price) and item["price_date"] == raw_date
        expected = None
        if item["mean"] is not None and item["target_upside_pct"] is not None:
            expected = float(((Decimal(str(item["mean"])) / price - 1) * 100)
                             .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        upside_ok = expected is None or expected == item["target_upside_pct"]
        ok = ok and same and upside_ok
        print(f"{s:5} yahoo={price} @ {at.astimezone(NY):%Y-%m-%d %H:%M} ET | "
              f"shown={item['price']} ({item['price_date']} {item['price_kind']}) | "
              f"mean={item['mean']:.2f} upside={item['target_upside_pct']} "
              f"(independent {expected}) reason={item['target_upside_reason']} | "
              f"{'MATCH' if same and upside_ok else 'MISMATCH'}"
              if item["mean"] is not None else
              f"{s:5} yahoo={price} shown={item['price']} reason={item['target_upside_reason']}")
    per_symbol = {k: sum(k in u for u in transport.calls)
                  for k in ("quoteSummary", "/chart/", "getcrumb")}
    print(f"requests by kind: {per_symbol}")
    ok = ok and per_symbol["/chart/"] == len(symbols) and \
        out["upstream_calls_today"] == len(symbols)
    print("ALL MATCH" if ok else "CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["AAPL", "NVDA", "AVGO", "MSFT", "JPM"]))
