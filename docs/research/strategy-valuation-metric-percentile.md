# 每種 Strategy 該把什麼放進自己的歷史分布——valuation metric 選型裁定

> **委託**：Option Chaser 未來支援多種 option strategy。需求方已裁定
> **不同 strategy 不需要、也不應該共用同一套 valuation metric**；真正跨
> strategy 的共同座標只有一個——「該 strategy 自己的 valuation metric，
> 目前值落在它自己歷史分布的第幾百分位」。本輪唯一任務：**逐 strategy
> 找出那個底層 metric**。
>
> **本輪只研究，不施工**：未寫 production code、未開 ticket、未設計
> Dashboard／UI、未修改 percentile 演算法。`git status` 全程只有本檔案
> 一個新增。
>
> 日期：2026-08-26／分支 `claude/implement-tfm9oa`／基準 HEAD `447c921`

---

## 證據分級（每條實質主張都掛標籤）

沿用本 repo 既有四級慣例：

- **【一手原文】** — 本輪實際讀到全文的原始文獻
- **【官方文件】** — 擁有該規格的組織自己發布的文件
- **【二手轉述】** — 轉述、搜尋索引摘要，或經本 repo 既有研究文件轉達的一手引文
- **【自行推論】** — 本輪自己的推導或引擎實算，未有外部來源背書

**⚠ 本文的證據結構必須先講清楚，不要被總量誤導**：本輪三條研究線的
證據等級落差很大。

| 研究線 | 一手原文 | 官方文件 | 二手轉述 | 自行推論 |
|---|---|---|---|---|
| Bounded structures（butterfly／condor／straddle／strangle） | **12** | 有（Cboe BFLY／CNDR methodology） | 多 | 多 |
| Vertical spread／單腿 | **0** | **0** | 27 | 41 |
| Prior Research Ledger（讀 repo） | — | — | — | — |

**Vertical spread 那條線沒有任何一筆本輪親讀的一手文獻**——它的說服力
100% 來自「引擎實算可重跑」與「與 repo 既有研究獨立交叉驗證」，不是來自
新的文獻權威。其 27 筆二手轉述中有 21 筆，是 repo 既有文件逐字重製的
一手引文（Zou & Derman 1999、Natenberg 1994、Gatheral、Mixon 2011 等）
的再轉達。**下裁示時請把這個落差算進去。**

---

## §0. 裁決（先給答案）

### 0.1 一句話

**需求方的產品原則成立，而且比原本設想的更乾淨——但代價是必須換掉
目前出貨的 Vertical Spread 指標，並且接受「跨 strategy percentile 只在
語意上可比、不在經濟後果上可比」這個誠實的限制。**

### 0.2 逐 strategy 裁定總表

| Strategy | 建議 metric | 歷史正規化方式 | 必須控制 | percentile 越高代表 | 證據信心 |
|---|---|---|---|---|---|
| **Long Call** | 買腿 `(tenor D, \|Δ\|)` 重錨定 IV | 1 年日曆窗、`≤` 含等於的 rank | 固定 tenor、固定 delta、不外插 | **更貴** | **高**（既有裁決，本輪未推翻） |
| **Long Put** | 同上（put 自己的網格、`\|Δ\|`） | 同上 | 同上 ＋ 必須用 put 網格 | **更貴** | **高**（指標）／**中**（跨策略可比性） |
| **Debit Vertical** | **VORD** ＝ 只換 vol、其餘凍結在今天的重定價 debit ÷ W | 同上；兩腿共同日期交集 | spot／DTE／r／q／履約價／寬度**全部凍結在今天** | **package 更貴**（對買方不利） | **中高**（數學強、先例無） |
| **Credit Vertical** | **VORD_credit** ＝ 同一公式，credit ÷ W | 同上 | 同上 | **package 更貴**（對賣方有利） | **中**（公式繼承，未經真實驗證） |
| **Butterfly** | `M = butterfly / (DF × h)` ＝ tent-weighted 風險中性機率 | 固定 DTE；body 錨在 ATM／固定 delta；wing width 取**相對值** | DTE ≫ moneyness ≫ vol；**all-OTM（iron）建構**；÷DF；美式漂移 | **更貴** | **高** |
| **Iron Butterfly** | `1 − credit/(DF × h)`（依 parity 與上式同一個數） | 同 butterfly | 同 butterfly | **更貴**（同樣風險收到更少 credit） | **高** |
| **Iron Condor** | `1 − credit/(DF × W)`，**delta-anchored**（20Δ/5Δ） | 固定 DTE；履約價錨在固定 delta | DTE；delta 錨定；÷DF；利率漂移 | **更貴** | **高** |
| **Straddle** | `straddle_mid / (DF × F)`（與 `σ_ATM` percentile 逐筆等價） | constant maturity；ATM-forward | DTE；ATM 錨定；單一價格口徑 | **更貴**（vol 貴） | **高** |
| **Strangle** | 固定對稱 delta 的 `(σ_put,Δ + σ_call,Δ)/2` ＝ `σ_ATM + BF` | constant maturity；固定 delta | DTE；對稱 delta 錨定 | **更貴**（level 與/或 curvature，兩者混在一起） | **高**（分解）／**中**（作為單一數字） |
| **Calendar／Diagonal** | **本輪不裁定，列為 V2+** | — | — | — | — |

Calendar／Diagonal 依委託授權延後：跨到期日讓「固定 tenor」這個本文
全部裁定所依賴的錨定方式失去唯一定義（兩條腿各有自己的 tenor），
方法本質不同，硬塞進本文框架只會製造假的一致性。

### 0.3 三條最重要的結論

**一、現行出貨的 `Spread IV Gap = Sell IV − Buy IV` 的 percentile 必須
停用。** 需求方的疑慮不只成立，而且比描述的更嚴重：它對 package 貴賤
不只是「主要描述 skew」，而是**對最大的驅動因子完全失明、對次要因子
符號相反**（§3）。而且這件事 **repo 自己的既有研究早就明文寫過**
——`candidate-iv-relative-value.md` §4.3 裁定 raw gap「走勢圖可以、
**percentile 不行**」，`historical-rich-cheap-canonical-methodology.md`
§11.3 掛了 ⚠ 說「skew 好看但 vol level 高、debit 仍然貴是真實情境」。
**出貨與既有裁決不一致，這是本輪最該修的東西。**

⚠ 要拿掉的是掛在 gap 上的 **percentile 與「歷史位置」語意**；**gap
作為走勢圖仍然有價值**（它誠實描述 skew 怎麼動）。

**二、三個 bounded 結構（butterfly／iron butterfly／iron condor）在數學上
是同一個工具，不是被硬湊在一起的。** `condor/(DF·W) + credit/(DF·W) = 1`
（數值驗到 1.78e-14）、`butterfly/(DF·h) = E^Q[tent(S_T)]`（驗到 5.6e-10）
——**no-arbitrage 說它們是同一個東西**，所以它們共用一個公式不違反
需求方「不得為了整齊硬湊」的紅線。方向歧義也隨之消失：**credit 賣方
在經濟上是那個 in-band payoff 的買方**，一句話同時涵蓋 debit 與 credit
兩種形式。

**三、跨 strategy percentile 是「同一種語句」可比，不是「同一種經濟
後果」可比。** 這是需求方核心前提的誠實答案，詳見 §7。

---

## §1. 取材限制（先講，因為它決定後面每一節的證據等級）

### 1.1 沙箱網路現況——**本輪更新了 repo 的既有紀錄**

repo 過去幾輪記載「`raw.githubusercontent.com` 是唯一一手通道」。
**本輪實測，這條記載已經過期**：

| 通道 | 本輪實測結果 |
|---|---|
| `raw.githubusercontent.com` | **已失效**（前輪 papers 鏡像路徑回 404） |
| `WebFetch` | **被擋** |
| `curl` → `cdn.cboe.com` | **200 通** ← 官方 methodology、完整即時全鏈、數十年指數歷史 |
| `curl` → `arxiv.org` | **200 通** |
| `curl` → `federalreserve.gov`／`nber.org`／`bis.org` | **200 通** |
| 各 vendor／交易所／監管網域（`api.marketdata.app` 等） | CONNECT 403 或 DNS 失敗（不變） |

**`curl` 沒有被沙箱閘道攔截，`WebFetch` 有**——這個區別是本輪最實用的
環境情報，建議寫進 `CLAUDE.md` 的「## 環境」一節供後續研究輪使用。
本文 bounded structures 那條線的 12 筆一手原文，全部是靠 `curl` 取得的。

### 1.2 資料限制

- **#111 仍 blocked**：真實 vendor 歷史選擇權鏈拿不到，因此本文**所有
  歷史 percentile 的行為主張都無法用真實序列驗證**，只能用引擎實算與
  合成曲面。這是本輪最大的單一限制。
- **`_MVP_STRATEGIES = ("bull-call-spread",)`**（`api_app/main.py:84`，
  本輪親自確認）——**委託點名的九個 strategy，今天只有一個真的有
  candidate generator**。本文其餘八個 strategy 的裁定全部是前瞻性的，
  沒有任何一個能用今天的 production 資料當場驗證。

---

## §2. Prior Research Ledger（Step 0 成果）

完整 ledger 共 821 行，逐條列出 26 個研究問題的狀態。此處只放結論。

**狀態統計：ANSWERED 15 · PARTIAL 5 · OPEN 6**

### 2.1 五條 ANSWERED——本輪未重新研究，直接沿用

| # | 既有結論 | 出處 |
|---|---|---|
| 1 | **`Sell IV − Buy IV` 量的是 skew，不是 package 貴賤。** 一階分解 `dV = (vega₁−vega₂)·dσ̄ + ½(vega₁+vega₂)·ds`——gap 騎在**平均** vega（永不為零），level 騎在 **net** vega（小且會變號，引擎實測 +0.2275 → −0.2616 across spot）。**ATM IV level 在兩腿之間幾乎完全抵消** | `fair-value-residual-methodology.md` §1.6；`candidate-iv-relative-value.md` |
| 2 | **不存在可定義的單一「Spread IV」。** `V(σ,σ)` 非單調（峰值以下有兩個 σ 解）；真實 TLT 部位解出 `σ_net = −0.74 vol 點`，賣腿 vega 動 1% 就跳 0.41 點 | `historical-rich-cheap-canonical-methodology.md` §6.1 |
| 3 | **price-space spread percentile 被 dominated。** 它相對 vol-space 唯一多出來的成分就是 rate／dividend／forward，而那是汙染：利率 +2pp ⇒ 理論價 +26% | `spread-price-percentile-vs-vol-space.md` |
| 4 | **`IV − realized vol` 否決**（量的是 variance risk premium，不是錯價）；**full SAS 是結構性死路**（唯一大得過摩擦的成分是 GS 自己歸零的那一半；可信的那一半只有 0.16–0.50 vol 點 vs 買賣價差半寬 0.80–2.65 點） | `historical-rich-cheap-canonical-methodology.md` §5.3／§5.4 |
| 5 | **可得性算術**：A（同合約歷史）需 `L ≥ D+T`，B（固定 tenor）只需 `L ≳ D`。repo 真實 882 天 fixture 下 A 需 41 個月 > 39 個月法規上限——**同合約殘差歷史在數學上不可能，換哪家 vendor、付多少錢都一樣** | 同上 §9.4 |

### 2.2 一個必須攤開的既有矛盾

`fair-value-residual-methodology.md`（主張 SAS-L：**保留 level、丟掉
shape**）比 `historical-rich-cheap-canonical-methodology.md`（**保留
shape、把 level-vs-history 當 VRP 否決**）**晚 6 小時**產出，兩者對
「level 要不要算」是相反的。而 SAS-L 自我歸類的家族，正是 canonical
文件否決掉的那個 VRP 家族。

**裁定：canonical 文件為準**，三個獨立理由——委託條款、專案紀錄區的
採納紀錄、以及 SAS-L 從未出貨。SAS-L 保留其 LEAPS 病理清單，以及一條
與此爭議無關、本身成立的算術：20 年資料只能產生約 10 個不重疊的 2 年
觀測。

⚠ **但本輪 §3.8 的發現讓這個矛盾出現新的轉折**：canonical 文件否決
level 的理由是「兩腿反號抵消讓 net vega 很小」，而那個前提在本產品
實際產生的 candidate 幾何下**不成立**。詳見 §3.8——這不是推翻 canonical
的裁決，是指出它的適用範圍比原本以為的窄。

### 2.3 六條 OPEN——本輪外部研究的實際標的

1. **除 vertical spread 外每個 strategy 的 richness metric**——Iron
   Condor／Iron Butterfly／Diagonal 在既有 27 份研究裡**字面零出現**；
   Butterfly／Strangle 的命中全是 FX 報價慣例；Straddle 的命中全是別人
   的測試工具。
2. 出貨的同合約 gap percentile 是否站得住（可本地驗證，不需 vendor）
3. 「對殘差取 percentile」有無先例（前輪刻意找過、沒找到，但當時搜尋通道
   已降級）
4. **跨 strategy percentile 可比性——本輪的核心前提，從未被檢驗過**
5. 縱向（longitudinal）reconstruction 準確度（既有只驗過橫斷面）
6. delta convention 驗證（#111 blocked）

---

## §3. 核心裁定一：Vertical Spread（委託特別要求重新判斷）

### 3.1 決定性數值實驗

引擎實算，用 repo 真實 fixture `tlt_leaps_real_quotes_2026-07-17.json`
（S=84.52／DTE 882／買 K90 賣 K130／W=40）。

**實驗一：vol level 12% → 22%，skew 形狀一個 vol point 都沒動**

| 量 | 前 | 後 | 變動 |
|---|---|---|---|
| **IV gap（現行出貨）** | 6.00 pt | 6.00 pt | **0.0%** ← 讀數一模一樣 |
| **Ĝ**（normalized skew） | 0.4882 | 0.2692 | **−44.9%** ← 反而說「變便宜」 |
| **debit（使用者實付）** | $3.167 | $5.065 | **+59.9%** |

> 「IV gap 正常但 spread 變貴」不是理論顧慮，是這個指標的**結構性必然**。

**實驗二：skew 變陡 ×2，level 不動**

IV gap **+100.0%**／Ĝ **+95.4%**／debit **−42.6%**
——兩個指標都往「更貴」走，價格卻往便宜走。**方向是反的。**

**實驗三：保真度總表**（4 個純 vol 衝擊，比對指標變動 % vs 使用者實付變動 %）

| 純 vol 衝擊 | **真實 debit** | IV gap（現行） | Ĝ | 買腿 IV | **VORD** |
|---|---|---|---|---|---|
| level 12%→18% | **+41.6%** | 0.0% | −32.8% | +45.4% | **+41.6%** |
| level 12%→8% | **−38.5%** | 0.0% | +48.3% | −30.3% | **−38.5%** |
| skew ×1.5 | **−17.6%** | +50.0% | +48.3% | +4.6% | **−17.6%** |
| skew ×0.5 | **+8.6%** | −50.0% | −49.4% | −4.6% | **+8.6%** |
| **符號吻合** | — | **0/4** | **0/4** | 2/4 | **4/4** |
| **量級吻合** | — | **0/4** | **0/4** | 0/4 | **4/4** |

【自行推論，引擎實算】

### 3.2 為什麼「vertical = 純 skew 玩法」在本產品不成立（決定性）

業界把 vertical spread 當 skew 工具的通則，**預設兩腿履約價相鄰**。
本產品實際產生的幾何完全不同：

| 寬度 W | 佔 spot 比例 | net vega ÷ 買腿 vega |
|---|---|---|
| 2.5 | 3% | **5.6%** |
| 5 | 6% | 12.6% |
| 20 | 24% | 60.4% |
| **40** | **47%** | **92.3%** ← 本產品實際產生的幾何 |

> W=40 時 net vega 是買腿的 **92.3%**——**vega 上幾乎就是裸買一張 call**。
> 代入 `fair-value-residual-methodology.md` §1.6 的一階分解，level 分量
> 的權重是 skew 分量的 **12.0 倍**。

**這解釋了一切**：既有研究說「level 在兩腿之間抵消」沒有錯，錯在那個
結論被套用到了它不適用的幾何上。**本產品的 candidate 不是窄價差，是
接近裸買腿的寬價差**，level 是主角不是配角。而現行指標對 level 的
靈敏度是 0.0%。

### 3.3 認真評估 Debit ÷ Width——它應得的肯定與致命問題

**先給肯定**：`spread-implied-probability-readout.md` §3.1 有一條
**模型無關、精確成立**的恆等式：

```
D/W = DF × (1/W)·∫[K1,K2] Q(S_T ≥ K) dK          0 ≤ D/W ≤ DF
```

即「付 D/W 換每 $1 上限」＝ 貼現因子 × 生存機率在 K1–K2 帶上的平均值。
**不需要** Black-Scholes、不需要 vol、不需要 forward／股息假設——對本產品
（q 模型未完全鎖定、美式 ETF、LEAPS）是真優勢。零售端也有成熟口語版
（tastytrade 系「至少收寬度 1/3」）【二手轉述】。

**但作為歷史 percentile，兩個獨立的致命問題**【自行推論】：

**(a) 自我指涉——沒有價格與價值之間的楔子。**
D/W **同時**是「你付的價格」與「市場認為的機率」。付 8.7¢ 買市場定價
8.7% 的機率，在市場自己的測度下**依定義是公平的**。要判斷值不值必須拿它
跟**別的東西**比，而 D/W 自己不含那個比較對象。**它是很好的「翻譯尺」，
不是「貴賤尺」。**

**(b) 歷史 percentile 被 moneyness 主宰。** vol surface **完全凍結**、
只動 spot：

| spot（曲面凍結） | IV gap | debit | **D/W** |
|---|---|---|---|
| 71.84（−15%） | 6.00 pt | $1.174 | **2.94%** |
| 84.52（基準） | 6.00 pt | $3.167 | **7.92%** |
| 105.65（+25%） | 6.00 pt | $13.153 | **32.88%** |
| **變動** | 0.0% | +315.3% | **+315.3%** |

> vol 貴賤一絲一毫都沒變，D/W 走了 2.94% → 32.88%。
> **「D/W 在歷史第 90 百分位」≈「標的漲上來了」。**

**(c) 重錨定救不回來**（本輪新增量測，既有研究只測過固定履約價）：

| 衝擊 | fixed-strike D/W | **fixed-delta（重錨定）D/W** |
|---|---|---|
| r 3% → 5% | +21.0% | **−18.1%** |
| q 0% → 4.5% | −47.1% | **+28.7%** |
| spot +15% | +145.0% | **−0.0%**（完美） |
| DTE 882→517 | −21.6% | **+1.6%**（近乎完美） |

> 重錨定完美修掉 spot 與 DTE（真收穫），但對利率與股息**只是把符號
> 翻過來、量級沒變小**。真實 skew 訊號只值 17.6–32.6%——**汙染與訊號
> 同量級**。

### 3.4 ⚠ 本輪整合時抓到的方法論落差（主 session 親自計算）

上表的 D/W **未除以貼現因子**（其上界是 DF 不是 1），而 §4 的
bounded-structure 建議 `M = price/(DF × max_payoff)` **有除**。兩者
因此不是拿同一把尺在比。主 session 補算：

```
T = 882/365 = 2.4164 年
DF(3%) = 0.93007    DF(5%) = 0.88619    DF 比值變動 = −4.72%
D/W 實測（未除 DF）        : −18.1%
同一序列除以 DF 之後       : −14.0%
÷DF 消掉的汙染             : 0.041 / 0.181 = 22%
```

**裁定：÷DF 是必要但不充分的修正。** 它只消掉 22% 的利率汙染，剩下的
14% 來自 forward drift（利率改變 forward，進而改變機率本身），那不是
貼現能修的。所以：

- **§3.3(c) 對 D/W 的否決仍然成立**（14% 仍與訊號同量級）
- 但**否決的力道被高估了約兩成**，本文如實修正
- **§4 對 bounded structures 的 ÷DF 要求是對的，且不可省略**

### 3.5 那到底有沒有能量 package 貴賤的單一數字——有

**【自行推論。這是本輪的核心建議，也是研究線自己的構造，證據等級請
看清楚。】**

問題根源：**現行指標在 vol 空間，看不到 level 與 skew 如何按這個結構
自己的 vega 權重合成價格；而 price 空間又被 spot／DTE／r／q 汙染。**

兩邊都要的話，答案是**把非 vol 的東西全部凍結**：

> ### VORD（Vol-Only Repriced Debit/Credit ÷ Width）
>
> 對每個歷史日 `t`，取兩腿當日隱含波動率 `σ_b(t)`、`σ_s(t)`，然後用
> **今天的** spot、**今天的** DTE、**今天的** r 與 q、**今天的**履約價，
> 重新定價**今天這組結構**：
>
> ```
> D_t    = C(S_now, K_b, T_now, r_now, q_now, σ_b(t))
>        − C(S_now, K_s, T_now, r_now, q_now, σ_s(t))
> VORD_t = D_t / W
> ```
>
> 取 `VORD_today` 在 `{VORD_t}` 一年序列中的 percentile。

**汙染為何是零**：spot／DTE／r／q 根本沒有進入序列的變異——被釘在今天
的值。**這不是「修正」或「控制」，是結構上不可能發生。**

**四個關鍵性質**：

1. **訊號保真 4/4 是恆等式不是擬合**——VORD 就是那個價格本身（§3.1
   實驗三）。
2. **對單腿完全退化成既有裁決**：`VORD_single(t) = C(S_now, K, T_now,
   r_now, q_now, σ_t)`。價格對 σ 嚴格遞增（vega > 0 恆成立）⇒ 單調變換
   ⇒ **保序** ⇒ **percentile 完全相同**。實測 250 樣本 × 3 張合約
   （0.36Δ call、深 OTM put、0.08Δ call），percentile mismatch ＝ **0**。
   **所以採用 VORD 不會造成單腿行為變更，跨策略可比性是數學上的同一個
   量，不是拼湊。**
3. **方向零歧義**：它是價格，更高＝package 更貴。其他每個候選都有 sign
   trap（實測 W=5 的窄 debit vertical，debit 對 vol 是**非單調**的，
   net vega 會穿零轉負，「更高 IV = 更貴」不普世成立）。
4. **零新增資料需求**——輸入就是現行 Spread IV Gap 已經在用的那兩條
   exact-contract 重建 IV 序列。

### 3.6 Debit vs Credit：同一公式，不同解讀

不需要兩個指標。VORD 對兩者都是「package 價格 ÷ 寬度」，「更高 =
package 更貴」普世成立，只是 debit 方是買家（貴 = 不利）、credit 方是
賣家（貴 = 收得多）。

**建議文案一律寫「package 貴／便宜」，不要寫「對你好／不好」**——
這同時解決 debit/credit 方向反轉與 net vega 穿零兩個問題。

### 3.7 VORD 的誠實缺口（必須向需求方明說）

1. **仍留約 ±21% 的 spot 殘餘汙染**——固定履約價的 IV 會隨 spot 沿著
   smile 滑動，這一層凍結不了。比現行 D/W 的 ±145% 好 7 倍、比現行 gap
   的完全失明是質變，但**不是零**。
2. **沒有直接業界先例。** 最接近的是 desk 的 scenario-based P&L
   attribution【二手轉述，`risk.net` 索引摘要，未讀全文】。把它拿來做
   **單一 candidate 的一年 percentile** 找不到具名先例。**研究線自己說
   這是它最想被推翻的一點**，本文如實轉達。
3. **曲面是單一參數化**。結論**方向**應穩健（保真度是恆等式），但**汙染
   的量級數字**會隨曲面形狀變。
4. **Credit vertical 整節未經真實驗證**（產品目前不產生此類 candidate）。
5. **fixed-coordinate 輸入版的 VORD 沒調校好**（座標錯配），不建議照原樣
   採用，需要另一輪設計。

### 3.8 一個獨立交叉驗證（值得注意）

本輪量到固定履約價 gap 序列有 **+30.6%/年**的機械 roll-down 漂移，這
獨立重現了 `candidate-iv-relative-value.md` §4.2.1 用 √t 律預測的
**+30%**——**兩條完全獨立的路徑得到同一個數字**。這對「gap 序列不適合
做 percentile」是強化證據。

---

## §4. 核心裁定二：三個 bounded 結構是同一個工具

### 4.1 恆等式（數值驗證）

【自行推論＋引擎實算，數值驗證】

```
butterfly / (DF × h) = E^Q[ max(0, 1 − |S_T − K| / h) ]      驗到 5.6e-10
condor/(DF·W) + credit/(DF·W) = 1                            驗到 1.78e-14
```

第一式是 Breeden–Litzenberger 的直接結果——butterfly 的 payoff 是一個
tent function，最大值為 h（在 S_T = K），除以 h 後值域落在 **[0, 1]**，
是一個 **tent-weighted 風險中性機率**。第二式是 put-call parity 的直接
推論。

**因此三個結構共用一個公式，不違反需求方「不得為了整齊硬湊」的紅線
——no-arbitrage 說它們本來就是同一個東西。**

統一形式：

```
M = structure_price / (DF × max_payoff)          M ∈ [0, 1]
```

### 4.2 方向陷阱的消解

**credit 賣方在經濟上是那個 in-band payoff 的買方**，價格 `M`。一旦看穿
這點，debit 與 credit 兩種形式用同一句話描述方向：**M 越高＝這個結果越貴**。
不需要為 credit 結構另立一套方向語意。

### 4.3 三條不可省略的建構紀律（每條都有實測）

| 紀律 | 實測 | 官方先例 |
|---|---|---|
| **必須用 all-OTM（iron）建構** | 同一個經濟上等價的 butterfly，三種建法在即時 SPY 鏈上的雜訊帶：all-call **0.0525**／all-put **0.0789**／**iron 0.0032**——乾淨 **17–25×**。原因是 ITM 那條腿帶 4.6–7.5% 的買賣價差。**不這樣做，butterfly 的雜訊帶會超過它的整個訊號範圍** | — |
| **必須 delta／moneyness 錨定，不可用固定履約價** | vol-level 汙染少 **17.2×** | **Cboe BFLY（5% OTM）與 CNDR（5Δ/20Δ）methodology 都這樣做**【官方文件】 |
| **必須除以貼現因子** | 否則有 1.9pp 的單調利率假象——**恰好在利率有趨勢時製造假的 regime shift** | — |

### 4.4 一個被低估的威脅：美式提前履約

put butterfly 上高達 **30% 的相對扭曲**，且在 0→5% 的利率週期上有
**+1.2pp 的單調漂移**——約佔整個訊號範圍的三分之一。**趨勢性汙染是
percentile 最糟糕的敵人**（它會讓 percentile 單向爬升，看起來像持續
變貴）。

緩解：在無股息標的上優先採用 call-based 建構是**零誤差**的，但不總是
可得。完整的 de-Americanization 修正本輪未測試。

---

## §5. 核心裁定三：Straddle 與 Strangle

### 5.1 Straddle——本輪最強的單一結果

在 ATM-forward 下（K = F），Black-76 給出 d₁ = σ√T/2、d₂ = −σ√T/2，
call 與 put 相等，因此：

```
straddle / (DF × F) = 2·( 2N(σ√T/2) − 1 )
```

【自行推論，閉式驗到 4.4e-15；主 session 獨立以 Black-76 推導確認】

這是**對 σ 嚴格遞增的雙射**。所以在固定到期期限下，**straddle 價格的
percentile 與 ATM IV 的 percentile 逐筆完全相同**。

**實務價值**：它**不需要反解 IV**——直接繞開本 repo 已記載的
`implied_vol()` 在 LEAPS 與退化 vendor IV（實測出現過 `vendor_iv ≈ 0.0001`）
上的脆弱性。即時鏈驗證：本輪算得 12.68% vs Cboe 自己的 12.46%，買賣
價差只值 ±0.023 vol 點——五個結構裡最乾淨的（0.36% of mid）。

**每天只需要兩張合約。**

### 5.2 IV − RV 對 straddle：既有否決成立，但直覺有一半是對的

**這一條研究線處理得很誠實，值得完整轉達**：

- **delta-hedged** 的 straddle **確實**是一個 variance 工具——這是為什麼
  直覺覺得 IV−RV 該適用。
- 但**未對沖**、持有到到期的 straddle 付的是 `|S_T − K|`，那是一個
  **終端價格函數**，不是 variance。
- **決定性的一點**：RV 在決策當下**是不可知的**（它要等選擇權存續期
  走完才知道）；用 trailing RV 代替，等於**偷換成第三個統計量**。

**既有否決成立**，但這個區別必須寫清楚，不能揮手帶過。

### 5.3 Strangle——分解精確，但作為單一數字有真實的妥協

```
(σ_put,Δ + σ_call,Δ) / 2  =  σ_ATM + BF        （固定對稱 delta 下精確成立，RR 代數上抵消）
```

【一手原文，Vanna-Volga arXiv:0904.1074 §3.3】即時 SPY 驗證：
BF +0.53／+1.29／+2.32 vol 點（25/16/10Δ）、RR −3.88／−6.07／−8.53。

**誠實的妥協**：這一個數字把 **level（σ_ATM）與 curvature（BF）混在
一起**。分開報 `σ_ATM` 與 `BF` 兩個 percentile 資訊量更高，但那**違反
「每 strategy 一個數字」的規則**——這是需求方的產品裁示點，不是研究能
決定的事。

---

## §6. 兩條研究線的關係——VORD 與 M 是同一個框架的兩端

這一節是主 session 整合時的判斷，兩條研究線各自都沒有寫。

### 6.1 表面上的衝突

- §4 推薦 bounded structures 用 `M = price/(DF × max_payoff)`，**直接取
  percentile**
- §3.3 卻**否決**了 vertical spread 的 `D/W`——形式上是同一種「價格 ÷
  最大報酬」

### 6.2 裁定：不是矛盾，是同一個問題在不同幾何上嚴重程度不同

| | Vertical spread 的 D/W | Bounded structure 的 M |
|---|---|---|
| payoff 的形狀 | **單邊、帶狀**（K1 到 K2 的累積生存機率） | **對稱、局部**（tent，罩在 body 附近） |
| body 錨在哪 | 沒有 body，整條帶隨 spot 相對移動 | **錨在 ATM／固定 delta**，永遠罩住 spot 附近 |
| spot 移動的效果 | D/W 必然單調上升（實測 spot +25% ⇒ **+315.3%**） | 被錨定吸收（重錨定後實測 **−0.0%**） |
| 本產品實際幾何 | **W=47% of spot**，極寬，幾乎是裸買腿 | 由建構規則自己決定，可控 |

**所以 §3.3(b) 的「被 moneyness 主宰」不能直接套到 delta-anchored
butterfly 上**——那是 vertical spread 單邊帶狀 payoff 的特有病，不是
「價格 ÷ 寬度」這個形式本身的病。

剩下的共同病是 **r／q 汙染**，兩條線都量到了、也都承認：§3.3(c) 的
−18.1%／+28.7%，與 §4.4 的 +1.2pp 單調利率漂移，**是同一件事在兩種
結構上的兩次現形**。§3.4 已證明 ÷DF 只能修掉其中 22%。

### 6.3 一個統一的可能性（供需求方裁示，本輪不推薦逕行採用）

**VORD 的核心思想「凍結所有非 vol 因子」在數學上可以套用到 bounded
structures**，把 §4.4 承認的利率漂移一併清零。也就是：

```
M_VORD,t = structure_price( S_now, K_now, T_now, r_now, q_now, σ(t) ) / (DF_now × max_payoff)
```

**但本輪不推薦逕行採用**，理由是一個真實的 trade-off，該由需求方裁：

| | `M`（§4 建議） | `M_VORD`（統一版） |
|---|---|---|
| **業界先例** | **有，且是官方規格**（Cboe BFLY／CNDR methodology）【官方文件】 | **無**（§3.7 第 2 點） |
| **r／q 汙染** | 有（÷DF 後仍有，§3.4／§4.4） | 結構上為零 |
| **可解釋性** | 「這是市場對這個結果定的機率價」——一句話講得完 | 需要解釋「凍結重定價」 |

需求方的產品原則寫的是「最符合機構實務」——**若那條原則優先，`M` 勝；
若「汙染最小」優先，`M_VORD` 勝。** 這是價值取捨，不是研究能代答的。

---

## §7. 正面回答核心前提：跨 strategy percentile 真的可比嗎

**這是本輪的核心前提，既有 27 份研究從未檢驗過它**（ledger OPEN #4）。
必須誠實回答。

### 7.1 可比的部分

percentile 是 rank statistic。在母體 stationary 的前提下，「第 P 百分位」
對任何 metric 都是**同一句話**：「比自己過去 P% 的時候貴」。這個**語意
是可比的**，而且是本輪框架成立的基礎。

### 7.2 不可比的部分——三個實測證據

**(a) 同一個數值可以同時是最貴與最便宜。** 用 Cboe 官方 `VIX_History.csv`
（9,258 個觀測）【一手原文】：

| VIX 水位 | 1 年 percentile 範圍 | 中位數 | n |
|---|---|---|---|
| 12 | 0.4 → 85.0 | 20.4 | 702 |
| **18** | **0.4 → 100.0** | 39.1 | **509** |
| 25 | 7.5 → 100.0 | 63.6 | 245 |
| 30 | 26.5 → 99.6 | 84.2 | 103 |

> **VIX = 18 在樣本裡同時當過最便宜與最貴的讀數，509 次。**
> percentile 回答的永遠是**「相對最近的記憶在哪」**，**從來不是**
> 「絕對而言貴不貴」。任何暗示後者的文案都是錯的。
>
> ⚠ 這與需求方 2026-08-25 對 percentile 文案的既有裁示（不得用
> 「異常／離群／貴」）**方向一致並強化了它**。

**(b) 回看窗口是一個使用者看不見、卻能改變答案的自由參數。**
同一個 VIX = 15.45：

| 窗口 | percentile |
|---|---|
| 126d | **10.2** |
| 252d | **15.4** |
| 504d | **18.2** |
| 756d | **35.4** |

> **3.5 倍擺動，純粹來自一個沒人看得見的選擇。**
> **窗口必須固定、必須寫進方法論、且應該讓使用者看得到。**

**(c) 不同 metric 的 persistence 不同，所以同一個 P80 意義不同。**
36 年 Cboe 資料：**SKEW 的 252 日自相關 ρ = +0.539，比 VIX 的 +0.248
更黏**。

> ⚠ **這條研究線誠實地反駁了自己**——它原本預期 shape 類指標
> persistence 較低（那會強化它自己的推薦），量出來相反，照樣寫進去。
> 後果是：**一年窗口對它自己推薦的那些 shape metric，可能整個落在
> 同一個 regime 裡面**，percentile 因此被壓縮。

**(d) 同一個事件在不同 strategy 上的反應倍率不同。** 實測在股票式向下
skew 下，鏡像 delta 的 put IV 與 call IV 差到 **22 個 vol 點**（0.10
delta）；同一個 ATM +6 pt 的純平移事件，在 0.15 delta 上讓 put IV 動
8.16 pt、call IV 只動 4.09 pt（**2.0×**）。

### 7.3 裁定

> **跨 strategy percentile 是「同一種語句」可比，不是「同一種經濟後果」
> 可比。**
>
> 「這個 Butterfly 在第 80 百分位」與「這個 Long Call 在第 80 百分位」
> **都正確地表示「比自己過去 80% 的時候貴」**——這個比較合法、有用，
> 而且是需求方要的東西。
>
> 但它們**不表示兩者貴的程度相同、不表示回歸的速度相同、也不表示
> 兩個 80 分背後的市場事件一樣大**。

**兩條必要條件**（若不滿足，跨 strategy 比較會誤導）：

1. **全部 strategy 必須用同一個回看窗口**，且該窗口要對使用者可見
   （否則 §7.2(b) 的 3.5× 擺動會在不同 strategy 之間製造假差異）。
2. **percentile 本身不足以當結論**，必須與 metric 的原始值並陳
   （§7.2(a)：VIX=18 可以是任何百分位）。

補充一條與本輪主題正交、但需求方應該知道的事實：**現行排行榜排的是
「賠率」不是「價值」。** `ranking.py:151` 的
`spread_baseline_return = (baseline_value − net_worst) / net_worst`，
劇本成立時 `baseline_value` 即滿額值，故此數本質是 `width/debit − 1`；
而 `debit/(DF×width)` 正是 §3.3 那個風險中性機率 p̂，兩者合起來即
`baseline_return ≈ 1/p̂ − 1`——由高到低排序等於**照 p̂ 由低到高排**。

**這不是 bug**：在「劇本必定成立」的前提下選賠率最高的確實是對的。但它
結構上不看劇本成立的機率，**而那正好就是本輪要建的那條軸**。兩者是
互相獨立的軸，不是新舊版本的關係——文案上必須分清楚，否則使用者會把
新指標誤解成舊排名的改良。

---

## §8. A / B / C 分級

### §A. Strong recommendation（成熟理論／機構實務支持，可直接作產品候選）

**A1. 停止把 1 年 percentile 掛在 `Sell IV − Buy IV` 上。**
本輪證據最強的一條：符號吻合 **0/4**、量級吻合 **0/4**、對 level
**0.0%** 失明、**+30.6%/年**機械漂移。而且 repo 既有兩份研究早已明文
寫過同一件事。⚠ **gap 作為走勢圖仍有價值**，要拿掉的是 percentile 與
「歷史位置」語意。

**A2. Long Call／Long Put 維持既有裁決**（fixed-tenor／fixed-delta 重錨定
IV percentile），**不要動**。本輪未發現任何推翻它的證據，並額外證明它與
VORD 是同一個數字（保序，mismatch = 0）。

**A3. Straddle → `straddle_mid / (DF × F)`，constant maturity。**
與 ATM IV percentile 逐筆等價（嚴格遞增雙射，已證），所以零資訊損失，
且**不需要反解 IV**——直接修掉本 repo 已記載的一個脆弱點。每天兩張合約，
五個結構裡買賣價差最乾淨。**本輪最強的單一結果。**

**A4. Bounded structures → `M = structure_price / (DF × max_payoff)`，
delta／moneyness 錨定。** 精確等於 tent-weighted 風險中性機率
（驗到 5.6e-10），值域 [0,1]。debit 與 credit 形式依 parity 是同一個
工具（驗到 1e-14）。

**A5. Family A 一律用 all-OTM（iron）建構。** 買賣價差雜訊少 16.6–24.9×，
中價一致到 0.021，所以這是免費的。**不這樣做，雜訊帶會超過整個訊號範圍。**

**A6. Family A 一律 delta 錨定，絕不用固定履約價。** vol-level 汙染少
17.2×。**Cboe 自己的 BFLY（5% OTM）與 CNDR（5Δ/20Δ）methodology 都這樣做**
【官方文件】。

**A7. 一律除以貼現因子。** 否則有 1.9pp 單調利率假象。（⚠ 但 §3.4 已證
這只修掉 22% 的利率汙染，不可誤以為除完就乾淨了。）

**A8. Strangle → 固定對稱 delta 的平均腿 IV**（＝ `σ_ATM + BF` 精確成立，
RR 代數抵消）。成熟 FX 慣例，有一手原文定義。

**A9. 方向語意一律寫「package 貴／便宜」，不要寫「對你好／不好」。**
同時解決 debit/credit 方向反轉與 net vega 穿零兩個問題。

**A10. 全部 strategy 必須共用同一個回看窗口，且對使用者可見**（§7.3）。

### §B. Plausible but needs validation（理論合理，證據或資料不足）

**B1. VORD 本身。** 數學可信（保真度是恆等式、保序性是 vega>0 的直接
推論），但：**無直接業界先例**（研究線自己最想被推翻的一點）、**±21%
spot 殘餘汙染**、曲面是單一參數化。**建議在裁示前先用一組真實 candidate
的實際重建 IV 序列跑一次 VORD、跟現行 gap 序列並排看**——沙箱做不到
（#111），production 可以。

**B2. `M` 的歷史離散度 0.0374 是模型數字不是實證數字。** 它來自在引擎裡
掃 σ 0.10–0.60，不是真實歷史序列。22.4× 訊噪比的主張建立在它上面。
**真實離散度可能明顯更小**，那樣的話雜訊底線就比本文說的更要緊。需要
真實歷史鏈，#111 blocked。

**B3. 回看窗口選多長。** §7.2(b) 顯示 126/252/504/756 天有 3.5× 擺動，
§7.2(c) 顯示 shape metric 夠黏、252 天可能整個落在同一個 regime 裡。
**本輪蒐集到的證據裡沒有可辯護的預設值**——需要真實歷史研究或需求方
明確裁示。

**B4. Family A 的美式修正。** §4.4 量化了問題（put butterfly 高達 30%
相對扭曲、利率週期 +1.2pp 單調漂移），但未測試修正方法。

**B5. Credit vertical 整節。** 公式繼承 debit 的證據，但產品目前不產生
此類 candidate，無真實資料可驗。

**B6. 觀測筆數門檻。** 既有研究說 <10 筆不可用。VORD／Spread 類指標的
共同日期交集會讓有效筆數**比單腿更少**（兩腿都要有值），門檻應該更嚴，
但本輪未量化該嚴到哪。

**B7. Strangle 分開報 `σ_ATM` 與 `BF` 兩個 percentile。** 資訊量更高，
但違反「一個 strategy 一個數字」——**這是需求方的裁示點，不是研究發現。**

**B8. Earnings window 汙染。** 有論證、無量測，對個股可能很大。

**B9. 財報／事件窗與 §6.3 的統一版 `M_VORD`。** 見 §6.3 的取捨表，
需求方裁示。

### §C. Do not use（看似直覺、其實量錯東西）

| 候選 | 否決理由 |
|---|---|
| **`Sell IV − Buy IV` 的 percentile** | 對 level 完全失明（0.0% vs package +59.9%）；對 skew 符號相反；+30.6%/年機械漂移 |
| **Ĝ 作為**唯一**主 percentile** | 對 package 貴賤符號吻合 0/4；÷ATM 不移除 roll-down（+30.8%） |
| **裸 Debit ÷ Width 的 percentile** | 自我指涉（同時是價格與機率，沒有價格 vs 價值的楔子）；被 moneyness 主宰（曲面凍結、spot +25% ⇒ **+315.3%**） |
| **固定 delta 重錨定的 D/W percentile** | r 汙染 −18.1%（÷DF 後仍 −14.0%）、q 汙染 +28.7%，與訊號同量級 |
| **net volatility／單一「Spread IV」／單一「Strangle IV」** | skew 下 ill-posed；真實 TLT 部位解出 **−0.74 vol 點**，1% vega 擾動跳 0.41 點 |
| **vega-weighted 合成 percentile** | 分母 `ν_b − ν_s` 穿零變號 |
| **fair-value／SAS residual 的歷史 percentile** | LEAPS tenor 上**數學上**不可得（`L ≥ D+T` vs 39 個月上限）；日噪音 ≥ 訊號 |
| **`IV − realized vol`（含 straddle）** | 量的是 variance risk premium 不是錯價；RV 在決策當下不可知，用 trailing RV 代替是偷換統計量。⚠ delta-hedged straddle 是例外，直覺有一半對，須說明不可揮手帶過 |
| **標的層級 IV Rank 作為 vertical 主指標** | 其理由（net vega 小一個量級）在本產品幾何下不成立（W=40 ⇒ **92.3%**）；tenor 錯配 |
| **裸價格／裸 credit 的 percentile（任何結構）** | 隨 spot、寬度、√T 縮放；同一標的的兩個日期之間都不可比 |
| **`credit / width` 不除以 DF** | 1.9pp 單調利率假象——恰好在利率有趨勢時製造假 regime shift |
| **固定履約價追蹤任何 wing 結構** | 產出的是一條**穿著估值標籤的 spot 部位序列**。在 1.20× spot 處，5% 的 spot 移動對指標的影響是 5 個 vol 點的 4.4 倍 |
| **all-call 或 all-put 的 butterfly 建構** | 一條深度 ITM 腿（即時 SPY 上 4.6–7.5% 買賣價差）讓雜訊帶超過整個訊號範圍；經濟上等價但髒 17–25× |
| **max-profit ÷ max-loss；`credit/(W−credit)` 報酬率** | 都是 `M` 的嚴格單調變換 ⇒ **percentile 逐筆相同**，零資訊增益，卻無界且在邊界附近病態。選它們嚴格劣於選 `M` |
| **`POP = 1 − credit/width` 的 percentile** | 是 C/W 的單調仿射變換，percentile 無新資訊，只多一層方向陷阱 |
| **券商的 "probability of profit"** | 通常是 `q = 0` 模型下的 `N(d2)`——本 repo 已確認 q=0 對自己的標的有實質誤差。`M` 是同一個數字的 model-free 版本 |
| **short strike delta 的 percentile** | 幾乎就是 spot 位置的 percentile |
| **同一張 OCC 合約自己的 raw IV percentile（單腿）** | DTE decay ＋ moneyness drift ＋ LEAPS 掛牌不滿一年 |
| **`0.8·S·σ√T` 當 straddle 指標** | 在 σ√T = 1.13（**正是本 repo 的 LEAPS 區間**）誤差 5.1%。用精確閉式或直接用價格 |
| **上述任何量的 z-score** | 肥尾＋強持續性；前輪已以同樣理由否決過 |

---

## §9. 未解決問題與 blocker

### 9.1 唯一的硬 blocker

**#111（vendor credential）仍未解除。** 後果：

- **本文所有歷史 percentile 的行為主張，都沒有用真實序列驗證過。**
  B1（VORD 的 ±21% 殘餘汙染）與 B2（`M` 的離散度是模型數字）兩條都
  直接卡在這裡。
- ledger OPEN #5（縱向 reconstruction 準確度，既有只驗過橫斷面——而
  **本文每一個 percentile 都是縱向的**）同樣卡在這裡。

### 9.2 其他未解決

1. **`M` vs `M_VORD` 的取捨**（§6.3）——先例 vs 汙染，需求方裁示點。
2. **回看窗口**（B3）——本輪找不到可辯護的預設值。
3. **Strangle 一個數字還是兩個**（B7）——產品裁示點。
4. **delta convention 驗證**（ledger OPEN #6）——一個實驗就能定，#111 blocked。
5. **「對殘差取 percentile」有無業界先例**（ledger OPEN #3）——前輪刻意
   找過沒找到，但當時與本輪的搜尋通道都是降級的，值得在通道恢復後再查
   一次，不必重新推導。
6. **八個 strategy 今天沒有 candidate generator**（§1.2）——本文對它們的
   裁定全部是前瞻性的。

### 9.3 本文自己的證據弱點（不藏）

- **Vertical spread／VORD 那條線：本輪一手原文 0 筆、官方文件 0 筆。**
  說服力來自數字可重跑與交叉驗證，不是文獻權威。
- **VORD 是本輪自創的構造**，找不到具名業界先例。若需求方的「符合機構
  實務」原則從嚴解釋，VORD 目前不滿足該條，`M`（有 Cboe 官方規格）
  才滿足。
- **§4 的 22.4× 訊噪比建立在模型掃描而非真實歷史離散度上**（B2）。

---

## §10. 重現步驟

本輪全部數值皆可重跑。引擎入口：

```bash
PYTHONPATH=/home/user/option-chaser /home/user/option-chaser/.venv/bin/python
```

- 定價與反解：`option_chaser/valuation.py` 的 `american_price()`／
  `merton_price()`／`implied_vol()`（Bjerksund–Stensland 1993）
- 現行出貨的 gap／percentile 邏輯：`option_chaser/ivspread.py`（105 行）、
  `option_chaser/ivtrend.py`（212 行）
- Vertical spread 實驗用的真實報價：`tests/fixtures/` 的 TLT LEAPS
  fixture（S=84.52／DTE 882）

§3.4 的貼現因子計算（主 session 親自執行）：

```python
import math
T = 882/365.0
df3, df5 = math.exp(-0.03*T), math.exp(-0.05*T)          # 0.93007, 0.88619
m = (1 - 0.181) / (df5/df3) - 1                          # -0.1405
```

外部一手資料的取得通道（§1.1）：`curl` 到 `cdn.cboe.com`
（`VIX_History.csv` 9,258 筆／`SKEW_History.csv` 9,213 筆／
`VVIX_History.csv` 5,090 筆／即時 SPY 全鏈 13,288 張合約）、
`arxiv.org`（Vanna-Volga arXiv:0904.1074、Talponen–Viitasaari
arXiv:1401.6383）。**`WebFetch` 被擋，`curl` 不被擋。**

⚠ 三條研究線的完整 findings（ledger 821 行／verticals 866 行／
wings 901 行）與其實驗腳本產生於本 session 的 scratchpad，**會隨
session 消失**。本文已把全部關鍵數字、實驗設定與裁定內化，不依賴那些
檔案存活；但若需要逐行複查原始推導，需要重跑。

---

## §11. 本輪範圍聲明

**未做**（委託明文禁止）：未設計 Dashboard／UI、未寫 production code、
未開 implementation ticket、未修改 percentile 演算法、未重新研究已
ANSWERED 的問題、未為了「統一」而強迫不同 strategy 共用 valuation
formula（§4.1 的共用是 no-arbitrage 的結果，不是為整齊而湊）、未擴張到
liquidity／risk／capital efficiency 等其他指標。

**本輪不進 `/to-spec`。** 等需求方審閱、對 §6.3（`M` vs `M_VORD`）、
B3（回看窗口）、B7（strangle 一個還是兩個數字）三個裁示點給出方向後，
才進入下一階段。
