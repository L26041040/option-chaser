"""REPAIR-09（#246，spec #237 OD-02，FIX-05）：單腿排名基準估值改為
own-expiration payoff——與 Vertical／Butterfly（T3／#17）既有裁示對齊，
不再用固定日曆錨點（附錄 A9）殘留時間價值，造成跨 family 排名系統性
灌水（實測最高 +166.1 pp，#052 audit）。

沿用 `tests/test_spread_baseline_at_expiry.py`（T3／#17 當年的同一套
結構）逐條鏡射到單腿版本——同一個問題、同一種修法、同一套驗證手法，
只是換成 `evaluate_contract()`。
"""
from datetime import date

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract, scenario_leg_value

TODAY = date(2026, 7, 15)

STRIKE = 110.0


def params(target_price: float = 120.0, strategy: str = "long-call") -> AnalysisParams:
    return AnalysisParams(target_price=target_price, target_month="2026-08",
                          strategy=strategy)


ANCHOR = params().anchor   # 舊的共用估值日；本票之後基準值不該再受它影響


def call_leg(expiry: str, iv: float = 0.30) -> OptionContract:
    return OptionContract(contract_symbol="C", option_type="call",
                          strike=STRIKE, expiry=expiry, bid=3.0, ask=3.25,
                          last=None, volume=10, open_interest=100,
                          implied_volatility=iv)


def put_leg(expiry: str, iv: float = 0.30) -> OptionContract:
    return OptionContract(contract_symbol="P", option_type="put",
                          strike=STRIKE, expiry=expiry, bid=3.0, ask=3.25,
                          last=None, volume=10, open_interest=100,
                          implied_volatility=iv)


def baseline_for(expiry: str, target_price: float = 120.0) -> float:
    return evaluate_contract(call_leg(expiry), spot=100.0, today=TODAY,
                             p=params(target_price)).baseline_value


# --- 估值時點：三種到期日相對錨點的位置 ------------------------------------

def test_expiry_after_the_anchor_uses_its_own_expiry():
    """核心案例——這正是 #052 audit 抓到的灌水情境：到期日晚於錨點，
    修法前會在錨點那天用 BS 估值、殘留時間價值；修法後在自己的到期日
    估值，退化成純內在價值（target_price − strike，call 價內 10 元）。
    """
    expiry = "2026-10-16"
    assert date.fromisoformat(expiry) > ANCHOR
    assert baseline_for(expiry) == 10.0   # 120 − 110


def test_expiry_equal_to_the_anchor():
    assert baseline_for(ANCHOR.isoformat()) == 10.0


def test_expiry_before_the_anchor():
    expiry = "2026-07-17"
    assert date.fromisoformat(expiry) < ANCHOR
    assert baseline_for(expiry) == 10.0


def test_all_three_positions_agree():
    """三種到期日位置的基準值一致——證明估值時點不再是那個共用日期。"""
    values = {baseline_for(e) for e in
              ("2026-07-17", ANCHOR.isoformat(), "2026-10-16", "2027-01-15")}
    assert values == {10.0}


def test_the_fix_actually_changes_the_number_for_a_late_expiry():
    """直接證明這不是空斷言：同一張合約若仍用舊的錨點估值（`scenario_
    leg_value(..., ANCHOR, ...)`），到期日晚於錨點時會得到一個高於
    內在價值的數字（殘留時間價值）——修法後的 `baseline_value` 必須
    嚴格小於它，證明真的換了估值時點，不是巧合同值。"""
    expiry = "2026-10-16"
    p = params()
    c = call_leg(expiry)
    old_anchor_based_value = scenario_leg_value(c, p.target_price, ANCHOR, p)
    fixed = evaluate_contract(c, spot=100.0, today=TODAY, p=p).baseline_value
    assert fixed == 10.0
    assert old_anchor_based_value > fixed   # 舊路徑真的比較貴（灌水）


# --- payoff 兩區段（單腿無「介於兩履約價之間」的第三段） --------------------

def test_call_in_the_money_pays_intrinsic():
    assert baseline_for("2026-10-16", target_price=140.0) == 30.0


def test_call_out_of_the_money_pays_nothing():
    assert baseline_for("2026-10-16", target_price=90.0) == 0.0


def test_call_exactly_at_the_strike_pays_nothing():
    assert baseline_for("2026-10-16", target_price=STRIKE) == 0.0


def test_baseline_never_goes_negative():
    for target in (1.0, 50.0, 90.0, 110.0, 200.0, 500.0):
        assert baseline_for("2026-10-16", target_price=target) >= 0.0


def test_put_uses_the_same_own_expiry_semantics():
    """AC 明文點名 Long Call**與** Long Put，這裡單獨驗證 put 那一側。"""
    expiry = "2026-10-16"
    p = params(target_price=90.0, strategy="long-put")
    v = evaluate_contract(put_leg(expiry), spot=100.0, today=TODAY, p=p)
    assert v.baseline_value == 20.0   # 110 − 90，put 價內


# --- 到期＝內在價值，與 IV 無關 --------------------------------------------

def test_baseline_ignores_implied_volatility():
    """到期時沒有時間價值可言，IV 不得影響基準值。"""
    p = params(115.0)
    quiet = evaluate_contract(call_leg("2026-10-16", iv=0.10), spot=100.0,
                              today=TODAY, p=p)
    wild = evaluate_contract(call_leg("2026-10-16", iv=1.20), spot=100.0,
                             today=TODAY, p=p)
    assert quiet.baseline_value == wild.baseline_value == 5.0


def test_iv_scenarios_collapse_at_expiry():
    """持有至到期的情境向量沒有 IV 不確定性，三檔 shift 必然同值；
    l2（最保守 IV 情境下的價值）在到期時也必須跟 baseline_value 同值
    ——這正是灌水修好之後，買價指引天花板（l2／l3）跟著一起修正的
    直接後果。"""
    v = evaluate_contract(call_leg("2026-10-16"), spot=100.0, today=TODAY,
                          p=params(115.0))
    assert {val for _, val in v.scenario_values} == {5.0}
    assert v.l2 == v.baseline_value == 5.0


# --- 與 Heatmap 估值路徑分離 ------------------------------------------------

def test_heatmap_path_still_carries_time_value():
    """同一張合約、同一個 spot，在到期**前**估值必須高於到期內在價值。

    這是兩種語意分離的證據：本票只改排名的估值時點（`evaluate_
    contract` 的 `baseline_value`／`scenario_values`／`l2`／`l3`），
    Heatmap 逐格 BS（直接呼叫 `scenario_leg_value` 帶任意日期）與 V7
    三價位（`ranking.return_at_price` 沿用既有錨點，票面明文不動）
    完全不受影響。
    """
    c = call_leg("2026-10-16")
    p = params(115.0)
    before_expiry = scenario_leg_value(c, 115.0, date(2026, 9, 1), p)
    at_expiry = scenario_leg_value(c, 115.0, date(2026, 10, 16), p)
    assert at_expiry == 5.0
    assert before_expiry != at_expiry
    assert before_expiry >= 0.0
