"""配息資料持久快取層（#123）——包在任何 `DividendLoader` 外面，資料源
本身完全不在這層的管轄範圍。形狀逐一鏡射
`tests/test_api_rate_cache.py`，差異只在**鍵是 symbol**、陳舊備援窗
是 90 天（不是 7 天）。
"""
import dataclasses
from datetime import date, datetime, timedelta, timezone

from api_app.dividend_cache import cached_loader
from api_app.storage import DividendCacheEntry
from api_app.storage.memory import MemoryStorage
from option_chaser.dividends import DividendHistory, DividendRecord

HISTORY = DividendHistory(symbol="TLT", as_of="2026-08-04", source="yahoo",
                          distributions=(DividendRecord("2026-08-03", 0.33),))
TODAY = date(2026, 8, 5)


def _underlying(calls, history=HISTORY, note="配息資料 yahoo（2026-08-04，1 筆）"):
    def loader(symbol, today):
        calls.append((symbol, today))
        return history, note
    return loader


def test_first_call_reaches_the_underlying_loader_and_caches_the_result():
    storage = MemoryStorage()
    calls = []

    history, note = cached_loader(storage, _underlying(calls))("TLT", TODAY)

    assert history == HISTORY
    assert note == "配息資料 yahoo（2026-08-04，1 筆）"
    assert calls == [("TLT", TODAY)]
    cached = storage.get_dividend_cache("TLT")
    assert cached is not None and cached.note == note
    assert cached.market_day == TODAY.isoformat()


def test_underlying_returning_a_stale_history_directly_does_not_count_as_fresh():
    storage = MemoryStorage()
    stale_history = dataclasses.replace(HISTORY, stale=True)
    calls = []

    def stale_underlying(symbol, today):
        calls.append((symbol, today))
        return stale_history, "配息資料 yahoo（陳舊備援）"

    history, note = cached_loader(storage, stale_underlying)("TLT", TODAY)

    assert history == stale_history
    assert history.stale is True
    cached = storage.get_dividend_cache("TLT")
    assert cached is not None
    assert cached.market_day is None
    assert cached.last_success_at is None


def test_second_call_within_the_same_market_day_reuses_the_cache():
    storage = MemoryStorage()
    calls = []
    loader = cached_loader(storage, _underlying(calls))

    loader("TLT", TODAY)
    history, note = loader("TLT", TODAY)

    assert len(calls) == 1
    assert history == HISTORY


def test_a_success_from_hours_ago_is_still_reused_within_the_same_market_day():
    storage = MemoryStorage()
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(
            timespec="seconds"),
        history={"symbol": "TLT", "as_of": "2026-08-04", "source": "yahoo",
                "distributions": [["2026-08-03", 0.33]], "stale": False},
        note="配息資料 yahoo（今天稍早）", market_day=TODAY.isoformat()))
    calls = []

    history, note = cached_loader(storage, _underlying(calls))("TLT", TODAY)

    assert calls == []
    assert history == HISTORY
    assert note == "配息資料 yahoo（今天稍早）"


def test_next_market_day_refetches_even_though_it_was_fetched_minutes_ago():
    storage = MemoryStorage()
    yesterday = date(2026, 8, 4)
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(
            timespec="seconds"),
        history={"symbol": "TLT", "as_of": "2026-08-04", "source": "yahoo",
                "distributions": [["2026-08-03", 0.33]], "stale": False},
        note="配息資料 yahoo（2026-08-04）", market_day=yesterday.isoformat(),
        attempted_day=yesterday.isoformat()))
    calls = []

    history, note = cached_loader(storage, _underlying(calls))("TLT", TODAY)

    assert calls == [("TLT", TODAY)]
    assert history == HISTORY


def test_a_recent_cached_failure_is_reused_without_retrying():
    storage = MemoryStorage()
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds"),
        history=None, note="配息資料不可得", attempted_day=TODAY.isoformat()))
    calls = []

    history, note = cached_loader(
        storage, _underlying(calls, note="不該被呼叫"))("TLT", TODAY)

    assert calls == []
    assert history is None
    assert note == "配息資料不可得"


def test_a_cached_failure_does_not_block_retrying_for_long():
    storage = MemoryStorage()
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(
            timespec="seconds"),
        history=None, note="配息資料不可得", attempted_day=TODAY.isoformat()))
    calls = []

    history, note = cached_loader(storage, _underlying(calls))("TLT", TODAY)

    assert calls == [("TLT", TODAY)]
    assert history == HISTORY


def test_underlying_loader_failure_is_cached_too():
    storage = MemoryStorage()

    history, note = cached_loader(
        storage, lambda s, d: (None, "配息資料不可得"))("TLT", TODAY)

    assert history is None
    cached = storage.get_dividend_cache("TLT")
    assert cached is not None
    assert cached.history is None
    assert cached.note == "配息資料不可得"


def test_a_broken_cache_read_falls_back_to_calling_the_underlying_loader():
    class BrokenStorage:
        def get_dividend_cache(self, symbol):
            raise RuntimeError("db 暫時連不上")

        def save_dividend_cache(self, entry):
            raise RuntimeError("db 暫時連不上")

    calls = []
    history, note = cached_loader(BrokenStorage(), _underlying(calls))("TLT", TODAY)

    assert history == HISTORY
    assert calls == [("TLT", TODAY)]


def test_cache_survives_a_history_round_trip_through_dict_serialization():
    storage = MemoryStorage()

    cached_loader(storage, _underlying([]))("TLT", TODAY)
    history, note = cached_loader(storage, lambda s, d: (_ for _ in ()).throw(
        AssertionError("不該再呼叫底層 loader")))("TLT", TODAY)

    assert history == HISTORY


def test_symbols_are_cached_independently():
    """核心不變量：一個劇本抓 TLT 不該讓另一個劇本抓 SPY 共用同一筆
    快取，也不該互相擋住彼此的重試節奏。"""
    storage = MemoryStorage()
    tlt_calls, spy_calls = [], []

    cached_loader(storage, _underlying(tlt_calls))("TLT", TODAY)
    spy_history = DividendHistory(symbol="SPY", as_of="2026-08-04", source="yahoo",
                                  distributions=())
    cached_loader(storage, _underlying(spy_calls, history=spy_history,
                                       note="配息資料 yahoo（0 筆）"))("SPY", TODAY)

    # 各自都成功抓過一次，且沒有互相干擾（重打各自的 loader 一次）
    assert len(tlt_calls) == 1 and len(spy_calls) == 1
    assert storage.get_dividend_cache("TLT").history["symbol"] == "TLT"
    assert storage.get_dividend_cache("SPY").history["symbol"] == "SPY"

    # 第二輪：都在同一市場日內，都該直接沿用快取，不再打底層
    cached_loader(storage, _underlying(tlt_calls, note="不該被呼叫"))("TLT", TODAY)
    cached_loader(storage, _underlying(spy_calls, note="不該被呼叫"))("SPY", TODAY)
    assert len(tlt_calls) == 1 and len(spy_calls) == 1


# ---------- 抓取失敗時沿用還沒過期的舊資料（90 天緊急備援窗） ----------

def test_a_stale_but_recent_history_is_preferred_over_falling_back_to_none():
    storage = MemoryStorage()
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(
            timespec="seconds"),
        history={"symbol": "TLT", "as_of": "2026-07-01", "source": "yahoo",
                "distributions": [["2026-06-01", 0.32]], "stale": False},
        note="配息資料 yahoo（2026-07-01）"))

    history, note = cached_loader(
        storage, lambda s, d: (None, "這次抓取失敗"))("TLT", TODAY)

    assert history == DividendHistory(
        symbol="TLT", as_of="2026-07-01", source="yahoo",
        distributions=(DividendRecord("2026-06-01", 0.32),), stale=True)
    assert history.stale is True
    assert "配息資料 yahoo（2026-07-01）" in note
    assert "這次抓取失敗" in note


def test_a_history_older_than_the_90_day_emergency_window_is_not_reused():
    storage = MemoryStorage()
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT",
        fetched_at=(datetime.now(timezone.utc) - timedelta(days=91)).isoformat(
            timespec="seconds"),
        history={"symbol": "TLT", "as_of": "2026-05-01", "source": "yahoo",
                "distributions": [["2026-04-01", 0.30]], "stale": False},
        note="配息資料 yahoo（2026-05-01）"))

    history, note = cached_loader(
        storage, lambda s, d: (None, "這次抓取失敗"))("TLT", TODAY)

    assert history is None
    assert note == "這次抓取失敗"


def test_no_prior_history_at_all_falls_straight_through_to_the_failure_note():
    storage = MemoryStorage()

    history, note = cached_loader(
        storage, lambda s, d: (None, "這次抓取失敗"))("TLT", TODAY)

    assert history is None
    assert note == "這次抓取失敗"


def test_a_successful_fetch_records_when_it_succeeded():
    storage = MemoryStorage()

    cached_loader(storage, _underlying([]))("TLT", TODAY)

    assert storage.get_dividend_cache("TLT").last_success_at is not None


def test_underlying_provider_raising_instead_of_returning_a_failure_tuple_is_tolerated():
    storage = MemoryStorage()

    def broken(symbol, today):
        raise RuntimeError("provider 自己的 bug")

    history, note = cached_loader(storage, broken)("TLT", TODAY)

    assert history is None
    assert "provider 自己的 bug" in note
    cached = storage.get_dividend_cache("TLT")
    assert cached is not None and cached.history is None
