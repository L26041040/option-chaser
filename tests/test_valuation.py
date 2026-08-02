from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import (
    bs_call, bs_put, catchup_price, evaluate_contract, intrinsic_value,
    scenario_leg_value,
)

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-08")
P_PUT = AnalysisParams(target_price=80.0, target_month="2026-08", strategy="long-put")


def make_contract(**kw):
    base = dict(contract_symbol="XYZ261016C00110000", option_type="call",
                strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25, last=3.1,
                volume=152, open_interest=830, implied_volatility=0.38)
    base.update(kw)
    return OptionContract(**base)


def test_call_anchors_and_scenarios():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    # T12（附錄 A14.2）：breakeven 等成本衍生數字＝Ask 口徑
    assert v.mid == 3.125 and v.breakeven == 113.25
    assert abs(v.breakeven_vs_spot - 0.1325) < 1e-9
    assert abs(v.breakeven_vs_target - (120 - 113.25) / 120) < 1e-9
    t_rem = (date(2026, 10, 16) - P.anchor).days / 365.0
    assert v.floor_value == 10.0 == v.l1
    for shift, val in v.scenario_values:
        assert abs(val - max(bs_call(120.0, 110.0, t_rem, P.rate, 0.38 * (1 + shift)), 10.0)) < 1e-12
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_put_anchors_mirror():
    c = make_contract(contract_symbol="XYZ261016P00090000", option_type="put",
                      strike=90.0, bid=2.8, ask=3.0, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.breakeven == 90.0 - 3.0                 # T12：Ask 口徑
    assert abs(v.breakeven_vs_spot - (100.0 - 87.0) / 100.0) < 1e-9
    assert abs(v.breakeven_vs_target - (87.0 - 80.0) / 80.0) < 1e-9  # put cushion = (BE−target)/target
    assert v.floor_value == 10.0 == v.l1  # max(90−80,0)
    assert v.delta < 0
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_scenario_leg_value_at_and_after_expiry():
    c = make_contract()
    assert scenario_leg_value(c, 120.0, date(2026, 10, 16), P) == 10.0
    assert scenario_leg_value(c, 120.0, date(2026, 11, 1), P) == 10.0  # past expiry -> intrinsic


def test_deep_itm_put_scenario_clamped():
    c = make_contract(contract_symbol="P120", option_type="put", strike=120.0,
                      bid=41.0, ask=41.5, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.baseline_value == 40.0  # BS European below intrinsic -> clamped


# ---------- D1（#14）：catchup_price —— Long Call 追平價格 S*=K+C×(1+R) ----------

def test_catchup_price_matches_the_spec_example():
    # 需求文件例：TLT K=100、C=2.5、R=500%（5.0）-> S*=115
    assert catchup_price(strike=100.0, call_cost=2.5, baseline_return=5.0) == 115.0


def test_catchup_price_is_where_the_long_call_return_equals_r():
    """數學一致性（D1 Testing Decisions）：標的在 S* 時，該 Long Call 的到期
    報酬率恰等於 R。"""
    strike, cost, r = 100.0, 2.5, 5.0
    s_star = catchup_price(strike=strike, call_cost=cost, baseline_return=r)
    intrinsic = intrinsic_value("call", s_star, strike)
    actual_return = (intrinsic - cost) / cost
    assert abs(actual_return - r) < 1e-9


def test_catchup_price_negative_return_still_meaningful():
    """R 為負值情境 → S* 仍有意義（低於損益兩平也算數），正常算出。"""
    strike, cost, r = 50.0, 4.0, -0.3
    s_star = catchup_price(strike=strike, call_cost=cost, baseline_return=r)
    assert s_star == 50.0 + 4.0 * 0.7
    intrinsic = intrinsic_value("call", s_star, strike)
    actual_return = (intrinsic - cost) / cost
    assert abs(actual_return - r) < 1e-9
