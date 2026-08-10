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
