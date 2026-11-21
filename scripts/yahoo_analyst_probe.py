"""LIVE-T1（#397）一次性本機實測：真的連上 Yahoo，量測逐券商目標價的可用性。

只讀外部公開端點、只在本機計算，**不連任何資料庫**（更不碰 Production）。
每檔之間間隔 1.5 秒，避免造成負擔；不使用任何繞過技術。共識計算的規則與
部署環境相同（`ConsensusRules(aliases=FIRM_ALIASES)`）。

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
from option_chaser.data.yahoo_analyst import FIRM_ALIASES, UrllibTransport, YahooError

DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "AVGO", "WMT", "JPM", "GS",
           "BABA", "TSM", "WDFC"]
NO_CRUMB_URL = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL"
                "?modules=upgradeDowngradeHistory")


def main(symbols: list[str]) -> int:
    tw = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rules = ConsensusRules(aliases=FIRM_ALIASES)
    source = YahooAnalystSource()
    print(f"# Yahoo upgradeDowngradeHistory 實測 {tw} (台灣)，美東日期 {today}")
    print(f"不帶 crumb 的 quoteSummary：HTTP {UrllibTransport().get(NO_CRUMB_URL).status}"
          "（401＝必須走 cookie＋crumb）")
    print("symbol | 原始列 | 有目標價 | 比例 | 券商 | 最早 | 分割 | 耗時s | "
          "有效人數/Yahoo人數 | status | D | 百分位 | 歷史點")
    ok = failed = 0
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(1.5)
        t0 = time.monotonic()
        try:
            data = source.client.fetch(sym)
        except YahooError as e:
            failed += 1
            print(f"{sym} | 失敗：{e} (retry_after={e.retry_after})")
            continue
        elapsed = time.monotonic() - t0
        ok += 1
        result = source.to_provider_result(sym, data)
        snap = compute_snapshot(result.records, result.splits, today, rules,
                                coverage=result.coverage, cross_check=result.cross_check)
        summary = data.summary
        share = len(summary.targets) / summary.history_rows if summary.history_rows else 0
        earliest = min((t.published_on for t in summary.targets), default=None)
        splits = ",".join(f"{s.effective_on}:{format(s.ratio.normalize(), 'f')}"
                          for s in data.splits[-2:]) or "-"
        d = f"{snap.dispersion:.4f}" if snap.dispersion is not None else "-"
        p = f"{snap.percentile:.3f}" if snap.percentile is not None else "-"
        print(f"{sym} | {summary.history_rows} | {len(summary.targets)} | {share:.1%} | "
              f"{len({t.firm for t in summary.targets})} | {earliest} | {splits} | "
              f"{elapsed:.2f} | {snap.n_analysts}/{summary.analyst_count} | {snap.status} | "
              f"{d} | {p} | {snap.history_points}")
    print(f"成功 {ok}／{ok + failed}，失敗 {failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or DEFAULT))
