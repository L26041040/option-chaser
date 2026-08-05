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

抓取失敗、但快取裡還有一份**還沒超過緊急備援窗**（`_STALE_FALLBACK_
MAX_AGE`）的舊曲線時，優先沿用舊曲線、只在說明文字裡誠實標出「這是
沿用的、最新一次嘗試失敗了」——不是平白蓋掉改退引擎的固定 4%。這跟
`option_chaser.data.treasury.load_rate_curve` 既有「抓取失敗→用快取
內還沒過期的舊曲線，標示快取日期」是同一個做法，只是快取放的位置從
本地檔案換成 Neon；`_STALE_FALLBACK_MAX_AGE` 沿用它既有的 7 日曆日
窗口。一份幾小時前的曲線仍然比固定 4% 更貼近市場真實利率，不該因為
「這輪照排程該重新整理了」就白白丟掉。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from option_chaser.ratecurve import RateCurve, curve_from_dict, curve_to_dict
from option_chaser.service import RateCurveLoader

from .storage import RateCacheEntry, Storage

_SUCCESS_MAX_AGE = timedelta(hours=12)
_FAILURE_MAX_AGE = timedelta(minutes=5)
# 與 `treasury.py` 既有 `CACHE_MAX_AGE_DAYS = 7` 用同一個數字：抓取
# 失敗時，手上這份舊曲線還能撐多久當緊急備援，是跟「多快該重新抓」
# （`_SUCCESS_MAX_AGE`）不同的問題。
_STALE_FALLBACK_MAX_AGE = timedelta(days=7)


def _age(entry: RateCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None   # 讀不懂的時間戳當舊，跟全站既有的新鮮度判斷同一個原則
    return datetime.now(timezone.utc) - fetched_at


def _fresh_enough(entry: RateCacheEntry) -> bool:
    age = _age(entry)
    if age is None:
        return False
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

        try:
            # 底層 provider 本身的錯誤（未來 #74 換源時可能沒有規規矩矩
            # 回傳 (None, note) 而是直接拋例外）不該讓分析整個 500——
            # 收斂成跟 provider 自己回報失敗同一種形狀。
            curve, note = underlying(today)
        except Exception as e:  # noqa: BLE001 — 收斂成失敗結果，不讓例外往上炸
            curve, note = None, f"利率來源丟出例外：{e}"

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 只在這次真的成功時前進；失敗（包含底下沿用舊曲線那個分支——
        # 那仍是「這次嘗試失敗」）一律沿用上一筆已知的成功時間，不然
        # `/api/health` 會答不出「最後一次成功是什麼時候」。
        last_success_at = now if curve is not None else (
            cached.last_success_at if cached is not None else None)

        if curve is None and cached is not None and cached.curve is not None:
            age = _age(cached)
            if age is not None and age < _STALE_FALLBACK_MAX_AGE:
                curve = curve_from_dict(cached.curve)
                note = f"{cached.note}（沿用快取，最新一次嘗試失敗：{note}）"

        try:
            # `fetched_at` 這裡蓋成現在——即使是沿用舊曲線那個分支，也要
            # 重設新鮮度時鐘，否則下一個劇本進來時同樣判定「該重抓了」，
            # 一輪刷新的 N 個劇本會把同一個失敗中的來源打好幾次。
            storage.save_rate_cache(RateCacheEntry(
                fetched_at=now,
                curve=curve_to_dict(curve) if curve is not None else None,
                note=note, last_success_at=last_success_at))
        except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
            pass
        return curve, note

    return loader
