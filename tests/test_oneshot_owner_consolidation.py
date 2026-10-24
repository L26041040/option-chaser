"""【臨時】OPTION-CHASER-OWNER-CONSOLIDATION-001 cold-start hook 的測試——
cleanup 時與 `api_app/oneshot_owner_consolidation.py` 一起移除。"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from api_app import oneshot_owner_consolidation as hook
from api_app import owner_consolidation as oc
from api_app.main import create_app
from test_owner_consolidation import (ANON, GHOST, OLD, SECRET_VALUES, T,  # noqa: F401
                                      T_TOKENS, TEST_DB_URL, NOW, _dump, _seed,
                                      _token, db)

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL（hook 只在 Postgres 上執行）")

SECRET_DSN = "postgresql://oc_user:super-secret-pw@db.example.test/prod"


@pytest.fixture(autouse=True)
def _clean_status():
    hook.STATUS.clear()
    yield
    hook.STATUS.clear()


def _env() -> dict[str, str]:
    return {"VERCEL_ENV": "production", "DATABASE_URL": TEST_DB_URL}


def _run(env=None, **kw):
    hook.run(_env() if env is None else env, now=lambda: NOW, **kw)


def _forbidden() -> tuple[str, ...]:
    return (T, OLD, *ANON, GHOST, *T_TOKENS, _token(OLD), *SECRET_VALUES,
            "Tcf2_BUR", SECRET_DSN, "super-secret-pw", TEST_DB_URL)


def _assert_clean(text: str) -> None:
    for needle in _forbidden():
        assert needle not in text


def test_non_production_never_connects(db):
    _seed(db)
    before = _dump()
    for env in ({}, {"VERCEL_ENV": "preview", "DATABASE_URL": TEST_DB_URL},
                {"VERCEL_ENV": "development", "DATABASE_URL": TEST_DB_URL}):
        hook.run(env, connect=lambda dsn: pytest.fail("connected"),
                 prepare_schema=lambda dsn: pytest.fail("schema"))
    assert hook.STATUS == {}
    assert _dump() == before


def test_cold_start_runs_the_consolidation_once_and_reports_counts(db, caplog):
    _seed(db)
    with caplog.at_level(logging.WARNING):
        _run()
    assert hook.STATUS["status"] == "completed"
    summary = hook.STATUS["summary"]
    assert summary["remaining_owners"] == 1
    assert summary["after"]["scenarios"] == {"total": 20, "target": 20}
    assert len(db.list_scenarios(owner=T, include_archived=True)) == 20
    _assert_clean(json.dumps(hook.STATUS))
    _assert_clean(caplog.text)

    # 下一次 cold start：備份已存在 → 只讀回報，絕不重跑。
    after = _dump()
    _run()
    assert hook.STATUS["status"] == "noop_completed"
    assert hook.STATUS["state"]["owners_now"] == 1
    assert _dump() == after


def test_precondition_mismatch_is_reported_and_writes_nothing(db):
    _seed(db)
    db.set_owner_role("anon-1", "superuser")
    before = _dump()
    _run()
    assert hook.STATUS["status"] == "blocked_precondition"
    assert hook.STATUS["mismatches"] == ["superuser_count", "target_prefix",
                                         "target_scenarios", "source_scenarios"]
    assert hook.STATUS["observed"]["superuser_count"] == 2
    assert _dump() == before
    _assert_clean(json.dumps(hook.STATUS))


def test_lock_held_elsewhere_skips_and_the_loser_rechecks_read_only(db, monkeypatch):
    import psycopg
    _seed(db)
    before = _dump()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as other:
        with other.transaction():
            other.execute("SELECT pg_advisory_xact_lock(%s)",
                          (hook.ADVISORY_LOCK_KEY,))
            _run()
    assert hook.STATUS["status"] == "skipped_lock_held"
    assert _dump() == before

    # 持有者完成之後，搶輸的 instance 在 health 上回頭讀共享狀態。
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.transaction():
            oc.execute(conn, now=NOW)
    hook.recheck_if_lock_was_held(_env())          # 還沒過 RECHECK_SECONDS
    assert hook.STATUS["status"] == "skipped_lock_held"
    monkeypatch.setattr(hook, "RECHECK_SECONDS", 0)
    after = _dump()
    hook.recheck_if_lock_was_held(_env())
    assert hook.STATUS["status"] == "noop_completed"
    assert _dump() == after


def test_unexpected_failure_records_only_the_exception_type(db, caplog):
    _seed(db)
    before = _dump()

    def broken(dsn):
        raise RuntimeError(f"cannot reach {dsn}")
    with caplog.at_level(logging.WARNING):
        hook.run({"VERCEL_ENV": "production", "DATABASE_URL": SECRET_DSN},
                 connect=broken, prepare_schema=lambda dsn: None)
    assert hook.STATUS["status"] == "failed_exception"
    assert hook.STATUS["error_type"] == "RuntimeError"
    _assert_clean(json.dumps(hook.STATUS))
    _assert_clean(caplog.text)
    assert _dump() == before


def test_failed_check_rolls_back_and_is_retried_on_next_cold_start(db, monkeypatch):
    _seed(db)
    before = _dump()
    real = oc._verify_cleanup

    def boom(conn, **kwargs):
        raise oc.ConsolidationError("verification: injected")
    monkeypatch.setattr(oc, "_verify_cleanup", boom)
    _run()
    assert hook.STATUS == {"status": "failed_check",
                           "reason": "verification: injected",
                           "at": hook.STATUS["at"]}
    assert _dump() == before
    monkeypatch.setattr(oc, "_verify_cleanup", real)
    _run()
    assert hook.STATUS["status"] == "completed"


def test_health_exposes_only_the_sanitized_status(db):
    _seed(db)
    _run()
    client = TestClient(create_app(fetch=lambda s: pytest.fail("no fetch"),
                                   storage=db, cron_secret="x"))
    body = client.get("/api/health").json()
    assert body["owner_consolidation"]["status"] == "completed"
    _assert_clean(json.dumps(body))
    hook.STATUS.clear()
    assert "owner_consolidation" not in client.get("/api/health").json()
