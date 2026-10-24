"""OPTION-CHASER-IDENTITY-FIX-002：owner cookie 簽一次、固定 400 天，不再
每次請求都續簽。

驗收清單（票面 §四）：初次建立 owner 正常且只簽一次；後續請求不再
`Set-Cookie`；重新整理／新分頁讀得到原劇本；owner_id 不變；一般請求不建
額外 owner；role 登入／登出不碰 owner cookie；舊版（滑動窗）cookie 照常
可用、只升級一次。另外鎖住「第一次綁定的回應遺失→重試」仍會補發 cookie。
"""
import os
import secrets
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import BrowserIdentity, Owner
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
MAX_AGE = 400 * 24 * 60 * 60
BOOTSTRAP = "X-OC-Owner-Bootstrap"
SU_PASSWORD = "test-only-su-password"


def _app(storage=None):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return create_app(fetch=lambda symbol: snap, storage=storage,
                      cron_secret="fake-cron-secret",
                      superuser_password=SU_PASSWORD), storage


def _browser(app, cookies=None) -> TestClient:
    return TestClient(app, base_url="https://testserver", cookies=cookies)


def _owner_cookies(resp) -> list[str]:
    return [v for k, v in resp.headers.multi_items()
            if k.lower() == "set-cookie" and v.startswith(_OWNER_COOKIE_NAME + "=")]


def _max_age(header: str) -> int:
    part = next(p for p in header.split(";")
                if p.strip().lower().startswith("max-age="))
    return int(part.split("=")[1])


def _legacy_identity(storage) -> str:
    """IDENTITY-FIX-002 之前簽的 cookie：identity 列沒有 `cookie_issued_at`。"""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    storage.create_owner_with_token(
        Owner(owner_id="legacy-owner", created_at=now),
        BrowserIdentity(token=token, owner_id="legacy-owner",
                        issued_at=now, last_seen_at=now))
    return token


def test_first_bind_issues_exactly_one_fixed_cookie():
    app, storage = _app()
    c = _browser(app)
    assert _owner_cookies(c.get("/api/scenarios")) == []     # 首訪讀取不簽
    r = c.post("/api/scenarios", json=NEW)
    assert r.status_code == 201
    [header] = _owner_cookies(r)
    assert _max_age(header) == MAX_AGE
    assert r.headers["x-oc-owner-bound"] == "1"
    assert len(storage.list_owners()) == 1
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    assert storage.get_browser_identity(token).cookie_issued_at is not None


def test_ordinary_requests_never_reissue_the_cookie_or_mint_an_owner():
    app, storage = _app()
    c = _browser(app)
    sid = c.post("/api/scenarios", json=NEW).json()["id"]
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    owner_id = storage.resolve_owner_by_token(token)
    responses = [
        c.get("/api/scenarios"),
        c.get(f"/api/scenarios/{sid}"),
        c.post(f"/api/scenarios/{sid}/refresh", params={"manual": "true"}),
        c.patch(f"/api/scenarios/{sid}", json={
            "target_price": 131.0, "target_month": "2027-01", "notes": "edited",
            "strategies": ["vertical-spread"]}),
        c.get("/api/me/usage-summary"),
        c.get("/api/settings"),
        c.post(f"/api/scenarios/{sid}/archive"),
        c.post(f"/api/scenarios/{sid}/restore"),
        c.post("/api/scenarios", json={**NEW, "symbol": "YYY"}),
        c.get("/api/scenarios/does-not-exist"),
    ]
    for r in responses:
        assert _owner_cookies(r) == [], (r.request.method, r.request.url.path)
        assert r.headers.get("x-oc-owner-bound") == "1", r.request.url.path
    assert [r.status_code for r in responses][:-1] == [200, 200, 200, 200, 200,
                                                         200, 200, 200, 201]
    assert c.cookies.get(_OWNER_COOKIE_NAME) == token
    assert [o.owner_id for o in storage.list_owners()] == [owner_id]


def test_reload_and_a_new_tab_read_the_same_owner_and_scenarios():
    app, storage = _app()
    first = _browser(app)
    created = first.post("/api/scenarios", json=NEW).json()
    token = first.cookies.get(_OWNER_COOKIE_NAME)
    owner_id = storage.resolve_owner_by_token(token)
    # 重新整理／新分頁＝另一個 client，只帶瀏覽器存著的那顆 cookie
    tab = _browser(app, cookies={_OWNER_COOKIE_NAME: token})
    r = tab.get("/api/scenarios")
    assert [row["id"] for row in r.json()] == [created["id"]]
    assert _owner_cookies(r) == []
    assert storage.resolve_owner_by_token(token) == owner_id
    assert len(storage.list_owners()) == 1


def test_role_login_and_logout_leave_the_owner_cookie_alone():
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    login = c.post("/api/auth/login", json={"password": SU_PASSWORD})
    assert login.json() == {"role": "superuser"}
    assert _owner_cookies(login) == []
    assert _owner_cookies(c.get("/api/scenarios")) == []
    logout = c.post("/api/auth/logout")
    assert _owner_cookies(logout) == []
    assert c.get("/api/auth/status").json() == {"role": "normal"}
    assert c.cookies.get(_OWNER_COOKIE_NAME) == token
    assert len(c.get("/api/scenarios").json()) == 1
    assert len(storage.list_owners()) == 1


def test_a_legacy_sliding_cookie_keeps_working_and_is_upgraded_exactly_once():
    app, storage = _app()
    token = _legacy_identity(storage)
    c = _browser(app, cookies={_OWNER_COOKIE_NAME: token})

    first = c.get("/api/scenarios")
    [header] = _owner_cookies(first)
    assert header.split(";")[0] == f"{_OWNER_COOKIE_NAME}={token}"   # 同一顆
    assert _max_age(header) == MAX_AGE

    created = c.post("/api/scenarios", json=NEW)
    assert created.status_code == 201 and _owner_cookies(created) == []
    again = c.get("/api/scenarios")
    assert _owner_cookies(again) == []
    assert len(again.json()) == 1
    assert [o.owner_id for o in storage.list_owners()] == ["legacy-owner"]
    assert storage.list_scenarios(owner="legacy-owner")[0].id == created.json()["id"]


def test_a_bootstrap_retry_after_a_lost_bind_response_still_gets_the_cookie():
    """第一次寫入成功、回應（連同 Set-Cookie）卻沒回到瀏覽器：重試窗內帶同一
    顆 bootstrap token 重送，伺服器沿用同一個 owner 並把 cookie 補發給它。"""
    app, storage = _app()
    boot = secrets.token_urlsafe(32)
    _browser(app).post("/api/scenarios", json=NEW,
                       headers={BOOTSTRAP: boot}).raise_for_status()
    retry = _browser(app).post("/api/scenarios", json={**NEW, "symbol": "YYY"},
                               headers={BOOTSTRAP: boot})
    assert retry.status_code == 201
    [header] = _owner_cookies(retry)
    assert header.split(";")[0] == f"{_OWNER_COOKIE_NAME}={boot}"
    assert _max_age(header) == MAX_AGE
    assert len(storage.list_owners()) == 1


@pytest.mark.skipif(not os.environ.get("OC_TEST_DATABASE_URL"),
                    reason="需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
def test_legacy_cookie_upgrade_is_recorded_once_on_postgres():
    """migration 加的 `cookie_issued_at` 欄位：舊列讀回 NULL→升級一次；記錄
    存在 DB 裡，另一個 app instance 也不再重簽。"""
    import psycopg
    from api_app.storage.postgres import PostgresStorage

    dsn = os.environ["OC_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in ("scenarios", "owners", "browser_identities"):
            conn.execute(f"DELETE FROM {table}")
    pg = PostgresStorage(dsn)
    app_a, _ = _app(pg)
    app_b, _ = _app(PostgresStorage(dsn))
    token = _legacy_identity(pg)

    first = _browser(app_a, cookies={_OWNER_COOKIE_NAME: token}).get("/api/scenarios")
    assert len(_owner_cookies(first)) == 1
    other = _browser(app_b, cookies={_OWNER_COOKIE_NAME: token}).get("/api/scenarios")
    assert _owner_cookies(other) == []
    assert other.headers.get("x-oc-owner-bound") == "1"
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM owners").fetchone()[0] == 1
