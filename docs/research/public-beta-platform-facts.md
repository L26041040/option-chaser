# Public Beta 平台與 Vendor 條款事實查核

> 本文件回答 issue #273：匿名公開測試（Public Beta）要做清理排程、限流、
> log 保留、DB 滿了怎麼辦這些決策，都得先知道「我們用的平台在目前方案下
> 到底能做什麼」。**這張票只查事實、不做決定**——每一格數字、每一句
> vendor 條款原文都附官方出處與查閱日期（今日 2026-09-11），查不到的
> 誠實寫 UNVERIFIED，不臆測、不生成看起來合理但沒查證過的數字。

## 給 Owner 的白話摘要

Vercel／Neon／GitHub 三個平台的免費層，撐過一次小規模公開測試在技術上
大致沒問題，但有兩個先前紀錄裡沒寫對、值得先知道的事：**(1) 現在
`vercel.json` 設的 60 秒逾時是我們自己設的，不是 Vercel 的上限**——
Hobby 方案本身就給到 300 秒、Pro 給到 800～1800 秒，這推翻了 CLAUDE.md
之前「60 秒是官方硬性上限」的舊說法；**(2) 目前這輪查核裡最重要、也最
容易被忽略的風險不是平台限制，是 Cboe 自己網站上寫的話**——「禁止用
自動抓取程式／查詢下載延遲報價資料，違者將被封鎖 IP，資料下載只能透過
手動輸入代號」，而這正是 Option Chaser 每次刷新在做的事，Yahoo Finance
的條款也明文禁止類似的自動化擷取與「建立競品資料源」。這兩條不是「用量
太大才會踩到」的門檻，是**現在這一刻、只要繼續照現行架構抓資料，理論上
就已經不符合對方條款**的既有狀態，Public Beta 只是把「一個人默默用」
變成「有公開流量」，讓被偵測與被封鎖的機率變高，不是製造出一個新問題。
好消息是：Vercel Hobby 方案本身「非商業、個人用途」的限制，因為 Option
Chaser 不收費、不放廣告、沒有人因為做這個網站而拿錢，依官方定義**不算
商業使用**，現在維持免費方案在條款上沒有問題；「production 網域維持
公開」這件事也已由官方文件證實成立，不需要另外裁示。依現有實測數字
換算，這套架構大概撐得住到兩位數量級的同時活躍匿名使用者，卡住的會是
Cboe 429 全站連坐視窗與 Neon 0.5 GB 兩個因素，本輪判斷現在還遠不到值得
搬到別的平台的時候。

---

## 目錄

1. [Vercel 事實表](#1-vercel-事實表)
2. [Neon 事實表](#2-neon-事實表)
3. [GitHub Free 事實表](#3-github-free-事實表public-repo)
4. [Vendor 條款：哪一條會讓公開測試踩雷](#4-vendor-條款哪一條會讓公開測試踩雷)
5. [未來擴充：什麼時候值得重新評估架構](#5-未來擴充什麼時候值得重新評估架構)
6. [這對 Option Chaser 意味著什麼](#6-這對-option-chaser-意味著什麼)
7. [誠實揭露：本輪沒查到 / 查不到的事](#7-誠實揭露本輪沒查到--查不到的事)

---

## 1. Vercel 事實表

> 查閱日期：全部 2026-09-11。出處一律為 vercel.com/docs 官方文件；
> 每列末的日期是該頁 docs 系統本身標示的 `last_updated`（供將來對照
> 是否已過期，不是我查閱的日期）。

### 1.1 Serverless Function 執行時間

| 項目 | Hobby | Pro | Enterprise | 出處 |
|---|---|---|---|---|
| 預設 duration | 300 秒（5 分） | 300 秒 | 300 秒 | [Functions Limits](https://vercel.com/docs/functions/limitations)（頁面標示 2026-08-24） |
| 最大 duration | 300 秒（**等於預設，不能再調高**） | 800 秒（GA） | 800 秒（GA） | 同上 |
| Extended 最大 duration | 不提供 | 1800 秒（30 分，Beta） | 1800 秒（Beta） | 同上 |
| Edge runtime | 25 秒內須開始回應，串流可到 300 秒 | 同 | 同 | 同上 |

**⚠ 直接推翻既有紀錄的一句話**：CLAUDE.md「環境」一節寫著
「serverless 函式硬性時間上限（CONTEXT.md：60 秒）」，且本 repo
`vercel.json` 明確設 `"maxDuration": 60`。**60 秒是本專案自己設定的
值，不是 Vercel Hobby 方案的上限**——Hobby 方案的官方預設與上限本身
就是 300 秒（5 分鐘），比現在設的還多 5 倍；若真的需要更長，升級到 Pro
可以再調到 800 秒甚至 1800 秒（Beta）。本專案的 `REFRESH_RUN_BUDGET =
45s` 與 `REFRESH_RUN_GROUP_LIMIT` 設計是刻意抓在「比自己設的 60 秒更
保守」的位置，而不是抓在 Vercel 平台真正的上限之下——這件事本身沒有
錯（提早收手比撞牆好），只是文件裡把「自己設的值」誤記成「平台的
硬上限」，需要更正認知。

### 1.2 Fluid Compute

| 項目 | 內容 | 出處 |
|---|---|---|
| 是否預設開啟 | **2025-04-23 起，新建立的專案預設開啟** | [Fluid compute](https://vercel.com/docs/fluid-compute)（2026-08-24） |
| 意義 | 多個請求可共用同一個執行環境（非每次都開新的 microVM），降低 cold start、支援請求結束後的背景工作（`waitUntil`）、跨可用區自動失效轉移 | 同上 |
| 是否要求 Pro | 不要求——Hobby／Pro／Enterprise 三個方案都支援，只有「Default/Max duration」數值依方案不同 | 同上 |
| 大型函式（>250MB/500MB）支援 | 需要 Fluid compute + Active CPU 才能用，新專案預設就有資格 | [Functions Limitations](https://vercel.com/docs/functions/limitations) |

本 repo 的 Vercel 專案建立於 2026-08-02（V1／#48），晚於 2025-04-23，
理論上預設應該已經是 Fluid compute 開著——但這是**依官方文件的預設
規則推論**，本輪未能直接查詢這個專案在 Vercel 後台的實際開關狀態
（見第 7 節說明），若要 100% 確認，Owner 到 Vercel Dashboard → 專案
Settings → Functions 分頁看一眼「Fluid Compute」那個切換開關即可，
一分鐘可查完，不需要另開票。

### 1.3 Cron Jobs

| 項目 | Hobby | Pro | Enterprise | 出處 |
|---|---|---|---|---|
| 每專案上限 | 100 個 | 100 個 | 100 個 | [Cron Jobs Usage & Pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)（2026-07-15） |
| 最短間隔 | **每天最多一次**（更頻繁的 cron 語法會在部署時直接失敗） | 每分鐘一次 | 每分鐘一次 | 同上 |
| 觸發時間精度 | ±59 分鐘（例如設 `0 1 * * *` 可能 1:00–1:59 之間任何時刻觸發） | 精確到分鐘 | 精確到分鐘 | 同上 |
| 計費 | 免費（cron 觸發的 function 本身照一般 function 用量計費） | 同 | 同 | 同上 |

本 repo 現有 `vercel.json` 的 cron（`"0 11 * * 1-5"`，平日一次）本來
就落在 Hobby「每天最多一次」的規則內，**現有設定不需要為了 Public
Beta 而改**；未來如果要新增「每 N 小時清一次過期資料」這類更頻繁的
排程，Hobby 方案在平台層級就直接擋掉，這是一個真的會卡到「清理排程
多久跑一次」這個問題的硬限制，不是理論上的。

### 1.4 Firewall / WAF

| 項目 | Hobby | Pro | Enterprise | 出處 |
|---|---|---|---|---|
| DDoS 全站防護 | 免費、自動、無需設定 | 同 | 同 | [Vercel Firewall](https://vercel.com/docs/vercel-firewall)（2026-08-11） |
| **Attack Mode**（俗稱 Attack Challenge Mode） | **免費，全部方案皆可用** | 免費 | 免費 | [Attack Mode](https://vercel.com/docs/vercel-firewall/attack-mode)（2026-08-11）："Attack Mode is available for free on all plans" |
| WAF Custom Rules 數量上限 | **3 條** | 40 條 | 1000 條 | [Hobby Plan 比較表](https://vercel.com/docs/plans/hobby)（2026-08-31） |
| WAF IP Blocking 數量上限 | 3 條 | 100 條 | — | 同上 |
| **WAF Rate Limiting** 是否可用 | **可用**（2024 年起「Rate limiting now available on Hobby」） | 可用 | 可用（Token Bucket 演算法限 Enterprise） | [WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)（2026-08-28） |
| Rate Limiting 規則數上限 | **1 條**（計入上面 3 條 custom rules 總額度內） | 40 條 | 1000 條 | 同上 |
| Rate Limiting 計數窗長度 | 10 秒～10 分鐘 | 10 秒～10 分鐘 | 10 秒～1 小時 | 同上 |
| Rate Limiting 免費請求額度 | 100 萬次「允許放行」的請求／月 | 用量計費 | 客製 | 同上 |
| Bot Protection Managed Ruleset 是否 Hobby 可用 | **UNVERIFIED**——官方頁面未明文列出各方案是否可用，只標示「需要權限」，Managed Ruleset 計費表只列出 Pro 欄位的免費額度 | 有免費額度（OWASP CRS 每請求 4KB） | — | [Bot Management](https://vercel.com/docs/bot-management)、[WAF Usage & Pricing](https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing)（皆 2026） |

**這條直接回答票面問題，且結果可能出乎預期**：「自訂 rate-limiting
規則是否可用」——**答案是可以，而且 Hobby（免費方案）就能用**，不是
Pro 才有。限制在於 Hobby 只給 1 條 rate-limiting 規則、演算法只有
Fixed Window（沒有 Token Bucket），但對「擋單一 IP 打太快」這種最
基本的公開測試防線已經夠用。

### 1.5 Runtime Logs 與 Log Drains

| 項目 | Hobby | Pro | Pro + Observability Plus | Enterprise | 出處 |
|---|---|---|---|---|---|
| Runtime Logs 保留時間 | **1 小時** | 1 天 | 30 天（可選最近連續 14 天視窗） | 3 天 | [Runtime Logs](https://vercel.com/docs/logs/runtime)（2026-08-28） |
| 單筆 log 大小 | 256 KB／行，1 MB／request 總量，256 行／request | 同 | 同 | 同 | 同上 |
| Log Drains（轉出到外部服務） | **不可用** | 可用 | 可用 | 可用（另有 Audit Log Drains，僅 Enterprise） | [Log Drains](https://vercel.com/docs/drains)（2026-09-01）："If you are on the Hobby or Pro Trial plan, you'll need to upgrade to Pro to access non-audit-log drains." |
| Log Drains 計費 | — | $0.50／GB（未壓縮 JSON 序列化後的位元組數） | 同 | 同 | 同上 |

**Hobby 只留 1 小時 log 這件事，是這輪查到、最值得放進「log 留多久」
決策裡的硬數字**——出事後 1 小時內沒把 log 存下來就永久看不到了；
若要接 Log Drains 把 log 轉存到自己的地方長期保留，需要升級 Pro。

### 1.6 Observability（一般，不含 Runtime Logs）

| 項目 | Hobby | Pro | Pro + Observability Plus | Enterprise | 出處 |
|---|---|---|---|---|---|
| 資料保留期 | 12 小時 | 1 天 | **30 天** | 3 天 | [Observability Plus](https://vercel.com/docs/observability/observability-plus)（2026-07-06） |
| Query（自訂查詢／存成 notebook） | 無 | 無 | 有 | 無（需另開 Plus） | 同上 |
| Observability Plus 計費 | 不可用（需升級 Pro） | 可加購 | $1.20／百萬 events | 可加購 | 同上 |

### 1.7 Web Analytics

| 項目 | Hobby | Pro | Pro + Web Analytics Plus | Enterprise | 出處 |
|---|---|---|---|---|---|
| 免費 events 額度 | **50,000／月** | 無內建額度，$0.03／千 events | $0.03／千 events | 客製 | [Web Analytics Pricing](https://vercel.com/docs/analytics/limits-and-pricing)（2026-08-25） |
| 資料保留窗（reporting window） | **1 個月** | 12 個月 | 24 個月 | 24 個月 | 同上 |
| 超額行為 | **暫停收集**（3 天 grace period 後開始暫停，之後等 7 天或升級 Pro 才恢復）；**不會被扣錢，Hobby 不能加購** | 依用量計費 | 依用量計費 | 客製 | 同上 |
| 自訂事件（Custom Events） | 不可用 | 可用（2 個屬性） | 可用（8 個屬性） | 可用（8 個屬性） | 同上 |

### 1.8 Spend Management（用量預算警示）

| 項目 | Hobby | Pro | 出處 |
|---|---|---|---|
| 是否可用 | **不可用（N/A）** | 可用 | [Hobby Plan 比較表](https://vercel.com/docs/plans/hobby)；[Spend Management](https://vercel.com/docs/spend-management)（2026-08-31） |
| 功能 | — | 設定金額門檻→50/75/100% 發通知（email／web／SMS）、可選自動暫停全部專案的 production 部署、可打 webhook | 同上 |
| 檢查頻率 | — | 「每幾分鐘」檢查一次（非即時），暫停可能延後幾分鐘才生效 | 同上 |

Hobby 方案**沒有** Spend Management——這件事本身影響有限（Hobby 免費、
超額多數情況是「暫停到下個月」而非扣款，見下），但意味著沒有「快要
撞到免費額度時主動通知我」這個機制，只能靠 Vercel 自動發的用量接近
上限通知（Web Analytics 額度接近時會發，其餘資源是否也有類似通知，
本輪查到的文件未逐項列出，標 UNVERIFIED）。

### 1.9 用量額度、超額行為與 Fair Use 限制

| 資源 | Hobby 免費額度 | Pro 免費額度／計費 | 出處 |
|---|---|---|---|
| Function Invocations | 100 萬／月 | 用量計費，$0.60／百萬次（超過 Pro monthly credit 之後） | [Limits](https://vercel.com/docs/limits)（2026-09-03） |
| Active CPU | 4 CPU-hrs | 用量計費，起價 $0.128／小時 | 同上 |
| Provisioned Memory | 360 GB-hrs | 用量計費，起價 $0.0106／GB-hr | 同上 |
| Fast Data Transfer（頻寬） | **100 GB** | 1 TB 免費，之後依區域計價 | 同上 |
| Fast Origin Transfer | 10 GB | 用量計費 | 同上 |
| Edge Requests | 100 萬 | 1000 萬免費，之後依區域計價 | [Hobby Plan](https://vercel.com/docs/plans/hobby) |
| Build Time／單次 deployment | 45 分鐘（超過即該次 build 失敗，兩方案相同） | 45 分鐘 | [Limits](https://vercel.com/docs/limits) |
| Deployments／天 | 100 | 6,000 | 同上 |
| Concurrent Builds | 1 | 最多 500 | 同上 |

**超額後會發生什麼事（Hobby）**：官方文件用一句話講清楚——
「if you exceed your usage limits on the Hobby plan, you will have
to wait until 30 days have passed before you can use the feature
again」——**多數資源是暫停使用、等 30 天週期重置，不是直接扣款**
（Hobby 本身無法被扣款：沒有信用卡、也不能加購）。[Hobby Plan](
https://vercel.com/docs/plans/hobby)（2026-08-31）。個別資源有更短
的暫停期（例如 Web Analytics 是 7 天）。

**⚠ 這節查到一個範圍外但重要、票面沒問到的合規事實**——**Hobby 方案
本身在條款上限定「非商業、個人用途」**：

> "As stated in the fair use guidelines, the Hobby plan restricts
> users to non-commercial, personal use only."
> —— [Hobby Plan](https://vercel.com/docs/plans/hobby)（2026-08-31）

完整定義引自 [Fair Use Guidelines](
https://vercel.com/docs/limits/fair-use-guidelines)（2026-07-29）：

> "Commercial usage is defined as any Deployment that is used for
> the purpose of financial gain of **anyone** involved in **any
> part of the production** of the project, including a paid
> employee or consultant writing the code."

明文列出的商業使用範例：跟訪客收款／處理付款、廣告銷售、有人因為
寫／更新／架這個網站而拿到報酬、affiliate 連結是網站主要目的、
放廣告（含 Google AdSense）。**明文排除**：

> "Asking for Donations **does not** fall under commercial usage."

**這對 Public Beta 的意義（見第 6 節詳述）**：Option Chaser 不收費、
不放廣告、目前也沒有任何人因為寫這個 repo 而收錢——依這個定義**不算
商業使用**，維持 Hobby 方案在條款上沒問題；但若未來加了廣告、付費
功能、或委託別人開發並支付報酬，這件事的答案會改變，需要重新檢查。

### 1.10 Deployment Protection

**核心結論（直接回答票面問題）**：本 repo 目前記錄的設定值
`prod_deployment_urls_and_all_previews`（見 CLAUDE.md「## 環境」
一節），對應 Vercel 目前文件用語裡的 **Standard Protection**（或其
在文件中並列的 legacy 名稱 "(Legacy) Standard Protection"——兩者
描述的行為完全相同，只是新舊版名稱，本輪查到的官方文件未逐字列出
API 層級的英文 enum 字串，這一段的字串對應關係是**依行為描述推論**，
不是我在文件裡直接看到那個確切字串）：

> "Standard Protection: Protects all deployments **except**
> production domains. Available on all plans."
>
> "On the Hobby plan, Vercel Authentication with Standard
> Protection is available. This protects your preview deployments
> and deployment URLs, but **your production domain remains
> publicly accessible**. To protect production domains, you need a
> Pro or Enterprise plan."
>
> —— [Deployment Protection](https://vercel.com/docs/deployment-protection)（2026-08-28）

也就是說：**目前這個設定值，確實代表 production 網域
（`option-chaser.vercel.app`）公開可達，不需要登入即可存取**——
只有「工作分支的 preview 部署」與「production 底下那些帶著部署 ID
的舊網址（例如 `option-chaser-abc123.vercel.app`）」被 Vercel
Authentication 擋著。**這正是票面要確認的假設，且確認成立**——不是
待決策項，是已經是這樣運作的既有事實。若要連 production 網域本身也
要求登入，必須換成「All Deployments」保護範圍，且該選項**只有 Pro
與 Enterprise 才能選**。

| Deployment Protection 選項 | 保護範圍 | 可用方案 | 出處 |
|---|---|---|---|
| Standard Protection | 除 production 網域外全部 | 全部方案 | 同上 |
| All Deployments | 全部（含 production 網域） | **Pro／Enterprise** | 同上 |
| Only Production Deployments（用 Trusted IPs） | 只保護 production，preview 全公開 | **僅 Enterprise** | 同上 |
| Password Protection | — | Enterprise／Pro 加購（$150／月） | 同上 |

### 1.11 Instant Rollback

| 項目 | Hobby | Pro／Enterprise | 出處 |
|---|---|---|---|
| 是否可用 | 可用 | 可用 | [Instant Rollback](https://vercel.com/docs/instant-rollback)（2026-07-07） |
| 可回退範圍 | **只能回退到「上一個」部署** | 可回退到任何曾經被 alias 到 production 的部署 | 同上 |

---

## 2. Neon 事實表

> 查閱日期：全部 2026-09-11。出處為 neon.com/docs 官方文件。

| 項目 | Free | Launch（最低付費方案） | 出處 |
|---|---|---|---|
| 儲存空間上限 | **0.5 GB／project** | 無上限，$0.35／GB-月 | [Neon Plans](https://neon.com/docs/introduction/plans) |
| 超過儲存上限的行為 | **寫入操作（insert／update／delete）失敗**，直到釋放空間或升級——**不會刪除既有資料** | — | 同上 |
| 月度 compute 額度 | 100 CU-hours／project | 依用量計費，$0.106／CU-hour，無最低消費 | 同上 |
| 用完 compute 額度的行為 | **compute 被暫停**，直到下個計費週期或升級 | — | 同上 |
| Autosuspend（scale-to-zero） | 閒置 **5 分鐘後**強制暫停，**不能關閉** | 閒置 5 分鐘後暫停，**可以關閉**（保持常駐） | [Scale to zero](https://neon.com/docs/introduction/scale-to-zero) |
| 恢復延遲（cold start） | 「幾百毫秒內」自動恢復 | 同 | 同上 |
| Scale-to-zero 適用範圍 | 僅 ≤16 CU 的 compute；用邏輯複寫當來源時，訂閱端連著就不會被暫停 | 同 | 同上 |
| Projects／Branches 上限 | 100 projects，每 project 10 branches | 100 projects，每 project 10 branches（相同） | [Neon Plans](https://neon.com/docs/introduction/plans) |
| 最大同時連線數 | **UNVERIFIED**——官方文件按 compute 大小（CU）列出 `max_connections`（例如 0.25 CU＝104 條、扣 7 條給 superuser 剩 97），但沒有明確指出 Free 方案預設對應哪個 CU 大小 | 同左 | [Connection Pooling](https://neon.com/docs/connect/connection-pooling) |
| History Window（PITR／回溯還原窗） | **6 小時**（上限另外再封頂 1 GB） | Launch 最長 **7 天**，Scale 最長 30 天 | [History Window](https://neon.com/docs/postgres/backup-restore/history-window) |
| History 對儲存用量的影響 | 視窗內的 WAL 都會被保留、計入用量；超出視窗的 WAL 自動清除、停止計費 | Launch/Scale 額外收 History 費：$0.20／GB-月 | 同上 |
| `pg_cron` 擴充套件 | **可用**——官方 `pg_cron` 文件全篇未提及任何方案限制 | 可用 | [pg_cron](https://neon.com/docs/extensions/pg_cron) |
| `pg_cron` 的實際限制（不是方案限制） | **pg_cron 只在 compute 處於 active 狀態時才會觸發**；官方文件明文建議「只在 24/7 常駐或已停用 scale-to-zero 的 compute 上使用 pg_cron」 | 同左（但 Launch+ 可以停用 scale-to-zero） | 同上 |
| `pg_repack`（回收因刪除／更新累積的膨脹空間） | **UNVERIFIED，但已知只在付費方案可用**——官方文件僅指出「Available only on paid Neon plans」，未列出是否指 Launch 或更高 | 可用 | [pg_cron 頁面內連帶提及](https://neon.com/docs/extensions/pg_cron) |

**這節裡最值得放進「清理排程多久跑一次」決策的一句話**：`pg_cron`
在文件上沒有被列為付費限定功能，**但在 Free 方案上形同虛設**——
因為 Free 方案的 autosuspend「閒置 5 分鐘就暫停、不能關閉」是無法
繞過的，而 `pg_cron` 排程只在 compute 醒著的那一刻才會被觸發，一個
長期沒有真實查詢流量的公開測試站，資料庫多半大部分時間是睡著的，
排定在資料庫內部跑的清理工作不會被準時執行。這與本專案既有
Treasury Cron 預熱端點（`GET /api/cron/warm-rate-cache`，由 Vercel
Cron 從外部打進來喚醒）是同一種解法方向：**要在 Free 方案上定期做
清理，得靠 Vercel Cron 從外面打一個 HTTP 端點觸發 SQL，而不是靠
`pg_cron` 排定在資料庫內部跑**。

---

## 3. GitHub Free 事實表（public repo）

> 查閱日期：全部 2026-09-11。出處為 docs.github.com／github.blog
> 官方文件。本 repo（`L26041040/option-chaser`）為 public repo。

| 項目 | 內容 | 出處 |
|---|---|---|
| Actions 分鐘數（public repo，標準 GitHub-hosted runner） | **免費、無每月分鐘數上限**——"GitHub Actions usage is free for standard GitHub-hosted runners in public repositories, and for self-hosted runners." Private repo 才有每月固定額度（GitHub Free 個人帳號為 2,000 分鐘／月） | [Billing and usage](https://docs.github.com/en/actions/concepts/billing-and-usage) |
| 2026-03-01 起自架 runner 新收費 | 每分鐘 $0.002 的「Actions cloud platform charge」——**僅適用自架（self-hosted）runner**，不影響 public repo 用標準 GitHub-hosted runner 這件事本身 | [GitHub Changelog](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)（經 WebSearch 摘要，本輪未逐字重新核對原文，列為次要佐證） |
| Postgres／資料庫 Service Container 是否可用 | **UNVERIFIED（方案層級明確聲明）**——[官方 Service Containers 文件](https://docs.github.com/en/actions/using-containerized-services/about-service-containers) 只講技術用法（如何在 workflow 裡定義 Docker service container），完全沒提任何方案限制；本輪查無官方文件明確寫「public repo／Free 方案可以／不可以用」，但這功能是標準 Actions 語法的一部分（非另計費的加值功能），沒有查到任何限制它的方案別文件 | 同上；本輪未能找到更明確的一手方案限制聲明 |
| Repository Rulesets（含 branch protection 規則） | **public repo 上，GitHub Free 個人帳號可用**；**private repo 需要 Pro／Team／Enterprise** | 這一格有兩份官方文件互相矛盾，見下方說明 |
| Secret Scanning（掃描 repo 裡意外提交的密鑰） | **public repo 免費、自動執行**——"Secret scanning runs automatically for free"／"Secret scanning alerts for users can be enabled on any free public repository that you own" | [About secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)、[Enabling for your repository](https://docs.github.com/en/code-security/secret-scanning/enabling-secret-scanning-features/enabling-secret-scanning-for-your-repository) |
| Push Protection（擋下含密鑰的 commit，不讓它進 repo） | **UNVERIFIED（是否對 public repo 預設開啟）**——本輪查到的頁面確認 push protection 是與 secret scanning alerts 並列的獨立功能，但沒有查到明確聲明它對 public repo 是否預設自動開啟；業界普遍認知 GitHub 已對公開 repo 全面預設開啟（2024 年公告），但本輪未能在時限內找到可重新核對的一手頁面，誠實列為 UNVERIFIED，不採信記憶 | 見第 7 節 |

**Rulesets 那一格的矛盾需要說清楚**：`docs.github.com` 的
["About rulesets"](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
頁面開頭寫著「A ruleset is a named list of rules that applies to a
repository or to multiple repositories in an organization **for
customers on GitHub Team and GitHub Enterprise plans**」——單獨讀
這句會以為 Free 方案完全不能用 rulesets。但透過搜尋比對到的另一段
（來自同一個文件家族、標題含「rulesets」與「plan availability」的
段落）明確寫「Rulesets are available in public repositories with
GitHub Free and GitHub Free for organizations, and in public and
private repositories with GitHub Pro, GitHub Team, and GitHub
Enterprise Cloud」。**兩段話的落差最合理的解釋**：前者講的可能是
「組織層級、跨多個 repo 一次套用的 ruleset」這個較進階子功能（歷史
上確實曾是 Team／Enterprise 才有），後者講的是「單一 public repo 自己
的 ruleset」這個基本功能——但本輪**沒有找到一份把兩者關係講清楚的
單一權威頁面**，這個對照關係本身是我的推論，不是我直接讀到的一句
定論。**建議 Owner 自行到 repo 的 Settings → Rules → Rulesets 點一次
「New ruleset」就能在 10 秒內確認 Free 方案下 public repo 能不能用**，
比繼續在文件裡挖更省事。

---

## 4. Vendor 條款：哪一條會讓公開測試踩雷

> 這節查閱日期同樣是 2026-09-11。這是整份文件最重要的一節——
> **票面特別點名 Cboe 最容易被忽略**，查證結果顯示這個提醒是對的，
> 而且問題比「容易被忽略」更嚴重：**條款寫得非常直接、而且已經有
> 實際執法動作（IP 封鎖）**。

### 4.1 Cboe 延遲報價（`cdn.cboe.com/api/global/delayed_quotes/...`，本產品主資料源）

本產品 `option_chaser/data/cboe.py` 直接打
`cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json`——這是
Cboe 網站上「Delayed Quotes」頁面本身用來畫報價表格的同一份底層資料。
Cboe 自己在對應的說明頁面上寫著（**逐字引用、原文全大寫**）：

> "PLEASE NOTE: **IT IS STRICTLY PROHIBITED TO DOWNLOAD DELAYED QUOTE
> TABLE DATA FROM THIS WEB SITE BY USING AUTO-EXTRACTION
> PROGRAMS/QUERIES AND/OR SOFTWARE. CBOE WILL BLOCK IP ADDRESSES OF
> ALL PARTIES WHO ATTEMPT TO DO SO.** THIS DATA IS PROPERTY OF CBOE
> LIVEVOL OR ITS DATA PROVIDERS. DOWNLOADING THIS DATA IN ANY OTHER
> WAY THAN BY MANUAL TICKER SYMBOL ENTRY IS STRICTLY PROHIBITED."
>
> —— <https://www.cboe.com/delayed_quotes/API/quote_table/>
> （2026-09-11 直接抓取該頁原始 HTML 確認逐字存在，非二手轉述）

白話：**Cboe 自己說「只能用手動在網頁上打代號查詢，任何自動抓取程式
或軟體都嚴格禁止，違者會被封鎖 IP」**。而 Option Chaser
`_default_fetch()` 每一次「刷新」都是伺服器端自動發出的 HTTP GET，
不是使用者在瀏覽器上手動打代號——**這正是這段話明確禁止的行為模式**，
與資料是 JSON 格式還是網頁表格格式無關，Cboe 這句話講的是「用什麼
方式取得」不是「取得的資料長什麼樣子」。

Cboe 官方網站的一般使用條款（`cboe.com/terms/`）再補上第二層、範圍
更廣的限制：

> "You may view, print and download **one copy** of the Materials
> for your **personal non-commercial use in connection with
> products and services offered by Cboe**."
>
> "You may not otherwise copy, reproduce, alter, store...
> distribute, or otherwise use in whole or in part in any other
> manner the Materials **without Cboe's prior written consent**."
>
> —— <https://www.cboe.com/terms/>（2026-09-11）

這一段講的不只是「不能自動抓」，還講「拿到的東西只能自己私下看，
不能拿去做別的服務再轉給別人看」——把這兩段合在一起看，Option
Chaser 現在的用法（伺服器自動抓、算出結果、顯示給網站訪客看）
在**兩個獨立的條款維度上都超出 Cboe 明文允許的範圍**，不是「用量
大了才會踩到」的門檻式限制，是**現在這一刻、不論有沒有 Public
Beta，理論上就已經在條款容許範圍之外**的既有狀態。

**這不是理論風險，本專案自己的紀錄裡已經有實測證據**：
CLAUDE.md 記錄 SCALE-04／#255 專門處理「Cboe 429 後端
`chain_backoff`」，且明確寫著「Cboe 無歷史端點...盤外報價凍結不
歸零」等既有觀察都是**實際打過這個端點、收到過 429 加
`Retry-After` header**才會知道的資訊——這與上面那句「自動抓取會被
封鎖 IP」的警告方向一致：Cboe 確實有在主動偵測與限制自動化存取，
不是一段擺著沒人管的免責聲明。

**Public Beta 改變的是什麼、沒改變的是什麼**：這個條款風險**不是
Public Beta 才創造出來的**——今天只有 Owner 一個人用，理論上一樣
不符合條款；Public Beta 改變的是**曝險程度**——(a) 使用者一多，
單位時間內對 Cboe 發出的請求量自然增加，被自動化偵測系統注意到、
觸發 IP 封鎖的機率變高；(b) 一旦 Vercel 出口 IP 被封鎖，受影響的是
「所有」使用這個 production 網域的使用者，不再是一個人的問題；
(c) 從「一個人的個人專案」變成「有公開流量的服務」後，若真的被
Cboe 追究，「純屬個人非商業使用」這個最基本的抗辯空間也會變小。

### 4.2 Yahoo Finance chart endpoint（`query2.finance.yahoo.com/v8/finance/chart/{symbol}`，股利資料主來源）

Yahoo 官方 Terms of Service（`legal.yahoo.com`）明文禁止本產品這種
使用模式，且措辭比 Cboe 更直接地點名「建立競品資料源」這件事：

> "access or collect data, or attempt to access or collect data,
> from our Services using any automated means, devices, programs,
> algorithms or methodologies, including but not limited to robots,
> spiders, scrapers, data mining tools, or data gathering or
> extraction tools, **for any purpose without our express, prior
> permission**."
>
> "use any material or content from, including without limitation
> any data, (a) **to create any database, archive, mobile
> application, data feed, widget or any other aggregated data
> source that competes with or constitutes a material substitute
> for the Services**"
>
> "reproduce, modify, rent, lease, sell, trade, distribute,
> transmit, broadcast, publicly perform, create derivative works
> based on, or exploit for any commercial purposes, any portion or
> use of, or access to, the Services"
>
> —— <https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html>
> （Section 2.4／2.5，2026-09-11 查閱）

Option Chaser 把 Yahoo 的配息資料抓進來、算成 dividend yield（q），
再拿去算選擇權估值、顯示給使用者——這是否構成「aggregated data
source that competes with...the Services」是一個需要主觀判斷的
灰色地帶（本產品顯示的是加工後的衍生數字，不是原始報價轉貼），但
「使用自動化工具擷取資料」這一條本身**沒有灰色空間**，字面就是
禁止的。

### 4.3 Nasdaq（`api.nasdaq.com`，股利資料第三備援）與 Financial Modeling Prep（`financialmodelingprep.com`，第二備援，需自備金鑰）

- **Nasdaq**：本輪嘗試直接讀取 `nasdaq.com` 網站一般使用條款頁面時
  兩次收到 HTTP 503（服務暫時不可用），未能取得一手逐字文本。透過
  WebSearch 找到的是 Nasdaq 對「機構訂閱者」（購買市場資料授權的
  券商／終端使用者）的正式 Subscriber Agreement，裡面確實有禁止
  「computerized voice, automated information inquiry systems」
  存取的條款，但那份文件服務的是**付費市場資料訂閱**這個完全不同
  的產品線，不必然適用於 `nasdaq.com` 網站背後這支免費、供網站自己
  前端使用的 `api.nasdaq.com` 端點。**本輪未能確認這支端點是否受
  一份更簡單的一般網站條款規範、還是完全沒有公開條款**，列為
  UNVERIFIED。因為 Nasdaq 在本產品的抓取順序裡是**第三備援**
  （Yahoo 失敗且沒設 `FMP_API_KEY` 或 FMP 也失敗才會用到），實際
  曝險頻率遠低於 Cboe 與 Yahoo。
- **Financial Modeling Prep**：官方 Terms of Service
  （`site.financialmodelingprep.com/terms-of-service`）本輪嘗試直接
  讀取時收到 HTTP 403，透過 WebSearch 取得的二手摘要顯示這是一份
  標準商業 API 授權條款（「limited, revocable, non-exclusive,
  non-transferable, non-sublicensable」授權，依 Order Form／帳戶
  訂閱範圍使用），**未能取得逐字原文**、也**未能確認免費層的具體
  使用範圍條款**，列為 UNVERIFIED。因為本產品程式碼裡 `FMP_API_KEY`
  是**伺服器端環境變數**（單一共用金鑰，不是每個使用者各自的
  token），若 Public Beta 讓使用量明顯增加，這把共用金鑰的免費額度
  被多個匿名使用者共同消耗掉的風險是確定的（不需要 ToS 才能判斷），
  但這件事在既有研究文件（`dividend-yield-source-selection.md`）
  裡已經記錄過，非本輪新發現。

### 4.4 U.S. Treasury 利率資料

**公有領域，確認成立**。美國聯邦法律明文規定聯邦政府作品不受著作權
保護：

> "Copyright protection under this title is **not available for any
> work of the United States Government**, but the United States
> Government is not precluded from receiving and holding copyrights
> transferred to it by assignment, bequest, or otherwise."
>
> —— 17 U.S.C. §105，[U.S. Copyright Office 官方文件](
> https://www.copyright.gov/title17/92chap1.html)（2026-09-11 查閱）

財政部發布的每日公債殖利率曲線資料屬於聯邦政府作品，據此**不受
著作權限制**，這條資料源在合規面沒有風險，是本輪四個外部資料源裡
唯一一個乾淨的。

### 4.5 Market Data App（`api.marketdata.app`，使用者自帶 token、由伺服器代打）

官方 Terms of Service（`marketdata.app/terms/`）有兩條與這個使用
模式直接相關的條款：

> "You may not sell, resell, retransmit, or **redistribute or make
> our data or any third-party data available to anyone** without a
> supplemental commercial use addendum to this agreement."
>
> "You may not **distribute the data programmatically as a data
> feed, an API, or an export file**."
>
> —— <https://www.marketdata.app/terms/>（經 WebSearch 摘要引用，
> 本輪多次嘗試直接完整讀取該頁原文未完全成功，逐字片段來自搜尋
> 引擎回傳的頁面摘要，**建議日後有機會時用可直接瀏覽該頁的環境
> 重新核對完整原文**）

這條款字面上限制的是「把資料當成一個 API／data feed／匯出檔轉賣或
提供給別人」——**這件事在本產品今天的用法（單一 Owner 自己的
token，結果只給 Owner 自己看）幾乎確定沒有問題**，因為唯一看到
資料的人就是 token 本人。**票面問的是 Public Beta 情境下「多個
匿名使用者各自帶自己的 token」這個模式**：如果每個使用者都是拿
「自己的」token、伺服器只是代替他打 API、算出來的結果也只顯示給
那個 token 的主人自己看——這比較接近「使用者本人透過我們提供的
介面使用自己的帳戶」，而不是「我們把 Market Data App 的資料轉賣給
第三方」；但這個區分本身帶有主觀判斷成分，**條款原文沒有明確處理
「伺服器代打、資料只回給 token 本人」這種中間型態**，本輪判斷這是
一個需要向 Market Data App 官方客服直接確認、而不是靠條款文字自行
推論的問題，不在此下結論。

---

## 5. 未來擴充：什麼時候值得重新評估架構

> **本節目的不是現在選平台，是回答「什麼時候值得重新評估」**——
> 依 Owner 已定案的方向（Public Beta 先以免費方案為目標、現在不搬
> 平台、production protection 現在不開），本輪的結論是：**現在不
> 建議搬，但先把訊號與門檻寫清楚，以後不必每次都重新從零討論**。

### 5.1 目前架構大概能撐到什�麼階段

**方法**：不是重新做效能測試，是用第 1–2 節查到的官方免費額度，
套進本專案既有的、已經記錄在案的實測數字（CLAUDE.md「Scaling
Foundation」一節），推算「大概會先撞到哪一面牆」。

| 資源 | 免費額度 | 本專案既有實測基準 | 推算的匿名同時活躍使用者上限（量級） |
|---|---|---|---|
| Neon Free 儲存空間 | 0.5 GB | SCALE-16／17 之後，穩態每次刷新約 169,847 B（悲觀情境；穩態下實測 564× 更省，約數百 B 級）——這是**單一 Owner 一個人**用時的量，Public Beta 下 N 個使用者、各自的劇本各自佔用空間，成長速度大致與「有效使用中的劇本數」成正比，不是與「使用者數」直接成正比（一個人可以開很多劇本，也可能只開一個） | 以「每人平均維持 5–10 個持續追蹤的劇本」估：0.5 GB ÷（劇本數 × 每筆穩態成長）落在**數百到數千個劇本**量級，換成「人」大概是**幾十到一兩百個活躍使用者**，但這個數字對「劇本數」比對「人數」敏感，見下方誠實揭露 |
| Cboe 429 全站連坐視窗 | 官方未公開明確 rate limit 數字（本產品既有紀錄：實測會回 429＋`retry-after`） | `chain_backoff` 的鍵是 **`source` 單獨、不分 symbol**（provider-global）——一旦被限流，**封鎖影響全站、全部使用者、全部 symbol**，不是壞在單一使用者或單一標的上 | 這道牆與「有多少人」無關、與「大家多密集地一起按刷新」有關——**個位數到十位數使用者同時集中在同一分鐘內按刷新，就可能觸發全站封鎖**，這比儲存空間牆更早出現、影響面更廣（見 4.1 節，且這件事本身可能已經違反 Cboe 條款，不是單純的用量問題） |
| Vercel Hobby Function Invocations | 100 萬次／月 | 一次「刷新」= 1 次 refresh-run invocation（C1／Refresh Run 架構已把「N 個劇本＝N 次 invocation」收斂成通常 1 次），一次「開詳細頁」= 1 次 invocation | 100 萬次／月 ÷ 30 天 ÷ 86400 秒 ≈ 每秒 0.38 次的等效常態流量，對應**幾百到上千個「偶爾來看一下」的使用者量級**——這道牆在本專案目前的架構下，遠比前兩道牆寬鬆 |
| Vercel Hobby Fast Data Transfer | 100 GB／月 | 前端靜態資源＋API JSON 回應（T13／T14 已把候選 payload 壓縮過，詳見 CLAUDE.md heatmap-matrix-payload-compression 相關記錄），單次頁面互動量級約數十至數百 KB | 同上，量級落在幾百到上千個使用者，不是這三道牆裡最先被撞到的 |

**結論**：**真正會先出事的不是「多少人」，是「多少個持續存在的
劇本」（撞 Neon 儲存）與「大家會不會同時集中按刷新」（撞 Cboe
429 全站連坐）**——這兩件事都不是傳統「每秒能處理多少請求」的
效能問題，是本專案自己的資料模型與既有韌性設計（provider-global
backoff）決定的天花板，跟要不要換一個更貴／更常駐的平台**沒有
直接關係**：換平台不會讓 Cboe 的條款變寬鬆、也不會讓 Neon Free
的 0.5 GB 變大。

### 5.2 哪個指標到了什麼程度才值得搬

以下四個訊號任一個持續出現（不是偶發一次），才值得重新評估架構
——不是提前準備，是**觸發時才動**：

1. **Neon `table_size_metrics`（本專案既有 `/api/ops/metrics` 端點）
   顯示儲存量持續逼近 0.5 GB**（例如連續一週都在 80% 以上）。
2. **Cboe 429／`chain_backoff` 進入 `is_sustained_incident()` 判定
   的持續性事故次數，一個月內發生超過個位數次**（既有機制：
   `INCIDENT_THRESHOLD_FAILURES=3`）——代表使用密度已經高到會
   規律性觸發全站限流，不是偶爾運氣不好。
3. **Vercel `/api/ops/metrics` 的 `chain_fetch_count`／
   `refresh_duration_ms` 顯示常態尾端延遲（p95）持續逼近或超過
   自設的 45 秒 `REFRESH_RUN_BUDGET`**——代表現在的批次大小已經
   吃緊，Continuation 分批頻率大幅增加、使用者體感變慢。
4. **Vercel Runtime Logs（Hobby 只留 1 小時）已經多次讓真正需要
   查證的事故追不回 log**——這件事本身用免費方案內的 Log Drains
   （需升級 Pro）就能解，不必連 DB／compute 平台一起換。

### 5.3 搬平台真正能省的是什麼

比較兩組「含常駐 Postgres／worker」的成熟替代（Fly.io、Render）跟
「留在 Vercel＋Neon、只是升級付費層」，逐項回答「換了之後省的是
錢、是複雜度，還是兩者都沒有」：

| 比較項目 | 現狀（Vercel Hobby＋Neon Free） | Vercel Pro＋Neon 付費層 | Fly.io（常駐 VM＋Managed Postgres） | Render（常駐 Web Service＋Postgres） |
|---|---|---|---|---|
| 執行時間上限 | 自設 60 秒（平台其實給 300 秒） | 800～1800 秒 [Functions Limits](https://vercel.com/docs/functions/limitations) | **無 serverless 式時間上限**——常駐 VM，官方定價文件未提及任何 per-request 逾時，最小 shared-cpu-1x/256MB 約 $2.02／月 [Fly.io Pricing](https://fly.io/docs/about/pricing/) | **無 serverless 式時間上限**（常駐容器架構，官方文件未提及 per-request 逾時） |
| 免費 Postgres 是否長期可用 | Neon Free：只要 < 0.5GB，**沒有期限、不會過期** | 依用量計費，無上限 | 未查到獨立免費 Postgres 方案（見 [Fly.io Pricing](https://fly.io/docs/about/pricing/)，只指向另一份含價格的 Managed Postgres 文件） | **免費 Postgres 30 天後過期，過期後 14 天寬限期，之後直接刪除資料庫（含全部資料）** [Render Free 文件](https://render.com/docs/free) |
| 冷啟動／喚醒延遲 | Fluid compute 有 bytecode caching＋pre-warming，production 冷啟動已優化過（但仍是「有時要重新啟動」的架構） | 同左 | 常駐 VM 原則上沒有「冷啟動」這個概念（除非自己選擇讓機器休眠） | 免費方案本身閒置 15 分鐘會 spin down，下次請求約 1 分鐘後才恢復（[Render Free 文件](https://render.com/docs/free)）——**這件事跟 Vercel serverless 的冷啟動問題本質相同，甚至更慢**（Fluid compute 的恢復是毫秒級／幾百毫秒級，Render 免費方案是「about one minute」） |
| 换了省的是什麼 | — | **省複雜度不省錢的方向**——不用換程式碼、不用換資料庫、只是解除幾個數量上限（duration／log 保留／WAF 規則數）；要花錢（$20／人／月起） | **兩者都不確定會省**——常駐 VM 理論上消滅了「serverless 執行時間上限」與「函式冷啟動」這兩個問題本身不存在，但需要重寫部署方式（`api_app/` 現在是包成一個 FastAPI serverless function，搬過去要改成長駐程序）、自己管理連線池／健康檢查／零停機部署這些 Vercel 目前免費幫忙做掉的事——**複雜度不會消失，只是從「被平台限制」換成「自己維運」** | **同上，且免費層的 Postgres 30 天過期是一個新增的、Vercel／Neon 組合完全沒有的額外坑**（Neon Free 沒有時間到期，只有容量上限） |
| 目前 60 秒逾時真的是瓶頸嗎 | **不是**——這是自設值，Hobby 本身給 300 秒，換平台前先把自己的設定調高就已經解掉大部分「時間不夠」的擔心，不需要換平台 | — | — | — |

**這格結論最重要的一句話**：**本專案今天真正撞到的三道牆（Neon
0.5GB、Cboe 429 全站連坐、Vercel Hobby 各項免費額度）沒有一道是
「serverless 執行時間太短」造成的**——`REFRESH_RUN_BUDGET=45s` 是
自己選的保守值，不是被平台逼出來的；Cboe 的限流是 vendor 端的
問題，換到 Fly.io／Render 一樣要打同一個 Cboe 端點、一樣會被限流，
**跟主機平台是 serverless 還是常駐 VM 完全無關**。因此「換平台」在
現階段對本專案真正的三個痛點**幾乎沒有幫助**，只會換來要自己重新
處理部署、連線池、健康檢查這些現在由 Vercel 免費代勞的工作——這正是
下一小節「過早搬遷」原則要提醒的事。

### 5.4 避免過早搬遷（premature migration）的原則

業界對這件事有成熟、可引用的共識：**先問「不加新東西能不能解決
現在的問題」，而不是先問「該換哪個新工具」**。Etsy 工程師 Dan
McKinley 在他自己撰寫、被廣泛引用的工程文化文章裡提出這個檢驗
方法：

> "Consider how you would solve your immediate problem without
> adding anything new. First, posing this question should detect
> the situation where the 'problem' is that someone really wants
> to use the technology."
>
> "The answer to this question in practice is almost never 'we
> can't do it,' it's usually just somewhere on the spectrum of
> 'well, we could do it, but it would be too hard.'"
>
> —— Dan McKinley, [*Choose Boring Technology*](
> https://mcfunley.com/choose-boring-technology)（作者本人網站，
> 2026-09-11 查閱）

另一個更基礎、來自軟體工程方法論的原則是 **YAGNI**（You Aren't
Gonna Need It）——不要為了「以後可能需要」而現在就建：

> "You Aren't Gonna Need It" is a mantra... capabilities presumed
> necessary in the future should not be built now because "you
> aren't gonna need it"... even with careful analysis, only
> one-third of anticipated features actually delivered intended
> value.
>
> —— Martin Fowler, [*Yagni*](https://martinfowler.com/bliki/Yagni.html)
> （作者本人網站，2026-09-11 查閱）

把這兩條原則套進本專案：**現在還沒有真實的公開流量數據**（Public
Beta 尚未開始），在完全沒有真實用量訊號的情況下討論「該不該搬到
Fly.io」，正是 McKinley 說的「問題其實是有人想用新技術」的典型
情境。5.2 節列出的四個訊號，就是把「以後可能需要」換成「出現具體
證據才動」的落地方式。

### 5.5 總表：訊號 → 大概門檻 → 若搬能省什麼

| 訊號 | 大概門檻（量級，非精確值） | 若搬到常駐 VM 平台（Fly.io／Render 這類）能省什麼 | 本輪建議 |
|---|---|---|---|
| Neon 儲存逼近 0.5 GB | 連續一週 > 80% | **不省**——常駐 VM 平台的 Postgres 一樣是照容量計費／或一樣有免費層容量上限（Render 免費層甚至有 30 天過期這個更嚴格的限制），换到付費 Neon 分層或付費常駐 Postgres 都要花錢，不換平台本身不解決容量問題 | 先升級 Neon 到付費層（$0.35／GB-月起），不必連 compute 平台一起換 |
| Cboe 429 常態化（每月個位數次以上持續性事故） | 每月 ≥3–5 次 `is_sustained_incident` | **不省，完全無關**——這是 vendor 端限流，跟主機是 serverless 還是常駐 VM 無關 | 檢視第 4.1 節的條款風險本身，可能需要考慮申請付費、有官方授權的資料源（既有研究已列出 Market Data App／ORATS／Alpha Vantage 等候選），不是换主機平台 |
| Vercel 常態 p95 延遲逼近 45 秒自設預算 | 連續多日 p95 > 35 秒 | **可能省一點**——常駐 VM 沒有函式冷啟動，但本專案的延遲瓶頸主要是外部 vendor 網路往返（Cboe／Treasury／Yahoo），不是平台本身的運算能力，換平台前應先確認慢在哪一段 | 先用既有 `/api/ops/metrics` 量測慢在哪一段，不要假設換平台就會變快 |
| Runtime Logs 1 小時不夠用、多次追不回事故 | 每月 ≥2 次因 log 消失查不出原因 | 這道牆本身升級 Vercel Pro（Log Drains）即可解，**不需要換整個主機平台** | 升級單一功能，不是全套搬遷的理由 |
| **本輪結論** | — | — | **以上四個訊號目前皆未出現（Public Beta 尚未開始），現在不建議搬遷；本節的角色是「以後不必每次從零討論」的檢查清單，不是行動項目** |

---

## 6. 這對 Option Chaser 意味著什麼

1. **Cboe 與 Yahoo 的自動化擷取條款是本輪最重要的發現，且很可能已經
   是既有事實，不是 Public Beta 才出現的新問題**【法規／安全必要】
   ——這兩家的官方條款都明文禁止「自動抓取程式擷取資料」，Cboe 更
   明確威脅會封鎖 IP。這不是「用量大才會踩到」的門檻，Public Beta
   只是提高了被偵測到、影響全站的機率。這件事需要 Owner 自己評估
   風險承受度並決定要不要處理（例如：改用有官方授權的付費資料源、
   或接受現有風險維持現狀），**本文件不建議任何特定做法，只呈現
   事實**。
2. **`vercel.json` 現有的 `maxDuration: 60` 是可以放寬的自設值，
   不是平台逼出來的上限**【Option Chaser 產品選擇】——Hobby 方案
   本身就給到 300 秒。若未來覺得 45 秒的 `REFRESH_RUN_BUDGET`
   太緊，有 5 倍的餘裕可以直接調高設定值，不需要升級付費方案、
   也不需要重新設計 Refresh Run 架構。
3. **Vercel Hobby 方案「非商業、個人用途」的限制，依官方定義本產品
   現在不算商業使用，維持免費方案在條款上沒有問題**【法規／安全
   必要】——但這個結論的前提（不收費、不打廣告、沒有人因此拿報酬）
   一旦改變，需要重新檢查。
4. **Production 網域維持公開這件事，已經是既有事實，不是一個需要
   重新裁示的待決策項**【Option Chaser 產品選擇，Owner 已定案】——
   目前 Standard Protection 設定下，`option-chaser.vercel.app`
   本身就不需要登入即可存取，這正好符合 Public Beta「匿名使用者
   直接進來用」的需求，維持現狀即可。
5. **WAF Rate Limiting 在 Hobby 免費方案上就能開**【業界慣例】——
   雖然只有 1 條規則、Fixed Window 演算法，但對「擋單一 IP 打太快」
   這種公開測試最基本的防線已經足夠，且完全不需要升級付費方案，
   建議 Public Beta 開始前先設好這一條規則。
6. **`pg_cron` 在 Neon Free 上「文件沒禁止，但架構上形同虛設」**
   【Option Chaser 產品選擇】——因為 Free 方案的 autosuspend 不能
   關閉。清理排程要延續本專案既有的「Vercel Cron 從外面打 HTTP
   端點喚醒」模式（Treasury 預熱端點已經是這個模式的先例），不要
   假設可以直接排一個資料庫內部的 cron job 定期跑。
7. **Runtime Logs 在 Hobby 上只留 1 小時**【業界慣例】——出事後
   若沒有在 1 小時內把 log 存下來（例如靠既有 `diagnostics` 表或
   `/api/ops/metrics` 這類自建、獨立於 Vercel Runtime Logs 的機制），
   就永久看不到當時發生了什麼。本專案已經有一套獨立的 Application
   Diagnostics（spec #143）與 operational metrics（SCALE-08），
   這兩套本來就不依賴 Vercel Runtime Logs 的保留期，是既有的、
   已經解決這個問題的機制，不需要為 Public Beta 額外做什麼。
8. **Neon 儲存與 Cboe 429 是兩道真正的牆，但都跟「要不要換平台」
   無關**【業界慣例】——換到 Fly.io／Render 這類常駐 VM 平台不會
   讓 Cboe 條款變寬鬆，也不會讓 Neon Free 的 0.5GB 變大；現階段
   換平台換不到任何實質好處，只會多出自己維運部署／連線池／健康
   檢查的複雜度。
9. **本輪找到但依 Owner 明確裁示不需要處理的項目**：production
   protection 現在不開（Owner 已定案，本文件只確認技術含意，不
   建議變更）；是否搬遷主機平台（本文件明確結論是現在不建議）。

---

## 7. 誠實揭露：本輪沒查到 / 查不到的事

- **這個 Vercel 專案目前實際的 Fluid Compute 開關狀態、以及
  Deployment Protection 記錄值的字面 API 名稱**，本輪未直接查詢
  Vercel MCP 工具去讀取這個專案的即時設定——CLAUDE.md 過往多次
  session（2026-08-24、2026-08-31 等）已經記錄過這條路徑對本專案
  結構性失敗（MCP 讀回工具對這個帳號底下的專案一律 404／403，屬
  已知工具整合缺陷），本輪判斷重試不會拿到新結果，因此改為完全
  依官方文件對「這個設定值該有什麼行為」的說明作答，而非直接讀取
  這個特定專案的即時設定值。若要 100% 確認，Owner 自己到 Vercel
  Dashboard 看一眼最準確、最快。
- **Neon Free 方案預設對應的 compute CU 大小、以及對應的最大同時
  連線數**——官方文件按 CU 大小列出連線數表格，但沒有明確指出
  Free 方案的預設／上限 CU 落在哪一格。
- **`pg_repack` 具體是哪個付費方案起可用**（只確認「付費方案可用，
  Free 不可用」，Launch／Scale 的分界未查到）。
- **GitHub Actions 的 Postgres service container 是否有任何方案層
  級限制**——官方文件只講技術用法，未查到方案限制的明文聲明（合理
  推測是沒有限制，因為這是標準 Actions 語法而非另計費功能，但沒有
  查到直接聲明）。
- **GitHub push protection 對 public repo 是否預設自動開啟**——
  本輪多次嘗試查證正確的官方文件網址皆 404，未能在時限內找到可
  重新核對的一手頁面；secret scanning alerts 本身「對 public repo
  免費可用」已確認，push protection 的預設狀態則列為 UNVERIFIED。
- **GitHub Repository Rulesets 在「public repo＋GitHub Free 個人
  帳號」與「Team／Enterprise 才能用 rulesets」這兩段官方文字之間
  的確切關係**——本輪判斷是「基本 ruleset 功能 vs. 組織層級進階
  子功能」的差異，但沒有找到一份把兩者關係講清楚的單一權威頁面，
  這是我的推論、不是我直接讀到的定論。
- **Nasdaq（`api.nasdaq.com`）與 Financial Modeling Prep 的官方
  網站條款完整逐字原文**——本輪嘗試直接讀取官方條款頁面時分別
  收到 HTTP 503／403，只取得經 WebSearch 整理的二手摘要，未能取得
  可逐字引用的一手原文；因兩者在本產品都是次要備援資料源（Nasdaq
  是股利抓取鏈的第三備援，FMP 需要目前很可能未設定的 `FMP_API_KEY`
  才會被觸發），曝險頻率遠低於 Cboe／Yahoo，本輪判斷優先度足以
  接受這個查證缺口，未繼續深挖。
- **Market Data App 官方條款頁面的完整逐字原文**——同上，多次嘗試
  完整讀取該頁時遇到內容截斷，取得的是搜尋引擎回傳的頁面片段而非
  完整一手原文，且條款本身沒有明確處理「伺服器代打、資料只回給
  token 本人」這種中間型態，這題本身就需要向 Market Data App 官方
  客服直接確認才能真正解決，不是靠更仔細讀條款文字就能解決的查證
  缺口。
