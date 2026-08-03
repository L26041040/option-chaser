"""劇本 CRUD／分析／歷史的 HTTP API 測試（V2／#50）。

後端唯一接縫＝HTTP API（spec #47）：儲存行為一律從 API 外部驗證，
不直接戳記憶體假體的內部狀態。假體與 Postgres adapter 的行為一致性
由 `tests/test_storage_contract.py` 保證（同一份契約、兩個實作都跑），
所以這裡用假體驗出來的結論對正式環境也成立。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- 建立與列出 ----------

def test_created_scenario_comes_back_with_an_id_and_mvp_defaults():
    sc = _create(_client())
    assert sc["id"]
    assert sc["symbol"] == "XYZ"
    assert sc["target_price"] == 130.0
    assert sc["target_month"] == "2026-09"
    assert sc["created_at"]
    assert sc["archived_at"] is None
    # 三欄表單（spec #47）：方向與策略是 MVP 固定值，不由前端送。
    assert sc["direction"] == "bullish"
    assert sc["strategies"] == ["bull-call-spread"]


def test_created_scenario_appears_in_the_list():
    c = _client()
    sc = _create(c)
    listed = c.get("/api/scenarios").json()
    assert [s["id"] for s in listed] == [sc["id"]]


def test_scenarios_persist_across_requests_in_the_same_storage():
    storage = MemoryStorage()
    sc = _create(_client(storage))
    # 換一個 app 實例（模擬 serverless 的下一次冷啟動），資料仍在
    assert _client(storage).get(f"/api/scenarios/{sc['id']}").json()["id"] == sc["id"]


def test_unknown_scenario_is_404():
    assert _client().get("/api/scenarios/nope").status_code == 404


def test_target_month_already_past_is_rejected():
    """生下來就過期的劇本不該存在（沿用既有 `ensure_month_open` 規則）。"""
    r = _client().post("/api/scenarios", json={**NEW, "target_month": "2020-01"})
    assert r.status_code == 400


def test_malformed_create_body_is_422():
    assert _client().post("/api/scenarios", json={"symbol": "XYZ"}).status_code == 422


# ---------- 封存＝軟刪除 ----------

def test_archiving_removes_it_from_the_list_but_keeps_the_record():
    c = _client()
    sc = _create(c)
    assert c.post(f"/api/scenarios/{sc['id']}/archive").status_code == 200

    assert c.get("/api/scenarios").json() == []
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["archived_at"] is not None


def test_archiving_is_idempotent_and_404s_on_unknown():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive")
    assert c.post(f"/api/scenarios/{sc['id']}/archive").status_code == 200
    assert c.post("/api/scenarios/nope/archive").status_code == 404


# ---------- 分析與結果歷史 ----------

def test_analyze_stores_a_result_readable_from_the_detail_endpoint():
    c = _client()
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/analyze")
    assert r.status_code == 200
    view = r.json()
    assert view["meta"]["symbol"] == "XYZ"

    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["latest_result"]["meta"]["symbol"] == "XYZ"
    assert detail["latest_analyzed_at"] == view["analyzed_at"]


def test_analyze_on_unknown_scenario_is_404():
    assert _client().post("/api/scenarios/nope/analyze").status_code == 404


def test_result_history_lists_each_analysis_once():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/analyze")
    c.post(f"/api/scenarios/{sc['id']}/analyze")   # 同一份快照＝同一時間戳

    hist = c.get(f"/api/scenarios/{sc['id']}/results").json()
    # 冪等：重跑同一次快照不該在歷史裡留兩筆
    assert len(hist) == 1
    assert hist[0]["analyzed_at"]


def test_detail_without_any_analysis_says_so_rather_than_faking_it():
    c = _client()
    sc = _create(c)
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["latest_result"] is None
    assert detail["latest_analyzed_at"] is None


def test_analysis_failure_maps_to_502_and_is_not_stored():
    from option_chaser.models import FetchError

    def boom(symbol):
        raise FetchError("data source down")

    storage = MemoryStorage()
    c = TestClient(create_app(fetch=boom, storage=storage))
    sc = _create(c)
    assert c.post(f"/api/scenarios/{sc['id']}/analyze").status_code == 502
    assert c.get(f"/api/scenarios/{sc['id']}/results").json() == []


# ---------- 事件紀錄 ----------

def test_creating_and_analysing_leave_an_audit_trail():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/analyze")
    c.post(f"/api/scenarios/{sc['id']}/archive")

    events = c.get(f"/api/scenarios/{sc['id']}/events").json()
    assert [e["event"] for e in events] == [
        "SCENARIO_CREATED", "ANALYSIS_COMPLETED", "SCENARIO_ARCHIVED"]


# ---------- 健康檢查如實回報實際用的儲存後端 ----------

def test_health_reports_which_storage_backend_is_actually_in_use():
    body = _client().get("/api/health").json()
    assert body["storage"] == "memory"


def test_api_layer_never_touches_sql_directly():
    """AC：API 層只透過儲存介面存取資料。以「main.py 不認識 psycopg／
    不含 SQL 關鍵字」這個結構性事實表達——換掉儲存後端時不需要動它。"""
    src = open("api_app/main.py", encoding="utf-8").read()
    for forbidden in ("psycopg", "SELECT ", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in src, f"main.py 不該出現 {forbidden!r}"


def test_analyze_also_persists_the_raw_option_chain_snapshot():
    """view dict 沒有逐筆合約報價——V8 的「原始資料 CSV」要的是原始快照，
    所以分析當下就得把它一起存起來，事後補不回來。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc = _create(c)
    view = c.post(f"/api/scenarios/{sc['id']}/analyze").json()

    snap = storage.get_snapshot(sc["id"], view["analyzed_at"])
    assert snap is not None
    assert snap["symbol"] == "XYZ"
    assert snap["contracts"], "快照要含逐筆合約，不是只有 meta"
