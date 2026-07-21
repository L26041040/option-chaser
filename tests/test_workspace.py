"""v5 spec §4 + §7.2/§7.3a/§7.5: 編排層 CRUD、載入期對帳矩陣、觀察式過期。"""
import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from option_chaser import store, workspace

TS = "2026-07-21T00:00:00+00:00"


def _create(ws, symbol="TLT", price=105.0, tdate="2028-01-01",
            direction="bullish"):
    return workspace.create_scenario(
        ws, symbol=symbol, direction=direction, target_price=price,
        target_date=tdate, notes="", strategies=("long-call",), ts=TS)


def test_create_writes_event_file_and_groups(tmp_path):
    sc = _create(tmp_path)
    assert sc.id == "TLT-105-202801" and sc.group_id == "G-TLT"
    events = store.read_events(tmp_path)
    assert events[0]["event"] == "SCENARIO_CREATED"
    assert store.scenario_path(tmp_path, sc.id).exists()
    groups = json.loads((tmp_path / "groups.json").read_text(encoding="utf-8"))
    assert groups["groups"][0]["members"] == [sc.id]


def test_create_collision_deterministic(tmp_path):
    a = _create(tmp_path)
    b = _create(tmp_path)
    assert (a.id, b.id) == ("TLT-105-202801", "TLT-105-202801-2")


def test_list_returns_sorted_and_validated(tmp_path):
    _create(tmp_path, symbol="TLT", tdate="2028-12-01", price=115.0)
    _create(tmp_path, symbol="SPY", price=500.0)
    _create(tmp_path, symbol="TLT", tdate="2028-01-01", price=105.0)
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert [s.symbol for s in got] == ["SPY", "TLT", "TLT"]
    assert got[1].target_date == "2028-01-01"


def test_set_status_and_confirm_relation(tmp_path):
    a = _create(tmp_path, tdate="2028-01-01", price=105.0)
    b = _create(tmp_path, tdate="2028-12-01", price=115.0)
    workspace.set_status(tmp_path, a.id, "Reached", reason="到價", ts=TS)
    assert store.load_scenario(store.scenario_path(tmp_path, a.id)).status == "Reached"
    workspace.confirm_relation(tmp_path, "G-TLT", (a.id, b.id),
                               "milestone-path", ts=TS)
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["relations"][0]["confirmed"] == "milestone-path"
    with pytest.raises(ValueError):
        workspace.confirm_relation(tmp_path, "G-TLT", (a.id, b.id), "bogus", ts=TS)


def test_expired_observational_transition(tmp_path):
    sc = _create(tmp_path, tdate="2027-01-01")
    got = workspace.list_scenarios(tmp_path, observed=date(2027, 1, 2))
    assert got[0].status == "Expired"
    last = store.read_events(tmp_path)[-1]
    assert last["event"] == "STATUS_CHANGED"
    assert last["payload"]["to"] == "Expired"
    assert last["payload"]["observed_at"] == "2027-01-02"
    assert last["payload"]["by"] == "system"


def test_not_expired_on_boundary_date(tmp_path):
    """觀察日 == target_date 不過期（規則是 觀察日 > target_date）。"""
    _create(tmp_path, tdate="2027-01-01")
    got = workspace.list_scenarios(tmp_path, observed=date(2027, 1, 1))
    assert got[0].status == "Active"


def test_delete_scenario_full_chain(tmp_path):
    a = _create(tmp_path, tdate="2028-01-01", price=105.0)
    b = _create(tmp_path, tdate="2028-12-01", price=115.0)
    (tmp_path / "results" / a.id).mkdir(parents=True)
    (tmp_path / "results" / a.id / "x.json").write_text("{}", encoding="utf-8")
    workspace.delete_scenario(tmp_path, a.id, ts=TS)
    assert not store.scenario_path(tmp_path, a.id).exists()
    assert not (tmp_path / "results" / a.id).exists()
    assert store.read_events(tmp_path)[-1]["event"] == "SCENARIO_DELETED"
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [b.id]


def test_reconcile_interrupted_delete(tmp_path):
    """§2.5 對帳：DELETED 末事件但檔案仍在 → 載入時完成刪除（冪等）。"""
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "SCENARIO_DELETED", {})
    # scenario 檔與 results 殘留
    (tmp_path / "results" / a.id).mkdir(parents=True)
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got == []
    assert not store.scenario_path(tmp_path, a.id).exists()
    assert not (tmp_path / "results" / a.id).exists()


def test_reconcile_created_without_file_ignored(tmp_path):
    store.append_event(tmp_path, TS, "GHOST-1-202801", "SCENARIO_CREATED",
                       {"id": "GHOST-1-202801"})
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got == []   # 不拋錯、不出現


def test_reconcile_crash_window_repair_in_list(tmp_path):
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r",
                        "by": "user"})   # 快取未更新（崩潰窗）
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got[0].status == "Reached"


def test_reconcile_tamper_raises_in_list(tmp_path):
    a = _create(tmp_path)
    store.save_scenario(tmp_path, dataclasses.replace(a, status="Invalidated"))
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))


def test_groups_rebuilt_on_load_after_manual_delete(tmp_path):
    _create(tmp_path)
    (tmp_path / "groups.json").unlink()
    workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert (tmp_path / "groups.json").exists()


def test_set_status_reconciles_before_transition(tmp_path):
    """崩潰窗後直呼 set_status：先修復（實為 Reached），再驗轉移合法性。"""
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r",
                        "by": "user"})   # 快取未更新（崩潰窗）
    with pytest.raises(ValueError):      # 修復後 Reached→Reached 非法，不重複 append
        workspace.set_status(tmp_path, a.id, "Reached", reason="again", ts=TS)
    assert store.load_scenario(store.scenario_path(tmp_path, a.id)).status == "Reached"


def test_load_groups_overwrites_tampered_file(tmp_path):
    a = _create(tmp_path)
    (tmp_path / "groups.json").write_text(
        '{"schema_version": 1, "groups": []}', encoding="utf-8")
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [a.id]   # 無條件重建，不信磁碟


def test_default_direction(tmp_path):
    assert workspace.default_direction("NOPE", 100.0,
                                       snapshots_dir=tmp_path) is None
    snap = json.loads(Path("tests/fixtures/xyz_v4_six_expiries.json")
                      .read_text(encoding="utf-8"))
    (tmp_path / "XYZ_20260721T000000+0000.json").write_text(
        json.dumps(snap), encoding="utf-8")
    spot = snap["spot"]
    assert workspace.default_direction("XYZ", spot + 10,
                                       snapshots_dir=tmp_path) == "bullish"
    assert workspace.default_direction("XYZ", spot - 10,
                                       snapshots_dir=tmp_path) == "bearish"
