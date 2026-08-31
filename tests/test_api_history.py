"""V9（#57）：Spread 歷史走勢圖的 API 接縫——`GET /api/scenarios/{id}/history`，
經 HTTP 驗證聚合邏輯真的接得上儲存層（`Storage.result_history()`）。

聚合本身（`store.spread_cost_history`）的細節案例見
`tests/test_store_spread_history.py`；這裡只驗證端到端：多次刷新 → 多筆
`ResultRecord` → 端點如實聚合回一條時間序列，缺席那次是斷點。
"""
import dataclasses

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
# 118/122 Call Spread，到期 2026-09-18——fixture 本身就有這組合約。
KEY = "bull-call-spread|118|122|2026-09-18"


def _snapshot_with_bid(bid_118, bid_122, fetched_at):
    snap = load_snapshot(FIX)
    contracts = []
    for c in snap.contracts:
        if c.expiry == "2026-09-18" and c.strike == 118.0 and c.option_type == "call":
            c = dataclasses.replace(c, bid=bid_118)
        elif c.expiry == "2026-09-18" and c.strike == 122.0 and c.option_type == "call":
            c = dataclasses.replace(c, bid=bid_122)
        contracts.append(c)
    return dataclasses.replace(snap, contracts=tuple(contracts), fetched_at=fetched_at)


def _client(fetch, storage=None, **overrides):
    return TestClient(create_app(fetch=fetch, storage=storage or MemoryStorage(),
                                 **overrides))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_history_is_one_continuous_series_across_refreshes_with_a_gap():
    # T06（#190）：chain 快取已整組移除（ADR-0001），這裡連續對同一個
    # symbol 觸發三次「真的重新抓一次」的刷新（每次餵不同快照）不需要
    # 任何特殊處理，自然就會各自真的重新抓一次。
    storage = MemoryStorage()
    snapshots = [
        _snapshot_with_bid(2.2, 1.4, "2026-07-15T21:30:00-04:00"),   # 正常
        _snapshot_with_bid(0.0, 1.4, "2026-07-16T21:30:00-04:00"),   # 118 報價異常→缺席
        _snapshot_with_bid(2.3, 1.5, "2026-07-17T21:30:00-04:00"),   # 恢復
    ]

    c1 = _client(lambda symbol: snapshots[0], storage)
    sc = _create(c1)
    c1.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    for snap in snapshots[1:]:
        c = _client(lambda symbol, s=snap: s, storage)
        c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    r = c1.get(f"/api/scenarios/{sc['id']}/history",
              params={"candidate_key": KEY})
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 3
    assert entries[0]["cost"] is not None
    assert entries[1]["cost"] is None       # 缺席那次＝斷點
    assert entries[1]["analyzed_at"] == "2026-07-16T21:30:00-04:00"
    assert entries[1]["spot"] == snapshots[1].spot   # 斷點仍有更新時間與標的價
    assert entries[2]["cost"] is not None


def test_unknown_scenario_is_404():
    c = _client(lambda symbol: load_snapshot(FIX))
    r = c.get("/api/scenarios/nope/history", params={"candidate_key": KEY})
    assert r.status_code == 404


def test_never_refreshed_scenario_has_empty_history():
    c = _client(lambda symbol: load_snapshot(FIX))
    sc = _create(c)
    r = c.get(f"/api/scenarios/{sc['id']}/history", params={"candidate_key": KEY})
    assert r.status_code == 200
    assert r.json()["entries"] == []


def test_read_only_does_not_write_anything():
    """唯讀聚合——查詢歷史不改變任何已存的結果或事件（T11 既有裁示）。"""
    storage = MemoryStorage()
    c = _client(lambda symbol: load_snapshot(FIX), storage)
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    before_events = c.get(f"/api/scenarios/{sc['id']}/events").json()

    c.get(f"/api/scenarios/{sc['id']}/history", params={"candidate_key": KEY})
    c.get(f"/api/scenarios/{sc['id']}/history", params={"candidate_key": "some-other-key"})

    after_events = c.get(f"/api/scenarios/{sc['id']}/events").json()
    assert before_events == after_events


def test_unmatched_candidate_key_is_all_gaps_not_an_error():
    c = _client(lambda symbol: load_snapshot(FIX))
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    r = c.get(f"/api/scenarios/{sc['id']}/history",
             params={"candidate_key": "bull-call-spread|9999|10000|2099-01-01"})
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["cost"] is None
