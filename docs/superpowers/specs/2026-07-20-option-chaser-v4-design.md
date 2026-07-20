# Option Chaser v4 Design Spec — 情境韌性引擎 + 到期日分組比較 + 流程化 GUI

日期：2026-07-20
狀態：待審
上游文件：OC-BRAINSTORM-001 頭腦風暴決議（四輪，含 mockup v1→v4 迭代）、v3 spec `2026-07-19-option-chaser-v3-gui-design.md`（已實作並通過 codex-audit）
介面權威：mockup v4（claude.ai artifact `e30c61ff`，使用者逐版確認）
本 spec 為 v3 之增量修訂；未提及處沿用既有 spec；衝突處以本文為準。

---

## 1. 目標與決議紀錄

### 1.1 目標

從「報酬排行工具」升級為「報酬與風險交換分析器」：每個候選附 7 個透明壓力情境的韌性向量；比較表按到期日分組（組內＝該到期日購物清單、組間＝時間階梯）；GUI 依使用流程重排（劇本→主圖→比較→進階）；輸入四項維持不變。

### 1.2 已拍板決議（brainstorm 定案，審核時不再翻案）

1. 比較表：**單一表格按到期日分組**（mockup v4 結構），取消雙 tab / 分策略卡片制。
2. 標章僅 🚀最高報酬、🛡️最強韌性 兩枚；**⚖️最佳折衷不做**（knee 演算法皆含隱形權重）。**💧最好成交不做**——改為反向警示 ⚠（見 §4.4）。
3. 韌性 = **7 情境取最壞（maximin）**，只用於 🛡️ 標章與「情境最壞」欄；**不做任何加權平均／分位數**（等權平均＝偷渡均勻分布）。
4. **不做任何安全分數**（單一或雙分數皆否決）；不做 Pareto knee 自動標。
5. **禁止機率語彙**：POP／Expected Profit／Sharpe／CVaR／「獲利機率」不得出現；Heatmap 覆蓋率指標不做。
6. 延遲容忍採**離散情境（晚30／90天）**，否決「最大容忍天數」求根（隱藏路徑假設的假精確）。
7. 主視圖預設顯示「**無⚠警示的最高劇本報酬候選**」；全部候選都有⚠時退回全場第一並保留⚠。
8. 「最差進場報酬率」正名為「**Natural 成交報酬**」（全 GUI／CLI／說明一致）。
9. 說明頁＋名詞懸浮辭典**納入 MVP**；辭典單一來源同時餵懸浮提示與說明頁。
10. Rho 不顯示；Gamma 每$100標準化僅入詳細頁且標「實驗欄位」（v4.1，MVP 不做）。
11. v3.1 UI 修補（$ 符 LaTeX 轉義、表單摺疊、手機表格）併入本版。
12. 輸入維持四項極簡；GUI 零金融公式紅線不變。

---

## 2. 情境韌性引擎（service 層新模組 `option_chaser/scenarios.py`）

### 2.1 七情境定義（全部沿用既有估值原語，零新定價模型）

對每個候選（單腿或價差），以 Mid 口徑計算：

| 代號 | 名稱 | 定義 |
|---|---|---|
| S1 | 不漲 | S=spot，估值日=target_date，基準 IV |
| S2 | 半程 | S=完成度50%價位，估值日=target_date，基準 IV |
| S3 | 大半程 | S=完成度75%價位，同上 |
| S4 | 晚30天 | 價格沿線性路徑於 target_date+30 到達 target（§2.2），基準 IV |
| S5 | 晚90天 | 同上，+90 |
| S6 | IV最保守 | S=target，估值日=target_date，σ 用 min(iv_shifts) 情境 |
| S7 | Natural成交 | S=target，估值日=target_date，基準 IV，成本=Natural（單腿=Ask；價差=長Ask−短Bid） |

- 完成度 k 的價位：`S_k = spot + k×(target − spot)`（看跌自動鏡像，同式即可——target<spot 時方向自帶）。
- 每情境報酬 = (該情境估值 − 成本)/成本；S7 成本為 Natural，其餘為 Mid。
- **情境最壞報酬 `worst_return` = min(S1..S7)**。
- 估值一律經既有 `scenario_leg_value`／`spread_scenario_value`（含美式鉗制與 [0,寬度] 鉗制）。

### 2.2 延遲情境的路徑約定（公開假設）

到達日 `arrive = target_date + Δ`（Δ∈{30,90}）。估值日 `d = min(arrive, expiry)`。估值日價格：

```
S(d) = spot + (target − spot) × (d − today) / (arrive − today)      （線性內插）
```

`d == arrive` 時 S=target（原語意）；`expiry < arrive` 時合約死在半路，以內插價於到期日算 payoff。此線性路徑為模型假設，說明頁與尾註必揭露。

### 2.3 目標日保本價與完成度門檻（`scenarios.py`）

- `breakeven_at_target(candidate, p) -> float | None`：bisection 求 `value(S, target_date, 基準IV) − Mid成本 = 0` 之 S。
  - 單調性：long call／bull-call-spread 對 S 嚴格遞增；long put／bear-put-spread 嚴格遞減——根唯一。
  - 搜尋區間 `[0.01, 2×max(spot, target, 各腿strike)]`；兩端同號＝區間內無根 → None。
  - 迭代 80 次或 |f|<1e-9；純函數、決定性。
- 完成度門檻 `completion_threshold = (BE − spot)/(target − spot)`（看跌鏡像 `(spot − BE)/(spot − target)`）。
  - 顯示語意：`≤0` → 「0%（已保本）」；`(0,1]` → 百分比；`>1` → 「>100% ⚠」；`BE=None` → 「— ⚠無法保本」。不鉗制數值，只規範顯示。
- 完成度報酬曲線：k∈{0,0.25,0.5,0.75,1} 五點（k=0 即 S1；k=1 即基準）。
- 不漲保留率 `retention = 1 + S1報酬`（顯示為百分比）。
- 成交摩擦 `friction = (Natural − Mid)/Mid`；顯示上限 999% 並並列絕對金額；`>25%` 觸發 ⚠。

---

## 3. Service 契約增量

### 3.1 CandidateView v4 新欄位

```python
@dataclass(frozen=True)
class ScenarioVector:
    entries: tuple[tuple[str, float], ...]   # (("S1", ret), ... ("S7", ret)) 固定順序
    worst_code: str                          # 最壞情境代號
    worst_return: float

# CandidateView 追加：
    scenario: ScenarioVector
    completion_curve: tuple[tuple[float, float], ...]  # ((0.0, ret), (0.25, ret) ... (1.0, ret))
    completion_threshold: float | None       # None = 無法保本
    breakeven_at_target: float | None
    retention: float                         # 不漲保留率（1 + S1）
    friction: float
    buffer_days: int                         # expiry − target_date
    quote_warning: bool                      # 任一腿 volume==0 或 friction > 0.25
```

### 3.2 比較結構改版：到期日分組

```python
@dataclass(frozen=True)
class ExpiryGroupRow:
    strategy: str
    candidate: CandidateView                 # 完整物件（含縮圖所需 matrix）
    badges: tuple[str, ...]                  # 子集 {"top_return","top_resilience","warning"}

@dataclass(frozen=True)
class ExpiryGroup:
    expiry: str
    buffer_days: int
    rows: tuple[ExpiryGroupRow, ...]         # 該到期日各策略最佳（依劇本報酬）
    hidden_count: int                        # 該到期日未展示的其餘合格候選數

# AnalysisResult 追加：
    expiry_groups: tuple[ExpiryGroup, ...]   # 依到期日升冪
    hidden_expiries: tuple[str, ...]          # 抽樣未展示的到期日（MVP 僅顯示數量）
    default_selection: tuple[str, str] | None  # (expiry, 候選識別) 主視圖預設
```

- 組內 rows：每策略取「該到期日中劇本報酬最高者」（tie-break 沿用各策略既有全序），依劇本報酬降冪。
- **到期日抽樣**：合格到期日 ≤4 → 全取；>4 → 最近（≥target_date）2 個全取＋其餘按日曆等距抽樣補至 4 組。抽樣規則決定性（等距索引取整，同分取較早）。
- 標章判定（全場範圍，跨組）：
  - `top_return`：全體合格候選中劇本報酬最高者。
  - `top_resilience`：worst_return 最高者（同分 → 劇本報酬高者 → 各策略 tie-break）。
  - `warning`：quote_warning 為真的列。
- `default_selection`：無 warning 的劇本報酬最高者；全員 warning → 全場第一。
- 既有 `comparison`/`best_strategy` 欄位保留（CLI 與舊測試相容），GUI 改用 expiry_groups。

### 3.3 韌性計算歸屬

全部在 service/scenarios 層（引擎函數呼叫的編排）；GUI 僅格式化（紅線沿用 v3：零金融公式）。

---

## 4. GUI 重構（`webapp/app.py`，依 mockup v4）

### 4.1 Step 1 劇本列

結果出現後輸入表單自動摺疊為 chips 列（標的/現價/目標(±%)/日期/策略/✎ 修改鈕展開表單）。

### 4.2 Step 2 主視圖（只放熱力圖）

- 僅一張選中候選的完整 heatmap；無讀數卡、無其他摘要。
- 標題列：候選名（含策略縮寫之懸浮解釋）。
- 左軸＝純價格數字；錨點列（超標／目標／現價／深跌）**粗體**，圖下註腳說明粗體意義。無圖標。
- 〔Natural 口徑切換〕不做（v4.1）。

### 4.3 熱力圖價格軸 v4（matrix.py 修訂，CLI/GUI 同源）

- 錨點集擴充為 4 個：`{spot, target, overshoot, adverse}`，其中
  `overshoot = target×1.10（看漲）／target×0.90（看跌）`、
  `adverse = spot×0.90（看漲）／spot×1.10（看跌）`。
- 範圍 `[min(錨點), max(錨點)]`（±10% 錨點即邊界，取代原 pad）；正值下限鉗制 `max(lo, 0.01×spot)` 沿用。
- 仍 11 列；防碰撞「移除最近格點＋插入錨點」演算法沿用（錨點升冪逐一處理，去重）。
- **CLI 矩陣同步採用新軸**（同源原則）→ 四份 golden 於本版重生成（§8）。

### 4.4 Step 3 比較表（單一表格，按到期日分組）

- 結構：`expiry_groups` 渲染；組標題列＝`{expiry} 到期（緩衝 +N 天）— {特性註記}`；特性註記為固定規則文案：緩衝 <45 天「收斂完全、容錯最低」；45–180「中庸帶」；>180「收斂不完全、容錯最高」。
- 欄位：標章｜組合｜縮圖｜劇本報酬｜情境最壞｜不漲保留率｜摩擦。
- 縮圖：該候選 heatmap 的純色塊迷你網格（自 MatrixView.cells 降採樣為 5×4：價格取 [10,7,4,1] 索引列、日期取 [0,~1/4,~1/2,~3/4,末] 五欄，色彩函數同 cell_color、無數字）。降採樣規則固定、決定性。
- 標章渲染：🚀（top_return）、🛡️（top_resilience）、⚠（warning，附懸浮原因：零成交腿／摩擦超標）、◀（目前選中）。
- 列點擊 → Step 2 主視圖切換至該候選（Streamlit 以每列按鈕實作）。
- 組尾顯示「＋此到期日其他 N 個候選」（純文字計數，展開為 v4.1）。
- 手機：欄寬受控（縮圖固定寬、數字欄 tabular），外層 overflow-x。

### 4.5 Step 4 進階區（預設收合的三個 expander）

1. **韌性與壓力情境**：選中候選的 7 情境向量表（最壞列紅底 + ◀標記）＋完成度報酬曲線表（0/25/50/75/100%，含各點價位）＋保本門檻一行（門檻%＋保本價）。
2. **報酬×韌性散點**：全體合格候選；Y=劇本報酬、X=情境最壞、色=策略、點大小=Mid成本；Pareto 前緣連線；被支配點淡化不刪；🚀🛡️點標記。自產 SVG（沿用零外部圖表庫原則）。
3. **Greeks 與流動性**：Net Delta（價差弱語意警語）、Θ日耗率（|NetΘ|/成本，加速警語）、Vega/1pt（NetVega×0.01/成本）、兩腿 OI/Volume、摩擦、30天純時間衰減情境（S=spot、IV 不變、today+30 估值）。原始文字報告（report_text）保留於此。

### 4.6 說明頁與名詞辭典

- `webapp/` 增加說明分頁（Streamlit multipage：`webapp/pages/1_說明.py` 或單頁內 tab——實作擇一，plan 定案）：三步教學（寫劇本／看主圖／比候選，文案照 mockup）＋完整名詞表＋三條免責＋模型假設（q=0、IV 恆定、線性延遲路徑、歐式+鉗制）。
- 名詞辭典：`option_chaser/glossary.py` 單一 dict `GLOSSARY: dict[str, str]`（名詞→白話解釋），GUI 懸浮提示（HTML title 屬性／st.help）與說明頁名詞表皆由它生成。CLI 不使用。
- 必收錄名詞（至少）：劇本報酬、情境最壞、Natural 成交報酬、成交摩擦、完成度門檻、不漲保留率、到期緩衝、保本價、Mid/Natural、BCS/BPS、Delta、Theta、Vega、IV、獲利上限、收斂。

### 4.7 v3.1 修補（併入）

- `$` 符：所有 st.markdown 動態文字經跳脫函數（`$`→`\$`）防 LaTeX 誤判；heatmap HTML 不受影響。
- 表單摺疊（§4.1）。舊「單腿三級距卡片＋標章卡」佈局由新結構整體取代。

---

## 5. CLI 報告增量（report.py）

每候選（全部候選，非僅首選）於買價指引之後新增區段：

```
韌性向量（7 情境，Mid 口徑）:
- S1 不漲: -86%   ◀ 情境最壞
- S2 半程: +38%
- S3 大半程: +471%
- S4 晚30天: +899%
- S5 晚90天: +822%（合約先到期，內插價 payoff）   ← 僅發生時附註
- S6 IV最保守: +936%
- S7 Natural成交: +788%
劇本完成度: 0%→-86% | 25%→-41% | 50%→+38% | 75%→+471% | 100%→+943%
保本門檻: 完成 62%（目標日保本價 $97.20，基準IV） | 不漲保留率: 14% | 成交摩擦: 16%
```

- 數字格式：本區段全部百分比**統一取 1 位小數**，與全報告既有紀律一致（mockup 中的整數位為示意，非規格）。
- 「最差進場（Ask）基準報酬率」行改文案為「Natural 成交報酬」。
- 尾註增列：7 情境定義、線性延遲路徑假設、保本價求根說明、「情境最壞非機率、非完整最壞」聲明。
- **四份 golden 重生成**（軸改版+新區段+改名），生成時人工核對清單同 v2/v3 慣例。

---

## 6. 紅線（引擎/GUI/文案）

1. 全 codebase 禁出現：機率、probability、POP、期望報酬、Sharpe、勝率 等機率語彙（測試以字串掃描鎖定 GUI 與報告輸出）。
2. 不存在任何綜合分數欄位／函數。
3. GUI 零金融公式（沿用 v3 紅線；情境/門檻/摩擦全部 service 預算）。
4. 「情境最壞」文案不得寫成「最壞情況」「最大風險」；固定用「情境最壞報酬（7情境）」或欄名「情境最壞」＋懸浮全稱。
5. 排名/標章/抽樣規則全部確定性、可從 spec 重現。

---

## 7. 測試（增量）

1. **scenarios 單元**：七情境逐一與直接引擎呼叫等值（構造已知案例）；S4/S5 的 `expiry < arrive` 內插分支專測；S7 成本口徑；worst 取 min 正確含代號。
2. **保本價**：單調四策略各一案例，bisection 結果代回 |value−cost|<1e-6；無根案例回 None；門檻顯示語意四分支（≤0／(0,1]／>1／None）。
3. **完成度曲線**：五點與 M3 定義等值；k=0 == S1、k=1 == 基準（恆等式）。
4. **分組**：到期日 ≤4 全取；>4 抽樣規則決定性（構造 6 個到期日 fixture 驗證選取集合）；組內各策略最佳與排序；hidden_count 正確。
5. **標章**：top_return/top_resilience/warning/default_selection 各判定，含「全員 warning 退回全場第一」。
6. **矩陣新軸**：4 錨點皆精確在列、看漲/看跌 overshoot/adverse 方向正確、正值鉗制、碰撞（spot×0.9 與格點重合）案例；縮圖降採樣索引固定。
7. **GUI（AppTest）**：分組表渲染（組標題/標章/縮圖 HTML）、列點擊切換主視圖、Step 4 三 expander、說明頁存在、`$` 跳脫（含 `$` 的文案不觸發 LaTeX 亂版——以輸出字串含 `\$` 斷言）、辭典懸浮 title 存在。
8. **紅線掃描測試**：GUI 原始碼與四份 golden 不含機率語彙清單。
9. **Golden × 4 重生成**：新軸+新區段，逐位元凍結+決定性重跑。
10. **既有回歸**：v3 service parity／matrix_grid parity 等全數保留（軸改版處更新期望值）。

## 7A. 審計覆蓋契約（codex-audit §格式，設計期凍結）

- **DC**：乾淨安裝；scenarios.py/glossary.py import；說明頁檔案存在；3.11/3.13 corner。
- **AC**：全套件 codex 親自跑；七情境 marching walk（每情境一項獨立重算比對）；保本價求根數值驗證（codex 自行 bisection 對照）≥2 案例；分組抽樣規則重現；標章判定矩陣；新 golden 逐位元；紅線掃描（機率語彙+GUI零公式+無分數函數）；縮圖降採樣索引驗證。
- **SL**：真實 TLT GUI 路徑（含 expiry_groups 非空、標章存在、主視圖預設無⚠）；同快照 CLI 重跑韌性向量數字一致；Docker compose up + 容器內同快照分析一致。無法執行處依 skill 處方模式，不得豁免。

---

## 8. 驗收案例

TLT 現價 84.52、劇本 2028-01-01 到 105、勾 LC+BCS：

1. 結果頁四步結構呈現；主視圖為無⚠之最高報酬候選的 heatmap；左軸純價格、4 錨點粗體（115.50/105.00/84.52/76.07 級別）。
2. 比較表按到期日分組（≥2 組時），組標題含緩衝天數與特性註記；🚀🛡️◀⚠ 正確落位；點列切換主圖。
3. 任一候選的 7 情境向量、完成度曲線、保本門檻在進階區與 CLI 報告中數字一致（同快照）。
4. 說明頁可開啟；≥16 個名詞有懸浮解釋。
5. 含 `$` 的金額文案在 GUI 不出現 LaTeX 亂版。
6. 全輸出無機率語彙；無任何分數欄位。

---

## 9. 明確不做（v4）

⚖️/💧標章、任何安全分數、POP/期望值/Sharpe、Heatmap 覆蓋率、Rho、Gamma 標準化欄（v4.1）、最大延遲天數求根、Natural 口徑 heatmap 切換（v4.1）、組內展開全部候選（v4.1）、展開全部到期日（v4.1）、絕對 vol-point IV shift（v4.1）、機率模式（未來獨立模式）。
