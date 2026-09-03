# tests/test_guidance.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract, guidance_judgments

TODAY = date(2026, 7, 15)


def make(strike, bid, ask, iv, expiry="2026-10-16"):
    return OptionContract(
        contract_symbol=f"XYZ-K{strike}", option_type="call", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=None, volume=10, open_interest=100,
        implied_volatility=iv,
    )


def test_ceiling_identity_matrix():
    # Spec §9 test 5: L1 <= L2 <= baseline over a fixed parameter matrix.
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    for strike in (80.0, 100.0, 110.0, 119.0, 130.0, 150.0):
        for iv in (0.15, 0.38, 0.9):
            for expiry in ("2026-10-16", "2027-01-15"):
                v = evaluate_contract(make(strike, 3.0, 3.2, iv, expiry),
                                      spot=100.0, today=TODAY, p=p)
                assert v.l1 <= v.l2 + 1e-12
                assert v.l2 <= v.baseline_value + 1e-12
                assert v.l3 <= v.baseline_value + 1e-12


def test_no_negative_shift_l2_equals_baseline():
    p = AnalysisParams(target_price=120.0, target_month="2026-08",
                       iv_shifts=(0.0, 0.2))
    v = evaluate_contract(make(110.0, 3.0, 3.2, 0.38), spot=100.0, today=TODAY, p=p)
    assert v.l2 == v.baseline_value


def test_judgments_all_trigger():
    # ask above every ceiling -> all three sentences
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    v = evaluate_contract(make(95.0, 31.4, 31.8, 0.9), spot=100.0, today=TODAY, p=p)
    # REPAIR-09（#246）：排名基準估值日改為候選自身到期日後，l1／l2／
    # l3／baseline_value 對單腿而言結構上恆相等（min_return=0 時）——
    # 與 Spread 早就有的 `l2 == baseline_value`（T3／#17 既有特性，
    # `spread_guidance_judgments()` docstring 甚至明講「spreads have
    # NO L1」）現在是同一件事的單腿版本，不是本票才出現的新缺陷：三層
    # 天花板不再嚴格遞增，但 ask 仍然個別越過每一層，`guidance_
    # judgments()` 的輸出本身（訊息數量與內容）不受影響。
    assert v.l1 == v.l2 == v.l3 == v.baseline_value == 25.0
    assert v.contract.ask > v.l1     # 三層天花板都被越過
    msgs = guidance_judgments(v, p)
    assert len(msgs) == 3
    assert "超過劇本內在價值" in msgs[0]
    assert "最保守 IV 情境" in msgs[1]
    assert "最低報酬" in msgs[2]


def test_judgments_none_trigger():
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    v = evaluate_contract(make(110.0, 3.0, 3.25, 0.38), spot=100.0, today=TODAY, p=p)
    assert guidance_judgments(v, p) == []
