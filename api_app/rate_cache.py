"""利率曲線的持久快取層（#67）。

包在任何 `RateCurveLoader`（`option_chaser.service.RateCurveLoader`）
外面——資料源本身（誰提供曲線、怎麼抓）完全不在這層的管轄範圍，換源
（#74）只需要換掉 `underlying`，這層一行都不用改。現有的
`service.default_rate_curve_loader`（Treasury）只是暫時填在接縫後面
的實作，不是這裡的選型結果。

一輪刷新可能對 N 個劇本各自觸發一次獨立的 serverless 呼叫（開站／
建立劇本後／功能列刷新鈕，每個劇本各打一次 `/refresh`），彼此不共享
行程內記憶體——要讓 N 個劇本共用同一條曲線，只能靠一個跨呼叫的持久
層，因此快取放儲存介面（Neon），不是行程內變數。

成功與失敗都要快取、但窗口長度不同：成功的曲線最多日頻更新，快取
`_SUCCESS_MAX_AGE` 這麼久很安全；失敗只快取 `_FAILURE_MAX_AGE`——
資料源短暫斷線恢復後，不該讓使用者卡在舊的失敗訊息裡到快取真正過期
才有機會重試，同時仍能吸收同一輪刷新裡 N 個劇本的重複請求。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from option_chaser.ratecurve import RateCurve, curve_from_dict, curve_to_dict
from option_chaser.service import RateCurveLoader

from .storage import RateCacheEntry, Storage

_SUCCESS_MAX_AGE = timedelta(hours=12)
_FAILURE_MAX_AGE = timedelta(minutes=5)


def _fresh_enough(entry: RateCacheEntry) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return False   # 讀不懂的時間戳當舊，跟全站既有的新鮮度判斷同一個原則
    age = datetime.now(timezone.utc) - fetched_at
    limit = _SUCCESS_MAX_AGE if entry.curve is not None else _FAILURE_MAX_AGE
    return age < limit


def cached_loader(storage: Storage, underlying: RateCurveLoader) -> RateCurveLoader:
    """回傳一個行為與 `underlying` 相同、但先查快取的 `RateCurveLoader`。"""

    def loader(today: date) -> tuple[RateCurve | None, str]:
        # 快取層本身的問題（例如 Neon 暫時連不上）不該讓利率取得跟著死掉
        # ——退回直接呼叫底層來源。跟 `option_chaser.data.treasury` 既有
        # 「快取讀寫失敗一律視為無快取、不影響本次分析」是同一個哲學。
        try:
            cached = storage.get_rate_cache()
        except Exception:  # noqa: BLE001 — 快取讀取失敗視同沒有快取
            cached = None
        if cached is not None and _fresh_enough(cached):
            return (curve_from_dict(cached.curve) if cached.curve else None, cached.note)

        curve, note = underlying(today)
        try:
            storage.save_rate_cache(RateCacheEntry(
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                curve=curve_to_dict(curve) if curve is not None else None,
                note=note))
        except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
            pass
        return curve, note

    return loader
