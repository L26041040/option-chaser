# 小型 SaaS 維運儀表板與可觀測性——Anonymous Public Beta

> 本文件回答 issue #278（Wayfinder 地圖 #272「Anonymous Public Beta」
> 子票）：產品要開放給陌生人（每個瀏覽器一個 cookie 識別的匿名
> owner，無登入）之後，Owner 想要一個維運儀表板，但 Owner 已經明確
> 提醒——**「不要把『Superuser』理解成預設能看所有 user private
> data」**。本輪把「Admin 需要系統健康／聚合可見度」與「Admin 能讀取
> 特定使用者的私有資料」當成兩個完全不同的權限層級／功能，逐項標明
> 下面想要的指標哪些只碰聚合／系統層資料（對隱私零風險）、哪些會碰到
> per-user 私有資料。**這張票只查事實、只做分類建議，不做決定、不寫
> code**——每一項平台能力／價格／限制都附官方出處與查閱日期（今日
> 2026-09-11），查不到或第三方轉述的一律標明等級或 UNVERIFIED。

## 給 Owner 的白話摘要

現有系統其實已經解決了這題的一大半，只是還沒有人把它們接成一個
「儀表板」。`operational_metrics` 表（SCALE-08）已經在記錄抓價次數、
429 次數、刷新耗時；`chain_backoff` 表（SCALE-04/05）已經在算「連續
失敗幾次算不算事故」；`diagnostics` 表（DG-01～07）已經在記錄每次
Historical IV 請求發生了什麼。這些全部是**純 Postgres、不分 owner**
或**owner 已隔離**的既有機制，本身就是免費的、已經上線驗證過的。真正
缺的不是「有沒有數字可看」，是「怎麼把它們攤開成一頁能看、能收到通知
的東西」。

第二個重點是：**Vercel 與 Neon 的免費層本身已經內建不少東西，但幾乎
都是「保存期限很短」的即時快照**——Vercel 免費版 Runtime Logs 只留
1 小時、一般 Observability 只留 12 小時，Neon 免費版主控台的歷史圖表
只留 1 天。這剛好解釋了這個 repo 過去為什麼要自己動手做
`operational_metrics`／`diagnostics` 這兩套東西：平台免費層拿不到
「這七天發生了什麼」，只有「現在這一刻」。所以本輪判斷：**繼續自己存
是對的方向，不是重造輪子**，只是量體目前還太小（七類）、缺「使用者
帳號」這個維度，也還沒有一個看得到的畫面。

第三個重點是分類——想要的指標分成兩種完全不同的東西：**「系統健不
健康」**（抓價次數、429、DB 大小成長）是聚合數字，完全不碰任何一個
使用者的內容，加了不會有隱私問題；**「多少人在用」**（DAU/WAU、
Scenario 數）對「匿名 cookie」這種身份要小心定義，否則一個人清一次
cookie 就會被算成兩個「新用戶」，數字會虛胖；至於「某個特定陌生人的
劇本內容出了什麼問題」——這才是真正會碰到 private data 的一塊，本輪
判斷**現階段完全不需要**，Admin 不需要、也不應該預設能讀到別人的
Scenario 內容才能維運這個系統。

最後，本輪建議：**不需要建一個即時儀表板**。以現在的流量規模，一個
沿用既有 `/api/ops/metrics` 慣例、多包幾個欄位的受保護 JSON
endpoint，加上一支利用既有 Vercel Cron 慣例（每天一次即可，Hobby
方案的每日一次限制剛好夠用）送出的每日文字摘要，外加二到三個「真的
出事才響」的即時警訊（Cboe 連續 429、儲存空間逼近上限），已經足夠。
只有一項東西建議花錢／裝第三方工具：**Sentry 免費層**（每月 5,000 筆
免費，一般小型 Beta 用不完），因為陌生人瀏覽器上發生的真實 JavaScript
錯誤堆疊，這是唯一一件自己土法煉鋼很難便宜複製的事——Owner 過去能
自己開瀏覽器主控台看錯誤，開放給陌生人之後就看不到了。

---

## 目錄

0. [施工前先讀：這個產品已經有的東西](#0-施工前先讀這個產品已經有的東西)
1. [兩類指標為什麼必須嚴格分開](#1-兩類指標為什麼必須嚴格分開)
2. [Vercel／Neon 已經免費內建什麼](#2-vercelneon-已經免費內建什麼)
3. [第三方免費工具能再加什麼](#3-第三方免費工具能再加什麼)
4. [自建 vs 外部工具：逐項分類](#4-自建-vs-外部工具逐項分類)
5. [最小 Dashboard 形狀](#5-最小-dashboard-形狀)
6. [Security／Abuse 訊號：獨立的第三類](#6-securityabuse-訊號獨立的第三類)
7. [Owner 期望項目總表](#7-owner-期望項目總表)
8. [最推薦／次佳／明確不推薦](#8-最推薦次佳明確不推薦)

---

## 0. 施工前先讀：這個產品已經有的東西

這節不是外部研究，是先把 repo 現況核對清楚，避免下面的建議跟已經
存在的東西打架或重造輪子。

### 0.1 `operational_metrics`（SCALE-08／#258）——系統層、不分 owner

`api_app/metrics.py` 定義**恰好七類**指標（有結構性測試鎖住這個數字，
新增第八類會讓 `tests/test_scale08_observability.py` 紅燈）：
`chain_fetch_count`／`chain_429_count`／`stale_serve_count`／
`cold_miss_count`／`refresh_duration_ms`／`table_size`／
`history_read_volume`。前六類經 `record()` 寫進 `operational_metrics`
表（`source`／`symbol`／`bucket` 三個維度，天級聚合，30 天
trim-on-write retention）；`table_size` 是 query-time gauge，即時查
`results`／`snapshots` 兩表的列數與大小，**不持久化、沒有歷史**。

**這張表的設計哲學明文寫在檔頭**：它與 `diagnostics` 是刻意分開的
兩套系統——`diagnostics` 是 owner-scoped 的事件流（「這一次 request
發生了什麼」），這裡是 system-wide 的天級聚合運維計數（「這七天系統
整體發生了多少次什麼」）。這個既有的分工，跟本題「system health vs
per-user 隱私」的分野幾乎是同一條線——`operational_metrics`
**結構上不存 `scenario_id`、`owner_id`，也不存任何報價／合約內容**，
只存 `source`（哪個 vendor）與 `symbol`（哪個標的）兩個維度。這代表
它今天已經是**對 Admin 完全安全、零隱私顧慮**的資料來源，不需要為了
Public Beta 做任何額外的隱私處理就能繼續使用、繼續擴充。

`GET /api/ops/metrics` 端點（`api_app/main.py`）用獨立於一般
API 之外的 `OPS_SECRET` bearer token 保護，fail-closed（未設定或不符
一律 401），一次回應吐出全部七類。

### 0.2 `diagnostics`（DG-01～07／#143，SCALE-06／#256 之後 owner 化）

`api_app/diagnostics.py` 是每次 request 的結構化事件流，`severity`
（info/warning/error）與 `user_facing`（PC-03／#201，是否該讓一般
使用者看到——與 severity 是兩個獨立維度）並存。全域 trim-on-write 上限
200 筆（**不分 owner 共用同一個 200 筆額度**——這點下面 §7 會標成
一個值得注意的既有限制，Public Beta 開放後如果一個匿名 owner 觸發
大量診斷事件，可能把其他 owner 的診斷事件擠出這 200 筆視窗）。

**重要澄清（訂正本票原始描述的一個不精確之處）**：`GET /api/diagnostics`
／`DELETE /api/diagnostics` 兩個端點**確實沒有像 `/api/ops/metrics`
那樣的獨立 secret 閘門**，但自 SCALE-06/SCALE-11（Ownership A-1）之後，
這兩個端點**已經是 owner-scoped**——`list_diagnostics()`／
`clear_diagnostics()` 都帶 `owner=identity_resolver()`，只回傳／清除
呼叫者自己這個 owner 名下的事件。換句話說，今天的實際狀況不是「任何人
都能看到所有陌生人的診斷事件」，而是「任何人只要有辦法讓伺服器認為
他是某個 owner（今天是固定值 `"solo"`，Public Beta 之後會換成
per-cookie 值），就能免驗證地看到／清空**那個 owner 自己的**診斷
事件」——這與整個產品「持有 cookie＝你自己」的匿名身份模型是一致的
（跟能看到／編輯自己的 Scenario 是同一種信任層級），**不是**額外的
隱私破口，但也**不是**一個給 Admin 用的系統層工具——Admin 想要「系統
全域有多少 warning／error」這種聚合視角，今天沒有對應端點，得另外做
（見 §4）。

診斷事件的 `context` 白名單裡包含 `scenario_id`——這代表 diagnostics
事件**可能間接洩漏「這個 owner 有哪些 scenario id」這類準私有資訊**，
若日後要建一個「Admin 能看全站 diagnostics」的端點，必須先決定要不要
連 `owner_id`／`scenario_id` 一起攤開給 Admin看，還是只給聚合計數
（例如「今天有幾筆 warning，分佈在哪些 stage」而不點名是誰）——這正是
Owner 提醒的那條界線，已記錄供 #282／#288 grilling 使用。

### 0.3 `chain_backoff`（SCALE-04／05）——既有的「純 Postgres 計數器」先例

`api_app/chain_backoff.py` 已經有 `INCIDENT_THRESHOLD_FAILURES = 3`
與 `is_sustained_incident()`：連續 3 次 vendor 抓取失敗，就判定為
「sustained incident」，並算出 `blocked_until`／`retry_after_seconds`
供前端顯示倒數。**這是全站第二個「不用 Redis，純 Postgres 表就做到
限流／熔斷計數」的既有先例**（第一個是這個以及 `metrics.py` 的天級
聚合）。這個既有模式對「要不要為了濫用防護／即時警訊另外裝一套外部
工具」這個問題非常關闎——見 §6。

### 0.4 身份現況（`api_app/identity.py`）

今天 `default_identity_resolver()` 回傳寫死的 `SOLO_OWNER = "solo"`；
Public Beta 需要換成 per-cookie 值（#275 的研究範圍），本文件假設
這件事會先完成，屆時「Admin」也會是這套機制底下的一個特殊身份（#275
研究建議用獨立於一般 cookie 的專屬 secret，比照本站已有兩次先例的
`CRON_SECRET`／`OPS_SECRET` 慣例）。本文件的儀表板建議都建立在
「Admin 是一個獨立、集中判斷的身份」這個前提上，不在每個 endpoint
各自判斷魔術字串。

---

## 1. 兩類指標為什麼必須嚴格分開

### 1.1 Product usage（產品使用）

**定義上要小心的地方——匿名 cookie 使用者的 DAU/WAU 容易虛胖**：
「一個瀏覽器一個 cookie」這個身份模型，跟有登入帳號的產品最大的差異
是——**cookie 會被清掉，清掉之後再訪等於「新使用者」**。這個現象業界
稱為 *cookie churn*：「當一個 cookie 被刪除、使用者回訪，系統會發一個
新的 cookie ID，可能被誤判成不同的使用者」【業界成熟慣例】
（[Analytics Toolkit — Cookie Churn glossary](https://www.analytics-toolkit.com/glossary/cookie-churn/)，
查閱 2026-09-11；這是 A/B 測試領域的標準詞彙，非官方平台文件，但是
業界公認對「用 cookie 當身份鍵」這件事的標準批評）。對 Option Chaser
而言，這代表：

- **原始的「distinct owner_id count」會系統性高估「真人數」**——同一個
  人在無痕視窗、清過 cookie、或換裝置，會在資料庫裡變成好幾個
  `owner_id`。這件事在 controlled beta（synthetic bot 壓測）階段會被
  進一步放大：**壓測腳本本身就是會產生大量一次性 cookie 的機器人**，
  若不排除，DAU 數字會被壓測期間的流量徹底污染，這正是 Owner 在
  #272 裁示「controlled beta 含 synthetic users/bots 壓測」時特別
  點名的情境。
- **建議的緩解方式（判斷，非查證）**：(a) 用「這個 owner 名下至少有
  一個非空的 Scenario，或至少呼叫過一次 refresh」當「active」的門檻，
  而不是「這個 cookie 存在」本身——純粹「建立了 cookie 但什麼都沒做」
  的訪客不計入 DAU；(b) 明確標記 controlled-beta 階段產生的
  synthetic owner（#276 研究已建議「現在就加標記欄位方便事後整批
  清空」，同一個標記欄位可以順便用來把 DAU 統計排除掉這批流量）；
  (c) 用 median／rolling window 而非單日峰值，稀釋單次 cookie-churn
  尖峰的影響。這些是**本文件的判斷與建議**，屬於【Option Chaser 產品
  選擇】，不是外部平台或研究機構給的標準答案——沒有一個公認的
  「anonymous-cookie DAU」官方公式可以直接照搬。
- **為什麼這件事對本產品實際有意義（不是為了做 vanity metric）**：
  DAU/WAU 唯一會被拿來做的真實決策是——「Public Beta 開放的速度要不
  要放慢／要不要暫停」（跟 Neon 0.5 GB／Cboe 429 全站封鎖窗兩個真實
  瓶頸直接掛鉤，#273 已量化「大概撐得住兩位數量級同時活躍匿名使用者」）
  ——如果 DAU 因為 cookie churn 虛胖兩三倍，會讓 Owner 誤判「已經有
  很多人在用」而提早做出不必要的擴充平台決策，或反過來因為數字看起來
  嚇人而不敢繼續開放。這不是好看的儀表板裝飾，是一個真的會被拿來做
  go/no-go 判斷的數字，算錯的代價是真的決策錯誤。
- **Bot 流量**：Vercel Web Analytics 官方文件明確說明它會用
  User-Agent 排除自動化流量（[Vercel Web Analytics — Bots 一節](https://vercel.com/docs/analytics)，
  查閱 2026-09-11：「Web Analytics doesn't count traffic that comes
  from automated processes or accounts. Vercel determines this by
  inspecting the User Agent header」）——但這只對**外部裝飾性訪客
  統計**（頁面瀏覽數）有效，對本產品自己資料庫裡的 `owner_id`／
  `Scenario` 計數完全沒有幫助，因為 controlled-beta 階段故意產生的
  synthetic 壓測流量，如果自己寫的腳本用了正常瀏覽器 UA（或直接呼叫
  API 而非跑瀏覽器），Vercel 的 UA 偵測完全看不到、也擋不掉。**這是
  自建計數必須自己處理 bot／synthetic 排除的原因，不能依賴平台幫忙
  過濾**。

- **新／active Scenario 數、refresh／analysis-run 數**：這兩項不涉及
  「使用者身份」定義問題，純粹是既有資料表上的計數。見 §4，這兩項
  今天幾乎是零成本可得（`Scenario.owner_id`／`created_at` 已存在；
  `refresh_duration_ms` 的 `count` 欄位本身就是刷新次數）。

### 1.2 System health（系統健康）

Vendor 呼叫次數、429／錯誤率、後端延遲、DB 成長率、廢棄 owner／
清理量——這些是**跟「有幾個人在用」完全正交的另一個問題**：即使只有
一個人在用，Cboe 429 全站封鎖窗（SCALE-04 的既有設計是
provider-global、不分 symbol）一樣可能被觸發；DB 儲存成長速度直接
決定 Neon Free 0.5 GB 什麼時候會滿（#273 研究：production-scale
view 剝除 `all_candidates` 之後每次刷新的實測成長率，已有具體數字可
換算撞牆時間）。

**為什麼一定要跟 usage 分開看，不能混在同一組 KPI 裡**：這兩類指標
會導出**完全不同、甚至互相矛盾的行動**。舉一個具體、本產品真的會
遇到的例子——如果只看「DAU 上升」這種正面 usage 指標，看起來一切
順利，理應繼續開放更多人進來；但如果同時 Cboe 429 率也在上升
（system health 指標），繼續開放只會讓封鎖窗被觸發得更頻繁，最終
是**所有**使用者（不只是新進來的）看到全站選擇權鏈抓取失敗。兩類
指標混在一張「本週摘要」裡、沒有清楚區分優先順序，容易讓「用戶變多
了，很好」蓋過「但系統快撐不住了，該踩煞車」——這正是本題要求
「嚴格分開」的實務理由，不是分類潔癖。

---

## 2. Vercel／Neon 已經免費內建什麼

> 全部查閱日期 2026-09-11，出處為官方文件頁面。

### 2.1 Vercel Web Analytics（Hobby 免費）

| 項目 | Hobby | Pro | 出處 |
|---|---|---|---|
| 免費額度 | 50,000 events／月 | 無內含額度，$0.03／1K events | [Pricing for Web Analytics](https://vercel.com/docs/analytics/limits-and-pricing) |
| 保存窗口（Reporting Window） | 1 個月 | 12 個月（Plus 加購 24 個月） | 同上 |
| 超額行為 | **不會被扣款**，3 天寬限期後暫停收集，直到下個帳單週期或升級 | 依用量計費 | 同上 |
| Custom Events | 不支援 | 支援（Plus 版支援更多屬性） | 同上 |
| 隱私模型 | 不用 cookie，用當日重置的請求 hash 識別訪客 | 同 | [Web Analytics 概念頁](https://vercel.com/docs/analytics) |
| Bot 排除 | 用 User-Agent 過濾自動化流量 | 同 | 同上 |

**對本產品的實際限制（判斷，非官方文件明文）**：本站是純前端 SPA
且用 `location.hash`（`#/s/{id}`）做路由（`src/route.ts`），不是
瀏覽器原生的 History API 換頁。Vercel 官方文件只說「後續 page view
透過瀏覽器原生 API 追蹤」，沒有明確寫清楚是否涵蓋 `hashchange`——
**這件事本文件無法從官方文件確認，標記 UNVERIFIED**，值得日後實際
掛上去觀察「切換到 Scenario 詳細頁」算不算一次新的 page view，否則
Web Analytics 對「使用者到底有沒有點進 Scenario 詳細頁」這個本產品
真正關心的問題可能派不上用場，只能看到「首頁被載入了幾次」。

### 2.2 Vercel Speed Insights（所有方案免費，Plus 加購解鎖更多）

| 項目 | 免費（所有方案） | Speed Insights Plus（Pro 加購 $10／專案／月） | 出處 |
|---|---|---|---|
| 額度 | 過去 30 天內 10,000 events，整個 team 共用 | 同樣 10,000 免費，超額 $0.65／10,000 events | [Limits and Pricing for Speed Insights](https://vercel.com/docs/speed-insights/limits-and-pricing) |
| 指標 | 只有 Real Experience Score（RES） | 完整 Core Web Vitals（FCP/LCP/INP/CLS/TTFB） | 同上 |
| 細分 | 只有 path／route 的 Great／Needs Improvement 計數 | 完整細分含 Poor、國家、元素選擇器 | 同上 |
| 時間範圍 | 24 小時、7 天 | 另加 30 天（Pro）／90 天（Enterprise） | 同上 |
| 超額行為 | 暫停收集 14 天 | 不暫停 | 同上 |

這一項跟本題目要求的「vendor 呼叫次數／後端延遲」關係較小（Speed
Insights 量的是前端載入體驗），列在這裡是為了回答「Hobby 上到底有
什麼」，供 §4 決定要不要在 Beta 開站時直接掛上（零成本、幾行 SDK）。

### 2.3 Vercel Observability（所有方案免費，Plus 需付費 Pro/Enterprise）

| 項目 | Hobby | Pro（未加購 Plus） | Pro/Enterprise ＋ Observability Plus | 出處 |
|---|---|---|---|---|
| Runtime Logs 保存 | **1 小時** | 1 天 | 30 天（單次查詢窗最多連續 14 天） | [Observability Plus — Limitations](https://vercel.com/docs/observability/observability-plus) |
| 一般 Observability 保存（traces／build diagnostics） | 12 小時 | 1 天 | 30 天 | 同上 |
| Query／Notebooks | 無法使用 | 無法使用 | 可用，可下 query、存成 notebook | 同上 |
| Functions 延遲細節 | 無 p75、無依 path 細分 | 同左 | 有 p75、可依 path／route 排序 | 同上 |
| Anomaly alerts | 不可用 | 不可用（需另開 Plus） | 可用（含 email 通知） | [Observability 概念頁](https://vercel.com/docs/observability)＋changelog 交叉確認 |
| 價格 | 免費 | 免費 | $1.20／百萬 events | [Observability Plus — Pricing](https://vercel.com/docs/observability/observability-plus) |

**這個對照表直接印證了本站既有架構的判斷是對的**：Hobby 的 Runtime
Logs 只留 1 小時、一般 Observability 只留 12 小時，這代表**如果完全
依賴 Vercel 免費層，Owner 隔天早上就看不到昨天發生了什麼**——這正是
SCALE-08／DG-01～07 兩套系統當初要解決的問題（CLAUDE.md 原文：
「serverless 沒有背景排程可以掛清理 job」「唯一持久線索是
`IvBackfillRun.outcome`」）。換句話說：**Vercel Observability 適合
「剛剛發生的事，現在馬上查」，不適合「本週的趨勢／每日摘要」**——
後者只能靠自己存。

### 2.4 Vercel WAF Rate Limiting 與 BotID（Hobby 已可用，涉及濫用防護，見 §6 交叉引用）

| 項目 | Hobby | Pro | Enterprise | 出處 |
|---|---|---|---|---|
| Rate Limiting 規則數 | 1 條（另有 3 條一般 firewall 規則上限） | 40 條 | 1000 條 | [WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting) |
| 內含請求數 | 1,000,000 允許請求／月 | 依用量計費 | 客製 | 同上 |
| 可用的計數鍵 | **只有 IP、JA4 Digest** | 同左 | 另加 User-Agent、任意 Header | 同上 |
| 計數演算法 | Fixed Window（10 秒～10 分） | 同 | 另有 Token Bucket（最長 1 小時窗） | 同上 |
| BotID Basic（隱形挑戰，抗一般機器人） | **免費**（所有方案） | 免費 | 免費 | [BotID](https://vercel.com/docs/botid) |
| BotID Deep Analysis（ML 進階判斷） | 不可用 | $1／1000 次 `checkBotId()` 呼叫 | 客製 | 同上 |

**關鍵限制，直接影響 §6 的濫用防護設計**：Hobby／Pro 的 WAF Rate
Limiting **只能用 IP 或 JA4 TLS 指紋當鍵**，**不能用 owner cookie
當鍵**（Enterprise 才能用「任意 Header」，理論上可以把 cookie 值
當 header 傳進去比對，但那是 Enterprise 專屬）。這代表 Vercel 邊緣層
的 WAF 完全**看不到、也管不到**「這個 owner_id 已經建了幾個
Scenario」這種應用層身份限流——那必須是應用層（FastAPI middleware
或 handler 內）自己判斷，讀不到 WAF 那一層的資訊。WAF Rate Limiting
能做的、也值得做的，是一層**粗但免費**的「同一個 IP／同一個 TLS
指紋短時間內打太多次」的邊緣防護，跟應用層的「同一個 owner 做太多
事」是互補、不是取代關係。

### 2.5 Vercel Cron Jobs（Hobby 限制，決定「每日摘要」怎麼做）

| 項目 | Hobby | Pro／Enterprise | 出處 |
|---|---|---|---|
| 每專案 cron 數 | 100 個 | 100 個 | [Usage & Pricing for Cron Jobs](https://vercel.com/docs/cron-jobs/usage-and-pricing) |
| 最小執行間隔 | **每天一次** | 每分鐘一次 | 同上 |
| 時間精確度 | ±59 分鐘 | 精確到分鐘 | 同上 |

Repo 現有的 `vercel.json` 已經有一支 cron（`warm-rate-cache`，
`0 11 * * 1-5`，平日一次），本身就是「每天一次」這個 Hobby 限制下
的正常用法。這對本題的意義很直接：**「每日文字摘要」剛好命中 Hobby
方案的甜蜜點**（一天一次是允許的上限，不需要 Pro），但「即時警訊」
（例如連續 429 立刻通知）**不能靠 cron 輪詢**做到（cron 一天最多跑
一次，等於最慢 24 小時才會被看到）——即時警訊必須是「事件發生的當下，
在既有程式碼路徑裡順手觸發一次通知」，不是另外排程輪詢，詳見 §5。

### 2.6 Neon 免費主控台

| 項目 | Free | Launch | Scale | 出處 |
|---|---|---|---|---|
| 主控台圖表歷史保存 | **1 天** | 3 天 | 14 天 | [Neon Monitoring Dashboard](https://neon.com/docs/introduction/monitoring-page)（第三方轉述格式的摘要，內容涵蓋 compute／connections／database size／activity／replication 等既有圖表；本文件未能逐字取得原始 HTML，數字經交叉搜尋確認，信心中等） |
| 內建圖表涵蓋範圍 | RAM／CPU 用量、連線數（含 pooler）、logical data size、deadlocks、row changes、compute cache hit rate 等 | 同左，只是保存更久 | 同左 | 同上 |
| Spending notifications（用量逼近門檻寄 email） | **不提供** | 提供 | 提供 | [Spending notifications](https://neon.com/docs/introduction/spending-notifications)（經 WebSearch 交叉確認：「Spending notifications are available on the Launch and Scale plans」） |
| Consumption limits（主動設定用量上限、超過自動停用 compute） | Free 本身就是固定上限（0.5GB／100 CU-hrs），沒有「額外可調」的空間 | 可自訂低於方案上限的值 | 可自訂 | [Configure consumption limits](https://neon.com/docs/guides/consumption-limits)（標題與存在性經 WebSearch 確認，內文細節本輪未逐字查證，標記 UNVERIFIED） |
| Free 方案硬性上限 | 0.5 GB 儲存／專案、100 CU-hours／月／專案、最多 2 CU（8GB RAM）、10 個 branch、100 個專案、閒置 5 分鐘後 autosuspend | — | — | [Neon Pricing](https://neon.com/pricing)（第三方摘要，經與 CLAUDE.md 既有多次引用的「Neon Free 0.5 GB」數字互相印證，信心高） |

**這一項是本輪最重要的發現之一**：**Neon Free 完全沒有任何用量告警
機制**——不管是主控台通知還是 email，Spending notifications 明文
只給 Launch／Scale 付費方案。這代表「DB 儲存空間快滿了」這件事，
**在 Neon 免費層上，Owner 必須自己主動去查才會知道**，Neon 不會
主動通知。這直接支持 §5 的建議：storage 逼近上限的告警，必須是
Option Chaser 自己（用既有 `table_size` 湊上一個門檻判斷）在
Owner 能看到的地方（每日摘要或即時通知）主動講出來，**不能依賴 Neon
自己會提醒**。同時，Neon 主控台自己的圖表只留 1 天歷史，這又再次印證
「30 天保留的自建 `operational_metrics` 表其實比 Neon 免費版自己的
主控台更有用」這個既有架構決策的正確性。

---

## 3. 第三方免費工具能再加什麼

> 全部查閱日期 2026-09-11。每項工具附（a）官方目前免費層限制，
> （b）什麼資料會離開這台伺服器流向第三方——**這一點請務必跟 #279
> （`docs/research/cookie-consent-analytics-ads-boundaries.md`，
> 尚未完成）交叉參照**，本文件只標出「有沒有資料外流、外流的是什麼
> 類型」的事實，不對消費者同意（consent）機制本身下結論。

### 3.1 錯誤追蹤：Sentry

| 項目 | Developer（免費）方案 | 出處 |
|---|---|---|
| 錯誤事件額度 | 5,000 errors／月 | [Sentry Pricing](https://sentry.io/pricing/) |
| 使用者數 | 1 人 | 同上 |
| 資料回溯窗 | 30 天 | 同上 |
| Performance tracing | 5M spans／月 | 同上 |
| Session Replay | 50 replays／月 | 同上 |
| 預設是否送出使用者 IP／PII | **預設不送**——官方文件明確說明 SDK 預設不傳送 IP，需主動設定 `send_default_pii = true` 才會啟用；敏感 header（如 IP、`Authorization`）預設被過濾 | [Scrubbing Sensitive Data](https://docs.sentry.io/platforms/python/data-management/sensitive-data/)、[Data Collected](https://docs.sentry.io/platforms/python/data-management/data-collected/) |
| Source map／stack trace 還原 | Sentry SDK 的核心能力，非額外付費功能（本輪未逐字找到「免費方案是否限制 source map 上傳筆數」的明文，標記 UNVERIFIED，但以其產品定位判斷應包含在免費層內） | 綜合官方 SDK 文件推斷，非逐字引用 |

**這是本輪推薦的唯一「非本站自建」項目**，理由見 §4——它是唯一一項
「便宜自建很難達到同等品質」的能力：真實使用者瀏覽器上發生的
JavaScript 例外，連同壓縮後程式碼對應回原始檔案行號的能力（source
map），這件事沒有現成、輕量的自建替代方案。5,000 errors／月對一個
低流量 Beta 而言相當寬裕。**隱私交叉點**：預設不傳 IP／PII 這件事
降低了跟 #279 的衝突面，但仍然會把「使用者瀏覽器發生了什麼錯誤、
點了什麼按鈕、瀏覽器版本」這類資訊送到 Sentry 的伺服器——這仍然是
「資料離開本站」，只是不含 IP／個資，`#279` 完成後應該回頭核對這是否
構成需要揭露／取得同意的資料處理。

**次佳替代（自架，未逐字驗證官方文件，來自多篇第三方部落格
交叉比對，信心中等）**：GlitchTip 是一個開源、與 Sentry SDK 相容
（同一組 DSN／SDK，換 endpoint 即可）的輕量自架替代品，宣稱可在
1–2GB RAM 的小型 VPS 上運作。若 Owner 未來希望「一行資料都不外流
到第三方」，這是一個保留選項，但代價是要自己維運另一個服務——與
#273 研究已建立的「現在不建議搬平台／不引入新維運負擔」的判斷方向
不一致，本文件**不建議現在採用**，僅記錄供未來需求改變時參考。

### 3.2 Log／Uptime／告警：Better Stack、Axiom、UptimeRobot

| 項目 | Better Stack（免費） | Axiom（免費，Personal） | UptimeRobot（免費） | 出處 |
|---|---|---|---|---|
| Log 攝入／保存 | 3GB logs，保留 3 天；另有 30GB metrics | **500GB／月**，保留 30 天 | 不適用（非 log 產品） | [Better Stack Pricing](https://betterstack.com/pricing)、[Axiom Pricing](https://axiom.co/pricing) |
| 告警內建 | 有（Slack／email） | 有（含 alerting，Personal 方案即內含） | 有（是它的核心功能） | 同上、[UptimeRobot Pricing](https://uptimerobot.com/pricing/) |
| Uptime 監控數 | 10 monitors + 1 status page | 不適用 | **50 monitors**，5 分鐘檢查頻率，1 個基本狀態頁 | 同上 |
| 額外內含（Better Stack） | 100,000 exceptions／月、5,000 session replays（Better Stack 近年也擴充了錯誤追蹤／replay 產品線） | — | — | Better Stack Pricing |
| 資料外流性質 | Log 內容視你送什麼而定（可能含 request path、錯誤訊息） | 同左 | **與前兩者性質不同**：UptimeRobot 是「從它的伺服器主動打你的網址」做健康檢查，不是「你的伺服器把使用者資料送給它」——這條路徑上**沒有任何真實使用者的資料外流**，純粹是合成的健康檢查流量 | 官方文件描述之產品運作方式 |

**UptimeRobot（或同性質的免費 synthetic uptime 監控）是本輪認為
「值得優先考慮」的一項**，理由很直接：它回答的是一個**自建系統結構上
答不出來的問題**——如果整個 serverless 應用掛掉（冷啟動失敗、DB
連不上、整個 domain 502），本站自己存在 Postgres 裡的
`operational_metrics`／`diagnostics` **同樣連不上、寫不進去**，
Owner 不會知道網站已經死了。外部、跟本站基礎設施完全獨立的健康檢查
是這個情境唯一的解法，這跟 Sentry 是「唯二」需要外部工具的理由
——一個管「應用還活著嗎」，一個管「使用者端出的錯誤細節」，兩者本質
都是「本站自己觀察不到自己」的死角，其餘全部可以自建。

**免費額度而言 UptimeRobot 已經很夠用**（50 個監控點、5 分鐘頻率，
單一網域的 Beta 只需要 1～2 個監控點），且如上表所述**它與使用者
隱私完全無關**，不需要跟 #279 交叉核對。

### 3.3 產品分析：PostHog vs. Plausible／Umami／GoatCounter

| 項目 | PostHog（免費） | Plausible | Umami | GoatCounter |
|---|---|---|---|---|
| 免費額度（雲端版） | 1M events／月、5K session recordings、100K exceptions、1M feature flag 請求 | **無免費雲端方案**，僅 30 天免費試用，之後最低 $9／月（1 萬 pageviews） | 自架版**完全免費**（開源，無事件量上限）；Cloud 版是否有免費 Hobby 層【UNVERIFIED，來自第三方聚合網站，非 umami.is 官方頁面逐字確認】 | Hosted 版對「合理的公開／小型使用」免費（無明確發佈的硬性數字）；自架版完全免費開源 |
| 是否需信用卡 | 不需要 | 試用不需要，之後需訂閱 | 自架不需要 | 免費 hosted 不需要 |
| Cookie 使用 | 依設定，預設不強制無 cookie | **完全無 cookie**，官方明文「不處理個資、不追蹤個別使用者」 | **預設不用任何 cookie**（官方 FAQ 逐字確認） | **不用 cookie 或持久個資識別訪客** |
| IP 位址處理 | **預設會透過 GeoIP 讀取 IP 推算地理位置**，需要主動開啟「IP anonymization」才會把 IP 最後一段歸零或直接捨棄——**與 Sentry 相反，PostHog 的隱私保護是需要主動設定，不是預設關閉** | 官方主張「不離開歐盟伺服器」、無個資處理 | 官方 FAQ 未逐字提及 IP 處理方式（UNVERIFIED） | 官方主張不存個資 |
| 資料存放地 / 自架選項 | 開源、MIT 授權，可自架（Docker Compose） | 開源，可自架，但 Cloud 版明文「只在歐盟伺服器」 | 開源、MIT 授權，可自架 | 開源，可自架 |
| 出處 | [PostHog Pricing](https://posthog.com/pricing)、[Self-host PostHog](https://posthog.com/docs/self-host)、[IP Anonymization](https://posthog.com/docs/cdp/transformations/template-ip-anonymization) | [plausible.io](https://plausible.io/) | [docs.umami.is FAQ](https://docs.umami.is/docs/faq) | [goatcounter.com](https://www.goatcounter.com/) |

**與 #279 的重疊，明確標出**：PostHog（雲端版）預設會抓 IP 做地理
定位、且其定位本來就是完整的產品行為分析（session replay、feature
flag、事件屬性），這一整條路徑**遠比 Vercel 免費 Web Analytics（無
cookie、當日重置 hash）或 Plausible／Umami／GoatCounter（均明文
無 cookie、不存個資）承載更多可能構成「處理個人資料」的內容**。若
Owner 未來考慮上任何一種產品分析工具，**這正是 #279 應該接手判斷
「要不要顯示 cookie／隱私聲明」的地方**——本文件在此只標出「PostHog
雲端版預設抓 IP、Plausible/Umami/GoatCounter 三者官方均聲稱不use
cookie 且不存個資」這個事實對比，不代替 #279 做同意機制的設計判斷。

**本輪判斷（§4／§8 會再收斂）**：以目前「Owner 一人＋剛開放的匿名
Beta」的規模，**這整類「訪客行為分析」工具都不是急件**——它們回答的
是「使用者在網站上做了什麼」這種產品經理視角的問題，跟本題 Owner
真正要的「系統健不健康、有沒有人在濫用」是不同層次的需求。若真的
要選一個，**Plausible／Umami／GoatCounter 這類 cookieless、明文不
存個資的工具，會比 PostHog 更適合搭配一個「還沒決定隱私政策長什麼
樣」的匿名 Beta**——理由不是它們功能比較好（功能遠不如 PostHog），
是它們從架構上就不太需要等 #279 的 consent 設計完成就能先掛上去，
PostHog 若要達到同等的「零隱私顧慮」則需要額外主動關閉 GeoIP／IP
記錄，等於多一道容易忘記做的設定步驟。

---

## 4. 自建 vs 外部工具：逐項分類

依 Owner 想要的每一項訊號逐一分類：**(a) 現有 7 類 catalogue 幾乎
零成本可加**、**(b) 需要新的、但同樣輕量的自架機制**、**(c) 真的需要
外部工具**。

| Owner 想要的訊號 | 分類 | 說明 |
|---|---|---|
| Anonymous-owner 數（新增／累計） | **(a)** | `Scenario.owner_id`（Ownership A-1 既有欄位）已存在——`SELECT COUNT(DISTINCT owner_id)`，不需要新表、新欄位，只需要一個 admin-only 的聚合查詢。定義「active」需要 §1.1 的產品判斷，但**技術上零成本** |
| 新／active Scenario 數 | **(a)** | 同上，`scenarios` 表本身就有 `owner_id`／`created_at`，直接查詢即可 |
| Refresh／analysis-run 次數 | **(a)** | `operational_metrics` 的 `refresh_duration_ms` 這個既有 metric 本身就帶 `count` 欄位——**這件事今天已經在記錄，不需要任何新程式碼**，只是還沒有人把它攤到畫面上 |
| Vendor 呼叫次數／429 率 | **(a)** | `chain_fetch_count`／`chain_429_count` 兩個既有 metric，同上，已經在記錄 |
| DAU/WAU（匿名 owner） | **(b)** | 底層資料存在（同上 owner_id／created_at），但需要一個新的「什麼算 active」的判斷邏輯與（可能）一個小型彙總查詢／view，而不是單純的 `COUNT(DISTINCT)`——尤其要排除 controlled-beta 的 synthetic 流量（需要先有 #276 建議的標記欄位） |
| 後端一般請求延遲（非僅刷新流程） | **(a)／Vercel 免費** | 已存在的 `refresh_duration_ms` 只涵蓋「刷新」這一條路徑；若要看其他 endpoint（例如 `GET /api/scenarios`）的延遲，**短期內 Vercel 免費 Observability（12 小時保存）已足夠做臨時除錯**，不需要立刻自建；若未來想要 30 天趨勢，才需要仿照 `refresh_duration_ms` 的既有寫法擴充成第 8 類 metric（需要先決定要不要打破「恰好七類」的結構性測試） |
| DB 儲存**現況**大小 | **(a)** | `table_size` 既有 query-time gauge 已經算好，`/api/ops/metrics` 已經吐得出來 |
| DB 儲存**成長趨勢**（過去 N 天） | **(b)** | `table_size` 本身刻意不落盤（它是即時 gauge，不是歷史序列）。要看「成長率」而非「現在多大」，需要一個新的、輕量的機制——例如既有 Vercel Cron（每天一次即符合 Hobby 限制）多加一支排程，把 `table_size_metrics()` 的結果寫進一張新的極小表（或擴充現有 catalogue，若決定接受第 8 類）。**Neon 免費版自己的主控台歷史只留 1 天**（§2.6），這件事只能靠自己做 |
| 廢棄 owner／清理量 | **(b)，且被 #276 擋住** | 今天**沒有任何「刪掉一個 owner 全部資料」的操作**（#276 研究已指出這個真缺口：`delete_scenario()` 只清單一劇本，`narrow_history`／`owner_settings`／`owner_credentials`／`owner_verifications`／`diagnostics` 皆無清理路徑）。清理量本身的計數是 trivial（清理批次跑完時 `metrics.record()` 一筆即可），但**前提是清理機制本身要先被 #276 設計出來**——這個訊號不是本票能獨立完成的 |
| 一般錯誤堆疊追蹤（Python 後端 exception） | **(b)** | 目前後端沒有任何「未預期例外」的集中記錄（`diagnostics` 只涵蓋刻意埋點的已知路徑，不是全域 exception handler）。加一個輕量的全域 exception handler，把堆疊摘要（不含完整 traceback 裡可能夾帶的使用者輸入內容）寫進既有的 `diagnostics`（`severity="error"`）或一張新表，屬於「同樣輕量的自架擴充」，不必馬上上 Sentry |
| **真實瀏覽器 JS 錯誤堆疊＋還原到原始碼行號（source map）** | **(c)** | 這是本輪唯一判斷「便宜自建很難達到同等品質」的項目——source map 還原、跨瀏覽器相容的錯誤捕捉（含 unhandled promise rejection、跨 iframe 邊界等邊角案例）是 Sentry 這類工具的核心工程投入，本站自己刻一個輕量版本雖然可行（例如全域 `window.onerror` + 手動上傳到既有 `/api/diagnostics`），但**不會有 source map 還原能力**，除錯價值會大打折扣 |
| 整站是否還活著（uptime） | **(c)** | 結構性理由見 §3.2——自建系統無法觀察「自己已經死掉」這件事，需要外部、獨立於本站基礎設施的健康檢查 |
| 濫用訊號（單一 cookie 密集建立 Scenario／異常刷新模式） | **(b)**，見 §6 | 這是應用層業務規則，沒有一個「開箱即用」的第三方工具懂得「一個 owner 建太多 Scenario」的語意——需要沿用既有 `chain_backoff.py` 的「純 Postgres 計數器」模式自己做，詳見 §6 |

---

## 5. 最小 Dashboard 形狀

### 5.1 受保護的 JSON endpoint（沿用既有 `/api/ops/metrics` 模式）——建議現在就做

延伸既有 `GET /api/ops/metrics`（`OPS_SECRET` bearer token 保護）
的既有慣例，把 §4 分類為 (a) 的項目（幾乎零成本，資料已存在）全部
併進同一次回應，或新增一個平行的 `GET /api/ops/usage` 端點（純
usage 類，與現有 metrics 端點的 system-health 定位分開，呼應 §1
「兩類指標嚴格分開」——即使技術上可以塞進同一個 JSON，回應的**分組
結構**也應該讓兩類指標明顯分開，不要攤平成一個扁平物件）。這是
目前成本最低、風險最低的選項——不需要新的認證機制、不需要前端頁面、
沿用一個已經上線驗證過的模式。

### 5.2 簡單的伺服器渲染 HTML 管理頁——現階段不建議，除非有具體理由

一個純 JSON endpoint 對「Owner 自己用 curl 或瀏覽器開發者工具看一眼」
已經足夠；HTML 頁面的價值在於「不用打字就能看趨勢圖、多人協作看同
一份數據」——對一個**目前只有一位 Owner** 的低流量 Beta，這個投資
報酬率不高。**唯一值得提前考慮 HTML 頁的情境**：如果 Owner 打算讓
除了自己以外的第二個人（例如共同維運者）也能查看儀表板但不方便給
對方 curl 指令，HTML 頁面會比較友善——但這不是目前已知的需求。

### 5.3 每日 email／Slack 摘要——建議現在就做，且是本輪認為最划算的一項

理由直接呼應 §2.5：Vercel Cron 在 Hobby 方案上**本來就只能一天跑一次**
，這剛好等於「每日摘要」需要的頻率，不需要為了更高頻率而升級付費
方案。做法：新增一支 cron（沿用既有 `warm-rate-cache` 的模式），
每天固定時間查詢 §4 分類 (a) 的既有 metric＋(b) 新增的
usage／storage-growth 數字，組成一段純文字（或簡單 Markdown），
用最陽春的方式送出——可以是一個免費方案就有配額的 transactional
email（多數這類服務都有極低流量的免費層，但本文件未逐項查證，
留給施工票具體選型時再查證），或是 Slack Incoming Webhook（免費、
零額度限制，只要 Owner 有一個 Slack workspace）。對比「即時儀表板」，
每日摘要更符合一個**低流量 Beta 的真實查看頻率**——Owner 大概率不會
每小時盯著儀表板看，但看一封「昨天發生了什麼」的信是低摩擦的。

### 5.4 最小告警集合——現在就該有的，vs. 以後再說的

引用 Google 自己發佈的 SRE Workbook 對告警設計的核心原則：好的告警
要同時兼顧 *precision*（響的時候真的有事）與 *recall*（有事時真的
會響），過多、過雜訊的告警只會導致「告警疲勞」而被忽略【業界成熟
慣例，[Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)，
查閱 2026-09-11】。套用在一個目前只有一位 Owner、剛開放陌生人使用
的低流量 Beta，本文件建議把「現在就做」壓到最少、最確定有意義的
幾條，而不是一次做齊：

**現在就該有（建議在開放給真正陌生人之前完成）**：

1. **Cboe 連續 429／sustained incident** —— `chain_backoff.py` 的
   `is_sustained_incident()` **今天已經在計算這件事**，只是目前只
   用來決定前端要不要顯示倒數與鎖定重試鈕。只需要在這個既有判斷
   為真的那個程式碼路徑，多加一個「順手」的副作用（例如打一次 Slack
   webhook），**不需要引入任何新的觀測平台**——這是零額外基礎設施
   成本、卻是最貼近「真的會影響全站每一個使用者」的一條告警。
2. **DB 儲存逼近 Neon Free 0.5 GB 上限的某個百分比**（例如 80%）——
   `table_size` 既有 gauge 已經算得出目前大小，只需要在既有的
   cron（或新增的每日摘要 cron）裡多一個門檻判斷；由於 §2.6 已確認
   **Neon 自己完全不會主動通知**，這條告警若不自己做，Owner 會在
   完全沒有預警的情況下直接看到 Neon 把 compute 停掉。

**看到濫用再做（不必現在就完整實作，但應在架構上預留掛點）**：

3. 單一 owner 短時間內建立異常多個 Scenario 或觸發異常多次
   refresh——見 §6，這需要先有一個「合理範圍」的產品判斷（多少算
   異常），不是純技術問題，建議留給 #277（濫用防護）的 grilling
   票裁示具體門檻後再實作，本文件只確認「機制上可行、且該用既有
   `chain_backoff.py` 那套純 Postgres 計數器模式做」。
4. 一般 HTTP 5xx 錯誤率超過某個門檻——目前後端沒有全域錯誤率統計
   （見 §4「一般錯誤堆疊追蹤」一列），這需要先有 (b) 的輕量機制
   到位才能談告警門檻。

---

## 6. Security／Abuse 訊號：獨立的第三類

Owner 的原始問題把這個獨立列出來，本文件也維持獨立——它跟「everyday
system health」（vendor 有沒有連得上、後端快不快）是不同性質的問題：
system health 關心「系統本身運作正常嗎」，abuse 訊號關心「有沒有人
在**惡意或異常地**使用系統」，兩者的因果方向不同（前者是系統自己的
問題，後者是外部行為者造成的問題），觸發後該做的事也不同（前者通常
是修 bug／擴充資源，後者通常是限流／封鎖／人工介入）。

**上面列出的免費工具，沒有一個天生就懂這類訊號**：

- Sentry／UptimeRobot／PostHog／Plausible 這類工具關心的是「錯誤」
  「網站是否存活」「使用者行為模式」，它們的告警邏輯都是建立在**它們
  自己定義的通用訊號**上（錯誤率尖峰、網站不可達、流量異常），**不
  認得「這個 owner_id 一分鐘內建立了 20 個 Scenario」這種本產品
  自訂的業務規則**。這種訊號的判準完全是應用層邏輯，沒有一個現成
  SaaS 產品能開箱即用地表達它。
- Vercel WAF Rate Limiting（§2.4）能提供的是**粗粒度、IP／TLS 指紋
  層級**的防護，這是有用的第一道邊緣防線，但如上所述**技術上就是
  看不到 owner_id**（Hobby／Pro 方案的計數鍵不含任意 header／
  cookie），無法表達「同一個 owner，換了 IP 一樣要被抓到」這種
  更精準的規則。

**結論：這是一個必須自己做的、獨立的小型機制**，且本站已經有可以
直接沿用的既有模式——`chain_backoff.py` 已經證明「用一張極小的
Postgres 表、記錄 `(鍵, 連續失敗次數, blocked_until)`，不用 Redis」
這套做法在 production 上能跑。同樣的形狀套用在「單一 owner 短時間內
建立過多 Scenario」或「單一 owner 觸發異常多次 refresh」，是同一套
已驗證架構的第三次應用（第一次是 `chain_backoff` 的 vendor
熔斷、第二次是 `operational_metrics` 的天級聚合），不是新技術、也
不是新的維運負擔。**具體門檻數字（多少次算異常）本文件不代為決定**
——這是 #277（濫用防護研究）明確涵蓋的範圍，本文件只確認「機制上
可行、免費、且有既有先例可循」。

---

## 7. Owner 期望項目總表

| Owner 想要的項目 | 建議來源 | 是否卡 Beta 上線 | 備註 |
|---|---|---|---|
| Anonymous-owner 數 | self（既有 `owner_id` 欄位聚合查詢） | 否 | 純聚合，零隱私風險，Admin 可直接看 |
| 新／active Scenario 數 | self（既有 `scenarios` 表） | 否 | 同上 |
| Refresh／analysis-run 次數 | self（`operational_metrics.refresh_duration_ms.count`，**今天已存在**） | 否 | 零額外程式碼 |
| Vendor 呼叫次數／429 率 | self（`operational_metrics`，**今天已存在**） | 否 | 零額外程式碼 |
| DAU/WAU（匿名 cookie） | self，但需先定義「active」＋排除 synthetic 流量 | 否，但建議在**開放給真正陌生人前**先定義好，避免 controlled-beta 壓測數字污染第一批真實數字 | 需與 #276 的 synthetic 標記欄位協調 |
| 後端一般延遲 | Vercel（免費 Observability，12 小時足夠臨時除錯）；長期趨勢才需 self | 否 | 不急，Vercel 免費層已覆蓋「剛剛發生的事」 |
| DB 儲存現況大小 | self（`table_size`，**今天已存在**） | 否 | — |
| DB 儲存成長趨勢 | self（新增：既有 cron 每日快照一筆） | **建議在 public（無限期、對任何陌生人開放）階段前完成**，controlled beta 階段可用既有 gauge 手動量測前後對照 | 呼應 Neon 免費版自己只留 1 天歷史（§2.6）這個事實 |
| 廢棄 owner／清理量 | self，但**被 #276 擋住**（清理機制本身尚未存在） | 否（不是本票能獨立完成的） | 一旦 #276 的清理機制上線，計數是 trivial 附加 |
| 真實瀏覽器 JS 錯誤＋source map | third-party（Sentry 免費層，5,000／月足夠） | **建議在開放給真正陌生人前完成**——Owner 屆時看不到別人瀏覽器的主控台 | 唯一建議付費／裝外部工具的一項（其實免費額度就夠） |
| 整站存活監控（uptime） | third-party（UptimeRobot 免費，或 Better Stack 免費） | **建議在開放給真正陌生人前完成** | 與使用者隱私無關，跟 #279 無交集 |
| 一般後端未預期例外集中記錄 | self（擴充既有 `diagnostics` 或全域 handler） | 建議儘早，非硬性擋 Beta | 目前後端無全域 exception 捕捉 |
| Cboe 連續 429 即時告警 | self（`chain_backoff.is_sustained_incident()` **今天已算好**，只差一個 side effect） | **建議在開放給真正陌生人前完成**，成本極低 | 全站級影響、零新基礎設施 |
| 儲存逼近上限即時告警 | self（`table_size` ＋門檻判斷） | **建議在 public 階段前完成** | Neon 自己完全不會通知（§2.6） |
| 濫用訊號（單 owner 密集建立/刷新） | self（沿用 `chain_backoff` 模式，具體門檻交給 #277） | 建議至少有基本版本在 public 階段前，具體規則不卡本票 | 沒有第三方工具天生懂這個語意 |
| 一般產品行為分析（PostHog 等級） | 明確不建議現在做 | 否 | 見 §8 |

---

## 8. 最推薦／次佳／明確不推薦

### 最推薦方案

**維持「大部分自建」的既有方向，只補兩個外部工具、一個每日摘要、
兩三條即時告警**：

1. 延伸既有 `operational_metrics` 模式，把 usage 類指標
   （anonymous-owner 數、Scenario 數，皆為既有欄位的聚合查詢）與
   一個新的、輕量的 DB 儲存成長趨勢快照（沿用既有 Vercel Cron 模式，
   每天一次剛好符合 Hobby 限制）補齊。
2. 延伸既有 `GET /api/ops/metrics` 模式做一個受保護 JSON endpoint
   （不建 HTML 頁），usage 與 system-health 兩類指標分組呈現、
   不攤平混在一起。
3. 加一支每日摘要 cron（Slack webhook 或低成本 transactional
   email），把上面的數字整理成一段人看得懂的文字。
4. 加兩條「今天就該有」的即時告警——Cboe sustained incident（既有
   邏輯已算好，只差一個 side effect）、DB 儲存逼近 Neon Free 上限
   （新的門檻判斷，邏輯極簡單）。
5. 唯二引入的外部免費工具：**Sentry**（真實瀏覽器錯誤堆疊，本站
   結構性做不到的能力）與 **UptimeRobot 或 Better Stack 免費層**
   （整站存活監控，本站結構性做不到的能力）。兩者皆有充裕的免費
   額度，且後者與使用者隱私完全無關。
6. 濫用／abuse 訊號沿用既有 `chain_backoff.py` 的純 Postgres
   計數器模式自建，具體門檻交給 #277 裁示，不等它完成也可以先把
   機制骨架準備好。

### 次佳方案

若 Owner 對「一行資料都不外流到第三方」有更高的要求，可以把 Sentry
換成自架的 GlitchTip（開源、Sentry SDK 相容，但需要自己維運另一台
小型服務）——本文件不建議現在採用，因為它違背 #273 已建立的「現在
不建議搬平台／不引入新維運負擔」判斷方向，但技術上是可行的備案。
同理，若未來確實需要完整的產品行為分析（session replay、漏斗分析），
PostHog 自架版是比雲端版更貼近隱私要求的次佳選項——但目前判斷完全
不需要走到這一步。

### 明確不推薦方案（及理由）

- **不建議現在採用任何完整的產品分析平台（PostHog 雲端版等）**：
  這類工具解決的是「使用者在網站上做了什麼」這種產品經理視角問題，
  跟 Owner 這次真正要的「系統健不健康、有沒有被濫用」是不同層次的
  需求；且雲端版預設抓 IP 做地理定位，會平白製造一個要跟 #279
  協調的隱私決策點，投入報酬比不成正比。
- **不建議現在建一個即時（例如即時輪詢或 WebSocket 推播）HTML
  管理儀表板**：目前只有一位 Owner、流量低，這類即時性投資在這個
  規模下沒有實際效益，屬於過度工程；一個每日摘要＋JSON endpoint
  已經涵蓋真實的查看頻率。
- **不建議只依賴 Vercel 免費 Observability／Runtime Logs 當唯一的
  系統紀錄**：保存期太短（Hobby 分別只有 12 小時／1 小時），這正是
  本專案當初自建 `operational_metrics`／`diagnostics` 兩套系統要
  解決的問題，繼續依賴平台免費層會讓 Owner 隔天就看不到前一天發生
  的事。
- **不建議引入 Google Analytics 或任何預設用 cookie／跨站追蹤的
  傳統分析工具**：相較於 Vercel 免費、無 cookie 的 Web Analytics
  已經涵蓋「一般流量好奇心」這個需求，額外引入一個隱私模型更重的
  工具，只會增加不必要的 #279 協調負擔，卻沒有帶來本題真正需要的
  新訊號類型。

---

## 附：本輪誠實揭露的不確定項目

- Vercel Web Analytics 對本站 hash-based（`#/s/{id}`）前端路由是否會
  正確計為多次 page view——官方文件未逐字說明涵蓋範圍，標記
  UNVERIFIED，建議實際掛上去後用真實資料核對。
- Neon 主控台監控頁與 consumption limits 頁的完整原文（本輪透過
  WebFetch 摘要與 WebSearch 交叉confirmation 取得核心數字，但非
  逐字段落引用，信心中等，非低）。
- Umami Cloud 是否真有一個免費 Hobby 層、其確切額度——來自第三方
  聚合網站而非 umami.is 官方頁面逐字確認，標記 UNVERIFIED；Umami
  **自架版本身完全免費**這件事則已由官方 FAQ 頁面確認，信心高。
- GoatCounter hosted 版「合理使用」免費的確切數字上限——官方網站未
  發佈明確硬性數字，只有「reasonable public usage」這類定性描述。
- GlitchTip 的所有數字皆來自第三方部落格與比較網站，非其官方文件
  逐字確認，僅供方向性參考，不應作為施工依據。
- Sentry 免費層是否對「上傳 source map」本身另外設限（額度或
  功能鎖），本輪未找到官方文件逐字確認這一點，標記 UNVERIFIED。
