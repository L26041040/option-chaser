"""SCALE-11（#262，Scaling Foundation Ownership A-1 Enforce）：對
`scenarios`／`results`／`snapshots`／`events`／`diagnostics` 五張
row-scoped 表全面套用 owner query boundary 的端到端驗收。

SCALE-06（#256，見 `test_scale06_ownership_expand.py`）只加欄位、
backfill，刻意不查詢過濾；本檔案驗證的是「query boundary 真的
enforce 了」這件事本身——兩個注入不同 identity 的 `TestClient` 共用
同一個 `MemoryStorage`，逐一證明對方的資料互相看不到、改不到、刪
不到、刷新不到。

## AC 對照

- AC-1：`test_alice_cannot_*` 系列（detail／edit／archive／restore／
  delete／refresh 六個操作）逐一證明互不可見、互不可修改。
- AC-2：`test_alice_cannot_read_bobs_*` 系列（detail／history／
  raw-data／raw-data-csv／results／events／diagnostics）逐一證明
  猜到對方的 scenario_id 也讀不到資料——一律回應與「這個 id 根本不
  存在」相同的 404，不洩漏「存在，只是不是你的」這個事實。
- AC-3：`test_refresh_run_*` 系列——省略 `scenario_ids` 時只列舉呼叫
  者自己的未過期劇本；帶明確 id 時，猜到的對方 id 被靜默排除（不是
  出現在 remaining 或以錯誤形式出現，是完全不在 `results` 裡）。
- AC-4：solo-owner 模式維持逐位元不變由既有全套 HTTP 測試（皆使用
  預設 `identity_resolver`，全部落在同一個 `"solo"`）在同一次全套
  執行裡自然佐證——不必另開專屬測試。
- AC-5：見 `test_storage_contract.py`（結構性檢查，非 HTTP 層）。
- AC-6：全套 storage 契約測試（memory＋真實 Postgres）本身。
"""
from fastapi.testclient import TestClient

from api_app.diagnostics import DiagnosticEvent
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _clients(storage=None):
    """共用一份 storage、各自固定身分的一組 alice／bob TestClient——
    兩人建立資料的動作彼此獨立，讀寫是否互相看得到／改得到才是本檔案
    要驗證的事。"""
    storage = storage or MemoryStorage()
    snap = load_snapshot(FIX)
    c_alice = TestClient(create_app(fetch=lambda symbol: snap, storage=storage,
                                    identity_resolver=lambda: "alice"))
    c_bob = TestClient(create_app(fetch=lambda symbol: snap, storage=storage,
                                  identity_resolver=lambda: "bob"))
    return c_alice, c_bob, storage


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- AC-2：detail／history／raw-data／results／events／diagnostics ----------

def test_alice_cannot_read_bobs_scenario_detail():
    c_alice, c_bob, _storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.get(f"/api/scenarios/{bob_sc['id']}")
    assert resp.status_code == 404
    # 跟根本不存在的 id 是同一種訊息格式（同一個 `_require()` 分支）
    # ——不洩漏「這個 id 存在，只是不是你的」這個事實。
    assert resp.json() == {"detail": f"劇本不存在：{bob_sc['id']}"}


def test_alice_cannot_read_bobs_history():
    c_alice, c_bob, _storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")
    c_bob.post(f"/api/scenarios/{bob_sc['id']}/refresh")
    detail = c_bob.get(f"/api/scenarios/{bob_sc['id']}").json()
    candidate_key = next(iter(detail["latest_result"]["candidate_pool"]))

    resp = c_alice.get(f"/api/scenarios/{bob_sc['id']}/history",
                       params={"candidate_key": candidate_key})
    assert resp.status_code == 404


def test_alice_cannot_read_bobs_raw_data():
    c_alice, c_bob, _storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")
    c_bob.post(f"/api/scenarios/{bob_sc['id']}/refresh")

    assert c_alice.get(f"/api/scenarios/{bob_sc['id']}/raw-data").status_code == 404
    assert c_alice.get(f"/api/scenarios/{bob_sc['id']}/raw-data.csv").status_code == 404


def test_alice_cannot_read_bobs_results_index():
    c_alice, c_bob, _storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")
    c_bob.post(f"/api/scenarios/{bob_sc['id']}/refresh")

    resp = c_alice.get(f"/api/scenarios/{bob_sc['id']}/results")
    assert resp.status_code == 404


def test_alice_cannot_read_bobs_events():
    c_alice, c_bob, _storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.get(f"/api/scenarios/{bob_sc['id']}/events")
    assert resp.status_code == 404


def _seed_diagnostic(storage, *, event_id, owner_id):
    storage.append_diagnostic(DiagnosticEvent(
        event_id=event_id, correlation_id="c1", ts="2026-08-15T00:00:00+00:00",
        subsystem="historical_iv", stage="vendor_fetch", severity="error",
        user_facing=True, message="boom", context={}, owner_id=owner_id))


def test_diagnostics_are_isolated_between_owners():
    """`/api/diagnostics` 不像其餘端點掛在單一 scenario_id 上——直接
    種兩筆分屬不同 owner 的診斷事件（比照 `test_storage_contract.py`
    既有的 `_diag()` 直接建構慣例），驗證兩個 owner 各自只看得到自己
    的那筆。"""
    c_alice, c_bob, storage = _clients()
    _seed_diagnostic(storage, event_id="a1", owner_id="alice")
    _seed_diagnostic(storage, event_id="b1", owner_id="bob")

    alice_ids = {e["event_id"] for e in c_alice.get("/api/diagnostics").json()}
    bob_ids = {e["event_id"] for e in c_bob.get("/api/diagnostics").json()}
    assert alice_ids == {"a1"}
    assert bob_ids == {"b1"}


def test_clear_diagnostics_only_clears_the_callers_own():
    c_alice, c_bob, storage = _clients()
    _seed_diagnostic(storage, event_id="a1", owner_id="alice")
    _seed_diagnostic(storage, event_id="b1", owner_id="bob")

    resp = c_alice.delete("/api/diagnostics")
    assert resp.status_code == 200
    assert resp.json() == {"cleared": 1}

    assert storage.list_diagnostics(limit=200, owner="alice") == []
    # bob 的診斷事件完全不受 alice 清空自己那筆的影響。
    bob_after = storage.list_diagnostics(limit=200, owner="bob")
    assert [e.event_id for e in bob_after] == ["b1"]


# ---------- AC-1：edit／archive／restore／delete／refresh 互不可修改 ----------

def test_alice_cannot_edit_bobs_scenario():
    c_alice, c_bob, storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.patch(f"/api/scenarios/{bob_sc['id']}",
                         json={**NEW, "symbol": "BBB", "target_price": 999.0})
    assert resp.status_code == 404
    assert storage.get_scenario(bob_sc["id"], owner="bob").target_price == 130.0


def test_alice_cannot_archive_bobs_scenario():
    c_alice, c_bob, storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.post(f"/api/scenarios/{bob_sc['id']}/archive")
    assert resp.status_code == 404
    assert storage.get_scenario(bob_sc["id"], owner="bob").archived_at is None


def test_alice_cannot_restore_bobs_archived_scenario():
    c_alice, c_bob, storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")
    c_bob.post(f"/api/scenarios/{bob_sc['id']}/archive")
    archived_at = storage.get_scenario(bob_sc["id"], owner="bob").archived_at
    assert archived_at is not None

    resp = c_alice.post(f"/api/scenarios/{bob_sc['id']}/restore")
    assert resp.status_code == 404
    # 還在垃圾桶裡，沒被 alice 那次無效呼叫還原。
    assert storage.get_scenario(bob_sc["id"], owner="bob").archived_at == archived_at


def test_alice_cannot_delete_bobs_archived_scenario():
    c_alice, c_bob, storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")
    c_bob.post(f"/api/scenarios/{bob_sc['id']}/archive")

    resp = c_alice.delete(f"/api/scenarios/{bob_sc['id']}")
    assert resp.status_code == 404
    assert storage.get_scenario(bob_sc["id"], owner="bob") is not None


def test_alice_cannot_refresh_bobs_scenario():
    c_alice, c_bob, storage = _clients()
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.post(f"/api/scenarios/{bob_sc['id']}/refresh")
    assert resp.status_code == 404
    assert storage.latest_result(bob_sc["id"], owner="bob") is None


# ---------- AC-3：refresh-run 只涵蓋呼叫者自己的 scenarios ----------

def test_refresh_run_without_ids_only_targets_the_callers_own_scenarios():
    c_alice, c_bob, storage = _clients()
    alice_sc = _create(c_alice, symbol="AAA")
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.post("/api/scenarios/refresh-run", json={})
    assert resp.status_code == 200
    body = resp.json()
    touched_ids = {r["scenario_id"] for r in body["results"]}
    assert touched_ids == {alice_sc["id"]}
    assert alice_sc["id"] not in body["remaining"]
    assert bob_sc["id"] not in body["remaining"]
    # bob 的劇本完全沒被這次 alice 觸發的批次刷新碰過。
    assert storage.latest_result(bob_sc["id"], owner="bob") is None


def test_refresh_run_with_explicit_ids_silently_excludes_a_guessed_foreign_id():
    c_alice, c_bob, storage = _clients()
    alice_sc = _create(c_alice, symbol="AAA")
    bob_sc = _create(c_bob, symbol="BBB")

    resp = c_alice.post("/api/scenarios/refresh-run",
                        json={"scenario_ids": [alice_sc["id"], bob_sc["id"]]})
    assert resp.status_code == 200
    body = resp.json()
    touched_ids = {r["scenario_id"] for r in body["results"]}
    # 猜到的 bob id 完全不出現——不是失敗項、不是 remaining，是
    # 結構上沒被列進 targets（跟這個 id 根本不存在同一種待遇）。
    assert touched_ids == {alice_sc["id"]}
    assert bob_sc["id"] not in touched_ids
    assert bob_sc["id"] not in body["remaining"]
    assert storage.latest_result(bob_sc["id"], owner="bob") is None
