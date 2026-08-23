"""Treasury 曲線列持久快取層——鍵是年份（PERF-03／#179）。

形狀逐一鏡射 `tests/test_api_dividend_cache.py`（同一套三態快取設計），
差異只在**鍵是年份**、且過去年份一旦成功即永久有效（沒有市場日／陳舊
窗的概念）。本檔案唯一真正重要的測試是
`test_a_past_years_rate_is_never_shadowed_by_the_current_years_cache`
——PIT 安全的核心不變量，見該測試 docstring。
"""
from datetime import date, datetime, timedelta, timezone

from api_app.storage import TreasuryYearCacheEntry
from api_app.storage.memory import MemoryStorage
from api_app.treasury_cache import cached_rate_curve_rows
from option_chaser.ratecurve import curve_asof

TODAY = date(2026, 8, 17)   # 當年＝2026
ROWS_2026 = (("2026-01-01", ((1.0, 0.041), (30.0, 0.043))),)


def _underlying(calls, rows=ROWS_2026):
    def fetch(from_date, to_date):
        calls.append((from_date, to_date))
        return rows
    return fetch


def test_first_call_reaches_the_underlying_fetch_and_caches_the_result():
    storage = MemoryStorage()
    calls = []

    got = cached_rate_curve_rows(storage, _underlying(calls))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ROWS_2026
    assert calls == [(date(2026, 1, 1), date(2026, 12, 31))]
    cached = storage.get_treasury_year_cache(2026)
    assert cached is not None and cached.market_day == TODAY.isoformat()


def test_second_call_within_the_same_market_day_reuses_the_cache():
    storage = MemoryStorage()
    calls = []
    fetch = cached_rate_curve_rows(storage, _underlying(calls))

    fetch(date(2026, 1, 1), date(2026, 12, 31), TODAY)
    got = fetch(date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert len(calls) == 1
    assert got == ROWS_2026


def test_a_success_from_hours_ago_is_still_reused_within_the_same_market_day():
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(
            timespec="seconds"),
        rows=[list(r) for r in ROWS_2026], note="Treasury 2026 年曲線（今天稍早）",
        market_day=TODAY.isoformat()))
    calls = []

    got = cached_rate_curve_rows(storage, _underlying(calls))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert calls == []
    assert got == ROWS_2026


def test_next_market_day_refetches_even_though_it_was_fetched_minutes_ago():
    storage = MemoryStorage()
    yesterday = date(2026, 8, 16)
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(
            timespec="seconds"),
        rows=[list(r) for r in ROWS_2026], note="Treasury 2026 年曲線",
        market_day=yesterday.isoformat(), attempted_day=yesterday.isoformat()))
    calls = []

    got = cached_rate_curve_rows(storage, _underlying(calls))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert calls == [(date(2026, 1, 1), date(2026, 12, 31))]
    assert got == ROWS_2026


def test_a_recent_cached_failure_is_reused_without_retrying():
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds"),
        rows=None, note="Treasury 曲線不可得", attempted_day=TODAY.isoformat()))
    calls = []

    got = cached_rate_curve_rows(
        storage, _underlying(calls, rows=()))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert calls == []
    assert got == ()


def test_a_cached_failure_does_not_block_retrying_for_long():
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(
            timespec="seconds"),
        rows=None, note="Treasury 曲線不可得", attempted_day=TODAY.isoformat()))
    calls = []

    got = cached_rate_curve_rows(storage, _underlying(calls))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert calls == [(date(2026, 1, 1), date(2026, 12, 31))]
    assert got == ROWS_2026


def test_underlying_fetch_failure_is_cached_too():
    storage = MemoryStorage()

    got = cached_rate_curve_rows(storage, lambda f, t: ())(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ()
    cached = storage.get_treasury_year_cache(2026)
    assert cached is not None
    assert cached.rows is None


def test_a_broken_cache_read_falls_back_to_calling_the_underlying_fetch():
    class BrokenStorage:
        def get_treasury_year_cache(self, year):
            raise RuntimeError("db 暫時連不上")

        def save_treasury_year_cache(self, entry):
            raise RuntimeError("db 暫時連不上")

    calls = []
    got = cached_rate_curve_rows(BrokenStorage(), _underlying(calls))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ROWS_2026
    assert calls == [(date(2026, 1, 1), date(2026, 12, 31))]


def test_rows_survive_a_round_trip_through_json_serialization():
    storage = MemoryStorage()

    cached_rate_curve_rows(storage, _underlying([]))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)
    got = cached_rate_curve_rows(
        storage, lambda f, t: (_ for _ in ()).throw(
            AssertionError("不該再呼叫底層來源")))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ROWS_2026


# ---------- 抓取失敗時沿用還沒過期的舊資料（7 天緊急備援窗，僅當年） ----------

def test_a_stale_but_recent_rows_are_preferred_over_falling_back_to_empty():
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(
            timespec="seconds"),
        rows=[list(r) for r in ROWS_2026], note="Treasury 2026 年曲線（3 天前）"))

    got = cached_rate_curve_rows(storage, lambda f, t: ())(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ROWS_2026


def test_rows_older_than_the_7_day_emergency_window_are_not_reused():
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026,
        fetched_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat(
            timespec="seconds"),
        rows=[list(r) for r in ROWS_2026], note="Treasury 2026 年曲線（8 天前）"))

    got = cached_rate_curve_rows(storage, lambda f, t: ())(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ()


def test_a_successful_fetch_records_when_it_succeeded():
    storage = MemoryStorage()

    cached_rate_curve_rows(storage, _underlying([]))(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert storage.get_treasury_year_cache(2026).last_success_at is not None


def test_underlying_raising_instead_of_returning_rows_is_tolerated():
    storage = MemoryStorage()

    def broken(from_date, to_date):
        raise RuntimeError("Treasury 來源自己的 bug")

    got = cached_rate_curve_rows(storage, broken)(
        date(2026, 1, 1), date(2026, 12, 31), TODAY)

    assert got == ()
    cached = storage.get_treasury_year_cache(2026)
    assert cached is not None and cached.rows is None
    assert "Treasury 來源自己的 bug" in cached.note


# ---------- 過去年份：一旦成功即永久有效 ----------

def test_a_past_year_success_from_long_ago_is_still_permanently_fresh():
    """過去年份不看 `fetched_at` 多舊、也不看 `market_day` 是否對得上
    今天——`year < today.year` 本身就是「永久有效」的唯一判準。"""
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2020, fetched_at="2020-06-01T00:00:00+00:00",
        rows=[["2020-01-01", [[1.0, 0.01]]]], note="Treasury 2020 年曲線",
        market_day="2020-06-01"))   # 跟 TODAY 差了 6 年，若誤判成不新鮮就會重打
    calls = []

    got = cached_rate_curve_rows(
        storage, _underlying(calls, rows=(("SHOULD-NOT-BE-CALLED", ()),)))(
        date(2020, 1, 1), date(2020, 12, 31), TODAY)

    assert calls == []
    assert got == (("2020-01-01", ((1.0, 0.01),)),)


def test_a_past_year_that_never_succeeded_still_retries():
    """過去年份沒有「永久有效」可言的前提是曾經成功過——一筆純失敗紀錄
    不該被永久當成「這年就是沒資料」，下一次呼叫仍要真的再試一次
    （沿用跟當年一樣的短窗去重機制，不是另一套規則）。"""
    storage = MemoryStorage()
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2020, fetched_at="2020-06-01T00:00:00+00:00",
        rows=None, note="Treasury 曲線不可得", attempted_day="2020-06-01"))
    calls = []

    got = cached_rate_curve_rows(storage, _underlying(calls, rows=ROWS_2026))(
        date(2020, 1, 1), date(2020, 12, 31), TODAY)

    assert calls == [(date(2020, 1, 1), date(2020, 12, 31))]
    assert got == ROWS_2026


def test_years_are_cached_independently_within_a_single_multi_year_call():
    """核心不變量：一次涵蓋兩個年份的查詢，各自獨立快取、互不干擾彼此
    的重試節奏（比照 `test_api_dividend_cache.test_symbols_are_cached_
    independently`，鍵換成年份）。"""
    storage = MemoryStorage()
    calls = []

    def underlying(from_date, to_date):
        calls.append(from_date.year)
        if from_date.year == 2025:
            return (("2025-06-01", ((1.0, 0.05),)),)
        return (("2026-06-01", ((1.0, 0.06),)),)

    got = cached_rate_curve_rows(storage, underlying)(
        date(2025, 6, 1), date(2026, 8, 17), TODAY)

    assert sorted(calls) == [2025, 2026]
    assert got == (("2025-06-01", ((1.0, 0.05),)), ("2026-06-01", ((1.0, 0.06),)))
    assert storage.get_treasury_year_cache(2025) is not None
    assert storage.get_treasury_year_cache(2026) is not None

    # 第二輪：2025（過去年份，永久有效）與 2026（當年，同市場日）都該
    # 直接沿用快取，不再打底層。
    got2 = cached_rate_curve_rows(
        storage, lambda f, t: (_ for _ in ()).throw(
            AssertionError("不該被呼叫")))(
        date(2025, 6, 1), date(2026, 8, 17), TODAY)
    assert got2 == got


def test_a_past_years_rate_is_never_shadowed_by_the_current_years_cache():
    """**這張票唯一真正重要的測試**（issue #179 AC 明文要求）：分別為
    2025 年與當年（2026）各自灌入互相不同、可辨識的假利率，快取都熱了
    之後，反覆查詢 `observation_date="2025-01-15"`，斷言拿到的永遠是
    2025-01-15 真正該有的利率，永遠不是當年的利率——PIT 安全的核心
    不變量，錯誤的快取鍵設計會**默默**產生錯誤數字，不會報錯。"""
    storage = MemoryStorage()
    ROWS_2025 = (("2025-01-01", ((1.0, 0.0111),)),)   # 可辨識：0.0111
    rows_2026 = (("2026-01-01", ((1.0, 0.0999),)),)   # 可辨識：0.0999，跟 2025 差很遠

    def underlying(from_date, to_date):
        return ROWS_2025 if from_date.year == 2025 else rows_2026

    fetch = cached_rate_curve_rows(storage, underlying)
    # 熱兩年的快取。
    fetch(date(2025, 1, 1), date(2026, 12, 31), TODAY)

    from option_chaser.ratecurve import par_to_continuous, rate_for_tenor
    expected_2025_rate = par_to_continuous(0.0111)
    expected_2026_rate = par_to_continuous(0.0999)

    for _ in range(5):   # 反覆查詢——不是只驗一次
        rows = fetch(date(2025, 1, 1), date(2026, 12, 31), TODAY)
        curve = curve_asof(rows, "2025-01-15")
        assert curve is not None
        assert rate_for_tenor(curve, 1.0) == expected_2025_rate
        assert rate_for_tenor(curve, 1.0) != expected_2026_rate
