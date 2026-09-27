"""PB-06（#299，Anonymous Public Beta）：Global Vendor Fuse——per-owner
額度（PB-05）之上再加一道 system-wide 保險絲，擋「很多使用者各自都在
額度內、加總卻燒光 vendor 額度」這個 per-owner 機制結構上擋不到的
情況。

計數來源沿用既有機制（`api_app.metrics` 的 `chain_fetch_count`），
本檔案的測試因此大量直接用 `storage.record_metric(...)` 預先灌入
「今天已經打過幾次」，而不是真的觸發成千上百次抓鏈——這正是票面
要求「沿用既有機制」的體現：如果需要另外搭一套機制才能測，那就是
在測一個不存在的平行系統。

沿用既有第 1 個 seam（HTTP API）與第 3 個（Storage port 契約，
memory＋真 Postgres 雙後端）。
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta, timezone
from datetime import datetime as _dt

from fastapi.testclient import TestClient

from api_app import vendor_fuse
from api_app.chain_backoff import ChainBackoffEntry
from api_app.clock import now_utc_iso, ny_today
from api_app.main import create_app
from api_app.storage import (DataSourceSettings, ProviderCredential,
                             UsageSetting)
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError
from tests._role_session import role_cookies
from _adhoc import post_adhoc

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(*, storage=None, global_vendor_daily_budget=None,
           role=None, **overrides):
    storage = storage or MemoryStorage()
    base_snap = load_snapshot(FIX)

    def _fetch(symbol: str):
        # 同 PB-05 既有測試的理由：production 每次抓取都蓋成「現在」，
        # fixture 本身的固定歷史時間戳不能拿來測 PB-05 節流窗——這裡
        # 雖然不測節流，但沿用同一份 helper 慣例維持一致性。
        return dataclasses.replace(base_snap, fetched_at=now_utc_iso())

    cookies = role_cookies(storage, role) if role else None
    return TestClient(create_app(
        identity_resolver=lambda: "solo", fetch=_fetch,
        storage=storage,
        global_vendor_daily_budget=global_vendor_daily_budget,
        **overrides),
        cookies=cookies)


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def _seed_today_count(storage, count: int) -> None:
    """直接對既有 `chain_fetch_count` 指標灌值，模擬「今天全站已經
    打過這麼多次」——沿用既有機制，不新建平行計數。"""
    if count <= 0:
        return
    storage.record_metric("chain_fetch_count", ny_today().isoformat(),
                          source="cboe", symbol="ANY", count=count)


# ---------- 1. 預算用盡 → 新抓鏈請求進入降級，非 5xx ----------


def test_a_brand_new_scenario_cannot_be_refreshed_once_the_budget_is_spent():
    storage = MemoryStorage()
    _seed_today_count(storage, 100)
    c = _client(storage=storage, global_vendor_daily_budget=100)
    sc = _create(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429, r.text
    assert r.status_code < 500
    detail = r.json()["detail"]
    assert detail["stage"] == "vendor_budget_exhausted"
    # facts-only：不得出現評價字眼。
    for banned in ("異常", "糟糕", "建議", "推薦"):
        assert banned not in detail["message"]


def test_an_already_successful_scenario_keeps_its_last_known_data_when_the_budget_is_spent():
    """「沿用既有資料」在這個既有架構裡的意思：一次失敗的刷新從不
    覆寫既有的 `latest_result()`——舊資料原封不動留在原地，前端既有的
    兩態失敗卡片（REPAIR-05／#242）因此天然能呈現「更新失敗，目前
    顯示上一次成功結果」，不需要為 PB-06 另外發明一套呈現機制。"""
    storage = MemoryStorage()
    # SW-10（#340，Owner 真機驗收）節流整段移除後，刷新一律真的再抓
    # ——不必再像 PB-05 時代那樣特地停用節流窗，兩次呼叫本來就都會
    # 真正嘗試抓鏈，只受 fuse 這一道煞車管。
    c = _client(storage=storage)
    sc = _create(c)
    ok = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert ok.status_code == 200
    before = storage.latest_result(sc["id"], owner="solo")
    assert before is not None

    # 現在把預算灌爆，再刷新一次應該失敗、且不動既有資料。
    _seed_today_count(storage, 999)
    c2 = _client(storage=storage, global_vendor_daily_budget=999)
    r = c2.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429

    after = storage.latest_result(sc["id"], owner="solo")
    assert after is not None
    assert after.analyzed_at == before.analyzed_at


def test_refresh_run_reports_the_fuse_as_a_non_5xx_batch_failure_item():
    storage = MemoryStorage()
    _seed_today_count(storage, 50)
    c = _client(storage=storage, global_vendor_daily_budget=50)
    sc = _create(c)

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sc["id"]]})
    assert r.status_code == 200  # 批次端點本身永遠 200，個別失敗夾在結果裡
    body = r.json()
    assert len(body["results"]) == 1
    item = body["results"][0]
    assert item["scenario_id"] == sc["id"]
    assert item["ok"] is False
    assert item["stage"] == "vendor_budget_exhausted"


def test_a_never_analyzed_scenario_is_honestly_reported_as_having_nothing_to_reuse():
    """從未成功過的劇本，刷新失敗時就是誠實地說失敗——既有兩態卡片
    的「尚無可用分析結果」（PC-05／#242）本來就是為這個情況設計的，
    PB-06 不需要偽造一份不存在的資料。"""
    storage = MemoryStorage()
    _seed_today_count(storage, 10)
    c = _client(storage=storage, global_vendor_daily_budget=10)
    sc = _create(c)
    assert storage.latest_result(sc["id"], owner="solo") is None

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    assert storage.latest_result(sc["id"], owner="solo") is None


# ---------- 2. 預算可由外部 config／DI 調整與停用 ----------


def test_the_budget_is_adjustable_via_di():
    storage = MemoryStorage()
    _seed_today_count(storage, 5)
    # 預算設得比已經打過的次數還高——不該觸發。
    c = _client(storage=storage, global_vendor_daily_budget=10)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 200


def test_the_budget_is_disabled_by_zero_and_behaves_like_today():
    storage = MemoryStorage()
    _seed_today_count(storage, 999999)  # 隨便灌多高都不該擋
    c = _client(storage=storage, global_vendor_daily_budget=0)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 200


def test_the_budget_reads_the_environment_variable_when_not_overridden(monkeypatch):
    monkeypatch.setenv("GLOBAL_VENDOR_DAILY_BUDGET", "3")
    storage = MemoryStorage()
    _seed_today_count(storage, 3)
    c = _client(storage=storage, global_vendor_daily_budget=None)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "vendor_budget_exhausted"


# ---------- 3. fuse 計數不引入 owner 維度 ----------


def test_operational_metrics_still_has_no_owner_dimension(monkeypatch):
    """`MetricEntry`／`record_metric()` 的簽章結構上就沒有 owner 欄位
    ——這裡從 HTTP 層再驗證一次：兩個不同 owner 各自觸發抓鏈，
    `metric_total()` 看到的是**加總**，不是各自獨立的桶（若真的有
    owner 維度，兩者才可能被分開計算）。

    刻意**不**覆寫 `fetch=`（比照 `test_scale08_observability.py`
    既有 `_client()` helper 的理由）——`_metered_chain_fetch()`
    只包在 `_default_fetch()` 內部，`fetch=` 被覆寫時整條計數路徑
    直接被繞過，測不出真正的計數行為；改成 monkeypatch
    `option_chaser.data.cboe.fetch_chain` 本身，讓 production 預設
    路徑真的被走到。"""
    from option_chaser.data import cboe

    snap = load_snapshot(FIX)
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)

    storage = MemoryStorage()
    c1_app = create_app(identity_resolver=lambda: "owner-a",
                        storage=storage, global_vendor_daily_budget=0)
    c2_app = create_app(identity_resolver=lambda: "owner-b",
                        storage=storage, global_vendor_daily_budget=0)
    ca, cb = TestClient(c1_app), TestClient(c2_app)
    sc_a = _create(ca, symbol="ABC")
    sc_b = _create(cb, symbol="DEF")
    ra = ca.post(f"/api/scenarios/{sc_a['id']}/refresh")
    rb = cb.post(f"/api/scenarios/{sc_b['id']}/refresh")
    assert ra.status_code == 200 and rb.status_code == 200

    total = vendor_fuse.today_chain_fetch_count(storage, ny_today())
    assert total >= 2  # 兩個 owner 各自的抓取都算進同一個全站總數


# ---------- 4. fuse 與 chain_backoff 兩個獨立機制 ----------


def test_fuse_and_chain_backoff_do_not_overwrite_each_others_state():
    """fuse 觸發時，`_fetch_chain()` 在任何真正的上游呼叫之前就短路
    ——`chain_backoff` 完全沒被問過，它自己既有的持久狀態（不論
    是否恰好也顯示封鎖中）因此原封不動，不會被這次失敗覆寫或清除。"""
    storage = MemoryStorage()
    now = _dt.now(timezone.utc)
    blocked_until = now + timedelta(seconds=99)
    entry = ChainBackoffEntry(
        source="cboe", blocked_until=blocked_until.isoformat(),
        retry_after_seconds=99.0, consecutive_failures=1,
        observed_at=now.isoformat(), last_success_at=None)
    storage.save_chain_backoff(entry)

    _seed_today_count(storage, 10)
    c = _client(storage=storage, global_vendor_daily_budget=10)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    # 這次失敗的**真正原因**是 fuse——不是 chain_backoff 從未被問過，
    # UI 不該把這次失敗誤植成「vendor 限流」。
    assert r.json()["detail"]["stage"] == "vendor_budget_exhausted"

    # chain_backoff 自己的持久狀態完全未被這次失敗改動。
    fetched = storage.get_chain_backoff("cboe")
    assert fetched is not None
    assert fetched.blocked_until == entry.blocked_until
    assert fetched.consecutive_failures == entry.consecutive_failures


def test_when_only_chain_backoff_is_tripped_and_the_fuse_is_not_the_existing_classification_still_applies():
    """反過來：fuse 沒觸發、單純是 Cboe 真的在限流——既有
    `rate_limited` 分類（SCALE-05）原樣生效，PB-06 沒有動到它。"""
    storage = MemoryStorage()
    now = _dt.now(timezone.utc)
    entry = ChainBackoffEntry(
        source="cboe", blocked_until=(now + timedelta(seconds=30)).isoformat(),
        retry_after_seconds=30.0, consecutive_failures=1,
        observed_at=now.isoformat(), last_success_at=None)
    storage.save_chain_backoff(entry)

    def _raise_fetch_error(symbol: str):
        raise FetchError("上游真的掛了")

    c = TestClient(create_app(
        identity_resolver=lambda: "solo", fetch=_raise_fetch_error,
        storage=storage, global_vendor_daily_budget=0))
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "rate_limited"


# ---------- 5. Super Admin 不豁免 ----------


def test_super_admin_is_not_exempt_from_the_fuse_when_using_the_product():
    """PB-06 原文測的是當時唯一的「elevated tier」（PB-09 的 Super
    User）——三層角色模型上線後，那一層在字面上對應到今天的 Super
    Admin（`ADMIN_SECRET` 唯一的正式後繼者），機制換成 role session
    cookie，斷言意圖不變：Global Vendor Fuse 對這一層依然套用。
    Super User 層級的豁免範圍（Scenario quota／refresh 節流）與這裡
    無關，屬 AUTH-05（#312）的範圍，不在本票補測。"""
    storage = MemoryStorage()
    _seed_today_count(storage, 10)
    c = _client(storage=storage, global_vendor_daily_budget=10,
               role="superadmin")
    # 先確認這個 client 真的是 Super Admin——不是誤用一把打不開的
    # session。
    assert c.get("/api/auth/status").json() == {"role": "superadmin"}

    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "vendor_budget_exhausted"


# ---------- 6. 沒有任何路徑可以繞過（AC-9） ----------


def test_the_fuse_blocks_even_a_configured_custom_provider_before_it_is_ever_called():
    storage = MemoryStorage()
    storage.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="custom", provider="marketdata-app"),
        historical_iv=UsageSetting(mode="default"),
        updated_at=now_utc_iso(), owner_id="solo"))
    storage.save_credential(ProviderCredential(
        provider="marketdata-app", token="tok", updated_at=now_utc_iso(),
        owner_id="solo"))
    _seed_today_count(storage, 10)

    custom_calls: list[str] = []

    def _custom_fetch(provider: str, symbol: str, token: str):
        custom_calls.append(symbol)
        raise AssertionError("fuse 應該在呼叫自訂來源之前就短路")

    c = TestClient(create_app(
        identity_resolver=lambda: "solo",
        fetch=lambda symbol: load_snapshot(FIX),
        custom_fetch=_custom_fetch, storage=storage,
        global_vendor_daily_budget=10))
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 429
    assert custom_calls == []


def test_the_ad_hoc_analyze_endpoint_is_also_blocked_by_the_fuse():
    storage = MemoryStorage()
    _seed_today_count(storage, 10)
    c = _client(storage=storage, global_vendor_daily_budget=10)
    # `AnalyzeRequest.strategies` 認的是具體 subtype（`STRATEGIES`
    # 白名單），跟 `CreateScenarioRequest`／`NEW` 用的 family 白名單
    # 是兩個不同層次的詞彙（main.py 既有註解明講），不能沿用 `NEW`。
    r = post_adhoc(c, {
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["bull-call-spread"]})
    assert r.status_code == 429
    assert r.status_code < 500
    assert r.json()["detail"]["stage"] == "vendor_budget_exhausted"


# ---------- 純函式層：vendor_fuse.tripped() ----------


def test_tripped_is_false_when_budget_disabled():
    storage = MemoryStorage()
    _seed_today_count(storage, 999)
    assert vendor_fuse.tripped(storage, ny_today(), 0) is False
    assert vendor_fuse.tripped(storage, ny_today(), -1) is False


def test_tripped_is_true_at_and_above_the_threshold_false_below_it():
    storage = MemoryStorage()
    _seed_today_count(storage, 9)
    assert vendor_fuse.tripped(storage, ny_today(), 10) is False
    _seed_today_count(storage, 1)  # 累加到 10
    assert vendor_fuse.tripped(storage, ny_today(), 10) is True


def test_tripped_fails_open_when_the_storage_read_itself_raises():
    class _BrokenStorage:
        def metric_total(self, metric: str, bucket: str) -> int:
            raise RuntimeError("storage 掛了")

    assert vendor_fuse.tripped(_BrokenStorage(), ny_today(), 10) is False


def test_global_vendor_fuse_tripped_is_a_fetch_error_subclass():
    """既有降級鏈（`_fetch_chain()` 往上層一律 `except FetchError`）
    因此不會因為多了這個新狀態而意外改變既有行為。"""
    assert issubclass(vendor_fuse.GlobalVendorFuseTripped, FetchError)


# 第 3 個接縫（Storage port 契約，memory＋真 Postgres 雙後端）的
# `metric_total()` 覆蓋收在 `test_storage_contract.py` 既有「S0 最小
# 可觀測性」區塊（比照全站既有慣例，儲存層契約測試集中一處，不散落
# 在各票各自的檔案裡）。
