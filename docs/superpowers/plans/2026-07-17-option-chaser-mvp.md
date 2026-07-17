# Option Chaser MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Option Chaser CLI: scan a US stock's Long Call chain, filter, valuate under the user's scenario with Black-Scholes, band by Delta, and emit a deterministic plain-text report with price-ceiling guidance.

**Architecture:** Pure-function pipeline `cli → report → ranking → valuation → filters → models` (one-way deps). Only `data/yf.py` touches the network; everything downstream of a snapshot is deterministic (same snapshot + params → byte-identical report). Spec: `docs/superpowers/specs/2026-07-15-option-chaser-mvp-design.md` (codex-approved round 2).

**Tech Stack:** Python 3.11+, stdlib only for math (`math.erf`, no scipy/numpy), `yfinance` as sole third-party runtime dep (+`tzdata` wheel on Windows for `zoneinfo` — timezone *data*, not a computation lib), `pytest` for tests (all offline).

## Global Constraints

- Python ≥ 3.11; package name `option_chaser`.
- Third-party runtime deps: `yfinance` only (plus `tzdata` on Windows for `zoneinfo`). Normal CDF via `0.5*(1+math.erf(x/√2))`.
- Determinism: analysis never reads the system clock; "today" = snapshot `fetched_at` converted to `America/New_York`, date part. No randomness. Fixed number formats: prices `{:.2f}`, returns `{x*100:.1f}%`, Lambda `{:.1f}`, Delta `{:.2f}`.
- Report is plain text; box-drawing characters are FORBIDDEN.
- All dates are US/Eastern calendar days; day counts are calendar days; `T = days/365`.
- `bs_call` with `T ≤ 0` returns `max(S−K, 0)` (no division by zero).
- iv_shifts: multiplier `1+shift` must be > 0; shift `0.0` force-included, deduped, sorted ascending.
- Filters run in fixed order (expiry → quote → IV → OI/volume → spread); a contract is counted against the FIRST stage it fails.
- No probability / expected-return logic anywhere (brief hard constraint).
- Every commit message: imperative summary line; commit after each task's tests pass.
- **Shell**: every command in this plan is POSIX shell — run them in **Git Bash**, NOT PowerShell 5.1 (`&&` is a parser error there). If you must use PowerShell, replace `A && B` with `A; if ($?) { B }`.
- Report money display (spec §7): per-share price AND per-contract amount (×100) side by side, e.g. `$3.13（$313/張）`; per-contract amounts formatted `{x*100:.0f}`.

## File Structure

```
option-chaser/
├── option_chaser/
│   ├── __init__.py            # empty
│   ├── models.py              # OptionContract, ChainSnapshot, AnalysisParams, FilterReport, errors
│   ├── data/
│   │   ├── __init__.py        # empty
│   │   ├── snapshot.py        # save/load JSON, snapshot_today()
│   │   └── yf.py              # yfinance fetch + row-dict mapping (lazy import; only networked module)
│   ├── valuation.py           # norm_cdf, bs_call, greeks, evaluate_contract (scenarios/stress/guidance)
│   ├── filters.py             # apply_filters -> (qualified, FilterReport)
│   ├── ranking.py             # classify, rank, build_reasons
│   ├── report.py              # render() -> str
│   └── cli.py                 # argparse, resolve_params, validate_scenario, main
├── tests/
│   ├── fixtures/
│   │   ├── xyz_snapshot.json  # golden fixture (10 contracts)
│   │   ├── golden_report.txt  # golden expected output
│   │   └── yf_rows.json       # raw-ish yfinance row dicts incl. NaN cases
│   ├── test_models_snapshot.py
│   ├── test_bs.py
│   ├── test_greeks.py
│   ├── test_valuation.py
│   ├── test_guidance.py
│   ├── test_filters.py
│   ├── test_ranking.py
│   ├── test_reasons.py
│   ├── test_yf_adapter.py
│   ├── test_cli_validation.py
│   └── test_golden.py
├── snapshots/.gitkeep         # runtime snapshots dir (gitignored contents)
├── .gitignore
├── pyproject.toml
└── README.md
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `option_chaser/__init__.py`, `option_chaser/data/__init__.py`, `snapshots/.gitkeep`, `tests/test_models_snapshot.py` (smoke only, extended in Task 2)

**Interfaces:**
- Produces: installable package `option_chaser`; `python -m pytest` runs green.

- [ ] **Step 1: Write files**

`pyproject.toml`:
```toml
[project]
name = "option-chaser"
version = "0.1.0"
description = "Long Call scenario optimizer (deterministic, no probability logic)"
requires-python = ">=3.11"
dependencies = [
  "yfinance>=0.2",
  "tzdata; platform_system == 'Windows'",
]

[project.scripts]
option-chaser = "option_chaser.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["option_chaser*"]

[tool.pytest.ini_options]
addopts = "-q"
```

`.gitignore`:
```
__pycache__/
*.egg-info/
.pytest_cache/
snapshots/*.json
```

`option_chaser/__init__.py` and `option_chaser/data/__init__.py`: empty files. `snapshots/.gitkeep`: empty file.

`tests/test_models_snapshot.py`:
```python
def test_package_imports():
    import option_chaser  # noqa: F401
```

- [ ] **Step 2: Install and run**

Run (Git Bash; one per line):
```bash
pip install -e .
pip install pytest
python -m pytest
```
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: scaffold option_chaser package"
```

---

### Task 2: Models + snapshot save/load

**Files:**
- Create: `option_chaser/models.py`, `option_chaser/data/snapshot.py`
- Modify: `tests/test_models_snapshot.py`

**Interfaces:**
- Produces:
  - `models.OptionContract(contract_symbol: str, strike: float, expiry: str, bid: float|None, ask: float|None, last: float|None, volume: int, open_interest: int, implied_volatility: float|None)` frozen dataclass
  - `models.ChainSnapshot(schema_version: int, symbol: str, fetched_at: str, spot: float, source: str, contracts: tuple[OptionContract, ...])` frozen dataclass
  - `models.AnalysisParams` frozen dataclass (all CLI knobs; see code)
  - `models.FilterStageResult(label: str, removed: int)`, `models.FilterReport(total: int, stages: tuple[FilterStageResult, ...], passed: int)`
  - `models.SCHEMA_VERSION = 1`, `models.SnapshotSchemaError`, `models.FetchError`, `models.ParamError`
  - `data.snapshot.save_snapshot(snap, path)`, `load_snapshot(path) -> ChainSnapshot`, `snapshot_today(fetched_at: str) -> datetime.date`

- [ ] **Step 1: Write the failing tests** (replace file content)

```python
# tests/test_models_snapshot.py
from datetime import date
from option_chaser.models import (
    OptionContract, ChainSnapshot, SCHEMA_VERSION, SnapshotSchemaError,
)
from option_chaser.data.snapshot import save_snapshot, load_snapshot, snapshot_today
import pytest


def make_snap():
    c = OptionContract(
        contract_symbol="XYZ261016C00110000", strike=110.0, expiry="2026-10-16",
        bid=3.0, ask=3.25, last=3.1, volume=152, open_interest=830,
        implied_volatility=0.38,
    )
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol="XYZ",
        fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
        source="yfinance", contracts=(c,),
    )


def test_roundtrip(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    assert load_snapshot(p) == snap


def test_schema_mismatch(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 99')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError):
        load_snapshot(p)


def test_snapshot_today_eastern():
    # 21:30 EDT on 7/15 is still 7/15 in New York
    assert snapshot_today("2026-07-15T21:30:00-04:00") == date(2026, 7, 15)
    # 03:00 UTC on 7/16 is 23:00 EDT on 7/15 -> "today" is 7/15
    assert snapshot_today("2026-07-16T03:00:00+00:00") == date(2026, 7, 15)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_models_snapshot.py -v`
Expected: FAIL — `ImportError` (names not defined)

- [ ] **Step 3: Implement**

```python
# option_chaser/models.py
"""Core data structures and errors. Stdlib only."""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


class SnapshotSchemaError(Exception):
    pass


class FetchError(Exception):
    pass


class ParamError(Exception):
    pass


@dataclass(frozen=True)
class OptionContract:
    contract_symbol: str
    strike: float
    expiry: str  # YYYY-MM-DD
    bid: float | None
    ask: float | None
    last: float | None
    volume: int
    open_interest: int
    implied_volatility: float | None


@dataclass(frozen=True)
class ChainSnapshot:
    schema_version: int
    symbol: str
    fetched_at: str  # ISO 8601 with UTC offset
    spot: float
    source: str
    contracts: tuple[OptionContract, ...]


@dataclass(frozen=True)
class AnalysisParams:
    target_price: float
    target_date: str  # YYYY-MM-DD
    min_days_after: int = 0
    min_expiry: str | None = None
    top: int = 3
    iv_shifts: tuple[float, ...] = (-0.2, 0.0, 0.2)  # normalized: 0 included, sorted
    rate: float = 0.04
    min_oi: int = 10
    min_volume: int = 0
    max_spread_pct: float = 0.15
    spread_floor: float = 0.10
    delta_bands: tuple[float, float] = (0.35, 0.65)
    min_return: float = 0.0
    delay_days: int = 0  # resolved from effective_buffer at param resolution
    force: bool = False


@dataclass(frozen=True)
class FilterStageResult:
    label: str
    removed: int


@dataclass(frozen=True)
class FilterReport:
    total: int
    stages: tuple[FilterStageResult, ...]
    passed: int
```

```python
# option_chaser/data/snapshot.py
"""Snapshot persistence + snapshot-derived 'today'. Stdlib only."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..models import SCHEMA_VERSION, ChainSnapshot, OptionContract, SnapshotSchemaError

_EASTERN = ZoneInfo("America/New_York")


def save_snapshot(snap: ChainSnapshot, path: str | Path) -> None:
    data = asdict(snap)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_snapshot(path: str | Path) -> ChainSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotSchemaError(
            f"snapshot schema_version={data.get('schema_version')} incompatible "
            f"with {SCHEMA_VERSION}; re-fetch the chain"
        )
    contracts = tuple(OptionContract(**c) for c in data["contracts"])
    return ChainSnapshot(
        schema_version=data["schema_version"], symbol=data["symbol"],
        fetched_at=data["fetched_at"], spot=data["spot"],
        source=data["source"], contracts=contracts,
    )


def snapshot_today(fetched_at: str) -> date:
    """Spec §8: 'today' = fetched_at converted to US/Eastern, date part."""
    return datetime.fromisoformat(fetched_at).astimezone(_EASTERN).date()
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_models_snapshot.py -v`
Expected: 4 passed (incl. Task 1 smoke)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: models, snapshot persistence, eastern-date derivation"
```

---

### Task 3: Black-Scholes pricing

**Files:**
- Create: `option_chaser/valuation.py`, `tests/test_bs.py`

**Interfaces:**
- Produces: `valuation.norm_cdf(x) -> float`, `valuation.norm_pdf(x) -> float`, `valuation.bs_call(S, K, T, r, sigma) -> float` (T ≤ 0 → intrinsic), `valuation.DAYS_PER_YEAR = 365.0`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bs.py
import math
from option_chaser.valuation import bs_call, norm_cdf


def _bs_put(S, K, T, r, sigma):
    # local reference implementation for parity check only
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def test_hull_textbook_value():
    # Hull, Options Futures and Other Derivatives: S=42,K=40,T=0.5,r=0.10,sigma=0.20 -> C≈4.76
    assert abs(bs_call(42, 40, 0.5, 0.10, 0.20) - 4.76) < 0.01


def test_zero_rate_atm():
    # S=K=100,T=1,r=0,sigma=0.2 -> 100*(N(0.1)-N(-0.1)) = 7.9656
    assert abs(bs_call(100, 100, 1.0, 0.0, 0.2) - 7.9656) < 1e-3


def test_put_call_parity():
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.35
    c = bs_call(S, K, T, r, sigma)
    p = _bs_put(S, K, T, r, sigma)
    assert abs((c - p) - (S - K * math.exp(-r * T))) < 1e-9


def test_t_zero_returns_intrinsic():
    assert bs_call(120, 110, 0.0, 0.04, 0.38) == 10.0
    assert bs_call(100, 110, 0.0, 0.04, 0.38) == 0.0
    assert bs_call(120, 110, -0.01, 0.04, 0.38) == 10.0


def test_deep_itm_approaches_forward_intrinsic():
    S, K, T, r = 100, 1, 0.5, 0.05
    assert abs(bs_call(S, K, T, r, 0.2) - (S - K * math.exp(-r * T))) < 1e-6


def test_deep_otm_approaches_zero():
    assert bs_call(100, 1000, 0.5, 0.05, 0.2) < 1e-6


def test_t_to_zero_approaches_intrinsic():
    assert abs(bs_call(120, 110, 1e-9, 0.04, 0.38) - 10.0) < 1e-4
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_bs.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Implement**

```python
# option_chaser/valuation.py
"""Black-Scholes valuation, Greeks, scenario/stress/guidance. Stdlib math only."""
from __future__ import annotations

import math

DAYS_PER_YEAR = 365.0


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call. Spec §5.1: T <= 0 -> intrinsic (BS undefined at T=0)."""
    if T <= 0.0:
        return max(S - K, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_bs.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: black-scholes call pricing with T<=0 intrinsic branch"
```

---

### Task 4: Greeks

**Files:**
- Modify: `option_chaser/valuation.py`
- Create: `tests/test_greeks.py`

**Interfaces:**
- Produces: `valuation.Greeks(delta, gamma, theta_per_day, vega_per_pct)` frozen dataclass; `valuation.call_greeks(S, K, T, r, sigma) -> Greeks` (caller guarantees T > 0)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_greeks.py
from option_chaser.valuation import call_greeks


def test_hull_greeks():
    # S=42,K=40,T=0.5,r=0.10,sigma=0.20 (Hull): d1=0.7693
    g = call_greeks(42, 40, 0.5, 0.10, 0.20)
    assert abs(g.delta - 0.7791) < 1e-3
    assert abs(g.gamma - 0.0500) < 1e-3
    assert abs(g.theta_per_day - (-4.559 / 365.0)) < 1e-4
    assert abs(g.vega_per_pct - 0.0882) < 1e-3


def test_delta_bounds():
    for k in (20, 40, 60, 100):
        g = call_greeks(50, k, 0.3, 0.04, 0.4)
        assert 0.0 < g.delta < 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_greeks.py -v`
Expected: FAIL — `ImportError: call_greeks`

- [ ] **Step 3: Implement** (append to `valuation.py`)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float


def call_greeks(S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §5.5. Caller guarantees T > 0 (filters ensure expiry > today)."""
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm_cdf(d2)
    )
    return Greeks(
        delta=norm_cdf(d1),
        gamma=norm_pdf(d1) / (S * st),
        theta_per_day=theta_year / DAYS_PER_YEAR,
        vega_per_pct=S * norm_pdf(d1) * math.sqrt(T) / 100.0,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_greeks.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: call greeks (delta, gamma, theta/day, vega/1pct)"
```

---

### Task 5: Contract valuation (scenarios, breakeven, lambda, stress)

**Files:**
- Modify: `option_chaser/valuation.py`
- Create: `tests/test_valuation.py`

**Interfaces:**
- Consumes: `bs_call`, `call_greeks`, `models.OptionContract`, `models.AnalysisParams`
- Produces:
  - `valuation.ContractValuation` frozen dataclass — fields: `contract: OptionContract, mid: float, spread: float, delta, gamma, theta_per_day, vega_per_pct: float, breakeven: float, breakeven_vs_spot: float, breakeven_vs_target: float, effective_leverage: float, floor_value: float, scenario_values: tuple[tuple[float, float], ...] (shift, value) ascending, baseline_value: float, stress_half: float, stress_delay: float | None, stress_flat: float, l1: float, l2: float, l3: float`
  - `valuation.evaluate_contract(c: OptionContract, spot: float, today: date, p: AnalysisParams) -> ContractValuation`
  - `valuation.days_between(d1: date, d2: date) -> int`
- Note: `evaluate_contract` requires bid/ask/IV non-null — filters (Task 7) guarantee this; assert defensively.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_valuation.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import bs_call, evaluate_contract

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=23)


def make_contract(**kw):
    base = dict(contract_symbol="XYZ261016C00110000", strike=110.0,
                expiry="2026-10-16", bid=3.0, ask=3.25, last=3.1,
                volume=152, open_interest=830, implied_volatility=0.38)
    base.update(kw)
    return OptionContract(**base)


def test_mid_spread_breakeven_lambda():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    assert v.mid == 3.125
    assert abs(v.spread - 0.25) < 1e-12
    assert v.breakeven == 113.125                       # strike + mid
    assert abs(v.breakeven_vs_spot - 0.13125) < 1e-9    # (be-spot)/spot
    assert abs(v.breakeven_vs_target - (120 - 113.125) / 120) < 1e-9
    assert abs(v.effective_leverage - v.delta * 100.0 / 3.125) < 1e-9


def test_scenario_values_match_bs():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert v.floor_value == 10.0  # max(120-110,0)
    shifts = [s for s, _ in v.scenario_values]
    assert shifts == [-0.2, 0.0, 0.2]
    for shift, val in v.scenario_values:
        expected = bs_call(120.0, 110.0, t_rem, P.rate, 0.38 * (1 + shift))
        assert abs(val - expected) < 1e-12
    assert v.baseline_value == dict(v.scenario_values)[0.0]


def test_stress_scenarios():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert abs(v.stress_half - bs_call(110.0, 110.0, t_rem, P.rate, 0.38)) < 1e-12
    t_delay = (date(2026, 10, 16) - date(2026, 8, 28)).days - 23
    assert abs(v.stress_delay - bs_call(120.0, 110.0, t_delay / 365.0, P.rate, 0.38)) < 1e-12
    assert abs(v.stress_flat - bs_call(100.0, 110.0, t_rem, P.rate, 0.38)) < 1e-12


def test_delay_zero_skips_delay_scenario():
    p0 = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=p0)
    assert v.stress_delay is None


def test_expiry_equals_target_date_uses_intrinsic():
    p0 = AnalysisParams(target_price=120.0, target_date="2026-10-16", delay_days=0)
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=p0)
    assert v.baseline_value == 10.0  # T_rem == 0 -> intrinsic branch
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_valuation.py -v`
Expected: FAIL — `ImportError: evaluate_contract`

- [ ] **Step 3: Implement** (append to `valuation.py`)

```python
from datetime import date

from .models import AnalysisParams, OptionContract


def days_between(d1: date, d2: date) -> int:
    return (d2 - d1).days


@dataclass(frozen=True)
class ContractValuation:
    contract: OptionContract
    mid: float
    spread: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float
    breakeven: float
    breakeven_vs_spot: float
    breakeven_vs_target: float
    effective_leverage: float
    floor_value: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    stress_half: float
    stress_delay: float | None
    stress_flat: float
    l1: float
    l2: float
    l3: float


def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams
) -> ContractValuation:
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    iv = c.implied_volatility
    expiry = date.fromisoformat(c.expiry)
    target = date.fromisoformat(p.target_date)

    g = call_greeks(spot, c.strike, days_between(today, expiry) / DAYS_PER_YEAR,
                    p.rate, iv)

    t_rem = days_between(target, expiry) / DAYS_PER_YEAR
    floor_value = max(p.target_price - c.strike, 0.0)
    scenario_values = tuple(
        (shift, bs_call(p.target_price, c.strike, t_rem, p.rate, iv * (1.0 + shift)))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]

    half_price = spot + 0.5 * (p.target_price - spot)
    stress_half = bs_call(half_price, c.strike, t_rem, p.rate, iv)
    stress_flat = bs_call(spot, c.strike, t_rem, p.rate, iv)
    stress_delay = None
    if p.delay_days > 0:
        t_delay = (days_between(target, expiry) - p.delay_days) / DAYS_PER_YEAR
        stress_delay = bs_call(p.target_price, c.strike, t_delay, p.rate, iv)

    # Price guidance (spec §5.7): L1 <= L2 <= baseline; L3 <= baseline.
    l1 = floor_value
    l2 = bs_call(p.target_price, c.strike, t_rem, p.rate,
                 iv * (1.0 + min(p.iv_shifts)))
    l3 = baseline_value / (1.0 + p.min_return)

    breakeven = c.strike + mid
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven,
        breakeven_vs_spot=(breakeven - spot) / spot,
        breakeven_vs_target=(p.target_price - breakeven) / p.target_price,
        effective_leverage=g.delta * spot / mid,
        floor_value=floor_value,
        scenario_values=scenario_values,
        baseline_value=baseline_value,
        stress_half=stress_half, stress_delay=stress_delay, stress_flat=stress_flat,
        l1=l1, l2=l2, l3=l3,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_valuation.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: per-contract scenario valuation, breakeven, lambda, stress, guidance"
```

---

### Task 6: Price guidance identity + judgment sentences

**Files:**
- Modify: `option_chaser/valuation.py`
- Create: `tests/test_guidance.py`

**Interfaces:**
- Produces: `valuation.guidance_judgments(v: ContractValuation, p: AnalysisParams) -> list[str]` — zero or more warning sentences; empty list means Ask is below all three ceilings.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guidance.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract, guidance_judgments

TODAY = date(2026, 7, 15)


def make(strike, bid, ask, iv, expiry="2026-10-16"):
    return OptionContract(
        contract_symbol=f"XYZ-K{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=None, volume=10, open_interest=100,
        implied_volatility=iv,
    )


def test_ceiling_identity_matrix():
    # Spec §9 test 5: L1 <= L2 <= baseline over a fixed parameter matrix.
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    for strike in (80.0, 100.0, 110.0, 119.0, 130.0, 150.0):
        for iv in (0.15, 0.38, 0.9):
            for expiry in ("2026-10-16", "2027-01-15"):
                v = evaluate_contract(make(strike, 3.0, 3.2, iv, expiry),
                                      spot=100.0, today=TODAY, p=p)
                assert v.l1 <= v.l2 + 1e-12
                assert v.l2 <= v.baseline_value + 1e-12
                assert v.l3 <= v.baseline_value + 1e-12


def test_no_negative_shift_l2_equals_baseline():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       iv_shifts=(0.0, 0.2), delay_days=0)
    v = evaluate_contract(make(110.0, 3.0, 3.2, 0.38), spot=100.0, today=TODAY, p=p)
    assert v.l2 == v.baseline_value


def test_judgments_all_trigger():
    # ask above every ceiling -> all three sentences
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make(95.0, 30.6, 31.0, 0.9), spot=100.0, today=TODAY, p=p)
    msgs = guidance_judgments(v, p)
    assert len(msgs) == 3
    assert "超過劇本內在價值" in msgs[0]
    assert "最保守 IV 情境" in msgs[1]
    assert "最低報酬" in msgs[2]


def test_judgments_none_trigger():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28", delay_days=0)
    v = evaluate_contract(make(110.0, 3.0, 3.25, 0.38), spot=100.0, today=TODAY, p=p)
    assert guidance_judgments(v, p) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_guidance.py -v`
Expected: FAIL — `ImportError: guidance_judgments`

- [ ] **Step 3: Implement** (append to `valuation.py`)

```python
def _shift_label(shift: float) -> str:
    if shift == 0.0:
        return "shift=0，即基準"
    return f"shift={shift * 100:+g}%"


def guidance_judgments(v: ContractValuation, p: AnalysisParams) -> list[str]:
    """Spec §5.7: independent per-ceiling judgments against current Ask."""
    ask = v.contract.ask
    msgs: list[str] = []
    if ask > v.l1:
        msgs.append("超過劇本內在價值，獲利需時間價值/IV 配合")
    if ask > v.l2:
        msgs.append(
            f"劇本成立但最保守 IV 情境（{_shift_label(min(p.iv_shifts))}）下仍虧損"
        )
    if ask > v.l3:
        msgs.append("以 Ask 進場達不到你設定的最低報酬（min-return）")
    return msgs
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_guidance.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: price-ceiling identity guarantees and ask judgment sentences"
```

---

### Task 7: Filters

**Files:**
- Create: `option_chaser/filters.py`, `tests/test_filters.py`

**Interfaces:**
- Consumes: `models.OptionContract`, `models.AnalysisParams`, `models.FilterReport`
- Produces: `filters.apply_filters(contracts: Iterable[OptionContract], p: AnalysisParams, today: date) -> tuple[list[OptionContract], FilterReport]`; stage labels exactly: `"到期日不符"`, `"報價異常"`, `"IV 異常"`, `"OI/成交量不足"`, `"Spread 過寬"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_filters.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import apply_filters

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28", min_days_after=45)
# expiry must be >= 2026-10-12


def make(sym="A", strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25,
         iv=0.38, volume=100, oi=100):
    return OptionContract(contract_symbol=sym, strike=strike, expiry=expiry,
                          bid=bid, ask=ask, last=None, volume=volume,
                          open_interest=oi, implied_volatility=iv)


def test_each_stage_rejects():
    contracts = [
        make("ok"),
        make("early", expiry="2026-09-18"),          # stage 1
        make("zerobid", bid=0.0),                    # stage 2
        make("nullbid", bid=None),                   # stage 2 (null counts as fail)
        make("crossed", bid=3.0, ask=2.0),           # stage 2
        make("lowiv", iv=0.001),                     # stage 3
        make("nulliv", iv=None),                     # stage 3
        make("lowoi", oi=5),                         # stage 4
        make("wide", bid=4.0, ask=6.0),              # stage 5: spread 2 > max(0.10, .15*5)
    ]
    passed, rep = apply_filters(contracts, P, TODAY)
    assert [c.contract_symbol for c in passed] == ["ok"]
    assert rep.total == 9 and rep.passed == 1
    assert [(s.label, s.removed) for s in rep.stages] == [
        ("到期日不符", 1), ("報價異常", 3), ("IV 異常", 2),
        ("OI/成交量不足", 1), ("Spread 過寬", 1),
    ]


def test_min_expiry_condition():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       min_days_after=0, min_expiry="2026-11-01")
    passed, _ = apply_filters([make("oct"), make("nov", expiry="2026-11-20")], p, TODAY)
    assert [c.contract_symbol for c in passed] == ["nov"]


def test_spread_floor_admits_tick_bound_cheap_contract():
    # bid .05 / ask .15: spread .10, mid .10; .10 <= max(0.10, .15*.10=.015) -> pass
    passed, _ = apply_filters([make("cheap", bid=0.05, ask=0.15)], P, TODAY)
    assert len(passed) == 1


def test_min_volume_optional_gate():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       min_days_after=45, min_volume=1)
    passed, rep = apply_filters([make("novol", volume=0)], p, TODAY)
    assert passed == [] and rep.stages[3].removed == 1


def test_volume_zero_passes_by_default():
    passed, _ = apply_filters([make("novol", volume=0)], P, TODAY)
    assert len(passed) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_filters.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# option_chaser/filters.py
"""Sequential hard filters with per-stage rejection counts (spec §4)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from .models import AnalysisParams, FilterReport, FilterStageResult, OptionContract


def apply_filters(
    contracts: Iterable[OptionContract], p: AnalysisParams, today: date
) -> tuple[list[OptionContract], FilterReport]:
    target = date.fromisoformat(p.target_date)
    min_expiry_1 = target + timedelta(days=p.min_days_after)
    min_expiry_2 = date.fromisoformat(p.min_expiry) if p.min_expiry else None

    def expiry_ok(c: OptionContract) -> bool:
        e = date.fromisoformat(c.expiry)
        return e >= min_expiry_1 and (min_expiry_2 is None or e >= min_expiry_2)

    def quote_ok(c: OptionContract) -> bool:
        return c.bid is not None and c.ask is not None and c.bid > 0 and c.ask >= c.bid

    def iv_ok(c: OptionContract) -> bool:
        return c.implied_volatility is not None and 0.01 <= c.implied_volatility <= 5.0

    def oi_volume_ok(c: OptionContract) -> bool:
        return c.open_interest >= p.min_oi and c.volume >= p.min_volume

    def spread_ok(c: OptionContract) -> bool:
        mid = (c.bid + c.ask) / 2.0
        return (c.ask - c.bid) <= max(p.spread_floor, p.max_spread_pct * mid)

    stages = (
        ("到期日不符", expiry_ok),
        ("報價異常", quote_ok),
        ("IV 異常", iv_ok),
        ("OI/成交量不足", oi_volume_ok),
        ("Spread 過寬", spread_ok),
    )
    remaining = list(contracts)
    total = len(remaining)
    results: list[FilterStageResult] = []
    for label, pred in stages:
        kept = [c for c in remaining if pred(c)]
        results.append(FilterStageResult(label=label, removed=len(remaining) - len(kept)))
        remaining = kept
    return remaining, FilterReport(total=total, stages=tuple(results), passed=len(remaining))
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_filters.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: five-stage hard filters with FilterReport"
```

---

### Task 8: Ranking (Delta bands, in-band sort, tie-break)

**Files:**
- Create: `option_chaser/ranking.py`, `tests/test_ranking.py`

**Interfaces:**
- Consumes: `valuation.ContractValuation`, `models.AnalysisParams`
- Produces:
  - `ranking.BAND_ORDER = ("conservative", "balanced", "aggressive")`, `ranking.BAND_LABELS = {"conservative": "保守型", "balanced": "平衡型", "aggressive": "積極型"}`
  - `ranking.classify(delta: float, bands: tuple[float, float]) -> str`
  - `ranking.baseline_return(v: ContractValuation) -> float`  — `(baseline_value − mid) / mid`
  - `ranking.rank(valuations: list[ContractValuation], p: AnalysisParams) -> dict[str, list[ContractValuation]]` — keys always all three bands (possibly empty lists), each sorted, truncated to `p.top`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract
from option_chaser.ranking import classify, rank, baseline_return, BAND_ORDER

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=0)


def test_classify_boundaries():
    bands = (0.35, 0.65)
    assert classify(0.34999, bands) == "aggressive"
    assert classify(0.35, bands) == "balanced"      # boundary inclusive to balanced
    assert classify(0.65, bands) == "balanced"      # boundary inclusive to balanced
    assert classify(0.65001, bands) == "conservative"


def make_val(sym, strike, bid, ask, iv, expiry="2026-10-16"):
    c = OptionContract(contract_symbol=sym, strike=strike, expiry=expiry,
                       bid=bid, ask=ask, last=None, volume=10,
                       open_interest=100, implied_volatility=iv)
    return evaluate_contract(c, spot=100.0, today=TODAY, p=P)


def test_rank_sorts_by_baseline_return_and_truncates():
    vals = [
        make_val("otm1", 110.0, 3.0, 3.2, 0.30),
        make_val("otm2", 115.0, 1.5, 1.7, 0.30),
        make_val("otm3", 125.0, 0.4, 0.5, 0.30),
        make_val("otm4", 130.0, 0.2, 0.3, 0.30),
    ]
    p1 = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                        min_days_after=45, delay_days=0, top=3)
    ranked = rank(vals, p1)
    agg = ranked["aggressive"]
    assert len(agg) == 3  # truncated from 4
    rets = [baseline_return(v) for v in agg]
    assert rets == sorted(rets, reverse=True)


def test_empty_band_present_as_empty_list():
    ranked = rank([make_val("otm1", 110.0, 3.0, 3.2, 0.30)], P)
    assert set(ranked.keys()) == set(BAND_ORDER)
    assert ranked["conservative"] == [] and ranked["balanced"] == []


def test_tie_break_total_order():
    # identical baseline return by construction: same strike/iv/quotes, different symbol
    a = make_val("AAA", 110.0, 3.0, 3.2, 0.30)
    b = make_val("BBB", 110.0, 3.0, 3.2, 0.30)
    ranked = rank([b, a], P)
    syms = [v.contract.contract_symbol for v in ranked["aggressive"]]
    assert syms == ["AAA", "BBB"]  # lexicographic contract_symbol as final key
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# option_chaser/ranking.py
"""Delta banding and in-band ranking (spec §6). No custom weights."""
from __future__ import annotations

from .models import AnalysisParams
from .valuation import ContractValuation

BAND_CONSERVATIVE = "conservative"
BAND_BALANCED = "balanced"
BAND_AGGRESSIVE = "aggressive"
BAND_ORDER = (BAND_CONSERVATIVE, BAND_BALANCED, BAND_AGGRESSIVE)
BAND_LABELS = {
    BAND_CONSERVATIVE: "保守型",
    BAND_BALANCED: "平衡型",
    BAND_AGGRESSIVE: "積極型",
}


def classify(delta: float, bands: tuple[float, float]) -> str:
    a, b = bands
    if delta > b:
        return BAND_CONSERVATIVE
    if delta < a:
        return BAND_AGGRESSIVE
    return BAND_BALANCED


def baseline_return(v: ContractValuation) -> float:
    return (v.baseline_value - v.mid) / v.mid


def _tie_break_key(v: ContractValuation) -> tuple:
    return (v.spread / v.mid, v.contract.strike, v.contract.expiry,
            v.contract.contract_symbol)


def rank(
    valuations: list[ContractValuation], p: AnalysisParams
) -> dict[str, list[ContractValuation]]:
    bands: dict[str, list[ContractValuation]] = {name: [] for name in BAND_ORDER}
    for v in valuations:
        bands[classify(v.delta, p.delta_bands)].append(v)
    for name in BAND_ORDER:
        bands[name].sort(key=lambda v: (-baseline_return(v), *_tie_break_key(v)))
        bands[name] = bands[name][: p.top]
    return bands
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: delta-band classification and deterministic in-band ranking"
```

---

### Task 9: Recommendation reasons (deterministic templates)

**Files:**
- Modify: `option_chaser/ranking.py`
- Create: `tests/test_reasons.py`

**Interfaces:**
- Consumes: `ContractValuation`, `rank()` output, `guidance_judgments`
- Produces: `ranking.build_reasons(v, band: str, ranked: dict, spot: float, n_qualified: int, p: AnalysisParams) -> tuple[list[str], list[str]]` — (pros, cons). Cons include guidance judgment sentences (spec §6.3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reasons.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_contract
from option_chaser.ranking import rank, build_reasons

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   min_days_after=45, delay_days=0)


def make_val(sym, strike, bid, ask, iv, expiry="2026-11-20"):
    c = OptionContract(contract_symbol=sym, strike=strike, expiry=expiry,
                       bid=bid, ask=ask, last=None, volume=10,
                       open_interest=100, implied_volatility=iv)
    return evaluate_contract(c, spot=100.0, today=TODAY, p=P)


def setup_ranked():
    vals = [
        make_val("cons", 90.0, 13.0, 13.4, 0.34),          # conservative
        make_val("bal", 105.0, 5.3, 5.5, 0.36, "2026-10-16"),  # balanced
        make_val("aggr", 110.0, 3.0, 3.25, 0.30, "2026-10-16"),  # aggressive
    ]
    return vals, rank(vals, P)


def test_conservative_pro_mentions_breakeven():
    vals, ranked = setup_ranked()
    pros, _ = build_reasons(ranked["conservative"][0], "conservative",
                            ranked, 100.0, 3, P)
    assert any("breakeven" in s for s in pros)


def test_aggressive_pro_top_return_claim():
    vals, ranked = setup_ranked()
    pros, _ = build_reasons(ranked["aggressive"][0], "aggressive",
                            ranked, 100.0, 3, P)
    # aggr has the highest baseline return of the three -> global-top sentence
    assert any("基準情境報酬率最高" in s for s in pros)


def test_low_delta_con_total_loss_warning():
    vals, ranked = setup_ranked()
    _, cons = build_reasons(ranked["aggressive"][0], "aggressive",
                            ranked, 100.0, 3, P)
    assert any("權利金可能全損" in s for s in cons)


def test_max_cost_con_on_most_expensive_first_pick():
    vals, ranked = setup_ranked()
    _, cons = build_reasons(ranked["conservative"][0], "conservative",
                            ranked, 100.0, 3, P)
    assert any("本金需求最大" in s for s in cons)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_reasons.py -v`
Expected: FAIL — `ImportError: build_reasons`

- [ ] **Step 3: Implement** (append to `ranking.py`)

```python
from .valuation import guidance_judgments


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_reasons(
    v: ContractValuation,
    band: str,
    ranked: dict[str, list[ContractValuation]],
    spot: float,
    n_qualified: int,
    p: AnalysisParams,
) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []

    all_ranked = [x for lst in ranked.values() for x in lst]
    max_ret = max(baseline_return(x) for x in all_ranked) if all_ranked else 0.0

    if band == BAND_CONSERVATIVE:
        s = f"breakeven 僅高於現價 {_pct(v.breakeven_vs_spot)}"
        if v.stress_half > v.mid:
            s += "，劇本半對仍獲利"
        pros.append(s)
    elif band == BAND_BALANCED:
        intrinsic_now = max(spot - v.contract.strike, 0.0)
        pros.append(
            f"內在價值佔權利金 {_pct(intrinsic_now / v.mid)}，時間價值負擔適中"
        )
    else:  # aggressive
        if baseline_return(v) == max_ret:
            pros.append(f"{n_qualified} 張合格合約中基準情境報酬率最高")
        else:
            pros.append(
                f"基準情境報酬率 {_pct(baseline_return(v))}，同級距中排名靠前"
            )

    if v.delta < 0.5:
        cons.append(
            f"若完全不漲權利金可能全損（最大虧損 ${v.mid * 100:.2f}/張）"
        )
    first_picks = [lst[0] for lst in ranked.values() if lst]
    if first_picks and v is max(first_picks, key=lambda x: x.mid):
        cons.append(f"本金需求最大（${v.mid * 100:.2f}/張）")
    # spread warning: same structure as the §4 hard filter, relative part scaled 2/3
    if v.spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * v.mid):
        cons.append("買賣價差偏大")
    cons.extend(guidance_judgments(v, p))
    return pros, cons
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_reasons.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: deterministic pro/con recommendation templates"
```

---

### Task 10: yfinance adapter (offline mapping + cleaning rules)

**Files:**
- Create: `option_chaser/data/yf.py`, `tests/test_yf_adapter.py`, `tests/fixtures/yf_rows.json`

**Interfaces:**
- Produces:
  - `data.yf.map_rows(symbol: str, spot: float, fetched_at: str, rows: list[dict]) -> ChainSnapshot` — pure, testable; applies spec §2.3 cleaning table. Each row dict uses yfinance column names: `contractSymbol, strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility`, plus `expiry` (YYYY-MM-DD) added by the fetch loop.
  - `data.yf.fetch_chain(symbol: str) -> ChainSnapshot` — network; imports `yfinance` lazily; raises `FetchError` on any failure; `fetched_at` = now(UTC) ISO.

- [ ] **Step 1: Write fixture + failing tests**

`tests/fixtures/yf_rows.json`:
```json
[
  {"contractSymbol": "XYZ261016C00110000", "expiry": "2026-10-16", "strike": 110.0,
   "bid": 3.0, "ask": 3.25, "lastPrice": 3.1, "volume": 152, "openInterest": 830,
   "impliedVolatility": 0.38},
  {"contractSymbol": "XYZ261016C00115000", "expiry": "2026-10-16", "strike": 115.0,
   "bid": NaN, "ask": 2.0, "lastPrice": NaN, "volume": NaN, "openInterest": NaN,
   "impliedVolatility": NaN},
  {"contractSymbol": "XYZ261016C00120000", "expiry": "2026-10-16", "strike": 120.0,
   "bid": 1.0, "ask": 1.2, "volume": 3, "openInterest": 55,
   "impliedVolatility": 0.41}
]
```
(Note: `NaN` is valid in Python's `json.loads` by default; the third row omits `lastPrice` entirely to cover the missing-key case.)

```python
# tests/test_yf_adapter.py
import json
from pathlib import Path
from option_chaser.data.yf import map_rows

FIXTURE = Path(__file__).parent / "fixtures" / "yf_rows.json"


def test_mapping_and_cleaning():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snap = map_rows("XYZ", 100.0, "2026-07-15T21:30:00-04:00", rows)
    assert snap.symbol == "XYZ" and snap.spot == 100.0 and snap.source == "yfinance"
    c0, c1, c2 = snap.contracts
    # clean row maps verbatim
    assert c0.bid == 3.0 and c0.volume == 152 and c0.implied_volatility == 0.38
    # NaN bid -> None; NaN volume/openInterest -> 0; NaN lastPrice -> None
    assert c1.bid is None and c1.last is None
    assert c1.volume == 0 and c1.open_interest == 0
    assert c1.implied_volatility is None
    # missing lastPrice key -> None
    assert c2.last is None and c2.bid == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_yf_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# option_chaser/data/yf.py
"""yfinance adapter: the only networked module. Cleaning rules per spec §2.3."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..models import SCHEMA_VERSION, ChainSnapshot, FetchError, OptionContract


def _clean_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _clean_count(value) -> int:
    f = _clean_float(value)
    return 0 if f is None else int(f)


def map_rows(
    symbol: str, spot: float, fetched_at: str, rows: list[dict]
) -> ChainSnapshot:
    contracts = tuple(
        OptionContract(
            contract_symbol=str(r["contractSymbol"]),
            strike=float(r["strike"]),
            expiry=str(r["expiry"]),
            bid=_clean_float(r.get("bid")),
            ask=_clean_float(r.get("ask")),
            last=_clean_float(r.get("lastPrice")),
            volume=_clean_count(r.get("volume")),
            open_interest=_clean_count(r.get("openInterest")),
            implied_volatility=_clean_float(r.get("impliedVolatility")),
        )
        for r in rows
    )
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol=symbol, fetched_at=fetched_at,
        spot=spot, source="yfinance", contracts=contracts,
    )


def fetch_chain(symbol: str) -> ChainSnapshot:
    try:
        import yfinance as yf  # lazy: tests never import the network stack

        t = yf.Ticker(symbol)
        spot = float(t.fast_info["last_price"])
        rows: list[dict] = []
        for expiry in t.options:
            calls = t.option_chain(expiry).calls
            for r in calls.to_dict("records"):
                r["expiry"] = expiry
                rows.append(r)
    except Exception as e:  # noqa: BLE001 — any yfinance failure is a fetch failure
        raise FetchError(f"yfinance 抓取失敗（{symbol}）: {e}") from e
    if not rows or spot <= 0 or math.isnan(spot):
        raise FetchError(f"yfinance 回傳資料不足（{symbol}）：無現價或無合約")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return map_rows(symbol, spot, fetched_at, rows)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_yf_adapter.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: yfinance adapter with deterministic NaN/missing cleaning"
```

---

### Task 11: CLI param resolution & validation

**Files:**
- Create: `option_chaser/cli.py`, `tests/test_cli_validation.py`

**Interfaces:**
- Consumes: `models.AnalysisParams`, `models.ParamError`
- Produces:
  - `cli.build_parser() -> argparse.ArgumentParser` — flags exactly per spec §3
  - `cli.effective_buffer(min_days_after: int, min_expiry: str | None, target_date: str) -> int`
  - `cli.resolve_params(args: argparse.Namespace) -> AnalysisParams` — normalizes iv_shifts (force-include 0, dedupe, sort), resolves delay_days default `(eb+1)//2`, validates all static rules; raises `ParamError`
  - `cli.validate_scenario(p: AnalysisParams, spot: float, today: date) -> None` — target_date > today; target_price > spot unless `force`; raises `ParamError`
  - `cli.main(argv: list[str] | None = None) -> int` — wired fully in Task 12

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_validation.py
from datetime import date
import pytest
from option_chaser.models import ParamError
from option_chaser.cli import build_parser, resolve_params, validate_scenario, effective_buffer


def parse(*extra):
    argv = ["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
            "--snapshot", "dummy.json"] + list(extra)
    return build_parser().parse_args(argv)


def test_effective_buffer_paths():
    assert effective_buffer(45, None, "2026-08-28") == 45
    assert effective_buffer(0, "2026-10-12", "2026-08-28") == 45
    assert effective_buffer(10, "2026-10-12", "2026-08-28") == 45  # max of both
    assert effective_buffer(50, "2026-10-12", "2026-08-28") == 50
    assert effective_buffer(0, "2026-08-01", "2026-08-28") == 0    # earlier than target -> 0


def test_delay_default_from_effective_buffer():
    p = resolve_params(parse("--min-days-after", "45"))
    assert p.delay_days == 23  # ceil(45/2)
    p2 = resolve_params(parse("--min-expiry", "2026-10-12"))
    assert p2.delay_days == 23  # min-expiry path also enables delay stress


def test_delay_exceeding_buffer_rejected():
    with pytest.raises(ParamError):
        resolve_params(parse("--min-days-after", "10", "--delay-days", "11"))


def test_iv_shifts_normalized():
    p = resolve_params(parse("--iv-shifts", "0.2,-0.2"))
    assert p.iv_shifts == (-0.2, 0.0, 0.2)  # 0 injected, sorted


def test_iv_shift_multiplier_must_be_positive():
    with pytest.raises(ParamError):
        resolve_params(parse("--iv-shifts", "-1.0,0"))


def test_delta_bands_validation():
    with pytest.raises(ParamError):
        resolve_params(parse("--delta-bands", "0.65,0.35"))
    with pytest.raises(ParamError):
        resolve_params(parse("--delta-bands", "0,0.5"))


def test_min_return_negative_rejected():
    with pytest.raises(ParamError):
        resolve_params(parse("--min-return", "-0.1"))


def test_scenario_target_below_spot_needs_force():
    p = resolve_params(parse())
    with pytest.raises(ParamError):
        validate_scenario(p, spot=130.0, today=date(2026, 7, 15))
    pf = resolve_params(parse("--force"))
    validate_scenario(pf, spot=130.0, today=date(2026, 7, 15))  # no raise


def test_scenario_target_date_must_be_future():
    p = resolve_params(parse())
    with pytest.raises(ParamError):
        validate_scenario(p, spot=100.0, today=date(2026, 8, 28))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cli_validation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# option_chaser/cli.py
"""CLI entry point: arg parsing, validation, orchestration (spec §3, §8)."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .models import AnalysisParams, ParamError


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="option-chaser",
        description="Long Call scenario optimizer（確定性計算，非投資建議）",
    )
    ap.add_argument("symbol")
    ap.add_argument("--target-price", type=float, required=True)
    ap.add_argument("--target-date", required=True)
    ap.add_argument("--min-days-after", type=int, default=0)
    ap.add_argument("--min-expiry", default=None)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--iv-shifts", default="-0.2,0,0.2")
    ap.add_argument("--rate", type=float, default=0.04)
    ap.add_argument("--min-oi", type=int, default=10)
    ap.add_argument("--min-volume", type=int, default=0)
    ap.add_argument("--max-spread-pct", type=float, default=0.15)
    ap.add_argument("--spread-floor", type=float, default=0.10)
    ap.add_argument("--delta-bands", default="0.35,0.65")
    ap.add_argument("--min-return", type=float, default=0.0)
    ap.add_argument("--delay-days", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--md", default=None)
    return ap


def _parse_iso(name: str, s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ParamError(f"{name} 必須為 YYYY-MM-DD：{s!r}") from None


def effective_buffer(min_days_after: int, min_expiry: str | None, target_date: str) -> int:
    """Spec §3: max(min_days_after, max(0, min_expiry - target_date))."""
    via_expiry = 0
    if min_expiry:
        via_expiry = max(
            0, (_parse_iso("--min-expiry", min_expiry) - _parse_iso("--target-date", target_date)).days
        )
    return max(min_days_after, via_expiry)


def resolve_params(args: argparse.Namespace) -> AnalysisParams:
    if args.target_price <= 0:
        raise ParamError("--target-price 必須 > 0")
    _parse_iso("--target-date", args.target_date)
    if args.min_days_after < 0:
        raise ParamError("--min-days-after 必須 >= 0")
    if args.min_expiry:
        _parse_iso("--min-expiry", args.min_expiry)
    if not 1 <= args.top <= 10:
        raise ParamError("--top 必須在 1–10")
    if args.rate < 0:
        raise ParamError("--rate 必須 >= 0")
    if args.min_oi < 0 or args.min_volume < 0:
        raise ParamError("--min-oi / --min-volume 必須 >= 0")
    if args.max_spread_pct <= 0:
        raise ParamError("--max-spread-pct 必須 > 0")
    if args.spread_floor < 0:
        raise ParamError("--spread-floor 必須 >= 0")
    if args.min_return < 0:
        raise ParamError("--min-return 必須 >= 0")

    try:
        shifts = [float(x) for x in args.iv_shifts.split(",") if x.strip() != ""]
    except ValueError:
        raise ParamError(f"--iv-shifts 解析失敗：{args.iv_shifts!r}") from None
    if any(1.0 + s <= 0 for s in shifts):
        raise ParamError("--iv-shifts 每個乘數 1+shift 必須 > 0")
    if 0.0 not in shifts:
        shifts.append(0.0)  # baseline scenario is mandatory (spec §3)
    iv_shifts = tuple(sorted(set(shifts)))

    try:
        a, b = (float(x) for x in args.delta_bands.split(","))
    except ValueError:
        raise ParamError(f"--delta-bands 解析失敗：{args.delta_bands!r}") from None
    if not (0.0 < a < b < 1.0):
        raise ParamError("--delta-bands 需滿足 0 < a < b < 1")

    eb = effective_buffer(args.min_days_after, args.min_expiry, args.target_date)
    delay = args.delay_days if args.delay_days is not None else (eb + 1) // 2
    if not 0 <= delay <= eb:
        raise ParamError(f"--delay-days 必須在 0–{eb}（有效緩衝天數）")

    return AnalysisParams(
        target_price=args.target_price, target_date=args.target_date,
        min_days_after=args.min_days_after, min_expiry=args.min_expiry,
        top=args.top, iv_shifts=iv_shifts, rate=args.rate,
        min_oi=args.min_oi, min_volume=args.min_volume,
        max_spread_pct=args.max_spread_pct, spread_floor=args.spread_floor,
        delta_bands=(a, b), min_return=args.min_return,
        delay_days=delay, force=args.force,
    )


def validate_scenario(p: AnalysisParams, spot: float, today: date) -> None:
    if date.fromisoformat(p.target_date) <= today:
        raise ParamError(f"--target-date 必須晚於資料日 {today.isoformat()}")
    if p.target_price <= spot and not p.force:
        raise ParamError(
            f"Long Call 劇本目標價 {p.target_price} 低於現價 {spot}；"
            "確定要跑請加 --force"
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_cli_validation.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: cli params, effective-buffer resolution, validation"
```

---

### Task 12: Report rendering + CLI wiring + golden test

**Files:**
- Create: `option_chaser/report.py`, `tests/fixtures/xyz_snapshot.json`, `tests/test_golden.py`, `tests/fixtures/golden_report.txt` (generated in Step 4)
- Modify: `option_chaser/cli.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `report.render(snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport, ranked: dict[str, list[ContractValuation]], n_qualified: int, today: date) -> str`
  - `report.render_filter_only(snap, p, freport, today) -> str` (zero-qualified path)
  - `cli.main(argv=None) -> int` — exit 0 success / 1 fetch-or-empty / 2 param error

- [ ] **Step 1: Write the golden fixture**

`tests/fixtures/xyz_snapshot.json` — 10 contracts: 5 qualify (1 conservative C90, 2 balanced C105+C95, 2 aggressive C110[vol=0]+C130[tick-bound]), 5 rejected (one per filter stage). Params used by the golden test: `--target-price 120 --target-date 2026-08-28 --min-days-after 45 --top 3`, everything else default.

```json
{
  "schema_version": 1,
  "symbol": "XYZ",
  "fetched_at": "2026-07-15T21:30:00-04:00",
  "spot": 100.0,
  "source": "yfinance",
  "contracts": [
    {"contract_symbol": "XYZ261120C00090000", "strike": 90.0, "expiry": "2026-11-20",
     "bid": 13.0, "ask": 13.4, "last": 13.2, "volume": 120, "open_interest": 500,
     "implied_volatility": 0.34},
    {"contract_symbol": "XYZ261016C00105000", "strike": 105.0, "expiry": "2026-10-16",
     "bid": 5.3, "ask": 5.5, "last": 5.4, "volume": 80, "open_interest": 300,
     "implied_volatility": 0.36},
    {"contract_symbol": "XYZ261016C00095000", "strike": 95.0, "expiry": "2026-10-16",
     "bid": 30.6, "ask": 31.0, "last": 30.8, "volume": 5, "open_interest": 40,
     "implied_volatility": 0.9},
    {"contract_symbol": "XYZ261016C00110000", "strike": 110.0, "expiry": "2026-10-16",
     "bid": 3.0, "ask": 3.25, "last": 3.1, "volume": 0, "open_interest": 830,
     "implied_volatility": 0.30},
    {"contract_symbol": "XYZ261016C00130000", "strike": 130.0, "expiry": "2026-10-16",
     "bid": 0.05, "ask": 0.15, "last": 0.1, "volume": 3, "open_interest": 50,
     "implied_volatility": 0.45},
    {"contract_symbol": "XYZ260918C00100000", "strike": 100.0, "expiry": "2026-09-18",
     "bid": 5.0, "ask": 5.3, "last": 5.1, "volume": 10, "open_interest": 100,
     "implied_volatility": 0.35},
    {"contract_symbol": "XYZ261016C00100000", "strike": 100.0, "expiry": "2026-10-16",
     "bid": 0.0, "ask": 0.5, "last": null, "volume": 10, "open_interest": 100,
     "implied_volatility": 0.35},
    {"contract_symbol": "XYZ261120C00100000", "strike": 100.0, "expiry": "2026-11-20",
     "bid": 5.0, "ask": 5.5, "last": null, "volume": 10, "open_interest": 100,
     "implied_volatility": 0.001},
    {"contract_symbol": "XYZ261016C00100500", "strike": 100.5, "expiry": "2026-10-16",
     "bid": 5.0, "ask": 5.4, "last": null, "volume": 10, "open_interest": 5,
     "implied_volatility": 0.35},
    {"contract_symbol": "XYZ261016C00102000", "strike": 102.0, "expiry": "2026-10-16",
     "bid": 4.0, "ask": 6.0, "last": null, "volume": 10, "open_interest": 100,
     "implied_volatility": 0.35}
  ]
}
```

Expected filter outcome: total 10 → 到期日不符 1 → 報價異常 1 → IV 異常 1 → OI/成交量不足 1 → Spread 過寬 1 → 合格 5. Bands: conservative [C90], balanced [C105 then C95], aggressive [C130 then C110] — C130's mid is $0.10 so its baseline return (~+4000%) is the global maximum and it sorts first in the aggressive band (and receives the "基準情境報酬率最高" pro sentence). C95 triggers all three ceiling judgments (ask 31.0 > baseline≈30.3); C110 carries the volume-freshness warning; C130 passes the spread filter only via the absolute floor.

- [ ] **Step 2: Implement report.py**

```python
# option_chaser/report.py
"""Deterministic plain-text report (spec §7). No box-drawing characters."""
from __future__ import annotations

from datetime import date

from .models import AnalysisParams, ChainSnapshot, FilterReport
from .ranking import BAND_LABELS, BAND_ORDER, baseline_return, build_reasons
from .valuation import ContractValuation, guidance_judgments


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _shift_name(shift: float) -> str:
    return "IV 不變" if shift == 0.0 else f"IV {shift * 100:+g}%"


def _val_line(name: str, val: float, cost: float) -> str:
    """spec §7: each scenario line = 估值 + 損益 + 報酬率 (per-share and per-contract)."""
    pnl = val - cost
    return (
        f"- {name}: ${_money(val)}（${val * 100:.0f}/張）"
        f"損益 {pnl:+.2f}（{pnl * 100:+.0f}/張）-> {_pct(pnl / cost)}"
    )


def _header_lines(snap: ChainSnapshot, p: AnalysisParams, today: date) -> list[str]:
    bands = p.delta_bands
    return [
        "OPTION CHASER 報告",
        "",
        "[使用者假設]",
        f"- 劇本: {p.target_date} 到達 ${_money(p.target_price)}",
        f"- 限制: 到期日 >= 劇本日 + {p.min_days_after} 天"
        + (f"; 到期日 >= {p.min_expiry}" if p.min_expiry else ""),
        f"- 最低要求報酬率: {_pct(p.min_return)}",
        "",
        "[市場資料]",
        f"- 資料時間: {snap.fetched_at}（來源 {snap.source}，可能延遲）",
        f"- {snap.symbol} 現價: ${_money(snap.spot)}（分析基準日 {today.isoformat()}）",
        "",
        "[模型假設]",
        f"- 無風險利率 {_pct(p.rate)}、無股利調整、Black-Scholes 歐式近似",
        f"- IV 情境: {', '.join(_shift_name(s) for s in p.iv_shifts)}",
        f"- Delta 分級門檻: {bands[0]:g} / {bands[1]:g}（實務慣例級距）",
        f"- 延遲壓力情境: {p.delay_days} 天" if p.delay_days > 0
        else "- 延遲壓力情境: 未啟用（delay-days=0）",
    ]


def _filter_lines(freport: FilterReport) -> list[str]:
    lines = ["", "[過濾統計]", f"- 全部 Long Call: {freport.total} 張"]
    for s in freport.stages:
        lines.append(f"- {s.label}刷掉: {s.removed}")
    lines.append(f"- 合格: {freport.passed} 張")
    return lines


def _candidate_lines(
    v: ContractValuation, idx: int, band: str,
    ranked: dict[str, list[ContractValuation]],
    snap: ChainSnapshot, n_qualified: int, p: AnalysisParams,
) -> list[str]:
    c = v.contract
    lines = [
        "",
        f"{idx}) {BAND_LABELS[band]}: Strike ${_money(c.strike)} / {c.expiry} 到期",
        f"- 現在買入: Bid ${_money(c.bid)}（${c.bid * 100:.0f}/張）"
        f" / Mid ${_money(v.mid)}（${v.mid * 100:.0f}/張）"
        f" / Ask ${_money(c.ask)}（${c.ask * 100:.0f}/張）IV {_pct_iv(c.implied_volatility)}",
        f"- Delta {v.delta:.2f} / Theta {v.theta_per_day:.3f}每天 / Vega {v.vega_per_pct:.2f}",
        f"- Breakeven: ${_money(v.breakeven)}（高於現價 {_pct(v.breakeven_vs_spot)}；"
        f"對目標價緩衝 {_pct(v.breakeven_vs_target)}）",
        f"- Lambda 有效槓桿: {v.effective_leverage:.1f}x",
    ]
    if c.volume == 0:
        lines.append("- 警示: 今日無成交，報價新鮮度存疑")
    lines.append("")
    lines.append("劇本成立時:")
    lines.append(_val_line("保守底線", v.floor_value, v.mid))
    for shift, val in v.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, v.mid))
    lines.append(
        f"- 最差進場（Ask）基準報酬率: {_pct((v.baseline_value - c.ask) / c.ask)}"
    )
    lines.append("")
    lines.append("壓力測試（純顯示，不參與排名）:")
    lines.append(_val_line("半程", v.stress_half, v.mid))
    if v.stress_delay is not None:
        lines.append(_val_line(f"延遲 {p.delay_days} 天", v.stress_delay, v.mid))
    lines.append(_val_line("全錯", v.stress_flat, v.mid))
    lines.append("")
    lines.append("買價指引:")
    lines.append(f"- L1 硬上限（劇本內在價值）: ${_money(v.l1)}（${v.l1 * 100:.0f}/張）")
    lines.append(f"- L2 保守上限（最保守 IV 情境）: ${_money(v.l2)}（${v.l2 * 100:.0f}/張）")
    lines.append(
        f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: "
        f"${_money(v.l3)}（${v.l3 * 100:.0f}/張）"
    )
    judgments = guidance_judgments(v, p)
    if judgments:
        for m in judgments:
            lines.append(f"- 警示: {m}")
    else:
        lines.append("- 目前 Ask 低於全部三層天花板")
    pros, cons = build_reasons(v, band, ranked, snap.spot, n_qualified, p)
    lines.append("")
    lines.append("評語:")
    for s in pros:
        lines.append(f"- 優點: {s}")
    for s in cons:
        lines.append(f"- 代價: {s}")
    return lines


def _pct_iv(iv: float) -> str:
    return f"{iv * 100:.0f}%"


def _footer_lines(p: AnalysisParams) -> list[str]:
    return [
        "",
        "[尾註]",
        "- 估值: Black-Scholes 歐式 call，N(x) = 0.5*(1+erf(x/sqrt(2)))，T = 日曆日/365",
        "- T <= 0 時以內在價值 max(S-K, 0) 取代 BS",
        "- 保守底線 = max(目標價 - Strike, 0)（無套利下限）",
        "- IV 情境: sigma' = sigma * (1 + shift)",
        "- 買價天花板: L1 = max(目標價-Strike, 0); L2 = BS(最保守 IV 情境); L3 = 基準估值/(1+min-return)",
        "- Breakeven = Strike + Mid（到期持有觀點，提前平倉不適用）",
        "- Lambda = Delta * 現價 / Mid（低權利金合約會放大，僅供量級參考）",
        f"- 過濾: 到期日 / 報價 / IV(0.01-5.0) / OI>={p.min_oi} 且 Vol>={p.min_volume} / "
        f"Spread <= max({p.spread_floor:g}, {p.max_spread_pct:g}*Mid)",
        "- 排名: Delta 分級（實務慣例），級內以基準情境報酬率（Mid 進場）排序",
        "- 模型限制: 無股利調整（q=0）、歐式近似、IV 乘法情境",
        "- 免責: 模型估計非保證價格，不構成投資建議",
    ]


def render_filter_only(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport, today: date
) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport)
    lines += ["", "過濾後無合格合約，不產生推薦。", ""]
    return "\n".join(lines)


def render(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport,
    ranked: dict[str, list[ContractValuation]], n_qualified: int, today: date,
) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport)
    idx = 0
    for band in BAND_ORDER:
        lines.append("")
        lines.append(f"=== {BAND_LABELS[band]}（{_band_range(band, p)}） ===")
        if not ranked[band]:
            lines.append("- 此級距無合格合約")
            continue
        for v in ranked[band]:
            idx += 1
            lines += _candidate_lines(v, idx, band, ranked, snap, n_qualified, p)
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)


def _band_range(band: str, p: AnalysisParams) -> str:
    a, b = p.delta_bands
    if band == "conservative":
        return f"Delta > {b:g}"
    if band == "aggressive":
        return f"Delta < {a:g}"
    return f"Delta {a:g}-{b:g}"
```

- [ ] **Step 3: Wire cli.main** (append to `cli.py`)

```python
from .data.snapshot import load_snapshot, save_snapshot, snapshot_today
from .filters import apply_filters
from .models import FetchError, SnapshotSchemaError
from .ranking import rank
from .report import render, render_filter_only
from .valuation import evaluate_contract

USAGE_HINT = "用法示例: option-chaser XYZ --target-price 120 --target-date 2026-08-28 --min-days-after 45"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        p = resolve_params(args)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        print(USAGE_HINT)
        return 2

    try:
        if args.snapshot:
            snap = load_snapshot(args.snapshot)
        else:
            from .data.yf import fetch_chain  # lazy: offline runs never import yfinance

            snap = fetch_chain(args.symbol)
            out = Path("snapshots") / f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.json"
            out.parent.mkdir(exist_ok=True)
            save_snapshot(snap, out)
    except (FetchError, SnapshotSchemaError, OSError) as e:
        print(f"資料錯誤: {e}")
        return 1

    today = snapshot_today(snap.fetched_at)
    try:
        validate_scenario(p, snap.spot, today)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        return 2

    qualified, freport = apply_filters(snap.contracts, p, today)
    if not qualified:
        print(render_filter_only(snap, p, freport, today))
        return 1

    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    ranked = rank(vals, p)
    text = render(snap, p, freport, ranked, n_qualified=len(qualified), today=today)
    print(text, end="")  # render() already ends with \n; keep stdout == --md content
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    return 0
```

- [ ] **Step 4: Generate + eyeball + freeze the golden file**

Run:
```bash
python -c "
from option_chaser.cli import main
import sys, io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = main(['XYZ','--target-price','120','--target-date','2026-08-28',
               '--min-days-after','45','--snapshot','tests/fixtures/xyz_snapshot.json'])
assert rc == 0, rc
open('tests/fixtures/golden_report.txt','w',encoding='utf-8',newline='').write(buf.getvalue())
print('written')
"
```

Then MANUALLY verify `tests/fixtures/golden_report.txt` against this checklist before committing (this is the one human-judgment step):
- 過濾統計 reads: 10 total; each of the 5 stages removed exactly 1; 合格 5.
- 保守型 has 1 candidate (Strike $90.00), 平衡型 2 (C105 first — higher baseline return than C95), 積極型 2 (C130 first — highest baseline return globally, then C110).
- C95 candidate shows all three 買價指引 warning sentences.
- C110 candidate shows the volume-freshness warning line.
- Every candidate's buy line shows Bid / Mid / Ask each with per-contract（$X/張）amounts; every 保守底線/IV情境/壓力測試 line shows 估值 + 損益（含/張）+ 報酬率; L1/L2/L3 carry（$X/張）.
- No box-drawing characters anywhere; footer lists formulas and the disclaimer.

- [ ] **Step 5: Write the golden + determinism test**

```python
# tests/test_golden.py
import io
import contextlib
from pathlib import Path
from option_chaser.cli import main

FIX = Path(__file__).parent / "fixtures"
ARGS = ["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
        "--min-days-after", "45", "--snapshot", str(FIX / "xyz_snapshot.json")]


def run_capture():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(ARGS)
    return rc, buf.getvalue()


def test_golden_report_byte_identical():
    rc, out = run_capture()
    assert rc == 0
    assert out == (FIX / "golden_report.txt").read_text(encoding="utf-8")


def test_repeat_run_is_deterministic():
    _, a = run_capture()
    _, b = run_capture()
    assert a == b


def test_no_box_drawing_characters():
    _, out = run_capture()
    assert not any(0x2500 <= ord(ch) <= 0x257F for ch in out)


def test_report_shows_bid_pnl_and_per_contract_amounts():
    # spec §7: bid/ask/mid visible; scenario lines carry 估值+損益+報酬率;
    # per-share and per-contract (x100) side by side
    _, out = run_capture()
    assert "Bid $" in out
    assert "/張）" in out
    assert "損益 " in out


def test_zero_qualified_exit_code(tmp_path):
    rc, out = None, None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
                   "--min-days-after", "3650",
                   "--snapshot", str(FIX / "xyz_snapshot.json")])
    assert rc == 1
    assert "無合格合約" in buf.getvalue()


def test_md_output(tmp_path):
    md = tmp_path / "r.md"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(ARGS + ["--md", str(md)])
    assert rc == 0
    assert md.read_text(encoding="utf-8") == buf.getvalue()
```

- [ ] **Step 6: Run full suite**

Run: `python -m pytest -v`
Expected: all tests pass (≈40)

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: report rendering, cli wiring, golden determinism test"
```

---

### Task 13: README + final verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# Option Chaser

Long Call scenario optimizer. Given YOUR scenario (target price + target date),
it scans the current option chain, filters for tradeability, valuates every
qualifying Long Call with Black-Scholes under your scenario, bands candidates
by Delta (conservative / balanced / aggressive), and prints a deterministic
plain-text report with price-ceiling guidance.

It does NOT predict stocks, judge your scenario, estimate probabilities, or
give investment advice. Same snapshot + same params = byte-identical output.

## Install

    pip install -e .

## Run (online; saves a snapshot under snapshots/)

    option-chaser NVDA --target-price 220 --target-date 2026-09-30 --min-days-after 45

## Re-run offline from a snapshot

    option-chaser NVDA --target-price 220 --target-date 2026-09-30 \
        --min-days-after 45 --snapshot snapshots/NVDA_xxxx.json

## Key flags

    --min-days-after N    expiry must be >= target-date + N days (hard gate)
    --min-expiry DATE     absolute expiry floor
    --iv-shifts CSV       IV scenarios, default -0.2,0,0.2 (0 always included)
    --min-return X        L3 price ceiling = baseline value / (1+X)
    --max-spread-pct / --spread-floor / --min-oi / --min-volume   tradeability gates
    --delta-bands A,B     banding thresholds, default 0.35,0.65
    --md PATH             also write the report to a file

## Tests (all offline)

    python -m pytest

Spec: docs/superpowers/specs/2026-07-15-option-chaser-mvp-design.md
```

- [ ] **Step 2: Manual smoke test (network; optional but recommended)**

Run: `option-chaser AAPL --target-price 260 --target-date 2026-09-30 --min-days-after 30`
Expected: a report prints; a snapshot JSON appears under `snapshots/`. If the market is closed, quotes may be stale — that's fine for a smoke test. (If this fails due to yfinance/network, note it and continue — mapping logic is covered by offline tests.)

- [ ] **Step 3: Full suite one last time**

Run: `python -m pytest`
Expected: all pass

- [ ] **Step 4: Commit and push**

```bash
git add -A && git commit -m "docs: README with usage and flag reference"
git push
```

---

## Self-Review Notes (author-checked before finalizing)

- Spec coverage: §2 module layout → Tasks 1–12; §3 params/validation → Task 11; §4 five filters + freshness warning → Tasks 7, 12; §5.1–5.5 → Tasks 3–5; §5.6 → Task 5; §5.7 → Tasks 5–6; §6 banding/ranking/reasons → Tasks 8–9; §7 report → Task 12; §8 error/determinism → Tasks 2, 11, 12 (exit codes 0/1/2, snapshot-derived today, byte-identical golden); §9 tests #1–10 → Tasks 3,4,7,8,5+6,5,12,11,2,10 respectively; §10 future scope → none (YAGNI); §11 acceptance → golden fixture mirrors the XYZ case.
- Type consistency: `ContractValuation` field names used in ranking/report match Task 5 definition; `AnalysisParams` fields match Task 2; stage labels in filters/tests/report identical strings.
- Determinism: only `data/yf.py` reads the clock/network; golden test enforces byte-identity; report avoids dict-iteration nondeterminism by iterating `BAND_ORDER` and sorted scenario tuples.
```

<!-- codex-peer-reviewed: 2026-07-17T04:27:18Z rounds=3 verdict=approved -->
