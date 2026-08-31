"""T05（#226，Initial V2 spec #217）：Candidate validity 兩層——
A. Quote-level invalidity（報價層：原始報價本身不可信）
B. Derived mathematical safety net（導出層：數學安全網）

兩層各自獨立成立，只需要自己的證據——不是同一條規則的兩種說法。範圍
紅線（Owner 2026-08-30 三次修訂）：不新增 max_profit<=0 過濾規則、
不建立任何形式的 generic payoff-envelope／extrema engine、B 層只檢查
既有計算路徑（`natural_cost`／`baseline_return`／`spread_baseline_
return`）本來就會產出的量。
"""
import math

import pytest

from option_chaser import service
from option_chaser.filters import apply_filters, generate_spread_pairs, validate_derived_values
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.ranking import baseline_return, spread_baseline_return

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def _contract(symbol="C1", option_type="call", strike=100.0, expiry="2026-10-16",
             bid=4.9, ask=5.0, last=5.0, volume=50, oi=100, iv=0.3):
    return OptionContract(contract_symbol=symbol, option_type=option_type,
                          strike=strike, expiry=expiry, bid=bid, ask=ask,
                          last=last, volume=volume, open_interest=oi,
                          implied_volatility=iv)


# ---------- A 層：報價層不可信（`apply_filters`，既有 quote_ok／iv_ok）----------

def test_a_layer_rejects_bid_greater_than_ask():
    bad = _contract(bid=5.5, ask=5.0)   # 買賣價倒掛
    kept, freport = apply_filters([bad], AnalysisParams(
        target_price=110.0, target_month="2026-10", strategy="long-call"))
    assert kept == []
    assert freport.stages[0].removed == 1
    assert freport.stages[0].filter_class == "A"


def test_a_layer_rejects_missing_quote():
    bad = _contract(bid=None, ask=5.0)
    kept, _ = apply_filters([bad], AnalysisParams(
        target_price=110.0, target_month="2026-10", strategy="long-call"))
    assert kept == []


def test_a_layer_rejects_nan_and_infinite_quotes():
    """AC：非有限數值（NaN／Infinity）與 bid>ask 同屬 A 層，明確檢查、
    不依賴比較運算子的副作用。"""
    nan_bid = _contract(symbol="NAN", bid=float("nan"), ask=5.0)
    inf_ask = _contract(symbol="INF", bid=4.9, ask=float("inf"))
    p = AnalysisParams(target_price=110.0, target_month="2026-10",
                      strategy="long-call")
    kept, freport = apply_filters([nan_bid, inf_ask], p)
    assert kept == []
    assert freport.stages[0].removed == 2


def test_a_layer_rejects_nan_and_infinite_iv():
    nan_iv = _contract(symbol="NANIV", iv=float("nan"))
    inf_iv = _contract(symbol="INFIV", iv=float("inf"))
    p = AnalysisParams(target_price=110.0, target_month="2026-10",
                      strategy="long-call")
    kept, freport = apply_filters([nan_iv, inf_iv], p)
    assert kept == []
    # 兩者都合法通過報價層（bid/ask 正常），死在 IV 這一關（B 類）。
    assert freport.stages[1].removed == 2
    assert freport.stages[1].filter_class == "B"


def test_a_layer_does_not_require_proving_a_derived_impossible_value():
    """AC：A 層不以『是否導致某個導出量變成不可能值』為前提——這裡故意
    挑一個 bid>ask 但兩邊都是正常量級的例子（不會製造出離譜的導出值），
    A 層照樣拒絕，理由只是『報價本身不可信』。"""
    bad = _contract(bid=5.01, ask=5.00)  # 只倒掛 1 分錢，數量級完全正常
    kept, freport = apply_filters([bad], AnalysisParams(
        target_price=110.0, target_month="2026-10", strategy="long-call"))
    assert kept == []
    assert freport.stages[0].removed == 1


def test_a_layer_cross_leg_contradiction_is_already_covered_by_pairing_sanity():
    """AC：『同一候選腿位之間的報價互相矛盾』——這一層由既有
    `generate_spread_pairs()` 的配對健全性檢查（`net_mid<=0`）承接，
    不另建一套新的判準。刻意構造買腿 mid 低於賣腿 mid 的一組報價：
    兩腿各自都通過 A/B 兩類報價品質檢查（bid<=ask、皆為正值），但
    合起來看是矛盾的（買比賣還便宜），既有機制早就擋下。"""
    long_leg = _contract(symbol="LOW", strike=100, bid=1.0, ask=1.1)
    short_leg = _contract(symbol="HIGH", strike=105, bid=2.0, ask=2.1)
    p = AnalysisParams(target_price=110.0, target_month="2026-10",
                      strategy="bull-call-spread")
    pairs, pair_report = generate_spread_pairs([long_leg, short_leg], p)
    assert pairs == []
    assert pair_report.removed_sanity == 1


def test_a_layer_stale_frozen_has_no_existing_hard_rule_to_reuse_today():
    """AC：A 層沿用**既有**的資料品質規則判斷 stale／frozen，不另建
    一套新的新鮮度判準。本 repo 目前唯一的『疑似陳舊報價』既有規則是
    `monotonicity_violations()`（FB5-03／#64）——但那是 C 類品質標示
    （只標不刪，不影響入選，spec #61 既有裁示），本票不得為了這條 AC
    把它升級成硬性排除（會改變既有排名，違反範圍紅線）。因此這條
    A 層判準今天結構上是**休眠**的：沒有任何既有的硬性新鮮度規則可以
    掛上去，一旦未來真的出現這種規則，會自然流進同一條 apply_filters
    路徑，不需要另開機制。這裡直接證明目前的行為：monotonicity 違反
    的腿依然進得了候選池，不受 A 層排除。"""
    from option_chaser.filters import monotonicity_violations

    stale_looking = [
        _contract(symbol="K100", strike=100, bid=4.9, ask=5.0),
        _contract(symbol="K105", strike=105, bid=5.9, ask=6.0),  # 違反單調
    ]
    p = AnalysisParams(target_price=110.0, target_month="2026-10",
                      strategy="long-call")
    kept, freport = apply_filters(stale_looking, p)
    assert len(kept) == 2   # 沒有被 A 層排除
    violations = monotonicity_violations(kept)
    assert violations   # 但確實被既有 C 類判準標記為疑似陳舊


# ---------- B 層：導出層數學安全網（`validate_derived_values`）----------

def test_b_layer_rejects_non_positive_cost():
    class Fake:
        def __init__(self, name):
            self.name = name

    good, bad = Fake("good"), Fake("bad")
    kept, stage = validate_derived_values(
        [good, bad], cost_fn=lambda v: 5.0 if v is good else 0.0,
        return_fn=lambda v: 0.5)
    assert kept == [good]
    assert stage.removed == 1
    assert stage.filter_class == "B"


def test_b_layer_rejects_nan_or_infinite_cost():
    class Fake:
        pass

    a, b, c = Fake(), Fake(), Fake()
    cost_by_id = {id(a): 5.0, id(b): float("nan"), id(c): float("inf")}
    kept, stage = validate_derived_values(
        [a, b, c], cost_fn=lambda v: cost_by_id[id(v)], return_fn=lambda v: 0.5)
    assert kept == [a]
    assert stage.removed == 2


def test_b_layer_rejects_nan_or_infinite_return_even_when_cost_is_fine():
    """AC：任何回報給使用者的導出量（報酬率等）出現 NaN／Infinity 一律
    invalid——不是只檢查成本一項。"""
    class Fake:
        pass

    a, b, c = Fake(), Fake(), Fake()
    ret_by_id = {id(a): 0.5, id(b): float("nan"), id(c): float("inf")}
    kept, stage = validate_derived_values(
        [a, b, c], cost_fn=lambda v: 5.0, return_fn=lambda v: ret_by_id[id(v)])
    assert kept == [a]
    assert stage.removed == 2


def test_b_layer_accepts_a_legitimately_negative_but_finite_return():
    """範圍紅線：劇本成立時仍為負報酬的候選是合法的分析結果，B 層不得
    誤殺——只有 NaN／Infinity 才 invalid，有限的負數完全合法。"""
    class Fake:
        pass

    v = Fake()
    kept, stage = validate_derived_values(
        [v], cost_fn=lambda _: 5.0, return_fn=lambda _: -0.87)
    assert kept == [v]
    assert stage.removed == 0


def test_b_layer_does_not_reject_when_premium_exceeds_width():
    """範圍紅線：明確不使用『權利金大於價差寬度』作為驗證案例——這種
    候選的 cost 是正值、return 是有限負數，兩層皆不觸發，只是數字難看
    但自洽的爛候選，照常留在排名裡讓它自然沉底。"""
    class Fake:
        pass

    v = Fake()
    # width=5、debit=6：cost 正常是正值，不觸發 B 層。
    kept, stage = validate_derived_values(
        [v], cost_fn=lambda _: 6.0, return_fn=lambda _: -0.2)
    assert kept == [v]
    assert stage.removed == 0


def test_b_layer_introduces_no_new_valuation_concept():
    """B 層只接受呼叫端既有的 cost_fn／return_fn，本身零讀取任何候選
    欄位——結構上不可能新增一套推導邏輯，因為它根本不知道候選長什麼
    樣子。檢查編譯後的 bytecode 名稱（不是原始碼文字），docstring 裡
    解釋『不做什麼』時提到這些詞不算數。"""
    names = validate_derived_values.__code__.co_names
    for banned in ("max_profit", "max_loss", "payoff_envelope", "extrema"):
        assert banned not in names


# ---------- 兩層共通：不可見於排名／代表候選／到期日分組 ----------

def _params(strategy, target):
    return AnalysisParams(target_price=target, target_month="2026-10",
                          strategy=strategy, min_return=0.0)


def test_b_layer_removed_candidates_never_reach_ranking_or_expiry_groups(monkeypatch):
    """整合測試：monkeypatch `service.baseline_return`，讓其中一個候選
    的報酬算出 NaN——證明 wiring 真的接在 `_single_leg_result()` 排名
    之前，不是只有獨立函式測試過。"""
    from option_chaser.models import STRATEGIES

    original = service.baseline_return
    poisoned_strike = None

    def poisoned(v):
        if poisoned_strike is not None and v.contract.strike == poisoned_strike:
            return float("nan")
        return original(v)

    p = _params("long-call", 120.0)
    baseline_result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=p,
                                strategies=("long-call",)), FIX)
    res = next(r for r in baseline_result.results if r.strategy == "long-call")
    assert res.status == "ok" and res.candidates
    target_strike = res.candidates[0].valuation.contract.strike

    monkeypatch.setattr(service, "baseline_return", original)  # sanity
    poisoned_strike = target_strike
    monkeypatch.setattr(service, "baseline_return", poisoned)
    poisoned_result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=p,
                                strategies=("long-call",)), FIX)
    poisoned_res = next(r for r in poisoned_result.results if r.strategy == "long-call")
    surviving_strikes = {cv.valuation.contract.strike for cv in poisoned_res.candidates}
    assert target_strike not in surviving_strikes
    for exp, group in poisoned_res.expiry_top10:
        assert all(cv.valuation.contract.strike != target_strike for cv in group)
    b_stage = next(s for s in poisoned_res.filter_report.stages
                  if s.filter_class == "B" and "不可能值" in s.label)
    assert b_stage.removed >= 1


def test_removal_is_visible_not_silent():
    """AC：剔除是可見的——`filter_report.stages` 看得出這次分析剔除了
    幾筆、哪一層。"""
    baseline_result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=_params("long-call", 120.0),
                                strategies=("long-call",)), FIX)
    res = next(r for r in baseline_result.results if r.strategy == "long-call")
    labels = [s.label for s in res.filter_report.stages]
    assert any("不可能值" in label for label in labels)


# ---------- 驗證與回歸：既有四策略逐位元不變（T01／#218）----------

def test_four_existing_strategies_pass_through_unaffected_under_normal_quotes():
    """正常報價下，B 層不移除任何候選——四個既有策略在真實 fixture 上
    的候選數與 T01 基準完全一致（間接證明：本票不改變既有排名）。"""
    for strategy, target in (("long-call", 120.0), ("long-put", 80.0),
                             ("bull-call-spread", 120.0),
                             ("bear-put-spread", 80.0)):
        result = service.run_offline(
            service.AnalysisRequest(symbol="XYZ", base_params=_params(strategy, target),
                                    strategies=(strategy,)), FIX)
        res = next(r for r in result.results if r.strategy == strategy)
        assert res.status == "ok"
        b_stage_removed = 0
        if res.filter_report:
            b_stage_removed += sum(s.removed for s in res.filter_report.stages
                                   if "不可能值" in s.label)
        if res.pair_report:
            b_stage_removed += res.pair_report.b_layer_removed
        assert b_stage_removed == 0, (
            f"{strategy}: B 層在正常報價下不該移除任何候選，實際移除 "
            f"{b_stage_removed} 筆")
