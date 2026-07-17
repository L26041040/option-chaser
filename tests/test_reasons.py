from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract
from option_chaser.ranking import rank, build_reasons

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=0)


def make_val(sym, strike, bid, ask, iv, expiry="2026-11-20"):
    c = OptionContract(contract_symbol=sym, strike=strike, expiry=expiry,
                       bid=bid, ask=ask, last=None, volume=10,
                       open_interest=100, implied_volatility=iv)
    return evaluate_contract(c, spot=100.0, today=TODAY, p=P)


def setup_ranked():
    vals = [
        make_val("cons", 90.0, 13.0, 13.4, 0.34),          # conservative
        make_val("bal", 105.0, 5.3, 5.5, 0.36, "2026-10-16"),  # balanced
        make_val("aggr", 110.0, 3.0, 3.25, 0.30, "2026-10-16"),  # aggressive
    ]
    return vals, rank(vals, P)


def test_conservative_pro_mentions_breakeven():
    vals, ranked = setup_ranked()
    pros, _ = build_reasons(ranked["conservative"][0], "conservative",
                            ranked, 100.0, 3, P)
    assert any("breakeven" in s for s in pros)


def test_aggressive_pro_top_return_claim():
    vals, ranked = setup_ranked()
    pros, _ = build_reasons(ranked["aggressive"][0], "aggressive",
                            ranked, 100.0, 3, P)
    # aggr has the highest baseline return of the three -> global-top sentence
    assert any("基準情境報酬率最高" in s for s in pros)


def test_low_delta_con_total_loss_warning():
    vals, ranked = setup_ranked()
    _, cons = build_reasons(ranked["aggressive"][0], "aggressive",
                            ranked, 100.0, 3, P)
    assert any("權利金可能全損" in s for s in cons)


def test_max_cost_con_on_most_expensive_first_pick():
    vals, ranked = setup_ranked()
    _, cons = build_reasons(ranked["conservative"][0], "conservative",
                            ranked, 100.0, 3, P)
    assert any("本金需求最大" in s for s in cons)
