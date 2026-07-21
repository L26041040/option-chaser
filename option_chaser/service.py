"""Application service — single shared entry for CLI and GUI (v3 spec §2.2)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .data.snapshot import load_snapshot, save_snapshot, snapshot_today
from .filters import apply_filters, generate_spread_pairs
from .matrix import date_axis, matrix_grid, price_axis
from .models import (AnalysisParams, ChainSnapshot, FilterReport, PairReport,
                     ParamError, SPREAD_STRATEGIES, STRATEGIES, is_bullish)
from .ranking import (BAND_ORDER, _spread_tie_key, _tie_break_key,
                      baseline_return, build_reasons, build_spread_reasons,
                      classify, rank, rank_spreads, spread_baseline_return)
from .report import STRATEGY_LABELS, render, render_filter_only, render_spreads
from .scenarios import (ScenarioVector, completion_curve, completion_scan,
                        friction, natural_cost, scenario_vector, _grid_price,
                        _value_fn)
from .valuation import (ContractValuation, SpreadValuation, evaluate_contract,
                        evaluate_spread, leg_greeks, scenario_leg_value,
                        spread_scenario_value)

Progress = Callable[[str], None]


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
class CandidateView:
    valuation: ContractValuation | SpreadValuation
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    matrix: MatrixView
    baseline_pnl: float        # 估值 − 成本（Mid 口徑，每股）
    baseline_return: float     # ranking.baseline_return / spread_baseline_return
    natural_return: float      # (基準估值 − Natural成本)/Natural成本
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
    cost: float
    baseline_return: float
    natural_return: float
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
    dates = date_axis(today, date.fromisoformat(p.target_date),
                      date.fromisoformat(expiry_iso))
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
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now, p.rate,
                         lng.implied_volatility)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now, p.rate,
                         sht.implied_volatility)
        return g_l.theta_per_day - g_s.theta_per_day
    return val.theta_per_day


def _net_vega(val: ContractValuation | SpreadValuation, spot: float,
             today: date, p: AnalysisParams) -> float:
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        t_now = (date.fromisoformat(lng.expiry) - today).days / 365.0
        g_l = leg_greeks(lng.option_type, spot, lng.strike, t_now, p.rate,
                         lng.implied_volatility)
        g_s = leg_greeks(sht.option_type, spot, sht.strike, t_now, p.rate,
                         sht.implied_volatility)
        return g_l.vega_per_pct - g_s.vega_per_pct
    return val.vega_per_pct


def _decay_30d(val: ContractValuation | SpreadValuation, spot: float,
               today: date, p: AnalysisParams) -> float:
    fn, mid, _, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    d30 = min(today + timedelta(days=30), expiry)
    return (fn(spot, d30, p) - mid) / mid


def _v4_fields(val: ContractValuation | SpreadValuation, spot: float,
              today: date, p: AnalysisParams) -> dict:
    sv = scenario_vector(val, spot, today, p)
    k, be = completion_scan(val, spot, today, p)
    fr = friction(val)
    if isinstance(val, SpreadValuation):
        expiry = val.long_leg.expiry
        zero_vol = val.long_leg.volume == 0 or val.short_leg.volume == 0
    else:
        expiry = val.contract.expiry
        zero_vol = val.contract.volume == 0
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
        buffer_days=(date.fromisoformat(expiry)
                     - date.fromisoformat(p.target_date)).days,
        quote_warning=zero_vol or fr > 0.25,
        theta_day_rate=abs(_net_theta(val, spot, today, p)) / mid_cost,
        vega_per_pt=_net_vega(val, spot, today, p) / mid_cost,
        decay_30d_return=_decay_30d(val, spot, today, p))


def _single_leg_view(v: ContractValuation, band: str,
                     ranked: dict[str, list[ContractValuation]], spot: float,
                     n_qualified: int, today: date,
                     p: AnalysisParams) -> CandidateView:
    pros, cons = build_reasons(v, band, ranked, spot, n_qualified, p)
    mv = _matrix_view(
        lambda S, d, c=v.contract: scenario_leg_value(c, S, d, p),
        v.mid, spot, p, today, v.contract.expiry)
    return CandidateView(
        valuation=v, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=v.baseline_value - v.mid,
        baseline_return=baseline_return(v),
        natural_return=(v.baseline_value - v.contract.ask) / v.contract.ask,
        **_v4_fields(v, spot, today, p))


def _spread_view(sv: SpreadValuation, idx: int, n_pairs: int, spot: float,
                 today: date, p: AnalysisParams) -> CandidateView:
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    mv = _matrix_view(
        lambda S, d, lng=sv.long_leg, sht=sv.short_leg:
            spread_scenario_value(lng, sht, S, d, p),
        sv.net_mid, spot, p, today, sv.long_leg.expiry)
    return CandidateView(
        valuation=sv, pros=tuple(pros), cons=tuple(cons), matrix=mv,
        baseline_pnl=sv.baseline_value - sv.net_mid,
        baseline_return=spread_baseline_return(sv),
        natural_return=(sv.baseline_value - sv.net_worst) / sv.net_worst,
        **_v4_fields(sv, spot, today, p))


def candidate_key(cv: CandidateView) -> str:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        return (f"{_strategy_of(v)}|{v.long_leg.strike:g}|"
                f"{v.short_leg.strike:g}|{v.long_leg.expiry}")
    return f"{_strategy_of(v)}|{v.contract.strike:g}|{v.contract.expiry}"


def _strategy_of(v) -> str:
    if isinstance(v, SpreadValuation):
        return ("bull-call-spread" if v.long_leg.option_type == "call"
                else "bear-put-spread")
    return "long-call" if v.contract.option_type == "call" else "long-put"


def _expiry_of(cv: CandidateView) -> str:
    v = cv.valuation
    return v.long_leg.expiry if isinstance(v, SpreadValuation) else v.contract.expiry


def _sample_expiries(expiries: list[str], target_date: str
                     ) -> tuple[list[str], list[str]]:
    """Spec §3.2: <=4 keep all; else nearest-2 (>= target) + evenly spaced to 4."""
    exps = sorted(set(expiries))
    if len(exps) <= 4:
        return exps, []
    kept = exps[:2]                       # expiry >= target_date guaranteed by filters
    rest = exps[2:]
    need = 2
    idx = [round(i * (len(rest) - 1) / (need - 1)) for i in range(need)] \
        if need > 1 else [0]
    for i in sorted(set(idx)):
        kept.append(rest[i])
    kept = sorted(set(kept))
    hidden = [e for e in exps if e not in kept]
    return kept, hidden


def _build_groups(results: tuple[StrategyResult, ...],
                  strategies_order: tuple[str, ...], target_date: str
                  ) -> tuple[tuple[ExpiryGroup, ...], tuple[str, ...],
                            tuple[str, str] | None]:
    """v4 spec §3.2: assemble expiry groups, global badges, sampling + injection."""
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
        buffer_days = (date.fromisoformat(exp) - date.fromisoformat(target_date)).days
        return ExpiryGroup(expiry=exp, buffer_days=buffer_days, rows=rows,
                           hidden_count=hidden_count)

    expiries = sorted({_expiry_of(cv) for _, cv in all_pairs})
    kept, hidden = _sample_expiries(expiries, target_date)
    groups: dict[str, ExpiryGroup] = {exp: _make_group(exp) for exp in kept}
    hidden_list = list(hidden)

    def _ensure_visible(pair: tuple[str, CandidateView]) -> None:
        s, cv = pair
        exp = _expiry_of(cv)
        if exp in groups:
            rows = groups[exp].rows
            if any(r.strategy == s and r.candidate is cv for r in rows):
                return
            new_row = ExpiryGroupRow(strategy=s, candidate=cv, badges=_row_badges(s, cv))
            new_rows = tuple(sorted(rows + (new_row,),
                                    key=lambda r: -r.candidate.baseline_return))
            groups[exp] = dataclasses.replace(groups[exp], rows=new_rows)
        else:
            groups[exp] = _make_group(exp)
            if exp in hidden_list:
                hidden_list.remove(exp)

    for pair in (top_return_pair, top_resilience_pair, default_pair):
        _ensure_visible(pair)

    ordered_expiries = sorted(groups.keys())
    expiry_groups = tuple(groups[e] for e in ordered_expiries)
    hidden_expiries = tuple(sorted(hidden_list))
    default_selection = (_expiry_of(default_pair[1]), candidate_key(default_pair[1]))
    return expiry_groups, hidden_expiries, default_selection


def _single_leg_result(p: AnalysisParams, snap: ChainSnapshot,
                       today: date) -> StrategyResult:
    qualified, freport = apply_filters(snap.contracts, p, today)
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
    qualified, freport = apply_filters(snap.contracts, p, today)
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
                                       today, p))

    # v4 spec §3.2: per-expiry best over ALL qualified spreads (not just the
    # top-3 in `candidates`), for expiry grouping.
    all_ranked = sorted(spreads, key=lambda s: (-spread_baseline_return(s),
                                                *_spread_tie_key(s)))
    counts: dict[str, int] = {}
    best_by_expiry: dict[str, tuple[int, SpreadValuation]] = {}
    for idx, sv in enumerate(all_ranked):
        exp = sv.long_leg.expiry
        counts[exp] = counts.get(exp, 0) + 1
        if exp not in best_by_expiry:
            best_by_expiry[exp] = (idx, sv)
    expiry_best = tuple(
        _spread_view(best_by_expiry[exp][1], best_by_expiry[exp][0],
                     pair_report.passed, snap.spot, today, p)
        for exp in sorted(best_by_expiry))
    expiry_counts = tuple(sorted(counts.items()))

    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=None, ranked_spreads=tuple(ranked),
        n_qualified=pair_report.passed, filter_report=freport,
        pair_report=pair_report, report_text=text, message="",
        expiry_best=expiry_best, expiry_counts=expiry_counts)


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
                expiry=sv.long_leg.expiry, cost=sv.net_mid,
                baseline_return=spread_baseline_return(sv),
                natural_return=(sv.baseline_value - sv.net_worst) / sv.net_worst,
                breakeven=sv.breakeven, max_profit=sv.max_profit))
        else:
            firsts = [lst[0] for lst in res.ranked_bands.values() if lst]
            v = sorted(firsts,
                       key=lambda x: (-baseline_return(x), *_tie_break_key(x)))[0]
            c = v.contract
            max_profit = None if res.strategy == "long-call" else c.strike - v.mid
            rows.append(ComparisonRow(
                strategy=res.strategy, label=f"K={c.strike:g}",
                expiry=c.expiry, cost=v.mid,
                baseline_return=baseline_return(v),
                natural_return=(v.baseline_value - c.ask) / c.ask,
                breakeven=v.breakeven, max_profit=max_profit))
    return tuple(rows)


def _validate_request(request: AnalysisRequest) -> None:
    """Spec §2.2 step 0: reject before ANY fetch/load side effect."""
    if not request.strategies:
        raise ParamError("至少需要一種策略")
    invalid = [s for s in request.strategies if s not in STRATEGIES]
    if invalid:
        raise ParamError(f"未知策略: {', '.join(invalid)}")


def _analyze(request: AnalysisRequest, snap: ChainSnapshot,
             snapshot_path: str, progress: Progress | None) -> AnalysisResult:
    today = snapshot_today(snap.fetched_at)
    base = request.base_params
    if date.fromisoformat(base.target_date) <= today:
        raise ParamError(f"--target-date 必須晚於資料日 {today.isoformat()}")
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
        tuple(results), request.strategies, base.target_date)
    return AnalysisResult(
        request=request,
        meta=SnapshotMeta(symbol=snap.symbol, spot=snap.spot,
                          fetched_at=snap.fetched_at, source=snap.source,
                          snapshot_path=snapshot_path,
                          target_move=(base.target_price - snap.spot) / snap.spot),
        snapshot=snap, today=today, results=tuple(results),
        comparison=comparison, best_strategy=best,
        expiry_groups=expiry_groups, hidden_expiries=hidden_expiries,
        default_selection=default_selection)


def fetch_and_save(symbol: str) -> tuple[ChainSnapshot, str]:
    """v5 spec §4: 抓取＋落盤 snapshot（run 與 workspace.analyze_group 共用）。"""
    from .data.yf import fetch_chain  # lazy: offline paths never import yfinance

    snap = fetch_chain(symbol)
    out = Path("snapshots") / f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.json"
    out.parent.mkdir(exist_ok=True)
    save_snapshot(snap, out)
    return snap, str(out)


def run(request: AnalysisRequest, progress: Progress | None = None) -> AnalysisResult:
    _validate_request(request)
    _emit(progress, f"正在抓取 {request.symbol} 市場資料……")
    snap, out = fetch_and_save(request.symbol)
    return _analyze(request, snap, out, progress)


def run_offline(request: AnalysisRequest, snapshot_path: str,
                progress: Progress | None = None) -> AnalysisResult:
    _validate_request(request)
    snap = load_snapshot(snapshot_path)
    return _analyze(request, snap, str(snapshot_path), progress)
