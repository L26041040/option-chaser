from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import (
    evaluate_spread, spread_scenario_value, spread_guidance_judgments,
)

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-08",
                   strategy="bull-call-spread")


def make(sym, strike, bid, ask, iv=0.35, opt="call", expiry="2026-10-16"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


def test_value_clamped_to_width_and_zero():
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 105.0, 5.0, 5.2)
    # very deep scenario: both far ITM -> raw diff < width e^{-rT} but clamps hold
    v_hi = spread_scenario_value(lng, sht, 500.0, date(2026, 8, 28), P)
    assert 0.0 <= v_hi <= 5.0
    v_lo = spread_scenario_value(lng, sht, 1.0, date(2026, 8, 28), P)
    assert v_lo == 0.0


def test_expiry_payoff():
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 110.0, 3.0, 3.2)
    assert spread_scenario_value(lng, sht, 120.0, date(2026, 10, 16), P) == 10.0
    assert spread_scenario_value(lng, sht, 105.0, date(2026, 10, 16), P) == 5.0
    assert spread_scenario_value(lng, sht, 90.0, date(2026, 10, 16), P) == 0.0


def test_deep_itm_spread_value_rises_when_iv_drops():
    # spec §9.7 counter-intuitive lock: net vega sign change — deep ITM vertical
    # gains value as IV falls (value pinned toward width)
    lng, sht = make("L", 60.0, 41.0, 41.4), make("S", 70.0, 31.5, 31.9)
    hi_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=+0.2)
    lo_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=-0.2)
    assert lo_iv > hi_iv


def test_evaluate_spread_fields_and_l2_min():
    lng, sht = make("L", 110.0, 3.0, 3.25, iv=0.30), make("S", 130.0, 0.05, 0.15, iv=0.45)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=P)
    assert sv.width == 20.0
    assert abs(sv.net_mid - (3.125 - 0.10)) < 1e-12
    assert abs(sv.net_worst - (3.25 - 0.05)) < 1e-12
    # T12（附錄 A14.2）：成本衍生數字＝net_worst 口徑
    assert sv.breakeven == 110.0 + sv.net_worst
    assert sv.l2 == min(v for _, v in sv.scenario_values)
    assert sv.l2 <= sv.baseline_value + 1e-12
    assert not hasattr(sv, "l1")
    assert abs(sv.max_profit - (20.0 - sv.net_worst)) < 1e-12


def test_bear_put_breakeven():
    p = AnalysisParams(target_price=80.0, target_month="2026-08",
                       strategy="bear-put-spread")
    lng = make("L", 100.0, 5.2, 5.4, iv=0.36, opt="put")
    sht = make("S", 85.0, 1.1, 1.25, iv=0.35, opt="put")
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=p)
    assert sv.breakeven == 100.0 - sv.net_worst
    assert abs(sv.breakeven_vs_target - (sv.breakeven - 80.0) / 80.0) < 1e-9


def test_spread_judgments_trigger():
    # overpriced quotes: net_worst above every ceiling. T3 起基準值＝到期
    # payoff，目標價 115 落在兩腳之間 → payoff 5.0，而 net_worst 6.1 高於它。
    p = AnalysisParams(target_price=115.0, target_month="2026-08",
                       strategy="bull-call-spread")
    lng = make("L", 110.0, 6.2, 6.5, iv=0.30)
    sht = make("S", 120.0, 0.4, 0.5, iv=0.30)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=p)
    assert sv.baseline_value == 5.0 and sv.net_worst > sv.baseline_value
    msgs = spread_guidance_judgments(sv, p)
    assert any("最保守 IV 情境" in m for m in msgs)
