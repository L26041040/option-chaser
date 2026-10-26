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
    assert s.headers.get(CRED) not in (None, local)                # 換發新隨機憑證
    summary = stale.get("/api/me/usage-summary").json()
    assert (summary["identity"], summary["identity_reason"]) == ("unknown", "self_deleted")
    # 仍帶著舊 token 寫入 → 拒絕、不綁；拿掉舊 header、用換發的憑證才會成功
    refused = stale.post("/api/scenarios", json=NEW)
    assert refused.status_code == 409 and refused.headers.get(IDENTITY) == "unknown"
    del stale.headers[CRED]
    assert stale.post("/api/scenarios", json=NEW).status_code == 201
    assert storage.resolve_owner_by_token(local) is None


def test_revoked_credentials_are_refused_and_fresh_tokens_are_unpredictable():
    """TOKEN-REPLAY-FIX-001：兩個分頁拿著同一顆作廢 token 寫入 → 都被 409 拒絕、
    都沒有 owner 被建立；兩顆換發的新憑證彼此不同、也都不是從舊 token 推導
    出來的（不可預測）。並發收斂是前端的事（Web Locks＋重送，見
    `src/credentialStore.test.ts` 與 `scripts/identity_torture.mjs`）。"""
    import hashlib, base64
    app, storage = _app()
    stale = "stale-shared-token-" + "z" * 24
    _browser(app, local=stale).post("/api/scenarios", json=NEW).raise_for_status()
    storage.delete_owner(storage.resolve_owner_by_token(stale), reason="retention_expired")
    before = len(storage.list_owners())
    tab_a, tab_b = _browser(app, local=stale), _browser(app, local=stale)   # 各自的 cookie jar
    ra = tab_a.post("/api/scenarios", json=NEW)
    rb = tab_b.post("/api/scenarios", json={**NEW, "symbol": "QQQ"})
    assert ra.status_code == rb.status_code == 409
    assert len(storage.list_owners()) == before
    fa, fb = ra.headers.get(CRED), rb.headers.get(CRED)
    derived = base64.urlsafe_b64encode(
        hashlib.sha256(b"oc-identity-rebind:" + stale.encode()).digest()).rstrip(b"=").decode()
    assert fa and fb and fa != fb and stale not in (fa, fb) and derived not in (fa, fb)
    assert storage.resolve_owner_by_token(stale) is None


def test_replaying_a_revoked_token_after_its_successor_is_bound_never_reaches_the_successor():
    """A 作廢 → 用換發的 B 建了 owner X → 再重放 A：unknown、409、又一顆新隨機
    憑證，看不到 X。接著 B 也作廢、再重放 A 與 B：一樣。撤銷不可繞過。"""
    app, storage = _app()
    a_tok = "token-a-" + "a" * 35
    victim = _browser(app, local=a_tok)
    victim.post("/api/scenarios", json=NEW).raise_for_status()
    victim.delete("/api/me").raise_for_status()                         # A 作廢（self_deleted）
    b_tok = victim.cookies.get(_OWNER_COOKIE_NAME)
    assert b_tok != a_tok
    victim.headers[CRED] = b_tok
    victim.post("/api/scenarios", json={**NEW, "symbol": "QQQ"}).raise_for_status()   # B 綁了 owner X
    x = storage.resolve_owner_by_token(b_tok)
    assert x is not None
    replay = _browser(app, local=a_tok)
    r = replay.get("/api/scenarios")
    assert r.headers.get(IDENTITY) == "unknown" and r.json() == []
    assert r.headers.get(CRED) not in (None, a_tok, b_tok)
    refused = _browser(app, local=a_tok).post("/api/scenarios", json=NEW)   # 只拿著 A 寫入
    assert refused.status_code == 409 and refused.headers.get(IDENTITY) == "unknown"
    assert refused.headers.get(CRED) not in (None, a_tok, b_tok)
    assert storage.resolve_owner_by_token(a_tok) is None
    assert len(storage.list_scenarios(owner=x)) == 1                     # X 沒有被重放者碰到
    # B 也作廢
    storage.delete_owner(x, reason="admin_deleted")
    for tok in (a_tok, b_tok):
        again = _browser(app, local=tok).get("/api/scenarios")
        assert again.headers.get(IDENTITY) == "unknown"
        assert again.headers.get(CRED) not in (None, a_tok, b_tok)
    assert storage.resolve_owner_by_token(a_tok) is None and storage.resolve_owner_by_token(b_tok) is None


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


# ---------- IRI-03：cookie 門檻式續簽 ----------

def _owner_set_cookies(resp) -> list[str]:
    return [v for k, v in resp.headers.multi_items()
            if k.lower() == "set-cookie" and v.startswith(_OWNER_COOKIE_NAME + "=")]


def _age_cookie(storage, token: str, days: float) -> None:
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    storage._browser_identities[token] = dataclasses.replace(
        storage._browser_identities[token], cookie_issued_at=when)


def test_a_resolved_cookie_is_renewed_with_the_same_token_once_it_is_30_days_old():
    app, storage = _app()
    b = _browser(app)
    bind = b.post("/api/scenarios", json=NEW)
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    assert len(_owner_set_cookies(bind)) == 1
    assert _owner_set_cookies(b.get("/api/scenarios")) == []            # 剛簽：不重簽
    _age_cookie(storage, tok, 29.5)
    assert _owner_set_cookies(b.get("/api/scenarios")) == []            # 未滿 30 天
    _age_cookie(storage, tok, 30)
    r = b.get("/api/scenarios")
    [header] = _owner_set_cookies(r)
    assert header.startswith(f"{_OWNER_COOKIE_NAME}={tok};")             # 同一顆 token
    assert "max-age=34560000" in header.lower()                           # 新的 400 天
    assert r.headers.get(IDENTITY) == "bound"
    assert _owner_set_cookies(b.get("/api/scenarios")) == []            # 續簽已記錄，不再簽
    assert b.cookies.get(_OWNER_COOKIE_NAME) == tok
    assert len(storage.list_owners()) == 1


def test_renewal_also_rides_a_404_but_never_changes_the_token_and_never_signs_pending():
    app, storage = _app()
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    _age_cookie(storage, tok, 45)
    r = b.get("/api/scenarios/does-not-exist")
    assert r.status_code == 404
    [header] = _owner_set_cookies(r)
    assert header.startswith(f"{_OWNER_COOKIE_NAME}={tok};")
    # 佔位（首訪）請求不論怎樣都不簽。
    assert _owner_set_cookies(_browser(app).get("/api/scenarios")) == []


def test_renewal_threshold_is_injectable():
    app, storage = _app(owner_cookie_renew_after_days=1)
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    _age_cookie(storage, tok, 0.5)
    assert _owner_set_cookies(b.get("/api/scenarios")) == []
    _age_cookie(storage, tok, 1)
    assert len(_owner_set_cookies(b.get("/api/scenarios"))) == 1


def test_renewal_is_recorded_in_the_database_so_another_instance_does_not_sign_again():
    import os
    import pytest
    if not os.environ.get("OC_TEST_DATABASE_URL"):
        pytest.skip("需要 OC_TEST_DATABASE_URL")
    import psycopg
    from api_app.storage.postgres import PostgresStorage
    dsn = os.environ["OC_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in ("scenarios", "owners", "browser_identities", "identity_tombstones"):
            conn.execute(f"DELETE FROM {table}")
    snap = load_snapshot(FIX)
    app_a = create_app(fetch=lambda symbol: snap, storage=PostgresStorage(dsn),
                       cron_secret="fake-cron-secret")
    app_b = create_app(fetch=lambda symbol: snap, storage=PostgresStorage(dsn),
                       cron_secret="fake-cron-secret")
    a = _browser(app_a)
    a.post("/api/scenarios", json=NEW).raise_for_status()
    tok = a.cookies.get(_OWNER_COOKIE_NAME)
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("UPDATE browser_identities SET cookie_issued_at = %s WHERE token = %s",
                     (old, tok))
    renewed = a.get("/api/scenarios")
    assert len(_owner_set_cookies(renewed)) == 1
    other = _browser(app_b).get("/api/scenarios",
                                headers={"Cookie": f"{_OWNER_COOKIE_NAME}={tok}"})
    assert _owner_set_cookies(other) == [] and other.headers.get(IDENTITY) == "bound"


# ---------- IRI-05：身分健康指標 ----------

def _totals(storage, metric: str) -> dict[str, float]:
    return {e.source: float(e.count) for e in storage.metric_summary() if e.metric == metric}


def test_identity_metrics_count_heals_unknowns_rebuilds_and_renewals():
    app, storage = _app()
    local = "metrics-local-" + "m" * 29
    b = _browser(app, local=local)
    b.post("/api/scenarios", json=NEW).raise_for_status()     # 綁定：兩腿一致，沒有補回
    assert _totals(storage, "identity_heal_cookie_from_local") == {}
    # cookie 腿不在、本機那份補回
    _browser(app, local=local).get("/api/scenarios")
    assert sum(_totals(storage, "identity_heal_cookie_from_local").values()) == 1
    # 本機儲存被清掉：前端帶著一顆新產生的 token，cookie 補回
    regenerated = TestClient(app, base_url="https://testserver",
                             cookies={_OWNER_COOKIE_NAME: local})
    regenerated.get("/api/scenarios", headers={CRED: "regenerated-" + "r" * 31})
    assert sum(_totals(storage, "identity_heal_local_from_cookie").values()) == 1
    # 完全沒帶 header 的呼叫端（curl、監控）不算遺失訊號
    TestClient(app, base_url="https://testserver",
               cookies={_OWNER_COOKIE_NAME: local}).get("/api/scenarios")
    assert sum(_totals(storage, "identity_heal_local_from_cookie").values()) == 1
    # 續簽
    _age_cookie(storage, local, 31)
    b.get("/api/scenarios")
    assert sum(_totals(storage, "identity_renew_cookie").values()) == 1
    # 作廢 → unknown（依原因計）→ 重建
    storage.delete_owner(storage.resolve_owner_by_token(local), reason="retention_expired")
    stale = _browser(app, local=local)
    stale.get("/api/scenarios")                                 # unknown
    assert stale.post("/api/scenarios", json=NEW).status_code == 409   # unknown＋拒絕
    assert _totals(storage, "identity_unknown_token") == {"retention_expired": 2.0}
    assert _totals(storage, "identity_unknown_write_refused") == {"retention_expired": 1.0}


def test_identity_metrics_are_a_noop_when_metrics_are_disabled():
    app, storage = _app(enable_metrics=False)
    local = "metrics-off-" + "o" * 31
    _browser(app, local=local).post("/api/scenarios", json=NEW).raise_for_status()
    _browser(app, local=local).get("/api/scenarios")
    assert [e for e in storage.metric_summary() if e.metric.startswith("identity_")] == []


def test_daily_digest_carries_an_identity_health_section():
    from api_app.digest import DigestSnapshot, build_digest_text
    from api_app import ops_alerts
    text = build_digest_text(DigestSnapshot(
        date="2026-10-26", owners_active=1, owners_abandoned=0,
        owners_eligible_for_hard_delete=0, owners_protected=1, owners_total=2,
        scenarios_total=3, scenarios_average_per_owner=1.5,
        cleanup_owners_deleted_today=0, cleanup_rows_deleted_today=0,
        alerts=ops_alerts.evaluate_alerts(sustained_incident_sources=(), cleanup_missed_days=0,
                                          storage_bytes=0, chain_429_count=0, chain_fetch_count=1),
        identity_unknown_today=4, identity_heals_today=2,
        identity_unknown_writes_refused_today=1, identity_cookie_renewals_today=7))
    assert "身分健康" in text
    assert "帶著已作廢憑證來的請求：4" in text and "cookie 門檻式續簽：7" in text


# ---------- IRI-06：storage 完整性守門 ----------

def _seed_main(storage, *, protected=True, role="superuser"):
    main = main_account.SEED_OWNER_PREFIX + "g" * 35
    tok = "main-device-" + "g" * 31
    storage.create_owner_with_token(
        Owner(owner_id=main, created_at="2026-01-01T00:00:00+00:00", protected=protected),
        BrowserIdentity(token=tok, owner_id=main, issued_at="2026-01-01T00:00:00+00:00",
                        last_seen_at="2026-01-01T00:00:00+00:00", role="superuser"))
    storage.set_owner_role(main, role)
    storage.set_main_account(main, now="2026-01-01T00:00:00+00:00", expected=None)
    return main, tok


def test_super_admin_cannot_delete_the_main_account_singly_or_in_a_batch():
    app, storage = _app(superadmin_password="test-only-sa-password")
    main, _ = _seed_main(storage, protected=False, role="normal")   # 連保護都拿掉了也一樣
    victim = _browser(app)
    victim.post("/api/scenarios", json=NEW).raise_for_status()
    vid = storage.resolve_owner_by_token(victim.cookies.get(_OWNER_COOKIE_NAME))
    admin = _browser(app)
    admin.post("/api/auth/login", json={"password": "test-only-sa-password"}).raise_for_status()
    single = admin.post(f"/api/superuser/owners/{main}/delete", json={"confirm_owner_id": main})
    assert single.status_code == 409
    batch = admin.post("/api/superuser/owners/batch-delete",
                       json={"owner_ids": [vid, main], "confirm_owner_ids": [main, vid]})
    assert batch.status_code == 409
    assert storage.get_owner(main) is not None and storage.get_owner(vid) is not None  # 零寫入


def test_cleanup_cron_excludes_the_main_account_even_if_unprotected_and_normal():
    app, storage = _app(anonymous_retention_days=1, anonymous_grace_period_days=1)
    main, tok = _seed_main(storage, protected=False, role="normal")
    _age_identities(storage, main, days=30)
    body = _browser(app).get("/api/cron/cleanup-abandoned-owners", headers=CRON).json()
    assert body["hard_deleted"] == 0
    assert storage.get_owner(main) is not None and storage.resolve_owner_by_token(tok) == main


def test_lock_table_orders_are_subsequences_of_one_canonical_order():
    from api_app.storage import postgres as pg_module
    from api_app.storage.postgres import PostgresStorage as PG
    canonical = pg_module._OWNER_LOCK_ORDER
    for tables in (PG._BETA_LOCK_TABLES, PG._ABSORB_LOCK_TABLES):
        positions = [canonical.index(t) for t in tables]
        assert positions == sorted(positions) and len(set(tables)) == len(tables)
    assert set(PG._BETA_LOCK_TABLES) >= {"owners", "browser_identities", "feedback",
                                        "rate_limits", "operational_metrics"}
    assert set(PG._ABSORB_LOCK_TABLES) >= {"owners", "browser_identities", "feedback", "rate_limits"}


# ---------- code review 補強：驗收逐條對應 ----------

def test_renewal_on_a_409_keeps_the_same_token():
    app, storage = _app(anonymous_max_active_scenarios=1)
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    _age_cookie(storage, tok, 31)
    r = b.post("/api/scenarios", json=NEW)                 # 撞 per-owner 額度
    assert r.status_code == 409
    [header] = _owner_set_cookies(r)
    assert header.startswith(f"{_OWNER_COOKIE_NAME}={tok};")
    assert b.cookies.get(_OWNER_COOKIE_NAME) == tok


def test_identity_metrics_are_visible_on_the_ops_endpoint():
    app, storage = _app(superadmin_password="test-only-sa-password")   # `/api/ops/metrics` 是 SA 端點
    local = "ops-visible-" + "v" * 31
    _browser(app, local=local).post("/api/scenarios", json=NEW).raise_for_status()
    _browser(app, local=local).get("/api/scenarios")       # cookie 腿從本機補回 → 一筆
    sa = _browser(app)
    sa.post("/api/auth/login", json={"password": "test-only-sa-password"}).raise_for_status()
    body = sa.get("/api/ops/metrics").json()
    assert "identity_heal_cookie_from_local" in body
    assert all(k not in str(body) for k in (local, "owner_id"))


def test_daily_digest_text_never_carries_tokens_or_owner_ids():
    from api_app.digest import DigestSnapshot, build_digest_text
    from api_app import ops_alerts
    text = build_digest_text(DigestSnapshot(
        date="2026-10-26", owners_active=1, owners_abandoned=0,
        owners_eligible_for_hard_delete=0, owners_protected=1, owners_total=2,
        scenarios_total=3, scenarios_average_per_owner=1.5,
        cleanup_owners_deleted_today=0, cleanup_rows_deleted_today=0,
        alerts=ops_alerts.evaluate_alerts(sustained_incident_sources=(), cleanup_missed_days=0,
                                          storage_bytes=0, chain_429_count=0, chain_fetch_count=1),
        identity_unknown_today=1, identity_heals_today=1,
        identity_unknown_writes_refused_today=1, identity_cookie_renewals_today=1))
    assert "owner_id" not in text and "token" not in text.lower()


def _postgres_app(**kwargs):
    import os
    import pytest
    if not os.environ.get("OC_TEST_DATABASE_URL"):
        pytest.skip("需要 OC_TEST_DATABASE_URL")
    import psycopg
    from api_app.storage.postgres import PostgresStorage
    dsn = os.environ["OC_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in ("scenarios", "owners", "browser_identities", "identity_tombstones",
                      "main_account", "superuser_audit_log"):
            conn.execute(f"DELETE FROM {table}")
    snap = load_snapshot(FIX)
    storage = PostgresStorage(dsn)
    return create_app(fetch=lambda symbol: snap, storage=storage,
                      cron_secret="fake-cron-secret", superuser_password=SU,
                      **kwargs), storage, dsn


def test_super_admin_cannot_delete_the_main_account_on_postgres():
    app, storage, _ = _postgres_app(superadmin_password="test-only-sa-password")
    main, _ = _seed_main(storage, protected=False, role="normal")
    admin = _browser(app)
    admin.post("/api/auth/login", json={"password": "test-only-sa-password"}).raise_for_status()
    r = admin.post(f"/api/superuser/owners/{main}/delete", json={"confirm_owner_id": main})
    assert r.status_code == 409
    assert storage.get_owner(main) is not None


def test_the_identity_health_audit_sql_runs_on_postgres():
    import psycopg
    _, _, dsn = _postgres_app()
    sql = open("docs/audits/identity-health-audit.sql", encoding="utf-8").read()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)          # 七段 SELECT 全部可執行（多語句、無參數）


# ---------- TOKEN-REPLAY-FIX-001 補強 ----------

def test_a_surviving_unbound_candidate_is_kept_instead_of_minting_a_new_one():
    """cookie 已作廢、但 header 是另一顆沒有墓碑的候選（別的分頁剛換發、鏡像過來
    的）：沿用它、不鑄新的——狀態仍 unknown、寫入仍 409，重送（cookie 已是它）就
    走首訪綁定。"""
    app, storage = _app()
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    dead = b.cookies.get(_OWNER_COOKIE_NAME)
    storage.delete_owner(storage.resolve_owner_by_token(dead), reason="self_deleted")
    keep = "survivor-" + "k" * 34
    r = b.get("/api/scenarios", headers={CRED: keep})
    assert r.headers.get(IDENTITY) == "unknown"
    assert b.cookies.get(_OWNER_COOKIE_NAME) == keep and CRED not in r.headers
    w = b.post("/api/scenarios", json=NEW, headers={CRED: keep})
    assert w.status_code == 201 and storage.resolve_owner_by_token(keep) is not None
    assert storage.resolve_owner_by_token(dead) is None


def test_replaying_credentials_revoked_by_logout_and_admin_delete_is_refused():
    app, storage = _app(superadmin_password="test-only-sa-password")
    main, _ = _seed_main(storage)
    dev = _browser(app)
    dev.post("/api/auth/login", json={"password": SU}).raise_for_status()
    logged_in = dev.cookies.get(_OWNER_COOKIE_NAME)
    dev.post("/api/auth/reset-role").raise_for_status()                 # 登出 → logged_out
    replay = _browser(app, local=logged_in)
    r = replay.post("/api/scenarios", json=NEW)
    assert r.status_code == 409 and r.headers.get("X-OC-Owner-Identity-Reason") == "logged_out"
    assert len(storage.list_scenarios(owner=main)) == 0 and storage.resolve_owner_by_token(logged_in) is None
    victim = _browser(app)
    victim.post("/api/scenarios", json=NEW).raise_for_status()
    vtok = victim.cookies.get(_OWNER_COOKIE_NAME)
    vid = storage.resolve_owner_by_token(vtok)
    admin = _browser(app)
    admin.post("/api/auth/login", json={"password": "test-only-sa-password"}).raise_for_status()
    admin.post(f"/api/superuser/owners/{vid}/delete", json={"confirm_owner_id": vid}).raise_for_status()
    r2 = _browser(app, local=vtok).post("/api/scenarios", json=NEW)
    assert r2.status_code == 409 and r2.headers.get("X-OC-Owner-Identity-Reason") == "admin_deleted"
    assert storage.resolve_owner_by_token(vtok) is None


def test_login_with_a_revoked_device_credential_still_binds_the_device_to_the_main_account():
    app, storage = _app()
    main, _ = _seed_main(storage)
    b = _browser(app)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    dead = b.cookies.get(_OWNER_COOKIE_NAME)
    storage.delete_owner(storage.resolve_owner_by_token(dead), reason="retention_expired")
    r = b.post("/api/auth/login", json={"password": SU})
    assert r.status_code == 200 and r.headers.get(IDENTITY) == "bound"
    assert storage.resolve_owner_by_token(b.cookies.get(_OWNER_COOKIE_NAME)) == main
