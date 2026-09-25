"""PB-02（#294，Anonymous Public Beta）：cookie-based Browser Identity
middleware——lazy creation ＋ 路由排除清單 ＋ `identity_resolver()`
切換。

沿用既有第 1 個 seam（HTTP API）與第 3 個（Storage port 契約，
`list_owners()` 已由 `test_storage_contract.py` 覆蓋，這裡只驗證
`create_app()` 這一層真的把它接上了）。

`base_url="https://testserver"`：production 是 Vercel（恆為 HTTPS），
這裡讓 httpx 的 cookie jar 用跟真實瀏覽器一致的 scheme 判斷，
`Secure`／`__Host-` cookie 才會在同一個 client 的多次請求之間正確
round-trip（已用最小重現腳本驗證：`http` scheme 下 Secure cookie
完全不會被送回，這不是本測試檔的臆測）。
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


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- Lazy creation ----------


def test_the_first_owner_scoped_request_issues_a_cookie():
    """SECURITY-FIX-01（deferred owner creation）改寫：第一次讀取仍然
    簽一顆 cookie（之後的請求才帶得回同一顆 token），但**不建立任何
    owner**——owner 等到第一次真正需要持久化資料時才建立。"""
    c, storage = _client()
    assert storage.list_owners() == []

    c.get("/api/scenarios")

    assert storage.list_owners() == []
    assert _OWNER_COOKIE_NAME in c.cookies


def test_repeated_requests_on_the_same_client_reuse_the_same_owner():
    """讀取期間沿用同一顆（尚未綁定的）token；第一次建立劇本時才把
    這顆 token 綁到一個 owner，之後都是同一個 owner。"""
    c, storage = _client()
    c.get("/api/scenarios")
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    c.get("/api/scenarios")
    c.get("/api/settings")
    assert c.cookies.get(_OWNER_COOKIE_NAME) == token
    assert storage.list_owners() == []

    _create(c)
    _create(c, symbol="YYY")
    assert len(storage.list_owners()) == 1
    assert c.cookies.get(_OWNER_COOKIE_NAME) == token
    assert storage.resolve_owner_by_token(token) == storage.list_owners()[0].owner_id


def test_a_request_carrying_an_unknown_token_gets_a_brand_new_owner():
    """cookie 查不到綁定：形狀正確就當作「還沒綁定的 token」沿用、
    不建立 owner；形狀不對（偽造的任意字串）就換一顆新的——兩者都不得
    報錯，也都不會沿用到任何既有 owner。"""
    c, storage = _client()
    r = c.get("/api/scenarios",
              headers={"Cookie": f"{_OWNER_COOKIE_NAME}=totally-made-up-token"})
    assert r.status_code == 200
    issued = r.cookies.get(_OWNER_COOKIE_NAME)
    assert issued and issued != "totally-made-up-token"   # 偽造值被換掉
    assert storage.list_owners() == []

    well_formed = "A" * 43                                  # 形狀正確、但從沒綁定過
    r = c.get("/api/scenarios", headers={"Cookie": f"{_OWNER_COOKIE_NAME}={well_formed}"})
    assert r.cookies.get(_OWNER_COOKIE_NAME) == well_formed  # 原樣沿用、續命
    assert storage.list_owners() == []

    r = c.post("/api/scenarios", json=NEW,
               headers={"Cookie": f"{_OWNER_COOKIE_NAME}={well_formed}"})
    assert r.status_code == 201
    assert len(storage.list_owners()) == 1
    assert storage.resolve_owner_by_token(well_formed) == storage.list_owners()[0].owner_id


# ---------- 隔離 ----------


def test_two_different_browsers_see_completely_isolated_data():
    storage = MemoryStorage()
    snap = load_snapshot(FIX)
    app = create_app(fetch=lambda symbol: snap, storage=storage)
    c1 = TestClient(app, base_url="https://testserver")
    c2 = TestClient(app, base_url="https://testserver")

    sc1 = _create(c1, symbol="AAA")
    sc2 = _create(c2, symbol="BBB")

    seen_by_1 = {r["symbol"] for r in c1.get("/api/scenarios").json()}
    seen_by_2 = {r["symbol"] for r in c2.get("/api/scenarios").json()}
    assert seen_by_1 == {"AAA"}
    assert seen_by_2 == {"BBB"}
    assert c1.get(f"/api/scenarios/{sc2['id']}").status_code == 404
    assert c2.get(f"/api/scenarios/{sc1['id']}").status_code == 404
    assert len(storage.list_owners()) == 2


def test_owner_id_still_never_appears_in_the_response_body_under_cookie_identity():
    c, _storage = _client()
    sc = _create(c)

    assert "owner_id" not in sc
    assert "owner_id" not in c.get(f"/api/scenarios/{sc['id']}").json()


# ---------- Lazy creation：路由排除清單（spec AC15） ----------


def test_health_does_not_create_an_owner():
    c, storage = _client()
    c.get("/api/health")
    assert storage.list_owners() == []


def test_health_does_not_issue_a_cookie():
    c, _storage = _client()
    c.get("/api/health")
    assert _OWNER_COOKIE_NAME not in c.cookies


def test_cron_endpoint_does_not_create_an_owner_even_when_unauthorized():
    c, storage = _client()
    c.get("/api/cron/warm-rate-cache")   # 401（無 CRON_SECRET）也不建立
    assert storage.list_owners() == []


def test_ops_endpoint_does_not_create_an_owner_even_when_unauthorized():
    c, storage = _client()
    # 這個端點由 Super Admin capability（軸二，AUTH-03／#310 起
    # `require_role(minimum=SUPERADMIN)`，取代已退役的
    # `ADMIN_SECRET`／更早的 `OPS_SECRET`）把關——測試本身不變：沒帶
    # 憑證一律 401，重點是「連 401 之前也不該先幫它建一個 owner」。
    c.get("/api/ops/metrics")
    assert storage.list_owners() == []


def test_auth_status_endpoint_does_not_create_an_owner():
    """AUTH-02（#309）新增端點，AUTH-03（#310）起是查詢角色的唯一
    正式管道（舊 `GET /api/superuser/status` 已隨 `ADMIN_SECRET`
    整組退役）——即使它本身永遠 200（查自己現在算 normal／superuser／
    superadmin 不該需要先被判定為某個角色），也不該幫沒有 cookie 的
    呼叫端先建立一個 owner。"""
    c, storage = _client()
    r = c.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json() == {"role": "normal"}
    assert storage.list_owners() == []


def test_repeated_health_probes_never_accumulate_owners():
    """PB-13 的 uptime／deploy-smoke 監控會持續打這個端點——不得洗出
    大量永遠不會再用到的 Abandoned Owner。"""
    c, storage = _client()
    for _ in range(20):
        c.get("/api/health")
    assert storage.list_owners() == []


# ---------- DI 覆寫：完全繞開 cookie（既有 test_scale06／test_scale11
# 依賴的注入方式） ----------


def test_overriding_identity_resolver_bypasses_cookies_entirely():
    snap = load_snapshot(FIX)
    storage = MemoryStorage()
    app = create_app(fetch=lambda symbol: snap, storage=storage,
                     identity_resolver=lambda: "solo")
    c = TestClient(app)   # 刻意用預設 http base_url——不該需要 https

    _create(c)

    assert storage.list_owners() == []   # 完全沒有走 cookie／owner 表
    assert storage.get_scenario("nope", owner="solo") is None   # owner 表沒有列，資料仍在既有 solo 路徑


# ---------- identity.cookie_identity_resolver() 的防呆 ----------


def test_cookie_identity_resolver_raises_outside_a_resolved_scope():
    from api_app.identity import cookie_identity_resolver

    import pytest
    with pytest.raises(RuntimeError):
        cookie_identity_resolver()


def test_cookie_identity_resolver_reads_the_resolved_scope():
    from api_app.identity import cookie_identity_resolver, resolved_owner_scope

    with resolved_owner_scope("anon-42"):
        assert cookie_identity_resolver() == "anon-42"
