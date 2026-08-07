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
    assert cached.market_day == TODAY.isoformat()


def test_underlying_returning_a_stale_curve_directly_does_not_count_as_a_fresh_success():
    """RC1（#87）：`underlying` 自己內部也可能有陳舊備援分支（例如
    `treasury.load_rate_curve()` 的本地檔案快取），回傳的曲線雖然不是
    `None`，但一樣不是「今天直接抓到」的。`market_day` 不該因此被誤判
    推進，否則同一天稍後的呼叫會被這筆假新鮮擋下來，不再嘗試真正的
    來源——這裡直接量 `market_day` 與 `last_success_at`，不是只看
    `curve.stale` 有沒有正確傳出去（那件事 `_resolve_rates` 那層已經
    測過）。"""
    import dataclasses

    storage = MemoryStorage()
    stale_curve = dataclasses.replace(CURVE, stale=True)
    calls = []

    def stale_underlying(d):
        calls.append(d)
        return stale_curve, "Treasury 曲線 2026-08-04（陳舊備援）"

    curve, note = cached_loader(storage, stale_underlying)(TODAY)

    assert curve == stale_curve
    assert curve.stale is True
    cached = storage.get_rate_cache()
    assert cached is not None
    # 陳舊曲線不算「今天直接成功」——不能讓下一次呼叫誤以為今天已經
    # 新鮮成功過而跳過真正的重試。
    assert cached.market_day is None
    assert cached.last_success_at is None


def test_second_call_within_the_same_market_day_reuses_the_cache():
    """一輪刷新 N 個劇本共用同一條——第二個劇本進來時今天已經成功過，
    不該再打一次資料源。"""
    storage = MemoryStorage()
    calls = []
    loader = cached_loader(storage, _underlying(calls))

    loader(TODAY)
    curve, note = loader(TODAY)

    assert len(calls) == 1
    assert curve == CURVE


def test_a_success_from_hours_ago_is_still_reused_within_the_same_market_day():
    """利率一天內不會劇烈變動——就算是好幾個小時前抓到的，只要還是
    同一個市場日，就不必重抓。這跟舊版「12 小時新鮮度窗」的差異正是
    這次修正的重點：時間差不重要，市場日有沒有變才重要。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-04", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-08-04（今天稍早）",
        market_day=TODAY.isoformat()))
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert calls == []
    assert curve == RateCurve(curve_date="2026-08-04", nodes=((1.0, 0.03),))
    assert note == "Treasury 曲線 2026-08-04（今天稍早）"


def test_next_market_day_refetches_even_though_it_was_fetched_minutes_ago():
    """反過來：就算上次成功是幾分鐘前的事，只要市場日已經換了，第一次
    有人需要時還是要重新 fetch——不能靠「還很新鮮」硬撐過市場日邊界。
    `attempted_day` 也明確設成昨天：不能只因為時間差夠短就沿用，
    這正是本測試要盯住的邊界情況。"""
    storage = MemoryStorage()
    yesterday = date(2026, 8, 4)
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-04", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-08-04", market_day=yesterday.isoformat(),
        attempted_day=yesterday.isoformat()))
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert calls == [TODAY]
    assert curve == CURVE
    assert note == "Treasury 曲線 2026-08-04"


def test_a_stale_fallback_reuse_from_yesterday_does_not_block_todays_first_try():
    """跟純失敗一樣的邊界情況，換成沿用緊急備援窗舊曲線那個分支：
    上一筆紀錄時間很近、`curve` 也不是 `None`（沿用了舊曲線），但那是
    **昨天**的嘗試留下的紀錄——今天的第一次請求還是要真的問一次底層
    來源，不能被這筆快要過期的舊紀錄擋下來。"""
    storage = MemoryStorage()
    yesterday = date(2026, 8, 4)
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-07-30", "nodes": [[1.0, 0.03]]},
        note="Treasury 曲線 2026-07-30（沿用快取，最新一次嘗試失敗：曲線不可得）",
        market_day=None, attempted_day=yesterday.isoformat()))
    calls = []

    curve, note = cached_loader(storage, _underlying(calls))(TODAY)

    assert calls == [TODAY]
    assert curve == CURVE


def test_a_recent_stale_fallback_from_today_is_deduped_and_stays_marked_stale():
    """RC1（#87）：短窗內重放同一筆「今天稍早沿用陳舊備援」紀錄時，
    stale 標記要跟著 `curve`／`note` 一起原樣重放，不能在 dedup 路徑上
    被悄悄洗白成看起來像新鮮抓到的。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds"),
        curve={"curve_date": "2026-08-01", "nodes": [[1.0, 0.03]], "stale": True},
        note="Treasury 曲線 2026-08-01（沿用快取，最新一次嘗試失敗：曲線不可得）",
        market_day=None, attempted_day=TODAY.isoformat()))
    calls = []

    curve, note = cached_loader(
        storage, _underlying(calls, note="不該被呼叫"))(TODAY)

    assert calls == []
    assert curve.stale is True


def test_a_recent_cached_failure_is_reused_without_retrying():
    """失敗也快取，同一輪刷新不會讓每個劇本各撞一次同樣會失敗的請求。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds"),
        curve=None, note="曲線不可得", attempted_day=TODAY.isoformat()))
    calls = []

    curve, note = cached_loader(
        storage, _underlying(calls, note="不該被呼叫"))(TODAY)

    assert calls == []
    assert curve is None
    assert note == "曲線不可得"


def test_a_cached_failure_does_not_block_retrying_for_long():
    """失敗的快取窗遠比成功共用的一整個市場日短——資料源恢復後，不該
    讓使用者卡在舊的失敗訊息裡到隔天才有機會重試。"""
    storage = MemoryStorage()
    storage.save_rate_cache(RateCacheEntry(
        fetched_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(
            timespec="seconds"),
        curve=None, note="曲線不可得", attempted_day=TODAY.isoformat()))
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

    # RC1（#87）：沿用陳舊備援窗的舊曲線要標成 stale=True，不能跟
    # 「今天真的成功抓到」顯示成同一態。
    assert curve == RateCurve(curve_date="2026-08-01", nodes=((1.0, 0.03),),
                              stale=True)
    assert curve.stale is True
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
