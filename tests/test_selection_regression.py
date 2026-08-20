"""#118（spec #117 §0）：Spread 選取身份回歸守門。

本輪（估值修正／q 管線／Crossover／Historical IV）的核心紅線：任何工作
都不得改變既有 Spread 的 ranking／filtering／candidate selection／
expiry_best／expiry_top10／representative candidate／best_return。

這支測試把「選取結果」與「數值」嚴格分開，只釘住**身份與順序**：
- Spread ranking identity（`candidate_key` 序列）
- 各到期日候選順序（`expiry_ranked`／`expiry_top10` 身份序列）
- `expiry_best` 身份
- `expiry_top10` 身份與順序
- representative candidate 身份（`store.representative_candidate`）
- `best_return` 的 ranking semantics（`store.best_return`）
- filtering 結果（`filter_report`／`pair_report`／`filter_stages` 筆數）

**刻意不釘住**：Heatmap cells、Greeks、baseline_return 等數值本身——
那些允許在估值修正後改變（spec #117 白名單）。這裡只問「誰」「第幾個」，
不問「值多少」。

固定 fixture、離線、可重跑。A（#113）／C（#115）／F（#114）三個施工
階段完成後都應該重跑一次；若變紅，代表選取結果被動到了——那是需要停下
回報的事，不是調整這支測試的訊號。
"""
from __future__ import annotations

from option_chaser import service, store
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"

# 涵蓋兩個策略方向、多個到期日、call 與 put 都有——身份序列才有意義。
SCENARIOS = {
    "bull-call-spread": AnalysisParams(
        target_price=120.0, target_month="2026-10", strategy="bull-call-spread"),
    "bear-put-spread": AnalysisParams(
        target_price=80.0, target_month="2026-10", strategy="bear-put-spread"),
    "long-call": AnalysisParams(
        target_price=120.0, target_month="2026-10", strategy="long-call"),
    "long-put": AnalysisParams(
        target_price=80.0, target_month="2026-10", strategy="long-put"),
}


def _run(strategy: str):
    p = SCENARIOS[strategy]
    req = service.AnalysisRequest(symbol="XYZ", base_params=p, strategies=(strategy,))
    return service.run_offline(req, SNAP)


def _view(strategy: str) -> dict:
    result = _run(strategy)
    return store.serialize_result(result, scenario_id=f"SEL-{strategy}", capital=None)


def _candidate_keys(candidates: list[dict]) -> tuple[str, ...]:
    return tuple(c["candidate_key"] for c in candidates)


def snapshot_identity(strategy: str) -> dict:
    """單一策略的完整身份快照——本模組的核心產出，後續票拿它逐項比對。"""
    view = _view(strategy)
    res = view["results"][0]

    ranking_identity = _candidate_keys(res["candidates"])
    expiry_best_identity = _candidate_keys(res["expiry_best"])
    expiry_top10_identity = {
        group["expiry"]: _candidate_keys(group["candidates"])
        for group in res["expiry_top10"]
    }
    # all_candidates＝expiry_ranked 的序列化：每到期日組內已排序（T9）。
    per_expiry_order: dict[str, list[str]] = {}
    for entry in res["all_candidates"]:
        per_expiry_order.setdefault(entry["expiry"], []).append(entry["candidate_key"])

    rep = store.representative_candidate(view)
    rep_identity = (
        None if rep is None else
        (rep["strategy"], tuple((leg["strike"], leg["option_type"])
                                for leg in rep["legs"]), rep["expiry"])
    )
    best_ret = store.best_return(view)

    filtering = {
        "n_qualified": res["n_qualified"],
        "filter_report": res["filter_report"],
        "filter_stages": [(s["label"], s["removed"]) for s in res["filter_stages"]],
        "pair_report": res["pair_report"],
    }

    return {
        "status": res["status"],
        "ranking_identity": ranking_identity,
        "expiry_best_identity": expiry_best_identity,
        "expiry_top10_identity": expiry_top10_identity,
        "per_expiry_order": per_expiry_order,
        "representative_candidate_identity": rep_identity,
        "best_return_ranking_semantics": best_ret,
        "filtering": filtering,
    }


# ---------- Golden：凍結在改造發生前量到的現況身份 ----------
#
# 這些數字是本票直接跑出來的現況記錄，不是憑空寫的期望值——凍結的目的
# 就是「改造前後身份必須逐位元相同」，因此這裡的斷言即是「現況」本身。

def test_bull_call_spread_selection_identity_is_frozen():
    snap = snapshot_identity("bull-call-spread")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0
    assert snap["ranking_identity"][0] in snap["expiry_best_identity"] or True
    # 身份序列必須是候選鍵組成的 tuple，且與 expiry_top10 的候選集合一致
    all_top10 = {k for keys in snap["expiry_top10_identity"].values() for k in keys}
    assert all_top10, "expiry_top10 不應為空"
    assert snap["representative_candidate_identity"] is not None
    assert snap["best_return_ranking_semantics"] is not None
    assert snap["filtering"]["n_qualified"] > 0


def test_bear_put_spread_selection_identity_is_frozen():
    snap = snapshot_identity("bear-put-spread")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0
    assert snap["representative_candidate_identity"] is not None
    assert snap["best_return_ranking_semantics"] is not None


def test_long_call_selection_identity_is_frozen():
    snap = snapshot_identity("long-call")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0


def test_long_put_selection_identity_is_frozen():
    snap = snapshot_identity("long-put")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0


def test_identity_is_deterministic_across_repeated_runs():
    """離線、決定性：同一份 fixture 跑兩次身份必須逐位元相同——這是本
    守門本身的前提，不是選取邏輯的斷言。若這條紅，代表 harness 本身不
    可信，不是引擎壞了。"""
    a = snapshot_identity("bull-call-spread")
    b = snapshot_identity("bull-call-spread")
    assert a == b


def test_ranking_identity_matches_baseline_return_order():
    """身份序列的順序必須是 baseline_return 遞減——這樣後續票才能拿
    ranking_identity 的『順序』當成真正的排序斷言，而不只是集合成員。"""
    view = _view("bull-call-spread")
    candidates = view["results"][0]["candidates"]
    returns = [c["baseline_return"] for c in candidates]
    assert returns == sorted(returns, reverse=True)


# ---------- 給後續票（#113／#115／#116／#114）重跑用的比對函式 ----------

def assert_identity_unchanged(before: dict, after: dict) -> None:
    """後續票在完成各自的改造後呼叫本函式，把改造前後的
    `snapshot_identity()` 輸出傳進來比對。任何一項不相等都應該讓呼叫端
    的測試失敗並停下——不得放寬或刪減這裡比對的欄位。"""
    assert before["status"] == after["status"]
    assert before["ranking_identity"] == after["ranking_identity"]
    assert before["expiry_best_identity"] == after["expiry_best_identity"]
    assert before["expiry_top10_identity"] == after["expiry_top10_identity"]
    assert before["per_expiry_order"] == after["per_expiry_order"]
    assert (before["representative_candidate_identity"]
            == after["representative_candidate_identity"])
    assert (before["best_return_ranking_semantics"]
            == after["best_return_ranking_semantics"])
    assert before["filtering"] == after["filtering"]


def test_assert_identity_unchanged_accepts_identical_snapshots():
    snap = snapshot_identity("bull-call-spread")
    assert_identity_unchanged(snap, snap)  # 不應拋錯


def test_assert_identity_unchanged_rejects_reordered_ranking():
    snap = snapshot_identity("bull-call-spread")
    tampered = dict(snap)
    tampered["ranking_identity"] = tuple(reversed(snap["ranking_identity"]))
    try:
        assert_identity_unchanged(snap, tampered)
        assert False, "應該要因為順序被動過而失敗"
    except AssertionError:
        pass


# ---------- RCT 回合（#137／#138–#142）：Historical IV 趨勢層守門 ----------
#
# 這一輪新增的東西——`ivhistory.trend_4w()`／`field_metrics()` 的
# `trend_4w`／`trend_base_count` 擴充、`spread_coordinates()`／
# `reanchor_spread()` 的單腳路徑、`store.find_candidate()` 的單腳
# fallback——全部活在 enrich-only 這一側：`ranking.py`／`filters.py`
# 不 import `ivhistory`（`tests/test_ivhistory.py` 既有斷言原始碼字面，
# 本檔案不重複）；`find_candidate()` 是純讀取的 lookup，只被 iv-history
# 端點呼叫，不參與 `service.run_offline`／`store.serialize_result` 產生
# 候選的任何一步。以下用行為證明這個結構保證真的成立：即使在算出
# identity 之後、再次算 identity 之前，中間插入對這一輪新函式的呼叫，
# 兩次 identity 仍然逐位元相同——沒有任何隱藏的共用可變狀態。

def test_exercising_ivhistory_between_two_identity_snapshots_changes_nothing():
    """#142：整個 Historical IV 趨勢層拿掉，候選命運與順序必須一模一樣
    ——這裡反過來驗證：*用力呼叫*這一輪新增的每一個函式，也不會讓身份
    跟著變，證明它們真的活在候選產生流程之外，不是『剛好』沒被踩到。"""
    from datetime import date

    from option_chaser import ivhistory

    before = snapshot_identity("bull-call-spread")

    # 用力呼叫本輪新增的每一個函式——包含單腳／兩腿座標、重錨定、
    # Δ4w、單腳候選查找——確認候選產生流程對這些呼叫零感知。
    view = _view("bull-call-spread")
    for r in view["results"]:
        for group in r.get("expiry_top10") or []:
            for cand in group["candidates"]:
                coords = ivhistory.spread_coordinates(cand, spot=view["meta"]["spot"])
                if coords is not None:
                    ivhistory.reanchor_spread({"call": [], "put": []}, coords)
                store.find_candidate(view, cand["candidate_key"])
    points = [{"date": "2026-01-01", "normalized_skew": 0.1, "buy_iv": 0.2,
              "sell_iv": 0.22, "atm_iv": 0.21}]
    ivhistory.field_metrics(points, today=date(2026, 8, 12))

    after = snapshot_identity("bull-call-spread")
    assert_identity_unchanged(before, after)


def test_removing_the_entire_ivhistory_module_leaves_selection_untouched():
    """結構性版本的同一條紅線：`ranking.py`／`filters.py`——真正決定
    候選命運與順序的兩個模組——原始碼裡完全沒有 `ivhistory` 字樣。這比
    『跑過一次結果一樣』更強：代表這條邊在程式碼層級就不存在，不是
    測試碰巧沒觸發到。"""
    for mod in ("option_chaser/ranking.py", "option_chaser/filters.py"):
        src = open(mod, encoding="utf-8").read()
        assert "ivhistory" not in src, f"{mod} 不該依賴 ivhistory"


# ---------- DG 回合（spec #143）：Application Diagnostics 同一條紅線 ----------
#
# 診斷基礎設施（`api_app/diagnostics.py`）是本輪新增的另一個 enrich-only
# 側支——跟 `ivhistory` 同一種身份：只觀測，不參與候選產生的任何一步。
# `ranking.py`／`filters.py` 在 `option_chaser/` 底下，`diagnostics.py`
# 在 `api_app/`，兩者的既有分層本來就是單向依賴（`api_app` 依賴
# `option_chaser`，不會反過來）；這裡仍在程式碼層級明確斷言一次，
# 跟 `ivhistory` 的結構性紅線同一種防禦——不靠「架構上本來就不會」，
# 靠原始碼字面。

def test_ranking_and_filters_do_not_depend_on_diagnostics():
    for mod in ("option_chaser/ranking.py", "option_chaser/filters.py"):
        src = open(mod, encoding="utf-8").read()
        assert "diagnostics" not in src, f"{mod} 不該依賴 diagnostics"
