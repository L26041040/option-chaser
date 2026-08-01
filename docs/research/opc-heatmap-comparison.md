# OPC（optionsprofitcalculator.com）矩陣估值方法 vs 本 repo 模型比較

研究日期：2026-08-01。
取材限制聲明：本次調查中，對 `optionsprofitcalculator.com`（含 `beta.` 子網域）的直接抓取
一律被沙箱出口 proxy 以 403 拒絕（CONNECT policy denial），Wayback Machine／archive.ph 亦
不可用。以下 OPC 一手資料**全部經由搜尋引擎索引的 faq.html／blog 頁面摘錄取得**（已用
逐字片語搜尋交叉驗證兩次以上者標為「已確認」；只出現一次者標為「單次來源」）。無法
藉此取得的細節（利率、天數慣例、股利、JS 原始碼）明確標為「未能自一手資料確認」。

## 1. 摘要

- **OPC**：以 **Black-Scholes 公式**、各腿**各自從市場報價反推的 IV（持有期間恆定）**，
  逐腿估價後相加，格值＝出場價值 − 進場成本（一手資料已確認）。
- **本 repo**：同樣是 **European Black-Scholes ＋ 每腿固定 IV（來自 yfinance 快照）**，
  另加內在價值下限箝制與 spread 的 [0, width] 箝制；r=0.04 固定、ACT/365、無股利
  （`option_chaser/valuation.py`）。
- **最大差異不在模型骨架（兩邊都是「固定 IV 的 BS」）而在輸入**：IV 的來源不同
  （OPC 自行由 mid/last 反推 vs 本 repo 直接採 yfinance 的 `impliedVolatility` 欄位）、
  無風險利率不同（OPC 未公開其值；本 repo 固定 4%）。這兩項只影響**到期前**的格子；
  **到期欄兩邊皆為純內在價值，理論上應完全一致**。

## 2. OPC 的估值方法（一手資料逐項）

- **定價模型**：Black-Scholes。FAQ：網站「uses the Black-Scholes formula to estimate
  returns at a range of dates and potential underlying prices」（已確認，兩次獨立查詢均
  指向 https://www.optionsprofitcalculator.com/faq.html ）。BS 公式本身即歐式定價
  （此句為模型含意的說明，出處 Hull, *Options, Futures, and Other Derivatives*，非 OPC
  自述）。**是否對美式選擇權另做 binomial／提前履約調整：未能自一手資料確認**——
  FAQ 摘錄只提 Black-Scholes，未提 binomial/CRR；計算頁 JS 因被封鎖無法檢視。
- **IV 來源**：由「the current price of the selected options and the current price of the
  underlying stock or ETF」反推（faq.html，已確認）；另一段 FAQ 摘錄稱 IV 係基於報價的
  mid 或 last price 反推，且「the calculated value of each option is not altered based on
  the current bid/ask spread」（單次來源，faq.html）。
- **IV 恆定假設**：FAQ 原句「Given a constant IV, the calculator will be correct in its
  price estimation, however since IV is a reflection of market sentiment ... it is impossible
  to predict what people will be thinking in the future.」（已確認）。即 IV 在**日期軸與
  價格軸上均取常數**（無 IV 期限結構、無 smile；此推論由「constant IV」與逐腿單一 IV
  的描述而來——smile 維度未見明文，嚴格說**價格軸不套 smile 屬合理推斷而非逐字引文**）。
- **多腿組合（含 call debit spread）**：「the estimated price of each option is calculated
  individually and combined to give gross profit or loss」（faq.html，已確認）。
  未見任何「箝制到 [0, 價差寬度]」的敘述——**是否箝制：未能自一手資料確認**。
- **矩陣格值定義**：「The overall P/L for any given point in time and price is the exit
  value less the total entry value, which is calculated using the latest market prices
  (15 min delayed) combined with the cost prices you select.」（faq.html，逐字已確認）。
  即：格值＝該（價格,日期）下各腿 BS 理論值合計 − **使用者自選的進場成本**。
- **日期欄語意**：各欄估的是**當日開盤時點**；到期日當天早上仍含時間價值，最後一欄
  「exp」為**到期日收盤**（faq.html，兩次查詢確認）。blog〈What happens when options
  expire〉／〈How changes to IV impacts option prices〉並稱到期時「the option's value
  will be from its intrinsic value only」——即 exp 欄＝純內在價值。
- **滑價／費用**：bid/ask 價差滑價與券商手續費**不**納入計算（faq.html，兩次查詢確認）。
- **無風險利率**：**未能自一手資料確認**（數值、來源、可否調整皆無 FAQ 摘錄提及）。
- **天數慣例（365/252、日曆/交易日）**：**未能自一手資料確認**。惟「欄＝當日開盤、
  exp＝當日收盤」顯示其時間參數具**日內粒度**（同一天早／晚不同值），非整數日。
- **股利**：**未能自一手資料確認**（是否用 q 或離散股利調整均無一手敘述）。
- **報價延遲**：15 分鐘（faq.html 已確認；另一摘錄稱 15–30 分鐘，單次來源）。

## 3. 本 repo 的估值方法（file:line）

- **模型**：European BS。`bs_call` `option_chaser/valuation.py:21-28`、`bs_put`
  `valuation.py:152-159`；T≤0 時直接取內在價值（`valuation.py:23-24,154-155`）。
- **箝制**：`clamped_price` `valuation.py:170-172`＝max(BS 值, 內在價值, 0)，即美式
  無套利下限；每次腿估值都經過它（`valuation.py:89`）。
- **情境腿估值**：`scenario_leg_value` `valuation.py:81-89`——估值日 ≥ 該腿到期日時
  回傳內在價值（`valuation.py:86-87`）；否則以「該腿快照 IV ×(1+shift)」帶入
  clamped BS（`valuation.py:88-89`）。IV 逐腿固定，來源為 yfinance 鏈快照的
  `impliedVolatility` 欄位（`option_chaser/data/yf.py:39`，模型欄位
  `option_chaser/models.py:33`）。
- **利率**：`AnalysisParams.rate` 預設 `0.04`（`option_chaser/models.py:60`），CLI 可調
  但矩陣一律用此單一常數。
- **天數**：ACT/365 日曆日——`DAYS_PER_YEAR = 365.0`（`valuation.py:10`）、
  `days_between` 用日期相減（`valuation.py:56-57`），**整數日**、無日內粒度。
- **股利**：q=0，未建模；README 明文揭露（`README.md:206-208`）。
- **Spread 估值**：`spread_scenario_value` `valuation.py:195-202`＝兩腿
  `scenario_leg_value` 之差，箝制到 [0, width]（`valuation.py:202`）。
- **矩陣**：
  - 價格軸 `price_axis` `option_chaser/matrix.py:21-43`：錨點 {現價, 目標,
    超標=目標×1.15（看多）, 深跌=現價×0.90（看多）}，11 點等距格再插入錨點。
  - 日期軸 `date_axis` `matrix.py:46-55`：今天 → **該合約自身到期日**，等分至多 7 欄，
    末欄恰為到期日。
  - 格值 `matrix_grid` `matrix.py:58-66`：`(value_fn(price,date) − cost)/cost`，
    即**報酬率**（OPC 主顯示為 $ P/L；本 repo 顯示 %）。
  - Spread 的 `value_fn`＝`spread_scenario_value`、`cost`＝`net_mid`
    （`option_chaser/service.py:246-249`；`_matrix_view` `service.py:151-158`）。
- **固定 IV 限制的自我揭露**：README 原文——英文版「IV is held constant through the
  target date; realized IV will differ — the ±20% IV scenarios are the hedge for that.」
  （`README.md:89-90`）；中文版「IV 假設恆定到日曆錨點日；實際 IV 會變，三情境
  （±20%）是覆蓋手段。」（`README.md:209`）。README:135-137 並自述矩陣是「同
  optionsprofitcalculator.com 的矩陣體驗」。

## 4. 假設差異對照表

| 項目 | OPC | 本 repo | 對格值影響方向 | 粗略量級 | 到期欄 |
|---|---|---|---|---|---|
| 定價模型 | BS（faq.html）；美式調整未確認 | European BS＋內在下限箝制（valuation.py:170-172） | 箝制只會抬高 repo 值；無股利的 call 理論上 BS≥內在，箝制對 call 幾乎不觸發，對深價內 put 才有感 | call spread：≈0；put：深價內可達數 % | 歸零（兩邊皆內在價值） |
| 無風險利率 | 未確認 | 固定 0.04（models.py:60） | 若 OPC 用不同 r：r 越高 call 越貴。差異經由 K·e^{−rT} 折現 | Δr=1pt、T=1 年、K=100 → 折現差 ≈ $1×N(d2)；近月遠小於此 | 歸零 |
| IV 來源 | 自行由 mid/last 反推（faq.html） | 直接用 yfinance `impliedVolatility`（data/yf.py:39） | 兩者對同一腿可得不同 IV（yfinance 常以 last 反推、可能陳舊）；**這是到期前格差的主要來源** | vega×ΔIV；ATM 一年期 vega≈0.4$/vol-pt，ΔIV 2–5pt 即差 $0.8–2 | 歸零 |
| IV 恆定（日期軸/價格軸） | 恆定（faq.html「constant IV」） | 恆定（valuation.py:89） | 相同假設，無差異 | — | — |
| 天數慣例 | 未確認；欄有日內粒度（開盤/收盤） | ACT/365 整數日曆日（valuation.py:10,56-57） | 半天之差＝半天 theta；OPC 同一日期欄取「開盤」，repo 取整數日 | ≤1 天 theta（近月 ATM 可達每日 1–3% of premium） | 歸零（exp 欄＝收盤＝內在；repo 到期列亦內在） |
| 股利 | 未確認 | q=0（README.md:206-208） | 若 OPC 也不建模則無差；若有，含息標的 repo 的 call 偏樂觀 | 高殖利率標的（TLT≈4%）長天期深價內最大 | 歸零 |
| 進場成本 | 使用者自選 cost price（faq.html） | 固定 net_mid（service.py:249） | 純平移：影響 P/L 與 %，不影響「出場價值」本身 | 依 bid/ask 寬度 | 影響 P/L 值但可藉「在 OPC 輸入 net_mid」消除 |
| Spread 箝制 [0,width] | 未確認（僅「逐腿相加」） | 有（valuation.py:202） | 兩腿 IV 不同時 BS 差值可能越界，repo 會截斷、OPC（推測）不會 | 通常 0；兩腿 IV 差距大時顯現 | 歸零（到期內在差值天然落在 [0,width]） |
| 顯示單位 | $ P/L（exit−entry；faq.html） | 報酬率 %（matrix.py:64） | 換算關係：% = $P/L ÷ cost | — | — |

結論：**所有模型差異在到期欄都應歸零**（兩邊到期欄皆為純內在價值減成本），故到期欄
是最強的一致性檢核點；到期前格差主要由「IV 輸入值不同」與「r 不同」貢獻。

## 5. 抽樣比對協議（可執行）

**樣本**（bull call spread，標的建議 SPY 或其他高流動性標的，3 到期 × 2 價性 = 6 組起）：

| | 近月（~30d） | 中月（~90d） | 遠月（~1y LEAPS） |
|---|---|---|---|
| 價內（長腿 ITM） | S1 | S3 | S5 |
| 價外（長腿 OTM） | S2 | S4 | S6 |

（可加價平列成 3×3；最低要求 3×2。）

**每組比對的格**：
1. **到期欄 × 目標價**——應**分毫不差**（容差 0）：兩邊皆為
   `min(max(target−K_long,0)−max(target−K_short,0), width) − cost`。唯二合法差異來源：
   (a) 進場成本不同 → 在 OPC 的 entry price 欄輸入我們的 `net_mid`（報告「買腿/賣腿
   Bid/Ask」區塊，`option_chaser/report.py:266-267`，net_mid＝兩腿 mid 差）；
   (b) 單位（OPC $/張含 ×100 乘數 vs 本 repo %）→ 以 `% × net_mid × 100` 換算後比對，
   容許 ±0.5%（顯示四捨五入）之內，其餘視為 FAIL。
2. **今天欄 × 現價**——校準格。兩邊都應接近目前市價；殘差≈vega×ΔIV＋rho×Δr。
   把此格差記為 `ε₀`，作為後續格的 IV/r 校準基線。
3. **中間一欄（第 4 欄，~T/2）× 目標價**——容忍帶取
   `|Δ| ≤ |vega×ΔIV| + |rho|×0.02 + |theta_per_day|×1.5`，其中 ΔIV 用第 2 格反推、
   Δr 上限取 2 個百分點（OPC 利率未知的保守包絡）、1.5 天涵蓋「開盤 vs 整數日」與
   快照時差。vega/theta 直接用本 repo 的 Greeks（`valuation.py:39-53,175-192`）。
   超出容忍帶→列為異常並記錄兩邊原始輸入（IV、成本、時間戳）。

**操作步驟**：
1. 本 repo 側：跑 CLI 產生分析；矩陣數字讀
   `workspace/results/<scenario_id>/<snapshot_ts>.json`（結構見 `README.md:268-271`，
   與 CLI/GUI 同源），或直接讀 CLI 報告的矩陣區。同時抄下兩腿 Bid/Ask/IV
   （`report.py:266-267`）與快照時間。
2. OPC 側：開 Bull Call Spread 計算器（`/calculator/`下有 2-legs 與 covered-call 等頁；
   debit spread 可用 custom 2-legged），輸入同標的、同兩腿（到期、履約價），**把每腿
   價格手動改成我們快照的 mid**（使 entry cost = net_mid），讀矩陣上對應
   （最接近的價格列, 日期欄）格值。OPC 為即時報價反推 IV——兩邊快照時間差控制在
   同一交易時段內，否則 IV 漂移會污染比對。
3. 逐格填入上表容差判定；到期欄任何超差都代表**實作 bug**（而非模型假設差），
   優先追查乘數（×100）、成本口徑（mid vs 自選價）、價格列對位（OPC 的價格列未必
   恰有我們的目標價——必要時在 OPC 用其自訂價格範圍功能對齊；**該功能是否存在
   未能自一手資料確認**，若無則取最接近列並以 delta 內插）。

## 6. 引用清單

一手（OPC；均經搜尋索引摘錄取得，直接抓取被 403 封鎖）：
- https://www.optionsprofitcalculator.com/faq.html —— BS 公式、IV 反推與恆定、逐腿相加、
  格值＝exit−entry、開盤/收盤欄語意、滑價與手續費不計、15 分鐘延遲
- https://www.optionsprofitcalculator.com/blog/how-changes-to-implied-volatility-impacts-option-prices —— 到期時價值僅剩內在價值；TSLA IV 變動案例
- https://www.optionsprofitcalculator.com/blog/what-happens-when-options-expire —— 到期行為
- （未能取得：計算頁 JS 原始碼、利率/天數/股利之任何一手敘述）

教科書（僅用於解釋「BS 模型本身隱含什麼」，不代表 OPC 實作）：
- J. Hull, *Options, Futures, and Other Derivatives*：BS 為歐式定價；無股利美式 call
  不提前履約、價值同歐式；美式 put 具提前履約溢價。

本 repo：
- `option_chaser/valuation.py:10,21-28,56-57,81-89,152-159,166-172,195-202,237-242`
- `option_chaser/models.py:33,55-60`
- `option_chaser/matrix.py:21-43,46-55,58-66`
- `option_chaser/service.py:151-158,243-249`
- `option_chaser/data/yf.py:39`
- `README.md:89-90,135-137,204-211,268-271`
- `option_chaser/report.py:266-267`
