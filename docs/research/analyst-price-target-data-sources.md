# 個別分析師目標價（含歷史）資料源比較：誰能餵 Consensus Gate

研究日期：2026-11-18（所有價格、方案、條款均為當日查得；價格會變，
採用前請重查）。對應功能：`docs/spec/options-scanner/01-design.md` 的
Consensus Gate（Target Dispersion ＋ Dispersion Percentile）。用語依
`CONTEXT.md`：Consensus Target、Target Dispersion（D = stdev / mean）、
Dispersion Percentile、Consensus Gate。

**查證標記（全文每一項主張都帶其中一個）**

- 【原件】＝當日直接抓到 vendor 自己的文件／定價頁／條款原文並核對過
  （verified-from-primary-source）。
- 【轉述】＝只有搜尋引擎索引、第三方文章或 SDK 鏡像的轉述（secondary）。
- 【未查證】＝沒有找到可核對的來源，或來源需要登入／報價
  （unverified）。

**取材限制聲明**：本次沙箱對多數 vendor 文件網域**連得上**（與
`historical-options-iv-data-sources.md` 那一輪全面 `EGRESS_BLOCKED` 不同），
但下列頁面抓不到，相關主張一律降為【轉述】或【未查證】：

- `www.benzinga.com`（API 行銷頁／licensing／pricing）→ HTTP 403；
  `docs.benzinga.com` 可讀。
- `www.tipranks.com`、`www.marketbeat.com` → HTTP 403（bot 防護）。
- `finnhub.io/pricing`、`data.nasdaq.com`、`developer.factset.com`、
  `docs.tipranks.com` 內頁、`www.tiingo.com/documentation` → 純前端渲染，
  抓回來是空殼。
- FMP 的 TipRanks add-on 價格、Massive／Benzinga 的 Business 價格 →
  需登入或找業務報價。

本研究**沒有**註冊任何帳號、沒有使用任何 API key、沒有購買任何東西；
唯一打過的資料端點是 Alpha Vantage 官方公開的 `apikey=demo` 範例。

## 1. 結論摘要（先行）

- **「個別目標價＋歷史」在零售價位只有兩條現成的路**，其餘不是只有
  共識值、就是機構級合約：
  1. **Benzinga Analyst Ratings（經 Massive，原 Polygon.io 轉售）**：
     US$99/月、歷史回溯到 **2011-12-08**、每筆含 analyst／firm（各有
     穩定 ID）、日期、目標價、前一次目標價、split-adjusted 目標價、
     評等動作（含終止覆蓋）。【原件】**但這個價位標明「Individual use
     only」**；Business 版要找業務報價。【原件】
  2. **FMP 的 TipRanks add-on（2026-07-29 公告）**：有一支現成的
     **point-in-time 端點** `tipranks-pit-symbol?symbol=&date=`，回傳
     「該日每位分析師最後一筆有效 call」（一位分析師一列）——形狀幾乎
     就是 Consensus Gate 要的輸入。【原件】**但歷史只給 3 年**，更早要
     Enterprise；add-on 價格未公開。【原件／未查證】
- **「現成的歷史共識序列含標準差」只有 Zacks 系與機構級有**：Zacks
  自家的 Price Targets 歷史檔有 Mean、Standard Dev、# Analysts、High、
  Low，**1997-12 起**；【原件】Intrinio 轉售的 Zacks 端點有
  `standard_deviation` 與 `total` 欄位，但**只開放 Enterprise 方案
  （US$1,250/月起）**。【原件】FactSet、I/B/E/S Summary 也有，屬機構合約。
- **Finnhub、Twelve Data、EODHD、Alpha Vantage、FMP 原生端點、
  yfinance 都沒有標準差**；前四者也沒有（或沒有夠深的）個別目標價
  歷史。Finnhub 有「歷史共識」但只有 mean／median／high／low／人數。
  【原件】
- **沒有任何一家的自助方案允許把資料或衍生值顯示給公開網站的使用者。**
  FMP 條款明文禁止未簽約的 display，且涵蓋「derived from the Services」
  的資訊；Finnhub 明文禁止分享「derived results」；Massive US$99 方案
  限個人非商業；Twelve Data、Intrinio 個人方案禁止 redistribution／
  display。【原件】**production 一定要談授權**，這是成本的主要未知數。
- **使用者已知事項的兩處修正**（詳 §4.1、§4.2）：
  - FMP 個別目標價端點（`/api/v4/price-target`）現在是 **legacy**：
    2025-08-27 起 legacy 文件只對符合資格的舊帳號開放；公開的 stable
    文件已**沒有**個別目標價端點，取而代之的是 TipRanks add-on。
    「歷史自 2021 起」這句話今天無法從公開文件核對。【原件／未查證】
  - I/B/E/S 的歷史改寫**今年還在發生**：WRDS 公告 2026-06 更新起
    Jefferies 與 Morningstar 的 Detail（含 Target Price）被整批移除，
    並連帶重排遮罩後的 analyst／broker ID。【原件】
- 本文**不做**最終選型（Owner 決定），只整理事實、算帳與風險。

## 2. 需求界定：Consensus Gate 需要什麼資料

`01-design.md` §2 的兩道關卡需要：

1. **今天的個別目標價**：每位分析師（或每家券商）一筆「目前有效」的
   目標價，帶發布／更新日與身分——用來算 `TP_mean`、`σ_TP`、
   `D = σ_TP / TP_mean`，並做有效期（12 個月）與新鮮度檢查。
2. **歷史分歧度序列 `D_t`**：兩種取得方式擇一——
   - (a) **個別目標價事件史**：自己在每個取樣日重建「當時有效」的
     那一組目標價，再算 `D_t`；或
   - (b) **vendor 現成的歷史共識序列**，至少含 mean、**stdev**、人數。
3. 更新頻率：每日一次即可。Universe：約 500 檔美股大型股。
4. 授權：衍生值（Consensus Target、D、pass/fail）要能顯示給公開 web
   app 的匿名使用者。

逐源檢核的六件事：個別目標價與欄位／有效或撤回標記、歷史深度與現成
stdev 序列、S&P 500 覆蓋與 ETF、最低可用價位與每日 500 檔的呼叫數、
對外顯示授權、歷史是 point-in-time 還是會被改寫。

**關於 ETF（通則）**：賣方分析師不對 ETF 發目標價；本文查到的所有
來源的分析師目標價都是個股層級，沒有任何一家文件宣稱提供 ETF 的
分析師目標價。【未查證——屬通則性判斷，未逐家確認】Universe 應限定
個股。

## 3. 總覽比較表

（「stdev 序列」＝是否有現成歷史共識序列含標準差；「顯示」＝自助方案
是否允許對公開使用者顯示資料或衍生值；價格為 2026-11-18 查得的月付價）

| 來源 | 個別目標價 | 個別目標價歷史 | stdev 序列 | 最低可用價位 | 500 檔每日更新 | 顯示授權（自助方案） | 對本功能 |
|---|---|---|---|---|---|---|---|
| Benzinga（經 Massive） | ✅ analyst＋firm＋ID、日期、PT、前次 PT、adjusted PT、動作【原件】 | **2011-12-08 起**【原件】 | ❌ 共識端點無 stdev、無日期參數【原件】 | **US$99/月**（Individual use only）；Business 報價【原件】 | 1 次呼叫（`last_updated.gte`，上限 50,000 筆）【原件】 | ❌ 個人非商業；Business 另談【原件】 | **能**（需自建 `D_t`） |
| Benzinga（直購） | ✅ 同上＋ISIN／CUSIP【原件】 | 2012–2013 起【轉述】 | ❌【原件】 | 報價【未查證】 | 10 次（每次上限 50 tickers）或 1 次（`updated` 增量）【原件】 | 依合約【未查證】 | **能** |
| FMP ＋ TipRanks add-on | ✅ analyst、firm、expertUID、recommendation、action、PT、來源文章【原件】 | **3 年**；更早需 Enterprise【原件】 | ❌ 無 stdev 欄位；但有現成 PIT 快照端點【原件】 | 核心方案＋ add-on；**最低核心級別與 add-on 價格皆未公開**【未查證】 | 1–2 次（`tipranks-search` 不帶 symbol，上限 5,000 筆）或 500 次 PIT【原件】 | ❌ 條款明文禁止 display，含衍生資訊；Enterprise 另談【原件】 | **能**（歷史短） |
| FMP 原生（stable） | ❌ stable 文件已無個別端點【原件】 | legacy `/api/v4/price-target`，僅舊帳號【原件】 | ❌ 只有 summary（月／季／年平均＋人數）與 consensus（high／low／median／consensus）【原件】 | Starter US$29/月（美股）【原件】 | bulk 1 次（限 Ultimate US$139/月）【原件】 | ❌ 同上【原件】 | 不能（無 stdev、無個別） |
| Finnhub | ❌ 只有共識【原件】 | — | ⚠ 有「歷史共識」但只有 mean／median／high／low／人數，**無 stdev**【原件】 | Premium，價格【未查證】 | 500 次【原件】 | ❌ 禁止分享資料與 derived results；所有方案限個人【原件】 | 不能（僅能做 range 代理） |
| Twelve Data | ✅ firm、analyst_name、日期、PT、前次 PT、動作【原件】 | 文件未說明；預設回 30 筆【原件】 | ❌【原件】 | **Ultra US$329/月**（個人）【原件】 | 500 次 × 200 credits ＝ 100,000 credits（約 39 分鐘）【原件】 | ❌ 需 Redistribution add-on；Derived Data 另有條款【原件】 | 部分（歷史深度不明、貴） |
| Zacks（直購／WRDS） | ❌ 目標價是共識檔（另有逐券商 recommendation）【原件】 | — | ✅ **Mean、Standard Dev、# Analysts、High、Low，1997-12 起**【原件】 | 報價【未查證】 | 檔案更新【未查證】 | 依合約【未查證】 | **能**（走 (b) 路線） |
| Zacks（經 Intrinio） | ❌【原件】 | — | ✅ 欄位有 `standard_deviation`、`total`、`median`、`most_recent_date`；歷史深度【未查證】 | **Enterprise US$1,250/月起**【原件】 | 分頁全表，數次呼叫【原件】 | Startup 級起才有 Commercial Use and Display Rights；本 feed 限 Enterprise【原件】 | **能**（貴） |
| Zacks（經 Nasdaq Data Link） | 【未查證】 | 【未查證】 | 【未查證】 | 【未查證】 | — | 【未查證】 | 未知 |
| TipRanks（直購 enterprise API） | ✅【原件，行銷層級】 | 【未查證】 | 【未查證】 | 報價【未查證】 | — | 依合約【未查證】 | 能（應比經 FMP 貴） |
| EODHD | ❌ 只有 `WallStreetTargetPrice`（平均）【原件】 | ❌ | ❌ | 個人 US$19.99–99.99/月【原件】 | — | 個人／商業分方案【原件】 | 不能 |
| Alpha Vantage | ❌ 只有 `AnalystTargetPrice` ＋評等人數【原件】 | ❌ | ❌ | Premium US$49.99/月起【原件】 | — | — | 不能 |
| Tiingo | ❌ 無分析師目標價產品【未查證】 | ❌ | ❌ | — | — | — | 不能 |
| Polygon／Massive 原生 | ❌ 僅 Benzinga partner data【原件】 | — | — | — | — | — | 見第一列 |
| Seeking Alpha／MarketBeat／StockAnalysis | 網站有；**無正式授權 API**【轉述／未查證】 | — | — | — | — | ❌（僅第三方爬蟲） | 不能（條款風險） |
| Yahoo／yfinance | ❌ 共識 current／low／high／mean／median【原件：yfinance 原始碼】 | 見 §4.11 | ❌ | 免費（非正式） | — | ❌ 灰色 | 不能 |
| LSEG I/B/E/S | ✅ Detail【原件：WRDS】 | 約 1999 起【轉述】 | ✅ Summary（月快照）【轉述】 | 機構合約【未查證】 | 檔案／feed | 依合約 | 能（不在預算內） |
| FactSet Estimates | ✅ broker detail（analyst、broker、input_date_time）【原件：SDK 文件】 | 「global coverage since 1999」【原件：SDK 文件】 | ✅ `standard_deviation`、`estimate_count`，指標 `PRICE_TGT`【原件：SDK 文件】 | 機構合約【未查證】 | API | 依合約 | 能（不在預算內） |
| S&P Capital IQ Estimates／Visible Alpha | ✅ detailed estimates【轉述】 | 北美 1999 起【轉述】 | 【未查證】 | 機構合約【未查證】 | Xpressfeed／Snowflake【轉述】 | 依合約 | 能（不在預算內） |
| Bloomberg | ✅（ANR／`BEST_TARGET_PRICE`）【未查證】 | 【未查證】 | 【未查證】 | Terminal／Data License【未查證】 | — | ❌ 終端資料不得轉散布【未查證】 | 不在預算內 |
| AnaChart（額外發現） | ✅ 66 萬筆目標價、7K+ 分析師、9K+ tickers【原件】 | **2008 起**【原件】 | ❌ | 一次性 custom report US$149 起；倉儲 share 報價【原件】 | 無 REST API（Snowflake／BigQuery share）【原件】 | 【未查證】 | 可當一次性 backfill |
| Unusual Whales（額外發現） | ✅ analyst_name、firm、target、timestamp【原件】 | 文件只說「latest」【原件】 | ❌ | 【未查證】 | — | 【未查證】 | 未知 |

## 4. 逐源說明

### 4.1 Benzinga Analyst Ratings（經 Massive 轉售／直購）

**Massive（原 Polygon.io）partner data** —— 全部【原件】，來源：
`massive.com/docs/rest/partners/benzinga/analyst-ratings.md`、
`.../consensus-ratings.md`、`massive.com/partners/benzinga`、
`massive.com/pricing`、`massive.com/business`、`massive.com/legal/terms`。

- 端點 `GET /benzinga/v1/ratings`。每筆欄位：`ticker`、`date`、`time`
  （UTC）、`analyst`、`benzinga_analyst_id`、`firm`、`benzinga_firm_id`、
  `price_target`、`previous_price_target`、`adjusted_price_target`、
  `previous_adjusted_price_target`（對 split 與 dividend 調整）、
  `price_target_action`（raises／lowers／maintains／announces／sets）、
  `rating`、`previous_rating`、`rating_action`、`currency`、
  `last_updated`、`benzinga_id`。
- **撤回／有效標記**：沒有 expiry 或 active 欄位；但 `rating_action`
  的值域含 `terminates_coverage_on`、`removes`、`suspends`、
  `firm_dissolved`，可作為「這位分析師的目標價自此失效」的事件。
  「超過 12 個月未更新」仍要自己判定。
- 歷史：文件 Plan History 寫「Records date back to December 8, 2011」，
  Individual 與 Business 方案都是「All history」。行銷頁寫「history
  going back to 2012」。
- 查詢能力：可用 `ticker.any_of`、`date.gte/lte`、`last_updated.gte`
  過濾；`limit` 預設 100、上限 50,000。→ **每日更新 500 檔只需 1 次
  呼叫**（抓昨天以來 `last_updated` 有變動的全部記錄）；首次 backfill
  14 年歷史也只是數十次分頁呼叫。
- 共識端點 `GET /benzinga/v1/consensus-ratings/{ticker}`：
  `consensus_price_target`、`high_price_target`、`low_price_target`、
  `price_target_contributors` 與評等分布；**沒有標準差**，文件列出的
  參數只有 `ticker`／`limit`／`fields`，**沒有日期參數**（只有現值）。
- 價格：`Benzinga Analyst Ratings` 資料集 **US$99/月**（年繳省 20%），
  按鈕旁標明「**Individual use only**」；partner data 是「$99/month per
  dataset」。Business 版頁面寫「Contact for pricing」。Massive 條款：
  Individuals 條款適用「personal, individual, and non-business use」。
  Business 頁另寫新創可談首年 25% 以上折扣。
- 覆蓋：行銷頁稱「broad coverage of the U.S. stock market」；
  「9,000+ US tickers」是搜尋摘要轉述。【轉述】S&P 500 逐檔覆蓋率
  【未查證】。
- **point-in-time 性質**：這是事件流（每筆有發布 `date` 與
  `last_updated`），重建過去某日的有效集合不需要 vendor 的快照；但
  記錄可被事後更新（`last_updated` 存在即表示會改），是否會刪除舊記錄
  【未查證】。

**Benzinga 直購** —— 欄位【原件】（`docs.benzinga.com/api-reference/
calendar-api/get-ratings.md`、`.../get-consensus-ratings.md`）：
`GET /api/v2.1/calendar/ratings`，欄位 `analyst`（券商名）、
`analyst_name`、`analyst_id`、`firm_id`、`pt_current`、`pt_prior`、
`adjusted_pt_current`、`adjusted_pt_prior`、`action_pt`、
`action_company`、`rating_current`、`rating_prior`、`date`、`time`、
`updated`（Unix）、`isin`、`cusip`；`parameters[tickers]` 上限 50 檔、
`pagesize` 上限 1,000、`parameters[updated]` 可做增量同步。共識端點
`/api/v1/consensus-ratings` 有 `consensus_price_target`、high／low、
`total_analyst_count`、`unique_analyst_count`，**無標準差**。價格與
display 授權：benzinga.com 被擋，【未查證】（業界慣例是報價制）。
「歷史自 2013」為搜尋摘要轉述。【轉述】

### 4.2 Financial Modeling Prep（原生端點＋ TipRanks add-on）

來源全部【原件】：`site.financialmodelingprep.com/developer/docs`、
`.../pricing-plans`、`.../terms-of-service`、`.../developer/docs/
changelog`、`.../datasets/analyst-ratings-tipranks`、TipRanks 合作公告
（2026-07-29）。

**原生端點現況**

- 公開 stable 文件的 Analyst 類只有：`price-target-summary`
  （上月／上季／去年／全期的平均目標價與筆數、publishers 清單）、
  `price-target-consensus`（high／low／median／consensus）、`grades`
  系列、`price-target-summary-bulk`。**沒有個別目標價、沒有標準差。**
- 使用者已知的個別目標價端點是 legacy `/api/v4/price-target`（2022-04
  新增，changelog 可見；回傳 analyst 名稱與發布日）。changelog
  2025-08-27：「Legacy API routes are no longer shown in the public
  documentation… accessible only after sign-in, and only to eligible
  accounts」。→ **新帳號能否呼叫 legacy 個別端點、歷史是否自 2021 起，
  今天都無法從公開文件核對。**【未查證】stable 版曾有的
  `price-target-news` 兩支端點，今天的文件索引裡已不存在（文件頁
  404）；API 是否仍回應【未查證】。
- 價格：Basic 免費（250 calls/日；price target 類端點限 87 檔指定
  symbol）；Starter US$29/月（年繳 US$19；300 calls/分；美股）；
  Premium US$69/月（750 calls/分）；Ultimate US$139/月（3,000 calls/分；
  bulk 端點只在這一級）。

**TipRanks add-on（「In partnership with TipRanks」）**

- 文件標示「These endpoints require an active TipRanks add-on」，定價頁
  的說明是「Activate premium third-party datasets that augment your
  core plan」。**add-on 月費在未登入狀態下不顯示**（定價頁的 Partner
  Modules 分頁是登入後才載入）。【未查證】
- 端點：
  - `tipranks-search`：逐筆個別評等。欄位含 analyst 名稱、firm、
    `expertUID`、recommendation、action、price target、來源文章；可用
    `symbol`、`expertUID`、`firmName`、`from`／`to` 過濾；`limit` 上限
    5,000。
  - **`tipranks-pit-symbol?symbol=AAPL&date=YYYY-MM-DD`**：「as of a
    given date, what did every analyst covering this ticker have on the
    books」——把歷史摺成每位分析師最後一筆 active call（每個
    `expertUID` 一列），附目標價與分析師績效統計；`date` 可回溯。
  - `tipranks-pit-analyst`（反向）、`tipranks-symbol-summary`／
    `-analyst-summary`／`-firm-summary`（視窗內的評等與目標價命中統計；
    沒有 stdev）、`tipranks-analysts`（名錄）。
- **歷史深度**：兩支端點的文件 disclaimer 原文：「Ratings history only
  goes back 3 years. For historical analyst ratings beyond that window,
  contact support — it requires an Enterprise plan.」
- 每日 500 檔：`tipranks-search` 不帶 symbol、`from`＝昨日，一兩次
  呼叫即可；或 500 次 `tipranks-pit-symbol`（Starter 300 calls/分，
  約 2 分鐘）。3 年 backfill：每檔 1–2 次 `tipranks-search`。
- **未解的語意**：(1)「latest active call」的 active 是否有內建
  有效期（例如幾個月沒更新就排除）；(2) `nonadjusted` 參數管的是
  **匯率換算**，文件沒有說目標價是否做 split 調整；(3) 3 年視窗邊界：
  在視窗最早那段日期查 PIT 時，更早發布、當時仍有效的 call 是否看得到
  ——若看不到，套 12 個月有效期後可用的 `D_t` 只剩約 2 年。
  三項皆【未查證】。
- 覆蓋：TipRanks 企業頁稱「over 8,000 analysts from 230 firms」。
  【原件】S&P 500 逐檔覆蓋率【未查證】。

**授權（條款原文重點）**

- §2.2.1 Personal Use：個人方案不得「integrate the Data or Services
  into any tools or applications accessible by any third parties, or
  use the Services to host, share, display, or provide content for
  others」。
- §2.2.2 Data Display：「Without a specific agreement with FMP,
  customers are prohibited from showcasing FMP Services or Data on…
  websites… applications designed for utilization by multiple
  individuals, irrespective of whether such usage is complimentary or
  paid」。
- §2.6.1：不得把「data or information contained in or **derived from**
  The Services」提供給第三方。→ **衍生值（D、pass/fail）也在禁止
  範圍內**，除非另簽 Data Display and Licensing Agreement（定價頁
  Commercial Use 分頁的 Enterprise 方案標示「Display and
  Redistribution*」，報價制）。
- §6.2／§6.3：合約終止時必須刪除所有資料**含快取**與衍生資訊，並簽
  Data Deletion Agreement——直接影響 §6 的自存快照策略。

### 4.3 Finnhub

【原件】`finnhub.io/docs/api`（文件頁內嵌的 API 定義）、
`finnhub.io/terms-of-service`。

- `/stock/price-target`：「Get latest price target consensus」——
  `targetHigh`、`targetLow`、`targetMean`、`targetMedian`、
  `numberAnalysts`、`lastUpdated`。Premium。
- `/stock/historical-price-target`：「Get historical price target
  consensus」——同樣五個欄位的時間序列。Premium。**沒有標準差、沒有
  個別目標價。**
- `/stock/upgrade-downgrade`：逐券商評等變動（`company`、`fromGrade`、
  `toGrade`、`action`、`gradeTime`），**不含目標價**。
- 條款：「not redistribute or share access to data or **derived
  results** from the data… without written approval」；「All plan
  listed on Finnhub website is strictly for personal use unless
  explicitly stated otherwise」。
- 價格：定價頁前端渲染抓不到；第三方轉述互相矛盾（US$50/月到
  All-in-One US$3,500/月）。【未查證】
- 對本功能：只能做 `(high − low) / mean` 之類的 range 代理，不是
  spec 定義的 D；歷史深度【未查證】。

### 4.4 Twelve Data

【原件】`twelvedata.com/docs/llms/analysis/*.md`、`/pricing`、`/terms`。

- `/analyst_ratings/us_equities`：`date`、`firm`、`analyst_name`、
  `rating_change`、`rating_current`、`rating_prior`、
  `action_price_target`、`price_target_current`、`price_target_prior`。
  200 credits／symbol；`outputsize` 預設 30；**文件沒有說歷史多深、
  也沒有日期範圍參數**。
- `/price_target`：high／median／low／average（75 credits）；無 stdev、
  無歷史。
- 兩者都限 **Ultra（個人，US$329/月起，2,584 credits/分）** 或
  Enterprise（商業）。500 檔一次 ＝ 100,000 credits ≈ 39 分鐘。
- 條款有一點值得注意：定義了「Derived Data」（無法反推回原始資料的
  衍生資料），允許建立，且「Customer retains rights to Derived Data」；
  但對外 display／redistribution 仍需 Redistribution Rights Add-On 或
  另約。D 與 pass/fail 能否算 Derived Data 而對外顯示，要書面確認。
  【未查證】

### 4.5 Zacks（直購、WRDS、Intrinio、Nasdaq Data Link）

- Zacks 自家歷史資料頁（`zackspro.com/historical.asp`）【原件】：
  「Price Targets - Mean Estimate, Standard Dev, # Analysts, Highest,
  Lowest… History: Price Targets - December 1997 to Present」，涵蓋
  16,000+ 檔美加股票（含已下市）。這是本次找到**唯一明文列出標準差
  歷史序列、且歷史最長**的來源。價格、更新頻率、授權皆報價制。
  【未查證】
- 這是**共識檔**，不是逐分析師目標價（Zacks 的逐券商檔是 estimates 與
  recommendations）。共識的納入規則（多舊的目標價會被剔除）【未查證】
  ——它決定了 Zacks 的 stdev 與 spec 的「12 個月有效期」是否同口徑。
- WRDS 上的 Zacks（學術授權）one-sheet 也列「Target Price
  Consensus」。【原件】不適用於商業產品。
- **Intrinio 轉售**【原件】（`docs.intrinio.com/documentation/web_api/
  get_zacks_target_price_consensuses_v2`、`intrinio.com/products/
  target-prices`、`intrinio.com/pricing`）：端點
  `/zacks/target_price_consensuses` 輸出 `high`、`low`、`mean`、
  **`standard_deviation`**、**`total`**（納入共識的筆數）、`median`、
  `most_recent_date`、`raised`、`lowered`；文件描述為「for the latest
  date」，產品頁 Key Features 列「Historical targets」但沒寫年限
  （「20+ 年」只見於搜尋摘要對舊產品頁的轉述【轉述】）。產品頁明載
  「available exclusively with our Enterprise plan」；定價頁：
  Individual US$150/月（Personal use only、No redistribution or
  display）、Startup US$333/月起（半年後 US$666、一年後 US$999；含
  Commercial Use and Display Rights）、**Enterprise US$1,250/月起**。
- Nasdaq Data Link 上是否有 Zacks 目標價資料集：網站前端渲染、舊 API
  回 410，【未查證】。

### 4.6 TipRanks（直購）

企業入口【原件】（`enterprise.tipranks.com`）：Analyst Ratings API
提供「real-time analyst recommendations, price targets, consensus
ratings, and historical performance insights」，「over 8,000 analysts
from 230 firms」。有公開文件站（`docs.tipranks.com/api-docs`，以
`X-APIKEY`／`X-APITOKEN` 驗證）但內頁抓不到。價格、歷史深度、欄位、
授權皆【未查證】（報價制）。實務上經 FMP add-on 取得會便宜得多，但
要超過 3 年歷史或要 display 授權時，直接問 TipRanks 也是一個選項。

### 4.7 EODHD、Alpha Vantage、Tiingo、Polygon／Massive 原生

- **EODHD**【原件】：Fundamentals 的 Highlights 有
  `WallStreetTargetPrice`（平均目標價）；文件中沒有個別目標價、
  沒有目標價歷史、沒有 stdev 欄位。定價頁分 Personal 與 Commercial 兩套
  方案（個人 US$19.99–99.99/月）。
- **Alpha Vantage**【原件，官方 demo 回應】：`OVERVIEW` 只有
  `AnalystTargetPrice` 與 `AnalystRatingStrongBuy/Buy/Hold/Sell/
  StrongSell`。Premium US$49.99/月起。
- **Tiingo**：文件站前端渲染抓不到；就記憶所及沒有分析師目標價產品。
  【未查證】
- **Polygon／Massive 原生**：分析師資料只有 Benzinga partner data
  （§4.1）。【原件】

### 4.8 Seeking Alpha／MarketBeat／StockAnalysis

三者網站都展示個別券商目標價，但**沒有找到正式、可授權的 API**：
`stockanalysis.com/api/` 回 404；【原件】MarketBeat 被 bot 防護擋下，
第三方轉述稱其不提供公開 developer API；【轉述】Seeking Alpha 只有
RapidAPI 上的非官方包裝。【未查證】Apify 等平台有多支爬蟲 actor，
屬違反網站條款的灰色來源，**不建議**作為公開產品的資料基礎。

### 4.9 機構級：LSEG I/B/E/S、FactSet、S&P Capital IQ／Visible Alpha、Bloomberg

- **LSEG I/B/E/S**：Detail（逐分析師）含 Target Price，Summary 是月
  快照共識。目標價起始年：一篇使用 I/B/E/S 共識目標價的論文樣本為
  1999-07 至 2018-06，【轉述】官方起始年月【未查證】。**改寫風險
  【原件：WRDS 公告與 vendor 頁】**：
  - 2026-03-27 公告：2026-06 更新起，Jefferies 與 Morningstar 的
    Detailed Estimates（含 Target Price、Recommendations）應兩家要求
    移除，「will likely lead to analyst and broker masked identifiers
    being reshuffled」；Summary 檔的過去值不變。
  - 2018-10-18：13.8% 的 broker ID、30.7% 的 analyst ID 被重新指派；
    UBS Equities 自 Detail History 移除。
  → Detail 檔**不是** point-in-time 穩定的；券商可事後整批抽走。
  價格為機構合約，WRDS 僅限學術。【未查證】
- **FactSet Estimates API**【原件：FactSet 官方 enterprise-sdk 文件】：
  指標清單含 `PRICE_TGT`；共識物件有 `mean`、`median`、
  `standard_deviation`、`high`、`low`、`estimate_count`、
  `estimate_date`；broker detail 物件有 `analyst_id`、`analyst_name`、
  `broker_id`、`broker_name`、`input_date_time`、`last_modified_date`；
  「global coverage since 1999」。資料面完全符合 (a) 與 (b) 兩種路線，
  但需企業訂閱，價格與 display 條款【未查證】。
- **S&P Capital IQ Estimates**：detailed estimates 涵蓋 19,000+ 公司、
  610+ contributors，北美歷史自 1999，含 Target Price，經 Xpressfeed／
  Snowflake 交付。【轉述】目標價是否附 stdev【未查證】。Visible Alpha
  主打 line-item 共識，與目標價關聯低。【未查證】
- **Bloomberg**：Terminal（ANR、`BEST_TARGET_PRICE`）與 Data License；
  價格與條款【未查證】；一般認知是終端資料不可對外轉散布。

這四家對 solo-developer 專案的量級都是每年五位數美元起跳的企業合約
【未查證】，列入只為完整。

### 4.10 額外發現：AnaChart、Unusual Whales

- **AnaChart**【原件】（`anachart.com/analyst-price-target-data/`）：
  自稱 66 萬筆以上目標價、75 萬筆以上評等、7K+ 分析師、9K+ tickers
  （含已下市），**2008 起**。交付方式沒有 REST API：Snowflake／
  BigQuery native share（月訂閱，「Quoted to the cut」；搜尋摘要稱
  US$1,000/月起【轉述】）或**一次性 custom report（US$149 起，
  Excel／PDF，一個工作天）**。對本功能的意義：可能是**一次性買斷
  歷史 backfill** 的便宜途徑（例如「這 500 檔 2008 年以來全部個別
  目標價」），再用別的來源做每日更新。資料來源、品質、授權（能否
  用於商業產品、能否顯示衍生值）【未查證】。
- **Unusual Whales**【原件】（`api.unusualwhales.com/docs`）：
  `GET /api/screener/analysts` 回傳 `analyst_name`、`firm`、`target`、
  `recommendation`、`timestamp`，描述為「latest analyst ratings」；
  歷史深度、價格、授權【未查證】。

### 4.11 Yahoo／yfinance（核對使用者已知事項）

yfinance 原始碼【原件：GitHub `yfinance/scrapers/analysis.py`、
`quote.py`】：`analyst_price_targets` 取 `financialData` 模組的
`target*` 欄位（current／low／high／mean／median），確認**沒有 stdev、
沒有個別目標價**。`upgrades_downgrades` 則把 Yahoo
`upgradeDowngradeHistory` 的每列原樣轉成 DataFrame（Firm、ToGrade、
FromGrade、Action…）。Yahoo 近期的回應是否在這個模組裡附帶逐券商的
目標價欄位，本次無法核對。【未查證】即使有，Yahoo 仍是非正式來源、
在本專案的 serverless 環境跑不起來、條款灰色，結論不變。

## 5. 四個問題的答案

### 5.1 最便宜的 prototype 路徑（約 50 檔）

**Massive 的 Benzinga Analyst Ratings，US$99/月，月繳、驗證完即可
停。** 理由：

- 14 年以上的個別目標價事件史，足以把 `D_t` 重建、Dispersion
  Percentile、有效期規則、split 處理全部驗證一遍（對應驗證計畫的
  離線階段）；用 `ticker.any_of` 過濾，50 檔全史只需數次分頁呼叫
  （每頁上限 50,000 筆）。
- 欄位有穩定的 analyst／firm ID 與 adjusted 目標價，省掉去重與 split
  換算的大半工程。
- 限制：方案標明 Individual use only。**Owner 私下離線研究**大致落在
  個人用途，但這是條款解釋問題，【未查證】；**任何結果只要出現在
  公開 beta 上就不是個人用途**。

備案：FMP 核心方案＋ TipRanks add-on（PIT 端點省掉自建重建邏輯，
但只有 3 年、add-on 價格未知）。兩者都沒有可用的免費層：FMP 免費層
涵蓋 87 檔，但只到 summary／consensus，沒有 stdev 也沒有個別目標價。

### 5.2 最便宜的 production 路徑（500 檔每日、含顯示授權）

**沒有任何自助價位包含顯示授權；每一條路都要先談合約。** 依「預期
成本由低到高」排序（除 Intrinio 外皆無公開報價）：

1. **Massive 的 Benzinga Analyst Ratings Business**（報價；新創首年
   25% 以上折扣）或 **Benzinga 直購授權**（報價）。歷史最深
   （2011 起）、每日 1 次呼叫。
2. **FMP Enterprise（Display and Redistribution）＋ TipRanks add-on**
   （報價）。有現成 PIT 端點；公開方案只有 3 年歷史，更深的歷史
   本來就要 Enterprise。
3. **Intrinio Enterprise 的 Zacks Target Price Consensus**：
   **US$1,250/月起**（每年約 US$15,000 起）——這是本次找到**唯一有
   公開價格、且含 stdev 與商業顯示權**的組合；走 (b) 路線，工程量
   最小，但沒有個別目標價，口徑由 Zacks 決定。歷史深度待確認。
4. Zacks 直購歷史檔＋更新檔（報價；1997-12 起，stdev 現成）。
5. LSEG／FactSet／S&P／Bloomberg（企業合約，不在預算量級內）。

談判時值得主動提的一點：本功能**不需要顯示任何一筆原始個別目標價**，
只顯示 Consensus Target（平均）、D、百分位與 pass/fail。「derived-only
display」的授權通常比原始資料 display 便宜，但各家條款對衍生值的
態度不同（FMP、Finnhub 明文把衍生值算進限制；Twelve Data 明文承認
Derived Data 歸客戶），**必須書面確認**，不能自行推定。

### 5.3 歷史太淺時，自己每日存快照能買到什麼

能買到的：

- **真正的 point-in-time**：自己某日存下的那一組目標價不會被 vendor
  事後改寫或抽走（I/B/E/S 2026-06 那種整家券商被移除的情況不影響
  已存檔的快照）。
- **歷史隨時間自己長出來**：搭配 3 年 backfill（FMP＋TipRanks）起步，
  每過一年多一年；`D_t` 序列每檔每日一個數，500 檔 × 252 日 ≈ 12.6 萬
  列／年，對 Neon 免費層是很小的負擔（若連個別目標價一起存，約
  500 檔 × 25 位分析師的變動事件，量級仍小）。
- **可稽核**：某天為什麼 pass／fail，可以拿當日快照重算。

買不到的：

- **不能回補過去**：只存快照的話，第一關（自身歷史最低 20%）在歷史
  累積足夠之前無法啟用。且目標價多在財報季更新，`D_t` 變動緩慢——
  一年的日資料約只對應 4 個財報週期的獨立資訊，百分位排名會很粗。
  （此點為本文推論，非 vendor 事實。）3 年歷史也只約 12 個週期；
  這是「3 年就夠嗎」的統計面疑慮，與資料源無關。
- **不是授權上的護城河**：FMP 條款 §6.2／§6.3 要求終止合約時刪除
  全部資料、快取與衍生資訊；【原件】換 vendor 時自存的歷史可能必須
  銷毀。其他 vendor 的保留條款【未查證】。簽約前應把「終止後可否
  保留衍生序列 `D_t`」列為明確條款。
- **不能繞過 display 授權**：存下來的仍是 vendor 資料或其衍生物。

結論：自存快照**值得做**（成本極低，換到 PIT 與可稽核），但它是
backfill 的補充，不是替代；真正決定第一關能否上線的是 backfill 深度。

### 5.4 未能查證的事項

見 §6。

## 6. 未經查證事項（採用前必須補查）

價格與授權：

1. FMP TipRanks add-on 的月費、需要搭配哪一級核心方案。
2. Massive「Benzinga Analyst Ratings Business」價格與是否含對外
   display；Individual 方案能否用於未公開的個人研究。
3. Benzinga 直購價格、最短合約期、display／derived-only 條款
   （benzinga.com 被擋）。
4. Finnhub 目前的方案與價格（定價頁抓不到）。
5. Zacks 直購、TipRanks 直購、LSEG、FactSet、S&P、Bloomberg 的價格
   量級（文中「每年五位數美元」為一般認知，非報價）。
6. 各家對「只顯示衍生值」的授權立場（除 FMP、Finnhub、Twelve Data
   條款原文外）。
7. 各家合約終止後能否保留已存資料或衍生序列（僅 FMP 已核對）。

資料語意：

8. FMP `tipranks-pit-symbol` 的「active call」定義（有無內建有效期）、
   目標價是否做 split 調整、3 年視窗邊界是否截斷當時仍有效的舊 call。
9. FMP legacy `/api/v4/price-target` 新帳號能否使用、歷史是否自 2021。
10. Benzinga／Massive 記錄事後被修改或刪除的頻率（是否影響 PIT 重建）。
11. Zacks 目標價共識的納入規則（有效期），與 spec 的 12 個月口徑是否
    一致；Intrinio 提供的歷史深度與取得方式（API 還是檔案）。
12. Twelve Data `/analyst_ratings/us_equities` 的歷史深度。
13. I/B/E/S 目標價 Detail／Summary 的官方起始年月（文中 1999 為論文
    樣本期間的轉述）。
14. Yahoo `upgradeDowngradeHistory` 是否已含逐券商目標價欄位。

覆蓋：

15. 任何一家對 S&P 500 的**逐檔**覆蓋率與每檔分析師人數（各家只有
    總量級的行銷數字）。建議 prototype 階段直接實測：500 檔中有效
    個別目標價 ≥ N 筆的比例。
16. ETF：推定各家皆無分析師目標價，未逐家確認。
17. AnaChart 的資料來源、授權範圍與 custom report 對「500 檔全史」的
    實際報價。

## 7. 來源

FMP

- 定價（個人）：https://site.financialmodelingprep.com/developer/docs/pricing
- 定價（商業）：https://site.financialmodelingprep.com/pricing-plans?planType=commercial
- 條款：https://site.financialmodelingprep.com/terms-of-service
- 文件索引（含 TipRanks 區段）：https://site.financialmodelingprep.com/developer/docs
- `tipranks-pit-symbol`：https://site.financialmodelingprep.com/developer/docs/stable/tipranks-pit-by-symbol
- `tipranks-search`：https://site.financialmodelingprep.com/developer/docs/stable/tipranks-search
- TipRanks 資料集頁：https://site.financialmodelingprep.com/datasets/analyst-ratings-tipranks
- 合作公告（2026-07-29）：https://site.financialmodelingprep.com/insights/platform/fmp-and-tipranks-join-forces-to-bring-professional-analyst
- `price-target-summary`：https://site.financialmodelingprep.com/developer/docs/stable/price-target-summary
- `price-target-consensus`：https://site.financialmodelingprep.com/developer/docs/stable/price-target-consensus
- legacy Price Targets：https://site.financialmodelingprep.com/developer/docs/price-target-api
- Changelog：https://site.financialmodelingprep.com/developer/docs/changelog

Benzinga／Massive

- Massive Analyst Ratings：https://massive.com/docs/rest/partners/benzinga/analyst-ratings.md
- Massive Consensus Ratings：https://massive.com/docs/rest/partners/benzinga/consensus-ratings.md
- Massive × Benzinga（價格、Individual use only）：https://massive.com/partners/benzinga
- Massive 定價：https://massive.com/pricing ｜ Business：https://massive.com/business
- Massive 條款：https://massive.com/legal/terms
- Benzinga Ratings：https://docs.benzinga.com/api-reference/calendar-api/get-ratings.md
- Benzinga Consensus Ratings：https://docs.benzinga.com/api-reference/calendar-api/get-consensus-ratings.md

Finnhub／Twelve Data／EODHD／Alpha Vantage

- Finnhub 文件：https://finnhub.io/docs/api/price-target
- Finnhub 條款：https://finnhub.io/terms-of-service
- Twelve Data Analyst ratings US：https://twelvedata.com/docs/llms/analysis/analyst-ratings-us.md
- Twelve Data Price target：https://twelvedata.com/docs/llms/analysis/price-target.md
- Twelve Data 定價：https://twelvedata.com/pricing ｜ 條款：https://twelvedata.com/terms
- EODHD Fundamentals：https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds
- EODHD 定價：https://eodhd.com/pricing
- Alpha Vantage 文件：https://www.alphavantage.co/documentation/ ｜ Premium：https://www.alphavantage.co/premium/

Zacks／Intrinio／TipRanks

- Zacks 歷史資料：https://www.zackspro.com/historical.asp
- Zacks on WRDS one-sheet：https://wrds-www.wharton.upenn.edu/documents/1174/Zacks-One-Sheet.pdf
- Intrinio Zacks Target Price Consensuses：https://docs.intrinio.com/documentation/web_api/get_zacks_target_price_consensuses_v2
- Intrinio Price Targets 產品頁：https://intrinio.com/products/target-prices
- Intrinio 定價：https://intrinio.com/pricing
- TipRanks Enterprise：https://enterprise.tipranks.com/
- TipRanks API 文件站：https://docs.tipranks.com/api-docs

機構級

- WRDS：Changes to IBES data（2026-03-27 公告）：https://wrds-www.wharton.upenn.edu/pages/special-pages/vendor-and-product-alert-listing-page/changes-to-ibes-data/
- WRDS：I/B/E/S vendor 頁（2018 ID 重排、UBS 移除）：https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/vendor-partner-ibes/
- FactSet Estimates SDK 文件：https://github.com/factset/enterprise-sdk/tree/main/code/python/FactSetEstimates/v2
- S&P Capital IQ Estimates（轉述）：https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates
- I/B/E/S 目標價樣本期間（轉述）：https://business.columbia.edu/sites/default/files-efs/imce-uploads/FRANK%20ZHANG%20PAPER%20PSZ_20190913.pdf

其他

- AnaChart：https://anachart.com/analyst-price-target-data/
- Unusual Whales Analyst Rating：https://api.unusualwhales.com/docs/operations/PublicApi.ScreenerController.analyst_ratings
- yfinance 原始碼：https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/analysis.py 、 https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/quote.py
