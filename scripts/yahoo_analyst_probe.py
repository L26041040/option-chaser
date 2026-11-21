"""LIVE-T1（#397）一次性本機實測：真的連上 Yahoo，量測逐券商目標價的可用性。

只讀外部公開端點、只在本機計算，**不連任何資料庫**（更不碰 Production）。
每檔之間間隔 1.5 秒，避免造成負擔；不使用任何繞過技術。

用法：
    PYTHONPATH=. .venv/bin/python scripts/yahoo_analyst_probe.py [SYMBOL ...]
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from api_app.analyst_source import YahooAnalystSource
from option_chaser.consensus import ConsensusRules, compute_snapshot
from option_chaser.data.yahoo_analyst import (SUMMARY_URL, UrllibTransport,
                                              YahooClient, YahooError)

DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "AVGO", "WMT", "JPM", "GS",
           "BABA", "TSM", "WDFC"]


def main(symbols: list[str]) -> int:
    tw = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    print(f"# Yahoo upgradeDowngradeHistory 實測 {tw} (台灣)，美東日期 {today}")
    transport = UrllibTransport()
    no_crumb = transport.get(SUMMARY_URL.format(symbol="AAPL", crumb="").replace("&crumb=", ""))
    print(f"不帶 crumb 的 quoteSummary：HTTP {no_crumb.status}（401＝必須走 cookie＋crumb）")
    client = YahooClient(transport)
    source = YahooAnalystSource()
    print("symbol | 原始列 | 有目標價 | 比例 | 券商 | 最早 | 分割 | 耗時s | 有效人數/Yahoo人數 | status | D | 百分位 | 歷史點")
    ok = failed = 0
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(1.5)
        t0 = time.monotonic()
        try:
            data = client.fetch(sym)
        except YahooError as e:
            failed += 1
            print(f"{sym} | 失敗：{e} (retry_after={e.retry_after})")
            continue
        dt = time.monotonic() - t0
        ok += 1
        result = source.result_from(sym, data)
        snap = compute_snapshot(result.records, result.splits, today, ConsensusRules(),
                                coverage=result.coverage, cross_check=result.cross_check)
        share = len(data.targets) / data.history_rows if data.history_rows else 0
        earliest = min((t.published_on for t in data.targets), default=None)
        splits = ",".join(f"{s.effective_on}:{format(s.ratio.normalize(), 'f')}" for s in data.splits[-2:]) or "-"
        d = f"{snap.dispersion:.4f}" if snap.dispersion is not None else "-"
        p = f"{snap.percentile:.3f}" if snap.percentile is not None else "-"
        print(f"{sym} | {data.history_rows} | {len(data.targets)} | {share:.1%} | "
              f"{len({t.firm for t in data.targets})} | {earliest} | {splits} | {dt:.2f} | "
              f"{snap.n_analysts}/{data.analyst_count} | {snap.status} | {d} | {p} | {snap.history_points}")
    print(f"成功 {ok}／{ok + failed}，失敗 {failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or DEFAULT))
