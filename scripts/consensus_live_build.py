#!/usr/bin/env python
"""本機實測：用**真實 Yahoo** 走正式程式路徑建立分析師資料（LIVE-T3／#398）。

和 SU 在 Scanner 頁按「更新分析師資料」完全同一條路：`create_app()` ＋
`POST /api/opportunity/consensus/update`，依 `remaining` 自動續跑到完，
重試／冷卻／每日上限／處理中標記／呼叫間隔都是正式的 `RefreshPolicy`
（`CONSENSUS_*` 環境變數可覆寫）。最後印出總耗時、成功／失敗檔數與原因、
重試次數、上游呼叫數（每檔一次 fetch）與實際 HTTP 請求數。

**只寫本機資料庫**：`--dsn` 的主機必須是 127.0.0.1／localhost／::1，否則
直接拒絕——絕不連 Production。不需要任何金鑰或密碼。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/consensus_live_build.py --dsn postgresql://postgres@127.0.0.1:55432/oclive
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from api_app import consensus_cache
from api_app.analyst_source import YahooAnalystSource
from api_app.main import create_app
from option_chaser.data.yahoo_analyst import UrllibTransport

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class CountingTransport(UrllibTransport):
    """數實際送出幾個 HTTP 請求（cookie、crumb、quoteSummary、chart）。"""

    def __init__(self):
        super().__init__()
        self.requests = 0

    def get(self, url):
        self.requests += 1
        return super().get(url)


def require_local(dsn: str) -> str:
    host = urlsplit(dsn).hostname or ""
    if host not in LOCAL_HOSTS:
        sys.exit(f"拒絕：DSN 主機 {host!r} 不是本機（只允許 {sorted(LOCAL_HOSTS)}）")
    return host


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    host = require_local(args.dsn)

    from api_app.storage.postgres import PostgresStorage
    from tests._role_session import grant_role

    storage = PostgresStorage(args.dsn)
    grant_role(storage, "superuser", owner_id="live-build")
    transport = CountingTransport()
    policy = consensus_cache.RefreshPolicy.from_env()
    client = TestClient(create_app(identity_resolver=lambda: "live-build",
                                   storage=storage,
                                   analyst_source=YahooAnalystSource(transport),
                                   consensus_refresh_policy=policy))
    print(f"DSN 主機 {host}（本機）；policy={json.dumps(policy.view())}")

    started = time.monotonic()
    calls = 0
    stopped = None
    while True:
        t0 = time.monotonic()
        r = client.post("/api/opportunity/consensus/update", json={})
        r.raise_for_status()
        body = r.json()
        calls += 1
        p = body["progress"]
        print(f"第 {calls} 次呼叫 {time.monotonic() - t0:5.1f}s：處理 {body['processed']} 檔"
              f"（成功 {body['succeeded']}、失敗 {body['failed']}），"
              f"剩 {len(body['remaining'])}；累計完成 {p['done']}／{p['total']}、失敗 {p['failed']}")
        if body["stopped_reason"]:
            stopped = body["message"]
            break
        if not body["remaining"] or body["processed"] == 0:
            break
    elapsed = time.monotonic() - started

    status = client.get("/api/opportunity/consensus/status").json()
    consensus = client.get("/api/opportunity/consensus").json()
    failed = [s for s in status["symbols"] if s["error"]]
    retries = sum(s["retries_today"] for s in status["symbols"])
    quality = Counter(i["status"] for i in consensus["items"])
    print("\n===== 結果 =====")
    print(f"更新母體 {status['progress']['total']} 檔；API 呼叫 {calls} 次；總耗時 {elapsed:.1f} 秒")
    print(f"成功 {status['progress']['done']} 檔、失敗 {len(failed)} 檔、今日重試 {retries} 次")
    print(f"上游呼叫（每檔 fetch）{status['upstream_calls_today']} 次／每日上限 "
          f"{status['daily_cap']}；實際 HTTP 請求 {transport.requests} 個")
    if stopped:
        print(f"停止原因：{stopped}")
    for s in failed:
        print(f"  失敗 {s['symbol']}：{s['error']}（狀態 {s['state']}，下次 {s['next_retry_at']}）")
    print(f"共識狀態分布（大型股樣本）：{dict(quality)}")
    print(f"資料日 {status['data_as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
