# tests/test_cost_basis.py
"""T12(B) 成本口徑（附錄 A14.2）：主排名與 Heatmap 成本改用
net_worst＝買腿 Ask − 賣腿 Bid；單腿主數字同步改用 Ask。
排名公式形狀 (基準值−成本)/成本 與 tie-break 不變，僅成本口徑改變。"""
from datetime import date

import pytest

from option_chaser import service
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.ranking import (baseline_return, rank_spreads,
                                   spread_baseline_return)
from option_chaser.valuation import (evaluate_contract, evaluate_spread,
                                     scenario_leg_value, spread_scenario_value)

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-08",
                   strategy="bull-call-spread")
SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def make(sym, strike, bid, ask, iv=0.30, opt="call", expiry="2026-10-16"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


# ---------- 排名分母 = net_worst / Ask ----------

def test_spread_baseline_return_denominator_is_net_worst():
    sv = evaluate_spread(make("L", 110.0, 3.0, 3.25), make("S", 130.0, 0.05, 0.15),
                         spot=100.0, today=TODAY, p=P)
    assert spread_baseline_return(sv) == pytest.approx(
        (sv.baseline_value - sv.net_worst) / sv.net_worst)


def test_single_leg_baseline_return_denominator_is_ask():
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    v = evaluate_contract(make("C", 110.0, 3.0, 3.25), spot=100.0,
                          today=TODAY, p=p)
    assert baseline_return(v) == pytest.approx(
        (v.baseline_value - v.contract.ask) / v.contract.ask)


def test_wide_bid_ask_same_mid_is_penalized():
    """驗收：同 mid 成本、同結構的兩組 spread，bid/ask 寬者名次被懲罰。"""
    narrow = evaluate_spread(make("LN", 110.0, 3.05, 3.20),
                             make("SN", 120.0, 0.55, 0.65),
                             spot=100.0, today=TODAY, p=P)
    wide = evaluate_spread(make("LW", 110.0, 2.65, 3.60),
                           make("SW", 120.0, 0.20, 1.00),
                           spot=100.0, today=TODAY, p=P)
    # 同 mid 成本、同到期日同履約價 → 基準值（到期內在價值）相同
    assert narrow.net_mid == pytest.approx(wide.net_mid)
    assert narrow.baseline_value == pytest.approx(wide.baseline_value)
    assert wide.net_worst > narrow.net_worst
    ranked = rank_spreads([wide, narrow], P)
    assert ranked[0] is narrow and ranked[1] is wide
    assert spread_baseline_return(narrow) > spread_baseline_return(wide)


# ---------- 衍生數字同口徑 ----------

def test_spread_breakeven_leverage_max_profit_use_net_worst():
    sv = evaluate_spread(make("L", 110.0, 3.0, 3.25), make("S", 130.0, 0.05, 0.15),
                         spot=100.0, today=TODAY, p=P)
    assert sv.breakeven == 110.0 + sv.net_worst
    assert sv.max_profit == pytest.approx(sv.width - sv.net_worst)
    assert sv.effective_leverage == pytest.approx(
        abs(sv.net_delta) * 100.0 / sv.net_worst)


def test_bear_put_breakeven_uses_net_worst():
    p = AnalysisParams(target_price=80.0, target_month="2026-08",
                       strategy="bear-put-spread")
    sv = evaluate_spread(make("L", 100.0, 5.2, 5.4, iv=0.36, opt="put"),
                         make("S", 85.0, 1.1, 1.25, iv=0.35, opt="put"),
                         spot=100.0, today=TODAY, p=p)
    assert sv.breakeven == 100.0 - sv.net_worst


def test_single_leg_breakeven_uses_ask():
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    v = evaluate_contract(make("C", 110.0, 3.0, 3.25), spot=100.0,
                          today=TODAY, p=p)
    assert v.breakeven == 110.0 + 3.25
    assert v.effective_leverage == pytest.approx(abs(v.delta) * 100.0 / 3.25)
    p_put = AnalysisParams(target_price=80.0, target_month="2026-08",
                           strategy="long-put")
    vp = evaluate_contract(make("P", 90.0, 2.8, 3.0, iv=0.40, opt="put"),
                           spot=100.0, today=TODAY, p=p_put)
    assert vp.breakeven == 90.0 - 3.0


# ---------- Heatmap 與排名同口徑；到期欄仍為內在價值（T3 不回歸） ----------

def _request(strategies):
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy=strategies[0], target_price=120.0,
                                   target_month="2026-08"),
        strategies=strategies)


def test_heatmap_cost_same_basis_as_ranking():
    result = service.run_offline(_request(("bull-call-spread",)), SNAP)
    res = result.results[0]
    assert res.status == "ok"
    cv = res.candidates[0]
    sv = cv.valuation
    p = result.request.base_params
    import dataclasses
    p = dataclasses.replace(p, strategy="bull-call-spread")
    for i, (price, _) in enumerate(cv.matrix.prices):
        for j, (iso, _) in enumerate(cv.matrix.dates):
            val = spread_scenario_value(sv.long_leg, sv.short_leg, price,
                                        date.fromisoformat(iso), p)
            assert cv.matrix.cells[i][j] == pytest.approx(
                (val - sv.net_worst) / sv.net_worst)
    # 末欄＝到期日 → 格值基礎為內在價值 payoff（T3 不回歸）
    last_iso = cv.matrix.dates[-1][0]
    assert last_iso == sv.long_leg.expiry
    for i, (price, _) in enumerate(cv.matrix.prices):
        payoff = min(max(max(price - sv.long_leg.strike, 0.0)
                         - max(price - sv.short_leg.strike, 0.0), 0.0), sv.width)
        assert cv.matrix.cells[i][-1] == pytest.approx(
            (payoff - sv.net_worst) / sv.net_worst)


def test_single_leg_heatmap_cost_is_ask():
    result = service.run_offline(_request(("long-call",)), SNAP)
    res = result.results[0]
    cv = res.candidates[0]
    v = cv.valuation
    p = result.request.base_params
    price, _ = cv.matrix.prices[3]
    iso, _ = cv.matrix.dates[1]
    val = scenario_leg_value(v.contract, price, date.fromisoformat(iso), p)
    assert cv.matrix.cells[3][1] == pytest.approx(
        (val - v.contract.ask) / v.contract.ask)


def test_candidate_view_merged_main_number():
    """Natural 成交報酬與主數字重合 → 合併：CandidateView 不再有 natural_return。"""
    result = service.run_offline(_request(("long-call", "bull-call-spread")), SNAP)
    for res in result.results:
        for cv in res.candidates:
            assert not hasattr(cv, "natural_return")
            v = cv.valuation
            worst = (v.net_worst if hasattr(v, "net_worst") else v.contract.ask)
            assert cv.baseline_pnl == pytest.approx(v.baseline_value - worst)
    assert result.comparison
    for row in result.comparison:
        assert not hasattr(row, "natural_return")
