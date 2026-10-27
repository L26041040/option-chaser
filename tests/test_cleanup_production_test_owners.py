"""PRODUCTION-TEST-DATA-CLEANUP-001：`scripts/cleanup_production_test_owners.py`。

在真 Postgres 上重建 Production 的形狀（Owner 施工令）：15 個 Owner（1 個主帳號＋
14 個測試 Normal）、24 個劇本（10 個主帳號原有＋14 個 XYZ 測試）、測試 Owner 另有分析
結果、一筆自己 owner_id 是 NULL 的子列、quota 計數列。驗證：dry-run 零寫入；執行後
1／10／0／0／孤兒 0 且非候選資料指紋不變；任何前置條件不符一律零寫入停止；交易中途
失敗整批 rollback。
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from api_app import main_account
from api_app.storage import BrowserIdentity, Owner, ResultRecord, Scenario
from scripts import cleanup_production_test_owners as cleanup

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")

MAIN = main_account.SEED_OWNER_PREFIX + "m" * 35
TEST_TS = "2026-10-27T00:11:{sec:02d}.000000+00:00"
OLD_TS = "2026-10-20T03:00:00+00:00"


def _iso(sec: int) -> str:
    return TEST_TS.format(sec=sec)


@pytest.fixture
def db():
    import psycopg

    from api_app.storage.postgres import PostgresStorage
    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE scenarios, results, current_results, snapshots, events, "
            "diagnostics, owner_settings, owner_credentials, owner_verifications, "
            "owners, browser_identities, rate_limits, feedback, main_account, "
            "owner_merge_archive, identity_tombstones RESTART IDENTITY")
    _seed_production_shape(st)
    yield st


def _scenario(sid, owner, *, created, price=130.0, month="2027-01", symbol="XYZ"):
    return Scenario(id=sid, symbol=symbol, direction="bullish", target_price=price,
                    target_month=month, notes="", strategies=("vertical-spread",),
                    created_at=created, archived_at=None, owner_id=owner)


def _seed_production_shape(st):
    st.create_owner_with_token(
        Owner(owner_id=MAIN, created_at="2026-09-01T00:00:00+00:00", protected=True),
        BrowserIdentity(token="main-device-" + "m" * 31, owner_id=MAIN,
                        issued_at=OLD_TS, last_seen_at=OLD_TS))
    st.set_owner_role(MAIN, "superuser")
    st.set_main_account(MAIN, now=OLD_TS, expected=None)
    for i in range(10):
        st.create_scenario(_scenario(f"orig-{i:02d}", MAIN, created=OLD_TS,
                                     price=100.0 + i, symbol="AAPL"))
        st.save_result(ResultRecord(f"orig-{i:02d}", OLD_TS, {"v": i}, best_return=0.1,
                                    owner_id=MAIN))
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO owner_settings (owner_id, settings, updated_at) "
                     "VALUES (%s, '{\"k\": 1}', %s)", (MAIN, OLD_TS))
    for i in range(14):
        oid = f"testowner-{i:02d}-" + "t" * 20
        st.create_owner_with_token(
            Owner(owner_id=oid, created_at=_iso(i), protected=False),
            BrowserIdentity(token=f"plaintext-device-token-{i:02d}-" + "z" * 12,
                            owner_id=oid, issued_at=_iso(i), last_seen_at=_iso(i)))
        sid = f"testscn-{i:02d}"
        st.create_scenario(_scenario(sid, oid, created=_iso(i)))
        if i < 2:                                   # 「另有 2 筆分析結果」
            st.save_result(ResultRecord(sid, _iso(i), {"v": "t"}, best_return=0.2,
                                        owner_id=oid))
        if i == 0:                                   # 自己 owner 是 NULL 的子列
            st.save_snapshot(sid, _iso(i), {"snap": 1}, owner_id=None)
            st.append_event(ts=_iso(i), scenario_id=sid, event="SCENARIO_CREATED",
                            payload={}, owner_id=None)
        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("INSERT INTO rate_limits (scope, key, window_seconds, "
                         "window_start, count) VALUES ('owner_vendor', %s, 3600, 1, 1)",
                         (oid,))


def _counts(db):
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        one = lambda q: conn.execute(q).fetchone()[0]  # noqa: E731
        return {"owners": one("SELECT count(*) FROM owners"),
                "scenarios": one("SELECT count(*) FROM scenarios"),
                "results": one("SELECT count(*) FROM results"),
                "snapshots": one("SELECT count(*) FROM snapshots"),
                "events": one("SELECT count(*) FROM events"),
                "identities": one("SELECT count(*) FROM browser_identities"),
                "tombstones": one("SELECT count(*) FROM identity_tombstones"),
                "xyz": one("SELECT count(*) FROM scenarios WHERE symbol = 'XYZ'")}


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)

    def _run(*extra, backup=True):
        argv = list(extra)
        if backup and "--confirm" in argv:
            argv += ["--backup-path", str(tmp_path / f"backup-{len(list(tmp_path.iterdir()))}.json")]
        return cleanup.main(argv)
    return _run


def test_dry_run_confirms_everything_and_writes_nothing(db, run, capsys):
    before = _counts(db)
    assert before["owners"] == 15 and before["scenarios"] == 24
    assert run() == 0
    out = capsys.readouterr().out
    assert '"candidates"' in out and "dry-run 完成" in out
    assert _counts(db) == before
    assert "plaintext-device-token" not in out          # 輸出絕不含 token


def test_confirm_leaves_exactly_the_production_owner_and_original_scenarios(db, run, tmp_path, capsys):
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        main_before = conn.execute("SELECT * FROM owners WHERE owner_id = %s", (MAIN,)).fetchall()
        orig_before = conn.execute("SELECT * FROM scenarios WHERE id LIKE 'orig-%' ORDER BY id").fetchall()
        settings_before = conn.execute("SELECT * FROM owner_settings").fetchall()
    assert run("--confirm") == 0
    out = capsys.readouterr().out
    after = _counts(db)
    assert after["owners"] == 1 and after["scenarios"] == 10 and after["xyz"] == 0
    assert after["identities"] == 1 and after["snapshots"] == 0 and after["events"] == 0
    assert after["results"] == 10                       # 只剩原有劇本的結果
    assert after["tombstones"] == 14                    # 14 顆測試憑證作廢
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        assert conn.execute("SELECT * FROM owners WHERE owner_id = %s", (MAIN,)).fetchall() == main_before
        assert conn.execute("SELECT * FROM scenarios WHERE id LIKE 'orig-%' ORDER BY id").fetchall() == orig_before
        assert conn.execute("SELECT * FROM owner_settings").fetchall() == settings_before
        assert conn.execute("SELECT count(*) FROM rate_limits").fetchone()[0] == 0
    assert all(v == 0 for v in cleanup.orphans(psycopg.connect(TEST_DB_URL, autocommit=True)).values())
    assert "plaintext-device-token" not in out
    # 備份與驗證紀錄
    [backup] = [p for p in tmp_path.iterdir() if p.suffix == ".json" and "verification" not in p.name]
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    raw = backup.read_text(encoding="utf-8")
    assert "plaintext-device-token" not in raw          # 備份不含明文憑證
    body = json.loads(raw)
    assert len(body["owners"]) == 14 and len(body["scenarios"]) == 14
    assert len(body["browser_identities"]) == 14
    assert all(len(r["token_sha256"]) == 64 for r in body["browser_identities"])
    assert len(body["results"]) == 2 and len(body["snapshots"]) == 1 and len(body["events"]) == 1
    verification = json.loads((tmp_path / (backup.name + ".verification.json")).read_text())
    assert verification["after"]["owners"] == 1 and verification["after"]["scenarios"] == 10


def test_second_run_refuses_because_there_is_nothing_left_to_match(db, run):
    assert run("--confirm") == 0
    assert run() == 2                                   # 候選 0 ≠ 14：停止，不是「成功但什麼都沒做」
    assert _counts(db)["owners"] == 1


@pytest.mark.parametrize("mutation", [
    "UPDATE scenarios SET target_price = 131 WHERE id = 'testscn-03'",
    "UPDATE owners SET protected = TRUE WHERE owner_id LIKE 'testowner-04-%'",
    "UPDATE owners SET role = 'superuser' WHERE owner_id LIKE 'testowner-05-%'",
    "INSERT INTO owner_settings (owner_id, settings, updated_at) "
    "SELECT owner_id, '{}', 'x' FROM owners WHERE owner_id LIKE 'testowner-06-%'",
    "INSERT INTO feedback (feedback_id, display_name, content, created_at, owner_id) "
    "SELECT 'f1', 'n', 'c', 'x', owner_id FROM owners WHERE owner_id LIKE 'testowner-07-%'",
    "DELETE FROM scenarios WHERE id = 'testscn-08'",
    "UPDATE results SET owner_id = 'someone-else' WHERE scenario_id = 'testscn-00'",
    "UPDATE scenarios SET created_at = '2026-10-26T00:11:00+00:00' WHERE id = 'testscn-09'",
])
def test_any_mismatch_stops_with_zero_writes(db, run, mutation):
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(mutation)
    before = _counts(db)
    assert run("--confirm") == 2
    assert _counts(db) == before


def test_an_extra_lookalike_owner_inside_the_window_is_ambiguity_not_a_15th_candidate(db, run):
    db.create_owner_with_token(
        Owner(owner_id="real-user-" + "r" * 20, created_at=_iso(30), protected=False),
        BrowserIdentity(token="real-user-device-" + "r" * 20, owner_id="real-user-" + "r" * 20,
                        issued_at=_iso(30), last_seen_at=_iso(30)))
    db.create_scenario(_scenario("real-scn", "real-user-" + "r" * 20, created=_iso(30),
                                 symbol="MSFT", price=400.0))
    before = _counts(db)
    assert run("--confirm", "--expect-owners", "16", "--expect-scenarios", "25") == 2
    assert _counts(db) == before


def test_wrong_totals_stop_with_zero_writes(db, run):
    before = _counts(db)
    assert run("--confirm", "--expect-owners", "16") == 2
    assert _counts(db) == before


def test_null_owner_children_of_test_scenarios_do_not_become_orphans(db, run):
    assert run("--confirm") == 0
    import psycopg
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM snapshots WHERE scenario_id = 'testscn-00'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM events WHERE scenario_id = 'testscn-00'").fetchone()[0] == 0


def test_failure_in_the_middle_rolls_back_all_14_owners(db, run, monkeypatch, capsys):
    from api_app.storage.postgres import PostgresStorage
    real = PostgresStorage.delete_owner
    calls = []

    def flaky(self, owner_id, *, reason="deleted"):
        calls.append(owner_id)
        if len(calls) == 8:
            raise RuntimeError("simulated failure on the 8th owner")
        return real(self, owner_id, reason=reason)
    monkeypatch.setattr(PostgresStorage, "delete_owner", flaky)
    before = _counts(db)
    assert run("--confirm") == 3
    assert len(calls) == 8
    assert _counts(db) == before                        # 前 7 個也沒刪
    assert "rollback" in capsys.readouterr().err


def test_post_delete_verification_failure_rolls_back(db, run, monkeypatch):
    real = cleanup.verify_after

    def bad(conn, before, args):
        after = real(conn, before, args)
        raise cleanup.Refused("simulated verification failure")
    monkeypatch.setattr(cleanup, "verify_after", bad)
    before = _counts(db)
    assert run("--confirm") == 3
    assert _counts(db) == before


def test_existing_backup_file_is_never_overwritten(db, run, tmp_path):
    existing = tmp_path / "keep.json"
    existing.write_text("precious")
    assert cleanup.main(["--confirm", "--backup-path", str(existing)]) == 2
    assert existing.read_text() == "precious"
    assert _counts(db)["owners"] == 15


def test_confirm_requires_a_backup_path(db, run):
    assert run("--confirm", backup=False) == 2
    assert _counts(db)["owners"] == 15
