"""ANTI-ABUSE-PROTOTYPE-001 Part A：用**真正的** `create_app()`（current
master）跑，證明現況行為——不是讀 code 推論。

隔離：MemoryStorage、假的 Cboe fetch、`https://testserver`。不連任何
資料庫、不打任何上游、不讀任何真實 secret。檔名刻意不是 `test_*.py`，
CI 的 `python -m pytest` 不會收進來；手動執行：

    PYTHONPATH=. .venv/bin/python -m pytest prototypes/anti_abuse/checks_current_master.py
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
AUTH = {"Authorization": "Bearer fake-cron-secret"}


def _scenario(symbol: str) -> dict:
    return {"symbol": symbol, "target_price": 130.0, "target_month": "2027-01",
            "strategies": ["vertical-spread"]}


class CountingCboe:
    """假的 Cboe 抓鏈：數它被叫了幾次。走 `cboe_fetch` 注入點而不是
    `fetch`——只有這條路徑會經過 `_metered_chain_fetch()`，
    `chain_fetch_count` 才會真的被記錄，global fuse 才量得到。"""

    def __init__(self):
        self.snap = load_snapshot(FIX)
        self.calls: list[str] = []

    def __call__(self, symbol: str):
        self.calls.append(symbol)
        return self.snap


def _app(**kwargs):
    storage = kwargs.pop("storage", None) or MemoryStorage()
    cboe = CountingCboe()
    app = create_app(cboe_fetch=cboe, storage=storage,
                     cron_secret="fake-cron-secret", **kwargs)
    return app, storage, cboe


def _full_refresh(client: TestClient, manual: bool) -> None:
    """照前端 `runBatch()` 的 Continuation：`remaining` 非空就接著打。"""
    ids = None
    while True:
        body = client.post("/api/scenarios/refresh-run",
                           json={"scenario_ids": ids, "manual": manual}).json()
        if not body["remaining"]:
            return
        ids = body["remaining"]


def _fresh_client(app) -> TestClient:
    """一個全新的瀏覽器：沒有任何 cookie。"""
    return TestClient(app, base_url="https://testserver")


# ---------- A1：owner identity 依賴什麼 ----------

def test_a1_every_cookieless_request_creates_a_new_owner():
    app, storage, _ = _app()
    for _ in range(5):
        _fresh_client(app).get("/api/scenarios").raise_for_status()
    assert len(storage.list_owners()) == 5


def test_a1_ip_plays_no_part_in_identity():
    """同一個 cookie 換 IP → 同一個 owner；同一個 IP 沒 cookie → 新 owner。"""
    app, storage, _ = _app()
    c = _fresh_client(app)
    c.post("/api/scenarios", json=_scenario("XYZ"),
           headers={"X-Forwarded-For": "203.0.113.1"}).raise_for_status()
    c.get("/api/scenarios", headers={"X-Forwarded-For": "198.51.100.9"})
    assert len(storage.list_owners()) == 1          # 換 IP、cookie 不變：同一人
    _fresh_client(app).get("/api/scenarios",
                           headers={"X-Forwarded-For": "203.0.113.1"})
    assert len(storage.list_owners()) == 2          # 同 IP、沒 cookie：新 owner


def test_a1_lost_cookie_orphans_scenarios_but_does_not_delete_them():
    app, storage, _ = _app()
    phone = _fresh_client(app)
    phone.post("/api/scenarios", json=_scenario("XYZ")).raise_for_status()
    old_owner = storage.list_owners()[0].owner_id

    phone.cookies.clear()                               # cookie 遺失
    assert phone.get("/api/scenarios").json() == []    # 「劇本消失了」
    assert len(storage.list_scenarios(owner=old_owner)) == 1   # 其實還在 DB


def test_a1_first_visit_fanout_creates_two_owners():
    """前端首次載入同時打兩個 owner-scoped GET（`App` 的清單＋
    `MobileStatsStrip` 的 usage-summary），兩個都還沒有 cookie——
    這裡用兩個獨立 client 模擬「同時送出、都沒帶 cookie」。"""
    app, storage, _ = _app()
    first = _fresh_client(app)
    second = _fresh_client(app)
    first.get("/api/scenarios")
    second.get("/api/me/usage-summary")
    assert len(storage.list_owners()) == 2              # 一個訪客 → 兩個 owner


# ---------- A2：cleanup 現況 ----------

def test_a2_passive_daily_user_is_hard_deleted_with_scenarios():
    """使用者建了劇本後每天只打開看（開站自動刷新、看詳細頁），沒有
    手動刷新／編輯——`last_activity_at` 停在建立那天。第 38 天 cron
    會把整個 owner（含劇本）刪掉，即使他昨天才打開過。預設天數。"""
    app, storage, cboe = _app()
    phone = _fresh_client(app)
    created = phone.post("/api/scenarios", json=_scenario("XYZ")).json()
    owner_id = storage.list_owners()[0].owner_id
    storage.touch_owner_activity(
        owner_id,
        now=(datetime.now(timezone.utc) - timedelta(days=38)).isoformat())

    # 今天：照常打開 app（前端開站實際會打的三個請求）
    phone.get("/api/scenarios").raise_for_status()
    _full_refresh(phone, manual=False)
    phone.get(f"/api/scenarios/{created['id']}").raise_for_status()

    body = phone.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["hard_deleted"] == 1
    assert storage.get_owner(owner_id) is None
    assert storage.list_scenarios(owner=owner_id) == []
    assert phone.get("/api/scenarios").json() == []     # 同一支手機：劇本沒了


# ---------- 成本面：現況沒有 per-owner vendor 上限 ----------

def test_cost_one_cookie_can_trip_the_global_fuse_for_everyone():
    """單一 owner、10 個不同 symbol 的劇本，連按刷新——每次 10 次上游。
    budget 設 100 讓它 10 輪就觸發；觸發後**另一個**無辜 owner 也抓不到。"""
    app, storage, cboe = _app(global_vendor_daily_budget=100)
    attacker = _fresh_client(app)
    for sym in "ABCDEFGHIJ":
        attacker.post("/api/scenarios", json=_scenario(f"Q{sym}")).raise_for_status()
    for _ in range(12):
        _full_refresh(attacker, manual=True)
    assert len(cboe.calls) == 100                       # 剛好燒到 budget 為止

    victim = _fresh_client(app)
    sc = victim.post("/api/scenarios", json=_scenario("AAPL")).json()
    r = victim.post(f"/api/scenarios/{sc['id']}/refresh")
    assert len(cboe.calls) == 100                       # 無辜者一次上游都拿不到
    assert r.status_code >= 400                         # 刷新失敗
    assert "vendor" in r.text or "預算" in r.text


def test_cost_legacy_analyze_endpoint_scans_any_symbol_without_scenarios():
    """`POST /api/analyze`（V1 遺留、前端已不呼叫）：不用建劇本、不受
    10 劇本額度限制，任意 symbol 一次一個上游呼叫，而且每次沒帶
    cookie 就多建一個 owner。"""
    app, storage, cboe = _app()
    for sym in ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN"]:
        _fresh_client(app).post("/api/analyze", json={
            "symbol": sym, "target_price": 100.0, "target_month": "2027-01",
            "strategies": ["bull-call-spread"]})
    assert cboe.calls == ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN"]
    assert len(storage.list_owners()) == 5
