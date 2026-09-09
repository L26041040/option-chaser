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

import math
from itertools import combinations
from typing import Callable, Iterable

from .models import (AnalysisParams, FilterReport, FilterStageResult, OptionContract,
                     PairReport, QualityFlagCount, leg_option_type)

# T05（#226，Initial V2 spec #217，`/code-review` Spec 軸回饋）：每一關剔除
# 掉的候選只記「前幾筆」的身份當範例，不是整份清單——診斷要的是「指認得出
# 是哪一組」，不是把整個被剔除的池子搬進報告裡（合約壞得夠多時清單本身
# 就會失去可讀性）。
_MAX_REMOVED_EXAMPLES = 5

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


def quote_ok(c: OptionContract) -> bool:
    """A 層「報價健全性」（T05／#226，Initial V2 spec #217）——缺失值／
    非有限數值（`NaN`／`Infinity`）與買賣價倒掛（`bid>ask`）同屬「報價
    本身不可信」。既有 `c.bid > 0`／`c.ask >= c.bid` 兩條件本身已隱含
    攔住多數這類壞值（`NaN` 比較恆為 False、`Infinity` 的 ask 若 bid
    有限會通過），這裡把「非有限數值」的判準寫成明確的檢查，不依賴
    比較運算子的副作用當作判準。

    SCALE-09（#261）：從 `apply_filters()` 內的私有 closure 抽成
    module-level 公開函式——candidate-specific historical resolver
    需要對「單一候選的單一腿」重跑這一項判準，不能透過重跑整個
    `apply_filters()`（那要求傳入整條鏈、會退化成重跑候選全池，違反
    AC-5）。兩個呼叫端共用同一份邏輯，不是各自維護一份可能漂移的
    判準（AC-6 的精神延伸到這裡）。"""
    return (c.bid is not None and c.ask is not None
            and math.isfinite(c.bid) and math.isfinite(c.ask)
            and c.bid > 0 and c.ask >= c.bid)


def iv_ok(c: OptionContract) -> bool:
    """B 層「IV 落在可解區間」（T05／#226）。同上，SCALE-09（#261）
    抽成公開函式供 resolver 重用，`apply_filters()` 與 resolver 共用
    同一份判準。"""
    return (c.implied_volatility is not None
            and math.isfinite(c.implied_volatility)
            and 0.01 <= c.implied_volatility <= 5.0)


def spread_structural_ok(long_leg: OptionContract, short_leg: OptionContract) -> bool:
    """Vertical Spread 配對層級的結構合法性（`generate_spread_pairs()`
    既有判準逐字抽出）：平均成本（`net_mid`）必須是真正的 debit，且
    最差成交成本（`net_worst`）不得達到或超過價差寬度——否則這組履約價
    湊不出一個有意義的 vertical spread（SCALE-09／#261，供 resolver
    重用，不重複維護一份）。"""
    width = abs(short_leg.strike - long_leg.strike)
    net_mid = (long_leg.bid + long_leg.ask) / 2.0 - (short_leg.bid + short_leg.ask) / 2.0
    net_worst = long_leg.ask - short_leg.bid
    return not (net_mid <= 0 or net_worst >= width)


def butterfly_structural_ok(
    low_leg: OptionContract, mid_leg: OptionContract, high_leg: OptionContract,
) -> bool:
    """Butterfly 三腿組合層級的結構合法性（`generate_butterfly_
    triples()` 既有判準逐字抽出）：平均成本必須是真正的 debit
    （SCALE-09／#261，供 resolver 重用）。"""
    net_mid = ((low_leg.bid + low_leg.ask) / 2.0
              - 2.0 * (mid_leg.bid + mid_leg.ask) / 2.0
              + (high_leg.bid + high_leg.ask) / 2.0)
    return net_mid > 0


def apply_filters(
    contracts: Iterable[OptionContract], p: AnalysisParams
) -> tuple[list[OptionContract], FilterReport]:
    side = leg_option_type(p.strategy)
    remaining = [c for c in contracts if c.option_type == side]
    total = len(remaining)

    stages = (
        ("A", "報價異常", quote_ok),
        ("B", "IV 異常", iv_ok),
    )
    results: list[FilterStageResult] = []
    for filter_class, label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        dropped = [c for c in remaining if not pred(c)]
        examples = tuple(c.contract_symbol for c in dropped[:_MAX_REMOVED_EXAMPLES])
        results.append(FilterStageResult(label=label, removed=len(dropped),
                                         filter_class=filter_class,
                                         removed_examples=examples))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))


def validate_derived_values(
    candidates: list, cost_fn, return_fn, identity_fn=None, max_loss_fn=None,
) -> tuple[list, FilterStageResult]:
    """T05（#226，Initial V2 spec #217）：B 層——導出層數學安全網。

    接在既有計算路徑之後（`evaluate_contract()`／`evaluate_spread()`
    算完之後）、排名之前，是**獨立的最後一道網**：即使 A 層（本模組
    `apply_filters()`／`generate_spread_pairs()` 的既有報價層檢查）
    全數通過，這裡仍會執行——不是 A 層的推論，是另一組獨立成立的證據。

    只檢查**既有計算路徑本來就會產出**的量：
    - `cost_fn(v)`（`scenarios.natural_cost`，Initial V2 全為 debit
      結構，理應恆為正值）出現 `<=0`／`NaN`／`Infinity`
    - `return_fn(v)`（`ranking.baseline_return`／`spread_baseline_
      return`，任何回報給使用者的導出量）出現 `NaN`／`Infinity`
    - `max_loss_fn(v)`（選填，T15／#230 新增：`ButterflyValuation.
      max_loss`）出現 `<=0`／`NaN`／`Infinity`——defined-risk 的候選
      結構上必須真的有風險可言，`max_loss<=0` 代表這組報價組合出來的
      是「怎麼樣都不會虧」的不可能局面（#213 Addendum，Owner 明文）。
      既有兩個呼叫端（單腳／Spread）不傳這個參數，`max_loss` 對它們
      本來就等於 `cost_fn` 的結果（既有不變量，見
      `valuation.SpreadValuation`／`ContractValuation` 各自的
      docstring），不需要重複檢查。

    **不引入任何新的估值／推導邏輯**——`cost_fn`／`return_fn`／
    `max_loss_fn` 都是呼叫端既有的純函式，這裡只是把它們的輸出拿來做
    有限性／正負號檢查，不新增 max_profit 之類的新概念，也不是跨
    strategy 的 generic payoff-envelope／extrema engine（#223 已判定
    Initial V2 不需要，正式收斂為 not planned）。

    劇本成立時報酬為負、但報價自洽的候選**不受影響**——`return_fn` 回
    一個有限的負數（例如 `-0.5`）完全合法，只有 `NaN`／`Infinity` 才
    invalid；這是既有 ranking 自然沉底的正常結果，不是本函式要攔的
    對象（票上明文紅線：不新增 `max_profit<=0` 過濾規則）。

    `identity_fn`（選填，`/code-review` Spec 軸回饋新增）：從被剔除的
    候選萃取一個可指認的身份字串（單腳給合約代碼、Spread 給買賣兩腿
    合約代碼的組合），供診斷指認「是哪一組」。省略時（呼叫端尚未提供）
    回傳的 `FilterStageResult.removed_examples` 就是空 tuple——不強迫
    既有呼叫端立刻補上。
    """
    def _finite(x) -> bool:
        # `/code-review` Standards 軸抓到：本函式的 `cost_fn`／`return_fn`
        # 是泛型參數，今天的兩個呼叫端（`natural_cost`／`baseline_return`／
        # `spread_baseline_return`）保證回傳 `float`，但簽章本身不強制。
        # `math.isfinite(None)` 會拋 `TypeError`，跟 `apply_filters()`
        # 既有 `quote_ok()` 的防禦風格一致，這裡也先擋 `None`。
        return x is not None and math.isfinite(x)

    kept = []
    removed = 0
    examples: list[str] = []
    for v in candidates:
        cost = cost_fn(v)
        ret = return_fn(v)
        max_loss_ok = max_loss_fn is None or (
            _finite(max_loss_fn(v)) and max_loss_fn(v) > 0)
        if _finite(cost) and cost > 0 and _finite(ret) and max_loss_ok:
            kept.append(v)
        else:
            removed += 1
            if identity_fn is not None and len(examples) < _MAX_REMOVED_EXAMPLES:
                examples.append(identity_fn(v))
    stage = FilterStageResult(label="成本或報酬為不可能值（B 層安全網）",
                              removed=removed, filter_class="B",
                              removed_examples=tuple(examples))
    return kept, stage


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
            if not spread_structural_ok(lng, sht):
                removed += 1
                continue
            out.append((lng, sht))
    return out, PairReport(total_pairs=total, removed_sanity=removed, passed=len(out))


# 枚舉迴圈每隔幾個組合徵詢一次 `should_stop`。徵詢本身有成本（呼叫端
# 那頭通常是一次 `time.monotonic()`），逐一徵詢在 `C(n,3)` 規模下量得
# 出來；4096 個組合在正常 production-scale 規模下遠低於一毫秒——夠密到
# 異常龐大的鏈能在瞬間停下，夠疏到正常情況量不出差別。
_ABORT_CHECK_EVERY = 4096


def generate_butterfly_triples(
    legs: list[OptionContract], p: AnalysisParams,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[tuple[OptionContract, OptionContract, OptionContract]], PairReport]:
    """T15（#230，Initial V2 spec #217）：同一到期日、同一權別的合格合約
    窮舉三個履約價組合（低／中／高，中腿口數 2）——比照 `generate_spread_
    pairs()` 同一種寫法，`itertools.combinations` 依履約價排序後直接給
    出 `k1<k2<k3`，不另外判斷方向（Butterfly 不像 Vertical 有
    `long_is_lower` 這種依 subtype 決定買賣腿順序的概念——call-fly／
    put-fly 皆是「買低賣中買高」同一套結構，差別只在 `leg_option_type()`
    決定窮舉哪一側的鏈）。

    A 層健全性判準沿用既有精神（配對層級的結構合法性，不重複 apply_
    filters 已做過的報價品質檢查）：`net_mid <= 0`——三腿組合出來的
    平均成本不是真正的 debit，這組合本身不成立（不是報價壞了，是這三
    個履約價湊不出一個有意義的 Butterfly）。**不在這裡檢查 max_loss**
    ——那是 T05（#226）的 B 層安全網職責（見 `validate_derived_values`
    的 `max_loss_fn` 參數），這裡只做配對層級的結構前提。`PairReport`
    沿用既有型別（欄位形狀通用，命名雖是「pair」但不因此另建一個
    幾乎相同的型別，Standards：避免 Primitive Obsession 式的過度切分）。

    `should_stop`：OPTION-CHASER-CLOSEOUT-004（PR #250 review Finding
    3）——呼叫端給的中止判準，每 `_ABORT_CHECK_EVERY` 個組合徵詢一次，
    回 `True` 就**停止枚舉**、把已經累積的組合原樣回傳（`PairReport`
    只反映真的走訪過的組合數，不假裝走完）。REPAIR-08（#245）加的
    soft deadline 原本只活在 `service._butterfly_result()` 的估值迴圈
    裡，而枚舉在那之前就已經跑完並把整份 `C(n,3)` 清單建好——異常龐大
    的鏈（例如某個 symbol 的 chain 意外回傳遠超正常量級的合約數）因此
    可能在任何檢查點生效之前就耗掉整個時間預算、或把 `out` 撐爆記憶體，
    最後仍被 Vercel hard kill。`combinations()` 本身是惰性的，真正會
    長大的是 `out`，這個徵詢點同時擋住時間與記憶體兩者。

    **刻意收成一個不帶語意的謂詞而不是直接吃 deadline**：本模組是排名
    ／過濾核心，既有結構紅線（`tests/test_analysis_soft_deadline.py::
    test_ranking_and_filters_do_not_import_the_soft_deadline_mechanism`）
    明文要求 soft deadline 機制不得滲透進 `ranking.py`／`filters.py`。
    這裡因此不認識時鐘、不認識 deadline，只知道「呼叫端說停就停」；
    政策留在 `service.py`（它傳進來的是
    `lambda: time.monotonic() >= deadline`）。

    `None`（預設）＝不啟用，行為與這個參數加入前逐位元相同。
    """
    by_expiry: dict[str, list[OptionContract]] = {}
    for c in legs:
        by_expiry.setdefault(c.expiry, []).append(c)
    total = 0
    removed = 0
    seen = 0
    out: list[tuple[OptionContract, OptionContract, OptionContract]] = []
    for expiry in sorted(by_expiry):
        group = sorted(by_expiry[expiry], key=lambda c: (c.strike, c.contract_symbol))
        for lo, mid, hi in combinations(group, 3):   # lo.strike < mid.strike < hi.strike
            if should_stop is not None:
                seen += 1
                if seen % _ABORT_CHECK_EVERY == 0 and should_stop():
                    return out, PairReport(total_pairs=total,
                                           removed_sanity=removed,
                                           passed=len(out))
            if lo.strike == mid.strike or mid.strike == hi.strike:
                continue
            total += 1
            if not butterfly_structural_ok(lo, mid, hi):
                removed += 1
                continue
            out.append((lo, mid, hi))
    return out, PairReport(total_pairs=total, removed_sanity=removed, passed=len(out))
