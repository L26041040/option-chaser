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

**已知取捨**（`/code-review` Spec 軸抓到、施工後追加修正）：這個快取
沒有「同一批刷新」的真正邊界概念，只有 wall-clock TTL——結構上無法
區分「同一輪批次刷新裡的另一個劇本剛好共用這個 symbol」跟「使用者對
**同一個**劇本連續按了兩次刷新」，兩者在 TTL 視窗內都會拿到同一份
快取結果。TTL 因此刻意壓在**秒級**而非分鐘級：大到足以吃到前端逐劇本
序列送出的同批次請求（通常在數秒內陸續發出），小到讓「使用者過一段
時間再手動重新整理」這種明顯不同的操作意圖，幾乎不會落在窗內看到
沒有任何提示的舊資料。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Callable

from option_chaser.data.snapshot import snapshot_from_dict
from option_chaser.models import ChainSnapshot

from .storage import ChainCacheEntry, Storage

CHAIN_CACHE_TTL = timedelta(seconds=15)


def _age(entry: ChainCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None   # 讀不懂的時間戳當舊，跟其餘快取模組同一個原則
    return datetime.now(timezone.utc) - fetched_at


def cached_fetch_chain(storage: Storage,
                       underlying: Callable[[str], ChainSnapshot],
                       *, ttl: timedelta = CHAIN_CACHE_TTL,
                       ) -> Callable[[str], ChainSnapshot]:
    """回傳一個行為與 `underlying` 相同、但先查短效期快取的抓鏈函式。

    `ttl` 可選、預設 `CHAIN_CACHE_TTL`——顯式參數而不是要求呼叫端
    monkeypatch 模組常數：`main.py` 的 `create_app()` 用既有 DI 慣例
    （`fetch`／`rate_loader`／`dividend_loader` 皆可注入）把它一併
    暴露成 `chain_cache_ttl` 參數，測試需要停用快取重用時直接傳
    `timedelta(0)`，不必伸手改模組內部狀態。"""

    def fetch(symbol: str) -> ChainSnapshot:
        try:
            cached = storage.get_chain_cache(symbol)
        except Exception:  # noqa: BLE001 — 快取讀取失敗視同沒有快取
            cached = None
        if cached is not None:
            age = _age(cached)
            if age is not None and age < ttl:
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
