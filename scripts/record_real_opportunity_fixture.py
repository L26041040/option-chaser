#!/usr/bin/env python
"""錄一份「真實資料」測試樣本（LIVE-T4／#400 的計算等價測試用）。

對一檔 symbol 錄下：

- Yahoo quoteSummary（`upgradeDowngradeHistory` 等）與 chart（分割日曆、週
  收盤）的**回應本文** → `tests/fixtures/yahoo/{SYMBOL}.quote_summary.json`／
  `.chart.json`（與 #397／#399 的真實樣本同一格式，`ReplayTransport` 回放）。
  只存回應本文：crumb 在 URL、cookie 在 header，兩者都不寫進檔案。
- 選擇權 chain：走**既有** `option_chaser.service.fetch_chain()`（Cboe →
  yfinance 降級鏈，不改任何東西）→ `tests/fixtures/real_chain_{SYMBOL}_{紐約
  日期}.json`（既有 `save_snapshot()` 格式；`source` 欄位照實記錄用了哪個源）。

不連任何資料庫、不需要任何金鑰。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/record_real_opportunity_fixture.py JPM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from option_chaser import service
from option_chaser.data.snapshot import save_snapshot, snapshot_today
from option_chaser.data.yahoo_analyst import HttpResponse, UrllibTransport, YahooClient

FIXTURES = Path("tests/fixtures")


class RecordingTransport(UrllibTransport):
    def __init__(self):
        super().__init__()
        self.bodies: dict[str, str] = {}

    def get(self, url: str) -> HttpResponse:
        resp = super().get(url)
        if resp.status == 200 and "quoteSummary" in url:
            self.bodies["quote_summary"] = resp.body
        elif resp.status == 200 and "/chart/" in url:
            self.bodies["chart"] = resp.body
        return resp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("symbol")
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()

    transport = RecordingTransport()
    YahooClient(transport).fetch(symbol)   # 解析失敗會丟例外：不存半份樣本
    for kind in ("quote_summary", "chart"):
        path = FIXTURES / "yahoo" / f"{symbol}.{kind}.json"
        path.write_text(transport.bodies[kind], encoding="utf-8")
        print(f"wrote {path}")

    snap = service.fetch_chain(symbol)
    out = FIXTURES / f"real_chain_{symbol}_{snapshot_today(snap.fetched_at).isoformat()}.json"
    save_snapshot(snap, out)
    print(f"wrote {out}（source={snap.source}，{len(snap.contracts)} 筆合約，"
          f"{len({c.expiry for c in snap.contracts})} 個到期日，spot {snap.spot}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
