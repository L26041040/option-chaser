"""SCALE-02（#253，Scaling Foundation C2）：`/api/scenarios/{id}/results`
改讀 `Storage.result_timestamps()`——主要索引來源是 `snapshots` 的主鍵，
輔以 `results` 表窄查詢 UNION 補回缺 snapshot 的孤兒列，兩邊都不觸碰
`view` JSONB。

行為契約（`test_result_history_lists_each_analysis_once`／
`test_deleting_removes_results_snapshots_and_events` 等）已在
`tests/test_api_scenarios.py` 覆蓋，本檔案只補這張票特有的三件事：
(1) 正式的 HTTP 層孤兒列測試（AC-2）、(2) SQL 不觸碰 `view` 的結構性
證明（AC-5）、(3) 不得對 narrow 候選表做 `DISTINCT` 的結構性守門
（AC-3，防呆——narrow 表尚未存在，守門先釘住「這個方法的實作裡沒有
DISTINCT」，避免未來 SCALE-09 上線後有人在這裡加一個）。
"""
import inspect

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord, Scenario
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _client(*, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _scenario(sid="s1"):
    return Scenario(id=sid, symbol="XYZ", direction="bullish",
                    target_price=120.0, target_month="2026-08", notes="",
                    strategies=("vertical-spread",),
                    created_at="2026-08-01T00:00:00+00:00")


# ---------- HTTP 層：孤兒列不會消失（AC-2） ----------

def test_results_endpoint_recovers_a_result_row_missing_its_snapshot():
    """模擬 `_refresh_and_save()` 的 `save_result()`／`save_snapshot()`
    兩次獨立呼叫之間中斷——只讀 `snapshots` 的話這個時間戳會憑空消失，
    改讀 `result_timestamps()` 之後不會。"""
    storage = MemoryStorage()
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_result(ResultRecord("s1", "2026-08-02T00:00:00+00:00", {"n": 2}))
    storage.save_snapshot("s1", "2026-08-02T00:00:00+00:00", {"contracts": []})

    c = _client(storage=storage)
    hist = c.get("/api/scenarios/s1/results").json()

    assert [h["analyzed_at"] for h in hist] == [
        "2026-08-01T00:00:00+00:00", "2026-08-02T00:00:00+00:00"]


def test_results_endpoint_still_404s_on_an_unknown_scenario():
    c = _client()
    assert c.get("/api/scenarios/nope/results").status_code == 404


# ---------- 結構性守門：不觸碰 view、不對 narrow 做 DISTINCT（AC-3／AC-5） ----------

def test_postgres_result_timestamps_sql_never_selects_view():
    """AC-5：不 SELECT `results.view`——只檢查 SQL 字面（含引號的程式
    碼行）裡有沒有 `view` 這個詞，不掃整段 docstring（docstring 討論
    脈絡本身會提到「view」這個詞，那不是 SQL）。"""
    from api_app.storage.postgres import PostgresStorage
    source = inspect.getsource(PostgresStorage.result_timestamps)
    sql_lines = [line for line in source.splitlines()
                 if '"' in line or "'" in line]
    sql_text = " ".join(sql_lines).lower()
    assert "select" in sql_text
    assert "view" not in sql_text


def test_result_timestamps_implementation_never_uses_distinct():
    """AC-3：narrow 表尚未存在（SCALE-09 才建），這裡先釘住「這個方法
    的實作不使用 DISTINCT」——UNION 本身已經去重，未來若有人想在這裡
    加一段對 narrow 表的 `SELECT DISTINCT`（Prototype #065 實測慢
    12.6×），這條測試會先紅燈逼一次重新考慮。"""
    from api_app.storage.memory import MemoryStorage as MS
    from api_app.storage.postgres import PostgresStorage

    for impl in (MS, PostgresStorage):
        source = inspect.getsource(impl.result_timestamps)
        sql_lines = [line for line in source.splitlines()
                    if '"' in line or "'" in line]
        assert "distinct" not in " ".join(sql_lines).lower()


def test_result_timestamps_scenario_id_is_the_only_filter_argument():
    """票面備註：本方法只吃 `scenario_id`，供 SCALE-11 之後直接在這裡
    的 WHERE 子句上加 owner 過濾——用簽章本身鎖住這個介面形狀，避免
    日後不小心多塞一個會繞過 owner boundary 的參數。"""
    from api_app.storage import Storage
    sig = inspect.signature(Storage.result_timestamps)
    assert list(sig.parameters) == ["self", "scenario_id"]
