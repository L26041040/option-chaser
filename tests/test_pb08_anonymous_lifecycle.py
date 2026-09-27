"""PB-08（#300，Anonymous Public Beta）：`last_activity_at` 語意＋
三段式生命週期（Active → Abandoned → Eligible for hard delete）＋
`GET /api/cron/cleanup-abandoned-owners`。

## AC 對照

- 純函式（`api_app.anonymous_lifecycle.classify()`）：
  `test_classify_*` 系列——三個狀態的邊界、`last_activity_at` 為
  `None` 時退回 `created_at`、無法解析的時間戳保守回 `"active"`。
- 六類真人操作各自把 `last_activity_at` 往前推：
  `test_creating_a_scenario_touches_activity` 等六條。
- **票面最強調的風險**——自動觸發的刷新不得算 activity：
  `test_auto_refresh_does_not_touch_activity`／
  `test_refresh_run_without_manual_does_not_touch_activity`。
- `protected` 的 owner 結構性排除在清理查詢之外：
  `test_protected_owner_survives_even_when_long_overdue`。
- 完整三段式生命週期走過一輪、真的透過 cron 端點觸發清除：
  `test_full_lifecycle_active_then_abandoned_then_hard_deleted`。
- 真人操作把 Abandoned／Grace 重新拉回 Active：
  `test_a_human_action_resets_an_abandoned_owner_back_to_active`。
- 天數／批次上限皆可經 `create_app()` DI 調整：貫穿全部生命週期測試
  （皆刻意傳極短天數才測得出邊界，本身就是這條 AC 的證明）。
- cron 端點 fail-closed（比照既有 `cron_warm_rate_cache` 慣例）：
  `test_missing_secret_is_401_and_deletes_nothing`／
  `test_wrong_secret_is_401_and_deletes_nothing`。
- 缺 cookie 打這個端點不會建立新 owner（`/api/cron/*` 既有排除清單，
  PB-02）：`test_cron_endpoint_itself_never_creates_an_owner`。
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_app.anonymous_lifecycle import classify
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from api_app.storage import Owner
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
AUTH = {"Authorization": "Bearer test-cron-secret"}


def _client(storage=None, **kwargs):
    """比照 `test_pb04_self_delete.py` 既有寫法：**不**覆寫
    `identity_resolver`，讓 production 真正的 cookie 流程建立 owner
    ——`_touch_activity()` 對不存在的 owner 安靜無效，用固定字串
    （例如 `identity_resolver=lambda: "solo"`）繞過 cookie 流程的話，
    `owners` 表永遠是空的，PB-08 要驗的東西完全測不到。"""
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    app = create_app(fetch=lambda symbol: snap, storage=storage,
                     cron_secret="test-cron-secret", **kwargs)
    return TestClient(app, base_url="https://testserver"), storage


def _set_last_seen(storage, owner_id: str, when: str) -> None:
    """把這個 owner 名下所有 browser identity 的 `last_seen_at` 設成
    `when`——SECURITY-FIX-01 起清理倒數的錨點就是它。"""
    for token, identity in list(storage._browser_identities.items()):
        if identity.owner_id == owner_id:
            storage.touch_browser_identity(token, now=when)


def _only_owner(storage) -> Owner:
    owners = storage.list_owners()
    assert len(owners) == 1
    return owners[0]


# ---------- 純函式：`classify()`（SECURITY-FIX-01：錨點＝last_seen_at） ----------

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
_DAYS = dict(retention_days=180, grace_period_days=7, empty_retention_days=1)


def _ago(days: float) -> str:
    return (_NOW - timedelta(days=days)).isoformat()


def test_classify_recent_visit_is_active():
    assert classify(last_seen_at=_ago(1), created_at=_ago(400), has_data=True,
                    now=_NOW, **_DAYS) == "active"


def test_classify_just_inside_retention_is_still_active():
    assert classify(last_seen_at=_ago(179), created_at=_ago(400), has_data=True,
                    now=_NOW, **_DAYS) == "active"


def test_classify_exactly_at_the_retention_threshold_is_abandoned():
    assert classify(last_seen_at=_ago(180), created_at=_ago(400), has_data=True,
                    now=_NOW, **_DAYS) == "abandoned"


def test_classify_within_the_grace_period_is_still_abandoned_not_deleted():
    assert classify(last_seen_at=_ago(184), created_at=_ago(400), has_data=True,
                    now=_NOW, **_DAYS) == "abandoned"


def test_classify_past_retention_plus_grace_is_eligible_for_hard_delete():
    assert classify(last_seen_at=_ago(187), created_at=_ago(400), has_data=True,
                    now=_NOW, **_DAYS) == "eligible_for_hard_delete"


def test_classify_falls_back_to_created_at_when_never_seen():
    """沒有任何 identity 列（例如合成壓測 owner）時退回 `created_at`。"""
    assert classify(last_seen_at=None, created_at=_ago(200), has_data=True,
                    now=_NOW, **_DAYS) == "eligible_for_hard_delete"


def test_classify_empty_owner_is_cleaned_after_one_day():
    assert classify(last_seen_at=_ago(0.5), created_at=_ago(3), has_data=False,
                    now=_NOW, **_DAYS) == "active"
    assert classify(last_seen_at=_ago(1), created_at=_ago(3), has_data=False,
                    now=_NOW, **_DAYS) == "eligible_for_hard_delete"


def test_classify_unparseable_timestamps_conservatively_stay_active():
    """分類失敗的後果不該是誤刪——讀不懂任一時間戳就保守回 `"active"`。"""
    assert classify(last_seen_at="not-a-timestamp", created_at="also-not-one",
                    has_data=True, now=_NOW, **_DAYS) == "active"


# ---------- 六類真人操作各自 touch activity ----------

def test_creating_a_scenario_touches_activity():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    assert _only_owner(storage).last_activity_at is not None


def test_editing_a_scenario_touches_activity():
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    owner_id = _only_owner(storage).owner_id
    # 回推到很久以前，證明編輯真的把它拉回現在，不是本來就有值。
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.patch(f"/api/scenarios/{created['id']}",
           json={"target_price": 999.0, "target_month": "2026-09",
                 "strategies": ["vertical-spread"]}).raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


def test_manual_single_scenario_refresh_touches_activity():
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.post(f"/api/scenarios/{created['id']}/refresh?manual=true").raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


def test_manual_refresh_run_touches_activity():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.post("/api/scenarios/refresh-run", json={"manual": True}).raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


def test_archiving_touches_activity():
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.post(f"/api/scenarios/{created['id']}/archive").raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


def test_restoring_touches_activity():
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    c.post(f"/api/scenarios/{created['id']}/archive").raise_for_status()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.post(f"/api/scenarios/{created['id']}/restore").raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


def test_permanently_deleting_touches_activity():
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    c.post(f"/api/scenarios/{created['id']}/archive").raise_for_status()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.delete(f"/api/scenarios/{created['id']}").raise_for_status()

    assert storage.get_owner(owner_id).last_activity_at != "2000-01-01T00:00:00+00:00"


# ---------- 票面最強調的風險：自動觸發不算 activity ----------

def test_auto_refresh_does_not_touch_activity():
    """單一劇本刷新端點省略 `manual`（預設 `False`）——`App.tsx` 內部
    `runBatch()` 的失敗隔離 fallback 走的正是這條路徑，不該把它算成
    真人操作。"""
    c, storage = _client()
    created = c.post("/api/scenarios", json=NEW).raise_for_status().json()
    owner_id = _only_owner(storage).owner_id
    assert storage.get_owner(owner_id).last_activity_at is not None  # 建立本身已算一次

    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")
    c.post(f"/api/scenarios/{created['id']}/refresh").raise_for_status()  # 無 manual

    assert storage.get_owner(owner_id).last_activity_at == "2000-01-01T00:00:00+00:00"


def test_refresh_run_without_manual_does_not_touch_activity():
    """開站自動觸發的整輪刷新（前端 `manual=false`，或乾脆省略）不算
    活動——這是 spec §7 點名『若也算，任何被背景分頁或搜尋引擎打開過
    的 owner 都會永遠不過期，清理機制形同虛設』的那個風險。"""
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(owner_id, now="2000-01-01T00:00:00+00:00")

    c.post("/api/scenarios/refresh-run", json={}).raise_for_status()  # manual 省略＝False

    assert storage.get_owner(owner_id).last_activity_at == "2000-01-01T00:00:00+00:00"


# ---------- protected owner 結構性排除 ----------

def test_protected_owner_survives_even_when_long_overdue():
    c, storage = _client(anonymous_retention_days=1, anonymous_grace_period_days=1)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner = _only_owner(storage)
    storage.set_owner_protected(owner.owner_id, True)
    # 遠遠超過 retention(1) + grace(1) = 2 天——若沒被 protected 濾掉，
    # 這個 owner 會被判定為 eligible_for_hard_delete 並真的被刪掉。
    _set_last_seen(
        storage, owner.owner_id, (datetime.now(timezone.utc) - timedelta(days=365)).isoformat())

    resp = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    # protected 在進入分類判斷之前就被濾掉——不會被計進 owners_checked，
    # 也不會被算進 abandoned／hard_deleted 任何一項。
    assert body["owners_checked"] == 0
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner.owner_id) is not None   # 資料原封不動還在


# ---------- 完整三段式生命週期 ----------

def test_full_lifecycle_active_then_abandoned_then_hard_deleted():
    """用極短天數（1 天 abandoned＋1 天 grace）真正走過整條生命週期，
    透過 cron 端點本身觸發，不是直接呼叫純函式模擬。"""
    c, storage = _client(anonymous_retention_days=1, anonymous_grace_period_days=1)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    now = datetime.now(timezone.utc)

    # 階段一：剛剛才活動過——仍是 active，cron 不動它。
    _set_last_seen(storage, owner_id, now.isoformat())
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 0
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner_id) is not None

    # 階段二：1.5 天前——超過 retention_days(1)，未過 grace(+1)。
    _set_last_seen(storage, owner_id, (now - timedelta(days=1, hours=12)).isoformat())
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 1
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner_id) is not None   # 還在，只是被標記 abandoned（衍生、不落盤）

    # 階段三：2.5 天前——超過 retention_days(1) + grace_period_days(1)。
    _set_last_seen(storage, owner_id, (now - timedelta(days=2, hours=12)).isoformat())
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 0
    assert body["hard_deleted"] == 1
    assert body["rows_deleted"] > 0
    assert storage.get_owner(owner_id) is None   # 真的被刪了
    assert storage.list_owners() == []


def test_any_visit_resets_an_abandoned_owner_back_to_active():
    """SECURITY-FIX-01：abandoned／grace 不是不可逆的——任何帶有效 cookie
    的回訪（**就算只是打開來看**，沒有任何建立／編輯／手動刷新）都把
    `last_seen_at` 拉回現在，下一次 cron 掃描時落回 `"active"`。"""
    c, storage = _client(anonymous_retention_days=1, anonymous_grace_period_days=1)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    now = datetime.now(timezone.utc)

    _set_last_seen(storage, owner_id, (now - timedelta(days=1, hours=12)).isoformat())
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 1

    c.get("/api/scenarios").raise_for_status()          # 純讀取的回訪

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 0
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner_id) is not None


def test_passive_viewer_is_never_deleted_by_the_old_manual_activity_rule():
    """這次要修的資料遺失：劇本建好後只打開來看的人，`last_activity_at`
    停在一年前，但每天都有回訪——預設天數下絕不能被清掉。"""
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    storage.touch_owner_activity(
        owner_id, now=(datetime.now(timezone.utc) - timedelta(days=365)).isoformat())

    c.get("/api/scenarios").raise_for_status()
    c.post("/api/scenarios/refresh-run", json={"scenario_ids": None, "manual": False})

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 0
    assert body["abandoned"] == 0
    assert len(storage.list_scenarios(owner=owner_id)) == 1


# ---------- cron 端點本身：fail-closed 授權＋不建立 owner ----------

def test_missing_secret_is_401_and_deletes_nothing():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    _set_last_seen(
        storage, owner_id, (datetime.now(timezone.utc) - timedelta(days=365)).isoformat())

    resp = c.get("/api/cron/cleanup-abandoned-owners")   # 沒帶 Authorization

    assert resp.status_code == 401
    assert storage.get_owner(owner_id) is not None


def test_wrong_secret_is_401_and_deletes_nothing():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    _set_last_seen(
        storage, owner_id, (datetime.now(timezone.utc) - timedelta(days=365)).isoformat())

    resp = c.get("/api/cron/cleanup-abandoned-owners",
                headers={"Authorization": "Bearer wrong-secret"})

    assert resp.status_code == 401
    assert storage.get_owner(owner_id) is not None


def test_cron_endpoint_itself_never_creates_an_owner():
    """`/api/cron/*` 早在 PB-02 的排除清單內——查詢營運狀態這件事本身
    不該幫呼叫端（Vercel Cron，沒有瀏覽器 cookie 可言）建立一個永遠
    不會再被用到的 owner。"""
    c, storage = _client()
    assert storage.list_owners() == []

    resp = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH)

    assert resp.status_code == 200
    assert storage.list_owners() == []
    assert _OWNER_COOKIE_NAME not in resp.cookies


# ---------- Cleanup volume 被記錄（spec §7／§22 AC5） ----------

def test_cleanup_volume_is_recorded_as_a_metric_not_only_in_the_response():
    """AC 明文要求『cleanup volume 有被記錄』——不是只回在這次 HTTP
    回應裡就算數。`METRIC_CATALOGUE` 因此有意識擴為八類（見
    `api_app/metrics.py`）。"""
    c, storage = _client(anonymous_retention_days=1, anonymous_grace_period_days=1)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = _only_owner(storage).owner_id
    _set_last_seen(
        storage, owner_id, (datetime.now(timezone.utc) - timedelta(days=365)).isoformat())

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 1

    entries = [e for e in storage.metric_summary()
              if e.metric == "abandoned_owner_cleanup_count"]
    assert len(entries) == 1
    assert entries[0].count == 1              # 這次刪掉一個 owner
    assert entries[0].total > 0                # 加總刪掉的資料列數 > 0


def test_a_run_that_cleans_nothing_still_records_a_zero_valued_metric():
    """每次執行都記一筆（含 0）——『今天 cron 有沒有真的跑過』本身也是
    有價值的訊號（PB-11 的每日摘要信）。"""
    c, storage = _client()
    c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).raise_for_status()

    entries = [e for e in storage.metric_summary()
              if e.metric == "abandoned_owner_cleanup_count"]
    assert len(entries) == 1
    assert entries[0].count == 0
    assert entries[0].total == 0.0


# ---------- 批次上限：超過單批的候選跨多次 cron 觸發全部處理到，
# 不遺漏不重複 ----------

def test_owners_beyond_one_batch_are_all_processed_across_repeated_cron_hits():
    c, storage = _client(anonymous_retention_days=1, anonymous_grace_period_days=1,
                         anonymous_cleanup_batch_size=1)
    very_old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    for symbol in ("AAA", "BBB", "CCC"):   # symbol 只准英文字母（見驗證規則）
        cc, _ = _client(storage=storage, anonymous_retention_days=1,
                        anonymous_grace_period_days=1, anonymous_cleanup_batch_size=1)
        cc.post("/api/scenarios", json={**NEW, "symbol": symbol}).raise_for_status()
    owner_ids = [o.owner_id for o in storage.list_owners()]
    assert len(owner_ids) == 3
    for oid in owner_ids:
        _set_last_seen(storage, oid, very_old)

    total_hard_deleted = 0
    for _ in range(3):   # 批次上限 1，三次呼叫恰好處理完全部三個
        body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
        assert body["batch_size"] <= 1
        total_hard_deleted += body["hard_deleted"]

    assert total_hard_deleted == 3   # 三個都被處理到，沒有遺漏、沒有重複
    assert storage.list_owners() == []
