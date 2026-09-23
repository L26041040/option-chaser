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


def test_reports_active_count_and_effective_quota():
    client = _client(anonymous_max_active_scenarios=5)
    _create(client, symbol="AAA")
    _create(client, symbol="BBB")

    r = client.get("/api/me/usage-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_scenarios"] == 2
    assert body["max_active_scenarios"] == 5
    assert body["quota_exempt"] is False


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


def test_super_user_and_super_admin_are_exempt_from_quota():
    """AUTH-05（#312）：`role >= Role.SUPERUSER` 豁免 quota——跟
    `create_scenario()` 既有豁免門檻同一個判準。

    SW-10（#340，Owner 真機驗收）：這條原本也斷言 `throttle_exempt`
    ——節流本身已經整段移除，那個回應欄位也跟著刪除，這裡只留 quota
    這一半仍然成立的斷言。"""
    storage = MemoryStorage()
    client = _client(storage=storage)

    for role in ("superuser", "superadmin"):
        body = client.get("/api/me/usage-summary",
                          cookies=role_cookies(storage, role)).json()
        assert body["quota_exempt"] is True, role


def test_normal_role_is_not_exempt():
    client = _client()
    body = client.get("/api/me/usage-summary").json()
    assert body["quota_exempt"] is False


def test_best_return_is_null_when_nothing_has_ever_analyzed_successfully():
    client = _client()
    body = client.get("/api/me/usage-summary").json()
    assert body["best_return"] is None
    assert body["best_return_symbol"] is None
    assert body["best_return_strategy"] is None
    assert body["best_return_target_month"] is None


def test_best_return_reports_the_scenario_with_the_highest_return():
    """SW-10（#340，Owner 真機驗收）：Artifact A 首頁 stats 板第二格
    「最佳劇本報酬」——建立本身不分析（`create_scenario()` 回應
    `best_return=None`，見其註解），真正的結果來自既有 Refresh
    Trigger 之一（這裡用單一劇本刷新端點）。兩個劇本刻意用不同
    `target_price`（110／120，經驗證對這份 fixture 分別產生 -1.0／
    1.0，非同分平手）而非只換 `symbol`——`fetch=` 對任何 symbol 都
    回傳同一份快照，同分時「哪個算贏」會退化成依賴 `list_scenarios()`
    迭代順序的巧合斷言。這裡不假造一筆結果，直接讀兩個真劇本各自的
    `best_return`，斷言 usage-summary 回報的是兩者裡較高的那一個，
    數字、標的、策略、目標年月四項都對得上同一個 `representative_
    candidate`，不是四個各自獨立算出來、恰好對得上的巧合。"""
    client = _client()
    a = _create(client, symbol="AAA", target_price=110.0, target_month="2026-09")
    b = _create(client, symbol="BBB", target_price=120.0, target_month="2026-09")
    client.post(f"/api/scenarios/{a['id']}/refresh").raise_for_status()
    client.post(f"/api/scenarios/{b['id']}/refresh").raise_for_status()

    detail_a = client.get(f"/api/scenarios/{a['id']}").json()
    detail_b = client.get(f"/api/scenarios/{b['id']}").json()
    winner = detail_a if detail_a["best_return"] >= detail_b["best_return"] else detail_b

    body = client.get("/api/me/usage-summary").json()
    assert body["best_return"] == winner["best_return"]
    assert body["best_return_symbol"] == winner["symbol"]
    assert (body["best_return_strategy"]
            == winner["representative_candidate"]["strategy"])
    assert body["best_return_target_month"] == winner["target_month"]


def test_best_return_excludes_archived_scenarios():
    """跟 `active_scenarios` 同一個「封存＝使用者主動整理，不該再影響
    首頁摘要」的既有原則——封存掉唯一有結果的劇本後，最佳報酬應該
    誠實回 `None`，不是繼續回報一個已經被丟進垃圾桶的劇本。"""
    client = _client()
    sc = _create(client)
    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    assert client.get("/api/me/usage-summary").json()["best_return"] is not None

    client.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()
    body = client.get("/api/me/usage-summary").json()
    assert body["best_return"] is None
    assert body["best_return_symbol"] is None


def test_quota_values_are_the_same_source_the_create_gate_actually_uses():
    """AC：「端點對 quota 設定值的來源與既有 create 閘門是同一份」——
    改一次設定值，兩邊（用量摘要回報的數字、真的擋人的 409）必須同步，
    不是各自讀出可能兜不起來的兩份答案。SW-10（#340）：節流（throttle）
    已經整段移除，這條測試原本也覆蓋 throttle 那一半，`/code-review`
    Standards 軸抓到函式名稱與 docstring 還留著「throttle」字樣但測試
    本體只剩 quota 斷言——這裡把名字與說明改回跟測試本體一致，不是
    弱化斷言範圍。"""
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
