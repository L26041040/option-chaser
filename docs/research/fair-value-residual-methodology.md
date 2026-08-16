# 合理價殘差（Rich/Cheap）方法論：從 Goldman Sachs SAS 到 Option Chaser 的單一選型

研究日期：2026-08-16。

**研究問題**：同一張實際掛牌合約的「市價 − 合理價」殘差歷史序列中，
**每個歷史日 t 的「合理價（fair value）」該怎麼算？**

範圍聲明（需求方已裁示、本文不重新討論）：canonical 序列固定為
**同一張合約**的殘差歷史、最多顯示一年、有多少畫多少、標示實際涵蓋期間與
觀測筆數、percentile 與 Δ4w 都跑在同一條序列上、**永不**偷換成固定期限／
固定 delta 的合成合約。本文只回答「fair value 怎麼算」這一個問題。

取材限制聲明：本沙箱出口 proxy 對多數金融網站直接抓取回 403/EGRESS_BLOCKED，
本次被擋的包括 `emanuelderman.com`、`arxiv.org`、`cdn.cboe.com`、
`www.dolthub.com`、`engineering.nyu.edu`。**核心一手文獻例外**：
Zou–Derman SAS 原文 PDF 自 GitHub 鏡像抓下後以 `pypdf` 完整解出 36 頁全文，
本文所有 SAS 相關引文與公式**皆為逐字核對原文**（標為「原文實證」）。
其餘文獻多數靠搜尋引擎索引的官方／期刊頁摘錄取得（標為「搜尋索引轉述」）。
無法以任一方式確認者一律列入 §12。

---

## 0. 執行摘要（先給答案）

**建議採用 SAS-L（Level-only Strike-Adjusted Spread）**：對每一張合約、每一次
快照，先用 put-call parity 從該到期日的市場報價反解出 implied forward F(T)
（一併吸收股息與 borrow），用 Black-76 從 mid price 反解出市場隱含波動率
σ_mkt；另一邊用標的自身日線報酬跑一條 **variance-targeting GARCH(1,1)**
遞迴得到當下的條件變異數，再用 GARCH 的期限結構公式把它**對齊到該合約剩餘
年期**得到 σ_fair；殘差 = σ_mkt − σ_fair，**主單位是波動率點（vol points）**，
另附一個美元金額當「今天多付了多少」的門面數字。這是 Zou–Derman SAS 的
**level component**——原文的 shape component（歷史微笑曲線）在 LEAPS 期限上
統計上估不出來（20 年日線只給得出約 10 個互不重疊的兩年期觀測），必須誠實
放棄，而不是硬做。**垂直價差**的規則是：兩腿共用**同一個 σ_fair** 分別定價、
相減得淨權利金殘差，單位用**美元（及 D/W，除以價差寬度）而非 vol points**
（淨 vega 會過零，正規化會爆）；並且必須誠實標示：價差的殘差在數學上幾乎
純粹是一個 **skew 讀數**，不是 level 讀數。分類學上要講白：SAS-L 屬於
**IV − 波動率預測（variance risk premium）家族**，不是「絕對錯價」偵測器；
它宣稱的是「這張合約的隱含波動率，相對於標的自身價格史所支持的水準、且
相對於它自己過去一年的分布，現在偏高或偏低」。

---

## 1. 建議演算法：SAS-L

### 1.1 名稱與定位

**SAS-L = Strike-Adjusted Spread, level-only variant。**

命名的用意是不要騙人：它就是 Zou–Derman (1999) 的 SAS，把 shape component
明示設為零——等價於把 RNHD（risk-neutralized historical distribution）退化成
一個 lognormal，其寬度＝標的歷史報酬給出的、期限對齊的波動率預測。原文
把 SAS 拆成兩塊的邏輯（§3.5）在這裡被反過來用：GS 丟掉 level 保留 shape，
Option Chaser 丟掉 shape 保留 level。理由不是我們比 GS 聰明，而是使用情境
完全相反——GS 是造市台要對同一天的整條 skew 排序，Option Chaser 是方向性
買方要看**同一張合約**跨時間的貴賤，而且期限落在 LEAPS。詳細論證見 §7。

### 1.2 符號表（每個符號都定義）

| 符號 | 意義 | 單位 |
|---|---|---|
| t | 快照時點（app 的一次 refresh） | — |
| S_t | 標的現價（快照的 `spot`） | $ |
| K | 合約履約價 | $ |
| K_L, K_S | 價差的買腿／賣腿履約價 | $ |
| T | 從 t 到到期日的年期（曆日 /365，沿用 repo 的 `DAYS_PER_YEAR`） | 年 |
| N | 從 t 到到期日的**交易日**數（≈ T × 252） | 日 |
| r(T) | 期限對齊的連續複利無風險利率（repo 既有 `rate_by_expiry`） | 年化小數 |
| F(T) | 該到期日的 implied forward（由 put-call parity 反解） | $ |
| q(T) | implied carry（股息＋borrow 合併），由 F 反推 | 年化小數 |
| C_mid(K), P_mid(K) | 該履約價 call／put 的 (bid+ask)/2 | $ |
| σ_mkt | 由 mid price 反解的市場隱含波動率 | 年化小數 |
| σ_bid, σ_ask | 由 bid／ask 分別反解的隱含波動率（誤差帶） | 年化小數 |
| u_i | 標的第 i 個交易日的日對數報酬 ln(C_i / C_{i−1}) | — |
| v_i | GARCH(1,1) 濾出的**日**條件變異數 | 日變異數 |
| V_L | 長期（無條件）日變異數，＝長樣本日報酬變異數 | 日變異數 |
| α, β | GARCH(1,1) 固定參數（**不做 MLE**） | — |
| φ | 持續度 φ = α + β | — |
| V̄(N) | 未來 N 個交易日的**平均**日變異數期望值 | 日變異數 |
| σ_fair | 期限對齊的合理波動率 = √(252 · V̄(N)) | 年化小數 |
| SASL(t) | 殘差主值 = σ_mkt − σ_fair | 波動率點 |
| D(t) | 殘差的價格版 = 市價 − 合理價 | $／股 |
| ν | vega（每 1.0 波動率變動的價格變動） | $／股／vol |
| W | 價差寬度 |K_S − K_L| | $ |

### 1.3 逐步計算（Call 與 Put 共用的前四步）

**Step 1 — 該到期日的 implied forward（吃掉股息與 borrow）**

對每一個到期日 T，在**兩邊都有有效雙向報價**（bid > 0、ask ≥ bid）的履約價集合上：

```
K*   = argmin_K | C_mid(K) − P_mid(K) |
F(T) = K* + e^{r(T)·T} · ( C_mid(K*) − P_mid(K*) )
q(T) = r(T) − (1/T) · ln( F(T) / S_t )
```

這是 Cboe VIX 方法論的第一步逐字照搬（F = K + e^{RT}(C − P)，K* 取
call/put 價差絕對值最小的履約價）
（<https://cdn.cboe.com/resources/indices/documents/SKEWwhitepaperjan2011.pdf>
與 VIX methodology；本次沙箱被擋，內容為搜尋索引轉述）。

**為什麼這一步是非做不可的**：repo 現行 `valuation.bs_call(S,K,T,r,sigma)`
**根本沒有股息參數 q**。TLT 這類每月配息的債券 ETF 年化配息率是幾個百分點，
兩年期 LEAPS call 在 q=0 假設下會被系統性高估。只要 fair value 這一側用
q=0、市場那一側用造市商含息的報價，殘差就會被一個跟 T 成正比的常數污染——
而且因為 T 一直在縮短，這個污染**會沿著序列漂移**，正好破壞我們最在乎的
「序列的時間變化要乾淨」。用 parity 反解 F 一次解決股息、特別股息、borrow
三件事，不需要任何股息預測。

若某到期日找不到任何雙向報價的履約價：取最近有解的到期日的 q(T′) 套用，
並在該筆記錄打 `forward_source = "borrowed"` 旗標；兩者皆無才退回 q = 0
並打 `"assumed_zero"`。**降級一律留痕，不無聲。**

**Step 2 — 反解市場隱含波動率 σ_mkt（用 Black-76，站在 forward 上）**

```
d1 = ( ln(F/K) + σ²T/2 ) / ( σ√T ) ,   d2 = d1 − σ√T
Call: C(σ) = e^{−rT} [ F·N(d1) − K·N(d2) ]
Put : P(σ) = e^{−rT} [ K·N(−d2) − F·N(−d1) ]
```

以 mid price 為目標，在 σ ∈ [0.01, 5.0] 上用 bisection（Brent 更好，但
stdlib 只要 bisection 就夠，價格對 σ 嚴格單調）解出 σ_mkt。同時解出
σ_bid、σ_ask 作為**該點的誤差帶**——這是幾乎零成本、卻讓整張圖誠實十倍的
一欄（LEAPS 的 bid-ask 常常寬到殘差本身的數量級，見 §6.2）。

**為什麼不直接用資料源給的 `iv` 欄**：Cboe 的 `iv`、yfinance 的
`impliedVolatility` 各自用不同的股息／利率／美式處理慣例，且供應商可以
無聲改版。我們的序列要跨月比較，**口徑一致比絕對正確更重要**；自己反解
才能把 r、q、模型版本一起版本化存下來。（此為工程推論，見 §10.2。）

**Step 3 — 合理波動率 σ_fair（標的自身歷史，期限對齊、會均值回歸）**

3a. 取標的日線收盤序列（越長越好，上限 10 年），算日對數報酬 u_i。

3b. 長期錨：V_L = 全樣本 u_i 的樣本變異數（日變異數）。

3c. 用 **variance targeting** 的 GARCH(1,1) 遞迴一路濾到今天，得到 v_t：

```
v_{i+1} = (1 − α − β)·V_L + α·u_i² + β·v_i ,    v_0 = V_L
```

固定 **α = 0.06、β = 0.92（φ = 0.98）**，**不做 MLE**。α = 0.06 沿用
RiskMetrics 的日頻衝擊權重（J.P. Morgan/Reuters RiskMetrics Technical
Document, 1996, λ = 0.94 ⇒ (α, β) = (0.06, 0.94)）；把 β 從 0.94 調到 0.92
是為了讓 φ < 1、產生均值回歸，φ = 0.98 落在日頻股票／ETF 常見估計區間
（NYU V-Lab GARCH 文件描述 α 典型 0.05–0.2、φ 逼近 1；
<https://vlab.stern.nyu.edu/docs/volatility/GARCH>，搜尋索引轉述）。
φ = 0.98 對應的衝擊半衰期 ln0.5/ln0.98 ≈ 34 個交易日。

3d. **期限對齊**（這一步是 SAS-L 相對於「教科書 IV − HV」的關鍵改良）：
GARCH(1,1) 的 n 日後條件變異數期望值是幾何衰減

```
E[v_{t+n}] = V_L + φⁿ · (v_t − V_L)
```

（Hull, *Options, Futures, and Other Derivatives*，GARCH 波動率期限結構節；
搜尋索引轉述確認此式）。對 n = 0…N−1 取算術平均，得到**未來 N 個交易日的
平均日變異數**（以下這一步是我自己的初等代數，可逐行驗算，見 §10.2）：

```
V̄(N) = V_L + (v_t − V_L) · ( 1 − φ^N ) / ( N · (1 − φ) )
σ_fair = sqrt( 252 · V̄(N) )
```

權重 w(N) = (1 − φ^N)/(N(1 − φ)) 就是「今天的波動率狀態在這個期限上還剩
多少話語權」：

| N（交易日） | ≈ 期限 | φ=0.97 | **φ=0.98** | φ=0.99 |
|---|---|---|---|---|
| 21 | 1 個月 | 0.750 | **0.823** | 0.906 |
| 63 | 3 個月 | 0.451 | **0.571** | 0.745 |
| 126 | 6 個月 | 0.259 | **0.366** | 0.570 |
| 252 | 1 年 | 0.132 | **0.197** | 0.365 |
| 504 | 2 年 | 0.066 | **0.099** | 0.197 |

**這張表本身就是 SAS-L 在 LEAPS 上可信的理由**：兩年期時今天的波動率狀態
只佔 6.6%–19.7% 權重，剩下全是長期錨。因此**唯一的調參旋鈕 φ 在 LEAPS
上幾乎不影響結果**——若當下條件變異數是長期值的 1.5 倍、長期波動率 15%，
φ 從 0.97 掃到 0.99，σ_fair 只從 15.25% 走到 15.72%，**不到 0.5 個波動率點**
（我的算術，`(1-φ^N)/(N(1-φ))` 代入即得）。相對地，一年期以下 φ 的影響
明顯放大（252 日：15.49% ↔ 16.31%），這也如實反映了「短天期的合理波動率
本來就比較難講」。

**Step 4 — 殘差**

```
SASL(t) = σ_mkt(t) − σ_fair(T_t, t)              ← 主值，波動率點
D(t)    = Mid(t) − Black76(F, K, T, r, σ_fair)   ← 門面數字，$／股
帶      = [ σ_bid − σ_fair , σ_ask − σ_fair ]    ← 該點的報價寬度誤差帶
```

percentile 與 Δ4w 一律跑在 SASL(t) 這條序列上，不跑在 D(t) 上（理由見 §1.7）。

### 1.4 Call 怎麼算

完全照 Step 1–4，Black-76 用 call 式。TLT 這類配息標的的美式提前履約風險：
只在除息日前一天、深度 ITM 且剩餘時間價值 < 股息時才有意義；Option Chaser
的 delta band 是 0.35–0.65（`models.AnalysisParams.delta_bands`），落在這個
區間的 call 幾乎不可能提前履約，歐式反解的偏差可忽略。（推論，見 §10.2。）

### 1.5 Put 怎麼算

Step 1–4 相同，Black-76 用 put 式，但**多兩條紀律**：

1. **美式提前履約會污染反解**。美式 put 價 > 歐式 put 價，用歐式模型反解會
   得到**偏高**的 σ_mkt，殘差假性偏「貴」；偏差隨 ITM 程度與 r·T 增大，
   在「兩年期 + r≈4% + ITM」這個組合上不是小數。專業做法是換數值方法：
   OptionMetrics IvyDB 對美式選擇權一律用 Cox-Ross-Rubinstein 二元樹（含
   離散股息）反解 IV，只有歐式才用 Black-Scholes
   （<https://optionmetrics.com/>，搜尋索引轉述）。
2. **本文的建議是不換模型、換範圍**：把殘差序列限制在 OTM／ATM put
   （K ≤ F 附近），提前履約溢價可忽略；ITM put 一律在 UI 上標示
   「歐式反解，ITM 美式溢價未扣除」。理由是引一個二元樹進 `valuation.py`
   會把「stdlib math only」的分層原則和整個測試基準一起打掉，換來的精度
   在 Option Chaser 的 delta band 內幾乎用不到。（工程判斷，§10.2。）

另外，Step 1 的 K* 本來就取最接近 forward 的履約價，所以 **implied forward
本身不會被 ITM 美式溢價污染**——這是照抄 VIX 方法論順帶得到的好處。

### 1.6 Vertical Spread 怎麼算

**規則（照做即可）：**

1. 該到期日算**一個** σ_fair(T, t)。
2. **兩腿共用這同一個 σ_fair** 分別定價：
   `FV = Black76(F, K_L, T, r, σ_fair) − Black76(F, K_S, T, r, σ_fair)`
3. 市場淨權利金：**序列用 net_mid**（= 買腿 mid − 賣腿 mid），
   **不用 repo 排名主數字 net_worst**（買腿 Ask − 賣腿 Bid）。理由：net_worst
   把兩腿的 bid-ask 寬度整個灌進殘差，而 bid-ask 寬度隨流動性起伏、不是
   貴賤訊號；用 worst 會讓序列變成「造市商今天心情如何」的圖。net_worst
   繼續留給成本／排名（T12 附錄 A14.2 口徑不動），**殘差序列另立口徑並標明**。
4. 殘差：`D_spread(t) = net_mid(t) − FV(t)`，單位 **$／股**；正規化顯示用
   `D_spread / W`（除以價差寬度，無量綱、跨寬度可比）。
5. **不要**把兩腿的 vol point 殘差直接加減（見下）。

**為什麼兩腿一定要共用同一個 σ_fair**：合理價模型的誤差在兩腿之間幾乎完全
共同（同標的、同到期、同 r、同 F），相減會抵消。這是價差殘差**唯一**的
統計優勢，若兩腿各用各的 fair vol（例如各自的市場 IV）就自毀。

**價差殘差在數學上是什麼**（一階展開，我的推導，§10.2）：

```
D_spread ≈ ν_L(σ_L − σ_fair) − ν_S(σ_S − σ_fair)
         = (ν_L − ν_S)(σ_L − σ_fair)  +  ν_S(σ_L − σ_S)
             └── level 分量，被淨 vega 縮小 ──┘   └─ skew 分量 ─┘
```

相鄰履約價的 vega 相近（ν_L ≈ ν_S），所以第一項被壓得很小，**第二項主宰**：
價差的殘差 ≈ vega × 兩個履約價之間的市場 IV 差 = **一個 skew 讀數**。
這不是缺陷、是事實，而且與文獻一致：Zou–Derman 自己說 SAS 在流動市場的
常用形態就是把 level 固定成市場 ATM、讓指標「成為相對於歷史的 skew
richness 度量」（原文實證，§3.5）；業界把 skew 的相對價值用 25-delta risk
reversal 對照自身歷史來看，也是同一套邏輯（Cboe SKEW 白皮書把 skew 定義為
OTM put/call 定價的相對關係並公佈其歷史區間 100–150、均值 115；CME 的
CVOL Skew 教材同理）。

**因此 UI 上價差的 Rich/Cheap 必須寫成「這組價差的兩個履約價之間的 skew，
相對它自己過去一年偏陡／偏平」**，不能寫成「這組價差比合理價貴 X 元」。
常數偏移（我們的 fair value 是零 skew 的、市場永遠有 skew）在 percentile
裡自動抵消，所以序列本身仍然可用；能用的是**變化**，不是水準。

**訊噪比要誠實**：價差殘差的訊號（淨值）比單腿小，噪音（兩腿各自的 bid-ask）
比單腿大約 √2 倍。所以價差的殘差圖需要更寬的誤差帶，且更該用 net_mid 而
非 net_worst。（推論，§10.2。）

### 1.7 殘差的單位：為什麼主值是 vol points

**單腿：波動率點（vol points）。** 三個理由：

1. **一階等價於 vega 正規化的價格殘差**：ΔPrice ≈ ν·Δσ，所以
   「vol point 殘差」＝「除以 vega 的美元殘差」。與其自己除，不如直接在
   波動率空間裡量。
2. **同一張合約的 vega 在一年內會變動好幾倍**（隨 √T 衰減、隨 moneyness
   移動）。美元殘差因此**非定態**：同樣的貴賤程度，在 T=2y 是 $0.80，
   在 T=6m 可能只剩 $0.25。跑 percentile 會量到 vega 的漂移而不是貴賤。
   波動率點沒有這個問題。
3. **原文同意**：SAS 本身就是波動率點——Zou–Derman 結論節逐字寫
   "This spread represents the richness in volatility points of an option,
   compared to the history of its underlyer."（原文實證）。

**跨履約價／跨期限的行為**：vol point 在跨期限上仍不完全可比（同樣 1 個
vol point 在 2 年期上是幾倍於 1 個月期的金額），但**本序列固定在同一張
合約上**，跨期限可比性不是需求。跨履約價的比較（例如同一到期日的 Top 10）
若要並排，vol point 是四個候選單位裡最可比的一個。

**還要不要美元**：要，但只當**當下的門面數字**，不進 percentile。方向性
買方真正付的是錢，「以合理波動率算，你今天多付 $0.62／股（每口 $62）」
是必須顯示的一行。

**價差：美元與 D/W，不用 vol points。** 理由是垂直價差的**淨 vega 很小、
且在兩個履約價之間會過零**；用淨 vega 正規化會在分母趨零時爆掉。除以
價差寬度 W 得到的 D/W 是無量綱、天然落在小數區間、跨寬度可比，是這裡
唯一穩健的正規化。（推論，§10.2。）

### 1.8 每次快照要存什麼（決定序列能不能重算）

每個被釘選的合約、每次快照存一列：

```
contract_key, ts, S_t, F(T), r(T), q(T), T, N,
bid, ask, mid, sigma_bid, sigma_mkt, sigma_ask,
v_t, V_L, phi, sigma_fair, SASL, D,
forward_source, model_version
```

**存輸入、也存輸出**：存輸出讓圖秒開；存輸入（S、F、r、q、報價）讓模型
改版後可以**整條重算**而不必等一年重新累積。`model_version` 是硬性要求——
沒有它，某天調了 φ 之後畫出來的就是一條半新半舊的假曲線。

每列約 20 個浮點數 ≈ 200 bytes；一年約 250 列；就算 50 張釘選合約也只有
2.5 MB 量級，Neon 免費層綽綽有餘。（估算，§10.2。）

---

## 2. 資料需求逐項表

| 輸入 | 欄位／頻率 | 來源 | Option Chaser **今天**拿得到嗎 |
|---|---|---|---|
| 合約 bid/ask | 每合約、每次刷新 | Cboe delayed JSON（`data/cboe.py`），yfinance 備援 | ✅ 已在用 |
| 標的現價 S_t | 每次刷新 | 同上快照的 `spot` | ✅ 已在用 |
| 同到期日 call **與** put 的 mid | 每到期日、每次刷新 | 同一份 Cboe 全鏈（單一 GET 就含兩側） | ✅ 已有，但**現行 `filters.apply_filters` 只留 strategy 對應那一側**，反解 forward 需要繞過該過濾直接讀 `snap.contracts` |
| r(T) 期限對齊利率 | 每到期日、每日 | Treasury CMT 曲線（`ratecurve.py` + `data/treasury.py`） | ✅ 已在用；且 Treasury 端點回**整年 CSV**，歷史 r 可回溯 |
| q(T) 股息＋borrow | 每到期日、每次刷新 | **不外求**，由 put-call parity 反解 | ✅ 只要有兩側報價就有 |
| 標的日線收盤（5–10 年） | 日頻、每日一次 | 新增：Stooq CSV（免金鑰、stdlib urllib 可取，`https://stooq.com/q/d/l/?s=tlt.us&i=d`，**無官方文件的非正式端點**）；或 yfinance（本地有、serverless 刻意不裝） | ⚠️ **要新增一個 adapter**，難度與 `data/treasury.py` 同級 |
| 標的日線 OHLC | 日頻 | 同上（Stooq CSV 本來就給 OHLCV） | ⚠️ 同上；只在採用 Yang–Zhang 估計子時才需要（可選） |
| **歷史選擇權報價** | 每合約、每日 | **重點**：見 §9.1 | ❌ 回溯不可得（除非用 §9.1 的兩條線索之一），但 ✅ **app 自己的歷史結果檔已經逐腿存了 bid/ask/iv** |

**關鍵事實**：`store._leg()` 已經把每張候選合約的 `bid`／`ask`／`iv` 寫進
每一份結果檔，`workspace.spread_history()` 也已經在做跨快照的身份鍵聚合。
換句話說，**殘差可以在使用者既有的工作區資料上「回頭重算」**——只要
Treasury 歷史曲線（可回溯）與標的日線（可回溯）補齊即可。序列的起點是
使用者第一次刷新那天，而不是「今天」。

---

## 3. 原始 SAS 全解構（Zou & Derman, Goldman Sachs, July 1999）

以下全部為**原文實證**（PDF 全文自 GitHub 鏡像取得並解碼，
<https://github.com/colejhudson/goldman-sachs-quantitative-strategies-research-notes>）。

### 3.1 SAS 的定義

> "the SAS of an option is the spread between the current market implied
> volatility of that option and our model's estimate of its historically
> appropriate volatility."

形式定義（原文 p.3、p.13）：

```
SAS(K, T) = Σ(K, T) − Σ_H(K, T)
```

Σ(K,T) 是市場 Black-Scholes 隱含波動率，Σ_H(K,T) 是由 RNHD 算出的價格再
轉回 BS 隱含波動率。**單位是波動率點**。ATM 約束版：

```
SAS_ATM(K, T) = Σ(K, T) − Σ_H(K, T) ,  且約束 SAS_ATM(S_F[T], T) = 0
```

即 RNHD 被額外約束成「重現市場 ATM-forward 隱含波動率」，於是 SAS_ATM
量的是**skew 的貴賤**，前提是「ATM-forward 依定義是公平的」。

### 3.2 演算法四步（原文 p.2–3 逐字轉述）

1. **選一段「歷史上相關」的期間**，取標的在期間 T 上的報酬分布 P。
   原文的 return 定義（EQ 2）是**滾動重疊**的 N 交易日連續複利報酬：
   `R_i = log( S_{i+N} / S_i )`。範例用 12 年（1987/5–1999/5）日資料造
   三個月期分布。
2. 用 P 當 prior，**最小化相對熵**求出風險中性分布 Q，唯一約束是
   「Q 下標的期望值 = 當前遠期價」。這個 Q 叫 **RNHD**
   （Stutzer 1996 稱之為 canonical distribution）。
3. 用 RNHD 對**所有履約價**算折現期望payoff，再把價格轉回 BS 隱含波動率
   → Σ_H(K,T)，即「估計的合理波動率微笑」。
4. SAS = 市場 IV − Σ_H。

**Appendix B 的數學**（原文 EQ B1–B5）：

```
Min_Q  S(P,Q) = E_Q[ log( Q(S)/P(S) ) ]
s.t.   ∫ Q(S_T)·S_T dS_T = S_0 · e^{r_f T}        （forward 約束）
       ∫ Q(S_T) dS_T = 1                          （歸一化）

解：    Q(S_T) = P(S_T)·exp(−λ S_T) / ∫ P(S)·exp(−λ S) dS
```

λ 由 forward 約束數值求解。若再相信市場 ATM，就在上面多加一條「Q 產生的
ATM 隱含波動率 = 市場 ATM 隱含波動率」的約束，得 RNHD_ATM。

**forward／折現／股息的處理**：原文只在 forward 約束裡用
`S_0·e^{r_f·T}`（r_f = 當前無風險利率），折現用 `e^{−r(T−t)}`（EQ 1）。
**股息沒有出現在任何一條式子裡**——原文全篇處理的是 S&P 500、DAX、FTSE
指數與一籃子銀行股，把股息隱含在 forward 裡帶過。這是 1999 年賣方研究
報告的常態，但對 Option Chaser 的配息 ETF LEAPS 是**不能照抄的空白**
（見 §1.3 Step 1）。

**一個重要的腳註（原文 footnote 7）**：若歷史分布是簡單複利報酬的常態
分布，熵最小化得到的 RNHD **等於把歷史分布平移到風險中性漂移、形狀不變**。
也就是說，**在「歷史分布是常態」的極限下，整套熵機器退化成「把 drift 換掉、
用歷史波動率當寬度」**——這正是 SAS-L 在做的事。SAS-L 不是把 SAS 亂砍，
它是 SAS 在「不宣稱知道高階動差」時的自洽退化解。

### 3.3 GS 為什麼不信 level（原文自己的話）

三處，逐字：

> "The volatility skew, the relative gap between at-the-money and
> out-of-the-money implied volatilities for a given expiration, is more
> stable than the absolute level of at-the-money implied volatilities.
> Often, therefore, irrespective of historical return distributions, the
> current level of at-the-money implied volatility is the most believable
> estimate of future volatility. **It is likely that historical
> distributions tell us more about the higher moments of future
> distributions than it does about their standard deviation.**"

> "Skew slopes seem more stable than volatility levels. Therefore, we will
> focus here on the relation between the implied volatilities of different
> strikes that follows from these distributions, and pay little attention
> to the prevailing absolute level of implied volatility."

> "Most often, in liquid markets, we calibrate the SAS to be consistent
> with current at-the-money volatility, so that it becomes a measure of
> skew richness as compared with history."

**注意他們的論點實際上是什麼**：不是「level 有結構性偏誤（VRP）」，而是
**「歷史對二階動差（標準差）的預測力，比對高階動差（skew／kurtosis）的
預測力差；而且 skew 的形狀比 level 穩定」**——是一個**估計品質與穩定性**
的論證，不是一個風險溢酬論證。這點很重要，因為它意味著：GS 沒有說 level
分量「沒有意義」，只說「用歷史去估它不如直接用市場」。

原文還誠實揭露了自家方法最大的弱點：Figure 5 vs Figure 6，同一批 1999/9
到期的 SPX 選擇權，歷史窗含 1987 crash 時 OTM put 顯示「略便宜」，把
crash 排除（1988/5 起算）後同一批 OTM put 變成「貴得離譜」——**符號翻轉**。
原文的自白：

> "There is no escaping the judgement necessary to decide which past period
> is most relevant to the current market from both a fundamental and
> psychological point of view."

### 3.4 level 的問題是不是結構性的？——是，而且無解

GS 給的是估計論證，但文獻給的是更硬的結構論證：**implied 系統性高於
subsequent realized，因為 variance risk premium 是真的**。

- **Carr & Wu (2009), "Variance Risk Premiums", RFS 22(3):1311–1341**
  用選擇權組合合成 variance swap rate，對五個股價指數與 35 支個股量測
  realized variance 與 swap rate 的差，建立了 variance risk premium 的
  model-free 量測框架（<https://academic.oup.com/rfs/article-abstract/22/3/1311/1581057>，
  搜尋索引轉述）。
- **Bakshi & Kapadia (2003), "Delta-Hedged Gains and the Negative Market
  Volatility Risk Premium", RFS 16(2):527–566**：delta-hedged 選擇權組合
  的報酬**系統性低於零**，且在高波動時期更負、在價外較不明顯
  （<https://academic.oup.com/rfs/article-abstract/16/2/527/1579962>，
  搜尋索引轉述）。
- **Ofek, Richardson & Whitelaw (2004), JFE 74(2):305–342**：put-call
  parity 的違反方向與放空成本高度相關，難借券標的的股價可比選擇權隱含
  價格高出達 7.5%（極端 1% 尾部）——即**供需與融券摩擦會直接寫進選擇權
  價格**（<https://pages.stern.nyu.edu/~rwhitela/papers/options%20jfe04.pdf>，
  搜尋索引轉述）。

**結論（我的判讀，§10.2）**：level 分量的偏誤是**結構性的、不可能被更好的
估計技術消掉**——它由 variance risk premium、jump/tail risk 定價、供需
失衡三者共同構成，任何以「realized/歷史」為基準的 fair value 都會系統性
低於市場。但這**不代表 level 分量沒用**：

- 它對**同一張合約跨時間**的 percentile 而言，常數偏誤**會抵消**；剩下的
  是 VRP 的時間變化，那正是我們要看的東西。
- 而且它有**實證上的預測力**：Goyal & Saretto (2009), JFE 94:310–326，
  以「過去 12 個月日報酬標準差 − 最接近 ATM、約 1 個月到期的 call/put IV
  平均」排序，做多（做空）差距最大（最小）的組合，straddle 月報酬
  15%–17%、delta-hedged call 1.6%–1.8%
  （<https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001251>，
  搜尋索引轉述）。這是**同一族訊號**（level 殘差）最強的公開證據。
  ⚠️ 但要誠實標注三個範圍限制：那是**橫斷面**排序（跨股票）不是時間序列、
  是**一個月期**不是 LEAPS、且賺的是 delta-hedged／straddle 而不是方向性
  裸買。Option Chaser 的用法在這三點上都不同。

---

## 4. 1999 → 今：後繼方法實際上是什麼

| 路線 | 代表文獻／文件 | 真的被採用了嗎 |
|---|---|---|
| **參數化微笑擬合** | SVI；Gatheral & Jacquier, "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1):59–71 (2014)，提出 SSVI 並給出無靜態套利的封閉形式（<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2033323>）；SABR：Hagan et al. (2002), "Managing Smile Risk" | **是，這是賣方今天的主流**。但它是**擬合**不是**合理價**：它告訴你某個履約價偏離自己那條微笑多少，不告訴你整條微笑貴不貴 |
| **標準化曲面（vendor）** | OptionMetrics IvyDB US：對每檔每日用 kernel smoothing 造 moneyness×maturity 曲面，輸出 delta 10–90（間隔 5）、到期 10 日至 2 年的標準化點；美式用 CRR 二元樹（<https://optionmetrics.com/>） | 是，學術界事實標準。**Option Chaser 買不起也不需要** |
| **曲面 PCA** | Cont & da Fonseca (2002), "Dynamics of implied volatility surfaces", *Quantitative Finance* 2(1):45–60：Karhunen-Loève 分解出三個正交因子＝level／orientation（skew）／convexity（<http://rama.cont.perso.math.cnrs.fr/pdf/ImpliedVolDynamics.pdf>） | 是，但用途是**曲面動態建模與避險**，不是單張合約的貴賤 |
| **廠商的 forecast vs implied** | ORATS：把曲面拆成 20 日統計波動率預測、無限期 implied 預測、earnings、strike slope、curvature 等參數，再拿市場值對照預測值（<https://orats.com/blog/forecasting-the-options-volatility-surface>、<https://docs.orats.io/>） | 是，且**這就是 SAS-L 的商業版**：level 用波動率預測、shape 用 slope/curvature 預測 |
| **指數化的 skew 量測** | Cboe SKEW 白皮書（30 日 risk-neutral skewness，SKEW = 100 − 10S，歷史區間約 100–150、均值 115）；CME CVOL Skew | 是，且是「skew 相對自身歷史」這個用法的官方背書 |
| **IV − RV 篩選** | Goyal & Saretto (2009)；Cao & Han (2013) JFE；Vasquez (2017) JFQA（IV 期限結構斜率預測 straddle 報酬） | 是，學術界的標準「貴賤」定義 |
| **canonical valuation 本身** | Stutzer (1996) JF 51:1633–1652；Haley & Walker (2010) JFM「Alternative tilts for nonparametric option pricing」 | **只在學術界延續**。找不到任何公開證據顯示有交易台把 RNHD 當日常定價工具（§12） |
| **僅由標的報酬校準的封閉解 GARCH 定價** | Heston & Nandi (2000), RFS 13(3):585–625：affine GARCH，**只用標的歷史報酬與現價就能估計與實作**，含 Heston (1993) 為連續極限（<https://academic.oup.com/rfs/article-abstract/13/3/585/1576522>） | 學術上成立、業界少見於此用途。是 SAS-L 最強的競爭者，落選理由見 §7 |

**哪些是民間傳說**：「市場做市商用歷史分布算 fair value 來報價」——沒找到
任何一手證據。實際做法是校準到**當下的市場報價**（SVI/SABR/SSVI），歷史
只進入風險管理與相對價值篩選。Zou–Derman 自己也說明了原因：真正嚴謹的
「歷史合理價」要模擬整條動態避險路徑，而

> "the hedging errors due to inaccurate volatility forecasting and
> infrequent hedging make the resulting statistics inconclusive."

---

## 5. 分類學：四種東西，永遠不要混為一談

| # | 名稱 | 它回答什麼問題 | 它對什麼是瞎的 | 單位 |
|---|---|---|---|---|
| ① | **真・合理價殘差** | 「這張合約值多少錢？市價偏離多少？」 | 需要一個外生的「應該值多少」模型；模型錯了殘差就錯了。實務上沒有 model-independent 的版本 | $ 或 vol pt |
| ② | **IV − RV／variance risk premium** | 「這張合約的隱含波動率，相對標的實際／預期會走的幅度，是不是偏高？」 | 對 skew 瞎；且**結構性偏正**（VRP），不能當絕對錯價 | vol pt |
| ③ | **曲面相對價值殘差** | 「這個履約價相對**它自己所屬的那條微笑**是不是偏離？」 | 對整條微笑的貴賤完全瞎；每日重新擬合會把水準重新歸零 | vol pt |
| ④ | **IV percentile／IV rank** | 「標的現在的（通常是 ATM 30 日）IV，在自己過去一年區間的哪裡？」 | 對這張合約瞎、對合理價瞎、對期限結構瞎。IVR =（今日IV − 52週低）/（52週高 − 52週低）×100（<https://support.tastytrade.com/support/s/solutions/articles/43000539059>） | 0–100 |

**Option Chaser 採用 SAS-L 之後，它的「Rich/Cheap」宣稱實際上是 ②，
不是 ①。** 必須這樣寫進 UI 文案與 glossary：

> 「Rich/Cheap ＝ 這張合約的隱含波動率，減去用標的自身價格史推算、
> 已對齊到本合約剩餘期限的合理波動率。正值＝市場對這張合約收的波動率
> 溢價，高於標的歷史所支持的水準。長期而言這個值**本來就傾向為正**
> （波動率風險溢酬），所以只看它自己過去一年的相對位置，不看絕對正負。」

而**垂直價差的殘差**（§1.6）實際上滑向 ③ 的親戚——它是「同一到期日、
兩個履約價之間的 skew，相對零 skew 基準」，percentile 才把它變回可讀。

**絕對不能做的事**：把 ④ 貼上「合理價」標籤；把 ② 說成「這張選擇權被
低估了 X 元」；把 ① 和 ③ 混在同一張圖的同一條線上。

---

## 6. Long Call／Long Put／LEAPS 的專屬病理

### 6.1 為什麼 LEAPS 讓原始 SAS 直接出局

SAS 需要「期間 T 的歷史報酬分布」。原文用**重疊**窗（EQ 2 的滾動 R_i），
三個月期 × 12 年資料。搬到兩年期 LEAPS：

- 20 年日線 ≈ 5,040 個交易日；兩年期 = 504 個交易日；
  **互不重疊的觀測只有約 10 個**。
- 重疊窗可以造出約 4,500 個「觀測」，但它們的自相關極高，**有效樣本數
  仍然是個位數**。而微笑的形狀由分布的**尾部**決定——十個觀測估不出尾部。

這不是實作困難，是統計上不存在的東西。原文自己在三個月期上就已經展示了
窗口選擇造成 SAS **符號翻轉**（§3.3）；兩年期上這個不穩定性只會更糟。
**所以 shape component 在 Option Chaser 的主戰場上必須放棄，不能硬做。**
（推導與算術為我的推論，見 §10.2；輸入的重疊窗定義與符號翻轉皆為原文實證。）

### 6.2 LEAPS 的其他病理，逐項

1. **bid-ask 寬到能吞掉訊號**。repo 的品質過濾容忍
   `spread ≤ max(0.10, 0.15 × mid)`（`filters.spread_ok`）——15% 的 mid。
   一張 mid = $6 的 LEAPS 可以合法有 $0.90 的價差；換算成波動率點可能是
   1.5–3 點，**與殘差本身同數量級**。⇒ 這就是 §1.3 Step 2 一定要同時
   反解 σ_bid / σ_ask 並在圖上畫誤差帶的原因。
2. **股息與利率敏感**。兩年期的 e^{−(r−q)T} 對 q 的誤差呈指數放大；TLT
   月配息不可忽略。⇒ parity 反解 forward（§1.3 Step 1）。
3. **borrow / hard-to-borrow**。Ofek-Richardson-Whitelaw (2004) 證實
   放空成本直接寫進 put-call parity 的違反；用 parity 反解 F **自動吸收**
   借券成本，不必另外建模。
4. **美式提前履約**（ITM put 為主）。見 §1.5。
5. **盤外報價與極稀交易**。已由 FB3-01（Cboe 主源，盤外凍結收盤報價）
   處理；殘留角落（整日無人報價）應在該筆記錄標 `stale`，**不要插值**——
   與 T11 `spread_history()`「缺席即斷點不插值」的既有裁示一致。
6. **序列取樣不規則**。快照由使用者手動刷新觸發，密度不均、且有自我選擇
   （使用者只在關心時才開 app）。這是 §11 的唯一阻塞點。

### 6.3 方向性買方到底該看哪一塊

方向性 Long Call／LEAPS 買方**不做 delta hedge**，他的損益主要由標的方向
決定，波動率只影響入場成本。因此：

- 對他有意義的是 **level 分量**（我付的權利金裡有多少是波動率溢價），
  不是 skew 分量。GS 丟掉的那一半，正好是 Option Chaser 唯一需要的那一半。
- **但要警告**：level 殘差為負（便宜）**不代表這筆交易會賺**，因為裸買
  的報酬由方向主導；殘差只在「同樣的方向觀點下，這個履約價／到期日的
  入場成本相對它自己的歷史是好是壞」這個窄義上有用。Goyal-Saretto 的
  超額報酬是**delta-hedged／straddle** 賺到的，不能移植成「裸買便宜的
  就會賺」（§3.4 的範圍限制）。

### 6.4 SAS-L 在 LEAPS 上的已知污染：strike-blindness

SAS-L 的 σ_fair 對履約價是平的。真實的合理微笑不是平的，所以當標的大幅
移動、固定履約價的合約沿著微笑滑動時，殘差會產生**與貴賤無關的漂移**。
量級估計（推論，§10.2，輸入為兩個引用值）：

- SAS 原文：三個月期 SPX 的 skew「typically about five volatility points
  for a 10% change in strike level」（原文實證）⇒ dσ/dk ≈ 0.5。
- ATM skew 斜率隨期限約以 T^{−1/2} 衰減（power-law decay 是公認的
  stylized fact；<https://hal.science/hal-04555805/document>、
  <https://arxiv.org/pdf/2312.15950>，搜尋索引轉述）⇒ 兩年期斜率
  ≈ 0.5 / √8 ≈ 0.18。
- 標的走 20%（Δk ≈ 0.18）⇒ 污染 ≈ 3 個波動率點（SPX 級 skew）。
  TLT 這類債券 ETF 的 skew 平得多，實際污染應小得多，但**不是零**。

**處理方式**：不修模型（修不了，見 §6.1），改成**在該筆記錄一併存下
delta 與 log-moneyness k = ln(K/F)**，並在圖上標出 moneyness 已大幅漂移
的區段。誠實揭露優於假裝沒有。

---

## 7. 為什麼是 SAS-L：候選方法評比

評比軸即需求指定的七項。✅ 好 / ⚠️ 有條件 / ❌ 不可行。

| 方法 | 時間穩定性 | 資料需求 | 參數敏感度 | 抗 bid-ask 噪音 | LEAPS 適用 | 計算成本 | Option Chaser 可實作性 |
|---|---|---|---|---|---|---|---|
| **① 原始 SAS / RNHD**（Zou–Derman, Stutzer） | ❌ 窗口選擇會讓符號翻轉（原文自證） | 20+ 年日線；期限 T 的**重疊**報酬分布 | ❌ 極高（歷史窗＝主參數且無客觀選法） | ⚠️ | ❌ 兩年期只有約 10 個獨立觀測 | ⚠️ 每合約一次熵最佳化＋逐履約價數值積分 | ❌ 且對使用者不可稽核 |
| **② SAS-L（建議）** | ✅ 參數固定、無滾動窗鬼影 | 5–10 年標的日線＋現有全鏈 | ✅ 兩年期 φ∈[0.97,0.99] 只差 <0.5 vol pt | ⚠️ 有噪音，但可用 σ_bid/σ_ask 明示誤差帶 | ✅ 期限對齊後自動收斂到長期波動率 | ✅ O(n) 一次遞迴＋每合約一次 bisection | ✅ 純 stdlib，與 `ratecurve.py` 同級 |
| **③ Heston–Nandi / Duan GARCH 定價** | ❌ 每日重估 5 個參數 → 合理價自己會跳 | 同 ② | ❌ MLE 不收斂／落在邊界是常態 | ⚠️ | ✅ 模型自帶期限結構 | ⚠️ 特徵函數數值積分＋MLE | ❌ 破壞 `valuation.py` 的 stdlib 分層，且無證據能改善 percentile |
| **④ SVI/SSVI 曲面殘差** | ❌ 每日重新擬合會把殘差重新歸零，序列近乎常數 | 每日全鏈（有） | ⚠️ 5 參數／slice，薄鏈易過擬合 | ❌ LEAPS 鏈稀疏，殘差≈報價噪音 | ❌ | ⚠️ 每到期日一次非線性最佳化 | ⚠️ 可做，但**回答的是別的問題**（分類 ③） |
| **⑤ 教科書 IV − 12 個月 HV**（Goyal-Saretto 式） | ⚠️ 等權滾動窗有 ghost feature（RiskMetrics 1996 §5 明載等權移動平均的鬼影／平台效應） | 標的日線 | ✅ 只有窗長 | ⚠️ | ❌ 拿 12 個月 HV 對兩年期 IV 是期限錯配 | ✅ | ✅ 但比 ② 差三點：無期限對齊、無 forward、無自反解 IV |
| **⑥ IV rank / percentile** | ✅ | 標的 ATM IV 歷史 | ✅ | ✅ | ⚠️ | ✅ | ✅ 但**沒有任何合理價內容**（分類 ④） |

**逐一說明為什麼落選**：

- **vs ①**：不是「太難」，是「估不出來」。§6.1 的十個獨立觀測是硬牆；
  且原文自己示範了窗口選擇造成符號翻轉。把一個作者本人都說「無法迴避
  主觀判斷」的量，做成一個給散戶看的單一 Rich/Cheap 數字，是欺騙。
- **vs ③**：Heston–Nandi 在理論上正是我們想要的（只用標的報酬、封閉解、
  自帶 skew 與期限結構）。落選的**唯一但決定性**理由是**序列穩定性**：
  每次快照重估參數，合理價會因為參數游走而跳動，而我們畫的是一年期的
  percentile。SAS-L 用固定 (α, β) ＋ variance targeting 換來的正是這個
  穩定性，而 §1.3 的權重表證明在 LEAPS 上這個「犧牲」只值不到 0.5 vol pt。
- **vs ④**：它回答的是別的問題。而且致命的是——每日重新擬合，殘差**依
  定義**在橫斷面上均值為零，同一張合約的殘差歷史會是一條圍繞小常數的
  噪音線，percentile 幾乎沒有資訊。
- **vs ⑤**：SAS-L 就是 ⑤ 的正確版本。三個具體修正：(i) 期限對齊（兩年期
  合約不該跟 12 個月 HV 比）；(ii) put-call parity forward（不然股息／
  borrow 會沿著 T 漂進殘差）；(iii) 自行反解 mid IV（口徑可版本化）。
- **vs ⑥**：IV rank 講的是標的、不是這張合約，而且與合理價無關。它可以
  當**旁邊的市場脈絡資訊**，不能當 canonical 序列。

---

## 8. 垂直價差：leg-by-leg 是不是成熟做法？

**是，但要看清楚「成熟做法」到底成熟在哪一段。**

- **定價這一段：確定是 leg-by-leg。** 賣方風險系統與資料廠商一律先建
  一條（單一）波動率曲面，再讓每一腿在該曲面上取值定價，組合價值＝各腿
  價值之和。OptionMetrics 的產品結構就是這樣（逐合約 IV／Greeks ＋ 一份
  標準化曲面），SVI/SSVI 的整個存在意義也是「給每一腿一個一致的取值」。
  **沒有任何證據顯示有人把 vertical spread 當成一個不可分割的原子去建
  合理價模型**——也沒有理由這樣做。
- **評價這一段：成熟做法是把它當 skew 部位看，而不是看「淨殘差多少錢」。**
  一手支持：Zou–Derman 的 SAS_ATM 就是把 level 釘死在市場、讓指標
  「成為相對於歷史的 skew richness 度量」（原文實證）；Cboe SKEW 指數以
  OTM put/call 的相對定價量測並公佈其歷史區間；CME CVOL Skew 是同類的
  交易所級指標。把 25-delta risk reversal 對照其自身歷史均值來判斷陡／平，
  是公開文獻與交易所教材都描述的做法。

**殘差相關性讓合併有沒有意義？——有，而且是正面的。** 兩腿共用 S、T、r、
F、σ_fair，模型誤差幾乎完全共同，相減時抵消；因此**價差的殘差對 fair vol
估計錯誤的敏感度，遠低於單腿**。這是價差殘差真正的統計優勢，而它成立的
前提就是 §1.6 的第 1 條：**兩腿必須共用同一個 σ_fair**。

**但訊噪比更差**：訊號（淨值）因為 vega 相消而縮小，噪音（兩腿各自的
bid-ask）相加。⇒ 價差圖需要更寬的誤差帶、且必須用 net_mid。

**該不該「直接對擬合的 skew 斜率評價」而不是走殘差？** 那是分類 ③ 的做法，
更精準，但它需要每個到期日有足夠多的有效履約價來擬合一條可信的 skew——
LEAPS 鏈上常常不成立（FB3-02／#45 就是為了「該期有效組數 < 3」而做的警示）。
所以本文建議維持 leg-by-leg 殘差，**但在文案上誠實標成 skew 讀數**。

---

## 9. 落地：Option Chaser 今天做得到什麼、做不到什麼

### 9.1 歷史選擇權報價：正面直視

**做不到的**：回溯取得任意歷史日的逐合約 bid/ask。這是硬限制，而且它
**與 fair value 選什麼模型無關**——不管用哪個模型，殘差的另一半（市價）
都必須來自那一天的真實報價。因此：

> **需要「上線第一天就有一年歷史」的演算法，一律不可實作。**
> SAS-L 不需要——它的 fair value 側完全由標的日線與 Treasury 曲線構成，
> 兩者都可回溯；受限的只有市價側。

**做得到的（三條，依可信度排序）**：

1. ✅ **app 自己已累積的結果檔**。`store._leg()` 每次刷新都存下每張候選
   合約的 bid/ask/iv，`workspace.spread_history()` 已在做跨快照聚合。
   ⇒ **序列可以從使用者的工作區「回頭重算」**，起點是他第一次刷新那天。
   這是零風險、零成本、今天就成立的一條。
2. ⚠️ **DoltHub `post-no-preference/options`**：公開、免費、2019 年至今的
   美股每日 option chain，2,098 個標的；DoltHub 提供 HTTP SQL API
   （`https://www.dolthub.com/api/v1alpha1/<owner>/<repo>/<branch>?q=<sql>`，
   任何唯讀 SQL 皆可）
   （<https://www.dolthub.com/blog/2024-09-27-dolt-post-no-preference/>、
   <https://docs.dolthub.com/products/dolthub/api/sql>，皆搜尋索引轉述——
   dolthub.com 在本沙箱被擋，**schema 未經查證**）。若其表確實含 bid/ask，
   一條 SQL 就能把單一合約一年的日線報價拉出來，**canonical 序列可以
   一次補滿**。這是本次調查最有價值的線索，但**必須先實測驗證**（§12）。
3. ⚠️ **Alpha Vantage `HISTORICAL_OPTIONS`**：指定日全鏈、含 IV 與全套
   Greeks、回溯 15 年；免費層 25 requests/day。補一年＝約 252 次呼叫
   ⇒ 免費層約 10 天可補完，或付費層一次補完。前次調查已記錄
   「免費層是否確含此端點」二手來源互相矛盾（`option-chain-data-sources.md`
   §3.4），本次搜尋傾向支持「免費層有歷史、即時要付費」，但仍未實測。

### 9.2 新增的工程項目（相對現況）

| 項目 | 落點 | 大小 |
|---|---|---|
| 標的日線 adapter | 新 `option_chaser/data/prices.py`（stdlib urllib，比照 `treasury.py`） | 小 |
| GARCH 遞迴＋期限聚合 | `option_chaser/volforecast.py`（純函式、零 I/O、可離線測） | 小 |
| parity forward 反解 | `valuation.py` 新增 `implied_forward()`；需要**繞過** `filters` 只留單側的行為，直接讀 `snap.contracts` | 小 |
| Black-76 ＋ IV 反解 | `valuation.py` 新增 `black76_price()`、`implied_vol()`（bisection） | 小 |
| 殘差組裝與持久化 | service 層新增 `residual_view()`；儲存見 §1.8 | 中 |

沒有任何一項需要新的第三方套件；全部 stdlib math，與 `valuation.py`
現行的「stdlib math only」原則相容。**serverless 每次請求的增量成本**
主要是標的日線抓取（可日快取）與一次 O(2500) 的遞迴——可忽略。

---

## 10. 證據分級

### 10.1 (a) 有引用來源的主張

- SAS 的定義、四步演算法、EQ 2 的重疊報酬定義、Appendix B 的熵最小化與
  解 Q(S)=P(S)e^{−λS}/∫、footnote 7 的「常態 ⇒ 平移不變形」、GS 對 level
  的三段自述、crash 含／不含造成的符號翻轉、「richness in volatility
  points」、「三個月 SPX skew 約每 10% 履約價 5 個波動率點」——**全部
  原文實證**，PDF 全文自
  <https://github.com/colejhudson/goldman-sachs-quantitative-strategies-research-notes>
  取得。
- Stutzer (1996) canonical valuation 的定位：
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb05220.x>
- VRP 結構性：Carr & Wu (2009) RFS；Bakshi & Kapadia (2003) RFS；
  Ofek/Richardson/Whitelaw (2004) JFE。
- level 殘差的預測力與其構造（12 個月日報酬標準差 vs 約 1 個月 ATM IV）：
  Goyal & Saretto (2009) JFE 94:310–326。
- SVI/SSVI：Gatheral & Jacquier (2014) *Quantitative Finance* 14(1):59–71。
- 曲面 PCA 三因子：Cont & da Fonseca (2002) *Quantitative Finance* 2(1):45–60。
- OptionMetrics 曲面方法（kernel smoothing、delta 10–90、到期 10 日–2 年、
  美式用 CRR 二元樹）。
- ORATS 把曲面拆成「統計波動率預測＋slope/curvature 預測」再與市場對照。
- Cboe SKEW 指數方法與歷史區間；VIX 方法論的 F = K + e^{RT}(C−P)。
- IVR 定義（tastytrade support）。
- RiskMetrics λ=0.94 與等權移動平均的 ghost feature。
- GARCH(1,1) 的 E[σ²_{n+t}] = V_L + (α+β)^t(σ²_n − V_L) 與
  V_L = ω/(1−α−β)。
- ATM skew 斜率隨期限約 T^{−1/2} 衰減為公認 stylized fact。
- Heston & Nandi (2000) RFS「可僅由標的歷史報酬估計與實作」。
- Yang & Zhang (2000) *Journal of Business* 73:477–492 的 OHLC 估計子
  （約較 close-to-close 高一個量級的效率）。
- DoltHub 資料集存在性、涵蓋 2019 至今、2,098 標的；DoltHub HTTP SQL API
  的 URL 形式。
- Alpha Vantage `HISTORICAL_OPTIONS` 涵蓋 15 年、含 IV 與 Greeks、
  免費層 25 req/day。

### 10.2 (b) 我的工程推論（可驗算，但沒有文獻直接背書）

- **兩年期 SAS shape 的十個獨立觀測**：5040/504 ≈ 10。純算術。
- **均值回歸權重表與 φ 敏感度**（<0.5 vol pt @ 2y）：由
  `w(N) = (1−φ^N)/(N(1−φ))` 直接計算，本文已列出數值。
- **V̄(N) 的封閉式**：由 GARCH 幾何衰減式對 n=0…N−1 取算術平均得到，
  初等代數，可逐行驗證。
- **價差殘差 ≈ ν(σ_L − σ_S) 的一階分解**，以及「兩腿共用 σ_fair 使模型
  誤差相消、但 bid-ask 噪音相加」的訊噪比結論。
- **常數偏誤在 same-contract percentile 中會抵消、只有時間變化留下**
  ——這是本文選擇容忍 VRP 偏誤的核心理由。
- **strike-blindness 污染量級 ≈ 3 vol pt @ SPX 級 skew、標的走 20%**
  （輸入的兩個數值有引用，合成是我的推論）。
- **不使用供應商 `iv` 欄、改自行反解**的口徑一致性論證。
- **價差序列改用 net_mid 而非 net_worst** 的理由。
- **儲存量估算**（每列 ~200 bytes、每年 ~250 列）。
- **TLT 級標的、delta 0.35–0.65 的 call 提前履約可忽略**。
- §9.2 的工程落點與工作量評估。

### 10.3 (c) 推測（沒有可靠證據，採用前要驗）

- DoltHub `post-no-preference/options` 的**表結構是否含 bid/ask**、
  是否涵蓋使用者實際查詢的標的（如 TLT）、HTTP SQL API 對大查詢的行為。
  **完全未查證**（域名被擋）。
- Alpha Vantage `HISTORICAL_OPTIONS` 免費層的真實可用性（二手來源矛盾，
  沿用前次調查的未決狀態）。
- Cboe 的 `iv` 欄與我們自行反解的 σ_mkt 會差多少（推測差在股息／美式
  處理，量級未知）。
- TLT 兩年期 ITM put 的美式提前履約溢價實際大小。
- φ = 0.98 是否適合 TLT 這類債券 ETF（股票指數的常見值；債券 ETF 的
  波動率持續度未查）。

---

## 11. 阻塞點

**證據足以定案，方法選型沒有阻塞。** SAS-L 的每一個組件都有一手或期刊
來源，取捨理由（LEAPS 的 shape 估不出來、序列穩定性優先、level 才是
方向性買方要看的一半）都可以由引用文獻與可驗算的算術支撐。

**但有一個唯一的、方法無法解決的阻塞未知**：

> **Option Chaser 的快照是使用者手動刷新觸發的，取樣不規則且有自我選擇
> 偏誤。任何跑在這條序列上的 percentile 與 Δ4w，其統計意義都建立在
> 「取樣與市場狀態無關」這個假設上，而這個假設在現行架構下不成立。**

具體來說：使用者在市場劇烈波動時更可能開 app 刷新，於是序列會超額取樣
高波動時段，percentile 因此系統性偏移；Δ4w 更直接——「四週前」在不規則
序列上可能根本沒有觀測點。這不是 fair value 模型能修的，也不是本次研究
能從文獻裡查出答案的；它需要一個產品／工程裁示（例如加一個每日固定時間
的 scheduled snapshot，讓序列變成規則日頻）。

**在該裁示做出前，percentile 與 Δ4w 應該標注「基於 N 筆不規則取樣」，
而不是呈現成日頻統計量。**

（另註：§9.1 的歷史回填線索若驗證成功，因為它是規則日頻的 EOD 資料，
**會順帶解決這個阻塞**——這是它值得優先實測的第二個理由。）

---

## 12. 未能查證的事項

- DoltHub `post-no-preference/options` 的 schema、標的覆蓋、資料品質
  （`www.dolthub.com` 全站被沙箱 proxy 擋）。
- Cboe VIX methodology 與 SKEW 白皮書的**原文逐字**（`cdn.cboe.com` 被擋；
  F = K + e^{RT}(C−P) 與 SKEW 的區間數字皆為搜尋索引轉述）。
- Gatheral–Jacquier 原文的 SSVI 公式細節（`arxiv.org` 被擋；只取得
  摘要級轉述）。
- Hull 的 GARCH 波動率期限結構節原文（教科書，無可抓取的線上原文；
  幾何衰減式經搜尋索引轉述確認，平均化那一步是本文自行推導）。
- Carr–Wu (2009) 的具體 VRP 數值與期限結構（PDF 主機被擋，只取得
  期刊摘要級描述）。**因此本文不引用任何 VRP 的具體百分比數字。**
- Goyal–Saretto 原文 PDF（只取得期刊頁與轉述；構造細節「12 個月日報酬
  標準差 vs 最接近 ATM、約 1 個月到期的 call/put IV 平均」為搜尋索引轉述）。
- ORATS 對 forecast 與 market 的比較究竟輸出成什麼指標（其
  Core Research PDF 未逐字取得）。
- Stooq CSV 端點的官方條款與速率限制（該站無官方 API 文件；端點形式
  為社群慣用）。
- 是否有任何交易台真的在日常業務中使用 RNHD／canonical valuation
  （反面證據亦未取得，屬「查不到」而非「證實沒有」）。

---

## 13. 引用清單

**一手（原文實證，本沙箱完整取得並逐字核對）**

- Joseph Zou & Emanuel Derman, *Strike-Adjusted Spread: A New Metric For
  Estimating The Value Of Equity Options*, Goldman Sachs Quantitative
  Strategies Research Notes, July 1999（36 頁全文）——
  <https://github.com/colejhudson/goldman-sachs-quantitative-strategies-research-notes>
  （原始出處 <https://emanuelderman.com/wp-content/uploads/1999/07/strike_adjusted_spread.pdf>、
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=170629>，兩者於本沙箱被擋）

**一手期刊／官方文件（搜尋索引轉述，未逐字核對原文）**

- Stutzer, M. (1996), *A Simple Nonparametric Approach to Derivative
  Security Valuation*, JF 51:1633–1652 —
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb05220.x>
- Carr, P. & Wu, L. (2009), *Variance Risk Premiums*, RFS 22(3):1311–1341 —
  <https://academic.oup.com/rfs/article-abstract/22/3/1311/1581057>
- Bakshi, G. & Kapadia, N. (2003), *Delta-Hedged Gains and the Negative
  Market Volatility Risk Premium*, RFS 16(2):527–566 —
  <https://academic.oup.com/rfs/article-abstract/16/2/527/1579962>
- Ofek, E., Richardson, M. & Whitelaw, R. (2004), *Limited Arbitrage and
  Short Sales Restrictions*, JFE 74(2):305–342 —
  <https://pages.stern.nyu.edu/~rwhitela/papers/options%20jfe04.pdf>
- Goyal, A. & Saretto, A. (2009), *Cross-section of option returns and
  volatility*, JFE 94:310–326 —
  <https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001251>
- Gatheral, J. & Jacquier, A. (2014), *Arbitrage-free SVI volatility
  surfaces*, Quantitative Finance 14(1):59–71 —
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2033323>
- Cont, R. & da Fonseca, J. (2002), *Dynamics of implied volatility
  surfaces*, Quantitative Finance 2(1):45–60 —
  <http://rama.cont.perso.math.cnrs.fr/pdf/ImpliedVolDynamics.pdf>
- Heston, S. & Nandi, S. (2000), *A Closed-Form GARCH Option Valuation
  Model*, RFS 13(3):585–625 —
  <https://academic.oup.com/rfs/article-abstract/13/3/585/1576522>
- Yang, D. & Zhang, Q. (2000), *Drift-Independent Volatility Estimation
  Based on High, Low, Open, and Close Prices*, Journal of Business
  73:477–492 — <https://www.jstor.org/stable/10.1086/209650>
- Hagan, P. et al. (2002), *Managing Smile Risk*, Wilmott Magazine（SABR）
- J.P. Morgan / Reuters, *RiskMetrics Technical Document*, 4th ed., 1996
  （λ=0.94；等權移動平均的 ghost feature）
- Hull, J., *Options, Futures, and Other Derivatives*，GARCH(1,1) 波動率
  期限結構節
- OptionMetrics IvyDB US（kernel-smoothed 曲面、CRR 二元樹）—
  <https://optionmetrics.com/>
- ORATS — <https://docs.orats.io/>、
  <https://orats.com/blog/forecasting-the-options-volatility-surface>
- Cboe SKEW 白皮書 —
  <https://cdn.cboe.com/resources/indices/documents/SKEWwhitepaperjan2011.pdf>
- CME Group, *Introduction to CVOL Skew* —
  <https://www.cmegroup.com/education/courses/introduction-to-cvol/introduction-to-cvol-skew>
- NYU V-Lab GARCH 文件 — <https://vlab.stern.nyu.edu/docs/volatility/GARCH>
- tastytrade, *Volatility Metrics (IVR, IV%, IVx, HV)* —
  <https://support.tastytrade.com/support/s/solutions/articles/43000539059>

**二手／線索（可信度較低，採用前需實測）**

- DoltHub `post-no-preference/options` —
  <https://www.dolthub.com/repositories/post-no-preference/options>、
  <https://www.dolthub.com/blog/2024-09-27-dolt-post-no-preference/>
- DoltHub SQL API — <https://docs.dolthub.com/products/dolthub/api/sql>
- Alpha Vantage `HISTORICAL_OPTIONS` — <https://www.alphavantage.co/documentation/>
- ATM skew 的 power-law 期限衰減 — <https://hal.science/hal-04555805/document>、
  <https://arxiv.org/pdf/2312.15950>
- Vasquez, A. (2017), *Equity Volatility Term Structures and the
  Cross-Section of Option Returns*, JFQA —
  <https://efmaefm.org/0efmameetings/efma%20annual%20meetings/2015-Amsterdam/papers/EFMA2015_0530_fullpaper.pdf>
- Stooq 日線 CSV 下載（無官方 API 文件）— <https://stooq.com/>

**本 repo**

- `option_chaser/valuation.py`（`bs_call`／`bs_put` **無 q 參數**；
  `evaluate_spread` 的 net_mid／net_worst 口徑；`catchup_price`）
- `option_chaser/filters.py:23-34`（quote_ok／iv_ok／spread_ok，
  `spread ≤ max(0.10, 0.15×mid)`）
- `option_chaser/models.py`（`delta_bands=(0.35,0.65)`、`OptionContract` 欄位）
- `option_chaser/data/cboe.py`（主資料源與缺值口徑）
- `option_chaser/ratecurve.py`／`option_chaser/data/treasury.py`
  （期限對齊 r(T)；Treasury 回傳整年 CSV ⇒ 歷史 r 可回溯）
- `option_chaser/store.py`（`_leg()` **已存逐腿 bid/ask/iv**；
  `serialize_result`）
- `option_chaser/workspace.py:228-255`（`spread_history()`：跨快照身份鍵
  聚合、缺席即斷點不插值）
- `docs/research/option-chain-data-sources.md`（資料源前次調查）
- `docs/research/risk-free-rate-for-bs.md`（利率口徑）
