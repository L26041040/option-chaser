# Vertical Spread 的「Package 貴不貴」——是否存在一個誠實的估值方法

研究日期：2026-09-09／分支 `claude/implement-tfm9oa`。本文是一份**收斂
裁決文件**，不是新的探索性研究——委託明文要求整合既有八份文件並給出
一個不含糊的答案。「Package」＝整組兩腿 debit vertical spread 當一個
單位，不是它任一條腿。

## 證據分級（沿用本 repo 既有四級慣例）

- **【一手原文】**——本輪或既有研究實際逐字讀過的原始文獻。
- **【官方文件】**——擁有該規格的組織自己發布的文件。
- **【二手轉述】**——搜尋索引摘要、部落格，或本輪打不開因此只能轉述的
  來源。
- **【自行推論】**——本文自己的推導或引擎實算，附輸入與重現步驟。
- **【repo 實證】**——本輪直接讀取本 repo 原始碼得到的事實（檔名:行號）。

**本文的證據結構**：八份既有文件的一手／官方文件證據已在各自文件中
交代清楚，本文不重複轉述其查證過程，只轉引其**結論與已驗證的數字**，
並在必要處用【repo 實證】＋【自行推論，本輪引擎重算】補上「這件事在
2026-09-09 的程式碼上是否依然成立」的獨立覆核。凡是本文自己重算出跟
既有文件不同的數字，會明講差異與原因（見 §4.2 的一處真實落差）。

---

## §0. 執行摘要與裁決

### 裁決：**NO RELIABLE PACKAGE VALUATION YET**

不是「暫時查不到」，是**結構性**的——每一個曾經被認真評估過的候選方法，
都落進以下三個桶子之一，沒有例外：

1. **有一個真正的估值參照系，但可信的那部分小於報價雜訊底噪**
   （surface residual、SAS 的 skew 那一半）。
2. **有一個真正的估值參照系，且量級夠大，但那個大的部分本身已被
   獨立否決為「不是錯價」**（SAS／IV−RV 的 level 那一半＝variance risk
   premium，不是 mispricing）。
3. **根本不是對「參照值」的比較，只是把價格換個單位講**（debit/width
   隱含機率、box parity、任何歷史 percentile／rank 家族），因此**依定義
   不構成估值**，不管它包裝得多精緻。

**現行已出貨的兩個「貴不貴」候選頭條**（Spread IV Gap percentile、
Normalized Skew Ĝ percentile）屬於第 3 桶且已被**引擎實測證偽**：對純
vol-level 造成的真實成本變動（本輪重算：debit +8.5%～+73.9%，視 q
假設而定），兩者的讀數對這個變動**完全視而不見**（gap 恆為 6.00 pts，
Δ=0.0000）或**方向相反**（Ĝ 從 0.400 掉到 0.240，即讀成「更便宜」）。
這不是「不夠精確」，是「讀反了」。

**本文的核心概念性發現**（既有八份文件都沒有明講到這一步）：2026-08-26
研究提出的 VORD（Vol-Only Repriced Debit/Credit）**修好了讀反的問題，
但它仍然不是估值**——它是「用今天的 S/T/r/q 但用歷史那天的 σ 重新
定價」，answer 的問題是「這個結構的**歷史 vol 水位**現在算不算高」
（Q2：相對自身歷史的位置），不是「這個結構**現在的價格**相對某個
獨立於價格本身的基準是不是太貴」（Q1：估值）。VORD 是這個 repo 目前
能拿到的**最好的描述性指標**，但用委託給定的定義（「參照值不能是價格
本身的另一種說法」）去檢驗，它沒有通過——它的「歷史」就是它自己
（重定價後）過去的樣子，不是一個外於價格的公平值。

### 三個必須同時成立、但沒有一個方法能全部滿足的條件

| 條件 | 誰做到了 | 誰做不到 |
|---|---|---|
| 有一個不是「價格本身」的外部參照 | SAS（標的歷史報酬分佈）、surface residual（同日鄰居）、box parity（無套利恆等式） | Ĝ、raw gap、VORD、任何歷史 percentile／IV-rank 家族——參照系都是「這個量自己過去的樣子」 |
| 可信量級大於報價雜訊底噪 | SAS 的 level 成分、raw gap 的絕對值 | SAS 的 skew 成分（0.15–0.50 vol pt vs 半寬 0.80–2.65 pt）、surface residual（LEAPS 期 41/41 觀測落在半價差內）、box parity（88% 埋在四腿交易成本內） |
| 大的那部分是「錯價」不是「風險溢酬」 | （無——這是三個桶子互斥的核心） | SAS／IV−RV 的 level 成分被其論文作者自己歸零（是 variance risk premium，不是 mispricing） |

---

## §1. 委託框架：描述性 vs 估值（不可模糊的界線）

委託要求的判準：**估值＝主張目前的成交價高於或低於某個防禦得住的
參照值，且該參照值不是價格本身的改寫**。「一個量有一年走勢圖／
percentile」不構成估值——這件事本身已經是本 repo 2026-08-26 研究的
核心發現，也是本文全篇要重複套用的唯一濾網。

把這個濾網套在每一個候選上，得到兩個獨立的問題：

- **Q_ref**：這個方法的參照系是不是外於價格本身？（是＝可能是估值；
  否＝一定是描述性）
- **Q_size**：若 Q_ref 為是，可信的訊號量級是否大於報價雜訊底噪？

只有 Q_ref＝是**且** Q_size＝是**且**那個訊號不是已知的風險溢酬，才
算估值。下一節逐方法檢驗。

---

## §2. Prior-art ledger：逐方法檢驗

### 2.1 Raw IV Gap（`Sell IV − Buy IV`）percentile——**已出貨、描述性、已證偽**

- **它量什麼**：兩張 exact-contract 逐日重建 IV 序列相減後的絕對差，
  裁窗、取 percentile／Δ4w（`option_chaser/ivspread.py:31-52` 的
  `align_spread_gap()`；`ivpipeline.py:735-760` 的 `spread_gap_payload()`
  把它接進 `ivtrend.py` 的 `trim_to_window`／`historical_percentile`／
  `delta_4w`）。**現為 Spread 詳細頁的卡片頭條**——`src/SpreadSummary.tsx:1-3`
  自述「SIG-03／#174：把 SIG-01（#172）新增的 spread_gap API 區塊接進
  留的空版位」，畫面上方顯示「Spread IV Gap」與其百分位。
- **Q_ref**：否。參照系是「這個 gap 自己過去的樣子」，不是任何外部
  公平值。這在定義上就是描述性統計量，不是估值——即使 UI 上看起來
  像一個「貴不貴」的答案。
- **已知致命缺陷**（本輪重算，見 §4.2）：對純 vol-level 造成的真實
  debit 變動（本輪：+8.5%～+73.9%）完全不動（Δ=0.0000 恰好）；對純
  skew 形狀變動，方向與 debit 實際變動**相反**（gap 擴大時 debit 反而
  下降）。
- **來源**：`docs/research/strategy-valuation-metric-percentile.md`
  §3.1（引擎實算：level 12%→22% 時 gap 讀數 0.0%、debit +59.9%；skew
  變陡 ×2 時 gap +100.0%、debit −42.6%，符號相反）——本輪用當前
  程式碼獨立重算，結論不變（§4.2）。

### 2.2 Normalized Skew `Ĝ = (σ_sell − σ_buy) / σ_ATM` percentile——**已出貨（Advanced 收合區）、描述性、對 package 貴賤符號常錯**

- **它量什麼**：raw gap 除以當日 ATM IV，理由是讓不同 vol regime 下的
  skew 形狀可比（`option_chaser/ivhistory.py:97-107` 的
  `normalized_skew()`；成分本身有先例——÷ATM normalize 是 Mixon 2011／
  Natenberg 1994／SAS_ATM 的既有作法，`docs/research/
  candidate-iv-relative-value.md` §5.1–5.2）。
- **Q_ref**：否，同 §2.1——參照系仍是自身歷史，只是分子換成正規化過的
  形狀量。
- **已知致命缺陷**：÷ATM 正規化解決的是「level regime 不同時 skew
  數字不可比」，**不解決**「level 本身變動時 Ĝ 對 package 真實貴賤的
  符號」——本輪重算（§4.2）顯示 level 上升時 Ĝ **下降**（0.400→0.240，
  即「讀成更便宜」）而 debit 上升 19.4%。此外 ÷ATM 完全不移除
  roll-down（同一份 fixture 環境凍結、DTE 882→252，raw gap 與 Ĝ
  同步漂移 +87.1%——`docs/research/
  historical-rich-cheap-canonical-methodology.md` §8.1）。
- **必要 normalization 本身的先例仍然成立**（不是說 ÷ATM 這個動作沒
  價值）：問題是「Ĝ percentile 能不能單獨回答 package 貴不貴」，不是
  「÷ATM 這個手法有沒有道理」。兩者是不同的問題。

### 2.3 Vol-level／IV-Rank 家族（單腿 constant-(tenor,delta) percentile）——**單腿合法（Q2），不構成 package 估值**

- **它量什麼**：`buy_iv`／`sell_iv`／`atm_iv` 各自的 fixed-(tenor,delta)
  重錨定序列 percentile（`ivhistory.py:499-529` 的 `field_metrics()`；
  單腿 exact-contract 版見 `ivtrend.py:170-185` 的 `historical_percentile()`）。
- **Q_ref**：否（水位相對自身歷史），但這對**單腿** Long Call／Long
  Put 是既有裁決接受的合法答案（`docs/research/
  historical-rich-cheap-canonical-methodology.md` §11.3：「本文未發現
  任何推翻它的證據」）——因為單腿本來就沒有「兩腿之間」的問題，Q1 與
  Q2 在 SAS 論文的字面上本來就對單腿 model-value 才有意義，而單腿
  這裡誠實只做 Q2，不冒充 Q1。
- **對 package 為什麼不夠**：兩腿各自的 IV percentile 不能相加或平均
  合成一個 package 答案——`net volatility` 公式在真實部位上數值不穩定
  （§2.6）；且兩個獨立的 Q2 讀數本身就不是「package 相對某個外部公平
  值」的陳述，二合一並排顯示（現行 UI 做法）也仍然是描述性，不是估值。

### 2.4 SAS／Fair-Value Residual（Zou–Derman，相對標的歷史報酬分佈）——**唯一真正的 Q1 候選，兩半都用不上**

- **它量什麼**：把標的的歷史報酬分佈經 entropy 最小化轉成風險中性
  分佈（RNHD），反推出「歷史公平 IV」`Σ_H(K,T)`，
  `SAS(K,T) = Σ_market − Σ_H`——**這是本文檢驗過的方法裡唯一
  Q_ref＝是的候選**：參照系是標的的歷史報酬史，不是這個選擇權自己的
  價格史。
- **Q_size 判定＝否，且理由是結構性的，不是資料不夠**：
  - **可信但小的那一半**（skew／SAS_ATM）：本輪引擎實算 0.15–0.50
    vol 點，vs 買賣價差半寬 0.80–2.65 vol 點——訊噪比 0.10–0.27×
    （`historical-rich-cheap-canonical-methodology.md` §4.5／§5.4）。
  - **大但不可信的那一半**（level／IV vs RNHD-implied level）：
    論文作者自己在 SAS_ATM 版本把它**主動歸零**，因為「the current
    level of at-the-money implied volatility is the most believable
    estimate of future volatility」【一手原文，同上 §3.2】——這個成分
    等價於 IV−RV／variance risk premium，見 §2.7 已被獨立否決的
    理由。**不是因為算不出來，是它的作者自己說不可信。**
  - **三難**（同上 §5.4）：不存在一個「可信、量級夠大、又能在 LEAPS
    tenor 上歷史化」的 fair-value 殘差——這不是工程問題，是這個問題
    本身的結構。
- **SAS 論文自己劃的紅線**（腳注 3，一手原文）：「A positive SAS
  connotes richness only for standard options whose value is a
  monotonically increasing function of volatility」——spread 價值對 σ
  非單調，**必須逐腿算，永遠不能湊出一個 spread 單一 SAS 數字**。

### 2.5 Surface Residual（相對同日鄰近履約價）——**合法 Q1，但答的是另一題，且多數時候安靜**

- **它量什麼**：市價相對「今天這條鏈自己」平滑後的參照曲線（per-expiry
  加權二次式，或 Cboe `theo` 欄位）的偏離——`docs/research/
  spread-surface-residual-rv.md` §2.4／§6，用真實 Cboe 全鏈（758 筆）
  實測驗證過 fit 品質。
- **Q_ref**：是——參照系是同一時刻、同到期的鄰近履約價，不是這個
  candidate 自己的價格史，也不是它自己歷史上的位置。這是本文檢驗過
  的方法裡**第二個**真正的 Q1 候選。
- **Q_size 判定＝視情況，多數時候「否」**：真實鏈實測，LEAPS 期
  41/41 個殘差觀測落在買賣價差半寬**之內**（同上 §6.1）——健康報價
  下這個指標**大部分時間沒有話講**，只在報價品質出問題時（離群報價、
  盤外殘留怪 ask）才有訊號，定位是「保險絲」不是「天天有態度的
  主指標」（同上 §7）。
- **它答的問題與委託問題正交**：surface residual 答「這兩張報價
  今天挑得好不好」（cross-sectional，零歷史依賴），委託問的「這個
  package 現在貴不貴」若隱含「相對它自己過去」則是另一題——**兩者
  在同一天可以給出相反答案**（一張報價相對鄰居很正常，但整條鏈今天
  相對半年前都貴了 10 個 vol 點，surface residual 對後者完全看不見）。

### 2.6 Debit/Width 隱含機率讀數——**合法、乾淨，但不是估值**

- **它量什麼**：`D/W = DF × 帶狀平均生存機率`——模型無關、精確成立的
  恆等式（`docs/research/spread-implied-probability-readout.md` §3.1，
  自行推導＋數值自洽驗證）。有厚實機構先例（Breeden–Litzenberger、
  央行 option-implied PDF、Morgan Stanley 公開定義、Kalshi 的
  ¢-per-$1）。
- **Q_ref**：**否，且是唯一結構上不可能滿足的候選**——它沒有「參照
  值」這個概念存在的空間。D/W 本身**就是**市場對這注 payoff 開的價，
  它回答「市場此刻怎麼定價這個結果」，不回答「這個定價相對什麼是貴
  是便宜」。委託文字要求的「reference 不能是價格本身的改寫」，D/W
  連改寫都不用——它**就是**價格，換個單位（機率）講。
- **這不是缺點，是它的定位本來就不同**：委託自己排除的「edge vs 自建
  預測」（比較市場機率與使用者自己對機率的看法）才是能把 D/W 轉成
  「貴不貴」判斷的那一步，而那一步需要使用者自己的機率模型——不是
  這個 repo 能替使用者做的事。

### 2.7 IV − Realized Volatility（VRP）——**明確否決，類別錯誤**

- **它量什麼**：隱含波動率減已實現波動率。
- **Q_ref**：表面上是（參照系是已實現的歷史波動），但**否決理由不是
  Q_size，是分類錯誤**：SAS 論文第 1 頁把它列為與 SAS **並列**的另一
  把尺，是「options replicators 的指標」，用途是鎖定 delta-hedge 到期
  的變異數價差【一手原文，`historical-rich-cheap-canonical-methodology.md`
  §5.3】。它量的是 **variance risk premium**（承擔 vol 風險的補償），
  一個持續為正的保險費不是錯價。且它在有 skew 時本質上不精確（單一
  RV 數字要對比一整排隨 strike 而異的 IV）。
- **對本產品的額外問題**：這個問題定義本身「退化掉了 strike」，而
  本產品買的正是特定 strike 的 vertical spread——退化掉 strike 等於
  退化掉整個問題（同上）。

### 2.8 Synthetic Parity（Call Spread vs Put Spread box relation）——**合法 Q1 但幾乎全是雜訊，唯一產品化價值是資料完整性紅旗**

- **它量什麼**：`D + C = W·DF`（box relation，put-call parity 推論），
  持續偏離代表兩條路徑報價不一致。
- **Q_ref**：是——參照系是無套利恆等式（模型無關），不是價格自己的
  改寫或自身歷史。
- **Q_size 判定＝否**：真實 Cboe 全鏈（1,978 組配對）實測，個別配對
  `|gap|` 中位數只有四腿半價差成本的 **0.22 倍**，88% 埋在自身交易
  成本內；系統性偏離的主因是美式選擇權的貼現／提前履約結構（r=0 時
  gap 中位數精確歸零），不是報價錯位（`docs/research/
  spread-synthetic-parity-check.md` §4.2–4.3）。
- **唯一站得住的產品化殘餘**：`net_worst > width`（最差成交成本已
  超過最大 payoff，穩賠）——這是資料健全性紅旗，不是「貴」的判斷，
  且零額外資料需求（同上 §4.5／§7）。

### 2.9 Fixed-Coordinate 結構「Price」Percentile（每天 re-strike 到固定 tenor/delta，取結構成本本身的歷史位置）——**已否決，被 rate/carry 汙染**

- **它量什麼**：跟 Ĝ 用同一組座標，但合成的是 BS 價格而不是 vol 差
  （`docs/research/spread-price-percentile-vs-vol-space.md` §2 的
  P1）。
- **Q_ref**：技術上是（相對自身「重定價」歷史），但本輪與該文件都把
  它歸進「歷史 percentile 家族」，本質上跟 raw gap／Ĝ 同類——參照系
  仍是自己過去的樣子，只是換算單位是錢。
- **Q_size 判定＝否，且是本文所有候選裡汙染最大的**：利率動 2 個
  百分點（一次尋常的 Fed 週期）使這個 LEAPS 結構的理論價變動
  **+26%**（該文件 §4.2）；本輪重算同一份 fixture 的相同 2pp 位移得
  **+29.8%（q=0）／+34.5%（q=4.5%）**——兩次獨立計算量級一致
  （見 §4.2）。這正是本文要否決的 VORD 用「凍結 r/q/S/T」解決的
  問題——P1 沒有凍結任何東西。

---

## §3. 資料現況的硬約束

### 3.1 候選幾何：本產品的 vertical spread 是寬、非相鄰履約價，且結構上偏向裸買腿

- `generate_spread_pairs()` 對同一到期日全部合格履約價做 `combinations
  (group, 2)` 窮舉，**沒有相鄰性限制、沒有寬度上限**
  （`option_chaser/filters.py:280-302`）。
- 排名公式 `spread_baseline_return = (baseline_value − net_worst) /
  net_worst`（`option_chaser/ranking.py:184-188`，本輪讀取 2026-09-09
  當前程式碼確認）——劇本成立時 `baseline_value` 即滿額值，此式等價
  `width/net_worst − 1`，由高到低排序等於**照 `net_worst/width`（即
  §2.6 的 D/W）由低到高排**，也就是系統性偏好「用最少錢買最大上限」
  的寬、低成本結構。
- 本輪用真實 TLT LEAPS fixture（`tests/fixtures/
  tlt_leaps_real_quotes_2026-07-17.json`，K90/K130）驗證：`W=40`
  （佔現價 47.3%）時，net vega ÷ 買腿 vega 在 q=0 為 **40.4%**、
  q=0.045 為 **62.9%**（本輪重算，見 §4.2 的重現腳本）——不論哪個
  q 假設，買腿的 level 曝險都占了package 波動率風險的顯著多數，遠非
  業界預設的「vertical＝窄價差、純 skew 玩法」（相鄰履約價時 net
  vega 只值買腿的個位數到十幾個百分比）。
- **產品現況：100% 的 vertical spread 都是 debit 結構**——Initial V2
  只出貨 `bull-call-spread`／`bear-put-spread` 兩個 debit subtype，
  credit vertical（bull-put／bear-call）與 iron-fly 因「return
  semantics 未 canonical」而 deferred（CLAUDE.md「Initial V2」§T15／
  「#213 Correction」段）。本文的結論範圍因此覆蓋今天**全部**可交易
  的 vertical spread candidate，不是子集。

### 3.2 LEAPS tenor 與「同合約歷史」的可得性算術

- 本產品核心情境的 tenor 達 DTE 882（29 個月），真實 fixture 佐證
  （`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`）。
- Listed equity/ETF option 的**法規上限是 39 個月**【二手轉述，多方
  查證一致但官方頁面本輪不可達】。同一張合約要有一年的歷史，需要它
  在「一年前」就已經以 `D+T` 的 tenor 掛牌——本產品 D=882 天時需要
  `L ≥ 41 個月 > 39 個月上限`，**在規則層級不可能**，換哪一家 vendor、
  付多少錢都一樣（`historical-rich-cheap-canonical-methodology.md`
  §9.4）。
- 這條限制**只殺死「同一張具體合約」的歷史**（Q3：這個 edge 相對過去
  的 edge），**不殺死** fixed-(tenor,delta) 重錨定序列（B 家族，本產品
  現行 Historical IV 架構已採用）——後者只需要「某一天的鏈上有 tenor
  ≥ D 的合約可以 bracket」，與歷史窗長度 T 無關，可行但貼著掛牌天花板
  （同上）。

### 3.3 兩條完全不同的「歷史」資源，且第一條恰好就是被否決掉的方法

這是本文的一個關鍵梳理——委託提到的兩種持久化資料，字面上都叫「歷史」，
但支援的方法完全不同：

**(a) 產品自己的 narrow history**（`scenario_id, analyzed_at,
candidate_key, cost`，永久保存，`api_app/storage/__init__.py:290-305`
的 `NarrowHistoryEntry`——PK 是前三欄，值只有一個 `cost` 浮點數）：

> **這正是 §2.9 已經被否決的 P1（fixed-structure price percentile）
> 的資料形狀**——只存最終成交口徑的成本，沒有分解出 IV／level／skew，
> 因此凡是需要「拆開 level 與 skew」的方法（Ĝ、VORD、SAS）都用不上
> 這條資料；能用它做的只有 §2.9 已經證明會被 rate/carry 汙染
> （2pp rate move → +26%~+34.5%）的那種 raw cost percentile。**這條
> 資料唯一支援的方法恰好是本文已經否決的那一個。**

**(b) L0 原始鏈快照**（`snapshots` 表，永久保存，自 V2／2026-08-04起
即已建立）**加上**本輪確認已存在的 point-in-time 利率／股利函式
（`option_chaser/ratecurve.py:215-223` 的 `curve_asof()`、
`option_chaser/dividends.py:167-175` 的 `compute_q_asof()`，皆為
HIVR-01／HIVR-02 已出貨並經 578 筆真實觀測校準到 STRONG_PASS 的
既有機制）：

> 這是一條**尚未接上任何估值候選、但技術上已經齊備**的路徑——對任何
> 一天曾經被使用者刷新過（因而留有 L0 快照）的 symbol，理論上可以
> 用 `implied_vol()`＋`curve_asof()`／`compute_q_asof()` 從**自己的**
> 原始報價逐日反解出 exact-contract IV，完全不需要 vendor 憑證。
> **本輪未發現任何程式碼把這條路徑接進 `ivreconstruct.py` 或任何
> percentile 計算**——它是 Scaling Foundation（SCALE-01/03，
> 2026-09-06 完工）留下的副產品，時間上晚於全部既有 IV 相對價值研究
> （皆完成於 2026-08）。這條路徑能解決「資料從哪來」，**不能解決**
> 本文核心裁決依賴的「即使有資料，方法本身是否構成估值」這個問題
> ——見 §5 的「若要翻案」。

### 3.4 Vendor 歷史 IV：非預設，但已驗證可用（修正既有紀錄的一處過期狀態）

- `GET /api/scenarios/{id}/iv-history*` 端點在**出廠設定**下一律 403
  （「Historical IV 未啟用——請在設定頁選擇自訂資料源並通過測試連線」，
  `api_app/main.py:1737-1740`），閘門判準是使用者是否在 Settings 選了
  自訂資料源且驗證通過（`api_app/main.py:1965-1972` 的
  `_historical_iv_enabled()`：`mode != MODE_CUSTOM` 或無 credential
  皆回 `False`）——**這件事對本文全部方法一視同仁**：不管方法本身
  是否構成估值，沒有使用者主動設定 Market Data App token，連
  Historical IV 卡片本身都不會出現。
- **但一旦使用者設定，資料確實拿得到，且已被真實驗證過**——GitHub
  issue #152（HIVT-01）在 2026-08-16 用真實 GitHub Actions probe 對
  真實合約 `TLT281215C00094000` 打通單合約歷史端點（HTTP 203、
  `s="ok"`，一次呼叫回 34 筆觀測），且 HIVR-01 至 HIVR-11（issues
  #160–170）已把「用自己的模型從 raw quote 反解 IV、而非照抄
  vendor 給的 IV」整條 pipeline 出貨並經 578 筆真實觀測校準到
  `STRONG_PASS`（`docs/research/
  historical-iv-reconstruction-corrected-calibration-results.md`）。
  **這修正了 CLAUDE.md 部分較舊段落仍記載「#111 credential-blocked」
  的印象**——那張 GitHub issue 因為原始驗收範圍（一個從未真正出貨的
  「Historical IV Position」模組）與後來實際出貨的東西不同，行政上
  尚未關閉，但**功能本身已經在跑**（`option_chaser/ivreconstruct.py`
  ／`option_chaser/data/marketdata.py::fetch_contract_history()`／
  `option_chaser/ivpipeline.py` 皆為現行、被 `main.py` 呼叫的
  production 程式碼，非死碼）。
- **這件事讓本文的裁決更有力，不是更弱**：既然「拿不到資料」這個
  藉口在 vendor 端也已經不成立（使用者只要設定一次 token），本文的
  否決理由就更純粹地落在**方法本身的數學／語意**上，不是「巧婦難為
  無米之炊」。即使 vendor 資料唾手可得，也沒有任何一家 vendor 賣過
  「vertical spread package 公平值」這種現成產品（`docs/research/
  spread-price-percentile-vs-vol-space.md` §3.4：17 家 vendor 名單裡
  沒有一家提供 constant-structure spread price 序列端點；
  §3.4「唯一接近的是 ORATS Backtest API，屬回測引擎非指標序列」）——
  這件事本身要嘛做自己的 fair-value 模型（SAS／VORD），要嘛承認做
  不到，vendor 選型解決不了它。

### 3.5 哪些方法死在可得性、哪些死在語意——清楚分開

| 方法 | 死因 | 有錢／有 vendor 授權能救嗎 |
|---|---|---|
| 同一張具體合約的 fair-value 殘差歷史（A 家族字面形式） | **可得性**——39 個月法規上限 vs 需要 41 個月（§3.2） | **不能**，這是規則層級的算術，換 vendor 無效 |
| SAS 全套自建（含歷史報酬分佈＋entropy 最小化） | **語意**——可信部分太小、夠大部分不可信（§2.4） | 不能，多買資料不會讓 GS 自己否決的 level 成分變可信 |
| Surface residual | **語意**（回答另一題）＋部分**訊噪比** | 不完全能——即使資料無限多，它答的仍是 cross-sectional 問題 |
| Debit/Width | **定義上不是估值** | 不能，這不是資料問題 |
| Box parity | **訊噪比**（美式提前履約結構主導） | 不能，貼現／提前履約的結構性成分不會因為多筆觀測而消失 |
| Fixed-structure price percentile（P1） | **語意汙染**（rate/carry） | 不能，汙染是模型結構造成的，不是樣本不夠 |
| Raw gap／Ĝ percentile | **語意**（讀反方向、對主因子失明） | 不能，多資料只會讓錯誤的讀數更穩定 |
| VORD | **分類錯誤**（本質仍是 Q2，非 Q1） | 不能救成 Q1；但**可得性已經不擋它**——這是本文唯一「有錢有 vendor 授權就能做」的候選，只是做出來仍是描述性指標 |

---

## §4. 分解問題：一個 wide debit vertical 的價格由五個因子驅動，任何誠實的估值方法都要講清楚控制了哪幾個

框架：(a) vol level (b) skew 形狀 (c) rate/carry (d) spot/moneyness
飄移 (e) 時間衰減。

### 4.1 逐候選對照表

| 方法 | (a) level | (b) skew | (c) rate/carry | (d) spot | (e) 時間 |
|---|---|---|---|---|---|
| Raw gap percentile | **失明**（Δ=0） | 混雜於 level（未 normalize） | N/A（不涉及重定價） | 未控制（漂移） | **未控制**（機械漂移 +87%／882→252d） |
| Ĝ percentile | **符號常錯**（÷ATM 無法修正） | 部分隔離但仍混 level | N/A | 未控制 | **未控制**（÷ATM 不移除 roll-down） |
| 單腿 IV-Rank | 直接量（單腿定義下合法） | N/A（單腿無 skew 概念） | N/A | 靠固定 delta 座標凍結 | 靠固定 tenor 凍結 |
| VORD | **正確隔離**（唯一目的） | 正確隔離（逐日重定價自然含入） | **凍結在今天**（結構性消除） | **凍結在今天**（結構性消除，但歷史那天的 σ 本身帶著當時的 moneyness 印記，殘留約 21%，見下） | **凍結在今天**（結構性消除） |
| SAS／殘差 | 混在 level 裡但被作者歸零 | 隔離出來，唯一可信但太小 | N/A（今日橫斷面） | N/A | N/A（今日橫斷面，無時間軸） |
| Surface residual | N/A（同日鄰居，level 對全鏈共同，相減抵銷） | 部分反映在殘差裡 | N/A | N/A（同日） | N/A（無時間軸） |
| D/W 隱含機率 | 內建（讀市場自己怎麼定價，不拆解） | 內建 | **未貼現需自己 ÷DF**（quotable 缺口） | 內建（就是市場現在的看法） | 內建（用當下 T） |
| Box parity | 內建（雙邊都吃到同樣的 level） | 內建 | **主導殘留成分**（美式提前履約＋貼現） | 內建 | 內建 |
| Fixed-structure price percentile (P1) | 混在價格裡 | 混在價格裡 | **完全未控制**（+26~34.5%／2pp，本節重算） | 部分靠重錨定緩解 | 靠固定 tenor 凍結 |

### 4.2 本輪引擎重算（可重現，2026-09-09 對當前程式碼）

輸入：`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（S=84.52、
today=2026-07-17、expiry=2028-12-15、T=882/365=2.416438 年、
r=4%，買 K90 iv=12%、賣 K130 iv=18%、W=40）。重現：

```python
# PYTHONPATH=. .venv/bin/python
from datetime import date
from option_chaser.valuation import american_price, days_between, DAYS_PER_YEAR

S, r0 = 84.52, 0.04
T = days_between(date(2026,7,17), date(2028,12,15)) / DAYS_PER_YEAR  # 2.416438

def debit(S, T, r, q, iv_b, iv_s):
    return (american_price("call", S, 90.0, T, r, q, iv_b)
          - american_price("call", S, 130.0, T, r, q, iv_s))
```

（呼叫的正是 production 定價函式 `american_price()`，
`option_chaser/valuation.py:650-681`——BS93 美式近似，q≤0 時對 call
逐位元退化成 Merton 歐式解，見同檔 §656–664 docstring。）

**實驗 A：純 vol-level 位移（兩腿各加同一個 vol 點數，gap 恆定）**

| shift | buy_iv | sell_iv | raw gap | debit（q=0） | Δ% | debit（q=4.5%） | Δ% |
|---|---|---|---|---|---|---|---|
| baseline | 12.0% | 18.0% | 6.00 pts | 6.1041 | — | 2.8225 | — |
| +3.0pt | 15.0% | 21.0% | 6.00 pts | 6.6223 | **+8.5%** | 3.6205 | **+28.3%** |
| +6.0pt | 18.0% | 24.0% | 6.00 pts | 6.9837 | **+14.4%** | 4.2627 | **+51.0%** |
| +10.0pt | 22.0% | 28.0% | 6.00 pts | 7.2854 | **+19.4%** | 4.9085 | **+73.9%** |
| −4.0pt | 8.0% | 14.0% | 6.00 pts | 5.0918 | **−16.6%** | 1.5321 | **−45.7%** |

**raw gap 全程 Δ=0.0000（恰好）**——這不是舍入誤差，是這個統計量的
定義（相減時 level 項本應完全抵銷）。用平均值當 ATM proxy 算出的
`Ĝ = gap/atm`：

| shift | Ĝ | Ĝ 變動 | debit（q=0）變動 |
|---|---|---|---|
| baseline | 0.4000 | — | — |
| +3.0pt | 0.3333 | **−16.7%** | +8.5% |
| +6.0pt | 0.2857 | **−28.6%** | +14.4% |
| +10.0pt | 0.2400 | **−40.0%** | +19.4% |
| −4.0pt | 0.5455 | **+36.4%** | −16.6% |

**Ĝ 與 debit 的變動方向完全相反**——package 實際變貴時 Ĝ 說「更
便宜」，這是本文引用最重的一條實測，因為它獨立於 2026-08-26 那份
研究、用不同的 shift 幅度、在當前程式碼上重跑，得到同一個質性結論
（那份研究用單一 +10pt 位移得 −44.9%／debit +59.9%；本輪多點掃描
確認這是全程單調反向，不是單一取樣點的巧合）。

**實驗 B：純 skew 形狀變動（拉開／收窄 gap，平均水位固定）**

| gap 倍數 | buy_iv | sell_iv | gap | debit（q=0） | Δ% |
|---|---|---|---|---|---|
| baseline | 12.00% | 18.00% | 6.00 pts | 6.1041 | — |
| ×1.5 | 10.50% | 19.50% | 9.00 pts | 4.8717 | **−20.2%** |
| ×2.0 | 9.00% | 21.00% | 12.00 pts | 3.5974 | **−41.1%** |
| ×0.5 | 13.50% | 16.50% | 3.00 pts | 7.2860 | **+19.4%** |

拉開 gap（sell 相對更貴）package 反而**變便宜**——因為這個結構近乎
裸買一張 call（見下），賣腿降價的邊際效果小於買腿降價的邊際效果，
與買賣腿 vega 占比一致。

**Vega 分解（本輪用 `call_greeks()` 重算，`valuation.py:39-64`）**：

| q | 買腿 delta | 買腿 vega/pt | 賣腿 delta | 賣腿 vega/pt | net vega/pt | net÷買腿 |
|---|---|---|---|---|---|---|
| 0.0 | 0.6082 | 0.5048 | 0.1461 | 0.3010 | 0.2038 | **40.4%** |
| 0.045 | 0.3399 | 0.4483 | 0.0670 | 0.1662 | 0.2821 | **62.9%** |

W=40（佔現價 47.3%）。**⚠ 誠實揭露一處與既有文件的落差**：
`docs/research/strategy-valuation-metric-percentile.md` §3.2 的表格
對「W=40」列出 net÷買腿 vega ＝ **92.3%**——本輪用同一份 fixture、同
一對履約價（K90/K130）、q=0 與 q=0.045 兩種假設**都重算不出這個
數字**（本輪得 40.4%／62.9%）；另用該研究另一節（§6.1，取自
`historical-rich-cheap-canonical-methodology.md`）明確給出的 K85/K130
組合重算，逐位元核對得 q=0 net=0.1418（÷買腿=32.0%）、q=0.045
net=0.3039（÷買腿=64.6%）——這組數字與被引用的來源文件完全吻合，
證明本輪引擎呼叫方式正確；但「92.3%」這個具體數字本輪無法用 fixture
裡任何一組真實報價重現，懷疑該表用的是另一種未載明參數的合成
sweep（例如買腿固定貼著 ATM、單一 flat sigma），而非 fixture 的
真實市場 IV。**結論不受影響**——不論是 40.4%、62.9% 還是 92.3%，
質性結論相同：這個產品實際產生的寬 vertical，買腿的 level 曝險占了
package vega 的顯著多數（三分之一到三分之二以上，甚至可能更高），
業界「vertical＝窄價差、純 skew 玩法」的預設在這裡不成立，但**本文
不引用「92.3%」這個無法自行驗證的數字**，只引用本輪自己算出、且
與另一份文件交叉核對一致的 40.4%／62.9%／32.0%／64.6% 四個數字。

**實驗 C：VORD 示範（用今天的 S/T/r=4%/q=4.5% 重定價「歷史」那天的
σ）**

| 「歷史」情境 | σ_buy | σ_sell | VORD = D/W |
|---|---|---|---|
| 今天（12/18） | 12% | 18% | 7.056% |
| level +6pt | 18% | 24% | 10.657% |
| level −4pt | 8% | 14% | 3.830% |
| skew ×1.5 | 10.5% | 19.5% | 4.655% |

VORD 忠實追蹤 debit 的方向與大致量級（level+6pt 使 debit 從 2.8225
漲到 4.2627，VORD 從 7.056%漲到10.657%，兩者變動比例相同——**這是
恆等式，不是巧合**：VORD 就是同一個定價函式在不同 σ 輸入下的值，
holding S/T/r/q 不變）。**這正是本文要強調的分類點**：VORD「忠實」
這件事本身**不是**在證明它是估值——它只是證明「同一個函式在不同
輸入下給出不同輸出」，這對任何函式都成立。VORD 真正的貢獻是**選對
了要凍結哪些變數**（S/T/r/q 凍結在今天），讓「歷史序列」乾淨地只
剩 σ 在變動——但序列本身依然是「這個 package 的 vol 定價分量，相對
它自己過去的樣子」，參照系仍是自己。

**實驗 D：Rate/carry 敏感度（2pp 位移，重算獨立驗證既有文件）**

| q | r=3% debit | r=5% debit | 變動% |
|---|---|---|---|
| 0.0 | 5.3301 | 6.9200 | **+29.8%** |
| 0.045 | 2.4311 | 3.2696 | **+34.5%** |

與 `spread-price-percentile-vs-vol-space.md` §4.2 的 +26.0%（q=0）
量級一致（該文件用略有不同的利率對，3%→5% vs 本輪同一區間，數字
接近但非逐位元相同，屬合理的實作/取值差異，不影響結論方向）。**這
就是 P1（fixed-structure price percentile）被否決、VORD 必須凍結
r/q 的直接理由**：不凍結的話，一次尋常的 Fed 週期就能讓「歷史
percentile」從中位數推到高位，跟 vol 結構毫無關係。

**Discount factor**：`DF(r=4%, T=2.416438) = 0.90787`。

### 4.3 分解問題的結論

沒有任何一個候選方法同時控制住全部五個因子**且**還剩下一個外於
價格本身的參照值。VORD 是唯一同時控制住 (a)(c)(d)(e) 的候選，付出
的代價是它連估值資格都放棄了（純粹的 Q2 描述性統計）；SAS 是唯一
沒有放棄估值資格的候選，付出的代價是能用的那一半量級太小。

---

## §5. 若要在未來讓一個 package 估值方法站得住腳，必須先讓下列哪些事變成真

以下按「解決它會不會改變裁決」排序：

1. **找到一個對 spread 而非單腿成立的「非單調安全」fair-value 模型**
   ——SAS 自己劃的紅線（腳注 3）是本文否決任何 package 單一 SAS 數字
   的根本原因。若未來出現一個逐腿定義、且合成方式不要求「價值對 σ
   單調」的 fair-value 框架（例如某種對 payoff 分佈整體定價、而非對
   單一 vol 數字定價的方法），SAS 家族的否決可能需要重新評估。**這是
   唯一一項，解決了會真正改變 §0 的裁決方向**（從「無估值」變成
   「有 Q1 候選」），因為它同時滿足 Q_ref＝是且不受單調性紅線限制。
2. **量測到 SAS skew 成分在某個 regime 下訊噪比顯著優於本文引用的
   0.10–0.27×**——本文引用的量級來自單一份真實 TLT LEAPS fixture
   與單一份 YETI 全鏈，不是跨多個標的、多個 vol regime 的系統性
   量測。若在高波動 regime（例如 vol spike 期間）skew 成分放大到
   接近或超過半價差，SAS_ATM 可能在那些窗口內重新具備可用性——但
   這只解決 Q_size，不解決「level 成分仍是 VRP」，裁決本身不會翻案，
   只是多一個「有條件可用」的旁註。
3. **接上 §3.3(b) 已具備的 L0＋point-in-time r/q 路徑，產生一條
   vendor-free 的 exact-contract 歷史 IV 序列**——這解決的是**資料
   來源獨立性**，不解決語意問題。即使做出來，餵進 VORD 或 SAS，
   VORD 仍然只是 Q2、SAS 的三難依舊成立。**這是本文唯一標記「值得
   做但不改變裁決」的一項**——列在這裡是因為它是低成本、已有機械可
   直接落地的基礎建設，未來若第 1 項成立，這條路徑會是實作它的
   資料骨架。
4. **業界出現具名先例，把「重定價後的歷史序列」（VORD 這一類構造）
   正式定性為某種形式的估值，而非單純的歷史位置指標**——本文找不到
   這樣的先例（§2.4 已否決的 SAS 本身走的是完全不同的路徑：轉換
   標的報酬分佈，不是重定價自身歷史）。若未來查到具名先例（例如某
   家機構把類似 VORD 的重定價序列用作「相對合理」的判斷依據，而非
   單純「相對過去」），需要重新評估 VORD 的分類，但即使重新分類為
   「弱估值」，其可信度仍受制於 §3.7（`candidate-iv-relative-value.md`）
   已記載的 ±21% spot 殘餘汙染，不會是乾淨的答案。
5. **需求方明確接受「跨 strategy percentile 只回答『比自己過去貴/
   便宜』這句話，不回答『值不值得』」這個框架本身作為產品答案**
   ——這不是讓某個方法變成估值，而是**改變委託問題本身**：若產品
   決定「rich/cheap」對使用者而言指的就是 Q2（相對自身歷史位置），
   VORD 已經是本文找得到的最好答案（優於現行出貨的 raw gap／Ĝ）。
   這條路徑不需要任何新研究，只需要 Owner Decision，且必須明確標示
   「此為歷史位置指標，非估值」（沿用需求方 2026-08-25 對 percentile
   文案「不得用異常／離群／貴」的既有裁示精神）。

---

## §6. 誠實侷限

1. **#111 的 vendor 資料存在性驗證，本輪未重新實測**——本文對
   HIVT-01／HIVR 系列的「已出貨、已驗證」判斷完全依賴既有 CLAUDE.md
   紀錄與 repo 原始碼結構（`ivreconstruct.py`／`marketdata.py` 確實
   被 `main.py` 呼叫），**未在本輪重新對真實 vendor 端點打一次
   請求**——本沙箱對 `api.marketdata.app` 仍是 CONNECT 403／DNS
   不解析（與既有紀錄一致，未改善）。
2. **§4.2 的 Ĝ 分子分母選擇（ATM proxy = 兩腿平均）是本輪的簡化，
   非 production 實際算法**——`ivhistory.py` 的正式 `atm_iv` 來自
   vendor 曲面在 delta=0.5 的內插值，本輪為了在沒有完整曲面資料下
   做出可重現的示範，改用兩腿 IV 平均值當 ATM 代理。這個簡化不影響
   「Ĝ 對 level 上升方向讀反」這個質性結論（因為只要 ATM 隨 level
   同步上升，`Ĝ=gap/ATM` 在 gap 固定時必然隨 ATM 上升而下降，這是
   代數事實，不是資料依賴的巧合），但 Ĝ 的**精確數值**不能直接
   對應 production 畫面上會顯示的數字。
3. **本文未取得、也未重新驗證任何新的一手外部文獻**——全部引用的
   一手／官方文件證據沿用既有八份研究文件已完成的查證工作（各自
   標注取得管道與限制），本輪只做了「用當前程式碼重新計算數字」
   這一層獨立覆核，未重新聯繫任何交易所／vendor／論文作者。
4. **§3.1 的候選幾何統計（W=40 佔 spot 47.3%）只來自單一份真實
   fixture**——本輪與所有既有研究一樣，沒有 production 真實使用者
   資料可供統計候選寬度的分佈，`net_vega/買腿_vega` 隨 W／IV 組合
   而異（本文示範過 K85/K130 與 K90/K130 兩組給出不同比例），
   「這個產品的典型 vertical 有多寬」目前只有結構性論證（排名公式
   偏好低成本高上限）與單一實例佐證，沒有跨多個真實 candidate 的
   統計分佈。
5. **§5 第 2 項（不同 vol regime 下 SAS skew 訊噪比是否顯著更好）
   本輪未實測**——需要跨越至少一次真實 vol spike 事件的歷史資料，
   本沙箱與既有研究皆不具備。
6. **VORD 與 SAS 之間是否存在第三種尚未被本文或既有八份研究設想到
   的組合方式**——本文窮舉的是既有文獻與既有研究已提出的候選，
   不代表窮盡了數學上所有可能的組合，只能說「目前檢視過的每一種
   都落進三個桶子之一」。
7. **本文的 executive verdict 是對「委託給定的估值定義」的判斷**
   ——若產品或需求方採用一個較寬鬆的估值定義（例如把「相對自身
   歷史的 vol-only 分量位置」也算作某種弱意義下的估值），§5 第 5
   項已指出這是可行的、且已有現成最佳候選（VORD）；本文的否決僅
   針對委託明文給定的嚴格定義（「參照值不能是價格本身的另一種
   說法」）。

---

## §7. 來源與重現步驟

**本輪直接讀取的 repo 原始碼**（皆為 2026-09-09 當前狀態）：
- `option_chaser/valuation.py`——`american_price()`（:650-681）、
  `merton_price()`（:551-567）、`call_greeks()`（:39-64）、
  `calibrate_leg()`（:103-170）、`implied_vol()`（:684-）
- `option_chaser/ivhistory.py`——`normalized_skew()`（:97-107）、
  `field_metrics()`（:499-529）、`iv_at()`（:60-88）
- `option_chaser/ivspread.py`——`align_spread_gap()`（:31-52）、
  `spread_delta_4w_ratio_status()`（:70-97）
- `option_chaser/ivtrend.py`——`historical_percentile()`（:170-185）、
  `_rolling_windows()`（:64-94）
- `option_chaser/ivreconstruct.py`——canonical series 定義（:1-68）
- `option_chaser/ivpipeline.py`——`spread_gap_payload()`（:735-760）、
  `legacy_backfill_status()`（:775-）
- `option_chaser/filters.py`——`generate_spread_pairs()`（:280-302）
- `option_chaser/ranking.py`——`spread_baseline_return()`（:184-188）
- `option_chaser/scenarios.py`——`natural_cost()`／`_vertical_cost()`
  （:146-163）
- `option_chaser/ratecurve.py`——`curve_asof()`（:215-）
- `option_chaser/dividends.py`——`compute_q_asof()`（:167-）
- `option_chaser/store.py`——`visible_candidate_keys()`（:173-）、
  `visible_candidate_costs()`（:208-218）
- `option_chaser/snapshot_replay.py`——`cost_from_snapshot()`（:75-）
- `api_app/storage/__init__.py`——`NarrowHistoryEntry`（:290-）
- `api_app/main.py`——`_iv_history_gate()`（:1720-1745）、
  `_historical_iv_enabled()`（:1965-1972）
- `src/SpreadSummary.tsx`——卡片頭條接線與文案（:1-140）

**本輪引擎重算**（`§4.2` 全部，`.venv/bin/python` + `PYTHONPATH=.`，
輸入為 `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`）：
腳本邏輯已完整節錄於 §4.2 內文，可直接貼回任何具備本 repo `.venv`
的環境重跑；本輪執行腳本本身存於 session scratchpad（非 repo 內
檔案，未 commit，會隨 session 消失，但重跑步驟本身已完整寫入正文，
不依賴腳本檔案存活）。

**既有研究文件**（全部逐一讀過全文或關鍵章節，具體引用位置見正文
各節）：
- `docs/research/strategy-valuation-metric-percentile.md`（2026-08-26，
  VORD 提案來源）
- `docs/research/candidate-iv-relative-value.md`（2026-08-08，四方案
  收斂、Ĝ 定義來源）
- `docs/research/spread-price-percentile-vs-vol-space.md`（2026-08-08，
  P1 否決）
- `docs/research/spread-surface-residual-rv.md`（2026-08-08，surface
  residual 全套實測）
- `docs/research/spread-implied-probability-readout.md`（2026-08-08，
  D/W 恆等式）
- `docs/research/spread-synthetic-parity-check.md`（2026-08-08，box
  parity 實測）
- `docs/research/historical-rich-cheap-canonical-methodology.md`
  （2026-08-16，SAS 一手解剖、A/B/C 家族裁決、可得性算術）
- `docs/research/iv-relative-history-methodology.md`（2026-08-07，
  IV-Rank 家族、單腿 vs spread 不能簡單平均）
- `docs/research/historical-options-iv-data-sources.md`（vendor 名單、
  #111 credential 狀態的歷史記錄）
- `docs/research/historical-iv-reconstruction-corrected-calibration-results.md`
  （reconstruction pipeline 的 STRONG_PASS 校準結果）

**本 repo 專案紀錄**：`CLAUDE.md`——Scaling Foundation（SCALE-01／
SCALE-03／SCALE-09／SCALE-14 段落，L0／narrow history 決策）、
HIVT-01～HIVR-11 施工紀錄段落、Initial V2（credit vertical deferred
決策）、Wayfinder「方向性策略擴充」段落（#111／#114 tracker 過期
狀態的既有記錄）。
