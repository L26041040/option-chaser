"""v5 spec §2.4 + §7.3: 歸組、排序決定性、提案三分支（含 bearish 鏡像）、
確認投影、生命週期界定（同 id 重建不復活舊確認）。"""
import dataclasses
import json
from pathlib import Path

from option_chaser import store
from option_chaser.store import Scenario

TS = "2026-07-21T00:00:00+00:00"


def _sc(sid, symbol="TLT", direction="bullish", price=105.0,
        tmonth="2028-01"):
    return Scenario(schema_version=store.SCENARIO_SCHEMA_VERSION, id=sid, symbol=symbol,
                    direction=direction, target_price=price, target_month=tmonth,
                    created_at=TS, notes="", group_id=f"G-{symbol}",
                    status="Active", strategies=("long-call",))


def _created(ws, sc):
    store.append_event(ws, TS, sc.id, "SCENARIO_CREATED", dataclasses.asdict(sc))


def test_same_symbol_grouped_members_sorted(tmp_path):
    a = _sc("TLT-115-202812", price=115.0, tmonth="2028-12")
    b = _sc("TLT-105-202801", price=105.0, tmonth="2028-01")
    c = _sc("SPY-500-202801", symbol="SPY", price=500.0)
    for s in (a, b, c):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b, c], store.read_events(tmp_path))
    gids = [g["id"] for g in data["groups"]]
    assert gids == ["G-SPY", "G-TLT"]
    tlt = next(g for g in data["groups"] if g["id"] == "G-TLT")
    assert tlt["members"] == ["TLT-105-202801", "TLT-115-202812"]  # target_date 升冪
    on_disk = json.loads((tmp_path / "groups.json").read_text(encoding="utf-8"))
    assert on_disk == data


def test_same_date_tie_breaks_by_id(tmp_path):
    a = _sc("TLT-110-202801", price=110.0, tmonth="2028-01")
    b = _sc("TLT-105-202801", price=105.0, tmonth="2028-01")
    for s in (a, b):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    assert data["groups"][0]["members"] == ["TLT-105-202801", "TLT-110-202801"]


def test_proposal_three_branches_and_bearish_mirror():
    early_b = _sc("A", price=105.0, tmonth="2028-01")
    late_b = _sc("B", price=115.0, tmonth="2028-12")
    assert store.propose_relation(early_b, late_b) == "milestone-path"
    late_lower = _sc("C", price=95.0, tmonth="2028-12")
    assert store.propose_relation(early_b, late_lower) == "review-needed"
    bear = _sc("D", direction="bearish", price=90.0, tmonth="2028-12")
    assert store.propose_relation(early_b, bear) == "exclusive-candidate"
    # bearish 鏡像：價格沿方向遞減 = milestone-path
    b1 = _sc("E", direction="bearish", price=95.0, tmonth="2028-01")
    b2 = _sc("F", direction="bearish", price=85.0, tmonth="2028-12")
    assert store.propose_relation(b1, b2) == "milestone-path"
    b3 = _sc("G", direction="bearish", price=99.0, tmonth="2028-12")
    assert store.propose_relation(b1, b3) == "review-needed"


def test_confirm_projection_and_default_undefined(tmp_path):
    a = _sc("TLT-105-202801", price=105.0, tmonth="2028-01")
    b = _sc("TLT-115-202812", price=115.0, tmonth="2028-12")
    for s in (a, b):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["proposed"] == "milestone-path"
    assert rel["confirmed"] == "undefined" and rel["confirmed_at"] is None

    store.append_event(tmp_path, TS, None, "GROUP_RELATION_CONFIRMED",
                       {"group_id": "G-TLT", "pair": [a.id, b.id],
                        "choice": "milestone-path"})
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["confirmed"] == "milestone-path"
    assert rel["confirmed_at"] == TS


def test_recreate_does_not_resurrect_confirmation(tmp_path):
    """spec §2.4 生命週期界定負例（行序，非 ts）。"""
    a = _sc("TLT-105-202801", price=105.0, tmonth="2028-01")
    b = _sc("TLT-115-202812", price=115.0, tmonth="2028-12")
    for s in (a, b):
        _created(tmp_path, s)
    store.append_event(tmp_path, TS, None, "GROUP_RELATION_CONFIRMED",
                       {"group_id": "G-TLT", "pair": [a.id, b.id],
                        "choice": "milestone-path"})
    store.append_event(tmp_path, TS, a.id, "SCENARIO_DELETED", {})
    _created(tmp_path, a)   # 同 id 重建（新 CREATED 在確認事件之後）
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["confirmed"] == "undefined"   # 舊確認不復活
