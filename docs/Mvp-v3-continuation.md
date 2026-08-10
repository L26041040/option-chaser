# Spec：MVP V3 Remaining Work / Continuation

> **本文只規格化「尚未完成」的部分。** 第一施工批次（#103–#110、#112）與
> QA-01 修正輪（QA-FIX-1–5）已於 HEAD `8e57a7b` 標記 CLOSED / ACCEPTED，
> **不在本 spec 範圍內、不重寫、不重開**。本文承接 issue #102，取代其中
> 尚未施工的部分敘述（#111／#113/#114/#115/#116），並新增兩項在 QA 與
> 研究過程中確立的工作（q 資料管線、Heatmap compact 小修）。

---

## Problem Statement

需求方目前看到的劇本詳細頁有三個問題：

1. **Heatmap 印著看得出來的錯數字。** 用真實 TLT LEAPS 資料走引擎本人，
   「今天 × 現價」那一格印 **+81.9%**（Bull Call Spread）／**+81.4%**
   （Long Call）。這一格有一個不需要任何模型就知道的正確答案——標的還沒
   動、剛用 Ask 買進，價值只可能是「用 Bid 平掉」，即負的買賣價差
   （−11.5%／−4.2%）。畫面等於在說「你按下買進的瞬間就賺了八成」。
2. **看不到「這組 Spread 到底贏不贏過直接買一張裸買選擇權」。**
   舊版有過一個 1D 的「追平價格」提示（D1／#14），在 #103 已移除；
   使用者真正要的是在 Heatmap 上直接看到「哪一區 Spread 贏、哪一區
   裸買贏」的 2D 邊界。
3. **看不到「現在的 IV 相對自己的歷史算貴還是便宜」。** 候選卡上有
   Current IV，但沒有任何歷史定位。

外加一個資訊密度問題：Heatmap 每格印 `+128%` 這種帶正負號與百分號的字串，
在手機與桌面都吃掉大量橫向寬度，同樣的螢幕看得到的日期欄位偏少。

---

## Solution

四件事，一條依賴鏈：

- **先把估值修對**——換上 Bjerksund–Stensland (1993) 美式近似 ＋ 股利
  殖利率 q ＋ 同模型逐腿 IV 反解（價格錨定），讓 t=0 的理論價依定義回到
  市場中價，Heatmap 的每一格才有意義。q 從外部配息資料取得（Yahoo 為
  primary），有完整的降級鏈與三態誠實揭露。
- **再把 Crossover 疊上去**——在同一張 Heatmap 上畫出「Spread 報酬 ＝
  同到期、同買腿履約價、同 option type 的裸買部位報酬」的邊界。
- **IV History 獨立進行**——延續既定的 compact 模組設計；但它卡在
  #111 的 vendor 實測，該實測必須在可連網環境完成，**本 spec 不假裝
  它已經解決**。
- **Heatmap compact 小修**——與上面三條完全獨立，可隨時施工。

---

## Scope（本 spec 涵蓋）

| 代號 | 工作 | 對應既有 issue |
|---|---|---|
| **A. 估值修正** | BS93 ＋ q ＋ 同模型 IV 反解、Greeks 同步、golden／契約重產 | #113（擴充） |
| **B. q 資料管線** | Yahoo → FMP → Nasdaq 取得 TTM 現金配息、per-symbol 快取、三態揭露 | **新增**（#113 的前置） |
| **B0. Yahoo 端點 production 探測** | 確認 `chart?events=div` 免 crumb 可用 | **新增**（B 的前置，必跑） |
| **C. Crossover comparator 資料層** | 依買腿 option type 選 comparator、算報酬矩陣 | #115 |
| **D. Crossover overlay 渲染** | 2D 邊界疊在既有 Heatmap 上 | #116 |
| **E. IV History vendor 實測** | 三步驗證、選定 vendor | #111 |
| **F. IV History 功能** | Normalized Skew ＋ 雙腿 IV compact 模組 | #114 |
| **G. Heatmap compact 小修** | cell 去 `+`／`%`、縮 padding、桌面減寬 | **新增** |

## Non-Scope（本 spec 明確不做）

- **已 ACCEPTED 的施工一律不重開**：#103、#104、#105、#106、#107、#108、
  #109、#110、#112，以及 QA-FIX-1–5。特別是 #109／QA-FIX-1 的右側
  「vs 現價」±% 欄——**本 spec 的 G 項不得動它的格式或位置**。
- **不恢復舊的 1D「追平價格」UI**（D1／#14）。Crossover 一律是 Heatmap
  上的 2D 邊界。`catchup_price()` 與 `_spread_catchup_price()` 的既有
  行為不再沿用於新邏輯（#115 AC 已載明其 put 買腿找 call 的缺陷）。
- **Method E 不作為正式 q source。** 它只能當 diagnostic／交叉驗證，
  不得成為 production 取得 q 的路徑。
- **不用二項樹（CRR）當 production 估值器。** 實測 CRR300 一張 2.4 年
  LEAPS 矩陣要 9.85 秒 vs BS93 的 3.83 ms，且會引入被刻意排除的 numpy。
  CRR **只留在測試裡當精度對照基準**。
- **不發明新的校準方法。** 研究文件裡提到的「可行性下限 q」等衍生想法
  明確不採用。
- **不降低目前的 Heatmap 日期解析度**（QA-FIX-5 的 `GUI_MAX_GAP_DAYS = 31`
  維持不動）。G 項是縮寬度，不是縮欄數。
- **不做「每到期日連同前十名並排的大表格」**（QA1-05 既有裁示）。
- 多使用者隔離（#59）、外觀優化（QA-v2 延後項）、Dashboard 佔位區。

---

## User Stories

1. 作為使用者，我希望 Heatmap「今天 × 現價」那一格顯示的是我現在平倉會
   拿到的負報酬，而不是憑空的 +81%，這樣我才敢相信其他格子。
2. 作為使用者，我希望估值用的波動率跟資料源給我的報價是同一套模型算出來
   的，不要一邊拿美式含股利的 IV、一邊代進歐式無股利公式。
3. 作為使用者，我希望像 TLT 這種月配息 ETF 的配息被算進去，不要因為
   假設不配息而讓長天期 call 被系統性高估。
4. 作為使用者，我希望看得到「這次分析用的 q 是多少、從哪來、資料截至
   哪一天」，跟利率那三欄一樣透明。
5. 作為使用者，當配息資料抓不到時，我希望畫面明講「這組估值未經 carry
   校準」，而不是安靜地退回一個看起來正常但已知會印出 +81% 的狀態。
6. 作為使用者，我希望非配息標的（例如一般個股）不需要任何特例處理就能
   正常運作，q = 0 是正確答案而不是降級。
7. 作為使用者，我希望長天期價內 put 的提前履約價值被算進去，因為
   Heatmap 的深跌欄正好把 put 買腿推進那一區。
8. 作為使用者，我希望顯示的 Delta 跟估值用的是同一個模型，不要出現
   「看到的 Greeks 跟算出來的價格來自不同世界」。
9. 作為使用者，我希望估值變準之後，劇本庫卡片上的最高收益率不要莫名
   其妙全部跳動——那些數字的口徑本來就跟模型無關。
10. 作為使用者，我希望 Spread 成本走勢圖不要因為換模型而出現斷層。
11. 作為使用者，我希望在 Heatmap 上直接看到一條邊界，左右兩邊分別是
    「Spread 比較好」和「直接買一張比較好」。
12. 作為使用者，我希望 Bull Call Spread 的比較對象是 Long Call、
    Bear Put Spread 的比較對象是 Long Put，而不是永遠拿 call 來比。
13. 作為使用者，我希望比較對象用的是跟我的 Spread 同一個到期日、同一個
    買腿履約價的那張合約，這樣比較才公平。
14. 作為使用者，我希望邊界照實際算出來的樣子畫——它可以彎、可以斷、
    可以整條跑出圖外，不要被強行拉直。
15. 作為使用者，當邊界整條跑出圖外時，我希望圖例告訴我「整張圖都屬於
    哪一區」，而不是讓我誤以為沒有交叉。
16. 作為使用者，當比較對象的報價缺失時，我希望 overlay 誠實地不出現並
    附一行原因，不要讓我誤讀成「沒有交叉」。
17. 作為使用者，我希望 Crossover 的邊界是建立在已經修正過的估值上，
    不要先用有偏差的引擎畫一次、之後再默默移位。
18. 作為使用者，我希望主 Heatmap 和候選展開後的 Heatmap 都有 overlay，
    不要只有其中一張有。
19. 作為使用者，我希望 overlay 疊上去之後，既有的格子數字、顏色、日期軸
    和右側 vs 現價欄全部照舊。
20. 作為使用者，我希望看到候選的 Normalized Skew 現值與 1 年期
    percentile，知道現在的偏斜相對自己的歷史算不算極端。
21. 作為使用者，我希望買腿與賣腿各自的 IV 現值與 percentile 是第二層
    輔助資訊，不要跟主要資訊搶版面。
22. 作為使用者，我希望歷史線是 compact sparkline，手機上不要因此多出
    一張大卡片。
23. 作為使用者，當候選的期限超出 vendor 可靠支援的網格時，我希望
    percentile 留白並標示「超出可比網格」，不要拿最長可用 tenor 硬代。
24. 作為使用者，我希望 IV History 只呈現事實（數值、percentile、歷史線），
    不要出現「便宜」「貴」「好買點」這種評語。
25. 作為使用者，我希望 IV 歷史抓取失敗不會擋住頁面其他區塊渲染。
26. 作為使用者，我希望 Heatmap 每格只印數字（`128`、`-34`），不要
    `+128%` 這種把寬度吃掉的寫法，這樣同樣的螢幕能看到更多日期。
27. 作為使用者，我希望在說明文字裡看得到一次「這些數字是百分比」，
    這樣去掉 `%` 之後我還是知道自己在看什麼。
28. 作為桌面使用者，我希望 Heatmap 不要浪費橫向寬度，能不捲動就看到
    越多欄越好。
29. 作為手機使用者，我希望 Heatmap 保留橫向捲動，不要為了塞滿一個月
    的格子把字縮到讀不出來。
30. 作為使用者，我希望日期解析度維持現在的每月一格，不要因為版面調整
    被偷偷降回七欄。

---

## Implementation Decisions

### 1. 估值核心（A）——鎖定決策

**1.1 單一估值原語。** 新增純函式 `american_price(option_type, S, K, T, r, q, sigma)`
（Bjerksund–Stensland 1993 封閉解，約 40 行，純 stdlib），取代
`bs_price`／`clamped_price` 在情境估值路徑上的角色。它在 `b = r − q ≥ r`
（即 q ≤ 0）時對 call **逐位元退化成 Merton 歐式**（實測差 0.00e+00），
因此**涵蓋**「只做 Merton」的方案，不是多維護一套模型。

必須寫進 AC 的兩個數值防護（實測會 `OverflowError`）：`beta` 過大、
`b_inf − b_zero → 0`。

**1.2 同模型 IV 反解 ＋ 價格錨定。** 不再直接把 vendor 的 `implied_volatility`
餵進估值公式。改為：用同一份快照的**中價**、在**同一個** BS93＋q 模型下
逐腿反解出 σ，再用同一個模型重估。這使 **t=0 的理論價依定義回到市場中價**。

根因說明（決定這條的證據）：Cboe feed 的 `iv` 欄位是**美式、含股利模型**
反解出來的（用 Cboe 自家 `theo`／`iv` 對 758 筆真實鏈實測：美式反解與
vendor 差 0.0029 vol pt，歐式反解差 0.0491；CRR N=400 精算差 0.0004），
但引擎把它代進歐式、q=0 公式。兩端模型不同、中間沒有轉換，這就是
+81.9% 的機制。

**1.3 架構要求（成本數字成立的前提）。** IV 反解是**每腿一次**
（30–343 µs），**不是每格**。實作時必須在建 `CandidateView` 時就把校準好的
`(q, σ)` 掛在腿上，矩陣迴圈維持成 `(S, t)` 的純函式。違反這一條，
§成本估算（3.83 ms／矩陣）不成立。

**1.4 Greeks 與 Delta 同步換口徑。** `leg_greeks` 目前是 q=0 歐式解析式；
改為與新模型一致（delta 為 `e^{-qT}·N(d1)` 口徑），連帶 `net_delta`／
`vega_per_pt`／`decay_30d_return`／`effective_leverage`。

> **⚠ 這條有一個必須明講的下游後果（selection semantics）**：
> `ranking.rank()` 用 `classify(v.delta, p.delta_bands)` 把單腿候選分成
> conservative／balanced／aggressive 三組各取 top-N。實測真實 TLT 五檔
> 在 `delta_bands=(0.35, 0.65)` 下，**三檔從 conservative 移到 balanced**
> （delta 位移 −0.25 至 −0.27）。也就是說**選出來的單腿候選名單會變**，
> 不只是數字變。
>
> 本 spec 依「Greeks／Delta 與新模型保持一致」的鎖定決策，**接受這個
> 名單變動**（凍結分級口徑會製造「顯示的 delta 與分級用的 delta 不同」
> 的內部不一致）。但這超出 #113 現行 AC 的「數值變、語意不變」，
> 施工票必須明列此後果並在驗收時逐項對帳。

**1.5 血徑範圍（好消息，可縮小驗收範圍）。** 逐條追過引擎後確認**不受影響**：

- **Spread 排名完全不變**——`rank_spreads` 依 `spread_baseline_return`
  排序，而 `evaluate_spread` 的 `scenario_values` 是在**該 Spread 自身
  到期日**估的（T3／#17 既有裁示），`scenario_leg_value` 在
  `at >= expiry` 走內在價值分支，**與定價模型無關**。
- 因此 `best_return`／`representative_candidate`／劇本庫卡片數字不變。
- **V9 的 Spread 成本走勢圖不會斷層**——它取的 `cost` 是
  `long_leg.ask − short_leg.bid`，純市場報價、不經模型。
- `price_axis`／`date_axis`／`move_pct`／右側 ±% 軸完全不受影響
  （座標軸與市價衍生量，不經估值）。

**1.6 `clamped_price` 語意更正。** 它是 `max(BS, 內在價值, 0)`，docstring
寫「American no-arbitrage floor」是**誤導**——實測它對美式溢價的回收率
中位數 0.0%（229 筆有溢價的 put，箝制真正生效只有 46 筆）。它防的是
「模型值低於內在價值」這種荒謬結果，不是提前履約權利的價值。BS93 對
真實鏈 496 筆 0 筆違反內在價值下限，此箝制成為冗餘的不變量檢查——
可保留，但 docstring 措辭必須改寫。

### 2. q 資料管線（B）——鎖定決策

**2.1 Primary source。** Yahoo Finance chart 端點的 `events.dividends`
（免金鑰、單一 GET、stdlib `urllib`）：

```
GET https://query2.finance.yahoo.com/v8/finance/chart/{SYMBOL}
        ?range=2y&interval=1d&events=div,splits,capitalGains
→ chart.result[0].events.dividends = { key: {"amount": float, "date": unix_ts}, … }
```

**2.2 計算方式。**

```
D_ttm = Σ { amount | ex_date ∈ (today − 365 天, today] }   # 只計經常性現金分配
q     = ln(1 + D_ttm / S_snapshot)                          # 連續複利年率
```

`S_snapshot` ＝ **本次分析所用的 `ChainSnapshot.spot`**，不是 vendor 的價格。

四條配套規則（每條都有量化撐腰）：

| 規則 | 為什麼（實測代價） |
|---|---|
| 用**實際現金分配**，不用 30 天 SEC 殖利率 | q 差 0.582pp ＝ **3.59pp** 中位格差 |
| 除以**我們自己的 spot**，不抄 vendor 算好的殖利率 % | q 差 0.142pp ＝ 0.87pp |
| 用 **TTM（12 個月加總）**，不用「年化最近一次」 | 準度略優，且對單月雜訊有 **12 倍**抑制 |
| **不建配息時間表、公式裡不出現配息次數** | 相位只值 0.007pp，但次數數錯值 0.16pp |

**異常分配**：`events.capitalGains` 預設**排除**（Yahoo 放在獨立鍵，
零成本）。單期金額嚴重偏離同標的過去 12 期中位數時，寧可用中位數 × 期數
——**門檻數值屬施工票判斷，本 spec 不指定**。

**非配息標的**：`D_ttm = 0 → q = 0`，**不需要任何特例分支**。

**2.3 Backup 鏈（依序）。**

1. **FMP** `stable/dividends`（需免費金鑰，250 次／日）。該網域已在本專案
   Vercel 正式環境實測回 `401 Invalid API KEY`——**可達，只缺金鑰**。
2. **Nasdaq** `api/quote/{sym}/dividends`（免金鑰，另附 `annualizedDividend`
   可交叉驗證；Vercel 可達性未測、需瀏覽器等級標頭）。

**2.4 Method E 的定位。** **不作為正式 q source，只可 diagnostic。**
兩者在真實快照上差 0.024–0.078pp（外部 4.486–4.588% vs Method E 4.510%），
互為交叉驗證。建議（不強制）：若兩者差距超過某個門檻即記錄一則健全性
警訊——這是便宜且有訊息量的檢查，但**不得**讓 Method E 的結果覆蓋外部 q。

**2.5 施工形狀：沿用 r 的既有 pattern。** 本 repo 已解過一次「抓外部公開
資料、快取、陳舊、fallback、三態揭露」（`ratecurve.py` ＋ `data/treasury.py`
＋ `api_app/rate_cache.py`）。**預設照抄**：

- 純函式與 I/O 分離：解析 payload／加總／換算 q 的模組零 I/O、零 wall-clock。
- 抓取隔在 `option_chaser/data/`，stdlib `urllib` ＋ `json`，帶 User-Agent，
  逾時 15 秒，**任何連線／解析失敗一律收斂成 `FetchError`**（與 `cboe.py` 同款）。
- 多層備援鏈形狀比照 `treasury.py::fetch_curve` 的 `attempts` tuple。
- **注入式 loader**，比照 `service.RateCurveLoader` 與 `api_app` 的
  late-binding——測試才能離線、`/api/health` 才誠實。

**三處刻意偏離，必須寫進施工票**：

| 偏離 | r 現況 | q 需要 | 理由 |
|---|---|---|---|
| 快取的鍵 | 單筆、全站一條曲線 | **per symbol** | q 是標的的性質。`Storage` protocol 加 `get_dividend_cache(symbol)`／`save_dividend_cache(symbol, entry)`，memory／postgres 各補一份。**這是唯一有 schema 影響的部分。** |
| 陳舊窗 | 7 天 | **90 天** | 7 天對配息過短（一個月才一次事件），會讓一次短暫斷線把使用者踢回已知會印出 +81% 的 q=0。90 天 ≈ 一個季配週期，最多值 0.25pp 的 q（≈1.6pp 格差），仍遠優於退回 q=0（27.84pp）。 |
| 快取的內容 | 曲線本身 | **配息金額清單 ＋ `as_of`**，不是算好的 q | 抄別人的比例＝混進別人的價格基準，值 0.87pp 格差。q 每次用**當次 spot** 現算。 |

**重抓頻率**：每個市場日至多一次，per symbol，直接沿用 `rate_cache.py`
既有的 `market_day` 判準。**失敗短窗**：沿用 5 分鐘（`_FAILURE_MAX_AGE`）。
（理由不是 q 每天會變——它一個月才動 0.015pp——而是沿用既有機制成本為零。）

### 3. B0：Yahoo 端點 production 探測（必跑，非裁示）

**唯一會改變 primary 選擇的技術未知**：`v8/finance/chart?events=div` 在
Vercel 上不帶 cookie/crumb 能不能拿到 `events.dividends`。`yfinance` 把
每個端點都包 crumb 機制，但那是該 library 的習慣，未必是端點的要求。

**沒有便宜的逃生口**：`pyproject.toml` 仍把 `yfinance` 留在 `yf` optional
extra，就是為了讓 pandas/numpy 不進 lambda，所以 SDK 不在部署環境裡、
不能靠它做 crumb dance。

**若探測失敗 → FMP 直接升為 primary**，沿用本 repo 既有紀律，
**不需另開研究票**。本 repo 2026-08-05 已做過一次同樣的臨時探測端點，
流程見 `interest-rate-source-selection.md` §6。

### 4. Crossover（C／D）——鎖定決策

**4.1 Comparator 選取規則。** 與 Spread **買腿同 option type、同到期、
同履約價**的單腿裸買部位。買腿合約本身即該單腿部位，**直接取自買腿報價**，
不做 option type 轉換、不另尋合約。

- bull-call-spread（買腿是 call）→ **Long Call**
- bear-put-spread（買腿是 put）→ **Long Put**

修正既有 `_spread_catchup_price` 在買腿為 put 時錯誤尋找「同履約價 call」
的行為——該轉換為缺陷，不再沿用於新邏輯。

**4.2 成本口徑。** 比較對象用該單腿 **Ask**（最差成交），與 Spread 淨成本
口徑一致（A14.2）。

**4.3 資料層／渲染層分離。** C 只交付資料（comparator 區塊 ＋
`comparator_cells`，與 `matrix.cells` 同形狀），不做任何前端渲染；
D 負責 overlay。

**4.4 前端零金融計算紅線維持。** D 從 `matrix.cells` 與 `comparator_cells`
兩個矩陣導出邊界，只做**相等比較與內插**。

**4.5 邊界照實際結果繪製**：可彎曲、可分段、可出界。出界時以圖例說明
整圖屬於哪一區。**不遮蔽既有 cell 數字、不逐格標 WIN/LOSE、不建立
第二張獨立 Heatmap。**

**4.6 C 被 A 擋的依賴必須維持。** 實測現行（未修正）引擎會把
**5.1%–6.7%** 的格子畫在邊界的**錯誤一側**，而且錯的**幾乎全部貼著邊界**
——正是使用者唯一會盯著看的地方。BS93 把兩個真實案例、528 格的判錯
清成 **0**。

> 補充觀察（對 D 的版面有用）：邊界的「形狀」（單調斜向、往低價往後推）
> 在四個模型下都一樣，模型誤差表現為**邊界左右位移約一欄**。但這不構成
> 解除依賴的理由——位移的正是貼邊格子。若需求方基於排程想解除，代價
> 已量化，屬知情選擇。

### 5. IV History（E／F）

**5.1 延續既定的 compact IV History 模組設計**（#114 現行 AC 全數維持，
不在本 spec 重述）。要點：Normalized Skew `Ĝ = (σ_sell − σ_buy) / σ_ATM`
為主要資訊，Buy／Sell 腿 IV 為第二層；歷史序列在候選的 **(tenor, delta)
座標**上每日重錨定取值，不是固定合約的原始 IV 序列；1Y 視窗、日粒度；
超出可比網格時 percentile 留白並標示，不外插、不以最長可用 tenor 代理；
只呈現事實，評語字樣由測試明文封鎖。

**5.2 ⚠ #111 是未解決的實作依賴，本 spec 不假裝它已解決。**

- #111 目前狀態：**OPEN**，標籤 `needs-human-validation`。
- 它要求「不得在未成功完成至少一次真實 API 呼叫並驗證資料形狀前，
  聲稱 vendor 已確認」。
- 沙箱環境對絕大多數外部網域出站被阻擋，**無法在此環境完成**。
- 因此 **F（#114）在 E（#111）於可連網環境完成實測、選定 vendor 之前
  不得開工**。若排程上需要先動，只能做不依賴 vendor 形狀的部分
  （percentile 純函式與其 golden 測試），且必須明確標示為半成品。
- 三步優先序（Market Data App 免費層 → Alpha Vantage 免費金鑰 →
  ORATS 原件確認）與月費上限裁示，沿用 #111 現行 AC。

### 6. Heatmap compact 小修（G）

**6.1 Cell 文字格式。** 去掉正號與百分號：`+128%` → `128`、`-34%` → `-34`。
負號保留（那是數字本身的一部分）。

- 這是 `formatCell` 一個純函式的改動。
- **`formatMovePct`／`formatMovePctShort`（右側「vs 現價」欄）不動**
  ——那是 #109／QA-FIX-1 的驗收範圍，格式與位置皆維持。
- **說明文字（caption）必須補上一次「數值為百分比」**，否則去掉 `%`
  之後單位就沒有任何地方交代。

**6.2 密度。** 縮小 cell 的水平 padding 與最小寬度。
- **桌面**：盡量減少不必要的橫向寬度，讓同樣寬度看到更多日期欄。
- **手機**：保留橫向捲動，**不要求**硬塞完整一個月的格子，不縮字級硬塞。
- **日期解析度不得降低**——`GUI_MAX_GAP_DAYS = 31`（QA-FIX-5）維持不動。
  本項是縮寬度，不是縮欄數。

**6.3 不得回歸的既有驗收**：QA-FIX-1（±% 在最右欄、sticky right）、
QA-FIX-2（對比度 WCAG AA）、QA-FIX-3（`.detail-pane` 桌面密度）、
QA-FIX-5（日期軸密度）、#109（±% 完整／短格式雙寫 ＋ CSS 切換）。

---

## Architecture / Data-flow Changes

```
                    ┌─────────────────────────────────────────┐
   [新增 B]         │ data/dividends_yahoo.py  (stdlib urllib) │
   外部配息 ────────►│   Yahoo → FMP → Nasdaq  attempts chain   │
                    │   任何失敗 → FetchError                  │
                    └────────────────┬────────────────────────┘
                                     │ 金額清單 + as_of + source
                    ┌────────────────▼────────────────────────┐
                    │ Storage: get/save_dividend_cache(symbol) │ ← per-symbol（新）
                    │   market_day 節流 / 90 天陳舊窗          │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
   [新增 B]         │ dividends.py（純函式，零 I/O）           │
                    │   D_ttm = Σ amount(365d)                 │
                    │   q = ln(1 + D_ttm / snapshot.spot)      │ ← 用當次 spot
                    └────────────────┬────────────────────────┘
                                     │ q + 三態
   ChainSnapshot ────────────────────┤
   ratecurve (r, 已解) ──────────────┤
                    ┌────────────────▼────────────────────────┐
   [改 A]           │ valuation.py                             │
                    │  ① 逐腿一次：反解 σ  (BS93+q, 中價)      │ ← 每腿一次，非每格
                    │  ② 掛在 CandidateView 的腿上             │
                    │  ③ american_price(type,S,K,T,r,q,σ)     │
                    │     矩陣迴圈維持 (S,t) 純函式            │
                    └────────┬──────────────────┬─────────────┘
                             │                  │
              matrix.cells（值變、形狀不變）   comparator_cells [新增 C]
                             │                  │
                    ┌────────▼──────────────────▼─────────────┐
   [改 D]           │ 前端 Heatmap：只做相等比較與內插         │
                    │   邊界 overlay + 圖例                    │
                    │   [改 G] formatCell 去 +/%、縮 padding   │
                    └─────────────────────────────────────────┘
```

**不變的資料流**：`price_axis`／`date_axis`／`move_pct`、`rank_spreads`
與其下游（`best_return`、劇本庫卡片）、V9 成本走勢圖、refresh／storage
／scenario 生命週期。

---

## Contracts

**契約樣本**：`contracts/analysis_sample.json`（＋ `scenario_row_sample.json`
若受影響）必須重產，drift 測試通過。前端 mock 與後端 fixture 共用同一份。

**新增／變更欄位：**

| 層 | 欄位 | 語意 |
|---|---|---|
| `AnalysisParams` | `q_used: float` | 本次估值實際採用的 q |
| | `q_source: str` | `yahoo` / `fmp` / `nasdaq` / `none` — 比照 `ChainSnapshot.source` 的誠實紀錄慣例 |
| | `q_as_of: str \| None` | 配息資料截止日 |
| | `q_stale: bool` | 是否走陳舊備援 |
| 候選 | `carry_calibrated: bool` | 這組估值是否經過 carry 校準；false 時 UI 必須說得出「未經 carry 校準」 |
| 候選腿 | 校準後的 σ | 反解結果，供揭露與除錯（形狀由施工票決定） |
| 候選 | `comparator`（C） | option type、履約價、到期、成本——**前端可直接顯示「Long Call」／「Long Put」，不需自行推導** |
| 候選 | `comparator_cells`（C） | 與 `matrix.cells` **同形狀**；報價缺失時如實缺席（null／不存在），**不得偽造數值** |
| `Storage` protocol | `get_dividend_cache(symbol)` / `save_dividend_cache(symbol, entry)` | per-symbol；memory／postgres 各補一份 |

**值會變、形狀不變**：`matrix.cells`、Greeks 相關欄位
（`net_delta`／`vega_per_pt`／`decay_30d_return`／`effective_leverage`）。

---

## Fallback / State Semantics

**q 的四層降級**（全部「降級 ＋ 誠實標示」，比照 #112／RC1 的三態透明化）：

| 層 | 情況 | 行為 | 狀態 |
|---|---|---|---|
| 1 | 抓到、有配息 | 依公式算 q | `fresh` |
| 2 | 抓到、**確定無配息** | **q = 0** | **`fresh`（正確答案，不是降級）** |
| 3 | 抓不到、快取在 **90 天**窗內 | 用快取的**金額清單**、以**本次 spot** 重算 q | `stale`（顯示資料截止日） |
| 4 | 抓不到且無快取 | **退回現況**：q=0 **＋ 直接採用 vendor IV**（＝今天的完整行為）＋ `carry_calibrated=false` 旗標 | `degraded`（UI 必須明講） |

> **⚠ 第 4 層絕不可改用「q=0 ＋ 價格錨定」。** 實測 q=0 下 5 檔真實 TLT
> LEAPS 有 **3 檔的 IV 反解在數學上無解**（市場中價低於 q=0 模型的
> σ→0 下限）——那條路是**直接失敗**而不是降級。（細網格覆核：q ≥ 3% 時
> 5/5 檔皆可解。）

**單腿層級反解失敗**（市價落在模型可行區間外，例如報價陳舊或錯價）
→ 該腿沿用 vendor IV 並標記，**不要**用外插或猜的數字填補
（沿用「缺席就如實缺席、不偽造數值」既有原則）。

**Comparator 缺失**（C／D）→ comparator 區塊與 `comparator_cells` 如實
缺席，overlay 不出現並顯示一行原因，**不得讓使用者誤讀為「沒有交叉」**。

**IV History 降級**（F）→ vendor 無資料／超配額／超網格時顯示目前值 ＋
原因，不顯示 percentile，**不擋其他區塊渲染**；refresh 流程與 IV 歷史
抓取失敗隔離。

**「全部失敗必須明確 degraded、不得默默假裝正常」**——這是鎖定決策，
適用於上表第 4 層與 comparator／IV History 的每一個缺席態。

---

## Dependencies

```
B0（Yahoo production 探測，必跑）
 └─► B（q 資料管線）
      └─► A（BS93 + IV 反解 + Greeks + golden/契約重產）   ← #113
           └─► C（comparator 矩陣）                          ← #115
                └─► D（Heatmap overlay）                     ← #116（另需 #109 ✅ 已完成）

E（#111 IV vendor 實測，需可連網環境／人工）
 └─► F（#114 IV History 功能）                （另需 #103 ✅ 已完成）

G（Heatmap compact 小修）  ← 無依賴，可隨時施工
```

**外部／人工依賴（不在 agent 可完成範圍）：**

1. **B0 的實測**必須在 Vercel／可連網環境執行。
2. **E（#111）**必須在可連網環境完成真實 API 呼叫。
3. **FMP 免費金鑰是否申請**（見下方待裁示）。

---

## Acceptance Criteria

### A — 估值修正

- [ ] `american_price(option_type, S, K, T, r, q, sigma)` 為純函式、純
      stdlib、無新依賴；含 `beta` 過大與 `b_inf − b_zero → 0` 兩個數值防護
- [ ] q ≤ 0 時對 call 逐位元退化成 Merton 歐式（測試斷言差為 0.0）
- [ ] IV 反解**每腿一次**，校準後的 `(q, σ)` 掛在腿上；矩陣迴圈為
      `(S, t)` 純函式（測試或計數斷言反解呼叫次數不隨格數成長）
- [ ] **t=0 錨定**：以真實 TLT fixture，`analyzed_at × spot` 那一格等於
      「以 mid 平倉」的報酬，即 `(mid − net_worst)/net_worst`，
      **不再出現 +81.9%／+81.4%**
- [ ] Greeks／Delta 改用與估值一致的口徑；`net_delta`／`vega_per_pt`／
      `decay_30d_return`／`effective_leverage` 同步
- [ ] **單腿 delta 分級位移逐項對帳**：以真實 TLT 五檔驗證重分級結果符合
      預期（三檔 conservative → balanced），並確認這是**已知且接受**的
      selection semantics 變動
- [ ] **回歸斷言（不得變）**：`rank_spreads` 排序、`best_return`、
      `representative_candidate`、劇本庫卡片數字、V9 成本走勢圖
- [ ] **回歸斷言（不得變）**：`price_axis`／`date_axis`／`move_pct`／
      右側 ±% 欄
- [ ] `clamped_price` docstring 改寫（不再宣稱是 American no-arbitrage floor）
- [ ] 4 份 golden fixtures ＋ 契約樣本重產並經人工審閱，drift 測試通過
- [ ] `report.py` 的「模型限制」尾註更新：可宣稱「carry 從完全沒有變成
      量級正確」，**不得宣稱 Heatmap 已經準了**
- [ ] 效能：2.4 年 LEAPS 單張矩陣仍在毫秒量級（實測基準 3.83 ms），
      一次分析數十張矩陣遠低於 60 秒上限
- [ ] 不引入 numpy／不使用二項樹當 production 估值器

### B — q 資料管線

- [ ] 純函式層零 I/O、零 wall-clock，用固定 fixture 離線可重跑
- [ ] `q = ln(1 + D_ttm / ChainSnapshot.spot)`，`D_ttm` 為除息日落在過去
      365 天內的**經常性現金分配**加總
- [ ] `events.capitalGains` 預設排除
- [ ] 非配息標的：`D_ttm = 0 → q = 0`，走 `fresh` 狀態，**無特例分支**
- [ ] 抓取層 stdlib `urllib`＋`json`、帶 User-Agent、逾時 15 秒、
      任何失敗收斂成 `FetchError`
- [ ] 備援鏈 Yahoo → FMP → Nasdaq，形狀比照 `treasury.py::fetch_curve`
- [ ] 注入式 loader（比照 `RateCurveLoader`），測試離線、`/api/health` 誠實
- [ ] `Storage` 新增 per-symbol 配息快取；memory／postgres 兩份實作
      皆通過既有 storage contract 測試
- [ ] **快取存金額清單 ＋ `as_of`，不存算好的 q**；q 每次用當次 spot 現算
- [ ] `market_day` 節流（每市場日至多一次／symbol）、失敗短窗 5 分鐘、
      **陳舊窗 90 天**
- [ ] 四層 fallback 各有測試，特別是**第 4 層必須是 q=0 ＋ vendor IV
      （現況行為），不得是 q=0 ＋ 價格錨定**
- [ ] `q_used`／`q_source`／`q_as_of`／`q_stale` 四欄在 API 與 UI 皆可辨識
- [ ] UI 只格式化、不計算（專案紅線）
- [ ] Method E **不在 production 路徑上**；若實作交叉驗證，其結果
      **不得覆蓋**外部 q

### B0 — production 探測

- [ ] 在 Vercel／可連網環境實際呼叫 `chart?events=div`，記錄真實回應
- [ ] 確認免 crumb 是否可取得 `events.dividends`
- [ ] 確認金額是否已做拆分調整（`events.splits` 對照）
- [ ] 失敗則 FMP 升為 primary，**不另開研究票**
- [ ] 結果記錄進 `docs/research/`

### C — Comparator 資料層（#115 現行 AC 全數維持，此處只列增補）

- [ ] comparator 估值走**已修正**的引擎（A 完成後）
- [ ] bull-call-spread → comparator option type 必為 call；
      bear-put-spread → 必為 put；履約價與到期等於買腿（兩策略各至少
      一組明確斷言）
- [ ] `comparator_cells` 與 `matrix.cells` 同形狀
- [ ] 買腿報價缺失時 comparator 如實缺席
- [ ] 契約樣本含兩種策略各一範例（call／put comparator 皆有覆蓋）
- [ ] 本票**不做任何前端渲染**

### D — Overlay 渲染（#116 現行 AC 全數維持，此處只列增補）

- [ ] 前端只做相等比較與內插，零金融計算
- [ ] 邊界可彎曲／可分段／可出界；出界時圖例說明整圖屬於哪一區
- [ ] 不遮蔽 cell 數字、不逐格標 WIN/LOSE、不建立第二張 Heatmap
- [ ] 圖例標示：cell 值仍是 Spread Return；邊界定義為兩者相等；
      comparator 合約標籤與成本口徑
- [ ] comparator 缺失時 overlay 缺席 ＋ 一行原因
- [ ] 主 Heatmap 與候選展開後的 Heatmap 皆有 overlay
- [ ] **不得回退 #109／QA-FIX-1 的右側 ±% 欄**；兩者共存
- [ ] **不恢復舊 1D 追平價格 UI**

### E — IV vendor 實測（#111 現行 AC 全數維持）

- [ ] **不得在未成功完成至少一次真實 API 呼叫並驗證資料形狀前，
      聲稱 vendor 已確認**

### F — IV History（#114 現行 AC 全數維持）

- [ ] **開工前置**：E 已完成且已選定 vendor
- [ ] 評語字樣（便宜／貴／好買點／建議進場）由測試明文封鎖

### G — Heatmap compact

- [ ] `formatCell`：`+128%` → `128`、`-34%` → `-34`（負號保留）
- [ ] **`formatMovePct`／`formatMovePctShort` 與右側欄位置格式不變**
- [ ] caption 補上一次「數值為百分比」
- [ ] cell 水平 padding／最小寬度縮小；桌面在固定寬度下可見欄數增加
      （以量測數字驗收，不用感覺）
- [ ] 手機保留橫向捲動；不縮字級硬塞；不要求塞滿一個月
- [ ] **`GUI_MAX_GAP_DAYS = 31` 不動**，日期欄數不減少
- [ ] 顏色與中性帶（`NEUTRAL_BAND` 0.05、`COLOR_CAP` 1.0）不變
- [ ] QA-FIX-1／2／3／5 與 #109 的既有驗收皆不回歸

---

## Migration / Backward Compatibility

- **無資料庫 migration 需求，除了一項**：`Storage` protocol 新增 per-symbol
  配息快取（memory ＋ postgres 兩份）。既有 scenario／result／snapshot／
  event／rate cache 結構完全不動。
- **既有已落盤的 result JSON 不重算、不回填。** 換模型後新舊快照的
  `matrix.cells` 口徑不同——**這在 V9 成本走勢圖上不會造成斷層**
  （那條線取的是 `long_leg.ask − short_leg.bid`，純市場報價）。若未來要
  在 UI 上並列新舊快照的模型數字，需另行處理，不在本 spec 範圍。
- **契約樣本與 golden fixtures 會漂移**，這是預期內的、由 A 一次性重產。
  前端 mock 與後端 fixture 共用同一份，漂移必須同步。
- **CLI 行為**：`matrix_lines` 的日期欄數維持 7（QA-FIX-5 的 `max_gap_days=None`
  路徑），G 項只影響 GUI。CLI 報告的數值會隨模型改變，golden 一併重產。
- **API 相容性**：新增欄位為純加法；`carry_calibrated=false` 時舊前端仍能
  渲染（只是不顯示降級提示），不造成硬性破壞。

---

## Testing Decisions

**什麼是好測試**：只測外部行為，不測實作細節。已建立的反例與教訓沿用：

- 位置／版面用**幾何量測**（`boundingBox`）而非存在性斷言——QA-FIX-1
  與 QA-FIX-4 都是因為原本用文字存在性／`isVisible()`，讓誤置與捲到
  畫面外的元素照樣通過。
- 收合狀態用 `toBeVisible()` 而非 `toBeInTheDocument()`——巢狀
  `<details>` 收合時內容仍在 DOM 裡（#107 的教訓）。

**測試接縫（沿用既有，不新增）：**

| 層 | 接縫 | 用途 |
|---|---|---|
| 引擎純函式 | 直接單元測試 | `american_price`、IV 反解、`dividends` 換算、percentile |
| 後端唯一接縫 | **HTTP API**（測試客戶端 ＋ 記憶體儲存假體） | 三態欄位、fallback 四層、comparator 缺席態、IV 端點三態 |
| 注入式 port | `RateCurveLoader` 同模式的 dividend loader、IV vendor client | 測試離線，**不打真實 vendor** |
| 契約 | `contracts/*.json` drift 測試 | 前後端共用同一份樣本 |
| 前端元件 | Vitest ＋ mock API | `formatCell`、overlay 存在／缺席、comparator 標籤 |
| E2E | Playwright 桌面 ＋ 手機 viewport | 版面密度、橫向捲動、overlay 可見 |

**精度驗收的既有手法（沿用）**：用 **CRR 二項樹當測試內的精度對照基準**
——研究文件所有精度數字都是這樣產生的。CRR **只在測試裡**，不進 production。

**必須有的具體測試：**

1. **t=0 錨定**：真實 TLT fixture，`analyzed_at × spot` 格 == `(mid − net_worst)/net_worst`。
2. **q ≤ 0 退化**：BS93 對 call == Merton 歐式，差為 0.0。
3. **反解次數**：不隨矩陣格數成長（架構要求 1.3 的守門）。
4. **fallback 第 4 層**：斷言走的是 q=0 ＋ vendor IV，**不是**價格錨定。
5. **delta 分級位移**：真實 TLT 五檔的重分級逐項對帳。
6. **不變量回歸**：`rank_spreads`／`best_return`／劇本庫卡片／V9 成本
   走勢圖／`move_pct`／±% 欄。
7. **comparator option type**：兩策略路徑各一組明確斷言。
8. **G 項密度**：桌面固定寬度下可見欄數的**量測**斷言；
   `formatCell` 純函式測試；QA-FIX-1 的 ±% 欄格式回歸斷言。
9. **對比度**：`src/contrast.test.ts` 既有守門持續通過。

---

## Construction Order

| # | 項目 | 被誰擋 | 備註 |
|---|---|---|---|
| 1 | **G**：Heatmap compact 小修 | 無 | 獨立、可先出貨，早期可見成果 |
| 2 | **B0**：Yahoo production 探測 | 無（需可連網環境） | 結果決定 B 的 primary |
| 3 | **B**：q 資料管線 | B0 | 含 Storage per-symbol 快取 |
| 4 | **A**：BS93 ＋ IV 反解 ＋ Greeks ＋ 重產 | B | ＝ #113 擴充版 |
| 5 | **C**：comparator 矩陣 | A | ＝ #115 |
| 6 | **D**：overlay 渲染 | C | ＝ #116 |
| 7 | **E**：IV vendor 實測 | 無（需可連網環境／人工） | ＝ #111，可與 1–6 並行 |
| 8 | **F**：IV History 功能 | E | ＝ #114 |

> A 與 B 也可以拆成「先做 A 的估值原語（q 當參數傳入，先用固定值跑測試）
> → 再接 B 的真實 q」，讓 B0 的實測不擋住引擎工作。這屬施工票的拆法判斷。

---

## Out of Scope

見上方「Non-Scope」。另外重申幾條容易被順手做掉的：

- 不重開任何已 ACCEPTED 的票。
- 不動 QA-FIX-1 的右側 ±% 欄格式與位置。
- 不把 Method E 接進 production 的 q 路徑。
- 不引入 numpy／pandas 進 lambda。
- 不發明新的 q 校準方法（「可行性下限 q」等明確不採用）。
- 不在 fallback 第 4 層使用「q=0 ＋ 價格錨定」。

---

## Further Notes

### 待裁示（不擋開工，但施工票要帶著走）

1. **FMP 免費金鑰要不要申請。** #74 當時裁示「先不申請」。q 的情況不同：
   **最終 fallback 是退回已知會印出 +81.9% 的行為**，備援深度的價值比
   利率那次高。建議重新裁示。
2. **ToS 取捨。** Yahoo（灰色、免鑰、**不擴大**本 repo 既有曝險）已由
   鎖定決策選為 primary；但 FMP 作為 backup 若要啟用，其「展示／再散布
   可能需簽 Data Display and Licensing Agreement」的問題需要需求方判斷
   ——研究文件明說無法代為判斷「把 q 當模型輸入並顯示一個衍生數字」
   算不算再散布。
3. **異常分配的門檻數值**（單期偏離中位數多少倍才改用中位數 × 期數）
   ——研究文件明說「門檻要多少、要不要做，屬實作票範圍」，未驗證。
4. **Method E 交叉驗證的告警門檻**（研究建議 0.5pp 量級，非驗證值）。

### 誠實揭露（必須進產品文案，不可誇大）

- 「用一個連續 q 描述固定美元配息」這個抽象本身在 Heatmap 網格邊緣
  自帶模型誤差。**不能宣稱換上 q 之後 Heatmap 就準了**；可以宣稱的是
  **「carry 從完全沒有變成量級正確」**。
- TTM 口徑對趨勢有約半年落後：分配以每月 1% 成長時，TTM 與「年化最近
  一次」差 0.25pp（≈1.52pp 格差）。在配息快速轉折期會系統性落後——
  這是知情取捨，應寫進模型限制揭露。
- 研究文件的精度數字（BS93 中位 0.18–0.33pp）來自**兩個部位、兩個標的、
  各一個快照**（TLT call／配息主導、YETI put／美式主導），**不是橫斷面
  統計**，不是保證的誤差界。
- 配息金額本身是搜尋索引轉述、非一手查證（有三來源自洽交叉檢查但
  不等於一手）。B0 的實測會順帶解決這一點。

### 已被本 spec 解決的既有裁示閘門

- **#113 的「需求方核准 #110 建議方法」人工閘門**：已由本 spec 的鎖定
  決策回答——採 BS93 ＋ 外部 q；**Method E 不作為正式 q source**。
  #113 施工票應更新 AC 以反映此決定與 delta 分級位移的後果。
- **#115 被 #113 擋的依賴**：維持，實測數據支持（5.1–6.7% 貼邊格子
  會畫錯側）。
- **#116 被 #109 擋的依賴**：#109 已完成，此依賴已解除。

### 施工依據

- `docs/research/heatmap-valuation-method-selection.md`（估值方法選型）
- `docs/research/dividend-yield-source-selection.md`（q 資料源與換算口徑）
- `docs/research/valuation-carry-method-comparison.md`（#110 方法比較）
- `docs/research/historical-options-iv-data-sources.md`、
  `docs/research/iv-relative-history-methodology.md`（IV History）
- `docs/research/interest-rate-source-selection.md` §6（production 探測流程先例）
- issue #102（MVP V3 母 spec）與 #111／#113／#114／#115／#116 現行 AC
