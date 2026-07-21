# Option Chaser v5 — 多劇本工作區與腳本地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 v5 spec（`docs/superpowers/specs/2026-07-21-option-chaser-v5-design.md`，codex APPROVED）：劇本持久化（store）、工作區編排（workspace）、結果全量 JSON 契約、v4 四步渲染抽出共用、多劇本工作區 GUI 頁。

**Architecture:** 新增三個純 stdlib 模組（`vocabulary.py` 常數、`store.py` 檔案層、`workspace.py` 編排層）＋ `webapp/render.py`（四步渲染純函數，dict 介面）＋新 GUI 頁 `webapp/pages/0_劇本工作區.py`。事件日誌 events.jsonl 是唯一真實來源；scenario status 是快取（兩型不一致處理）；groups.json 是全量可重建快取。估值引擎（service 及以下）除抽出 `fetch_and_save` 外零改動。

**Tech Stack:** Python ≥3.11 stdlib（store/workspace/vocabulary 零第三方依賴）、Streamlit（GUI）、pytest + streamlit.testing.v1 AppTest。

**Branch:** `feature/v5-workspace`（自 master 開出；第一個 task 的第一步建立）。

## Global Constraints

（每個 task 隱含遵守；違反即 review 紅線）

1. **機率紅線**：新檔案（store.py / workspace.py / vocabulary.py / render.py / 0_劇本工作區.py）不得出現裸詞「機率」，不得出現 BANNED 清單詞（見 tests/test_redlines.py）。無 POP/期望值/Sharpe/分數。
2. **GUI 零金融公式**：佔本金%、天數、max_profit 等全部由 `store.serialize_result` 預算入 result dict；GUI 僅格式化。
3. **store 零 wall-clock**：store.py 所有函數不呼叫 `datetime.now()`/`date.today()`；時間（events ts、observed 日期）一律由呼叫端（workspace 層或測試）顯式傳入。workspace 層允許取 wall-clock。
4. **原子寫入**：所有檔案寫入一律 temp 檔（`<target>.tmp`）＋ `os.replace`；events.jsonl 追加 = 讀全文＋追加一行＋原子替換。UTF-8。
5. **寫入次序（spec §2.5）**：任何變更操作＝先 append 事件，再改衍生檔。唯一例外：analyze 先落 result 檔、後補 `ANALYSIS_COMPLETED`。
6. **投影次序權威＝events.jsonl 行序**；`ts` 僅 metadata，禁止用 `ts` 比較（spec §2.3）。
7. **決定性**：同 snapshot＋同 params＋同 capital → serialize_result 輸出逐位元相同（`json.dumps(..., sort_keys=True, ensure_ascii=False)`）。
8. **既有回歸**：v4 全套件（master 現有 177 tests）不改而綠；`webapp/app.py` 快速分析視圖行為與渲染輸出不變。
9. **事件值域**：寫入 events.jsonl 的 event 值必須 ∈ `vocabulary.EVENT_TYPES_V5`（v7 預留 enum 在 v5 拒寫）。
10. Windows 相容：檔名不得含 `:`（snapshot_ts 用 `fetched_at.replace(":", "")`）。
11. 每 task 至少一個 commit；訊息格式 `feat(v5): ...` / `test(v5): ...` / `refactor(v5): ...`。

## File Structure

```
option_chaser/
  __init__.py            ← 修改：加 __version__ = "0.5.0"（現為空檔）
  vocabulary.py          ← 新增（Task 1）：狀態/事件/動作常數
  store.py               ← 新增（Task 2-5）：檔案層（scenario/events/groups/constraints/result 序列化）
  workspace.py           ← 新增（Task 7-8）：編排層（CRUD、對帳、分析）
  service.py             ← 修改（Task 6）：抽出 fetch_and_save；run 行為不變
webapp/
  app.py                 ← 修改（Task 9）：渲染函數移至 render.py，改走 dict 視圖；流程/session 邏輯不動
  render.py              ← 新增（Task 9）：四步渲染純函數（dict 介面）
  pages/0_劇本工作區.py   ← 新增（Task 10）
  pages/1_說明.py         ← 修改（Task 11）：工作區概念一節
option_chaser/glossary.py ← 修改（Task 11）：新增 5 詞
tests/
  test_vocabulary.py      ← Task 1
  test_store_scenario.py  ← Task 2
  test_store_events.py    ← Task 3
  test_store_groups.py    ← Task 4
  test_store_serialize.py ← Task 5
  test_service_fetch.py   ← Task 6
  test_workspace.py       ← Task 7
  test_workspace_analyze.py ← Task 8
  test_webapp_workspace.py  ← Task 10
  test_redlines.py        ← 修改（Task 11）：TARGETS 擴 4 檔
compose.yaml              ← 修改（Task 11）：掛 ./workspace
.gitignore                ← 修改（Task 11）：加 workspace/
README.md                 ← 修改（Task 11）：多劇本工作區章節
```

**共用 fixture 基準**（Task 5/8/10 使用，與既有測試一致）：
- `tests/fixtures/xyz_v4_six_expiries.json`（symbol XYZ、spot 100 附近、六個到期日）
- 分析參數基準：`target_price=120.0`、`target_date="2026-08-01"`、strategies `("long-call",)` 或 `("long-call","bull-call-spread")`
- `tests/fixtures/xyz_v4_all_warning.json`（data_quality 兩態測試的變體原料）

---

### Task 1: vocabulary.py 與 `__version__`

**Files:**
- Create: `option_chaser/vocabulary.py`
- Modify: `option_chaser/__init__.py`（現為空檔）
- Test: `tests/test_vocabulary.py`

**Interfaces:**
- Produces: `SCENARIO_STATUSES: tuple[str,...]`、`EVENT_TYPES_V5: tuple[str,...]`（5 種）、`EVENT_TYPES_V7_RESERVED: tuple[str,...]`（5 種）、`EVENT_TYPES = EVENT_TYPES_V5 + EVENT_TYPES_V7_RESERVED`、`ACTION_TYPES: tuple[str,...]`（11 種）、`RELATION_CHOICES: tuple[str,...]`（4 種）、`option_chaser.__version__ == "0.5.0"`。後續所有 task 寫事件/狀態必須引用本模組常數。

- [ ] **Step 0: 開分支**

```bash
git checkout master && git checkout -b feature/v5-workspace
```

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_vocabulary.py
"""v5 spec §6: 詞彙表常數（文件＋常數，零引擎）。"""
import option_chaser
from option_chaser import vocabulary as voc


def test_version():
    assert option_chaser.__version__ == "0.5.0"


def test_statuses():
    assert voc.SCENARIO_STATUSES == ("Active", "Reached", "Expired", "Invalidated")


def test_event_types_v5():
    assert voc.EVENT_TYPES_V5 == (
        "SCENARIO_CREATED", "STATUS_CHANGED", "ANALYSIS_COMPLETED",
        "GROUP_RELATION_CONFIRMED", "SCENARIO_DELETED")


def test_event_types_v7_reserved():
    assert voc.EVENT_TYPES_V7_RESERVED == (
        "PRICE_REACHED", "TARGET_DATE_ARRIVED", "EXPIRY_BUFFER_LOW",
        "LIQUIDITY_DEGRADED", "REANALYSIS_REQUESTED")
    assert voc.EVENT_TYPES == voc.EVENT_TYPES_V5 + voc.EVENT_TYPES_V7_RESERVED


def test_action_types():
    assert voc.ACTION_TYPES == (
        "HOLD", "OPEN", "ADD", "REDUCE", "CLOSE", "RECOVER_PRINCIPAL",
        "KEEP_RUNNER", "ROLL_TO_NEXT_MILESTONE", "SWITCH_SCENARIO",
        "HOLD_CASH", "RERUN_ANALYSIS")
    assert len(voc.ACTION_TYPES) == 11


def test_relation_choices():
    assert voc.RELATION_CHOICES == (
        "milestone-path", "independent", "exclusive", "undefined")


def test_all_tuples_of_str():
    for t in (voc.SCENARIO_STATUSES, voc.EVENT_TYPES, voc.ACTION_TYPES,
              voc.RELATION_CHOICES):
        assert isinstance(t, tuple) and all(isinstance(x, str) for x in t)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_vocabulary.py -v`
Expected: FAIL（`ImportError`/`AttributeError`）

- [ ] **Step 3: 實作**

```python
# option_chaser/vocabulary.py
"""v5 spec §6: State/Event/Action 詞彙表（文件＋常數，零引擎邏輯）。

- EVENT_TYPES_V5: v5 生效 5 種（store/workspace 寫事件僅允許這些）。
- EVENT_TYPES_V7_RESERVED: v7 預留 5 種（本版僅常數定義，寫入被拒）。
- ACTION_TYPES: 11 種，v5 全部僅文件用途（無任何程式碼觸發）。
"""
from __future__ import annotations

SCENARIO_STATUSES: tuple[str, ...] = ("Active", "Reached", "Expired", "Invalidated")

EVENT_TYPES_V5: tuple[str, ...] = (
    "SCENARIO_CREATED", "STATUS_CHANGED", "ANALYSIS_COMPLETED",
    "GROUP_RELATION_CONFIRMED", "SCENARIO_DELETED")

EVENT_TYPES_V7_RESERVED: tuple[str, ...] = (
    "PRICE_REACHED", "TARGET_DATE_ARRIVED", "EXPIRY_BUFFER_LOW",
    "LIQUIDITY_DEGRADED", "REANALYSIS_REQUESTED")

EVENT_TYPES: tuple[str, ...] = EVENT_TYPES_V5 + EVENT_TYPES_V7_RESERVED

ACTION_TYPES: tuple[str, ...] = (
    "HOLD", "OPEN", "ADD", "REDUCE", "CLOSE", "RECOVER_PRINCIPAL",
    "KEEP_RUNNER", "ROLL_TO_NEXT_MILESTONE", "SWITCH_SCENARIO",
    "HOLD_CASH", "RERUN_ANALYSIS")

RELATION_CHOICES: tuple[str, ...] = (
    "milestone-path", "independent", "exclusive", "undefined")
```

```python
# option_chaser/__init__.py（整檔）
__version__ = "0.5.0"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_vocabulary.py -v`
Expected: 6 passed

- [ ] **Step 5: 既有回歸不破**

Run: `python -m pytest -q`
Expected: 全綠（177 + 6）

- [ ] **Step 6: Commit**

```bash
git add option_chaser/vocabulary.py option_chaser/__init__.py tests/test_vocabulary.py
git commit -m "feat(v5): vocabulary constants + __version__ 0.5.0"
```

---

### Task 2: store 第一層 — 原子寫入、Scenario 實體、id 規則、constraints

**Files:**
- Create: `option_chaser/store.py`
- Test: `tests/test_store_scenario.py`

**Interfaces:**
- Consumes: `vocabulary.SCENARIO_STATUSES`
- Produces（後續 task 依賴的精確簽名）:
  - `class WorkspaceIntegrityError(Exception)`
  - `@dataclass(frozen=True) Scenario(schema_version:int, id:str, symbol:str, direction:str, target_price:float, target_date:str, created_at:str, notes:str, group_id:str, status:str, strategies:tuple[str,...])`
  - `_atomic_write_text(path: Path, text: str) -> None`（temp `.tmp` + `os.replace`）
  - `atomic_write_json(path: Path, obj) -> None`（`json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)`）
  - `scenario_id(symbol: str, target_price: float, target_date: str, existing_ids: set[str]) -> str`
  - `scenario_path(ws_root, sid) -> Path`＝`<ws>/scenarios/<sid>.json`
  - `save_scenario(ws_root, sc: Scenario) -> None`／`load_scenario(path) -> Scenario`／`list_scenario_files(ws_root) -> list[Path]`（依檔名排序）
  - `load_constraints(ws_root) -> dict`（缺檔→`{"schema_version": 1, "total_capital": None}`）／`save_constraints(ws_root, total_capital: float|None) -> None`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_store_scenario.py
"""v5 spec §2.1/§2.2/§2.6 + §7.1: Scenario round-trip、id 決定性、原子寫入、constraints。"""
import json
import os
from pathlib import Path

import pytest

from option_chaser import store
from option_chaser.store import Scenario


def _sc(**kw):
    base = dict(schema_version=1, id="TLT-105-202801", symbol="TLT",
                direction="bullish", target_price=105.0,
                target_date="2028-01-01", created_at="2026-07-21T00:00:00+00:00",
                notes="", group_id="G-TLT", status="Active",
                strategies=("long-call", "bull-call-spread"))
    base.update(kw)
    return Scenario(**base)


def test_scenario_round_trip(tmp_path):
    sc = _sc()
    store.save_scenario(tmp_path, sc)
    loaded = store.load_scenario(store.scenario_path(tmp_path, sc.id))
    assert loaded == sc
    assert isinstance(loaded.strategies, tuple)


def test_scenario_id_rules():
    assert store.scenario_id("TLT", 105.0, "2028-01-01", set()) == "TLT-105-202801"
    assert store.scenario_id("TLT", 92.5, "2028-01-01", set()) == "TLT-92p5-202801"


def test_scenario_id_collision_deterministic():
    existing = {"TLT-105-202801"}
    assert store.scenario_id("TLT", 105.0, "2028-01-01", existing) == "TLT-105-202801-2"
    existing.add("TLT-105-202801-2")
    assert store.scenario_id("TLT", 105.0, "2028-01-01", existing) == "TLT-105-202801-3"


def test_atomic_write_uses_tmp_and_replace(tmp_path, monkeypatch):
    """spec §7.1: 以「temp 檔命名規則＋replace 呼叫」單元鎖定。"""
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", spy)
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"a": 1})
    assert len(calls) == 1
    src, dst = calls[0]
    assert src.endswith(".json.tmp") and dst == str(target)
    assert not (tmp_path / "x.json.tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_atomic_write_interruption_leaves_no_target(tmp_path, monkeypatch):
    """寫入中斷（replace 前爆炸）不留半檔。"""
    def boom(src, dst):
        raise OSError("interrupted")

    monkeypatch.setattr(store.os, "replace", boom)
    target = tmp_path / "y.json"
    with pytest.raises(OSError):
        store.atomic_write_json(target, {"a": 1})
    assert not target.exists()


def test_constraints_two_states(tmp_path):
    assert store.load_constraints(tmp_path) == {
        "schema_version": 1, "total_capital": None}
    store.save_constraints(tmp_path, 100000.0)
    assert store.load_constraints(tmp_path)["total_capital"] == 100000.0
    store.save_constraints(tmp_path, None)
    assert store.load_constraints(tmp_path)["total_capital"] is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_store_scenario.py -v`
Expected: FAIL（no module `option_chaser.store`）

- [ ] **Step 3: 實作**

```python
# option_chaser/store.py
"""v5 spec §2/§3: 工作區檔案層。純 stdlib、零 wall-clock（時間由呼叫端傳入）。

events.jsonl 是唯一真實來源；scenario 檔的 status 欄位是快取；
groups.json 是全量可重建快取。所有寫入 temp 檔＋os.replace 原子替換。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path


class WorkspaceIntegrityError(Exception):
    """快取與事件投影不一致（竄改型，spec §2.2）。"""


@dataclass(frozen=True)
class Scenario:
    schema_version: int
    id: str
    symbol: str
    direction: str          # "bullish" | "bearish"
    target_price: float
    target_date: str        # YYYY-MM-DD
    created_at: str         # ISO 8601 UTC
    notes: str
    group_id: str
    status: str             # vocabulary.SCENARIO_STATUSES
    strategies: tuple[str, ...]


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    _atomic_write_text(
        Path(path),
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


# ---------- Scenario ----------

def scenario_id(symbol: str, target_price: float, target_date: str,
                existing_ids: set[str]) -> str:
    """spec §2.2: {symbol}-{target:g 且 '.'→'p'}-{yyyymm}; 撞名 -2、-3（決定性）。"""
    price = format(target_price, "g").replace(".", "p")
    base = f"{symbol}-{price}-{target_date[:4]}{target_date[5:7]}"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


def scenario_path(ws_root, sid: str) -> Path:
    return Path(ws_root) / "scenarios" / f"{sid}.json"


def save_scenario(ws_root, sc: Scenario) -> None:
    atomic_write_json(scenario_path(ws_root, sc.id), dataclasses.asdict(sc))


def load_scenario(path) -> Scenario:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["strategies"] = tuple(data["strategies"])
    return Scenario(**data)


def list_scenario_files(ws_root) -> list[Path]:
    d = Path(ws_root) / "scenarios"
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


# ---------- constraints ----------

def load_constraints(ws_root) -> dict:
    path = Path(ws_root) / "constraints.json"
    if not path.exists():
        return {"schema_version": 1, "total_capital": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_constraints(ws_root, total_capital: float | None) -> None:
    atomic_write_json(Path(ws_root) / "constraints.json",
                      {"schema_version": 1, "total_capital": total_capital})
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_store_scenario.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add option_chaser/store.py tests/test_store_scenario.py
git commit -m "feat(v5): store layer 1 — Scenario entity, atomic writes, id rules, constraints"
```

---

### Task 3: store 第二層 — 事件日誌、狀態投影、轉移、兩型不一致

**Files:**
- Modify: `option_chaser/store.py`（追加）
- Test: `tests/test_store_events.py`

**Interfaces:**
- Consumes: Task 2 全部；`vocabulary.EVENT_TYPES_V5`
- Produces:
  - `append_event(ws_root, ts: str, scenario_id: str|None, event: str, payload: dict) -> None`（event ∉ EVENT_TYPES_V5 → `ValueError`；含 v7 預留）
  - `read_events(ws_root) -> list[dict]`（行序即 list 序＝投影次序權威）
  - `lifecycle_events(events: list[dict], sid: str) -> list[dict]`（最後一筆 CREATED 之後、未被其後 DELETED 蓋掉；無生命週期→`[]`）
  - `project_status(events, sid) -> str|None`（無生命週期→None；有→自 "Active" fold STATUS_CHANGED）
  - `reconcile_status(ws_root, sc: Scenario, events) -> Scenario`（一致→原樣；崩潰窗→修復快取檔並回傳修復後；竄改→raise `WorkspaceIntegrityError`）
  - `ALLOWED_TRANSITIONS = {("Active","Reached"), ("Active","Invalidated"), ("Active","Expired")}`
  - `change_status(ws_root, ts: str, sc: Scenario, to: str, reason: str, by: str = "user", extra_payload: dict|None = None) -> Scenario`（非法轉移→`ValueError`；先事件後快取）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_store_events.py
"""v5 spec §2.2/§2.3 + §7.2: 事件、投影（行序權威）、轉移、兩型不一致。"""
import dataclasses
import json
from pathlib import Path

import pytest

from option_chaser import store
from option_chaser.store import Scenario, WorkspaceIntegrityError

TS = "2026-07-21T00:00:00+00:00"


def _sc(**kw):
    base = dict(schema_version=1, id="TLT-105-202801", symbol="TLT",
                direction="bullish", target_price=105.0,
                target_date="2028-01-01", created_at=TS, notes="",
                group_id="G-TLT", status="Active",
                strategies=("long-call",))
    base.update(kw)
    return Scenario(**base)


def _boot(tmp_path):
    sc = _sc()
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_CREATED",
                       dataclasses.asdict(sc))
    store.save_scenario(tmp_path, sc)
    return sc


def test_append_and_read_order(tmp_path):
    _boot(tmp_path)
    store.append_event(tmp_path, TS, "TLT-105-202801", "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r", "by": "user"})
    events = store.read_events(tmp_path)
    assert [e["event"] for e in events] == ["SCENARIO_CREATED", "STATUS_CHANGED"]


def test_append_rejects_non_v5_vocabulary(tmp_path):
    with pytest.raises(ValueError):
        store.append_event(tmp_path, TS, None, "BOGUS_EVENT", {})
    with pytest.raises(ValueError):   # v7 預留 enum 在 v5 拒寫
        store.append_event(tmp_path, TS, None, "PRICE_REACHED", {})


def test_legal_transitions_append_event_and_update_cache(tmp_path):
    sc = _boot(tmp_path)
    for to, by in [("Reached", "user")]:
        sc2 = store.change_status(tmp_path, TS, sc, to, reason="到了", by=by)
        assert sc2.status == to
        on_disk = store.load_scenario(store.scenario_path(tmp_path, sc.id))
        assert on_disk.status == to
        last = store.read_events(tmp_path)[-1]
        assert last["event"] == "STATUS_CHANGED"
        assert last["payload"] == {"from": "Active", "to": to,
                                   "reason": "到了", "by": by}


def test_expired_observational_payload(tmp_path):
    sc = _boot(tmp_path)
    store.change_status(tmp_path, TS, sc, "Expired", reason="target_date 已過",
                        by="system", extra_payload={"observed_at": "2028-01-02"})
    last = store.read_events(tmp_path)[-1]
    assert last["payload"]["observed_at"] == "2028-01-02"


def test_illegal_transitions_raise(tmp_path):
    sc = _boot(tmp_path)
    sc = store.change_status(tmp_path, TS, sc, "Reached", reason="r")
    for to in ("Active", "Invalidated", "Expired"):
        with pytest.raises(ValueError):
            store.change_status(tmp_path, TS, sc, to, reason="x")


def test_projection_and_reconcile_clean(tmp_path):
    sc = _boot(tmp_path)
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) == "Active"
    assert store.reconcile_status(tmp_path, sc, events) == sc


def test_crash_window_repair(tmp_path):
    """崩潰窗：事件已 append、快取未更新 → 自動修復、不追加事件。"""
    sc = _boot(tmp_path)
    store.append_event(tmp_path, TS, sc.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r", "by": "user"})
    # 快取仍是 Active（== 最後一筆 STATUS_CHANGED 的 from）
    events = store.read_events(tmp_path)
    n_before = len(events)
    repaired = store.reconcile_status(tmp_path, sc, events)
    assert repaired.status == "Reached"
    assert store.load_scenario(store.scenario_path(tmp_path, sc.id)).status == "Reached"
    assert len(store.read_events(tmp_path)) == n_before   # 不追加新事件


def test_tamper_raises(tmp_path):
    sc = _boot(tmp_path)
    hacked = dataclasses.replace(sc, status="Reached")   # 無任何事件可解釋
    store.save_scenario(tmp_path, hacked)
    with pytest.raises(WorkspaceIntegrityError):
        store.reconcile_status(tmp_path, hacked, store.read_events(tmp_path))


def test_deleted_then_recreated_restarts_projection(tmp_path):
    sc = _boot(tmp_path)
    sc = store.change_status(tmp_path, TS, sc, "Reached", reason="r")
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_DELETED", {})
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) is None       # 生命週期結束
    # 同 id 重建 → 投影重新起算（舊 Reached 不復活）
    store.append_event(tmp_path, TS, sc.id, "SCENARIO_CREATED",
                       dataclasses.asdict(_sc()))
    events = store.read_events(tmp_path)
    assert store.project_status(events, sc.id) == "Active"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_store_events.py -v`
Expected: FAIL（`AttributeError: append_event`）

- [ ] **Step 3: 實作（追加到 store.py）**

```python
# --- 追加 import ---
from .vocabulary import EVENT_TYPES_V5

# ---------- events.jsonl ----------

ALLOWED_TRANSITIONS: set[tuple[str, str]] = {
    ("Active", "Reached"), ("Active", "Invalidated"), ("Active", "Expired")}


def _events_path(ws_root) -> Path:
    return Path(ws_root) / "events.jsonl"


def append_event(ws_root, ts: str, scenario_id: str | None, event: str,
                 payload: dict) -> None:
    """spec §6: event 值域鎖定 EVENT_TYPES_V5（v7 預留在 v5 拒寫）。"""
    if event not in EVENT_TYPES_V5:
        raise ValueError(f"事件值不在 v5 詞彙表內: {event}")
    line = json.dumps({"ts": ts, "scenario_id": scenario_id,
                       "event": event, "payload": payload},
                      ensure_ascii=False, sort_keys=True)
    path = _events_path(ws_root)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _atomic_write_text(path, existing + line + "\n")


def read_events(ws_root) -> list[dict]:
    path = _events_path(ws_root)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _last_index(events: list[dict], sid: str, etype: str) -> int:
    idx = -1
    for i, e in enumerate(events):
        if e.get("scenario_id") == sid and e.get("event") == etype:
            idx = i
    return idx


def lifecycle_events(events: list[dict], sid: str) -> list[dict]:
    """spec §2.3: 行序權威。最後一筆 CREATED 之後的該 id 事件；
    若其後有 DELETED（或根本無 CREATED）→ 無現行生命週期。"""
    created = _last_index(events, sid, "SCENARIO_CREATED")
    deleted = _last_index(events, sid, "SCENARIO_DELETED")
    if created == -1 or deleted > created:
        return []
    return [e for i, e in enumerate(events)
            if i > created and e.get("scenario_id") == sid]


def project_status(events: list[dict], sid: str) -> str | None:
    created = _last_index(events, sid, "SCENARIO_CREATED")
    deleted = _last_index(events, sid, "SCENARIO_DELETED")
    if created == -1 or deleted > created:
        return None
    status = "Active"
    for e in lifecycle_events(events, sid):
        if e["event"] == "STATUS_CHANGED":
            status = e["payload"]["to"]
    return status


def reconcile_status(ws_root, sc: Scenario, events: list[dict]) -> Scenario:
    """spec §2.2 兩型：崩潰窗修復（快取==最後 STATUS_CHANGED 的 from）／竄改拋錯。"""
    projected = project_status(events, sc.id)
    if projected is None:
        raise WorkspaceIntegrityError(
            f"劇本 {sc.id} 檔案存在但事件投影無現行生命週期")
    if sc.status == projected:
        return sc
    changes = [e for e in lifecycle_events(events, sc.id)
               if e["event"] == "STATUS_CHANGED"]
    if changes and sc.status == changes[-1]["payload"]["from"]:
        repaired = dataclasses.replace(sc, status=projected)
        save_scenario(ws_root, repaired)     # 修復快取，不追加事件
        return repaired
    raise WorkspaceIntegrityError(
        f"劇本 {sc.id} 狀態快取 {sc.status} 與事件投影 {projected} 不一致（非崩潰窗型）")


def change_status(ws_root, ts: str, sc: Scenario, to: str, reason: str,
                  by: str = "user", extra_payload: dict | None = None) -> Scenario:
    """先 append 事件、再改快取（spec §2.5 統一寫入次序）。"""
    if (sc.status, to) not in ALLOWED_TRANSITIONS:
        raise ValueError(f"非法狀態轉移: {sc.status} -> {to}")
    payload = {"from": sc.status, "to": to, "reason": reason, "by": by}
    if extra_payload:
        payload.update(extra_payload)
    append_event(ws_root, ts, sc.id, "STATUS_CHANGED", payload)
    updated = dataclasses.replace(sc, status=to)
    save_scenario(ws_root, updated)
    return updated
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_store_events.py tests/test_store_scenario.py -v`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add option_chaser/store.py tests/test_store_events.py
git commit -m "feat(v5): store layer 2 — event log, line-order projection, status transitions, two-type mismatch"
```

---

### Task 4: store 第三層 — groups.json 全量重建

**Files:**
- Modify: `option_chaser/store.py`（追加）
- Test: `tests/test_store_groups.py`

**Interfaces:**
- Consumes: Task 2-3 全部；`vocabulary.RELATION_CHOICES`
- Produces:
  - `propose_relation(a: Scenario, b: Scenario) -> str`（三分支：`"milestone-path"` / `"review-needed"` / `"exclusive-candidate"`；a 為 target_date 較早者）
  - `rebuild_groups(ws_root, scenarios: list[Scenario], events: list[dict]) -> dict`（決定性重建並原子覆寫 groups.json，回傳 dict；結構同 spec §2.4）
  - relations 的 `confirmed` 生命週期界定：僅計入行序在 pair 兩成員各自最新 `SCENARIO_CREATED` 之後的 `GROUP_RELATION_CONFIRMED`（pair 以集合比對）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_store_groups.py
"""v5 spec §2.4 + §7.3: 歸組、排序決定性、提案三分支（含 bearish 鏡像）、
確認投影、生命週期界定（同 id 重建不復活舊確認）。"""
import dataclasses
import json
from pathlib import Path

from option_chaser import store
from option_chaser.store import Scenario

TS = "2026-07-21T00:00:00+00:00"


def _sc(sid, symbol="TLT", direction="bullish", price=105.0,
        tdate="2028-01-01"):
    return Scenario(schema_version=1, id=sid, symbol=symbol,
                    direction=direction, target_price=price, target_date=tdate,
                    created_at=TS, notes="", group_id=f"G-{symbol}",
                    status="Active", strategies=("long-call",))


def _created(ws, sc):
    store.append_event(ws, TS, sc.id, "SCENARIO_CREATED", dataclasses.asdict(sc))


def test_same_symbol_grouped_members_sorted(tmp_path):
    a = _sc("TLT-115-202812", price=115.0, tdate="2028-12-01")
    b = _sc("TLT-105-202801", price=105.0, tdate="2028-01-01")
    c = _sc("SPY-500-202801", symbol="SPY", price=500.0)
    for s in (a, b, c):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b, c], store.read_events(tmp_path))
    gids = [g["id"] for g in data["groups"]]
    assert gids == ["G-SPY", "G-TLT"]
    tlt = next(g for g in data["groups"] if g["id"] == "G-TLT")
    assert tlt["members"] == ["TLT-105-202801", "TLT-115-202812"]  # target_date 升冪
    on_disk = json.loads((tmp_path / "groups.json").read_text(encoding="utf-8"))
    assert on_disk == data


def test_same_date_tie_breaks_by_id(tmp_path):
    a = _sc("TLT-110-202801", price=110.0, tdate="2028-01-01")
    b = _sc("TLT-105-202801", price=105.0, tdate="2028-01-01")
    for s in (a, b):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    assert data["groups"][0]["members"] == ["TLT-105-202801", "TLT-110-202801"]


def test_proposal_three_branches_and_bearish_mirror():
    early_b = _sc("A", price=105.0, tdate="2028-01-01")
    late_b = _sc("B", price=115.0, tdate="2028-12-01")
    assert store.propose_relation(early_b, late_b) == "milestone-path"
    late_lower = _sc("C", price=95.0, tdate="2028-12-01")
    assert store.propose_relation(early_b, late_lower) == "review-needed"
    bear = _sc("D", direction="bearish", price=90.0, tdate="2028-12-01")
    assert store.propose_relation(early_b, bear) == "exclusive-candidate"
    # bearish 鏡像：價格沿方向遞減 = milestone-path
    b1 = _sc("E", direction="bearish", price=95.0, tdate="2028-01-01")
    b2 = _sc("F", direction="bearish", price=85.0, tdate="2028-12-01")
    assert store.propose_relation(b1, b2) == "milestone-path"
    b3 = _sc("G", direction="bearish", price=99.0, tdate="2028-12-01")
    assert store.propose_relation(b1, b3) == "review-needed"


def test_confirm_projection_and_default_undefined(tmp_path):
    a = _sc("TLT-105-202801", price=105.0, tdate="2028-01-01")
    b = _sc("TLT-115-202812", price=115.0, tdate="2028-12-01")
    for s in (a, b):
        _created(tmp_path, s)
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["proposed"] == "milestone-path"
    assert rel["confirmed"] == "undefined" and rel["confirmed_at"] is None

    store.append_event(tmp_path, TS, None, "GROUP_RELATION_CONFIRMED",
                       {"group_id": "G-TLT", "pair": [a.id, b.id],
                        "choice": "milestone-path"})
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["confirmed"] == "milestone-path"
    assert rel["confirmed_at"] == TS


def test_recreate_does_not_resurrect_confirmation(tmp_path):
    """spec §2.4 生命週期界定負例（行序，非 ts）。"""
    a = _sc("TLT-105-202801", price=105.0, tdate="2028-01-01")
    b = _sc("TLT-115-202812", price=115.0, tdate="2028-12-01")
    for s in (a, b):
        _created(tmp_path, s)
    store.append_event(tmp_path, TS, None, "GROUP_RELATION_CONFIRMED",
                       {"group_id": "G-TLT", "pair": [a.id, b.id],
                        "choice": "milestone-path"})
    store.append_event(tmp_path, TS, a.id, "SCENARIO_DELETED", {})
    _created(tmp_path, a)   # 同 id 重建（新 CREATED 在確認事件之後）
    data = store.rebuild_groups(tmp_path, [a, b], store.read_events(tmp_path))
    rel = data["groups"][0]["relations"][0]
    assert rel["confirmed"] == "undefined"   # 舊確認不復活
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_store_groups.py -v`
Expected: FAIL（`AttributeError: rebuild_groups`）

- [ ] **Step 3: 實作（追加到 store.py）**

```python
# ---------- groups.json（全量可重建快取，spec §2.4） ----------

def propose_relation(a: Scenario, b: Scenario) -> str:
    """相鄰提案（a 為 target_date 較早者）。確定性，零 LLM。"""
    if a.direction != b.direction:
        return "exclusive-candidate"
    if a.direction == "bullish":
        progressing = a.target_price <= b.target_price
    else:
        progressing = a.target_price >= b.target_price
    return "milestone-path" if progressing else "review-needed"


def rebuild_groups(ws_root, scenarios: list[Scenario],
                   events: list[dict]) -> dict:
    """members/proposed 由 scenario 檔決定性重建；confirmed 由事件投影
    （行序權威＋生命週期界定：僅計入 pair 兩成員各自最新 CREATED 之後者）。"""
    by_symbol: dict[str, list[Scenario]] = {}
    for sc in scenarios:
        by_symbol.setdefault(sc.symbol, []).append(sc)

    groups = []
    for symbol in sorted(by_symbol):
        members = sorted(by_symbol[symbol],
                         key=lambda s: (s.target_date, s.id))
        relations = []
        for a, b in zip(members, members[1:]):
            confirmed, confirmed_at = "undefined", None
            created_a = _last_index(events, a.id, "SCENARIO_CREATED")
            created_b = _last_index(events, b.id, "SCENARIO_CREATED")
            for i, e in enumerate(events):
                if (e.get("event") == "GROUP_RELATION_CONFIRMED"
                        and set(e["payload"].get("pair", [])) == {a.id, b.id}
                        and i > created_a and i > created_b):
                    confirmed = e["payload"]["choice"]
                    confirmed_at = e["ts"]
            relations.append({"pair": [a.id, b.id],
                              "proposed": propose_relation(a, b),
                              "confirmed": confirmed,
                              "confirmed_at": confirmed_at})
        groups.append({"id": f"G-{symbol}", "symbol": symbol,
                       "members": [m.id for m in members],
                       "relations": relations})
    data = {"schema_version": 1, "groups": groups}
    atomic_write_json(Path(ws_root) / "groups.json", data)
    return data
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_store_groups.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add option_chaser/store.py tests/test_store_groups.py
git commit -m "feat(v5): store layer 3 — rebuildable groups cache, proposal rules, lifecycle-bounded confirmations"
```

---

### Task 5: serialize_result / save_result / load_result / latest_result_path

**Files:**
- Modify: `option_chaser/store.py`（追加）
- Modify: `docs/superpowers/specs/2026-07-21-option-chaser-v5-design.md`（§3 補一行「全量」明細，見 Step 5）
- Test: `tests/test_store_serialize.py`

**Interfaces:**
- Consumes: `service.AnalysisResult / CandidateView / candidate_key / run_offline / AnalysisRequest`、`valuation.SpreadValuation`、`scenarios.natural_cost`、`option_chaser.__version__`
- Produces:
  - `serialize_result(result: AnalysisResult, scenario_id: str, capital: float|None) -> dict`（spec §3 全欄位）
  - `save_result(ws_root, scenario_id: str, view: dict) -> Path`＝`<ws>/results/<sid>/<fetched_at.replace(':','')>.json`
  - `load_result(path) -> dict`
  - `latest_result_path(ws_root, sid) -> Path|None`（檔名字典序取最新）
  - candidate dict 欄位（Task 9/10 渲染依賴的鍵名，精確）：`candidate_key, strategy, legs[{contract_symbol, option_type, strike, expiry, bid, ask, iv, volume, open_interest}], mid_cost, natural_cost, baseline_pnl, baseline_return, natural_return, scenario_vector{entries, worst_code, worst_return}, completion_curve, completion_prices, completion_threshold, breakeven_at_target, retention, friction, friction_amount, buffer_days, quote_warning, theta_day_rate, vega_per_pt, decay_30d_return, net_delta, breakeven, max_profit, effective_leverage, matrix{prices, dates, cells}, capital_per_contract, max_loss_per_contract, pct_of_capital, days_to_target, days_to_expiry`。legs 順序：單腿 `[contract]`；spread `[long_leg, short_leg]`。
  - 頂層鍵：`schema_version, engine_version, analyzed_at, scenario_id, params, snapshot_ref{path, fetched_at, source, spot}, meta{symbol, spot, fetched_at, source, snapshot_path, target_move}, capital_assumed, data_quality{fetched_at, all_quotes_filtered}, results[], expiry_groups[], hidden_expiries, default_selection, comparison[], best_strategy, today`。
  - `results[]` 每策略：`strategy, status, message, n_qualified, filter_stages[{label,removed}], pair_report{total_pairs,removed_sanity,passed}|null, candidates[], expiry_best[], expiry_counts[[expiry,n]], report_text`。
  - `expiry_groups[]`：`{expiry, buffer_days, hidden_count, rows[{strategy, badges[], candidate}]}`（candidate 為完整 candidate dict 內嵌）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_store_serialize.py
"""v5 spec §3 + §7.4: 全欄位 round-trip、逐位元決定性、pct 兩態、
capital/max_loss/days 手算、data_quality 兩態、版本欄位。"""
import json
from datetime import date
from pathlib import Path

import option_chaser
from option_chaser import store
from option_chaser import service
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _result(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0],
                                       target_price=120.0,
                                       target_date="2026-08-01"),
            strategies=strategies),
        FIX)


def test_top_level_fields_and_versions():
    view = store.serialize_result(_result(), "XYZ-120-202608", 100000.0)
    assert view["schema_version"] == 1
    assert view["engine_version"] == option_chaser.__version__ == "0.5.0"
    assert view["scenario_id"] == "XYZ-120-202608"
    assert view["analyzed_at"] == view["snapshot_ref"]["fetched_at"]
    assert view["capital_assumed"] == 100000.0
    assert view["data_quality"]["all_quotes_filtered"] is False
    assert view["params"]["target_price"] == 120.0
    assert view["today"] == _result().today.isoformat()
    assert view["meta"]["target_move"] == _result().meta.target_move
    assert isinstance(view["default_selection"], list)
    json.dumps(view)   # 全結構可 JSON 化


def test_candidate_fields_hand_checked():
    result = _result(("long-call",))
    view = store.serialize_result(result, "S", 100000.0)
    res0 = view["results"][0]
    assert res0["strategy"] == "long-call" and res0["status"] == "ok"
    cand = res0["candidates"][0]
    cv = result.results[0].candidates[0]
    v = cv.valuation
    assert cand["candidate_key"] == service.candidate_key(cv)
    assert cand["mid_cost"] == v.mid
    assert cand["capital_per_contract"] == v.mid * 100
    assert cand["max_loss_per_contract"] == v.mid * 100          # debit 恆等於成本
    assert cand["pct_of_capital"] == (v.mid * 100) / 100000.0
    today = result.today
    assert cand["days_to_target"] == (date.fromisoformat("2026-08-01") - today).days
    assert cand["days_to_expiry"] == (
        date.fromisoformat(v.contract.expiry) - today).days
    assert cand["legs"][0]["strike"] == v.contract.strike
    assert cand["legs"][0]["iv"] == v.contract.implied_volatility
    assert cand["scenario_vector"]["worst_code"] == cv.scenario.worst_code
    assert cand["max_profit"] is None                            # long-call
    assert cand["net_delta"] == v.delta
    assert cand["matrix"]["cells"] == [list(r) for r in cv.matrix.cells]


def test_spread_legs_order_and_max_profit():
    result = _result(("bull-call-spread",))
    view = store.serialize_result(result, "S", None)
    cand = view["results"][0]["candidates"][0]
    sv = result.results[0].candidates[0].valuation
    assert cand["legs"][0]["strike"] == sv.long_leg.strike    # [0]=long
    assert cand["legs"][1]["strike"] == sv.short_leg.strike   # [1]=short
    assert cand["mid_cost"] == sv.net_mid
    assert cand["max_profit"] == sv.max_profit
    assert cand["net_delta"] == sv.net_delta


def test_pct_null_without_capital():
    view = store.serialize_result(_result(), "S", None)
    assert view["capital_assumed"] is None
    for res in view["results"]:
        for cand in res["candidates"]:
            assert cand["pct_of_capital"] is None


def test_byte_determinism(tmp_path):
    r = _result()
    a = store.serialize_result(r, "S", 100000.0)
    b = store.serialize_result(r, "S", 100000.0)
    dump = lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True)
    assert dump(a).encode("utf-8") == dump(b).encode("utf-8")
    p1 = store.save_result(tmp_path, "S", a)
    (tmp_path / "results" / "S2").mkdir(parents=True)
    import shutil
    p2 = Path(str(p1).replace("S", "S2", 1))
    store.save_result(tmp_path, "S2", b)
    assert p1.read_bytes() == p2.read_bytes()


def test_save_result_filename_windows_safe(tmp_path):
    view = store.serialize_result(_result(), "S", None)
    path = store.save_result(tmp_path, "S", view)
    expected_ts = view["snapshot_ref"]["fetched_at"].replace(":", "")
    assert path.name == f"{expected_ts}.json"
    assert ":" not in path.name
    assert store.latest_result_path(tmp_path, "S") == path
    assert store.load_result(path) == json.loads(
        path.read_text(encoding="utf-8"))


def test_latest_result_path_none_when_empty(tmp_path):
    assert store.latest_result_path(tmp_path, "NOPE") is None


def test_data_quality_all_quotes_filtered(tmp_path):
    """兩態：正常 False；全部合約 bid/ask=0 → 每策略 empty 且報價異常 removed>=1 → True。"""
    src = json.loads(Path("tests/fixtures/xyz_v4_all_warning.json")
                     .read_text(encoding="utf-8"))
    for c in src["contracts"]:
        c["bid"] = 0.0
        c["ask"] = 0.0
    bad = tmp_path / "all_zero.json"
    bad.write_text(json.dumps(src), encoding="utf-8")
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="long-call",
                                       target_price=120.0,
                                       target_date="2026-08-01"),
            strategies=("long-call", "bull-call-spread")),
        str(bad))
    view = store.serialize_result(result, "S", None)
    assert all(r["status"] == "empty" for r in view["results"])
    assert view["data_quality"]["all_quotes_filtered"] is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_store_serialize.py -v`
Expected: FAIL（`AttributeError: serialize_result`）

- [ ] **Step 3: 實作（追加到 store.py）**

```python
# --- 追加 import ---
from datetime import date

from . import __version__
from .scenarios import natural_cost
from .service import AnalysisResult, CandidateView, candidate_key
from .valuation import SpreadValuation

# ---------- ScenarioResult 契約（spec §3） ----------

def _leg(c) -> dict:
    return {"contract_symbol": c.contract_symbol, "option_type": c.option_type,
            "strike": c.strike, "expiry": c.expiry, "bid": c.bid,
            "ask": c.ask, "iv": c.implied_volatility, "volume": c.volume,
            "open_interest": c.open_interest}


def _candidate(cv: CandidateView, strategy: str, capital: float | None,
               today: date, target_date: str) -> dict:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        legs = [_leg(v.long_leg), _leg(v.short_leg)]   # [0]=long, [1]=short
        mid_cost, expiry = v.net_mid, v.long_leg.expiry
        max_profit, net_delta = v.max_profit, v.net_delta
    else:
        legs = [_leg(v.contract)]
        mid_cost, expiry = v.mid, v.contract.expiry
        # 與 service._comparison 相同定義（long-call 無上限 → None）
        max_profit = None if strategy == "long-call" else v.contract.strike - v.mid
        net_delta = v.delta
    cap_per = mid_cost * 100
    return {
        "candidate_key": candidate_key(cv),
        "strategy": strategy,
        "legs": legs,
        "mid_cost": mid_cost,
        "natural_cost": natural_cost(v),
        "baseline_pnl": cv.baseline_pnl,
        "baseline_return": cv.baseline_return,
        "natural_return": cv.natural_return,
        "scenario_vector": {"entries": [list(e) for e in cv.scenario.entries],
                            "worst_code": cv.scenario.worst_code,
                            "worst_return": cv.scenario.worst_return},
        "completion_curve": [list(e) for e in cv.completion_curve],
        "completion_prices": list(cv.completion_prices),
        "completion_threshold": cv.completion_threshold,
        "breakeven_at_target": cv.breakeven_at_target,
        "retention": cv.retention,
        "friction": cv.friction,
        "friction_amount": cv.friction_amount,
        "buffer_days": cv.buffer_days,
        "quote_warning": cv.quote_warning,
        "theta_day_rate": cv.theta_day_rate,
        "vega_per_pt": cv.vega_per_pt,
        "decay_30d_return": cv.decay_30d_return,
        "net_delta": net_delta,
        "breakeven": v.breakeven,
        "max_profit": max_profit,
        "effective_leverage": v.effective_leverage,
        "matrix": {"prices": [list(p) for p in cv.matrix.prices],
                   "dates": [list(d) for d in cv.matrix.dates],
                   "cells": [list(r) for r in cv.matrix.cells]},
        # spec §3 新增四組（乘除法與日期差，非估值邏輯）
        "capital_per_contract": cap_per,
        "max_loss_per_contract": cap_per,   # debit 恆等於成本
        "pct_of_capital": (cap_per / capital) if capital else None,
        "days_to_target": (date.fromisoformat(target_date) - today).days,
        "days_to_expiry": (date.fromisoformat(expiry) - today).days,
    }


def serialize_result(result: AnalysisResult, scenario_id: str,
                     capital: float | None) -> dict:
    base = result.request.base_params
    today = result.today

    def cand(cv, strategy):
        return _candidate(cv, strategy, capital, today, base.target_date)

    def strat(r):
        return {
            "strategy": r.strategy, "status": r.status, "message": r.message,
            "n_qualified": r.n_qualified,
            "filter_stages": ([{"label": s.label, "removed": s.removed}
                               for s in r.filter_report.stages]
                              if r.filter_report else []),
            "pair_report": ({"total_pairs": r.pair_report.total_pairs,
                             "removed_sanity": r.pair_report.removed_sanity,
                             "passed": r.pair_report.passed}
                            if r.pair_report else None),
            "candidates": [cand(cv, r.strategy) for cv in r.candidates],
            "expiry_best": [cand(cv, r.strategy) for cv in r.expiry_best],
            "expiry_counts": [list(e) for e in r.expiry_counts],
            "report_text": r.report_text,
        }

    strategy_of_row = {}
    for r in result.results:
        for cv in list(r.candidates) + list(r.expiry_best):
            strategy_of_row[candidate_key(cv)] = r.strategy

    def group(g):
        return {"expiry": g.expiry, "buffer_days": g.buffer_days,
                "hidden_count": g.hidden_count,
                "rows": [{"strategy": row.strategy,
                          "badges": list(row.badges),
                          "candidate": cand(row.candidate, row.strategy)}
                         for row in g.rows]}

    all_quotes_filtered = bool(result.results) and all(
        r.status == "empty" and r.filter_report is not None and any(
            s.label == "報價異常" and s.removed >= 1
            for s in r.filter_report.stages)
        for r in result.results)

    m = result.meta
    return {
        "schema_version": 1,
        "engine_version": __version__,
        "analyzed_at": m.fetched_at,
        "scenario_id": scenario_id,
        "params": {**dataclasses.asdict(base),
                   "iv_shifts": list(base.iv_shifts),
                   "delta_bands": list(base.delta_bands)},
        "snapshot_ref": {"path": m.snapshot_path, "fetched_at": m.fetched_at,
                         "source": m.source, "spot": m.spot},
        "meta": {"symbol": m.symbol, "spot": m.spot,
                 "fetched_at": m.fetched_at, "source": m.source,
                 "snapshot_path": m.snapshot_path,
                 "target_move": m.target_move},
        "capital_assumed": capital,
        "data_quality": {"fetched_at": m.fetched_at,
                         "all_quotes_filtered": all_quotes_filtered},
        "results": [strat(r) for r in result.results],
        "expiry_groups": [group(g) for g in result.expiry_groups],
        "hidden_expiries": list(result.hidden_expiries),
        "default_selection": (list(result.default_selection)
                              if result.default_selection else None),
        "comparison": [dataclasses.asdict(c) for c in result.comparison],
        "best_strategy": result.best_strategy,
        "today": today.isoformat(),
    }


def save_result(ws_root, scenario_id: str, view: dict) -> Path:
    """檔名 = fetched_at.replace(':','')（Windows 安全；字典序＝時間序）。"""
    ts = view["snapshot_ref"]["fetched_at"].replace(":", "")
    path = Path(ws_root) / "results" / scenario_id / f"{ts}.json"
    atomic_write_json(path, view)
    return path


def load_result(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_result_path(ws_root, scenario_id: str) -> Path | None:
    d = Path(ws_root) / "results" / scenario_id
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    return files[-1] if files else None
```

註：`strategy_of_row` 若最終實作未用到（rows 已帶 strategy），刪除該區塊——不留死碼。

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_store_serialize.py -v`
Expected: 8 passed

- [ ] **Step 5: spec §3 doc-sync（全量明細一行）**

spec §3 標題句「v4 `AnalysisResult` 的**全量 JSON 化**」統攝一切欄位；列舉區塊漏列三處實際存在於 v4 `AnalysisResult` 的資料。在 spec §3 `today: ISO date（snapshot 推導，決定性）` 之後補一行：

```
meta（SnapshotMeta 全欄含 target_move）與各 strategy result 的 expiry_best[]/expiry_counts[] 亦序列化（「全量」原則；render/散點圖依賴 expiry_best）。
```

- [ ] **Step 6: 既有回歸**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 7: Commit**

```bash
git add option_chaser/store.py tests/test_store_serialize.py docs/superpowers/specs/2026-07-21-option-chaser-v5-design.md
git commit -m "feat(v5): ScenarioResult contract — full serialization, byte determinism, windows-safe result files"
```

---

### Task 6: service.fetch_and_save 抽出（run 行為不變）

**Files:**
- Modify: `option_chaser/service.py:564-573`（僅 `run`；新增 `fetch_and_save`）
- Test: `tests/test_service_fetch.py`

**Interfaces:**
- Produces: `service.fetch_and_save(symbol: str) -> tuple[ChainSnapshot, str]`（抓取＋存 snapshots/，回傳 (snap, path)；`run` 改為呼叫它，行為與訊息序完全不變）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_service_fetch.py
"""v5 spec §4: service 抽出 fetch_and_save 供 workspace.analyze_group 共用。"""
import json
from pathlib import Path

from option_chaser import service
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def test_fetch_and_save_returns_snap_and_path(tmp_path, monkeypatch):
    snap = load_snapshot(FIX)
    import option_chaser.data.yf as yf
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: snap)
    monkeypatch.chdir(tmp_path)   # snapshots/ 寫在 cwd
    got_snap, path = service.fetch_and_save("XYZ")
    assert got_snap == snap
    p = Path(path)
    assert p.exists() and p.parent.name == "snapshots"
    assert ":" not in p.name
    assert json.loads(p.read_text(encoding="utf-8"))["symbol"] == "XYZ"


def test_run_delegates_to_fetch_and_save(monkeypatch):
    """run 只是 fetch_and_save + _analyze 的組合（行為不變的結構性證據）。"""
    snap = load_snapshot(FIX)
    calls = []

    def fake_fetch_and_save(symbol):
        calls.append(symbol)
        return snap, FIX

    monkeypatch.setattr(service, "fetch_and_save", fake_fetch_and_save)
    from option_chaser.models import AnalysisParams
    result = service.run(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_date="2026-08-01"),
        strategies=("long-call",)))
    assert calls == ["XYZ"]
    assert result.meta.snapshot_path == FIX
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_service_fetch.py -v`
Expected: FAIL（`AttributeError: fetch_and_save`）

- [ ] **Step 3: 實作 — service.py `run` 改寫為**

```python
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
```

（刪除 run 內原本的 fetch/save 四行；`_analyze` 及其他一律不動。）

- [ ] **Step 4: 跑測試確認通過＋全回歸**

Run: `python -m pytest tests/test_service_fetch.py -v && python -m pytest -q`
Expected: 全綠（run 行為不變 → test_service*.py、goldens 全綠）

- [ ] **Step 5: Commit**

```bash
git add option_chaser/service.py tests/test_service_fetch.py
git commit -m "refactor(v5): extract service.fetch_and_save (run behavior unchanged)"
```

---

### Task 7: workspace — create/list（載入期對帳）/set_status/confirm_relation/delete

**Files:**
- Create: `option_chaser/workspace.py`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: store 全部（Task 2-5）、`vocabulary.RELATION_CHOICES`
- Produces:
  - `now_utc_iso() -> str`／`ny_today() -> date`（wall-clock 僅在此層）
  - `create_scenario(ws_root, symbol, direction, target_price, target_date, notes, strategies, *, ts=None) -> Scenario`
  - `list_scenarios(ws_root, *, observed: date|None = None) -> list[Scenario]`（§2.5 對帳全表＋Expired 觀察式轉移＋groups 重建；回傳依 (symbol, target_date, id) 排序）
  - `set_status(ws_root, sid, to, reason, *, ts=None) -> Scenario`
  - `confirm_relation(ws_root, group_id, pair: tuple[str,str], choice, *, ts=None) -> None`（choice ∉ RELATION_CHOICES → ValueError）
  - `delete_scenario(ws_root, sid, *, ts=None) -> None`
  - `load_groups(ws_root) -> dict`（讀 groups.json；缺檔→重建）
  - `default_direction(symbol, target_price, snapshots_dir="snapshots") -> str|None`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_workspace.py
"""v5 spec §4 + §7.2/§7.3a/§7.5: 編排層 CRUD、載入期對帳矩陣、觀察式過期。"""
import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from option_chaser import store, workspace

TS = "2026-07-21T00:00:00+00:00"


def _create(ws, symbol="TLT", price=105.0, tdate="2028-01-01",
            direction="bullish"):
    return workspace.create_scenario(
        ws, symbol=symbol, direction=direction, target_price=price,
        target_date=tdate, notes="", strategies=("long-call",), ts=TS)


def test_create_writes_event_file_and_groups(tmp_path):
    sc = _create(tmp_path)
    assert sc.id == "TLT-105-202801" and sc.group_id == "G-TLT"
    events = store.read_events(tmp_path)
    assert events[0]["event"] == "SCENARIO_CREATED"
    assert store.scenario_path(tmp_path, sc.id).exists()
    groups = json.loads((tmp_path / "groups.json").read_text(encoding="utf-8"))
    assert groups["groups"][0]["members"] == [sc.id]


def test_create_collision_deterministic(tmp_path):
    a = _create(tmp_path)
    b = _create(tmp_path)
    assert (a.id, b.id) == ("TLT-105-202801", "TLT-105-202801-2")


def test_list_returns_sorted_and_validated(tmp_path):
    _create(tmp_path, symbol="TLT", tdate="2028-12-01", price=115.0)
    _create(tmp_path, symbol="SPY", price=500.0)
    _create(tmp_path, symbol="TLT", tdate="2028-01-01", price=105.0)
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert [s.symbol for s in got] == ["SPY", "TLT", "TLT"]
    assert got[1].target_date == "2028-01-01"


def test_set_status_and_confirm_relation(tmp_path):
    a = _create(tmp_path, tdate="2028-01-01", price=105.0)
    b = _create(tmp_path, tdate="2028-12-01", price=115.0)
    workspace.set_status(tmp_path, a.id, "Reached", reason="到價", ts=TS)
    assert store.load_scenario(store.scenario_path(tmp_path, a.id)).status == "Reached"
    workspace.confirm_relation(tmp_path, "G-TLT", (a.id, b.id),
                               "milestone-path", ts=TS)
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["relations"][0]["confirmed"] == "milestone-path"
    with pytest.raises(ValueError):
        workspace.confirm_relation(tmp_path, "G-TLT", (a.id, b.id), "bogus", ts=TS)


def test_expired_observational_transition(tmp_path):
    sc = _create(tmp_path, tdate="2027-01-01")
    got = workspace.list_scenarios(tmp_path, observed=date(2027, 1, 2))
    assert got[0].status == "Expired"
    last = store.read_events(tmp_path)[-1]
    assert last["event"] == "STATUS_CHANGED"
    assert last["payload"]["to"] == "Expired"
    assert last["payload"]["observed_at"] == "2027-01-02"
    assert last["payload"]["by"] == "system"


def test_not_expired_on_boundary_date(tmp_path):
    """觀察日 == target_date 不過期（規則是 觀察日 > target_date）。"""
    _create(tmp_path, tdate="2027-01-01")
    got = workspace.list_scenarios(tmp_path, observed=date(2027, 1, 1))
    assert got[0].status == "Active"


def test_delete_scenario_full_chain(tmp_path):
    a = _create(tmp_path, tdate="2028-01-01", price=105.0)
    b = _create(tmp_path, tdate="2028-12-01", price=115.0)
    (tmp_path / "results" / a.id).mkdir(parents=True)
    (tmp_path / "results" / a.id / "x.json").write_text("{}", encoding="utf-8")
    workspace.delete_scenario(tmp_path, a.id, ts=TS)
    assert not store.scenario_path(tmp_path, a.id).exists()
    assert not (tmp_path / "results" / a.id).exists()
    assert store.read_events(tmp_path)[-1]["event"] == "SCENARIO_DELETED"
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [b.id]


def test_reconcile_interrupted_delete(tmp_path):
    """§2.5 對帳：DELETED 末事件但檔案仍在 → 載入時完成刪除（冪等）。"""
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "SCENARIO_DELETED", {})
    # scenario 檔與 results 殘留
    (tmp_path / "results" / a.id).mkdir(parents=True)
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got == []
    assert not store.scenario_path(tmp_path, a.id).exists()
    assert not (tmp_path / "results" / a.id).exists()


def test_reconcile_created_without_file_ignored(tmp_path):
    store.append_event(tmp_path, TS, "GHOST-1-202801", "SCENARIO_CREATED",
                       {"id": "GHOST-1-202801"})
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got == []   # 不拋錯、不出現


def test_reconcile_crash_window_repair_in_list(tmp_path):
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r",
                        "by": "user"})   # 快取未更新（崩潰窗）
    got = workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert got[0].status == "Reached"


def test_reconcile_tamper_raises_in_list(tmp_path):
    a = _create(tmp_path)
    store.save_scenario(tmp_path, dataclasses.replace(a, status="Invalidated"))
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))


def test_groups_rebuilt_on_load_after_manual_delete(tmp_path):
    _create(tmp_path)
    (tmp_path / "groups.json").unlink()
    workspace.list_scenarios(tmp_path, observed=date(2026, 7, 21))
    assert (tmp_path / "groups.json").exists()


def test_set_status_reconciles_before_transition(tmp_path):
    """崩潰窗後直呼 set_status：先修復（實為 Reached），再驗轉移合法性。"""
    a = _create(tmp_path)
    store.append_event(tmp_path, TS, a.id, "STATUS_CHANGED",
                       {"from": "Active", "to": "Reached", "reason": "r",
                        "by": "user"})   # 快取未更新（崩潰窗）
    with pytest.raises(ValueError):      # 修復後 Reached→Reached 非法，不重複 append
        workspace.set_status(tmp_path, a.id, "Reached", reason="again", ts=TS)
    assert store.load_scenario(store.scenario_path(tmp_path, a.id)).status == "Reached"


def test_load_groups_overwrites_tampered_file(tmp_path):
    a = _create(tmp_path)
    (tmp_path / "groups.json").write_text(
        '{"schema_version": 1, "groups": []}', encoding="utf-8")
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [a.id]   # 無條件重建，不信磁碟


def test_default_direction(tmp_path):
    assert workspace.default_direction("NOPE", 100.0,
                                       snapshots_dir=tmp_path) is None
    snap = json.loads(Path("tests/fixtures/xyz_v4_six_expiries.json")
                      .read_text(encoding="utf-8"))
    (tmp_path / "XYZ_20260721T000000+0000.json").write_text(
        json.dumps(snap), encoding="utf-8")
    spot = snap["spot"]
    assert workspace.default_direction("XYZ", spot + 10,
                                       snapshots_dir=tmp_path) == "bullish"
    assert workspace.default_direction("XYZ", spot - 10,
                                       snapshots_dir=tmp_path) == "bearish"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL（no module `option_chaser.workspace`）

- [ ] **Step 3: 實作**

```python
# option_chaser/workspace.py
"""v5 spec §4: 工作區編排層（store 與 GUI 之間；不碰估值）。

wall-clock 僅在本層（now_utc_iso / ny_today）；store 保持純函數。
觀察日基準 = America/New_York（與引擎 snapshot_today 一致，spec §2.2）。
"""
from __future__ import annotations

import dataclasses
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import service, store
from .data.snapshot import load_snapshot
from .models import AnalysisParams
from .store import Scenario
from .vocabulary import RELATION_CHOICES

_EASTERN = ZoneInfo("America/New_York")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ny_today() -> date:
    return datetime.now(_EASTERN).date()


def _existing_ids(ws_root) -> set[str]:
    return {p.stem for p in store.list_scenario_files(ws_root)}


def create_scenario(ws_root, symbol: str, direction: str, target_price: float,
                    target_date: str, notes: str,
                    strategies: tuple[str, ...], *, ts: str | None = None
                    ) -> Scenario:
    """§2.5 次序：產 id → append CREATED → 寫檔 → 重建 groups。"""
    ts = ts or now_utc_iso()
    sid = store.scenario_id(symbol, target_price, target_date,
                            _existing_ids(ws_root))
    sc = Scenario(schema_version=1, id=sid, symbol=symbol, direction=direction,
                  target_price=target_price, target_date=target_date,
                  created_at=ts, notes=notes, group_id=f"G-{symbol}",
                  status="Active", strategies=tuple(strategies))
    store.append_event(ws_root, ts, sid, "SCENARIO_CREATED",
                       dataclasses.asdict(sc))
    store.save_scenario(ws_root, sc)
    _rebuild(ws_root)
    return sc


def _rebuild(ws_root) -> dict:
    scenarios = [store.load_scenario(p)
                 for p in store.list_scenario_files(ws_root)]
    return store.rebuild_groups(ws_root, scenarios, store.read_events(ws_root))


def list_scenarios(ws_root, *, observed: date | None = None) -> list[Scenario]:
    """spec §2.5 載入期對帳（全部冪等）＋ Expired 觀察式轉移 ＋ groups 重建。"""
    ws = Path(ws_root)
    (ws / "scenarios").mkdir(parents=True, exist_ok=True)
    observed = observed or ny_today()
    events = store.read_events(ws_root)

    # 1. DELETED 末事件殘檔 → 完成刪除（冪等）
    dead = {e["scenario_id"] for e in events if e["event"] == "SCENARIO_DELETED"
            if store.project_status(events, e["scenario_id"]) is None}
    for sid in dead:
        p = store.scenario_path(ws_root, sid)
        if p.exists():
            p.unlink()
        rdir = ws / "results" / sid
        if rdir.is_dir():
            shutil.rmtree(rdir)

    # 2. 載入 scenario 檔（CREATED 無檔 → 自然忽略：只迭代存在的檔）
    scenarios = [store.load_scenario(p)
                 for p in store.list_scenario_files(ws_root)]

    # 3. 快取驗證/崩潰窗修復（竄改 → WorkspaceIntegrityError 上拋）
    scenarios = [store.reconcile_status(ws_root, sc, events)
                 for sc in scenarios]

    # 4. Expired 觀察式轉移（觀察日 > target_date 且 Active）
    out = []
    for sc in scenarios:
        if (sc.status == "Active"
                and observed > date.fromisoformat(sc.target_date)):
            sc = store.change_status(
                ws_root, now_utc_iso(), sc, "Expired",
                reason="target_date 已過", by="system",
                extra_payload={"observed_at": observed.isoformat()})
        out.append(sc)

    # 5. groups 無條件重建（快取全量可重建）
    store.rebuild_groups(ws_root, out, store.read_events(ws_root))
    return sorted(out, key=lambda s: (s.symbol, s.target_date, s.id))


def set_status(ws_root, sid: str, to: str, reason: str,
               *, ts: str | None = None) -> Scenario:
    """變更前必先對帳（崩潰窗修復／竄改拋錯）——不信任快取直接轉移。"""
    events = store.read_events(ws_root)
    sc = store.reconcile_status(
        ws_root, store.load_scenario(store.scenario_path(ws_root, sid)), events)
    return store.change_status(ws_root, ts or now_utc_iso(), sc, to, reason)


def confirm_relation(ws_root, group_id: str, pair: tuple[str, str],
                     choice: str, *, ts: str | None = None) -> None:
    if choice not in RELATION_CHOICES:
        raise ValueError(f"未知關係選項: {choice}")
    store.append_event(ws_root, ts or now_utc_iso(), None,
                       "GROUP_RELATION_CONFIRMED",
                       {"group_id": group_id, "pair": list(pair),
                        "choice": choice})
    _rebuild(ws_root)


def delete_scenario(ws_root, sid: str, *, ts: str | None = None) -> None:
    """§2.5 次序：先事件、後刪檔、後重建群組；殘局由 list_scenarios 補完。"""
    store.append_event(ws_root, ts or now_utc_iso(), sid,
                       "SCENARIO_DELETED", {})
    p = store.scenario_path(ws_root, sid)
    if p.exists():
        p.unlink()
    rdir = Path(ws_root) / "results" / sid
    if rdir.is_dir():
        shutil.rmtree(rdir)
    _rebuild(ws_root)


def load_groups(ws_root) -> dict:
    """spec §2.5: groups.json 任何過時/缺失 → 無條件重建（快取全量可重建，
    絕不回傳磁碟上可能被手改的版本）。"""
    return _rebuild(ws_root)


def default_direction(symbol: str, target_price: float,
                      snapshots_dir="snapshots") -> str | None:
    """建立表單預設方向：該 symbol 最近 snapshot 的 spot 推得（spec §2.2）。"""
    d = Path(snapshots_dir)
    if not d.is_dir():
        return None
    files = sorted(d.glob(f"{symbol}_*.json"))
    if not files:
        return None
    snap = load_snapshot(files[-1])
    return "bullish" if target_price > snap.spot else "bearish"
```

（`AnalysisParams`／`service` import 供 Task 8 使用；若本 task 結束時 linter 報 unused，改為 Task 8 再加。）

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add option_chaser/workspace.py tests/test_workspace.py
git commit -m "feat(v5): workspace orchestration — CRUD, load-time reconciliation, observational expiry"
```

---

### Task 8: workspace — analyze_scenario / analyze_group / latest_result

**Files:**
- Modify: `option_chaser/workspace.py`（追加）
- Test: `tests/test_workspace_analyze.py`

**Interfaces:**
- Consumes: `service.run / run_offline / fetch_and_save / AnalysisRequest`、`store.serialize_result / save_result / load_result / latest_result_path / load_constraints / append_event`
- Produces:
  - `analyze_scenario(ws_root, sid, progress=None, *, snapshot_path: str|None = None, ts: str|None = None) -> Path`（snapshot_path 為測試鉤/群組共用：非 None → `service.run_offline`）
  - `analyze_group(ws_root, group_id, progress=None, *, snapshot_path=None, ts=None) -> list[Path]`（一次抓取共用 snapshot；全成員 result 的 `snapshot_ref.path` 相同）
  - `latest_result(ws_root, sid) -> dict|None`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_workspace_analyze.py
"""v5 spec §4 + §7.5: 分析鏈路（offline 注入）、群組共用 snapshot、事件序。"""
from datetime import date
from pathlib import Path

from option_chaser import store, workspace

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"


def _create(ws, price=120.0, tdate="2026-08-01"):
    return workspace.create_scenario(
        ws, symbol="XYZ", direction="bullish", target_price=price,
        target_date=tdate, notes="", strategies=("long-call",), ts=TS)


def test_create_analyze_latest_chain(tmp_path):
    sc = _create(tmp_path)
    path = workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)
    assert path.exists()
    view = workspace.latest_result(tmp_path, sc.id)
    assert view["scenario_id"] == sc.id
    assert view["snapshot_ref"]["path"] == FIX
    assert view["engine_version"] == "0.5.0"
    events = [e["event"] for e in store.read_events(tmp_path)]
    assert events == ["SCENARIO_CREATED", "ANALYSIS_COMPLETED"]
    last = store.read_events(tmp_path)[-1]
    assert last["payload"]["result_path"] == str(path)
    assert last["payload"]["snapshot_ref"] == view["snapshot_ref"]  # 完整物件


def test_analyze_logically_deleted_scenario_raises(tmp_path):
    """殘檔（已刪但 scenario 檔被復原/殘留）不得被分析。"""
    import pytest
    sc = _create(tmp_path)
    workspace.delete_scenario(tmp_path, sc.id, ts=TS)
    store.save_scenario(tmp_path, sc)   # 模擬殘檔
    with pytest.raises(store.WorkspaceIntegrityError):
        workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)


def test_analyze_uses_capital_snapshot(tmp_path):
    sc = _create(tmp_path)
    store.save_constraints(tmp_path, 100000.0)
    workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=FIX, ts=TS)
    view = workspace.latest_result(tmp_path, sc.id)
    assert view["capital_assumed"] == 100000.0
    cand = view["results"][0]["candidates"][0]
    assert cand["pct_of_capital"] == cand["capital_per_contract"] / 100000.0


def test_analyze_group_shares_snapshot(tmp_path):
    a = _create(tmp_path, price=110.0, tdate="2026-08-01")
    b = _create(tmp_path, price=120.0, tdate="2026-09-01")
    paths = workspace.analyze_group(tmp_path, "G-XYZ",
                                    snapshot_path=FIX, ts=TS)
    assert len(paths) == 2
    views = [store.load_result(p) for p in paths]
    assert views[0]["snapshot_ref"]["path"] == views[1]["snapshot_ref"]["path"]
    assert {v["scenario_id"] for v in views} == {a.id, b.id}


def test_analyze_group_online_fetches_once(tmp_path, monkeypatch):
    from option_chaser import service
    from option_chaser.data.snapshot import load_snapshot
    _create(tmp_path, price=110.0, tdate="2026-08-01")
    _create(tmp_path, price=120.0, tdate="2026-09-01")
    calls = []

    def fake_fetch_and_save(symbol):
        calls.append(symbol)
        return load_snapshot(FIX), FIX

    monkeypatch.setattr(service, "fetch_and_save", fake_fetch_and_save)
    paths = workspace.analyze_group(tmp_path, "G-XYZ", ts=TS)
    assert calls == ["XYZ"]          # 一次抓取
    assert len(paths) == 2


def test_latest_result_none_without_analysis(tmp_path):
    sc = _create(tmp_path)
    assert workspace.latest_result(tmp_path, sc.id) is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_workspace_analyze.py -v`
Expected: FAIL（`AttributeError: analyze_scenario`）

- [ ] **Step 3: 實作（追加到 workspace.py）**

```python
def _request_for(sc: Scenario) -> service.AnalysisRequest:
    """base_params 自 scenario 欄位；其餘 CLI 預設（spec §4）。"""
    base = AnalysisParams(target_price=sc.target_price,
                          target_date=sc.target_date,
                          strategy=sc.strategies[0])
    return service.AnalysisRequest(symbol=sc.symbol, base_params=base,
                                   strategies=tuple(sc.strategies))


def analyze_scenario(ws_root, sid: str, progress=None, *,
                     snapshot_path: str | None = None,
                     ts: str | None = None) -> Path:
    """§2.5 例外次序：result 檔先落盤，ANALYSIS_COMPLETED 後補。
    分析前必先對帳：邏輯已刪（殘檔）→ 拋錯；崩潰窗 → 修復後續行。"""
    events = store.read_events(ws_root)
    if store.project_status(events, sid) is None:
        raise store.WorkspaceIntegrityError(f"劇本 {sid} 不存在或已刪除")
    sc = store.reconcile_status(
        ws_root, store.load_scenario(store.scenario_path(ws_root, sid)), events)
    req = _request_for(sc)
    if snapshot_path is None:
        result = service.run(req, progress)
    else:
        result = service.run_offline(req, snapshot_path, progress)
    capital = store.load_constraints(ws_root)["total_capital"]
    view = store.serialize_result(result, sc.id, capital)
    path = store.save_result(ws_root, sc.id, view)
    store.append_event(ws_root, ts or now_utc_iso(), sc.id,
                       "ANALYSIS_COMPLETED",
                       {"result_path": str(path),
                        "snapshot_ref": view["snapshot_ref"]})   # 完整物件（spec §2.3）
    return path


def analyze_group(ws_root, group_id: str, progress=None, *,
                  snapshot_path: str | None = None,
                  ts: str | None = None) -> list[Path]:
    """一次抓取共用 snapshot；全成員 result 的 snapshot_ref.path 相同（spec §4）。"""
    groups = load_groups(ws_root)
    group = next(g for g in groups["groups"] if g["id"] == group_id)
    if snapshot_path is None:
        _, snapshot_path = service.fetch_and_save(group["symbol"])
    return [analyze_scenario(ws_root, sid, progress,
                             snapshot_path=snapshot_path, ts=ts)
            for sid in group["members"]]


def latest_result(ws_root, sid: str) -> dict | None:
    path = store.latest_result_path(ws_root, sid)
    return store.load_result(path) if path else None
```

- [ ] **Step 4: 跑測試確認通過＋全回歸**

Run: `python -m pytest tests/test_workspace_analyze.py -v && python -m pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add option_chaser/workspace.py tests/test_workspace_analyze.py
git commit -m "feat(v5): workspace analyze — shared-snapshot group analysis, capital snapshot, audit events"
```

---

### Task 9: webapp/render.py 抽出（dict 介面；既有 AppTest 不改而綠）

**Files:**
- Create: `webapp/render.py`
- Modify: `webapp/app.py`
- Test: 既有 `tests/test_webapp.py`、`tests/test_webapp_v4.py`、`tests/test_heatmap_colors.py` **一字不改**全綠（spec §7.6 硬證據）

**Interfaces:**
- Consumes: `store.serialize_result` 產出的 view dict（Task 5 鍵名）；`glossary.GLOSSary`、`scenarios.SCENARIO_NAMES`、`report.STRATEGY_LABELS`、`matrix.thumbnail_cells`
- Produces（`webapp/render.py`，全部收 dict）:
  - `cell_color(ret: float) -> str`（自 app.py 原樣搬移——`test_heatmap_colors.py` 經 `webapp.app` 屬性取 source，app.py re-export 後 `inspect.getsource` 仍可用）
  - `esc(text) -> str`、`abbr(term) -> str`、`money(x) -> str`、`pct(x) -> str`
  - `heatmap_html(matrix: dict) -> str`（matrix = candidate["matrix"]）
  - `render_summary(view: dict) -> None`
  - `render_step2(view: dict, key: str|None) -> None`
  - `render_step3(view: dict, key: str|None, state_key: str = "selected_key") -> None`
  - `render_step4(view: dict, key: str|None) -> None`
  - `all_rows(view) -> list[dict]`、`find_row(view, key) -> dict|None`（row dict：`{"strategy","badges","candidate"}`）
  - `default_key(view) -> str|None`（`view["default_selection"][1]` 或 None）

**重構規則（防止渲染輸出漂移）：**
- 每個函數自 app.py 對應函數搬移，僅做「屬性存取 → dict 索引」替換，HTML/文案字串一律逐字保留。替換對照表：
  - `cv.baseline_return` → `cand["baseline_return"]`；`cv.scenario.worst_return` → `cand["scenario_vector"]["worst_return"]`；`cv.scenario.entries` → `cand["scenario_vector"]["entries"]`；`cv.scenario.worst_code` → `cand["scenario_vector"]["worst_code"]`
  - `cv.matrix.prices/dates/cells` → `cand["matrix"]["prices"/"dates"/"cells"]`（list-of-list，原 tuple 解包 `for iso, lbl in mv.dates` 對 list `[iso, lbl]` 同樣可用）
  - `service.candidate_key(row.candidate)` → `row["candidate"]["candidate_key"]`
  - `_mid_cost(s, cv)` → `cand["mid_cost"]`；`_net_delta(cv)` → `cand["net_delta"]`
  - `isinstance(v, SpreadValuation)` → `row["strategy"] in ("bull-call-spread", "bear-put-spread")`（或 `len(cand["legs"]) == 2`）
  - `_candidate_label`：spread → `f"買 {cand['legs'][0]['strike']:g} / 賣 {cand['legs'][1]['strike']:g}"`；單腿 → `f"K={cand['legs'][0]['strike']:g}"`
  - Greeks expander 的 OI/Volume：`cand["legs"][i]["open_interest"]/["volume"]`
  - `res.report_text` → strategy result dict `r["report_text"]`；scatter 的 `res.expiry_best` → `r["expiry_best"]`
  - summary chips：`m.symbol/m.spot/m.target_move` → `view["meta"][...]`；`base.target_price/target_date` → `view["params"][...]`；跳過訊息 `r.status != "ok"` → dict 同名鍵
  - `_buffer_note`、`_price_tag`、badge 圖示字串、CSS、圖例文案：逐字複製
- `render_step3` 的選看按鈕：`st.button("選看", key=f"sel-{cand['candidate_key']}")` → `st.session_state[state_key] = cand["candidate_key"]; st.rerun()`（`state_key` 預設 `"selected_key"` 使 app.py 行為不變；工作區詳頁傳自己的 key）

**app.py 修改範圍（僅此三處，流程/session/錯誤處理不動）：**
1. 刪除被搬移的函數；頂部加 `from option_chaser import store` 與 `from webapp.render import (cell_color, heatmap_html, render_summary, render_step2, render_step3, render_step4, default_key, find_row)`（`cell_color`、`heatmap_html` re-export 供 test_heatmap_colors 取 source）。
2. `_selected_key(result)` 改收 view dict：

```python
def _selected_key(view) -> str | None:
    if "selected_key" not in st.session_state:
        st.session_state["selected_key"] = default_key(view)
    key = st.session_state["selected_key"]
    if find_row(view, key) is None and view["default_selection"]:
        key = view["default_selection"][1]
        st.session_state["selected_key"] = key
    return key
```

3. 兩處渲染點改為先轉 view（session 內仍存 AnalysisResult dataclass——`test_webapp.py`/`test_webapp_v4.py` 斷言 `session_state["result"].request...` 不變）：

```python
# 頂部 summary 分支：
else:
    render_summary(store.serialize_result(_result, "", None))
    ...
# 尾端四步：
if "result" in st.session_state:
    _final_result = st.session_state["result"]
    _view = store.serialize_result(_final_result, "", None)
    _key = _selected_key(_view)
    render_step2(_view, _key)
    render_step3(_view, _key)
    render_step4(_view, _key)
```

- [ ] **Step 1: 先跑既有 GUI 測試記錄基準**

Run: `python -m pytest tests/test_webapp.py tests/test_webapp_v4.py tests/test_heatmap_colors.py -v`
Expected: 全綠（基準）

- [ ] **Step 2: 建立 `webapp/render.py`**（依上表搬移全部渲染函數；模組 docstring 註明「v5 spec §5.1：四步渲染純函數，dict 介面，零金融公式」）

- [ ] **Step 3: 修改 `webapp/app.py`**（依上述三處）

- [ ] **Step 4: 既有測試不改而綠**

Run: `python -m pytest tests/test_webapp.py tests/test_webapp_v4.py tests/test_heatmap_colors.py -v && git diff --stat tests/`
Expected: 全綠；`git diff --stat tests/` 輸出空（tests 零改動的硬證據）

- [ ] **Step 5: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add webapp/render.py webapp/app.py
git commit -m "refactor(v5): extract four-step rendering to webapp/render.py (dict interface, output unchanged)"
```

---

### Task 10: 工作區 GUI 頁 `webapp/pages/0_劇本工作區.py`

**Files:**
- Create: `webapp/pages/0_劇本工作區.py`
- Test: `tests/test_webapp_workspace.py`

**Interfaces:**
- Consumes: `workspace.*`（Task 7-8）、`render.*`（Task 9）、`store.load_constraints/save_constraints`
- Produces: GUI 頁。工作區根目錄 = `os.environ.get("OC_WORKSPACE", "workspace")`（測試隔離鉤）。
- 「重新分析」按鈕顯示條件（spec §5.1 兩條件）：前一里程碑 `status=="Reached"` **且** 該 pair `confirmed=="milestone-path"`。

- [ ] **Step 1: 寫頁面**

```python
# webapp/pages/0_劇本工作區.py
"""v5 spec §5: 多劇本工作區（清單/建立/群組/詳頁/設定）。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from webapp.render import (esc, money, pct, render_step2, render_step3,
                           render_step4, render_summary)

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
STATUS_BADGE = {"Active": "🟢 Active", "Reached": "🏁 Reached",
                "Expired": "⌛ Expired", "Invalidated": "❌ Invalidated"}
RELATION_LABELS = {"milestone-path": "里程碑路徑", "independent": "獨立",
                   "exclusive": "互斥", "undefined": "暫不定義"}
PROPOSED_LABELS = {"milestone-path": "里程碑路徑", "review-needed": "需檢視",
                   "exclusive-candidate": "互斥候選"}

st.set_page_config(page_title="劇本工作區", layout="wide")
st.title("劇本工作區")


def _summary_of(sid: str):
    view = workspace.latest_result(WS_ROOT, sid)
    if view is None or not view["default_selection"]:
        return None
    key = view["default_selection"][1]
    for g in view["expiry_groups"]:
        for row in g["rows"]:
            if row["candidate"]["candidate_key"] == key:
                return view, row
    return None


def _analyze_with_status(fn, *args, **kw):
    try:
        with st.status("分析中……", expanded=True) as status:
            out = fn(*args, progress=status.write, **kw)
            status.update(label="分析完成", state="complete")
        return out
    except (FetchError, ParamError) as e:
        st.error(str(e))
    except Exception:
        st.error("分析過程發生錯誤，請稍後再試。")
    return None


# ---------- 設定區 ----------
constraints = store.load_constraints(WS_ROOT)
with st.expander("⚙ 設定", expanded=False):
    cur = constraints["total_capital"]
    cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                             value=float(cur or 0.0), step=1000.0,
                             key="ws-capital")
    if st.button("儲存設定", key="ws-save-capital"):
        store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
        st.rerun()

# ---------- 建立表單 ----------
# 不用 st.form：方向推測與策略預設需要即時 rerun 連動（spec §2.2/§5.1）。
with st.expander("＋ 建立劇本", expanded=False):
    st.text_input("標的", key="ws-new-symbol", placeholder="TLT")
    st.number_input("目標價位", key="ws-new-price", min_value=0.01,
                    value=100.0, step=1.0)
    sym = (st.session_state.get("ws-new-symbol") or "").strip().upper()
    inferred = (workspace.default_direction(
        sym, float(st.session_state.get("ws-new-price", 100.0)))
        if sym else None)
    # 無 snapshot → 必選（首項為空白佔位）；有 snapshot → 預設推測方向
    options = ("bullish", "bearish") if inferred else ("", "bullish", "bearish")
    dir_labels = {"": "（請選擇）", "bullish": "看漲", "bearish": "看跌"}
    idx = options.index(inferred) if inferred else 0
    direction = st.selectbox("方向", options, index=idx,
                             format_func=lambda d: dir_labels[d],
                             key="ws-new-direction")
    # 方向變更時重設策略勾選預設（LC+BCS 看漲、LP+BPS 看跌）；
    # 之後使用者手動勾選不再被覆蓋（僅在方向切換當下重設一次）。
    if direction and st.session_state.get("ws-new-dir-prev") != direction:
        st.session_state["ws-new-dir-prev"] = direction
        defaults = ({"long-call", "bull-call-spread"} if direction == "bullish"
                    else {"long-put", "bear-put-spread"})
        for s in STRATEGY_ORDER:
            st.session_state[f"ws-new-chk-{s}"] = s in defaults
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"ws-new-chk-{s}")
    st.date_input("目標日", key="ws-new-date",
                  value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    st.text_input("備註", key="ws-new-notes")
    if st.button("建立", key="ws-new-create"):
        strategies = tuple(s for s in STRATEGY_ORDER
                           if st.session_state.get(f"ws-new-chk-{s}"))
        if not sym:
            st.error("請輸入標的代號。")
        elif not direction:
            st.error("請選擇方向（此標的尚無 snapshot，無法自動推測）。")
        elif not strategies:
            st.error("請至少勾選一種策略。")
        else:
            workspace.create_scenario(
                WS_ROOT, symbol=sym, direction=direction,
                target_price=float(st.session_state["ws-new-price"]),
                target_date=st.session_state["ws-new-date"].isoformat(),
                notes=st.session_state["ws-new-notes"],
                strategies=strategies)
            st.rerun()

# ---------- 載入（含對帳） ----------
scenarios = workspace.list_scenarios(WS_ROOT)
by_id = {sc.id: sc for sc in scenarios}
groups = workspace.load_groups(WS_ROOT)

# ---------- 清單區 ----------
st.subheader("劇本清單")
if len(scenarios) > 6:
    st.warning(f"目前有 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
if not scenarios:
    st.info("尚無劇本。用上方「＋ 建立劇本」開始。")
for sc in scenarios:
    cols = st.columns([1.0, 0.7, 0.8, 0.9, 1.0, 0.8, 0.9, 2.2, 1.8])
    with cols[0]:
        st.markdown(f"**{sc.symbol}**")
    with cols[1]:
        st.markdown("看漲" if sc.direction == "bullish" else "看跌")
    with cols[2]:
        st.markdown(esc(f"${money(sc.target_price)}"))
    with cols[3]:
        st.markdown(sc.target_date)
    with cols[4]:
        st.markdown(STATUS_BADGE[sc.status])
    with cols[5]:
        st.markdown(sc.group_id)
    summary = _summary_of(sc.id)
    with cols[6]:
        if summary is not None:
            p = summary[1]["candidate"]["pct_of_capital"]
            st.markdown(f"佔本金 {pct(p)}" if p is not None else "—")
        else:
            st.markdown("—")
    with cols[7]:
        if summary is not None:
            row = summary[1]
            cand = row["candidate"]
            label = (f"買 {cand['legs'][0]['strike']:g} / "
                     f"賣 {cand['legs'][1]['strike']:g}"
                     if len(cand["legs"]) == 2
                     else f"K={cand['legs'][0]['strike']:g}")
            st.markdown(esc(
                f"{STRATEGY_LABELS[row['strategy']]} {label}｜"
                f"劇本報酬 {pct(cand['baseline_return'])}｜"
                f"情境最壞 {pct(cand['scenario_vector']['worst_return'])}"))
        else:
            st.markdown("尚未分析")
    with cols[8]:
        if st.button("分析", key=f"ws-an-{sc.id}"):
            # 僅成功才 rerun——失敗時 st.error 留在本次渲染，不被沖掉
            if _analyze_with_status(workspace.analyze_scenario, WS_ROOT,
                                    sc.id) is not None:
                st.rerun()
        if summary is not None and st.button("詳頁", key=f"ws-det-{sc.id}"):
            st.session_state["ws-detail"] = sc.id
            st.rerun()
    if sc.status == "Active":
        rcols = st.columns([3.0, 1.2, 1.2, 4.0])
        with rcols[0]:
            st.text_input("原因", key=f"ws-reason-{sc.id}",
                          placeholder="標記原因（必填）")
        reason = (st.session_state.get(f"ws-reason-{sc.id}") or "").strip()
        with rcols[1]:
            if st.button("標記達成", key=f"ws-reach-{sc.id}"):
                if reason:
                    workspace.set_status(WS_ROOT, sc.id, "Reached", reason)
                    st.rerun()
                else:
                    st.error("請填原因。")
        with rcols[2]:
            if st.button("標記失效", key=f"ws-inv-{sc.id}"):
                if reason:
                    workspace.set_status(WS_ROOT, sc.id, "Invalidated", reason)
                    st.rerun()
                else:
                    st.error("請填原因。")
    dcols = st.columns([1.6, 1.0, 7.0])
    with dcols[0]:
        st.checkbox("確認刪除", key=f"ws-delok-{sc.id}")
    with dcols[1]:
        if st.button("刪除", key=f"ws-del-{sc.id}"):
            if st.session_state.get(f"ws-delok-{sc.id}"):
                workspace.delete_scenario(WS_ROOT, sc.id)
                st.session_state.pop("ws-detail", None)
                st.rerun()
            else:
                st.error("請先勾選「確認刪除」。")
    st.divider()

# ---------- 群組區 ----------
st.subheader("劇本群組")
for g in groups["groups"]:
    members = [by_id[m] for m in g["members"] if m in by_id]
    if not members:
        continue
    st.markdown(f"**{g['id']}**（{len(members)} 個里程碑）")
    for sc in members:
        summary = _summary_of(sc.id)
        if summary is not None:
            cand = summary[1]["candidate"]
            line = (f"{sc.target_date} ${money(sc.target_price)}｜"
                    f"{STATUS_BADGE[sc.status]}｜"
                    f"劇本報酬 {pct(cand['baseline_return'])}｜"
                    f"情境最壞 {pct(cand['scenario_vector']['worst_return'])}｜"
                    f"緩衝 +{cand['buffer_days']} 天")
        else:
            line = (f"{sc.target_date} ${money(sc.target_price)}｜"
                    f"{STATUS_BADGE[sc.status]}｜尚未分析")
        st.markdown(esc(line))
    for i, rel in enumerate(g["relations"]):
        a_id, b_id = rel["pair"]
        st.markdown(esc(
            f"{a_id} ↔ {b_id}｜提案：{PROPOSED_LABELS[rel['proposed']]}｜"
            f"已確認：{RELATION_LABELS[rel['confirmed']]}"))
        ccols = st.columns([2.4, 1.0, 6.0])
        with ccols[0]:
            choice = st.selectbox(
                "確認關係", ("milestone-path", "independent", "exclusive",
                             "undefined"),
                format_func=lambda c: RELATION_LABELS[c],
                key=f"ws-rel-{g['id']}-{i}")
        with ccols[1]:
            if st.button("確認", key=f"ws-rel-btn-{g['id']}-{i}"):
                workspace.confirm_relation(WS_ROOT, g["id"], (a_id, b_id),
                                           choice)
                st.rerun()
        # spec §5.1 兩條件：前一里程碑 Reached 且 confirmed==milestone-path
        prev, nxt = by_id.get(a_id), by_id.get(b_id)
        if (prev is not None and nxt is not None
                and prev.status == "Reached"
                and rel["confirmed"] == "milestone-path"):
            if st.button(f"重新分析 {nxt.id}", key=f"ws-rean-{nxt.id}"):
                if _analyze_with_status(workspace.analyze_scenario, WS_ROOT,
                                        nxt.id) is not None:
                    st.rerun()
    if st.button("群組分析", key=f"ws-gan-{g['id']}"):
        if _analyze_with_status(workspace.analyze_group, WS_ROOT,
                                g["id"]) is not None:
            st.rerun()
    st.divider()

# ---------- 詳頁 ----------
detail_id = st.session_state.get("ws-detail")
if detail_id and detail_id in by_id:
    view = workspace.latest_result(WS_ROOT, detail_id)
    if view is not None:
        st.subheader(f"詳頁：{detail_id}")
        if st.button("關閉詳頁", key="ws-close-detail"):
            st.session_state.pop("ws-detail", None)
            st.rerun()
        render_summary(view)
        key = st.session_state.get("ws-selected-key")
        if key is None or all(
                row["candidate"]["candidate_key"] != key
                for gg in view["expiry_groups"] for row in gg["rows"]):
            key = (view["default_selection"][1]
                   if view["default_selection"] else None)
            st.session_state["ws-selected-key"] = key
        render_step2(view, key)
        render_step3(view, key, state_key="ws-selected-key")
        render_step4(view, key)
```

- [ ] **Step 2: 寫 AppTest 測試**

```python
# tests/test_webapp_workspace.py
"""v5 spec §7.7: 工作區 GUI（AppTest）。OC_WORKSPACE 隔離＋service seam 注入。"""
from datetime import date
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/pages/0_劇本工作區.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    import option_chaser.service as svc
    real_offline = svc.run_offline
    monkeypatch.setattr(svc, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))
    from option_chaser.data.snapshot import load_snapshot
    monkeypatch.setattr(svc, "fetch_and_save",
                        lambda symbol: (load_snapshot(FIX), FIX))
    return tmp_path


def _mk(ws_root, price=120.0, tdate="2026-08-01"):
    return workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=price,
        target_date=tdate, notes="", strategies=("long-call",), ts=TS)


def _body(at):
    return " ".join(m.value for m in at.markdown)


def test_create_via_form_appears_in_list(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.number_input(key="ws-new-price").set_value(120.0)
    at.date_input(key="ws-new-date").set_value(date(2026, 8, 1))
    at.run()
    # 測試 cwd 的 snapshots/ 無 XYZ_*.json → 無法推測 → 必選方向
    at.selectbox(key="ws-new-direction").set_value("bullish")
    at.run()
    assert at.session_state["ws-new-chk-long-call"] is True   # 方向連動預設策略
    assert at.session_state["ws-new-chk-long-put"] is False
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert not at.exception
    assert "XYZ" in _body(at)
    assert workspace.list_scenarios(ws)[0].id == "XYZ-120-202608"
    assert workspace.list_scenarios(ws)[0].direction == "bullish"


def test_create_requires_direction_when_no_snapshot(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("請選擇方向" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []


def test_analysis_error_stays_visible(ws, monkeypatch):
    """失敗不 rerun：st.error 留在畫面上（durable feedback）。"""
    sc = _mk(ws)
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-an-{sc.id}").set_value(True).run(timeout=30)
    assert any("boom" in e.value for e in at.error)
    assert not at.exception


def test_status_buttons_with_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key=f"ws-reason-{sc.id}").set_value("到價")
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Reached"


def test_status_button_requires_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert any("請填原因" in e.value for e in at.error)
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Active"


def test_group_card_and_relation_confirm(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    assert "G-XYZ" in body and "里程碑路徑" in body     # proposed 顯示
    next(bt for bt in at.button
         if bt.key == "ws-rel-btn-G-XYZ-0").set_value(True).run(timeout=30)
    assert not at.exception
    groups = workspace.load_groups(ws)
    assert groups["groups"][0]["relations"][0]["confirmed"] == "milestone-path"


def test_reanalyze_button_requires_both_conditions(ws):
    """負例×2＋正例：單一條件成立不出現（spec §7.7）。"""
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")

    def has_rean(at):
        return any(bt.key == f"ws-rean-{b.id}" for bt in at.button)

    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 皆不成立
    workspace.set_status(ws, a.id, "Reached", reason="到價", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 僅 Reached，未確認
    workspace.confirm_relation(ws, "G-XYZ", (a.id, b.id), "milestone-path",
                               ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert has_rean(at)                           # 兩條件成立
    # 反向單一條件：只確認、未 Reached
    workspace.delete_scenario(ws, a.id, ts=TS)
    c = _mk(ws, price=110.0, tdate="2026-08-01")
    workspace.confirm_relation(ws, "G-XYZ", (c.id, b.id), "milestone-path",
                               ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)


def test_capital_pct_shown_after_analysis(ws):
    sc = _mk(ws)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert "佔本金" in _body(at)


def test_detail_page_renders_four_steps(ws):
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-det-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    subheaders = " ".join(s.value for s in at.subheader)
    assert "Step 2" in subheaders and "Step 3" in subheaders \
        and "Step 4" in subheaders


def test_delete_button_full_chain(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.checkbox(key=f"ws-delok-{sc.id}").set_value(True)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-del-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert workspace.list_scenarios(ws) == []


def test_group_analyze_button_shares_snapshot(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")
    at = AppTest.from_file(PAGE)
    at.run()
    next(bt for bt in at.button
         if bt.key == "ws-gan-G-XYZ").set_value(True).run(timeout=60)
    assert not at.exception
    va = workspace.latest_result(ws, a.id)
    vb = workspace.latest_result(ws, b.id)
    assert va["snapshot_ref"]["path"] == vb["snapshot_ref"]["path"]
```

- [ ] **Step 3: 跑測試**

Run: `python -m pytest tests/test_webapp_workspace.py -v`
Expected: 11 passed（迭代修頁面直到綠；AppTest 對 st.status 的相容性若有問題，`_analyze_with_status` 允許降級為 `st.spinner`——文案不變）

- [ ] **Step 4: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add webapp/pages/0_劇本工作區.py tests/test_webapp_workspace.py
git commit -m "feat(v5): multi-scenario workspace GUI page + AppTest suite"
```

---

### Task 11: 紅線掃描擴充、glossary/說明頁、README、compose、.gitignore、總回歸

**Files:**
- Modify: `tests/test_redlines.py`、`option_chaser/glossary.py`、`webapp/pages/1_說明.py`、`README.md`、`compose.yaml`、`.gitignore`

**Interfaces:**
- Consumes: 全部前置 task 的檔案存在
- Produces: spec §5.2/§6/§8 的收尾交付

- [ ] **Step 1: 擴充紅線掃描（先改測試）**

`tests/test_redlines.py` 兩處清單各加 4 個新檔：

```python
TARGETS = [Path("webapp/app.py"), Path("webapp/pages/1_說明.py"),
           Path("option_chaser/glossary.py"),
           Path("option_chaser/store.py"), Path("option_chaser/workspace.py"),
           Path("option_chaser/vocabulary.py"),
           Path("webapp/render.py"), Path("webapp/pages/0_劇本工作區.py"),
           *sorted(Path("tests/fixtures").glob("golden_*.txt"))]
```

`test_new_copy_avoids_bare_probability_word` 的清單追加：

```python
                 Path("option_chaser/store.py"),
                 Path("option_chaser/workspace.py"),
                 Path("option_chaser/vocabulary.py"),
                 Path("webapp/render.py"),
                 Path("webapp/pages/0_劇本工作區.py"),
```

Run: `python -m pytest tests/test_redlines.py -v`
Expected: PASS（若 FAIL 表示新檔有禁詞——修檔案文案，不修測試）

- [ ] **Step 2: glossary 增 5 詞**（`option_chaser/glossary.py` 的 `GLOSSARY` dict 加入）

```python
    "劇本群組": "同一標的下多個劇本的集合；純顯示分組，不進任何計算。",
    "里程碑": "群組內依目標日排序的單一劇本；前一個標記達成後可手動重新分析下一個。",
    "狀態": "劇本生命週期：Active（進行中）/ Reached（已達成）/ Expired（已過期）/ Invalidated（已失效）。",
    "佔本金%": "最佳候選的每口成本（Mid×100）除以你設定的資金總額；僅在分析當下有設定資金時記錄。",
    "資料品質": "此次分析的資料狀態：若所有策略皆因報價異常而無合格合約，代表資料可能不可用（如盤前），而非市場無機會。",
```

- [ ] **Step 3: 說明頁增補一節**（`webapp/pages/1_說明.py` 末尾照該檔既有寫法追加一節）

內容（照檔內既有 st.markdown 格式落款）：

```
## 劇本工作區

- **劇本**：一組「標的＋方向＋目標價＋目標日」的持久化假設；建立後唯讀，改錯請刪除重建。
- **群組**：同標的劇本自動歸為一組（純顯示，不影響計算）；相鄰劇本會依方向與價位提出關係提案，由你四選確認（里程碑路徑／獨立／互斥／暫不定義）。
- **里程碑**：群組內依目標日排序的劇本序列；前一個標記「達成」且關係已確認為里程碑路徑時，下一個出現「重新分析」按鈕（純手動，零自動化）。
- **狀態**：Active → Reached／Invalidated 由你手動標記（必附原因）；目標日過後讀取工作區時自動轉 Expired。所有狀態變更都寫入事件日誌，可審計。
```

- [ ] **Step 4: compose.yaml 加 workspace 掛載、.gitignore 加 workspace/**

```yaml
    volumes:
      - ./snapshots:/app/snapshots
      - ./workspace:/app/workspace
```

`.gitignore` 追加一行：`workspace/`

- [ ] **Step 5: README 加「多劇本工作區」章節**（照 README 既有語氣；內容涵蓋：workspace/ 佈局五檔、劇本生命週期四態、群組與關係四選、群組分析共用 snapshot、佔本金% 需先設資金、事件日誌可審計、result 檔為機器可讀 JSON 契約 schema_version 1）

- [ ] **Step 6: 全套件總回歸＋驗收清單自查**

Run: `python -m pytest -q`
Expected: 全綠（177 舊＋約 60 新）

對照 spec §8 驗收案例 1-7 逐條自查（1-4 由 test_workspace*/test_webapp_workspace 覆蓋；5 由 test_store_events/test_workspace 覆蓋；6 由 Task 9 Step 4 覆蓋；7 由 test_redlines 覆蓋）。

- [ ] **Step 7: Commit**

```bash
git add tests/test_redlines.py option_chaser/glossary.py webapp/pages/1_說明.py README.md compose.yaml .gitignore
git commit -m "feat(v5): redline scan expansion, workspace docs/glossary, docker workspace mount"
```

---

## Self-Review 紀錄

- **Spec 覆蓋**：§2.1→T2/T5（佈局、原子寫入、snapshot_ts、compose 掛載 T11）；§2.2→T2/T3/T7（實體、id、轉移、兩型、NY 觀察日）；§2.3→T1/T3（enum、行序權威、生命週期）；§2.4→T4（快取語意、提案、生命週期界定）；§2.5→T3/T7（次序、對帳矩陣）；§2.6→T2；§3→T5（含 doc-sync）；§4→T6/T7/T8；§5→T9/T10（按鈕兩條件、清單 pct 非回溯）；§5.2→T11；§6→T1/T3（值域鎖定）；§7.1-7.9→對應測試檔；§8→T11 Step 6；§9 不做清單→無任務觸碰。
- **型別一致**：`Scenario`/`serialize_result`/candidate dict 鍵名在 T5 Interfaces 定義一次，T9/T10 引用同名；`analyze_scenario(..., snapshot_path=, ts=)` 簽名 T8 定義、T10 測試同形使用。
- **已知妥協（review 時檢視）**：(a) T5 `strategy_of_row` 標註「未用即刪」；(b) T10 `st.status` 相容性允許降級 `st.spinner`；(c) 建立表單不用 `st.form`（方向推測與策略預設需即時 rerun 連動；無 snapshot 時方向為空白佔位必選，測試鎖定）。

<!-- codex-peer-reviewed: 2026-07-21T06:04:29Z rounds=2 verdict=approved -->
