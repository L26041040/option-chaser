# Heatmap／Crossover 估值方法選型：未到期日 × 指定價格，最低工程成本的成熟解

研究日期：2026-08-09（MVP V3／spec #102；位置在 #110 之後、#113／#115 之前）。

**本文性質聲明（guardrail）**：本票只做方法選型研究、真實資料量化與書面建議；
**不修改 `option_chaser` 引擎、不修改 golden fixtures、不修改契約樣本、不開票、
不自行鎖定模型**。文中「建議」一律指需要需求方核准後才會進入 #113 的建議，
不是已經做掉的變更。

**與 #110 的分工（重要，別把兩份文件當成同一題）**：
`docs/research/valuation-carry-method-comparison.md`（#110，決策 D1）問的是
「**哪一種 carry 模型在正確性上是對的**」；本文問的是
「**Heatmap／Crossover 這個用途，成本最低的成熟現成方法是哪一個**」。
兩題的答案有交集但不相同，§6 逐條說明我同意什麼、補充什麼、以及一處
#110 沒看到的根因。

---

## 資料品質聲明（每一條主張都標證據等級）

本文所有主張標成四級，全文不出現「沙箱連不到 ⇒ 不存在／production 也連不到」
這種推論：

- **【實測】** 本地真實資料量化，任何人可重跑。資料＝本 repo 既有
  `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（#110 建立的真實 TLT
  LEAPS 報價）與真實 Cboe 全鏈 `YETI.json`（758 筆，
  `docs/research/spread-synthetic-parity-check.md` §引用清單已記錄原檔位址
  `https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json`，
  本次重新下載成功、HTTP 200、328,854 bytes）。
- **【一手原始碼】** 逐字讀到的公開原始碼（本次經 `raw.githubusercontent.com`
  取得，該網域是本沙箱目前唯一可用的外部通道）。原始碼本身即一手來源。
- **【索引轉述】** WebSearch 回傳的搜尋索引摘錄。**不是**一手資料；逐條標明，
  且凡是摘錄與網域歸屬有疑義的一律寫出疑義（§3.1 有一個真實例子）。
- **【本文推導】** 我自己的推理或設計建議，沒有外部背書。

**沙箱出口狀態（本次實測，2026-08-09）**：`curl` 對
`optionsprofitcalculator.com`／`theocc.com`／`cdn.cboe.com`／`sec.gov`／
`arxiv.org`／`en.wikipedia.org`／`web.archive.org` 一律 CONNECT 403 或連線失敗；
WebFetch 對 `www.optionsprofitcalculator.com` 回 `EGRESS_BLOCKED`。
可達的只有 `raw.githubusercontent.com` 與 `api.github.com`。這是**本沙箱的出口
政策**，與這些站台是否存在、production 能否連到無關。無法一手查證的項目全部
列在 §9。

---

## 目錄

1. 摘要
2. 問題定義：Heatmap／Crossover 對估值的實際要求
3. 外部比較：OPC 一類工具與成熟公開程式庫怎麼做這件事
4. 真實資料診斷：現行 q=0 在**部署路徑上**產生什麼
5. 四個候選方法的真實資料量化比較
6. 與 #110 的異同
7. Crossover 專屬的含義（#115／#116 的直接輸入）
8. 施工影響與 blast radius（#113 的隱藏 scope）
9. 侷限與無法一手查證的清單
10. 六問六答（決策用）
11. 引用清單

---

## 1. 摘要

- **現行 q=0 歐式 BS ＋ 直接採用 vendor IV 這個組合，在部署路徑上會印出明顯
  荒謬的數字**。用真實 TLT LEAPS 報價餵進**引擎本人**
  （`service.run_with_snapshot`，不是我的重寫版），Heatmap「今天 × 現價」那一格
  ——標的還沒動、你才剛用 Ask 買進——顯示 **+81.9%**（Bull Call Spread）與
  **+81.4%**（Long Call），而誠實的答案是 −11.5%／−4.2%（就是你付掉的買賣價差）
  【實測，§4.1】。
- **根因不是「少了一項 q」，是模型不一致**：引擎消費的 vendor IV 是**用含股利、
  且是美式模型**反解出來的，卻被代回一個既無股利、又是歐式的公式。用 Cboe 自家
  `theo` 欄位可以直接證明這件事——長天期價內 put 上，`|theo − 美式|` 中位數
  $0.033、`|theo − 歐式|` 中位數 $0.663，24/24 全部靠向美式；反解 IV 更直接：
  vendor `iv` 與美式反解差 0.0029–0.0047 vol pt，與歐式反解差 0.049–0.060 vol pt
  （差 10–20 倍）【實測，§4.3】。
- **因此本文的核心方法論主張是**：模型選哪一個是次要的，**「用同一個模型反解
  IV、再用同一個模型重新估值」（calibrate-and-reprice with one model）才是主要
  的**。這正是 OptionsProfitCalculator 自己 FAQ 描述的作法（IV 由該合約當下的
  市價反解）【索引轉述，§3.1】。只做這件事、模型完全不換，就能讓「今天 × 現價」
  那一格**依定義**回到市價。
- **四個方法的實測結論**（兩個真實部位、走引擎自己的 `price_axis`／`date_axis`／
  `matrix_grid`，以 CRR 美式樹為對照基準）：

  | 方法 | Heatmap 格差（中位／p90／max, pp） | Crossover 勝負判錯格數 | 每格成本 | 2.4y LEAPS 單張矩陣 |
  |---|---|---|---|---|
  | 現行 q=0＋vendor IV | 4.79–14.28 ／ 10.12–35.14 ／ 13.74–43.25 | 5.1%–6.7% | 0.93 µs | 0.59 ms |
  | Merton BSM＋q（價格錨定） | 1.44–2.21 ／ 7.03–8.89 ／ 10.72–37.67 | 0.3%–3.5% | 0.62 µs | 0.44 ms |
  | **Bjerksund–Stensland 1993＋q（價格錨定）** | **0.18–0.33 ／ 0.54–1.73 ／ 0.81–4.47** | **0.0%** | **6.0 µs** | **3.83 ms** |
  | CRR 美式樹 N=300 | （基準） | （基準） | 15,434 µs | **9.85–10.19 s** |

  （兩個數字＝TLT Bull Call Spread 與 YETI Bear Put Spread 兩個真實案例，
  完整表格見 §5。）
- **建議採用：Bjerksund–Stensland (1993) 美式近似封閉解，帶連續股利殖利率 q，
  並以「同快照、同模型反解每腿 IV」價格錨定。** 理由是它同時滿足四件事：
  (a) 成熟公開（QuantLib 內建 `BjerksundStenslandApproximationEngine`
  【一手原始碼】）；(b) 封閉解、純 stdlib、無需 numpy（本 repo 刻意不讓 numpy
  進 lambda，見 `pyproject.toml` 註解）；(c) q ≤ 0 時對 call **數學上恰好退化成
  Merton 歐式**（實測差 0.00e+00），所以它**涵蓋**「Merton＋q」而不是多一套；
  (d) 成本只有 BS 的 8.7 倍，一張 2.4 年 LEAPS 矩陣 3.83 ms，而 CRR 樹是 10 秒
  ——後者在 60 秒 serverless 上限下不可行。
- **CRR／二項樹明確不建議當 production 估值器**（但**建議保留在測試裡當對照
  基準**）：實測一張 2.4 年 LEAPS Spread 矩陣 638 次估值，CRR N=300 要 9.85 秒；
  一次分析會建**幾十張**矩陣（連 11 筆合約的玩具 fixture 都建了 11 張、
  1,694 次腿估值），CRR 化之後光那個玩具 fixture 就要 26.1 秒【實測，§5.3】。
- **仍需需求方裁示三件事**（§10 第 6 問）：q 的來源沿用 #110 的 Method E（本文
  實測證明 q 的**數值**即使在價格錨定之後仍然重要，不能隨便給一個）；
  Bjerksund–Stensland vs 只做 Merton 的取捨；以及一個 #113 票面**目前沒寫到**的
  副作用——**單腿（Long Call／Long Put）的 delta 分級會位移，候選選取結果會變**
  （實測 TLT 五檔中三檔從 conservative 掉到 balanced）【實測，§8】。

---

## 2. 問題定義：Heatmap／Crossover 對估值的實際要求

`option_chaser/valuation.py::scenario_leg_value` 是唯一的「指定未來日期 `at`、
指定標的價 `S`」估值原語；`spread_scenario_value` 是它的兩腿差再箝制到
`[0, width]`。Heatmap 的每一格就是呼叫它一次：

```python
# option_chaser/matrix.py::matrix_grid
tuple((value_fn(price, d) - cost) / cost for d, _ in dates)
```

**這個用途有四個約束，是本文選型的評分表**：

1. **每格一次呼叫，格數不小**。`price_axis` 固定回 11 個價位；`date_axis` 在
   GUI 走 `GUI_MAX_GAP_DAYS = 31`，2.4 年 LEAPS ＝ 29–30 個日期欄（QA-FIX-5
   已實測命中）。一張 Spread 矩陣＝ 11×30×2 腿 ≈ 660 次估值；Crossover
   （#115）再加一張 comparator 矩陣 ≈ 330 次。而一次分析建的矩陣數量是
   **每個候選各一張**——實測 11 筆合約的 `xyz_v4_six_expiries.json` 就建了
   11 張矩陣、1,694 次腿估值【實測】，真實鏈的 `expiry_top10`（每期最多 10 檔
   × 最多 5 期）會是數十張。**每格成本乘以四位數的倍率，是硬約束。**
2. **要能在到期前的任意日期估值**。到期欄可以走內在價值（`at >= expiry` 分支
   已如此），但中間欄不行——這正是模型差異會顯現的地方。
3. **前端零金融計算**（專案紅線）。任何需要前端逐格算東西的方案直接出局。
4. **serverless 預算**：Vercel 函式上限 60 秒，前端 `request()` 逾時 90 秒
   （CLAUDE.md 環境節既有紀錄）。而且 `pyproject.toml` 的核心依賴刻意不含
   numpy／pandas（原文：「不把 pandas/numpy 拖進 serverless 函式」）——
   **向量化二項樹這條路要先推翻那個既有決定**。

**Crossover 額外要求**（`docs/Mvp-v3-appendix.txt` CROSSOVER SEMANTICS）：
對每個 (t, S) 同時算 `Spread Return(t,S)` 與 `Comparator Return(t,S)`，取
**相等的邊界**。comparator 依 #115 的裁示＝與買腿同 option type、同到期、
同履約價的裸買部位（Bear Put Spread → Long Put，不得寫死 Long Call）。
所以 Crossover 是一個**符號比較**：它對估值誤差的敏感度跟 Heatmap 的
cell 值不一樣，§7 專門量化。

---

## 3. 外部比較：OPC 一類工具與成熟公開程式庫怎麼做

### 3.1 OptionsProfitCalculator（本題的標竿）

本 repo 已有一份專門文件：`docs/research/opc-heatmap-comparison.md`
（2026-08-01），本節不重做，只補本次查證的增減。

**沿用該文已確認的一手（經搜尋索引）敘述**【索引轉述】：

- 定價模型＝Black-Scholes；「future option estimates, as all estimates on
  this site, are calculated using the Black Scholes formula」（本次搜尋再次
  命中同一段文字，與該文 2026-08-01 的記錄一致）。
- IV 由**該合約當下的市價與標的價反解**，且持有期間**恆定**：「Given a
  constant IV, the calculator will be correct in its price estimation,
  however since IV is a reflection of market sentiment ... it is impossible
  to predict what people will be thinking in the future.」（本次再次命中）。
- 多腿：「the estimated price of each option is calculated individually and
  combined」；格值＝ exit value − entry value；bid/ask 滑價與手續費不計。

**本次新增的兩點，兩點都要標疑義**：

- 「does not account for early assignment, bid-ask spreads, liquidity, or
  taxes」——這段摘錄出現在一次搜尋的結果彙整中，但**同一批連結同時包含
  `optionsprofitcalculator.com/faq.html` 與另一個名稱極相近的第三方網域
  `options-profit-calculator.com`**。我**無法**確定這句話屬於前者。
  【索引轉述，歸屬存疑，不得當作 OPC 的一手自述引用】。
- **股利**：本次以 `allowed_domains` 限定 `optionsprofitcalculator.com` 再搜一次，
  仍然**沒有**任何 FAQ 段落提到 dividend／股利處理。與
  `opc-heatmap-comparison.md` 當初的結論一致：**未能自一手資料確認**。

**對本題的結論**：OPC 這一類工具的公開自述停在「BS ＋ 每腿自反解的恆定 IV ＋
逐腿相加 ＋ exit−entry」。**它們公開承諾的東西裡，最重要的其實是「IV 由該合約
自己的市價反解」——那是價格錨定，不是模型選擇**。這一點本 repo 目前沒有做
（見 §4.2）。

### 3.2 optionlab（開源、逐字原始碼，本題最貼近的架構同類）

`rgaveiga/optionlab` 是一個公開 Python 套件，功能定義幾乎與本題一字不差：
「the profit/loss profile of the strategy on a **user-defined target date**」
（README，【一手原始碼】）。逐字讀它的原始碼：

- `optionlab/black_scholes.py::get_bs_info(s, x, r, vol, years_to_maturity, y=0.0)`
  ——`y` 就是年化股利殖利率，公式是
  `d1 = (log(s/x) + (r - y + vol²/2)·τ) / (vol·√τ)`，
  `call_price = s·e^{-yτ}·N(d1) - x·e^{-rτ}·N(d2)`。**即 Merton (1973) 股利
  殖利率調整版歐式 BS，q 是第一級輸入參數。**【一手原始碼】
- `optionlab/engine.py`：`data.use_bs.append(strategy.expiration != inputs.target_date)`
  ——到期日不等於目標日就走 BS，等於就走到期內在價值；`_run_option_calcs()`
  以 `target_to_maturity = (days_to_maturity[i] - days_to_target)/days_in_year`
  呼叫 `get_pl_profile_bs(..., inputs.dividend_yield, ...)`。
  **架構與本 repo 的 `scenario_leg_value` 完全同構：未到期走模型、到期走內在。**
  【一手原始碼】
- `inputs.model` 只有 `"black-scholes"` 與 `"array"` 兩種，而後者是算
  probability-of-profit 用的終端價格分布，**不是**另一個定價器。
  **整個套件沒有美式樹。**【一手原始碼】

### 3.3 QuantLib（成熟度／可得性的佐證）

【一手原始碼】QuantLib（`lballabio/QuantLib`）同時內建：

- `ql/pricingengines/vanilla/bjerksundstenslandengine.hpp`：
  註解逐字「Bjerksund and Stensland pricing engine for American options (1993)」。
- `ql/pricingengines/vanilla/baroneadesiwhaleyengine.hpp`：
  「Barone-Adesi and Whaley pricing engine for American options (1987)」。
- `ql/methods/lattices/binomialtree.hpp`：二項樹家族（含 CRR）。

這證明兩件事：**封閉式美式近似是業界標準工具箱裡的一等公民**（不是偏方），
而且**同一套函式庫把「近似」與「樹」並列**，代表選近似不是走捷徑，是在成本／
精度上做取捨。

### 3.4 Cboe 自己的計算器

【索引轉述，且部分結果來自第三方站台、歸屬存疑】搜尋索引指出 Cboe 官方
options calculator「automatically uses the binomial model when you select
American-style options」，輸入含 dividend yield。**但**該次搜尋回傳的連結多數
是第三方（pineify.app 等），只有一條指向 `cboe.com/education/tools/options-calculator/`
且無法一手開啟。因此這條**只當旁證**——真正有力的證據是 §4.3，我直接從 Cboe
自己的報價 feed 反推出他們用的是美式模型，那是【實測】。

### 3.5 小結：業界慣例長什麼樣

| | 定價模型 | IV | q | 美式 |
|---|---|---|---|---|
| OPC | BS【索引轉述】 | **由該合約市價自反解、期間恆定**【索引轉述】 | 未能確認 | 未能確認（一則存疑摘錄稱不處理 early assignment） |
| optionlab | Merton BSM（含 q）【一手原始碼】 | 呼叫端給 | **一級輸入**【一手原始碼】 | 無樹【一手原始碼】 |
| QuantLib | 全都有【一手原始碼】 | — | — | BS93／BAW／樹並列【一手原始碼】 |
| Cboe 官方計算器 | 美式選二項【索引轉述，歸屬存疑】 | — | 有 dividend yield 輸入【同上】 | 有 |
| Cboe 報價 feed 的 `theo`／`iv` | **美式**【實測，§4.3】 | 美式反解 | （其效果已含在 theo 裡） | 是 |
| **本 repo 現行** | **歐式 BS，q=0** | **直接抄 vendor 欄位（模型不明）** | **無** | 只有 `max(BS, 內在)` 下限 |

**這張表最重要的一列是「IV」那一欄**：唯一講清楚 IV 怎麼來的公開工具（OPC）
用的是**自反解**；本 repo 用的是**外部給的、模型未知的數字**。§4 證明這正是
+81.9% 那一格的來源。

---

## 4. 真實資料診斷：現行 q=0 在部署路徑上產生什麼

### 4.1 走引擎本人的端到端實測

把 `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（真實 TLT 2028-12-15
LEAPS call 報價，#110 建立）組成 `ChainSnapshot`，**呼叫
`service.run_with_snapshot()` 本人**（不是重寫版），`rate=0.0426`、
`rate_explicit=True`（期限對齊的 2.4 年 Treasury 量級，見
`docs/research/risk-free-rate-for-bs.md`）：

| 策略 | 首選候選 | 網格 | 引擎「今天 × 現價」格 | 誠實答案（現在最差成交平倉） |
|---|---|---|---|---|
| bull-call-spread | 買 90C ask 4.10／賣 130C bid 0.63，net_worst 3.470 | 11 × 30 | **+81.9%** | **−11.5%** |
| long-call | 85C ask 5.90 | 11 × 30 | **+81.4%** | **−4.2%** |

【實測】整條「今天」欄都被抬高：Long Call 那張在今天欄印出
`76.07:−9%, 81.11:+41%, 84.52:+81%, 91.20:+171% …`。

**「今天 × 現價」這一格有一個不需要任何模型就知道的正確答案**：標的還沒動、
你剛用 Ask 買進，你的部位價值只可能是「用 Bid 平掉」，即負的買賣價差。引擎
印 +81.9% 等於告訴使用者「你按下買進的瞬間就賺了八成」。這不是「精度不足」，
是**畫面上直接看得出來的錯**。

### 4.2 根因：不是少一項 q，是模型不一致

逐檔看引擎對每張 TLT call 的估值【實測】：

| 履約價 | Bid | Ask | vendor IV | 引擎（q=0 歐式）模型值 | 市場中價 | 高估 |
|---|---|---|---|---|---|---|
| 79 | 8.00 | 9.05 | 0.120 | 14.661 | 8.525 | **+72.0%** |
| 80 | 7.45 | 8.20 | 0.110 | 13.627 | 7.825 | **+74.2%** |
| 85 | 5.65 | 5.90 | 0.120 | 10.700 | 5.775 | **+85.3%** |
| 90 | 3.80 | 4.10 | 0.120 | 7.961 | 3.950 | **+101.5%** |
| 130 | 0.63 | 0.73 | 0.180 | 1.648 | 0.680 | **+142.4%** |

**同一份 IV，代進 q=0 歐式公式，全部高估 72%–142%。** 而如果反過來問「要多少
IV 才能讓 q=0 模型重現市價」，答案是 K=79／80／85 **無解**（#110 §3.1 的結論，
本次獨立重算確認），K=90 需要 0.0356、K=130 需要 0.1427——一組毫無結構、
且與 vendor 給的 0.11–0.18 差了幾倍的數字。

**這說明 vendor IV 與 q=0 歐式公式根本不是同一個模型的產物。** 反過來，在
q=4.5%（#110 的跨履約價經驗擬合值）下反解，得到
0.1315／0.1272／0.1314／0.1292／0.1806——**與 vendor 給的 0.12／0.11／0.12／
0.12／0.18 量級與形狀都對得上**【實測】。vendor 顯然用了含股利的模型。

### 4.3 直接證明 vendor IV 是**美式模型** IV（用 Cboe 自家欄位）

TLT 的 vendor 是 yfinance（該 fixture 的來源），無法直接驗證其模型。但主資料源
Cboe 的 delayed quotes feed 自己就帶 `theo` 與 `iv` 兩個欄位——拿真實的 758 筆
YETI 全鏈（spot 44.97，2023-08-11，r 取 5.4%，YETI 不配息故 q=0），把 vendor 的
`iv` 分別代進歐式 BS 與美式 CRR，看 `theo` 與市場中價落在哪邊【實測】：

| 樣本 | \|theo − 歐式\| 中位 | \|theo − 美式\| 中位 | 靠向美式 |
|---|---|---|---|
| 全部 put（n=233） | 0.0547 | 0.0313 | 190/233（82%） |
| **長天期價內 put（DTE>180 且 K>S，n=24）** | **0.6625** | **0.0332** | **24/24（100%）** |
| 全部 call（n=263） | 0.0310 | 0.0310 | 126/263（48%） |

| 樣本 | \|市場中價 − 歐式\| 中位 | \|市場中價 − 美式\| 中位 | 靠向美式 |
|---|---|---|---|
| 全部 put | 0.0353 | 0.0071 | 214/233（92%） |
| 長天期價內 put | 0.6180 | 0.0226 | 24/24（100%） |

**call 那一列 48% 恰恰是理論預測的結果**：無股利時美式 call 不提前履約、與歐式
同值（Merton 1973 的標準結果），所以兩者本來就分不出來——這反過來當成了這套
量測方法自身的對照組。

更直接的是反解 IV。取「歐式與美式差最大」的那一區（長天期價內 put，n=44）：

| | \|反解 IV − vendor iv\| 中位（vol pt） |
|---|---|
| 歐式反解 | 0.0491（r=5.0%）／0.0597（r=5.4%） |
| **美式反解** | **0.0029（r=5.0%）／0.0047（r=5.4%）** |

逐檔看更清楚【實測】：

| 合約 | vendor iv | 歐式反解 | 美式反解 |
|---|---|---|---|
| YETI240119P00050000 | 0.3953 | 0.4114 | **0.3981** |
| YETI240119P00055000 | 0.3898 | 0.4245 | **0.3931** |
| YETI240119P00057500 | 0.3888 | 0.4391 | **0.3926** |
| YETI250117P00050000（CRR400 精算） | 0.4174 | — | **0.4170** |
| YETI250117P00040000（CRR400 精算） | 0.4428 | — | **0.4424** |

最後兩列用 CRR N=400 精算，與 vendor 差 **0.0004 vol pt**——幾乎逐位元吻合。

**結論（【實測】導出，不需要任何外部文件背書）**：Cboe feed 的 `iv` 是美式模型
反解出來的。本 repo 的 `data/cboe.py` 直接把它塞進 `OptionContract.
implied_volatility`，`scenario_leg_value` 再把它代進歐式、無股利的 `bs_price`。
**兩端模型不同，中間沒有任何轉換。** 這就是 §4.1 那格 +81.9% 的機制。

### 4.4 順帶量化：既有的 `clamped_price` 不是美式修正

`option_chaser/valuation.py::clamped_price` ＝ `max(BS, 內在價值, 0)`，docstring
寫「American no-arbitrage floor」。實測它對美式溢價的回收率【實測，YETI 真實鏈】：

- 有美式溢價的 put：229 筆；**箝制真的生效的只有 46 筆**。
- 回收比例：中位數 **0.0%**、平均 14.4%、最大 99.0%。
- 殘餘（美式真值 − 箝制後）：中位 $0.0210、最大 $1.3512。

**它防的是「模型值低於內在價值」這種荒謬結果，不是提前履約權利的價值。**
文件與 docstring 若被理解成後者會誤導。（附帶：Bjerksund–Stensland 對真實鏈
496 筆全部 ≥ 內在價值，0 筆違反【實測】——換上去之後這個箝制會變成冗餘的
不變量檢查，可以保留但語意要改寫。）

### 4.5 美式溢價到底多大（決定「要不要處理美式」的量化依據）

真實 YETI 全鏈，q=0、r=5.4%，CRR N=800 美式 − Merton 歐式【實測】：

| 分群 | n | 溢價 $ 中位 | 佔美式價值 % 中位 | 相對半個買賣價差 |
|---|---|---|---|---|
| call DTE>180 | 55 | **−0.0000**（max +0.0026） | −0.00% | −0.00 |
| put DTE≤60 | 135 | +0.0162 | 0.63% | 0.15× |
| put 60<DTE≤180 | 47 | +0.2024 | 2.19% | 0.82× |
| put DTE>180 | 51 | +0.1665 | 3.46% | 1.61× |
| **put DTE>180 且價內** | 24 | **+0.6186** | **5.10%** | **3.14×** |
| **put DTE>180 且深價內（K>1.2S）** | 13 | **+1.1029** | **6.18%** | **6.26×** |

- **call 那一列的 −0.0000 / max 0.0026 就是離散誤差**，等於在真實資料上重現了
  「無股利美式 call 不提前履約」這個定理。
- **put 側則不是雜訊**：長天期價內 put 的美式溢價中位數是半個買賣價差的
  3.1 倍、深價內 6.3 倍。本 repo 既有的判準（`spread-synthetic-parity-check.md`
  §4.3：訊號小於自身交易成本就是雜訊）套用在這裡，結論是**這個溢價超過雜訊
  門檻數倍**。
- **這件事對 Heatmap 特別重要**：`price_axis` 在看空劇本會一路取樣到
  `spot × 1.10` 以下、`target × 0.85` 的深跌區——**put 買腿在那些格子裡正好
  變成深價內**。也就是說，歐式模型誤差最大的地方，恰好是 Heatmap 刻意要
  展示的地方。

---

## 5. 四個候選方法的真實資料量化比較

### 5.1 方法定義

| 代號 | 方法 | 說明 |
|---|---|---|
| **A** | 現行：歐式 BS，q=0，直接用 vendor IV | `clamped_price(...c.implied_volatility)` |
| **B** | Merton BSM ＋ q，**價格錨定** | 每腿的 IV 用**同一份快照的中價**、在同一個 q 下反解，再用同一條公式估值 |
| **C** | **Bjerksund–Stensland (1993) 美式近似 ＋ q，價格錨定** | 封閉解；`b = r − q`；`b ≥ r` 時對 call 恰好退化成 B |
| **D** | CRR 美式二項樹 ＋ q，價格錨定 | 對照基準（不建議 production） |

「價格錨定」是 B／C／D 共有的紀律：**用哪個模型估值，就用哪個模型反解 IV**。
這是 §3.1 的 OPC 作法，也是 §4 診斷出來的真正修法。

**CRR 實作驗證（先證明對照基準本身可信）**【實測】：
歐式極限收斂 O(1/N)（N=50 誤差 −0.048、100 −0.024、200 −0.012、500 −0.0048、
1000 −0.0024、2000 −0.0012）；q=0 的美式 call 與歐式 call 差 −2.5e-3（＝同 N 的
離散誤差量級，即定理成立）；美式 put > 歐式 put（+6.90%）。

**Bjerksund–Stensland 實作驗證**【實測】：
- q=0 的 call 與 Merton 歐式**逐位元相同**（差 0.00e+00，三個價位）。
- 教科書網格（174 組：S 80–120、T 0.25–2.5、q 0/4.5/8%、σ 15/35%、r 5%）
  對 CRR N=1200：中位 0.275%、p90 1.122%、**max 3.271%**。
- **真實 Cboe 鏈 496 筆**對 CRR N=800：中位 **0.092%**、p90 0.640%、
  **max 1.136%**；最難的一區（長天期價內 put，n=24）中位 0.550%、max 0.817%。
- 用 BS93 反解的 IV vs 用 CRR400 反解的 IV：差 +0.0035／+0.0030 vol pt
  （所以 §5.2 拿 CRR 當基準時共用同一組 IV 的作法不會因為這點差距而失真）。
- 需要兩個數值防護：σ→0 時 `beta` 爆炸（`S**beta` overflow）與
  `b_inf − b_zero → 0`。兩者各一行 early-return 即可，**要寫進實作票**。

### 5.2 精度：兩個真實部位，走引擎自己的網格

**CASE 1 — TLT 真實 LEAPS，Bull Call Spread 買 85C／賣 90C**
（T=2.416y、width 5.0、net_worst 2.100、net_mid 1.825、comparator Long Call
ask 5.90、目標價 110、網格 11×30＝330 格）：

反解 IV【實測】：q=0 下 **K=85 無解**、K=90 得 0.0356（即 A 這條路連價格錨定
都做不到）；q=4.5% 下 Merton 得 0.1314／0.1292、BS93 得 0.1278／0.1273。

| 「今天 × 現價」格（誠實答案 **−26.2%**） | Spread | Comparator |
|---|---|---|
| A 現行 | **+30.5%** | **+81.4%** |
| B Merton＋q | −13.1% | −2.1% |
| C BS93＋q | −13.1% | −2.1% |
| D CRR300（基準） | −12.8% | −1.5% |

| 對 D 的格差（pp） | Spread 中位／p90／max | Comparator 中位／p90／max |
|---|---|---|
| A 現行 | 14.28 ／ 35.14 ／ 43.25 | **52.04 ／ 119.26 ／ 143.48** |
| B Merton＋q | 1.44 ／ 8.89 ／ 37.67 | 0.27 ／ 4.18 ／ 13.90 |
| **C BS93＋q** | **0.18 ／ 1.73 ／ 4.47** | **0.07 ／ 0.81 ／ 1.63** |

**CASE 2 — YETI 真實 Cboe 鏈，Bear Put Spread 買 50P／賣 40P**
（T=1.438y、width 10.0、net_worst 5.200、net_mid 4.900、comparator Long Put
ask 10.50、目標價 36、網格 11×18＝198 格；YETI 不配息故 q=0，**這個案例
單獨隔離「美式」這一個變因**）：

反解 IV【實測】：歐式 0.4470／0.4565；BS93 0.4205／0.4453
（vendor 給的是 0.4174／0.4428——又一次確認 vendor 靠美式那邊）。

| 「今天 × 現價」格（誠實答案 **−11.5%**） | Spread | Comparator |
|---|---|---|
| A 現行 | −13.1% | −7.8% |
| B 歐式＋價格錨定 | −5.8% | −1.9% |
| C BS93 | −5.8% | −1.9% |
| D CRR300（基準） | −5.3% | −1.2% |

| 對 D 的格差（pp） | Spread 中位／p90／max | Comparator 中位／p90／max |
|---|---|---|
| A 現行 | 4.79 ／ 10.12 ／ 13.74 | 3.15 ／ 7.81 ／ 11.96 |
| B 歐式＋價格錨定 | 2.21 ／ 7.03 ／ 10.72 | 1.10 ／ 4.56 ／ 9.02 |
| **C BS93** | **0.33 ／ 0.54 ／ 0.81** | **0.51 ／ 0.68 ／ 0.81** |

**兩個案例合起來說的事**：

1. **光是價格錨定（A→B）就把誤差砍掉一半以上**，而且它讓「今天 × 現價」那格
   **依定義**回到市價。兩個案例都可以逐位元驗算【實測】：
   CASE 1 的 B 印 −13.1%，`net_worst × (1 − 0.131) = 2.100 × 0.869 = 1.825`
   ＝該部位的 `net_mid`；CASE 2 的 B 印 −5.8%，
   `5.200 × 0.942 = 4.900` ＝ `net_mid`。也就是說那一格從此只剩下一個意義：
   **你付掉的買賣價差**——這正是它應該表達的東西。
2. **但價格錨定救不了 put 的美式效應**：CASE 2 的 B 仍有中位 2.21pp、max 10.72pp
   的殘差，因為「把提前履約溢價塞進一個假的常數波動率」在 t=0 成立、往未來走
   就跟不上。
3. **C（BS93）把兩個案例的殘差都壓到 1pp 以下的中位數**，最大值也只有
   0.81–4.47pp。

### 5.3 成本：實測，不是估的

單核 CPython、stdlib math【實測】：

| | 每次估值 | 相對倍率 |
|---|---|---|
| 現行 `clamped_price`（q=0） | 0.93 µs | ×1.0 |
| Merton BSM（含 q） | 0.62–0.69 µs | ×0.7 |
| **Bjerksund–Stensland 1993** | **6.00 µs** | **×8.7**（對 Merton） |
| CRR N=100 | 1,748 µs | ×1,884 |
| CRR N=300 | 15,434 µs | ×16,631 |
| CRR N=500 | 42,724 µs | ×46,038 |
| CRR N=800 | 108,401 µs | ×116,807 |

一次性校準成本（**每腿一次，不是每格**）：Merton IV 二分法 30 µs／腿
（≈32 次 BS）；BS93 IV 二分法 343 µs／腿。

縮放到真實 Heatmap 工作量（11 價位 × N 日期欄，Spread 每格 2 腿）【實測】：

| 情境 | 矩陣 | 估值次數 | 現行 BS（0.93 µs） | **BS93（6.0 µs）** | CRR300 |
|---|---|---|---|---|---|
| ~3 個月（7 欄） | Spread | 154 | 0.14 ms | 0.92 ms | 2.38 s |
| ~1 年（13 欄） | Spread | 286 | 0.27 ms | 1.72 ms | 4.41 s |
| **2.4y LEAPS（29 欄）** | **Spread** | **638** | **0.59 ms** | **3.83 ms** | **9.85 s** |
| 2.4y LEAPS | Crossover comparator | 319 | 0.30 ms | 1.92 ms | 4.92 s |

（Merton BSM 比現行 `clamped_price` 略快——0.62–0.69 µs vs 0.93 µs，少一層
箝制分支——所以「換成 Merton」在成本上是**淨減少**，上表取現行值當保守上界。）

**而一次分析不是一張矩陣**。實測 `xyz_v4_six_expiries.json`（只有 11 筆合約、
最長 5 個月）：**11 張矩陣、847 格、1,694 次腿估值、引擎總耗時 22.7 ms**；同一份
玩具 fixture 全部改成 CRR300 就是 **26.1 秒**。真實鏈的 `expiry_top10`
（每期最多 10 檔 × 最多 5 期）＋ `candidates` ＋ `comparison` 是數十張矩陣，
LEAPS 的欄數又是這份 fixture 的四倍——**CRR 在 60 秒 serverless 上限下不可行，
差的不是常數因子，是量級。**

**「向量化就好了吧？」**：要 numpy。`pyproject.toml` 的核心依賴刻意排除
numpy／pandas（原文註解：「不把 pandas/numpy 拖進 serverless 函式」，且
`yfinance` 就是為此被移到 `yf` extra）。**走這條路要先推翻一個既有的、寫了
理由的決定**，那已經不是「最低工程成本」。

### 5.4 價格錨定之後，q 的**數值**還重要嗎？

這是我原本懷疑可以省掉 #110 校準工作的假設，**實測結果是：不能省**。
CASE 1（TLT）固定用 Merton、每個 q 都重新反解 IV，比較 Heatmap 格值【實測】：

| q | 對 q=4.5% 的格差（中位／p90／max, pp） |
|---|---|
| 3.0% | **9.26 ／ 22.62 ／ 47.29** |
| 4.5% | 0 ／ 0 ／ 0（基準） |
| 6.0% | 0.35 ／ 8.91 ／ 55.11 |

**q 抓錯 1.5 個百分點，Heatmap 中位數就差 9.26pp、尾端差 47pp。**
價格錨定保證的是 **t=0** 那一欄對，**不保證**未來欄對——q 決定的是 forward
的漂移，那是逐欄累積的。所以 §10 第 3 問的答案裡，q 的來源必須是真的校準
（#110 Method E），不能是拍腦袋的常數。

### 5.5 總表

| | A 現行 q=0 | B Merton＋q | **C BS93＋q** | D CRR 樹 |
|---|---|---|---|---|
| 成熟度／公開性 | — | Merton 1973，教科書標準；optionlab 一級參數【一手原始碼】 | **Bjerksund–Stensland 1993；QuantLib 內建引擎**【一手原始碼】 | CRR 1979；QuantLib 內建【一手原始碼】 |
| 「今天 × 現價」格 | **+81.9% / +81.4%（錯得看得出來）** | 依定義回到市價 | 依定義回到市價 | 依定義回到市價 |
| 對美式基準的格差（中位） | 4.79–14.28 pp | 1.44–2.21 pp | **0.18–0.33 pp** | 0 |
| Crossover 判錯格 | 5.1%–6.7% | 0.3%–3.5% | **0.0%** | 0 |
| 每格成本 | 0.93 µs | 0.62 µs | **6.0 µs** | 15,434 µs |
| 2.4y LEAPS 單張矩陣 | 0.59 ms | 0.44 ms | **3.83 ms** | 9.85 s |
| 新增依賴 | — | 無（stdlib） | **無（stdlib）** | numpy（否則不可行） |
| 新增程式碼量 | — | ~10 行 | ~40 行＋2 個數值防護 | ~30 行，但架構性不可行 |
| q=0 時的行為 | — | — | **對 call 逐位元退化成 B** | — |
| 主要殘留誤差 | 系統性、量級 100% | put 側美式溢價（max 10.7pp） | 近似誤差（真實鏈 max 1.14%） | 離散誤差（N=300 時 $0.0023） |

---

## 6. 與 #110 的異同

**同意，且本文獨立重現**：

1. q=0 對真實 TLT LEAPS 不可行（#110 §3.1 的 3/5 檔無解）——本次以獨立寫的
   反解器重算，K=79／80／85 確認無解【實測】。
2. 不採 Method D（put-call parity 直接萃取股利）。#110 §4 引
   `spread-synthetic-parity-check.md` 的 758 筆實算證明美式提前履約溢價會汙染
   parity；**本文 §4.5 用同一份資料獨立量化了那個汙染源本身**（長天期價內 put
   美式溢價中位 5.10%、深價內 6.18%），與該結論一致。
3. 不採 Method C（配息時間表預測）。
4. 方向上採「Merton 股利殖利率調整 ＋ 同快照校準 q」（#110 §7）。
5. **q 的數值必須真的校準**——#110 §3.3 強調 q 會隨快照變動、不能寫死常數；
   本文 §5.4 用 Heatmap 格值把這件事量化了（q 差 1.5pp → 中位 9.26pp），
   **強化**而非弱化 #110 的立場。

**補充／不同，三點**：

1. **#110 沒有指出 IV 來源的模型不一致，而那才是 +81.9% 的直接機制。**
   #110 的框架是「引擎的 carry 假設錯了」，修法是換公式。但即使換上 Merton＋q，
   **只要 IV 還是直接抄 vendor 欄位**，t=0 那格仍然不會回到市價——因為 vendor
   的 IV 是在**別的模型**下反解的。§4.3 用 Cboe 自家 `theo` 與 `iv` 證明了那個
   「別的模型」是美式含股利模型。**真正的修法是「用同一個模型反解 IV、再用同一
   個模型估值」，模型換不換是第二順位。** 這也正好是 OPC 公開自述的作法。
   實測支持：光做價格錨定（A→B）就把 CASE 2 的格差中位從 4.79pp 降到 2.21pp，
   **而 CASE 2 的 q 是 0，一項 carry 都沒改。**
2. **#110 的「Method B 公式」在 put 側不夠。** #110 §7 誠實寫了「這仍是歐式近似
   ＋經驗校準殖利率，不是完整美式定價模型，殘留誤差需揭露」。本文把那句話變成
   數字：**CASE 2 的殘留是中位 2.21pp、max 10.72pp、Crossover 判錯 3.5%**。
   並且指出一個 #110 沒評估的選項——**封閉式美式近似（Bjerksund–Stensland）
   把殘留壓到中位 0.33pp、Crossover 判錯 0%，代價只是每格 6 µs**。也就是說
   「不做完整美式定價」這個妥協**不需要**被接受，它的價格比想像中便宜得多。
3. **#110 只評估了校準的計算成本（「相對現有規模可忽略」），沒有評估估值原語
   本身在 Heatmap 規模下的成本。** 本文補上：這是本題唯一真正會把方案排除掉的
   維度（CRR 樹一張 LEAPS 矩陣 9.85 秒 vs 60 秒 serverless 上限）。#110 §6 的
   總表沒有樹這一列，本文把它放進來、量化、然後有依據地排除它。

---

## 7. Crossover 專屬的含義（#115／#116 的直接輸入）

Crossover 不是讀 cell 值，是讀 **`sign(Spread Return − Comparator Return)`**。
兩邊共用同一條買腿，誤差會部分抵銷——所以它對模型的敏感度**低於** cell 值，
但**不是零**【實測】：

| | CASE 1（TLT，330 格） | CASE 2（YETI，198 格） |
|---|---|---|
| A 現行 vs 美式基準 | **22/330（6.7%）** | **10/198（5.1%）** |
| B Merton／歐式＋價格錨定 | 1/330（0.3%） | 7/198（3.5%） |
| **C BS93** | **0/330（0.0%）** | **0/198（0.0%）** |

另外量到一件對 #116 版面有用的事：判錯的格子**幾乎全部貼著邊界**。把 CASE 2
的勝負圖印出來（列＝價格高到低，欄＝日期早到晚，`S`＝Spread 勝、`C`＝
comparator 勝、`*`＝兩模型不一致）【實測】：

```
  49.47 C*SSSSSSSSSSSSSSSS
  47.58 CCSSSSSSSSSSSSSSSS
  44.97 CCCSSSSSSSSSSSSSSS
  43.81 CCC*SSSSSSSSSSSSSS
  41.92 CCCC*SSSSSSSSSSSSS
  40.03 CCCCC*SSSSSSSSSSSS
  38.15 CCCCCC*SSSSSSSSSSS
  36.00 CCCCCCCCSSSSSSSSSS
  34.37 CCCCCCCC*SSSSSSSSS
  32.49 CCCCCCCCC**SSSSSSS
  30.60 CCCCCCCCCCC**SSSSS
```

**邊界的「形狀」（單調斜向、往低價往後推）在四個模型下都一樣；模型誤差表現為
邊界左右位移約一欄。** 這對 #116 有兩個含義：

- 附錄那句「Do not assume the boundary is straight / monotonic ... Render the
  actual calculated result」在真實資料上是對的——邊界確實不是直線，而且會逸出
  網格（CASE 1 的兩個模型下 Spread 勝的格數分別是 77 與 100 之於 330，差異
  不小）。
- **但「用現行 q=0 引擎先做 Crossover、之後再修估值」會讓 5–7% 的格子畫在錯的
  一邊**，而且錯的正是**邊界附近**——也就是使用者唯一會盯著看的地方。
  **#115 被 #113 擋這個依賴設計是對的，本文的數據支持維持它。**
  （若需求方基於排程想解除這個依賴，代價已量化：約 5–7% 貼邊格子會反向，
  之後修估值時邊界會移動——這是可以知情選擇的取捨，不是未知風險。）

---

## 8. 施工影響與 blast radius（#113 票面目前沒寫到的部分）

逐條追過 `option_chaser/` 之後【實測／原始碼查證】：

**會變的：**

1. **全部 Heatmap 格值**（`matrix.cells`）——這是目的，#113 AC 已寫。
2. **Greeks**：`leg_greeks` 目前是 q=0 歐式解析式。換模型後 delta 應為
   `e^{-qT}·N(d1)`。連帶影響 `_v4_fields` 的 `net_delta`／`vega_per_pt`／
   `decay_30d_return` 與 `effective_leverage`。
3. **⚠ 單腿候選的「選取結果」會變，不只是數值變。**
   `ranking.rank()` 用 `classify(v.delta, p.delta_bands)` 把單腿候選分成
   conservative／balanced／aggressive 三組、**各取 top-N**。實測 TLT 五檔在
   `delta_bands=(0.35, 0.65)` 下的重分級【實測】：

   | 履約價 | 現行 delta | Merton（q=4.5%，重反解 IV） | 位移 | 現行分級 | 新分級 |
   |---|---|---|---|---|---|
   | 85 | 0.7306 | 0.4649 | −0.2657 | conservative | **balanced** |
   | 80 | 0.8435 | 0.5704 | −0.2731 | conservative | **balanced** |
   | 79 | 0.8431 | 0.5893 | −0.2538 | conservative | **balanced** |
   | 90 | 0.6211 | 0.3630 | −0.2581 | balanced | balanced |
   | 130 | 0.1513 | 0.0706 | −0.0807 | aggressive | aggressive |

   （`classify()` 的門檻方向：`|delta| > 0.65` → conservative、
   `< 0.35` → aggressive、其餘 balanced。**「現行 delta」那一欄可以獨立
   對帳**：fixture 自帶的 `delta_bucket` 欄位寫的是
   「conservative (Delta 0.72)」/「balanced (Delta 0.61)」/
   「aggressive (Delta 0.14)」，與我算出的 0.7306／0.6211／0.1513 吻合
   ——證明這組 delta 確實重現了引擎現行口徑，不是我另算的一套。）

   五檔中三檔跨越 0.65 這條線。**這是 selection semantics 的變動**，
   #113 現行 AC 只寫「數值變、語意不變」，涵蓋不到這件事。**需求方需要明確
   裁示**：接受單腿候選名單改變，或另外把分級用的 delta 凍結在舊口徑
   （後者會製造「顯示的 delta 與分級用的 delta 不同」這種內部不一致，
   我不建議，但那是需求方的決定）。
   另外 `ContractValuation.scenario_values`／`baseline_value`／`l2` 是在
   **錨點日**（`p.anchor`，未到期）估的，所以**單腿的 in-band 排序也是模型
   相依的**。

**不會變的（好消息，可以縮小 #113 的驗收範圍）：**

4. **Spread 的排名完全不受影響。** `ranking.rank_spreads()` 依
   `spread_baseline_return` 排序，而 `evaluate_spread` 的 `scenario_values`
   是在 **該 Spread 自身到期日**估的（T3／#17 的既有裁示），
   `scenario_leg_value` 在 `at >= expiry` 走內在價值分支——**與定價模型無關**。
5. 因此 **`best_return`／`representative_candidate`／劇本庫卡片數字不變**
   （皆由 spread `baseline_return` 導出）。
6. **V9 的 Spread 成本走勢圖不會斷層**：`store.spread_cost_history` 取的
   `cost` ＝ `scenarios.natural_cost()` ＝ `long_leg.ask − short_leg.bid`，
   純市場報價、不經模型。
7. **`clamped_price` 的內在價值下限變成冗餘**（BS93 對真實鏈 496 筆 0 違反）
   ——可保留當不變量斷言，但 docstring 的「American no-arbitrage floor」措辭
   要改，它從來就不是美式修正（§4.4）。

**架構要點（影響工程成本估算）**：IV 反解是**每腿一次**（30–343 µs），
不是每格。實作時應在建 `CandidateView` 時就把校準好的 (q, σ) 掛在腿上，
矩陣迴圈維持成 `(S, t)` 的純函式——這樣 §5.3 的成本表才成立。

**必然連動**：4 份 golden fixtures ＋ `contracts/analysis_sample.json` 重產
（#113 AC 已列）；`report.py` 的「模型限制」尾註措辭；#112 剛做完的
`rate_used`／`rate_curve_date` 透明化模式應該複製一份給 q
（讓使用者看得到「這次用的 q 是多少、怎麼來的」——#110 §7 也提了同一件事）。

---

## 9. 侷限與無法一手查證的清單

**無法一手查證（沙箱出口限制；reviewer 若要覆核需在可連網環境執行）**：

1. **OPC 的一手 FAQ 全文**。`optionsprofitcalculator.com` CONNECT 403、
   WebFetch `EGRESS_BLOCKED`。§3.1 的引文全部是搜尋索引摘錄，與
   `opc-heatmap-comparison.md`（2026-08-01）互相印證，但**沒有人逐字讀過
   原頁**。特別未確認：**股利處理**（兩輪搜尋、含限定網域搜尋皆無結果）、
   **美式提前履約**（唯一一則相關摘錄的網域歸屬存疑，見 §3.1）、
   **無風險利率數值**、**天數慣例**。
2. **OCC 的一手規則文件**。§ 相關主張——「ordinary cash dividend 不調整
   契約條款」——來自搜尋索引摘錄，指向
   `theocc.com/.../Interpretative-Guidance-on-the-Adjustment-Policy-for-Cash-Dividends-and-Distributions.pdf`
   與數則 Federal Register 公告，**兩者皆無法開啟**。這條主張是「為什麼必須
   建模 q」的制度理由；本文的結論**不依賴**它（結論由 §4 的實測獨立成立），
   但要寫進產品說明的話應由需求方覆核原文。
3. **Cboe／OCC 的合約規格原件**（equity/ETF options 為美式、實物交割）。
   §3.4 為索引轉述。**但本文對「Cboe 的模型是美式」的主張不靠這個**——
   §4.3 是直接從 Cboe 自家 `theo`／`iv` 欄位量出來的【實測】。
4. **Black-Scholes (1973)／Merton (1973)／Cox-Ross-Rubinstein (1979)／
   Bjerksund-Stensland (1993) 的原始論文**。arxiv／jstor／sec.gov／wikipedia
   全部不可達；GitHub 上未找到可用鏡像（`mcp__github__search_code` 對 PDF
   內容不索引，數次以檔名／倉庫搜尋皆無結果）。§3.3 以 **QuantLib 原始碼的
   類別名稱與註解**當作這些方法「成熟且被標準函式庫採用」的【一手原始碼】
   證據，**沒有**引用任何論文的逐字內容。本文用到的公式（Merton 的
   `d1 = (ln(S/K) + (r−q+σ²/2)T)/(σ√T)`、CRR 的 `u=e^{σ√dt}, d=1/u,
   p=(e^{(r−q)dt}−d)/(u−d)`、BS93 的 trigger price 形式）**皆為我依標準
   形式實作，並以數值自驗**（歐式極限收斂、q=0 美式 call 等於歐式、
   美式 put 大於歐式），**未逐字比對原文**。

**量化本身的侷限（誠實揭露，不誇大）**：

5. **兩個部位、兩個標的、各一個快照。** CASE 1 是 TLT（配息 ETF、call、
   q 主導），CASE 2 是 YETI（不配息個股、put、美式主導）——刻意選成互相
   隔離變因，但**不是**橫斷面統計。「BS93 中位 0.18–0.33pp」是這兩個案例的
   數字，不是保證的誤差界。
6. **q=4.5% 沿用 #110 的經驗擬合，本文未重新校準**，也沿用了 #110 §3.3
   自己列的侷限（單一快照、5 檔合約、扣掉離群只剩 4 檔）。
7. **YETI 的 r=5.4% 是我依 2023-08 的 1 年期 UST 量級設定的**，非該日
   Treasury 原始資料。已用 r=5.0% 重跑 §4.3 的判別測試，結論方向不變
   （歐式 0.0491 vs 美式 0.0029），但個別金額對 r 有敏感度。
8. **YETI 假設 q=0**（該公司當時不配息，屬常識性理解，非本次一手查證）。
   若實際有小額配息，§4.5 的 put 美式溢價會被略微低估（q>0 會讓美式 put
   溢價更大），方向不利於歐式，不影響結論。
9. **§5.2 的「基準」是 CRR N=300 且共用 BS93 反解出的 IV**。理想的基準應是
   「用 CRR 自己反解 IV 的 CRR」；已量測兩者 IV 差 0.0030–0.0035 vol pt
   （§5.1），故此簡化對 B／C 的**相對**比較無實質影響，但對 C 的絕對誤差
   有輕微有利偏誤，讀者應以「C 的誤差 ≲ 1pp」而非「恰好 0.18pp」理解。
10. **TLT fixture 的 `reported_iv` 只有兩位小數**（0.11／0.12／0.18，抄自
    `tlt_report.md` 的顯示值），無法用來精細判別 yfinance 的模型；§4.2 只用
    到「量級與形狀對得上 q>0」這種粗判。

---

## 10. 六問六答（決策用）

### 10-1. 推薦 Option Chaser 採用哪一個？

**Bjerksund–Stensland (1993) 美式近似封閉解，帶連續股利殖利率 q，
並以「同快照、同模型逐腿反解 IV」價格錨定。**

作為**單一估值原語**取代 `bs_price`／`clamped_price`：

```
american_price(option_type, S, K, T, r, q, sigma)
```

它在 `b = r − q ≥ r`（即 q ≤ 0）時對 call **逐位元退化成 Merton 歐式**
（實測差 0.00e+00），所以它**涵蓋**方案 B 而不是多維護一套模型。

**可接受的最小版本（若需求方要最小 diff）**：只做方案 B（Merton＋q＋價格
錨定）。代價已量化：Crossover 判錯 0.3%–3.5%、put 部位 Heatmap 格差
中位 2.21pp／max 10.72pp。這是知情取捨，不是未知風險。

**明確不建議**：CRR／任何二項樹當 production 估值器（§5.3，量級問題，
且要引入被刻意排除的 numpy）。**但建議把 CRR 留在測試裡當精度對照基準**
——本文所有精度數字都是這樣產生的，#113 的驗收測試可以沿用同一手法。

### 10-2. 為什麼？

1. **現況是畫面上看得出來的錯，不是精度問題**：引擎本人在真實 TLT 資料上，
   「今天 × 現價」印 +81.9%，誠實答案 −11.5%（§4.1）。
2. **根因是模型不一致，修法是價格錨定**：vendor IV 是美式含股利模型反解的
   （§4.3，以 Cboe 自家 `theo`／`iv` 證明），卻被代進歐式無股利公式。
   「用同一個模型反解、再用同一個模型估值」讓 t=0 依定義回到市價——這正是
   OPC 唯一公開承諾的作法（§3.1）。
3. **q 必須有、且數值要對**：q=0 對真實 TLT LEAPS 在數學上無解（§4.2，
   與 #110 一致）；且價格錨定**不能**讓 q 的數值變得無所謂——q 差 1.5pp，
   Heatmap 中位差 9.26pp（§5.4）。
4. **美式對 put 側不是雜訊**：長天期價內 put 的美式溢價是半個買賣價差的
   3.1 倍、深價內 6.3 倍（§4.5），而 Heatmap 的深跌欄正好把 put 買腿推進
   那一區。既有的 `clamped_price` 回收不了它（中位回收 0.0%，§4.4）。
5. **成本便宜到不構成理由**：BS93 一張 2.4 年 LEAPS Spread 矩陣 3.83 ms
   （CRR300 是 9.85 秒）；純 stdlib、無新依賴、~40 行封閉解。
6. **成熟且公開**：QuantLib 內建 `BjerksundStenslandApproximationEngine`
   （【一手原始碼】），與 Barone-Adesi–Whaley、二項樹並列在同一個工具箱裡。
7. **它把 Crossover 的判錯清成 0**（兩個真實案例、528 格，§7）。

### 10-3. 需要什麼輸入資料？

**全部已經在手上，不新增任何外部資料源**：

| 輸入 | 來源 | 狀態 |
|---|---|---|
| S（標的價） | `ChainSnapshot.spot` | 現成 |
| K、到期日、option type | `OptionContract` | 現成 |
| **r（期限對齊）** | `ratecurve.py` ＋ `leg_rate(p, expiry)` | **已解決**（`risk-free-rate-for-bs.md`；par→continuous 近似 1M–3Y <1bp，#110 §5 已獨立覆核） |
| **σ（每腿）** | **不再直接抄 vendor 欄位**：用同一份快照的中價、在同一個模型下反解 | 需要一個二分法求解器（30–343 µs／腿，一次性） |
| **q（每到期日或每快照一個）** | **#110 的 Method E**：同到期日、同側（call）的多筆真實報價，擬合出讓跨履約價 IV 最一致的 q | **需要需求方核准 #110 的建議**（#113 既有的人工裁示閘門） |

**不需要**：股利時間表、外部股利殖利率 API、歷史資料、任何新網域。

### 10-4. Fallback 怎麼運作（輸入拿不到時）？

分層，全部「降級 ＋ 誠實標示」，比照 #112 剛做完的
`rate_used`／`rate_curve_date`／`rate_curve_stale` 透明化模式：

1. **q 校準成功**（該到期日有足夠筆數的流動同側報價，#110 §7 說是 3–4 筆
   起跳）→ 正常路徑。
2. **該到期日筆數不足** → 沿用同一份快照中筆數足夠的**最近到期日**擬合出的 q。
   理由：carry 是**標的**的性質，不是到期日的性質——TLT 的配息殖利率不會因為
   你看哪一期而不同。（【本文推導】，需求方可否決。）
3. **整份快照都校準不出來** → **退回現況**（q=0 ＋ vendor IV，即今天的行為），
   並在候選契約上帶一個明確旗標，讓 UI 說得出「這組估值未經 carry 校準」。
   **不要**在這種情況下悄悄改用 q=0 ＋ 價格錨定——§4.2 已證明 q=0 下多數
   近價位 LEAPS call 的 IV 反解**無解**，那條路會直接失敗而不是降級。
4. **單腿層級的反解失敗**（市價落在模型的可行區間外，例如報價陳舊或錯價）
   → 該腿沿用 vendor IV 並標記，**不要**用外插或猜的數字填補
   （沿用本專案「缺席就如實缺席、不偽造數值」的既有原則，見 #115 AC）。

**【本文推導，明確標為「超出 #110 範圍、不在本次建議內」】**：另有一個
「可行性下限」作法——取能讓所有腿的 IV 反解都可行的最小 q。它便宜且確定，
但**那是一個新的校準方法**，本文的 guardrail 明訂不發明新校準法，故僅記錄
存在、不建議在 #113 採用。需求方若想要，應另開研究票。

### 10-5. 對 Heatmap／Crossover 的施工影響

**估值層（真正的改動很小）**：

- 新增一個純函式 `american_price(type, S, K, T, r, q, sigma)`（~40 行 ＋
  2 個數值防護：`beta` 過大、`b_inf − b_zero → 0`，兩者實測會 OverflowError，
  必須寫進 AC）。`scenario_leg_value` 改呼叫它。
- `AnalysisParams` 新增 q 相關欄位（值 ＋ 來源 ＋ 是否成功校準），比照
  `rate_curve_used`／`rate_curve_date`／`rate_curve_stale` 三態的既有形狀。
- **校準每腿一次、掛在腿上**；矩陣迴圈維持 `(S, t)` 純函式——這是 §5.3 成本
  數字成立的前提，也是唯一的架構要求。

**Heatmap（#109 已完成的部分）**：
`price_axis`／`date_axis`／`move_pct`／右側 ±% 軸**完全不受影響**——那些是
座標軸與市價衍生量，不經估值。變的只有 `cells` 的值。
執行成本：2.4 年 LEAPS 單張矩陣 0.59 ms → 3.83 ms；一次分析數十張矩陣仍在
百毫秒量級，遠低於 60 秒上限（§5.3）。

**Crossover（#115／#116）**：

- #115 的 comparator 矩陣是**同一個原語再跑一次單腿**，多 319 次估值／
  1.92 ms（LEAPS）。無架構影響。
- #116 的 overlay 是前端對兩個矩陣做**相等比較與內插**——本方案不改變那個
  契約形狀，前端零金融計算的紅線維持成立。
- **#115 被 #113 擋的依賴應該維持**：實測現行引擎會把 5.1%–6.7% 的格子畫在
  邊界的錯誤一側，而且錯的都是貼著邊界的格子（§7）。

**⚠ 一個 #113 票面沒寫、必須先裁示的副作用**：
**單腿（Long Call／Long Put）候選的 delta 分級會位移，選出來的候選會不同**
——TLT 五檔中三檔從 conservative 掉到 balanced（§8）。
**Spread 的排名不受影響**（`rank_spreads` 吃的是到期日內在價值，T3／#17
的既有裁示），`best_return`／`representative_candidate`／劇本庫卡片
／V9 成本走勢圖**皆不變**（§8）。

### 10-6. 這樣夠不夠直接進 `/to-spec`？還是有東西未決？

**方法選型這一題已經收斂到可以決策**：候選、真實資料量化、成本、blast radius
都在上面，沒有需要再研究的技術未知。

**但不建議直接進 `/to-spec`，因為有三個需求方裁示點**（都很小、都已量化，
一次回覆即可解決）；#113 本來就掛著「需求方核准 #110 建議」的人工閘門，
這三點應該一起裁示：

1. **核准 #110 的 q 校準方法（Method E）**——#113 既有的閘門。本文 §5.4 補充
   了「q 的數值即使在價格錨定後仍然重要」的量化，支持這個校準是必要的。
2. **BS93 還是只做 Merton？** 本文建議 BS93；只做 Merton 的代價已量化
   （Crossover 判錯 3.5%、put 部位格差 max 10.72pp）。需求方若偏好最小 diff，
   選 Merton 是合理的知情決定，但那時應在「模型限制」揭露裡寫明 put 側的殘留。
3. **單腿 delta 分級位移怎麼處理？**（§8 第 3 點）接受候選名單改變，或凍結
   分級口徑。這是 selection semantics，#113 現行 AC 涵蓋不到，**不裁示就施工
   會踩到「不得改變既有 ranking／selection 語意」那條慣例**。

**另外兩件不擋施工、但應同時記錄的事**：

- Greeks 要不要一起換成 Merton 口徑（換了才自洽；不換就要在文件裡寫明
  「顯示的 Greeks 與估值不同模型」）。
- q 的透明化顯示（比照 #112 的 `rate_used`／`Curve date`），#110 §7 也提過。

**§9 的外部查證缺口（OPC 一手 FAQ、OCC 原件、原始論文）都不擋這個決定**
——本文的結論由 §4／§5 的真實資料實測獨立成立，外部來源只提供「業界慣例
長這樣」的旁證。

---

## 11. 引用清單

**本次新產出（scratchpad，未進 repo；任何人可依 §5 的參數重寫重跑）**：
CRR 二項樹、Merton BSM、Bjerksund–Stensland 1993、IV 二分法求解器，以及
六支量測腳本（YETI 全鏈掃描、vendor 模型判別、部位層 Heatmap 比較、成本
基準、引擎端到端）。**依 guardrail，本票只留下這一份研究文件，程式碼不進
repo**；#113 若被核准，實作與其驗收測試屬該票範圍。

**真實資料（皆為 repo 內既有或已記錄出處）**：
- `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（#110 建立，源自
  `tlt_report.md`）
- `https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json`
  ——真實 Cboe delayed-quotes 全鏈 758 筆，出處由
  `docs/research/spread-synthetic-parity-check.md` 記錄，本次重新下載成功
- `tests/fixtures/treasury_csv_sample.txt`（本文未直接使用，r 的處理沿用
  既有結論）

**本 repo 既有研究（直接引用，未重做）**：
- `docs/research/valuation-carry-method-comparison.md`（#110）——本文 §6 的
  比較對象
- `docs/research/opc-heatmap-comparison.md`（2026-08-01）——OPC 的既有調查，
  §3.1 沿用並補充
- `docs/research/spread-synthetic-parity-check.md`（R4／#99）——美式 parity
  汙染的真實資料實算；YETI 全鏈出處
- `docs/research/risk-free-rate-for-bs.md`（T12-A）——r 已解決
- `docs/research/cboe-field-semantics.md`——Cboe 欄位語意

**外部一手原始碼（本次逐字讀取，經 `raw.githubusercontent.com`）**：
- `rgaveiga/optionlab`：`optionlab/black_scholes.py`、`optionlab/engine.py`、
  `README.md`——Merton BSM 含 `y`（股利殖利率）、target-date 估值架構、
  無美式樹
- `lballabio/QuantLib`：`ql/pricingengines/vanilla/bjerksundstenslandengine.hpp`、
  `ql/pricingengines/vanilla/baroneadesiwhaleyengine.hpp`、
  `ql/methods/lattices/binomialtree.hpp`——封閉式美式近似與二項樹在標準函式庫
  中並列

**搜尋索引轉述（非一手，逐條標明；歸屬存疑者已於 §3.1／§3.4 標出）**：
- `https://www.optionsprofitcalculator.com/faq.html`——BS 公式、IV 由市價反解、
  constant IV、逐腿相加、exit−entry、bid/ask 與手續費不計
- `https://www.theocc.com/getmedia/.../Interpretative-Guidance-on-the-Adjustment-Policy-for-Cash-Dividends-and-Distributions.pdf`
  ＋ 數則 Federal Register OCC 規則公告——ordinary cash dividend 不調整契約條款
- `https://www.cboe.com/exchange-traded-stock/equity-options-spec/`、
  `https://www.cboe.com/exchange-traded-stock`——equity／ETF options 為美式、
  實物交割
- `https://www.cboe.com/education/tools/options-calculator/`——官方計算器對
  美式選用二項模型、含 dividend yield 輸入（**同批搜尋結果多為第三方站台，
  歸屬存疑，僅作旁證；本文對「Cboe 用美式模型」的主張以 §4.3 的實測為準**）

**學術方法（依標準形式實作並數值自驗，未逐字比對原文——見 §9 第 4 點）**：
- Merton, R. C. (1973)——股利殖利率調整 BS
- Cox, J., Ross, S., Rubinstein, M. (1979)——二項樹
- Bjerksund, P., Stensland, G. (1993)——美式近似封閉解
- Barone-Adesi, G., Whaley, R. (1987)——另一個成熟美式近似（本文未量測，
  QuantLib 同樣內建，需求方若想比較可另行評估）

**本 repo 程式碼（分析對象，未修改）**：
`option_chaser/valuation.py`、`option_chaser/matrix.py`、
`option_chaser/service.py`、`option_chaser/ranking.py`、
`option_chaser/scenarios.py`、`option_chaser/store.py`、
`option_chaser/models.py`、`pyproject.toml`
