"""v4 spec Task 8: CLI/GUI parity lock.

For every ok StrategyResult produced by service.run_offline on a shared
fixture snapshot, each CandidateView kept in `candidates` must format its
scenario/threshold/retention/friction numbers (report-style, 1 decimal
percent — mirrors option_chaser.report._pct/_money exactly) into substrings
that are byte-identical to what appears in that same strategy's report_text.
This proves the GUI's data source (CandidateView, service layer) and the CLI
report (report.py) are numerically the same computation, not two
independently-drifting formatters.
"""
from option_chaser import service
from option_chaser.models import AnalysisParams
from option_chaser.report import _money, _pct
from option_chaser.scenarios import SCENARIO_NAMES

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _request():
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call", "bull-call-spread"))


def _ok_results():
    result = service.run_offline(_request(), SNAP)
    ok = [r for r in result.results if r.status == "ok"]
    assert ok, "fixture must produce at least one ok StrategyResult"
    for res in ok:
        assert res.candidates, f"{res.strategy}: expected non-empty candidates"
    return ok


def _threshold_str(cv) -> str:
    """Mirrors report.py's _resilience_lines three-branch threshold display
    (spec §2.3): None / <=0 / else, with the exact CLI wording."""
    if cv.completion_threshold is None:
        thr = "— ⚠劇本全成仍不保本"
    elif cv.completion_threshold <= 0:
        thr = "0%（已保本）"
    else:
        thr = (f"完成 {_pct(cv.completion_threshold)}"
               f"（錨點日保本價 ${_money(cv.breakeven_at_target)}，基準IV）")
    return f"保本門檻: {thr}"


def test_scenario_entries_match_report_text():
    for res in _ok_results():
        for cv in res.candidates:
            for code, ret in cv.scenario.entries:
                line = f"- {code} {SCENARIO_NAMES[code]}: {_pct(ret)}"
                assert line in res.report_text, (
                    f"{res.strategy}: {line!r} missing from report_text")


def test_completion_threshold_matches_report_text():
    for res in _ok_results():
        for cv in res.candidates:
            expect = _threshold_str(cv)
            assert expect in res.report_text, (
                f"{res.strategy}: {expect!r} missing from report_text")


def test_retention_matches_report_text():
    for res in _ok_results():
        for cv in res.candidates:
            expect = f"不漲保留率: {_pct(cv.retention)}"
            assert expect in res.report_text, (
                f"{res.strategy}: {expect!r} missing from report_text")


def test_friction_matches_report_text():
    for res in _ok_results():
        for cv in res.candidates:
            expect = (f"Bid-Ask Spread: {_pct(min(cv.friction, 9.99))}"
                      f"（${_money(cv.friction_amount)}/股）")
            assert expect in res.report_text, (
                f"{res.strategy}: {expect!r} missing from report_text")
