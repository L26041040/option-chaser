from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import apply_filters

P = AnalysisParams(target_price=120.0, target_month="2026-08")


def make(sym="A", strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25,
         iv=0.38, volume=100, oi=100, option_type="call"):
    return OptionContract(contract_symbol=sym, option_type=option_type, strike=strike, expiry=expiry,
                          bid=bid, ask=ask, last=None, volume=volume,
                          open_interest=oi, implied_volatility=iv)


def test_each_stage_rejects():
    """FB5-01（#62）：OI／成交量已從硬門檻移除（spec #61 三分類——它們是
    C 類品質標示，不是 A/B 類的資料健全性／數學前提），現在只剩三關。
    `lowoi` 不再是任何一關的受害者，直接進 `passed`。"""
    contracts = [
        make("ok"),
        make("zerobid", bid=0.0),                    # stage 1
        make("nullbid", bid=None),                   # stage 1 (null counts as fail)
        make("crossed", bid=3.0, ask=2.0),           # stage 1
        make("lowiv", iv=0.001),                     # stage 2
        make("nulliv", iv=None),                     # stage 2
        make("lowoi", oi=5),                         # 不再被任何一關擋下
        make("wide", bid=4.0, ask=6.0),              # stage 3: spread 2 > max(0.10, .15*5)
    ]
    passed, rep = apply_filters(contracts, P)
    assert [c.contract_symbol for c in passed] == ["ok", "lowoi"]
    assert rep.total == 8 and rep.passed == 2
    assert [(s.label, s.removed) for s in rep.stages] == [
        ("報價異常", 3), ("IV 異常", 2), ("Spread 過寬", 1),
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


def test_volume_never_excludes_a_candidate():
    """FB5-01（#62）：成交量從來不是門檻——`min_volume` 曾預設 0，
    `volume >= 0` 恆真，是從未起過作用的死條件，本票整條移除。"""
    passed, _ = apply_filters([make("novol", volume=0)], P)
    assert len(passed) == 1


def test_open_interest_never_excludes_a_candidate():
    """FB5-01（#62）核心裁示：未平倉量不再有生殺大權，只要報價／IV／
    價差三關過得了，OI 多低都留在候選池裡（含 0）。"""
    passed, _ = apply_filters([make("zerooi", oi=0)], P)
    assert len(passed) == 1


def test_pool_does_not_collapse_to_a_single_survivor_from_liquidity_alone():
    """回歸防護（spec #61 Testing Decisions 明列）：這正是需求方回報的
    症狀——真實 Cboe 全鏈的某到期日曾因 OI 門檻從 28 筆砍到剩 1 筆，讓
    「該期最高收益」淪為唯一倖存者的假象，而非比較出來的結果。

    這裡用 9 組「報價與 IV 皆正常、但 OI 個位數」的合約重現該情境的
    結構：舊版四道關卡下只有 1 組能通過 OI>=10；新版必須全部 9 組
    都留在池子裡，證明流動性指標不再能把候選池單獨壓垮。
    """
    thin_contracts = [make(f"thin{i}", strike=100.0 + i, oi=i) for i in range(9)]
    passed, rep = apply_filters(thin_contracts, P)
    assert len(passed) == 9
    assert rep.passed == 9
