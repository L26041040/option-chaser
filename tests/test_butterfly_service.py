"""T15（#230，Initial V2 spec #217）：`service._butterfly_result()`／
`_analyze()` 端到端測試——比照既有 `_spread_result()` 的既有測試涵蓋
範圍，逐項對照 issue #230 的 acceptance criteria。
"""
from option_chaser import service
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract

# 中密度 fixture（`scripts/gen_butterfly_fixture.py` 產生）——夠密可以
# 排出正的 max_profit，又不像效能測試用的密集版（`xyz_v6_butterfly_
# ladder.json`）動輒近萬組合、拖慢一般行為測試。
FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"


def _run(strategy, target_price, target_month="2026-10", strategies=None):
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy=strategy, target_price=target_price,
                                   target_month=target_month),
        strategies=strategies or (strategy,))
    return service.run_offline(req, FIX)


def test_call_fly_produces_ok_status_with_qualified_candidates():
    result = _run("call-fly", 108.0)
    res = result.results[0]
    assert res.status == "ok"
    assert res.n_qualified > 0
    assert len(res.candidates) > 0
    assert res.ranked_butterflies is not None
    assert res.ranked_spreads is None and res.ranked_bands is None


def test_put_fly_produces_ok_status_with_qualified_candidates():
    result = _run("put-fly", 92.0)
    res = result.results[0]
    assert res.status == "ok"
    assert res.n_qualified > 0
    for c in res.candidates:
        assert c.valuation.option_type == "put"


def test_body_position_is_not_hardcoded_it_emerges_from_ranking():
    """AC：body 的位置不由任何硬編碼規則決定，只由排名結果決定——同一
    份候選池換一個 target_price，排名第一的履約價組合應該跟著換（不是
    每次都選同一組固定的三個履約價）。"""
    winners = set()
    # call-fly 只在 bullish／flat 適用（target >= spot=100）——四個目標
    # 價位都落在這個範圍內，確保每一輪都真的跑出候選而非被方向閘門擋下。
    for target in (100.0, 104.0, 108.0, 116.0):
        result = _run("call-fly", target)
        res = result.results[0]
        bv = res.candidates[0].valuation
        winners.add((bv.low_leg.strike, bv.mid_leg.strike, bv.high_leg.strike))
    assert len(winners) > 1, (
        "不同目標價位排出來的第一名組合完全相同，代表 body 疑似被寫死")


def test_candidates_carry_a_real_profit_region_or_none_honestly():
    result = _run("call-fly", 108.0)
    res = result.results[0]
    for c in res.candidates:
        assert (c.profit_region is None) or (
            isinstance(c.profit_region, tuple) and len(c.profit_region) == 2
            and c.profit_region[0] < c.profit_region[1])
        # 單調家族既有的保本掃描單一數字對 Butterfly 恆為 None——與
        # profit_region 互斥出現（AC：不硬擠成單一數字）。
        assert c.completion_threshold is None
        assert c.breakeven_at_target is None


def test_historical_identity_fields_are_populated_from_day_one():
    """AC：Butterfly 候選的歷史身份列從第一天就落盤——`expiry_ranked`
    （供 `store._history_entry()` 序列化用）必須非空，不是留給未來
    某個「第二天」才補上的空殼。"""
    result = _run("call-fly", 108.0)
    res = result.results[0]
    assert len(res.expiry_ranked) > 0
    for exp, ranked_group in res.expiry_ranked:
        assert len(ranked_group) > 0
        for bv in ranked_group:
            assert bv.low_leg.expiry == exp


def test_empty_when_fewer_than_three_strikes_exist_at_any_expiry():
    """單一到期日不足三個履約價（且不同到期日不能組合）時，狀態應為
    empty，而不是拋錯或誤報 ok。"""
    from datetime import date as _date
    from option_chaser.valuation import american_price

    expiry = "2026-10-16"
    T = (_date(2026, 10, 16) - _date(2026, 7, 15)).days / 365.0
    contracts = []
    for i, strike in enumerate((95.0, 105.0)):   # 只有 2 個履約價
        theo = american_price("call", 100.0, strike, T, 0.04, 0.0, 0.25)
        contracts.append(OptionContract(
            contract_symbol=f"X{i}", option_type="call", strike=strike,
            expiry=expiry, bid=round(theo - 0.05, 2), ask=round(theo + 0.05, 2),
            last=round(theo, 2), volume=10, open_interest=100,
            implied_volatility=0.25))
    snap = ChainSnapshot(schema_version=2, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="test", contracts=tuple(contracts))
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="call-fly", target_price=105.0,
                                   target_month="2026-10"),
        strategies=("call-fly",))
    result = service.run_with_snapshot(req, snap)
    res = result.results[0]
    assert res.status == "empty"
    assert res.candidates == ()
    assert res.report_text is not None


def test_wrong_direction_is_skipped_not_forced():
    """call-fly 只在 bullish／flat 適用；bearish 劇本應該被既有
    `skipped_direction` 機制擋下，不強行跑出候選。"""
    result = _run("call-fly", 50.0)   # 遠低於現價 100，明確 bearish
    res = result.results[0]
    assert res.status == "skipped_direction"


def test_flat_scenario_is_eligible_for_both_call_fly_and_put_fly():
    """Owner 2026-08-27 裁示：持平（target==spot）只有 Butterfly 可選。"""
    call_result = _run("call-fly", 100.0)   # spot 恆為 100（fixture 既定）
    put_result = _run("put-fly", 100.0)
    assert call_result.results[0].status != "skipped_direction"
    assert put_result.results[0].status != "skipped_direction"


def test_comparison_row_uses_the_lower_breakeven_and_real_max_profit():
    result = _run("call-fly", 108.0)
    assert len(result.comparison) == 1
    row = result.comparison[0]
    assert row.strategy == "call-fly"
    bv = result.results[0].candidates[0].valuation
    assert row.cost == bv.net_worst
    assert row.max_profit == bv.max_profit
    if bv.breakeven_points:
        assert row.breakeven == bv.breakeven_points[0]


def test_report_text_renders_without_crashing_and_names_all_three_legs():
    result = _run("call-fly", 108.0)
    text = result.results[0].report_text
    assert "低履約腿" in text
    assert "中履約腿（賣 2 口）" in text
    assert "高履約腿" in text
    assert "獲利區間（到期）" in text


def test_existing_four_strategies_unaffected_when_run_alongside_butterfly():
    """AC：既有四個策略的輸出不受本票影響——同一次分析請求混合既有
    策略與新策略，既有策略的候選集合應與單獨跑得到的結果一致。"""
    solo = _run("bull-call-spread", 108.0)
    combined_req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread", target_price=108.0,
                                   target_month="2026-10"),
        strategies=("bull-call-spread", "call-fly"))
    combined = service.run_offline(combined_req, FIX)
    solo_keys = [service.candidate_key(cv) for cv in solo.results[0].candidates]
    combined_keys = [service.candidate_key(cv)
                     for cv in combined.results[0].candidates]
    assert solo_keys == combined_keys


def test_max_loss_can_exceed_the_premium_paid_for_a_real_broken_wing_candidate():
    """AC 明文性質的端到端證明：真實鏈上至少有一個候選的 max_loss 超過
    natural_cost（既有四策略『max_loss 恆等於成本』的不變量在 Butterfly
    上不成立）——如果這份密集 fixture 裡一個都沒有，代表枚舉或 A/B 層
    篩掉了所有 broken-wing 組合，需要重新檢視測試 fixture 而非略過。"""
    result = _run("call-fly", 108.0)
    from option_chaser.scenarios import natural_cost
    found = any(bv.max_loss > natural_cost(bv) + 1e-9
               for exp, group in result.results[0].expiry_ranked for bv in group)
    assert found, "這份 fixture 沒有任何 broken-wing 候選可供驗證"
