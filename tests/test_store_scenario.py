"""v5 spec §2.1/§2.2/§2.6 + §7.1: Scenario round-trip、id 決定性、原子寫入、constraints。"""
import json
import os
from pathlib import Path

import pytest

from option_chaser import store
from option_chaser.store import Scenario


def _sc(**kw):
    base = dict(schema_version=1, id="TLT-105-202801", symbol="TLT",
                direction="bullish", target_price=105.0,
                target_date="2028-01-01", created_at="2026-07-21T00:00:00+00:00",
                notes="", group_id="G-TLT", status="Active",
                strategies=("long-call", "bull-call-spread"))
    base.update(kw)
    return Scenario(**base)


def test_scenario_round_trip(tmp_path):
    sc = _sc()
    store.save_scenario(tmp_path, sc)
    loaded = store.load_scenario(store.scenario_path(tmp_path, sc.id))
    assert loaded == sc
    assert isinstance(loaded.strategies, tuple)


def test_scenario_id_rules():
    assert store.scenario_id("TLT", 105.0, "2028-01-01", set()) == "TLT-105-202801"
    assert store.scenario_id("TLT", 92.5, "2028-01-01", set()) == "TLT-92p5-202801"


def test_scenario_id_collision_deterministic():
    existing = {"TLT-105-202801"}
    assert store.scenario_id("TLT", 105.0, "2028-01-01", existing) == "TLT-105-202801-2"
    existing.add("TLT-105-202801-2")
    assert store.scenario_id("TLT", 105.0, "2028-01-01", existing) == "TLT-105-202801-3"


def test_atomic_write_uses_tmp_and_replace(tmp_path, monkeypatch):
    """spec §7.1: 以「temp 檔命名規則＋replace 呼叫」單元鎖定。"""
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", spy)
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"a": 1})
    assert len(calls) == 1
    src, dst = calls[0]
    assert src.endswith(".json.tmp") and dst == str(target)
    assert not (tmp_path / "x.json.tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_atomic_write_interruption_leaves_no_target(tmp_path, monkeypatch):
    """寫入中斷（replace 前爆炸）不留半檔。"""
    def boom(src, dst):
        raise OSError("interrupted")

    monkeypatch.setattr(store.os, "replace", boom)
    target = tmp_path / "y.json"
    with pytest.raises(OSError):
        store.atomic_write_json(target, {"a": 1})
    assert not target.exists()


def test_constraints_two_states(tmp_path):
    assert store.load_constraints(tmp_path) == {
        "schema_version": 1, "total_capital": None}
    store.save_constraints(tmp_path, 100000.0)
    assert store.load_constraints(tmp_path)["total_capital"] == 100000.0
    store.save_constraints(tmp_path, None)
    assert store.load_constraints(tmp_path)["total_capital"] is None
