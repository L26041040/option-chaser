"""Sequential hard filters with per-stage rejection counts (spec §4).

到期日的取捨**完全**由 `timeframe.select_expiries` 的六點規則負責，在窮舉之前就
已發生；本模組因此不設任何到期日條件——只做合約品質過濾（報價／IV），參數沿用
現行值（附錄 A8.4）。錨點前方、早於目標月的到期日進到這裡時，與其他到期日受
完全相同的品質標準檢驗。

FB5-01／FB5-02／FB5-03（#62／#63／#64，spec #61）：過濾器的每一關都歸入三類
之一，只有前兩類仍是硬門檻——
- A 類「資料健全性」：算不出來就必須排除（報價存在且不交叉）
- B 類「數學前提」：模型算不出有意義的值（IV 落在可解區間）
- C 類「品質標示」：跟能不能算無關，只影響「這筆好不好」（未平倉量、成交量、
  買賣價差寬度、無套利一致性）——**本輪起不再是硬門檻**，全部改為隨候選一併
  呈現的資訊。未平倉量／報價原樣序列化（`OptionContract.open_interest`／
  `.bid`／`.ask`）；買賣價差寬度改用本模組匯出的 `is_spread_wide()`（公式與
  舊硬門檻完全相同，只是從「刷掉」改成供 `service.py` 判定要不要標「品質
  標示」），沿用既有的 `CandidateView.quote_warning` 機制，不新造一套；
  無套利一致性用本模組匯出的 `monotonicity_violations()`（相鄰履約價 ask
  應單調，違反即報價可疑），因其嚴重性與生成方式都與前兩者不同（配對關係
  違反，非單一數值超標），走獨立的 `CandidateView.monotonicity_warning`
  欄位，不與 `quote_warning` 混在同一個布林值裡；成交量條件（`min_volume`
  恆真的半條件）直接移除。

三分類的理由（spec #61）：本 repo 主數字一律採最差成交口徑（買腿 Ask、賣腿
Bid，T12／附錄 A14.2），流動性差的候選成本已經被誠實算高、報酬率已經被誠實
壓低；再用硬門檻刪掉它們是同一件事罰兩次，而且是更糟的罰法——刪掉資訊，
而不是把資訊定價進去。實測未平倉量是 OCC 收盤後才發布的 T+1 落後數字，
硬門檻換來的是把候選池砍到只剩唯一倖存者，而不是篩掉真正有問題的報價。

FB5-04（#65）：分類本身現在是程式碼裡的一個結構，不只是文件——`FILTER_CLASS_LABELS`
是三類的人話對照表；A／B 兩類的分類標籤隨 `apply_filters()` 逐關寫進
`FilterStageResult.filter_class`；C 類則由 `quality_flag_counts()` 把既有的
三個品質判準（零成交量／`is_spread_wide`／`monotonicity_violations`）攤開算
成整個合格池裡的計數（`QualityFlagCount`），供過濾統計區與報告尾註呈現
「排除了幾筆」與「標示了幾筆」的差別——前者是「算不出來」，後者是
「算得出來但不夠好看」。
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable

from .models import (AnalysisParams, FilterReport, FilterStageResult, OptionContract,
                     PairReport, QualityFlagCount, leg_option_type)

# FB5-04（#65，spec #61）：三分類的人話說明，`FilterStageResult.filter_class` 與
# `quality_flag_counts()` 的呼叫端（report.py／store.py）共用同一份措辭，
# 不各自重複硬編碼一次。
FILTER_CLASS_LABELS = {
    "A": "資料健全性",
    "B": "數學前提",
    "C": "品質標示",
}


def is_spread_wide(bid: float, ask: float, p: AnalysisParams) -> bool:
    """FB5-02（#63）：買賣價差是否超過舊硬門檻的公式（現在只用來標示，
    不再刪除候選）。公式逐字沿用舊 `spread_ok`：`spread > max(spread_floor,
    max_spread_pct * mid)`。呼叫端＝`service._v4_fields`，用來決定
    `CandidateView.quote_warning`；`bid`/`ask` 皆需已知（None 屬 A 類報價
    健全性，在 `apply_filters` 那一關就已經被擋下，不會走到這裡）。
    """
    mid = (bid + ask) / 2.0
    return (ask - bid) > max(p.spread_floor, p.max_spread_pct * mid)


def monotonicity_violations(contracts: Iterable[OptionContract]) -> frozenset[str]:
    """FB5-03（#64，spec #61）：無套利一致性檢查——C 類品質標示，只標不刪，
    本函式不被 `apply_filters` 呼叫、不影響誰進得了候選池。

    同一到期日、同一類型，call 的 ask 對履約價必須非遞增、put 必須非遞減
    ——低履約價 call 不可能比高履約價便宜，否則垂直價差有負價值，是無
    風險套利。用 `ask`（不用 mid）：本 repo 的成本口徑本來就以 ask 為準
    （單腿最差成交＝Ask，T12／附錄 A14.2），這裡沿用同一個欄位，不另外
    引入 mid 這個次要欄位當判準。

    只在**相鄰**（依履約價排序後緊鄰，中間若有合約因 A/B 類硬門檻被擋下
    就跳過、比對下一個可得的）配對上檢查；違反時**兩邊都標記**——這是
    配對關係的違反，光看單一報價無法判斷是哪一邊陳舊，寧可雙邊都標。
    實測（`docs/research/option-liquidity-filtering.md` §6.3）307 組相鄰
    配對僅 3 組違反，且全部落在久未成交的冷門履約價，訊噪比極佳。

    刻意**不做凸性檢查**：同份研究實測 50/305 組「違反」，訊噪比太差；
    且期權市場本質非凸，把非凸判成錯誤會系統性誤殺真實市場結構（spec
    #61 已裁示，需求方原話「交易市場，特別是期權市場，本質上是非凸的」）。
    """
    by_group: dict[tuple[str, str], list[OptionContract]] = {}
    for c in contracts:
        by_group.setdefault((c.expiry, c.option_type), []).append(c)
    flagged: set[str] = set()
    for (_, option_type), group in by_group.items():
        ordered = sorted(group, key=lambda c: c.strike)
        for a, b in zip(ordered, ordered[1:]):
            violates = a.ask < b.ask if option_type == "call" else a.ask > b.ask
            if violates:
                flagged.add(a.contract_symbol)
                flagged.add(b.contract_symbol)
    return frozenset(flagged)


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
        ("A", "報價異常", quote_ok),
        ("B", "IV 異常", iv_ok),
    )
    results: list[FilterStageResult] = []
    for filter_class, label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        results.append(FilterStageResult(label=label, removed=len(remaining) - len(kept),
                                         filter_class=filter_class))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))


def quality_flag_counts(
    qualified: Iterable[OptionContract], violations: frozenset[str], p: AnalysisParams
) -> tuple[QualityFlagCount, ...]:
    """FB5-04（#65，spec #61）：C 類品質標示在**整個合格池**（`apply_filters`
    的輸出，價差策略是配對前的腿級池，與 `FilterReport.passed` 同一個口徑）
    上各自出現幾次。三項對應 `service._v4_fields()` 已經在算的三個判準
    （`zero_vol`／`is_spread_wide`／`monotonicity_violations`）——這裡只是
    把同一組既有判準攤開來算「整池有幾筆」，不是新規則、也不新增門檻。

    未平倉量（OI）刻意不在這裡：FB5-01 只把它從硬門檻移除、原樣顯示，
    沒有定義「多低算有疑慮」的新門檻，這裡跟著不發明一個——呼叫端
    （`report.py` 尾註）也不得聲稱這裡有算它，見尾註措辭的既有裁示。
    """
    quals = list(qualified)
    return (
        # MVP V3（#104，spec #102 決策 F）：零成交量在 LEAPS／冷門履約價
        # 是常態，不是報價可疑的推論依據——字面只講事實（今日沒有成交），
        # 不再由零成交量推論出報價品質的問題。舊有的推論式措辭已依裁示
        # 禁用（`tests/test_redlines.py` 封鎖，見該檔 BANNED 清單）。
        QualityFlagCount("今日無成交量",
                        sum(1 for c in quals if c.volume == 0)),
        QualityFlagCount("買賣價差偏大",
                        sum(1 for c in quals if is_spread_wide(c.bid, c.ask, p))),
        QualityFlagCount("報價與鄰近履約價不一致，疑似陳舊報價",
                        sum(1 for c in quals if c.contract_symbol in violations)),
    )


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
