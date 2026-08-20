# 已有方向性目標價與目標日，怎麼判斷 Call／Vertical Spread 現價貴不貴：
# 從物理分布到風險中性公平值的橋接

研究日期：2026-08-13。

---

## 取材限制聲明

**本沙箱的出口 proxy 對幾乎所有金融／學術網域一律回 403**（`curl` 與
`WebFetch` 皆同一結果，錯誤訊息固定為 `CONNECT tunnel failed, response 403`
或 `EGRESS_BLOCKED`）。本輪**逐一實測**、新確認被擋的網域包含：
`trading-volatility.com`（Colin Bennett 官方書籍下載頁本身）、
`moontowermeta.com`、`pdfcoffee.com`、`scribd.com`、`sciarium.com`、
`archive.org`／`web.archive.org`、`onlinelibrary.wiley.com`、`arxiv.org`、
`academic.oup.com`、`math.ntu.edu.tw`（Duan 本人掛在台大網站的講義 PDF）、
`cfrn.com.cn`、`morganstanley.com`。這與前次調查
（`docs/research/option-richness-assessment-methods.md`）記錄的
`cdn.cboe.com`／`ssrn.com`／`nber.org`／`wikipedia.org`／`aqr.com` 等一併
確認：**沒有一個學術或投行網域是通的**。

**唯一可行的第一手管道，同前次調查，仍是 `git clone` 對 `github.com`**
（`api.github.com` 回 200，`git clone` 成功；`curl` 打 `github.com` 首頁
本身回 400 但不影響 clone）。本輪額外做了兩件事：

1. **複用前次調查已找到的鏡像** `github.com/s0ap/gs-quantitative-strategies-research-notes`，
   但這次讀的是**不同的論文**——前次調查逐頁讀了 *Strike-Adjusted Spread*
   （SAS）論文用於「單腿／spread 相對於同一張曲面貴不貴」（M4／M8），
   **本次為了本文的核心問題（物理分布如何橋接到風險中性公平值），
   把同一篇論文的 Appendix A／B／C（entropy 與 utility 推導）逐式讀完**，
   這部分前次調查完全沒有引用。另外新讀了同一鏡像中的
   *Investing in Volatility*、*Regimes of Volatility*、
   *Outperformance Options* 三篇，確認其內容與本文問題不直接相關
   （分別是純波動率曝險商品設計、sticky-strike/delta 機制、雙標的
   選擇權），故本文不引用它們。
2. **確認 GitHub code search（`search_code`）與 `search_repositories`
   在本次調查找不到 Colin Bennett《Trading Volatility》、Euan
   Sinclair《Volatility Trading》／《Positional Option Trading》、
   Sheldon Natenberg《Option Volatility and Pricing》的完整文字鏡像**
   （多次以書名、作者名、`extension:pdf`、`filename:` 組合查詢，
   命中的只有讀書筆記／程式碼複現 repo，不含原文）。這三本書委託明列
   為「應視為第一手實務來源」，但**本次沒有找到可讀到原文的合法管道**，
   只能退回搜尋引擎摘要與書商簡介，證據等級降為【搜尋索引轉述】，
   部分甚至只到「出版社／書評轉述的簡介」等級，比一般搜尋摘要更弱，
   逐處會特別註明。

因此本文證據分三級，沿用 repo 既有慣例，全文逐處標示：

- **【原文實證】**——本人逐頁讀過全文的文件。本次唯一達到此級的來源是
  Goldman Sachs *Strike-Adjusted Spread*（1999）的 Appendix A／B／C，
  以及同一篇論文正文中與 Table 1 相關的敘述（後者前次調查已引用過，
  本文僅在需要銜接論證時重提頁碼，不重複整段抄錄）。
- **【搜尋索引轉述】**——只讀到搜尋引擎回傳的摘要或書商／部落格轉述，
  **沒有讀到原文**。本文絕大多數關於 GARCH option pricing（Duan 1995）、
  Stutzer (1996) canonical valuation、Rosenberg & Engle (2002) empirical
  pricing kernel、Christoffersen & Jacobs (2004)、HAR-RV（Corsi，沿用前次
  調查的證據等級）、以及 Sinclair／Bennett／Natenberg 三本書的內容，都屬
  此級。**引用的每一個數字或具體結論，若無【原文實證】標記，就是我沒
  親眼在原文看過的。**
- **【repo 實證】**——本 repo 自身程式碼，本次為驗證 CLAUDE.md 記載的
  「repo 現況」是否可信而直接讀過的檔案（見 §6 開頭的核對記錄）。

**開工前的 checkout 完整性核對**（依委託指示執行，記錄於此避免重蹈
前次調查的覆轍）：`git log --oneline -3` 顯示 HEAD 為 `46d3bf8`
（「docs(research): 機構如何判斷選擇權貴賤」），**與委託描述的
「應看到 46d3bf8 或更新」相符**；`docs/research/` 目錄下確認存在
`option-richness-assessment-methods.md` 以及其餘 17 份既有研究文件；
`option_chaser/` 目錄下確認存在 `valuation.py`（`bs_call`／`leg_greeks`
均帶股息殖利率參數 `q`）、`ivhistory.py`（19.8K，(tenor, delta) 座標
重錨定模組，見 §6）、`ratecurve.py`、`data/cboe.py`、`data/dividends.py`、
`data/marketdata.py`。**checkout 是新鮮的，非前次調查回退到 V1 的
那種陷阱狀態**，本文的 §6【repo 實證】可信。

凡搜尋亦無法確認者，一律列入「未能查證的事項」，不猜數字、不編頁碼。

---

## 結論摘要

**核心問題的直接答案**：機構作法**不是**把你的目標價／目標日直接當成
物理分布去算期望報酬——那樣算出來的是「你自己主觀相信的期望損益」，
不是「公平值」，因為它會隨你（或任何人）自己的風險胃納不同而得到不同
數字，而**市場成交價不會管你的風險胃納是多少**。正確流程有清楚的三步，
本文逐一鋪陳，這裡先給結論：

1. **先把你的看法變成一個完整的機率分布** `P`（不是一個點）——即使你
   只有目標價＋目標日，業界的標準做法也是**假設一個形狀**（幾乎總是
   對數常態／常態，跟 Black-Scholes 一樣）、把目標價當**這個分布的
   均值或中位數**，再用某個波動率估計（你自己的、或市場的 ATM
   implied vol）撐開這個分布的寬度——**不會有分布「從無到有」憑空生
   出來，點看法一定要先參數化成分布**（§1、§6）。
2. **把 `P` 轉成風險中性分布 `Q`，而不是直接對 `P` 取期望值積分**。
   這是本文查到最重要、也最容易被誤解的一步：正確的轉換**不是主觀挑一個
   風險溢酬去打折**，而是找出「滿足無套利遠期條件（`E_Q[S_T] =
   S_0·e^(r_f T)`）、同時跟 `P` 距離最小」的那個 `Q`——用 minimum relative
   entropy（Kullback-Leibler 距離）求解，數學上等於對 `P` 做一次
   **指數傾斜**（exponential tilting／Esscher transform）：
   `Q(S_T) = P(S_T)·exp(c₀ − c₁·S_T)`。Goldman Sachs 1999 年的內部
   研究報告用兩條完全獨立的路徑（純資訊理論的 entropy 最小化、
   以及代表投資人指數效用函數的均衡推導）**推出同一個 `Q`，且證明這個
   `Q` 與投資人的風險趨避程度無關**【原文實證，Zou & Derman 1999,
   Appendix B–C, p.21–29】——這代表「公平值」在離開風險中性框架後，
   仍然可以有一個**不需要你猜市場整體風險胃納**的明確定義。當 `P`
   接近常態時，這個轉換會退化成最簡單的直覺：**保留你自己對波動率
   （分布形狀）的判斷，只把均值／drift 換成無風險遠期**——這與
   GARCH 選擇權定價文獻裡 Duan (1995) 的 Local Risk-Neutral Valuation
   Relationship（LRNVR：條件變異數在 P 測度與 Q 測度下相同，只有條件
   均值被換成無風險率）是同一個原理的動態模型版本【搜尋索引轉述】——
   兩條互相獨立的文獻線（1990s GS 實務筆記、1995 年學術 GARCH 定價）
   收斂到同一個處方，這是本文找到最強的跨來源一致證據。
3. **拿模型公平值跟市場價比，優先用「vol 點」當單位，而不是美元**，
   因為 vol 點在不同履約價間穩定、可透過 vega 直接換回美元 P&L，
   而美元誤差不同 spread 之間不可比。**比較前要先扣掉真實成交成本**
   （買方 Ask、賣方 Bid，不是 mid），因為多篇文獻與業界共識都指出
   選擇權策略的理論優勢有很大一部分被 bid-ask 吃掉（§3）。

**次要但同樣重要的發現**：這整套「entropy 最小化把物理分布橋接到
風險中性分布」的方法，**不是教科書空想**——Goldman Sachs 把它做成了
真的內部指標（SAS／SAS_ATM），且明確引用了它的學術源頭
Stutzer (1996, *Journal of Finance*, canonical valuation)【原文實證
（GS 論文腳註引用；Stutzer 原文本身未取得，屬搜尋索引轉述）】。
相對地，**參數化更精緻的 GARCH 選擇權定價模型（Duan 1995 及其後續）,
雖然理論優雅、文獻量極大，卻有直接的實證反例**：Christoffersen &
Jacobs (2004) 發現在 LRNVR 的字面限制下，GARCH 選擇權模型的定價與
避險表現不佳，後續研究要放寬「兩個測度下變異數必須相同」這個限制
（modified LRNVR）才勉強修正【皆搜尋索引轉述】——這是本文對「哪些是
業界真的在用、哪些是學術上優雅但撐不過真實摩擦」這條分界線最明確的
一組正反案例（§5）。

---

## 1. 物理（predictive／forecast）分布怎麼建

這裡直接回答：**GARCH／EGARCH 一族、HAR-RV、歷史／拔靴（bootstrap）
分布、情境疊加、集成——這些名詞在業界文獻與實務筆記裡都找得到蹤跡，
但份量並不平均。**

- **歷史／經驗分布（historical / empirical distribution）是本文查到
  唯一有「真的被拿去定價」第一手證據的方法。** GS 的 SAS 論文直接
  把「標的的歷史報酬分布」當成 `P`，不對它做任何參數化假設（不假設
  常態、不假設某個 GARCH 過程），**理由是論文自己講的**：要嚴謹地從
  過去股價路徑反推公平選擇權價格，得對歷史上每一刻做連續避險模擬，
  「耗時、困難、容易出錯，而且終究不切實際」【原文實證，p.9：
  "time-consuming, difficult, error-prone and ultimately impractical"】，
  所以退而求其次，直接拿經驗分布當先驗（prior），不建模、不估參數。
  這是一個對本文問題極重要的方法論選擇：**業界處理「物理分布哪裡來」
  的實際答案之一，是乾脆不去擬合任何隨機過程，直接用歷史資料的
  經驗分布本身**。GS 的例子用了 **12 年**歷史報酬（1987 年 5 月至
  1999 年 5 月）來算一次 3 個月期選擇權的公平 skew【原文實證，p.11】，
  另一版本排除 1987 崩盤只用約 11 年【原文實證，p.11–12，前次調查
  已引用】。
- **GARCH／EGARCH 條件波動率模型**：學術文獻極厚（Duan 1995 及其後
  數十篇擴充），且**業界確實用**——但用的層面主要是**風險管理
  （VaR／RiskMetrics 式的日常波動率預測）**，不是本文要問的「選擇權
  定價」層面。搜尋摘要指出 JP Morgan 的 RiskMetrics 用 EWMA
  （λ=0.94，日資料）而非完整 GARCH，理由是計算成本與穩健性
  【搜尋索引轉述，⚠ λ=0.94 這個數字是被廣泛轉述的業界慣例，
  我沒有讀到 RiskMetrics 原始技術文件核對】；另有搜尋摘要指出「更
  複雜的模型不必然勝過簡單模型」，在 VaR 回測中 EWMA 有時比完整
  GARCH／stochastic volatility 犯規（violation）更少【搜尋索引轉述】。
  **這與「GARCH 選擇權定價模型」是兩件事——GARCH 當波動率預測引擎
  很常見，GARCH 當選擇權定價引擎（帶 LRNVR 那套）則證據薄弱得多**
  （§5 詳述）。
- **HAR-RV（Corsi）**：沿用前次調查已建立的證據等級與內容
  （`option-richness-assessment-methods.md` §4-M2），不重複列式——
  搜尋摘要稱其為這條文獻的 workhorse，優於 GARCH／ARFIMA-RV
  【搜尋索引轉述，前次已標註同一等級】。本文要補的一點是：HAR-RV
  的優勢主要來自**高頻（日內）已實現波動率**，日線版本只是粗糙代理，
  這點前次調查已提過、此處只做延續性提醒，不新開證據。
- **拔靴（bootstrap）分布**：把歷史報酬序列隨機重抽樣、疊出經驗分布，
  概念上與「直接用歷史分布」（上一條）同源，差別只在有沒有做重抽樣
  平滑。本文沒有找到獨立的第一手或搜尋來源專門討論這個變體用於選擇權
  定價，判定為**上一條方法的工程變體**，不單獨列證據。
- **情境／基本面疊加（scenario / fundamental overlay）**：這正是
  Option Chaser 使用者的起點（一個目標價＋目標日，本質是單一情境）。
  業界怎麼把單一情境變成可用分布，見 §6——這裡先指出：**沒有找到
  任何文獻把「單一情境」本身當成物理分布直接使用**；情境永遠是拿來
  **參數化**某個假設形狀的分布（通常是對數常態），而不是分布本身。
- **集成（ensemble）**：本次沒有找到專門討論「多個物理分布模型集成」
  用於選擇權相對價值判斷的第一手或搜尋來源。這與前次調查在 M1–M3
  已經確認「業界真的用」的單一模型（GARCH 當風險管理引擎、歷史分布
  當 SAS 先驗）不同層級，本文判定為**沒有找到證據，不代表不存在**，
  列入未能查證事項。

**小結**：**在「選擇權定價」這個特定用途下，本文找到最紮實的第一手
證據，指向的是最不花俏的做法——直接用歷史經驗分布當先驗，不擬合任何
隨機過程參數。** 更精緻的 GARCH／HAR 族在「預測未來已實現波動率」這個
鄰近但不同的問題上證據更強（且前次調查的 M1／M2 已詳細處理），但在
「把物理分布橋接到選擇權公平值」這個本文的核心問題上，證據反而集中在
更簡單的經驗分布 + entropy 橋接（見 §2）。

---

## 2. 物理分布如何變成 Call／Put／Vertical Spread 的模型公平值
### （這是委託點名的關鍵問題）

### 2.1 為什麼「直接對 P 積分期望報酬」不是答案

先講清楚陷阱：如果你有一個物理分布 `P(S_T)`，最直覺的做法是算
`e^(−r T) · E_P[payoff(S_T)]` 當公平值。**這在金融理論上是錯的**，
理由不是「不準」而是**它根本不是一個唯一定義的價格**——期望值算子
`E_P` 只回答「平均而言」，沒有對風險本身定價；兩個對風險趨避程度不同
的人拿同一個 `P` 會算出你「應該」付的兩個不同數字，但選擇權的**市場
成交價**不會因為換一個人來看就變。GS 論文的原話清楚點出這個張力：
`Q(·)` 與 `P(·)` **不可能完全相同**，因為 `Q` 之下標的價格的期望值
必須等於**現在的無風險遠期價**，而 `P` 之下的期望值是**過去的歷史
平均遠期價**，兩者跟現在的無風險利率毫無關係【原文實證，p.9】。
換句話說：**`P` 和 `Q` 的第一動差（均值）在定義上就不相等，任何
「直接對 P 積分」的做法都已經在用錯的 drift 訂價。**

### 2.2 正確的橋接：entropy 最小化 ＝ 指數傾斜，且與風險趨避程度無關

GS 給的解法是**把 `Q` 定義成「離 `P` 最近、但滿足無風險遠期條件」的
那個分布**，「最近」用相對熵（relative entropy，即 Kullback-Leibler
散度）衡量：

```
Min_Q  S(P,Q) = E_Q[ log(Q(S)/P(S)) ]                      (B1)

subject to
    ∫ Q(S_T)·S_T dS_T = S_0·e^(r_f T)      ——無風險遠期條件      (B2)
    ∫ Q(S_T) dS_T = 1                       ——機率歸一化         (B3)
```

【原文實證，Zou & Derman 1999, Appendix B, p.24–25】。用 Lagrange
乘子解這個約束最小化問題，得到的解是**指數傾斜（exponential
tilting／Esscher transform）**：

```
Q(S_T) = P(S_T) · exp(c₀ − c₁·S_T)                          (B4)
```

【原文實證，同上】。這個式子的意思很直白：**風險中性分布 = 物理分布
乘上一個對 `S_T` 遞減（多頭風險溢酬情境下 `c₁ > 0`）的指數權重**——
`S_T` 越高，權重越輕；`S_T` 越低，權重越重。直覺上這正是「賣方要求
補償尾部風險」的數學表達：市場對下檔給的隱含機率權重，比你單純從歷史
分布讀到的還要重。

**更重要的是獨立性結果**：GS 用另一條完全不同的路徑重新推導同一個
`Q`——設一個代表投資人，在均衡下用指數效用函數 `U(W_T) = −exp(−b·W_T)`
（`b` 是風險趨避參數）在無風險債券與一組完整的 Arrow-Debreu 證券之間
配置財富，求解使 `E_P[U(W_T)]` 最大化的配置。解出來的均衡風險中性分布
是

```
Q(S_t,t;E,T) = P(S_t,t;E,T) · exp(c₀ − c₁·E)               (C21)
```

跟 (B4) **完全同型**。論文接著明講最關鍵的一句：

> "the constant c0 and c1 (and thus the risk-neutral distribution Q)
> is independent of the parameter, b, of the utility function. It
> only depends on the prior distribution P, and the forward price
> constraint... It is essential that the risk-neutral distribution
> be independent of the investor's risk aversion!"

【原文實證，Zou & Derman 1999, Appendix C, p.29】。也就是說：**只要
代表投資人的效用函數屬於指數族（CARA），求出來的 `Q` 就跟這個投資人
究竟有多怕風險完全無關，只跟你選的物理分布先驗 `P` 與無風險遠期條件
有關。** 這回答了委託裡最尖銳的一個子問題——「離開風險中性框架後，
公平值到底是什麼意思」：**它不是「用某個猜測的風險溢酬把 P 打個折」，
而是「用 P 本身的形狀，去解一個滿足無套利遠期條件、資訊增量最小的
唯一 Q」**，這個 Q 不需要你（或市場）的風險胃納數字就能唯一確定。

### 2.3 正常態特例：退化成「保留你的 vol，換掉 drift」

論文有一則腳註把這個一般性結果對到最熟悉的直覺上：**如果歷史（物理）
報酬分布本身接近常態，entropy 最小化得到的 `Q` 就只是把 `P` 平移到
正確的風險中性利率，形狀完全不變**——「這個從歷史分布到風險中性分布
的平移不變性，在一般情況下不成立」【原文實證，p.10，footnote 7】。
換句話說：

- **常態（或近似常態）特例**：`Q` = 把你的 `P` 沿均值方向平移到
  `S_0·e^(r_f T)`，**你自己估的波動率（`P` 的第二動差）原封不動地
  變成定價用的波動率**。這正是初階金融課本教的「風險中性定價：
  drift 換成無風險率，vol 不變」——但這裡的「vol」是**你自己對物理
  波動率的判斷**，不是市場的 implied vol。
- **一般情況（有偏態／厚尾）**：平移不足夠，形狀本身也會被指數傾斜
  重塑——而且是朝著「放大下檔尾部權重」的方向，這正是股票報酬歷史上
  的負偏態會自動轉成 `Q` 下負 skew 的機制，不需要另外假設一個 skew
  參數。

**這個常態特例的處方，與完全獨立的另一條文獻線——GARCH 選擇權定價
——的核心處方一致**：Duan (1995) 的 **Local Risk-Neutral Valuation
Relationship（LRNVR）**：在 GARCH 過程下，**條件變異數在物理測度 P
與風險中性測度 Q 下保持相同，只有一期條件均值被換成無風險率**
【搜尋索引轉述】。用本文的語言講，這就是「§2.3 常態特例」的**動態、
參數化版本**：不管是 1999 年 GS 的非參數 entropy 方法、還是 1995 年
學術界的參數化 GARCH 方法，兩者對「怎麼把你的波動率判斷變成定價用的
波動率」給出的答案是同一句話——**保留你自己對波動率／分布形狀的判斷，
只修正到滿足無風險遠期這個約束為止，不要另外去猜一個風險溢酬折扣**。
這是本文認為對委託問題最直接、跨來源一致的答案。

### 2.4 對「Vertical Spread」具體怎麼算

拿到 `Q(S_T)` 之後，Call／Put／Spread 的模型公平值就是標準風險中性
定價：

```
C_model(K,T) = e^(−r_f T) · E_Q[max(S_T − K, 0)]
Spread_model(K1,K2,T) = C_model(K1,T) − C_model(K2,T)
```

GS 論文接著把這個 `Q` 反推出的價格換算回 **implied volatility**——
「取得公平價格後，我們反推出讓 Black-Scholes 公式等於這個公平價格的
那個波動率，這個程序可以對所有履約價與到期日重複，畫出一整條公平
implied volatility 曲面」【原文實證，p.10】。這一步很關鍵：**它把
「用你自己的分布算出的公平值」統一換算回市場的報價單位（vol 點）**，
這正是 §3 要講的比較口徑。

---

## 3. 貴賤與 edge 怎麼定義，才是可決策的

### 3.1 「貴／便宜」的定義本身很直接，難的是單位

一旦有了 §2 的模型公平 implied vol `Σ_H(K,T)`，貴賤定義沒有懸念：

```
SAS(K,T) = Σ_market(K,T) − Σ_H(K,T)
```

`SAS > 0` 表示這個履約價的市場報價比你（從你的物理分布橋接來的）
模型公平值貴，`< 0` 則便宜【原文實證，前次調查已引用同一定義，此處
不重複列 SAS_ATM 變體的完整公式，見前次調查 §4-M4】。**對 vertical
spread**，因為 SAS 是逐履約價定義的，包裹的 richness 就是兩腿殘差相減
（前次調查 §4-M8-B 已推導過權重與方向，本文不重複）。

### 3.2 為什麼優先用 vol 點，不用美元

**vol 點是這整套方法論裡「單位」的原生語言**：GS 論文從頭到尾把
richness／cheapness 表達成 implied volatility 的點差，不是美元價差
【原文實證，貫穿全文】。理由本文推斷有兩層（第二層屬合理推論，非
原文明講，故不標原文實證）：(1) vol 點在不同履約價、不同到期日之間
遠比美元價差穩定可比——同樣 1 美元的錯價，對深價外長天期合約與對
價平短天期合約代表的 vol 點數天差地遠；(2) vol 點可以透過 vega
直接換算回美元 P&L（`Δ$ ≈ vega × Δvol`），所以「用 vol 點算優勢、
用 vega 換算部位大小」是同一個框架裡自然銜接的兩步，這與前次調查
沒有找到反例，且與搜尋摘要「vega 曝險以美元／vol 點報價，讓部位
規模化更直覺」的說法方向一致【搜尋索引轉述，見引用清單 FlashAlpha
系列文章】。

### 3.3 交易成本：先扣，不是事後檢查

比較模型公平值與市場價之前，**市場價要用真實可成交的價位，不是
mid**——這點與前次調查在 M8 的分析一致（`net_worst` 用 Ask−Bid 而非
mid，前次調查已指出這使隱含機率偏保守）。本輪額外找到的補充證據：
搜尋摘要指出機構投資人的實際成交條件通常優於報價價差（一個常被引用
的基準是「有效價差約為報價價差的 25%」），但**這是機構議價能力，
不是零售可得的條件**【搜尋索引轉述，具體 25% 數字未在原文核對，
不應作為本產品使用者的決策依據——本產品使用者面對的是零售可得報價，
應該用 Ask/Bid 全額而非機構折扣價估算成本，這是保守但正確的方向】。
**沒有找到任何來源主張「先算出貴賤結論、再拿交易成本去打折」是正確
順序**——所有找到的討論（前次調查與本次）都是把成交成本當成比較前
就要扣掉的一部分，而不是事後的免責聲明。

### 3.4 「edge」該怎麼表達

本文沒有找到一個統一到「業界標準寫法」的 edge 定義，但綜合 §2–3.3，
可決策的 edge 至少需要三個獨立成分同時出現，缺一都不算完整：

1. **模型公平值 vs 市場價**（vol 點，§3.1–3.2）——回答「這組 spread
   相對於你自己的物理分布是貴是便宜」。
2. **成交成本**（§3.3）——回答「這個貴賤在你真的能拿到的價位上，
   還剩多少」。
3. **風險溢酬楔子的方向性提醒**（沿用前次調查 M8 第 7 問，本文不
   重複列式）——`Q` 系統性比 `P` 更看重下檔尾部，所以**任何用 `Q`
   反推出的「市場隱含機率」都會比你自己主觀相信的機率更悲觀**；
   如果你的物理分布判斷本身就已經是「市場低估了我的看法」，這個楔子
   是在幫你，如果你的物理分布判斷比市場更悲觀，這個楔子會讓你的
   edge 被低估。**量級本文仍未查到可信數字**（列入未能查證事項）。

---

## 4. 業界實際用的模型、資料與校準——具體到什麼程度

**資料需求（依 §1–2 找到的方法逐一列）**：

- **歷史經驗分布 + entropy 橋接（GS SAS 的實際做法）**：標的**日線
  報酬**，GS 論文的實例用了 **12 年**（1987/05–1999/05）與**約 11 年**
  （1988/05–1999/05，排除 1987 崩盤）兩個版本互相對照，藉此展示
  「歷史窗選擇本身就會翻轉結論」這個核心警告【原文實證，p.11–13，
  前次調查已引用】。**沒有找到 GS 使用日內／高頻資料的證據**——
  entropy 方法用的輸入是日線報酬序列。
- **當下完整選擇權鏈**：用來取得無風險遠期條件（S_F）與（若要用
  SAS_ATM 變體）當下 ATM implied vol 這個額外約束，以及事後把模型
  公平值換算回 vol 點時要對照的市場報價曲面。
- **期限對齊的無風險利率**（`r_f`）：用在遠期條件 `E_Q[S_T] =
  S_0·e^(r_f T)` 裡；文中沒有另外討論股息，但遠期價的標準寫法本身
  應含股息（本文未在原文找到 GS 明確處理股息的段落，列入未能查證）。
- **GARCH 族（用於波動率預測，非選擇權定價）**：搜尋摘要提到的
  RiskMetrics 慣例用日資料、EWMA 衰減參數 λ=0.94【搜尋索引轉述，
  數字未核對原文】；HAR-RV 的完整優勢版本需要日內（如 5 分鐘）已實現
  波動率序列，日線版是退化代理（沿用前次調查判斷）。
- **GARCH 選擇權定價（Duan LRNVR 及其後續）**：需要標的報酬序列去
  估計 GARCH 參數（物理測度），加上一組當下選擇權報價去校準
  risk-neutralization 之後的模型是否吻合市場——這是**兩階段校準**
  （先估 P 測度參數，再用選擇權市場資料校準或驗證 Q 測度轉換），
  比 SAS 的單階段 entropy 求解更重【搜尋索引轉述，校準流程描述，
  非數字】。

**小結**：**本文找到有第一手證據支持「業界真的這樣做」的資料需求，
落在相對克制的一端**——日線標的報酬（十年級距）＋當下一次完整選擇權
鏈＋期限對齊利率，這三樣都是低頻、可管理的資料量，且都不需要高頻
tick 資料或付費的機構持倉資料庫。**更精緻的方法（完整參數化 GARCH
選擇權定價、empirical pricing kernel 的跨期版本）證據等級只到搜尋
索引轉述，且描述中隱含的資料與計算需求明顯更重**（§5 詳述）。

---

## 5. 有實證支持 vs 學術優雅但業界不用

依委託要求明確分桶：

### 5.1 有實證支持、且能指名「真的有人這樣定價」

- **Minimum relative entropy／canonical valuation（Stutzer 1996）→
  GS 內部指標 SAS（1999）**。這是本文找到唯一一條**從學術方法到
  真實內部交易台指標**、且本文親自讀過落地版本原文的鏈路
  【原文實證：GS 論文本身；Stutzer 原文未取得，屬搜尋索引轉述，
  但 GS 論文腳註明確引用它與 Buchen & Kelly (1996)、Gulko (1996)
  三篇獨立文獻線，指出「entropy 在金融經濟學與衍生品定價的相關性
  已有多位作者研究過」【原文實證，p.9，footnote 6，我親眼看到這個
  引註，但沒有讀過被引的三篇原文本身】】。
- **EWMA／簡單 GARCH(1,1) 當波動率預測引擎**：搜尋摘要一致認為這是
  業界（尤其風險管理端）的主力，且有研究指出更複雜模型不必然在
  out-of-sample 表現更好【搜尋索引轉述，見引用清單】。**但這是「預測
  波動率」的證據，不是「用來給選擇權定價」的證據**，兩者不可混為
  一談——本文刻意把這條列在「有支持」桶，是因為它支持的主張範圍
  本身就窄（波動率預測，不是選擇權公平值）。
- **VRP 作為指數層級的可交易現象**：沿用前次調查已建立的證據
  （Carr & Wu 2009、Bakshi & Kapadia 2003，皆搜尋索引轉述），本文
  不重複列數字，只在此重申其證據等級與前次調查一致。

### 5.2 學術優雅、但沒有找到「業界真的據此對散戶方向性 spread 定價」的證據

- **GARCH 選擇權定價模型（Duan 1995 LRNVR 及其後續 mLRNVR）**：
  文獻量極大、被引用次數高，但**有直接的負面實證**——搜尋摘要指出
  Christoffersen & Jacobs (2004) 發現 LRNVR 字面限制下的 GARCH
  選擇權模型定價與避險表現不佳，Barone-Adesi et al. (2008) 進一步
  指出問題根源就是 LRNVR「兩測度下變異數相同」這個限制本身，後續
  必須放寬成 modified LRNVR（讓風險中性測度下的變異數持續性高於
  物理測度，藉此捕捉 variance risk premium）才勉強修正
  【皆搜尋索引轉述，具體統計量未取得】。**本文沒有找到任何來源指出
  一般方向性選擇權交易台，會用完整參數化 GARCH-Q 模型去給單一標的
  的 vertical spread 定價**——它出現的脈絡始終是學術期刊間的模型
  優劣比較，不是「這是某家投行的內部工具」。這與 §5.1 的 SAS
  （有明確的「這是我們內部真的在用的工具」原文陳述）形成鮮明對比。
- **Empirical pricing kernel（Rosenberg & Engle 2002 及其後續）**：
  理論上直接回答「風險中性密度 ÷ 物理密度 = pricing kernel」這個
  委託關心的問題本身，且催生了有名的「pricing kernel puzzle」
  （估出來的 kernel 在某些財富區間遞增，違反標準風險趨避理論的
  預期）【搜尋索引轉述】。但這條文獻的實作需要**大量橫斷面選擇權
  報價的時間序列**（原始論文是月度、1991–1995 年 S&P 500 選擇權）
  去非參數估計密度比值，**本文沒有找到任何跡象顯示這是一個被用來
  給單一標的、單一到期日 vertical spread 定價的日常工具**，它在
  搜尋結果裡出現的脈絡始終是「風險趨避的實證研究」而非「交易台的
  定價引擎」。與 GS SAS 相比，這是**同一類問題（P→Q 橋接）的另一種
  解法，但停留在學術診斷工具的層級，沒有找到落地成交易台指標的證據**。
- **Sinclair《Positional Option Trading》所描述的「方向性選擇權
  量化交易法」**：搜尋到的書商簡介稱其涵蓋「term-structure premia、
  earnings 效應、BSM 穩健性、部位規模」等主題，**聽起來與本文的
  委託問題高度相關**，但本文**完全沒有讀到原文**，連一段可信的
  原文摘錄都沒找到——現有材料只到 Amazon／Wiley／書評網站的行銷
  簡介等級，比一般搜尋索引摘要更弱（沒有具體公式或數字可轉述，
  只有主題列表）。**本文刻意不把它列入「有支持」桶**，因為委託明確
  要求「不要把只讀過摘要的內容當成驗證過的來源」——這本書可能正是
  最貼近委託問題的實務文獻，但本次調查條件下無法驗證其具體內容，
  只能誠實列入下方「未能查證的事項」。

---

## 6. 對應到 Option Chaser 的情況：從「目標價＋目標日」到可用的分布

**本節不設計實作，只描述業界如何處理同一個問題**（委託明確要求）。

### 6.1 Option Chaser 現有、可直接餵給 §2 流程的東西【repo 實證】

以下逐項核對過 repo 現況，非轉述舊研究文件：

- **標的現價**：`option_chaser/data/cboe.py`／`data/yf.py` 每次刷新
  取得。
- **完整選擇權鏈，含每張合約的 implied volatility**：同上，
  `cboe.py` 一次 GET 回全鏈，含 bid／ask／last／volume／open_interest／
  **iv**。
- **期限對齊的無風險利率**：`option_chaser/ratecurve.py` ＋
  `option_chaser/data/treasury.py`，`valuation.leg_rate` 依到期日
  各自查表。
- **股息殖利率**：`valuation.py` 的 `bs_call`／`leg_greeks` 等函式
  均帶 `q` 參數（例如 `leg_greeks(..., q: float = 0.0)`），
  `option_chaser/data/dividends.py`／`dividends.py`（頂層）存在
  ——這與 CLAUDE.md 記載「T12／#26 已完成期限對齊利率＋股息」一致，
  本次直接讀程式碼確認為真，非沿用舊文件的說法。
- **到期日（days-to-expiry, T）**：`AnalysisParams.rate_by_expiry`
  按到期日分組已在手，`timeframe.py` 是純函式的年月／到期日選取
  模組。
- **每腿 Greeks（含 delta）**：`valuation.leg_greeks`。
- **跨刷新累積的候選快照時間序列**：`store.list_result_paths()`／
  `workspace.spread_history()`。
- **(tenor, delta) 座標上的 IV 歷史重錨定**：`option_chaser/
  ivhistory.py`（19.8K，docstring 明寫「歷史序列不是『這張合約過去的
  IV』，而是『過去每一天，那天的鏈上與今天這個候選同樣座標的那個 IV
  是多少』」）——**這正是前次調查 M7（delta／期限正規化）建議的資料
  結構已經有雛形**，本文確認其存在，但沒有深入讀它的完整實作（超出
  本次委託範圍：只需要盤點，不需要評估實作）。

**結論**：§2 的橋接流程（`P` → entropy 最小化 → `Q` → 折現期望payoff）
在計算層面**不缺任何一個輸入**——標的價、遠期條件所需的 `r_f`／`q`、
以及事後要對照的市場 implied vol 曲面全部已經在引擎裡。**缺的是「`P`
從哪裡來」這一步**，而這正是 §6.2 要講的、委託要求聚焦的問題。

### 6.2 業界如何把「一個目標價＋一個目標日」變成可用的 `P`

**本文在 §1 已經指出：沒有找到任何文獻把單一點看法直接當成分布使用。**
綜合 §1（物理分布怎麼建）與 §2.3（常態特例的橋接處方），業界處理
「我只有一個點看法」這個問題的標準做法，可以拼出以下模式：

1. **先選一個分布形狀（幾乎總是對數常態，即 log-return 常態）**——
   這是 Black-Scholes 本身假設的形狀，也是 §2.3 常態特例能直接套用
   「只換 drift、保留 vol」這個簡化處方的前提。GS 論文的**非參數**
   版本（直接用歷史經驗分布，不假設常態）是在「有充分歷史資料、且
   想保留真實偏態厚尾」時的做法；但當輸入只是一個點看法（沒有一整段
   歷史路徑可言）時，**沒有「經驗分布」可用，只能回到參數化假設**——
   這是本文推論、非原文明講，但邏輯上是 §1／§2 兩節內容的直接延伸：
   非參數方法需要一段歷史路徑當輸入，點看法沒有路徑，所以無法套用
   非參數版本，只能走參數化路徑。
2. **把目標價當成這個分布在目標日的均值或中位數**——即用你的方向性
   看法釘住分布的**第一動差（位置）**，這一步業界文獻裡最接近的
   直接對應，是 GS 的 **SAS_ATM 變體**：SAS_ATM 額外約束
   `RNHD` 重現市場的 at-the-money-forward 價格，使
   `SAS_ATM(S_F[T], T) = 0`——概念上就是「先釘住一個參考點（那裡是
   市場遠期價，本文情境是你的目標價），再談其他履約價相對這個參考點
   貴不貴」【原文實證，前次調查已引用同一機制，此處只是指出它與
   「釘住點看法」是同一種操作，本文不重複公式】。
3. **分布的寬度（波動率）從哪裡借**——這是「點看法→分布」這一步
   唯一還需要一個外部輸入的地方，業界的兩個可能來源在本文材料中
   都有蹤跡：(a) 用**市場當下的 ATM implied vol**當寬度——優點是
   跟市場現狀一致、零額外資料成本，缺點是你等於承認「我對這件事
   会怎麼發生沒有自己的波動率判斷，只有均值判斷」；(b) 用**你自己
   對標的歷史波動率的估計**（§1 的 GARCH／EWMA／歷史 vol 三選一）
   當寬度——優點是保留了你自己的判斷、與 §2.3 的「保留你的 vol、
   換掉 drift」處方完全吻合，缺點是需要標的的歷史報酬資料。

   > **【repo 實證，本文撰寫後校對時新增更正】**：這裡引用前次調查
   > 原文「Cboe 端點無歷史、yfinance 被排除在 serverless 相依外」
   > 已經過時——前次調查發佈後已由**前次調查文首的事後更正**（同一
   > 檔案）指出並經人工複核確認：`option_chaser/data/dividends.py`
   > 呼叫的 Yahoo chart 端點本身就帶
   > `range=2y&interval=1d`（見該檔第 39–40 行），已經在跟 vendor
   > 要 2 年日線；目前的 parser 只解析同一份回應裡的
   > `events.dividends`，**沒有**解析 `indicators.quote[].close`——
   > 也就是說 (b) 這個選項**不缺資料源、只缺一段 parsing**，不是
   > 本文原稱的「沒有這個資料源」。且此端點已有 production 實測
   > 記錄（CLAUDE.md #120，GitHub Actions 真實出口實測 HTTP 200）。
   > 這處更正**不影響**本文其餘結論（entropy 橋接、edge 定義、
   > 業界實證分界線皆與此無關），只影響「(b) 選項在 Option Chaser
   > 現況下可不可行」這一句話本身。
4. **把這個「釘住均值、借來寬度」的參數化 `P` 餵進 §2 的 entropy／
   drift-replacement 橋接**，得到 `Q`，才能算模型公平值、才能跟市場
   價比出貴賤。

**本文沒有找到「業界標準捷徑」這個委託字面問的東西的第一手證據**——
即沒有找到一份文件明確寫著「給一個價格目標和一個日期，直接這樣算」
的操作手冊。找到的是**拼出來的邏輯鏈**：(1) 點看法先參數化成分布
（形狀通常對數常態）；(2) 均值釘目標價；(3) 寬度借自市場 ATM vol 或
自己的歷史波動率估計，這兩個選項業界文獻裡都各自有支持但沒有明確
「哪個才是標準做法」的排序；(4) 用 §2 的橋接處方（entropy 最小化，
常態特例下退化成單純換 drift）把這個 `P` 轉成 `Q`。**這條邏輯鏈的每
一個環節都有本文找到的某種來源支持，但沒有任何單一來源把全部四步
串成一份「這就是業界標準做法」的操作手冊**——這是本文對委託第 6 個
子問題最誠實的答案：業界處理的是同一類問題（用一個判斷去撐開一個
可定價的分布），但本文沒有找到把它寫成單一標準捷徑的原始文件。

---

## 未能查證的事項

1. **Colin Bennett《Trading Volatility》、Euan Sinclair《Volatility
   Trading》與《Positional Option Trading》、Sheldon Natenberg
   《Option Volatility and Pricing》的原文**——委託明列為應視為第一手
   實務來源的三位作者，本次窮盡了官方網站、GitHub 鏡像搜尋、code
   search 等管道皆未取得可讀原文，只能退回書商簡介與部落格轉述，
   證據等級全部標為【搜尋索引轉述】甚至更弱。**若要真正驗證，
   需要一個能存取這些書籍原文（購買版、圖書館資料庫，或未被此沙箱
   proxy 擋住的合法線上閱讀管道）的環境。**
2. **Stutzer (1996)、Duan (1995)、Christoffersen & Jacobs (2004)、
   Rosenberg & Engle (2002)、Barone-Adesi et al. (2008) 的原文**——
   全部網域（Wiley、SSRN、ScienceDirect、arXiv、中國大陸鏡像站
   `cfrn.com.cn`、台大教師個人網頁 `math.ntu.edu.tw`）皆被 proxy
   擋下，本文對這些論文的描述**全部來自搜尋引擎摘要，未逐字核對**。
3. **風險中性測度與物理測度之間楔子的量級**（§3.4 第 3 點）——沿用
   前次調查已列的同一項未查證事項，本輪沒有新進展：方向明確（`Q`
   系統性比 `P` 看重下檔尾部），但沒有找到可信的量化數字。
4. **RiskMetrics EWMA λ=0.94 這個具體參數**——被搜尋摘要廣泛轉述為
   業界慣例，但本文沒有讀到 JP Morgan 的原始技術文件核對，也沒有
   查證這個參數在 2026 年是否仍是業界現行慣例（原始 RiskMetrics
   文件年代久遠）。
5. **機構「有效價差約為報價價差 25%」這個數字**（§3.3）——搜尋摘要
   給出但未核對原文，且即使屬實也是機構議價能力的產物，不代表本產品
   零售使用者可得的條件，本文引用時已明確標註不應作為決策依據。
6. **GS SAS 論文是否處理股息**——本文讀過的段落（entropy 推導、
   Appendix B/C、Table 1 對照）沒有出現股息殖利率的討論，但本文沒有
   逐頁讀完全文（前次調查已讀過的段落與本次新讀的 Appendix 段落
   合計仍非全文），不能排除股息處理在本文未讀到的段落。
7. **「點看法→參數化分布→橋接」這條邏輯鏈（§6.2）是否有單一原始
   文件把它寫成一份操作手冊**——本文明確找不到，已在正文誠實列為
   「沒有找到，不代表不存在」。若要查證，方向是尋找面向零售/半專業
   使用者的投行「期權策略構建」培訓材料（往往不對外公開），或
   直接聯繫有相關經驗的從業者做訪談，本沙箱的搜尋與 git clone 管道
   都無法觸及這類非公開材料。

---

## 引用清單

**【原文實證】（git clone 取得，逐頁讀過相關章節；第三方鏡像
`github.com/s0ap/gs-quantitative-strategies-research-notes`）**

- Joseph Zou & Emanuel Derman, *Strike-Adjusted Spread: A New Metric
  For Estimating The Value Of Equity Options*, Goldman Sachs
  Quantitative Strategies Research Notes, July 1999.
  （本文新引用處：Entropy 與 RNHD 定義 p.8–10；「嚴謹但不切實際」的
  連續避險模擬替代方案論述 p.9；歷史窗長度 12 年／11 年的實例 p.11；
  SAS_ATM 定義與 at-the-money-forward 錨定 p.12；Appendix A（entropy
  數學定義）p.21–23；Appendix B（relative entropy 最小化與指數傾斜
  解 B1–B4）p.24–25；Appendix C（代表投資人指數效用均衡推導，
  風險中性分布與風險趨避參數 b 無關的結論）p.26–29。前次調查
  已引用同一篇論文的 skew 公平值 Table 1 與「無法迴避判斷」p.13，
  本文不重複列頁碼。）

**【搜尋索引轉述】學術（原文未取得）**

- Jin-Chuan Duan (1995), "The GARCH Option Pricing Model",
  *Mathematical Finance* 5(1).
  https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9965.1995.tb00099.x
- Michael Stutzer (1996), "A Simple Nonparametric Approach to
  Derivative Security Valuation", *Journal of Finance* 51(5):1633–1652.
  https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb05220.x
  （GS SAS 論文本身引用此文為 entropy 方法的學術源頭之一——這一點
  是【原文實證】，但 Stutzer 論文本身的內容我沒有讀過原文。）
- Joshua V. Rosenberg & Robert F. Engle (2002), "Empirical Pricing
  Kernels", *Journal of Financial Economics* 64(3).
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X02001289
  （亦見 NBER Working Paper 6222, "Option Hedging Using Empirical
  Pricing Kernels"。）
- Peter Christoffersen & Kris Jacobs (2004), "Which GARCH Model for
  Option Valuation?", *Management Science*.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=306843
- Giovanni Barone-Adesi et al. (2008), "A GARCH Option Pricing Model
  in Incomplete Markets"（LRNVR 限制與 mLRNVR 修正的討論）。
- Peter Christoffersen, Kris Jacobs & Chayawat Ornthanalai,
  "GARCH Option Valuation: Theory and Evidence".
  https://www.ssrn.com/abstract=2054859
- Fulvio Corsi, HAR-RV model（沿用前次調查引用，本文不重複列出
  完整書目資訊，見 `option-richness-assessment-methods.md` §4-M2）。

**【搜尋索引轉述，且證據等級低於一般學術摘要——僅書商／書評轉述】**

- Colin Bennett, *Trading Volatility: Trading Volatility, Correlation,
  Term Structure and Skew*（作者官網 trading-volatility.com 被
  proxy 擋，內容未取得，僅知書名與章節架構）。
- Euan Sinclair, *Volatility Trading*, 2nd ed., Wiley.
- Euan Sinclair, *Positional Option Trading: An Advanced Guide*,
  Wiley, 2020.（Amazon／Wiley／Porchlight 書介：涵蓋方向性選擇權
  量化交易、term-structure premia、earnings 效應、BSM 穩健性、
  部位規模——內容未取得，僅知主題列表。）
- Sheldon Natenberg, *Option Volatility and Pricing: Advanced Trading
  Strategies and Techniques*, 2nd ed., McGraw-Hill.（"theoretical
  edge" 概念的轉述來自第三方書評／筆記網站，非原文。）

**【搜尋索引轉述】產業／部落格**

- FlashAlpha, "Complete Guide to Volatility Relative-Value Trading"／
  "Variance Risk Premium vs Volatility Risk Premium"（vol 點單位、
  vega 曝險報價慣例的轉述來源）。
- Party at the Moontower（Kris Abdelmessih，前 Susquehanna
  選擇權交易員部落格），"the option market's point spread"——網域
  被 proxy 擋，僅見搜尋結果標題，內容未取得，本文未引用其具體主張，
  僅記錄其存在供後續查證。

**【repo 實證】本 repo（本次直接讀過，非沿用前次調查的舊記錄）**

- `option_chaser/valuation.py`（`bs_call`／`leg_greeks` 帶股息殖利率
  參數 `q`；`leg_rate`）
- `option_chaser/ratecurve.py`、`option_chaser/data/treasury.py`
  （期限對齊利率曲線）
- `option_chaser/data/cboe.py`（主資料源，含每合約 iv）、
  `option_chaser/data/dividends.py`、`option_chaser/dividends.py`
  （股息，頂層與 data 層各一個檔案，本次確認兩者皆存在）
- `option_chaser/ivhistory.py`（19.8K，(tenor, delta) 座標 IV
  重錨定模組，docstring 明寫「不外插」原則）
- `option_chaser/timeframe.py`（年月／到期日純函式選取）
- `option_chaser/store.py`、`option_chaser/workspace.py`
  （`list_result_paths`／`spread_history`，跨刷新歷史累積機制）
- **checkout 完整性核對**：`git log --oneline -3` HEAD 為
  `46d3bf8`，符合委託描述的「應為 46d3bf8 或更新」，非前次調查
  遭遇的回退陷阱狀態。
