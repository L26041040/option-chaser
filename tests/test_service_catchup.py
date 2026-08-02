"""D1（#14）：CandidateView.catchup_price 的服務層接線——S*=K+C×(1+R) 的
K／C／R 三個輸入，都要在服務層（有完整快照）算好，不留給零金融計算的
render 層（見 `webapp/render.py` 模組說明）。純算術本身（S* 的數學正確性）
已由 tests/test_valuation.py 對 `catchup_price()` 覆蓋，這裡只驗證接線：
bull-call-spread 直接用買腿自己的 Ask；bear-put-spread 從同一快照找同履約價
的 call；找不到就是 None，不拋錯。"""
from option_chaser import service
from option_chaser.data.snapshot import save_snapshot
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract, SCHEMA_VERSION
from option_chaser.valuation import catchup_price

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


def test_bull_call_spread_catchup_uses_buy_legs_own_ask(tmp_path):
    """買腿本身就是同履約價的 call，不需要另外查快照。"""
    contracts = [_contract("call", 100.0, 2.4, 2.5), _contract("call", 110.0, 0.9, 1.0)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bull-call-spread", 120.0), path)
    res = next(r for r in result.results if r.strategy == "bull-call-spread")
    assert res.status == "ok"
    cv = res.candidates[0]
    expected = catchup_price(strike=cv.valuation.long_leg.strike, call_cost=2.5,
                             baseline_return=cv.baseline_return)
    assert cv.catchup_price == expected


def test_bear_put_spread_catchup_looks_up_matching_call(tmp_path):
    contracts = [
        _contract("put", 100.0, 3.9, 4.0), _contract("put", 90.0, 0.9, 1.0),
        _contract("call", 100.0, 2.4, 2.5),   # 同履約價的 call，供追平比較查找
    ]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bear-put-spread", 80.0), path)
    res = next(r for r in result.results if r.strategy == "bear-put-spread")
    assert res.status == "ok"
    cv = res.candidates[0]
    assert cv.valuation.long_leg.strike == 100.0   # 買腿＝較高履約價那隻 put
    expected = catchup_price(strike=100.0, call_cost=2.5,
                             baseline_return=cv.baseline_return)
    assert cv.catchup_price == expected


def test_bear_put_spread_catchup_none_when_no_matching_call(tmp_path):
    """買腿履約價沒有對應的 call 報價：找不到，回傳 None，不拋錯。"""
    contracts = [_contract("put", 100.0, 3.9, 4.0), _contract("put", 90.0, 0.9, 1.0)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("bear-put-spread", 80.0), path)
    res = next(r for r in result.results if r.strategy == "bear-put-spread")
    assert res.status == "ok"
    cv = res.candidates[0]
    assert cv.catchup_price is None


def test_single_leg_candidate_has_no_catchup_price(tmp_path):
    """Long Call／Long Put 本身沒有「與 Long Call 比較」的意義（D1 Out of
    Scope）——欄位存在但恆為 None，供 render 層區分「不適用」。"""
    contracts = [_contract("call", 100.0, 2.4, 2.5)]
    path = _write_snap(tmp_path, contracts)
    result = service.run_offline(_request("long-call", 120.0), path)
    res = next(r for r in result.results if r.strategy == "long-call")
    assert res.status == "ok"
    assert res.candidates[0].catchup_price is None
