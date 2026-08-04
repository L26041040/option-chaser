"""Sequential hard filters with per-stage rejection counts (spec §4).

到期日的取捨**完全**由 `timeframe.select_expiries` 的六點規則負責，在窮舉之前就
已發生；本模組因此不設任何到期日條件——只做合約品質過濾（報價／IV），參數沿用
現行值（附錄 A8.4）。錨點前方、早於目標月的到期日進到這裡時，與其他到期日受
完全相同的品質標準檢驗。

FB5-01／FB5-02（#62／#63，spec #61）：過濾器的每一關都歸入三類之一，只有前兩類
仍是硬門檻——
- A 類「資料健全性」：算不出來就必須排除（報價存在且不交叉）
- B 類「數學前提」：模型算不出有意義的值（IV 落在可解區間）
- C 類「品質標示」：跟能不能算無關，只影響「這筆好不好」（未平倉量、成交量、
  買賣價差寬度）——**本輪起不再是硬門檻**，全部改為隨候選一併呈現的資訊。
  未平倉量／報價原樣序列化（`OptionContract.open_interest`／`.bid`／`.ask`）；
  買賣價差寬度改用本模組匯出的 `is_spread_wide()`（公式與舊硬門檻完全相同，
  只是從「刷掉」改成供 `service.py` 判定要不要標「品質標示」），沿用既有的
  `CandidateView.quote_warning` 機制，不新造一套；成交量條件（`min_volume`
  恆真的半條件）直接移除。

三分類的理由（spec #61）：本 repo 主數字一律採最差成交口徑（買腿 Ask、賣腿
Bid，T12／附錄 A14.2），流動性差的候選成本已經被誠實算高、報酬率已經被誠實
壓低；再用硬門檻刪掉它們是同一件事罰兩次，而且是更糟的罰法——刪掉資訊，
而不是把資訊定價進去。實測未平倉量是 OCC 收盤後才發布的 T+1 落後數字，
硬門檻換來的是把候選池砍到只剩唯一倖存者，而不是篩掉真正有問題的報價。
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable

from .models import AnalysisParams, FilterReport, FilterStageResult, OptionContract, PairReport, leg_option_type


def is_spread_wide(bid: float, ask: float, p: AnalysisParams) -> bool:
    """FB5-02（#63）：買賣價差是否超過舊硬門檻的公式（現在只用來標示，
    不再刪除候選）。公式逐字沿用舊 `spread_ok`：`spread > max(spread_floor,
    max_spread_pct * mid)`。呼叫端＝`service._v4_fields`，用來決定
    `CandidateView.quote_warning`；`bid`/`ask` 皆需已知（None 屬 A 類報價
    健全性，在 `apply_filters` 那一關就已經被擋下，不會走到這裡）。
    """
    mid = (bid + ask) / 2.0
    return (ask - bid) > max(p.spread_floor, p.max_spread_pct * mid)


def apply_filters(
    contracts: Iterable[OptionContract], p: AnalysisParams
) -> tuple[list[OptionContract], FilterReport]:
    side = leg_option_type(p.strategy)
    remaining = [c for c in contracts if c.option_type == side]
    total = len(remaining)

    def quote_ok(c: OptionContract) -> bool:
        return c.bid is not None and c.ask is not None and c.bid > 0 and c.ask >= c.bid

    def iv_ok(c: OptionContract) -> bool:
        return c.implied_volatility is not None and 0.01 <= c.implied_volatility <= 5.0

    stages = (
        ("報價異常", quote_ok),
        ("IV 異常", iv_ok),
    )
    results: list[FilterStageResult] = []
    for label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        results.append(FilterStageResult(label=label, removed=len(remaining) - len(kept)))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))


def generate_spread_pairs(
    legs: list[OptionContract], p: AnalysisParams
) -> tuple[list[tuple[OptionContract, OptionContract]], PairReport]:
    """Spec §4.2: same-expiry exhaustive pairing over qualified legs + sanity."""
    by_expiry: dict[str, list[OptionContract]] = {}
    for c in legs:
        by_expiry.setdefault(c.expiry, []).append(c)
    long_is_lower = p.strategy == "bull-call-spread"
    total = 0
    removed = 0
    out: list[tuple[OptionContract, OptionContract]] = []
    for expiry in sorted(by_expiry):
        group = sorted(by_expiry[expiry], key=lambda c: (c.strike, c.contract_symbol))
        for a, b in combinations(group, 2):  # a.strike <= b.strike
            if a.strike == b.strike:
                continue
            total += 1
            lng, sht = (a, b) if long_is_lower else (b, a)
            width = abs(sht.strike - lng.strike)
            net_mid = (lng.bid + lng.ask) / 2.0 - (sht.bid + sht.ask) / 2.0
            net_worst = lng.ask - sht.bid
            if net_mid <= 0 or net_worst >= width:
                removed += 1
                continue
            out.append((lng, sht))
    return out, PairReport(total_pairs=total, removed_sanity=removed, passed=len(out))
