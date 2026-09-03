"""T15（#230，Initial V2 spec #217）：Butterfly 候選序列化——比照既有
`test_store_serialize.py::test_candidate_fields_hand_checked` 的手算
風格，逐欄核對三腿版本的契約形狀。
"""
from option_chaser import service, store
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"


def _result(strategy="call-fly", target_price=108.0, target_month="2026-10"):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategy, target_price=target_price,
                                       target_month=target_month),
            strategies=(strategy,)),
        FIX)


def test_butterfly_candidate_has_three_legs_with_explicit_side_and_quantity():
    result = _result()
    view = store.serialize_result(result, "S", 100000.0)
    key = view["results"][0]["candidates"][0]
    cand = view["candidate_pool"][key]
    legs = cand["legs"]
    assert len(legs) == 3
    assert legs[0]["side"] == "buy" and legs[0]["quantity"] == 1
    assert legs[1]["side"] == "sell" and legs[1]["quantity"] == 2
    assert legs[2]["side"] == "buy" and legs[2]["quantity"] == 1
    assert legs[0]["strike"] < legs[1]["strike"] < legs[2]["strike"]


def test_breakeven_points_carries_two_points_or_empty_not_a_single_scalar():
    result = _result()
    view = store.serialize_result(result, "S", 100000.0)
    for key in view["results"][0]["candidates"]:
        cand = view["candidate_pool"][key]
        assert len(cand["breakeven_points"]) in (0, 2)
        if cand["breakeven_points"]:
            assert cand["breakeven_points"][0] < cand["breakeven_points"][1]
            assert cand["breakeven"] == cand["breakeven_points"][0]
        else:
            assert cand["breakeven"] is None


def test_max_loss_per_contract_can_differ_from_capital_per_contract():
    """AC 明文的性質：既有四策略 `max_loss_per_contract == capital_
    per_contract` 恆成立，Butterfly 不假設這條不變量——這裡直接掃過
    全部候選，證明契約層真的把 `ButterflyValuation.max_loss` 而非
    `natural_cost` 序列化進這個欄位。"""
    result = _result()
    view = store.serialize_result(result, "S", 100000.0)
    found_broken_wing = False
    for key in view["results"][0]["candidates"]:
        cand = view["candidate_pool"][key]
        assert cand["max_loss_per_contract"] >= cand["capital_per_contract"] - 1e-6
        if cand["max_loss_per_contract"] > cand["capital_per_contract"] + 1e-6:
            found_broken_wing = True
    assert found_broken_wing, "沒有任何候選的 max_loss 超過 capital——換一份 fixture 檢查"


def test_profit_region_matches_the_engine_value():
    result = _result()
    view = store.serialize_result(result, "S", 100000.0)
    res0 = result.results[0]
    view_res0 = view["results"][0]
    for key, cv in zip(view_res0["candidates"], res0.candidates):
        cand = view["candidate_pool"][key]
        if cv.profit_region is None:
            assert cand["profit_region"] is None
        else:
            assert cand["profit_region"] == list(cv.profit_region)


def test_existing_four_strategies_still_serialize_breakeven_as_a_single_point():
    """回歸：既有四策略的 `breakeven_points` 契約形狀（單元素陣列）
    完全不受 Butterfly 三腿分支影響。"""
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="bull-call-spread",
                                       target_price=108.0, target_month="2026-10"),
            strategies=("bull-call-spread",)),
        FIX)
    view = store.serialize_result(result, "S", 100000.0)
    for key in view["results"][0]["candidates"]:
        cand = view["candidate_pool"][key]
        assert len(cand["legs"]) == 2
        assert cand["breakeven_points"] == [cand["breakeven"]]
        assert cand["max_loss_per_contract"] == cand["capital_per_contract"]


def test_history_entry_includes_butterfly_candidates_from_the_first_analysis():
    """`_history_entry()` 三分支測試——Butterfly 的 `natural_cost`／
    `baseline_return`／`valuation_key` 皆走各自的多型函式。"""
    result = _result()
    res0 = result.results[0]
    for exp, ranked_group in res0.expiry_ranked:
        for rank, bv in enumerate(ranked_group, start=1):
            entry = store._history_entry(bv, exp, rank)
            assert entry["expiry"] == exp
            assert entry["rank_in_expiry"] == rank
            assert entry["cost"] == bv.net_worst
            assert "|" in entry["candidate_key"]


def test_representative_candidate_carries_all_three_butterfly_legs_with_quantity():
    """OPTION-CHASER-CLOSEOUT-001（劇本庫卡片 champion 顯示一致性）：

    `representative_candidate()`／`representative_candidates_by_
    family()` 給劇本清單卡片用的輕量投影，過去只投影 `strike`／
    `option_type`／`side`，缺 `quantity`——前端 `formatRepresentative
    Legs()` 因此無從標出 Butterfly 中腿的「2×」，且舊版格式化邏輯只抓
    一隻 buy 腿與一隻 sell 腿，會把三腿 champion 靜默截斷成兩腿。

    這裡直接驗證：當跨 family champion 是 Butterfly 時，
    `representative_candidate()` 回傳的輕量投影本身就帶著完整三腿
    （含 `quantity`），與 `candidate_pool` 裡的完整候選逐腿一致——
    卡片顯示需要的資料本來就在同一個 candidate 裡，不需要另一個
    來源。"""
    result = _result()
    view = store.serialize_result(result, "S", 100000.0)
    key = view["results"][0]["candidates"][0]
    full_cand = view["candidate_pool"][key]

    rep = store.representative_candidate(view)
    assert rep is not None
    assert rep["strategy"] == "call-fly"
    assert len(rep["legs"]) == 3
    assert [leg["side"] for leg in rep["legs"]] == ["buy", "sell", "buy"]
    assert [leg["quantity"] for leg in rep["legs"]] == [1, 2, 1]
    # 履約價逐一對上完整候選——同一個候選，不是另外湊出來的資料。
    assert ([leg["strike"] for leg in rep["legs"]]
           == [leg["strike"] for leg in full_cand["legs"]])

    per_family = store.representative_candidates_by_family(view)
    assert per_family["butterfly"]["legs"] == rep["legs"]
