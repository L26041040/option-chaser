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
