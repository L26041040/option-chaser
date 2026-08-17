"""Exact-contract IV(t) 的原始序列處理（HIVT-02／#153，spec #151 §1／§3）。

跟 `ivhistory.py` 物理分開，且刻意不 import 它、也不被它 import——那個
模組是 (tenor, delta) 逐日重錨定家族，只服務既有 Normalized Skew；這裡
是 **exact contract**（同一 underlying／expiration／strike／option_type，
spec #151 §2 絕對紅線）家族，兩者資料語意完全不同（spec #151 §0／§7
隔離紅線：新 feature 絕不吃重錨定家族的資料，也不讓重錨定家族吃這裡的）。

本檔案目前只有 HIVT-02（#153）需要的視窗裁切與跨度計算；統計量
（moving average／Bollinger／z-score／percentile／Δ4w，HIVT-03／#154）
物理位置在同一模組，屆時直接加函式，不另開檔案。
"""
from __future__ import annotations

from datetime import date, timedelta

# spec #151 §4「最多最近 1 year」的具體機制——不是「不設下限」的另一面
# （那句管的是掛牌不滿一年時不補齊，這個常數管的是掛牌超過一年時裁掉
# 多少）。用日曆天，不是觀測筆數：vendor 實際 cadence 在 #152 之前從未
# 確認過，不能假設任何點數對應天數。
IV_TREND_MAX_HISTORY_DAYS = 365


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
