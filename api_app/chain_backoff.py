"""Cboe 429 韌性的控制狀態持久層（SCALE-04／#255，Scaling Foundation）。

包在任何 `Callable[[str], ChainSnapshot]`（今天是
`option_chaser.data.cboe.fetch_chain`）外面——與 `api_app/rate_cache.py`
／`treasury_cache.py`／`dividend_cache.py` 同一個「持久快取包住資料源」
的既有模式，差異是這裡包的不是「要不要重打」的快取，而是「上游現在
讓不讓我打」的限流控制狀態。

**鍵是 `source`（provider-global），不分 symbol**——`docs/spec/
scaling-foundation.md` §8.4 2026-09-06 訂正：沒有證據顯示 Cboe 的
429 限流是 per-symbol，若真是整個 provider 被限流，per-symbol 鍵會
讓使用者「換一個 symbol 繼續打」就繞過封鎖窗，等於 retry storm 換馬甲
繼續打上游。安全預設是整個來源一起封鎖。

**⚠ RL-19（紅線）：這一層完全不碰 chain payload／市場報價**——它只
讀寫 `ChainBackoffEntry`（純控制中繼資料），`snap`（`ChainSnapshot`）
只是原樣穿過這一層，從未被序列化進 backoff 狀態本身。

backoff 狀態讀寫失敗一律 fail-open（比照既有三層快取的既有哲學）：
視同沒有 backoff 狀態，不阻斷主抓取流程——backoff 是韌性機制本身，
它自己的故障不該變成新的單點失敗。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from option_chaser.models import ChainSnapshot, FetchError, RateLimitedError

from .storage import ChainBackoffEntry, Storage

# 上游沒給（或給的值解析不出來）`Retry-After` 時的保守預設封鎖窗。
# **可調，含調成 `timedelta(0)`＝停用**——這是明文要求的 rollback 手段
# （circuit breaker 誤開，會讓功能在 vendor 其實健康時仍不可用）。
DEFAULT_BACKOFF = timedelta(seconds=60)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_blocked_until(entry: ChainBackoffEntry | None) -> datetime | None:
    if entry is None or entry.blocked_until is None:
        return None
    try:
        return datetime.fromisoformat(entry.blocked_until)
    except ValueError:
        return None   # 讀不懂的時間戳視同沒有封鎖，fail-open


def _read(storage: Storage, source: str) -> ChainBackoffEntry | None:
    try:
        return storage.get_chain_backoff(source)
    except Exception:  # noqa: BLE001 — 讀取失敗視同沒有 backoff 狀態
        return None


def _write(storage: Storage, entry: ChainBackoffEntry) -> None:
    try:
        storage.save_chain_backoff(entry)
    except Exception:  # noqa: BLE001 — 寫入失敗不影響這次已經發生的抓取結果
        pass


def backoff_aware_fetch(storage: Storage, source: str,
                        underlying: Callable[[str], ChainSnapshot],
                        symbol: str, *,
                        default_backoff: timedelta = DEFAULT_BACKOFF
                        ) -> ChainSnapshot:
    """包住 `underlying`——呼叫前先查 `source` 的 provider-global
    backoff 狀態，窗口內直接短路（**`underlying` 完全不會被呼叫，
    零 upstream request**）；成功時清除封鎖狀態並更新
    `last_success_at`；遇到 `RateLimitedError`（HTTP 429）時記錄一次
    觀測並設定／延長封鎖窗（`retry_after_seconds` 有值就用它，否則用
    `default_backoff`）；其餘失敗（一般 `FetchError`／未預期例外）
    原樣往外拋、**不動 backoff 狀態**——那不是限流造成的，不該影響
    下一次是否嘗試。

    窗口內短路拋出一般 `FetchError`（不是 `RateLimitedError`）：這次
    呼叫根本沒有真的問過上游，用「限流專屬」例外型別描述它並不準確；
    且維持 `FetchError` 讓既有 `service.fetch_chain` 的
    `except FetchError: ... yfinance 備援` 邏輯原樣接住，不因為換了
    抓取路徑而改變既有降級鏈相容性。"""
    entry = _read(storage, source)
    blocked_until = _parse_blocked_until(entry)
    now = _now()
    if blocked_until is not None and now < blocked_until:
        raise FetchError(
            f"{source} 目前處於限流封鎖窗（至 {entry.blocked_until} 前不"
            "重打上游）")

    try:
        snap = underlying(symbol)
    except RateLimitedError as e:
        consecutive = (entry.consecutive_failures + 1) if entry is not None else 1
        wait = (timedelta(seconds=e.retry_after_seconds)
               if e.retry_after_seconds is not None else default_backoff)
        _write(storage, ChainBackoffEntry(
            source=source,
            blocked_until=(now + wait).isoformat(timespec="seconds"),
            retry_after_seconds=e.retry_after_seconds,
            consecutive_failures=consecutive,
            observed_at=_now_iso(),
            last_success_at=entry.last_success_at if entry is not None else None))
        raise

    _write(storage, ChainBackoffEntry(
        source=source, blocked_until=None, retry_after_seconds=None,
        consecutive_failures=0,
        observed_at=entry.observed_at if entry is not None else _now_iso(),
        last_success_at=_now_iso()))
    return snap
