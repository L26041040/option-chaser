"""OS-06（#395）：機會搜尋真瀏覽器驗證用的本機站（由 `opportunity_verify.mjs` 啟動）。

跟正式站同一套東西：`npm run build` 出來的前端（`dist/`）＋同一個 FastAPI
app（`create_app()`），走 HTTPS（`__Host-` cookie 需要 Secure）。差別只在
**所有外部資料都換成固定測試資料**，而且這支程式自己擋住任何對外連線：

- 分析師資料：`FixtureAnalystSource`（`tests/fixtures/analyst_targets_fixture.json`，
  ticker AAA…GGG，`is_fixture = True` → 頁面必須標示「測試資料」）。
  `--unconfigured` 則不給來源（＝正式站目前的狀態：尚未設定）。
- 選擇權報價：固定 chain 快照（`tests/fixtures/xyz_v7_butterfly_moderate.json`，
  與 `tests/test_api_opportunity_search.py` 同一份）；`EEE` 固定抓鏈失敗，用來
  驗證錯誤隔離。利率、配息、Historical IV、Cboe、自訂來源一律換成假的。
- 網路閘：行程內所有 Python socket 只准連 loopback（127.0.0.0/8、::1、Unix
  socket），其餘一律拒絕並記錄；`/__verify/stats` 回報被擋的次數（必須是 0）。
- 資料庫：`--dsn` 只接受 127.0.0.1／localhost 上的本機測試 Postgres；或
  `--memory`。**絕不連 Production。**
- 「今天」凍結在測試資料設計用的評估日（同 `tests/conftest.py`）。
- SU／SA 密碼與 cron secret 只從環境變數讀（呼叫端每次隨機產生的**拋棄式
  測試值**），不印出、不寫檔。

`/__verify/stats`（不在 `/api` 底下、只有這支驗證站有）回傳呼叫端給的
nonce（金絲雀用：證明瀏覽器連到的是這個行程）、分析師來源與 chain 的
呼叫次數（驗證「改門檻不重打上游」）、被擋的對外連線數。
"""
from __future__ import annotations

import argparse
import dataclasses
import ipaddress
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ANALYST_FIXTURE = ROOT / "tests/fixtures/analyst_targets_fixture.json"
CHAIN_FIXTURE = ROOT / "tests/fixtures/xyz_v7_butterfly_moderate.json"
FAILING_SYMBOL = "EEE"

_lock = threading.Lock()
STATS = {"analyst_fetches": 0, "chain_fetches": 0, "blocked_connections": 0,
         "blocked_targets": []}


def _bump(key: str, n: int = 1) -> None:
    with _lock:
        STATS[key] += n


# ---------- 網路閘：只准 loopback ----------

def _is_loopback(address) -> bool:
    if isinstance(address, (str, bytes)):          # AF_UNIX
        return True
    host = address[0]
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_network_guard() -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def refuse(address) -> None:
        with _lock:
            STATS["blocked_connections"] += 1
            STATS["blocked_targets"].append(str(address)[:80])
        raise ConnectionRefusedError(f"verify server: outbound connection blocked ({address!r})")

    def connect(self, address):
        if not _is_loopback(address):
            refuse(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        if not _is_loopback(address):
            refuse(address)
        return original_connect_ex(self, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


def assert_local_dsn(dsn: str) -> str:
    """只接受本機 Postgres；回傳資料庫名。"""
    parsed = urlparse(dsn)
    if parsed.scheme not in ("postgresql", "postgres") or parsed.hostname not in (
            "127.0.0.1", "localhost"):
        raise SystemExit("ABORT  --dsn 必須是 127.0.0.1／localhost 上的本機測試 Postgres")
    return (parsed.path or "/").lstrip("/")


# ---------- 假資料來源 ----------

def _freeze_today() -> None:
    """同 `tests/conftest.py`：把每個模組持有的 `ny_today` 換成凍結版本。"""
    from api_app import clock
    from tests._frozen_clock import FROZEN_NY_TODAY

    original = clock.ny_today
    frozen = lambda: FROZEN_NY_TODAY  # noqa: E731
    for module in list(sys.modules.values()):
        if getattr(module, "ny_today", None) is original:
            module.ny_today = frozen


def build_app(*, storage, configured: bool, nonce: str, chain_delay: float, label: str):
    from starlette.exceptions import HTTPException
    from starlette.responses import JSONResponse
    from starlette.staticfiles import StaticFiles

    from api_app.analyst_source import FixtureAnalystSource
    from api_app.main import create_app
    from option_chaser.data.snapshot import load_snapshot
    from option_chaser.models import FetchError
    from scripts.gen_contract_sample import _sample_dividend_loader, _sample_rate_loader

    chain = load_snapshot(str(CHAIN_FIXTURE))

    def fetch(symbol: str):
        _bump("chain_fetches")
        if chain_delay:
            time.sleep(chain_delay)     # 讓「逐檔出現」在畫面上看得到
        if symbol == FAILING_SYMBOL:
            raise FetchError(f"verify server: simulated chain failure for {symbol}")
        # 同一份報價，只把代號換成被查的那一檔（詳細頁頭條才顯示對的代號）；
        # 數值完全不變。
        return dataclasses.replace(chain, symbol=symbol)

    class CountingFixtureSource:
        def __init__(self):
            self.inner = FixtureAnalystSource(ANALYST_FIXTURE)
            self.name = self.inner.name
            self.is_fixture = self.inner.is_fixture

        def fetch(self, symbol, today):
            _bump("analyst_fetches")
            return self.inner.fetch(symbol, today)

    def offline(*_args, **_kwargs):
        raise FetchError("verify server: external source disabled")

    api = create_app(
        fetch=fetch, storage=storage,
        rate_loader=_sample_rate_loader, dividend_loader=_sample_dividend_loader,
        verify_provider=offline, custom_fetch=offline, historical_surface=offline,
        contract_history=offline, rate_curve_rows=offline, cboe_fetch=offline,
        analyst_source=CountingFixtureSource() if configured else None,
        superuser_password=os.environ["OC_VERIFY_SU_PASSWORD"],
        superadmin_password=os.environ["OC_VERIFY_SA_PASSWORD"],
        cron_secret=os.environ["OC_VERIFY_CRON_SECRET"])
    _freeze_today()

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
                body = {**STATS, "blocked_targets": list(STATS["blocked_targets"]),
                        "nonce": nonce, "label": label, "configured": configured}
            return await JSONResponse(body)(scope, receive, send)
        if scope["type"] != "http" or scope["path"].startswith("/api"):
            return await api(scope, receive, send)
        return await static(scope, receive, send)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dsn")
    group.add_argument("--memory", action="store_true")
    parser.add_argument("--unconfigured", action="store_true")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--chain-delay", type=float, default=0.0)
    args = parser.parse_args()
    nonce = os.environ["OC_VERIFY_NONCE"]
    from api_app.storage.factory import _ENV_CANDIDATES
    for name in _ENV_CANDIDATES:
        os.environ.pop(name, None)      # 萬一殼層裡有正式站連線字串，一律不用

    install_network_guard()
    if args.dsn:
        db = assert_local_dsn(args.dsn)
        from api_app.storage.postgres import PostgresStorage
        storage = PostgresStorage(args.dsn)
        label = f"postgres:{db}"
    else:
        from api_app.storage.memory import MemoryStorage
        storage = MemoryStorage()
        label = "memory"
    app = build_app(storage=storage, configured=not args.unconfigured, nonce=nonce,
                    chain_delay=args.chain_delay, label=label)
    import uvicorn
    print(json.dumps({"ready_soon": label, "port": args.port}), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, ssl_certfile=args.cert,
                ssl_keyfile=args.key, log_level="info")


if __name__ == "__main__":
    main()
