"""【臨時】CLAUDE-DB-HYGIENE-008 cold-start 修復 hook 的測試——cleanup PR
與 `api_app/oneshot_db_rescue.py` 一起移除。"""
from __future__ import annotations

import contextlib
import json

import pytest
from fastapi.testclient import TestClient

from api_app import data_lifecycle, oneshot_db_rescue
from test_db_hygiene_002 import (NOW, TARGET, TEST_DB_URL, _app,  # noqa: F401
                                 _seed_production_shape, db)

SECRET_DSN = "postgresql://oc_user:super-secret-pw@db.example.test/prod"
PROD_ENV = {"VERCEL_ENV": "production", "DATABASE_URL": SECRET_DSN}
_REAL_EXECUTE = data_lifecycle.execute


@pytest.fixture(autouse=True)
def _target_and_clean_status(monkeypatch):
    monkeypatch.setattr(oneshot_db_rescue, "TARGET_OWNER_ID", TARGET)
    oneshot_db_rescue.STATUS.clear()
    yield
    oneshot_db_rescue.STATUS.clear()


def _lock(acquired: bool):
    seen: list[str] = []

    @contextlib.contextmanager
    def lock(dsn):
        seen.append(dsn)
        yield acquired
    lock.seen = seen
    return lock


def _run(db, env=PROD_ENV, *, acquired=True):
    lock = _lock(acquired)
    oneshot_db_rescue.run(env, storage_factory=lambda env: db, lock=lock,
                          now=lambda: NOW)
    return lock


def _count_execute(monkeypatch, *, fail: bool = False) -> list[int]:
    calls: list[int] = []
    def spy(db, *, target_owner_id, now):
        calls.append(1)
        assert target_owner_id == TARGET
        if fail:
            raise data_lifecycle.MaintenanceError(
                "搬遷驗證失敗，已整段 rollback：劇本 legacy0 " + SECRET_DSN)
        return _REAL_EXECUTE(db, target_owner_id=target_owner_id, now=now)
    monkeypatch.setattr(data_lifecycle, "execute", spy)
    return calls


def test_non_production_never_touches_the_database(db, monkeypatch):
    _seed_production_shape(db)
    calls = _count_execute(monkeypatch)
    for env in ({}, {"VERCEL_ENV": "preview", "DATABASE_URL": SECRET_DSN},
                {"VERCEL_ENV": "development", "DATABASE_URL": SECRET_DSN}):
        lock = _run(db, env)
        assert lock.seen == [] and calls == []
    assert oneshot_db_rescue.STATUS == {}
    assert db.list_scenarios(owner=TARGET, include_archived=True)  # 只有 mine0


def test_lock_held_elsewhere_skips_without_planning(db, monkeypatch):
    _seed_production_shape(db)
    calls = _count_execute(monkeypatch)
    monkeypatch.setattr(data_lifecycle, "plan", lambda *a, **k: pytest.fail("plan"))
    _run(db, acquired=False)
    assert calls == []
    assert oneshot_db_rescue.STATUS["status"] == "skipped_lock_held"


def _recheck(db, *, acquired=True):
    oneshot_db_rescue.recheck_if_lock_was_held(
        PROD_ENV, storage_factory=lambda env: db, lock=_lock(acquired),
        now=lambda: NOW)


def test_lock_loser_rechecks_shared_state_after_the_holder_finishes(db, monkeypatch):
    """Codex P2（PR #348）：搶輸 lock 的 warm instance 不能永遠停在
    skipped_lock_held。"""
    _seed_production_shape(db)
    _run(db, acquired=False)                        # 這個 instance 搶輸
    _REAL_EXECUTE(db, target_owner_id=TARGET, now=NOW)   # 持有者做完
    monkeypatch.setattr(oneshot_db_rescue, "RECHECK_SECONDS", 0)
    calls = _count_execute(monkeypatch)
    _recheck(db)
    assert calls == []
    assert oneshot_db_rescue.STATUS["status"] == "noop_already_complete"


def test_recheck_is_throttled_and_never_executes_on_the_request_path(
        db, monkeypatch):
    _seed_production_shape(db)
    _run(db, acquired=False)
    calls = _count_execute(monkeypatch)
    plans = []
    real_plan = data_lifecycle.plan
    monkeypatch.setattr(data_lifecycle, "plan",
                        lambda *a, **k: plans.append(1) or real_plan(*a, **k))
    _recheck(db)                                    # 60 秒內：不重查
    assert plans == [] and oneshot_db_rescue.STATUS["status"] == "skipped_lock_held"
    monkeypatch.setattr(oneshot_db_rescue, "RECHECK_SECONDS", 0)
    _recheck(db)                                    # 持有者失敗、工作仍待辦
    assert calls == []
    assert oneshot_db_rescue.STATUS["status"] == "pending_after_lock_released"
    _recheck(db)                                    # 已不是 skipped：不再重查
    assert len(plans) == 1


def test_pending_work_calls_canonical_execute_exactly_once(db, monkeypatch):
    _seed_production_shape(db)
    calls = _count_execute(monkeypatch)
    _run(db)
    assert calls == [1]
    status = oneshot_db_rescue.STATUS
    assert status["status"] == "completed"
    after = status["plan_after"]
    assert after["null_owner_scenarios"] == 0 and after["solo_rows"] == 0
    assert after["target_total_scenarios"] == 18
    assert after["target_active_scenarios"] == 14
    assert after["target_protected"] is True
    assert after["retired_tables_present"] == []
    assert status["verification"]["migration_problems"] == 0
    assert status["verification"]["cleanup_problems"] == 0
    assert status["verification"]["result_views"]["clearable"] == 0
    assert status["verification"]["target_credential_providers"] == 1
    assert status["summary"]["current_results_reconstructed"] == 13


def test_already_complete_is_a_no_op(db, monkeypatch):
    _seed_production_shape(db)
    _run(db)                                   # 第一次 cold start 施工
    calls = _count_execute(monkeypatch)
    _run(db)                                   # 之後的 cold start
    assert calls == []
    status = oneshot_db_rescue.STATUS
    assert status["status"] == "noop_already_complete"
    assert status["plan"]["target_total_scenarios"] == 18
    assert status["verification"]["cleanup_problems"] == 0


def test_execute_failure_is_swallowed_sanitized_and_retried_next_cold_start(
        db, monkeypatch):
    _seed_production_shape(db)
    calls = _count_execute(monkeypatch, fail=True)
    _run(db)                                   # 不拋例外
    status = oneshot_db_rescue.STATUS
    assert status["status"] == "failed_maintenance_error"
    assert status["reason"] == "搬遷驗證失敗，已整段 rollback"
    assert "legacy0" not in json.dumps(status, ensure_ascii=False)
    monkeypatch.setattr(data_lifecycle, "execute", _REAL_EXECUTE)
    _run(db)                                   # 下一次 cold start 重試
    assert calls == [1]
    assert oneshot_db_rescue.STATUS["status"] == "completed"


def test_unexpected_exception_records_only_the_type(db, monkeypatch):
    _seed_production_shape(db)

    def boom(*a, **k):
        raise RuntimeError(f"connection to {SECRET_DSN} failed")
    monkeypatch.setattr(data_lifecycle, "plan", boom)
    _run(db)
    assert oneshot_db_rescue.STATUS["status"] == "failed_exception"
    assert oneshot_db_rescue.STATUS["error_type"] == "RuntimeError"


def test_no_secret_reaches_status_logs_or_health(db, monkeypatch, caplog):
    _seed_production_shape(db)
    with caplog.at_level("WARNING"):
        _run(db)
    health = TestClient(_app(db)).get("/api/health").json()
    assert health["db_rescue"]["status"] == "completed"
    blob = json.dumps(health, ensure_ascii=False) + caplog.text
    for leaked in (SECRET_DSN, "super-secret-pw", "fake-solo-token", TARGET,
                   "legacy0", "solo0"):
        assert leaked not in blob


def test_health_has_no_db_rescue_field_when_the_hook_did_nothing(db):
    assert "db_rescue" not in TestClient(_app(db)).get("/api/health").json()


@pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")
def test_postgres_advisory_lock_admits_only_one_holder():
    with oneshot_db_rescue._postgres_advisory_lock(TEST_DB_URL) as first:
        with oneshot_db_rescue._postgres_advisory_lock(TEST_DB_URL) as second:
            assert first is True and second is False
    with oneshot_db_rescue._postgres_advisory_lock(TEST_DB_URL) as again:
        assert again is True                    # transaction 結束即釋放
