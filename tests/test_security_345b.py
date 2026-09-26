"""#345 剩餘項目：A-4 defense-in-depth（iv-history 窄查詢）與 B-1～B-7。

- B-1：cron secret 固定時間比較，非 ASCII header 不會變 500。
- B-2：`/api/health` 不把例外原文（DB 連線細節）回給未認證的呼叫端。
- B-3：引擎非預期例外的原文不直達 client（分層照舊）。
- B-4：audit-log `limit` 夾住範圍。
- B-5：`vercel.json` 帶基本安全 headers。
- B-6：runtime 依賴釘死版本。
- B-7：redaction 同時遮原值與 strip 後的形式。
- A-4：Historical IV 用 `list_protected_owners()` 窄查詢（storage 合約在
  `tests/test_storage_contract.py`）。
B-8（role session 無 server-side 到期）為 #307 Owner 裁示，僅記錄、不改。
"""
import json
import pathlib
import tomllib

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.main import create_app
from api_app.storage import SuperUserAuditEvent
from api_app.storage.memory import MemoryStorage
from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from _role_session import superadmin_cookies

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
       "strategies": ["vertical-spread"]}
CRON = "fake-cron-secret"
CRON_PATHS = ("/api/cron/warm-rate-cache", "/api/cron/cleanup-abandoned-owners",
              "/api/cron/daily-digest")


def _client(storage=None, cron_secret=CRON, **kwargs):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    app = create_app(fetch=lambda symbol: snap, storage=storage,
                     cron_secret=cron_secret, **kwargs)
    return TestClient(app, base_url="https://testserver"), storage


# ---------- B-1 ----------

@pytest.mark.parametrize("path", CRON_PATHS)
@pytest.mark.parametrize("header", [
    None, "Bearer wrong", f"Bearer {CRON}x", CRON,
    # 非 ASCII（header 以 latin-1 傳進來）：比較本身不得丟例外變 500
    "Bearer é-non-ascii".encode("latin-1")])
def test_cron_endpoints_reject_anything_but_the_exact_bearer(path, header):
    c, _ = _client()
    headers = {"Authorization": header} if header is not None else {}
    assert c.get(path, headers=headers).status_code == 401


def test_cron_endpoints_are_closed_when_the_secret_is_unset():
    c, _ = _client(cron_secret="")
    for path in CRON_PATHS:
        assert c.get(path, headers={"Authorization": "Bearer "}).status_code == 401


def test_cron_secret_is_compared_in_constant_time(monkeypatch):
    """固定時間比較是時序性質，行為測試看不出來——直接確認比較走的是
    `secrets.compare_digest`（改回 `!=` 這條會紅）。"""
    calls = []
    real = main_module.secrets.compare_digest

    def spy(a, b):
        calls.append((type(a), type(b)))
        return real(a, b)

    monkeypatch.setattr(main_module.secrets, "compare_digest", spy)
    c, _ = _client()
    c.get("/api/cron/warm-rate-cache", headers={"Authorization": "Bearer nope"})
    assert calls == [(bytes, bytes)]


def test_cron_endpoint_accepts_the_exact_bearer():
    c, _ = _client()
    r = c.get("/api/cron/cleanup-abandoned-owners",
              headers={"Authorization": f"Bearer {CRON}"})
    assert r.status_code == 200


# ---------- B-2 ----------

class _BrokenStorage(MemoryStorage):
    def get_rate_cache(self):
        raise RuntimeError(
            "connection to server at \"db.internal.example\" (10.0.0.5), "
            "user \"app_user\" failed")


def test_health_does_not_leak_storage_error_details():
    c, _ = _client(storage=_BrokenStorage())
    body = c.get("/api/health").json()
    assert body["storage"] == "unavailable"
    text = json.dumps(body)
    for leak in ("db.internal.example", "10.0.0.5", "app_user", "connection"):
        assert leak not in text


# ---------- B-3 ----------

def test_unexpected_engine_error_text_does_not_reach_the_client(monkeypatch):
    c, _ = _client()
    sid = c.post("/api/scenarios", json=NEW).json()["id"]

    def boom(*args, **kwargs):
        raise RuntimeError("internal detail: /srv/app/secret_path.py line 42")

    monkeypatch.setattr(service, "run_with_snapshot", boom)
    r = c.post(f"/api/scenarios/{sid}/refresh")
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail["stage"] == "analyze"                   # 分層照舊
    assert "secret_path" not in detail["message"]
    assert "internal detail" not in detail["message"]


# ---------- B-4 ----------

def _seed_audit(storage, n):
    for i in range(n):
        storage.append_audit_event(SuperUserAuditEvent(
            event_id=f"e{i}", ts=f"2026-09-25T00:00:{i:02d}+00:00",
            actor="superadmin", action="test", target_owner_id=None, detail=None))


@pytest.mark.parametrize("limit,expected", [(-5, 1), (0, 1), (3, 3), (10**9, 12)])
def test_audit_log_limit_is_clamped(limit, expected):
    c, storage = _client()
    _seed_audit(storage, 12)
    c.cookies.update(superadmin_cookies(storage))
    r = c.get("/api/superuser/audit-log", params={"limit": limit})
    assert r.status_code == 200
    assert len(r.json()) == expected


def test_audit_log_upper_bound_is_enforced_before_hitting_storage(monkeypatch):
    seen = []
    original = MemoryStorage.list_audit_events

    def spy(self, *, limit=200):
        seen.append(limit)
        return original(self, limit=limit)

    monkeypatch.setattr(MemoryStorage, "list_audit_events", spy)
    c, storage = _client()
    c.cookies.update(superadmin_cookies(storage))
    c.get("/api/superuser/audit-log", params={"limit": 10**9}).raise_for_status()
    assert seen == [main_module._AUDIT_LOG_MAX_LIMIT]


# ---------- B-5 ----------

def test_vercel_config_sets_baseline_security_headers():
    config = json.loads((ROOT / "vercel.json").read_text())
    rules = [r for r in config.get("headers", []) if r["source"] == "/(.*)"]
    assert rules, "所有路徑都要套安全 headers"
    headers = {h["key"].lower(): h["value"] for h in rules[0]["headers"]}
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "object-src 'none'" in headers["content-security-policy"]
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"


# ---------- B-6 ----------

def test_runtime_dependencies_are_pinned_and_mirrored():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    runtime = [d for d in project["dependencies"] if "platform_system" not in d]
    assert runtime and all("==" in d for d in runtime), runtime
    mirrored = {line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    assert set(project["dependencies"]) == mirrored


# ---------- B-7 ----------

# B-3（502 那一側）：adapter 包裝 FetchError 時只放例外類別名

def test_adapter_fetch_errors_do_not_carry_raw_exception_text(monkeypatch):
    from option_chaser.data import cboe
    from option_chaser.models import FetchError

    def boom(*args, **kwargs):
        raise OSError("connect to internal-proxy.example:3128 refused")

    with pytest.raises(FetchError) as info:
        cboe.fetch_chain("XYZ", http_get=boom)
    assert "internal-proxy" not in str(info.value)
    assert "OSError" in str(info.value)
    assert "internal-proxy" in str(info.value.__cause__)      # 原文仍在 cause


def test_secret_forms_cover_the_stripped_value():
    assert main_module._secret_forms("  hunter2 \n", None, "", "   ", "plain") == (
        "  hunter2 \n", "hunter2", "plain")
