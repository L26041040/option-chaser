"""CLAUDE-DB-HYGIENE-002：一次性 Production 資料修復的端到端驗證。

模擬已知的 Production 形狀（縮小版）：Owner 真正的 target owner 已有劇本；
`solo` 有幾個 SCALE-16 之後的劇本（有 current_results）；`owner_id IS NULL`
的 SCALE-16 之前舊劇本（部分已封存）只有帶完整 `view` 的歷史結果、沒有
current_results、也沒有 fact context。跑完修復後，Owner 用自己的 cookie
走一般 API 就要看得到、用得了全部劇本；額度只擋之後的「建立」。

記憶體與 Postgres 兩個後端都跑（Postgres 需要 `OC_TEST_DATABASE_URL`）。
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from _role_session import superadmin_cookies, superuser_cookies
from api_app import data_lifecycle
from api_app.identity import SOLO_OWNER
from api_app.main import create_app
from api_app.storage import (RETIRED_TABLES, BrowserIdentity, DataSourceSettings,
                             Owner, ProviderCredential, ProviderVerification,
                             ResultRecord, Scenario, UsageSetting)
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from scripts import repair_production_data_lifecycle as repair

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TARGET = "owner-real"
TOKEN = "tok-real-" + "x" * 34            # 形狀要像真的 cookie token
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
with open(FIX, encoding="utf-8") as _f:
    SNAPSHOT = json.load(_f)          # 真的快照形狀（raw-data 端點要能解析）


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
            "rate_limits, operational_metrics RESTART IDENTITY")
    yield st


def _app(db):
    snap = load_snapshot(FIX)
    return create_app(fetch=lambda symbol: snap, storage=db,
                      cron_secret="fake-cron-secret")


def _owner_client(db) -> TestClient:
    client = TestClient(_app(db), base_url="https://testserver")
    client.cookies.set("__Host-oc_owner", TOKEN)
    return client


def _register_target(db) -> None:
    db.create_owner_with_token(
        Owner(owner_id=TARGET, created_at="2026-09-20T00:00:00+00:00"),
        BrowserIdentity(token=TOKEN, owner_id=TARGET,
                        issued_at="2026-09-20T00:00:00+00:00",
                        last_seen_at="2026-09-20T00:00:00+00:00"))


def _analyzed_view(db) -> dict:
    """跑一次真的分析拿到一份真實的 view（之後拿它當 legacy view 複製）。"""
    solo_client = TestClient(create_app(
        fetch=lambda symbol: load_snapshot(FIX), storage=db,
        identity_resolver=lambda: "probe"))
    sid = solo_client.post("/api/scenarios", json=NEW).json()["id"]
    solo_client.post(f"/api/scenarios/{sid}/refresh").raise_for_status()
    view = db.latest_result(sid, owner="probe").view
    db.archive_scenario(sid, owner="probe", ts="2026-09-01T00:00:00+00:00")
    db.delete_scenario(sid, owner="probe")
    return view


def _scenario(sid: str, owner: str | None, *, archived=False) -> Scenario:
    return Scenario(id=sid, symbol="XYZ", direction="bullish",
                    target_price=130.0, target_month="2027-01", notes="",
                    strategies=("vertical-spread",),
                    created_at="2026-08-05T00:00:00+00:00",
                    archived_at="2026-09-01T00:00:00+00:00" if archived else None,
                    owner_id=owner)


def _seed_legacy_null(db, view: dict, sid: str, *, archived=False,
                      stamps=("2026-08-06T00:00:00+00:00",
                              "2026-08-07T00:00:00+00:00")) -> None:
    """SCALE-16 之前的舊劇本：owner NULL、歷史結果帶完整 view、沒有
    fact context、沒有 current_results。"""
    db.create_scenario(_scenario(sid, None, archived=archived))
    for ts in stamps:
        db.save_result(ResultRecord(sid, ts, {**view, "analyzed_at": ts},
                                    best_return=0.5, owner_id=None))
        db.save_snapshot(sid, ts, SNAPSHOT, owner_id=None)
    db.append_event(ts=stamps[0], scenario_id=sid, event="SCENARIO_CREATED",
                    payload={}, owner_id=None)


def _seed_solo(db, view: dict, sid: str) -> None:
    """SCALE-16 之後的 solo 劇本：ledger 不帶 view、有 current_results。"""
    db.create_scenario(_scenario(sid, SOLO_OWNER))
    ts = "2026-09-10T00:00:00+00:00"
    fact = data_lifecycle.derive_fact_context(view)
    rec = ResultRecord(sid, ts, None, best_return=0.7, owner_id=SOLO_OWNER, **fact)
    db.save_result(rec)
    db.save_current_result(dataclasses.replace(rec, view=view))
    db.save_snapshot(sid, ts, SNAPSHOT, owner_id=SOLO_OWNER)


def _seed_production_shape(db, *, null_active=9, null_archived=4, solo=4,
                           target_existing=1):
    view = _analyzed_view(db)
    _register_target(db)
    for i in range(target_existing):
        db.create_scenario(_scenario(f"mine{i}", TARGET))
    for i in range(null_active):
        _seed_legacy_null(db, view, f"legacy{i}")
    for i in range(null_archived):
        _seed_legacy_null(db, view, f"legacy-archived{i}", archived=True)
    for i in range(solo):
        _seed_solo(db, view, f"solo{i}")
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="default"),
        historical_iv=UsageSetting(mode="custom", provider="marketdata-app"),
        updated_at="2026-09-01T00:00:00+00:00", owner_id=SOLO_OWNER))
    db.save_credential(ProviderCredential(
        provider="marketdata-app", token="fake-solo-token",
        updated_at="2026-09-01T00:00:00+00:00", owner_id=SOLO_OWNER))
    db.save_verification(ProviderVerification(
        provider="marketdata-app", ok=True, reason=None,
        checked_at="2026-09-01T00:00:00+00:00", owner_id=SOLO_OWNER))
    return view


def _run(db, *, confirm: bool) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = repair.run(db, target_owner_id=TARGET, confirm=confirm, now=NOW)
    return code, buf.getvalue()


# ---------- dry-run ----------

def test_dry_run_reports_the_plan_and_writes_nothing(db):
    _seed_production_shape(db)
    before = (db.table_row_counts(), db.owner_row_counts(None),
              db.owner_row_counts(SOLO_OWNER), db.owner_row_counts(TARGET))

    code, out = _run(db, confirm=False)

    assert code == 0
    assert "未帶 --confirm" in out
    assert (db.table_row_counts(), db.owner_row_counts(None),
            db.owner_row_counts(SOLO_OWNER), db.owner_row_counts(TARGET)) == before
    plan = data_lifecycle.plan(db, target_owner_id=TARGET, now=NOW)
    assert plan["null_owner_legacy"]["scenarios"] == 13
    assert plan["null_owner_legacy"]["active_scenarios"] == 9
    assert plan["solo"]["active_scenarios"] == 4
    assert plan["expected_active_scenarios_after"] == 14
    assert plan["conflicts"] == []
    assert plan["planned"]["current_results_reconstructed"] == 13
    assert plan["planned"]["fact_context_backfilled"] == 26
    assert plan["planned"]["null_lineage_rows_claimed"]["results"] == 26


def test_output_never_contains_secret_values(db):
    _seed_production_shape(db)
    _, dry = _run(db, confirm=False)
    _, real = _run(db, confirm=True)
    for out in (dry, real):
        assert "fake-solo-token" not in out
        assert TOKEN not in out


def test_missing_target_owner_is_refused(db):
    code, out = repair.run(db, target_owner_id="ghost", confirm=True, now=NOW), ""
    assert code == 2
    with pytest.raises(data_lifecycle.MaintenanceError, match="不存在"):
        data_lifecycle.execute(db, target_owner_id="ghost", now=NOW)


# ---------- --confirm ----------

def test_confirmed_run_rescues_everything_and_is_idempotent(db):
    _seed_production_shape(db)

    code, _ = _run(db, confirm=True)

    assert code == 0
    assert all(n == 0 for n in db.owner_row_counts(SOLO_OWNER).values())
    assert db.owner_row_counts(None)["scenarios"] == 0
    assert db.get_owner(TARGET).protected is True
    assert len(db.list_scenarios(owner=TARGET)) == 14
    assert len(db.list_scenarios(owner=TARGET, include_archived=True)) == 18
    assert db.lineage_report(TARGET).ok
    # 13 個舊劇本都重建了 current_results（最新那一筆、剝除過 all_candidates）
    for i in range(9):
        current = db.latest_result(f"legacy{i}", owner=TARGET)
        assert current.analyzed_at == "2026-08-07T00:00:00+00:00"
        assert current.best_return == 0.5
        assert all("all_candidates" not in r for r in current.view["results"])
        assert current.resolved_params is not None
    # legacy results.view 全部清掉、fact context 補齊
    assert db.result_view_stats() == {"with_view": 0, "missing_fact_context": 0,
                                      "clearable": 0}
    ctx = db.result_fact_context("legacy0", "2026-08-06T00:00:00+00:00")
    assert ctx.engine_version is not None and ctx.snapshot_source is not None
    # 設定／credential 跟著 solo 搬過來
    assert db.get_credential("marketdata-app", owner=TARGET) is not None

    # 重跑：安全 no-op
    assert _run(db, confirm=True)[0] == 0
    assert len(db.list_scenarios(owner=TARGET)) == 14


def test_rescued_legacy_scenarios_are_usable_through_the_normal_api(db):
    _seed_production_shape(db)
    assert _run(db, confirm=True)[0] == 0
    client = _owner_client(db)

    rows = {r["id"]: r for r in client.get("/api/scenarios").json()}
    assert len(rows) == 14
    assert rows["legacy0"]["best_return"] == 0.5          # 不是「尚未分析」
    detail = client.get("/api/scenarios/legacy0")
    assert detail.status_code == 200
    assert detail.json()["latest_result"] is not None
    assert client.get("/api/scenarios/legacy0/raw-data").status_code == 200
    # 歷史索引：fact ledger 兩筆都還在；8/06 那份快照超過 30 天、又不是
    # 最新，已被 retention 清掉——明講「原始資料不在了」，不假裝可以重播。
    history = client.get("/api/scenarios/legacy0/results").json()
    assert history == [
        {"analyzed_at": "2026-08-06T00:00:00+00:00", "raw_snapshot_available": False},
        {"analyzed_at": "2026-08-07T00:00:00+00:00", "raw_snapshot_available": True}]


# ---------- 額度：搬遷後 >10 個進行中劇本 ----------

def test_normal_owner_over_quota_keeps_using_everything_but_cannot_create(db):
    _seed_production_shape(db)
    assert _run(db, confirm=True)[0] == 0
    client = _owner_client(db)

    summary = client.get("/api/me/usage-summary").json()
    assert summary["active_scenarios"] == 14
    assert summary["max_active_scenarios"] == 10
    assert summary["quota_exempt"] is False
    assert client.get("/api/scenarios/legacy3").status_code == 200
    assert client.post("/api/scenarios/legacy3/refresh").status_code == 200
    assert client.post("/api/scenarios/legacy4/archive").status_code == 200
    r = client.post("/api/scenarios", json=NEW)
    assert r.status_code == 409
    assert "上限" in r.json()["detail"]


@pytest.mark.parametrize("cookies", [superuser_cookies, superadmin_cookies])
def test_superuser_and_superadmin_stay_quota_exempt(db, cookies):
    _seed_production_shape(db)
    assert _run(db, confirm=True)[0] == 0
    client = _owner_client(db)
    client.cookies.update(cookies(db))

    assert client.get("/api/me/usage-summary").json()["quota_exempt"] is True
    assert client.post("/api/scenarios/legacy3/refresh").status_code == 200
    assert client.post("/api/scenarios", json=NEW).status_code == 201


# ---------- fail closed ----------

def test_conflicting_settings_block_the_run_with_zero_writes(db):
    _seed_production_shape(db)
    db.save_credential(ProviderCredential(
        provider="marketdata-app", token="fake-other-token",
        updated_at="2026-09-21T00:00:00+00:00", owner_id=TARGET))
    before = (db.owner_row_counts(None), db.owner_row_counts(SOLO_OWNER),
              db.owner_row_counts(TARGET))

    code, out = _run(db, confirm=True)

    assert code == 3
    assert "owner_credentials:marketdata-app" in out
    assert "fake-other-token" not in out
    assert (db.owner_row_counts(None), db.owner_row_counts(SOLO_OWNER),
            db.owner_row_counts(TARGET)) == before
    with pytest.raises(data_lifecycle.MaintenanceError, match="沒有寫入任何資料"):
        data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)


def test_a_failure_mid_migration_rolls_back_the_whole_migration(db, monkeypatch):
    """solo 已經搬過去、NULL 劇本也救了之後才炸 → 整段 rollback。"""
    _seed_production_shape(db)
    before = (db.owner_row_counts(None), db.owner_row_counts(SOLO_OWNER),
              db.owner_row_counts(TARGET), db.get_owner(TARGET).protected)

    def boom(*_a, **_k):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(data_lifecycle, "reconstruct_current_results", boom)

    with pytest.raises(RuntimeError):
        data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)
    assert (db.owner_row_counts(None), db.owner_row_counts(SOLO_OWNER),
            db.owner_row_counts(TARGET), db.get_owner(TARGET).protected) == before


def test_unrecoverable_legacy_scenario_is_kept_and_reported(db):
    _seed_production_shape(db, null_active=1, null_archived=0, solo=0)
    db.create_scenario(_scenario("no-view", None))
    db.save_result(ResultRecord("no-view", "2026-08-06T00:00:00+00:00", None,
                                owner_id=None))

    summary = data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)

    assert summary["current_results_unrecoverable"] == ["no-view"]
    assert db.get_scenario("no-view", owner=TARGET) is not None
    assert db.latest_result("no-view", owner=TARGET) is None


def test_legacy_view_that_cannot_be_backfilled_keeps_its_view(db):
    _seed_production_shape(db, null_active=1, null_archived=0, solo=0)
    db.save_result(ResultRecord("legacy0", "2026-08-05T00:00:00+00:00",
                                {"results": []}, owner_id=None))   # 太舊的形狀

    summary = data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)

    assert summary["fact_context_impossible"] == 1
    assert db.result_view_stats() == {"with_view": 1, "missing_fact_context": 1,
                                      "clearable": 0}


# ---------- retention ----------

def test_snapshot_retention_runs_as_part_of_the_repair(db):
    view = _seed_production_shape(db, null_active=1, null_archived=0, solo=0)
    del view
    for day in range(1, 26):                   # 再補 25 份 9 月的歷史快照
        db.save_snapshot("legacy0", f"2026-09-{day:02d}T00:00:00+00:00", {},
                         owner_id=None)

    data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)

    stamps = db.snapshot_timestamps("legacy0", owner=TARGET)
    # current（8/07）＋最新（9/25）＋最多 10 份 30 天內的歷史
    assert "2026-08-07T00:00:00+00:00" in stamps
    assert stamps[-1] == "2026-09-25T00:00:00+00:00"
    assert len(stamps) == 12


# ---------- legacy singleton 表（只有 Postgres 會有） ----------

def _create_legacy_tables(with_credential_token: str) -> None:
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("CREATE TABLE provider_credentials (provider TEXT PRIMARY KEY,"
                     " token TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO provider_credentials VALUES "
                     "('fmp', %s, '2026-08-01T00:00:00+00:00')",
                     (with_credential_token,))
        conn.execute("CREATE TABLE narrow_history (x INT)")
        conn.execute("CREATE TABLE chain_cache (x INT)")


def test_legacy_tables_are_adopted_then_dropped(db):
    if isinstance(db, MemoryStorage):
        pytest.skip("記憶體假體沒有 legacy 表")
    _seed_production_shape(db)
    _create_legacy_tables("fake-legacy-token")

    code, out = _run(db, confirm=True)

    assert code == 0
    assert "fake-legacy-token" not in out
    assert db.get_credential("fmp", owner=TARGET).token == "fake-legacy-token"
    assert db.retired_tables_present() == []


def test_legacy_tables_are_not_dropped_without_a_canonical_copy(db, monkeypatch):
    if isinstance(db, MemoryStorage):
        pytest.skip("記憶體假體沒有 legacy 表")
    _seed_production_shape(db)
    _create_legacy_tables("fake-legacy-token")
    monkeypatch.setattr(type(db), "adopt_legacy_settings",
                        lambda self, owner: {"settings": 0, "credentials": 0,
                                             "verifications": 0})

    with pytest.raises(data_lifecycle.MaintenanceError, match="canonical"):
        data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)
    assert "provider_credentials" in db.retired_tables_present()
    assert db.owner_row_counts(SOLO_OWNER)["scenarios"] == 4     # 整段 rollback


# ---------- 每日 cron 也跑 retention（活躍／protected owner 不會被 owner 清理碰到） ----------

def test_daily_cleanup_cron_applies_the_retention_policy(db):
    from api_app.storage import RoleSession, SuperUserAuditEvent

    _register_target(db)
    db.set_owner_protected(TARGET, True)
    db.create_scenario(_scenario("mine", TARGET))
    now = datetime.now(timezone.utc)
    old = "2025-01-01T00:00:00+00:00"                     # 遠超過每一種保留期
    db.save_snapshot("mine", old, SNAPSHOT, owner_id=TARGET)
    for i in range(3):
        db.save_snapshot("mine", now.replace(microsecond=0, second=i).isoformat(),
                         SNAPSHOT, owner_id=TARGET)
    db.append_event(ts=old, scenario_id="mine", event="E", payload={},
                    owner_id=TARGET)
    db.append_audit_event(SuperUserAuditEvent(
        event_id="a-old", ts=old, actor="superadmin", action="x",
        target_owner_id=None, detail={}))
    db.create_role_session(RoleSession("expired", "superadmin", "2024-01-01T00:00:00+00:00"))
    db.create_role_session(RoleSession("revoked", "superuser", old, revoked_at=old))
    db.create_role_session(RoleSession("live", "superadmin", now.isoformat()))

    body = TestClient(_app(db)).get(
        "/api/cron/cleanup-abandoned-owners",
        headers={"Authorization": "Bearer fake-cron-secret"}).json()

    assert body["retention_rows_purged"] == {
        "snapshots": 1, "role_sessions": 2, "audit_log": 1, "events": 1}
    assert old not in db.snapshot_timestamps("mine", owner=TARGET)
    assert db.resolve_role_session("live") is not None
    assert db.get_scenario("mine", owner=TARGET) is not None     # 劇本本身不受影響


# ---------- cleanup invariant：有 current result 就必須有對應快照 ----------

def test_cleanup_fails_and_rolls_back_when_a_current_result_has_no_snapshot(db):
    """CLAUDE-DB-HYGIENE-003：current_result 存在、快照卻一份都沒有（空清單）
    也必須讓清理驗證失敗——不能因為「沒有任何快照」而靜默通過。清理段
    整段 rollback：fact 回填、legacy view 清除、retention、DROP 都不留下。"""
    _seed_production_shape(db, null_active=1, null_archived=0, solo=0)
    for day in range(1, 16):          # 讓 retention 有東西可刪，才驗得出 rollback
        db.save_snapshot("legacy0", f"2026-09-{day:02d}T00:00:00+00:00",
                         SNAPSHOT, owner_id=None)
    # 目標 owner 自己的劇本：有 current result，但 0 份快照
    db.save_current_result(ResultRecord(
        "mine0", "2026-09-20T00:00:00+00:00", {"results": []}, owner_id=TARGET))
    assert db.snapshot_timestamps("mine0", owner=TARGET) == []
    snapshots_before = db.table_row_counts()["snapshots"]["rows"]

    with pytest.raises(data_lifecycle.MaintenanceError,
                       match="mine0 的最新結果沒有對應快照"):
        data_lifecycle.execute(db, target_owner_id=TARGET, now=NOW)

    # 清理段完全沒有留下任何變更
    assert db.result_view_stats() == {"with_view": 2, "missing_fact_context": 2,
                                      "clearable": 0}
    assert db.result_fact_context(
        "legacy0", "2026-08-06T00:00:00+00:00").engine_version is None
    assert db.table_row_counts()["snapshots"]["rows"] == snapshots_before
    # 搬遷段是獨立的原子段落，已經完成且可以安全重跑
    assert db.get_scenario("legacy0", owner=TARGET) is not None
    assert db.get_owner(TARGET).protected is True
