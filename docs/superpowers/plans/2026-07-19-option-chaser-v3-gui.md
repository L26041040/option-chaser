# Option Chaser v3 Web GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the v2 engine in a minimal Streamlit web GUI via a shared Application Service, with cross-strategy comparison and an HTML P/L heatmap — engine behavior and the four CLI goldens byte-frozen.

**Architecture:** New `option_chaser/service.py` (shared GUI/CLI entry), `matrix_grid()` added to `matrix.py` (matrix_lines refactored on top, output byte-identical), `cli.py` re-orchestrated onto the service (flag behavior and goldens unchanged), `webapp/app.py` Streamlit single file, Dockerfile + compose.yaml. Spec: `docs/superpowers/specs/2026-07-19-option-chaser-v3-gui-design.md` (codex-approved, 3 rounds).

**Tech Stack:** Python 3.11+, Streamlit (only new dep, as `gui` extra), stdlib elsewhere; heatmap = self-generated HTML table (no plotly).

## Global Constraints

- All commands POSIX shell — run in **Git Bash**, NOT PowerShell 5.1.
- **Byte-frozen regressions:** the four v2 goldens (`tests/fixtures/golden_*.txt`) and all existing 99+ tests must pass unchanged after EVERY task.
- GUI may not: call the CLI via subprocess, parse CLI text output, or contain ANY financial formula — all math via `option_chaser.service` → engine functions.
- One fetch per analysis; all selected strategies share the same snapshot.
- GUI never sets `force`; direction-mismatched strategies → `skipped_direction`, others still run.
- Heatmap color scale centered at 0%, display range clamped to ±100%, |ret| < 5% neutral gray `#ededed`, cells always show true numbers `{ret*100:+.0f}%`; color function pure/deterministic.
- Chinese UI copy from Brief_v3/spec used verbatim where quoted (progress lines, error messages, disclaimer).
- No traceback ever reaches the GUI user.
- Exit-code mapping for CLI unchanged: ok→0(print report_text, end=""), single-leg empty→1(print with trailing newline as v2), spread empty→1(end=""), skipped_direction→2 with v2-format ParamError message.

## File Structure

```
option_chaser/service.py    # NEW  shared Application Service (dataclasses + run/run_offline)
option_chaser/matrix.py     # MOD  + matrix_grid(); matrix_lines refactored (byte-identical)
option_chaser/cli.py        # MOD  main() orchestration via service
webapp/app.py               # NEW  Streamlit app (form/progress/results/heatmap/errors)
webapp/__init__.py          # NEW  empty (test importability)
Dockerfile                  # NEW
compose.yaml                # NEW
pyproject.toml              # MOD  [project.optional-dependencies] gui = ["streamlit>=1.30"]
tests/test_matrix_grid.py   # NEW
tests/test_service.py       # NEW
tests/test_webapp.py        # NEW  (Streamlit AppTest, offline)
tests/test_heatmap_colors.py# NEW
README.md                   # MOD  GUI/Docker section
```

---

### Task 1: `matrix_grid()` + `matrix_lines` refactor (byte-identical)

**Files:**
- Modify: `option_chaser/matrix.py`
- Create: `tests/test_matrix_grid.py`

**Interfaces:**
- Produces: `matrix.matrix_grid(value_fn, cost, prices, dates) -> tuple[tuple[float, ...], ...]` — `cells[i][j] = (value_fn(prices[i][0], dates[j][0]) − cost) / cost`, row order = prices ascending (same as input).
- `matrix_lines` becomes formatting-only on top of `matrix_grid`; output byte-identical (goldens prove it).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matrix_grid.py
import re
from datetime import date
from option_chaser.matrix import date_axis, matrix_grid, matrix_lines, price_axis


def _fn(S, d):
    return max(S - 110.0, 0.0)


def test_grid_shape_and_values():
    prices = price_axis(100.0, 120.0)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    grid = matrix_grid(_fn, 3.0, prices, dates)
    assert len(grid) == len(prices) and len(grid[0]) == len(dates)
    for i, (price, _) in enumerate(prices):
        for j, (d, _) in enumerate(dates):
            assert grid[i][j] == (_fn(price, d) - 3.0) / 3.0


def test_lines_formats_grid_cell_for_cell():
    prices = price_axis(100.0, 120.0)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    grid = matrix_grid(_fn, 3.0, prices, dates)
    lines = matrix_lines(_fn, 3.0, prices, dates)
    # data rows are displayed descending; parse each cell and compare to grid
    for row_idx, line in enumerate(lines[1:]):
        i = len(prices) - 1 - row_idx
        cells = re.findall(r"([+-]\d+)%", line)
        assert len(cells) == len(dates)
        for j, cell in enumerate(cells):
            assert cell == f"{grid[i][j] * 100:+.0f}".replace("+-", "-")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_matrix_grid.py -v`
Expected: FAIL — `ImportError: matrix_grid`

- [ ] **Step 3: Implement** — in `matrix.py`, add `matrix_grid` ABOVE `matrix_lines` and rewrite `matrix_lines` body (formatting unchanged character-for-character):

```python
def matrix_grid(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str]], dates: list[tuple[date, str]],
) -> tuple[tuple[float, ...], ...]:
    """Structured cell returns (v3 spec §2.3): single data source for CLI and GUI."""
    return tuple(
        tuple((value_fn(price, d) - cost) / cost for d, _ in dates)
        for price, _ in prices
    )


def matrix_lines(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str]], dates: list[tuple[date, str]],
) -> list[str]:
    grid = matrix_grid(value_fn, cost, prices, dates)
    header = "價格".ljust(10) + " ".join(
        (d.strftime("%m/%d") + lbl).rjust(7) for d, lbl in dates
    )
    lines = [header]
    for i in range(len(prices) - 1, -1, -1):
        price, plabel = prices[i]
        cells = [f"{grid[i][j] * 100:+.0f}%".rjust(7) for j in range(len(dates))]
        lines.append(f"{price:8.2f}{plabel}".ljust(10) + " ".join(cells))
    return lines
```

- [ ] **Step 4: Run full suite** — `python -m pytest -q` → all pass INCLUDING the four goldens (byte-identity proof).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v3): matrix_grid structured cells; matrix_lines refactored byte-identical"
```

---

### Task 2: Application Service (`service.py`)

**Files:**
- Create: `option_chaser/service.py`, `tests/test_service.py`

**Interfaces (produces — consumed by Tasks 3/4):**
- Dataclasses exactly per spec §2.2: `AnalysisRequest(symbol, base_params: AnalysisParams, strategies)`, `MatrixView(prices, dates, cells)` (dates as ISO strings), `CandidateView(valuation, pros, cons, matrix)`, `StrategyResult(strategy, status, candidates, ranked_bands, ranked_spreads, n_qualified, filter_report, pair_report, report_text, message)`, `ComparisonRow(strategy, label, expiry, cost, baseline_return, worst_return, breakeven, max_profit)`, `SnapshotMeta`, `AnalysisResult(meta, snapshot, today, results, comparison, best_strategy)`.
- `service.run(request, progress=None) -> AnalysisResult` (network, one fetch, snapshot saved); `service.run_offline(request, snapshot_path, progress=None)`.
- Semantics: skip only when direction mismatch AND not `base_params.force`; per-strategy params via `dataclasses.replace`; report_text ok=render/render_spreads, empty=render_filter_only/empty render_spreads, skipped=None; comparison rows = per-strategy global best (singles: max over band-firsts by baseline_return with v2 tie-break; spreads: ranked[0]); best_strategy tie → earlier in request order; Tab candidates: singles = band #1s in BAND_ORDER, spreads = top 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_service.py
import dataclasses
from datetime import date
from option_chaser.models import AnalysisParams, ParamError
from option_chaser import service
from option_chaser.ranking import baseline_return
import pytest

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def req(strategies, target=120.0, force=False):
    base = AnalysisParams(target_price=target, target_date="2026-08-28", force=force)
    return service.AnalysisRequest(symbol="XYZ", base_params=base,
                                   strategies=tuple(strategies))


def test_multi_strategy_shared_snapshot_and_order():
    r = service.run_offline(req(["long-call", "bull-call-spread"]), FIX)
    assert [s.strategy for s in r.results] == ["long-call", "bull-call-spread"]
    assert r.meta.spot == 100.0 and r.snapshot.symbol == "XYZ"
    assert r.today == date(2026, 7, 15)


def test_single_leg_result_matches_engine_and_report():
    from option_chaser.filters import apply_filters
    from option_chaser.valuation import evaluate_contract
    from option_chaser.ranking import rank
    from option_chaser.report import render
    from option_chaser.data.snapshot import load_snapshot, snapshot_today
    r = service.run_offline(req(["long-call"]), FIX)
    res = r.results[0]
    assert res.status == "ok" and res.n_qualified == 5
    p = dataclasses.replace(req(["long-call"]).base_params, strategy="long-call")
    snap = load_snapshot(FIX)
    today = snapshot_today(snap.fetched_at)
    qualified, freport = apply_filters(snap.contracts, p, today)
    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    ranked = rank(vals, p)
    assert res.report_text == render(snap, p, freport, ranked,
                                     n_qualified=len(qualified), today=today)
    # tab candidates = band #1s
    assert [cv.valuation.contract.contract_symbol for cv in res.candidates] == [
        ranked[b][0].contract.contract_symbol for b in ("conservative", "balanced", "aggressive") if ranked[b]]


def test_comparison_uses_global_best_not_band_order():
    r = service.run_offline(req(["long-call"]), FIX)
    res = r.results[0]
    row = r.comparison[0]
    firsts = [lst[0] for lst in res.ranked_bands.values() if lst]
    best = max(firsts, key=baseline_return)
    assert abs(row.baseline_return - baseline_return(best)) < 1e-12
    assert row.label == f"K={best.contract.strike:g}"
    assert row.max_profit is None  # long-call unlimited


def test_long_put_max_profit_bounded():
    r = service.run_offline(req(["long-put"], target=80.0), FIX)
    row = r.comparison[0]
    assert row.max_profit is not None and row.max_profit > 0


def test_direction_skip_without_force_runs_others():
    r = service.run_offline(req(["long-call", "long-put"], target=80.0), FIX)
    by = {s.strategy: s for s in r.results}
    assert by["long-call"].status == "skipped_direction"
    assert by["long-call"].report_text is None
    assert by["long-put"].status == "ok"
    assert r.best_strategy == "long-put"


def test_force_runs_mismatched_direction():
    r = service.run_offline(req(["long-call"], target=80.0, force=True), FIX)
    assert r.results[0].status == "ok"


def test_empty_carries_filter_only_report():
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                          min_expiry="2030-01-01")
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ", base_params=base, strategies=("long-call",)), FIX)
    res = r.results[0]
    assert res.status == "empty" and "無合格" in res.report_text
    assert r.comparison == () and r.best_strategy is None


def test_target_date_not_after_snapshot_raises():
    base = AnalysisParams(target_price=120.0, target_date="2026-07-15")
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=("long-call",)), FIX)


def test_matrix_view_matches_grid():
    from option_chaser.matrix import matrix_grid, price_axis, date_axis
    from option_chaser.valuation import scenario_leg_value
    r = service.run_offline(req(["long-call"]), FIX)
    cv = r.results[0].candidates[0]
    v = cv.valuation
    p = dataclasses.replace(req(["long-call"]).base_params, strategy="long-call")
    prices = price_axis(100.0, 120.0)
    dates = date_axis(r.today, date(2026, 8, 28),
                      date.fromisoformat(v.contract.expiry))
    grid = matrix_grid(lambda S, d, c=v.contract: scenario_leg_value(c, S, d, p),
                       v.mid, prices, dates)
    assert cv.matrix.cells == grid
    assert cv.matrix.dates[-1][0] == v.contract.expiry


def test_invalid_request_rejected():
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=()), FIX)
    with pytest.raises(ParamError):
        service.run_offline(service.AnalysisRequest(
            symbol="XYZ", base_params=base, strategies=("straddle",)), FIX)


def test_validation_precedes_fetch_and_load(monkeypatch):
    base = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    bad = service.AnalysisRequest(symbol="XYZ", base_params=base, strategies=())
    # run(): fetch must never be touched
    import option_chaser.data.yf as yf_mod
    monkeypatch.setattr(yf_mod, "fetch_chain",
                        lambda symbol: (_ for _ in ()).throw(AssertionError("fetch called")))
    with pytest.raises(ParamError):
        service.run(bad)
    # run_offline(): validation raises ParamError even for nonexistent path (load not reached)
    with pytest.raises(ParamError):
        service.run_offline(bad, "does-not-exist.json")


def test_result_carries_request():
    r = service.run_offline(req(["long-call"]), FIX)
    assert r.request.base_params.target_price == 120.0


def test_progress_callback_called():
    calls = []
    service.run_offline(req(["long-call"]), FIX, progress=calls.append)
    assert any("過濾" in c or "比較" in c for c in calls)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_service.py -v` → ModuleNotFoundError

- [ ] **Step 3: Implement `option_chaser/service.py`** (complete):

```python
"""Application service — single shared entry for CLI and GUI (v3 spec §2.2)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
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
from .valuation import (ContractValuation, SpreadValuation, evaluate_contract,
                        evaluate_spread, scenario_leg_value,
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
    worst_return: float
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
    prices = price_axis(spot, p.target_price)
    dates = date_axis(today, date.fromisoformat(p.target_date),
                      date.fromisoformat(expiry_iso))
    cells = matrix_grid(value_fn, cost, prices, dates)
    return MatrixView(prices=tuple(prices),
                      dates=tuple((d.isoformat(), lbl) for d, lbl in dates),
                      cells=cells)


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
        candidates.append(CandidateView(valuation=v, pros=tuple(pros),
                                        cons=tuple(cons), matrix=mv))
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
        candidates.append(CandidateView(valuation=sv, pros=tuple(pros),
                                        cons=tuple(cons), matrix=mv))
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
                worst_return=(sv.baseline_value - sv.net_worst) / sv.net_worst,
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
                worst_return=(v.baseline_value - c.ask) / c.ask,
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
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_service.py -v` → 10 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v3): shared application service with comparison and matrix views"
```

---

### Task 3: CLI re-orchestration onto the service (goldens frozen)

**Files:**
- Modify: `option_chaser/cli.py`
- Modify: `tests/test_cli_validation.py` (add regression tests below; existing tests unchanged)

**Interfaces:**
- `main()` behavior table (v2 parity): param error → print 參數錯誤+USAGE_HINT, exit 2; data error → 資料錯誤, exit 1; skipped_direction → re-raise via `validate_scenario(p, result.snapshot.spot, result.today)` to print the EXACT v2 message, exit 2; ok → `print(report_text, end="")`, `--md` writes same text, exit 0; single-leg empty → `print(report_text)` (v2 had trailing newline), exit 1; spread empty → `print(report_text, end="")`, exit 1. Symbol passed to the request UNCHANGED (no strip/upper — CLI parity).

- [ ] **Step 1: Add regression tests** (append to `tests/test_cli_validation.py`)

```python
def test_cli_uses_service_and_goldens_unchanged():
    # golden byte-identity is asserted by tests/test_golden_v2.py; here assert
    # the service wiring exists (no subprocess, single entry)
    import option_chaser.cli as cli
    import inspect
    src = inspect.getsource(cli.main)
    assert "service.run" in src or "run_offline" in src
    assert "subprocess" not in src


def test_cli_skipped_direction_exits_2(capsys, tmp_path):
    import json, io, contextlib
    from option_chaser.cli import main
    snap = json.loads(open("tests/fixtures/xyz_v2_snapshot.json", encoding="utf-8").read())
    f = tmp_path / "s.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--target-price", "80", "--target-date", "2026-08-28",
                   "--snapshot", str(f)])
    assert rc == 2 and "看漲策略目標價" in buf.getvalue()
```

- [ ] **Step 2: Run to verify failure** — first test fails (`service` not referenced yet).

- [ ] **Step 3: Implement** — replace `cli.main` body (keep resolve_params/validate_scenario/parser untouched):

```python
from . import service


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        p = resolve_params(args)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        print(USAGE_HINT)
        return 2

    request = service.AnalysisRequest(symbol=args.symbol, base_params=p,
                                      strategies=(p.strategy,))
    try:
        if args.snapshot:
            result = service.run_offline(request, args.snapshot)
        else:
            result = service.run(request)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        return 2
    except (FetchError, SnapshotSchemaError, OSError) as e:
        print(f"資料錯誤: {e}")
        return 1

    res = result.results[0]
    if res.status == "skipped_direction":
        try:
            validate_scenario(p, result.snapshot.spot, result.today)
        except ParamError as e:
            print(f"參數錯誤: {e}")
        return 2

    text = res.report_text
    if res.status == "empty":
        if p.strategy in SPREAD_STRATEGIES:
            print(text, end="")
        else:
            print(text)
        return 1
    print(text, end="")
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    return 0
```

（remove the now-unused direct imports in cli.py that only served the old orchestration: apply_filters/generate_spread_pairs/evaluate_contract/evaluate_spread/rank/rank_spreads/render/render_filter_only/render_spreads/load_snapshot/save_snapshot/snapshot_today — keep `SPREAD_STRATEGIES`, `FetchError`, `SnapshotSchemaError`, `Path`, `validate_scenario`.）

- [ ] **Step 4: Run FULL suite** — `python -m pytest -q` → all pass; the four goldens + `test_zero_qualified` style tests prove byte/exit parity.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(v3): cli orchestrates via service; goldens byte-identical"
```

---

### Task 4: Streamlit GUI (`webapp/app.py`)

**Files:**
- Create: `webapp/__init__.py` (empty), `webapp/app.py`
- Modify: `pyproject.toml` — add:

```toml
[project.optional-dependencies]
gui = ["streamlit>=1.30"]
```

**Interfaces:**
- `app.cell_color(ret: float) -> str` and `app.heatmap_html(mv: MatrixView) -> str` module-level pure functions (Task 5 tests import them).
- `app.run_analysis(request, progress)` seam = `service.run` (tests monkeypatch `option_chaser.service.run`).
- Widget keys: `symbol`, `target_price`, `target_date`, `chk-<strategy>`, submit button label 開始分析.

- [ ] **Step 1: Install streamlit** — `pip install -e ".[gui]"`

- [ ] **Step 2: Implement `webapp/app.py`** (complete):

```python
"""Option Chaser Web GUI（Streamlit）。所有金融計算一律經 option_chaser.service。"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from option_chaser import service
from option_chaser.models import AnalysisParams, FetchError, ParamError, SPREAD_STRATEGIES
from option_chaser.report import STRATEGY_LABELS

STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
DEFAULT_CHECKED = {"long-call", "bull-call-spread"}


def cell_color(ret: float) -> str:
    """0% 為中心之紅綠雙向色階；顯示範圍鉗制 ±100%；|ret|<5% 中性。純函數。"""
    if abs(ret) < 0.05:
        return "#ededed"
    t = min(abs(ret), 1.0)
    target = (34, 139, 34) if ret > 0 else (178, 34, 34)
    r = round(255 - t * (255 - target[0]))
    g = round(255 - t * (255 - target[1]))
    b = round(255 - t * (255 - target[2]))
    return f"#{r:02x}{g:02x}{b:02x}"


def _price_tag(label: str) -> str:
    tag = label.replace("<現價>", " 現價").replace("<目標>", " 目標")
    return tag


def heatmap_html(mv: service.MatrixView) -> str:
    n = len(mv.dates)
    head_cells = []
    for j, (iso, lbl) in enumerate(mv.dates):
        suffix = ("*" if lbl == "*" else "") + ("（到期）" if j == n - 1 else "")
        head_cells.append(
            f'<th style="padding:4px 8px;white-space:nowrap">{iso[5:7]}/{iso[8:10]}{suffix}</th>')
    rows = []
    for i in range(len(mv.prices) - 1, -1, -1):
        price, plabel = mv.prices[i]
        cells = "".join(
            f'<td style="background:{cell_color(v)};color:#111;text-align:right;'
            f'padding:4px 8px">{v * 100:+.0f}%</td>'
            for v in mv.cells[i])
        rows.append(
            f'<tr><td style="padding:4px 8px;white-space:nowrap">'
            f'{price:.2f}{_price_tag(plabel)}</td>{cells}</tr>')
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;'
            'font-family:monospace;font-size:13px">'
            f'<tr><th style="padding:4px 8px">價格</th>{"".join(head_cells)}</tr>'
            + "".join(rows) + "</table></div>"
            '<p style="font-size:12px;color:#666">此圖顯示在不同標的價格與日期下，'
            '以目前 Mid 價進場的模型報酬率。</p>')


def run_analysis(request, progress):
    return service.run(request, progress)


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _single_card(cv) -> str:
    v = cv.valuation
    c = v.contract
    warn = "；".join(cv.cons) if cv.cons else "無"
    return (f"**K={c.strike:g} / {c.expiry} 到期**\n\n"
            f"- Bid ${_money(c.bid)} / Mid ${_money(v.mid)} / Ask ${_money(c.ask)}"
            f"（每張 ${v.mid * 100:.0f}）｜IV {c.implied_volatility * 100:.0f}%｜"
            f"Delta {v.delta:.2f}\n"
            f"- Breakeven ${_money(v.breakeven)}｜劇本日估值 ${_money(v.baseline_value)}"
            f"｜損益 {v.baseline_value - v.mid:+.2f}｜"
            f"報酬率 {_pct((v.baseline_value - v.mid) / v.mid)}｜"
            f"最差進場 {_pct((v.baseline_value - c.ask) / c.ask)}\n"
            f"- 優點：{'；'.join(cv.pros)}\n- 警示：{warn}")


def _spread_card(cv) -> str:
    sv = cv.valuation
    warn = "；".join(cv.cons) if cv.cons else "無"
    return (f"**買 {sv.long_leg.strike:g} / 賣 {sv.short_leg.strike:g} / "
            f"{sv.long_leg.expiry} 到期（寬度 ${_money(sv.width)}）**\n\n"
            f"- Net Mid ${_money(sv.net_mid)}（每組 ${sv.net_mid * 100:.0f}）｜"
            f"最差（Natural）${_money(sv.net_worst)}｜最大虧損 ${_money(sv.net_mid)}｜"
            f"最大獲利 ${_money(sv.max_profit)}\n"
            f"- Breakeven ${_money(sv.breakeven)}｜劇本日估值 ${_money(sv.baseline_value)}"
            f"｜損益 {sv.baseline_value - sv.net_mid:+.2f}｜"
            f"報酬率 {_pct((sv.baseline_value - sv.net_mid) / sv.net_mid)}｜"
            f"最差進場 {_pct((sv.baseline_value - sv.net_worst) / sv.net_worst)}\n"
            f"- 優點：{'；'.join(cv.pros)}\n- 警示：{warn}")


def _render_results(result) -> None:
    m = result.meta
    st.subheader("劇本摘要")
    base = result.request.base_params
    lines = [f"{m.symbol} 現價 ${_money(m.spot)}",
             f"劇本：{base.target_date} 前到達 ${_money(base.target_price)}",
             f"資料時間：{m.fetched_at}（來源 {m.source}）",
             "已比較：" + "、".join(
                 STRATEGY_LABELS[r.strategy] for r in result.results
                 if r.status == "ok")]
    for r in result.results:
        if r.status != "ok":
            lines.append(f"（{STRATEGY_LABELS[r.strategy]}：{r.message}）")
    st.write("  \n".join(lines))

    if result.comparison:
        st.subheader("跨策略比較")
        header = "|策略|候選|到期日|進場成本|劇本報酬率|最差進場報酬率|Breakeven|最大獲利|\n|---|---|---|---|---|---|---|---|"
        rows = []
        for row in result.comparison:
            badge = "🏆最高報酬 " if row.strategy == result.best_strategy else ""
            mp = "無上限" if row.max_profit is None else f"${_money(row.max_profit)}"
            rows.append(
                f"|{badge}{STRATEGY_LABELS[row.strategy]}|{row.label}|{row.expiry}"
                f"|${_money(row.cost)}|{_pct(row.baseline_return)}"
                f"|{_pct(row.worst_return)}|${_money(row.breakeven)}|{mp}|")
        st.markdown(header + "\n" + "\n".join(rows))
        st.caption("最高報酬 ≠ 最佳投資：本系統不判斷劇本發生機率。")

    shown = [r for r in result.results]
    tabs = st.tabs([STRATEGY_LABELS[r.strategy] for r in shown])
    for tab, res in zip(tabs, shown):
        with tab:
            if res.status != "ok":
                st.info(res.message)
                continue
            for i, cv in enumerate(res.candidates):
                st.markdown(_spread_card(cv)
                            if res.strategy in SPREAD_STRATEGIES
                            else _single_card(cv))
                with st.expander("查看 Heatmap", expanded=(i == 0)):
                    st.markdown(heatmap_html(cv.matrix),
                                unsafe_allow_html=True)
            with st.expander("查看完整計算細節"):
                st.code(res.report_text, language=None)


st.set_page_config(page_title="Option Chaser", layout="wide")
st.title("Option Chaser")
st.caption("輸入你的價格劇本，Option Chaser 會自動掃描目前的選擇權鏈，"
           "比較單腿與價差策略，找出條件式報酬率最高的候選。")

with st.form("scenario"):
    symbol_in = st.text_input("標的", key="symbol", placeholder="TLT")
    target_price_in = st.number_input("目標價位", key="target_price",
                                      min_value=0.01, value=100.0, step=1.0)
    target_date_in = st.date_input("預計到達時間", key="target_date",
                                   value=date.today() + timedelta(days=180),
                                   min_value=date.today() + timedelta(days=1))
    checks = {s: st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}",
                             value=(s in DEFAULT_CHECKED))
              for s in STRATEGY_ORDER}
    submitted = st.form_submit_button(
        "開始分析", disabled=st.session_state.get("running", False))

def _do_analysis() -> None:
    """Runs on the rerun AFTER running=True, so the form above is already
    rendered disabled while this executes (two-phase rerun pattern)."""
    request = st.session_state.pop("pending_request")
    try:
        with st.status("分析中……", expanded=True) as status:
            result = run_analysis(request, status.write)
            status.update(label="分析完成", state="complete")
        st.session_state["result"] = result
        st.session_state.pop("error_msg", None)
    except FetchError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = (
            "找不到此標的，請確認代號是否正確。" if "資料不足" in str(e)
            else f"目前無法取得 {request.symbol} 的市場資料，請稍後再試。")
    except ParamError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = str(e)
    except Exception:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = "分析過程發生錯誤，請稍後再試。"
    finally:
        st.session_state["running"] = False


if submitted and not st.session_state.get("running", False):
    sym = (symbol_in or "").strip().upper()
    strategies = tuple(s for s in STRATEGY_ORDER if checks[s])
    if not sym:
        st.error("請輸入標的代號。")
    elif not strategies:
        st.error("請至少勾選一種策略。")
    else:
        base = AnalysisParams(target_price=float(target_price_in),
                              target_date=target_date_in.isoformat())
        st.session_state["pending_request"] = service.AnalysisRequest(
            symbol=sym, base_params=base, strategies=strategies)
        st.session_state["running"] = True
        st.rerun()   # next run renders the form with disabled=True, THEN analyzes

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()       # re-enable the button and show results/errors

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])
if "result" in st.session_state:
    _render_results(st.session_state["result"])
```

- [ ] **Step 3: Manual smoke** — `streamlit run webapp/app.py` briefly; form renders. (Automated tests in Task 5.)

- [ ] **Step 4: Full suite still green** — `python -m pytest -q`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v3): streamlit gui with comparison table, tabs, html heatmap"
```

---

### Task 5: GUI tests (AppTest) + heatmap color tests

**Files:**
- Create: `tests/test_webapp.py`, `tests/test_heatmap_colors.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_heatmap_colors.py
from webapp.app import cell_color


def test_neutral_band():
    assert cell_color(0.0) == "#ededed" == cell_color(0.049) == cell_color(-0.049)


def test_zero_centered_signs():
    assert cell_color(0.5) != cell_color(-0.5)


def test_clamp_saturation():
    assert cell_color(1.0) == cell_color(9.43)      # +943% same as +100%
    assert cell_color(-1.0) == cell_color(-5.1)


def test_deterministic():
    assert cell_color(0.37) == cell_color(0.37)
```

```python
# tests/test_webapp.py
from datetime import date
import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def _patched(monkeypatch):
    import option_chaser.service as svc
    real_offline = svc.run_offline
    monkeypatch.setattr(
        svc, "run",
        lambda req, progress=None: real_offline(req, FIX, progress))


def _fill_and_submit(at, symbol="XYZ", price=120.0,
                     checks=("long-call", "bull-call-spread")):
    at.text_input(key="symbol").set_value(symbol)
    at.number_input(key="target_price").set_value(price)
    at.date_input(key="target_date").set_value(date(2026, 8, 28))
    for s in ("long-call", "bull-call-spread", "long-put", "bear-put-spread"):
        at.checkbox(key=f"chk-{s}").set_value(s in checks)
    at.run()  # register widget states
    at.button[0].set_value(True).run(timeout=30)
    return at


def test_happy_path_renders_all_sections(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert "跨策略比較" in " ".join(s.value for s in at.subheader)
    assert "最高報酬" in body
    assert "overflow-x:auto" in body          # heatmap html present
    assert not at.exception


def test_summary_shows_scenario(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(getattr(x, "value", "") for x in at.markdown) +            " ".join(getattr(x, "value", "") for x in at.text)
    assert "劇本" in body and "120" in body and "2026-08-28" in body


def test_direction_mismatch_partial(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, price=80.0,
                          checks=("long-call", "long-put"))
    texts = " ".join(getattr(x, "value", "") for x in at.info) + \
            " ".join(m.value for m in at.markdown)
    assert "未執行" in texts                    # skip message shown
    assert not at.exception


def test_empty_symbol_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, symbol="   ")
    assert any("請輸入標的代號" in e.value for e in at.error)


def test_no_strategy_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, checks=())
    assert any("至少勾選一種策略" in e.value for e in at.error)


def test_fetch_error_mappings(monkeypatch):
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 回傳資料不足（XX）：無現價或無合約")))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, symbol="XX")
    assert any("找不到此標的" in e.value for e in at.error)

    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 抓取失敗（XX）: boom")))
    at2 = AppTest.from_file("webapp/app.py")
    at2.run()
    at2 = _fill_and_submit(at2, symbol="XX")
    assert any("請稍後再試" in e.value for e in at2.error)


def test_no_traceback_on_unexpected(monkeypatch):
    import option_chaser.service as svc
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    assert any("分析過程發生錯誤" in e.value for e in at.error)
    assert not at.exception
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_webapp.py tests/test_heatmap_colors.py -v`; iterate on AppTest selector details if the API differs (fix the TEST addressing, never weaken assertions). Then full suite.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "test(v3): apptest gui coverage and heatmap color rules"
```

---

### Task 6: Docker, README, live smoke

**Files:**
- Create: `Dockerfile`, `compose.yaml`, `.dockerignore`
- Modify: `README.md`

- [ ] **Step 1: Write files**

`Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY option_chaser ./option_chaser
COPY webapp ./webapp
RUN pip install --no-cache-dir ".[gui]"
ENV PORT=8501
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
  python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8501')+'/_stcore/health')"
CMD ["sh", "-c", "streamlit run webapp/app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
```

`compose.yaml`:
```yaml
services:
  option-chaser:
    build: .
    ports:
      - "${PORT:-8501}:8501"
    volumes:
      - ./snapshots:/app/snapshots
    restart: unless-stopped
```

`.dockerignore`:
```
.git
snapshots/*.json
.superpowers
__pycache__
*.egg-info
.pytest_cache
```

`README.md` — append after the CLI 使用說明 section:

```markdown
## Web GUI

    pip install -e ".[gui]"
    streamlit run webapp/app.py        # http://localhost:8501

或 Docker：

    docker compose up -d               # http://localhost:8501（PORT 環境變數可改）

網頁只需四項輸入（標的／目標價／到達日期／策略勾選，預設 Long Call
+ Bull Call Spread），一次抓取市場資料後同一快照分析所有勾選策略，
輸出跨策略比較表、各策略前三名候選與價格×日期 P/L Heatmap。
進階參數一律採用 CLI 預設值；方向不合的策略會被跳過並提示，
GUI 不提供 --force。所有計算皆由與 CLI 相同的引擎完成。
```

- [ ] **Step 2: Full suite** — `python -m pytest -q` → green.

- [ ] **Step 3: Live smoke (network; non-blocking on failure, note outcome)**

```bash
python - <<'EOF'
from option_chaser.models import AnalysisParams
from option_chaser import service
base = AnalysisParams(target_price=110.0, target_date="2027-12-31")
req = service.AnalysisRequest(symbol="TLT", base_params=base,
                              strategies=("long-call", "bull-call-spread"))
r = service.run(req, progress=print)
print("strategies:", [(s.strategy, s.status, len(s.candidates)) for s in r.results])
print("comparison rows:", len(r.comparison), "best:", r.best_strategy)
print("snapshot:", r.meta.snapshot_path)
EOF
```

Expected: both strategies ok with candidates; snapshot saved.

- [ ] **Step 4: Docker verification（若本機有 Docker；否則記錄留給 audit SL）**

```bash
docker compose up -d --build && sleep 20 && docker compose ps
curl -s http://localhost:8501/_stcore/health
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v3): dockerfile, compose, gui readme; live smoke"
```

---

## Self-Review Notes (author-checked)

- Spec coverage: §2.2 contract → T2 (dataclasses verbatim, incl. report_text ok/empty/None rules, force gating, CLI mapping in T3); §2.3 → T1; §3 GUI → T4 (form/progress/五區/文案) + T5 (AppTest); §4 heatmap → T4 code + T5 color tests (0-center/±100% clamp/neutral/deterministic); §5 error mapping → T4 + T5; §6 Docker → T6; §7 tests 1-6 → T2 (parity/behavior) T1 (grid parity) golden suite (byte-frozen) T5 (AppTest/colors) T6 (docker manual); §7A audit contract enforced at codex-audit; §8 acceptance = Brief §10 mirrored by T2 (shared snapshot #3), T4/T5 (#1/#2/#4/#5/#6/#7/#10), T1+T2 (#8 structural), constraints (#9), T6 (#11/#13), service parity tests (#12), heatmap overflow div (#14).
- Type consistency: `MatrixView.dates` ISO strings produced in T2, consumed by T4 `heatmap_html` (`iso[5:7]`), matches; `_tie_break_key` import from ranking exists (v2); `STRATEGY_LABELS` exported by report.py (v2 Task 3); `run_analysis` seam patched via `svc.run` (T5 patches the service module attr the app calls through).
- Placeholder scan: clean（先前 `_render_results` 內的殘留佔位迴圈已直接自 T4 程式碼移除）.
```

<!-- codex-peer-reviewed: 2026-07-19T11:43:43Z rounds=3 verdict=approved -->
