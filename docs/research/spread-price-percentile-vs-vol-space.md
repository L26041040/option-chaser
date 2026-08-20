# Call Spread「常數結構價格」的歷史 percentile——price 空間 vs vol 空間

研究日期：2026-08-08。本文是 `candidate-iv-relative-value.md`（同日，下稱
「方案二研究」）的**補遺，不是重寫**：方案二研究已收斂出 vol 空間的
normalized skew 序列 `Ĝ = (σ(Δ_s)−σ(Δ_b))/σ_ATM` 之 1Y percentile
（其 §12.2），本文回答該輪懸而未決的正交問題——**「這種 call spread
結構的成本，位於自己歷史的什麼位置」能不能、該不該直接在 price 空間做**
（固定 tenor×delta 座標、每天 re-anchor 的 call spread 成本序列取
percentile，例如「25Δ/10Δ、6 個月 call spread 的成本佔 spot 的比例，
今天在過去兩年的第 80 百分位」），還是一律折回 IV／skew 空間。

**範圍界線**：不重推 vol 空間方法論（方案二研究已完成）；不做 vendor
最終選型（`historical-options-iv-data-sources.md` 保留給需求方）；
固定「合約」的成本走勢（V9 `spread_cost_history()`）已出貨且
`iv-relative-history-methodology.md` §4.d 已判定其定位，本文只在對照時
引用，不重評。本文不施工、不替需求方拍板，結論段直接服務 G1 裁示。

## 0. 研究方法與資料品質聲明

- **本輪查證通道**：沙箱 WebFetch 對絕大多數外部網域回 403（與前幾輪
  `EGRESS_BLOCKED` 同型；`raw.githubusercontent.com` 例外但本輪無需
  動用），因此**本文所有外部引用均為搜尋引擎索引轉述**，未逐字核對
  原文。沿用 `option-strategy-report-conventions.md` §7 的標記體系：
  〔官方・索引轉述〕＝發布者官方頁面／PDF 經索引摘錄；
  〔二手・索引轉述〕＝第三方整理；〔檢索性結論〕＝absence of
  evidence，不能排除漏檢。本文**沒有任何一項〔一手・逐字〕**——與
  方案二研究（取得三份一手 PDF）不同，這是本輪的誠實現狀。
- **數值段（§4.2）全部為本 repo `option_chaser/valuation.py` 引擎
  實算**（stdlib、可重現、重現步驟附上），不依賴外部轉述。
- 逐節標注每項先例是「一手驗證」還是「轉述」；未能查證事項集中 §7。

## 目錄

- §1 結論摘要（先行）
- §2 問題界定：price 空間指標的精確定義
- §3 先例調查：desk／vendor／結構性產品三條線
- §4 取捨：price 空間相對 vol 空間多答什麼、少答什麼（含引擎量化）
- §5 資料需求：「不自存全鏈」硬約束下的最小需求與接縫
- §6 判定：dominated——理由與唯一的低成本例外形態
- §7 查證限制
- §8 明確不涵蓋
- §9 來源清單

## 1. 結論摘要（先行）

1. **先例：有，但形態全部不是「per-candidate 座標的 percentile 指標」。**
   專業市場確實直接在 price 空間追蹤常數結構成本，可查證的三種形態：
   (a) sell-side「hedging cost monitor」型——固定座標結構的成本
   （% of spot）對照歷史，GS 衍生品研究的 put spread collar 篩選明文
   用「low prices compared with history」語言（§3.1）；(b) 「解出
   participation／strike 的對偶價格」型——CSFB Fear Barometer（賣
   10% OTM call 能買到多 OTM 的 put）、Cboe CLLZ 的逐月解出 call
   strike、JHEQX collar 的零成本 call strike 史、defined outcome ETF
   每期 reset 的 cap 水位史（§3.2–3.3）；(c) premium capture 序列型
   ——BXM 逐月權利金（% of underlying）序列（§3.1.3）。**三種全是
   index／基金層級的標準座標結構，沒有找到任何 desk 或 vendor 把
   「使用者自選兩腿的常數結構價格 percentile」做成常設指標**
   〔檢索性結論〕。
2. **Vendor：無現成「constant-structure spread price 序列」產品。**
   17 家名單（`historical-options-iv-data-sources.md`）中沒有一家把
   它做成可直接查的序列端點；最接近的是 **ORATS Backtest API**——
   可對「固定 DTE×delta 進場」的 vertical spread 逐日重建歷史進場價
   （2007 起），且其參數體系原生就有「spread 價格佔 strike 寬度比例」
   這個座標——證明「常數結構歷史進場價」在 vendor 端**可被生成**，
   但形態是回測引擎不是指標序列，且是另一份訂閱（§3.4）。
3. **取捨判定：price 空間被方案二 dominated，不值得做為核心指標。**
   price 空間唯一多答的是「level＋skew＋carry＋forward 合回一個、
   單位是錢」——但「今天實際要付多少錢」本產品已由最差成交 debit
   直接顯示，「這組合約的成本走勢」已由 V9 出貨；re-anchor 後的
   常數結構價格 percentile 相對 Ĝ percentile 的**增量資訊恰好就是
   利率／forward／股息成分**，而這些對「結構貴不貴」是汙染不是訊號。
   引擎實算（§4.2）：本產品 TLT LEAPS 實例中，利率動 2 個百分點使
   spread 理論價動 **+26%**，等效於 gap 動約 **4 個 vol 點**——兩年
   percentile 窗內一次 Fed 週期就足以把 percentile 從中位推到高位，
   與 vol 結構零關係。defined outcome ETF 的 cap 史提供了公開的
   實證：2022–2023 cap 創新高，發行方自己的歸因就是「利率升＋vol 高」
   ——price 空間序列被利率主導是業界自己承認的現象（§3.3）。
4. **資料需求結論：不必整條 smile，但嚴格不少於方案二。**在「不自存
   全鏈」硬約束下，price 空間序列的唯一可行路徑是「用方案二同一組
   座標點 IV ＋ spot／利率／股息歷史，經 BS 重建結構價」——vendor
   資料需求與方案二相同（每天 2–3 個座標點），但**額外**需要：
   (a) 歷史利率曲線（repo 已有現成口徑）；(b) 歷史股息率——本 repo
   引擎是 q=0 口徑，方案二研究 §7.4 已實測它在 TLT LEAPS 上把 call
   理論值高估近一倍，**重建出的價格序列會把股息模型誤差整段燒進
   percentile**；(c) 直接查 per-contract 報價序列（Market Data App
   形狀）對 re-anchor 序列**不適用**——每天 re-strike 後兩腿是不同
   合約，逐日對齊等於變相要每天的鏈或 surface。三步驗證（Market
   Data App → Alpha Vantage → ORATS）無需為本題擴充（§5）。
5. **G1 裁示建議**：price 空間 percentile **不做**；vol 空間（方案二
   Ĝ）已足夠回答「這組結構相對歷史貴不貴」，且是唯一把利率／股息
   汙染排除在外的定義。若需求方仍想看「錢的單位」的歷史脈絡，唯一
   值得考慮的低成本形態是：用方案二已付費取得的同一組 IV 點順手
   重建「% of spot 成本」當**展示列**（不另掛 percentile、標注含
   利率成分），零新增資料源（§6.3）。

## 2. 問題界定：price 空間指標的精確定義

先把要評估的對象釘死，避免與已出貨物混淆。三個相鄰但不同的東西：

| # | 對象 | 座標 | 單位 | 現狀 |
|---|---|---|---|---|
| P0 | **固定合約**的 debit 走勢 | 兩張 OCC 合約 | 錢 | 已出貨（V9 `spread_cost_history()`）；§4.d 已判定「作為 IV 判讀是錯誤標籤」 |
| P1 | **常數結構價格 percentile**（本文主題） | 固定 (tenor, Δ_b, Δ_s)，每天 re-anchor／re-strike | 錢（÷spot 或 ÷strike 寬） | 未做，本文評估 |
| V2 | 方案二 normalized skew Ĝ percentile | 同 P1 的座標 | vol 點（無因次） | 方案二研究 §12.2，待裁示 |

P1 的定義（與需求方例子一致）：每個歷史交易日 t，在當天 surface 上
找到 tenor=T*、delta=Δ_b 與 Δ_s 的兩個 strike，計算該 bull call spread
的成本 `P_t`（正規化為 `P_t / S_t` 或 `P_t / (K_s−K_b)`），得一條
永續序列；今天的值取 candidate 實際座標，報它在序列中的 percentile。
**re-anchor 機制與 V2 完全同款**（`iv-relative-history-methodology.md`
§3.3、方案二研究 §9.1）——P1 與 V2 的差異只在「取兩點之後合成什麼」：
V2 合成 IV 差（÷ATM），P1 合成 BS 價格（把 level、skew、T、r、q、
forward 全部捲進一個錢數）。本文的問題因此可以精確化為：**「多捲進
r、q、forward 換到『單位是錢』，是划算的交易嗎？」**

## 3. 先例調查：desk／vendor／結構性產品三條線

### 3.1 Desk／sell-side：price 空間追蹤存在，形態是「hedging cost monitor」

**3.1.1 GS 衍生品研究的結構價格篩選〔二手・索引轉述〕。**公開報導
轉述的 GS 衍生品研究工作流：對多市場的 put spread collar 篩選
「**low prices compared with history** 且 payout ratio > 8x」的結構、
「哪些 call 要賣掉才能 fund 這個 put spread 的成本」、「call strike
相對過去報酬分佈偏高」等——**結構的『價格相對自身歷史』是 sell-side
衍生品研究的成文篩選語言**，且座標是標準化結構（固定 %OTM 或
delta、固定 tenor），不是任意 bespoke 兩腿。這是本題「先例：有」的
最直接證據；但注意它是研究報告裡的橫斷面篩選（跨市場找便宜結構），
不是常設的 per-structure percentile 指標欄位。

**3.1.2 「cost of protection as % of spot」慣例〔二手・索引轉述〕。**
對沖成本以「佔 spot／部位價值百分比」表達並跨期追蹤，是散見於
broker 教材與機構白皮書的通用語言（Schwab、Global X collar 白皮書
等）。%-of-spot 正規化消掉 spot 量級，是 price 空間序列能成立的
前提——P1 定義照抄這個慣例。

**3.1.3 Premium capture 序列：BXM〔官方・索引轉述〕。**Cboe BXM
（S&P 500 BuyWrite）逐月賣一個月 ATM call，Ibbotson 對 1988–2004 的
case study 報出**月均權利金 1.69% of underlying** 的序列統計——
「同一常數結構（1M ATM call）的權利金佔比逐月序列」在指數層級已
存在近四十年。systematic overwriting 的 premium capture 追蹤是
price 空間常數結構序列的最老先例；但它是 index 產品的副產物
（收益歸因用），不是「進場貴賤判讀」指標。

### 3.2 「對偶價格」家族：解出 strike／participation 的 price 空間指標

price 空間追蹤在專業端最成熟的形態，其實不是「固定結構報價格」，
而是它的**對偶**——「固定價格（常為零成本）解出結構參數」：

- **Credit Suisse Fear Barometer（CSFB）〔二手・索引轉述〕**：
  賣 3 個月 10% OTM SPX call，用權利金買 3 個月 put——指數值＝
  該 put 能買到的 %OTM 深度。這是**純 price 空間**的常數結構指標
  （整條計算只有價格相等，一個 vol 都不出現），每天 re-anchor、
  有長期歷史、被媒體當 sentiment 序列判讀（「歷史新高」語言＝
  percentile 思維）。**它證明 price 空間常數結構序列可以做成
  嚴肅的每日指標**——但也示範了代價：CSFB 的判讀爭議正是「它的
  水位混合了 skew、level 與供需，動因不可歸因」（宏觀部落格對
  「為何 fear 如此穩定」的討論即此困惑的公開版）。
- **Cboe CLLZ／CLLR〔官方・索引轉述〕**：Zero-Cost Put Spread
  Collar 指數，每月把 2.5%–5% put spread 的成本用「解出 strike 的
  call」對沖到零——被解出的 call strike 逐月序列就是一條常數結構
  對偶價格史（官方 methodology PDF 存在，本輪僅索引轉述）。
- **JHEQX（JPMorgan Hedged Equity）〔二手・索引轉述〕**：每季末
  reset 的 put spread collar（買 95% put／賣 80% put／賣 call 湊零
  成本），被解出的 call strike「歷史上平均落在 spot 上方 3.5%–5.5%」
  ——市場評論者持續追蹤這個 strike 水位當作「結構定價貴賤」的
  讀數。基金規模與 reset 的市場影響使它成為被第三方（SpotGamma 等）
  **反向追蹤**最密的常數結構價格史。

### 3.3 結構性產品線：defined outcome ETF 的 cap 水位史（需求方點名深挖）

這條線索確實是「常數結構價格史」的最公開、最長、可逐期查證的樣本：

- **機制**：Innovator／First Trust（FT Vest）等發行的 buffer ETF，
  每期（月或年）reset 一次，結構固定（SPY exposure＋固定 buffer
  9%/15%/30%＋1 年 tenor），**cap 是被解出的參數**——使整個選擇權
  包在 reset 日淨成本為零（扣費前）的上限水位。cap 因此正是 §3.2
  對偶家族的 ETF 版：**同構結構、每期 re-anchor、解出的價格對偶量、
  完整公開史**。
- **公開性**：每期 cap 以新聞稿＋prospectus supplement 形式發佈
  （GlobeNewswire 存檔、SEC 497 文件可逐期回查）；Innovator 官網有
  逐基金的 cap／buffer 現值工具〔官方・索引轉述〕。**「常數結構
  價格史」在這裡不但存在，還是受 SEC 揭露義務保障的公開時間序列**
  ——這是三條線裡先例最扎實的。
- **對本題的關鍵教訓（歸因問題的公開實證）**：2023 年期 cap 創
  歷史新高，發行方自己的說法就是「**vol 維持高檔＋利率上升**使
  選擇權組合更值錢、cap 更高」〔官方新聞稿・索引轉述〕；第三方
  educator 文章逐項列出 cap 的決定因子＝IV、利率、股息〔二手〕。
  換句話說：**業界自己承認 cap 史（price 空間序列）的大部分變異
  來自利率與 vol level 的混合**，把它當「這個結構的 vol 定價貴賤」
  讀數用，正是本文 §4 要量化的汙染。2022–2024 的 cap 上行主因是
  Fed 升息——若對 cap 序列取 percentile 來判讀「現在進場划不划算」，
  會把利率環境誤讀成結構定價環境。

### 3.4 Vendor：無現成序列產品；ORATS Backtester 是最接近的生成器

對照 `historical-options-iv-data-sources.md` 的 17 家名單與交集四家
（ORATS／Market Data App／Alpha Vantage／EODHD），加上本票點名的
IVolatility、SpotGamma、Cboe DataShop：

- **沒有任何一家提供「constant-structure spread price」的現成序列
  端點**（例如「給我 TLT 25Δ/10Δ、180 天 call spread 成本的兩年
  日序列」一個 GET 搞定）〔檢索性結論，§7 第 4 項〕。vendor 的
  歷史序列產品一律停在**單一座標點的 IV**（ORATS constant-maturity
  delta-level IV、IVolatility IV Index/surface）或**單一合約的報價**
  （Market Data App from/to）層級；「兩點合成一個結構價」這步沒有
  人替你做。
- **最接近的存在：ORATS Backtest API**〔官方・索引轉述〕——REST
  提交策略定義（vertical spread、進場條件固定 DTE×delta、2007 起）
  逐日重建歷史進場價與損益；參數體系原生支援「spread 價格佔
  strike 寬度比例」「option 價格÷股價」這類 price 空間座標。
  **意義**：常數結構歷史進場價在 vendor 端「可被生成」已被產品化
  證明，需求不是空想；**限制**：它是回測引擎（一次性任務、輸出
  交易列表），不是可按需查的指標序列，且 Backtest API 是 Data API
  之外的另一份訂閱（價格轉述矛盾問題同資料源研究 §7）。
- **SpotGamma**：其公開文獻是策略教學與 JPM collar 反向追蹤／
  dealer positioning 分析，無 per-structure 歷史價格序列產品
  〔檢索性結論〕。**Cboe DataShop**：bulk 檔案（資料源研究 §4.2
  已判 ❌ bulk），不因本題翻案。

### 3.5 先例調查小結

| 形態 | 實例 | 座標 | 是否 percentile 化 | 對 P1 的支持度 |
|---|---|---|---|---|
| Hedging cost monitor | GS put spread collar 篩選 | 標準結構、跨市場 | 「low vs history」定性 | 中——證明 price vs history 是成文語言 |
| 對偶（解 strike/cap） | CSFB、CLLZ、JHEQX、buffer ETF cap 史 | 固定結構逐期 re-anchor | 「歷史新高」語言常見 | 高——序列存在且公開；但歸因困難是公認代價 |
| Premium capture | BXM 月權利金 % | 1M ATM、指數層級 | 統計摘要 | 低——歸因用途，非判讀指標 |
| Vendor 序列產品 | （無） | — | — | 反面——需求存在但無人做成端點 |

**共同點**：所有先例都活在**指數／基金層級的標準座標**（3M 10% OTM、
1M ATM、年期 buffer 結構），服務的是宏觀敘事（「對沖現在貴嗎」）；
**沒有一個把 price 空間 percentile 綁到使用者自選的 bespoke 兩腿上**。
專業端要判讀「這組具體 legs 的定價相對歷史」時，語言一律切回 vol／
skew 空間（方案二研究 §3 的三層拆解、Natenberg／Sinclair／SAS 的
先例鏈）——本輪檢索沒有找到反例。

## 4. 取捨：price 空間多答什麼、少答什麼

### 4.1 多答的（誠實列舉）

1. **單位是錢**：P1 的讀數就是「這種結構今天要付的成本」，使用者
   零翻譯成本；Ĝ 需要一句定義文案（方案二研究 §12.2 已自認）。
2. **全包**：level＋skew＋carry＋forward＋discounting 合回一個數＝
   你實際要掏的錢。任何單維 vol 指標都只覆蓋其中一兩維。
3. **與付錢體驗同構**：若使用者的問題是「同樣形狀的票，過去兩年
   什麼時候買最便宜」，P1 是字面直答。

但注意本產品的既有出貨已經覆蓋了 1 和 3 的大半：**今天實際要付的
錢**＝最差成交口徑 debit（A14.2，主數字）；**這組合約的成本走勢**＝
V9 走勢圖（P0）。P1 相對它們的增量只剩「re-anchor 消漂移＋percentile
定位」——而這正是它與 V2 重疊的部分。

### 4.2 少答的（引擎量化）

**4.2.1 無法歸因。**P1 動了，分不出是 level、skew、利率還是 forward
（CSFB 的公開判讀爭議、cap 史的利率主導，§3.2–3.3）。本產品 §0 約束
「只呈現事實性數字」還撐得住，但「percentile 高＝結構貴」這個使用者
必然會做的推論，在 P1 上是不成立的——見下。

**4.2.2 利率汙染的量級（引擎實算，可重現）。**用本 repo 引擎、
方案二研究 §11 的同一 TLT 實例（S=84.52，K 90/130，IV 12%/18%，
T=882/365）：

```python
# PYTHONPATH=. .venv/bin/python
from option_chaser.valuation import bs_call
S=84.52; T=882/365
def spread(r): return bs_call(S,90,T,r,0.12)-bs_call(S,130,T,r,0.18)
spread(0.03), spread(0.04), spread(0.05)
# → 5.33, 6.10, 6.92：利率 3%→5% 使結構價 +26.0%
# 6 個月同 strikes 版本：1.311→1.569，+17.9%
```

- 利率動 2 個百分點（一次尋常的 Fed 週期，兩年 percentile 窗內完全
  可能發生）使 LEAPS 結構價**+26%**——以方案二研究 §11.2 的
  `dV/dG = −0.403/pt` 換算，等效於 gap 動約 **4 個 vol 點**（其 TLT
  實例的 raw gap 總共才 6 pts）。**利率成分單獨就能把 P1 的
  percentile 從中位推到高位**，而 vol 結構一動未動。
- 長天期越嚴重：同一利率位移在 6 個月結構上是 +17.9%、在 882 天
  結構上是 +26%——本產品主戰場恰是 LEAPS，2026 vs 2028 到期的
  DF／forward 差異正是需求方在票上點名的痛點，引擎數字證實它是
  一階效應不是潔癖。
- 對照組：**V2（Ĝ）對 r 與 q 的敏感度恆為零**——它只消費市場 IV，
  分子分母都不含 discounting。這就是「折回 vol 空間」在數學上
  買到的東西。

**4.2.3 股息／模型汙染（本產品特有的坑）。**P1 的歷史值必須「重建」
（§5.1），重建就要定價模型。方案二研究 §7.4 已實測：本 repo q=0
引擎對 TLT LEAPS call 的理論值高估近一倍（7.68 vs 市場 3.95）——
TLT 配息率與利率同量級，**用現有引擎重建的 P1 序列整段是股利假象**；
要修就得引入歷史股息率口徑（新資料需求＋新模型參數），而 V2 完全
沒有這個問題。

**4.2.4 percentile 窗內的結構性趨勢。**P1 序列在利率有趨勢的年代
（2022–2024 升息、其後降息）帶著單向漂移，percentile 的「歷史分佈」
不平穩——與 raw gap 的 √t 機械漂移（方案二研究 §4.2.1）同型的病，
只是汙染源換成利率。buffer ETF cap 史 2022–2023 的單邊走高（§3.3）
就是這個病的公開病歷。

### 4.3 取捨結論

P1 多答的三項中，兩項已被既有出貨覆蓋；唯一真正的增量（把 carry／
forward 也捲進來）對「這組結構的 vol 定價相對歷史」恰好是汙染。
P1 少答的四項（歸因、利率、股息模型、非平穩窗）每一項都有量化或
公開實證。**在本產品的問題定義下，P1 被 V2 dominated**；先例調查
（§3.5）也顯示專業端在 per-structure 判讀場景同樣折回 vol 空間，
price 空間序列只活在宏觀敘事與對偶（零成本解參數）場景。

## 5. 資料需求：「不自存全鏈」硬約束下的最小需求

（需求方 2026-08-07 裁示：不自存 option chain、資料庫負擔最低。）

### 5.1 P1 的唯一可行路徑＝「座標點 IV＋重建」，不是「直接查價」

先排除直覺路徑：**per-contract 歷史報價序列（Market Data App
from/to 形狀）對 P1 不適用**。P1 每天 re-strike 到當天的 Δ 座標，
歷史上每一天的兩腿是**不同合約**——要知道「那天的 25Δ/10Δ 是哪兩個
strike」本身就需要那天的 surface（或全鏈＋delta），然後才能查那
兩張合約的價。直接查價路徑退化成「每天一次全鏈查詢」（Alpha
Vantage `HISTORICAL_OPTIONS` 形狀，N 天 N 次呼叫、每次整鏈），與
「資料庫負擔最低」的精神相悖，也遠重於方案二。

可行路徑只剩重建：對每個歷史日取 (T*, Δ_b)、(T*, Δ_s) 兩點 IV
（**與方案二完全同一組查詢**，ORATS constant-maturity delta-level
IV 形狀），加上當日 spot、利率、股息率，經含 q 的 BS 重建結構價。
結論：**P1 不需要整條 smile**——這點與方案二相同；但它嚴格**多**
需要三樣東西：

| 需求 | V2（方案二） | P1 | 備註 |
|---|---|---|---|
| 座標點 IV 歷史（2–3 點/日） | 需要 | 需要 | 同一組 vendor 查詢，量級 KB 級 |
| ATM IV（normalize 用） | 需要 | 不需要 | — |
| spot 歷史 | 不需要 | 需要 | 免費易得（既有 yfinance/Cboe 口徑） |
| 歷史利率曲線 | 不需要 | 需要 | repo 已有期限對齊利率口徑（T12），歷史化要擴充 |
| 歷史股息率 q | 不需要 | **需要** | 新資料源＋引擎新參數；不做則序列是股利假象（§4.2.3） |
| 定價引擎 | 純算術 | 含 q 的 BS（或美式修正） | V2 零模型、P1 有模型風險 |

**「恰好等於方案二已估的需求」的答案是：vendor 面恰好相等，總量
嚴格更重**——多出的部分全在自家（利率歷史化、q 口徑、引擎擴充），
而這些恰恰是 §4.2 論證的汙染源本身：P1 的額外成本花在把噪音算對。

### 5.2 與三步驗證（Market Data App → Alpha Vantage → ORATS）的接縫

資料源研究 §5.2 的驗證優先序**無需為 P1 擴充或重排**：

1. **Market Data App**（第一步）：驗證的是 per-contract 序列——
   服務 P0（V9 疊合）與方案三（raw gap 走勢），與 P1 無關（上述
   re-strike 錯位）。
2. **Alpha Vantage**（第二步）：指定日全鏈——若 P1 走「直接查價」
   路徑會用到它，但該路徑已在 §5.1 判定不成立；維持原定位（備援
   與抽查用）。
3. **ORATS**（第三步）：constant-maturity delta-level IV 序列——
   同時服務 V2 與 P1 的重建路徑；若日後真要 P1，唯一新增的驗證
   項目是「Backtest API 能否當一次性生成器」（§3.4），屬另一份
   訂閱的獨立決策，不進本輪三步。
4. LEAPS tenor 缺口（>365/730 天）對 P1 與 V2 完全同型（方案二
   研究 §9.4 的三條路線通用），P1 不增不減。

## 6. 判定（供 G1 裁示）

### 6.1 price 空間 percentile（P1）：不建議做

- **先例面**：price 空間常數結構序列在專業端存在（§3），但全部
  服務宏觀敘事或零成本對偶場景；per-candidate 判讀場景專業端
  一律用 vol／skew 語言，P1 形態無先例〔檢索性結論〕。
- **資訊面**：P1 = V2 的資訊 ＋ 利率/股息/forward 成分；後者對
  本產品的問題是汙染（§4.2 引擎量化：2pp 利率 ≈ 4 vol pts 等效，
  LEAPS 上是一階效應），且業界自己的 cap 史歸因公開承認這一點。
- **成本面**：vendor 查詢與 V2 相同，但自家工程嚴格更重（歷史
  利率＋q 口徑＋含 q 引擎），多花的每一分工都花在把噪音算對。
- **既有出貨面**：P1 想answer的「錢的體感」已由最差成交 debit
  （今天）＋V9 走勢（這組合約的歷史）覆蓋大半。

### 6.2 vol 空間（方案二 Ĝ）為什麼已足夠

Ĝ 序列在同一組座標、同一份 vendor 資料上，把 P1 的四項汙染全部
排除（r/q 零敏感、÷ATM 消 level、re-anchor 消漂移），直答「這組
結構的 vol 定價相對歷史」；使用者要的「付錢單位」由既有 debit
主數字承擔——兩個數字各司其職，正是 `iv-relative-history-
methodology.md` §4.d 早已裁定的「成本走勢與 IV 判讀必須分清楚」
在 percentile 層的重演。

### 6.3 唯一值得保留的低成本例外形態（若需求方想要「錢的歷史脈絡」）

若裁示後仍想在 card 上看到 price 空間的歷史脈絡，**不要**建 P1
序列；用方案二已取得的同一組 IV 點順手重建「本結構今日成本佔
spot %」一個**當日數字**（或與 V9 固定合約走勢並排），明確標注
「含利率與股息成分」——零新增資料源、零 percentile 誤導。這是
先例中 hedging cost monitor 語言（§3.1.2）能誠實搬進本產品的
最大範圍。

## 7. 查證限制（未能查證的事項）

1. **全文無一手逐字來源**（§0）：GS 篩選語言、CSFB 公式、CLLZ
   methodology、JHEQX strike 慣例、BXM 1.69% 統計、Innovator cap
   歸因、ORATS Backtest 參數體系——全部為索引轉述，未核對原件。
2. **CSFB 的精確計算規則**（call 的 %OTM 定義、結算口徑、是否仍
   在 CS 併入 UBS 後維護）未查證；其指數現況（2023 後）不明。
3. **JHEQX「call strike 平均 3.5%–5.5%」**為第三方（MenthorQ）
   轉述，非 JPM 官方揭露口徑。
4. **「無 vendor 提供 constant-structure spread price 序列端點」
   是檢索性結論**（absence of evidence）；尤其 SpiderRock／
   Bloomberg（VCA 之外的函數）／IVolatility cloud API 的完整端點
   目錄無法在沙箱枚舉，不能排除機構級產品有近似物。
5. **ORATS Backtest API 的訂閱層級與價格**未查證（資料源研究 §7
   的 ORATS 價格矛盾同題）。
6. **Nations TailDex/SkewDex 的精確公式**未查證：TDEX「量 3σ OTM
   put 的價格」的正規化方式（% of spot？）索引轉述不一致，本文
   僅將其列為 price 空間指數存在的旁證，不依賴其公式細節。
7. **§4.2 的利率汙染數字是模型內推演**：q=0 BS、IV 凍結、只動 r
   ——真實序列中 r 與 IV 相關（利率與 vol 環境共動），實際汙染
   佔比可能更高或更低；數字僅示意量級與方向（與方案二研究 §15
   第 12 項同型留保）。
8. **buffer ETF cap 歸因**：「2023 cap 創高主因利率＋vol」取自
   發行方新聞稿與 educator 文章，未經獨立分解驗證。

## 8. 明確不涵蓋

- vol 空間方法論與四方案比較（方案二研究已完成，本文只引用）
- vendor 最終選型與價格核實（資料源研究保留給需求方）
- P0（V9 固定合約成本走勢）的重評——已出貨、定位已裁定
- 零成本 collar／對偶指標要不要做成本產品功能（§3.2 家族只作
  先例引用；若需求方對「解出 cap」形態有興趣屬新題，另開票）
- UI 欄位設計（§6.3 只到「一個當日數字」的形態層）

## 9. 來源清單

**標記說明**：本文全部外部來源為〔官方・索引轉述〕或〔二手・索引
轉述〕（§0）；引擎實算與推導在正文逐處標明重現步驟。

Desk／sell-side 先例
- 〔二手・索引轉述〕[Yahoo Finance — Goldman Sachs options play to protect portfolios（put spread collar「low prices compared with history」篩選）](https://finance.yahoo.com/markets/options/articles/bullish-bets-surge-goldman-sachs-133000726.html)
- 〔二手・索引轉述〕[CNBC — Goldman's hedging strategy for a market drawdown (2025)](https://www.cnbc.com/2025/10/22/goldmans-hedging-strategy-for-a-market-drawdown-buy-puts-in-weak-stocks.html)
- 〔二手・索引轉述〕[Global X — Options Collar Strategies as a Risk Management Tool](https://www.globalxetfs.com/articles/options-collar-strategies-as-a-risk-management-tool)、[Charles Schwab — What Are Options Collars?](https://www.schwab.com/learn/story/what-are-options-collars)

對偶價格家族（CSFB／CLLZ／JHEQX）
- 〔二手・索引轉述〕[SurlyTrader — The Fear Barometer（CSFB 機制）](https://surlytrader.com/the-fear-barometer/)、[Yahoo Finance — Credit Suisse's own 'Fear Barometer'](https://finance.yahoo.com/news/credit-suisse-own-fear-barometer-135601834.html)、[Bloomberg — This Fear Gauge Just Hit an All-Time High (2016)](https://www.bloomberg.com/news/articles/2016-04-11/this-fear-gauge-just-hit-an-all-time-high)、[Disciplined Systematic Global Macro Views — CSFB Fear Barometer: Why is fear stable?](http://mrzepczynski.blogspot.com/2020/10/csfb-fear-barometer-why-is-fear-stable.html)
- 〔官方・索引轉述〕[Cboe Zero-Cost Put Spread Collar Indices Methodology (PDF)](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Zero-Cost_Put_Spread_Collar_Indices_Methodology.pdf)、[Cboe Collar Indices Methodology (PDF)](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Collar_Indices_Methodology.pdf)、[Cboe Insights — Hedging Downside Exposure with PPUT, CLL and CLLZ](https://www.cboe.com/insights/posts/benchmark-indices-series-hedging-downside-exposure-with-pput-cll-and-cllz-indices)
- 〔二手・索引轉述〕[MenthorQ — JP Morgan Collar Trade Explained（JHEQX 機制與 call strike 3.5–5.5% 慣例）](https://menthorq.com/guide/jp-morgan-collar-trade-explained/)、[SpotGamma Support — JPM Collar](https://support.spotgamma.com/hc/en-us/articles/12763513348243-JPM-Collar)

Premium capture
- 〔官方・索引轉述〕[Ibbotson — Case Study on BXM Buy-Write Options（月均權利金 1.69%）](https://cdn.cboe.com/resources/education/research_publications/IbbotsonAug30final.pdf)、[Cboe BuyWrite Indices Methodology (PDF)](https://cdn.cboe.com/api/global/us_indices/governance/BXM_Methodology.pdf)

Defined outcome ETF cap 史
- 〔官方・索引轉述〕[Innovator — Record Year…Publishes New Upside Caps for 2023（cap 創高的利率＋vol 歸因）](https://www.globenewswire.com/news-release/2023/01/03/2582203/0/en/Innovator-Announces-Record-Year-for-Defined-Outcome-ETFs-as-Bonds-and-Stocks-Declined-Together-Publishes-New-Upside-Caps-for-2023.html)、[Innovator — New Upside Cap Ranges for August Series (2020)](https://www.globenewswire.com/news-release/2020/07/27/2068111/0/en/Innovator-ETFs-Announces-New-Upside-Cap-Ranges-for-S-P-500-Buffer-ETFs.html)、[Innovator ETFs Trust Form 497（SEC，逐期 cap 揭露）](https://www.sec.gov/Archives/edgar/data/1415726/000101376225001675/ea0234921-07_497.htm)
- 〔二手・索引轉述〕[ETF.com — Innovator Buffer ETF Family Enters New Phase](https://www.etf.com/sections/daily-etf-watch/innovator-buffer-etf-family-enters-new-phase)、[Stuart Chaussee — What factors influence the upside cap level of Buffer ETFs](https://preservingwealth.com/what-factors-influence-the-upside-cap-level-of-buffer-etfs/)

Price 空間指數旁證
- 〔官方・索引轉述〕[Nations Indexes — About Our Indexes（TailDex／SkewDex）](https://nationsindexes.com/indexes/)

Vendor（constant-structure 生成能力）
- 〔官方・索引轉述〕[ORATS Backtest API Reference](https://docs.orats.io/backtest-api-guide/backtest.html)、[ORATS University — Custom backtesting（spread price % of width 參數）](https://orats.com/university/custom-backtesting)、[ORATS — Optimizing Options Backtests: DTE, Deltas…](https://orats.com/blog/optimizing-options-backtests-days-to-expiry-deltas-and-technical-indicators)、[IBKR Traders' Academy — ORATS Backtester](https://www.interactivebrokers.com/campus/trading-lessons/orats-backtester/)
- 〔官方・索引轉述〕[ORATS — Our Most Popular IV is Constant Maturity Implied Volatility](https://orats.com/blog/our-most-popular-iv-is-constant-maturity-implied-volatility.-how-we-calculate-it)

結構性產品背景
- 〔二手・索引轉述〕[SRP — History of structured products](https://www.structuredretailproducts.com/srp-academy/structured-products-history)、[LegalClarity — Structured Notes Explained](https://legalclarity.org/structured-notes-explained-components-payoffs-and-types/)

本 repo（引擎與既有研究）
- `option_chaser/valuation.py` —— `bs_call`（§4.2 利率敏感度實算）
- `docs/research/candidate-iv-relative-value.md` —— 方案二（Ĝ）定義
  §12.2、q=0 引擎警告 §7.4、TLT 實算 §11、re-anchor §9.1
- `docs/research/iv-relative-history-methodology.md` —— §3.3 座標
  取點、§4.d spread debit percentile 的既有裁定
- `docs/research/historical-options-iv-data-sources.md` —— vendor
  名單、交集四家、三步驗證 §5.2、硬約束界定 §2
- `store.spread_cost_history()`（V9／#57）—— P0 既有出貨
