# 美股選擇權鏈資料源調查：OPC 的資料從哪來＋yfinance 的替代方案

研究日期：2026-08-02。

取材限制聲明：本沙箱的出口 proxy 對多數金融網站的**直接抓取一律回 403**
（CONNECT policy denial），包括 `optionsprofitcalculator.com`、`cdn.cboe.com`、
`docs.tradier.com`、`alphavantage.co`、`polygon.io`、`marketdata.app`、
`finnhub.io`，Wayback Machine 亦不可用。因此本文的一手資料多數**經由搜尋引擎
索引的官方文件頁摘錄取得**（下文標為「搜尋索引轉述」），另有一部分靠
**GitHub 上可直接抓取的開源程式碼**（實際解析這些 API 的專案原始碼，屬
可逐字檢視的一手證據，標為「原始碼實證」）。無法以任一方式確認者，
一律列入 §5「未能查證的事項」。

## 1. 結論摘要

- **Part A**：OPC 自己的 FAQ 明講——報價「sourced from reputable third party
  websites」、且**負擔不起 premium data feed 訂閱**。即：OPC 不自建資料庫、
  也沒買商業餵送，靠免費第三方來源；**具體是哪家，全站未具名**（詳 §2）。
- **Part B**：本 repo「盤外 bid=0 → 候選池被濾光」問題（`option_chaser/filters.py:24`
  要求 `bid > 0`；盤前 LEAPS 全滅的實錄見
  `docs/superpowers/audits/2026-07-20-option-chaser-v4-audit.md:28`），
  **換資料源可以解掉大半**，因為 Cboe／Tradier 這類券商級快照在盤外
  仍保留收盤時的 bid/ask，不會歸零。推薦排序：

  1. **Cboe delayed quotes JSON**（免費、免金鑰、全鏈含 LEAPS、含 IV＋全套
     Greeks、盤外仍有上一盤 bid/ask）——首選，但屬**無官方文件的非正式端點**，
     無 SLA、服務條款灰色。
  2. **Tradier 免費 sandbox**（免費開發者帳號、REST＋token、15 分鐘延遲、
     ORATS Greeks/IV 每小時更新、60 req/min）——次選；sandbox 定位是開發測試，
     拿來當正式站資料源有 ToS 疑慮。
  3. **Alpha Vantage `HISTORICAL_OPTIONS`**（免費 25 req/day、EOD 全鏈含
     IV＋Greeks＋bid/ask/mark、正式文件、條款乾淨）——當「盤外基準快照」
     或備援極合適，但**只有 EOD**、免費額度極小。
  4. 願意付費時：**Polygon/Massive Options Starter US$29/月**（無限次呼叫、
     15 分鐘延遲全鏈快照含 Greeks）或 **MarketData.app 付費層**。
  - 不推薦：Finnhub（免費層能否用 option-chain 查不到定論，且有報價品質
    問題的公開 issue）、Nasdaq Data Link（選擇權資料為付費資料庫）、
    Polygon 免費層（EOD-only＋5 req/min，抓全鏈不可行）。

  另外：**yfinance 的 payload 本來就含 `lastPrice`，本 repo 也已經存下來了**
  （`option_chaser/data/yf.py:36` 存為 `last`），只是 filters／估值全部只認
  bid/ask。無論換不換源，**last/mark 後備仍建議保留**——即使是 Cboe，
  也存在「該合約整天無人報價」的深度 OTM LEAPS 角落案例。

## 2. Part A：OPC 的資料源

### 2.1 一手證據（OPC 自述）

出處均為 https://www.optionsprofitcalculator.com/faq.html （直接抓取被本沙箱
403 擋下；以下引文為**搜尋索引轉述**，兩次獨立查詢措辭一致）：

> "Stock and Options prices are sourced from reputable third party websites,
> and prices are delayed between 15-30 minutes."

> （關於為何不用更好的資料）the site "doesn't make enough money to cover
> a subscription to a premium data feed."

前次調查（`docs/research/opc-heatmap-comparison.md` §2，2026-08-01）亦自
同一 FAQ 確認過「15 分鐘延遲」與「15–30 分鐘延遲」兩種說法並存。

### 2.2 判讀

- 工作假設（OPC 無力自建普查式選擇權資料庫、必然消費第三方餵送）
  **獲得一手佐證**：OPC 明講價格來自第三方，且明講**沒有付費餵送**。
- 「reputable third party **websites**」的用詞（不是 feed/API/vendor）暗示
  其來源是免費公開網站級資料（與 Yahoo、Cboe 延遲報價頁同類），
  而非 Tradier/Intrinio/QuoteMedia 這類簽約 vendor——**此為推論**，
  OPC 全站（FAQ、首頁、blog）經多組關鍵字搜尋（"data provided by"、
  "quotes provided by"、"powered by"、各 vendor 名）**皆未找到任何具名
  attribution**。
- 15–30 分鐘延遲與 Cboe 免費延遲報價（15 分鐘）的口徑相容，但**無任何
  證據指認 OPC 用的是 Cboe**；Reddit／GitHub 亦搜不到逆向分析出其上游的
  公開紀錄。
- 未能查證：OPC 首頁 footer／terms 頁原文（403）、其前端 XHR 呼叫
  （需實機開發者工具，沙箱不可行）、archive.org 快照（被擋）。

## 3. Part B：候選資料源比較

### 3.1 總表

| 候選 | 費用 | 認證 | 盤外報價（關鍵） | 全鏈含 LEAPS | IV/Greeks | 速率限制 | ToS 風險（小型網站） | Python 難度 |
|---|---|---|---|---|---|---|---|---|
| Cboe delayed JSON | 免費 | 無 | 保留上一盤 bid/ask＋last（推定，見 §3.2） | ✅ 全部掛牌到期日 | ✅ IV＋δγθv ρ | 未公布（社群自律 5–10s/檔） | 非正式端點、站方條款限制自動抓取（轉述） | 極低（單一 GET） |
| Tradier sandbox | 免費 | token | 券商級快照含 bid/ask 時戳（推定） | ✅（per-expiry 呼叫） | ✅ ORATS，每小時更新 | 60 req/min（sandbox 市場資料） | sandbox 定位為開發測試 | 低（REST） |
| Alpha Vantage HISTORICAL_OPTIONS | 免費 | API key | ✅ EOD 快照天生適合盤外 | ✅ 指定日全鏈 | ✅ 恆附 | 25 req/day（免費） | 乾淨（正式 API） | 低 |
| Polygon/Massive 免費層 | 免費 | API key | EOD-only | 理論可、實務不可（5 req/min） | 免費層無快照 Greeks | 5 req/min | 乾淨 | 低 |
| Polygon/Massive Starter | US$29/月 | API key | 15 分鐘延遲快照（盤外＝收盤值） | ✅ 快照端點 | ✅ | 無限次 | 乾淨 | 低 |
| MarketData.app 免費層 | 免費 | token | 快取餵送概念、但額度算法致命（§3.6） | ✅ | ✅ | 100 credits/day；**全鏈即時＝1 credit/合約** | 乾淨 | 低 |
| Finnhub | 免費層存疑 | API key | 未查明 | 未查明 | 有欄位 | 60 req/min | 免費層限非商用 | 低 |
| Nasdaq Data Link | 付費 | API key | — | — | — | — | — | — |
| yfinance（現狀） | 免費 | 無 | ❌ bid/ask 歸零，僅剩 lastPrice | ✅ | 只有 IV | 無正式（易被限流） | 非正式（Yahoo ToS 灰色） | 已在用 |

### 3.2 Cboe delayed quotes JSON（首選）

- **端點**：`https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json`
  （指數與部分特殊代號要加底線前綴 `_SPX`；TLT 等一般股票/ETF 直接用代號）。
  本沙箱直接抓取被 proxy 擋（curl 與 WebFetch 皆 403），**未能檢視即時回應**；
  以下欄位清單為**原始碼實證**——自 OpenBB 官方 Cboe provider 原始碼逐字讀出
  （https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py ），
  並經另三個獨立開源專案交叉印證（carlosjimenezdiaz/GEX 的 R 抓取腳本、
  AdRedrock/OptionsAnalyzer、GitHub code search 其餘 32 個命中）。
- **結構與欄位**：`data.options[]` 每筆含
  `option`（OCC 代號，形如 `TLT260618C00120000`，含到期 yymmdd／C-P／
  strike×1000）、`bid`、`ask`、`bid_size`、`ask_size`、`iv`、
  `open_interest`、`volume`、`delta`、`gamma`、`theta`、`vega`、`rho`、
  `theo`（理論價）、`last_trade_price`、`last_trade_time`、`prev_day_close`、
  `percent_change`；標的層另有 `current_price`、`close`、`prev_day_close`、
  `iv30`、`last_trade_time`、`security_type`。
- **覆蓋**：單一 GET 回傳**該標的全部掛牌序列**（所有到期日含 LEAPS、
  所有履約價）；使用者實測量級為每檔 3,000–5,000 筆合約（原始碼實證，
  出處為上列開源專案內的註解）。
- **延遲**：15 分鐘（此端點即 cboe.com「Delayed Quotes」頁
  https://www.cboe.com/delayed_quotes/tlt/quote_table 的後端資料）。
- **盤外行為**：**未能在本沙箱直接驗證**（端點被擋）。推定為「持續供應
  上一盤最後一次延遲快照」——依據：它是 Cboe 延遲報價網頁的資料源，
  該網頁收盤後照常顯示完整報價表；且回應本身帶 `last_trade_time`、
  `prev_day_close` 等收盤參照欄位。與 Yahoo 的差異關鍵在：Yahoo 盤外把
  bid/ask **改寫成 0**，而 Cboe 快照是凍結最後值。此推定建議在採用前
  於盤外實測一次（見 §4.4）。
- **費用／認證／限制**：免金鑰、免註冊。**無官方 API 文件、無公布的
  速率限制與使用條款**；搜尋索引轉述稱 cboe.com 網站條款限制自動化
  抓取（未能取得條款原文）。社群慣例是多檔輪抓時每檔間隔 5–10 秒
  （GEX 腳本原始碼）。對「部署在 Vercel 的小型網站」而言風險有二：
  端點隨時可能改版或封鎖雲端出口 IP；商用性質的持續抓取在條款上站不住。
- **Python**：一個 `requests.get` 加 OCC 代號解析即可，難度最低。

### 3.3 Tradier 免費 sandbox（次選）

- **取得**：developer.tradier.com 免費註冊開發者帳號即發 sandbox token，
  **不需券商帳戶**（https://developer.tradier.com/user/sign_up ；
  Zorro 專案手冊亦稱 "a free sandbox account can be opened … for receiving
  delayed market data"，https://zorro-project.com/manual/en/tradier.htm ，
  搜尋索引轉述）。
- **端點**：`GET /v1/markets/options/chains?symbol=TLT&expiration=…&greeks=true`
  （文件 https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains ，
  本沙箱被擋，內容為搜尋索引轉述）。到期日清單另呼叫 expirations 端點，
  **每個到期日一次呼叫**——TLT 約 20 個到期日＝20 次，60 req/min 內可完成。
- **欄位**（原始碼實證，社群整理的 OpenAPI spec
  https://github.com/sargun/tradier/blob/master/specs/tradier.yaml ）：
  `last`、`close`、`prevclose`、`bid`、`ask`、`bidsize`/`asksize`、
  `bid_date`/`ask_date`（**報價時戳**，可據以判斷盤外新鮮度）、
  `greeks{delta, gamma, theta, …, bid_iv, mid_iv, ask_iv, smv_vol}`。
- **Greeks/IV**：由 ORATS 提供（https://production.tradier.com/platforms/orats ），
  文件稱**每小時更新一次**（搜尋索引轉述；注意有第三方論壇把這句誤讀成
  「報價每小時一次」——報價本身是 15 分鐘延遲，慢的是 Greeks）。
- **延遲／限制**：sandbox 一律 15 分鐘延遲、無法升級；市場資料端點
  60 req/min（https://docs.tradier.com/docs/rate-limiting ，搜尋索引轉述）。
- **盤外行為**：未見文件明文。券商級報價快照含 bid/ask 時戳，推定盤外
  保留收盤 bid/ask（待實測）。
- **ToS 風險**：sandbox 的定位是「開發與測試」；把它常駐當一個對外部署
  網站的正式資料源，屬於明顯的灰色使用。個人專案風險低，但應知情。

### 3.4 Alpha Vantage `HISTORICAL_OPTIONS`（EOD 基準／備援）

- **端點**：`function=HISTORICAL_OPTIONS&symbol=TLT[&date=YYYY-MM-DD]`
  （文件 https://www.alphavantage.co/documentation/ ，被擋，搜尋索引轉述）。
  回傳**指定日（預設前一交易日）該標的全鏈**：所有到期日、所有履約價，
  依到期日→履約價排序；**IV 與全套 Greeks 恆附**，另含 last、mark、
  bid、ask、volume、OI；歷史回溯 15 年（2008 起）。
- **免費層**：25 requests/day（https://www.macroption.com/alpha-vantage-api-limits/ ，
  二手）。一檔一天一次全鏈快照的用法剛好可行。`REALTIME_OPTIONS`
  則為 premium（US$49.99/月起）。⚠ 有二手來源
  （tradingtoolshub.com）稱 HISTORICAL_OPTIONS 也要 premium，與多數
  來源（含逐欄位描述其免費回應的 https://oyamori.com/learning/options-data-api-alphavantage-alpaca/ ）
  矛盾——**免費層是否含此端點，最終要以實際金鑰打一次為準**。
- **定位**：它就是「收盤快照」，天生沒有盤外歸零問題；缺點是盤中不更新、
  免費額度小。適合當**盤外基準／yfinance 壞掉時的備援**，不適合當唯一源。
- 已知怪癖（二手）：DTE ≤ 3 天的合約 IV 欄不可靠。

### 3.5 Polygon.io（已更名 Massive）

- 免費層 **Options Basic**：5 API calls/min、**EOD-only**
  （https://massive.com/pricing ，被擋，搜尋索引轉述）。抓全鏈需逐合約或
  逐 aggregate 呼叫，5 req/min 下不可行——**免費層不符本案需求**。
- **Options Starter US$29/月**：無限次呼叫、15 分鐘延遲、全鏈 snapshot
  端點（`/v3/snapshot/options/{underlying}`）含即時 Greeks/IV、OI、
  2 年歷史（https://massive.com/docs/rest/options/overview ，搜尋索引轉述）。
  若願意付費，這是文件最完整、條款最乾淨的選項。

### 3.6 MarketData.app

- 免費層 Free Forever：**100 credits/day**
  （https://www.marketdata.app/docs/account/plan-limits/ ，搜尋索引轉述）。
- 致命點：**option chain 端點即時查詢是「回傳幾筆合約就扣幾個 credit」**
  ——官方文件自己舉例 SPX 全鏈 22,718 筆＝22,718 credits
  （https://www.marketdata.app/docs/api/options/chain/ ，搜尋索引轉述）。
  cached mode（整鏈 1 credit）**免費與試用層不能用**。TLT 全鏈數千筆，
  免費層一天連一次都抓不完——**免費層不符本案需求**；付費層（cached
  mode）則相當合適，且其「快取餵送」本來就是盤外供最後已知報價的設計。
- 欄位面（bid/ask/mid/last、全套 Greeks、IV、OI、updated 時戳）完整。

### 3.7 Finnhub／Nasdaq Data Link（皆不推薦）

- **Finnhub** `GET /stock/option-chain`：端點存在
  （https://finnhub.io/docs/api/option-chain ，被擋）；**免費層能否呼叫，
  正反查證皆未得**。且有公開品質疑慮：官方 repo issue「/stock/option-chain
  Endpoint Issue」（https://github.com/finnhubio/Finnhub-API/issues/545 ）、
  finnhub-python issue #65「Option chain incorrect numbers for lastPrice,
  bid and ask」（https://github.com/Finnhub-Stock-API/finnhub-python/issues/65 ）。
  免費層條款限個人非商用。不值得押注。
- **Nasdaq Data Link**：選擇權（如 NGVUS「Greeks and Implied Volatility」
  https://data.nasdaq.com/databases/NGVUS ）為付費訂閱資料庫，無真正免費
  的全鏈來源。

### 3.8 yfinance 本身：我們丟掉了什麼

- Yahoo 選擇權 payload 每筆合約含 `lastPrice`、`bid`、`ask`、`volume`、
  `openInterest`、`impliedVolatility` 等欄；**盤外 Yahoo 把 bid/ask 歸零，
  但 `lastPrice` 與 `impliedVolatility` 留著**（本 repo 盤前實錄：
  `docs/superpowers/audits/2026-07-20-option-chaser-v4-audit.md:28`——
  盤前 08:19 ET LEAPS 全滅、對照週日快照 182/186 檔有報價）。
- 本 repo **已經抓下 `lastPrice`**（`option_chaser/data/yf.py:36` 存為
  `OptionContract.last`），但下游完全沒用它：
  - 過濾：`filters.py:24` 要求 `bid is not None and ask is not None and
    bid > 0`——盤外整鏈被這行濾光；
  - 成本：`valuation.py:244-245`（net_mid／net_worst）、`scenarios.py:34,79`
    全用 bid/ask。
- 即：**「用 last 當盤外後備」不需要新資料，只需要改口徑**——但 last 可能
  極陳舊（幾天前的成交），拿它算 net_mid 會低估摩擦，只宜當「有標記的
  降級模式」而非無聲後備。

## 4. 對 Option Chaser 的落地建議

### 4.1 現行 Streamlit 版（改動最小）

新增 **Cboe delayed JSON adapter** 作為第二個 `fetch_chain` 實作
（`option_chaser/data/` 下新模組，回傳同一 `ChainSnapshot`，`source="cboe"`）：
欄位對映直接（bid/ask/iv/OI/volume 一一對應，另外免費多得全套 Greeks），
OCC 代號解析到期日與履約價即可。yfinance 降為備援。單一標的單一 GET，
無金鑰，部署零設定。

### 4.2 Vercel serverless 重寫版

同樣以 Cboe 為主源——serverless function 內一個 fetch 即可，且回應可以
edge cache（15 分鐘延遲資料本來就不需要秒級新鮮）。兩個注意點：
1. Cboe 可能封鎖資料中心出口 IP（本沙箱的 403 是自家 proxy 所為，
   不能當證據，但 Vercel IP 段被擋的風險真實存在）——上線前先在
   Vercel 上打一次驗證；
2. 設計上把資料源做成可替換的 adapter＋降級鏈：
   **Cboe → yfinance（含 last 後備）→ Alpha Vantage EOD**，
   任一層失敗自動落到下一層並在快照標記 `source`。

### 4.3 「bid=0 餓死候選池」能否純靠換源解決？

**大部分能，但不全能。**盤外歸零是 Yahoo 的行為，不是市場的行為；
Cboe／Tradier 快照凍結收盤 bid/ask，換源後 `filters.py` 現行邏輯在盤外
就能吃到完整候選池。但兩個殘餘案例仍需 last/mark 後備：
1. **盤中開盤初期**造市商報價未鋪滿（audit 實錄的 09:35 ET 案例）——
   這在任何 15 分鐘延遲源上同樣會發生；
2. 真正無人報價的深度 OTM／極遠月合約，任何源的 bid 都可能是 0。
因此建議保留一個**顯式標記的 last-price 降級口徑**（例如快照層記
`quote_source: "bid_ask" | "last_fallback"`，排名時懲罰後者），
而不是把 last 無聲混進 mid。

### 4.4 採用前的驗證清單（沙箱做不到、需在真環境跑）

1. 盤外（含週末）打 `cdn.cboe.com/api/global/delayed_quotes/options/TLT.json`，
   確認 bid/ask 非零且等於收盤快照；
2. 從 Vercel serverless 打同一端點，確認未被 IP 封鎖；
3. 用免費金鑰各打一次 Alpha Vantage `HISTORICAL_OPTIONS` 與 Tradier
   sandbox chains，確認免費層實際可用（§3.4 的矛盾、§3.3 的 sandbox
   權限以實測為準）。

## 5. 未能查證的事項

- OPC 具體上游 vendor／網站（全站無具名；前端 XHR 與 terms 頁無法取得）。
- Cboe：端點的即時回應原文（沙箱 403）、盤外/週末實際行為、官方使用
  條款與速率限制原文（是否明文禁止此類用法）。
- Tradier：sandbox 盤外 bid/ask 是否保留收盤值的明文；sandbox 用於
  正式部署的條款邊界原文。
- Alpha Vantage：HISTORICAL_OPTIONS 是否確在免費層（二手來源互相矛盾，
  §3.4）。
- Finnhub：免費層是否含 `/stock/option-chain`。
- MarketData.app：免費層可否用 `date` 參數以「1 credit/1000 筆」抓
  前一日全鏈（文件說免費層不含 real-time 與 current-day，但歷史口徑
  是否覆蓋「昨日」未見明文）。
- 所有被 403 擋下的官方文件頁：內容以搜尋索引轉述為準，未逐字核對原文。

## 6. 引用清單

一手（原始碼實證，本沙箱可直接抓取）：
- https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/openbb_platform/providers/cboe/openbb_cboe/models/options_chains.py —— Cboe 端點 URL、欄位對映、OCC 解析、標的層欄位
- https://github.com/carlosjimenezdiaz/GEX/blob/main/Gamma%20Exposure%20CBOE%20Data%20(Scraping).R —— Cboe 端點用法、bid/ask 欄、多檔輪抓間隔慣例
- https://github.com/sargun/tradier/blob/master/specs/tradier.yaml —— Tradier 報價欄位（last/close/prevclose/bid/ask/bid_date/greeks/mid_iv/smv_vol）
- GitHub code search（"delayed_quotes/options"，32 個命中）—— delta/gamma/theta/vega/rho 欄與每檔 3,000–5,000 筆量級之交叉印證

一手官方文件（被沙箱 403 擋下，內容為搜尋索引轉述）：
- https://www.optionsprofitcalculator.com/faq.html —— 第三方來源、15–30 分鐘延遲、無 premium feed
- https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains 、 https://docs.tradier.com/docs/rate-limiting 、 https://developer.tradier.com/user/sign_up
- https://production.tradier.com/platforms/orats —— ORATS Greeks/IV
- https://www.alphavantage.co/documentation/ —— HISTORICAL_OPTIONS／REALTIME_OPTIONS
- https://massive.com/pricing 、 https://massive.com/docs/rest/options/overview —— Polygon/Massive 各層
- https://www.marketdata.app/docs/api/options/chain/ 、 https://www.marketdata.app/docs/account/plan-limits/ —— credit 計價與層級
- https://finnhub.io/docs/api/option-chain 、 https://finnhub.io/pricing

二手：
- https://zorro-project.com/manual/en/tradier.htm —— sandbox 免費、延遲資料
- https://www.macroption.com/alpha-vantage-api-limits/ —— 25 req/day
- https://oyamori.com/learning/options-data-api-alphavantage-alpaca/ —— HISTORICAL_OPTIONS 回應細節
- https://github.com/finnhubio/Finnhub-API/issues/545 、 https://github.com/Finnhub-Stock-API/finnhub-python/issues/65 —— Finnhub 品質疑慮
- https://data.nasdaq.com/databases/NGVUS —— Nasdaq 選擇權資料為付費

本 repo：
- `option_chaser/data/yf.py:34-39`（bid/ask/last/IV 對映）、`option_chaser/filters.py:24`（bid>0 過濾）、`option_chaser/valuation.py:244-245`、`option_chaser/scenarios.py:34,79`
- `docs/superpowers/audits/2026-07-20-option-chaser-v4-audit.md:28`（盤前 LEAPS 全滅實錄）
- `docs/research/opc-heatmap-comparison.md`（OPC FAQ 前次查證）
