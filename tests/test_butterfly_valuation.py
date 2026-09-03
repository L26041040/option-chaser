"""T15（#230，Initial V2 spec #217）：Butterfly 估值純函式測試。

覆蓋 `butterfly_expiry_payoff()`／`butterfly_breakeven_and_profit_
region()`／`evaluate_butterfly()`——這個結構自己的分段線性算術，不透過
任何通用跨 strategy 的 payoff-envelope／extrema engine（#223 已判定
Initial V2 不需要，正式收斂為 not planned）。
"""
from datetime import date

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import (
    ButterflyProfitRegion,
    american_price,
    butterfly_breakeven_and_profit_region,
    butterfly_expiry_payoff,
    butterfly_guidance_judgments,
    evaluate_butterfly,
)

TODAY = date(2026, 1, 1)
EXPIRY_ISO = "2026-06-01"
EXPIRY = date.fromisoformat(EXPIRY_ISO)
SPOT = 100.0
T_YEARS = (EXPIRY - TODAY).days / 365.0
R, Q, SIGMA = 0.04, 0.0, 0.25
P = AnalysisParams(target_price=100.0, target_month="2026-06", strategy="call-fly")


def _leg(strike: float, sym: str, option_type: str = "call",
        sigma: float = SIGMA) -> OptionContract:
    """用 production 定價函式（`american_price`）本身算出理論價、包一個
    很窄的 bid/ask——round-trip 風格 fixture（已知 sigma 反推回報價），
    不是手猜期望值。"""
    price = american_price(option_type, SPOT, strike, T_YEARS, R, Q, sigma)
    half = 0.01
    return OptionContract(
        contract_symbol=sym, option_type=option_type, strike=strike,
        expiry=EXPIRY_ISO, bid=round(price - half, 4), ask=round(price + half, 4),
        last=round(price, 4), volume=10, open_interest=100,
        implied_volatility=sigma)


# ---------- butterfly_expiry_payoff：純算術，四個知識點各自驗證 ----------

def test_payoff_is_zero_below_the_low_strike_for_calls():
    assert butterfly_expiry_payoff("call", 90, 100, 110, 80) == 0.0
    assert butterfly_expiry_payoff("call", 90, 100, 110, 90) == 0.0


def test_payoff_peaks_at_the_middle_strike():
    # 對稱蝶式：峰值 = K2-K1 = 10
    assert butterfly_expiry_payoff("call", 90, 100, 110, 100) == 10.0


def test_payoff_returns_to_zero_above_the_high_strike_when_wings_are_symmetric():
    assert butterfly_expiry_payoff("call", 90, 100, 110, 110) == 0.0
    assert butterfly_expiry_payoff("call", 90, 100, 110, 200) == 0.0


def test_payoff_slopes_are_plus_one_then_minus_one_regardless_of_wing_width():
    """T15 核心不變量：不論兩翼是否等寬，[K1,K2] 斜率恆 +1、[K2,K3] 斜率
    恆 -1（call／put 皆然）——這是 `butterfly_breakeven_and_profit_
    region()` 用封閉式代數求根、而非迭代逼近的數學基礎。"""
    for k1, k2, k3 in [(90, 100, 110), (95, 100, 130), (60, 100, 105)]:
        left_slope = (butterfly_expiry_payoff("call", k1, k2, k3, k1 + 1)
                     - butterfly_expiry_payoff("call", k1, k2, k3, k1))
        right_slope = (butterfly_expiry_payoff("call", k1, k2, k3, k2 + 1)
                      - butterfly_expiry_payoff("call", k1, k2, k3, k2))
        assert left_slope == 1.0
        assert right_slope == -1.0


def test_asymmetric_wings_produce_a_nonzero_tail_value():
    """Broken-wing：右翼寬度(20) != 左翼寬度(5) 時，S 遠大於 K3 的
    payoff 不是 0，而是 2*K2-K1-K3（call）——這是這個權重結構
    （+1/-2/+1）在非對稱履約價下的真實性質，不是 bug。"""
    tail = butterfly_expiry_payoff("call", 95, 100, 120, 500)
    assert tail == 2 * 100 - 95 - 120  # -15
    assert tail != 0.0


def test_put_butterfly_has_the_same_tent_shape_mirrored():
    """Put 版本：payoff 在高履約價側恆為 0（call 是低履約價側恆為 0）
    ——鏡像對稱，峰值仍在 K2。"""
    assert butterfly_expiry_payoff("put", 90, 100, 110, 200) == 0.0
    assert butterfly_expiry_payoff("put", 90, 100, 110, 100) == 10.0
    assert butterfly_expiry_payoff("put", 90, 100, 110, 50) == 0.0


# ---------- butterfly_breakeven_and_profit_region：邊界案例逐一驗證 ----------

def test_symmetric_wings_yield_two_interior_breakevens():
    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", 90, 100, 110, net_cost=4.0)
    assert breakevens == (94.0, 106.0)
    assert region == ButterflyProfitRegion(lower=94.0, upper=106.0)


def test_peak_not_exceeding_cost_means_no_profit_region_anywhere():
    """峰值（10）扣掉成本（12）為負——到期時任何價位都無法獲利，回傳
    空的損益兩平點與 `None`，不硬擠成一個假的區間。"""
    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", 90, 100, 110, net_cost=12.0)
    assert breakevens == ()
    assert region is None


def test_peak_exactly_equal_to_cost_is_still_no_profit_region():
    """邊界情況：峰值剛好等於成本（`peak_profit == 0`），依函式定義
    `<= 0.0` 視為不獲利——這是刻意的邊界選擇（剛好打平不算「有獲利
    區間」），不是浮點誤差。"""
    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", 90, 100, 110, net_cost=10.0)
    assert breakevens == ()
    assert region is None


def test_symmetric_wings_with_a_net_credit_are_profitable_on_both_flat_tails():
    """對稱蝶式＋淨收入（net_cost 為負，收到的錢）：兩翼 payoff 恆等
    （v1=v3=0），只要 net_cost<0 兩側就同時「已經獲利」。

    CLOSEOUT-004（Finding 1）：兩側都是恆定平台、平台值已高於成本
    ——往兩個方向走多遠到期時都還是獲利，兩個邊界因此**都不存在**，
    回 `None`。修正前填 K1／K3，等於宣稱「跌破 90 或漲過 110 就不
    賺」，而實際上那兩段各自恆賺 $1。"""
    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", 90, 100, 110, net_cost=-1.0)
    assert region is not None
    assert region.lower is None
    assert region.upper is None
    assert breakevens == ()   # 沒有任何價位由虧轉盈
    # 非空斷言：翼外真的獲利，不是「算不出來」。
    assert butterfly_expiry_payoff("call", 90, 100, 110, 1.0) - (-1.0) > 0
    assert butterfly_expiry_payoff("call", 90, 100, 110, 9999.0) - (-1.0) > 0


def test_asymmetric_wings_with_one_tail_already_profitable_and_one_real_root():
    """Broken-wing（k1=95,k2=100,k3=120）＋淨收入：call 左翼恆為 0，
    v3=2*100-95-120=-15（右翼真的會虧）。net_cost=-5（收到 $5）時，
    左翼 0>-5 已經獲利（CLOSEOUT-004 起＝沒有下界，`None`），右翼仍有
    一個真正的交叉點（峰值 payoff(100)=5，peak_profit=5-(-5)=10，
    交叉點＝K2+10=110，剛好等於 K3——這是這組數字的巧合，不是函式
    邊界的特殊處理）。單側無界時 `breakeven_points` 只收錄真的那一個。"""
    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", 95, 100, 120, net_cost=-5.0)
    assert region is not None
    assert region.lower is None   # 左側恆賺，沒有下界
    assert region.upper == 110.0  # 真正的交叉點：K2 + peak_profit = 100+10
    assert breakevens == (110.0,)


# ---------- CLOSEOUT-004（PR #250 review Finding 1）：unbounded 側 ----------

def test_broken_wing_debit_with_a_profitable_outer_plateau_has_no_upper_bound():
    """Review Finding 1 的重現案例，逐字對應。

    call-fly K1=100 / K2=110 / K3=115（左翼 10 寬、右翼 5 寬，broken
    wing），到期 payoff 在 K3 之外是恆定平台
    `v3 = (K2-K1)-(K3-K2) = 5`。進場成本 4.0 < 5，代表**標的漲多高
    到期時都還是賺 $1**——獲利區間在上方沒有界。

    修正前：`upper` 被填成 K3=115、`breakeven_points` 因此含 115，
    而 115 那一點的損益是 +1.0（根本不是損益兩平點），下游文案還會
    說「區間外到期時無法獲利」——對使用者的假話。"""
    k1, k2, k3, cost = 100.0, 110.0, 115.0, 4.0
    # 前提（非空斷言的基礎）：翼外平台真的高於成本，而且到多遠都一樣。
    assert butterfly_expiry_payoff("call", k1, k2, k3, k3) - cost == 1.0
    assert butterfly_expiry_payoff("call", k1, k2, k3, 10_000.0) - cost == 1.0

    breakevens, region = butterfly_breakeven_and_profit_region(
        "call", k1, k2, k3, net_cost=cost)

    assert region is not None
    assert region.lower == 104.0   # 真正的交叉點：K1 - (v1 - cost) = 100+4
    assert region.upper is None    # 上方沒有界
    assert breakevens == (104.0,)  # 只有一個真的損益兩平點
    assert k3 not in breakevens    # 修正前這裡是 115.0


def test_broken_wing_put_fly_mirrors_the_unbounded_side_downward():
    """put-fly 的鏡射：右翼寬於左翼時 `v1 = (K3-K2)-(K2-K1) > 0`，
    K1 之**下**是獲利的恆定平台——獲利區間在下方沒有界。證明修法不是
    只針對 call 那一側寫死的特例。"""
    k1, k2, k3, cost = 100.0, 105.0, 115.0, 4.0
    assert butterfly_expiry_payoff("put", k1, k2, k3, k1) - cost == 1.0
    assert butterfly_expiry_payoff("put", k1, k2, k3, 0.0) - cost == 1.0

    breakevens, region = butterfly_breakeven_and_profit_region(
        "put", k1, k2, k3, net_cost=cost)

    assert region is not None
    assert region.lower is None
    # 峰值 payoff(K2)=K3-K2=10，peak_profit=10-4=6，上界＝K2+6=111
    # （獨立核對：payoff(111) = 0 - 0 + (115-111) = 4 = cost，確實打平）。
    assert region.upper == 111.0
    assert breakevens == (111.0,)
    assert butterfly_expiry_payoff("put", k1, k2, k3, 111.0) == cost
    assert k1 not in breakevens


def test_every_finite_bound_really_is_a_boundary():
    """把「邊界必須真的是邊界」寫成可執行的不變量，掃過真實 fixture
    的**全部**候選——這條是抓得到舊 bug 的那一條（修正前實測
    `xyz_v6_butterfly_ladder` 9998 組候選中有 4052 組違反、
    `xyz_v7_butterfly_moderate` 323 組中有 159 組違反）。

    不變量：`profit_region` 的某一側若是有限數字，那個方向再走出去
    就**必須**虧損；若那個方向其實仍然獲利，該側就該是 `None`。"""
    from option_chaser.data.snapshot import load_snapshot
    from option_chaser.filters import apply_filters, generate_butterfly_triples

    checked = 0
    for fixture, target in (("tests/fixtures/xyz_v6_butterfly_ladder.json", 110.0),
                            ("tests/fixtures/xyz_v7_butterfly_moderate.json", 106.0)):
        snap = load_snapshot(fixture)
        p = AnalysisParams(target_price=target, target_month="2026-10",
                          strategy="call-fly")
        today = date.fromisoformat(snap.fetched_at[:10])
        qualified, _ = apply_filters(snap.contracts, p)
        triples, _ = generate_butterfly_triples(qualified, p)
        cache: dict = {}
        for lo, mid, hi in triples:
            bv = evaluate_butterfly(lo, mid, hi, snap.spot, today, p, cache)
            if bv.profit_region is None:
                continue
            checked += 1
            k1, k3 = lo.strike, hi.strike
            payoff = lambda S: butterfly_expiry_payoff(
                bv.option_type, k1, mid.strike, k3, S)
            if bv.profit_region.upper is not None:
                # 上界之外必須真的虧（取遠到不可能再有轉折的價位）
                assert payoff(k3 + 10_000.0) - bv.net_worst <= 0, (
                    f"{lo.contract_symbol}/{mid.contract_symbol}/"
                    f"{hi.contract_symbol} 宣稱上界 "
                    f"{bv.profit_region.upper} 但更高的價位仍獲利")
            if bv.profit_region.lower is not None:
                assert payoff(max(k1 - 10_000.0, 0.0)) - bv.net_worst <= 0, (
                    f"{lo.contract_symbol}/{mid.contract_symbol}/"
                    f"{hi.contract_symbol} 宣稱下界 "
                    f"{bv.profit_region.lower} 但更低的價位仍獲利")
    assert checked > 1000, f"只檢查到 {checked} 組，樣本不足以當守門"


# ---------- evaluate_butterfly：完整型別欄位＋跟 brute-force 掃描對照 ----------

def _brute_force_profit_region(option_type, k1, k2, k3, net_cost, lo=50.0,
                               hi=200.0, step=0.001):
    xs = [lo + i * step for i in range(int((hi - lo) / step) + 1)]
    payoffs = [butterfly_expiry_payoff(option_type, k1, k2, k3, x) - net_cost
              for x in xs]
    crossings = []
    prev = None
    for x, v in zip(xs, payoffs):
        if prev is not None and ((prev <= 0 < v) or (prev >= 0 > v)):
            crossings.append(round(x, 3))
        prev = v
    return crossings, max(payoffs)


def test_symmetric_butterfly_matches_a_brute_force_scan():
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    crossings, peak = _brute_force_profit_region(
        "call", 90, 100, 110, bv.net_worst)
    assert bv.profit_region is not None
    assert abs(bv.profit_region.lower - crossings[0]) < 0.01
    assert abs(bv.profit_region.upper - crossings[1]) < 0.01
    assert abs(bv.max_profit - peak) < 1e-9


def test_asymmetric_butterfly_matches_a_brute_force_scan():
    low, mid, high = _leg(95, "LOW"), _leg(100, "MID"), _leg(130, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    crossings, peak = _brute_force_profit_region(
        "call", 95, 100, 130, bv.net_worst)
    assert len(crossings) == 1  # 左翼已經獲利（見上方單元測試同款情境）
    assert bv.profit_region is not None
    assert abs(bv.profit_region.upper - crossings[0]) < 0.01
    assert abs(bv.max_profit - peak) < 1e-9


def test_evaluate_butterfly_fields_and_worst_cost():
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    assert bv.option_type == "call"
    assert bv.net_worst == low.ask - 2.0 * mid.bid + high.ask
    assert bv.net_mid == ((low.bid + low.ask) / 2.0
                          - 2.0 * (mid.bid + mid.ask) / 2.0
                          + (high.bid + high.ask) / 2.0)
    assert bv.l2 == min(v for _, v in bv.scenario_values)
    assert bv.l3 == bv.baseline_value / (1.0 + P.min_return)
    # 對稱蝶式：max_loss 恆等於已付權利金（v1=v3=0）
    assert abs(bv.max_loss - bv.net_worst) < 1e-9


def test_evaluate_butterfly_broken_wing_max_loss_exceeds_the_premium_paid():
    """AC 明文的性質：broken-wing 組合的最壞損失可能超過已付權利金——
    這是這個結構的真實經濟性質，不是既有四策略「max_loss 恆等於成本」
    這條不變量的例外，是 Butterfly 結構性地不保證這條不變量。"""
    low, mid, high = _leg(95, "LOW"), _leg(100, "MID"), _leg(120, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    assert bv.max_loss > bv.net_worst


def test_evaluate_butterfly_baseline_value_uses_the_target_price_at_own_expiry():
    """T3／#17 既有裁示的延伸：排名情境＝標的在**自身到期日**等於目標價。"""
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    p = AnalysisParams(target_price=105.0, target_month="2026-06", strategy="call-fly")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, p)
    expected = butterfly_expiry_payoff("call", 90, 100, 110, 105.0)
    assert abs(bv.baseline_value - expected) < 1e-9


def test_effective_leverage_uses_net_delta_and_spot_over_worst_cost():
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    assert abs(bv.effective_leverage - abs(bv.net_delta) * SPOT / bv.net_worst) < 1e-9


def test_carry_calibration_fallback_matches_today_when_q_unset():
    """`p.q_by_symbol is None`（q 管線未接）——三腿全部退回今天的完整
    行為（q=0、vendor IV），與既有 Spread／單腿同一套 fallback。"""
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    assert bv.low_carry.carry_calibrated is False
    assert bv.low_carry.q == 0.0
    assert bv.low_carry.sigma == low.implied_volatility


# ---------- butterfly_guidance_judgments：鏡射既有 spread 判準 ----------

def test_guidance_judgments_flag_worst_iv_scenario_loss():
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    # 人為構造一個 net_worst 超過 l2 的情境：直接用 dataclasses.replace
    import dataclasses
    inflated = dataclasses.replace(bv, net_worst=bv.l2 + 100.0)
    msgs = butterfly_guidance_judgments(inflated, P)
    assert any("最保守 IV 情境" in m for m in msgs)


def test_guidance_judgments_empty_when_cost_is_comfortably_below_ceilings():
    low, mid, high = _leg(90, "LOW"), _leg(100, "MID"), _leg(110, "HIGH")
    bv = evaluate_butterfly(low, mid, high, SPOT, TODAY, P)
    if bv.net_worst <= bv.l2 and bv.net_worst <= bv.l3:
        assert butterfly_guidance_judgments(bv, P) == []
