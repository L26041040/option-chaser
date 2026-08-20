# 選擇權「相對貴／便宜」怎麼判斷：機構實務方法調查

研究日期：2026-08-13。

---

> ## ⚠ 事後更正（2026-08-13，撰寫後同日查證）
>
> **本文撰寫期間，執行環境的 repo checkout 回退到 201 個 commit 之前的
> V1 時期狀態**（HEAD 掉回 `4d3cea3`；當時連本機 remote-tracking ref
> 也一併被重設，`git rev-list --left-right --count` 因此誤報 `0 0`，
> 正是 CLAUDE.md 早已記載的那個陷阱）。撰寫者是對著那份舊快照做
> 【repo 實證】的。
>
> **因此下列內容一律不可採信，需以正確 tree 重做**：
>
> - 所有標【repo 實證】關於「本專案有／沒有什麼」的敘述
> - 每個方法的第 8 問（**Option Chaser 實作成本**）
> - §1 結論摘要與文末排序中**凡依賴「資料拿不拿得到」的判斷**
>
> **已逐項查證為錯誤的具體主張**（正確 tree ＝ `75c70c2`）：
>
> | 本文原稱 | 實際狀況 |
> |---|---|
> | `option_chaser/ivhistory.py` 不存在 | 存在，20,270 bytes |
> | dividend loader 不存在 | 存在：`option_chaser/dividends.py`＋`data/dividends.py` |
> | Market Data App adapter 不存在 | 存在：`option_chaser/data/marketdata.py` |
> | `requirements.txt` 只有 fastapi | 那是 V1 舊檔；Vercel 實際認 `pyproject.toml`（見 `docs/deploy-vercel.md`），現含 psycopg，另有 `yf` extra |
>
> **最關鍵的一項——它直接翻轉排序**：本文 §7 把「有沒有免費、stdlib
> 可抓、Vercel egress 連得到的 underlying 每日收盤來源」列為最重要的
> 未查證項，並據此把 M1／M2／M3 判為不可行。**該路徑早已存在且在
> production 運行中**：`option_chaser/data/dividends.py` 已在呼叫
> `https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d&...`
> ——Yahoo daily-bar 端點，請求本身就在要 2 年日線，stdlib urllib、
> 匿名無 token，已接進 serverless 路徑（`api_app/dividend_cache.py`）並
> 有 server 端快取；且 CLAUDE.md #120 記載該端點做過 **production 探測
> 實測 HTTP 200**（GitHub Actions runner，真實網路出口），已從「建議」
> 升級為「實測確認」的 primary source。
>
> 但須精確理解：現行 parser 只讀 `events.dividends`／`events.splits`，
> **未**解析同一份回應中的價格序列（`indicators.quote[].close`）。因此
> 取得日收盤是「在一條已驗證、已快取的請求上多解析一段」，屬 parsing
> 增修，**不是新增資料依賴、也不是新的 egress 風險**。
>
> 排序連帶影響：**M1／M2／M3 應重新進入評估**；**M9（IV Percentile）
> 不受此更正影響**——它需要的是歷史 option IV，不是 underlying 收盤，
> 那仍然昂貴且受額度限制。故本文「IV Percentile 應排最後」的結論不但
> 未被推翻，反而因替代方案變得可行而更站得住。
>
> **未受影響、仍有效的部分**：M1–M10 的核心原理、計算方式、empirical
> evidence 與缺陷分析——這些取自外部文獻，與 repo 狀態無關（其證據等級
> 仍受下方〈取材限制聲明〉約束）。
>
> **另需單獨重驗**：文中「當 target price ≥ short strike 時
> `spread_baseline_return == 1/p̂ − 1`」這項副產品發現，是在 V1 時期的
> 引擎上跑出來的；T3／T12 之後 spread 估值與利率處理均已改動。該恆等式
> 若成立對產品定位影響重大，**採用前必須在現行引擎重跑驗算**。

---

**取材限制聲明**：本沙箱的出口 proxy 對幾乎所有金融／學術網域一律回 403
（CONNECT policy denial）——實測被擋的包含 `cdn.cboe.com`、`www.cboe.com`、
`arxiv.org`、`papers.ssrn.com`、`www.nber.org`、`en.wikipedia.org`、
`www.aqr.com`、`orats.com`、`people.umass.edu`、`personal.utdallas.edu`、
`mfe.baruch.cuny.edu`、`www.econ.yale.edu`、`engineering.nyu.edu`、
`public.econ.duke.edu`、`nbgarleanu.github.io`。WebFetch 與 curl 皆失敗。

因此本文的證據分三級，全文逐處標示：

- **【原文實證】**——本人逐頁讀過全文的文件。本次唯一可行的管道是
  **git over HTTPS 對 github.com 仍然通**（`curl` 打 github.com 是 403，
  但 `git clone` 成功）。據此取得
  `github.com/s0ap/gs-quantitative-strategies-research-notes`，
  內含 1990 年代 **Goldman Sachs Quantitative Strategies Research Notes**
  原始 PDF（含 GS 版權頁、原始排版）。本文的機構實務主幹來自其中四篇，
  數字皆為我從原文表格逐字抄出。⚠ 這是**第三方鏡像**而非
  goldmansachs.com 官方下載，真偽以版權頁與內文自洽性判斷為高，
  但未能與官方版本對校。
- **【搜尋索引轉述】**——只讀到搜尋引擎回傳的摘要，**沒有讀到原文**。
  所有學術論文（Carr & Wu、Bakshi & Kapadia、Goyal & Saretto、
  Breeden & Litzenberger、Poon & Granger、Corsi、Gârleanu-Pedersen-Poteshman
  等）、所有交易所方法論白皮書（Cboe VIX／SKEW）、所有廠商文件
  （OptionMetrics、ORATS、tastytrade）都屬此級。**引用的每一個數字若無
  【原文實證】標記，就是我沒親眼在原文看過的數字。**
- **【repo 實證】**——本 repo 自身程式碼，可逐行覆核，並附我實際跑過的
  驗算。

凡搜尋亦無法確認者，一律列入 §7「未能查證的事項」，**不猜數字**。

---

## 1. 結論摘要

1. **「Historical IV Percentile／IV Rank」在機構端不是判斷貴賤的主力方法。**
   最強的反證不是二手評論，而是 Goldman Sachs 自己 1999 年的研究報告
   開宗明義說：「最常見的選擇權價值量尺是**當前與過去 implied volatility
   的價差**……這是**選擇權投機客**（options speculators）的指標」，
   並緊接著指出「自從 volatility smile 出現以後，要對兩張複雜曲面的相對
   richness 有明確看法就變難了」【原文實證，Zou & Derman 1999, p.1】。
   該文整篇的存在理由就是**取代**這個指標。IV Rank 的普及來源是零售平台
   （tastytrade 推廣、券商介面預設欄位）【搜尋索引轉述】。它不是錯的，
   它是**維度不對**：它描述 ATM 波動率水位的時序位置，而不是「這一組
   合約相對於同一張曲面上其他合約貴不貴」。
2. **對 Option Chaser 這種「賣點是 vertical spread」的產品，正確的核心
   方法不是波動率水位類，而是「包裹層的機率讀法」。**
   由 Breeden-Litzenberger 的恆等式可得一個**精確**（非近似）關係：

   ```
   (C(K1) − C(K2)) / (K2 − K1) = e^(−rT) · (1/(K2−K1)) ∫[K1..K2] Q(S_T > K) dK
                                ≈ e^(−rT) · Q(S_T > (K1+K2)/2)
   ```

   也就是說，**一組 vertical spread 的「淨成本 ÷ 履約價寬度」，就是市場
   自己開出來的、標的到期站上中點履約價的（折現）機率。** 判斷這組
   spread 貴或便宜，等價於判斷「市場開的這個機率，跟你自己的機率相比，
   哪個高」。這是結構台每天在做的換算，不需要任何歷史資料。
3. **本 repo 的排名公式，其實已經等價於「照市場機率由低到高排」——只是
   方向可能跟使用者想的相反。**【repo 實證】當目標價 ≥ 賣腿履約價時，
   `evaluate_spread` 的 `baseline_value` 恆等於 width，於是

   ```
   spread_baseline_return = (width − net_worst) / net_worst = 1/p̂ − 1，
   其中 p̂ = net_worst / width（未折現的市場隱含機率上界）
   ```

   我用 repo 自身程式驗算過（width=10、net_worst=2.5 → baseline_return
   = 3.0 = 1/0.25 − 1，完全相等）。推論：**目前的排行榜，永遠把「市場
   認為最不可能成功」的那一組排在第一名。** 這不是 bug——公式沒錯——
   但它意味著現行排名量的是「賠率」，不是「優勢（edge）」。要量優勢，
   分母缺的那一半（你自己的機率、或某個第三方基準機率）必須補上。
   這是本次調查對產品最重要的單一發現。
4. **真正在機構端天天用的方法，共通點是「先把座標系正規化，再比」**：
   GS 交易員的內部資料庫「把選擇權的 implied volatility 記成**到期期限
   與 Black-Scholes delta 的函數**」，SPX 曲面就是 12 個數字
   （25Δ put／50Δ／25Δ call × 1／3／6／12 個月）【原文實證，
   Kamal & Derman, p.2】；OptionMetrics IvyDB 的標準商品也是
   constant-maturity × delta 網格【搜尋索引轉述】。固定履約價的比較
   在機構資料模型裡根本不存在。
5. **skew 的「公平值」是可以被歷史檢定的，而且檢定結果是「大致公平」。**
   GS 用兩種獨立方法（風險中性期望法、複製成本法）估計 SPX 的公平
   skew，結論是崩盤後市場觀察到的 skew 斜率「大致公平」；
   量化對照表（25Δ put 與 25Δ call 的 vol 點差）：SPX 正常時期 4–7%、
   極端時期 14%、由歷史算出的公平值 6.0%；DAX 3–6%／10%／3.5%；
   FTSE 2–6%／10%／4.0%【原文實證，Zou & Derman 1999, Table 1】。
   對 spread 產品的意義：**你不能預設「賣腿收的權利金一定被高估」**，
   常態下它大致就是公平價。
6. **資料現實決定一切（§3）。** Option Chaser 部署在 Vercel serverless、
   執行期相依只有 `fastapi`（`requirements.txt` 刻意排除 yfinance）、
   估值層宣告「Stdlib math only」、**沒有任何標的歷史價格的取得路徑，
   也沒有任何歷史 IV 儲存**。這一條把所有「需要 realized volatility」
   或「需要一年份 IV 時序」的方法（M1／M2／M3／M9）全部推到「要先新增
   資料源」那一側；而「只用當下這一張鏈就能算」的方法（M5／M6／M7／M8，
   以及工程較重的 M4）則是零新資料。
7. **最終排名（詳見 §8）**：M8 包裹機率讀法 ＞ M7 delta／期限正規化座標
   ＞ M5 skew 相對值 ＞ M6 期限結構 ＞ M4 曲面擬合殘差 ＞ M1 IV−RV
   ＞ M2 IV−預測 ＞ M3 VRP ＞ M10 部位／需求 ＞ **M9 IV Percentile（最後）**。

---

## 2. 判準：什麼叫「貴」，以及怎麼分辨「真的在交易」與「文章在寫」

### 2.1 三種互不相同的「貴」

討論之所以混亂，是因為「貴」至少有三個彼此獨立的意思，證據等級也不同：

| 口徑 | 主張 | 可否被證偽 |
|---|---|---|
| **A. 絕對貴**（vs 未來實現） | 這張合約的 implied volatility 高於標的未來實際會走出來的 volatility | 可以，但要等到期後才知道；統計上要靠大量樣本 |
| **B. 相對貴**（vs 同一張曲面上的鄰居） | 在同一個標的、同一天，這個 (delta, 期限) 座標比曲面平滑值高 | 可以，即時、不必等未來 |
| **C. 風險溢酬**（結構性） | 賣方長期收得到補償，因為承擔了不可對沖的風險 | 可以，但這是「應該貴」不是「不該貴」 |

A 與 C 是**方向性**判斷（適合做多／做空 volatility）；B 是**相對值**判斷
（適合在同一張鏈裡選腿）。**Option Chaser 問的是 B 型問題**（「同一個標的
的一堆 spread，哪一組比較划算」），而 IV Rank／IV Percentile 只回答 A 型
問題的一個粗糙代理。這個錯配是本文最核心的判斷。

### 2.2 「業界據此下單」vs「教育文章的指標」的分辨標準

本文對每個方法給出 verdict，判準有三：

1. **它是不是某個實際成交商品的定價基礎**（variance swap、VIX 期貨、
   FX 的 25Δ RR/BF 報價慣例）。是 → 幾乎必然「業界據此下單」。
2. **它有沒有出現在賣方／買方的內部資料模型或研究報告裡**
   （GS trader database、OptionMetrics IvyDB、GS QSRN）。
3. **它的推廣者是誰**。若主要傳播管道是零售券商介面與教學文章、且找不到
   對應的機構資料產品或成交商品，則歸「教育材料指標」。

---

## 3. Option Chaser 的資料與工程現況（第 8 問的共同前提）

以下全為【repo 實證】，是我實際讀過的檔案，非推測：

**引擎已經有的**

- Black-Scholes 定價、內在價值下限箝制、單腿與 spread 的情境估值：
  `option_chaser/valuation.py`（檔頭明寫 **"Stdlib math only"**）。
- 每一腿的 Greeks（delta／gamma／theta／vega）：`valuation.leg_greeks`。
- **期限對齊的無風險利率**：`option_chaser/ratecurve.py` ＋
  `option_chaser/data/treasury.py`，每個到期日各自查表
  （`valuation.leg_rate`、`AnalysisParams.rate_by_expiry`）。
- 完整選擇權鏈（含 LEAPS）：`option_chaser/data/cboe.py`，一次 GET
  `cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json`，
  每筆含 bid／ask／last／volume／open_interest／**iv**；備援
  `option_chaser/data/yf.py`。
- 品質過濾與配對窮舉：`option_chaser/filters.py`（報價／IV／OI／價差四關）。
- 排名：`option_chaser/ranking.py`，spread 主數字
  `spread_baseline_return = (baseline_value − net_worst)/net_worst`，
  成本口徑 = 最差成交（買腿 Ask − 賣腿 Bid）。
- 自建的歷史累積：`store.list_result_paths()` ＋
  `workspace.spread_history()`——每次刷新的全部有效候選都被序列化保存，
  可依 spread 身份鍵橫向串接成時間序列。

**引擎完全沒有的（必須明講，因為委託說明裡提到的幾項在這份程式碼裡不存在）**

- **沒有 `option_chaser/ivhistory.py`**（全 repo 搜尋無此檔）。
- **沒有 dividend loader**（全 repo 搜尋 `dividend` 只命中 numpy 測試）。
  → 目前的 BS 是**無股息**版本，對 TLT 這類高配息 ETF 是已知偏差。
- **沒有 Market Data App adapter**。它只出現在
  `docs/research/option-chain-data-sources.md` §3.6 的候選評估裡，
  且該節結論是：免費層 100 credits/日、chain 端點**回傳幾筆合約就扣
  幾個 credit**，全鏈數千筆 → **免費層連抓一次都不夠**。
- **沒有任何標的日線收盤價的取得路徑。** Cboe 端點只給
  `current_price`／`close` 兩個當下數字，沒有歷史；yfinance
  被刻意排除在 serverless 相依之外。
- **沒有任何歷史 implied volatility 的儲存或來源。**

**部署與工程約束**

- Vercel serverless，`requirements.txt` 只有 `fastapi>=0.117.1`，
  檔案裡明白寫著「刻意不含 yfinance：它帶 pandas/numpy，塞進 serverless
  函式體積不划算」。→ **任何需要 numpy/scipy 的方法都要先推翻這個決定。**
- 持久化層 V2（issue #50）才接 Neon Postgres；在那之前歷史只存在檔案系統，
  serverless 上等同不可靠。
- 刷新只有三個入口（開站／建立劇本／頂部刷新鈕，QA1-07）→ 自建歷史的
  取樣密度**由使用者行為決定**，不是每日規律。

這份盤點會被下面每一個方法的第 8 問直接引用。

---

## 4. 方法逐條檢視

### M1. Implied vs Realized Volatility（IV − RV，含 volatility cone）

1. **核心主張**：選擇權的 implied volatility 若顯著高於標的**過去已實現**
   的 volatility，代表 replicator（delta 對沖到期者）可以鎖住兩者差額。
   GS 明確定位這是「**選擇權複製者**（options replicators）的指標」，
   而且點出它的先天弱點：「在有 volatility skew 時，這個比較會變得不精確
   ——有一整排隨履約價變動的 implied volatility，卻只有**單一個**歷史
   realized volatility 可比」【原文實證，Zou & Derman 1999, p.1】。
   **volatility cone**（Burghardt & Lane, *JPM* 16(2), 1990,
   "How to tell if options are cheap"）是這個想法的期限結構版：把不同
   回看窗（20／60／120／250 日）的 realized volatility 分布畫成錐形，
   再把當前各期限 implied 疊上去比【搜尋索引轉述，論文原文未取得】。
2. **需要的資料**：標的日線（或更高頻）收盤價，長度至少 1–2 年；
   當前各期限的 ATM implied volatility。
3. **實際算法**：close-to-close 年化 σ_RV(n) = √(252/n · Σ(ln(S_t/S_{t−1}) − r̄)²)
   （或 Parkinson／Garman-Klass 等 range 估計量以降變異）。訊號
   = σ_IV(T) − σ_RV(n)，**窗長 n 要與 T 對齊**（cone 的存在理由就是
   提醒你不要拿 20 日 RV 比 2 年 IV）。normalization 慣例是取「同期限
   RV 歷史分布的分位數」而非原始點差。
4. **實證**：Poon & Granger (2003, *JEL* 41(2):478–539) 綜述 93 篇研究，
   結論是 option-implied volatility 的預測力優於時序模型【搜尋索引轉述；
   ⚠ 我另外看到一則搜尋摘要宣稱「39 篇中 22 篇認為歷史波動率較佳」，
   兩者方向相反，**我無法核對原文，兩個數字都不採信**，只採「多數綜述
   認為 implied 含有歷史以外的資訊、但是有偏估計」這個方向性結論】。
   Christensen & Prabhala (1998, *JFE* 50:125–150) 發現 implied 優於
   過去 volatility，並把先前文獻的「有偏」歸因於 1987 崩盤前後的
   regime shift【搜尋索引轉述】。Goyal & Saretto (2009, *JFE*)
   直接把 IV−RV 當排序變數：以 1 年歷史 realized volatility 對 ATM
   implied 的差值排序，多空組合的 straddle／delta-hedged 月報酬顯著為正
   【搜尋索引轉述；**具體報酬率與 t 值我沒取得，不引用任何數字**】。
5. **適合 Long Call／Put？** 適合，但只在「你打算 delta 對沖」時主張才成立。
   裸多單腿的損益由標的方向主導，IV−RV 只是二階項。
6. **適合 Vertical Spread？** **基本不適合。** 一個 spread 是兩個相鄰履約價
   的差；ATM 的 IV−RV 水位對這個差幾乎沒有資訊（見 §4-M8 的推導：
   包裹價值由**斜率**決定，不由**水位**決定）。要用在包裹上，得先把
   「單一個 RV」擴充成「整條公平 smile」——那就是 M4（SAS）而不是 M1。
7. **最大缺陷**：(a) skew 一出現就單位不匹配（GS 原文指出）；
   (b) 過去 RV 不是未來 RV，這是 M2 要處理的問題；
   (c) 成本吞噬——選擇權買賣價差是這類策略的主要殺手（見 M2 第 4 問）。
8. **Option Chaser 成本**：**中偏高，且卡在資料源。** 需要一個新的日線
   收盤價 adapter；Cboe 端點不提供歷史，yfinance 被排除在 serverless
   相依外。stdlib 可行的候選是免金鑰 CSV 型的日線來源，但
   **本沙箱無法測試任何候選端點是否可從 Vercel 連通**（§7）。
   算式本身很便宜（~30 行 stdlib）。真正的代價是新增並維護第二個網路
   相依，而且它對本產品主推的 spread 幾乎不產生排序資訊。
   **verdict：業界真的據此下單**（replicator／vol arb 的基本盤，
   1990 年就有 JPM 論文，GS 內部文件列為兩大既有量尺之一）。

### M2. Implied vs **Forecast** Volatility（與 M1 是不同的主張）

1. **核心主張**：M1 拿的是「過去」，M2 拿的是「模型對**未來** T 期間
   RV 的條件預測」。主張是：市場定價 σ_IV(T) 相對於**最佳可得預測**
   E[RV(T)] 偏高／偏低。這是 vol arb 的真正形式；M1 只是它的一個
   naive 特例（把預測設成「未來＝過去」）。
2. **需要的資料**：標的高頻或日線報酬（建 realized variance 序列）；
   若要做事件調整，還需要財報日／宏觀事件日曆。
3. **實際算法**：業界主力是 **HAR-RV**（Corsi 2009）：
   `RV_{t+1} = β0 + βd·RV_t^(d) + βw·RV_t^(w) + βm·RV_t^(m) + ε`，
   三個回歸元分別是日／週（5 日均）／月（22 日均）的 realized volatility，
   用最小平方擬合。搜尋摘要稱 HAR 已成為此文獻的 workhorse，且顯著
   優於 GARCH 與 ARFIMA-RV【搜尋索引轉述】。實務上再疊加事件項
   （把財報日的期望變異單獨加總）。訊號 = σ_IV(T) − √(Σ 預測日變異)。
4. **實證**：Poon & Granger 的排序把 implied 放在時序模型之上
   【搜尋索引轉述】，這其實是對 M2 不利的證據——**如果 implied 已經
   是最好的預測器，那「implied 減預測」的殘差就沒有交易價值**。
   支持 M2 的一側是 Goyal & Saretto 那類橫斷面結果（同上，數字未取得）。
   成本方面：搜尋摘要指出「bid-ask 價差顯著侵蝕選擇權策略的原始利潤」，
   但也指出「會挑執行時點的交易者，其 effective spread 不到傳統量測的
   40%」，且此一發現會改變對成本後獲利性的結論【搜尋索引轉述，
   **40% 這個數字我未在原文核對，不應作為決策依據**】。
5. **適合 Long Call／Put？** 適合（同 M1，仍以對沖為前提）。
6. **適合 Vertical Spread？** 與 M1 同樣不適合——它產出的是**水位**判斷。
7. **最大缺陷**：(a) 若 implied 本來就是較佳預測器，殘差是雜訊不是 alpha；
   (b) 日線 RV 是高頻 RV 的粗糙代理，HAR 的優勢主要來自高頻資料；
   (c) 對單一標的、遠月 LEAPS，樣本內外的預測誤差遠大於 IV−forecast
   的訊號量級。
8. **Option Chaser 成本**：**高。** = M1 的資料成本 ＋ 一個回歸模型。
   HAR 的 4 參數最小平方在 stdlib 可解（4×4 正規方程手寫），不必引入
   numpy；但取得**高頻**資料完全沒有免費路徑。做日線版 HAR 等於承擔
   M1 的全部成本，換來邊際很小的改善。
   **verdict：業界真的據此下單**（這就是 volatility arbitrage 本業），
   但**零售教育內容反而很少講**——教育內容多半停在 M1／M9。

### M3. Volatility Risk Premium（VRP）

1. **核心主張**：**選擇權「本來就該貴」。** 風險中性期望變異數
   （variance swap rate）系統性高於實際實現變異數，差額是賣方承擔
   不可對沖風險的補償。所以「IV 高於 RV」本身不構成 mispricing——
   要主張 mispricing，你得說「今天的 VRP 比它應有的水準異常」。
2. **需要的資料**：完整 OTM 選擇權鏈（算 variance swap rate）＋
   標的報酬序列（算 realized variance）＋期限對齊利率。
3. **實際算法**：VIX 式的 log-contract 複製。Cboe 的方法論
   （搜尋索引轉述的公式形式）為

   ```
   σ²(T) = (2/T)·Σ_i (ΔK_i/K_i²)·e^(rT)·Q(K_i) − (1/T)·(F(T)/K_0 − 1)²
   ```

   權重與 1/K² 成正比，這正是複製 variance swap 收益的權重
   【搜尋索引轉述，Cboe VIX methodology】。30 日值由跨越 30 天的
   兩個到期日在**總變異數**上做線性內插得到。
   VRP = 該 variance swap rate − 隨後實現的 variance。
   **GS 的原文給了一個對本產品有用的修正項**【原文實證，
   Demeterfi et al. 1999】：當 smile 對履約價呈線性
   `Σ(K) = Σ0 − b·(K−S_F)/S_F` 時，公平變異數
   `K_var ≈ Σ0²·(1 + 3·T·b² + …)`；當 smile 對 delta 線性
   `Σ(Δp) = Σ0 + b·(Δp + 1/2)` 時，
   `K_var ≈ Σ0²·(1 + (1/√π)·b·√T + (1/12)·b²/Σ0² + …)`。
   → **fair variance 高於 ATM 水位，且增量與 skew 斜率平方、與期限成正比。**
4. **實證**：Carr & Wu (2009, *RFS* 22(3):1311–1341) 用選擇權組合合成
   variance swap rate，對 5 個股票指數與 35 支個股檢驗；搜尋摘要引用的
   做空 variance swap Sharpe ratio 為 S&P 500 = 0.98、S&P 100 = 0.85、
   Dow = 0.87【搜尋索引轉述，**我未在原文核對這三個數字**】。
   **對本產品最關鍵的一句**：搜尋摘要指出「S&P 100 的 variance risk
   premium 顯著為負，而**個股的 variance risk premium 常常是零、
   甚至為正**」【搜尋索引轉述】——亦即 VRP 主要是**指數**現象。
   Bakshi & Kapadia (2003, *RFS* 16(2):527–566) 以 delta-hedged gains
   為切入，發現 S&P 500 的 delta 對沖組合報酬低於零、離價越遠低估程度
   越小、高波動時期低估越大，支持負的市場 volatility risk premium
   【搜尋索引轉述】。Gârleanu, Pedersen & Poteshman (2009, *RFS* 22(10))
   給了**為什麼**：終端使用者是指數選擇權（尤其 OTM put）的淨買方，
   風險趨避的中介商因此把價格推高【搜尋索引轉述】。
   AQR 的 practitioner 研究主張 VRP 在各 volatility regime 都存在
   【搜尋索引轉述，白皮書原文被擋】。
5. **適合 Long Call／Put？** 適合，但**方向對本產品不利**：VRP 的結論是
   「買方長期是付溢酬的一方」。它會系統性地說「你的 Long Call 偏貴」，
   而且它是對的——這是應該讓使用者知道的事實，不是選腿的排序工具。
6. **適合 Vertical Spread？** **部分適合，而且方向有趣。**
   Bull call spread 是「買一個 vega ＋ 賣一個 vega」，淨 vega 遠小於
   單腿，**因此它天生就把 VRP 的大部分對沖掉了**。這其實是 spread
   相對單腿的一個真實優勢，值得在產品裡講清楚——但也正因為對沖掉了，
   VRP 對「哪一組 spread 較划算」幾乎沒有排序資訊。
7. **最大缺陷**：(a) 它是「應該貴」的解釋，不是「不該貴」的訊號，
   容易被誤用成 timing 指標；(b) 個股／單一 ETF 的 VRP 證據遠弱於指數；
   (c) 賣 volatility 的報酬分布嚴重左偏厚尾，Sharpe ratio 本身就會
   誤導風險【搜尋索引轉述】。
8. **Option Chaser 成本**：**風險中性那半邊很便宜、實現那半邊做不到。**
   Cboe 全鏈 ＋ 期限對齊 r 已在手，VIX 式 strip 是純算術（stdlib，
   ~60 行），可以每次刷新就算出「本標的各到期日的 model-free 隱含變異數」。
   但 realized variance 需要標的日線——**沒有路徑**（§3）。
   而且對 TLT 這類單一 ETF，第 4 問的證據說 VRP 可能根本不顯著。
   **verdict：業界真的據此下單**（VIX 期貨／variance swap 是實際成交
   商品，方法論就是它的定價基礎）。

### M4. Volatility Surface Relative Value（曲面擬合殘差／SAS）

1. **核心主張**：同一標的、同一天的所有合約應該落在一張**平滑且無靜態
   套利**的曲面上。偏離平滑值的個別合約就是相對貴／相對便宜。這是
   **B 型（相對貴）** 判斷，不需要對未來做任何預測——這是它相對 M1–M3
   的根本優勢。
2. **需要的資料**：當下完整鏈（多履約價 × 多到期日）。**進階版（SAS）
   額外需要標的歷史報酬。**
3. **實際算法**——兩條路線：
   - **純橫斷面（無歷史）**：對每個到期日切片，以 total implied variance
     `w(k,T) = σ²(k,T)·T` 對 log-moneyness `k = ln(K/F)` 擬合。業界標準
     參數化是 **SVI**（Gatheral & Jacquier, *Arbitrage-free SVI volatility
     surfaces*, 2012），5 參數控制水位、斜率、曲率、偏斜；其
     **SSVI／eSSVI** 變體再跨切片施加一致性以避免 calendar spread 套利
     【搜尋索引轉述】。無套利條件是：**每個切片無 butterfly 套利，
     且總變異數在固定 k 上對 T 非遞減**【搜尋索引轉述】。
     richness 訊號 = 市場 IV − 擬合 IV（殘差）。
   - **含歷史（SAS）**【原文實證，Zou & Derman 1999】：
     用標的歷史報酬分布當先驗，以**相對熵最小化**求出一個滿足遠期條件的
     風險中性分布（RNHD, risk-neutralized historical distribution），
     再用它算出各履約價的「歷史公平 implied volatility」Σ_H(K,T)。
     `SAS(K,T) = Σ(K,T) − Σ_H(K,T)`。
     GS 特別提供了一個**只比形狀、不比水位**的變體 **SAS_ATM**：
     額外約束 RNHD 重現市場的 ATM-forward 價格，使
     `SAS_ATM(S_F, T) = 0`——原文的理由是「skew 比 ATM 水位穩定得多，
     所以常常不論歷史分布如何，**當前 ATM implied 就是對未來波動最可信
     的估計**；歷史分布告訴我們的，比較是未來分布的**高階動差**，
     而不是它的標準差」（p.3）。
4. **實證**：GS 原文的實例（1999-05-18 的 SPX 9 月合約）顯示：用含 1987
   崩盤的 12 年歷史，OTM put 略便宜、OTM call 略貴；用排除崩盤的 11 年
   歷史，OTM put 顯得**太貴**、OTM call 略便宜——**同一天、同一組合約，
   只因為歷史窗選擇不同，結論就完全相反**。原文自己承認：「SAS 是排序
   相對價值的量化工具，但這並不免除使用者選擇歷史期間的責任……無法
   迴避判斷」（p.13）【原文實證】。這是我在整份調查中看到最誠實、也最
   重要的方法論警告。
   對 M4 有利的證據：Kamal & Derman 對 SPX／Nikkei 曲面變動做主成分分析，
   前三個模態（水位／期限結構／skew）解釋 SPX 90.7%、Nikkei 95.9% 的變異
   【原文實證，Table 1；細項 SPX 81.6／5.0／4.1，Nikkei 85.6／7.9／2.4，
   模態 4–6 對 SPX 各只有 2.1／1.7／1.6%】。→ **曲面確實是低維物件，
   「偏離平滑面」是有意義的殘差而非雜訊。**
5. **適合 Long Call／Put？** 非常適合——這是造市商每天替單一合約標
   rich/cheap 的方法。
6. **適合 Vertical Spread？** **適合，而且是少數天生適合包裹的方法之一。**
   因為擬合是逐合約給殘差，包裹的殘差就是**兩腿殘差相減**：
   `SAS(spread) = SAS(K1,T) − SAS(K2,T)`（在 vega 加權下）。
   注意方向：買腿殘差為負（便宜）、賣腿殘差為正（貴）才是好包裹。
   而且 SAS_ATM 那個變體特別合用——它刻意把「水位對不對」剔除，
   只留「不同履約價之間的相對關係」，這正是 vertical spread 的損益來源。
7. **最大缺陷**：(a) **窗選擇即結論**（GS 自承，上引）；
   (b) 殘差可能是「資料髒」而非「便宜」——流動性差的遠月合約報價本身
   就爛，擬合殘差會系統性把它們標成 mispriced，這對本 repo（TLT LEAPS
   是主戰場）是真實風險；(c) 純橫斷面版本會把「市場對某個事件的正確
   定價」誤判為套利機會。
8. **Option Chaser 成本**：**中至高，但這是唯一「零新資料」的高強度方法。**
   - 純橫斷面版：資料全在手（一次 Cboe 全鏈就有全部履約價 × 全部到期日
     的 iv）。工程障礙是**非線性最小平方**——SVI 是 5 參數非線性擬合，
     `requirements.txt` 只有 fastapi、`valuation.py` 宣告 stdlib-only，
     所以要嘛手寫 Nelder-Mead（~80 行，收斂性要自己顧），要嘛降階成
     **對 log-moneyness 的二次式**（`w(k) = a + b·k + c·k²`）——那是
     **線性**最小平方，3×3 正規方程用 stdlib 十幾行就能解，而且足以
     產出「這一腿相對於本期切片是貴是便宜」的殘差。**我認為降階版是
     本產品的正確取捨**：拿到 M4 八成的價值，不必推翻 serverless
     相依決策。
   - SAS 完整版：需要標的歷史報酬（無路徑）＋熵最小化（凸優化）→
     在目前架構下不可行。
   **verdict：業界真的據此下單**（造市商每日校準曲面就是這件事；
   SVI 是公開的業界標準參數化；SAS 是 GS 為自家交易台寫的工具）。

### M5. Skew Relative Value

1. **核心主張**：曲面的**橫向斜率**（同到期日、不同履約價之間的 IV 差）
   有自己的公平值與自己的均值回歸，可以獨立於水位交易。
2. **需要的資料**：當下鏈（含各腿 delta）。歷史比較需要 skew 的時序。
3. **實際算法**——業界座標是 **delta 化**的：
   - **25Δ Risk Reversal** `RR25 = IV(25Δ call) − IV(25Δ put)`；
   - **25Δ Butterfly** `BF25 = ½·(IV(25Δ call) + IV(25Δ put)) − IV(ATM)`
     【搜尋索引轉述，vendor／教育來源；但 GS 原文獨立佐證了 25Δ 座標
     的機構地位——SPX 曲面就是用 25Δ put／50Δ／25Δ call 三個 delta
     記錄的，見 M7】。
   - 常數到期化：把各到期日的斜率加權插值成「30 日斜率」，再與歷史
     迴歸出的預測斜率相比【搜尋索引轉述，ORATS】。
   - 另一個實務讀法：**vega-neutral ratio**——要賣幾張 OTM call 才能
     把一張 ATM call 的 vega 打平；需要賣的張數越少，代表 skew 越陡
     【搜尋索引轉述，ORATS】。
   - **公平值基準**：GS 用歷史報酬分布反推公平 skew，量化對照見 §1-5
     的 Table 1【原文實證】。
4. **實證**：GS 兩種獨立方法（風險中性期望法、複製法）都得到「崩盤後
   SPX 的 skew 斜率大致公平」的結論；複製法的細節是——用比歷史 realized
   volatility **高 3 到 5 個百分點**的 hedge volatility 去複製，得到的
   公平 skew 才與市場觀察到的 skew 形狀相符【原文實證，Derman/Kamal/
   Kani/Zou, p.9–10】。注意這句話同時也是 M1／M3 的證據：**implied 系統性
   高於 realized 3–5 個 vol 點，是 GS 當年拿來當工作假設的量級。**
   跨資產／橫斷面方面，Xing, Zhang & Zhao (2010, *JFQA* 45:641–662)
   發現個股的 volatility smirk（OTM put 與 ATM call 的 IV 差）可預測
   未來股票報酬，並獲 JFQA 最佳論文獎【搜尋索引轉述，數值未取得】。
   Cboe SKEW 指數則把 30 日風險中性偏度指數化，方法論根源是
   Bakshi, Kapadia & Madan (2003) 的 model-free 動差【搜尋索引轉述】。
5. **適合 Long Call／Put？** 間接適合——它告訴你「同一張鏈上，是 put 側
   還是 call 側相對貴」，但單腿的損益仍由水位與方向主導。
6. **適合 Vertical Spread？** **高度適合。這是包裹層的正確語言。**
   由 M8 的推導，vertical spread 的價格對「兩個履約價之間那一段 IV 斜率」
   一階敏感，對整體水位只有二階敏感。**判斷 bull call spread 貴不貴，
   本質上就是判斷 K1→K2 這一段的 skew 是不是太陡。**
7. **最大缺陷**：(a) skew 的均值回歸只在極端值附近才有可交易性
   【搜尋索引轉述】，中間帶是雜訊；(b) 陡 skew 常常是**正確**在定價
   真實的尾部風險（GS 的結論就是「大致公平」），把它當套利會系統性地
   做空崩盤保險；(c) delta 本身依賴 IV，座標有內生性。
8. **Option Chaser 成本**：**低至中，零新資料。** 引擎已有各腿 delta
   （`leg_greeks`）與各合約 iv；把同到期日的 (delta, iv) 排序後線性插值
   出 25Δ／50Δ 三點，算 RR 與 BF，是純算術（~50 行 stdlib）。
   **當下值零成本；歷史對照是唯一難點**——沒有 backfill，只能靠
   `store` 每次刷新累積（§3），要好幾個月才有可用的分位數。
   務實做法：先只顯示「本標的當下各到期日的 skew 斜率」與
   「本組 spread 跨越的那一段斜率相對於同鏈其他段落是陡是平」，
   完全不碰歷史；歷史對照留待 Neon（#50）落地後自然累積。
   **verdict：業界真的據此下單**（RR/BF 是 FX 與股票指數的報價慣例，
   GS 內部資料庫就是用 25Δ 座標存的）。

### M6. Term Structure Relative Value（期限結構）

1. **核心主張**：不同到期日之間的 implied volatility 有一致性條件與
   自身的風險溢酬；「某個到期日相對於它的鄰居貴」是一個獨立的判斷。
2. **需要的資料**：至少兩個到期日的 ATM（或同 log-moneyness）IV ＋ 期限。
3. **實際算法**：換算成**總變異數**再取差：

   ```
   forward variance  σ_f²  = (σ2²·T2 − σ1²·T1) / (T2 − T1)
   ```

   若 `σ2²·T2 < σ1²·T1`（總變異數隨到期遞減），就存在 **calendar spread
   套利**——賣近月買遠月可收淨權利金而無風險【搜尋索引轉述，SVI／SSVI
   無套利文獻】。判斷法：把 σ_f 與「該遠期區間的 RV 預測」或「歷史同
   forward window 的 realized」相比。
   GS 的 PCA 給了期限結構模態的權重：SPX 5.0%、Nikkei 7.9% 的曲面變異
   【原文實證，Table 1】——**比 skew 模態還大一點**。
4. **實證**：搜尋摘要指出 variance risk premium 的期限結構（其斜率）
   對未來股指報酬有預測力、且是股票橫斷面中顯著的因子【搜尋索引轉述，
   多篇；具體係數未取得】。另有研究把 IV 期限結構斜率與未來 straddle
   報酬掛勾【搜尋索引轉述，Jones & Wang，原文被擋】。
5. **適合 Long Call／Put？** 適合——「同一個劇本，買哪個月」是純期限結構
   問題，而這恰好是 Option Chaser 已經在做的事（`timeframe.py` 的
   到期日選取、T9/T10 的每期 Top 10）。
6. **適合 Vertical Spread？** **適合，但只在「跨期比較」時**：對一組
   同到期日的 vertical spread，期限結構是常數、不產生組內排序。
   它回答的是「**哪一期**的 bull call spread 較划算」，不是「該期裡的
   哪一組」。對本產品（畫面上就是橫向到期日選單）這剛好對得上。
7. **最大缺陷**：(a) 陡峭的期限結構常常反映**已知事件**（財報、FOMC、
   到期日群聚），把它當 mispricing 會系統性做空事件風險；
   (b) 遠月流動性差，ATM IV 估計本身誤差大，forward variance 是兩個
   帶噪估計相減，噪音被放大。
8. **Option Chaser 成本**：**最低的一類，零新資料。** 引擎已經按到期日
   分組、已有各到期日的 iv 與期限對齊 r，計算 forward variance 是幾行
   算術。**額外紅利**：`σ2²·T2 ≥ σ1²·T1` 的單調性檢查是一個免費的
   **資料品質檢驗**——Cboe 延遲報價若某期資料髒，這個條件會先破，
   比等到候選池被 `filters.py` 殺光（FB3-02／#45 處理的那個症狀）
   更早、更明確地告訴使用者「這一期的資料不可信」。
   **verdict：業界真的據此下單**（forward vol／calendar 是 vol 台的
   標準部位；calendar 無套利條件是所有曲面模型的硬約束）。

### M7. Delta- 與 Tenor-Normalized 比較（可比座標）

1. **核心主張**：這一項嚴格說不是「判貴賤的方法」，而是**其他所有方法
   得以成立的前提**：固定履約價、固定日曆到期日的兩個報價根本不可比，
   因為標的會動、時間會過。必須換到 (Δ, T) 或 (k = ln(K/F), T) 座標。
2. **需要的資料**：當下鏈 ＋ 每腿 delta ＋ 遠期價（或現價與 r）。
3. **實際算法**：
   - **GS 交易員的實際做法**【原文實證，Kamal & Derman, p.2】：
     「在這兩個資料庫裡，一張選擇權的 implied volatility 被記錄成
     **它的到期期限與它的 Black-Scholes delta 的函數**。交易員常選 delta
     而非履約價本身當第二個變數，因為他們覺得把 implied volatility
     畫成 delta 的函數，可以**移除市場變動時資料裡許多非本質的、
     暫時性的特徵**。」SPX 曲面＝12 個數字（put delta 0.25／delta 0.50／
     call delta 0.25 × 1、3、6、12 個月）；Nikkei 曲面＝54 個
     （9 個等距 delta × 5 個期限）。原文並自行類比：「這就像固定收益
     市場參與者把 on-the-run 債券的殖利率報成到期期限或存續期間的函數，
     再用它插出一條平滑的殖利率曲線。」
   - **OptionMetrics IvyDB**（機構標準歷史資料庫）：每日對每個標的產出
     constant-maturity × delta 網格，期限 10／30／60／91／122／152／182／
     273／365／547／730 日，delta 由 0.10 至 0.90、每 0.05 一格
     （put 為負），以 **kernel smoothing** 在 (ln 到期日數, call-equivalent
     delta) 空間上平滑【搜尋索引轉述】。
   - 另一常見正規化是 **standardized moneyness** `k/(σ√T)`。
4. **實證**：Kamal & Derman 的 PCA 結果本身就是它有效的證據——在
   (Δ, T) 座標下，SPX／Nikkei 兩個由完全獨立的交易員、隔著時差與大洋
   記錄的曲面，前三個模態「形狀驚人地相似」，且解釋 90.7%／95.9% 的
   變異【原文實證】。若座標選錯，不可能出現這種跨市場一致性。
5. **適合 Long Call／Put？** 是——這是把「兩張不同履約價的單腿」放上同一
   把尺的唯一方法。
6. **適合 Vertical Spread？** 是，而且更必要：一組 spread 的兩腿本來就
   落在曲面上兩個不同座標，不先正規化就沒有「這組比那組貴」可言。
   對包裹的自然座標是 **(Δ_long, Δ_short, T)** 或
   **(Δ_mid, ΔΔ = Δ_long − Δ_short, T)**——後者把「位置」與「寬度」
   分離，正是比較不同寬度 spread 的正確方式。
7. **最大缺陷**：(a) delta 由 IV 反算，IV 髒則座標髒；
   (b) sticky-delta 假設本身不總成立（GS 另有整篇在討論 sticky-strike／
   sticky-delta／implied-tree 三種 regime）；(c) 正規化本身不產生任何
   買賣訊號——它只是讓比較合法。
8. **Option Chaser 成本**：**最低。零新資料、零新相依。**
   `valuation.leg_greeks` 已經算出每腿 delta；`AnalysisParams.rate_by_expiry`
   已經是期限對齊利率；`service` 已按到期日分組。要做的只是
   (a) 把候選的識別與呈現從「履約價」改成／並列「delta」，
   (b) 在每個到期日內把 (delta, iv) 排序後線性插值出標準 delta 點。
   大約是一個純函式模組的量，測試容易（給定 fixture 鏈 → 期望網格）。
   **這是投入產出比最高的一張票**：它本身不判貴賤，但它把 M4／M5／M6
   從「不可能」變成「幾十行」，同時直接改善使用者體驗（現在使用者看到
   的是 90/100 這種與標的價位綁死的數字，換月換價後完全不可比）。
   **verdict：業界真的據此下單**——嚴格說是「業界的資料模型本身」，
   比任何單一訊號更根本。

### M8. **Spread-Package Relative Value（包裹層相對價值）** ← 本產品的核心

這是委託特別點名、且公開資料最少的一項。以下把它拆成「恆等式」、
「敏感度分解」、「desk 實務讀法」三層。

#### 8-A 恆等式：vertical spread 的價格就是市場開的機率

由 Breeden & Litzenberger (1978, *Journal of Business* 51:621–651)
【搜尋索引轉述】的結果——歐式 call 價對履約價的二階導數即風險中性密度：

```
∂²C/∂K² = e^(−rT)·q(K)        ⇒        −∂C/∂K = e^(−rT)·Q(S_T > K)
```

對 K 從 K1 積到 K2，得到一個**精確**（不是近似）的等式：

```
C(K1) − C(K2) = e^(−rT) · ∫[K1..K2] Q(S_T > K) dK
```

兩邊同除寬度：

```
淨成本 / 寬度 = e^(−rT) · Q̄，   Q̄ ≡ 區間 [K1,K2] 上 Q(S_T > K) 的平均值
              ≈ e^(−rT) · Q(S_T > (K1+K2)/2)      （寬度不太大時）
```

**這就是判斷一組 vertical spread 貴賤的第一原理**：把它的「成本佔寬度
的比例」讀成「市場認為標的到期站上中點履約價的機率」，然後跟你自己的
機率相比。貴／便宜不是相對於某個歷史水位，而是相對於**你自己的信念**。

**這條恆等式已經藏在本 repo 的排名公式裡**【repo 實證】。
`valuation.evaluate_spread` 在目標價 ≥ 賣腿履約價時，
`baseline_value` 恆為 `width`；於是

```
spread_baseline_return = (width − net_worst)/net_worst = 1/p̂ − 1,
p̂ ≡ net_worst / width
```

我用 repo 自身程式碼實跑驗證（bull call 90/100、買腿 Ask 3.4、賣腿
Bid 0.9 → width 10、net_worst 2.5、baseline_return 3.0；而
1/0.25 − 1 = 3.0，**完全相等**）。

推論——**現行排行榜等價於「照市場隱含機率由低到高排序」**：
`baseline_return` 是 p̂ 的嚴格遞減函數，所以第一名永遠是市場認為
**最不可能成功**的那一組。這在數學上無誤，在產品語意上卻是重大警訊：
它排的是**賠率**，不是**優勢**。使用者若把第一名讀成「最划算」，
他實際上是被推向長賠率彩券。

補正很小：`p̂` 用的是最差成交成本（買腿 Ask − 賣腿 Bid），所以它是
真實隱含機率的**上界**；要換算成風險中性機率需再乘 `e^(rT)`——
而 `rate_by_expiry` 已經在手（T12／#26）。

#### 8-B 敏感度分解：包裹對「水位」不敏感，對「斜率」敏感

把 `∂C/∂K` 在有 smile 的世界展開（鏈鎖法則，`Σ` 為 implied volatility）：

```
∂C/∂K = ∂C_BS/∂K |_Σ  +  Vega · ∂Σ/∂K
      = −e^(−rT)·N(d2) +  Vega · ∂Σ/∂K
```

故（窄寬度極限）

```
call spread 價值 ≈ ΔK · [ e^(−rT)·N(d2)  −  Vega · (∂Σ/∂K) ]
                                            ↑ skew 修正項
```

股票／ETF 常見的負 skew（`∂Σ/∂K < 0`）使修正項為**正**：bull call
spread 因此比「兩腿同一個 IV」的估計**更貴**。直覺一致——你買的是
IV 較高的低履約價腿，賣的是 IV 較低的高履約價腿。
【此展開式的形式與「數位選擇權價 = BS 數位價 − call 的 vega × ∂Σ/∂K」
的標準結果一致，我在搜尋摘要中看到同一敘述【搜尋索引轉述】；
上式本身是可自行覆核的微積分，不依賴任何外部來源。】

**兩個結論直接落到產品上**：

- **ATM IV 的水位（以及它的 IV Rank／IV Percentile）對包裹幾乎不帶
  資訊**——它在兩腿之間大幅相消，只剩二階效應。這是 M9 排在最後的
  技術理由，也是 M1／M2／M3 對本產品貢獻有限的理由。
- **決定包裹貴賤的是 `∂Σ/∂K` 在 [K1,K2] 這一段的平均斜率**。所以
  M8 與 M5 是同一件事的兩種表述：**包裹層的機率讀法 ≡ 局部 skew 的
  價格讀法**。

#### 8-C desk 實務怎麼看一個兩腿包裹

- **把包裹當單一報價物件，不當兩張合約。** 廠商分析工具描述的專業做法
  是：先解出一致的 residual rate 讓 call/put IV 對齊、以平滑後的 skew
  重算 delta、再把 IV 對 delta 作圖，然後才談斜率貴賤；並用
  **vega-neutral ratio**（要賣幾張 OTM 才打平一張 ATM 的 vega）當
  skew 陡峭度的直觀量尺【搜尋索引轉述，ORATS】。
- **skew 交易的標準結構就是 vertical spread 與 risk reversal**：
  業界說法是「許多 skew 的表達方式看起來就是簡單的 vertical spread，
  機構台的優勢在於**在 skew 觀點之上再疊一層 volatility 水位觀點**」
  【搜尋索引轉述，Rival Systems——供專業選擇權台的系統廠商，屬產業
  來源而非學術來源】。
- **公平基準是可算的，而且常態下市場大致公平**：GS 的 25Δ put 減
  25Δ call 對照表（SPX 正常 4–7%／極端 14%／歷史公平 6.0%）
  【原文實證】是我能找到最接近「vertical spread 該多貴」的機構級
  公開基準。它的產品意涵是：**不要把「賣腿收到的權利金」預設成
  超額報酬來源**。
- **SAS 的相減讀法**（見 M4 第 6 問）是把包裹放進曲面框架的正規做法。

現在回答八問：

1. **核心主張**：包裹的成本佔寬度比例，就是市場開出的（折現）機率；
   相對於**你自己的機率**（或某個獨立基準機率）才有貴賤可言。而包裹的
   價格由局部 skew 斜率驅動，不由 IV 水位驅動。
2. **需要的資料**：兩腿報價、寬度、期限對齊 r、期限。**全部已在手。**
   要進一步做「相對於基準」還需要一個獨立的機率估計（可由使用者提供、
   或由 M4 的公平 smile 產生）。
3. **實際算法**：`p̂ = 淨成本/寬度`；`p_Q = p̂·e^(rT)`；
   風險中性讀法的中點履約價 `K̄ = (K1+K2)/2`；賠率 `1/p̂ − 1`
   （＝現行 `baseline_return`）。若要「相對貴賤」，需要第二個機率
   `p_ref`：edge = `p_ref − p_Q`（或以 Kelly 形式呈現）。
4. **實證**：恆等式部分不需要實證——它是無套利下的定義。
   **有爭議的是 `p_Q` 與真實（物理測度）機率的差距**：風險中性密度相對
   物理密度更負偏、尾部更厚，反映崩盤風險溢酬與保險需求
   【搜尋索引轉述】；Gârleanu-Pedersen-Poteshman 從終端使用者淨需求
   解釋這個楔子【搜尋索引轉述】。**方向明確、量級我沒有可信數字**（§7）。
5. **適合 Long Call／Put？** 只部分適合。單腿沒有寬度，`−∂C/∂K` 只在
   微分意義下成立；單腿的「貴」仍要回到 M1–M4。但同一個框架給了單腿
   一個有用的讀數：`N(d2) = 到期 ITM 的風險中性機率`，可以並列顯示。
6. **適合 Vertical Spread？** **這是唯一為包裹量身打造的方法。**
7. **最大缺陷**：(a) `p_Q` 不是真實機率，直接拿來跟主觀機率比會系統性
   高估下跌、低估上漲的機率（風險溢酬楔子），量級未知；
   (b) 用 `net_worst`（Ask−Bid）算出的 `p̂` 會高估真實隱含機率，讓所有
   spread 看起來都比實際貴——不過這個方向是保守的，可接受；
   (c) 「≈ 中點履約價機率」的近似在寬 spread（如 90/120）上會失準，
   應該用精確的區間平均式；
   (d) **它需要使用者提供一個機率**，而本產品目前只收目標價與目標月，
   沒有信心度欄位——這是產品面而非技術面的缺口。
8. **Option Chaser 成本**：**最低的一級。零新資料、零新相依、~20 行。**
   所有輸入（兩腿價、width、`leg_rate`、期限）都已在
   `SpreadValuation` 裡。最小可行版本是把現有的 `baseline_return`
   旁邊多印一個「市場隱含機率 p_Q」與一句白話（「市場認為這件事發生的
   機率約 X%；你認為呢？」）。**這件事的價值幾乎全在敘事而非計算**——
   它把一個容易誤讀成「最划算」的排行榜，改寫成「這是賠率，這是市場
   的機率，你的機率是多少」。
   **verdict：業界真的據此下單**（結構台把 spread 報成數位／機率是
   日常換算；恆等式來自 1978 年的定價基礎文獻）。**同時這也是零售
   教育內容最少覆蓋的一項**——教育文章多半停在「最大獲利／最大虧損／
   損益兩平點」，不做機率換算。

### M9. Historical IV Percentile／IV Rank

1. **核心主張**：當前 ATM implied volatility 在其過去 N（通常 252）個
   交易日分布中的位置，可用來判斷「現在該買還是該賣選擇權」。
   `IV Rank = (IV − IV_min)/(IV_max − IV_min)`；
   `IV Percentile = 過去 N 日中 IV 低於今日的比例`
   【搜尋索引轉述，tastytrade 支援文件的定義】。
2. **需要的資料**：**至少一年份的每日 ATM implied volatility 時序**
   （通常還要是常數到期的 30 日 IV，否則到期日輪替會造成鋸齒）。
3. **實際算法**：如上。normalization 的兩個變體差異在對極端值的敏感度
   ——IV Rank 對單次尖峰極度敏感，一次 spike 會壓低其後數月的讀數
   【搜尋索引轉述】。
4. **實證**：**這是本次調查中證據最薄弱的一項。**
   - 我**沒有找到任何以 IV Rank／IV Percentile 為排序變數的同儕審查
     實證研究**（多次不同措辭的搜尋都只回傳零售券商與教學網站）。
     ⚠ 搜尋找不到 ≠ 不存在；但相對於 M1–M8 每一項都能點名期刊、卷期、
     頁碼，這個落差本身有意義。
   - 學術文獻中與它最接近的、**有**證據的變數是 IV−RV 價差
     （M1，Goyal & Saretto）——注意那是**兩個量的差**，不是**一個量的
     時序分位數**。這兩者不能互相背書。
   - **最有力的反面證據是機構自己的文件**：GS 把「當前與過去 implied
     volatility 的價差」明確歸為「**選擇權投機客**的指標」，並指出
     smile 出現後它就難以對複雜曲面下判斷【原文實證，Zou & Derman
     1999, p.1】——整篇 SAS 論文就是為了取代它而寫的。
   - 連推廣它的一側也承認：高 IV Rank 不代表 IV 會下降，2008／2020／2022
     的持續高波動期間 IV Rank 可以「讀高」數週而 IV 繼續攀升
     【搜尋索引轉述】。
5. **適合 Long Call／Put？** 勉強適合，作為**粗糙的**水位脈絡。它至少
   與單腿的 vega 同號。
6. **適合 Vertical Spread？** **幾乎不適合。** 由 §4-M8-B，包裹對 IV 水位
   只有二階敏感度；IV Rank 描述的正是水位。用 IV Rank 排序 bull call
   spread 在數學上接近排序一個已被相消掉的量。
7. **最大缺陷**：(a) **維度錯配**——它回答 A 型問題（絕對貴），產品問的
   是 B 型（相對貴）；(b) 對 regime 變化無免疫力，在趨勢性 volatility
   環境會持續給出錯誤訊號；(c) 有 skew 時「哪一個 IV」本身就定義不清
   （GS 的批評）；(d) 窗長與 rank/percentile 的選擇會實質改變結論，
   卻沒有理論依據可挑。
8. **Option Chaser 成本**：**全部方法中最高，且沒有可行路徑。**
   需要 ≥252 個交易日的每日 IV。Cboe 端點只給當下；沒有歷史 IV 來源；
   Market Data App 免費層連一次全鏈都抓不完（§3）；自建歷史要靠使用者
   手動刷新累積**一年以上**，而刷新只有三個入口、密度不規律。
   **即「證據最弱 × 對包裹最無關 × 資料最貴」三者同時成立。**
   **verdict：主要是教育材料指標。** 它在零售端無所不在（tastytrade
   推廣、券商介面預設、TradingView 腳本），在機構文獻與機構資料產品裡
   則找不到對應物；GS 的原文更把它的前身歸類為投機客工具。
   這不是說用它的人都錯——它是一個廉價的脈絡指標——但把它當成
   「判斷選擇權貴賤的正確答案」，沒有證據支撐。

### M10. 部位／需求面（demand-based pricing、dealer positioning）

1. **核心主張**：選擇權的貴不是抽象的定價誤差，而是**流量造成的**：
   終端使用者對某些合約（指數 OTM put）是持續淨買方，風險趨避且無法
   完全對沖的中介商因此把價格推高。故「誰持有什麼」可以預測「什麼會貴」。
2. **需要的資料**：分類別的持倉／成交（dealer vs end-user），如 Cboe
   的 open-close 資料；或至少是 open interest 的變化與買賣方向推斷。
3. **實際算法**：以淨終端使用者需求對各合約回歸 implied volatility 殘差；
   模型預測某合約的需求壓力使其價格上升的幅度**正比於其不可對沖部分的
   變異數**，並透過**共變異數**外溢到其他合約【搜尋索引轉述，
   Gârleanu, Pedersen & Poteshman 2009, *RFS* 22(10):4259–4299】。
4. **實證**：同上——該文報告需求壓力效果可解釋指數選擇權「看起來很貴」
   與 smirk，並延伸解釋個股的橫斷面差異【搜尋索引轉述；原文被擋，
   數值未取得】。
5. **適合 Long Call／Put？** 適合（它解釋你要付多少溢酬）。
6. **適合 Vertical Spread？** 部分適合——若兩腿的需求壓力不同，包裹會
   繼承其差額；但把 dealer positioning 對應到特定兩腿的公開資料極稀。
7. **最大缺陷**：資料是機構特權（分類持倉多半付費或不公開）；
   公開的 open interest 沒有方向，推斷買賣方是猜測。
8. **Option Chaser 成本**：**部分可得、整體不可行。** `OptionContract`
   已有 `open_interest` 與 `volume`（免費）；可以做到的最多是「OI 分布
   與異常」這種描述性顯示。真正的 signed dealer flow 沒有免費來源。
   **verdict：業界真的據此下單**（自營台每天看 dealer gamma／positioning），
   但**對本產品的可得性等於零**。

---

## 5. 幾個容易混淆的區分（委託特別要求分開處理的）

- **IV vs Realized（M1）≠ IV vs Forecast（M2）**：前者主張「未來像過去」，
  後者主張「我對未來有比市場更好的模型」。M1 是 M2 令 forecast = 過去
  的特例。證據上，Poon & Granger 那類綜述若成立（implied 優於時序模型），
  對 M1 是**不利**的——因為它意味著 implied 已經吸收了歷史資訊。
- **VRP（M3）≠ mispricing**：VRP 說選擇權**應該**貴。把「IV > RV」當
  mispricing 訊號，等於把風險補償誤認為免費午餐。正確的 M3 用法是
  「今天的 VRP 相對於它自己的常態是高是低」，那需要 VRP 的時序——
  而那需要 realized variance——而那本產品沒有。
- **Skew（M5）≠ Skewness 指數（Cboe SKEW）**：前者是曲面的局部斜率、
  可交易；後者是 30 日風險中性偏度的指數化、是總體風向標。
  對 spread 有用的是前者。
- **曲面相對值（M4）≠ 曲面套利**：殘差多半不是套利，而是流動性、
  需求壓力或資料誤差。GS 自己在 SAS 論文裡就說它是「排序工具」，
  且無法免除人的判斷。

---

## 6. 對本產品的具體結論（不是實作計畫，是判斷）

1. **現行排名量的是賠率。** 應該在畫面上把
   `p̂ = 淨成本/寬度` 明講成「市場隱含機率」，並讓使用者理解
   「排第一 = 市場認為最不可能」。（M8，零成本）
2. **座標要正規化。** 以 delta 與期限標示候選，而不是（或不只是）
   履約價——這是機構資料模型的做法，且是後續一切的前提。（M7，零成本）
3. **貴賤的判斷應該落在「局部 skew」而不是「IV 水位」。**（M5＋M8-B）
4. **不要在沒有 realized volatility 資料源的情況下，硬做 IV−RV／VRP／
   IV Percentile。** 前兩者要新資料源、第三者要一年份歷史，且第三者
   對包裹幾乎沒有資訊。
5. **若要做一個「richness」欄位且只准動一次工程**，做 M4 的降階版
   （每個到期日切片對 log-moneyness 的二次擬合，取 IV 殘差），
   因為它零新資料、直接給每一腿一個 rich/cheap 讀數，
   且包裹的讀數就是兩腿相減。

---

## 7. 未能查證的事項

1. **所有學術論文的原文**（Carr & Wu 2009、Bakshi & Kapadia 2003、
   Goyal & Saretto 2009、Santa-Clara & Saretto 2009、Breeden &
   Litzenberger 1978、Poon & Granger 2003、Christensen & Prabhala 1998、
   Corsi 2009、Xing/Zhang/Zhao 2010、Gârleanu/Pedersen/Poteshman 2009、
   Gatheral & Jacquier 2012、Burghardt & Lane 1990）。全部網域被 proxy
   403。**引用的方法描述來自搜尋索引摘要，未逐字核對。**
2. **具體數字，逐項標明未核實**：
   - Carr & Wu 的做空 variance swap Sharpe ratio（摘要稱 SPX 0.98、
     OEX 0.85、Dow 0.87）——**未核對原文**。
   - 「VRP 約 3–4 個 vol 點、約 85% 的時間為正」——來源是低品質部落格，
     **不採信，本文未使用**。
   - Goyal & Saretto 的多空組合月報酬與 t 值——**完全未取得**。
   - 「挑執行時點者的 effective spread 不到傳統量測的 40%」——
     **未核對原文**。
   - Poon & Granger 的統計（「93 篇」vs「39 篇中 22 篇」兩個互相矛盾的
     搜尋摘要）——**兩者皆不採信**，只保留方向性結論。
   - OptionMetrics IvyDB 的 delta／期限網格具體值——來自廠商頁面摘要，
     **未見原始技術文件**。
3. **Cboe VIX 與 SKEW 官方白皮書原文**（`cdn.cboe.com` 被擋）。
   §4-M3 引用的 VIX 公式形式來自搜尋摘要，**未與官方白皮書對校**。
4. **Goldman Sachs 研究報告的來源真偽**：PDF 取自第三方 GitHub 鏡像
   `s0ap/gs-quantitative-strategies-research-notes`，含完整 GS 版權頁與
   1990 年代原始排版，內部自洽（互相引用、頁碼連續、圖表編號正確），
   我判斷為真；但**未與 goldmansachs.com 官方版本對校**，且發表年份
   在部分篇章的封面上我未逐一確認（SAS 為 1999 年 7 月、
   volatility swaps 為 1999 年 3 月，兩者封面明載；
   "Is the Volatility Skew Fair?" 與 "The Patterns of Change…" 的封面
   月份我未取到，據 SAS 論文的出版清單推定在 1996–1997 年間）。
5. **ORATS 與 AQR 的原文**（皆被擋）。§4-M5 的 constant-maturity slope
   與 vega-neutral ratio 做法、§4-M3 的 AQR 主張，均為搜尋摘要轉述。
6. **本產品可用的免費日線收盤價來源是否存在、且能否從 Vercel 出口 IP
   連通**——沙箱無法測試任何候選端點（全部 403）。這是 M1／M2／M3
   能否落地的唯一未知數，**必須在真環境實測**。
7. **Market Data App 免費層能否以 `date` 參數取歷史全鏈**——
   `docs/research/option-chain-data-sources.md` §5 已列為未查證，本次
   無新進展。
8. **風險中性機率與物理機率之間楔子的量級**（M8 第 7 問的 (a)）——
   方向確定，量級無可信數字。要驗證需要 OptionMetrics 級的歷史曲面
   與後續實現分布。

**要補齊這些，需要**：一個沒有 egress 限制的環境（讀 SSRN／NBER／
期刊 PDF 與 Cboe 白皮書），以及一次從 Vercel 實際部署發出的
HTTP 探測（測日線資料源連通性）。

---

## 8. 排名：有效性 × 適合 Option Chaser × 資料取得難度

「有效性」＝證據強度與機制可靠度；「適合」＝對「同一標的的多組 bull
call spread 排序」這件事的資訊量；「資料難度」＝在 §3 的現況下的取得
成本。**排序原則是有效性優先，資料難度只作為同級內的排序依據，
不作為晉級理由。**

| # | 方法 | 有效性 | 適合本產品 | 資料難度 | 業界 vs 教育 | 置放理由 |
|---|---|---|---|---|---|---|
| 1 | **M8 包裹機率讀法** | 高（定價恆等式，無需實證） | **極高**（唯一為兩腿包裹設計） | **無**（全在手） | **業界交易**（教育內容罕見） | 唯一直接回答產品在問的問題；且已證明現行排名是它的單調變換，補上機率語言即可把「賠率榜」改成可判斷的東西 |
| 2 | **M7 delta／期限正規化** | 高（機構資料模型本身；GS PCA 跨市場一致性佐證） | 高（一切比較的前提） | **無**（`leg_greeks` 已有 delta） | **業界交易**（是資料模型，不是訊號） | 本身不判貴賤，但把 M4/M5/M6 從不可能變成幾十行，同時直接修掉「履約價不可比」的使用者問題。投入產出比最高 |
| 3 | **M5 skew 相對值** | 高（RR/BF 是報價慣例；GS 給了公平值基準） | **高**（包裹價格的一階驅動因子） | 低（當下值零成本；歷史需自建） | **業界交易** | M8 的另一面：既然包裹由局部斜率決定，就該直接量斜率。唯一扣分是歷史分位數要等好幾個月才有 |
| 4 | **M6 期限結構** | 中高（PCA 佔 5–8%；forward variance 是硬約束） | 中（只排「哪一期」，不排「期內哪一組」） | **無** | **業界交易** | 便宜、與畫面上的到期日橫向選單天然對齊，並附帶免費的資料品質檢查；但對組內排序無貢獻，故不進前三 |
| 5 | **M4 曲面擬合殘差（降階版）** | **高**（造市商日常；SVI 是業界標準） | 高（逐腿 rich/cheap，包裹＝相減） | 無新資料，但**工程重** | **業界交易** | 有效性足以進前三，被工程成本與過擬合風險壓下來：stdlib-only ＋ serverless 的約束下要降階成二次擬合；遠月流動性差會讓殘差變成「資料髒」的代名詞 |
| 6 | **M1 IV − RV（含 volatility cone）** | 高（文獻最厚，1990 年就有 JPM 實務論文） | **低**（水位量尺，對包裹相消） | **高**（需新資料源，連通性未知） | **業界交易** | 證據強但問錯問題：它判「絕對貴」，產品問「相對貴」；且要新增第二個網路相依才能開始 |
| 7 | **M2 IV − 預測（HAR 等）** | 中高（vol arb 本業；但 Poon-Granger 若成立則削弱） | 低（同 M1） | **很高**（M1 成本 ＋ 模型 ＋ 高頻資料無免費路徑） | **業界交易**（教育內容少見） | 相對 M1 的邊際改善小、成本高一截，故緊接其後 |
| 8 | **M3 VRP** | 高（有實際成交商品當背書） | **低偏負**（spread 已把 vega 對沖掉；個股/單一 ETF 證據弱） | 高（風險中性那半免費，實現那半無路徑） | **業界交易** | 概念上最重要的「應該貴」教育點，但作為排序工具幾乎無用；且它的結論對本產品的多頭結構是不利而非可操作 |
| 9 | **M10 部位／需求** | 中高（有 RFS 論文與日常實務） | 中（能解釋為何某些腿貴） | **不可得**（signed flow 需付費） | **業界交易** | 有效但資料在自由層完全拿不到，只能退化成 OI 描述性顯示 |
| 10 | **M9 IV Percentile／IV Rank** | **低**（找不到同儕審查實證；機構文件把其前身歸類為投機客指標） | **極低**（包裹對水位只有二階敏感） | **最高**（需 ≥1 年每日 IV，無來源、自建要一年） | **教育材料指標** | 三項全敗：證據最弱、對包裹最無關、資料最貴。它在零售端無所不在，但沒有證據支撐它是「判斷選擇權貴賤的正確答案」 |

**前三名一句話理由**

1. **M8**——把 `淨成本/寬度` 讀成市場機率，是唯一直接針對兩腿包裹的
   第一原理方法；零資料成本，且已證明能把現行「賠率排行榜」翻譯成
   使用者真正需要的判斷。
2. **M7**——delta × 期限座標是機構的資料模型本身（GS 交易員資料庫、
   OptionMetrics IvyDB），引擎已算出 delta，是解鎖其餘方法的鑰匙。
3. **M5**——vertical spread 的價格由局部 skew 斜率一階決定，量斜率就是
   量包裹貴賤；當下值零成本，且 GS 留下了可對照的公平值基準。

**最後一名的判定重述**：委託要求不預設 IV Percentile 是正確答案。
調查結果是**它應該被明確降級**，理由不是「它太簡單」，而是三條獨立的
證據線同時指向同一結論——(i) 找不到同儕審查的實證支持；
(ii) 機構的一手文件把它的前身歸為投機客指標並專門寫論文取代它；
(iii) 對 vertical spread 這個包裹，它量的那個維度在數學上被相消掉。

---

## 9. 引用清單

**【原文實證】（git clone 取得，逐頁讀過；第三方鏡像
`github.com/s0ap/gs-quantitative-strategies-research-notes`）**

- Joseph Zou & Emanuel Derman, *Strike-Adjusted Spread: A New Metric For
  Estimating The Value Of Equity Options*, Goldman Sachs Quantitative
  Strategies Research Notes, July 1999.
  （引用處：richness/cheapness 三種既有量尺與其批評 p.1；SAS 與
  SAS_ATM 定義 p.2–4；skew 公平性與 Table 1 的 25Δ 對照 p.11–12；
  歷史窗選擇改變結論、以及「無法迴避判斷」p.13）
- Emanuel Derman, Michael Kamal, Iraj Kani & Joseph Zou,
  *Is the Volatility Skew Fair?*, GS QSRN.
  （引用處：兩種公平定義 p.2；風險中性期望法 p.3–5；複製法與
  「hedge volatility 高於 realized 3–5 個百分點」p.8–9；結論 p.10）
- Michael Kamal & Emanuel Derman, *The Patterns of Change in Implied
  Index Volatilities*, GS QSRN.
  （引用處：交易員以「期限 × BS delta」記錄曲面、SPX 12 點／Nikkei 54
  點 p.2；PCA 模態與 Table 1 的變異解釋比例 p.6）
- Kresimir Demeterfi, Emanuel Derman, Michael Kamal & Joseph Zou,
  *More Than You Ever Wanted To Know About Volatility Swaps*,
  GS QSRN, March 1999.
  （引用處：skew 對公平變異數的修正 EQ 30–33，linear-in-strike 與
  linear-in-delta 兩種參數化）

**【搜尋索引轉述】學術（原文未取得）**

- Breeden, D. & Litzenberger, R. (1978), "Prices of State-Contingent
  Claims Implicit in Option Prices", *Journal of Business* 51:621–651.
- Carr, P. & Wu, L. (2009), "Variance Risk Premiums", *RFS* 22(3):1311–1341.
  https://academic.oup.com/rfs/article-abstract/22/3/1311/1581057
- Bakshi, G. & Kapadia, N. (2003), "Delta-Hedged Gains and the Negative
  Market Volatility Risk Premium", *RFS* 16(2):527–566.
- Goyal, A. & Saretto, A. (2009), "Cross-section of option returns and
  volatility", *JFE*.
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001251
- Santa-Clara, P. & Saretto, A. (2009), "Option strategies: Good deals
  and margin calls", *Journal of Financial Markets* 12:391–417.
- Poon, S.-H. & Granger, C. (2003), "Forecasting Volatility in Financial
  Markets: A Review", *JEL* 41(2):478–539.
  https://www.aeaweb.org/articles?id=10.1257%2F002205103765762743
- Christensen, B. & Prabhala, N. (1998), "The relation between implied
  and realized volatility", *JFE* 50:125–150.
- Corsi, F. (2009), HAR-RV model（"A Simple Approximate Long-Memory Model
  of Realized Volatility", *Journal of Financial Econometrics*）。
- Xing, Y., Zhang, X. & Zhao, R. (2010), "What Does the Individual Option
  Volatility Smirk Tell Us about Future Equity Returns?",
  *JFQA* 45:641–662.
- Gârleanu, N., Pedersen, L. H. & Poteshman, A. (2009),
  "Demand-Based Option Pricing", *RFS* 22(10):4259–4299.
  https://www.nber.org/papers/w11843
- Gatheral, J. & Jacquier, A. (2012), "Arbitrage-free SVI volatility
  surfaces", arXiv:1204.0646.
- Bakshi, G., Kapadia, N. & Madan, D. (2003), model-free 高階動差
  （Cboe SKEW 方法論的根據）。
- Burghardt, G. & Lane, M. (1990), "How to tell if options are cheap",
  *Journal of Portfolio Management* 16(2):72–78, DOI 10.3905/jpm.1990.409259.

**【搜尋索引轉述】交易所／廠商／產業（原文被 proxy 擋）**

- Cboe, *Volatility Index Mathematics Methodology* /
  *VIX White Paper*：https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Volatility_Index_Mathematics_Methodology.pdf
- Cboe, *SKEW Index* FAQ／白皮書。
- OptionMetrics IvyDB US，volatility surface 產品規格：
  https://optionmetrics.com/united-states/
- ORATS, "Is Skew Cheap Or Expensive?"：https://orats.com/blog/is-skew-cheap-or-expensive
  （constant-maturity slope、vega-neutral ratio 的實務描述）
- Rival Systems, 專業選擇權台的 skew 交易做法（產業系統廠商）。
- AQR, *Understanding the Volatility Risk Premium* (May 2018)。
- tastytrade support, Volatility Metrics (IVR, IV%, IVx, HV) —— IV Rank
  的定義與其零售推廣來源。

**【repo 實證】本 repo（可逐行覆核）**

- `option_chaser/valuation.py`（`bs_call`／`leg_greeks`／`leg_rate`／
  `evaluate_spread`／`spread_scenario_value`／`catchup_price`；
  檔頭 "Stdlib math only"）
- `option_chaser/ranking.py`（`spread_baseline_return` 及其成本口徑註解）
- `option_chaser/filters.py`（四段品質過濾）
- `option_chaser/ratecurve.py`、`option_chaser/data/treasury.py`
  （期限對齊利率曲線）
- `option_chaser/data/cboe.py`（主資料源與其欄位對映）、
  `option_chaser/data/yf.py`（備援）、`option_chaser/data/snapshot.py`
- `option_chaser/service.py`（`CandidateView`／`StrategyResult`／
  `_spread_view`／`fetch_chain`）
- `option_chaser/store.py`、`option_chaser/workspace.py`
  （`list_result_paths`／`spread_history`——自建歷史的既有機制）
- `requirements.txt`（serverless 執行期只有 fastapi，明文排除 yfinance）
- `docs/research/option-chain-data-sources.md`（§3.6 Market Data App
  的 credit 計價、§5 未查證清單）
- **驗算**：`(width − net_worst)/net_worst == 1/(net_worst/width) − 1`
  以 repo 自身 `evaluate_spread`／`spread_baseline_return` 帶入
  width=10、net_worst=2.5 實跑確認（見 §4-M8-A）。
