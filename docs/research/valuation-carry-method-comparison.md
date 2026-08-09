# LEAPS 估值／Carry 處理方法比較：q=0 基準是否成立，以及備選方案

研究日期：2026-08-09（issue #110，決策 D1）。

**本文性質聲明（guardrail）**：本票只做方法比較、真實資料量化、驗收
測試與書面建議；**不修改 `option_chaser` 引擎既有行為、不修改 golden
fixtures、不修改契約樣本、不自行選定並鎖定最終模型**。任何「推薦」
字樣皆指需要需求方核准才會進入後續「鎖定並實作」票（#113）的建議，
不是本票已經做的變更。

**資料品質聲明**（沿用本 repo research 慣例）：

- **實測實證（一手，本地可重跑）**：§3、§5 的全部數字，由
  `tests/test_research_valuation_carry.py` 對 `tests/fixtures/`
  底下兩份真實資料計算，任何人／agent 皆可重跑覆核，見該檔案。
- **本 repo 既有研究引用**：§4 大量引用 `docs/research/
  spread-synthetic-parity-check.md`（R4／#99，真實 758 筆 Cboe 全鏈
  實算）與 `docs/research/risk-free-rate-for-bs.md`（T12-A，Treasury
  曲線口徑），兩者皆已完成且經過本票獨立覆核（§5），不是道聽塗說。
- **搜尋索引轉述**：教科書/學術結果的章節對應，未逐字核對原文，
  引用清單見 §7。

## 目錄

1. 摘要
2. 問題陳述：現行 q=0 基準在真實 LEAPS 資料上不成立
3. 真實資料量化：q=0 vs 股利殖利率調整（本票核心）
4. ETF 美式履約效應：為什麼不能直接假定 parity 導出的 forward 正確
5. 獨立覆核：Treasury par → continuous 近似的正確性
6. 方法比較總表
7. 書面建議
8. 引用清單

---

## 1. 摘要

- **現行基準（q=0，無股利調整）對真實 LEAPS 合約有可量化、非邊緣案例
  的失敗模式**：用 2026-07-17 真實 TLT 2028-12-15 到期 5 檔 LEAPS call
  報價實測，**3/5 檔的市場中價低於 q=0 模型自身在 sigma→0 時的理論
  下限**——不是擬合較差，是這組 carry 假設在數學上無法解釋這些真實
  報價，無論怎麼調 IV 都到不了（§3.1）。此結論在合理利率範圍內穩健：
  排除掉「其實是 r 抓錯」的對立假說（§3.1 表），三檔的臨界利率介於
  1.6%–3.2%，遠低於同期文件記錄的真實利率量級（~4%）。
- **不建議把 vanilla put-call parity（Method D）當成萃取股利/forward
  的方法**：本 repo 既有研究（`spread-synthetic-parity-check.md`）已用
  758 筆真實 Cboe 全鏈證明，美式 ETF options 的 parity 殘差主要成分是
  提前履約溢價（r=0 時殘差精確歸零），不是可以乾淨分離出股利效應的
  訊號；LEAPS 天期（DTE>365）此效應中位數達 +3.13% width（§4）。
- **本票量化了一個資料依賴更低、不會被提前履約溢價汙染的替代校準法
  （Method E：跨履約價 IV 一致性）**：只用同一到期日的同側（call）報價，
  找一個讓隱含波動率跨履約價最一致的股利殖利率——不需要外部資料源，
  用引擎本來就會抓到的同一批快照即可。經驗最佳擬合 q≈4.5% 時，5 檔
  合約全部可解，且四個價位相近的履約價之間隱含波動率離散度比低 q
  時明顯收斂（§3.2）；深度 OTM 那一檔（K=130）刻意排除在一致性判定
  外，因為它在任何 q 下都明顯偏離，是真實的波動率偏斜，不是 carry
  假設沒調對（§3.2 反面佐證）。
- **Treasury par→continuous 近似的既有結論獨立覆核通過**：用真實
  2026-08-04 Treasury 曲線＋自製半年配息 bootstrap，1M–3Y（本工具實際
  使用範圍）內與現行 `par_to_continuous` 直接近似公式的差距 <1bp，
  與既有研究文件（`risk-free-rate-for-bs.md`）的 0.52bp 結論幾乎完全
  吻合（§5）。
- **建議方向（需需求方核准）**：若要修正，採 Method B 的公式（Merton
  股利殖利率調整 BS）＋ Method E 的校準來源（同快照跨履約價擬合），
  不採 Method C（配息時間表預測，天期一長預測誤差比 q=0 本身還大）或
  Method D（parity 直接萃取，已知會被美式提前履約汙染）。這是**建議**，
  不是本票已鎖定的實作方向；且即使核准，仍是歐式近似加一個經驗校準的
  殖利率，不是完整美式定價模型，殘留誤差需要在使用者說明裡誠實揭露
  （沿用本 app 既有的「模型限制」自揭文化，見 `tlt_report.md` 尾註）。

---

## 2. 問題陳述：現行 q=0 基準在真實 LEAPS 資料上不成立

`option_chaser/valuation.py` 的 `bs_call`／`bs_put` 是標準無股利歐式
Black-Scholes：

```python
d1 = (ln(S/K) + (r + 0.5*sigma^2)*T) / (sigma*sqrt(T))
C  = S*N(d1) - K*e^{-rT}*N(d2)
```

沒有任何股利／配息項——這就是本票標題「q=0 基準」的來源，也是
`tlt_report.md`（本 repo 既有、真實產出的舊版 CLI 報告）尾註自己寫的
「模型限制: 無股利調整（q=0）」。`clamped_price()` 再疊加一個「美式
無套利下限」（模型價與內在價值取大者），但這只防止**低於內在價值**
的荒謬結果，不修正**提前履約權利本身的價值**，更完全不處理股利。

TLT（iShares 20+ Year Treasury Bond ETF）**逐月配息**，是本 app 從
一開始的主打標的（見 CLAUDE.md 專案紀錄區歷次 TLT 實測）。任何配息
標的的 q=0 定價，理論上都會系統性高估 call、低估 put，且誤差隨天期
複利放大——這正是本票要量化「放大到什麼程度」的地方。

---

## 3. 真實資料量化：q=0 vs 股利殖利率調整（本票核心）

**資料**：`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`——
5 檔真實 TLT 2028-12-15 到期 LEAPS call（K=79/80/85/90/130），逐位元
抄自本 repo 已提交的 `tlt_report.md`（該檔案是較早版本 CLI 對真實
yfinance 快照的輸出，git 歷史可查，不是本票新造的資料）。分析日
2026-07-17，TLT 現價 $84.52，T≈2.42 年。

**方法**：`scripts/research_valuation_methods.py` 的
`bs_call_with_yield`／`implied_vol_call`——標準 Merton 股利殖利率調整
BS，對每個候選 q，用市場中價（Bid/Ask 均值）反解隱含波動率。全部計算
可由 `tests/test_research_valuation_carry.py` 重跑覆核。

### 3.1 q=0 的可行性：不是擬合差，是數學上到不了

對每個履約價，q=0 模型在 sigma→0 時有一個理論下限
`floor = max(S - K*e^{-rT}, 0)`（`call_floor_price`）。若市場中價低於
這個下限，代表**不存在任何非負波動率能讓 q=0 模型重現這個市場價**：

| 履約價 | 市場中價 | q=0 下限（sigma→0） | 可行？ |
|---|---|---|---|
| K=85 | $5.775 | $7.351 | **不可行** |
| K=80 | $7.825 | $11.891 | **不可行** |
| K=79 | $8.525 | $12.799 | **不可行** |
| K=90 | $3.950 | $2.812 | 可行 |
| K=130 | $0.680 | $0.000 | 可行 |

**3/5 檔不可行**（`test_q0_baseline_cannot_price_several_real_leaps_calls`）。
這三檔的市場中價都**高於未貼現內在價值**（K=85 內在價值 $0、K=80 為
$4.52、K=79 為 $5.52，皆遠低於市場中價），排除了「報價本身荒謬／
陳舊」這個更基本的解釋——問題精確出在 q=0 這個 carry 假設上。

**對立假說覆核**：會不會其實是利率 r 抓錯，不是少了股利？對每個
不可行的履約價，反解出「q=0 恰好可行」的臨界利率：

| 履約價 | 臨界利率（q=0 可行的上限） |
|---|---|
| K=85 | 3.16% |
| K=80 | 1.75% |
| K=79 | 1.60% |

同期真實利率量級由 `docs/research/risk-free-rate-for-bs.md` §7 記錄
在案（2026-07 中旬 2Y ≈ 4.26%，第三方鏡像轉述但方向與量級可信）。
K=79／K=80 需要的臨界利率不到真實利率的一半，K=85 也明顯偏低——
「r 抓錯」不足以解釋這個落差，落差的方向（市場價系統性低於 q=0 模型
下限）與量級只有股利效應解釋得通
（`test_q0_infeasibility_survives_plausible_rate_recalibration`）。

### 3.2 股利殖利率調整：經驗最佳擬合與跨履約價一致性

**方法（Method E）**：不假設任何外部股利數字，直接用同一到期日、
同側（call）的多筆真實報價，找一個讓**跨履約價隱含波動率最一致**的
殖利率 q——理論依據是：同一到期日、相近價位的隱含波動率理論上該
相對一致，系統性偏離代表 forward／carry 假設錯了，不是波動率結構
本身的事。這個方法**只用引擎本來就會抓到的同一批快照**，不需要新增
任何外部資料依賴（trailing distribution yield API、配息時間表…）。

排除 K=130（深度 OTM，見下方反面佐證）後，四個價位相近的履約價
（K=79/80/85/90）在不同 q 下的隱含波動率離散度（母體標準差）：

| q | 離散度（vol pt） |
|---|---|
| 2.5% | 1.388 |
| 3.0% | 0.822 |
| 3.5% | 0.468 |
| **4.0%** | **0.231** |
| **4.5%** | **0.194**（最小） |
| 5.0% | 0.337 |
| 5.5% | 0.501 |
| 6.0% | 0.660 |

**q≈4.5% 是這份真實快照的經驗最佳擬合**，離散度在兩側都回升，形成
清楚的內部極小值——不是單調改善到某個邊界，是真的有一個「最一致」
的點。這個量級（4.5%）與同期文件記錄的無風險利率（~4%）相近、甚至
略高，跟「TLT 持有的是長天期公債、殖利率反映當時較高的長端利率
環境」這個常識性理解方向一致（僅供合理性交叉檢查，不是外部驗證）。

在此 q 下，**5 檔合約全部可解出正的隱含波動率**（q=0 只有 2/5 可解，
`test_dividend_yield_adjustment_resolves_all_five_contracts`），四檔
近端履約價的離散度比低 q（2.5%，四檔中已有兩檔在此之下仍不可行）時
明顯收斂
（`test_dividend_yield_adjustment_improves_cross_strike_iv_consistency`）。

**反面佐證（避免「挑資料」的嫌疑）**：K=130 就算用 q=4.5%，隱含波動率
仍比其餘四檔的最大值高出兩個以上百分點
（`test_deep_otm_strike_shows_larger_iv_dispersion_than_near_money_cluster`）
——這是真實的波動率偏斜（深度 OTM 選擇權常見現象），把它排除在
「跨履約價一致性」判定之外是對的，不是為了讓數字好看而挑資料。

### 3.3 侷限（誠實揭露，不誇大結論）

- **單一標的、單一快照**：只有一天的 TLT 快照，5 檔合約。q≈4.5% 是
  **這個時間點**的經驗擬合，不是「TLT 的股利殖利率就是 4.5%」這種
  可以直接寫死的常數——TLT 配息隨利率環境逐月變動，不同快照重跑這個
  校準大機率會得到不同的 q。這正是本票建議「每次分析用同快照重新
  校準」而非「寫死一個常數」的理由（見 §6、§7）。
- **只用 call，未涉及 put**：本節的量化不受
  `spread-synthetic-parity-check.md` 點名的「put 提前履約溢價汙染
  parity」影響（因為完全不用 put），但 call 本身的美式提前履約權利
  （雖然對 call 通常遠小於 put）仍是殘留、未拆分的誤差來源——回推出
  的 q 可能比「純股利效應」略有偏差，方向未定。
- **5 個履約價、扣掉 1 個離群值只剩 4 個**：離散度極小值的統計把握度
  在這個樣本數下有限，是「方向與量級合理」的證據，不是精確估計。

---

## 4. ETF 美式履約效應：為什麼不能直接假定 parity 導出的 forward 正確

AC 明文要求：「不得假定 parity 導出的 forward 天然正確」。本 repo
已有一份完整、用真實資料驗證過的研究直接回答這件事——
`docs/research/spread-synthetic-parity-check.md`（R4／#99，
2026-08-08），本節只摘要對 #110 有直接意義的結論，細節與引用見原文。

**核心發現（該文 §4.3，真實 758 筆 Cboe 全鏈實算，YETI，13 個到期日
DTE 0–525）**：

- 美式選擇權的 put-call parity 只剩不等式，不是等式：
  `S-K ≤ C_A-P_A ≤ S-K·e^{-rT}`（有股利時下界再減 PV(D)）。
- 用歐式基準衡量，call 側 parity gap 中位數 +1.2% width，表面看像
  「call 系統性偏貴」。但 **r=0 時這個 gap 精確歸零**——市場其實是把
  美式 box 定價在**未貼現** width 附近，這正是美式不等式上緣的預期
  行為，**不是報價錯位，是模型口徑差**。
- **LEAPS 天期效應最大**：DTE>365 的配對中，95.2% 呈現這個方向，
  gap 中位數達 +3.13% width——天期越長、提前履約權利的價值越大。
- 個別配對層級，|gap| 中位數只有四腿交易成本的 0.22 倍——**對單一
  配對而言是雜訊，不是可交易訊號**，遑論拿來精確反推股利。

**對 #110 的含義**：若直接把 C-P 代進 `F = K + (C-P)·e^{rT}` 反推
forward（Method D），算出來的數字混合了「真實股利效應」與「put 提前
履約溢價」兩個成分，且後者在 LEAPS 天期上量級不比前者小（同一份文件
的量化：LEAPS box 偏離未貼現 width 的幅度達 7% width 量級）。**這兩個
成分無法從 vanilla parity 單獨分離**，需要一個獨立的美式定價模型
（例如二項樹）當對照才能拆開——複雜度遠超過本票 §3 示範的「同側跨
履約價校準」，且後者已經因為只用 call、不牽涉 put，天然避開了這個
文件點名的主要汙染源。這是本票 §6 不推薦 Method D 的直接理由。

**除息前 call 的提前履約風險**（`spread-synthetic-parity-check.md`
§3.2，搜尋索引轉述）：TLT 逐月配息，深度 ITM 短 call 在除息日前有
被提前指派的誘因（Cboe 教育內容明文警告）；本 app 目前的候選策略
（Long Call／Bull Call Spread／Long Put／Bear Put Spread）皆為**買方
視角**（付權利金方），提前指派風險主要落在**賣出**的那一腿（縱向
價差的賣腿）身上——這是產品既有策略範圍的既有風險，不是本票新增的
問題，但任何未來的股利/carry 模型修正都不會、也不能消除這個風險，
需要在文件與 UI 揭露上維持誠實。

---

## 5. 獨立覆核：Treasury par → continuous 近似的正確性

`docs/research/risk-free-rate-for-bs.md` §5.3 已量化「par→zero
bootstrap 與直接公式 `r_cc=2·ln(1+y/2)` 之差在 3Y 以下可忽略
（0.52bp）」，`option_chaser/ratecurve.py` 現行實作正是採用這個直接
公式、不做 bootstrap。AC 要求本票「一併驗證」——本節提供**獨立**
（不同曲線資料、獨立實作的 bootstrap 函式）覆核，而不是重抄一次舊
結論。

**方法**：`scripts/research_valuation_methods.py::bootstrap_zero_curve`
——標準半年配息公債序貫 bootstrap（教科書作法，見 §7 引用），對
`tests/fixtures/treasury_csv_sample.txt`（真實 2026-08-04 Treasury 曲線，
`ratecurve.parse_treasury_csv` 既有函式解析，非本票新解析邏輯）逐節點
求解，與現行 `par_to_continuous` 的直接近似公式比較。

| 年期 | par 殖利率 | 直接近似 | bootstrap | 差距 |
|---|---|---|---|---|
| 0.5 | 4.000% | 3.9605% | 3.9605% | 0.000bp |
| 1.0 | 4.040% | 3.9997% | 4.0001% | 0.040bp |
| **2.0** | 4.200% | 4.1565% | 4.1617% | **0.522bp** |
| **3.0** | 4.250% | 4.2055% | 4.2108% | **0.529bp** |
| 5.0 | 4.330% | 4.2838% | 4.2948% | 1.098bp |
| 7.0 | 4.470% | 4.4208% | 4.4489% | 2.808bp |
| 10.0 | 4.630% | 4.5772% | 4.6335% | 5.628bp |

2Y 節點的獨立覆核結果（0.522bp）與既有研究文件引用的數字（0.52bp）
幾乎完全吻合，交叉驗證兩份分析互相一致。**本工具實際使用範圍
（1M–3Y，`risk-free-rate-for-bs.md` §7 既有結論：3Y 以上用不到）內，
差距全部 <1bp**，5Y 以上才明顯放大（但超出使用範圍，不影響現行
實作的正確性判斷）。既有結論**獨立覆核通過**，見
`test_par_to_continuous_matches_bootstrap_within_documented_tolerance`。

---

## 6. 方法比較總表

| 方法 | 假設 | 資料需求 | 主要失敗模式 | 本票量化結果 |
|---|---|---|---|---|
| **A. 現行 q=0 基準** | 標的不配息或可忽略 | 無（現有輸入即可） | 對配息標的系統性高估 call；LEAPS 複利放大 | **3/5 真實 LEAPS 合約在數學上不可行**（§3.1） |
| **B. 固定股利殖利率** | 配息可用大致固定的連續殖利率近似 | 一個 q 數字（外部來源或本票校準法） | q 若抓錯／過時，引入新誤差；不解決美式提前履約殘留 | 用 Method E 校準後 5/5 可行、離散度收斂（§3.2） |
| **C. 已知配息時間表** | 未來配息時序＋金額可預測 | 完整配息歷史＋預測方法論 | LEAPS 天期預測誤差累積可能比 q=0 本身更大；仍不解決 put 側提前履約 | 未實作（複雜度／資料依賴皆高於 B，本票判斷不值得） |
| **D. Put-call parity 隱含 forward** | 市場對同履約價 call/put 定價乾淨反映 parity | 同履約同到期雙邊流動報價 | **已證實**：美式提前履約溢價汙染，LEAPS 尤其嚴重，無法乾淨分離股利效應（§4） | 引用既有真實資料研究，本票不重做（§4） |
| **E. 跨履約價 IV 一致性校準**（本票提出） | 同到期日相近價位的隱含波動率該相對一致 | 同到期日至少 3–4 筆流動同側報價（無新資料依賴） | 深度 OTM/ITM 需排除（真實 skew）；殘留美式 call 提前履約誤差 | **本票主要量化結果**（§3.2），相對 D 天然避開 put 提前履約汙染 |

---

## 7. 書面建議

**這是建議，不是本票已執行的變更**——需要需求方核准才會進入後續
「鎖定並實作」票（#113 或其後續）。

**建議方向**：Method B 的公式（Merton 股利殖利率調整 BS）＋ Method E
的校準來源（同一次分析、同一到期日的多筆真實報價，跨履約價擬合出
讓隱含波動率最一致的 q）。

**理由**：

1. §3 已用真實資料證明現行 q=0 基準對 LEAPS TLT call 有非邊緣案例的
   失敗（3/5 檔不可行），且這個結論在合理利率誤差範圍內穩健。
2. Method D（parity 直接萃取）已被本 repo 既有研究證明會被美式提前
   履約溢價汙染，LEAPS 天期效應更大——AC 明文警告的風險，§4 已用
   真實資料坐實，不建議採用。
3. Method C（配息時間表）的預測複雜度與天期累積誤差，對這個 app
   的定位（手機優先、單一使用者快速判讀）不成比例；且仍不解決 put
   側提前履約，工程投資報酬率低。
4. Method E 的最大優點是**零新增資料依賴**——不需要接新的外部股利
   資料源（新的失敗模式、新的維護負擔），用引擎本來就會抓到的同一批
   選擇權鏈自我校準即可，且天然避開 D 的已知汙染源（只用同側 call，
   不跨 call/put 組合）。

**已知殘留侷限（核准前務必一併裁示，不是事後才發現）**：

- 校準需要同到期日至少 3–4 筆流動性夠的同側報價；候選池過少的到期日
  （FB3-02／#45 已有的警示邏輯）校準會不穩定，需要一個明確的
  fallback（退回 q=0，或退回一個保守的固定值）與對應的警示文案，
  這是實作票的範圍，本票不預先設計。
- 每次分析多一個數值求解（跨履約價擬合），計算成本相對現有規模
  可忽略，但需要在下一張實作票的驗收條件裡明確測到。
- 即使核准，這仍是**歐式近似＋經驗校準殖利率**，不是完整美式定價
  模型——沒有解決 call／put 提前履約的殘留誤差，只是把「完全沒有
  股利調整」這個目前已知最大的誤差來源縮小。使用者說明（沿用
  `tlt_report.md` 尾註「模型限制」的既有揭露文化）需要同步更新用詞，
  不能把這個方案包裝成「已修正美式定價」。
- q 的校準結果會隨每次分析的快照變動（§3.3），不是一個寫死的常數；
  UI／報告若要顯示這個數字，語意上應該類比現行 T12 的
  `rate_used`／`rate_curve_date` 透明化做法（#112 剛完成的先例），
  讓使用者看得到「這次用的 q 是多少、怎麼來的」，而不是一個黑盒子
  調整。

---

## 8. 引用清單

**本票新產出（可重跑）**：

- `scripts/research_valuation_methods.py`——研究用純函式（股利調整
  BS、隱含波動率求解器、半年配息 bootstrap）
- `tests/test_research_valuation_carry.py`——8 條可重複執行的驗收
  測試，明確門檻見各測試 docstring
- `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`——真實 TLT
  LEAPS 報價（來源：本 repo 既有 `tlt_report.md`）

**本 repo 既有（直接引用，未重做）**：

- `tlt_report.md`——真實 TLT LEAPS 分析報告（本票 §3 資料來源）
- `tests/fixtures/treasury_csv_sample.txt`——真實 2026-08-04 Treasury
  曲線（本票 §5 資料來源）
- `docs/research/spread-synthetic-parity-check.md`（R4／#99）——美式
  parity／提前履約溢價的真實資料實算，本票 §4 核心引用
- `docs/research/risk-free-rate-for-bs.md`（T12-A）——r 的定義與
  par→continuous 近似的原始量化，本票 §5 獨立覆核對象
- `docs/research/interest-rate-source-selection.md`（issue #73）——
  利率資料源選型，已定案，本票不重新評估
- `docs/research/cboe-field-semantics.md`——真實全鏈 fixture 出處
  （YETI，`spread-synthetic-parity-check.md` 引用鏈的上游）
- `option_chaser/valuation.py`——現行 q=0 引擎實作（本票分析對象，
  未修改）
- `option_chaser/ratecurve.py`——現行 par→continuous 實作（本票 §5
  獨立覆核對象，未修改）

**學術／教科書（沿用既有研究文件已列的引用，未重新查證）**：

- Merton, R. C. (1973). "Theory of Rational Option Pricing."
  *Bell Journal of Economics and Management Science*——股利殖利率
  調整 BS 公式的原始出處（標準教科書結果，逐字未核對原文）。
- Black, F. (1975). "Fact and Fantasy in the Use of Options."
  *Financial Analysts Journal*——escrowed dividend model／美式 call
  pseudo-American 近似（Method C 提及，逐字未核對原文）。
- Hull, *Options, Futures, and Other Derivatives*——美式 put-call
  parity 不等式、bootstrap 曲線構建標準作法（章節對應沿用
  `risk-free-rate-for-bs.md` 既有引用，未重新查證）。
- 美式 put-call parity 不等式與股利修正：與
  `spread-synthetic-parity-check.md` §8 同一組轉述來源
  （midhafin.com、NYU／HKUST 課程講義，經搜尋索引摘錄）。

**取材限制聲明**：本沙箱出口 proxy 對多數金融／政府資料網域回 403
（與前次研究一致，見 `risk-free-rate-for-bs.md` 開頭聲明）；
`raw.githubusercontent.com` 本次實測可達，`docs/research/
spread-synthetic-parity-check.md` 引用的真實 YETI 全鏈原檔可重新
下載覆核。本票未能取得真實 TLT 全鏈（含 put）快照，§3 的量化因此
限定在真實但只有 call 側的 `tlt_report.md` 資料——這個侷限已在 §3.3
明列，不影響 §3 核心結論（q=0 在數學上不可行）的有效性，因為那個
結論只需要 call 側資料就能證明。
