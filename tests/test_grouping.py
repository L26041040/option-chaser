"""v4 spec §3.2: expiry grouping, sampling, badges, injection."""
from option_chaser import service
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _run(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_date="2026-08-28", min_return=0.0),
        strategies=strategies), SNAP)


def test_groups_ascending_and_rows_sorted():
    r = _run()
    assert r.expiry_groups
    expiries = [g.expiry for g in r.expiry_groups]
    assert expiries == sorted(expiries)
    for g in r.expiry_groups:
        rets = [row.candidate.baseline_return for row in g.rows]
        assert rets == sorted(rets, reverse=True)
        strategies = [row.strategy for row in g.rows]
        assert len(strategies) == len(set(strategies))  # per-strategy best only


def test_badges_global():
    r = _run()
    rows = [row for g in r.expiry_groups for row in g.rows]
    tops = [row for row in rows if "top_return" in row.badges]
    shields = [row for row in rows if "top_resilience" in row.badges]
    assert len(tops) == 1 and len(shields) == 1
    best = max(rows, key=lambda x: x.candidate.baseline_return)
    assert "top_return" in best.badges
    hard = max(rows, key=lambda x: x.candidate.scenario.worst_return)
    assert "top_resilience" in hard.badges


def test_default_selection_no_warning_and_visible():
    r = _run()
    assert r.default_selection is not None
    expiry, key = r.default_selection
    match = [row for g in r.expiry_groups if g.expiry == expiry
             for row in g.rows if service.candidate_key(row.candidate) == key]
    assert len(match) == 1
    all_rows = [row for g in r.expiry_groups for row in g.rows]
    if any(not row.candidate.quote_warning for row in all_rows):
        assert not match[0].candidate.quote_warning


def test_sampling_deterministic_six_expiries():
    """Unit test the sampler directly with 6 synthetic expiries."""
    exps = ["2028-01-21", "2028-03-17", "2028-06-16", "2028-09-15",
            "2028-12-15", "2029-06-15"]
    kept, hidden = service._sample_expiries(exps, "2027-11-30")
    assert len(kept) == 4
    assert kept[0] == "2028-01-21" and kept[1] == "2028-03-17"  # nearest 2
    assert set(kept) | set(hidden) == set(exps)
    assert kept == service._sample_expiries(exps, "2027-11-30")[0]  # deterministic
