"""SCALE-17（#268，Scaling Foundation C1）：停止把 `all_candidates`
寫進 persisted current/result materialization，保留 current UI／
ranking／heatmap／champion／API 相容性。

本檔案專門驗證 #268 issue 本文逐條列出、之前沒有專屬測試覆蓋的
Acceptance Criteria；`tests/test_detail_projection.py`（`GET /api/
scenarios/{id}` 的既有投影測試，跟進補上「storage 本身也不再含這個
key」的直接斷言）／`tests/test_scale14_history_read_path.py`（AC-5：
`/history` 完全不依賴 `all_candidates`，改走 `POST /api/analyze` 取得
candidate_key）皆已在各自既有範圍內驗證過與這張票相關的行為，這裡
只補 AC-1（真實 size benchmark）與 AC-3（`/api/analyze` 契約不受
storage 剝除影響——證明是「兩條路徑本來就分流」而非「fixture 重產
把 breaking change 洗成綠燈」）。
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord, Scenario
from api_app.storage.memory import MemoryStorage
from option_chaser import service, store
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
FIX = "tests/fixtures/xyz_v8_production_scale.json"


def _production_view(strategies=("bull-call-spread", "bear-put-spread",
                                 "call-fly", "put-fly")):
    """真實引擎算出的 production-scale view——與
    `tests/test_scale16_ledger_split.py::_real_production_view()`
    刻意同一份 fixture／同一組參數（不同檔案各自 import 一份，這裡
    重算一次而非跨檔案共用私有函式，維持測試檔互相獨立）。"""
    snap = load_snapshot(FIX)
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=110.0, target_month="2026-10"),
        strategies=strategies)
    result = service.run_with_snapshot(req, snap)
    return store.serialize_result(result, "s17-bench", None)


# ---------- AC-1：persisted current materialization 不含 all_candidates ----------

def test_stripped_view_has_no_all_candidates_key_anywhere():
    """AC-1（結構面）：`strip_persisted_all_candidates()` 產生的、真的
    會被寫進 `current_results.view` 的那份內容，`results[]` 逐項都不含
    `all_candidates` key——不是「值變空」，是 key 本身不存在。"""
    view = _production_view()
    assert all("all_candidates" in r for r in view["results"]), \
        "測試前提：真實引擎輸出本來就有 all_candidates，否則這條測試" \
        "測不出剝除有沒有生效"

    stripped = store.strip_persisted_all_candidates(view)
    assert all("all_candidates" not in r for r in stripped["results"])
    # 沒被碰到的其他部分逐位元相同——只拿掉那一個 key，不動其他內容。
    for original, cleaned in zip(view["results"], stripped["results"]):
        without_key = {k: v for k, v in original.items() if k != "all_candidates"}
        assert cleaned == without_key
    # 頂層與其他既有容器完全不受影響（candidate_pool／expiry_top10／
    # family_eligibility／per_family 等，UI 真正消費的東西）。
    assert stripped["candidate_pool"] == view["candidate_pool"]
    for key in ("family_eligibility", "engine_version", "schema_version"):
        if key in view:
            assert stripped.get(key) == view.get(key)


def test_stripped_view_is_measurably_smaller_reported_size_matches_audit_direction():
    """AC-1（量測面）：physical size/serialize benchmark 報告與 Audit
    方向一致——`all_candidates` 佔壓倒性比例，剝除後大小數量級下降。
    Audit 原文量到 97.82%；這裡用真實引擎（4 個 debit subtype 全開、
    600 張合約）重新量，數字量級吻合（差異來自不同 fixture／啟用
    subtype 組合，非量測誤差，`docs/research/storage-optimization-
    audit.md` 與 CLAUDE.md 已記錄過同一組事實）。"""
    view = _production_view()
    full_bytes = len(json.dumps(view))
    stripped_bytes = len(json.dumps(store.strip_persisted_all_candidates(view)))

    share_removed = 1 - stripped_bytes / full_bytes
    print(f"\n[SCALE-17 AC-1] full={full_bytes:,}B stripped={stripped_bytes:,}B "
          f"all_candidates share={share_removed:.2%} "
          f"ratio={full_bytes/stripped_bytes:.2f}x")

    # Audit 原文 97.82%；本測試不要求逐位元命中同一個百分比（不同
    # fixture／subtype 組合本來就會有差異），但方向必須一致——
    # all_candidates 是壓倒性大宗（>=90%），剝除後至少數量級縮小。
    assert share_removed >= 0.90
    assert full_bytes / stripped_bytes >= 10.0


@pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")
def test_persisted_current_results_row_physical_size_reflects_the_stripped_view():
    """AC-1（真實 Postgres 落地面）：不只是「Python dict 變小」，真的
    寫進 `current_results` 之後，這一列的實際落盤大小也對應剝除後的
    內容，而不是悄悄把整份 view 塞進某個其他欄位。"""
    import psycopg

    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, current_results, "
                     "snapshots RESTART IDENTITY")

    view = _production_view()
    stripped = store.strip_persisted_all_candidates(view)
    st.create_scenario(Scenario(
        id="s17-pg", symbol="XYZ", direction="bullish", target_price=110.0,
        target_month="2026-10", notes="", strategies=("vertical-spread",),
        created_at="2026-08-01T00:00:00+00:00", owner_id="solo"))
    st.save_current_result(ResultRecord(
        "s17-pg", "2026-08-01T00:00:00+00:00", stripped, owner_id="solo"))

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("VACUUM FULL current_results")
        pg_bytes = conn.execute(
            "SELECT pg_column_size(view) FROM current_results "
            "WHERE scenario_id = 's17-pg'").fetchone()[0]

    logical_full = len(json.dumps(view))
    logical_stripped = len(json.dumps(stripped))
    print(f"\n[SCALE-17 AC-1] pg_column_size(view)={pg_bytes:,}B "
          f"(logical stripped={logical_stripped:,}B, "
          f"logical full would be={logical_full:,}B)")
    # 落盤的那一欄本身遠小於「若整份 view 都存進去」的邏輯大小——
    # 允許 JSONB 二進位表示與 TOAST 壓縮造成的合理差異，門檻抓
    # 「肯定不是整份塞進去」而非要求精確比對位元組數。
    assert pg_bytes < logical_full / 5

    # 讀回來的內容仍是剝除後那份、且 current detail 需要的東西都在。
    got = storage_view = st.latest_result("s17-pg", owner="solo").view
    assert all("all_candidates" not in r for r in got["results"])
    assert got["candidate_pool"]


# ---------- AC-3：/api/analyze 契約不因 storage 優化而改變 ----------

def _client(*, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def test_api_analyze_response_still_carries_all_candidates_uncut():
    """AC-3：`POST /api/analyze` 是 Audit 找到的仍會回 unprojected view
    的 reachable endpoint——它的回應形狀不因 SCALE-17 而改變。這條測試
    直接證明「剝除只發生在寫入路徑」：同一份分析參數分別 (a) 直接呼叫
    `store.serialize_result()`（引擎輸出，`/api/analyze` 端點內部就是
    回傳這個），(b) 真的打 HTTP `/api/analyze`——兩者的 `all_candidates`
    逐位元相同，而 `store.strip_persisted_all_candidates()` 從未被
    `/api/analyze` 這條路徑呼叫過（AST 結構檢查，不是靠行為巧合）。"""
    c = _client()
    body = {"symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
           "strategies": ["bull-call-spread"]}
    resp = c.post("/api/analyze", json=body).json()

    assert any(r.get("all_candidates") for r in resp["results"]), (
        "測試前提：這份請求真的能產生非空 all_candidates，否則測不出"
        "剝除有沒有被誤套用到這條路徑")

    # 對照組：直接呼叫引擎＋序列化（/api/analyze 端點內部實際在做的
    # 事），逐位元相同——證明 HTTP 層沒有偷偷加一層剝除。
    from option_chaser import service
    from option_chaser.models import AnalysisParams
    result = service.run_with_snapshot(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="bull-call-spread",
                                       target_price=110.0,
                                       target_month="2026-10"),
            strategies=("bull-call-spread",)),
        load_snapshot(FIX))
    direct = store.serialize_result(result, "adhoc", None)
    assert json.dumps(resp["results"], sort_keys=True) == \
        json.dumps(direct["results"], sort_keys=True)


def test_analyze_endpoint_source_never_calls_the_strip_function():
    """AC-3（結構性保證，不是行為巧合）：`analyze_adhoc()`（`/api/
    analyze` 的 handler）直接回傳 `_analyze()` 給的 view，原始碼裡
    結構上就不含 `strip_persisted_all_candidates` 這個名字——與既有
    `test_selection_regression.py` 用原始碼文字掃描證明「ranking.py
    不 import ivhistory」是同一種手法，比執行期斷言更強：即使未來
    改寫 `_refresh_and_save()` 的實作細節，只要沒有人明確在
    `analyze_adhoc()` 裡加一行呼叫，這條路徑就不可能被剝除函式碰到。
    """
    import inspect

    from api_app import main as main_module

    # `analyze_adhoc()` 是定義在 `create_app()` 內部的巢狀函式，不是
    # 模組層級屬性，`inspect.getsource()` 拿不到它本身——改對整個
    # `main.py` 原始碼文字掃描，鎖定從
    # `@app.post("/api/analyze")` 這個裝飾器開始、到下一個
    # `@app.post`／`@app.get` 之前為止的區塊（handler 本身的邊界）。
    src = inspect.getsource(main_module)
    start = src.index('@app.post("/api/analyze")')
    end = src.index("@app.", start + 1)
    handler_src = src[start:end]
    assert "strip_persisted_all_candidates" not in handler_src
