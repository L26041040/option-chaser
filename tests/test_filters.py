from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import (apply_filters, is_spread_wide,
                                   monotonicity_violations, quality_flag_counts)

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


def test_each_stage_is_tagged_with_its_class():
    """FB5-04（#65）：分類要「在程式碼中明確可讀」——`apply_filters` 的
    兩關各自標好 A／B，不必靠標籤字串猜測。"""
    _, rep = apply_filters([make("ok")], P)
    assert [(s.filter_class, s.label) for s in rep.stages] == [
        ("A", "報價異常"), ("B", "IV 異常"),
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


# --- monotonicity_violations：FB5-03（#64）新增的純函式，無套利一致性
# 檢查（同到期日、同類型，call 非遞增／put 非遞減）。只標不刪，`filters.py`
# 完全不呼叫它——它只服務 `service.py` 的品質標示，不影響誰進得了候選池。

def test_monotonicity_catches_a_call_priced_below_a_higher_strike():
    """需求方原話：「明明 100/105/110，但 105 卻比 100 便宜，這肯定有鬼」
    ——call 履約價越高，ask 應該越低（或持平），這裡反過來了。"""
    low = make("K100", strike=100.0, ask=10.0)
    mid = make("K105", strike=105.0, ask=12.0)   # 違反：比 K100 貴
    high = make("K110", strike=110.0, ask=8.0)
    violations = monotonicity_violations([low, mid, high])
    assert violations == {"K100", "K105"}   # 違反是配對關係，兩邊都標
    assert "K110" not in violations         # K105→K110 這段沒問題（12>=8）


def test_monotonicity_catches_a_put_priced_above_a_higher_strike():
    """put 反過來：履約價越高，ask 應該越高（或持平）。"""
    low = make("K100", strike=100.0, ask=8.0, option_type="put")
    mid = make("K105", strike=105.0, ask=6.0, option_type="put")  # 違反：比 K100 便宜
    violations = monotonicity_violations([low, mid])
    assert violations == {"K100", "K105"}


def test_monotonicity_does_not_flag_non_convex_but_monotone_quotes():
    """驗收標準第二面：不該誤報的不誤報。10/8/3 不是凸的（差分
    -2、-5，二階差分為負），但整條路徑本身仍然單調非遞增——期權市場
    本質非凸（需求方原話），這種形狀合法，不能被當成有鬼。"""
    a = make("a", strike=100.0, ask=10.0)
    b = make("b", strike=105.0, ask=8.0)
    c = make("c", strike=110.0, ask=3.0)
    assert monotonicity_violations([a, b, c]) == frozenset()


def test_monotonicity_ties_are_not_violations():
    """非遞增／非遞減本身就含「持平」——相鄰履約價 ask 相同不算有鬼。"""
    a = make("a", strike=100.0, ask=5.0)
    b = make("b", strike=105.0, ask=5.0)
    assert monotonicity_violations([a, b]) == frozenset()


def test_monotonicity_only_compares_within_the_same_expiry_and_type():
    """不同到期日或不同類型之間沒有單調性關係，不該被拿來互相比較。"""
    call_100 = make("call100", strike=100.0, ask=1.0, option_type="call")
    put_100 = make("put100", strike=100.0, ask=50.0, option_type="put")
    other_expiry = make("later", strike=105.0, ask=200.0,
                        expiry="2027-01-15", option_type="call")
    violations = monotonicity_violations([call_100, put_100, other_expiry])
    assert violations == frozenset()


def test_monotonicity_never_used_as_a_hard_gate():
    """驗收標準：只標不刪——`apply_filters` 完全不呼叫這個函式，候選
    數量不會因為單調性違反而減少。"""
    low = make("K100", strike=100.0, ask=10.0)
    mid = make("K105", strike=105.0, ask=12.0)
    passed, rep = apply_filters([low, mid], P)
    assert len(passed) == 2
    assert not any("單調" in s.label for s in rep.stages)


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


# --- quality_flag_counts：FB5-04（#65），三分類收尾票——把 C 類三個既有
# 判準（零成交量／`is_spread_wide`／`monotonicity_violations`）攤開算整個
# 合格池裡各出現幾次，供過濾統計區與報告尾註呈現「標示」而非「排除」。

def test_quality_flag_counts_tallies_each_class_c_check_over_the_pool():
    # 各自用不同到期日隔開，避免互相被拿去比對單調性（單調性只在同到期日
    # 同類型之間比較），三個判準才能獨立驗證互不干擾。
    quiet = make("quiet", volume=0, expiry="2026-11-20")          # 零成交量
    wide = make("wide", bid=1.0, ask=9.0, expiry="2026-12-18")    # 買賣價差偏大
    low = make("K100", strike=100.0, bid=9.8, ask=10.0)           # 單調性違反的一對
    mid = make("K105", strike=105.0, bid=11.8, ask=12.0)
    clean = make("clean", expiry="2027-01-15")
    contracts = [quiet, wide, low, mid, clean]
    violations = monotonicity_violations(contracts)
    counts = {qf.label: qf.count for qf in quality_flag_counts(contracts, violations, P)}
    assert counts["報價非最新（今日無成交）"] == 1
    assert counts["買賣價差偏大"] == 1
    assert counts["報價與鄰近履約價不一致，疑似陳舊報價"] == 2


def test_quality_flag_counts_never_shrinks_the_pool():
    """驗收標準：只是計數，不是門檻——`apply_filters` 通過的筆數不因
    `quality_flag_counts` 存在而改變（它甚至不被 `apply_filters` 呼叫）。"""
    contracts = [make("quiet", volume=0), make("wide", bid=1.0, ask=9.0)]
    passed, rep = apply_filters(contracts, P)
    quality_flag_counts(passed, frozenset(), P)  # 呼叫本身不應有副作用
    assert len(passed) == 2 and rep.passed == 2


def test_quality_flag_counts_reuses_is_spread_wide_not_a_new_threshold():
    """C 類不發明新門檻——`quality_flag_counts` 的「買賣價差偏大」與
    `is_spread_wide` 對同一組報價的判斷必須完全一致。"""
    c = make("edge", bid=4.0, ask=6.0)   # is_spread_wide(4.0, 6.0, P) is True
    assert is_spread_wide(c.bid, c.ask, P) is True
    counts = {qf.label: qf.count for qf in quality_flag_counts([c], frozenset(), P)}
    assert counts["買賣價差偏大"] == 1


def test_quality_flag_counts_open_interest_not_included():
    """FB5-01 只把 OI 從硬門檻移除、原樣顯示，沒定義「多低算有疑慮」的
    門檻——這裡不發明一個，回傳的三個 key 裡沒有未平倉量。"""
    counts = {qf.label: qf.count
              for qf in quality_flag_counts([make("zerooi", oi=0)], frozenset(), P)}
    assert not any("未平倉" in k or "OI" in k for k in counts)
