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
