"""LIVE-T4（#400）：機會搜尋「真實上游」真瀏覽器驗證用的本機站（由
`opportunity_live_verify.mjs` 啟動）。

和 `opportunity_verify_server.py`（固定測試資料）同一套站：`dist/` 前端＋
`create_app()`，HTTPS。差別是**資料全部真實**：

- 分析師資料：`YahooAnalystSource`（真實 `upgradeDowngradeHistory`，部署環境同一
  個 adapter、同一組別名表）。
- 選擇權報價、利率、配息：`create_app()` 的**預設**路徑（Cboe → yfinance 降級鏈、
  Global Vendor Fuse、429 退避；不覆寫 `fetch`）。只在 Cboe／yfinance 兩個呼叫點
  外面記下次數與 `ChainSnapshot.source`，回傳值原封不動。
- 「今天」不凍結（真實日期）。

安全：

- 網路閘（沿用 `opportunity_verify_server.install_network_guard`）：行程內只准連
  loopback——本機 Postgres 與沙箱的 HTTPS proxy（`HTTPS_PROXY` 在 127.0.0.1）。
  對外請求一律經 proxy；任何直連都會被擋並記錄（必須是 0）。
- 資料庫：`--dsn` 只接受 127.0.0.1／localhost；殼層裡任何正式站連線字串一律清掉。
  **絕不連 Production。**
- SU／SA 密碼與 cron secret 只從環境變數讀（呼叫端每次隨機產生的拋棄式值），不印
  出、不寫檔。

`/__verify/stats` 回傳 nonce（金絲雀）、分析師來源呼叫數、各報價來源的呼叫數與
成功來源、被擋的對外連線數。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.opportunity_verify_server import (  # noqa: E402
    STATS as GUARD_STATS, assert_local_dsn, install_network_guard)

_lock = threading.Lock()
STATS = {"analyst_fetches": 0, "analyst_http_requests": 0, "chain_attempts": {},
         "chain_sources": {}}
# 逐次記錄（LIVE-T6／#402 驗收報告用）：每次抓鏈 attempt 與每次分析師抓取。
CHAIN_LOG: list[dict] = []
ANALYST_LOG: list[dict] = []


def _count(bucket: str, key: str) -> None:
    with _lock:
        STATS[bucket][key] = STATS[bucket].get(key, 0) + 1


def build_app(*, storage, nonce: str, label: str):
    from starlette.exceptions import HTTPException
    from starlette.responses import JSONResponse
    from starlette.staticfiles import StaticFiles

    from api_app import consensus_cache
    from api_app.analyst_source import YahooAnalystSource
    from api_app.main import create_app
    from option_chaser.consensus import ConsensusRules
    from option_chaser.data import cboe as cboe_module
    from option_chaser.data import yf as yf_module
    from option_chaser.data.yahoo_analyst import FIRM_ALIASES, UrllibTransport

    def observed(name, fn):
        def fetch(symbol):
            _count("chain_attempts", name)
            t0 = time.monotonic()
            started = time.time()
            try:
                snap = fn(symbol)
            except Exception as e:  # noqa: BLE001 — 照原樣往外拋，只記錄
                with _lock:
                    CHAIN_LOG.append({"symbol": symbol, "attempt": name, "ok": False,
                                      "started": started,
                                      "seconds": round(time.monotonic() - t0, 2),
                                      "error": f"{type(e).__name__}: {e}"[:300]})
                raise
            _count("chain_sources", snap.source)
            with _lock:
                CHAIN_LOG.append({"symbol": symbol, "attempt": name, "ok": True,
                                  "started": started,
                                  "seconds": round(time.monotonic() - t0, 2),
                                  "source": snap.source, "spot": snap.spot,
                                  "fetched_at": snap.fetched_at,
                                  "contracts": len(snap.contracts),
                                  "expiries": len({c.expiry for c in snap.contracts})})
            return snap
        return fetch

    class CountingTransport(UrllibTransport):
        def get(self, url):
            with _lock:
                STATS["analyst_http_requests"] += 1
            return super().get(url)

    yf_module.fetch_chain = observed("yfinance", yf_module.fetch_chain)

    class CountingYahoo(YahooAnalystSource):
        def fetch(self, symbol, today):
            with _lock:
                STATS["analyst_fetches"] += 1
            t0 = time.monotonic()
            try:
                out = super().fetch(symbol, today)
            except Exception as e:  # noqa: BLE001
                with _lock:
                    ANALYST_LOG.append({"symbol": symbol, "ok": False,
                                        "seconds": round(time.monotonic() - t0, 2),
                                        "error": f"{type(e).__name__}: {e}"[:300]})
                raise
            with _lock:
                err = getattr(out, "error", None)
                ANALYST_LOG.append({"symbol": symbol, "ok": err is None, "error": err,
                                    "seconds": round(time.monotonic() - t0, 2)})
            return out

    api = create_app(
        storage=storage,
        analyst_source=CountingYahoo(CountingTransport()),
        consensus_rules=ConsensusRules(aliases=FIRM_ALIASES),
        consensus_refresh_policy=consensus_cache.RefreshPolicy.from_env(),
        cboe_fetch=observed("cboe", cboe_module.fetch_chain),
        superuser_password=os.environ["OC_VERIFY_SU_PASSWORD"],
        superadmin_password=os.environ["OC_VERIFY_SA_PASSWORD"],
        cron_secret=os.environ["OC_VERIFY_CRON_SECRET"])

    class SPA(StaticFiles):
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as e:
                if e.status_code != 404:
                    raise
                return await super().get_response("index.html", scope)

    static = SPA(directory=str(ROOT / "dist"), html=True)

    async def app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/__verify/stats":
            with _lock:
                body = {"analyst_fetches": STATS["analyst_fetches"],
                        "analyst_http_requests": STATS["analyst_http_requests"],
                        "chain_log": list(CHAIN_LOG), "analyst_log": list(ANALYST_LOG),
                        "chain_attempts": dict(STATS["chain_attempts"]),
                        "chain_sources": dict(STATS["chain_sources"]),
                        "blocked_connections": GUARD_STATS["blocked_connections"],
                        "blocked_targets": list(GUARD_STATS["blocked_targets"]),
                        "nonce": nonce, "label": label}
            return await JSONResponse(body)(scope, receive, send)
        if scope["type"] != "http" or scope["path"].startswith("/api"):
            return await api(scope, receive, send)
        return await static(scope, receive, send)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    nonce = os.environ["OC_VERIFY_NONCE"]
    from api_app.storage.factory import _ENV_CANDIDATES
    for name in _ENV_CANDIDATES:
        os.environ.pop(name, None)      # 萬一殼層裡有正式站連線字串，一律不用

    install_network_guard()
    db = assert_local_dsn(args.dsn)
    from api_app.storage.postgres import PostgresStorage
    app = build_app(storage=PostgresStorage(args.dsn), nonce=nonce, label=f"postgres:{db}")
    import uvicorn
    print(json.dumps({"ready_soon": db, "port": args.port}), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, ssl_certfile=args.cert,
                ssl_keyfile=args.key, log_level="info")


if __name__ == "__main__":
    main()
