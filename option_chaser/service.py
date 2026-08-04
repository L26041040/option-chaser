"""Application service — single shared entry for CLI and GUI (v3 spec §2.2)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .data.snapshot import find_contract, load_snapshot, save_snapshot, snapshot_today
from .filters import apply_filters, generate_spread_pairs, is_spread_wide
from .matrix import date_axis, matrix_grid, price_axis
from .models import (AnalysisParams, ChainSnapshot, FetchError, FilterReport,
                     PairReport, ParamError, SPREAD_STRATEGIES, STRATEGIES,
                     is_bullish)
from .ranking import (BAND_ORDER, _spread_tie_key, _tie_break_key,
                      baseline_return, build_reasons, build_spread_reasons,
                      classify, rank, rank_spreads, return_at_price,
                      spread_baseline_return)
from .report import STRATEGY_LABELS, render, render_filter_only, render_spreads
from .scenarios import (ScenarioVector, completion_curve, completion_scan,
                        friction, natural_cost, scenario_vector, _grid_price,
                        _value_fn)
from .timeframe import (TargetMonth, calendar_anchor, ensure_month_open,
                        select_expiries)
from .ratecurve import RateCurve, rate_for_tenor
from .valuation import (ContractValuation, DAYS_PER_YEAR, SpreadValuation,
                        catchup_price, evaluate_contract, evaluate_spread,
                        leg_greeks, leg_rate, scenario_leg_value,
                        spread_scenario_value)

Progress = Callable[[str], None]

# T12（附錄 A14.1）：利率曲線 loader = (today) -> (RateCurve | None, 報告註記)。
# 只有網路路徑（run／workspace 群組刷新）預設接真管線；run_offline 預設 None，
# 快照重放與測試因此決定性且零網路。
RateCurveLoader = Callable[[date], tuple[RateCurve | None, str]]


def default_rate_curve_loader(today: date):
    from .data.treasury import load_rate_curve  # lazy: offline paths never觸網
    return load_rate_curve(today)


@dataclass(frozen=True)
class AnalysisRequest:
    symbol: str
    base_params: AnalysisParams
    strategies: tuple[str, ...]


@dataclass(frozen=True)
class MatrixView:
    prices: tuple[tuple[float, str], ...]
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
    friction: float
    friction_amount: float    # natural_cost(val) − mid 成本（spec §2.3, $/股）
    buffer_days: int
    quote_warning: bool
    theta_day_rate: float      # |淨Θ| / Mid 成本
    vega_per_pt: float         # 淨Vega(每1 IV百分點) / Mid 成本
    decay_30d_return: float    # S=spot、IV不變、today+30(或到期)估值報酬
    # D1（#14）：Long Call 追平價格 S*=K+C×(1+R)——只對 Spread 有意義
    # （買腿履約價 K 的同履約價 Call 若報價缺失也是 None）；單腳恆為 None。
    catchup_price: float | None = None
    # V7（#55）。預設空 tuple：沒設兩端、也沒走 `_v4_fields` 的呼叫端
    # （若有）都不會壞。
    price_ladder: tuple[PricePoint, ...] = ()


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


def _skip_message(strategy: str) -> str:
    if is_bullish(strategy):
        return ("目標價低於目前股價，因此未執行 Long Call 與 Bull Call Spread。"
                "可改選 Long Put 或 Bear Put Spread。")
    return ("目標價高於目前股價，因此未執行 Long Put 與 Bear Put Spread。"
            "可改選 Long Call 或 Bull Call Spread。")


def _matrix_view(value_fn, cost: float, spot: float, p: AnalysisParams,
                 today: date, expiry_iso: str) -> MatrixView:
    prices = price_axis(spot, p.target_price, is_bullish(p.strategy))
    dates = date_axis(today, date.fromisoformat(expiry_iso))
    cells = matrix_grid(value_fn, cost, prices, dates)
    return MatrixView(prices=tuple(prices),
                      dates=tuple((d.isoformat(), lbl) for d, lbl in dates),
                      cells=cells)


def _mid_cost(val: ContractValuation | SpreadValuation) -> float:
    return val.net_mid if isinstance(val, SpreadValuation) else val.mid


def _net_theta(val: ContractValuation | SpreadValuation, spot: float,
              today: date, p: AnalysisParams) -> float:
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        t_now = (date.fromisoformat(lng.expiry) - today).days / 365.0
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now,
                         leg_rate(p, lng.expiry), lng.implied_volatility)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now,
                         leg_rate(p, sht.expiry), sht.implied_volatility)
        return g_l.theta_per_day - g_s.theta_per_day
    return val.theta_per_day


def _net_vega(val: ContractValuation | SpreadValuation, spot: float,
             today: date, p: AnalysisParams) -> float:
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        t_now = (date.fromisoformat(lng.expiry) - today).days / 365.0
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now,
                         leg_rate(p, lng.expiry), lng.implied_volatility)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now,
                         leg_rate(p, sht.expiry), sht.implied_volatility)
        return g_l.vega_per_pct - g_s.vega_per_pct
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


def _v4_fields(val: ContractValuation | SpreadValuation, spot: float,
              today: date, p: AnalysisParams) -> dict:
    sv = scenario_vector(val, spot, today, p)
    k, be = completion_scan(val, spot, today, p)
    fr = friction(val)
    if isinstance(val, SpreadValuation):
        expiry = val.long_leg.expiry
        zero_vol = val.long_leg.volume == 0 or val.short_leg.volume == 0
        # FB5-02（#63）：任一腿的買賣價差超過舊硬門檻公式就標——兩腿各自
        # 的報價品質，不是合成後的淨值，合成淨值那個訊號已經有 fr>0.25。
        wide_spread = (is_spread_wide(val.long_leg.bid, val.long_leg.ask, p)
                      or is_spread_wide(val.short_leg.bid, val.short_leg.ask, p))
    else:
        expiry = val.contract.expiry
        zero_vol = val.contract.volume == 0
        wide_spread = is_spread_wide(val.contract.bid, val.contract.ask, p)
    mid_cost = _mid_cost(val)
    curve = completion_curve(val, spot, today, p)
    return dict(
        scenario=sv,
        completion_curve=curve,
        completion_prices=tuple(_grid_price(spot, p.target_price, k)
                                for k, _ in curve),
        completion_threshold=k, breakeven_at_target=be,
        retention=1.0 + dict(sv.entries)["S1"], friction=fr,
        friction_amount=natural_cost(val) - mid_cost,
        buffer_days=(date.fromisoformat(expiry) - p.anchor).days,
        # FB5-02（#63）：沿用既有的 `quote_warning` 機制，不新造一套——
        # 買賣價差過寬只是這個既有布林旗標的第三個觸發條件。
        quote_warning=zero_vol or wide_spread or fr > 0.25,
        theta_day_rate=abs(_net_theta(val, spot, today, p)) / mid_cost,
        vega_per_pt=_net_vega(val, spot, today, p) / mid_cost,
        decay_30d_return=_decay_30d(val, spot, today, p),
        price_ladder=_price_ladder(val, p))


def _single_leg_view(v: ContractValuation, band: str,
                     ranked: dict[str, list[ContractValuation]], spot: float,
                     n_qualified: int, today: date,
                     p: AnalysisParams) -> CandidateView:
    pros, cons = build_reasons(v, band, ranked, spot, n_qualified, p)
    mv = _matrix_view(
        lambda S, d, c=v.contract: scenario_leg_value(c, S, d, p),
        v.contract.ask, spot, p, today, v.contract.expiry)
    return CandidateView(
        valuation=v, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=v.baseline_value - v.contract.ask,
        baseline_return=baseline_return(v),
        **_v4_fields(v, spot, today, p))


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


def _spread_view(sv: SpreadValuation, idx: int, n_pairs: int, spot: float,
                 today: date, p: AnalysisParams, snap: ChainSnapshot) -> CandidateView:
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    mv = _matrix_view(
        lambda S, d, lng=sv.long_leg, sht=sv.short_leg:
            spread_scenario_value(lng, sht, S, d, p),
        sv.net_worst, spot, p, today, sv.long_leg.expiry)
    return CandidateView(
        valuation=sv, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=sv.baseline_value - sv.net_worst,
        baseline_return=spread_baseline_return(sv),
        catchup_price=_spread_catchup_price(sv, snap),
        **_v4_fields(sv, spot, today, p))


def valuation_key(v: ContractValuation | SpreadValuation) -> str:
    """需求八：Spread／單腳身分鍵，直接吃估值物件——`candidate_key()` 的
    CandidateView 包裝只是它的一層外皮。T9 序列化全部有效候選的歷史五欄位
    時不需要（也不划算）先建 CandidateView，所以底層鍵在這裡獨立出來重用，
    公開給 `store.py` 跨模組呼叫（非本模組私用，因此不加底線）。"""
    if isinstance(v, SpreadValuation):
        return (f"{_strategy_of(v)}|{v.long_leg.strike:g}|"
                f"{v.short_leg.strike:g}|{v.long_leg.expiry}")
    return f"{_strategy_of(v)}|{v.contract.strike:g}|{v.contract.expiry}"


def candidate_key(cv: CandidateView) -> str:
    return valuation_key(cv.valuation)


def _strategy_of(v) -> str:
    if isinstance(v, SpreadValuation):
        return ("bull-call-spread" if v.long_leg.option_type == "call"
                else "bear-put-spread")
    return "long-call" if v.contract.option_type == "call" else "long-put"


def _expiry_of(cv: CandidateView) -> str:
    v = cv.valuation
    return v.long_leg.expiry if isinstance(v, SpreadValuation) else v.contract.expiry


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
    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    ranked = rank(vals, p)
    text = render(snap, p, freport, ranked, n_qualified=len(qualified),
                  today=today)
    candidates = []
    for band in BAND_ORDER:
        if not ranked[band]:
            continue
        v = ranked[band][0]
        candidates.append(_single_leg_view(v, band, ranked, snap.spot,
                                           len(qualified), today, p))

    # v4 spec §3.2: per-expiry best over ALL qualified (not just top-3 bands),
    # for expiry grouping. Cost control: CandidateView only built for winners.
    vals_sorted = sorted(vals, key=lambda v: (-baseline_return(v),
                                              *_tie_break_key(v)))
    counts: dict[str, int] = {}
    best_by_expiry: dict[str, ContractValuation] = {}
    for v in vals_sorted:
        exp = v.contract.expiry
        counts[exp] = counts.get(exp, 0) + 1
        best_by_expiry.setdefault(exp, v)
    expiry_best = tuple(
        _single_leg_view(best_by_expiry[exp],
                         classify(best_by_expiry[exp].delta, p.delta_bands),
                         ranked, snap.spot, len(qualified), today, p)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))

    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=ranked, ranked_spreads=None, n_qualified=len(qualified),
        filter_report=freport, pair_report=None, report_text=text, message="",
        expiry_best=expiry_best, expiry_counts=expiry_counts)


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
    spreads = [evaluate_spread(l, s, snap.spot, today, p) for l, s in pairs]
    ranked = rank_spreads(spreads, p)
    text = render_spreads(snap, p, freport, pair_report, ranked,
                          n_pairs=pair_report.passed, today=today)
    candidates = []
    for i, sv in enumerate(ranked[:3]):
        candidates.append(_spread_view(sv, i, pair_report.passed, snap.spot,
                                       today, p, snap))

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
                     pair_report.passed, snap.spot, today, p, snap)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))
    # 各到期日自己的前十名（Heatmap 矩陣只隨這至多 5×10 檔入快照，附錄A10.3）；
    # idx/組內大小都是「本期」的，不是全域——這是各期自己的排名，不是全域
    # 前十名的節錄。
    expiry_top10 = tuple(
        (exp, tuple(_spread_view(sv, i, len(by_expiry[exp]), snap.spot,
                                 today, p, snap)
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
        expiry_top10=expiry_top10, expiry_ranked=expiry_ranked)


def _comparison(results: tuple[StrategyResult, ...]) -> tuple[ComparisonRow, ...]:
    rows = []
    for res in results:
        if res.status != "ok" or not res.candidates:
            continue
        if res.strategy in SPREAD_STRATEGIES:
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
    """
    if p.rate_explicit:
        return p
    if loader is None:
        return dataclasses.replace(p, rate_note="離線重放，未啟用利率曲線")
    curve, note = loader(today)
    if curve is None:
        return dataclasses.replace(p, rate_note=note)
    pairs = tuple(
        (e, rate_for_tenor(
            curve, (date.fromisoformat(e) - today).days / DAYS_PER_YEAR))
        for e in sorted({c.expiry for c in snap.contracts}))
    return dataclasses.replace(p, rate_by_expiry=pairs, rate_note=note)


def _analyze(request: AnalysisRequest, snap: ChainSnapshot,
             snapshot_path: str, progress: Progress | None,
             rate_curve_loader: RateCurveLoader | None = None) -> AnalysisResult:
    today = snapshot_today(snap.fetched_at)
    base = request.base_params
    month = ensure_month_open(TargetMonth.from_key(base.target_month), today)
    anchor = calendar_anchor(month)
    _emit(progress, "正在依日曆錨點選取到期日……")
    snap, baseline_expiry = _scoped_to_selected_expiries(snap, anchor, today)
    _emit(progress, "正在解析無風險利率……")
    base = _resolve_rates(base, snap, today, rate_curve_loader)
    # 解出的利率是估值輸入的一部分：回寫 request，讓結果持久化與呼叫端可見。
    request = dataclasses.replace(request, base_params=base)
    results = []
    _emit(progress, "正在過濾合約……")
    for s in request.strategies:
        p = dataclasses.replace(base, strategy=s)
        bull = is_bullish(s)
        mismatch = ((bull and p.target_price <= snap.spot)
                    or ((not bull) and p.target_price >= snap.spot))
        if mismatch and not base.force:
            results.append(StrategyResult(
                strategy=s, status="skipped_direction", candidates=(),
                ranked_bands=None, ranked_spreads=None, n_qualified=0,
                filter_report=None, pair_report=None, report_text=None,
                message=_skip_message(s)))
            continue
        if s in SPREAD_STRATEGIES:
            _emit(progress, f"正在窮舉 {STRATEGY_LABELS[s]}……")
            results.append(_spread_result(p, snap, today))
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
                    rate_curve_loader=default_rate_curve_loader)


def run_with_snapshot(request: AnalysisRequest, snap: ChainSnapshot,
                      snapshot_ref: str = "(in-memory)",
                      progress: Progress | None = None, *,
                      rate_curve_loader: RateCurveLoader | None = None
                      ) -> AnalysisResult:
    """V1（#48）：分析一份**已在記憶體中**的快照，不讀寫檔案系統。

    serverless（Vercel）檔案系統唯讀，API 層既不能落盤也不該從磁碟
    重載；`snapshot_ref` 只是記在結果 meta 裡的來源標示字串。注意舊
    Streamlit 版的「原始資料」區塊會拿 `snapshot_ref.path` 去
    `load_snapshot()`——傳入非路徑字串時該區塊會顯示「檔案已不在」的
    既有警告（安全降級，不會拋錯）。新前端的原始資料區（V8／#56）
    改由 API 提供，不再從路徑重讀。

    與 `run_offline` 同樣預設不接利率管線（決定性）。"""
    _validate_request(request)
    return _analyze(request, snap, snapshot_ref, progress,
                    rate_curve_loader=rate_curve_loader)


def run_offline(request: AnalysisRequest, snapshot_path: str,
                progress: Progress | None = None, *,
                rate_curve_loader: RateCurveLoader | None = None
                ) -> AnalysisResult:
    """離線重放預設不接利率管線（決定性、零網路）；networked 呼叫端（如
    workspace 群組刷新，自己剛抓完 chain）可明示傳 loader 啟用曲線。"""
    _validate_request(request)
    snap = load_snapshot(snapshot_path)
    return _analyze(request, snap, str(snapshot_path), progress,
                    rate_curve_loader=rate_curve_loader)
