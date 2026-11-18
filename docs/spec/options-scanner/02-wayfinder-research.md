# 選擇權機會搜尋器 — Wayfinder 研究報告

> OPTION-CHASER-SCANNER-DESIGN-WAYFINDER-003。回答 Owner 的七個研究問題。
> 地圖：[Wayfinder Map：選擇權機會搜尋器](https://github.com/L26041040/option-chaser/issues/379)。
> 程式位置以 commit `6108fa8`（master）之後的工作分支為準，行號可能隨後續提交位移。
>
> **證據標籤**：〔程式〕本 repo 實際程式碼／〔文件〕本 repo 既有研究或 ADR／
> 〔外部〕資料源官方文件或二手資料（詳見 `docs/research/analyst-price-target-data-sources.md`）／
> 〔推測〕老弟的推論，未經量測。

---

## Q1. 哪些既有選擇權計算、窮舉、排序功能可以重用？

**結論：選擇權部分幾乎全部可以重用，不需要重寫任何計算。** 現有引擎的輸入正好是
「標的＋目標價＋目標月份＋策略家族」，輸出正好是搜尋器要的成本、損益、報酬倍率與排序。

| 需求 | 既有能力 | 位置 |
|---|---|---|
| 給一個劇本跑完整分析（不必先存成劇本） | 內部接縫 `_analyze(symbol, target_price, target_month, strategies, best_price, worst_price, snap)`，回傳 view 與快照；可傳入已抓好的鏈 | 〔程式〕`api_app/main.py:1836` |
| 引擎入口（記憶體中的快照，不碰檔案系統） | `run_with_snapshot()` → `_analyze()` | 〔程式〕`option_chaser/service.py:1392`、`:1240` |
| 方向自動判定（看漲／看跌／持平） | `derive_direction(target_price, spot)`、`subtype_eligible()` | 〔程式〕`option_chaser/models.py:331`、`:342` |
| 策略家族與子型 | `FAMILIES = ("single-leg", "vertical-spread", "butterfly")`、`FAMILY_SUBTYPES` | 〔程式〕`option_chaser/models.py:233`、`:252` |
| 目標月份 → 實際到期日 | `calendar_anchor()`（該月第三個星期五）＋`select_expiries()`（六點規則：baseline＋前後各 2，最多 5 檔） | 〔程式〕`option_chaser/timeframe.py:87`、`:121` |
| 窮舉 | 單腿（`_single_leg_result`）、價差配對（`generate_spread_pairs`）、Butterfly 三腿（`generate_butterfly_triples`） | 〔程式〕`option_chaser/service.py:748`、`:860`、`:966`；`option_chaser/filters.py:280`、`:312` |
| 報價健全性與流動性過濾 | `apply_filters()`、`quote_ok()`、`iv_ok()`、`is_spread_wide()`；門檻 `max_spread_pct = 0.15`、`spread_floor = 0.10` | 〔程式〕`option_chaser/filters.py:160`、`:108`、`:127`、`:63`；`option_chaser/models.py:159` |
| 成本（最差可成交價） | 單腿＝ask；價差＝買腿 ask − 賣腿 bid（`net_worst`） | 〔程式〕`option_chaser/ranking.py:42`、`:184` |
| 目標價情境報酬（主排名數字） | `baseline_return()`、`spread_baseline_return()`、`butterfly_baseline_return()` | 〔程式〕`option_chaser/ranking.py:42`、`:184`、`:214` |
| 任意價位的報酬（三價位對照） | `return_at_price()`；劇本的 `best_price`／`worst_price` 已是既有欄位 | 〔程式〕`option_chaser/ranking.py:47`；`option_chaser/models.py:110` |
| 每個家族的代表候選摘要 | `ComparisonRow`（策略、標籤、到期日、成本、`baseline_return`、損益兩平、最大獲利）由 `_comparison()` 產生，已在 view 的 `comparison` 欄位 | 〔程式〕`option_chaser/service.py:266`、`:1082`；`option_chaser/store.py:783` |
| 單次分析的時間保護 | `ANALYSIS_SOFT_DEADLINE`（45 秒）逐家族檢查 | 〔程式〕`option_chaser/service.py:72` |

**需要注意的既有決策**

- 未平倉量與成交量**已經不是**過濾門檻（FB5-01）；現有的流動性過濾只有報價健全性與買賣
  價差上限。「排除流動性差的組合」目前等於這兩項。〔程式〕`option_chaser/models.py:156`
- 既有實測：極便宜的合約會讓報酬率失真（成本 $0.10 的價差報酬率 1900%，成本差 1 tick 就掉
  667 個百分點）。跨標的排序時這個問題會被放大，所以「最低成本」是值得新增的條件。
  〔文件〕`docs/research/option-liquidity-filtering.md`
- 完整 view 很大：三個家族約 12 MiB／次。搜尋器只需要 `comparison` 摘要列，**不應該**把每檔
  的完整 view 存進資料庫。〔文件〕`docs/research/market-data-lifecycle-scaling.md:715`
- 公開的一次性分析端點 `POST /api/analyze` 已因安全理由移除（任意 symbol 就打一次上游的
  攻擊面）。搜尋器的新端點必須有自己的額度控制，不能重開同一個洞。
  〔程式〕`api_app/main.py:2859`

**真正需要新寫的只有三塊**：共識計算、分析師資料源 adapter 與快取、把多檔結果合併排序的
一層薄邏輯（加上 Settings 與頁面）。

---

## Q2. 分析師個別目標價及歷史紀錄的資料源、成本與覆蓋率

（本節由研究票
[研究：分析師個別目標價資料源](https://github.com/L26041040/option-chaser/issues/380)
回填，完整內容見 `docs/research/analyst-price-target-data-sources.md`。）

**結論（查證日 2026-11-18；價格與條款會變，採用前要重查）**

1. **做得到，而且歷史深度足夠**：平價價位有現成的「個別目標價＋歷史」。
2. **最大的問題不是技術，是授權**：**沒有任何一家的自助方案允許把資料或衍生數值顯示給公開
   網站的使用者**。正式對外一定要另外談授權，這是成本最大的未知數。

| 資料源 | 個別目標價 | 歷史深度 | 現成的標準差序列 | 最低價位 | 每日更新 500 檔 | 自助方案能否對外顯示 |
|---|---|---|---|---|---|---|
| **Benzinga Analyst Ratings（經 Massive，原 Polygon.io）** | ✅ 分析師與券商都有穩定 ID、發布日、目標價、前次目標價、**已做分割調整的目標價**、終止覆蓋的動作 | **2011-12-08 起** | ❌（要自己算） | **US$99／月** | **1 次呼叫**（依更新時間增量抓） | ❌ 標明 Individual use only；Business 版要報價 |
| **FMP＋TipRanks add-on**（2026-07-29 公告） | ✅ 有現成的「指定日期、每位分析師一列」端點，形狀幾乎就是共識計算的輸入 | **3 年**（更早要 Enterprise） | ❌ | 未公開 | 1～2 次（批次）或 500 次 | ❌ 條款明文禁止，且涵蓋衍生資訊 |
| **Zacks 共識序列（經 Intrinio）** | ❌（只有共識） | 自 1997-12（Zacks 自家檔）；Intrinio 版深度未查證 | ✅ **平均、標準差、分析師人數、最高、最低** | **US$1,250／月起**（Enterprise） | 數次呼叫 | ✅ 這是唯一查到「標準差＋商業顯示權」有公開價格的組合 |
| Finnhub、Twelve Data、EODHD、Alpha Vantage、yfinance | 多數只有共識值 | 不足或不明 | ❌ | — | — | ❌ |
| LSEG I/B/E/S、FactSet、S&P、Bloomberg | ✅ | 約 1999 起 | ✅ | 機構合約 | — | 依合約 |

〔外部〕全部出自 `docs/research/analyst-price-target-data-sources.md`，該文件逐項標註
原件／轉述／未查證並附來源連結。

**對先前認知的兩個修正**

- FMP 原本的個別目標價端點已變成 legacy，2025-08-27 起只對舊帳號開放；公開文件已沒有這個
  端點，取而代之的是 TipRanks add-on。先前文件寫的「FMP 歷史自 2021 年起」今天無法核對。
- I/B/E/S 的歷史改寫今年還在發生：2026-06 的更新整批移除了兩家券商的明細（含目標價）。
  這也說明「自己每日保存算出來的分歧度」有實際價值。

**對施工的含意**

| 階段 | 最省錢的路 | 限制 |
|---|---|---|
| 原型與自用（約 50 檔起） | Massive／Benzinga US$99／月，月繳 | 僅限個人使用：功能只能開給 Owner 自己（Super User），不能對公開使用者顯示 |
| 正式對外（500 檔每日） | 向 Massive／Benzinga Business、FMP Enterprise＋TipRanks 詢價；Intrinio 約 US$15,000／年是已知上限 | 詢價時要問清楚「只顯示衍生數值（平均目標價、分歧度、是否通過）」是否有較低的授權價 |

- **第一關（自身歷史百分位）在技術上可行**：Benzinga 的歷史從 2011 年起，足夠為每檔股票重建
  十年以上的月度分歧度序列；分割調整與終止覆蓋的標記也都有。
- **ETF**：查到的所有來源都只有個股層級的目標價，沒有任何一家提供 ETF 的分析師目標價
  （通則性判斷，未逐家確認）。ETF 必須另外規劃，與 Owner 的指示一致。
- **自行保存快照的價值與限制**：能得到真正「當時看得到」的資料並可稽核；但不能回補過去，
  而且部分條款（例如 FMP）要求終止合約時刪除快取與衍生資料。

**未能查證**：FMP TipRanks add-on 與 Massive／Benzinga Business 的價格；TipRanks「有效」的
定義與分割調整；各家對 S&P 500 逐檔的實際覆蓋率；Zacks 共識納入規則；Finnhub 價格。
Benzinga、TipRanks、MarketBeat 的網站擋掉了自動讀取，相關說法只到二手層級。

**本 repo 內的既有相關事實**

- 專案已經有 Financial Modeling Prep 的 adapter 形狀與金鑰慣例：配息資料的備援鏈
  Yahoo → FMP → Nasdaq，金鑰走環境變數 `FMP_API_KEY`，未設定就略過。
  〔程式〕`option_chaser/data/dividends.py:41`、`:85`
- 使用者自備金鑰的機制也已存在（Market Data App 的 Provider credential），可作為另一種
  金鑰模式。〔程式〕`api_app/providers.py:39`

---

## Q3. 股票自身歷史百分位與絕對門檻如何可靠計算？

**絕對門檻**很單純：`D = 標準差 ÷ 平均`，與門檻比較即可。可靠性只取決於「目前有效的個別
目標價」這份清單乾不乾淨。

**自身歷史百分位**需要每檔股票的歷史分歧度序列。做法：

1. 取得該股票歷史上全部的個別目標價（分析師、目標價、發布日）。
2. 對過去每個取樣日 *t*（建議月底）：每位分析師取 *t* 當時最新的一筆，剔除超過有效期的，
   算出當時的 `D_t`。因為只用發布日 ≤ *t* 的資料，這個序列是「當時看得到的樣子」。
3. 百分位＝序列中 `D_t ≤ D_今天` 的比例。

**會讓它不可靠的因素與對策**

| 因素 | 影響 | 對策 |
|---|---|---|
| 歷史太短 | 取樣點少，百分位跳動大；20% 門檻在 24 個點上只是「最低的 4～5 個」 | 設最短歷史（建議 24 個月度點）；不足時不通過第一關，不硬算 |
| 舊目標價沒被移除 | 過期的目標價會虛增分歧度，而且歷史與現在的虛增程度不同 | 明確的有效期規則，歷史與現在用**同一條** |
| 分析師人數變動 | 人數少時標準差不穩 | 最低人數規則同時套用在歷史每個取樣點；不達標的點不計入序列 |
| 股票分割 | 分割前後的目標價混在同一組會讓分歧度暴增 | 目標價先換算到同一基準再計算 |
| 資料源事後改寫或刪除舊紀錄 | 歷史序列會悄悄改變 | 每日保存自己算出的分歧度快照；之後的歷史以自己的快照為準 |
| 取樣點高度自相關 | 相鄰月份的分歧度很像，「60 個點」的資訊量小於 60 | 不影響門檻的定義，只影響解讀；不需要為此加模型 |
| 樣本或母體標準差 | 人數少時差異明顯（5 人時差約 12%） | 擇一並固定，歷史與現在一致 |

**誠實的限制**：這兩道門檻量的是「共識程度」，不是「預測準確度」。它們算得可靠，不代表
平均目標價會成真。

上述規則的具體數值是決策票
[共識計算的資料品質與歷史取樣規則](https://github.com/L26041040/option-chaser/issues/385)
的內容。

---

## Q4. 12 個月目標價如何對應現有月份劇本及到期日？

**現有機制已經處理了「月份 → 到期日」**：劇本只有月級的 `target_month`；引擎用該月第三個
星期五當日曆錨點，選距離最近的實際到期日當 baseline（同距取較晚者），再加前後各兩檔。
〔程式〕`option_chaser/timeframe.py:87`、`:121`

所以搜尋器只需要決定**目標月份**，三個候選見設計文件 §3.2。補充事實：

- 月份已過完的劇本會被拒絕（`ensure_month_open()`）；系統產生的目標月份一定在未來，不會
  撞到這條。〔程式〕`option_chaser/timeframe.py:99`
- 12 個月後附近的到期日通常比近月稀疏〔推測：一般只有季月與一月的長天期合約〕。六點規則
  仍會選出最多 5 個實際到期日，但 baseline 可能與目標月份差一兩個月。現有畫面已經會顯示
  每個到期日與目標月份的距離（`buffer_days`）。〔程式〕`option_chaser/service.py:258`
- 方向由目標價相對現價自動決定，所以平均目標價低於現價的股票會自然得到看跌結構，不需要
  另外處理。〔程式〕`option_chaser/models.py:331`
- 不需要新增日級的時間概念；`CONTEXT.md`「不要說目標日期」的紀律維持不變。

決策票：[12 個月目標價如何對應目標月份](https://github.com/L26041040/option-chaser/issues/381)。

---

## Q5. 大量股票搜尋的 API 成本、執行時間與快取方案

**兩段成本要分開看。**

### 5.1 共識數值（每檔股票、與使用者無關）

- 平均目標價、分歧度、歷史百分位對所有使用者都一樣；使用者的兩個門檻只是讀取時的比較。
  所以**全站每天算一次**，存進共用快取即可。
- 既有的同型做法：配息資料的 `dividend_cache`（每個 symbol 一列、`market_day`／
  `attempted_day` 保證每個交易日最多抓一次、保留上一份成功資料）；無風險利率由每日 cron
  `GET /api/cron/warm-rate-cache` 預熱。
  〔程式〕`api_app/storage/postgres.py:158`；`api_app/main.py:1971`；`vercel.json`
- 呼叫量取決於資料源是否有批次端點；逐檔端點＝每日約 500 次呼叫。〔外部，見 Q2〕

### 5.2 選擇權搜尋（只對通過門檻的股票）

- 抓鏈：Cboe 延遲報價，**一次 GET 回傳一檔股票的全部到期日**，逾時 15 秒，無金鑰、無 SLA，
  已有 429 退避。〔程式〕`option_chaser/data/cboe.py:24`
- 每次真正的上游呼叫都會計入全站每日額度 `GLOBAL_VENDOR_DAILY_BUDGET`（預設 2000）。
  搜尋 50 檔＝至少 50 次，佔 2.5%；搜尋 500 檔＝25%。**所以選擇權搜尋應該只對通過共識門檻的
  股票做**，這也是兩段式設計的原因。〔程式〕`api_app/main.py:259`、`:1091`、`:1769`
- 執行時間：函式上限設定為 60 秒（`vercel.json` `maxDuration`），一輪刷新預算 45 秒，
  每次回應只處理一個 symbol 分組，其餘放進 `remaining` 由前端續跑。搜尋器可以用**同一個
  模式**：每次呼叫處理一檔，結果逐檔送達。
  〔程式〕`api_app/main.py:214`、`:228`、`:3272`；`src/App.tsx:287`
- 單檔分析實際耗時**沒有既有量測數字**；只知道安全上限是 45 秒、三個家族的 view 約 12 MiB。
  〔文件〕`docs/spec/scaling-foundation.md:483`（明言沒有延遲基準線）。需要在 P0／P3 量測。
- 鏈的共用只存在於單次呼叫之內，不跨呼叫快取（ADR-0001：跨呼叫快取整條鏈被證實是純增
  成本）。搜尋器不應該重新引入整條鏈的資料庫快取；要快取的是**每檔的摘要結果**（很小）。
  〔文件〕`docs/adr/0001-chain-sharing-within-run-only.md`

### 5.3 平台限制

- Vercel Hobby：cron 每天最多一次、觸發時間有 ±59 分鐘誤差；函式最長可設到 300 秒（本專案
  目前自行設為 60 秒）。〔文件〕`docs/research/public-beta-platform-facts.md` §1.1、§1.3
- 每日 cron 一次跑不完 500 檔時，需要分段接續（例如每次處理一批、記錄進度，隔日或由下一次
  使用者請求接續），或調高 `maxDuration`。這是決策票
  [執行模型、使用權限與成本上限](https://github.com/L26041040/option-chaser/issues/386)
  的內容。

### 5.4 粗估（全部為推測，P0 會量測取代）

| 項目 | 估計 | 依據 |
|---|---|---|
| 通過兩道門檻的比例 | 約 5%～10%（500 檔中 25～50 檔） | 第一關平均約 20% 通過；第二關再擋掉一部分。**純推測** |
| 一次使用者搜尋的抓鏈數 | 25～50 次 | 同上 |
| 一次搜尋總時間 | 數分鐘（逐檔出現） | 每檔一次呼叫；單檔耗時未量測 |

---

## Q6. Settings、操作流程、結果頁如何融入現有產品？

| 項目 | 現況 | 搜尋器的接法 |
|---|---|---|
| 路由 | hash 路由：首頁、`#/trash`、`#/settings`、`#/admin`、`#/privacy`、劇本詳細頁 〔程式〕`src/route.ts`、`src/App.tsx:341` | 新增 `#/search`，寫法相同 |
| 導覽 | 手機底部導覽三項（首頁、垃圾桶、設定）；桌面頂欄 〔程式〕`src/BottomNav.tsx:44` | 多一個項目 |
| 設定的儲存 | `owner_settings` 每個使用者一列，內容是 JSON（目前兩個鍵：`market_data`、`historical_iv`） 〔程式〕`api_app/storage/postgres.py:586`、`:1904` | JSON 多一個鍵即可，**不需要改資料表結構**；既有列讀回來沒有這個鍵時用預設值 |
| 設定的 API | `GET／PUT /api/settings`，`SettingsRequest` 目前兩個欄位 〔程式〕`api_app/main.py:508`、`:3879` | 新增選填欄位（additive，既有呼叫端不受影響） |
| Settings 頁 | 角色分層：Normal 只看得到刪除資料／免責聲明／登入；Super User 才有 Data／API 區塊 〔程式〕`src/Settings.tsx:138`、`:231` | 「機會搜尋」區塊放哪一層，取決於誰可以用（決策票） |
| 劇本額度 | 匿名使用者最多 10 個進行中劇本 〔程式〕`api_app/main.py:252` | 搜尋結果**不自動存成劇本**；使用者點「存成劇本」才建立，受同一個額度限制 |
| 詳細頁 | Heatmap、家族分頁、三價位對照、Historical IV 等 | 存成劇本後直接沿用，零改動 |
| 逐檔出現的進度 | 既有的「更新中」徽章與續跑迴圈 | 沿用同一套呈現語言 |

`CLAUDE.md` §3 規定不得漂移的產品語意（劇本建立與所有權、刷新時機、候選產生與排名、
權限矩陣、額度與熔斷、既有 API 契約）——上述接法**都不觸碰**：搜尋器是新增的路由與端點，
共識劇本只有在使用者主動存檔時才變成普通劇本。

原型票：[搜尋頁、結果頁與 Settings 的原型](https://github.com/L26041040/option-chaser/issues/388)。

---

## Q7. 最低成本、最少改動的施工分期與驗收方法

見 [`03-construction-plan.md`](./03-construction-plan.md)。摘要：

- P0 離線量測（不進產品程式）→ P1 共識純函式 → P2 資料源與共用快取 → P3 搜尋後端（重用
  `_analyze()` 與續跑）→ P4 Settings → P5 頁面 → P6 擴到 500 檔。ETF 另案。
- 最關鍵的驗收是 P3 的**等價性測試**：搜尋器對某檔股票的結果，必須與手動建立相同劇本的結果
  逐欄相同——這保證搜尋器沒有偷偷改變任何金融計算。

---

## 查證狀態

| 項目 | 狀態 |
|---|---|
| Q1、Q4、Q5（程式位置）、Q6 | 已實際讀過程式碼 |
| 單檔分析耗時、通過門檻的比例 | **未量測**（P0） |
| 12 個月後到期日的稀疏程度 | 推測，未用實際鏈驗證 |
| 資料源價格、歷史深度、授權 | 2026-11-18 查證；逐項標註見 `docs/research/analyst-price-target-data-sources.md`；Business／Enterprise 價格未公開 |
