# Option Chaser MVP Design Spec

日期：2026-07-15
狀態：待審
上游文件：`Option_Chaser/product_brief_v1.md`（OPTION-OPT-001 Product Brief）
成品形狀已由使用者確認：`Option_Chaser/mock_report_preview.md`

---

## 1. 目標與非目標

### 1.1 目標

在假設使用者劇本成立（股票於目標日期到達目標價）的前提下，掃描目前市場上所有符合限制的單腿 Long Call，以確定性公式估算各合約的條件式價值、損益與壓力測試結果，輸出數個不同取捨的候選及推薦理由。

### 1.2 已確認的產品決策（brainstorming 定案）

1. 定位：自用優先，架構保留未來產品化空間。
2. 介面：CLI（單一指令），輸出終端報告與可選 Markdown 檔。
3. 資料來源：yfinance（免費、延遲 15 分鐘）起步，資料層以 Provider Adapter 抽象，未來可換付費源。
4. 估值：多情境 IV（B3）加保守底線。每合約輸出 `1 + len(iv_shifts)` 個估值：內在價值底線，加上每個 IV 情境各一（預設三情境 −20%/不變/+20%，可由 `--iv-shifts` 自訂）。shift=0（基準情境）永遠強制包含——排名與壓力測試依賴它，使用者清單未列 0 時自動加入。
5. 使用者關注的三個取捨面向及其對應機制：報酬率最大化 → 「高報酬型」排名原型；容錯空間 → 「容錯型」排名原型；時間緩衝 → 到期日硬過濾（`--min-days-after`）加延遲壓力情境與 Theta 診斷欄的顯示（不做排名原型）。另設「平衡型」原型綜合前兩者。流動性不做排名維度，只做硬過濾。
6. MVP 完全無 LLM。計算、排名、推薦理由全部由確定性程式與模板產生。

### 1.3 非目標（承襲 brief 第 4 節硬性限制）

- 不預測股票走勢、不判斷劇本正確性、不估算劇本機率、不計算含機率的期望報酬。
- 不將模型估計值描述為保證成交價格；不宣稱保證獲利。
- 不含自動下單、券商整合、選股、投資組合管理。
- 不得因短天期合約表面報酬較高而繞過使用者的到期日安全緩衝。

---

## 2. 架構

### 2.1 模組結構（Python 3.11+，套件名 `option_chaser`）

```
Option_Chaser/
├── option_chaser/
│   ├── __init__.py
│   ├── models.py      # dataclasses：ChainSnapshot, OptionContract, Scenario, Valuation, Candidate, FilterReport
│   ├── data/
│   │   ├── __init__.py
│   │   ├── base.py    # Provider 抽象介面：fetch_chain(symbol) -> ChainSnapshot
│   │   ├── yf.py      # yfinance 實作（全系統唯一碰網路的模組）
│   │   └── snapshot.py# 快照存檔/載入（JSON）
│   ├── filters.py     # 到期日限制 + 資料品質/流動性硬過濾，回傳 FilterReport
│   ├── valuation.py   # Black-Scholes 定價、Greeks、內在價值底線、IV 情境、壓力測試
│   ├── ranking.py     # 三原型排名，純公式
│   ├── report.py      # 終端純文字報告 + Markdown 輸出（禁用 box-drawing 字元）
│   └── cli.py         # argparse 進入點
├── tests/             # pytest，全離線，fixture 快照
├── snapshots/         # 執行時自動存放抓取快照（gitignore）
├── pyproject.toml
└── README.md
```

依賴原則：`cli → report → ranking → valuation → filters → models`，單向。第三方依賴僅 `yfinance`（及其傳遞依賴）；BS 所需的常態分布 CDF 用 `math.erf` 自行實作，不引入 scipy/numpy。

### 2.2 資料流

```
symbol → data/yf.py 抓取 → ChainSnapshot → snapshot.py 落地 JSON（含時間戳）
       → filters.py（回傳合格合約 + FilterReport 統計）
       → valuation.py（每合約算底線/各 IV 情境/壓力測試/Greeks）
       → ranking.py（三原型排序取前 N）
       → report.py（組報告）
```

離線重跑：`--snapshot <path>` 跳過抓取，直接載入舊快照。相同快照 + 相同參數必須產生逐位元相同的報告（決定性要求，見 §8）。

### 2.3 ChainSnapshot JSON 格式

```json
{
  "schema_version": 1,
  "symbol": "XYZ",
  "fetched_at": "2026-07-15T21:30:00-04:00",
  "spot": 100.0,
  "source": "yfinance",
  "contracts": [
    {
      "contract_symbol": "XYZ261016C00110000",
      "strike": 110.0,
      "expiry": "2026-10-16",
      "bid": 3.0,
      "ask": 3.25,
      "last": 3.1,
      "volume": 152,
      "open_interest": 830,
      "implied_volatility": 0.38
    }
  ]
}
```

僅存 call。`fetched_at` 用資料源回報時間；若源不提供，用本機抓取時刻（UTC 偏移標明）。價格單位為每股（1 張合約 = 100 股，報告中的金額換算 ×100 並標示）。

---

## 3. 使用者輸入

| 參數 | 必填 | 意義 | 驗證 |
|---|---|---|---|
| `symbol` | 是 | 美股代號 | 非空字串 |
| `--target-price` | 是 | 劇本目標價 | > 0；若 ≤ 現價，警告「Long Call 劇本目標價低於現價」並要求 `--force` 才續跑 |
| `--target-date` | 是 | 劇本到達日 | 必須晚於今天；格式 YYYY-MM-DD |
| `--min-days-after` | 否，預設 0 | 到期日至少晚於 target-date 的天數 | ≥ 0 整數 |
| `--min-expiry` | 否 | 到期日絕對下限 | 格式 YYYY-MM-DD |
| `--top` | 否，預設 3 | 每原型候選數 | 1–10 |
| `--iv-shifts` | 否，預設 `-0.2,0,0.2` | IV 乘法情境（數量不限） | 逗號分隔浮點數，乘數 = 1+shift 必須 > 0；shift=0 未列出時自動加入（排名依賴基準情境）；去重後由小到大排序 |
| `--rate` | 否，預設 0.04 | 無風險年利率 | ≥ 0 |
| `--min-oi` | 否，預設 10 | Open Interest 門檻 | ≥ 0 |
| `--delay-days` | 否，預設 ceil(min-days-after/2) | 延遲壓力情境的延遲天數 | 0 ≤ delay_days ≤ min_days_after（保證延遲時合約未到期）；若 min-days-after=0 且未指定，預設 0（不跑延遲情境） |
| `--force` | 否 | 允許目標價 ≤ 現價的劇本續跑 | 布林旗標 |
| `--snapshot` | 否 | 離線重跑用快照路徑 | 檔案存在且 schema_version 相容 |
| `--md` | 否 | Markdown 報告輸出路徑 | 可寫入 |

日期一律以美東（US/Eastern）日曆日理解；天數為日曆日。

---

## 4. 過濾（filters.py）

依序執行，每道記錄刷掉張數與原因（FilterReport）：

1. **到期日限制**：`expiry ≥ target_date + min_days_after` 且（若給定）`expiry ≥ min_expiry`。
2. **報價有效**：`bid > 0`、`ask ≥ bid`。
3. **IV 有效**：`0.01 ≤ implied_volatility ≤ 5.0`。
4. **流動性**：`open_interest ≥ min_oi`。

任何一道不過即淘汰，不進入估值。過濾後合格數為 0 時：輸出 FilterReport 全文（每道門檻刷掉多少）並終止，不產生推薦（brief 成功標準 #10）。

---

## 5. 估值（valuation.py）

### 5.1 Black-Scholes 定價

歐式 call：

```
d1 = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
d2 = d1 − σ·√T
C  = S·N(d1) − K·e^(−rT)·N(d2)
```

`N(x)` 用 `0.5·(1 + erf(x/√2))` 實作。`T` 為年化剩餘時間 = 日曆日 / 365。

**T ≤ 0 分支**：任何估值呼叫若 `T ≤ 0`（如 `min-days-after=0` 使 `expiry == target_date`，或延遲情境 `delay_days == min_days_after` 使剩餘時間歸零），BS 不適用（d1 除以零），直接回傳內在價值 `max(S − K, 0)`。此分支必須有單元測試。

已文件化的模型限制（報告尾註必列）：

- 無股利調整（q = 0）。對高股利股票會高估 call 價值。
- 歐式近似。無股利 call 的美式價值等於歐式（不提前行使最優），有股利時為近似。
- σ 取當前該合約的 IV，情境調整用乘法（σ' = σ × (1 + shift)）。

### 5.2 每合約的條件式估值

情境時點：target_date，股價 = target_price，剩餘時間 T_rem = (expiry − target_date)/365。

輸出：

| 名稱 | 公式 |
|---|---|
| 保守底線 | `max(target_price − strike, 0)`（美式選擇權市價不低於內在價值的無套利下限） |
| IV 情境 × len(iv_shifts) | `BS(S=target_price, K=strike, T=T_rem, r=rate, σ=IV×(1+shift))`，對每個 shift ∈ iv_shifts 各算一個。shift=0 稱「基準情境」，必然存在（§3 驗證保證） |

估值、報告、golden test 都對 iv_shifts 動態迭代，不得寫死情境數量；golden test 的 fixture 用預設三情境。

### 5.3 進場成本與損益

- 基準成本 = Mid = (bid + ask) / 2；最差成本 = Ask。
- 每個估值分別對兩種成本算：`損益 = 估值 − 成本`、`報酬率 = 損益 / 成本`。
- 報告主表用 Mid，Ask 版本在同區塊以「最差進場」列出。

### 5.4 壓力測試（每合約，確定性）

| 情境 | 定義 |
|---|---|
| 半程 | target_date 時股價只到 `spot + 0.5×(target_price − spot)`，IV 不變，BS 估值 |
| 延遲 | 股價於 `target_date + delay_days` 才到 target_price，剩餘時間相應縮短，IV 不變，BS 估值。因 `delay_days ≤ min_days_after`，合約必然尚未到期 |
| 全錯 | target_date 時股價 = 今日 spot（完全沒漲），IV 不變，BS 估值 |

### 5.5 Greeks（診斷欄位，當前時點）

以現在的 S=spot、T=(expiry−今天)/365、σ=當前 IV 計算：Delta = N(d1)、Gamma = φ(d1)/(S·σ·√T)、Theta（每日）、Vega（每 1% IV）。僅供診斷顯示，不參與排名。

---

## 6. 排名（ranking.py）

全部以 Mid 進場、報酬率（不是絕對金額）為比較基準（同資本公平比較）。

| 原型 | 分數（越大越好） |
|---|---|
| 高報酬型 | 基準情境報酬率（IV 不變） |
| 容錯型 | `0.5 × 半程報酬率 + 0.5 × 全錯報酬率` |
| 平衡型 | `−(高報酬排名名次 + 容錯排名名次) / 2`（名次平均取負值，維持「分數越大越好」的統一語義；三原型一律降冪排序取前 N） |

延遲情境不入分數（它由 min-days-after 硬門檻保障，報告中顯示供參考）。

決定性 tie-break（依序）：spread%（(ask−bid)/mid）小者優先 → strike 低者優先 → expiry 早者優先 → contract_symbol 字典序。此為全序，保證相同輸入排序唯一。

每原型輸出前 `top` 名。同一合約可在多個原型出現（如實反映，不去重）。

推薦理由模板（每候選）：

- 優點：由該原型分數構成要素生成（如「46 張合格合約中基準情境報酬率最高」）。
- 代價：固定規則生成——Delta < 0.5 提示「若完全不漲權利金可能全損」；成本為三原型首選中最高者提示「本金需求最大」；spread% > 10% 提示「買賣價差偏大」。

---

## 7. 報告（report.py）

結構（純文字，禁用 box-drawing 字元，適合手機閱讀）：

1. 標頭：資料時間戳與延遲標示、現價、使用者劇本、使用者限制、模型假設。四類資訊（使用者假設／市場資料／模型假設／計算結果）分區標示。
2. 過濾統計：總數 → 每道門檻刷掉數 → 合格數。
3. 三原型候選區：每候選列出 strike/expiry/bid/ask/mid/IV/Delta/Theta/Vega、保守底線與各 IV 情境（依 iv_shifts 動態迭代，估值+損益+報酬率）、三個壓力測試、最差進場（Ask）版本的基準報酬率、模板生成的優點與代價。
4. 尾註：全部計算公式、參數值、模型限制、免責聲明（「模型估計非保證價格，不構成投資建議」）。

`--md` 給定時另存 Markdown 版本（同內容）。

金額顯示：每股價格與每張合約金額（×100）並列。數字格式固定（價格 2 位小數、報酬率 1 位小數百分比），保證決定性輸出。

---

## 8. 錯誤處理與決定性

| 狀況 | 行為 |
|---|---|
| 抓取失敗（網路/代號不存在/源改版） | 明確錯誤訊息 + 非零 exit code，不產生部分報告 |
| 過濾後 0 合格 | 輸出 FilterReport，說明每道門檻，非零 exit code |
| 合約缺 IV 或 IV 越界 | 該合約淘汰並計入統計，不估值 |
| 輸入驗證失敗 | 錯誤訊息 + 用法提示，exit code 2 |
| 快照 schema 不相容 | 明確報錯，提示重抓 |

決定性保證：`分析(snapshot, params) → report` 是純函數。不讀系統時鐘——「今天」定義為：將快照的 `fetched_at` 轉換至 US/Eastern 時區後取其日期部分（與 §3 的日期規則一致，避免跨午夜或從亞洲時區執行時差一天）。不用隨機數，排序有全序 tie-break，數字格式固定。同一快照同參數 → 逐位元相同輸出。線上模式唯一的非決定性在抓取那一步，抓完即落地成快照。

---

## 9. 測試（tests/，pytest，全離線）

1. **BS 單元測試**：對教科書已知值驗證定價（誤差 < 1e-4）；put-call parity；邊界（深價內趨近 S−K·e^(−rT)、深價外趨近 0、T→0 趨近內在價值）。
2. **Greeks 單元測試**：對已知值驗證；Delta ∈ (0,1)。
3. **過濾測試**：每道門檻獨立驗證 + FilterReport 計數正確。
4. **排名測試**：構造合約使三原型序已知；tie-break 全序驗證（構造完全同分的合約）。
5. **Golden test**：fixture 快照 + 固定參數 → 報告與存檔的預期輸出逐字元相等（決定性 + 回歸雙保險）。
6. **輸入驗證測試**：非法日期、負價格、target ≤ spot 無 --force 等。
7. **快照 round-trip**：存檔→載入→資料等值。
8. **yf adapter 對映測試**：以存檔的 yfinance 回傳形狀 fixture（mock，不碰網路）驗證欄位對映到 ChainSnapshot 正確（含缺欄位、NaN 處理）。

yfinance 的實際網路抓取以手動煙霧測試驗證；對映邏輯由測試 #8 離線覆蓋。

---

## 10. 未來擴充（不在 MVP，僅保留空間）

- 付費資料源 adapter（Polygon/Tradier）——實作 `data/base.py` 介面即可。
- Web UI——`report.py` 之上另建呈現層，核心不動。
- 其他策略（bull call spread 等）——models 與 valuation 泛化。
- 多情境劇本、IV 曲面模型——valuation 擴充。

---

## 11. 驗收對照（brief 第 7 節案例）

XYZ 現價 100、45 天後到 120、緩衝 45 天：

1. 系統不評估「XYZ 能否到 120」→ 程式中不存在任何機率/預測邏輯。✓（§1.3）
2. 排除到期日不符合約 → 過濾第 1 道。✓（§4）
3. 比較所有資料合格 Long Call → 過濾後全體進估值。✓（§4–5）
4. 估算各候選條件式結果 → 底線 + 各 IV 情境（此案例用預設三情境）+ 三壓力測試。✓（§5）
5. 顯示市場報價、模型假設、計算結果 → 報告四區分類。✓（§7）
6. 依批准方法提供候選與理由 → 三原型 + 模板理由，公式全揭露。✓（§6–7）

<!-- codex-peer-reviewed: 2026-07-15T03:45:22Z rounds=4 verdict=approved -->
