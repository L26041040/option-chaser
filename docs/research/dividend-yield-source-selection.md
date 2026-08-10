# 股利／配息殖利率 q 的正式環境取得方案：外部資料源評選與換算口徑

研究日期：2026-08-09。前置文件＝同目錄
`heatmap-valuation-method-selection.md`（同日，commit `91e8fb9`）。

**本文性質聲明（guardrail）**：本票只做**外部資料源**評選、真實資料量化與書面
建議；**不修改 `option_chaser` 引擎、不修改 fixtures／契約樣本、不開票、不自行
鎖定資料源**。文中「建議」一律指需要需求方核准後才會進入實作票的建議。

**本文的起點（不重新論證）**：前置文件已判定 Heatmap／Crossover 應採
Bjerksund–Stensland 1993 ＋ 連續股利殖利率 q ＋ 價格錨定，並明確結論
**「q 是唯一需要新增的輸入」**（該文 §10-3：S／K／到期日／bid-ask／IV／
期限對齊的 r 都已在手）。本文只回答**那個 q 在正式環境要從哪裡拿、怎麼算**。

**明確不在本文範圍**（前置文件與 #110 已各自處理，本文只引用不重做）：
BS93／CRR／Merton 的公式與收斂性、IV 價格錨定、Crossover 語意，以及
**Method E**（#110 的跨履約價 chain-implied 校準）。Method E 只在 §10 以
「已知的另一條取得路徑」身分出現，本文用它當**對照基準**而不重新推導或重新
論證其優劣。

---

## 0. 資料品質聲明（每一條主張都標證據等級）

沿用前置文件的四級標記，全文不出現「沙箱連不到 ⇒ 不存在／production 也連不到」
這種推論：

- **【實測】** 本地真實資料量化，任何人可用 repo 現成程式重跑。本文所有數字
  都走 `scripts/research_valuation_methods.py`（#110 建立的研究原語）＋
  `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（真實 TLT LEAPS 報價）。
- **【一手原始碼】** 逐字讀到的公開原始碼。本次全部經 `raw.githubusercontent.com`
  取得（該網域是本沙箱目前唯一可用的外部通道）。原始碼本身即一手來源，但
  **它證明的是「某個公開客戶端這樣呼叫這個端點」，不等於端點官方文件的承諾**。
- **【索引轉述】** WebSearch 回傳的搜尋索引摘錄。**不是**一手資料。
- **【本文推導】** 我自己的推理或設計建議，沒有外部背書。

**沙箱出口狀態（本次實測，2026-08-09）**：`curl` 對 `www.ishares.com`、
`query1.finance.yahoo.com`、`financialmodelingprep.com`、`api.nasdaq.com`
一律連線失敗（HTTP code `000`）；`raw.githubusercontent.com`（200）與
`api.github.com`（200）可用。**這是本沙箱的出口政策，與這些站台是否存在、
Vercel 能否連到完全無關**——本文**沒有**打到過任何一個候選 vendor 端點，
凡列出的回應形狀一律標明是「文件形狀／客戶端原始碼推得的形狀」，
**不是觀測到的 payload**。需要人工在 Vercel 上驗證的項目全部集中在 §12。

---

## 目錄

1. 摘要（結論先行）
2. 問題定義：q 餵給誰、精度門檻多少
3. 我們**現有**的資料源帶不帶 q
4. ETF 發行商官方配息資料（範圍 1）
5. 公開市場資料 API（範圍 2）
6. 對照表
7. 從原始欄位到引擎的 q：公式與真實資料量化（範圍 3）
8. 資料缺漏時的 fallback（範圍 4）
9. 新鮮度／快取／陳舊規則（範圍 5）
10. 與 Method E（#110）的關係
11. 施工形狀：沿用 r 的既有 pattern，偏離處逐條說明
12. 侷限、無法一手查證清單、與 reviewer 驗證清單
13. 六問六答（決策用）
14. 引用清單

---

## 1. 摘要（結論先行）

- **推薦 primary：Yahoo Finance chart 端點的 `events.dividends`（免金鑰、
  單一 GET、stdlib urllib 可解析）**，取**過去 12 個月的實際配息金額（美元）**，
  在引擎端除以**本次快照自己的 spot**換成 q。理由：它是**唯一一個
  (a) 本 repo 已經接受其 ToS 風險等級、(b) 其網域已在本專案的 Vercel 正式環境
  被實測連通過、(c) 回傳的是配息「金額＋除息日」而不是別人算好的殖利率**的
  候選（§5.1、§7.3）。
- **推薦 backup：Financial Modeling Prep `stable/dividends`**（需免費金鑰，
  250 次／日，正式文件化 JSON）。它的網域**已在本專案 Vercel 正式環境實測
  回過 `401 Invalid API KEY`**——網路可達、純粹缺金鑰（`interest-rate-source-selection.md`
  §6.4，本 repo 既有紀錄）。第二 backup ＝ Nasdaq 免鑰端點（§5.3）。
- **明確不推薦當 primary：ETF 發行商官網（iShares）**。不是因為不權威——正好
  相反，它是最權威的——而是因為它的機器可讀通道是**網站內部 DataTables AJAX**
  （`?tab=distributions&fileType=json` 回 `{"table":{"aaData":[[…]]}}`），
  無文件、無 SLA、逐發行商各一套、且部分區域站台需要通過 cookie／投資人身分
  閘門才拿得到下載連結（§4）。**每支標的都要先知道它的 issuer 與 product id**
  這件事本身就與「使用者可以輸入任意 ticker」的產品定位衝突。
- **明確不推薦當 q 的來源：30 天 SEC 殖利率**。它是**基金持債的到期收益率
  口徑**，不是基金實際發出的現金分配率，兩者在本次真實資料上差 **0.582pp
  的 q**，換算成 Heatmap 中位格差約 **3.59pp**【實測，§7.4】——這是一個
  純粹因為選錯欄位而付出的誤差，且方向系統性。
- **最重要的量化結果（本文核心）**【實測，§7.3】：對 2026-07-17 的真實 TLT
  LEAPS 快照，
  - 市場自身隱含的 carry（用 repo 自己的 #110 原語細網格重解）＝ **q\* = 4.510%**；
  - 用**外部配息資料**算出來的 q ＝ **4.486%（`ln(1+D/S)`）到
    4.588%（簡單 `D/S`）**，與 q\* 差 **0.024–0.078 個百分點**，
    換算 Heatmap 中位格差 **0.15–0.48pp**。（第三種慣例
    `−ln(1−D/S)` 得 4.697%、差 0.187pp，同樣達標，只是略遠。）
  - 對照前置文件量測的精度門檻（q 差 1.5pp → Heatmap 中位格差 9.26pp）：
    **外部資料源這條路，誤差比門檻小一到兩個數量級，遠遠達標**；而
    **q=0（今天的引擎）差 4.510pp → 中位格差 27.84pp**。
  - 換句話說：**外部配息資料與市場隱含 carry 在這一份真實快照上互相印證到
    0.03–0.08pp**。這是 n=1 的證據（§12 第 5 點），但它是本文最有決策價值的
    數字——它說明外部資料 q 與 Method E **不是競爭關係，是互為交叉驗證**。
- **真正會付出代價的只有三個決定**【實測，§7.4】，其餘都在噪音裡：

  | 決定 | 選錯的代價（q） | 換算 Heatmap 中位格差 |
  |---|---|---|
  | 用現金分配額 vs 用 30 天 SEC 殖利率 | 0.582pp | **3.59pp** |
  | 用**我們**快照的 spot vs 直接抄 vendor 算好的殖利率百分比 | 0.142pp | 0.87pp |
  | 複利慣例（`D/S`／`ln(1+D/S)`／`−ln(1−D/S)`）最差差距 | 0.163pp | 1.01pp |
  | （對照）完全沒有 q | 4.510pp | **27.84pp** |

  **直接推論：管線必須快取「配息金額（美元）」而不是「殖利率（%）」**——
  抄 vendor 的百分比等於偷偷把他們的價格基準混進我們的模型（§7.5）。
- **不要建配息時間表**。實測：整份除息日曆的「相位」（除息日落在月初或月底）
  只值 **<0.01pp** 的 q，但**多算或少算一次配息就值 0.16pp**（≈ 0.99pp 格差）
  【實測，§7.6】。也就是說，建時間表**引進的離散化風險大於它解決的問題**——
  這與 #110 §6 排除 Method C 的判斷方向一致，本文用 q 的敏感度重新坐實一次。
- **工程成本**：一次 HTTP GET ＋ 一個純函式模組（解析、加總、換算），
  **零新增套件**（stdlib `urllib` ＋ `json`，與 `option_chaser/data/cboe.py`
  同款設計）。快取沿用 `api_app/rate_cache.py` 的 Neon 形狀，唯一實質偏離是
  **q 是 per-symbol，利率是全站單一值**，所以快取要從單筆改成以 symbol 為鍵
  （§11）。
- **仍需需求方裁示三件事**（§13-6）：ToS 取捨（Yahoo 灰色管道 vs FMP 的
  Data Display Licensing Agreement）、是否申請 FMP 免費金鑰、以及
  q 與 Method E 的**主從順序**。

---

## 2. 問題定義：q 餵給誰、精度門檻多少

**q 的消費者**（引用前置文件，不重做）：`scenario_leg_value` →
Heatmap 每一格、Crossover 邊界、Greeks。**Spread 排名不吃 q**
（`rank_spreads` 用該 Spread 自身到期日的內在價值，T3／#17 既有裁示），
所以劇本庫卡片數字、`best_return`、V9 成本走勢圖都不會因為 q 而變
（前置文件 §8 已逐條追過）。

**精度門檻（本文的評分尺）**——前置文件 §5.4 的實測：

> q 抓錯 **1.5 個百分點**，Heatmap 格值中位數差 **9.26pp**、p90 差 22.62pp。

本文全部用這條線性刻度把「q 的誤差」翻譯成「使用者實際看得到的格差」：
**1.00pp 的中位格差 ⟺ 0.162pp 的 q**【本文推導，由上述比例換算】。
這個換算是線性外推（前置文件只量了 ±1.5pp 兩點），在本文關心的
±0.1–0.7pp 小區間內用它做量級判斷是合理的，但**不是精確保證**（§12 第 6 點）。

**q 的定義（決定要抓哪個欄位）**：Merton (1973) 的 q 是**連續複利的比例式
持有收益率**——持有標的的人以連續速率 q 收到收益，因此遠期價
`F = S·e^{(r−q)T}`。它有兩個直接推論，兩個都在 §7 產生實際後果：

1. 它要的是**基金／公司實際發出的現金**（配息、分配），不是「基金持有的
   債券的到期收益率」。**30 天 SEC 殖利率是後者**。
2. 它是**比例**，所以分母（spot）必須是**我們這次分析用的那個 spot**，
   不能是 vendor 在別的時點、用別的價格算好的百分比。

---

## 3. 我們**現有**的資料源帶不帶 q

先排除「其實不用新增資料源」這個最省事的可能。

| 現有來源 | 有沒有配息／殖利率欄位 | 證據 |
|---|---|---|
| **Cboe delayed quotes**（主鏈源，`option_chaser/data/cboe.py`） | **沒有** | 【一手原始碼】OpenBB 的 Cboe provider 是這個端點最完整的公開消費者，`models/options_chains.py` 與 `utils/helpers.py` 全檔**沒有任何 dividend／yield／payout 字樣**；它取到的標的層欄位只有 `current_price`／`close`／`prev_day_close`／`iv30`／`iv30_change`／`security_type`。 |
| **Cboe 同主機的 equity quote 端點**（`/delayed_quotes/quotes/{sym}.json`，本 repo 尚未用） | **沒有** | 【一手原始碼】同上，`models/equity_quote.py` 的欄位全是 iv30／hv30／iv60／iv90 的年度高低，**無 dividend／yield**。 |
| **yfinance**（備援鏈源，`option_chaser/data/yf.py`） | **有，但目前沒抓** | 【一手原始碼】見 §5.1。本 repo 只呼叫 `option_chain()` 與 `fast_info`，沒碰配息通道。 |
| **Treasury 曲線**（`option_chaser/data/treasury.py`） | 不適用 | 只有利率。 |

**結論**：**現有主資料源不帶 q，必須新增一條取得管線。**
（順帶：Cboe feed 的 `theo` 欄位**內含**了 vendor 自己的股利假設效果——
前置文件 §4.3 已用它證明 vendor 用的是美式含股利模型——但那是一個**已經
算完的價格**，無法從中乾淨分離出一個 q 來餵我們自己的模型。前置文件已經
把「從價格反推 carry」這條路歸給 Method D／E，不在本文範圍。）

---

## 4. ETF 發行商官方配息資料（範圍 1）

### 4.1 iShares（TLT 的發行商）

- **人可讀頁面**：`https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf`
  ——含 Distributions 分頁、30-Day SEC Yield、以及 fact sheet PDF
  （`https://www.ishares.com/us/literature/fact-sheet/tlt-ishares-20-year-treasury-bond-etf-fund-fact-sheet-en-us.pdf`）。
  【索引轉述】
- **機器可讀通道**：網站內部的 DataTables AJAX。逐字取自一個公開的
  iShares 客戶端【一手原始碼，`0rShemesh/ishares_etf_data`
  `src/ishares_etf_data/core.py`】：

  ```
  https://www.ishares.com/us/products/{productId}/{slug}/1467271812595.ajax
      ?tab=distributions&fileType=json&subtab=table
  ```

  該客戶端消費的回應形狀是
  `{"table": {"aaData": [[{"display": …, "raw": …}, …], …]}}`——
  每列是一組 `{display, raw}` 儲存格，第 0 欄是 `YYYYMMDD` 的 raw 日期。
  **注意：該客戶端只用了第 0 欄的日期**（它拿 distributions 分頁當「有哪些
  資料日」的清單用），**所以金額、除息／發放日、分配類型分別是第幾欄，
  本文沒有任何證據可以確定**——這是一個必須實際打一次才知道的東西。
  另一個廣為使用的姊妹端點是 holdings：
  `…/1467271812596.ajax?fileType=csv&fileName={TICKER}_holdings&dataType=fund`
  （多個獨立專案交叉印證同一形狀【一手原始碼】：`business-science/tidyquant`、
  `penny-vault/pvdata`、`leoncvlt/etf4u`、`erfanio/etf-holdings` 等）。

- **判定：不建議當 primary**，四個獨立理由（重要性遞減）：
  1. **要先知道 issuer 與 product id**。URL 裡的 `239454` 是 BlackRock 內部
     產品編號，**沒有從 ticker 到 product id 的公開對照表**。本 app 接受
     任意 ticker，這條路等於要為每一支使用者可能輸入的標的維護一張人工
     對照表——與產品定位直接衝突。
  2. **逐發行商各一套**。State Street／Vanguard／Invesco 的端點形狀各不相同
     （例：Vanguard 走
     `https://investor.vanguard.com/investment-products/etfs/profile/api/{…}`
     一類路徑【一手原始碼，`vokuxyz/vestra` 的 provider schema】）。
     支援 N 個發行商就是 N 個 adapter。
  3. **無文件、無 SLA，且形狀是 DataTables 內部結構**。`aaData` 是
     jQuery DataTables 的序列化格式，欄位順序隨網頁改版而變，**沒有任何
     欄名可以錨定解析**——這比 Treasury CSV（至少有 `"1 Mo"` 這種表頭）
     脆弱一個級別。
  4. **部分區域站台有身分閘門**。一個公開的 iShares 抓取專案自述其歐洲站
     路徑「需要驅動 headless browser 通過 cookie 同意橫幅與投資人類型／
     國別閘門（兩者都必須先過，真正的 `.ajax` 下載連結才會出現在 DOM 裡）」
     【一手原始碼，`dibyajyotiron/etf-holdings-parser` README】。
     **美國站是否同樣有閘門，本文未能查證**（§12）。serverless 函式裡跑
     headless browser 在 60 秒上限與 bundle 體積下不可行。

- **但它有一個不可替代的用途**：**當作人工覆核的 ground truth**。發行商
  官網是配息金額的權威來源，需求方要驗證某個 vendor 給的數字對不對時，
  應該對照它，而不是對照另一個 aggregator（§12 驗證清單第 4 項）。

### 4.2 30 天 SEC 殖利率：權威，但是**錯的欄位**

發行商頁面上最顯眼、最「官方」的殖利率數字就是 30-Day SEC Yield（TLT 於
2026-08-06 報 **5.17%**【索引轉述】）。**它不該拿來當 q**：

- 它是**標準化的、基於基金持有部位到期收益率、扣除費用後**的收益衡量，
  設計目的是讓不同基金之間可比；**它不是基金實際發出的現金分配率**。
  同一天同一支基金的 12 個月實際分配殖利率是 **4.73%**【索引轉述】——
  兩者差 0.44pp，且在利率變動期會系統性分歧（新買進的債券票息高於
  組合平均時，SEC 殖利率會領先實際分配）。
- **本次量化**：把 5.17% 直接當 q，與市場隱含的 4.510% 差 **0.660pp**，
  Heatmap 中位格差 **4.07pp**、p90 **9.95pp**【實測，§7.3】。相對地，
  用實際現金分配算的 q 只差 0.024–0.078pp。**選錯這個欄位的代價，是
  選對欄位之後所有其餘決定加起來的好幾倍。**
- **「distribution rate」（分配率）**是發行商頁上另一個數字，口徑接近
  「最近一次分配 × 頻率 ÷ NAV」，方向上比 SEC 殖利率正確得多，但各家
  定義不完全一致，而且**它仍然是別人用別人的價格算好的百分比**（§7.5
  說明為什麼這件事本身就要付 0.87pp 的格差）。

---

## 5. 公開市場資料 API（範圍 2）

### 5.1 Yahoo Finance —— 推薦 primary

**兩條可用通道，本文推薦後者：**

**(a) `quoteSummary` 的 `summaryDetail` 模組**——【一手原始碼，`ranaroussi/yfinance`】
`yfinance/scrapers/quote.py:43` 寫死
`_QUOTE_SUMMARY_URL_ = f"{_BASE_URL_}/v10/finance/quoteSummary"`，
`_BASE_URL_ = 'https://query2.finance.yahoo.com'`（`yfinance/const.py:2`），
`summaryDetail` 是官方合法模組之一（`const.py` 的 `quote_summary_valid_modules`
逐字列出）。OpenBB 的 yfinance ETF provider 從這條路取的鍵名逐字是
`"yield"`、`"trailingAnnualDividendRate"`、`"trailingAnnualDividendYield"`
【一手原始碼，`openbb_yfinance/models/etf_info.py:34-36, 238-240`】。
**缺點兩個，都是硬傷**：(i) 它給的是**別人算好的百分比**，不是金額
（§7.5 要付 0.87pp 的格差）；(ii) `yfinance` 的所有請求都經過
cookie＋crumb 機制（`data.py::_make_request` 逐字：
`crumb, strategy = self._get_cookie_and_crumb()`，且 400 以上會切換
cookie 策略重試），**用 stdlib urllib 手刻要複製整套 crumb 取得流程**。

**(b) chart 端點的 `events`（推薦）**——【一手原始碼，同套件】
`yfinance/scrapers/history.py:198,208` 逐字：

```python
params["events"] = "div,splits,capitalGains"
url = f"{_BASE_URL_}/v8/finance/chart/{self.ticker}"
```

回應形狀由 `yfinance/utils.py::parse_actions` 逐字確定
（**文件形狀，非本文觀測**）：

```
chart.result[0].events.dividends    = { key: {"amount": float, "date": unix_ts, "currency"?: str}, … }
chart.result[0].events.capitalGains = { key: {"amount": float, "date": unix_ts}, … }
chart.result[0].events.splits       = { key: {"numerator", "denominator", "date", "splitRatio"}, … }
```

**為什麼推薦這一條**：

1. **它給的是金額（美元）＋除息日**，不是別人算好的百分比——正是 §7 證明
   最準的那個輸入形狀。
2. **它把 `capitalGains` 與 `dividends` 分開**。對基金這是關鍵：資本利得
   分配同樣會壓低 NAV，但它是不定期的，**需要明確決定要不要計入**（§8 的
   irregular case）。一個只給「殖利率」的欄位不讓你做這個決定。
3. **單一 GET、JSON、stdlib 可解析**，與 `option_chaser/data/cboe.py` 同款
   設計，**不需要 yfinance SDK，因此不觸碰 pandas/numpy 的 bundle 問題**。
   這一點是硬約束不是偏好：`pyproject.toml` 現行的
   `[project] dependencies` 只有 `fastapi`／`psycopg[binary]`／`tzdata`，
   `yfinance` 明確被移到 `yf` optional extra，該處註解逐字寫著
   「移出核心依賴是為了不把 pandas/numpy 拖進 serverless 函式」，而
   `requirements.txt` 的表頭又記錄了 V1／#48 的實測結論
   ——**Vercel 的 Python builder 認的是 `pyproject.toml` 的
   `[project] dependencies`**。兩者合起來的含意是：
   **正式環境的 lambda 裡沒有 yfinance SDK**，
   任何 Yahoo 通道都只能手刻 stdlib 版本。
   **這也意味著 crumb 問題沒有「改用 SDK 就好」的逃生口**——它是本推薦
   唯一的硬技術風險，必須先實測（§12.3 第 1 項）。
4. **標的無配息時自然回空**，這正是 q=0 的正確答案，且是**肯定的答案而不是
   失敗**（§8 的關鍵區分）。
5. **免金鑰、免註冊、免配額申請。**
6. **本專案已經接受這個 vendor 的 ToS 風險等級**——`option_chaser/data/yf.py`
   就是 Cboe 失敗後的備援鏈源，且 `option-chain-data-sources.md` §3.1 已把
   「Yahoo ToS 灰色」白紙黑字列為已知並接受的風險。**新增這條 q 管線不會
   擴大既有的 ToS 曝險面，只是多打同一個 vendor 一次。**

**已知風險（必須誠實列出）**：

- **無官方文件、無 SLA**，是 Yahoo 網站前端的內部端點（本 repo 既有紀錄：
  `interest-rate-source-selection.md` §3.5「Yahoo 從未公開這是給第三方消費
  的 API」）。
- **chart 端點是否需要 crumb／cookie，本文未能驗證**。`yfinance` 對**所有**
  端點都掛 crumb，但那是套件的統一做法，**不代表 chart 端點本身強制要求**。
  這是 §12 驗證清單的第 1 項，也是本推薦最主要的未決技術風險。
  **若實測需要 crumb**，備援（FMP）立刻升為 primary——這個切換不需要重開
  研究票，判準與 `interest-rate-source-selection.md` §6.3 既有的
  「探測結果與桌面排序矛盾時以探測結果為準」一致。
- **網域可達性**：`interest-rate-source-selection.md` §6.4 記錄本專案於
  2026-08-05 在 **Vercel 正式環境**對 Yahoo 免鑰端點探測**成功（200、
  拿到真實 ^IRX/^FVX/^TNX/^TYX 報價）**。這證明 **`query*.finance.yahoo.com`
  這個網域從 Vercel 出得去、且至少有一個匿名端點可用**；**它不證明
  `v8/finance/chart?events=div` 這條路徑也匿名可用**（該次探測用的是哪條
  路徑，repo 未記錄——§12 第 2 點）。

### 5.2 Financial Modeling Prep —— 推薦 backup

- **端點**（【一手原始碼】，逐字取自 OpenBB 的 FMP provider
  `openbb_fmp/models/historical_dividends.py`）：

  ```
  https://financialmodelingprep.com/stable/dividends?symbol={SYM}&limit={N}&apikey={KEY}
  ```

- **欄位**（同上，逐字取自該檔的 `__alias_dict__`，**文件形狀**）：
  `date`（除息日）、`dividend`（金額）、`adjDividend`（拆分調整後金額）、
  `yield`（**該次配息代表的殖利率，以百分比表示——OpenBB 自己掛了一個
  `v / 100` 的 normalizer**）、`recordDate`、`paymentDate`、
  `declarationDate`、`frequency`。
  **同時給金額與殖利率**，所以 §7.5 的「拿金額、自己除」可以照做。
- **金鑰／配額**：需要免費自助申請；免費層 **250 次／日**、
  近 30 天 500MB 頻寬、5 年歷史【索引轉述，多來源一致】。對本 app
  「一天刷新數次、每次數個標的」的用量寬裕。
- **可達性**：**已在本專案 Vercel 正式環境實測回 `401 Invalid API KEY`**
  ——網路連通，純粹缺金鑰（`interest-rate-source-selection.md` §6.4，
  repo 既有紀錄）。這是所有候選裡**唯一一個 production 可達性已被本專案
  自己證實**的商業 vendor。
- **⚠ 授權**：搜尋索引指出「展示或再散布來自 FMP 的資料需要與 FMP 簽
  Data Display and Licensing Agreement」【索引轉述，**未逐字核對 ToS 原文**】。
  本 app 的用法是**把 q 當模型輸入**，畫面上只會顯示一個算出來的 q 與
  來源標籤，不逐筆展示 FMP 的配息表——這**可能**不構成「展示／再散布」，
  但**本文無法替需求方判斷**。列入 §13-6 的裁示點。
- **可靠性折扣**：商業聚合站，**已知至少改版過一次**（Legacy 與 Stable
  兩套文件並存），本 repo 前次研究已因此把它評為「第三層」而非前兩層
  （`interest-rate-source-selection.md` §3.7）。本文沿用同一評級，把它
  放在 backup 而非 primary。

### 5.3 Nasdaq 免鑰端點 —— 第二 backup

- **端點**（【一手原始碼】，逐字取自 OpenBB 的 Nasdaq provider
  `openbb_nasdaq/models/historical_dividends.py`）：

  ```
  https://api.nasdaq.com/api/quote/{SYMBOL}/dividends?assetclass={stocks|etf}
  ```

  該 fetcher 明寫 `require_credentials = False`（**免金鑰**），先試
  `assetclass=stocks`，回應 `status.rCode == 400` 時改試 `etf`——
  **所以最壞情況是兩次 GET**。它同時掛了瀏覽器等級的標頭
  （`openbb_nasdaq/utils/helpers.get_headers("json")`）。
- **欄位**（同上，**文件形狀**）：`data.dividends.rows[]` 每列含
  `exOrEffDate`（`MM/DD/YYYY`）、`amount`（帶 `$` 前綴的字串，OpenBB 自己
  剝 `$` 與 `N/A`）、`type`、`declarationDate`、`recordDate`、`paymentDate`。
  另有頂層的 **`data.annualizedDividend` 與 `data.yield`**
  【一手原始碼，`rtybase/tests` 的 `get_dividends.py` 逐字讀這兩個鍵】——
  **這是唯一一個既給明細金額、又直接給年化配息金額的免鑰來源**，很適合
  當交叉驗證。
- **判定**：免鑰是大優點，但 (i) 與 Cboe／Yahoo 同樣是**無文件的網站內部
  端點**；(ii) 需要瀏覽器等級標頭才回得動（雲端出口 IP 更容易被擋）；
  (iii) **本專案從未在 Vercel 上測過這個網域**。因此排在 FMP 之後。

### 5.4 其餘候選（逐一剔除，理由與本 repo 既有評選一致）

| 候選 | 剔除理由 |
|---|---|
| **Alpha Vantage** | 免費層 **25 次／日、5 次／分鐘且全站帳號共用**（`interest-rate-source-selection.md` §3.6 既有紀錄）。本 repo 已把 Alpha Vantage `HISTORICAL_OPTIONS` 列為選擇權鏈的候選備援；再讓它承擔 q 會共搶同一個 25 次／日配額。且本次搜尋**未能確認**存在一個獨立的 `DIVIDENDS` function——索引只查到配息資訊經由 `TIME_SERIES_DAILY_ADJUSTED` 的 split/dividend 事件提供【索引轉述】。 |
| **Polygon.io（已更名 Massive）** | `/v3/reference/dividends` 存在，參數含 `ticker`／`ex_dividend_date`／`cash_amount`／`frequency`／`dividend_type`，reference 端點在免費層可用，但**免費層 5 次／分鐘**【索引轉述】。本 repo 既有評選已判定「付費解一個政府／同業本來就免費公開的問題不成比例」（§3.8 同一邏輯）。可列為「若未來因選擇權鏈已訂閱 Starter，順帶取用」的加分項。 |
| **Finnhub** | `GET /stock/dividend?symbol=&from=&to=` 欄位齊全——`symbol`／`date`（**Ex-Dividend date**）／`amount`／`adjustedAmount`／`payDate`／`recordDate`／`declarationDate`／`currency`／`freq`（`0 Annually, 1 Monthly, 2 Quarterly, 3 Semi-annually, 4 Other`）【**一手原始碼**，Finnhub 官方產生的客戶端 repo `Finnhub-Stock-API/finnhub-go` 的 `api/openapi.yaml`，逐字】。**剔除理由**：本 repo 既有研究已記錄「免費層能否呼叫，正反查證皆未得」，且免費層條款限個人非商用，並有公開的資料品質 issue（`option-chain-data-sources.md` §3.7）。本文沿用該結論，不重新查證。 |
| **Tiingo** | 有 corporate-actions 配息 API，免費 starter 金鑰可用【索引轉述】。**剔除理由**：索引明確指出「個人層級的訂價不是一份概括的再散布授權」【索引轉述】——對一個**已部署、可公開存取**的 app 而言，這是比 FMP 更明確的授權疑慮，且它並不提供 FMP／Nasdaq 沒有的東西。 |
| **SEC／EDGAR** | XBRL `companyconcept`／`frames` API 免鑰、免費、權威，但它服務的是**營運公司的財報標記**（10-K／10-Q）。ETF 是註冊投資公司，走 N-CEN（年報）／N-PORT（季報，且有延遲）路徑，**沒有一個逐次分配、及時的 per-share 分配數列**【索引轉述＋【本文推導】】。**延遲本身就是致命傷**：一個季度延遲的資料無法回答「上個月配了多少」。**本文未能查證** TLT 的 CIK 底下是否真的有任何配息相關 XBRL concept 被填（§12）。 |
| **CME／交易所授權資料** | 沿用 `risk-free-rate-for-bs.md` §3.1 的既有結論：需簽授權，對免費工具不可行。不重新查證。 |

---

## 6. 對照表

評選維度沿用本 repo `interest-rate-source-selection.md` §2 的八項，以便與
利率那次選型可直接對照。

| 來源 | ①機器可讀 | ②金鑰 | ③給的是金額還是%| ④更新 | ⑤可靠性 | ⑥配額 | ⑦Vercel 可達性 | ⑧stdlib 成本 |
|---|---|---|---|---|---|---|---|---|
| **Yahoo chart `events`**（推薦 primary） | JSON，**無官方文件** | 免鑰 | **金額＋除息日**，dividends／capitalGains 分開 | 逐日 | 無 SLA、逆向工程，本 repo 已接受同級風險 | 未公布，易限流 | **網域已實測可達**；此路徑未測 | 低（單 GET，**crumb 需求未確認**） |
| **FMP `stable/dividends`**（推薦 backup） | JSON，**正式文件化** | 免費申請 | **金額＋`yield`兩者皆有** | 逐日 | 中（商業聚合站，已知改版過一次） | 250/日 | **已實測回 401＝可達** | 低 |
| **Nasdaq `api/quote/…/dividends`** | JSON，無官方文件 | **免鑰** | **金額＋`annualizedDividend`** | 逐日 | 無 SLA，需瀏覽器標頭 | 未公布 | **未測** | 低（最壞兩次 GET） |
| iShares AJAX | JSON，**DataTables 內部結構** | 免鑰 | 金額（欄位順序未知） | 逐次分配 | 無 SLA、無欄名可錨定、部分站台有身分閘門 | 未公布 | 未測 | 中高（要 ticker→productId 對照表） |
| 30 天 SEC 殖利率 | 同上頁面 | — | **%，且是錯的口徑** | 月 | 權威但**語意不對** | — | — | — |
| Alpha Vantage | JSON，文件化 | 免費申請 | — | 逐日 | 穩定 | **25/日全站共用** | 未測 | 低 |
| Polygon／Massive | JSON，文件化 | 需金鑰 | 金額 | 逐日 | 商業 SLA | **免費層 5/分** | 未測 | 低 |
| Finnhub | JSON，**官方 OpenAPI** | 需金鑰 | 金額（欄位最完整） | 逐日 | 有公開品質 issue | 免費層限非商用 | 未測 | 低 |
| Tiingo | JSON，文件化 | 免費 starter | 金額 | 逐日 | 中 | 依方案 | 未測 | 低 |
| SEC／EDGAR | JSON／XML，文件化 | 免鑰 | **不提供逐次分配數列** | 季／年（有延遲） | 極強 | 有文件 | 未測 | — |

---

## 7. 從原始欄位到引擎的 q：公式與真實資料量化（範圍 3）

**這一節是本文的實質內容。** 全部數字由
`scripts/research_valuation_methods.py`（repo 既有）＋ TLT 真實 fixture
算出，任何人可重跑覆核。

### 7.1 量測設定

- 標的部位：`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`
  ——真實 TLT 2028-12-15 LEAPS call，`S = 84.52`、`T = 2.4164y`、
  `r = 0.0426`（期限對齊的 2.4 年 Treasury 量級，與前置文件同值）。
- **對照基準 q\***：用 repo 自己的 #110 原語（`implied_vol_call`）對
  **近價位四檔**（K=79/80/85/90，排除 K=130 深度 OTM 的真實 skew，
  排除理由沿用 #110 §3.2）在 2%–8% 上以 **0.01pp 的細網格**重解跨履約價
  隱含波動率離散度的最小值：

  **q\* = 4.510%**（離散度 0.1754 vol pt）【實測】。

  （#110 的粗網格結論是 4.5%；本文以獨立寫的細網格重跑得 4.510%，
  **確認 #110 的數字**，並取得後續比較所需的解析度。）

### 7.2 配息原始資料（**證據等級最弱的一環，請注意**）

TLT 的實際配息金額**無法在本沙箱取得**。以下是搜尋索引摘錄
【索引轉述，**未經一手核對**】：

- 逐月配息，2026-07-01 每股 **$0.318**、2026-08-03 每股 **$0.330**；
- 12 個月移動殖利率 **4.73%**（as of 2026-08-06）；
- 遠期／年化殖利率 **4.83%**（as of 2026-08-04）；
- 30 天 SEC 殖利率 **5.17%**（as of 2026-08-06）。

**自洽性覆核【本文推導】**：年化最近一次配息 = $0.330 × 12 = $3.96；
若它對應 4.83% 的殖利率，隱含的價格基準是 3.96 / 0.0483 = **$81.99**。
在同一個價格基準上，4.73% 的 TTM 殖利率對應 TTM 分配總額
0.0473 × 81.99 = **$3.878**。另一個 aggregator 報的「年配息 $3.90」
在同一基準上是 4.76%，與 4.73% 差 **0.03pp**——
**aggregator 之間的不一致約 0.03pp 量級**，遠小於本節其他任何誤差項。

**本節之後所有計算用的輸入是「$3.878／年的 TTM 分配總額」與
「$3.96／年的年化最近值」這兩個金額**，除以**我們自己快照的 spot 84.52**。

### 7.3 候選公式的實測比較（核心表）

**全部除以我們快照的 spot 84.52**（為什麼這件事重要見 §7.5）：

| 候選 q 算法 | q | 距 q\*=4.510% | ≈Heatmap 中位格差 | ≈p90 |
|---|---|---|---|---|
| TTM $3.878 / S，`ln(1+D/S)` | **4.486%** | **0.024pp** | **0.15pp** | 0.36pp |
| 年化最近 $3.96 / S，`ln(1+D/S)` | 4.579% | 0.069pp | 0.42pp | 1.04pp |
| **TTM $3.878 / S，簡單 `D/S`** | **4.588%** | **0.078pp** | **0.48pp** | 1.18pp |
| 年化最近 $3.96 / S，簡單 `D/S` | 4.685% | 0.175pp | 1.08pp | 2.64pp |
| TTM $3.878 / S，`−ln(1−D/S)` | 4.697% | 0.187pp | 1.15pp | 2.82pp |
| **直接抄 vendor 的 TTM 殖利率 4.73%** | 4.730% | 0.220pp | 1.36pp | 3.32pp |
| 直接抄 vendor 的遠期殖利率 4.83% | 4.830% | 0.320pp | 1.98pp | 4.83pp |
| 30 天 SEC 殖利率，`ln(1+y)` | 5.041% | 0.531pp | 3.28pp | 8.00pp |
| **30 天 SEC 殖利率，如發布值** | **5.170%** | **0.660pp** | **4.07pp** | 9.95pp |
| **q = 0（今天的引擎）** | 0.000% | **4.510pp** | **27.84pp** | 68.01pp |

【全表實測】

**讀法**：

1. **任何一個「基於實際現金分配、除以我們自己 spot」的算法都落在
   0.024–0.187pp 之內**，也就是 Heatmap 中位格差 0.15–1.15pp。相對於
   前置文件量到的門檻（1.5pp 的 q ⇒ 9.26pp 的格差），**這條路的誤差比
   門檻小一到兩個數量級**。
2. **複利慣例之爭是假議題**。三種慣例（`D/S`、`ln(1+D/S)`、`−ln(1−D/S)`）
   彼此最遠差 0.163pp（≈1.01pp 格差），而且**三種都比選錯欄位或選錯
   spot 基準便宜**。既然如此，**建議取最簡單、最不需要解釋的
   `q = D_ttm / S_snapshot`**——它同時也是 Merton 定義的一階近似
   （分配以連續速率 q 在價格 S 上累積，一年累積 q·S ≈ D）。
   若需求方想要一個「更講究」的版本，`ln(1 + D/S)` 在本樣本上恰好最接近，
   **但那是 n=1 的巧合，不足以當成理論優越性的證據**（§12 第 5 點）。
3. **30 天 SEC 殖利率是全表最差的非零選項**，且錯的方向是系統性偏高。

### 7.4 真正要付代價的三個決定

把上表拆成「單一決定的邊際成本」【實測】：

| 決定 | 邊際 |Δq| | ≈中位格差 |
|---|---|---|
| 用實際現金分配 vs 用 30 天 SEC 殖利率 | 0.582pp | **3.59pp** |
| 用我們的 spot vs 直接抄 vendor 的殖利率% | 0.142pp | 0.87pp |
| 複利慣例（最差配對） | 0.163pp | 1.01pp |
| （對照）完全沒有 q | 4.510pp | **27.84pp** |

**這張表就是本文對實作票的全部規範壓力所在**：把第一列做對，其餘兩列
做成什麼樣都在噪音裡。

### 7.5 為什麼必須快取「金額」而不是「殖利率百分比」

q 是比例，分母是價格。vendor 算好的殖利率百分比用的是**他們的價格、
他們的時點**。實測【實測】：

- 同一筆 $3.878 的年度分配，除以 2026-07-17 的 fixture spot 84.52 得 **4.608%**
  （以貼現後的除息日程計）／簡單比例 **4.588%**；
- 除以 2026-08-06 附近 aggregator 的價格基準 81.99 得 **4.758%**。
- **光是 spot 在三週內動了約 3%，就造成 0.151pp 的 q 差 ≈ 0.93pp 的
  Heatmap 中位格差**——這是一個純粹的口徑污染，不是市場資訊。

**設計結論【本文推導】**：管線的持久化單位是**「配息金額（美元）＋除息日」
的清單**；q 在每次分析時**用當次快照的 spot 現算**。這也讓快取的語意變乾淨：
金額是歷史事實（幾乎不變），比例是隨行情浮動的衍生量。

### 7.6 離散逐月配息用一個連續 q 近似，誤差在哪裡

兩個獨立的量測，結論方向相反地互相補強：

**(a) 除息日曆的細節不重要**【實測】。把除息日相位在月內從第 0.1 個月
挪到第 0.9 個月，q 只動 **0.007pp**（≈0.04pp 格差）。

**(b) 但配息「次數」很重要**【實測】。在 2.4164 年的到期前，假設有
27／28／29／30 次配息，逐次貼現後的等效連續 q 分別是
4.289%／4.448%／4.608%／4.767%——**每多算或少算一次配息就差 0.16pp
的 q（≈0.99pp 格差）**。

**(a)＋(b) 的合併含意【本文推導】**：**不要建配息時間表**。時間表的價值
（抓對相位）值 0.007pp，而它引進的風險（次數數錯、下一次除息日預測錯、
到期日剛好卡在除息日前後）值 0.16pp 起跳。**用「年度分配總額 ÷ spot」
這個沒有配息次數概念的比例，反而更穩健。** 這與 #110 §6 排除 Method C
（已知配息時間表）的判斷同向，本文從 q 的敏感度獨立得到同一結論。

### 7.7 連續殖利率這個抽象本身的殘留模型風險（誠實揭露）

連續 q 假設**分配與價格成比例**；真實的配息是**固定的美元金額**。
兩者在 `S = S_snapshot` 那一點依定義相等，但 Heatmap 的價格軸會走到
0.85×–1.30×。實測（K=85、σ=0.13、T=2.4164、比較「連續 q」與
「escrowed dividend：`S − PV(配息)` 代入無股利 BS」）【實測】：

| 價格列 | S | 連續 q | escrowed | 差（以 $5.90 單腿為分母） |
|---|---|---|---|---|
| 0.85× | 71.84 | 1.4899 | 1.2162 | **+4.64pp** |
| 0.94× | 79.45 | 3.5556 | 3.3501 | +3.48pp |
| 1.00×附近 | 83.25 | 5.0436 | 4.9794 | +1.09pp |
| 1.12× | 94.66 | 11.2600 | 12.0438 | −13.28pp |
| 1.30× | 109.88 | 22.5380 | 24.9920 | **−41.59pp** |

**這不是資料源的問題，是「用一個連續殖利率描述配息」這個抽象自帶的模型
風險**，而該抽象正是前置文件已核准方向（BS93＋q）的前提。列在這裡是為了
讓實作票的「模型限制」揭露文案寫得準確——**不能宣稱換上 q 之後 Heatmap
就準了**；能宣稱的是「carry 從完全沒有變成量級正確」。

**它也提供一個止損訊號**：既然 q 這個抽象自身在網格邊緣就有 4–40pp 的
模型誤差，**在資料源上追求優於 ~0.2pp 的 q 精度是買不到東西的**。

---

## 8. 資料缺漏時的 fallback（範圍 4）

**核心設計主張【本文推導】：必須區分「查到了、答案是沒有配息」與
「沒查到」。** 這兩件事在一個只給殖利率百分比的來源上長得一樣（都是
0 或 null），但在 `events.dividends` 這種給明細的來源上是可分的
（HTTP 200＋空事件 vs 抓取失敗）——**這是 §5.1 推薦金額型來源的第四個
理由**，也是整個 fallback 設計的地基。

分層如下，比照 #112／RC1（#87）已落地的
`rate_curve_used`／`rate_curve_date`／`rate_curve_stale` 三態透明化：

1. **抓取成功、有配息** → 依 §7.3 算 q，狀態 `fresh`，報告顯示
   「q = X.XX%（來源、資料截至 YYYY-MM-DD）」。
2. **抓取成功、明確無配息**（非配息標的，如前置文件 CASE 2 的 YETI）
   → **q = 0，狀態同樣是 `fresh`，不是 fallback**。這是正確答案：
   前置文件 §5.1 實測 BS93 在 q=0 時對 call **逐位元退化成 Merton 歐式**
   （差 0.00e+00），所以非配息標的**不需要任何新輸入**。
3. **抓取失敗、快取仍在窗內** → 用快取的金額清單、除以**本次**快照 spot
   重算 q，狀態 `stale`，報告標示快取日期（§9）。
4. **抓取失敗且無可用快取** → **退回現況**：q=0 ＋ 直接採用 vendor IV，
   即今天引擎的完整行為，並在候選上帶明確旗標讓 UI 說得出
   「這組估值未經 carry 校準」。
   **⚠ 絕對不要在這種情況下改用「q=0 ＋ 價格錨定」**——#110 §3.1 實測
   q=0 下 5 檔真實 TLT LEAPS 有 **3 檔的 IV 反解在數學上無解**
   （市場中價低於 q=0 模型的 σ→0 下限），那條路是**直接失敗**而不是降級。
   本文以細網格獨立覆核：在 q ≥ 3% 時 5/5 檔皆可解【實測】。
   （此層與前置文件 §10-4 第 3 點的建議一致，本文不另創。）

**異常分配的處理【本文推導】**：一次性的特別分配若被當成經常性配息、
攤到 2.4 年的視野上，是真實誤差——實測在 $3.878/年之上加一筆 $1.00 的
特別分配，q 從 4.608% 跳到 5.153%（**0.545pp ≈ 3.36pp 格差**）【實測】。
建議：
- **只計入經常性現金分配**；`events.capitalGains` 與明顯的一次性分配
  預設**排除**（Yahoo 把 capitalGains 放在獨立鍵，正好讓這件事零成本）。
- 若某月金額偏離同一標的過去 12 期中位數超過某個倍數，**寧可用中位數 ×
  期數**，也不要讓一筆離群值主導 q。**這是建議的處理方向，不是本文已
  驗證的規則**——門檻要多少、要不要做，屬實作票範圍。
- 個股（季配、金額不規則）與非配息標的都由同一條路徑自然涵蓋：
  q = 過去 12 個月實際現金分配總額 ÷ spot，**不需要知道配息頻率**。
  Finnhub／FMP 的 `freq`／`frequency` 欄位只用於顯示與健全性檢查，
  **不進公式**（進了就會重新引入 §7.6 的「次數」風險）。

---

## 9. 新鮮度／快取／陳舊規則（範圍 5）

**q 的變動速度遠慢於 r，這是本節所有建議的依據。** 實測 TLT 的
月配息從 $0.318 走到 $0.330（+3.8% m/m）【索引轉述的輸入，換算為實測】：

- **年化最近值**基準：一個月就動 **0.176pp** 的 q（≈1.08pp 格差）——
  對單月雜訊敏感。
- **TTM 基準**：同一個變動只替換掉 12 期中的 1 期，一個月動 **0.015pp**
  （≈**0.09pp** 格差）。

**→ 這是選 TTM 而不是「年化最近一次」當主口徑的第二個理由**（第一個
理由是 §7.3 的準度）：它對單月雜訊有 12 倍的抑制，代價是對趨勢有半年
的落後。落後的量化：分配以每月 1% 成長時，TTM 與年化最近值的差距是
0.25pp（≈1.52pp 格差）——**在利率快速轉折期，TTM 會系統性落後**，
這是知情取捨，應寫進模型限制揭露。

**陳舊預算**【實測】：1.00pp 的中位格差 ⟺ 0.162pp 的 q。以 TTM 基準：

| 分配月成長率 | 陳舊 3 個月 | 陳舊 12 個月 |
|---|---|---|
| 0.5%／月 | 0.067pp → 0.42pp 格差 | 0.275pp → 1.70pp |
| 1.0%／月 | 0.132pp → 0.81pp | 0.551pp → 3.40pp |
| 2.0%／月 | 0.252pp → 1.56pp | 1.106pp → 6.83pp |

**建議規則【本文推導】**：

1. **重抓頻率：每個市場日至多一次，per symbol。** 直接沿用
   `api_app/rate_cache.py` 既有的 `market_day` 判準（同一市場日成功抓過
   就共用，一輪刷新的 N 個劇本不重複打來源）。**不是因為 q 每天會變**
   ——上表說它一個月才動 0.015pp——而是因為**沿用既有機制的工程成本是零，
   而發明第二套節流邏輯的成本不是零**。
2. **陳舊備援窗：90 天。** 依上表，90 天在合理的分配成長率下最多值
   0.25pp 的 q（≈1.6pp 格差），仍遠優於退回 q=0（27.84pp）。
   **這是本文對 r 的既有 pattern 的一處刻意偏離**——`treasury.py` 與
   `rate_cache.py` 用的是 **7 天**。偏離理由：7 天對利率是合理的（利率
   日日在動），對配息不是（一個月才有一次事件），**7 天的窗會讓一個
   週末以外的短暫斷線就把使用者踢回 q=0 這個已知會產出 +81% 荒謬格值的
   狀態**。90 天約等於「一個季配週期」，對季配個股也剛好涵蓋一次事件。
3. **失敗短窗：沿用 5 分鐘**（`_FAILURE_MAX_AGE`），理由與 r 完全相同
   （同一輪刷新的 N 個劇本不該把同一個失敗中的來源打 N 次）。
4. **陳舊如何呈現**：比照 #112 已落地的
   `rate_used`／`rate_curve_date`／`rate_curve_stale` 三態，新增同形狀的
   `q_used`／`q_source`／`q_as_of`／`q_stale`，並在 `/api/health` 掛
   `last_success_at`（`RateCacheEntry` 既有欄位語意直接複製）。
   **UI 只格式化，不算任何東西**（專案紅線）。
5. **⚠ 不要快取算好的 q**。快取金額清單＋`as_of`；q 每次用當次 spot 現算
   （§7.5，否則白付 0.87pp 的格差）。這也讓陳舊語意變準確：
   「配息資料截至 X 日」是事實陳述，「q 是 4.6%」則會隨行情過期。

---

## 10. 與 Method E（#110）的關係

**本文不重新論證 Method E，只回答「兩者是什麼關係」。**

| | 外部配息資料（本文） | Method E（#110，chain-implied） |
|---|---|---|
| 輸入 | 一次外部 GET，per symbol | 引擎本來就抓的同一份快照 |
| 新增失敗模式 | **有**（新網域、新解析、新快取） | 無 |
| 失敗前提 | vendor 不可達 | **同到期日需 3–4 筆流動同側報價**（#110 §7 自述） |
| 對候選池稀薄的到期日 | **不受影響**（q 是標的的性質） | **會不穩定**——而這正是 FB3-02／#45 已經在畫面上警示的既有狀況 |
| 對非配息標的 | 空回應 ⇒ q=0（正確且明確） | 需要有報價才解得出來 |
| 本次量測結果 | **q = 4.486%–4.588%**（兩種推薦慣例） | **q\* = 4.510%** |

**兩者在這一份真實快照上差 0.024–0.078pp（≈0.15–0.48pp 格差）**【實測】。

**推論【本文推導】**：這不是「二選一」的題目。

- 兩條路**互為交叉驗證**：如果某次分析裡兩者差超過（比方說）0.5pp，
  那多半代表其中一邊出事了（vendor 給了錯的金額，或該到期日的報價被
  盤外／流動性污染），是一個**很便宜、很有訊息量的健全性檢查**。
- **外部 q 天然補上 Method E 的已知失敗模式**（候選池稀薄的到期日），
  而 Method E 天然補上外部 q 的已知失敗模式（vendor 不可達）。
- **主從順序是需求方的裁示，本文的資料兩種都支持**（§13-6 第 3 點）。
  若一定要本文表態：**外部 q 當 primary、Method E 當 guardrail** 略優，
  因為外部 q 是**每個標的一個確定的數字**，不隨候選池組成、不隨到期日
  變動，語意上更容易對使用者解釋（「TLT 過去一年配了 $3.88，除以現價
  就是 4.6%」），而 Method E 的數字需要解釋一整套跨履約價擬合。
  但這是**可解釋性**的偏好，不是精度的證據——精度上兩者在本樣本無法區分。

---

## 11. 施工形狀：沿用 r 的既有 pattern，偏離處逐條說明

本 repo 已經解過一次「抓外部公開資料、快取、陳舊、fallback、三態揭露」
這道題（`option_chaser/ratecurve.py` ＋ `option_chaser/data/treasury.py` ＋
`api_app/rate_cache.py`）。**預設應該照抄那個形狀。**

**照抄的部分**：

1. **純函式與 I/O 分離**：`option_chaser/dividends.py`（假名）只認文字與
   資料結構——解析 payload、加總 12 個月金額、除以 spot、換算 q——
   零 I/O、零 wall-clock，單元測試用固定 fixture 離線重跑。對照
   `ratecurve.py` 的 docstring 明講的同一條紀律。
2. **抓取隔在 `option_chaser/data/`**：一個 `dividends_yahoo.py`（假名），
   stdlib `urllib` ＋ `json`，`Request(url, headers={"User-Agent": …})`，
   逾時 15 秒，**任何連線／解析失敗一律收斂成 `FetchError`**——
   與 `cboe.py:100-105` 逐字同款（那裡的註解已經寫明為什麼要收斂）。
3. **多層備援鏈**：Yahoo → FMP（有金鑰時）→ Nasdaq，形狀比照
   `treasury.py::fetch_curve` 的 `attempts` tuple。
4. **注入式 loader**：比照 `service.RateCurveLoader`
   （`Callable[[date], tuple[RateCurve | None, str]]`）與
   `api_app/main.py` 的 `_rate_curve_loader()` late-binding——
   測試才能離線、`/api/health` 才誠實。
5. **三態呈現欄位**：`AnalysisParams` 加
   `q_used`／`q_source`／`q_as_of`／`q_stale`，語意逐條對應
   `rate_curve_used`／`rate_curve_date`／`rate_curve_stale`
   （`models.py:74-82` 的既有註解已經寫清楚這三欄「只給呈現層讀」）。

**刻意偏離的部分（三處，都要寫進實作票）**：

| 偏離 | r 的現況 | q 需要 | 理由 |
|---|---|---|---|
| **快取的鍵** | 單筆（`get_rate_cache()`／`save_rate_cache()`，無參數）——全站一條曲線 | **per symbol** | q 是標的的性質。`Storage` protocol 要加 `get_dividend_cache(symbol)`／`save_dividend_cache(symbol, entry)`，`memory.py`／`postgres.py` 各補一份。這是**本文建議裡唯一有 schema 影響的部分**。 |
| **陳舊窗** | 7 個日曆日 | **90 天** | §9 第 2 點已量化：7 天對配息過短，會讓短暫斷線把使用者踢回已知荒謬的 q=0。 |
| **快取的內容** | 曲線本身（已經是可直接用的數值） | **配息金額清單＋as_of**，不是算好的 q | §7.5 已量化：抄別人的比例＝混進別人的價格基準，值 0.87pp 的格差。 |

**不會變的（可縮小實作票驗收範圍）**：Spread 排名、`best_return`、
劇本庫卡片、V9 成本走勢圖皆不受 q 影響（前置文件 §8 已逐條追過，本文
不重做）。**⚠ 單腿 delta 分級位移**這個副作用也在前置文件 §8 記錄在案，
**是 q 一併帶來的**，實作票必須沿用該處的裁示要求。

---

## 12. 侷限、無法一手查證清單、與 reviewer 驗證清單

### 12.1 無法一手查證（沙箱出口限制；需在可連網環境／Vercel 上執行）

1. **本文沒有打到過任何一個候選 vendor 端點。** 所有回應形狀都是從公開
   客戶端原始碼或官方 OpenAPI 規格推得的**文件形狀**，
   **不是觀測到的 payload**。本文刻意不編造任何範例 JSON 內容。
2. **本專案 2026-08-05 那次 Vercel 探測，對 Yahoo 用的是哪一條 URL，
   repo 沒有記錄**（`interest-rate-source-selection.md` §6.4 只寫
   「Yahoo Finance ^IRX/^FVX/^TNX/^TYX（免鑰）✅ 通、200、拿到即時報價」）。
   因此「Yahoo 網域從 Vercel 可達」是**已證實**的，
   「`v8/finance/chart?events=div` 這條路徑匿名可達」是**未證實**的。
3. **`v8/finance/chart` 是否強制要求 crumb／cookie，未能驗證。**
   `yfinance` 對所有端點統一掛 crumb，這是套件的做法，不是端點的要求。
   **這個未知沒有便宜的逃生口**：正式環境的 lambda 依 `pyproject.toml`
   的 `[project] dependencies` 只裝 `fastapi`／`psycopg`／`tzdata`，
   **沒有 yfinance SDK 可以代勞 crumb 流程**（§5.1 第 3 點）。
   附帶記錄一個文件不同步：`docs/deploy-vercel.md` 的
   「為什麼 serverless 上沒有 yfinance」一節把機制講成
   「`requirements.txt` 刻意只裝 fastapi」，但 V1／#48 之後
   `requirements.txt` 自己的表頭已改寫成「**這份檔案不是 serverless
   實際安裝依賴的來源**，Vercel 認的是 pyproject」。**結論（沒有
   yfinance）兩邊一致，只有機制敘述過時**——不影響本文結論，
   但實作票若要改依賴，該看的是 `pyproject.toml`。
4. **iShares distributions AJAX 的欄位順序未知**（見 §4.1）；
   **美國站是否有 cookie／投資人身分閘門未能查證**。
5. **FMP 的 Terms of Service 原文未逐字核對**——「展示或再散布需簽
   Data Display and Licensing Agreement」是搜尋索引轉述。Tiingo 的
   「個人訂價非概括再散布授權」同樣是索引轉述。
6. **Alpha Vantage 是否有獨立的 `DIVIDENDS` function，未能確認。**
7. **TLT 的 CIK 底下是否有任何配息相關的 XBRL concept 被填，未查證。**
8. **TLT 的實際配息金額（$0.318／$0.330、TTM $3.878）全部是搜尋索引
   轉述，未經一手核對。** §7 之後的所有數字都建立在這組輸入上。
   §7.2 的自洽性覆核（三個獨立報導的殖利率彼此吻合到 0.03pp）**提高
   了可信度但不等於一手驗證**。

### 12.2 量化本身的侷限

9. **n = 1**：一個標的（TLT）、一份快照（2026-07-17）、五檔合約
   （排除離群後四檔）。「外部 q 與 chain-implied 差 0.024–0.078pp」是
   **這一個案例**的數字，**不是保證的誤差界**，也不足以證明某一種複利
   慣例在理論上更好（§7.3 讀法第 2 點已標明）。
10. **對照基準 q\* 本身沿用 #110 的 Method E 定義**，因此也沿用 #110 §3.3
    自陳的侷限（單一快照、樣本小、只用 call、殘留美式 call 提前履約誤差）。
    **兩條路互相印證到 0.08pp 這件事，不排除兩者共享同一個系統性偏差
    的可能**（例如都沒有處理美式提前履約）。
11. **1.5pp ⇒ 9.26pp 的換算是線性外推。** 前置文件只量了 ±1.5pp 兩點；
    本文在 0.02–0.7pp 的小區間用同一比例做量級判斷。**用來排序候選是
    穩健的，用來當精確預測不是。**
12. **§7.6 與 §7.7 的配息時程是等額逐月的理想化假設**（$3.878/12 每月），
    真實 TLT 的月配息金額有波動。相位／次數的敏感度結論對此不敏感
    （它們量的是結構，不是特定金額），但絕對數值會有小幅變動。
13. **§7.7 的 escrowed 對照是「同一個 σ」下的價格比較**，不是各自重新
    校準 IV 之後的比較。價格錨定會吸收掉一部分該差異（前置文件 §5.2
    已示範這個效應），所以表中的 4–40pp 是**未經價格錨定的上界**，
    不是最終使用者會看到的格差。

### 12.3 Reviewer 必須實測的清單（Vercel／可連網環境，依重要性排序）

沿用本 repo `interest-rate-source-selection.md` §6 的探測紀律：每個 URL
記下**狀態碼 ＋ `Content-Type` ＋ 前 500 bytes body**，平日與假日各一次，
**探測結果與本文排序矛盾時以探測結果為準**，不需另開研究票。

| # | 要測什麼 | 怎麼測 | PASS 判準 |
|---|---|---|---|
| 1 | **Yahoo chart events 匿名可用性**（本推薦的關鍵未知） | `GET https://query2.finance.yahoo.com/v8/finance/chart/TLT?range=2y&interval=1d&events=div,splits,capitalGains`，**不帶任何 cookie／crumb** | 200 ＋ JSON ＋ `chart.result[0].events.dividends` 非空且每筆含 `amount`／`date` |
| 2 | 同上，但對**非配息**標的（如 YETI） | 同上換 symbol | 200 ＋ `events` 缺 `dividends` 鍵或為空 —— 這是 §8 第 2 層「明確無配息」要能分辨的形狀 |
| 3 | Yahoo 給的金額是否**已做拆分調整**、以及是否含資本利得 | 拿 TLT 回應的逐筆金額與發行商官網 Distributions 分頁對帳 | 12 個月加總與官網一致到分 |
| 4 | **對帳 ground truth** | `https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf` 的 Distributions 分頁（人工） | 取得 2025-08 ~ 2026-08 逐月金額，覆核 §7.2 的 $3.878 |
| 5 | FMP（若決定申請金鑰） | `GET https://financialmodelingprep.com/stable/dividends?symbol=TLT&limit=20&apikey={KEY}` | 200 ＋ JSON ＋ 每筆含 `date`／`dividend`；比對 §5.2 列的鍵名是否與實際一致 |
| 6 | Nasdaq 免鑰 | `GET https://api.nasdaq.com/api/quote/TLT/dividends?assetclass=etf`，帶瀏覽器等級 `User-Agent`／`Accept` | 200 ＋ `data.dividends.rows` 非空 ＋ `data.annualizedDividend` 存在 |
| 7 | iShares AJAX（僅為釐清 §4.1 的欄位順序，不影響推薦） | `GET https://www.ishares.com/us/products/239454/{slug}/1467271812595.ajax?tab=distributions&fileType=json&subtab=table` | 200 ＋ `table.aaData`；記下每欄語意 |
| 8 | 盤外／假日行為 | 上述 1、5、6 在週末各再打一次 | 回舊資料（而非錯誤或歸零），比照 `cboe.py` 對盤外行為的既有驗證慣例 |

---

## 12.4 追記（#120，本輪僅完成沙箱可行部分）——探測腳本已就緒，實測結果待補

**沙箱出口封鎖已直接驗證**：`curl` 對三個候選網域皆收到 CONNECT 層級
拒絕（非目的站問題）：

```
$ curl -sS -m 10 -o /dev/null -w "yahoo: %{http_code}\n" \
    "https://query2.finance.yahoo.com/v8/finance/chart/TLT?..."
curl: (56) CONNECT tunnel failed, response 403
$ curl ... api.nasdaq.com ...         → 同樣 CONNECT 403
$ curl ... financialmodelingprep.com ...  → 同樣 CONNECT 403
```

代理層 `/__agentproxy/status` 的 `recentRelayFailures` 同步確認三筆
`connect_rejected`（`gateway answered 403 to CONNECT`），與
`interest-rate-source-selection.md` §0 記錄的同一種沙箱限制、同一種
誠實揭露（**沙箱連不到 ≠ Vercel／需求方本機連不到**，兩件事不可
混為一談）。

**本輪已完成（沙箱可行部分）**：

- 探測腳本 `scripts/probe_dividend_sources.py`（純 stdlib
  `urllib.request`，比照 `cboe.py`／`treasury.py` 既有慣例）已寫好、
  可直接在 Vercel／任何可連網環境執行：`python3
  scripts/probe_dividend_sources.py`
- 涵蓋 §12.3 第 1、2、6 項（Yahoo chart events 對配息／非配息標的各
  一次、Nasdaq 免鑰端點）；第 3／4／7 項需要人工比對發行商官網或
  非本腳本目的，第 5 項（FMP）需要金鑰，第 8 項（假日行為）需要
  跨週末重跑，皆不在本腳本範圍
- 已用**沙箱可達的網域**（`raw.githubusercontent.com`）與**刻意指向
  被擋網域**兩種情況分別跑過一次，確認腳本本身的成功／錯誤處理路徑
  正確（見下）——這**不是**對三個候選 vendor 的實測，只是證明腳本
  邏輯没問題，交給下一個能連網的環境跑就會拿到真實結果：

  | 情境 | 結果 |
  |---|---|
  | 指向可達網域（`raw.githubusercontent.com`） | `status=200`，正確讀到 `content_type`／`body_preview` |
  | 指向 Yahoo（沙箱內，預期被擋） | 正確捕捉為 `URLError: Tunnel connection failed: 403 Forbidden`，不拋例外、不誤判成功 |

**本輪未完成、且明確不得代為宣稱**：

- **第 12.3 項第 1 項（Yahoo chart events 匿名可用性，本推薦的關鍵
  未知）尚未有任何一次成功的真實呼叫**——依 #120／#111 兩張票共同的
  既有紀律，**不得**在此狀態下宣稱「Yahoo 已確認可用」或「primary
  source 已確定」。目前的 primary 選擇（§13-1）仍是**建立在文件與
  索引轉述上的建議**，不是實測結論。
- 若之後在可連網環境跑出與本文矛盾的結果（例如 Yahoo 端點需要
  crumb、實際回 401/403），依本文 §13-1 已載明的紀律：**FMP 直接
  升為 primary，不需另開研究票**。

---

## 13. 六問六答（決策用）

### 13-1. 推薦 q source（primary）

**Yahoo Finance chart 端點的 `events.dividends`**（免金鑰、單一 GET、
stdlib `urllib`）：

```
GET https://query2.finance.yahoo.com/v8/finance/chart/{SYMBOL}
        ?range=2y&interval=1d&events=div,splits,capitalGains
→ chart.result[0].events.dividends = { key: {"amount": float, "date": unix_ts}, … }
```

取**除息日落在過去 365 天內**的 `amount` 加總。

**一句話理由**：它是唯一同時滿足「本 repo 已接受其 ToS 風險等級 ＋ 網域
已在本專案 Vercel 正式環境實測連通 ＋ 回傳的是配息**金額**而不是別人算好的
殖利率」的候選；而 §7 證明「拿金額、除以我們自己的 spot」正是唯一能把
誤差壓到 0.08pp 以內的輸入形狀。

### 13-2. backup source

1. **Financial Modeling Prep** `stable/dividends`（需免費金鑰，250 次／日）
   ——正式文件化、**網域已在本專案 Vercel 實測回 401（可達、只缺金鑰）**。
   ⚠ 授權需裁示（§13-6）。
2. **Nasdaq** `api.nasdaq.com/api/quote/{sym}/dividends?assetclass=…`
   ——免金鑰，另附 `annualizedDividend`／`yield` 可當交叉驗證；
   但 Vercel 可達性未測、需瀏覽器等級標頭。

**若 §12.3 第 1 項實測失敗（chart 端點需要 crumb），FMP 直接升為 primary**
——沿用既有紀律，不需另開研究票。

### 13-3. 計算方式（原始欄位 → 引擎的 q）

```
D_ttm = Σ { amount  |  ex_date ∈ (today − 365 天, today] }      # 美元，只計經常性現金分配
q     = D_ttm / S_snapshot                                       # 連續複利年率
```

其中 `S_snapshot` ＝ **本次分析所用 `ChainSnapshot.spot`**，不是 vendor 的價格。

**四條配套規則**（每一條都有 §7 的量化撐腰）：

| 規則 | 為什麼 |
|---|---|
| 用**實際現金分配**，**不用 30 天 SEC 殖利率** | 差 0.582pp 的 q ＝ 3.59pp 的中位格差（§7.4） |
| 除以**我們自己的 spot**，不抄 vendor 的殖利率% | 差 0.142pp ＝ 0.87pp（§7.4、§7.5） |
| 用 **TTM（12 個月加總）**，不用「年化最近一次」 | 準度略優（§7.3），且對單月雜訊有 12 倍抑制（§9） |
| **不建配息時間表、公式裡不出現配息次數** | 相位只值 0.007pp，但次數數錯值 0.16pp（§7.6） |

**複利慣例**：`ln(1 + D/S)` 在本樣本上最接近（0.024pp），但三種慣例最遠
只差 0.163pp，**建議取最簡單的 `D/S`**；若需求方偏好 `ln(1+D/S)`，
差異在噪音內，兩者皆可（§7.3 讀法第 2 點）。

**非配息標的**：`D_ttm = 0 → q = 0`，且 BS93 對 call **逐位元退化成
Merton 歐式**（前置文件 §5.1 實測差 0.00e+00）——**不需要任何特例分支**。

### 13-4. fallback

四層，全部「降級 ＋ 誠實標示」，比照 #112／RC1 的三態透明化（§8 完整版）：

1. 抓到、有配息 → 正常路徑，狀態 `fresh`。
2. **抓到、確定無配息 → q = 0，狀態仍是 `fresh`**（正確答案，不是降級）。
3. 抓不到、快取在 **90 天**窗內 → 用快取的**金額清單**、以**本次** spot
   重算 q，狀態 `stale`，顯示資料截止日。
4. 抓不到且無快取 → **退回現況**（q=0 ＋ vendor IV ＝ 今天的完整行為）
   ＋ 明確旗標。**絕不可**在此層改用「q=0 ＋ 價格錨定」——#110 §3.1 實測
   該路徑對 3/5 檔真實 TLT LEAPS **數學上無解**。

**異常分配**：`capitalGains` 預設排除；單期金額嚴重偏離同標的中位數時
寧可用中位數 × 期數（門檻屬實作票範圍，本文未驗證具體數值）。

### 13-5. 所需欄位（管線必須取得的具體清單）

**必要（缺一不可）**：

| 欄位 | Yahoo | FMP | Nasdaq | 用途 |
|---|---|---|---|---|
| 配息**金額**（美元／股） | `events.dividends[].amount` | `dividend` | `rows[].amount`（帶 `$`，需剝） | q 的分子 |
| **除息日** | `events.dividends[].date`（unix ts） | `date` | `rows[].exOrEffDate`（`MM/DD/YYYY`） | 界定 12 個月視窗 |
| 現價 | — | — | — | **來自我們自己的 `ChainSnapshot.spot`**，不向 vendor 要 |

**選用（用於健全性檢查與呈現，不進公式）**：

| 欄位 | 用途 |
|---|---|
| `events.capitalGains[]`（Yahoo） | 明確排除資本利得分配；若要納入需為明示決定 |
| `events.splits[]`（Yahoo）／`adjDividend`（FMP）／`adjustedAmount`（Finnhub） | 判斷金額是否已做拆分調整（§12.3 第 3 項要實測確認） |
| `frequency`／`freq`（FMP／Finnhub）、`data.annualizedDividend`（Nasdaq） | 交叉驗證與 UI 顯示 |
| `currency` | 非美元計價標的的守門（超出目前範圍，但缺這欄會靜默算錯） |

**管線需自行產生並落盤**：`as_of`（資料截止日）、`source`（實際用了哪個
vendor，比照 `ChainSnapshot.source` 的既有誠實紀錄慣例）、
`q_used`／`q_stale`（呈現層三態）。

### 13-6. 是否足以直接進 `/to-spec`，或還有什麼未決

**資料源選型與換算口徑這一題已經收斂到可以決策**——候選、真實資料量化、
精度門檻對照、fallback、快取形狀、blast radius 都在上面，沒有需要再研究的
**技術**未知。

**但不建議直接進 `/to-spec`，有三個需求方裁示點 ＋ 一個必須先跑的實測**：

1. **【必須先跑，非裁示】§12.3 第 1 項**：Yahoo chart 端點在 Vercel 上
   不帶 crumb 能不能拿到 `events.dividends`。這是唯一會改變 primary 選擇的
   未知。成本＝一個臨時探測端點（本 repo 2026-08-05 已經做過一次同樣的事，
   流程與紀律見 `interest-rate-source-selection.md` §6）。
2. **【裁示】ToS 取捨**：走 Yahoo（灰色、免鑰、**不擴大**本 repo 既有曝險）
   還是走 FMP（正式 API、但「展示／再散布」可能需要簽 Data Display and
   Licensing Agreement，§5.2）。**本文無法替需求方判斷「把 q 當模型輸入
   並在畫面顯示一個數字」算不算再散布。**
3. **【裁示】要不要申請 FMP 免費金鑰**。本 repo 在 #74 時曾裁示「先不申請，
   可接受 fallback 鏈只有 Treasury→固定 4% 這一種深度」。q 的情況不同：
   **最終 fallback 是退回已知會印出 +81.9% 的行為**（前置文件 §4.1），
   所以備援深度的價值比利率那次高。建議重新裁示。
4. **【裁示】q 與 Method E 的主從順序**（§10）。本文的資料**兩種順序都
   支持**（兩者差 0.024–0.078pp）。本文略微傾向「外部 q 為 primary、
   Method E 為 guardrail」，理由是可解釋性與不受候選池稀薄影響，
   **不是精度證據**。

**另外三件不擋施工、但實作票應一併記錄的事**：

- **`Storage` protocol 要加 per-symbol 的配息快取**（§11 的唯一 schema 影響）。
- **陳舊窗從 7 天改成 90 天**是對既有 pattern 的刻意偏離，理由已量化（§9）。
- **模型限制揭露的措辭**：§7.7 證明「用連續 q 描述固定美元配息」這個抽象
  在 Heatmap 網格邊緣自帶模型誤差，**不能宣稱換上 q 之後 Heatmap 就準了**；
  可以宣稱的是「carry 從完全沒有變成量級正確」。

**§12 的外部查證缺口都不擋這個決定**——除了第 1 項（那是實測，不是查證）
之外，本文的結論由 §7 的真實資料實測獨立成立，外部來源只提供端點形狀與
授權條件的旁證。

---

## 14. 引用清單

### 本 repo 既有（直接引用，未重做）

- `docs/research/heatmap-valuation-method-selection.md`（commit `91e8fb9`）
  ——本文的前置文件：BS93＋q 的選型、q 是唯一新輸入、
  **q 差 1.5pp → Heatmap 中位格差 9.26pp** 的精度門檻、q=0 時 BS93 對 call
  逐位元退化成 Merton、blast radius
- `docs/research/valuation-carry-method-comparison.md`（#110）
  ——Method A–E 的定義、q=0 對 3/5 檔真實 TLT LEAPS 數學上不可行、
  Method E 的 q≈4.5% 與跨履約價離散度、排除 Method C／D 的理由
- `docs/research/interest-rate-source-selection.md`（#73／#74）
  ——**§6.4 的 Vercel 正式環境實測結果**（Yahoo 免鑰端點 200／
  FMP 401 可達／FRED 便利端點逾時）、八項評選維度、§6 的探測紀律
- `docs/research/risk-free-rate-for-bs.md`（T12-A）——r 的既有解法與三態 fallback
- `docs/research/option-chain-data-sources.md`——Cboe／Alpha Vantage／
  Polygon／Finnhub／Tiingo 的既有評估與 ToS 風險評級
- 程式碼（分析對象，**未修改**）：`option_chaser/ratecurve.py`、
  `option_chaser/data/treasury.py`、`option_chaser/data/cboe.py`、
  `option_chaser/data/yf.py`、`option_chaser/models.py`、
  `option_chaser/service.py`、`api_app/rate_cache.py`、
  `api_app/storage/__init__.py`、`api_app/main.py`、`scripts/research_valuation_methods.py`
- 真實資料：`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`

### 外部一手原始碼（本次經 `raw.githubusercontent.com` 逐字讀取）

- `ranaroussi/yfinance`：`yfinance/const.py`（`_QUERY1_URL_`／`_BASE_URL_`／
  `quote_summary_valid_modules`）、`yfinance/scrapers/quote.py`
  （`_QUOTE_SUMMARY_URL_`）、`yfinance/scrapers/history.py`
  （`params["events"] = "div,splits,capitalGains"`、`v8/finance/chart`）、
  `yfinance/utils.py::parse_actions`（`events.dividends`／`capitalGains`／
  `splits` 的逐鍵形狀）、`yfinance/data.py::_make_request`（crumb 機制）
- `OpenBB-finance/OpenBB`：
  `providers/cboe/openbb_cboe/models/options_chains.py`、
  `providers/cboe/openbb_cboe/models/equity_quote.py`、
  `providers/cboe/openbb_cboe/utils/helpers.py`（**Cboe 無配息欄位的證據**）；
  `providers/fmp/openbb_fmp/models/historical_dividends.py`（FMP 端點與鍵名）；
  `providers/nasdaq/openbb_nasdaq/models/historical_dividends.py`
  （Nasdaq 端點、`require_credentials = False`、鍵名）；
  `providers/yfinance/openbb_yfinance/models/etf_info.py`
  （`yield`／`trailingAnnualDividendRate`／`trailingAnnualDividendYield`）；
  `core/openbb_core/provider/standard_models/historical_dividends.py`
- `Finnhub-Stock-API/finnhub-go`：`api/openapi.yaml`
  （`/stock/dividend` 路徑與 `Dividends` schema 逐字，含 `freq` 的
  `0 Annually / 1 Monthly / 2 Quarterly / 3 Semi-annually / 4 Other`）
- `0rShemesh/ishares_etf_data`：`src/ishares_etf_data/core.py`
  （iShares distributions AJAX URL 與 `table.aaData` 形狀）
- `dibyajyotiron/etf-holdings-parser`：`README.md`
  （iShares 部分區域站台的 cookie／投資人身分閘門）
- `rtybase/tests`：`dividends-data/get_dividends.py`
  （Nasdaq 的 `data.annualizedDividend`／`data.yield`）
- 交叉印證 iShares AJAX 形狀者：`business-science/tidyquant`、
  `penny-vault/pvdata`、`leoncvlt/etf4u`、`erfanio/etf-holdings`、
  `vokuxyz/vestra`（後者另含 Vanguard 端點形狀）

### 搜尋索引轉述（非一手，逐條已於內文標明）

- `https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf`
  ——TLT 產品頁、Distributions、30-Day SEC Yield
- TLT 配息與殖利率數值（$0.318／$0.330、TTM 4.73%、遠期 4.83%、
  30 天 SEC 5.17%）——多個 aggregator（stockanalysis.com、dividend.com、
  nasdaq.com、dividenddata.com 等）的索引摘錄，**未經一手核對**
- `https://site.financialmodelingprep.com/…` ——FMP 免費層 250 次／日、
  Data Display and Licensing Agreement 的存在
- `https://www.tiingo.com/documentation/corporate-actions/dividends`、
  `https://www.tiingo.com/about/pricing` ——Tiingo 配息 API 與授權範圍
- `https://polygon.io/docs`（現 massive.com）——`/v3/reference/dividends`
  參數與免費層 5 次／分
- `https://www.alphavantage.co/documentation/` ——未查到獨立 `DIVIDENDS`
  function；配息經 `TIME_SERIES_DAILY_ADJUSTED` 提供
- `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`
  ——XBRL `frames`／`companyconcept` API 的定位

### 本次新產出（scratchpad，**未進 repo**）

四支量測腳本（Method E 細網格重解、候選公式比較、離散 vs 連續誤差、
陳舊預算），全部只 import `scripts/research_valuation_methods.py` 與
stdlib，任何人可依 §7.1 的參數重寫重跑。**依 guardrail，本票只留下這一份
研究文件，程式碼不進 repo。**
