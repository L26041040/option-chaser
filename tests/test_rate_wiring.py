# tests/test_rate_wiring.py
"""T12(A3) 接線：每腿以自身剩餘年期取利率、`--rate` 明示跳過管線、
報告參數行三態標示。全部離線（loader 為注入的假物件）。"""
from datetime import date

import pytest

from option_chaser import service
from option_chaser.cli import build_parser, resolve_params
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.ratecurve import RateCurve
from option_chaser.valuation import (clamped_price, evaluate_spread, leg_rate,
                                     scenario_leg_value)

SNAP = "tests/fixtures/xyz_v4_six_expiries.json"


def _contract(expiry: str, strike=110.0, bid=10.0, ask=10.4) -> OptionContract:
    return OptionContract(contract_symbol=f"C{expiry}", option_type="call",
                          strike=strike, expiry=expiry, bid=bid, ask=ask,
                          last=None, volume=10, open_interest=100,
                          implied_volatility=0.38)


def _params(**kw) -> AnalysisParams:
    return AnalysisParams(target_price=120.0, target_month="2026-08", **kw)


# ---------- leg_rate 查表 ----------

def test_leg_rate_lookup_and_fallback():
    p = _params(rate_by_expiry=(("2026-09-18", 0.041), ("2027-01-15", 0.043)))
    assert leg_rate(p, "2026-09-18") == 0.041
    assert leg_rate(p, "2027-01-15") == 0.043
    assert leg_rate(p, "2028-01-19") == p.rate      # 表外 → 常數


def test_scenario_leg_value_uses_own_expiry_rate():
    p = _params(rate_by_expiry=(("2026-12-18", 0.10),))
    c = _contract("2026-12-18")
    at = date(2026, 8, 21)
    T = (date(2026, 12, 18) - at).days / 365.0
    assert scenario_leg_value(c, 120.0, at, p) == pytest.approx(
        clamped_price("call", 120.0, 110.0, T, 0.10, 0.38))
    # 對照：無表時仍用 p.rate
    p0 = _params()
    assert scenario_leg_value(c, 120.0, at, p0) == pytest.approx(
        clamped_price("call", 120.0, 110.0, T, 0.04, 0.38))


def test_legs_with_different_expiries_get_different_rates():
    """驗收：不同到期日的腿取到不同 r。"""
    p = _params(rate_by_expiry=(("2026-12-18", 0.03), ("2027-06-18", 0.05)))
    near, far = _contract("2026-12-18"), _contract("2027-06-18")
    at = date(2026, 8, 21)
    t_near = (date(2026, 12, 18) - at).days / 365.0
    t_far = (date(2027, 6, 18) - at).days / 365.0
    assert scenario_leg_value(near, 120.0, at, p) == pytest.approx(
        clamped_price("call", 120.0, 110.0, t_near, 0.03, 0.38))
    assert scenario_leg_value(far, 120.0, at, p) == pytest.approx(
        clamped_price("call", 120.0, 110.0, t_far, 0.05, 0.38))
    # 同一組參數下兩腿實際用到不同 r（而非同一常數）
    assert leg_rate(p, near.expiry) != leg_rate(p, far.expiry)
    # evaluate_spread 不炸且能吃異到期日腿（greeks 逐腿取各自 r）
    sv = evaluate_spread(near, _contract("2027-06-18", 130.0, bid=2.0, ask=2.2),
                         spot=100.0, today=date(2026, 7, 15), p=p)
    assert sv.net_delta == sv.net_delta        # smoke: 有限值


# ---------- service 管線三態 ----------

def _request():
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08"),
        strategies=("long-call",))


def _fake_loader(today):
    # 平坦 par 曲線→轉換後為常數 cc 曲線；值刻意偏離 0.04 以便觀察生效
    return (RateCurve(curve_date="2026-07-31",
                      nodes=((1 / 12, 0.05), (5.0, 0.05))),
            "Treasury 曲線 2026-07-31")


def test_run_offline_with_loader_resolves_per_expiry_rates():
    result = service.run_offline(_request(), SNAP,
                                 rate_curve_loader=_fake_loader)
    p = result.request.base_params
    assert p.rate_by_expiry, "曲線可得時必須解出各到期日利率"
    expiries = {c.expiry for c in result.snapshot.contracts}
    assert {e for e, _ in p.rate_by_expiry} == expiries
    assert all(r == pytest.approx(0.05) for _, r in p.rate_by_expiry)
    res = result.results[0]
    assert "期限對齊" in res.report_text
    assert "Treasury 曲線 2026-07-31" in res.report_text


def test_run_offline_without_loader_keeps_legacy_behavior():
    result = service.run_offline(_request(), SNAP)
    p = result.request.base_params
    assert p.rate_by_expiry == () and p.rate_note == ""
    assert "無風險利率 4.0%" in result.results[0].report_text


def test_loader_failure_falls_back_to_fixed_rate_with_note():
    result = service.run_offline(_request(), SNAP,
                                 rate_curve_loader=lambda t: (None, "曲線不可得"))
    p = result.request.base_params
    assert p.rate_by_expiry == ()
    text = result.results[0].report_text
    assert "固定 4.0%" in text and "曲線不可得" in text


def test_explicit_rate_skips_pipeline_entirely():
    def exploding_loader(today):
        raise AssertionError("--rate 明示時不得呼叫利率管線")

    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", rate=0.07,
                                   rate_explicit=True),
        strategies=("long-call",))
    result = service.run_offline(req, SNAP, rate_curve_loader=exploding_loader)
    assert result.request.base_params.rate_by_expiry == ()
    assert "無風險利率 7.0%" in result.results[0].report_text


# ---------- CLI --rate 語意 ----------

def _parse(*argv):
    return build_parser().parse_args(
        ["XYZ", "--target-price", "120", "--target-month", "2026/8", *argv])


def test_cli_rate_omitted_default_004_not_explicit():
    p = resolve_params(_parse())
    assert p.rate == 0.04 and p.rate_explicit is False


def test_cli_rate_given_marks_explicit():
    p = resolve_params(_parse("--rate", "0.05"))
    assert p.rate == 0.05 and p.rate_explicit is True


def test_cli_rate_negative_rejected():
    from option_chaser.models import ParamError
    with pytest.raises(ParamError):
        resolve_params(_parse("--rate=-0.01"))
