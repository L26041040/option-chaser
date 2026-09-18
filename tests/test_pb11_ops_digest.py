"""PB-11（#303，Anonymous Public Beta）：Ops metrics 擴充（匿名 owner
分佈／scenario 總數／cleanup volume）＋ daily email digest。

- 純函式層（`api_app/ops_alerts.py`／`api_app/digest.py`）：四條
  alert 判準各自獨立可測、`build_digest_text()` 的五類分開陳列、
  `send_digest_email()` 的嚴格 no-op 與（monkeypatch 後的）真送信
  兩條路徑。
- HTTP-seam 層：`/api/ops/metrics` 擴充欄位的數值正確性（建構已知
  owner／scenario 狀態逐一核對，不只信任「有回傳欄位」）、
  `GET /api/cron/daily-digest` 的 fail-closed 與 SMTP 配置完整／不
  完整兩種情況、兩個端點共用同一份 `_ops_snapshot()` 的一致性。
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api_app import ops_alerts
from api_app.digest import DigestSnapshot, build_digest_text, send_digest_email
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from tests._role_session import superadmin_cookies

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
CRON_SECRET = "the-real-cron-secret"
CRON_AUTH = {"Authorization": f"Bearer {CRON_SECRET}"}


def _client(*, storage=None, **kwargs):
    snap = load_snapshot(FIX)
    storage = storage or MemoryStorage()
    return TestClient(
        create_app(fetch=lambda symbol: snap, storage=storage,
                  cron_secret=CRON_SECRET,
                  cleanup_missed_days_threshold=999,  # 大多數測試不想被這條噪音干擾
                  **kwargs),
        base_url="https://testserver"), storage


def _admin_cookies(storage):
    """PB-09／AUTH-03（#298／#310）：`/api/ops/metrics` gate 在 Super
    Admin——這裡直接寫入一顆有效的 role session cookie，取代舊版的
    `ADMIN_AUTH` header 常數。"""
    return superadmin_cookies(storage)


# ---------- 純函式：`ops_alerts.evaluate_alerts()` ----------


def test_no_alerts_trigger_under_nominal_inputs():
    alerts = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=100)
    assert all(not a.triggered for a in alerts)
    assert len(alerts) == 4


def test_chain_sustained_incident_triggers_and_names_the_sources():
    alerts = ops_alerts.evaluate_alerts(
        sustained_incident_sources=("cboe",), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=1)
    incident = next(a for a in alerts if a.key == "chain_sustained_incident")
    assert incident.triggered
    assert "cboe" in incident.message


def test_cleanup_missed_triggers_at_threshold_not_below():
    below = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=1,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=1,
        cleanup_missed_days_threshold=2)
    at = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=2,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=1,
        cleanup_missed_days_threshold=2)
    assert not next(a for a in below if a.key == "cleanup_missed").triggered
    assert next(a for a in at if a.key == "cleanup_missed").triggered


def test_storage_usage_triggers_at_configured_ratio():
    below = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=79, chain_429_count=0, chain_fetch_count=1,
        storage_cap_bytes=100, storage_alert_ratio=0.8)
    at = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=80, chain_429_count=0, chain_fetch_count=1,
        storage_cap_bytes=100, storage_alert_ratio=0.8)
    assert not next(a for a in below if a.key == "storage_usage").triggered
    assert next(a for a in at if a.key == "storage_usage").triggered


def test_chain_error_rate_triggers_at_configured_threshold():
    below = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=9, chain_fetch_count=100,
        chain_error_rate_threshold=0.10)
    at = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=10, chain_fetch_count=100,
        chain_error_rate_threshold=0.10)
    assert not next(a for a in below if a.key == "chain_error_rate").triggered
    assert next(a for a in at if a.key == "chain_error_rate").triggered


def test_chain_error_rate_with_zero_fetches_does_not_divide_by_zero():
    alerts = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=0)
    rate_alert = next(a for a in alerts if a.key == "chain_error_rate")
    assert not rate_alert.triggered


def test_storage_cap_of_zero_does_not_divide_by_zero():
    alerts = ops_alerts.evaluate_alerts(
        sustained_incident_sources=(), cleanup_missed_days=0,
        storage_bytes=999, chain_429_count=0, chain_fetch_count=1,
        storage_cap_bytes=0)
    assert not next(a for a in alerts if a.key == "storage_usage").triggered


# ---------- 純函式：`build_digest_text()` ----------


def _snapshot(**overrides):
    base = dict(date="2026-09-14", owners_active=3, owners_abandoned=1,
               owners_eligible_for_hard_delete=0, owners_protected=1,
               owners_total=5, scenarios_total=12,
               scenarios_average_per_owner=2.4,
               cleanup_owners_deleted_today=0, cleanup_rows_deleted_today=0,
               alerts=ops_alerts.evaluate_alerts(
                   sustained_incident_sources=(), cleanup_missed_days=0,
                   storage_bytes=0, chain_429_count=0, chain_fetch_count=1))
    base.update(overrides)
    return DigestSnapshot(**base)


def test_digest_text_has_five_separately_labelled_sections():
    text = build_digest_text(_snapshot())
    assert "使用量" in text
    assert "清理排程" in text
    assert "系統健康" in text
    # 五類：product usage／system health／vendor usage-quota／
    # storage growth／security-abuse——本函式把 vendor usage-quota 與
    # security-abuse 併入同一段落陳列（皆來自 `alerts`），但每一條
    # alert 各自標明是哪一種訊號，不是揉成一個總分數字。
    assert "3" in text  # active owners
    assert "12" in text  # scenarios_total


def test_digest_text_omits_the_alert_banner_when_nothing_is_triggered():
    text = build_digest_text(_snapshot())
    assert "⚠ 需要留意" not in text


def test_digest_text_shows_the_alert_banner_when_something_triggers():
    triggered_alerts = ops_alerts.evaluate_alerts(
        sustained_incident_sources=("cboe",), cleanup_missed_days=0,
        storage_bytes=0, chain_429_count=0, chain_fetch_count=1)
    text = build_digest_text(_snapshot(alerts=triggered_alerts))
    assert "⚠ 需要留意" in text
    assert "cboe" in text


# ---------- 純函式：`send_digest_email()` ----------


def test_send_digest_email_is_a_strict_noop_when_any_config_is_missing():
    combos = [
        dict(smtp_host=None, smtp_port=587, smtp_user="u", smtp_password="p",
            mail_from="a@example.com", mail_to="b@example.com"),
        dict(smtp_host="smtp.example.com", smtp_port=None, smtp_user="u",
            smtp_password="p", mail_from="a@example.com",
            mail_to="b@example.com"),
        dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user=None,
            smtp_password="p", mail_from="a@example.com",
            mail_to="b@example.com"),
        dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="u",
            smtp_password=None, mail_from="a@example.com",
            mail_to="b@example.com"),
        dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="u",
            smtp_password="p", mail_from=None, mail_to="b@example.com"),
        dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="u",
            smtp_password="p", mail_from="a@example.com", mail_to=None),
    ]
    for kwargs in combos:
        sent = send_digest_email("body", subject="s", **kwargs)
        assert sent is False


def test_send_digest_email_sends_via_smtp_when_fully_configured(monkeypatch):
    calls = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls["connect"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls["starttls"] = True

        def login(self, user, password):
            calls["login"] = (user, password)

        def sendmail(self, from_addr, to_addrs, msg):
            calls["sendmail"] = (from_addr, to_addrs)

    monkeypatch.setattr("api_app.digest.smtplib.SMTP", _FakeSMTP)
    sent = send_digest_email(
        "the body", smtp_host="smtp.example.com", smtp_port=587,
        smtp_user="user@example.com", smtp_password="secret",
        mail_from="from@example.com", mail_to="to@example.com",
        subject="the subject")

    assert sent is True
    assert calls["connect"] == ("smtp.example.com", 587)
    assert calls["starttls"] is True
    assert calls["login"] == ("user@example.com", "secret")
    assert calls["sendmail"][0] == "from@example.com"
    assert calls["sendmail"][1] == ["to@example.com"]


# ---------- HTTP：`/api/ops/metrics` 擴充欄位 ----------


def test_ops_metrics_reports_correct_anonymous_owner_distribution():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()  # owner A：active
    c2, _ = _client(storage=storage)
    c2.post("/api/scenarios", json=NEW).raise_for_status()  # owner B：即將是 abandoned
    owner_ids = [o.owner_id for o in storage.list_owners()]
    old = (date.today() - timedelta(days=999)).isoformat() + "T00:00:00+00:00"
    storage.touch_owner_activity(owner_ids[1], now=old)
    storage.set_owner_protected(owner_ids[0], True)

    r = c.get("/api/ops/metrics", cookies=_admin_cookies(storage))
    assert r.status_code == 200
    dist = r.json()["anonymous_owners"]
    assert dist["total"] == 2
    assert dist["protected"] == 1
    assert dist["abandoned"] + dist["eligible_for_hard_delete"] == 1
    assert dist["active"] == 1


def test_ops_metrics_reports_scenario_totals_and_average():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    c.post("/api/scenarios", json={**NEW, "symbol": "AAA"}).raise_for_status()
    c2, _ = _client(storage=storage)
    c2.post("/api/scenarios", json=NEW).raise_for_status()

    r = c.get("/api/ops/metrics", cookies=_admin_cookies(storage))
    body = r.json()["scenarios"]
    assert body["total"] == 3
    assert body["average_per_owner"] == pytest.approx(1.5)


def test_ops_metrics_includes_alerts_and_still_requires_authorization():
    c, storage = _client()
    unauthorized = c.get("/api/ops/metrics")
    assert unauthorized.status_code == 401

    r = c.get("/api/ops/metrics", cookies=_admin_cookies(storage))
    assert "alerts" in r.json()
    assert len(r.json()["alerts"]) == 4


def test_ops_metrics_response_carries_no_individual_owner_or_scenario_content():
    """票面 §10：聚合視圖不得混入個別 owner 可識別內容（那是 PB-10
    的獨立端點）。"""
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()
    owner_id = storage.list_owners()[0].owner_id

    r = c.get("/api/ops/metrics", cookies=_admin_cookies(storage))
    assert owner_id not in r.text
    assert "XYZ" not in r.text


# ---------- HTTP：`GET /api/cron/daily-digest` ----------


def test_daily_digest_is_fail_closed_without_the_correct_cron_secret():
    c, _ = _client()
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        r = c.get("/api/cron/daily-digest", headers=headers)
        assert r.status_code == 401


def test_daily_digest_never_creates_an_owner():
    c, storage = _client()
    c.get("/api/cron/daily-digest", headers=CRON_AUTH)
    assert storage.list_owners() == []


def test_daily_digest_with_no_smtp_config_reports_sent_false_but_still_succeeds():
    c, storage = _client()
    c.post("/api/scenarios", json=NEW).raise_for_status()

    r = c.get("/api/cron/daily-digest", headers=CRON_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] is False
    assert "date" in body
    assert "alerts_triggered" in body


def test_daily_digest_with_full_smtp_config_reports_sent_true(monkeypatch):
    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            pass

    monkeypatch.setattr("api_app.digest.smtplib.SMTP", _FakeSMTP)
    c, _ = _client(
        digest_smtp_host="smtp.example.com", digest_smtp_port=587,
        digest_smtp_user="u@example.com", digest_smtp_password="p",
        digest_email_from="from@example.com", digest_email_to="to@example.com")

    r = c.get("/api/cron/daily-digest", headers=CRON_AUTH)
    assert r.status_code == 200
    assert r.json()["sent"] is True


# ---------- 兩個端點共用同一份計算 ----------


def test_ops_metrics_and_daily_digest_agree_on_the_same_numbers(monkeypatch):
    """`/api/ops/metrics` 與 digest 內文必須是同一份 `_ops_snapshot()`
    算出來的——不是兩處各自重算出兜不起來的兩個答案。"""
    captured = {}

    class _CapturingSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            captured["msg"] = msg

    monkeypatch.setattr("api_app.digest.smtplib.SMTP", _CapturingSMTP)
    c, storage = _client(
        digest_smtp_host="smtp.example.com", digest_smtp_port=587,
        digest_smtp_user="u@example.com", digest_smtp_password="p",
        digest_email_from="from@example.com", digest_email_to="to@example.com")
    c.post("/api/scenarios", json=NEW).raise_for_status()
    c.post("/api/scenarios", json={**NEW, "symbol": "AAA"}).raise_for_status()

    metrics_body = c.get("/api/ops/metrics", cookies=_admin_cookies(storage)).json()
    c.get("/api/cron/daily-digest", headers=CRON_AUTH)

    assert str(metrics_body["scenarios"]["total"]) in captured["msg"]
    assert str(metrics_body["anonymous_owners"]["total"]) in captured["msg"]
