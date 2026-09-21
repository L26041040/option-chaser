"""PB-07（#304，Anonymous Public Beta）：Synthetic load-test harness
——mock vendor（既有 DI 注入點）＋ `is_synthetic` 標記。

## 絕對紅線（票面 §3，逐字）

Owner 明文禁止「用技術手段規避 vendor rate limit 或偵測」——本輪
harness 全程**不得打真實 Cboe／Yahoo**。全部合成流量一律經
`cboe_fetch=` DI 注入點（`create_app()` 既有參數，SCALE-04／#255）
接管——它仍會走既有 `_metered_chain_fetch()` 包裝（`chain_fetch_count`
指標因此真的被 synthetic 流量推進，不是靠手動灌值模擬「今天已經打過
幾次」，quota／fuse 的觸發是**真實機制在真實負載下運作**，不是預先
擺好的劇本），但從未碰到真正的 `cboe.fetch_chain`／`yf.fetch_chain`。
`test_zero_real_vendor_calls_across_the_whole_harness` 把這件事從
「結構保證」升格為「計數斷言」（票面 AC：「有計數斷言證明，非口頭
保證」）——把兩個真實 adapter 換成引爆就報錯的地雷，完整跑一輪
harness 情境後斷言地雷從未被引爆。

## 「preset cookie」技術（本票新引入，`main.py` 零 production code
改動——票面 §7 明文要求：harness 不得讓 production 出現只為壓測而
存在的分支）

`_make_synthetic_owner()` 直接呼叫既有 `Storage.
create_owner_with_token()`（PB-01）＋本票唯一新增的 storage 欄位
`is_synthetic=True`，再把那個 token 預先塞進 `TestClient` 的
cookie jar 才發出第一個請求——PB-02 的 lazy-creation 路徑因此完全
走不到（cookie 一開始就合法），synthetic owner 從第一個位元組起與
正常使用者路徑無法分辨，除了它自己的 `is_synthetic` 旗標。這個
技巧本身已用一支獨立腳本手動驗證過（見 CLAUDE.md PB-07 段落）：
單一 synthetic owner 建立一筆劇本後，`storage.list_owners()` 恰好
一筆、`is_synthetic=True`，證明不會意外多生出一個 owner。

## §15 Exit Criteria 對照

- 第 1 項（互不污染）：`test_exit_1_*`
- 第 2 項（quota／fuse 真的被觸發）：
  `test_exit_2_quota_is_actually_triggered_under_synthetic_load`／
  `test_exit_2_global_vendor_fuse_is_actually_triggered_under_synthetic_load`
- 第 3 項（graceful degradation，無 500）：
  `test_exit_3_no_500_across_every_degradation_path`
- 第 4 項（cleanup lifecycle 完整跑通，含 protected 交叉驗證）：
  `test_exit_4_full_cleanup_lifecycle_across_many_synthetic_owners_at_once`
- 第 6 項（DB 成長速率外推）：`test_exit_6_*`——僅在真實 Postgres 上
  跑（`OC_TEST_DATABASE_URL` 未設定時 skip）。沿用 SCALE-16／
  REPAIR-10 既有教訓「必須量到收斂，不得用退化小 fixture 外推」：
  這裡用 `PRODUCTION_SCALE_FIXTURE`（600 張合約），不是六到期日的
  小樣本。

## 其餘 AC

- 零真實 vendor 呼叫：`test_zero_real_vendor_calls_across_the_whole_harness`。
- synthetic 資料可整批清空：
  `test_synthetic_data_can_be_cleared_in_one_batch`。
- `is_synthetic` 欄位本身的 Storage port 契約（round-trip、預設值）
  已在 `tests/test_storage_contract.py::
  test_is_synthetic_defaults_to_false_and_round_trips_true` 覆蓋，
  本檔案不重複。

走既有第 1 個 seam（HTTP API）與第 3 個（Storage port 契約）——harness
本身即是測試載體，不新增 seam（票面 §9）。
"""
from __future__ import annotations

import dataclasses
import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api_app.clock import now_utc_iso
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import BrowserIdentity, Owner
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from tests._production_scale_fixtures import (
    PRODUCTION_SCALE_FIXTURE, offline_rate_loader, real_dividend_loader)

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
CRON_SECRET = "test-pb07-cron-secret"
CRON_AUTH = {"Authorization": f"Bearer {CRON_SECRET}"}
TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")


def _scenario_payload(symbol: str = "XYZ", **overrides) -> dict:
    return {"symbol": symbol, "target_price": 130.0, "target_month": "2026-09",
            "strategies": ["vertical-spread"], **overrides}


def _cboe_mock(snapshot):
    """`cboe_fetch=` DI 注入點的假體——仍會被 `_default_fetch()` 包進
    既有 `_metered_chain_fetch()`，因此 `chain_fetch_count` 真的隨
    synthetic 流量遞增；從未碰到真實 `cboe.fetch_chain`。每次呼叫回傳
    同一份快照，`fetched_at` 蓋成「現在」（比照既有 PB-05／PB-06 測試
    helper 慣例：production 每次抓取都蓋成現在，fixture 固定的歷史
    時間戳不能拿來測節流／預算窗）。"""
    calls = {"n": 0}

    def _fetch(symbol: str):
        calls["n"] += 1
        return dataclasses.replace(snapshot, fetched_at=now_utc_iso())

    _fetch.calls = calls  # type: ignore[attr-defined]
    return _fetch


def _make_synthetic_owner(storage, *, protected: bool = False,
                          last_activity_at: str | None = None) -> tuple[str, str]:
    owner_id = f"synthetic-{secrets.token_urlsafe(8)}"
    token = secrets.token_urlsafe(16)
    now = now_utc_iso()
    storage.create_owner_with_token(
        Owner(owner_id=owner_id, created_at=now, last_activity_at=last_activity_at,
              protected=protected, is_synthetic=True),
        BrowserIdentity(token=token, owner_id=owner_id, issued_at=now, last_seen_at=now))
    return owner_id, token


def _client_for(app, token: str) -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(_OWNER_COOKIE_NAME, token)
    return c


# ---------- Exit 第 1 項：多 synthetic owner 互不污染 ----------


def test_exit_1_multiple_synthetic_owners_are_fully_isolated_from_each_other():
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET)

    clients: list[tuple[TestClient, str]] = []
    for _ in range(5):
        _owner_id, token = _make_synthetic_owner(storage)
        c = _client_for(app, token)
        r = c.post("/api/scenarios", json=_scenario_payload())
        assert r.status_code == 201, r.text
        clients.append((c, r.json()["id"]))

    for i, (c, sid) in enumerate(clients):
        listing = c.get("/api/scenarios").json()
        assert len(listing) == 1
        assert listing[0]["id"] == sid
        for j, (_, other_sid) in enumerate(clients):
            if j == i:
                continue
            # 看不到別人的劇本——與不存在時回應完全一致（既有 SCALE-11
            # 既有 owner enforcement 慣例）。
            assert c.get(f"/api/scenarios/{other_sid}").status_code == 404

    assert storage.scenario_count_total() == 5
    assert len({o.owner_id for o in storage.list_owners()}) == 5


# ---------- Exit 第 2 項：quota 與 fuse 真的被觸發 ----------


def test_exit_2_quota_is_actually_triggered_under_synthetic_load():
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     anonymous_max_active_scenarios=3)
    _owner_id, token = _make_synthetic_owner(storage)
    c = _client_for(app, token)

    statuses = [c.post("/api/scenarios", json=_scenario_payload()).status_code
               for _ in range(5)]

    assert statuses.count(201) == 3
    assert statuses.count(409) == 2
    assert 500 not in statuses


def test_exit_2_global_vendor_fuse_is_actually_triggered_under_synthetic_load():
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     global_vendor_daily_budget=3,
                     anonymous_max_active_scenarios=0)
    _owner_id, token = _make_synthetic_owner(storage)
    c = _client_for(app, token)
    sc = c.post("/api/scenarios", json=_scenario_payload()).json()

    results = [c.post(f"/api/scenarios/{sc['id']}/refresh?manual=true") for _ in range(6)]

    # 預算 3、六次真實抓取嘗試——一定有幾次撞到 fuse。
    assert mock.calls["n"] <= 3  # type: ignore[attr-defined]
    assert any(
        r.status_code == 429 and r.json()["detail"]["stage"] == "vendor_budget_exhausted"
        for r in results)
    assert all(r.status_code < 500 for r in results)


# ---------- Exit 第 3 項：graceful degradation，無 500 ----------


def test_exit_3_no_500_across_every_degradation_path():
    """quota 拒絕（409）、fuse 拒絕（429）、正常成功（200／201）三種
    情境混在同一輪合成流量裡，逐一確認沒有任何一個回應是 500。"""
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     global_vendor_daily_budget=5,
                     anonymous_max_active_scenarios=2)

    all_statuses: list[int] = []
    for _ in range(4):
        _owner_id, token = _make_synthetic_owner(storage)
        c = _client_for(app, token)
        created_ids = []
        for _ in range(3):
            r = c.post("/api/scenarios", json=_scenario_payload())
            all_statuses.append(r.status_code)
            if r.status_code == 201:
                created_ids.append(r.json()["id"])
        for sid in created_ids:
            r = c.post(f"/api/scenarios/{sid}/refresh?manual=true")
            all_statuses.append(r.status_code)

    assert all(s < 500 for s in all_statuses), all_statuses
    assert 409 in all_statuses  # 額度 2、每個 owner 嘗試 3 個——真的擋到過
    assert 429 in all_statuses  # 預算 5、8 個劇本各刷一次——真的擋到過


# ---------- Exit 第 4 項：cleanup lifecycle，多 owner 同時、含
# protected 交叉驗證 ----------


def test_exit_4_full_cleanup_lifecycle_across_many_synthetic_owners_at_once():
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     anonymous_abandoned_after_days=1, anonymous_grace_period_days=1)
    now = datetime.now(timezone.utc)

    active_id, active_token = _make_synthetic_owner(storage)
    _client_for(app, active_token).post(
        "/api/scenarios", json=_scenario_payload(symbol="AAA")).raise_for_status()
    storage.touch_owner_activity(active_id, now=now.isoformat())

    abandoned_id, abandoned_token = _make_synthetic_owner(storage)
    _client_for(app, abandoned_token).post(
        "/api/scenarios", json=_scenario_payload(symbol="BBB")).raise_for_status()
    storage.touch_owner_activity(
        abandoned_id, now=(now - timedelta(days=1, hours=12)).isoformat())

    eligible_id, eligible_token = _make_synthetic_owner(storage)
    _client_for(app, eligible_token).post(
        "/api/scenarios", json=_scenario_payload(symbol="CCC")).raise_for_status()
    storage.touch_owner_activity(
        eligible_id, now=(now - timedelta(days=2, hours=12)).isoformat())

    # protected——遠遠超過 abandoned+grace，若沒被正確濾掉會被判定為
    # eligible_for_hard_delete 並真的被刪掉（交叉驗證 PB-08 既有斷言）。
    protected_id, protected_token = _make_synthetic_owner(storage, protected=True)
    _client_for(app, protected_token).post(
        "/api/scenarios", json=_scenario_payload(symbol="DDD")).raise_for_status()
    storage.touch_owner_activity(
        protected_id, now=(now - timedelta(days=365)).isoformat())

    resp = _client_for(app, active_token).get(
        "/api/cron/cleanup-abandoned-owners", headers=CRON_AUTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["owners_checked"] == 3  # protected 在查詢層就被濾掉
    assert body["abandoned"] == 1
    assert body["hard_deleted"] == 1
    assert body["rows_deleted"] > 0

    assert storage.get_owner(active_id) is not None
    assert storage.get_owner(abandoned_id) is not None  # 標記但未刪
    assert storage.get_owner(eligible_id) is None  # 真的被刪了
    assert storage.get_owner(protected_id) is not None  # 交叉驗證：存活


# ---------- 零真實 vendor 呼叫：計數斷言，非口頭保證 ----------


def test_zero_real_vendor_calls_across_the_whole_harness(monkeypatch):
    """把真實 `cboe.fetch_chain`／`yf.fetch_chain` 換成引爆就報錯＋
    計數的地雷，完整跑一輪多 owner／quota／fuse／cleanup 的合成流量，
    最後斷言地雷從未被引爆——把票面 AC『全程零真實 vendor 呼叫』從
    結構保證（`cboe_fetch=` DI 覆寫）升格為可執行的計數斷言。"""
    from option_chaser.data import cboe as cboe_module
    from option_chaser.data import yf as yf_module

    real_calls = {"n": 0}

    def _landmine(symbol: str):
        real_calls["n"] += 1
        raise AssertionError(
            "real vendor adapter was called — synthetic harness leaked "
            "past the cboe_fetch= mock injection point")

    monkeypatch.setattr(cboe_module, "fetch_chain", _landmine)
    monkeypatch.setattr(yf_module, "fetch_chain", _landmine)

    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     global_vendor_daily_budget=2, anonymous_max_active_scenarios=2,
                     anonymous_abandoned_after_days=1, anonymous_grace_period_days=1)

    last_token = None
    for _ in range(4):
        _owner_id, token = _make_synthetic_owner(storage)
        last_token = token
        c = _client_for(app, token)
        for _ in range(3):
            r = c.post("/api/scenarios", json=_scenario_payload())
            if r.status_code == 201:
                c.post(f"/api/scenarios/{r.json()['id']}/refresh?manual=true")

    assert last_token is not None
    _client_for(app, last_token).get(
        "/api/cron/cleanup-abandoned-owners", headers=CRON_AUTH)

    assert real_calls["n"] == 0
    assert mock.calls["n"] > 0  # 確認流量真的有發生，不是整段被跳過


# ---------- synthetic 資料可整批清空 ----------


def test_synthetic_data_can_be_cleared_in_one_batch():
    """Public Beta 上線前必須清空全部 synthetic 資料（票面 §4，spec
    §9）——用 `is_synthetic` 旗標篩出全部 synthetic owner，逐一呼叫
    既有 PB-04 `Storage.delete_owner()`，清空前後列數對照；混一個
    非 synthetic 的真人 owner 進去，證明清空不會誤刪它。"""
    snap = load_snapshot(FIX)
    mock = _cboe_mock(snap)
    storage = MemoryStorage()
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET)

    real_client = TestClient(app, base_url="https://testserver")
    real_client.post("/api/scenarios", json=_scenario_payload(symbol="REAL")).raise_for_status()
    real_owner_id = next(o.owner_id for o in storage.list_owners() if not o.is_synthetic)

    for _ in range(4):
        _owner_id, token = _make_synthetic_owner(storage)
        _client_for(app, token).post(
            "/api/scenarios", json=_scenario_payload()).raise_for_status()

    assert storage.scenario_count_total() == 5
    assert len(storage.list_owners()) == 5

    synthetic_ids = [o.owner_id for o in storage.list_owners() if o.is_synthetic]
    assert len(synthetic_ids) == 4
    for oid in synthetic_ids:
        storage.delete_owner(oid)

    remaining = storage.list_owners()
    assert len(remaining) == 1
    assert remaining[0].owner_id == real_owner_id
    assert remaining[0].is_synthetic is False
    assert storage.scenario_count_total() == 1


# ---------- Exit 第 6 項：DB 成長速率外推（僅真實 Postgres） ----------

_GROWTH_TABLES = ("scenarios", "results", "current_results", "snapshots",
                  "events", "owners", "browser_identities")


def _total_db_bytes(conn) -> int:
    total = 0
    for table in _GROWTH_TABLES:
        row = conn.execute(
            "SELECT pg_total_relation_size(%s)", (table,)).fetchone()
        total += row[0]
    return total


@pytest.mark.skipif(
    not TEST_DB_URL,
    reason="需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）——DB 成長"
          "速率外推只在真實 Postgres 上有意義（記憶體假體沒有真正的"
          "磁碟頁面／TOAST）")
def test_exit_6_db_growth_rate_extrapolates_to_a_concrete_neon_free_owner_count():
    """production-scale fixture（600 張合約，`PRODUCTION_SCALE_FIXTURE`）
    ——沿用 SCALE-16／REPAIR-10 既有教訓：小 fixture（六到期日、
    數十張合約）量不出真實比例，必須量到收斂才能外推。量測涵蓋
    7 張 owner-scoped 表（`_GROWTH_TABLES`，與 PB-04 `_OWNER_SCOPED_
    TABLES` 同一份清單邏輯，這裡額外加 `owners`／`browser_identities`
    本身；SW-12／#342 起原本第 8 張 `narrow_history` 隨 Spread 淨成本
    走勢功能整個退休一併移除），VACUUM FULL 後才量——否則量到的是
    MVCC 冷啟動膨脹，不是 production 穩態足跡（SCALE-16 既有教訓）。"""
    import psycopg

    from api_app.storage import postgres as pg
    from api_app.storage.postgres import PostgresStorage

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:  # type: ignore[arg-type]
        conn.execute(
            "TRUNCATE scenarios, results, current_results, snapshots, events, "
            "owners, browser_identities RESTART IDENTITY")

    pg._schema_ready.discard(TEST_DB_URL)  # 這個程序只建一次 schema 的快取
    storage = PostgresStorage(TEST_DB_URL)  # type: ignore[arg-type]
    snap = load_snapshot(PRODUCTION_SCALE_FIXTURE)
    mock = _cboe_mock(snap)
    app = create_app(cboe_fetch=mock, storage=storage, cron_secret=CRON_SECRET,
                     rate_loader=offline_rate_loader,
                     dividend_loader=real_dividend_loader,
                     anonymous_max_active_scenarios=0)

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:  # type: ignore[arg-type]
        for table in _GROWTH_TABLES:
            conn.execute(f"VACUUM FULL {table}")
        before = _total_db_bytes(conn)

    # N=5 量出 163,840 B/owner（恰好是 8KB 頁面的整數倍）——在這個
    # 量級下，VACUUM FULL 後固定表開銷／頁面配置粒度可能還沒被稀釋掉
    # （SCALE-16 既有教訓：N 太小時量到的是量化雜訊，不是真實比例）。
    # N=20 才是這裡實際採用的值，用來確認數字有沒有隨 N 收斂。
    n_owners = 20
    for _ in range(n_owners):
        _owner_id, token = _make_synthetic_owner(storage)
        c = _client_for(app, token)
        sc = c.post("/api/scenarios", json=_scenario_payload()).json()
        r = c.post(f"/api/scenarios/{sc['id']}/refresh?manual=true")
        assert r.status_code == 200, r.text

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:  # type: ignore[arg-type]
        for table in _GROWTH_TABLES:
            conn.execute(f"VACUUM FULL {table}")
        after = _total_db_bytes(conn)

    delta_bytes = after - before
    assert delta_bytes > 0
    bytes_per_owner = delta_bytes / n_owners

    from api_app.ops_alerts import DEFAULT_STORAGE_CAP_BYTES

    owners_before_cap = DEFAULT_STORAGE_CAP_BYTES / bytes_per_owner
    print(
        f"\nPB-07 Exit #6 — DB growth: {bytes_per_owner:,.0f} bytes/synthetic-"
        f"owner (N={n_owners}, production-scale fixture, one refresh each) "
        f"-> ~{owners_before_cap:,.0f} anonymous owners before the Neon Free "
        f"storage alert threshold ({DEFAULT_STORAGE_CAP_BYTES:,} bytes, "
        "PB-11's DEFAULT_STORAGE_CAP_BYTES).")
    assert owners_before_cap > 0
