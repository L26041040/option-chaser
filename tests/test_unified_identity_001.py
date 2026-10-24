"""OPTION-CHASER-UNIFIED-IDENTITY-001：一個瀏覽器＝一個持久 user；劇本、
設定、權限全部掛在同一個 user 上；憑證同時存在 HttpOnly cookie 與前端本機
儲存（`X-OC-Credential`），兩份互相補回。

驗收（票面）：同一使用者 1) 永遠讀到自己的劇本 2) SU／SA 升權後重新進站
仍保留權限 3) 不會無故建立新 user 4) 前後端所有身分判斷一致。
"""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
SU = "test-only-su-password"
SA = "test-only-sa-password"
CRED = "X-OC-Credential"
AUTH = {"Authorization": "Bearer fake-cron-secret"}


def _app(storage=None, **kwargs):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return create_app(fetch=lambda symbol: snap, storage=storage,
                      cron_secret="fake-cron-secret", superuser_password=SU,
                      superadmin_password=SA, **kwargs), storage


def _browser(app, *, cookie=None, local=None) -> TestClient:
    """一個瀏覽器：`cookie`＝cookie jar 裡那份，`local`＝本機儲存那份
    （每個請求都放在 `X-OC-Credential`，比照 `src/api.ts` 的 `send()`）。"""
    c = TestClient(app, base_url="https://testserver",
                   cookies={_OWNER_COOKIE_NAME: cookie} if cookie else None)
    if local:
        c.headers[CRED] = local
    return c


def _status(c) -> str:
    return c.get("/api/auth/status").json()["role"]


# ---------- 1. 永遠讀到自己的劇本（任何一份憑證還在就夠） ----------

def test_either_credential_alone_reaches_the_same_user_and_heals_the_other():
    app, storage = _app()
    local = "L" * 43
    first = _browser(app, local=local)
    sid = first.post("/api/scenarios", json=NEW).json()["id"]
    [owner] = storage.list_owners()
    assert first.cookies.get(_OWNER_COOKIE_NAME) == local      # 兩份是同一顆

    # cookie 被清掉、本機那份還在 → 同一個 user，cookie 補發
    r = _browser(app, local=local).get("/api/scenarios")
    assert [row["id"] for row in r.json()] == [sid]
    assert r.cookies.get(_OWNER_COOKIE_NAME) == local
    # 本機那份被清掉（例如 Safari 清掉 script 可寫的儲存）、cookie 還在 → 同一個
    # user，回應把憑證交回給前端存
    r = _browser(app, cookie=local).get("/api/scenarios")
    assert [row["id"] for row in r.json()] == [sid]
    assert r.headers[CRED] == local
    assert [o.owner_id for o in storage.list_owners()] == [owner.owner_id]


def test_a_fresh_local_token_next_to_a_valid_cookie_converges_to_the_cookie():
    """舊版前端在綁定後刪掉了本機那份：升級後第一次載入，前端會新產生一顆
    還沒綁定的 token。cookie 優先，回應把正確的那顆交回去，從此兩份一致——
    不會多出 user。"""
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    cookie = c.cookies.get(_OWNER_COOKIE_NAME)
    upgraded = _browser(app, cookie=cookie, local="N" * 43)
    r = upgraded.get("/api/scenarios")
    assert len(r.json()) == 1
    assert r.headers[CRED] == cookie
    assert "set-cookie" not in r.headers
    assert len(storage.list_owners()) == 1


# ---------- 2. 權限跟著 user 走 ----------

def test_role_follows_the_user_through_every_way_back_in():
    app, storage = _app()
    local = "R" * 43
    c = _browser(app, local=local)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    assert c.post("/api/auth/login", json={"password": SA}).json() == {"role": "superadmin"}

    assert _status(_browser(app, cookie=local)) == "superadmin"      # 重新整理／新分頁
    assert _status(_browser(app, local=local)) == "superadmin"       # cookie 掉了
    redeployed, _ = _app(storage)
    assert _status(_browser(redeployed, cookie=local)) == "superadmin"   # 重新部署
    assert len(storage.list_owners()) == 1


def test_an_elevated_user_with_no_scenarios_is_never_cleaned_up():
    """權限永久保留，除非使用者主動重設：只登入、還沒建劇本的 SA 是「空
    user」，空 user 清理只要 1 天——有權限的 user 必須跳過。"""
    app, storage = _app()
    c = _browser(app)
    c.post("/api/auth/login", json={"password": SU}).raise_for_status()
    [owner] = storage.list_owners()
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    storage._owners[owner.owner_id] = replace(owner, created_at=old)
    for token, ident in list(storage._browser_identities.items()):
        storage._browser_identities[token] = replace(ident, last_seen_at=old)
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner.owner_id).role == "superuser"


def test_beta_reset_keeps_the_admin_who_ran_it():
    app, storage = _app()
    _browser(app).post("/api/scenarios", json=NEW).raise_for_status()   # 一般使用者
    admin = _browser(app)
    admin.post("/api/auth/login", json={"password": SA}).raise_for_status()
    r = admin.post("/api/superuser/reset-beta-data", json={"confirm": "Reset"})
    assert r.status_code == 200
    assert [o.role for o in storage.list_owners()] == ["superadmin"]
    assert _status(admin) == "superadmin"


# ---------- 3. 不會無故建立新 user ----------

def test_reads_status_and_reset_never_create_a_user():
    app, storage = _app()
    c = _browser(app, local="Q" * 43)
    for path in ("/api/scenarios", "/api/me/usage-summary", "/api/auth/status",
                 "/api/settings"):
        assert c.get(path).status_code == 200, path
    assert c.post("/api/auth/reset-role").status_code == 200
    assert storage.list_owners() == []


def test_login_on_a_new_browser_binds_its_local_credential():
    """還沒有 user 的瀏覽器輸入密碼：建立恰好一個 user，綁的就是本機那份
    憑證（cookie 跟著簽同一顆），之後的寫入都落在這個 user。"""
    app, storage = _app()
    local = "S" * 43
    c = _browser(app, local=local)
    r = c.post("/api/auth/login", json={"password": SU})
    assert r.json() == {"role": "superuser"}
    assert r.cookies.get(_OWNER_COOKIE_NAME) == local
    c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner] = storage.list_owners()
    assert storage.resolve_owner_by_token(local) == owner.owner_id
    assert len(storage.list_scenarios(owner=owner.owner_id)) == 1


# ---------- 4. 身分判斷一致 ----------

def test_every_role_aware_answer_comes_from_the_same_user_record():
    """登入、狀態、用量摘要的豁免、SA 管理端點——全部讀同一筆 user 記錄。"""
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()

    def snapshot():
        return (_status(c),
                c.get("/api/me/usage-summary").json()["quota_exempt"],
                c.get("/api/superuser/owners").status_code)

    assert snapshot() == ("normal", False, 401)
    c.post("/api/auth/login", json={"password": SU}).raise_for_status()
    assert snapshot() == ("superuser", True, 401)
    c.post("/api/auth/login", json={"password": SA}).raise_for_status()
    assert snapshot() == ("superadmin", True, 200)
    c.post("/api/auth/reset-role").raise_for_status()
    assert snapshot() == ("normal", False, 401)


def test_owner_scoped_responses_are_never_shared_cacheable():
    """回應依 user 而異，而且可能帶著憑證：一律 `private, no-store`。"""
    app, _ = _app()
    c = _browser(app, local="C" * 43)
    for r in (c.get("/api/scenarios"), c.post("/api/scenarios", json=NEW),
              c.get("/api/auth/status")):
        assert r.headers["cache-control"] == "private, no-store"


@pytest.mark.skipif(not os.environ.get("OC_TEST_DATABASE_URL"),
                    reason="需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
def test_user_scenarios_and_role_survive_across_instances_on_postgres():
    import psycopg
    from api_app.storage.postgres import PostgresStorage

    dsn = os.environ["OC_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in ("scenarios", "owners", "browser_identities"):
            conn.execute(f"DELETE FROM {table}")
    local = "P" * 43
    app_a, _ = _app(PostgresStorage(dsn))
    a = _browser(app_a, local=local)
    sid = a.post("/api/scenarios", json=NEW).json()["id"]
    a.post("/api/auth/login", json={"password": SA}).raise_for_status()

    app_b, _ = _app(PostgresStorage(dsn))                 # 另一個 instance／重新部署
    for b in (_browser(app_b, cookie=local), _browser(app_b, local=local)):
        assert [row["id"] for row in b.get("/api/scenarios").json()] == [sid]
        assert _status(b) == "superadmin"
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM owners").fetchone()[0] == 1
        assert conn.execute("SELECT role FROM owners").fetchone()[0] == "superadmin"
