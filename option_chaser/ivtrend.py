"""Exact-contract IV(t) 的原始序列處理與統計量（HIVT-02／#153、
HIVT-03／#154，spec #151 §1／§3）。

跟 `ivhistory.py` 物理分開，且刻意不 import 它、也不被它 import——那個
模組是 (tenor, delta) 逐日重錨定家族，只服務既有 Normalized Skew；這裡
是 **exact contract**（同一 underlying／expiration／strike／option_type，
spec #151 §2 絕對紅線）家族，兩者資料語意完全不同（spec #151 §0／§7
隔離紅線：新 feature 絕不吃重錨定家族的資料，也不讓重錨定家族吃這裡的）。

`historical_percentile()`／`delta_4w()` 的演算法定義**沿用**
`ivhistory.percentile()`／`trend_4w()`（spec #151 §3 明文指定），但是
**重新實作、不 import**——維持雙向零耦合的隔離紅線比省那幾行重複更
重要（spec #151 §7 Migration Map C：兩個家族的演算法可以相同，但物理
上不共用同一份程式碼路徑）。
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median, stdev

# spec #151 §4「最多最近 1 year」的具體機制——不是「不設下限」的另一面
# （那句管的是掛牌不滿一年時不補齊，這個常數管的是掛牌超過一年時裁掉
# 多少）。用日曆天，不是觀測筆數：vendor 實際 cadence 在 #152 之前從未
# 確認過，不能假設任何點數對應天數。
IV_TREND_MAX_HISTORY_DAYS = 365

# spec #151 §3：moving average／Bollinger bands 的回溯窗，用日曆天而非
# 觀測筆數——跟既有 Δ4w 窗口（`_TREND_WINDOW_START_DAYS`／
# `_TREND_WINDOW_END_DAYS`）同一種「日曆天框架」慣例，vendor 真實
# cadence 不管是不是逐日，這個常數都維持正確。
IV_TREND_LOOKBACK_DAYS = 30

# 標準差要有足夠點數才有意義——這個門檻以下，moving average／bands／
# z-score 各自誠實回報 unavailable（null），不是硬湊一個不可信的數字。
# percentile／Δ4w 沿用既有無最低門檻慣例，不受這個常數約束。
IV_TREND_MIN_OBSERVATIONS_FOR_BANDS = 5


def trim_to_window(points: list[tuple[str, float | None]], *, today: date,
                   max_days: int = IV_TREND_MAX_HISTORY_DAYS,
                   ) -> list[tuple[str, float | None]]:
    """裁到最近 `max_days` 天——合約掛牌不滿這個天數時原樣回傳（有多少
    回多少，spec §4 明文不補齊、不拿其他合約頂替）。`points` 不要求先
    排序，回傳順序與輸入順序一致（呼叫端已負責排序時不會被打亂）。
    """
    cutoff = (today - timedelta(days=max_days)).isoformat()
    return [(d, iv) for d, iv in points if d >= cutoff]


def history_span_days(points: list[tuple[str, float | None]]) -> int:
    """最早與最新觀測日期之間相差幾天——**不管 iv 是否為 null**，這是
    「vendor 對這張合約給了多長的時間涵蓋範圍」，跟「這段範圍裡有幾筆
    真正可用的 IV」（`observation_count`，由呼叫端另外算）是兩個不同的
    數字。空序列回 0——沒有觀測就沒有跨度可言。
    """
    if not points:
        return 0
    dates = sorted(d for d, _ in points)
    return (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days


# ---------- 統計量（HIVT-03／#154，spec #151 §3）----------

def _rolling_windows(points: list[tuple[str, float | None]], *,
                     window_days: int,
                     ) -> list[tuple[str, list[float]]]:
    """逐一有效觀測（`iv` 非 `None`，依日期排序）算出：以該點為右端，
    往前 `window_days` 個日曆天（含當天）視窗內的全部有效 iv 值。

    `moving_average()`／`bollinger_bands()`／`current_zscore()` 共用
    同一份視窗計算——三者「用同一份 mean／std」（spec #151 §3 z-score
    定義的明文要求）就是靠共用這個輔助函式做到，不是三處各自重算一次
    容易漂移的邏輯。
    """
    valid = sorted((d, iv) for d, iv in points if iv is not None)
    out: list[tuple[str, list[float]]] = []
    for d, _ in valid:
        window_start = (date.fromisoformat(d) - timedelta(days=window_days)).isoformat()
        window_vals = [v for dd, v in valid if window_start <= dd <= d]
        out.append((d, window_vals))
    return out


def moving_average(points: list[tuple[str, float | None]], *,
                   window_days: int = IV_TREND_LOOKBACK_DAYS,
                   ) -> list[tuple[str, float | None]]:
    """逐日 rolling SMA——只對有 `iv` 值的日期輸出一筆（`iv=None` 的日子
    沒有新資料可以把平均線推進到那一天，前端依 `date` key 對齊，不需要
    跟 `points` 逐位元對齊）。單一點視窗內有效觀測筆數低於
    `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS` 時，那一點回 `None`——序列
    起始端天然會有這樣的空窗，這正是「有多少歷史就顯示多少」的圖表版本，
    不是額外要處理的特例。
    """
    return [(d, mean(vals) if len(vals) >= IV_TREND_MIN_OBSERVATIONS_FOR_BANDS
             else None)
            for d, vals in _rolling_windows(points, window_days=window_days)]


def bollinger_bands(points: list[tuple[str, float | None]], *,
                    window_days: int = IV_TREND_LOOKBACK_DAYS,
                    num_std: float = 2.0,
                    ) -> dict[str, list[tuple[str, float | None]]]:
    """Rolling mean ± `num_std` 個標準差，逐點與 `moving_average()` 用
    同一份視窗（`_rolling_windows`）算出——上下界因此永遠以 MA 為中心，
    不會因為兩處分別計算而漂移。視窗觀測數不足時該點回 `None`，跟
    `moving_average()` 同一個門檻、同一種「起始端天然空窗」語意。

    回傳 `{upper, lower, mean, std}` 四條序列（spec #151 §3 明文簽章）
    ——`mean` 等同 `moving_average()` 的輸出、`std` 是算出 upper／lower
    當下的標準差，一併回傳讓呼叫端（例如 `current_zscore` 之外，未來
    若有需要重算 z-score 的呼叫端）不必自己從 upper／lower 反推。
    """
    upper: list[tuple[str, float | None]] = []
    lower: list[tuple[str, float | None]] = []
    means: list[tuple[str, float | None]] = []
    stds: list[tuple[str, float | None]] = []
    for d, vals in _rolling_windows(points, window_days=window_days):
        if len(vals) < IV_TREND_MIN_OBSERVATIONS_FOR_BANDS:
            upper.append((d, None))
            lower.append((d, None))
            means.append((d, None))
            stds.append((d, None))
            continue
        m, s = mean(vals), stdev(vals)
        upper.append((d, m + num_std * s))
        lower.append((d, m - num_std * s))
        means.append((d, m))
        stds.append((d, s))
    return {"upper": upper, "lower": lower, "mean": means, "std": stds}


def current_zscore(points: list[tuple[str, float | None]], *,
                   window_days: int = IV_TREND_LOOKBACK_DAYS,
                   ) -> float | None:
    """今天（序列裡最新一筆有效觀測）的 z-score＝`(current − rolling
    mean) / rolling std`，用**最新那一點**的 rolling window（跟
    `moving_average()`／`bollinger_bands()` 的最後一點同一份 mean／std，
    spec #151 §3 明文要求）。

    最新視窗觀測數不足、或序列本身沒有任何有效觀測時回 `None`。標準差
    為 0（視窗內全部同值，含最新這筆）時，`current − mean` 也必然是
    0——定義為 0.0 而非除以零：沒有離散度可言，不是「離散度是 0 所以
    距離無限大」。
    """
    windows = _rolling_windows(points, window_days=window_days)
    if not windows:
        return None
    d, vals = windows[-1]
    if len(vals) < IV_TREND_MIN_OBSERVATIONS_FOR_BANDS:
        return None
    m, s = mean(vals), stdev(vals)
    if s == 0:
        return 0.0
    return (vals[-1] - m) / s


def historical_percentile(points: list[tuple[str, float | None]],
                          current: float | None) -> float | None:
    """`current` 在整段（已裁窗的）歷史裡的百分位（0–1）。

    沿用 `ivhistory.percentile()` 的「≤ 含等於」定義（spec #151
    §3）——全同值序列回 1.0 而不是 0.0，後者會把「跟過去一樣」說成
    「處於歷史最低」。**無最低觀測門檻**：`current` 或整段歷史為空時
    回 `None`，否則不論母體有幾筆都照算（spec §3／原始需求 AC14——
    掛牌不滿一年的合約也該有百分位，不因為點數少就藏起來）。
    """
    if current is None:
        return None
    series = [iv for _, iv in points if iv is not None]
    if not series:
        return None
    return sum(1 for x in series if x <= current) / len(series)


# Δ4w 回溯窗——跟 `ivhistory.trend_4w()` 完全同一組數字（spec #151 §3
# 明文「重用同一個 [today−42, today−21] 中位數定義」），獨立定義在這裡
# 是刻意的重複，理由見本檔案頂部的隔離說明。
_TREND_WINDOW_START_DAYS = 42
_TREND_WINDOW_END_DAYS = 21


def delta_4w(points: list[tuple[str, float | None]], *,
            latest: float | None, today: date) -> float | None:
    """Δ4w＝`latest` 減去 `[today−42d, today−21d]` 窗內全部有效觀測的
    **中位數**（沿用 `ivhistory.trend_4w()` 的定義，見本模組頂部說明）。

    `latest` 由呼叫端傳入而不是這裡自己推——兩者保證是同一個數字。窗內
    一筆有效觀測都沒有，或根本沒有 `latest` 可減 → `None`：不外推、
    不拿窗外較近的點頂替。
    """
    if latest is None:
        return None
    window_start = (today - timedelta(days=_TREND_WINDOW_START_DAYS)).isoformat()
    window_end = (today - timedelta(days=_TREND_WINDOW_END_DAYS)).isoformat()
    base_values = [v for d, v in points if v is not None
                   and window_start <= d <= window_end]
    if not base_values:
        return None
    return latest - median(base_values)
