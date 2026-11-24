#!/usr/bin/env python
"""本機實測：用**真實 Yahoo** 走正式程式路徑建立分析師資料（LIVE-T3／#398）。

和 SU 在 Scanner 頁按「更新分析師資料」完全同一條路：`create_app()` ＋
`POST /api/opportunity/consensus/update`，依 `remaining` 自動續跑到完，
重試／冷卻／每日上限／處理中標記／呼叫間隔都是正式的 `RefreshPolicy`
（`CONSENSUS_*` 環境變數可覆寫）。最後印出總耗時、成功／失敗檔數與原因、
重試次數、上游呼叫數（每檔一次 fetch）與實際 HTTP 請求數。

`--mode cron`（V2-02／#403）：改走 `GET /api/cron/consensus-refresh`——跟
Vercel Cron 同一個端點、同一個 45 秒預算，一次一次呼叫直到整個每日更新範圍
（S&P 500 ＋ SU/SA 自訂清單）跑完，記錄每次呼叫處理的檔數與秒數，換算一天
需要幾個 cron 時段。授權用的是這支腳本每次執行時隨機產生、只活在這個行程裡
的本機值，不是任何真實的 `CRON_SECRET`。遇到 429 就照正式規則停下（整個來源
暫停），不再呼叫上游——不硬打。

**只寫本機資料庫**：`--dsn` 的主機必須是 127.0.0.1／localhost／::1，否則
直接拒絕——絕不連 Production。不需要任何金鑰或密碼。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/consensus_live_build.py --dsn postgresql://postgres@127.0.0.1:55432/oclive
"""
from __future__ import annotations

import argparse
import json
import math
import secrets
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
    parser.add_argument("--mode", choices=("update", "cron"), default="update")
    parser.add_argument("--max-calls", type=int, default=60)
    args = parser.parse_args()
    host = require_local(args.dsn)

    from api_app.storage.postgres import PostgresStorage
    from tests._role_session import grant_role

    storage = PostgresStorage(args.dsn)
    grant_role(storage, "superuser", owner_id="live-build")
    transport = CountingTransport()
    policy = consensus_cache.RefreshPolicy.from_env()
    local_cron_value = secrets.token_urlsafe(32)   # 只活在這個行程裡的本機值
    client = TestClient(create_app(identity_resolver=lambda: "live-build",
                                   storage=storage,
                                   analyst_source=YahooAnalystSource(transport),
                                   consensus_refresh_policy=policy,
                                   cron_secret=local_cron_value))
    print(f"DSN 主機 {host}（本機）；policy={json.dumps(policy.view())}")
    if args.mode == "cron":
        return run_cron(client, transport, local_cron_value, args.max_calls)

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


def run_cron(client, transport, local_cron_value: str, max_calls: int) -> int:
    """像 Vercel Cron 一樣一次一次打 `GET /api/cron/consensus-refresh`。"""
    headers = {"Authorization": f"Bearer {local_cron_value}"}
    started = time.monotonic()
    rows = []
    stopped = None
    for n in range(1, max_calls + 1):
        t0, req0 = time.monotonic(), transport.requests
        r = client.get("/api/cron/consensus-refresh", headers=headers)
        r.raise_for_status()
        body = r.json()
        secs = time.monotonic() - t0
        rows.append((body["processed"], secs, transport.requests - req0))
        print(f"cron 第 {n} 次 {secs:5.1f}s：處理 {body['processed']} 檔（成功 "
              f"{body['succeeded']}、失敗 {body['failed']}），HTTP {transport.requests - req0}，"
              f"剩 {len(body['remaining'])}，今日上游 {body['upstream_calls_today']}／"
              f"{body['daily_cap']}，stopped={body['stopped_reason']}")
        if body["stopped_reason"]:
            stopped = body
            break
        if not body["remaining"] or body["processed"] == 0:
            break
    elapsed = time.monotonic() - started
    status = client.get("/api/opportunity/consensus/status").json()
    consensus = client.get("/api/opportunity/consensus").json()
    failed = [s for s in status["symbols"] if s["error"]]
    full = [p for p, _s, _h in rows[:-1]] or [rows[0][0]]
    per_call = sum(full) / len(full)
    per_symbol = sum(s for _p, s, _h in rows) / max(1, sum(p for p, _s, _h in rows))
    total = status["progress"]["total"]
    print("\n===== cron 實測結果 =====")
    print(f"每日更新範圍 {total} 檔；cron 呼叫 {len(rows)} 次；總耗時 {elapsed:.1f} 秒")
    print(f"每次呼叫（不含最後一次）平均處理 {per_call:.1f} 檔、"
          f"{sum(s for _p, s, _h in rows[:-1]) / max(1, len(rows) - 1):.1f} 秒；"
          f"每檔 {per_symbol:.2f} 秒")
    print(f"成功 {status['progress']['done']}、失敗 {len(failed)}（失敗率 "
          f"{len(failed) / max(1, total):.1%}）")
    print(f"上游呼叫（每檔 fetch）{status['upstream_calls_today']} 次／每日上限 "
          f"{status['daily_cap']}；實際 HTTP 請求 {transport.requests} 個")
    if per_call > 0:
        print(f"一天跑完 {total} 檔需要的 cron 時段：{math.ceil(total / per_call)}")
    else:
        print("這次沒有任何一檔需要抓（同一交易日已成功的不重抓、失敗的在冷卻中）")
    print(f"排程紀錄：{status['cron']}")
    if stopped:
        print(f"停止原因：{stopped['stopped_reason']}（{stopped['message']}），"
              f"暫停到 {stopped.get('rate_limited_until')}")
    for s in failed:
        print(f"  失敗 {s['symbol']}：{s['error']}（狀態 {s['state']}）")
    quality = Counter(i["status"] for i in consensus["items"])
    print(f"共識狀態分布：{dict(quality)}；資料日 {status['data_as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
