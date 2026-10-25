"""OPTION-CHASER-IDENTITY-RELIABILITY-IMPROVEMENT-001（IRI-04）：身分墓碑讓
「以前有過身分、現在不認得」在每一條作廢路徑上都被訊號出來，而且下一次寫入
鑄的是全新憑證——舊 token 永不重綁。

路徑：retention 清理（有資料／空 owner）、使用者自刪、匿名裝置登入主帳號
（併入）、主帳號裝置登出、重新登入輪替。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_app import main_account
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import BrowserIdentity, Owner
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
SU = "test-only-su-password"
CRED = "X-OC-Credential"
IDENTITY = "X-OC-Owner-Identity"
CRON = {"Authorization": "Bearer fake-cron-secret"}


def _app(**kwargs):
    snap = load_snapshot(FIX)
    storage = MemoryStorage()
    return create_app(fetch=lambda symbol: snap, storage=storage,
                      cron_secret="fake-cron-secret", superuser_password=SU,
                      **kwargs), storage


def _browser(app, *, local=None) -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    if local:
        c.headers[CRED] = local
    return c


def _age_identities(storage, owner_id: str, days: float) -> None:
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for tok, bi in list(storage._browser_identities.items()):
        if bi.owner_id == owner_id:
            storage._browser_identities[tok] = dataclasses.replace(bi, last_seen_at=when)


def _state(client, **headers) -> str:
    return client.get("/api/scenarios", headers=headers).headers.get(IDENTITY)


def test_retention_cleanup_leaves_a_tombstone_and_the_browser_reads_unknown():
    app, storage = _app(anonymous_retention_days=1, anonymous_grace_period_days=1)
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    oid = storage.resolve_owner_by_token(tok)
    _age_identities(storage, oid, days=3)
    body = b.get("/api/cron/cleanup-abandoned-owners", headers=CRON).json()
    assert body["hard_deleted"] == 1 and body["empty_owners_deleted"] == 0
    assert storage.lookup_identity_tombstone(tok) == "retention_expired"
    assert _state(b) == "unknown"
    w = b.post("/api/scenarios", json=NEW)
    assert w.status_code == 201 and b.cookies.get(_OWNER_COOKIE_NAME) != tok


def test_empty_owner_cleanup_is_its_own_reason():
    app, storage = _app(anonymous_empty_owner_retention_days=1)
    tok = "empty-owner-token-" + "e" * 25
    storage.claim_browser_token(tok, Owner(owner_id="empty-owner", created_at="2026-01-01T00:00:00+00:00"),
                                now="2026-01-01T00:00:00+00:00")
    _age_identities(storage, "empty-owner", days=2)
    _browser(app).get("/api/cron/cleanup-abandoned-owners", headers=CRON).raise_for_status()
    assert storage.lookup_identity_tombstone(tok) == "empty_owner_cleanup"
    assert _state(_browser(app), **{CRED: tok}) == "unknown"


def test_self_delete_tombstones_the_credential_and_replaces_both_legs_at_once():
    """`DELETE /api/me` 回應就把兩腿換成一顆全新、還沒綁定的憑證（跟登出主
    帳號同一套）：瀏覽器不會帶著作廢的 token 繼續走，下一次是乾淨的首訪。"""
    app, storage = _app()
    local = "self-delete-local-" + "s" * 25
    b = _browser(app, local=local)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    assert b.cookies.get(_OWNER_COOKIE_NAME) == local
    r = b.delete("/api/me")
    assert r.status_code == 204
    assert storage.lookup_identity_tombstone(local) == "self_deleted"
    fresh = r.headers.get(CRED)
    assert fresh and fresh != local and b.cookies.get(_OWNER_COOKIE_NAME) == fresh
    assert r.headers.get("X-OC-Owner-Bound") is None          # 前端據此重置分頁快取
    assert r.headers.get(IDENTITY) == "none"
    b.headers[CRED] = fresh
    assert _state(b) == "none"
    # 另一個還拿著舊憑證的分頁：以前有身分、原因是本人刪除。
    stale = _browser(app, local=local)
    s = stale.get("/api/scenarios")
    assert s.headers.get(IDENTITY) == "unknown"
    assert s.headers.get("X-OC-Owner-Identity-Reason") == "self_deleted"
    summary = stale.get("/api/me/usage-summary").json()
    assert (summary["identity"], summary["identity_reason"]) == ("unknown", "self_deleted")
    assert storage.resolve_owner_by_token(local) is None


def test_two_tabs_holding_the_same_stale_token_still_collapse_into_one_owner():
    """並發首寫的原子性不因 `unknown` 而退化：新憑證是從舊 token 決定性導出
    的，兩個分頁各自算出同一顆，`claim_browser_token()` 的 PK 收斂成一個
    owner（每個請求各自隨機就會變成兩個）。"""
    app, storage = _app()
    stale = "stale-shared-token-" + "z" * 24
    _browser(app, local=stale).post("/api/scenarios", json=NEW).raise_for_status()
    storage.delete_owner(storage.resolve_owner_by_token(stale), reason="retention_expired")
    before = len(storage.list_owners())
    tab_a, tab_b = _browser(app, local=stale), _browser(app, local=stale)   # 各自的 cookie jar
    ra = tab_a.post("/api/scenarios", json=NEW)
    rb = tab_b.post("/api/scenarios", json={**NEW, "symbol": "QQQ"})
    assert ra.status_code == rb.status_code == 201
    assert ra.headers.get(CRED) == rb.headers.get(CRED) != stale
    assert len(storage.list_owners()) == before + 1
    assert len(tab_b.get("/api/scenarios").json()) == 2       # 同一個 owner 的兩個劇本


def test_identity_exempt_routes_carry_no_identity_header():
    app, _ = _app()
    r = _browser(app).get("/api/health")
    assert IDENTITY not in r.headers and "X-OC-Owner-Bound" not in r.headers


def test_the_main_account_cannot_self_delete_and_writes_no_tombstone():
    app, storage = _app()
    main = main_account.SEED_OWNER_PREFIX + "k" * 35
    tok = "main-device-" + "k" * 31
    storage.create_owner_with_token(
        Owner(owner_id=main, created_at="2026-01-01T00:00:00+00:00", protected=True),
        BrowserIdentity(token=tok, owner_id=main, issued_at="2026-01-01T00:00:00+00:00",
                        last_seen_at="2026-01-01T00:00:00+00:00", role="superuser"))
    storage.set_owner_role(main, "superuser")
    storage.set_main_account(main, now="2026-01-01T00:00:00+00:00", expected=None)
    r = _browser(app, local=tok).delete("/api/me")
    assert r.status_code == 409
    assert storage.lookup_identity_tombstone(tok) is None
    assert storage.resolve_owner_by_token(tok) == main


def test_super_admin_delete_leaves_an_admin_deleted_tombstone():
    app, storage = _app(superadmin_password="test-only-sa-password")
    victim = _browser(app)
    victim.post("/api/scenarios", json=NEW).raise_for_status()
    vtok = victim.cookies.get(_OWNER_COOKIE_NAME)
    vid = storage.resolve_owner_by_token(vtok)
    admin = _browser(app)
    admin.post("/api/auth/login", json={"password": "test-only-sa-password"}).raise_for_status()
    r = admin.post(f"/api/superuser/owners/{vid}/delete", json={"confirm_owner_id": vid})
    assert r.status_code == 200
    assert storage.lookup_identity_tombstone(vtok) == "admin_deleted"
    s = victim.get("/api/scenarios")
    assert (s.headers.get(IDENTITY), s.headers.get("X-OC-Owner-Identity-Reason")) == ("unknown", "admin_deleted")


def test_retention_purges_tombstones_older_than_400_days_only():
    from api_app import data_lifecycle
    from api_app.storage import identity_token_hash
    app, storage = _app()
    now = datetime.now(timezone.utc)
    storage._identity_tombstones[identity_token_hash("old-" + "o" * 40)] = (
        "self_deleted", (now - timedelta(days=401)).isoformat())
    storage._identity_tombstones[identity_token_hash("new-" + "n" * 40)] = (
        "self_deleted", (now - timedelta(days=399)).isoformat())
    purged = data_lifecycle.run_retention(storage, now=now)
    assert purged["identity_tombstones"] == 1
    assert storage.lookup_identity_tombstone("old-" + "o" * 40) is None
    assert storage.lookup_identity_tombstone("new-" + "n" * 40) == "self_deleted"


def test_anonymous_device_logging_in_tombstones_its_old_credential_as_absorbed():
    app, storage = _app()
    # Production 的形狀：主帳號已經存在（Tcf2_BUR 開頭、superuser、受保護），
    # 匿名裝置登入是「併入」而不是「成為主帳號」。
    main = main_account.SEED_OWNER_PREFIX + "m" * 35
    storage.create_owner_with_token(
        Owner(owner_id=main, created_at="2026-01-01T00:00:00+00:00", protected=True),
        BrowserIdentity(token="main-device-" + "m" * 31, owner_id=main,
                        issued_at="2026-01-01T00:00:00+00:00",
                        last_seen_at="2026-01-01T00:00:00+00:00", role="superuser"))
    storage.set_owner_role(main, "superuser")
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    old = b.cookies.get(_OWNER_COOKIE_NAME)
    r = b.post("/api/auth/login", json={"password": SU})
    assert r.status_code == 200 and r.json()["role"] == "superuser"
    new = b.cookies.get(_OWNER_COOKIE_NAME)
    assert new != old
    assert storage.lookup_identity_tombstone(old) == "absorbed_into_main"
    # 另一台裝置拿著舊憑證來：以前有身分（已併入），不是首訪。
    assert _state(_browser(app), **{CRED: old}) == "unknown"
    # 主帳號裝置重新登入 → 舊憑證輪替；登出 → 作廢。
    b.post("/api/auth/login", json={"password": SU}).raise_for_status()
    assert storage.lookup_identity_tombstone(new) == "rotated"
    current = b.cookies.get(_OWNER_COOKIE_NAME)
    assert b.post("/api/auth/reset-role").json()["role"] == "normal"
    assert storage.lookup_identity_tombstone(current) == "logged_out"
    assert _state(_browser(app), **{CRED: current}) == "unknown"
