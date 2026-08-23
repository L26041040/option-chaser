"""V8（#56）：原始資料（當次快照）——查看與 CSV 下載，經 HTTP API 驗證
（後端唯一接縫，spec #47）。

CSV 內容正確性本就由既有純函式 `data.snapshot.snapshot_to_csv` 的測試
覆蓋（QA1-10／#37）；這裡只驗證「接線」——端點真的把 refresh 時存進去
的那份原始快照原樣交出來，JSON 查看與 CSV 下載走的是同一份資料。
"""
from datetime import timedelta

from fastapi.testclient import TestClient

from api_app import chain_cache
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot, snapshot_to_csv

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}


def _client(*, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap, storage=storage or MemoryStorage()))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_raw_data_before_any_analysis_is_404():
    c = _client()
    sc = _create(c)
    resp = c.get(f"/api/scenarios/{sc['id']}/raw-data")
    assert resp.status_code == 404


def test_raw_data_csv_before_any_analysis_is_404():
    c = _client()
    sc = _create(c)
    resp = c.get(f"/api/scenarios/{sc['id']}/raw-data.csv")
    assert resp.status_code == 404


def test_raw_data_unknown_scenario_is_404():
    c = _client()
    assert c.get("/api/scenarios/nope/raw-data").status_code == 404
    assert c.get("/api/scenarios/nope/raw-data.csv").status_code == 404


def test_raw_data_json_reaches_the_endpoint_after_a_refresh():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    raw = c.get(f"/api/scenarios/{sc['id']}/raw-data").json()

    snap = load_snapshot(FIX)
    assert raw["meta"]["symbol"] == snap.symbol
    assert raw["meta"]["spot"] == snap.spot
    assert raw["meta"]["source"] == snap.source
    assert raw["meta"]["contract_count"] == len(snap.contracts)
    assert len(raw["contracts"]) == len(snap.contracts)
    # 逐筆合約的完整原樣，不是候選腿專用的精簡子集——`last` 是 `_leg()`
    # 故意省略、但原始資料表不該省略的欄位。
    assert "last" in raw["contracts"][0]


def test_raw_data_meta_matches_the_analysis_view_meta():
    """查看區的 meta（symbol／spot／source）要跟同一次分析的 `meta` 一致
    ——兩處若各自算一份，數字對不上就是「亂掰」的另一種形式。"""
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    raw = c.get(f"/api/scenarios/{sc['id']}/raw-data").json()
    view = c.get(f"/api/scenarios/{sc['id']}").json()["latest_result"]

    assert raw["meta"]["symbol"] == view["meta"]["symbol"]
    assert raw["meta"]["spot"] == view["meta"]["spot"]
    assert raw["meta"]["source"] == view["meta"]["source"]


def test_raw_data_csv_matches_the_pure_function_output_byte_for_byte():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    resp = c.get(f"/api/scenarios/{sc['id']}/raw-data.csv")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text == snapshot_to_csv(load_snapshot(FIX))


def test_raw_data_json_and_csv_carry_the_same_row_count():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    raw = c.get(f"/api/scenarios/{sc['id']}/raw-data").json()
    csv_text = c.get(f"/api/scenarios/{sc['id']}/raw-data.csv").text
    csv_data_rows = len(csv_text.strip("\n").splitlines()) - 1   # 扣掉表頭

    assert len(raw["contracts"]) == csv_data_rows


def test_raw_data_follows_the_latest_refresh_not_a_stale_one(monkeypatch):
    """原始資料跟著「最新一次結果」的 `analyzed_at` 走——重刷後拿到的
    要是新的那份快照，不是第一次刷新時存的舊資料。"""
    import dataclasses

    # PERF-06（#182）：這裡刻意對同一個 symbol 連續觸發兩次「真的重新
    # 抓一次」，跟短效期 chain cache 的設計目的直接衝突，關掉這裡的
    # 快取重用——這條測試驗證的是「回應跟著最新結果走」，不是在測
    # chain cache 本身。
    monkeypatch.setattr(chain_cache, "CHAIN_CACHE_TTL", timedelta(seconds=0))
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    newer = dataclasses.replace(load_snapshot(FIX), fetched_at="2026-07-16T09:30:00-04:00")
    c2 = TestClient(create_app(fetch=lambda symbol: newer, storage=storage))
    c2.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    raw = c2.get(f"/api/scenarios/{sc['id']}/raw-data").json()
    assert raw["meta"]["fetched_at"] == "2026-07-16T09:30:00-04:00"
