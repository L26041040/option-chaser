from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract
from option_chaser.ranking import rank, build_reasons

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-08")


def make_val(sym, strike, bid, ask, iv, expiry="2026-11-20"):
    c = OptionContract(contract_symbol=sym, option_type="call", strike=strike, expiry=expiry,
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


def test_balanced_pro_intrinsic_ratio():
    vals, ranked = setup_ranked()
    pros, _ = build_reasons(ranked["balanced"][0], "balanced",
                            ranked, 100.0, 3, P)
    assert any("內在價值佔權利金" in s for s in pros)


def test_aggressive_fallback_when_not_global_top():
    # Create two aggressive contracts with different returns
    vals = [
        make_val("aggr_high", 110.0, 3.0, 3.25, 0.30, "2026-10-16"),
        make_val("aggr_low", 115.0, 1.5, 1.75, 0.28, "2026-10-16"),
    ]
    ranked = rank(vals, P)
    # The second contract (lower return) should have fallback sentence
    pros, _ = build_reasons(ranked["aggressive"][1], "aggressive",
                            ranked, 100.0, 2, P)
    assert any("同級距中排名靠前" in s for s in pros)
    assert not any("基準情境報酬率最高" in s for s in pros)


def test_spread_warning_con():
    vals = [make_val("spread_warn", 110.0, 3.00, 3.35, 0.30, "2026-10-16")]
    ranked = rank(vals, P)
    _, cons = build_reasons(ranked["aggressive"][0], "aggressive",
                            ranked, 100.0, 1, P)
    assert any("買賣價差偏大" in s for s in cons)


def test_guidance_judgments_included_in_cons():
    vals = [make_val("guidance_all", 95.0, 30.6, 31.0, 0.9, "2026-10-16")]
    ranked = rank(vals, P)
    # This contract (strike 95) has delta ~0.64, classified as balanced
    _, cons = build_reasons(ranked["balanced"][0], "balanced",
                            ranked, 100.0, 1, P)
    assert any("超過劇本內在價值" in s for s in cons)


def test_conservative_put_gets_no_total_loss_warning():
    p_put = AnalysisParams(target_price=80.0, target_month="2026-08", strategy="long-put")
    c = OptionContract(contract_symbol="P115", option_type="put", strike=115.0,
                       expiry="2026-11-20", bid=16.6, ask=17.0, last=None,
                       volume=50, open_interest=200, implied_volatility=0.30)
    from option_chaser.valuation import evaluate_contract
    from option_chaser.ranking import rank
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=p_put)
    assert abs(v.delta) > 0.65  # conservative band
    ranked = rank([v], p_put)
    _, cons = build_reasons(ranked["conservative"][0], "conservative", ranked, 100.0, 1, p_put)
    assert not any("權利金可能全損" in s for s in cons)


def test_half_way_profit_claim_is_judged_at_the_candidates_own_expiry():
    """OPTION-CHASER-CLOSEOUT-003（PR #250 merge gate review 抓到）：
    「劇本半對仍獲利」原本在**固定日曆錨點**（附錄 A9）上判定，對到期日
    晚於錨點的候選會說出與到期真相相反的話。

    這張 K95 call 的到期日（2026-12-18）晚於 `target_month="2026-10"` 的
    錨點（2026-10-16），delta 0.672 落在保守型級距（這句話只在保守型
    出現）。半價位是 110.0（現價 100 → 目標 120 的中點）：
    - 在錨點那天它還沒到期，殘留兩個月時間價值 → 值 **16.32 > ask 16.0**，
      舊實作因此印出「劇本半對仍獲利」
    - 但它真正到期時，標的停在 110.0 的內在價值只有 **15.00 < 16.0**，
      使用者實際上是**虧損**的

    這句話是講給使用者聽的事實陳述，不能用一個該候選根本還沒到期的
    日期去判定——估值日已與 `baseline_return`／`return_at_price` 對齊
    成候選自身到期日。

    ⚠ 這條測試的參數是刻意挑過的：級距必須是保守型（否則整個分支不會
    執行，斷言變成恆真的空話——本測試第一版就犯了這個錯，用 K110 寫，
    它落在別的級距，修法前也照樣綠），且「錨點判定」與「到期真相」必須
    真的相反（16.32 > 16.0 但 15.00 < 16.0）。"""
    p = AnalysisParams(target_price=120.0, target_month="2026-10")
    c = OptionContract(contract_symbol="C95", option_type="call", strike=95.0,
                       expiry="2026-12-18", bid=15.8, ask=16.0, last=None,
                       volume=10, open_interest=100, implied_volatility=0.30)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=p)
    ranked = rank([v], p)
    # 前提斷言：這個分支只在保守型級距執行，挑錯級距整條測試就是空的。
    assert ranked["conservative"], "fixture 必須落在保守型級距，否則斷言恆真"
    pros, _ = build_reasons(ranked["conservative"][0], "conservative",
                            ranked, 100.0, 1, p)
    assert not any("劇本半對仍獲利" in s for s in pros), (
        "半價位 110.0 時這張 K95 call 到期內在價值 15.00 < ask 16.0，"
        "使用者是虧損的——不得宣稱『劇本半對仍獲利』")
