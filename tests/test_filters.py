from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import apply_filters, is_spread_wide

P = AnalysisParams(target_price=120.0, target_month="2026-08")


def make(sym="A", strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25,
         iv=0.38, volume=100, oi=100, option_type="call"):
    return OptionContract(contract_symbol=sym, option_type=option_type, strike=strike, expiry=expiry,
                          bid=bid, ask=ask, last=None, volume=volume,
                          open_interest=oi, implied_volatility=iv)


def test_each_stage_rejects():
    """FB5-02（#63）：買賣價差寬度也從硬門檻移除（spec #61 三分類——與
    OI／成交量同屬 C 類品質標示），現在只剩兩關（A 類報價健全性、B 類
    IV 數學前提）。`lowoi` 與 `wide` 都不再被任何一關擋下，直接進
    `passed`——它們是否要標示「品質有疑慮」是 `service.py` 的事，不是
    `filters.py` 的事，這裡只管誰進得了池子。"""
    contracts = [
        make("ok"),
        make("zerobid", bid=0.0),                    # stage 1
        make("nullbid", bid=None),                   # stage 1 (null counts as fail)
        make("crossed", bid=3.0, ask=2.0),           # stage 1
        make("lowiv", iv=0.001),                     # stage 2
        make("nulliv", iv=None),                     # stage 2
        make("lowoi", oi=5),                         # 不再被任何一關擋下（FB5-01）
        make("wide", bid=4.0, ask=6.0),               # 不再被任何一關擋下（FB5-02）
    ]
    passed, rep = apply_filters(contracts, P)
    assert [c.contract_symbol for c in passed] == ["ok", "lowoi", "wide"]
    assert rep.total == 8 and rep.passed == 3
    assert [(s.label, s.removed) for s in rep.stages] == [
        ("報價異常", 3), ("IV 異常", 2),
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


def test_wide_spread_never_excludes_a_candidate():
    """FB5-02（#63）核心裁示：買賣價差再寬也不再有生殺大權——本 repo
    主數字採最差成交口徑，寬價差的候選成本已經被誠實算高、報酬率已經
    被誠實壓低，硬門檻是同一件事罰兩次。"""
    passed, _ = apply_filters([make("verywide", bid=1.0, ask=9.0)], P)
    assert len(passed) == 1


# --- is_spread_wide：FB5-02 新增的純函式，取代舊 spread_ok 硬門檻的公式，
# 供 service.py 判定要不要標「品質標示」（不影響誰進得了候選池）。 ---

def test_is_spread_wide_matches_the_old_hard_gate_formula():
    """公式與舊版 `spread_ok` 完全相同（`max(spread_floor, max_spread_pct*mid)`），
    只是從「刷掉」改成「回傳布林值供標示」——這正是 spec #61 三分類的核心：
    C 類品質標示不是新規則，是舊規則換了個用途。"""
    # spread 2.0, mid 5.0, threshold max(0.10, 0.15*5.0=0.75) -> 2.0 > 0.75 -> wide
    assert is_spread_wide(4.0, 6.0, P) is True
    # spread .10, mid .10, threshold max(0.10, .15*.10=.015)=0.10 -> .10 <= .10 -> not wide
    assert is_spread_wide(0.05, 0.15, P) is False


def test_is_spread_wide_boundary_is_inclusive():
    """邊界值本身不算寬——與舊 `spread_ok` 的 `<=` 語意一致，不是新規則。"""
    p = AnalysisParams(target_price=120.0, target_month="2026-08",
                       spread_floor=0.0, max_spread_pct=0.10)
    # spread 1.0, mid 10.0, threshold max(0, 0.10*10.0)=1.0 -> 1.0 <= 1.0 -> not wide
    assert is_spread_wide(9.5, 10.5, p) is False


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
