"""OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001：跨裝置的單一主帳號。

票面驗收：任何裝置輸入正確的 SU 密碼都登入同一個主帳號、不建立第二個 SU
owner；SA 密碼也登入主帳號，但 SU／SA 權限依每顆登入憑證各自判斷；一個
owner 綁多顆裝置憑證；已有匿名劇本的裝置登入時安全併入、不遺失；一般匿名
使用者照舊；cookie、本機憑證同步、重新登入的憑證輪替正確；三個獨立瀏覽器
登入同一個 SU 帳號，劇本一致、權限正確、owner 不增加。

每個 `Device` 是一個獨立的瀏覽器：自己的 cookie jar（HttpOnly
`__Host-oc_owner`）＋自己的本機憑證副本——每個請求帶在 `X-OC-Credential`，
回應交回新值就存起來，比照 `src/api.ts` 的 `send()`。記憶體與 Postgres
兩個後端都跑。
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets

import pytest
from fastapi.testclient import TestClient

from api_app import main_account
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import (BrowserIdentity, DataSourceSettings, Owner,
                             ProviderCredential, ProviderVerification,
                             ResultRecord, UsageSetting)
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
SU = "test-only-su-password"
SA = "test-only-sa-password"
CRED = "X-OC-Credential"
NOW = "2026-10-25T00:00:00+00:00"
# Production 主帳號的形狀：owner_id 以 seed 前綴開頭、role=superuser、受保護。
MAIN = main_account.SEED_OWNER_PREFIX + "x" * 35
MAIN_TOKEN = "main-existing-device-" + "m" * 30
_TABLES = ("scenarios", "results", "current_results", "snapshots", "events",
           "diagnostics", "owner_settings", "owner_credentials",
           "owner_verifications", "owners", "browser_identities", "role_sessions",
           "superuser_audit_log", "rate_limits", "operational_metrics", "feedback",
           "main_account", "owner_merge_archive")


@pytest.fixture(params=["memory", "postgres"])
def db(request):
    if request.param == "memory":
        yield MemoryStorage()
        return
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL 才能驗證 PostgresStorage")
    import psycopg

    from api_app.storage.postgres import PostgresStorage
    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(_TABLES) + " RESTART IDENTITY")
    yield st


def _app(db):
    snap = load_snapshot(FIX)
    return create_app(fetch=lambda symbol: snap, storage=db,
                      cron_secret="fake-cron-secret", superuser_password=SU,
                      superadmin_password=SA)


class Device:
    """一個獨立的瀏覽器（見檔頭）。"""

    def __init__(self, app, local: str | None = None):
        self.client = TestClient(app, base_url="https://testserver")
        self.local = local or secrets.token_urlsafe(32)

    def call(self, method: str, path: str, **kwargs):
        r = self.client.request(method, path, headers={CRED: self.local}, **kwargs)
        echoed = r.headers.get(CRED)
        if echoed:
            self.local = echoed
        return r

    def login(self, password: str):
        return self.call("POST", "/api/auth/login", json={"password": password})

    def role(self) -> str:
        return self.call("GET", "/api/auth/status").json()["role"]

    def scenario_ids(self) -> set[str]:
        return {row["id"] for row in self.call(
            "GET", "/api/scenarios", params={"include_archived": True}).json()}

    def create(self) -> str:
        r = self.call("POST", "/api/scenarios", json=NEW)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    @property
    def cookie(self) -> str | None:
        return self.client.cookies.get(_OWNER_COOKIE_NAME)


def _seed_main(db, scenarios: int = 3) -> list[str]:
    """Production 主帳號：已經有劇本、有一台既有裝置（OWNER-CONSOLIDATION 之後
    那台，憑證權限由冷啟動回填成 superuser）；`main_account` 對應還沒建立。"""
    db.create_owner_with_token(
        Owner(owner_id=MAIN, created_at=NOW, protected=True),
        BrowserIdentity(token=MAIN_TOKEN, owner_id=MAIN, issued_at=NOW,
                        last_seen_at=NOW))
    db.set_owner_role(MAIN, "superuser")
    db.set_credential_role(MAIN_TOKEN, "superuser")
    ids = []
    for i in range(scenarios):
        from api_app.storage import Scenario
        sid = f"main-{i}"
        db.create_scenario(Scenario(
            id=sid, symbol="XYZ", direction="bullish", target_price=130.0,
            target_month="2027-01", notes="", strategies=("vertical-spread",),
            created_at=NOW, archived_at=NOW if i == 0 else None, owner_id=MAIN))
        ids.append(sid)
    return ids


def _owners(db) -> set[str]:
    return {o.owner_id for o in db.list_owners()}


def _archive(db) -> list[dict]:
    if isinstance(db, MemoryStorage):
        return [dict(a) for a in db._owner_merge_archive]
    with db._connect() as conn:
        return [{"source_owner_id": r[0], "target_owner_id": r[1],
                 "table_name": r[2], "row_data": r[3]} for r in conn.execute(
            "SELECT source_owner_id, target_owner_id, table_name, row_data "
            "FROM owner_merge_archive ORDER BY seq")]


# ---------- 三個獨立瀏覽器登入同一個 SU 帳號（票面第 8 點） ----------

def test_three_browsers_log_into_one_main_account(db):
    main_ids = set(_seed_main(db))
    app = _app(db)
    visitor = Device(app)                         # 不相干的匿名使用者
    visitor_sid = visitor.create()
    a = Device(app)                               # 已經有匿名劇本的裝置
    a_ids = {a.create(), a.create()}
    a_owner = db.resolve_owner_by_token(a.local)
    b, c = Device(app), Device(app)               # 全新的兩台裝置
    owners_before = _owners(db)
    assert owners_before == {MAIN, visitor_owner(db, visitor), a_owner}

    assert a.login(SU).json() == {"role": "superuser"}
    assert b.login(SU).json() == {"role": "superuser"}
    assert c.login(SA).json() == {"role": "superadmin"}

    # 主帳號以完整 owner_id 持久對應；沒有第二個 SU owner，A 的匿名 owner
    # 併進主帳號後消失——owner 只少不多。
    assert db.get_main_account() == MAIN
    assert _owners(db) == {MAIN, visitor_owner(db, visitor)}
    assert [o.owner_id for o in db.list_owners() if o.role != "normal"] == [MAIN]
    # 三台裝置看到同一份劇本：主帳號原本的＋A 帶進來的。
    everything = main_ids | a_ids
    for device in (a, b, c):
        assert device.scenario_ids() == everything
    # 權限依各自登入的密碼：SU、SU、SA；SA 專屬端點只有 C 進得去。
    assert (a.role(), b.role(), c.role()) == ("superuser", "superuser", "superadmin")
    for device, status in ((a, 401), (b, 401), (c, 200)):
        assert device.call("GET", "/api/superuser/owners").status_code == status
    # 一台新增，另外兩台立刻看得到。
    sid = b.create()
    assert sid in a.scenario_ids() and sid in c.scenario_ids()
    # 主帳號原本那台裝置照常可用；不相干的匿名使用者完全不受影響。
    old = Device(app, local=MAIN_TOKEN)
    assert old.role() == "superuser" and sid in old.scenario_ids()
    assert visitor.role() == "normal"
    assert visitor.scenario_ids() == {visitor_sid}


def visitor_owner(db, device: Device) -> str:
    return db.resolve_owner_by_token(device.local)


def test_one_owner_holds_one_credential_per_device(db):
    _seed_main(db)
    app = _app(db)
    devices = [Device(app) for _ in range(3)]
    for d in devices:
        d.login(SU)
    tokens = {d.local for d in devices} | {MAIN_TOKEN}
    assert len(tokens) == 4
    assert {db.resolve_owner_by_token(t) for t in tokens} == {MAIN}
    # cookie 與本機副本是同一顆。
    assert all(d.cookie == d.local for d in devices)


# ---------- 合併、輪替、登出 ----------

def test_login_merges_the_devices_anonymous_data_without_loss(db):
    _seed_main(db, scenarios=1)
    app = _app(db)
    a = Device(app)
    sid = a.create()
    owner = db.resolve_owner_by_token(a.local)
    for ts in ("2026-10-01T00:00:00+00:00", "2026-10-02T00:00:00+00:00"):
        db.save_result(ResultRecord(sid, ts, None, best_return=0.4, owner_id=owner))
        db.save_snapshot(sid, ts, {"at": ts}, owner_id=owner)
    db.save_current_result(ResultRecord(sid, "2026-10-02T00:00:00+00:00",
                                        {"results": [], "sid": sid},
                                        best_return=0.4, owner_id=owner))
    a.login(SU)
    assert db.get_scenario(sid, owner=MAIN) is not None
    assert len(db.result_history(sid, owner=MAIN)) == 2
    assert db.latest_result(sid, owner=MAIN).view == {"results": [], "sid": sid}
    assert db.get_snapshot(sid, "2026-10-01T00:00:00+00:00", owner=MAIN) == {
        "at": "2026-10-01T00:00:00+00:00"}
    assert db.list_events(scenario_id=sid, owner=MAIN)
    assert db.lineage_report(MAIN).ok
    assert db.get_owner(owner) is None
    assert sid in a.scenario_ids()


def test_merge_keeps_the_main_accounts_settings_and_archives_conflicts(db):
    _seed_main(db, scenarios=0)
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="default"),
        historical_iv=UsageSetting(mode="custom", provider="marketdata-app"),
        updated_at=NOW, owner_id=MAIN))
    db.save_credential(ProviderCredential(provider="marketdata-app",
                                          token="main-md-secret",
                                          updated_at=NOW, owner_id=MAIN))
    app = _app(db)
    a = Device(app)
    a.create()
    owner = db.resolve_owner_by_token(a.local)
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="custom", provider="fmp"),
        historical_iv=UsageSetting(mode="default"), updated_at=NOW, owner_id=owner))
    for provider, token in (("marketdata-app", "anon-md-secret"),
                            ("fmp", "anon-fmp-secret")):
        db.save_credential(ProviderCredential(provider=provider, token=token,
                                              updated_at=NOW, owner_id=owner))
        db.save_verification(ProviderVerification(provider=provider, ok=True,
                                                  reason=None, checked_at=NOW,
                                                  owner_id=owner))
    a.login(SU)
    bundle = db.owner_settings_bundle(MAIN)
    assert bundle.settings.historical_iv.provider == "marketdata-app"    # 主帳號優先
    assert bundle.credentials["marketdata-app"].token == "main-md-secret"
    assert bundle.credentials["fmp"].token == "anon-fmp-secret"         # 沒衝突就搬
    assert set(bundle.verifications) == {"fmp"}    # 不跟主帳號的 credential 配錯對
    archived = {(a["table_name"], a["row_data"].get("provider"))
                for a in _archive(db)}
    assert archived == {("owner_settings", None),
                        ("owner_credentials", "marketdata-app"),
                        ("owner_verifications", "marketdata-app")}
    assert all(a["source_owner_id"] == owner and a["target_owner_id"] == MAIN
               for a in _archive(db))
    assert any("anon-md-secret" in json.dumps(a["row_data"]) for a in _archive(db))


def test_relogin_rotates_the_credential_and_retires_the_old_one(db):
    _seed_main(db)
    app = _app(db)
    a = Device(app)
    a.login(SU)
    first = a.local
    r = a.login(SU)
    assert r.json() == {"role": "superuser"}
    assert a.local != first and a.cookie == a.local
    assert db.resolve_owner_by_token(first) is None
    assert db.resolve_owner_by_token(a.local) == MAIN
    assert Device(app, local=first).role() == "normal"
    assert _owners(db) == {MAIN}


def test_su_and_sa_credentials_never_contaminate_each_other(db):
    _seed_main(db)
    app = _app(db)
    su, sa = Device(app), Device(app)
    sa.login(SA)
    su.login(SU)
    su.login(SU)
    assert (su.role(), sa.role()) == ("superuser", "superadmin")
    sa.login(SU)                                  # 這台改用 SU 密碼登入
    assert (su.role(), sa.role()) == ("superuser", "superuser")
    sa.login(SA)
    assert sa.call("POST", "/api/auth/reset-role").json() == {"role": "normal"}
    assert sa.role() == "normal" and sa.scenario_ids() == set()
    assert su.role() == "superuser" and su.scenario_ids()
    assert _owners(db) == {MAIN}


def test_reset_logs_only_this_device_out_and_it_becomes_a_fresh_visitor(db):
    ids = set(_seed_main(db))
    app = _app(db)
    a, b = Device(app), Device(app)
    a.login(SU)
    b.login(SU)
    token = a.local
    a.call("POST", "/api/auth/reset-role")
    assert a.local != token and a.cookie == a.local
    assert db.resolve_owner_by_token(token) is None
    assert db.resolve_owner_by_token(a.local) is None        # 還沒綁定
    assert a.scenario_ids() == set()
    own = a.create()                                        # 一般匿名功能照舊
    assert a.scenario_ids() == {own}
    assert db.resolve_owner_by_token(a.local) not in (None, MAIN)
    assert b.scenario_ids() == ids and b.role() == "superuser"


def test_wrong_password_neither_creates_nor_changes_anything(db):
    _seed_main(db)
    app = _app(db)
    d = Device(app)
    assert d.login("nope").status_code == 401
    assert _owners(db) == {MAIN} and db.get_main_account() is None
    assert d.role() == "normal" and d.scenario_ids() == set()


def test_main_account_cannot_be_deleted_from_any_device(db):
    ids = set(_seed_main(db))
    app = _app(db)
    a = Device(app)
    a.login(SU)
    r = a.call("DELETE", "/api/me")
    assert r.status_code == 409
    assert {s.id for s in db.list_scenarios(owner=MAIN, include_archived=True)} == ids
    visitor = Device(app)
    visitor.create()
    assert visitor.call("DELETE", "/api/me").status_code == 204


def test_anonymous_users_need_no_registration_and_stay_separate(db):
    _seed_main(db)
    app = _app(db)
    x, y = Device(app), Device(app)
    sx, sy = x.create(), y.create()
    assert x.scenario_ids() == {sx} and y.scenario_ids() == {sy}
    assert x.role() == y.role() == "normal"
    assert db.get_main_account() is None          # 匿名使用不碰主帳號


# ---------- 主帳號的對應 ----------

def test_main_account_mapping_is_persisted_with_the_full_owner_id(db):
    _seed_main(db)
    app = _app(db)
    Device(app).login(SU)
    assert db.get_main_account() == MAIN
    # 之後就算又出現一個同前綴的 owner，對應也不會變。
    db.create_owner_with_token(
        Owner(owner_id=main_account.SEED_OWNER_PREFIX + "other", created_at=NOW),
        BrowserIdentity(token="tok-other-" + "o" * 30,
                        owner_id=main_account.SEED_OWNER_PREFIX + "other",
                        issued_at=NOW, last_seen_at=NOW))
    Device(app).login(SA)
    assert db.get_main_account() == MAIN


def test_fresh_deployment_designates_the_first_device_and_later_ones_join(db):
    app = _app(db)
    first, second = Device(app), Device(app)
    sid = first.create()
    second_sid = second.create()
    first.login(SU)
    main = db.get_main_account()
    assert main is not None and db.get_owner(main).protected is True
    second.login(SA)
    assert _owners(db) == {main}
    assert first.scenario_ids() == second.scenario_ids() == {sid, second_sid}


def test_a_stale_mapping_is_replaced_instead_of_locking_everyone_out(db):
    _seed_main(db)
    db.set_main_account("deleted-owner", now=NOW, expected=None)
    app = _app(db)
    d = Device(app)
    d.login(SU)
    assert db.get_main_account() == MAIN
    assert d.scenario_ids()


def test_seed_prefix_is_matched_literally(db):
    """`_` 不是萬用字元：`Tcf2xBUR…` 不能被當成主帳號。"""
    look_alike = main_account.SEED_OWNER_PREFIX.replace("_", "x") + "y" * 30
    db.create_owner_with_token(
        Owner(owner_id=look_alike, created_at=NOW),
        BrowserIdentity(token="tok-look-" + "l" * 30, owner_id=look_alike,
                        issued_at=NOW, last_seen_at=NOW))
    assert db.owners_with_id_prefix(main_account.SEED_OWNER_PREFIX) == []


# ---------- 冷啟動回填（Postgres） ----------

def test_cold_start_backfills_existing_privileged_credentials():
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL")
    import psycopg

    from api_app.storage import postgres as pg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        pg.PostgresStorage(TEST_DB_URL)._ensure_schema()
        conn.execute("TRUNCATE " + ", ".join(_TABLES) + " RESTART IDENTITY")
        conn.execute("INSERT INTO owners (owner_id, created_at, role) VALUES "
                     "('priv', %s, 'superuser'), ('anon', %s, 'normal')", (NOW, NOW))
        conn.execute("INSERT INTO browser_identities (token, owner_id, issued_at, "
                     "last_seen_at) VALUES ('t-priv', 'priv', %s, %s), "
                     "('t-anon', 'anon', %s, %s)", (NOW, NOW, NOW, NOW))
        pg._schema_ready.discard(TEST_DB_URL)
        pg.PostgresStorage(TEST_DB_URL)._ensure_schema()
        roles = dict(conn.execute(
            "SELECT token, role FROM browser_identities").fetchall())
    assert roles == {"t-priv": "superuser", "t-anon": None}


# ---------- 第 9 點：同一份後端的指紋 ----------

def test_health_reports_a_backend_fingerprint_without_secrets(monkeypatch):
    dsn = "postgresql://oc_user:super-secret-pw@ep-abc.us-east-1.aws.neon.tech/neondb?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "0123456789abcdef")
    body = TestClient(_app(MemoryStorage())).get("/api/health").json()
    expected = hashlib.sha256(b"ep-abc.us-east-1.aws.neon.tech/neondb").hexdigest()[:12]
    assert body["backend"] == {"env": "production", "commit": "0123456",
                               "database": expected}
    text = json.dumps(body)
    for secret in ("super-secret-pw", "oc_user", "ep-abc", "neon.tech"):
        assert secret not in text
