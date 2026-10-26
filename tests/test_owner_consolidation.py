"""OPTION-CHASER-OWNER-CONSOLIDATION-001：Production 舊 Owner 資料統一合併。

模擬 Owner 確認的 Production 形狀：9 個 owner、20 個劇本；唯一 Super User
（target）有 1 個劇本，其他 8 個 owner 共 19 個（其中一個是受保護的 Owner
舊身份，帶設定與 API 憑證）。只跑真的 Postgres（`OC_TEST_DATABASE_URL`）
——Production 本來就只有 Postgres，而這裡要驗的正是 transaction、DDL 與
rollback 的行為。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api_app import owner_consolidation as oc
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import (OWNER_RATE_LIMIT_SCOPE, BrowserIdentity,
                             DataSourceSettings, Owner, ProviderCredential,
                             ProviderVerification, ResultRecord, Scenario,
                             UsageSetting)

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL（合併只在 Postgres 上執行）")

NOW = datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)
T = "Tcf2_BUR" + "q" * 35
T_TOKENS = ("tok-target-a-" + "a" * 30, "tok-target-b-" + "b" * 30)
OLD = "old-owner-protected"
ANON = [f"anon-{i}" for i in range(1, 8)]
# 每個 source owner 的劇本數（OLD 12 ＋ 匿名 7 個共 7）＝ 19。
SOURCE_SCENARIOS = {OLD: 12, "anon-1": 2, "anon-2": 1, "anon-3": 1,
                    "anon-4": 1, "anon-5": 1, "anon-6": 1, "anon-7": 0}
GHOST = "ghost-deleted-owner"           # 只殘留在 diagnostics 的舊 owner_id
PENDING = "pending:" + "0" * 32
CREATED = "2026-09-01T00:00:00+00:00"
SECRET_VALUES = ("old-tradier-secret", "old-md-secret", "anon2-md-secret",
                 "anon3-fmp-secret", "target-md-secret")


def _token(owner: str) -> str:
    return f"tok-{owner}-" + "z" * 30


def _tables() -> tuple[str, ...]:
    return ("scenarios", "results", "current_results", "snapshots", "events",
            "diagnostics", "owner_settings", "owner_credentials",
            "owner_verifications", "owners", "browser_identities",
            "role_sessions", "superuser_audit_log", "rate_limits",
            "operational_metrics", "feedback", "identity_tombstones")


@pytest.fixture
def db():
    import psycopg

    from api_app.storage.postgres import PostgresStorage
    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {oc.BACKUP_SCHEMA} CASCADE")
        conn.execute("TRUNCATE " + ", ".join(_tables()) + " RESTART IDENTITY")
    yield st
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {oc.BACKUP_SCHEMA} CASCADE")


def _sql(sql: str, params=()):
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        return conn.execute(sql, params).fetchall() if sql.lstrip().upper(
            ).startswith("SELECT") else conn.execute(sql, params).rowcount


def _in_tx(fn):
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.transaction():
            return fn(conn)


def _execute():
    return _in_tx(lambda conn: oc.execute(conn, now=NOW))


def _rollback():
    return _in_tx(lambda conn: oc.rollback(conn, now=NOW))


def _status():
    return _in_tx(oc.status)


def _owner(db, owner_id: str, tokens: tuple[str, ...], *, role="normal",
           protected=False) -> None:
    db.create_owner_with_token(
        Owner(owner_id=owner_id, created_at=CREATED),
        BrowserIdentity(token=tokens[0], owner_id=owner_id, issued_at=CREATED,
                        last_seen_at=CREATED))
    for tok in tokens[1:]:
        _sql("INSERT INTO browser_identities (token, owner_id, issued_at, "
             "last_seen_at) VALUES (%s, %s, %s, %s)", (tok, owner_id, CREATED, CREATED))
    if role != "normal":
        db.set_owner_role(owner_id, role)
        # CROSS-DEVICE-ACCOUNT-001：權限看憑證——跟 Production 冷啟動回填後
        # 的狀態一樣，這個特權 owner 的每顆裝置憑證都帶著它的權限。
        for tok in tokens:
            db.set_credential_role(tok, role)
    if protected:
        db.set_owner_protected(owner_id, True)


def _scenario(db, sid: str, owner: str, *, archived=False, child_owner="same"):
    db.create_scenario(Scenario(
        id=sid, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2027-01", notes="", strategies=("vertical-spread",),
        created_at=CREATED, archived_at=CREATED if archived else None,
        owner_id=owner))
    child = owner if child_owner == "same" else child_owner
    for ts in ("2026-09-10T00:00:00+00:00", "2026-09-11T00:00:00+00:00"):
        db.save_result(ResultRecord(sid, ts, None, best_return=0.4,
                                    owner_id=child))
        db.save_snapshot(sid, ts, {"symbol": "XYZ", "at": ts}, owner_id=child)
    db.save_current_result(ResultRecord(sid, "2026-09-11T00:00:00+00:00",
                                        {"results": [], "sid": sid},
                                        best_return=0.4, owner_id=child))
    db.append_event(ts=CREATED, scenario_id=sid, event="SCENARIO_CREATED",
                    payload={}, owner_id=child)


def _settings(db, owner: str, updated: str, provider="marketdata-app") -> None:
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="default"),
        historical_iv=UsageSetting(mode="custom", provider=provider),
        updated_at=updated, owner_id=owner))


def _cred(db, owner: str, provider: str, token: str, updated: str,
          verified: bool | None = None) -> None:
    db.save_credential(ProviderCredential(provider=provider, token=token,
                                          updated_at=updated, owner_id=owner))
    if verified is not None:
        db.save_verification(ProviderVerification(
            provider=provider, ok=verified, reason=None, checked_at=updated,
            owner_id=owner))


def _diag(owner: str | None) -> None:
    _sql("INSERT INTO diagnostics (event_id, correlation_id, ts, subsystem, "
         "stage, severity, user_facing, message, context, owner_id) VALUES "
         "(%s, 'c', %s, 'refresh', 'fetch', 'warning', TRUE, 'm', '{}', %s)",
         (f"ev-{owner}", CREATED, owner))


def _seed(db, *, target_settings=False) -> None:
    _owner(db, T, T_TOKENS, role="superuser")
    _scenario(db, "t-0", T)
    _owner(db, OLD, (_token(OLD),), protected=True)
    for owner in ANON:
        _owner(db, owner, (_token(owner),))
    for owner, n in SOURCE_SCENARIOS.items():
        for i in range(n):
            # anon-5 的劇本有 NULL-owner 的子列（SCALE-06 之前寫入的舊列）。
            _scenario(db, f"{owner}-{i}", owner, archived=(owner == OLD and i < 3),
                      child_owner=None if owner == "anon-5" else "same")
    # OLD（受保護的 Owner 舊身份）：設定＋兩把憑證＋驗證結果。
    _settings(db, OLD, "2026-09-20T00:00:00+00:00")
    _cred(db, OLD, "tradier", "old-tradier-secret", "2026-09-20T00:00:00+00:00", True)
    _cred(db, OLD, "marketdata-app", "old-md-secret", "2026-09-20T00:00:00+00:00", True)
    # anon-2 有較新的設定與同 provider、不同值的憑證（衝突：OLD 受保護優先）。
    _settings(db, "anon-2", "2026-10-01T00:00:00+00:00", provider="other")
    _cred(db, "anon-2", "marketdata-app", "anon2-md-secret",
          "2026-10-02T00:00:00+00:00", False)
    # anon-3 有一把只有它有的憑證：沒有衝突，直接歸入 target。
    _cred(db, "anon-3", "fmp", "anon3-fmp-secret", "2026-10-03T00:00:00+00:00", True)
    if target_settings:
        _settings(db, T, "2026-09-01T00:00:00+00:00", provider="target-choice")
        _cred(db, T, "marketdata-app", "target-md-secret", "2026-09-01T00:00:00+00:00")
    for owner in (OLD, "anon-1", None):
        _diag(owner)
    _diag(GHOST)
    _diag(PENDING)
    _sql("INSERT INTO feedback (feedback_id, display_name, content, created_at, "
         "owner_id) VALUES ('fb-1', 'n', 'c', %s, 'anon-7'), "
         "('fb-2', 'n', 'c', %s, NULL)", (CREATED, CREATED))
    for key in (T, "anon-7", OLD):
        _sql("INSERT INTO rate_limits (scope, key, window_seconds, window_start, "
             "count) VALUES (%s, %s, 86400, 1792800000, 3)",
             (OWNER_RATE_LIMIT_SCOPE, key))
    _sql("INSERT INTO rate_limits (scope, key, window_seconds, window_start, "
         "count) VALUES ('source_vendor', 'hmac-x', 60, 1792800000, 1)")
    _sql("INSERT INTO superuser_audit_log (event_id, ts, actor, action, "
         "target_owner_id, detail) VALUES ('a-1', %s, 'superadmin', "
         "'delete_owner_scenario', 'anon-1', '{}')", (CREATED,))
    # 最近登入：target 剛用過；source 裡 OLD 比 anon-2 晚（anon-2 的設定
    # 雖然比較新，衝突時仍以最近登入的 OLD 為準）。
    _last_seen(T, "2026-10-25T05:00:00+00:00")
    _last_seen(OLD, "2026-10-20T00:00:00+00:00")
    _last_seen("anon-2", "2026-10-05T00:00:00+00:00")


def _last_seen(owner: str, ts: str) -> None:
    _sql("UPDATE browser_identities SET last_seen_at = %s WHERE owner_id = %s",
         (ts, owner))


def _dump() -> dict[str, list]:
    out = {}
    for table in _tables():
        rows = _sql(f"SELECT row_to_json(t)::text FROM {table} t")
        out[table] = sorted(r[0] for r in rows)
    return out


def _client(db) -> TestClient:
    return TestClient(create_app(fetch=lambda s: pytest.fail("no fetch"),
                                 storage=db, cron_secret="x"),
                      base_url="https://testserver")


# ---------- 預檢 ----------

def test_status_before_reports_the_preconditions_without_writing(db):
    _seed(db)
    before = _dump()
    st = _status()
    assert st["state"] == "not_started" and st["mismatches"] == []
    obs = st["observed"]
    assert obs["owners_total"] == 9 and obs["scenarios_total"] == 20
    assert obs["target_scenarios"] == 1 and obs["source_scenarios"] == 19
    assert obs["superuser_count"] == 1 and obs["target_prefix_match"] is True
    assert obs["target_most_recently_active"] is True
    assert obs["unregistered_source_ids"] == 1          # GHOST
    assert obs["pending_placeholder_ids"] == 1
    assert _dump() == before
    assert not _in_tx(oc.backup_exists)


@pytest.mark.parametrize("break_it", [
    "extra_owner", "second_superuser", "wrong_prefix", "extra_scenario",
    "superuser_is_superadmin"])
def test_any_precondition_mismatch_writes_nothing(db, break_it):
    _seed(db)
    if break_it == "extra_owner":
        _owner(db, "late-visitor", (_token("late-visitor"),))
    elif break_it == "second_superuser":
        db.set_owner_role("anon-1", "superuser")
    elif break_it == "wrong_prefix":
        db.set_owner_role(T, "normal")
        db.set_owner_role("anon-1", "superuser")
    elif break_it == "extra_scenario":
        _scenario(db, "t-1", T)
    else:
        db.set_owner_role(T, "superadmin")
    before = _dump()
    with pytest.raises(oc.PreconditionMismatch) as e:
        _execute()
    assert e.value.mismatches
    assert _dump() == before
    assert not _in_tx(oc.backup_exists)
    assert "target" not in e.value.observed
    assert not any(isinstance(v, str) and (T in v or OLD in v)
                   for v in e.value.observed.values())


# ---------- 合併 ----------

def test_execute_moves_every_scenario_and_its_history_into_the_target(db):
    _seed(db)
    before = _dump()
    summary = _execute()

    assert summary["remaining_owners"] == 1
    assert summary["before"]["owners"] == {"total": 9, "target": 1}
    assert summary["after"]["owners"] == {"total": 1, "target": 1}
    for table in ("scenarios", "results", "current_results", "snapshots",
                  "events"):
        assert summary["after"][table]["total"] == summary["before"][table]["total"]
        assert summary["after"][table]["target"] == summary["after"][table]["total"]
    assert summary["after"]["scenarios"] == {"total": 20, "target": 20}
    assert summary["after"]["results"] == {"total": 40, "target": 40}
    assert len(db.list_scenarios(owner=T, include_archived=True)) == 20
    assert len(db.list_scenarios(owner=T)) == 17
    assert db.lineage_report(T).ok
    # 歷史分析一筆不少、內容不變（只有 owner_id 換了）。
    for sid in ("old-owner-protected-0", "anon-5-0", "t-0"):
        assert len(db.result_history(sid, owner=T)) == 2
        assert db.latest_result(sid, owner=T).view == {"results": [], "sid": sid}
        assert db.get_snapshot(sid, "2026-09-10T00:00:00+00:00", owner=T) == {
            "symbol": "XYZ", "at": "2026-09-10T00:00:00+00:00"}
    assert len(db.list_events(owner=T)) == 20
    after = _dump()
    assert len(after["superuser_audit_log"]) == len(before["superuser_audit_log"])
    assert after["superuser_audit_log"] == before["superuser_audit_log"]


def test_target_keeps_its_role_and_login_and_old_identities_are_not_rebound(db):
    _seed(db)
    _execute()
    owner = db.get_owner(T)
    assert owner.role == "superuser"
    assert owner.protected is True                 # OLD 受保護 → 保護延續
    for tok in T_TOKENS:
        assert db.resolve_owner_by_token(tok) == T
    for src in (OLD, *ANON):
        assert db.resolve_owner_by_token(_token(src)) is None
        assert db.get_owner(src) is None

    client = _client(db)
    me = client.get("/api/auth/status", cookies={_OWNER_COOKIE_NAME: T_TOKENS[0]})
    assert me.json() == {"role": "superuser"}
    listed = client.get("/api/scenarios", params={"include_archived": True},
                        cookies={_OWNER_COOKIE_NAME: T_TOKENS[0]}).json()
    assert len(listed) == 20
    # 舊瀏覽器帶著舊 cookie 回來：只是一個沒有權限、沒有資料的新訪客。
    old = client.get("/api/auth/status", cookies={_OWNER_COOKIE_NAME: _token(OLD)})
    assert old.json() == {"role": "normal"}
    assert client.get("/api/scenarios", params={"include_archived": True},
                      cookies={_OWNER_COOKIE_NAME: _token(OLD)}).json() == []


def test_settings_and_credentials_merge_without_losing_anything(db):
    _seed(db)
    summary = _execute()
    bundle = db.owner_settings_bundle(T)
    # target 沒有設定：最近登入的 OLD 優先於設定較新的 anon-2。
    assert bundle.settings.historical_iv.provider == "marketdata-app"
    assert set(bundle.credentials) == {"tradier", "marketdata-app", "fmp"}
    assert bundle.credentials["marketdata-app"].token == "old-md-secret"
    assert bundle.credentials["fmp"].token == "anon3-fmp-secret"
    assert set(bundle.verifications) == {"tradier", "marketdata-app", "fmp"}
    assert bundle.verifications["marketdata-app"].ok is True     # OLD 的
    assert summary["settings"] == {
        "owner_settings": {"adopted": 1, "archived_only": 1},
        "owner_credentials": {"adopted": 3, "archived_only": 1},
        "owner_verifications": {"adopted": 3, "archived_only": 1}}
    # 沒被採用的那份（anon-2）完整留在備份裡。
    archived = _sql(f"SELECT token FROM {oc.BACKUP_SCHEMA}.copy_owner_credentials "
                    "WHERE owner_id = 'anon-2'")
    assert archived == [("anon2-md-secret",)]
    assert _sql(f"SELECT count(*) FROM {oc.BACKUP_SCHEMA}.copy_owner_settings "
                "WHERE owner_id = 'anon-2'") == [(1,)]


def test_most_recently_active_source_wins_a_conflict_the_target_lacks(db):
    _seed(db)
    _last_seen("anon-2", "2026-10-24T00:00:00+00:00")   # 現在 anon-2 最近登入
    _execute()
    bundle = db.owner_settings_bundle(T)
    assert bundle.settings.historical_iv.provider == "other"
    assert bundle.credentials["marketdata-app"].token == "anon2-md-secret"
    assert bundle.verifications["marketdata-app"].ok is False   # 跟著 anon-2 的
    assert bundle.credentials["tradier"].token == "old-tradier-secret"
    assert _sql(f"SELECT token FROM {oc.BACKUP_SCHEMA}.copy_owner_credentials "
                "WHERE owner_id = %s AND provider = 'marketdata-app'",
                (OLD,)) == [("old-md-secret",)]


def test_target_settings_win_every_conflict(db):
    _seed(db, target_settings=True)
    _execute()
    bundle = db.owner_settings_bundle(T)
    assert bundle.settings.historical_iv.provider == "target-choice"
    assert bundle.credentials["marketdata-app"].token == "target-md-secret"
    assert "marketdata-app" not in bundle.verifications   # target 本來就沒有
    assert bundle.credentials["tradier"].token == "old-tradier-secret"
    assert bundle.verifications["tradier"].ok is True


def test_no_ownerless_rows_are_left_anywhere(db):
    _seed(db)
    _execute()
    st = _status()
    assert st["state"] == "completed"
    assert st["owners_now"] == 1 and st["target_role_now"] == "superuser"
    assert st["target_scenarios_now"] == 20
    assert all(n == 0 for n in st["ownerless_rows_now"].values())
    assert _sql("SELECT count(*) FROM feedback WHERE owner_id = %s", (T,)) == [(1,)]
    assert _sql("SELECT count(*) FROM feedback WHERE owner_id IS NULL") == [(1,)]
    assert _sql("SELECT key FROM rate_limits WHERE scope = %s",
                (OWNER_RATE_LIMIT_SCOPE,)) == [(T,)]
    # 系統層級（NULL）與每請求佔位值的診斷列原樣保留。
    assert _sql("SELECT count(*) FROM diagnostics WHERE owner_id IS NULL "
                "OR owner_id LIKE 'pending:%%'") == [(2,)]
    assert _sql("SELECT count(*) FROM diagnostics WHERE owner_id = %s",
                (T,)) == [(3,)]


def test_execute_is_one_shot(db):
    _seed(db)
    _execute()
    after = _dump()
    with pytest.raises(oc.PreconditionMismatch) as e:
        _execute()
    assert "backup_absent" in e.value.mismatches
    assert _dump() == after


def test_a_failed_verification_rolls_back_everything_including_the_backup(
        db, monkeypatch):
    _seed(db)
    before = _dump()

    def boom(conn, **kwargs):
        raise oc.ConsolidationError("verification: injected")
    monkeypatch.setattr(oc, "_verify_cleanup", boom)
    with pytest.raises(oc.ConsolidationError, match="injected"):
        _execute()
    assert _dump() == before
    assert not _in_tx(oc.backup_exists)


def test_summary_and_status_never_carry_ids_or_secrets(db):
    _seed(db)
    texts = [json.dumps(_status()), json.dumps(_execute()), json.dumps(_status())]
    for text in texts:
        for needle in (T, OLD, *ANON, GHOST, *T_TOKENS, _token(OLD),
                       *SECRET_VALUES, "Tcf2_BUR"):
            assert needle not in text


# ---------- 回滾 ----------

def test_rollback_restores_the_exact_pre_merge_state(db):
    _seed(db)
    before = _dump()
    _execute()
    assert _dump() != before
    out = _rollback()
    assert out["owners"] == 8 and out["browser_identities_token_reused"] == 0
    assert _dump() == before
    assert _status()["state"] == "rolled_back"
    with pytest.raises(oc.ConsolidationError, match="not_completed"):
        _rollback()
    with pytest.raises(oc.PreconditionMismatch):        # 回滾後不會自動重跑
        _execute()


def test_rollback_keeps_what_happened_after_the_merge(db):
    _seed(db, target_settings=True)
    _execute()
    _scenario(db, "t-new", T)                           # 合併後新建的劇本
    _settings(db, T, "2026-10-26T00:00:00+00:00", provider="changed-later")
    # 舊瀏覽器回來寫入：同一顆 token 被綁成新的匿名 owner。
    db.claim_browser_token(_token("anon-1"),
                           Owner(owner_id="anon-1-new", created_at=CREATED),
                           now=CREATED)
    out = _rollback()
    assert out["browser_identities_token_reused"] == 1
    assert db.resolve_owner_by_token(_token("anon-1")) == "anon-1-new"
    assert db.get_owner("anon-1") is not None
    assert db.list_scenarios(owner="anon-1", include_archived=True)
    assert {s.id for s in db.list_scenarios(owner=T, include_archived=True)} \
        == {"t-new", "t-0"}
    assert db.owner_settings_bundle(T).settings.historical_iv.provider \
        == "target-choice"
    assert _sql(f"SELECT settings->'historical_iv'->>'provider' FROM "
                f"{oc.BACKUP_SCHEMA}.rollback_archive_owner_settings "
                "WHERE owner_id = %s", (T,)) == [("changed-later",)]


def test_owner_script_reads_status_and_rolls_back_only_with_confirm(db):
    import subprocess
    import sys
    _seed(db)
    before = _dump()
    _execute()

    def run(*args):
        return subprocess.run(
            [sys.executable, "scripts/owner_consolidation.py", *args],
            env={**os.environ, "DATABASE_URL": TEST_DB_URL},
            capture_output=True, text=True, check=True).stdout

    merged = _dump()
    for out in (run(), run("--rollback")):
        assert '"state": "completed"' in out
        for needle in (T, OLD, *T_TOKENS, *SECRET_VALUES):
            assert needle not in out
    assert _dump() == merged
    out = run("--rollback", "--confirm")
    assert '"state": "rolled_back"' in out
    assert _dump() == before
