# Option Chaser v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Option Chaser to four debit strategies (long-call / long-put / bull-call-spread / bear-put-spread) with a price×date P/L matrix engine, retiring the buffer/stress-test machinery per the v2 spec.

**Architecture:** Same one-way pipeline `cli → report → ranking → valuation → filters → models`, plus new `matrix.py`. Spread pair generation lives in `filters.py` (it is candidate filtering); spread valuation in `valuation.py`. Spec: `docs/superpowers/specs/2026-07-19-option-chaser-v2-design.md` (codex-approved). v1 code exists and is green (62 tests); tasks are ordered so the suite stays green after every task.

**Tech Stack:** Python 3.11+, stdlib math (`math.erf`), `yfinance` only (+`tzdata` on Windows), pytest offline.

## Global Constraints

- All commands are POSIX shell — run in **Git Bash**, NOT PowerShell 5.1 (`&&` is a parser error there).
- Deterministic: no clock reads outside `data/yf.py` fetch; "today" = snapshot `fetched_at` → America/New_York date; fixed number formats (prices `{:.2f}`, returns `{x*100:.1f}%`, matrix cells `{x*100:+.0f}%`, Lambda `{:.1f}`, Delta `{:.2f}`); box-drawing characters FORBIDDEN.
- 美式內在價值鉗制（spec §3.2）：ALL valuations = `max(BS, intrinsic, 0)`.
- Spread valuation clamped to `[0, width]`（spec §3.3）; spread guidance has NO L1; spread L2 = min over ALL IV scenarios including baseline（spec §3.4）.
- Matrix price axis lower bound `max(lo, 0.01×spot)`; anchor insertion is remove-then-insert, collision-safe（spec §5.1）.
- `--min-days-after` / `--delay-days` must be argparse UNKNOWN-argument errors (not silently ignored).
- `SCHEMA_VERSION = 2`; loading schema-1 snapshots errors with a re-fetch message, exit 1.
- iv_shifts: 0.0 force-included, deduped, sorted ascending (unchanged from v1).
- Exit codes: 0 success / 1 data-or-empty / 2 param error (unchanged).
- Report money display: per-share AND per-contract (×100, `{x*100:.0f}`) side by side; scenario lines = 估值+損益+報酬率 (unchanged).

## File Structure

```
option_chaser/
├── models.py      # + option_type, strategy constants/helpers, AnalysisParams v2, PairReport
├── valuation.py   # + bs_put, leg_greeks, clamps, scenario_leg_value, SpreadValuation, evaluate_spread, spread guidance
├── filters.py     # stage-1 change, side selection, generate_spread_pairs
├── ranking.py     # |Delta| banding, rank_spreads, strategy-aware reasons
├── matrix.py      # NEW: price_axis, date_axis, matrix_lines
├── report.py      # strategy header, spread blocks, matrix placement, stress section removed
├── cli.py         # --strategy/--matrix-all, buffer flags removed, direction validation, dual pipelines
└── data/
    ├── snapshot.py# schema 2 gate
    └── yf.py      # map calls+puts
tests/
├── fixtures/xyz_v2_snapshot.json           # 20 contracts (10 calls + 10 puts)
├── fixtures/golden_long_call.txt           # generated in Task 8
├── fixtures/golden_long_put.txt
├── fixtures/golden_bull_call_spread.txt
├── fixtures/golden_bear_put_spread.txt
└── (v1 test files updated per task; old golden/stress/buffer tests retired in Task 3)
```

---

### Task 1: Models & schema v2

**Files:**
- Modify: `option_chaser/models.py`, `option_chaser/data/snapshot.py`
- Modify: `tests/test_models_snapshot.py`, `tests/fixtures/xyz_snapshot.json`, `tests/fixtures/yf_rows.json`
- Note: `tests/test_golden.py` still runs against the v1 fixture this task — bump that fixture in place (schema 2 + `option_type`) so the whole suite stays green.

**Interfaces:**
- Produces: `OptionContract.option_type: str` (`"call" | "put"`, REQUIRED field — no default; all constructors updated); `SCHEMA_VERSION = 2`; `STRATEGIES`, `SINGLE_LEG_STRATEGIES`, `SPREAD_STRATEGIES` tuples; `leg_option_type(strategy) -> str`; `is_bullish(strategy) -> bool`; `PairReport(total_pairs: int, removed_sanity: int, passed: int)` frozen dataclass. `load_snapshot` raises `SnapshotSchemaError` for version 1 with message containing `請重新抓取`.
- AnalysisParams is NOT changed in this task (Task 3 does that) — v1 fields still present.

- [ ] **Step 1: Write the failing tests** (append/modify in `tests/test_models_snapshot.py`)

```python
# modify make_snap()'s OptionContract call: add option_type="call"
# append:
from option_chaser.models import (
    STRATEGIES, SINGLE_LEG_STRATEGIES, SPREAD_STRATEGIES,
    leg_option_type, is_bullish, PairReport,
)


def test_strategy_helpers():
    assert STRATEGIES == ("long-call", "long-put", "bull-call-spread", "bear-put-spread")
    assert set(SINGLE_LEG_STRATEGIES) == {"long-call", "long-put"}
    assert set(SPREAD_STRATEGIES) == {"bull-call-spread", "bear-put-spread"}
    assert leg_option_type("long-call") == "call"
    assert leg_option_type("bull-call-spread") == "call"
    assert leg_option_type("long-put") == "put"
    assert leg_option_type("bear-put-spread") == "put"
    assert is_bullish("long-call") and is_bullish("bull-call-spread")
    assert not is_bullish("long-put") and not is_bullish("bear-put-spread")


def test_schema_v1_rejected_with_refetch_message(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 1')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError) as ei:
        load_snapshot(p)
    assert "請重新抓取" in str(ei.value)


def test_pair_report_shape():
    pr = PairReport(total_pairs=6, removed_sanity=2, passed=4)
    assert pr.passed == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_models_snapshot.py -v`
Expected: FAIL (ImportError / TypeError missing option_type)

- [ ] **Step 3: Implement**

In `option_chaser/models.py`: set `SCHEMA_VERSION = 2`; add `option_type: str` to `OptionContract` immediately after `contract_symbol` (REQUIRED, no default); add:

```python
STRATEGIES = ("long-call", "long-put", "bull-call-spread", "bear-put-spread")
SINGLE_LEG_STRATEGIES = ("long-call", "long-put")
SPREAD_STRATEGIES = ("bull-call-spread", "bear-put-spread")


def leg_option_type(strategy: str) -> str:
    """Which chain side the strategy trades (spec §4.1)."""
    return "call" if strategy in ("long-call", "bull-call-spread") else "put"


def is_bullish(strategy: str) -> bool:
    return strategy in ("long-call", "bull-call-spread")


@dataclass(frozen=True)
class PairReport:
    total_pairs: int
    removed_sanity: int
    passed: int
```

In `option_chaser/data/snapshot.py`, replace the schema check body:

```python
    version = data.get("schema_version")
    if version == 1:
        raise SnapshotSchemaError(
            "快照為 v1 格式（僅含 call），請重新抓取（schema_version=1，需要 2）"
        )
    if version != SCHEMA_VERSION:
        raise SnapshotSchemaError(
            f"snapshot schema_version={version} incompatible with {SCHEMA_VERSION}; re-fetch the chain"
        )
```

Then mechanically update every `OptionContract(...)` constructor in the codebase's TESTS and FIXTURES to carry `option_type`: in `tests/fixtures/xyz_snapshot.json` set `"schema_version": 2` and add `"option_type": "call"` to all 10 contracts; in `tests/fixtures/yf_rows.json` no change (adapter fixture — adapter updated in Task 9; `map_rows` gets a temporary hardcoded `option_type="call"` in its constructor call to stay green: edit `option_chaser/data/yf.py` `map_rows` to pass `option_type=str(r.get("option_type", "call"))`). Update helper factories in `tests/test_valuation.py`, `tests/test_guidance.py`, `tests/test_filters.py`, `tests/test_ranking.py`, `tests/test_reasons.py` (each `OptionContract(...)`/`make_*` helper gains `option_type="call"`).

- [ ] **Step 4: Run full suite**

Run: `python -m pytest -q`
Expected: all pass (same count as before: 62)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): schema 2, option_type field, strategy helpers, PairReport"
```

---

### Task 2: Put pricing, put Greeks, American-intrinsic clamp

**Files:**
- Modify: `option_chaser/valuation.py`
- Create: `tests/test_put_bs.py`

**Interfaces:**
- Produces: `bs_put(S, K, T, r, sigma) -> float` (T≤0 → `max(K−S, 0)`); `bs_price(option_type, S, K, T, r, sigma) -> float`; `intrinsic_value(option_type, S, K) -> float`; `clamped_price(option_type, S, K, T, r, sigma) -> float` = `max(bs_price, intrinsic, 0)`; `leg_greeks(option_type, S, K, T, r, sigma) -> Greeks` (put delta = `N(d1) − 1`; put theta_year = `−(S·φ(d1)·σ)/(2√T) + r·K·e^(−rT)·N(−d2)`).
- Purely additive — nothing existing changes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_put_bs.py
import math
from option_chaser.valuation import (
    bs_call, bs_put, bs_price, intrinsic_value, clamped_price, leg_greeks,
)


def test_hull_put_value():
    # Hull S=42,K=40,T=0.5,r=0.10,sigma=0.20: C≈4.76, parity → P≈0.81
    assert abs(bs_put(42, 40, 0.5, 0.10, 0.20) - 0.81) < 0.01


def test_put_call_parity_via_bs_put():
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.35
    c = bs_call(S, K, T, r, sigma)
    p = bs_put(S, K, T, r, sigma)
    assert abs((c - p) - (S - K * math.exp(-r * T))) < 1e-9


def test_put_t_zero_intrinsic():
    assert bs_put(80, 120, 0.0, 0.04, 0.4) == 40.0
    assert bs_put(130, 120, 0.0, 0.04, 0.4) == 0.0


def test_deep_itm_european_put_below_intrinsic_and_clamp():
    # deep ITM put: European BS < intrinsic (K discounting); clamp restores floor
    S, K, T, r, sigma = 80.0, 120.0, 0.5, 0.04, 0.2
    raw = bs_put(S, K, T, r, sigma)
    assert raw < K - S  # the very defect §3.2 exists for
    assert clamped_price("put", S, K, T, r, sigma) == K - S


def test_clamp_noop_for_call_with_positive_rate():
    S, K, T, r, sigma = 120.0, 100.0, 0.5, 0.04, 0.3
    assert clamped_price("call", S, K, T, r, sigma) == bs_call(S, K, T, r, sigma)


def test_bs_price_dispatch_and_intrinsic():
    assert bs_price("call", 42, 40, 0.5, 0.10, 0.20) == bs_call(42, 40, 0.5, 0.10, 0.20)
    assert bs_price("put", 42, 40, 0.5, 0.10, 0.20) == bs_put(42, 40, 0.5, 0.10, 0.20)
    assert intrinsic_value("call", 120, 110) == 10.0
    assert intrinsic_value("put", 80, 120) == 40.0


def test_put_greeks():
    g = leg_greeks("put", 42, 40, 0.5, 0.10, 0.20)
    gc = leg_greeks("call", 42, 40, 0.5, 0.10, 0.20)
    assert abs(g.delta - (gc.delta - 1.0)) < 1e-12   # put delta = call delta − 1
    assert -1.0 < g.delta < 0.0
    assert abs(g.gamma - gc.gamma) < 1e-12
    assert abs(g.vega_per_pct - gc.vega_per_pct) < 1e-12
    # put theta_year = call theta_year + r·K·e^{−rT} (differentiate parity)
    expected = gc.theta_per_day + (0.10 * 40 * math.exp(-0.05)) / 365.0
    assert abs(g.theta_per_day - expected) < 1e-9
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_put_bs.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement** (append to `valuation.py`)

```python
def bs_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put. T <= 0 -> intrinsic (spec §3.1)."""
    if T <= 0.0:
        return max(K - S, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    return bs_call(S, K, T, r, sigma) if option_type == "call" else bs_put(S, K, T, r, sigma)


def intrinsic_value(option_type: str, S: float, K: float) -> float:
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def clamped_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Spec §3.2: American no-arbitrage floor applied to every valuation output."""
    return max(bs_price(option_type, S, K, T, r, sigma), intrinsic_value(option_type, S, K), 0.0)


def leg_greeks(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §3.1. Caller guarantees T > 0."""
    g = call_greeks(S, K, T, r, sigma)
    if option_type == "call":
        return g
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year_put = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm_cdf(-d2)
    )
    return Greeks(
        delta=g.delta - 1.0,
        gamma=g.gamma,
        theta_per_day=theta_year_put / DAYS_PER_YEAR,
        vega_per_pct=g.vega_per_pct,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_put_bs.py -v` → 7 passed; then `python -m pytest -q` → 69 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): put pricing/greeks and American-intrinsic clamp"
```

---

### Task 3: Core pipeline refactor (buffer retirement, strategy-aware single legs)

The coordinated v1→v2 cut. After this task: `AnalysisParams` is v2-shaped, buffer/stress machinery is gone, single-leg pipeline is strategy-aware for BOTH call and put, suite green. Spreads/matrix/report-polish come later.

**Files:**
- Modify: `option_chaser/models.py` (AnalysisParams), `option_chaser/valuation.py` (evaluate_contract, ContractValuation, scenario_leg_value; delete stress code), `option_chaser/filters.py` (stage 1, side selection), `option_chaser/ranking.py` (|Delta| classify, put reason wording), `option_chaser/report.py` (stress section removal, strategy header, put wording), `option_chaser/cli.py` (flags, direction check, param resolution)
- Modify tests: `tests/test_valuation.py`, `tests/test_guidance.py`, `tests/test_filters.py`, `tests/test_ranking.py`, `tests/test_reasons.py`, `tests/test_cli_validation.py`
- Delete: `tests/test_golden.py`, `tests/fixtures/xyz_snapshot.json`, `tests/fixtures/golden_report.txt` (golden coverage returns in Task 8 with the v2 fixture — document this gap in the commit message)

**Interfaces:**
- `AnalysisParams` v2 (exact):

```python
@dataclass(frozen=True)
class AnalysisParams:
    target_price: float
    target_date: str
    strategy: str = "long-call"
    min_expiry: str | None = None
    top: int = 3
    iv_shifts: tuple[float, ...] = (-0.2, 0.0, 0.2)
    rate: float = 0.04
    min_oi: int = 10
    min_volume: int = 0
    max_spread_pct: float = 0.15
    spread_floor: float = 0.10
    delta_bands: tuple[float, float] = (0.35, 0.65)
    min_return: float = 0.0
    force: bool = False
    matrix_all: bool = False
```

（`min_days_after`/`delay_days` DELETED — any code still referencing them must be updated in this task.）
- `valuation.scenario_leg_value(c: OptionContract, S: float, at: date, p: AnalysisParams, shift: float = 0.0) -> float` — remaining `T = (expiry − at)/365`; `at ≥ expiry` → intrinsic; else `clamped_price(c.option_type, S, K, T, r, iv·(1+shift))`. This is the single valuation primitive reused by scenarios NOW and matrix cells in Task 7.
- `ContractValuation` v2 fields (exact order): `contract, mid, spread, delta, gamma, theta_per_day, vega_per_pct, breakeven, breakeven_vs_spot, breakeven_vs_target, effective_leverage, floor_value, scenario_values, baseline_value, l1, l2, l3` — stress fields DELETED. `delta` keeps its sign (negative for puts); banding uses `abs`.
- Per-type anchors: call BE = `K + mid`, put BE = `K − mid`; `breakeven_vs_spot`: call `(BE−spot)/spot`, put `(spot−BE)/spot`; `breakeven_vs_target`: call `(target−BE)/target`, put `(BE−target)/target`; `floor_value = l1 = intrinsic_value(type, target, K)`; L2 = `scenario_leg_value(c, target, target_date, p, min(iv_shifts))`; L3 unchanged. Identity `L1 ≤ L2 ≤ baseline` holds post-clamp for both types.
- `filters.apply_filters(contracts, p, today)`: first slice `[c for c in contracts if c.option_type == leg_option_type(p.strategy)]` (this slice defines `total`), then five stages with stage 1 = `expiry ≥ target_date and (min_expiry is None or expiry ≥ min_expiry)`.
- `ranking.classify(delta, bands)` uses `abs(delta)` internally; everything downstream unchanged.
- `cli.build_parser()`: add `--strategy` (`choices=STRATEGIES`, default `"long-call"`), `--matrix-all` (`action="store_true"`); DELETE `--min-days-after`, `--delay-days`, and `effective_buffer()`. `resolve_params` builds v2 AnalysisParams. `validate_scenario(p, spot, today)`: target_date > today; direction: `is_bullish(p.strategy)` and `target ≤ spot` → ParamError unless force; not bullish and `target ≥ spot` → ParamError unless force.
- `report.py`: delete the stress-test block and `stress` references; header line 2 becomes `f"- 策略: {STRATEGY_LABELS[p.strategy]}"` with `STRATEGY_LABELS = {"long-call": "Long Call", "long-put": "Long Put", "bull-call-spread": "Bull Call Spread", "bear-put-spread": "Bear Put Spread"}` (define in report.py); delete the 延遲壓力情境 header line; put-aware wording: breakeven line uses `高於現價` for calls, `低於現價` for puts.

- [ ] **Step 1: Update the failing tests first** (representative complete replacements; carry over unlisted v1 tests unchanged except constructor/param updates)

`tests/test_valuation.py` — replace stress tests with:

```python
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import bs_call, bs_put, evaluate_contract, scenario_leg_value

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28")
P_PUT = AnalysisParams(target_price=80.0, target_date="2026-08-28", strategy="long-put")


def make_contract(**kw):
    base = dict(contract_symbol="XYZ261016C00110000", option_type="call",
                strike=110.0, expiry="2026-10-16", bid=3.0, ask=3.25, last=3.1,
                volume=152, open_interest=830, implied_volatility=0.38)
    base.update(kw)
    return OptionContract(**base)


def test_call_anchors_and_scenarios():
    v = evaluate_contract(make_contract(), spot=100.0, today=TODAY, p=P)
    assert v.mid == 3.125 and v.breakeven == 113.125
    assert abs(v.breakeven_vs_spot - 0.13125) < 1e-9
    assert abs(v.breakeven_vs_target - (120 - 113.125) / 120) < 1e-9
    t_rem = (date(2026, 10, 16) - date(2026, 8, 28)).days / 365.0
    assert v.floor_value == 10.0 == v.l1
    for shift, val in v.scenario_values:
        assert abs(val - max(bs_call(120.0, 110.0, t_rem, P.rate, 0.38 * (1 + shift)), 10.0)) < 1e-12
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_put_anchors_mirror():
    c = make_contract(contract_symbol="XYZ261016P00090000", option_type="put",
                      strike=90.0, bid=2.8, ask=3.0, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.breakeven == 90.0 - 2.9
    assert abs(v.breakeven_vs_spot - (100.0 - 87.1) / 100.0) < 1e-9
    assert abs(v.breakeven_vs_target - (87.1 - 80.0) / 80.0) < 1e-9  # put cushion = (BE−target)/target
    assert v.floor_value == 10.0 == v.l1  # max(90−80,0)
    assert v.delta < 0
    assert v.l1 <= v.l2 <= v.baseline_value + 1e-12


def test_scenario_leg_value_at_and_after_expiry():
    c = make_contract()
    assert scenario_leg_value(c, 120.0, date(2026, 10, 16), P) == 10.0
    assert scenario_leg_value(c, 120.0, date(2026, 11, 1), P) == 10.0  # past expiry -> intrinsic


def test_deep_itm_put_scenario_clamped():
    c = make_contract(contract_symbol="P120", option_type="put", strike=120.0,
                      bid=41.0, ask=41.5, implied_volatility=0.40)
    v = evaluate_contract(c, spot=100.0, today=TODAY, p=P_PUT)
    assert v.baseline_value == 40.0  # BS European below intrinsic -> clamped
```

`tests/test_cli_validation.py` — replace buffer tests with:

```python
def test_removed_buffer_flags_error(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
             "--snapshot", "d.json", "--min-days-after", "45"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_strategy_choices_and_default():
    p = resolve_params(parse())
    assert p.strategy == "long-call" and p.matrix_all is False
    p2 = resolve_params(parse("--strategy", "bear-put-spread", "--matrix-all"))
    assert p2.strategy == "bear-put-spread" and p2.matrix_all is True


def test_direction_matrix():
    from datetime import date
    today = date(2026, 7, 15)
    for strat, target, spot, needs_force in [
        ("long-call", 120.0, 100.0, False), ("long-call", 90.0, 100.0, True),
        ("bull-call-spread", 120.0, 100.0, False), ("bull-call-spread", 90.0, 100.0, True),
        ("long-put", 80.0, 100.0, False), ("long-put", 110.0, 100.0, True),
        ("bear-put-spread", 80.0, 100.0, False), ("bear-put-spread", 110.0, 100.0, True),
    ]:
        p = resolve_params(parse("--strategy", strat, "--target-price", str(target)))
        if needs_force:
            with pytest.raises(ParamError):
                validate_scenario(p, spot=spot, today=today)
            validate_scenario(
                resolve_params(parse("--strategy", strat, "--target-price", str(target), "--force")),
                spot=spot, today=today)
        else:
            validate_scenario(p, spot=spot, today=today)
```

（`parse()` helper: later `--target-price` overrides work because argparse takes the last occurrence — append extras AFTER the base args, which the existing helper already does.）

`tests/test_filters.py` — stage-1 & side-selection updates:

```python
def test_stage1_expiry_vs_target_date_only():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    passed, rep = apply_filters(
        [make("sep", expiry="2026-09-18"), make("aug", expiry="2026-08-01")], p, TODAY)
    assert [c.contract_symbol for c in passed] == ["sep"]  # Sep>=target passes now
    assert rep.stages[0].removed == 1


def test_side_selection_defines_total():
    p = AnalysisParams(target_price=120.0, target_date="2026-08-28")
    calls = [make("c1"), make("c2")]
    puts = [make("p1", option_type="put"), ]
    passed, rep = apply_filters(calls + puts, p, TODAY)
    assert rep.total == 2  # puts not counted for long-call
    p2 = AnalysisParams(target_price=80.0, target_date="2026-08-28", strategy="long-put")
    passed2, rep2 = apply_filters(calls + puts, p2, TODAY)
    assert rep2.total == 1
```

`tests/test_ranking.py` — add:

```python
def test_classify_uses_abs_delta():
    bands = (0.35, 0.65)
    assert classify(-0.72, bands) == "conservative"
    assert classify(-0.50, bands) == "balanced"
    assert classify(-0.20, bands) == "aggressive"
```

`tests/test_guidance.py` / `tests/test_reasons.py`: update `AnalysisParams(...)` constructors (drop `delay_days`), keep behavior tests; guidance sentences unchanged for single legs.

- [ ] **Step 2: Run to verify failures**

Run: `python -m pytest -q`
Expected: many FAIL/ERROR (old fields gone from tests, new signatures missing)

- [ ] **Step 3: Implement the refactor**

`models.py`: replace `AnalysisParams` with the v2 definition above.

`valuation.py`: delete stress fields/logic from `ContractValuation`/`evaluate_contract`; add:

```python
def scenario_leg_value(
    c: OptionContract, S: float, at: date, p: AnalysisParams, shift: float = 0.0
) -> float:
    """Spec §3 valuation primitive: value of one leg at date `at` with spot S."""
    expiry = date.fromisoformat(c.expiry)
    if at >= expiry:
        return intrinsic_value(c.option_type, S, c.strike)
    T = days_between(at, expiry) / DAYS_PER_YEAR
    return clamped_price(c.option_type, S, c.strike, T, p.rate, c.implied_volatility * (1.0 + shift))
```

`evaluate_contract` rebuilt (complete):

```python
def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams
) -> ContractValuation:
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    expiry = date.fromisoformat(c.expiry)
    target = date.fromisoformat(p.target_date)
    g = leg_greeks(c.option_type, spot, c.strike,
                   days_between(today, expiry) / DAYS_PER_YEAR, p.rate,
                   c.implied_volatility)
    scenario_values = tuple(
        (shift, scenario_leg_value(c, p.target_price, target, p, shift))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]
    floor_value = intrinsic_value(c.option_type, p.target_price, c.strike)
    if c.option_type == "call":
        breakeven = c.strike + mid
        be_vs_spot = (breakeven - spot) / spot
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = c.strike - mid
        be_vs_spot = (spot - breakeven) / spot
        be_vs_target = (breakeven - p.target_price) / p.target_price
    l2 = scenario_leg_value(c, p.target_price, target, p, min(p.iv_shifts))
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven, breakeven_vs_spot=be_vs_spot,
        breakeven_vs_target=be_vs_target,
        effective_leverage=abs(g.delta) * spot / mid,
        floor_value=floor_value, scenario_values=scenario_values,
        baseline_value=baseline_value,
        l1=floor_value, l2=l2, l3=baseline_value / (1.0 + p.min_return),
    )
```

`filters.py` (`apply_filters` head; stages 2–5 unchanged):

```python
from .models import leg_option_type
...
    side = leg_option_type(p.strategy)
    remaining = [c for c in contracts if c.option_type == side]
    total = len(remaining)
    target = date.fromisoformat(p.target_date)
    min_expiry_2 = date.fromisoformat(p.min_expiry) if p.min_expiry else None

    def expiry_ok(c: OptionContract) -> bool:
        e = date.fromisoformat(c.expiry)
        return e >= target and (min_expiry_2 is None or e >= min_expiry_2)
```

`ranking.py`: `classify` first line `delta = abs(delta)`; in `build_reasons` conservative branch, wording per type:

```python
    if band == BAND_CONSERVATIVE:
        word = "高於" if v.contract.option_type == "call" else "低於"
        s = f"breakeven 僅{word}現價 {_pct(v.breakeven_vs_spot)}"
        half_price = spot + 0.5 * (p.target_price - spot)
        from .valuation import scenario_leg_value
        from datetime import date as _date
        if scenario_leg_value(v.contract, half_price, _date.fromisoformat(p.target_date), p) > v.mid:
            s += "，劇本半對仍獲利"
        pros.append(s)
```

（move the imports to the top of `ranking.py`; `half_price` formula is direction-agnostic: `spot + 0.5×(target − spot)` moves halfway toward the target for both families.）Balanced branch: `intrinsic_now = intrinsic_value(v.contract.option_type, spot, v.contract.strike)`（import from valuation）.

`report.py`: add `STRATEGY_LABELS` dict; header user-assumption block gains `f"- 策略: {STRATEGY_LABELS[p.strategy]}"` as its first bullet; delete 延遲壓力情境 line and the whole 壓力測試 block in `_candidate_lines`; breakeven line wording:

```python
    word = "高於" if c.option_type == "call" else "低於"
    ... f"- Breakeven: ${_money(v.breakeven)}（{word}現價 {_pct(v.breakeven_vs_spot)}；"
        f"對目標價緩衝 {_pct(v.breakeven_vs_target)}）",
```

`cli.py`: parser — delete the two buffer `add_argument` lines and `effective_buffer`; add:

```python
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="long-call")
    ap.add_argument("--matrix-all", action="store_true")
```

`resolve_params`: drop buffer resolution; return v2 params (`strategy=args.strategy, matrix_all=args.matrix_all`). `validate_scenario`:

```python
def validate_scenario(p: AnalysisParams, spot: float, today: date) -> None:
    if date.fromisoformat(p.target_date) <= today:
        raise ParamError(f"--target-date 必須晚於資料日 {today.isoformat()}")
    if is_bullish(p.strategy):
        if p.target_price <= spot and not p.force:
            raise ParamError(
                f"看漲策略目標價 {p.target_price} 低於現價 {spot}；確定要跑請加 --force")
    else:
        if p.target_price >= spot and not p.force:
            raise ParamError(
                f"看跌策略目標價 {p.target_price} 高於現價 {spot}；確定要跑請加 --force")
```

Delete `tests/test_golden.py` and the two v1 fixture files. Update `main()` only as far as it still compiles for long-call/long-put single-leg flow (spread branch raises `ParamError("價差策略於本版後續任務啟用")` TEMPORARILY — removed in Task 6; footer 過濾 line no longer mentions buffer).

- [ ] **Step 4: Run full suite**

Run: `python -m pytest -q`
Expected: all pass（~66 — stress/golden retired, new direction/anchor tests added）

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2)!: retire buffer/stress machinery; strategy-aware single-leg pipeline (golden coverage returns in Task 8)"
```

---

### Task 4: Spread pair generation (filters.py)

**Files:**
- Modify: `option_chaser/filters.py`
- Create: `tests/test_spread_pairs.py`

**Interfaces:**
- Produces: `filters.generate_spread_pairs(legs: list[OptionContract], p: AnalysisParams) -> tuple[list[tuple[OptionContract, OptionContract]], PairReport]` — each tuple is `(long_leg, short_leg)`; bull-call: long = lower strike; bear-put: long = higher strike; same-expiry pairs only; sanity rejects `net_mid ≤ 0` or `net_worst ≥ width` (`net_mid = mid_long − mid_short`, `net_worst = ask_long − bid_short`, `width = |K_short − K_long|`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spread_pairs.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import generate_spread_pairs

P_BCS = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                       strategy="bull-call-spread")


def make(sym, strike, bid, ask, expiry="2026-10-16", opt="call"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=0.35)


def test_bull_call_pairing_and_sanity():
    legs = [make("A", 100.0, 5.0, 5.2), make("B", 110.0, 2.0, 2.2),
            make("C", 120.0, 0.8, 1.0), make("N", 105.0, 3.0, 3.2, expiry="2026-11-20")]
    pairs, rep = generate_spread_pairs(legs, P_BCS)
    # same-expiry combos: C(3,2)=3 from Oct16; Nov20 alone has none
    assert rep.total_pairs == 3
    for lng, sht in pairs:
        assert lng.strike < sht.strike and lng.expiry == sht.expiry


def test_sanity_rejects_counted():
    # net_mid <= 0: long cheaper than short (crossed pricing)
    legs = [make("A", 100.0, 1.0, 1.1), make("B", 110.0, 2.0, 2.2)]
    pairs, rep = generate_spread_pairs(legs, P_BCS)
    assert pairs == [] and rep.removed_sanity == 1 and rep.total_pairs == 1
    # net_worst >= width: 30-wide quotes on a 5-wide spread
    legs2 = [make("A", 100.0, 31.0, 32.0), make("B", 105.0, 1.0, 1.2)]
    pairs2, rep2 = generate_spread_pairs(legs2, P_BCS)
    assert pairs2 == [] and rep2.removed_sanity == 1


def test_bear_put_long_is_higher_strike():
    p = AnalysisParams(target_price=80.0, target_date="2026-08-28",
                       strategy="bear-put-spread")
    legs = [make("L", 100.0, 5.0, 5.2, opt="put"), make("S", 85.0, 1.0, 1.2, opt="put")]
    pairs, rep = generate_spread_pairs(legs, p)
    assert len(pairs) == 1
    lng, sht = pairs[0]
    assert lng.strike == 100.0 and sht.strike == 85.0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_spread_pairs.py -v` → ImportError

- [ ] **Step 3: Implement** (append to `filters.py`)

```python
from itertools import combinations

from .models import AnalysisParams, PairReport


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
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_spread_pairs.py -v` → 3 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): exhaustive same-expiry spread pairing with sanity PairReport"
```

---

### Task 5: Spread valuation & guidance

**Files:**
- Modify: `option_chaser/valuation.py`
- Create: `tests/test_spread_valuation.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class SpreadValuation:
    long_leg: OptionContract
    short_leg: OptionContract
    width: float
    net_mid: float
    net_worst: float
    net_delta: float
    breakeven: float
    breakeven_vs_target: float
    effective_leverage: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l2: float           # min over ALL scenarios (spec §3.4) — no l1 field exists
    l3: float
    max_profit: float   # width − net_mid

def spread_scenario_value(long_leg, short_leg, S: float, at: date, p, shift: float = 0.0) -> float
def evaluate_spread(long_leg, short_leg, spot: float, today: date, p) -> SpreadValuation
def spread_guidance_judgments(sv: SpreadValuation, p) -> list[str]
```

- `spread_scenario_value` = `min(max(scenario_leg_value(long) − scenario_leg_value(short), 0), width)`; breakeven: bull-call `K_long + net_mid`, bear-put `K_long − net_mid`（long is the higher strike there — formula in code below uses the long leg's own strike with direction sign）; cushion mirrors §3.4; `l2 = min(v for _, v in scenario_values)`.
- Judgments (spread has no L1 sentence): `net_worst > l2` → `f"劇本成立但最保守 IV 情境下仍虧損（IV 情境最低值 ${l2:.2f}）"`; `net_worst > l3` → `"以最差進場成本達不到你設定的最低報酬（min-return）"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spread_valuation.py
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import (
    evaluate_spread, spread_scenario_value, spread_guidance_judgments,
)

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   strategy="bull-call-spread")


def make(sym, strike, bid, ask, iv=0.35, opt="call", expiry="2026-10-16"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


def test_value_clamped_to_width_and_zero():
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 105.0, 5.0, 5.2)
    # very deep scenario: both far ITM -> raw diff < width e^{-rT} but clamps hold
    v_hi = spread_scenario_value(lng, sht, 500.0, date(2026, 8, 28), P)
    assert 0.0 <= v_hi <= 5.0
    v_lo = spread_scenario_value(lng, sht, 1.0, date(2026, 8, 28), P)
    assert v_lo == 0.0


def test_expiry_payoff():
    lng, sht = make("L", 100.0, 8.0, 8.2), make("S", 110.0, 3.0, 3.2)
    assert spread_scenario_value(lng, sht, 120.0, date(2026, 10, 16), P) == 10.0
    assert spread_scenario_value(lng, sht, 105.0, date(2026, 10, 16), P) == 5.0
    assert spread_scenario_value(lng, sht, 90.0, date(2026, 10, 16), P) == 0.0


def test_deep_itm_spread_value_rises_when_iv_drops():
    # spec §9.7 counter-intuitive lock: net vega sign change — deep ITM vertical
    # gains value as IV falls (value pinned toward width)
    lng, sht = make("L", 60.0, 41.0, 41.4), make("S", 70.0, 31.5, 31.9)
    hi_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=+0.2)
    lo_iv = spread_scenario_value(lng, sht, 120.0, date(2026, 8, 28), P, shift=-0.2)
    assert lo_iv > hi_iv


def test_evaluate_spread_fields_and_l2_min():
    lng, sht = make("L", 110.0, 3.0, 3.25, iv=0.30), make("S", 130.0, 0.05, 0.15, iv=0.45)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=P)
    assert sv.width == 20.0
    assert abs(sv.net_mid - (3.125 - 0.10)) < 1e-12
    assert abs(sv.net_worst - (3.25 - 0.05)) < 1e-12
    assert sv.breakeven == 110.0 + sv.net_mid
    assert sv.l2 == min(v for _, v in sv.scenario_values)
    assert sv.l2 <= sv.baseline_value + 1e-12
    assert not hasattr(sv, "l1")
    assert abs(sv.max_profit - (20.0 - sv.net_mid)) < 1e-12


def test_bear_put_breakeven():
    p = AnalysisParams(target_price=80.0, target_date="2026-08-28",
                       strategy="bear-put-spread")
    lng = make("L", 100.0, 5.2, 5.4, iv=0.36, opt="put")
    sht = make("S", 85.0, 1.1, 1.25, iv=0.35, opt="put")
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=p)
    assert sv.breakeven == 100.0 - sv.net_mid
    assert abs(sv.breakeven_vs_target - (sv.breakeven - 80.0) / 80.0) < 1e-9


def test_spread_judgments_trigger():
    # overpriced quotes: net_worst above every ceiling
    lng = make("L", 110.0, 9.4, 9.6, iv=0.30)
    sht = make("S", 120.0, 0.4, 0.5, iv=0.30)
    sv = evaluate_spread(lng, sht, spot=100.0, today=TODAY, p=P)
    msgs = spread_guidance_judgments(sv, P)
    assert any("最保守 IV 情境" in m for m in msgs)
```

- [ ] **Step 2: Run to verify failure** → ImportError

- [ ] **Step 3: Implement** (append to `valuation.py`)

```python
def spread_scenario_value(
    long_leg: OptionContract, short_leg: OptionContract,
    S: float, at: date, p: AnalysisParams, shift: float = 0.0,
) -> float:
    width = abs(short_leg.strike - long_leg.strike)
    raw = (scenario_leg_value(long_leg, S, at, p, shift)
           - scenario_leg_value(short_leg, S, at, p, shift))
    return min(max(raw, 0.0), width)


@dataclass(frozen=True)
class SpreadValuation:
    long_leg: OptionContract
    short_leg: OptionContract
    width: float
    net_mid: float
    net_worst: float
    net_delta: float
    breakeven: float
    breakeven_vs_target: float
    effective_leverage: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l2: float
    l3: float
    max_profit: float


def evaluate_spread(
    long_leg: OptionContract, short_leg: OptionContract,
    spot: float, today: date, p: AnalysisParams,
) -> SpreadValuation:
    width = abs(short_leg.strike - long_leg.strike)
    net_mid = (long_leg.bid + long_leg.ask) / 2.0 - (short_leg.bid + short_leg.ask) / 2.0
    net_worst = long_leg.ask - short_leg.bid
    target = date.fromisoformat(p.target_date)
    expiry = date.fromisoformat(long_leg.expiry)
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    g_l = leg_greeks(long_leg.option_type, spot, long_leg.strike, t_now, p.rate,
                     long_leg.implied_volatility)
    g_s = leg_greeks(short_leg.option_type, spot, short_leg.strike, t_now, p.rate,
                     short_leg.implied_volatility)
    net_delta = g_l.delta - g_s.delta
    scenario_values = tuple(
        (shift, spread_scenario_value(long_leg, short_leg, p.target_price, target, p, shift))
        for shift in p.iv_shifts
    )
    baseline = dict(scenario_values)[0.0]
    if long_leg.option_type == "call":
        breakeven = long_leg.strike + net_mid
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = long_leg.strike - net_mid
        be_vs_target = (breakeven - p.target_price) / p.target_price
    return SpreadValuation(
        long_leg=long_leg, short_leg=short_leg, width=width,
        net_mid=net_mid, net_worst=net_worst, net_delta=net_delta,
        breakeven=breakeven, breakeven_vs_target=be_vs_target,
        effective_leverage=abs(net_delta) * spot / net_mid,
        scenario_values=scenario_values, baseline_value=baseline,
        l2=min(v for _, v in scenario_values),
        l3=baseline / (1.0 + p.min_return),
        max_profit=width - net_mid,
    )


def spread_guidance_judgments(sv: SpreadValuation, p: AnalysisParams) -> list[str]:
    """Spec §3.4: spreads have NO L1; L2 is the scenario envelope minimum."""
    msgs: list[str] = []
    if sv.net_worst > sv.l2:
        msgs.append(f"劇本成立但最保守 IV 情境下仍虧損（IV 情境最低值 ${sv.l2:.2f}）")
    if sv.net_worst > sv.l3:
        msgs.append("以最差進場成本達不到你設定的最低報酬（min-return）")
    return msgs
```

- [ ] **Step 4: Run** — file 7 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): spread valuation with width clamp, envelope L2, spread guidance"
```

---

### Task 6: Spread ranking, reasons, report & CLI wiring

**Files:**
- Modify: `option_chaser/ranking.py`, `option_chaser/report.py`, `option_chaser/cli.py`
- Create: `tests/test_spread_ranking.py`

**Interfaces:**
- `ranking.spread_baseline_return(sv) -> float` = `(baseline_value − net_mid)/net_mid`
- `ranking.rank_spreads(spreads: list[SpreadValuation], p) -> list[SpreadValuation]` — sort by return desc; tie-break `((long.spread+short.spread)/net_mid, long.strike, expiry, long.contract_symbol)`; truncate `p.top`
- `ranking.build_spread_reasons(sv, idx: int, n_pairs: int, p) -> tuple[list[str], list[str]]` — pros: `f"劇本成立時報酬率 {_pct(ret)}（合格 {n_pairs} 組中第 {idx+1}）"`; cons: `f"獲利上限 = 寬度 − 淨成本 = ${sv.max_profit:.2f}（目標價以上的漲幅不參與）"`, combined-spread% warning when `(long.spread+short.spread) > max(p.spread_floor, (2/3)·p.max_spread_pct·net_mid)`, plus `spread_guidance_judgments`
- `report.render_spreads(snap, p, freport, pair_report, ranked_spreads, n_pairs, today) -> str` — header/footer shared with single-leg render; 配對統計 lines after filter stats: `配對總數/健全性淘汰/合格組數`; per-candidate block: both legs (`買 {sym} K=… @Mid` / `賣 {sym} K=… @Mid`), 淨成本(Bid/Mid/Ask口徑=net_worst)、寬度、最大獲利、BE+緩衝、IV 情境行標籤「IV 情境最低值」for the l2 display line、損益三件套、買價指引（L2/L3 only）、評語
- `cli.main`: spread strategies → `apply_filters` → `generate_spread_pairs` → `evaluate_spread` per pair → `rank_spreads` → `render_spreads`; zero pairs → filter-only report + pair stats, exit 1. Remove the Task-3 temporary `ParamError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spread_ranking.py
import io, contextlib
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_spread
from option_chaser.ranking import rank_spreads, spread_baseline_return, build_spread_reasons

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   strategy="bull-call-spread")


def make(sym, strike, bid, ask, iv=0.30):
    return OptionContract(contract_symbol=sym, option_type="call", strike=strike,
                          expiry="2026-10-16", bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


def build(lo, hi):
    return evaluate_spread(lo, hi, spot=100.0, today=TODAY, p=P)


def test_rank_spreads_orders_by_baseline_return():
    a = build(make("A", 105.0, 5.3, 5.5, 0.36), make("B", 130.0, 0.05, 0.15, 0.45))
    b = build(make("C", 110.0, 3.0, 3.25, 0.30), make("B2", 130.0, 0.05, 0.15, 0.45))
    ranked = rank_spreads([a, b], P)
    rets = [spread_baseline_return(s) for s in ranked]
    assert rets == sorted(rets, reverse=True)


def test_reasons_mention_rank_and_cap():
    sv = build(make("A", 110.0, 3.0, 3.25), make("B", 130.0, 0.05, 0.15, 0.45))
    pros, cons = build_spread_reasons(sv, idx=0, n_pairs=4, p=P)
    assert any("合格 4 組中第 1" in s for s in pros)
    assert any("獲利上限" in s for s in cons)


def test_cli_spread_end_to_end(tmp_path):
    # snapshot with two call legs -> one qualified pair -> report renders
    import json
    from option_chaser.cli import main
    snap = {
        "schema_version": 2, "symbol": "XYZ",
        "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
        "source": "yfinance", "contracts": [
            {"contract_symbol": "A", "option_type": "call", "strike": 105.0,
             "expiry": "2026-10-16", "bid": 5.3, "ask": 5.5, "last": None,
             "volume": 80, "open_interest": 300, "implied_volatility": 0.36},
            {"contract_symbol": "B", "option_type": "call", "strike": 110.0,
             "expiry": "2026-10-16", "bid": 3.0, "ask": 3.25, "last": None,
             "volume": 90, "open_interest": 400, "implied_volatility": 0.30},
        ],
    }
    f = tmp_path / "s.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--strategy", "bull-call-spread", "--target-price", "120",
                   "--target-date", "2026-08-28", "--snapshot", str(f)])
    out = buf.getvalue()
    assert rc == 0
    assert "配對總數" in out and "Bull Call Spread" in out
    assert "獲利上限" in out
```

- [ ] **Step 2: Run to verify failure** → ImportError / ParamError(temporary guard)

- [ ] **Step 3: Implement**

`ranking.py` (append; `_pct` already exists):

```python
from .valuation import SpreadValuation, spread_guidance_judgments


def spread_baseline_return(sv: SpreadValuation) -> float:
    return (sv.baseline_value - sv.net_mid) / sv.net_mid


def _spread_tie_key(sv: SpreadValuation) -> tuple:
    legs_spread = (sv.long_leg.ask - sv.long_leg.bid) + (sv.short_leg.ask - sv.short_leg.bid)
    return (legs_spread / sv.net_mid, sv.long_leg.strike, sv.long_leg.expiry,
            sv.long_leg.contract_symbol)


def rank_spreads(spreads: list[SpreadValuation], p: AnalysisParams) -> list[SpreadValuation]:
    ordered = sorted(spreads, key=lambda s: (-spread_baseline_return(s), *_spread_tie_key(s)))
    return ordered[: p.top]


def build_spread_reasons(
    sv: SpreadValuation, idx: int, n_pairs: int, p: AnalysisParams
) -> tuple[list[str], list[str]]:
    pros = [f"劇本成立時報酬率 {_pct(spread_baseline_return(sv))}（合格 {n_pairs} 組中第 {idx + 1}）"]
    cons = [f"獲利上限 = 寬度 − 淨成本 = ${sv.max_profit:.2f}（目標價以上的漲幅不參與）"]
    legs_spread = (sv.long_leg.ask - sv.long_leg.bid) + (sv.short_leg.ask - sv.short_leg.bid)
    if legs_spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * sv.net_mid):
        cons.append("買賣價差偏大（兩腿合計）")
    cons.extend(spread_guidance_judgments(sv, p))
    return pros, cons
```

`report.py` — add (sharing `_header_lines`/`_filter_lines`/`_footer_lines`/`_money`/`_pct`/`_shift_name`/`_val_line`):

```python
def _pair_lines(pr) -> list[str]:
    return ["", "[配對統計]", f"- 配對總數: {pr.total_pairs}",
            f"- 健全性淘汰: {pr.removed_sanity}", f"- 合格組數: {pr.passed}"]


def _spread_candidate_lines(sv, idx, n_pairs, p) -> list[str]:
    from .ranking import build_spread_reasons
    from .valuation import spread_guidance_judgments
    ll, sl = sv.long_leg, sv.short_leg
    lines = [
        "",
        f"{idx + 1}) 買 K={_money(ll.strike)} / 賣 K={_money(sl.strike)} / {ll.expiry} 到期（寬度 ${_money(sv.width)}）",
        f"- 買腿 {ll.contract_symbol}: Bid ${_money(ll.bid)} / Ask ${_money(ll.ask)} IV {_pct_iv(ll.implied_volatility)}",
        f"- 賣腿 {sl.contract_symbol}: Bid ${_money(sl.bid)} / Ask ${_money(sl.ask)} IV {_pct_iv(sl.implied_volatility)}",
        f"- 淨成本: Mid ${_money(sv.net_mid)}（${sv.net_mid * 100:.0f}/張） / 最差 ${_money(sv.net_worst)}（${sv.net_worst * 100:.0f}/張）",
        f"- 最大獲利: ${_money(sv.max_profit)}（${sv.max_profit * 100:.0f}/張） / 淨Delta {sv.net_delta:.2f} / Lambda {sv.effective_leverage:.1f}x",
        f"- Breakeven: ${_money(sv.breakeven)}（對目標價緩衝 {_pct(sv.breakeven_vs_target)}）",
        "",
        "劇本成立時:",
    ]
    for shift, val in sv.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, sv.net_mid))
    lines.append(_val_line("IV 情境最低值", sv.l2, sv.net_mid))
    lines += ["", "買價指引:",
              f"- L2 保守上限（IV 情境最低值）: ${_money(sv.l2)}（${sv.l2 * 100:.0f}/張）",
              f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: ${_money(sv.l3)}（${sv.l3 * 100:.0f}/張）"]
    judgments = spread_guidance_judgments(sv, p)
    if judgments:
        lines += [f"- 警示: {m}" for m in judgments]
    else:
        lines.append("- 目前最差進場成本低於全部天花板")
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    lines += ["", "評語:"] + [f"- 優點: {s}" for s in pros] + [f"- 代價: {s}" for s in cons]
    return lines


def render_spreads(snap, p, freport, pair_report, ranked, n_pairs, today) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport) + _pair_lines(pair_report)
    if not ranked:
        lines += ["", "無合格價差組合，不產生推薦。", ""]
        return "\n".join(lines)
    for i, sv in enumerate(ranked):
        lines += _spread_candidate_lines(sv, i, n_pairs, p)
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)
```

`cli.py` `main()` — replace the temporary guard with:

```python
    qualified, freport = apply_filters(snap.contracts, p, today)
    if p.strategy in SPREAD_STRATEGIES:
        pairs, pair_report = generate_spread_pairs(qualified, p)
        if not pairs:
            print(render_spreads(snap, p, freport, pair_report, [], 0, today), end="")
            return 1
        spreads = [evaluate_spread(l, s, snap.spot, today, p) for l, s in pairs]
        ranked = rank_spreads(spreads, p)
        text = render_spreads(snap, p, freport, pair_report, ranked,
                              n_pairs=pair_report.passed, today=today)
    else:
        if not qualified:
            print(render_filter_only(snap, p, freport, today))
            return 1
        vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
        ranked_bands = rank(vals, p)
        text = render(snap, p, freport, ranked_bands, n_qualified=len(qualified), today=today)
    print(text, end="")
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    return 0
```

（imports at top of cli.py: `SPREAD_STRATEGIES`, `generate_spread_pairs`, `evaluate_spread`, `rank_spreads`, `render_spreads`. Note the single-leg path also switches to `print(text, end="")` and zero-qualified spread path returns 1 — keep `render_filter_only` printing unchanged for single legs.）

- [ ] **Step 4: Run** — file 3 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): spread ranking/reasons/report and CLI dual pipeline"
```

---

### Task 7: Matrix engine (axes + lines)

**Files:**
- Create: `option_chaser/matrix.py`, `tests/test_matrix.py`

**Interfaces:**
- Produces:

```python
matrix.price_axis(spot: float, target: float) -> list[tuple[float, str]]   # ascending, len 11
matrix.date_axis(today: date, target_date: date, expiry: date) -> list[tuple[date, str]]  # len ≤ 7, last = expiry
matrix.matrix_lines(value_fn: Callable[[float, date], float], cost: float,
                    prices: list[tuple[float, str]], dates: list[tuple[date, str]]) -> list[str]
```

- `value_fn(S, d)` is strategy-agnostic (caller builds it from `scenario_leg_value` / `spread_scenario_value`, which already handle `d ≥ expiry` → payoff).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_matrix.py
from datetime import date
from option_chaser.matrix import price_axis, date_axis, matrix_lines


def test_price_axis_len_anchors_and_positivity():
    rows = price_axis(100.0, 120.0)
    prices = [v for v, _ in rows]
    assert len(rows) == 11 and prices == sorted(prices)
    assert 100.0 in prices and 120.0 in prices
    labels = dict(rows)
    assert labels[100.0] == "<現價>" and labels[120.0] == "<目標>"
    # low-target put scenario: floor at 0.01*spot
    rows2 = price_axis(10.0, 0.5)
    assert min(v for v, _ in rows2) >= 0.01 * 10.0 - 1e-12


def test_price_axis_collision_spot_near_target():
    rows = price_axis(100.0, 100.5)
    prices = [v for v, _ in rows]
    assert len(rows) == 11 and 100.0 in prices and 100.5 in prices


def test_price_axis_spot_equals_target_dual_label():
    rows = price_axis(100.0, 100.0)
    labels = dict(rows)
    assert labels[100.0] == "<現價><目標>"
    assert len(rows) == 11


def test_date_axis_endpoints_and_anchor():
    cols = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))
    ds = [d for d, _ in cols]
    assert ds[0] == date(2026, 7, 15) and ds[-1] == date(2026, 10, 16)
    assert date(2026, 8, 28) in ds
    assert dict(cols)[date(2026, 8, 28)] == "*"


def test_date_axis_target_equals_expiry_shares_column():
    cols = date_axis(date(2026, 7, 15), date(2026, 10, 16), date(2026, 10, 16))
    ds = [d for d, _ in cols]
    assert ds[-1] == date(2026, 10, 16) and dict(cols)[date(2026, 10, 16)] == "*"


def test_matrix_lines_shape_and_determinism():
    prices = price_axis(100.0, 120.0)
    dates = date_axis(date(2026, 7, 15), date(2026, 8, 28), date(2026, 10, 16))

    def fn(S, d):  # deterministic dummy
        return max(S - 110.0, 0.0)

    a = matrix_lines(fn, 3.0, prices, dates)
    b = matrix_lines(fn, 3.0, prices, dates)
    assert a == b
    assert len(a) == 1 + 11  # header + one line per price row
    assert not any(0x2500 <= ord(ch) <= 0x257F for line in a for ch in line)
```

- [ ] **Step 2: Run to verify failure** → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# option_chaser/matrix.py
"""Price×date P/L matrix engine (spec §5). Pure functions, deterministic."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable


def _insert_anchors(pts: list[float], anchors: list[float]) -> list[float]:
    """Spec §5.1: per-anchor remove nearest unremoved grid point, then insert anchors."""
    removed: set[int] = set()
    for a in anchors:
        best = min(
            (abs(pts[i] - a), i) for i in range(len(pts)) if i not in removed
        )[1]
        removed.add(best)
    vals = [p for i, p in enumerate(pts) if i not in removed] + list(anchors)
    vals.sort()
    return vals


def price_axis(spot: float, target: float) -> list[tuple[float, str]]:
    pad = 0.10 * spot
    lo = max(min(spot, target) - pad, 0.01 * spot)
    hi = max(spot, target) + pad
    pts = [lo + (hi - lo) * i / 10.0 for i in range(11)]
    anchors = sorted({spot, target})
    vals = _insert_anchors(pts, anchors)

    def label(v: float) -> str:
        s = ""
        if v == spot:
            s += "<現價>"
        if v == target:
            s += "<目標>"
        return s

    return [(v, label(v)) for v in vals]


def date_axis(today: date, target_date: date, expiry: date) -> list[tuple[date, str]]:
    total = (expiry - today).days
    pts = [today + timedelta(days=round(total * i / 6.0)) for i in range(7)]
    pts[-1] = expiry
    uniq = sorted(set(pts))
    if target_date not in uniq:
        interior = [i for i in range(len(uniq)) if 0 < i < len(uniq) - 1]
        if interior:
            best = min((abs((uniq[i] - target_date).days), i) for i in interior)[1]
            uniq[best] = target_date
            uniq = sorted(set(uniq))
    return [(d, "*" if d == target_date else "") for d in uniq]


def matrix_lines(
    value_fn: Callable[[float, date], float], cost: float,
    prices: list[tuple[float, str]], dates: list[tuple[date, str]],
) -> list[str]:
    header = "價格".ljust(10) + " ".join(
        (d.strftime("%m/%d") + lbl).rjust(7) for d, lbl in dates
    )
    lines = [header]
    for price, plabel in reversed(prices):
        cells = []
        for d, _ in dates:
            ret = (value_fn(price, d) - cost) / cost
            cells.append(f"{ret * 100:+.0f}%".rjust(7))
        lines.append(f"{price:8.2f}{plabel}".ljust(10) + " ".join(cells))
    return lines
```

- [ ] **Step 4: Run** — file 6 passed; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): matrix engine with collision-safe anchors and positivity clamp"
```

---

### Task 8: Matrix integration, v2 fixture, four goldens

**Files:**
- Modify: `option_chaser/report.py`
- Create: `tests/fixtures/xyz_v2_snapshot.json`, `tests/test_golden_v2.py`; goldens generated: `tests/fixtures/golden_long_call.txt`, `golden_long_put.txt`, `golden_bull_call_spread.txt`, `golden_bear_put_spread.txt`

**Interfaces:**
- `report._matrix_block(value_fn, cost, snap, p, today, expiry) -> list[str]` — computes axes (`price_axis(snap.spot, p.target_price)`, `date_axis(today, target, expiry)`), returns `["", "P/L 矩陣（報酬率，Mid 進場）:"] + matrix_lines(...)`.
- Placement: single-leg — bands' index-0 candidates get the block appended after 評語 (or every candidate when `p.matrix_all`); spreads — ranked index 0 (or all when `matrix_all`).
- Single-leg `value_fn = lambda S, d: scenario_leg_value(c, S, d, p)`; spread `value_fn = lambda S, d: spread_scenario_value(lng, sht, S, d, p)`.
- Footer gains: `- 矩陣: 11 價格 × ≤7 日期；IV 按快照值恆定；末欄為到期 payoff；估值含美式內在價值鉗制`; footer 過濾 line unchanged; put/spread formula lines added: `- Put: P = K·e^(-rT)·N(-d2) - S·N(-d1)；估值鉗制 value = max(BS, 內在價值, 0)`、`- 價差: V = 長腿 − 短腿，鉗制至 [0, 寬度]；價差無 L1，L2 = 全部 IV 情境最小值（情境包絡，非無套利下限）`.

- [ ] **Step 1: Write the v2 fixture** — `tests/fixtures/xyz_v2_snapshot.json`, spot 100.0, `fetched_at "2026-07-15T21:30:00-04:00"`, schema 2. Contracts (all fields listed; `last: null` unless noted):

```json
{"schema_version": 2, "symbol": "XYZ", "fetched_at": "2026-07-15T21:30:00-04:00",
 "spot": 100.0, "source": "yfinance", "contracts": [
  {"contract_symbol": "XYZC90N",  "option_type": "call", "strike": 90.0,  "expiry": "2026-11-20", "bid": 13.0, "ask": 13.4, "last": 13.2, "volume": 120, "open_interest": 500, "implied_volatility": 0.34},
  {"contract_symbol": "XYZC105O", "option_type": "call", "strike": 105.0, "expiry": "2026-10-16", "bid": 5.3,  "ask": 5.5,  "last": 5.4,  "volume": 80,  "open_interest": 300, "implied_volatility": 0.36},
  {"contract_symbol": "XYZC95O",  "option_type": "call", "strike": 95.0,  "expiry": "2026-10-16", "bid": 30.6, "ask": 31.0, "last": 30.8, "volume": 5,   "open_interest": 40,  "implied_volatility": 0.9},
  {"contract_symbol": "XYZC110O", "option_type": "call", "strike": 110.0, "expiry": "2026-10-16", "bid": 3.0,  "ask": 3.25, "last": 3.1,  "volume": 0,   "open_interest": 830, "implied_volatility": 0.30},
  {"contract_symbol": "XYZC130O", "option_type": "call", "strike": 130.0, "expiry": "2026-10-16", "bid": 0.05, "ask": 0.15, "last": 0.1,  "volume": 3,   "open_interest": 50,  "implied_volatility": 0.45},
  {"contract_symbol": "XYZC100A", "option_type": "call", "strike": 100.0, "expiry": "2026-08-01", "bid": 5.0,  "ask": 5.3,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35},
  {"contract_symbol": "XYZC100B", "option_type": "call", "strike": 100.0, "expiry": "2026-10-16", "bid": 0.0,  "ask": 0.5,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35},
  {"contract_symbol": "XYZC100C", "option_type": "call", "strike": 100.0, "expiry": "2026-11-20", "bid": 5.0,  "ask": 5.5,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.001},
  {"contract_symbol": "XYZC100D", "option_type": "call", "strike": 100.5, "expiry": "2026-10-16", "bid": 5.0,  "ask": 5.4,  "last": null, "volume": 10,  "open_interest": 5,   "implied_volatility": 0.35},
  {"contract_symbol": "XYZC102O", "option_type": "call", "strike": 102.0, "expiry": "2026-10-16", "bid": 4.0,  "ask": 6.0,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35},
  {"contract_symbol": "XYZP115N", "option_type": "put",  "strike": 115.0, "expiry": "2026-11-20", "bid": 16.6, "ask": 17.0, "last": null, "volume": 50,  "open_interest": 200, "implied_volatility": 0.30},
  {"contract_symbol": "XYZP120O", "option_type": "put",  "strike": 120.0, "expiry": "2026-10-16", "bid": 41.0, "ask": 41.5, "last": null, "volume": 5,   "open_interest": 40,  "implied_volatility": 0.40},
  {"contract_symbol": "XYZP100O", "option_type": "put",  "strike": 100.0, "expiry": "2026-10-16", "bid": 5.2,  "ask": 5.4,  "last": null, "volume": 60,  "open_interest": 250, "implied_volatility": 0.36},
  {"contract_symbol": "XYZP85O",  "option_type": "put",  "strike": 85.0,  "expiry": "2026-10-16", "bid": 1.1,  "ask": 1.25, "last": null, "volume": 0,   "open_interest": 300, "implied_volatility": 0.35},
  {"contract_symbol": "XYZP70O",  "option_type": "put",  "strike": 70.0,  "expiry": "2026-10-16", "bid": 0.06, "ask": 0.16, "last": null, "volume": 2,   "open_interest": 60,  "implied_volatility": 0.50},
  {"contract_symbol": "XYZP100A", "option_type": "put",  "strike": 100.0, "expiry": "2026-08-01", "bid": 5.0,  "ask": 5.2,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35},
  {"contract_symbol": "XYZP100B", "option_type": "put",  "strike": 100.0, "expiry": "2026-10-16", "bid": 5.0,  "ask": 4.0,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35},
  {"contract_symbol": "XYZP100C", "option_type": "put",  "strike": 100.0, "expiry": "2026-11-20", "bid": 5.0,  "ask": 5.5,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 9.9},
  {"contract_symbol": "XYZP90O",  "option_type": "put",  "strike": 90.0,  "expiry": "2026-10-16", "bid": 3.5,  "ask": 3.7,  "last": null, "volume": 10,  "open_interest": 3,   "implied_volatility": 0.35},
  {"contract_symbol": "XYZP92O",  "option_type": "put",  "strike": 92.0,  "expiry": "2026-10-16", "bid": 3.0,  "ask": 5.0,  "last": null, "volume": 10,  "open_interest": 100, "implied_volatility": 0.35}
]}
```

Expected outcomes (verify in Step 3's checklist): long-call (target 120): 10 calls → 1/1/1/1/1 per stage → 5 qualified (C130 tops aggressive). long-put (target 80): 10 puts → 1/1/1/1/1 → 5 qualified; P120 deep-ITM clamp visible (baseline = intrinsic 40.00) and triggers ceilings (ask 41.5 > 40). bull-call-spread: Oct16 legs {95,105,110,130} → 6 pairs, 2 sanity-rejected (95/105, 95/110 — net cost ≥ width), 4 passed. bear-put-spread: Oct16 legs {120,100,85,70} → 6 pairs, 2 rejected ((120,100),(120,85)), 4 passed; top = (85,70).

- [ ] **Step 2: Implement matrix placement in report.py** — in `render`, after `_candidate_lines` for a band's index-0 candidate (or all when `p.matrix_all`):

```python
from datetime import date as _date
from .matrix import date_axis, matrix_lines, price_axis
from .valuation import scenario_leg_value, spread_scenario_value


def _matrix_block(value_fn, cost, spot, p, today, expiry) -> list[str]:
    prices = price_axis(spot, p.target_price)
    dates = date_axis(today, _date.fromisoformat(p.target_date), expiry)
    return ["", "P/L 矩陣（報酬率，Mid 進場）:"] + matrix_lines(value_fn, cost, prices, dates)
```

In `render`: `for j, v in enumerate(ranked[band]): lines += _candidate_lines(...); if j == 0 or p.matrix_all: c = v.contract; lines += _matrix_block(lambda S, d, c=c: scenario_leg_value(c, S, d, p), v.mid, snap.spot, p, today, _date.fromisoformat(c.expiry))`. In `render_spreads` analogously with `spread_scenario_value` and `sv.net_mid`, expiry from `sv.long_leg.expiry`. Footer additions per Interfaces.

- [ ] **Step 3: Generate + eyeball + freeze the four goldens**

```bash
python - <<'EOF'
import io, contextlib
from option_chaser.cli import main
CASES = [
    ("golden_long_call.txt",        ["--strategy", "long-call",        "--target-price", "120"]),
    ("golden_long_put.txt",         ["--strategy", "long-put",         "--target-price", "80"]),
    ("golden_bull_call_spread.txt", ["--strategy", "bull-call-spread", "--target-price", "120"]),
    ("golden_bear_put_spread.txt",  ["--strategy", "bear-put-spread",  "--target-price", "80"]),
]
for name, extra in CASES:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--target-date", "2026-08-28",
                   "--snapshot", "tests/fixtures/xyz_v2_snapshot.json"] + extra)
    assert rc == 0, (name, rc)
    open(f"tests/fixtures/{name}", "w", encoding="utf-8", newline="").write(buf.getvalue())
    print("written", name)
EOF
```

MANUALLY verify each golden before committing: filter counts per the fixture expectations above; every strategy header correct; matrix present on band #1s / spread #1 ONLY; matrix has `<現價>`/`<目標>` rows and `*` date column; expiry column values consistent with payoff (e.g. long-call C90 row at price 120: `(30 − 13.2)/13.2 → +127%`); P120 put candidate shows baseline 40.00 with all ceiling warnings; spread #1 (bear-put 85/70) shows 獲利上限 and pair stats 6/2/4; no box-drawing; no 壓力測試 section anywhere.

- [ ] **Step 4: Write the golden tests**

```python
# tests/test_golden_v2.py
import io
import contextlib
from pathlib import Path
import pytest
from option_chaser.cli import main

FIX = Path(__file__).parent / "fixtures"
CASES = [
    ("golden_long_call.txt", "long-call", "120"),
    ("golden_long_put.txt", "long-put", "80"),
    ("golden_bull_call_spread.txt", "bull-call-spread", "120"),
    ("golden_bear_put_spread.txt", "bear-put-spread", "80"),
]


def run(strategy, target, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--strategy", strategy, "--target-price", target,
                   "--target-date", "2026-08-28",
                   "--snapshot", str(FIX / "xyz_v2_snapshot.json"), *extra])
    return rc, buf.getvalue()


@pytest.mark.parametrize("golden,strategy,target", CASES)
def test_golden_byte_identical(golden, strategy, target):
    rc, out = run(strategy, target)
    assert rc == 0
    assert out == (FIX / golden).read_text(encoding="utf-8")


@pytest.mark.parametrize("golden,strategy,target", CASES)
def test_deterministic_rerun(golden, strategy, target):
    assert run(strategy, target)[1] == run(strategy, target)[1]


def test_matrix_all_adds_matrices():
    _, base = run("long-call", "120")
    _, full = run("long-call", "120", "--matrix-all")
    assert full.count("P/L 矩陣") > base.count("P/L 矩陣")


def test_no_box_drawing_all_strategies():
    for _, strategy, target in CASES:
        _, out = run(strategy, target)
        assert not any(0x2500 <= ord(ch) <= 0x257F for ch in out)


def test_no_stress_section():
    _, out = run("long-call", "120")
    assert "壓力測試" not in out
```

- [ ] **Step 5: Run full suite** — `python -m pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(v2): matrix placement in reports, v2 fixture, four goldens frozen"
```

---

### Task 9: yfinance adapter — both chain sides

**Files:**
- Modify: `option_chaser/data/yf.py`, `tests/test_yf_adapter.py`, `tests/fixtures/yf_rows.json`

**Interfaces:**
- `map_rows` unchanged signature; each row dict now REQUIRES `"option_type"` (`"call"|"put"`) injected by the fetch loop — remove the Task-1 temporary default (`str(r["option_type"])`, KeyError if missing is acceptable: fetch loop always injects).
- `fetch_chain`: for each expiry, map BOTH `chain.calls` (option_type "call") and `chain.puts` ("put").

- [ ] **Step 1: Update fixture & failing tests** — in `tests/fixtures/yf_rows.json` add `"option_type": "call"` to rows 1–2 and `"option_type": "put"` to row 3. Append test:

```python
def test_option_type_mapped():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snap = map_rows("XYZ", 100.0, "2026-07-15T21:30:00-04:00", rows)
    assert snap.contracts[0].option_type == "call"
    assert snap.contracts[2].option_type == "put"


def test_fetch_chain_maps_both_sides(monkeypatch):
    import sys, types
    fake = types.ModuleType("yfinance")

    class FakeCalls:
        def __init__(self, records): self._r = records
        def to_dict(self, kind): return self._r

    class FakeChain:
        def __init__(self):
            self.calls = FakeCalls([{"contractSymbol": "C1", "strike": 110.0,
                "bid": 3.0, "ask": 3.25, "lastPrice": 3.1, "volume": 152,
                "openInterest": 830, "impliedVolatility": 0.38}])
            self.puts = FakeCalls([{"contractSymbol": "P1", "strike": 90.0,
                "bid": 2.8, "ask": 3.0, "lastPrice": 2.9, "volume": 100,
                "openInterest": 400, "impliedVolatility": 0.40}])

    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = {"last_price": 100.0}
            self.options = ("2026-10-16",)
        def option_chain(self, expiry): return FakeChain()

    fake.Ticker = FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    from option_chaser.data.yf import fetch_chain
    snap = fetch_chain("XYZ")
    types_seen = {c.option_type for c in snap.contracts}
    assert types_seen == {"call", "put"} and len(snap.contracts) == 2
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement** — `map_rows` contract construction: `option_type=str(r["option_type"])`; `fetch_chain` loop:

```python
        for expiry in t.options:
            chain = t.option_chain(expiry)
            for side, frame in (("call", chain.calls), ("put", chain.puts)):
                for r in frame.to_dict("records"):
                    r["expiry"] = expiry
                    r["option_type"] = side
                    rows.append(r)
```

- [ ] **Step 4: Run** — adapter file passes; full suite green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(v2): yfinance adapter maps calls and puts"
```

---

### Task 10: README v2 + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README** — replace the strategy/flag portions with:

```markdown
## Strategies

    --strategy long-call          (default) bullish single leg
    --strategy long-put           bearish single leg
    --strategy bull-call-spread   bullish debit vertical (exhaustive same-expiry pairs)
    --strategy bear-put-spread    bearish debit vertical

Direction guard: bullish strategies need target > spot, bearish need target < spot
(override with --force). Band-first candidates include a price×date P/L matrix
(11 price rows × up to 7 date columns; add --matrix-all for every candidate).

## Removed in v2

    --min-days-after / --delay-days and the stress-test section are gone —
    the matrix supersedes them. Manage your own expiry buffer via --min-expiry.

## Key flags

    --min-expiry DATE     absolute expiry floor (expiry >= target-date is always enforced)
    --iv-shifts CSV       IV scenarios, default -0.2,0,0.2 (0 always included)
    --min-return X        L3 price ceiling = baseline value / (1+X)
    --max-spread-pct / --spread-floor / --min-oi / --min-volume   tradeability gates
    --delta-bands A,B     |Delta| banding thresholds, default 0.35,0.65
    --matrix-all          matrix on every candidate
    --md PATH             also write the report to a file

Snapshots are schema v2 (calls + puts). v1 snapshots must be re-fetched.
```

- [ ] **Step 2: Full suite** — `python -m pytest -q` → all pass.

- [ ] **Step 3: Live smoke, both families (network; note results, non-blocking on failure)**

```bash
python -c "from option_chaser.cli import main; main(['TLT','--target-price','110','--target-date','2027-12-31'])" | head -40
python -c "from option_chaser.cli import main; main(['TLT','--strategy','long-put','--target-price','70','--target-date','2027-06-30'])" | head -40
```

Expected: reports print with matrices; snapshots land in `snapshots/` (schema 2).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs(v2): README for strategies, matrix, retired flags"
```

---

## Self-Review Notes (author-checked)

- Spec coverage: §1.2/1.4 → T3 (flags/direction/stress removal), §2 → T3, §3.1/3.2 → T2, §3.3/3.4 → T5, §4.1 → T3, §4.2 → T4, §4.3 → T3+T6, §5 → T7+T8, §6 → T1+T9, §7 → T3+T6+T8, §8 → T1+T3, §9.1–9.11 → T2(1,2) T5(3) T4(4) T3(5,7,11) T7/T8(6,8) T1(9) T9(10), §9A contract enforced at codex-audit time, §11 acceptance mirrored by the four goldens + smoke.
- Suite stays green after every task; golden coverage intentionally absent between T3 and T8 (unit/integration tests cover the gap; noted in T3 commit message).
- Type consistency: `scenario_leg_value(c, S, at, p, shift)` defined T3, consumed T5/T7/T8; `SpreadValuation` fields defined T5, consumed T6/T8; `PairReport` defined T1, produced T4, rendered T6; `price_axis/date_axis/matrix_lines` defined T7, consumed T8; all AnalysisParams constructors in tests use v2 fields only after T3.
```
