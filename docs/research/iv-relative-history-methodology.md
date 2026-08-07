# 「IV 現在算貴還是便宜」的成熟做法——相對歷史 IV 判讀方法論調查

研究日期：2026-08-07。需求背景：Option Chaser 想加「這組 debit vertical spread
現在進場，IV 環境算貴還是便宜？」的相對歷史判讀。本文回答需求方界定的七個
問題（四種歷史比較基準的實務評價、spread 層級的定義選項、能不能平均兩腿 IV
的數學、以及給需求方裁示用的候選方案清單）。

**範圍界線（三條，皆需求方明示）**：

1. **不選資料 vendor**。「歷史 IV 資料哪裡買／哪裡抓」是平行研究
   `historical-options-iv-data-sources.md` 的範圍，本文對資料只用抽象語言
   描述形狀與量級（如「標的層級 constant-maturity IV 日序列一年」）。
2. **不涵蓋 Long Call vs Spread 比較**（另案）。
3. **不涵蓋跨劇本比較維度**（需求方保留為後續獨立討論）。

**與現行引擎的關係**：本產品估值口徑見 `option_chaser/valuation.py`
（Black-Scholes、stdlib math）與 `option_chaser/ranking.py`（主排名數字＝
最差成交口徑，附錄 A14.2）；引擎已有的 IV 機制是 `AnalysisParams.iv_shifts`
（`models.py:65`，預設 ±20% 情境擾動）——那回答的是「**如果** IV 變了會怎樣」，
本文要補的是「**現在的** IV 相對它自己的歷史站在哪裡」，兩者互補不重疊。
前端零金融計算的分層原則（spec #47）沿用：本文所有候選方案的計算都落在
Python 引擎側。

## 0. 取材限制聲明

本沙箱出口 proxy 的封鎖狀態與前兩份研究（`option-liquidity-filtering.md`、
`option-strategy-report-conventions.md`）相同，本次逐一實測：

- **WebFetch 對一般外部網域一律被擋**（`EGRESS_BLOCKED`）。實測遭拒：
  `support.tastytrade.com`、`www.tastylive.com`、`cdn.cboe.com`、
  `pricing.online.fr`（Derman 1999 PDF 的公開鏡像）。
- **`raw.githubusercontent.com` 可達**（實測 200），但本題是方法論調查，
  GitHub 上沒有可替代官方方法論文件的一手 payload，故本文未像
  `option-liquidity-filtering.md` 那樣取得可逐筆重算的外部實測資料。
- 因此**所有外部事實聲明均為搜尋索引轉述**，沿用既有三級標示：
  **〔索引轉述〕**（索引摘錄取得、未逐字核對原文）、
  **〔索引轉述・近逐字〕**（索引摘錄中出現近似逐字片段）。
  未能以任何方式確認者列入 §7「未能查證的事項」。
- **唯一的例外是 §5**：能不能平均兩腿 IV 的數學是**自行推導**，並用本 repo
  自己的 `valuation.bs_call`／`call_greeks`（stdlib、可重現）**數值驗算**，
  不依賴任何外部轉述——這一節的可信度不受 403 影響。

## 1. 結論摘要（七問七答）

1. **同一 OCC 合約自己的 1Y IV percentile：不成立，沒有主流平台這樣做。**
   固定合約的序列同時混入三種非 IV-環境訊號：DTE 每天遞減把 term structure
   的 roll-down 混進來（常態 contango 下，固定到期日的 IV 會單純因為時間
   流逝而下滑，§3.1）；spot 移動使該合約在 skew 上的位置漂移（sticky-strike
   ／sticky-delta 文獻的核心議題，§2.3）；遠月合約上市不滿一年、早期無流動
   性，序列殘缺——本產品主戰場正是 LEAPS，這一條打擊最重（§3.1.3）。
2. **同 expiry＋相近 strike 往回看：比方法一少一種混淆，仍不成立。**
   strike 固定消掉一部分 moneyness 漂移（僅在 sticky-strike 視角下成立），
   但 DTE 遞減的 term-structure 滑動原封不動，且排程事件（FOMC／CPI；個股
   則是 earnings）進出該到期日的覆蓋窗會造成階梯跳動——ORATS 甚至專門把
   earnings effect 從逐月 IV 解出來再談歷史可比性（§3.2）。
3. **同 DTE＋同 delta 的 surface 取點：學術與專業資料商的標準做法。**
   OptionMetrics IvyDB 的 standardized options（kernel-smoothed，到期
   10–730 天 × delta 0.10–0.90 網格）就是為此而生，是學術實證的事實標準；
   ORATS 提供 10–365 天 × 4 個 delta 的內插 IV；FX 市場更是直接以 delta
   為座標報價（25Δ risk reversal／butterfly）。資料要求是「每天一張平滑
   surface」的歷史，是四種方法裡最重的（§3.3）。
4. **Constant-maturity ATM IV 指數的 percentile：業界零售端的絕對主流。**
   VIX（30 天，兩鄰近到期日的 variance 內插）、IVolatility IV Index（每
   到期日 4 張 ATM、delta/vega 加權、√t 內插到 30/60/…天）、IBKR V30
   （每到期日 4 個最近價平 strike 共 8 張、IV 對 strike 擬合拋物線、
   variance 線性內插）、tastytrade IVx（VIX 式逐到期日＋預設 30 天內插）、
   ORATS `atmIvM1`＋`ivRank1y`／`ivPct1y` 全屬此類。IV Rank（對 52 週
   高低點的位置）與 IV Percentile（過去一年有多少交易日低於現值）是兩個
   不同統計量，tastytrade 兩者都給、預設用 Rank；thinkorswim 的欄位**名叫**
   IV Percentile、**算的是** Rank 公式，是有名的命名陷阱（§3.4）。
5. **Spread 層級的「IV 貴/便宜」四種定義各有位置**：(a) 兩腿各自 percentile
   分開呈現最忠實但把合成工作丟給使用者；(b) vega 加權合成在 debit vertical
   上有分母趨零與變號問題，不穩定；(c) surface-relative rich/cheap（ORATS
   smooth edge S%）回答的是**橫斷面**問題（相對今天整條 surface 這兩張貴不貴），
   不是**時間序列**問題（相對歷史現在的環境貴不貴），兩者正交、不可互相
   替代；(d) spread debit 自己的歷史 percentile 幾乎只量到 spot 與 DTE，
   IV 是二階成分，**不是** IV 判讀（§4）。
6. **兩腿 IV 能不能直接平均：一階上就是錯的，但錯多少可以量化。**
   debit vertical 對兩腿 IV 的敏感度是 `+vega₁` 與 `−vega₂`（符號相反）；
   把平行位移與 skew 拆開後，`dV = (vega₁−vega₂)·dσ̄ + ((vega₁+vega₂)/2)·ds`
   ——對 skew 變動的敏感度是**平均 vega**，即使 net vega 歸零它照樣很大，
   簡單平均把 s（兩腿 IV 差＝skew 局部斜率）整項抹掉。且「spread 的單一
   隱含波動率」本身數學上 ill-defined：spread 價格對單一 σ **非單調**
   （本 repo 引擎實算：σ 從 0.05 掃到 2.00，spread 價值先升後降，同一價格
   對應兩個 σ）。簡單平均的誤差 `=(vega₁−vega₂)(σ₁−σ₂)/(2(vega₁+vega₂))`，
   兩腿 strike 很近（vega 相近）或 skew 平坦時可接受（§5）。
7. **給需求方的候選方案共五案**（§6）：A＝標的層級 constant-maturity ATM
   IV 指數 1Y Rank＋Percentile（業界主流形狀，資料最輕）；B＝與劇本天期
   對齊的長 tenor constant-maturity percentile（修正 A 的 30 天 tenor 與
   LEAPS 主戰場的錯配）；C＝兩腿 surface 點各自 percentile＋skew 差
   （最忠實、資料最重）；D＝延伸既有 V9 spread 成本歷史（資料已在手上，
   但誠實標注它不是 IV 判讀）；E＝IV/HV 比值（零歷史 IV 資料需求的
   互補指標，量的是 risk premium 不是歷史位置）。推薦排序 A → E → B →
   C → D，理由見 §6.6——**本文不替需求方做決定**，五案並陳供裁示。

## 2. 基礎名詞：Rank、Percentile、與「算在什麼東西上」

### 2.1 IV Rank 與 IV Percentile 的定義（tastytrade 口徑）

tastytrade Help Center（Volatility Metrics 條目）的定義〔索引轉述・近逐字〕：

- **IV Rank** ＝ `(當前 IV − 52 週 IV 最低值) / (52 週 IV 最高值 − 52 週 IV 最低值)`
  ，表示當前 IV 落在 52 週區間內的位置，0–100%。
- **IV Percentile** ＝ 過去 52 週中「當日 IV 低於當前 IV」的交易日數佔比，
  分母為 252 個交易日。

兩者的行為差異（多個來源交叉一致）〔索引轉述〕：

| | IV Rank | IV Percentile |
|---|---|---|
| 統計量 | 對區間極值的相對位置 | 對整個分布的位置（經驗 CDF） |
| 對極值敏感度 | **高**——一次暴漲把之後一整年的 Rank 都壓低 | 低——一天只是 1/252 |
| 直覺 | 「介於一年最低與最高之間的哪裡」 | 「比過去一年幾 % 的日子貴」 |
| 平台預設 | tastytrade 預設顯示 Rank | Barchart 兩者並列 |

**thinkorswim 的命名陷阱**：thinkorswim 平台上的欄位叫「IV Percentile」，
但 Schwab 官方說明寫的是「shows the day's IV compared to the **high and low
range** for the past 12 months」〔索引轉述・近逐字〕——這是 **Rank 的公式**。
第三方（Hahn-Tech、useThinkScript 社群）明白指出「thinkorswim 用 IV
Percentile 這個詞、實際顯示的值是 IV Rank」〔二手・索引轉述〕。
**教訓：本產品若同時顯示兩個數字，名詞與公式的對應必須寫死在測試裡**
（本 repo 已有 `test_frontend_contract.py` 的字彙漂移防線慣例可沿用）。

### 2.2 這些指標全部算在「標的層級的 IV 指數」上，不是單一合約上

檢視過的每一家（tastytrade、thinkorswim、Barchart、IBKR、ORATS、
IVolatility）的 Rank／Percentile，底層序列都是**標的層級、constant-maturity
的合成 IV 指數**（各家建構法見 §3.4），沒有任何一家把 Rank／Percentile
算在單一 OCC 合約自己的 IV 歷史上〔索引轉述；檢索性結論，見 §7 第 8 項的
留保〕。Barchart 的 per-contract options-history 頁面（Premier）提供單一
合約逐日的 IV **供查看**，但頁面上的 IV Rank／Percentile 欄位仍是標的
層級的〔索引轉述〕。這個一致性不是巧合——單一合約序列的三個結構性問題
見 §3.1，是方法上的，換多少家資料商都解不掉。

### 2.3 Sticky strike vs sticky delta：為什麼「同一張合約」不是可比單位

Derman《Regimes of Volatility》（Goldman Sachs Quantitative Strategies
Research Notes, 1999）提出 volatility surface 隨 spot 移動的三種經驗規則
〔索引轉述〕：

- **sticky strike**：固定 (strike, expiry) 的 IV 不隨 spot 動——趨勢盤整期
  較接近此規則；
- **sticky delta／sticky moneyness**：固定 **moneyness（或 delta）** 的 IV
  不隨 spot 動——spot 動了以後，「同一張合約」的 IV 會因為它在 skew 上的
  位置變了而改變，即使市場的整體 vol 環境完全沒變；
- **sticky implied tree**：恐慌期較接近。

Daglish–Hull–Suo（2007,《Volatility Surfaces: Theory, Rules of Thumb, and
Empirical Evidence》）對這些規則做了理論與實證檢驗〔索引轉述〕；FX 市場
的 surface 建構慣例整個建立在 sticky delta 上——市場直接以 ATM＋25Δ risk
reversal＋25Δ butterfly（delta 座標）報整條 smile〔索引轉述〕。

**對本文的意義**：市場沒有一致遵循 sticky strike（只有它成立時「固定合約」
才勉強是可比單位），而專業界建 surface 用 delta 座標，正說明**業界共識的
可比單位是 (DTE, delta)，不是 (contract)**。這是 §3.3／§3.4 方法的理論根基。

## 3. 四種歷史比較基準逐一評述（問題 1–4）

### 3.1 方法一：同一 OCC 合約自己的 1Y IV percentile（問題 1）

做法：取同一張合約（如 `TLT280519C00100000`）過去一年每天收盤的 IV，
算當前 IV 在其中的 percentile。**三個根本問題，每個都不是資料品質問題、
是這個序列在量測上就不是同一個東西**：

**3.1.1 DTE 每天遞減——term structure 的 roll-down 混進訊號。**
IV term structure 在平靜市場常態是向上傾斜（contango：遠月 IV > 近月 IV），
壓力期倒掛（backwardation）〔索引轉述，多來源一致〕。固定到期日的合約
每天沿著這條曲線往近端滑：**即使整條 term structure 一天都沒動、市場的
vol 環境毫無變化，這張合約的 IV 也會單純因為 DTE 從 500 天變成 250 天而
系統性下降**（contango 下）。一年前的「DTE=650 的它」與今天的「DTE=285
的它」根本是曲線上兩個不同的點，percentile 把兩者當同一個隨機變數的觀測，
是類別錯誤。對本產品傷害具體化：劇本天期以年計，一年的持有期會讓 DTE
橫跨 term structure 斜率明顯不同的區段（遠端平、近端陡），越接近到期
這個偏差越大。

**3.1.2 Spot 移動——skew 混進訊號。**
固定 strike、spot 從 88 漲到 105，這張 K=100 call 從 OTM 變成近 ATM——
在 sticky-delta（市場常態之一，§2.3）下，它的 IV 會沿著 skew 移動。
本產品的使用情境放大了這個問題：劇本本來就在賭 +20%～+40% 的大漲，
**劇本越接近成立、合約的 moneyness 漂得越遠**，「IV percentile 變了」
到底是 vol 環境變了還是劇本走到一半，無法區分。

**3.1.3 上市不滿一年——遠月合約沒有歷史。**
目標年月在兩年後的 LEAPS，一年前可能剛掛牌或根本未掛牌；即使掛了，
早期報價稀疏（Cboe 做市商連續報價義務只涵蓋九個月內的序列，LEAPS 報價
是自願的——見 `option-liquidity-filtering.md` §3.2 的既有調查）。序列
要嘛不存在、要嘛前半段全是 stale 報價反推的 IV。**本產品主戰場正是
LEAPS，這一條在本產品上是致命的**。

**誰在用**：本次檢索**沒有找到任何主流平台**以單一合約自身歷史做
Rank／Percentile（§2.2；檢索性結論的留保見 §7）。

**唯一的適用情境**：合約已接近到期（DTE 小、變動慢）、spot 穩定、且只
回看很短的窗（幾天）——此時三個混淆都小。但那已經不是「一年 percentile」
這個題目了。

### 3.2 方法二：同 expiry＋相近 strike/moneyness 的歷史 IV（問題 2）

做法：固定到期日（如 2028-05-19 那期），往回看該期 ATM 或某 moneyness
帶的 IV 歷史。相對方法一的變化：

- **修掉的**：若同時把「相近 strike」動態選成當天的 ATM（而非固定
  strike），moneyness 漂移可大幅消除；
- **沒修掉的**：**DTE 遞減原封不動**——「同 expiry」就是「固定日曆日」，
  今天它是 DTE=650、一年後它是 DTE=285，term-structure 滑動照樣混入
  （§3.1.1 的論證逐字適用）；上市不滿一年的問題也原封不動。
- **新增的麻煩——事件進出覆蓋窗**：排程事件（個股 earnings；TLT 這類
  利率商品則是 FOMC、CPI、再融資公告）被市場定價在**涵蓋該事件的到期日**
  的 IV 裡。固定到期日往回看，事件一個個「進入」它的覆蓋窗，IV 序列出現
  與 vol 環境無關的階梯。ORATS 對這件事的處理是專門解出 implied earnings
  effect、提供 ex-earnings IV，才敢談逐月 IV 的歷史可比性〔索引轉述〕
  ——反面印證了原始的固定 expiry 序列不可直接比。TLT 沒有 earnings，
  macro 事件對長天期 IV 的階梯幅度較小，但機制相同。

**誰在用**：tastytrade 的 IVx 逐到期日顯示（VIX 式計算套在單一到期日上）
〔索引轉述〕是「**當下**逐期快照」的呈現——用來看今天的 term structure
哪一期被抬高（如 earnings 期），**不是**拿單一到期日自己的歷史算
percentile。本次檢索同樣沒有找到以固定到期日歷史做 Rank／Percentile 的
主流實作。

**判定**：比方法一少一種混淆，但致命傷（DTE 遞減、歷史殘缺）都還在。
不建議。

### 3.3 方法三：同 DTE＋同 delta/moneyness 的歷史 surface 取點（問題 3）

做法：每一個歷史交易日，在**當天的** surface 上取「DTE=N、delta=D」
那一點（通常要對 expiry 與 strike 兩個維度內插），構成 (DTE, delta) 固定
的可比序列，再對它算 percentile。這把 §3.1 的三個混淆全部消掉：DTE 恆為
N、moneyness 座標恆為 D、序列永續（不隨任何一張合約上市／到期而生滅）。

**誰在用（這是學術與專業端的標準做法）**：

- **OptionMetrics IvyDB**（學術實證的事實標準資料庫）：每檔標的每天算一份
  kernel-smoothed 的 standardized volatility surface，到期 10／30／60／91
  ／122／152／182／273／365／547／730 日 × delta 0.10–0.90（間隔 0.05，
  put 為負）網格〔索引轉述〕。學術論文（如 Springer《Implied volatility
  surfaces: a comprehensive analysis using half a billion option prices》）
  直接消費這份網格〔索引轉述〕。
- **ORATS**：SMV 平滑系統（清洗報價 → put-call parity 解 residual yield →
  對 strike IV 擬合無套利平滑曲線）之上，提供 10–365 天 × 4 個 delta 的
  內插 IV，surface 以 (DTE, delta) 為自變數明文定義〔索引轉述〕。
- **FX 市場**：整個報價體系就是 (tenor, delta) 座標（ATM＋25Δ RR＋25Δ BF
  逐 tenor），sticky delta 是市場建構慣例〔索引轉述〕。

**資料要求（抽象描述）**：每天一份「全鏈 EOD 快照＋平滑內插」的產出，
或直接取得 vendor 已算好的 surface 網格歷史。量級：一檔標的一年 ≈ 252 天
×（11 tenor × 17 delta ≈ 187 點）≈ 4.7 萬個浮點數——單檔標的其實不大，
**重的不是儲存、是每天要有人把平滑做對**（清洗、無套利、內插的整套
工程，正是 ORATS／OptionMetrics 的產品本體）。自建的話等於把 SMV 系統
重寫一遍；買現成的則是 vendor 選擇問題（平行研究範圍）。

**判定**：方法論上最正確的「逐腿」歷史基準；成本在資料工程。它是 §4(a)
／§4(c) 與候選方案 C 的前置。

### 3.4 方法四：constant-maturity ATM IV 指數的 percentile（問題 4）

方法三取「任意 (DTE, delta) 點」；方法四是它的退化特例——只取 **ATM 一條
線上的固定 tenor 點**（最常見 30 天），把整個 surface 壓成標的層級的單一
數字，再對這個數字算 Rank／Percentile。這正是 §2.2 所述所有零售平台
實際在做的事。各家建構法：

| 家 | 指數 | 建構方法（皆〔索引轉述〕） |
|---|---|---|
| Cboe | **VIX** | model-free：取 23–37 天的兩個 SPX 到期日，各自從全帶 OTM 報價算 expected variance，再對**總 variance 做時間線性內插**到恰好 30 天，開根號 ×100。權重以分鐘計。這是「constant maturity 內插」的祖形 |
| IVolatility | **IV Index（IVX）** | 每個到期日取 4 張 ATM 合約，以 delta／vega 專有加權解出該期 IV，再對兩鄰近到期日**依 √t 線性內插**正規化到 30/60/90/…/720 天固定 tenor。1998 年推出 |
| IBKR | **V30** | 第一個「至少還有 8 個日曆日」的到期月起，每期取 4 個最接近市場價的 strike 共 8 張合約，IV 對 strike **擬合拋物線**、取期望期貨價位處的值當該期 ATM IV，再對兩期的 **variance 線性內插**（必要時外插）到 30 天，開根號 |
| tastytrade | **IVx** | 「VIX 式計算逐到期日各算一個」；watchlist／positions 預設顯示 30 天值，**由兩個最鄰近到期日內插** |
| ORATS | **atmIvM1…M4 ＋ ivRank1m/ivPct1m/ivRank1y/ivPct1y** | SMV 平滑後的逐月 ATM IV 與 constant-maturity 內插值；**Rank 與 Percentile 兩種統計量、1 月與 1 年兩種窗，四個欄位全提供**（API 實例值如 `ivRank1y: 44.49, ivPct1y: 40.08`） |
| Barchart | ATM 平均 IV | 「ATM average IV relative to the highest/lowest values over the past 1-year」為 Rank；「% of days where IV closed below current」為 Percentile |

**為什麼這是業界主流**（歸納自上表的共性）：

1. **可比性**：固定 (tenor=30d, ATM) 錨點，序列裡每個點量的是同一個東西
   ——§3.1 三個混淆全部按定義消失；
2. **序列永續**：指數不隨個別合約生滅，一年、五年的窗都取得到；
3. **單一數字**：能做成 watchlist 欄位、能下 screener 條件、能對一般
   使用者說「TLT 的選擇權現在整體偏貴」——溝通成本最低；
4. **與交易慣例掛勾**：tastytrade 系的教學慣例是以標的層級 IVR 決定
   策略型態——IVR 低（常見門檻 <30）時偏好 debit spread 等淨買方策略、
   IVR 高時偏好賣方策略〔二手・索引轉述，多來源一致；tastytrade 官方
   原文未逐字核對，見 §7〕。**這正是本產品要回答的那個問題的業界標準
   回答形狀**：debit vertical 的「IV 環境」判讀，業界慣例就是看標的
   層級的 constant-maturity IVR，而不是看兩腿各自的 IV（原因見 §4 末段
   與 §5 的數學——兩腿 IV 高度共動，spread 對整體水位的敏感度由 net
   vega 決定）。

**侷限（對本產品特別要緊）**：30 天 tenor 與本產品 LEAPS 主戰場（DTE
數百天）的錯配。term structure 近端波動遠大於遠端（近端受事件與短期
恐慌驅動，遠端由長期均值回歸預期釘住）——30 天指數的 Rank 會**誇大**
LEAPS 實際面對的 vol 環境起伏。緩解：加一條長 tenor（如 365 天
constant-maturity）並列，或直接用候選方案 B（§6.2）。ORATS 的欄位
設計（1 月窗與 1 年窗並列）也反映了「單一窗不夠用」的同一認知。

## 4. Vertical spread 的「IV 貴/便宜」四種定義（問題 5）

前提：debit vertical（本產品：bull call spread 為主）買 K₁ call、賣 K₂
call（K₁<K₂），淨支出 debit。四種定義逐一評述；數學細節統一放 §5。

### 4.a 兩腿各自 percentile，分開呈現

- **做法**：對每腿取 §3.3 的 (DTE, delta) 對應點歷史，各算一個 percentile，
  並排顯示「買腿 IV 位於其歷史第 X 百分位／賣腿第 Y 百分位」。
- **誰在用**：沒有找到任何平台把「進場判讀」做成這個形狀〔檢索性結論〕。
  平台顯示的是兩腿**當下** IV（本 repo `report.py:386-387` 已比照顯示）＋
  標的層級一個 IVR。
- **優點**：資訊最完整、不做任何有損合成；兩個 percentile 的**差**還額外
  攜帶 skew 相對歷史的資訊（X≫Y ＝ 買腿相對貴、skew 對這個結構不利）。
- **缺點**：合成判斷丟給使用者——本產品使用者不是 quant，「買腿 62 百分位、
  賣腿 41 百分位，所以呢？」沒有自明的答案；兩個數字可能指向相反結論。
- **資料要求**：surface 歷史（同 §3.3，最重）。

### 4.b Vega-weighted 合成 measure

- **做法**：以各腿 vega 為權重把兩腿 percentile（或 IV）合成單一數字。
- **誰在用**：vega 加權在「同向籃子」上是成熟做法——IVolatility 的 IV
  Index 就是以 vega 加權合成每期 4 張 ATM 合約〔索引轉述〕；組合層級的
  net vega 是所有平台風險頁的標配。但**把對沖結構（一多一空）做成
  vega-weighted 的『spread IV percentile』，沒有找到先例**〔檢索性結論〕。
- **致命問題（§5 推導）**：debit vertical 的權重天生是 `+vega₁` 與
  `−vega₂`——分母 `vega₁−vega₂` 會隨 spot 穿越兩 strike 之間而**趨零並
  變號**（本 repo 引擎實算：S=88 時 net vega +0.228，S=105 時 −0.068，
  S=118 時 −0.262）。分母趨零時加權平均爆炸，變號時「貴/便宜」的方向
  整個翻面。**做成常駐指標必然在某些劇本狀態下輸出垃圾。**
- **判定**：不建議作為單一輸出；net vega 本身（含符號）倒是值得顯示——
  它告訴使用者「你這組現在到底是買 vol 還是賣 vol」（§5.2）。

### 4.c Surface-relative rich/cheap（逐腿對平滑 surface 的殘差）

- **做法**：每腿市場報價與「整條鏈擬合出的平滑 surface」理論值的差距。
- **誰在用**：ORATS 的 **smoothed edge（S%）**——SMV 平滑值與成交價的
  距離，是其 options scanner 的核心欄位之一〔索引轉述〕。Cboe delayed
  quotes 附的 `theo` 欄位（Hanweck 曲面擬合值）是同一思想的免費版——
  本 repo 前次研究已實測過它與 mid 的獨立性
  （`option-liquidity-filtering.md` §6.5）。
- **關鍵界定**：這回答的是**橫斷面（cross-sectional）**問題——「相對
  **今天**同一標的的其他合約，這兩張的報價偏貴還是偏便宜」（挑 strike
  ／挑合約用），**不是**需求方問的**時間序列**問題——「相對**歷史**，
  現在進場的 vol 環境貴不貴」（挑時機用）。兩者正交：整條 surface 可以
  處於歷史高位（時間序列貴）而你挑的兩張相對 surface 便宜（橫斷面便宜），
  反之亦然。**產品上不可把 (c) 當成問題的答案，但它是有價值的另一題**
  ——且與本 repo 既有的最差成交口徑互補（成本已誠實算最差，殘差再告訴
  你這個最差價本身偏不偏）。
- **資料要求**：只要**當天**全鏈＋一套平滑擬合（無需任何歷史）——資料
  最輕，工程在擬合本身。

### 4.d Spread debit 對自己歷史的 percentile

- **做法**：直接量「同一組 spread 的淨成本」相對它自己的歷史序列。
- **誰在用**：thinkorswim 可用 comparison study 畫兩腿差價的歷史圖
  （`.SPXW…P4480-.SPXW…P4470` 這種合成符號，取**成交價**）〔二手・索引
  轉述〕——是「查看」工具，非 percentile 指標。**本 repo 已有同款**：
  `store.spread_cost_history()`（V9／#57，依 Spread 身份鍵跨快照聚合、
  斷點不插值）。
- **問題**：固定兩張合約的 debit 序列，混淆比 §3.1 還嚴重——debit 的
  逐日變動由 delta（spot 移動）主導，theta（DTE 遞減）次之，vega（IV
  環境）在多數狀態是**二階成分**。「debit 位於歷史第 90 百分位」幾乎
  等於「標的漲了」，跟 IV 環境貴賤基本無關。要把 vol 成分剝出來就得
  對每個歷史點做 model-based 歸因（用當日 spot／DTE 重新定價、取殘差）
  ——等於繞回 surface 歷史，且變成 model-dependent。
- **判定**：作為「這組結構的成本走勢」的誠實呈現（本 repo 已出貨）有
  價值；**作為 IV 判讀是錯誤標籤**，兩者在 UI 上必須分清楚。

### 4.e 補記：那 debit vertical 的「IV 環境」到底該掛在哪一層？

業界慣例的答案很一致：**掛在標的層級**（§3.4 第 4 點——IVR 低買 debit
spread 的 tasty 系慣例、Fidelity/Barchart screener 的 IVR 欄位全是標的
層級）。理由正是 §5 的數學：兩腿 IV 對整體水位的變動高度共動，spread
對平行位移的淨敏感度（net vega）比單腿小一個量級，**「環境貴/便宜」的
第一階資訊在標的層級就已經決定**；spread 特有的部分（skew）是第二階
修飾，屬 (a)／(c) 的範圍。這個分層與本產品「主數字誠實、細節分層揭露」
的既有哲學（附錄 A14.2、FB5 系列的品質標示）同構。

## 5. 能不能直接平均兩腿 IV（問題 6）——自行推導＋引擎數值驗算

本節不依賴任何外部轉述。記號：spread 價值
`V(σ₁,σ₂) = C(K₁,σ₁) − C(K₂,σ₂)`（同到期日 T、同 spot S、同 r；C 為
BS call 價格），`vega_i = ∂C(K_i)/∂σ_i > 0`。

### 5.1 一階敏感度：兩腿符號相反，平均權重是錯的

對兩腿 IV 各自微擾：

```
dV = vega₁·dσ₁ − vega₂·dσ₂
```

把兩腿 IV 改寫成「平均水位＋skew 差」：`σ̄ = (σ₁+σ₂)/2`、`s = σ₁−σ₂`
（同 expiry 相鄰 strike 的 IV 差＝skew 的局部斜率×strike 距），
即 `σ₁ = σ̄ + s/2`、`σ₂ = σ̄ − s/2`，代入得**本節的核心分解**：

```
dV = (vega₁ − vega₂)·dσ̄  +  ½(vega₁ + vega₂)·ds
      └── net vega ──┘        └── 平均 vega ──┘
      對「整體水位」敏感度      對「skew」敏感度
```

兩個立即結論：

1. **對整體水位（dσ̄）的敏感度是 net vega（差）**，不是平均——簡單平均
   兩腿 IV 隱含的權重是 (½, ½)，正確權重是 (+vega₁, −vega₂)，**第二腿
   符號就是錯的**。
2. **對 skew（ds）的敏感度是平均 vega（和的一半）——它不隨對沖縮小**。
   即使 net vega 剛好為零（spread 對整體水位免疫），skew 一動照樣以
   全額平均 vega 打在 P&L 上。**簡單平均 `(σ₁+σ₂)/2` 把 s 這一項整個
   消掉——被抹掉的恰恰是 spread 特有的 vol 曝險。**

### 5.2 數值驗算（本 repo `valuation.call_greeks`，可重現）

TLT 型例子：S=88、K₁=100（買）、K₂=120（賣）、T=1.5 年、r=4%、
σ₁=0.17、σ₂=0.15（s=0.02）。`vega_per_pct` 為每 1 IV 百分點的美元 vega：

| spot | vega₁(K=100) | vega₂(K=120) | **net vega** | 平均 vega |
|---|---|---|---|---|
| 88（兩腿 OTM，本產品典型進場態） | 0.4195 | 0.1920 | **+0.2275** | 0.3058 |
| 105（spot 進入兩 strike 之間） | 0.4216 | 0.4892 | **−0.0676** | 0.4554 |
| 118（貼近賣腿） | 0.2849 | 0.5465 | **−0.2616** | 0.4157 |
| 130（整組深 ITM） | 0.1622 | 0.4410 | **−0.2789** | 0.3016 |

判讀：

- **進場態（S=88）**：net vega ＝平均 vega 的 74%——此時這組 spread
  是**實質的買 vol 部位**，「IV 環境貴/便宜」對它是真問題，且方向與
  單腿相同（環境便宜＝對進場有利）。這支持 §4.e：進場判讀掛標的層級
  水位，方向正確。
- **劇本走到一半（S=105）**：net vega 縮到平均 vega 的 15% 且**變號**
  ——vega-weighted 合成（§4.b）的分母正是這個會穿零的量，指標在使用者
  劇本進行中會先爆炸再翻面。
- **skew 敏感度恆大**：四個 spot 下平均 vega 都在 0.30–0.46，從不歸零
  ——skew 變動的曝險永遠在，而簡單平均永遠看不見它。

### 5.3 「spread 的單一隱含波動率」本身 ill-defined

單腿 IV 之所以 well-defined，是因為 BS 價格對 σ 嚴格單調。spread 沒有
這個性質——`V(σ,σ)`（兩腿同 σ）對 σ **非單調**：σ→0 時兩腿都趨內在值
（OTM spread → 0）；σ→∞ 時兩張 call 都趨 S，差趨 0；中間有峰。
本 repo 引擎實算（`valuation.bs_call`，S=88、K 100/120、T=1.5、r=4%）：

```
σ     0.05   0.10   0.15   0.20   0.30   0.50   0.80   1.20   2.00
V     0.377  1.931  3.298  4.182  5.055  5.367  4.832  3.753  1.854
```

峰在 σ≈0.5 附近。**峰值以下的任何市場 debit 都對應兩個 σ 解**（如
V≈3.75 同時解在 σ≈0.18 與 σ=1.20）——「這組 spread 的隱含波動率」
沒有唯一定義，任何試圖給 spread 一個「單一 IV」再對它做歷史 percentile
的設計，在數學上就站不住。這是 (b)／(d) 類方案共同的深層障礙。

### 5.4 誠實的另一半：簡單平均什麼時候誤差可接受

簡單平均與 vega 加權平均（同向權重版 `σ_w = (vega₁σ₁+vega₂σ₂)/(vega₁+vega₂)`）
的差為：

```
σ̄ − σ_w = −(vega₁ − vega₂)(σ₁ − σ₂) / (2(vega₁ + vega₂))
```

（上例實算：−0.0037，即 0.37 IV 百分點，公式與直算吻合。）誤差在
**兩種情境下趨小**：

1. **兩腿 strike 很近**（vega₁≈vega₂）：窄 spread 兩腿在 surface 上是
   鄰點，vega 相近、s 也小——此時 `(σ₁+σ₂)/2` 當「這一小段 surface 的
   水位」的描述性統計是可以的；
2. **skew 平坦**（σ₁≈σ₂）：s≈0 時抹掉 s 沒有損失。

但要分清楚：即使在這兩種情境下，簡單平均也只是「**描述**兩腿附近的
surface 水位」的合理近似，**仍然不是**「spread 對 vol 的敏感度」——
後者永遠由 §5.1 的分解決定（水位項用 net vega、skew 項用平均 vega）。
描述用途可以偷懶，敏感度用途不行。本產品若只是要在報告裡給一個
「這組 spread 附近的 IV 水位」參考數字，寬 spread（本產品常見 20 點寬）
用簡單平均的偏差如上例約 0.4 IV 百分點、可標注後接受；但任何「乘上
IV 變化推 P&L」的用途必須走 §5.1 的分解，不可用平均。

## 6. 給 Option Chaser 的候選方案（問題 7）

共同前提：資料形狀用抽象語言描述（vendor 比較是平行研究
`historical-options-iv-data-sources.md` 的事）；計算全部落在 Python 引擎
（前端零金融計算）；所有新數字都遵守本 repo 既有揭露哲學——標示、
不改排名（比照 FB5 系列「品質標示不影響入選」的先例；若要進排名屬
口徑變更、需另行裁示）。**本節是選項清單，不替需求方做決定。**

### 6.1 方案 A：標的層級 constant-maturity ATM IV 指數的 1Y Rank＋Percentile

- **資料**：標的層級 constant-maturity（30 天為業界慣例錨點）ATM IV
  **日序列一年**——一天一個數字 × ~252，單檔標的幾 KB。取得方式二選一
  （屬平行研究）：買 vendor 現成序列（可即時回填一年）；或自建——每個
  交易日固定時刻抓一次全鏈快照、以 §3.4 表中 IBKR／IVolatility 的公開
  配方（每期取 4 張最近 ATM、解出該期 ATM IV、兩鄰近期 variance 內插到
  30 天）算出當日值存入 Neon。**自建有冷啟動問題：要累積滿一年窗才有
  完整 percentile**（窗未滿時可顯示「以現有 N 天計」並標注，比照本 repo
  利率快取「誠實標注 fallback」的既有慣例）。
- **計算**：`IVR = (今值−min)/(max−min)`；`IVP = #{低於今值的日} / N`。
  兩個都算（ORATS 同時給四個欄位的先例；§2.1 的統計量差異是真實的，
  單給 Rank 會被極值扭曲）。
- **解釋性**：**最高**。「TLT 的選擇權整體比過去一年 78% 的日子貴」是
  一句一般使用者能直接行動的話；且與業界慣例（IVR 低利於 debit spread）
  同語言。
- **複雜度**：**最低**。計算是 stdlib 等級；工程量在「每天固定抓一次」
  的排程與持久化（本 repo 已有 Neon 與市場日語意快取的全套先例）。
- **已知弱點**：30 天 tenor 與 LEAPS 主戰場錯配（§3.4 末段）——指標會
  比 LEAPS 實際環境更神經質。可與方案 B 疊加緩解。

### 6.2 方案 B：與劇本天期對齊的長 tenor constant-maturity percentile

- **資料**：多 tenor 的 constant-maturity ATM IV 日序列（如 30／90／365
  天三條，或 vendor 的全 tenor 內插線），一年。量級仍是 KB 級／檔。
- **計算**：對每個劇本取「與 `days_to_expiry` 最接近的 tenor」那條序列
  算 Rank／Percentile；或對兩條鄰近 tenor 再做一次內插（√t 或 variance
  線性，同 §3.4 配方）。本 repo 的期限對齊利率曲線（T12／`leg_rate`）
  已有完全同構的「依到期日查表」機制可類比。
- **解釋性**：**好**，且比 A 更貼題——「與你這個劇本同天期的 IV 水位」。
  代價是每個劇本的 percentile 基準不同，跨劇本粗看時數字不可直接互比
  （跨劇本比較是需求方保留的獨立議題，此處不展開）。
- **複雜度**：中。自建路線要每天對**多個** tenor 各解一個內插值（仍是
  同一份快照、同一套配方多跑幾次）；vendor 路線只是多取幾條序列。
- **已知弱點**：長 tenor 的 ATM IV 移動平緩，一年窗內的 min–max 區間窄，
  Rank 對小變動會顯得敏感（分母小）；Percentile 較穩健——**若採此案，
  Percentile 應為主、Rank 為輔**。

### 6.3 方案 C：兩腿 (DTE, delta) surface 點各自 percentile＋skew 差

- **資料**：**per-standardized-point 的 surface 歷史一年**（§3.3 的形狀：
  ~252 天 × tenor×delta 網格；或至少涵蓋兩腿所在的 (DTE, delta) 鄰域）。
  這是五案中唯一需要「每天一張平滑 surface」的，自建等於重寫 SMV 級
  管線，實務上只有 vendor 路線可行。
- **計算**：對買腿取其 (DTE, delta) 對應的歷史序列算 percentile；賣腿
  同；另算 `s = σ₁−σ₂` 的歷史 percentile（skew 相對歷史的位置——§5.1
  證明這是 spread 特有曝險，只有本案顯示得出來）。
- **解釋性**：**最低**。三個 percentile 並排，對非 quant 使用者需要
  大量解釋文字；本產品報告版型（R1 的「結論先行」原則）下很難不淪為
  第二層明細。
- **複雜度**：**最高**（資料與呈現兩頭都重）。
- **定位**：方法論的天花板、產品的第二階段選項——若 A／B 上線後需求方
  發現 skew 訊號有實際決策價值，再升級到本案。

### 6.4 方案 D：延伸既有 spread 成本歷史（明確標注：不是 IV 判讀）

- **資料**：**已在手上**——`store.spread_cost_history()`（V9）聚合的
  自家快照歷史，Neon 裡有多久就是多久。
- **計算**：在既有走勢圖上加「當前成本位於自家歷史第 X 百分位」一行字。
- **解釋性**：直覺但**有誤導風險**：§4.d 已論證這個 percentile 量的
  主要是 spot 與 DTE，不是 IV。若採用，措辭必須是「這組結構的**成本**
  相對你追蹤以來的位置」，且不得與「IV 環境」出現在同一個標籤下。
- **複雜度**：最低（一個純函式＋一行 UI）。
- **定位**：**不能作為本題的答案**，列入只為完整性——需求方若只想要
  「這組東西比我上週看它時貴了」的樸素判讀，本案已足夠且零新資料。

### 6.5 方案 E：IV / 已實現波動（HV）比值——零歷史 IV 資料的互補指標

- **資料**：標的**價格**日序列（既有備援資料源即可得）＋**當下** IV
  （快照已有）。完全不需要歷史 IV。
- **計算**：`HV_n` ＝過去 n 日對數報酬的年化標準差（n=20／90 兩檔）；
  指標 ＝ 當前 constant-maturity ATM IV（或退而求其次：baseline 期 ATM
  合約 IV）÷ HV。IV/HV 比值是各平台標配欄位（Barchart 有專頁）
  〔索引轉述〕。
- **解釋性**：好——「選擇權定價的波動是實際波動的 1.4 倍」。**但要
  誠實標注它量的是 volatility risk premium 的高低，不是『相對自己歷史』
  的位置**——IV 可以處於一年低點同時 IV/HV 仍偏高（實現波動更低）。
  與 A 是不同軸的資訊，互補而非替代。
- **複雜度**：低（HV 是 stdlib 一行統計；唯一新依賴是價格日序列的
  取得與快取，形狀與利率快取雷同）。
- **已知弱點**：backward-looking 的 HV 對前瞻事件盲目；n 的選擇有
  自由度（須在方法論尾註揭露，本 repo 報告版型已有此慣例位置）。

### 6.6 推薦排序（供裁示，非決定）

**A → E → B → C，D 不作為本題答案。**理由：

1. **A 先做**：業界主流形狀（§3.4 六家同款）、資料最輕、解釋性最高、
   與「IVR 低利於 debit spread」的通行語言直接接軌。它的 30 天 tenor
   錯配是已知且可標注的限制，不阻礙先上。
2. **E 緊隨或同批**：與 A 共用「每日一抓」的排程機制，邊際成本極低，
   而且**在 A 的一年窗冷啟動期間（若走自建路線）E 是唯一立即可用的
   環境判讀**——這個順序保險價值很高。
3. **B 是 A 的正確深化**：解 tenor 錯配、貼合本產品 LEAPS 定位，機制
   與 T12 期限對齊利率同構。等 A 的管線跑穩後演進。
4. **C 是天花板**：等需求方看過 A/B 的實際決策價值後再裁示要不要為
   skew 訊號付出 surface 歷史的成本。
5. **D 已出貨的部分維持原樣**，只需守住標籤紀律（成本走勢 ≠ IV 環境）。

**共同紅線（沿用既有裁示慣例）**：任何 IV 環境指標都是**標示層**——
不進排名、不進過濾、不改 A14.2 成本口徑；要讓它影響候選池或排序，
屬口徑變更，需求方另行裁示後才開票。

## 7. 未能查證的事項

1. **tastytrade IVR／IV%／IVx 的官方原文**。`support.tastytrade.com`
   直接抓取被擋（本次實測 `EGRESS_BLOCKED`），§2.1／§3.4 的定義為索引
   轉述（公式在多個獨立來源間交叉一致，可信度高，但**逐字措辭未核對**）。
   需求方界定「tastytrade 對兩者的定義要引原文」——本文能給的最接近版本
   已標〔索引轉述・近逐字〕，逐字引用建議由需求方在可正常連網環境對
   Help Center 條目（Volatility Metrics, article 43000539059）覆核後定稿。
2. **Cboe VIX 白皮書的內插公式逐字**。`cdn.cboe.com` 被擋；「兩鄰近
   到期日、總 variance 時間線性內插、權重以分鐘計」的描述由官方方法論
   PDF 的索引摘錄與第三方（Macroption）交叉取得，公式細節（N_T1/N_T2/
   N_30 的分鐘記法）未逐字核對。
3. **IVolatility IV Index 的加權細節**。官方明言 delta／vega 加權為
   proprietary——「每期 4 張 ATM、√t 內插到固定 tenor」可信，權重公式
   本來就不公開。
4. **IBKR V30 說明頁逐字**（ibkrguides／TWS 文件）。方法描述（8 日
   門檻、4 strike×2、拋物線擬合、variance 內插）為索引轉述，未逐字核對。
5. **OptionMetrics kernel smoother 的參數**。網格規格（tenor×delta）
   可信；smoother 的 bandwidth 等細節在付費的 reference manual（v5.2）
   內，未取得。
6. **ORATS `ivRank1m`／`ivPct1y` 欄位的精確視窗與底層序列定義**。欄位
   存在與實例值經 API 文件索引確認；「底層是哪一條 constant-maturity
   序列、窗的確切起訖」未逐字核對。
7. **Derman (1999) 與 Daglish–Hull–Suo (2007) 的逐字定義**。兩份 PDF
   的公開鏡像（pricing.online.fr、rotman.utoronto.ca）均被擋，§2.3 為
   索引轉述；sticky strike／sticky delta 的概念表述在教科書級來源間
   高度一致，風險低。
8. **「沒有主流平台對單一合約做 IV Rank／Percentile」是檢索性結論**
   （absence of evidence）——本次多輪檢索未找到反例，且 §3.1 的三個
   結構性理由使反例不太可能存在，但不能排除某個小眾工具這樣做。
   §4.a／§4.b 的「沒有找到先例」同此留保。
9. **tastylive「IVR<30 買 debit spread」的官方原文**。此慣例在多個二手
   來源間一致（含自稱轉述 tasty 方法論者），tastylive 官方頁面本身被擋，
   具體門檻數字（20 vs 30）各來源有出入，本文僅以「IVR 低利於 debit
   spread 的通行慣例」的強度引用，未依賴具體門檻值。
10. **thinkorswim「IV Percentile 實為 Rank」**。Schwab 官方文章的索引
    摘錄本身描述的就是 high-low range 公式（間接支持），但「官方欄位
    名與公式錯配」這個判斷主要來自第三方（Hahn-Tech、useThinkScript），
    官方頁逐字未核對。

## 8. 來源清單

**標記說明**：沿用 `option-strategy-report-conventions.md` §7 的分類。
本次 WebFetch 僅 `raw.githubusercontent.com` 可達（§0），外部來源無一
逐字檢視，全部經搜尋索引。

平台定義（IV Rank／Percentile／IVx）
- 〔官方・索引轉述〕[Volatility Metrics (IVR, IV%, IVx, HV) — tastytrade Help Center](https://support.tastytrade.com/support/s/solutions/articles/43000539059)（直接抓取被擋）——IVR／IVP 公式、IVx 為 VIX 式逐到期日計算、預設 30 天由兩鄰近到期日內插
- 〔官方・索引轉述〕[Using Implied Volatility Percentages and Rankings — Charles Schwab](https://www.schwab.com/learn/story/using-implied-volatility-percentiles)、[3 Stock Options Trading Stats on thinkorswim — Charles Schwab](https://www.schwab.com/learn/story/3-stock-options-trading-stats-on-thinkorswim)——「Current IV Percentile shows the day's IV compared to the high and low range for the past 12 months」
- 〔二手・索引轉述〕[Thinkorswim Implied Volatility Percentile — Hahn-Tech](https://www.hahn-tech.com/thinkorswim-implied-volatility-percentile/)、[useThinkScript 社群](https://usethinkscript.com/threads/implied-volatility-iv-rank-percentile-for-thinkorswim.674/)——thinkorswim 欄位名與公式錯配
- 〔官方・索引轉述〕[Implied Volatility IV Rank and IV Percentile — Barchart](https://www.barchart.com/options/iv-rank-percentile)——ATM 平均 IV 對一年高低點（Rank）／低於現值日數佔比（Percentile）
- 〔官方・索引轉述〕[Options History（per-contract 頁）— Barchart](https://www.barchart.com/stocks/quotes/DLTR%7C20240315%7C129.00C/options-history)——單一合約逐日 IV 供查看（Premier）

Constant-maturity 指數建構
- 〔官方・索引轉述〕[Volatility Index Methodology: Cboe Volatility Index (PDF)](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf)（直接抓取被擋）、[VIX Maturity Interpolation whitepaper (PDF)](https://cdn.cboe.com/resources/education/research_publications/VIXInterpolationWhitepaper.pdf)——兩鄰近 SPX 到期日、總 variance 時間線性內插至 30 天
- 〔二手・索引轉述〕[VIX Calculation Explained — Macroption](https://www.macroption.com/vix-calculation/)——內插公式的第三方重述
- 〔官方・索引轉述〕[Implied Volatility Index (IV Index) — IVolatility](https://www.ivolatility.com/education/implied-volatility-index/)、[IVolatility Data Guide (PDF)](https://www.ivolatility.com/doc/IVolatility_Data_Nov17.pdf)、[How to Use the IV Index — Fidelity/IVolatility user guide (PDF)](https://www.fidelity.com/research/options/12.09/pdf/IVX_Index_User_Guide.pdf)——每期 4 張 ATM、delta/vega 專有加權、√t 內插至 30/60/…/720 天
- 〔官方・索引轉述〕[Implied Volatility Viewer — IBKR Guides](https://ibkrguides.com/traderworkstation/implied-volatility-viewer.htm)、[TWS API: Option Greeks — IBKR](https://interactivebrokers.github.io/tws-api/option_computations.html)——V30：≥8 日的首月起、每期 4 strike×2、IV 對 strike 擬合拋物線取期望期貨價處值、variance 線性內插開根號

ORATS（surface、rank 欄位、rich/cheap、earnings 調整）
- 〔官方・索引轉述〕[Smoothing Options Implied Volatilities Using ORATS SMV System — ORATS blog](https://orats.com/blog/smoothing-options-implied-volatilities-using-orats-smv-system)——清洗報價、put-call parity 解 residual yield、無套利平滑曲線
- 〔官方・索引轉述〕[Describing The Implied Volatility Options Surface — ORATS blog](https://orats.com/blog/describing-the-implied-volatility-options-surface)——surface 以 (DTE, delta) 為自變數；10–365 天 × 4 delta 內插 IV；30/60/90/6m/1y constant-maturity
- 〔官方・索引轉述〕[Core Research — ORATS API 文件](https://orats.com/docs/core-research)——`atmIvM1…M4`、`ivRank1m`/`ivPct1m`/`ivRank1y`/`ivPct1y` 欄位與實例值
- 〔官方・索引轉述〕[How To Find The Best Options Trade Using Theoretical Values — ORATS blog](https://orats.com/blog/how-to-find-the-best-options-trade-using-theoretical-values)——smoothed edge（S%）：SMV 理論值與成交價的距離
- 〔官方・索引轉述〕[How ORATS Removes Earnings Effect from Implied Volatility — ORATS blog](https://orats.com/blog/how-orats-removes-earnings-effect-from-implied-volatility)、[Implied Volatility Term Structure's Three Parameters — ORATS blog](https://orats.com/blog/implied-volatility-term-structures-three-parameters)——implied earnings effect 解出後才談逐月 IV 歷史可比

OptionMetrics（standardized surface）
- 〔官方・索引轉述〕[IvyDB US — OptionMetrics](https://optionmetrics.com/united-states/)、[IvyDB US flyer (PDF)](https://optionmetrics.com/wp-content/uploads/2024/03/OM_IvyDB-US_Flyer_WEB_REV.pdf)——kernel-smoothed constant-expiration surface；到期 10–730 天、delta 0.10–0.90 間隔 0.05
- 〔二手・索引轉述〕[Implied volatility surfaces: a comprehensive analysis using half a billion option prices — Review of Derivatives Research (Springer)](https://link.springer.com/article/10.1007/s11147-023-09195-5)——學術端消費 IvyDB surface 的例證

理論（sticky rules、FX 慣例、term structure）
- 〔官方・索引轉述〕[Regimes of Volatility — E. Derman, Goldman Sachs QS Research Notes, 1999（公開鏡像）](http://pricing.online.fr/docs/regimes.pdf)（直接抓取被擋）；另見 [Patterns of Volatility Change — Derman smile lecture 9](https://emanuelderman.com/wp-content/uploads/2013/09/smile-lecture9.pdf)
- 〔官方・索引轉述〕[Volatility Surfaces: Theory, Rules of Thumb, and Empirical Evidence — Daglish, Hull, Suo (Rotman)](https://www-2.rotman.utoronto.ca/~hull/downloadablepublications/DaglishHullSuoRevised.pdf)
- 〔二手・索引轉述〕[Sticky strike vs Sticky delta — Delta Quants](http://deltaquants.com/volatility-sticky-strike-vs-sticky-delta)
- 〔二手・索引轉述〕[FX Volatility Smile conventions（RR/STR）— quantpie](https://www.quantpie.co.uk/fx/fx_rr_str.php)、[A Guide to FX Options Quoting Conventions — Reiswich & Wystup（ResearchGate）](https://www.researchgate.net/publication/275905055_A_Guide_to_FX_Options_Quoting_Conventions)、[Arbitrage-free smile construction on FX option markets — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9483449/)——ATM＋25Δ RR＋25Δ BF 的 delta 座標報價、sticky delta 建構
- 〔二手・索引轉述〕[Implied Volatility Term Structure — QuestDB glossary](https://questdb.com/glossary/implied-volatility-term-structure/)、[How to Read Volatility Term Structure — FlashAlpha](https://flashalpha.com/articles/volatility-term-structure-contango-backwardation-events)——contango 為常態、事件與壓力期倒掛、roll-down

Debit spread 與 IV 環境的交易慣例（§3.4 第 4 點、§4.e）
- 〔二手・索引轉述〕[Implied Volatility And Debit Spreads — Trading Strategy Guides](https://tradingstrategyguides.com/implied-volatility-and-debit-spreads-trade-setup-guide/)、[IV Rank vs. Percentile Guide — MenthorQ](https://menthorq.com/guide/iv-rank-vs-percentile/)、[IV Rank Options — Bullish Bears](https://bullishbears.com/iv-rank/)——IVR/IVP 低（常見門檻 <20–30）時偏好 debit spread 的通行慣例（門檻數字各來源有出入，§7 第 9 項）

Spread 歷史查看工具（§4.d）
- 〔二手・索引轉述〕[thinkorswim comparison study 畫 spread 歷史（basecamptrading support）](https://support.basecamptrading.com/hc/en-us/articles/14671221735195)、[Options price displayed on chart — useThinkScript](https://usethinkscript.com/threads/options-price-displayed-on-chart.9793/)

本 repo（引擎與既有研究）
- `option_chaser/valuation.py` —— `bs_call`／`call_greeks`（§5 數值驗算的計算引擎）、`iv_shifts` 情境機制（`models.py:65`）
- `option_chaser/ranking.py` —— 最差成交口徑主排名（附錄 A14.2）
- `option_chaser/filters.py:112` —— IV 存在性為引擎前置條件（IV 0.01–5.0）
- `option_chaser/report.py:386-387` —— 兩腿 Bid/Ask/IV 已逐腿顯示（V8）
- `option_chaser/store.py:380` —— `spread_cost_history()`（V9，§4.d／方案 D 的既有基礎）
- `docs/research/option-liquidity-filtering.md` —— 最差成交口徑哲學、LEAPS 報價義務（§3.2）、`theo` 欄位獨立性（§6.5）
- `docs/research/option-strategy-report-conventions.md` —— §5 曾把「IV 百分位／IV Rank」列為 V8 明確不做項（「需要歷史 IV 序列，引擎目前沒有」）——本文即是把那一項從「不做」推進到「怎麼做」的方法論前置
- `docs/research/interest-rate-source-selection.md` —— 期限對齊查表機制（方案 B 的同構先例）
