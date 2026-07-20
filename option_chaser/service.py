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
from .ranking import (BAND_ORDER, _tie_break_key, baseline_return,
                      build_reasons, build_spread_reasons, rank, rank_spreads,
                      spread_baseline_return)
from .report import STRATEGY_LABELS, render, render_filter_only, render_spreads
from .scenarios import (ScenarioVector, completion_curve, completion_scan,
                        friction, scenario_vector, _value_fn)
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
    completion_threshold: float | None
    breakeven_at_target: float | None
    retention: float
    friction: float
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


@dataclass(frozen=True)
class AnalysisResult:
    request: AnalysisRequest
    meta: SnapshotMeta
    snapshot: ChainSnapshot
    today: date
    results: tuple[StrategyResult, ...]
    comparison: tuple[ComparisonRow, ...]
    best_strategy: str | None


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
    return dict(
        scenario=sv,
        completion_curve=completion_curve(val, spot, today, p),
        completion_threshold=k, breakeven_at_target=be,
        retention=1.0 + dict(sv.entries)["S1"], friction=fr,
        buffer_days=(date.fromisoformat(expiry)
                     - date.fromisoformat(p.target_date)).days,
        quote_warning=zero_vol or fr > 0.25,
        theta_day_rate=abs(_net_theta(val, spot, today, p)) / mid_cost,
        vega_per_pt=_net_vega(val, spot, today, p) / mid_cost,
        decay_30d_return=_decay_30d(val, spot, today, p))


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
        pros, cons = build_reasons(v, band, ranked, snap.spot,
                                   len(qualified), p)
        mv = _matrix_view(
            lambda S, d, c=v.contract: scenario_leg_value(c, S, d, p),
            v.mid, snap.spot, p, today, v.contract.expiry)
        candidates.append(CandidateView(
            valuation=v, pros=tuple(pros), cons=tuple(cons), matrix=mv,
            baseline_pnl=v.baseline_value - v.mid,
            baseline_return=baseline_return(v),
            natural_return=(v.baseline_value - v.contract.ask) / v.contract.ask,
            **_v4_fields(v, snap.spot, today, p)))
    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=ranked, ranked_spreads=None, n_qualified=len(qualified),
        filter_report=freport, pair_report=None, report_text=text, message="")


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
        pros, cons = build_spread_reasons(sv, i, pair_report.passed, p)
        mv = _matrix_view(
            lambda S, d, lng=sv.long_leg, sht=sv.short_leg:
                spread_scenario_value(lng, sht, S, d, p),
            sv.net_mid, snap.spot, p, today, sv.long_leg.expiry)
        candidates.append(CandidateView(
            valuation=sv, pros=tuple(pros), cons=tuple(cons), matrix=mv,
            baseline_pnl=sv.baseline_value - sv.net_mid,
            baseline_return=spread_baseline_return(sv),
            natural_return=(sv.baseline_value - sv.net_worst) / sv.net_worst,
            **_v4_fields(sv, snap.spot, today, p)))
    return StrategyResult(
        strategy=p.strategy, status="ok", candidates=tuple(candidates),
        ranked_bands=None, ranked_spreads=tuple(ranked),
        n_qualified=pair_report.passed, filter_report=freport,
        pair_report=pair_report, report_text=text, message="")


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
    return AnalysisResult(
        request=request,
        meta=SnapshotMeta(symbol=snap.symbol, spot=snap.spot,
                          fetched_at=snap.fetched_at, source=snap.source,
                          snapshot_path=snapshot_path),
        snapshot=snap, today=today, results=tuple(results),
        comparison=comparison, best_strategy=best)


def run(request: AnalysisRequest, progress: Progress | None = None) -> AnalysisResult:
    _validate_request(request)
    _emit(progress, f"正在抓取 {request.symbol} 市場資料……")
    from .data.yf import fetch_chain  # lazy: offline paths never import yfinance

    snap = fetch_chain(request.symbol)
    out = Path("snapshots") / f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.json"
    out.parent.mkdir(exist_ok=True)
    save_snapshot(snap, out)
    return _analyze(request, snap, str(out), progress)


def run_offline(request: AnalysisRequest, snapshot_path: str,
                progress: Progress | None = None) -> AnalysisResult:
    _validate_request(request)
    snap = load_snapshot(snapshot_path)
    return _analyze(request, snap, str(snapshot_path), progress)
