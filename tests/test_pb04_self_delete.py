"""PB-04（#296，Anonymous Public Beta）：`DELETE /api/me` 自助刪除
端點——HTTP 層端到端驗證。Storage 層的 `delete_owner()` 完整契約
（10 張資料表＋身份表清空、shared 表不動、跨 owner 隔離）由
`tests/test_storage_contract.py` 覆蓋；這裡只驗證 HTTP 邊界本身。
"""
from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(storage=None):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return TestClient(create_app(fetch=lambda symbol: snap, storage=storage),
                      base_url="https://testserver"), storage


def test_deleting_my_own_data_removes_the_scenario_i_created():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    assert len(storage.list_owners()) == 1

    resp = c.delete("/api/me")

    assert resp.status_code == 204
    assert storage.list_owners() == []


def test_the_old_cookie_gets_a_fresh_empty_identity_on_the_next_request():
    """刪除後那顆舊 cookie 還留在瀏覽器裡，但它指向的身份已經被清空
    ——下一次請求走既有 lazy-creation 路徑，拿到一個全新、空的身份，
    而不是報錯或卡死。"""
    c, storage = _client()
    old_token = None
    r = c.post("/api/scenarios", json=NEW)
    r.raise_for_status()
    old_token = c.cookies.get(_OWNER_COOKIE_NAME)
    assert old_token

    c.delete("/api/me").raise_for_status()

    listed = c.get("/api/scenarios").json()
    assert listed == []
    new_token = c.cookies.get(_OWNER_COOKIE_NAME)
    assert new_token != old_token   # 拿到一顆全新的 cookie
    assert len(storage.list_owners()) == 1   # 舊的沒了，只有這個新的


def test_deleting_my_own_data_does_not_touch_another_owner():
    storage = MemoryStorage()
    snap = load_snapshot(FIX)
    app = create_app(fetch=lambda symbol: snap, storage=storage)
    c1 = TestClient(app, base_url="https://testserver")
    c2 = TestClient(app, base_url="https://testserver")

    c1.post("/api/scenarios", json={**NEW, "symbol": "AAA"}).raise_for_status()
    c2.post("/api/scenarios", json={**NEW, "symbol": "BBB"}).raise_for_status()

    c1.delete("/api/me").raise_for_status()

    assert [r["symbol"] for r in c2.get("/api/scenarios").json()] == ["BBB"]


def test_delete_endpoint_does_not_accept_a_caller_supplied_owner_id():
    """安全邊界：body／query 帶任何 owner_id 字樣都不該被理會——這個
    端點本來就沒有宣告接受它，FastAPI 對多餘的 body 欄位預設忽略，
    這條測試把這個『看起來像沒做防護、實則結構上不存在攻擊面』的事實
    釘成一條可執行的回歸線。"""
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    my_owner = storage.list_owners()[0].owner_id

    resp = c.request("DELETE", "/api/me", json={"owner_id": "someone-else"})

    assert resp.status_code == 204
    # 真的刪掉的是呼叫者自己（cookie 解析出的身份），不是 body 裡那個字串
    assert storage.get_owner(my_owner) is None
    assert storage.get_owner("someone-else") is None   # 本來就不存在，也不會被憑空建立


def test_deleting_with_no_prior_data_is_still_a_clean_204():
    c, storage = _client()
    c.get("/api/scenarios")   # lazy-create 一個空身份

    resp = c.delete("/api/me")

    assert resp.status_code == 204


def test_overriding_identity_resolver_still_deletes_the_injected_identity():
    """DI 覆寫路徑（既有 test_scale06／test_scale11 依賴的模式）不受
    cookie 機制影響——`delete_my_data()` 直接呼叫
    `identity_resolver()`，覆寫時一樣正確運作。"""
    snap = load_snapshot(FIX)
    storage = MemoryStorage()
    app = create_app(fetch=lambda symbol: snap, storage=storage,
                     identity_resolver=lambda: "alice")
    c = TestClient(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    assert storage.list_scenarios(owner="alice") != []

    resp = c.delete("/api/me")

    assert resp.status_code == 204
    assert storage.list_scenarios(owner="alice") == []
