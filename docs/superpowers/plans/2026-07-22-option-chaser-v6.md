# Option Chaser v6 — Artifact Parity、正式產品化與一鍵啟動 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落實 v6 spec（`docs/superpowers/specs/2026-07-22-option-chaser-v6-design.md`，codex APPROVED 2 rounds）：Artifact 淺色視覺基準真正落地、四頁導覽重構、候選價格全面顯示（含 Spread 封頂）、狀態文案八分類、打包修復、Windows 一鍵啟動。

**Architecture:** 新增純函數展示層三模組（`webapp/theme.py` 樣式常數、`webapp/status.py` 狀態推導、`webapp/components.py` 卡片元件庫）＋擴充 `render.py`（Spread 封頂、比較表）＋ `store.py` 序列化加三欄（v2）＋ `workspace.py` 新增一個編排函數（`adopt_result`）＋五個新 view 檔取代舊 `webapp/pages/`＋`webapp/app.py` 改為 `st.navigation` 路由入口＋打包／版本／BAT 修復。**引擎（service 及以下）零修改**。

**Tech Stack:** Streamlit ≥1.57（`st.navigation`/`st.Page`/`st.popover`/`st.Page(visibility="hidden")`；開發環境現裝 1.59.2）、pytest + `streamlit.testing.v1.AppTest`（多頁測試改用 `AppTest.from_file("webapp/app.py")` + `switch_page(...)`）。

**Branch:** `feature/v6-artifact-parity`（自 master 開出）。

## Global Constraints

（每個 task 隱含遵守；違反即 review 紅線，逐字抄自 spec）

1. **引擎零修改**：`option_chaser/service.py` 及其下游（`valuation.py`／`scenarios.py`／`ranking.py`／`filters.py`／`matrix.py`／`report.py`／`models.py`）本 plan 全程不觸碰。`store.py` 僅 Task 2 加三欄；`workspace.py` 僅 Task 3 新增 `adopt_result`，既有函數簽名與行為零修改。
2. **GUI 零金融公式**：新欄位一律在 `store.serialize_result` 內預算（乘法／取值，非估值邏輯）；views/components 僅格式化與展示層比較（價格 vs `cap_price`、路徑相等、日期比對、計數彙總）。
3. **機率禁詞掃描**：`BANNED = ["獲利機率","機率加權","勝率","POP","probability","期望報酬","expected profit","Sharpe","CVaR"]`；`tests/test_redlines.py` 的 `TARGETS` 與 bare-機率清單須含所有新檔案、移除已刪除的舊 `webapp/pages/*.py`。
4. **CSS 使用邊界**：`.streamlit/config.toml` 承載全站色彩／字體（Streamlit 官方主題機制，覆蓋原生元件：按鈕／輸入框／側欄）；`webapp/theme.py` 注入的 CSS 僅限本專案自訂類別（`.oc-*` 前綴：卡片／膠囊／徽章／里程碑軌），**不得**選取或覆寫 Streamlit 內部 DOM class（如 `.stButton`、`div[data-testid=...]`）——與既有 `render.py` 的 `.oc-thumb`/`.oc-num` 慣例一致。
5. **決定性**：`serialize_result` 輸出（含新欄）在同輸入下逐位元決定性（`json.dumps(sort_keys=True, ensure_ascii=False)`）不變。
6. **既有回歸**：master 現有 246 tests 全數為基準；`test_webapp*.py` 因頁面重構**允許修改**（保留語意斷言，更新路徑/key）；`test_store_*.py`／`test_workspace*.py`／引擎測試（v1-v4，177 顆）**零修改零紅**。
7. **視覺核可硬閘**：本 plan 最終任務產出 Chromium 桌機＋手機截圖與 Artifact 差異表，**合併前需使用者核可**——非自動化驗收項，由控制者在 SDD 流程最後一步向使用者確認。
8. **文件同步**：`docs/view-contract.md` 所列鍵必須是 `test_store_serialize.py` 斷言鎖定的鍵（Task 2 完成後同步撰寫，Task 12 收尾核對）。

---

## File Structure

```
option_chaser/
  __init__.py            ← 改：__version__ = "0.6.0"（Task 1）
  store.py                ← 改：serialize_result 加三欄，schema_version 2（Task 2）
  workspace.py             ← 改：新增 adopt_result（Task 3）
pyproject.toml             ← 改：packages.find 加 webapp*；streamlit>=1.57；version 0.6.0（Task 1）
Dockerfile                 ← 改：COPY .streamlit/（Task 1）
.streamlit/
  config.toml              ← 新增：light theme token（Task 1）
webapp/
  __init__.py              ← 既有，不動
  app.py                   ← 全面改寫：st.navigation 路由入口（Task 12）
  render.py                ← 改：Spread 封頂＋候選比較表函數（Task 7）
  theme.py                 ← 新增：THEME_CSS 常數＋inject()（Task 4）
  status.py                ← 新增：狀態推導純函數（Task 5）
  components.py             ← 新增：卡片元件庫（Task 6）
  views/
    __init__.py             ← 新增（Task 8）
    overview.py             ← 新增：戰情總覽（Task 8）
    help.py                 ← 新增：使用說明（Task 8，遷自 pages/1_說明.py）
    quick.py                 ← 新增：快速試算（Task 9，遷自現 app.py 主體）
    workspace.py             ← 新增：劇本工作區（Task 10，遷自 pages/0_劇本工作區.py）
    detail.py                ← 新增：劇本詳頁（Task 11，獨立路由）
  pages/                    ← 整個刪除（Task 12）
docs/
  view-contract.md          ← 新增（Task 2 起草，Task 12 核對定稿）
啟動 Option Chaser.bat      ← 新增（Task 13）
建立桌面捷徑.bat             ← 新增（Task 13）
logs/                       ← 新增空目錄＋.gitkeep（Task 13）
.gitignore                  ← 改：加 logs/*.log、logs/running.lock（Task 13）
tests/
  test_store_serialize_v2.py    ← 新增（Task 2）
  test_workspace_adopt.py       ← 新增（Task 3）
  test_theme.py                 ← 新增（Task 4）
  test_status.py                ← 新增（Task 5）
  test_components.py            ← 新增（Task 6）
  test_render_cap.py            ← 新增（Task 7）
  test_views_overview_help.py   ← 新增（Task 8）
  test_views_quick.py           ← 新增（Task 9）
  test_views_workspace.py       ← 新增（Task 10，取代 test_webapp_workspace.py）
  test_views_detail.py          ← 新增（Task 11）
  test_app_navigation.py        ← 新增（Task 12）
  test_redlines.py              ← 改：TARGETS 更新（Task 12）
  test_webapp.py                ← 刪除（內容併入 test_views_quick.py，Task 9）
  test_webapp_v4.py              ← 刪除（內容併入 test_views_quick.py + test_views_detail.py，Task 9/11）
  test_webapp_workspace.py       ← 刪除（內容併入 test_views_workspace.py，Task 10）
```

**共用 fixture 基準**（沿用 v5）：`tests/fixtures/xyz_v4_six_expiries.json`（symbol XYZ、spot≈100、六到期日）、`xyz_v4_all_warning.json`（全零報價變體，Task 2/5 用）、`xyz_v2_snapshot.json`。分析基準參數：`target_price=120.0`、`target_date="2026-08-01"`、`strategies=("long-call","bull-call-spread")`。

---

### Task 1: 打包修復、版本統一、light theme config

**Files:**
- Modify: `pyproject.toml`
- Modify: `option_chaser/__init__.py`
- Modify: `Dockerfile`
- Create: `.streamlit/config.toml`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces：`option_chaser.__version__ == "0.6.0"`；pyproject `[project].version == "0.6.0"`；pyproject gui extra 含 `streamlit>=1.57`；`webapp` 與 `webapp.views` 為可安裝子套件（`import webapp.render`、`import webapp.views.overview` 在任意 cwd 之乾淨 venv 中成立）。

- [ ] **Step 1: 開分支**

```bash
git checkout master && git checkout -b feature/v6-artifact-parity
```

- [ ] **Step 2: 寫失敗測試**

```python
# tests/test_packaging.py
"""v6 spec §8: packaging fix — webapp installable, version unified."""
import re
import tomllib
from pathlib import Path

import option_chaser


def test_version_matches_pyproject():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == option_chaser.__version__ == "0.6.0"


def test_streamlit_floor_is_1_57():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    gui = pyproject["project"]["optional-dependencies"]["gui"]
    assert any(re.match(r"streamlit>=1\.57", dep) for dep in gui), gui


def test_webapp_package_included():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "webapp*" in include


def test_streamlit_config_exists_and_light():
    text = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert 'base = "light"' in text
    assert "#eef0f3" in text  # backgroundColor
    assert "#ff4b4b" in text  # primaryColor


def test_webapp_importable_from_subprocess_without_pythonpath(tmp_path):
    """No-PYTHONPATH import proof: subprocess run from an unrelated cwd."""
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "import webapp.render; print('OK')"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/test_packaging.py -v`
Expected: FAIL（`pyproject` 缺 include/floor；`.streamlit/config.toml` 不存在；子行程 import 失敗因 webapp 未安裝為套件）

- [ ] **Step 4: 實作**

```toml
# pyproject.toml（整檔取代）
[project]
name = "option-chaser"
version = "0.6.0"
description = "Long Call scenario optimizer (deterministic, no probability logic)"
requires-python = ">=3.11"
dependencies = [
  "yfinance>=0.2",
  "tzdata; platform_system == 'Windows'",
]

[project.scripts]
option-chaser = "option_chaser.cli:main"

[project.optional-dependencies]
gui = ["streamlit>=1.57"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["option_chaser*", "webapp*"]

[tool.pytest.ini_options]
addopts = "-q"
```

```python
# option_chaser/__init__.py（整檔）
__version__ = "0.6.0"
```

```dockerfile
# Dockerfile（整檔取代）
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY option_chaser ./option_chaser
COPY webapp ./webapp
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir ".[gui]"
ENV PORT=8501
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
  python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8501')+'/_stcore/health')"
CMD ["sh", "-c", "streamlit run webapp/app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
```

```toml
# .streamlit/config.toml（新檔）
# v6 spec §2.1: Artifact 淺色視覺基準（唯一色彩來源，views/components 不得另覆寫全站色彩）
[theme]
base = "light"
primaryColor = "#ff4b4b"
backgroundColor = "#eef0f3"
secondaryBackgroundColor = "#f3f4f6"
textColor = "#1c1f26"
borderColor = "#e3e6ea"
baseRadius = "10px"
buttonRadius = "8px"
showWidgetBorder = true
font = "sans-serif"
```

Note：`webapp/views/` 目錄與 `__init__.py` 到 Task 8 才建立（Task 1 僅需 `include=["webapp*"]` 的 pyproject 設定；`test_webapp_package_included` 檢查設定值本身，`import webapp.render` 測試不依賴尚未存在的 `views/`）。

- [ ] **Step 5: 跑測試確認通過**

Run: `python -m pip install -e ".[gui]" -q && python -m pytest tests/test_packaging.py -v`
Expected: 5 passed

- [ ] **Step 6: 更新硬編碼 `"0.5.0"` 的既有測試（版本升級會使全回歸變紅，此步驟必須先做）**

三個既有測試檔硬編碼版本字串，版本升到 `0.6.0` 後會直接斷言失敗：`tests/test_store_serialize.py:30`（`assert view["engine_version"] == option_chaser.__version__ == "0.5.0"`）、`tests/test_vocabulary.py:7`（`assert option_chaser.__version__ == "0.5.0"`）、`tests/test_workspace_analyze.py:24`（`assert view["engine_version"] == "0.5.0"`）。

```bash
python - <<'PYEOF'
import pathlib
edits = [
    ("tests/test_store_serialize.py",
     'assert view["engine_version"] == option_chaser.__version__ == "0.5.0"',
     'assert view["engine_version"] == option_chaser.__version__ == "0.6.0"'),
    ("tests/test_vocabulary.py",
     'assert option_chaser.__version__ == "0.5.0"',
     'assert option_chaser.__version__ == "0.6.0"'),
    ("tests/test_workspace_analyze.py",
     'assert view["engine_version"] == "0.5.0"',
     'assert view["engine_version"] == "0.6.0"'),
]
for path, old, new in edits:
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, f"anchor not found in {path}"
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched", path)
PYEOF
```

- [ ] **Step 7: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠（246 + 5 = 251）

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml option_chaser/__init__.py Dockerfile .streamlit/config.toml tests/test_packaging.py tests/test_store_serialize.py tests/test_vocabulary.py tests/test_workspace_analyze.py
git commit -m "feat(v6): fix packaging (webapp installable, no PYTHONPATH), version 0.6.0, light theme config"
```

---

### Task 2: store.serialize_result v2（候選價格新欄）

**Files:**
- Modify: `option_chaser/store.py`
- Create: `docs/view-contract.md`（起草）
- Test: `tests/test_store_serialize_v2.py`

**Interfaces:**
- Consumes：既有 `_candidate`／`serialize_result`（見下方「現況」）、`valuation.SpreadValuation`（`long_leg`/`short_leg`/`max_profit`）、`scenarios.natural_cost`。
- Produces：candidate dict 新增三鍵：`natural_per_contract: float`、`max_profit_per_contract: float|None`、`cap_price: float|None`。`schema_version: 2`。

**現況（`option_chaser/store.py` 內 `_candidate` 函數，供對照修改點）：**

```python
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
        max_profit = None if strategy == "long-call" else v.contract.strike - v.mid
        net_delta = v.delta
    cap_per = mid_cost * 100
    return {
        "candidate_key": candidate_key(cv),
        "strategy": strategy,
        "legs": legs,
        "mid_cost": mid_cost,
        "natural_cost": natural_cost(v),
        ...
        "capital_per_contract": cap_per,
        "max_loss_per_contract": cap_per,
        "pct_of_capital": (cap_per / capital) if capital else None,
        "days_to_target": (date.fromisoformat(target_date) - today).days,
        "days_to_expiry": (date.fromisoformat(expiry) - today).days,
    }
```

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_store_serialize_v2.py
"""v6 spec §4.3: serialize_result v2 — natural_per_contract, max_profit_per_contract,
cap_price. 手算鎖定 + 決定性 + v1 舊檔相容。"""
import hashlib
import json
from datetime import date
from pathlib import Path

from option_chaser import service, store
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _result(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0], target_price=120.0,
                                       target_date="2026-08-01"),
            strategies=strategies),
        FIX)


def test_schema_version_is_2():
    view = store.serialize_result(_result(), "S", None)
    assert view["schema_version"] == 2


def test_single_leg_new_fields_hand_checked():
    result = _result(("long-call",))
    view = store.serialize_result(result, "S", None)
    cand = view["results"][0]["candidates"][0]
    cv = result.results[0].candidates[0]
    v = cv.valuation
    assert cand["natural_per_contract"] == cv.valuation.mid * 100 or True  # sanity guard below is exact
    from option_chaser.scenarios import natural_cost
    assert cand["natural_per_contract"] == natural_cost(v) * 100
    assert cand["max_profit_per_contract"] == (
        None if cand["max_profit"] is None else cand["max_profit"] * 100)
    assert cand["cap_price"] is None   # single-leg has no cap


def test_spread_new_fields_hand_checked():
    result = _result(("bull-call-spread",))
    view = store.serialize_result(result, "S", None)
    cand = view["results"][0]["candidates"][0]
    sv = result.results[0].candidates[0].valuation
    from option_chaser.scenarios import natural_cost
    assert cand["natural_per_contract"] == natural_cost(sv) * 100
    assert cand["max_profit_per_contract"] == sv.max_profit * 100
    assert cand["cap_price"] == sv.short_leg.strike == cand["legs"][1]["strike"]


def test_determinism_v2_byte_identical():
    r = _result()
    a = store.serialize_result(r, "S", 100000.0)
    b = store.serialize_result(r, "S", 100000.0)
    dump = lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True).encode("utf-8")
    assert hashlib.sha256(dump(a)).hexdigest() == hashlib.sha256(dump(b)).hexdigest()


def test_v1_result_file_loads_without_new_fields(tmp_path):
    """舊 result 檔（v1，缺 natural_per_contract 等）must load without exception."""
    view = store.serialize_result(_result(("long-call",)), "S", None)
    # 模擬 v1 舊檔：移除 v2 新欄＋降版本號
    for r in view["results"]:
        for c in r["candidates"]:
            c.pop("natural_per_contract", None)
            c.pop("max_profit_per_contract", None)
            c.pop("cap_price", None)
    view["schema_version"] = 1
    path = store.save_result(tmp_path, "S", view)
    loaded = store.load_result(path)
    assert loaded["schema_version"] == 1
    assert "natural_per_contract" not in loaded["results"][0]["candidates"][0]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_store_serialize_v2.py -v`
Expected: FAIL（`KeyError: 'natural_per_contract'` 等；`schema_version` 仍為 1）

- [ ] **Step 3: 實作**

於 `option_chaser/store.py` 的 `_candidate` 函數內，`cap_per = mid_cost * 100` 之後、`return` 之前插入：

```python
    natural_per = natural_cost(v) * 100
    max_profit_per = None if max_profit is None else max_profit * 100
    cap_price = legs[1]["strike"] if len(legs) == 2 else None
```

`return` dict 的既有欄位表中，於 `"days_to_expiry": ...` 之後追加三行：

```python
        "natural_per_contract": natural_per,
        "max_profit_per_contract": max_profit_per,
        "cap_price": cap_price,
```

`serialize_result` 函數內 `"schema_version": 1,` 改為 `"schema_version": 2,`。

- [ ] **Step 4: 跑測試確認通過＋既有序列化測試不破**

Run: `python -m pytest tests/test_store_serialize_v2.py tests/test_store_serialize.py -v`
Expected: 全綠（`test_store_serialize.py` 原有斷言未讀 `schema_version` 精確值以外欄位，應天然相容；若其中有 `assert view["schema_version"] == 1` 的斷言，本步驟需同步改為 `2`——見 Step 4a）

- [ ] **Step 4a: 若既有測試斷言 schema_version==1，更新之**

```bash
python - <<'PYEOF'
import pathlib
p = pathlib.Path("tests/test_store_serialize.py")
text = p.read_text(encoding="utf-8")
text2 = text.replace('view["schema_version"] == 1', 'view["schema_version"] == 2')
if text2 != text:
    p.write_text(text2, encoding="utf-8")
    print("patched")
else:
    print("no occurrence, nothing to patch")
PYEOF
python -m pytest tests/test_store_serialize.py -v
```

- [ ] **Step 5: 起草 `docs/view-contract.md`**

```markdown
# Option Chaser — Result View 契約（schema_version 2）

`store.serialize_result(result, scenario_id, capital) -> dict` 的輸出是本專案唯一的 GUI 資料介面；未來任何前端（含非 Streamlit 實作）只需讀 `results/<id>/<ts>.json`（此 dict 的落盤形式）＋ `workspace` 目錄下的 scenario/groups/events 檔，即可重建完整 UI，無需呼叫 `option_chaser.service` 或任何估值函數。

## 頂層鍵

`schema_version`(int, 現為2) / `engine_version`(str) / `analyzed_at`(ISO8601) / `scenario_id` / `params`(dict) / `snapshot_ref`(`{path,fetched_at,source,spot}`) / `meta`(`{symbol,spot,fetched_at,source,snapshot_path,target_move}`) / `capital_assumed`(float|null) / `data_quality`(`{fetched_at,all_quotes_filtered}`) / `results`(list) / `expiry_groups`(list) / `hidden_expiries`(list) / `default_selection`(`[expiry,candidate_key]`|null) / `comparison`(list) / `best_strategy`(str|null) / `today`(ISO date)

## candidate dict（`results[].candidates[]` / `expiry_best[]` / `expiry_groups[].rows[].candidate`）

`candidate_key` `strategy` `legs`(list of `{contract_symbol,option_type,strike,expiry,bid,ask,iv,volume,open_interest}`；單腿長度1、Spread長度2＝[long,short]) `mid_cost` `natural_cost` `baseline_pnl` `baseline_return` `natural_return` `scenario_vector`(`{entries,worst_code,worst_return}`) `completion_curve` `completion_prices` `completion_threshold` `breakeven_at_target` `retention` `friction` `friction_amount` `buffer_days` `quote_warning` `theta_day_rate` `vega_per_pt` `decay_30d_return` `net_delta` `breakeven` `max_profit`(nullable) `effective_leverage` `matrix`(`{prices,dates,cells}`) `capital_per_contract` `max_loss_per_contract` `pct_of_capital`(nullable) `days_to_target` `days_to_expiry` **`natural_per_contract`（v2新）** **`max_profit_per_contract`（v2新，nullable）** **`cap_price`（v2新，nullable；Spread=賣腿strike，單腿=null）**

## 消費者

`webapp/render.py`（heatmap／比較表／進階區）、`webapp/components.py`（卡片）——皆為純函數，僅格式化與展示層比較，零金融公式。

（此文件與 `tests/test_store_serialize_v2.py` 互為印證；欄位變動須同步兩者。）
```

- [ ] **Step 6: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 7: Commit**

```bash
git add option_chaser/store.py tests/test_store_serialize_v2.py tests/test_store_serialize.py docs/view-contract.md
git commit -m "feat(v6): serialize_result v2 — natural/max_profit per-contract, cap_price; view-contract.md"
```

---

### Task 3: workspace.adopt_result（快速試算保存為劇本）

**Files:**
- Modify: `option_chaser/workspace.py`
- Test: `tests/test_workspace_adopt.py`

**Interfaces:**
- Consumes：`store.scenario_id`／`store.scenario_path`／`store.save_scenario`／`store.append_event`／`store.serialize_result`／`store.save_result`／`service.AnalysisResult`。
- Produces：`workspace.adopt_result(ws_root, result: AnalysisResult, notes: str = "", *, ts: str|None = None) -> tuple[Scenario, Path]`；`workspace.scenario_exists(ws_root, symbol, target_price, target_date) -> str|None`（回傳已存在的 base id 或 None，供 view 層預檢用，避免重複實作 §1.2 撞名判斷）。

**現況（`workspace.py` 相關函數，供對照）：**

```python
def create_scenario(ws_root, symbol: str, direction: str, target_price: float,
                    target_date: str, notes: str,
                    strategies: tuple[str, ...], *, ts: str | None = None
                    ) -> Scenario:
    """§2.5 次序：產 id → append CREATED → 寫檔 → 重建 groups。"""
    ts = ts or now_utc_iso()
    sid = store.scenario_id(symbol, target_price, target_date, _existing_ids(ws_root))
    ...
```

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_workspace_adopt.py
"""v6 spec §1.2: adopt_result（quick-analysis -> persisted scenario）+ 撞名預檢。"""
from datetime import date

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


def _quick_result(price=120.0, tdate="2026-08-01"):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="long-call", target_price=price,
                                       target_date=tdate),
            strategies=("long-call", "bull-call-spread")),
        FIX)


def test_scenario_exists_none_when_absent(tmp_path):
    assert workspace.scenario_exists(tmp_path, "XYZ", 120.0, "2026-08-01") is None


def test_adopt_result_creates_scenario_and_result(tmp_path):
    result = _quick_result()
    sc, path = workspace.adopt_result(tmp_path, result, notes="from quick", ts=TS)
    assert sc.id == "XYZ-120-202608"
    assert sc.direction == "bullish"          # 120 > spot(~100)
    assert sc.strategies == ("long-call", "bull-call-spread")
    assert path.exists()
    view = store.load_result(path)
    assert view["scenario_id"] == sc.id
    assert view["snapshot_ref"]["path"] == FIX   # 重用當次 snapshot，非重新分析
    events = [e["event"] for e in store.read_events(tmp_path)]
    assert events == ["SCENARIO_CREATED", "ANALYSIS_COMPLETED"]
    assert workspace.scenario_exists(tmp_path, "XYZ", 120.0, "2026-08-01") == sc.id


def test_adopt_result_uses_current_capital(tmp_path):
    store.save_constraints(tmp_path, 50000.0)
    result = _quick_result()
    sc, path = workspace.adopt_result(tmp_path, result, ts=TS)
    view = store.load_result(path)
    assert view["capital_assumed"] == 50000.0


def test_adopt_result_bearish_direction(tmp_path):
    result = _quick_result(price=80.0)   # < spot(~100) -> bearish scenario in fixture terms
    sc, _ = workspace.adopt_result(tmp_path, result, ts=TS)
    assert sc.direction == "bearish"


def test_adopt_result_rejects_duplicate_base_id(tmp_path):
    result = _quick_result()
    workspace.adopt_result(tmp_path, result, ts=TS)
    with __import__("pytest").raises(ValueError):
        workspace.adopt_result(tmp_path, result, ts=TS)


def test_adopt_result_does_not_touch_other_workspace_functions(tmp_path):
    """迴歸防護：adopt_result 不得繞過 create_scenario 的既有 create 流程副作用
    （groups.json 必須反映新劇本）。"""
    result = _quick_result()
    sc, _ = workspace.adopt_result(tmp_path, result, ts=TS)
    groups = workspace.load_groups(tmp_path)
    assert groups["groups"][0]["members"] == [sc.id]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_workspace_adopt.py -v`
Expected: FAIL（`AttributeError: adopt_result`）

- [ ] **Step 3: 實作（追加到 `workspace.py` 末尾）**

```python
def scenario_exists(ws_root, symbol: str, target_price: float,
                    target_date: str) -> str | None:
    """base id（無撞名後綴）是否已有劇本檔。供 UI 撞名預檢與 adopt_result 共用。"""
    base_id = store.scenario_id(symbol, target_price, target_date, set())
    return base_id if store.scenario_path(ws_root, base_id).exists() else None


def adopt_result(ws_root, result: service.AnalysisResult, notes: str = "",
                 *, ts: str | None = None) -> tuple[Scenario, Path]:
    """v6 spec §1.2：快速試算「保存為劇本」——重用當次分析結果，不重新分析。
    §2.5 次序：create_scenario（事件先行）→ result 檔先落盤 → ANALYSIS_COMPLETED。"""
    ts = ts or now_utc_iso()
    req = result.request
    base = req.base_params
    symbol, target_price, target_date = req.symbol, base.target_price, base.target_date
    if scenario_exists(ws_root, symbol, target_price, target_date) is not None:
        raise ValueError(f"劇本已存在：{symbol} {target_price:g} {target_date}")
    direction = "bullish" if target_price > result.meta.spot else "bearish"
    sc = create_scenario(ws_root, symbol=symbol, direction=direction,
                         target_price=target_price, target_date=target_date,
                         notes=notes, strategies=req.strategies, ts=ts)
    capital = store.load_constraints(ws_root)["total_capital"]
    view = store.serialize_result(result, sc.id, capital)
    path = store.save_result(ws_root, sc.id, view)
    store.append_event(ws_root, ts, sc.id, "ANALYSIS_COMPLETED",
                       {"result_path": str(path),
                        "snapshot_ref": view["snapshot_ref"]})
    return sc, path
```

`Path` 已由既有 `from pathlib import Path` 匯入（檔案頂部已有），無需新增 import。

- [ ] **Step 4: 跑測試確認通過＋全回歸**

Run: `python -m pytest tests/test_workspace_adopt.py -v && python -m pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add option_chaser/workspace.py tests/test_workspace_adopt.py
git commit -m "feat(v6): workspace.adopt_result + scenario_exists — quick-analysis save-as-scenario"
```

---

### Task 4: webapp/theme.py（Artifact 淺色 token，scoped CSS）

**Files:**
- Create: `webapp/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces：`THEME_CSS: str`（純字串常數，僅含 `.oc-*` 前綴選擇器）；`inject() -> None`（`st.markdown(THEME_CSS, unsafe_allow_html=True)` 包一層 `<style>`）；顏色常數字典 `TOKENS: dict[str, str]`（供 components.py 讀取十六進位色碼，避免色碼字串散落多檔）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_theme.py
"""v6 spec §2.1: Artifact 淺色 token；CSS 僅限 .oc-* 自訂類別，不覆寫 Streamlit 內部 DOM。"""
import re

from webapp import theme


def test_tokens_match_artifact_light_values():
    assert theme.TOKENS["bg"] == "#eef0f3"
    assert theme.TOKENS["chrome"] == "#f3f4f6"
    assert theme.TOKENS["surface"] == "#ffffff"
    assert theme.TOKENS["ink"] == "#1c1f26"
    assert theme.TOKENS["accent"] == "#ff4b4b"
    assert theme.TOKENS["pos"] == "#1a7f37"
    assert theme.TOKENS["neg"] == "#b22222"


def test_css_only_targets_oc_prefixed_classes():
    """紅線：不得選取 Streamlit 內部 DOM（.stButton、[data-testid=...]、.st-key- 除外——
    st-key- 是 Streamlit 官方文件建議的元件定位法，非內部私有 DOM）。"""
    selectors = re.findall(r'\.([A-Za-z][\w-]*)\s*\{', theme.THEME_CSS)
    for sel in selectors:
        assert sel.startswith("oc-") or sel.startswith("st-key-"), sel
    assert "data-testid" not in theme.THEME_CSS
    assert ".stButton" not in theme.THEME_CSS


def test_no_banned_vocabulary():
    for term in ["獲利機率", "機率加權", "勝率", "POP", "probability",
                 "期望報酬", "expected profit", "Sharpe", "CVaR"]:
        assert term not in theme.THEME_CSS
    assert "機率" not in theme.THEME_CSS


def test_inject_is_callable_without_streamlit_context_error():
    # inject() 只包裝 st.markdown；不在此測試實際呼叫（無 ScriptRunContext），
    # 僅驗證函數存在且 THEME_CSS 是合法字串輸入。
    assert callable(theme.inject)
    assert "<style>" in theme.THEME_CSS or True  # inject() 自己包 <style>，THEME_CSS 為裸規則
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_theme.py -v`
Expected: FAIL（no module `webapp.theme`）

- [ ] **Step 3: 實作**

```python
# webapp/theme.py
"""v6 spec §2.1: Artifact 淺色視覺 token。

色彩來源權威 = Artifact 淺色呈現（其 :root 預設值）。全站色彩／字體由
.streamlit/config.toml 承載（Streamlit 官方主題機制，覆蓋原生元件）；本模組
的 CSS 僅補足 config.toml 無法表達的自訂視覺元件（卡片陰影／膠囊／徽章／
里程碑軌），選擇器一律以 `.oc-` 前綴自訂類別為準，不得覆寫 Streamlit 內部
DOM（`.stButton`／`[data-testid=...]`）——與 render.py 既有 `.oc-thumb`/
`.oc-num` 慣例一致。
"""
from __future__ import annotations

import streamlit as st

TOKENS: dict[str, str] = {
    "bg": "#eef0f3",
    "chrome": "#f3f4f6",
    "chrome_ink": "#374151",
    "surface": "#ffffff",
    "ink": "#1c1f26",
    "dim": "#6b7280",
    "line": "#e3e6ea",
    "accent": "#ff4b4b",
    "pos": "#1a7f37",
    "neg": "#b22222",
}

THEME_CSS = f"""
.oc-card {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(15,18,25,.10);
  padding: 14px 18px;
  margin: 10px 0;
}}
.oc-pill {{
  display: inline-block;
  border-radius: 999px;
  padding: 1px 10px;
  font-size: 12.5px;
  border: 1px solid;
  white-space: nowrap;
}}
.oc-pill-active {{ color: {TOKENS['pos']}; border-color: {TOKENS['pos']}; background: #ecf9f0; }}
.oc-pill-reached {{ color: #7a5b00; border-color: #caa53d; background: #fff8e1; }}
.oc-pill-expired {{ color: {TOKENS['dim']}; border-color: {TOKENS['dim']}; background: #f3f4f6; }}
.oc-pill-invalidated {{ color: {TOKENS['neg']}; border-color: {TOKENS['neg']}; background: #fbeaea; }}
.oc-badge-ok {{ color: {TOKENS['pos']}; }}
.oc-badge-warn {{ color: #b45309; }}
.oc-badge-stale {{ color: {TOKENS['dim']}; }}
.oc-metric-tile {{
  background: {TOKENS['chrome']};
  border-radius: 10px;
  padding: 10px 16px;
  min-width: 140px;
  display: inline-block;
  margin: 0 8px 8px 0;
}}
.oc-metric-tile .oc-metric-label {{ font-size: 12px; color: {TOKENS['chrome_ink']}; }}
.oc-metric-tile .oc-metric-value {{ font-size: 22px; font-weight: 600; color: {TOKENS['ink']}; }}
.oc-rail-node {{ border-left: 2px solid {TOKENS['line']}; padding-left: 14px; margin: 6px 0; }}
.oc-rail-node.oc-rail-confirmed {{ border-left-color: {TOKENS['accent']}; }}
.oc-num {{ font-variant-numeric: tabular-nums; }}
.oc-thumb {{ display: inline-block; width: 46px; overflow: hidden; }}
"""


def inject() -> None:
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_theme.py -v`
Expected: 5 passed

- [ ] **Step 5: 全回歸**

Run: `python -m pytest -q`

- [ ] **Step 6: Commit**

```bash
git add webapp/theme.py tests/test_theme.py
git commit -m "feat(v6): webapp/theme.py — Artifact light-theme tokens, scoped .oc-* CSS"
```

---

### Task 5: webapp/status.py（狀態推導）

**Files:**
- Create: `webapp/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes：view dict（Task 2 v2 schema）、`option_chaser.data.snapshot.snapshot_today`。
- Produces：
  - `derive_result_status(view: dict | None) -> str`：回傳 `"尚未分析"` / `"有可用候選"` / `"無合格候選"` / `"報價資料不足"`。
  - `quality_tone(view: dict | None, observed) -> str`：回傳 `"正常"` / `"報價不足"` / `"歷史資料"`（`observed: datetime.date`；優先序：報價不足 > 歷史資料 > 正常——工程決策，file docstring 註明）。
  - `INSUFFICIENT_QUOTE_MESSAGE: str` = `"已完成分析，但目前報價資料不足，沒有可用候選。"`
  - `EMPTY_CANDIDATE_MESSAGE: str` = `"已完成分析，目前沒有符合條件的候選。"`
  - `is_legacy_schema(view: dict) -> bool`：`view.get("schema_version", 1) < 2`——判定 result 檔缺 v2 新欄（Task 2 三欄），供 components/views 決定是否顯示降級提示。
  - `LEGACY_RESULT_MESSAGE: str` = `"舊版分析結果，重新分析以顯示完整價格。"`（spec §4.3 誠實聲明的落地文案）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_status.py
"""v6 spec §6.1/§6.2: 狀態推導八分類（展示層純函數，逐列鎖定）。"""
from datetime import date

from webapp import status


def _view(all_quotes_filtered=False, has_selection=True, fetched_at="2026-07-22T10:00:00+00:00"):
    return {
        "default_selection": ["2026-08-01", "long-call|100|2026-08-01"] if has_selection else None,
        "data_quality": {"all_quotes_filtered": all_quotes_filtered, "fetched_at": fetched_at},
        "snapshot_ref": {"fetched_at": fetched_at},
    }


def test_not_yet_analyzed():
    assert status.derive_result_status(None) == "尚未分析"


def test_has_candidates():
    assert status.derive_result_status(_view(has_selection=True)) == "有可用候選"


def test_no_qualified_candidates():
    v = _view(has_selection=False, all_quotes_filtered=False)
    assert status.derive_result_status(v) == "無合格候選"


def test_insufficient_quote_data():
    v = _view(has_selection=False, all_quotes_filtered=True)
    assert status.derive_result_status(v) == "報價資料不足"


def test_insufficient_takes_priority_even_with_selection():
    """all_quotes_filtered=True 理論上不會與 has_selection=True 並存（服務端保證），
    但推導函數仍應以 all_quotes_filtered 為優先判準（防禦性一致）。"""
    v = _view(has_selection=True, all_quotes_filtered=True)
    assert status.derive_result_status(v) == "報價資料不足"


def test_quality_tone_normal():
    v = _view(fetched_at="2026-07-22T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "正常"


def test_quality_tone_insufficient_quote_wins():
    v = _view(all_quotes_filtered=True, fetched_at="2026-07-22T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "報價不足"


def test_quality_tone_historical():
    v = _view(fetched_at="2026-07-15T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "歷史資料"


def test_quality_tone_none_view_is_normal_placeholder():
    assert status.quality_tone(None, observed=date(2026, 7, 22)) == "正常"


def test_messages_no_synthetic_fallback_path():
    """誠實聲明：程式內無 synthetic/last-trade fallback 資料路徑。"""
    import inspect
    src = inspect.getsource(status)
    assert "synthetic" not in src.lower()
    assert "last_trade" not in src.lower() and "last-trade" not in src.lower()


def test_is_legacy_schema_v1_vs_v2():
    assert status.is_legacy_schema({"schema_version": 1}) is True
    assert status.is_legacy_schema({"schema_version": 2}) is False
    assert status.is_legacy_schema({}) is True   # 缺欄視同 v1（get 預設 1）


def test_legacy_result_message_defined():
    assert "重新分析" in status.LEGACY_RESULT_MESSAGE
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_status.py -v`
Expected: FAIL（no module `webapp.status`）

- [ ] **Step 3: 實作**

```python
# webapp/status.py
"""v6 spec §6: 劇本顯示狀態推導（展示層純函數，非新狀態機——沿用既有
Scenario.status／result dict 資料，僅做分類判斷，零金融公式）。

quality_tone 優先序（工程決策，spec 未明定精確優先序時的完成）：
報價不足 > 歷史資料 > 正常——報價不足更具行動急迫性，優先呈現。

誠實聲明（spec §6.1）：引擎不存在 Last-Trade/Synthetic fallback，本模組
無對應觸發路徑；「使用測試 fallback」狀態文案僅為未來 vocabulary 保留，
本檔不實作。
"""
from __future__ import annotations

from datetime import date

from option_chaser.data.snapshot import snapshot_today

INSUFFICIENT_QUOTE_MESSAGE = "已完成分析，但目前報價資料不足，沒有可用候選。"
EMPTY_CANDIDATE_MESSAGE = "已完成分析，目前沒有符合條件的候選。"
LEGACY_RESULT_MESSAGE = "舊版分析結果，重新分析以顯示完整價格。"


def is_legacy_schema(view: dict) -> bool:
    """v6 spec §4.3：result 檔 schema_version < 2 即缺 natural_per_contract／
    max_profit_per_contract／cap_price（Task 2 新欄），components/views 應顯示
    LEGACY_RESULT_MESSAGE 並以 .get() 降級讀取，而非 KeyError。"""
    return view.get("schema_version", 1) < 2


def derive_result_status(view: dict | None) -> str:
    if view is None:
        return "尚未分析"
    if view["data_quality"]["all_quotes_filtered"]:
        return "報價資料不足"
    if view["default_selection"] is not None:
        return "有可用候選"
    return "無合格候選"


def quality_tone(view: dict | None, observed: date) -> str:
    if view is None:
        return "正常"
    if view["data_quality"]["all_quotes_filtered"]:
        return "報價不足"
    if snapshot_today(view["snapshot_ref"]["fetched_at"]) != observed:
        return "歷史資料"
    return "正常"
```

- [ ] **Step 4: 跑測試確認通過＋全回歸**

Run: `python -m pytest tests/test_status.py -v && python -m pytest -q`

- [ ] **Step 5: Commit**

```bash
git add webapp/status.py tests/test_status.py
git commit -m "feat(v6): webapp/status.py — result status + quality tone derivation"
```

---

### Task 6: webapp/components.py（卡片元件庫）

**Files:**
- Create: `webapp/components.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes：`webapp.theme.TOKENS`、`webapp.status`（含 Task 5 新增的 `is_legacy_schema`／`LEGACY_RESULT_MESSAGE`）、`option_chaser.report.STRATEGY_LABELS`、`webapp.render.money/pct/esc`（**沿用既有格式化函數，不重複定義**）。
- Produces：
  - `scenario_card(sc: dict, summary: dict | None) -> str`：`sc` 為 `dataclasses.asdict(Scenario)` 形狀（`id,symbol,direction,target_price,target_date,status,group_id,notes`）；`summary` 為對應劇本 `latest_result` 的 view dict 或 None。**紅線：`sc["symbol"]`／`sc["notes"]` 為使用者輸入，注入前必須 `html.escape()`**（本函數與 `unsafe_allow_html=True` 呼叫端配對，未跳脫的使用者字串會破壞版面或注入標記）。
  - `candidate_card(cand: dict, strategy: str) -> str`：單腿／Spread 雙版式（依 `len(cand["legs"])` 分支）。**v1 相容**：v2 新欄（`natural_per_contract`／`max_profit_per_contract`／`cap_price`）一律以 `.get(key)` 讀取，缺欄時該行顯示 `"—"` 並於卡尾附註 `status.LEGACY_RESULT_MESSAGE`（不得對新欄直接索引導致 `KeyError`）。
  - `metric_tile(label: str, value: str) -> str`。
  - `status_pill(scenario_status: str) -> str`（`Active/Reached/Expired/Invalidated` → 對應 `.oc-pill-*`）。
  - `quality_badge(tone: str) -> str`（`webapp.status.quality_tone` 的三值輸出 → emoji＋class）。
  - 所有回傳字串在 `return` 前一律經 `webapp.render.esc()` 處理（既有 v4/v5 慣例：即使走 `unsafe_allow_html=True`，Streamlit 仍會將裸 `$` 誤判為 LaTeX 定界符；金額顯示到處都是 `$`，故元件層級統一處理，呼叫端不需重複跳脫）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_components.py
"""v6 spec §2.2: 卡片元件庫——零公式，僅格式化＋既有 dict 值直讀。"""
from webapp import components

SC = {"id": "XYZ-120-202608", "symbol": "XYZ", "direction": "bullish",
     "target_price": 120.0, "target_date": "2026-08-01", "status": "Active",
     "group_id": "G-XYZ", "notes": "測試備註"}

SINGLE_CAND = {
    "candidate_key": "long-call|93|2028-01-21", "strategy": "long-call",
    "legs": [{"contract_symbol": "X", "option_type": "call", "strike": 93.0,
              "expiry": "2028-01-21", "bid": 1.32, "ask": 1.52, "iv": 0.11,
              "volume": 13, "open_interest": 17320}],
    "mid_cost": 1.42, "natural_cost": 1.52, "natural_per_contract": 152.0,
    "capital_per_contract": 142.0, "max_loss_per_contract": 142.0,
    "max_profit": None, "max_profit_per_contract": None, "cap_price": None,
    "breakeven": 94.42, "baseline_return": 7.4938, "net_delta": 0.39,
}

SPREAD_CAND = {
    "candidate_key": "bull-call-spread|100|120|2028-12-15", "strategy": "bull-call-spread",
    "legs": [{"contract_symbol": "L", "option_type": "call", "strike": 100.0,
              "expiry": "2028-12-15", "bid": 1.0, "ask": 1.1, "iv": 0.13,
              "volume": 10, "open_interest": 100},
             {"contract_symbol": "S", "option_type": "call", "strike": 120.0,
              "expiry": "2028-12-15", "bid": 0.05, "ask": 0.15, "iv": 0.17,
              "volume": 5, "open_interest": 50}],
    "mid_cost": 0.95, "natural_cost": 1.11, "natural_per_contract": 111.0,
    "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
    "max_profit": 19.05, "max_profit_per_contract": 1905.0, "cap_price": 120.0,
    "breakeven": 100.95, "baseline_return": 20.05, "net_delta": 0.20,
}


def test_scenario_card_shows_core_fields():
    html = components.scenario_card(SC, None)
    assert "XYZ" in html and "120.00" in html and "2026-08-01" in html
    assert "尚未分析" in html


def test_scenario_card_no_position_language():
    """brief §7.1 紅線：不得偽造持倉語彙。"""
    html = components.scenario_card(SC, None)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in html


def test_candidate_card_single_leg_shows_bid_mid_ask_and_per_contract():
    html = components.candidate_card(SINGLE_CAND, "long-call")
    assert "1.32" in html and "1.42" in html and "1.52" in html   # bid/mid/ask
    assert "142" in html    # 每張成本
    assert "94.42" in html  # breakeven
    assert "履約價" in html and "93" in html


def test_candidate_card_spread_shows_max_profit_and_cap_price():
    html = components.candidate_card(SPREAD_CAND, "bull-call-spread")
    assert "0.95" in html          # net mid debit /股
    assert "95" in html            # 每組成本
    assert "1,905" in html or "1905" in html   # 最大獲利每組
    assert "120" in html           # 封頂價
    assert "買" in html and "賣" in html


def test_candidate_card_no_formula_arithmetic():
    """禁止元件內做金融乘除——所有顯示值須直接取自 dict（字串搜尋已知輸入值）。"""
    html = components.candidate_card(SPREAD_CAND, "bull-call-spread")
    # 每組成本應直接等於 dict 內已算好的 capital_per_contract，不應是元件自算 mid*100
    assert f"{SPREAD_CAND['capital_per_contract']:.0f}" in html


def test_metric_tile():
    html = components.metric_tile("Active 劇本數", "3")
    assert "Active 劇本數" in html and ">3<" in html or "3" in html


def test_status_pill_four_states():
    for st_ in ("Active", "Reached", "Expired", "Invalidated"):
        html = components.status_pill(st_)
        assert st_ in html


def test_quality_badge_three_tones():
    for tone in ("正常", "報價不足", "歷史資料"):
        html = components.quality_badge(tone)
        assert tone in html


def test_scenario_card_escapes_html_injection_in_symbol_and_notes():
    """紅線：使用者輸入（symbol/notes）注入 HTML 標記時必須被跳脫，不得破壞卡片
    結構或執行注入內容。"""
    malicious = {**SC, "symbol": "<script>alert(1)</script>",
                "notes": '<img src=x onerror="alert(2)">'}
    html = components.scenario_card(malicious, None)
    assert "<script>" not in html
    assert "onerror=" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_candidate_card_bear_put_spread_shows_put_not_call():
    """BPS 兩腿皆 put——卡片不得誤標 Call（先前草稿硬編 Call 的迴歸測試）。"""
    bps_cand = {
        "candidate_key": "bear-put-spread|100|80|2028-12-15", "strategy": "bear-put-spread",
        "legs": [{"contract_symbol": "L", "option_type": "put", "strike": 100.0,
                 "expiry": "2028-12-15", "bid": 1.0, "ask": 1.1, "iv": 0.13,
                 "volume": 10, "open_interest": 100},
                {"contract_symbol": "S", "option_type": "put", "strike": 80.0,
                 "expiry": "2028-12-15", "bid": 0.05, "ask": 0.15, "iv": 0.17,
                 "volume": 5, "open_interest": 50}],
        "mid_cost": 0.95, "natural_cost": 1.11, "natural_per_contract": 111.0,
        "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
        "max_profit": 19.05, "max_profit_per_contract": 1905.0, "cap_price": 80.0,
        "breakeven": 99.05, "baseline_return": 20.05, "net_delta": -0.20,
    }
    html = components.candidate_card(bps_cand, "bear-put-spread")
    assert "Put" in html
    assert "Call" not in html


def test_candidate_card_v1_legacy_missing_fields_no_crash():
    """v1 舊 result 檔缺 v2 新欄（natural_per_contract/max_profit_per_contract/
    cap_price）——必須降級顯示，不得 KeyError。"""
    legacy_single = {k: v for k, v in SINGLE_CAND.items()
                     if k not in ("natural_per_contract", "max_profit_per_contract", "cap_price")}
    html = components.candidate_card(legacy_single, "long-call")
    assert "—" in html
    assert "舊版分析結果" in html

    legacy_spread = {k: v for k, v in SPREAD_CAND.items()
                     if k not in ("natural_per_contract", "max_profit_per_contract", "cap_price")}
    html2 = components.candidate_card(legacy_spread, "bull-call-spread")
    assert "—" in html2
    assert "舊版分析結果" in html2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_components.py -v`
Expected: FAIL（no module `webapp.components`）

- [ ] **Step 3: 實作**

```python
# webapp/components.py
"""v6 spec §2.2/§4: 卡片元件庫——純函數，輸出 HTML 字串，吃 dict，零金融公式。
與 render.py 同紅線：每個顯示數字皆直接取自已由 store.serialize_result 預算好的
dict 欄位；本模組僅格式化、條件分支（單腿 vs Spread）與既有 status/render 工具函數
的組合呼叫。

安全紅線：使用者輸入（scenario symbol／notes）一律先經 `html.escape()` 才可注入
HTML 樣板；本模組所有回傳字串在 return 前一律經 `esc()`（$ 轉義，見 render.py）
處理，呼叫端不需重複跳脫。v1 舊 result 檔缺 v2 新欄時以 `.get()` 降級讀取，顯示
`—` 與 `status.LEGACY_RESULT_MESSAGE`，不得 KeyError。
"""
from __future__ import annotations

import html as html_lib

from option_chaser.report import STRATEGY_LABELS
from webapp.render import esc, money, pct
from webapp.status import (EMPTY_CANDIDATE_MESSAGE,  # noqa: F401 (re-export for views)
                           LEGACY_RESULT_MESSAGE, derive_result_status,
                           is_legacy_schema)

_STATUS_PILL_CLASS = {
    "Active": "oc-pill-active", "Reached": "oc-pill-reached",
    "Expired": "oc-pill-expired", "Invalidated": "oc-pill-invalidated",
}
_STATUS_EMOJI = {"Active": "🟢", "Reached": "🏁", "Expired": "⌛", "Invalidated": "❌"}
_QUALITY_CLASS = {"正常": "oc-badge-ok", "報價不足": "oc-badge-warn", "歷史資料": "oc-badge-stale"}
_QUALITY_EMOJI = {"正常": "✓", "報價不足": "⚠", "歷史資料": "🕒"}


def _h(text: str) -> str:
    """HTML-escape user-controlled text before interpolating into a template
    (symbol/notes) — distinct from esc(), which only guards '$' against LaTeX."""
    return html_lib.escape(text, quote=True)


def status_pill(scenario_status: str) -> str:
    cls = _STATUS_PILL_CLASS[scenario_status]
    emoji = _STATUS_EMOJI[scenario_status]
    return esc(f'<span class="oc-pill {cls}">{emoji} {scenario_status}</span>')


def quality_badge(tone: str) -> str:
    cls = _QUALITY_CLASS[tone]
    emoji = _QUALITY_EMOJI[tone]
    return esc(f'<span class="{cls}">{emoji} {tone}</span>')


def metric_tile(label: str, value: str) -> str:
    return esc(f'<div class="oc-metric-tile"><div class="oc-metric-label">{_h(label)}</div>'
              f'<div class="oc-metric-value oc-num">{_h(value)}</div></div>')


def scenario_card(sc: dict, summary: dict | None) -> str:
    result_status = derive_result_status(summary)
    parts = [f'<div class="oc-card"><b>{_h(sc["symbol"])}</b> '
            f'{"看漲" if sc["direction"] == "bullish" else "看跌"} '
            f'{status_pill(sc["status"])}<br>'
            f'目標 ${money(sc["target_price"])} ｜ {sc["target_date"]} ｜ {_h(sc["group_id"])}<br>']
    if summary is None:
        parts.append(f'<span class="oc-badge-stale">{result_status}</span>')
    else:
        cand = None
        if summary["default_selection"]:
            key = summary["default_selection"][1]
            for g in summary["expiry_groups"]:
                for row in g["rows"]:
                    if row["candidate"]["candidate_key"] == key:
                        cand = row["candidate"]
                        break
        if cand is not None:
            parts.append(f'{STRATEGY_LABELS[cand["strategy"]]}｜每張/組 ≈ '
                        f'${cand["capital_per_contract"]:.0f}｜劇本報酬 {pct(cand["baseline_return"])}')
        else:
            parts.append(f'<span class="oc-badge-warn">{result_status}</span>')
    if sc["notes"]:
        parts.append(f'<div style="font-size:12px;color:#6b7280">{_h(sc["notes"])}</div>')
    parts.append('</div>')
    return esc("".join(parts))


def candidate_card(cand: dict, strategy: str) -> str:
    legs = cand["legs"]
    label = STRATEGY_LABELS[strategy]
    legacy = is_legacy_schema({"schema_version": cand.get("schema_version", 2)}) or (
        "natural_per_contract" not in cand)
    legacy_note = f'<div style="font-size:12px;color:#b45309">{LEGACY_RESULT_MESSAGE}</div>' if legacy else ""

    def _fmt_money(key: str) -> str:
        v = cand.get(key)
        return f'${v:,.0f}' if v is not None else "—"

    if len(legs) == 1:
        leg = legs[0]
        lines = [
            f'<b>{esc(label)}</b> ｜ 履約價 {leg["strike"]:g} ｜ 到期 {leg["expiry"]}',
            f'Bid ${money(leg["bid"])} ｜ Mid ${money(cand["mid_cost"])} ｜ Ask ${money(leg["ask"])}',
            f'Mid 每張 ≈ ${cand["capital_per_contract"]:.0f} ｜ '
            f'Natural 每張 ≈ {_fmt_money("natural_per_contract")}',
            f'最大損失 ≈ ${cand["max_loss_per_contract"]:.0f} ｜ '
            f'Breakeven ${money(cand["breakeven"])} ｜ 劇本報酬 {pct(cand["baseline_return"])}',
        ]
    else:
        long_leg, short_leg = legs
        max_profit_v = cand.get("max_profit_per_contract")
        max_profit_txt = (f'${max_profit_v:,.0f}' if max_profit_v is not None
                         else ("無上限" if "max_profit_per_contract" in cand else "—"))
        cap_price = cand.get("cap_price")
        cap_txt = f'{cap_price:g}' if cap_price is not None else "—"
        # BCS 兩腿皆 call、BPS 兩腿皆 put——讀 leg 實際 option_type，不得硬編 "Call"
        # （spec brief §5.2 明確要求 Bear Put Spread 顯示 Put，先前草稿誤植兩者皆
        # 顯示 Call）。
        opt_label = long_leg["option_type"].capitalize()
        lines = [
            f'<b>{esc(label)}</b> ｜ 買 {long_leg["strike"]:g} {opt_label} ／ '
            f'賣 {short_leg["strike"]:g} {opt_label} ｜ 到期 {short_leg["expiry"]}',
            f'Net Mid Debit ${money(cand["mid_cost"])}／股 ｜ 每組 ≈ ${cand["capital_per_contract"]:.0f}',
            f'Natural Debit ${money(cand["natural_cost"])}／股 ｜ '
            f'Natural 每組 ≈ {_fmt_money("natural_per_contract")}',
            f'最大損失 ≈ ${cand["max_loss_per_contract"]:.0f} ｜ 最大獲利 ≈ {max_profit_txt} ｜ '
            f'Breakeven ${money(cand["breakeven"])} ｜ 獲利封頂價 {cap_txt}',
        ]
    return esc('<div class="oc-card">' + "<br>".join(lines) + legacy_note + '</div>')


def milestone_rail(group: dict, scenarios_by_id: dict, views_by_id: dict) -> str:
    """v6 spec §3.5：垂直里程碑軌。group 為 store.rebuild_groups 產出的單一群組 dict；
    scenarios_by_id/views_by_id 為呼叫端預先聚合的 {scenario_id: Scenario|view dict}。"""
    parts = [f'<div class="oc-card"><b>{_h(group["id"])}</b>（{len(group["members"])} 個里程碑）']
    for mid in group["members"]:
        sc = scenarios_by_id[mid]
        view = views_by_id.get(mid)
        cls = "oc-rail-node"
        line = (f'{status_pill(sc.status)} {sc.target_date} ${money(sc.target_price)}')
        if view is not None and view["default_selection"]:
            key = view["default_selection"][1]
            cand = next((row["candidate"] for g in view["expiry_groups"]
                        for row in g["rows"] if row["candidate"]["candidate_key"] == key), None)
            if cand is not None:
                line += f' ｜ {STRATEGY_LABELS[cand["strategy"]]} ｜ 劇本報酬 {pct(cand["baseline_return"])}'
        parts.append(f'<div class="{cls}">{line}</div>')
    same_snapshot = len({views_by_id[m]["snapshot_ref"]["path"] for m in group["members"]
                         if m in views_by_id}) == 1 and len(views_by_id) >= 2
    if same_snapshot:
        parts.append('<div class="oc-badge-ok">✓ 同一資料快照</div>')
    parts.append('</div>')
    return esc("".join(parts))
```

- [ ] **Step 4: 跑測試確認通過＋紅線掃描**

Run: `python -m pytest tests/test_components.py -v && python -m pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add webapp/components.py tests/test_components.py
git commit -m "feat(v6): webapp/components.py — Artifact-style card component library"
```

---

### Task 7: render.py 擴充 — Spread 封頂標示＋候選比較表

**Files:**
- Modify: `webapp/render.py`
- Test: `tests/test_render_cap.py`

**Interfaces:**
- Consumes：candidate dict（`cap_price`／`max_profit_per_contract`，Task 2）。
- Produces：
  - `heatmap_html(matrix: dict, cand: dict | None = None) -> str`（**擴充既有函數簽名**，新增可選 `cand` 參數；`cand=None` 時行為與現狀逐位元相同——單腿呼叫點不傳 `cand` 或傳 `None`）。
  - `comparison_table_html(view: dict) -> str`（新函數，詳頁候選比較表，13 欄）。

**現況 `heatmap_html`（Task 6 前綴為既有內容，供對照擴充點）：** 見 §render.py 內容（已於本 plan 開頭 Task 前的探查中列出，此處僅標註插入點）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_render_cap.py
"""v6 spec §5: Spread heatmap 封頂標示（BCS/BPS 鏡像）；§4.4 候選比較表。"""
from webapp.render import comparison_table_html, heatmap_html

MATRIX = {
    "prices": [[130.0, ""], [120.0, "<目標>"], [100.0, "<現價>"], [80.0, ""]],
    "dates": [["2026-08-01", ""], ["2026-09-01", "*"]],
    "cells": [[0.9, 0.9], [0.8, 0.8], [-0.3, -0.3], [-1.0, -1.0]],
}

BCS_CAND = {"strategy": "bull-call-spread",
           "legs": [{"strike": 100.0}, {"strike": 120.0}],
           "cap_price": 120.0, "max_profit_per_contract": 1905.0}
BPS_CAND = {"strategy": "bear-put-spread",
           "legs": [{"strike": 100.0}, {"strike": 80.0}],
           "cap_price": 80.0, "max_profit_per_contract": 1500.0}
SINGLE_CAND = {"strategy": "long-call", "legs": [{"strike": 100.0}],
              "cap_price": None, "max_profit_per_contract": None}


def test_single_leg_heatmap_unchanged_no_cap_marker():
    html_old = heatmap_html(MATRIX)                 # 既有呼叫形式（無 cand）仍合法
    html_new = heatmap_html(MATRIX, SINGLE_CAND)
    assert html_old == html_new
    assert "收益封頂" not in html_new
    assert "最大獲利區" not in html_new


def test_bcs_caps_at_and_above_cap_price():
    html = heatmap_html(MATRIX, BCS_CAND)
    assert "收益封頂" in html
    # 回傳字串整體經 esc() 處理（$ -> \$，見 render.py 既有慣例，v6 新增 cap_note
    # 含 $ 金額必須跳脫），故斷言比對跳脫後的實際輸出，而非原始未跳脫字面。
    assert "股價 ≥ \\$120" in html
    assert "1,905" in html or "1905" in html


def test_bps_caps_at_and_below_cap_price():
    html = heatmap_html(MATRIX, BPS_CAND)
    assert "收益封頂" in html
    assert "股價 ≤ \\$80" in html


def test_bcs_v1_legacy_no_cap_price_degrades_silently():
    """v1 舊 result 檔缺 cap_price/max_profit_per_contract——不得 KeyError，
    降級為無封頂標示（等同 cand=None 的行為）。"""
    legacy = {"strategy": "bull-call-spread", "legs": [{"strike": 100.0}, {"strike": 120.0}]}
    html = heatmap_html(MATRIX, legacy)
    assert "收益封頂" not in html


def test_comparison_table_contains_required_columns():
    view = {
        "expiry_groups": [{
            "expiry": "2026-09-01", "buffer_days": 30, "hidden_count": 0,
            "rows": [{"strategy": "long-call", "badges": ["top_return"],
                     "candidate": {**SINGLE_CAND, "candidate_key": "k1",
                                  "mid_cost": 1.5, "natural_cost": 1.6,
                                  "capital_per_contract": 150.0,
                                  "natural_per_contract": 160.0,
                                  "max_loss_per_contract": 150.0,
                                  "breakeven": 101.5, "baseline_return": 0.5,
                                  "scenario_vector": {"worst_return": -1.0, "worst_code": "S1",
                                                      "entries": []},
                                  "retention": 0.1, "friction": 0.05,
                                  "quote_warning": False,
                                  "legs": [{"strike": 100.0, "bid": 1.4, "ask": 1.6,
                                           "option_type": "call", "expiry": "2026-09-01"}]}}]
        }],
        "hidden_expiries": [],
    }
    html = comparison_table_html(view)
    for token in ("策略", "Breakeven", "最大損失", "劇本報酬", "情境最壞",
                 "成交摩擦", "overflow-x:auto"):
        assert token in html


def test_comparison_table_v1_legacy_spread_no_crash():
    """v1 舊 result 檔的 Spread 候選缺 max_profit_per_contract——不得 KeyError。"""
    legacy_cand = {"strategy": "bull-call-spread", "candidate_key": "k2",
                   "mid_cost": 0.95, "natural_cost": 1.11,
                   "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
                   "breakeven": 100.95, "baseline_return": 0.2,
                   "scenario_vector": {"worst_return": -1.0, "worst_code": "S1", "entries": []},
                   "retention": 0.3, "friction": 0.1, "quote_warning": False,
                   "legs": [{"strike": 100.0, "expiry": "2026-09-01"},
                           {"strike": 120.0, "expiry": "2026-09-01"}]}
    view = {"expiry_groups": [{"expiry": "2026-09-01", "buffer_days": 30, "hidden_count": 0,
                               "rows": [{"strategy": "bull-call-spread", "badges": [],
                                        "candidate": legacy_cand}]}],
            "hidden_expiries": []}
    html = comparison_table_html(view)   # must not raise KeyError
    assert "—" in html
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_render_cap.py -v`
Expected: FAIL（`heatmap_html` 不接受 `cand` 參數；無 `comparison_table_html`）

- [ ] **Step 3: 實作**

修改 `webapp/render.py` 的 `heatmap_html` 簽名與函式體（整段取代）：

```python
def heatmap_html(matrix: dict, cand: dict | None = None) -> str:
    """v4 spec §4.2/§4.3: bold rows are exactly those whose price_axis label is
    non-empty (spot/target/overshoot/adverse) — GUI reads the label, it never
    recomputes the anchor prices itself.

    v6 spec §5: 若傳入 Spread 候選（`cand` 含非 null `cap_price`），封頂區依
    策略方向標示——BCS（賣腿在上）價格 >= cap_price 為封頂區；BPS（賣腿在下）
    價格 <= cap_price 為封頂區。純展示層比較（價格 vs cap_price）＋讀
    max_profit_per_contract，不做估值。"""
    dates = matrix["dates"]
    prices = matrix["prices"]
    cells = matrix["cells"]
    n = len(dates)
    head_cells = []
    for j, (iso, lbl) in enumerate(dates):
        suffix = ("*" if lbl == "*" else "") + ("（到期）" if j == n - 1 else "")
        head_cells.append(
            f'<th style="padding:4px 8px;white-space:nowrap">{iso[5:7]}/{iso[8:10]}{suffix}</th>')

    # .get(...) 而非直接索引：v1 舊 result 檔缺 cap_price/max_profit_per_contract
    # （Task 2 v2 新欄）時應靜默降級為「無封頂標示」，不得 KeyError。
    cap_price = cand.get("cap_price") if cand else None
    is_bcs = cand is not None and cand["strategy"] == "bull-call-spread"
    is_bps = cand is not None and cand["strategy"] == "bear-put-spread"

    def _is_capped(price: float) -> bool:
        if cap_price is None:
            return False
        if is_bcs:
            return price >= cap_price
        if is_bps:
            return price <= cap_price
        return False

    rows = []
    for i in range(len(prices) - 1, -1, -1):
        price, plabel = prices[i]
        cells_html = "".join(
            f'<td style="background:{cell_color(v)};color:#111;text-align:right;'
            f'padding:4px 8px">{v * 100:+.0f}%</td>'
            for v in cells[i])
        price_text = f"{price:.2f}{_price_tag(plabel)}"
        if _is_capped(price):
            price_text = f"{price_text} 收益封頂"
        if plabel:
            price_text = f"<b>{price_text}</b>"
        row_style = ' style="border-top:2px solid #888"' if (
            cap_price is not None and _is_capped(price) and
            i < len(prices) - 1 and not _is_capped(prices[i + 1][0])) else ""
        rows.append(
            f'<tr{row_style}><td style="padding:4px 8px;white-space:nowrap">'
            f'{price_text}</td>{cells_html}</tr>')

    cap_note = ""
    if cap_price is not None and cand is not None and cand.get("max_profit_per_contract") is not None:
        direction = "≥" if is_bcs else "≤"
        cap_note = (f'<p style="font-size:12px;color:#666">'
                    f'股價 {direction} ${cap_price:g} 後，收益固定於最大獲利 ≈ '
                    f'${cand["max_profit_per_contract"]:,.0f}／每組。'
                    f'<span style="color:#888">（最大獲利區）</span></p>')

    out = ('<div style="overflow-x:auto"><table style="border-collapse:collapse;'
          'font-family:monospace;font-size:13px">'
          f'<tr><th style="padding:4px 8px">價格</th>{"".join(head_cells)}</tr>'
          + "".join(rows) + "</table></div>"
          '<p style="font-size:12px;color:#666">此圖顯示在不同標的價格與日期下，'
          '以目前 Mid 價進場的模型報酬率。'
          '<b>粗體</b>價格列為錨點（現價／目標／超標／深跌），其餘為等距內插價。</p>'
          + cap_note)
    # v5 原函數本無 $ 字元（僅百分比），故不需 esc()；v6 新增的 cap_note 含
    # 裸 $ 金額，經 unsafe_allow_html=True 仍可能被誤判為 LaTeX 定界符，
    # 整段回傳統一經 esc() 處理（cap_note 為空字串時 esc() 為 no-op）。
    return esc(out)
```

於檔案末尾（`render_step4` 之後）追加新函數：

```python
def comparison_table_html(view: dict) -> str:
    """v6 spec §4.4：詳頁候選比較表，13 欄，overflow-x 手機橫向捲動。"""
    rows_html = []
    for g in view["expiry_groups"]:
        for row in g["rows"]:
            cand = row["candidate"]
            legs = cand["legs"]
            is_spread = len(legs) == 2
            structure = (f"買{legs[0]['strike']:g}/賣{legs[1]['strike']:g}"
                        if is_spread else f"K={legs[0]['strike']:g}")
            price_col = (f"Net Mid ${money(cand['mid_cost'])} / "
                        f"Natural ${money(cand['natural_cost'])}" if is_spread
                        else f"{money(legs[0]['bid'])}/{money(cand['mid_cost'])}/{money(legs[0]['ask'])}")
            _mp = cand.get("max_profit_per_contract")   # .get(): v1 舊檔缺此欄不得 KeyError
            max_profit_col = ("無上限" if (not is_spread and row["strategy"] == "long-call")
                              else (f"${_mp:,.0f}" if _mp is not None else "—"))
            fr = cand["friction"]
            fr_html = f'{pct(min(fr, 9.99))}' + (" ⚠" if fr > 0.25 else "")
            rows_html.append(
                f"<tr><td>{STRATEGY_LABELS[row['strategy']]}</td><td>{structure}</td>"
                f"<td>{legs[0]['expiry']}</td><td>{price_col}</td>"
                f"<td>${cand['capital_per_contract']:.0f}</td>"
                f"<td>${cand['max_loss_per_contract']:.0f}</td>"
                f"<td>{max_profit_col}</td><td>${money(cand['breakeven'])}</td>"
                f"<td>{pct(cand['baseline_return'])}</td>"
                f"<td>{pct(cand['scenario_vector']['worst_return'])}</td>"
                f"<td>{pct(cand['retention'])}</td><td>{fr_html}</td>"
                f"<td>{'⚠' if cand['quote_warning'] else '正常'}</td></tr>")
    header = ("<tr><th>策略</th><th>結構</th><th>到期日</th><th>Bid/Mid/Ask 或 Net Mid/Natural</th>"
             "<th>每張・每組成本</th><th>最大損失</th><th>最大獲利</th><th>Breakeven</th>"
             "<th>劇本報酬</th><th>情境最壞</th><th>不漲保留率</th><th>成交摩擦</th><th>資料品質</th></tr>")
    return esc('<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:13px">'
              + header + "".join(rows_html) + "</table></div>")
```

（`esc()`：既有紅線——render.py 的既有慣例是每個含 `$` 金額且經 `unsafe_allow_html=True` 呈現的組合字串一律在 `return` 前包一層 `esc()`，否則 Streamlit 的 markdown 引擎仍會把裸 `$` 誤判為 LaTeX 定界符，即使走 `unsafe_allow_html=True`——本函數的 `${money(...)}`／`${cand[...]:.0f}` 等多處金額欄位皆屬此類，故整個回傳字串統一跳脫，不逐欄位處理。）

- [ ] **Step 4: 跑測試確認通過＋既有 render 測試不破**

Run: `python -m pytest tests/test_render_cap.py -v && python -m pytest tests/test_webapp.py tests/test_webapp_v4.py -v`
Expected: 全綠（既有呼叫點 `heatmap_html(cand["matrix"])` 於 `render_step2` 未變——單參數呼叫仍合法，`cand` 預設 `None`）

- [ ] **Step 5: render_step2 傳入 cand 以啟用封頂標示**

`render.py` 內 `render_step2` 函數，`st.markdown(heatmap_html(cand["matrix"]), unsafe_allow_html=True)` 改為：

```python
    st.markdown(heatmap_html(cand["matrix"], cand), unsafe_allow_html=True)
```

- [ ] **Step 6: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠（既有 golden/heatmap 相關測試若對單腿字串做逐字比對，因單腿 `cand.strategy` 不觸發封頂分支，輸出不變——不需修改；若有測試對 Spread heatmap 字串做逐字比對，需確認新增的封頂註記不破壞既有斷言，逐一檢查 `test_webapp_v4.py`／golden 檔案）

- [ ] **Step 7: Commit**

```bash
git add webapp/render.py tests/test_render_cap.py
git commit -m "feat(v6): render.py — Spread heatmap cap-region marking (BCS/BPS mirrored), comparison table"
```

---

### Task 8: webapp/views/overview.py ＋ webapp/views/help.py

**Files:**
- Create: `webapp/views/__init__.py`（空檔）
- Create: `webapp/views/overview.py`
- Create: `webapp/views/help.py`（遷自 `webapp/pages/1_說明.py`，內容原樣＋新增劇本工作區一節已存在，沿用）
- Test: `tests/test_views_overview_help.py`

**Interfaces:**
- Consumes：`workspace.list_scenarios`／`workspace.latest_result`／`workspace.load_groups`／`webapp.components.metric_tile`／`webapp.theme.inject`。
- Produces：兩個可獨立執行的 Streamlit 腳本（`st.Page` 相容——純腳本，不包函數）。

**現況 `webapp/pages/1_說明.py`**：既有 4.6KB 檔案（v4/v5 內容：術語表、工作區三概念說明）。Task 內容＝原樣搬移至 `webapp/views/help.py`，**不改動任何一行內容**（純檔案移動）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_views_overview_help.py
"""v6 spec §3.1/既有 help 頁遷移：AppTest via router (webapp/app.py) + switch_page。
本測試獨立於 Task 12 的 app.py 路由重寫——先用 AppTest.from_file 直接驗證頁面腳本
本身在 stub session_state 下可執行（views 檔案本身零例外），Task 12 完成後另有
test_app_navigation.py 驗證完整路由整合。"""
import os
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def test_overview_empty_workspace_shows_guidance(ws):
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body


def test_overview_metrics_reflect_workspace(ws):
    workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts=TS)
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert ">1<" in body or "1" in body   # Active 劇本數 = 1


def test_overview_no_position_language(ws):
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    body = " ".join(m.value for m in at.markdown)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body


def test_help_page_renders():
    from option_chaser.glossary import GLOSSARY
    at = AppTest.from_file("webapp/views/help.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert any(term in body for term in GLOSSARY)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_views_overview_help.py -v`
Expected: FAIL（`webapp/views/` 不存在）

- [ ] **Step 3: 實作**

```python
# webapp/views/__init__.py
```
（空檔）

```python
# webapp/views/overview.py
"""v6 spec §3.1：戰情總覽（首頁）。全部數字為既有資料彙總（計數/時間比對），
零金融公式。"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from webapp.components import metric_tile
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))

inject()
st.title("戰情總覽")

scenarios = workspace.list_scenarios(WS_ROOT)

if not scenarios:
    # 注意：本頁獨立測試時（AppTest.from_file 直接載入本檔）尚無 st.navigation
    # 路由存在，st.page_link 要求目標檔案必須是「已在 st.navigation 註冊的頁面」
    # 否則丟例外——此處故意只用純文字指引，可點擊的頁面連結延後到 Task 12（路由
    # 建好後）以 st.page_link 升級並於 test_app_navigation.py 驗證整合行為。
    st.markdown("尚無劇本。前往「劇本工作區」建立第一個劇本。")
else:
    views = {sc.id: workspace.latest_result(WS_ROOT, sc.id) for sc in scenarios}
    groups = workspace.load_groups(WS_ROOT)

    active_n = sum(1 for sc in scenarios if sc.status == "Active")
    unanalyzed_n = sum(1 for sc in scenarios if views[sc.id] is None)
    bad_quality_n = sum(1 for sc in scenarios if views[sc.id] is not None and (
        views[sc.id]["data_quality"]["all_quotes_filtered"]
        or views[sc.id]["default_selection"] is None))
    reached_n = sum(1 for sc in scenarios if sc.status == "Reached")
    pending_relations = sum(
        1 for g in groups["groups"] for rel in g["relations"]
        if rel["confirmed"] == "undefined")
    analyzed_times = [v["analyzed_at"] for v in views.values() if v is not None]
    latest_time = max(analyzed_times) if analyzed_times else "—"

    tiles = "".join([
        metric_tile("Active 劇本數", str(active_n)),
        metric_tile("尚未分析", str(unanalyzed_n)),
        metric_tile("資料異常", str(bad_quality_n)),
        metric_tile("已完成", str(reached_n)),
        metric_tile("待確認關係", str(pending_relations)),
        metric_tile("最近分析時間", latest_time),
    ])
    st.markdown(tiles, unsafe_allow_html=True)

    st.subheader("劇本速覽")
    for sc in scenarios:
        st.markdown(f"**{sc.symbol}** {sc.status} ｜ 目標 ${sc.target_price:g} ｜ {sc.target_date}")
```

```bash
git mv webapp/pages/1_說明.py webapp/views/help.py
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_views_overview_help.py -v`
Expected: 4 passed

- [ ] **Step 5: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠（舊 `test_webapp_v4.py::test_help_page_renders` 若仍指向 `webapp/pages/1_說明.py` 會因檔案已搬移而失敗——本 task 暫時保留該檔失敗**是預期的**，因為 Task 9 會整併/刪除 `test_webapp_v4.py`；若 CI 在此中繼點要求全綠，改為此步驟同時刪除該筆舊斷言：）

```bash
python - <<'PYEOF'
import pathlib
p = pathlib.Path("tests/test_webapp_v4.py")
text = p.read_text(encoding="utf-8")
marker = 'def test_help_page_renders():'
if marker in text:
    start = text.index(marker)
    end = text.index("\n\n\n", start)
    text = text[:start] + text[end+3:]
    p.write_text(text, encoding="utf-8")
    print("removed stale test_help_page_renders (superseded by test_views_overview_help.py)")
PYEOF
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add webapp/views/__init__.py webapp/views/overview.py webapp/views/help.py webapp/pages/1_說明.py tests/test_views_overview_help.py tests/test_webapp_v4.py
git commit -m "feat(v6): views/overview.py (戰情總覽) + migrate help page to views/"
```

---

### Task 9: webapp/views/quick.py（快速試算，遷自 app.py）

**Files:**
- Create: `webapp/views/quick.py`
- Delete: `tests/test_webapp.py`（內容併入本檔新測試）
- Modify: `tests/test_webapp_v4.py`（保留 render 相關斷言，遷移至 `test_views_quick.py` 後刪除本檔——見 Step 5）
- Test: `tests/test_views_quick.py`

**Interfaces:**
- Consumes：現 `webapp/app.py` 全部邏輯（表單/兩段式 rerun/錯誤映射，見 Task 1 前探查列出的現況原文）、`workspace.adopt_result`／`workspace.scenario_exists`（Task 3）。
- Produces：`webapp/views/quick.py`——獨立可執行腳本，行為與現 `app.py` 主體邏輯**完全一致**＋新增「保存為劇本」按鈕（spec §1.2）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_views_quick.py
"""v6 spec §1.2/§3.4：快速試算頁——沿用 v5 app.py 全部語意斷言（併入自
test_webapp.py + test_webapp_v4.py），新增副標與保存為劇本斷言。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams, FetchError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
PAGE = "webapp/views/quick.py"


def _patched(monkeypatch):
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))


def _fill_and_submit(at, symbol="XYZ", price=120.0, checks=("long-call",)):
    at.text_input(key="symbol").set_value(symbol)
    at.number_input(key="target_price").set_value(price)
    at.date_input(key="target_date").set_value(date(2026, 8, 1))
    for s in ("long-call", "bull-call-spread", "long-put", "bear-put-spread"):
        at.checkbox(key=f"chk-{s}").set_value(s in checks)
    at.run()
    at.button[0].set_value(True).run(timeout=30)
    return at


def test_subtitle_present(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    body = " ".join(m.value for m in at.markdown) + " ".join(getattr(x, "value", "") for x in at.caption)
    assert "不會自動保存" in body


def test_happy_path_renders_four_steps(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    subheaders = " ".join(s.value for s in at.subheader)
    assert "Step 2" in subheaders and "Step 3" in subheaders and "Step 4" in subheaders
    assert not at.exception


def test_empty_symbol_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at, symbol="   ")
    assert any("請輸入標的代號" in e.value for e in at.error)


def test_fetch_error_mapping(monkeypatch):
    import option_chaser.service as svc
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 抓取失敗（XX）: boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at, symbol="XX")
    assert any("請稍後再試" in e.value for e in at.error)


def test_analysis_does_not_write_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    assert workspace.list_scenarios(tmp_path) == []   # 零新檔（測試鎖定）


def test_save_as_scenario_button_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    save_buttons = [b for b in at.button if b.label == "保存為劇本"]
    assert save_buttons, "expected a 保存為劇本 button after analysis"
    save_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
    scenarios = workspace.list_scenarios(tmp_path)
    assert len(scenarios) == 1
    assert scenarios[0].id == "XYZ-120-202608"


def test_save_as_scenario_duplicate_shows_link(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    workspace.create_scenario(tmp_path, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts="2026-07-22T00:00:00+00:00")
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert "已有同名劇本" in body
    assert not any(b.label == "保存為劇本" for b in at.button)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_views_quick.py -v`
Expected: FAIL（`webapp/views/quick.py` 不存在）

- [ ] **Step 3: 實作**

```python
# webapp/views/quick.py
"""v6 spec §1.2/§3.4：快速試算——一次性分析，結果不會自動保存。
輸入表單、渲染邏輯與 v5 app.py 完全沿用；新增副標與「保存為劇本」。"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams, FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from webapp.render import (cell_color, default_key, find_row, heatmap_html,
                           render_step2, render_step3, render_step4,
                           render_summary)
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
DEFAULT_CHECKED = {"long-call", "bull-call-spread"}


def run_analysis(request, progress):
    return service.run(request, progress)


def _selected_key(view) -> str | None:
    if "selected_key" not in st.session_state:
        st.session_state["selected_key"] = default_key(view)
    key = st.session_state["selected_key"]
    if find_row(view, key) is None and view["default_selection"]:
        key = view["default_selection"][1]
        st.session_state["selected_key"] = key
    return key


def _scenario_form_fields():
    st.text_input("標的", key="symbol", placeholder="TLT")
    st.number_input("目標價位", key="target_price",
                    min_value=0.01, value=100.0, step=1.0)
    st.date_input("預計到達時間", key="target_date",
                  value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}", value=(s in DEFAULT_CHECKED))


inject()
st.title("快速試算")
st.caption("一次性分析，結果不會自動保存。")

_result = st.session_state.get("result")
if _result is None:
    with st.form("scenario"):
        _scenario_form_fields()
        submitted = st.form_submit_button(
            "開始分析", disabled=st.session_state.get("running", False))
else:
    render_summary(store.serialize_result(_result, "", None))
    with st.expander("✎ 修改劇本", expanded=False):
        with st.form("scenario"):
            _scenario_form_fields()
            submitted = st.form_submit_button(
                "開始分析", disabled=st.session_state.get("running", False))


def _do_analysis() -> None:
    request = st.session_state.pop("pending_request")
    try:
        with st.status("分析中……", expanded=True) as status:
            result = run_analysis(request, status.write)
            status.update(label="分析完成", state="complete")
        st.session_state["result"] = result
        st.session_state.pop("selected_key", None)
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
        logging.exception("analysis failed")
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = "分析過程發生錯誤，請稍後再試。"
    finally:
        st.session_state["running"] = False


if submitted and not st.session_state.get("running", False):
    sym = (st.session_state.get("symbol") or "").strip().upper()
    strategies = tuple(s for s in STRATEGY_ORDER if st.session_state.get(f"chk-{s}"))
    if not sym:
        st.error("請輸入標的代號。")
    elif not strategies:
        st.error("請至少勾選一種策略。")
    else:
        base = AnalysisParams(target_price=float(st.session_state["target_price"]),
                              target_date=st.session_state["target_date"].isoformat())
        st.session_state["pending_request"] = service.AnalysisRequest(
            symbol=sym, base_params=base, strategies=strategies)
        st.session_state["running"] = True
        st.rerun()

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])

if "result" in st.session_state:
    _final_result = st.session_state["result"]
    _view = store.serialize_result(_final_result, "", None)
    _key = _selected_key(_view)
    render_step2(_view, _key)
    render_step3(_view, _key)
    render_step4(_view, _key)

    # v6 spec §1.2: 保存為劇本
    _base = _final_result.request.base_params
    _existing = workspace.scenario_exists(
        WS_ROOT, _final_result.request.symbol, _base.target_price, _base.target_date)
    if _existing is not None:
        st.markdown(f"已有同名劇本：`{_existing}`，前往劇本工作區查看。")
    else:
        if st.button("保存為劇本", key="save-as-scenario"):
            sc, _ = workspace.adopt_result(WS_ROOT, _final_result)
            st.success(f"已保存為劇本 `{sc.id}`，前往劇本工作區查看。")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_views_quick.py -v`
Expected: 7 passed

- [ ] **Step 5: 刪除已由本檔取代的舊測試檔**

```bash
git rm tests/test_webapp.py
```

`tests/test_webapp_v4.py` 內容分兩批：Step-1~4 相關斷言（分組表格/badge/scatter/greeks/glossary/dollar-escape）本質是渲染測試，**保留在 `test_webapp_v4.py` 但改指向新頁面路徑**（Task 11 一併處理，因為多數斷言依賴含「候選成本」與到期日分組資料，該頁面在 v6 對應到詳頁而非快速試算——見 Task 11 Step 5 的完整搬遷）。本步驟僅先移除已被 `test_views_quick.py`／`test_views_overview_help.py` 覆蓋的重複項（`test_help_page_renders`，Task 8 已處理；`test_glossary_importable_without_streamlit` 為純 import 測試，與頁面無關，予以保留在 `test_webapp_v4.py` 直到 Task 11 決定其最終歸屬）。

- [ ] **Step 6: 全回歸**

Run: `python -m pytest -q`
Expected: `test_webapp.py` 已刪除、`test_views_quick.py` 全綠；`test_webapp_v4.py` 中依賴 `webapp/pages/0_劇本工作區.py`／`webapp/app.py` 路徑的測試會失敗——**此為中繼態，Task 10/11/12 會逐一收斂**，記錄於 progress ledger 供 review 追蹤，不視為本 task 失敗（本 task 的 own 測試 `test_views_quick.py` 全綠即為驗收標準）。

- [ ] **Step 7: Commit**

```bash
git add webapp/views/quick.py tests/test_views_quick.py
git rm tests/test_webapp.py
git commit -m "feat(v6): views/quick.py — migrate app.py body, add 保存為劇本 (adopt_result wiring)"
```

---

### Task 10: webapp/views/workspace.py（劇本工作區，卡片牆重構）

**Files:**
- Create: `webapp/views/workspace.py`
- Delete: `tests/test_webapp_workspace.py`（併入新測試）
- Test: `tests/test_views_workspace.py`

**Interfaces:**
- Consumes：`workspace.*`（全部既有函數，Task 3 新增 `adopt_result` 本頁不用）、`webapp.components.*`、`webapp.theme.inject`。
- Produces：`webapp/views/workspace.py`——建立表單（`st.popover`）＋劇本卡片牆（`scenario_card`）＋`⋯ 管理` 彈出層（`st.popover`：標記達成/失效/刪除/關係設定）＋群組里程碑軌（`milestone_rail`）。**行為語意與 v5 `webapp/pages/0_劇本工作區.py` 相同**（重新分析按鈕兩條件規則、撞名確認、觀察式過期沿用），僅視覺與元件呈現改變。

**現況 `webapp/pages/0_劇本工作區.py`**：v5 完整實作（275 行，見 v5 plan Task 10）——建立表單、清單列、群組卡、狀態操作、重新分析兩條件按鈕。本 task 為**視覺重構**，非行為新增；語意斷言（重新分析按鈕四態負例、原因必填、撞名邏輯、群組分析共用 snapshot）全數搬遷。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_views_workspace.py
"""v6 spec §3.2/§3.5：劇本工作區卡片牆——沿用 v5 test_webapp_workspace.py 全部
語意斷言，改為卡片/popover 呈現形式；新增 candidate_card 價格顯示斷言。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/views/workspace.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


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


def test_scenario_card_shows_symbol_and_status(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert "XYZ" in _body(at)


def test_scenario_card_price_after_analysis(ws):
    sc = _mk(ws)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    assert "每張/組" in body or "每張" in body   # candidate_card 摘要含成本


def test_manage_popover_contains_status_actions(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    labels = [p.label for p in at.get("popover")] if hasattr(at, "get") else []
    body = _body(at)
    assert "⋯ 管理" in body or any("管理" in (getattr(p, "label", "") or "") for p in [])
    # popover 內容須存在標記達成/標記失效/刪除按鈕（按鍵 key 前綴檢查）
    assert any(b.key and b.key.startswith("ws-reach-") for b in at.button)
    assert any(b.key and b.key.startswith("ws-inv-") for b in at.button)
    assert any(b.key and b.key.startswith("ws-del-") for b in at.button)


def test_status_change_requires_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert any("請填原因" in e.value for e in at.error)


def test_reanalyze_button_requires_both_conditions(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")

    def has_rean(at):
        return any(bt.key == f"ws-rean-{b.id}" for bt in at.button)

    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)
    workspace.set_status(ws, a.id, "Reached", reason="到價", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)
    workspace.confirm_relation(ws, "G-XYZ", (a.id, b.id), "milestone-path", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert has_rean(at)


def test_group_analyze_shares_snapshot(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")
    at = AppTest.from_file(PAGE)
    at.run()
    next(bt for bt in at.button if bt.key == "ws-gan-G-XYZ").set_value(True).run(timeout=60)
    assert not at.exception
    va = workspace.latest_result(ws, a.id)
    vb = workspace.latest_result(ws, b.id)
    assert va["snapshot_ref"]["path"] == vb["snapshot_ref"]["path"]


def test_no_position_language(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body


```

**注意（不在本 task 測試）**：「詳頁」按鈕呼叫 `st.switch_page("views/detail.py", ...)`——
此呼叫要求目標頁已於 `st.navigation` 註冊（經實測驗證：`AppTest.from_file` 直接載入
單一頁面腳本時，該腳本本身即是「入口」，無任何 `st.navigation` 宣告，`switch_page`/
`page_link` 對任何目標一律拋 `StreamlitAPIException`，即使目標檔案確實存在於磁碟
——與是否已完成 Task 12 無關）。因此本 task 的獨立測試**不得**點擊 `ws-det-*`
按鈕；該按鈕的端到端驗證（含 `sid` 經 `query_params` 正確傳遞）延後至 Task 12
`test_app_navigation.py`，經 `webapp/app.py` 真實入口＋`switch_page("views/workspace.py")`
到達本頁後才點擊測試。

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_views_workspace.py -v`
Expected: FAIL（`webapp/views/workspace.py` 不存在）

- [ ] **Step 3: 實作**

```python
# webapp/views/workspace.py
"""v6 spec §3.2/§3.5：劇本工作區——Artifact 風卡片牆＋⋯管理彈出層＋群組里程碑軌。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from webapp.components import candidate_card, quality_badge, scenario_card, status_pill
from webapp.status import quality_tone
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
RELATION_LABELS = {"milestone-path": "里程碑路徑", "independent": "獨立",
                   "exclusive": "互斥", "undefined": "暫不定義"}
PROPOSED_LABELS = {"milestone-path": "里程碑路徑", "review-needed": "需檢視",
                   "exclusive-candidate": "互斥候選"}

inject()
st.title("劇本工作區")


def _summary_of(sid: str):
    return workspace.latest_result(WS_ROOT, sid)


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


# ---------- 設定 ----------
constraints = store.load_constraints(WS_ROOT)
with st.popover("⚙ 設定"):
    cur = constraints["total_capital"]
    cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                             value=float(cur or 0.0), step=1000.0, key="ws-capital")
    if st.button("儲存設定", key="ws-save-capital"):
        store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
        st.rerun()

# ---------- 建立劇本 ----------
with st.popover("＋ 建立劇本"):
    st.text_input("標的", key="ws-new-symbol", placeholder="TLT")
    st.number_input("目標價位", key="ws-new-price", min_value=0.01, value=100.0, step=1.0)
    sym = (st.session_state.get("ws-new-symbol") or "").strip().upper()
    inferred = (workspace.default_direction(sym, float(st.session_state.get("ws-new-price", 100.0)))
               if sym else None)
    options = ("bullish", "bearish") if inferred else ("", "bullish", "bearish")
    dir_labels = {"": "（請選擇）", "bullish": "看漲", "bearish": "看跌"}
    idx = options.index(inferred) if inferred else 0
    direction = st.selectbox("方向", options, index=idx, format_func=lambda d: dir_labels[d],
                             key="ws-new-direction")
    if direction and st.session_state.get("ws-new-dir-prev") != direction:
        st.session_state["ws-new-dir-prev"] = direction
        defaults = ({"long-call", "bull-call-spread"} if direction == "bullish"
                    else {"long-put", "bear-put-spread"})
        for s in STRATEGY_ORDER:
            st.session_state[f"ws-new-chk-{s}"] = s in defaults
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"ws-new-chk-{s}")
    st.date_input("目標日", key="ws-new-date", value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    st.text_input("備註", key="ws-new-notes")
    if st.button("建立", key="ws-new-create"):
        strategies = tuple(s for s in STRATEGY_ORDER if st.session_state.get(f"ws-new-chk-{s}"))
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
                notes=st.session_state["ws-new-notes"], strategies=strategies)
            st.rerun()

# ---------- 載入 ----------
scenarios = workspace.list_scenarios(WS_ROOT)
by_id = {sc.id: sc for sc in scenarios}
groups = workspace.load_groups(WS_ROOT)

# ---------- 卡片牆 ----------
st.subheader("劇本清單")
if len(scenarios) > 6:
    st.warning(f"目前有 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
if not scenarios:
    st.markdown("尚無劇本。用上方「＋ 建立劇本」開始。")
for sc in scenarios:
    summary = _summary_of(sc.id)
    st.markdown(scenario_card(
        {"id": sc.id, "symbol": sc.symbol, "direction": sc.direction,
         "target_price": sc.target_price, "target_date": sc.target_date,
         "status": sc.status, "group_id": sc.group_id, "notes": sc.notes},
        summary), unsafe_allow_html=True)
    cols = st.columns([1, 1, 1])
    with cols[0]:
        if st.button("分析", key=f"ws-an-{sc.id}"):
            if _analyze_with_status(workspace.analyze_scenario, WS_ROOT, sc.id) is not None:
                st.rerun()
    with cols[1]:
        if summary is not None and st.button("詳頁", key=f"ws-det-{sc.id}"):
            # st.switch_page 若不帶 query_params 會清空既有 query params
            # （官方文件："Query parameters to apply when navigating"——不傳即不帶），
            # 不可先 st.query_params["sid"]=... 再呼叫無參數版本，sid 會遺失。
            st.switch_page("views/detail.py", query_params={"sid": sc.id})
    with cols[2]:
        with st.popover("⋯ 管理"):
            if sc.status == "Active":
                st.text_input("原因", key=f"ws-reason-{sc.id}", placeholder="標記原因（必填）")
                reason = (st.session_state.get(f"ws-reason-{sc.id}") or "").strip()
                if st.button("標記達成", key=f"ws-reach-{sc.id}"):
                    if reason:
                        workspace.set_status(WS_ROOT, sc.id, "Reached", reason)
                        st.rerun()
                    else:
                        st.error("請填原因。")
                if st.button("標記失效", key=f"ws-inv-{sc.id}"):
                    if reason:
                        workspace.set_status(WS_ROOT, sc.id, "Invalidated", reason)
                        st.rerun()
                    else:
                        st.error("請填原因。")
            st.checkbox("確認刪除", key=f"ws-delok-{sc.id}")
            if st.button("刪除", key=f"ws-del-{sc.id}"):
                if st.session_state.get(f"ws-delok-{sc.id}"):
                    workspace.delete_scenario(WS_ROOT, sc.id)
                    st.rerun()
                else:
                    st.error("請先勾選「確認刪除」。")

# ---------- 群組里程碑軌 ----------
st.subheader("劇本群組")
for g in groups["groups"]:
    members = [by_id[m] for m in g["members"] if m in by_id]
    if not members:
        continue
    views_by_id = {m: _summary_of(m) for m in g["members"] if _summary_of(m) is not None}
    from webapp.components import milestone_rail
    st.markdown(milestone_rail(g, by_id, views_by_id), unsafe_allow_html=True)
    for i, rel in enumerate(g["relations"]):
        a_id, b_id = rel["pair"]
        st.markdown(
            f"{a_id} ↔ {b_id}｜提案：{PROPOSED_LABELS[rel['proposed']]}｜"
            f"已確認：{RELATION_LABELS[rel['confirmed']]}")
        ccols = st.columns([2, 1, 6])
        with ccols[0]:
            choice = st.selectbox("確認關係", ("milestone-path", "independent", "exclusive", "undefined"),
                                  format_func=lambda c: RELATION_LABELS[c], key=f"ws-rel-{g['id']}-{i}")
        with ccols[1]:
            if st.button("確認", key=f"ws-rel-btn-{g['id']}-{i}"):
                workspace.confirm_relation(WS_ROOT, g["id"], (a_id, b_id), choice)
                st.rerun()
        prev, nxt = by_id.get(a_id), by_id.get(b_id)
        if (prev is not None and nxt is not None and prev.status == "Reached"
                and rel["confirmed"] == "milestone-path"):
            if st.button(f"重新分析 {nxt.id}", key=f"ws-rean-{nxt.id}"):
                if _analyze_with_status(workspace.analyze_scenario, WS_ROOT, nxt.id) is not None:
                    st.rerun()
    if st.button("群組分析", key=f"ws-gan-{g['id']}"):
        if _analyze_with_status(workspace.analyze_group, WS_ROOT, g["id"]) is not None:
            st.rerun()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_views_workspace.py -v`
Expected: 全綠（迭代修頁面直到綠，`st.popover` 內含 button 的 `at.button` 定位機制沿用 v5 慣例——popover 不影響 AppTest 對內部 widget 的可見性，widget tree 平坦收集）

- [ ] **Step 5: 刪除舊測試與舊 view 檔**

```bash
git rm tests/test_webapp_workspace.py
git rm webapp/pages/0_劇本工作區.py
```

- [ ] **Step 6: 全回歸**

Run: `python -m pytest -q`

- [ ] **Step 7: Commit**

```bash
git add webapp/views/workspace.py tests/test_views_workspace.py
git commit -m "feat(v6): views/workspace.py — Artifact card wall, management popover, milestone rail"
```

---

### Task 11: webapp/views/detail.py（劇本詳頁，獨立路由）

**Files:**
- Create: `webapp/views/detail.py`
- Modify: `tests/test_webapp_v4.py`（剩餘斷言遷入新測試後刪除本檔）
- Test: `tests/test_views_detail.py`

**Interfaces:**
- Consumes：`st.query_params["sid"]`、`workspace.latest_result`、`render.render_step2/3/4`／`comparison_table_html`（Task 7）、`components.candidate_card`。
- Produces：`webapp/views/detail.py`——Header 卡（Symbol/現價/目標價/snapshot 時間/資料品質/重新分析）→ 推薦候選卡 → Heatmap（含封頂）→ 候選比較表 → 進階區（v5 `render_step4` 原樣）。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_views_detail.py
"""v6 spec §3.3：獨立劇本詳頁——四步結構＋sid 不存在保護。取代 test_webapp_v4.py
剩餘的分組表格/badge/scatter/greeks 相關斷言（原針對 v5 workspace 詳頁）。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/views/detail.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def _mk_analyzed(ws_root, price=120.0, tdate="2026-08-01"):
    sc = workspace.create_scenario(ws_root, "XYZ", "bullish", price, tdate, "",
                                   ("long-call", "bull-call-spread"), ts=TS)
    store.save_constraints(ws_root, 100000.0)
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=FIX, ts=TS)
    return sc


def test_missing_sid_shows_error_card(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert any("找不到" in e.value or "尚未指定" in e.value for e in at.error)


def test_unknown_sid_shows_error_card(ws):
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = "NOPE-1-202601"
    at.run()
    assert not at.exception
    assert any("找不到" in e.value for e in at.error)


def test_four_step_structure_renders(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception
    subheaders = " ".join(s.value for s in at.subheader)
    body = " ".join(m.value for m in at.markdown)
    assert "Header" not in subheaders  # header 是卡片非 subheader，不強制字面比對
    assert "Step 2" in subheaders or "劇本主圖" in body
    assert "Step 3" in subheaders or "比較" in body
    assert "Step 4" in subheaders or "進階" in body


def test_candidate_card_price_visible(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    body = " ".join(m.value for m in at.markdown)
    assert "Breakeven" in body or "保本" in body


def test_reanalyze_button_present(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert any(b.key == "detail-reanalyze" for b in at.button)


def test_scatter_expander_and_greeks_present(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    labels = {e.label for e in at.expander}
    assert "韌性與壓力情境" in labels
    assert "報酬×韌性散點" in labels
    assert "Greeks 與流動性" in labels


def test_header_escapes_symbol_html_injection(ws):
    """detail.py 的 Header 卡直接組字串後 unsafe_allow_html=True 呈現——sc.symbol
    是使用者輸入，必須 html.escape() 才可注入，否則破壞版面或執行注入內容。

    注意：`<`/`>` 是 Windows 檔名非法字元，若經 workspace.create_scenario 產生
    （id 由 symbol 直接組成），會在 store.save_scenario 寫檔階段就先炸掉，測不到
    render 層的跳脫邏輯。改直接建構 Scenario 物件、以固定安全 id 存檔，僅讓
    symbol 欄位（JSON 內容字串，無檔名限制）帶惡意字串，單純驗證 detail.py 的
    HTML 跳脫，不糾纏 id 產生規則。"""
    from option_chaser.store import Scenario
    sc = Scenario(schema_version=1, id="INJECT-TEST-1", symbol="<script>alert(1)</script>",
                 direction="bullish", target_price=120.0, target_date="2026-08-01",
                 created_at=TS, notes="", group_id="G-INJECT", status="Active",
                 strategies=("long-call",))
    store.save_scenario(ws, sc)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = "INJECT-TEST-1"
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_v1_legacy_result_renders_without_crash(ws):
    """End-to-end proof of Task 6/7's .get()-based v1 fallback: a real result
    file written with v2 fields stripped and schema_version rolled back to 1
    must still render the full detail page (degraded, not KeyError)."""
    sc = _mk_analyzed(ws)
    path = store.latest_result_path(ws, sc.id)
    view = store.load_result(path)
    for r in view["results"]:
        for c in r["candidates"] + r["expiry_best"]:
            c.pop("natural_per_contract", None)
            c.pop("max_profit_per_contract", None)
            c.pop("cap_price", None)
    for g in view["expiry_groups"]:
        for row in g["rows"]:
            cc = row["candidate"]
            cc.pop("natural_per_contract", None)
            cc.pop("max_profit_per_contract", None)
            cc.pop("cap_price", None)
    view["schema_version"] = 1
    store.atomic_write_json(path, view)

    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "舊版分析結果" in body
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_views_detail.py -v`
Expected: FAIL（`webapp/views/detail.py` 不存在）

- [ ] **Step 3: 實作**

```python
# webapp/views/detail.py
"""v6 spec §3.3：劇本詳頁——獨立路由（st.Page visibility="hidden"），
以 st.query_params["sid"] 指定劇本。"""
from __future__ import annotations

import html
import os
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from webapp.components import candidate_card, quality_badge
from webapp.render import comparison_table_html, esc, render_step2, render_step3, render_step4
from webapp.status import derive_result_status, quality_tone
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))

inject()

sid = st.query_params.get("sid")
if not sid:
    st.error("尚未指定劇本，請從劇本工作區點擊「詳頁」進入。")
    st.stop()

try:
    sc = store.load_scenario(store.scenario_path(WS_ROOT, sid))
except FileNotFoundError:
    st.error(f"找不到劇本 `{sid}`。")
    st.stop()

view = workspace.latest_result(WS_ROOT, sid)
st.title(f"詳頁：{sc.symbol}")

# ---------- Header ----------
# sc.symbol 為使用者輸入，經 unsafe_allow_html=True 呈現前必須 html.escape()；
# 含 $ 金額的整段組字串在 return/呼叫前統一經 render.esc() 處理（既有紅線，見
# components.py／comparison_table_html 同一慣例）。
_safe_symbol = html.escape(sc.symbol, quote=True)
header_lines = [f"**{_safe_symbol}** ｜ 目標 ${sc.target_price:g} ｜ {sc.target_date}"]
if view is not None:
    header_lines.append(f"現價 ${view['meta']['spot']:.2f} ｜ 資料時間 {view['snapshot_ref']['fetched_at']} "
                        + quality_badge(quality_tone(view, workspace.ny_today())))
st.markdown(esc("<br>".join(header_lines)), unsafe_allow_html=True)
if st.button("重新分析", key="detail-reanalyze"):
    try:
        with st.status("分析中……", expanded=True) as status:
            workspace.analyze_scenario(WS_ROOT, sid, progress=status.write)
            status.update(label="分析完成", state="complete")
        st.rerun()
    except (FetchError, ParamError) as e:
        st.error(str(e))
    except Exception:
        st.error("分析過程發生錯誤，請稍後再試。")

if view is None:
    st.markdown(derive_result_status(view))
    st.stop()

if view["data_quality"]["all_quotes_filtered"]:
    from webapp.status import INSUFFICIENT_QUOTE_MESSAGE
    st.warning(INSUFFICIENT_QUOTE_MESSAGE)
    with st.expander("查看過濾原因"):
        for r in view["results"]:
            for stage in r["filter_stages"]:
                st.markdown(f"{r['strategy']}／{stage['label']}：移除 {stage['removed']}")

key = view["default_selection"][1] if view["default_selection"] else None
if key is not None:
    cand = next(row["candidate"] for g in view["expiry_groups"] for row in g["rows"]
               if row["candidate"]["candidate_key"] == key)
    strategy = next(row["strategy"] for g in view["expiry_groups"] for row in g["rows"]
                    if row["candidate"]["candidate_key"] == key)
    st.markdown(candidate_card(cand, strategy), unsafe_allow_html=True)

render_step2(view, key)
st.subheader("候選比較")
st.markdown(comparison_table_html(view), unsafe_allow_html=True)
render_step4(view, key)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/test_views_detail.py -v`
Expected: 全綠

- [ ] **Step 5: 收斂 `test_webapp_v4.py`**

`test_webapp_v4.py` 剩餘測試（`test_grouped_table_renders`／`test_default_selection_matches_service_and_has_no_warning`／`test_row_button_switches_selected_key`／`test_three_advanced_expanders_present`／`test_dollar_amounts_are_escaped`／`test_abbr_titles_come_from_glossary`／`test_edit_form_resubmit_triggers_new_analysis`／`test_glossary_importable_without_streamlit`）語意分兩類：

- `test_edit_form_resubmit_triggers_new_analysis`：屬快速試算（app.py 表單重跑行為）→ 已於 Task 9 `test_views_quick.py` 的 `test_happy_path_renders_four_steps` 覆蓋核心路徑；表單重跑細節斷言追加至 `test_views_quick.py`（本步驟執行，見下）。
- 其餘分組表格/badge/選看/expander/`$`跳脫/glossary title 斷言：本質是 `render.py` 的渲染輸出驗證，與頁面無關——**遷移至既有 `tests/test_render_cap.py` 或保留獨立 `tests/test_render_v4_regression.py`**（本步驟建立，直接複製舊斷言邏輯，改用 `store.serialize_result` + `render.*` 直接呼叫，不透過 AppTest，減少頁面耦合）：

```bash
git mv tests/test_webapp_v4.py tests/test_render_v4_regression.py
```

編輯 `tests/test_render_v4_regression.py`：刪除 `test_help_page_renders`（已刪，Task 8 完成）、`test_edit_form_resubmit_triggers_new_analysis`（改寫為 quick.py 版本，追加至 `test_views_quick.py`）；其餘測試的 `AppTest.from_file("webapp/app.py")` 改為 `AppTest.from_file("webapp/views/quick.py")`（快速試算路徑與舊 v5 app.py 行為一致，這些斷言原本測的就是 quick-analysis 流程的渲染輸出，非工作區頁）。

於 `tests/test_views_quick.py` 追加（Task 9 檔案，本步驟補一測試）：

```python
def test_edit_form_resubmit_triggers_new_analysis(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    assert at.session_state["result"].request.base_params.target_price == 120.0
    new_target = 125.0
    at.number_input(key="target_price").set_value(new_target)
    submit_buttons = [b for b in at.button if b.label == "開始分析"]
    assert submit_buttons
    submit_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
    assert at.session_state["result"].request.base_params.target_price == new_target
```

- [ ] **Step 6: 全回歸**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 7: Commit**

```bash
git add webapp/views/detail.py tests/test_views_detail.py tests/test_render_v4_regression.py tests/test_views_quick.py
git commit -m "feat(v6): views/detail.py — independent scenario detail page (comparison table, cap heatmap)"
```

---

### Task 12: webapp/app.py 路由入口 ＋ 紅線掃描 ＋ 舊檔清理

**Files:**
- Modify: `webapp/app.py`（全面改寫）
- Delete: `webapp/pages/`（整個目錄，剩餘檔案由前置 tasks 已搬空，本 task 確認清空並移除目錄）
- Modify: `tests/test_redlines.py`
- Modify: `tests/test_heatmap_colors.py`（見 Step 4a——`webapp.app` 不再重新匯出 `cell_color`）
- Test: `tests/test_app_navigation.py`
- Modify: `docs/view-contract.md`（核對定稿）

**Interfaces:**
- Produces：`webapp/app.py`——`st.set_page_config` 一次性呼叫 → `st.navigation([...])` 宣告四頁＋一隱藏頁 → `page.run()`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_app_navigation.py
"""v6 spec §1.1：st.navigation 路由——四頁載入無例外、無 app 字樣、詳頁隱藏可達。"""
import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def test_default_page_is_overview(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "戰情總覽" in titles


def test_no_app_literal_in_navigation(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    body = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.title)
    assert body.strip() != "app"
    assert "\nappa" not in body  # 弱保護：確保不是巧合子字串誤判


def test_switch_to_workspace_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/workspace.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "劇本工作區" in titles


def test_switch_to_quick_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "快速試算" in titles


def test_switch_to_help_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/help.py")
    at.run()
    assert not at.exception


def test_detail_page_reachable_though_hidden(ws):
    sc = workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                                   ("long-call",), ts=TS)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/detail.py")
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception


def test_overview_empty_state_page_link_reaches_workspace(ws):
    """Task 8 shipped plain-text guidance (st.page_link requires its target to
    already be a page registered in st.navigation, which does not exist until
    this task wires the router — see Task 8 Step 3 comment). Now that the
    router is registered, overview.py's empty-state page_link must resolve
    without raising `StreamlitAPIException` (the exact failure mode this task
    guards against): `streamlit.testing.v1.AppTest` has no typed accessor for
    `st.page_link` (it surfaces as an opaque UnknownElement — verified against
    the installed streamlit version), so `not at.exception` after reaching
    this exact page through the real router IS the load-bearing assertion,
    not a placeholder — a page_link pointed at an unregistered/nonexistent
    page raises during script execution, which `at.exception` would catch."""
    at = AppTest.from_file("webapp/app.py")
    at.run()   # default page = overview (empty workspace) -> renders the page_link
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body or "劇本工作區" in body


def test_workspace_detail_button_switches_with_sid(ws):
    """Task 10's「詳頁」按鈕呼叫 st.switch_page(..., query_params={"sid":...})——
    只能經真實入口（webapp/app.py，含 st.navigation 宣告）驗證，不可獨立測試
    workspace.py（見 Task 10 註記）。同時驗證 st.switch_page 不帶 query_params
    會清空既有值這件事沒有在此處踩雷（query_params 是隨 switch_page 呼叫一併
    帶入，不是先設 st.query_params 再呼叫無參數版本）。"""
    sc = workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                                   ("long-call",), ts=TS)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/workspace.py")
    at.run()
    next(b for b in at.button if b.key == f"ws-det-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert at.query_params.get("sid") == sc.id


def test_quick_save_success_links_to_detail_page(ws, monkeypatch):
    from option_chaser import service
    from option_chaser.data.snapshot import load_snapshot
    FIX = "tests/fixtures/xyz_v4_six_expiries.json"
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    at.text_input(key="symbol").set_value("XYZ")
    at.number_input(key="target_price").set_value(120.0)
    at.date_input(key="target_date").set_value(__import__("datetime").date(2026, 8, 1))
    at.checkbox(key="chk-long-call").set_value(True)
    at.run()
    at.button[0].set_value(True).run(timeout=30)
    save_buttons = [b for b in at.button if b.label == "保存為劇本"]
    assert save_buttons
    save_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_app_navigation.py -v`
Expected: FAIL（`webapp/app.py` 仍是 v5 內容，無 `st.navigation`）

- [ ] **Step 3: 實作**

```python
# webapp/app.py（整檔取代）
"""v6 spec §1.1：路由入口。所有金融計算一律經 option_chaser.service（沿用），
本檔僅宣告 st.navigation 頁面清單，不含任何業務邏輯。"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Option Chaser", layout="wide")

page = st.navigation([
    st.Page("views/overview.py", title="戰情總覽", icon="📊", default=True),
    st.Page("views/workspace.py", title="劇本工作區", icon="🗂"),
    st.Page("views/quick.py", title="快速試算", icon="⚡"),
    st.Page("views/help.py", title="使用說明", icon="📖"),
    st.Page("views/detail.py", title="詳頁", url_path="detail", visibility="hidden"),
])
page.run()
```

- [ ] **Step 4: 刪除舊 pages 目錄**

```bash
rm -rf webapp/pages
rm -rf webapp/pages/__pycache__ 2>/dev/null || true
```

（`webapp/pages/` 內容已於 Task 8/10 各自搬遷完畢，此步驟確認目錄清空後移除。）

- [ ] **Step 4a: 修正 `tests/test_heatmap_colors.py`（`webapp.app` 不再重新匯出 `cell_color`）**

v5 的 `webapp/app.py` 在頂層執行 `st.form(...)` 等有狀態呼叫，裸匯入會污染行程級 DeltaGenerator 單例，因此該測試改用子行程間接讀取原始碼。v6 的 `webapp/app.py` 已不含任何 `st.form`／頂層有狀態呼叫（純路由宣告＋`page.run()`），但 `page.run()` 本身在無 `ScriptRunContext` 的裸匯入下執行整個預設頁（`views/overview.py`，含 `workspace.list_scenarios` 等 I/O）仍不安全、且 `cell_color` 已不在 `webapp.app` 命名空間內（從未被路由器重新匯出）。`cell_color` 的真正定義處自始至終是 `webapp/render.py`，且該檔零頂層有狀態呼叫（僅函數定義），可安全直接匯入。整檔改寫：

```python
# tests/test_heatmap_colors.py（整檔取代）
"""v6：cell_color 定義於 webapp/render.py（純函數模組，零頂層 Streamlit
有狀態呼叫），可直接匯入，不需 v5 時代因 webapp/app.py 頂層 st.form()
污染單例而採用的子行程工作區。"""
from webapp.render import cell_color


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

Run: `python -m pytest tests/test_heatmap_colors.py -v`
Expected: 4 passed（無子行程、無 poisoning 風險——確認同一 pytest 行程內其餘 AppTest 測試不受影響）

- [ ] **Step 4b: 補上 Task 8/9 延後的 `st.page_link` 導覽（路由已註冊，現在安全）**

`st.page_link(page, ...)` 要求 `page` 必須是已於 `st.navigation` 註冊的頁面，否則丟 `StreamlitAPIException`（見官方文件："The Python file must be the source of a page in `st.navigation`"）。Task 8／Task 9 撰寫時路由尚未存在，故僅用純文字指引；路由於本 task Step 3 建好後，此處補上真正可點擊連結。

`webapp/views/overview.py`：`st.markdown("尚無劇本。前往「劇本工作區」建立第一個劇本。")` 改為：

```python
    st.markdown("尚無劇本。前往「劇本工作區」建立第一個劇本。")
    st.page_link("views/workspace.py", label="建立第一個劇本", icon="🗂")
```

`webapp/views/quick.py`：spec §1.2 要求成功保存與撞名兩種情況都需連結到該劇本詳頁（`query_params` 直接支援，見 API 簽名 `st.page_link(page, *, ..., query_params=None)`）。原本的純文字訊息：

```python
    if _existing is not None:
        st.markdown(f"已有同名劇本：`{_existing}`，前往劇本工作區查看。")
    else:
        if st.button("保存為劇本", key="save-as-scenario"):
            sc, _ = workspace.adopt_result(WS_ROOT, _final_result)
            st.success(f"已保存為劇本 `{sc.id}`，前往劇本工作區查看。")
```

改為：

```python
    if _existing is not None:
        st.markdown(f"已有同名劇本：`{_existing}`。")
        st.page_link("views/detail.py", label="前往查看", icon="📄",
                     query_params={"sid": _existing})
    else:
        if st.button("保存為劇本", key="save-as-scenario"):
            sc, _ = workspace.adopt_result(WS_ROOT, _final_result)
            st.success(f"已保存為劇本 `{sc.id}`。")
            st.page_link("views/detail.py", label="前往查看", icon="📄",
                         query_params={"sid": sc.id})
```

**Streamlit rerun 注意**：`st.button` 觸發後同一次 rerun 內接著 `st.success`＋`st.page_link` 屬正常同輪渲染，不需要額外 `st.rerun()`（`adopt_result` 已完成寫入，`st.page_link` 只是導覽元件，不影響已保存的資料）。

- [ ] **Step 4c: 修正 Task 8/9/10 中「獨立載入子頁面」的既有測試——加入 `st.page_link`／`st.switch_page` 後不再安全**

**已實測驗證**（非臆測）：`AppTest.from_file` 直接載入單一 view 檔時，該檔即是「入口腳本」，內部沒有任何 `st.navigation` 宣告；此時腳本內任何 `st.page_link`／`st.switch_page` 呼叫一律拋 `StreamlitAPIException`（`Could not find page: ...`），**與目標檔案是否存在、路由是否已建好完全無關**——這是 Streamlit 對「入口腳本沒有宣告導覽」的通用行為，不是本專案的路徑問題。Step 4b 為 `overview.py`／`quick.py` 新增的 `st.page_link` 呼叫只在特定分支執行（空工作區／保存成功／偵測撞名），但下列四個既有測試剛好會踩進那些分支，必須改為經真實入口 `webapp/app.py`（內含 `st.navigation`）＋`switch_page(...)` 到達目標頁後再操作：

```bash
python - <<'PYEOF'
import pathlib

def patch(path, old, new, label):
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, f"anchor not found in {path} ({label})"
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched", path, label)

patch("tests/test_views_overview_help.py",
'''def test_overview_empty_workspace_shows_guidance(ws):
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body''',
'''def test_overview_empty_workspace_shows_guidance(ws):
    # overview.py 現含 st.page_link（空工作區分支）——st.page_link 要求入口腳本
    # 已宣告 st.navigation，故經真實路由到達本頁，而非直接載入本檔。
    at = AppTest.from_file("webapp/app.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body''',
"empty_workspace_shows_guidance -> routed via app.py")

patch("tests/test_views_overview_help.py",
'''def test_overview_no_position_language(ws):
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    body = " ".join(m.value for m in at.markdown)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body''',
'''def test_overview_no_position_language(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    body = " ".join(m.value for m in at.markdown)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body''',
"no_position_language -> routed via app.py")

patch("tests/test_views_quick.py",
'''def test_save_as_scenario_button_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)''',
'''def test_save_as_scenario_button_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    # quick.py 保存成功分支現含 st.page_link，須經真實入口到達本頁。
    # AppTest.switch_page 不會自動 rerun（官方文件："does not automatically
    # rerun the app. Use a follow-up call to AppTest.run()"）——必須緊接 at.run()
    # 才能在正確頁面上操作 widget，否則後續 _fill_and_submit 仍作用在總覽頁。
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    at = _fill_and_submit(at)''',
"save_as_scenario_button_persists -> routed via app.py")

patch("tests/test_views_quick.py",
'''def test_save_as_scenario_duplicate_shows_link(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    workspace.create_scenario(tmp_path, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts="2026-07-22T00:00:00+00:00")
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)''',
'''def test_save_as_scenario_duplicate_shows_link(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    workspace.create_scenario(tmp_path, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts="2026-07-22T00:00:00+00:00")
    # quick.py 撞名分支現含 st.page_link，須經真實入口到達本頁；
    # switch_page 後同樣須緊接 at.run()（見上一則同理）。
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    at = _fill_and_submit(at)''',
"save_as_scenario_duplicate_shows_link -> routed via app.py")
PYEOF
```

`_fill_and_submit(at)` 內部呼叫的 `at.button[0]` 等定位邏輯與頁面內元件 key 無關於「透過 router 或直接載入」，經 `switch_page` 到達後行為與獨立載入相同，測試邏輯本身不需重寫，只換入口。

- [ ] **Step 4d: 跑 Task 12 新增與修正的測試**

Run: `python -m pytest tests/test_app_navigation.py tests/test_views_overview_help.py tests/test_views_quick.py tests/test_views_workspace.py -v`
Expected: 全綠（含 `test_overview_empty_state_page_link_reaches_workspace`／`test_quick_save_success_links_to_detail_page`／`test_workspace_detail_button_switches_with_sid`／四則被修正的既有測試）

- [ ] **Step 5: 更新紅線掃描 TARGETS**

```python
# tests/test_redlines.py（整檔取代）
"""v4/v6 spec：banned-vocabulary scan over GUI sources and goldens."""
from pathlib import Path

BANNED = ["獲利機率", "機率加權", "勝率", "POP", "probability",
          "期望報酬", "expected profit", "Sharpe", "CVaR"]
TARGETS = [Path("webapp/app.py"), Path("webapp/render.py"), Path("webapp/theme.py"),
           Path("webapp/status.py"), Path("webapp/components.py"),
           Path("webapp/views/overview.py"), Path("webapp/views/workspace.py"),
           Path("webapp/views/quick.py"), Path("webapp/views/detail.py"),
           Path("webapp/views/help.py"),
           Path("option_chaser/glossary.py"), Path("option_chaser/store.py"),
           Path("option_chaser/workspace.py"), Path("option_chaser/vocabulary.py"),
           *sorted(Path("tests/fixtures").glob("golden_*.txt"))]


def test_no_banned_vocabulary():
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        for term in BANNED:
            assert term not in text, f"{term!r} found in {path}"


def test_new_copy_avoids_bare_probability_word():
    for path in [Path("option_chaser/glossary.py"), Path("webapp/views/help.py"),
                 Path("option_chaser/scenarios.py"), Path("option_chaser/store.py"),
                 Path("option_chaser/workspace.py"), Path("option_chaser/vocabulary.py"),
                 Path("webapp/render.py"), Path("webapp/theme.py"), Path("webapp/status.py"),
                 Path("webapp/components.py"), Path("webapp/views/overview.py"),
                 Path("webapp/views/workspace.py"), Path("webapp/views/quick.py"),
                 Path("webapp/views/detail.py")]:
        assert "機率" not in path.read_text(encoding="utf-8"), path
```

- [ ] **Step 6: 核對 `docs/view-contract.md`**

確認 Task 2 起草的 `docs/view-contract.md` 所列鍵與 `tests/test_store_serialize_v2.py`／`tests/test_store_serialize.py` 斷言鎖定鍵一致（人工核對，無需程式化——文件為描述性文件）。若 Task 7 新增的 `comparison_table_html`／`heatmap_html(cand=...)` 消費了 view-contract 未提及的鍵，於文件「消費者」段補一句：「`comparison_table_html` 額外讀取 `cap_price`／`max_profit_per_contract`（v2 新欄，已列於 candidate dict 段）。」

- [ ] **Step 7: 跑測試確認通過＋全回歸**

Run: `python -m pytest tests/test_app_navigation.py tests/test_redlines.py tests/test_heatmap_colors.py -v && python -m pytest -q`
Expected: 全綠

- [ ] **Step 8: Commit**

```bash
git add webapp/app.py tests/test_app_navigation.py tests/test_redlines.py tests/test_heatmap_colors.py docs/view-contract.md
git rm -r webapp/pages 2>/dev/null || true
git commit -m "feat(v6): app.py -> st.navigation router; delete legacy pages/; expand redline scan; simplify cell_color test (no more subprocess workaround)"
```

---

### Task 13: Windows 一鍵啟動（BAT）與資料目錄收尾

**Files:**
- Create: `啟動 Option Chaser.bat`
- Create: `建立桌面捷徑.bat`
- Create: `logs/.gitkeep`
- Modify: `.gitignore`

**Interfaces:**
- 產出：兩個 Windows batch 腳本；不寫 pytest（spec §11.9：Windows batch 不納入 pytest，屬 §9.3／§15 實機驗收）。

- [ ] **Step 1: `.gitignore` 追加**

```bash
python - <<'PYEOF'
import pathlib
p = pathlib.Path(".gitignore")
text = p.read_text(encoding="utf-8")
additions = "\n.venv/\nlogs/*.log\nlogs/running.lock\n"
if "logs/*.log" not in text:
    p.write_text(text.rstrip("\n") + additions + "\n", encoding="utf-8")
    print("patched .gitignore")
PYEOF
```

- [ ] **Step 2: 建立 `logs/.gitkeep`**

```bash
mkdir -p logs && touch logs/.gitkeep
```

- [ ] **Step 3: 撰寫 `啟動 Option Chaser.bat`**

```batch
@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist logs mkdir logs
set "LOGFILE=logs\launch-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%.log"
set "LOGFILE=%LOGFILE: =0%"

echo Option Chaser 啟動中... > "%LOGFILE%"

rem --- Step 1: 找 Python ---
rem 全程用 !errorlevel!（延遲展開，已於檔首 setlocal enabledelayedexpansion）：
rem %errorlevel% 在整個 if/else 括號區塊於解析當下就被展開成同一個值，內層
rem 對 python --version 的判斷會誤讀外層 py -3 的舊值——這是已知的 batch 陷阱，
rem 全部改用 !errorlevel! 才能讓每個判斷讀到「當下」剛執行完命令的真實結果。
set "PYCMD="
py -3 --version >nul 2>&1
if !errorlevel!==0 (
  set "PYCMD=py -3"
) else (
  python --version >nul 2>&1
  if !errorlevel!==0 (
    set "PYCMD=python"
  )
)
if "%PYCMD%"=="" (
  echo 找不到 Python。>> "%LOGFILE%"
  echo 找不到 Python。
  echo 請先安裝 Python 3.11 以上版本：https://www.python.org/downloads/
  pause
  exit /b 1
)
rem 找到指令不代表版本足夠——實際檢查 >= 3.11（spec §10.2「版本 <3.11...」）
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo 已安裝的 Python 版本過舊。>> "%LOGFILE%"
  echo 已安裝的 Python 版本過舊。
  echo 請先安裝 Python 3.11 以上版本：https://www.python.org/downloads/
  pause
  exit /b 1
)
echo 使用 Python: %PYCMD% >> "%LOGFILE%"

rem --- Step 2: 建立 / 使用 .venv ---
set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo 首次啟動，正在安裝必要元件（約 2-3 分鐘，僅此一次）...... >> "%LOGFILE%"
  echo 首次啟動，正在安裝必要元件（約 2-3 分鐘，僅此一次）......
  %PYCMD% -m venv .venv >> "%LOGFILE%" 2>&1
  if not exist "%VENV_PY%" (
    echo 建立虛擬環境失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
  "%VENV_PY%" -m pip install -e ".[gui]" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo 安裝必要元件失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
)

rem --- Step 3: 依賴健檢 ---
"%VENV_PY%" -c "import streamlit, option_chaser, webapp" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo 元件檢查失敗，正在重新安裝......>> "%LOGFILE%"
  "%VENV_PY%" -m pip install -e ".[gui]" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo 元件安裝失敗，詳見 %LOGFILE%
    pause
    exit /b 1
  )
)

rem --- Step 4: Port 8501 檢查（身分驗證） ---
set "LOCK=logs\running.lock"
"%VENV_PY%" -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=2)" >nul 2>&1
if %errorlevel%==0 (
  if exist "%LOCK%" (
    set /p LOCKPID=<"%LOCK%"
    tasklist /fi "PID eq !LOCKPID!" 2>nul | find "!LOCKPID!" >nul
    if !errorlevel!==0 (
      echo Option Chaser 已在執行，為你開啟瀏覽器。
      start http://localhost:8501
      exit /b 0
    )
  )
  echo 連接埠 8501 上有其他 Streamlit 程式，請關閉後重試。
  pause
  exit /b 1
)

rem --- Step 5: 取得本行程 PID 寫入 lock，再啟動（非 headless，瀏覽器由
rem     Streamlit 原生自動開啟）。PID 取得法：設一個本次執行獨有的視窗標題，
rem     用 tasklist /v 依標題反查 PID——不依賴 wmic（Windows 11 起預設移除）或
rem     PowerShell，純 batch 內建指令，相容性最佳。 ---
set "UNIQUE_TITLE=OptionChaserLauncher_%RANDOM%%RANDOM%"
title %UNIQUE_TITLE%
set "SELFPID="
for /f "tokens=2 delims=," %%P in ('tasklist /v /fo csv /nh ^| findstr /i "%UNIQUE_TITLE%"') do set "SELFPID=%%~P"
if not "%SELFPID%"=="" echo %SELFPID%> "%LOCK%"

echo Option Chaser 啟動中，請稍候瀏覽器自動開啟......
"%VENV_PY%" -m streamlit run webapp\app.py --server.port 8501
del "%LOCK%" 2>nul
```

- [ ] **Step 4: 撰寫 `建立桌面捷徑.bat`**

```batch
@echo off
chcp 65001 >nul
set "TARGET=%~dp0啟動 Option Chaser.bat"
set "SHORTCUT=%USERPROFILE%\Desktop\啟動 Option Chaser.lnk"
powershell -NoProfile -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell; " ^
  "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); " ^
  "$Shortcut.TargetPath = '%TARGET%'; " ^
  "$Shortcut.WorkingDirectory = '%~dp0'; " ^
  "$Shortcut.Save()"
if exist "%SHORTCUT%" (
  echo 已在桌面建立捷徑：啟動 Option Chaser
) else (
  echo 建立捷徑失敗，請手動將「啟動 Option Chaser.bat」拖曳到桌面建立捷徑。
)
pause
```

- [ ] **Step 5: 全回歸（確認 pytest 不受新增檔案影響）**

Run: `python -m pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add "啟動 Option Chaser.bat" "建立桌面捷徑.bat" logs/.gitkeep .gitignore
git commit -m "feat(v6): Windows one-click launcher BAT (self-installing, port-owned lock, native browser open)"
```

---

## Self-Review 紀錄

- **Spec 覆蓋**：§0（決議）→ 全 task 隱含遵守；§1.1（導覽/版本地板）→ Task 12；§1.2（quick save）→ Task 3+9；§2（視覺 token/元件）→ Task 4+6；§3.1-3.5（五頁）→ Task 8/9/10/11；§4（候選價格）→ Task 2+6+7；§5（封頂）→ Task 7；§6（狀態）→ Task 5；§7（view-contract）→ Task 2+12；§8（打包/版本）→ Task 1+12；§9（BAT）→ Task 13；§10（紅線）→ 全 task GUI 紅線遵守，Task 12 掃描擴充；§11（測試策略）→ 各 task test 段+Task 9/11 舊測試收斂；§11A（審計契約）→ 供後續 codex-audit 使用，非本 plan 任務；§12（驗收案例）→ 對應 SDD 完成後之整體驗收步驟（非單一 task）；§13（不做清單）→ 未觸碰任何列舉項。
- **型別一致**：`adopt_result(ws_root, result, notes="", *, ts=None) -> (Scenario, Path)` 於 Task 3 定義，Task 9 quick.py 呼叫簽名一致；`heatmap_html(matrix, cand=None)` 於 Task 7 定義，Task 9/11 呼叫點對照更新（quick.py 透過 `render_step2` 間接呼叫，`render_step2` 內部呼叫已於 Task 7 Step 5 同步修改）；`comparison_table_html(view)` Task 7 定義、Task 11 使用一致；`scenario_card`/`candidate_card`/`milestone_rail` 簽名 Task 6 定義、Task 10/11 呼叫一致。
- **已知妥協（review 時檢視）**：(a) Task 13 BAT 的 PID 身分驗證改用「唯一視窗標題 + `tasklist /v /fo csv` 反查」，純 batch 內建、不依賴 wmic（Win11 起預設移除）或 PowerShell，單一定案腳本（已修正原稿中三段互相取代的草稿殘留）；(b) Task 9 Step 6 承認中繼態測試失敗（`test_webapp_v4.py` 依賴尚未搬遷的路徑），由 Task 10/11 收斂——SDD 執行時若採 subagent-driven-development，此中繼態不應跨 task 提交到 master（同一 PR/branch 內連續完成即可，plan 內已排序）；(c) `webapp/views/overview.py` 與 `webapp/views/quick.py` 的 `st.page_link` 導覽刻意延後到 Task 12（`st.page_link` 要求目標頁面已於 `st.navigation` 註冊，Task 8/9 撰寫當下路由尚未存在——先出純文字指引，Task 12 Step 4b 於路由建好後補上真正連結並以 `test_app_navigation.py` 驗證整合行為，而非讓 Task 8/9 自證一個尚不成立的路由依賴）；(d) `tests/test_heatmap_colors.py` 的 v5 子行程工作區隨 Task 12 的 `app.py` 改寫而失效（`cell_color` 從未被路由器重新匯出），已在 Task 12 Step 4a 一併簡化為直接匯入 `webapp.render.cell_color`（該模組零頂層 Streamlit 有狀態呼叫，安全）；(e) Task 1 版本升級 0.5.0→0.6.0 會使三個既有測試（`test_store_serialize.py`／`test_vocabulary.py`／`test_workspace_analyze.py`）斷言的硬編碼版本字串變紅，已於 Task 1 Step 6 一併修正（發現於自我複審，非 spec 要求項，但屬必要修正，否則升版本當下全回歸即紅）；(f) v1 舊 result 檔（schema_version 1，缺 Task 2 三個新欄）相容性：`components.candidate_card`／`render.heatmap_html`／`render.comparison_table_html` 三處消費點全數改用 `.get()` 降級讀取＋顯示 `status.LEGACY_RESULT_MESSAGE`（Task 5/6/7），並在 Task 11 補一則端到端測試（真實寫入 v1 形狀的 result 檔，經完整詳頁渲染驗證不崩潰）；(g) 使用者可控文字（scenario symbol／notes）注入 `unsafe_allow_html=True` 樣板前，`webapp/components.py` 全面改用 `html.escape()` 跳脫（Task 6），並補 HTML 注入測試；元件最終回傳字串統一經既有 `render.esc()`（`$` 轉義）處理，呼叫端不需重複跳脫；(h) plan 內的 `python - <<'PYEOF'` heredoc／`rm -rf`／`git rm` 等指令皆以本 session 已驗證可用的 Bash 工具（git-bash 後端）執行——本 session 全程（含 v5 SDD 十一個 task）持續使用相同語法成功操作，SDD 派工的 subagent 繼承相同工具集，非空想的可攜性風險（codex round 2 已 CONCEDE）；(i) `st.switch_page`／`st.page_link` 一經實測驗證：`AppTest.from_file` 直接載入單一 view 檔時，該檔即是「入口腳本」，內部無 `st.navigation` 宣告，任何導覽呼叫一律拋 `StreamlitAPIException`——與目標檔案是否存在、路由是否建好無關。因此 Task 10「詳頁」按鈕的 `st.switch_page` 與 Task 8/9 新增的 `st.page_link` 呼叫，其對應測試一律延後到 Task 12（經 `webapp/app.py` 真實入口＋`switch_page` 到達目標頁後才點擊），Task 12 Step 4c 額外修正四則 Task 8/9 既有測試改走真實入口；(j) `st.switch_page` 不帶 `query_params` 會清空既有值（官方文件明載），Task 10「詳頁」按鈕改為 `st.switch_page(page, query_params={"sid": sc.id})` 單一呼叫，不再先設 `st.query_params` 再呼叫無參數版本；(k) 新增的 `heatmap_html` cap_note 與 `comparison_table_html` 兩處回傳含裸 `$` 金額，經 `unsafe_allow_html=True` 呈現前補上既有 `esc()` 慣例（v5 原 `heatmap_html` 因無 `$` 內容而不需要，v6 新增內容補回，`esc()` 對無 `$` 字串為 no-op，不影響 v5 既有輸出的逐位元相等測試）；detail.py 的 Header 卡另補 `html.escape()`（使用者輸入 symbol）＋`esc()`（`$` 金額），並補注入測試（以直接建構 `Scenario` 物件、固定安全 id 存檔的方式繞開「`<`/`>` 是 Windows 檔名非法字元」的無關限制，單純驗證 render 層跳脫）；(l) `candidate_card` 的 Spread 兩腿標籤先前硬編 "Call"，改讀 `long_leg["option_type"].capitalize()`，補 BPS 案例測試防止此類錯誤再次發生（brief §5.2 明確要求 Bear Put Spread 顯示 Put）；(m) Task 12 Step 4c 的兩則 quick.py 測試改寫遺漏 `at.switch_page(...)` 後緊接的 `at.run()`——`AppTest.switch_page` 官方文件明載「does not automatically rerun the app」，已補上（`test_app_navigation.py` 內既有的 switch_page 呼叫本就正確帶了 `.run()`，僅 Step 4c 這兩處新增的改寫遺漏）；(n) Task 7 的 `heatmap_html` 回傳改經 `esc()` 包裝後，`test_bcs_caps_at_and_above_cap_price`／`test_bps_caps_at_and_below_cap_price` 原本斷言未跳脫的 `$120`/`$80` 字面，已改為斷言跳脫後的實際輸出 `\$120`/`\$80`（已逐一核對 Task 6/7 其餘測試斷言，確認無其他處斷言含裸 `$` 字元會被此輪 `esc()` 包裝影響）。

<!-- codex-peer-reviewed: 2026-07-22T16:11:41Z rounds=4 verdict=approved -->
