# 無風險利率公開資料源評選（不預設 Treasury）

研究日期：2026-08-05。對應 issue #73。

**取材限制聲明**：本沙箱出口 proxy 對本文評估的**所有**候選來源域名
（`home.treasury.gov`、`fiscaldata.treasury.gov`／`api.fiscaldata.treasury.gov`、
`fred.stlouisfed.org`／`api.stlouisfed.org`、`fredaccount.stlouisfed.org`、
`markets.newyorkfed.org`／`apps.newyorkfed.org`、`federalreserve.gov`、
`query1.finance.yahoo.com`、`alphavantage.co`）的直接連線一律回
**CONNECT 403**（WebFetch 與 `curl` 皆實測失敗；`$HTTPS_PROXY/__agentproxy/status`
的 `recentRelayFailures` 顯示原因是
`"gateway answered 403 to CONNECT (policy denial or upstream failure)"`——
是這個沙箱自己的出口政策擋下，不是目的站拒絕，也**不是**這些站台不可達的
證據）。這與前次研究（`docs/research/risk-free-rate-for-bs.md`）遇到的狀況
完全相同，且範圍更廣：這次連 Treasury 官方新版 REST API
（`api.fiscaldata.treasury.gov`）與 FRED 官方 API（`api.stlouisfed.org`）
也一併被擋，證明**這是本沙箱對整類金融／政府資料網域的政策封鎖**，
與網域本身的可及性、與正式環境（Vercel）能否連通完全無關——本
repo 的正式環境已證實能連上 Cboe（`cdn.cboe.com`，見 CLAUDE.md V1／#48
與 `docs/deploy-vercel.md`「部署後的第一件事：確認 Cboe 可達性」一節）。
**本文任何一句話都不會用「這個沙箱連不上」去推論「正式環境也連不上」**——
凡標「經搜尋索引摘錄」者，內容來自搜尋引擎索引到的官方文件頁／第三方
逐欄位轉述，未能在本環境逐位元核對；無法以任一方式確認者列入 §7。
真正的可及性答案由 §6 的正式環境探測程序取得，其結果可推翻本文排序。

> **2026-08-05 追記（issue #74，已在 Vercel 正式環境實測，見 §6.4）**：
> Primary 維持 Treasury，探測確認可達、已硬化並落地。§5 排序的
> 「Fallback #1：FRED 免鑰路徑」**被實測推翻**——`fredgraph.csv` 便利
> 端點本身逢時（官方 keyed API 網域是通的，純粹缺金鑰）。目前落地的
> fallback 鏈是「Treasury → 陳舊窗快取 → 固定 4%」，FRED／FMP 兩個
> keyed 備援待需求方之後申請金鑰再接上——技術上可行、只是還沒做。
> 需求方另外提議的 Yahoo Finance 免鑰指數，用真實資料重新驗證後
> 結論不變（涵蓋範圍不夠，1–3 年期插值誤差過大），維持不採用。

## 1. 摘要（結論先行）

- **推薦排序**：**① US Treasury Daily Par Yield Curve（`home.treasury.gov`
  CSV/XML，現行實作）→ ② FRED DGS 系列（`api.stlouisfed.org` 官方 API，
  免鑰 `fredgraph.csv` 為次選路徑）→ ③ Financial Modeling Prep
  `treasury-rates`（付鑰、單次呼叫回全曲線）→ ④ 現行固定 0.04**。
  這**不是**蕭規曹隨——本文對 9 個候選逐一在 8 個維度上重新比較（§3–5），
  結論會在下列三點上明確**修正**前次研究的處理方式：
  1. **新負面發現**：Treasury 現代化、有正式版本控管與文件的
     Fiscal Data REST API（`api.fiscaldata.treasury.gov`）**不含**
     Daily Treasury Par Yield Curve 這個資料集——搜尋多組關鍵字、逐一
     核對 fiscaldata.treasury.gov 的公開資料集清單頁，均未見其蹤影；
     殖利率曲線只活在 Treasury 舊版「Data Chart Center」CSV/XML 這條
     **非正式、無版本文件的網頁下載端點**上（§3.1、§7）。即本 repo
     現行實作用的其實是 Treasury 唯一可行、但最不「像 API」的那條路。
  2. **FRED 從「次選、較不建議」升格為第一備援，且理由是操作面而非
     資料本質**：FRED 的 `DGS*` 系列是 Treasury CMT 的逐日鏡像（同一
     par yield、同一 BEY 報價口徑），**欄位語意與本 repo 既有
     `par_to_continuous()` 轉換公式完全相容**——換源不必動
     `ratecurve.py` 消費端一行，只需新增一個 fetch adapter（§3.2、§5）。
     FRED 有正式文件化的 REST API＋速率限制＋免費金鑰（申請即用），
     這在「機器可讀 API」與「可靠性」兩個維度上其實**優於** Treasury
     自己的 CSV/XML 頁面。且 FRED 網域是 `stlouisfed.org`（聯邦準備銀行
     自有網域），與 Treasury 的 `.gov` 網域走不同基礎設施——若正式環境
     擋 Treasury 的原因是「擋 .gov」這一類網域層級封鎖，FRED 是真正
     獨立的備援路徑，不是同一套基礎設施的兩個門面（§5）。
  3. **新增候選 Financial Modeling Prep 作第三層**：單次 GET 回傳完整
     1M–30Y 曲線、免費層 250 次/日相當寬裕、JSON 欄位乾淨（§3.7）。
     不是比 Treasury／FRED 更「正」的來源（它本身也是轉手 Treasury
     數據的商業聚合站），純粹作為「兩個政府來源都連不上」時的操作層
     保險——且不需要為它另外設計解析器，一次 GET 就是全曲線。
- **明確剔除的候選**：NY Fed SOFR（無真正期限結構，見 §3.4）、
  CME Term SOFR（授權不可行，沿用前次研究 §3.1 已驗證的結論）、
  Yahoo Finance ^IRX/^FVX/^TNX/^TYX（3M 與 5Y 之間完全無節點，
  本 app 主戰場 1M–3Y 幾乎整段落在缺口裡，見 §3.5）、Fed H.15 官方直接
  XML feed（Fed 自己在 2026 年正把 Data Download Program 逐步退役、
  導引使用者改用 FRED，見 §3.3）、Alpha Vantage `TREASURY_YIELD`
  （缺 1 個月與 1 年兩個關鍵節點、且與本 repo 既有 Alpha Vantage
  選擇權備援方案共用同一組 25 次/日全站配額，會互搶，見 §3.6）。
- **與前次研究（`risk-free-rate-for-bs.md`）的分工**：那篇答的是「BS 的
  r 該是什麼、換算公式怎麼推」（理論層，結論仍然有效，本文不重推）；
  本文答的是「去哪裡抓、抓不抓得到、抓壞了退到哪」（資料源操作層）。
  兩篇對 Treasury 是否該用的判斷方向一致，但本文是**獨立重新比較**
  得出的，不是照搬前文結論（任務要求的正是這一點）。

## 2. 評選維度（8 項，逐源固定套用）

1. 機器可讀 API（非僅可爬取的 HTML）
2. 是否需要 API key，取得與管理的摩擦／成本
3. 期限覆蓋——BS 需要期限結構，單一利率不能當主要來源
4. 更新頻率與資料延遲
5. 可靠性——歷史格式穩定度、有無 SLA、schema 改版頻率
6. 速率限制
7. Vercel／serverless 適配度——冷啟動友善？一次請求拿到整條曲線，
   還是要打很多次？有無長連線需求？
8. 備援可行性——欄位與其他候選的相容程度、真的要切換時的成本

## 3. 逐源評估

### 3.1 US Treasury Daily Par Yield Curve（`home.treasury.gov`）—— 現行實作

- **端點**：資料頁
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value={YYYY}`；
  CSV 直鏈
  `…/daily-treasury-rates.csv/{YYYY}/all?type=daily_treasury_yield_curve&field_tdr_date_value={YYYY}&_format=csv`；
  XML feed
  `…/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={YYYY}`
  （feed 說明頁 https://home.treasury.gov/treasury-daily-interest-rate-xml-feed ）。
  本 repo 現行實作見 `option_chaser/data/treasury.py`（CSV 為主、XML 備援、
  前一年 CSV 再備援），解析在 `option_chaser/ratecurve.py`。
- **① 機器可讀 API？** **否，嚴格來說不是**——這是政府 CMS
  （Drupal-based「Data Chart Center」）頁面提供的「下載 CSV／XML」
  連結，**沒有官方 API 參考文件、沒有版本號、沒有請求／回應 schema
  承諾**。現行程式碼用的 CSV URL 樣式甚至是**轉引自第三方套件**
  （`dailytreasuryrates`、`epogrebnyak/data-ust`，見前次研究 §4.1），
  不是 Treasury 自家 API 文件給的範例——這點是本文新確認的：Treasury
  真正「現代化、有文件」的 API 是 **Fiscal Data**
  （base URL `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/`，
  官方文件 https://fiscaldata.treasury.gov/api-documentation/ ，開放存取
  免帳號、JSON/CSV/XML 皆可選、有 `fields`／`filter`／`sort` 查詢參數），
  但**這個殖利率曲線資料集不在 Fiscal Data 裡**——反覆用不同關鍵字
  搜尋 fiscaldata.treasury.gov 的公開資料集清單（`/datasets/…`），
  只找到「Average Interest Rates on U.S. Treasury Securities」
  （https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/ ，
  這是**流通在外債務的加權平均票面利率**，跟 BS 要的**市場殖利率曲線**
  是兩回事）與其他不相干資料集，**未見任何 par-yield-curve／
  yield-curve-rates 資料集頁面**。結論：唯一涵蓋 CMT 殖利率曲線的
  Treasury 管道，就是舊版 Data Chart Center 這條**非正式下載端點**。
- **② API key？** 不需要，免鑰。
- **③ 期限覆蓋？** 最完整——1, 1.5, 2, 3, 4, 6 個月＋1, 2, 3, 5, 7, 10,
  20, 30 年，共 14 個節點，本 app 需要的 1M–3Y 區間內就有 8 個節點
  （經搜尋索引摘錄確認的官方頁面自述，
  https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026 ；
  本文與前次研究交叉確認一致）。
- **④ 更新頻率／延遲？** 每個交易日一筆，報價基礎是「當日約下午 3:30 ET
  由紐約聯邦準備銀行取得的收盤前指示性報價」（方法論頁
  https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology ，
  經搜尋索引摘錄）；**確切的公開發布時間（是否當日晚間即可下載、
  抑或次一營業日才更新）未能查證**，列入 §7。
- **⑤ 可靠性？** 官方一手來源、公有領域資料，內容權威性最高；但
  **傳遞管道本身歷史上已知至少換過一次 URL 樣式**（舊版
  `treasury.gov/…/pages/TextView.aspx?data=yieldAll` 一類網址仍可在
  搜尋索引與第三方連結中看到，現行網址已改為
  `home.treasury.gov/…/TextView?type=…`），且**無任何公開 SLA、無
  schema 版本號、無「下一次改版會如何」的官方承諾**——本 repo 自己的
  程式碼註解也寫明「端點 URL 為搜尋索引轉述，以實際回應為準」
  （`treasury.py` 檔頭）。這是一手資料源可靠性維度上**最弱**的一環。
- **⑥ 速率限制？** 未見任何公開文件提及此端點的速率限制（Fiscal Data
  API 有找到「免鑰但可選填 api_key 換取更高限額」的說法，但那是另一個
  不含此資料集的系統，不適用）。
- **⑦ Vercel 適配度？** 佳——單一 GET 回傳整年份 CSV（含當年所有交易日、
  所有節點），一次請求即拿到完整曲線；無需長連線、無需分頁；純文字
  回應，`urllib` 即可處理，與本 repo 既有 `cboe.py`／`treasury.py` 的
  stdlib-only 風格一致。**已知的正式環境缺口**：現行 `treasury.py` 的
  7 日陳舊窗快取寫入本地檔案系統（`snapshots/treasury_curve_cache.json`），
  而 Vercel serverless **唯讀檔案系統**這件事在本 repo 已有明文記錄
  （`api_app/main.py` 檔頭：「serverless 前提：全程不碰檔案系統
  （Vercel 唯讀）」；`option_chaser/service.py` 的 `run_with_snapshot`
  docstring 同樣寫明「serverless（Vercel）檔案系統唯讀」）——這條快取
  路徑目前在正式環境下**不會生效**
  （每次冷啟動都是全新檔案系統），屬於進新一輪 Vercel 重寫（V1/#48 之後
  的利率整合票）必須一併處理的既有工程缺口，不是本研究的新結論但值得
  在此標記，因為它直接影響 §5 的 fallback 設計是否真的能「7 日內用快取」。
- **⑧ 備援相容性？** 作為「基準」被拿來跟其他來源比對——見各源
  小節；與 FRED 的相容度最高（§3.2）。

### 3.2 FRED（Federal Reserve Bank of St. Louis）—— 推薦第一備援

- **兩條路徑**：
  (a) **官方文件化 REST API**：`https://api.stlouisfed.org/fred/series/observations?series_id={ID}&api_key={KEY}&file_type=json`
  （文件 https://fred.stlouisfed.org/docs/api/fred/series_observations.html ，
  金鑰頁 https://fred.stlouisfed.org/docs/api/api_key.html ）——**一次呼叫
  只回一個 series**，要組出完整曲線需對每個 tenor 各打一次（1M–3Y 區間
  約 6–8 個 series：`DGS1MO`／`DGS2MO`／`DGS3MO`／`DGS4MO`／`DGS6MO`／
  `DGS1`／`DGS2`／`DGS3`，其中 `DGS2MO`／`DGS4MO` 的存在**經搜尋索引摘錄
  間接確認**、未逐一開啟系列頁核對，見 §7）。
  (b) **`fredgraph.csv` 便利端點**（供網站圖表下載用，非正式 REST API
  文件的一部分，但**免鑰、支援逗號分隔多 series 一次取回**）：
  `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS1MO,DGS3MO,DGS6MO,DGS1,DGS2,DGS3`
  ——第三方工具（如 `ivo-welch.org` 的「FRED CSV Gateway」
  https://ivo-welch.org/professional/fredcsv.html ）長年依賴這個端點的
  多 series 語法，屬**廣泛使用但無正式文件承諾**的慣例用法。
- **① 機器可讀 API？** 是，(a) 路徑有完整官方 API 參考文件（版本化，
  另有 `fred/v2/…` 系列端點，見
  https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html ）；
  這點**優於** Treasury 自己的 CSV/XML 頁面。
- **② API key？** (a) 路徑需要；免費申請、`fredaccount.stlouisfed.org`
  信箱註冊即時啟用（經搜尋索引摘錄）——摩擦極低，一次性設定，存成
  Vercel 環境變數即可，與本 repo 未來 Neon `DATABASE_URL` 走的模式一致。
  (b) 路徑免鑰，但屬「借用網站內部端點」，非官方承諾穩定。
- **③ 期限覆蓋？** 與 Treasury CMT 一一對應（DGS 系列本來就是 Treasury
  CMT 的每日鏡像），本文查證明確存在的至少有 `DGS1MO`／`DGS3MO`／
  `DGS6MO`／`DGS1`／`DGS2`／`DGS3`／`DGS5`／`DGS7`／`DGS10`／`DGS20`／
  `DGS30`（https://fred.stlouisfed.org/series/DGS1 、DGS2、DGS5、DGS10、
  DGS20、DGS30、DGS1MO 等系列頁；經搜尋索引列出）；`DGS2MO`／`DGS4MO`
  存在但**未逐一開啟系列頁確認起始日期與是否仍在維護**，列入 §7。
  1M–3Y 區間內至少 6 個可確認節點，足夠支撐既有線性插值設計。
- **④ 更新頻率／延遲？** 逐日更新，鏡像 Treasury CMT／Fed H.15 發布，
  **確切的「當日 vs. 次一營業日可得」時間未能查證**（列入 §7）。
- **⑤ 可靠性？** 這是本文所有候選中**歷史穩定度證據最強**的一個：
  FRED 由聖路易聯邦準備銀行維運、部分序列回溯至 1962 年，且有
  **ALFRED（Archival FRED）保存每一版本的修訂歷史**（vintage date／
  `realtime_start`／`realtime_end` 概念，見
  https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html ，
  GitHub `mortada/fredapi` 對此有完整說明）——這代表 FRED 不只是「有」
  歷史資料，還**明確追蹤每筆資料何時被修訂過**，是資料治理成熟度的
  直接證據。搜尋未見任何 API 端點破壞性改版的公開紀錄（只查到 2026-07
  新增 `fred/v2/release/observations` 一類**擴充**端點，非破壞既有 v1）。
- **⑥ 速率限制？** 有文件化：**申請 key 後 120 次/分鐘**（未帶 key
  的基準額度較低，一份二手來源提到 30 次/分鐘，**未能在官方文件逐字
  核對這個「30」的數字**，列入 §7；但無論如何，帶 key 之後 120/分鐘
  對「每次分析打 6–8 個 series」的用量而言極寬裕）。
- **⑦ Vercel 適配度？** 佳。(a) 路徑一次分析需 6–8 次循序或平行 GET，
  單次都是小型 JSON，遠在 Vercel `maxDuration: 60`（見
  `docs/deploy-vercel.md`）內完成；無長連線需求。(b) 路徑一次 GET
  拿到多 series CSV，呼叫次數更少，但依賴一個沒有正式文件承諾的
  便利端點——建議只在(a)路徑失敗時當內部次要手段，不當唯一實作。
- **⑧ 備援相容性？** **本文重點結論**：DGS 系列與 Treasury CMT 同一
  報價口徑（半年複利 bond-equivalent par yield），`ratecurve.py` 的
  `par_to_continuous()`／`rate_for_tenor()` 消費端**完全不用改**，
  只需新增一個把 FRED JSON/CSV 轉成
  `tuple[tuple[年期, par 小數]]` 的 adapter——與 Treasury CSV/XML
  解析器同等重量級（都是「一個純函式轉一種文字格式」）。這是它從
  「次選」升格為「第一備援」的核心理由：換源代價全 repo 最低。

### 3.3 Federal Reserve Board H.15（`federalreserve.gov`）—— 不建議直接對接

- **端點**：XML feed `https://www.federalreserve.gov/feeds/h15.xml`／
  `H15_H15.XML`（SDMX 格式，schema 說明見
  https://www.federalreserve.gov/feeds/datadownload.xml ），或透過
  Data Download Program（DDP）自訂資料包
  `https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15`。
- **① 機器可讀 API？** 有 XML（SDMX 標準格式，非隨意結構），比 Treasury
  CSV/XML 更「像」正式資料交換格式。
- **② API key？** 不需要。
- **③ 期限覆蓋？** H.15 本身涵蓋聯邦資金利率、多個 T-bill 到期別
  （4 週/13 週/26 週/52 週）與 CMT（1,2,3,5,7,10,20,30 年）——內容上
  足夠，但本質上是 Treasury CMT 加聯邦資金利率的**再包裝**，不是獨立
  一手數據。
- **④ 更新頻率？** 每個交易日一次（H.15 為 Fed 每日發布的統計釋出）。
- **⑤ 可靠性——本文新發現，判定為不建議的關鍵**：Fed 官方公告
  **正在退役 DDP**——「截至 2026-07-16，理事會計畫在 2026-11-09 當週
  從 DDP 移除『Build Your Package』選項，為 DDP 最終退役鋪路，使用者
  屆時改用 FRED 或直接下載該釋出的 XML 格式檔案」（搜尋索引摘錄自
  `federalreserve.gov/datadownload/help/default.htm` 一類頁面內容，
  **未能逐字核對原文**，但多個獨立搜尋結果一致指向同一時間點與同一
  遷移方向）。即：**Fed 自己都在把使用者導去 FRED**，直接對接一個
  官方已宣告要退役的系統沒有意義——這正是本文把 FRED 而非 Fed 直連
  排進主要候選的另一個佐證。XML feed 頁面本身（`/feeds/h15.xml`）是否
  在 DDP 退役後仍會留存，**未能查證**。
- **⑥⑦⑧** 因⑤已判定不建議，不展開細評；若後續真要用，其 SDMX
  schema 解析成本高於 Treasury CSV／FRED JSON，備援相容性也弱
  （SDMX 欄位命名與 DGS/CMT 慣例不同，需要獨立 mapping）。

### 3.4 NY Fed SOFR（Markets Data API）—— 剔除：無真正期限結構

- **端點**：資料頁 https://www.newyorkfed.org/markets/reference-rates
  、SOFR Averages 專頁
  https://www.newyorkfed.org/markets/reference-rates/sofr-averages-and-index
  ；Markets Data API 有官方規格文件
  （https://apps.newyorkfed.org/~/media/XML/Schemas/api_spec ，搜尋索引摘錄），
  免鑰 JSON。
- **① 機器可讀 API？** 是，官方明講「SOFR Averages and Index data
  will be available via API call」且提供 schema 文件——這是本文所有
  候選裡**唯一有正式 schema spec 文件**的官方端點。
- **② API key？** 不需要。
- **③ 期限覆蓋——判定剔除的直接原因**：SOFR Averages 是
  **回顧性（backward-looking）、對已實現隔夜 SOFR 做複利平均**的
  30／90／180 **日曆天**滾動平均（依 ISDA 複利公式；經搜尋索引摘錄
  自 ARRC《An Updated User's Guide to SOFR》），**不是**對未來到期日的
  市場報價利率。即使把 180 天（約 0.5 年）硬套進 BS 的 r，語意也是錯的
  ——它回答的是「過去 180 天平均隔夜利率是多少」，不是「今天市場對
  0.5 年期無風險利率的定價是多少」。且最長節點只到 180 天，本 app
  需要的 1–3 年區間**完全沒有覆蓋**。與前次研究 §4「無期限結構」的
  結論一致，本文在此把機制講清楚：不是「數據不夠多」，是**這個數字
  的定義本身就跟 BS 要的東西不同維度**。
- **④–⑧** 因③已判定不適用，不展開；僅供 CME Term SOFR（§3.9 沿用）
  之外，再次確認「免費、免鑰的 SOFR 期限結構」在公開資料裡不存在。

### 3.5 Yahoo Finance ^IRX/^FVX/^TNX/^TYX —— 剔除：主戰場整段落在缺口裡

- **端點**：非官方，`query1.finance.yahoo.com`／`query2.finance.yahoo.com`
  的 chart／quote 端點（`yfinance` 套件即是包這層），本 repo 已在
  `option_chaser/data/yf.py` 用同一家的選擇權鏈端點（作為 Cboe 失敗
  後的備援），故技術上零學習成本。
- **① 機器可讀 API？** 有 JSON 回應，但**無官方文件**——Yahoo 從未
  公開這是給第三方消費的 API，純粹是網站前端呼叫的內部端點，`yfinance`
  等套件靠逆向工程使用。
- **② API key？** 不需要。
- **③ 期限覆蓋——判定剔除的直接原因**：四個指數對應 13 週 T-bill、
  5 年、10 年、30 年（Yahoo 商品頁自述，https://finance.yahoo.com/quote/%5ETNX/ ，
  經搜尋索引摘錄，與前次研究交叉確認一致）。**3 個月與 5 年之間完全
  沒有節點**——而本 app 的主戰場（`ratecurve.py` 要的 1M–3Y、
  CLAUDE.md 記錄的 TLT LEAPS 到 2028 情境）**幾乎整段都落在這個缺口
  裡**，用線性插值橫跨 4.75 年會引入遠大於前次研究量化的曲線口徑誤差
  （前次研究 §6 算過的 7.5bp 級誤差是「1Y–3Y 之間」的量級，這裡是
  「3M–5Y」，斜率覆蓋範圍大了近 20 倍，插值誤差不能类比）。
- **④** 即時／盤中更新（Cboe 指數，非延遲報價），但延遲與凍結行為
  未專門查證（非本文重點，因③已判定剔除）。
- **⑤⑥⑦** 無 SLA、非正式端點、`yfinance` 依賴 pandas/numpy——這正是
  `docs/deploy-vercel.md`「為什麼 serverless 上沒有 yfinance」一節
  已經因體積問題拒絕過的同一組套件；若要用，得像 `cboe.py` 一樣
  手刻 stdlib-only 版本，多一份工程量換一個資料本身就不合用的來源，
  不划算。
- **⑧** 因③已判定剔除，不展開。

### 3.6 Alpha Vantage `TREASURY_YIELD` —— 剔除：缺鍵節點＋配額衝突

- **端點**：`https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=daily&maturity={M}&apikey={KEY}`
  （官方文件 https://www.alphavantage.co/documentation/#treasury-yield ）。
- **① 機器可讀 API？** 是，正式文件化，JSON/CSV 可選。
- **② API key？** 需要；免費自助申請（與本 repo 前次研究討論選擇權
  資料源時已評估過的同一組帳號體系，見
  `docs/research/option-chain-data-sources.md` §3.4）。
- **③ 期限覆蓋——判定剔除的主因之一**：`maturity` 允許值只有
  `3month, 2year, 5year, 7year, 10year, 30year`（官方文件摘錄）——
  **缺 1 個月與 1 年**，1 年正是短天期選擇權情境的關鍵節點；且每個
  maturity 要各打一次，1M–3Y 區間內只覆蓋得到 2 個可用節點（3month、
  2year），插值品質明顯弱於 Treasury／FRED。
- **④** 逐日更新。
- **⑤** 官方產品，多年穩定，未見破壞性改版報告。
- **⑥ 速率限制——判定剔除的另一主因**：免費層 **25 次/日、5 次/分鐘**
  （多份 2026 年來源交叉確認一致，見搜尋結果）。這個配額是**帳號層級
  共用的**，涵蓋 Alpha Vantage 全站所有 function——前次研究
  （`option-chain-data-sources.md` §3.4）已把 Alpha Vantage
  `HISTORICAL_OPTIONS` 列為選擇權鏈的候選備援之一。**若兩邊都採用
  Alpha Vantage，會共搶同一個 25 次/日配額**：光是每次分析要湊出
  3–8 個 maturity 的利率曲線，就可能吃掉大半配額，擠壓到選擇權鏈
  備援可用的次數。這是本文新提出、前次研究未觸及的操作面衝突。
- **⑦** 單次呼叫僅回一個 maturity，需多次呼叫；小型 JSON，
  Vercel 冷啟動無虞，但配額（⑥）才是真正瓶頸。
- **⑧** 因③⑥已判定剔除，不展開。

### 3.7 Financial Modeling Prep `treasury-rates` —— 推薦第三層備援

- **端點**：`https://financialmodelingprep.com/stable/treasury-rates?apikey={KEY}`
  （文件 https://site.financialmodelingprep.com/developer/docs/stable/treasury-rates ，
  舊版 https://site.financialmodelingprep.com/developer/docs/treasury-rates-api ）。
- **① 機器可讀 API？** 是，正式文件化 JSON REST。
- **② API key？** 需要；免費自助申請。
- **③ 期限覆蓋？** **單次呼叫回傳整條曲線**：1 個月、2 個月、3 個月、
  6 個月、1 年、2 年、3 年、5 年、7 年、10 年、20 年、30 年（官方文件
  自述，經搜尋索引摘錄）——與 Treasury CMT 節點數幾乎一致，是本文
  查到「一次呼叫拿全部節點」中覆蓋最完整的一個。
- **④** 逐日更新（EOD／盤後）。
- **⑤ 可靠性？** 這是商業聚合站（非一手監理機關），本身**已知至少
  經歷過一次端點改版**（「Legacy」與「Stable」兩套文件並存，官方自己
  區分新舊版），代表 schema 曾經變過、日後也可能再變——可靠性評級
  低於 Treasury／FRED 這兩個一手來源，屬於「操作方便換來的可靠性
  折扣」，適合當**第三層**而非前兩層。
- **⑥ 速率限制？** 免費層 **250 次/日**（2026 年多份來源一致），對
  「一天可能刷新數次分析」的用量相當寬裕，遠優於 Alpha Vantage 的
  25 次/日。
- **⑦ Vercel 適配度？** 佳——單次 GET、小型 JSON 陣列、無長連線需求。
- **⑧ 備援相容性？** 欄位是 `financialmodelingprep.com` 自訂命名
  （如 `month1`／`year2`／`year10` 一類鍵名，**確切鍵名未逐一開啟
  官方回應範例核對**，列入 §7），與 Treasury CSV 表頭（`"1 Mo"`）／
  FRED（`DGS1`）三套命名互不相同，需要各自獨立的 mapping 層——但
  這本來就是「新增一個 adapter」該做的事，成本可控，不因此排除。

### 3.8 Massive／Polygon.io Treasury Yields —— 不建議：付費且與需求不成比例

- **端點**：`https://massive.com/docs/rest/economy/treasury-yields`
  （原 Polygon.io，已更名 Massive；前次研究已評估過同家供應商的
  選擇權鏈 Starter 方案 US$29/月，見 `option-chain-data-sources.md` §3.5）。
- 單次 GET 回傳完整 1 個月至 30 年曲線、歷史回溯至 1962 年
  （官方文件自述，搜尋索引摘錄）；欄位／分層（是否含在免費層、
  Starter 層、抑或更高階的 Economy 加購包）**未能查證**，列入 §7。
- **判定**：即使欄位規格看起來完整，**付費解一個「政府本來就免費
  公開」的問題不成比例**——除非本 app 未來因為選擇權鏈的緣故已經
  訂閱 Massive Starter（前次研究把它列為 Cboe/yfinance 都失效時的
  付費保底），屆時 Treasury Yields 若剛好包含在同一份訂閱裡，才值得
  當「反正都付錢了」的加分項；不構成獨立訂閱的理由。

### 3.9 CME Term SOFR —— 剔除（沿用前次研究已驗證的結論）

授權不可行：再散布與用於估值定價皆須向 CME 簽署 Use License／ILA
（https://www.cmegroup.com/market-data/files/term-sofr-data-license-faq.pdf 、
https://www.cmegroup.com/articles/faqs/cme-term-sofr-reference-rates.html ，
前次研究 §3.1 已驗證，本文不重新查證，直接沿用）。對免費工具不可行，
與 §3.4 NY Fed SOFR 一併說明「SOFR 期限結構在公開免費資料裡不存在」
這個結論的完整性。

## 4. 對照表

| 來源 | ①機器可讀API | ②需要金鑰 | ③期限覆蓋（1M–3Y內節點數） | ④更新頻率 | ⑤可靠性 | ⑥速率限制 | ⑦單次拿全曲線 | ⑧備援相容成本 |
|---|---|---|---|---|---|---|---|---|
| **Treasury CSV/XML**（現行） | 否，非正式下載端點 | 免鑰 | 最完整，8 節點 | 逐日 | 一手但無SLA、URL已知變過 | 未見文件 | 是（單GET整年份） | 基準 |
| **FRED（官方API）** | 是，文件化 | 免費申請，摩擦低 | 至少6節點（確認）+2節點（推定） | 逐日 | 極強，ALFRED版本追蹤 | 有文件（申請後120/分） | 否（(a)一次一series；(b)便利端點可多series但非正式文件） | 極低（DGS≡CMT同口徑） |
| Fed H.15 直連 | 是，SDMX XML | 免鑰 | 完整（同CMT+FF） | 逐日 | **DDP正在退役中（2026）** | 未見文件 | 是 | 中（SDMX需獨立mapping） |
| NY Fed SOFR | 是，有schema文件 | 免鑰 | **0（僅O/N與回顧平均，最長180天）** | 逐日 | 強（官方文件完整） | 未見文件 | 是 | 不適用——語意不同，非期限結構 |
| Yahoo ^IRX等 | 否，非官方端點 | 免鑰 | **0（3M–5Y整段缺口）** | 即時/盤中 | 無SLA、逆向工程 | 未公布，易限流 | 否（4指數需各自查詢，quote端點可批次） | 低（yf.py既有基礎）但資料本身不合用 |
| Alpha Vantage TREASURY_YIELD | 是，文件化 | 免費申請 | 2節點（缺1M、1Y） | 逐日 | 穩定多年 | **25次/日全站共用，與選擇權備援衝突** | 否（一次一maturity） | 中，但配額是硬瓶頸 |
| Financial Modeling Prep | 是，文件化 | 免費申請 | 完整，約10節點 | 逐日 | 中（商業聚合站，已知改版過一次） | 250次/日，寬裕 | **是（單GET全曲線）** | 中（自訂鍵名，需獨立mapping） |
| Massive/Polygon Treasury Yields | 是，文件化 | 需付費方案 | 完整，回溯至1962 | 逐日 | 商業SLA（未查證細節） | 依方案 | 是 | 低，但**成本不成比例**除非已為選擇權訂閱 |
| CME Term SOFR | 是（授權後） | **需付費授權（ILA）** | 完整期限結構 | 即時 | 商業SLA | 依授權 | 是 | 不可行（授權），僅存參 |

## 5. 推薦順序與理由

1. **Primary：Treasury CSV/XML（現行實作，不動）。** 理由：期限覆蓋
   全場最完整（14 節點對齊本 app 需要的 1M–3Y 區間）、免鑰、零金融
   語意風險（一手官方公有領域資料）、已實作且有測試覆蓋、與本 repo
   既有「免鑰、stdlib GET」的資料源哲學一致（`cboe.py` 同款設計）。
   代價：傳遞管道非正式 API，無 SLA、無速率限制文件——這是**已知、
   可接受**的風險，因為排名（T3 之後）完全不吃 r，r 只影響 heatmap
   到期前格值與 Greeks（前次研究 §7 已量化，本文不重算）。
2. **Fallback #1：FRED（官方 REST API，`api.stlouisfed.org`，免費金鑰）。**
   理由：(a) 資料語意上與 Treasury CMT 幾乎零落差、換源不用碰
   `ratecurve.py` 消費端一行；(b) 網域是 `stlouisfed.org`，與 Treasury
   的 `.gov` 網域走不同基礎設施——若正式環境失敗模式是「擋掉某一類
   政府網域」而非「擋掉所有金融資料網域」，FRED 是真正獨立的備援
   路徑，不是同一套基礎設施換個門面；(c) 有文件化速率限制與版本化
   API，操作可預期性優於 Treasury 自己的頁面。需要一次性申請並管理
   一把 API key（存 Vercel 環境變數），這是唯一的額外摩擦，相對於
   它換來的可靠性與獨立性是合理代價。
3. **Fallback #2：Financial Modeling Prep `treasury-rates`。** 兩個政府
   來源都連不上時的操作層保險——單次 GET 拿到完整曲線、免費層 250
   次/日寬裕、不需要為它另外設計期限對照（覆蓋完整）。可靠性評等
   低於前兩層（商業聚合站、已知改過版），所以放最後一層，不是因為
   資料不夠好，是因為它終究只是 Treasury 數據的轉手包裝，沒有比
   Treasury／FRED 更「正」的理由排到前面。
4. **最終備援：維持現行固定 `0.04`**，並在報告參數行如實標示
   「曲線不可得」（`treasury.py` 既有設計，三層來源全部失敗才會走到
   這裡）。
5. **明確不採用**：NY Fed SOFR、Yahoo Finance 四指數、Alpha Vantage
   `TREASURY_YIELD`、CME Term SOFR、Fed H.15 直連（理由詳 §3.4/3.5/
   3.6/3.9/3.3）；Massive/Polygon 僅在「本 app 未來已為選擇權鏈訂閱
   付費方案」的前提下才值得重新評估（§3.8）。

此排序建立在桌面研究（官方文件＋搜尋索引摘錄）之上，**不是**正式環境
實測結果——§6 的探測程序若在 Vercel 上跑出與本排序矛盾的結果
（例如 Treasury 真的被檔在 Vercel 出口但 FRED 沒有，或反過來），
**以探測結果為準**，直接調整 primary/fallback 順序，不需要回來重新
論證一次。

## 6. 正式環境連通性探測程序（供後續票在 Vercel 上實際執行）

沙箱做不到這件事（§0 已說明原因）；以下是可以直接照做的清單，設計
成一次性腳本或臨時 debug 端點，部署到 Vercel 後手動觸發一次，把
每一步的原始回應（狀態碼、`Content-Type`、前 200 bytes body）記錄
下來即完成。

### 6.1 前置

- FRED：先到 `https://fredaccount.stlouisfed.org/` 申請免費 API key
  （§3.2 已確認免費、即時啟用），存成 Vercel 環境變數
  （例如 `FRED_API_KEY`）。
- Financial Modeling Prep：同樣先申請免費 key，存成
  `FMP_API_KEY`。
- 建議在既有 `api_app/` 底下開一個**臨時**探測端點（或直接寫一支
  一次性腳本在 Vercel 的 dev/preview 環境跑），對外只回傳每個目標
  URL 的探測結果 JSON，探測完就整個刪掉——不要把它留在正式 API 面上。

### 6.2 逐來源探測步驟與判定標準

| 順序 | 來源 | 探測 URL | 檢查什麼 | PASS 標準 | FAIL 標準 |
|---|---|---|---|---|---|
| 1 | Treasury CSV | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&_format=csv` | 狀態碼、`Content-Type`、body 是否以 `Date,` 開頭且含 `"1 Yr"`/`"2 Yr"` 欄 | 200＋`text/csv`或`text/plain`＋表頭含目標欄位＋最新列日期在近 5 個日曆日內 | 403/超時/連線失敗（記下是哪一種）、或表頭欄位對不上（端點已改版） |
| 2 | Treasury XML（CSV 失敗才測） | `…/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026` | 同上，改檢查 `NEW_DATE`／`BC_2YEAR` 元素 | 200＋可解析 XML＋至少一個 entry 含 `BC_2YEAR` | 同上 |
| 3 | FRED 官方 API | `https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key={KEY}&file_type=json&sort_order=desc&limit=1` | 狀態碼、`Content-Type: application/json`、`observations[0].value`／`observations[0].date` | 200＋JSON＋`value` 可解析成 0–20 之間的浮點數＋`date` 在近 5 個日曆日內 | 403/超時、或 `value` 是字串 `"."`（FRED 缺值標記，代表當天無資料，需重試前一交易日） |
| 4 | FRED `fredgraph.csv`（備用路徑） | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS1MO,DGS3MO,DGS6MO,DGS1,DGS2,DGS3` | 表頭是否為 `DATE,DGS1MO,DGS3MO,...`、最新列是否可解析 | 200＋`text/csv`＋表頭符合＋值可解析 | 403/超時、或表頭欄位順序與請求的 `id` 不一致（代表端點行為已變） |
| 5 | Financial Modeling Prep | `https://financialmodelingprep.com/stable/treasury-rates?apikey={KEY}` | 狀態碼、JSON 陣列第一筆是否含 `month1`／`year2`／`year10` 一類鍵、日期新鮮度 | 200＋JSON 陣列＋可辨識的期限鍵名＋日期在近 5 個日曆日內 | 403/超時、或鍵名與預期不符（先用一次真實回應確認 §3.7 標記「未逐一核對」的鍵名，再寫死解析器） |
| 6（次要，僅供佐證，不影響排序） | NY Fed SOFR | `https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json` | 狀態碼、JSON 結構 | 僅確認「連得到」，不代表要採用（§3.4 已判定不適用） | — |

### 6.3 執行紀律

- **每個 URL 至少測兩次**：一次在平日盤中／盤後，一次在週末或假日
  ——用來確認「假日該端點是回舊資料還是回錯誤」，比照本 repo
  `cboe.py` 對盤外行為的既有驗證慣例（FB3-01／#44 的需求方實測
  紀錄）。
- **把原始回應存下來**（狀態碼＋前 200 bytes body＋`Content-Type`），
  不要只記「成功/失敗」——如果將來端點行為變了，有原始樣本才能
  比對是哪裡變了。
- **結果寫回本文件或另開一個帶日期的追記章節**（依本 repo研究文件
  慣例，比照 `docs/research/risk-free-rate-for-bs.md` 那樣的「取材
  限制聲明」寫法，把「探測於 Vercel 實測」與「桌面研究、未實測」
  清楚分開標註）。
- **若探測結果與 §5 排序矛盾，以探測結果為準**——例如 Treasury 兩條
  路徑（CSV/XML）都在 Vercel 出口被擋，但 FRED 通，那就直接把 FRED
  升為 primary，不需要再開一次研究票論證「為什麼」。

## 6.4 追記：Vercel 正式環境實測結果（2026-08-05，issue #74）

**探測方式**：在需求方的 Vercel 帳號下建立一個用完即丟的臨時專案
（`option-chaser-rate-probe`，跟正式 `option-chaser` 專案完全分開部署），
單一 Python serverless function 直接對候選來源打 GET，回傳狀態碼、
`Content-Type`、前 500–6000 bytes body。探測後這個臨時專案本身應
從 Vercel 帳號移除（本輪工具沒有刪除專案的操作可用，留待需求方
手動清掉）。**只測了一輪**（工作階段內），不是 §6.3 建議的「平日
＋假日各一次」——2026-08-05（週三）美股交易日盤後測的，還沒有跨
假日驗證「盤後／假日該端點是回舊資料還是回錯誤」，這點列為本追記
自己的取材限制。

**結果**：

| 來源 | 結果 | 細節 |
|---|---|---|
| **Treasury CSV**（`home.treasury.gov`，主源） | ✅ 通 | 200、`Content-Type: text/csv; charset=UTF-8`，拿到真實資料（`08/04/2026,3.78,3.80,...`），已存成 `tests/fixtures/treasury_csv_sample.txt` |
| **Treasury XML**（備援端點） | ✅ 通 | 200、`Content-Type: text/xml; charset=UTF-8`，拿到完整 entry，已存成 `tests/fixtures/treasury_xml_sample.txt` |
| **FRED 免鑰 `fredgraph.csv`** | ❌ **逢時** | 兩次獨立測試皆逢時（15 秒與 25 秒逾時皆同），與 §5 原排序「FRED 為第一備援」的**假設路徑**矛盾 |
| **FRED 官方 keyed API**（`api.stlouisfed.org`，不同子網域） | ✅ 通（缺 key） | 200 級網路連線正常，回 `400 Bad Request: Variable api_key is not set`——證明**網域本身**沒被擋，逢時的只有 `fred.stlouisfed.org` 這個便利端點 |
| **Financial Modeling Prep**（`financialmodelingprep.com`） | ✅ 通（缺 key） | 回 `401 Invalid API KEY`——網路連通，純粹缺金鑰 |
| **Yahoo Finance ^IRX/^FVX/^TNX/^TYX**（需求方提議，免鑰） | ✅ 通、但涵蓋不足 | 200、拿到即時報價（13 週 3.725%／5 年 4.324%／10 年 4.617%／30 年 5.174%），確認 §3.5 的缺口判斷：拿同一天 Treasury 真實資料回頭比對，內插 1–3 年期的誤差約 18–25 個基點，約為本 repo 既有可接受插值誤差門檻（7.5bp）的 3 倍，本 app 主戰場（1M–3Y）品質不足 |

**與 §5 排序的關係——結論修正**：

1. **Primary 維持 Treasury（CSV／XML），此點與 §5 一致，探測確認無誤**——
   已完成硬化（狀態碼檢查、瀏覽器等級標頭、真實回歸樣本、分來源分
   階段的失敗訊息），見 `option_chaser/data/treasury.py`（issue #74）。
2. **§5 排序的「Fallback #1：FRED 免鑰路徑」被探測結果推翻**——
   免鑰 `fredgraph.csv` 端點本身連不上（不是網域被擋，是這個便利
   端點本身的問題，官方 keyed API 網域是通的）。**探測結果推翻桌面
   研究此處的排序**，依 §6.3「若探測結果與 §5 排序矛盾，以探測結果
   為準」處理。
3. **FRED keyed API／Financial Modeling Prep 皆確認網路可達，但需要
   金鑰**——本輪範圍內沒有金鑰（需求方裁示：先不申請，可接受
   fallback 鏈只有 Treasury→固定 4% 這一種深度），**未在這輪實作**，
   純粹是「還沒去申請」，不是技術上不可行。之後拿到金鑰，直接在
   `default_rate_curve_loader` 前面接一個新 adapter 即可（介面已是
   可替換的 `RateCurveLoader`）。
4. **需求方提議的 Yahoo Finance 免鑰指數，此輪用真實資料重新驗證，
   結論與 §3.5 桌面研究一致（不採用）**——不是因為「難申請」或
   「不夠公開」，是涵蓋範圍本身不夠（3 個月與 5 年之間無節點），
   拿同一天的真實資料實際算過插值誤差，量化後排除。
5. **最終 fallback 鏈（本輪落地版本）**：Treasury（CSV→XML→前一年
   CSV）→ 本地／Neon 陳舊窗快取 → 固定 4%。與 §5 原排序的差異只在
   於「中間那一到兩層目前是空的」，不是 Treasury 這一層本身有問題。

## 7. 取材限制（未能查證事項清單）

- 本文所有標「經搜尋索引摘錄」的內容，均來自搜尋引擎索引到的官方
  文件頁節錄或第三方逐欄位轉述，**未能在本環境直接開啟原始頁面
  逐字核對**（§0 已說明是本沙箱出口政策封鎖，非目的站問題）。
- Treasury CSV/XML 端點的**確切發布時間**（當日晚間 vs. 次一營業日）
  未能查證。
- FRED 無金鑰時的速率限制數字（「30 次/分鐘」）僅見於單一二手來源，
  **未能在官方文件逐字核對**；有金鑰後的「120 次/分鐘」同樣是搜尋
  索引轉述，未逐字核對官方文件原文。
- `DGS2MO`／`DGS4MO` 這兩個 FRED series 是否確實存在、起始日期、
  是否仍在維護，僅間接見於搜尋結果的「相關系列」提及，**未逐一開啟
  系列頁核對**。
- Financial Modeling Prep `treasury-rates` 回應的**確切 JSON 鍵名**
  （如 `month1`／`year2` 是否為真實欄位名）未能取得一份真實回應樣本
  核對，僅為官方文件敘述的搜尋索引轉寫。
- Massive/Polygon Treasury Yields 端點屬於免費層、Starter 層、還是
  更高階 Economy 加購包，**未能查證**。
- Fed H.15 DDP 退役公告的**確切原文**（時間點、影響範圍是否僅止於
  「Build Your Package」選項或整個 DDP）僅為搜尋索引轉述，多組獨立
  查詢結果方向一致，但未逐字核對 `federalreserve.gov` 官方公告原文。
- NY Fed Markets Data API 的完整 schema 規格文件
  （`apps.newyorkfed.org/~/media/XML/Schemas/api_spec`）未能直接開啟，
  內容為官方頁面自述的搜尋索引轉寫。
- 所有候選來源在 Vercel serverless 實際出口環境下的**真實可及性**
  ——本文完全未能驗證（也不該由這個沙箱驗證），這正是 §6 探測程序
  存在的理由。

## 8. 引用清單

一手官方（多數被本沙箱 403 擋下，內容為搜尋索引摘錄，見 §7）：

- https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026 —— CMT 節點清單、CSV/XML 下載入口
- https://home.treasury.gov/treasury-daily-interest-rate-xml-feed —— XML feed 說明頁
- https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology —— 報價取得時間、monotone convex 方法論
- https://fiscaldata.treasury.gov/api-documentation/ —— Fiscal Data REST API 官方文件（base URL、格式、查詢參數）
- https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/ —— 確認 Fiscal Data 裡「平均利率」資料集與殖利率曲線是兩回事
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html 、 https://fred.stlouisfed.org/docs/api/api_key.html 、 https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html —— FRED 官方 API 文件、金鑰申請、v2 端點
- https://fred.stlouisfed.org/series/DGS1 、DGS2、DGS5、DGS10、DGS20、DGS30、DGS1MO 、DGS3MO —— DGS 系列頁
- https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html —— ALFRED vintage／修訂歷史機制
- https://www.federalreserve.gov/feeds/h15.xml 、 https://www.federalreserve.gov/feeds/datadownload.xml 、 https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15 、 https://www.federalreserve.gov/datadownload/help/default.htm —— H.15 XML feed 與 DDP 退役公告
- https://www.newyorkfed.org/markets/reference-rates 、 https://www.newyorkfed.org/markets/reference-rates/sofr-averages-and-index 、 https://apps.newyorkfed.org/~/media/XML/Schemas/api_spec —— NY Fed SOFR 資料頁與 API schema
- https://www.alphavantage.co/documentation/#treasury-yield —— TREASURY_YIELD 官方文件
- https://site.financialmodelingprep.com/developer/docs/stable/treasury-rates 、 https://site.financialmodelingprep.com/developer/docs/treasury-rates-api —— FMP Treasury Rates 新舊版文件
- https://massive.com/docs/rest/economy/treasury-yields —— Massive/Polygon Treasury Yields 端點文件
- https://www.cmegroup.com/market-data/files/term-sofr-data-license-faq.pdf 、 https://www.cmegroup.com/articles/faqs/cme-term-sofr-reference-rates.html —— CME Term SOFR 授權限制（沿用前次研究）

二手／第三方轉述：

- https://ivo-welch.org/professional/fredcsv.html —— `fredgraph.csv` 多 series 慣例用法
- https://github.com/mortada/fredapi —— ALFRED vintage 概念說明
- https://finance.yahoo.com/quote/%5ETNX/ —— ^TNX 等指數定義
- 多份 2026 年 API 評測部落格（Alpha Vantage／FMP 速率限制與定價，
  查詢語句與命中頁面見前述各節，未逐一列出因屬同質重複來源）

本 repo：

- `option_chaser/data/treasury.py`、`option_chaser/ratecurve.py` —— 現行 Treasury 實作
- `option_chaser/data/cboe.py` —— 同款 stdlib-only adapter 設計慣例
- `docs/deploy-vercel.md`「serverless 唯讀」「為什麼 serverless 上沒有
  yfinance」兩節 —— Vercel 環境限制與既有資料源決策脈絡
- `docs/research/risk-free-rate-for-bs.md` —— BS r 的理論口徑研究（本文的分工對照，§1 已說明）
- `docs/research/option-chain-data-sources.md` —— Alpha Vantage／Massive
  作為選擇權鏈備援的既有評估，本文 §3.6/3.8 據此指出配額共用與訂閱
  重複的操作面問題
