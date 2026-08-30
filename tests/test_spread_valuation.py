from datetime import date
from pathlib import Path

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import (
    evaluate_spread, spread_scenario_value, spread_guidance_judgments,
)

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-08",
                   strategy="bull-call-spread")


def make(sym, strike, bid, ask, iv=0.35, opt="call", expiry="2026-10-16"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


def test_value_stays_within_zero_and_width_without_an_explicit_clamp():
    """T02（#219）更正：舊名字 `test_value_clamped_to_width_and_zero`
    暗示這裡有一道 clamp 在把值夾在 `[0, width]`——那道 clamp 已經被
    #217 決策 B 廢除（見上面 `test_spread_scenario_value_equals_raw_
    leg_sum_no_clamp`）。這條測試量的其實是**數學性質**：這份 fixture
    的兩腿共用同一個 IV，BS 定價在履約價上單調遞減，差值天然落在
    `[0, width]`，不需要任何顯式 clamp 就會成立——這正是移除 clamp 後
    T01 基準絕大多數格點逐位元不變的根本原因，不是巧合。（真的有 skew
    ── 兩腿 IV 不同 ── 時這個保證不成立，見
    `test_leg_valued_differently_can_transiently_exceed_width_before_
    expiry`，那是本票施工中實測抓到、Owner 已核准的真實例外。）"""
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 105.0, 5.0, 5.2)
    # 深度雙邊 ITM：兩腿差值天然貼近 width（不是被夾住，是算出來就在這裡）
    v_hi = spread_scenario_value(lng, sht, 500.0, date(2026, 8, 28), P)
    assert 0.0 <= v_hi <= 5.0
    # 深度雙邊 OTM：兩腿都趨近 0，差值天然趨近 0（同理不是被夾住）
    v_lo = spread_scenario_value(lng, sht, 1.0, date(2026, 8, 28), P)
    assert v_lo == 0.0


def test_expiry_payoff():
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 110.0, 3.0, 3.2)
    assert spread_scenario_value(lng, sht, 120.0, date(2026, 10, 16), P) == 10.0
    assert spread_scenario_value(lng, sht, 105.0, date(2026, 10, 16), P) == 5.0
    assert spread_scenario_value(lng, sht, 90.0, date(2026, 10, 16), P) == 0.0


def test_deep_itm_spread_value_rises_when_iv_drops():
    # spec §9.7 counter-intuitive lock: net vega sign change — deep ITM vertical
    # gains value as IV falls (value pinned toward width)
    lng, sht = make("L", 60.0, 41.0, 41.4), make("S", 70.0, 31.5, 31.9)
    hi_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=+0.2)
    lo_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=-0.2)
    assert lo_iv > hi_iv


def test_evaluate_spread_fields_and_l2_min():
    lng, sht = make("L", 110.0, 3.0, 3.25, iv=0.30), make("S", 130.0, 0.05, 0.15, iv=0.45)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=P)
    assert sv.width == 20.0
    assert abs(sv.net_mid - (3.125 - 0.10)) < 1e-12
    assert abs(sv.net_worst - (3.25 - 0.05)) < 1e-12
    # T12（附錄 A14.2）：成本衍生數字＝net_worst 口徑
    assert sv.breakeven == 110.0 + sv.net_worst
    assert sv.l2 == min(v for _, v in sv.scenario_values)
    assert sv.l2 <= sv.baseline_value + 1e-12
    assert not hasattr(sv, "l1")
    assert abs(sv.max_profit - (20.0 - sv.net_worst)) < 1e-12


def test_bear_put_breakeven():
    p = AnalysisParams(target_price=80.0, target_month="2026-08",
                       strategy="bear-put-spread")
    lng = make("L", 100.0, 5.2, 5.4, iv=0.36, opt="put")
    sht = make("S", 85.0, 1.1, 1.25, iv=0.35, opt="put")
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=p)
    assert sv.breakeven == 100.0 - sv.net_worst
    assert abs(sv.breakeven_vs_target - (sv.breakeven - 80.0) / 80.0) < 1e-9


def test_spread_judgments_trigger():
    # overpriced quotes: net_worst above every ceiling. T3 起基準值＝到期
    # payoff，目標價 115 落在兩腳之間 → payoff 5.0，而 net_worst 6.1 高於它。
    p = AnalysisParams(target_price=115.0, target_month="2026-08",
                       strategy="bull-call-spread")
    lng = make("L", 110.0, 6.2, 6.5, iv=0.30)
    sht = make("S", 120.0, 0.4, 0.5, iv=0.30)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=p)
    assert sv.baseline_value == 5.0 and sv.net_worst > sv.baseline_value
    msgs = spread_guidance_judgments(sv, p)
    assert any("最保守 IV 情境" in m for m in msgs)


# ---------- T02（#219）：逐腿直算取代 debit-only 包絡 ----------

def test_spread_scenario_value_equals_raw_leg_sum_no_clamp():
    """#217 決策 B：payoff 一律 `Σ 方向符號 × 口數 × 單腿價值`，
    `min(max(long-short,0), width)` 這個結構專屬封套公式已廢除。

    這條直接證明 `spread_scenario_value` 現在就是純粹的逐腿相減——
    不是「剛好通過既有測試」，是拿它跟手算的逐腿相減比對，逐位元相同。
    """
    from option_chaser.valuation import scenario_leg_value
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 105.0, 5.0, 5.2)
    S, at = 102.0, date(2026, 8, 28)
    expected = (scenario_leg_value(lng, S, at, P)
               - scenario_leg_value(sht, S, at, P))
    assert spread_scenario_value(lng, sht, S, at, P) == expected


def test_spread_scenario_value_is_not_floored_at_zero_when_raw_is_negative():
    """把「買、賣」對調（賣低履約價、買高履約價——不是本產品啟用的
    subtype，純粹用來證明原語本身不偷偷加 floor），到期時的 payoff
    在標的走高時是負的（賣方那隻腿虧錢）。舊的 `min(max(raw,0),width)`
    公式會把這個負值打成 0；新的逐腿直算原語不做這件事——這正是
    「不假設買賣方向組合」的直接證明。"""
    from option_chaser.valuation import scenario_leg_value
    low_strike, high_strike = make("A", 100.0, 8.0, 8.2), make("B", 105.0, 5.0, 5.2)
    S, at = 120.0, date(2026, 10, 16)   # 到期日，深度 ITM
    # 呼叫端角色對調：low_strike 傳進 short_leg 位置、high_strike 傳進
    # long_leg 位置——payoff = high_strike 內在價值 − low_strike 內在
    # 價值 = (120-105) − (120-100) = 15 − 20 = −5（負值）。
    result = spread_scenario_value(high_strike, low_strike, S, at, P)
    expected = (scenario_leg_value(high_strike, S, at, P)
               - scenario_leg_value(low_strike, S, at, P))
    assert result == expected == -5.0
    assert result < 0.0, "驗證真的沒有 floor(0)：舊公式在這裡會給 0"


def test_payoff_value_round_trip_matches_scenario_leg_value_for_single_leg():
    """新原語 `payoff_value` 是本票的核心產出：不假設腿數為 2、不假設
    買賣方向組合。單腿（sign=+1, qty=1）必須精確退化成既有的
    `scenario_leg_value`——round-trip 驗證，不手猜期望值。"""
    from option_chaser.valuation import WeightedLeg, payoff_value, scenario_leg_value
    c = make("A", 100.0, 8.0, 8.2)
    S, at = 110.0, date(2026, 8, 28)
    legs = (WeightedLeg(contract=c, sign=1.0, quantity=1),)
    assert payoff_value(legs, S, at, P) == scenario_leg_value(c, S, at, P)


def test_payoff_value_does_not_assume_two_legs():
    """三腿（模擬 Butterfly：買一口低履約價、賣兩口中間履約價、買一口高
    履約價）在到期時的 payoff，用純算術手算期望值驗證——不透過任何
    Spread 專屬公式，因為這個組合根本不是 Spread。"""
    from option_chaser.valuation import (WeightedLeg, payoff_value,
                                         intrinsic_value)
    low = make("L", 95.0, 6.0, 6.2)
    mid = make("M", 100.0, 3.0, 3.2)
    high = make("H", 105.0, 1.0, 1.2)
    legs = (
        WeightedLeg(contract=low, sign=1.0, quantity=1),
        WeightedLeg(contract=mid, sign=-1.0, quantity=2),
        WeightedLeg(contract=high, sign=1.0, quantity=1),
    )
    for S in (90.0, 97.0, 100.0, 103.0, 110.0):
        at = date(2026, 10, 16)   # 到期日，用內在價值手算
        expected = (intrinsic_value("call", S, 95.0)
                   - 2 * intrinsic_value("call", S, 100.0)
                   + intrinsic_value("call", S, 105.0))
        assert payoff_value(legs, S, at, P) == expected


def test_payoff_value_empty_legs_is_zero():
    """零腿（結構上不該發生，但原語本身不該對此特殊處理／拋錯）：純加總
    的空集合就是 0，不需要任何 if-empty 分支。"""
    from option_chaser.valuation import payoff_value
    assert payoff_value((), 100.0, date(2026, 8, 28), P) == 0.0


def test_leg_valued_differently_can_transiently_exceed_width_before_expiry():
    """記錄一個真實發現（施工過程中在 T01 基準上直接抓到，Owner 已核准
    拿掉 clamp 並更新基準——這條測試把發現本身鎖進回歸套件）：兩腿的
    vendor IV 不同時（真實市場 skew，未經 carry 校準的既有預設路徑），
    逐腿直算的到期前價值差**可能微幅超出 width**——這不是浮點雜訊，
    是「各腿各自反解自己的 IV、分開定價」這個既有模型在有 skew 時的
    真實性質。舊 clamp 會把這種情況無聲地夾回 width；新原語如實顯示。
    """
    long_leg = make("L", 105.0, 5.3, 5.5, iv=0.36)
    short_leg = make("S", 110.0, 3.0, 3.25, iv=0.30)
    S, at = 133.2, date(2026, 7, 15)
    raw = spread_scenario_value(long_leg, short_leg, S, at, P)
    assert raw > 5.0, "這正是本票拿掉 clamp 後才如實顯示出來的張力"


# ---------- T03（#223）：包絡量由 payoff 導出 ----------

def _leg(option_type, strike, sign, qty=1):
    from option_chaser.valuation import WeightedLeg
    return WeightedLeg(contract=make("X", strike, 1.0, 1.0, opt=option_type),
                       sign=sign, quantity=qty)


def test_payoff_envelope_long_call_is_unbounded_above():
    """裸買一口 Call 的 payoff 沒有上界——回傳 None，不外插、不改標成
    無限大（#223 修訂後的範圍界定核心案例）。"""
    from option_chaser.valuation import payoff_envelope
    legs = (_leg("call", 100.0, 1.0),)
    min_payoff, max_payoff = payoff_envelope(legs)
    assert min_payoff == 0.0
    assert max_payoff is None


def test_payoff_envelope_long_put_bounded_at_zero_price():
    """裸買一口 Put 的最大 payoff 在 S=0 達到，值＝履約價——這是價格
    不可能為負這個真實邊界給出的，不是任意搜尋窗。"""
    from option_chaser.valuation import payoff_envelope
    legs = (_leg("put", 100.0, 1.0),)
    min_payoff, max_payoff = payoff_envelope(legs)
    assert min_payoff == 0.0
    assert max_payoff == 100.0


def test_payoff_envelope_vertical_spread_bounded_both_sides():
    """兩腿 Vertical（買低賣高履約價的 call）payoff 天然有界於
    [0, width]——不需要任何 clamp，折點＋漸近值分析自然給出。"""
    from option_chaser.valuation import payoff_envelope
    legs = (_leg("call", 100.0, 1.0), _leg("call", 105.0, -1.0))
    min_payoff, max_payoff = payoff_envelope(legs)
    assert min_payoff == 0.0
    assert max_payoff == 5.0


def test_payoff_envelope_does_not_assume_two_legs_or_monotonicity():
    """三腿非單調結構（模擬 Butterfly）：payoff 在 body 履約價達到峰值，
    兩翼歸零——折點掃描不需要知道這是不是單調函式。"""
    from option_chaser.valuation import payoff_envelope
    legs = (_leg("call", 95.0, 1.0), _leg("call", 100.0, -1.0, qty=2),
           _leg("call", 105.0, 1.0))
    min_payoff, max_payoff = payoff_envelope(legs)
    assert min_payoff == 0.0
    assert max_payoff == 5.0   # 峰值在 S=100：(100-95) - 0 + 0 = 5


def test_payoff_breakeven_points_round_trip_single_leg():
    """Round-trip：任選一個履約價與成本，反推損益兩平價，代回 payoff
    驗證真的等於成本——不手猜期望值。"""
    from option_chaser.valuation import payoff_breakeven_points, _payoff_at_expiry
    legs = (_leg("call", 100.0, 1.0),)
    cost = 5.4
    roots = payoff_breakeven_points(legs, cost)
    assert len(roots) == 1
    assert abs(_payoff_at_expiry(legs, roots[0]) - cost) < 1e-9


def test_payoff_breakeven_points_round_trip_two_leg_spread():
    from option_chaser.valuation import payoff_breakeven_points, _payoff_at_expiry
    legs = (_leg("put", 110.0, 1.0), _leg("put", 105.0, -1.0))
    cost = 2.5
    roots = payoff_breakeven_points(legs, cost)
    assert len(roots) == 1
    assert abs(_payoff_at_expiry(legs, roots[0]) - cost) < 1e-9


def test_payoff_breakeven_points_two_roots_for_non_monotonic_structure():
    """非單調結構（模擬 Butterfly）在成本落在峰值以下時有兩個損益兩平
    點——round-trip 驗證兩個根代回 payoff 都等於成本。"""
    from option_chaser.valuation import payoff_breakeven_points, _payoff_at_expiry
    legs = (_leg("call", 95.0, 1.0), _leg("call", 100.0, -1.0, qty=2),
           _leg("call", 105.0, 1.0))
    cost = 2.0
    roots = payoff_breakeven_points(legs, cost)
    assert len(roots) == 2
    for r in roots:
        assert abs(_payoff_at_expiry(legs, r) - cost) < 1e-9
    assert roots[0] < roots[1]


def test_derived_envelope_matches_existing_formulas_exactly_on_real_fixture():
    """對真實 fixture 的每一組候選（含所有真實 bid/ask/strike 浮點值），
    導出的 max_profit／breakeven 逐位元等於既有的結構專屬封套公式——
    這是 bitwise parity 的直接證明，不是靠全套測試綠燈間接推論。"""
    import sys
    sys.path.insert(0, "tests")
    from test_selection_regression import SCENARIOS, SNAP
    from option_chaser import service
    from option_chaser.valuation import (WeightedLeg, payoff_envelope,
                                         payoff_breakeven_points)

    checked = 0
    for strat in ("bull-call-spread", "bear-put-spread", "long-call", "long-put"):
        p = SCENARIOS[strat]
        req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                      strategies=(strat,))
        result = service.run_offline(req, SNAP)
        for r in result.results:
            for sv in (r.ranked_spreads or ()):
                legs = (WeightedLeg(contract=sv.long_leg, sign=1.0, quantity=1),
                       WeightedLeg(contract=sv.short_leg, sign=-1.0, quantity=1))
                _, max_payoff = payoff_envelope(legs)
                width = abs(sv.short_leg.strike - sv.long_leg.strike)
                assert max_payoff - sv.net_worst == width - sv.net_worst
                roots = payoff_breakeven_points(legs, sv.net_worst)
                assert len(roots) == 1
                assert roots[0] == sv.breakeven
                checked += 1
            for band_list in (r.ranked_bands or {}).values():
                for cv in band_list:
                    legs = (WeightedLeg(contract=cv.contract, sign=1.0, quantity=1),)
                    min_payoff, max_payoff = payoff_envelope(legs)
                    if cv.contract.option_type == "call":
                        assert max_payoff is None
                    else:
                        assert max_payoff - cv.contract.ask == (
                            cv.contract.strike - cv.contract.ask)
                    roots = payoff_breakeven_points(legs, cv.contract.ask)
                    assert len(roots) == 1
                    assert roots[0] == cv.breakeven
                    checked += 1
    assert checked >= 19, f"樣本數太少不足以當回歸證據：{checked}"


def test_no_structure_specific_envelope_formula_remains_in_store_or_valuation():
    """AC：『程式碼中不再有結構專屬的封套公式』——結構性證明，不靠測試
    綠燈間接推論。舊公式（`strategy=="long-call"` 判斷、`strike±ask`／
    `width-net_worst` 硬寫算術）不得出現在任何生產程式碼的可執行行裡
    （註解裡提及舊公式名字沒關係，那是解釋歷史脈絡）。"""
    for mod in ("option_chaser/store.py", "option_chaser/valuation.py"):
        src = Path(mod).read_text(encoding="utf-8")
        code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
        code = "\n".join(code_lines)
        assert 'strategy == "long-call"' not in code, (
            f"{mod} 不該再用策略名字判斷 max_profit 是否為 None")
        assert "width - net_worst" not in code, (
            f"{mod} 不該再有 width-net_worst 這條硬寫封套公式")
