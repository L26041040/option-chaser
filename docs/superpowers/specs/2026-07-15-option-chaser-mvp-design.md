# Option Chaser MVP Design Spec

日期：2026-07-15（第二輪修訂：2026-07-16）
狀態：待審（第二輪）
上游文件：`product_brief_v1.md`（OPTION-OPT-001 Product Brief）
成品形狀已由使用者確認：`mock_report_preview.md`

第二輪修訂重點（回應三個痛點）：

1. 排名方法改為實務標準的 moneyness/Delta 分級制，廢除自訂評分權重（§6）。
2. 新增「買價指引」三層天花板，回答「這張最高買到多少仍合理」（§5.7）。
3. 流動性過濾升級：spread 硬過濾（含絕對地板）+ volume 新鮮度警示（§4）。

---

## 1. 目標與非目標

### 1.1 目標

在假設使用者劇本成立（股票於目標日期到達目標價）的前提下，掃描目前市場上所有符合限制的單腿 Long Call，以確定性公式估算各合約的條件式價值、損益與壓力測試結果，依實務標準的 Delta 分級輸出不同風險級距的候選、買價指引及推薦理由。

### 1.2 已確認的產品決策

1. 定位：自用優先，架構保留未來產品化空間。
2. 介面：CLI（單一指令），輸出終端報告與可選 Markdown 檔。
3. 資料來源：yfinance（免費、延遲 15 分鐘）起步，資料層以 Provider Adapter 抽象，未來可換付費源。
4. 估值：多情境 IV（B3）加保守底線。每合約輸出 `1 + len(iv_shifts)` 個估值：內在價值底線，加上每個 IV 情境各一（預設三情境 −20%/不變/+20%，可由 `--iv-shifts` 自訂）。shift=0（基準情境）永遠強制包含——排名與買價指引依賴它，使用者清單未列 0 時自動加入。
5. 使用者關注的三個取捨面向及其對應機制：報酬率最大化 → 積極型級距（價外，高槓桿）；容錯空間 → 保守型級距（價內，breakeven 貼近現價）；時間緩衝 → 到期日硬過濾（`--min-days-after`）加延遲壓力情境與 Theta 診斷欄。級距劃分採實務標準 moneyness/Delta 分級（§6），不使用任何自訂評分權重。
6. MVP 完全無 LLM。計算、分級、排序、推薦理由、買價指引全部由確定性程式與模板產生。
7. 買價指引：以三層天花板（劇本內在價值／保守 IV 情境估值／要求報酬反推價）回答「最高買到多少仍合理」，全部為現有估值機制的延伸（§5.7）。
8. 可交易性：bid-ask spread 為選擇權流動性的標準量測，升級為硬過濾（相對門檻 + 絕對地板取大者）；volume 作新鮮度警示，預設不過濾（§4）。

### 1.3 非目標（承襲 brief 第 4 節硬性限制）

- 不預測股票走勢、不判斷劇本正確性、不估算劇本機率、不計算含機率的期望報酬。
- 不將模型估計值描述為保證成交價格；不宣稱保證獲利。
- 不含自動下單、券商整合、選股、投資組合管理。
- 不得因短天期合約表面報酬較高而繞過使用者的到期日安全緩衝。

---

## 2. 架構

### 2.1 模組結構（Python 3.11+，套件名 `option_chaser`）

```
option-chaser/
├── option_chaser/
│   ├── __init__.py
│   ├── models.py      # dataclasses：ChainSnapshot, OptionContract, Scenario, Valuation, PriceGuidance, Candidate, FilterReport
│   ├── data/
│   │   ├── __init__.py
│   │   ├── base.py    # Provider 抽象介面：fetch_chain(symbol) -> ChainSnapshot
│   │   ├── yf.py      # yfinance 實作（全系統唯一碰網路的模組）
│   │   └── snapshot.py# 快照存檔/載入（JSON）
│   ├── filters.py     # 到期日限制 + 資料品質/流動性/spread 硬過濾，回傳 FilterReport
│   ├── valuation.py   # Black-Scholes 定價、Greeks、內在價值底線、IV 情境、壓力測試、Breakeven/Lambda、買價指引
│   ├── ranking.py     # Delta 分級 + 級內排序，純公式
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
       → valuation.py（每合約算底線/各 IV 情境/壓力測試/Greeks/Breakeven/Lambda/買價指引）
       → ranking.py（Delta 分級，級內排序取前 N）
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
| `--top` | 否，預設 3 | 每級距候選數 | 1–10 |
| `--iv-shifts` | 否，預設 `-0.2,0,0.2` | IV 乘法情境（數量不限） | 逗號分隔浮點數，乘數 = 1+shift 必須 > 0；shift=0 未列出時自動加入（排名與買價指引依賴基準情境）；去重後由小到大排序 |
| `--rate` | 否，預設 0.04 | 無風險年利率 | ≥ 0 |
| `--min-oi` | 否，預設 10 | Open Interest 門檻 | ≥ 0 |
| `--min-volume` | 否，預設 0 | 當日成交量硬門檻（預設不過濾） | ≥ 0 整數 |
| `--max-spread-pct` | 否，預設 0.15 | spread 相對門檻（spread ≤ 該比例 × mid） | > 0 |
| `--spread-floor` | 否，預設 0.10 | spread 絕對地板（美元/股）；spread ≤ 地板者一律放行 | ≥ 0 |
| `--delta-bands` | 否，預設 `0.35,0.65` | Delta 分級門檻 a,b | 兩個浮點數，0 < a < b < 1 |
| `--min-return` | 否，預設 0 | 最低要求報酬率（用於買價指引 L3） | ≥ 0 |
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
4. **未平倉/成交量**：`open_interest ≥ min_oi` 且 `volume ≥ min_volume`（min_volume 預設 0，即預設只看 OI；volume 門檻預設不啟用的理由：合約單日成交量波動極大，硬過濾會使同一合約隔日忽進忽出候選名單，破壞結果穩定性）。
5. **Spread 可交易性**：淘汰條件 `spread > max(spread_floor, max_spread_pct × mid)`，其中 `spread = ask − bid`、`mid = (bid + ask)/2`。相對門檻為主（bid-ask spread 是選擇權流動性的標準量測，主流券商篩選器均採 OI + Volume + Spread 三軸）；絕對地板防止低價合約因最小跳動單位（tick）造成 spread% 虛高而被誤殺（例：bid 0.05 / ask 0.15，spread% = 100% 但 spread 僅 $0.10，屬 tick-bound 而非流動性差）。

任何一道不過即淘汰，不進入估值。過濾後合格數為 0 時：輸出 FilterReport 全文（每道門檻刷掉多少）並終止，不產生推薦（brief 成功標準 #10）。

**報價新鮮度警示（不過濾）**：通過全部過濾但 `volume = 0` 的合約，在報告中加註「今日無成交，報價新鮮度存疑」。yfinance 無可靠逐筆時間戳，volume=0 是唯一可用的新鮮度代理訊號；不做硬過濾以免誤殺低頻但可交易的合約。

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

### 5.4 壓力測試（每合約，確定性；純顯示，不參與排名）

| 情境 | 定義 |
|---|---|
| 半程 | target_date 時股價只到 `spot + 0.5×(target_price − spot)`，IV 不變，BS 估值 |
| 延遲 | 股價於 `target_date + delay_days` 才到 target_price，剩餘時間相應縮短，IV 不變，BS 估值。因 `delay_days ≤ min_days_after`，合約必然尚未到期 |
| 全錯 | target_date 時股價 = 今日 spot（完全沒漲），IV 不變，BS 估值 |

### 5.5 Greeks（診斷欄位，當前時點）

以現在的 S=spot、T=(expiry−今天)/365、σ=當前 IV 計算：Delta = N(d1)、Gamma = φ(d1)/(S·σ·√T)、Theta（每日）、Vega（每 1% IV）。Delta 同時作為 §6 分級依據；其餘僅供診斷顯示。因過濾保證 `expiry ≥ target_date > 今天`，計算 Greeks 時恆有 T > 0。

### 5.6 Breakeven 與 Lambda（診斷欄位，教科書標準公式）

| 名稱 | 公式 | 依據 |
|---|---|---|
| Breakeven | `strike + mid`（到期持有觀點的靜態損益兩平價；以 Mid 計） | OIC/CBOE 選擇權教育標準公式 |
| Breakeven 距現價 | `(breakeven − spot) / spot`，百分比 | 同上 |
| Breakeven 對目標價緩衝 | `(target_price − breakeven) / target_price`，百分比（可為負；負值表示劇本全部兌現仍不足以覆蓋到期持有的成本） | 同上 |
| Lambda（有效槓桿） | `Delta × spot / mid`（elasticity，Hull《Options, Futures, and Other Derivatives》） | 教科書標準 |

兩者皆為診斷顯示，不參與排名。報告註明：Breakeven 為到期持有觀點，提前平倉不適用；Lambda 對低權利金合約會放大，僅供槓桿量級參考。

### 5.7 買價指引：三層天花板（每合約）

回答「根據你的劇本，這張最高買到多少仍然合理」。三層全部為確定性公式：

| 層 | 名稱 | 公式 | 語意 |
|---|---|---|---|
| L1 | 硬上限 | `max(target_price − strike, 0)` | 劇本成立時的內在價值，模型無關。買價超過它，即使股價完全按劇本到位並持有至目標日，內在價值都不足以回本 |
| L2 | 保守上限 | `BS(S=target_price, K=strike, T=T_rem, r=rate, σ=IV×(1+min(iv_shifts)))` | 最保守 IV 情境下的目標日估值。買價超過它，需要「IV 不惡化」這個劇本之外的額外假設才能不虧 |
| L3 | 要求報酬上限 | `基準情境估值 ÷ (1 + min_return)` | 買價超過它，即使劇本成立也達不到使用者設定的最低報酬率 |

恆等式：因 BS call 價值 ≥ 內在價值（r ≥ 0）且 min(iv_shifts) ≤ 0（§3 保證 0 必在清單中），恆有 `L1 ≤ L2 ≤ 基準情境估值`；又 min_return ≥ 0，故 `L3 ≤ 基準情境估值`。L3 與 L1/L2 的相對位置隨 min_return 浮動，因此報告不採固定區間敘事，改為對目前 Ask 逐層獨立判定：

- `Ask > L1` → 「超過劇本內在價值，獲利需時間價值/IV 配合」
- `Ask > L2` → 「劇本成立但 IV 走弱情境下仍虧損」
- `Ask > L3` → 「以 Ask 進場達不到你設定的最低報酬（min_return）」

三句判定互相獨立，可同時出現多句；全部未觸發時顯示「目前 Ask 低於全部三層天花板」。觸發 L2 的合約仍照常列出與排名，僅明確警示——本產品不替使用者做最終買賣決定（brief §4）。

---

## 6. 分級與排序（ranking.py）

### 6.1 Delta 分級（取代自訂評分原型）

依當前 Delta（§5.5）把合格合約劃入三個級距。劃分依據為選擇權實務的標準 moneyness 分類——深價內 call 即實務所稱「stock replacement」策略（McMillan《Options as a Strategic Investment》、CBOE/OIC 教材），高 Delta、breakeven 貼近現價、劇本失敗時殘值高；價外 call 為高槓桿投機。Delta 作為 moneyness 代理是實務慣例：

| 級距 | 條件（預設 a=0.35, b=0.65，`--delta-bands` 可調） | 風險語意 |
|---|---|---|
| 保守型 | Delta > b | 價內／stock replacement：容錯空間大，本金需求高，倍數低 |
| 平衡型 | a ≤ Delta ≤ b | 價平附近：時間價值與內在價值的折衷 |
| 積極型 | Delta < a | 價外：劇本全對時報酬率最高，全錯時歸零風險最高 |

門檻預設值為實務慣例級距，非最佳化結果（spec 明示，避免偽精確）。每張合約恰屬一個級距。某級距無合格合約時，報告明示「此級距無合格合約」，不從其他級距借調充數。

### 6.2 級內排序（同一把尺）

各級距內部以**基準情境報酬率**（IV 不變情境、Mid 進場，§5.2–5.3）降冪排序，取前 `top` 名。全部級距用同一把尺——風險差異已由級距劃分表達，級內只比「劇本成立時的資本效率」。

不再存在任何自訂權重或名次合成分數。壓力測試（§5.4）與 Breakeven/Lambda（§5.6）為顯示欄位，不參與排序。

決定性 tie-break（依序，不變）：spread%（(ask−bid)/mid）小者優先 → strike 低者優先 → expiry 早者優先 → contract_symbol 字典序。此為全序，保證相同輸入排序唯一。

### 6.3 推薦理由模板（每候選，確定性生成）

- 優點：由級距語意 + 該合約實際數字生成。例：保守型「breakeven 僅高於現價 X%，劇本半對仍獲利」；積極型「N 張合格合約中基準情境報酬率最高」；平衡型「內在價值佔權利金 X%，時間價值負擔適中」。
- 代價：固定規則生成——Delta < 0.5 提示「若完全不漲權利金可能全損」；成本為三級距首選中最高者提示「本金需求最大」；spread% > 過濾門檻的 2/3 提示「買賣價差偏大」（警示線 = 門檻 × 2/3，保證與 §4 硬過濾一致，不會出現已通過過濾卻觸發矛盾警示的情況）；觸發 §5.7 任一天花板判定的，對應警句納入代價欄。

---

## 7. 報告（report.py）

結構（純文字，禁用 box-drawing 字元，適合手機閱讀）：

1. 標頭：資料時間戳與延遲標示、現價、使用者劇本、使用者限制、模型假設。四類資訊（使用者假設／市場資料／模型假設／計算結果）分區標示。
2. 過濾統計：總數 → 五道門檻各刷掉數（§4 順序）→ 合格數。
3. 三級距候選區（保守型 → 平衡型 → 積極型）：每候選列出 strike/expiry/bid/ask/mid/IV/Delta/Theta/Vega/Breakeven（含距現價%、對目標價緩衝%）/Lambda、保守底線與各 IV 情境（依 iv_shifts 動態迭代，估值+損益+報酬率）、三個壓力測試、最差進場（Ask）版本的基準報酬率、**買價指引小節**（L1/L2/L3 三個數字 + Ask 逐層判定句，§5.7）、模板生成的優點與代價、volume=0 時的新鮮度警示（§4）。
4. 尾註：全部計算公式、參數值、模型限制、免責聲明（「模型估計非保證價格，不構成投資建議」）。

`--md` 給定時另存 Markdown 版本（同內容）。

金額顯示：每股價格與每張合約金額（×100）並列。數字格式固定（價格 2 位小數、報酬率 1 位小數百分比、Lambda 1 位小數、Delta 2 位小數），保證決定性輸出。

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
3. **過濾測試**：五道門檻獨立驗證 + FilterReport 計數正確；spread 過濾需含「絕對地板放行 tick-bound 低價合約」案例（如 bid 0.05/ask 0.15 應放行）與「相對門檻淘汰寬 spread」案例；volume=0 警示標記正確且不淘汰。
4. **分級與排序測試**：Delta 恰為級距邊界值（0.35、0.65）的歸屬明確；空級距輸出正確；級內排序與 tie-break 全序驗證（構造完全同分的合約）。
5. **買價指引測試**：L1/L2/L3 公式驗證；恆等式 `L1 ≤ L2 ≤ 基準估值` 在隨機參數組合下成立（參數化測試，非隨機數——用固定參數矩陣）；Ask 逐層判定句觸發條件正確。
6. **Breakeven/Lambda 測試**：公式對已知值驗證；緩衝為負（breakeven > target）的案例。
7. **Golden test**：fixture 快照 + 固定參數 → 報告與存檔的預期輸出逐字元相等（決定性 + 回歸雙保險；fixture 需覆蓋三級距皆有候選、volume=0 警示、觸發 L2/L3 判定句的合約各至少一例）。
8. **輸入驗證測試**：非法日期、負價格、target ≤ spot 無 --force、delta-bands 非法（a ≥ b、越界）、min-return 負值等。
9. **快照 round-trip**：存檔→載入→資料等值。
10. **yf adapter 對映測試**：以存檔的 yfinance 回傳形狀 fixture（mock，不碰網路）驗證欄位對映到 ChainSnapshot 正確（含缺欄位、NaN 處理）。

yfinance 的實際網路抓取以手動煙霧測試驗證；對映邏輯由測試 #10 離線覆蓋。

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
4. 估算各候選條件式結果 → 底線 + 各 IV 情境（此案例用預設三情境）+ 三壓力測試 + 買價指引。✓（§5）
5. 顯示市場報價、模型假設、計算結果 → 報告四區分類。✓（§7）
6. 依批准方法提供候選與理由 → Delta 分級（實務標準）+ 級內單一排序尺 + 模板理由，公式全揭露。✓（§6–7）

<!-- codex-peer-reviewed: 2026-07-15T03:45:22Z rounds=4 verdict=approved (第一輪版本) -->
<!-- 第二輪修訂 2026-07-16：Delta分級制/買價指引/流動性升級，待 codex peer review -->
