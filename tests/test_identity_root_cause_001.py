"""OPTION-CHASER-IDENTITY-ROOT-CAUSE-REVIEW-001：「劇本消失」的身分路徑
regression。

兩類測試：

1. **鎖住已證實健全的部分**（今天就綠）——伺服器在 request 帶著一顆
   可解析的 owner cookie 時，不會在任何回應（含 404／409）把它換掉或
   改屬性；同一顆 cookie 跨 app instance（模擬重新部署）在 Postgres 上
   解析到同一個 owner。這些是調查過程中逐一排除「伺服器端弄丟身分」
   的證據，收進測試避免未來回歸。

2. **重現缺陷本身**（`xfail(strict=True)`，等 Owner 裁決修法後翻綠）——
   三種「身分不在」的狀態（沒 cookie／cookie token 伺服器不認得／
   bootstrap token 過期）對讀取端點的回應與**首訪完全無法區分**：
   同樣 200、同樣 `[]`、同樣沒有任何身分訊號。前端因此只能把它畫成
   「還沒有劇本」，下一次寫入再默默鑄一個新 owner（`claim_browser_
   token`），舊 owner 與舊劇本留在 DB 卻再也存取不到。這裡用最小的
   additive 介面描述期望：讀取回應帶 `X-OC-Owner-Identity`
   （`bound`／`unknown`／`none`），`/api/me/usage-summary` 多一個
   `identity` 欄位。欄位名只是提案，Owner 若另有裁示再改。
"""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
IDENTITY_HEADER = "X-OC-Owner-Identity"
PENDING_DECISION = ("OPTION-CHASER-IDENTITY-ROOT-CAUSE-REVIEW-001：身分不在的"
                    "讀取回應與首訪無法區分；等 Owner 裁決最小修法")


def _app(storage=None, **kwargs):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return create_app(fetch=lambda symbol: snap, storage=storage,
                      cron_secret="fake-cron-secret", **kwargs), storage


def _browser(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def _owner_set_cookies(resp) -> list[str]:
    return [v for k, v in resp.headers.multi_items()
            if k.lower() == "set-cookie" and v.startswith(_OWNER_COOKIE_NAME + "=")]


def _split(header: str) -> tuple[str, list[str]]:
    first, *attrs = header.split(";")
    return first.split("=", 1)[1], sorted(a.strip().lower() for a in attrs)


# ---------- 1. 伺服器端不會弄丟一顆可解析的 cookie ----------

def test_every_response_with_a_resolvable_cookie_renews_the_same_token_and_attrs():
    app, _ = _app(anonymous_max_active_scenarios=1)
    b = _browser(app)
    bind = b.post("/api/scenarios", json=NEW)
    assert bind.status_code == 201
    token, attrs = _split(_owner_set_cookies(bind)[0])
    # 200、404、409（第二個劇本撞上 per-owner 額度）都要續命，而且一字不差。
    renewals = [
        b.get("/api/scenarios"),
        b.get("/api/scenarios/does-not-exist"),
        b.post("/api/scenarios", json=NEW),
    ]
    assert [r.status_code for r in renewals] == [200, 404, 409]
    for r in renewals:
        headers = _owner_set_cookies(r)
        assert len(headers) == 1, r.status_code
        assert _split(headers[0]) == (token, attrs), r.status_code
        assert r.headers.get("X-OC-Owner-Bound") == "1"
    assert "max-age=16156800" in attrs and "secure" in attrs and "httponly" in attrs


@pytest.mark.skipif(not os.environ.get("OC_TEST_DATABASE_URL"),
                    reason="需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
def test_same_cookie_resolves_across_app_instances_on_postgres():
    """模擬重新部署／另一個 serverless instance：instance A 簽發的
    cookie，instance B（全新 `create_app()`＋全新 `PostgresStorage`）
    直接解析到同一個 owner，不多建 owner。"""
    import psycopg
    from api_app.storage.postgres import PostgresStorage

    dsn = os.environ["OC_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in ("scenarios", "owners", "browser_identities"):
            conn.execute(f"DELETE FROM {table}")
    app_a, _ = _app(PostgresStorage(dsn))
    app_b, _ = _app(PostgresStorage(dsn))
    a = _browser(app_a)
    created = a.post("/api/scenarios", json=NEW)
    assert created.status_code == 201
    token = a.cookies.get(_OWNER_COOKIE_NAME)

    b = _browser(app_b)
    r = b.get("/api/scenarios", headers={"Cookie": f"{_OWNER_COOKIE_NAME}={token}"})
    assert r.status_code == 200
    assert [row["id"] for row in r.json()] == [created.json()["id"]]
    assert r.headers.get("X-OC-Owner-Bound") == "1"
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM owners").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM browser_identities").fetchone()[0] == 1


# ---------- 2. 缺陷重現：身分不在 ＝ 首訪（無法區分） ----------

def _first_visit_signature(app):
    r = _browser(app).get("/api/scenarios")
    return r.status_code, r.json(), r.headers.get("X-OC-Owner-Bound"), _owner_set_cookies(r)


def _lost_identity_cases(storage, app):
    """三種「這個瀏覽器以前有身分、現在請求帶不到」的伺服器端狀態。"""
    # (a) cookie 還在、但 token 伺服器已不認得（identity 列不在了）
    b_unknown = _browser(app)
    b_unknown.post("/api/scenarios", json=NEW)
    tok = b_unknown.cookies.get(_OWNER_COOKIE_NAME)
    del storage._browser_identities[tok]
    yield "unknown-token", b_unknown, {}
    # (b) cookie 不在，只剩一顆綁定超過 10 分鐘的 bootstrap token
    b_stale_src = _browser(app)
    boot = "stale-" + "x" * 40
    b_stale_src.post("/api/scenarios", json=NEW, headers={"X-OC-Owner-Bootstrap": boot})
    oid = storage.resolve_owner_by_token(boot)
    storage._owners[oid] = replace(
        storage._owners[oid],
        created_at=(datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat())
    yield "stale-bootstrap", _browser(app), {"X-OC-Owner-Bootstrap": boot}


def test_lost_identity_reads_are_today_indistinguishable_from_a_first_visit():
    """這條**今天會過**——它就是缺陷的重現：兩種遺失狀態的讀取回應跟
    首訪一模一樣（200／[]／沒有 X-OC-Owner-Bound／沒有 Set-Cookie），
    前端拿不到任何線索。修法落地後這條應該改寫或刪除。"""
    app, storage = _app()
    first = _first_visit_signature(app)
    for name, browser, headers in _lost_identity_cases(storage, app):
        r = browser.get("/api/scenarios", headers=headers)
        assert (r.status_code, r.json(), r.headers.get("X-OC-Owner-Bound"),
                _owner_set_cookies(r)) == first, name
        assert IDENTITY_HEADER not in r.headers, name
        summary = browser.get("/api/me/usage-summary", headers=headers).json()
        assert summary["active_scenarios"] == 0 and "identity" not in summary, name


def test_next_write_after_losing_identity_silently_mints_a_new_owner():
    """同樣是缺陷重現（今天會過）：三種遺失狀態下的第一次寫入都成功
    （201）、都多出一個 owner，舊 owner 的劇本仍在 DB 但這個瀏覽器
    再也看不到。這就是 production 同一個人累積出多個 owner 的機制。"""
    app, storage = _app()
    for name, browser, headers in _lost_identity_cases(storage, app):
        before = len(storage.list_owners())
        if name == "stale-bootstrap":
            # 伺服器會先 409；前端（src/api.ts sendOwnerBootstrap）換 token 重送
            r = browser.post("/api/scenarios", json=NEW, headers=headers)
            assert r.status_code == 409 and r.headers.get("X-OC-Owner-Bootstrap-Stale") == "1"
            headers = {"X-OC-Owner-Bootstrap": "fresh-" + "y" * 40}
        r = browser.post("/api/scenarios", json=NEW, headers=headers)
        assert r.status_code == 201, name
        assert len(storage.list_owners()) == before + 1, name
        assert len(browser.get("/api/scenarios", headers=headers).json()) == 1, name
    # 兩個「舊 owner」的劇本都還在，只是沒有任何 cookie 能指到它們
    orphaned = [o for o in storage.list_owners()
                if not any(i.owner_id == o.owner_id for i in storage._browser_identities.values())]
    assert len(orphaned) == 1   # (a) 的舊 owner；(b) 的舊 owner 仍握有 stale token 那列
    assert all(storage.list_scenarios(owner=o.owner_id) for o in orphaned)


@pytest.mark.xfail(strict=True, reason=PENDING_DECISION)
def test_reads_with_an_unknown_but_well_formed_token_are_signalled():
    """期望（提案）：cookie 形狀合法但伺服器不認得時，讀取回應要帶
    `X-OC-Owner-Identity: unknown`，`usage-summary` 要回 `identity:
    "unknown"`——讓前端能把它畫成「此瀏覽器的身分已失效」而不是
    「還沒有劇本」，也讓 Production 能被觀測。"""
    app, storage = _app()
    cases = dict((name, (b, h)) for name, b, h in _lost_identity_cases(storage, app))
    browser, headers = cases["unknown-token"]
    r = browser.get("/api/scenarios", headers=headers)
    assert r.headers.get(IDENTITY_HEADER) == "unknown"
    assert browser.get("/api/me/usage-summary", headers=headers).json()["identity"] == "unknown"


@pytest.mark.xfail(strict=True, reason=PENDING_DECISION)
def test_bound_and_anonymous_reads_expose_their_identity_state():
    """期望（提案）：已綁定 → `bound`；完全沒有身分（首訪／cookie 不在）
    → `none`。前端搭配本機非身分性的「曾經綁定過」標記，就能在 cookie
    不在時警示，而不是默默當成新訪客。"""
    app, _ = _app()
    fresh = _browser(app)
    assert fresh.get("/api/scenarios").headers.get(IDENTITY_HEADER) == "none"
    fresh.post("/api/scenarios", json=NEW)
    assert fresh.get("/api/scenarios").headers.get(IDENTITY_HEADER) == "bound"
    assert fresh.get("/api/me/usage-summary").json()["identity"] == "bound"
