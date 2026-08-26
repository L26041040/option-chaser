"""診斷骨幹（DG-02／#145）：event／emit／redaction／correlation ID。

本檔案不接任何 subsystem——測試的是能力本身，不是 Historical IV 的
接線（那在 `test_api_diagnostics.py`／DG-03 的測試裡）。
"""
from __future__ import annotations

import json
import logging

import pytest

from api_app import diagnostics


class _RecordingStorage:
    def __init__(self):
        self.events = []

    def append_diagnostic(self, event):
        self.events.append(event)


class _ExplodingStorage:
    def append_diagnostic(self, event):
        raise RuntimeError("storage 掛了")


# ---------- sanitize_string ----------

def test_sanitize_string_truncates_long_values():
    long_text = "x" * 1000
    got = diagnostics.sanitize_string(long_text)
    assert len(got) <= 500
    assert got.endswith("…[截斷]")


def test_sanitize_string_short_values_are_untouched():
    assert diagnostics.sanitize_string("hello") == "hello"


def test_sanitize_string_masks_bearer_tokens():
    got = diagnostics.sanitize_string("Authorization: Bearer sk-abc123XYZ")
    assert "sk-abc123XYZ" not in got
    assert "[redacted]" in got


def test_sanitize_string_masks_token_query_params():
    got = diagnostics.sanitize_string(
        "https://api.example.com/x?token=SECRET123&date=2026-08-01")
    assert "SECRET123" not in got
    assert "date=2026-08-01" in got


def test_sanitize_string_masks_database_urls():
    got = diagnostics.sanitize_string(
        "connection refused: postgres://user:pw@host:5432/db")
    assert "user:pw@host" not in got
    assert "[redacted]" in got


def test_sanitize_string_masks_known_current_secrets():
    """已知現行祕密值（設定中的 provider token、DATABASE_URL）逐字比對——
    即使沒有落入任何樣式規則，只要字串裡出現這個值就換成 [redacted]。"""
    got = diagnostics.sanitize_string(
        "vendor said: invalid key MYPLAINTOKEN999",
        secrets=("MYPLAINTOKEN999",))
    assert "MYPLAINTOKEN999" not in got
    assert "[redacted]" in got


# ---------- sanitize_context ----------

def test_sanitize_context_drops_keys_not_on_the_whitelist():
    got = diagnostics.sanitize_context(
        {"symbol": "TLT", "authorization": "Bearer sk-abc", "cookie": "sid=1"})
    assert got == {"symbol": "TLT"}


def test_sanitize_context_drops_none_values():
    """只顯示實際存在的欄位——None 在產生時就拿掉，不是留給前端過濾。"""
    got = diagnostics.sanitize_context({"symbol": "TLT", "expiration": None})
    assert got == {"symbol": "TLT"}
    assert "expiration" not in got


def test_sanitize_context_sanitizes_string_values_too():
    got = diagnostics.sanitize_context(
        {"vendor_errmsg": "token=SECRET leaked in errmsg"})
    assert "SECRET" not in got["vendor_errmsg"]


def test_sanitize_context_leaves_non_string_values_alone():
    got = diagnostics.sanitize_context({"raw_rows": 42, "found": True})
    assert got == {"raw_rows": 42, "found": True}


# ---------- correlation ID ----------

def test_new_correlation_id_is_unique():
    assert diagnostics.new_correlation_id() != diagnostics.new_correlation_id()


def test_correlation_scope_binds_and_restores():
    assert diagnostics.current_correlation_id() is None
    with diagnostics.correlation_scope("cid-abc") as cid:
        assert cid == "cid-abc"
        assert diagnostics.current_correlation_id() == "cid-abc"
    assert diagnostics.current_correlation_id() is None


def test_correlation_scope_generates_one_when_not_given():
    with diagnostics.correlation_scope() as cid:
        assert cid
        assert diagnostics.current_correlation_id() == cid


def test_nested_correlation_scopes_restore_the_outer_one():
    with diagnostics.correlation_scope("outer"):
        with diagnostics.correlation_scope("inner"):
            assert diagnostics.current_correlation_id() == "inner"
        assert diagnostics.current_correlation_id() == "outer"


# ---------- emit() ----------

def test_emit_writes_to_storage_and_returns_the_event():
    storage = _RecordingStorage()
    with diagnostics.correlation_scope("cid-1"):
        event = diagnostics.emit(
            storage, subsystem="historical_iv", stage="vendor_fetch",
            severity="error", message="boom", ts="2026-08-15T00:00:00+00:00",
            symbol="TLT")
    assert event is not None
    assert storage.events == [event]
    assert event.correlation_id == "cid-1"
    assert event.subsystem == "historical_iv"
    assert event.stage == "vendor_fetch"
    assert event.severity == "error"
    assert event.context == {"symbol": "TLT"}
    assert event.event_id


def test_emit_uses_the_current_correlation_id_without_being_told():
    storage = _RecordingStorage()
    with diagnostics.correlation_scope("cid-auto"):
        diagnostics.emit(storage, subsystem="historical_iv", stage="cache",
                         severity="info", message="ok",
                         ts="2026-08-15T00:00:00+00:00")
    assert storage.events[0].correlation_id == "cid-auto"


def test_emit_generates_a_correlation_id_when_none_is_bound():
    storage = _RecordingStorage()
    diagnostics.emit(storage, subsystem="historical_iv", stage="cache",
                     severity="info", message="ok",
                     ts="2026-08-15T00:00:00+00:00")
    assert storage.events[0].correlation_id


def test_emit_sanitizes_the_message_too():
    storage = _RecordingStorage()
    diagnostics.emit(
        storage, subsystem="historical_iv", stage="vendor_fetch",
        severity="error", message="failed with token=SECRETXYZ",
        ts="2026-08-15T00:00:00+00:00")
    assert "SECRETXYZ" not in storage.events[0].message


def test_emit_masks_known_secrets_passed_in(caplog):
    storage = _RecordingStorage()
    diagnostics.emit(
        storage, subsystem="historical_iv", stage="vendor_fetch",
        severity="error", message="vendor said MYSECRETTOKEN was invalid",
        ts="2026-08-15T00:00:00+00:00", secrets=("MYSECRETTOKEN",))
    assert "MYSECRETTOKEN" not in storage.events[0].message


def test_emit_does_not_raise_when_storage_fails():
    """診斷絕不能成為新的故障源——storage 掛了，`emit()` 不拋例外。event
    物件本身（構造與 log 都已成功）仍照樣回傳，因為呼叫端會拿它組進
    這次 request 的 in-response diagnostics（DG-03），那件事不依賴
    storage 是否寫入成功。"""
    storage = _ExplodingStorage()
    got = diagnostics.emit(storage, subsystem="historical_iv", stage="cache",
                           severity="info", message="ok",
                           ts="2026-08-15T00:00:00+00:00")
    assert got is not None
    assert got.message == "ok"


def test_emit_logs_a_parseable_json_line(caplog):
    storage = _RecordingStorage()
    with caplog.at_level(logging.INFO, logger="option_chaser.diagnostics"):
        event = diagnostics.emit(
            storage, subsystem="historical_iv", stage="vendor_fetch",
            severity="error", message="boom", ts="2026-08-15T00:00:00+00:00",
            symbol="TLT")
    lines = [r.message for r in caplog.records
            if r.name == "option_chaser.diagnostics"]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event_id"] == event.event_id
    assert parsed["correlation_id"] == event.correlation_id
    assert parsed["subsystem"] == "historical_iv"
    assert parsed["context"] == {"symbol": "TLT"}


# ---------- user_facing（PC-03／#201） ----------

@pytest.mark.parametrize("severity,expected", [
    ("error", True), ("warning", True), ("info", False),
])
def test_emit_default_user_facing_mirrors_severity(severity, expected):
    """省略 `user_facing` 時的預設規則：warning／error 視為
    user-facing，info 視為工程可見度——這是本票唯一定義一次的規則。"""
    storage = _RecordingStorage()
    event = diagnostics.emit(storage, subsystem="historical_iv",
                             stage="vendor_fetch", severity=severity,
                             message="m", ts="2026-08-15T00:00:00+00:00")
    assert event.user_facing is expected


def test_emit_user_facing_can_be_explicitly_overridden_against_the_default():
    """`user_facing` 是具名參數，能覆蓋預設規則——這是 PC-04 之後四項
    覆寫賴以掛上去的機制：即使 severity 是 warning，呼叫端仍能顯式說
    這件事不該讓使用者看到。"""
    storage = _RecordingStorage()
    event = diagnostics.emit(storage, subsystem="historical_iv",
                             stage="backfill", severity="warning",
                             user_facing=False, message="m",
                             ts="2026-08-15T00:00:00+00:00")
    assert event.user_facing is False

    event2 = diagnostics.emit(storage, subsystem="historical_iv",
                              stage="cache", severity="info",
                              user_facing=True, message="m",
                              ts="2026-08-15T00:00:00+00:00")
    assert event2.user_facing is True


def test_emit_user_facing_is_not_swallowed_into_context():
    """`user_facing` 走具名參數這條路，不會被 `**context` 收集、也不會
    被 `sanitize_context()` 的欄位白名單靜默丟棄——它是 `DiagnosticEvent`
    自己的欄位，不是 `context` dict 裡的一個 key。"""
    storage = _RecordingStorage()
    event = diagnostics.emit(storage, subsystem="historical_iv",
                             stage="backfill", severity="warning",
                             user_facing=False, message="m",
                             ts="2026-08-15T00:00:00+00:00", symbol="TLT")
    assert "user_facing" not in event.context
    assert event.context == {"symbol": "TLT"}
    assert event.user_facing is False


def test_emit_logging_failure_does_not_block_the_storage_write(monkeypatch):
    """log 那一步失敗（例如序列化爆掉）不該連帶讓 storage 也寫不進去——
    兩條路徑各自獨立失敗、互不牽連。"""
    storage = _RecordingStorage()
    monkeypatch.setattr(diagnostics, "_log_line",
                        lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    got = diagnostics.emit(storage, subsystem="historical_iv", stage="cache",
                           severity="info", message="ok",
                           ts="2026-08-15T00:00:00+00:00")
    assert got is not None
    assert storage.events == [got]
