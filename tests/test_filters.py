from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import apply_filters

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28", min_days_after=45)
# expiry must be >= 2026-10-12


def make(sym="A", strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25,
         iv=0.38, volume=100, oi=100):
    return OptionContract(contract_symbol=sym, option_type="call", strike=strike, expiry=expiry,
                          bid=bid, ask=ask, last=None, volume=volume,
                          open_interest=oi, implied_volatility=iv)


def test_each_stage_rejects():
    contracts = [
        make("ok"),
        make("early", expiry="2026-09-18"),          # stage 1
        make("zerobid", bid=0.0),                    # stage 2
        make("nullbid", bid=None),                   # stage 2 (null counts as fail)
        make("crossed", bid=3.0, ask=2.0),           # stage 2
        make("lowiv", iv=0.001),                     # stage 3
        make("nulliv", iv=None),                     # stage 3
        make("lowoi", oi=5),                         # stage 4
        make("wide", bid=4.0, ask=6.0),              # stage 5: spread 2 > max(0.10, .15*5)
    ]
    passed, rep = apply_filters(contracts, P, TODAY)
    assert [c.contract_symbol for c in passed] == ["ok"]
    assert rep.total == 9 and rep.passed == 1
    assert [(s.label, s.removed) for s in rep.stages] == [
        ("到期日不符", 1), ("報價異常", 3), ("IV 異常", 2),
        ("OI/成交量不足", 1), ("Spread 過寬", 1),
    ]


def test_min_expiry_condition():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       min_days_after=0, min_expiry="2026-11-01")
    passed, _ = apply_filters([make("oct"), make("nov", expiry="2026-11-20")], p, TODAY)
    assert [c.contract_symbol for c in passed] == ["nov"]


def test_spread_floor_admits_tick_bound_cheap_contract():
    # bid .05 / ask .15: spread .10, mid .10; .10 <= max(0.10, .15*.10=.015) -> pass
    passed, _ = apply_filters([make("cheap", bid=0.05, ask=0.15)], P, TODAY)
    assert len(passed) == 1


def test_min_volume_optional_gate():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       min_days_after=45, min_volume=1)
    passed, rep = apply_filters([make("novol", volume=0)], p, TODAY)
    assert passed == [] and rep.stages[3].removed == 1


def test_volume_zero_passes_by_default():
    passed, _ = apply_filters([make("novol", volume=0)], P, TODAY)
    assert len(passed) == 1
