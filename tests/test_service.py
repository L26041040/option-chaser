import dataclasses
from datetime import date
from option_chaser.models import AnalysisParams, ParamError
from option_chaser import service
from option_chaser.ranking import baseline_return
import pytest

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def req(strategies, target=120.0, force=False):
    base = AnalysisParams(target_price=target, target_date="2026-08-28", force=force)
    return service.AnalysisRequest(symbol="XYZ", base_params=base,
                                   strategies=tuple(strategies))


def test_multi_strategy_shared_snapshot_and_order():
    r = service.run_offline(req(["long-call", "bull-call-spread"]), FIX)
    assert [s.strategy for s in r.results] == ["long-call", "bull-call-spread"]
    assert r.meta.spot == 100.0 and r.snapshot.symbol == "XYZ"
    assert r.today == date(2026, 7, 15)


def test_single_leg_result_matches_engine_and_report():
    from option_chaser.filters import apply_filters
    from option_chaser.valuation import evaluate_contract
    from option_chaser.ranking import rank
    from option_chaser.report import render
    from option_chaser.data.snapshot import load_snapshot, snapshot_today
    r = service.run_offline(req(["long-call"]), FIX)
    res = r.results[0]
    assert res.status == "ok" and res.n_qualified == 5
    p = dataclasses.replace(req(["long-call"]).base_params, strategy="long-call")
    snap = load_snapshot(FIX)
    today = snapshot_today(snap.fetched_at)
    qualified, freport = apply_filters(snap.contracts, p, today)
    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    ranked = rank(vals, p)
    assert res.report_text == render(snap, p, freport, ranked,
                                     n_qualified=len(qualified), today=today)
    # tab candidates = band #1s
    assert [cv.valuation.contract.contract_symbol for cv in res.candidates] == [
        ranked[b][0].contract.contract_symbol for b in ("conservative", "balanced", "aggressive") if ranked[b]]


def test_comparison_uses_global_best_not_band_order():
    r = service.run_offline(req(["long-call"]), FIX)
    res = r.results[0]
    row = r.comparison[0]
    firsts = [lst[0] for lst in res.ranked_bands.values() if lst]
    best = max(firsts, key=baseline_return)
    assert abs(row.baseline_return - baseline_return(best)) < 1e-12
    assert row.label == f"K={best.contract.strike:g}"
    assert row.max_profit is None  # long-call unlimited


def test_long_put_max_profit_bounded():
    r = service.run_offline(req(["long-put"], target=80.0), FIX)
    row = r.comparison[0]
    assert row.max_profit is not None and row.max_profit > 0


def test_direction_skip_without_force_runs_others():
    r = service.run_offline(req(["long-call", "long-put"], target=80.0), FIX)
    by = {s.strategy: s for s in r.results}
    assert by["long-call"].status == "skipped_direction"
    assert by["long-call"].report_text is None
    assert by["long-put"].status == "ok"
    assert r.best_strategy == "long-put"


def test_force_runs_mismatched_direction():
    r = service.run_offline(req(["long-call"], target=80.0, force=True), FIX)
    assert r.results[0].status == "ok"


def test_empty_carries_filter_only_report():
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                          min_expiry="2030-01-01")
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ", base_params=base, strategies=("long-call",)), FIX)
    res = r.results[0]
    assert res.status == "empty" and "無合格" in res.report_text
    assert r.comparison == () and r.best_strategy is None


def test_target_date_not_after_snapshot_raises():
    base = AnalysisParams(target_price=120.0, target_date="2026-07-15")
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=("long-call",)), FIX)


def test_matrix_view_matches_grid():
    from option_chaser.matrix import matrix_grid, price_axis, date_axis
    from option_chaser.valuation import scenario_leg_value
    r = service.run_offline(req(["long-call"]), FIX)
    cv = r.results[0].candidates[0]
    v = cv.valuation
    p = dataclasses.replace(req(["long-call"]).base_params, strategy="long-call")
    prices = price_axis(100.0, 120.0)
    dates = date_axis(r.today, date(2026, 8, 28),
                      date.fromisoformat(v.contract.expiry))
    grid = matrix_grid(lambda S, d, c=v.contract: scenario_leg_value(c, S, d, p),
                       v.mid, prices, dates)
    assert cv.matrix.cells == grid
    assert cv.matrix.dates[-1][0] == v.contract.expiry


def test_invalid_request_rejected():
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=()), FIX)
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=("straddle",)), FIX)


def test_validation_precedes_fetch_and_load(monkeypatch):
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    bad = service.AnalysisRequest(symbol="XYZ", base_params=base, strategies=())
    # run(): fetch must never be touched
    import option_chaser.data.yf as yf_mod
    monkeypatch.setattr(yf_mod, "fetch_chain",
                        lambda symbol: (_ for _ in ()).throw(AssertionError("fetch called")))
    with pytest.raises(ParamError):
        service.run(bad)
    # run_offline(): validation raises ParamError even for nonexistent path (load not reached)
    with pytest.raises(ParamError):
        service.run_offline(bad, "does-not-exist.json")


def test_result_carries_request():
    r = service.run_offline(req(["long-call"]), FIX)
    assert r.request.base_params.target_price == 120.0


def test_progress_callback_called():
    calls = []
    service.run_offline(req(["long-call"]), FIX, progress=calls.append)
    assert any("過濾" in c or "比較" in c for c in calls)


def test_candidate_view_returns_precomputed():
    from option_chaser.ranking import baseline_return as br
    r = service.run_offline(req(["long-call"]), FIX)
    cv = r.results[0].candidates[0]
    v = cv.valuation
    assert cv.baseline_return == br(v)
    assert abs(cv.baseline_pnl - (v.baseline_value - v.mid)) < 1e-12
    assert abs(cv.worst_return - (v.baseline_value - v.contract.ask) / v.contract.ask) < 1e-12
