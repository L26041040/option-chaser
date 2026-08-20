# 指定 Candidate 的 IV 歷史相對位置——專業市場成熟方法深挖

研究日期：2026-08-08。本文是 `iv-relative-history-methodology.md`（2026-08-07，
下稱「上一輪」）的**深化，不是重寫**：上一輪已確立「同一 OCC 合約 1Y
percentile 不成立」（上一輪 §3.1）、「零售主流是標的層級 constant-maturity
ATM IV 指數」（§3.4）、「不能簡單平均兩腿 IV」（§5）、「spread 單一 IV
ill-defined」（§5.3）。需求方看完後把問題推進到：**不要標的整體 IV，要
「這一組具體 Buy/Sell legs 的 volatility 結構」相對歷史的位置**。本文以
上一輪 §3.3（同 DTE＋delta surface 取點）、§4.c（surface 殘差）、§4.e
（環境掛哪一層）為起點，逐項回答需求方的十個問題，收斂成四個可實作方案，
文末做 A／B／C 成熟度分類——**本文不施工、不替需求方拍板**。

**範圍界線**：不做 vendor 選型（平行研究
`historical-options-iv-data-sources.md` 已列交集候選 ORATS／Market Data
App／Alpha Vantage／EODHD，本文談資料只用抽象形狀＋對照該文）；不涵蓋
Long Call vs Spread 的 ROI 比較（需求方保留 Grill C）；不涵蓋跨劇本比較
（Grill D）；UI 只談到「card 上放哪些數字」的資訊架構層。

## 0. 產品層已確定約束（需求方已裁示，原樣照錄，本文所有方案皆遵守）

- IV card 綁 candidate / option combination，不綁整個 scenario
- scenario card 只顯示目前代表／最優 candidate 的精簡 IV card；完整 IV
  card 在詳細分析區
- 只呈現事實性數字與圖（IV、percentile、歷史走勢、gap、skew 等），
  **不要**「偏高／便宜／有利」這類主觀標籤
- 最終整合成**單一 candidate IV card**，不拆成多個獨立 UI 區塊
- **不創造沒有嚴謹定義的「Spread IV」**（上一輪 §5.3 已證 ill-defined）
- IV 指標只作資訊層，不改 ranking / filter / candidate selection
- 不自存 option chain；歷史資料優先按需 vendor API

## 1. 取材限制聲明（本輪與前幾輪不同：取得三份一手 PDF）

本輪逐一實測 WebFetch 可達性，結果與前幾輪同型但有一個重要例外：

- **一般外部網域一律 `EGRESS_BLOCKED`**。本輪實測遭拒：`arxiv.org`、
  `papers.ssrn.com`、`emanuelderman.com`、`web.archive.org`、
  `www.mathfinance.com`、`physikinvest.com`、`pdfs.semanticscholar.org`、
  `acfr.aut.ac.nz`、`www.ivolatility.com`、`www.trading-volatility.com`、
  `notion.moontowermeta.com`、`github.com`（HTML 403）。
- **`raw.githubusercontent.com` 可達**（沿用前幾輪的唯一通道），而本題的
  關鍵一手文獻恰好有公開 GitHub 鏡像。本輪因此**逐字檢視了三份一手文件**：
  1. **Zou & Derman, “Strike-Adjusted Spread: A New Metric For Estimating
     The Value Of Equity Options”, Goldman Sachs QS Research Notes, July
     1999**——全文 10 頁 PDF（含附錄 A–C 與參考文獻），取自
     `colejhudson/goldman-sachs-quantitative-strategies-research-notes`
     鏡像；
  2. **Natenberg,《Option Volatility and Pricing》1994 年版**——第 10 章
     Bull and Bear Spreads（pp. 204–209）與第 18 章 Volatility Skews
     （pp. 409–415）掃描頁，取自 `hemraj4684/Imp-Books` 鏡像；
  3. **Gatheral,《The Volatility Surface: A Practitioner's Guide》(Wiley
     2006)**——第 3 章 SVI 參數化一節文字層，取自
     `PlamenStilyianov/Quant` 鏡像。
- 聲明分級沿用 `option-strategy-report-conventions.md` §7 的標記體系，
  本輪新增一級：**〔一手・逐字〕**（PDF 原文逐字檢視）＞
  **〔官方・索引轉述〕**＞**〔二手・索引轉述〕**；自行推導與引擎實算
  一律標明可重現步驟。鏡像完整性風險（第三方 repo 而非發行方原站）
  列入 §15 第 1 項。
- **§4 的混淆量化與 §11 的 TLT 實算全部是自行推導＋本 repo
  `option_chaser/valuation.py` 引擎實算**（stdlib、可重現），不依賴任何
  外部轉述。

## 2. 結論摘要（十問十答）

1. **專業 desk 判讀指定 vertical spread 的 vol relative value，用的是
   「三層拆解」而不是單一數字**：(a) 標的層級 vol level（上一輪 §3.4 的
   IVR 家族）；(b) 兩腿之間的 skew／slope（以 delta 或 log-moneyness 為
   座標的兩點差，normalized 後看歷史位置）；(c) 逐腿相對今天整條 surface
   的殘差（rich/cheap edge）。Natenberg 的 desk 教科書把 vertical spread
   選型明文歸結為「IV 太低就買 ATM 腿、IV 太高就賣 ATM 腿」（vega 集中
   規則），Sinclair 把 vertical spread 直接描述為「賣掉 vol 曲線上最貴的
   一段」——**spread 在專業語言裡本來就是 level＋skew 的複合體，沒有人
   給它單一 IV**（§3）。
2. **Sell-leg IV − Buy-leg IV 的固定合約歷史 percentile：比上一輪 §3.1
   的單合約 percentile 好一截，但仍不能直接當核心指標。**同 expiry 讓
   term-structure 的**平行**滑動在相減時共模抵銷（這是它比單腿序列強的
   真實原因），但 skew 斜率本身隨 DTE 縮短而變陡（≈1/√T），固定 strike
   對的 gap 會**單純因時間流逝而機械性放大**（本文引擎外推：DTE 882→252
   天，+6.0 pts 漂到 +11.2 pts，vol 環境零變化）；spot 漂移與 LEAPS
   歷史殘缺兩個混淆原封不動；raw gap 還與 vol level 一階成正比。誠實
   結論：**短窗、spot 穩、同 expiry、看走勢不看 percentile 時是合理
   近似**；一年 percentile 不是（§4）。
3. **業界 normalize 的成熟工具箱有四件，全部有一手或官方出處**：
   除以 ATM vol（Mixon 2011 的推薦度量 `(σ_25Δp−σ_25Δc)/σ_50Δ`；
   Natenberg 1994 早已用「IV as % of ATM」）；log-moneyness ÷ √T 座標
   （Natenberg 的 `x = ln(E/U)/√t`；Bennett 的「skew × √T 應為常數」）；
   delta 座標兩點差（FX RR 慣例）；SVI 參數化的 slope（`∂w/∂k`，wings
   漸近斜率 `b(1±ρ)`）。**組合「gap ÷ ATM vol」＋「per-delta 或
   per-log-moneyness slope」即可做到不用人工 bucket、不同 spread 結構
   間可比**（§5）。
4. **FX Risk Reversal 語言可以搬一半**：可搬＝delta 座標、固定兩點差做成
   時間序列、對序列做 percentile／z-score（FX 宏觀圈對 RR z-score 有
   成文實務，1 個月與 6 個月 lookback）；不可搬＝RR 是 call−put 跨兩翼
   （量 smile 不對稱），我們是同翼 call−call（量 call wing 的局部斜率）；
   RR 兩點是 constant delta（每天 re-strike，天然無漂移），我們的
   candidate 是固定 strike（要靠 §9 的座標重錨定解決）；FX OTC 的 delta
   慣例（spot/forward/premium-adjusted）不適用 listed ETF options（§6）。
5. **Zou–Derman SAS（1999，一手全文）實際算的是**：以標的歷史報酬分佈
   經 entropy 最小化轉成 risk-neutral 分佈（RNHD），得出「歷史公平
   smile」，`SAS(K,T) = Σ(K,T) − Σ_H(K,T)`＝市場 IV 對歷史公平 IV 的
   價差，並以 SAS_ATM（強制 ATM-forward 處為 0）版本量「**skew 相對
   歷史的 richness**」，用途明文是「rank the relative value of all
   standard equity options」。它是**橫斷面 rich/cheap 對『歷史公平值』**
   的比較，不直接是時間序列 percentile，但形狀可歷史化；vendor 簡化版
   （ORATS S%、SpiderRock edge、Vola Dynamics fit）把「歷史公平 smile」
   換成「今天的平滑 fit」。SAS 原文腳注還先講了本產品上一輪 §5.3 的
   紅線：SAS 只對「價值對 σ 單調」的標的物有意義——spread 不單調，
   所以**逐腿算，不給 spread 一個 vol-單位的單一數字**（§7）。
6. **「對整個 option universe 做系統性掃描排序」是有一手文獻背書的
   institutional workflow**：SAS 論文自述目的就是給 desk 一個「單維
   metric 把所有標準選擇權排相對價值」；學術端 Goyal–Saretto 2009
   （JFE，IV−HV 橫斷面排序）與 Vasquez（JFQA，term-structure slope
   排序 straddle）證實系統性 vol RV 篩選有超額報酬；vendor 端 ORATS
   scanner（S%/D%/F% 三種 edge）、SpiderRock scanners、Bloomberg VCA
   rich/cheap 全是產品化的同款。**Option Chaser 的「窮舉候選後比較」
   是把這條 workflow 產品化，不是重造不存在的需求**（§8）。
7. **DTE／delta 漂移的成熟解法＝每天重建 surface、在固定 (tenor, delta)
   座標取值，且 vendor 已把這件事做成現成的歷史序列**：ORATS 提供
   constant-maturity IV at 5/25/50/75/95 call delta ×
   10/20/30/60/90/180/365 天內插、含 ex-earnings 版本、2007 起、REST
   按 trade date 查——**對 tenor ≤365 天完全零 bucket**。缺口在本產品
   主戰場：LEAPS DTE（TLT 實例 882 天）超出 ORATS 的 365 天與
   OptionMetrics 的 730 天標準網格，要嘛取「可得最長 tenor」並標注，
   要嘛對 vendor 的 per-expiry 平滑 IV 自做 expiry 維內插（仍無任意
   bucket，工程小、模型透明）（§9）。
8. **Long Call 與 Spread 應該用不同的 IV-history definition，且這正是
   專業慣例**：surface 的三個維度在市場上本來就用三種語言分開報——
   level（ATM vol）、skew（RR／slope）、curvature（butterfly）。單腿＝
   一個 surface 點，判讀它的是 level 語言（percentile 直接成立，上一輪
   §3.3 形狀）；spread＝兩個點的差，判讀它的是 skew 語言（gap／slope／
   residual）。硬把兩種結構塞同一公式反而**沒有**專業先例（§10）。
9. 產品約束已於 §0 原樣照錄，四個方案（§12）逐案對照約束設計，全部
   落在「單一 candidate IV card、事實性數字、不進排名」框架內。
10. **收斂四案（§12，詳表含公式／資料／冷啟動／TLT 實算／先例）**：
    方案一＝兩腿 (tenor, delta) surface 座標各自 1Y percentile（成熟，
    資料最重）；方案二＝candidate 錨定的 normalized skew 序列
    `Ĝ = (σ(Δ_s)−σ(Δ_b))/σ_ATM` 的 1Y percentile（成分全成熟、組合是
    我們的延伸）；方案三＝固定合約 raw gap 走勢圖（資料最輕、誠實
    標注混淆、不做 percentile 核心指標）；方案四＝橫斷面 surface 殘差
    （edge）列（成熟，但回答的是正交的「今天貴不貴」問題，card 上
    必須與歷史位置分開標示）。A/B/C 分類見 §13。

## 3. 問題 1：專業 desk 如何判讀指定 vertical spread 的 volatility relative value

### 3.1 Natenberg（desk 教科書，一手逐字）：以理論 edge 與 vega 集中規則選腿

《Option Volatility and Pricing》1994 年版第 10 章，在 95/100 與 100/105
bull call spread 的對照例（兩組 delta 同為 +20）之後〔一手・逐字〕：

> “As in all spreads, the option trader's goal is to create a position
> with positive theoretical edge, by either purchasing high value at a
> low price, or selling low value at a high price.” (p. 207)
>
> “From an option trader's point of view, the relative prices of options
> in the marketplace is usually represented by the implied volatility.”
> (p. 207)
>
> “If implied volatility is too low, vertical spreads should focus on
> purchasing the at-the-money option. If implied volatility is too high,
> vertical spreads should focus on selling the at-the-money options.”
> (p. 208，原書斜體)

背後機制原文也講明：三張只差履約價的選擇權中，「the at-the-money option
is always the most sensitive in total points to a change in volatility」
（p. 208）——ATM 腿 vega 最大，所以 vol 環境的貴賤決定**哪一腿當主角**。
這是對本產品最直接的 desk 先例：**vertical spread 的 vol 判讀第一層是
「環境水位」（決定買 ATM 還是賣 ATM），不是給 spread 一個自己的 IV**。
這與上一輪 §4.e（環境掛標的層級）與 §5.2 的引擎驗算（進場態 net vega
為正、方向與單腿一致）互相印證。

### 3.2 第二層語言：vertical spread 是 skew 結構（Sinclair、Bennett、GS）

- Sinclair《Positional Option Trading》（2020）對 vertical spread 的
  描述〔二手・索引轉述〕：看空時用 50Δ/20Δ put spread，「同時賣掉隱含
  波動率曲線上最貴的部分之一……好處來自以被抬高的 vol 賣出 20-delta
  put」——**兩腿的 IV 差（skew）是這個結構的內生報酬來源之一**，desk
  對它的判讀語言是 skew，不是「spread 的 IV」。
- Bennett《Trading Volatility》（2014，Santander 研究部原版）：
  「Skew weighted by the square root of time should also be constant」，
  以適當權重 normalize 後的 term structure 與 skew 可用來「identify
  calendar and skew trades in addition to highlighting which strike and
  expiry is significant」〔索引轉述〕。
- Zou–Derman SAS 論文正文以「25-delta put 與 25-delta call 的 vol 差」
  作為 index skew 的量測單位（Table 1：SPX 正常期 4–7 pts、極端期
  14 pts、歷史公平值 6.0 pts）〔一手・逐字〕——GS desk 對 skew 的
  standing 度量就是**兩個 delta 點的 IV 差**。

### 3.3 歸納：desk 的三層拆解（本文後續的骨架）

| 層 | 問題 | 度量 | 對應本產品 |
|---|---|---|---|
| **Level** | 這個標的的 vol 環境相對歷史貴嗎 | constant-maturity ATM IV 的 Rank/Percentile（上一輪 §3.4） | 上一輪方案 A/B，已在需求方手上 |
| **Slope（skew）** | 這組兩腿結構的 IV 差相對歷史在哪 | 兩個 (tenor, delta) 點的差，normalized（§5） | **本文主題**，方案二/三 |
| **Residual** | 這兩張合約相對**今天**整條 surface 偏貴/偏便宜嗎 | fair-smile／smooth-fit 殘差（SAS、S%） | 方案四（橫斷面，與歷史位置正交） |

三層正交、各答各的問題；specified candidate 的「volatility 結構歷史
位置」落在第二層，第三層是它的今日橫斷面補充。沒有任何一手或官方來源
把三層壓成單一「spread IV」——反而 SAS 論文腳注 3 明文警告單一 vol
數字只對「價值對 σ 單調」的東西有意義（§7.1），與上一輪 §5.3 的
ill-defined 證明同一結論。

## 4. 問題 2：Sell-leg IV − Buy-leg IV 的固定合約歷史 percentile 能否直接當核心指標

記 `G = σ_sell − σ_buy`（需求方直覺的 gap；同 expiry 的 bull call spread
中賣腿 strike 較高）。與上一輪 §5.1 的記號對應：`G = −s`，spread 價值的
一階分解為 `dV = (vega₁−vega₂)·dσ̄ − ((vega₁+vega₂)/2)·dG`——**G 正是
spread 特有曝險的自然座標**，需求方盯住 G 這個「對象」是對的（TLT 實例
中 spread 對 G 的敏感度是對平行水位的 2 倍，§11）。問題出在「固定合約
的 G 歷史序列」這把**尺**。

### 4.1 相對上一輪 §3.1，它真的修掉了一種混淆

上一輪 §3.1.1 的第一混淆是 DTE 遞減把 term-structure roll-down 混進
單腿序列。兩腿**同 expiry** 時，term structure 的**平行**滑動（整條
曲線的 level 隨 DTE 變化）在 `σ_sell − σ_buy` 相減時共模抵銷——這是
G 序列確實比任何單腿序列乾淨的地方，值得誠實承認。

### 4.2 沒修掉的三個混淆（每個都能量化）

**4.2.1 skew 斜率本身的 roll-down——相減消不掉。**
skew 的斜率（固定 log-moneyness 座標下）隨到期縮短而變陡，衰減律約
1/√T：Gatheral 書中對 SPX 的 ATM skew vs 到期時間實證擬合（Fig 3.4）
〔一手・逐字〕、Bennett 的「skew × √T 應為常數」經驗律〔索引轉述〕、
Natenberg Fig 18-8d「以 `ln(E/U)/√t` 為 x 軸後各到期的 skew 幾乎重合」
〔一手・逐字〕三方一致。固定 strike 對的 gap ≈ 斜率 × strike 距，因此
**在 surface 形狀（normalized 座標下）完全不變的世界裡，G 也會隨 DTE
縮短機械性放大**。以 √t 律外推本文 TLT 實例（引擎腳本見 §11.1）：

```
DTE 882 → G = 6.0 pts（今天）
DTE 517 → G ≈ 7.8 pts（一年後，vol 環境零變化）
DTE 252 → G ≈ 11.2 pts
DTE 126 → G ≈ 15.9 pts
```

一年 percentile 窗內序列自己就有 +30% 的機械漂移，「G 位於一年高位」
與「skew 環境變貴」無法區分。這是上一輪 §3.1.1 的 skew 版本，逐字適用。

**4.2.2 spot 漂移——兩點沿 smile 滑動。**固定 strike 對在 delta 座標上
的位置隨 spot 移動：TLT 從 84.52 漲向目標 110 時，買腿 90 從 0.61Δ 漂向
深 ITM、賣腿 130 從 0.15Δ 漂向 ATM，G 量到的是 smile **不同區段**的局部
斜率（TLT 的 call wing 越遠越陡，§11 的 +6 pts 正是這個形狀）。上一輪
§3.1.2「劇本越接近成立、漂移越大」的論證原封不動。

**4.2.3 LEAPS 歷史殘缺——原封不動。**兩腿同為遠月 LEAPS、同時掛牌，
一年前可能不存在或報價稀疏（`option-liquidity-filtering.md` §3.2 的
報價義務調查）；G 序列與單腿序列一樣殘缺。本產品主戰場正是 LEAPS，
此混淆無法用任何相減修掉。

**4.2.4 補充：raw G 與 vol level 一階成正比。**skew 以 vol 點計的
寬度大致隨整體 vol 水位縮放（Mixon 對「不控制 vol 與 kurtosis 水位就
無法解讀 skew 度量」的系統性論證〔索引轉述〕；Natenberg p. 412 的
處理動機原文：「suppose the implied volatility … were to double …
the implied volatilities at each exercise price can also be expected
to double」〔一手・逐字〕）。raw G 的 percentile 因此把「level 環境」
與「skew 形狀」再度混在一起——而 level 已由上一輪方案 A/B 回答，
不該讓 G 重複量它。除以 σ_ATM 消掉此項（§5）。

### 4.3 誠實結論：什麼情況下它仍是合理近似

同 expiry（必要條件，否則連 4.1 的抵銷都沒有）＋回看窗短（數週內
√t 漂移 <5%）＋spot 未大幅移動＋兩腿之間 strike 距適中時，raw G 的
**走勢**是「這組結構的 skew 定價最近怎麼動」的可用近似；資料需求也
最輕（兩條 per-contract IV 日序列，
`historical-options-iv-data-sources.md` §4.7 的 Market Data App 單合約
from/to 查詢形狀一次呼叫一腿）。**但把它做成一年 percentile 並當
card 的核心數字，上述 4 個混淆會讓數字在使用者最關心的情境（劇本
進行中、LEAPS、長窗）恰好最失真**。定位：走勢圖可以、percentile
不行——與上一輪 §4.d 對 spread debit 歷史的處置同構。

## 5. 問題 3：raw gap 不夠時，業界怎麼 normalize（深挖）

### 5.1 原型早於一切：Natenberg 1994 的雙重 normalization〔一手・逐字〕

第 18 章處理「不同到期、不同 vol 水位的 skew 如何放在同一張圖比較」，
給出的正是本題要的兩個 normalization：

1. **x 軸**：「in the Black-Scholes model the relative amount of
   movement required to reach an exercise price is fully expressed as
   [natural logarithm (exercise price / underlying price)] / square
   root (time)」（p. 410）——即 `x = ln(E/U)/√t`。轉軸後「the skews
   start to look very much alike」（p. 411）。
2. **y 軸**：「The easiest way … is to express the implied volatility
   at each exercise price as a percent of the at-the-money implied
   volatility.」（p. 412），並把整條 skew 寫成
   `volatility at an exercise price = the at-the-money volatility × f(x)`
   （p. 413，f 的示例 `f(x)=30x²+1`）。

這兩步合起來就是「**log-moneyness ÷ √T 座標、除以 ATM vol**」——1994
年的 desk 教科書已把本題的 normalization 講完，後面的文獻是把它精緻化。

### 5.2 Mixon 2011：系統比較後的推薦度量〔索引轉述〕

Mixon, “What Does Implied Volatility Skew Measure?”（Journal of
Derivatives 18(4), 2011, pp. 9–25）系統比較常用 skew 度量，結論：
多數常用度量「不控制 volatility 與 kurtosis 水位就難以解讀」、許多
ad hoc 度量不滿足有效的 skewness ordering；**推薦度量＝
`(σ_25Δput − σ_25Δcall) / σ_50Δ`**——「most descriptive and least
redundant」。要點有二：(a) 座標用 **delta**（消 moneyness 漂移）；
(b) **除以 ATM vol**（消 level 依賴，§4.2.4）。原文 PDF 在本沙箱
不可達（ivolatility.com 掛載的全文被擋），公式與結論經多來源交叉，
列 §15 第 2 項。

### 5.3 SVI／Gatheral：slope 的參數化語言

Gatheral 書中 SVI 參數化〔一手・逐字〕（式 3.20；k＝log-strike，
w＝total implied variance）：

```
w(k) = a + b·{ ρ·(k − m) + √((k − m)² + σ²) }
```

且「by at-the-money skew, we mean ∂/∂k σ_BS(k,T)²」——**專業端的
「skew」定義就是 surface 對 log-moneyness 的斜率**。由式 3.20 直接
取極限（自行推導）：`k→+∞` 時 `w → a + b(1+ρ)(k−m)`、`k→−∞` 時
`w → a + b(1−ρ)(m−k)`，即**兩翼的漸近斜率是 `b(1±ρ)`**——SVI 把
「call wing 有多陡」壓成兩個參數的組合，這正是「不用人工 bucket、
跨結構可比」的極致形態（整條 smile 五參數，任何兩點差都能從參數
重建）。Gatheral–Jacquier (Quantitative Finance 14(1), 2014) 給出
無套利校準〔索引轉述〕。對本產品：SVI 是方案四自建路線的候選擬合
形式，非第一階段需求。

### 5.4 Bennett：跨到期比較的 √T 加權〔索引轉述〕

「Skew weighted by the square root of time should also be constant」
——與 §4.2.1 的 1/√T 衰減律互為表裡：把 slope × √T 之後，不同 DTE
的 skew 落到同一尺度。注意這與 Natenberg 的 `x = ln(E/U)/√t` 在數學上
等價（斜率對 x 取，自動內建 √t）：本文 §11 實算兩種寫法得到同一個
數字（0.2536），是好的內部一致性檢查。

### 5.5 CBOE SKEW index：同族但不適用本題〔官方・索引轉述〕

SKEW = 100 − 10 × S，S 為 30 天 risk-neutral skewness（第三動差），
由整帶 OTM SPX 選擇權組合以 model-free 方式算出、兩鄰近到期內插到
30 天，典型區間 100–150。它證明「把 skew 做成可長期比較的指數」在
交易所層級成熟可行，但它是**標的層級、全 smile 的第三動差**——
綁不到 candidate 的兩個具體點上，且 tenor 固定 30 天與 LEAPS 錯配
（上一輪 §3.4 末段同一問題）。列入本文只為完整性，不進方案。

### 5.6 歸納：本產品可用的 normalized gap 定義

把 §5.1–5.4 收斂成一個可實作族（記買賣腿座標為 delta 或 log-moneyness）：

| 定義 | 公式 | 消掉的混淆 | 先例 |
|---|---|---|---|
| **Level-normalized gap** | `Ĝ = (σ_s − σ_b) / σ_ATM` | §4.2.4 level 依賴 | Mixon、Natenberg y 軸 |
| **Per-delta slope** | `G / (Δ_b − Δ_s)`（每 10Δ 報一次） | 不同 strike 距的結構間可比 | FX RR（固定 25Δ 距）、Mixon |
| **Per-log-moneyness slope × √T** | `G / ln(K_s/K_b) × √T` | strike 距 ＋ §4.2.1 的 √t roll-down | Natenberg x 軸、Bennett、SVI ∂w/∂k |

三者都不需要 bucket：分母全是 candidate 自己的座標算術。**若座標本身
每天在當天 surface 上重錨定（§9.1），這些 normalized gap 的歷史序列就
同時消掉 §4.2.1–4.2.3 全部三個混淆**——這是方案二的定義基礎。

## 6. 問題 4：FX Risk Reversal 語言能否類比到 debit vertical spread

### 6.1 慣例本體〔官方＋二手・索引轉述；上一輪 §2.3/§3.3 已建立部分〕

FX 市場不直接報 smile，報三件套：ATM vol、25Δ risk reversal、25Δ
butterfly/strangle，各 tenor 一組（1W/1M/3M/6M/1Y）；
`σ_RR,25 = σ_25Δcall − σ_25Δput`（FX 記號慣例；等式方向與股票圈慣用的
put−call 相反），smile 由三件套重建（Reiswich & Wystup, “FX Volatility
Smile Construction”, CPQF Working Paper No. 20；原文 PDF 被擋，§15
第 3 項）。delta 有 spot／forward／premium-adjusted 多種慣例，選錯
慣例重建就錯——這是 FX OTC 特有的坑。RR 的歷史序列在宏觀圈是標準
positioning 指標：對 RR 序列取 **z-score**（常用 1 個月與 6 個月
lookback，前者看流向、後者看結構性倉位）判讀極端〔二手・索引轉述，
Spectra Markets 教材〕。

### 6.2 可搬的三件事

1. **delta 座標**：RR 幾十年實務證明「兩個 delta 點的 IV 差」是穩定
   可交易、可比較的物件——方案二的座標選擇直接繼承。
2. **固定兩點差的時間序列化**：RR 每天算一個數、存成序列——「兩點差
   可以是一條有歷史的線」這件事不需要我們發明。
3. **percentile／z-score 化**：對 RR 序列取統計位置判讀極端是成文
   實務；z-score 與 percentile 的取捨同上一輪 §2.1 的 Rank vs
   Percentile 討論（極值敏感度），本產品沿用 percentile 為主。

### 6.3 不可直接搬的四件事

1. **跨翼 vs 同翼**：RR＝call 翼減 put 翼，量的是 smile 的**不對稱**
   （第三動差方向）；本產品 bull call spread 的 G＝同一 call 翼上兩點
   之差，量的是 **call wing 的局部斜率**。兩者是 surface 的不同泛函，
   歷史行為不同（TLT 的 call wing 向上傾斜是利率市場「賭大漲」需求的
   結構特徵，與 equity index 的 put skew 不同向）。類比只到「兩點差」
   的形式層，不能把 RR 的經驗規律（如 RR 與 spot 動能的相關）搬過來。
2. **constant delta vs fixed strike**：RR 每天 re-strike 到當天的
   25Δ，序列天然無 moneyness 漂移；我們的 candidate 是固定 strike，
   直接序列化就掉進 §4.2 的坑。解法不是放棄，而是 §9.1 的座標重錨定
   ——歷史比較集用 constant-delta 建，今天的值取 candidate 實際座標。
3. **OTC 慣例不適用**：premium-adjusted delta、spot vs forward delta
   等 FX 慣例在 listed ETF options 無對應物；本產品用 BS call delta
   （引擎既有口徑）即可，但引用 FX 文獻數字時不可混用。
4. **tenor 結構**：FX 三件套逐 tenor 常設報價、序列永續；listed
   options 只有離散到期日，固定 tenor 序列要靠內插（§9）——FX 那邊
   「拿來就用」的部分在我們這邊是要自己（或 vendor）做的工。

## 7. 問題 5：Strike-Adjusted Spread 與 fair-surface residual 家族（一手深挖）

### 7.1 SAS 實際算什麼〔一手・逐字，Zou & Derman 1999〕

論文開篇先把「舊的兩把尺」定位——這兩句對本產品極有價值，因為它們
正是上一輪方案 A 與 E 的 desk 血統證明：

> “The most common gauge of options value has been the spread between
> current and past implied volatilities. This is the metric of options
> speculators…” (p. 1)
>
> “A second gauge is the spread between current implied and past
> realized volatilities. This is the metric of options replicators…”
> (p. 1)

SAS 的四步定義（pp. 2–3，原文編號步驟摘錄）：

1. 取標的歷史報酬在期限 T 上的經驗分佈；
2. 以**相對 entropy 最小化**把經驗分佈轉成滿足 forward 約束的
   risk-neutral 分佈（RNHD，“risk-neutralized historical
   distribution”；Stutzer 1996 的 canonical valuation 一脈）；
3. 用 RNHD 對每個 strike 定價、反推 BS implied volatility，得
   「歷史公平 vol」`Σ_H(K,T)`；
4. **`SAS(K,T) = Σ(K,T) − Σ_H(K,T)`**——市場 IV 與歷史公平 IV 的
   價差，「a measure of the current richness of the option based on
   historical returns」。

用途定位（p. 2）：「a natural one-dimensional metric with which to
rank the relative value of all standard equity options, irrespective
of their particular strike or expiration. We propose to use SAS in
roughly the same way that stock investors use ‘alpha’ and mortgage
investors use OAS.」

**腳注 3（p. 3）是給本產品的紅線背書**：「A positive SAS connotes
richness only for standard options whose value is a monotonically
increasing function of volatility.」——spread 價值對 σ 非單調（上一輪
§5.3 的引擎實證），所以 SAS 家族的任何實作都必須**逐腿**，永遠不對
spread 湊單一 vol 數字。1999 年的 GS 原文與本 repo 2026 年的引擎實算
在同一結論上會師。

### 7.2 SAS_ATM＝「skew 相對歷史的 richness」

多數情況 GS 用加約束版本：RNHD 額外校準到市場 ATM-forward vol
（RNHD_ATM），使 `SAS_ATM(S_F[T], T) = 0`——理由原文（p. 3）：「The
volatility skew … is more stable than the absolute level of
at-the-money implied volatilities」（§4.2.1 的又一佐證），以及結論章
（p. 21）：「we calibrate the SAS to be consistent with current
at-the-money volatility, so that it becomes a measure of **skew
richness as compared with history**.」——**把 level 交給 ATM、自己
專量 skew** 的分層，與本文 §3.3 三層拆解完全同構。使用警語（p. 21）：
「The SAS ranking cannot be used blindly; it depends on the user's
selection of the historical period most relevant to the current
market.」（Fig 5 vs Fig 6：含不含 1987 崩盤，OTM put 從偏便宜翻成
大幅偏貴）——任何歷史窗參數都必須在方法論尾註揭露，本 repo 報告
版型已有此慣例位置。

### 7.3 能否轉化為「單一 candidate 的歷史 percentile」

SAS 本身是**橫斷面**量（今天的市場 vs 歷史推出的公平值），不是
「今天 vs 過去每一天」的時間序列位置——但兩者可以複合：對每個歷史
交易日算當日的 `SAS(K_b)`、`SAS(K_s)` 或其差，再取今天值在序列中的
percentile。**本輪檢索沒有找到任何 vendor 把「per-candidate SAS
歷史 percentile」做成現成產品**〔檢索性結論，§15 第 9 項〕；工程上
它要求「每天一份 RNHD＋全鏈定價」，比 §9 的 surface 歷史還重一層
（多一個歷史報酬分佈模型）。判定：**RNHD 全套不進第一階段方案**；
它的簡化版（下）才是可實作路徑。

### 7.4 同族的 vendor 簡化版：把「歷史公平 smile」換成「今天的平滑 fit」

- **ORATS smoothed edge（S%）**：SMV 平滑值與成交價的距離，scanner
  核心欄位；另有 D%（distribution edge）與 F%（forecast edge）兩種
  理論 edge〔官方・索引轉述〕。上一輪 §4.c 已定位：這回答橫斷面
  問題。D% 用報酬分佈定公平值，血統上就是 SAS 的直系後代。
- **SpiderRock**：兩步 surface fit（spline 參數化），提供「current
  valuation theoretical edge」與 edge 部位的 P&L 追蹤、surface curve
  歷史（含 ATM 點、skew／term 參數）、市場 scanner〔官方・索引轉述〕。
- **Vola Dynamics**：無套利約束下的 surface fitter，約 50 家專業
  交易機構在用；rich/cheap 判讀是其 use case 敘述的一部分〔官方・
  索引轉述〕。
- **Cboe `theo` 欄位**（Hanweck 擬合值）：免費版同思想，本 repo 已
  實測過其與 mid 的獨立性（`option-liquidity-filtering.md` §6.5）——
  方案四的零成本起點。

**與本產品引擎的口徑警告（引擎實算）**：本 repo 引擎是 q=0 的 BS
（報告尾註明載「無股利調整」）。以 §11 的實際輸入驗算：
`bs_call(84.52, 90, 2.416, 0.04, 0.12) = 7.68`，而市場報價 3.80/4.10
——TLT 配息率與利率同量級，q=0 模型在長天期把 call 理論值高估近一倍。
**這不影響方案一～三（它們消費的是市場 IV 本身），但堵死了「用現有
引擎自建方案四殘差」的捷徑**：fair-value 模型必須帶股利口徑，否則
殘差全是股利假象。Cboe `iv` 為含離散股利的美式二項樹反推
（`cboe-field-semantics.md` §2.2），與 BS-q=0 本來就不等價，同一
警告的另一面。

## 8. 問題 6：專業市場是否對整個 universe 做系統性掃描與 relative-value screening

**是，且三個層級都有據可查**——本節目的：確認 Option Chaser
「窮舉候選後比較」是把 institutional workflow 產品化。

1. **Desk（一手）**：SAS 論文自述寫作動機是 equity derivatives desk
   「options on many different underlyers must be valued daily」，
   產出就是把**所有** strike×expiry 排上同一維相對價值尺（§7.1 引文）；
   Fig 5–7 對整條 strike 帶逐點畫 SAS。Natenberg 第 10 章的選腿流程
   （§3.1）同樣是「先掃全部可選 strike 的理論 edge、再挑結構」。
2. **學術（橫斷面 RV 文獻）**〔索引轉述〕：Goyal & Saretto (2009,
   Journal of Financial Economics 94, pp. 310–326)——按「HV − ATM IV」
   對全股票池排序，做多大正差、放空大負差的零成本組合，月均報酬在
   經濟與統計上皆顯著，對風險因子穩健；Vasquez (JFQA)——按 IV term
   structure 斜率排序買賣 straddle，高斜率減低斜率組合月均毛報酬
   27.1%（未扣成本，數字未經原文核對，§15 第 6 項）。兩者的方法核心
   都是**在固定座標（ATM、標準 tenor）上對整個 universe 排序**——
   與本產品「每期窮舉、排名、取 Top 10」同一形狀。
3. **Vendor／平台**〔官方・索引轉述〕：ORATS Option Scanner（以
   S%/D%/F% 理論 edge 為條件掃描）；SpiderRock market scanners（以
   surface edge 為訊號）；Bloomberg VCA（跨標的 implied/realized
   rich-cheap、比較誰的 skew／term structure 最陡）。

**結論**：「先窮舉、後比較、以固定座標的量化指標排序」是從 desk 到
學術到 vendor 三方一致的成熟 workflow。Option Chaser 已做的是
「報酬結構」維度的窮舉比較；本文要加的 IV 資訊層，等於把同一
workflow 的「vol 維度」補上——每一個成分都有先例，見 §13 分類。

## 9. 問題 7：歷史比較如何處理 DTE／Delta／moneyness 漂移（可實作層級）

### 9.1 核心觀念：座標重錨定（re-anchoring），不是跟著合約走

上一輪 §3.3 的做法此輪講透一層。固定合約的序列之所以是類別錯誤
（§4.2），是因為它讓**量測座標跟著合約漂**。成熟做法把問題反過來：

> 歷史比較集不綁合約，綁座標。每個歷史交易日在**當天的** surface 上
> 取固定 (tenor, delta) 點，構成該座標點自己的永續序列；今天要判讀
> candidate 時，取 candidate **今天實際的**座標 (T*, Δ_b, Δ_s)，問
> 「這組座標的今天值，落在同組座標的一年歷史分佈哪裡」。

candidate 明天座標變了（DTE−1、delta 隨 spot 漂），就問明天座標的
歷史分佈——**每一天的 percentile 都是「當下這個結構」對「歷史上
同形狀結構」的誠實比較**，三個漂移（DTE、moneyness、上市時長）按
定義消失：DTE 恆為 T*、delta 恆為錨定值、序列不隨任何合約生滅。
這正是 OptionMetrics standardized options／ORATS 內插 IV 的消費方式
（上一輪 §3.3），也是 FX RR「每天 re-strike 到 25Δ」慣例的 listed
版本（§6.2）。

### 9.2 「每天一張 surface」的實作選項（若走自建）

| 步驟 | 選項 | 出處 |
|---|---|---|
| strike 維擬合 | SVI（5 參數／expiry，無套利約束可加，式 3.20） | Gatheral〔一手〕、Gatheral–Jacquier 2014〔索引〕 |
| | kernel smoothing（網格輸出） | OptionMetrics IvyDB〔上一輪 §3.3〕 |
| | spline＋殘差 yield 對齊 put/call | ORATS SMV、SpiderRock〔索引轉述〕 |
| expiry 維內插 | total variance 對 T 線性（VIX 祖形）／√t 內插 | 上一輪 §3.4 表 |
| 取點 | 反解 (tenor, delta) → (T*, K*)，讀出 σ | FX 慣例同款 |

自建量級：每天全鏈一次擬合＋兩三個點的求值——但「把平滑做對」
（清洗、無套利、稀疏報價）正是 vendor 的產品本體（上一輪 §3.3 的
同一警告），第一階段不建議自建。

### 9.3 Vendor 直接提供 per-(tenor, delta) 歷史序列——零 bucket 成立

ORATS 官方〔官方・索引轉述〕：constant-maturity implied volatility
在 **5／25／50／75／95 call delta** 各水平提供，tenor 內插點
**10／20／30／60／90／180／365 日曆天**，且**含 ex-earnings 版本**；
歷史 API 覆蓋全美股選擇權 **2007 起**、按 trade date 查詢；計算法
為「取夾住目標天數的兩個到期、在指定 delta 水平上加權平均」。
OptionMetrics standardized surface 網格為 tenor 10–730 天 × delta
0.10–0.90 間隔 0.05（上一輪 §3.3）。**結論：對 tenor ≤365（OM 到
730）天，需求方「不想自己切 ±30 天 bucket」的願望由 vendor 現成
序列直接滿足——不存在任何人工 bucket，座標是連續內插的。**

### 9.4 誠實缺口：本產品的 LEAPS tenor 超出標準網格

TLT 實例 DTE=882 天 > ORATS 365 > OptionMetrics 730。三條處理路線
（供方案設計引用，不拍板）：

1. **錨最長可得 tenor**（如 365d 或 730d）當 proxy，card 上如實標注
   「以 N 天期結構為基準」——遠端 term structure 平緩（上一輪 §3.4
   末段），proxy 誤差是二階，但必須揭露；
2. **對 vendor 的 per-expiry 平滑 IV 自做 expiry 維內插**：ORATS
   `hist/strikes` 級歷史含每個實際到期的平滑 IV（2007 起），對最遠
   兩個實際 expiry 做 total-variance 內插到 882 天——仍然零任意
   bucket（內插不是 bucket），工程量小、模型透明，但把一小段擬合
   責任搬回自己家；
3. **等 candidate 老化進網格**：DTE 進入 ≤730/365 後切回路線 9.3；
   card 標注切換。

## 10. 問題 8：Long Call 與 Vertical Spread 是否應使用不同的 IV-history definition

**應該，且「不同結構用不同 vol 語言」正是專業慣例，不是我們的妥協**：

1. **市場自己就把 surface 的三個維度拆成三種語言報價**：FX 的
   ATM（level）／RR（skew）／BF（curvature）三件套（§6.1）；SAS 的
   level 交給 ATM 校準、SAS_ATM 專量 skew（§7.2）；Bennett 對 level
   ／term structure／skew 各給不同的 normalize 與交易型態〔索引轉述〕。
2. **單腿 Long Call＝一個 surface 點**：它的歷史判讀是 level 語言
   ——該 (tenor, delta) 座標的 IV percentile（上一輪 §3.3 形狀，
   本文 §9.1 機制），一個數字、直接成立。
3. **Vertical spread＝兩個點的差**：它的特有曝險由 gap 承載（§4 開頭
   的分解；TLT 實例 skew 敏感度是 level 的 2 倍，§11.3），歷史判讀是
   skew 語言——normalized gap 的 percentile（§5.6）。給它硬套單腿的
   「單一 IV percentile」等於把 §4.2 的四個混淆全數請回來，或違反
   §0 的「不創造 Spread IV」紅線。
4. **同一張 card 的統一感由「欄位家族」達成，不必由「同一公式」達成**
   （§12.5）：兩種模式共用「腿列（每腿 IV＋座標＋percentile）」，
   spread 模式多一列 gap——資訊架構統一、定義誠實分流。SAS 論文
   腳注 3（§7.1）是「不硬統一」的一手背書。

## 11. TLT LEAP Call Spread 實算（各方案共用的數字基礎）

### 11.1 輸入與重現步驟

輸入取自 repo 根目錄 `tlt_report.md`（commit `8625fad` 已入庫的真實
報告；yfinance 快照 2026-07-18、分析基準日 2026-07-17、TLT 現價
**84.52**、劇本 2027-12-31 到 110.00、r=4%）。註：任務原點名的
`contracts/analysis_sample.json` 實為合成 XYZ 樣本、`tests/fixtures/`
的真實 TLT payload（`test_data_cboe.py`）只有 2026-07-31 近月三張，
皆不含 LEAPS 兩腿——`tlt_report.md` 是 repo 內唯一含真實 TLT LEAPS
雙邊報價＋IV 的檔案，故以它為輸入。報告顯示的 IV 為整數百分比
（四捨五入），據此重算的 Greeks 與報告顯示值可能差最末位（實測：
賣腿 vega 重算 0.30、報告顯示 0.29，即顯示捨入殘差；delta 兩腿
0.61／0.14 完全吻合）。

Candidate：**Bull Call Spread 買 2028-12-15 C90 ／ 賣 2028-12-15 C130**

| 腿 | Bid | Ask | IV（報告顯示值） |
|---|---|---|---|
| 買 C90 | 3.80 | 4.10 | 12% |
| 賣 C130 | 0.63 | 0.73 | 18% |
| （參考）C85 ≈ ATM | 5.65 | 5.90 | 12% |

重現（`PYTHONPATH=. .venv/bin/python`，全部 stdlib＋repo 引擎）：

```python
import math
from datetime import date
from option_chaser.valuation import call_greeks, bs_call, days_between
S, r = 84.52, 0.04
T = days_between(date(2026, 7, 17), date(2028, 12, 15)) / 365.0  # 882/365
g_b = call_greeks(S,  90.0, T, r, 0.12)   # delta 0.6082, vega/pct 0.5048
g_s = call_greeks(S, 130.0, T, r, 0.18)   # delta 0.1461, vega/pct 0.3010
G = 0.18 - 0.12                            # sell IV - buy IV = +6.0 pts
# normalized 系列（§5.6）
G / 0.12                                   # ÷ ATM IV        = 0.500
G*100 / ((g_b.delta - g_s.delta)*10)       # per 10-delta    = 1.298 pts
G*100*0.10 / math.log(130/90)              # per 10% logm    = 1.632 pts
(G / math.log(130/90)) * math.sqrt(T)      # slope×√T        = 0.2536
# §4 開頭的敏感度分解
g_b.vega_per_pct - g_s.vega_per_pct        # net vega        = +0.2038 /pt
-(g_b.vega_per_pct + g_s.vega_per_pct)/2   # dV/dG           = -0.4029 /pt
# gap 的定價意義：平均水位固定在 0.15，G 從 0 拉開到 6 pts
bs_call(S,90,T,r,0.15)-bs_call(S,130,T,r,0.15)   # G=0    → 8.41
bs_call(S,90,T,r,0.12)-bs_call(S,130,T,r,0.18)   # G=6pts → 6.10（便宜 2.30）
```

### 11.2 結果表（card 上可放的事實性數字）

| 量 | 值 | 說明 |
|---|---|---|
| 買腿座標 | (DTE 882, Δ 0.61)，IV 12% | 方案一的取點座標 |
| 賣腿座標 | (DTE 882, Δ 0.15)，IV 18% | 同上 |
| **Raw gap G** | **+6.0 vol pts** | sell − buy（需求方直覺量） |
| G ÷ ATM IV | 0.50 | Mixon 式 level-normalized |
| G per 10-delta | 1.30 pts | delta 座標 slope |
| G per 10% log-moneyness | 1.63 pts | strike 座標 slope |
| slope × √T | 0.254 | Natenberg x 座標＝Bennett √t 加權（兩法同值，內部一致） |
| net vega（每 +1pt 平行） | +$0.204/股 | 上一輪 §5.1 分解第一項 |
| dV/dG（每 +1pt gap 拉開） | −$0.403/股 | 分解第二項（|skew| ≈ 2×|level|） |
| G 的定價效果 | 平均水位 0.15 固定下，G 0→6pts 使 package 模型值 8.41→6.10（−2.30/股） | q=0 引擎口徑 |
| net_worst / max_profit | 3.47 ／ 36.53 | 既有 A14.2 口徑，對照用 |

### 11.3 判讀（事實層，示範 card 語言不加主觀標籤）

- 這組 candidate 的 skew 曝險（0.403/pt）約為平行水位曝險（0.204/pt）
  的 **2 倍**——「這組 legs 的 volatility 結構」確實主要活在 gap 維度，
  需求方把問題推進到 gap 是有引擎數學支持的。
- +6.0 pts 的 raw gap 在「平均水位不變」的對照下讓這組 package 的
  模型值低 2.30/股（約 27%）——gap 高低對 debit 買方的**進場定價**
  是一階效應，值得放上 card；但它相對歷史高不高，必須用 §5.6 的
  normalized 版本＋§9.1 的座標重錨定序列來答，raw G 序列會被
  §4.2.1 的 √t 漂移污染（同組 strikes 一年後光 roll-down 就漂到
  ≈7.8 pts）。
- q=0 引擎在此標的長天期的絕對定價與市場有大偏差（§7.4 末段），
  本表中凡「模型值」皆為引擎口徑、與產品其餘顯示同源；IV 與 gap
  本身取自市場，不受此影響。

## 12. 問題 10：收斂為四個可實作方案

共同前提：計算全落 Python 引擎（前端零金融計算，spec #47）；全部
遵守 §0 約束——單一 candidate IV card、事實性數字、不進排名；資料
形狀對照 `historical-options-iv-data-sources.md`（vendor 選型平行
研究，本文不選）。**Long Call 與 Spread 在每案內都是同一 card 的
兩種模式**（§10、§12.5）。

### 12.1 方案一：兩腿 (tenor, delta) surface 座標各自的 1Y percentile

- **定義**：對每腿，取其今日座標 (T*, Δ)（§9.1 重錨定），在 vendor
  的 per-(tenor, delta) 歷史序列上算 1Y percentile。card 顯示：
  每腿「IV x%｜歷史第 p 百分位」。Long Call 模式＝只有一腿，退化為
  單點 percentile（上一輪 §3.3 的原型）。
- **資料**：per-(tenor, delta) 歷史序列，每腿一條 ×252 天（KB 級）。
  vendor 對照：ORATS constant-maturity delta-level IV（2007 起，
  §9.3）——但 tenor ≤365 天；OptionMetrics 到 730 天；**LEAPS 缺口
  走 §9.4 的三條路線之一，card 須標注所用 tenor**。
- **一年序列與 percentile**：序列錨在座標上、永續，無新掛牌問題；
  標的本身歷史不足一年時顯示「以現有 N 天計」（本 repo 利率快取
  「誠實標注 fallback」慣例）。
- **優點**：方法論天花板（上一輪 §3.3 判定不變）；學術／資料商雙重
  先例；兩腿 percentile 的差本身就攜帶 skew-relative-to-history 資訊。
- **缺點／失真**：兩個 percentile 的合成判斷丟給使用者（上一輪
  §4.a 的老問題）；LEAPS tenor 缺口；vendor 依賴最深。
- **成本**：無自建擬合；每次刷新 2 次（Long Call 1 次）vendor 查詢
  ＋一年序列快取（Neon 一表，形狀同利率快取）。
- **TLT 實算**：買腿點 (882d, 0.61Δ)＝IV 12%、賣腿點 (882d, 0.15Δ)
  ＝IV 18%（§11.2）；percentile 需歷史序列，沙箱不可得，card 位置
  與計算路徑如上。
- **先例**：OptionMetrics standardized surface（學術事實標準）、
  ORATS 內插 IV＋`ivRank/ivPct` 欄位家族（上一輪 §3.4 表）。

### 12.2 方案二：candidate 錨定的 normalized skew 序列（本文主推形狀，供裁示）

- **定義**：以 candidate 今日座標 (T*, Δ_b, Δ_s) 錨定；對每個歷史
  交易日在當天 surface 取同座標兩點，算
  **`Ĝ_t = (σ_t(Δ_s) − σ_t(Δ_b)) / σ_t(ATM)`**（§5.6 第一式；分子
  亦可並列 per-10Δ slope 寫法），得一條一年序列；card 顯示今天的
  `Ĝ` 與其 1Y percentile＋迷你走勢圖。**Long Call 模式＝分子退化為
  單點對 ATM 的差（σ(Δ)−σ_ATM）／σ_ATM，或直接省略 gap 列只留方案一
  的單點 percentile**——同一公式族、兩種呈現。
- **資料**：與方案一同一來源（每天三個座標點：兩腿＋ATM），量級
  相同（KB 級）；LEAPS tenor 缺口同 §9.4。
- **一年序列與 percentile**：序列錨在座標三元組上、永續；candidate
  老化時座標日日重錨（§9.1），每天的 percentile 都是「當下結構 vs
  歷史同形結構」；新掛牌無影響。
- **優點**：**這是對需求方原始問題（「這組 legs 的 volatility 結構
  相對歷史在哪」）最直接的單一數字回答**；§4.2 的四個混淆全消
  （√t 由重錨定消、level 由 ÷σ_ATM 消、moneyness 由 delta 座標消、
  殘缺由座標序列消）；單一數字＋單一走勢圖，符合 §0 的單一 card
  約束；與 spread 的實際曝險軸對齊（§11.3：skew 敏感度 2× level）。
- **缺點／失真**：`Ĝ` 是合成量，對使用者要一句定義文案（card 腳注
  「賣腿與買腿 IV 之差，除以同天期 ATM IV」）；delta 錨取「今日
  delta」使昨天與今天的 percentile 基準略有位移（結構老化的真實
  反映，不是 bug，但要能解釋）；vendor 的 delta 網格若只有
  5/25/50/75/95，非網格 delta（如 0.61）要再做一次 delta 維內插
  （線性即可，斜率平滑段誤差二階）。
- **成本**：每次刷新 3 個座標點查詢＋序列快取；計算為純算術
  （stdlib），落 `valuation.py` 旁新純函式即可。
- **TLT 實算**：今天值 `Ĝ = (0.18−0.12)/0.12 = 0.50`；並列寫法
  per-10Δ = 1.30 pts、slope×√T = 0.254（§11.2）。歷史 percentile
  需 vendor 序列。
- **先例**：**成分全部成熟**——delta 座標兩點差（FX RR，§6）、
  ÷ATM normalization（Mixon 2011、Natenberg 1994、SAS_ATM 的
  level/skew 分層）、序列 percentile/z-score 化（FX RR z-score
  實務、上一輪 §2.1 家族）；**組合無直接先例**（把兩點錨在
  candidate 自身 delta 對、call−call 同翼）——B 類延伸，延伸點
  見 §13。

### 12.3 方案三：固定合約 raw gap 走勢圖（需求方直覺案的誠實版）

- **定義**：對 candidate 的兩張實際合約，畫 `G_t = σ_sell,t −
  σ_buy,t` 的日粒度走勢圖（V9 spread 成本走勢的 IV 版），標注今天
  值；**不把 percentile 當核心數字**（§4.3 判定；若需求方堅持顯示，
  必須附「此序列含 DTE 與價格漂移成分」的中性標注，且不得與
  「歷史位置」字樣並用）。
- **資料**：兩條 per-contract IV 日序列。三個來源層級：(a) 按需
  vendor per-contract 歷史（Market Data App 單合約 from/to 一次
  呼叫一腿——查詢形狀最省，見資料源研究 §4.7；ORATS strikes 級
  同能）；(b) **自家 V9 快照歷史**（`store.spread_cost_history()`
  同款聚合改抽 IV 欄位——零新資料源、零成本，歷史深度＝自家快照
  多久）；(c) 兩者疊合。
- **一年序列**：受 §4.2.3 限制——合約掛牌前無資料，斷點如實留白
  （V9「缺席即斷點不插值」慣例沿用）。
- **優點**：資料最輕（b 路線零新依賴）；語意最直觀（就是這兩張
  合約）；與 V9 成本走勢圖並排時，使用者可自行對照「debit 動了是
  spot 還是 IV 結構動了」——這是它獨有的教育價值。
- **缺點／失真**：§4.2 全套混淆；走勢圖尾端（DTE 縮短）的機械性
  放大會被誤讀為「skew 變貴」，card 文案要中性處理。
- **成本**：b 路線＝一個純函式＋一條折線（V9 同款）；a 路線＝
  vendor 兩次呼叫。
- **TLT 實算**：今天 G = +6.0 pts；√t 機械漂移示意（vol 環境凍結）：
  DTE 882→517→252 天時 6.0→7.8→11.2 pts（§4.2.1）——此表本身
  就該放進工程文件當「為何不做 percentile」的註記。
- **先例**：thinkorswim comparison study 畫兩腿差價歷史（上一輪
  §4.d，查看工具、非指標）；per-contract IV 歷史為 Barchart
  Premier 等平台的既有欄位（上一輪 §2.2）。gap 的 percentile 化
  無先例，且本文 §4.2 論證了為什麼不該有。

### 12.4 方案四：橫斷面 surface 殘差（edge）列——與歷史位置正交的補充

- **定義**：對每腿，顯示「市場報價相對**今天**整條平滑 surface 的
  殘差」（vol 點或價格 %）。card 上與歷史 percentile 分區、分標題
  （「相對今日曲線」vs「相對一年歷史」），嚴禁混排——上一輪 §4.c
  的正交性警告原樣沿用。
- **資料**：只要當天全鏈＋一套平滑值。零成本起點＝Cboe `theo` 欄位
  （快照已有，`option-liquidity-filtering.md` §6.5 實測過獨立性）；
  升級路徑＝vendor edge 欄位（ORATS S%）或自建 SVI 擬合（§9.2）。
  **自建警告：本 repo q=0 引擎不可直接當 fair-value 模型**（§7.4
  末段的 7.68 vs 3.95 實測），要嘛用 Cboe/vendor 的含股利理論值，
  要嘛擬合時把 forward 從 put-call parity 解出（ORATS SMV 的
  residual yield 手法）。
- **歷史化選項**：edge 本身可再做歷史 percentile（SAS 的複合式，
  §7.3），但無 vendor 先例、且是第二階段議題，本輪不進 card。
- **優點**：回答「這兩張報價今天挑得好不好」——與最差成交口徑
  互補（成本已誠實算最差，殘差再告訴你最差價本身偏不偏）；資料
  最輕的一案。
- **缺點／失真**：**它不回答需求方的歷史位置問題**（正交）；
  `theo` 路線的擬合品質不受我們控制；殘差在寬 bid-ask 的 LEAPS 上
  噪音大（殘差 < 半個 spread 時無資訊量，card 應以 spread 寬度為
  底噪標尺）。
- **成本**：`theo` 路線＝快照已有欄位的一次減法＋序列化；vendor
  路線＝每腿一欄。
- **TLT 實算**：本輪快照無 `theo` 留存，示意口徑：`edge_b = ask_b −
  theo_b`、`edge_s = bid_s − theo_s`（與 A14.2 最差成交同向取保守）。
- **先例**：SAS（一手，§7.1）、ORATS S%／D%、SpiderRock edge、
  Vola Dynamics、Bloomberg VCA（§7.4、§8）——**四案中先例最厚**。

### 12.5 同一張 candidate IV card 的資訊架構（四案的落位示意，只到欄位層）

```
┌ IV 結構（candidate：TLT 2028-12-15 90/130 Bull Call）────────┐
│ 買腿 C90   IV 12%  (882d, 0.61Δ)   1Y percentile ▓▓░░ p₁   │ ← 方案一
│ 賣腿 C130  IV 18%  (882d, 0.15Δ)   1Y percentile ▓░░░ p₂   │ ← 方案一
│ Gap（賣−買） +6.0 pts   Ĝ=0.50    1Y percentile ▓▓▓░ p₃   │ ← 方案二
│ [gap 走勢圖 ────────────────╮                              │ ← 方案三
│                              ╰──●]  基準 tenor：365d*      │
│ 相對今日曲線：買腿 +x.x pts／賣腿 −y.y pts（Bid-Ask 0.30/0.10）│ ← 方案四
└──────────────────────────────────────────────────────────────┘
  Long Call 模式：同 card 去掉 Gap 列與賣腿列。
  * 標注（§9.4 tenor 缺口）與歷史窗、資料源，落方法論尾註慣例位置。
```

單一 card、全部事實性數字、無主觀標籤——四案不是四個 UI 區塊，
是同一張 card 的四種候選「列」；需求方可裁示取哪幾列。

## 13. 成熟度分類（明確分類，不拍板）

**A. 業界成熟做法（有 desk／vendor／文獻 precedent，可直接引用先例）**

- 方案一（per-(tenor, delta) 座標 percentile）：OptionMetrics／ORATS
  現成序列＋學術消費慣例（§9.3；上一輪 §3.3）。
- 方案四（橫斷面 surface 殘差）：SAS 一手＋ORATS S%＋SpiderRock＋
  Vola Dynamics（§7）。
- 底層件全部成熟：delta 座標兩點差（FX RR）、÷ATM normalization
  （Mixon／Natenberg／SAS_ATM）、√t 加權（Natenberg／Bennett）、
  序列 percentile/z-score（IVR 家族／FX RR z-score）、universe
  掃描排序（SAS／Goyal-Saretto／Vasquez／vendor scanners）。

**B. 合理但屬我們的產品化延伸（成熟成分組合而來，無直接先例——
延伸點標明如下）**

- **方案二**：延伸點有三——(1) 兩點錨在 candidate 自身的 delta 對，
  而非市場慣例的固定 25Δ（RR 是市場慣例點，我們是結構自訂點）；
  (2) call−call 同翼 gap，而非 RR 的跨翼差（§6.3 第 1 點）；(3)
  「每日重錨定＋當日座標 percentile」的呈現組合。三個延伸都是把
  成熟座標系「參數化到 candidate」，不引入新的金融假設。
- **方案三的 gap 走勢圖**：查看工具有先例（thinkorswim comparison
  study 形狀），把它做成 candidate card 的常駐列是我們的延伸；
  誠實標注下屬低風險。
- （沿用上一輪 B 類：方案一的 LEAPS tenor 缺口處理——§9.4 路線 2
  的自做 expiry 內插是我們的工程延伸，內插法本身成熟。）

**C. 不建議採用＋原因**

- **固定合約 raw gap 的 1Y percentile 作為核心指標**：§4.2 四個
  混淆（√t 機械漂移、spot 漂移、LEAPS 殘缺、level 依賴），數字在
  最關鍵情境最失真；走勢圖形式已由方案三承接。
- **vega-weighted「spread IV percentile」**：上一輪 §4.b／§5.2——
  分母穿零變號，常駐指標必然間歇輸出垃圾。
- **任何單一「Spread IV」**：上一輪 §5.3 ill-defined＋SAS 腳注 3
  的單調性紅線（§7.1）＋§0 約束明文禁止。
- **spread debit 自身 percentile 當 IV 指標**：上一輪 §4.d——量到
  的主要是 spot 與 DTE；標籤紀律已裁示。
- **RNHD／SAS 全套自建（第一階段）**：§7.3——需歷史報酬分佈＋
  entropy 最小化＋全鏈定價，成本與方案四的簡化版差一個量級，
  邊際資訊增量對本產品使用者不成比例。
- **CBOE SKEW 式全 smile 第三動差**：§5.5——綁不到 candidate、
  tenor 錯配。

## 14. 明確不涵蓋

- vendor 選型與價格（平行研究 `historical-options-iv-data-sources.md`；
  本文僅引用其形狀結論）
- Long Call vs Spread 的 ROI／結構比較（需求方保留 Grill C）
- 跨劇本比較維度（Grill D）
- UI 實作細節（本文只到 §12.5 的欄位層）
- 任何會改變 ranking／filter／candidate selection 的口徑變更（§0
  紅線；如要做屬另案裁示）

## 15. 查證限制（未能查證的事項）

1. **三份一手 PDF 均取自第三方 GitHub 鏡像**（§1）：SAS 取自
   `colejhudson/goldman-sachs-quantitative-strategies-research-notes`、
   Natenberg 1994 掃描本取自 `hemraj4684/Imp-Books`、Gatheral 2006
   取自 `PlamenStilyianov/Quant`。內容與 emanuelderman.com 官方連結
   同名文件、版式為原版（GS QSRN 版式／McGraw-Hill 掃描／Wiley 排版），
   但**無法對發行方原站做 byte-level 核對**（原站均被擋）。引用段落
   均為逐字轉錄，頁碼以 PDF 內印刷頁碼為準。
2. **Mixon (2011) 的推薦度量與論證**：原文 PDF（ivolatility.com 掛載）
   被擋，`(σ_25Δp−σ_25Δc)/σ_50Δ` 公式與「most descriptive and least
   redundant」結論為索引轉述（多來源交叉一致）。
3. **Reiswich & Wystup 的 RR／BF 逐字定義與 delta 慣例細節**：
   mathfinance.com PDF 被擋，§6.1 為索引轉述（上一輪 §7 第 7 項
   同型留保）。
4. **Bennett《Trading Volatility》逐字**：官方免費 PDF
   （trading-volatility.com）與已知鏡像均被擋；「skew × √T 為常數」
   與 skew 度量分類為索引轉述。
5. **Sinclair《Positional Option Trading》逐字**：50Δ/20Δ put spread
   段落取自第三方書評轉述〔二手〕，未核對原書頁面。
6. **Goyal–Saretto 與 Vasquez 的精確數字**：JFE 卷期頁碼與「月均毛
   報酬 27.1%」等為索引轉述，未核對原文；本文只依賴其「系統性 vol
   RV 排序存在且有效」的定性結論。
7. **CBOE SKEW 白皮書公式細節**：`SKEW = 100 − 10·S` 與 30 天內插
   為索引轉述（whitepaper PDF 被擋）。
8. **ORATS constant-maturity delta-level IV 的欄位名與網格細節**：
   「5/25/50/75/95 call delta × 10–365 天、ex-earnings 版本、2007
   起」為官方 blog／文件索引轉述；確切 API 欄位命名未核對原件。
   SpiderRock／Vola Dynamics／Bloomberg VCA 的功能描述同為索引轉述。
9. **「沒有 vendor 提供 per-candidate SAS／edge 歷史 percentile
   現成產品」是檢索性結論**（absence of evidence；§7.3、§12.4），
   不能排除某家機構級產品有此欄位。
10. **Spectra Markets 的 RR z-score lookback 慣例（1M/6M）**：二手
    教材轉述，非銀行內部規範原件。
11. **tlt_report.md 輸入的捨入殘差**：報告顯示 IV 為整數百分比，
    據此重算的賣腿 vega（0.30）與報告顯示（0.29）差一末位；§11
    全部數字以「報告顯示值為輸入」的口徑自洽，已在 §11.1 標注。
12. **√t 漂移外推（§4.2.1 表）是規律外推不是量測**：假設 surface
    在 normalized 座標下形狀凍結；真實序列的漂移幅度會疊加 vol
    環境變化，表中數字僅示意混淆的量級與方向。

## 16. 來源清單

**標記說明**：〔一手・逐字〕＝PDF 原文逐字檢視（本輪新增級別）；
〔官方・索引轉述〕＝發布者官方頁面，僅索引摘錄；〔二手・索引轉述〕
＝第三方整理。自行推導與引擎實算在正文逐處標明。

一手 PDF（經 GitHub 鏡像取得，見 §15 第 1 項）
- 〔一手・逐字〕Zou, J. & Derman, E., *Strike-Adjusted Spread: A New
  Metric For Estimating The Value Of Equity Options*, Goldman Sachs
  Quantitative Strategies Research Notes, July 1999——鏡像
  [colejhudson/goldman-sachs-quantitative-strategies-research-notes](https://github.com/colejhudson/goldman-sachs-quantitative-strategies-research-notes)；
  官方連結（被擋）[emanuelderman.com](https://emanuelderman.com/wp-content/uploads/1999/07/strike_adjusted_spread.pdf)；
  [SSRN abstract 170629](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=170629)
- 〔一手・逐字〕Natenberg, S., *Option Volatility and Pricing:
  Advanced Trading Strategies and Techniques*, McGraw-Hill, 1994——
  Ch. 10 pp. 204–209、Ch. 18 pp. 409–415；鏡像
  [hemraj4684/Imp-Books](https://github.com/hemraj4684/Imp-Books)
- 〔一手・逐字〕Gatheral, J., *The Volatility Surface: A
  Practitioner's Guide*, Wiley, 2006——Ch. 3「Another Digression:
  The SVI Parameterization」；鏡像
  [PlamenStilyianov/Quant](https://github.com/PlamenStilyianov/Quant)

Skew 度量與參數化
- 〔官方・索引轉述〕[Mixon, S., “What Does Implied Volatility Skew Measure?”, Journal of Derivatives 18(4), 2011](https://jod.pm-research.com/content/18/4/9.abstract)；[SSRN 1618602](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1618602)
- 〔官方・索引轉述〕[Gatheral, J. & Jacquier, A., “Arbitrage-free SVI volatility surfaces”, Quantitative Finance 14(1), 2014（arXiv:1204.0646）](https://arxiv.org/abs/1204.0646)
- 〔二手・索引轉述〕Bennett, C., *Trading Volatility: Correlation,
  Term Structure and Skew*, 2014——官方免費下載頁（被擋）
  [trading-volatility.com](https://www.trading-volatility.com/downloads.html)；
  筆記轉述 [moontowermeta.com](https://moontowermeta.com/notes-on-trading-volatility-correlation-term-structure-and-skew/)
- 〔官方・索引轉述〕[Cboe SKEW Index whitepaper (2011)](https://cdn.cboe.com/resources/indices/documents/SKEWwhitepaperjan2011.pdf)（被擋）；〔二手〕[Wikipedia: SKEW](https://en.wikipedia.org/wiki/SKEW)

FX Risk Reversal 慣例與實務
- 〔官方・索引轉述〕[Reiswich, D. & Wystup, U., “FX Volatility Smile Construction”, CPQF Working Paper No. 20](https://www.mathfinance.com/wp-content/uploads/2025/04/FXVolatility-Smile-Construction_CPQF_Arbeits20_neu2.pdf)（被擋）
- 〔二手・索引轉述〕[Spectra Markets — How to trade the positioning report（RR z-score 1M/6M lookback 實務）](https://www.spectramarkets.com/amfx/sfxpm-explainer/)
- 〔二手・索引轉述〕[Convex — FX Risk Reversal Explained](https://convextrade.com/glossary/risk-reversal-skew)

Desk 教科書與交易實務（一手以外）
- 〔二手・索引轉述〕Sinclair, E., *Positional Option Trading*, Wiley
  2020——[Robot Wealth 書評（50Δ/20Δ put spread 段落）](https://robotwealth.com/positional-option-trading-by-euan-sinclair-a-review/)

學術 relative-value 文獻
- 〔官方・索引轉述〕[Goyal, A. & Saretto, A., “Cross-section of option returns and volatility”, Journal of Financial Economics 94 (2009) 310–326](https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001251)
- 〔官方・索引轉述〕[Vasquez, A., “Equity Volatility Term Structures and the Cross-Section of Option Returns”, JFQA（SSRN 1944298）](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1944298)

Vendor analytics（surface、edge、constant-maturity 序列）
- 〔官方・索引轉述〕[ORATS — Our Most Popular IV is Constant Maturity Implied Volatility](https://orats.com/blog/our-most-popular-iv-is-constant-maturity-implied-volatility.-how-we-calculate-it)、[Implied Volatility Term Structure and Interpolated IVs](https://orats.com/blog/implied-volatility-term-structure-and-interpolated-ivs)、[Important New Data Added To The ORATS API](https://orats.com/blog/important-new-data-added-to-the-orats-api)、[How To Find The Best Options Trade Using Theoretical Values（S%）](https://orats.com/blog/how-to-find-the-best-options-trade-using-theoretical-values)、[Option Scanner](https://orats.com/option-scanner)
- 〔官方・索引轉述〕[SpiderRock — Live Volatility Surfaces](https://docs.spiderrockconnect.com/docs/next/Documentation/PlatformFeatures/Analytics/LiveVolSurfaces/)、[Historical Volatility Surface Datasets](https://spiderrock.net/data/historical-data-analytics/volatility-surfaces/)
- 〔官方・索引轉述〕[Vola Dynamics — Use Cases](https://voladynamics.com/use-cases/)
- 〔官方・索引轉述〕[Bloomberg — Navigating derivatives market sentiment with volatility and correlation analysis（VCA）](https://www.bloomberg.com/professional/insights/trading/navigating-derivatives-market-sentiment-with-volatility-and-correlation-analysis/)

本 repo（引擎、資料與既有研究）
- `option_chaser/valuation.py` —— `bs_call`／`call_greeks`／
  `days_between`（§4、§11 全部實算）
- `tlt_report.md`（commit `8625fad`）—— §11 輸入的真實 TLT LEAPS
  報價與 IV
- `docs/research/iv-relative-history-methodology.md` —— 上一輪全文
  （本文的 §3.1/§3.3/§3.4/§4/§5 編號引用皆指向它）
- `docs/research/historical-options-iv-data-sources.md` —— 資料源
  約束與交集候選（§12 各案「資料」欄的對照對象）
- `docs/research/option-liquidity-filtering.md` §3.2/§6.5 —— LEAPS
  報價義務、Cboe `theo` 獨立性
- `docs/research/cboe-field-semantics.md` §2.2 —— Cboe `iv` 為含
  股利美式二項樹口徑（§7.4 警告的依據）
- `docs/research/option-strategy-report-conventions.md` §7 ——
  標記體系與「結論先行」版型慣例
