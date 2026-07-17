# tests/test_guidance.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract, guidance_judgments

TODAY = date(2026, 7, 15)


def make(strike, bid, ask, iv, expiry="2026-10-16"):
    return OptionContract(
        contract_symbol=f"XYZ-K{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=None, volume=10, open_interest=100,
        implied_volatility=iv,
    )


def test_ceiling_identity_matrix():
    # Spec §9 test 5: L1 <= L2 <= baseline over a fixed parameter matrix.
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    for strike in (80.0, 100.0, 110.0, 119.0, 130.0, 150.0):
        for iv in (0.15, 0.38, 0.9):
            for expiry in ("2026-10-16", "2027-01-15"):
                v = evaluate_contract(make(strike, 3.0, 3.2, iv, expiry),
                                      spot=100.0, today=TODAY, p=p)
                assert v.l1 <= v.l2 + 1e-12
                assert v.l2 <= v.baseline_value + 1e-12
                assert v.l3 <= v.baseline_value + 1e-12


def test_no_negative_shift_l2_equals_baseline():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       iv_shifts=(0.0, 0.2), delay_days=0)
    v = evaluate_contract(make(110.0, 3.0, 3.2, 0.38), spot=100.0, today=TODAY, p=p)
    assert v.l2 == v.baseline_value


def test_judgments_all_trigger():
    # ask above every ceiling -> all three sentences
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make(95.0, 30.6, 31.0, 0.9), spot=100.0, today=TODAY, p=p)
    msgs = guidance_judgments(v, p)
    assert len(msgs) == 3
    assert "超過劇本內在價值" in msgs[0]
    assert "最保守 IV 情境" in msgs[1]
    assert "最低報酬" in msgs[2]


def test_judgments_none_trigger():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make(110.0, 3.0, 3.25, 0.38), spot=100.0, today=TODAY, p=p)
    assert guidance_judgments(v, p) == []
