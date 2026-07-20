# Option Chaser v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 情境韌性引擎（7 情境 maximin）＋完成度門檻掃描＋到期日分組比較表＋流程化 GUI 四步版面＋說明頁/辭典，per spec `docs/superpowers/specs/2026-07-20-option-chaser-v4-design.md`（codex 4 輪過審）。

**Architecture:** 新模組 `option_chaser/scenarios.py`（純函數，全部呼叫既有估值原語）與 `option_chaser/glossary.py`；`matrix.py` 價格軸改 4 錨點並新增縮圖降採樣；`service.py` 改名 `worst_return→natural_return`、CandidateView 擴充情境欄位、新增 ExpiryGroup 分組/標章/注入；`report.py` 每候選加韌性區段（golden ×4 重生成）；`webapp/app.py` 依 mockup v4 重排四步。

**Tech Stack:** Python 3.11+ stdlib（math/datetime/dataclasses）、Streamlit（GUI）、pytest + AppTest。零新依賴。

## Global Constraints（逐字自 spec）

- 機率語彙紅線固定禁詞清單（掃 GUI 原始碼與四份 golden）：`獲利機率`、`機率加權`、`勝率`、`POP`、`probability`、`期望報酬`、`expected profit`、`Sharpe`、`CVaR`。v4 新增文案不得含裸詞「機率」；既有 v1-v3 免責句（如「不算機率」）不在禁詞清單內。
- 不存在任何綜合分數欄位／函數。GUI 零金融公式（情境/門檻/摩擦全部 service 預算好，GUI 僅格式化）。
- 「情境最壞」欄名固定；不得寫成「最壞情況」「最大風險」；解釋文案用「非統計推論」。
- 排名/標章/抽樣/降採樣規則全部確定性；同快照同參數 = 逐位元同輸出。
- `worst_return`（v3 Natural 口徑）全 codebase 改名 `natural_return`；「情境最壞」一律綁 `candidate.scenario.worst_return`。
- 韌性 = min(S1..S7)，不做加權/平均/分位數；標章僅 🚀/🛡️/⚠/◀。
- 報告數字：百分比 1 位小數（`_pct`），金額 2 位（`_money`）。
- 測試權威跑法（RTK proxy 會誤報 "No tests collected"）：
  `"C:/Users/Rice/AppData/Local/Programs/Python/Python311/python.exe" -c "import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','-q'],capture_output=True,text=True); print(r.stdout[-3000:]); print(r.stderr[-2000:]); sys.exit(r.returncode)"`
- Windows：子行程需 `PYTHONUTF8=1`；PowerShell 5.1 無 `&&`。

---

### Task 1: scenarios.py — 七情境向量

**Files:**
- Create: `option_chaser/scenarios.py`
- Test: `tests/test_scenarios.py`

**Interfaces:**
- Consumes: `valuation.scenario_leg_value(c, S, at, p, shift)`, `valuation.spread_scenario_value(long, short, S, at, p, shift)`, `valuation.ContractValuation`, `valuation.SpreadValuation`, `models.AnalysisParams`
- Produces: `ScenarioVector(entries, worst_code, worst_return)`（frozen dataclass）; `scenario_vector(val, spot, today, p) -> ScenarioVector`（val 為 ContractValuation 或 SpreadValuation）

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scenarios.py
"""v4 spec §2.1/§2.2: seven-scenario resilience vector."""
from datetime import date

import pytest

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.scenarios import ScenarioVector, scenario_vector
from option_chaser.valuation import (evaluate_contract, evaluate_spread,
                                     scenario_leg_value, spread_scenario_value)


def _p(**kw):
    base = dict(strategy="long-call", target_price=105.0,
                target_date="2028-01-01", min_return=0.0)
    base.update(kw)
    return AnalysisParams(**base)


def _call(strike, expiry, bid, ask, iv, volume=10, oi=100):
    return OptionContract(
        contract_symbol=f"XYZ{expiry}C{strike}", strike=strike, expiry=expiry,
        bid=bid, ask=ask, last_price=(bid + ask) / 2, volume=volume,
        open_interest=oi, implied_volatility=iv, option_type="call")


TODAY = date(2026, 7, 1)
SPOT = 84.52


def test_single_leg_seven_entries_match_engine():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert [code for code, _ in sv.entries] == [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    tgt = date.fromisoformat(p.target_date)
    mid = v.mid
    # S1: S=spot at target_date, base IV
    exp_s1 = (scenario_leg_value(c, SPOT, tgt, p) - mid) / mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    # S2/S3: completion 50%/75%
    s50 = SPOT + 0.5 * (p.target_price - SPOT)
    s75 = SPOT + 0.75 * (p.target_price - SPOT)
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(c, s50, tgt, p) - mid) / mid)
    assert dict(sv.entries)["S3"] == pytest.approx(
        (scenario_leg_value(c, s75, tgt, p) - mid) / mid)
    # S6: envelope min over ALL iv_shifts (incl. base)
    exp_s6 = min(
        scenario_leg_value(c, p.target_price, tgt, p, sh) for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx((exp_s6 - mid) / mid)
    # S7: Natural cost (=Ask), base value at target
    base_val = scenario_leg_value(c, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base_val - c.ask) / c.ask)
    # worst = min, code = first minimum in S1..S7 order
    rets = [r for _, r in sv.entries]
    assert sv.worst_return == pytest.approx(min(rets))
    assert sv.worst_code == sv.entries[rets.index(min(rets))][0]


def test_delay_scenarios_arrive_before_expiry():
    """S4: expiry >= target+30 -> valued at arrive date with S=target."""
    c = _call(93.0, "2028-12-15", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = date.fromisoformat(p.target_date) + timedelta(days=30)
    exp = (scenario_leg_value(c, p.target_price, arrive, p) - v.mid) / v.mid
    assert dict(sv.entries)["S4"] == pytest.approx(exp)


def test_delay_scenario_expiry_before_arrive_interpolates():
    """v4 spec §2.2: expiry < target+90 -> payoff at interpolated price at expiry."""
    expiry = date(2028, 1, 21)          # target 2028-01-01 + 90 > expiry
    c = _call(93.0, expiry.isoformat(), 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    from datetime import timedelta
    arrive = date.fromisoformat(p.target_date) + timedelta(days=90)
    frac = (expiry - TODAY).days / (arrive - TODAY).days
    s_at_expiry = SPOT + (p.target_price - SPOT) * frac
    exp = (scenario_leg_value(c, s_at_expiry, expiry, p) - v.mid) / v.mid
    assert dict(sv.entries)["S5"] == pytest.approx(exp)


def test_spread_vector_uses_spread_engine_and_natural_cost():
    lng = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    p = _p(strategy="bull-call-spread")
    sv_val = evaluate_spread(lng, sht, SPOT, TODAY, p)
    sv = scenario_vector(sv_val, SPOT, TODAY, p)
    tgt = date.fromisoformat(p.target_date)
    exp_s1 = (spread_scenario_value(lng, sht, SPOT, tgt, p) - sv_val.net_mid) / sv_val.net_mid
    assert dict(sv.entries)["S1"] == pytest.approx(exp_s1)
    natural = lng.ask - sht.bid
    base = spread_scenario_value(lng, sht, p.target_price, tgt, p)
    assert dict(sv.entries)["S7"] == pytest.approx((base - natural) / natural)
    # S6 envelope: min over shifts of spread value (net vega can flip sign)
    exp_s6 = min(spread_scenario_value(lng, sht, p.target_price, tgt, p, sh)
                 for sh in p.iv_shifts)
    assert dict(sv.entries)["S6"] == pytest.approx(
        (exp_s6 - sv_val.net_mid) / sv_val.net_mid)


def test_bearish_completion_mirrors():
    """target < spot: S2 is halfway DOWN."""
    put = OptionContract(
        contract_symbol="XYZP70", strike=80.0, expiry="2028-01-21",
        bid=3.0, ask=3.4, last_price=3.2, volume=5, open_interest=50,
        implied_volatility=0.25, option_type="put")
    p = _p(strategy="long-put", target_price=70.0)
    v = evaluate_contract(put, SPOT, TODAY, p)
    sv = scenario_vector(v, SPOT, TODAY, p)
    s50 = SPOT + 0.5 * (70.0 - SPOT)
    tgt = date.fromisoformat(p.target_date)
    assert dict(sv.entries)["S2"] == pytest.approx(
        (scenario_leg_value(put, s50, tgt, p) - v.mid) / v.mid)
```

- [ ] **Step 2: Run tests, verify FAIL** — `ModuleNotFoundError: option_chaser.scenarios`

- [ ] **Step 3: Implement**

```python
# option_chaser/scenarios.py
"""v4 spec §2: seven-scenario resilience engine. Pure, deterministic.

Every valuation goes through the existing primitives scenario_leg_value /
spread_scenario_value (American clamp + [0, width] clamp included).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import AnalysisParams
from .valuation import (ContractValuation, SpreadValuation,
                        scenario_leg_value, spread_scenario_value)

SCENARIO_NAMES = {
    "S1": "不漲", "S2": "半程", "S3": "大半程", "S4": "晚30天",
    "S5": "晚90天", "S6": "IV最保守", "S7": "Natural成交",
}


@dataclass(frozen=True)
class ScenarioVector:
    entries: tuple[tuple[str, float], ...]   # (("S1", ret) ... ("S7", ret)) fixed order
    worst_code: str                          # first minimum in S1..S7 order
    worst_return: float


def _value_fn(val):
    """Uniform (S, at, shift) -> value callable for single legs and spreads."""
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        return (lambda S, at, p, shift=0.0:
                spread_scenario_value(lng, sht, S, at, p, shift)), val.net_mid, \
               (lng.ask - sht.bid), lng.expiry
    c = val.contract
    return (lambda S, at, p, shift=0.0:
            scenario_leg_value(c, S, at, p, shift)), val.mid, c.ask, c.expiry


def _delay_value(fn, spot: float, today: date, p: AnalysisParams,
                 expiry: date, delta_days: int) -> float:
    """Spec §2.2: linear path spot->target over [today, target+delta]."""
    arrive = date.fromisoformat(p.target_date) + timedelta(days=delta_days)
    d = min(arrive, expiry)
    frac = (d - today).days / (arrive - today).days
    s_at_d = spot + (p.target_price - spot) * frac
    return fn(s_at_d, d, p)


def scenario_vector(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams) -> ScenarioVector:
    fn, mid, natural, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    tgt = date.fromisoformat(p.target_date)

    def ret(value: float, cost: float) -> float:
        return (value - cost) / cost

    s_half = spot + 0.5 * (p.target_price - spot)
    s_most = spot + 0.75 * (p.target_price - spot)
    values = [
        ("S1", ret(fn(spot, tgt, p), mid)),
        ("S2", ret(fn(s_half, tgt, p), mid)),
        ("S3", ret(fn(s_most, tgt, p), mid)),
        ("S4", ret(_delay_value(fn, spot, today, p, expiry, 30), mid)),
        ("S5", ret(_delay_value(fn, spot, today, p, expiry, 90), mid)),
        ("S6", ret(min(fn(p.target_price, tgt, p, sh) for sh in p.iv_shifts),
                   mid)),
        ("S7", ret(fn(p.target_price, tgt, p), natural)),
    ]
    worst = min(r for _, r in values)
    code = next(c for c, r in values if r == worst)
    return ScenarioVector(entries=tuple(values), worst_code=code,
                          worst_return=worst)
```

- [ ] **Step 4: Run tests, verify PASS**
- [ ] **Step 5: Commit** — `feat(v4): seven-scenario resilience vector (scenarios.py)`

---

### Task 2: scenarios.py — completion_scan／曲線／保留率／摩擦

**Files:**
- Modify: `option_chaser/scenarios.py`
- Test: `tests/test_scenarios.py`（追加）

**Interfaces:**
- Produces: `completion_scan(val, spot, today, p) -> tuple[float | None, float | None]`（threshold, breakeven_price）; `completion_curve(val, spot, today, p) -> tuple[tuple[float, float], ...]`（k∈{0,.25,.5,.75,1} 五點報酬）; `friction(val) -> float`; `natural_cost(val) -> float`

- [ ] **Step 1: Write failing tests（追加到 tests/test_scenarios.py）**

```python
from option_chaser.scenarios import completion_curve, completion_scan, friction


def test_completion_scan_suffix_condition_long_call():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, be = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and 0.0 < k <= 1.0
    tgt = date.fromisoformat(p.target_date)
    # suffix property: every grid j in [k, 1] >= cost; k-0.001 violates
    for j in [k, (k + 1.0) / 2, 1.0]:
        s = max(SPOT + j * (p.target_price - SPOT), min(0.01 * SPOT, p.target_price))
        assert scenario_leg_value(c, s, tgt, p) >= v.mid - 1e-12
    s_prev = SPOT + (k - 0.001) * (p.target_price - SPOT)
    assert scenario_leg_value(c, s_prev, tgt, p) < v.mid
    assert be == pytest.approx(SPOT + k * (p.target_price - SPOT))


def test_completion_scan_hopeless_returns_none():
    """Cost above full-completion value -> (None, None)."""
    c = _call(120.0, "2028-01-21", 8.0, 9.0, 0.20)   # deep OTM, huge premium
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    assert completion_scan(v, SPOT, TODAY, p) == (None, None)


def test_completion_scan_already_breakeven_negative_k():
    """Deep ITM low-premium: threshold <= 0 (already at breakeven at k=0)."""
    c = _call(60.0, "2028-01-21", 24.0, 24.6, 0.18)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    k, _ = completion_scan(v, SPOT, TODAY, p)
    assert k is not None and k <= 0.0


def test_completion_scan_floor_extreme_bullish():
    """target >= 6*spot: k=-0.2 corner triggers floor min(0.01*spot, target)."""
    c = _call(3.0, "2028-01-21", 0.4, 0.6, 0.8)
    p = _p(target_price=15.0)
    spot = 2.0
    v = evaluate_contract(c, spot, TODAY, p)
    k, be = completion_scan(v, spot, TODAY, p)   # must not raise (S<=0 -> BS log)
    assert be is None or be > 0.0


def test_completion_scan_deep_bearish_k1_exact_target():
    """target < 0.01*spot: floor must NOT distort k=1 (S_1 == target exactly)."""
    put = OptionContract(
        contract_symbol="XYZP05", strike=5.0, expiry="2028-01-21",
        bid=4.0, ask=4.4, last_price=4.2, volume=5, open_interest=50,
        implied_volatility=0.9, option_type="put")
    p = _p(strategy="long-put", target_price=0.5)
    spot = 100.0
    floor = min(0.01 * spot, p.target_price)
    s1 = max(spot + 1.0 * (p.target_price - spot), floor)
    assert s1 == pytest.approx(p.target_price)


def test_completion_curve_identities():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    curve = completion_curve(v, SPOT, TODAY, p)
    assert [k for k, _ in curve] == [0.0, 0.25, 0.5, 0.75, 1.0]
    sv = scenario_vector(v, SPOT, TODAY, p)
    assert dict(curve)[0.0] == pytest.approx(dict(sv.entries)["S1"])   # k=0 == S1
    tgt = date.fromisoformat(p.target_date)
    base = (scenario_leg_value(c, p.target_price, tgt, p) - v.mid) / v.mid
    assert dict(curve)[1.0] == pytest.approx(base)                     # k=1 == baseline


def test_friction():
    c = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    p = _p()
    v = evaluate_contract(c, SPOT, TODAY, p)
    assert friction(v) == pytest.approx((4.4 - 4.2) / 4.2)
    lng = _call(93.0, "2028-01-21", 4.0, 4.4, 0.20)
    sht = _call(100.0, "2028-01-21", 1.8, 2.2, 0.22)
    sp = evaluate_spread(lng, sht, SPOT, TODAY, _p(strategy="bull-call-spread"))
    assert friction(sp) == pytest.approx(
        ((lng.ask - sht.bid) - sp.net_mid) / sp.net_mid)
```

- [ ] **Step 2: Run, verify FAIL**
- [ ] **Step 3: Implement（追加到 scenarios.py）**

```python
def natural_cost(val: ContractValuation | SpreadValuation) -> float:
    if isinstance(val, SpreadValuation):
        return val.long_leg.ask - val.short_leg.bid
    return val.contract.ask


def friction(val: ContractValuation | SpreadValuation) -> float:
    """(Natural - Mid) / Mid. Display cap handled by presentation layers."""
    mid = val.net_mid if isinstance(val, SpreadValuation) else val.mid
    return (natural_cost(val) - mid) / mid


def _grid_price(spot: float, target: float, k: float) -> float:
    """Spec §2.3: positive floor min(0.01*spot, target) keeps k=1 == target."""
    return max(spot + k * (target - spot), min(0.01 * spot, target))


def completion_scan(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams
                    ) -> tuple[float | None, float | None]:
    """Suffix-condition grid scan (spec §2.3): k* = smallest k such that
    value >= Mid cost at EVERY grid point in [k, 1.0]. Walk down from 1.0."""
    fn, mid, _, _ = _value_fn(val)
    tgt = date.fromisoformat(p.target_date)
    k_star = None
    for i in range(1000, -201, -1):          # k = 1.000 down to -0.200
        k = i / 1000.0
        s = _grid_price(spot, p.target_price, k)
        if fn(s, tgt, p) < mid:
            break
        k_star = k
    if k_star is None:                        # value(S_1.0) < cost
        return None, None
    return k_star, _grid_price(spot, p.target_price, k_star)


def completion_curve(val: ContractValuation | SpreadValuation, spot: float,
                     today: date, p: AnalysisParams
                     ) -> tuple[tuple[float, float], ...]:
    fn, mid, _, _ = _value_fn(val)
    tgt = date.fromisoformat(p.target_date)
    out = []
    for k in (0.0, 0.25, 0.5, 0.75, 1.0):
        s = _grid_price(spot, p.target_price, k)
        out.append((k, (fn(s, tgt, p) - mid) / mid))
    return tuple(out)
```

- [ ] **Step 4: Run tests（全 test_scenarios.py），verify PASS**
- [ ] **Step 5: Commit** — `feat(v4): completion scan (suffix condition), curve, friction`

---

### Task 3: matrix.py — 4 錨點價格軸 + 縮圖降採樣

**Files:**
- Modify: `option_chaser/matrix.py`（`price_axis` 簽名改為 `price_axis(spot, target, bullish)`）
- Modify: `option_chaser/service.py:110-118`、`option_chaser/report.py:130-133`（呼叫端補 `bullish` 參數：`is_bullish(p.strategy)`，自 `models` import）
- Test: `tests/test_matrix.py`（修改既有 + 追加）

**Interfaces:**
- Produces: `price_axis(spot, target, bullish) -> list[tuple[float, str]]`（11 列，4 錨點精確在列）; `thumbnail_cells(cells) -> tuple[tuple[float, ...], ...]`（4 價格列 × ≤5 日期欄）

- [ ] **Step 1: Write failing tests（tests/test_matrix.py 追加；既有 price_axis 測試改傳 bullish=True 並更新期望值）**

```python
def test_price_axis_v4_anchors_bullish():
    spot, target = 84.52, 105.0
    pts = price_axis(spot, target, bullish=True)
    vals = [v for v, _ in pts]
    assert len(vals) == 11
    overshoot, adverse = target * 1.10, spot * 0.90
    for anchor in (spot, target, overshoot, adverse):
        assert anchor in vals
    assert min(vals) == pytest.approx(adverse)
    assert max(vals) == pytest.approx(overshoot)


def test_price_axis_v4_anchors_bearish():
    spot, target = 84.52, 70.0
    pts = price_axis(spot, target, bullish=False)
    vals = [v for v, _ in pts]
    overshoot, adverse = target * 0.90, spot * 1.10
    for anchor in (spot, target, overshoot, adverse):
        assert anchor in vals
    assert min(vals) == pytest.approx(overshoot)
    assert max(vals) == pytest.approx(adverse)


def test_price_axis_v4_positive_clamp():
    pts = price_axis(2.0, 15.0, bullish=True)   # adverse=1.8 > 0.02 so no clamp
    assert all(v > 0 for v, _ in pts)


def test_price_axis_anchor_collision_dedup():
    """spot*0.9 colliding with a grid point must not duplicate rows."""
    pts = price_axis(100.0, 110.0, bullish=True)
    vals = [v for v, _ in pts]
    assert len(vals) == len(set(vals)) == 11


def test_thumbnail_cells_indices():
    from option_chaser.matrix import thumbnail_cells
    cells = tuple(tuple(float(r * 10 + c) for c in range(7)) for r in range(11))
    th = thumbnail_cells(cells)
    assert len(th) == 4                     # price rows [10,7,4,1] high-to-low
    assert th[0][0] == 100.0 and th[3][0] == 10.0
    assert len(th[0]) == 5                  # date cols [0, 1, 3, 5, 6] for n=7
    assert th[0] == (100.0, 101.0, 103.0, 105.0, 106.0)


def test_thumbnail_cells_few_dates_dedup():
    cells = tuple(tuple(float(r) for _ in range(2)) for r in range(11))
    th = thumbnail_cells(cells)
    assert len(th[0]) == 2                  # dedup: n=2 -> cols [0, 1]
```

- [ ] **Step 2: Run, verify FAIL**
- [ ] **Step 3: Implement**

`price_axis` 全文替換為：

```python
def price_axis(spot: float, target: float, bullish: bool) -> list[tuple[float, str]]:
    """v4 spec §4.3: anchors {spot, target, overshoot, adverse}; range = anchor hull."""
    overshoot = target * (1.10 if bullish else 0.90)
    adverse = spot * (0.90 if bullish else 1.10)
    anchors = sorted({spot, target, overshoot, adverse})
    lo = max(min(anchors), 0.01 * spot)
    hi = max(anchors)
    pts = [lo + (hi - lo) * i / 10.0 for i in range(11)]
    vals = _insert_anchors(pts, anchors)

    def label(v: float) -> str:
        s = ""
        if v == spot:
            s += "<現價>"
        if v == target:
            s += "<目標>"
        if v == overshoot:
            s += "<超標>"
        if v == adverse:
            s += "<深跌>"
        return s

    return [(v, label(v)) for v in vals]
```

（v4 新增 `<超標>`/`<深跌>` 標籤：GUI 以「label 非空 → 粗體列」判斷錨點，避免 GUI 自算 target×1.1 違反零公式紅線；CLI 矩陣同步顯示這些標記，golden 於 Task 6 吸收。測試追加：`test_price_axis_v4_anchor_labels` 斷言四錨點列 label 分別含 <現價>/<目標>/<超標>/<深跌>，且看跌方向 label 落在正確價位。）

注意 `_insert_anchors` 既有實作在錨點數 > 移除數時可能超過 11 列——錨點恰 4 個、每個移除 1 格點，總數不變（去重後 anchors 可能 <4，同理不變）。追加於檔尾：

```python
def thumbnail_cells(
    cells: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, ...], ...]:
    """v4 spec §4.4: 4 price rows [10,7,4,1] (high-to-low) x <=5 date cols."""
    n = len(cells[0])
    col_idx = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
    return tuple(
        tuple(cells[r][c] for c in col_idx) for r in (10, 7, 4, 1)
    )
```

呼叫端：`service._matrix_view` 內 `price_axis(spot, p.target_price)` → `price_axis(spot, p.target_price, is_bullish(p.strategy))`（models 已 export `is_bullish`）；`report._matrix_block` 同改（import `is_bullish` from `.models`）。

- [ ] **Step 4: Run 全套件** — test_matrix 全綠；**四份 golden 測試此時預期 FAIL**（軸改變）——golden 於 Task 6 重生成，本 task **允許 golden 測試暫紅**，在 commit message 註明。其餘測試（含 matrix_grid parity）必須綠。
- [ ] **Step 5: Commit** — `feat(v4): 4-anchor price axis + thumbnail downsample (goldens regenerate in later task)`

---

### Task 4: service.py — natural_return 改名 + CandidateView v4 欄位

**Files:**
- Modify: `option_chaser/service.py`、`webapp/app.py`（改名波及行 82/97）、`tests/test_service.py`（改名波及）
- Test: `tests/test_service_v4.py`（新建）

**Interfaces:**
- Consumes: Task 1/2 的 `scenario_vector`、`completion_scan`、`completion_curve`、`friction`
- Produces: `CandidateView` 追加欄位 `scenario: ScenarioVector`、`completion_curve: tuple[tuple[float, float], ...]`、`completion_threshold: float | None`、`breakeven_at_target: float | None`、`retention: float`、`friction: float`、`buffer_days: int`、`quote_warning: bool`、`theta_day_rate: float`（|淨Θ|/Mid成本）、`vega_per_pt: float`（淨Vega×0.01/Mid成本）、`decay_30d_return: float`（S=spot、IV 不變、today+30 估值之報酬；expiry ≤ today+30 時以到期日估）；`worst_return` 改名 `natural_return`（ComparisonRow 同步改名）。進階區三值必須 service 預算（GUI 零金融公式紅線），Task 7 GUI 僅格式化。

- [ ] **Step 1: Write failing tests**

```python
# tests/test_service_v4.py
"""v4 spec §3.1: CandidateView scenario fields (fixture snapshot, offline)."""
from datetime import date

import pytest

from option_chaser import service
from option_chaser.scenarios import (completion_scan, friction,
                                     scenario_vector)
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _request(strategies=("long-call", "bull-call-spread")):
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=110.0,
                                   target_date="2027-12-31", min_return=0.0),
        strategies=strategies)


def test_candidate_view_scenario_fields_consistent():
    result = service.run_offline(_request(), SNAP)
    ok = [r for r in result.results if r.status == "ok"]
    assert ok
    for res in ok:
        for cv in res.candidates:
            spot = result.snapshot.spot
            p = _params_for(result, res.strategy)
            expect = scenario_vector(cv.valuation, spot, result.today, p)
            assert cv.scenario == expect
            assert cv.friction == pytest.approx(friction(cv.valuation))
            k, be = completion_scan(cv.valuation, spot, result.today, p)
            assert cv.completion_threshold == k
            assert cv.breakeven_at_target == be
            assert cv.retention == pytest.approx(
                1.0 + dict(cv.scenario.entries)["S1"])
            expiry = (cv.valuation.long_leg.expiry
                      if hasattr(cv.valuation, "long_leg")
                      else cv.valuation.contract.expiry)
            assert cv.buffer_days == (
                date.fromisoformat(expiry)
                - date.fromisoformat(p.target_date)).days


def _params_for(result, strategy):
    import dataclasses
    return dataclasses.replace(result.request.base_params, strategy=strategy)


def test_natural_return_renamed():
    result = service.run_offline(_request(), SNAP)
    cv = next(r for r in result.results if r.status == "ok").candidates[0]
    assert hasattr(cv, "natural_return")
    assert not hasattr(cv, "worst_return")
    row = result.comparison[0]
    assert hasattr(row, "natural_return")


def test_quote_warning_friction_over_25pct():
    result = service.run_offline(_request(), SNAP)
    for res in result.results:
        for cv in res.candidates:
            legs_zero = _any_zero_volume(cv.valuation)
            assert cv.quote_warning == (legs_zero or cv.friction > 0.25)


def _any_zero_volume(val):
    if hasattr(val, "long_leg"):
        return val.long_leg.volume == 0 or val.short_leg.volume == 0
    return val.contract.volume == 0
```

- [ ] **Step 2: Run, verify FAIL**
- [ ] **Step 3: Implement** — service.py：
  1. `CandidateView.worst_return` → `natural_return`（欄位註解「(基準估值 − Natural成本)/Natural成本」）；`ComparisonRow.worst_return` → `natural_return`；`_comparison` 與兩個 result builder 同步。
  2. CandidateView 追加 8 欄；`_single_leg_result`/`_spread_result` 內建構處統一經 helper：

```python
def _v4_fields(val, spot: float, today: date, p: AnalysisParams) -> dict:
    sv = scenario_vector(val, spot, today, p)
    k, be = completion_scan(val, spot, today, p)
    fr = friction(val)
    if isinstance(val, SpreadValuation):
        expiry = val.long_leg.expiry
        zero_vol = val.long_leg.volume == 0 or val.short_leg.volume == 0
    else:
        expiry = val.contract.expiry
        zero_vol = val.contract.volume == 0
    return dict(
        scenario=sv,
        completion_curve=completion_curve(val, spot, today, p),
        completion_threshold=k, breakeven_at_target=be,
        retention=1.0 + dict(sv.entries)["S1"], friction=fr,
        buffer_days=(date.fromisoformat(expiry)
                     - date.fromisoformat(p.target_date)).days,
        quote_warning=zero_vol or fr > 0.25,
        theta_day_rate=abs(_net_theta(val)) / _mid_cost(val),
        vega_per_pt=_net_vega(val) * 0.01 / _mid_cost(val),
        decay_30d_return=_decay_30d(val, spot, today, p))
```

輔助：`_mid_cost(val)` = net_mid/mid；`_net_theta`/`_net_vega`：單腿取 `val.theta_per_day`/`val.vega_per_pct`；價差以 `leg_greeks` 對兩腿以現價重算差值（today 為基準，T=today→expiry）。`_decay_30d`：`d30 = min(today+30天, expiry)`，`(fn(spot, d30) − Mid成本)/Mid成本`（fn 同 scenarios._value_fn 取得）。三者各加一條 tests/test_service_v4.py 斷言（與直接引擎呼叫等值）。

  建構呼叫 `CandidateView(..., **_v4_fields(v, snap.spot, today, p))`。
  3. `webapp/app.py` 行 82/97 `cv.worst_return` → `cv.natural_return`；文案「最差進場」→「Natural 成交報酬」（此為過渡，Task 7 整體重寫 GUI）。
  4. `tests/test_service.py` 既有斷言中 `worst_return` 全部改 `natural_return`。
- [ ] **Step 4: Run 全套件** — 除 golden 外全綠。
- [ ] **Step 5: Commit** — `feat(v4): natural_return rename + CandidateView scenario fields`

---

### Task 5: service.py — ExpiryGroup 分組／標章／抽樣／注入

**Files:**
- Modify: `option_chaser/service.py`
- Test: `tests/test_grouping.py`（新建）

**Interfaces:**
- Produces: `ExpiryGroupRow(strategy, candidate, badges)`、`ExpiryGroup(expiry, buffer_days, rows, hidden_count)`；`AnalysisResult` 追加 `expiry_groups: tuple[ExpiryGroup, ...]`、`hidden_expiries: tuple[str, ...]`、`default_selection: tuple[str, str] | None`（(expiry, candidate_key)）；`candidate_key(cv) -> str`（如 `"long-call|93.0|2028-01-21"`／`"bull-call-spread|93.0|100.0|2028-01-21"`，決定性識別）

**分組來源**：全部合格候選＝各策略 StrategyResult 的**全體** CandidateView。注意：v3 起 candidates 僅前 3（單腿各級首選/價差前 3）——v4 分組需要「每到期日每策略最佳」，故 `_single_leg_result`/`_spread_result` 需在 ranked 全集上按到期日重取（不改 candidates 既有語意，另建全集清單傳給分組函數；對每個 (expiry, strategy) 取劇本報酬最高者建 CandidateView——CandidateView 建構含 matrix，僅對入組者建構以控成本）。

- [ ] **Step 1: Write failing tests**

```python
# tests/test_grouping.py
"""v4 spec §3.2: expiry grouping, sampling, badges, injection."""
from option_chaser import service
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _run(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=110.0,
                                   target_date="2027-12-31", min_return=0.0),
        strategies=strategies), SNAP)


def test_groups_ascending_and_rows_sorted():
    r = _run()
    assert r.expiry_groups
    expiries = [g.expiry for g in r.expiry_groups]
    assert expiries == sorted(expiries)
    for g in r.expiry_groups:
        rets = [row.candidate.baseline_return for row in g.rows]
        assert rets == sorted(rets, reverse=True)
        strategies = [row.strategy for row in g.rows]
        assert len(strategies) == len(set(strategies))  # per-strategy best only


def test_badges_global():
    r = _run()
    rows = [row for g in r.expiry_groups for row in g.rows]
    tops = [row for row in rows if "top_return" in row.badges]
    shields = [row for row in rows if "top_resilience" in row.badges]
    assert len(tops) == 1 and len(shields) == 1
    best = max(rows, key=lambda x: x.candidate.baseline_return)
    assert "top_return" in best.badges
    hard = max(rows, key=lambda x: x.candidate.scenario.worst_return)
    assert "top_resilience" in hard.badges


def test_default_selection_no_warning_and_visible():
    r = _run()
    assert r.default_selection is not None
    expiry, key = r.default_selection
    match = [row for g in r.expiry_groups if g.expiry == expiry
             for row in g.rows if service.candidate_key(row.candidate) == key]
    assert len(match) == 1
    all_rows = [row for g in r.expiry_groups for row in g.rows]
    if any(not row.candidate.quote_warning for row in all_rows):
        assert not match[0].candidate.quote_warning


def test_sampling_deterministic_six_expiries():
    """Unit test the sampler directly with 6 synthetic expiries."""
    exps = ["2028-01-21", "2028-03-17", "2028-06-16", "2028-09-15",
            "2028-12-15", "2029-06-15"]
    kept, hidden = service._sample_expiries(exps, "2027-12-31")
    assert len(kept) == 4
    assert kept[0] == "2028-01-21" and kept[1] == "2028-03-17"  # nearest 2
    assert set(kept) | set(hidden) == set(exps)
    assert kept == service._sample_expiries(exps, "2027-12-31")[0]  # deterministic
```

- [ ] **Step 2: Run, verify FAIL**
- [ ] **Step 3: Implement** — service.py 追加：

```python
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
```

分組主函數 `_build_groups(per_expiry_best, target_date)`：
1. `per_expiry_best`: dict[(expiry, strategy) -> CandidateView]（result builder 提供，見 Interfaces 說明）。
2. 抽樣 → 對 kept 每 expiry 建 rows（策略最佳、劇本報酬降冪）、`hidden_count` = 該 expiry 其他合格候選數（result builder 一併回傳 per-expiry qualified counts）。
3. 全場標章：top_return / top_resilience（tie-break 依 spec §3.2）；warning per row。
4. `default_selection`：無 warning 最高 baseline_return；全 warning → 全場第一。
5. 注入規則：top_return/top_resilience/default_selection 不在可見列 → (a) 組已展示：附加該列；(b) 組被抽掉：追加該組（組數可 >4，該 expiry 自 hidden 移除）。
6. `AnalysisResult` 填 `expiry_groups`（升冪）、`hidden_expiries`、`default_selection=(expiry, candidate_key(cv))`。

`_single_leg_result`/`_spread_result` 各回傳（或另存於 StrategyResult 新欄位 `expiry_best: tuple[CandidateView, ...]`＋`expiry_counts: dict[str, int]`——實作者可選 dataclass 欄位或平行回傳，唯須 frozen-safe：用 tuple）。

- [ ] **Step 4: Run 全套件**（golden 除外全綠）
- [ ] **Step 5: Commit** — `feat(v4): expiry grouping, global badges, sampling + injection`

---

### Task 6: report.py — 韌性區段 + Natural 改名 + 尾註 + Golden ×4 重生成

**Files:**
- Modify: `option_chaser/report.py`
- Modify: `tests/fixtures/golden_*.txt`（4 份重生成）
- Test: `tests/test_report.py`（追加區段測試）、既有 golden 測試恢復綠

**Interfaces:**
- Consumes: `scenarios.scenario_vector/completion_scan/completion_curve/friction/SCENARIO_NAMES`（report 層直接呼叫——非 GUI，紅線不禁止；與 service 同函數保證數字一致）

- [ ] **Step 1: Write failing test（tests/test_report.py 追加）**

```python
def test_resilience_section_present_and_formatted():
    from option_chaser import service
    from option_chaser.models import AnalysisParams
    result = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=110.0,
                                   target_date="2027-12-31", min_return=0.0),
        strategies=("long-call", "bull-call-spread")),
        "tests/fixtures/xyz_v2_snapshot.json")
    for res in result.results:
        if res.status != "ok":
            continue
        text = res.report_text
        for needle in ["韌性向量（7 情境，Mid 口徑）:", "- S1 不漲: ",
                       "◀ 情境最壞", "劇本完成度: ", "保本門檻: ",
                       "不漲保留率: ", "成交摩擦: "]:
            assert needle in text, (res.strategy, needle)
        assert "最差進場（Ask）基準報酬率" not in text
        if res.strategy == "long-call":
            assert "Natural 成交報酬" in text
```

- [ ] **Step 2: Run, verify FAIL**
- [ ] **Step 3: Implement** — `_candidate_lines`/`_spread_candidate_lines` 在買價指引後追加（共用 helper `_resilience_lines(val, spot, today, p)`）：

```python
def _resilience_lines(val, spot, today, p) -> list[str]:
    from .scenarios import (SCENARIO_NAMES, completion_curve, completion_scan,
                            friction, scenario_vector)
    sv = scenario_vector(val, spot, today, p)
    lines = ["", "韌性向量（7 情境，Mid 口徑）:"]
    for code, ret in sv.entries:
        mark = "   ◀ 情境最壞" if code == sv.worst_code else ""
        lines.append(f"- {code} {SCENARIO_NAMES[code]}: {_pct(ret)}{mark}")
    curve = completion_curve(val, spot, today, p)
    lines.append("劇本完成度: " + " | ".join(
        f"{int(k * 100)}%→{_pct(r)}" for k, r in curve))
    k, be = completion_scan(val, spot, today, p)
    if k is None:
        thr = "— ⚠劇本全成仍不保本"
    elif k <= 0:
        thr = "0%（已保本）"
    else:
        thr = f"完成 {_pct(k)}（目標日保本價 ${_money(be)}，基準IV）"
    retention = 1.0 + dict(sv.entries)["S1"]
    lines.append(f"保本門檻: {thr} | 不漲保留率: {_pct(retention)}"
                 f" | 成交摩擦: {_pct(min(friction(val), 9.99))}")
    return lines
```

  - S5（或 S4）發生 `expiry < arrive` 時該行尾加 `（合約先到期，內插價 payoff）`——helper 需比對 expiry 與 target+Δ。
  - 「最差進場（Ask）基準報酬率」行改「Natural 成交報酬」（單腿）；價差候選行文案同步（若有）。
  - `_footer_lines` 追加 4 行（spec §5 尾註：7 情境定義一行、線性延遲路徑假設、保本門檻掃描定義（後綴條件）、「情境最壞＝7 個固定情境的最低值，屬透明情境集合的最壞值，非統計推論、亦非所有可能情況的最壞」）。措辭不得含裸詞「機率」。
  - render/render_spreads 需將 `snap.spot`/`today` 傳入 `_candidate_lines`（簽名已含 snap；today 需補傳——依現行簽名調整）。
- [ ] **Step 4: 重生成四份 golden** — 跑 golden 生成腳本（既有慣例：以 fixture snapshot 跑 CLI/render 寫回 fixtures），**人工核對清單**寫入 commit message：新軸 11 列含 4 錨點、韌性區段 7 行、完成度 5 點、門檻/保留率/摩擦行、Natural 改名、尾註 4 新行、無禁詞。
- [ ] **Step 5: Run 全套件** — 全綠（golden 恢復）。決定性重跑一次確認逐位元。
- [ ] **Step 6: Commit** — `feat(v4): CLI resilience section + goldens regenerated (manual checklist in message)`

---

### Task 7: glossary.py + GUI 四步重構

**Files:**
- Create: `option_chaser/glossary.py`
- Modify: `webapp/app.py`（整體重排）
- Test: `tests/test_webapp_v4.py`（AppTest，新建；沿用既有 subprocess/inspect 模式跑 AppTest）

**Interfaces:**
- Consumes: `AnalysisResult.expiry_groups/hidden_expiries/default_selection`、`candidate_key`、`matrix.thumbnail_cells`、`GLOSSARY`
- Produces: GUI 內部 helper `_esc(text) -> str`（`$`→`\$`）、`_abbr(term) -> str`（`<abbr title="{GLOSSARY[term]}">{term}</abbr>`）、`_thumb_html(cv) -> str`、`_badge_str(row) -> str`

- [ ] **Step 1: glossary.py**

```python
# option_chaser/glossary.py
"""v4 spec §4.6: single-source glossary feeding tooltips and the help page."""
GLOSSARY: dict[str, str] = {
    "劇本報酬": "劇本完整成立（目標日到達目標價）時的模型報酬率，Mid 進場。",
    "情境最壞": "7 個固定壓力情境中最低的報酬率。屬透明情境集合的最壞值，非統計推論。",
    "Natural 成交報酬": "以吃單價成交（買付 Ask、賣收 Bid）時的劇本報酬率。",
    "成交摩擦": "Mid 與吃單價的落差佔 Mid 的比例，衡量進場成本劣化。",
    "完成度門檻": "劇本至少要走完的比例；達門檻後任何更高完成度都不虧（目標日、基準 IV）。",
    "不漲保留率": "目標日股價不動時，剩餘價值佔進場成本的比例。",
    "到期緩衝": "到期日晚於劇本日的天數；緩衝越大，時間容錯越高。",
    "保本價": "目標日剛好不虧的股價（基準 IV、Mid 進場）。",
    "Mid": "買賣報價中點，本工具的基準進場價。",
    "Natural": "直接吃對手單的價格：買付 Ask、賣收 Bid。",
    "BCS": "Bull Call Spread（看漲垂直價差）：買低履約價 Call、賣高履約價 Call。",
    "BPS": "Bear Put Spread（看跌垂直價差）：買高履約價 Put、賣低履約價 Put。",
    "Delta": "股價每漲 $1，權利金約變動的金額；價差為兩腿淨值。",
    "Theta": "每天流失的時間價值（其他條件不變）。",
    "Vega": "IV 每變 1 個百分點，權利金約變動的金額。",
    "IV": "隱含波動率：市場價格反推的波動預期。",
    "獲利上限": "價差的最大獲利 = 寬度 − 淨成本；到期價超過賣腿後不再增加。",
    "收斂": "價差兩腿價值隨到期日接近而向內在價值靠攏的過程。",
}
```

- [ ] **Step 2: webapp/app.py 重構**（依 mockup v4；以下為結構契約，實作照 spec §4）
  - **Step 1 chips**：`result` 存在時表單收進 `st.expander("✎ 修改劇本", expanded=False)`，上方一行 chips（symbol/現價/目標±%/日期/策略）。
  - **Step 2 主圖**：`st.session_state["selected_key"]` 預設 `default_selection`；渲染該候選 heatmap（沿用 heatmap_html；左軸已是純價格，錨點列 `<b>`——`MatrixView.prices` 的 label 非空即錨點列，另 overshoot/adverse 無 label，判斷改為「值 ∈ {spot, target, overshoot, adverse}」由 service 傳；簡化：heatmap_html 接受 `bold_prices: set[float]`，service 端 MatrixView 不改，GUI 由 `row.candidate` 對應 p 計算錨點集？——**紅線：GUI 不得算 target×1.1**。解法：`price_axis` 回傳 label 擴充：overshoot 標 `<超標>`、adverse 標 `<深跌>`（看跌時 overshoot 在下、adverse 在上，label 文字同）。此為 Task 3 的一部分——**在 Task 3 實作 label 擴充並更新 golden 期望**（golden 於 Task 6 重生成時一併吸收）。GUI 以「label 非空 → 粗體」判斷。）
  - **Step 3 分組表**：迭代 `result.expiry_groups`；組標題 `f"{g.expiry} 到期（緩衝 +{g.buffer_days} 天）— {注記}"`，注記規則 <45「收斂完全、容錯最低」/ 45–180「中庸帶」/ >180「收斂不完全、容錯最高」（此為文案分級非金融公式，GUI 可判）。每列：badges（🚀🛡️⚠◀）、組合名、`_thumb_html`（`thumbnail_cells(cv.matrix.cells)` 色塊 div，色 `cell_color`）、劇本報酬、情境最壞（`cv.scenario.worst_return`）、不漲保留率、摩擦（>25% 加 ⚠）。每列 `st.button("選看", key=f"sel-{key}")` → `selected_key` 切換。組尾 hidden_count 行；表尾 hidden_expiries 數量行。
  - **Step 4 三 expander**：韌性表（7 行，worst 列紅底 HTML）＋完成度曲線表＋門檻行；散點 SVG（自產：viewBox 600×360，X=worst_return、Y=baseline_return，Pareto 前緣線；全部數字來自 candidates，GUI 僅座標映射——座標縮放屬展示非金融公式）；Greeks 與流動性（沿用 v3 詳細資料 + report_text）。
  - **`_esc`**：所有含金額的 `st.markdown` 文字經 `text.replace("$", "\\$")`。
  - 全 GUI 用詞經 `_abbr` 包裝主要欄名。
- [ ] **Step 3: AppTest 測試**（tests/test_webapp_v4.py；沿用既有 subprocess 隔離模式）：分組表存在（組標題字串）、預設選中無⚠（構造 fixture 快照斷言 selected 初值 == default_selection）、點列切換（AppTest button click 後 selected_key 變更）、三 expander label 存在、`\$` 出現於輸出、abbr title 來自 GLOSSARY。
- [ ] **Step 4: Run 全套件**，verify PASS
- [ ] **Step 5: Commit** — `feat(v4): glossary + four-step GUI (grouped comparison, thumbnails, badges)`

---

### Task 8: 說明頁 + 紅線掃描測試 + CLI/GUI 一致性測試

**Files:**
- Create: `webapp/pages/1_說明.py`
- Test: `tests/test_redlines.py`、`tests/test_parity_v4.py`

- [ ] **Step 1: 說明頁** — 三步教學（寫劇本／看主圖／比候選，文案依 mockup v4 說明頁）＋名詞表（`for term, desc in GLOSSARY.items()`）＋免責三條＋模型假設四條（q=0、IV 恆定、線性延遲路徑、歐式+美式鉗制）。純靜態，無計算。
- [ ] **Step 2: 紅線掃描測試**

```python
# tests/test_redlines.py
"""v4 spec §6.1: banned-vocabulary scan over GUI sources and goldens."""
from pathlib import Path

BANNED = ["獲利機率", "機率加權", "勝率", "POP", "probability",
          "期望報酬", "expected profit", "Sharpe", "CVaR"]
TARGETS = [Path("webapp/app.py"), Path("webapp/pages/1_說明.py"),
           Path("option_chaser/glossary.py"),
           *sorted(Path("tests/fixtures").glob("golden_*.txt"))]


def test_no_banned_vocabulary():
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        for term in BANNED:
            assert term not in text, f"{term!r} found in {path}"


def test_new_copy_avoids_bare_probability_word():
    """v4-new files must not contain the bare word 機率 at all."""
    for path in [Path("option_chaser/glossary.py"),
                 Path("webapp/pages/1_說明.py"),
                 Path("option_chaser/scenarios.py")]:
        assert "機率" not in path.read_text(encoding="utf-8"), path
```

- [ ] **Step 3: 一致性測試**（tests/test_parity_v4.py）— 同 fixture 快照：service 之 `cv.scenario.entries` 各值格式化為 `_pct` 後，逐一出現在該候選的 `report_text` 韌性區段；門檻/保留率/摩擦行同（字串包含斷言——鎖 GUI 資料源與 CLI 報告同數字）。
- [ ] **Step 4: Run 全套件**，verify PASS
- [ ] **Step 5: Commit** — `feat(v4): help page + redline scan + CLI/GUI parity tests`

---

### Task 9: README + 收尾驗證

**Files:**
- Modify: `README.md`（Web GUI 節：四步版面、7 情境、分組比較、說明頁；「怎麼讀報告」補韌性區段一段；模型限制補線性延遲路徑）
- Modify: `pyproject.toml`（僅若需要——本版無新依賴，預期不動）

- [ ] **Step 1: README 更新**（中英兩節同步；不加機率語彙）
- [ ] **Step 2: 全套件權威跑法執行**，記錄測試數（預期 ≥155）
- [ ] **Step 3: 決定性驗證** — 同 fixture 兩次 render 逐位元相同
- [ ] **Step 4: Commit** — `docs(v4): README for scenario resilience + grouped comparison`

---

## 完成後

最終 whole-branch review（最強模型）→ merge → 依 spec §7A 執行 codex-audit（DC/AC/SL）→ push。
