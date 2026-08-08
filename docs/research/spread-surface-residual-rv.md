# Vertical Spread 的 surface 殘差 relative value——fit 等級、Cboe 資料可用性與輸出語意

研究日期：2026-08-08（issue #97／R2）。本文承接
`candidate-iv-relative-value.md` §12.4（方案四：橫斷面 surface 殘差）與
§3.3 三層拆解的「Residual 層」，把該案從「先例厚、可行」推進到**可施工
判定**：殘差標示（給零售使用者一個 rich/cheap 讀數）的最低可接受 fit
等級是什麼、Cboe 延遲快照的 `iv`／`theo` 欄位撐不撐得起這條路徑、殘差
用什麼單位呈現、以及它誠實的能與不能。**本文不施工、不替需求方拍板。**

這條路徑的獨特地位：候選路徑中**唯一零歷史資料**就能做的正宗 relative
value——參照系是「同一時刻、同到期、鄰近履約價」，一份當下快照自足。

## 0. 資料品質聲明（先讀）

沙箱網路限制與前幾輪相同：WebFetch 對絕大多數網域 403，
`raw.githubusercontent.com` 例外。本文證據分級沿用既有標記體系：

- **〔實測實證〕**：真實 Cboe 全鏈 payload（YETI.json，2023-08-11，
  758 筆、13 個到期日，`cboe-field-semantics.md` §7 已驗證自洽性）上的
  **本輪新實算**——per-expiry 二次式擬合、殘差 vs bid-ask 寬度、
  `theo` 殘差對照，全部 stdlib＋repo 引擎，§6 附完整重現步驟。
  這是本文最強的證據等級，關鍵判定全部落在這一級。
- **〔一手・逐字〕**：僅限前幾輪已逐字檢視過的文獻（Gatheral SVI
  參數化、Natenberg skew 座標、Zou–Derman SAS），本輪引用時註明
  「前輪已驗」；本輪**沒有**新取得一手 PDF。
- **〔索引轉述〕**：Dumas–Fleming–Whaley 1998、OptionMetrics 方法、
  ORATS SMV／S%、SABR 失敗模式、加權慣例、SpiderRock 用語——皆為
  搜尋索引摘錄，**未逐字核對原文**，逐項列 §8。

## 目錄

1. 結論摘要
2. fit 的最低要求：從 kernel／SVI／SABR 到 per-expiry 二次式
3. 資料現實：點數、Cboe `iv` 直接 fit、`theo` 極簡路徑
4. 輸出語意：單位與「兩腿 vs 整組」的取捨
5. 誠實侷限：橫斷面盲區與延遲報價
6. 實算：YETI 真實鏈上的二次式殘差 sanity check
7. 結論（供 G1 裁示）
8. 查證限制
9. 來源清單

## 1. 結論摘要

1. **「殘差標示」用途的最低可接受 fit＝per-expiry、log-moneyness 座標、
   OTM-only、以 1/相對價差² 加權的二次式**——有一線學術先例（DFW 1998
   的「practitioner／ad hoc Black-Scholes」正是逐期二次式平滑，且
   out-of-sample 打贏更複雜的 deterministic volatility function 模型，
   §2.2）、有本輪實測背書（真實鏈上 OTM 殘差中位數 0.12–0.37 vol pts，
   遠低於 bid-ask 半寬，§6）。SVI／SABR／kernel 是「無套利定價、做市、
   跨期一致性」等**更高用途**的工具，殘差標示不需要（§2.4）。
2. **但二次式的「夠」有三個前置條件，缺一即壞**（全部有實測反例）：
   (a) **OTM-only**——混入深 ITM 合約，161 天期殘差中位數從 0.22 暴增
   到 3.91 vol pts（§6.2）；(b) **moneyness 剪裁**——遠翼垃圾報價
   （IV 100%+ 的廢紙合約）殘差可達 ±40 pts，必須先剪；(c) **加權**
   ——1/相對價差² 或 vega 加權是業界標準（§2.5）。
3. **每到期可用點數：實測 9–26 個 OTM 有效點（近月 4 個）**。三參數
   二次式的建議下限 **≥6 點**；不足時**直接放棄該期、顯示「無法評估」**
   ——與 FB3-02 的 `expiry_counts` 警示同一姿勢。第一階段**不建議**
   跨到期借力（那等於自建整張 surface，工程與風險跳一個量級，§3.1）。
4. **直接 fit Cboe `iv` 欄位：成立，且是繞開自家 q=0 缺陷的唯一正解**。
   Cboe `iv` 是含離散股利的美式二項樹反推，同一條鏈內自成一致口徑；
   `iv=0→None` 既有映射已把哨兵值擋掉。實測 OTM call＋put 混合 fit
   殘差乾淨（LEAPS 期 0.12 pts），代表 Cboe 的 call/put IV 對齊品質
   對本用途夠用（§3.2）。
5. **`theo` 極簡路徑（殘差＝market−theo）：實測可行，且與自建二次式
   高度一致**——同一批 OTM 點上，`(mid−theo)/vega` 與自建二次式殘差的
   相關係數 **+0.94（161d）／+0.98（525d／LEAPS）**（§6.3）。零實作
   成本版是合格的 v0；黑箱、無文件、無更新時點保證是它的長期風險，
   自建二次式是它的驗證器與升級路（§3.3）。
6. **輸出單位三種都有先例**：vol pts（desk 標準語言）、$（theo edge）、
   佔 mid 的 %（ORATS S%，掃描器慣用 ±3% 當「合理定價帶」）。本產品
   建議：**spread 整體殘差佔 debit 的 % 為主讀數**（對 debit 買方最可
   行動）＋**每腿 vol pts 為明細**。兩腿同號相消在 $ 口徑下不是 bug
   ——兩腿同樣貴時 spread 淨額外成本本來就部分抵銷，$ 加總如實反映
   （§4.2）。
7. **誠實侷限**：(a) 橫斷面殘差**看不見整張 surface 一起貴**——它與
   vol level／skew 歷史位置（前輪方案 A／方案二）互補而非替代，card
   上必須分區標示「相對今日曲線」；(b) **健康鏈上多數時間讀數低於
   雜訊門檻**——LEAPS 期實測 41/41 殘差落在 bid-ask 半寬內，正確呈現
   是「無顯著偏離」而不是硬擠一個 rich/cheap 標籤；殘差必須永遠對照
   半價差當底噪標尺（§5.2）；(c) 延遲與盤外報價的 staleness 會以
   「假殘差」形式出現，只能靠標注快照時戳與門檻緩解（§5.3）。

## 2. fit 的最低要求

### 2.1 用途決定 fit 等級：先把光譜擺出來

| fit 等級 | 代表 | 原生用途 | 對「殘差標示」的過度之處 |
|---|---|---|---|
| 3D kernel smoothing | OptionMetrics IvyDB standardized surface | 學術資料標準、跨期網格 | 需全鏈跨期聯合平滑＋vega 加權基建 |
| spline＋無套利修正 | ORATS SMV、SpiderRock | vendor 理論值產品、edge 掃描 | 無套利修正（butterfly/calendar）對顯示用殘差無感 |
| SVI（5 參數/expiry） | Gatheral（前輪一手已驗）；Gatheral–Jacquier 2014 無套利版 | 定價、外插 wings、g-function 無套利檢查 | 非線性最佳化＋參數辨識問題；wings 外插本用途不需要 |
| SABR | Hagan 2002 | 利率界定價/避險 | 近似式在長天期／遠翼**產生負機率密度**（已知失敗模式）；沒有理由引入 |
| **per-expiry 低階多項式** | **DFW 1998「ad hoc BS」** | **平滑市場 IV、當定價 benchmark** | ——（本文主角） |

〔索引轉述〕SABR 的 Hagan 近似「accuracy deteriorates for high
volatilities, long maturities and OTM options, yielding negative
densities in the tails」——長天期＋遠翼恰好是本產品 LEAPS 主戰場，
SABR 是這張表裡唯一「不只是過度、還會主動出錯」的選項。SVI 的優勢
（g-function 解析檢查無套利）服務的是定價與做市；殘差標示不消費
無套利性——fitted curve 有一點 butterfly arbitrage 不影響「這筆報價
離鄰居多遠」的讀數。

### 2.2 「per-expiry 二次式就夠」的一線先例：DFW 1998

〔索引轉述〕Dumas, Fleming & Whaley, “Implied Volatility Functions:
Empirical Tests”, *Journal of Finance* 53(6), 1998：文中作為對照組的
「ad hoc／practitioner Black-Scholes」程序＝**把 BS implied volatility
對履約價（與到期）做二次多項式平滑，再塞回 BS 公式用**。論文的著名
結論：這個「毫無理論尊嚴」的平滑程序在 out-of-sample 預測與避險上
**不輸、甚至打贏** deterministic volatility function 模型。後續文獻
（如 Christoffersen–Jacobs 2004）把 ad hoc BS 當作評估任何定價模型的
標準 benchmark。這正是本題要的先例形狀：**當用途是「把市場自己的
smile 平滑之後當參照」而非「無套利定價」，逐期二次式是有 25 年文獻
背書的專業做法**。

補一個反向界線〔索引轉述＋理論〕：Lee (2004) moment formula 證明
implied **variance** 在 |k|→∞ 至多線性成長；二次式在遠翼是二次成長，
**必然**在夠遠的 wings 高估——所以二次式的適用域是「候選所在的中央
moneyness 帶」，遠翼要剪裁（§2.5），不能拿它外插。這不是缺陷而是
分工：本產品的殘差只需要在**候選兩腿附近**準。

### 2.3 vendor 實務對照：他們多做的部分是為了什麼

- **OptionMetrics**〔索引轉述〕：對每檔標的每天算 kernel-smoothed
  constant-expiration surface（Gaussian kernel、vega 加權）。多做的
  「跨期聯合」服務的是 constant-maturity 網格輸出——本用途不需要
  跨期輸出，逐期獨立 fit 即可。
- **ORATS SMV**〔索引轉述〕：先清報價、由 put-call parity 解
  residual yield 把 call/put IV 對齊，再以「akin to a cubic spline」
  的曲線逐 strike 局部調整，消 butterfly/calendar arbitrage；加權上
  「靠近 50 delta 權重高、同 strike 的 OTM 側比 ITM 側權重高」
  （20Δ call 的 IV 權重高於同履約價 80Δ put）。注意兩件事對本產品
  的啟示：(a) residual yield 這一步我們**不用做**——Cboe `iv` 已是
  含股利美式口徑，同鏈自洽（§3.2）；(b) 「OTM 側優先」正是 §6.2
  實測到的 ITM 污染問題的 vendor 級解法，我們的 OTM-only 是它的
  簡化版。
- **SpiderRock／Vola Dynamics／Bloomberg VCA**：surface fit＋edge
  是機構產品標配（前輪 §7.4 已述，不重複）。

### 2.4 判定：殘差標示的最低可接受 fit

**per-expiry、x＝log-moneyness `ln(K/S)`、y＝Cboe `iv`、OTM-only、
1/相對價差² 加權、OLS 二次式（3 參數）**。理由收攏：

1. 用途只是「這兩張合約離同期鄰居多遠」的顯示層讀數，不定價、不
   避險、不外插——DFW 先例＋§6 實測都說明這個等級對這個用途夠；
2. 三參數 OLS 是封閉解（3×3 正規方程），stdlib 純手算即可，符合
   serverless 引擎「無 scipy 依賴」的現實；
3. 失敗模式全部可預先繳械：ITM 污染→OTM-only；遠翼發散→moneyness
   剪裁＋只在候選附近讀值；點數不足→放棄該期（§3.1）。

**反例（什麼時候二次式不夠）**：(a) 要對**遠翼外插**（Lee 界，
§2.2 末）；(b) 要跨期比較或 constant-maturity 輸出（需 total
variance 內插，等於自建 surface）；(c) 要保證無套利（做市/定價）。
三者都不在本票用途內。

### 2.5 加權與剪裁的業界慣例

〔索引轉述，Homescu 2011 survey 等〕擬合權重的兩個標準選擇：
**1/(bid-ask spread)²**（統計上近似殘差變異數的倒數，最小變異）或
**vega²**（「vega weights are a smoothed version of the inverse of
the bid-ask spread」）；流動性太差的點「移除比硬 fit 好」。本文實算
採 1/相對價差²，效果見 §6。剪裁建議：只取有雙邊報價、`iv>0`、
相對價差 ≤ 某上限（可沿用既有品質過濾的 15% 口徑）的 OTM 點；
遠翼 IV 異常點（如 §6.2 的 IV 102% 廢紙 put）自然被價差權重壓低，
但保守起見可再加 |log-moneyness| 上限。

## 3. 資料現實：Cboe 延遲快照撐不撐得起

### 3.1 (a) 每到期可用點數與稀疏對策〔實測實證〕

真實 Cboe 全鏈（YETI，13 個到期日）的「可 fit 點」普查——條件＝
`iv>0`＋雙邊報價＋OTM：

| DTE | 0 | 7 | 14 | 21 | 28 | 35 | 42 | 49 | 98 | 161 | 189 | 315 | **525** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 全部合約 | 82 | 94 | 84 | 56 | 56 | 32 | 56 | 56 | 36 | 94 | 34 | 36 | **42** |
| OTM 可用 | 4 | 19 | 25 | 15 | 16 | 9 | 20 | 20 | 16 | 26 | 14 | 16 | **21** |

- **除了當日到期（4 點），每期 9–26 個可用點**——對 3 參數二次式
  綽綽有餘。**LEAPS 期（525d）有 21 點**，且該期報價品質最好
  （`cboe-field-semantics.md` §1.1：`iv=0` 僅 1/42；§5.2：相對價差
  中位數 3.9%、全鏈最窄）。TLT 流動性優於 YETI，LEAPS 履約價網格
  （5 點間距）預期同量級或更密。
- **建議下限 ≥6 點**（3 參數 × 2 的工程餘裕）；低於下限**放棄該期**，
  殘差列顯示「該期候選點不足，無法評估」——語意與 FB3-02 的
  「⚠ 該期僅 N 組候選通過品質過濾」警示同族，可共用 `expiry_counts`
  基建。
- **不建議跨到期借力（第一階段）**：借力＝在 total variance 空間做
  期限維內插＋跨期一致性約束，等於自建整張 surface——正是 §2.1 表
  中「更高用途」那幾行的工程量。稀疏到 fit 不動的期，通常整期候選
  池本來就有問題（FB3 診斷的 deep-ITM-only 情境），誠實顯示「無法
  評估」比借一個看似精確的數字好。

### 3.2 (b) 直接 fit Cboe `iv`：成立，且是 q=0 缺陷的正解〔實測實證〕

`candidate-iv-relative-value.md` §7.4 的警告是本題的出發點：自家引擎
q=0 歐式 BS 在 TLT LEAPS 上把理論值高估近一倍（bs_call=7.68 vs 市場
3.80/4.10），**任何用自家模型當 fair value 的殘差都是股利假象**。
繞法就是不經過自家模型：

1. **Cboe `iv` 是含離散股利的美式二項樹反推**（Hanweck 口徑，
   `cboe-field-semantics.md` §2.2）——股利與美式特徵已在反推時吃掉，
   同一條鏈內的 `iv` 彼此同口徑。**殘差是「iv 對 fitted-iv」的差，
   模型偏置在被減數與減數中共模抵銷**——這是「直接 fit `iv`」在
   方法論上成立的核心理由。
2. **已知品質問題與既有防線**：`iv=0` 哨兵值（深 ITM／無時間價值，
   非 LEAPS 病）已由 `iv=0→None` 映射擋掉；廢紙合約（bid=0）不進
   雙邊報價條件；近到期反推退化（T→0）不影響本產品的遠月主戰場。
3. **call/put 對齊品質實測夠用**：OTM-only 集合同時含 OTM put
   （K<S）與 OTM call（K>S），若 Cboe 的 call/put IV 沒對齊（ORATS
   要靠 residual yield 解決的問題），fit 會在 S 附近出現接縫、殘差
   系統性放大。實測沒有：LEAPS 期混合 fit 殘差中位數 0.12 pts、
   41/41 在半價差內（§6.1）——本用途所需精度下，Cboe 出廠的對齊
   品質直接可用。
4. **殘留缺口——深 ITM 腿不可評分**：`iv=0`／無時間價值的深 ITM
   合約（FB3 診斷裡 2028/6 只剩 75/80 的那種候選）在這條路徑下
   **沒有殘差讀數**，該腿如實顯示「無法評估」。這與
   `cboe-field-semantics.md` §1.2 第 3 點的「無時間價值旁路」建議
   相容：那種腿實質等同持股，rich/cheap 對它本來就不是有意義的問題。

### 3.3 (c) `theo` 極簡路徑：品質實測合格的 v0〔實測實證〕

殘差＝`market − theo`，零 fit、零實作成本。本輪把它和自建二次式放在
同一批點上對照（§6.3）：

- `(mid − theo)/vega` 換算成 vol pts 後，與自建二次式殘差的相關係數
  **+0.94（161d）／+0.64（315d）／+0.98（525d，LEAPS）**——在本產品
  主戰場（遠月）兩者幾乎是同一個訊號。
- 幅度也同量級：|mid−theo| 中位數 0.13–0.67 pts vs 自建 fit 的
  0.12–0.22 pts。
- 佐證既有實測：`option-liquidity-filtering.md` §6.5——`theo` 不是
  mid 的換算（0/600 恰等於 mid、19 筆落在 [bid,ask] 外），是獨立的
  曲面擬合值。

**判定**：`theo` 殘差是合格的 v0——一次減法＋vega 換算（`vega` 欄位
Cboe 也現成給），adapter 只需新增 `theo`（既有 D5 裁示項）與 `vega`
兩欄。**長期風險**：端點無文件、演算法黑箱、更新時點與 staleness
未知（`option-liquidity-filtering.md` §9 第 2 項）、Cboe 隨時可改口徑
——自建二次式因此不是重複造輪，是 `theo` 的**驗證器**（兩者背離時
標示「參照值分歧，讀數不可靠」）與斷供時的升級路。兩條路徑同時做
的邊際成本極低（二次式 OLS 是 3×3 封閉解）。

## 4. 輸出語意

### 4.1 單位的先例

| 單位 | 先例 | 適用讀者 |
|---|---|---|
| **vol pts** | desk 標準語言；SpiderRock 圈的口語換算「3 vol pts 殘差 ≈ 30-DTE SPY 上 $0.50 edge」〔索引轉述〕；SAS 本身就是 vol pts（前輪一手已驗） | 懂 IV 的使用者、每腿明細 |
| **$** | theo edge（理論值−市價）；ORATS 掃描的 theoretical edge | 直接可加總到 spread |
| **佔 mid 的 %** | ORATS S%＝smoothed theo 與 mid 的距離 ÷ mid；掃描實務用 ±3% 當「合理定價帶」〔索引轉述〕 | 零售主讀數——與報酬率同一種語言 |

換算橋樑是 vega：`殘差($) ≈ 殘差(vol pts) × vega_per_pct`。三種單位
是同一個數字的三件衣服，資料上互通。

### 4.2 兩腿各自殘差 vs spread 整體殘差

- **vol pts 空間不可加總**：兩腿 vega 不同，vol pts 直接相加無意義；
  且 SAS 腳注 3 的單調性紅線（前輪 §7.1）禁止給 spread 湊單一
  vol-單位數字——**每腿 vol pts 只能並排列示，不能合成**。
- **$ 空間天然可加**：`spread 殘差($) = (mid_buy − fit_buy) −
  (mid_sell − fit_sell)`（或保守用 worst 口徑：ask_buy／bid_sell）。
  「兩腿殘差同號相消」在這個口徑下**是正確結論不是缺陷**：兩腿同樣
  貴 1 pt 時，買貴的部分被賣貴的部分抵銷，spread 淨多付的就是
  vega 差那一塊——$ 加總如實反映使用者實際多付／少付的錢。
- **建議呈現（對齊前輪 §12.5 card 的方案四列）**：主讀數＝
  **spread 整體殘差佔 debit 的 %**（正＝比參照曲線貴、負＝便宜；
  中性措辭沿用「事實性數字、不加主觀標籤」裁示）；明細＝每腿
  vol pts＋各自 bid-ask 半寬（§5.2 的底噪標尺）。深 ITM 腿無讀數時
  整組退化為「僅賣腿可評估」的部分讀數＋標注。

## 5. 誠實侷限

### 5.1 橫斷面盲區：看不見「整張 surface 一起貴」

殘差的參照系是**今天的鄰居**。整條 smile 平移 +10 pts（vol 環境變貴）
時每一筆的殘差不動——它回答「這兩張合約**挑得**好不好」，不回答
「**現在進場**好不好」。與前輪三層拆解的關係必須在 UI 上講死：

| 問題 | 路徑 | 資料需求 |
|---|---|---|
| 現在 vol 環境貴嗎（level） | 前輪方案 A/B（ATM IV 歷史位置） | 需歷史 |
| 這組結構的 skew 相對歷史在哪（slope） | 前輪方案二（normalized gap 序列） | 需歷史 |
| **這兩張報價相對今天的鄰居偏不偏（residual）** | **本文** | **零歷史** |

三者正交；card 上「相對今日曲線」與「相對一年歷史」分區分標題、
嚴禁混排（前輪 §12.4 的警告原樣沿用）。零歷史是本路徑的獨有優勢，
橫斷面盲區是同一枚硬幣的另一面——文件與 UI 都不得暗示它涵蓋
「現在是不是好時機」。

### 5.2 殘差 vs 雜訊：多數時間讀數在底噪之下

§6 實測的核心誠實發現：**健康鏈上殘差普遍小於 bid-ask 半寬**——
LEAPS 期 41/41、315d 期 16/16 的殘差都落在半價差內。含義：

1. **底噪標尺是產品義務**：|殘差| ≤ 半價差時，「rich/cheap」與
   「兩邊報價各自量化誤差」不可分，正確顯示是「無顯著偏離（±x pts
   內）」。前輪 §12.4 的「殘差 < 半個 spread 時無資訊量」判斷被
   本輪實測完全證實，且證實的是**常態而非例外**。
2. **這個指標大部分時間會說「沒事」**——對品質健康的標的（TLT 級
   流動性）這是常態。產品要接受「多數時候無訊號」的指標定位：它的
   價值在**例外時刻**（某腿被掛出離群報價、盤外殘留怪 ask、冷門
   履約價）當保險絲，與 §6.5 `theo` 檢查的「盤外／冷門標的保險絲」
   定位一致。把它包裝成天天有戲的主指標，等於逼它輸出雜訊。
3. LEAPS 的絕對 vega 大（同樣 $ 價差換算出的 vol pts 底噪反而小，
   §6.1 表中 525d 半寬中位數 0.81 pts、全鏈最低）——**本產品主戰場
   恰是這條路徑訊噪比最好的地方**，這是幸運的巧合，值得記錄。

### 5.3 延遲與盤外報價的 staleness

- 免費端點是 15 分鐘延遲快照；**同一份 payload 內各合約的報價新鮮度
  不一致**（唯一時間欄位 `last_trade_time` 是成交時戳，報價無時戳，
  `option-liquidity-filtering.md` §5 已查）。一筆陳舊報價對上以新報價
  fit 出的曲線，殘差讀數就是快照不同步的假訊號——冷門履約價（恰好
  是殘差最可能報警的地方）最容易中。
- 盤外 Cboe 報價凍結不歸零（FB3-01 已實測），凍結的兩腿與凍結的
  鄰居彼此仍同時刻口徑，**盤外殘差比 yfinance 的歸零報價可用**；
  但跨收盤時段（部分更新部分凍結）的快照最髒。
- 緩解只有標注與門檻：card 沿用快照時戳揭露慣例；殘差門檻用
  半價差（§5.2）本身就吸收了大部分 staleness 雜訊——陳舊報價通常
  伴隨寬價差，門檻自動變高。**無法根治，如實承認。**

## 6. 實算：YETI 真實鏈上的 per-expiry 二次式 sanity check〔實測實證〕

### 6.1 設定與主結果

資料＝`cboe-field-semantics.md` §7 的同一份真實 Cboe 全鏈
（YETI，2023-08-11 16:27:37，spot 44.97，758 筆）。註：任務原點名的
`tests/fixtures/` 實無完整 Cboe fixture（`test_data_cboe.py` 內嵌的
TLT fixture 僅近月三張，fit 不動），故沿用該文件記載的可下載真實
樣本。方法＝對每期取「`iv>0`＋雙邊報價＋OTM」點，x＝`ln(K/S)`、
y＝Cboe `iv`、權重＝1/相對價差²，OLS 二次式（3×3 正規方程手解，
stdlib）；殘差換算 vol pts，與「bid-ask 半寬 ÷ vega」（同為 vol pts，
vega 用 repo 引擎 `call_greeks`，r=5.3%）逐筆對照：

| DTE | n（OTM） | \|殘差\| 中位數 | 半價差中位數 | 殘差 ≤ 半價差 |
|---|---|---|---|---|
| 98 | 16 | 0.37 pts | 1.43 pts | 14/16 |
| 161 | 26 | 0.22 pts | 1.03 pts | 23/26 |
| 315 | 16 | 0.13 pts | 0.83 pts | 16/16 |
| **525（LEAPS）** | **21** | **0.12 pts** | **0.81 pts** | **21/21** |

判讀：(a) 二次式對真實 smile 的中央帶擬合到「殘差量級 ≈ 十分之一
半價差」——fit 誤差不是殘差讀數的瓶頸，報價雜訊才是；(b) 越遠月
越乾淨，LEAPS 全數在底噪內（§5.2 的產品含義）；(c) 98/161 天期的
breach 全是遠翼廢紙點（IV 102% 的 P25、IV 70% 的 C70，殘差 +25～
+40 pts）——moneyness 剪裁的必要性的直接證據。

### 6.2 ITM 污染的量化（OTM-only 的必要性）

同一 161 天期，把全部雙邊報價（含深 ITM）都餵進 fit：n=59、殘差
中位數 **3.91 pts**（>半價差中位數 2.39，31/59 breach）；OTM-only
後 n=26、殘差中位數 **0.22 pts**。差 18 倍。機制＝深 ITM 報價時間
價值趨零、IV 反推退化＋美式提前履約溢價，這些點不在 smile 上卻有
低價差（權重大），整條曲線被拖歪。**OTM-only 不是偏好是前置條件**
——ORATS 的「OTM 側權重高於 ITM 側」是同一件事的 vendor 版（§2.3）。

### 6.3 `theo` 路徑對照

同一批 OTM 點上算 `(mid − theo)/vega`（Cboe 理論值殘差，vol pts）
與自建二次式殘差的一致性：

| DTE | n | \|fit 殘差\| 中位數 | \|mid−theo\| 中位數 | 相關係數 |
|---|---|---|---|---|
| 161 | 26 | 0.22 pts | 0.67 pts | **+0.94** |
| 315 | 16 | 0.13 pts | 0.13 pts | +0.64 |
| 525 | 21 | 0.12 pts | 0.21 pts | **+0.98** |

兩條完全獨立的參照線（Cboe 黑箱 fit vs 自家 stdlib 二次式）給出
幾乎同一組殘差——`theo` 路徑的品質判定（§3.3）與「二次式夠用」的
判定（§2.4）在此互相驗證。

### 6.4 重現步驟

```
資料：https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json
     （328,854 bytes，本沙箱實測 200 OK；自洽性驗證見 cboe-field-semantics.md §7）
解析：OCC 代號拆 expiry/type/strike（同 option_chaser/data/cboe.py 手法）
篩選：iv>0、bid>0、ask>bid、OTM（call K≥S／put K≤S）
擬合：x=ln(K/S)、y=iv、w=1/max(相對價差,1%)²；
     加權 OLS 二次式＝3×3 正規方程＋高斯消去（stdlib）
殘差：(iv−fit)×100 → vol pts
底噪：(ask−bid)/2 ÷ call_greeks(S,K,DTE/365,0.053,iv).vega_per_pct
theo：(mid−theo) ÷ 同上 vega
```

（實算腳本為 session scratchpad 臨時檔，上述步驟足以在任何環境
以 stdlib＋repo 引擎重現全部數字。）

## 7. 結論（供 G1 裁示）

**這條路徑回答哪種「貴」**：「這組 vertical spread 的兩腿報價，相對
**同一時刻、同到期的鄰近履約價**，偏貴／偏便宜多少」——今日橫斷面的
挑選品質，**不是**「現在進場時機好不好」（那是 level/skew 歷史位置的
問題，前輪方案 A／方案二，正交互補，§5.1 的分區表）。它是唯一零歷史
資料、零 vendor 依賴就能做的正宗 relative value。

**最小可行實作（fit 等級＋資料需求）**：

- **v0（零 fit）**：殘差＝`market − theo`，per-leg，vega 換算 vol pts
  ——adapter 加 `theo`／`vega` 兩欄（D5 裁示項）＋一次減法。實測與
  自建 fit 相關 +0.94~+0.98，直接合格。
- **v1（自建參照）**：per-expiry 加權 OLS 二次式（x＝log-moneyness、
  OTM-only、1/相對價差² 加權、moneyness 剪裁、≥6 點否則放棄該期）
  ——stdlib 封閉解，當 `theo` 的驗證器與斷供備援。
- **明確不做**：SVI/SABR/kernel（用途不需要）、跨到期借力（等於自建
  surface）、用自家 q=0 引擎當 fair value（股利假象）、給 spread 湊
  vol-單位單一數字（單調性紅線）。

**建議輸出單位與呈現**：主讀數＝spread 整體殘差佔 debit 的 %（$ 口徑
可加總，worst 或 mid 口徑擇一揭露）；明細＝每腿 vol pts；**每個讀數
旁邊永遠並列 bid-ask 半寬底噪**，|殘差|≤半寬時顯示「無顯著偏離」。
深 ITM／`iv=0` 腿如實顯示「無法評估」。

**殘差 vs 雜訊的誠實評估**：健康鏈上這是一個**多數時間安靜**的指標
（LEAPS 期實測 41/41 在底噪內）；它的產品定位是例外時刻的保險絲＋
「挑選品質」的客觀化，不是天天變動的主指標。恰好本產品主戰場
（LEAPS）是它訊噪比最好的 tenor。若需求方要的是「每天都有態度的
數字」，這條路徑給不了，該去前輪方案二；若要的是「零歷史成本、
方法論站得住、能抓離群報價」的補充列，這條路徑是四案中證據最厚、
成本最低的一條。

## 8. 查證限制

1. **DFW 1998 未逐字**：「ad hoc BS＝二次式平滑、out-of-sample 打贏
   DVF」為多來源索引轉述（SSRN/JSTOR/課程講義一致）；原文 PDF
   （ruf.rice.edu）在本沙箱被擋。
2. **OptionMetrics kernel 的公式細節**（Gaussian kernel 維度、vega
   加權形式）：官方 reference manual 非公開，轉述自引用它的學術文獻
   索引，未核對原件。
3. **ORATS SMV 流程**（residual yield、spline bands、OTM 側加權）與
   **S% 定義**（smoothed theo 距離 ÷ mid、±3% 掃描慣例）：官方 blog
   ／文件索引轉述。
4. **SABR 負密度失敗模式**：多篇文獻索引一致，未逐字核對 Hagan
   2002 原文或任一反例論文全文。
5. **Lee (2004) moment formula** 的精確陳述：教科書級常識＋索引
   轉述，未核對原文。
6. **加權慣例**（1/spread²、vega²）：Homescu 2011 survey 等索引
   轉述。
7. **「3 vol pts ≈ $0.50 edge」口語換算**：第三方教學文轉述，僅作
   單位慣例存在性的佐證，數字本身不引用。
8. **YETI 樣本的外推性**：單一標的、單一盤中快照（2023-08）；TLT
   的履約價密度、價差結構、盤外快照的殘差行為未在真實 TLT 全鏈上
   驗過——需求方部署環境抓 TLT 全鏈後，§6 全套統計可原樣重跑
   （與 `cboe-field-semantics.md` §8 第 1 項、
   `option-liquidity-filtering.md` §9 第 1 項是同一次抓取可結清的
   事項）。
9. **`theo` 演算法黑箱**：§3.3 的品質判定是行為層實測（與自建 fit
   的相關性），不是對其方法的核對；Cboe 改口徑無從得知。

## 9. 來源清單

**實測實證（可下載、可重跑）**

- [YETI.json 真實 Cboe 全鏈](https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json)
  ——§3.1／§6 全部統計的資料源（樣本驗證見 `cboe-field-semantics.md` §7）
- `option_chaser/valuation.py`（`call_greeks`）——vega 換算

**per-expiry 多項式先例**

- 〔索引轉述〕[Dumas, B., Fleming, J. & Whaley, R., “Implied Volatility Functions: Empirical Tests”, Journal of Finance 53(6), 1998（SSRN 7373）](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7373)；
  [全文 PDF（被擋）](http://www.ruf.rice.edu/~jfleming/pub/jf9812.pdf)；
  [JSTOR](https://www.jstor.org/stable/117461)
- 〔索引轉述〕[Homescu, C., “Implied Volatility Surface: Construction Methodologies and Characteristics”, 2011（arXiv:1107.1834）](https://arxiv.org/pdf/1107.1834)
  ——加權慣例（1/spread²、vega）與 fit 方法光譜的 survey

**vendor 方法**

- 〔索引轉述〕[OptionMetrics IvyDB US（kernel-smoothed standardized surface）](https://optionmetrics.com/united-states/)
- 〔索引轉述〕[ORATS — Smoothing Options Implied Volatilities Using ORATS SMV System](https://orats.com/blog/smoothing-options-implied-volatilities-using-orats-smv-system)、
  [Describing The Implied Volatility Options Surface](https://orats.com/blog/describing-the-implied-volatility-options-surface)、
  [How To Find The Best Options Trade Using Theoretical Values（S%）](https://orats.com/blog/how-to-find-the-best-options-trade-using-theoretical-values)、
  [ORATS University — Option scanning](https://orats.com/university/option-scanning)
- 〔索引轉述〕[SpiderRock — Analytics Framework](https://spiderrock.net/platform/analytics-framework/)、
  [FlashAlpha — Volatility Surface API（rich/cheap、vol pts→$ 換算口語）](https://flashalpha.com/articles/volatility-surface-api-how-to-build-visualize-trade-iv-surface)

**參數化模型與失敗模式**

- 〔前輪一手已驗〕Gatheral,《The Volatility Surface》Ch.3 SVI
  （`candidate-iv-relative-value.md` §5.3／§16）
- 〔索引轉述〕[Gatheral & Jacquier, “Arbitrage-free SVI volatility surfaces”（arXiv:1204.0646）](https://arxiv.org/abs/1204.0646)
- 〔索引轉述〕SABR 負密度：[Explicit SABR Calibration Through Simple Expansions](https://www.researchgate.net/publication/272242692_Explicit_SABR_Calibration_Through_Simple_Expansions)、
  [Analytic Calibration in Andreasen-Huge SABR Model（arXiv:2008.09108）](https://arxiv.org/pdf/2008.09108)、
  [volsurf-rs — Building Volatility Surfaces in Rust（工程視角的 wings 失敗整理）](https://volsurf-rs.github.io/posts/building-vol-surfaces-in-rust/)

**本 repo（引擎與既有研究）**

- `docs/research/candidate-iv-relative-value.md` §3.3／§7／§12.4——
  三層拆解、SAS 單調性紅線、方案四原始定位與 q=0 警告
- `docs/research/cboe-field-semantics.md` §1.1／§2.2／§5.2／§7——
  `iv=0` 哨兵語意、Hanweck 口徑、LEAPS 相對價差、樣本驗證
- `docs/research/option-liquidity-filtering.md` §6.5／§9——`theo`
  獨立性實測與 D5 裁示項
- `option_chaser/data/cboe.py`——`iv=0→None` 既有映射、OCC 解析
