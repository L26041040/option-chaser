# 專業機構選擇權策略報告的版型慣例——兼論本產品「📄 分析報告」的改版方向

研究日期：2026-08-04。對應票號：R1（[#49]），上游 spec [#47]，
反饋來源 `docs/user-feedback-v3.md` 第 10 點（「分析報告我覺得還沒對齊華爾街會
發行的那種分析報告，請跑一下 research，看人家專業的怎麼呈現的」）。
下游施工票：V8（[#56]）。

## 0. 取材限制聲明

本沙箱的出口 proxy 對金融／法規類網站的**直接抓取一律回 403**
（CONNECT tunnel policy denial）。本次實測遭拒者包含 `finra.org`、
`sec.gov`、`cdn.cboe.com`、`theocc.com`、`cfainstitute.org`、
`morganstanley.com`、`asx.com.au`；**且本次 WebFetch 對任何網域皆回 403**
（連 `en.wikipedia.org` 亦然），故與前一份調查
（`docs/research/option-chain-data-sources.md`）相比，本次連「抓網頁再逐字引用」
這條路都不可用。

因此本文**全部一手資料均來自搜尋引擎索引的官方頁面摘錄**，下文一律標為
**〔索引轉述〕**。凡屬索引摘錄中出現的近似逐字片段，標為
**〔索引轉述・近逐字〕**；凡無法以任何方式確認者，一律列入 §6「未能查證的事項」，
不寫進 §3／§4 的建議依據。

**這對結論的影響**：§3 的歸納建立在四個彼此獨立、且互相印證的來源家族上
（寫作指引／課綱與教育機構／實際發行的 trade idea／專業平台 UI），交叉一致的
部分可信度高；但**任何單一機構報告的實際排版細節（字級、欄寬、頁面順序）本文
無法證實**，故 §4 的建議只落在「章節順序、指標選取、表格與文字配比、語氣」
這幾個交叉印證得到的層次，不臆測視覺細節。

## 1. 結論摘要（給 V8 的五條）

1. **結論先行，方法論墊底。** 專業報告一律「執行摘要／建議 → 論據 → 風險 →
   估值方法 → 免責」；本產品目前是**完全相反**的順序——`option_chaser/report.py`
   先印 `[使用者假設]`／`[市場資料]`／`[模型假設]`／`[過濾統計]`／`[配對統計]`
   五個區塊共 30 行前言，第一組候選的淨成本要到**第 34 行**才出現
   （行號實測自 `contracts/analysis_sample.json` 的 `results[0].report_text`）。
   **這是本次最大、也最單純的落差**（§3.1、§4.1）。
2. **交易建議要有一句話的「標準句型」。** 業界公開發行的 trade idea 有高度固定
   的一句話格式：`買 <到期> <買K>/<賣K> <結構>，成本 $X → 損益兩平 $Y →
   最大獲利 $Z`（§2.3）。本產品目前沒有任何一句話結論，資訊全散在條列中。
3. **「最大損失」必須與「最大獲利」同框出現。** 這是所有來源家族的交集：教育
   機構的策略卡、專業平台的策略單、法規對溝通內容的要求，三者都把
   max profit／max loss／breakeven 視為**同一組不可拆的三件套**（§2.2、§2.4、§2.5）。
   本產品的純文字報告目前**只印最大獲利，不印最大損失**——雖然
   `max_loss_per_contract` 這個欄位在契約裡早就有（見 §4.2），純文字報告沒用它。
   ⚠ 例外：Long Call 的 `max_profit` 依定義序列化為 `null`（`store.py:357-358`，
   獲利無上限），V8 該格必須顯示「無上限」，不可留白或顯示 0。
4. **講機會就要同時講風險，不得單獨出現。** FINRA 對選擇權溝通的要求是
   「任何提到潛在機會或優勢的敘述，都必須有對應風險敘述來平衡」（§2.5）。
   本產品不受該規範管轄（非美國經紀商、非會員），但這是很好的品質標準：
   **「劇本報酬率 +566%」不該單獨成立，要和「情境最壞 −100%」並排。**
   好消息是我們的韌性向量早就算好了最壞情境，只是它埋在第七層。
5. **表格為主、散文為輔。** 專業報告的關鍵指標走表格，散文只負責「為什麼」；
   本產品目前**除了 P/L 矩陣是對齊表格之外，其餘全是 `- xxx: yyy` 的條列散文**，
   既難掃讀也浪費新前端已經有的表格能力（§3.3、§4.3）。

**範圍界線**：以下建議**全部只動呈現層**——重排既有欄位、加上呈現層純算術
（除法、百分比、單位換算）。凡需要引擎新增計算或新增資料（IV 百分位、獲利機率
等）者，一律列在 §5「明確不做」，不混進 V8。

**惟有一項要事先知道**：其中四項內容（買價指引 L2/L3、評語 cons、方法論尾註、
免責）目前**只以散文形式活在 `report_text` 字串裡，沒有結構化欄位**，V8 需要
順手替它們補上序列化（值都已算好，不是新增計算）。這是 R1 在核對契約時發現的，
不是原本估的工作量——詳見 §4.2 A2。

## 2. 來源盤點（四個獨立來源家族 A–D，＋法規面約束 E）

### 2.1 家族 A：賣方研究報告的寫作指引

多份業界訓練教材與 CFA Institute 的報告架構描述交叉指向同一個骨架〔索引轉述〕：

- 報告開頭是**執行摘要**，內容為「為什麼發這份報告、建議採取什麼行動、關鍵
  催化劑」，並帶上**建議評級與目標價**〔索引轉述・近逐字〕。
- 完整報告的章節順序被描述為：**Executive Summary（含建議與目標價）→
  Investment Thesis（含催化劑）→ Business Description → Industry Analysis →
  Financial Analysis → Valuation → Risk Factors → ESG → Disclosures and
  Disclaimers**〔索引轉述〕。
- 短篇 note（flash note）只有 1–2 頁，內容是「評級 ＋ key takeaways」，即
  **執行摘要單獨成篇**〔索引轉述〕。
- 風險章節的定位是「可能推翻投資論點的發展」〔索引轉述〕——即**風險是對論點的
  反面測試，不是免責話術**。

> 對本產品的意義：一份分析報告 = 一個 flash note。骨架應是
> 「結論 → 論據 → 風險 → 方法 → 免責」，且**免責與方法在最後**。

### 2.2 家族 B：課綱與教育機構的「單一策略描述」欄位順序

- CFA Institute 的選擇權策略單元被描述為：對每個策略討論
  **investment objective、structure、payoff、risk(s)、value at expiration、
  profit、maximum profit、maximum loss、breakeven underlying price at
  expiration**〔索引轉述・近逐字〕。
- OCC／OIC 的《Options Strategies Quick Guide》採**每個策略一頁**的版型，
  每個策略「都配一張到期損益圖（profit and loss at expiration）」，並可依
  **forecast（看多／看空）或 objective（收租、避險等）**檢索〔索引轉述〕。

> 對本產品的意義：(a) 欄位順序是「目的 → 結構 → 損益形狀 → 風險 → 到期價值 →
> 獲利 → 最大獲利 → 最大損失 → 損益兩平」，注意**最大損失緊接在最大獲利之後**，
> 兩者不分家；(b) **到期損益圖是策略描述的標準配件**，不是加分項。

### 2.3 家族 C：實際發行／公開播出的 trade idea 樣本

搜尋索引取得兩則具體的公開選擇權建議（CNBC《Options Action》類型）〔索引轉述・近逐字〕：

- Eli Lilly：「買 December $155/$170 call spread，總成本 $5.50，損益兩平
  $160.50，最大獲利 $9.50。」
- Cisco：「買 June 32/36 call spread，$1，損益兩平 $33，若股價到 $36 以上
  最大獲利 $3。」

賣方機構層級（Goldman Sachs 選擇權研究）的公開轉述則顯示另外兩個慣例〔索引轉述〕：

- 以 **max payout ratio（最大獲利／權利金，如「大於 8 倍」）** 當作結構吸引力的
  單一數字。
- 以 **「相對歷史而言便宜」** 描述權利金水準；並以「要賣哪些 call 才能把 put
  spread 的成本打平」描述資金來源。

> 對本產品的意義：一句話結論的**欄位與順序是固定的**——
> `動作 + 到期 + 履約組合 + 結構名稱 + 成本 → 損益兩平 → 最大獲利`。
> 另外 payout ratio（倍數）是機構愛用的壓縮指標，我們可由既有欄位直接算。

### 2.4 家族 D：專業平台的策略單呈現

- Fidelity **Strategy Evaluator**：對每個回傳的策略顯示
  **Maximum Gain/Loss、Probability、Intrinsic Value**，並直接連到預填的下單單
  〔索引轉述・近逐字〕。
- **OptionStrat**：以**損益圖為介面主體**，並顯示隱含波動率、時間衰退等因子
  對部位的影響〔索引轉述〕。
- 一般性描述：損益圖（P/L chart）是「把預期損益對股價作圖」的視覺工具，
  多腿部位**可能有多個損益兩平點**〔索引轉述〕。
- **Greeks 的位置**：交易平台的典型作法是「一個面板放策略參數的當前值，
  **另一個面板**放該策略當下的 Delta／Gamma／Vega／Theta／Rho」
  〔索引轉述・近逐字〕；而 Fidelity Strategy Evaluator 的**策略摘要列
  根本不含 Greeks**（只有 Maximum Gain/Loss、Probability、Intrinsic Value，
  見上）。兩者一致指向：**Greeks 是第二層明細，不進頭條那一列。**

> 對本產品的意義：平台把「最大獲利／最大損失」壓在同一格（`Maximum Gain/Loss`），
> 印證 §2.2 的三件套不可拆；**圖是主體、數字是輔助**；而 **Greeks 自成一區、
> 不與三件套爭頭條**。

### 2.5 家族 E：法規面對「語氣與免責」的硬性約束

（本產品不受下列規範管轄——我們不是美國經紀商也不是 FINRA 會員。列在此處是
**當作品質標準借用**，§4.4 會據此給建議，但不會宣稱我們有法律義務。）

- **FINRA Rule 2220（Options Communications）**：選擇權溝通中「任何提到潛在
  機會或優勢的敘述，必須以對應風險的敘述來平衡」〔索引轉述・近逐字〕。在交付
  選擇權揭露文件（ODD）之前的溝通，**不得包含建議、不得包含過去或預估績效
  數字（含年化報酬率）、不得指名個別證券**；2220(d)(3)/(d)(4) 允許預估與歷史
  績效數字，**前提是溝通必須先行或同時附上 ODD**〔索引轉述〕。
- **OCC《Characteristics and Risks of Standardized Options》（ODD）**：業界
  依賴這份文件向客戶說明選擇權風險〔索引轉述〕。
- **FINRA Rule 2210(d)(1)**：所有溝通必須 **fair, balanced and not misleading**；
  推銷潛在報酬時必須以平衡方式揭露對應風險〔索引轉述・近逐字〕。
  2210(d)(1)(F) **禁止績效的預測或推估、禁止暗示過去績效會重演、禁止誇大或無
  根據的主張／意見／預測**；研究報告中的目標價屬明文例外，**但須有合理基礎**
  〔索引轉述〕。

> 對本產品的意義：三點很具體。(a) 報酬數字旁邊永遠要有最壞情境；(b) 我們滿屏
> 都是情境估算數字，措辭必須明確標示為**模型估計、非預測**，且要有「合理基礎」
> 可追溯（我們的方法論尾註正好就是這個基礎，所以尾註不能刪，只能降位）；
> (c) 免責段落應**明確指向選擇權風險揭露文件**，而不只是一句「不構成投資建議」。

## 3. 歸納：慣例長什麼樣

### 3.1 章節順序（四個家族的交集）

| 位置 | 章節 | 家族 A | 家族 B | 家族 C | 家族 D |
|---|---|---|---|---|---|
| 1 | 一句話結論／建議 | ✓ 執行摘要 | ✓ objective | ✓ 標準句型 | ✓ 策略列 |
| 2 | 關鍵指標（成本／最大獲利／最大損失／損益兩平） | ✓ key financials | ✓ 三件套 | ✓ 三件套 | ✓ Max Gain/Loss |
| 3 | 論據（為什麼是這個結構、催化劑） | ✓ thesis | ✓ structure | — | — |
| 4 | 情境／損益形狀（含圖） | ✓ valuation | ✓ payoff 圖 | — | ✓ 圖為主體 |
| 5 | 風險（會推翻論點的事） | ✓ risk factors | ✓ risk(s) | — | — |
| 6 | 方法與假設 | ✓ valuation 方法 | — | — | — |
| 7 | 免責與揭露 | ✓ disclosures | — | — | — |

（第 7 列另有家族 E 獨立支持——ODD 屬 §2.5 法規家族，不在本表四欄之內；
本表只統計 A–D 的交集。）

**沒有任何一個來源把「資料過濾統計」「模型參數」放在報告開頭。**

### 3.2 指標呈現

- 成本／最大獲利／最大損失／損益兩平＝**同一個表格區塊**，不可拆散。
- 絕對金額與**相對比例並列**：成本佔現價 %、損益兩平距現價 %、
  max payout ratio（倍數）。機構偏好倍數與百分比，因為可跨標的比較。
- 每股 vs 每張（×100）兩種單位都要給——本產品既有寫法
  `$X（$Y/張）` 已符合，保留。
- **Greeks 分層擺放**（§2.4）：頭條列只放三件套與成本；Delta／Theta／Vega
  另立一個「部位敏感度」小區，位置在風險段而非摘要段。理由是 Greeks 回答的是
  「部位每天／每 1% IV 會漂多少」，屬持有期間的風險管理問題，不是進場決策的
  第一層問題。

### 3.3 表格與文字的配比

專業報告是**表格與圖為主、散文為輔**；散文只出現在「論據」與「風險」兩節，
且以短段落承載因果，不承載數字。數字一律進表。

### 3.4 圖表取捨

到期損益圖是標配（§2.2、§2.4）。**同一份報告不重複畫同一件事**——既然本產品
Step 2 主圖已是 Heatmap（價格 × 日期的報酬率矩陣，資訊量嚴格大於單一到期損益
曲線），報告區不需要再畫一次 payoff 曲線。

### 3.5 語氣

- 陳述語氣、短句、不用驚嘆與情緒詞。
- 每個機會敘述配一個風險敘述（§2.5）。
- 估計值明確標為估計，並可追溯到方法論。

## 4. 對本產品「📄 分析報告」的具體改版建議（V8 施工用）

現況基準：`option_chaser/report.py` 產生的純文字 `report_text`，
契約欄位為 `results[].report_text`。以下建議**不改 `report.py` 的計算來源**，
而是由前端就既有序列化欄位（`results[].candidates[]`、`meta`、`params`、
`filter_stages`、`pair_report`）重新組版。

⚠ **一個例外先講清楚**：現行報告裡有四項內容（買價指引 L2/L3、評語 cons、
方法論尾註、免責）**只活在 `report_text` 這個大字串裡，沒有對應的結構化欄位**。
V8 要用它們就得讓 `store._candidate()` 多吐幾個欄位——值都已經算好，屬序列化層
加欄位，不是新增金融計算，仍在「引擎 report 內容來源不變」的界線內。詳見 §4.2 A2。

### 4.1 目標章節骨架

```
① 交易摘要      一句話結論句 ＋ 關鍵指標表
② 劇本與論據    目標月/目標價、距現價、追平價格 S*
③ 情境分析      韌性 7 情境表 ＋ 劇本完成度曲線 ＋ P/L 矩陣
④ 風險與代價    情境最壞、保本門檻、不漲保留率、Bid-Ask Spread、警示
                ＋「部位敏感度」小區（Delta／Theta／Vega／Lambda）
⑤ 進場執行      逐腿報價（買腿買入價／賣腿賣出價／淨價）、買價指引 L2/L3
⑥ 方法與假設    模型假設、利率、IV 情境、過濾與配對統計、資料時間與來源
⑦ 免責聲明
```

與現況的差異一句話：**把現況的第 1–5 區塊整段搬到第 ⑥ 位，把現況埋在候選內部
第 6 層的成本與報酬提到第 ① 位。**

### 4.2 欄位對照表

**A. 重排（既有欄位換位置，不改值）**

| 既有位置 | 既有內容 | 搬到 |
|---|---|---|
| `[使用者假設]` 劇本／最低要求報酬率 | 目標月、目標價、min-return | ② 劇本與論據 |
| `[使用者假設]` 到期日選取 | 日曆錨點規則 | ⑥ 方法與假設 |
| `[市場資料]` | 資料時間、來源、現價 | ⑥（惟「資料時間」另在頁首新鮮度列，已由 V4 負責） |
| `[模型假設]` | 利率、IV 情境、Delta 門檻 | ⑥ |
| `[過濾統計]`／`[配對統計]` | 掃描張數、各階段刷掉、合格組數 | ⑥（壓成一行：「掃描 N 張 → 合格 M 組」） |
| 候選內 `淨成本`／`最大獲利`／`Breakeven` | 三件套 | ① 關鍵指標表 |
| 候選內 `買腿`／`賣腿` 報價列 | 逐腿 Bid/Ask/IV | ⑤ 進場執行（呼應 feedback-v3 第 8 點） |
| 候選內 `劇本成立時` 各 IV 情境 | 估值／損益／報酬率 | ③ 情境分析 |
| 候選內 `韌性向量` 7 情境 ＋ `劇本完成度` | 情境 | ③ 情境分析（`scenario_vector`／`completion_curve`／`completion_prices`） |
| 候選內 `保本門檻`／`不漲保留率`／`Bid-Ask Spread` | 風險量 | ④ 風險與代價（`completion_threshold`／`retention`／`friction`＋`friction_amount`） |
| 候選內 `Delta`／`Theta`／`Vega`／`Lambda` | Greeks | ④ 的「部位敏感度」小區（`net_delta`／`theta_day_rate`／`vega_per_pt`／`effective_leverage`）——見下方注意事項 |
| `P/L 矩陣` | 矩陣 | ③ 情境分析（`matrix`） |

> **Greeks 口徑注意**：契約序列化的是**已正規化的比率**，不是原始 Greeks——
> `theta_day_rate` ＝ |淨Θ| / **Mid** 成本，`vega_per_pt` ＝ 淨Vega(每 1 IV
> 百分點) / **Mid** 成本（`option_chaser/service.py:78-79`）。亦即它們是
> 「每天／每 1% IV 損耗本金的幾 %」，分母是 Mid 而非主數字用的最差成本。
> 這比原始美元 Greeks 更適合放進風險段，但**標籤必須寫清楚是「佔成本比率
> （Mid 口徑）」**，不能寫成「Theta」了事。原始每股 Θ／Vega 未序列化。

**A2. 需 V8 補序列化（值引擎早就算好了，只是沒進契約）**

以下四項在現行純文字報告裡看得到，但**不在 `store._candidate()` 的輸出**中，
只存在於 `report_text` 這個大字串裡。V8 若要在新版型呈現，必須讓序列化層多吐
這幾個欄位——**這仍符合「引擎 report 內容來源不變」**：值已經由
`CandidateView.pros/cons`（`service.py:61-62`）與 `valuation` 的 `l2`／`l3`
算完，只是沒被 `store.py` 寫出來，屬序列化層加欄位，不是新增金融計算。
**替代方案是前端去 parse `report_text` 的散文——強烈不建議。**

| 既有位置 | 既有內容 | 現況 | 搬到 |
|---|---|---|---|
| 候選內 `買價指引` L2/L3 ＋ 警示 | 天花板 | `valuation.l2`／`l3` 已算，未序列化 | ⑤ 進場執行 |
| 候選內 `評語: 代價` | cons | `CandidateView.cons` 已算，未序列化 | ④ 風險與代價 |
| `[尾註]` 方法論 20 行 | 方法論 | 與免責同在 `report_text` 尾端，未拆欄位 | ⑥（預設折疊） |
| `[尾註]` 最後一行免責 | 免責 | 同上，需與方法論拆開 | ⑦（獨立、不折疊） |

**B. 補充（呈現層算術，資料早就在契約裡）**

成本口徑一律採 **`natural_cost`（最差成交假設：單腿 Ask／價差買 Ask − 賣 Bid）**
——與排名、Breakeven、矩陣同口徑（T12／附錄 A14.2）。`mid_cost` 僅供次要顯示。
（注意：候選物件上**沒有**叫 `cost` 的鍵；`cost` 只存在於 `comparison[]` 列。）

| 新增顯示 | 由既有欄位算 | 依據 |
|---|---|---|
| **最大損失** | `max_loss_per_contract`（**已序列化，純文字報告未印**） | §2.2／§2.4 三件套 |
| 一句話結論 | `legs[].strike`＋`legs[].expiry`＋`strategy`＋`natural_cost`＋`breakeven`＋`max_profit` | §2.3 標準句型 |
| max payout ratio | `max_profit / natural_cost`（Long Call 的 `max_profit` 為 `null` → 顯示「無上限」） | §2.3 GS 慣例 |
| 成本佔現價 % | `natural_cost / meta.spot` | §3.2 |
| 損益兩平距現價 % | `breakeven / meta.spot − 1` | §3.2 |
| 剩餘天數 | `days_to_expiry`（已有，純文字報告未印） | §3.2 |
| 情境最壞與劇本報酬並排 | `baseline_return` 與 `scenario_vector.worst_return` | §2.5 平衡原則 |

**C. 刪除／降級**

| 項目 | 處置 | 理由 |
|---|---|---|
| `評語: 優點`（pros） | 不獨立成段，且**不必補序列化** | 與 ① 關鍵指標表高度重複；專業版型不用形容詞複述數字。`build_reasons`／`build_spread_reasons` 引擎端保留不動（cons 則需補，見 A2） |
| `[過濾統計]` 逐階段明細 | 壓成一行，明細折疊 | §3.1：沒有來源把資料管線放在讀者動線上 |
| `[尾註]` 全文常駐 | 改預設折疊 | 需保留（§2.5「合理基礎」可追溯），但不佔動線 |
| 報告區另畫到期損益曲線 | 不做 | §3.4：Step 2 Heatmap 已涵蓋且資訊量更大 |

### 4.3 表格與文字配比

- ①③④⑤ 的數字**全部走表格**（新前端有真表格，不再用 `- k: v` 條列）。
- 散文只留在 ② 論據與 ④ 風險的短註解，每段 ≤ 2 行。
- 保留既有「每股（每張）」雙單位寫法。

### 4.4 語氣與免責

1. 全文陳述語氣，去掉驚嘆與情緒詞（QA1-09 已做過一輪自創名詞清理，延續同一標準）。
2. **報酬數字不得單獨出現**：任何 `baseline_return` 的呈現位置，同一列必須有
   `scenario_vector.worst_return`。
3. 情境數字標示為「模型估計」，並在同區塊給一個指向 ⑥ 方法與假設的連結／錨點，
   確保「合理基礎」可追溯。
4. 免責段落建議由現行單行擴寫為固定段落，內容涵蓋：模型估計非保證價格／不構成
   投資建議／本工具非經紀商亦非投資顧問／選擇權風險請參閱 OCC
   《Characteristics and Risks of Standardized Options》。
   **措辭不得聲稱本產品受 FINRA 或任何監理規範管轄**（§2.5 前言）。

## 5. 明確不做（越出「只動呈現」的界線，如要做請另開票）

- **IV 百分位／IV Rank**（「權利金相對歷史便宜或貴」，§2.3 GS 慣例、亦為
  業界標配〔索引轉述：低於約 25 百分位視為便宜、高於約 75 視為貴〕）——
  需要歷史 IV 序列，引擎目前沒有。
- **獲利機率**（Fidelity Strategy Evaluator 的 `Probability`，§2.4）——
  需要機率模型，本產品是情境法不是機率法，硬加會與既有口徑打架。
- **催化劑／事件日曆**（§2.1 thesis 的標配）——需要外部事件資料源。
- **多個損益兩平點**（§2.4）——本產品範圍內的策略（Long Call/Put、
  Bull Call/Bear Put Spread）都只有單一損益兩平點，不需處理。

## 6. 未能查證的事項

1. **任何一份實際賣方選擇權研究報告的原件**。全部機構網域（Morgan Stanley、
   FINRA、SEC、CFA Institute、Cboe、OCC）在本沙箱皆 403，無法逐字檢視版面。
   §2.1／§2.3 的機構層級描述均為索引轉述，**排版細節（頁序、欄寬、字級、
   圖表尺寸）本文一概未主張**。
2. **家族 A 沒有一手發布者**。§2.1 的四筆全是第三方訓練機構（Financial Edge、
   Wall Street Prep、CFI、Valuation Master Class）對「賣方報告該怎麼寫」的整理，
   **不是任何一家投行的內部寫作規範原件**。它們彼此獨立且說法一致，但同屬
   「教人進投行」的教材生態，可能共享同一批二手認知。§3.1 的章節順序因此
   另以家族 B（課綱）、C（實際發行的建議）、D（平台 UI）交叉印證，不單靠 A。
3. **CFA Institute 選擇權策略單元的確切欄位順序**。§2.2 的九個欄位來自索引
   摘錄的列舉，順序看似即為原文順序，但未能對照原文確認。
4. **FINRA 規則條文的逐字文本**。§2.5 全部為索引轉述，條號與要旨可交叉印證
   （2210(d)(1)、2210(d)(1)(F)、2220、2220(d)(3)/(d)(4) 在多筆結果中一致），
   但**未逐字核對**。任何要寫進產品免責文字的法規措辭，建議由需求方在可正常
   連網的環境覆核原文後定稿。
5. **Goldman Sachs 的 max payout ratio 是否為其報告固定欄位**。索引摘錄顯示
   該詞用於實際建議（「max payout ratios of greater than 8 times」），但無法
   確認是否為制式欄位或個案措辭。§4.2 據此建議新增此指標，屬**低風險**——
   它只是 `max_profit / 成本` 的另一種寫法，即使非制式欄位亦無害。
6. **OCC Quick Guide 的每頁欄位名稱**。§2.2 的「每策略一頁 ＋ 到期損益圖」
   可從索引確認，但「when to use／maximum profit／maximum loss／breakeven」
   四個欄位名是搜尋提問中帶入的假設，索引回覆未逐字確認欄位標題。
   §4 的建議不依賴此點（三件套已由家族 B 課綱、家族 C 樣本、家族 D 平台
   三方獨立印證）。

## 7. 來源清單

**標記說明**（沿用 `option-chain-data-sources.md` §6 的分類慣例，每一筆都標，
不留空白）。因本次 WebFetch 對所有網域皆 403（§0），**沒有任何一筆是逐字檢視
原文取得**，全部經搜尋索引：

- **〔官方・索引轉述〕**＝發布者本人的官方頁面／官方 PDF，但只讀到索引摘錄。
- **〔二手・索引轉述〕**＝第三方訓練機構或媒體的整理，非規則／課綱的發布者本人。

家族 A（寫作指引）——**本家族四筆全為二手訓練教材，無一手發布者**，
故 §3.1 的章節順序另以家族 B/C/D 交叉印證，不單靠本家族。
- 〔二手・索引轉述〕[How to Write an Equity Research Report — Financial Edge Training](https://www.fe.training/free-resources/esg/equity-research-report/)
- 〔二手・索引轉述〕[Equity Research Report | Format + Example — Wall Street Prep](https://www.wallstreetprep.com/knowledge/sample-equity-research-report/)
- 〔二手・索引轉述〕[What Is an Equity Research Report? Format, Sections — Valuation Master Class](https://valuationmasterclass.com/equity-research-report/)
- 〔二手・索引轉述〕[Equity Research Report: Definition, Types, and Key Components — Corporate Finance Institute](https://corporatefinanceinstitute.com/resources/valuation/equity-research-report/)

家族 B（課綱與教育機構）
- 〔官方・索引轉述〕[Options Strategies — CFA Institute Refresher Readings](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/options-strategies)（直接抓取 403）
- 〔官方・索引轉述〕[The Options Strategies Quick Guide — OIC / OptionsEducation.org](https://www.optionseducation.org/the-options-strategies-quick-guide)
- 〔官方・索引轉述〕[Options Strategies Quick Guide (PDF) — OCC](https://www.theocc.com/getmedia/f34f8a0d-806f-4f1a-adf7-d49d8d94b16e/option-strategies-quick-guide.pdf)（直接抓取 403）

家族 C（實際發行的 trade idea）
- 〔二手・索引轉述〕[As bullish bets surge, here's the Goldman Sachs options play… — Yahoo Finance](https://finance.yahoo.com/markets/options/articles/bullish-bets-surge-goldman-sachs-133000726.html)（媒體轉述 GS 研究，非 GS 原件）
- 〔官方・未取得內容〕[Morgan Stanley Derivatives Trading Ideas（免責頁）](https://www.morganstanley.com/disclaimers/derivatives_trading)（直接抓取 403，索引亦無實質摘錄；**未用於任何結論**，僅列為此類頁面存在的證據）

家族 D（專業平台）
- 〔官方・索引轉述〕[Fidelity.com Help — Research Options / Strategy Evaluator](https://www.fidelity.com/webcontent/ap002390-mlo-content/19.09/help/researching_options.shtml)
- 〔官方・索引轉述〕[Using the Strategy Evaluator — Fidelity Learning Center](https://www.fidelity.com/learning-center/tools-demos/research-tools/using-the-strategy-evaluator-video)
- 〔官方・索引轉述〕[OptionStrat | The Option Trader's Toolkit](https://optionstrat.com/)
- 〔二手・索引轉述〕[Options Foundations: P/L charts — Public.com](https://public.com/trade-options/resources/pl-charts)

家族 E（法規／揭露）
- 〔官方・索引轉述〕[FINRA Rule 2220 — Options Communications](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2220)（直接抓取 403）
- 〔官方・索引轉述〕[FINRA Rule 2210 — Communications with the Public](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2210)（直接抓取 403）
- 〔官方・索引轉述〕[FINRA Regulatory Notice 22-08 — Complex Products and Options](https://www.finra.org/rules-guidance/notices/22-08)（直接抓取 403）

補充（§5 不做項的依據）
- 〔二手・索引轉述〕[Using Implied Volatility Percentiles — Charles Schwab](https://www.schwab.com/learn/story/using-implied-volatility-percentiles)
- 〔二手・索引轉述〕[IV Rank vs. IV Percentile — TradingBlock](https://www.tradingblock.com/blog/iv-rank-vs-iv-percentile)
