# 「這張具體合約現在買貴還是買便宜」——canonical 歷史量的重新裁定

研究日期：2026-08-16。**開工前 checkout 核對**（沿用既有紀律）：HEAD ＝
`ad7e50074f99446b1cda63cceb7913a2407b0ff5`，working tree 乾淨，非本專案
多次出現的容器回退狀態（`4d3cea3`）——本文所有【repo 實證】與引擎實算
都對著正確的 tree 做。

本文回答需求方這一句話：

> 「我現在準備買的這張具體 Call／這組具體 Vertical Spread，相對它自己的
> 歷史合理價值，現在到底買貴還是買便宜？」

**委託明文要求：既有已出貨的 fixed-(tenor, delta) 重錨定實作在本文中
評重為零。** 本文不把「已經蓋好了」當成任何一項證據，也不預設
`IV − realized vol` 是 fair-value 殘差。凡是與既有實作結論一致的地方，
都必須另外給出與既有實作無關的獨立理由；凡是與既有實作衝突的地方，
一律照寫。

## 證據分級（每一條實質主張都掛標籤）

- **【一手原文】**——我本人逐字讀過原始文本（論文 PDF、原始碼、規格）。
- **【官方文件】**——我本人實際抓取到的官方 vendor／交易所文件。
- **【二手轉述】**——搜尋索引摘要、部落格、論壇，或**我打不開因此
  只能轉述**的來源。
- **【自行推論】**——本文自己的推導或數值計算（附輸入與重現步驟）。

**紀律**：本文絕不讓【二手轉述】冒充【一手原文】。凡是我打不開的網頁，
一律明說打不開並標【二手轉述】。凡是引用本 repo 既有研究文件中已經
**逐字重製**的原文，標為「【一手原文】（原文出自 X，逐字重製於本 repo
Y 文 §Z）」；只要既有文件只是**描述**而未重製原文，一律降級為
【二手轉述】。

本輪的一手取得成果：**Zou & Derman, *Strike-Adjusted Spread*, Goldman
Sachs Quantitative Strategies Research Notes, July 1999，10 頁 PDF 全文
本輪重新下載並逐頁重讀**（不是沿用前輪轉述），來源見 §15.1。以下所有
標【一手原文】的 SAS 引文，都是我本次從該 PDF 抽出的文字。

---

## 0. 裁決（先給答案）

**單一裁決＝C（hybrid），但是一個非對稱、界線寫死的 hybrid，不是把
A 和 B 攪在一起。**

分成兩句話：

1. **最直接回答需求方那一句問題的量，是 A 家族的「fair-value
   residual」——但回答問題的是「殘差本身」，不是「殘差的歷史」。**
   Zou–Derman 的 SAS 定義就是 `SAS(K,T) = Σ_market(K,T) − Σ_H(K,T)`，
   而 `Σ_H` 是從**標的的歷史報酬分佈**推出來的，**完全不需要這張合約
   的任何報價歷史**【一手原文，§3.1】。需求方句子裡的「歷史」，被
   SAS 用標的的報酬史滿足掉了，不是用合約的報價史。
2. **可以被歷史化、可以掛 1Y 走勢圖／percentile／Δ4w 的 canonical 量，
   只能是 B 家族的 fixed-(tenor, delta) 重錨定序列**——理由不是「已經
   做了」，而是一條與任何 vendor 無關的算術恆等式（§9.4）：
   - A（同一張合約的歷史）需要 **掛牌前置期 L ≥ D + T**
   - B（固定 tenor 的歷史）只需要 **L ≳ D**
   （D＝今天的 tenor，T＝要畫的歷史窗長度，L＝該類合約最長掛牌前置期）
   本產品核心情境 D ＝ 18–36 個月、T ＝ 12 個月，A 需要 L ≥ 30–48 個月，
   而 listed equity/ETF option 的**法規上限就是 39 個月**【二手轉述，
   §9.1】。**D = 882 天（本 repo 真實 fixture 的 TLT LEAPS）時，A 需要
   L ≥ 41 個月 > 39 個月上限——A 在數學上不可能，換哪一家 vendor、
   付多少錢都一樣。**

而**兩者之間不存在第三種選擇**：既是 fair value、又大得過摩擦成本、
又能在 LEAPS tenor 上歷史化的殘差，本文找不到，而且找不到的原因是
結構性的（§5.4）——SAS 裡唯一大得過買賣價差的成分（level／
implied-vs-historical），**GS 自己在論文裡就說不可信並主動歸零**
（SAS_ATM）【一手原文，§3.2】；剩下可信的那一半（skew richness）的
量級，本文用真實全鏈實測是 **0.15–0.5 vol 點，只有買賣價差半寬的
0.10–0.27 倍**【自行推論＋真實資料，§4.5】。

因此逐條裁決：

| 委託指定的問題 | 裁決 |
|---|---|
| A／B／C 哪個最直接回答「這張現在貴不貴」 | **A 家族的殘差本身**最直接；**A 的歷史**不但不回答這個問題，而且在本產品 tenor 上不存在 |
| canonical 歷史量到底該是什麼 | **fixed-(tenor, delta) 重錨定序列**（B 的座標系）——這是 OptionMetrics 標準化曲面（10–730 天 × delta 0.10–0.90）的同一個選擇【二手轉述，§4.4】 |
| Call 怎麼定義 | 買腿座標 `(D, |Δ_buy|)` 的 IV（level 語言） |
| Vertical Spread 怎麼定義 | 兩腿座標各自的 IV，**加上**以 ATM 正規化的 skew `Ĝ`；**不得**壓成單一「Spread IV」（§6.1 引擎實算：net-volatility 公式在真實 TLT 部位上 1% 輸入擾動造成 0.41 vol 點跳動，且解出 −0.74 vol 點的無意義值） |
| percentile／Δ4w 掛在哪個量上 | 掛在**上一列那些重錨定序列**上，**不得**掛在任何 fair-value 殘差上（殘差在本產品 tenor 上沒有足夠歷史） |
| 既有 fixed-tenor/delta 機器哪些是必要 normalization | 固定 tenor、固定 delta、不外插、skew ÷ ATM、rank 統計量——五項全部是必要且有業界先例（§12.1） |
| 哪些不該被當成訊號 | 買腿 IV percentile 被當成「貴不貴」的答案、Ĝ 的絕對值跨候選比較、Δ4w 被當成方向、觀測筆數 <10 的 percentile、貼著網格邊界的 ATM 內插（§12.2） |
| `IV − realized vol` 算不算 fair-value 殘差 | **明確否決**。SAS 論文第 1 頁把它列為與 SAS 並列的**另一把尺**，是「options replicators 的指標」，且「在有 skew 時就變得不精確」【一手原文，§5.3】。它量的是 **variance risk premium**（承擔 vol 風險的補償），不是這張合約相對它自己該有的價格 |
| 殘留 blocker | **只有一個**：TLT 這一類 ETF 的實際最長掛牌前置期 L（§14.1）。它只影響「A 在 18–24 個月 tenor 上可不可行」這條邊界；**不影響** 882 天核心情境的裁決（那條由 39 個月法規上限就已鎖死） |

**與已出貨實作的關係（刻意寫在最前面，避免被誤讀成背書）**：本文的
canonical 座標系結論**與已出貨的 B 實作一致，但三件事不一致**：

1. **既有機器回答的不是需求方問的那個問題**，而且再怎麼加工也不會變成
   回答那個問題（§11.1）。買腿 IV percentile 是 SAS 論文開篇點名的
   「options speculators 的指標」【一手原文】，它回答「現在的 vol 水位
   在歷史哪裡」，不回答「這個價格對不對」。
2. **`ivhistory` 的 delta 座標與 vendor 曲面網格的 delta 很可能不同
   convention**（引擎 `q=0` vs vendor 帶股利），本文引擎實算顯示同一張
   真實 TLT LEAPS 的 delta 是 0.7194（q=0）vs 0.4478（q=4.5%），
   若 vendor 網格帶 q，查表會落在 **K=74.03 而不是 K=85**、
   系統性偏 **−1.95 vol 點**（§12.3）。這是**可驗證的風險，不是已確認
   的 bug**——vendor greeks 的 q 慣例在本沙箱無法驗證（#111）。
3. **超出掛牌天花板的 tenor 應該誠實顯示「這個 tenor 沒有可比歷史」**，
   而不是用零星幾點湊出一條 percentile（§12.2 第 4 點、§9.4）。

---

## 1. 取材限制（本節先講，因為它決定後面每一節的證據等級）

本沙箱的 egress proxy 對絕大多數外部網域回 CONNECT 403。本輪逐一實測：

**打不開（皆 EGRESS_BLOCKED / CONNECT 403，各只重試一次）**：
`docs.marketdata.app`、`www.marketdata.app`、`cdn.cboe.com`、
`ww2.cboe.com`、`www.cboe.com`、`www.sec.gov`、`www.govinfo.gov`、
`www.federalregister.gov`、`www.optionseducation.org`（OCC）、
`www.theocc.com`。**因此本文沒有任何一條【官方文件】等級的證據**——
委託要求抓取 https://docs.marketdata.app/ 的部分，實測 DNS 都解析不到
（`getaddrinfo ENOTFOUND docs.marketdata.app`），該項在本文一律降為
【二手轉述】或引用本 repo 既有紀錄。

**打得開**：
- `raw.githubusercontent.com`（沿用前幾輪唯一通道）——本輪由此取得
  **SAS 全文 PDF**（§15.1）與**一份真實 Cboe 全鏈 JSON**（§15.2）。
- `WebSearch`（索引摘要）——一律標【二手轉述】。
- GitHub REST API（`api.github.com`）**在本 session 被 scope 限制**：
  對 `l26041040/option-chaser` 以外的 repo 回
  「GitHub access to this repository is not enabled for this session」，
  因此 `search_code`／`search_repositories` 路線不可用，鏡像路徑改用
  WebSearch 定位 ＋ `raw.githubusercontent.com` 直取。

**引擎實算的環境**：`/home/user/option-chaser/.venv/bin/python`，
`PYTHONPATH=/home/user/option-chaser`。所有腳本放在 session scratchpad
（**未進 repo，未 commit**），全文與參數列在 §15.3，任何人可貼回去重跑。

---

## 2. 問題定義：需求方那句話裡藏了三個不同的問題

把「相對它自己的歷史合理價值，現在買貴還是買便宜」拆開，會發現裡面
擠了三個彼此獨立、答案來源完全不同的問題【自行推論】：

| # | 問題 | 需要什麼資料 | 學名 |
|---|---|---|---|
| Q1 | 這個價格相對**它應該值多少**，貴還是便宜？ | 今天的鏈 ＋ 一個 fair-value 模型 | rich/cheap vs fair value（SAS、theoretical edge） |
| Q2 | 這個 vol 水位／結構相對**它自己過去的水位**，高還是低？ | 這個座標的歷史 IV | historical position（IVR／IV percentile） |
| Q3 | 我今天付的**這個 edge** 相對**過去我能拿到的 edge**，好還是差？ | 每一天的 Q1 答案 | residual history（＝Q1 的歷史化） |

**這三個是不同的問題，答案可以互相矛盾。**一條整體偏貴但今天比昨天
便宜的 surface，Q1 說貴、Q2 說便宜。SAS 論文開篇就是在區分 Q1 與 Q2：

> “The most common gauge of options value has been the spread between
> current and past implied volatilities. **This is the metric of options
> speculators**, who hope to get in at historically low volatilities,
> hedge for a while, and get out high.”
> 【一手原文，Zou & Derman 1999, p.1】

那一段講的正是 Q2。SAS 自己要解的是 Q1。**需求方的句子字面上問的是
Q1（「相對合理價值」），但「歷史」兩個字與 1Y 走勢圖／percentile／Δ4w
三種呈現形式，把它拉向 Q3。**本文的整個結構就是回答：Q1 能不能算
（能，§3–§6）、Q3 能不能算（本產品 tenor 上不能，§9）、既有機器算的
是 Q2（是，§11.1）。

---

## 3. Research A-1：SAS 的一手解剖（全文重讀）

### 3.1 SAS 到底定義了什麼（四步，逐字）

論文第 2–3 頁把 SAS 拆成四個編號步驟【一手原文】：

> 1. First, choosing some historically relevant period, we obtain the
>    distribution of stock returns over time T. This empirical return
>    distribution characterizes the past behavior of the stock.
> 2. Option theory dictates that options are valued as the discounted
>    expected value of the option payoff over the risk-neutral
>    distribution. We do not know the appropriate risk-neutral
>    distribution. However, we use the empirical return distribution as
>    a statistical prior to provide us with an estimate of the
>    risk-neutral distribution by minimizing the entropy associated with
>    the difference between the distributions, subject to ensuring that
>    the risk-neutral distribution is consistent with the current forward
>    price of the stock. We call this risk-neutral distribution obtained
>    in this way the risk-neutralized historical distribution, or RNHD.
> 3. We then use the RNHD to calculate the expected values of standard
>    options of all strikes for expiration T, and convert these values to
>    Black-Scholes implied volatilities. … This is our estimated fair
>    option volatility.
> 4. For an option with strike K and expiration T, whose market implied
>    volatility is Σ(K,T), the strike-adjusted spread in volatility is
>    defined as `SAS(K,T) = Σ(K,T) − Σ_H(K,T)`. This spread is a measure
>    of the current richness of the option based on historical returns.

逐項回答委託的「機制要弄對」：

- **reference distribution ＝** 標的自己的**經驗報酬分佈**（不擬合任何
  隨機過程），再用 minimum relative entropy 傾斜成滿足 forward 條件的
  risk-neutral 分佈（RNHD）。論文明講為什麼不走 replication 路線：
  「Not only is this replication cost difficult and time-consuming to
  simulate, but, in our experience, the hedging errors due to inaccurate
  volatility forecasting and infrequent hedging make the resulting
  statistics inconclusive.」【一手原文，p.2】
- **being differenced ＝** 兩個**BS implied volatility**（不是價格、
  不是美元）。fair 那一側是把 RNHD 定出來的價格再反解成 BS IV。
- **over what history ＝** 使用者自選的「historically relevant period」；
  論文範例用 **12 年**（1987-05 至 1999-05）算一個 3 個月期的公平 skew，
  另一版本刻意排除 1987 崩盤只用 11 年【一手原文，p.13 圖 5／圖 6】。
- **held fixed ＝** `(K, T)`。**市場 IV 與公平 IV 在同一個 `(K,T)` 上取
  值**——這一點在 §8.1 會變成 A 家族唯一真正的技術優勢。

### 3.2 SAS_ATM：GS 自己把 level 那一半關掉

論文絕大多數情況用的是加了約束的版本【一手原文，p.3】：

> “The volatility skew, the relative gap between at-the-money and
> out-of-the-money implied volatilities for a given expiration, is more
> stable than the absolute level of at-the-money implied volatilities.
> Often, therefore, irrespective of historical return distributions, the
> current level of at-the-money implied volatility is the most believable
> estimate of future volatility. **It is likely that historical
> distributions tell us more about the higher moments of future
> distributions than it does about their standard deviation.**”

於是把 RNHD 進一步約束到市場 ATM-forward vol（RNHD_ATM），使
`SAS_ATM(S_F[T], T) = 0`；結論章講得更白【一手原文，p.21】：

> “Most often, in liquid markets, we calibrate the SAS to be consistent
> with current at-the-money volatility, **so that it becomes a measure of
> skew richness as compared with history**.”

**這一段是本文整條論證線上最重要的一手證據**（§5.4 會用到）：SAS 家族
裡**唯一被作者自己認證可信的部分是 skew richness**，level 那一半被
主動歸零，理由是歷史分佈根本不該拿來預測 vol 水位。

### 3.3 SAS 的用途定位＝橫斷面排序，並且明示對標 OAS

> “This method leads us to the notion of Strike-Adjusted Spread, or SAS,
> a natural one-dimensional metric with which to rank the relative value
> of all standard equity options, irrespective of their particular strike
> or expiration. **We propose to use SAS in roughly the same way that
> stock investors use “alpha” and mortgage investors use OAS
> (option-adjusted spread).**”【一手原文，p.2】

兩點推論：

- **SAS 的原生形態是橫斷面（cross-sectional）**：今天，把所有 strike ×
  expiry 排在同一條尺上。**不是**「今天 vs 過去每一天」。【自行推論】
- **但 OAS 這個類比本身是支持歷史化的**：MBS 圈把 OAS 跟它自己的歷史
  平均／percentile 相比、判斷 rich/cheap，是成文的標準做法
  【二手轉述】。所以「把 SAS 歷史化」不是誤用，是照著論文自己給的
  類比往下走。**A 家族的動機是正當的**——它敗在可得性（§9），不敗在
  概念。

### 3.4 論文有沒有真的把 SAS 歷史化？——有兩個時點，沒有序列

這是委託問題 3 的關鍵。論文**確實**在兩個日期各算一次 SAS_ATM 並比較
變化【一手原文，p.13–15，圖 5／6 為 1999-05-18、圖 7 為 1999-06-21】：

> “Although at-the-money volatility has now fallen from 25.5% to 21%,
> the size of skews has remained relatively stable. … the strike-adjusted
> spreads have changed so that out-of-the-money puts have become about
> two SAS points cheaper… If you had thought the relevant historical
> distribution was the crash-inclusive one of Figure 5, and had bought
> cheap puts, **you would have lost SAS**.”

也就是說：**論文明確把 SAS 的變化當成你的損益**，這在概念上就是
「SAS 是可以有時間序列的量」。但論文**沒有**建構任何 SAS 時間序列、
沒有 SAS percentile、沒有 SAS 走勢圖——只有兩個快照的對照。
【一手原文＋自行推論】

**同一段還坐實了 SAS 的一個致命實務缺陷**：圖 5（含 1987 崩盤）說 OTM
put「slightly cheap」，圖 6（排除 1987 崩盤）說同一批 OTM put
「much too rich」——**同一天、同一批合約，只因為歷史窗換了 11 年 vs
12 年，結論正負號翻轉**。論文自己下的警語【一手原文，p.13／p.21】：

> “There is no escaping the judgement necessary to decide which past
> period is most relevant to the current market…”
> “The SAS ranking cannot be used blindly; it depends on the user's
> selection of the historical period most relevant to the current market.”

對一個以 **facts-only、不做評價字眼**為紅線的產品（本 repo 既有裁示），
一個「換個參數就翻號、而且沒有客觀方法選那個參數」的頭條數字，
是產品層的重大風險【自行推論】。

### 3.5 SAS 給本產品的兩條紅線（腳註 3）

> “A positive SAS connotes richness **only for standard options whose
> value is a monotonically increasing function of volatility**. Exotic
> options may have values that decrease as volatility increases.”
> 【一手原文，p.3 footnote 3】

vertical spread 的價值對 σ **非單調**（本 repo 既有引擎實證，
`iv-relative-history-methodology.md` §5.3）。因此**任何 SAS 家族的實作
都必須逐腿做，永遠不能對 spread 湊一個單一 vol 數字**。1999 年的 GS
原文與本 repo 2026 年的引擎實算在同一結論上會師——這一條在 §6 會再被
一次獨立的引擎實算確認。

---

## 4. Research A-2：1999 之後的成熟簡化與延伸（本節主要靠【二手轉述】）

**本節聲明**：除了 §4.5 的真實資料實測之外，**本節所有 vendor 相關
敘述都是【二手轉述】**——所有 vendor 官網（orats.com、
docs.orats.io、spiderrock.net、optionmetrics.com、ivolatility.com、
datashop.cboe.com）在本沙箱皆不可達，內容來自搜尋索引摘要。

### 4.1 SAS 的直系後代：把「歷史公平 smile」換成「今天的平滑 fit」

1999 之後真正被產品化的，不是 RNHD，而是把 `Σ_H` 換掉的簡化版：

- **ORATS SMV / S%（smoothed edge）**：SMV 系統「cleans and normalizes
  quotes, solves for a residual yield rate, and fits a non-arbitrageable
  smooth curve through strike implied volatilities」；S% 是 SMV 值與
  成交價的距離。另有 D%（distribution edge，用報酬分佈定公平值——
  血統上就是 SAS 的直系後代）與 F%（forecast edge）。資料自 2007 起。
  【二手轉述】
- **SpiderRock**：「Theoretical volatility surfaces are models of the
  fair market volatility of an option… The gap between market IV and the
  fitted IV at each strike is the residual — any contract whose market
  IV is significantly above the curve is 'rich', below is 'cheap'.」
  並提供 current valuation theoretical edge、edge 部位的 P&L 追蹤，
  以及**定期封存的歷史 volatility surface**。【二手轉述】
- **Cboe `theo`（Hanweck 擬合值）**：免費層同思想；本 repo 已實測過它
  與 mid 的獨立性（`option-liquidity-filtering.md` §6.5）。
- **IVolatility IVolLive**：提供「IV surfaces … to fair value and touch
  probabilities」、「Fair values and full Greeks for any option」、
  以及 IV Rank／IV Percentile／IV–HV Spread 三種歷史位置指標。
  【二手轉述】

### 4.2 這一整家族**不是** fair value——這是本文最重要的正名

【自行推論，但依據是各家自己的定義文字】：smooth-fit residual 量的是
**這張合約相對「它自己所屬的那條 smile」偏離多少**。它的參照系是
**今天、同一個標的、同一個 expiry 的兄弟合約**。因此：

- 整條 surface 一起貴 20%，smooth-fit residual **恆為零**。
- 它回答的是「同一條鏈上誰報錯了」，不是「這條鏈該不該是這個價」。
- 它的正當用途是**挑選品質**（在已經決定要買的候選之間，避開明顯
  脫離曲線的那一張）與**報價健全性**，不是 rich/cheap 的判決。

這與本 repo 既有的 `spread-surface-residual-rv.md` 的定位（「安靜的
保險絲＋挑選品質客觀化」）一致，但本文的理由是獨立的：**參照系不同**。
SAS 的參照系是標的的歷史報酬分佈（外生），smooth fit 的參照系是今天的
市場自己（內生）。**內生參照系不可能判斷市場整體貴賤**，這是定義問題
不是精度問題。

### 4.3 有沒有「per-contract 每日 residual 歷史序列」的成熟具名實務？

**結論：沒有找到任何具名的成熟實務。**【檢索性結論，證據等級
【二手轉述】】

本輪檢索到最接近的三件事，逐一說明差在哪：

1. **SpiderRock 封存歷史 surface ＋ 提供 theoretical edge**——但公開
   資料描述的是「archives volatility surfaces at regular intervals for
   historical analysis」，也就是**歷史曲面**（＝B 的座標系），加上
   **當下**的 edge；沒有查到「某一張 OCC 合約的 edge 歷史百分位」這種
   現成欄位。【二手轉述】
2. **ORATS 提供 IV rank／percentile「for the last month and year」**
   ——但那是**標的層級的 IV**（Q2），不是 per-contract 的 edge 歷史
   （Q3）。【二手轉述】
3. **MBS 的 OAS 歷史 percentile** 是成熟具名實務【二手轉述】，而
   SAS 明示對標 OAS——**但 MBS 與 listed option 有一個關鍵差異：
   一檔 MBS pool 的存續期以年計、它每天都存在；一張 listed option
   在你想觀察的那個 tenor 上根本還沒掛牌**（§9）。類比在概念上成立，
   在資料可得性上不成立。

因此對委託問題 3 的正式回答：**不存在**一個成熟、有名字、可引用的
「for a single listed option, at every historical timestamp, market −
fair, producing a historizable residual series」的業界實務。查不到不等於
不存在（我打不開任何一家 vendor 的官方文件），但**四個獨立來源家族
（sell-side 一手論文、vol vendor、資料商、零售平台）都沒有出現這個
產品形態**，而且 §9 給出了它為什麼不會出現的結構性理由。

### 4.4 業界真正歷史化的東西是什麼：OptionMetrics 的答案

**這是本文找到最有力的「業界 canonical 量」證據**【二手轉述】：

> OptionMetrics IvyDB 每天為每個標的計算一張 standardized
> constant-maturity volatility surface，expirations 為 **10, 30, 60, 91,
> 122, 152, 182, 273, 365, 547, 730 個曆日**，deltas 為
> **0.10 … 0.90（每 0.05 一格）**。

三個推論【自行推論】：

1. **業界資料標準把「可歷史化的量」定義成 (constant maturity, delta)**
   ——不是 (contract)。這與 A／B 之爭的答案完全一致，而且這個證據與本
   repo 的實作決策完全無關（OptionMetrics 的 schema 早於本專案）。
2. **最長 tenor 是 730 天（24 個月）**。這不是懶惰——它恰好落在
   §9 推導出的掛牌天花板附近。**連 OptionMetrics 都不敢承諾 730 天
   以上的標準化曲面**，而本產品的核心情境是 882 天。
3. **delta 軸只到 0.90／低到 0.10**：邊界之外不外插。與本 repo
   `iv_at()` 的「出界回 None」是同一個紀律。

### 4.5 最常見的簡化版有多大？——真實全鏈實測

【自行推論，真實資料，可重現】。資料：**真實 Cboe delayed-quote 全鏈，
YETI 2023-08-11，758 筆合約**，由 `raw.githubusercontent.com` 鏡像取得
（§15.2；與本 repo `cboe-field-semantics.md` 用的是同一個檔案）。

方法（腳本 `exp2_noise.py`，§15.3）：對每個 expiry 取 **OTM-only**、
`bid>0`、`iv>0`、`vega ≥ 0.01`，以 vega 加權對 `k = ln(K/S)/√T` 做
二次式 WLS 擬合，殘差 ＝ `iv − fit(k)`；另一路用 vendor 自己的
`theo`，殘差 ＝ `(mid − theo)/vega`。噪音底線 ＝
`(ask − bid)/2 / vega`。**分子分母都用 vendor 自己的 vega，因此
q=0／美式歐式的口徑問題是共模、不進入比值。**

| DTE | n(OTM) | 買賣價差半寬（vol 點） | med\|殘差\|(smile fit) | 倍數 | med\|殘差\|(vendor theo) | 倍數 |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 16 | 2.65 | 0.50 | 0.19× | 1.20 | 0.45× |
| 14 | 24 | 2.30 | 0.61 | 0.26× | 1.15 | 0.50× |
| 21 | 15 | 2.32 | 0.62 | 0.27× | 1.33 | 0.57× |
| 28 | 16 | 2.07 | 0.31 | 0.15× | 0.71 | 0.34× |
| 35 | 8 | 1.24 | 0.33 | 0.27× | 0.74 | 0.60× |
| 42 | 20 | 2.53 | 0.31 | 0.12× | 0.61 | 0.24× |
| 49 | 20 | 2.00 | 0.37 | 0.18× | 0.57 | 0.28× |
| **98** | 16 | 1.35 | **2.14** | **1.58×** | 0.46 | 0.34× |
| 161 | 26 | 0.93 | 0.81 | 0.87× | 0.61 | 0.66× |
| 189 | 14 | 1.11 | 0.11 | 0.10× | 0.15 | 0.13× |
| 315 | 16 | 0.80 | 0.12 | 0.15× | 0.13 | 0.16× |
| **525（LEAPS）** | 21 | **0.80** | **0.16** | **0.21×** | **0.20** | **0.25×** |

**讀法**：倍數 < 1 ＝ 殘差整個埋在買賣價差半寬裡面。**除了 DTE 98
（一個冷門 expiry）之外，每一個 expiry 的中位殘差都只有半寬的
0.10–0.66 倍；LEAPS 那一期是 0.21×／0.25×。**

【自行推論】結論：**簡化版 fair-value 殘差在 LEAPS 上是可以算的，但
它比你進場要付的滑價小 4–5 倍。**把它當頭條數字，等於請使用者盯著
一個比手續費還小的量做決策。

---

## 5. Research A-3：四種「殘差」的正名（哪些配叫 fair value）

【自行推論，分類依據為各方法的參照系；SAS 那一欄有【一手原文】背書】

| 方法 | 參照系 | 真正量的是什麼 | 配不配叫 fair value |
|---|---|---|---|
| **SAS / SAS_ATM（RNHD）** | 標的的**歷史報酬分佈**（外生） | 這個 strike 的市場 IV 相對「歷史報酬所隱含的公平 IV」的價差 | **配**。這是本文找到唯一一個定義上真的是 fair value 的 listed-option 殘差 |
| **smooth-fit residual（SMV/S%、`theo`、SpiderRock edge）** | **今天自己的 smile**（內生） | 這張合約相對兄弟合約的偏離 | **不配**。整條鏈一起貴時恆為零（§4.2） |
| **IV − realized vol（IV−HV、VRP）** | 標的的**已實現波動** | 承擔 vol 風險的補償（variance risk premium） | **不配**，見 §5.3 |
| **IV percentile / IV Rank** | **這個座標自己的 IV 歷史** | 水位的歷史位置 | **不配**。這是 Q2，不是估值 |

### 5.1 為什麼 smooth-fit 殘差不配（重申，因為最容易被混淆）

它的參照系是市場自己。市場整體錯價時它看不見。它是**arbitrage /
consistency** 檢查，不是 **valuation**。ORATS 自己的描述用的詞是
「fits a non-arbitrageable smooth curve」——目標函數是**無套利與平滑**，
不是公平【二手轉述】。

### 5.2 為什麼 IV percentile 不配

SAS 論文第 1 頁把它點名為「the metric of options **speculators**」
【一手原文，§2 引文】。它假設「歷史上這個座標的 vol 水位分佈」就是
公平的參考——但那個分佈本身可能整段偏貴（例如整個期間 VRP 都是正的）。
**在一個系統性偏貴的市場裡，第 20 百分位仍然是貴的。**【自行推論】

### 5.3 `IV − realized vol` 明確否決（委託指定要正面回答）

**否決。**理由三條，前兩條有一手背書：

1. **SAS 論文把它列為與 SAS 並列的另一把尺，不是 SAS 的一種**
   【一手原文，p.1】：
   > “A second gauge is the spread between current implied and past
   > realized volatilities. **This is the metric of options
   > replicators**, who hope to lock in the difference between future
   > realized and current implied volatilities by delta-hedging their
   > options to expiration. **This comparison becomes imprecise in the
   > presence of a volatility skew**, when there are a range of implied
   > volatilities, varying by strike, that must be compared with only a
   > single historical realized volatility.”
2. **論文明說 SAS 是它在有 skew 時的推廣，兩者只在無 skew 世界重合**
   【一手原文，p.2】：
   > “SAS can be thought of as an extension of the commonly quoted
   > implied-to-historical volatility spread, **which is unique only in
   > the absence of skew. In non-skewed worlds, both spreads become
   > identical.**”
   ——也就是說：`IV − RV` 是 SAS 的**退化特例**，而且它退化掉的正是
   「這個 strike」這件事。本產品買的是**特定 strike 的 vertical
   spread**，退化掉 strike 等於退化掉整個問題。
3. **它量的是風險溢酬，不是錯價**：variance risk premium 被定義為
   風險中性測度與實體測度下期望變異數之差，是「承擔 vol 與報酬負相關
   這個風險的補償」【二手轉述，Carr–Wu 一脈】。**一個持續為正的補償
   不是錯價**——它是市場對保險賣方的付費。把它當成「買貴了」，等於
   說「保險永遠買貴」。

**它正確的用途**：它是一個誠實的**成本揭露**——「你付的 IV 比這個標的
過去實際波動的水準高 X 點」。這是事實敘述，可以放進方法論尾註或次層，
但**不能掛 fair-value 的名字，也不能當 rich/cheap 判決**。

### 5.4 結構性結論：可信的那一半太小，夠大的那一半不可信

把 §3.2 的一手引文與 §4.5 的實測併起來【自行推論】：

- SAS = level 成分 + skew 成分。
- **level 成分**（≈ implied vs historical volatility）夠大（TLT LEAPS
  的 IV 12–18% vs 長期已實現波動，隨便就是好幾個 vol 點），
  **但 GS 自己說不可信**並在 SAS_ATM 裡主動歸零：「the current level of
  at-the-money implied volatility is the most believable estimate of
  future volatility」【一手原文】。而且它就是 §5.3 剛否決掉的 VRP。
- **skew 成分**（SAS_ATM）**可信**，但量級與 smooth-fit 殘差同級：
  §4.5 實測 LEAPS 上是 0.16–0.20 vol 點 vs 0.80 vol 點的半寬。

**因此：不存在一個既可信、又大得過摩擦、又能歷史化的 fair-value
殘差。**這不是工程問題，是這個問題本身的結構。任何主張「做一個
per-candidate fair-value 殘差當頭條」的方案，都必須先回答這三難。

---

## 6. Research A-4：Vertical Spread 該逐腿還是整包（引擎實算）

委託問題 6。答案：**逐腿算殘差，再用各自的 vega 換成美元、依部位方向
相加**。理由是「整包」的兩條路都死了。

### 6.1 「整包 vol」路線的死法：net volatility 公式的數值不穩定

業界確實有 **net volatility** 這個具名概念（spread 的「隱含波動率」，
兩腿以 vega 加權）【二手轉述】：
`σ_net = (σ_L·ν_L − σ_S·ν_S) / (ν_L − ν_S)`

【自行推論，引擎實算，腳本 `exp4_spread.py`】。輸入＝本 repo 真實
fixture `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`：
S=84.52、DTE 882（T=2.4164y）、r=0.04；買腿 K=85（bid 5.65／ask 5.90、
iv 0.12）、賣腿 K=130（bid 0.63／ask 0.73、iv 0.18）。Greeks 用
`option_chaser.valuation.call_greeks`（`vega_per_pct` ＝ $/1 vol 點）。

| q | 買腿 Δ | 賣腿 Δ | 買腿 vega/pt | 賣腿 vega/pt | net vega/pt | σ_net | σ_net（賣腿 vega +1%） |
|---|---|---|---|---|---|---|---|
| 0.000 | 0.7194 | 0.1461 | $0.4427 | $0.3010 | $0.1418 | **−0.74 vol 點** | −1.14（**跳 0.41 點**） |
| 0.045 | 0.4478 | 0.0670 | $0.4701 | $0.1662 | $0.3039 | 8.72 vol 點 | 8.67（跳 0.05 點） |

三個致命點【自行推論】：

1. q=0 時 `σ_net = −0.74`——**負的波動率**，而兩腿實際 IV 是 12% 與
   18%。這個「spread 的 IV」不在任何一腿附近，也不在任何有意義的區間。
2. 分母 `ν_L − ν_S` 是 net vega，對 vertical debit spread 而言又小又
   會穿零；**賣腿 vega 只要動 1%，σ_net 就跳 0.41 vol 點**。任何以它為
   基礎的 percentile 都在量自己的數值噪音。
3. 同一組真實報價，換一個 q 假設，σ_net 從 −0.74 變 8.72——**這個量
   對本 repo 尚未鎖定的 q 模型（#110／#113）一階敏感**。

這與 SAS 腳註 3 的一手警語（spread 價值對 σ 非單調，SAS 只對單調標的
成立）是同一件事的兩個側面【一手原文＋自行推論】。**否決任何單一
「Spread IV」。**

### 6.2 可行的整包做法：price space 直接可加

【自行推論】逐腿殘差 `r_b, r_s`（vol 點）換成美元再相加，是良定義的：

```
resid_$(package) = ν_b · r_b − ν_s · r_s
```

它**不需要除以任何會穿零的東西**，在 net vega ≈ 0 時照樣成立。這正是
委託問「per-leg then combine 有沒有標準加權」的答案：**加權就是各腿
自己的 vega，符號就是部位方向**。這也是 §3.5 腳註 3 唯一允許的做法
（SAS 逐腿定義，包裹的 richness 是兩腿殘差相減）。

### 6.3 它有多大？跟進場摩擦比一比（同一組真實報價）

| 情境（買腿, 賣腿 殘差 vol 點） | q=0 → 包裹殘差 | % of mid debit | 倍數 vs 進場摩擦 | q=4.5% → 包裹殘差 | 倍數 |
|---|---|---|---|---|---|
| (+0.23, +0.23)（§4.5 實測 LEAPS RMS） | +$0.0326 | +0.64% | **0.19×** | +$0.0699 | **0.40×** |
| (+0.23, −0.23) | +$0.1710 | +3.36% | 0.98× | +$0.1464 | 0.84× |
| (+0.50, 0.00) | +$0.2214 | +4.34% | 1.26× | +$0.2351 | 1.34× |
| (+1.00, +1.00) | +$0.1418 | +2.78% | 0.81× | +$0.3039 | 1.74× |

mid debit ＝ 5.095，worst debit ＝ 5.270，**進場摩擦（兩腿各半個
價差）＝ 0.175 ＝ mid debit 的 3.4%**。

【自行推論】**在最貼近實測的那一列（兩腿各 0.23 vol 點），整包殘差只有
進場摩擦的 0.19–0.40 倍。**要讓殘差贏過摩擦，得假設兩腿殘差**反號**
（+0.23/−0.23）或**單腿 0.5 點以上**——而 §4.5 的實測分佈說這在 LEAPS
上是尾端事件，不是常態。

---

## 7. Research A-5：哪個殘差適合 1Y 走勢圖／percentile／Δ4w

【自行推論】三種呈現形式對被呈現的量有不同的硬性要求：

| 呈現形式 | 對量的要求 | 誰過關 |
|---|---|---|
| **1Y 走勢圖** | 一年份、密度夠、**同一個定義**的觀測 | 只有固定座標的量（B）。任何綁定合約的量在 D > L−12 時沒有一年（§9） |
| **percentile** | 母體是**可比**的同一個量；rank 統計量本身抗離群 | 同上。殘差如果連續一年可得也過關，但前提同上 |
| **Δ4w** | 同上，且**兩端點都要在網格內**、量的噪音要小於 4 週的真實變化 | §4.5 實測：殘差的日噪音（≈ 半寬 0.8 vol 點的隨機取樣）與殘差本身（0.16 點）同級甚至更大→**殘差不適合做 Δ4w** |

**結論**：三種形式全部只能掛在**固定座標的 IV／skew 序列**上。
把它們掛在 fair-value 殘差上，在本產品的 tenor 上是資料不可得
（§9），在短 tenor 上是訊噪比不足（§4.5）。

---

## 8. Research A-6：八個維度逐項評估（含決定性引擎實算）

### 8.1 座標漂移免疫性——A 家族唯一真正的技術優勢（引擎實算）

這是本文對 A 家族最有利的一項發現，先講清楚再講它為什麼救不了 A。

【自行推論，腳本 `exp1_rolldown.py`，§15.3】。用真實 fixture 校準一個
標準的 sticky-log-moneyness／1/√T skew 衰減曲面：

```
σ(K,T) = atm + β·k/√T ,  k = ln(K/F) ,  F = S·e^{(r−q)T}
```

以 TLT 真實兩點（K=85 iv=0.12、K=130 iv=0.18，DTE 882，S=84.52，
r=0.04）反解得 `atm = 0.1328`、`β = 0.2195`。**然後把環境完全凍結**
（atm、β、spot、r 全不動），只讓同一張合約／同一組 spread 的 DTE 從
882 掉到 252：

| DTE | 買腿 IV% | 賣腿 IV% | raw gap（點） | Ĝ = gap/atm | 殘差（fair 模型正確） | 殘差（fair 的 β 偏 +20%） |
|---:|---:|---:|---:|---:|---:|---:|
| 882 | 12.00 | 18.00 | 6.00 | 0.452 | +0.500 | +0.757 |
| 525 | 12.34 | 20.11 | 7.78 | 0.585 | +0.500 | +0.690 |
| 252 | 12.70 | 23.93 | **11.22** | **0.845** | **+0.500** | +0.616 |

**環境零變化下的漂移**：

- raw 買腿 IV：+0.70 點（+5.9%）
- raw 賣腿 IV：+5.93 點（+32.9%）
- **raw gap：+6.00 → +11.22 點（+87.1%）**
- **Ĝ = gap/ATM：+0.452 → +0.845（+87.1%）——除以 ATM 完全沒有移除
  roll-down**（因為 roll-down 是 tenor 的函數，不是 level 的函數）
- **殘差（fair 模型形狀正確）：完全不動，drift = 0.0000 點**
- 殘差（fair 的 skew 係數偏 20%）：−0.141 點，**比 raw gap 的漂移小
  37 倍**

【自行推論】**這一組數字同時做到三件事**：

1. **獨立重現了本 repo 前輪的關鍵主張**（`candidate-iv-relative-value.md`
   §2 稱 DTE 882→252、gap 6.0→11.2 點）。本文的模型是自己建的、
   校準自真實 fixture，數字對上，代表那條主張站得住。
2. **證明「固定合約的 raw gap percentile 不成立」**——因為它有 87% 的
   純機械漂移。這一條與既有實作的裁示一致，但理由是本文自己算的。
3. **證明殘差對座標漂移免疫**——因為市場 IV 與 fair IV **在同一個
   `(K,T)` 上取值**（§3.1），roll-down 在分子分母同時發生、相減時
   共模抵銷。**這是 A 家族相對 B 家族唯一真正的結構性優勢**：
   B 必須靠「固定座標」來人為凍結漂移，A 天生就不受漂移影響。

**但這個優勢在本產品上用不到**：B 因為固定 tenor，本來就沒有漂移可以
被免疫（漂移在 B 的定義裡不存在）。A 的優勢只有在「你堅持要跟著合約
走」時才值錢，而 §9 說明那條路走不通。

### 8.2 八維度總表

【自行推論；「資料成本」欄的 vendor 敘述為【二手轉述】】

| 維度 | A：同合約 fair-value 殘差歷史 | B：fixed (tenor, delta) 歷史位置 | C：hybrid（今日殘差 + B 的歷史） |
|---|---|---|---|
| **穩定性** | 殘差本身極穩（§8.1，correct-model drift = 0）；但 fair 模型的歷史窗選擇會翻號（§3.4） | 穩；rank 統計量抗離群 | 各取所長 |
| **DTE decay** | 天生免疫（同座標相減） | 靠固定 tenor 凍結，等效 | 兩者都處理掉 |
| **moneyness drift** | 天生免疫 | 靠固定 delta 凍結；**但 delta convention 必須一致**（§12.3 風險） | 同 B |
| **delta drift** | 天生免疫 | 同上 | 同 B |
| **bid-ask 噪音** | **差**：殘差 0.16–0.20 點 vs 半寬 0.80 點（§4.5）→ 訊噪比 0.2× | **好**：percentile 是 rank 統計量，單日爛報價改變不了名次；本 repo 已把 Δ4w 基準改成窗內中位數 | 殘差只當非頭條，B 當頭條 |
| **LEAPS 適用性（本產品核心）** | **不可行**：D=882 天需要 L ≥ 41 個月 > 39 個月法規上限（§9.4） | **可行但有天花板**：需要 L ≳ D，且要 bracket；超過天花板要誠實留白 | 可行 |
| **資料成本** | 需要**歷史單合約報價序列**（Market Data App / ORATS / Alpha Vantage，皆需金鑰，#111 未解）＋ RNHD 需標的多年日線 | 需要**歷史鏈曲面**（同樣需金鑰）；已出貨路徑就是這條 | ＝B 的成本 ＋ 今日鏈（免費，已有） |
| **實作複雜度** | 最高：每個歷史日一份 RNHD ＋ 全鏈定價 ＋ entropy 解 | 中：雙軸線性插值，已出貨 | 中＋（多一個今日的 smile fit） |

---

## 9. Research B：掛牌規則與同合約歷史的實際可得性（做實證，不假設）

委託明文要求：**不要假設 LEAPS 沒有一年歷史，用掛牌規則與資料把它
證明成或證偽。**

### 9.1 掛牌規則（本節全部是【二手轉述】——所有官方頁面皆不可達）

實測不可達：`cdn.cboe.com`、`www.cboe.com`、`ww2.cboe.com`、
`www.sec.gov`、`www.govinfo.gov`、`www.federalregister.gov`、
`www.optionseducation.org`（OCC）、`www.theocc.com`。以下全部來自
搜尋索引摘要。

1. **January LEAPS 的新增時點**：Cboe／C2／BZX／EDGX 在**九月標準到期
   週的第一個營業日**掛出新的 January LEAP series。兩個有日期的實例：
   **2021 年 1 月系列於 2018-09-17 掛出**；**2022 年 1 月系列於
   2019-09-16 掛出**。→ **前置期約 28 個月**。【二手轉述】
2. **同時只有兩檔 January 系列存活**：「Currently, equity LEAPS have two
   series at any time with January expirations. For example, in November
   2014, investors would see January 2016 and January 2017 LEAPS
   listed.」【二手轉述】（2014-11 的最長 ＝ Jan 2017 ＝ 26 個月，與
   28 個月前置期相容。）
3. **法規上限 39 個月**：Cboe Rule 4.5／5.8 一脈，「the longest term for
   an option series expiration is thirty-nine months from the listing
   date」，且 equity LEAPS「expiration months may be up to 39 months from
   the date of initial listing, with January expiration only」。
   【二手轉述】
4. **ETF 例外**：「SPY, QQQ, and IWM often have March, June, September,
   and December LEAPS in addition to January」，且非-January 長天期
   系列「varies by exchange and tends to favor the most actively traded
   names」。【二手轉述】

⚠ 第 3 點與第 4 點在措辭上互相衝突（「January expiration only」
vs「December LEAPS 存在」）。這正是本文唯一殘留 blocker 的來源
（§14.1）。

### 9.2 真實全鏈實證：階梯長什麼樣（【自行推論】，真實資料）

用 §4.5 的同一份真實 Cboe 全鏈（YETI，2023-08-11，758 筆）把整個
到期日階梯攤開：

| 到期日 | DTE | 月 | 合約數 |
|---|---:|---:|---:|
| 2023-08-11 | 0 | 0.0 | 82 |
| 2023-08-18 | 7 | 0.2 | 94 |
| 2023-08-25 | 14 | 0.5 | 84 |
| 2023-09-01 | 21 | 0.7 | 56 |
| 2023-09-08 | 28 | 0.9 | 56 |
| 2023-09-15 | 35 | 1.1 | 32 |
| 2023-09-22 | 42 | 1.4 | 56 |
| 2023-09-29 | 49 | 1.6 | 56 |
| 2023-11-17 | 98 | 3.2 | 36 |
| 2024-01-19 | 161 | 5.3 | 94 |
| 2024-02-16 | 189 | 6.2 | 34 |
| 2024-06-21 | 315 | 10.3 | 36 |
| **2025-01-17** | **525** | **17.2** | 42 |

**這是本文最乾淨的一項實證**【自行推論】：

- 最長掛牌到期日 ＝ **17.2 個月**，發生在 **2023 年 8 月**，也就是
  **九月新增前一個月**。
- 兩檔 January 系列 ＝ 2024-01-19（161 天）與 2025-01-17（525 天），
  與 §9.1 第 2 點完全吻合。
- **推得**：最長掛牌 tenor 是一條鋸齒——每年九月重設到 ≈28 個月，
  隔年八月衰減到 ≈16–17 個月。**這條鋸齒就是天花板。**

### 9.3 TLT 的例外：本 repo 自己的真實 fixture 打破 28 個月

【自行推論，repo 實證】本 repo `tests/fixtures/
tlt_leaps_real_quotes_2026-07-17.json` 的 provenance 寫明是
**2026-07-17 當下 TLT 的真實 2028-12-15 到期 LEAPS call 報價**
（逐位元抄自 repo 已提交的 `tlt_report.md`，該檔由較早版本 CLI 對真實
快照跑出）。

`2028-12-15 − 2026-07-17 = 882 天 = 29.0 個月`，而且是**十二月**到期。

兩個推論：

1. TLT 屬於 §9.1 第 4 點的「額外季度長天期系列」那一群 ETF——
   它有 December 長天期系列，不是 January-only。
2. **TLT 的實際掛牌前置期 L ≥ 29 個月**（因為這張合約在 29 個月時
   已經在報價）。上界仍是 39 個月的法規上限。

### 9.4 決定性推導：A 與 B 的可得性條件不對稱

【自行推論】設：
- `L` ＝ 該類合約的最長掛牌前置期（月）
- `D` ＝ 今天這個候選的 tenor（月）
- `T` ＝ 想畫的歷史窗長度（月），本產品 T = 12

**A（同一張合約的歷史）**：T 個月前，這張合約的 DTE 是 `D + T`。它
那時必須已經掛牌，所以

> **A 可行 ⟺ L ≥ D + T**

**B（固定 tenor D 的重錨定）**：T 個月前那一天，只要當天的鏈上有
tenor ≥ D 的合約（且下方有一檔可以 bracket）就行。當天的最長掛牌
tenor 是那條鋸齒 `M(t) ∈ [L − cycle, L]`，**與 T 無關**：

> **B 可行 ⟺ D ≲ M(t)，逐日判斷；與歷史窗長度 T 無關**

**這就是全文的樞紐。** A 的條件比 B 嚴格整整一個歷史窗。

代入數字：

| 前置期 L | A 需要 D ≤ | 換算天數 | 本產品 1.5–3 年核心情境（18–36 個月）過關嗎 |
|---|---|---|---|
| 28 個月（January equity/ETF 實務） | 16 個月 | 487 天 | **全部不過** |
| 29 個月（TLT 實測下界） | 17 個月 | 517 天 | **全部不過** |
| **39 個月（法規上限）** | **27 個月** | **822 天** | 18–27 個月過、**28–36 個月不過** |

**對 repo 真實案例 D = 882 天 = 29.0 個月**：A 需要
`L ≥ 29 + 12 = 41 個月`，**超過 39 個月的法規上限**。

> 【自行推論】**在 listed option 的規則之下，一張 tenor 882 天的合約
> 不可能有一年的自身報價歷史。這與 vendor、與付費、與資料工程無關，
> 是掛牌規則的算術後果。** 唯一能推翻它的，是「39 個月上限」這條
> 【二手轉述】是錯的（§14.1）。

**B 在同一情境下的覆蓋率**（鋸齒模型，`cycle` ＝ 新系列間隔）：

- January-only（cycle = 12 個月，L = 28）：D = 18 個月 → 83% 的日子
  可 bracket；D = 24 → 33%；**D ≥ 28 → 0%**。
- ETF 季度長天期（cycle = 3 個月，L ≈ 30–32）：D = 29 個月 →
  大約 `(L − 29)/3`，L=32 時 **100%**、L=30 時 33%。

【自行推論】所以 **B 在 LEAPS 上「可行但貼著天花板」**，A 在同一
tenor 上**結構性不可行**。這也解釋了本 repo 既有的 #134 症狀
（「連線成功但無資料」）：`ivhistory.iv_at()` 的
`if tenor_days < tenors[0] or tenor_days > tenors[-1]: return None`
【repo 原始碼實證】就是這條天花板在程式裡的具體表現，**它是對的，
不是 bug**。

### 9.5 Market Data App 單合約端點（委託 B-3；【二手轉述】，未實測）

**本沙箱無法抓取 https://docs.marketdata.app/**（DNS 不解析，
`www.marketdata.app` CONNECT 403）。因此本節只能給兩級證據：

**（a）本 repo 既有紀錄**（`docs/research/historical-options-iv-data-sources.md`
§4.7，該文自述為索引轉述）：
- `/v1/options/quotes/{optionSymbol}/` 支援 `from`／`to`，**單一呼叫
  回整段日序列**；每列含 bid/ask/mid/last/IV/Greeks/OI/volume。
- 產品頁稱 EOD 歷史自 **2010** 起（另一處文件寫 2005，**兩處互相
  矛盾，該文已標記**）。
- 免費層 100 credits/日；付費約 US$12–30/月級（轉述）。
- **credit 扣法未經實測確認**。

**（b）本 repo 程式碼實證**（`option_chaser/data/marketdata.py`，
【repo 原始碼實證】——這是關於**本 repo 相信 vendor 長什麼樣**的證據，
不是關於 vendor 的證據）：
- 實際實作的歷史端點是 **chain** 而非 quotes：
  `_HISTORICAL_CHAIN_URL = _BASE + "/options/chain/{symbol}/?date={date}"`，
  可加 `&expiration=`。
- **repo 從未實作 `/v1/options/quotes/` 單合約端點**——也就是說，
  A 路線在本 repo 連 adapter 都還不存在。
- `fetch_surface()` 解析出的每一列只取 `side`／`delta`／`iv`／`dte`
  三個欄位（`_parse_surface_rows`）——**曲面路徑不取 bid/ask**。

**（c）#111 現況**：Market Data App／Alpha Vantage／ORATS 三家皆
credential-blocked，**至今沒有任何一次成功的真實資料呼叫**
（本 repo 既有紀錄，issue #111 維持 OPEN）。

【自行推論】對委託問題 B-3 的正式回答：**「單一呼叫能不能回整段歷史」
這件事目前只有轉述級證據，且與 repo 已實作的端點不是同一支。**
但這一題的權重其實很低——**因為 §9.4 已經證明，就算這支端點完美
運作、就算你付錢，它在 882 天 tenor 上也沒有一年的資料可以回給你。**

### 9.6 就算拿得到，同合約序列有沒有意義（委託 B-5，刻意與可得性分開）

【自行推論】**有意義，但意義跟大家以為的不一樣。**

- **對 raw IV／raw gap：沒有意義。** §8.1 引擎實算：環境完全不變時，
  同合約 gap 從 6.00 漂到 11.22 點（+87%）。這 87% 全是 DTE decay
  造成的，一點資訊都沒有。
- **對 fair-value 殘差：有意義，而且是所有方法裡最好的。** §8.1 同一組
  計算：正確設定的 fair 模型下殘差 drift 為 **0.0000**，fair 模型 skew
  係數偏 20% 時也只 drift 0.141 點。**殘差把 DTE decay 與 moneyness
  drift 一起消掉，因為市場與公平在同一個 `(K,T)` 上相減。**
- **對「這張合約的 debit 走勢」：有意義但已被否決。** 本 repo 既有
  V9 `SpreadHistory` 就在畫它；`spread-price-percentile-vs-vol-space.md`
  已證 price 空間被利率／股息汙染（TLT LEAPS 利率 2pp → 理論價 +26%），
  不適合做 percentile。

所以委託 B-5 的答案是：**同合約序列的「有沒有意義」完全取決於序列上
放的是什麼量。放殘差有意義、放 raw IV 沒有意義。**——而放殘差那條路
被 §9.4 的可得性堵死。**兩個問題各自的答案是「有意義」與「拿不到」，
不能互相取代，也不能合併成一句「同合約不行」。**

---

## 10. 三選項正面比較

【自行推論】

| | **A：同合約 fair-value 殘差歷史** | **B：fixed (tenor, delta) 歷史位置** | **C：hybrid** |
|---|---|---|---|
| 回答的是 §2 的哪一題 | Q3（我的 edge 相對過去的 edge） | Q2（水位／結構的歷史位置） | Q1（今日殘差）＋ Q2（B 的歷史） |
| 直接回答需求方那句話嗎 | **殘差本身直接回答 Q1**；殘差的**歷史**不回答 | **不回答**——它回答的是另一題 | **是**：Q1 由殘差答、「歷史」由 B 提供脈絡 |
| 座標漂移 | 天生免疫（§8.1，drift = 0） | 靠固定座標凍結（等效） | 兩者都乾淨 |
| LEAPS 可得性 | **D=882 天時結構性不可能**（§9.4，需 L≥41 > 39 個月上限） | 可行但貼天花板（需 L ≳ D，逐日 bracket） | ＝ B |
| 訊噪比 | 差（殘差 0.16–0.20 vs 半寬 0.80 vol 點，§4.5） | 好（rank 統計量） | 殘差不當頭條即可 |
| 業界先例 | **查無**具名成熟實務（§4.3） | **OptionMetrics 標準化曲面**（10–730 天 × delta 0.10–0.90）（§4.4） | 等於把 SAS 的橫斷面用途（§3.3）與 surface 歷史各自放回原位 |
| 新增 vendor 依賴 | 單合約歷史報價（#111 未解） | 歷史鏈曲面（#111 未解，但已出貨路徑） | ＝ B |
| 致命弱點 | 可得性（結構性）＋ 歷史窗選擇會翻號（§3.4 一手警語） | **它不是估值**；使用者會誤以為它回答了 Q1 | 需要嚴格的標籤紀律，兩塊不能混講 |

---

## 11. 裁決細節（逐條回答委託指定的每一個問題）

### 11.1 哪一個最直接回答「這張現在貴不貴」

**A 家族的殘差本身。** 但必須把「殘差」與「殘差的歷史」切開：

- **殘差本身 = SAS(K,T) = Σ_market(K,T) − Σ_H(K,T)**，是 Q1 的定義級
  答案【一手原文，§3.1】，**不需要這張合約的任何報價歷史**。
- **殘差的歷史**（＝選項 A 字面所指）回答的是 Q3，且在本產品 tenor
  上不存在（§9.4）。

**B 明確不回答這個問題。** 買腿 IV percentile 是 SAS 論文第 1 頁點名
的「options speculators 的指標」【一手原文】——它回答「水位在哪」，
不回答「價格對不對」。**這一點必須向需求方講清楚：已出貨的
Historical IV 卡片，無論再加多少功能，都不會變成 Q1 的答案。**

### 11.2 canonical 歷史量到底該是什麼

> **每一個歷史交易日，在該候選今天的 `(tenor D, |delta|)` 座標上，
> 對當日鏈的雙軸線性插值取得的 IV；出界一律留白不外插。**

三條獨立理由（都不是「已經做了」）：

1. **可得性算術**：`L ≳ D`（B）vs `L ≥ D + T`（A）。整整差一個歷史窗
   （§9.4）。
2. **業界資料標準**：OptionMetrics IvyDB 的標準化曲面就是這個座標系，
   tenor 10–730 天、delta 0.10–0.90【二手轉述，§4.4】。這個先例
   完全獨立於本專案。
3. **漂移**：固定座標把 DTE decay／moneyness drift／delta drift 一次
   全部凍結。§8.1 實算顯示不凍結的代價是 87% 的假訊號。

### 11.3 Call 與 Vertical Spread 分別怎麼定義

**Long Call（level 語言）**
- 主量：`IV(D, |Δ_buy|)`
- 輔量：`IV(D, 0.50)`（ATM），用來讓讀者分辨「是整體 vol 高，還是這一點
  高」

**Vertical Spread（skew 語言，且必須兩軸並陳）**
- 主量之一（**水位**）：`IV(D, |Δ_buy|)` 與 `IV(D, |Δ_sell|)` **各自
  一條完整序列**
- 主量之二（**形狀**）：`Ĝ = (IV(D,|Δ_sell|) − IV(D,|Δ_buy|)) / IV(D,0.50)`
- **禁止**：任何單一「Spread IV」。§6.1 引擎實算給出獨立於既有裁示的
  否決理由（σ_net = −0.74 vol 點；1% vega 擾動跳 0.41 點）；SAS 腳註 3
  給出一手理由。

⚠ **對既有實作的一個實質異議**：把 Ĝ 當成 Spread 模式的**唯一**頭條
是有風險的。SAS_ATM 之所以把 level 歸零，是因為 GS 判斷歷史分佈**推不出
level 的公平值**【一手原文，§3.2】——但那不代表 level 不重要，只代表
它不該被拿去跟歷史比公平。**使用者付的錢裡，level 那一塊是實打實的。**
本 repo 既有實作把兩腿 IV 放在次層，方向是對的；本文的建議是
**兩腿 IV 的 percentile 與 Ĝ 的 percentile 必須等權呈現**，因為
「skew 好看但 vol level 高、debit 仍然貴」是真實情境（需求方顧問在
spec #137 Gate 1 已指出，本文獨立同意）。

### 11.4 percentile 與 Δ4w 掛在哪個量上

**掛在 §11.3 列出的那些重錨定序列上，一個都不掛在 fair-value 殘差上。**

理由（§7）：殘差在本產品 tenor 上沒有一年的歷史；就算在短 tenor 上有，
它的日噪音（買賣價差半寬 0.8 vol 點的隨機取樣）與它自己的量級
（0.16 vol 點）同級——**Δ4w 會在量自己的噪音**。

### 11.5 既有 fixed-(tenor, delta) 機器：必要 vs 不該當訊號

見 §12（獨立成節，因為這是委託明文指定要交付的清單）。

### 11.6 `IV − realized vol` 算不算 fair-value 殘差

**不算，明確否決。** 完整理由見 §5.3（三條，兩條有一手背書）。
它實際量的是 **variance risk premium**——賣方提供 vol 保險所要求的
補償。一個持續為正的保險費不是錯價。

**它可以留在哪裡**：方法論尾註或次層的成本揭露（「你付的 IV 比這個
標的過去的實際波動高 X 點」），措辭必須是事實敘述，**不得**掛
「合理價值」「偏貴」「edge」等字眼。

### 11.7 證據夠不夠下這個裁決

**夠，但有一條明確的依賴。** 核心情境（D = 882 天）的裁決只依賴
**「39 個月是 listed equity/ETF option 的掛牌上限」**這一條
【二手轉述】。若它成立，A 在核心情境上不可能，裁決成立。
若它不成立（例如某些 ETF 的長天期系列可以掛到 45 個月以上），
**18–29 個月那一段的比較必須重開**。這就是 §14.1 的單一 blocker。

---

## 12. 對既有 fixed-(tenor, delta) 機器的逐件分類

委託明文指定的交付項。【自行推論，逐條對照 `option_chaser/ivhistory.py`
與 `api_app/main.py` 原始碼】

### 12.1 **必要的 normalization**（保留，且每一條都有獨立先例）

1. **固定 tenor（constant maturity）**——移除 DTE decay。
   先例：OptionMetrics 標準化曲面的 11 個固定 tenor【二手轉述】；
   §8.1 實算給出不做的代價（賣腿 IV 假漂 +32.9%）。
2. **固定 delta（constant delta）**——移除 moneyness／delta drift。
   先例：OptionMetrics 的 17 個 delta 格；FX 圈 25Δ RR/BF 慣例
   （本 repo 既有研究已建立）。
3. **不外插（`iv_at` 出界回 `None`）**——這是**誠實**，不是保守。
   OptionMetrics 的 delta 軸同樣只到 0.10／0.90【二手轉述】。
   §9.4 進一步說明：出界不是資料缺陷，是掛牌天花板的必然表現。
4. **skew ÷ ATM（`Ĝ`）**——讓 skew 在不同 vol regime 下可比。
   先例：SAS_ATM 的同構分層（level 交給 ATM 校準、殘差專量 skew）
   【一手原文，§3.2】。
   ⚠ **但要注意它做不到什麼**：§8.1 實算顯示 ÷ATM **不移除 roll-down**
   （Ĝ 與 raw gap 同樣漂 +87.1%）。在固定 tenor 下這不成問題，但如果
   將來有人把 Ĝ 拿去跟合約自己的歷史比，這個保護不存在。
5. **percentile 用 rank 統計量、含等於**——rank 本質抗離群，單日一筆
   爛報價改變不了名次。本 repo 已把 Δ4w 的基準改成 [21,42] 天窗內
   中位數（spec #137 Gate 2），方向正確。

### 12.2 **不該被當成訊號的部分**

1. **買腿 IV percentile 被當成「貴不貴」的答案**。它是 Q2 不是 Q1
   （§2、§5.2）。SAS 論文第 1 頁的原話就是「options speculators 的
   指標」【一手原文】。**在一個系統性偏貴的市場裡，第 20 百分位仍然
   是貴的。**
2. **Ĝ 的絕對值跨候選比較**。Ĝ 的大小取決於 `(Δ_buy, Δ_sell)` 這一對
   座標，而那一對是**候選產生器選的**，不是市場給的。兩個履約價不同
   的候選，Ĝ 不可比。**Ĝ 只在同一個候選的自身歷史上有意義。**
3. **Δ4w 被讀成方向**。它是「已經發生的事」的描述。本 repo 第六輪
   研究已經以一手證據（Harvey–Whaley 1992、Simon–Campasano 2012）
   排除預測用途，本文無異議、不重推。
4. **觀測筆數少於約 10 筆時的 percentile**。此時 percentile 是在
   數 sampling schedule（`crc32(symbol:week)` 選出的那幾天）的名次，
   不是在數市場。**尤其在貼近掛牌天花板的 tenor 上，能 bracket 的
   日子本來就只有 §9.4 表格裡那個百分比**——畫面應該直說「這個 tenor
   只有 N 天有可比網格」，而不是給一個看起來跟其他候選一樣可信的
   percentile。
5. **貼著網格邊界的 ATM 內插**。`iv_at(..., delta=0.50)` 在長天期鏈上
   常常只有很少的 strike 能 bracket；此時 `Ĝ` 的分母是一個由兩三點
   撐起來的插值。分母不穩，Ĝ 的 percentile 就不穩。

### 12.3 ⚠ 新發現：delta convention 可能不一致（**可驗證的風險，非已確認的 bug**）

【自行推論，引擎實算 ＋ repo 原始碼實證】

- **座標那一側**：`ivhistory.leg_coordinate()` 用
  `valuation.call_greeks(..., q)`，而 `spread_coordinates()` 的
  docstring 明寫「**股利殖利率沿用 q=0**：這是 #122 既有紅線」。
  → 座標 delta 是 **q=0** 的 delta。
- **網格那一側**：`marketdata._parse_surface_rows()` 直接取 vendor
  回傳的 `row["delta"]`。**vendor 的 delta 用什麼 q，本 repo 從未
  驗證過**（#111 credential-blocked）。

若 vendor 的 delta 帶股利（多數專業 vendor 會），量級如下（同一張
真實 TLT LEAPS，K=85、iv=0.12、DTE 882、S=84.52、r=0.04）：

| | q = 0（引擎座標） | q = 4.5%（#110 研究對這份快照的最佳擬合） |
|---|---|---|
| delta | **0.7194** | **0.4478** |

以 §8.1 校準的真實 TLT smile 反查：在一張帶 q=4.5% 的網格上，
`|delta| = 0.7194` 這個座標對應的是 **K = 74.03**，而使用者實際要買的
是 **K = 85.00**。

> **strike 偏 −12.9%，IV 系統性偏 −1.95 vol 點。**

【自行推論】後果不是「數字錯一點」，而是**整條歷史序列量的是 smile
上另一個點**——它仍然是一條內部一致的序列（每天都用同一個錯的座標），
所以 percentile 不會爆掉，**但它不是這個候選的序列**。

**這件事只需要一個實驗就能結案**：拿到 Market Data App 金鑰後，
對同一張合約比對「vendor 回的 delta」與「引擎 q=0 算的 delta」。
差在小數第三位＝無事；差 0.2 以上＝確認。**在驗證之前不得宣稱是
bug，也不得宣稱沒事。**

---

## 13. 明確否決清單（每條附理由與證據等級）

1. **任何單一「Spread IV」／net volatility 當頭條**——§6.1 引擎實算
   （σ_net = −0.74 vol 點；1% vega 擾動跳 0.41 點；換 q 從 −0.74 變
   8.72）【自行推論】＋ SAS 腳註 3【一手原文】。
2. **`IV − realized vol` 當 fair-value 殘差**——§5.3【一手原文 ×2 ＋
   二手轉述】。
3. **同合約 raw IV／raw gap 的 percentile**——§8.1 實算：環境零變化下
   87% 的機械漂移【自行推論】。（與本 repo 既有裁示一致，但理由是
   本文獨立算的。）
4. **同合約 fair-value 殘差歷史（選項 A 的字面形式）當 canonical 歷史量**
   ——§9.4 可得性算術：D=882 天需要 L ≥ 41 個月 > 39 個月上限
   【自行推論 ＋ 二手轉述的上限值】。**否決理由是結構性的，不是
   「已經蓋了別的」。**
5. **RNHD／完整 SAS 全套自建當頭條**——三難（§5.4）：可信的那一半太小
   （0.16–0.20 vol 點 vs 0.80 半寬）、夠大的那一半 GS 自己說不可信、
   兩半都不能在 LEAPS tenor 上歷史化【一手原文 ＋ 自行推論】。
   額外風險：歷史窗選擇會讓結論**翻號**【一手原文，§3.4】，與
   facts-only 紅線衝突。
6. **smooth-fit residual（`theo`／SMV 式）掛「合理價值」的名字**——
   參照系是市場自己，整條鏈一起貴時恆為零（§4.2）【自行推論，依據為
   vendor 自述的目標函數文字】。它可以留，但只能叫「相對同鏈其他合約
   的偏離」。
7. **把 fair-value 殘差掛 Δ4w**——§7：殘差自身量級與日噪音同級，
   Δ4w 會在量噪音【自行推論】。
8. **用「39 個月上限」以外的樂觀假設推 A 的可行性**——在 §14.1 的
   blocker 解掉之前，任何「也許 LEAPS 有更長前置期」的假設都不得
   進入設計。

---

## 14. 未能查證事項與限制

### 14.1 **唯一殘留 blocker（委託要求具體寫出）**

> **需要的確切事實**：TLT 這一類（有季度長天期系列的高流動性 ETF）
> 在某一個特定日期上，**完整的到期日清單與其中最長的 tenor**。
>
> **從哪個確切來源**：任一可取得完整 expiration 清單的來源即可——
> (a) Market Data App `/v1/options/expirations/TLT/`（本 repo
> `marketdata.py` 已經有 `_EXPIRATIONS_URL` 常數，只差金鑰）；
> (b) `https://cdn.cboe.com/api/global/delayed_quotes/options/TLT.json`
> 的全鏈（本沙箱 403，需求方本機或 production 可取）；
> (c) 任一券商的 TLT 選擇權到期日下拉選單截圖。
>
> **它會定案什麼**：把 §9.4 表格裡的 `L` 從區間 `[29, 39]` 收成一個
> 數字。
> - 若 `L ≤ 39`：本文裁決全部成立，A 在 ≥ 28 個月 tenor 上永遠不可行。
> - 若 `L ≥ 41`（意即目前查到的 39 個月上限是錯的或有例外）：
>   **18–29 個月那一段的 A vs B 比較必須重開**，因為 A 的座標漂移
>   免疫性（§8.1，drift = 0 vs 87%）是真實優勢，只要可得性解除就值得
>   重新評估。

**這個 blocker 不阻擋 §11 的裁決在 882 天核心情境上成立**，只影響
中段 tenor 的邊界。

### 14.2 其他限制（逐條）

1. **本文沒有任何【官方文件】等級的證據**。所有交易所／OCC／vendor
   官方頁面在本沙箱皆不可達（§1 列出實測清單）。掛牌規則整節
   （§9.1）是【二手轉述】。
2. **SAS PDF 取自第三方 GitHub 鏡像**
   （`colejhudson/goldman-sachs-quantitative-strategies-research-notes`），
   非 GS 原站。鏡像完整性未經第二來源比對；但檔案為 10 頁、含完整
   附錄 A–C 與參考文獻，內容自洽，且與本 repo 前兩輪獨立取得的引文
   逐字吻合。
3. **YETI 是單一股票、單一日期（2023-08-11）的快照**。§4.5 的
   訊噪比與 §9.2 的階梯都只代表這一個樣本。TLT（ETF、流動性更好、
   有季度長天期系列）的數字可能不同——**特別是 §9.2 的階梯，YETI
   是 January-only 的單一股票，不能直接套到 TLT**（§9.3 已用 repo
   自己的 fixture 證明 TLT 不同）。
4. **§8.1 的曲面模型是本文自建的參數化形式**（sticky log-moneyness ＋
   1/√T skew 衰減），只用真實 fixture 的兩個點校準。真實 TLT surface
   的 term structure 未必服從 1/√T。**這個實驗的價值在於「同座標相減
   會共模抵銷」這個結構性結論，那一條對任何確定性曲面形狀都成立；
   87% 這個具體數字則依賴模型形式。**
5. **§6 的 vega 用 `call_greeks`（歐式 BS ＋ 連續 q）**，不是 BS93
   美式近似。理由：本節比較的是**比值**（殘差 vs 摩擦），兩邊用同一
   個 vega，模型偏差共模抵銷。若要拿絕對美元數字去做決策，應改用
   `valuation.american_price`／`implied_vol` 路徑（#113 已接線）。
6. **q = 4.5% 這個值來自本 repo #110 研究的經驗最佳擬合**，
   **尚未被需求方核准鎖定**（#113 的 correctness 裁示仍未定）。
   §6.1 與 §12.3 同時列出 q=0 與 q=4.5% 兩組數字，就是因為這一點
   未定。
7. **§4.3「查無成熟具名實務」是檢索性結論**。我打不開任何一家 vendor
   的官方文件，只能從索引摘要判斷。查不到不等於不存在。
8. **Market Data App 的 wire format 至今未經真實回應驗證**（本 repo
   既有紀錄，#111）。§9.5 的所有欄位敘述都繼承這個不確定性。
9. **本文沒有實測任何歷史選擇權資料**。所有關於「歷史序列長什麼樣」
   的敘述都是從掛牌規則與今日快照推導的。

---

## 15. 重現步驟

### 15.1 SAS 全文取得

```bash
curl -sSL "https://raw.githubusercontent.com/colejhudson/goldman-sachs-quantitative-strategies-research-notes/master/Strike-Adjusted%20Spread_%20A%20New%20Metric%20For%20Estimating%20The%20Value%20Of%20Equity%20Options.pdf" -o sas.pdf
# 10 頁 PDF v1.2，204.3 KB
uv pip install --python .venv/bin/python pypdf
.venv/bin/python -c "
from pypdf import PdfReader
r=PdfReader('sas.pdf')
print(''.join(f'\n===PAGE {i}===\n'+(p.extract_text() or '') for i,p in enumerate(r.pages,1)))
"
```

本文引用的頁碼採**論文自己的頁碼**（PDF 第 5 頁 ＝ 論文 p.1）。

### 15.2 真實 Cboe 全鏈取得

```bash
curl -sSL "https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json" -o yeti.json
# timestamp 2023-08-11 16:27:37, spot 44.97, 758 contracts
```

### 15.3 四個分析腳本

全部放在 session scratchpad
`/tmp/claude-0/-home-user-option-chaser/a40b16e9-7300-4a2a-ba5e-5073ebdd01f0/scratchpad/`，
**未進 repo、未 commit**（研究票紅線）。執行方式：

```bash
PYTHONPATH=/home/user/option-chaser /home/user/option-chaser/.venv/bin/python <script>
```

| 腳本 | 產出的節 | 核心輸入 |
|---|---|---|
| `exp1_rolldown.py` | §8.1 座標漂移表 | TLT fixture 兩點校準 (atm=0.1328, β=0.2195)，DTE 882→252 |
| `exp2_noise.py` | §4.5 殘差 vs 噪音表 | `yeti.json`，OTM-only，vega≥0.01，vega 加權二次式 WLS |
| `exp3_listing.py` | §9.4 可得性表 | L ∈ {28, 29, 39} 個月的鋸齒模型 |
| `exp4_spread.py` | §6.1／§6.3 表 ＋ §12.3 delta 對照 | TLT fixture 兩腿真實 bid/ask/iv，`call_greeks`，q ∈ {0, 0.045} |

**單位陷阱（留給下一個人）**：Cboe payload 的 `vega` 是**每 1 vol 點**
的美元值（不是每 1.0 的 σ）；本 repo `valuation.Greeks.vega_per_pct`
同一慣例。`exp2_noise.py` 第一版把它當成每單位 σ，算出「買賣價差半寬
287 vol 點」這種明顯荒謬的數字才發現——**荒謬到一眼看得出來是幸運，
下一次可能不會**。

---

## 16. 參考資料

**【一手原文】**
- Zou, J. & Derman, E., *Strike-Adjusted Spread: A New Metric For
  Estimating The Value Of Equity Options*, Goldman Sachs Quantitative
  Strategies Research Notes, July 1999（10 頁全文，本輪逐頁重讀；
  鏡像來源見 §15.1）
- 本 repo 原始碼：`option_chaser/ivhistory.py`、
  `option_chaser/valuation.py`、`option_chaser/data/marketdata.py`、
  `api_app/main.py`（`iv_history` 端點）

**真實資料**
- `raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json`
  ——真實 Cboe delayed-quote 全鏈，2023-08-11，758 筆
- 本 repo `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`
  ——真實 TLT 2028-12-15 LEAPS call 報價 5 檔

**【二手轉述】（皆為搜尋索引摘要，原站在本沙箱不可達）**
- Cboe, *January LEAP Series Listing Schedule*（`cdn.cboe.com`，403）
- Cboe, *January 2022 LEAP Series on Cboe Options Exchanges*
  （`cdn.cboe.com`，403）
- Cboe Rule 4.5 / 5.8（`sec.gov`、`govinfo.gov`、`federalregister.gov`
  皆 403）
- OCC / optionseducation.org, *LEAPS® & Expiration Cycles*（403）
- OptionMetrics IvyDB standardized volatility surface 規格
  （`optionmetrics.com`，未實測）
- ORATS SMV / S% / D% / F%（`orats.com`、`docs.orats.io`，未實測）
- SpiderRock volatility surface / theoretical edge（`spiderrock.net`，
  未實測）
- IVolatility IVolLive（`ivolatility.com`，未實測）
- Cboe LiveVol DataShop 產品線（`datashop.cboe.com`，未實測）
- Market Data App `/v1/options/quotes/`（`docs.marketdata.app` DNS
  不解析、`www.marketdata.app` 403）
- Variance risk premium 定義（Carr–Wu 一脈；本輪未取得原文，
  本 repo 第六輪已有 Carr & Wu 2005 一手全文，本文未重複引用其內文）
- MBS OAS 歷史 percentile 為標準 relative-value 做法

**本 repo 既有研究（作為既有結論引用，未重推）**
- `candidate-iv-relative-value.md`（第三輪，SAS 一手深挖、四方案）
- `iv-relative-history-methodology.md`（第二輪，spread 單一 IV
  ill-defined 的引擎實證）
- `spread-price-percentile-vs-vol-space.md`（price 空間被利率汙染）
- `spread-surface-residual-rv.md`（smooth-fit 殘差定位為安靜保險絲）
- `rich-cheap-trend-entry-timing.md`（第六輪，Δ4w 與 facts-only 紅線）
- `historical-options-iv-data-sources.md`（vendor 比較、#111 現況）
- `valuation-carry-method-comparison.md`（#110，q ≈ 4.5% 經驗擬合）
