"""CLAUDE-BETA-LAUNCH-FINAL-001：封測前最後一批功能的 HTTP＋儲存層驗證。

- A：Super Admin 批次刪除（protected 守門、單一交易）與 Beta Reset。

記憶體與 Postgres 兩個後端都跑（Postgres 需要 `OC_TEST_DATABASE_URL`）。
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from _role_session import superadmin_cookies, superuser_cookies
from api_app.clock import ny_today
from api_app.main import create_app
from api_app.storage import (RETIRED_TABLES, DataSourceSettings,
                             ProviderCredential, ProviderVerification,
                             RateCacheEntry, RateLimitBucket, SuperUserAuditEvent,
                             UsageSetting)
from api_app.storage.memory import MemoryStorage
from api_app.superuser import ROLE_COOKIE_NAME
from option_chaser.data.snapshot import load_snapshot

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
TS = "2026-09-28T00:00:00+00:00"
TOK_PROTECTED = "tok-protected-" + "p" * 30
TOK_BETA_1 = "tok-beta-one-" + "a" * 30
TOK_BETA_2 = "tok-beta-two-" + "b" * 30


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
        conn.execute("DROP TABLE IF EXISTS " + ", ".join(RETIRED_TABLES))
        conn.execute(
            "TRUNCATE scenarios, results, current_results, snapshots, events, "
            "diagnostics, owner_settings, owner_credentials, owner_verifications, "
            "owners, browser_identities, role_sessions, superuser_audit_log, "
            "rate_limits, operational_metrics, rate_cache RESTART IDENTITY")
    yield st


def _client(db, *, cookies: dict[str, str] | None = None,
            owner_token: str | None = None) -> TestClient:
    snap = load_snapshot(FIX)
    client = TestClient(create_app(fetch=lambda symbol: snap, storage=db),
                        base_url="https://testserver", cookies=cookies or {})
    if owner_token:
        client.cookies.set("__Host-oc_owner", owner_token)
    return client


def _owner_with_scenario(db, token: str) -> str:
    """走一般 cookie 流程建一個劇本（連帶結果、快照、事件），回傳 owner_id。"""
    client = _client(db, owner_token=token)
    created = client.post("/api/scenarios", json=NEW)
    created.raise_for_status()
    client.post(f"/api/scenarios/{created.json()['id']}/refresh").raise_for_status()
    owner_id = db.resolve_owner_by_token(token)
    assert owner_id is not None
    return owner_id


def _give_provider_settings(db, owner_id: str) -> None:
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="custom", provider="marketdata"),
        historical_iv=UsageSetting(mode="default"),
        updated_at=TS, owner_id=owner_id))
    db.save_credential(ProviderCredential(
        provider="marketdata", token="secret-" + owner_id[:6],
        updated_at=TS, owner_id=owner_id))
    db.save_verification(ProviderVerification(
        provider="marketdata", ok=True, reason=None, checked_at=TS,
        owner_id=owner_id))


def _seed_world(db) -> dict[str, str]:
    """一個 protected owner（Owner 自己）＋兩個封測 owner，全部都有劇本；
    外加 metrics、rate limits、shared cache 與一筆既有 audit。"""
    protected = _owner_with_scenario(db, TOK_PROTECTED)
    db.set_owner_protected(protected, True)
    _give_provider_settings(db, protected)
    beta_1 = _owner_with_scenario(db, TOK_BETA_1)
    _give_provider_settings(db, beta_1)
    beta_2 = _owner_with_scenario(db, TOK_BETA_2)
    today = ny_today().isoformat()
    db.record_metric("chain_fetch_count", today, count=5)
    db.record_metric("cold_miss_count", today, count=2)
    db.record_metric("chain_fetch_count", "2026-09-01", count=3)
    db.rate_limit_consume([
        RateLimitBucket("owner_vendor", beta_1, 60, 0, 10),
        RateLimitBucket("login", "some-source", 60, 0, 10)])
    db.save_rate_cache(RateCacheEntry(fetched_at=TS, curve=None, note="shared"))
    db.append_audit_event(SuperUserAuditEvent(
        event_id="earlier", ts=TS, actor="superadmin", action="set_owner_protected",
        target_owner_id=protected, detail={"protected": True}))
    return {"protected": protected, "beta_1": beta_1, "beta_2": beta_2}


def _reset(db, cookies, confirm="Reset"):
    return _client(db, cookies=cookies).post(
        "/api/superuser/reset-beta-data", json={"confirm": confirm})


# ---------- A2：Beta Reset ----------


@pytest.mark.parametrize("role", ["normal", "superuser"])
def test_reset_is_forbidden_below_superadmin(db, role):
    ids = _seed_world(db)
    cookies = superuser_cookies(db) if role == "superuser" else {}
    assert _reset(db, cookies).status_code == 401
    assert db.get_owner(ids["beta_1"]) is not None
    assert db.list_scenarios(owner=ids["beta_1"])


@pytest.mark.parametrize("confirm", ["reset", "RESET", "Reset ", " Reset", "", "重設"])
def test_reset_rejects_anything_but_the_exact_word(db, confirm):
    ids = _seed_world(db)
    before = len(db.list_audit_events())
    r = _reset(db, superadmin_cookies(db), confirm=confirm)
    assert r.status_code == 400
    assert db.get_owner(ids["beta_1"]) is not None
    assert db.list_scenarios(owner=ids["protected"])
    assert len(db.list_audit_events()) == before


def test_reset_clears_beta_data_and_keeps_protected_owner_config(db):
    ids = _seed_world(db)
    sa_cookies = superadmin_cookies(db)
    fuse_today = db.metric_total("chain_fetch_count", ny_today().isoformat())
    r = _reset(db, sa_cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reset"] is True
    counts = body["counts"]
    assert counts["owners"] == 2
    assert counts["scenarios"] == 3
    assert counts["results"] >= 3 and counts["snapshots"] >= 3
    assert counts["owner_credentials"] == 1
    assert counts["rate_limits"] >= 2
    # 今天的 chain_fetch_count（vendor fuse 真相來源）留著，其他 metric 清掉。
    assert counts["operational_metrics"] >= 2

    # 非 protected owner 整個消失（含 browser identity 與 provider 設定）。
    for key in ("beta_1", "beta_2"):
        assert db.get_owner(ids[key]) is None
        assert db.list_scenarios(owner=ids[key], include_archived=True) == []
    assert db.resolve_owner_by_token(TOK_BETA_1) is None
    assert db.get_credential("marketdata", owner=ids["beta_1"]) is None
    assert db.get_settings(owner=ids["beta_1"]) is None

    # protected owner：本人、身份、provider 設定全保留；劇本資料清空。
    protected = db.get_owner(ids["protected"])
    assert protected is not None and protected.protected
    assert protected.last_activity_at is None
    assert db.resolve_owner_by_token(TOK_PROTECTED) == ids["protected"]
    assert db.get_credential("marketdata", owner=ids["protected"]) is not None
    assert db.get_settings(owner=ids["protected"]) is not None
    assert db.get_verification("marketdata", owner=ids["protected"]) is not None
    assert db.list_scenarios(owner=ids["protected"], include_archived=True) == []
    assert db.latest_summaries(owner=ids["protected"]) == {}

    # shared cache、今天的 fuse 計數、role session、audit 全保留；audit 多一筆。
    assert db.get_rate_cache() is not None
    assert db.metric_total("chain_fetch_count", ny_today().isoformat()) == fuse_today
    assert db.metric_total("chain_fetch_count", "2026-09-01") == 0
    assert db.metric_total("cold_miss_count", ny_today().isoformat()) == 0
    assert db.resolve_role_session(sa_cookies[ROLE_COOKIE_NAME]) is not None
    actions = [e.action for e in db.list_audit_events()]
    assert actions[0] == "reset_beta_data" and "set_owner_protected" in actions
    assert db.list_audit_events()[0].detail == {"deleted_rows": counts}
    # 回應只有列數，不帶 owner_id 或 credential。
    assert ids["protected"] not in r.text and "secret-" not in r.text


def test_reset_keeps_the_operators_session_usable(db):
    _seed_world(db)
    sa_cookies = superadmin_cookies(db)
    assert _reset(db, sa_cookies).status_code == 200
    client = _client(db, cookies=sa_cookies)
    assert client.get("/api/auth/status").json() == {"role": "superadmin"}
    assert client.get("/api/superuser/owners").status_code == 200


def test_second_reset_is_a_safe_no_op(db):
    _seed_world(db)
    sa_cookies = superadmin_cookies(db)
    assert _reset(db, sa_cookies).status_code == 200
    r = _reset(db, sa_cookies)
    assert r.status_code == 200
    assert set(r.json()["counts"].values()) == {0}


def test_reset_rolls_back_everything_when_the_audit_write_fails(db, monkeypatch):
    ids = _seed_world(db)
    sa_cookies = superadmin_cookies(db)

    def boom(event):
        raise RuntimeError("audit store down")

    cold_before = db.metric_total("cold_miss_count", ny_today().isoformat())
    monkeypatch.setattr(db, "append_audit_event", boom)
    client = TestClient(create_app(fetch=lambda s: load_snapshot(FIX), storage=db),
                        base_url="https://testserver", cookies=sa_cookies,
                        raise_server_exceptions=False)
    r = client.post("/api/superuser/reset-beta-data", json={"confirm": "Reset"})
    assert r.status_code == 500
    assert db.get_owner(ids["beta_1"]) is not None
    assert db.list_scenarios(owner=ids["beta_2"])
    assert db.list_scenarios(owner=ids["protected"])
    assert db.metric_total("cold_miss_count", ny_today().isoformat()) == cold_before


# ---------- A1：批次刪除 ----------


def _batch_delete(db, cookies, owner_ids):
    return _client(db, cookies=cookies).post(
        "/api/superuser/owners/batch-delete",
        json={"owner_ids": owner_ids, "confirm_owner_ids": owner_ids})


def test_batch_delete_refuses_protected_owners_with_zero_writes(db):
    ids = _seed_world(db)
    before = len(db.list_audit_events())
    r = _batch_delete(db, superadmin_cookies(db),
                      [ids["beta_1"], ids["protected"], ids["beta_2"]])
    assert r.status_code == 409
    assert db.get_owner(ids["beta_1"]) is not None
    assert db.get_owner(ids["beta_2"]) is not None
    assert db.get_owner(ids["protected"]) is not None
    assert len(db.list_audit_events()) == before


def test_batch_delete_removes_every_selected_owner_in_one_go(db):
    ids = _seed_world(db)
    r = _batch_delete(db, superadmin_cookies(db), [ids["beta_1"], ids["beta_2"]])
    assert r.status_code == 200
    assert set(r.json()["deleted"]) == {ids["beta_1"], ids["beta_2"]}
    assert db.get_owner(ids["beta_1"]) is None
    assert db.get_owner(ids["beta_2"]) is None
    assert db.get_owner(ids["protected"]) is not None
    audited = [e for e in db.list_audit_events() if e.action == "batch_delete_owner"]
    assert {e.target_owner_id for e in audited} == {ids["beta_1"], ids["beta_2"]}


def test_batch_delete_is_all_or_nothing(db, monkeypatch):
    ids = _seed_world(db)
    sa_cookies = superadmin_cookies(db)
    real = db.delete_owner
    calls = []

    def flaky(owner_id):
        calls.append(owner_id)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real(owner_id)

    monkeypatch.setattr(db, "delete_owner", flaky)
    client = TestClient(create_app(fetch=lambda s: load_snapshot(FIX), storage=db),
                        base_url="https://testserver", cookies=sa_cookies,
                        raise_server_exceptions=False)
    targets = [ids["beta_1"], ids["beta_2"]]
    r = client.post("/api/superuser/owners/batch-delete",
                    json={"owner_ids": targets, "confirm_owner_ids": targets})
    assert r.status_code == 500
    assert db.get_owner(ids["beta_1"]) is not None
    assert db.list_scenarios(owner=ids["beta_1"])
    assert not [e for e in db.list_audit_events() if e.action == "batch_delete_owner"]


@pytest.mark.parametrize("role", ["normal", "superuser"])
def test_batch_delete_is_forbidden_below_superadmin(db, role):
    ids = _seed_world(db)
    cookies = superuser_cookies(db) if role == "superuser" else {}
    assert _batch_delete(db, cookies, [ids["beta_1"]]).status_code == 401
    assert db.get_owner(ids["beta_1"]) is not None
