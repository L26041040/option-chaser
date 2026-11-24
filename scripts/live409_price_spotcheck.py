#!/usr/bin/env python
"""V2-07（#409）股價與目標漲跌幅抽查：本機 `oc409` 存下的值 vs Yahoo chart 原值。

- 存下的值：`consensus_snapshots.snapshot->'quote'`（股票掃描＝分析師共識更新時、同一個
  chart 回應存下的），以及 build 階段 `GET /api/opportunity/consensus` 的
  `price`／`price_date`／`target_upside_pct`（raw JSON）。
- 原值：獨立 GET Yahoo chart 端點一次（不經 adapter），讀 `meta.regularMarketPrice`／
  `regularMarketTime`。
- 目標漲跌幅另以 (mean ÷ price − 1) × 100（Decimal，ROUND_HALF_UP 到 0.1）重算核對。

只讀本機資料庫（主機必須是 127.0.0.1）；只連 Yahoo（經沙箱代理，`SSL_CERT_FILE`）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from option_chaser.data.dividends import _USER_AGENT
from option_chaser.data.yahoo_analyst import CHART_URL
from option_chaser.symbols import yahoo_symbol

NY = ZoneInfo("America/New_York")
TAIPEI = ZoneInfo("Asia/Taipei")


def raw_meta(symbol: str) -> dict:
    req = urllib.request.Request(CHART_URL.format(symbol=yahoo_symbol(symbol)),
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        meta = json.load(resp)["chart"]["result"][0]["meta"]
    at = datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=timezone.utc)
    return {"regularMarketPrice": meta["regularMarketPrice"], "regularMarketTime_utc": at.isoformat(),
            "ny_date": at.astimezone(NY).date().isoformat()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="oc409")
    ap.add_argument("--build-json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("symbols", nargs="+")
    args = ap.parse_args()
    build = json.load(open(args.build_json))
    snap = build["phases"].get("b6_snapshot_final") or build["phases"]["b2_snapshot"]
    items = {i["symbol"]: i for i in snap["items"]}
    rows = []
    for sym in args.symbols:
        q = subprocess.run(["psql", "-X", "-qtA", "-h", "127.0.0.1", "-p", "55432", "-U", "postgres",
                            "-d", args.db, "-c",
                            f"SELECT inet_server_addr(), snapshot->'quote', computed_at FROM consensus_snapshots "
                            f"WHERE symbol='{sym}' ORDER BY computed_at DESC LIMIT 1"],
                           capture_output=True, text=True, check=True).stdout.strip()
        addr, quote, computed_at = q.split("|") if q else (None, "null", None)
        stored_quote = json.loads(quote) if quote else None
        it = items[sym]
        raw = raw_meta(sym)
        time.sleep(1.0)
        recomputed = None
        if it["mean"] is not None and it["price"]:
            recomputed = float(((Decimal(str(it["mean"])) / Decimal(str(it["price"])) - 1) * 100)
                               .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        rows.append({
            "symbol": sym, "db_host": addr, "consensus_computed_at": computed_at,
            "stored_quote_in_consensus_snapshot": stored_quote,
            "api_price": it["price"], "api_price_date": it["price_date"], "api_price_kind": it["price_kind"],
            "api_mean": it["mean"], "api_target_upside_pct": it["target_upside_pct"],
            "api_target_upside_reason": it["target_upside_reason"], "status": it["status"],
            "raw_yahoo": raw,
            "price_matches_raw": it["price"] is not None and abs(it["price"] - raw["regularMarketPrice"]) < 0.005,
            "date_matches_raw": it["price_date"] == raw["ny_date"],
            "upside_recomputed": recomputed,
            "upside_matches_recomputed": (recomputed == it["target_upside_pct"]) if recomputed is not None
            else it["target_upside_pct"] is None,
        })
        print(sym, rows[-1]["api_price"], raw["regularMarketPrice"], rows[-1]["api_price_date"], raw["ny_date"],
              it["target_upside_pct"], recomputed, it["target_upside_reason"])
    out = {"checked_tw": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S") + " (台灣)", "rows": rows,
           "all_price_match": all(r["price_matches_raw"] for r in rows if r["api_price"] is not None),
           "all_date_match": all(r["date_matches_raw"] for r in rows if r["api_price"] is not None),
           "all_upside_match": all(r["upside_matches_recomputed"] for r in rows)}
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=2)
    print({k: v for k, v in out.items() if k != "rows"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
