"""OPTION-CHASER-IDENTITY-ROOT-CAUSE-REVIEW-001：「劇本消失」的身分路徑
regression。

兩類測試：

1. **鎖住已證實健全的部分**（今天就綠）——伺服器在 request 帶著一顆
   可解析的 owner cookie 時，不會在任何回應（含 404／409）重簽或改動它
   （IDENTITY-FIX-002 起簽一次、固定期限）；同一顆 cookie 跨 app
   instance（模擬重新部署）在 Postgres 上解析到同一個 owner。這些是調查過程中逐一排除「伺服器端弄丟身分」
   的證據，收進測試避免未來回歸。

2. **身分不在的語意**（IRI-04 落地，原本是 `xfail` 等裁示）——帶著一顆
   我們自己作廢過的 token（身分墓碑有紀錄）來讀，回應帶
   `X-OC-Owner-Identity: unknown`、`/api/me/usage-summary` 回
   `identity: "unknown"`，首寫時鑄一顆**全新**憑證、兩腿一起換掉，絕不把
   舊 token 再綁到新 owner；完全沒帶或帶的是前端自己產生、還沒綁定的
   token 是 `none`（首訪），照舊原樣綁定——跨分頁共用同一顆才能靠 PK
   只建一個 owner。墓碑之外被刪掉的 token（資料庫回復到更早時點）當
   `none`，是明寫的能力邊界。

   OPTION-CHASER-UNIFIED-IDENTITY-001 起，憑證同時存在 cookie 與前端本機
   儲存、互相補回；只剩「兩份都對不上伺服器」才算身分不在。原本的「cookie
   不在、只剩本機那份」改成正向測試：它現在就是還原路徑。
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

def test_no_response_to_a_resolvable_cookie_touches_the_cookie():
    app, _ = _app(anonymous_max_active_scenarios=1)
    b = _browser(app)
    bind = b.post("/api/scenarios", json=NEW)
    assert bind.status_code == 201
    token, attrs = _split(_owner_set_cookies(bind)[0])
    assert "max-age=34560000" in attrs and "secure" in attrs and "httponly" in attrs
    # 200、404、409（第二個劇本撞上 per-owner 額度）都不再發 owner cookie，
    # 但照舊說「已綁定」。
    later = [
        b.get("/api/scenarios"),
        b.get("/api/scenarios/does-not-exist"),
        b.post("/api/scenarios", json=NEW),
    ]
    assert [r.status_code for r in later] == [200, 404, 409]
    for r in later:
        assert _owner_set_cookies(r) == [], r.status_code
        assert r.headers.get("X-OC-Owner-Bound") == "1"
    assert b.cookies.get(_OWNER_COOKIE_NAME) == token


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
    # instance A 綁定時記下的 cookie_issued_at 在 DB 裡：instance B 不重簽。
    assert _owner_set_cookies(r) == []
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM owners").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM browser_identities").fetchone()[0] == 1


# ---------- 2. 缺陷重現：身分不在 ＝ 首訪（無法區分） ----------

def _first_visit_signature(app):
    r = _browser(app).get("/api/scenarios")
    return r.status_code, r.json(), r.headers.get("X-OC-Owner-Bound"), _owner_set_cookies(r)


def _lost_identity_cases(storage, app):
    """「這個瀏覽器以前有身分、現在兩份憑證都對不上」的伺服器端狀態——
    身分是經由我們自己的原語作廢的（會留墓碑）。"""
    # cookie 還在、但 owner 已被 retention 清掉；沒有本機那份。
    b_cookie = _browser(app)
    b_cookie.post("/api/scenarios", json=NEW)
    oid = storage.resolve_owner_by_token(b_cookie.cookies.get(_OWNER_COOKIE_NAME))
    storage.delete_owner(oid, reason="retention_expired")
    yield "unknown-cookie", b_cookie, {}
    # 只剩本機那份（cookie 不在）、owner 已被使用者自己刪掉。
    local = "local-gone-" + "y" * 32
    _browser(app).post("/api/scenarios", json=NEW,
                       headers={"X-OC-Credential": local}).raise_for_status()
    storage.delete_owner(storage.resolve_owner_by_token(local), reason="self_deleted")
    yield "unknown-local", _browser(app), {"X-OC-Credential": local}


def test_a_cookie_less_browser_with_its_local_credential_is_not_a_lost_identity():
    """UNIFIED-IDENTITY-001：cookie 不見了、但前端本機那份還在（不論綁定了
    多久）——同一個 owner、看得到原本的劇本，cookie 補發回來，不會多出
    owner。舊設計在這裡把它當新訪客，是「劇本消失＋多出 owner」的入口之一。"""
    app, storage = _app()
    local = "local-" + "x" * 40
    _browser(app).post("/api/scenarios", json=NEW,
                       headers={"X-OC-Credential": local}).raise_for_status()
    oid = storage.resolve_owner_by_token(local)
    storage._owners[oid] = replace(
        storage._owners[oid],
        created_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
    r = _browser(app).get("/api/scenarios", headers={"X-OC-Credential": local})
    assert len(r.json()) == 1
    assert r.headers.get(IDENTITY_HEADER) == "bound"
    assert _owner_set_cookies(r)[0].startswith(f"{_OWNER_COOKIE_NAME}={local};")
    w = _browser(app).post("/api/scenarios", json={**NEW, "symbol": "QQQ"},
                           headers={"X-OC-Credential": local})
    assert w.status_code == 201
    assert [o.owner_id for o in storage.list_owners()] == [oid]


def test_lost_identity_reads_are_signalled_as_unknown_but_otherwise_look_like_a_first_visit():
    """IRI-04：遺失狀態的讀取仍是 200／[]／不簽 cookie／沒有 Owner-Bound
    （不建立任何東西），**但**身分訊號說 `unknown`——前端與觀測從此分得出
    「還沒有劇本」與「以前的身分已不在」。"""
    app, storage = _app()
    status, body, bound, cookies = _first_visit_signature(app)
    for name, browser, headers in _lost_identity_cases(storage, app):
        r = browser.get("/api/scenarios", headers=headers)
        assert (r.status_code, r.json(), r.headers.get("X-OC-Owner-Bound"),
                _owner_set_cookies(r)) == (status, body, bound, cookies), name
        assert r.headers.get(IDENTITY_HEADER) == "unknown", name
        summary = browser.get("/api/me/usage-summary", headers=headers).json()
        assert summary["active_scenarios"] == 0 and summary["identity"] == "unknown", name


def test_next_write_after_losing_identity_mints_a_new_owner_with_a_fresh_credential():
    """兩份憑證都對不上伺服器＝能力邊界：第一次寫入仍會得到一個**新**
    owner（舊劇本無法安全配對回來，不猜）。但 IRI-04 起新 owner 綁的是一顆
    全新的 token，兩腿同時換掉；舊 token 留在墓碑裡、不會被重新綁定。"""
    app, storage = _app()
    for name, browser, headers in _lost_identity_cases(storage, app):
        stale = headers.get("X-OC-Credential") or browser.cookies.get(_OWNER_COOKIE_NAME)
        before = len(storage.list_owners())
        r = browser.post("/api/scenarios", json=NEW, headers=headers)
        assert r.status_code == 201, name
        assert r.headers.get(IDENTITY_HEADER) == "bound", name
        assert len(storage.list_owners()) == before + 1, name
        fresh, _ = _split(_owner_set_cookies(r)[0])
        assert fresh != stale, name
        assert r.headers.get("X-OC-Credential") == fresh, name      # 本機那份也換
        assert storage.resolve_owner_by_token(stale) is None, name  # 舊 token 沒被重綁
        assert storage.lookup_identity_tombstone(stale) is not None, name
        follow = browser.get("/api/scenarios", headers={**headers, "X-OC-Credential": fresh}
                             if headers else {})
        assert len(follow.json()) == 1, name
    orphaned = [o for o in storage.list_owners()
                if not any(i.owner_id == o.owner_id for i in storage._browser_identities.values())]
    assert orphaned == []       # 舊 owner 連同劇本已被原語刪掉，沒有半套狀態


def test_reads_with_an_unknown_but_well_formed_token_are_signalled():
    app, storage = _app()
    cases = dict((name, (b, h)) for name, b, h in _lost_identity_cases(storage, app))
    browser, headers = cases["unknown-cookie"]
    r = browser.get("/api/scenarios", headers=headers)
    assert r.headers.get(IDENTITY_HEADER) == "unknown"
    assert browser.get("/api/me/usage-summary", headers=headers).json()["identity"] == "unknown"


def test_bound_and_anonymous_reads_expose_their_identity_state():
    """已綁定 → `bound`；完全沒有身分（首訪／cookie 不在）→ `none`。"""
    app, _ = _app()
    fresh = _browser(app)
    assert fresh.get("/api/scenarios").headers.get(IDENTITY_HEADER) == "none"
    assert fresh.get("/api/me/usage-summary").json()["identity"] == "none"
    fresh.post("/api/scenarios", json=NEW)
    assert fresh.get("/api/scenarios").headers.get(IDENTITY_HEADER) == "bound"
    assert fresh.get("/api/me/usage-summary").json()["identity"] == "bound"


def test_a_client_generated_token_that_was_never_bound_reads_as_none_and_binds_as_is():
    """正式站的首訪一定帶著前端自己產生、還沒綁定的 token（`X-OC-Credential`）。
    它不是「以前的身分」——沒有墓碑——所以是 `none`，而且首寫**原樣**綁定
    這顆 token（所有分頁共用同一顆，靠 PK 只建一個 owner），不鑄新的。"""
    app, storage = _app()
    local = "client-" + "c" * 36
    b = _browser(app)
    r = b.get("/api/scenarios", headers={"X-OC-Credential": local})
    assert r.headers.get(IDENTITY_HEADER) == "none"
    w = b.post("/api/scenarios", json=NEW, headers={"X-OC-Credential": local})
    assert w.status_code == 201
    token, _ = _split(_owner_set_cookies(w)[0])
    assert token == local
    assert "X-OC-Credential" not in w.headers          # 本機那份本來就對
    assert storage.resolve_owner_by_token(local) is not None


def test_tokens_deleted_outside_the_storage_primitives_read_as_none():
    """能力邊界（明寫）：不經過 storage 原語消失的 token（例如資料庫回復到
    更早時點）沒有墓碑，分不出來，當 `none`——首寫會原樣綁定它。"""
    app, storage = _app()
    b = _browser(app)
    b.post("/api/scenarios", json=NEW)
    tok = b.cookies.get(_OWNER_COOKIE_NAME)
    del storage._browser_identities[tok]
    assert b.get("/api/scenarios").headers.get(IDENTITY_HEADER) == "none"
    w = b.post("/api/scenarios", json=NEW)
    assert w.status_code == 201
    assert storage.resolve_owner_by_token(tok) is not None
