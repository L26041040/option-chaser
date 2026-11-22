#!/usr/bin/env python
"""LIVE-T2（#399）一次性本機實測：真實 Yahoo → 共識快取 → 個股詳細資料。

走部署環境同一條路徑：`YahooAnalystSource`（真的連 Yahoo，每檔間隔 1.5 秒）→
`consensus_cache.refresh_symbols()`（寫快取）→ `consensus_cache.detail_view()`
（只讀快取），規則與部署相同（`ConsensusRules(aliases=FIRM_ALIASES)`）、門檻用
預設 20%／10%。

**只寫本機測試資料庫**：storage 一律是 `OC_TEST_DATABASE_URL`（必須指向
127.0.0.1／localhost），沒設就用記憶體；絕不讀 `DATABASE_URL` 等正式環境變數。

    SSL_CERT_FILE=... OC_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/octest \\
    PYTHONPATH=. .venv/bin/python scripts/consensus_history_live_check.py [SYMBOL ...]
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from api_app import consensus_cache, opportunity_settings
from api_app.analyst_source import YahooAnalystSource
from option_chaser.consensus import ConsensusRules
from option_chaser.data.yahoo_analyst import FIRM_ALIASES

DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "AVGO", "JPM", "BABA", "TSM", "WDFC"]


class Paced:
    """每次抓取前間隔 1.5 秒，避免造成負擔。"""

    def __init__(self, inner):
        self.inner, self.name, self.is_fixture = inner, inner.name, inner.is_fixture
        self.first = True

    def fetch(self, symbol, today):
        if not self.first:
            time.sleep(1.5)
        self.first = False
        return self.inner.fetch(symbol, today)


def _storage():
    url = os.environ.get("OC_TEST_DATABASE_URL")
    if not url:
        from api_app.storage.memory import MemoryStorage
        return MemoryStorage(), "memory"
    host = urlparse(url).hostname
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit(f"拒絕：OC_TEST_DATABASE_URL 不是本機（{host}）")
    from api_app.storage.postgres import PostgresStorage
    return PostgresStorage(url), f"postgres@{host}"


def main(symbols: list[str]) -> int:
    tw = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    storage, where = _storage()
    rules = ConsensusRules(aliases=FIRM_ALIASES)
    source = Paced(YahooAnalystSource())
    stats = consensus_cache.refresh_symbols(storage, source, symbols, today,
                                            budget_exhausted=lambda: False, rules=rules)
    print(f"# LIVE-T2 實測 {tw} (台灣)，美東日期 {today}，storage={where}")
    print(f"更新：成功 {stats['succeeded']}、失敗 {stats['failed']}、"
          f"今天已更新過 {stats['already_attempted_today']}")
    print("symbol | status | 有效人數 | 平均 | D | 百分位 | 合格歷史點/月數 | 入選 | 原因")
    opportunity = opportunity_settings.effective(None)
    for sym in symbols:
        body = consensus_cache.detail_view(storage, source, sym, opportunity, today,
                                           rules=rules)
        i = body["item"]
        d = f"{i['dispersion']:.4f}" if i["dispersion"] is not None else "-"
        p = f"{i['percentile']:.3f}" if i["percentile"] is not None else "-"
        mean = f"{i['mean']:.2f}" if i["mean"] is not None else "-"
        reasons = "; ".join(i["gate"]["reasons"]) or "-"
        print(f"{sym} | {i['status']} | {i['n_analysts']} | {mean} | {d} | {p} | "
              f"{body['qualified_points']}/{len(body['series'])} | "
              f"{'是' if i['gate']['selected'] else '否'} | {reasons}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or DEFAULT))
