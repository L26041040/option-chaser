# 免費（US$0）個別分析師目標價＋歷史資料源：能不能餵 Consensus Gate

研究日期：2026-11-19（以下時間若未註明，皆指本日查得；外部工具回傳的
UTC 時間已換算為台灣時間）。前一份研究：
`docs/research/analyst-price-target-data-sources.md`（2026-11-18，付費路線；
本文不重查付費 vendor）。對應功能：`docs/spec/options-scanner/01-design.md`
的 Consensus Gate（Target Dispersion `D = σ_TP / TP_mean` ＋ 自身歷史
Dispersion Percentile）。

**預算前提**：新外部資料服務預算 **US$0**。本研究**沒有**註冊任何帳號、
沒有申請或使用任何 API key、沒有開試用、沒有購買任何東西，也沒有呼叫
本專案的任何 production 系統。

**查證標記（全文每一項主張都帶其中一個）**

- 【原件】＝當日直接讀到一手來源：vendor 自己的文件／條款原文，或開源
  函式庫原始碼與其**錄下的真實 HTTP 回應 fixture**（verified-from-primary-source）。
- 【轉述】＝搜尋引擎摘要、第三方文章、社群 issue／PR、或前一份研究的
  結論而本日未能重新讀到原件（secondary）。
- 【未查證】＝沒有找到可核對的來源（unverified）。
- 另有少數【推論】＝由【原件】資料推得的判斷，不是 vendor 的陳述。

**取材限制聲明**

- **Yahoo 與 Nasdaq 的端點本次都沒有直接呼叫**：兩者都是沒有公開文件的
  網站內部端點，不屬於「公開文件明示可免鑰呼叫」的範圍。Yahoo 的欄位、
  歷史深度與覆蓋改用開源函式庫 `node-yahoo-finance2` 版本庫內**錄下的
  真實 Yahoo 回應**（測試 fixture，錄於 2026-05-29 18:30（台灣））做分析，
  這是本文最主要的實證來源。
- 唯一實際打過的資料端點：Alpha Vantage 官方文件的 `apikey=demo` 範例
  （`OVERVIEW&symbol=IBM`）。
- 抓不到的頁面（相關主張一律降為【轉述】或【未查證】）：
  - `site.financialmodelingprep.com` 全站（文件、定價、條款）→ CloudFront
    HTTP 403。前一份研究（2026-11-18）當時讀得到，FMP 的主張沿用該份的
    【原件】結論，本文標為【轉述：前次研究原件】。
  - `www.nasdaq.com`（條款、price-target 頁）→ 503／逾時。
  - `www.tipranks.com`、`www.marketbeat.com` → 403（bot 防護）。

## 1. 結論摘要（先行）

- **(a) 有，而且只有一個**：免費來源裡，唯一能拿到**逐券商目標價＋日期
  ＋券商身分＋多年歷史**的是 **Yahoo Finance quoteSummary 的
  `upgradeDowngradeHistory` 模組**。每列有 `epochGradeDate`、`firm`、
  `toGrade`、`fromGrade`、`action`、`priceTargetAction`、
  `currentPriceTarget`、`priorPriceTarget`。【原件：yahoo-finance2 型別定義＋
  真實回應 fixture】以 2026-05-29 錄下的回應為例：AAPL 968 列／59 家券商、
  CRM 919 列／84 家、AMZN 990 列／63 家，約 95% 的列帶非零目標價。【原件】
  可以從「每家券商最近一筆、12 個月內」重建當日有效集合，算 mean、stdev、
  `D`，並往回逐月重建 `D_t`。
- **但它有四個硬傷**，都會直接影響 Gate 的數字（詳 §4.1）：
  1. **目標價沒有做 split 調整**：AMZN 2022、GOOG 2022、AAPL 2020 分割前後
     的目標價混在一起，跨分割月份的 `D_t` 會爆到 1–2 以上。必須自己用
     split 日曆做調整。【原件】
  2. **歷史長度上限約 1,000 列**：被大量覆蓋的股票會被截斷。AAPL 的資料
     實際只回到 2018-02（另有一筆孤立的 2012 年資料），AMZN 只回到
     2019-10。被覆蓋較少的股票可以回到 2012–2014 年。【原件／推論】
  3. **覆蓋不完整**：只有發布過評等或目標價動作的券商才會出現，而且沒有
     「終止覆蓋」事件。以 2025-02-24 為基準，重建的 12 個月有效集合人數
     只有 Yahoo 自家共識人數（`numberOfAnalystOpinions`）的約 63–78%
     （AAPL 31／40、AMZN 43／63、CRM 37／47）；ADR 更差（BABA 13／39）。【原件】
  4. **只有券商名稱字串**：沒有券商 ID，也沒有分析師姓名。券商改名或合併
     （Cowen & Co.→TD Cowen、SunTrust→Truist）會讓同一家變成兩家。【原件】
- **其他免費來源都拿不到個別目標價**：
  - FMP 免費層只有 summary／consensus；個別目標價端點
    （`price-target-news`）是付費。【轉述】
  - Finnhub 免費層的分析師目標價端點全部標「Premium」，免費只剩
    recommendation trends。【原件】
  - Nasdaq `api/analyst/{sym}/targetprice` 只有共識概覽。【轉述】
  - Alpha Vantage 只有 `AnalystTargetPrice`（一個平均值）。【原件】
  - Twelve Data 的分析師端點只開放 Ultra 以上。【原件】
  - EODHD 免費層每日 20 次，只有平均目標價。【原件／轉述】
  - Massive 的 Benzinga 是每個資料集 US$99/月。【原件】
  - SEC EDGAR 沒有分析師目標價。【未查證，通則】
- **(b) 顯示授權：沒有任何一個免費來源允許把資料或衍生值（mean、`D`、
  pass/fail）顯示給公開網站的使用者。** 說清楚：
  - Yahoo 條款明文禁止自動化擷取、任何商業目的的使用，以及未經書面許可
    的散布或製作衍生作品。【原件】
  - Finnhub 明文禁止分享「derived results」。【原件】
  - FMP 明文禁止未簽約的 display，而且涵蓋「derived from the Services」的
    資訊。【轉述：前次研究原件】
  - Alpha Vantage 免費層排除「讓 User 以外的人直接或間接取得資訊」的用法。
    【原件：repo 既有研究】
  - Zacks、Dow Jones（MarketWatch／WSJ）、StockAnalysis 的條款都明文禁止
    爬取。【原件】

  US$0 預算下，**合法的公開顯示路徑不存在**；免費路線只能用在 Owner
  私下的離線研究與驗證。這一點的條款解釋本身也有灰色地帶，不構成法律
  意見。
- **(c) 覆蓋缺口要寫進設計**：Yahoo 只在券商「發布評等或目標價動作」時
  記一筆。在視窗內沒動作的券商會缺席，撤回覆蓋的券商又不會消失，直到
  視窗到期。所以「目前有效」的集合**既缺人、又可能含過期的人**，用它算
  的 stdev 有雙向偏差。
- **最佳免費路徑（僅限離線研究）**：用 Yahoo `upgradeDowngradeHistory`
  做 50 檔的回溯驗證。需要自己做 split 調整、合併券商名稱、套 12 個月
  有效期。股價可以用同一個 Yahoo chart 端點（repo 的 `dividends.py` 已在用，
  但同樣受 Yahoo 條款限制）。
  - 每檔 1 次呼叫，但每檔回應約 30–185 KB（緊湊 JSON）。【原件】
  - 需要 cookie＋crumb 兩步驟。【原件：yfinance 原始碼】
  - 純 stdlib `urllib` 做得到，但 yfinance 自己警告：沒有瀏覽器 TLS 指紋的
    client 可能被限流或擋下。【原件】

## 2. 需求對照：Gate 需要的三樣東西

| 需求 | 需要的資料 | 免費來源能否滿足 |
|---|---|---|
| ① 當日 `TP_mean`、`σ_TP`、`D` | 每家券商一筆「目前有效」的目標價、日期、身分 | 只有 Yahoo `upgradeDowngradeHistory`（有覆蓋缺口）【原件】 |
| ② 自身歷史 `D_t`（月頻、數年） | 個別目標價事件史，或現成含 stdev 的共識序列 | Yahoo 事件史可重建，但有 split 與約 1,000 列上限問題；沒有任何免費來源提供現成 stdev 序列【原件】 |
| ③ 驗證：12 個月內股價是否觸及 mean target | ② 的歷史 mean ＋日線高價（含 split） | Yahoo chart（非正式）或 Stooq（非正式）；兩者條款都不允許公開顯示【轉述／原件】 |
| 授權 | 對公開匿名使用者顯示衍生值 | **全部不行**（§1(b)） |

## 3. 總覽比較表

（「個別」＝逐券商或逐分析師的目標價；「500 檔／日」＝每日更新 500 檔
所需的呼叫數與能否塞進免費額度；「stdlib」＝能否只用 Python stdlib
`urllib`、不用 pandas，在 serverless 上取得）

| 來源 | 個別目標價 | 欄位 | 歷史深度 | 免費額度／500 檔／日 | stdlib | 公開顯示授權 | 穩定性 |
|---|---|---|---|---|---|---|---|
| **Yahoo `upgradeDowngradeHistory`** | ✅ 逐券商【原件】 | `epochGradeDate`、`firm`、`toGrade`、`fromGrade`、`action`、`priceTargetAction`、`currentPriceTarget`、`priorPriceTarget`【原件】 | 少覆蓋的股票可到 2012–2014；大型熱門股被約 1,000 列上限截到 2018–2019【原件／推論】 | 無公開額度；500 次＋2 次 cookie／crumb；每日約 50–90 MB【原件／推論】 | ✅ 需 cookie＋crumb；TLS 指紋風險【原件】 | ❌ 條款禁止自動化、商業、散布與衍生作品【原件】 | 非正式、無文件、無 SLA |
| Yahoo `financialData` | ❌ 只有共識【原件】 | `targetMean/High/Low/MedianPrice`、`numberOfAnalystOpinions`、`recommendationMean`【原件】 | 只有現值【原件】 | 可與上一列同一次呼叫取得【原件】 | ✅ 同上 | ❌ 同上 | 同上 |
| FMP 免費（Basic） | ❌（個別端點 `price-target-news` 為付費）【轉述】 | summary：期間平均＋筆數；consensus：high／low／median／consensus【轉述：前次研究原件】 | summary 到「all time」平均，非序列【轉述】 | 250 次／日；price target 類只限約 87 檔指定 symbol【轉述：前次研究原件】→ 500 檔不可行 | ✅（repo 已用） | ❌ 禁止 display，含衍生資訊【轉述：前次研究原件】 | 正式 API |
| Nasdaq `api/analyst/{sym}/targetprice` | ❌ 共識概覽【轉述】 | `consensusOverview`（`priceTarget`、high／low、買賣持有數）＋疑似共識歷史【轉述】 | 【未查證】 | 無公開額度【未查證】 | ✅（repo 已用 Nasdaq 股利端點） | ❌ 網站條款限個人非商業【轉述】 | 非正式、無文件 |
| Finnhub 免費 | ❌【原件】 | 免費只有 `/stock/recommendation`（評等人數）；`price-target`、`historical-price-target`、`upgrade-downgrade` 都標 Premium【原件】 | — | 60 次／分（free）【轉述】 | ✅ | ❌ 禁止分享 data 與 derived results；所有方案限個人【原件】 | 正式 API |
| Alpha Vantage 免費 | ❌【原件】 | `OVERVIEW.AnalystTargetPrice`＋五級評等人數【原件：demo 回應】 | 只有現值 | 25 次／日【原件】→ 500 檔不可行 | ✅ | ❌ 商業使用定義排除【原件：repo 既有研究】 | 正式 API |
| Twelve Data Basic | ❌（分析師端點限 Ultra／Enterprise）【原件】 | — | — | Basic 8 credits／分（800／日）【原件】 | — | ❌ | 正式 API |
| EODHD 免費 | ❌ 只有 `WallStreetTargetPrice`【轉述：前次研究原件】 | — | — | 20 次／日；部分資料類型免費層不可用【原件】 | — | ❌ 分個人與商業方案【原件】 | 正式 API |
| Massive（Polygon）免費 | ❌ Benzinga 是付費 partner data【原件】 | — | — | US$99/月／資料集【原件】 | — | ❌ 免費／個人層限個人非商業【原件：repo 既有研究】 | 正式 API |
| Benzinga 免費／developer | 【未查證】（只知道有試用，試用被預算排除） | — | — | — | — | — | — |
| Tiingo 免費 | ❌ 定價頁沒有分析師資料產品【原件】 | — | — | — | — | — | — |
| SEC EDGAR | ❌ 申報資料庫，不含賣方報告【未查證，通則】 | — | — | — | — | — | — |
| Zacks／MarketWatch／WSJ／StockAnalysis／MarketBeat／TipRanks 網站 | 網站上看得到（部分） | — | — | — | — | ❌ 條款禁止爬取（Zacks、Dow Jones、StockAnalysis【原件】；MarketBeat、TipRanks 403【未查證】） | **不建議、本次未爬** |

## 4. 逐源說明

### 4.1 Yahoo Finance quoteSummary `upgradeDowngradeHistory`（唯一可用的免費個別來源）

**端點與取得方式**【原件：yfinance `main` 分支原始碼，2026-11-19 抓取】

- `GET https://query2.finance.yahoo.com/v10/finance/quoteSummary/{SYMBOL}?modules=upgradeDowngradeHistory&formatted=false&crumb=…`
  （`yfinance/const.py` `_BASE_URL_`、`yfinance/scrapers/quote.py:43,651-666`）。
  一次可以帶多個 module（例如 `upgradeDowngradeHistory,financialData`），
  省一半呼叫。
- **需要 cookie＋crumb**（`yfinance/data.py:226-280`）：
  1. 先 `GET https://fc.yahoo.com` 取得 cookie。
  2. 再帶 cookie `GET https://query1.finance.yahoo.com/v1/test/getcrumb`
     取得 crumb 字串，回 429 或內容含「Too Many Requests」就視為限流。

  node-yahoo-finance2 錄下的請求 URL 同樣帶 `crumb=` 參數與 `A1`／`A3`
  等 cookie。【原件：fixture】不帶 crumb 會怎樣，本次未測。【未查證】
- **TLS 指紋風險**：yfinance `_http.py` 開頭註明「plain `requests` cannot
  replicate the JA3/JA4 fingerprint and HTTP/2 settings that `curl_cffi`
  provides, so Yahoo Finance may rate-limit or block this client」。【原件】
  stdlib `urllib` 屬於同一類。repo 現有 `dividends.py` 用 `urllib` 打
  Yahoo v8 chart 端點（不需要 crumb）能運作，但 quoteSummary 加
  cookie／crumb 在 Vercel 上的成功率【未查證】。
- **rate limit**：Yahoo 沒有公開額度。yfinance 只對 429 做處理
  （`data.py:274,368,508`）。【原件】實際門檻【未查證】。
- yfinance 的 `Ticker.upgrades_downgrades`（`quote.py:564-583`）把
  `history` 陣列原樣轉成 DataFrame，只改名 5 欄（`epochGradeDate`→
  `GradeDate`、`firm`→`Firm`…），**其餘欄位原樣保留**。所以 Yahoo 回傳的
  目標價欄位會以原名 `currentPriceTarget` 等出現在 DataFrame 中，但
  docstring 仍只寫「firm toGrade fromGrade action」（`base.py:250-256`）。
  【原件】

**欄位**【原件：`node-yahoo-finance2` `src/modules/quoteSummary-iface.ts:1070-1100`，
以及同版本庫 `tests/fixtures/http/quoteSummary-upgradeDowngradeHistory-*.json`】

```
epochGradeDate: Date          // Unix 秒
firm: string                  // 券商名稱字串，例如 "B of A Securities"
toGrade / fromGrade: Grade    // 評等字串
action: "down"|"init"|"main"|"reit"|"up"
priceTargetAction: "Lowers"|"Raises"|"Maintains"|"Announces"|"Adjusts"|""
currentPriceTarget: number    // 0 表示該筆沒有目標價
priorPriceTarget: number      // 0 表示沒有前值
```

實際一列（AAPL，2026-05-26）：`{"epochGradeDate":1779816618,
"firm":"B of A Securities","toGrade":"Buy","fromGrade":"Buy","action":"main",
"priceTargetAction":"Raises","currentPriceTarget":380,"priorPriceTarget":330}`。
【原件：fixture】陣列依時間由新到舊排列。【原件：fixture，8 檔全部成立】

社群用例也印證同一組欄位：GitHub issue 用 yfinance 取 MSFT 約 950 列，並
提到「drop rows without currentPriceTarget」；另一個 PR 提到 AAPL「969
actions with firm, both grades and both targets」。【轉述】

**歷史深度與覆蓋（8 檔真實回應，錄於 2026-05-29 18:30（台灣））**【原件】

| 代號 | 列數 | 最早 | 帶非零目標價 | 券商數 | 各年筆數（12→26） |
|---|---|---|---|---|---|
| AAPL | 968 | 2012-09-12（孤立 1 筆）；連續資料自 2018-02-07 | 948 | 59 | 12:1、13–17:0、18:44、19:103、20:186、21:94、22:86、23:137、24:131、25:144、26:42 |
| AMZN | 990 | 2019-10-25 | 989 | 63 | 19:4、20:128、21:102、22:154、23:173、24:168、25:184、26:77 |
| CRM | 919 | 2012-02-24 | 880 | 84 | 每年 20–146 筆，無斷層 |
| GOOG | 698 | 2012-06-22 | 683 | 73 | 16–19 每年只有 5–9 筆；24–26 也偏少（22、29、12） |
| ABBV | 386 | 2013-03-11 | 353 | 41 | 每年 12–63 筆 |
| BABA | 539 | 2014-09-08 | 517 | 57 | 每年 14–89 筆 |
| SPOT | 450 | 2018-04-03（上市日附近） | 433 | 49 | 每年 24–84 筆 |
| ARMK | 178 | 2014-01-21 | 167 | 22 | 每年 3–29 筆 |

- **約 1,000 列上限**【推論】：AAPL（968）與 AMZN（990）的資料從
  2018-02、2019-10 這種年中突然開始，而覆蓋較少的 CRM、ABBV 可以連續
  回到 2012–2013。最合理的解釋是 Yahoo 只回傳最近約 1,000 筆。對大型
  熱門股，可回溯的連續歷史約 **6–8 年**。
- **GOOG 的斷層**：2016–2019 與 2024 之後每年筆數異常少。可能是同一家
  公司的事件分記在 GOOG 與 GOOGL 兩個代號下。【推論】雙重股權股票要
  兩個代號合併處理。
- **上游可能是 Benzinga**【推論】：券商命名（「B of A Securities」）、
  `priceTargetAction` 的詞彙（Maintains／Raises／Lowers／Announces）與
  Benzinga `action_pt` 的值域相同（Benzinga 文件列「Maintains, Raises,
  Lowers, Announces, Removes」【原件】），最早記錄 2012-02 也接近 Benzinga
  的 2011-12-08 起點。【原件：Massive 文件】Yahoo 沒有公開說明資料供應商。
  【未查證】

**資料品質問題（逐項都會影響 `D`）**【原件：fixture 分析】

1. **未做 split 調整**：
   - AMZN 2022-06-06（20:1）分割前夕的目標價是 3,300–4,185，之後的
     「Adjusts」列才改成 156–200。
   - GOOG 2022-07-18（20:1）同樣如此。
   - AAPL 2020-08-31（4:1）前夕新舊口徑混雜：同一天 Wells Fargo 420、
     Citigroup 112.5。

   `Adjusts` 是部分券商在分割後重新發布的調整列，**不是**對舊資料的回溯
   修正。直接重建的 `D_t` 在跨分割月份爆掉：AMZN 2023-01 的 `D` 為 2.18，
   GOOG 2023-01 為 2.37，AAPL 2020-07 為 0.60。必須用 split 日曆，把分割日
   之前發布的目標價除以分割比例。
2. **`currentPriceTarget = 0` 的列**（每檔 1–39 列）：
   - 純評等動作，例如 Needham 對 AAPL 的「Hold」重申一律沒有目標價。
   - 部分 upgrade 或 init 沒附目標價。

   這些列應排除在目標價集合外，但它們代表「該券商仍在覆蓋」。
3. **沒有終止覆蓋事件**：`action` 只有 down／init／main／reit／up，沒有
   terminate 或 suspend。撤回覆蓋的券商只能靠 12 個月視窗自然淘汰。
4. **只有券商字串，沒有 ID 與分析師**：同一份回應同時出現「Cowen & Co.」
   與「TD Cowen」、「SunTrust Robinson Humphrey」與「Truist Securities」、
   「Credit Suisse」。去重要自建別名表。
5. **同日重複**：每檔有 1–2 組「同券商同一天兩筆」，取時間戳較晚者。
6. **point-in-time 不保證**：這是 Yahoo 今天回傳的事件史，事後有沒有
   補登、改寫或刪除，無從得知。【未查證】

**覆蓋缺口實測：重建集合 vs Yahoo 自家共識（基準日 2025-02-24）**【原件】

`financialData` fixture 錄於 2025-02-24 17:35（台灣）。用 2026-05 的事件史
重建同一天「每家券商最近一筆、365 天內、非零」的集合：

| 代號 | Yahoo 共識 n／mean／high／low | 重建 n／mean／high／low（365 天） | 重建 `D` | 人數覆蓋率 |
|---|---|---|---|---|
| AAPL | 40／252.2／325／197 | 31／243.8／325／160 | 0.165 | 78% |
| AMZN | 63／266.5／306／207 | 43／266.3／306／205 | 0.074 | 68% |
| CRM | 47／394.6／442／247 | 37／376.7／450／236 | 0.151 | 79% |
| ABBV | 26／204.4／239／165 | 18／209.5／239／185 | 0.063 | 69% |
| ARMK | 15／44.3／49／38.43 | 11／43.0／47／39 | 0.070 | 73% |
| GOOG | 18／218.7／235／200 | 15／207.4／240／165 | 0.114 | 83% |
| SPOT | 35／632.5／737／235 | 25／549.8／730／230 | 0.277 | 71% |
| BABA | 39／152.8／191／86 | 13／142.9／190／85 | 0.231 | 33% |

觀察：

- 美國大型股的重建人數約為共識人數的 7–8 成。mean 多半落在 ±5% 內
  （SPOT 差 13%）。high 常一致，low 則常比共識更低，可能是過期目標價
  沒被淘汰。
- 把視窗放寬到 730 天，人數更接近共識，但 `D` 明顯變大（例如 AMZN
  從 0.074 變 0.167）。原因是舊目標價拉開了分散度。有效期規則對 `D` 的
  影響不小。
- Yahoo 共識本身的供應商與口徑【未查證】，不一定和事件史同源。

**重建的 `D_t` 範例**（AAPL，每半年 1 點，365 天視窗，**未做 split 調整**，
僅示範可行性）【原件：fixture 計算】：2019-01 0.259、2020-01 0.352、
**2020-07 0.597、2021-01 0.544（受 2020-08 分割汙染）**、2021-07 0.135、
2022-07 0.085、2023-07 0.131、2024-07 0.132、2025-07 0.150、2026-01 0.136。

**`financialData`（共識，非 stdev）**【原件：yahoo-finance2 iface 與 fixture】
`targetHighPrice`、`targetLowPrice`、`targetMeanPrice`、`targetMedianPrice`、
`numberOfAnalystOpinions`、`recommendationMean`、`recommendationKey`。只有
現值，沒有 stdev，**不可**拿 (high − low) 冒充標準差。yfinance 的
`analyst_price_targets` 取的就是這幾欄。【轉述：前次研究原件】

**呼叫量與 serverless 可行性**

- 500 檔／日：500 次 quoteSummary（兩個 module 合併一次）＋1 次 cookie
  ＋1 次 crumb。【原件：呼叫形狀】
- 沒有日期或增量參數，每次都回傳完整歷史。【原件：yfinance／
  yahoo-finance2 均無此參數】
- 回應大小（緊湊 JSON）：AAPL 約 179 KB、AMZN 約 184 KB、ARMK 約 32 KB。
  【原件】500 檔每日約 50–90 MB 下行流量。【推論】
- 純 stdlib 可行：`urllib.request` ＋ `http.cookiejar` ＋ `json`，不需要
  pandas。【推論】

**條款**【原件：`legal.yahoo.com/us/en/yahoo/terms/otos/index.html`，
Last updated: 1 November 2026】

- 禁止「access or collect data … from our Services using any automated
  means … including … robots, spiders, scrapers, data mining tools … for any
  purpose without our express [written permission]」。
- 「Unless otherwise expressly stated, you may not access or reuse the
  Services, or any portion thereof, for any commercial purpose.」
- 「Unless you have explicit written permission, you must not reproduce,
  modify, rent, lease, sell, trade, distribute, transmit, broadcast, publicly
  perform, **create derivative works based on**, or exploit for any commercial
  purposes, any portion or use of, or access to, the Services (including
  content, … APIs …)」。
- 禁止建立與「data offered by Yahoo or our data providers」競爭或可替代的
  資料庫或資料源。
- yfinance README：「the Yahoo! finance API is intended for personal use
  only」，並說它「not affiliated, endorsed, or vetted by Yahoo」。【原件】

→ 在公開網站顯示 mean、`D`、pass/fail，屬於「散布」與「基於內容製作
衍生作品」。條款沒有為衍生值另開例外。**不可公開顯示。** repo 既有研究
`public-beta-market-data-source-selection.md` 對 Yahoo 股利抓取也是同一結論。
【原件：repo 既有研究】

### 4.2 FMP 免費層（Basic）

本日 FMP 網站全站被 CloudFront 擋下（403），以下沿用前一份研究
（2026-11-18）讀到的原件結論，以及本日的搜尋摘要。

- **額度**：250 calls／日。【轉述：前次研究原件；FMP 自家頁面的搜尋摘要
  亦同】30 天滾動頻寬 500 MB、歷史約 5 年、僅 EOD。【轉述】
- **symbol 限制**：price target 類端點在免費層只限約 87 檔指定 symbol。
  【轉述：前次研究原件】→ 500 檔不可行，50 檔驗證能否全落在名單內
  【未查證】。
- **分析師端點**：
  - stable 文件的 Analyst 類有 `price-target-summary`（上月、上季、去年、
    全期的平均目標價與筆數）、`price-target-consensus`（high、low、
    median、consensus）、`grades` 系列。【轉述：前次研究原件】
  - **免費能拿到的都沒有個別目標價、沒有 stdev**。
  - `grades` 是逐券商評等變動，不含目標價。【轉述】
  - 搜尋結果裡沒有 `grades-historical`；FMP 有 `ratings-historical`，那是
    FMP 自家的評分，不是賣方評等。【轉述】
- **個別目標價**：
  - `stable/price-target-news`（含 `analystName`、`analystCompany`、
    `priceTarget`、`priceWhenPosted`、`publishedDate`）與
    `price-target-latest-news` 的文件頁本日出現在搜尋索引中（前次研究
    當天 404）。
  - 開源 PowerShell 包裝套件的說明寫「this is a premium endpoint that
    requires a paid subscription」。【轉述】
  - 舊版 `/api/v4/price-target` 是 legacy，只開放給既有付費帳號。【轉述】
  - → **免費層沒有個別目標價**。
- **條款**：§2.2.2 未簽約不得在網站或多人應用程式上 display，不論免費或
  付費。§2.6.1 涵蓋「derived from the Services」的資訊。【轉述：前次研究原件】
  → 不可公開顯示。

### 4.3 Nasdaq（`api.nasdaq.com/api/analyst/{symbol}/…`）

- 路徑：`/api/analyst/{sym}/{earnings-date|earnings-forcast|estimate-momentum|peg-ratio|ratings|targetprice}`。
  這是社群逆向整理的非官方文件（stonkBot `NASDAQ_API_DOC.md`），沒有
  Nasdaq 官方文件。【原件：該 OSS 文件】
- `targetprice` 的回應：第三方範例讀取 `data.consensusOverview`，其中
  `priceTarget` 為平均目標價，另有 high、low 與買賣持有人數。也有包裝
  宣稱提供共識歷史（`consensusHistory`）。【轉述】**沒有任何來源顯示它
  有逐券商目標價。**
- 免鑰：repo 的股利端點以瀏覽器等級 `User-Agent` 與 `Accept` 免鑰取得。
  【原件：`option_chaser/data/dividends.py`】analyst 端點是否同樣可用，
  本次未呼叫。【未查證】
- Nasdaq 官方的分析師目標價產品是 Nasdaq Data Link 的
  `TIPRANKS/ARPT`（付費）。【轉述】
- 條款：nasdaq.com 網站授權為「personal, non-commercial use」。【轉述：
  搜尋摘要；條款頁本日 503】

### 4.4 Finnhub 免費層

【原件：`finnhub.io/static/swagger.json`（文件頁使用的 API 定義）、
`finnhub.io/terms-of-service`】

- `/stock/price-target`：「Get latest price target consensus」，欄位
  `targetHigh`、`targetLow`、`targetMean`、`targetMedian`、`numberAnalysts`、
  `lastUpdated`。**Premium required.**
- `/stock/historical-price-target`：歷史共識。**Premium required.**
- `/stock/upgrade-downgrade`：欄位 `symbol`、`gradeTime`、`fromGrade`、
  `toGrade`、`company`、`action`，**不含目標價**。**Premium Access Required.**
- 免費只剩 `/stock/recommendation`（各評等人數）。
- 限流：文件寫「On top of all plan's limit, there is a 30 API calls/second
  limit」。【原件】免費 60 calls／分是常見轉述，本日定價頁抓不到。【轉述】
- 條款：「You hereby agree to not redistribute or share access to data or
  **derived results** from the data obtained from Finnhub with anyone or any 3rd
  party without written approval」；「All plan listed on Finnhub website is
  strictly for personal use unless explicitly stated otherwise」。

### 4.5 其他有免費層的 vendor

- **Alpha Vantage**【原件】：
  - 免費 25 requests／日（`/support/`、`/premium/`）。
  - `OVERVIEW` 只有 `AnalystTargetPrice` 與 `AnalystRatingStrongBuy…StrongSell`。
    本日 demo 回應：IBM `AnalystTargetPrice: 259.85`，評等人數 3／9／11／1／1。
  - 文件中與 analyst 相關的只有 EPS 與營收預估。
  - 條款排除「allows individuals or entities other than User to access
    information directly or indirectly」的商業用途。【原件：repo 既有研究
    `public-beta-market-data-source-selection.md` §3.3】
- **Twelve Data**【原件：`twelvedata.com/pricing`、`docs/llms/analysis/*.md`】：
  - Basic $0，8 credits／分（800／日）。
  - `price_target`、`analyst_ratings/light` 標「available on the Ultra plan
    (individual) and the Enterprise plan (business) and above」。
  - 免費層不可用。
- **EODHD**【原件：`eodhd.com/pricing`】：
  - 「Once you register you get 20 free API calls per day. Some data types are
    not accessible on the free package.」
  - 分析師資料只有平均目標價 `WallStreetTargetPrice`。【轉述：前次研究原件】
- **Massive（Polygon）**【原件：`massive.com/pricing`、Benzinga analyst-ratings 文件】：
  - Benzinga Analyst Ratings 是「$99 /month per dataset」的 partner data，
    免費層沒有。
- **Benzinga 直購**：只知道有試用方案，被預算排除。免費 developer
  方案是否存在【未查證】（benzinga.com 前次研究即 403）。
- **Tiingo**：定價頁沒有分析師相關字樣。【原件】
- **SEC EDGAR**：只收發行人與相關人申報，賣方分析師報告與目標價不在
  申報範圍。【未查證，通則判斷】

### 4.6 公開網站（只查條款立場，本次未爬）

- **Zacks**【原件：`zacks.com/terms_of_service.php`】：「The use of automated
  systems, tools, or software to collect or extract data from this website, e.g.,
  automated data extraction, crawling, or scraping, is expressly prohibited.」
  另寫明資料僅供「private, non-commercial use」，不得「recirculated,
  redistributed or published」。
- **Dow Jones（MarketWatch、WSJ）**【原件：`dowjones.com/terms-of-use/`】：
  - §9.4.1 不得「display, post, frame, scrape, aggregate」內容。
  - 不得用於「text or data mining」。
  - 並聲明 robots.txt 的設定不擴張使用權。
- **StockAnalysis**【原件：`stockanalysis.com/terms-of-use/`】：「You may not
  use bots, scripts, scrapers, browser automations or any other automated or
  programmatic methods to access the platform, collect data from it, or
  download data in bulk.」
- **MarketBeat、TipRanks**：條款頁 403，【未查證】。前次研究亦確認沒有
  正式免費 API。【轉述】

## 5. 缺口與免費替代路線

### 5.1 能做什麼、不能做什麼

| 用途 | 免費路線可行嗎 | 條件 |
|---|---|---|
| Owner 私下離線研究：50 檔回溯驗證 | **可行**（技術上） | Yahoo 事件史＋自建 split 調整、別名表、有效期；條款上屬灰色（個人研究 vs 自動化擷取禁令），非法律意見 |
| 公開 beta 顯示 Consensus Target、`D`、pass/fail | **不可行** | 所有免費來源條款都不允許（§1(b)） |
| 公開 beta 只在伺服器內部用 Gate 篩選、完全不顯示數值 | **仍不建議** | Yahoo 條款禁止「for any purpose」的自動化擷取與商業使用；篩選結果本身仍是衍生作品的對外呈現【推論】 |

### 5.2 用 Yahoo 歷史自舉（bootstrap）`D_t`

- **第二關**（當日 `D ≤ 10%`）：第一天就能算，但受 §4.1 的覆蓋缺口影響
  （人數約 7–8 成、可能含過期目標價）。
- **第一關**（自身歷史 `D` 百分位 ≤ 20%）：
  - 用 Yahoo 事件史逐月重建，大型熱門股約有 2018–2019 起的 6–8 年，也就是
    約 70–95 個月點。覆蓋較少的股票可以回到 2013–2014。
  - 但月點不是獨立樣本：目標價多在財報季更新，一年約只有 4 個獨立
    資訊週期。6 年約等於 24 個週期，百分位會很粗。【推論；與前次研究
    §5.3 一致】
  - 早年人數太少的月份（例如 GOOG 2017–2019 每月只有 4–6 家）要設最低
    人數門檻，否則 `D` 雜訊很大。【原件：重建結果】
- **驗證研究**（12 個月內股價是否觸及 mean target）：
  - 每個月點的 mean 要先做 split 調整，股價要用同口徑的日線高價。
  - 2019–2025 的月點都已有 12 個月的後續資料，可以立刻離線做完。
  - 風險：Yahoo 事件史不是 point-in-time 快照（可能有事後補登或刪除），
    回測結果可能偏樂觀。【推論】

### 5.3 只靠自存每日快照（沒有可回溯歷史時）要等多久

假設只能取得「今天」的資料，例如只有共識值的來源，或決定不用 Yahoo
的歷史：

- 第二關需要的是當日個別目標價，只有共識的來源（FMP、Nasdaq、Finnhub、
  Alpha Vantage）**永遠算不出 stdev**，存再久也沒用。
- 若每日存 Yahoo 的當日有效集合（不倚賴它的歷史），第一關要累積足夠的
  月點：
  - 12 個月點（1 年）只能做很粗的百分位。
  - 24–36 個月點（2–3 年）才勉強可用。【推論】
- 驗證研究還要再加 12 個月的後續期。
- 結論：**免費路線的價值在 Yahoo 那段可回溯的歷史**。自存快照只換到
  point-in-time 與可稽核，換不到時間。

### 5.4 要上 production 時

前次研究的結論不變：要對公開使用者顯示，就一定要有書面授權，而所有
已知的授權路徑都不是 US$0。免費路線最多能做到「用離線研究證明 Gate
值得付費」，然後再談授權。

## 6. 未能查證的事項

1. **Yahoo 列數上限的確切數字與規則**（約 1,000 列是由 AAPL、AMZN 推得），
   以及是否可用參數取得更多。
2. **Yahoo 事件史的上游供應商**（推論為 Benzinga），以及事件是否會被
   事後改寫、補登或刪除。
3. **Yahoo quoteSummary 在 Vercel 上用 stdlib `urllib`（無 TLS 指紋偽裝）
   的成功率與限流門檻**；不帶 crumb 是否仍可取得。
4. **Yahoo `financialData` 共識的供應商與口徑**，以及它與事件史的
   對應關係。
5. **雙重股權（GOOG／GOOGL）事件分記的實際規則**。
6. **FMP 免費層本日的實際內容**（網站 403）：price target 類的 symbol
   清單（約 87 檔）、`price-target-news` 是否確定為付費。
7. **Nasdaq `targetprice` 的完整回應結構**，以及共識歷史的深度。
8. **Finnhub 免費層 60 calls／分**（定價頁抓不到）。
9. **Benzinga 是否有免費 developer 方案**。
10. **MarketBeat、TipRanks 網站條款原文**（403）。
11. **條款解釋**：「個人離線研究」是否落在 Yahoo 條款「for any purpose
    without our express permission」的禁止範圍內。本文不做法律判斷。

## 7. 來源

一手（【原件】）：

- yfinance 原始碼（`main`，2026-11-19 抓取）：
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/scrapers/quote.py
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/data.py
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/_http.py
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/base.py
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/const.py
  - https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md
- node-yahoo-finance2（`devel`）：
  - 型別：https://raw.githubusercontent.com/gadicc/node-yahoo-finance2/devel/src/modules/quoteSummary-iface.ts
  - 錄下的 Yahoo 回應：https://github.com/gadicc/node-yahoo-finance2/tree/devel/tests/fixtures/http
    （`quoteSummary-upgradeDowngradeHistory-{AAPL,ABBV,AMZN,ARMK,BABA,CRM,GOOG,SPOT,…}.json`、
    `quoteSummary-financialData-*.json`；經 `cdn.jsdelivr.net/gh/gadicc/node-yahoo-finance2@devel/…` 取得）
- Yahoo 條款：https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html
- Finnhub：https://finnhub.io/static/swagger.json 、https://finnhub.io/terms-of-service
- Alpha Vantage：https://www.alphavantage.co/documentation/ 、https://www.alphavantage.co/support/ 、
  https://www.alphavantage.co/premium/ 、demo：`https://www.alphavantage.co/query?function=OVERVIEW&symbol=IBM&apikey=demo`
- Twelve Data：https://twelvedata.com/pricing 、https://twelvedata.com/docs/llms/analysis/price-target.md 、
  https://twelvedata.com/docs/llms/analysis/analyst-ratings-light.md
- EODHD：https://eodhd.com/pricing
- Massive：https://massive.com/pricing 、https://massive.com/docs/rest/partners/benzinga/analyst-ratings.md
- Benzinga：https://docs.benzinga.com/api-reference/calendar-api/get-ratings.md
- Tiingo：https://www.tiingo.com/about/pricing
- Zacks：https://www.zacks.com/terms_of_service.php
- Dow Jones：https://www.dowjones.com/terms-of-use/
- StockAnalysis：https://stockanalysis.com/terms-of-use/
- Nasdaq 非官方端點整理：https://github.com/steveman1123/stonkBot/blob/master/NASDAQ_API_DOC.md
- repo 內：`option_chaser/data/dividends.py`、
  `docs/research/analyst-price-target-data-sources.md`、
  `docs/research/public-beta-market-data-source-selection.md`

二手（【轉述】）：

- https://github.com/FelixSchramm/real-time-stock-market-pipeline/issues/16 （yfinance 欄位、MSFT 約 950 列）
- https://github.com/gururafiki/muffin-deployment/pull/494 （AAPL 969 筆）
- https://www.powershellgallery.com/packages/FinancialModelingPrep/0.1/Content/PublicFunctions%5CGet-FMPPriceTargetNews.ps1 （FMP price-target-news 為 premium）
- FMP 頁面的搜尋摘要：https://site.financialmodelingprep.com/developer/docs/stable/price-target-news 、
  https://site.financialmodelingprep.com/datasets/analyst-estimates-targets 、
  https://site.financialmodelingprep.com/insights/platform/what-happens-when-you-hit-your-fmp-api-limit
- Nasdaq：https://www.nasdaq.com/legal （搜尋摘要）、https://data.nasdaq.com/databases/ARPT 、
  https://www.mboum.com/blogs/how-to-retrieve-analyst-ratings-and-price-targets-with-the-mboum-api
