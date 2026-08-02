"""v4 spec §3.2: expiry grouping, badges；選取取代事後抽樣。"""
from datetime import date

from option_chaser import service
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _run(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
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


# --- 六到期日鏈：選取取代抽樣 + all-warning fallback ---

SIX_EXPIRY_SNAP = "tests/fixtures/xyz_v4_six_expiries.json"
ALL_WARNING_SNAP = "tests/fixtures/xyz_v4_all_warning.json"

SIX_EXPIRIES = ("2026-08-07", "2026-08-21", "2026-09-18", "2026-10-16",
                "2026-11-20", "2026-12-18")


def _run_six_expiry():
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call",)), SIX_EXPIRY_SNAP)


def test_selection_replaces_sampling_no_hidden_expiries():
    """六檔鏈、目標月 2026-08（錨點 2026-08-21，恰好命中實際到期日）：
    baseline 前 1（鏈上只有一檔）＋ 後 3（缺額由另一側補足）＝ 五檔。
    每一檔選中的到期日都是一組，事後抽樣層已整個消失。"""
    r = _run_six_expiry()
    group_expiries = [g.expiry for g in r.expiry_groups]
    assert group_expiries == ["2026-08-07", "2026-08-21", "2026-09-18",
                              "2026-10-16", "2026-11-20"]
    assert r.hidden_expiries == ()
    assert "2026-12-18" not in group_expiries      # 超出五檔窗，未被窮舉

    res = r.results[0]
    qualified_counts = dict(res.expiry_counts)
    assert set(qualified_counts) == set(group_expiries)
    for g in r.expiry_groups:
        assert g.hidden_count == qualified_counts[g.expiry] - len(g.rows)


def test_all_badged_rows_visible():
    """全域徽章（最高報酬／最強韌性）恆在可見分組內——不再需要注入補救。"""
    r = _run_six_expiry()
    rows = [row for g in r.expiry_groups for row in g.rows]
    for badge in ("top_return", "top_resilience"):
        assert len([row for row in rows if badge in row.badges]) == 1


def test_buffer_days_measured_from_calendar_anchor():
    r = _run_six_expiry()
    anchor = r.request.base_params.anchor
    for g in r.expiry_groups:
        assert g.buffer_days == (date.fromisoformat(g.expiry) - anchor).days


def test_all_warning_fallback():
    """(c) When every candidate has quote_warning, default_selection falls
    back to the global top_return candidate (and it is still visible)."""
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
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
