from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract
from option_chaser.ranking import classify, rank, baseline_return, BAND_ORDER

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=0)


def test_classify_boundaries():
    bands = (0.35, 0.65)
    assert classify(0.34999, bands) == "aggressive"
    assert classify(0.35, bands) == "balanced"      # boundary inclusive to balanced
    assert classify(0.65, bands) == "balanced"      # boundary inclusive to balanced
    assert classify(0.65001, bands) == "conservative"


def make_val(sym, strike, bid, ask, iv, expiry="2026-10-16"):
    c = OptionContract(contract_symbol=sym, option_type="call", strike=strike, expiry=expiry,
                       bid=bid, ask=ask, last=None, volume=10,
                       open_interest=100, implied_volatility=iv)
    return evaluate_contract(c, spot=100.0, today=TODAY, p=P)


def test_rank_sorts_by_baseline_return_and_truncates():
    vals = [
        make_val("otm1", 110.0, 3.0, 3.2, 0.30),
        make_val("otm2", 115.0, 1.5, 1.7, 0.30),
        make_val("otm3", 125.0, 0.4, 0.5, 0.30),
        make_val("otm4", 130.0, 0.2, 0.3, 0.30),
    ]
    p1 = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                        min_days_after=45, delay_days=0, top=3)
    ranked = rank(vals, p1)
    agg = ranked["aggressive"]
    assert len(agg) == 3  # truncated from 4
    rets = [baseline_return(v) for v in agg]
    assert rets == sorted(rets, reverse=True)


def test_empty_band_present_as_empty_list():
    ranked = rank([make_val("otm1", 110.0, 3.0, 3.2, 0.30)], P)
    assert set(ranked.keys()) == set(BAND_ORDER)
    assert ranked["conservative"] == [] and ranked["balanced"] == []


def test_tie_break_total_order():
    # identical baseline return by construction: same strike/iv/quotes, different symbol
    a = make_val("AAA", 110.0, 3.0, 3.2, 0.30)
    b = make_val("BBB", 110.0, 3.0, 3.2, 0.30)
    ranked = rank([b, a], P)
    syms = [v.contract.contract_symbol for v in ranked["aggressive"]]
    assert syms == ["AAA", "BBB"]  # lexicographic contract_symbol as final key
