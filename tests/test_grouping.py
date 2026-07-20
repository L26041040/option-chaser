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


# --- v4 task-review coverage gap: full-pipeline sampling + injection + all-warning fallback ---

SIX_EXPIRY_SNAP = "tests/fixtures/xyz_v4_six_expiries.json"
ALL_WARNING_SNAP = "tests/fixtures/xyz_v4_all_warning.json"

SIX_EXPIRIES = ("2026-08-07", "2026-08-21", "2026-09-18", "2026-10-16",
                "2026-11-20", "2026-12-18")


def _run_six_expiry():
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_date="2026-08-01", min_return=0.0),
        strategies=("long-call",)), SIX_EXPIRY_SNAP)


def test_six_expiry_pipeline_sampling_and_hidden():
    """(a) >4-expiry sampling through the FULL pipeline: hidden_expiries
    populated and per-group hidden_count correct."""
    r = _run_six_expiry()
    assert len(r.expiry_groups) >= 4

    group_expiries = [g.expiry for g in r.expiry_groups]
    assert group_expiries == sorted(group_expiries)  # ascending
    assert set(group_expiries) | set(r.hidden_expiries) == set(SIX_EXPIRIES)
    assert set(group_expiries).isdisjoint(r.hidden_expiries)

    res = r.results[0]
    qualified_counts = dict(res.expiry_counts)
    for g in r.expiry_groups:
        assert g.hidden_count == qualified_counts[g.expiry] - len(g.rows)


def test_injection_of_sampled_out_resilience():
    """(b) A global top_resilience candidate whose expiry is sampled OUT of
    the base <=4-group sample must be re-added to expiry_groups and removed
    from hidden_expiries (spec §3.2 injection)."""
    r = _run_six_expiry()
    rows = [row for g in r.expiry_groups for row in g.rows]
    resilient_rows = [row for row in rows if "top_resilience" in row.badges]
    assert len(resilient_rows) == 1
    resilient_row = resilient_rows[0]
    resilient_expiry = service._expiry_of(resilient_row.candidate)

    # visible in expiry_groups, not in hidden_expiries
    assert resilient_expiry in [g.expiry for g in r.expiry_groups]
    assert resilient_expiry not in r.hidden_expiries

    # prove it was actually sampled OUT of the base <=4 sample (i.e. injection fired)
    kept, hidden = service._sample_expiries(list(SIX_EXPIRIES), "2026-08-01")
    assert resilient_expiry in hidden
    assert resilient_expiry not in kept
    assert len(r.expiry_groups) > 4


def test_all_warning_fallback():
    """(c) When every candidate has quote_warning, default_selection falls
    back to the global top_return candidate (and it is still visible)."""
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_date="2026-08-01", min_return=0.0),
        strategies=("long-call",)), ALL_WARNING_SNAP)

    rows = [row for g in r.expiry_groups for row in g.rows]
    assert rows
    assert all("warning" in row.badges for row in rows)

    top_return_rows = [row for row in rows if "top_return" in row.badges]
    assert len(top_return_rows) == 1
    top_return_row = top_return_rows[0]
    expected = (service._expiry_of(top_return_row.candidate),
                service.candidate_key(top_return_row.candidate))

    assert r.default_selection == expected
    match = [row for g in r.expiry_groups if g.expiry == expected[0]
             for row in g.rows if service.candidate_key(row.candidate) == expected[1]]
    assert len(match) == 1  # visible
