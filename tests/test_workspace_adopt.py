# tests/test_workspace_adopt.py
"""v6 spec §1.2: adopt_result（quick-analysis -> persisted scenario）+ 撞名預檢。"""
from datetime import date

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


def _quick_result(price=120.0, tdate="2026-08-01"):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="long-call", target_price=price,
                                       target_date=tdate),
            strategies=("long-call", "bull-call-spread")),
        FIX)


def test_scenario_exists_none_when_absent(tmp_path):
    assert workspace.scenario_exists(tmp_path, "XYZ", 120.0, "2026-08-01") is None


def test_adopt_result_creates_scenario_and_result(tmp_path):
    result = _quick_result()
    sc, path = workspace.adopt_result(tmp_path, result, notes="from quick", ts=TS)
    assert sc.id == "XYZ-120-202608"
    assert sc.direction == "bullish"          # 120 > spot(~100)
    assert sc.strategies == ("long-call", "bull-call-spread")
    assert path.exists()
    view = store.load_result(path)
    assert view["scenario_id"] == sc.id
    assert view["snapshot_ref"]["path"] == FIX   # 重用當次 snapshot，非重新分析
    events = [e["event"] for e in store.read_events(tmp_path)]
    assert events == ["SCENARIO_CREATED", "ANALYSIS_COMPLETED"]
    assert workspace.scenario_exists(tmp_path, "XYZ", 120.0, "2026-08-01") == sc.id


def test_adopt_result_uses_current_capital(tmp_path):
    store.save_constraints(tmp_path, 50000.0)
    result = _quick_result()
    sc, path = workspace.adopt_result(tmp_path, result, ts=TS)
    view = store.load_result(path)
    assert view["capital_assumed"] == 50000.0


def test_adopt_result_bearish_direction(tmp_path):
    result = _quick_result(price=80.0)   # < spot(~100) -> bearish scenario in fixture terms
    sc, _ = workspace.adopt_result(tmp_path, result, ts=TS)
    assert sc.direction == "bearish"


def test_adopt_result_rejects_duplicate_base_id(tmp_path):
    result = _quick_result()
    workspace.adopt_result(tmp_path, result, ts=TS)
    with __import__("pytest").raises(ValueError):
        workspace.adopt_result(tmp_path, result, ts=TS)


def test_adopt_result_does_not_touch_other_workspace_functions(tmp_path):
    """迴歸防護：adopt_result 不得繞過 create_scenario 的既有 create 流程副作用
    （groups.json 必須反映新劇本）。"""
    result = _quick_result()
    sc, _ = workspace.adopt_result(tmp_path, result, ts=TS)
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [sc.id]
