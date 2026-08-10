"""配息資料的持久快取層（#123）。

包在任何 `DividendLoader`（`option_chaser.service.DividendLoader`）
外面，形狀逐一比照 `api_app/rate_cache.py`——同一套「同一市場日成功
抓過一次就共用、失敗走短窗重試、抓取失敗但快取還沒過緊急備援窗就沿用
舊資料並標 stale」設計。**差異只有兩處**（皆為研究文件
`docs/research/dividend-yield-source-selection.md` §9／§11 的既有結論）：

1. **鍵是 symbol**：q 是標的的性質，不是全站單一值——`Storage` 走的是
   `get_dividend_cache(symbol)`／`save_dividend_cache(entry)`，不是
   `rate_cache.py` 的單一全站狀態。
2. **陳舊備援窗是 90 天，不是 7 天**：分配是月頻事件而非日頻，7 天窗
   會讓一次短暫斷線就把使用者踢回 q=0（已知會印 +81% 的狀態）。
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from option_chaser.data.dividends import CACHE_MAX_AGE_DAYS as _UNDERLYING_STALE_DAYS
from option_chaser.dividends import DividendHistory, history_from_dict, history_to_dict
from option_chaser.service import DividendLoader

from .storage import DividendCacheEntry, Storage

_FAILURE_MAX_AGE = timedelta(minutes=5)   # 與 rate_cache.py 同一數字，同一理由
# 研究 §9：90 天，非利率沿用的 7 天。與 `data/dividends.py` 本地檔案快取
# 的 `CACHE_MAX_AGE_DAYS` 用同一個數字——這層（Neon）與底層（本地檔案）
# 兩層各自獨立判斷是否過窗，數字一致只是巧合式的一致（同一份研究結論），
# 不是共享同一個常數的耦合。
_STALE_FALLBACK_MAX_AGE = timedelta(days=_UNDERLYING_STALE_DAYS)


def _age(entry: DividendCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None
    return datetime.now(timezone.utc) - fetched_at


def _success_is_fresh(entry: DividendCacheEntry, today: date) -> bool:
    return entry.history is not None and entry.market_day == today.isoformat()


def _recent_attempt(entry: DividendCacheEntry, today: date) -> bool:
    if entry.attempted_day != today.isoformat():
        return False
    age = _age(entry)
    return age is not None and age < _FAILURE_MAX_AGE


def cached_loader(storage: Storage, underlying: DividendLoader) -> DividendLoader:
    """回傳一個行為與 `underlying` 相同、但先查（per-symbol）快取的
    `DividendLoader`。"""

    def loader(symbol: str, today: date) -> tuple[DividendHistory | None, str]:
        try:
            cached = storage.get_dividend_cache(symbol)
        except Exception:  # noqa: BLE001 — 快取讀取失敗視同沒有快取
            cached = None
        if cached is not None and _success_is_fresh(cached, today):
            return history_from_dict(cached.history), cached.note
        if cached is not None and _recent_attempt(cached, today):
            return (history_from_dict(cached.history) if cached.history is not None
                    else None), cached.note

        try:
            history, note = underlying(symbol, today)
        except Exception as e:  # noqa: BLE001 — 收斂成失敗結果，不讓例外往上炸
            history, note = None, f"配息來源丟出例外：{e}"

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 只在這次真的成功「直接抓到」時前進（同 rate_cache.py 的
        # `fetched_fresh` 判準）；沿用下面緊急備援窗舊資料那個分支不算。
        fetched_fresh = history is not None and not history.stale
        last_success_at = now if fetched_fresh else (
            cached.last_success_at if cached is not None else None)
        market_day = today.isoformat() if fetched_fresh else (
            cached.market_day if cached is not None else None)

        if history is None and cached is not None and cached.history is not None:
            age = _age(cached)
            if age is not None and age < _STALE_FALLBACK_MAX_AGE:
                history = dataclasses.replace(history_from_dict(cached.history),
                                              stale=True)
                note = f"{cached.note}（沿用快取，最新一次嘗試失敗：{note}）"

        try:
            storage.save_dividend_cache(DividendCacheEntry(
                symbol=symbol, fetched_at=now,
                history=history_to_dict(history) if history is not None else None,
                note=note, last_success_at=last_success_at,
                market_day=market_day, attempted_day=today.isoformat()))
        except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
            pass
        return history, note

    return loader
