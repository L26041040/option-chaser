# 選擇權流動性過濾調查：`bid_size`/`ask_size` 盤外行為、四道關卡在最差成交口徑下還剩多少價值、以及陳舊報價該怎麼抓

研究日期：2026-08-04。前一份欄位語意調查見
`docs/research/cboe-field-semantics.md`（`iv=0`／`open_interest` 的判讀、
`OI>=10` 是候選池主殺手的實測），本文**不重複**那些內容，只往下處理三件事：

1. 該文 §8 第 7 項留下的未驗證假設——**Cboe `bid_size`/`ask_size` 盤外會不會歸零**；
2. 需求方提出的更銳利框架——**在「最差成交口徑」之下，四道關卡到底哪幾道還賺得到它的存在**；
3. 真正的殘留風險——**陳舊報價（stale quote）能不能在單一快照裡偵測出來**。

取材限制聲明（沿用前次）：本沙箱出口 proxy 對 `cdn.cboe.com`、`www.cboe.com`
一律回 403（CONNECT tunnel failed），**無法即時抓取 Cboe 端點**；WebFetch 對
所有網域回 403。可用的通道只有 GitHub（`raw.githubusercontent.com`／
`api.github.com` 實測 200）與搜尋索引。因此本文證據沿用三級標示：

- **實測實證**：本次實際下載、逐筆重算的真實 payload（原檔 URL 與統計重現方式見 §8）。
- **原始碼實證**：GitHub 上可直接抓取、逐字檢視的開源程式碼。
- **搜尋索引轉述**：被 403 擋下的頁面，內容經搜尋引擎索引摘錄取得，未逐字核對原文。

---

## 1. 結論摘要

### 1.1 主問題：`bid_size`/`ask_size` 盤外**不會**歸零（實測實證）

**答案是「不會歸零」——但這個提案仍然不該做，理由跟原本擔心的完全不同。**

三份互相獨立的真實 Cboe 資料一致顯示，`bid_size` 歸零的**充分必要條件就是
`bid` 歸零**，兩者是同一筆報價紀錄的兩個欄位，一起凍結、一起消失：

| 樣本 | 筆數 | `bid_size=0` | `bid=0` | 兩者不一致 | `ask_size=0` |
|---|---|---|---|---|---|
| YETI 全鏈（2023-08-11，盤中） | 758 | 158 | 158 | **0** | **0** |
| MLTX 全鏈（2025-02-12，OpenBB 匯出） | 176 | 40 | 40 | **0** | **0** |
| 本 repo fixture（2026-07-31 **23:43 ET，盤外**） | 3 | 1 | 1 | **0** | **0** |

本 repo 自己的測試 fixture 就是決定性證據：`tests/test_data_cboe.py` 的
`PAYLOAD` 是需求方在**美股休市時段**實測的回傳，`timestamp` 為
`2026-08-01 03:43:59`（UTC，換算美東為**週五 2026-07-31 23:43**，收盤後
七個半小時），其 `bid_size` 為 43／0／31、`ask_size` 為 46／77／14——
**盤外照樣是非零的實數，跟 bid/ask 一起凍結在收盤值**。這與 FB3-01（#44）
換源時需求方實測的「Cboe 盤外凍結收盤報價不歸零」完全一致：size 跟 price
是同一筆 NBBO 紀錄，不會只凍一半。

**所以「換成 size 會在盤外把候選池餓死」這個疑慮，可以正式排除。**

**但提案本身仍然不成立，真因有二（皆為實測）：**

- **(a) 在「有沒有」這個層次上，`bid_size` 與 `bid > 0` 是同一個條件。**
  934 筆真實報價、0 筆不一致。既有的 `quote_ok` 已經檢查 `bid > 0`，
  再加一條 `bid_size > 0` 是**恆真的贅語**，一個候選都篩不掉。
- **(b) 在「有多少」這個層次上，size 主要是做市商報價義務與自動報價機的
  產物，不是深度。**Cboe 規則要求 Hybrid 類別的做市商初始報價至少
  **10 口**，數量遞減到零就必須補回至少 10 口（搜尋索引轉述，§3.1）。
  實測的 size 也確實高度群聚在少數幾個值上（YETI：30/31/6/11/20；
  MLTX：5–10），這是報價機的預設值，不是真實可成交深度。
  把門檻設在 10 以下等於沒設，設在 10 以上就是在篩「這檔標的的做市商
  今天用了哪個預設值」。

一個附帶的量化事實：把 `OI>=10` 換成 `min(bid_size, ask_size)>=10`，在
YETI 的 600 筆雙邊報價裡有 **248 筆是「OI 不過但 size 過」、40 筆是
「OI 過但 size 不過」**——兩者衡量的根本是不同的東西，不存在「換一個更好的
同類指標」這種關係。

### 1.2 需求方的框架是對的：在最差成交口徑下，四道關卡幾乎都沒賺到存在（實測實證）

需求方的原話是「如果根本不篩，那我們還要篩什麼？反正回傳的都是有人出過的價
不就好了？」——**實測支持這個質疑**。

對 YETI 全鏈跑本 repo 的實際排名邏輯（`spread_baseline_return` ＝
(目標價內在值 − net_worst) / net_worst，成本口徑 net_worst ＝ 買腿 Ask −
賣腿 Bid，附錄 A14.2），做逐道 leave-one-out：

| 拿掉哪一道 | 合格買腿 | 合格組數 | **榜首報酬** | 與原 top10 重疊 |
|---|---|---|---|---|
| （四道全開，基準） | 102 | 607 | **1900.0%** | — |
| 拿掉 `quote_ok` | 106 (+4) | 659 | **1900.0%** | 2/10 |
| 拿掉 `iv_ok` | 105 (+3) | 637 | **1900.0%** | 10/10 |
| 拿掉 `oi_volume_ok` | 217 (**+115**) | 1600 | **1900.0%** | 3/10 |
| 拿掉 `spread_ok` | 114 (+12) | 773 | **1900.0%** | 8/10 |

**四道關卡，沒有任何一道改變榜首。**而 `OI>=10` 一道就砍掉 53% 的買腿
（217→102），卻連榜首都攔不住——它付出最大的候選池代價，換到的是零。

逐道評估（詳見 §4）：

| 關卡 | 在最差成交口徑下還賺不賺得到存在 | 判定 |
|---|---|---|
| `quote_ok`（bid>0、ask>=bid） | **賣腿需要**（要賣出必須有人出價買）；**買腿不需要**——實測把買腿放寬成「只要 ask>0」，配對數與榜首**完全不變**（0 組新增），因為 `net_mid > 0` 的配對合理性已經先把它們擋掉了 | **保留，但買腿那半是贅語** |
| `iv_ok` | **不是流動性關卡，是引擎保護**——`evaluate_contract` 明文 assert 需要 IV。拿掉它 top10 重疊 10/10，對排名毫無影響 | **保留（理由要改寫成引擎前置條件）** |
| `oi_volume_ok` | **賺不到**。OI 是 T+1 落後結算數（前文 §3）；`volume >= min_volume` 那半恆真不做事；代價是砍掉一半候選池，收益是零 | **建議降級／移除** |
| `spread_ok` | **需求方的分析成立**——價差寬的合約，成本在 net_worst 已經被誠實算高、報酬率自然被壓低。再擋一次是**把已經定價進去的事重複懲罰**，而且是用「刪掉資訊」這個更糟的方式 | **建議降級為顯示層警語** |

### 1.3 「不合理收益率」的真因不是資料品質，是度量本身（實測實證）

這是本次調查最重要、也最違反直覺的發現。

YETI 全鏈在**現行四道關卡全開**之下，榜首是：DTE=7、K 49.0/51.0 的價外
價差，成本 $0.10、寬度 $2.00、**報酬率 1900%**。而這張合約一點都不冷門——
`bid_size=618`、`ask_size=573`，當天 11:42 才成交過。**它是一張完全流動、
完全真實的近月價外樂透票。**

換句話說：**1900% 不是髒資料，是這個度量在成本很小時的必然結果。**
報酬率 = (內在值 − 成本)/成本，成本進了分母；只要成本掉到兩三個
最小跳動點，報酬率就會噴到四位數。實測敏感度：

| 榜首成本 | 報酬率 | 成本 +1 tick ($0.05) 後 | 變動 |
|---|---|---|---|
| $0.10（2 ticks） | 1900.0% | 1233.3% | **−667 個百分點** |
| $0.20（4 ticks） | 1400.0% | 1100.0% | −300 個百分點 |
| $0.25（5 ticks） | 1300.0% | 1066.7% | −233 個百分點 |

**唯一真正壓得住榜首數字的，是對成本本身設下限**（實測，只留 `quote_ok`
再加最低成本）：

| 額外條件 | 合格組數 | 榜首報酬 |
|---|---|---|
| （純 `quote_ok`） | 3076 | 1900.0% |
| ＋最低成本 $0.30 | 3005 | **1042.9%** |
| ＋最低成本 $0.50 | 2916 | **743.1%** |

注意它砍掉的組數極少（3076→2916，只有 5%），卻把榜首數字砍掉六成——
**這正是「精準命中問題、不誤傷候選池」的形狀**，跟 `OI>=10`（砍 53%、
效果 0）恰成對比。

### 1.4 陳舊報價：Cboe 沒有逐筆報價時戳，但單一快照的內部一致性檢查可行且已有業界慣例

- **逐筆報價時戳：不存在。**Cboe delayed_quotes 的 option row 只有 23 個
  欄位，其中與時間有關的只有 `last_trade_time`（**成交**時戳，不是報價時戳）、
  `tick`、`change`/`percent_change`（對比 `prev_day_close`）。**沒有
  `bid_time`／`ask_time`**（§6.1，實測＋原始碼雙重證實）。
- **`last_trade_time` 不能拿來判斷報價新不新。**實測：600 筆雙邊報價裡
  **244 筆從來沒成交過**（`last_trade_time = null`）卻有活生生的雙邊報價；
  有成交紀錄的那 356 筆，成交年齡中位數 1 天、**p90 高達 28 天、最大 185 天**。
  「沒成交」跟「沒人報價」是兩件事——這同時也是 OI／volume 不該當硬門檻的
  最直接反證。
- **業界慣例是用無套利一致性檢查取代新鮮度時戳**，順序是
  **正性 → 單調性 → 凸性**（搜尋索引轉述稱這組是「CBOE 建議」的標準過濾，
  §6.2）。需求方猜的方向是對的。
- **但本 repo 的最差成交口徑已經先一步把「陳舊且偏低的 ask」這個風險
  大幅壓掉了**（實測，§6.4）：前十名候選的 `net_worst / theo成本` 比值落在
  **1.15–2.10**，全部**高於** Cboe 自己的理論成本；6127 組 box 用最差報價
  檢驗**零套利違反**；320 筆 call 裡**零筆** `ask < 遠期內在值`。
  在這份健康的快照上，「stale 導致成本低估」找不到任何一個實例。
- **真正查得到東西的檢查是單調性**：ask 曲線 307 組相鄰履約價中有
  **3 組違反單調**（履約價變高、ask 反而變貴），三組全部落在 OI 低、
  成交久遠或從未成交的冷門履約價上——**這是一個會命中、且命中得有道理的
  檢查**，且它不誤傷任何流動合約。

### 1.5 建議一句話總結

**把「事前刪除候選」換成「事後標記＋壓住度量的分母」**：移除 `OI>=10`
硬門檻、把 `spread_ok` 降級成警語、保留 `quote_ok`（賣腿）與 `iv_ok`
（引擎前置條件），新增**單調性一致性檢查**（抓陳舊報價）與**最低成本門檻
或報酬率呈現方式的修正**（抓度量本身的分母爆炸）。具體條列見 §10。

---

## 2. 主問題實證：三份真實 payload 的 size 欄位

### 2.1 樣本與可重現性

| 樣本 | 來源 | 快照時刻 | 筆數 |
|---|---|---|---|
| YETI 全鏈 | `raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json` | `2023-08-11 16:27:37` UTC ＝ **週五 12:27 ET，盤中** | 758 |
| MLTX 全鏈 | `raw.githubusercontent.com/AdRedrock/OptionsAnalyzer/main/data/imported/CBOE/MLTX/2025-02-12/2025-02-12_close_UTC+01_00_MLTX.csv` | 2025-02-12（OpenBB 正規化匯出） | 176 |
| TLT 節錄 | 本 repo `tests/test_data_cboe.py` | `2026-08-01 03:43:59` UTC ＝ **週五 2026-07-31 23:43 ET，盤外** | 3 |

### 2.2 順帶修正前文一處：YETI 樣本是**盤中**不是盤後（實測實證）

`cboe-field-semantics.md` 未指明該樣本的時區。本次確認 **Cboe 的
`timestamp` 欄位是 UTC，而 `last_trade_time` 是美東時間**，證據是延遲量
剛好對得上：YETI 檔當天最晚的一筆成交是 `2023-08-11T12:12:17`（ET），
payload `timestamp` 是 `16:27:37`（UTC ＝ 12:27:37 ET），**相差 15 分 20 秒
——正是 Cboe 延遲報價的 15 分鐘延遲**。若把 timestamp 讀成 ET，就得解釋
為什麼 16:27 的快照裡最後一筆成交停在 12:12，且當天 12:12 之後完全無成交，
明顯不合理。

這個修正不影響前文任何結論（前文的統計都不依賴時區），但**它是本文能把
repo fixture 認定為「盤外樣本」的前提**：`2026-08-01 03:43:59` UTC 換算
美東就是週五收盤後 23:43。

### 2.3 `bid_size` 與 `bid` 是同生共死的一對（實測實證）

YETI 758 筆的交叉表，只有兩格有值：

| | `bid_size = 0` | `bid_size > 0` |
|---|---|---|
| `bid = 0` | **158** | 0 |
| `bid > 0` | 0 | **600** |

`ask` 側更乾脆：758 筆**沒有任何一筆** `ask = 0` 或 `ask_size = 0`。
MLTX 176 筆重跑同一組檢定，同樣是 0 筆不一致（40 筆 `bid=0` 對應 40 筆
`bid_size=0`）。

**判讀**：這兩個欄位來自同一筆 NBBO 紀錄。沒有 bid 就沒有 bid size，
有 bid 就一定有 size。因此
`bid_size > 0` **完全等價於**現有 `quote_ok` 裡的 `bid > 0`。

### 2.4 盤外樣本：size 凍結，不歸零（實測實證）

repo fixture 的三筆（週五 23:43 ET）：

| 合約 | bid | bid_size | ask | ask_size |
|---|---|---|---|---|
| `TLT260731C00065000` | 17.15 | **43.0** | 17.30 | **46.0** |
| `TLT260731P00065000` | 0.0 | **0.0** | 0.01 | **77.0** |
| `TLT260731C00079500` | 2.67 | **31.0** | 2.79 | **14.0** |

三筆都是前一天（7/31 週五）已到期的合約，收盤後七個半小時仍保有非零
size；`bid=0` 的那筆 `bid_size=0`、但 `ask=0.01` 的那筆 `ask_size=77`
——與 §2.3 的規律完全一致。

**結論：`bid_size`/`ask_size` 在盤外與 bid/ask 一起凍結在收盤值，不歸零。
`cboe-field-semantics.md` §8 第 7 項的疑慮解除。**

⚠ 侷限：這份盤外樣本只有 3 筆，且前文 §7.1 已指出同一份 fixture 的
`current_price` 可能被裁剪時改過。但**它的方向與 §2.3 的 934 筆結構性規律
一致**，而且需求方換源時本來就是實測「盤外不歸零」才決定用 Cboe 的——
三條線指向同一結論。真正的完整盤外全鏈仍未取得（§9 第 1 項）。

---

## 3. quote size 的語意陷阱：它是報價義務，不是深度

### 3.1 做市商最低報價量就是 10 口（搜尋索引轉述）

Cboe 規則：「Initial market-maker quote size in Hybrid classes must be for at
least **10-contracts** … Once the size decrements to zero, the market-maker
must replenish to at least 10-contracts.」
（https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG18-009.pdf 、
RG03-084、RG19-032，搜尋索引轉述）

**這使得 `size >= 10` 這種門檻在語意上很尷尬**：它篩掉的不是「沒人要的
合約」，而是「最佳報價恰好來自不受該義務約束的一方（客戶掛單、其他交易所）」
的合約。

### 3.2 連續報價義務**不涵蓋** LEAPS（搜尋索引轉述）

同一組規則：做市商必須對其指派類別中「**time to expiration of less than
nine months**」的 60% 序列維持連續電子報價。**九個月以上的長天期序列
不在連續報價義務範圍內**。

⚠ 這對本 repo 特別要緊——本 app 的主戰場正是 LEAPS。它的意思是：
**LEAPS 有沒有報價是自願的**，所以「有報價」在 LEAPS 上反而是個比近月更
強的訊號（實測佐證：YETI DTE=525 的 21 筆 call **全部 21 筆**都有雙邊報價，
IV 與 spread 兩關幾乎沒殺人，見前文 §1.2 第 5 點）。

### 3.3 實測：size 的分布是報價機預設值，不是深度（實測實證）

非零 `bid_size` 的出現次數前幾名：

- YETI（758 筆）：30 出現 46 次、31 出現 43 次、6 出現 41 次、11 出現 27 次、20 出現 26 次
- MLTX（176 筆）：6 出現 37 次、5 出現 26 次、8 出現 12 次、10 出現 9 次

同一檔標的的 size 大量重複在少數幾個值上，**跨標的又完全不同**（YETI 在
30 附近、MLTX 在 6 附近）。這是自動報價機對整條鏈套用同一組參數的特徵，
不是逐一履約價的真實可成交量。

### 3.4 沒有任何開源專案拿 size 當流動性門檻（原始碼實證）

- **OpenBB 官方 Cboe provider**：`quotes["bid_size"] = quotes["bid_size"].astype("int64")`、
  `quotes["ask_size"] = quotes["ask_size"].astype("int64")`——只做型別轉換，
  **零特判、零過濾**
  （https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py ）。
  順帶一提，這行 `astype("int64")` 遇到 NaN 會直接爆掉，**反證 Cboe 對每一筆
  option row 都一定給得出這兩個欄位**（不會是 null）。
- **`Ollie1o1/options`**（同樣打 `cdn.cboe.com` 延遲報價的開源選擇權篩選器，
  是目前找到與本 repo 最相似的專案）：`src/cboe_client.py` 有原封不動地
  把 `bid_size`/`ask_size` 映射進來，但 `src/filters.py` 的四道過濾
  **完全沒有用到它們**。
- **`gauss314/skills` 的 `cboe-data` 參考文件**
  （https://raw.githubusercontent.com/gauss314/skills/main/skills/cboe-data/references/REFERENCE.md ）
  逐欄位記載了 delayed_quotes 的回傳，`bid_size`/`ask_size` 只註明
  「float / Bid size」，**沒有任何盤外語意的說明**。⚠ 該文件另有一張
  「index vs stock」對照表寫 index 的 `bid_size`/`ask_size` 為 0——
  那是**標的層**（`data.bid_size`）的欄位，指數沒有 bid/ask 所以為 0，
  **與 option row 的 size 無關**，不要誤讀成盤外歸零的證據。

---

## 4. 逐道關卡在最差成交口徑下的價值（本文核心，實測實證）

需求方指出的架構事實是對的：本 repo 主數字一律用**最差成交口徑**
（單腿 ＝ Ask；價差 ＝ 買腿 Ask − 賣腿 Bid，見 `valuation.py:245` 與
`ranking.py:109-113`，附錄 A14.2）。這代表過濾器擋掉的很多東西，**成本
公式已經誠實懲罰過一次了**。以下逐道檢驗。

方法：對 YETI 全鏈（call、DTE>0）跑本 repo 的實際排名式
`(baseline_value − net_worst) / net_worst`，`baseline_value` ＝ 目標價在該
Spread 自身到期日的內在值夾在 `[0, width]`（T3／`spread_scenario_value`），
目標價取 spot +15%。完整腳本見 §8。

### 4.1 `quote_ok`：賣腿必要，買腿是贅語

拆成不對稱檢驗——買腿只要求 `ask > 0`，賣腿仍要求 `bid > 0`：

| | 合格組數 | 榜首 |
|---|---|---|
| 對稱 `quote_ok`（現況） | 3076 | 1900.0% |
| 買腿放寬成只要 `ask > 0` | **3076** | **1900.0%** |
| 其中買腿 `bid = 0` 的組數 | **0** | — |

**放寬買腿是完全的 no-op**。原因：全鏈 43 筆 `bid=0 且 ask>0` 的 call
價外程度中位數 K/S ＝ **1.45**（深度價外），把它們當買腿去配一個更高履約價
的賣腿時，`net_mid > 0` 這條配對合理性（`filters.py:71`）本來就先擋掉了。

**判定：`quote_ok` 保留，但要理解它的作用力全在賣腿。**賣腿要賣得掉必須
真的有人出價買，`bid > 0` 是硬需求。買腿那半沒有做事，也沒有害處——
不建議為了拿掉它而改動（改了不會多出任何候選）。

### 4.2 `iv_ok`：不是流動性關卡，是引擎前置條件

拿掉它只多 3 筆買腿、top10 重疊 **10/10**——對排名毫無影響。它真正的作用
是保護估值引擎：`evaluate_contract`（`valuation.py:106-116`）明文 assert
需要 IV，缺 IV 的合約進去會炸。

**判定：保留，但它被歸類在「品質過濾」是誤導。**建議把它從「四道品質
過濾」的敘事裡拉出來，正名為引擎前置條件——這樣後續討論「要不要放寬過濾」
時不會有人誤以為可以動它。

### 4.3 `oi_volume_ok`：賺不到存在，建議移除

- 代價最大：拿掉它買腿從 102 → **217**（+115，池子多一倍），組數 607 → 1600。
- 收益為零：榜首報酬**一模一樣**是 1900%。
- `volume >= p.min_volume` 那一半在 adapter 把 volume 轉成
  `int(... or 0)` 之後**恆真**，不做任何事（前文 §3.3 已指出）。
- 語意本來就錯位：OI 是 OCC 收盤後結算、隔天才發布的 **T+1 落後數字**
  （前文 §3.1）。本文再補一個更直接的反證：**YETI 600 筆雙邊報價裡，
  244 筆從來沒成交過**（`last_trade_time = null`）——它們有活的雙邊報價，
  OI 與 volume 卻都是 0。用成交紀錄去判斷「現在有沒有市場」，方向就是錯的。

**判定：建議移除硬門檻。**（⚠ 這一項改變候選池組成，屬需求方裁示範圍，
見 §10。）

### 4.4 `spread_ok`：需求方的分析成立，建議降級為警語

需求方的論證是：價差寬的合約，`net_worst = 買腿 Ask − 賣腿 Bid` 本來就
會算得高、報酬率自然低——**gate 4 等於把已經誠實反映在成本裡的事再擋一次，
而且用的是「直接刪掉資訊」這個更糟的方式**。

實測支持：拿掉 `spread_ok` 只多 12 筆買腿、top10 重疊 8/10、榜首不變。
前文 §5.2 也已證明這條規則對 LEAPS 本來就寬鬆（>365 天的相對價差中位數
只有 3.9%，p90 才 11.4%，遠低於 15% 的 cap）——**它幾乎只在近月便宜價外
合約上發威，而那正是成本口徑已經懲罰得最重的地方**。

另外要注意：`build_spread_reasons`（`ranking.py:132-134`）**已經有**一條
「買賣價差偏大（兩腿合計）」的顯示層警語。也就是說降級的目的地已經存在，
不必新建。

**判定：建議從硬過濾降級為顯示層警語（機制已存在）。**（⚠ 同樣改變候選池，
屬裁示範圍。）

### 4.5 為什麼四道全都攔不住榜首

因為它們篩的是**合約的品質**，而失控的是**度量的分母**。榜首那張
K 49.0/51.0（`bid_size=618`、`ask_size=573`、當天成交過）是全鏈流動性
最好的合約之一，四道關卡沒有一道有理由擋它——它只是**很便宜**。
詳見 §5。

---

## 5. 「不合理收益率」的真因：分母爆炸，不是髒資料（實測實證）

### 5.1 現象

排名式 `(baseline_value − net_worst) / net_worst` 把成本放進分母。當
`net_worst` 掉到兩三個最小跳動點（$0.05 tick）時：

- 報酬率必然是四位數；
- 而且**一個 tick 的報價誤差就能讓它變動數百個百分點**（§1.3 的表）。

這不是資料錯，是**在成本接近價格解析度時，比率這個統計量本身就失去意義**。

### 5.2 這解釋了需求方回報的症狀，也解釋了為什麼「篩得更兇」沒有用

需求方 feedback-v3 第 4 點回報的是「盤外只剩 deep ITM、報酬率 41%」。
把兩件事分開看：

- **「只剩 deep ITM」是候選池被殺光**——前文已定案，主因是 `OI>=10`；
- **「數字不合理」則是這個度量的性質**——實測顯示，**即使候選池健康、
  四道關卡全開，榜首照樣是 1900%**。

也就是說，就算 FB3-01／FB3-02 把資料源與候選池問題全解決，**只要度量不動，
使用者還是會看到四位數的報酬率**。這一點必須讓需求方知道。

### 5.3 唯一有效、且精準的處置：對成本設下限

| 條件 | 合格組數 | 佔比 | 榜首報酬 |
|---|---|---|---|
| 純 `quote_ok` | 3076 | 100% | 1900.0% |
| ＋ `net_worst >= 0.30` | 3005 | **97.7%** | 1042.9% |
| ＋ `net_worst >= 0.50` | 2916 | **94.8%** | 743.1% |

對照 `OI>=10`：砍掉 53% 的買腿，榜首**一點都沒動**。

**這是一個「精準命中、幾乎零誤傷」的處置**，而且它的理由是可以寫進文件的
工程理由——**不是「我們不喜歡便宜的合約」，而是「當成本只有 2 個 tick 時，
報酬率的數值誤差比數值本身還大」**。

⚠ 但它仍然是產品決策：便宜的價外樂透票**可能正是使用者想找的東西**。
替代做法（不刪候選、只改呈現）見 §10 第 5 項。

---

## 6. 陳舊報價（stale quote）：能查到什麼、業界怎麼做、單一快照能不能判

### 6.1 Cboe delayed_quotes **沒有**逐筆報價時戳（實測＋原始碼雙重證實）

YETI payload 的 option row 完整欄位（23 個，實測列舉）：

```
ask, ask_size, bid, bid_size, change, delta, gamma, high, iv,
last_trade_price, last_trade_time, low, open, open_interest, option,
percent_change, prev_day_close, rho, theo, theta, tick, vega, volume
```

**沒有 `bid_time`／`ask_time`／`quote_time`。**唯一的逐筆時間欄位是
`last_trade_time`，那是**成交**時戳。

交叉印證（原始碼實證）：OpenBB 的標準 options-chain 模型**有**
`bid_time`/`ask_time`/`bid_exchange`/`ask_exchange` 欄位（見
`gururafiki/muffin-agent` 的 OpenBB 契約樣本），但 **Cboe provider 匯出的
實際 CSV 欄位裡沒有這幾欄**（AdRedrock 的 MLTX 檔表頭：
`…,tick,bid,bid_size,ask,ask_size,open,high,low,prev_close,change,…`）——
即這些欄位是別的 provider 才填得出來的，Cboe 這條線天生就沒有。

其餘可用的間接訊號：`tick`（`up`/`down`/`no_change`，YETI 600 筆雙邊報價中
**326 筆是 `no_change`**）、`change`／`percent_change`（對比 `prev_day_close`）。
兩者都只說明「今天有沒有動過」，不說明「這個 bid/ask 是幾點掛的」。

### 6.2 業界怎麼偵測陳舊報價：無套利一致性，而非時戳（搜尋索引轉述）

學術與資料供應商的標準清洗流程是三段式，**且搜尋索引明確稱這組是
「CBOE 建議」的無套利過濾**：

1. **正性（positivity）**：中價非正的報價一律剔除；
2. **單調性（monotonicity）**：call 價格對履約價必須非遞增，put 非遞減；
3. **凸性（convexity）**：對履約價的二階差分必須非負（防蝴蝶套利）。

（https://arxiv.org/pdf/2605.22792 、https://arxiv.org/pdf/2008.09454
「Detecting and repairing arbitrage in traded option prices」，搜尋索引轉述）

同一批文獻對成因的說法，與本案完全對得上：「likely drivers of data quality
issues include insufficient liquidity (wide, non-synchronous quotes),
**stale prints in the vendor feed**, and spot/forward misalignment」；並指出
「**stale or asynchronous quotes may generate potential static arbitrages**」
——也就是說，**陳舊報價會以「靜態套利違反」的形式露出馬腳**，這正是單一
快照就能檢驗的東西。OptionMetrics 這種商用資料庫同樣有此問題，已有專門的
品質研究（Wallmeier 2024, *Journal of Futures Markets*，
https://onlinelibrary.wiley.com/doi/full/10.1002/fut.22495 ，搜尋索引轉述）。

**結論：需求方猜的方向（單調性／凸性一致性檢查）就是業界做法。**

### 6.3 實測：這些檢查在真實鏈上跑起來是什麼樣子（實測實證）

對 YETI 全鏈（call、有雙邊報價）實跑：

| 檢查 | 檢驗數 | 命中 | 判讀 |
|---|---|---|---|
| `ask < 遠期內在值 (S − K·DF)` | 320 | **0** | 硬套利下限完全沒被觸犯 |
| ask 曲線相鄰履約價單調性 | 307 組 | **3** | **會命中、且命中得有道理**（見下） |
| ask 曲線凸性（三連履約價） | 305 組 | 50 | **誤判率太高，不建議單獨用**——ask 含了半個買賣價差，凸性本來就會被雜訊破壞 |
| box 價差套利（用最差報價） | 6127 組 | **0** | 零誤報，但在本案也零命中（原因見 §6.4） |

三筆單調性違反的長相：

```
dte= 98  K 65.0 ask 0.35 → K 70.0 ask 2.25  (oi 24 / 0,   最後成交 08-10 / 從未成交)
dte=161  K 72.5 ask 0.35 → K 75.0 ask 0.75  (oi 27 / 110, 最後成交 08-10 / 08-10)
dte=161  K 80.0 ask 0.40 → K 82.5 ask 0.75  (oi 216 / 78, 最後成交 07-12 / 05-22)
```

三組全部落在冷門／久未成交的履約價上（其中一組的兩腿最後成交分別是 7/12
與 5/22，快照日是 8/11）。**單調性檢查抓到的正是「陳舊或錯誤」的那一類，
而且 307 組只誤傷 0 組流動合約。**

### 6.4 為什麼 box 檢查零命中：最差成交口徑已經先擋住了

box 檢查是模型無關的硬檢驗：
`(C1.ask − C2.bid) + (P2.ask − P1.bid) >= DF × (K2 − K1)`，
違反就等於有無風險套利，代表**至少一筆報價是陳舊或錯的**。6127 組零違反。

原因在 §6.5 的數字裡：**最差成交口徑本身就是最保守的取價方式**，
它系統性地讓成本偏高，所以「成本被低估」這個失效模式很難發生。

### 6.5 `theo` 欄位：一個被 adapter 丟掉的獨立交叉檢查（實測實證）

Cboe 每一筆都附了 `theo`（Hanweck 二項樹理論價，前文 §2.2）。**本 repo 的
adapter 沒有取用這個欄位。**它值得注意，因為實測顯示它**不是中價的換算**：

- 600 筆雙邊報價中，`theo` **沒有任何一筆**恰等於 mid；
- `|theo − mid|` 中位數 $0.033、p90 $0.129、最大 $1.076；
- **19 筆的 `theo` 落在 [bid, ask] 區間之外**。

也就是說 `theo` 是一個**獨立於該筆報價**的曲面擬合值，可以拿來當
「這筆報價跟整條鏈的其他報價一不一致」的檢查。

實測結果——**對本 repo 而言，它查不到東西**：前十名候選的
`net_worst ÷ (買腿 theo − 賣腿 theo)` 比值是

```
1.29, 1.28, 1.17, 2.10, 1.35, 1.58, 1.15, 1.21
```

**全部大於 1**，即最差成交成本一律**高於**理論成本。套上
「成本必須 ≥ 0.7／0.8／0.9 倍 theo 成本」的門檻，三個水準都是**一組都篩不掉**。

**判讀**：這是一個**負面但有價值**的結果。它量化地證實了需求方的架構論證
——**最差成交口徑已經自帶了對「陳舊且偏低的 ask」的免疫力**，因為它從不
假設你能成交在 mid。殘留風險確實存在（理論上一個陳舊偏低的 ask 會低估成本），
但在這份真實快照上，**該風險的實例數是 0**。

⚠ 侷限：這是**盤中、流動性正常**的快照。盤外全鏈是否同樣乾淨，未能查證
（§9 第 1 項）。`theo` 檢查的正確定位是**盤外／冷門標的的保險絲**，
成本極低（欄位現成，一行比較），即使平常不命中也值得裝。

---

## 7. 業界怎麼篩流動性，以及盤外到底怎麼辦

### 7.1 用什麼指標（Q2）

| 指標 | 地位 | 出處 |
|---|---|---|
| **相對買賣價差**（quoted spread / mid） | **學術與業界的首選**。選擇權的平均百分比價差 **13.44%**，遠高於股票的 0.81%——所以價差在選擇權上是強訊號 | Cao & Wei (2010) *Option market liquidity: Commonality and other characteristics*, http://www.yorku.ca/mcao/Cao_Wei_JFM_2010.pdf （搜尋索引轉述） |
| **成交量（volume）** | 常用，衡量「今天活躍度」 | 同上 |
| **未平倉量（OI）** | 常用但**明確被指出是落後指標**：「what you see on your screen reflects yesterday's session」 | 前文 §3.1 已列 |
| **報價量（quote size）／市場深度** | **明顯較少被討論**：「Bid-Ask Size — Less Frequently Discussed」 | https://www.tradingblock.com/blog/options-liquidity 、https://optionsamurai.com/blog/options-liquidity-tips-to-identify-the-best-opportunities-with-real-market-example/ （搜尋索引轉述） |
| **複合評分** | 有商用實作但方法不公開：tastytrade 有 1–5 星「liquidity rating」、Market Chameleon 有 liquidity ratings | 搜尋索引轉述，**方法學未公開**（§9 第 4 項） |

業界的一致建議是**多指標並用、且務必回頭看實際價差**：「High OI does not
guarantee tight spreads … Always check the actual spread before entering a
trade, not just the OI number.」（搜尋索引轉述）

### 7.2 開源實作實際上怎麼寫（原始碼實證）

`Ollie1o1/options`（同樣以 `cdn.cboe.com` 為資料源的選擇權篩選器）的
`src/filters.py`：

```python
# 2. Liquidity Filter (Volume OR OI)
# Same semantics as the live path in options_screener.enrich_and_score:
# a contract is liquid enough when EITHER floor is cleared. Do not switch
# this back to AND — two different semantics for the same config keys was
# a 2026-07-13 audit finding.
min_vol = f_config.get("min_volume", 50)
min_oi  = f_config.get("min_open_interest", 10)
df = df[(df["volume"] >= min_vol) | (df["openInterest"] >= min_oi)].copy()
```

三個可直接借鏡的點：

1. **是 `OR` 不是 `AND`**，而且註解明白記載「改回 AND 是 2026-07-13 的稽核
   缺失」。本 repo 目前是 `open_interest >= min_oi and volume >= min_volume`
   （`filters.py:30`）——同樣的兩個欄位、相反的邏輯。
2. **價差上限的預設是 `max_bid_ask_spread_pct = 0.40`（40%）**，比本 repo
   的 15% 寬得多。
3. **它把 `bid_size`/`ask_size` 抓進來了，但過濾完全沒用到。**

### 7.3 盤外到底怎麼辦（Q3）——業界不拒絕，而是標記等級

**篩選器不會在盤外拒絕篩選。**Barchart 的 options screener 明白提供
**Market Close（3pm CT）與 End-of-Day（4:45pm CT）** 兩個排程寄送時段
（https://www.barchart.com/options/options-screener ，搜尋索引轉述）——
4:45pm CT 是收盤後，也就是**盤後跑篩選是正常產品行為**，篩的就是凍結的
收盤報價。

開源端的做法更明確（原始碼實證，`wesso80/marketscannerpros`
`lib/options-confluence-analyzer.ts`）——**把資料新鮮度做成一等公民的列舉，
並且只在最差那一級才拒絕輸出**：

```ts
export interface DataQuality {
  optionsChainSource: 'alpha_vantage' | 'nasdaq_fmv' | 'cboe' | 'none';
  freshness: 'REALTIME' | 'DELAYED' | 'EOD' | 'STALE';
  hasGreeksFromAPI: boolean;
  hasMeaningfulOI: boolean;
  ...
}
```

```ts
if (dataQuality.freshness === 'STALE' || chaoticRegime || optionsDrivenInputsMissing) {
  return buildInsufficientIntent(symbol, timeframe, 'DATA_INSUFFICIENT');
}
```

關鍵設計：**`EOD`（收盤後的凍結資料）是一個「正常可用」的狀態**，照樣輸出
結果，只在下游附加揭露（該檔另有 `if (dataQuality.freshness === 'EOD') { … }`
的專屬處理分支）；只有 `STALE` 才整個拒答。它另外把
`hasMeaningfulOI = totalCallOI > 100 || totalPutOI > 100` 當成獨立的品質旗標，
**在 OI 不可信時關掉依賴 OI 的功能（如 max pain），而不是把候選丟掉**。

**對 Q3「有沒有一個盤中盤外都穩健的流動性訊號」的誠實答案：沒有，
而且不需要有。**收盤後確實沒有活的委託，「現在有沒有人在報價」這個訊號
定義上就不存在。可行的工程解法是三件事的組合，而非找一個神奇指標：

1. **改用盤外仍有意義的訊號**——凍結的**收盤價差**（相對價差）與**報價存在性**
   （`bid > 0`）都在盤外原封保留，語意是「**收盤那一刻**市場長這樣」，
   誠實且可揭露；
2. **加上內部一致性檢查**（§6.2／§6.3 的單調性）——它完全不依賴時間，
   盤中盤外一體適用；
3. **標記狀態、降級但不拒答**（`REALTIME`／`EOD` 的分級 ＋ UI 揭露）。

---

## 8. 本次分析的可重現路徑

三份原檔（本沙箱實測皆 200 OK）：

```
https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json
  → timestamp 2023-08-11 16:27:37 UTC（＝12:27 ET 盤中）、current_price 44.97、
    data.options 758 筆、13 個到期日（DTE 0–525）、328,854 bytes

https://raw.githubusercontent.com/AdRedrock/OptionsAnalyzer/main/data/imported/CBOE/MLTX/2025-02-12/2025-02-12_close_UTC%2B01_00_MLTX.csv
  → OpenBB 正規化匯出的 Cboe 鏈，176 筆、7 個到期日、underlying_price 43.6

（本 repo）tests/test_data_cboe.py 的 PAYLOAD
  → timestamp 2026-08-01 03:43:59 UTC（＝2026-07-31 23:43 ET 盤外）、3 筆
```

所有統計以 stdlib Python 計算，方法與前文一致：OCC 代號解析同
`option_chaser/data/cboe.py:31-45`；過濾規則同 `option_chaser/filters.py:23-34`
（`min_oi=10`）；排名式同 `option_chaser/ranking.py:109-113` 配
`valuation.py:211-218` 的 `spread_scenario_value`（目標價內在值夾在
`[0, width]`）；貼現 `DF(t) = exp(−0.053 × t/365)`（2023-08 短率水準）；
目標價取 spot×1.15（另跑過 ×1.30，榜首相同）。

⚠ **注意 AdRedrock 的三個 MLTX 檔是同一份快照的三次匯出**（`2025-02-12`
與 `2025-02-13` 兩檔 md5 完全相同；`2025-02-14` 檔只有 `dte` 欄不同——
OpenBB 的 `dte` 是用匯出當下的 `datetime.now()` 重算的）。**不可以把它們
當成三個時間點**。本文只把它當成**一份**獨立樣本使用。

已檢視但**未採用**的樣本：`simoneb/gex` 的 `CMG.json`（前文已研判為手造
測試資料）；`AzuraKiko/CBOE_log` 的 `snap_*.json`（實測內容是 **Cboe
Australia（CXA）股票深度委託簿**，與選擇權延遲報價無關）；
`gururafiki/muffin-agent` 的 OpenBB 契約樣本（所有數值都是佔位的 `1.0`）。

---

## 9. 未能查證的事項

1. **完整的盤外全鏈 payload**——本文的盤外直接證據只有 repo fixture 的
   **3 筆**。§2.3 的 934 筆同生共死規律是**盤中**樣本推得的結構性事實，
   §2.4 只是與之相容，**不等於已經在盤外驗過一整條鏈**。
   → 需求方在部署環境於**收盤後**抓一次 TLT 全鏈，統計
   `bid_size=0` 與 `bid=0` 的交叉表、以及 §6.3 四項一致性檢查的命中數。
   這一次抓取可以同時結清前文 §8 第 1 項（TLT 遠期 `iv=0` 實況）。
2. **`theo` 到底怎麼算的**——Cboe 端點無文件。§6.5 只證明了它**不等於 mid**、
   且會落在報價區間外，因此是獨立值；但它是否由同一筆（可能陳舊的）報價
   反推而來，未能確認。若是，它偵測該筆報價陳舊的能力就會打折。
3. **Cboe 對 `bid_size`/`ask_size` 的官方語意與更新時點**——端點無文件，
   官方站被 403 擋下。§3.1 的 10 口最低報價量來自監理通函的搜尋索引轉述，
   **未逐字核對原文**，且它規範的是**做市商的義務**，不等於 delayed_quotes
   feed 顯示的 NBBO size 一定服從它。
4. **tastytrade / Market Chameleon 的 liquidity rating 方法學**——兩者都
   確認有此功能，但**計算方式未公開**，搜尋索引也查不到公式。因此無法
   拿來當本 repo 複合指標的設計依據。
5. **盤外的 `spread_ok` 通過率**——§4.4 建議降級的依據（LEAPS 相對價差
   中位數 3.9%）來自**盤中**樣本。收盤價差通常比盤中最佳時段寬，盤外的
   實際通過率未測。
6. **凸性檢查的正確門檻**——§6.3 實測 ask 曲線凸性誤判 50/305（16%），
   本文因此不建議採用；但**改用 mid 曲線、或加上容差**是否能把誤判壓下來，
   未測。
7. **被 403 擋下、僅有搜尋索引轉述的頁面**：Cboe 監理通函 RG18-009／
   RG03-084／RG19-032、Barchart options screener 說明、TradingBlock／
   Option Samurai 流動性教育文、Cao & Wei (2010)、Wallmeier (2024)、
   arXiv 的無套利修復論文。皆未逐字核對原文。

---

## 10. 對 `option_chaser/filters.py` 的具體建議

分成兩類：**安全可做**（不改變已議定的成本/品質口徑，工程判斷即可施工）
與**需要需求方裁示**（改變候選池組成或附錄 A14.2 的口徑，本 repo 慣例
須人類簽核）。

### 10.1 安全可做（工程判斷）

**S1. 移除 `bid_size`/`ask_size` 這個選項，並把結論寫回前一份研究。**
`cboe-field-semantics.md` §1.2 第 4 點與 §8 第 7 項應更新為：盤外不歸零
（疑慮解除），但 `bid_size > 0` 與既有 `bid > 0` **恆等**（934 筆、0 例外），
量的層次又是報價義務產物——**此路不通，不要開票**。adapter 維持不取用。

**S2. 修掉 `volume >= p.min_volume` 這半條恆真條件。**
`filters.py:30` 的 `c.volume >= p.min_volume` 在 adapter 把 volume 轉成
`int(... or 0)` 之後恆真（`min_volume` 預設 0）。無論 `oi_volume_ok` 最後
怎麼處置，這半條都該處理掉——要嘛刪除，要嘛按 `Ollie1o1/options` 的
稽核結論改成 `OI >= min_oi OR volume >= min_volume`（§7.2）。
**這是純粹的死碼／邏輯瑕疵修正，不改變任何過濾結果。**

**S3. 新增單調性一致性檢查，先只做「標記」不做「刪除」。**
同一到期日、同一 option_type，`ask` 對履約價必須非遞增（call）／非遞減
（put），違反者掛上「報價與鄰近履約價不一致，可能為陳舊報價」旗標。
實測誤判率極低（307 組命中 3 組，且三組全是久未成交的冷門履約價，§6.3）。
**只加旗標不刪候選，因此不動口徑**，可直接施工。

**S4. 把 `iv_ok` 從「品質過濾」的敘事裡正名為引擎前置條件。**
純文件／命名層面（模組 docstring 與 `FilterStageResult` 的 label）。
它不影響排名（拿掉後 top10 重疊 10/10），把它跟流動性關卡混在一起會誤導
後續的放寬討論。

**S5. 保留 `quote_ok` 原樣。**買腿那半雖是贅語，但實測放寬後
**多出 0 組候選**（§4.1）——改了沒有好處，不值得動。

### 10.2 需要需求方裁示（改變候選池組成／A14.2 口徑）

**D1. 移除 `open_interest >= min_oi` 硬門檻。**
- 依據：砍掉 53% 的買腿（217→102），榜首報酬**完全沒變**（§4.3）；
  OI 是 T+1 落後數；實測 600 筆雙邊報價中 244 筆從未成交過卻有活報價。
- 選項：(a) 完全移除；(b) 改成 `OI >= min_oi OR volume >= min_volume`
  （`Ollie1o1/options` 的稽核結論，§7.2）；(c) 保留但降級成排序懲罰／
  顯示警語（前一份研究 §1.2 第 4 點的建議）。
- **為何需裁示**：直接改變候選池組成與 FB3-02（#45）「候選池過少警示」的
  觸發頻率。

**D2. 把 `spread_ok` 從硬過濾降級為顯示層警語。**
- 依據：最差成交口徑已經在成本裡誠實懲罰過寬價差，硬擋是重複懲罰且用的是
  「刪除資訊」這個更糟的方式（需求方論證，§4.4 實測支持）；
  `ranking.py:132-134` 已有現成的「買賣價差偏大（兩腿合計）」警語可承接。
- **為何需裁示**：這正面觸及附錄 A14.2 議定的成本/品質口徑分工——
  「哪些事由成本表達、哪些事由過濾表達」是產品決策。

**D3. 處理報酬率的分母爆炸。**這是本次調查認為**最該優先處理**的一項，
因為它是使用者實際回報的症狀，而且**現行四道關卡一道都攔不住**（§5）。
三個選項，成本與侵入性遞增：

- **(a) 純顯示層（最小侵入）**：`net_worst` 低於某個 tick 數時，
  在候選卡片上標注「成本僅 N 個跳動點，報酬率對報價誤差極度敏感」，
  數字照常顯示。**不動候選池、不動口徑。**
- **(b) 排序層**：報酬率相同時（或報酬率極高時）以成本大小做次要排序／
  加權，讓兩個 tick 的樂透票不會固定霸榜。
- **(c) 過濾層**：`net_worst >= 門檻`（實測 $0.30 → 榜首 1042%、$0.50 →
  743%，而只砍掉 2.3%／5.2% 的候選組數，§5.3）。
- **為何需裁示**：(c) 直接改變候選池；(a)(b) 也改變了「本 app 推薦什麼」
  的產品立場——便宜的近月價外樂透票**可能正是使用者要找的東西**，
  這不是工程能單方面決定的。

**D4. 盤外的分級與揭露。**
- 依據：業界不拒絕盤外篩選（Barchart 有 EOD 排程），而是把新鮮度做成
  一等公民的分級、只在最差一級拒答（`marketscannerpros` 的
  `REALTIME | DELAYED | EOD | STALE`，§7.3）。
- 建議形狀：快照層加一個新鮮度欄位（由 `fetched_at` 與美東交易時段推算），
  UI 在非 `REALTIME` 時揭露「這是收盤後的凍結報價，反映的是 X 月 X 日
  收盤那一刻的市場」。
- **為何需裁示**：牽涉 UI 文案與「要不要在盤外降級任何功能」的產品決策，
  且與 V1–V10 的新前端規劃（issue #47）範圍重疊，應併入該輪一起考慮。

**D5.（低優先，保險絲）`theo` 一致性檢查。**
- 依據：`theo` 是獨立於該筆報價的曲面值（§6.5 實測：0/600 等於 mid、
  19 筆落在報價區間外），可當「成本被低估」的偵測器。
- 但實測**在健康快照上一組都篩不掉**（比值全部 >1，最差口徑本身已免疫）。
- 建議：若要做，**只做標記、且定位為盤外／冷門標的的保險絲**，
  不要當常態過濾。成本極低（欄位現成），但收益也未經證實。
- **為何需裁示**：需要 adapter 新增欄位（`OptionContract` 加 `theo`），
  屬於契約變更。

### 10.3 明確不建議做的事

- **不要**新增 `bid_size`/`ask_size` 門檻（S1）。
- **不要**用 `last_trade_time` 當新鮮度門檻——它是成交時戳不是報價時戳，
  且 600 筆雙邊報價中 244 筆根本沒有這個值（§6.1）。
- **不要**單獨採用凸性檢查——實測 305 組誤判 50 組（16%），
  在加上容差並改用 mid 曲線重測之前不要上（§9 第 6 項）。
- **不要**指望換資料源或篩得更兇能解決「報酬率不合理」——
  實測顯示那是度量的性質，不是資料的性質（§5.2）。

---

## 11. 引用清單

**實測實證（本沙箱可直接下載、可逐筆重算）**

- https://raw.githubusercontent.com/eo1989/textbook_notes/master/data/YETI.json
  —— 真實 Cboe 全鏈 payload（758 筆／13 個到期日），本文 §2.3、§4、§5、
  §6.1、§6.3、§6.5 全部統計的來源
- https://raw.githubusercontent.com/AdRedrock/OptionsAnalyzer/main/data/imported/CBOE/MLTX/2025-02-12/2025-02-12_close_UTC%2B01_00_MLTX.csv
  —— 第二份獨立 Cboe 鏈（OpenBB 匯出，176 筆），§2.3 交叉驗證
- 本 repo `tests/test_data_cboe.py` 的 `PAYLOAD`
  —— 唯一的盤外樣本（2026-07-31 23:43 ET），§2.4

**原始碼實證（GitHub raw，可逐字檢視）**

- https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py
  —— Cboe provider 對 `bid_size`/`ask_size` 只做 `astype("int64")`，零特判
- https://raw.githubusercontent.com/Ollie1o1/options/main/src/filters.py
  —— 同源（cdn.cboe.com）開源篩選器：`volume >= 50 OR OI >= 10`、
  註解記載「改回 AND 是稽核缺失」、`max_bid_ask_spread_pct` 預設 0.40
- https://raw.githubusercontent.com/Ollie1o1/options/main/src/cboe_client.py
  —— 有映射 `bid_size`/`ask_size`，但過濾層完全沒用到
- https://raw.githubusercontent.com/wesso80/marketscannerpros/main/lib/options-confluence-analyzer.ts
  —— `DataQuality.freshness: 'REALTIME' | 'DELAYED' | 'EOD' | 'STALE'`、
  `hasMeaningfulOI`、只在 `STALE` 拒答的分級設計
- https://raw.githubusercontent.com/gauss314/skills/main/skills/cboe-data/references/REFERENCE.md
  —— delayed_quotes 逐欄位說明（無盤外語意）；index 的標的層
  `bid_size=0` 與 option row 無關
- GitHub code search（`api.github.com`）：
  `"bid_size" "ask_size" "theo" "iv" extension:json`（2 命中）、
  `"delayed_quotes/options" bid_size`（42 命中）、
  `"bid_size" "ask_size" "open_interest" "theo" extension:csv`（11 命中）
  —— 全網已 committed 的真實 Cboe 選擇權 payload 就只有本文採用的那幾份

**一手／權威文件（被 403 擋下，內容為搜尋索引轉述）**

- https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG18-009.pdf
  （另見 RG03-084、RG19-032）—— 做市商初始報價至少 10 口、遞減到零須補回；
  連續報價義務只涵蓋到期日 **九個月以內** 的序列（LEAPS 不在義務範圍）
- https://www.barchart.com/options/options-screener
  —— 篩選器提供 Market Close（3pm CT）與 End-of-Day（4:45pm CT）排程，
  盤後跑篩選是正常產品行為
- http://www.yorku.ca/mcao/Cao_Wei_JFM_2010.pdf 、
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1082642
  —— Cao & Wei (2010)：選擇權平均百分比價差 13.44% vs 股票 0.81%
- https://arxiv.org/pdf/2008.09454 —— Detecting and repairing arbitrage in
  traded option prices
- https://arxiv.org/pdf/2605.22792 —— 正性／單調性／凸性三段式無套利過濾
  （文中稱為 CBOE 建議），並指出 stale/asynchronous quotes 會產生靜態套利
- https://onlinelibrary.wiley.com/doi/full/10.1002/fut.22495
  —— Wallmeier (2024)，OptionMetrics IvyDB 的資料品質問題
- https://www.tradingblock.com/blog/options-liquidity 、
  https://optionsamurai.com/blog/options-liquidity-tips-to-identify-the-best-opportunities-with-real-market-example/
  —— 各流動性指標的地位；quote size「less frequently discussed」
- https://support.tastytrade.com/support/s/solutions/articles/43000435335
  —— tastytrade 的收盤後 15 分鐘選擇權交易說明

**本 repo**

- `option_chaser/filters.py:23-34`（四道過濾）、`:71`（配對合理性 `net_mid > 0`）
- `option_chaser/ranking.py:109-113`（`spread_baseline_return`）、
  `:132-134`（既有的「買賣價差偏大」警語）
- `option_chaser/valuation.py:211-218`（`spread_scenario_value`）、
  `:245`（`net_worst`）、`:106-116`（`evaluate_contract` 的 IV assert）
- `option_chaser/data/cboe.py:31-45`（OCC 解析）、`:58-68`（`_positive_or_none`）
  —— 目前未取用 `bid_size`/`ask_size`/`theo`
- `tests/test_data_cboe.py` —— 本文唯一的盤外樣本
- `docs/research/cboe-field-semantics.md` —— 前一份調查，本文 §1.1、§4.3、
  §6.1 多處交叉引用；其 §8 第 7 項由本文 §2 結清
- `docs/research/option-chain-data-sources.md` —— 資料源比較，本文不重複
- `docs/user-feedback-v3.md` 第 4 點 —— 本文 §5.2 對該症狀的重新歸因
