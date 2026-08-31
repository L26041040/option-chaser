"""Application service — single shared entry for CLI and GUI (v3 spec §2.2)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .data.snapshot import find_contract, load_snapshot, save_snapshot, snapshot_today
from .dividends import DividendHistory, compute_q
from .filters import (apply_filters, generate_butterfly_triples, generate_spread_pairs,
                      is_spread_wide, monotonicity_violations, quality_flag_counts,
                      validate_derived_values)
from .matrix import GUI_MAX_GAP_DAYS, date_axis, matrix_grid, price_axis
from .models import (AnalysisParams, BUTTERFLY_STRATEGIES, ChainSnapshot, FetchError,
                     FilterReport, PairReport, ParamError, QualityFlagCount,
                     SPREAD_STRATEGIES, STRATEGIES, DIRECTION_LABELS, derive_direction,
                     is_bullish, subtype_eligible)
from .ranking import (BAND_ORDER, _butterfly_tie_key, _spread_tie_key, _tie_break_key,
                      baseline_return, build_butterfly_reasons, build_reasons,
                      build_spread_reasons, butterfly_baseline_return, classify,
                      rank, rank_butterflies, rank_spreads, return_at_price,
                      spread_baseline_return)
from .report import (STRATEGY_LABELS, render, render_butterflies, render_filter_only,
                     render_spreads)
from .scenarios import (ResilienceMetrics, ScenarioVector, natural_cost,
                        resilience_metrics, _grid_price, _value_fn)
from .timeframe import (TargetMonth, calendar_anchor, ensure_month_open,
                        select_expiries)
from .ratecurve import RateCurve, rate_for_tenor
from .valuation import (ButterflyValuation, ContractValuation, DAYS_PER_YEAR,
                        SpreadValuation, butterfly_scenario_value, catchup_price,
                        evaluate_butterfly, evaluate_contract, evaluate_spread,
                        leg_greeks, leg_rate, scenario_leg_value,
                        spread_scenario_value)

Progress = Callable[[str], None]

# T12（附錄 A14.1）：利率曲線 loader = (today) -> (RateCurve | None, 報告註記)。
# 只有網路路徑（run／workspace 群組刷新）預設接真管線；run_offline 預設 None，
# 快照重放與測試因此決定性且零網路。
RateCurveLoader = Callable[[date], tuple[RateCurve | None, str]]

# #123（spec #117 §2）：股利／配息資料 loader = (symbol, today) ->
# (歷史或 None, 報告參數行註記)。與 `RateCurveLoader` 同一種介面形狀——
# 只有網路路徑預設接真管線；`run_offline`／`run_with_snapshot` 預設
# `None`，快照重放與測試因此決定性且零網路。回傳的是**金額清單**
# （`DividendHistory`），不是算好的 q——q 要用**當次快照的 spot**現算
# （研究文件 §7.5：快取比例會凍結一個過期的價格基準），這裡只負責
# 「這個標的過去有哪些配息」這件事。
DividendLoader = Callable[[str, date], tuple[DividendHistory | None, str]]


def default_rate_curve_loader(today: date):
    from .data.treasury import load_rate_curve  # lazy: offline paths never觸網
    return load_rate_curve(today)


def default_dividend_loader(symbol: str, today: date):
    from .data.dividends import load_dividend_history  # lazy: 同上
    return load_dividend_history(symbol, today)


@dataclass(frozen=True)
class AnalysisRequest:
    symbol: str
    base_params: AnalysisParams
    strategies: tuple[str, ...]


@dataclass(frozen=True)
class MatrixView:
    # 決策 M（#109）：第三個元素是 `move_pct`（相對 `spot` 的變動分數），
    # 直接沿用 `price_axis()` 回傳的同一組 3-tuple，不在這裡另外算。
    prices: tuple[tuple[float, str, float], ...]
    dates: tuple[tuple[str, str], ...]
    cells: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class PricePoint:
    """V7（#55）：一個劇本價位與該候選在那個價位上的報酬。

    `ret` 的口徑與主排名數字完全相同（`ranking.return_at_price`），三價位
    才能與頭條那個數字並排讀——包含估值日：價差用自身到期日、單腿用
    日曆錨點，兩條路徑各自沿用既有裁示。
    """
    label: str        # "worst" | "target" | "best"
    price: float
    ret: float


@dataclass(frozen=True)
class ComparatorView:
    """#115（spec #117 §4）：Crossover 對照——就是這組 Spread 買腿本身，
    不是搜尋或轉換出來的另一份合約。同 option type／履約價／到期日是
    **定義**使然：Call Spread 的對照恆是 Long Call、Put Spread 恆是
    Long Put，直接讀買腿既有報價，不做任何 option-type 轉換、不查找
    另一張合約。

    這正是 D1（#14）舊 `catchup_price` 曾經犯過的錯誤（put 買腿去找
    「同履約價的 call」）的修正——新的作法從根本上不允許那種查找存在：
    `option_type`／`strike`／`expiry` 三欄直接複製自 `SpreadValuation.
    long_leg`，沒有任何分支邏輯可以讓它們與買腿本身不同。

    `option_type` 讓前端能直接顯示「Long Call」／「Long Put」，不必
    自己從 strategy 反推。
    """
    option_type: str
    strike: float
    expiry: str
    cost: float          # 買腿 Ask（worst 成交口徑，與 Spread net_worst 一致）
    matrix: MatrixView    # 與該 Spread 自己的 matrix 同一組 price×date grid


@dataclass(frozen=True)
class CandidateView:
    valuation: ContractValuation | SpreadValuation
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    matrix: MatrixView
    # T12（附錄 A14.2）：主數字成本口徑＝最差成交假設（單腿 Ask／價差
    # net_worst）。原 natural_return 與主數字重合，已合併進 baseline_return。
    baseline_pnl: float        # 估值 − 成本（最差口徑，每股）
    baseline_return: float     # ranking.baseline_return / spread_baseline_return
    scenario: ScenarioVector
    completion_curve: tuple[tuple[float, float], ...]
    completion_prices: tuple[float, ...]
    completion_threshold: float | None
    breakeven_at_target: float | None
    retention: float
    buffer_days: int
    # MVP V3（#104，spec #102 決策 F）：`quote_warning` 是選取閘門用的
    # 複合旗標（zero_vol or wide_spread），**不對外顯示**——只供
    # `_build_groups` 內部挑選 default_pair。顯示旗標另外分家成
    # `wide_spread_warning`（見下），語意收斂成單一、可行動的判準。
    # T04（#220，#217 決策 D）：friction 已自 canonical model 退場，
    # 原本的第三個條件（fr>0.25）隨之移除，不新增任何替代指標——這是
    # 本票唯一預期中的 quote_warning 行為變動。
    # ⚠ 更正（`/code-review` Spec 軸抓到）：這個公式變動**確實會讓某些
    # 候選的 quote_warning 從 True 翻成 False**——例如
    # `contracts/analysis_sample.json` 的 bull-call-spread|118|122
    # 候選（friction 恰為 0.25、wide_spread_warning=False），先前
    # commit 聲稱「沒有任何候選單獨依賴這個條件」不準確，已用契約樣本
    # 逐位元核對推翻。真正成立的是：quote_warning 唯一的消費端是
    # `_build_groups()` 產生的 `default_selection`／
    # `ExpiryGroup.rows[].badges`——這是 v4 舊「到期日分組比較」遺留
    # 結構，`src/` 全站零消費者（#104 施工時已 grep 確認過的既有死碼，
    # 非本票新產生），因此這個翻轉**沒有任何使用者可見影響**，但這是
    # 「消費端剛好是死碼」的巧合結果，不是「這個公式改動本身不影響
    # 任何候選」。
    quote_warning: bool
    # 顯示旗標（決策 F）：⚠ 徽章與候選池文案只認這個——僅 `is_spread_wide`
    # 一項，不含零成交量。
    wide_spread_warning: bool
    # FB5-03（#64）：無套利一致性違反（相鄰履約價 ask 不單調）。獨立於
    # `quote_warning`，不合併——嚴重性與成因都不同（配對關係違反，不是
    # 單一數值超標），合併會讓使用者分不出「報價可疑，可能是陳舊資料」
    # 跟「這組候選價差比較寬」是同一等級的事。
    monotonicity_warning: bool
    theta_day_rate: float      # |淨Θ| / Mid 成本
    vega_per_pt: float         # 淨Vega(每1 IV百分點) / Mid 成本
    decay_30d_return: float    # S=spot、IV不變、today+30(或到期)估值報酬
    # MVP V3（#112，spec #102 決策 H）：這組候選估值實際用到的利率與
    # 年期——`leg_rate(p, expiry)` 查表結果（T12 附錄A14.1 既有查表
    # 函式，估值管線本來就在用，這裡只是把同一個結果也吐進契約）；
    # 年期＝分析日到候選自身到期日的年分數，與 `rate_by_expiry` 建表
    # 時（`_resolve_rates`）用的公式逐字相同。前端只格式化，不查表、
    # 不換算。
    rate_used: float
    rate_tenor_years: float
    # D1（#14）：Long Call 追平價格 S*=K+C×(1+R)——只對 Spread 有意義
    # （買腿履約價 K 的同履約價 Call 若報價缺失也是 None）；單腳恆為 None。
    # R2 裁示已移除對應 UI，本欄位只留 migration／regression 用，#115
    # 的新 `comparator` 才是 Crossover 實際使用的欄位（見下）。
    catchup_price: float | None = None
    # V7（#55）。預設空 tuple：沒設兩端、也沒走 `_v4_fields` 的呼叫端
    # （若有）都不會壞。
    price_ladder: tuple[PricePoint, ...] = ()
    # #113（spec #117 contracts 表）：這組候選的估值是否經過 carry 校準。
    # 單腿讀 `valuation.carry.carry_calibrated`；價差要求兩條腿都校準
    # 成功才算——任一腿退回今天的行為，整組候選就不是「carry 校準過」。
    # False 時 UI 必須說得出「這組估值未經 carry 校準」（spec §10-4）。
    carry_calibrated: bool = False
    # #115（spec #117 §4）：Crossover 對照——只有 Spread 候選才有意義，
    # 單腿恆為 None（沒有「跟自己比較」的概念）；Spread 候選只在買腿
    # 報價缺失（結構上不該發生——上游過濾早已保證雙腿報價齊全，這裡是
    # 防禦性核對，不假造）時才是 None。
    comparator: ComparatorView | None = None
    # T15（#230，Initial V2 spec #217）：非單調結構（Butterfly）的獲利
    # 區間——兩個邊界價，見 `valuation.ButterflyProfitRegion`。單腿／
    # Spread（單調家族）恆為 `None`；Butterfly 峰值連進場成本都賺不回來
    # 時也是 `None`（到期時任何價位都無法獲利，不是「沒算」）。這是
    # `completion_threshold`／`breakeven_at_target`（單調家族用的保本
    # 掃描單一數字，AC 明文「不硬擠成單一數字」）在非單調結構上的替代
    # 呈現，兩者互斥出現：Butterfly 恆為 `completion_threshold=None`。
    profit_region: tuple[float, float] | None = None


@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    status: str
    candidates: tuple[CandidateView, ...]
    ranked_bands: dict[str, list[ContractValuation]] | None
    ranked_spreads: tuple[SpreadValuation, ...] | None
    n_qualified: int
    filter_report: FilterReport | None
    pair_report: PairReport | None
    report_text: str | None
    message: str
    # v4 spec §3.2: per-(expiry, strategy) best CandidateView over ALL qualified
    # candidates (not just the top-3 kept in `candidates`), used for grouping.
    expiry_best: tuple[CandidateView, ...] = ()
    expiry_counts: tuple[tuple[str, int], ...] = ()
    # T9（#23，需求三）：每個到期日各自的完整前十名——分組後各自取前 10，
    # 不是跨到期日的全域前 10；只有 spread 策略填入（MVP 範圍，附錄A13）。
    expiry_top10: tuple[tuple[str, tuple[CandidateView, ...]], ...] = ()
    # T9（附錄A7）：該次全部有效候選，依到期日分組、組內已排序——供 store 層
    # 序列化「所屬到期日內名次」等歷史五欄位；不建 CandidateView（無 Heatmap
    # 矩陣），成本控制同 `expiry_best` 的既有取捨。
    expiry_ranked: tuple[tuple[str, tuple[SpreadValuation, ...]], ...] = ()
    # FB5-04（#65，spec #61）：C 類品質標示在**整個合格池**（腿級，`filters.
    # quality_flag_counts()`）裡各出現幾次——單腿／價差都用同一份 `qualified`
    # 計算，不受 `expiry_top10` 只填價差策略那個既有 MVP 範圍限制影響
    # （附錄A13）。空池（`status == "empty"`）維持預設空 tuple。
    quality_flags: tuple[QualityFlagCount, ...] = ()
    # T15（#230，Initial V2）：`ranked_bands`（單腿）／`ranked_spreads`
    # （Vertical）同一種模式的第三個具名欄位——不是通用容器，跟既有兩個
    # 一樣是各自 family 專屬的排序結果。預設 `None`：既有兩個呼叫端
    # （單腿／Spread）不需要知道這個欄位存在。
    ranked_butterflies: tuple[ButterflyValuation, ...] | None = None


@dataclass(frozen=True)
class ExpiryGroupRow:
    strategy: str
    candidate: CandidateView
    badges: tuple[str, ...]


@dataclass(frozen=True)
class ExpiryGroup:
    expiry: str
    buffer_days: int
    rows: tuple[ExpiryGroupRow, ...]
    hidden_count: int


@dataclass(frozen=True)
class ComparisonRow:
    strategy: str
    label: str
    expiry: str
    cost: float                # 最差成交口徑（單腿 Ask／價差 net_worst）
    baseline_return: float
    breakeven: float
    max_profit: float | None


@dataclass(frozen=True)
class SnapshotMeta:
    symbol: str
    spot: float
    fetched_at: str
    source: str
    snapshot_path: str
    target_move: float


@dataclass(frozen=True)
class AnalysisResult:
    request: AnalysisRequest
    meta: SnapshotMeta
    snapshot: ChainSnapshot
    today: date
    results: tuple[StrategyResult, ...]
    comparison: tuple[ComparisonRow, ...]
    best_strategy: str | None
    expiry_groups: tuple[ExpiryGroup, ...]
    hidden_expiries: tuple[str, ...]
    default_selection: tuple[str, str] | None
    # T10（#24，附錄A8.5）：baseline＝距日曆錨點最近的實際到期日（六點規則，
    # `timeframe.select_expiries`）；None 僅見於鏈上零到期日（附錄A12.2）。
    baseline_expiry: str | None
    # 詳細頁進頁預設選中：baseline 期自己的第 1 名（不是 `default_selection`
    # 的全域最高報酬避警示邏輯——那是 v4 舊有、與 app.py 快速分析頁共用的
    # 語意，T10 不動它）。baseline 期若沒有任何候選（如零合格候選）→ None。
    baseline_selection: tuple[str, str] | None


def _emit(progress: Progress | None, msg: str) -> None:
    if progress is not None:
        progress(msg)


def _skip_message(direction: str) -> str:
    """T08（#225，Initial V2 spec #217）：訊息內容改用『這個方向適用
    哪些既有 subtype』的資料反查（`SUBTYPE_DIRECTIONS`），不再硬編碼
    成兩段互斥文字——新增 subtype 時這裡不需要修改，訊息會自動涵蓋
    新的 eligible／skipped 名單。"""
    label = DIRECTION_LABELS.get(direction, direction)
    skipped, available = [], []
    for s in STRATEGIES:
        (available if subtype_eligible(s, direction) else skipped).append(
            STRATEGY_LABELS[s])
    msg = f"目前劇本方向為「{label}」，因此未執行 {'、'.join(skipped)}。"
    if available:
        msg += f"可改選 {'、'.join(available)}。"
    return msg


def _matrix_view(value_fn, cost: float, spot: float, p: AnalysisParams,
                 today: date, expiry_iso: str) -> MatrixView:
    # QA 修正：價格軸上下限吃劇本區間（最高／最低價位）——兩端都沒填時
    # `price_axis` 自己退回既有算式，這裡不做判斷。
    prices = price_axis(spot, p.target_price, is_bullish(p.strategy),
                        best_price=p.best_price, worst_price=p.worst_price)
    # QA-FIX-5（QA-01）：GUI 走高密度日期軸（欄距上限約一個月）。
    # CLI 文字報告（`report.py`）刻意不傳這個參數，維持既有七欄——
    # 密度是呈現層決策，兩條路徑各自選自己合適的。
    dates = date_axis(today, date.fromisoformat(expiry_iso),
                      max_gap_days=GUI_MAX_GAP_DAYS)
    cells = matrix_grid(value_fn, cost, prices, dates)
    return MatrixView(prices=tuple(prices),
                      dates=tuple((d.isoformat(), lbl) for d, lbl in dates),
                      cells=cells)


def _mid_cost(val: ContractValuation | SpreadValuation | ButterflyValuation) -> float:
    if isinstance(val, (SpreadValuation, ButterflyValuation)):
        return val.net_mid
    return val.mid


def _butterfly_leg_greeks(bv: ButterflyValuation, spot: float, today: date,
                          p: AnalysisParams):
    """三腿各自的 Greeks（今天的 (t_now, r) 查表方式與既有 Spread 分支
    逐字相同，只是多一條腿）——`_net_theta`／`_net_vega` 共用，避免兩處
    複製貼上同一段查表邏輯。"""
    lo, mid, hi = bv.low_leg, bv.mid_leg, bv.high_leg
    t_now = (date.fromisoformat(lo.expiry) - today).days / 365.0
    g_lo = leg_greeks(lo.option_type, spot, lo.strike, t_now,
                      leg_rate(p, lo.expiry), bv.low_carry.sigma, bv.low_carry.q)
    g_mid = leg_greeks(mid.option_type, spot, mid.strike, t_now,
                       leg_rate(p, mid.expiry), bv.mid_carry.sigma, bv.mid_carry.q)
    g_hi = leg_greeks(hi.option_type, spot, hi.strike, t_now,
                      leg_rate(p, hi.expiry), bv.high_carry.sigma, bv.high_carry.q)
    return g_lo, g_mid, g_hi


def _net_theta(val: ContractValuation | SpreadValuation | ButterflyValuation,
              spot: float, today: date, p: AnalysisParams) -> float:
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        t_now = (date.fromisoformat(lng.expiry) - today).days / 365.0
        # #113：讀 carry 校準後的 (q, sigma)，未校準時精確等於 vendor IV／
        # q=0（見 LegCarry fallback 設計），既有行為不變。
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now,
                         leg_rate(p, lng.expiry), val.long_carry.sigma,
                         val.long_carry.q)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now,
                         leg_rate(p, sht.expiry), val.short_carry.sigma,
                         val.short_carry.q)
        return g_l.theta_per_day - g_s.theta_per_day
    if isinstance(val, ButterflyValuation):
        g_lo, g_mid, g_hi = _butterfly_leg_greeks(val, spot, today, p)
        return g_lo.theta_per_day - 2.0 * g_mid.theta_per_day + g_hi.theta_per_day
    return val.theta_per_day


def _net_vega(val: ContractValuation | SpreadValuation | ButterflyValuation,
             spot: float, today: date, p: AnalysisParams) -> float:
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        t_now = (date.fromisoformat(lng.expiry) - today).days / 365.0
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now,
                         leg_rate(p, lng.expiry), val.long_carry.sigma,
                         val.long_carry.q)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now,
                         leg_rate(p, sht.expiry), val.short_carry.sigma,
                         val.short_carry.q)
        return g_l.vega_per_pct - g_s.vega_per_pct
    if isinstance(val, ButterflyValuation):
        g_lo, g_mid, g_hi = _butterfly_leg_greeks(val, spot, today, p)
        return g_lo.vega_per_pct - 2.0 * g_mid.vega_per_pct + g_hi.vega_per_pct
    return val.vega_per_pct


def _decay_30d(val: ContractValuation | SpreadValuation, spot: float,
               today: date, p: AnalysisParams) -> float:
    fn, mid, _, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    d30 = min(today + timedelta(days=30), expiry)
    return (fn(spot, d30, p) - mid) / mid


def _price_ladder(val: ContractValuation | SpreadValuation,
                  p: AnalysisParams) -> tuple[PricePoint, ...]:
    """V7（#55）：劇本區間兩端與目標價各自的報酬，由低到高排列。

    未設定的端不佔位（票上：「未設定的端不顯示、不佔位報錯」），所以只填
    一端時這裡就只有兩個點。順序固定 worst → target → best，讓呈現層不必
    自己排序，也讓「越右邊越樂觀」成為版面上的固定語意。
    """
    points = [("worst", p.worst_price), ("target", p.target_price),
              ("best", p.best_price)]
    return tuple(PricePoint(label=label, price=price,
                            ret=return_at_price(val, price, p))
                 for label, price in points if price is not None)


def _v4_fields(val: ContractValuation | SpreadValuation | ButterflyValuation,
              spot: float, today: date, p: AnalysisParams,
              violations: frozenset[str] = frozenset(),
              resilience_cache: dict[int, ResilienceMetrics] | None = None,
              ) -> dict:
    """`violations`＝`filters.monotonicity_violations()` 的輸出，由呼叫端
    對整批 qualified 合約算一次、傳進來（FB5-03／#64）——單一候選這裡
    只做查表，不重算，避免每個候選各自重新掃一次全部合約。預設空集合：
    沒有呼叫端傳（理論上不會發生，所有 `_v4_fields` 呼叫都經過
    `_single_leg_view`／`_spread_view`／`_butterfly_view`）就是「沒有
    已知違反」，不是壞掉。

    `resilience_cache`：T09（#191）——韌性向量／完成度曲線／保本掃描
    透過 `scenarios.resilience_metrics()` 與文字報告路徑
    （`report._resilience_lines`）共用同一個依 `id(val)` 鍵入的快取，
    同一輪分析裡同一個候選不會被兩條路徑各自重算一次。不傳（`None`）
    時退回每次都重算，行為與這層快取加入前完全一樣。

    T15（#230）：`ButterflyValuation` 分支——`resilience_metrics()`
    內部的 `completion_scan()` 對它已經短路回 `(None, None)`
    （`scenarios.completion_scan` docstring），這裡因此額外算
    `profit_region`（非單調結構的替代呈現，AC 明文「不硬擠成單一
    數字」）：`ButterflyValuation.profit_region` 早在 `evaluate_
    butterfly()` 算好，這裡只是把它投影成 `(lower, upper)` 元組（或
    `None`）——不重新求根，不新增計算。既有兩個型別的 `profit_region`
    恆為 `None`（`CandidateView` 欄位預設值），這是唯一的新增鍵，
    其餘欄位對既有兩個型別逐位元不變。"""
    rm = resilience_metrics(val, spot, today, p, cache=resilience_cache)
    sv, curve, k, be = rm.scenario, rm.curve, rm.threshold, rm.breakeven
    profit_region = None
    if isinstance(val, SpreadValuation):
        expiry = val.long_leg.expiry
        zero_vol = val.long_leg.volume == 0 or val.short_leg.volume == 0
        # FB5-02（#63）：任一腿的買賣價差超過舊硬門檻公式就標——兩腿各自
        # 的報價品質，不是合成後的淨值。
        wide_spread = (is_spread_wide(val.long_leg.bid, val.long_leg.ask, p)
                      or is_spread_wide(val.short_leg.bid, val.short_leg.ask, p))
        monotonicity_warning = (val.long_leg.contract_symbol in violations
                                or val.short_leg.contract_symbol in violations)
    elif isinstance(val, ButterflyValuation):
        expiry = val.low_leg.expiry
        zero_vol = (val.low_leg.volume == 0 or val.mid_leg.volume == 0
                   or val.high_leg.volume == 0)
        wide_spread = (is_spread_wide(val.low_leg.bid, val.low_leg.ask, p)
                      or is_spread_wide(val.mid_leg.bid, val.mid_leg.ask, p)
                      or is_spread_wide(val.high_leg.bid, val.high_leg.ask, p))
        monotonicity_warning = (val.low_leg.contract_symbol in violations
                                or val.mid_leg.contract_symbol in violations
                                or val.high_leg.contract_symbol in violations)
        if val.profit_region is not None:
            profit_region = (val.profit_region.lower, val.profit_region.upper)
    else:
        expiry = val.contract.expiry
        zero_vol = val.contract.volume == 0
        wide_spread = is_spread_wide(val.contract.bid, val.contract.ask, p)
        monotonicity_warning = val.contract.contract_symbol in violations
    mid_cost = _mid_cost(val)
    return dict(
        scenario=sv,
        completion_curve=curve,
        completion_prices=tuple(_grid_price(spot, p.target_price, k)
                                for k, _ in curve),
        completion_threshold=k, breakeven_at_target=be,
        retention=1.0 + dict(sv.entries)["S1"],
        buffer_days=(date.fromisoformat(expiry) - p.anchor).days,
        # FB5-02（#63）：沿用既有的 `quote_warning` 機制，不新造一套——
        # 買賣價差過寬是這個既有布林旗標的觸發條件之一。單調性違反
        # 不加進來（見 `monotonicity_warning` 欄位註解）。
        quote_warning=zero_vol or wide_spread,
        wide_spread_warning=wide_spread,
        monotonicity_warning=monotonicity_warning,
        theta_day_rate=abs(_net_theta(val, spot, today, p)) / mid_cost,
        vega_per_pt=_net_vega(val, spot, today, p) / mid_cost,
        decay_30d_return=_decay_30d(val, spot, today, p),
        # MVP V3（#112）：與估值管線同一個查表結果／同一條年期公式
        # （`_resolve_rates` 建 `rate_by_expiry` 時所用），不是另外重算。
        rate_used=leg_rate(p, expiry),
        rate_tenor_years=(date.fromisoformat(expiry) - today).days / DAYS_PER_YEAR,
        price_ladder=_price_ladder(val, p),
        profit_region=profit_region)


def _single_leg_view(v: ContractValuation, band: str,
                     ranked: dict[str, list[ContractValuation]], spot: float,
                     n_qualified: int, today: date, p: AnalysisParams,
                     violations: frozenset[str] = frozenset(),
                     resilience_cache: dict[int, ResilienceMetrics] | None = None,
                     ) -> CandidateView:
    pros, cons = build_reasons(v, band, ranked, spot, n_qualified, p)
    # #113：矩陣迴圈維持 (S,t) 純函式——carry 已在 evaluate_contract() 算
    # 過一次、掛在 v.carry 上，這裡直接傳，不重新反解。
    mv = _matrix_view(
        lambda S, d, c=v.contract, carry=v.carry: scenario_leg_value(c, S, d, p, carry=carry),
        v.contract.ask, spot, p, today, v.contract.expiry)
    return CandidateView(
        valuation=v, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=v.baseline_value - v.contract.ask,
        baseline_return=baseline_return(v),
        carry_calibrated=v.carry.carry_calibrated,
        **_v4_fields(v, spot, today, p, violations, resilience_cache))


def _spread_catchup_price(sv: SpreadValuation, snap: ChainSnapshot) -> float | None:
    """D1（#14）：S*=K+C×(1+R)。K／R 固定用買腿（long_leg）本身；C＝同履約價
    Call 的實際成本——買腿本身是 call（bull-call-spread）時就是它自己的
    Ask，是 put（bear-put-spread）時得從同一快照另外找同履約價的 call。
    找不到報價回傳 None（render 層負責顯示「無法計算」，不拋錯）。"""
    strike, expiry = sv.long_leg.strike, sv.long_leg.expiry
    if sv.long_leg.option_type == "call":
        call_cost = sv.long_leg.ask
    else:
        call = find_contract(snap, "call", strike, expiry)
        call_cost = call.ask if call is not None else None
    if call_cost is None:
        return None
    return catchup_price(strike, call_cost, spread_baseline_return(sv))


def _spread_comparator(sv: SpreadValuation, spot: float, today: date,
                       p: AnalysisParams) -> ComparatorView | None:
    """#115（spec #117 §4）：Crossover 對照＝買腿本身，逐字讀既有欄位。

    刻意不呼叫 `find_contract`、`ranking.classify`、`ranking.rank` 或
    任何候選搜尋——`option_type`／`strike`／`expiry` 三欄直接取自
    `sv.long_leg`，沒有分支可以讓它們偏離買腿本身（見 `ComparatorView`
    docstring）。matrix 用同一個 `_matrix_view`（同一組 spot／today／
    p／expiry 輸入 ⇒ 同一組 price×date 軸，逐位元與 Spread 自己的
    matrix 同形狀），value_fn 用買腿已經算過一次的 `sv.long_carry`
    （不重新反解 IV，架構要求與 `_single_leg_view` 一致）。

    買腿報價缺失（`ask is None`）→ None，不假造——結構上不該發生
    （`evaluate_spread` 上游已保證雙腿報價齊全才會走到這裡），這裡是
    誠實揭露的防禦性核對，不是預期路徑。
    """
    leg = sv.long_leg
    if leg.ask is None:
        return None
    mv = _matrix_view(
        lambda S, d, c=leg, carry=sv.long_carry: scenario_leg_value(c, S, d, p, carry=carry),
        leg.ask, spot, p, today, leg.expiry)
    return ComparatorView(option_type=leg.option_type, strike=leg.strike,
                          expiry=leg.expiry, cost=leg.ask, matrix=mv)


def _spread_view(sv: SpreadValuation, idx: int, n_pairs: int, spot: float,
                 today: date, p: AnalysisParams, snap: ChainSnapshot,
                 violations: frozenset[str] = frozenset(),
                 resilience_cache: dict[int, ResilienceMetrics] | None = None,
                 ) -> CandidateView:
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    mv = _matrix_view(
        lambda S, d, lng=sv.long_leg, sht=sv.short_leg, lc=sv.long_carry, \
              sc=sv.short_carry:
            spread_scenario_value(lng, sht, S, d, p, long_carry=lc, short_carry=sc),
        sv.net_worst, spot, p, today, sv.long_leg.expiry)
    return CandidateView(
        valuation=sv, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=sv.baseline_value - sv.net_worst,
        baseline_return=spread_baseline_return(sv),
        catchup_price=_spread_catchup_price(sv, snap),
        # #113：兩腿都校準成功才算「這組候選 carry 校準過」——任一腿
        # 退回今天的行為，整組候選的估值就不是全然校準過的。
        carry_calibrated=(sv.long_carry.carry_calibrated
                          and sv.short_carry.carry_calibrated),
        comparator=_spread_comparator(sv, spot, today, p),
        **_v4_fields(sv, spot, today, p, violations, resilience_cache))


def _butterfly_view(bv: ButterflyValuation, idx: int, n_triples: int, spot: float,
                    today: date, p: AnalysisParams,
                    violations: frozenset[str] = frozenset(),
                    resilience_cache: dict[int, ResilienceMetrics] | None = None,
                    ) -> CandidateView:
    """T15（#230，Initial V2 spec #217）：`_spread_view()` 的三腿版本。
    無 `catchup_price`／`comparator`（兩者皆只對兩腿 Spread 有意義，
    預設 `None` 即可，不必顯式傳）。"""
    pros, cons = build_butterfly_reasons(bv, idx, n_triples, p)
    mv = _matrix_view(
        lambda S, d, lo=bv.low_leg, mid=bv.mid_leg, hi=bv.high_leg, \
              lc=bv.low_carry, mc=bv.mid_carry, hc=bv.high_carry:
            butterfly_scenario_value(lo, mid, hi, S, d, p, low_carry=lc,
                                     mid_carry=mc, high_carry=hc),
        bv.net_worst, spot, p, today, bv.low_leg.expiry)
    return CandidateView(
        valuation=bv, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=bv.baseline_value - bv.net_worst,
        baseline_return=butterfly_baseline_return(bv),
        # 三腿都校準成功才算「這組候選 carry 校準過」——與 Spread 的
        # 「兩腿都校準」同一種全稱判準延伸到三腿。
        carry_calibrated=(bv.low_carry.carry_calibrated
                          and bv.mid_carry.carry_calibrated
                          and bv.high_carry.carry_calibrated),
        **_v4_fields(bv, spot, today, p, violations, resilience_cache))


def valuation_key(v: ContractValuation | SpreadValuation | ButterflyValuation) -> str:
    """需求八：Spread／單腳／Butterfly 身分鍵，直接吃估值物件——
    `candidate_key()` 的 CandidateView 包裝只是它的一層外皮。T9 序列化
    全部有效候選的歷史五欄位時不需要（也不划算）先建 CandidateView，
    所以底層鍵在這裡獨立出來重用，公開給 `store.py` 跨模組呼叫（非本
    模組私用，因此不加底線）。"""
    if isinstance(v, SpreadValuation):
        return (f"{_strategy_of(v)}|{v.long_leg.strike:g}|"
                f"{v.short_leg.strike:g}|{v.long_leg.expiry}")
    if isinstance(v, ButterflyValuation):
        return (f"{_strategy_of(v)}|{v.low_leg.strike:g}|"
                f"{v.mid_leg.strike:g}|{v.high_leg.strike:g}|{v.low_leg.expiry}")
    return f"{_strategy_of(v)}|{v.contract.strike:g}|{v.contract.expiry}"


def candidate_key(cv: CandidateView) -> str:
    return valuation_key(cv.valuation)


def _strategy_of(v) -> str:
    if isinstance(v, SpreadValuation):
        return ("bull-call-spread" if v.long_leg.option_type == "call"
                else "bear-put-spread")
    if isinstance(v, ButterflyValuation):
        return "call-fly" if v.option_type == "call" else "put-fly"
    return "long-call" if v.contract.option_type == "call" else "long-put"


def _expiry_of(cv: CandidateView) -> str:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        return v.long_leg.expiry
    if isinstance(v, ButterflyValuation):
        return v.low_leg.expiry
    return v.contract.expiry


def _build_groups(results: tuple[StrategyResult, ...],
                  strategies_order: tuple[str, ...], anchor: date
                  ) -> tuple[tuple[ExpiryGroup, ...], tuple[str, ...],
                            tuple[str, str] | None]:
    """v4 spec §3.2 的分組與全域徽章。

    窮舉範圍已由六點規則收斂到至多五檔到期日，原本「先窮舉全鏈、事後取樣顯示」
    的抽樣層因此整個消失：每一檔被選中的到期日都是一組，`hidden_expiries` 恆空。
    """
    order_index = {s: i for i, s in enumerate(strategies_order)}
    all_pairs: list[tuple[str, CandidateView]] = []
    pe_best: dict[tuple[str, str], CandidateView] = {}
    total_counts: dict[str, int] = {}
    for res in results:
        if res.status != "ok":
            continue
        for cv in res.expiry_best:
            pe_best[(_expiry_of(cv), res.strategy)] = cv
            all_pairs.append((res.strategy, cv))
        for exp, cnt in res.expiry_counts:
            total_counts[exp] = total_counts.get(exp, 0) + cnt

    if not all_pairs:
        return (), (), None

    def _return_key(pair: tuple[str, CandidateView]) -> tuple:
        s, cv = pair
        return (-cv.baseline_return, order_index[s], candidate_key(cv))

    def _resilience_key(pair: tuple[str, CandidateView]) -> tuple:
        s, cv = pair
        return (-cv.scenario.worst_return, -cv.baseline_return, order_index[s],
                candidate_key(cv))

    top_return_pair = min(all_pairs, key=_return_key)
    top_resilience_pair = min(all_pairs, key=_resilience_key)
    no_warning = [pair for pair in all_pairs if not pair[1].quote_warning]
    default_pair = min(no_warning, key=_return_key) if no_warning else top_return_pair

    def _row_badges(s: str, cv: CandidateView) -> tuple[str, ...]:
        badges = []
        if cv.quote_warning:
            badges.append("warning")
        if s == top_return_pair[0] and cv is top_return_pair[1]:
            badges.append("top_return")
        if s == top_resilience_pair[0] and cv is top_resilience_pair[1]:
            badges.append("top_resilience")
        return tuple(badges)

    def _make_rows(exp: str) -> tuple[ExpiryGroupRow, ...]:
        rows = [ExpiryGroupRow(strategy=s, candidate=pe_best[(exp, s)],
                               badges=_row_badges(s, pe_best[(exp, s)]))
                for s in strategies_order if (exp, s) in pe_best]
        rows.sort(key=lambda r: -r.candidate.baseline_return)
        return tuple(rows)

    def _make_group(exp: str) -> ExpiryGroup:
        rows = _make_rows(exp)
        hidden_count = total_counts.get(exp, 0) - len(rows)
        # 緩衝天數的參考日＝日曆錨點（附錄 A9），不是任何被發明出來的目標日。
        return ExpiryGroup(expiry=exp,
                           buffer_days=(date.fromisoformat(exp) - anchor).days,
                           rows=rows, hidden_count=hidden_count)

    expiries = sorted({_expiry_of(cv) for _, cv in all_pairs})
    expiry_groups = tuple(_make_group(exp) for exp in expiries)
    default_selection = (_expiry_of(default_pair[1]), candidate_key(default_pair[1]))
    return expiry_groups, (), default_selection


def _baseline_selection(expiry_groups: tuple[ExpiryGroup, ...],
                        baseline_expiry: str | None
                        ) -> tuple[str, str] | None:
    """T10（#24，附錄A8.5）：詳細頁預設選中＝baseline 期自己的第 1 名。

    `_make_rows()` 已把每組 `rows` 依 baseline_return 由高到低排過序，
    第 0 個就是該期第 1 名——不必另建排序或另跑一次全域比較（那是
    `default_selection` 的既有語意，與此處刻意不同，見 AnalysisResult
    欄位註解）。baseline 期若不在 `expiry_groups`（如零合格候選、或鏈上
    零到期日）→ None，UI 端自行處理「無可選」的顯示。
    """
    group = next((g for g in expiry_groups if g.expiry == baseline_expiry),
                None)
    if group is None or not group.rows:
        return None
    return (baseline_expiry, candidate_key(group.rows[0].candidate))


def _single_leg_result(p: AnalysisParams, snap: ChainSnapshot,
                       today: date) -> StrategyResult:
    qualified, freport = apply_filters(snap.contracts, p)
    if not qualified:
        return StrategyResult(
            strategy=p.strategy, status="empty", candidates=(),
            ranked_bands=None, ranked_spreads=None, n_qualified=0,
            filter_report=freport, pair_report=None,
            report_text=render_filter_only(snap, p, freport, today),
            message="目前沒有符合流動性與報價條件的合約。")
    # FB5-03（#64）：無套利一致性只在**通過 A/B 類硬門檻的合約**之間比較
    # ——跟不合格的報價比較沒有意義，也算一次就好，不必每個候選各自重算。
    violations = monotonicity_violations(qualified)
    quality_flags = quality_flag_counts(qualified, violations, p)
    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    # T05（#226，Initial V2 spec #217）：B 層——導出層數學安全網，接在
    # 既有計算路徑之後、排名之前，獨立於 A 層（`apply_filters()`）成立。
    # `n_qualified` 隨之改用 B 層之後的數量——「合格池」語意上就該是
    # 「真的進得了排名」的那些，不是「通過 A 層但可能算出不可能值」。
    vals, b_stage = validate_derived_values(
        vals, natural_cost, baseline_return,
        identity_fn=lambda v: v.contract.contract_symbol)
    freport = dataclasses.replace(freport, stages=freport.stages + (b_stage,),
                                  passed=len(vals))
    n_qualified = len(vals)
    ranked = rank(vals, p)
    # T09（#191）：韌性／完成度指標只算一次，文字報告與 View 兩條路徑
    # 共用同一個快取——`ranked`／`vals_sorted`／`best_by_expiry` 全部
    # 沿用 `vals` 裡的同一批物件（`sorted()`／切片不複製元素），`id(val)`
    # 因此在文字報告（下面 `render()`）與 View（下面 `_single_leg_view()`）
    # 兩條路徑之間、以及 View 自己的 `candidates`／`expiry_best` 兩個
    # 容器之間都能正確命中。
    resilience_cache: dict[int, ResilienceMetrics] = {}
    text = render(snap, p, freport, ranked, n_qualified=n_qualified,
                  today=today, violations=violations, quality_flags=quality_flags,
                  resilience_cache=resilience_cache)
    candidates = []
    for band in BAND_ORDER:
        if not ranked[band]:
            continue
        v = ranked[band][0]
        candidates.append(_single_leg_view(v, band, ranked, snap.spot,
                                           n_qualified, today, p,
                                           violations, resilience_cache))

    # v4 spec §3.2: per-expiry best over ALL qualified (not just top-3 bands),
    # for expiry grouping. Cost control: CandidateView only built for winners.
    #
    # T09（#222）：`by_expiry` 順便在同一輪迴圈裡收集齊——`vals_sorted`
    # 已是全域依 `(-baseline_return, *_tie_break_key)` 排序，分組後各自
    # 的相對順序與獨立對該組排序等價（全域鍵不依賴其他組），跟
    # `_spread_result()` 的既有裁示同一條理由：不必為 `expiry_top10`／
    # `expiry_ranked` 另跑一次排序。
    vals_sorted = sorted(vals, key=lambda v: (-baseline_return(v),
                                              *_tie_break_key(v)))
    counts: dict[str, int] = {}
    best_by_expiry: dict[str, ContractValuation] = {}
    by_expiry: dict[str, list[ContractValuation]] = {}
    for v in vals_sorted:
        exp = v.contract.expiry
        counts[exp] = counts.get(exp, 0) + 1
        best_by_expiry.setdefault(exp, v)
        by_expiry.setdefault(exp, []).append(v)
    expiry_best = tuple(
        # #122：分級標籤同樣只讀 classification_delta（同一條紅線），
        # 不影響 best_by_expiry 本身的選取——那是 vals_sorted 依
        # baseline_return 決定的，跟 delta 分級無關，這裡只是幫選出來
        # 的候選標一個風險級距文字。
        _single_leg_view(best_by_expiry[exp],
                         classify(best_by_expiry[exp].classification_delta,
                                 p.delta_bands),
                         ranked, snap.spot, n_qualified, today, p,
                         violations, resilience_cache)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))
    # T09（#222）：單腿路徑補齊與 Spread 同形狀的到期日分組欄位——
    # `expiry_top10`（各期前十名，含 Heatmap 矩陣）／`expiry_ranked`
    # （該期全部有效候選，供 `all_candidates` 歷史五欄位序列化）。
    # MVP 範圍當初只做 Spread（附錄A13）留下的空白，這裡照 `_spread_
    # result()` 既有寫法補齊，不引入新的分組邏輯。
    #
    # ⚠ 刻意的一處不對稱（`/code-review` Standards 軸抓到、值得記錄）：
    # `_spread_view()` 吃的是**本期**組內大小＋本期索引
    # （`len(by_expiry[exp])`／`enumerate()`），因為 Spread 的
    # `build_spread_reasons()` 文字明講「合格 N 組中第 idx+1」；這裡
    # 仍傳**全域** `n_qualified`（跟 `candidates`／`expiry_best` 用的
    # 是同一個既有呼叫慣例），因為 `_single_leg_view` 的 `n_qualified`
    # 只餵 `build_reasons()` 拿去跟全域 `max_ret` 比較，不像 Spread 那樣
    # 把組內大小寫進文字——單腿路徑沒有「本期組內大小」這個概念要傳。
    expiry_top10 = tuple(
        (exp, tuple(_single_leg_view(
            v, classify(v.classification_delta, p.delta_bands), ranked,
            snap.spot, n_qualified, today, p, violations, resilience_cache)
            for v in by_expiry[exp][:10]))
        for exp in sorted(by_expiry))
    expiry_ranked = tuple((exp, tuple(by_expiry[exp]))
                          for exp in sorted(by_expiry))

    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=ranked, ranked_spreads=None, n_qualified=n_qualified,
        filter_report=freport, pair_report=None, report_text=text, message="",
        expiry_best=expiry_best, expiry_counts=expiry_counts,
        expiry_top10=expiry_top10, expiry_ranked=expiry_ranked,
        quality_flags=quality_flags)


def _spread_result(p: AnalysisParams, snap: ChainSnapshot,
                   today: date) -> StrategyResult:
    qualified, freport = apply_filters(snap.contracts, p)
    pairs, pair_report = generate_spread_pairs(qualified, p)
    if not pairs:
        return StrategyResult(
            strategy=p.strategy, status="empty", candidates=(),
            ranked_bands=None, ranked_spreads=None, n_qualified=0,
            filter_report=freport, pair_report=pair_report,
            report_text=render_spreads(snap, p, freport, pair_report, [], 0,
                                       today),
            message="目前沒有符合流動性與報價條件的合約。")
    # FB5-03（#64）：同一批 qualified 腿的無套利一致性只算一次，兩隻腿
    # 各自查表——跟單腿路徑同一個函式、同一個口徑。
    violations = monotonicity_violations(qualified)
    quality_flags = quality_flag_counts(qualified, violations, p)
    spreads = [evaluate_spread(l, s, snap.spot, today, p) for l, s in pairs]
    # T05（#226，Initial V2 spec #217）：B 層——導出層數學安全網，接在
    # 既有計算路徑之後、排名之前，獨立於 A 層（`generate_spread_pairs()`
    # 既有的配對健全性檢查）成立。單位是「配對」，記在 `pair_report`
    # 而非 `freport`（後者是腿級單位，混在一起會讓同一份報告裡出現
    # 兩種不同單位的數字）。
    spreads, b_stage = validate_derived_values(
        spreads, natural_cost, spread_baseline_return,
        identity_fn=lambda v: f"{v.long_leg.contract_symbol}/{v.short_leg.contract_symbol}")
    pair_report = dataclasses.replace(
        pair_report, passed=len(spreads), b_layer_removed=b_stage.removed,
        b_layer_removed_examples=b_stage.removed_examples)
    ranked = rank_spreads(spreads, p)
    # T09（#191）：韌性／完成度指標只算一次，文字報告與 View 兩條路徑
    # 共用同一個快取——見 `_single_leg_result` 同一段註解，`spreads` 裡
    # 的物件被 `ranked`／`all_ranked`／`by_expiry` 全數沿用，不複製。
    resilience_cache: dict[int, ResilienceMetrics] = {}
    text = render_spreads(snap, p, freport, pair_report, ranked,
                          n_pairs=pair_report.passed, today=today,
                          violations=violations, quality_flags=quality_flags,
                          resilience_cache=resilience_cache)
    candidates = []
    for i, sv in enumerate(ranked[:3]):
        candidates.append(_spread_view(sv, i, pair_report.passed, snap.spot,
                                       today, p, snap, violations,
                                       resilience_cache))

    # v4 spec §3.2: per-expiry best over ALL qualified spreads (not just the
    # top-3 in `candidates`), for expiry grouping. T9（#23）：同一輪順便把
    # 每個到期日各自的完整排序分組收集起來（`by_expiry`）——分組後各自的
    # 相對順序與獨立對該組排序等價（全域鍵不依賴其他組），因此不必為
    # `expiry_top10`/`expiry_ranked` 另跑一次排序。
    all_ranked = sorted(spreads, key=lambda s: (-spread_baseline_return(s),
                                                *_spread_tie_key(s)))
    counts: dict[str, int] = {}
    best_by_expiry: dict[str, tuple[int, SpreadValuation]] = {}
    by_expiry: dict[str, list[SpreadValuation]] = {}
    for idx, sv in enumerate(all_ranked):
        exp = sv.long_leg.expiry
        counts[exp] = counts.get(exp, 0) + 1
        if exp not in best_by_expiry:
            best_by_expiry[exp] = (idx, sv)
        by_expiry.setdefault(exp, []).append(sv)
    expiry_best = tuple(
        _spread_view(best_by_expiry[exp][1], best_by_expiry[exp][0],
                     pair_report.passed, snap.spot, today, p, snap, violations,
                     resilience_cache)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))
    # 各到期日自己的前十名（Heatmap 矩陣只隨這至多 5×10 檔入快照，附錄A10.3）；
    # idx/組內大小都是「本期」的，不是全域——這是各期自己的排名，不是全域
    # 前十名的節錄。
    expiry_top10 = tuple(
        (exp, tuple(_spread_view(sv, i, len(by_expiry[exp]), snap.spot,
                                 today, p, snap, violations, resilience_cache)
                    for i, sv in enumerate(by_expiry[exp][:10])))
        for exp in sorted(by_expiry))
    expiry_ranked = tuple((exp, tuple(by_expiry[exp]))
                          for exp in sorted(by_expiry))

    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=None, ranked_spreads=tuple(ranked),
        n_qualified=pair_report.passed, filter_report=freport,
        pair_report=pair_report, report_text=text, message="",
        expiry_best=expiry_best, expiry_counts=expiry_counts,
        expiry_top10=expiry_top10, expiry_ranked=expiry_ranked,
        quality_flags=quality_flags)


def _butterfly_result(p: AnalysisParams, snap: ChainSnapshot,
                      today: date) -> StrategyResult:
    """T15（#230，Initial V2 spec #217）：`_spread_result()` 的三腿版本
    ——同一套結構（A 層→B 層→排名→逐到期日分組），只是配對函式換成
    `generate_butterfly_triples()`、估值換成 `evaluate_butterfly()`。"""
    qualified, freport = apply_filters(snap.contracts, p)
    triples, pair_report = generate_butterfly_triples(qualified, p)
    if not triples:
        return StrategyResult(
            strategy=p.strategy, status="empty", candidates=(),
            ranked_bands=None, ranked_spreads=None, n_qualified=0,
            filter_report=freport, pair_report=pair_report,
            report_text=render_butterflies(snap, p, freport, pair_report, [], 0,
                                           today),
            message="目前沒有符合流動性與報價條件的合約。")
    violations = monotonicity_violations(qualified)
    quality_flags = quality_flag_counts(qualified, violations, p)
    butterflies = [evaluate_butterfly(lo, mid, hi, snap.spot, today, p)
                  for lo, mid, hi in triples]
    # T05（#226）：B 層——導出層數學安全網，這裡額外傳 `max_loss_fn`
    # （#213 Addendum：defined-risk 候選的 max_loss 必須 > 0），既有
    # 單腿／Spread 兩個呼叫端不傳這個參數，行為不受影響。
    butterflies, b_stage = validate_derived_values(
        butterflies, natural_cost, butterfly_baseline_return,
        identity_fn=lambda v: (f"{v.low_leg.contract_symbol}/"
                               f"{v.mid_leg.contract_symbol}/"
                               f"{v.high_leg.contract_symbol}"),
        max_loss_fn=lambda v: v.max_loss)
    pair_report = dataclasses.replace(
        pair_report, passed=len(butterflies), b_layer_removed=b_stage.removed,
        b_layer_removed_examples=b_stage.removed_examples)
    ranked = rank_butterflies(butterflies, p)
    resilience_cache: dict[int, ResilienceMetrics] = {}
    text = render_butterflies(snap, p, freport, pair_report, ranked,
                              n_triples=pair_report.passed, today=today,
                              violations=violations, quality_flags=quality_flags,
                              resilience_cache=resilience_cache)
    candidates = []
    for i, bv in enumerate(ranked[:3]):
        candidates.append(_butterfly_view(bv, i, pair_report.passed, snap.spot,
                                          today, p, violations, resilience_cache))

    all_ranked = sorted(butterflies, key=lambda b: (-butterfly_baseline_return(b),
                                                    *_butterfly_tie_key(b)))
    counts: dict[str, int] = {}
    best_by_expiry: dict[str, tuple[int, ButterflyValuation]] = {}
    by_expiry: dict[str, list[ButterflyValuation]] = {}
    for idx, bv in enumerate(all_ranked):
        exp = bv.low_leg.expiry
        counts[exp] = counts.get(exp, 0) + 1
        if exp not in best_by_expiry:
            best_by_expiry[exp] = (idx, bv)
        by_expiry.setdefault(exp, []).append(bv)
    expiry_best = tuple(
        _butterfly_view(best_by_expiry[exp][1], best_by_expiry[exp][0],
                        pair_report.passed, snap.spot, today, p, violations,
                        resilience_cache)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))
    expiry_top10 = tuple(
        (exp, tuple(_butterfly_view(bv, i, len(by_expiry[exp]), snap.spot,
                                    today, p, violations, resilience_cache)
                    for i, bv in enumerate(by_expiry[exp][:10])))
        for exp in sorted(by_expiry))
    expiry_ranked = tuple((exp, tuple(by_expiry[exp]))
                          for exp in sorted(by_expiry))

    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=None, ranked_spreads=None,
        ranked_butterflies=tuple(ranked),
        n_qualified=pair_report.passed, filter_report=freport,
        pair_report=pair_report, report_text=text, message="",
        expiry_best=expiry_best, expiry_counts=expiry_counts,
        expiry_top10=expiry_top10, expiry_ranked=expiry_ranked,
        quality_flags=quality_flags)


def _comparison(results: tuple[StrategyResult, ...]) -> tuple[ComparisonRow, ...]:
    rows = []
    for res in results:
        if res.status != "ok" or not res.candidates:
            continue
        if res.strategy in BUTTERFLY_STRATEGIES:
            bv = res.ranked_butterflies[0]
            # `ComparisonRow.breakeven` 是單一 scalar 欄位（跨 family 比較表
            # 的既有形狀），但 Butterfly 到期時連峰值都賺不到時
            # `breakeven_points` 是空的（見 `butterfly_breakeven_and_
            # profit_region()`）——這裡沒有真正的損益兩平點可填。
            # `bv.low_leg.strike` 不是損益兩平點，只是這個既有 scalar
            # 欄位在「沒有損益兩平點」情境下的佔位值（比較表本身仍要顯示
            # 一個數字），不得誤讀成任何財務意義。
            breakeven = (bv.breakeven_points[0] if bv.breakeven_points
                        else bv.low_leg.strike)
            rows.append(ComparisonRow(
                strategy=res.strategy,
                label=(f"買 {bv.low_leg.strike:g} / 賣 2×{bv.mid_leg.strike:g} / "
                      f"買 {bv.high_leg.strike:g}"),
                expiry=bv.low_leg.expiry, cost=bv.net_worst,
                baseline_return=butterfly_baseline_return(bv),
                breakeven=breakeven, max_profit=bv.max_profit))
        elif res.strategy in SPREAD_STRATEGIES:
            sv = res.ranked_spreads[0]
            rows.append(ComparisonRow(
                strategy=res.strategy,
                label=f"買 {sv.long_leg.strike:g} / 賣 {sv.short_leg.strike:g}",
                expiry=sv.long_leg.expiry, cost=sv.net_worst,
                baseline_return=spread_baseline_return(sv),
                breakeven=sv.breakeven, max_profit=sv.max_profit))
        else:
            firsts = [lst[0] for lst in res.ranked_bands.values() if lst]
            v = sorted(firsts,
                       key=lambda x: (-baseline_return(x), *_tie_break_key(x)))[0]
            c = v.contract
            max_profit = None if res.strategy == "long-call" else c.strike - c.ask
            rows.append(ComparisonRow(
                strategy=res.strategy, label=f"K={c.strike:g}",
                expiry=c.expiry, cost=c.ask,
                baseline_return=baseline_return(v),
                breakeven=v.breakeven, max_profit=max_profit))
    return tuple(rows)


def _validate_request(request: AnalysisRequest) -> None:
    """Spec §2.2 step 0: reject before ANY fetch/load side effect."""
    if not request.strategies:
        raise ParamError("至少需要一種策略")
    invalid = [s for s in request.strategies if s not in STRATEGIES]
    if invalid:
        raise ParamError(f"未知策略: {', '.join(invalid)}")


def _scoped_to_selected_expiries(snap: ChainSnapshot, anchor: date,
                                 today: date
                                 ) -> tuple[ChainSnapshot, str | None]:
    """把快照收斂到六點規則選中的至多五檔到期日——窮舉只發生在這個範圍內。
    同時交回 baseline（T10／附錄A8.5：詳細頁預設選中的到期日），供
    `_analyze` 往下傳遞到 `AnalysisResult`——不在這裡之外重算一次。

    候選到期日必須晚於資料日：已到期／當日到期的合約 T <= 0，Greeks 無定義，
    根本不是可分析的標的。這是資料有效性前提，與「到期日 >= 目標日」那條被移除
    的目標導向下限無關——錨點前方、早於目標月的到期日一律照常入選。

    附錄 A12 第 2 點：鏈上零個到期日但抓取本身未拋例外時，不得逕自判為刷新
    失敗——比照零合格候選（A10.2）處理，回傳零合約快照，讓下游每個策略走
    既有的空結果分支（綠燈＋「—」）。`select_expiries` 這個純函式本身在被
    直接餵入空清單時仍然拋錯，這裡只是不讓服務層把「沒有到期日可選」誤讀成
    產品異常；此時 baseline 也無從定義，回傳 None。
    """
    tradable = {c.expiry for c in snap.contracts
                if date.fromisoformat(c.expiry) > today}
    if not tradable:
        return dataclasses.replace(snap, contracts=()), None
    selection = select_expiries(tradable, anchor)
    selected = set(selection.expiries)
    scoped = dataclasses.replace(
        snap, contracts=tuple(c for c in snap.contracts
                              if c.expiry in selected))
    return scoped, selection.baseline


def _resolve_rates(p: AnalysisParams, snap: ChainSnapshot, today: date,
                   loader: RateCurveLoader | None) -> AnalysisParams:
    """T12（附錄 A14.1）：每個入選到期日以「分析日→到期日」年期取期限對齊利率。

    `--rate` 明示（rate_explicit）→ 原樣返回，行為與現行完全一致。
    無 loader（離線重放）→ 估值同樣用常數，但報告參數行必須標示——只有
    明示 --rate 被授權沿用現行寫法（issue #26），其餘固定值一律說明原因。
    曲線不可得 → 保持常數 `p.rate`，僅設 `rate_note` 供報告參數行標示。
    解出的表以到期日為鍵：同一腿在 Heatmap 全格共用一個 r。

    RC1（#87）：`rate_curve_used`/`rate_curve_date`/`rate_curve_stale`
    三欄只描述「這次是否真的取得一條 `RateCurve`」，獨立於 `rate_by_
    expiry` 是否非空——後者在鏈上零合約時即使曲線成功也會是空表，兩者
    脫鉤，呈現層才不會把「曲線成功但鏈上零合約」誤判成 fallback。
    """
    if p.rate_explicit:
        return p
    if loader is None:
        return dataclasses.replace(p, rate_note="離線重放，未啟用利率曲線")
    curve, note = loader(today)
    if curve is None:
        return dataclasses.replace(p, rate_note=note, rate_curve_used=False)
    pairs = tuple(
        (e, rate_for_tenor(
            curve, (date.fromisoformat(e) - today).days / DAYS_PER_YEAR))
        for e in sorted({c.expiry for c in snap.contracts}))
    return dataclasses.replace(p, rate_by_expiry=pairs, rate_note=note,
                               rate_curve_used=True,
                               rate_curve_date=curve.curve_date,
                               rate_curve_stale=curve.stale)


def _resolve_q(p: AnalysisParams, snap: ChainSnapshot, today: date,
               loader: DividendLoader | None) -> AnalysisParams:
    """#123（spec #117 §2）：股利殖利率 q，鏡射 `_resolve_rates` 的三層
    fallback 結構，差異只在 q 是**單一數值、per-symbol**（不是逐到期日
    查表）。

    無 loader（離線重放）→ `q_by_symbol` 維持 `None`，走既有行為
    （`valuation.calibrate_leg` 的第 4 層：q=0＋vendor IV，不是「q=0＋
    價格錨定」——後者對很多真實 LEAPS 在數學上無解）。

    loader 回 `None`（fetch 失敗且無可用快取）→ 同樣維持 `None`，只設
    `q_note` 供報告說明原因——這正是 AC 的 fallback 第 4 層。

    loader 回一份 `DividendHistory`（不論 fresh 或 stale）→ 用**這次
    快照的 spot**現算 q（`compute_q`，研究 §7.5：不快取算好的比例）。
    `distributions` 為空（確定無配息）→ `compute_q` 自然回 0.0，狀態
    仍是 `q_stale=history.stale`（通常是 fresh）——這是正確答案，不是
    降級（研究 §8 第 2 層）。

    `compute_q` 對 `spot <= 0` 會拋 `ParamError`（未特別接住，讓它往上
    傳）——與 `_resolve_rates` 不同，那裡的輸入來源（Treasury 曲線）
    不可能產生會拋例外的壞資料。這裡故意不接住：`api_app/main.py` 既有
    的 `except ParamError` 分支會把它映射成 400 "params"，雖然語意上
    更接近「快照壞了」而非「使用者輸入錯」，但**真實市場報價的 spot
    不可能是零或負值**，這是防禦性case、不是預期會發生的路徑，沿用
    既有的 `ParamError` → 400 收斂已經是「不會讓分析炸成 500」的正確
    行為，值得一個新的失敗分層前應先觀察是否真的發生過。
    """
    if loader is None:
        return p
    history, note = loader(snap.symbol, today)
    if history is None:
        return dataclasses.replace(p, q_note=note)
    q = compute_q(history, snap.spot, today)
    return dataclasses.replace(p, q_by_symbol=q, q_source=history.source,
                               q_as_of=history.as_of, q_stale=history.stale,
                               q_note=note)


def _analyze(request: AnalysisRequest, snap: ChainSnapshot,
             snapshot_path: str, progress: Progress | None,
             rate_curve_loader: RateCurveLoader | None = None,
             dividend_loader: DividendLoader | None = None) -> AnalysisResult:
    today = snapshot_today(snap.fetched_at)
    base = request.base_params
    month = ensure_month_open(TargetMonth.from_key(base.target_month), today)
    anchor = calendar_anchor(month)
    _emit(progress, "正在依日曆錨點選取到期日……")
    snap, baseline_expiry = _scoped_to_selected_expiries(snap, anchor, today)
    _emit(progress, "正在解析無風險利率……")
    base = _resolve_rates(base, snap, today, rate_curve_loader)
    _emit(progress, "正在解析股利殖利率……")
    base = _resolve_q(base, snap, today, dividend_loader)
    # 解出的利率／q 是估值輸入的一部分：回寫 request，讓結果持久化與
    # 呼叫端可見。
    request = dataclasses.replace(request, base_params=base)
    results = []
    _emit(progress, "正在過濾合約……")
    # T08（#225，Initial V2 spec #217）：Direction 是衍生值，分析當下
    # 算一次、不落盤、不進事件——由 `target_price` 相對 `spot` 推導，
    # 三態、無容忍帶。取代舊版逐 subtype 各自呼叫 `is_bullish()` 再湊
    # 一次 bull/bear 互斥判斷的寫法。
    direction = derive_direction(base.target_price, snap.spot)
    for s in request.strategies:
        p = dataclasses.replace(base, strategy=s)
        mismatch = not subtype_eligible(s, direction)
        if mismatch and not base.force:
            results.append(StrategyResult(
                strategy=s, status="skipped_direction", candidates=(),
                ranked_bands=None, ranked_spreads=None, n_qualified=0,
                filter_report=None, pair_report=None, report_text=None,
                message=_skip_message(direction)))
            continue
        if s in SPREAD_STRATEGIES:
            _emit(progress, f"正在窮舉 {STRATEGY_LABELS[s]}……")
            results.append(_spread_result(p, snap, today))
        elif s in BUTTERFLY_STRATEGIES:
            _emit(progress, f"正在窮舉 {STRATEGY_LABELS[s]}……")
            results.append(_butterfly_result(p, snap, today))
        else:
            _emit(progress, f"正在比較 {STRATEGY_LABELS[s]}……")
            results.append(_single_leg_result(p, snap, today))
    _emit(progress, "正在建立 Heatmap……")
    comparison = _comparison(tuple(results))
    order = list(request.strategies)
    best = None
    if comparison:
        best = max(comparison,
                   key=lambda r: (r.baseline_return, -order.index(r.strategy))
                   ).strategy
    expiry_groups, hidden_expiries, default_selection = _build_groups(
        tuple(results), request.strategies, anchor)
    baseline_selection = _baseline_selection(expiry_groups, baseline_expiry)
    return AnalysisResult(
        request=request,
        meta=SnapshotMeta(symbol=snap.symbol, spot=snap.spot,
                          fetched_at=snap.fetched_at, source=snap.source,
                          snapshot_path=snapshot_path,
                          target_move=(base.target_price - snap.spot) / snap.spot),
        snapshot=snap, today=today, results=tuple(results),
        comparison=comparison, best_strategy=best,
        expiry_groups=expiry_groups, hidden_expiries=hidden_expiries,
        default_selection=default_selection, baseline_expiry=baseline_expiry,
        baseline_selection=baseline_selection)


def fetch_chain(symbol: str) -> ChainSnapshot:
    """抓取選擇權鏈，**不落盤**。

    FB3-01（#44）：Cboe 延遲報價為主源（盤外凍結收盤 bid/ask 不歸零、
    單一 GET 回全鏈），失敗自動退回 yfinance；快照 `source` 欄位如實
    記錄實際用了哪個源。lazy import：離線路徑永不碰網路模組。

    V1（#48）：自 `fetch_and_save` 抽出——serverless 檔案系統唯讀，
    API 層需要「只抓不存」的入口，降級鏈本身則不重複實作。

    serverless 部署刻意不裝 yfinance（帶 pandas/numpy，體積不划算）：
    `data/yf.py` 模組本身只依賴 stdlib，真正的 `import yfinance` 在它的
    `fetch_chain` 內部、且已被收斂成 FetchError，因此「備援不存在」在
    這裡自然表現為 FetchError，不需要額外防護。"""
    from .data import cboe

    try:
        return cboe.fetch_chain(symbol)
    except FetchError:
        from .data import yf

        return yf.fetch_chain(symbol)


def fetch_and_save(symbol: str) -> tuple[ChainSnapshot, str]:
    """v5 spec §4: 抓取＋落盤 snapshot（run 與 workspace.analyze_group 共用）。"""
    snap = fetch_chain(symbol)
    out = Path("snapshots") / f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.json"
    out.parent.mkdir(exist_ok=True)
    save_snapshot(snap, out)
    return snap, str(out)


def run(request: AnalysisRequest, progress: Progress | None = None) -> AnalysisResult:
    _validate_request(request)
    _emit(progress, f"正在抓取 {request.symbol} 市場資料……")
    snap, out = fetch_and_save(request.symbol)
    return _analyze(request, snap, out, progress,
                    rate_curve_loader=default_rate_curve_loader,
                    dividend_loader=default_dividend_loader)


def run_with_snapshot(request: AnalysisRequest, snap: ChainSnapshot,
                      snapshot_ref: str = "(in-memory)",
                      progress: Progress | None = None, *,
                      rate_curve_loader: RateCurveLoader | None = None,
                      dividend_loader: DividendLoader | None = None
                      ) -> AnalysisResult:
    """V1（#48）：分析一份**已在記憶體中**的快照，不讀寫檔案系統。

    serverless（Vercel）檔案系統唯讀，API 層既不能落盤也不該從磁碟
    重載；`snapshot_ref` 只是記在結果 meta 裡的來源標示字串。注意舊
    Streamlit 版的「原始資料」區塊會拿 `snapshot_ref.path` 去
    `load_snapshot()`——傳入非路徑字串時該區塊會顯示「檔案已不在」的
    既有警告（安全降級，不會拋錯）。新前端的原始資料區（V8／#56）
    改由 API 提供，不再從路徑重讀。

    與 `run_offline` 同樣預設不接利率／股利管線（決定性）。"""
    _validate_request(request)
    return _analyze(request, snap, snapshot_ref, progress,
                    rate_curve_loader=rate_curve_loader,
                    dividend_loader=dividend_loader)


def run_offline(request: AnalysisRequest, snapshot_path: str,
                progress: Progress | None = None, *,
                rate_curve_loader: RateCurveLoader | None = None,
                dividend_loader: DividendLoader | None = None
                ) -> AnalysisResult:
    """離線重放預設不接利率／股利管線（決定性、零網路）；networked
    呼叫端（如 workspace 群組刷新，自己剛抓完 chain）可明示傳 loader
    啟用。"""
    _validate_request(request)
    snap = load_snapshot(snapshot_path)
    return _analyze(request, snap, str(snapshot_path), progress,
                    rate_curve_loader=rate_curve_loader,
                    dividend_loader=dividend_loader)
