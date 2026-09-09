# Runtime Targeted Scaling — Fluid Compute 與 Python Background Execution 查證

**本文性質**：這不是一輪新的大型研究，是一份**針對性 addendum**，只
回答兩份既有文件明文標記為「未查證」的具體事實：

1. `docs/research/market-data-lifecycle-scaling.md` §「本輪明確的取材
   與量測限制」第 4 項——「Python runtime 是否有 `waitUntil` 等價物、
   部署專案實際是否啟用 fluid compute（僅能依『2025-04-23 後建立的
   新專案預設啟用』推定）」。
2. `docs/wayfinder/scaling-foundation.md` §9 Q6——同樣兩個問題，並
   點名它們分別決定 §7.1（process-local cache 能不能當 L1）與 §6.2
   （stale-while-revalidate 可不可行）。

**本文不推翻、不改寫、不擴充上述兩份文件的任何既有結論**——本文只
負責把 Q6 點名的兩件事查清楚，並回頭在原文加一句指標。查證日期：
**2026-09-04**（本文所有「存取日期」皆同此）。

**證據分級規則**（本文全程遵守）：每一項主張都標記三級之一——
**官方保證**（官方文件明文陳述為事實／預設行為）／**production 實測**
（直接對真實 `option-chaser` production 專案觀測到的結果）／
**合理推定**（未直接觀測，從文件措辭或平台通例推論）。**推論絕不
包裝成事實呈現。**

---

## 1. Q1｜Fluid Compute 是否確定 enabled？

### 1.1 Tier 1（最高優先）：直接查詢 production 專案 config——**嘗試
過，結果是「structurally 查不到」，不是「沒查」**

依指示載入 Vercel MCP 工具（`list_projects`／`get_project`／
`get_deployment`／`get_git_deployment_context`／
`get_project_deployment_protection`）並實際呼叫，而非假設會失敗：

| 呼叫 | 結果 |
|---|---|
| `list_teams` | 成功，回傳唯一團隊 `ofriedoriceo-5352's projects`（`team_SyK6VaGTHE1dU8oTppOX0hRc`），與 production preview 網址 `option-chaser-git-claude-imp-aef368-**ofriedoriceo-5352s-projects**.vercel.app` 的 team slug 逐字吻合——確認查的是對的團隊 |
| `list_projects(teamId=...)` | 回傳 `{"projects": []}`——**這個團隊底下一個專案都列不出來**，不只是 `option-chaser` |
| `get_project(projectId="option-chaser", teamId=...)` | `404 Not Found` |
| `get_deployment(idOrUrl="option-chaser.vercel.app", teamId=...)` | `404 Not Found`，body：`{"error":{"code":"not_found","message":"Deployment not found"}}` |
| `get_git_deployment_context()` | 回傳同一個團隊，但 `"linkedProjects": []`、`"originConnections": []`——**連「有沒有連 git」都查不到** |
| `get_project_deployment_protection(projectId="option-chaser", ...)` | `404 Not Found` |
| `web_fetch_vercel_url("https://option-chaser.vercel.app/api/health")` | `{"success": false, "info": "Unable to create shareable URL..."}` |

**這是一個比先前紀錄更明確的結果**：先前 CLAUDE.md 記載的已知
缺陷是「MCP 自己剛建立的**臨時**專案讀不回來」（`option-chaser-
vendor-probe` 等）；本輪確認的是——**這個 MCP session 對它宣稱擁有的
那個團隊底下，連一個專案（包含真實、長期存在、git-linked 的
production 專案 `option-chaser`）都完全看不到**。最可能的解釋是這個
Vercel MCP 的 OAuth 授權範圍與實際擁有 `option-chaser` 專案的帳號／
權杖不是同一組（`list_teams` 回傳的團隊名稱字面對得上不代表底層
token 對那個團隊有專案讀取權）。**這件事本身沒有被更深入追查**——
往下追查 OAuth／權杖歸屬需要人為介入 Vercel 帳號設定，超出本輪
targeted research 的範圍，且原始任務指示是「report exactly what
actually happens」，不是排除這個整合缺陷。

**判定**：Tier 1 直接查詢**不可行**（不是「懶得查」，是六種呼叫方式
全部失敗，含最基礎的「這個團隊有哪些專案」）。

**Owner 可自行完成、成本最低的替代查法**（見 §2.4 官方文件對 dashboard
路徑的明確指引）：登入 Vercel 帳號 → 進入 `option-chaser` 專案 →
**Settings → Functions** → 找到 **Fluid Compute** 那個區塊，直接看
那個開關目前的狀態。這是官方文件本身給出的唯一標準檢查路徑
（見 §1.3），一分鐘可完成，比任何 API 或程式碼側手法都直接。

### 1.2 Tier 2：repo 設定面——**確認沒有任何本地覆寫**

- `vercel.json`（全文，任務指示中已給出）**沒有** `fluid` 這個
  key。【官方保證】fluid compute 可以透過 `vercel.json` 的
  `{"fluid": true}` 逐專案／逐環境設定（見 §1.3 引用），**這代表
  本 repo 沒有任何程式碼層的顯式開關**——目前的狀態完全取決於 Vercel
  **dashboard 端的專案設定**，本輪對 repo 本身的檢查查無此設定
  ，不代表帳實際狀態。
- 對整個 repo（不含 `.venv` 第三方套件，那些是 Python/Scheme/APDL
  等語言裡巧合帶有 "fluid" 字樣的無關符號）逐字掃描 `fluid`：
  唯二命中處是既有的 `docs/research/market-data-lifecycle-scaling.md`
  與 `docs/wayfinder/scaling-foundation.md` 自己（本輪要修的那兩處
  未查證項），沒有第三處 config 檔案。
- 沒有 `.vercel/project.json`（未本地連結專案），本輪也未新增。

### 1.3 Tier 3：官方文件——精確引文＋存取日期

**S1｜`https://vercel.com/docs/fluid-compute`**（存取
2026-09-04，頁面自報 `Last updated August 24, 2026`）：

> "As of April 23, 2025, fluid compute is enabled by default for new
> projects."

> "You can enable fluid compute through the Vercel dashboard or by
> configuring your `vercel.json` file for specific environments or
> deployments."

該頁全文檢索**沒有**任何「既有（pre-2025-04-23）專案是否會被自動
遷移／grandfather 到預設啟用」的說明——只講「new projects」。這代表
「新專案預設啟用」這條規則的適用範圍**在官方文件裡本身就是有邊界
的**，不能不加區分地套用到任何一個專案。

**檢查步驟原文（官方指引，dashboard 路徑）**：

> "Navigate to your project's Functions Settings in the dashboard"
> → "Locate the **Fluid Compute** section" → "Toggle the switch to
> enable fluid compute for your project" → "Click **Save**..." →
> "Deploy your project for the changes to take effect."

（連結目標路徑樣式：`/[team]/[project]/settings/functions`）

**S1-b｜同頁「Isolation boundaries and global state」小節**（逐字，
即 §7.1 已引用的那句話的完整上下文）：

> "Fluid compute uses a different approach to isolation. Instead of
> using a microVM for each function invocation, **multiple
> invocations can share the same physical instance (a global
> state/process) concurrently.** This allows functions to share
> resources and execute in the same environment, which can improve
> performance and reduce costs."

**關鍵字仍然是 "can"，不是 "will" 或 "always"**——這句話本身**不
保證**任何特定請求會落在被重用的實例上，也不保證重用會發生。這是
§7.1 既有推導的原始依據，本輪逐字覆核，用字與既有引用完全一致。

**S1-c｜同頁「Available runtime support」小節**（逐字）：

> "Fluid compute is available for the following runtimes:
> Node.js / Python / Edge / Bun / ..."

【官方保證】Fluid compute（含上面的 instance-sharing 機制）**明確
涵蓋 Python runtime**，不是 Node.js 限定功能——這對本專案有直接
意義：`option-chaser` 的後端是 Python（FastAPI，`api/index.py`），
§7.1「process-local cache 只能當 L1」的推導對象（Python 行程）確實
是這個機制設計上會作用到的對象，不是文件討論的是別的 runtime。

### 1.4 四個子問題逐一回答

**a. production 是否確定 enabled？**

**NOT_CONFIRMED**（結論不是「未查」，是「查過、查不到」）。

- 【production 實測】：本輪**沒有**、也**無法**取得 `option-chaser`
  production 專案的 Fluid Compute 開關狀態——六種 MCP 查詢路徑全數
  404／空陣列（§1.1）。
- 【官方保證】：`vercel.json` 沒有顯式 `fluid` key（§1.2），代表
  「若有值，值來自 dashboard 專案設定，本輪查不到那個值」。
- 【合理推定】：如果比照先前研究的邏輯——本專案 Vercel 部署（V1／
  #48）是在這個 repo 自己的時間軸「2026-08 前後」才第一次建立，
  遠晚於官方文件的 2025-04-23 分界，若這個專案是**當時全新建立**
  （而非更早建立、事後才接上 git），依官方文件字面就會落在「新
  專案預設啟用」的規則裡。**但這正是原始任務指示明令禁止當最終答案
  用的那個弱推論**——它沒有排除「專案其實更早建立、之後才被此
  session 使用」、也沒有排除「Owner 事後在 dashboard 手動關閉過」
  這兩種可能。本文如實把它列為**合理推定**，不升級為 production 實測
  或官方保證。

**b. 如果無法直接驗證，能證明到什麼程度？**

最強的證據鏈是：(1) 官方文件明確界定「新專案預設啟用」規則的觸發
條件與生效日期（S1，官方保證）；(2) repo 本身沒有任何顯式覆寫這個
預設值的設定（Tier 2，直接檢視 repo 得到的事實）；(3) 本輪**確實
嘗試**過六種不同的直接查詢路徑，全部得到一致、可重現的「查不到」
結果，而非單一工具的偶發失敗（Tier 1，過程與結果皆逐一記錄）。

殘留的不確定性：**(3) 本身就是「證明的極限」**——沒有一條路徑能
繞過它。唯一能把 (a) 從「合理推定」升級到「production 實測」的方法
是 Owner 親自用官方文件給的 dashboard 路徑（§1.3）看一眼，這是
本輪能提供的最務實的下一步，而不是本 session 自己想辦法繞過去。

**c. process/global memory 是否可能被後續 invocation 重用？**

【官方保證，逐字引用見 §1.3 S1-b】"multiple invocations **can**
share the same physical instance (a global state/process)
concurrently."——**這是「可能」，用字是 "can" 不是 "will"**，官方
文件本身沒有承諾任何關於實例數量、實例存活時間、哪個請求落在哪個
實例、冷啟動頻率的保證。這句話**無論 (a) 的答案是 CONFIRMED 或
NOT_CONFIRMED 都成立**——它描述的是 fluid compute 這個機制本身的
性質，不是本專案有沒有開啟它；本專案若確實開啟，這個「可能但不保證」
的性質原封不動適用；若沒開啟，這句話乾脆不適用（傳統 microVM 模型
下每次呼叫都是獨立隔離的，連「可能重用」都不成立）。

**d. 哪些部分只能當 L1 optimization、絕不能當 correctness guarantee？**

從 (c) 直接推導，與 `docs/wayfinder/scaling-foundation.md` §7.1
既有判斷完全一致、本輪不做任何修改，只是重新確認這個推導的前提
（"can" 不是 "will"）本身是逐字準確的官方引用：**任何假設「暖啟動
時某個 process-local 狀態一定會被下一個請求重用」的設計都不安全**
——例如「同一個 freshness 窗內只打一次上游」這種正確性承諾在
process-local 快取上結構上無法成立，不論 (a) 的答案是什麼。它能做的
只是「命中就省一次請求，沒命中就照常走」的 best-effort hit-rate
優化，價值無法事先預測、不該寫進任何契約——這正是 §7.1 原文的立場，
本輪查證後**沒有推翻它，反而讓它的前提更站得住腳**（因為 (a) 是
NOT_CONFIRMED，意味著這個「不能依賴」的警告比原本設想的更該被
遵守——連「有沒有開」都不確定的情況下，設計上更沒有理由去賭它）。

---

## 2. Q2｜Python Background Execution

### 2.1 官方文件逐一核對

**S2｜`https://vercel.com/docs/functions/functions-api-reference/
vercel-functions-package`**（存取 2026-09-04，頁面自報 `Last
updated September 3, 2026`）——**頁面 `<title>` 本身就是**
`"@vercel/functions API Reference (Node.js)"`。`waitUntil()` 與
`after()`（Next.js 15.1+）都定義在這一頁，即 npm 套件
`@vercel/functions`（`import { waitUntil } from '@vercel/functions'`）
——**這是 JavaScript/TypeScript 套件，明確標註 Node.js**，不是
語言無關的平台層 API。

**S3｜`https://vercel.com/docs/functions/functions-api-reference/
vercel-sdk-python`**（存取 2026-09-04，頁面自報 `Last updated
August 11, 2026`）——這是官方 Python SDK（`vercel` Python 套件）的
完整參考頁。**該頁全部章節逐一列出如下，窮舉、非摘錄**：

> `install-and-use-the-package` / `helper-methods`（僅含
> `get_env`／geolocation 相關輔助函式）/ `geolocation` /
> `runtimecache`（`RuntimeCache`／`AsyncRuntimeCache`，是**快取**
> 原語，語意等同一個帶 TTL 的 key-value store，跟「在回應送出後繼續
> 背景執行工作」完全不同的概念）/ `specification` /
> `limits-and-usage`

**全文檢索 `waitUntil`／`wait_until`／`RequestContext`／
`background`（實質語意，非導覽列雜訊）在這一頁全數零命中。**

**S4｜`https://vercel.com/docs/functions/runtimes/python`**（存取
2026-09-04，頁面自報 `Last updated August 12, 2026`）——這是 Python
runtime 的主文件頁（確認本專案用的形態：ASGI/WSGI，`api/index.py`
命中官方列出的合法檔名清單之一）。**全文檢索 `waitUntil` 零命中。**

**S5｜`https://vercel.com/changelog/waituntil-is-now-available-for-
vercel-functions`**（存取 2026-09-04，官方 changelog，發布日
`10 May 2024`）——`waitUntil` 功能發布公告本身逐字寫：

> "...supported in **Node.js and Edge runtimes**..."

這是 `waitUntil` 這個 API **從第一天發布起，官方口徑就明確限定在
Node.js 與 Edge runtime**（2024-05-10，早於 fluid compute 2025-04-23
上線）。本輪未找到任何後續官方文件把這條範圍擴大到涵蓋 Python。

**S1-c 的反向確認**（§1.3 已引用）：fluid compute 本身（instance
共用、動態 scaling、optimized concurrency）在官方文件裡明確涵蓋
Python runtime——但這是「fluid compute 這個底層機制對 Python 生效」，
跟「Python 有沒有一個公開 API 可以呼叫『回應送出後繼續跑』」是兩件
不同的事。**底層機制存在，不代表有對外暴露的程式介面。** 本輪查證
的正是後者，而後者在四份不同官方頁面（S2／S3／S4／S5）上得到一致、
互相印證的否定結果。

### 2.2 社群來源（次要，明確標示，不當主要證據）

WebSearch 帶回一篇 dev.to 部落格（"Background Jobs on Vercel in
2026: Field Notes on waitUntil, Queues, Workflow, and Cron"）的
搜尋摘要聲稱 waitUntil「supported on the Node.js, Bun, Rust, and
Python runtimes」。**這條陳述與本輪四份官方一手文件（S2／S3／S4／
S5）互相矛盾**——尤其與 S2 頁面標題本身寫死 "(Node.js)"、S3（官方
Python SDK 完整參考頁）窮舉六個章節裡完全沒有這個 API、S5（官方
2024 年發布公告原文）明講範圍是 "Node.js and Edge runtimes" 三者
矛盾。**本文採信官方一手文件、不採信這則社群摘要**——理由：官方
文件是 2026 年當下（本輪存取日）的即時內容，S3 頁面結構上不可能
「忘記列出」一個已存在的公開 API（那是它唯一的職責），而社群部落格
可能混淆了「fluid compute 機制對 Python 生效」（真，S1-c）與
「waitUntil 這個具體 API 對 Python 可用」（本輪四份官方頁面皆未見）
兩件事。**這一點記入 §5「還是不確定的部分」，不強行消除這個矛盾**
——本 session 沒有管道取得比官方文件更權威的來源來仲裁。

### 2.3 四個子問題逐一回答

**a. Python function 回 response 後，是否能可靠繼續執行工作？**

**NOT_SUPPORTED（as officially documented）**。官方文件裡沒有任何
一個 Python 專屬的 API 承諾「回應送出後仍保證繼續執行」。§1.3 S1-c
確認的「fluid compute 機制本身對 Python 生效」只代表**同一個
process 可能被下一個 invocation 重用**（跟 Q1 的 "can" 精確同一
性質，不是保證），**不代表**有任何機制讓「這次請求自己發起的背景
工作」在這次 HTTP response 已經送出之後被平台保證跑完。這是兩個不同
的承諾層級，官方文件只給了前者（machine 層級的可能共享），沒有給
後者（application 層級的背景任務保證）。

**b. 官方 API／限制是什麼？**

**No official Python equivalent of `waitUntil`/`after()` documented
as of 2026-09-04.** Python 官方 SDK（`vercel-sdk-python`，S3）目前
公開的能力集合窮盡於：`get_env`、geolocation 輔助函式、
`RuntimeCache`/`AsyncRuntimeCache`（快取，非背景執行）。Node.js
專屬的 `@vercel/functions` 套件（S2）才有 `waitUntil`/`after()`，
且該頁自己的 `<title>` 明確標註 "(Node.js)"。

**c. 是否適合 Treasury／Dividend stale-while-revalidate？**

依 (a)(b) 的結論：**目前這個 fire-and-forget 形態的 SWR（先回舊值、
背景默默更新、不讓使用者等）在 Python function 上沒有官方支持的
實作路徑**。這件事**直接印證、而非推翻**
`docs/wayfinder/scaling-foundation.md` §6.2 表格裡已經寫的判斷——
該表格本來就把「Stale-while-revalidate」標成「需要背景執行機制
（⚠ 未查證）」；本輪把那個「⚠ 未查證」實心地確認為「查證後：沒有
這樣的官方機制」，**結論方向沒有變，只是從『不確定』變成『確定不
支援』**，因此 §6.2 那一行原本的判斷（划算但需要背景更新機制）現在
可以更堅定地說：**若要做 SWR，觸發方式必須改成別的形狀**（見下方
(d)），不能規劃成「fire-and-forget 背景更新」這個原始想像的形狀。

**d. 如果不支援，最小替代方案有哪些？**（範圍限定：只列與 Option
Chaser 直接相關的選項，不涉及 queue／Kafka／microservice）

1. **Synchronous refresh-on-miss（同步、請求內刷新）**——目前
   `treasury_cache.py`／`rate_cache.py`／`dividend_cache.py`
   三者其實**已經是這個形狀**（PERF-03／#179 等既有票已落地）：
   cache miss 或陳舊時，**在同一個請求內**同步打上游、拿到新值才
   回應，不是背景更新。缺點是那個「不幸撞上 miss」的請求要多等一次
   上游延遲；優點是零額外機制、正確性由請求本身保證，不依賴任何
   平台承諾。
2. **Vercel Cron Job 打專屬 refresh endpoint（排程式主動刷新，
   非請求觸發）**——每個市場日開盤前（或 Treasury 15:30 ET 發布後）
   由 Cron 主動打一次某個「只做刷新、不服務使用者請求」的端點，把
   快取填新。這是 §6.2 已有的既有選項之一（`docs/wayfinder/
   scaling-foundation.md` 已在別處討論過 Hobby cron 一天一次的限制，
   本文不重複），**不依賴 waitUntil**，因為 Cron invocation 本身
   就是一個完整、允許跑到完成的 HTTP 請求，不需要「回應送出後還要
   繼續」這件事。
3. **兩者疊加**：Cron 負責「日常、可預期」的刷新（降低多數使用者
   撞上 miss 的機率），同步 refresh-on-miss 當保底（Cron 沒跑到、
   或跑失敗時，第一個撞上舊資料的請求還是能自己救回來）——這正是
   選項 1 與 2 的組合，不是第三種新機制。

**這三項都不需要任何 Python 背景執行 API**——它們把「背景」這件事
從「同一個 process 生命週期內自己延續」換成「另一次獨立的
invocation」（不論是使用者的下一次請求，還是 Cron 觸發的那一次），
繞開了 (a)(b) 確認的那個缺口。

---

## 3. 對 Wayfinder 既有結論的影響（本文只指出，不動手改）

| 既有段落 | 查證前狀態 | 查證後狀態 | 結論方向是否改變 |
|---|---|---|---|
| §7.1 process-local cache 只能當 L1 | "can" 不是 "will"，因此不能當 correctness layer；附帶一個未查證的「是否真的 enabled」 | 同一個推導邏輯不變（"can" 用字逐字覆核成立）；「是否 enabled」查證後結果是 **NOT_CONFIRMED**（比原本「不確定」更明確地不確定——嘗試查過、查不到） | **沒有改變**，反而更站得住腳——連「有沒有開」都無法確認時，更沒有理由把任何正確性建立在它上面 |
| §6.2 stale-while-revalidate 需要「背景執行機制」 | 標「⚠ 未查證」，方向未定 | 官方文件確認 Python **沒有** `waitUntil`/`after()` 這類公開 API（S2/S3/S4/S5 四份一致） | **從「不確定」變成「確定不可行（以 fire-and-forget 的原始形狀）」**——但 SWR 這個目標本身不必因此放棄，§2.3(d) 給出兩個不依賴背景執行 API 的替代觸發形狀，方向是「換觸發方式」而非「整個放棄 SWR」 |

（以上僅為本文內部整理，供人工比對；實際回頭修改 §7.1／§9 原文
的動作，見 repo 內對這兩份文件的獨立 pointer 編輯，不在此表格內
執行任何修改。）

---

## 4. Sources / Evidence

### 4.1 Vercel MCP 直接查詢（2026-09-04，production 專案）

| # | 呼叫 | 結果 |
|---|---|---|
| M1 | `list_teams` | 成功，回傳 `ofriedoriceo-5352's projects` |
| M2 | `list_projects(teamId=team_SyK6...)` | `{"projects": []}` |
| M3 | `get_project(projectId="option-chaser", ...)` | `404 Not Found` |
| M4 | `get_deployment(idOrUrl="option-chaser.vercel.app", ...)` | `404 Not Found` |
| M5 | `get_git_deployment_context()` | `linkedProjects: []`、`originConnections: []` |
| M6 | `get_project_deployment_protection(projectId="option-chaser", ...)` | `404 Not Found` |
| M7 | `web_fetch_vercel_url("https://option-chaser.vercel.app/api/health")` | `success: false` |
| M8 | `curl https://option-chaser.vercel.app/api/health`（繞過 MCP，直接打 production） | `HTTP/2 200`，`{"status":"ok","engine_version":"0.5.0","storage":"postgres",...}`，headers 含 `x-vercel-id: iad1::iad1::wdc6m-...`——**production 本身可達，問題在 MCP 對這個專案的可見度，不是 production 本身壞了** |

### 4.2 官方文件（全部 2026-09-04 存取，`curl` 直連，非 WebFetch——
本沙箱環境對 `vercel.com` 的 `curl` 暢通、`WebFetch` 未測試但依 repo
既有環境備註優先用 `curl`）

| # | Source | 頁面自報 last_updated | 取得的確切內容 |
|---|---|---|---|
| S1 | `https://vercel.com/docs/fluid-compute` | 2026-08-24 | "As of April 23, 2025, fluid compute is enabled by default for new projects."／"multiple invocations can share the same physical instance (a global state/process) concurrently"／dashboard 檢查路徑：Settings → Functions → 「Fluid Compute」區塊／runtime 支援清單含 Node.js、**Python**、Edge、Bun |
| S2 | `https://vercel.com/docs/functions/functions-api-reference/vercel-functions-package` | 2026-09-03 | 頁面 `<title>` 為 `"@vercel/functions API Reference (Node.js)"`；`waitUntil()`／`after()` 定義於此，`import { waitUntil } from '@vercel/functions'` |
| S3 | `https://vercel.com/docs/functions/functions-api-reference/vercel-sdk-python` | 2026-08-11 | 官方 Python SDK 完整參考頁，六個章節窮盡列出：`get_env`／geolocation／`RuntimeCache`／`AsyncRuntimeCache`／specification／limits-and-usage。**零 `waitUntil` 命中** |
| S4 | `https://vercel.com/docs/functions/runtimes/python` | 2026-08-12 | Python runtime 主文件（ASGI/WSGI，合法檔名含 `index.py`/`main.py` 等）。**零 `waitUntil` 命中** |
| S5 | `https://vercel.com/changelog/waituntil-is-now-available-for-vercel-functions` | 發布日 2024-05-10 | "...supported in **Node.js and Edge runtimes**..."（官方 changelog 原文，`waitUntil` 首發範圍聲明） |

### 4.3 社群次要來源（明確標示，未採信為結論依據）

| # | Source | 說明 |
|---|---|---|
| C1 | dev.to：「Background Jobs on Vercel in 2026: Field Notes on waitUntil, Queues, Workflow, and Cron」 | WebSearch 摘要聲稱 waitUntil 支援 Python runtime，**與 S2/S3/S4/S5 四份官方一手文件矛盾**，本文不採信，列入 §5 |

---

## 5. 還是不確定的部分（誠實列出，不強行下結論）

1. **`option-chaser` production 專案本身的 Fluid Compute 開關狀態
   仍然是未知數。** 本輪窮盡了本 session 可用的每一種查詢管道
   （§4.1），全數指向「這個 MCP 整合對這個團隊／專案沒有讀取權」，
   而不是「查了、答案是關閉」。**這件事只有 Owner 本人登入 Vercel
   dashboard 才能在一分鐘內解決**（路徑見 §1.3／§1.4-b）——這不是
   本 session 能力範圍內能再進一步的事。
2. **C1（dev.to 部落格）與四份官方文件的矛盾未被仲裁。** 本文選擇
   採信官方文件（理由見 §2.2），但沒有找到一份能明確解釋「為什麼
   一篇 2026 年的部落格會聲稱一件當下官方文件矛盾的事」的第三方
   來源——可能是部落格作者的錯誤、可能是指某個尚未寫進公開文件的
   beta／私有功能、也可能是把「fluid compute 機制對 Python 生效」
   與「waitUntil 這個 API 對 Python 可用」兩件事搞混了（本文認為
   這是最可能的解釋，但沒有直接證據）。
3. **即使 Owner 確認 Fluid Compute 確實已 enabled，這也不會改變
   §7.1 的核心結論**（process-local cache 仍然只能當 L1，不能當
   correctness layer）——這點在 §1.4-d 已說明，這裡重申是為了避免
   Owner 查完開關狀態後誤以為「原來有開，那就可以放心依賴它」。
   "can" 不是 "will" 這件事跟開關狀態無關，是機制本身的性質。
