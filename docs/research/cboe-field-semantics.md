# Cboe 延遲報價欄位語意調查：`iv=0` / `open_interest=0` 是什麼意思，以及該不該自己反推 IV

研究日期：2026-08-04。前一份資料源調查見
`docs/research/option-chain-data-sources.md`（OPC 的資料源、各家 API 比較），
本文不重複那些內容，只處理「拿到 Cboe payload 之後，欄位該怎麼判讀」。

取材限制聲明（沿用前次）：本沙箱出口 proxy 對 `cdn.cboe.com`、`www.cboe.com`、
`barchart.com`、`optionsprofitcalculator.com`、`deepwiki.com` 一律回 403
（CONNECT tunnel failed / HTTP 403），**無法即時抓取 Cboe 端點**；curl 實測
`https://cdn.cboe.com/api/global/delayed_quotes/options/TLT.json` 回
`curl: (56) CONNECT tunnel failed, response 403`。因此本文的證據分三級：

- **實測實證**：本次分析的**真實 Cboe payload 原檔**（第三方 repo 內
  committed 的完整回傳，可逐筆檢視、可重跑統計）——這是本文最強的證據，
  下文所有數字皆可由 §7 的原檔重現。
- **原始碼實證**：GitHub 上可直接抓取的開源解析器原始碼。
- **搜尋索引轉述**：被 403 擋下的官方頁面，內容經搜尋引擎索引摘錄取得，
  標示為「搜尋索引轉述」，未逐字核對原文。

---

## 1. 結論摘要

### 1.1 三個關鍵發現（皆有實測實證）

**(A) `iv: 0.0` 是「解不出來／不計算」的哨兵值，不是「波動率為零」。**
它的觸發條件是**深度價內／價外（vega≈0）＋ 報價已無時間價值**，而**不是**
「遠期／LEAPS」。在真實 Cboe 全鏈樣本（YETI，758 筆，2023-08-11）裡：

| 到期天數 | 合約數 | `iv=0` 筆數 |
|---|---|---|
| 0（當日到期） | 82 | 23 |
| 7 | 94 | 19 |
| 14 | 84 | 9 |
| 21–49 | 200 | 13 |
| 98 | 36 | 0 |
| 161 | 94 | 14 |
| 189 | 34 | 0 |
| 315 | 36 | 0 |
| **525（LEAPS）** | **42** | **1** |

**最遠期的 LEAPS 反而幾乎沒有 `iv=0`。**`iv=0` 的 82 筆裡，55 筆
`|delta| ≥ 0.99` 或 `≤ 0.01`，只有 6 筆 `|delta| < 0.9`；反過來看，
`|delta| ≥ 0.95` 的 184 筆裡有 71 筆（39%）`iv=0`。

**(B) 需求方貼出的兩組 TLT 樣本，全部是「已到期／當日到期」的合約，
因此不能用來證明 LEAPS 會拿到 `iv=0`。**

- 樣本 A：報價時間 2026-08-01（週六），合約 `TLT260731*` ＝ **前一天
  （7/31 週五）已到期**。
- 樣本 B：報價時間 2026-08-03 20:38 ET（收盤後），合約 `TLT260803*` ＝
  **當天到期**。

樣本 A 裡 `TLT260731C00079500` 與 `TLT260731P00079500` **共用同一個
`iv=2.8028`（280%）**、且所有 call 的 `delta` 都是 1.0——這正是
T→0 時反推退化的典型症狀（時間價值趨近 0，任何 σ 都解得出／解不出）。
**要判斷 TLT 的 2028 年 LEAPS 到底有沒有 `iv=0`，必須另外抓一次
遠期合約的樣本**（§8 驗證清單第 1 項）。

**(C) 自己反推 IV 救不回這些合約——數學上無解。**
對真實樣本裡「`iv=0` ＋ 有雙邊報價 ＋ DTE>0」的 32 筆 call 做二分法反推
（r=5.3%，2023-08 的短率水準）：

- **可解：2 筆**
- **無解：30 筆**——因為 `mid < S − K·e^{−rT}`（報價低於**歐式遠期內在值**）。

例：DTE=7、K=35、mid=10.00，而 `S − K·e^{−rT}` = 10.006。這在歐式 BS
底下沒有任何 σ 能解出，任何 solver 都只會拋
`BelowIntrinsicException` 或回 NaN。整體看，`iv=0` 的 82 筆裡有 47 筆
`mid < 未貼現內在值`（貼現後更多），而 `iv≠0` 的 676 筆裡只有 2 筆如此。
**Cboe 之所以填 0，就是因為它自己也解不出來。**

### 1.2 建議（本 app 該怎麼處理 `iv=0` 與 `OI=0`）

1. **`iv=0 → None` 的映射保留不動**（`option_chaser/data/cboe.py:58-68`
   已經是對的）。0.0 在語意上是「未計算」，映射成缺值正確；把它當成
   「零波動率」餵進 BS 才是真正的錯誤。

2. **不要新增「自己反推 IV」的邏輯。**實測 32 筆只救得回 2 筆（6%），
   其餘 30 筆在數學上無解；付出的代價是一個 solver、一套例外處理、
   以及「用陳舊 last 反推出的垃圾 IV」的新風險（§4.2）。投報率極差。

3. **真正該做的是讓「已無時間價值」的合約不必經過 IV 這一關。**
   這些深度 ITM 合約的市價就是平價（parity），BS 在 σ→0 的極限值等於
   遠期內在值，**用哪個 σ 幾乎不影響定價**。可行做法（工程判斷，非本文
   裁示）：在 adapter 或過濾層加一條旁路——若
   `mid ≤ max(S − K·e^{−rT}, 0) + ε`，標記該腿為「無時間價值」，
   `implied_volatility` 補一個下限（如 0.01）並在 UI 揭露來源，
   估值端既有的 `clamped_price()`／`intrinsic_value()`
   （`option_chaser/valuation.py:182-189`）本來就會把價格夾在合理區間。
   ⚠ 但要意識到：這種腿實質上「等同持股」，槓桿與收益率結構跟一般
   spread 不同，是否納入排名屬產品決策。

4. **`open_interest` 不該當硬條件。**OI 是 OCC 收盤後結算、隔天早上才
   發布的 **T+1 落後數字**（§3，一手佐證），它回答的是「昨天收盤時有多少
   未平倉」，不是「現在有沒有人報價」。實測樣本裡**每個天期都有
   `OI=0 但 volume>0`** 的合約。建議把 `min_oi` 從硬過濾降級成排序懲罰
   ／顯示警語，或直接改抓 Cboe 已經提供、但目前 adapter **沒有取用**的
   `bid_size` / `ask_size`——那才是「現在有沒有人掛單、掛多少口」的直接
   證據。

5. **候選池被殺光的主因，實測是 OI 門檻而不是 IV。**對同一份真實全鏈跑
   本 app 的四道過濾（call、`min_oi=10`）：

   | DTE | 總數 | 報價 OK | IV OK | OI/量 OK | Spread OK |
   |---|---|---|---|---|---|
   | 0 | 41 | 25 | 15 | 10 | 10 |
   | 14 | 42 | 38 | 31 | **7** | 5 |
   | 49 | 28 | 27 | 26 | **1** | 1 |
   | 161 | 47 | 29 | 28 | 27 | 21 |
   | **525** | **21** | **21** | **20** | **19** | **19** |

   525 天期（LEAPS）從 21 筆只掉到 19 筆，**IV 與 spread 幾乎沒殺人**；
   中天期（14–49 天）則被 OI≥10 砍掉 8–9 成。若 TLT 的遠期候選池真的
   被殺光，最該先查的是 OI 門檻與該期的掛牌履約價密度，而不是 IV。

6. **`max(0.10, 0.15 × mid)` 的 spread 規則對 LEAPS 是**寬鬆**的，不是元凶**
   （§5）。實測相對價差中位數：≤30 天 6.6%、31–90 天 11.3%、91–365 天 4.2%、
   **>365 天 3.9%**（p90 僅 11.4%）。長天期選擇權**絕對**價差寬，但單價高，
   **相對**價差反而最窄。

---

## 2. Q1：Cboe `iv` 欄位的語意

### 2.1 沒有官方文件（已確認）

`cdn.cboe.com/api/global/delayed_quotes/` 是**無公開文件的非正式端點**
（前次調查已確認，`docs/research/option-chain-data-sources.md` §3.2）。
本次再查一輪，Cboe 官方站上**找不到任何說明 `iv` 何時填 0 的文字**。
另外要記著：Cboe 延遲報價頁的條款「strictly prohibits downloading delayed
quote table data using auto-extraction programs or queries」，資料歸屬
Cboe LiveVol（https://www.cboe.com/delayed_quotes/cboe ，搜尋索引轉述）。

### 2.2 計算方是誰、用什麼模型（搜尋索引轉述）

Cboe 的 IV／Greeks 由 **Cboe Hanweck** 產出，方法為
「industry-standard binomial tree with discrete dividends … to allow for
accurate pricing of both European and American exercise styles」，
Delta/Gamma/Vega/Theta/Rho「computed from real-time theoretical prices」
（https://www.cboe.com/services/analytics/hanweck/implied_volatility ，
搜尋索引轉述）。

⚠ **這對本 app 是重要的口徑差**：Cboe 的 `iv` 是**美式二項樹**反推的，
本 repo 的估值是**歐式 BS**（`option_chaser/valuation.py:21-37`）。
對深度 ITM 的美式 call（尤其有配息的 TLT），兩者本來就不等價——
美式提前履約溢價會讓市價落在歐式 BS 的可行區間之外，這也正是 §1.1(C)
那 30 筆「歐式無解」的根本原因。

### 2.3 開源解析器一致把「iv > 0」當成「有值」（原始碼實證）

沒有任何開源專案把 `iv=0` 當有效值處理；相反地，多個獨立專案顯式把它當缺值：

- `chriswong6031-creator/mastermind-terminal`（`ingest/collect_options.py`）：
  「Per expiry: find nearest-to-spot strike, compute mid(call_iv, put_iv)
  **dropping zero/absent**.」
- `respectfulnrespected59-source/marketpulse`（`options.py`）：
  「For any contract CBOE leaves **ungraded** we fall back to a
  Black-Scholes-Merton computation from the IV」；程式碼
  `if len(g) < 5 and iv > 0:  # backfill any missing greeks with Black-Scholes`
  ——即 **`iv > 0` 是「這筆有沒有被 Cboe 算過」的判斷式**。
- `Kza56/OFK_Atas_GEX`（`OFK_GEX_Pipeline/data_fetcher_NQ.py`）：
  `if gamma == 0 and iv > 0 and dte > 0:` 再自行補算 gamma——同樣把
  `iv > 0` 當前提。
- OpenBB 官方 Cboe provider
  （https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py ）
  只做 `"iv": "implied_volatility"` 欄位改名，**不做任何 0 值處理**——
  即 OpenBB 使用者拿到的就是原始 0.0。

「Cboe 有沒有一條成文規則」——**查不到**（§7）。但「0.0 是哨兵、不是真值」
這件事，在實測統計（§2.4）與跨專案原始碼慣例上都站得住。

### 2.4 實測：`iv=0` 到底跟什麼相關（實測實證）

樣本：`https://github.com/eo1989/textbook_notes/blob/master/data/YETI.json`
——一份 committed 的**完整真實 Cboe 回傳**，`timestamp` 2023-08-11 16:27:37，
`current_price` 44.97，`iv30` 35.615，`data.options` 758 筆，涵蓋 13 個到期日
（DTE 0 至 525）。真實性交叉檢核：對 121 組價平附近的 call/put 做賣權買權平價
（`C − P + K·e^{−rT}`），推得的標的價中位數 **44.961**，與 `current_price`
44.97 相差 0.02%——資料自洽，不是捏造的樣本。

統計結果（腳本可重跑，見 §7）：

| 檢驗 | `iv = 0`（n=82） | `iv ≠ 0`（n=676） |
|---|---|---|
| `mid < 未貼現內在值` | 47（57%） | 2（0.3%） |
| `\|delta\| ≥ 0.99` 或 `≤ 0.01` | 55（67%） | — |
| `\|delta\| < 0.9` | 6（7%） | — |
| `last_trade_price = 0` | 59（72%） | 265（39%） |

判讀：

- **主因是「報價裡已經沒有時間價值」**——57% 的 `iv=0` 合約，其 mid 甚至
  低於未貼現內在值（貼現後比例更高）。這類報價在歐式 BS 下無解。
- **次因是 vega≈0 的深度價內／價外**——67% 的 `iv=0` 合約 delta 已貼到
  0 或 1，此時價格對 σ 幾乎不敏感，反推在數值上無意義。
- **與「有沒有成交過」只是弱相關**（72% vs 39%），不是主因；所以
  「Cboe 只對有成交的合約算 IV」這個假說**不成立**。
- **與到期日長短無關**（§1.1(A) 的表）——`iv=0` 集中在 DTE≤14，
  525 天期只有 1/42。

**推論（非一手文件）**：Cboe/Hanweck 的流程是「對每筆報價跑二項樹反推，
解不出來或落在無效區間就填 0.0」，沒有「不算遠期」「不算沒成交的」這種規則。

---

## 3. Q2：`open_interest` 的語意

### 3.1 OI 是 T+1 落後數字（一手佐證）

OCC 官方的 Volume and Open Interest 頁面
（https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest ）
即為每日發布的 OI 報表。業界說法一致（搜尋索引轉述）：

- OI 由 OCC 在**收盤後**依已結算成交重新對帳，**隔天早上**才發布；
- 因此 OI 不是即時資料，「what you see on your screen reflects yesterday's
  session, not live intraday activity」
  （https://www.interactivebrokers.com/campus/podcasts/ibkr-podcasts/what-is-option-open-interest-and-how-to-analyze/ 、
  https://www.optionsplaybook.com/options-introduction/open-interest 、
  https://www.tradingview.com/support/solutions/43000685269-open-interest/ ，
  搜尋索引轉述）。

### 3.2 兩組樣本的差異有沒有「documented explanation」

**沒有 Cboe 的成文說明**（端點無文件）。但 T+1 語意足以解釋樣本 B：

- 樣本 B 的 `TLT260803*` 是**當天到期**的合約。若這些部位是**當天新開的**
  （日內開倉、當天平倉／到期），前一晚的結算 OI 本來就是 0，
  而 `volume` 180/241/64 是**當天**的成交量——**`OI=0` 且 `volume>0`
  完全正常，不是資料錯誤**。
- 實測佐證：真實 YETI 樣本裡，**每一個天期都存在 `OI=0 且 volume>0`**
  的合約（DTE 0:4 筆、7:6 筆、28:2 筆、42:3 筆、49:1 筆、525:1 筆）。
- 樣本 A 有 OI（110/42/310/2163）也正常——那批合約已掛牌一段時間，
  前一晚結算 OI 自然非零。

### 3.3 這對過濾器的意義

`oi_volume_ok` 目前是 `open_interest >= 10 and volume >= 0`
（`option_chaser/filters.py:29-30`）。兩個問題：

1. `volume >= 0` **恆真**，這一半條件不做事（`volume` 在 adapter
   已被轉成 `int(... or 0)`，永遠 ≥0）。
2. `open_interest >= 10` 拿一個**昨天的、對新掛牌／新交易履約價天生為 0
   的數字**當硬門檻。實測它是本 app 中天期候選池的最大殺手
   （§1.2 第 5 點的表：DTE 49 從 26 筆殺到 1 筆）。

真實全鏈的 OI≥10 通過率（僅計有雙邊報價者）：≤30 天 71/265、
31–90 天 23/121、91–365 天 97/172、>365 天 34/42。

---

## 4. Q3：自己反推 IV 的產業做法（本文重點）

### 4.1 用哪個價格反推

三種主流口徑，各有明確出處：

| 口徑 | 誰在用 | 出處 |
|---|---|---|
| **mid（NBBO 中價）** | ORATS：「computes theoretical values and volatility based on the implied volatility of the **average of the market bid ask prices**」；另提供 bid-IV／ask-IV／mid-IV 三條 | https://orats.com/docs/core-research 、https://docs.orats.io/datav2-api-guide/core-research.html （搜尋索引轉述） |
| **last，缺才用 mid** | Barchart：「Implied Volatility, which is based on the Binomial model, is calculated using the **delayed last price if it exists**. If the last price does not exist (for today) then we use the **midpoint between the bid and the ask price**.」 | https://www.barchart.com/stocks/quotes/$SPX/volatility-greeks （搜尋索引轉述） |
| **只用雙邊報價（先過濾流動性）** | CME Group Options Analytics：「only provides data for **two-sided markets**, pre-filtering for liquidity, ensuring Greeks and implied volatilities are based on actual, tradable prices, **not stale quotes**」 | https://www.cmegroup.com/market-data/greeks-and-implied-volatility-data.html （搜尋索引轉述） |

**判讀與建議口徑**：**mid 優先，last 只在明確標記為降級時使用**。
理由就寫在本 repo 自己的 fixture 裡——`TLT260731C00065000` 的
`last_trade_price` 是 21.55，但 `last_trade_time` 是 **2026-06-30**
（一個月前），而同一筆的 `bid/ask` 是 17.15/17.30、Cboe 自己的
`theo` 是 17.235。**用那個 last 反推會得到完全錯誤的 IV。**
Barchart「last 優先」的做法會被陳舊成交毒害；CME 的「先過濾雙邊市場」
才是穩健口徑。

### 4.2 用什麼求根法

| 方法 | 特性 | 出處 |
|---|---|---|
| **Newton-Raphson（用 vega 當導數）** | 快，但 `Δσ = f(σ)/vega`，**vega→0 時發散**；深度 ITM／OTM、近到期一律不穩 | https://www.interactivebrokers.com/campus/ibkr-quant-news/implied-volatility-formulation-computation-and-robust-numerical-methods/ （搜尋索引轉述） |
| **Bisection／Brent** | 需要 bracket，保證收斂但慢；Brent＝bisection＋反二次插值 | QuantLib `ImpliedVolatilityHelper::calculate()` 用 **Brent**：`solver.setMaxEvaluations(maxEvaluations)`、`solver.solve(f, accuracy, guess, minVol, maxVol)`，guess=`(minVol+maxVol)/2.0`（原始碼實證：https://github.com/lballabio/QuantLib/blob/master/ql/instruments/impliedvolatility.cpp ） |
| **Newton＋bisection 混合** | 業界常見折衷 | 同 IBKR 文 |
| **Jäckel「Let's Be Rational」** | **業界標準**：四段有理函數初值 ＋ 四階 Householder 迭代，**最多兩次迭代達到 64-bit 機器精度**，單次約 1 微秒（比同精度舊算法快 5 倍以上） | 論文 http://www.jaeckel.org/LetsBeRational.pdf （Wilmott, 2015；https://onlinelibrary.wiley.com/doi/abs/10.1002/wilm.10395 ） |

**收斂容差的實際數字**（原始碼實證，
https://raw.githubusercontent.com/vollib/py_lets_be_rational/master/py_lets_be_rational/lets_be_rational.py ）：
`implied_volatility_maximum_iterations = 2`，內部註解稱
「Theoretically accurate to (better than) precision ε = 2.23E-16」。
Python 生態的實作是 `py_vollib` / `py_lets_be_rational`
（https://github.com/vollib/py_vollib ）。

### 4.3 已知的失敗案例，以及該怎麼辦

`py_lets_be_rational` 的失敗處理是**顯式拋例外**，不是回傳哨兵值
（原始碼實證，同上檔案 ＋
https://github.com/vollib/py_lets_be_rational/blob/master/py_lets_be_rational/exceptions.py ）：

```
if price < intrinsic:   raise BelowIntrinsicException
if price >= max_price:  raise AboveMaximumException
```

四類典型失敗：

1. **報價低於內在值** → `BelowIntrinsicException`。這正是本案 30/32 筆的
   狀況。成因：(a) 美式深度 ITM 以平價成交，歐式模型容不下；
   (b) 買賣價差跨過內在值；(c) 標的價與選擇權報價快照時間不同步。
   已知 issue：https://github.com/vollib/py_vollib/issues/5 （Deep ITM
   European Options，錯誤訊息「The volatility is below the intrinsic
   value」，**至今 open、無官方解法**）、
   https://github.com/vollib/py_vollib/issues/18 （Dealing with deep
   in-the-money index option）、
   https://github.com/vollib/py_vollib/issues/13 （負利率下的
   BelowIntrinsicError）。
2. **vega≈0（深度 ITM/OTM、近到期）** → Newton 發散；Brent 則會撞上
   「root not bracketed」（QuantLib 已知現象，
   https://quantlib-users.narkive.com/CNP64KU4/bug-related-to-error-message-root-not-bracketed ，
   搜尋索引轉述）。
3. **bid=0 的廢紙合約** → mid = ask/2，價格量化誤差（tick=0.01）相對於
   價格本身極大，反推出的 IV 誤差可達數十個 vol point。
4. **價格超過理論上限**（call > S）→ `AboveMaximumException`。

**業界的處置慣例**：解不出來就**回傳缺值並標記**，不要硬填。
社群實作的一致做法是 catch 這兩個例外並回 `None`/`NaN`
（https://github.com/loganrudd/implied-vol-plot/blob/main/market.py ）。
CME 的做法更前置——**先過濾出雙邊市場再算**，讓解不出來的情況根本不發生
（https://www.cmegroup.com/market-data/greeks-and-implied-volatility-data.html ，
搜尋索引轉述）。

**對本 app 的直接結論**：Cboe 的 `iv=0` 就是「已經照這個慣例回缺值」。
我們自己再反推一次，只會在同一批合約上撞同一面牆——實測 32 筆只多救 2 筆。
真正的出路是 §1.2 第 3 點：**承認這些合約沒有時間價值，用平價／內在值
定價，繞過 IV**，而不是把 solver 換得更厲害。

---

## 5. Q4：LEAPS 的流動性過濾慣例

### 5.1 業界的門檻說法（皆為二手／教育內容，非交易所規範）

沒有交易所或監理機關規定「什麼樣的價差算可接受」——這是慣例問題。
常見說法：

- 「Open interest at your strike should be **100+ contracts** and bid-ask
  spread should be **within 5–10% of mid-price**」
  （https://quantamentaltrader.substack.com/p/how-to-choose-options-based-on-highest ）。
- 「**5% is quite high**, anything around **2 to 3% is acceptable**,
  and less than that is desirable」；絕對值口徑則常見「spread ≤ $0.30」
  （https://optionshawk.com/understanding-options-bid-ask-spreads-and-liquidity/ 、
  https://tackletrading.com/options-101-bidask-open-interest-and-volume/ ，
  搜尋索引轉述）。
- LEAPS 專門的說法：「LEAPS generally have **lower liquidity and greater
  bid-ask spread** compared to shorter-dated options」，
  mega-cap 上約 $0.10–0.50、mid-cap 約 $0.50–2.00，建議一律掛限價單、
  從 mid 開始試
  （https://optionsamurai.com/blog/leap-options-trading/ 、
  https://www.equicurious.com/learn/derivatives/options-fundamentals/leaps-and-long-dated-contracts ，
  搜尋索引轉述）。

**注意這些數字是絕對價差**。「LEAPS 價差寬」是就**絕對金額**而言。

### 5.2 實測：相對價差其實隨天期變窄（實測實證）

同一份真實 Cboe 全鏈，只計有雙邊報價者，`(ask−bid)/mid` 分布：

| 天期 | n | 中位數 | p75 | p90 | ≤15% 的比例 |
|---|---|---|---|---|---|
| ≤30 天 | 265 | 6.6% | 17.9% | 50.0% | 73% |
| 31–90 天 | 121 | 11.3% | 22.2% | 50.0% | 65% |
| 91–365 天 | 172 | 4.2% | 9.5% | 20.7% | 84% |
| **>365 天** | **42** | **3.9%** | **7.4%** | **11.4%** | **90%** |

原因很直觀：長天期合約**單價高**（本例 LEAPS 常在 $5–20），
同樣 $0.30 的絕對價差除以大的 mid，相對值反而小；而近月價外合約單價
$0.05–0.50，同樣的 tick 就是 20–50%。

### 5.3 判讀：15% 的 cap 適不適合 LEAPS？

- **它不是近月專用慣例，用在 LEAPS 上也不會誤殺**——實測 >365 天有
  90% 的合約相對價差 ≤15%，套上完整規則
  `max(0.10, 0.15×mid)` 後通過 38/42。
- **相對於業界慣例（5–10%），15% 已經偏寬鬆**；再放寬的邊際效益很小
  （p90 才 11.4%）。
- **`max(0.10, …)` 的絕對下限才是對便宜合約的救命條款**：$0.30 的合約
  容許 $0.10 價差＝33%。這個設計是對的，不建議動。
- **真正該檢討的是 OI 門檻，不是 spread**（§1.2 第 5 點）。

---

## 6. Q5：OPC 到底做了什麼過濾？

前次調查已確認 OPC 的**資料源**（第三方免費網站、15–30 分鐘延遲、
無 premium feed）與**模型**（自行由報價反推 IV、IV 恆定的 BS）——見
`docs/research/option-chain-data-sources.md` §2 與
`docs/research/opc-heatmap-comparison.md` §2，本節不重複。

本次的新增證據是**它的線路格式**（原始碼實證，多個獨立專案逐字一致）：

```
GET https://www.optionsprofitcalculator.com/ajax/getOptions?stock={SYMBOL}&reqId=1
```

回傳結構（Go struct，含 JSON tag，
https://github.com/tripplyons/options-data/blob/main/internal/client.go ）：

```go
Result struct {
    ResultOptions map[string]map[string]map[string]ResultPrices `json:"options"`
}   // options[到期日][ "c" | "p" ][履約價] = ResultPrices
ResultPrices struct {
    BidPremium   float32 `json:"b"`
    AskPremium   float32 `json:"a"`
    LastPremium  float32 `json:"l"`
    OpenInterest int     `json:"oi"`
    Volume       int     `json:"v"`
}
```

交叉印證：`mnsrulz/mytradingview`
（https://github.com/mnsrulz/mytradingview/blob/master/src/lib/optionPriceHelper.ts ）
的 TS 型別為 `Record<string, { "l": number, "a": number }>`，同一形狀；
另有 `t73liu/trading-bot`、`a1mart/yeast`、`joshbyvelds/bsx-version-two`
等 5 個以上專案打同一端點（GitHub code search「optionsprofitcalculator.com/ajax/getOptions」，17 個命中）。

**由此可推的結論**：

1. **OPC 一次回傳「該標的全部到期日 × 全部履約價」的完整鏈**，
   以巢狀 map 呈現。`tripplyons/options-data` 的解析程式
   **對回傳合約不做任何過濾**（「All options extracted from the JSON
   response are appended to `allContracts` without any validation or
   exclusion logic based on bid/ask premiums, volume, open interest」），
   而它產出的結果與 OPC 網頁一致——即**網頁端本身也沒有品質過濾**。
2. **payload 裡完全沒有 IV 欄位**。這與前次調查（OPC 自述 IV 由報價反推）
   吻合，並進一步證明：**OPC 的 IV 是前端自己從 `b`/`a`/`l` 算出來的，
   因此「IV 算不出來」對 OPC 而言不是把合約丟掉的理由**——大不了那格
   顯示不出到期前的估值，到期損益（純內在值）照樣畫得出來。
3. 因此需求方觀察到的「OPC 有一堆可用合約、本 app 幾乎沒有」，
   **主要不是資料源差異，而是產品定位差異**：OPC 是「你挑合約，我幫你算」，
   零過濾；本 app 是「我幫你挑」，必須排名，於是加了四道品質過濾。
   兩者不是同一件事。**推論**：若要縮小落差，方向是把硬過濾降級為
   「排序懲罰 ＋ 顯示警語」，而不是換資料源。

未能查證：OPC 網頁前端的 JS 原始碼（站點 403，無法逐行核對是否有客戶端
過濾）；OPC 是否對「完全無報價」的履約價在上游就不回傳。

---

## 7. 本次分析的可重現路徑

真實 Cboe payload 原檔（可直接下載，本沙箱實測 200 OK，328,854 bytes）：

```
https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json
```

`timestamp` 2023-08-11 16:27:37、`current_price` 44.97、`data.options` 758 筆、
13 個到期日（DTE 0–525）。本文所有統計均由此檔以 stdlib Python 計算：
OCC 代號解析同 `option_chaser/data/cboe.py:31-45`；過濾規則同
`option_chaser/filters.py:23-34`（`min_oi=10`）；反推用二分法（σ∈[1e-6, 5]、
200 次迭代）配歐式 BS，r 取 0.053（2023-08 短率）。

另一個可下載但**不可信**的樣本：`simoneb/gex` 的 `CMG.json`（僅 3 KB、
數字全為整齊圓整值、`bid_size` 與 `ask_size` 完全相同），研判為手造測試資料，
**未採用**。

### 7.1 順帶發現：本 repo fixture 的 `current_price` 對不上（待複查）

`tests/test_data_cboe.py` 的 fixture 裡 `current_price` = 86.11，
但同一份 payload 的 `TLT260731C00065000` bid/ask = 17.15/17.30、
`TLT260731P00065000` bid/ask = 0.0/0.01——套賣權買權平價得標的價 ≈ **82.22**，
與 86.11 差 4.7%；且與需求方在本次任務描述中所說的「spot ≈ 82」一致。

對照組：真實 YETI 檔的 `current_price` 與 121 組平價推算的中位數只差 0.02%，
**Cboe 的 `current_price` 一般是可信的**。所以這個 4.7% 落差要嘛是
fixture 節錄時被改過，要嘛是那一刻 Cboe 的 `current_price` 陳舊。

⚠ 這件事有實際風險：`option_chaser/data/cboe.py:73` 用
`current_price`（退而用 `close`）當**所有 BS 定價的標的價**。若它在
盤外會陳舊而選擇權報價不會，整張 heatmap 的基準點就偏了。
**建議需求方用原始未裁剪的回傳複查一次**（§8 第 4 項）。

---

## 8. 未能查證的事項

1. **TLT 遠期（2027/2028）合約的 `iv` 實況**——沙箱無法抓 `cdn.cboe.com`，
   需求方兩組樣本又都是到期日當天／隔天的合約。**「LEAPS 會不會拿到
   `iv=0`」這個問題本文無法回答**；唯一的真實遠期樣本（YETI 525 天）
   顯示 42 筆只有 1 筆 `iv=0`，但那是 2023 年、另一檔標的、單一快照。
   → 需求方在部署環境抓一次 TLT 全鏈，統計 2027/2028 各期的
   `iv=0` 比例與四道過濾的逐段淘汰數。
2. **Cboe 對 `iv=0` 有無成文規則**——端點無文件，官方站上找不到任何
   說明何時填 0 的文字。§2.4 的結論是統計推論＋跨專案慣例，**不是**
   Cboe 的官方定義。
3. **Cboe 對 `open_interest` 更新頻率的自述**——同樣無文件。
   §3 的 T+1 語意來自 OCC／券商教育頁，是**業界通則**，
   未經 Cboe 官方確認其延遲報價 feed 的實際更新時點。
4. **本 repo fixture 的 `current_price` 86.11 是否為原始值**（§7.1）。
5. **被 403 擋下、僅有搜尋索引轉述的頁面**：Cboe Hanweck IV/Greeks 方法頁、
   Cboe delayed_quotes 條款頁、Barchart 方法說明、CME Options Analytics、
   ORATS Core Research、各 LEAPS 流動性教育文、deepwiki 的
   py_lets_be_rational 條目。皆未逐字核對原文。
6. **OPC 前端 JS 是否有客戶端過濾**（站點 403）。
7. **Cboe `bid_size`/`ask_size` 在盤外的行為**——建議的替代流動性訊號
   （§1.2 第 4 點）是否在收盤後歸零，未經驗證；若歸零則不能單獨當門檻。

---

## 9. 引用清單

**實測實證（本沙箱可直接下載、可逐筆重算）**

- https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json
  —— 真實 Cboe 全鏈 payload（758 筆／13 個到期日），本文 §1.1、§2.4、
  §3.2、§5.2 全部統計的來源

**原始碼實證（GitHub raw，可逐字檢視）**

- https://github.com/lballabio/QuantLib/blob/master/ql/instruments/impliedvolatility.cpp
  —— Brent solver、accuracy／maxEvaluations／minVol／maxVol 用法
- https://raw.githubusercontent.com/vollib/py_lets_be_rational/master/py_lets_be_rational/lets_be_rational.py
  —— `implied_volatility_maximum_iterations = 2`、精度註解、
  BelowIntrinsic／AboveMaximum 拋出點
- https://github.com/vollib/py_lets_be_rational/blob/master/py_lets_be_rational/exceptions.py
  —— 例外階層
- https://github.com/vollib/py_vollib —— Python 參考實作
- https://github.com/vollib/py_vollib/issues/5 、 /issues/18 、 /issues/13
  —— 深度 ITM／負利率下的 BelowIntrinsic 實務案例（皆 open）
- https://github.com/loganrudd/implied-vol-plot/blob/main/market.py
  —— catch 例外回 NaN 的社群慣例
- https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py
  —— Cboe provider 不對 `iv=0` 做任何處理
- https://github.com/tripplyons/options-data/blob/main/internal/client.go
  —— OPC `getOptions` 回傳 struct（b/a/l/oi/v）、零過濾
- https://github.com/mnsrulz/mytradingview/blob/master/src/lib/optionPriceHelper.ts
  —— OPC 回傳形狀交叉印證
- GitHub code search「optionsprofitcalculator.com/ajax/getOptions」（17 命中）、
  「delayed_quotes/options + iv」（122 命中）—— `iv > 0` 當可用性判斷式的
  跨專案慣例（marketpulse／mastermind-terminal／OFK_Atas_GEX）

**一手／權威文件（部分被 403 擋下，內容為搜尋索引轉述）**

- http://www.jaeckel.org/LetsBeRational.pdf 、
  https://onlinelibrary.wiley.com/doi/abs/10.1002/wilm.10395
  —— Jäckel (2015)：兩次 Householder 迭代達機器精度
- https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest
  —— OCC 每日 OI 報表
- https://www.cboe.com/services/analytics/hanweck/implied_volatility
  —— Cboe Hanweck：二項樹＋離散股利、支援美式
- https://www.cboe.com/delayed_quotes/cboe —— 延遲報價資料歸屬與
  禁止自動抓取條款
- https://www.cmegroup.com/market-data/greeks-and-implied-volatility-data.html
  —— 只對雙邊市場計算、先過濾流動性
- https://orats.com/docs/core-research 、
  https://docs.orats.io/datav2-api-guide/core-research.html
  —— ORATS：以 bid/ask 平均反推、bid-IV/mid-IV/ask-IV 三條、SMV 平滑
- https://www.barchart.com/stocks/quotes/$SPX/volatility-greeks
  —— Barchart：二項模型、last 優先否則 mid
- https://www.interactivebrokers.com/campus/ibkr-quant-news/implied-volatility-formulation-computation-and-robust-numerical-methods/
  —— Newton 在 vega→0 時發散、混合法
- https://www.interactivebrokers.com/campus/podcasts/ibkr-podcasts/what-is-option-open-interest-and-how-to-analyze/
  —— OI 非即時
- https://quantlib-users.narkive.com/CNP64KU4/bug-related-to-error-message-root-not-bracketed
  —— Brent「root not bracketed」實務案例

**二手（教育內容，非規範）**

- https://quantamentaltrader.substack.com/p/how-to-choose-options-based-on-highest
  —— OI 100+、價差 5–10% of mid
- https://optionshawk.com/understanding-options-bid-ask-spreads-and-liquidity/ 、
  https://tackletrading.com/options-101-bidask-open-interest-and-volume/
  —— 2–3% 可接受、$0.30 絕對門檻
- https://optionsamurai.com/blog/leap-options-trading/ 、
  https://www.equicurious.com/learn/derivatives/options-fundamentals/leaps-and-long-dated-contracts
  —— LEAPS 流動性較差、絕對價差區間、限價單建議
- https://www.optionsplaybook.com/options-introduction/open-interest 、
  https://www.tradingview.com/support/solutions/43000685269-open-interest/
  —— OI 隔日發布

**本 repo**

- `option_chaser/data/cboe.py:58-68`（`_positive_or_none`，`iv=0→None`）、
  `:73`（`current_price` 當 spot）、`:31-45`（OCC 解析）
- `option_chaser/filters.py:23-34`（四道過濾）
- `option_chaser/valuation.py:21-37`（歐式 BS）、`:106-116`
  （`evaluate_contract` 的 IV assert）、`:182-189`
  （`intrinsic_value`／`clamped_price`）
- `tests/test_data_cboe.py`（fixture 與 §7.1 的 `current_price` 落差）
- `docs/research/option-chain-data-sources.md`（資料源比較，本文不重複）
- `docs/research/opc-heatmap-comparison.md`（OPC 模型口徑，本文不重複）
