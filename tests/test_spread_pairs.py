from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import generate_spread_pairs

P_BCS = AnalysisParams(target_price=120.0, target_month="2026-08",
                       strategy="bull-call-spread")


def make(sym, strike, bid, ask, expiry="2026-10-16", opt="call"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=0.35)


def test_bull_call_pairing_and_sanity():
    legs = [make("A", 100.0, 5.0, 5.2), make("B", 110.0, 2.0, 2.2),
            make("C", 120.0, 0.8, 1.0), make("N", 105.0, 3.0, 3.2, expiry="2026-11-20")]
    pairs, rep = generate_spread_pairs(legs, P_BCS)
    # same-expiry combos: C(3,2)=3 from Oct16; Nov20 alone has none
    assert rep.total_pairs == 3
    for lng, sht in pairs:
        assert lng.strike < sht.strike and lng.expiry == sht.expiry


def test_sanity_rejects_counted():
    # net_mid <= 0: long cheaper than short (crossed pricing)
    legs = [make("A", 100.0, 1.0, 1.1), make("B", 110.0, 2.0, 2.2)]
    pairs, rep = generate_spread_pairs(legs, P_BCS)
    assert pairs == [] and rep.removed_sanity == 1 and rep.total_pairs == 1
    # net_worst >= width: 30-wide quotes on a 5-wide spread
    legs2 = [make("A", 100.0, 31.0, 32.0), make("B", 105.0, 1.0, 1.2)]
    pairs2, rep2 = generate_spread_pairs(legs2, P_BCS)
    assert pairs2 == [] and rep2.removed_sanity == 1


def test_bear_put_long_is_higher_strike():
    p = AnalysisParams(target_price=80.0, target_month="2026-08",
                       strategy="bear-put-spread")
    legs = [make("L", 100.0, 5.0, 5.2, opt="put"), make("S", 85.0, 1.0, 1.2, opt="put")]
    pairs, rep = generate_spread_pairs(legs, p)
    assert len(pairs) == 1
    lng, sht = pairs[0]
    assert lng.strike == 100.0 and sht.strike == 85.0
