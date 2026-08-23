"""完整 option chain 快照的短效期快取——鍵是 symbol（PERF-06／#182）。

開站整批刷新時，共用同一個 symbol 的多個劇本各自序列觸發一次完全相同
的完整 chain 抓取（前端既有逐劇本序列送出刷新請求的行為，本票不改、
零前端改動）；同一批刷新裡第二個以後命中同一個 symbol 的請求直接重用
剛抓到的結果，不再對外打 vendor。

跟 `rate_cache.py`／`dividend_cache.py`／`treasury_cache.py` 同一套
「包在任何抓取來源外面、快取放儲存介面」設計——serverless 一輪刷新對
N 個劇本各自觸發一次獨立呼叫，彼此不共享行程內記憶體，快取因此得放在
儲存介面而不是行程內變數（同一個理由，見那三個模組各自的說明）。

**新鮮度判準刻意不同**：這裡是即時報價，不是需要 point-in-time 正確性
的歷史資料，短效期（`CHAIN_CACHE_TTL`）本身就是正確語意，不需要比照
市場日三態設計（同一市場日重用／隔天重新嘗試那一套）。**失敗不快取**
——這裡沒有「陳舊備援」的概念，抓取失敗時呼叫端照舊直接看到例外，跟
今天行為一致，只影響「成功之後」的重用路徑。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Callable

from option_chaser.data.snapshot import snapshot_from_dict
from option_chaser.models import ChainSnapshot

from .storage import ChainCacheEntry, Storage

# 一次整批刷新是前端逐劇本序列送出的一串 HTTP request，通常在幾秒到
# 一兩分鐘內跑完；設得比這個量級再寬裕一些——短到不會讓「這輪還沒刷完」
# 的後續請求看到明顯過期的報價，長到真的能吃到同一輪對同一個 symbol
# 的重複命中。具名、可調整——沒有查到「一次整批刷新通常花多久」的
# 精確量測，用一個保守值。
CHAIN_CACHE_TTL = timedelta(minutes=2)


def _age(entry: ChainCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None   # 讀不懂的時間戳當舊，跟其餘快取模組同一個原則
    return datetime.now(timezone.utc) - fetched_at


def cached_fetch_chain(storage: Storage,
                       underlying: Callable[[str], ChainSnapshot],
                       ) -> Callable[[str], ChainSnapshot]:
    """回傳一個行為與 `underlying` 相同、但先查短效期快取的抓鏈函式。"""

    def fetch(symbol: str) -> ChainSnapshot:
        try:
            cached = storage.get_chain_cache(symbol)
        except Exception:  # noqa: BLE001 — 快取讀取失敗視同沒有快取
            cached = None
        if cached is not None:
            age = _age(cached)
            if age is not None and age < CHAIN_CACHE_TTL:
                return snapshot_from_dict(cached.snapshot)

        # 失敗不快取：`underlying` 丟出的例外原樣往上炸，呼叫端既有的
        # FetchError 處理（V4／#52 的 502 分層）不受影響。
        snap = underlying(symbol)

        try:
            storage.save_chain_cache(ChainCacheEntry(
                symbol=symbol,
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                snapshot=dataclasses.asdict(snap)))
        except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
            pass
        return snap

    return fetch
