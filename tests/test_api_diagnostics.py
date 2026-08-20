"""HTTP 端點與 correlation ID middleware（DG-02／#145）。

本檔案只測骨幹本身——`GET`／`DELETE /api/diagnostics`、
`X-Correlation-Id` 標頭。Historical IV 實際產生 events 的那條路徑
在 DG-03／#146 的測試裡（本檔案用 `diagnostics.emit()` 直接灌資料，
不假裝已經接了任何 subsystem）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api_app import diagnostics
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage


@pytest.fixture
def db():
    return MemoryStorage()


@pytest.fixture
def client(db):
    return TestClient(create_app(storage=db))


def _seed(db, n=1, **over):
    for i in range(n):
        diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                         severity="error", message=f"boom-{i}",
                         ts=f"2026-08-15T00:0{i}:00+00:00", **over)


# ---------- GET /api/diagnostics ----------

def test_empty_diagnostics_list(client):
    assert client.get("/api/diagnostics").json() == []


def test_lists_seeded_events_newest_first(db, client):
    _seed(db, 3)
    body = client.get("/api/diagnostics").json()
    assert [e["message"] for e in body] == ["boom-2", "boom-1", "boom-0"]


def test_returned_shape_has_every_field(db, client):
    _seed(db, 1, symbol="TLT")
    got = client.get("/api/diagnostics").json()[0]
    for key in ("event_id", "correlation_id", "ts", "subsystem", "stage",
                "severity", "message", "context"):
        assert key in got
    assert got["context"] == {"symbol": "TLT"}


def test_limit_query_param_is_respected(db, client):
    _seed(db, 5)
    body = client.get("/api/diagnostics?limit=2").json()
    assert len(body) == 2


def test_limit_is_clamped_to_the_retention_ceiling(db, client):
    _seed(db, 3)
    body = client.get(
        f"/api/diagnostics?limit={diagnostics.RETENTION_LIMIT + 1000}").json()
    assert len(body) == 3   # 沒有更多資料可回，不會因為夾上限而炸掉


# ---------- DELETE /api/diagnostics ----------

def test_clear_reports_how_many_were_removed(db, client):
    _seed(db, 4)
    resp = client.delete("/api/diagnostics")
    assert resp.json() == {"cleared": 4}
    assert client.get("/api/diagnostics").json() == []


def test_clear_on_an_empty_store_is_harmless(client):
    assert client.delete("/api/diagnostics").json() == {"cleared": 0}


# ---------- correlation ID middleware ----------

def test_every_response_carries_a_correlation_id_header(client):
    resp = client.get("/api/health")
    assert resp.headers.get("X-Correlation-Id")


def test_error_responses_carry_a_correlation_id_too(client):
    resp = client.get("/api/scenarios/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers.get("X-Correlation-Id")


def test_different_requests_get_different_correlation_ids(client):
    a = client.get("/api/health").headers["X-Correlation-Id"]
    b = client.get("/api/health").headers["X-Correlation-Id"]
    assert a != b


# ---------- security gate（DG-07／#150）：端點層 redaction 全表面驗證 ----------
#
# `test_diagnostics.py` 已經在 `emit()`／`sanitize_*()` 這個純函式層級
# 測過同一組規則；這裡换一個角度——從 HTTP 端點（真正離開後端進到
# 使用者手上的那個介面）往回驗證同一件事沒有在某一層漏接。

def test_a_known_provider_token_never_reaches_the_api_response(db, client):
    token = "mdapp_live_SECRET_TOKEN_998877"
    diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                     severity="error",
                     message=f"vendor rejected key {token}",
                     ts="2026-08-15T00:00:00+00:00", secrets=(token,))
    resp = client.get("/api/diagnostics")
    assert token not in resp.text


def test_a_known_database_url_never_reaches_the_api_response(db, client):
    """需求方明確點名的第二個表面（跟 provider token 同一個機制，
    `secrets` 對兩者一視同仁——這裡用它真實的樣子單獨測一次，不只是
    論證上的『同理可證』。"""
    db_url = "postgres://appuser:s3cr3t-pw@ep-cool-cloud-12345.neon.tech/main"
    diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                     severity="error",
                     message=f"connection failed: {db_url}",
                     ts="2026-08-15T00:00:00+00:00", secrets=(db_url,))
    resp = client.get("/api/diagnostics")
    assert db_url not in resp.text
    # 帳密片段也不能單獨留在畫面上（防止只做整串比對漏掉子字串殘留）。
    assert "s3cr3t-pw" not in resp.text


def test_a_context_key_outside_the_whitelist_never_reaches_the_api_response(
        db, client):
    diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                     severity="info", message="ok",
                     ts="2026-08-15T00:00:00+00:00",
                     symbol="TLT", authorization="Bearer should-not-survive",
                     cookie="session=should-not-survive")
    got = client.get("/api/diagnostics").json()[0]
    assert got["context"] == {"symbol": "TLT"}
    assert "authorization" not in got["context"]
    assert "cookie" not in got["context"]
    assert "should-not-survive" not in client.get("/api/diagnostics").text


def test_an_overlong_errmsg_is_truncated_visibly_in_the_api_response(db, client):
    long_errmsg = "x" * 5000
    diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                     severity="error", message="vendor error",
                     ts="2026-08-15T00:00:00+00:00",
                     vendor_errmsg=long_errmsg)
    got = client.get("/api/diagnostics").json()[0]
    assert len(got["context"]["vendor_errmsg"]) < len(long_errmsg)
    assert got["context"]["vendor_errmsg"].endswith("…[截斷]")


def test_full_http_headers_are_never_recorded_only_the_rate_limit_whitelist(
        db, client):
    """context 白名單本身就不含任何泛用 header 名稱——這裡用一個典型的
    完整 headers dict 當 context 值餵進去，確認白名單過濾一樣把它擋在
    門外（headers 不是白名單認得的 key，整包被丟棄）。"""
    diagnostics.emit(db, subsystem="historical_iv", stage="vendor_fetch",
                     severity="info", message="ok",
                     ts="2026-08-15T00:00:00+00:00",
                     headers={"Set-Cookie": "sid=abc", "Authorization": "Bearer x"},
                     **{"X-Api-Ratelimit-Remaining": "42"})
    got = client.get("/api/diagnostics").json()[0]
    assert "headers" not in got["context"]
    assert got["context"].get("X-Api-Ratelimit-Remaining") == "42"
    assert "Set-Cookie" not in client.get("/api/diagnostics").text
    assert "sid=abc" not in client.get("/api/diagnostics").text
