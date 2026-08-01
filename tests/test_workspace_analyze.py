"""v5 spec §4 + §7.5: 分析鏈路（offline 注入）、群組共用 snapshot、事件序。"""
from datetime import date
from pathlib import Path

from option_chaser import store, workspace

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"


def _create(ws, price=120.0, tmonth="2026-08"):
    return workspace.create_scenario(
        ws, symbol="XYZ", direction="bullish", target_price=price,
        target_month=tmonth, notes="", strategies=("long-call",), ts=TS)


def test_create_analyze_latest_chain(tmp_path):
    sc = _create(tmp_path)
    path = workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)
    assert path.exists()
    view = workspace.latest_result(tmp_path, sc.id)
    assert view["scenario_id"] == sc.id
    assert view["snapshot_ref"]["path"] == FIX
    assert view["engine_version"] == "0.5.0"
    events = [e["event"] for e in store.read_events(tmp_path)]
    assert events == ["SCENARIO_CREATED", "ANALYSIS_COMPLETED"]
    last = store.read_events(tmp_path)[-1]
    assert last["payload"]["result_path"] == str(path)
    assert last["payload"]["snapshot_ref"] == view["snapshot_ref"]  # 完整物件


def test_analyze_logically_deleted_scenario_raises(tmp_path):
    """殘檔（已刪但 scenario 檔被復原/殘留）不得被分析。"""
    import pytest
    sc = _create(tmp_path)
    workspace.delete_scenario(tmp_path, sc.id, ts=TS)
    store.save_scenario(tmp_path, sc)   # 模擬殘檔
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)


def test_analyze_uses_capital_snapshot(tmp_path):
    sc = _create(tmp_path)
    store.save_constraints(tmp_path, 100000.0)
    workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)
    view = workspace.latest_result(tmp_path, sc.id)
    assert view["capital_assumed"] == 100000.0
    cand = view["results"][0]["candidates"][0]
    assert cand["pct_of_capital"] == cand["capital_per_contract"] / 100000.0


def test_analyze_group_shares_snapshot(tmp_path):
    a = _create(tmp_path, price=110.0, tmonth="2026-08")
    b = _create(tmp_path, price=120.0, tmonth="2026-09")
    paths = workspace.analyze_group(tmp_path, "G-XYZ",
                                    snapshot_path=FIX, ts=TS)
    assert len(paths) == 2
    views = [store.load_result(p) for p in paths]
    assert views[0]["snapshot_ref"]["path"] == views[1]["snapshot_ref"]["path"]
    assert {v["scenario_id"] for v in views} == {a.id, b.id}


def test_analyze_group_online_fetches_once(tmp_path, monkeypatch):
    from option_chaser import service
    from option_chaser.data.snapshot import load_snapshot
    _create(tmp_path, price=110.0, tmonth="2026-08")
    _create(tmp_path, price=120.0, tmonth="2026-09")
    calls = []

    def fake_fetch_and_save(symbol):
        calls.append(symbol)
        return load_snapshot(FIX), FIX

    monkeypatch.setattr(service, "fetch_and_save", fake_fetch_and_save)
    paths = workspace.analyze_group(tmp_path, "G-XYZ", ts=TS)
    assert calls == ["XYZ"]          # 一次抓取
    assert len(paths) == 2


def test_latest_result_none_without_analysis(tmp_path):
    sc = _create(tmp_path)
    assert workspace.latest_result(tmp_path, sc.id) is None
