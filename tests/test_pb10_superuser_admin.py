"""PB-10（#301，Anonymous Public Beta）：Super User system/admin
operations——跨 owner 檢視與管理 ＋ 高風險操作二次確認 ＋ audit trail。

正式執行 SUPERUSER-007 對舊 OD-6 的 supersede（spec #291 v3 §6）：
Super User 是 Normal User 完整權限超集合，本票落地的能力包括查看其他
owner 的資料、刪除他人資料（含批次）、runtime 設定／取消 `protected`
lifecycle 旗標。每一項高風險操作皆有伺服器端可驗證的二次確認
（`confirm_owner_id`／`confirm_owner_ids` 必須逐字等於目標，前端 modal
只是 UX、不是護欄本身）＋ audit trail（獨立於 `diagnostics`／`events`，
`tests/test_storage_contract.py` 已涵蓋其儲存層契約——不被 200 筆
diagnostics 上限沖掉、`delete_owner()` 不清除自己的紀錄——本檔案只驗證
HTTP 邊界＋接線）。

走既有第 1 個接縫（HTTP API）。`base_url="https://testserver"` 比照
`test_pb02_cookie_identity.py`／`test_pb09_superuser.py` 既有慣例，
讓 Secure cookie 在同一個 client 的多次請求之間正確 round-trip。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ProviderCredential
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
ADMIN_SECRET = "the-real-admin-secret"
ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN_SECRET}"}


def _client(*, storage=None, headers=None):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return TestClient(
        create_app(fetch=lambda symbol: snap, storage=storage,
                  admin_secret=ADMIN_SECRET),
        base_url="https://testserver", headers=headers or {}), storage


def _owner_client(storage):
    """建立一個走正常 cookie 流程的一般使用者 client——不帶
    `ADMIN_SECRET`，第一次打任何 owner-scoped 端點就會 lazy-create
    一個新 owner。"""
    c, _ = _client(storage=storage)
    return c


def _admin_client(storage):
    """建立一個帶著有效 `ADMIN_SECRET` 的 Super User client——刻意
    不覆寫 `identity_resolver`（走真實 cookie 流程），驗證軸二不影響
    軸一：這個 client 自己也會有一個 owner_id，但它操作的是**其他人**
    的 owner_id（透過路徑參數傳入），不是自己的。"""
    c, _ = _client(storage=storage, headers=ADMIN_AUTH)
    return c


# ---------- 跨 owner 檢視 ----------


def test_superuser_can_list_every_owner_across_the_site():
    storage = MemoryStorage()
    _owner_client(storage).post("/api/scenarios", json=NEW).raise_for_status()
    _owner_client(storage).post("/api/scenarios", json=NEW).raise_for_status()
    assert len(storage.list_owners()) == 2

    admin = _admin_client(storage)
    r = admin.get("/api/superuser/owners")
    assert r.status_code == 200
    ids = {o["owner_id"] for o in r.json()}
    assert ids == {o.owner_id for o in storage.list_owners()}


def test_superuser_can_view_another_owners_scenario_list_and_detail():
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    created = owner_c.post("/api/scenarios", json=NEW).json()
    owner_c.post(f"/api/scenarios/{created['id']}/refresh").raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    rows = admin.get(f"/api/superuser/owners/{owner_id}/scenarios").json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "XYZ"

    detail = admin.get(
        f"/api/superuser/owners/{owner_id}/scenarios/{created['id']}").json()
    assert detail["symbol"] == "XYZ"
    # Super User 看到的內容與該 owner 自己看到的一致（同一份投影）：
    own_detail = owner_c.get(f"/api/scenarios/{created['id']}").json()
    assert detail["latest_result"] == own_detail["latest_result"]


def test_superuser_scenario_detail_requires_matching_owner_and_scenario():
    """明確傳入目標 owner_id（票面 §8：不得靠傳 `None` 繞過
    `require_owner()`）——用另一個 owner 的 id 去查這個 scenario_id，
    404，不會意外洩漏或誤配對到別人的資料。"""
    storage = MemoryStorage()
    a = _owner_client(storage)
    created = a.post("/api/scenarios", json=NEW).json()
    a_owner_id = [o.owner_id for o in storage.list_owners()][0]
    b = _owner_client(storage)
    b.post("/api/scenarios", json=NEW).raise_for_status()
    b_owner_id = next(o.owner_id for o in storage.list_owners()
                      if o.owner_id != a_owner_id)

    admin = _admin_client(storage)
    r = admin.get(
        f"/api/superuser/owners/{b_owner_id}/scenarios/{created['id']}")
    assert r.status_code == 404


def test_pure_browsing_does_not_record_any_audit_entries():
    """票面 §3「純瀏覽不強制」的明確選擇：列出全部 owner／某 owner
    的劇本清單／單一劇本內容，這三種純讀取動作都不寫入 audit trail
    ——不然每一次查閱都會製造噪音，卻不帶來任何額外可稽核性。"""
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    created = owner_c.post("/api/scenarios", json=NEW).json()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    admin.get("/api/superuser/owners")
    admin.get(f"/api/superuser/owners/{owner_id}/scenarios")
    admin.get(f"/api/superuser/owners/{owner_id}/scenarios/{created['id']}")

    assert admin.get("/api/superuser/audit-log").json() == []


# ---------- Normal User 一律被拒 ----------


_CROSS_OWNER_ROUTES = [
    ("GET", "/api/superuser/owners"),
    ("GET", "/api/superuser/owners/anyone/scenarios"),
    ("GET", "/api/superuser/owners/anyone/scenarios/whatever"),
    ("POST", "/api/superuser/owners/anyone/delete"),
    ("POST", "/api/superuser/owners/batch-delete"),
    ("PUT", "/api/superuser/owners/anyone/protected"),
    ("GET", "/api/superuser/audit-log"),
]


def _call(client, method, path):
    if method == "GET":
        return client.get(path)
    if method == "POST":
        return client.post(path, json={"confirm_owner_id": "anyone",
                                       "owner_ids": ["anyone"],
                                       "confirm_owner_ids": ["anyone"]})
    if method == "PUT":
        return client.put(path, json={"protected": True,
                                      "confirm_owner_id": "anyone"})
    raise AssertionError(method)


def test_normal_user_is_rejected_from_every_new_superuser_endpoint():
    c, _ = _client()
    for method, path in _CROSS_OWNER_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code} {r.text}"


def test_a_wrong_secret_is_rejected_from_every_new_superuser_endpoint_too():
    c, _ = _client(headers={"Authorization": "Bearer definitely-not-it"})
    for method, path in _CROSS_OWNER_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


# ---------- 高風險：刪除他人全部資料（含二次確認＋audit） ----------


def test_superuser_can_delete_another_owners_data_with_correct_confirmation():
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    r = admin.post(f"/api/superuser/owners/{owner_id}/delete",
                   json={"confirm_owner_id": owner_id})
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    assert body["counts"]["scenarios"] == 1
    assert storage.get_owner(owner_id) is None


def test_delete_without_matching_confirmation_is_rejected_and_deletes_nothing():
    """伺服器端可驗證的二次確認真的生效——略過前端 modal、直接打 API
    但帶錯 `confirm_owner_id`，應被拒絕（票面 §8／AC）。"""
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    r = admin.post(f"/api/superuser/owners/{owner_id}/delete",
                   json={"confirm_owner_id": "not-the-right-owner"})
    assert r.status_code == 400
    assert storage.get_owner(owner_id) is not None
    assert admin.get("/api/superuser/audit-log").json() == []


def test_delete_without_a_confirmation_field_at_all_is_rejected():
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    r = admin.post(f"/api/superuser/owners/{owner_id}/delete", json={})
    assert r.status_code == 422
    assert storage.get_owner(owner_id) is not None


def test_batch_delete_requires_the_confirmation_set_to_match_exactly():
    storage = MemoryStorage()
    _owner_client(storage).post("/api/scenarios", json=NEW).raise_for_status()
    _owner_client(storage).post("/api/scenarios", json=NEW).raise_for_status()
    owner_ids = [o.owner_id for o in storage.list_owners()]
    assert len(owner_ids) == 2

    admin = _admin_client(storage)
    # 只確認了其中一個——部分確認不放行任何一個。
    r = admin.post("/api/superuser/owners/batch-delete",
                   json={"owner_ids": owner_ids,
                        "confirm_owner_ids": owner_ids[:1]})
    assert r.status_code == 400
    assert len(storage.list_owners()) == 2

    r = admin.post("/api/superuser/owners/batch-delete",
                   json={"owner_ids": owner_ids, "confirm_owner_ids": owner_ids})
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted"]) == sorted(owner_ids)
    assert storage.list_owners() == []
    # 每個目標各自一筆 audit 紀錄——不是把兩個目標塞進同一筆。
    audit = admin.get("/api/superuser/audit-log").json()
    assert len(audit) == 2
    assert {e["target_owner_id"] for e in audit} == set(owner_ids)


# ---------- 高風險：runtime protected 旗標（含二次確認＋audit） ----------


def test_superuser_can_toggle_protected_with_correct_confirmation():
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    r = admin.put(f"/api/superuser/owners/{owner_id}/protected",
                  json={"protected": True, "confirm_owner_id": owner_id})
    assert r.status_code == 200
    assert r.json() == {"owner_id": owner_id, "protected": True}
    assert storage.get_owner(owner_id).protected is True

    r = admin.put(f"/api/superuser/owners/{owner_id}/protected",
                  json={"protected": False, "confirm_owner_id": owner_id})
    assert r.status_code == 200
    assert storage.get_owner(owner_id).protected is False


def test_setting_protected_on_a_nonexistent_owner_is_404():
    storage = MemoryStorage()
    admin = _admin_client(storage)
    r = admin.put("/api/superuser/owners/never-existed/protected",
                  json={"protected": True, "confirm_owner_id": "never-existed"})
    assert r.status_code == 404


def test_setting_protected_without_matching_confirmation_is_rejected():
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]

    admin = _admin_client(storage)
    r = admin.put(f"/api/superuser/owners/{owner_id}/protected",
                  json={"protected": True, "confirm_owner_id": "wrong"})
    assert r.status_code == 400
    assert storage.get_owner(owner_id).protected is False


# ---------- Audit trail：誰／對誰／做了什麼／何時 ----------


def test_audit_log_records_who_what_target_and_when_for_high_risk_actions():
    storage = MemoryStorage()
    owner_a = _owner_client(storage)
    owner_a.post("/api/scenarios", json=NEW).raise_for_status()
    owner_b = _owner_client(storage)
    owner_b.post("/api/scenarios", json=NEW).raise_for_status()
    owner_ids = [o.owner_id for o in storage.list_owners()]
    a_id, b_id = owner_ids[0], owner_ids[1]

    admin = _admin_client(storage)
    admin.put(f"/api/superuser/owners/{a_id}/protected",
             json={"protected": True, "confirm_owner_id": a_id}).raise_for_status()
    admin.post(f"/api/superuser/owners/{b_id}/delete",
              json={"confirm_owner_id": b_id}).raise_for_status()

    audit = admin.get("/api/superuser/audit-log").json()
    assert len(audit) == 2
    # 最新在最上：delete 是後做的，應排在前面。
    assert audit[0]["action"] == "delete_owner"
    assert audit[0]["actor"] == "superuser"
    assert audit[0]["target_owner_id"] == b_id
    assert audit[0]["ts"]
    assert audit[1]["action"] == "set_owner_protected"
    assert audit[1]["target_owner_id"] == a_id
    assert audit[1]["detail"] == {"protected": True}


def test_audit_log_never_contains_a_credential_token_in_plaintext():
    """`delete_owner()` 一併清掉目標 owner 的 `owner_credentials`，
    但 audit `detail` 只放列數，即使真的有 token 存在也不會外洩到
    audit trail（也不會外洩到這個端點的 HTTP 回應本身）。"""
    storage = MemoryStorage()
    owner_c = _owner_client(storage)
    owner_c.post("/api/scenarios", json=NEW).raise_for_status()
    [owner_id] = [o.owner_id for o in storage.list_owners()]
    storage.save_credential(ProviderCredential(
        provider="marketdata_app", token="super-secret-token-value",
        updated_at="2026-09-14T00:00:00+00:00", owner_id=owner_id))

    admin = _admin_client(storage)
    admin.post(f"/api/superuser/owners/{owner_id}/delete",
              json={"confirm_owner_id": owner_id}).raise_for_status()

    r = admin.get("/api/superuser/audit-log")
    assert "super-secret-token-value" not in r.text
