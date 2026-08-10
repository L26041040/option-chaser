# 歷史選擇權鏈／歷史 IV 資料源比較：誰能按需重建歷史 Spread Debit

研究日期：2026-08-07。姊妹篇：`docs/research/option-chain-data-sources.md`
（**即時**鏈資料源評選，現行主源 Cboe delayed quotes、備援 yfinance）、
`docs/research/cboe-field-semantics.md`（Cboe 欄位語意實測）。本文只處理
「**歷史**」——過去某一天（EOD 即可）的 per-contract bid/ask/IV——
即時鏈的結論不重推。

**取材限制聲明（沿用本 repo research 慣例）**：本沙箱出口 proxy 對本文
評估的 vendor 網域一律封鎖——WebFetch 對 `www.orats.com`、`polygon.io`、
`www.marketdata.app` 實測回 `EGRESS_BLOCKED`（本次逐一實測），與前兩輪
研究（`option-strategy-report-conventions.md` §6、
`interest-rate-source-selection.md` 開頭）遇到的封鎖完全同型。因此本文
**所有 vendor 官方文件內容均為搜尋引擎索引轉述**，未逐字核對原文；
價格數字尤其易變且轉述易錯，全部標注查證日期並在 §7 逐項列出未經
原件查證者。**「沙箱連不到」≠「production 連不到」**——本 repo 的
Vercel 正式環境已證實能連上 Cboe 與 Treasury（見 CLAUDE.md V1／#74），
任何採用決定前應以 production 實測 vendor 端點為準。

## 1. 結論摘要（先行）

- **A.3 的答案是「有解，且不只一家」**：要按需（REST 查詢、不自建資料庫）
  重建歷史 spread debit（Buy Ask − Sell Bid）＋歷史 IV，可行候選是
  **ORATS Data API**（2007 起、每日一次 near-EOD 快照、per-contract
  雙邊報價＋IV＋Greeks）、**Market Data App**（2010 起 EOD、單一呼叫可回
  **整段日粒度時間序列**——對本 app 的 SpreadHistory 走勢圖是獨有優勢）、
  **Alpha Vantage `HISTORICAL_OPTIONS`**（2008 起、指定日全鏈、
  免費層資格存疑）、**EODHD**（欄位最齊但**只回溯到 2023 Q4**，約 2.5 年，
  年限硬傷）。詳 §5。
- **Yahoo／yfinance 查證確認：沒有歷史選擇權鏈。** `option_chain()` 只回
  當下快照；Yahoo 對單一選擇權合約有**成交價 OHLC** 歷史（同股票走勢），
  但無歷史 bid/ask、無歷史 IV——重建最差成交口徑的 debit **不能**（§4.3）。
- **Theta Data 資料面完全合格、架構面與本專案衝突**：其 REST API 由本機
  常駐的 Java「Theta Terminal」提供，Vercel serverless 無法常駐行程——
  除非另租一台小 VM 當資料 gateway，否則不可用（§4.6）。
- **Polygon.io（已更名 Massive）與 Databento 是 tick 級思維**：歷史 NBBO
  是逐筆報價流（Polygon quotes 只回溯到 ~2022；Databento 要自算 IV），
  要 EOD 快照得自己降採樣，工程量與流量都跟「按需查一天」不成比例——
  部分能，但不適配（§4.5、§4.12）。
- **廉價 EOD 檔案商（historicaloptiondata.com、optionsDX、FirstRate
  Data、Cboe DataShop 檔案類產品）年限與欄位都合格、但形式全是 bulk
  檔案下載**——與需求方「不自己每天存 chain、資料庫負擔越低越好」的
  硬約束**直接衝突**，本文如實比較但逐一標明衝突（§4.13、§4.2）。
- 本文**不做**最終選型（需求方保留），只整理事實與 trade-off；也不涵蓋
  IV 方法論（另一份研究）、Long Call vs Spread 比較、跨劇本比較。

## 2. 需求界定：A.3 到底需要什麼

本 app 的成本口徑是**最差成交**（Buy leg 用 Ask、Sell leg 用 Bid；
T12／附錄 A14.2，序列化欄位見 `option_chaser/data/cboe.py` 的
`OptionContract`：per-contract bid/ask/iv/greeks/OI/volume）。要重建
**歷史** spread debit，逐源檢核四件事：

1. **per-contract 歷史 bid 與 ask**——不是成交價 OHLC、不是 mid、
   不是理論價；且兩腿要**同一時點**（EOD 收盤快照即可）。
2. **歷史 IV**——per-contract 或 surface 層級皆可。
3. **API 形式**——「分析當下按需查詢」的 REST，而非 bulk 檔案倒進
   自己的資料庫。**這是需求方明文硬約束**：不採「我們每天自己存
   chain」方案；Neon Postgres 免費層，資料庫負擔越低越好。
4. **回溯年限**——本 app 劇本以月～年為尺度（LEAPS 劇本），至少要
   涵蓋「一組 spread 從建立到到期」的量級（1–3 年）；更長年限
   （2007–2012 起）是加分不是門檻。

另兩個操作面維度：**查詢粒度**（一次呼叫回一天全鏈？回單一合約的
整段序列？）與**能否展示給使用者**（授權是否允許 display／再散布）。
後者多數 vendor 條款原文無法在本沙箱取得，統一列入 §7。

## 3. 總覽比較表

（價格均為 2026-08-07 經搜尋索引轉述查得，量級參考用，未經原件查證；
「A.3」欄＝能否重建歷史 spread debit＋IV；「約束」欄＝與「不自存、
按需查詢」硬約束的相容性：✅ 相容／⚠ 部分／❌ 衝突）

| 來源 | 歷史年限（EOD） | bid/ask | IV | Greeks | API 形式 | 價格量級 | A.3 | 約束 |
|---|---|---|---|---|---|---|---|---|
| ORATS Data API | 2007 起 | ✅ 雙邊（3:46 ET 快照） | ✅ | ✅ | REST（`hist/strikes` 逐日全鏈） | 轉述矛盾：US$49～399/月（§4.1） | **能** | ✅ |
| Cboe DataShop（檔案） | 2012 起（quotes+calcs） | ✅ | ✅ | ✅ | bulk CSV 下載／訂閱 | 訂閱 US$500/月級；ad-hoc 另計 | 能 | ❌ bulk |
| Cboe All Access API | 有歷史端點（年限未查明） | ✅ | ✅ | ✅ | REST（points 計費） | 不透明（points 制） | 能 | ✅（價未明） |
| Yahoo／yfinance | 合約成交 OHLC（僅掛牌期間） | ❌ 無歷史 | ❌ 無歷史 | ❌ | 非正式 | 免費 | **不能** | — |
| Alpha Vantage `HISTORICAL_OPTIONS` | 2008 起（15+ 年） | ✅ | ✅ | ✅ | REST（指定日全鏈） | 免費 25 req/日（存疑）；premium US$49.99/月起 | **能** | ✅ |
| Polygon.io／Massive | quotes ~2022 起；trades 2016 起；aggregates 2 年（Starter） | ⚠ tick NBBO，無 EOD 快照 | ❌ 歷史無（snapshot 僅當下） | ❌ 同左 | REST | US$29／79／199/月 | 部分能 | ⚠ tick 降採樣 |
| Theta Data | 免費 1 年；Value 4 年／Standard 8 年／Pro 12 年 | ✅ | ✅ | ✅ | REST **但打本機 Theta Terminal** | 免費～US$160/月 | 能 | ❌ 架構（§4.6） |
| Market Data App | 2010 起（一說 2005，文件互相矛盾） | ✅ | ✅ | ✅ | REST（單合約 from/to 回整段日序列） | Free 100 credits/日；付費 US$12–30/月級（轉述） | **能** | ✅ |
| IVolatility | 2005 起 | ✅ NBBO | ✅（Raw IV／surface／IV Index 為獨立資料集） | ✅ | API＋Data Download Tool，pay-per-use | 按資料集計價（單位未查明） | 能 | ⚠ 偏批次 |
| Intrinio | 「最多 10 年、按年計售」 | ⚠ 欄位未逐項查證 | ✅（Silver 起） | ✅（Silver 起） | REST | US$150 起/月，Silver 級常見 US$600–2000/月交易所費 | 部分能（待查證） | ✅（價高） |
| EODHD（UnicornBay options） | **2023 Q4 起（~2.5 年）** | ✅ 含 size | ✅ | ✅ 五希臘 | REST（逐日、逐合約過濾） | US$39.99/月（前三月 29.99） | 能（年限硬傷） | ✅ |
| Barchart OnDemand | `getEquityOptionsHistory`（年限未查明） | ✅（選填欄位） | ✅ | ✅ | REST | US$500/月起（enterprise 談價） | 能 | ✅（價高） |
| Databento（OPRA） | CMBP-1 2023-03 起；CBBO-1m／OHLCV 2013-04 起 | ⚠ tick／分鐘 NBBO | ❌ 不提供（要自算） | ❌ 同左 | REST＋批次，按量計費 | 按量（每 GB 費率未查明） | 部分能 | ⚠ tick 降採樣 |
| historicaloptiondata.com | 2002 起 | ✅ 含 size | ✅ | ✅ | bulk CSV | 便宜（明細未查明）；2013 上半年樣本免費 | 能 | ❌ bulk |
| optionsDX | 2010 起（免費、標的有限） | ✅ | ✅ | ✅ | bulk 檔案 | 免費（EOD）／付費（intraday） | 能 | ❌ bulk |
| FirstRate Data | 2010 起 | ✅ 含雙邊 IV | ✅ | ✅ | bulk CSV | 單標的年更 ~US$99/年；bundle US$59–99/月 | 能 | ❌ bulk |
| FlashAlpha | 2017 起（分鐘級 analytics） | ⚠ 未查明 per-contract 報價 | ✅（analytics 口徑） | ✅ | REST | 免費層；付費 US$63～79/月起（轉述矛盾） | 部分能 | ✅ |
| Tradier | 合約成交 OHLC（`get-history` 吃 OCC 代號） | ❌ 無歷史 | ❌ | ❌ | REST | 免費 sandbox | **不能** | — |

## 4. 逐源展開

### 4.1 ORATS Data API

- **產品**：Historical Data API，`https://api.orats.io/datav2/hist/strikes`
  （token 認證），逐 trade date 回該標的全鏈 strike 級資料；另有
  monies／summaries／greeks 等衍生端點。文件：
  https://orats.com/docs/historical-data-api 、
  https://docs.orats.io/data-api-guide/data.html （皆被沙箱擋，轉述）。
- **年限**：2007 起（"15+ years"，https://orats.com/data-api ；
  near-EOD 產品頁 https://orats.com/near-eod-data 同口徑）；另有
  2020-08 起的 1 分鐘 intraday 產品（https://orats.com/one-minute-data ，
  本案不需要）。
- **欄位**：strikes 端點含 `callBidPrice`／`callAskPrice`／
  `putBidPrice`／`putAskPrice`、bid/ask size、volume、OI、IV、
  Greeks（delta/gamma/theta/vega/rho/phi）、ORATS 理論價——
  **雙邊報價齊全，可直接重建最差成交口徑**。
- **⚠ 時點口徑**：ORATS 的「EOD」快照是**收盤前 14 分鐘（約 3:46 ET）**
  取的，官方說法是刻意避開收盤競價時段的異常寬價差
  （https://orats.com/data-api 轉述）。兩腿同一時點、口徑一致，重建
  spread debit 沒問題；但與 Cboe 收盤快照逐日對帳時會有系統性小差異，
  採用時要記在方法論尾註。
- **API 形式**：REST 按需查詢，100 req/min（轉述）；strikes 端點單次
  回應有 6000 列上限（一天全鏈通常在此之內）。逐日查詢＝一天一次呼叫；
  重建 N 天 debit 序列＝N 次呼叫（每次抓全鏈、兩腿同回應內）。
- **價格（2026-08-07 轉述，互相矛盾、未definitive）**：一說 Data API
  US$49/月、「有意義的歷史 API 存取」US$199–299/月
  （https://brokers-exchange.com/orats-review/ ，二手）；另一說歷史
  資料年約 US$399/年（FTP 下載口徑）。**訂閱制月費量級 US$49–399
  之間，實際層級與 API 是否含全歷史需以官網原件為準**（§7）。
- **A.3 判定：能。** EOD（3:46 ET）、per-contract 雙邊報價＋IV＋
  Greeks、2007 起、REST 按需。與硬約束相容。

### 4.2 Cboe DataShop（檔案）＋ Cboe All Access API

**現行主源 Cboe 的免費 delayed quotes endpoint 沒有歷史**——只回當下
快照（`option-chain-data-sources.md` §3.2）。Cboe 的歷史產品是另外
付費的兩條路：

- **DataShop 檔案類**（https://datashop.cboe.com/ ）：
  「End-of-Day Option Quotes with Calcs」訂閱＝每日 EOD 快照＋3:45PM ET
  快照、OHLC、volume，Calcs 加購含 IV＋Greeks，**歷史自 2012-01 起**
  （https://datashop.cboe.com/option-quotes-end-of-day-with-calcs-yearly-subscription ，
  轉述）。SEC 費率文件轉述：EOD 訂閱 US$500/月、歷史 ad-hoc
  US$400/請求·月（該數字出自 Open-Close 類產品的費率表，
  https://www.sec.gov/files/rules/sro/cboe/2015/34-74159-ex5.pdf ；
  DataShop 對單一標的、短區間的 ad-hoc CSV 是否有更低單價，
  **未能查證**，§7）。形式是 CSV 下載——**與「不自存」硬約束衝突**：
  買了檔案還是得自己落庫才能查。
- **All Access API**（2021-01-25 起取代 LiveVol API，
  https://datashop.cboe.com/product-launch-cboe-all-access-apis ；
  技術文件 https://api.livevol.com/v1/docs/Help?apiGroupName=allaccess ）：
  REST、**同一訂閱可打 live／delayed／historical 請求**，含 IV 與
  Greeks。計費是「points 制」——各層級每月配額若干 points，不同端點
  扣點不同（https://datashopcert.livevol.com/all-access-apis-pricing ，
  轉述；**具體層級價格與扣點表未能查證**）。形式上與硬約束相容，
  是「官方 Cboe 血統＋REST 歷史查詢」唯一的一條路，但價格不透明、
  多半是機構量級。
- **A.3 判定**：檔案類「能，但 bulk」；All Access API「能，價未明」。

### 4.3 Yahoo／yfinance：查證確認沒有歷史鏈

需求方點名要查清楚的一點，結論明確：

- **yfinance 的 `option_chain(expiry)` 只回當下快照**，沒有任何
  「as of 過去某日」參數；社群多次求解無 workaround
  （https://github.com/ranaroussi/yfinance/discussions/2078 ；
  https://www.macroption.com/yahoo-finance-options-python/ ）。
- Yahoo 對**單一合約**（OCC 代號當 ticker）有歷史**成交價 OHLC**
  （同股票 chart API），僅限合約掛牌期間、且是 trade-based——
  **無歷史 bid/ask、無歷史 IV**（Macroption 同上，轉述）。
- **A.3 判定：不能。** 最差成交口徑的 debit 需要雙邊報價；成交價
  OHLC 連 mid 都湊不出來，低流動性 LEAPS 可能數週無成交。Tradier
  的 `get-history` 端點同理（吃 OCC 代號、回成交 OHLC，
  https://documentation.tradier.com/brokerage-api/markets/get-history ，
  轉述）——**Tradier 也沒有歷史鏈**，同判「不能」。

### 4.4 Alpha Vantage `HISTORICAL_OPTIONS`

前次研究（`option-chain-data-sources.md` §3.4）已涵蓋，本文補歷史面：

- **形式**：`function=HISTORICAL_OPTIONS&symbol=X&date=YYYY-MM-DD`，
  REST、**指定日回全鏈**（所有到期日所有履約價），含 bid/ask/mark/
  last/volume/OI/**IV/全套 Greeks**；**2008 起、15+ 年**
  （https://www.alphavantage.co/documentation/ ，轉述）。
- 一次呼叫＝一天全鏈（兩腿同回應）；重建 N 天序列＝N 次呼叫。
- **免費層資格是老問題且仍未定**：前次研究已記錄二手來源互相矛盾
  （25 req/日免費 vs premium-only）；本次搜尋到的較新轉述傾向
  「options 端點含歷史屬 premium（US$49.99/月起）」
  （https://www.findmymoat.com/tools/alpha-vantage ，2026 轉述，二手）。
  **以實際金鑰打一次為準**——這正好可與前次研究 §4.4 驗證清單
  合併執行。
- **A.3 判定：能。** 與硬約束相容。已知怪癖沿用前文：DTE ≤ 3 的
  IV 欄不可靠。

### 4.5 Polygon.io（已更名 Massive）

- **歷史 quotes**：`/v3/quotes/{optionsTicker}` 回逐筆 NBBO（bid/ask/
  size/exchange/時戳），**歷史僅回溯到 ~2022**；trades 回溯 2016
  （https://polygon.io/docs/rest/options/trades-quotes/quotes 、
  https://massive.com/docs/rest/options/quotes ，轉述）。
- **歷史 IV／Greeks：沒有。** IV 與 Greeks 只活在 snapshot 端點
  （當下），aggregates（OHLC bar）是成交口徑、無 bid/ask
  （https://massive.com/docs/rest/options/snapshots/option-chain-snapshot ，
  轉述；FlashAlpha 的對比文也以「raw vs computed」定位它，
  https://flashalpha.com/articles/flashalpha-vs-polygon-options-data-raw-vs-computed ，二手）。
- **層級**：Options Starter US$29／Developer US$79／Advanced US$199/月
  （2026-08-07 轉述）；Starter 的 aggregates 歷史 2 年。**歷史 quotes
  端點落在哪一層未能查證**（過往慣例是高層級才開，§7）。
- **A.3 判定：部分能。** 理論上可以「取每天收盤前最後一筆 NBBO」
  重建 debit，但那是逐合約拉 tick 流再自己降採樣——工程量、流量、
  層級費用都跟「按需查一天 EOD」不成比例；且 IV 歷史整條缺失，
  要自算（IV 方法論屬另一份研究，本文不展開）。年限 ~2022 起也偏短。

### 4.6 Theta Data

- **資料面**：OPRA 全市場，EOD／intraday quotes（bid/ask）＋trades、
  per-contract IV 與 1–3 階 Greeks；歷史深度依層級：免費層 1 年
  EOD（30 req/min）、Value US$40/月＝4 年、Standard US$80/月＝8 年
  ＋tick、Pro US$160/月＝12 年（https://www.thetadata.net/pricing 、
  https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html ，
  轉述；另有二手文章給出 US$25/60 的不同數字，
  https://flashalpha.com/articles/flashalpha-vs-thetadata-options-greeks-iv-api ——
  **價格轉述矛盾**，§7）。資料面是全場對 A.3 最完整的組合之一，
  且有免費層可實測。
- **架構面（致命點）**：API 是**打本機 Theta Terminal**——一個要常駐
  執行的 Java 程序，維持與 Theta 伺服器的壓縮協定連線，REST 服務
  開在 localhost（QuantConnect 整合文件明講要先啟動 Terminal，
  https://www.quantconnect.com/docs/v2/lean-cli/datasets/theta-data ，
  轉述）。**Vercel serverless 無法常駐行程**（`api_app/main.py` 檔頭
  記錄的唯讀／無常駐前提），要用 Theta Data 就得另租一台常駐 VM 當
  資料 gateway——與「Vercel＋Neon 免費層、預算敏感」的部署形狀衝突。
  是否存在不經 Terminal 的官方雲端 REST，**未能查證**（§7）。
- **A.3 判定：能（資料面）；架構衝突（部署面）。**

### 4.7 Market Data App

前次研究（§3.6）judged 免費層抓**即時全鏈**不可行（逐合約扣
credit）。歷史面是另一回事，且對本案有一個獨有優勢：

- **形式**：`/v1/options/quotes/{optionSymbol}/` 支援 `from`／`to`
  日期參數，**單一合約一次呼叫回整段日粒度歷史報價序列**（bid/ask/
  mid/last/IV/Greeks/OI/volume，https://www.marketdata.app/docs/api/options/quotes ，
  轉述）。重建一組 spread 的 debit 走勢＝**兩次呼叫**（每腿一次），
  這對 SpreadHistory（V9）那種「一條走勢圖」的查詢形狀是全場最省的
  ——其他逐日全鏈型來源要 N 天 N 次呼叫。
- **年限**：官方文件自我矛盾——API 文件頁說 quotes 回溯 **2005**，
  產品頁說 EOD 歷史自 **2010** 起（https://www.marketdata.app/data/options/ ，
  轉述；兩說並存原樣記錄）。無論哪說都覆蓋本案需求。
- **價格（2026-08-07 轉述）**：Free Forever 100 credits/日；付費層
  轉述為 Starter US$12/月（10,000 credits/日、歷史回溯 5 年、15 分鐘
  延遲）／Trader US$30/月（100,000 credits/日、歷史無年限）
  （https://www.marketdata.app/docs/account/plan-limits/ 、
  https://www.marketdata.app/pricing/ ，轉述——**與前次研究記到的
  價格結構出入不小，未經原件查證**，§7）。歷史單合約序列查詢扣
  多少 credit（一次呼叫一 credit？逐日扣？）**未能查證**——若是
  前者，連免費層都夠本案輕度使用。
- **A.3 判定：能。** 與硬約束相容，且查詢形狀最適配。

### 4.8 IVolatility

- 老牌選擇權資料商（OCC 的 OIC 教育網站亦採用其資料，
  https://oic.ivolatility.com/historical-options-data/ ）。EOD 歷史自
  **2005** 起，含下市標的；資料集拆售：underlying US$0.20、
  option prices（NBBO）＋HV US$0.40、Raw IV／IV surface（by
  moneyness）／IV Index US$0.60——**計價單位（per ticker-year？
  per 下載？）未能查證**（https://www.ivolatility.com/data-download-intro/ 、
  https://www.ivolatility.com/historical-options-data/ ，轉述）。
- 交付形式：Data Download Tool（一次性 CSV）、FTP、Managed DB、
  cloud API（https://www.ivolatility.com/data-cloud-api/ ）。
  pay-per-use、無訂閱是它的賣點，但主流用法偏「下載一批自己算」
  ——**cloud API 能否逐日按需查詢單標的鏈，粒度與計費未能查證**。
- **A.3 判定：能（資料面齊全）；形式偏批次，API 細節待查。**
  它的獨特之處是 **IV surface 是獨立商品**——若日後「歷史 IV」要的
  是 surface 而非 per-contract，這裡是少數直接賣 surface 的。

### 4.9 Intrinio

- 定位是 B2B／平台商。EOD 歷史選擇權「最多 10 年、按年計售、無
  交易所費」（https://intrinio.com/options/eod-historical-options ，
  轉述，經第三方交付）；套餐 Bronze（最新 EOD OPRA 價）／Silver
  （15 分鐘延遲＋Greeks＋IV，常見另有 US$600–2000/月交易所費）／
  Gold（即時）（https://intrinio.com/guides/options-bronze 等，轉述）。
  平台整體定價 US$150–1,600/月級（https://www.g2.com/products/intrinio-financial-data-api/pricing ，二手）。
- **歷史 EOD 是否含收盤 bid/ask（而非只有 OHLC）未能逐欄查證**（§7）。
- **A.3 判定：部分能（欄位待查證）；價格量級對個人專案不友善。**

### 4.10 EODHD（UnicornBay「US Stock Options Data」）

- **形式**：REST，marketplace 加購件，US$39.99/月（beta 期前三個月
  29.99；2026-08-07 轉述，https://eodhd.com/marketplace/unicornbay/options ）。
  6,000+ 美股標的，42+ 欄位：OHLC、**bid/ask 含 size**、volume/OI
  （含日增減）、**五希臘＋IV**、理論價、moneyness、DTE 等
  （https://eodhd.com/lp/us-stock-options-api ，轉述）。
- **年限（硬傷）**：**2023 Q4 起，約 2.5 年**。對「重建一組 2026 年
  劇本的歷史」夠用，對更長回溯不夠，且欄位再齊也補不了年限。
- **A.3 判定：能（年限受限）。** 與硬約束相容。

### 4.11 Barchart OnDemand

- `getEquityOptionsHistory` 端點：吃合約代號
  （`AAPL|20200417|250.00C`），回歷史序列，**選填欄位含 bid/ask、
  IV、Greeks**（https://www.barchart.com/ondemand/api/getEquityOptionsHistory ，
  轉述；歷史年限未查明）。
- 商業條件：OnDemand API **US$500/月起**、enterprise 談價
  （https://www.barchart.com/ondemand/api ，轉述）。
- **A.3 判定：能；價格量級不適配個人專案。**

### 4.12 Databento（OPRA）

- 原始行情思維：OPRA.PILLAR 資料集，schema 含 trades、CMBP-1
  （NBBO 更新，**2023-03-28 起**）、CBBO-1m（分鐘級 NBBO，
  **2013-04 起**）、OHLCV、statistics、definitions（
  https://databento.com/datasets/OPRA.PILLAR 、
  https://databento.com/blog/opra-migration 、
  https://databento.com/blog/opra-improvements-coming-soon ，轉述）。
  歷史維持 pay-as-you-go 按量計費（每 GB 費率未能查證；live OPRA
  的按量制 2025-06-03 已停，https://databento.com/blog/introducing-new-opra-pricing-plans ）。
- **不提供 IV／Greeks**——它賣的是規整後的原始行情，衍生指標自算。
- **A.3 判定：部分能。** 分鐘級 NBBO 可降採樣出 EOD 雙邊報價
  （2013 起），但這就是「自建資料管線」的形狀——與硬約束的精神
  （低工程、低儲存）相悖；IV 還得自算。適合量化回測基建，不適合
  本案。

### 4.13 廉價 EOD 檔案商（bulk，全數與硬約束衝突）

這一類年限長、欄位齊、單價低，但形式全是「下載 CSV → 自己落庫」，
逐一標明衝突後如實記錄：

- **historicaloptiondata.com**：**2002 起**、4000+ 標的全市場 EOD，
  雙邊報價含 size、Greeks＋IV 不另收費；2013 年 1–6 月樣本檔
  （1.8GB）免費（官網轉述，出處經
  https://readmedium.com/how-to-download-free-historical-eod-options-data-84d72ab8a404 等二手引介）。
- **optionsDX**（https://www.optionsdx.com/ ）：**免費** EOD 歷史
  （2010 起、標的選擇有限），intraday 付費；含 Greeks／IV／標的價。
  「免費拿幾年 SPY/TLT 檔案來做一次性研究校驗」是它的合理用途——
  當 production 資料源則否。
- **FirstRate Data**（https://firstratedata.com/options-data 、
  https://firstratedata.com/b/49/historical-options-data ）：2010 起、
  5800+ 現存＋4000+ 下市標的，全鏈雙邊報價＋**bid/ask 兩側各自的
  IV**＋Greeks＋OI；單標的年更 ~US$99/年、bundle US$59–99/月（轉述）。
- **optiondata.org（HistoricalData.net）**：同型 CSV 商，有免費樣本
  （https://optiondata.org/ ）。
- **Cboe DataShop 檔案類**：見 §4.2，血統最正的 bulk。
- **A.3 判定：能（資料面），❌ 形式與硬約束直接衝突。**

### 4.14 其他發現與點名未深查者

- **FlashAlpha**（https://flashalpha.com/ ，研究過程中反覆出現的新進
  vendor）：定位是 options **analytics** API（GEX／Greeks surface／
  vol surface／VRP），歷史鏡像 API 支援 `?at=` 參數回放 **2017 起**
  任一分鐘（https://flashalpha.com/docs/api ，轉述）。IV 面「部分能」；
  **per-contract 歷史 bid/ask 是否可取未能查證**；免費層存在，付費
  轉述矛盾（US$63 vs 79/月起，§7）。其站上大量「vs 同業」比較文是
  行銷內容，本文僅取其中可交叉驗證的事實。
- **點名但未深查**（本輪搜尋未覆蓋，僅記錄存在與粗略定位，無引註，
  不得引用為結論）：OptionMetrics IvyDB（學術界標準歷史選擇權資料庫，
  經 WRDS 訂閱，機構價）；Interactive Brokers TWS API（有歷史
  bid/ask bar，但需常駐 gateway＋券商帳戶，與 serverless 衝突，
  形狀同 §4.6 的問題）；QuoteMedia／dxFeed／SpiderRock（機構餵送）。

## 5. A.3 結論性彙整

### 5.1 逐源判定（能／不能／部分能）

| 來源 | 判定 | 端點／產品 | 粒度 | 回溯 |
|---|---|---|---|---|
| ORATS | **能** | `datav2/hist/strikes` | EOD（3:46 ET 快照） | 2007 起 |
| Market Data App | **能** | `/v1/options/quotes/` ＋ from/to | EOD（日序列一次回） | 2010（一說 2005）起 |
| Alpha Vantage | **能** | `HISTORICAL_OPTIONS` | EOD（指定日全鏈） | 2008 起 |
| EODHD | **能**（年限受限） | UnicornBay options API | EOD | 2023 Q4 起 |
| Cboe All Access API | 能（價未明） | historical 請求 | EOD／intraday | 未查明 |
| Cboe DataShop 檔案 | 能（❌ bulk） | EOD Quotes with Calcs | EOD＋3:45PM 快照 | 2012 起 |
| Theta Data | 能（❌ 架構） | Terminal REST（quotes/Greeks） | EOD～tick | 1–12 年依層級 |
| IVolatility | 能（形式偏批次） | Data Download／cloud API | EOD | 2005 起 |
| Barchart OnDemand | 能（價高） | `getEquityOptionsHistory` | EOD 序列 | 未查明 |
| bulk 檔案商 ×4 | 能（❌ bulk） | CSV | EOD | 2002／2010 起 |
| Intrinio | 部分能（欄位待查） | EOD historical options | EOD | ~10 年 |
| Polygon/Massive | 部分能 | `/v3/quotes/`（tick） | tick（自行降採樣） | ~2022 起 |
| Databento | 部分能 | CBBO-1m／CMBP-1 | 分鐘／tick（自行降採樣、IV 自算） | 2013／2023 起 |
| FlashAlpha | 部分能（IV 面） | historical mirror `?at=` | 分鐘 | 2017 起 |
| Yahoo／yfinance | **不能** | 僅合約成交 OHLC | — | — |
| Tradier | **不能** | 僅 `get-history` 成交 OHLC | — | — |

### 5.2 「能重建 debit＋IV」×「按需查詢、低資料庫負擔」交集

四家進交集，成本量級與 trade-off 並列（**不做最終決定**）：

1. **ORATS**——年限最長（2007）、選擇權專業血統、欄位為 spread 分析
   而生；代價：訂閱價轉述矛盾（US$49–399/月量級待原件確認）、
   時點是 3:46 ET 非收盤、逐日查詢一天一呼叫。
2. **Market Data App**——查詢形狀最適配（單合約一次呼叫回整段日
   序列，SpreadHistory 一張圖＝兩次呼叫）；免費層可實測；代價：
   年限文件自我矛盾（2005 vs 2010）、歷史查詢的 credit 扣法未查明、
   付費層價格轉述與前次研究出入大。
3. **Alpha Vantage**——與本 repo 既有備援方案同一家（金鑰可共用）、
   指定日全鏈一次回；代價：免費層資格懸而未決（傾向 premium
   US$49.99/月起）、與既有選擇權備援共用配額的老問題（
   `interest-rate-source-selection.md` 對利率端點記過同一筆帳）。
4. **EODHD**——US$39.99/月、欄位最齊（42+ 欄含 bid/ask size）；
   代價：**只回溯 2023 Q4**，這條硬傷讓它只適合「近期劇本回放」
   而非長歷史。

**次一級（單項不合但值得記錄）**：Theta Data（資料面最強、免費層
1 年 EOD 可白嫖驗證，卡在 Terminal 常駐架構）；Cboe All Access API
（血統與現行主源一致，卡在價格不透明）；IVolatility（surface 級
歷史 IV 的少數直接來源，卡在批次形式與計價單位不明）。

**驗證優先序建議**（沙箱做不到、需 production 或本機真金鑰）：
① Market Data App 免費層實打歷史單合約序列（確認 credit 扣法與
實際回溯年限）→ ② Alpha Vantage 免費金鑰實打 `HISTORICAL_OPTIONS`
（一次解決兩輪研究共同的懸案）→ ③ ORATS 官網原件確認訂閱層級——
三者都免費或近免費，實測後交集名單可能縮小或重排。

## 5.1 追記（#111）——production 實測已完成，三家皆 credential-blocked

**沙箱出口封鎖已直接驗證**（背景，維持原記錄）：`curl` 對候選網域皆收到
CONNECT 層級拒絕，與本文開頭 §0 記錄的同一種沙箱限制。**這只是沙箱出口
政策**——本節記錄的是繞過沙箱、從真實可連網環境（GitHub Actions
`ubuntu-latest` runner，理由與方法同 #120，見
`dividend-yield-source-selection.md` §12.4）跑出的結果。

**實測結果（2026-08-10，run
[31408756757](https://github.com/L26041040/option-chaser/actions/runs/31408756757)，
真實對外請求，`ALPHA_VANTAGE_API_KEY=demo`——Alpha Vantage 官方公開文件
的示範金鑰，非私自取得的憑證）**：

| 順序 | vendor | 是否可申請免費金鑰 | 實測結果 | 資料形狀是否符合需求 | 結論 |
|---|---|---|---|---|---|
| ① | Market Data App | 可（未申請） | **未發出請求**——端點要求 `Authorization: Bearer {token}`，沒有任何匿名可測路徑，`MARKETDATA_APP_TOKEN` 未設定即無法呼叫 | 不適用 | **credential-blocked**：連可達性都無法在無金鑰下驗證 |
| ② | Alpha Vantage | 可（用官方 demo 金鑰測試） | **HTTP 200**，但 body 是 `{"Information": "The **demo** API key is for demo purposes only. Please claim your free API key at (...) to explore our full API offerings."}`——**不是** `HISTORICAL_OPTIONS` 的真實資料 | **無法驗證**——demo 金鑰擋在資料本身之前 | **credential-blocked**：端點確認可達（HTTP 200、非網路層失敗），但取得真實資料仍需申請免費金鑰（官方文案「不到 20 秒」） |
| ③ | ORATS | 多半需付費 | **未發出請求**——端點要求 query string `token=`，`ORATS_TOKEN` 未設定即無法呼叫 | 不適用 | **credential-blocked**：同 Market Data App，連可達性都無法驗證 |

**與 §4.1/§4.7 原研究的差異**：①③ 兩家的認證設計是「金鑰是呼叫的必要
輸入」而非「先試後擋」——探測腳本對它們**連請求都沒送出**（沒有金鑰就
沒有可測的 URL），這比「打了但被 401/403 拒絕」更嚴格，**不是探測腳本
的缺陷，是這兩個 vendor 的認證機制本身**。②Alpha Vantage 稍有不同：
它公開了一個任何人都能用的 `demo` 金鑰，讓探測腳本至少驗證了「端點存在、
可達、回真實 HTTP 回應」，但該金鑰的資料範圍不含 `HISTORICAL_OPTIONS`
這個 function 對 TLT 的真實回應——**仍未取得一次真正的 historical
option/IV 資料**。

**結論（依 #111 既有 AC 逐字適用）**：

- **三家 vendor 皆為 credential-blocked，沒有一家可以宣稱「已確認」**。
  這**不是**沙箱限制造成的——本次探測已經是從真實可連網環境（GitHub
  Actions）發出的真實請求，Alpha Vantage 甚至拿到了真實 HTTP 200——
  三家的共同瓶頸是**取得實際資料本身需要一把本 repo 尚未持有的免費／
  付費金鑰**，這正是 AC 明文要求「明確標記 credential-blocked」的情況。
- **不得宣稱任何 vendor 已確認**，也**不得**用本次的 Alpha Vantage
  HTTP 200（demo 金鑰的「請註冊」訊息）冒充一次成功的
  `HISTORICAL_OPTIONS` 呼叫。
- **#111 本身不可 close**：距離「至少一次成功的真實 API 呼叫並驗證
  資料形狀」還差一步——**需要需求方決定是否要為以下任一 vendor 申請
  免費金鑰**（依 §5 優先序）：
  1. **Alpha Vantage**（建議優先，免費申請號稱 20 秒、且已確認端點
     真實可達）：https://www.alphavantage.co/support/#api-key
  2. **Market Data App**（免費層 100 credits/日）：
     https://www.marketdata.app/
  3. ORATS 多半需付費訂閱，僅在①②皆不可行時才需要考慮
- **#114（Historical IV Position 模組）依既有 blocked-by 持續卡在
  #111 之後**，本輪未能解除。
- 若需求方核發任一金鑰，重跑 `scripts/probe_iv_history_vendors.py`
  （設對應環境變數）即可完成 #111 剩餘驗證，腳本與探測管線本身
  已就緒、不需重寫。

## 6. 明確不涵蓋

- **IV 方法論**（surface 建構、內插、無模型 IV 等）——另一份研究在做。
- **Long Call vs Spread 比較**、**跨劇本比較**——需求方保留為後續
  獨立討論。
- 「我們每天自己存 chain」方案——需求方明文不採，本文只在各 bulk
  來源處標記衝突，不評估自存架構。

## 7. 查證限制（未經原件查證的關鍵數字）

本輪 WebFetch 對 vendor 網域實測 `EGRESS_BLOCKED`（§0），以下全部
只有搜尋索引轉述，**採用前需以原件或實測覆核**；價格查證日期均為
2026-08-07：

- **ORATS**：訂閱層級與價格（US$49/月 vs US$199–299/月 vs
  US$399/年三說並存）；3:46 ET 快照口徑的官方原文；6000 列上限與
  100 req/min。
- **Market Data App**：付費層價格（本次轉述 US$12／30/月，與前次
  研究記錄的結構不一致）；歷史回溯 2005 vs 2010 的官方矛盾；
  歷史序列查詢的 credit 扣法；免費層能否查歷史。
- **Alpha Vantage**：`HISTORICAL_OPTIONS` 免費層資格（兩輪研究、
  四個以上二手來源仍互相矛盾）。
- **Theta Data**：層級價格（US$40/80/160 vs US$25/60 兩說）；是否
  存在不經本機 Terminal 的官方雲端 REST。
- **Cboe**：DataShop 對單標的短區間 ad-hoc 的實際單價（SEC 文件的
  US$400/500 數字出自特定產品費率表，不必然適用）；All Access API
  各層級價格與扣點表；其歷史回溯年限。
- **Polygon/Massive**：歷史 quotes 端點落在哪個訂閱層；quotes 實際
  起始日（"~2022" 為轉述）。
- **IVolatility**：pay-per-use 計價單位；cloud API 的查詢粒度。
- **Intrinio**：EOD 歷史是否含收盤 bid/ask；各套餐實價。
- **Databento**：OPRA 歷史每 GB 費率；單標的單日成本量級。
- **EODHD**：API 呼叫額度上限（「generous」無具體數字）。
- **Barchart**：`getEquityOptionsHistory` 歷史年限。
- **FlashAlpha**：per-contract 歷史 bid/ask 是否可取；價格
  （US$63 vs 79/月）。
- **所有 vendor**：display／再散布授權條款原文（「能否展示給使用者」
  一律未能從條款原件確認）。
- **沙箱連不到 ≠ production 連不到**：本文沒有任何一句用沙箱封鎖
  推論 vendor 端點在 production 的可達性；採用前依本 repo 慣例
  （#74 的探測程序）在 production 實打。

## 8. 引用清單

一手官方頁（皆被沙箱擋，內容為搜尋索引轉述）：

- ORATS：https://orats.com/data-api 、 https://orats.com/docs/historical-data-api 、 https://docs.orats.io/data-api-guide/data.html 、 https://orats.com/near-eod-data 、 https://orats.com/one-minute-data
- Cboe：https://datashop.cboe.com/option-quotes-end-of-day-with-calcs-yearly-subscription 、 https://datashop.cboe.com/option-eod-summary 、 https://datashop.cboe.com/product-launch-cboe-all-access-apis 、 https://api.livevol.com/v1/docs/Help?apiGroupName=allaccess 、 https://datashopcert.livevol.com/all-access-apis-pricing
- Alpha Vantage：https://www.alphavantage.co/documentation/
- Polygon/Massive：https://polygon.io/docs/rest/options/trades-quotes/quotes 、 https://massive.com/docs/rest/options/quotes 、 https://massive.com/docs/rest/options/snapshots/option-chain-snapshot
- Theta Data：https://www.thetadata.net/pricing 、 https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html 、 https://www.thetadata.net/options-data
- Market Data App：https://www.marketdata.app/docs/api/options/quotes 、 https://www.marketdata.app/data/options/ 、 https://www.marketdata.app/docs/account/plan-limits/ 、 https://www.marketdata.app/pricing/
- IVolatility：https://www.ivolatility.com/data-download-intro/ 、 https://www.ivolatility.com/historical-options-data/ 、 https://www.ivolatility.com/data-cloud-api/
- Intrinio：https://intrinio.com/options/eod-historical-options 、 https://intrinio.com/guides/options-bronze 、 https://intrinio.com/guides/options-silver
- EODHD：https://eodhd.com/marketplace/unicornbay/options 、 https://eodhd.com/lp/us-stock-options-api
- Barchart：https://www.barchart.com/ondemand/api 、 https://www.barchart.com/ondemand/api/getEquityOptionsHistory
- Databento：https://databento.com/datasets/OPRA.PILLAR 、 https://databento.com/blog/opra-migration 、 https://databento.com/blog/introducing-new-opra-pricing-plans 、 https://databento.com/blog/opra-improvements-coming-soon
- bulk 檔案商：https://www.optionsdx.com/ 、 https://firstratedata.com/options-data 、 https://firstratedata.com/b/49/historical-options-data 、 https://optiondata.org/
- Tradier：https://documentation.tradier.com/brokerage-api/markets/get-history
- FlashAlpha：https://flashalpha.com/docs/api 、 https://flashalpha.com/pricing
- SEC 費率文件：https://www.sec.gov/files/rules/sro/cboe/2015/34-74159-ex5.pdf

二手：

- https://brokers-exchange.com/orats-review/ （ORATS 價格）
- https://www.findmymoat.com/tools/alpha-vantage （Alpha Vantage 免費層現狀）
- https://www.g2.com/products/intrinio-financial-data-api/pricing （Intrinio 價格帶）
- https://www.quantconnect.com/docs/v2/lean-cli/datasets/theta-data （Theta Terminal 常駐前提）
- https://www.macroption.com/yahoo-finance-options-python/ 、 https://github.com/ranaroussi/yfinance/discussions/2078 （Yahoo 無歷史鏈）
- https://flashalpha.com/articles/flashalpha-vs-polygon-options-data-raw-vs-computed 、 https://flashalpha.com/articles/flashalpha-vs-thetadata-options-greeks-iv-api （同業對比，行銷內容、僅取可交叉驗證處）
- https://readmedium.com/how-to-download-free-historical-eod-options-data-84d72ab8a404 （optionsDX／historicaloptiondata 引介）
- https://www.quantvps.com/blog/download-historical-options-data 、 https://www.quantvps.com/blog/best-apis-for-historical-options-market-data-volatility （綜述類，僅作線索）

本 repo：

- `docs/research/option-chain-data-sources.md`（即時鏈評選；Alpha Vantage
  免費層矛盾的首次記錄；Market Data App credit 制的即時面判定）
- `docs/research/cboe-field-semantics.md`（Cboe 欄位語意；`iv=0` 哨兵值）
- `docs/research/interest-rate-source-selection.md`（取材限制聲明慣例；
  Alpha Vantage 全站共用配額的前例）
- `option_chaser/data/cboe.py`（現行 per-contract 資料形狀：bid/ask/iv/
  greeks/OI/volume）、`option_chaser/service.py`（`fetch_chain`／估值
  輸入口徑）
