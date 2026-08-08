# 隱含機率讀數——Debit/Width 作為市場隱含勝率的專業先例與陷阱

研究日期：2026-08-08。對應票號：R1（[#96]），上游地圖 [#95]（路徑 7a）。
本文回答：對一組 vertical call spread（買 K1／賣 K2 call、debit D、
width W = K2−K1），專業 desk 與學術如何把 **D/W** 讀成「市場隱含的
機率／期望值定價」——這是「這組 spread 現在貴不貴」的候選判讀路徑
之一，參照系＝**市場自己的隱含分布**（不是歷史、不是鄰居、不是
自建預測）。本文只做研究、不施工、不替需求方拍板。

**範圍界線**：不做「edge vs 自建預測分布」（地圖 7b，需求方明示本輪
不做）；不動排名／過濾／A14.2 成本口徑（既有紅線）；不涵蓋 Long
Call vs Spread 比較（Grill C）與跨劇本比較（Grill D）。

## 0. 研究方法與資料品質聲明

沿用 `option-strategy-report-conventions.md` §7／`candidate-iv-relative-value.md`
§1 的標記體系。本輪實測網路狀況：

- **WebFetch 一律 `EGRESS_BLOCKED`**。本輪實測遭拒：`pages.stern.nyu.edu`
  （Figlewski 的 RND 綜述 PDF）、`www.morganstanley.com`（MS Research
  的 implied probabilities 說明 PDF）。與前幾輪不同，本輪**沒有找到
  關鍵一手文獻的 `raw.githubusercontent.com` 鏡像**，故本文**沒有任何
  〔一手・逐字〕級來源**——全部外部引用為 **〔官方・索引轉述〕**
  （發布者官方頁面／PDF，僅經搜尋索引摘錄）或 **〔二手・索引轉述〕**
  （第三方整理），逐筆標明於 §9，未逐字核對者列入 §8。
- **數學推導與數值例全部是自行推導＋本 repo 引擎實算**（§3、§4；
  stdlib＋`option_chaser/valuation.py` 的 `norm_cdf`／`days_between`，
  重現步驟逐處附上），不依賴任何外部轉述。§3.1 的核心恆等式另做了
  **數值自洽驗證**（toy model 下帶狀積分與 spread 價格之比完全相等，
  §4.3），這部分的可信度不受索引轉述限制影響。

## 目錄

- §1 結論摘要（五問五答）
- §2 先例：call spread＝市場自己在交易的 digital（含成熟度分級）
- §3 最小版本：單一快照下 D/W 的精確語意與推導
- §4 陷阱：美式／bid-ask／smile／貼現，逐項含量級
- §5 呈現先例與本產品的呈現建議
- §6 誠實侷限：這條路徑能與不能回答什麼
- §7 給 G1 的結論段（非量化背景可讀）
- §8 未能查證的事項
- §9 來源清單

## 1. 結論摘要（五問五答）

1. **先例：厚，且「機構成熟慣例」級。**(a) 定價理論與 structured
   products desk 端：digital option 的教科書定義就是 call spread 的
   極限，且 exotic desk **實務上反過來用 call spread 掛帳與對沖
   digital**（overhedge 慣例，§2.1）；(b) 學術與央行端：
   Breeden–Litzenberger (1978) 把「call 價對履約價的斜率／二階導」
   讀成風險中性 CDF／密度，Bank of England 每日估算 option-implied
   PDF、Minneapolis Fed 公開發布「市場定價的機率」（§2.2）；(c) 賣方
   研究端：Morgan Stanley 公開文件明文以「butterfly 成本 ÷ 落在區間
   的 payout，再做時間價值調整」定義 implied probability（§2.3）；
   (d) 交易所／預測市場端：CME FedWatch 把期貨價轉成逐會期機率長條，
   Kalshi（CFTC 監管的事件合約交易所）以 1–99¢ 報價、**¢ 數＝機率
   百分點**（§2.4）。以上全屬機構成熟慣例；「風險中性→真實世界」
   的轉換才是學術成立、業界少用的部分（§2.6 分級表）。
2. **最小版本：D/W 是「K1–K2 帶狀的風險中性機率加權平均 payout」，
   模型無關、精確成立。**恆等式 `D/W = DF × (1/W)∫[K1,K2] Q(S_T≥K)dK`
   （DF＝貼現因子、Q＝風險中性生存機率；§3.1 自行推導＋數值驗證）。
   「D/W ≈ P(S_T ≥ 帶狀中點)」只在 Q 於帶內近似線性時成立，誤差
   ≈ `(W²/24)·|q′|`（§3.2）——本產品 W=40 的寬帶下**不該當點機率
   呈現，該當帶狀平均**。與 N(d2)／delta 的關係：N(d2) 是「單一模型
   ＋單一 vol ＋正確 forward」下的點機率，對股利假設極度敏感（TLT
   實算：q=0 vs q=4.3% 讓同一點的 N(d2) 從 20.3% 砍半到 10.1%，
   §3.4）；delta＝N(d1) 恆高於 N(d2)，σ√T 越大差越大（LEAPS 最大）。
   **D/W 不需要任何這些假設——這正是它對本產品（q=0 引擎、美式
   ETF、LEAPS）的決定性優勢。**
3. **陷阱四項，各有量級**：(a) 美式性——兩腿的提前履約溢價在相減時
   部分抵銷，殘差方向是**把 D 推高、機率讀數輕微高估**；兩腿皆 OTM
   的 LEAPS 下量級遠小於 bid-ask 帶寬，買腿深 ITM＋臨近除息時才需
   警惕（§4.1）；(b) bid-ask——應呈現**上下界**：本產品最差成交
   口徑（A14.2）給出讀數上緣（你實付的定價），mid 給市場中心值；
   TLT 實例整個 bid-ask 帶寬折合 1.1 個機率點（§4.2）；(c) smile——
   教科書 digital 的 skew 修正項（−vega·∂σ/∂K）在本例 LEAPS 上高達
   4.5 個機率點（≈讀數的一半！），**而 call spread 的市價本身就內建
   了這個修正**——這是「用交易出來的 spread 價，不用模型 digital」
   的全部理由（§4.3）；(d) 貼現——D/W 是**貼現後**的量，要除以 DF
   才是機率；TLT 2.4 年期 DF≈0.908，是 9% 級的一階效應，不可忽略；
   DF 可直接用既有 T12 期限對齊利率曲線（§4.4）。
4. **呈現先例**：FedWatch 的逐結局機率長條、Minneapolis Fed 的
   「市場定價之機率」措辭、MS 的 butterfly 讀數、Kalshi 的 ¢-per-$1、
   GS 的 max payout ratio、tastytrade 對 defined-risk spread 的
   POP = 1 − credit/width（§5.1）。**¢-per-$1 適合借用**——spread
   payoff 除以 W 之後在數學上就是一張「上限 $1」的合約，「付 8.7¢
   換每 $1 上限」是零失真的翻譯；但標籤要用「市場定價」，**不可用
   「勝率」**（風險中性＋帶狀平均兩重距離，§5.2）。
5. **誠實侷限**：這條路徑回答「**相對市場自己定的機率，你付了
   多少**」——它把 spread 的標價翻譯成市場的語言，不判斷市場對
   不對；風險中性機率≠真實世界機率（差一個風險溢酬，TLT 上主要是
   債券期限溢酬，方向不如股票 put 端有共識）；LEAPS 的寬 bid-ask
   意味著「市場的機率」本身就有 ±0.5 個機率點的帶寬（§6）。

## 2. 先例：call spread＝市場自己在交易的 digital

### 2.1 定價理論與 structured products desk：digital 的定義與對沖本體

**理論端**〔二手・索引轉述，多來源交叉一致〕：digital（binary）call
的教科書定義就是 call spread 的極限——「a digital option is an
infinitely leveraged call or put spread, where the long and short
strikes are so close together that they are effectively the same
strike」；Black-Scholes 下 cash-or-nothing call 的閉式解為
`e^(−rT)·N(d2)`，即「貼現因子 × 履約機率」。

**Desk 端**〔二手・索引轉述，Delta Quants／The Financial Engineer
兩個獨立 quant 實務站點一致〕：exotic／structured products desk
**幾乎一律把 digital 與 barrier payoff 用 option spread 掛帳與對沖**
（「almost always barrier/digital options are booked and hedged as
option spreads」），理由是 spread 的 Greeks 連續平滑；而且慣例上
call spread 被刻意做成**比理論 digital 貴一點的保守替代**
（overhedge/conservative replication）。這對本產品的意義是雙向的：

> 市場不是「把 call spread 近似成 digital」——是反過來，**digital
> 這種產品在專業市場的實際存在形式就是 call spread**。把 D/W 讀成
> 帶狀機率定價，讀的是市場本來就在交易的物件，不是學術類比。

### 2.2 Breeden–Litzenberger 與央行實務：機率讀數的正統血統

- **Breeden & Litzenberger (1978, Journal of Business)**〔官方・索引
  轉述〕：call 價格函數對履約價的**一階導數＝貼現後的（負）生存
  機率、二階導數∝風險中性密度**。這是整條路徑的理論基石；§3.1
  給出自含推導，不依賴轉述。
- **Bank of England**〔官方・索引轉述〕：BoE Macro Financial
  Analysis Division **每日**估算 option-implied PDF，方法論見
  Clews, Panigirtzoglou & Proudman (2000, Quarterly Bulletin)；另有
  官方「terminology and concepts」說明文件與通膨版應用（Smith,
  2012 Q3 Quarterly Bulletin）、CCBS 的 FX 版手冊。央行把它當
  **標準判讀工具**發布，不是研究室玩具。
- **Federal Reserve Bank of Minneapolis**〔官方・索引轉述〕：公開
  網頁常設發布「Market-Based Probabilities」——例如「S&P 500 未來
  一年漲逾 20% 的機率」，方法明文為：以 Shimko (1993) 手法對 IV
  擬合曲線→轉回連續 call 價格→Breeden–Litzenberger 取分布。
  官方措辭把它定義為「市場對某事件**指派的權重**」。
- 補充：Fed 理事會 IFDP 工作論文亦用同法讀跨幣別利率預期
  〔官方・索引轉述〕。

### 2.3 賣方研究：Morgan Stanley 的公開定義

Morgan Stanley Research 公開 PDF《How Options Implied Probabilities
Are Calculated》〔官方・索引轉述；原檔被擋，內容經索引摘錄〕：

> 「在選擇權市場，你可以用 butterfly spread 買到對特定價格區間的
> 曝險……該股票落在區間內的機率＝**butterfly 的成本 ÷ 落在區間時
> 的 payout**」；實作是用內插 vol surface 造出一串很窄的重疊
> butterfly，「**以成本除以 payout、再做時間價值調整**，得到選擇權
> 定價出的未來機率分布」，並註明這是**近似的風險中性分布**。

這是與本票問題**同構到逐字**的賣方先例：butterfly 是密度版
（cost/payout＝區間機率），call spread 是 CDF 版（D/W＝帶狀平均
生存機率）；「adjusting for the time value of money」正是 §4.4 的
貼現項。另外既有研究已錄得 Goldman Sachs 以 **max payout ratio**
（最大獲利／權利金，「大於 8 倍」）呈現結構吸引力
（`option-strategy-report-conventions.md` §2.3）——同一枚硬幣的
odds 面。

### 2.4 交易所與預測市場：機率呈現的大眾化先例

- **CME FedWatch**〔官方・索引轉述〕：把 30-Day Fed Funds 期貨價
  轉成逐次 FOMC 會議的結局機率（無變動／降一碼／降兩碼…），以
  機率長條與跨會期機率樹呈現。是「從市場價格反推機率並直接標成 %」
  最廣為接受的公開產品。
- **Kalshi**〔官方＋二手・索引轉述〕：CFTC 監管的事件合約交易所，
  合約結算 $1 或 $0，報價 1–99¢，**價格的 ¢ 數＝隱含機率百分點**
  （38¢＝38%）；Polymarket 同理以 $0–$1 報價。監管意義：**binary
  option 這個物件本身已是美國受監管交易所的上市商品**，「價格＝
  機率定價」是其官方讀法。
- 這兩者對本產品是**呈現層**先例（§5），數學上與 §2.2 同源。

### 2.5 交易員教育圈：value/width 的口頭慣例

- **tastytrade**〔二手・索引轉述〕：對 defined-risk credit spread
  的 Probability of Profit 公式明文是 `POP = 100 − (credit/width)×100`
  ——即 **spread 價 ÷ width 直接當機率用**（credit 側視角；debit
  側就是 D/W 本身）。零售主流平台級的既成慣例。
- **Moontower（前 SIG 選擇權造市商 Kris Abdelmessih）**〔二手・索引
  轉述〕：專文〈a deeper understanding of vertical spreads〉直接給出
  「**[value of the spread]/[distance between the strikes] 隱含股價
  到期落在 spread 中點以下的機率**」的讀法——desk 出身者對本題
  的白話版，連「中點」近似都與 §3.2 一致。

### 2.6 成熟度分級

| 成分 | 分級 | 依據 |
|---|---|---|
| digital＝call spread 極限；desk 以 call spread 掛帳 digital | **機構成熟慣例** | §2.1 |
| B–L 讀數；央行常設發布 option-implied 機率 | **機構成熟慣例** | §2.2 |
| 賣方以 cost/payout＋貼現調整呈現 implied prob | **機構成熟慣例** | §2.3 |
| 價格＝機率的 ¢ 報價（受監管事件合約） | **機構成熟慣例** | §2.4 |
| spread 價/width 當機率的口頭讀法 | **成熟（交易員圈），非正式** | §2.5 |
| 整條 RND 曲線估計（擬合＋平滑＋尾部外推） | 成熟但屬央行／vendor 級工程，**非本票最小版本所需** | §2.2、§3 |
| 風險中性→真實世界分布的轉換（風險溢酬校正） | **學術成立、業界少用**（央行文獻自己也標明其不確定性） | §6 |

## 3. 最小版本：單一快照下 D/W 的精確語意

### 3.1 恆等式（自行推導，模型無關）

設歐式無套利、貼現因子 `DF = e^(−rT)`，風險中性測度下
`C(K) = DF·E[(S_T−K)⁺] = DF·∫_K^∞ (s−K) q(s) ds`（q＝密度）。
對 K 微分（Leibniz）：

```
∂C/∂K = −DF·∫_K^∞ q(s) ds = −DF·Q(S_T ≥ K)        …(B–L 一階式)
```

把 debit 寫成兩點差再用微積分基本定理：

```
D = C(K1) − C(K2) = DF·∫[K1,K2] Q(S_T ≥ K) dK

⇒  D/W = DF × (1/W)·∫[K1,K2] Q(S_T ≥ K) dK          …(核心恆等式)
```

**逐字讀法：D/W ＝ 貼現因子 × 「生存機率 Q(S_T≥K) 在 K1–K2 帶上
的平均值」。**它不是任何一點的機率，是帶狀平均——等價地（分部
積分）可寫成「機率加權平均 payout」：

```
D/W = DF × [ Q(S_T ≥ K2)·1 + E( (S_T−K1)/W · 1{K1<S_T<K2} ) ]
```

即：漲過 K2 拿滿 $1、落在帶內按比例拿部分——**「付 D/W 換每 $1
上限」是這條恆等式的白話直譯，零近似**。推導只用到「無套利＋
歐式」，不用 Black-Scholes、不用任何 vol、不用 forward 假設。
無套利界限：`0 ≤ D/W ≤ DF`——讀數天然不會超過 1。

### 3.2 「≈ P(S_T ≥ 中點)」何時成立（近似與誤差項）

由積分中值定理，帶內必存在 K* 使 `D/W = DF·Q(S_T ≥ K*)`——讀數
**恆是帶內某一點的確切機率**，只是那點未必是中點。取中點
`Km=(K1+K2)/2` 做二階 Taylor 展開並對帶取平均：

```
(1/W)∫Q dK = Q(Km) + (W²/24)·Q″(Km) + O(W⁴)
           = Q(Km) − (W²/24)·q′(Km) + O(W⁴)
```

- **窄帶（W→0）**：誤差 O(W²) 消失，D/W→DF·Q(中點)——這就是
  「tight call spread＝digital」的極限，也是 §2.5 口頭慣例成立的
  條件。
- **本產品的寬帶（TLT 實例 W=40，佔現價近半）**：OTM 帶上密度
  遞減（q′<0），帶平均**高於**中點機率，偏差可觀（§4.3 的 toy
  model 裡帶平均 7.1% vs 中點修正後 5.5%）。**結論：本產品應把
  D/W 呈現為「帶狀平均／付 X 換每 $1 上限」，不要標成「漲到中點
  的機率」**——後者在寬帶上是會被打臉的過度簡化。

### 3.3 與 N(d2)、delta 的關係與差異

| 量 | 定義 | 是什麼機率 | 需要的假設 |
|---|---|---|---|
| **D/W ÷ DF** | 兩個市價相減 | 帶狀平均生存機率（風險中性），**精確** | 無（模型無關） |
| **N(d2)** | BS 公式項 | 單點 `Q(S_T≥K)`，**僅在 BS 世界成立** | 常數 vol、幾何布朗、**正確 forward（股利！）** |
| **delta = N(d1)** | 對沖比率 | 不是機率；`N(d1) = N(d2) + φ(d2)·σ√T` 之近似意義上**恆高估** | 同上 |

- **N(d2) 對 forward 假設極度敏感（引擎實算）**：TLT 實例（S=84.52、
  T=2.416y、r=4%、σ=15%、K=110）：q=0 時 N(d2)=**20.3%**；帶入
  TLT 量級的配息率 q=4.3% 後＝**10.1%**——**同一點的「機率」被
  股利假設砍半**。本 repo 引擎是 q=0 的 BS（`candidate-iv-relative-value.md`
  §7.4 已證其在 TLT 長天期絕對定價偏差近一倍），**任何用引擎
  N(d2) 直接標機率的做法都會系統性高估一倍量級**。D/W 完全繞開
  此問題：它只吃市價，市場已把股利定進價格裡。
- **delta 當機率是雙重近似**：N(d1)−N(d2) ≈ φ(d2)·σ√T，隨 σ√T
  放大——LEAPS（σ√T≈0.23–0.28）正是差距最大的場域〔方向與量級
  另有多來源索引轉述交叉，§9〕。結論：**在本產品的 LEAPS 場景，
  delta 連可用 proxy 都算勉強，N(d2) 被股利假設卡死，D/W 是唯一
  不需要新假設的機率讀數。**

### 3.4 TLT 實算（重現：stdlib＋`option_chaser/valuation.py`）

輸入沿用 `candidate-iv-relative-value.md` §11 同一組（`tlt_report.md`
commit `8625fad`：S=84.52、r=4%、基準日 2026-07-17；candidate＝
買 2028-12-15 C90（3.80/4.10）／賣 C130（0.63/0.73）；W=40、
T=882/365=2.416y、DF=e^(−0.04×2.416)=**0.9079**）：

| 口徑 | D | D/W | ÷DF（未貼現讀數） | ¢-per-$1 | 淨 odds（(W−D)/D） | payout ratio（W/D） |
|---|---|---|---|---|---|---|
| **最差成交（A14.2：買 Ask−賣 Bid）** | 3.47 | 8.7% | **9.6%** | 8.7¢ | 10.5 : 1 | 11.5× |
| Mid | 3.27 | 8.2% | **9.0%** | 8.2¢ | 11.2 : 1 | 12.2× |
| 最佳成交（買 Bid−賣 Ask） | 3.07 | 7.7% | 8.5% | 7.7¢ | 12.0 : 1 | 13.0× |

讀法示範（事實性措辭，無主觀標籤）：「以最差成交計，市場對這組
90–130 帶狀 payoff 的定價是**每 $1 上限收 8.7¢**；除以貼現因子後
＝**帶狀平均隱含機率約 9.6%**（風險中性口徑）；等價 odds 約
**10.5 賠 1**。」附註：本例帶狀中點 (90+130)/2=110 恰為劇本目標價
——這是**此 candidate 的巧合**（K1/K2 由排名選出），不是通則，
呈現層不得依賴。

## 4. 陷阱：逐項與量級

### 4.1 美式 ETF options（提前履約、配息）

B–L 恆等式假設歐式；TLT options 是美式實物交割。偏差結構：

- 美式 call 價＝歐式價＋提前履約溢價（EEP≥0）。兩腿相減時
  `D_美式 = D_歐式 + [EEP(K1) − EEP(K2)]`；EEP 隨 moneyness 變深
  而增大（配息標的的 call 只在深 ITM＋臨近除息時值得提前履約
  〔官方＋二手・索引轉述：教科書共識＋文獻綜述〕），故
  `EEP(K1) ≥ EEP(K2)`，**殘差非負：D 被推高、機率讀數方向性
  高估**。
- **量級**：兩腿皆 OTM／淺 ITM 時（本產品常態——買腿 delta
  0.61、賣腿 0.15），EEP 是二階小量；學術與央行做整條 RND 時的
  標準處置是「de-Americanization」（以美式模型反推 IV、再用歐式
  公式重造價格）〔官方・索引轉述：Figlewski RND 綜述、
  de-Americanization 文獻、OptionMetrics 慣例〕，但那是為了整條
  密度曲線的精度；**對單一帶狀讀數，OTM LEAPS 的 EEP 殘差遠小於
  bid-ask 帶寬（本例 1.1 個機率點，§4.2）**，屬可忽略級。
- **何時不可忽略**：買腿深 ITM（劇本接近成立、spread 漸趨滿值）
  ＋臨近除息時，EEP(K1) 上升，讀數上偏擴大。誠實處置：呈現層
  註明「美式報價，讀數含輕微上偏」，不做數值校正（校正需要
  美式定價模型＝引入 §3.3 力圖避開的整套假設，得不償失）。
- 注意：Cboe 快照的 `iv` 欄位是含股利美式二項樹口徑
  （`cboe-field-semantics.md` §2.2）——但本讀數**不消費 IV，只
  消費價格**，該口徑問題與本路徑無關。

### 4.2 Bid-ask：呈現點值還是上下界

**呈現上下界＋一個主數字**。本例三個口徑差距（§3.4 表）：最差
9.6% vs mid 9.0% vs 最佳 8.5%——**整個 bid-ask 帶折合 1.1 個機率
點、最差對 mid 差 0.55 點**。語意各不相同：

- **最差成交（A14.2 既有口徑）**＝「你實際會付的定價」→ 讀數
  上緣。與產品所有成本數字同口徑，**建議當主數字**（口徑一致性
  是既有裁示的直接延伸）。
- **Mid**＝市場中心估計 → 「市場認為的機率」的最佳單點。建議
  並列（次要位置），因為「你付的」與「市場定的」之差正是成交
  摩擦的機率語言版本。
- 不建議只給單一點值：LEAPS 的寬市場下，掩蓋 ±0.5 點的不確定
  帶反而製造假精度。

### 4.3 Smile：修正項的載體就是 call spread 自己

教科書結論〔二手・索引轉述，Quant Next 等；與 Gatheral 式推導
一致〕：smile 存在時，digital 價 ≠ DF·N(d2)，而是

```
Digital(K) = DF·N(d2) − vega(K)·∂σ/∂K
```

**修正項量級（引擎實算，toy model）**：取 q=4.3%、線性 smile 過
兩腿報價 IV（12%→18%），帶狀中點 K=110 處 vega≈27.4（每單位
vol）、∂σ/∂K≈0.0015/$ → 修正 **4.5 個機率點**：未修正 N(d2)=10.1%
→ 修正後 5.5%。**修正項是讀數的一半量級**——LEAPS 的大 vega ×
TLT call wing 的上斜 skew，兩者相乘讓「拿單腿 IV 算 N(d2) 當機率」
在本產品場景完全不可用。

**而這正是 D/W 的全部優勢所在**：call spread 的市價是兩個**交易
出來的**價格之差，`−∂C/∂K` 的帶狀積分把 smile 的貢獻**如實內建**
——desk 給 digital 報價時用 call spread 對沖、教科書給 digital
定價時加 skew 修正項，兩者說的是同一件事：**call spread 本身就是
那個修正的載體**。讀 D/W 不需要（也不可以再）做 smile 修正。

同一 toy model 的自洽驗證（重現見下）：對 smile 一致的 digital 在
帶上數值積分 ÷W ＝ 0.0711，與模型 spread 價 ÷W ＝ 0.0711 **完全
相等**——§3.1 恆等式的數值確認。（toy model 之 C(90)=3.51 與
市場 mid 3.95 有差，因真實 q／美式性未精確校準——這差異本身再次
示範「自建模型難、讀市價穩」。）

```python
# PYTHONPATH=. .venv/bin/python；q=4.3%、線性 smile 12%→18%
# C(K)=BS_q(K,σ(K))；數值 -dC/dK 沿帶積分/W 與 (C(90)-C(130))/40 比對
# 結果：0.0711 == 0.0711（§3.1 恆等式成立）；vega(110)=27.4、
# 修正項=4.52 機率點、修正後中點 digital=5.5%、帶平均=7.1%
```

### 4.4 貼現：D/W 是「未貼現機率」嗎——不是

D/W 是**貼現後**的量（§3.1 恆等式右邊有 DF）。要說「機率」必先
除以 DF。量級：本例 T=2.416y、r=4% → DF=0.9079，**差 9.2%（相對）
＝約 0.8 個機率點**——LEAPS 上是一階效應，不可省。實作上 DF 用
既有 T12 期限對齊利率曲線（`leg_rate`）即可，**零新資料**。兩種
呈現皆有先例：Kalshi 的 ¢ 報價其實是貼現後的（短天期 DF≈1 被
忽略）；MS 明文「adjusting for the time value of money」。本產品
天期長，建議：**¢-per-$1 用原始 D/W（它就是實付價格，天然含
貼現），「隱含機率」一律用 ÷DF 後的數字**，兩者並列、各自標明。

### 4.5 補充：測度的精確名字

嚴格說 ÷DF 之後的量是 **T-forward measure 下的機率**（利率確定時
＝風險中性測度）；本產品用確定利率曲線，兩者無差，footnote 級
註記即可（自行推導；與 §2.2 央行文獻的口徑一致）。

## 5. 呈現先例與本產品的呈現建議

### 5.1 先例盤點

| 先例 | 呈現形式 | 對本產品的可借用點 |
|---|---|---|
| CME FedWatch〔官方・索引轉述〕 | 逐結局機率長條、跨會期機率樹 | 「機率」可以直白標成 %，公眾早已習慣 |
| Minneapolis Fed〔官方・索引轉述〕 | 「市場對事件指派的權重」措辭＋時間序列圖 | **措辭範本：「市場定價的機率」而非「機率」** |
| Morgan Stanley〔官方・索引轉述〕 | cost ÷ payout ＝機率，註明近似風險中性 | 讀數定義句型＋風險中性註記慣例 |
| Kalshi／Polymarket〔官方＋二手・索引轉述〕 | **1–99¢，¢ 數＝機率百分點** | ¢-per-$1 的直譯呈現（見下） |
| GS max payout ratio（既有研究 §2.3） | 「大於 8 倍」單一倍數 | payout ratio＝W/D，同一數字的 odds 面 |
| tastytrade POP〔二手・索引轉述〕 | `1 − credit/width` 標成 Probability of Profit | **反面教材**：把風險中性讀數直接標成真實勝率——本產品不跟進 |

### 5.2 ¢-per-$1 是否適合借用——適合，且是零失真的那一個

spread payoff ÷ W 之後就是一張「結算上限 $1」的合約（帶內部分
給付），**「付 8.7¢ 換每 $1 上限」不是類比，是恆等式 §3.1 的白話
直譯**。相對地「機率 X%」隔了兩層翻譯（÷DF、帶狀平均→點機率的
誤讀風險）。建議的欄位家族（事實性數字、無主觀標籤，落
`option-strategy-report-conventions.md` §4.1 骨架的 ① 關鍵指標表
或 ④ 風險與代價區）：

```
市場定價（最差成交）   8.7¢ / $1 上限     （mid：8.2¢）
隱含帶狀平均機率       ≈ 9.6%（風險中性，已除貼現因子 0.908）
等價 odds              約 10.5 賠 1（payout ratio 11.5×）
```

尾註（方法論慣例位置）：「機率為 90–130 帶狀之風險中性平均、
非漲到特定價位之機率、非預測；美式報價含輕微上偏；口徑＝最差
成交。」——與既有「合理基礎可追溯」慣例（同文件 §2.5）對齊。
**「勝率」二字全程不用**；FINRA 語感上這也是「暗示未來績效」的
高風險詞（同文件家族 E 的品質標準借用）。

## 6. 誠實侷限：能與不能回答什麼

**能回答**：
1. 「市場對『這個結局』收多少價」——絕對定價，零參照歷史、零
   參照鄰居。你付 8.7¢ 換每 $1，市場就是這樣定這注的 odds。
2. 「你付的 vs 市場中心定價」——最差成交與 mid 的機率點差，把
   成交摩擦翻譯進同一單位。
3. 跨 candidate、跨到期的**同單位比較**（¢-per-$1 對任何 W、任何
   期限可比）——池級套用（地圖 #95 對路徑 6 的注記）在讀數層
   自動成立。

**不能回答**：
1. **市場定的機率對不對**——那是 edge vs 自建預測分布（地圖
   7b），本輪明確不做。D/W 高不代表貴、低不代表便宜；只代表
   市場如此定價。
2. **真實世界勝率**——風險中性機率含風險溢酬。股票 put 端方向
   有共識（隱含>真實）；**TLT 的 call 端主要混入債券期限溢酬與
   利率風險定價，方向並無教科書共識**——正因如此更不能標
   「勝率」〔央行文獻對轉換之不確定性的自述，索引轉述〕。
3. **相對歷史的位置**——D/W 是當下快照的絕對讀數；「這個 odds
   在自己歷史上高還是低」屬路徑 8（R3）。
4. 市場本身的不精確：LEAPS 寬 bid-ask 下「市場的機率」自帶
   ±0.5 點帶寬（§4.2）；成交稀疏時 quote 未必代表可成交深度
   （`option-liquidity-filtering.md` 的既有結論沿用）。

## 7. 給 G1 的結論段（供裁示，非量化背景可讀）

- **這條路徑回答哪一種「貴」**：「**這注的 odds**」。把 spread
  的標價換算成「付幾 ¢ 換每 $1 上限」——跟 Kalshi 上看一個事件
  合約標價 38¢ 完全同一種讀法。它是**絕對**讀數：不跟歷史比、
  不跟隔壁合約比，就是市場此刻對這個結局開的價。四條研究路徑裡
  只有它把「貴不貴」直接翻譯成「機率／odds」這種人人能讀的單位。
- **最小實作需要什麼資料**：**零額外資料**。D（既有最差成交／mid
  成本欄位）、W（兩腿履約價差）、貼現因子（既有 T12 期限對齊
  利率曲線）——全部已在快照與契約裡；計算是十行以內的純算術
  （形狀同 `catchup_price()`，落 `valuation.py` 新純函式＋
  serialize 一欄），無 vendor、無歷史序列、無新模型。四條路徑中
  資料負擔並列最輕（與 R2 同為「僅當下快照」）。
- **建議的呈現形式**（標示層，不進排名）：三行欄位家族——
  「市場定價 8.7¢/$1 上限（最差成交；mid 8.2¢）」＋「隱含帶狀
  平均機率 ≈9.6%（風險中性）」＋「等價 odds 約 10.5 賠 1」；
  尾註標明帶狀平均、非勝率、非預測、美式輕微上偏。**不用
  「勝率」二字**。
- **主要陷阱已全部有處置**：貼現（÷DF，既有利率曲線）、bid-ask
  （上下界並列，主數字沿用 A14.2 口徑）、smile（不需處理——
  spread 市價已內建，這正是選它而非 N(d2) 的理由）、美式性
  （OTM LEAPS 下小於 bid-ask 噪音，尾註揭露即可）。
- **與其他路徑的界線**：路徑 2/3（vol 空間、相對歷史）答「這個
  市場環境下 vol 賣得貴嗎」；路徑 4（R2）答「這兩腿相對鄰居有
  沒有標錯價」；**本路徑答「這注 odds 是多少」**——三者正交，
  可並存於同一 card 的不同列。它**不**答「這 odds 值不值得接」
  ——那需要自己的預測（7b），是產品哲學層的另一個決定。

## 8. 未能查證的事項

1. **本輪零一手逐字來源**（§0）：Figlewski《Risk Neutral Densities:
   A Review》與 Morgan Stanley《How Options Implied Probabilities
   Are Calculated》兩份 PDF 均實測被擋，內容為索引轉述；MS 的
   「butterfly cost ÷ payout＋時間價值調整」句型經索引近逐字摘錄，
   未逐字核對原件。
2. **Breeden–Litzenberger (1978) 原文**未取得；§3.1 恆等式為自行
   推導（標準教科書結果），不依賴原文措辭。
3. **BoE「每日估算」與 Minneapolis Fed 方法細節**（Shimko 擬合、
   發布頻率）為官方頁面／PDF 的索引轉述，未逐字核對。
4. **Delta Quants／The Financial Engineer 的 overhedge 慣例描述**
   為 quant 實務站點轉述，非任何投行內部規範原件；兩站獨立一致。
5. **tastytrade POP 公式**（`100 − credit/width×100`）為教育內容
   索引轉述；其平台實際計算另有以 delta／模型為底的版本，未逐一
   核對——本文只引用其「spread 價/width 當機率」的慣例存在性。
6. **Moontower 對 value/width＝中點以下機率的表述**為索引摘錄，
   未核對原文全文；作者的 SIG 背景為公開自述。
7. **EEP 在 OTM LEAPS 上「遠小於 bid-ask」的量級判斷**是方向性
   推理（EEP 單調性＋文獻對 OTM 提前履約條件的共識），本輪未
   對 TLT 實際合約做美式/歐式雙模型定價差實測——引擎無美式
   定價器，補實測需新工程，列為若進 spec 的驗證項。
8. **N(d1)−N(d2) 差距「隨 σ√T 放大」的多來源轉述**：方向經
   Macroption／Quora／Medium 等多來源交叉，公式 `N(d1)−N(d2)`
   的近似展開為自行推導。
9. **q=4.3% 的 TLT 配息率**為量級假設（與既有研究「配息率與利率
   同量級」一致），非當日精確殖利率；§3.3／§4.3 的數字只用於
   示範敏感度方向與量級。

## 9. 來源清單

**標記說明**：本輪無〔一手・逐字〕級來源（§0）。
〔官方・索引轉述〕＝發布者官方頁面／PDF，僅經搜尋索引摘錄；
〔二手・索引轉述〕＝第三方整理。自行推導與引擎實算在正文逐處標明。

理論與綜述
- 〔官方・索引轉述〕Breeden, D. & Litzenberger, R., "Prices of
  State-Contingent Claims Implicit in Option Prices", *Journal of
  Business* 51(4), 1978（經 BoE／Minneapolis Fed 方法文件與多來源
  索引轉述）
- 〔官方・索引轉述〕[Figlewski, S., "Risk Neutral Densities: A Review" (NYU Stern, 2017)](https://pages.stern.nyu.edu/~sfiglews/documents/RND%20Review%20ver4.pdf)（被擋）
- 〔官方・索引轉述〕[Lind, P. P. & Gatheral, J., "NN de-Americanization" (SSRN 4616123；Quantitative Finance 25(1))](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4616123)；[Calibration to American Options: Numerical Investigation of the de-Americanization (arXiv:1611.06181)](https://arxiv.org/pdf/1611.06181)

Digital／call spread 替代與 skew 修正
- 〔二手・索引轉述〕[Quant Next — Binary Options: Pricing, Replication and Skew Sensitivity](https://quant-next.com/binary-options-pricing-replication-and-skew-sensitivity/)
- 〔二手・索引轉述〕[Delta Quants — Managing risks of Digital payoffs - Overhedging](http://www.deltaquants.com/managing-risks-of-digital-payoffs-overhedging)
- 〔二手・索引轉述〕[The Financial Engineer — Managing risks of Digital payoffs – Overhedging](https://thefinancialengineer.org/2014/12/06/managing-risks-of-digital-payoffs-overhedging/)
- 〔二手・索引轉述〕[quantpie — Cash or Nothing binary：BS 閉式解與 Greeks](https://www.quantpie.co.uk/bsm_bin_c_formula/bs_bin_c_vega.php)
- 〔二手・索引轉述〕[Roundhill — What is a Digital Option?](https://blog.roundhillinvestments.com/what-is-a-digital-option)

央行與官方機率發布
- 〔官方・索引轉述〕[Bank of England — Terminology and concepts: implied probability density functions](https://www.bankofengland.co.uk/-/media/boe/files/statistics/option-implied-pdfs/terminology-and-concepts-implied-probability-density-functions.pdf)；Clews, Panigirtzoglou & Proudman (2000, QB)；[Smith, T. (2012 Q3) — Option-implied probability distributions for future inflation](https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/2012/option-implied-probability-distributions-for-future-inflation.pdf)；[CCBS — Deriving option-implied probability densities for FX](https://www.bankofengland.co.uk/-/media/boe/files/ccbs/resources/deriving-option-implied-probability-densities-for-foreign-exchange-markets.pdf)
- 〔官方・索引轉述〕[Minneapolis Fed — Current and Historical Market-Based Probabilities](https://www.minneapolisfed.org/banking/current-and-historical-market--based-probabilities)；[Methodology PDF](https://www.minneapolisfed.org/-/media/assets/banking/current-and-historical-market-based-probabilities/methodology.pdf)；[Background, Commentary, and Analysis](https://www.minneapolisfed.org/banking/current-and-historical-market--based-probabilities/market-based-probabilities-background-commentary-and-analysis)
- 〔官方・索引轉述〕[Federal Reserve Board — Option-implied LIBOR Rate Expectations across Currencies (IFDP, 2016)](https://www.federalreserve.gov/econres/ifdp/option-implied-libor-rate-expectations-across-currencies.htm)

賣方與交易所呈現
- 〔官方・索引轉述〕[Morgan Stanley Research — How Options Implied Probabilities Are Calculated](https://www.morganstanley.com/content/dam/msdotcom/en/assets/pdfs/Options_Probabilities_Exhibit_Link.pdf)（被擋）
- 〔官方・索引轉述〕[CME Group — Understanding the CME Group FedWatch Tool Methodology](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html)；[FedWatch User Guide](https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html)
- 〔二手・索引轉述〕[iPredicta — How to Read Kalshi Odds](https://ipredicta.co/learn/how-to-read-kalshi-odds/)；[SI — Kalshi vs. Polymarket](https://www.si.com/prediction-markets/reviews/kalshi-vs-polymarket)；[MetaMask — Kalshi vs Polymarket 2026](https://metamask.io/news/kalshi-vs-polymarket)

交易員圈慣例與 proxy 辨析
- 〔二手・索引轉述〕[Moontower — a deeper understanding of vertical spreads](https://moontowermeta.com/a-deeper-understanding-of-vertical-spreads/)
- 〔二手・索引轉述〕tastytrade POP 教育內容（`100 − credit/width×100`，經 [datadrivenoptions](https://datadrivenoptions.com/strategies-for-option-trading/favorite-strategies/credit-put-spread/) 等轉述）
- 〔二手・索引轉述〕[Macroption — Delta of Calls vs. Puts and Probability of Expiring ITM](https://www.macroption.com/delta-calls-puts-probability-expiring-itm/)；[Medium (R. Gomes) — Is Delta the same as ITM probability?](https://medium.com/@rgaveiga/is-delta-the-same-as-in-the-money-probability-8df723bb4fe4)

風險中性 vs 真實世界
- 〔官方・索引轉述〕[Implied risk-neutral probability density functions from option prices: a central bank perspective (ScienceDirect chapter)](https://www.sciencedirect.com/science/article/abs/pii/B978075066942950011X)；[BoE WP455 — Estimating probability distributions of future asset prices](https://www.bankofengland.co.uk/working-paper/2012/estimating-probability-distributions-of-future-asset-prices)
- 〔二手・索引轉述〕[Newfound Research — Are Market Implied Probabilities Useful?](https://blog.thinknewfound.com/2017/11/market-implied-probabilities-useful/)；[Freeport Logbook — Options Implied Distributions are NOT Real-World Distributions](https://freeportlogbook.substack.com/p/options-implied-distributions-are)

本 repo（引擎、資料與既有研究）
- `option_chaser/valuation.py` —— `norm_cdf`／`days_between`（§3.4、
  §4.3 實算）；`catchup_price()`（最小實作的形狀先例）
- `tlt_report.md`（commit `8625fad`）—— §3.4 輸入的真實 TLT LEAPS
  雙邊報價
- `docs/research/candidate-iv-relative-value.md` —— §11 同一組
  candidate 輸入；§7.4 的 q=0 引擎偏差實測（本文 §3.3 依據）
- `docs/research/cboe-field-semantics.md` §2.2 —— Cboe `iv` 美式
  口徑（本文 §4.1 注記）
- `docs/research/option-liquidity-filtering.md` —— LEAPS 報價
  義務與深度（本文 §6 第 4 點）
- `docs/research/option-strategy-report-conventions.md` —— 呈現
  骨架與「機會必配風險」慣例（本文 §5.2 落位依據）
