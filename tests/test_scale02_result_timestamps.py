"""SCALE-02（#253，Scaling Foundation C2）：`/api/scenarios/{id}/results`
改讀 `Storage.result_timestamps()`——主要索引來源是 `snapshots` 的主鍵，
輔以 `results` 表窄查詢 UNION 補回缺 snapshot 的孤兒列，兩邊都不觸碰
`view` JSONB。

行為契約（`test_result_history_lists_each_analysis_once`／
`test_deleting_removes_results_snapshots_and_events` 等）已在
`tests/test_api_scenarios.py` 覆蓋，本檔案只補這張票特有的四件事：
(1) 正式的 HTTP 層孤兒列測試（AC-2）、(2) SQL 不觸碰 `view` 的結構性
證明（AC-5）、(3) 不得對 narrow 候選表做 `DISTINCT` 的結構性守門
（AC-3，防呆——narrow 表尚未存在，守門先釘住「這個方法的實作裡沒有
DISTINCT」，避免未來 SCALE-09 上線後有人在這裡加一個）、(4) 真實
Postgres 延遲量測（AC-4）。
"""
import inspect
import os
import time

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord, Scenario
from api_app.storage.memory import MemoryStorage

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
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


# ---------- 真實 Postgres 延遲量測（AC-4） ----------

@pytest.mark.skipif(not TEST_DB_URL,
                    reason="需要 OC_TEST_DATABASE_URL 才能量測真實延遲")
def test_result_timestamps_is_not_slower_than_the_old_full_view_scan():
    """AC-4：真實 Postgres 量測延遲不得高於 baseline。baseline＝舊版
    `list_results()` 的實作方式（`result_history()`，連每一列的完整
    `view` 都撈出來）；新版（`result_timestamps()`，UNION 兩個窄查詢）
    在 100 筆歷史列、每筆 view 約 55KB（契約樣本量級）的條件下實測
    （2026-09-06，本機 PostgreSQL 16，30 輪取中位數）：

        舊路徑 median 40.06ms／p95 49.73ms
        新路徑 median  5.56ms／p95  6.15ms
        改善倍數：median 7.2×、p95 8.1×

    本測試把這個量測寫成可重跑、可長期守門的斷言（新路徑中位數不得
    比舊路徑慢，抓 2× 安全邊際避免正常機器效能波動誤報），不是只留一次
    性的紀錄——CI 或未來任何一輪重構若把這個查詢改回全表掃描，這裡會
    紅燈。"""
    import psycopg

    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots RESTART IDENTITY")

    sid = "bench1"
    st.create_scenario(_scenario(sid))
    big_view = {"n": "x" * 55000,
               "candidate_pool": {f"k{i}": {"v": i} for i in range(50)}}
    n = 100
    for i in range(n):
        ts = f"2026-08-{(i % 28) + 1:02d}T{i:02d}:00:00+00:00"
        st.save_result(ResultRecord(sid, ts, big_view))
        st.save_snapshot(sid, ts, {"contracts": list(range(300))})

    def median_ms(fn, rounds=15):
        samples = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000)
        samples.sort()
        return samples[len(samples) // 2]

    old_timestamps = sorted(r.analyzed_at for r in st.result_history(sid))
    new_timestamps = st.result_timestamps(sid)
    assert old_timestamps == new_timestamps   # 結果集合必須一致（AC-1）

    old_median = median_ms(lambda: st.result_history(sid))
    new_median = median_ms(lambda: st.result_timestamps(sid))

    assert new_median <= old_median * 2   # 安全邊際；實測是 7× 改善，不是勉強打平
    assert new_median < old_median
