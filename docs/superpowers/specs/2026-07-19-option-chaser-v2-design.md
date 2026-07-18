# Option Chaser v2 Design Spec — 矩陣引擎 + 四策略 + Buffer 退役

日期：2026-07-19
狀態：待審
上游文件：`product_brief_v1.md`、v1 spec `2026-07-15-option-chaser-mvp-design.md`（已實作並通過 codex-audit）
本 spec 為 v1 的增量修訂：未提及之處沿用 v1 spec 原文；凡與 v1 衝突處以本文為準。

---

## 1. 產品重定位與範圍

### 1.1 重定位

v1 是「情境點估計 + 推薦」。v2 升級為「**價格×時間全景計算 + 多組合比較引擎**」，對標 optionsprofitcalculator.com 的矩陣體驗（指定價格區間 × 時間區間的 P/L 表），補上該網站做不到的：自動掃鏈、多組合同場排名、價差全配對窮舉。

使用者劇本（目標價 + 目標日）保留唯一用途：**排名錨點**（候選排序需要單一數字）。其餘認知功能全部由矩陣承載。

### 1.2 v2 範圍（本輪 brainstorming 定案）

1. `--strategy {long-call | long-put | bull-call-spread | bear-put-spread}`，預設 `long-call`（v1 行為向後相容）。一次執行一種策略。
2. 全部為借方（debit）策略：最大虧損 = 付出權利金，v1 風險哲學不變。
3. P/L 矩陣引擎（§5）：每個級距首選附完整矩陣；`--matrix-all` 全開。
4. Buffer 機制退役（§1.4）。
5. 快照 schema v2：calls + puts 都存（§6）。

### 1.3 已討論並否決（審核時不再翻案）

- **貸方策略**（credit spread、裸賣）：涉及保證金/指派風險模型，留 v3。
- **股利調整 q**：與使用者完整討論量化影響後（TLT 案例 call 殘值差約 15%），使用者明確決策維持 q=0。偏誤方向於尾註揭露：call 殘值偏樂觀、put 殘值偏保守，高殖利率標的最明顯。
- **全混合排名**（單腿與價差同池排序）：Delta 分級對價差無風險語意，否決。
- **多標的同場比較**：留未來版本。

### 1.4 Buffer 機制退役（brief 硬性限制之修訂）

v1 的 `--min-days-after`、`effective_buffer`、`--delay-days` 與三個壓力測試（半程/延遲/全錯）**整組移除**。理由：

- 使用者自行管理到期日緩衝（工作流中 buffer 在選定劇本前已抓定）。
- 三個壓力測試全是矩陣的特例：半程 = 價格軸中段列、全錯 = 現價列、延遲 = 劇本日之後的日期欄。矩陣資訊量嚴格較大。
- brief §4.5「不得因短天期表面報酬繞過使用者到期日安全緩衝」隨功能退役：使用者不再透過本工具表達 buffer，該限制無保護對象。本段即為 brief 層級變更的正式紀錄。

**保留的結構性底線**：`expiry ≥ target_date`（合約必須活到劇本兌現日——數學要求，非保護機制）。`--min-expiry` 保留為選用過濾器。

---

## 2. 使用者輸入（§3 取代 v1 對應表）

| 參數 | 必填 | 意義 | 驗證 |
|---|---|---|---|
| `symbol` | 是 | 美股代號 | 非空字串（v1 audit 修正沿用） |
| `--strategy` | 否，預設 `long-call` | 策略 | 四值其一 |
| `--target-price` | 是 | 劇本目標價（排名錨點） | > 0；方向檢查見下 |
| `--target-date` | 是 | 劇本到達日（排名錨點） | 晚於今天；YYYY-MM-DD |
| `--min-expiry` | 否 | 到期日絕對下限 | YYYY-MM-DD |
| `--top` | 否，預設 3 | 每級距（單腿）/清單（價差）候選數 | 1–10 |
| `--iv-shifts` | 否，預設 `-0.2,0,0.2` | 同 v1 | 同 v1（0 強制包含） |
| `--rate` | 否，預設 0.04 | 無風險年利率 | ≥ 0 |
| `--min-oi` / `--min-volume` / `--max-spread-pct` / `--spread-floor` / `--delta-bands` / `--min-return` / `--force` / `--snapshot` / `--md` | 同 v1 | 同 v1 | 同 v1 |
| `--matrix-all` | 否 | 所有候選都附矩陣 | 布林旗標 |

**移除**：`--min-days-after`、`--delay-days`（傳入須為 argparse 未知參數錯誤，不得靜默忽略）。

**方向檢查**（取代 v1 的單向 force 規則）：

- `long-call`、`bull-call-spread`：`target_price ≤ spot` → 警告並要求 `--force`。
- `long-put`、`bear-put-spread`：`target_price ≥ spot` → 警告並要求 `--force`。

---

## 3. 估值（增量）

### 3.1 Put 定價與 Greeks（教科書標準，鏡像 call）

```
P = K·e^(−rT)·N(−d2) − S·N(−d1)      （d1/d2 同 v1 定義）
T ≤ 0 分支：P = max(K − S, 0)
Delta_put = N(d1) − 1（∈ (−1, 0)）；Gamma、Vega 與 call 同式
Theta_put(年) = −(S·φ(d1)·σ)/(2√T) + r·K·e^(−rT)·N(−d2)，每日 ÷365
```

### 3.2 美式內在價值鉗制（新規則，v1 未有）

**所有估值輸出**（劇本估值、矩陣格值、L1/L2、到期前任一時點）一律取：

```
value = max(BS 估值, 當下內在價值, 0)
```

理由：歐式 BS 深價內 put 會低於內在價值（K 折現所致），但美式選擇權市價有 `≥ 內在價值` 的無套利下限。call 在 r ≥ 0 時 BS ≥ 內在價值恆成立，鉗制無作用但統一套用（分支更少、決定性不變）。此規則必須有單元測試（深價內 put 觸發鉗制的案例）。

### 3.3 價差估值

- 兩腿同到期日；每腿用自己的市場 IV；`V_spread = V_長腿 − V_短腿`（各腿先過 §3.2 鉗制），再整體鉗制到 `[0, 寬度]`（垂直價差無套利界）。
- 到期時點（矩陣末欄）直接用 payoff：`clamp(方向化內在價值差, 0, 寬度)`。
- 進場成本：基準 = 長腿 Mid − 短腿 Mid；最差 = 長腿 Ask − 短腿 Bid。成本 ≤ 0 或 ≥ 寬度的組合於配對階段淘汰（§4.2）。

### 3.4 各策略錨點公式（Breakeven / 保守底線 / 買價指引）

| 策略 | Breakeven | 保守底線（劇本日） | L1 硬上限 |
|---|---|---|---|
| long-call | K + Mid | max(target − K, 0) | 同保守底線 |
| long-put | K − Mid | max(K − target, 0) | 同保守底線 |
| bull-call-spread | K_low + 淨Mid | min(max(target − K_low, 0), 寬度) | 同保守底線 |
| bear-put-spread | K_high − 淨Mid | min(max(K_high − target, 0), 寬度) | 同保守底線 |

- 對目標價緩衝：call 族 = `(target − BE)/target`；put 族 = `(BE − target)/target`（正值 = 劇本兌現仍獲利）。
- L2 = 最保守 IV 情境（`min(iv_shifts)`）的劇本日估值（含 §3.2/§3.3 鉗制）；L3 = 基準估值 ÷ (1 + min_return)。恆等式 `L1 ≤ L2 ≤ 基準` 在鉗制後對四策略皆成立，測試以固定參數矩陣驗證。
- 價差另有天花板提示：淨成本恆 < 寬度（無套利）；`Ask 口徑成本 ≥ 寬度` 的組合已於配對階段淘汰，不會出現在報告。
- Lambda：單腿 = |Delta|·spot/Mid；價差 = |淨Delta|·spot/淨Mid（純診斷，尾註註明淨 Delta 對價差僅供量級參考）。

---

## 4. 過濾與候選生成

### 4.1 單腿（call 或 put，依策略選邊）

v1 五道硬過濾原封沿用，第 1 道改為：`expiry ≥ target_date` 且（若給定）`expiry ≥ min_expiry`。volume=0 新鮮度警示沿用。

### 4.2 價差三段式（本輪定案：過濾式粗掃 + 全配對窮舉）

1. **腿粗掃**：候選腿先過 §4.1 五道過濾（不合格的腿不可能出現在最優組合——這就是「最優解區間」的嚴謹版）。
2. **全配對窮舉**：合格腿中同到期日兩兩配對（bull-call：K_low 買 / K_high 賣；bear-put：K_high 買 / K_low 賣）。計算量評估：過濾後每到期日 10–40 檔 → 全標的合計 < 1 萬組，每組 2 次 BS，Python < 1 秒，窮舉零漏解。
3. **配對健全檢查**：淘汰 `淨Mid成本 ≤ 0`、`淨Ask口徑成本 ≥ 寬度`（報價異常/無利可圖組），計入 FilterReport 新增的「配對統計」段（配對總數 → 健全性淘汰 → 合格組數）。

### 4.3 分級與排名

- 單腿：以 `|Delta|` 分三級距，門檻沿用 0.35/0.65（深價內 put = 類現貨空頭替代，實務語意成立）。級內以基準情境報酬率（Mid 進場）降冪，tie-break 沿用 v1 四層全序。
- 價差：**不分級**，單一清單依基準情境報酬率降冪取 `top`，tie-break：合計 spread%（兩腿 (ask−bid) 之和 ÷ 淨Mid）→ 長腿 strike → expiry → 長腿 contract_symbol。
- 推薦理由模板（確定性）：
  - put 保守型優點：「breakeven 僅低於現價 X%，劇本半對仍獲利」。「半對」的確定性定義（call/put 通用，僅用於理由模板）：半程價 = spot ± 0.5×|target − spot|（往目標方向取半），於 target_date 的估值（含鉗制）> Mid 即成立；積極型/平衡型鏡像 v1。
  - 價差優點：「劇本成立時報酬率 X%（合格 N 組中第 k）」；代價固定規則：「獲利上限 = 寬度 − 淨成本 = $X（目標價以上的漲幅不參與）」+ 合計 spread% 警示（門檻同 v1 的 2/3 規則）+ 買價指引警句。

---

## 5. P/L 矩陣引擎（`option_chaser/matrix.py`，新模組）

### 5.1 軸生成（純函數，決定性）

- **價格軸（11 列，由高至低顯示）**：範圍 `[min(spot, target) − pad, max(spot, target) + pad]`，`pad = 0.10 × spot`。先生成 11 個等距格點，再以「最接近者替換」植入精確 `spot`（標 `<現價>`）與精確 `target`（標 `<目標>`）。替換演算法確定性（距離同分取較低格點）。
- **日期軸（7 欄）**：`今天 → expiry` 日曆日等分（含兩端），再以最接近者替換植入精確 `target_date`（標 `*`）。末欄恆為 expiry。
- 兩軸皆為 snapshot + params 的純函數；同輸入逐位元同輸出。

### 5.2 格值

- 非末欄：`value(S_row, t_col)` = 該策略估值（§3，含鉗制），IV 按各腿快照值恆定（尾註揭露此限制）。
- 末欄（expiry）：到期 payoff（單腿內在價值 / 價差 clamp 後 payoff 差）。
- 顯示：報酬率 %（Mid 進場），格式 `{:+.0f}%`，固定欄寬；列首為價格 `{:.2f}`；欄首為 `MM/DD`。禁 box-drawing。

### 5.3 放置

- 預設：單腿三級距各自 #1、價差清單 #1 附完整矩陣；其餘候選精簡區塊。
- `--matrix-all`：所有列出候選都附。

---

## 6. 資料層

- `schema_version: 2`。`contracts[]` 每筆新增 `option_type: "call" | "put"`；抓取時 calls 與 puts 都存。
- 載入 schema 1 快照：明確報錯「快照為 v1 格式（僅含 call），請重新抓取」，exit code 1。不做遷移（快照為短效市場資料）。
- `data/yf.py`：`option_chain(expiry)` 的 `.calls` 與 `.puts` 都對映；清洗規則不變。
- golden fixture 重製：v2 格式快照一份（含 call+put、各過濾情境、價差健全性淘汰案例），四策略 golden 各一。

---

## 7. 報告

結構：標頭（含策略名）→ 過濾統計（單腿五道；價差另加配對統計段）→ 候選區（首選含矩陣，§5.3）→ 尾註（公式全列，含 put/價差公式、鉗制規則、q=0 與 IV 恆定之限制揭露、免責）。

**刪除**：壓力測試區（矩陣取代）。其餘 v1 格式紀律不變（每股+每張並列、估值+損益+報酬率三件套、決定性數字格式、手機可讀）。

---

## 8. 錯誤處理與決定性

v1 §8 全部沿用（exit 0/1/2、快照衍生「今天」、純函數、逐位元決定性）。新增：schema 1 快照 → exit 1 與提示；`--min-days-after`/`--delay-days` → argparse 未知參數錯誤（exit 2）。

---

## 9. 測試（增量；v1 既有測試除壓力測試/buffer 相關者外全保留）

1. **Put BS**：教科書已知值（Hull S=42,K=40,T=0.5,r=0.10,σ=0.20 → P≈0.81）；put-call parity 沿用；T≤0 → 內在價值；深價內歐式 put < 內在價值時 §3.2 鉗制生效的專屬案例。
2. **Put Greeks**：Delta ∈ (−1,0)；已知值驗證。
3. **價差估值**：`[0,寬度]` 鉗制；到期 payoff 正確；同 IV 下寬度單調性。
4. **配對生成**：組合數正確；健全性淘汰計數正確（構造 淨成本≤0 與 ≥寬度 案例）。
5. **|Delta| 分級**：put 邊界值歸屬；四策略方向驗證 × force 全矩陣。
6. **矩陣**：軸決定性（同輸入連跑兩次逐位元同）；spot/target 列為精確值且標記正確；末欄 = payoff；任取 3 格與直接 BS 呼叫比對；`--matrix-all` 行為。
7. **買價指引恆等式**：四策略 × 固定參數矩陣，`L1 ≤ L2 ≤ 基準`（鉗制後）。
8. **Golden × 4 策略**：v2 fixture 快照 + 固定參數 → 逐字元相等；含決定性重跑。
9. **Schema**：v2 round-trip；v1 快照載入報錯訊息與 exit code。
10. **yf adapter**：puts 對映 fixture 測試（mock，不碰網路）。
11. **CLI**：移除旗標傳入 → argparse 錯誤；v1 audit 新增之空 symbol 測試沿用。

## 9A. 審計覆蓋契約（codex-audit v2 規格，設計期凍結）

- **DC**：乾淨環境安裝；schema 2 fixture 解析；四策略模組 import；Python 3.11/3.13 corner（v1 曾在 3.13 崩潰，永久列管）。
- **AC**：codex 親自跑全套件；marching walk = 四策略各自的 {exit codes, 空級距/空清單, 天花板觸發/不觸發, 方向 force 檢查}；put-call parity 恆等式；價差 [0,寬度] 恆等式；矩陣軸決定性與特殊列（spot 列、target 列、expiry 欄 = payoff）；v2 golden 四份；邊界 checkerboard（|Delta| 恰 0.35/0.65、NaN、空 symbol、tick-bound spread）。
- **SL**：真實 API 全鏈路至少兩次——看漲家族一次（long-call 或 bull-call-spread）、看跌家族一次（long-put 或 bear-put-spread）；每次驗證報告產出、snapshot 落地、離線重跑逐位元一致。無法連網時依 skill 之處方腳本模式執行，不得豁免。

---

## 10. 未來擴充（不在 v2）

貸方策略與保證金模型；股利調整（本輪已否決，未來重議須帶新論據）；CSV/HTML 熱力圖匯出；多標的同場比較；IV 曲面/期限結構。

---

## 11. 驗收案例

TLT 現價 84.52，劇本 2027-12-31 到 110：

1. `--strategy long-call`：合格單腿分三級距，各級首選附 11×7 矩陣；矩陣 `<目標>` 列 × `*` 欄的格值與劇本估值一致；expiry 欄 = 內在價值。
2. `--strategy bull-call-spread`：全配對窮舉後 top-3 清單，榜首附矩陣；每組顯示兩腿明細/淨成本/最大獲利/寬度/BE；無任何組淨成本 ≥ 寬度。
3. `--strategy long-put --target-price 70`（看跌劇本）：方向檢查通過，put 三級距輸出；`--target-price 110` 時要求 `--force`。
4. 傳入 `--min-days-after 45` → argparse 錯誤退出（機制已退役）。
5. 同快照同參數重跑任一策略 → 報告逐位元相同。
