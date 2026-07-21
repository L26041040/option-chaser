# Option Chaser v5 Design Spec — 多劇本工作區與腳本地基

日期：2026-07-21
狀態：待審
上游文件：`Brief_v3.md`（多劇本架構與交易腳本機器人地基）、v4 spec `2026-07-20-option-chaser-v4-design.md`（已實作、audit CONFORMANT）
本 spec 為 v4 之增量修訂；未提及處沿用既有 spec；衝突處以本文為準。

---

## 1. 目標與決議紀錄

### 1.1 目標

建立未來倉位配置（v6）與交易腳本引擎（v7）所需的持久化地基：劇本成為持久實體、分析結果成為機器可讀檔案、同標的多劇本有結構表達。**零配置、零下單、零自動化決策、零機率。**

### 1.2 已拍板決議（brainstorm 定案，審核時不再翻案）

1. **資金總額 v5 就輸入**（GUI 設定一次），結果檔與清單顯示「佔本金%」；不做任何配置建議。
2. **里程碑重評＝手動按鈕**：劇本標記 Reached 後，群組內下一個里程碑出現「重新分析」按鈕；零自動化。
3. **關係確認四選現在做**：里程碑路徑／獨立／互斥／暫不定義；未確認＝暫不定義＝引擎當獨立處理。
4. **群組檢視＝摘要列表**：每里程碑一列，點入 v4 四步詳頁；並排比較延後（v5.1 觀察後再議）。
5. 劇本上限軟限制 6（GUI 提示，schema 不設限）。
6. 儲存用 JSON 檔＋temp-rename 原子寫入（非 SQLite）：git-diffable、可審計、6 劇本量級足夠。
7. 機率紅線全面沿用 v4（禁詞清單、無 POP/期望值/Sharpe、無分數）；LLM 不進任何邏輯。
8. 不做：倉位配置、自動下單、自動狀態轉移（除 Expired 觀察式轉移）、跨標的關係、重新估值引擎、歷史模擬、蒙地卡羅。

---

## 2. 儲存層（新模組 `option_chaser/store.py`）

### 2.1 工作區佈局

```
workspace/                      ← 預設 ./workspace，可由參數覆寫；gitignore
  scenarios/<scenario_id>.json  ← 劇本定義（一檔一劇本）
  results/<scenario_id>/<snapshot_ts>.json   ← 分析結果（全量）
  groups.json                   ← 群組與關係
  constraints.json              ← v5 僅 {"total_capital": float|null}；其餘 schema 預留
  events.jsonl                  ← 全工作區 append-only 事件日誌
```

所有寫入一律 temp 檔＋`os.replace` 原子替換。所有讀寫 UTF-8。

### 2.2 Scenario 實體

```json
{
  "schema_version": 1,
  "id": "TLT-105-202801",
  "symbol": "TLT",
  "direction": "bullish",
  "target_price": 105.0,
  "target_date": "2028-01-01",
  "created_at": "2026-07-21T00:00:00Z",
  "notes": "",
  "group_id": "G-TLT",
  "status": "Active",
  "strategies": ["long-call", "bull-call-spread"]
}
```

- **id 規則**：`{symbol}-{target:g 且 '.'→'p'}-{yyyymm(target_date)}`；撞名追加 `-2`、`-3`（決定性）。
- **direction 為使用者輸入**（建立表單選看漲/看跌；預設依該 symbol 最近 snapshot 的 spot 推得，無 snapshot 則必選）。分析時既有方向守衛照舊（不合方向的策略 skipped_direction）。
- **status 僅 4 態**：`Active | Reached | Expired | Invalidated`。Draft 為 GUI 未存檔暫態不落盤；Partially Realized/Exited/Paused 需部位概念，v7 再加（status 是 string，加值不破檔）。
- **狀態轉移規則**：
  - 手動：Active→Reached、Active→Invalidated（GUI 按鈕，必附 reason）。
  - 觀察式自動：讀取工作區時若 系統日期 > target_date 且 status==Active → 追加事件並轉 Expired（observed_at 顯式入事件）。
  - 其餘轉移 v5 不存在；Reached/Expired/Invalidated 為終態（v5 內不可逆；改錯了刪劇本重建）。
- **狀態不可覆寫紅線**：scenario 檔中的 status 欄位是快取；每次變更必先 append 事件，再改快取；載入時驗證快取==事件投影（不一致→拋錯，測試鎖定）。

### 2.3 事件日誌（events.jsonl，每行一 JSON）

```json
{"ts": "2026-07-21T00:00:00Z", "scenario_id": "TLT-105-202801",
 "event": "STATUS_CHANGED", "payload": {"from": "Active", "to": "Reached", "reason": "手動標記", "by": "user"}}
```

v5 事件 enum（string，可擴充）：`SCENARIO_CREATED`、`STATUS_CHANGED`、`ANALYSIS_COMPLETED`（payload 含 result 檔路徑與 snapshot_ref）、`GROUP_RELATION_CONFIRMED`。
v7 預留 enum（本版僅文件與常數定義，不觸發）：`PRICE_REACHED`、`TARGET_DATE_ARRIVED`、`EXPIRY_BUFFER_LOW`、`LIQUIDITY_DEGRADED`、`REANALYSIS_REQUESTED`。

### 2.4 ScenarioGroup（groups.json）

```json
{
  "schema_version": 1,
  "groups": [{
    "id": "G-TLT",
    "symbol": "TLT",
    "members": ["TLT-105-202801", "TLT-115-202812"],
    "relations": [{
      "pair": ["TLT-105-202801", "TLT-115-202812"],
      "proposed": "milestone-path",
      "confirmed": "undefined",
      "confirmed_at": null
    }]
  }]
}
```

- **自動歸組**：same symbol → same group（`G-{symbol}`）；members 依 target_date 升冪、同日依 id 字典序（決定性）。
- **提案規則（確定性，零 LLM）**：相鄰兩劇本若 同 direction 且 目標價沿方向遞進（bullish：早者 target ≤ 晚者 target；bearish 鏡像）→ `proposed="milestone-path"`；同 direction 但價格反向 → `proposed="review-needed"`；不同 direction → `proposed="exclusive-candidate"`。
- **confirmed 四選**：`milestone-path | independent | exclusive | undefined`（預設）。確認即 append `GROUP_RELATION_CONFIRMED` 事件。
- **紅線：Group 是純 metadata**。分析永遠 per-scenario；v5 內任何計算不得讀取 relation（唯一使用處＝GUI 顯示與「重新分析下一里程碑」按鈕的顯示條件）。

### 2.5 constraints.json（v5 僅一欄生效）

```json
{"schema_version": 1, "total_capital": 100000.0}
```

其餘限制欄位（max_per_scenario_pct 等）v6 定義；v5 不預寫欄名（YAGNI），僅保留檔案與 schema_version。`total_capital` 可為 null（未設定→GUI 不顯示佔本金%、結果檔 pct 欄為 null）。

---

## 3. ScenarioResult 契約（results/<id>/<snapshot_ts>.json）

v4 `AnalysisResult` 的**全量 JSON 化**＋新增欄位。序列化函數 `store.serialize_result(result, scenario_id, capital) -> dict` 與 `store.save_result(...) -> path`；tuple→list、dataclass→dict、date→ISO 字串。

```
schema_version: 1                ← result 檔自有版本（獨立於 snapshot schema v2）
engine_version: "<option_chaser.__version__>"   ← 新增 __version__ = "0.5.0"
analyzed_at: ISO8601（取 snapshot fetched_at，非 wall-clock——決定性）
scenario_id / params(AnalysisParams 全欄) / snapshot_ref{path, fetched_at, source, spot}
capital_assumed: float|null      ← 分析當下 constraints.total_capital 的快照
data_quality: {
  fetched_at: ISO8601,
  all_quotes_filtered: bool      ← true 當「每個要求策略 status==empty 且
                                    報價異常 stage removed ≥ 1」；
                                    區分「市場無機會」vs「資料不可用（如盤前）」
}
results[]: per strategy —— status / message / n_qualified / filter_stages[{label, removed}]
  / pair_report / candidates[]:
    candidate_key / legs[{contract_symbol, option_type, strike, expiry, bid, ask,
                          iv, volume, open_interest}]
    mid_cost / natural_cost / baseline_pnl / baseline_return / natural_return
    scenario_vector{entries: [[code, ret]×7], worst_code, worst_return}
    completion_curve / completion_prices / completion_threshold / breakeven_at_target
    retention / friction / friction_amount / buffer_days / quote_warning
    theta_day_rate / vega_per_pt / decay_30d_return / net_delta
    breakeven / max_profit(nullable) / effective_leverage
    matrix{prices: [[value, label]], dates: [[iso, label]], cells}
    capital_per_contract: mid_cost×100          ← 新增
    max_loss_per_contract: mid_cost×100（debit 恆等於成本）← 新增
    pct_of_capital: capital_per_contract/capital_assumed 或 null  ← 新增
    days_to_target / days_to_expiry（自 result 的 today 起算）← 新增
  / report_text（原文保留）
expiry_groups / hidden_expiries / default_selection / comparison / best_strategy（v4 原樣）
today: ISO date（snapshot 推導，決定性）
```

- **決定性**：同 snapshot＋同 params＋同 capital → 序列化後逐位元相同（`json.dumps(..., sort_keys=True, ensure_ascii=False)`，浮點原值不四捨五入）。
- **新計算歸屬**：capital/max_loss/pct/days 四組欄位在 `store.serialize_result` 內計算（乘除法與日期差，非估值邏輯，不進 engine；GUI 僅格式化——零公式紅線延伸適用）。
- 讀取：`store.load_result(path) -> dict`（v5 回 dict 即可，不反序列化回 dataclass——消費者是未來引擎與 GUI 摘要）。

---

## 4. 工作區服務層（新模組 `option_chaser/workspace.py`）

介於 store 與 GUI 之間的編排層（不碰估值）：

- `create_scenario(ws_root, symbol, direction, target_price, target_date, notes, strategies) -> Scenario`：產 id、寫檔、append `SCENARIO_CREATED`、自動歸組（更新 groups.json 與提案）。
- `list_scenarios(ws_root)`：載入全部＋Expired 觀察式轉移＋快取/事件投影一致性驗證。
- `set_status(ws_root, id, to, reason)`：僅允許 §2.2 轉移表；append 事件＋更新快取。
- `confirm_relation(ws_root, group_id, pair, choice)`。
- `analyze_scenario(ws_root, id, progress) -> result_path`：組 AnalysisRequest（base_params 自 scenario 欄位；其餘 CLI 預設）→ `service.run`（線上）→ `store.serialize_result`＋`save_result` → append `ANALYSIS_COMPLETED`。
- `analyze_group(ws_root, group_id, progress) -> [result_path]`：**一次抓取共用 snapshot**——第一個成員走 `service.run`，其餘成員以同一 snapshot 走 `service.run_offline`（重用既有函數；service 需抽出 `fetch_and_save(symbol) -> (snap, path)` 供本函數與 `run` 共用——`run` 行為不變）。全體成員的 result 檔 snapshot_ref.path 必須相同（測試鎖定）。
- `latest_result(ws_root, id) -> dict|None`（依檔名 snapshot_ts 取最新）。
- 全部函數顯式收 `ws_root`；無全域狀態；引擎內不呼叫 wall-clock（Expired 觀察與 events ts 由呼叫端傳入或於 workspace 層取得並顯式入檔）。

---

## 5. GUI（多劇本工作區）

### 5.1 結構

- `webapp/app.py`：**現有 v4 四步快速分析視圖完全不動**（不落盤的即用即走模式）。四步結果渲染函數抽出為 `webapp/render.py`（純函數，收 AnalysisResult 或 result dict——內部統一走 dict 介面），app.py 與工作區頁共用。抽出屬重構：AppTest 既有測試必須全數不改而綠（渲染輸出不變）。
- 新頁 `webapp/pages/0_劇本工作區.py`：
  - **清單區**：每劇本一列——symbol／方向／目標價／目標日／狀態徽章／群組徽章／佔本金%（有最新 result 且 capital 設定時）／最新分析摘要（最佳候選＋劇本報酬＋情境最壞，取自 latest_result 的 default_selection）。＞6 個劇本時頂部軟提示。
  - **建立表單**：symbol／方向（預設自動推）／目標價／目標日／備註／策略勾選（預設 LC+BCS 看漲、LP+BPS 看跌）。
  - **群組區**：每群組一卡；里程碑摘要列表（狀態／最佳候選／劇本報酬／情境最壞／緩衝）；相鄰關係顯示 proposed 並提供四選確認；成員列「分析」「群組分析」按鈕；**「重新分析」按鈕僅在前一里程碑 status==Reached 時對下一里程碑顯示**。
  - **詳頁**：點任一列 → 以 `render.py` 渲染該劇本 latest_result 的完整四步視圖（與 v4 相同）。
  - **設定區**：total_capital 輸入（寫 constraints.json）。
  - 狀態操作：Active 劇本提供「標記達成」「標記失效」（附 reason 欄）。
- 說明頁增補一節：工作區三概念（劇本/群組/里程碑）與狀態意義；辭典增詞：劇本群組、里程碑、狀態、佔本金%、資料品質。

### 5.2 紅線（沿用＋延伸）

- GUI 零金融公式（佔本金%、天數等全部由 store 預算入 result；GUI 僅格式化）。
- 機率禁詞清單掃描範圍擴至 `option_chaser/store.py`、`option_chaser/workspace.py`、`webapp/render.py`、`webapp/pages/0_劇本工作區.py`（新檔案無裸詞「機率」）。
- 無分數欄位/函數；狀態轉移全部可審計；Group 不進分析。

---

## 6. State/Event/Action 詞彙表（文件＋常數，零引擎）

- `option_chaser/vocabulary.py`：`SCENARIO_STATUSES`、`EVENT_TYPES`（v5 生效 4 種＋v7 預留 5 種，註明）、`ACTION_TYPES`（11 種，v5 全部僅文件用途）。常數為 tuple[str]；store/workspace 寫事件時必須用本模組常數（測試鎖定：events.jsonl 內不得出現詞彙表外的 event 值）。
- `docs/superpowers/specs/` 本 spec §6 即詞彙表權威；README 補「多劇本工作區」章節。

Action 詞彙（純文件）：`HOLD / OPEN / ADD / REDUCE / CLOSE / RECOVER_PRINCIPAL / KEEP_RUNNER / ROLL_TO_NEXT_MILESTONE / SWITCH_SCENARIO / HOLD_CASH / RERUN_ANALYSIS`。

---

## 7. 測試（增量）

1. **store 單元**：Scenario round-trip（寫→讀→相等）；id 決定性與撞名 `-2` 追加；原子寫入（temp+replace，寫入中斷不留半檔——以「temp 檔命名規則＋replace 呼叫」單元鎖定）；constraints null/set 兩態。
2. **事件與狀態**：每種合法轉移 append 事件＋快取一致；非法轉移拋錯（Reached→Active 等）；快取被手改後載入偵測不一致拋錯；Expired 觀察式轉移（傳入日期跨過 target_date）append 事件。
3. **群組規則矩陣**：同 symbol 自動歸組；members 排序決定性；提案三分支（milestone-path／review-needed／exclusive-candidate，含 bearish 鏡像案例）；四選確認寫入＋事件；undefined 語意（無任何行為影響）。
4. **serialize_result**：對 fixture 快照分析結果——全欄位 round-trip；決定性（兩次序列化逐位元同）；pct_of_capital 有/無 capital 兩態；capital/max_loss/days 與手算相等；data_quality.all_quotes_filtered 兩態（用 all-warning fixture 變體構造全空案例：所有合約 bid/ask 置 0）；schema_version/engine_version 存在。
5. **workspace**：create→list→analyze（offline 注入：analyze_scenario 收 optional snapshot_path 測試鉤，走 run_offline）→ latest_result 鏈路；analyze_group 共用 snapshot（兩成員 result 的 snapshot_ref.path 相同）；事件序完整（CREATED→ANALYSIS_COMPLETED）。
6. **render 抽出重構**：既有 test_webapp / test_webapp_v4 全數不改而綠（渲染不變的硬證據）。
7. **工作區 GUI（AppTest）**：建立劇本→列表出現；狀態按鈕轉移＋reason；群組卡與四選確認；「重新分析」按鈕僅於前一里程碑 Reached 時出現；capital 設定後佔本金%顯示；詳頁渲染四步結構。
8. **紅線掃描**：禁詞清單擴 4 新檔；新檔無裸詞「機率」；events.jsonl 值域鎖定（詞彙表外值拒寫）。
9. **既有回歸**：v4 全套件 177 tests 不動全綠。

## 7A. 審計覆蓋契約（codex-audit，設計期凍結）

- **DC**：乾淨安裝；store/workspace/vocabulary/render import；工作區目錄自動建立；3.11/3.13 corner；JSON schema 檔案 parse。
- **AC**：全套件 codex 親自跑；result 序列化獨立驗證（codex 載入 result JSON，抽 ≥3 個數值欄位以引擎原語重算比對，另驗 capital/pct/days 手算）；事件投影獨立重放（codex 以 events.jsonl 重建狀態比對快取）；群組提案規則矩陣重現（含 bearish 鏡像）；id 撞名決定性；決定性雙跑逐位元；紅線掃描（擴充範圍）；v4 回歸全綠。
- **SL**：真實多劇本流程——live 建立 TLT 105/2028-01 與 TLT 115/2028-12 兩劇本 → 自動歸組＋milestone-path 提案 → 群組分析（驗證兩 result 檔引用同一 snapshot 檔）→ 清單/群組摘要渲染 → 標記第一個 Reached → 「重新分析」按鈕出現 → live 重跑第二劇本；result 檔重載一致；Docker 容器內載入主機工作區重算 parity（結構同一＋使用者可見精度，跨 libm 漂移依 v4 判例 <1e-12 接受）。無法執行處依 skill 處方模式，不得豁免。

---

## 8. 驗收案例

1. 建立 TLT 105/2028-01（看漲）與 TLT 115/2028-12（看漲）→ 自動同組、提案 milestone-path、依日期排序。
2. 群組分析一鍵：兩劇本共用同一份新 snapshot；各自 result 檔落盤且含全部 §3 欄位。
3. 設定 total_capital=100000 → 清單顯示每劇本最佳候選佔本金%；result 檔 pct_of_capital 非 null。
4. 標記第一劇本 Reached（附 reason）→ events.jsonl 兩行新事件（STATUS_CHANGED）→ 第二劇本出現「重新分析」按鈕 → 點擊後產生新 result 檔（新 snapshot）。
5. 手改 scenario 檔 status 為不一致值 → 載入報錯（審計性）。
6. v4 快速分析視圖行為與輸出與 v5 前完全相同（回歸＋AppTest 不改而綠）。
7. 全輸出無機率語彙；無分數；Group 未進任何計算路徑。

---

## 9. 明確不做（v5）

倉位配置與任何建議、自動下單、自動狀態轉移（除 Expired 觀察式）、跨標的關係、LLM 任何介入、重新估值引擎、歷史模擬、蒙地卡羅、Policy 引擎、並排里程碑比較（v5.1）、劇本編輯（v5 建立後唯讀，改錯刪除重建；Partially Realized/Exited/Paused 狀態）、多使用者/併發寫入。
