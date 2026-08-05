"""利率曲線持久快取層（#67）——包在任何 `RateCurveLoader` 外面，資料源
本身（誰提供曲線）完全不在這層的管轄範圍：換源（#74）不需要動這裡，
`test_provider_is_swappable_without_touching_the_caching_layer` 用一個
假 provider 走完整條路徑直接證明這點。

一輪刷新可能對 N 個劇本各打一次 `/refresh`（各自獨立的 serverless
呼叫，彼此不共享行程內記憶體），要讓 N 個劇本共用同一條曲線，只能靠
一個跨呼叫的持久層——這裡測的正是「快取新鮮就不再呼叫底層 loader」。
"""
from datetime import date, datetime, timedelta, timezone

from api_app.rate_cache import cached_loader
from api_app.storage import RateCacheEntry
from api_app.storage.memory import MemoryStorage
from option_chaser.ratecurve import RateCurve

CURVE = RateCurve(curve_date="2026-08-04", nodes=((1.0, 0.04),))
TODAY = date(2026, 8, 5)


def _underlying(calls, curve=CURVE, note="Treasury 曲線 2026-08-04"):
    def loader(d):
        calls.append(d)
        return curve, note
    return loader


def test_first_call_reaches_the_underlying_loader_and_caches_the_result():
    storage = MemoryStorage()
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert curve == CURVE
    assert note == "Treasury 曲線 2026-08-04"
    assert calls == [TODAY]
    cached = storage.get_rate_cache()
    assert cached is not None and cached.note == note


def test_second_call_within_the_freshness_window_reuses_the_cache():
    """一輪刷新 N 個劇本共用同一條——第二個劇本進來時快取還新鮮，
    不該再打一次資料源。"""
    storage = MemoryStorage()
    calls = []
    loader = cached_loader(storage, _underlying(calls))

    loader(TODAY)
    curve, note = loader(TODAY)

    assert len(calls) == 1
    assert curve == CURVE


def test_stale_success_cache_is_refetched():
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=13)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-01", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-08-01（舊）"))
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert calls == [TODAY]
    assert curve == CURVE
    assert note == "Treasury 曲線 2026-08-04"


def test_a_recent_cached_failure_is_reused_without_retrying():
    """失敗也快取，同一輪刷新不會讓每個劇本各撞一次同樣會失敗的請求。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds"),
        curve=None, note="曲線不可得"))
    calls = []

    curve, note = cached_loader(
        storage, _underlying(calls, note="不該被呼叫"))(TODAY)

    assert calls == []
    assert curve is None
    assert note == "曲線不可得"


def test_a_cached_failure_does_not_block_retrying_for_long():
    """失敗的快取窗遠比成功短——資料源恢復後，不該讓使用者卡在舊的
    失敗訊息裡到 12 小時後才有機會重試。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(
            timespec="seconds"),
        curve=None, note="曲線不可得"))
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert calls == [TODAY]
    assert curve == CURVE


def test_underlying_loader_failure_is_cached_too():
    storage = MemoryStorage()

    curve, note = cached_loader(storage, lambda d: (None, "曲線不可得"))(TODAY)

    assert curve is None
    cached = storage.get_rate_cache()
    assert cached is not None
    assert cached.curve is None
    assert cached.note == "曲線不可得"


def test_provider_is_swappable_without_touching_the_caching_layer():
    """接縫在哪裡：換一個完全不同的 underlying（不是 Treasury），這層
    行為原封不動——它從頭到尾不知道 loader 背後是誰，也不必知道。"""
    storage = MemoryStorage()
    fake_curve = RateCurve(curve_date="2099-01-01", nodes=((2.0, 0.05),))

    def fake_provider(d):
        return fake_curve, "假來源 2099-01-01"

    curve, note = cached_loader(storage, fake_provider)(TODAY)

    assert curve == fake_curve
    assert note == "假來源 2099-01-01"


def test_a_broken_cache_read_falls_back_to_calling_the_underlying_loader():
    """快取層本身的問題（例如 Neon 暫時連不上）不該讓利率取得跟著死掉，
    更不該讓整次分析失敗——退回直接呼叫底層來源。跟 `option_chaser.
    data.treasury` 既有的「快取讀寫失敗一律視為無快取、不影響本次分析」
    是同一個哲學，套用在這個新的持久層上。"""
    class BrokenStorage:
        def get_rate_cache(self):
            raise RuntimeError("db 暫時連不上")

        def save_rate_cache(self, entry):
            raise RuntimeError("db 暫時連不上")

    calls = []
    curve, note = cached_loader(BrokenStorage(), _underlying(calls))(TODAY)

    assert curve == CURVE
    assert calls == [TODAY]


def test_cache_survives_a_curve_round_trip_through_dict_serialization():
    """存進去的是 `curve_to_dict()` 的結果，取回來要能還原成同一條
    `RateCurve`，不是一路傳裸 dataclass。"""
    storage = MemoryStorage()

    cached_loader(storage, _underlying([]))(TODAY)
    curve, note = cached_loader(storage, lambda d: (_ for _ in ()).throw(
        AssertionError("不該再呼叫底層 loader")))(TODAY)

    assert curve == CURVE


# ---------- 抓取失敗時沿用還沒過期的舊曲線（緊急備援窗） ----------

def test_a_stale_but_recent_curve_is_preferred_over_falling_back_to_the_fixed_rate():
    """舊曲線雖然過了 12 小時新鮮度窗，但還在 7 天緊急備援窗內、且這次
    抓取失敗——優先沿用舊曲線，不平白蓋成 None（讓引擎退回固定 4%）。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=13)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-01", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-08-01"))

    curve, note = cached_loader(
        storage, lambda d: (None, "這次抓取失敗"))(TODAY)

    assert curve == RateCurve(curve_date="2026-08-01", nodes=((1.0, 0.03),))
    assert "Treasury 曲線 2026-08-01" in note
    assert "這次抓取失敗" in note


def test_falling_back_to_the_stale_curve_still_resets_the_freshness_clock():
    """沿用舊曲線那個分支也要重設 `fetched_at`——否則下一個劇本進來時
    同樣判定「該重抓了」，一輪刷新的 N 個劇本會把同一個失敗中的來源
    打好幾次。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=13)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-01", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-08-01"))
    calls = []

    cached_loader(storage, _underlying(calls, curve=None,
                                       note="這次抓取失敗"))(TODAY)
    cached_loader(storage, _underlying(calls, curve=None,
                                       note="不該被呼叫"))(TODAY)

    assert len(calls) == 1


def test_a_curve_older_than_the_emergency_fallback_window_is_not_reused():
    """緊急備援窗也有極限——舊曲線超過 7 天，不再假裝它還貼近市場。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-07-28", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-07-28"))

    curve, note = cached_loader(
        storage, lambda d: (None, "這次抓取失敗"))(TODAY)

    assert curve is None
    assert note == "這次抓取失敗"


def test_no_prior_curve_at_all_falls_straight_through_to_the_failure_note():
    storage = MemoryStorage()

    curve, note = cached_loader(
        storage, lambda d: (None, "這次抓取失敗"))(TODAY)

    assert curve is None
    assert note == "這次抓取失敗"


# ---------- `/api/health` 的「最後一次成功」獨立於最近一次嘗試 ----------

def test_a_successful_fetch_records_when_it_succeeded():
    storage = MemoryStorage()

    cached_loader(storage, _underlying([]))(TODAY)

    assert storage.get_rate_cache().last_success_at is not None


def test_last_success_at_survives_a_subsequent_failure():
    storage = MemoryStorage()
    cached_loader(storage, _underlying([]))(TODAY)
    first_success_at = storage.get_rate_cache().last_success_at
    # 把這筆快取推到失敗窗（5 分鐘）之外，逼下一次呼叫真的再打一次底層。
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=13)).isoformat(
            timespec="seconds"),
        curve=storage.get_rate_cache().curve,
        note=storage.get_rate_cache().note,
        last_success_at=first_success_at))

    cached_loader(storage, lambda d: (None, "這次失敗了"))(TODAY)

    assert storage.get_rate_cache().last_success_at == first_success_at


def test_last_success_at_survives_even_past_the_emergency_fallback_window():
    """就算舊曲線久到連緊急備援都不再沿用，「最後一次成功的時間」這個
    事實仍然不能被抹掉。"""
    storage = MemoryStorage()
    old_success = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(
        timespec="seconds")
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=old_success,
        curve={"curve_date": "2026-07-28", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-07-28", last_success_at=old_success))

    curve, note = cached_loader(storage, lambda d: (None, "曲線不可得"))(TODAY)

    assert curve is None
    assert storage.get_rate_cache().last_success_at == old_success


def test_underlying_provider_raising_instead_of_returning_a_failure_tuple_is_tolerated():
    """#74 換源後，未來的 provider 若沒規規矩矩回傳 (None, note) 而是直接
    拋例外，不該讓整條分析路徑跟著炸成 500。"""
    storage = MemoryStorage()

    def broken(d):
        raise RuntimeError("provider 自己的 bug")

    curve, note = cached_loader(storage, broken)(TODAY)

    assert curve is None
    assert "provider 自己的 bug" in note
    cached = storage.get_rate_cache()
    assert cached is not None and cached.curve is None
