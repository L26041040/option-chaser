"""Option chain 短效期快取——鍵是 symbol（PERF-06／#182）。

形狀逐一鏡射 `tests/test_api_treasury_cache.py`（同一套「包裝任意來源、
快取放儲存介面」設計），差異只在：這裡沒有市場日／年份的三態邏輯，
只有單一「距上次抓取是否超過 TTL」的判準——即時報價，短效期本身就是
正確語意，不是 point-in-time 正確性考量。
"""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from api_app import chain_cache
from api_app.chain_cache import cached_fetch_chain
from api_app.storage import ChainCacheEntry
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _underlying(calls, snap=None):
    payload = snap or load_snapshot(FIX)

    def fetch(symbol):
        calls.append(symbol)
        return payload
    return fetch


def test_first_call_reaches_the_underlying_fetch_and_caches_the_result():
    storage = MemoryStorage()
    calls = []

    got = cached_fetch_chain(storage, _underlying(calls))("XYZ")

    assert got == load_snapshot(FIX)
    assert calls == ["XYZ"]
    assert storage.get_chain_cache("XYZ") is not None


def test_second_call_within_the_ttl_reuses_the_cache_and_does_not_refetch():
    """核心不變量：同一批刷新裡對同一個 symbol 的第二個以後請求直接
    重用剛抓到的結果，不觸發新的 vendor chain 請求——這是本票存在的
    理由本身。"""
    storage = MemoryStorage()
    calls = []
    fetch = cached_fetch_chain(storage, _underlying(calls))

    fetch("XYZ")
    got = fetch("XYZ")

    assert len(calls) == 1
    assert got == load_snapshot(FIX)


def test_cache_expires_after_the_ttl_and_resumes_fetching_independently():
    """快取過期後恢復正常各自抓取。"""
    storage = MemoryStorage()
    stale_snap = load_snapshot(FIX)
    storage.save_chain_cache(ChainCacheEntry(
        symbol="XYZ",
        fetched_at=(datetime.now(timezone.utc) - chain_cache.CHAIN_CACHE_TTL
                   - timedelta(seconds=1)).isoformat(timespec="seconds"),
        snapshot=dataclasses.asdict(stale_snap)))
    calls = []

    got = cached_fetch_chain(storage, _underlying(calls))("XYZ")

    assert calls == ["XYZ"]
    assert got == load_snapshot(FIX)


def test_a_success_from_seconds_ago_is_still_reused_within_the_ttl():
    storage = MemoryStorage()
    snap = load_snapshot(FIX)
    storage.save_chain_cache(ChainCacheEntry(
        symbol="XYZ",
        fetched_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(
            timespec="seconds"),
        snapshot=dataclasses.asdict(snap)))
    calls = []

    got = cached_fetch_chain(storage, _underlying(calls))("XYZ")

    assert calls == []
    assert got == snap


def test_symbols_are_cached_independently():
    """一個劇本刷新 XYZ 不該讓另一個劇本刷新 SPY 共用同一筆快取。"""
    storage = MemoryStorage()
    calls = []
    xyz_snap = load_snapshot(FIX)
    spy_snap = dataclasses.replace(xyz_snap, symbol="SPY")

    def underlying(symbol):
        calls.append(symbol)
        return xyz_snap if symbol == "XYZ" else spy_snap

    fetch = cached_fetch_chain(storage, underlying)
    fetch("XYZ")
    fetch("SPY")
    assert calls == ["XYZ", "SPY"]

    # 第二輪：都在 TTL 內，都該直接沿用快取，不再打底層。
    fetch("XYZ")
    fetch("SPY")
    assert calls == ["XYZ", "SPY"]


def test_a_failed_fetch_is_not_cached_and_the_exception_propagates():
    """失敗不快取——這裡沒有陳舊備援的概念，呼叫端照舊直接看到例外，
    跟今天行為一致。"""
    storage = MemoryStorage()

    def broken(symbol):
        raise FetchError("報價來源掛了")

    with pytest.raises(FetchError):
        cached_fetch_chain(storage, broken)("XYZ")
    assert storage.get_chain_cache("XYZ") is None


def test_a_broken_cache_read_falls_back_to_calling_the_underlying_fetch():
    class BrokenStorage:
        def get_chain_cache(self, symbol):
            raise RuntimeError("db 暫時連不上")

        def save_chain_cache(self, entry):
            raise RuntimeError("db 暫時連不上")

    calls = []
    got = cached_fetch_chain(BrokenStorage(), _underlying(calls))("XYZ")

    assert got == load_snapshot(FIX)
    assert calls == ["XYZ"]


def test_snapshot_survives_a_round_trip_through_dict_serialization():
    storage = MemoryStorage()

    cached_fetch_chain(storage, _underlying([]))("XYZ")
    got = cached_fetch_chain(storage, lambda s: (_ for _ in ()).throw(
        AssertionError("不該再呼叫底層 fetch")))("XYZ")

    assert got == load_snapshot(FIX)
