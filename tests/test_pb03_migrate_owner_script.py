"""PB-03（#295，Anonymous Public Beta）：`scripts/migrate_solo_to_
owner.py` 的行為契約與 HTTP 層端到端驗證。腳本本身硬綁
`PostgresStorage`（正式環境唯一會用到它的地方），因此這裡的測試需要
一個真的 Postgres（`OC_TEST_DATABASE_URL`），沒有時整組跳過。
"""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

from api_app.identity import SOLO_OWNER
from api_app.main import create_app
from api_app.storage import BrowserIdentity, Owner
from api_app.storage.postgres import PostgresStorage
from option_chaser.data.snapshot import load_snapshot

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL 才能驗證 PostgresStorage")

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}

migrate_module = importlib.import_module("scripts.migrate_solo_to_owner")


@pytest.fixture
def db():
    import psycopg

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE scenarios, results, current_results, snapshots, events, "
            "diagnostics, owner_settings, owner_credentials, "
            "owner_verifications, owners, browser_identities RESTART IDENTITY")
    yield st


def _run_script(argv, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setattr(sys, "argv", ["migrate_solo_to_owner.py", *argv])
    migrate_module.main()


def test_refuses_to_run_against_a_target_owner_that_does_not_exist(db, monkeypatch):
    with pytest.raises(SystemExit, match="不存在"):
        _run_script(["--target-owner-id", "ghost-owner", "--confirm"], monkeypatch)


def test_dry_run_without_confirm_does_not_write_anything(db, monkeypatch, capsys):
    snap = load_snapshot(FIX)
    client = TestClient(create_app(fetch=lambda symbol: snap,
                                   identity_resolver=lambda: SOLO_OWNER, storage=db))
    client.post("/api/scenarios", json=NEW).raise_for_status()
    db.create_owner_with_token(
        Owner(owner_id="anon-real", created_at="2026-09-14T00:00:00+00:00"),
        BrowserIdentity(token=_REAL_TOKEN, owner_id="anon-real",
                        issued_at="2026-09-14T00:00:00+00:00",
                        last_seen_at="2026-09-14T00:00:00+00:00"))

    _run_script(["--target-owner-id", "anon-real"], monkeypatch)

    out = capsys.readouterr().out
    assert "未帶 --confirm" in out
    assert db.list_scenarios(owner="anon-real") == []
    assert len(db.list_scenarios(owner=SOLO_OWNER)) == 1


def test_confirmed_run_migrates_and_protects_and_is_idempotent(db, monkeypatch, capsys):
    snap = load_snapshot(FIX)
    client = TestClient(create_app(fetch=lambda symbol: snap,
                                   identity_resolver=lambda: SOLO_OWNER, storage=db))
    created = client.post("/api/scenarios", json=NEW).json()
    client.post(f"/api/scenarios/{created['id']}/refresh").raise_for_status()

    db.create_owner_with_token(
        Owner(owner_id="anon-real", created_at="2026-09-14T00:00:00+00:00"),
        BrowserIdentity(token=_REAL_TOKEN, owner_id="anon-real",
                        issued_at="2026-09-14T00:00:00+00:00",
                        last_seen_at="2026-09-14T00:00:00+00:00"))

    _run_script(["--target-owner-id", "anon-real", "--confirm"], monkeypatch)

    assert db.get_scenario(created["id"], owner="anon-real") is not None
    assert db.get_scenario(created["id"], owner=SOLO_OWNER) is None
    assert db.get_owner("anon-real").protected is True

    out = capsys.readouterr().out
    assert "solo 底下 10 張表皆已清空" in out

    # 第二次跑：完全冪等，不報錯、不重複搬動。
    _run_script(["--target-owner-id", "anon-real", "--confirm"], monkeypatch)
    assert db.get_scenario(created["id"], owner="anon-real") is not None


# 形狀要像真的 cookie token（`secrets.token_urlsafe(32)`，43 字元）——
# SECURITY-FIX-01 起 middleware 不接受太短的任意字串當身份。
_REAL_TOKEN = "tok-real-" + "x" * 34


def test_end_to_end_owner_sees_all_legacy_scenarios_through_their_own_cookie(
        db, monkeypatch):
    """AC 明文要求的端到端驗證：遷移後，Owner 用自己那顆 cookie 取得的
    身份看得到全部舊劇本——這裡用「直接把既有 token 對到目標 owner_id」
    模擬同一顆瀏覽器 cookie（PB-02 的 cookie middleware 本身已在
    `test_pb02_cookie_identity.py` 逐一驗證過，這裡只驗證遷移後的資料
    可見性，不重測 cookie 機制本身）。"""
    snap = load_snapshot(FIX)
    legacy_client = TestClient(create_app(
        fetch=lambda symbol: snap, identity_resolver=lambda: SOLO_OWNER, storage=db))
    created = []
    for symbol in ("AAA", "BBB", "CCC"):
        r = legacy_client.post("/api/scenarios", json={**NEW, "symbol": symbol})
        r.raise_for_status()
        created.append(r.json()["id"])

    db.create_owner_with_token(
        Owner(owner_id="anon-real", created_at="2026-09-14T00:00:00+00:00"),
        BrowserIdentity(token=_REAL_TOKEN, owner_id="anon-real",
                        issued_at="2026-09-14T00:00:00+00:00",
                        last_seen_at="2026-09-14T00:00:00+00:00"))

    _run_script(["--target-owner-id", "anon-real", "--confirm"], monkeypatch)

    owner_client = TestClient(
        create_app(fetch=lambda symbol: snap, storage=db),
        base_url="https://testserver")
    owner_client.cookies.set("__Host-oc_owner", _REAL_TOKEN)

    seen = {row["id"] for row in owner_client.get("/api/scenarios").json()}
    assert seen == set(created)
