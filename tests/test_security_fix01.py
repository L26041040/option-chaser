"""SECURITY-FIX-01（Public Beta pre-launch hardening）：identity／lifecycle
correctness。

- deferred owner creation：讀取、404、首頁載入、usage-summary 都不建立
  owner；第一次真正持久化才建立，而且只建立一個（含並發首訪）。
- owner cookie 180 天、滑動續命。
- cleanup：錨點是 browser identity 的 last_seen_at；有資料 180＋7 天、
  空 owner 1 天；先判定再套批次上限（活躍的舊 owner 不再卡住清理）。
- `POST /api/analyze` 已不存在。

Sentry `request.data` 移除的測試在 `tests/test_observability.py`；
storage 層的並發綁定（真 Postgres、多執行緒）在
`tests/test_storage_contract.py`。
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
AUTH = {"Authorization": "Bearer fake-cron-secret"}
ONE_EIGHTY_DAYS = 180 * 24 * 60 * 60


def _app(storage=None, **kwargs):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    app = create_app(fetch=lambda symbol: snap, storage=storage,
                     cron_secret="fake-cron-secret", **kwargs)
    return app, storage


def _browser(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _set_last_seen(storage, owner_id: str, when: str) -> None:
    for token, identity in list(storage._browser_identities.items()):
        if identity.owner_id == owner_id:
            storage.touch_browser_identity(token, now=when)


def _metric(storage, name: str) -> int:
    return sum(e.count for e in storage.metric_summary() if e.metric == name)


# ---------- deferred owner creation ----------

def test_anonymous_read_only_first_visit_creates_no_owner():
    app, storage = _app()
    c = _browser(app)
    # 首頁載入實際會打的讀取（清單、usage-summary、設定、角色狀態）
    assert c.get("/api/scenarios").json() == []
    c.get("/api/me/usage-summary").raise_for_status()
    c.get("/api/settings").raise_for_status()
    c.get("/api/auth/status").raise_for_status()
    # 沒有劇本時前端不送 refresh-run；就算送了也是空的，不建 owner
    assert c.post("/api/scenarios/refresh-run",
                  json={"scenario_ids": None, "manual": False}).json() == {
        "results": [], "remaining": []}
    assert storage.list_owners() == []
    assert storage._browser_identities == {}


def test_usage_summary_creates_no_owner_and_reports_empty_usage():
    app, storage = _app()
    body = _browser(app).get("/api/me/usage-summary").json()
    assert body["active_scenarios"] == 0
    assert body["best_return"] is None
    assert storage.list_owners() == []


def test_404s_create_no_owner():
    app, storage = _app()
    c = _browser(app)
    assert c.get("/api/scenarios/does-not-exist").status_code == 404
    assert c.get("/api/definitely-not-a-route").status_code == 404
    assert c.post("/api/scenarios/does-not-exist/archive").status_code == 404
    assert storage.list_owners() == []


def test_first_persistent_action_creates_exactly_one_owner():
    app, storage = _app()
    c = _browser(app)
    c.get("/api/scenarios")
    c.get("/api/me/usage-summary")
    assert storage.list_owners() == []

    c.post("/api/scenarios", json=NEW).raise_for_status()
    c.post("/api/scenarios", json={**NEW, "symbol": "YYY"}).raise_for_status()

    owners = storage.list_owners()
    assert len(owners) == 1
    assert len(storage.list_scenarios(owner=owners[0].owner_id)) == 2
    assert _metric(storage, "new_owner_count") == 1


def test_concurrent_first_visit_then_create_yields_one_owner():
    """前端首訪同時送出多個沒帶 cookie 的讀取：沒有任何一個建立 owner、
    也沒有任何一個發 cookie。接著的第一次建立劇本才簽發並綁定 token
    ——只會有一個 owner。"""
    app, storage = _app()
    barrier = threading.Barrier(4)

    def first_read(path: str):
        barrier.wait()
        return _browser(app).get(path).cookies.get(_OWNER_COOKIE_NAME)

    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(first_read, ["/api/scenarios", "/api/me/usage-summary",
                                            "/api/settings", "/api/scenarios"]))
    assert tokens == [None] * 4
    assert storage.list_owners() == []

    r = _browser(app).post("/api/scenarios", json=NEW)
    assert r.status_code == 201
    assert r.cookies.get(_OWNER_COOKIE_NAME)
    assert len(storage.list_owners()) == 1


def test_a_slow_first_visit_read_cannot_overwrite_a_materialized_cookie():
    """Codex P1（PR #346）：首訪同時送出多個沒帶 cookie 的讀取；使用者在
    其中一個比較慢的讀取回來之前就建立了劇本。那個慢的回應**不得**帶一顆
    新的（未綁定的）token 覆蓋掉剛綁定的 cookie——否則剛建立的 owner 與
    劇本就再也存取不到。"""
    app, storage = _app()
    slow_read = _browser(app).get("/api/scenarios")      # 還在路上的首訪讀取
    created = _browser(app).post("/api/scenarios", json=NEW)
    assert created.status_code == 201
    jar = created.cookies.get(_OWNER_COOKIE_NAME)         # 瀏覽器現在持有的
    # 慢的回應這時才回到瀏覽器：它帶了什麼 Set-Cookie，瀏覽器就照單全收。
    jar = slow_read.cookies.get(_OWNER_COOKIE_NAME) or jar
    after = _browser(app).get("/api/scenarios",
                              headers={"Cookie": f"{_OWNER_COOKIE_NAME}={jar}"})
    assert [r["id"] for r in after.json()] == [created.json()["id"]]


def test_reads_without_a_bound_owner_set_no_owner_cookie():
    """沒有綁定 owner 的回應一律不發 owner cookie：只有「已綁定」或「這次
    請求剛綁定」的回應才會 `Set-Cookie`，所以任何還在路上的首訪回應都沒有
    東西可以覆蓋。"""
    app, storage = _app()
    for path in ("/api/scenarios", "/api/me/usage-summary", "/api/settings",
                 "/api/scenarios/nope"):
        r = _browser(app).get(path)
        assert _OWNER_COOKIE_NAME not in r.headers.get("set-cookie", ""), path
    stale = "s" * 43                                   # 形狀合法但沒綁定的舊 cookie
    r = _browser(app).get("/api/scenarios",
                          headers={"Cookie": f"{_OWNER_COOKIE_NAME}={stale}"})
    assert _OWNER_COOKIE_NAME not in r.headers.get("set-cookie", "")
    assert storage.list_owners() == []


def test_concurrent_first_persistent_actions_with_one_token_yield_one_owner():
    """同一顆還沒綁定的 token 同時送出多個建立請求（連點、或多個分頁）
    ——綁定靠 token PK 原子完成，只會有一個 owner，所有劇本都在它名下。"""
    app, storage = _app()
    token = "t" * 43                  # 形狀合法、還沒綁定（例如 owner 被清掉後的舊 cookie）
    barrier = threading.Barrier(6)

    def create(i: int) -> int:
        barrier.wait()
        return _browser(app).post(
            "/api/scenarios", json={**NEW, "symbol": "ABCDEF"[i]},
            headers={"Cookie": f"{_OWNER_COOKIE_NAME}={token}"}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(create, range(6)))

    assert statuses == [201] * 6
    owners = storage.list_owners()
    assert len(owners) == 1
    assert len(storage.list_scenarios(owner=owners[0].owner_id)) == 6
    assert _metric(storage, "new_owner_count") == 1


def test_valid_cookie_return_is_the_same_owner():
    app, storage = _app()
    c = _browser(app)
    created = c.post("/api/scenarios", json=NEW).json()
    owner_id = storage.list_owners()[0].owner_id
    assert [r["id"] for r in c.get("/api/scenarios").json()] == [created["id"]]
    c.post("/api/scenarios", json={**NEW, "symbol": "QQQ"}).raise_for_status()
    assert [o.owner_id for o in storage.list_owners()] == [owner_id]


def test_pending_visitors_never_see_each_others_data():
    app, storage = _app()
    writer = _browser(app)
    writer.post("/api/scenarios", json=NEW).raise_for_status()
    stranger = _browser(app)
    assert stranger.get("/api/scenarios").json() == []
    assert stranger.get("/api/me/usage-summary").json()["active_scenarios"] == 0


# ---------- cookie TTL ----------

def _max_age(response) -> int:
    header = response.headers["set-cookie"]
    part = next(p for p in header.split(";") if p.strip().lower().startswith("max-age="))
    return int(part.split("=")[1])


def test_owner_cookie_is_180_days_and_keeps_its_security_attributes():
    app, _ = _app()
    r = _browser(app).post("/api/scenarios", json=NEW)
    header = r.headers["set-cookie"]
    assert _max_age(r) == ONE_EIGHTY_DAYS
    assert header.startswith(f"{_OWNER_COOKIE_NAME}=")
    lowered = header.lower()
    assert "httponly" in lowered and "secure" in lowered
    assert "samesite=lax" in lowered and "path=/" in lowered
    assert "domain=" not in lowered


def test_owner_cookie_renewal_is_sliding():
    """每一次帶有效 cookie 的請求都重新簽 180 天（同一顆 token），不是
    固定從第一次簽發起算。"""
    app, storage = _app()
    c = _browser(app)
    first = c.post("/api/scenarios", json=NEW)
    token = first.cookies.get(_OWNER_COOKIE_NAME)
    again = c.get("/api/scenarios")
    assert again.cookies.get(_OWNER_COOKIE_NAME) == token
    assert _max_age(again) == ONE_EIGHTY_DAYS


def test_a_valid_cookie_return_updates_last_seen():
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = storage.list_owners()[0].owner_id
    _set_last_seen(storage, owner_id, _ago(100))

    c.get("/api/scenarios").raise_for_status()

    facts = {f.owner_id: f for f in storage.owner_lifecycle_facts()}
    seen = datetime.fromisoformat(facts[owner_id].last_seen_at)
    assert datetime.now(timezone.utc) - seen < timedelta(minutes=1)


# ---------- cleanup（預設天數：180＋7、空 owner 1） ----------

def test_owner_seen_within_180_days_is_not_deleted():
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = storage.list_owners()[0].owner_id
    _set_last_seen(storage, owner_id, _ago(179))
    storage.touch_owner_activity(owner_id, now=_ago(179))     # 舊規則下早就該刪

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 0
    assert storage.get_owner(owner_id) is not None


def test_owner_past_180_plus_grace_is_deleted_but_not_inside_grace():
    app, storage = _app()
    c = _browser(app)
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = storage.list_owners()[0].owner_id

    _set_last_seen(storage, owner_id, _ago(183))              # grace 期間
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["abandoned"] == 1 and body["hard_deleted"] == 0

    _set_last_seen(storage, owner_id, _ago(188))              # 超過 180+7
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 1
    assert storage.get_owner(owner_id) is None
    assert storage.list_scenarios(owner=owner_id) == []


def test_empty_owner_is_cleaned_quickly_and_counted_separately():
    """劇本建了又永久刪掉＝空 owner：一天沒回訪就清掉，記在
    `empty_owner_cleanup_count`；那顆 cookie 之後只是「還沒綁定」，
    下次建立時自然拿到新 owner。"""
    app, storage = _app()
    c = _browser(app)
    created = c.post("/api/scenarios", json=NEW).json()
    c.post(f"/api/scenarios/{created['id']}/archive").raise_for_status()
    c.delete(f"/api/scenarios/{created['id']}").raise_for_status()
    owner_id = storage.list_owners()[0].owner_id
    _set_last_seen(storage, owner_id, _ago(2))

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["empty_owners_deleted"] == 1
    assert storage.list_owners() == []
    assert _metric(storage, "empty_owner_cleanup_count") == 1
    assert _metric(storage, "abandoned_owner_cleanup_count") == 0

    c.post("/api/scenarios", json=NEW).raise_for_status()      # 同一個瀏覽器繼續用
    assert len(storage.list_owners()) == 1


def test_active_oldest_owners_do_not_block_eligible_cleanup():
    """最舊的 owner 全部都還活躍、批次上限只有 1——真正該清的那個（比較
    新）仍然在第一次 cron 就被清掉。舊寫法會永遠卡在最舊那幾個。"""
    app, storage = _app(anonymous_cleanup_batch_size=1)
    active_ids = []
    for symbol in ("AAA", "BBB", "CCC"):
        c = _browser(app)
        c.post("/api/scenarios", json={**NEW, "symbol": symbol}).raise_for_status()
        active_ids.append(storage.list_owners()[-1].owner_id)
    for oid in active_ids:                                     # 讓它們在排序上最舊
        storage._owners[oid] = storage._owners[oid].__class__(
            **{**storage._owners[oid].__dict__, "created_at": _ago(900)})

    victim = _browser(app)
    victim.post("/api/scenarios", json={**NEW, "symbol": "DDD"}).raise_for_status()
    victim_id = next(o.owner_id for o in storage.list_owners() if o.owner_id not in active_ids)
    _set_last_seen(storage, victim_id, _ago(400))

    body = _browser(app).get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["eligible"] == 1
    assert body["hard_deleted"] == 1
    assert storage.get_owner(victim_id) is None
    assert all(storage.get_owner(oid) is not None for oid in active_ids)


def test_protected_owner_is_never_cleaned_even_with_no_data_and_no_visits():
    app, storage = _app()
    c = _browser(app)
    created = c.post("/api/scenarios", json=NEW).json()
    c.post(f"/api/scenarios/{created['id']}/archive").raise_for_status()
    c.delete(f"/api/scenarios/{created['id']}").raise_for_status()
    owner_id = storage.list_owners()[0].owner_id
    storage.set_owner_protected(owner_id, True)
    _set_last_seen(storage, owner_id, _ago(2000))

    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["owners_checked"] == 0
    assert storage.get_owner(owner_id) is not None


# ---------- `/api/analyze` 退休 ----------

def test_legacy_analyze_endpoint_is_gone_and_creates_no_owner():
    app, storage = _app()
    r = _browser(app).post("/api/analyze", json={
        "symbol": "AAPL", "target_price": 100.0, "target_month": "2027-01",
        "strategies": ["bull-call-spread"]})
    assert r.status_code in (404, 405)
    assert storage.list_owners() == []
    assert not any(route.path == "/api/analyze" for route in app.routes)
