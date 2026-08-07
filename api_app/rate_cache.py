"""利率曲線的持久快取層（#67）。

包在任何 `RateCurveLoader`（`option_chaser.service.RateCurveLoader`）
外面——資料源本身（誰提供曲線、怎麼抓）完全不在這層的管轄範圍，未來
新增備援 provider 只需要把 `underlying` 換成一個會依序試多個來源的
合成函式，這層一行都不用改。現有的 `service.default_rate_curve_loader`
（Treasury）是 #73／#74 選型與 production 實測後的落地結果（見
`docs/research/interest-rate-source-selection.md` §6.4），不是暫時
填充物；FRED／FMP 兩個候選備援皆已確認網路可達、只是還沒申請到
金鑰，之後補上不需要動這層快取邏輯。

一輪刷新可能對 N 個劇本各自觸發一次獨立的 serverless 呼叫（開站／
建立劇本後／功能列刷新鈕，每個劇本各打一次 `/refresh`），彼此不共享
行程內記憶體——要讓 N 個劇本共用同一條曲線，只能靠一個跨呼叫的持久
層，因此快取放儲存介面（Neon），不是行程內變數。

成功一輪只需要一次：利率一天內不會劇烈變動，同一市場日內只要成功
抓過一次，所有劇本、所有 refresh 都共用那一份，直到下一個市場日第一
次有人需要時才重新 fetch（`market_day` 欄位判準，見
`RateCacheEntry` 的說明）。失敗走不同的窗口
（`_FAILURE_MAX_AGE`）——資料源短暫斷線恢復後，不該讓使用者卡在
舊的失敗訊息裡到隔天才有機會重試，同時仍能吸收同一輪刷新裡 N 個
劇本的重複請求。

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

import dataclasses
from datetime import date, datetime, timedelta, timezone

from option_chaser.ratecurve import RateCurve, curve_from_dict, curve_to_dict
from option_chaser.service import RateCurveLoader

from .storage import RateCacheEntry, Storage

_FAILURE_MAX_AGE = timedelta(minutes=5)
# 與 `treasury.py` 既有 `CACHE_MAX_AGE_DAYS = 7` 用同一個數字：抓取
# 失敗時，手上這份舊曲線還能撐多久當緊急備援，是跟「多快該重新抓」
# 不同的問題。
_STALE_FALLBACK_MAX_AGE = timedelta(days=7)


def _age(entry: RateCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None   # 讀不懂的時間戳當舊，跟全站既有的新鮮度判斷同一個原則
    return datetime.now(timezone.utc) - fetched_at


def _success_is_fresh(entry: RateCacheEntry, today: date) -> bool:
    """同一市場日成功抓過一次就共用，不看時間差——利率一天內不會
    劇烈變動，沒理由每次刷新都重打來源。比對 `market_day`（呼叫端
    傳入的 `today`）而不是 `fetched_at` 的日期部分：後者是 UTC
    wall-clock，跟「今天是哪個市場日」在午夜前後對不起來。"""
    return entry.curve is not None and entry.market_day == today.isoformat()


def _recent_attempt(entry: RateCacheEntry, today: date) -> bool:
    """短窗內最近試過一次（不論是純失敗、還是失敗後沿用了緊急備援窗
    裡的舊曲線）——同一輪刷新的 N 個劇本不用把同一個失敗中的來源打
    好幾次。刻意不檢查 `entry.curve is None`：沿用舊曲線那個分支
    `curve` 不是 `None`，但 `market_day` 沒推進到今天，一樣代表
    「今天這次嘗試沒有成功」，短窗內同樣該直接沿用這筆紀錄，不是
    每次都重新問一次底層來源。

    同時要求 `attempted_day == today`：只看 `fetched_at` 的時間差
    在市場日剛跨過午夜的那幾分鐘會出錯——上一個市場日收尾前才失敗
    過一次，時間差確實很短，但那是**昨天**的嘗試，今天的第一次
    請求仍然應該真的問一次底層來源，不能被那筆快要過期的舊紀錄
    擋下來。"""
    if entry.attempted_day != today.isoformat():
        return False
    age = _age(entry)
    return age is not None and age < _FAILURE_MAX_AGE


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
        if cached is not None and _success_is_fresh(cached, today):
            return curve_from_dict(cached.curve), cached.note
        if cached is not None and _recent_attempt(cached, today):
            return (curve_from_dict(cached.curve) if cached.curve is not None
                    else None), cached.note

        try:
            # 底層 provider 本身的錯誤（未來 #74 換源時可能沒有規規矩矩
            # 回傳 (None, note) 而是直接拋例外）不該讓分析整個 500——
            # 收斂成跟 provider 自己回報失敗同一種形狀。
            curve, note = underlying(today)
        except Exception as e:  # noqa: BLE001 — 收斂成失敗結果，不讓例外往上炸
            curve, note = None, f"利率來源丟出例外：{e}"

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 只在這次真的成功「直接抓到」時前進；沿用下面緊急備援窗舊曲線
        # 那個分支不算——那仍是「這次嘗試失敗」，`market_day` 若跟著設成
        # 今天，會讓同一天稍後的呼叫誤判「今天已經成功過」而不再重試，
        # 即使資料源當時只是短暫斷線。`curve.stale`（RC1／#87）同一個
        # 判準也適用在 `underlying` 自己內部的陳舊備援分支（例如
        # `treasury.load_rate_curve()` 的本地檔案快取）——那份曲線雖然
        # 不是 `None`，但一樣不是「今天直接抓到」，不能讓 `market_day`
        # 誤判成功推進，否則同一天稍後的呼叫會被這筆假新鮮擋下來，
        # 不再嘗試真正抓一次新鮮曲線。
        fetched_fresh = curve is not None and not curve.stale
        last_success_at = now if fetched_fresh else (
            cached.last_success_at if cached is not None else None)
        market_day = today.isoformat() if fetched_fresh else (
            cached.market_day if cached is not None else None)

        if curve is None and cached is not None and cached.curve is not None:
            age = _age(cached)
            if age is not None and age < _STALE_FALLBACK_MAX_AGE:
                # RC1（#87）：今天的嘗試失敗、沿用 Neon 裡還沒過緊急備援
                # 窗的舊曲線——不論那筆快取本身當初是不是新鮮抓到的，
                # 這次沿用的行為本身就是「陳舊」，明確標成 stale=True。
                curve = dataclasses.replace(curve_from_dict(cached.curve),
                                            stale=True)
                note = f"{cached.note}（沿用快取，最新一次嘗試失敗：{note}）"

        try:
            # `fetched_at` 這裡蓋成現在——即使是沿用舊曲線那個分支，也要
            # 重設失敗窗的時鐘，否則下一個劇本進來時同樣判定「該重抓
            # 了」，一輪刷新的 N 個劇本會把同一個失敗中的來源打好幾次。
            # `attempted_day` 不論成敗都蓋成今天——`_recent_attempt` 靠它
            # 判斷「這筆短窗紀錄是不是今天留下的」，跟只成功時才前進的
            # `market_day` 是不同的東西。
            storage.save_rate_cache(RateCacheEntry(
                fetched_at=now,
                curve=curve_to_dict(curve) if curve is not None else None,
                note=note, last_success_at=last_success_at,
                market_day=market_day, attempted_day=today.isoformat()))
        except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
            pass
        return curve, note

    return loader
