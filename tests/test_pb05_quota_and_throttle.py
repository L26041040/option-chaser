"""PB-05（#297，Anonymous Public Beta）：per-owner 成本煞車。

原本兩件事、各自獨立：
1. **額度**——每個 owner 最多 `ANONYMOUS_MAX_ACTIVE_SCENARIOS`
   （預設 10）個**未封存**劇本，第 N+1 個建立請求被拒（4xx，非 500）。
2. ~~**節流**——同一 scenario 在 `ANONYMOUS_REFRESH_MIN_INTERVAL_
   MINUTES` 分鐘內再次刷新不會真的發起 vendor fetch。~~

SW-10（#340，Owner 真機驗收）：節流整段移除——「所有人都可以隨時按
重新整理」是 Owner 直接裁示，`api_app/main.py::_refresh_and_save()`
不再有這道短路。本檔案原本「節流：單一劇本刷新」「節流：refresh-run
（批次）」兩個小節、以及 config 化小節裡節流那一半的測試已整段刪除
——它們斷言的正是現在已經不存在的行為（例如「窗內不會再打一次」）。
額度（quota）本身完全不受這輪改動影響，相關測試原樣保留。
"""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from api_app.clock import now_utc_iso
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(*, storage=None, owner="solo", fetch_calls=None, **overrides):
    base_snap = load_snapshot(FIX)

    def _fetch(symbol: str):
        if fetch_calls is not None:
            fetch_calls.append(symbol)
        return dataclasses.replace(base_snap, fetched_at=now_utc_iso())

    return TestClient(create_app(
        identity_resolver=lambda: owner, fetch=_fetch,
        storage=storage or MemoryStorage(), **overrides))


def _create(client, **overrides):
    return client.post("/api/scenarios", json={**NEW, **overrides})


def _sym(i: int) -> str:
    """`_SYMBOL` 的驗證規則只准字母／`.`／`-`（見 `main.py`），不能用
    `f"SY{i}"` 這種帶數字的寫法（既有既有測試踩過的同一個坑）。"""
    return "SY" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i]


# ---------- 額度 ----------

def test_the_eleventh_active_scenario_is_rejected_not_500():
    c = _client()
    for i in range(10):
        assert _create(c, symbol=_sym(i)).status_code == 201
    r = _create(c, symbol="SYX")
    assert r.status_code != 500
    assert 400 <= r.status_code < 500
    assert "10" in r.json()["detail"]


def test_archiving_a_scenario_frees_a_quota_slot():
    c = _client()
    ids = [_create(c, symbol=_sym(i)).json()["id"] for i in range(10)]
    assert _create(c, symbol="SYX").status_code >= 400

    r = c.post(f"/api/scenarios/{ids[0]}/archive")
    assert r.status_code == 200

    assert _create(c, symbol="SYX").status_code == 201


def test_quota_is_scoped_per_owner_not_global():
    storage = MemoryStorage()
    alice = _client(storage=storage, owner="alice")
    bob = _client(storage=storage, owner="bob")
    for i in range(10):
        assert _create(alice, symbol=_sym(i)).status_code == 201
    assert _create(alice, symbol="SYX").status_code >= 400
    # bob 完全不受 alice 額度影響——額度綁在伺服器解析出的 owner_id，
    # 不是全站共用的一個計數器。
    assert _create(bob, symbol=_sym(0)).status_code == 201


def test_quota_can_be_disabled_via_di():
    c = _client(anonymous_max_active_scenarios=0)
    for i in range(11):
        assert _create(c, symbol=_sym(i)).status_code == 201


def test_extra_body_fields_cannot_bypass_the_quota():
    """`CreateScenarioRequest` 沒有 `owner_id`／額度相關欄位——pydantic
    預設丟棄未宣告的欄位，這裡把這個既有防線寫成可執行的回歸測試：
    client 傳什麼都不該能讓第 11 個劇本通過。"""
    c = _client()
    for i in range(10):
        assert _create(c, symbol=_sym(i)).status_code == 201
    r = _create(c, symbol="SYX", owner_id="somebody-else",
               anonymous_max_active_scenarios=999, bypass_quota=True)
    assert r.status_code >= 400
    assert r.status_code != 500


# ---------- 刷新一律真的再抓（節流整段移除後的 regression 守門） ----------

def test_a_never_analyzed_scenario_fetches():
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    r = c.post(f"/api/scenarios/{sid}/refresh")
    assert r.status_code == 200
    assert calls == ["XYZ"]


def test_refreshing_twice_in_a_row_fetches_again_the_second_time():
    """SW-10（#340，Owner 真機驗收）：這裡原本測的是「30 分鐘窗內第二次
    呼叫不會真的再抓」，節流整段移除後行為反過來——不論間隔多短，第二次
    呼叫一律真的再抓一次，`latest_analyzed_at` 因此也會跟著換成新的。"""
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]

    r1 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r1.status_code == 200
    assert len(calls) == 1

    r2 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r2.status_code == 200
    assert len(calls) == 2


def test_refresh_run_also_fetches_again_on_a_second_call():
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid]})
    assert r.status_code == 200
    assert len(calls) == 2
    body = r.json()
    assert body["remaining"] == []
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["ok"] is True
    assert set(result.keys()) == {"scenario_id", "ok", "row"}


def test_refresh_run_with_omitted_scenario_ids_also_fetches_again():
    """`scenario_ids` 省略＝「開站」／「頂部按鈕」兩個既有 Trigger 實際
    呼叫的形狀（`CONTEXT.md`）——這條走的是與上面測試不同的 `targets`
    來源分支（`list_scenarios(owner=...)` 而非逐一查找），這裡確認省略
    時一樣真的再抓一次，不必逐一為每個 Trigger 的呼叫形狀各寫一份
    重複的斷言。"""
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    r = c.post("/api/scenarios/refresh-run", json={})
    assert r.status_code == 200
    assert len(calls) == 2


# ---------- config 化：環境變數也是有效來源，不只 DI ----------

def test_max_active_scenarios_can_be_set_via_environment_variable(monkeypatch):
    monkeypatch.setenv("ANONYMOUS_MAX_ACTIVE_SCENARIOS", "2")
    # 不傳 `anonymous_max_active_scenarios`（維持 `None`）——讓
    # `create_app()` 走 `_env_int()` 那一支，不是 DI 顯式覆寫那一支。
    c = _client()
    assert _create(c, symbol=_sym(0)).status_code == 201
    assert _create(c, symbol=_sym(1)).status_code == 201
    assert _create(c, symbol=_sym(2)).status_code >= 400


# ---------- 結構性：刷新入口只有既有兩個 ----------

def test_refresh_capable_routes_are_still_exactly_the_existing_two():
    c = _client()
    refresh_routes = sorted(
        (route.path, tuple(sorted(route.methods)))
        for route in c.app.routes
        if "refresh" in getattr(route, "path", ""))
    assert refresh_routes == [
        ("/api/scenarios/refresh-run", ("POST",)),
        ("/api/scenarios/{scenario_id}/refresh", ("POST",)),
    ]
