"""SCALE-06（#256，Scaling Foundation Ownership A-1 Expand）：5 張
row-scoped 表的 owner_id 純加法擴充＋可注入的 identity resolver。

`api_app/storage/__init__.py`／`memory.py`／`postgres.py` 的欄位存在、
round-trip、backfill 冪等性由 `tests/test_storage_contract.py` 的
「Ownership A-1 Expand」區塊覆蓋（兩個後端都跑）。這裡專注在
`create_app()` 這一層的接線——identity resolver 有沒有真的被寫進新
資料、可不可以注入、以及 AC-3／AC-4 這兩條跟「production 行為不變」
直接相關的斷言。

## AC 對照

- AC-1／AC-2：見 `test_storage_contract.py`
- AC-3：`test_default_identity_resolver_is_solo_owner_end_to_end`／
  `test_owner_id_never_appears_in_any_http_response_body`（後者是
  「production 行為逐位元不變」字面意義的落地——今天任何 HTTP 回應
  都不含 `owner_id`，這一票加了欄位不代表這一票也改了任何一個回應
  形狀）
- AC-4：`test_scenarios_created_under_different_identities_are_all_
  visible_in_the_unfiltered_list`
- AC-5：見 `test_storage_contract.py`
- AC-6：全套既有測試套件本身
"""
from contextlib import contextmanager

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(*, identity_resolver=None, storage=None):
    snap = load_snapshot(FIX)
    kwargs = {}
    if identity_resolver is not None:
        kwargs["identity_resolver"] = identity_resolver
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(), **kwargs))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_default_identity_resolver_is_solo_owner_end_to_end():
    """production 預設（未覆寫 `identity_resolver`）下，一個劇本從建立
    到刷新，全部 5 張表的新寫入都標成同一個固定 `"solo"`。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert r.status_code == 200, r.text
    analyzed_at = r.json()["latest_analyzed_at"]

    assert storage.get_scenario(sc["id"]).owner_id == "solo"
    assert storage.latest_result(sc["id"]).owner_id == "solo"
    assert storage.get_snapshot_owner(sc["id"], analyzed_at) == "solo"
    events = storage.list_events(scenario_id=sc["id"])
    assert len(events) >= 2   # SCENARIO_CREATED + ANALYSIS_COMPLETED
    assert all(e["owner_id"] == "solo" for e in events)


def test_identity_resolver_is_injectable_and_new_writes_carry_it():
    """AC-3：可注入——換一個回傳別的值的 resolver，新寫入立刻改用它，
    不需要動 `main.py` 任何一行程式碼。"""
    storage = MemoryStorage()
    c = _client(identity_resolver=lambda: "alice", storage=storage)
    sc = _create(c)
    r = c.post(f"/api/scenarios/{sc['id']}/refresh")
    analyzed_at = r.json()["latest_analyzed_at"]

    assert storage.get_scenario(sc["id"]).owner_id == "alice"
    assert storage.latest_result(sc["id"]).owner_id == "alice"
    assert storage.get_snapshot_owner(sc["id"], analyzed_at) == "alice"
    events = storage.list_events(scenario_id=sc["id"])
    assert all(e["owner_id"] == "alice" for e in events)


def test_archive_restore_edit_events_also_carry_the_resolved_owner():
    """AC-2「新寫入都有 owner」不是只有建立與分析兩條路徑——封存／
    還原／編輯各自的事件記錄也要有。"""
    storage = MemoryStorage()
    c = _client(identity_resolver=lambda: "bob", storage=storage)
    sc = _create(c)

    c.patch(f"/api/scenarios/{sc['id']}", json={**NEW, "target_price": 140.0})
    c.post(f"/api/scenarios/{sc['id']}/archive")
    c.post(f"/api/scenarios/{sc['id']}/restore")

    events = {e["event"]: e["owner_id"]
             for e in storage.list_events(scenario_id=sc["id"])}
    assert events["SCENARIO_CREATED"] == "bob"
    assert events["SCENARIO_EDITED"] == "bob"
    assert events["SCENARIO_ARCHIVED"] == "bob"
    assert events["SCENARIO_RESTORED"] == "bob"


def test_editing_a_scenario_does_not_change_its_own_owner_id():
    """`update_scenario()` 不動 `owner_id`（設計決策，見
    `test_storage_contract.py::test_updating_a_scenario_does_not_
    touch_its_owner_id`）——這裡從 HTTP 層再驗一次同一條規則：即使
    「現在解析出來的身分」變了，已存在的劇本本身的 owner 依然不變
    （沒有任何機制會回頭改寫既有列的 owner_id，只有 `backfill_
    missing_owner_ids()` 這個明確、獨立的操作才會）。"""
    storage = MemoryStorage()
    resolver_calls = {"who": "alice"}
    c = _client(identity_resolver=lambda: resolver_calls["who"], storage=storage)
    sc = _create(c)
    assert storage.get_scenario(sc["id"]).owner_id == "alice"

    resolver_calls["who"] = "carol"   # 之後的 request 換了身分
    c.patch(f"/api/scenarios/{sc['id']}", json={**NEW, "target_price": 140.0})

    # 劇本自己的 owner_id 沒被編輯動過，還是原本建立時的那個。
    assert storage.get_scenario(sc["id"]).owner_id == "alice"
    # 但這次編輯留下的事件，記的是「這次 request」的身分。
    events = {e["event"]: e["owner_id"]
             for e in storage.list_events(scenario_id=sc["id"])}
    assert events["SCENARIO_EDITED"] == "carol"


def test_owner_id_never_appears_in_any_http_response_body():
    """AC-3「預設 solo-owner 下 production 行為逐位元不變」的字面
    落地：`owner_id` 是純粹的儲存層標記，不該在這一票裡悄悄變成 wire
    contract 的一部分——清單、詳細頁、建立回應都不該看得到這個字。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert "owner_id" not in sc
    assert "owner_id" not in c.get(f"/api/scenarios/{sc['id']}").json()
    (row,) = c.get("/api/scenarios").json()
    assert "owner_id" not in row


def test_scenarios_created_under_different_identities_are_all_visible_in_the_unfiltered_list():
    """AC-4：本票結束時查詢仍未加過濾——即使兩個劇本被不同的
    identity resolver 值標記，清單端點依然兩個都回，不會因為
    `owner_id` 不同就互相看不到彼此（那是 SCALE-11 才會做的事）。"""
    storage = MemoryStorage()
    c_alice = _client(identity_resolver=lambda: "alice", storage=storage)
    c_bob = _client(identity_resolver=lambda: "bob", storage=storage)

    _create(c_alice, symbol="AAA")
    _create(c_bob, symbol="BBB")

    symbols_seen_by_alice = {r["symbol"] for r in c_alice.get("/api/scenarios").json()}
    symbols_seen_by_bob = {r["symbol"] for r in c_bob.get("/api/scenarios").json()}
    assert symbols_seen_by_alice == {"AAA", "BBB"}
    assert symbols_seen_by_bob == {"AAA", "BBB"}


def test_the_middleware_actually_wraps_every_request_in_an_owner_scope(monkeypatch):
    """`diagnostics.owner_scope()`／`current_owner_id()` 本身的行為由
    `tests/test_diagnostics.py` 逐一驗證過；這裡只證明
    `_request_scope_middleware` 真的把它接上了——用一個記錄呼叫參數的
    假 `owner_scope`，確認每次真實 HTTP request 都會用
    `identity_resolver()` 當下的回傳值呼叫它一次。這樣即使
    `main.py::create_scenario()` 等端點日後改成透過
    `diagnostics.current_owner_id()`（而非直接呼叫 `identity_
    resolver()`）取得 owner，這條測試依然抓得住 middleware 這一層
    有沒有被拔掉。"""
    from api_app import diagnostics as diagnostics_module

    calls: list = []
    real_owner_scope = diagnostics_module.owner_scope

    @contextmanager
    def _spy_owner_scope(owner_id=None):
        calls.append(owner_id)
        with real_owner_scope(owner_id) as v:
            yield v

    monkeypatch.setattr(diagnostics_module, "owner_scope", _spy_owner_scope)

    c = _client(identity_resolver=lambda: "erin")
    _create(c)
    c.get("/api/scenarios")

    assert calls == ["erin", "erin"]   # 兩次 request，各自進了一次 scope
