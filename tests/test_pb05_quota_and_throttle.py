"""PB-05（#297，Anonymous Public Beta）：per-owner 成本煞車。

兩件事、各自獨立：
1. **額度**——每個 owner 最多 `ANONYMOUS_MAX_ACTIVE_SCENARIOS`
   （預設 10）個**未封存**劇本，第 N+1 個建立請求被拒（4xx，非 500）。
2. **節流**——同一 scenario 在 `ANONYMOUS_REFRESH_MIN_INTERVAL_
   MINUTES`（預設 30）分鐘內再次刷新不會真的發起 vendor fetch，
   沿用既有資料（`stage`／`ok` 皆與一次正常成功刷新無法區分）。

⚠ 節流**不是第四種 Refresh Trigger**——本檔案測試因此只走既有兩個
刷新端點（`POST /api/scenarios/{id}/refresh`／`POST /api/scenarios/
refresh-run`），沒有新增任何觸發面；`test_refresh_capable_routes_
are_still_exactly_the_existing_two` 直接對路由表做結構性驗證。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

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
        # PB-05 節流讀的是 `analyzed_at`（＝快照的 `fetched_at`）——
        # 真實 `cboe.py::fetch_chain()` 每次呼叫都蓋成 `datetime.now(...)`
        # （production 行為）。固定 fixture 檔案本身的 `fetched_at` 是
        # 早就寫死的歷史日期，逐位元原樣回傳的話，節流窗判斷會永遠讀到
        # 一個相對「現在」早已過期的時間戳，測不出節流真正生效——這裡
        # 每次呼叫都蓋成「剛剛」，才與 production 抓取行為一致。
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


def _old_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _backdate(storage: MemoryStorage, scenario_id: str, *, owner: str,
             minutes: int) -> None:
    """把某個 scenario 落盤的 `analyzed_at` 撥到 `minutes` 分鐘前——
    直接複用已由一次真實刷新產生、欄位完整的 `ResultRecord`（`dataclasses.
    replace()`），不手刻一份可能漏欄位的假紀錄（比照
    `tests/test_scale16_ledger_split.py` 既有 `save_current_result
    (dataclasses.replace(rec, ...))` 手法）。"""
    rec = storage.latest_result(scenario_id, owner=owner)
    assert rec is not None, "backdate 前必須已經有一次成功結果"
    updated = dataclasses.replace(rec, analyzed_at=_old_iso(minutes))
    storage.save_current_result(updated)


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


# ---------- 節流：單一劇本刷新 ----------

def test_a_never_analyzed_scenario_is_not_throttled():
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    r = c.post(f"/api/scenarios/{sid}/refresh")
    assert r.status_code == 200
    assert calls == ["XYZ"]


def test_refresh_within_the_throttle_window_does_not_call_fetch():
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]

    r1 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r1.status_code == 200
    assert len(calls) == 1
    first_analyzed_at = r1.json()["latest_analyzed_at"]

    r2 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r2.status_code == 200
    assert len(calls) == 1   # 窗內：沒有再打一次
    assert r2.json()["latest_analyzed_at"] == first_analyzed_at


def test_refresh_outside_the_throttle_window_calls_fetch_again():
    calls: list[str] = []
    storage = MemoryStorage()
    c = _client(storage=storage, fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    _backdate(storage, sid, owner="solo", minutes=40)   # 超過預設 30 分鐘窗

    r = c.post(f"/api/scenarios/{sid}/refresh")
    assert r.status_code == 200
    assert len(calls) == 2   # 窗外了，真的再抓一次


def test_throttle_can_be_disabled_via_di():
    calls: list[str] = []
    c = _client(fetch_calls=calls, anonymous_refresh_min_interval_minutes=0)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 2


def test_throttle_window_is_configurable():
    """5 分鐘窗：4 分鐘前抓過的仍節流，6 分鐘前抓過的不節流——證明
    真的在讀分鐘數，不是寫死 30。"""
    calls: list[str] = []
    storage = MemoryStorage()
    c = _client(storage=storage, fetch_calls=calls,
               anonymous_refresh_min_interval_minutes=5)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    _backdate(storage, sid, owner="solo", minutes=4)
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1   # 4 分鐘 < 5 分鐘窗，仍節流

    _backdate(storage, sid, owner="solo", minutes=6)
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 2   # 6 分鐘 > 5 分鐘窗，真的再抓


# ---------- 節流：refresh-run（批次） ----------

def test_refresh_run_when_the_whole_group_is_throttled_makes_zero_fetch_calls():
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1
    before = c.get(f"/api/scenarios/{sid}").json()["latest_analyzed_at"]

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid]})
    assert r.status_code == 200
    assert len(calls) == 1   # refresh-run 完全沒有再打上游
    body = r.json()
    assert body["remaining"] == []
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["ok"] is True   # 沿用既有資料＝成功，不是失敗
    assert "stage" not in result
    assert result["row"]["latest_analyzed_at"] == before


def test_refresh_run_with_omitted_scenario_ids_is_also_throttled():
    """`scenario_ids` 省略＝「開站」／「頂部按鈕」兩個既有 Trigger 實際
    呼叫的形狀（`CONTEXT.md`）——這條走的是與上面測試不同的 `targets`
    來源分支（`list_scenarios(owner=...)` 而非逐一查找），但兩者共用
    同一段 `groups`／`needs_chain` 邏輯，這裡直接證明省略時一樣受節流
    約束，不必逐一為每個 Trigger 的呼叫形狀各寫一份重複的斷言。"""
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    r = c.post("/api/scenarios/refresh-run", json={})
    assert r.status_code == 200
    assert len(calls) == 1   # 省略 scenario_ids 一樣不會再打


def test_refresh_run_a_throttled_solo_group_is_indistinguishable_from_a_normal_success():
    """對呼叫端（`runBatch()`）而言，節流短路與一次正常成功刷新必須是
    同一種回應形狀——這正是「不會自我製造 retry storm」的結構性保證：
    沒有任何欄位可以讓前端把它辨認成一次失敗。"""
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid]})
    result = r.json()["results"][0]
    assert set(result.keys()) == {"scenario_id", "ok", "row"}


def test_refresh_run_with_a_non_throttled_sibling_still_fetches_once_but_the_throttled_scenario_keeps_its_old_data():
    calls: list[str] = []
    storage = MemoryStorage()
    c = _client(storage=storage, fetch_calls=calls)
    sid_a = _create(c, symbol="XYZ").json()["id"]
    sid_b = _create(c, symbol="XYZ", target_price=131.0).json()["id"]

    # 兩個都還沒分析過，第一次一起刷新：ADR-0001 同組共用一次抓取。
    c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid_a, sid_b]})
    assert len(calls) == 1
    a_after_first = c.get(f"/api/scenarios/{sid_a}").json()["latest_analyzed_at"]

    # 只把 b 撥到窗外；a 維持窗內（節流中）。
    _backdate(storage, sid_b, owner="solo", minutes=40)
    b_backdated = storage.latest_result(sid_b, owner="solo").analyzed_at

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid_a, sid_b]})
    assert len(calls) == 2   # 為了 b（非節流手足）而多抓一次
    results = {x["scenario_id"]: x for x in r.json()["results"]}
    # a 全程節流中——即使這次組內確實抓了一份新 Chain（為了 b），
    # a 完全沒有用到它，資料逐位元不變。
    assert results[sid_a]["row"]["latest_analyzed_at"] == a_after_first
    # b 沒被節流，吃到剛抓的新資料——跟它自己的舊（被撥到 40 分鐘前）
    # 時間戳比較，不跟 a 比較：`now_utc_iso()` 只到秒級精度，兩次
    # refresh-run 若剛好落在同一秒，跟 a 比較會巧合相等而非真的測到
    # 節流生效，跟自己的陳舊時間戳比較才不受這個巧合影響。
    assert results[sid_b]["row"]["latest_analyzed_at"] != b_backdated


def test_refresh_run_a_throttled_group_fetch_failure_does_not_report_as_the_throttled_scenarios_failure():
    """組內某個非節流手足導致的抓取失敗，不該連坐節流中的 scenario——
    它本來就不會消費這份 Chain，這次失敗與它無關。"""
    calls: list[str] = []
    storage = MemoryStorage()
    c = _client(storage=storage, fetch_calls=calls)
    sid_a = _create(c, symbol="XYZ").json()["id"]
    sid_b = _create(c, symbol="XYZ", target_price=131.0).json()["id"]
    c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid_a, sid_b]})
    a_after_first = c.get(f"/api/scenarios/{sid_a}").json()["latest_analyzed_at"]
    _backdate(storage, sid_b, owner="solo", minutes=40)   # 只有 b 不節流

    from option_chaser.models import FetchError

    def _always_fails(symbol: str):
        calls.append(symbol)
        raise FetchError("vendor 掛了")

    c2 = TestClient(create_app(identity_resolver=lambda: "solo",
                               fetch=_always_fails, storage=storage))
    r = c2.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid_a, sid_b]})
    results = {x["scenario_id"]: x for x in r.json()["results"]}
    # b（非節流、真的想抓）確實回報失敗。
    assert results[sid_b]["ok"] is False
    assert results[sid_b]["stage"] == "fetch"
    # a（節流中）完全不受這次失敗影響——照樣是成功、資料不變。
    assert results[sid_a]["ok"] is True
    assert results[sid_a]["row"]["latest_analyzed_at"] == a_after_first


# ---------- config 化：環境變數也是有效來源，不只 DI ----------

def test_max_active_scenarios_can_be_set_via_environment_variable(monkeypatch):
    monkeypatch.setenv("ANONYMOUS_MAX_ACTIVE_SCENARIOS", "2")
    # 不傳 `anonymous_max_active_scenarios`（維持 `None`）——讓
    # `create_app()` 走 `_env_int()` 那一支，不是 DI 顯式覆寫那一支。
    c = _client()
    assert _create(c, symbol=_sym(0)).status_code == 201
    assert _create(c, symbol=_sym(1)).status_code == 201
    assert _create(c, symbol=_sym(2)).status_code >= 400


def test_refresh_min_interval_minutes_can_be_set_via_environment_variable(monkeypatch):
    monkeypatch.setenv("ANONYMOUS_REFRESH_MIN_INTERVAL_MINUTES", "0")
    calls: list[str] = []
    c = _client(fetch_calls=calls)
    sid = _create(c).json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 2   # 環境變數把節流設成 0＝停用


# ---------- 結構性：不是第四種 Refresh Trigger ----------

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
