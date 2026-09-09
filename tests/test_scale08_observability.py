"""SCALE-08（#258，Scaling Foundation S0：最小可觀測性，七項指標封頂）。

`api_app/storage/__init__.py`／`memory.py`／`postgres.py` 的
`MetricEntry`／`record_metric()`／`metric_summary()`／
`table_size_metrics()` 由 `tests/test_storage_contract.py` 的
「S0 最小可觀測性」區塊覆蓋（雙後端）。這裡專注在 `create_app()` 這一層
的接線——七類指標各自真的在哪個既有動作發生時被記錄、operator 端點、
以及 AC-4／AC-5／AC-6 這幾條跟「不干擾產品」直接相關的斷言。

## AC 對照

- AC-1：`test_ops_metrics_endpoint_answers_all_seven_categories`
- AC-2：`test_metric_catalogue_is_exactly_seven`
- AC-3：見 `test_storage_contract.py`
- AC-4：`test_metrics_on_or_off_produces_byte_identical_product_api_responses`
- AC-5：`test_a_broken_metrics_backend_does_not_break_the_refresh_flow`
- AC-6：`test_ops_metrics_endpoint_requires_authorization`
- AC-7：見 `test_storage_contract.py::test_metric_entry_has_no_disallowed_fields`
"""
import dataclasses
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.metrics import METRIC_CATALOGUE, PERSISTED_METRICS
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import RateLimitedError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
OPS_AUTH = {"Authorization": "Bearer ops-secret"}


def _fresh_snapshot():
    snap = load_snapshot(FIX)
    return dataclasses.replace(
        snap, fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _client(monkeypatch, *, storage=None, ops_secret="ops-secret",
           snap=None, **overrides):
    """刻意**不**覆寫 `fetch=`——`create_app()` 只有在 `fetch is
    service.fetch_chain`（未被覆寫）時才會走 `_default_fetch()`，而
    指標 #1／#2（chain fetch／429 count）只包在 `_default_fetch()`
    內部的 `_metered_chain_fetch()`。改成 monkeypatch `cboe.
    fetch_chain` 本身（比照 `test_scale04_chain_backoff.py`／
    `test_scale06_ownership_expand.py` 既有手法），讓 production 預設
    路徑真的被走到，指標才有機會被記錄。

    `snap`：選填，讓需要比較兩個獨立 client 之行為的測試（AC-4）能
    共用**同一個**快照物件——否則各自呼叫 `_fresh_snapshot()` 會各自
    取到不同的 `fetched_at`，而 `analyzed_at` 直接就是快照的
    `fetched_at`（既有既定語意），兩個 client 的回應會因為這個與
    metrics 開關完全無關的理由而不同，讓比對失去意義。"""
    from option_chaser.data import cboe

    snap = snap if snap is not None else _fresh_snapshot()
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    return TestClient(create_app(storage=storage or MemoryStorage(),
                                 ops_secret=ops_secret, **overrides))


def _create_and_refresh(client, symbol="XYZ"):
    r = client.post("/api/scenarios", json={**NEW, "symbol": symbol})
    sid = r.json()["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    return sid


# ---------- AC-2：catalogue 恰好七類 ----------

def test_metric_catalogue_is_exactly_seven():
    assert len(METRIC_CATALOGUE) == 7
    assert set(METRIC_CATALOGUE) == {
        "chain_fetch_count", "chain_429_count", "stale_serve_count",
        "cold_miss_count", "refresh_duration_ms", "table_size",
        "history_read_volume"}


def test_table_size_is_the_only_non_persisted_metric():
    """`table_size` 是 query-time gauge，不經過 `record()`；其餘六個
    才是真的寫進 `operational_metrics` 表的。"""
    assert set(METRIC_CATALOGUE) - set(PERSISTED_METRICS) == {"table_size"}
    assert len(PERSISTED_METRICS) == 6


def test_recording_an_unknown_metric_name_is_rejected():
    """新增第八類必須明確改 `METRIC_CATALOGUE`——不是隨便傳一個新字串
    就能悄悄生出一個新指標。"""
    import pytest

    from api_app import metrics as metrics_module

    with pytest.raises(AssertionError):
        metrics_module.record(MemoryStorage(), "totally_new_metric",
                              __import__("datetime").date(2026, 9, 6))


# ---------- AC-1：operator 端點一次回答全部七項 ----------

def test_ops_metrics_endpoint_answers_all_seven_categories(monkeypatch):
    storage = MemoryStorage()
    c = _client(monkeypatch, storage=storage)
    _create_and_refresh(c)

    r = c.get("/api/ops/metrics", headers=OPS_AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == set(METRIC_CATALOGUE)
    # 一次刷新至少會產生一筆 chain_fetch_count（真的抓過鏈）與一筆
    # refresh_duration_ms（真的完整跑完一次刷新）。
    assert body["chain_fetch_count"], "應該至少有一筆抓鏈紀錄"
    assert body["refresh_duration_ms"], "應該至少有一筆刷新耗時紀錄"
    assert body["table_size"]["results"]["row_count"] >= 1


def test_chain_fetch_and_history_read_volume_are_recorded_end_to_end(monkeypatch):
    storage = MemoryStorage()
    c = _client(monkeypatch, storage=storage)
    sid = _create_and_refresh(c)

    entries = storage.metric_summary()
    fetch_entries = [e for e in entries if e.metric == "chain_fetch_count"]
    assert fetch_entries
    assert fetch_entries[0].symbol == "XYZ"
    assert fetch_entries[0].source   # cboe 或 custom，視預設路徑而定

    # 走一次 /history，觸發 history_read_volume。
    c.get(f"/api/scenarios/{sid}/history",
         params={"candidate_key": "bull-call-spread|100|110|2026-08-07"})
    history_entries = [e for e in storage.metric_summary()
                       if e.metric == "history_read_volume"]
    assert history_entries
    assert history_entries[0].count >= 1


def test_refresh_duration_tracks_count_and_amount(monkeypatch):
    storage = MemoryStorage()
    c = _client(monkeypatch, storage=storage)
    _create_and_refresh(c)
    _create_and_refresh(c, symbol="ABC")

    (entry,) = [e for e in storage.metric_summary()
               if e.metric == "refresh_duration_ms"]
    assert entry.count == 2
    assert entry.total > 0
    assert entry.max_value >= entry.total / entry.count


def test_chain_429_is_recorded_separately_from_a_plain_fetch_failure():
    """429 記兩筆（`chain_429_count`＋`chain_fetch_count`，因為那也是一次
    真的打過上游的嘗試），一般失敗只記 `chain_fetch_count`。"""
    from option_chaser.data import cboe, yf

    storage = MemoryStorage()

    def rate_limited(symbol):
        raise RateLimitedError("429", retry_after_seconds=60.0)

    fallback = dataclasses.replace(_fresh_snapshot(), source="yfinance")
    c = TestClient(create_app(storage=storage, ops_secret="ops-secret"))
    import unittest.mock as mock
    with mock.patch.object(cboe, "fetch_chain", side_effect=rate_limited), \
         mock.patch.object(yf, "fetch_chain", return_value=fallback):
        r = c.post("/api/scenarios", json=NEW)
        c.post(f"/api/scenarios/{r.json()['id']}/refresh")

    entries = {(e.metric, e.source): e.count for e in storage.metric_summary()}
    assert entries.get(("chain_429_count", "cboe")) == 1
    assert entries.get(("chain_fetch_count", "cboe")) == 1
    assert entries.get(("chain_fetch_count", "yfinance")) == 1


# ---------- AC-6：operator-only ----------

def test_ops_metrics_endpoint_requires_authorization(monkeypatch):
    storage = MemoryStorage()
    c = _client(monkeypatch, storage=storage)
    _create_and_refresh(c)

    assert c.get("/api/ops/metrics").status_code == 401
    assert c.get("/api/ops/metrics",
                 headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_ops_secret_not_configured_fails_closed(monkeypatch):
    monkeypatch.delenv("OPS_SECRET", raising=False)
    c = _client(monkeypatch, ops_secret=None)
    r = c.get("/api/ops/metrics", headers={"Authorization": "Bearer Anything"})
    assert r.status_code == 401


def test_ops_secret_is_independent_from_cron_secret(monkeypatch):
    """不同的信任邊界，不共用同一把——cron 的 secret 對 ops 端點無效，
    反之亦然。"""
    c = _client(monkeypatch, ops_secret="ops-only-secret",
               cron_secret="cron-only-secret")
    assert c.get("/api/ops/metrics",
                 headers={"Authorization": "Bearer cron-only-secret"}
                 ).status_code == 401
    assert c.get("/api/cron/warm-rate-cache",
                 headers={"Authorization": "Bearer ops-only-secret"}
                 ).status_code == 401


# ---------- AC-4：觀測 ON/OFF 對產品 API 回應逐位元一致 ----------

def _strip_random_ids(body: dict) -> dict:
    """比對兩個獨立建立的劇本（各自隨機 id、各自真實 wall-clock
    `created_at`）之前，把「這個劇本是誰、什麼時候建立的」這些跟
    metrics 開關完全無關、但每次跑測試都會真的不同的欄位拿掉——AC-4
    要驗證的是「開關 metrics 有沒有改變回應內容」，不是「兩個不同的
    劇本剛好連建立時間都一樣」。

    `created_at`：`create_scenario()` 用 `now_utc_iso()`（秒精度）
    蓋章，兩個 client 各自的 `POST /api/scenarios` 呼叫若剛好跨過同一
    秒的邊界，這個欄位就會真的不同——第一版測試沒有濾掉它，在全套
    測試裡真的因為時間點不巧而紅過一次，不是理論風險。`analyzed_at`／
    `latest_analyzed_at` 不需要濾：它們是快照自己的 `fetched_at`
    （既有既定語意），呼叫端傳同一個 `snap` 物件時這兩個值本來就
    逐位元相同，不是靠運氣。`id` 在頂層與 `latest_result`（view dict
    本身回顯 `scenario_id`）各出現一次。"""
    body = dict(body)
    body.pop("id", None)
    body.pop("created_at", None)
    if body.get("latest_result"):
        body["latest_result"] = {k: v for k, v in body["latest_result"].items()
                                 if k != "scenario_id"}
    return body


def test_metrics_on_or_off_produces_byte_identical_product_api_responses(monkeypatch):
    storage_on = MemoryStorage()
    storage_off = MemoryStorage()
    shared_snap = _fresh_snapshot()   # 見 _client() docstring：兩邊必須共用同一份
    c_on = _client(monkeypatch, storage=storage_on, enable_metrics=True,
                   snap=shared_snap)
    c_off = _client(monkeypatch, storage=storage_off, enable_metrics=False,
                    snap=shared_snap)

    r_on = c_on.post("/api/scenarios", json=NEW)
    r_off = c_off.post("/api/scenarios", json=NEW)
    assert _strip_random_ids(r_on.json()) == _strip_random_ids(r_off.json())

    sid_on, sid_off = r_on.json()["id"], r_off.json()["id"]
    refresh_on = c_on.post(f"/api/scenarios/{sid_on}/refresh").json()
    refresh_off = c_off.post(f"/api/scenarios/{sid_off}/refresh").json()
    assert _strip_random_ids(refresh_on) == _strip_random_ids(refresh_off)

    detail_on = c_on.get(f"/api/scenarios/{sid_on}").json()
    detail_off = c_off.get(f"/api/scenarios/{sid_off}").json()
    assert _strip_random_ids(detail_on) == _strip_random_ids(detail_off)

    # 關閉時，storage 裡完全沒有 operational_metrics 紀錄；開啟時有。
    assert storage_off.metric_summary() == []
    assert storage_on.metric_summary() != []


# ---------- AC-5：觀測失敗 fail-open ----------

def test_a_broken_metrics_backend_does_not_break_the_refresh_flow(monkeypatch):
    """`record_metric()` 本身炸掉時，主流程（建立→刷新）必須完全不受
    影響——`api_app.metrics.record()` 的 try/except 是這個保證的
    落地點。"""
    class _BrokenMetricsStorage(MemoryStorage):
        def record_metric(self, *args, **kwargs):
            raise RuntimeError("metrics 後端暫時掛了")

    storage = _BrokenMetricsStorage()
    c = _client(monkeypatch, storage=storage)

    r = c.post("/api/scenarios", json=NEW)
    assert r.status_code == 201
    refresh = c.post(f"/api/scenarios/{r.json()['id']}/refresh")
    assert refresh.status_code == 200, refresh.text


def test_a_broken_metrics_backend_does_not_break_history_or_chain_fetch_paths(monkeypatch):
    """AC-5 明列的其餘主流程（history、429、Treasury 路徑本身）同樣
    不受記錄失敗影響——`refresh` 已在上一條測試驗證過，這裡補
    `/history` 與一次帶 429 的刷新。"""
    from option_chaser.data import cboe

    class _BrokenMetricsStorage(MemoryStorage):
        def record_metric(self, *args, **kwargs):
            raise RuntimeError("metrics 後端暫時掛了")

    storage = _BrokenMetricsStorage()
    c = _client(monkeypatch, storage=storage)
    sid = _create_and_refresh(c)

    history = c.get(f"/api/scenarios/{sid}/history",
                    params={"candidate_key":
                           "bull-call-spread|100|110|2026-08-07"})
    assert history.status_code == 200, history.text

    def rate_limited(symbol):
        raise RateLimitedError("429", retry_after_seconds=60.0)

    import unittest.mock as mock

    from option_chaser.data import yf
    fallback = dataclasses.replace(_fresh_snapshot(), source="yfinance")
    with mock.patch.object(cboe, "fetch_chain", side_effect=rate_limited), \
         mock.patch.object(yf, "fetch_chain", return_value=fallback):
        r2 = c.post("/api/scenarios", json={**NEW, "symbol": "DEF"})
        refresh2 = c.post(f"/api/scenarios/{r2.json()['id']}/refresh")
    assert refresh2.status_code == 200, refresh2.text
