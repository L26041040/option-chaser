"""T5（#19）／附錄 A8.2: 手動移除＝事件溯源軟刪除。

移除只寫一筆事件：清單與刷新不再包含該劇本，events.jsonl 與 results/ 下的
歷史檔案一個都不動（與 `delete_scenario` 的硬刪除是兩種不同的動作）。
"""
from datetime import date

import pytest

from option_chaser import store, workspace

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"
OBSERVED = date(2026, 7, 21)   # 與 TS 同日：建立驗證不吃真實時鐘


def _create(ws, price=120.0, tmonth="2028-01"):
    return workspace.create_scenario(
        ws, symbol="XYZ", direction="bullish", target_price=price,
        target_month=tmonth, notes="", strategies=("bull-call-spread",),
        ts=TS, observed=OBSERVED)


def test_remove_keeps_events_and_result_history(tmp_path):
    sc = _create(tmp_path)
    workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)
    before = sorted(p.name for p in (tmp_path / "results" / sc.id).glob("*.json"))

    workspace.remove_scenario(tmp_path, sc.id, ts=TS)

    assert [e["event"] for e in store.read_events(tmp_path)] == [
        "SCENARIO_CREATED", "ANALYSIS_COMPLETED", "SCENARIO_REMOVED"]
    after = sorted(p.name for p in (tmp_path / "results" / sc.id).glob("*.json"))
    assert after == before and before != []
    # 劇本檔本身也留著——移除是標記，不是清除
    assert store.scenario_path(tmp_path, sc.id).exists()


def test_removed_scenario_leaves_list_and_groups(tmp_path):
    a = _create(tmp_path, price=110.0, tmonth="2028-01")
    b = _create(tmp_path, price=120.0, tmonth="2028-12")

    workspace.remove_scenario(tmp_path, a.id, ts=TS)

    listed = workspace.list_scenarios(tmp_path, observed=OBSERVED)
    assert [s.id for s in listed] == [b.id]
    assert workspace.load_groups(tmp_path)["groups"][0]["members"] == [b.id]


def test_removed_scenario_is_not_refreshed(tmp_path):
    sc = _create(tmp_path)
    workspace.remove_scenario(tmp_path, sc.id, ts=TS)
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)


def test_remove_is_idempotent(tmp_path):
    sc = _create(tmp_path)
    workspace.remove_scenario(tmp_path, sc.id, ts=TS)
    workspace.remove_scenario(tmp_path, sc.id, ts=TS)
    assert workspace.list_scenarios(tmp_path, observed=OBSERVED) == []


def test_status_of_a_removed_scenario_cannot_be_changed(tmp_path):
    sc = _create(tmp_path)
    workspace.remove_scenario(tmp_path, sc.id, ts=TS)
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.set_status(tmp_path, sc.id, "Reached", reason="到價", ts=TS)


def test_recreating_the_same_target_starts_a_fresh_lifecycle(tmp_path):
    """移除後再建立同一組合：新劇本自成生命週期，不被舊的移除事件遮蔽。"""
    a = _create(tmp_path)
    workspace.remove_scenario(tmp_path, a.id, ts=TS)
    b = _create(tmp_path)
    assert b.id != a.id      # 舊劇本檔還在，id 依既有規則讓位
    listed = workspace.list_scenarios(tmp_path, observed=OBSERVED)
    assert [s.id for s in listed] == [b.id]
