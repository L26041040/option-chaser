from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import apply_filters

P = AnalysisParams(target_price=120.0, target_month="2026-08")


def make(sym="A", strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25,
         iv=0.38, volume=100, oi=100, option_type="call"):
    return OptionContract(contract_symbol=sym, option_type=option_type, strike=strike, expiry=expiry,
                          bid=bid, ask=ask, last=None, volume=volume,
                          open_interest=oi, implied_volatility=iv)


def test_each_stage_rejects():
    contracts = [
        make("ok"),
        make("zerobid", bid=0.0),                    # stage 1
        make("nullbid", bid=None),                   # stage 1 (null counts as fail)
        make("crossed", bid=3.0, ask=2.0),           # stage 1
        make("lowiv", iv=0.001),                     # stage 2
        make("nulliv", iv=None),                     # stage 2
        make("lowoi", oi=5),                         # stage 3
        make("wide", bid=4.0, ask=6.0),              # stage 4: spread 2 > max(0.10, .15*5)
    ]
    passed, rep = apply_filters(contracts, P)
    assert [c.contract_symbol for c in passed] == ["ok"]
    assert rep.total == 8 and rep.passed == 1
    assert [(s.label, s.removed) for s in rep.stages] == [
        ("報價異常", 3), ("IV 異常", 2), ("OI/成交量不足", 1), ("Spread 過寬", 1),
    ]


def test_no_expiry_condition_survives():
    """到期日取捨完全由六點選取規則負責——過濾層不得有任何到期日條件。

    錨點前方、早於目標月的到期日與其他到期日受完全相同的品質標準檢驗。
    """
    early = make("early", expiry="2026-07-17")     # 遠早於目標月 2026-08
    late = make("late", expiry="2029-01-19")       # 遠晚於目標月
    passed, rep = apply_filters([early, late], P)
    assert [c.contract_symbol for c in passed] == ["early", "late"]
    assert not any("到期日" in s.label for s in rep.stages)


def test_side_selection_defines_total():
    calls = [make("c1"), make("c2")]
    puts = [make("p1", option_type="put")]
    _, rep = apply_filters(calls + puts, P)
    assert rep.total == 2  # puts not counted for long-call
    p2 = AnalysisParams(target_price=80.0, target_month="2026-08",
                        strategy="long-put")
    _, rep2 = apply_filters(calls + puts, p2)
    assert rep2.total == 1


def test_spread_floor_admits_tick_bound_cheap_contract():
    # bid .05 / ask .15: spread .10, mid .10; .10 <= max(0.10, .15*.10=.015) -> pass
    passed, _ = apply_filters([make("cheap", bid=0.05, ask=0.15)], P)
    assert len(passed) == 1


def test_min_volume_optional_gate():
    p = AnalysisParams(target_price=120.0, target_month="2026-08", min_volume=1)
    passed, rep = apply_filters([make("novol", volume=0)], p)
    assert passed == [] and rep.stages[2].removed == 1


def test_volume_zero_passes_by_default():
    passed, _ = apply_filters([make("novol", volume=0)], P)
    assert len(passed) == 1
