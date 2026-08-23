"""Treasury 利率曲線列的持久快取層——鍵是年份（PERF-03／#179）。

包在任何 `RateCurveRowsFetch`（`api_app.main.RateCurveRowsFetch`，
`Callable[[date, date], CurveRows]`）外面，跟 `rate_cache.py`／
`dividend_cache.py` 同一套「包裝任意來源、快取放儲存介面」設計。

**風險說明**（本輪風險最高的一項，正確性必須靠鍵設計本身鎖死，不能
只靠呼叫端小心）：快取鍵永遠是「這筆快取存的是哪一年」，不是「今天」
或「抓到的時間」——一個對歷史日期 D 的查詢，結構上只可能被 D 所在
年份的快取區塊滿足，不存在「不小心套用到今天曲線回答歷史查詢」的
路徑。

過去年份（`year < today.year`）一旦成功快取即永久有效，不設
TTL——Treasury 不會回頭修正三年前已公布的曲線，這是不可變的歷史事實，
一旦有資料就直接沿用，連陳舊備援窗都不需要判斷（`_success_is_fresh`
對過去年份只看 `rows is not None`）。當年（`year == today.year`）比照
既有 `rate_cache.py` 的市場日語意：同一市場日成功抓過一次就共用、
隔天第一次請求才重新嘗試、失敗有 5 分鐘去重窗、且有 7 天陳舊備援窗
（Treasury 短暫斷線時沿用當年稍早抓到的曲線列，好過直接讓那一批
觀測全記成 no_rate）。

`RateCurveRowsFetch` 本身的簽章（`Callable[[date, date], CurveRows]`）
沒有「今天」這個參數——這裡包出來的版本因此多吃一個 `today`（呼叫端
的市場日）位置參數，只有當年那一格需要它判斷「今天是否已經成功抓過」，
過去年份的判斷完全不看它。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

from option_chaser.ratecurve import CurveRows

from .storage import Storage, TreasuryYearCacheEntry

_FAILURE_MAX_AGE = timedelta(minutes=5)
# 只對當年生效——過去年份一旦成功即永久有效，不會走到需要「陳舊備援」
# 的分支（見 `_fetch_one_year`：過去年份成功後在 `_success_is_fresh`
# 就直接短路回傳，不會再往下執行到這裡）。跟 `rate_cache.py` 同一個
# 7 天數字、同一個理由：抓取失敗時，手上這份還能撐多久當緊急備援。
_STALE_FALLBACK_MAX_AGE = timedelta(days=7)


def _rows_to_json(rows: CurveRows) -> list:
    return [[d, [[t, r] for t, r in nodes]] for d, nodes in rows]


def _rows_from_json(data: list) -> CurveRows:
    return tuple((d, tuple((t, r) for t, r in nodes)) for d, nodes in data)


def _age(entry: TreasuryYearCacheEntry) -> timedelta | None:
    try:
        fetched_at = datetime.fromisoformat(entry.fetched_at)
    except ValueError:
        return None   # 讀不懂的時間戳當舊，跟 rate_cache.py 同一個原則
    return datetime.now(timezone.utc) - fetched_at


def _success_is_fresh(entry: TreasuryYearCacheEntry, year: int, today: date) -> bool:
    """過去年份一旦成功即永久新鮮——PIT 安全的核心：不看 `fetched_at`
    多舊，只看那年是否曾經成功抓到過。當年比照 `rate_cache.py`：同一
    市場日成功抓過一次就共用，不看時間差。"""
    if entry.rows is None:
        return False
    if year < today.year:
        return True
    return entry.market_day == today.isoformat()


def _recent_attempt(entry: TreasuryYearCacheEntry, today: date) -> bool:
    """短窗內最近試過一次（不論純失敗、還是失敗後沿用了緊急備援窗裡的
    舊資料）——同一輪歷史 reconstruction 對同一年份的重複查詢不用把
    同一個失敗中的來源打好幾次。語意與 `rate_cache._recent_attempt`
    完全一致，見該處說明。"""
    if entry.attempted_day != today.isoformat():
        return False
    age = _age(entry)
    return age is not None and age < _FAILURE_MAX_AGE


def _fetch_one_year(storage: Storage, year: int,
                    underlying: Callable[[date, date], CurveRows],
                    today: date) -> CurveRows:
    """單一年份的快取讀寫——結構逐一鏡射 `rate_cache.cached_loader()`
    的內層邏輯，鍵從「固定一筆」換成「這個 `year`」。"""
    try:
        cached = storage.get_treasury_year_cache(year)
    except Exception:  # noqa: BLE001 — 快取讀取失敗視同沒有快取
        cached = None
    if cached is not None and _success_is_fresh(cached, year, today):
        return _rows_from_json(cached.rows)
    if cached is not None and _recent_attempt(cached, today):
        return _rows_from_json(cached.rows) if cached.rows is not None else ()

    try:
        # 一律傳整年的日期範圍——Treasury 只提供整年一份檔案
        # （`fetch_curve_rows_for_year`），`fetch_curve_range` 也只看
        # `.year` 決定抓哪幾年，傳入區間裡的月日對它沒有意義；快取要能
        # 跨越不同觀測範圍重用同一年份的資料，本來就必須以整年為單位。
        rows: CurveRows | None = underlying(date(year, 1, 1), date(year, 12, 31))
        if not rows:
            rows = None
        note = (f"Treasury {year} 年曲線（{len(rows)} 個交易日）" if rows
               else f"Treasury {year} 年抓取結果為空")
    except Exception as e:  # noqa: BLE001 — 收斂成失敗結果，不讓例外往上炸
        rows, note = None, f"Treasury 曲線來源丟出例外：{e}"

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fetched_fresh = rows is not None
    last_success_at = now if fetched_fresh else (
        cached.last_success_at if cached is not None else None)
    market_day = today.isoformat() if fetched_fresh else (
        cached.market_day if cached is not None else None)

    if rows is None and cached is not None and cached.rows is not None:
        age = _age(cached)
        if age is not None and age < _STALE_FALLBACK_MAX_AGE:
            rows = _rows_from_json(cached.rows)
            note = f"{cached.note}（沿用快取，最新一次嘗試失敗：{note}）"

    try:
        storage.save_treasury_year_cache(TreasuryYearCacheEntry(
            year=year, fetched_at=now,
            rows=_rows_to_json(rows) if rows is not None else None,
            note=note, last_success_at=last_success_at,
            market_day=market_day, attempted_day=today.isoformat()))
    except Exception:  # noqa: BLE001 — 快取寫不進去不影響這次分析結果，下次再試
        pass

    return rows if rows is not None else ()


def cached_rate_curve_rows(storage: Storage,
                           underlying: Callable[[date, date], CurveRows],
                           ) -> Callable[[date, date, date], CurveRows]:
    """回傳一個依年份快取的版本，多吃一個 `today` 位置參數（見模組
    docstring 說明）。逐年查快取、串接——單一年份抓取失敗不讓整段範圍
    報廢，跟 `treasury.fetch_curve_range` 原本的容錯行為一致。"""
    def fetch(from_date: date, to_date: date, today: date) -> CurveRows:
        rows: list = []
        for year in range(from_date.year, to_date.year + 1):
            rows.extend(_fetch_one_year(storage, year, underlying, today))
        return tuple(rows)
    return fetch
