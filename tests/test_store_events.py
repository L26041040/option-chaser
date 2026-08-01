"""v5 spec §2.2/§2.3 + §7.2: 事件、投影（行序權威）、轉移、兩型不一致。"""
import dataclasses
import json
from pathlib import Path

import pytest

from option_chaser import store
from option_chaser.store import Scenario, WorkspaceIntegrityError

TS = "2026-07-21T00:00:00+00:00"


def _sc(**kw):
    base = dict(schema_version=store.SCENARIO_SCHEMA_VERSION, id="TLT-105-202801", symbol="TLT",
                direction="bullish", target_price=105.0,
                target_month="2028-01", created_at=TS, notes="",
                group_id="G-TLT", status="Active",
                strategies=("long-call",))
    base.update(kw)
    return Scenario(**base)


def _boot(tmp_path):
    sc = _sc()
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_CREATED",
                       dataclasses.asdict(sc))
    store.save_scenario(tmp_path, sc)
    return sc


def test_append_and_read_order(tmp_path):
    _boot(tmp_path)
    store.append_event(tmp_path, TS, "TLT-105-202801", "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r", "by": "user"})
    events = store.read_events(tmp_path)
    assert [e["event"] for e in events] == ["SCENARIO_CREATED", "STATUS_CHANGED"]


def test_append_rejects_non_v5_vocabulary(tmp_path):
    with pytest.raises(ValueError):
        store.append_event(tmp_path, TS, None, "BOGUS_EVENT", {})
    with pytest.raises(ValueError):   # v7 預留 enum 在 v5 拒寫
        store.append_event(tmp_path, TS, None, "PRICE_REACHED", {})


def test_legal_transitions_append_event_and_update_cache(tmp_path):
    sc = _boot(tmp_path)
    for to, by in [("Reached", "user")]:
        sc2 = store.change_status(tmp_path, TS, sc, to, reason="到了", by=by)
        assert sc2.status == to
        on_disk = store.load_scenario(store.scenario_path(tmp_path, sc.id))
        assert on_disk.status == to
        last = store.read_events(tmp_path)[-1]
        assert last["event"] == "STATUS_CHANGED"
        assert last["payload"] == {"from": "Active", "to": to,
                                   "reason": "到了", "by": by}


def test_expired_observational_payload(tmp_path):
    sc = _boot(tmp_path)
    store.change_status(tmp_path, TS, sc, "Expired", reason="target_date 已過",
                        by="system", extra_payload={"observed_at": "2028-01-02"})
    last = store.read_events(tmp_path)[-1]
    assert last["payload"]["observed_at"] == "2028-01-02"


def test_illegal_transitions_raise(tmp_path):
    sc = _boot(tmp_path)
    sc = store.change_status(tmp_path, TS, sc, "Reached", reason="r")
    for to in ("Active", "Invalidated", "Expired"):
        with pytest.raises(ValueError):
            store.change_status(tmp_path, TS, sc, to, reason="x")


def test_projection_and_reconcile_clean(tmp_path):
    sc = _boot(tmp_path)
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) == "Active"
    assert store.reconcile_status(tmp_path, sc, events) == sc


def test_crash_window_repair(tmp_path):
    """崩潰窗：事件已 append、快取未更新 → 自動修復、不追加事件。"""
    sc = _boot(tmp_path)
    store.append_event(tmp_path, TS, sc.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r", "by": "user"})
    # 快取仍是 Active（== 最後一筆 STATUS_CHANGED 的 from）
    events = store.read_events(tmp_path)
    n_before = len(events)
    repaired = store.reconcile_status(tmp_path, sc, events)
    assert repaired.status == "Reached"
    assert store.load_scenario(store.scenario_path(tmp_path, sc.id)).status == "Reached"
    assert len(store.read_events(tmp_path)) == n_before   # 不追加新事件


def test_tamper_raises(tmp_path):
    sc = _boot(tmp_path)
    hacked = dataclasses.replace(sc, status="Reached")   # 無任何事件可解釋
    store.save_scenario(tmp_path, hacked)
    with pytest.raises(WorkspaceIntegrityError):
        store.reconcile_status(tmp_path, hacked, store.read_events(tmp_path))


def test_deleted_then_recreated_restarts_projection(tmp_path):
    sc = _boot(tmp_path)
    sc = store.change_status(tmp_path, TS, sc, "Reached", reason="r")
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_DELETED", {})
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) is None       # 生命週期結束
    # 同 id 重建 → 投影重新起算（舊 Reached 不復活）
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_CREATED",
                       dataclasses.asdict(_sc()))
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) == "Active"
