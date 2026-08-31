"""v4 spec §2.1/§2.2: seven-scenario resilience vector."""
from datetime import date

import pytest

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser import scenarios
from option_chaser.scenarios import (ScenarioVector, scenario_vector,
                                     completion_curve, completion_scan)
from option_chaser.valuation import (evaluate_butterfly, evaluate_contract,
                                     evaluate_spread, scenario_leg_value,
                                     spread_scenario_value)


def _p(**kw):
    base = dict(strategy="long-call", target_price=105.0,
                target_month="2028-01", min_return=0.0)
    base.update(kw)
    return AnalysisParams(**base)


def _call(strike, expiry, bid, ask, iv, volume=10, oi=100):
    return OptionContract(
        contract_symbol=f"XYZ{expiry}C{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=oi, implied_volatility=iv, option_type="call")


def _put(strike, expiry, bid, ask, iv, volume=10, oi=100):
    return OptionContract(
        contract_symbol=f"XYZ{expiry}P{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=oi, implied_volatility=iv, option_type="put")


TODAY = date(2026, 7, 1)
SPOT = 84.52


def test_single_leg_seven_entries_match_engine():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert [code for code, _ in sv.entries] == [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    tgt = p.anchor
    mid = v.mid
    # S1: S=spot at anchor, base IV
    exp_s1 = (scenario_leg_value(c, SPOT, tgt, p) - mid) / mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    # S2/S3: completion 50%/75%
    s50 = SPOT + 0.5 * (p.target_price - SPOT)
    s75 = SPOT + 0.75 * (p.target_price - SPOT)
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(c, s50, tgt, p) - mid) / mid)
    assert dict(sv.entries)["S3"] == pytest.approx(
        (scenario_leg_value(c, s75, tgt, p) - mid) / mid)
    # S6: envelope min over ALL iv_shifts (incl. base)
    exp_s6 = min(
        scenario_leg_value(c, p.target_price, tgt, p, sh) for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx((exp_s6 - mid) / mid)
    # S7: Natural cost (=Ask), base value at target
    base_val = scenario_leg_value(c, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base_val - c.ask) / c.ask)
    # worst = min, code = first minimum in S1..S7 order
    rets = [r for _, r in sv.entries]
    assert sv.worst_return == pytest.approx(min(rets))
    assert sv.worst_code == sv.entries[rets.index(min(rets))][0]


def test_delay_scenarios_arrive_before_expiry():
    """S4: expiry >= target+30 -> valued at arrive date with S=target."""
    c = _call(93.0, "2028-12-15", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = p.anchor + timedelta(days=30)
    exp = (scenario_leg_value(c, p.target_price, arrive, p) - v.mid) / v.mid
    assert dict(sv.entries)["S4"] == pytest.approx(exp)


def test_delay_scenario_expiry_before_arrive_interpolates():
    """v4 spec §2.2: expiry < target+90 -> payoff at interpolated price at expiry."""
    expiry = date(2028, 1, 21)          # target 2028-01-01 + 90 > expiry
    c = _call(93.0, expiry.isoformat(), 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = p.anchor + timedelta(days=90)
    frac = (expiry - TODAY).days / (arrive - TODAY).days
    s_at_expiry = SPOT + (p.target_price - SPOT) * frac
    exp = (scenario_leg_value(c, s_at_expiry, expiry, p) - v.mid) / v.mid
    assert dict(sv.entries)["S5"] == pytest.approx(exp)


def test_spread_vector_uses_spread_engine_and_natural_cost():
    lng = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    p = _p(strategy="bull-call-spread")
    sv_val = evaluate_spread(lng, sht, SPOT, TODAY, p)
    sv = scenario_vector(sv_val, SPOT, TODAY, p)
    tgt = p.anchor
    exp_s1 = (spread_scenario_value(lng, sht, SPOT, tgt, p) - sv_val.net_mid) / sv_val.net_mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    natural = lng.ask - sht.bid
    base = spread_scenario_value(lng, sht, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base - natural) / natural)
    # S6 envelope: min over shifts of spread value (net vega can flip sign)
    exp_s6 = min(spread_scenario_value(lng, sht, p.target_price, tgt, p, sh)
                 for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx(
        (exp_s6 - sv_val.net_mid) / sv_val.net_mid)


def test_bearish_completion_mirrors():
    """target < spot: S2 is halfway DOWN."""
    put = OptionContract(
        contract_symbol="XYZP70", strike=80.0, expiry="2028-01-21",
        bid=3.0, ask=3.4, last=3.2, volume=5, open_interest=50,
        implied_volatility=0.25, option_type="put")
    p = _p(strategy="long-put", target_price=70.0)
    v = evaluate_contract(put, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    s50 = SPOT + 0.5 * (70.0 - SPOT)
    tgt = p.anchor
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(put, s50, tgt, p) - v.mid) / v.mid)


def test_completion_scan_suffix_condition_long_call():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, be = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and 0.0 < k <= 1.0
    tgt = p.anchor
    # suffix property: every grid j in [k, 1] >= cost; k-0.001 violates
    for j in [k, (k + 1.0) / 2, 1.0]:
        s = max(SPOT + j * (p.target_price - SPOT), min(0.01 * SPOT, p.target_price))
        assert scenario_leg_value(c, s, tgt, p) >= v.mid - 1e-12
    s_prev = SPOT + (k - 0.001) * (p.target_price - SPOT)
    assert scenario_leg_value(c, s_prev, tgt, p) < v.mid
    assert be == pytest.approx(SPOT + k * (p.target_price - SPOT))


def test_completion_scan_four_strategies():
    """spec §7.2: one completion_scan case per strategy; suffix property must
    hold for long-call, long-put, bull-call-spread, and bear-put-spread."""
    tgt = _p().anchor          # 2028-01 的日曆錨點

    def check(val, spot, target_price, value_fn):
        k, be = completion_scan(val, spot, TODAY, _p(target_price=target_price))
        assert k is not None, "fixture must have a completion threshold"
        mid = val.net_mid if hasattr(val, "net_mid") else val.mid
        for j in [k, (k + 1.0) / 2, 1.0]:
            s = scenarios._grid_price(spot, target_price, j)
            assert value_fn(s) >= mid - 1e-12
        if k > -0.2:
            s_prev = scenarios._grid_price(spot, target_price, k - 0.001)
            assert value_fn(s_prev) < mid
        assert be == pytest.approx(scenarios._grid_price(spot, target_price, k))

    # long-call
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p_call = _p(strategy="long-call", target_price=105.0)
    v_call = evaluate_contract(c, SPOT, TODAY, p_call)
    check(v_call, SPOT, 105.0, lambda s: scenario_leg_value(c, s, tgt, p_call))

    # long-put
    put = _put(80.0, "2028-01-21", 3.0, 3.4, 0.25)
    p_put = _p(strategy="long-put", target_price=70.0)
    v_put = evaluate_contract(put, SPOT, TODAY, p_put)
    check(v_put, SPOT, 70.0, lambda s: scenario_leg_value(put, s, tgt, p_put))

    # bull-call-spread
    lng_c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht_c = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    p_bcs = _p(strategy="bull-call-spread", target_price=105.0)
    v_bcs = evaluate_spread(lng_c, sht_c, SPOT, TODAY, p_bcs)
    check(v_bcs, SPOT, 105.0,
          lambda s: spread_scenario_value(lng_c, sht_c, s, tgt, p_bcs))

    # bear-put-spread
    lng_p = _put(85.0, "2028-01-21", 6.0, 6.4, 0.25)
    sht_p = _put(75.0, "2028-01-21", 2.0, 2.4, 0.28)
    p_bps = _p(strategy="bear-put-spread", target_price=70.0)
    v_bps = evaluate_spread(lng_p, sht_p, SPOT, TODAY, p_bps)
    check(v_bps, SPOT, 70.0,
          lambda s: spread_scenario_value(lng_p, sht_p, s, tgt, p_bps))


def test_completion_scan_hopeless_returns_none():
    """Cost above full-completion value -> (None, None)."""
    c = _call(120.0, "2028-01-21", 8.0, 9.0, 0.20)   # deep OTM, huge premium
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    assert completion_scan(v, SPOT, TODAY, p) == (None, None)


def test_completion_scan_already_breakeven_negative_k():
    """Deep ITM low-premium: threshold <= 0 (already at breakeven at k=0)."""
    c = _call(60.0, "2028-01-21", 24.0, 24.6, 0.18)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, _ = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and k <= 0.0


def test_completion_scan_floor_extreme_bullish():
    """target >= 6*spot: k=-0.2 corner triggers floor min(0.01*spot, target)."""
    c = _call(3.0, "2028-01-21", 0.4, 0.6, 0.8)
    p = _p(target_price=15.0)
    spot = 2.0
    v = evaluate_contract(c, spot, TODAY, p)
    k, be = completion_scan(v, spot, TODAY, p)   # must not raise (S<=0 -> BS log)
    assert be is None or be > 0.0


def test_completion_scan_deep_bearish_k1_exact_target():
    """target < 0.01*spot: floor must NOT distort k=1 (S_1 == target exactly).

    Reviewer finding M1: the previous version recomputed the _grid_price
    formula inline and could never fail. Assert against the real
    scenarios._grid_price function directly instead.
    """
    assert scenarios._grid_price(100.0, 0.5, 1.0) == pytest.approx(0.5)
    # floor engages: raw = 1.2*2 - 0.2*15 = -0.6 -> floored to min(0.01*2, 15) = 0.02
    assert scenarios._grid_price(2.0, 15.0, -0.2) == pytest.approx(
        min(0.01 * 2.0, 15.0))


def test_completion_curve_identities():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    curve = completion_curve(v, SPOT, TODAY, p)
    assert [k for k, _ in curve] == [0.0, 0.25, 0.5, 0.75, 1.0]
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert dict(curve)[0.0] == pytest.approx(dict(sv.entries)["S1"])   # k=0 == S1
    tgt = p.anchor
    base = (scenario_leg_value(c, p.target_price, tgt, p) - v.mid) / v.mid
    assert dict(curve)[1.0] == pytest.approx(base)                     # k=1 == baseline


def test_completion_scan_suffix_semantics_synthetic(monkeypatch):
    """Spec §7.2 附錄A: same-expiry debit verticals provably cannot produce an
    up-down-up value(S) shape (the two legs' deltas cross exactly once, so the
    net value has at most one extremum). The false-threshold guard is
    therefore locked by injecting a synthetic non-monotone value function at
    the _value_fn seam: an above-cost island at k in [0.10, 0.20], below-cost
    gap, then an above-cost suffix from k = 0.50. First-touch semantics would
    return 0.10; suffix semantics must return 0.50."""
    import option_chaser.scenarios as sc
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    cost = v.mid

    def fake_value_fn(val):
        def fn(S, at, params, shift=0.0):
            k = (S - SPOT) / (p.target_price - SPOT)
            if 0.0995 <= k <= 0.2005 or k >= 0.4995:
                return cost + 1.0
            return cost - 1.0
        return fn, cost, v.contract.ask, v.contract.expiry

    monkeypatch.setattr(sc, "_value_fn", fake_value_fn)
    k_star, be = sc.completion_scan(v, SPOT, TODAY, p)
    assert k_star == pytest.approx(0.5)


# ---------- T17（#234，Initial V2）：持平劇本（target_price == spot）
# 的價格網格不塌陷 ----------
#
# spec #217 §F／§P.5 明文點名的既有地雷：「價格網格產生器在該情況下
# 會把五個 k 塌成同一個價格」——`_grid_price()`／`scenario_vector()`
# 的 S2/S3/S4/S5／`completion_curve()` 全部依賴「從 spot 走到 target」
# 這條路徑取樣，target==spot 時路徑長度為零。


def test_effective_target_only_changes_the_degenerate_case():
    """target != spot 原樣回傳——既有看漲／看跌劇本逐位元不變（T01
    基準，AC 明文要求）；target == spot 才換成合成終點，且是非零、
    往上偏移（沿用 `matrix.price_axis()` 既有的 15% 比例）。"""
    assert scenarios._effective_target(100.0, 105.0) == 105.0
    assert scenarios._effective_target(100.0, 95.0) == 95.0
    assert scenarios._effective_target(SPOT, SPOT) == pytest.approx(SPOT * 1.15)


def test_grid_price_does_not_collapse_when_target_equals_spot():
    """修正前：`_grid_price(spot, spot, k)` 對任何 k 都回傳 spot 本身
    ——這裡直接證明五個既有 k 取樣點（0, 0.25, 0.5, 0.75, 1.0）不再
    塌成同一個價格，且與 `_effective_target()` 的合成終點吻合。"""
    prices = [scenarios._grid_price(SPOT, SPOT, k)
             for k in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert len(set(prices)) == 5, "五個取樣點仍塌成少於 5 個相異價格"
    assert prices[0] == pytest.approx(SPOT)             # k=0 恆為 spot 本身
    assert prices[-1] == pytest.approx(SPOT * 1.15)      # k=1 恆為合成終點
    assert prices == sorted(prices)                      # 單調遞增，路徑合理


def test_grid_price_unaffected_when_target_differs_from_spot():
    """既有非持平案例逐位元不變——修正只在 `target == spot` 時介入。"""
    for k in (-0.2, 0.0, 0.37, 1.0):
        assert scenarios._grid_price(SPOT, 105.0, k) == pytest.approx(
            max(SPOT + k * (105.0 - SPOT), min(0.01 * SPOT, 105.0)))


def _flat_butterfly(spot=SPOT):
    """持平劇本（target_price == spot）下的 call-fly 候選——三腿對稱
    圍繞 spot，body（中腿）落在 spot 附近，符合「body 錨在現價」的
    Butterfly 招牌情境（spec #217 §Problem Statement）。

    翼寬刻意選得夠寬（±20，K1=65／K3=105）——`_effective_target()` 的
    合成終點（spot×1.15≈97.2）必須落在 [K1,K3] 這個「還有時間價值」
    的區間內：測試曾用 ±5 窄翼（K3=90）撞到一個不相干的真相——S_half／
    S_most 剛好都落在 K3 之外，那裡到期時 payoff 恆為 0（帳篷形狀本身
    如此，不是網格塌陷的症狀）；`p.anchor` 對這份 fixture 的
    `target_month="2028-01"` 恰好等於腿的到期日（`2028-01-21`），
    `at >= expiry` 因此走到期內在價值分支而非平滑的 BS 時間價值，這個
    「剛好卡在到期日評價」的邊界情況與網格塌陷是兩件不同的事，加寬翼
    寬讓合成終點落回有意義的區間即可避開，不需要另外處理到期日邊界。"""
    low = _call(round(spot - 20, 0), "2028-01-21", 26.0, 26.4, 0.20)
    mid = _call(round(spot, 0), "2028-01-21", 6.4, 6.6, 0.20)
    high = _call(round(spot + 20, 0), "2028-01-21", 0.4, 0.6, 0.20)
    p = _p(strategy="call-fly", target_price=spot)
    v = evaluate_butterfly(low, mid, high, spot, TODAY, p)
    return v, p


def test_scenario_vector_does_not_collapse_for_a_flat_butterfly_scenario():
    """S2／S3（半程／大半程）不再塌成跟 S1 一樣的數字；S1／S6／S7 維持
    讀取真正的 `target_price`（== spot，答案本來就該是 spot 本身的
    評價，不是退化）。"""
    v, p = _flat_butterfly()
    sv = scenario_vector(v, SPOT, TODAY, p)
    by_code = dict(sv.entries)
    assert len({by_code["S1"], by_code["S2"], by_code["S3"]}) == 3, (
        "S1/S2/S3 仍然塌成同一個數字")
    # S1 是「不漲」＝就在 spot 評價，這本來就該等於 spot（不是退化）。
    tgt = p.anchor
    fn, mid, natural, expiry_iso = scenarios._value_fn(v)
    exp_s1 = (fn(SPOT, tgt, p) - mid) / mid
    assert by_code["S1"] == pytest.approx(exp_s1)
    # S7 讀真正的 target_price（此情境下等於 spot）——同樣不是退化，
    # 是「劇本成立時（就停在原地）該有的報酬」這個問題的正確答案。
    exp_s7 = (fn(p.target_price, tgt, p) - natural) / natural
    assert by_code["S7"] == pytest.approx(exp_s7)


def test_completion_curve_does_not_collapse_for_a_flat_butterfly_scenario():
    v, p = _flat_butterfly()
    curve = completion_curve(v, SPOT, TODAY, p)
    assert [k for k, _ in curve] == [0.0, 0.25, 0.5, 0.75, 1.0]
    returns = [r for _, r in curve]
    assert len(set(returns)) > 1, "完成度曲線的五個點仍全部退化成同一個值"


def test_completion_scan_flat_butterfly_still_short_circuits_to_profit_region():
    """T15（#230）既有短路：Butterfly 的保本掃描恆回 (None, None)，
    「正常」的意思是誠實回這個既有 sentinel（profit_region 才是替代
    答案），不受本票影響——這條測試釘住這個既有行為在持平情境下
    依然成立，不是本票不小心動到它。"""
    v, p = _flat_butterfly()
    assert completion_scan(v, SPOT, TODAY, p) == (None, None)


def test_completion_scan_flat_forced_single_leg_still_respects_suffix_property():
    """單腿／Spread 候選在 CLI `--force` 繞過方向閘門時，仍可能以
    `target_price == spot` 呼叫到這條路徑（見 `completion_scan()`
    docstring）——`_grid_price()` 的修正必須讓這裡的 suffix 條件
    （k 之後每一格都 >= mid cost）繼續在非退化的網格上成立。"""
    c = _call(80.0, "2028-01-21", 6.0, 6.4, 0.20)   # 價內，容易保本
    p = _p(strategy="long-call", target_price=SPOT, force=True)
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, be = completion_scan(v, SPOT, TODAY, p)
    assert k is not None
    tgt = p.anchor
    for j in [k, (k + 1.0) / 2, 1.0]:
        s = scenarios._grid_price(SPOT, p.target_price, j)
        assert scenario_leg_value(c, s, tgt, p) >= v.mid - 1e-12
    if k > -0.2:
        s_prev = scenarios._grid_price(SPOT, p.target_price, k - 0.001)
        assert scenario_leg_value(c, s_prev, tgt, p) < v.mid
    assert be == pytest.approx(scenarios._grid_price(SPOT, p.target_price, k))
    # 非退化的直接證明：這張深價內合約在 k=1.0（合成終點）與 k=0.0
    # （spot 本身）給出不同的估值，證明網格真的走過不只一個價格。
    s_k1 = scenarios._grid_price(SPOT, p.target_price, 1.0)
    s_k0 = scenarios._grid_price(SPOT, p.target_price, 0.0)
    assert s_k1 != pytest.approx(s_k0)
    assert scenario_leg_value(c, s_k1, tgt, p) != pytest.approx(
        scenario_leg_value(c, s_k0, tgt, p))
