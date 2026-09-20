"""OG-05（#324）：劇本庫 stats strip 的唯讀使用量摘要端點
`GET /api/me/usage-summary`，以及 `/api/ops/metrics` 新增的
`vendor_fuse`（Super Admin-only stats 方塊要用）。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from tests._role_session import role_cookies

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(storage=None, **overrides):
    snap = load_snapshot(FIX)
    return TestClient(create_app(
        identity_resolver=lambda: "solo", fetch=lambda symbol: snap,
        storage=storage or MemoryStorage(), **overrides))


def _create(client, **kw):
    r = client.post("/api/scenarios", json={**NEW, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_reports_active_count_and_effective_quota_throttle():
    client = _client(anonymous_max_active_scenarios=5,
                     anonymous_refresh_min_interval_minutes=7)
    _create(client, symbol="AAA")
    _create(client, symbol="BBB")

    r = client.get("/api/me/usage-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_scenarios"] == 2
    assert body["max_active_scenarios"] == 5
    assert body["refresh_min_interval_minutes"] == 7
    assert body["quota_exempt"] is False
    assert body["throttle_exempt"] is False


def test_archived_scenarios_do_not_count_as_active():
    """跟 `create_scenario()` 額度檢查同一個算法——封存本就是使用者
    主動整理，不該倒扣額度／灌水 active 數字。"""
    client = _client()
    sc = _create(client)
    client.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    assert client.get("/api/me/usage-summary").json()["active_scenarios"] == 0


def test_max_active_scenarios_null_when_quota_disabled():
    client = _client(anonymous_max_active_scenarios=0)
    body = client.get("/api/me/usage-summary").json()
    assert body["max_active_scenarios"] is None


def test_refresh_min_interval_null_when_throttle_disabled():
    client = _client(anonymous_refresh_min_interval_minutes=0)
    body = client.get("/api/me/usage-summary").json()
    assert body["refresh_min_interval_minutes"] is None


def test_super_user_and_super_admin_are_exempt_from_both():
    """AUTH-05（#312）：`role >= Role.SUPERUSER` 豁免 quota／throttle
    ——跟 `create_scenario()`／`_refresh_and_save()` 既有豁免門檻
    同一個判準。"""
    storage = MemoryStorage()
    client = _client(storage=storage)

    for role in ("superuser", "superadmin"):
        body = client.get("/api/me/usage-summary",
                          cookies=role_cookies(storage, role)).json()
        assert body["quota_exempt"] is True, role
        assert body["throttle_exempt"] is True, role


def test_normal_role_is_not_exempt():
    client = _client()
    body = client.get("/api/me/usage-summary").json()
    assert body["quota_exempt"] is False
    assert body["throttle_exempt"] is False


def test_quota_and_throttle_values_are_the_same_source_the_gates_actually_use():
    """AC：「端點對 quota／throttle 設定值的來源與既有 create／refresh
    閘門是同一份」——改一次設定值，兩邊（用量摘要回報的數字、真的擋人
    的 409）必須同步，不是各自讀出可能兜不起來的兩份答案。"""
    client = _client(anonymous_max_active_scenarios=1)
    _create(client, symbol="AAA")

    body = client.get("/api/me/usage-summary").json()
    assert body["max_active_scenarios"] == 1
    assert body["active_scenarios"] == 1

    # 額度已滿——第二個劇本真的被既有閘門擋下，證明上面回報的數字跟
    # 這個真正的判斷用的是同一份 `_effective_max_active_scenarios`。
    r = client.post("/api/scenarios", json={**NEW, "symbol": "BBB"})
    assert r.status_code == 409


def test_does_not_advance_last_activity():
    """票面 AC 明文、測試鎖住：查看自己的用量不算真人操作。

    比照既有 `tests/test_pb08_anonymous_lifecycle.py::_client()` 的
    既有寫法：**不**覆寫 `identity_resolver`，讓 production 真正的
    cookie 流程建立 owner——固定字串（例如 `identity_resolver=lambda:
    "solo"`）會繞過 cookie 流程，`owners` 表永遠是空的，`_touch_
    activity()` 對不存在的 owner 安靜無效，這個檔案其餘測試用的
    `"solo"` 因此測不出這條 AC。建立劇本會推進 `last_activity_at`
    （既有 `_touch_activity()` 呼叫點）——用它當一個非 `None` 的基準
    值，證明後續呼叫 `usage-summary`（不論呼叫幾次）都不會把它往前推。
    """
    snap = load_snapshot(FIX)
    client = TestClient(create_app(fetch=lambda symbol: snap, storage=MemoryStorage()),
                        base_url="https://testserver")
    _create(client)
    before = client.get("/api/me/usage-summary").json()["last_activity_at"]
    assert before is not None

    client.get("/api/me/usage-summary")
    client.get("/api/me/usage-summary")
    after = client.get("/api/me/usage-summary").json()["last_activity_at"]
    assert after == before


def test_brand_new_owner_has_null_last_activity_and_zero_active():
    """全新 owner（`Storage.get_owner()` 可能回 `None`——這張表本身
    是全新的，既有 `solo` owner 從未寫進去過）誠實回報預設值，不是
    拋錯或假造一筆活動紀錄。"""
    client = _client()
    body = client.get("/api/me/usage-summary").json()
    assert body["active_scenarios"] == 0
    assert body["last_activity_at"] is None


def test_response_never_contains_owner_id():
    """SCALE-06 既有不變量的延伸——這個端點是純加法，不得意外洩漏
    `owner_id`。"""
    client = _client()
    _create(client)
    assert "owner_id" not in client.get("/api/me/usage-summary").json()


def test_missing_role_cookie_behaves_like_a_normal_owner_scoped_endpoint():
    """這個端點不在 `_OWNER_EXEMPT_PREFIXES`／`_OWNER_EXEMPT_EXACT`
    清單裡——沒有角色 cookie 時走既有 Normal User 路徑，不是被擋在
    門外（跟 `DELETE /api/me`、`POST /api/scenarios` 同一種待遇）。"""
    client = _client()
    assert client.get("/api/me/usage-summary").status_code == 200


# ---------- /api/ops/metrics 的 `vendor_fuse`（Super Admin-only 方塊用）----------

def test_ops_metrics_reports_vendor_fuse_usage_against_the_real_budget():
    storage = MemoryStorage()
    client = _client(storage=storage, global_vendor_daily_budget=100)
    body = client.get("/api/ops/metrics",
                      cookies=role_cookies(storage, "superadmin")).json()
    assert body["vendor_fuse"] == {"used": 0, "budget": 100}


def test_ops_metrics_vendor_fuse_budget_is_null_when_disabled():
    storage = MemoryStorage()
    client = _client(storage=storage, global_vendor_daily_budget=0)
    body = client.get("/api/ops/metrics",
                      cookies=role_cookies(storage, "superadmin")).json()
    assert body["vendor_fuse"]["budget"] is None
