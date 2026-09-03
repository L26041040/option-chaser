"""T13（#231，Initial V2 spec #217）：詳細頁 payload 投影與 top-N 上限。

`GET /api/scenarios/{id}` 曾經原樣回傳 `ResultRecord.view`（`store.
serialize_result()` 的完整輸出）——其中 `results[].candidates`（引擎
全量候選 key 清單，未經任何上限裁切）會把每一筆通過過濾的候選都拉進
`candidate_pool`，是「每多啟用一個 spread 策略就多約 495KB」的真正
成因。`results[].all_candidates`（V9 Spread 淨成本走勢的歷史序列）
同樣是前端從未消費、只服務 server 端查詢的完整序列。

`store.project_for_detail()` 只投影**這一個 HTTP 端點**要回傳的內容，
不動儲存層——落盤的 `ResultRecord.view` 維持 `serialize_result()`
原樣的全保真輸出，本檔案的測試逐一驗證這條界線。
"""
import json

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import store
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _offline_rate_loader(today):
    return None, "test：離線重放，未啟用利率曲線"


def _offline_dividend_loader(symbol, today):
    return None, "test：離線重放，未啟用股利管線"


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(),
                                 rate_loader=_offline_rate_loader,
                                 dividend_loader=_offline_dividend_loader))


def _multi_family_detail(storage):
    """建一個真的啟用兩個 family 的劇本（bullish：single-leg 的
    long-call＋vertical-spread 的 bull-call-spread 皆為 ok），刷新後
    回傳 `(scenario_id, storage 裡的完整 view, HTTP 回應的投影 view)`
    ——這正是票上點名「每多啟用一個 spread 策略就多約 495KB」的實際
    情境，用真實契約樣本量測，不是手造小 fixture。"""
    c = _client(storage)
    r = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg", "vertical-spread"]})
    sc_id = r.json()["id"]
    c.post(f"/api/scenarios/{sc_id}/refresh").raise_for_status()
    full_view = storage.latest_result(sc_id).view
    projected_view = c.get(f"/api/scenarios/{sc_id}").json()["latest_result"]
    return sc_id, full_view, projected_view


# ---------- AC：回應不含完整候選序列 ----------

def test_detail_response_has_no_full_candidate_lists():
    storage = MemoryStorage()
    _, full_view, projected_view = _multi_family_detail(storage)

    # 儲存層本來就有這兩個欄位（下面的全保真測試另外驗證），這裡先
    # 確認 fixture 真的產生了非空內容，不然這條測試沒有測到任何東西。
    assert any(r.get("candidates") for r in full_view["results"])

    for r in projected_view["results"]:
        assert "candidates" not in r
        assert "all_candidates" not in r


# ---------- AC：候選內容池只保留被實際引用到的鍵，沒有孤兒項目 ----------

def test_candidate_pool_has_no_orphans():
    storage = MemoryStorage()
    _, _, projected_view = _multi_family_detail(storage)

    referenced = set()
    for r in projected_view["results"]:
        referenced.update(r.get("expiry_best") or ())
        for group in r.get("expiry_top10") or ():
            referenced.update(group["candidate_keys"])
    for group in projected_view.get("expiry_groups") or ():
        for row in group["rows"]:
            referenced.add(row["candidate_key"])

    pool_keys = set(projected_view["candidate_pool"])
    assert pool_keys <= referenced, (
        f"孤兒項目：{pool_keys - referenced}")
    # 反過來也要成立——不能為了「沒有孤兒」就乾脆清空整個池子，被引用
    # 到的鍵必須真的解得回內容。
    assert pool_keys == referenced


# ---------- AC：每個 family 的候選數不超過「到期日數 × 10」 ----------

def test_candidate_count_per_strategy_bounded_by_expiry_count_times_ten():
    storage = MemoryStorage()
    _, _, projected_view = _multi_family_detail(storage)

    for r in projected_view["results"]:
        if r["status"] != "ok":
            continue
        groups = r.get("expiry_top10") or []
        expiry_count = len(groups)
        keys = {k for g in groups for k in g["candidate_keys"]}
        keys.update(r.get("expiry_best") or ())
        assert len(keys) <= expiry_count * 10, (
            f"{r['strategy']}：{len(keys)} 筆候選、{expiry_count} 個到期日")
        # fixture 要真的有東西可測，不然上面的斷言是空話。
        assert expiry_count > 0


# ---------- AC：儲存的內容維持全保真——與投影前逐位元相同 ----------

def test_storage_stays_full_fidelity_project_for_detail_does_not_touch_it():
    storage = MemoryStorage()
    sc_id, full_view, projected_view = _multi_family_detail(storage)

    # 落盤的那份完全沒被動過——`project_for_detail()` 回傳新字典，不
    # 修改輸入。這裡直接比對整份 dict 逐位元相同，而不只是挑幾個欄位。
    again = storage.latest_result(sc_id).view
    assert again == full_view
    assert any(r.get("candidates") for r in full_view["results"])
    assert any(r.get("all_candidates") for r in full_view["results"])

    # 投影後的的確變小了，且變小的正是被移除的那兩個欄位。
    assert len(json.dumps(projected_view)) < len(json.dumps(full_view))


# ---------- AC：以真實契約樣本量測並記錄投影前後的大小 ----------

def test_measured_size_reduction_with_a_real_multi_family_scenario():
    """真實量測（非估計，非票上引用的 495KB 那個數字——那是 production
    真實選擇權鏈的觀察，本測試用的是刻意精簡、跑得快的測試 fixture，
    每個到期日通過過濾的候選數量本就少，`candidates`／`expiry_top10`
    兩者重疊度因此偏高，縮減幅度不能拿來跟 production 數字比較）：
    2026-08-31 本地實測 `xyz_v4_six_expiries.json`（single-leg ＋
    vertical-spread 兩個 family 皆啟用，bullish）——66,495 bytes →
    64,271 bytes（縮減 3.3%）。結構性修法本身（移除唯二無上限成長
    的欄位）才是重點，不是這個特定 fixture 量到的百分比；真正的量體
    差異只會在候選數量多的真實鏈上顯現。"""
    storage = MemoryStorage()
    _, full_view, projected_view = _multi_family_detail(storage)

    full_bytes = len(json.dumps(full_view, ensure_ascii=False))
    projected_bytes = len(json.dumps(projected_view, ensure_ascii=False))
    reduction = 1 - (projected_bytes / full_bytes)

    print(f"\nT13 payload 投影量測（{FIX}，single-leg + vertical-spread "
         f"兩個 family 皆啟用）：全保真 {full_bytes:,} bytes → "
         f"投影後 {projected_bytes:,} bytes（縮減 {reduction:.1%}）")

    # 這個 fixture 刻意精簡（測試要跑得快），縮減幅度因此遠低於票上
    # 引用的 production 觀察值——斷言只鎖「結構性修法確實生效」（欄位
    # 真的少了、位元組數真的降了），不編一個這個 fixture 量不出來的
    # 百分比門檻。
    assert projected_bytes < full_bytes
    assert reduction > 0


# ---------- AC：既有依賴完整序列的功能零回歸（走 server 端路徑） ----------

def test_representative_candidate_and_best_return_still_resolve_against_projected_view():
    """`store.representative_candidate()`／`best_return()` 靠
    `expiry_groups` 運作——這個函式刻意保留在投影結果裡（見
    `project_for_detail()` docstring），這裡直接證明它們對投影後的
    view 仍然算得出跟對完整 view 一樣的答案。"""
    storage = MemoryStorage()
    _, full_view, projected_view = _multi_family_detail(storage)

    rep_full = store.representative_candidate(full_view)
    rep_projected = store.representative_candidate(projected_view)
    assert rep_full is not None
    assert rep_projected == rep_full
    assert store.best_return(projected_view) == store.best_return(full_view)


def test_spread_history_and_raw_data_are_unaffected_because_they_read_storage_directly():
    """V9 Spread 淨成本走勢／V8 原始資料兩個既有端點都是從 `_db()`
    （storage）直接讀最新結果或逐筆快照，完全不經過
    `GET /api/scenarios/{id}` 這個端點、也就不經過 `project_for_
    detail()`——這裡用真實端點呼叫直接證明，不只是推論程式碼路徑。"""
    storage = MemoryStorage()
    c = _client(storage)
    r = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]})
    sc_id = r.json()["id"]
    c.post(f"/api/scenarios/{sc_id}/refresh").raise_for_status()

    view = storage.latest_result(sc_id).view
    candidate_key = view["results"][0]["expiry_top10"][0]["candidate_keys"][0]

    history = c.get(f"/api/scenarios/{sc_id}/history"
                    f"?candidate_key={candidate_key}")
    assert history.status_code == 200
    assert history.json()["entries"]

    raw = c.get(f"/api/scenarios/{sc_id}/raw-data")
    assert raw.status_code == 200
    assert raw.json()["contracts"]


# ---------- 純函式層：`project_for_detail()` 直接測 ----------

def _fake_view(results, pool, extra=None):
    return {"results": results, "candidate_pool": pool,
           "expiry_groups": [], **(extra or {})}


def test_pure_function_drops_unreferenced_pool_entries():
    view = _fake_view(
        results=[{
            "strategy": "long-call", "status": "ok",
            "candidates": ["k1", "k2", "k3"],
            "all_candidates": [{"date": "2026-01-01"}],
            "expiry_best": ["k1"],
            "expiry_top10": [{"expiry": "2026-09-18", "candidate_keys": ["k1"]}],
        }],
        pool={"k1": {"candidate_key": "k1"}, "k2": {"candidate_key": "k2"},
             "k3": {"candidate_key": "k3"}},
    )
    out = store.project_for_detail(view)
    assert set(out["candidate_pool"]) == {"k1"}
    assert "candidates" not in out["results"][0]
    assert "all_candidates" not in out["results"][0]


def test_pure_function_keeps_expiry_groups_referenced_keys():
    view = _fake_view(
        results=[{
            "strategy": "bull-call-spread", "status": "ok",
            "candidates": ["k1"], "all_candidates": [],
            "expiry_best": [], "expiry_top10": [],
        }],
        pool={"k9": {"candidate_key": "k9"}},
        extra={"expiry_groups": [
            {"expiry": "2026-09-18",
             "rows": [{"strategy": "bull-call-spread", "candidate_key": "k9"}]},
        ]},
    )
    out = store.project_for_detail(view)
    assert set(out["candidate_pool"]) == {"k9"}


def test_pure_function_keeps_default_and_baseline_selection_resolvable():
    view = _fake_view(
        results=[{
            "strategy": "long-call", "status": "ok",
            "candidates": [], "all_candidates": [],
            "expiry_best": [], "expiry_top10": [],
        }],
        pool={"a": {"candidate_key": "a"}, "b": {"candidate_key": "b"}},
        extra={"default_selection": ["2026-09-18", "a"],
              "baseline_selection": ["2026-09-18", "b"]},
    )
    out = store.project_for_detail(view)
    assert set(out["candidate_pool"]) == {"a", "b"}


def test_pure_function_does_not_mutate_the_input():
    view = _fake_view(
        results=[{
            "strategy": "long-call", "status": "ok",
            "candidates": ["k1"], "all_candidates": [{"date": "x"}],
            "expiry_best": ["k1"], "expiry_top10": [],
        }],
        pool={"k1": {"candidate_key": "k1"}},
    )
    snapshot = json.dumps(view)
    store.project_for_detail(view)
    assert json.dumps(view) == snapshot


def test_pure_function_handles_a_completely_empty_view():
    view = _fake_view(results=[], pool={})
    out = store.project_for_detail(view)
    assert out["results"] == []
    assert out["candidate_pool"] == {}
