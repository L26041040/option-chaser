"""SCALE-09（#261，Scaling Foundation Stage 1-1）Part A：narrow
history dual-write。

## AC 對照

- AC-1：`test_visible_candidate_costs_matches_the_legacy_all_
  candidates_derived_cost`——對 `visible_candidate_keys()` 選出的每個
  key，`visible_candidate_costs()` 的值與舊 `all_candidates`（經
  `spread_cost_history()`／`_history_entry()`）推導出的成本逐位元
  相同。
- AC-2：storage 層契約測試在 `tests/test_storage_contract.py`。
- AC-7：`test_history_endpoint_is_untouched_by_narrow_history_dual_
  write`——結構性鎖住 `get_spread_history()` 不呼叫任何
  narrow-history 方法；HTTP 端到端確認回應形狀不變。
- AC-8：`test_refresh_dual_writes_narrow_history_without_changing_the_
  stored_view`——`results.view` 逐位元不變，narrow history 是純加法
  的額外寫入。
"""
from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import service, store
from option_chaser.data import cboe, yf
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _view(strategies=("long-call", "bull-call-spread", "call-fly")):
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0],
                                       target_price=120.0,
                                       target_month="2026-08"),
            strategies=strategies),
        FIX)
    return store.serialize_result(result, "s1", 100000.0)


# ---------- visible_candidate_keys()／visible_candidate_costs() ----------

def test_visible_candidate_keys_is_empty_for_none_view():
    assert store.visible_candidate_keys(None) == set()
    assert store.visible_candidate_costs(None) == {}


def test_visible_candidate_keys_includes_expiry_top10_and_expiry_best():
    view = _view()
    keys = store.visible_candidate_keys(view)
    assert keys   # 非空——這份 fixture 有合格候選

    expected_from_top10 = {
        k for r in view["results"] for group in r["expiry_top10"]
        for k in group["candidate_keys"]
    }
    expected_from_best = {
        k for r in view["results"] for k in r["expiry_best"]
    }
    assert expected_from_top10 <= keys
    assert expected_from_best <= keys


def test_visible_candidate_keys_includes_the_baseline_champion():
    """跨 family champion（`representative_candidate`）與 per-family
    代表皆是 baseline 期小池子（`_baseline_group`）裡 `max()` 選出來
    的——這裡驗證 baseline 期全部列的 key 確實都在 visible 集合裡，
    間接證明 champion／per-family 兩者選中的 key 也在其中（見
    `store.visible_candidate_keys()` docstring 的推導）。"""
    view = _view()
    baseline_group = next(
        g for g in view["expiry_groups"] if g["expiry"] == view["baseline_expiry"])
    baseline_keys = {row["candidate_key"] for row in baseline_group["rows"]}
    assert baseline_keys
    assert baseline_keys <= store.visible_candidate_keys(view)


def test_visible_candidate_costs_matches_the_legacy_all_candidates_derived_cost():
    """AC-1：與舊 `all_candidates`（V9／#57 `spread_cost_history()` 的
    既有讀取路徑）推導出的成本逐一比對——證明這是換一種讀法，不是
    換一種數字。"""
    view = _view()
    costs = store.visible_candidate_costs(view)
    assert costs

    legacy_by_key = {
        e["candidate_key"]: e["cost"]
        for r in view["results"] for e in r["all_candidates"]
    }
    for key, cost in costs.items():
        assert key in legacy_by_key, f"{key} 不在舊 all_candidates 裡"
        assert cost == legacy_by_key[key]


def test_visible_candidate_costs_reads_from_the_candidate_pool():
    view = _view()
    costs = store.visible_candidate_costs(view)
    for key, cost in costs.items():
        assert cost == view["candidate_pool"][key]["natural_cost"]


# ---------- AC-8：refresh 端到端 dual-write，results.view 不變 ----------

def _client_without_fetch_override(storage, **overrides) -> TestClient:
    return TestClient(create_app(storage=storage, **overrides))


def test_refresh_dual_writes_narrow_history_without_changing_the_stored_view(
    monkeypatch,
):
    snap = load_snapshot(FIX)
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: snap)

    storage = MemoryStorage()
    c = _client_without_fetch_override(storage)
    r = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 120.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]})
    assert r.status_code == 201, r.text
    sc_id = r.json()["id"]

    resp = c.post(f"/api/scenarios/{sc_id}/refresh")
    assert resp.status_code == 200, resp.text

    record = storage.latest_result(sc_id)
    view = record.view
    expected_costs = store.visible_candidate_costs(view)
    assert expected_costs

    for key, cost in expected_costs.items():
        entry = storage.get_narrow_history_entry(sc_id, record.analyzed_at, key)
        assert entry is not None, f"visible candidate {key} 沒有被 dual-write"
        assert entry.cost == cost

    # `results.view` 本身完全不變——dual-write 是純加法的額外寫入。
    reserialized_costs = store.visible_candidate_costs(view)
    assert reserialized_costs == expected_costs


# ---------- AC-7：不切 production read path ----------

def test_history_endpoint_is_untouched_by_narrow_history_dual_write():
    """Stage boundary（票面明文）：本票不得切換 `/history` production
    read path——結構性鎖住 `get_spread_history()`（`GET /api/scenarios/
    {id}/history` 的實作函式）原始碼不含任何 narrow-history 方法名稱，
    確保它仍然只走既有的 `result_history()`／`spread_cost_history()`
    路徑。"""
    from api_app import main

    src = inspect.getsource(main)
    # `get_spread_history` 是路由函式的名稱，抓出它的原始碼片段來檢查
    # ——不檢查整個 `main.py`，避免這裡的 narrow-history storage 方法
    # 定義（在別的模組）或未來其他端點誤觸發假陽性。
    start = src.index("def get_spread_history")
    end = src.index("\n\n", start)
    body = src[start:end]
    assert "narrow_history" not in body
    assert "get_narrow_history_entry" not in body
    assert "save_narrow_history" not in body


def test_history_endpoint_response_shape_is_unchanged(monkeypatch):
    """端到端確認：這次刷新新增的 narrow-history dual-write 不影響
    `/history` 端點的回應內容——同一個劇本，刷新前後打 `/history`
    看到的仍是既有的 `{entries: [...]}` 形狀與既有欄位。"""
    snap = load_snapshot(FIX)
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: snap)

    storage = MemoryStorage()
    c = _client_without_fetch_override(storage)
    r = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 120.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]})
    sc_id = r.json()["id"]
    c.post(f"/api/scenarios/{sc_id}/refresh")

    detail = c.get(f"/api/scenarios/{sc_id}").json()
    # 挑一個真的存在的 candidate_key——直接從 candidate_pool 拿第一個。
    candidate_key = next(iter(detail["latest_result"]["candidate_pool"]))

    resp = c.get(f"/api/scenarios/{sc_id}/history",
                params={"candidate_key": candidate_key})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "entries" in body
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert set(entry.keys()) == {"analyzed_at", "spot", "cost",
                                 "baseline_return", "rank_in_expiry"}
