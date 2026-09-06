"""SCALE-04（#255，Scaling Foundation Cboe 429 韌性）：`chain_backoff`
provider-global 控制狀態表——同一來源被限流時，封鎖窗涵蓋該來源底下
全部 symbol（不分 symbol，見 `docs/spec/scaling-foundation.md` §8.4
2026-09-06 訂正）。

## AC 對照

- AC-1：`test_a_second_symbol_is_blocked_with_zero_vendor_calls_
  during_the_window`
- AC-2：`test_parse_retry_after_*`（delta-seconds／HTTP-date／
  missing／invalid 四種案例）
- AC-3：`test_a_successful_fetch_after_the_window_clears_backoff_
  state_and_allows_other_symbols`
- AC-4：`test_rate_limited_error_is_a_fetch_error_subclass`／
  `test_generic_failure_does_not_touch_backoff_state`
- AC-5：`test_chain_backoff_entry_has_no_market_data_fields`
- AC-6：`test_storage_failures_are_fail_open`
- AC-7：`test_backoff_can_be_disabled_via_zero_default_backoff`
"""
import math
from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.error import HTTPError

import pytest

from api_app import chain_backoff
from api_app.storage import ChainBackoffEntry
from api_app.storage.memory import MemoryStorage
from option_chaser.data import cboe
from option_chaser.models import FetchError, RateLimitedError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- AC-2：Retry-After 解析（delta-seconds／HTTP-date／missing／invalid） ----------

def test_parse_retry_after_delta_seconds():
    assert cboe.parse_retry_after("34") == 34.0


def test_parse_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=120)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    parsed = cboe.parse_retry_after(header)
    assert parsed is not None
    assert 110 <= parsed <= 130   # 允許測試執行耗時的些微誤差


def test_parse_retry_after_missing():
    assert cboe.parse_retry_after(None) is None
    assert cboe.parse_retry_after("") is None


def test_parse_retry_after_invalid():
    assert cboe.parse_retry_after("not-a-valid-value") is None
    assert cboe.parse_retry_after("-5") is None   # 負值不合理，視同無效


# ---------- cboe.fetch_chain()：429 抬成 RateLimitedError ----------

def _http_error(code: int, retry_after: str | None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://cdn.cboe.com/x", code, "test", headers, None)


def test_cboe_fetch_chain_raises_rate_limited_error_on_429_with_delta_seconds():
    def http_get(url):
        raise _http_error(429, "34")

    with pytest.raises(RateLimitedError) as exc_info:
        cboe.fetch_chain("XYZ", http_get=http_get)
    assert exc_info.value.retry_after_seconds == 34.0


def test_cboe_fetch_chain_raises_rate_limited_error_on_429_without_retry_after():
    def http_get(url):
        raise _http_error(429, None)

    with pytest.raises(RateLimitedError) as exc_info:
        cboe.fetch_chain("XYZ", http_get=http_get)
    assert exc_info.value.retry_after_seconds is None


def test_cboe_fetch_chain_non_429_http_error_stays_a_plain_fetch_error():
    def http_get(url):
        raise _http_error(500, None)

    with pytest.raises(FetchError) as exc_info:
        cboe.fetch_chain("XYZ", http_get=http_get)
    assert not isinstance(exc_info.value, RateLimitedError)


# ---------- AC-4：例外階層 ----------

def test_rate_limited_error_is_a_fetch_error_subclass():
    assert issubclass(RateLimitedError, FetchError)


# ---------- AC-5：結構性——零市場資料欄位 ----------

def test_chain_backoff_entry_has_no_market_data_fields():
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(ChainBackoffEntry)}
    banned_substrings = ("bid", "ask", "quote", "contract", "strike",
                        "premium", "volatility", "volume", "spot", "chain",
                        "payload")
    for name in field_names:
        for banned in banned_substrings:
            assert banned not in name.lower(), (name, banned)
    assert field_names == {"source", "blocked_until", "retry_after_seconds",
                           "consecutive_failures", "observed_at",
                           "last_success_at"}


# ---------- backoff_aware_fetch()：核心行為 ----------

def test_a_second_symbol_is_blocked_with_zero_vendor_calls_during_the_window():
    """AC-1：symbol A 觸發 429 backoff 後，同一 source 底下、從未被
    打過的 symbol B 在窗口內也必須被擋下，且 vendor call count=0。"""
    storage = MemoryStorage()
    calls: list[str] = []

    def underlying(symbol: str):
        calls.append(symbol)
        raise RateLimitedError("429", retry_after_seconds=60.0)

    with pytest.raises(FetchError):
        chain_backoff.backoff_aware_fetch(storage, "cboe", underlying, "A")
    assert calls == ["A"]

    # symbol B，從未被打過，同一個 source 底下應該直接被擋，vendor 不
    # 應該被呼叫。
    with pytest.raises(FetchError) as exc_info:
        chain_backoff.backoff_aware_fetch(storage, "cboe", underlying, "B")
    assert calls == ["A"]   # underlying 完全沒有再被呼叫過
    assert not isinstance(exc_info.value, RateLimitedError)   # 這次是短路，不是真的又打了一次上游


def test_a_successful_fetch_after_the_window_clears_backoff_state_and_allows_other_symbols():
    """AC-3：窗口結束後成功抓取會清掉 blocked state／consecutive
    failure，更新 last_success_at；之後其他 symbol 可正常打 source。"""
    storage = MemoryStorage()

    # 直接寫入一筆「窗口已過」的 backoff 狀態，模擬時間已經走到封鎖窗
    # 結束之後（比照既有 rate_cache／dividend_cache 測試手法：直接
    # 操作已存的紀錄，不依賴真的等待）。
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(
        timespec="seconds")
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=past, retry_after_seconds=60.0,
        consecutive_failures=3, observed_at=_now_iso(),
        last_success_at=None))

    sentinel = object()

    def underlying(symbol: str):
        return sentinel

    result = chain_backoff.backoff_aware_fetch(storage, "cboe", underlying, "B")
    assert result is sentinel

    entry = storage.get_chain_backoff("cboe")
    assert entry.blocked_until is None
    assert entry.consecutive_failures == 0
    assert entry.retry_after_seconds is None
    assert entry.last_success_at is not None

    # 之後任何 symbol（含先前從未打過的）都能正常打
    result2 = chain_backoff.backoff_aware_fetch(storage, "cboe", underlying, "C")
    assert result2 is sentinel


def test_generic_failure_does_not_touch_backoff_state():
    """AC-4：一般失敗（非 429）不是限流，不該影響 backoff 狀態——
    下一次仍然正常嘗試，不會被誤判成封鎖。"""
    storage = MemoryStorage()

    def flaky(symbol: str):
        raise FetchError("暫時性網路錯誤")

    with pytest.raises(FetchError):
        chain_backoff.backoff_aware_fetch(storage, "cboe", flaky, "A")

    assert storage.get_chain_backoff("cboe") is None   # 完全沒有寫入任何狀態

    # 下一次呼叫（換一個會成功的 underlying）應該正常執行，不受剛才
    # 的一般失敗影響。
    def ok(symbol: str):
        return "snapshot"

    assert chain_backoff.backoff_aware_fetch(storage, "cboe", ok, "A") == "snapshot"


def test_default_backoff_is_used_when_retry_after_is_absent():
    storage = MemoryStorage()

    def underlying(symbol: str):
        raise RateLimitedError("429", retry_after_seconds=None)

    before = datetime.now(timezone.utc)
    with pytest.raises(FetchError):
        chain_backoff.backoff_aware_fetch(
            storage, "cboe", underlying, "A",
            default_backoff=timedelta(seconds=45))

    entry = storage.get_chain_backoff("cboe")
    blocked_until = datetime.fromisoformat(entry.blocked_until)
    delta = (blocked_until - before).total_seconds()
    assert 40 <= delta <= 50   # 接近 45 秒（允許測試耗時誤差）
    assert entry.retry_after_seconds is None   # 誠實記錄「上游沒給」


def test_consecutive_failures_increment_across_repeated_429s():
    storage = MemoryStorage()

    def underlying(symbol: str):
        raise RateLimitedError("429", retry_after_seconds=0.0)

    for expected in (1, 2, 3):
        with pytest.raises(FetchError):
            chain_backoff.backoff_aware_fetch(storage, "cboe", underlying, "A")
        assert storage.get_chain_backoff("cboe").consecutive_failures == expected


# ---------- AC-6：backoff 狀態讀寫失敗 fail-open ----------

def test_storage_failures_are_fail_open():
    """backoff 狀態自己的讀寫故障不該讓主抓取流程跟著死掉——比照既有
    三層快取（rate/dividend/treasury_year）既有哲學。"""

    class BrokenStorage:
        def get_chain_backoff(self, source):
            raise RuntimeError("db 暫時連不上")

        def save_chain_backoff(self, entry):
            raise RuntimeError("db 暫時連不上")

    def ok(symbol: str):
        return "snapshot"

    # 讀取失敗 → 視同沒有 backoff 狀態，仍然正常呼叫 underlying
    assert chain_backoff.backoff_aware_fetch(
        BrokenStorage(), "cboe", ok, "A") == "snapshot"

    def rate_limited(symbol: str):
        raise RateLimitedError("429", retry_after_seconds=10.0)

    # 寫入失敗 → 原本的例外仍然照樣往外拋，不因為記錄失敗而被吞掉或
    # 換成別的例外
    with pytest.raises(RateLimitedError):
        chain_backoff.backoff_aware_fetch(BrokenStorage(), "cboe",
                                          rate_limited, "A")


# ---------- AC-7：可調成 0 停用（rollback 手段） ----------

def test_backoff_can_be_disabled_via_zero_default_backoff():
    """封鎖窗長度可調（含調成 0＝停用）：把 `default_backoff` 設成 0，
    下一次呼叫立刻不再被擋（`retry_after_seconds=None` 時走
    `default_backoff`，設成 0 秒等於這個來源實質上不再被封鎖）。"""
    storage = MemoryStorage()
    calls: list[str] = []

    def flaky_then_ok(symbol: str):
        calls.append(symbol)
        if len(calls) == 1:
            raise RateLimitedError("429", retry_after_seconds=None)
        return "snapshot"

    with pytest.raises(FetchError):
        chain_backoff.backoff_aware_fetch(
            storage, "cboe", flaky_then_ok, "A",
            default_backoff=timedelta(seconds=0))

    # default_backoff=0 秒 → 幾乎立刻可以再打
    result = chain_backoff.backoff_aware_fetch(
        storage, "cboe", flaky_then_ok, "A",
        default_backoff=timedelta(seconds=0))
    assert result == "snapshot"
    assert calls == ["A", "A"]   # 第二次真的又呼叫了 underlying，沒被卡住
