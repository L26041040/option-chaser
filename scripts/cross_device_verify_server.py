"""OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001：真瀏覽器跨裝置登入驗證用的本機站。

跟正式站同一套東西：`npm run build` 出來的前端（`dist/`）＋同一個 FastAPI
app（`create_app()`）＋真的 Postgres，走 HTTPS（`__Host-` cookie 需要
Secure）。抓報價換成測試快照（不打外部網路）。SU／SA 密碼只用環境變數給的
**測試值**——絕不是正式站的密碼。需要 `uvicorn`（`uv pip install uvicorn`）
與一組自簽憑證（`openssl req -x509 -newkey rsa:2048 -nodes …`）。

    # 1) 先種一個跟 Production 同形狀的主帳號（Tcf2_BUR 開頭、superuser、
    #    受保護、20 個劇本、一台舊裝置憑證還沒有權限欄位）
    python scripts/cross_device_verify_server.py --dsn postgresql://... --seed
    # 2) 另一個 process 起站（冷啟動的 schema 回填會在這裡真的跑一次）
    OC_VERIFY_SU_PASSWORD=... OC_VERIFY_SA_PASSWORD=... \\
      python scripts/cross_device_verify_server.py --dsn postgresql://... \\
      --cert cert.pem --key key.pem --port 8443
    # 3) node scripts/cross_device_verify.mjs（見那支檔案）
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api_app import main_account  # noqa: E402
from api_app.storage import BrowserIdentity, Owner, Scenario  # noqa: E402

FIX = ROOT / "tests/fixtures/xyz_v4_six_expiries.json"
NOW = "2026-10-25T00:00:00+00:00"
SEED_SCENARIOS = 20


def seed(dsn: str) -> None:
    import psycopg

    from api_app.storage.postgres import PostgresStorage
    st = PostgresStorage(dsn)
    st._ensure_schema()
    tables = ("scenarios", "results", "current_results", "snapshots", "events",
              "diagnostics", "owner_settings", "owner_credentials",
              "owner_verifications", "owners", "browser_identities",
              "rate_limits", "feedback", "main_account", "owner_merge_archive",
              "identity_tombstones")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY")
    main = main_account.SEED_OWNER_PREFIX + secrets.token_urlsafe(26)
    st.create_owner_with_token(
        Owner(owner_id=main, created_at=NOW, protected=True),
        BrowserIdentity(token=secrets.token_urlsafe(32), owner_id=main,
                        issued_at=NOW, last_seen_at=NOW))
    st.set_owner_role(main, "superuser")
    for i in range(SEED_SCENARIOS):
        st.create_scenario(Scenario(
            id=f"seed-{i:02d}", symbol="XYZ", direction="bullish",
            target_price=130.0 + i, target_month="2027-01", notes="",
            strategies=("vertical-spread",), created_at=NOW,
            archived_at=NOW if i < 3 else None, owner_id=main))
    # 模擬上線前的資料：舊裝置憑證還沒有權限欄位（冷啟動回填前的狀態）。
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("UPDATE browser_identities SET role = NULL")
    print(f"seeded main account ({main_account.SEED_OWNER_PREFIX}…) with "
          f"{SEED_SCENARIOS} scenarios")


def build_app(dsn: str):
    from starlette.exceptions import HTTPException
    from starlette.staticfiles import StaticFiles

    from api_app.main import create_app
    from api_app.storage.postgres import PostgresStorage
    from option_chaser.data.snapshot import load_snapshot

    snap = load_snapshot(str(FIX))
    api = create_app(fetch=lambda symbol: snap, storage=PostgresStorage(dsn),
                     superuser_password=os.environ["OC_VERIFY_SU_PASSWORD"],
                     superadmin_password=os.environ["OC_VERIFY_SA_PASSWORD"],
                     cron_secret="verify-only-cron-secret")

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
        if scope["type"] != "http" or scope["path"].startswith("/api"):
            return await api(scope, receive, send)
        return await static(scope, receive, send)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()
    if args.seed:
        seed(args.dsn)
        return
    import uvicorn
    uvicorn.run(build_app(args.dsn), host="127.0.0.1", port=args.port,
                ssl_certfile=args.cert, ssl_keyfile=args.key, log_level="warning")


if __name__ == "__main__":
    main()
