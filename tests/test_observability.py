"""Sentry 接線（PB-13／#293，Anonymous Public Beta）——`api_app/
observability.py` 的行為契約：未設定 `SENTRY_DSN` 時整個模組是
no-op，設定時才真的初始化並套用 PII scrubbing。
"""
import pytest

from api_app import observability


def test_init_sentry_is_a_noop_without_sentry_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.init_sentry() is False


def test_init_sentry_does_not_import_sentry_sdk_when_unset(monkeypatch):
    """本票紅線：未設定 DSN 的部署不得多付任何 import 成本。"""
    import sys

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delitem(sys.modules, "sentry_sdk", raising=False)

    observability.init_sentry()

    assert "sentry_sdk" not in sys.modules


def test_init_sentry_initializes_when_dsn_is_set(monkeypatch):
    calls = []

    class FakeSentrySdk:
        @staticmethod
        def init(**kwargs):
            calls.append(kwargs)

    import sys
    monkeypatch.setitem(sys.modules, "sentry_sdk", FakeSentrySdk)
    monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/1")

    assert observability.init_sentry() is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://example@sentry.io/1"
    # FREE-FIRST：不開 performance tracing。
    assert calls[0]["traces_sample_rate"] == 0.0
    assert calls[0]["send_default_pii"] is False


def test_known_env_secrets_picks_up_configured_secrets(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-secret-value")
    monkeypatch.setenv("OPS_SECRET", "ops-secret-value")
    monkeypatch.delenv("ADMIN_SECRET", raising=False)

    secrets = observability.known_env_secrets()

    assert "cron-secret-value" in secrets
    assert "ops-secret-value" in secrets


def test_known_env_secrets_skips_unset_names(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("OPS_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert observability.known_env_secrets() == ()


@pytest.mark.parametrize("header", ["Cookie", "cookie", "Authorization"])
def test_scrub_event_redacts_sensitive_headers(header):
    event = {"request": {"headers": {header: "secret-value"}, "cookies": {"oc_owner": "tok"}}}

    scrubbed = observability._scrub_event(event, ())

    assert scrubbed["request"]["headers"][header] == "[redacted]"
    assert "cookies" not in scrubbed["request"]


def test_scrub_event_strips_query_string_from_the_url():
    event = {"request": {"url": "https://example.com/api/health?owner=abc"}}

    scrubbed = observability._scrub_event(event, ())

    assert scrubbed["request"]["url"] == "https://example.com/api/health"


def test_scrub_event_masks_known_secrets_in_the_message():
    event = {"message": "leaked postgresql://user:pass@host/db in the log"}

    scrubbed = observability._scrub_event(
        event, secrets=("postgresql://user:pass@host/db",))

    assert "postgresql://user:pass@host/db" not in scrubbed["message"]
    assert "[redacted]" in scrubbed["message"]


def test_scrub_event_masks_bearer_tokens_in_exception_values():
    event = {"exception": {"values": [{"value": "auth failed: Bearer abc123XYZ"}]}}

    scrubbed = observability._scrub_event(event, ())

    assert "abc123XYZ" not in scrubbed["exception"]["values"][0]["value"]
