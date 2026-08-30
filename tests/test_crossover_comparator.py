"""#115（spec #117 §4）：Crossover comparator——就是 Spread 買腿本身，
不是搜尋或轉換出來的另一張合約。

覆蓋範圍：comparator 直接讀買腿既有報價（call/put 各一條路徑）；本票明文
要求的「不得做任何選取」證明（不呼叫 find_contract／legacy 排名／delta
分級）；cost=Ask；matrix 與 Spread 自身 matrix 同一組 price×date grid、
同形狀；買腿報價缺失時誠實回 None；單腿候選恆無 comparator。
"""
from __future__ import annotations

from unittest.mock import patch

from option_chaser import service
from option_chaser.data.snapshot import save_snapshot
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract, SCHEMA_VERSION

EXPIRY = "2026-10-16"


def _contract(option_type, strike, bid, ask):
    return OptionContract(
        contract_symbol=f"{option_type[0].upper()}{strike:g}", option_type=option_type,
        strike=strike, expiry=EXPIRY, bid=bid, ask=ask, last=(bid + ask) / 2,
        volume=50, open_interest=100, implied_volatility=0.3)


def _write_snap(tmp_path, contracts, name="snap.json"):
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=tuple(contracts))
    path = tmp_path / name
    save_snapshot(snap, path)
    return str(path)


def _request(strategy, target_price):
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy=strategy, target_price=target_price,
                                   target_month="2026-10", min_return=0.0),
        strategies=(strategy,))


# ---------- bull-call-spread → comparator 是 Long Call ----------

def test_bull_call_spread_comparator_is_a_call_matching_the_buy_leg(tmp_path):
    contracts = [_contract("call", 100.0, 2.4, 2.5), _contract("call", 110.0, 0.9, 1.0)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bull-call-spread", 120.0), path)
    res = next(r for r in result.results if r.strategy == "bull-call-spread")
    cv = res.candidates[0]
    long_leg = cv.valuation.long_leg

    assert cv.comparator is not None
    assert cv.comparator.option_type == "call"
    assert cv.comparator.strike == long_leg.strike
    assert cv.comparator.expiry == long_leg.expiry
    assert cv.comparator.cost == long_leg.ask


# ---------- bear-put-spread → comparator 是 Long Put（不是 D1 舊 bug 的 call）----------

def test_bear_put_spread_comparator_is_a_put_matching_the_buy_leg_not_a_call(tmp_path):
    """這正是 #115 要修正的既有缺陷（D1／#14 的 `_spread_catchup_price`
    對 put 買腿去找「同履約價的 call」）——新 comparator 對 put spread
    必須是 put，不是 call，且是買腿自己這張合約，不是另外查出來的。"""
    contracts = [
        _contract("put", 100.0, 3.9, 4.0), _contract("put", 90.0, 0.9, 1.0),
        _contract("call", 100.0, 2.4, 2.5),   # 存在也不該被 comparator 用到
    ]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bear-put-spread", 80.0), path)
    res = next(r for r in result.results if r.strategy == "bear-put-spread")
    cv = res.candidates[0]
    long_leg = cv.valuation.long_leg
    assert long_leg.option_type == "put"   # 買腿本身確實是 put（較高履約價那隻）

    assert cv.comparator is not None
    assert cv.comparator.option_type == "put"
    assert cv.comparator.strike == long_leg.strike == 100.0
    assert cv.comparator.cost == long_leg.ask == 4.0


# ---------- 不得做任何選取（AC 明文要求的可證明性） ----------

def test_comparator_construction_never_calls_find_contract(tmp_path):
    """D1 舊 bug 的根源就是呼叫 `find_contract` 查另一張合約——新
    comparator 完全不該碰這個函式。直接對 `_spread_comparator` 本身
    斷言（不是整條 `run_offline` 管線）：舊的 `_spread_catchup_price`
    （D1／#14，刻意保留不動，見 `CandidateView.catchup_price` 註解）
    仍然會為 put 買腿呼叫 `find_contract`，那是既有、被有意保留的行為，
    跟這裡要證明的「新 comparator 完全不搜尋」是兩件事，混在一起測
    會把舊欄位的既有行為誤判成新欄位的缺陷。"""
    from datetime import date

    from option_chaser.valuation import evaluate_spread

    long_leg = _contract("put", 100.0, 3.9, 4.0)
    short_leg = _contract("put", 90.0, 0.9, 1.0)
    p = AnalysisParams(strategy="bear-put-spread", target_price=80.0,
                       target_month="2026-10")
    sv = evaluate_spread(long_leg, short_leg, spot=100.0,
                         today=date(2026, 7, 15), p=p)

    with patch("option_chaser.service.find_contract") as mock_find:
        mock_find.side_effect = AssertionError("comparator 不該呼叫 find_contract")
        comparator = service._spread_comparator(sv, spot=100.0,
                                                 today=date(2026, 7, 15), p=p)

    assert comparator is not None
    assert comparator.option_type == "put"
    mock_find.assert_not_called()


def test_comparator_construction_never_calls_legacy_ranking_or_classification(tmp_path):
    """AC：「no candidate search, no call into legacy single-leg ranking,
    no Delta band classification anywhere on this path」——直接對
    `_spread_comparator` 呼叫本身斷言，monkeypatch `ranking.classify`／
    `ranking.rank` 讓它們一被呼叫就炸。"""
    from datetime import date

    from option_chaser.valuation import evaluate_spread

    long_leg = _contract("put", 100.0, 3.9, 4.0)
    short_leg = _contract("put", 90.0, 0.9, 1.0)
    p = AnalysisParams(strategy="bear-put-spread", target_price=80.0,
                       target_month="2026-10")
    sv = evaluate_spread(long_leg, short_leg, spot=100.0,
                         today=date(2026, 7, 15), p=p)

    with patch("option_chaser.ranking.classify") as mock_classify, \
         patch("option_chaser.ranking.rank") as mock_rank, \
         patch("option_chaser.ranking.rank_spreads") as mock_rank_spreads:
        mock_classify.side_effect = AssertionError("comparator 不該做分級")
        mock_rank.side_effect = AssertionError("comparator 不該做排名")
        mock_rank_spreads.side_effect = AssertionError("comparator 不該做排名")
        comparator = service._spread_comparator(sv, spot=100.0,
                                                 today=date(2026, 7, 15), p=p)

    assert comparator is not None
    assert comparator.option_type == "put"
    mock_classify.assert_not_called()
    mock_rank.assert_not_called()
    mock_rank_spreads.assert_not_called()


# ---------- matrix：同 grid、同形狀 ----------

def test_comparator_matrix_matches_the_spreads_own_grid_shape(tmp_path):
    contracts = [_contract("call", 100.0, 2.4, 2.5), _contract("call", 110.0, 0.9, 1.0)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bull-call-spread", 120.0), path)
    res = next(r for r in result.results if r.strategy == "bull-call-spread")
    cv = res.candidates[0]

    assert cv.comparator.matrix.prices == cv.matrix.prices
    assert cv.comparator.matrix.dates == cv.matrix.dates
    assert len(cv.comparator.matrix.cells) == len(cv.matrix.cells)
    assert all(len(crow) == len(srow)
              for crow, srow in zip(cv.comparator.matrix.cells, cv.matrix.cells))


# ---------- 缺席誠實：買腿報價缺失 → None，不假造 ----------

def test_comparator_is_none_when_buy_legs_ask_is_missing(tmp_path):
    """結構上不該發生（上游過濾已保證雙腿報價齊全）——這裡直接呼叫
    `_spread_comparator` 用一個手造的 ask=None 買腿驗證防禦性核對本身
    確實生效，不假造一個 cost。"""
    from datetime import date

    from option_chaser.valuation import LegCarry, SpreadValuation

    long_leg = OptionContract(contract_symbol="C100", option_type="call",
                              strike=100.0, expiry=EXPIRY, bid=None, ask=None,
                              last=None, volume=0, open_interest=0,
                              implied_volatility=None)
    short_leg = _contract("call", 110.0, 0.9, 1.0)
    carry = LegCarry(q=0.0, sigma=0.3, carry_calibrated=False)
    sv = SpreadValuation(
        long_leg=long_leg, short_leg=short_leg, width=10.0, net_mid=1.0,
        net_worst=1.0, net_delta=0.3, breakeven=101.0, breakeven_vs_target=0.1,
        effective_leverage=1.0, scenario_values=((0.0, 1.0),), baseline_value=1.0,
        l2=1.0, l3=1.0, max_profit=9.0, max_loss=1.0,
        long_carry=carry, short_carry=carry)
    p = AnalysisParams(strategy="bull-call-spread", target_price=120.0,
                       target_month="2026-10")

    comparator = service._spread_comparator(sv, spot=100.0,
                                             today=date(2026, 7, 15), p=p)
    assert comparator is None


# ---------- 單腿候選恆無 comparator ----------

def test_single_leg_candidate_has_no_comparator(tmp_path):
    contracts = [_contract("call", 100.0, 2.4, 2.5)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("long-call", 120.0), path)
    res = next(r for r in result.results if r.strategy == "long-call")
    assert res.candidates[0].comparator is None
