# 同 payoff 等價品比價（synthetic parity check）：call spread vs put spread 的套利意義「貴」，在延遲報價上可不可測

研究日期：2026-08-08（R4／issue #99）。相關前作：
`docs/research/cboe-field-semantics.md`（欄位語意與真實全鏈樣本出處）、
`docs/research/candidate-iv-relative-value.md`（「相對歷史」的貴）、
`docs/research/opc-heatmap-comparison.md`（估值口徑）。本文只處理
「box relation／synthetic 比價」這一條路徑：bull call spread（debit D）
與同履約價 bull put spread（credit C）到期 payoff 相同，理論上
D + C ＝ 貼現後的 width；若 call 側持續比 put 側貴，call spread 就是
**套利意義上**的「貴」。問題是：這個訊號在零售延遲報價＋最差成交口徑下，
是可測的訊號還是雜訊。

## 資料品質聲明

證據分三級（沿用本 repo research 慣例）：

- **實測實證（一手，本地可重跑）**：§4 的全部統計，由真實 Cboe 全鏈
  payload 原檔（YETI，758 筆，2023-08-11，來源見
  `cboe-field-semantics.md` §7，本沙箱實測可下載）以 stdlib Python
  計算，腳本全文節錄於 §4.1，所有數字可重現。
- **原始碼／repo 實證**：本 repo 的 adapter 與過濾器
  （`option_chaser/data/cboe.py`、`option_chaser/filters.py`）、
  快照結構（put 合約已在快照內）。
- **搜尋索引轉述**：§2、§3 的 desk 先例與美式選擇權文獻。本沙箱
  WebFetch 對絕大多數網域回 403，這些內容經搜尋引擎索引摘錄取得，
  **未逐字核對原文**，引用清單見 §8。

一項與任務描述的出入需先聲明：任務文字把 put spread 最差成交 credit
寫成「K1 put bid − K2 put ask」，該式對 K1<K2 恆為負，應為筆誤。
bull put spread（賣 K2 put、買 K1 put）的最差成交 credit 是
**C_worst ＝ P_bid(K2) − P_ask(K1)**（賣腿 bid、買腿 ask，與附錄
A14.2「買腿 Ask − 賣腿 Bid」同一保守口徑），本文全程採此定義。

## 目錄

1. 結論摘要
2. Desk 先例：conversion／reversal、box、synthetic 比價
3. 美式修正：American box 不是無風險，parity 只剩不等式
4. 實算：真實 Cboe 全鏈上的 parity gap 分布（本票核心）
5. 產品語意：「這組 call spread 貴」還是「該用 put spread 進場」
6. 誠實侷限：三種「貴」的關係
7. G1 裁示建議
8. 引用清單

---

## 1. 結論摘要

**(A) 對個別配對，parity gap 是雜訊，不是可交易訊號。**真實 Cboe
全鏈上 1,978 組可組四腿的 K1<K2 配對：mid 口徑 parity 殘差
|gap|/四腿半價差成本的中位數只有 **0.22**（gap 約為交易成本的 1/5），
只有 12% 的配對殘差超過自身四腿半價差；帶外幅度超過半價差的更只有
**0.4%**。延遲報價的雙邊 bid-ask 把 gap 淹沒——這是實測，不是推論。

**(B) 「call 側系統性偏貴」的表象，實測是美式貼現效果，不是錯價。**
以歐式基準 W·e^{−rT} 衡量，gap 中位數 +1.2% width、75% 配對為正——
看起來 call 側貴。但利率敏感度戳破它：r 取 0 時 gap 中位數**精確歸零**
（box_mid/width 中位數 = 1.0000）。即市場把美式 box 定價在**未貼現**
width 附近——這正是教科書上美式 box 的合理位置（∈ [W·DF, W]，§3），
深度 ITM 美式腿以內在值報價、提前履約權利吃掉貼現。**用歐式 parity
去量美式 ETF options，量到的「貴」大部分是模型口徑差，不是報價錯位。**

**(C) 唯一在最差成交口徑下仍站得住的系統性訊號：深度 ITM 縱向價差
該從 OTM 側進場。**決策量 Δ ＝ D_worst − (W·DF − C_worst)（>0 表示
最差口徑下走 put 側仍較便宜）：兩腿皆 ITM 的配對 89% 為正（中位數
+3.3% width）；但本 app 典型的 ATM/OTM bull call spread（K1≥spot）
只有 44.5% 為正（中位數 −1.2% width）——**在產品實際候選區，put 側
沒有系統性優勢**。ITM 區的優勢來自流動性住在 OTM 側（深度 ITM call
報價寬、OTM put 報價窄），是已知市場結構，且部分是對美式提前指派
風險的補償，不是免費的錢。

**(D) 可產品化的最小殘餘價值是資料健全性紅旗，不是比價排名。**
樣本中 **3.8%** 的配對 D_worst > width——最差口徑買進成本超過最大
payoff，穩賠，這種候選要嘛是報價陳舊要嘛不可成交，一條
`D_worst > K2−K1` 的檢查零額外資料、零利率假設就能抓出來（且引擎
現有 worst 口徑已算好 D_worst）。至於「put 側合成價」對照顯示，
零額外資料也做得到（put 已在快照裡），但依 (A)(B)(C)，它能說的話
很有限，見 §7。

---

## 2. Desk 先例：conversion／reversal、box、synthetic 比價

（本節全部為搜尋索引轉述，未逐字核對原文。）

### 2.1 術語與標準做法

- **Conversion / reversal**：put-call parity 的單履約價套利。
  conversion ＝ 持有現股＋買 put＋賣同履約價 call；reversal（reverse
  conversion）＝ 放空現股＋買 call＋賣 put。當 C − P 偏離
  S − PV(K)（含股利調整）時鎖定無風險價差。這是做市商的日常庫存
  管理工具而非零售策略——做市商保證金約為零售的 1/5–1/10，零售做
  這件事在資金效率上先天不利（tradealgo.com、optiontradingpedia.com、
  optionseducation.org，轉述）。已知風險三件套：**pin risk**（到期
  日收在履約價附近，不知道會不會被指派，週末留下裸股票部位）、
  **dividend risk**（reversal 的空頭現股要付股利）、**early
  assignment**（短腿被提前指派拆散對沖）。
- **Box spread**：兩個履約價的四腿組合（bull call spread ＋ bear put
  spread），到期恆值 width，等同零息債。歐式 box 的價格就是
  width 的貼現值，反推出**隱含融資利率**——desk 用它借貸資金，
  術語即「box financing」。
- **Synthetic 比價**：任何部位都有 synthetic 等價品（synthetic long
  ＝ 買 call 賣 put 等），desk 掛單前比較實體與合成路徑取便宜側——
  本票研究的 call spread vs put spread 比價就是這件事在縱向價差上的
  版本。

### 2.2 SPX box 當融資工具與 boxtrades.com 現象

SPX 選擇權是**歐式、現金結算**，box 在其上真正接近無風險零息債：

- Cboe 官方內容把長天期 SPX box 描述成「借款利率僅比同天期國庫券
  高 30–50 bps」的融資工具（cboe.com insights，轉述）。
- 社群站 **boxtrades.com** 專門彙整實際成交的 SPX box，把每筆成交
  換算成隱含利率曲線，Bogleheads 有長期討論串把它當低成本槓桿的
  標準做法（boxtrades.com、bogleheads.org，轉述）。
- 學術脈絡：box 隱含利率高於國庫券殖利率的差，被解讀為國庫券的
  convenience yield（約 10–30 bps，隨市況變動；搜尋摘錄轉述）。

**對本票的含義**：box 比價在歐式指數選擇權上是成熟、可交易的市場
（成交價緊到能當利率曲線用）；但這個乾淨世界**不能直接搬到美式
ETF options**——見 §3。

---

## 3. 美式修正：American box 不是無風險，parity 只剩不等式

（教科書結果＋搜尋索引轉述。）

### 3.1 等式退化為區間

歐式：C − P ＝ S − K·e^{−rT}（無股利），故歐式 box ＝ W·e^{−rT}。
美式無股利只剩不等式：

```
S − K ≤ C_A − P_A ≤ S − K·e^{−rT}
```

（有股利時下界再減 PV(D)。）對應到 box：**美式 box 的無套利區間是
[W·e^{−rT}, W]**——上界是未貼現 width，因為短腿隨時可能被指派、
長腿隨時可以履約，貼現的「時間」不再有保證。§4 實測顯示市場就把
美式 box 定在這個區間的上緣（中位數恰為 W）。

### 3.2 哪裡偏離最大

- **深度 ITM put**：美式 put 提前履約在高利率下有正價值（拿回 K 先
  收利息），深度 ITM 美式 put 以內在值 K−S 報價、不貼現——put 側
  因此比歐式值「貴」，正是把 D＋C 從 W·DF 推向 W 的主力。利率越高、
  天期越長，偏離越大（本樣本 2023-08，短率 5.3%，LEAPS 的
  W−W·DF 達 7% width）。
- **除息前 call**：有配息標的（TLT 每月配息）在除息日前，深度 ITM
  call 有提前履約誘因，call 側同樣脫離歐式值。Cboe 官方教育內容
  明文警告短 call 在除息前被指派、被迫付股利的風險（cboe.com
  insights「Don't Get Stuck Paying the Dividend」，轉述）。
- **pin risk**：到期日 spot 貼著短腿履約價，指派與否不確定。

### 3.3 短腿提前指派：American box「無風險」的破口

賣出 put spread（或做空 box）的短腿是美式的，深度 ITM 時隨時可能
被提前指派：指派瞬間 spread 變成「長腿選擇權＋現股部位」，需要的
保證金／資金可能遠超帳戶承受（tastytrade、E*TRADE 教育頁，轉述；
optionalpha／optionsamurai 對 short box 的風險說明同旨）。廣為流傳
的 2019 年 Robinhood「1R0NYMAN」事件即是在美式選擇權上做 box 被
提前指派拆散而爆倉的案例（**記憶轉述，本次未查證細節**）。

**含義**：§4 量到的「ITM 區走 put 側較便宜」有一部分正是市場對
這個指派風險收的補償。把它當免費套利呈現給零售使用者是誤導。

---

## 4. 實算：真實 Cboe 全鏈上的 parity gap 分布（本票核心）

### 4.1 樣本、口徑與腳本

**樣本**：repo 內 FB3-01 的 Cboe fixture（`tests/test_data_cboe.py`）
只有 3 筆合約、且全是同到期日單邊資料，無法組四腿；故採
`cboe-field-semantics.md` §7 記載的 758 筆真實 Cboe 全鏈原檔
（YETI，2023-08-11 16:27:37，spot 44.97，13 個到期日 DTE 0–525，
該文件已做賣權買權平價自洽性檢核，誤差 0.02%）。本沙箱下載實測
200 OK。侷限：單一標的、單一快照、消費股非 TLT，見 §6。

**口徑**（K1 < K2，只取四腿皆雙邊報價 bid>0 且 ask>0 者，剔除
DTE≤0 的到期日；共 **1,978 組**配對，全枚舉非抽樣）：

- `D_worst = C_ask(K1) − C_bid(K2)`：買 bull call spread 最差成交成本
  （引擎 net_worst 同口徑，附錄 A14.2）
- `C_worst = P_bid(K2) − P_ask(K1)`：賣 bull put spread 最差成交 credit
- `D_mid`／`C_mid`：同組合 mid 口徑
- `W·DF = (K2−K1)·e^{−rT}`，基準 r=5.3%（樣本日 2023-08 的短率；
  敏感度另跑 4% 與 0%）
- `gap_mid = D_mid + C_mid − W·DF`：純報價錯位（box relation 殘差）
- `Δ = D_worst − (W·DF − C_worst) = D_worst + C_worst − W·DF`：
  決策量，>0 ⇒ 最差成交口徑下走 put 側進場仍較便宜
- `half_cost = (D_worst−D_mid) + (C_mid−C_worst)`：四腿半價差合計
  （雜訊基準）；`four_leg = Σ(ask−bid)` 四腿全寬

腳本（stdlib，完整檔在 scratchpad `parity_check.py`／
`parity_check2.py`，核心節錄）：

```python
for k2 in strikes[i+1:]:
    c1b,c1a = chain[(exp,'call',k1)]; c2b,c2a = chain[(exp,'call',k2)]
    p1b,p1a = chain[(exp,'put', k1)]; p2b,p2a = chain[(exp,'put', k2)]
    w = k2 - k1; df = math.exp(-r*T)
    d_worst = c1a - c2b                      # 買腿 ask − 賣腿 bid
    c_worst = p2b - p1a                      # 賣腿 bid − 買腿 ask
    d_mid = (c1a+c1b)/2 - (c2a+c2b)/2
    c_mid = (p2a+p2b)/2 - (p1a+p1b)/2
    gap_mid     = d_mid + c_mid - w*df       # box relation 殘差
    delta_worst = d_worst + c_worst - w*df   # 決策量
    half_cost   = (d_worst-d_mid) + (c_mid-c_worst)
```

### 4.2 gap 分布 vs 雙邊 bid-ask 寬度（訊噪判定）

關鍵輸出（r=5.3%）：

```
全部 (n=1978)
  gap_mid $      : med +0.063  Q1 +0.001  Q3 +0.322
  gap_mid %width : med +1.20%  Q1 +0.02%  Q3 +3.11%
  |gap_mid|/half_cost: med 0.22  Q3 0.54  p90 1.14  >1 佔 12%
  four_leg $     : med 1.050   half_cost $ med 0.525
  delta_worst $  : med +0.065  >0（put 側仍勝）佔 70.5%
```

- gap 中位數 +$0.063（+1.2% width）——方向上「call 側偏貴」
  （75% 配對 gap>0）。
- 但同一批配對的四腿半價差成本中位數是 $0.525、四腿全寬 $1.05：
  **|gap| 中位數只有半價差成本的 0.22 倍**，88% 的配對 gap 埋在
  自身交易成本之內。對「這一組要不要換邊」的個別決策，gap 是雜訊。

### 4.3 「call 側系統性偏貴」的解剖：利率敏感度與美式 box 帶

```
利率敏感度（全部配對，gap_mid 中位數）
  r=5.3%: +0.0634   r=4.0%: +0.0504   r=0.0%: +0.0000

box_mid/width: med 1.0000  IQR [0.9760, 1.0133]
落在美式無套利帶 [DF, 1] 內: 31.2%；>1: 44.0%；<DF: 24.8%
帶外幅度超過自身四腿半價差者: 8 組（佔全部 0.4%）
```

r=0 時 gap 中位數**精確為 0**、box_mid/width 中位數**精確為 1**：
市場把這條美式鏈的 box 定在未貼現 width。也就是說，用歐式基準
W·e^{−rT} 量出來的「call 側貴 +1.2%」，其中位數成分**完全等於
貼現項**——是 §3.1 不等式上緣的預期行為，不是報價錯位。逐配對看，
雖有 68.8% 落在理論帶 [DF, 1] 之外，但帶外幅度超過自身四腿半價差
的只有 8 組（0.4%）——帶外幾乎全是報價量化雜訊。

順帶的反向驗證：若硬把長天期 box 當融資工具讀，隱含利率
DTE 91–365 中位數 3.9%（IQR 2.3–5.9%）、DTE>365 中位數 3.4%
（IQR 2.1–4.3%），對照同期短率 5.3%——IQR 寬達 2–4 個百分點，
**單一標的延遲報價鏈上讀不出可用的利率訊號**（SPX box 成交價
才有那個精度，§2.2）。

### 4.4 最差成交口徑的決策量：優勢只在深度 ITM 區

```
                    n     gap_mid%w   delta_worst>0    delta_worst med %w
OTM(K1>=spot)      623     +2.71%        44.5%             −1.23%
straddle           1001    +1.08%        80.1%             +1.14%
ITM(K2<=spot)      354     +0.03%        89.0%             +3.34%

DTE 1-30   n=696   delta_worst>0: 67.8%
DTE 31-90  n=416   delta_worst>0: 53.1%
DTE 91-365 n=656   delta_worst>0: 76.4%
DTE >365   n=210   delta_worst>0: 95.2%（gap_mid med +3.13%w）
```

- **兩腿皆 ITM**：走 put 側（賣 OTM put spread）最差口徑仍便宜
  中位數 +3.3% width、89% 配對為正。原因是市場結構：深度 ITM call
  報價寬、貼內在值甚至低於內在值（`cboe-field-semantics.md` §1.1(C)
  的同一批合約），OTM put 報價窄。「縱向價差從 OTM 側進場」是
  零售選擇權的已知慣例，資料完全支持。
- **本 app 的典型候選區（K1≥spot 的 OTM bull call spread）**：
  delta_worst>0 只剩 44.5%、中位數 −1.2% width——**put 側沒有系統性
  優勢**，因為這時 call 才是 OTM 流動側，而深度 ITM put（K2 遠高於
  spot 的 put 在此分組不存在……準確說：K1≥spot 時兩支 put 皆 ITM，
  報價寬）換到了 put 側。
- **LEAPS 的 95.2%**：長天期貼現項大（7% width），Δ 的正值主要就是
  貼現項＋美式 put 溢價，對照 §4.3，不能讀成 call 報價壞掉。
- r=4% 敏感度：delta_worst>0 全體比例 70.5% → 67.2%，分組結論不變；
  r=0 時掉到 35.2%，再次確認訊號主體是貼現口徑而非錯價。

### 4.5 資料健全性紅旗（穩賠配對）

```
D_worst > width（最差成交成本超過最大 payoff，穩賠）: 75 組（3.8%）
D_worst <= 0: 0 組
```

3.8% 的配對在最差口徑下買進即穩賠——這不是「貴」，是「報價不可
成交或已陳舊」。這條檢查**不需要 put 報價、不需要利率**，只要
`net_worst > K2−K1`，而引擎的 worst 口徑本來就算好了 net_worst。
這是本次實算裡唯一乾淨、零假設、可直接產品化的訊號。

---

## 5. 產品語意：「這組 call spread 貴」還是「該用 put spread 進場」

兩種呈現對應完全不同的產品承諾：

**選項 A：「這組 call spread（相對合成路徑）偏貴」——診斷型顯示。**
只陳述兩側報價的相對位置，不建議行動。範圍不變（引擎照樣只產
call spread candidates），put 報價已在快照內，計算是純函式。但依
§4，這句話在 mid 口徑對個別配對多半是雜訊（§4.2），系統性成分是
美式貼現（§4.3）；誠實的版本只剩「D_worst 超過 width──此組報價
不可成交」這一種強陳述（§4.5），以及在深度 ITM 區的「同 payoff
的 OTM 側報價明顯較窄」提示。

**選項 B：「該用 put spread 進場」——改變產品範圍。**這不是換一個
顯示字串：

1. **引擎範圍**：目前 candidates 只有 call debit spread；產 put
   credit spread 是新策略型別（排名、估值、序列化、前端全鏈路）。
2. **帳戶語意**：debit spread 付權利金、最大損失＝成本，現金帳戶
   可做；credit spread 收權利金、要**保證金**（width − credit），
   現金帳戶多半不可做，零售券商等級（options level）要求更高。
3. **美式風險語意**：credit spread 的短 put 深度 ITM 時有提前指派
   風險（§3.3）——而 §4.4 顯示 put 側優勢恰好集中在深度 ITM 區，
   優勢與風險是同一件事的兩面。推薦零售使用者去賺這 3% width，
   等於推薦他們承接指派風險，產品要能講清楚這件事才有資格推薦。
4. **與產品定位的張力**：本 app 的劇本是「看多到目標價」，debit
   spread 的心智模型（付出上限成本、賭上漲）與 credit spread
   （收租、賭不跌破）不同，混排會弄髒排名口徑（worst 成本收益率
   對 credit 策略要重新定義）。

本票只界定語意：**A 是顯示層決策，B 是產品範圍決策**，二者不該
混在同一張票裁示。§7 給 G1 的建議以 A 的最小子集為限。

---

## 6. 誠實侷限：三種「貴」的關係

parity 比較能回答的，跟使用者直覺問的「這組貴不貴」多半不是同一
個問題。三種「貴」：

1. **套利意義的貴（本文）**：同 payoff 的兩條進場路徑，哪條此刻
   報價較高。它是**同一瞬間的橫斷面**比較，抓的是兩側報價的相對
   錯位與資料健全性。它完全不知道這組 spread 對「這檔標的、這個
   波動率環境」而言處在歷史上的什麼位置。實測結論：在美式 ETF
   延遲報價上，這個訊號個別配對層級是雜訊（§4.2），系統性成分是
   模型口徑差（§4.3），殘餘可用部分是資料健全性（§4.5）與深度
   ITM 區的流動性側提示（§4.4）。
2. **相對歷史的貴**：這組 spread 的成本（或其 IV）相對自身歷史
   分位數高不高——`candidate-iv-relative-value.md` 與
   `iv-relative-history-methodology.md` 的主題，需要歷史資料，
   parity 比較零幫助。
3. **相對機率的貴**：成本相對模型期望 payoff 高不高——引擎估值
   （BS＋利率曲線）已在做的事。parity gap 對它也零幫助：兩側同貴
   或同便宜時 parity 殘差不動。

本次實算自身的侷限：**單一標的（YETI，消費股、無配息壓力）、單一
快照（2023-08-11，短率 5.3%）**。TLT 有每月配息（除息前 call 提前
履約誘因，§3.2），利率環境也不同——分布的具體數字（例如 3.8% 的
紅旗比例）不可直接外推到 TLT，但結構性結論（美式 box 貼上緣、
gap 埋在四腿價差內、優勢集中 ITM 區）依賴的是美式選擇權的一般
性質與市場結構，方向上可外推。若要在 TLT 上覆核，同一腳本吃
本 app 任何一份 Cboe 快照即可重跑（欄位相同）。

---

## 7. G1 裁示建議

**訊噪比判定：雜訊為主，不建議把「call vs put 側比價」做成排名
訊號或常駐指標。**個別配對 |gap| 中位數僅為四腿半價差的 0.22 倍、
88% 埋在交易成本內；系統性成分是美式貼現口徑而非錯價；最差成交
口徑下的 put 側優勢只存在於本產品不主打的深度 ITM 區，且該優勢
與提前指派風險互為表裡。

**若仍要做，最小實作（零額外資料——put 合約已在 ChainSnapshot
裡，Cboe 單一 GET 本來就回全鏈雙邊）分兩級：**

- **第一級（建議做，甚至不需要 put）**：穩賠紅旗
  `net_worst > K2−K1` ⇒「最差成交成本已超過最大 payoff，此組報價
  不可成交或已陳舊」。純顯示層警語，與 FB3-02 候選池警示同性質；
  實測能抓到 3.8% 的配對，全是真問題。
- **第二級（可選，診斷型顯示）**：對已選定的那一組算
  `put_route_worst = (K2−K1)·DF − (P_bid(K2) − P_ask(K1))`，與
  `net_worst` 並列顯示「同 payoff 的 put 側合成成本」。措辭必須是
  選項 A（§5）：只說「兩側報價相對位置」，不說「建議改用 put
  spread」；且差距小於四腿半價差時不顯示（否則 88% 情況是在展示
  雜訊）。DF 用既有期限對齊利率曲線（T12 成果），不需新利率輸入。

**不建議進入本輪範圍**：put credit spread 作為候選策略（選項 B）
——保證金／帳戶等級／指派風險／排名口徑四件事都要重定義，且實測
顯示其相對優勢在產品主打的 OTM 候選區並不存在。

**與其他路徑的界線**：本路徑與「相對歷史」（IV 分位數）、「相對
機率」（估值引擎）三者正交（§6），互不替代；parity check 唯一
獨佔的價值是**資料健全性**——而那個價值的最小載體是第一級紅旗，
不需要任何 parity 數學。

---

## 8. 引用清單

**實測實證（本地可重跑）**

- 真實 Cboe 全鏈原檔：`https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json`
  （758 筆／13 到期日，出處與自洽性檢核見
  `docs/research/cboe-field-semantics.md` §7）
- 分析腳本：scratchpad `parity_check.py`／`parity_check2.py`
  （核心邏輯已全文節錄於 §4.1，stdlib：json/math/statistics/datetime）

**本 repo**

- `option_chaser/data/cboe.py`（欄位映射；快照含全部 put 合約）
- `tests/test_data_cboe.py`（FB3-01 fixture——僅 3 筆，無法組四腿，
  故實算改用上列全鏈原檔）
- `docs/modifyRequestV1.md` 附錄 A14.2（worst 口徑：買腿 Ask −
  賣腿 Bid）
- `docs/research/candidate-iv-relative-value.md`、
  `docs/research/iv-relative-history-methodology.md`（「相對歷史」
  路徑，§6 的界線對象）

**搜尋索引轉述（未逐字核對原文）**

- https://www.boxtrades.com/ —— SPX box 成交彙整與隱含利率
- https://www.cboe.com/insights/posts/long-dated-box-spreads-a-better-way-to-buy-a-home-updated/
  —— 長天期 SPX box 當融資工具、高於國庫券 30–50 bps
- https://www.bogleheads.org/forum/viewtopic.php?t=371120 ——
  「Let's Talk SPX Box Spreads」長期討論串
- https://en.wikipedia.org/wiki/Box_spread —— box 基本關係
- https://www.schwab.com/learn/story/what-are-box-spreads 、
  https://optionsamurai.com/blog/short-box-spread/ 、
  https://optionalpha.com/strategies/short-box-spread ——
  American box 的提前指派風險
- https://support.tastytrade.com/support/s/solutions/articles/43000505597 、
  https://us.etrade.com/knowledge/library/options/understanding-assignment-risk
  —— 短腿提前指派機制與資金風險
- https://www.cboe.com/insights/posts/dont-get-stuck-paying-the-dividend-on-your-short-trade
  —— 除息前短 call 指派風險
- https://www.optiontradingpedia.com/conversion_reversal_arbitrage.htm 、
  https://www.tradealgo.com/trading-guides/options-strategies/conversion-and-reversal-arbitrage-how-market-makers-stay-delta-neutral 、
  https://www.optionseducation.org/advancedconcepts/put-call-parity
  —— conversion/reversal 術語、pin risk／dividend risk、做市商
  資金效率優勢
- https://www.midhafin.com/put-call-partity-american-options-bounds 、
  https://math.nyu.edu/~cai/Courses/Derivatives/lecture8.pdf 、
  https://www.math.hkust.edu.hk/~maykwok/courses/ma571/06_07/Kwok_Chap_5.pdf
  —— 美式 put-call parity 不等式 S−K ≤ C−P ≤ S−K·e^{−rT} 與
  股利修正
- 2019 Robinhood「1R0NYMAN」box 爆倉事件——**記憶轉述，未查證**
