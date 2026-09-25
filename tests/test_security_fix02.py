"""SECURITY-FIX-02（Public Beta pre-launch hardening）：vendor 濫用防護。

全部用假的東西：假時鐘（不 sleep）、假 IP（TEST-NET 與文件保留段）、
假 HMAC secret、假角色密碼、假 Cboe 抓鏈（計數用，走 `cboe_fetch` 注入點
——只有這條路徑會被 `_metered_chain_fetch()` 計入 global fuse）。

邊界測試用的都是**正式預設值**（60／300／800、120／600、40%）：先把計數器
直接預填到「差一次就到上限」，再用真正的 HTTP 請求驗證最後一次放行、
下一次被擋——不必真的打幾百次 HTTP。
"""
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api_app import abuse_control as ac
from api_app import metrics
from api_app.clock import ny_today
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
SECRET = "fake-source-hmac-secret-for-tests"
SU_PW = "fake-superuser-password"
SA_PW = "fake-superadmin-password"
AUTH = {"Authorization": "Bearer fake-cron-secret"}
IP_A, IP_B = "203.0.113.10", "198.51.100.20"


class FakeClock:
    def __init__(self):
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CountingCboe:
    def __init__(self):
        self.snap = load_snapshot(FIX)
        self.calls = 0

    def __call__(self, symbol):
        self.calls += 1
        return self.snap


@pytest.fixture
def env():
    storage = MemoryStorage()
    clock = FakeClock()
    cboe = CountingCboe()
    app = create_app(cboe_fetch=cboe, storage=storage, clock=clock,
                     source_hmac_secret=SECRET, trusted_ip_header="x-forwarded-for",
                     superuser_password=SU_PW, superadmin_password=SA_PW,
                     cron_secret="fake-cron-secret")
    return app, storage, clock, cboe


def _browser(app, ip=IP_A) -> TestClient:
    return TestClient(app, base_url="https://testserver",
                      headers={"X-Forwarded-For": ip})


def _new_owner_with_scenario(app, storage, ip=IP_A):
    c = _browser(app, ip)
    sc = c.post("/api/scenarios", json=NEW).json()
    owner_id = storage.resolve_owner_by_token(c.cookies.get("__Host-oc_owner"))
    return c, sc["id"], owner_id


def _refresh(c, sid):
    return c.post(f"/api/scenarios/{sid}/refresh")


def _stage(r):
    return r.json()["detail"]["stage"]


def _seed(storage, scope, key, seconds, start, count):
    for _ in range(count):
        assert storage.rate_limit_consume(scope, key, [(seconds, start, 10**9)]) is None


def _metric(storage, name):
    return sum(e.count for e in storage.metric_summary() if e.metric == name)


def _age_owner(storage, owner_id, days):
    rec = storage._owners[owner_id]
    storage._owners[owner_id] = rec.__class__(**{
        **rec.__dict__, "created_at": ac.datetime.fromtimestamp(
            time.time() - days * 86400, ac.ZoneInfo("UTC")).isoformat()})


# ---------- per-owner quota（Normal：60／300／800） ----------

@pytest.mark.parametrize("seconds,limit", [(ac.MINUTE, 60), (ac.HOUR, 300), (ac.DAY, 800)])
def test_normal_owner_quota_boundaries(env, seconds, limit):
    app, storage, clock, cboe = env
    c, sid, owner = _new_owner_with_scenario(app, storage)
    _age_owner(storage, owner, 2)                    # 不讓 new-owner tier 干擾
    _seed(storage, "owner_vendor", owner, seconds,
          ac.window_start(clock(), seconds), limit - 1)

    assert _refresh(c, sid).status_code == 200       # 第 limit 次：放行
    calls = cboe.calls
    blocked = _refresh(c, sid)                        # 第 limit+1 次：擋
    assert blocked.status_code == 429
    assert _stage(blocked) == "usage_limited"
    assert cboe.calls == calls                        # 被擋的那次沒有打上游
    assert _metric(storage, "owner_quota_block_count") == 1


def test_owner_minute_quota_recovers_in_the_next_window(env):
    app, storage, clock, _ = env
    c, sid, owner = _new_owner_with_scenario(app, storage)
    _age_owner(storage, owner, 2)
    _seed(storage, "owner_vendor", owner, ac.MINUTE,
          ac.window_start(clock(), ac.MINUTE), 60)
    assert _refresh(c, sid).status_code == 429
    clock.advance(61)
    assert _refresh(c, sid).status_code == 200


@pytest.mark.parametrize("password", [SU_PW, SA_PW])
def test_superuser_and_superadmin_are_exempt_from_owner_quota(env, password):
    app, storage, clock, _ = env
    c, sid, owner = _new_owner_with_scenario(app, storage)
    assert c.post("/api/auth/login", json={"password": password}).status_code == 200
    for seconds, limit in ((ac.MINUTE, 60), (ac.HOUR, 300), (ac.DAY, 800)):
        _seed(storage, "owner_vendor", owner, seconds,
              ac.window_start(clock(), seconds), limit)
    assert _refresh(c, sid).status_code == 200


@pytest.mark.parametrize("password", [SU_PW, SA_PW])
def test_superuser_and_superadmin_still_hit_the_global_fuse(env, password):
    app, storage, _, cboe = env
    c, sid, _ = _new_owner_with_scenario(app, storage)
    c.post("/api/auth/login", json={"password": password}).raise_for_status()
    metrics.record(storage, "chain_fetch_count", ny_today(), count=2000)
    calls = cboe.calls
    r = _refresh(c, sid)
    assert r.status_code == 429
    assert _stage(r) == "vendor_budget_exhausted"
    assert cboe.calls == calls
    assert _metric(storage, "global_fuse_block_count") == 1


# ---------- source burst（120／分、600／時，沒有每日上限） ----------

@pytest.mark.parametrize("seconds,limit", [(ac.MINUTE, 120), (ac.HOUR, 600)])
def test_source_burst_boundaries(env, seconds, limit):
    app, storage, clock, _ = env
    key = ac.source_key(IP_A, SECRET, clock())
    _seed(storage, "source_vendor", key, seconds, ac.window_start(clock(), seconds), limit - 1)
    c1, sid1, o1 = _new_owner_with_scenario(app, storage, IP_A)
    _age_owner(storage, o1, 2)
    assert _refresh(c1, sid1).status_code == 200
    blocked = _refresh(c1, sid1)
    assert blocked.status_code == 429 and _stage(blocked) == "usage_limited"
    assert _metric(storage, "source_burst_block_count") == 1


def test_source_burst_has_no_daily_cap(env):
    """同一個來源連續三個小時都用到 599 次／時，一天累計遠超過 600，
    仍然每個小時都放行——source 層只抓短時間爆量。"""
    app, storage, clock, _ = env
    for _hour in range(3):
        key = ac.source_key(IP_A, SECRET, clock())
        _seed(storage, "source_vendor", key, ac.HOUR,
              ac.window_start(clock(), ac.HOUR), 599)
        c, sid, owner = _new_owner_with_scenario(app, storage, IP_A)
        _age_owner(storage, owner, 2)
        assert _refresh(c, sid).status_code == 200
        clock.advance(3600)


def test_source_burst_does_not_depend_on_the_owner_cookie(env):
    """刪 cookie、同一個來源：新 owner 照樣被同一個 source bucket 擋。"""
    app, storage, clock, _ = env
    key = ac.source_key(IP_A, SECRET, clock())
    _seed(storage, "source_vendor", key, ac.MINUTE,
          ac.window_start(clock(), ac.MINUTE), 120)
    for _ in range(3):                                # 三次「刪 cookie 重來」
        c, sid, owner = _new_owner_with_scenario(app, storage, IP_A)
        _age_owner(storage, owner, 2)
        r = _refresh(c, sid)
        assert r.status_code == 429 and _stage(r) == "usage_limited"
    other_source, sid2, o2 = _new_owner_with_scenario(app, storage, IP_B)
    _age_owner(storage, o2, 2)
    assert _refresh(other_source, sid2).status_code == 200


def test_changing_source_with_the_same_cookie_does_not_reset_owner_quota(env):
    app, storage, clock, _ = env
    c, sid, owner = _new_owner_with_scenario(app, storage, IP_A)
    _age_owner(storage, owner, 2)
    _seed(storage, "owner_vendor", owner, ac.DAY, ac.window_start(clock(), ac.DAY), 800)
    moved = TestClient(app, base_url="https://testserver",
                       headers={"X-Forwarded-For": IP_B}, cookies=c.cookies)
    r = _refresh(moved, sid)
    assert r.status_code == 429 and _stage(r) == "usage_limited"
    assert storage.resolve_owner_by_token(moved.cookies.get("__Host-oc_owner")) == owner


# ---------- new-owner tier（< 24h 的 owner 全體共用 fuse 的 40%） ----------

def test_new_owner_pool_is_forty_percent_of_the_global_fuse():
    assert ac.new_owner_tier_pool(2000, 0.4) == 800
    assert ac.new_owner_tier_pool(1000, 0.4) == 400
    assert ac.new_owner_tier_pool(0, 0.4) == 0         # fuse 停用＝tier 也停用


def test_rotating_cookie_and_source_is_bounded_by_the_new_owner_pool(env):
    app, storage, clock, cboe = env
    day, start = ac.ny_day_bounds(clock())
    _seed(storage, "new_owner_tier", day, ac.DAY, start, 799)
    c1, sid1, _ = _new_owner_with_scenario(app, storage, "192.0.2.1")
    assert _refresh(c1, sid1).status_code == 200      # 池子的第 800 次
    for i in range(3):                                 # 換 cookie、換 IP 也一樣
        c, sid, _ = _new_owner_with_scenario(app, storage, f"192.0.2.{i + 2}")
        r = _refresh(c, sid)
        assert r.status_code == 429 and _stage(r) == "vendor_budget_exhausted"
    assert _metric(storage, "new_owner_tier_block_count") == 3


def test_existing_owners_keep_the_remaining_global_capacity(env):
    app, storage, clock, _ = env
    old, old_sid, old_owner = _new_owner_with_scenario(app, storage, IP_A)
    _age_owner(storage, old_owner, 3)
    day, start = ac.ny_day_bounds(clock())
    _seed(storage, "new_owner_tier", day, ac.DAY, start, 800)   # 新 owner 池用光

    new, new_sid, _ = _new_owner_with_scenario(app, storage, IP_B)
    assert _refresh(new, new_sid).status_code == 429
    assert _refresh(old, old_sid).status_code == 200            # 既有 owner 不受影響


def test_new_owner_pool_follows_a_configured_global_budget():
    storage, clock = MemoryStorage(), FakeClock()
    app = create_app(cboe_fetch=CountingCboe(), storage=storage, clock=clock,
                     source_hmac_secret=SECRET, trusted_ip_header="x-forwarded-for",
                     global_vendor_daily_budget=1000)
    day, start = ac.ny_day_bounds(clock())
    _seed(storage, "new_owner_tier", day, ac.DAY, start, 399)
    c, sid, _ = _new_owner_with_scenario(app, storage)
    assert _refresh(c, sid).status_code == 200
    assert _refresh(c, sid).status_code == 429


# ---------- 只有真的要打上游才計數 ----------

def test_page_dashboard_and_detail_reads_consume_zero_vendor_quota(env):
    app, storage, _, cboe = env
    c, sid, _ = _new_owner_with_scenario(app, storage)
    for _ in range(25):
        c.get("/api/scenarios").raise_for_status()
        c.get(f"/api/scenarios/{sid}").raise_for_status()
        c.get("/api/me/usage-summary").raise_for_status()
        c.get(f"/api/scenarios/{sid}/results").raise_for_status()
        c.get("/api/settings").raise_for_status()
    assert cboe.calls == 0
    assert storage._rate_limits == {}


# ---------- source key：不落盤、會過期、IPv6 聚合 ----------

def test_raw_ip_is_never_persisted_anywhere(env):
    app, storage, _, _ = env
    ip = "203.0.113.77"
    c, sid, owner = _new_owner_with_scenario(app, storage, ip)
    _age_owner(storage, owner, 2)
    _refresh(c, sid).raise_for_status()
    c.post("/api/auth/login", json={"password": "wrong"})
    dump = repr((storage._rate_limits, storage.metric_summary(), list(storage._diagnostics),
                 storage._events, storage._owners, storage._browser_identities))
    assert ip not in dump
    assert any(scope == "source_vendor" for scope, *_ in storage._rate_limits)


def test_source_state_is_purged_after_its_window(env):
    app, storage, clock, _ = env
    c, sid, owner = _new_owner_with_scenario(app, storage)
    _age_owner(storage, owner, 2)
    _refresh(c, sid).raise_for_status()
    assert any(scope == "source_vendor" for scope, *_ in storage._rate_limits)

    clock.advance(2 * 86400)
    body = c.get("/api/cron/cleanup-abandoned-owners", headers=AUTH).json()
    assert body["rate_limit_rows_purged"] > 0
    assert storage._rate_limits == {}


def test_source_key_normalization_and_rotation():
    now = time.time()
    k = ac.source_key
    assert k("2001:db8:1:2::1", SECRET, now) == k("2001:db8:1:2:ffff::9", SECRET, now)
    assert k("2001:db8:1:2::1", SECRET, now) != k("2001:db8:1:3::1", SECRET, now)
    assert k("::ffff:203.0.113.5", SECRET, now) == k("203.0.113.5", SECRET, now)
    assert k(IP_A, SECRET, now) != k(IP_A, SECRET, now + 86400)     # 每日輪替
    assert k(IP_A, SECRET, now) != k(IP_A, "another-secret", now)
    assert IP_A not in k(IP_A, SECRET, now)


def test_untrusted_forwarded_header_is_ignored_off_vercel():
    headers = {"x-forwarded-for": "198.51.100.99"}
    assert ac.client_ip(headers, "192.0.2.50", None) == "192.0.2.50"
    assert ac.client_ip(headers, "192.0.2.50", "x-forwarded-for") == "198.51.100.99"
    assert ac.client_ip({"x-forwarded-for": "not-an-ip"}, None, "x-forwarded-for") is None
    assert ac.client_ip({"x-forwarded-for": "198.51.100.1, 10.0.0.1"}, None,
                        "x-forwarded-for") == "198.51.100.1"


def test_trusted_header_is_only_the_default_on_vercel(monkeypatch):
    monkeypatch.delenv("TRUSTED_CLIENT_IP_HEADER", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert ac.default_trusted_ip_header() is None
    monkeypatch.setenv("VERCEL", "1")
    assert ac.default_trusted_ip_header() == "x-forwarded-for"
    monkeypatch.setenv("TRUSTED_CLIENT_IP_HEADER", "none")
    assert ac.default_trusted_ip_header() is None


def test_missing_secret_explicitly_disables_source_and_login_limits():
    storage = MemoryStorage()
    app = create_app(cboe_fetch=CountingCboe(), storage=storage,
                     source_hmac_secret="", trusted_ip_header="x-forwarded-for",
                     superadmin_password=SA_PW)
    c = _browser(app)
    for _ in range(15):
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert not any(scope in ("login", "source_vendor") for scope, *_ in storage._rate_limits)
    c.post("/api/auth/login", json={"password": SA_PW}).raise_for_status()
    status = c.get("/api/ops/metrics").json()["abuse_control"]
    assert status["source_limiter"] == "disabled_missing_secret"
    assert SECRET not in repr(status) and "fake" not in repr(status)


# ---------- 登入暴力猜測 ----------

def test_login_brute_force_is_limited_per_source_without_global_lockout(env):
    app, storage, clock, _ = env
    attacker = _browser(app, IP_A)
    for _ in range(10):
        assert attacker.post("/api/auth/login", json={"password": "guess"}).status_code == 401
    blocked = attacker.post("/api/auth/login", json={"password": SA_PW})
    assert blocked.status_code == 429                  # 連正確密碼也先擋（這個來源）
    assert _metric(storage, "login_rate_limit_block_count") == 1

    owner = _browser(app, IP_B)                        # 別的來源：完全不受影響
    assert owner.post("/api/auth/login", json={"password": SA_PW}).status_code == 200

    clock.advance(61)                                  # 同一個來源，下一分鐘恢復
    assert attacker.post("/api/auth/login", json={"password": SA_PW}).status_code == 200


def test_login_hourly_source_limit(env):
    app, storage, clock, _ = env
    key = ac.source_key(IP_A, SECRET, clock())
    _seed(storage, "login", key, ac.HOUR, ac.window_start(clock(), ac.HOUR), 60)
    r = _browser(app, IP_A).post("/api/auth/login", json={"password": SA_PW})
    assert r.status_code == 429


def test_limits_are_configurable_without_code_changes(monkeypatch):
    monkeypatch.setenv("OWNER_VENDOR_QUOTA_PER_MINUTE", "5")
    monkeypatch.setenv("SOURCE_VENDOR_BURST_PER_MINUTE", "7")
    monkeypatch.setenv("NEW_OWNER_TIER_SHARE", "0.25")
    monkeypatch.setenv("SOURCE_HMAC_SECRET", "env-provided-fake-secret")
    storage = MemoryStorage()
    app = create_app(cboe_fetch=CountingCboe(), storage=storage, superadmin_password=SA_PW)
    c = _browser(app)
    c.post("/api/auth/login", json={"password": SA_PW}).raise_for_status()
    status = c.get("/api/ops/metrics").json()["abuse_control"]
    assert status["owner_vendor_quota"][0] == 5
    assert status["source_vendor_burst"][0] == 7
    assert status["new_owner_tier_share"] == 0.25
    assert status["source_limiter"] == "enabled"
    assert "env-provided-fake-secret" not in repr(c.get("/api/ops/metrics").json())
