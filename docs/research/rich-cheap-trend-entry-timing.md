# Rich/Cheap Trend——「現在進場還是再等等」的時間軸指標最終設計

研究日期：2026-08-14。本文是本 repo 第六輪選擇權貴賤判斷研究。前五輪
（`iv-relative-history-methodology.md`、`candidate-iv-relative-value.md`、
`spread-price-percentile-vs-vol-space.md`、`option-richness-assessment-methods.md`、
`modern-surface-methods-rich-cheap-architecture.md`）已把「**現在的狀態相對
歷史站在哪**」（座標正規化、percentile、橫斷面殘差）回答完畢；需求方明示
本輪**不要**再研究「今天哪個 strike 便宜、surface 上誰 mispriced、哪組
spread 贏過兄弟」——那些已由 Net Cost → Return → ranking 收斂。本輪的
新問題是**動態層（dynamics / entry timing）**：

> 這一組具體的 Call／Vertical Spread，相對它自己的可比歷史狀態，現在
> 便宜／正常／貴——**而且正在往哪個方向走**？「再等一下，歷史與當前
> 趨勢給不給一個等到更好進場價的合理機會」？還是「更好的價格已經出現過
> ／正在離開，現在就已經是相對好的進場點」？

**與前五輪不同，本輪依委託指示必須拍板**：不開菜單，收斂成一個最貼近
成熟 vol desk 實務、可直接在既有 `option_chaser/ivhistory.py` 基礎設施上
實作的單一設計。結論先講（§0），逐點論證與證據在 §1–§6，最終方案逐項
規格在 §7，證據強度逐項表在 §8，取材限制在 §9，與第五輪架構文件的關係
在 §10。

**開工前 checkout 核對**（依委託指示執行，寫檔前複驗一次）：HEAD ＝
`04dfcfca9a41befbe0148ac60360020c14dfc56c`，working tree 乾淨，非本專案
歷史上多次出現的容器回退狀態——本文所有【repo 實證】對著正確的 tree 做。

**證據分級**（沿用近三輪體系）：**【一手全文】**＝逐頁讀過原文 PDF；
**【搜尋索引轉述】**＝只讀到搜尋引擎摘要，未讀原文；**【repo 實證】**＝
本 repo 程式碼逐行覆核或引擎實算（附重現步驟）；**【本文推論】**＝自行
推導，明確標注。本輪經 GitHub 鏡像取得**三份新的一手全文**（Simon &
Campasano 2012、Cooper 2013、Carr & Wu 2005，見 §9），引用既有研究已
確立的結論一律標「（既有研究已證，見 X 文 §Y）」不重推。

## 0. 一句話結論（先給答案）

**在已出貨的 Historical IV Position 序列（固定 (tenor, delta) 逐日重錨定
的買腿 IV／賣腿 IV／Normalized Skew Ĝ，時間加權 percentile＋觀測筆數）
之上，只加一個趨勢統計量：Δ4w——同一條重錨定序列上「最新觀測值減去
約四週前觀測值」的原始變化量，以量自身的單位呈報（腿 IV 用 vol 點、Ĝ
無因次），與 percentile、觀測筆數並列成一行事實敘述；不加任何預測、
評價字眼、顏色暗示或象限標籤。** Long Call 模式主讀數＝買腿 IV 的
percentile＋Δ4w（level 語言）；Vertical Spread 模式主讀數＝Ĝ 的
percentile＋Δ4w（skew 語言），兩腿 IV 為次層輔助（與已出貨 MVP V3 的
資訊權重完全一致）。**零新增資料源、零新增 vendor 呼叫**——Δ4w 由既有
observation cache 的同一批點算出。四週這個 lookback 不是拍腦袋：它落在
IV level 因子 half-life 的證據帶（GARCH 持續性推出的 23–34 個交易日、
Cont–da Fonseca level 因子 OU 時間常數 28–51 天）內約一個 half-life，
也與 FX Risk Reversal 圈 1 個月 lookback 的成文慣例一致。**明確不做**：
IV Rank（第一輪已判）、z-score、volatility cone、per-symbol half-life
估計（66 點/年抽樣下數學上站不住）、模型化 expected drift／任何形式的
forecast（違反 facts-only 紅線，且 Harvey–Whaley 1992 證明 IV 變化的
統計可預測性換不到扣除成本後的 edge）、term-structure slope 進場訊號
（Simon–Campasano 一手全文：基差不預測 spot vol 的變化，預測的是期貨
持有報酬）、Markov regime-switching（desk 證據不足＋資料密度不可行）。

## 1. 問題定義：debit 的四分量分解，與「等待」的誠實帳本

### 1.1 分解式與本產品實際量級（【repo 實證】，可重現）

等待到明天再進場，同一組 debit 結構的進場成本變化一階近似為：

```
d(debit) ≈ Δ_net·dS ＋ vega_net·dσ̄ ＋ (∂V/∂G)·dG ＋ θ_net·dt （＋ρ_net·dr，LEAPS 才顯著）
            └ spot ┘   └ vol level ┘   └ skew gap ┘   └ 時間 ┘
```

其中 `σ̄` 為兩腿平均 IV 水位、`G = σ_sell − σ_buy` 為 skew gap——這是
第一輪 §5.1 已推導的分解（水位項權重 net vega、skew 項權重平均 vega），
本文只是把 `dS`、`dt` 兩項補回同一張帳本。用第二輪 §11 的旗艦實例
（TLT 2028-12-15 Bull Call 90/130，S=84.52、r=4%、IV 12%/18%、
T=882/365，`net_worst` debit＝$3.47）以本 repo `valuation.call_greeks`
實算（`PYTHONPATH=. .venv/bin/python`，q=0 顯示口徑，與 #122 分級路徑
同一假設）：

| 分量 | 引擎值 | 等待「一週」的典型量級（佔 debit %） | 等待「一個月」 |
|---|---|---|---|
| spot（net delta 0.4621） | 1σ 週波動 ±$1.43 → ±$0.66 | **±19.0%** | ±$1.35 → **±39%** |
| vol level（net vega +0.2038/pt） | 1 vol 點 → $0.20 | 5.9%／pt | 同左 |
| skew gap（平均 vega 0.4029/pt） | 1 vol 點 gap → $0.40 | 11.6%／pt | 同左 |
| theta（net −$0.00397/日） | 7 天 → −$0.028 | **−0.8%** | 28 天 → −$0.11 ＝ −3.2% |

（1σ 週／月 spot 波動以買腿 IV 12% 年化換算日波動 $0.639 推得；theta
為 q=0 口徑、LEAPS 天期下偏小，DTE 縮短後會顯著變大。重現步驟：本文
撰寫當日以上述指令對 `call_greeks(84.52, 90, 2.416, 0.04, 0.12)` 與
`call_greeks(84.52, 130, 2.416, 0.04, 0.18)` 直算，數字與第二輪 §11.2
的 net vega +0.2038、dV/dG −0.4029 完全一致。）

### 1.2 三個直接推論（本設計的邊界條件）

1. **「等更便宜的 debit」主要是 spot 的賭注，不是 vol 的判讀。**
   一週的 spot 不確定性（±19% of debit）就吞掉三個 vol 點的 level 變化；
   一個月是 ±39%。使用者的劇本本來就是「看漲」——等待＝對自己的方向
   論點反向下注，且 theta 在旁邊持續滴血（LEAPS 每月 ~3%，近月更兇）。
   **成熟實務從不假裝能 time spot**：desk 語言裡的 entry timing 指標
   一律掛在 vol 分量上（「vol 便宜時買結構」），spot 交給使用者自己的
   方向判斷。Natenberg 1994 的 vertical spread 選腿規則（「IV 太低就買
   ATM 腿」，第二輪 §3.1【一手全文】）、tastytrade 系「IVR 低利於
   debit spread」慣例（第一輪 §3.4）、Sinclair 對 variance premium
   「是長選擇權部位必須克服的潮水（the tide that long option positions
   need to overcome to be profitable）」的定位【搜尋索引轉述，經
   SpotGamma 支援文件轉引 *Volatility Trading*】——全部是同一個分工。
   **本輪指標因此只 scope 到 vol 分量（level 與 gap），並在方法論尾註
   對 spot 誠實**：它回答「你要買的 volatility 結構現在相對歷史貴不貴、
   往哪走」，不回答也不暗示「標的價格會不會給你更好的進場點」。
2. **對 Spread，gap 分量比 level 分量重一倍**（11.6% vs 5.9% per pt，
   第二輪 §11.3 同一結論）——趨勢層的主角必須是 Ĝ，不是腿 IV。§5 展開。
3. **theta 是「等待的已知成本」，可以直接算，不需要指標**——它已經在
   產品的估值與報告裡；本輪不為它新增顯示，但方法論尾註要把「等待有
   已知的 theta 成本」這句事實寫進去，才算把帳本攤完整。

### 1.3 「統計上可預測」≠「可以據此行動」：一開始就把野心關小

Harvey & Whaley (1992, "Market volatility prediction and the efficiency
of the S&P 100 index option market", *Journal of Financial Economics*
30, pp. 33–73)【搜尋索引轉述】：S&P 100 隱含波動率的**變化是統計上
可預測的**（拒絕「IV 變化不可預測」的假設），但用這個可預測性做交易
模擬，**扣除交易成本後沒有異常報酬**——市場有效性成立。這是本輪動態層
最重要的一條前置紀律：**指標的任務是把「位置＋方向」這兩件事實攤給
使用者，不是替他預測**。一個顯示「現在第 24 百分位、四週來 −1.8 pts」
的 card 已把歷史與趨勢交代完；把它加工成「預期還會再跌 X pts」就越過
了證據（與產品紅線）允許的線。

## 2. 可比序列：前五輪已解決，本輪原樣繼承（短）

趨勢統計量算在哪條序列上，前幾輪已把地基打完，本文不重推、只點名：

- **固定合約序列不可比**（DTE 遞減／moneyness 漂移／LEAPS 上市不滿一年
  ——第一輪 §3.1）；**固定合約 raw gap 序列同樣不可比**（skew 斜率
  ~1/√T roll-down：DTE 882→252 天 gap 6.0→11.2 pts 零環境變化——
  第二輪 §4.2）。
- **成熟解法＝每天在當日 surface 上取固定 (tenor, delta) 座標重錨定**
  （第一輪 §3.3、第二輪 §9.1；OptionMetrics／ORATS／FX RR 三方同款）；
  spread 的單一數字＝**Normalized Skew `Ĝ = (σ_s − σ_b)/σ_ATM`**
  （÷ATM 消 level 依賴——Mixon 2011、Natenberg 1994 y 軸、SAS_ATM
  三重先例，第二輪 §5）。
- **這條序列已經出貨**【repo 實證，本輪逐行重讀】：
  `option_chaser/ivhistory.py`——`iv_at()` 兩軸皆嚴格不外插（出界回
  `None`＝「超出可比網格」，LEAPS 超出當日抓到的到期日梯子時誠實留白）；
  `normalized_skew()`；`sampling_schedule()` 近 90 天每週約 2 點、90 天
  ～1 年每週約 1 點，全年約 66 點，crc32 決定性排程；`interval_weights()`
  Voronoi 時間權重、單點代表上限 14 天；`weighted_percentile()`
  「小於等於」含等於；`field_metrics()` 對 `normalized_skew`／`buy_iv`
  ／`sell_iv`／`atm_iv` 四欄各回 `{value, percentile, count}`，不設任何
  樣本數門檻（#133 裁示）。API 接縫在 `api_app/main.py`
  `GET /api/scenarios/{id}/iv-history`（第 798 行起；`field_metrics`
  與 `observations` 序列化在第 207–208 行），前端 `src/IvHistory.tsx`
  以「現值＋percentile＋觀測筆數＋compact sparkline」三指標呈現，
  facts-only 由測試守門。
- **紅線**（spec #117）：`ranking.py`／`filters.py` 不 import
  `ivhistory`（有測試斷言原始碼字面），enrich-only 是結構保證。本輪
  趨勢層是 `field_metrics` 家族的純加法延伸，紅線自動繼承。

**本輪唯一的新問題因此收得很窄**：在這條「已經正確可比」的序列上，
「位置」已有（percentile），**「方向」用什麼統計量、多長的 lookback、
怎麼呈現**。

## 3. Level 統計的專業實務：percentile／Rank／z-score／cone 四選一

### 3.1 四種統計量的實際使用版圖

| 統計量 | 誰真的在用 | 證據 |
|---|---|---|
| **Percentile**（經驗 CDF） | ORATS `ivPct1y`＋**slope percentile**（把橫斷面擬合的 skew slope 對自身歷史取百分位，「slope 在第九十百分位＝下檔保護比九成歷史觀測貴」）；Barchart IV Percentile；Market Chameleon IV30 % Rank（名為 Rank、算的是「過去一年有幾天低於現值」＝percentile） | 第一輪 §3.4【索引轉述】；ORATS "Is Skew Cheap Or Expensive?"／"Predictive indicators"【搜尋索引轉述，本輪新增】；Market Chameleon Volatility Rankings【搜尋索引轉述，本輪新增】 |
| **IV Rank**（min-max） | tastytrade 預設、Barchart、多數零售 screener | 第一輪 §2.1；對單一極端值高度敏感（一次尖峰壓低其後一整年讀數）已判定為本產品不用的理由 |
| **Z-score** | FX Risk Reversal 序列（1M/6M lookback，宏觀圈成文實務）；VRP z-score 慣例；零售 screener 亦有「IV Z-Score」欄位（PowerOptions） | 第二輪 §6.1；第五輪 §5.2；PowerOptions IV Rank Screener【搜尋索引轉述，本輪新增】 |
| **Volatility cone** | 教科書級經典：Burghardt & Lane (1990, "How to tell if options are cheap", *Journal of Portfolio Management* 16(2), p. 72) 提出——按持有天期分桶（30/60/90/120 天…）滾動計算歷史 realized volatility，各天期取 min／25%／median／75%／max 疊成錐形，再把**對應天期**的當前 implied vol 疊上去比；關鍵紀律＝**tenor matching**（1 個月 IV 只跟 1 個月 HV 分布比）；Hodges & Tompkins (2002, "Volatility Cones and Their Sampling Properties", *Journal of Derivatives* 10(1)) 補上重疊視窗抽樣偏誤的修正因子 | 【搜尋索引轉述，多來源交叉：Semantic Scholar／JPM 索引、Montreal Exchange 教材（PDF 本體被沙箱擋）、PyQuant News 等教學重述】 |

Sell-side 銀行週報級 screen（GS／JPM／MS 衍生品研究的 vol screens）的
內部方法論**本輪查不到公開文件**——搜尋只能到「GS 衍生品研究主管
Marshall 自述其篩選超越歷史波動與同儕比較、找資產負債表層級的不對稱」
這種訪談語言【搜尋索引轉述，證據弱】。可查證的替代證據是 vendor 端
同款產品：Bloomberg VCA 的 implied/realized rich-cheap 與「誰的 skew／
term structure 最陡」排序（第二輪 §8）、ORATS scanner 的 percentile
家族。**結論：percentile 與 z-score 兩者都是真實在用的縱軸統計，cone
是「tenor matching＋分布疊圖」的教科書標準**——這與第五輪 §5.4 的
詞彙表完全一致，本輪只是把 cone 補進版圖。

### 3.2 本產品的判定：維持 percentile（已出貨），不換、不加

1. **不採 IV Rank**：第一輪 §2.1 的極值敏感論證原樣有效。
2. **不採 z-score**：z-score 依賴均值與標準差，對離群值的敏感度與
   Rank 同病（第五輪 §6.4 對殘差量的同一推論延伸到本序列——一次爛
   報價反推的 IV 尖峰會同時污染分子與分母）；66 點/年的不均勻抽樣下
   還要決定加權標準差的口徑，多一套統計換不到資訊增量；且 z-score 的
   「±1.5σ」語言隱含常態假設，IV 分布右偏眾所周知。FX RR／VRP 圈用
   z-score 是因為那些量近似平穩對稱——腿 IV 與 Ĝ 不具備這個性質。
   percentile 已出貨、有 ORATS 同款先例（slope percentile 尤其是
   「橫斷面衍生量的時間序列 percentile」的直接先例），維持。
3. **不採 cone**：cone 回答的是「**IV vs 各天期 realized vol 分布**」
   ——它的比較對象是 RV，不是 IV 自己的歷史；那是第一輪方案 E
   （IV/HV，量 risk premium）的圖形化親戚，不是本輪「相對自身歷史
   位置」這一題。cone 最重要的方法論貢獻——**tenor matching**——
   已被固定 (tenor, delta) 重錨定座標完整繼承（我們的 percentile
   本來就只跟同天期同 delta 的歷史比）；再畫 cone 需要標的收盤價
   序列＋逐天期 RV 計算（新資料、新引擎工作），對本輪問題零增量。
   cone 留給未來若做方案 E 時再評估，**本輪明確不做**。

## 4. Dynamics：IV 在「等幾天到幾週」的視野下怎麼動（本輪核心新材料）

### 4.1 短視野：volatility clustering——水位是持續的（persistence）

- Cont (2001, "Empirical properties of asset returns: stylized facts
  and statistical issues", *Quantitative Finance* 1, pp. 223–236)
  【搜尋索引轉述】：volatility clustering 是資產報酬的 stylized fact
  ——高/低波動事件在時間上成群，波動的自相關正值持續數日以上。
- GARCH(1,1) 對 S&P 500 的典型估計 α+β ≈ 0.97–0.99【搜尋索引轉述，
  教學/vendor 多來源交叉】——衝擊衰減 half-life ＝ ln(0.5)/ln(α+β)
  ≈ **23–34 個交易日**。
- 對 IV 本身（不是 RV）：Cont & da Fonseca (2002, "Dynamics of implied
  volatility surfaces", *Quantitative Finance* 2(1), pp. 45–60)
  【搜尋索引轉述】——surface 前三個主成分解釋約 95% 日變異；各因子
  自相關呈指數衰減、以 AR(1)／Ornstein-Uhlenbeck 建模合理；**level
  因子的均值回歸時間常數：S&P 500 約 28 天、FTSE 約 51 天**（換算
  half-life ＝ τ·ln2 ≈ 19–35 天）。⚠ 這兩個數字未能核對原文（PDF
  被沙箱擋），但與 GARCH 的 23–34 交易日、以及第五輪已引的
  Kamal–Derman／Cont–da Fonseca「三因子、level 主導」結論構成
  **三個獨立來源家族收斂到同一條 3–7 週的時間尺度帶**。

**推論（明確標注【本文推論】）**：對「等幾天」的視野，IV 水位是
**持續**的——今天貴、明天大概率還貴；一條正在下行的序列短期內傾向
繼續下行（clustering 的另一面）。這是「趨勢值得顯示」的統計基礎：
Δ4w 的符號在短視野內有延續傾向，不是白噪音。

### 4.2 中視野：均值回歸——但速度以「月」計，且不保證回到你要的位置

- 上述 half-life 證據帶（3–7 週）本身就是均值回歸證據：衝擊會消退，
  但**一個 half-life 就要一個月上下**——「等它便宜回來」的等待單位是
  月，不是天，而 §1.1 已算過一個月的 spot 不確定性是 ±39% of debit。
- Goyal & Saretto (2009, *JFE* 94, pp. 310–326)【搜尋索引轉述；第二輪
  §8 已引】：以「IV 偏離 HV」排序的組合在**一個月**的持有期內獲得
  顯著報酬——其明文動機正是「波動有均值回歸性，IV 與 HV 的大偏離
  指向錯價、並在月度尺度上修正」。這條橫斷面證據同時是「IV−RV 是
  買方的 richness 錨」的最強學術背書。
- Cooper (2013, "Easy Volatility Investing", SSRN 2255327)
  【一手全文，本輪經 GitHub 鏡像取得，33 頁逐頁可查】：spot VIX
  「相當可預測、傾向均值回歸」——用 11 日 SMA crossover 的均值回歸
  規則（收在均線下做多、否則做空）自 1990 年模擬年化 215%（VIX 不可
  交易，故不可實現，僅證明序列的統計性質）(pp. 3)。

### 4.3 Momentum 在哪裡：在 carry／premium，不在 spot vol

Cooper 同文 (pp. 13–15)【一手全文】：對四檔 VIX ETP 做 k 日 lookback
的動能輪動有效（取「典型值」k=83 個交易日而非最適化的 88），但作者
自己的歸因是 **roll yield 與 VRP 的符號持續性**（sign persistence
「經常持續一、三、六個月甚至更久」）——動能活在**期貨 carry／風險
溢酬**這一層，不是 spot vol 水位這一層；同文對 XIV 價格序列做
variance ratio／ADF／Phillips–Perron 檢定，**無法拒絕隨機漫步**
(p. 13)。對本產品的翻譯：**「IV 序列本身有可交易的趨勢」沒有證據
支撐；有證據的是（a）水位短期持續（§4.1）、（b）水位月度均值回歸
（§4.2）、（c）溢酬層的符號持續（與我們的進場問題正交）**。

### 4.4 Term-structure slope 當進場訊號：一手證據說「不要」

Simon & Campasano ("The VIX Futures Basis: Evidence and Trading
Strategies"，2012-06-27 SSRN 版，後刊 *Journal of Derivatives* 21(3),
2014)【一手全文，本輪經 GitHub 鏡像取得 41 頁 PDF】：

> "This study demonstrates that the VIX futures basis **does not have
> significant forecast power for the change in the VIX spot index**
> from 2006 through 2011 but does have forecast power for subsequent
> VIX futures returns." (Abstract)
>
> "…the VIX futures basis does not accurately reflect the mean-reverting
> properties of the VIX spot index but rather **reflects a risk premium
> that can be harvested**." (Abstract)

其文獻回顧並引 Mixon (2007)、Nossman & Wilhelmsson (2009)：基差對
未來 VIX 的預測力不顯著，除非先扣掉時變風險溢酬 (p. 4)。**判定**：
contango/backwardation 是溢酬訊號（給賣方 carry 用），**不是**「spot
vol 將要跌/漲」的可靠條件訊號——把 term slope 做成本產品的「再等等
會更便宜」指標，等於把一手文獻明文否定的因果關係賣給使用者。
**明確不做。**（本產品連 VIX 期貨資料都沒有，這條本來就貴；現在是
「貴且錯」，雙重排除。）

### 4.5 VRP：買方的結構性逆風，錨定「便宜」的意義

- Carr & Wu (2009, "Variance Risk Premiums", *Review of Financial
  Studies* 22(3), pp. 1311–1341)【搜尋索引轉述】：以 synthetic
  variance swap rate 對比 realized variance，S&P 500／100、DJIA 的
  variance risk premia **強烈為負**，多數個股亦為負（幅度較小）——
  variance 的買方平均付出負超額報酬，換的是對波動上行的避險。
- Bollerslev, Tauchen & Zhou (2009, *RFS* 22(11), pp. 4463–4492)
  【搜尋索引轉述】：VRP 對**股市報酬**在季度視野有預測力——注意
  它預測的是 equity premium，不是 IV 的漂移方向，對本輪的 entry
  timing 不直接可用，列出只為完整。
- Sinclair《Volatility Trading》對 variance premium 的定位：「長選擇權
  部位必須克服的潮水」【搜尋索引轉述】。

**對本輪的意義**：VRP 解釋了為什麼 debit 買方要在乎「相對自身歷史
便宜」——你平均在付溢酬，於是「在溢酬相對低的日子進場」是唯一能
系統性壓低這條逆風的桿子（tastytrade 系 IVR 慣例的學理版）。但 VRP
的**量測**（IV−RV）需要 realized vol，屬第一輪方案 E 的範圍，本輪
不擴——本輪的 percentile＋Δ4w 量的是「IV 相對自己歷史」，與 IV−RV
是兩個正交的錨，卡片語言不得互相冒充（第一輪 §6.5 的既有紀律）。

### 4.6 Regime-switching：證據等級不足，排除

檢索「Markov regime switching 在 desk 生產工具的使用」得到的是
vendor 指標／部落格層級材料（LuxAlgo、Medium、教學網站）——與第五輪
§4 對 ML 的檢驗同型：**找不到「銀行 vol desk 以 regime-switching
模型做選擇權進場判讀」的可查證據**【搜尋索引轉述＋檢索性結論】。
Derman "Regimes of Volatility" (1999)（GS QSRN 鏡像內有全文，前輪已
確認）講的是 sticky 規則隨市場狀態切換——是 surface **動力學的描述
框架**，不是可部署的進場訊號。加上本產品 66 點/年的抽樣密度連 AR(1)
都估不穩（§7.3），二狀態 HMM 的參數更無從談起。**排除。**

### 4.7 動態層總結：可顯示的是「位置＋方向」，不可顯示的是「預測」

| 視野 | 證據說什麼 | 對指標設計的含義 |
|---|---|---|
| 日～週 | 水位/skew 持續（clustering；高自相關） | 趨勢的**符號**短期有延續傾向 → Δ4w 值得顯示 |
| 週～月 | 均值回歸，half-life ≈ 3–7 週（三來源家族收斂） | lookback 取 ~4 週＝一個 half-life：再短是噪音，再長會把回歸抹平 |
| 月＋ | 回歸主導；IV−HV 偏離月度修正 | percentile（1Y 窗）承載這一層——已出貨 |
| 任何 | 統計可預測性 ≠ 扣成本後的 edge（Harvey–Whaley）；slope 不預測 spot vol（Simon–Campasano） | **不出 forecast、不用 term slope**；指標=事實，判斷留給使用者 |

## 5. Vertical Spread 專屬：timing 層追蹤什麼、vol timing 對 spread 值多少

### 5.1 Spread 的主角是 Ĝ，腿 IV 是脈絡（與已出貨資訊權重一致）

第二輪 §11 與本輪 §1.1 的引擎實算給出同一個數量級結論：這組 spread
對 gap 的敏感度（0.4029/pt）是對平行水位（0.2038/pt）的**兩倍**；
而 spread 的 net vega 只有裸買腿 vega 的 **40%**（0.2038 vs 0.5048）
——vertical 的兩腿互為部分 vol 對沖，level timing 對它的重要性天生
比對 Long Call 低，skew timing 反而是它特有的、無處迴避的曝險。
換算成 debit 佔比【repo 實證，§1.1 同一次計算】：

- **Long Call C90**（ask $4.10，vega 0.5048）：1 vol 點 ≈ **12.3%**
  of premium——level timing 對裸買腿是一階大事；
- **Spread 90/130**（debit $3.47）：1 vol 點 level ≈ 5.9%、1 vol 點
  gap ≈ **11.6%**——對 spread 而言 gap 才是那個 12% 級的桿子。

這正是 MVP V3 已裁示的資訊權重（Normalized Skew ＝ Primary、兩腿 IV
＝ Supporting Detail，`docs/Mvp-v3.md` §5–§7）的動態層延伸：**趨勢
統計量也照同一權重掛**——Spread 模式的頭條是 Ĝ 的 percentile＋Δ4w，
兩腿 IV 的 percentile＋Δ4w 在次層；Long Call 模式退化為買腿 IV 一條
（level 語言），沒有 gap 可言。「不同結構用不同 vol 語言」是專業慣例
不是妥協（第二輪 §10 的四點論證，含 SAS 腳注 3 的單調性紅線）。

### 5.2 Skew richness 的 timing 有 desk／vendor 先例

- **ORATS**【搜尋索引轉述，本輪新增】："Is Skew Cheap Or Expensive?"
  ——以 constant-maturity slope 的 **percentile 對照自身歷史**判讀
  skew 貴賤，並給出交易對應（skew 高估利於 risk reversal、低估利於
  collar）；其產品另有 slope forecast 與現值的對照。這是「skew 衍生
  量的歷史 percentile ＋ 據此擇時」的現成 vendor 產品，本輪主推設計
  的最直接先例。
- **FX Risk Reversal**（第二輪 §6【索引轉述】）：對 RR 序列取
  z-score、**1 個月 lookback 看流向、6 個月看結構性倉位**——「兩點
  差的序列＋短 lookback 方向判讀」的成文實務；本輪 Δ4w 的 lookback
  選擇與其 1M 慣例對齊。
- **Zou–Derman SAS_ATM**（第二輪 §7.2【一手全文】）：GS 把 level 交給
  ATM 校準、SAS_ATM 專量「skew 相對歷史的 richness」——level／skew
  分開判讀的 desk 血統。

**Spread 的 timing 層因此拍板**：追蹤 **Ĝ 的 percentile＋Δ4w**（主）
＋兩腿 IV 各自的 percentile＋Δ4w（輔）。不造 spread 單一 IV（ill-
defined，第一輪 §5.3）、不做 vega 加權合成（分母穿零，第一輪 §4.b）、
不做固定合約 raw gap 的 percentile（√t roll-down，第二輪 §4.2）——
三個否決全部沿用前輪，本輪零翻案。

## 6. 呈現方式：成熟工具怎麼顯示「位置＋方向」，本產品採哪一種

### 6.1 版圖（【搜尋索引轉述】，本輪新增材料）

| 呈現形態 | 實例 | 對本產品的評估 |
|---|---|---|
| **數值欄位並列：現值＋歷史位置＋短期變化** | Market Chameleon Volatility Rankings（IV30、IV30 52-Week Position、**1-Day IV Change**）；Barchart Premier 歷史欄位（IV、**IV Change**、Rank、Percentile）；PowerOptions screener（IV Rank／Percentile／Z-Score 並列） | ✅ 與已出貨 card 同構——現值＋percentile＋筆數已在，補一個變化欄即成 |
| 方向著色（漲綠跌紅） | Market Chameleon 對 1-Day IV Change 的紅綠 | ✖ 對 debit 買方「IV 跌」才是省錢方向——紅綠的褒貶語意會反向誤導，且逼近評價字眼紅線；用帶正負號的數字即可 |
| Cone 疊圖 | Burghardt–Lane 傳統、各教學平台 | ✖ §3.2 已判：另一題（IV vs RV）、新資料 |
| Z-score band（±1σ／±2σ 區帶） | VRP／RR 圈 | ✖ §3.2 已判不採 z-score |
| 象限／狀態標籤（rich & rising 之類） | 部落格級 dashboard 常見 | ✖ 「rich」「cheap」是評價字眼，`docs/Mvp-v3.md` §9 明文禁止、有測試守門 |
| Sparkline（形狀提示） | 本產品已出貨（`IvHistory.tsx`，18px、缺值斷線） | ✅ 保留原樣——趨勢的「形狀脈絡」它已經給了，Δ4w 是把肉眼斜率變成可讀數字 |

### 6.2 拍板：延伸既有複合標籤一格，其餘不動

已出貨的 `metricCaption` 是「第 62 百分位・45 筆觀測」。本輪唯一的
UI 增量＝在同一行追加一格：

```
Normalized Skew   0.50        第 78 百分位・45 筆觀測・4週 +0.06
買腿 IV           12.0%       第 24 百分位・45 筆觀測・4週 −1.2 pts
賣腿 IV           18.0%       第 61 百分位・45 筆觀測・4週 −0.4 pts
```

規則：帶正負號的原始變化量、量自身單位（腿 IV 以 vol 點、Ĝ 無因次
小數）；基準觀測缺席（§7.4 的容忍窗內無點）時該格顯示「4週 —」；
不加顏色、不加箭頭圖示、不加任何評價詞；sparkline、觀測筆數、
percentile、「近 1 年 N 個觀測，依候選的到期天數與 delta 座標逐日
重錨定」的尾註全部原樣。方法論尾註（分析報告的 Model & Assumptions
／既有 methodology note 慣例位置）新增兩句事實：(a) 4 週變化的定義
與基準容忍窗；(b) 「等待進場另有已知的 theta 成本與標的價格風險，
本區塊僅描述 volatility 結構」——§1 的誠實條款落地處。

## 7. 最終建議（單一方案，逐點回答委託 Step 3）

**方案名：既有 Historical IV Position 序列上的「Percentile＋Δ4w」
趨勢層。** 以下每一點都是決定，不是選項。

### 7.1 指標追蹤什麼

- **Long Call**：買腿 (tenor, delta) 座標的重錨定 IV——level 語言。
  頭條一條：`IV 現值・percentile・count・Δ4w`。
- **Vertical Spread**：頭條＝ **Normalized Skew Ĝ**（percentile・
  count・Δ4w）；次層＝買腿 IV、賣腿 IV 各自同款四件組。`atm_iv`
  照舊只作分母與內部脈絡，不上頭條。
- 不新增任何量。不造 spread 單一 IV、不做 vega 加權、不做固定合約
  raw gap percentile（§5.1 末段）。

### 7.2 Normalization：確認既有做法，零調整

固定 (tenor, delta) 逐日重錨定（消 DTE／moneyness／上市時長三漂移）
＋ Ĝ 除以當日 ATM（消 level 依賴）——第一、二輪的判定經本輪 §3–§5
的新證據（ORATS slope percentile、cone 的 tenor-matching 紀律、
Simon–Campasano）檢驗後**只被加固、沒有被動搖**。嚴格不外插（超出
當日網格回 `None`）維持：LEAPS 超網格的日子在 percentile 與 Δ4w 都
如實留白，不拿最長天期頂替。

### 7.3 歷史視窗：維持 1 年；66 點/年下什麼估得出、什麼估不出（誠實帳）

- **維持 1Y**。理由：(a) 業界慣例錨（52 週 IVR/IVP 家族、ORATS
  `ivRank1y/ivPct1y`、Market Chameleon 52-Week Position——第一輪
  §3.4＋本輪 §6.1）；(b) 1 年 ≈ level 因子 8–12 個 half-life（§4.1
  證據帶），percentile 的參照分布涵蓋多輪回歸循環，統計上「位置」
  有意義；(c) 2Y 能加抗 regime 韌性（一個 Fed 週期），但 vendor
  呼叫量與冷啟動期翻倍，且 SAS 的一手警語（歷史窗選擇能翻轉結論，
  Zou–Derman p. 21，第二輪 §7.2）提醒的是**揭露**視窗而非加長視窗
  ——視窗長度已在卡片尾註與方法論註記揭露，維持現狀。
- **估得出**（66 點/年、近 90 天每週 2 點的密度下）：
  - 時間加權 percentile（已出貨，Voronoi 權重正是為此密度設計）；
  - **Δ4w**：基準點落在密集段（≤90 天），4 週前 ±1 週內幾乎必有
    觀測（每週 2 點）——這是 Δ4w 對本 cache 可行的關鍵，也是不選
    Δ1w（單點噪音、對齊誤差佔比大）與 Δ3m（落進稀疏段、且跨多個
    half-life 後趨勢被回歸抹平）的資料面理由。
- **估不出（明確不做）**：**per-symbol half-life／AR(1)／OU 參數**。
  誠實的算術：一年僅 ~66 點、不等距，密集段連續點間距 2–5 天、稀疏
  段 7–14 天；AR(1) 係數在 n≈66 且不等距下要用連續時間 MLE，係數
  標準誤大到「half-life 20 天 vs 60 天」無法區分——而這兩者對使用者
  的含義天差地遠。**文獻 half-life（§4.1 的 3–7 週帶）只用來校準
  lookback 的設計，不做成 per-symbol 數字顯示。**需要 per-symbol
  估計的那天，前提是日頻序列（~252 點/年，vendor 呼叫量 ~4 倍），
  屬另案。

### 7.4 趨勢統計量：Δ4w 的精確定義（本輪的核心交付）

對 `field_metrics` 既有四欄位各自計算（與 percentile 同一批
observation points，零新增 vendor 呼叫）：

```
Δ4w(field) = latest_value − base_value

latest_value：該欄位最後一筆非 None 觀測（與既有 value 同一筆）
base_value ：落在 [today−42天, today−21天] 視窗內、距 (today−28天)
             最近的那筆非 None 觀測之值
視窗內無非 None 觀測 → Δ4w = None（呈現為「4週 —」，不外推、不用
最近點頂替——沿用 iv_at() 的不外插哲學）
```

序列化：`field_metrics` 每欄位在 `{value, percentile, count}` 之外
純加法新增 `{trend_4w, trend_base_date}`（後者供除錯與方法論透明，
UI 不一定顯示）。契約為 additive、前端零金融計算原則不變。

**為什麼是「原始變化量」而不是其他候選**（逐一否決）：

1. **EMA／迴歸斜率**：不等距抽樣下要自建加權迴歸，統計自由度
   （span／權重）多一層任意性；對使用者的資訊增量≈0——sparkline
   已給形狀，Δ4w 已給方向與幅度；且「IV change」數值欄是 vendor
   現成先例形狀（§6.1），迴歸斜率不是。
2. **Δ4w 的 percentile（變化量的歷史位置）**：把「動得算不算快」
   也交給歷史分布——概念自洽，但每欄位要再維護一條變化量序列，
   卡片再加一個要解釋的數字；MVP V3 的裁示是「快速讀值，不是把
   研究報告塞進 UI」（`docs/Mvp-v3.md` §7）。不做。
3. **Mean-reversion-aware expected drift**（以 OU 參數算 E[Δσ]）：
   §7.3 已證 per-symbol 參數估不出；借文獻參數＝把大盤指數的動態
   包裝成這個 symbol 這個座標的預測；且任何 forecast 都跨過
   facts-only 紅線（`docs/Mvp-v3.md` §9 測試守門的禁語清單雖列的是
   評價詞，forecast 是更強的評價）；Harvey–Whaley（§1.3）從市場
   效率面補刀。ORATS 有 slope forecast 產品，證明 vendor 可以賣
   forecast——但那是人家的模型產品線，本產品的定位裁示是「提供
   事實，交易判斷由使用者自己完成」。**不做。**
4. **k 的選擇**：4 週（28 曆日）＝ §4 證據帶的一個 half-life ≈
   FX RR 的 1M lookback 慣例 ≈ 密集抽樣段的中點。1 週太吵（兩點
   之間就是全部資訊）、13 週（一季）已跨 2–4 個 half-life、趨勢
   訊號會系統性衰減，且基準落進每週 1 點的稀疏段。

### 7.5 「現在貴/便宜＋正在變貴/變便宜」的 facts-only 呈現

§6.2 的格式為準：`第 P 百分位・N 筆觀測・4週 ±X`。禁：便宜/貴/
好買點/建議/有利/不利（既有測試守門清單）、紅綠褒貶著色、rich/
cheap/rising/falling 象限標籤、任何預測句。允許且建議的完整範例
（Spread 模式）：

```
IV 相對位置
  Normalized Skew   0.50    第 78 百分位・45 筆觀測・4週 +0.06   ▁▂▄▆▇
  買腿 IV          12.0%    第 24 百分位・45 筆觀測・4週 −1.2 pts ▇▆▄▂▁
  賣腿 IV          18.0%    第 61 百分位・45 筆觀測・4週 −0.4 pts ▄▄▅▄▄
  近 1 年 45 個觀測，依候選的到期天數與 delta 座標逐日重錨定；
  4週變化＝與約四週前（21–42 天窗內最近一筆）觀測之差
```

使用者從這三行自己讀出委託開頭的兩個問題的答案：「第 24 百分位＋
四週 −1.2 pts」＝歷史低位且仍在下行（等的論點與風險自己權衡）；
「第 78 百分位＋四週 +0.06」＝skew 在歷史高位且四週來走高。產品
把兩個事實擺齊，判斷句一個都不說。

### 7.6 Long Call vs Vertical Spread：同一卡片家族、不同主角

同 §5：Long Call＝level 語言，一條（買腿 IV 四件組）；Spread＝skew
語言，Ĝ 主＋兩腿輔。vega 量級的事實（spread net vega ＝ 裸腿 40%、
gap 敏感度 ＝ level 的 2 倍）寫進方法論註記，讓進階使用者知道為什麼
兩種模式的頭條不同。不硬統一公式（SAS 腳注 3 的一手背書，第二輪
§7.1）。

### 7.7 資料需求與可行性（含 vendor 封鎖現狀）

- **趨勢層本身：零新增。**Δ4w 用既有 observation cache 的同一批點；
  不多打一次 vendor、不加表、不改抽樣排程。實作面是
  `option_chaser/ivhistory.py::field_metrics()` 的純函式延伸＋
  `api_app/main.py` 序列化一欄＋`IvHistory.tsx` 標籤一格。
- **繼承的既有 blocker 如實列出**：整條 Historical IV 線仍被 #111
  擋住（IV history vendor credential-blocked，免 key 路線已於
  2026-08-11 窮盡確認不可行）——趨勢層不加重也不解除這個 blocker，
  它跟 percentile 同生共死。LEAPS 超出當日網格的日子（`iv_at` 回
  `None`）在 Δ4w 同樣留白，繼承既有誠實語意。
- **若未來要更多**（明確標價，非本輪範圍）：per-symbol half-life
  → 日頻序列（vendor 呼叫 ~4 倍）；cone／IV-HV（方案 E）→ 標的
  日收盤序列（第四輪更正已確認 Yahoo chart 端點回應內含
  `indicators.quote[].close`、屬 parsing 增修非新資料依賴）＋逐
  天期 RV 計算；這兩條都等需求方看過趨勢層的實際決策價值再議。

### 7.8 紅線合規

Enrich-only：趨勢欄位只進 iv-history 端點與 `IvHistory.tsx`，
`ranking.py`／`filters.py` 不 import `ivhistory` 的結構保證與 #118
選取身份回歸守門原樣有效——Δ4w 在結構上不可能影響排名、過濾或候選
選取。

## 8. 證據強度逐項表

| # | 本文依賴的主張 | 等級 | 來源 |
|---|---|---|---|
| 1 | debit 分解的權重（net vega／平均 vega）與 TLT 實例量級 | 【repo 實證】可重現 | 第一輪 §5、第二輪 §11、本輪 §1.1 引擎實算 |
| 2 | 等待的 spot 不確定性 >> vol 分量（週 ±19%、月 ±39% of debit） | 【repo 實證】＋【本文推論】（1σ 換算） | 本輪 §1.1 |
| 3 | IV 變化統計可預測但扣成本無 edge | 【搜尋索引轉述】 | Harvey & Whaley 1992, JFE 30:33–73 |
| 4 | 固定 (tenor,delta) 重錨定＋Ĝ=÷ATM 是正確可比序列 | 既有研究已證（含一手：Natenberg、Zou–Derman、Gatheral） | 第一輪 §3.3、第二輪 §5／§9 |
| 5 | percentile 是本量的正確縱軸統計（vs Rank/z-score） | 既有研究已證＋本輪先例補強（ORATS slope percentile） | 第一輪 §2.1、第五輪 §5、本輪 §3 |
| 6 | cone＝tenor-matched「IV vs RV 分布」，另一題 | 【搜尋索引轉述】（Burghardt–Lane 1990、Hodges–Tompkins 2002 皆未讀原文） | 本輪 §3.1–3.2 |
| 7 | volatility clustering／短期持續 | 【搜尋索引轉述】（Cont 2001；GARCH α+β 教學級多來源） | 本輪 §4.1 |
| 8 | IV level 因子 half-life ≈ 3–7 週（S&P τ≈28d、FTSE≈51d；GARCH 23–34 交易日） | 【搜尋索引轉述】⚠ 數字未核對原文，但三個獨立來源家族收斂 | Cont & da Fonseca 2002；GARCH 教學文獻；第五輪 §3.1（Kamal–Derman 佐證低維結構） |
| 9 | spot VIX 均值回歸；momentum 活在 ETP carry 層非 spot 層；XIV 隨機漫步檢定 | **【一手全文】** | Cooper 2013（SSRN 2255327，GitHub 鏡像 33 頁逐頁） |
| 10 | term-structure basis 不預測 spot vol 變化、只反映可收割溢酬 | **【一手全文】** | Simon & Campasano 2012（SSRN 2094510，GitHub 鏡像 41 頁；刊 JOD 2014） |
| 11 | VRP 平均為負＝買方結構性逆風 | 【搜尋索引轉述】 | Carr & Wu 2009, RFS 22(3)；Sinclair（轉引）；BTZ 2009（equity-premium 預測，註明不直接可用） |
| 12 | IV−HV 偏離月度修正、預測選擇權報酬 | 【搜尋索引轉述】 | Goyal & Saretto 2009, JFE 94:310–326（第二輪已引，本輪補其均值回歸動機） |
| 13 | skew richness 的歷史 percentile 擇時有 vendor 現成產品 | 【搜尋索引轉述】 | ORATS "Is Skew Cheap Or Expensive?"／Predictive indicators |
| 14 | 「現值＋歷史位置＋短期變化」數值欄是零售端現成呈現形狀 | 【搜尋索引轉述】 | Market Chameleon Volatility Rankings；Barchart IV Change 欄位；PowerOptions |
| 15 | regime-switching 無 desk 級部署證據 | 【搜尋索引轉述】＋檢索性結論（absence of evidence） | 本輪 §4.6 |
| 16 | 66 點/年下 per-symbol AR(1)/half-life 估不出 | 【本文推論】（樣本量算術，保守方向） | 本輪 §7.3 |
| 17 | 既有 ivhistory 基礎設施的行為（抽樣、加權、留白、契約） | 【repo 實證】逐行 | `option_chaser/ivhistory.py`、`api_app/main.py:183–208/798+`、`src/IvHistory.tsx` |
| 18 | VIX 的 30 天 model-free 建構與定位 | **【一手全文】** | Carr & Wu 2005 "A Tale of Two Indices"（GitHub 鏡像 38 頁；本文僅背景引用） |
| 19 | 銀行週報 vol screen 內部方法論 | **未能查證**（proprietary） | §9 第 6 項 |

## 9. 取材限制（誠實聲明）

1. **沙箱網路與前五輪同型**：絕大多數金融／學術網域 403。本輪新測
   `www.m-x.ca`（Montreal Exchange cone 教材 PDF）被擋；委託已標明
   的封鎖清單（trading-volatility.com、arxiv.org、web.archive.org、
   onlinelibrary.wiley.com 等）未重試。`api.github.com` 與 GitHub
   MCP 的 search/code、search/repositories 本 session 被限制在本
   repo，**但 `raw.githubusercontent.com` 單檔下載與 `git clone`
   （含 `--filter=blob:none` 列目錄）依然可用**——本輪的三份一手
   全文即由此取得。
2. **本輪【一手全文】三份**（皆第三方 GitHub 鏡像 `emintham/Papers`，
   無法對發行方原站做 byte 級核對，版式／SSRN 浮水印自洽）：
   Simon & Campasano 2012（41 頁）、Cooper 2013（33 頁）、
   Carr & Wu 2005（38 頁）。引文為逐字轉錄。
3. **Cont & da Fonseca 2002 的關鍵數字（τ≈28/51 天）未能核對原文**
   ——PDF 掛在 `rama.cont.perso.math.cnrs.fr`（第五輪已測被擋）。
   本文以「三來源家族收斂」的方式使用該數字帶，並把設計（4 週
   lookback）做成對這個帶的中點取值，而非依賴單一精確值。
4. **GARCH half-life 23–34 交易日**為教學／vendor 級多來源交叉，
   非某一篇可引用的 primary 估計；α+β≈0.97–0.99 是文獻常識級數字，
   同樣未逐字核對任何單一原文。
5. **Burghardt & Lane 1990 與 Hodges & Tompkins 2002 均未讀到原文**
   （JPM／JOD 付費牆＋鏡像被擋）；cone 的構造與用法為多來源一致的
   轉述，本文對 cone 的裁決（不採用）不依賴其任何精確細節。
6. **銀行（GS/JPM/MS/BofA）週報級 vol screen 的內部方法論查無公開
   文件**——本文以 vendor 同款產品（Bloomberg VCA、ORATS、Market
   Chameleon）為替代證據，並如實標注這個缺口。
7. **Bennett《Trading Volatility》與 Sinclair 兩本書本輪仍無一手**
   （官方站與已知鏡像全被擋、GitHub 無全文鏡像——第 2026-08-13 輪
   已窮舉確認）；引用皆為書商／第三方轉述級，逐處標明。
8. **Harvey & Whaley 1992／Carr & Wu 2009／Goyal & Saretto 2009／
   BTZ 2009** 皆為索引轉述；其中 H-W 的「模擬無異常報酬」是本文
   §1.3 的支柱之一，若需求方要把這句寫進產品文案，建議先在可連網
   環境覆核原文。
9. **檢索性結論**（absence of evidence，不能排除漏檢）：「IV 序列
   本身存在可交易 momentum」查無支持；「regime-switching 有 desk
   級部署」查無支持；「有平台把 per-candidate 趨勢統計做成
   forecast 以外的第三種形態」查無。
10. 本輪引擎實算使用 q=0 顯示口徑的 Greeks（與 #122 分級路徑一致）；
    theta 絕對值在含 q 校準下會略有不同，不影響本文的數量級論證。

## 10. 與第五輪架構文件的關係（承接什麼、新增什麼、有無衝突）

第五輪（`modern-surface-methods-rich-cheap-architecture.md`）收攏的
四層 Rich/Cheap Engine 架構：Layer 0 資料層／Layer 1 橫斷面 fit
（per-expiry 二次式或 `theo` 殘差）／Layer 2 兩腿封裝（$ 空間相加）
／Layer 3 **殘差的時間層（選配、非 MVP、明文不拍板）**。

- **承接**：本輪完全不動 Layer 0–2；第五輪 §6.4 第 4 點的「三條
  時間軸正交、標籤紀律」警告原樣繼承——本輪的 percentile＋Δ4w 活在
  「ATM/腿 IV 水位歷史」與「skew gap Ĝ 歷史」這兩條**已出貨**的
  時間軸上，與 Layer 3 那條「橫斷面殘差的歷史」是不同的軸。
- **新增（本輪拍板了第五輪刻意留白的哪一部分）**：第五輪對「時間層
  該不該做、統計量選什麼」只到「若做，percentile 優於 z-score／Rank
  【推論】」就停（因為它談的殘差序列無業界先例、尚無一天歷史）。
  本輪把時間層的問題**移到有業界先例、有已出貨序列的量上**（level
  與 skew——ORATS ivPct／slope percentile 先例，第五輪 §5.1 自己
  找到的正面案例正是 slope percentile），並補上第五輪未觸及的
  **dynamics 證據（half-life、clustering、term-slope 否定、VRP）**
  與**趨勢統計量的最終規格（Δ4w）**。第五輪「percentile 優於
  z-score」的推論在本輪被沿用並得到額外先例支撐。
- **無衝突**：第五輪 Layer 3（殘差歷史）維持「選配、後期、需求方
  看過 Layer 1–2 上線效果後再議」的原判——本輪不提前它，也不因
  本輪的趨勢層而改變它的定位。若未來 Layer 3 真的實作，其呈現應
  沿用本輪的四件組形狀（value・percentile・count・Δ4w）以保持
  卡片語言一致，但那是到時候的事。
- **對第五輪結論摘要的一處補強**：第五輪 §5.3 report 的最大查證
  缺口（「殘差本身的時間序列化無 vendor 先例」）不影響本輪——本輪
  的量（腿 IV、Ĝ）的時間序列化先例充分（IVR/IVP 家族、slope
  percentile、FX RR），這正是把 timing 層掛在 level/skew 軸而非
  殘差軸上的理由之一。

## 11. 來源清單

**一手全文（本輪新增，GitHub 鏡像 `github.com/emintham/Papers`）**

- 【一手全文】Simon, D.P. & Campasano, J., "The VIX Futures Basis:
  Evidence and Trading Strategies"（2012-06-27 SSRN 版，SSRN 2094510；
  刊 *Journal of Derivatives* 21(3), 2014）——鏡像路徑
  `Simon,Campasano- The VIX Futures Basis: Evidence and Trading
  Strategies.pdf`（41 頁）
- 【一手全文】Cooper, T., "Easy Volatility Investing"（2013，SSRN
  2255327）——鏡像路徑 `Cooper- Easy Volatility Investing.pdf`
  （33 頁）
- 【一手全文】Carr, P. & Wu, L., "A Tale of Two Indices"（2005-12-22
  版；刊 *Journal of Derivatives* 13(3), 2006）——鏡像路徑
  `Carr,Wu- A Tale of Two Indices.pdf`（38 頁）

**搜尋索引轉述（本輪新增引用）**

- Burghardt, G. & Lane, M., "How to tell if options are cheap",
  *Journal of Portfolio Management* 16(2), Winter 1990, p. 72
  （jpm.iijournals.com/content/16/2/72；Semantic Scholar 索引）
- Hodges, S. & Tompkins, R., "Volatility Cones and Their Sampling
  Properties", *Journal of Derivatives* 10(1), 2002
  （jod.pm-research.com/content/10/1/27）
- Cont, R. & da Fonseca, J., "Dynamics of implied volatility
  surfaces", *Quantitative Finance* 2(1), 2002, pp. 45–60
  （SSRN 295859；原 PDF 域被擋）
- Cont, R., "Empirical properties of asset returns: stylized facts
  and statistical issues", *Quantitative Finance* 1, 2001,
  pp. 223–236
- Harvey, C. & Whaley, R., "Market volatility prediction and the
  efficiency of the S&P 100 index option market", *Journal of
  Financial Economics* 30, 1992, pp. 33–73
- Carr, P. & Wu, L., "Variance Risk Premiums", *Review of Financial
  Studies* 22(3), 2009, pp. 1311–1341
- Bollerslev, T., Tauchen, G. & Zhou, H., "Expected Stock Returns
  and Variance Risk Premia", *RFS* 22(11), 2009, pp. 4463–4492
- Goyal, A. & Saretto, A., "Cross-section of option returns and
  volatility", *JFE* 94, 2009, pp. 310–326（第二輪已引）
- GARCH(1,1) S&P 500 持續性與 half-life（教學級多來源交叉：
  quantt.co.uk、riskhub.org、jonathankinlay.com 等）
- ORATS, "Is Skew Cheap Or Expensive?"（orats.com/blog；Nasdaq 轉載
  2021-07-08）、"Predictive indicators"（orats.com/university）
- Market Chameleon, "Option Implied Volatility Rankings Report"
  （marketchameleon.com/volReports/VolatilityRankings；IV30 52-Week
  Position、1-Day IV Change 定義）
- Barchart options screener／IV Rank-Percentile 頁（IV Change 欄位）；
  PowerOptions IV Rank Screener（IV Z-Score 欄位）
- Sinclair, E., *Volatility Trading*（Wiley，2nd ed. 2013）——
  variance premium「the tide that long option positions need to
  overcome」經 SpotGamma 支援文件轉引；Bennett, C., *Trading
  Volatility*（2014）——書商／第三方轉述級
- Markov regime-switching 工具（LuxAlgo／Medium／教學站，vendor
  指標級——用於證明「desk 級證據缺席」）

**本 repo（既有研究與程式碼）**

- `docs/research/iv-relative-history-methodology.md`（第一輪：§2.1
  Rank vs Percentile、§3.3 座標、§4/§5 spread 定義與數學、§6 方案）
- `docs/research/candidate-iv-relative-value.md`（第二輪：§5 正規化
  工具箱、§6 FX RR、§7 SAS 一手、§9 重錨定、§11 TLT 實算、§12 方案二）
- `docs/research/spread-price-percentile-vs-vol-space.md`（第三輪：
  price 空間 dominated 負結論）
- `docs/research/option-richness-assessment-methods.md`（第四輪：
  M1–M10 外部方法內容；其 repo 實證段已自我標注不可信，本文未引用
  該部分；其 2026-08-13 更正記錄的 Yahoo chart `indicators.quote[]
  .close` 事實在 §7.7 引用）
- `docs/research/modern-surface-methods-rich-cheap-architecture.md`
  （第五輪：四層架構、§5 詞彙版圖、§6.4 Layer 3——本文 §10 逐點
  對位）
- `docs/research/directional-option-fair-value-workflow.md`（封鎖
  網域清單與 GS QSRN 鏡像現狀）
- `docs/Mvp-v3.md` §4–§9（Historical IV Position 目的、Normalized
  Skew 主資訊、facts-only 禁語清單）＋`docs/Mvp-v3-appendix.txt`
- `option_chaser/ivhistory.py`（本輪逐行重讀：抽樣、加權、不外插、
  `field_metrics` 契約）；`api_app/main.py`（iv-history 端點與序列
  化接縫）；`src/IvHistory.tsx`（呈現層現狀與測試守門）
- `option_chaser/valuation.py::call_greeks`（§1.1 分解實算引擎）
