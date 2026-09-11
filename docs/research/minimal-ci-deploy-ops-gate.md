# Minimal CI／Deploy Gate／Ops 把關研究

研究日期：**2026-09-11**（本文全部「存取日期」皆同此，除非另外標註）。
對應 GitHub issue **#280**（Wayfinder 地圖 **#272「Anonymous Public
Beta」**的 research 子票之一）。

**本輪範圍**：純研究，不建立任何 `.github/workflows/*.yml`、不執行
`/security-review`、不 commit、不動 GitHub issue／PR、不跑測試套件本身
——只讀 repo 既有檔案確認現況、只查官方文件確認平台能力／價格／限制、
只把選項與代價攤開。**任何決定都留給 Owner。**

**證據分級**：全文標記 **【官方文件】**（平台自己的文件，附網址／
章節／存取日期）、**【repo 查核】**（我直接讀這個 repo 的檔案得到的
事實）、**【推估】**（我自己的估算，非實測，明確標出）、**【判斷】**
（我的分析與建議，非可驗證事實）。不確定的主張一律標 **UNVERIFIED**。

---

## 白話總結（給 Owner 看）

現在這個 repo **完全沒有 CI**——`.github/` 目錄根本不存在。有將近
2,000 條後端測試、761 條前端單元測試、123 條端對端測試，但這些測試
今天只活在「agent 每次施工完自己手動跑一次、貼在回報裡說全綠」這件
事上，沒有任何機制強迫它們在程式碼真的要上線之前一定要跑過。而
production 網址今天是 **push 到 `master` 就直接部署**，中間沒有任何
關卡——這件事在 Owner 自用階段風險有限，但接下來要做的
Anonymous Public Beta（匿名 cookie、rate limiter 這類真正碰得到陌生
人資料與安全的改動）一旦上線出包，影響的就不再是 Owner 自己一個人。

**這份研究最重要的一個發現，也是本文標題「CI 能不能真的擋住部署」
的答案**：Vercel 自己完全不會等外部 CI（GitHub Actions）跑完才決定
要不要部署——push 到 `master` 一律觸發建置與部署，這是 Vercel 官方
文件白紙黑字寫的行為，沒有任何官方開關能讓 Vercel「等 GitHub Actions
綠燈再部署」。但這不代表沒有辦法把關：GitHub 自己的 **branch
protection**（要求 PR 合併前必須 CI 通過）在**公開 repo 上完全免費**
，而這個 repo 剛好就是公開的。也就是說，只要 Owner 養成「先開 PR、
CI 跑過才按合併」的習慣（而不是像過去幾次那樣直接 push 到 master），
「CI 沒過就不會有新程式碼進 master」這件事在事實上就成立了——把關點
不是 Vercel，是 GitHub 的合併按鈕。

其他幾項發現同樣重要：**LINE Notify 已經在 2025 年 3 月確定收攤**
（LINE 官方公告，非傳聞），台灣使用者很容易誤以為還能用，這條路已經
死了；Vercel 免費方案（Hobby）的執行紀錄（Runtime Logs）**只留
1 小時**，過了就永遠查不到，這對「陌生人在半夜踩到一個 bug」這種
情境幾乎沒有用，因此一個免費、有 30 天保留期的錯誤追蹤服務（Sentry
免費層）不是錦上添花、而是這個階段少數真正該優先做的事；本 repo
已經有的 `/api/health` 端點剛好就是最省成本的「部署後健檢」入口，
不需要新建。

以下逐項附上官方出處，並在最後給出建議的優先順序。

---

## 0. Repo 現況（`repo 查核`，作為後續建議的基準）

- `.github/` 目錄不存在——**零 CI**【repo 查核，`ls -la`】。
- 後端測試由 `pytest` 執行，透過 `OC_TEST_DATABASE_URL` 環境變數切換
  「只跑記憶體假體」與「記憶體＋真實 Postgres 雙後端」兩種模式；未設
  該變數時 Postgres 契約測試會被跳過而非失敗【repo 查核，
  `pyproject.toml` `[tool.pytest.ini_options]`、`CLAUDE.md` §環境】。
  約 2,000 條測試（CLAUDE.md 最近一次記錄：後端全套 1700+ 條）。
- 前端 `package.json` 定義四個相關 script：`typecheck`
  （`tsc --noEmit`）、`test`（`vitest run`）、`build`（`tsc --noEmit
  && vite build`，即 typecheck 已內建在 build 裡）、`e2e`
  （`playwright test`）【repo 查核】。有 `package-lock.json`，可用
  `npm ci`。約 761 條 Vitest、123 條 Playwright（`iPhone`＋`Desktop`
  兩個 project）。
- `playwright.config.ts`：`fullyParallel: true`，兩個 project 靠
  `testMatch`/`testIgnore` 互不重疊；`webServer` 打本機 dev server
  （`http://127.0.0.1:5173`）；有 `PLAYWRIGHT_CHROMIUM_PATH` 環境變數
  可指定既有 Chromium 執行檔，避免重新下載瀏覽器【repo 查核】。
- `vercel.json` 的 `functions.maxDuration: 60` 是**自設值，不是平台
  上限**——見下方第 1 節與 CLAUDE.md 既有記錄的更正。
- `api_app/main.py` 已有 `GET /api/health`，回傳 `status`／
  `engine_version`／`storage`（實際使用的儲存後端，`postgres`／
  `memory`／`unavailable: ...`）／`rate`（利率快取狀態）
  【repo 查核，`main.py:905-942`】——這正是部署後健檢天然的目標端點，
  不需要新建。
- 全文 grep `CLAUDE.md`／`docs/deploy-vercel.md`：**沒有任何既有的
  Slack／webhook／LINE 通知整合**供這個專案使用【repo 查核】。
- 確認 `L26041040/option-chaser` 是**公開（Public）repo**
  【WebFetch `github.com/L26041040/option-chaser`，2026-09-11】。
- 現行部署模型：Vercel 的 Git 整合，push 到 `master` 直接觸發
  production 部署，中間沒有任何關卡【repo 查核，
  `docs/deploy-vercel.md`：「之後每次 push 到 master 就自動重新
  部署」；下方第 2 節有官方文件佐證】。

---

## 1. 用 GitHub Actions 跑現有四套測試

### 1.1 Postgres service container

【官方文件】GitHub Docs〈Creating PostgreSQL service containers〉
<https://docs.github.com/en/actions/how-tos/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers>
（存取 2026-09-11）給出的官方範例（job 直接跑在 runner 上、不是跑在
容器裡的情境，對應本 repo 這種單一 job 直接裝 Python/Node 的形狀）：

```yaml
services:
  postgres:
    image: postgres
    env:
      POSTGRES_PASSWORD: postgres
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
    ports:
      - 5432:5432
```

官方預設帳號是 `postgres`／預設資料庫也叫 `postgres`；job 用
`localhost:5432` 連線（不是用 service 的 label 名稱——label 名稱只在
job 本身也跑在容器裡時才用得上）。

這與本 repo 既有的本機開發慣例（`CLAUDE.md` §環境／
`docs/deploy-vercel.md`：`initdb --auth=trust`、`postgres` 使用者、
自訂 port）**形狀相容但細節不同**——本機用 `trust` 免密碼，官方
service container 範例用密碼；CI 只要把 `OC_TEST_DATABASE_URL` 組成
`postgresql://postgres:postgres@localhost:5432/postgres`（或先跑一步
`createdb octest` 對齊 `CLAUDE.md` 用的資料庫名稱）即可對齊，這是
純接線細節，未來寫 workflow 時再決定，不影響本研究結論。

### 1.2 各套件在 CI 大概要跑多久

**以下全部是【推估】，不是實測**——本輪未真的建立 workflow 執行過，
只能依測試數量與量級合理推算：

| 套件 | 【推估】CI 耗時 | 依據 |
|---|---|---|
| pytest 雙後端（~2,000 條，含 Postgres 啟動＋依賴安裝） | 約 5–10 分鐘 | 測試量體加上 `fastapi`／`psycopg[binary]`／`httpx`／`yfinance` 安裝時間、Postgres service container 啟動的健檢等待 |
| Vitest（~761 條，jsdom） | 1–2 分鐘內 | jsdom 元件測試量級通常遠快於 e2e |
| `tsc --noEmit && vite build` | 1–2 分鐘內 | 專案規模中等，未見到會拖慢 build 的大型依賴 |
| Playwright 全套（123 條，iPhone＋Desktop 兩個 project，`fullyParallel: true`） | 3–8 分鐘 | 含瀏覽器安裝（若未快取）、`webServer` 起 dev server 的等待時間 |

若四套各自獨立跑在四個平行 job（GitHub Actions 對公開 repo 完全免費，
平行開 job 不增加金錢成本，只吃 20 個並行 job 上限——見 1.3），**總
wall-clock 時間【推估】約落在最長那個 job 附近（8–15 分鐘量級）**；
若擠在單一 job 裡依序跑，則接近四者相加（20–25 分鐘量級）。這兩個
數字都是推估，不是 benchmark，實際數字要真的跑過 workflow 才知道。

### 1.3 GitHub Actions 在公開 repo 上的額度與時限

【官方文件】GitHub Docs〈About billing for GitHub Actions〉
<https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions>
（存取 2026-09-11）：標準 GitHub-hosted runner 在**公開 repo 上完全
免費且無用量上限**（只有 self-hosted runner 在 2026-03-01 之後才開始
對公開 repo 收取每分鐘 $0.002 的「cloud platform charge」，這與本
research 建議的方案無關，因為建議走標準 hosted runner）。

【官方文件】GitHub Docs〈Limits in GitHub Actions〉
<https://docs.github.com/en/actions/reference/actions-limits>
（存取 2026-09-11）：單一 job 執行時間上限 **6 小時**；單次 workflow
run 總時限 **35 天**（含排隊等待時間）；免費帳號的並行 job 上限
**20 個**（macOS runner 另有獨立的 5 個上限，本專案用不到 macOS）。
這些上限對本專案的四套測試而言完全不構成實務壓力。

### 1.4 Playwright：全套還是只跑 smoke？

【官方文件】Playwright〈Continuous Integration〉
<https://playwright.dev/docs/ci>（存取 2026-09-11）：Playwright 官方
自帶的預設 GitHub Actions workflow 範本本身就是**每次 push／PR 跑
完整測試套件**（`npx playwright test`，觸發條件是
`push`／`pull_request` 到 main/master），這是官方展示的**預設、
推薦作法**，不是「先跑 smoke、其餘延後」。官方文件唯一提到的「先跑
一部分」是 `--only-changed` 這個**輔助性、啟發式**（heuristic）的
預覽功能，用來讓 PR 提早看到可能失敗的測試，但文件明講**事後仍必須
跑過完整套件**（"it's important that you always run the full test
suite after the preliminary test run"）——不是拿它取代完整套件。
官方對規模擴大後的建議是 **sharding**（把測試切開分散到多個 CI
job），而不是永久縮減成只跑 smoke。

**【判斷】對本專案而言**：123 條測試、【推估】3–8 分鐘，遠遠沒有大到
需要 sharding 或縮減成 smoke-only 的規模——**跑完整套件正是 Playwright
自己官方文件展示的標準做法，沒有理由在這個規模下自行縮水**。

---

## 2. CI 紅燈真的能擋住部署嗎？

這題答案分兩半：**Vercel 自己擋不住**、但**GitHub 的合併關卡擋得住**，
兩者是完全不同的機制，必須分開理解。

### 2.1 Vercel 端：push 到 master 一律觸發部署，不等任何外部 CI

【官方文件】Vercel Docs〈Deploying Git Repositories with Vercel〉
<https://vercel.com/docs/git>（存取 2026-09-11，頁面 `last_updated:
2026-08-28`）：「Vercel allows for automatic deployments on every
branch push and merges onto the production branch」——push 到
production branch（本專案是 `master`）**一律**觸發部署，文件全文
沒有任何「等待外部 CI 結果」的機制描述。Vercel 唯一會讓部署**失敗**
的自然機制，是 Vercel 自己的 build command 本身失敗——而本專案的
build command 剛好就是 `tsc --noEmit && vite build`（見 §0），也就是
**前端 typecheck／build 這一項今天就已經是天然的部署關卡**，不需要
額外設定；後端 pytest／前端 Vitest／Playwright e2e 三者則完全不在
Vercel build 的視野內。

### 2.2 Ignored Build Step：能不能拿來等外部 CI？

【官方文件】Vercel KB〈How do I use the "Ignored Build Step" field on
Vercel?〉<https://vercel.com/kb/guide/how-do-i-use-the-ignored-build-step-field-on-vercel>
＋ Vercel Docs〈vercel.json〉的 `ignoreCommand`（存取 2026-09-11）：
這是一段自訂 shell command，**exit code 1＝繼續建置，exit code 0＝
跳過這次建置**。官方設計場景是「這個 monorepo 子目錄沒改動就不用重建」
（範例：`git diff --quiet HEAD^ HEAD ./`），是**同步、基於當下 git
狀態**的判斷，官方文件裡沒有任何「呼叫外部 API 查詢 CI 狀態」的
支援案例。

**【判斷】能不能濫用**：技術上可以寫一段 script 用 GitHub API 查詢
該 commit 在 GitHub Actions 上的 run 狀態、依結果 exit 0/1，但這是
**沒有官方支援、有真實 race condition 的 hack**——Vercel 的 Git
webhook 與 GitHub Actions 的 `push` 事件是**約略同時**觸發的兩條
獨立管線，沒有任何保證 GitHub Actions 的 run 會在 Vercel 評估
`ignoreCommand` 之前就跑完（甚至可能根本還沒開始）。這條路**不建議
採用**——見第 6 節「明確不推薦」。

### 2.3 Deployment Checks／Checks API

【官方文件】Vercel Docs〈Working with Checks〉
<https://vercel.com/docs/checks>（存取 2026-09-11，`last_updated:
2026-08-11`）：Checks 的設計場景是 **Marketplace 第三方整合**（例如
Checkly）——生命週期是「部署建立完成（`deployment.ready`）→
整合商透過 Checks API 註冊檢查 → Vercel 等所有檢查回報結論 →
結論都到齊才真的把網域指過去（alias）」。這**確實是一個會擋住
上線的機制**（"Vercel waits until all the created checks receive an
update"），但官方文件通篇是以「Marketplace 整合商」為主體在描述，
沒有明確展示「自己的 GitHub Actions workflow 直接呼叫 Checks API
回報結果」這條路徑是不是被官方當作一般使用者的標準用法。

**這裡有兩個 UNVERIFIED 的點**：(1) Checks API 是否對話開發者（非
Marketplace 整合商）也開放自行串接，我沒有在 `/docs/checks` 上找到
明確禁止或明確鼓勵的說法；(2) 這項能力的方案門檻——我嘗試 fetch
`/docs/deployment-checks`（即 §2.3 這條規則的姊妹頁）時該頁回
404，`/docs/checks` 本身也沒有出現「僅限 Pro/Enterprise」這類字樣，
但這不足以確認它在 Hobby 方案上可用。**兩點皆標記 UNVERIFIED，
建議若真的想走這條路，先在 Vercel 後台或客服確認一次，而不是假設
可行。**

**【判斷】即使真的可行**：這條路的建置複雜度（要寫程式呼叫 Checks
API、處理 `deployment.created`／`deployment.ready` 兩個 webhook、
自己管理 check 的建立與回報）遠高於下面 2.4 的 GitHub 原生方案，
且效果高度重疊——不建議優先投入。

### 2.4 GitHub branch protection：真正免費、真正能擋的關卡

【官方文件】GitHub Docs〈About protected branches〉
<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
（存取 2026-09-11）：「Required status checks must have a
`successful`, `skipped`, or `neutral` status before collaborators
can make changes to a protected branch.」——勾選 **"Require status
checks to pass before merging"** 之後，PR 合併鈕本身會被鎖住，直到
指定的 status check（也就是我們的 GitHub Actions workflow）回報成功
為止；可另外勾選 **"Require branches to be up to date before
merging"**，強制 PR 分支必須跟 base 同步後才能合併，避免「CI 是對
舊版本跑的、merge 後才發現壞掉」這種空窗。

**方案可用性**：直接讀該頁的官方版本 metadata（frontmatter
`versions: fpt: '*'`）確認這個功能整體適用於 github.com 全部方案
（含 Free）【官方文件，`raw.githubusercontent.com/github/docs`
frontmatter，存取 2026-09-11】；頁面裡唯一明確標出方案差異的地方
是**另一個更窄的功能**（「限制哪些人可以直接 push 到受保護分支」）：
「You can enable branch restrictions in public repositories owned by
a GitHub Free organization」——這條限制只針對「誰可以 push」，不是
「required status checks」本身。交叉比對 WebSearch 得到的獨立結果
也明確指出：「on the Free plan, features like required reviewers,
code owners, branch protection rules, and required status checks
only work on public repositories」（私有 repo 需要 Pro／Team 以上）。

⚠ **誠實揭露一處官方文件本身的表述落差**：GitHub Docs
〈GitHub's plans〉<https://docs.github.com/en/get-started/learning-about-github/githubs-plans>
的方案比較表把「Protected branches」只列在 Pro 以上一欄，字面上
與上述結論衝突。**判斷**：那張表是以「私有 repo」為預設情境在做
方案比較（GitHub 大部分方案比較表的預設視角都是私有 repo，因為公開
repo 本來就幾乎全部功能一致），而 `about-protected-branches` 這個
**功能專屬頁面**本身的版本 metadata 與逐字的公私 repo 差異描述才是
更精確、更該採信的一手來源。由於本 repo `L26041040/option-chaser`
**是公開 repo**，結論是：**required status checks 在這個 repo 上
免費可用**，但這個結論建立在兩個獨立來源交叉印證上，而非單一
無歧義的官方陳述，**保留一絲不確定性、建議 Owner 實際去 repo
Settings → Branches 頁面點開驗證一次**（該頁面本身若不可勾選會
直接告訴你原因）。

### 2.5 兩種「擋」的差異，以及對本專案工作流程的建議

**這是本節最關鍵的一句話，必須講清楚**：Vercel 的部署行為與 GitHub
的合併行為是**兩條互相獨立的管線**——Vercel 永遠不會因為外部 CI
紅燈而拒絕建置一個已經存在於 `master` 上的 commit；GitHub 的
branch protection 管的是**「這個 commit 有沒有資格被合併進
master」**，管不到「已經在 master 上的 commit，Vercel 要不要建置它」
這件事。

**因此，能達成的最強保護方式，是把兩者接起來、而不是硬要 Vercel
本身查詢 CI 狀態**：

1. GitHub branch protection 要求 CI（pytest／Vitest／build／
   Playwright）通過才能合併 PR 進 `master`。
2. 由於 `master` 上出現的每一個新 commit 都必須先通過這關才能存在，
   **等到 Vercel 因為 push 到 master 而觸發部署時，CI 早已在合併的
   那一刻就通過了**——保護生效的時間點是「合併」，不是「部署」，
   但效果一樣：不會有沒過 CI 的程式碼被部署上線。
3. **這個保護對 Owner 個人這個 workflow 的實際適用前提**是：
   Owner（或協助施工的 agent）**改成一律走 PR、不再直接 `git push`
   到 `master`**——CLAUDE.md 自己的紀錄裡就有過需求方直接 commit
   進 master 的先例（例如 2026-08-02 的 `docs/user-feedback-v3.md`）。
   若這個習慣不改，branch protection 再嚴格也擋不住「直接 push」
   這條路——branch protection 有一個獨立的「限制誰能直接 push」選項
   可以連這條路也堵起來，但那是更大幅度的流程改變（連 Owner 自己
   都不能直接 push），**本研究不建議在 Beta 準備階段就走到這一步**，
   先養成「用 PR」的習慣即可達成本題要的保護程度。

**這正是本題要求特別點出的區別：對於「Owner 親自審閱、手動合併 PR」
這種 workflow，可達成的保護（GitHub 擋合併）與不可達成的保護（Vercel
擋部署）分別是什麼，答案已在上面寫清楚。**

---

## 3. 部署後健檢（Post-deploy smoke testing）

### 3.1 `deployment_status` 事件：正確的觸發點

【官方文件】GitHub Docs〈Events that trigger workflows〉
<https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows>
（存取 2026-09-11）：`deployment_status` 事件「Runs your workflow
when a third party provides a deployment status」——當任何第三方
透過 GitHub Deployments API 建立一筆 deployment status 時觸發，帶有
`GITHUB_SHA`／`GITHUB_REF`。

**這條線直接對得上本專案的實際部署方式**：【官方文件】Vercel Docs
〈Git〉同一頁（見 §2.1）明確提到「GitHub deployment activity on a
pull request | The **deployment_status Events** control in your
project's Git settings」——也就是說 **Vercel 的 GitHub 整合本身就會
對它建立的每一次部署（含 preview 與 production）發出 GitHub
`deployment_status` 事件**，這正是官方確認過、現成可用的觸發點，
不需要自己額外接一條 webhook。

**【判斷】寫 workflow 時要注意的兩個實務細節**（非本輪要動手做，
留給未來實作參考）：(1) `deployment_status` 對 preview 與 production
部署都會觸發，workflow 內要判斷
`github.event.deployment_status.state == 'success'` 且部署環境是
production，避免每個 preview 部署都跑一次健檢；(2) 觸發時機是
「Vercel 回報這次部署狀態」的那一刻，不是「使用者實際能連到新版本」
的那一刻——中間若有 CDN 快取層通常已經即時，但保守起見健檢步驟本身
可以加一次重試或短暫等待。

### 3.2 健檢打什麼

【repo 查核】`/api/health` 已存在，回傳 `storage`（`postgres`／
`memory`／`unavailable: ...`）與 `rate`（利率快取狀態），這兩個欄位
剛好就是「資料庫真的接上了嗎」與「排程性快取有沒有在運作」的直接
證據——**這是現成的、零新增程式碼的健檢端點**，workflow 只需要
`curl` 它、檢查 HTTP 200 且 `storage == "postgres"`，不 200 或
`storage` 顯示 `memory`／`unavailable` 就代表部署後環境變數或資料庫
連線出了問題，值得發送通知（見第 4 節通知路徑）。首頁本身
（靜態 `index.html`）也值得順手打一次，確認前端資源真的有部署上去。

### 3.3 Deploy Hooks：容易被誤用的方向

【官方文件】Vercel Docs〈Deploy Hooks〉
<https://vercel.com/docs/deploy-hooks>（存取 2026-09-11）：Deploy
Hook 是一個**觸發新部署**的 POST URL（例如給 headless CMS 或排程
服務用），URL 本身就是憑證、不需要另外認證。Hobby／Pro 帳號每個
專案最多 5 個 hook、每小時最多觸發 60 次。

**【判斷】這與「部署後健檢」是相反方向的功能**——Deploy Hook 是
「叫 Vercel 重新部署一次」，不是「部署完成後通知我」。本題研究
Deploy Hooks 是為了確認這一點：**它不是本題要的工具，正確的工具是
上面 3.1 的 `deployment_status` 事件**。這個澄清本身就是本節的一項
研究產出，避免未來誤用。

### 3.4 UptimeRobot 免費層

【官方文件】UptimeRobot〈Pricing〉<https://uptimerobot.com/pricing/>
（存取 2026-09-11）：Free 方案——**50 個 monitor**、**5 分鐘**檢查
間隔、email／SMS／voice call／Email2SMS 幾種個人通知管道（SMS/voice
的額度要另購）、1 個基本 status page、**3 個月**資料保留、**不需要
信用卡**。

**【判斷】定位**：UptimeRobot 補的是「沒有任何人動任何東西、但服務
本身在某個時間點掛掉」這種情境（例如 Neon 資料庫額度用完、Cboe
永久性封鎖導致核心功能失效），跟 3.1–3.2 的「這次部署有沒有把東西
弄壞」是不同的風險——後者機率更高（因為每次改動都可能引入問題）、
前者機率較低但持續存在。兩者互補，非互斥。

### 3.5 Instant Rollback：出事後的立即止血手段

【官方文件】Vercel Docs〈Performing an Instant Rollback on a
Deployment〉<https://vercel.com/docs/instant-rollback>（存取
2026-09-11）：從專案總覽頁的「Production Deployment」卡片點
**Instant Rollback**，選擇要回退到的部署、確認即完成，過程即時生效
（Vercel 直接把網域指回選定的部署，不是重新建置）。**Hobby 方案只能
回退到「上一個」部署**（不能跳過去選更早的）；Pro／Enterprise 可以
在全部曾經被 alias 過 production 網域的部署中任選。

**⚠ 一個容易忽略的行為**（官方文件明文提醒）：回退之後，Vercel 會
**關閉「production 網域自動指向最新部署」這件事**——之後即使繼續
`push` 到 `master`，新的部署也**不會**自動上線，直到用「Undo
Rollback」或手動 promote 一次為止。這代表：如果 Owner 半夜用 Instant
Rollback 緊急止血，隔天早上若忘記手動 undo，接下來所有正常的修復
push 都會靜靜地不生效——**這點值得寫進未來的 Release Gate 操作
手冊，是一個真實、容易踩到的坑，不是理論風險**。

---

## 4. 錯誤監控與通知組合

### 4.1 Sentry 免費層（Python＋JS/React SDK）

【官方文件】Sentry〈Pricing〉<https://sentry.io/pricing/>（存取
2026-09-11）：免費 **Developer** 方案——**5,000 個 error 事件／月**、
**1 位使用者**、**30 天回溯保留期（30-day lookback）**。同一方案另有
獨立配額（不吃錯誤事件額度）：Session Replay 50 次、Tracing 5M
spans、Logs 5GB、Metrics 5GB——這些是效能／回放類功能，跟單純的
錯誤追蹤是分開計數的，不會被效能監控吃光。

Python 與 JS/React SDK 皆有官方整合，且沒有被鎖進付費方案：
【官方文件】Sentry Docs〈FastAPI〉
<https://docs.sentry.io/platforms/python/integrations/fastapi/>
（存取 2026-09-11）確認是官方 FastAPI 整合頁，`pip install
sentry-sdk`，`sentry_sdk.init(dsn=...)` 即可；`fastapi` 套件存在時
FastAPI／Starlette 整合會自動啟用。頁面本身沒有任何「需要付費方案」
的字樣，符合免費層可用的一般預期。

### 4.2 Vercel Runtime Logs 保留期：Hobby 只有 1 小時

【官方文件】Vercel Docs〈Runtime Logs〉
<https://vercel.com/docs/logs/runtime>（存取 2026-09-11，
`last_updated: 2026-08-28`）：

| 方案 | Runtime Logs 保留期 |
|---|---|
| Hobby | **1 小時** |
| Pro | 1 天 |
| Pro ＋ Observability Plus | 30 天 |
| Enterprise | 3 天 |
| Enterprise ＋ Observability Plus | 30 天 |

**【判斷】這是本節最重要的單一事實**：本專案目前是 Hobby 方案，
Runtime Logs 只留 1 小時、過了就永久查不到、**沒有匯出機制**（同頁
文件描述的是即時查看／篩選／分享單一 log 連結，不是長期歸檔）。對於
一個「陌生人在 Owner 沒有盯著畫面的時候踩到一個 bug」的 Beta 情境，
1 小時保留期幾乎等於「錯過就永遠不知道發生過什麼」。**這正是 Sentry
免費層（30 天保留、5,000 事件／月，對早期 Beta 流量綽綽有餘）不該被
當成「nice to have」的原因**——見第 6 節的分級。

### 4.3 通知路徑：LINE Notify 已死，最簡單的路是 email

【官方文件、關鍵確認】LINE Developers 官方公告：
<https://developers.line.biz/en/news/2025/04/01/line-notify/>（服務
已於 2025-03-31 終止）＋ 2024-10-07 的預告
<https://developers.line.biz/en/news/2024/10/07/line-notify-will-be-discontinued/>
（存取皆為 2026-09-11）：**LINE Notify 確定已經收攤**——2025-04-01
起全部功能不可用，官方帳號與網頁已規劃在 2025-05-12 後刪除。官方
建議的替代方案是 **Messaging API**，但那是一個需要建立並驗證正式
LINE 官方帳號的重量級產品，**不是簡單換一個 token 就能接上的
drop-in 替代品**。**這件事必須明確提醒 Owner：任何舊筆記或直覺
「用 LINE Notify 通知自己」這條路，今天已經不存在了。**

【repo 查核】本 repo 的 CLAUDE.md 與 `docs/deploy-vercel.md` 全文
搜尋不到任何既有的 Slack workspace／webhook／其他訊息整合供這個
產品專案使用——這是一個尚未建立的能力，不是「已經有、只是沒接上」。

**【判斷】最低摩擦的路徑排序**：

1. **Sentry 免費層自帶的 email 通知**——這是摩擦最小的選項，因為
   Sentry 本身就是要接的錯誤聚合服務，它內建的「新 issue 就 email
   給我」功能不需要再另外接任何 glue code 或 webhook。
2. **GitHub 自己原生的 workflow 失敗通知**——這管的是 CI／部署
   pipeline 本身失敗（跟第 4.1 節的「production 執行期真的發生
   的錯誤」是不同的層次），GitHub 帳號通知設定裡本來就有「workflow
   run 失敗時 email 我」的選項，零額外設定成本，直接對應第 1 節的
   CI。
3. **Slack incoming webhook**——技術上完全可行、設定也不複雜，但
   前提是要先有一個 Slack workspace 給這個通知落地；既然目前沒有，
   這一步比前兩項多一道「先建立 workspace」的門檻，**列為選用而非
   必要**，若 Owner 本來就有慣用的 Slack 可以直接用，優先度可以
   提前。

### 4.4 什麼等級的錯誤該主動通知，什麼放著就好

**【判斷】**（非官方文件能回答的題目，屬於工程判斷）——這個 repo
剛好已經有一套相對成熟的內部錯誤分級機制可以借鏡：`api_app/
diagnostics.py` 早就用 `severity`（`info`／`warning`／`error`）＋
`user_facing`（布林）兩個獨立維度區分「這件事有多嚴重」與「這件事
該不該讓一般使用者看到／擔心」（PC-03／PC-04，見 CLAUDE.md 記錄）。
借用同一套精神，本題的建議分級：

- **該主動通知（Sentry 觸發 email／進 error 追蹤）**：任何未被
  程式自己攔截、真正冒出 5xx 或未處理例外的請求；資料庫連線失敗
  （`/api/health` 的 `storage` 不是 `postgres`）；vendor 資料源
  （Cboe **與**備援 yfinance）雙雙失效，導致核心分析功能完全不可用；
  新增的匿名身份／rate limiter 機制本身丟出例外（這正是這輪 Beta
  改動最新、驗證最少的一塊）。
- **放進 log／既有 diagnostics 系統即可、不必主動吵醒人**：這個
  app 本來就已經用 UI 誠實揭露給使用者看的降級狀態（quota 用盡、
  利率曲線陳舊備援、`skipped_direction` 的方向不合候選、單純
  404／400 這類正常的錯誤請求）——這些不是「系統壞掉」，是系統
  按照設計在告訴使用者一個事實，重複送進 Sentry 只會製造雜訊、
  稀釋真正該被注意的訊號。

---

## 5. `/security-review` 該放在哪裡

### 5.1 Pre-PR 還是 Pre-release？

**這題主要是推理，不是查文件能直接得到答案**——`/security-review`
描述本身就講明是「審查目前分支尚未合併的 diff」，這個範圍界定本身
就決定了它天生適合當一個**開 PR 之前、由當事人（Owner 或協助施工的
agent）親手跑一次**的本地檢查：diff 還小、上下文還在腦子裡、改起來
成本最低。

**【判斷】但只做 pre-PR 不夠**——這一整個 Anonymous Public Beta
計畫是拆成一串票（#282 匿名身份、#283 資料保留、#284 濫用防護、
#285 儀表板……）分開施工的，每一張票的 diff 單獨看可能都合理，
但幾張票組合起來、真正要把「陌生人打得到」這個開關打開的那一刻，
才是整個攻擊面第一次真正完整存在的時間點。因此：

- **Pre-PR**：每一張碰到身份／cookie／credential／rate limiter的
  票，開 PR 前各自跑一次 `/security-review`，抓當下 diff 裡看得到
  的問題，成本最低、越早抓到越便宜。
- **Pre-release**：在 Owner 已經規劃好的兩段式上線（controlled
  beta → public beta，見 CLAUDE.md 既有的 Owner 裁示）**每一次要
  擴大暴露面之前**（尤其是真的要打開 public beta 那一刻），再做
  一次針對「這批已經合併的東西合起來看，是不是真的安全」的整體
  檢查——這才是本題舉例的「新增匿名 cookie ＋ rate limiter 真的要
  上線」該對應的檢查點。

**兩者都要，且服務的是不同的問題**——pre-PR 抓局部、pre-release
抓整體，不是其中一個可以取代另一個。

### 5.2 OWASP ASVS：這個階段用哪一個 Level

【官方文件】OWASP ASVS 5.0，`0x03-What-is-the-ASVS.md`
<https://github.com/OWASP/ASVS/blob/master/5.0/en/0x03-What-is-the-ASVS.md>
（raw 內容存取 2026-09-11，經 `raw.githubusercontent.com` 直接讀取；
版本確認：ASVS **5.0.0**，2025-05-30 發布）：

> Level 1：「This level contains the minimum requirements to
> consider when securing an application and represents a critical
> starting point.」——「generally critical or basic, first-layer of
> defense requirements for preventing common attacks」。**5.0 版
> 明確指出 Level 1「not necessarily penetration testable by an
> external tester without internal access to documentation or
> code」**——這是與 ASVS 4.0（當年 Level 1 被描述為「完全可用人力
> 滲透測試涵蓋」）不同的定義，5.0 版刻意把 Level 1 重新設計得更窄、
> 更聚焦在「第一層防線」，理由是 OWASP 自己的工作小組發現 4.0 版
> Level 1 題目太多（約 128 條、佔全部 46%）反而讓團隊卻步、乾脆不做
> 【WebSearch 交叉確認，`softwaremill.com/whats-new-in-asvs-5-0`
> 等二手轉述引自 OWASP 官方 changelog 說明，非一手原文逐字，標記
> 為【二手轉述但與一手文件方向一致】】。5.0 版 Level 1 共 **70 條**
> 要求（4.0 版是 128 條）。

> Level 2：「Most applications should be striving to achieve this
> level of security.」——處理「less common attacks or more
> complicated protections against common attacks」，5.0 版有 183
> 條要求，官方定位是「大多數帶有敏感資料的應用程式該追求的層級」。

ASVS 各 Level 彼此是**累加**關係：Level 2 涵蓋 Level 1 全部要求，
Level 3（92 條，5.0 版大幅擴充）在此之上再加最高信任等級要求
【WebSearch 交叉確認的通用描述，與 OWASP 4.0／5.0 一手文件一貫的
「累加式」設計原則一致】。

**【判斷】本專案該用哪個 Level**：**ASVS Level 1 作為 Beta 上線前
的底線（blocking）**——理由是 5.0 版本身就是刻意重新設計成「一個
真正可達成的最低起點」，而不是形式上的門面；本專案目前也還沒有
金流、也沒有高價值交易，套用 Level 2／3 的完整清單不成比例。**但有
一個例外要單獨挑出來**：本專案的 `owner_credentials`（見 CLAUDE.md
SCALE-13 記錄）已經在存**使用者自己提供的第三方 API 憑證**（例如
Market Data App 的 token）——這正是 ASVS 對 Level 2 描述裡點名的
「處理敏感資產」情境。**因此建議：Level 1 整體作為 blocking 底線，
再額外挑出 ASVS 憑證儲存／處理相關的幾條 Level 2 控制項一併納入
blocking 範圍**（不是整個 Level 2 清單，只挑跟憑證儲存直接相關的
那幾條）——這個判斷理由是「這項風險已經存在於今天的產品裡，不是
因為 Beta 才新增的」，跟 Beta 開放本身沒有必然關聯，不該因為
「還在 Beta」而順便被降級忽略。

### 5.3 Vercel 與 Neon 官方安全指引

【官方文件】Vercel Docs〈Security overview〉
<https://vercel.com/docs/security>（存取 2026-09-11）：平台**預設
內建、對所有方案（含 Hobby）免費**的保護包含——全站 HTTPS
與自動 SSL 憑證；「An enterprise-grade platform-wide firewall
available for free for all customers with no configuration
required that includes automatic DDoS mitigation」；Web Application
Firewall（WAF，可自訂規則，但自訂規則數量 Hobby 上限較低於
Pro）；存取控制（Deployment Protection）用於限制誰能看到
preview／production 網址。

【官方文件】Neon Docs〈Security overview〉
<https://neon.com/docs/security/security-overview>（存取
2026-09-11）：連線一律要求 TLS，官方建議使用 `verify-full` 模式
（PostgreSQL 最嚴格的 SSL 模式）防中間人攻擊；**全部 Postgres
角色的密碼都被要求至少 60-bit 熵**（透過 Console／API／CLI 建立的
密碼自動符合，透過 SQL 手動建立的角色則在建立時被驗證）；Neon
Proxy 在連線真正到達 Postgres 之前先做身份驗證，降低暴力破解／
連線濫用的風險。**IP allowlist 這項功能只在付費的 Scale 方案上
提供**，Hobby／Neon Free 用不到——這代表本專案目前無法用「只准
特定 IP 連資料庫」這條路作為額外防線，安全性主要靠上面兩項（TLS
＋高熵密碼＋Neon Proxy 驗證）與應用層自己的 owner 隔離機制
（CLAUDE.md 記錄的 Ownership A-1）。

**【判斷】這一節最重要的推論**：Vercel 與 Neon 兩個平台本身已經
把「傳輸層加密」「DDoS 防護」「連線層驗證」這些網路層／平台層的
基本功都做成**平台預設、免費、零設定**的東西——這代表本專案真正
缺的、真正該花力氣補的，幾乎全部集中在**應用層**（匿名身份怎麼
發放與驗證、rate limiter 怎麼設計、憑證怎麼存、多久清一次舊資料）
——這剛好精確對應到地圖 #272 底下 #282–#287 那幾張還在等 Owner
裁示的票，不是巧合，是這幾個平台的責任分工本來就長這樣。

---

## 6. 分級：Beta 前必須有 vs Beta 後再說

**原則**：只有在「不做這件事，陌生人可能因此受害、或 Owner 完全沒有
辦法事後知道發生過什麼」這兩種情況下才列為 blocking；其餘一律歸
later，不因為「反正很便宜」就順手升格。另外，Owner 已經自己定案
「controlled beta（合成流量／bot 壓測）→ public beta（真人）」兩段式
上線（見 CLAUDE.md 記錄），本分級沿用這個兩階段結構。

| 項目 | 定性 | 理由 |
|---|---|---|
| CI 跑四套既有測試（push／PR 觸發） | **Public Beta 前 blocking**；Controlled Beta 前建議但非必要 | Controlled beta 階段流量是合成的、Owner 本來就在盯著；一旦進入 public beta，程式碼變更頻率與影響的人都會提高，人工手動跑測試的紀律不該是唯一防線 |
| GitHub branch protection 要求 CI 通過才能合併 | **Public Beta 前 blocking**（且是 CI 本身要真正發揮擋人效果的必要條件） | 沒有這一步，「CI 跑過」只是紀錄用，擋不住任何東西——見第 2 節 |
| Vercel build（`tsc --noEmit && vite build`）失敗即不部署 | 已經是現況，無需額外動作 | 平台既有行為，零成本 |
| `deployment_status` 觸發的 `/api/health` 健檢 | **Public Beta 前 blocking** | 成本極低（端點已存在），直接對應「部署後陌生人看到壞掉的網站卻沒人知道」這個具體風險 |
| UptimeRobot 外部監控 | **Later（nice to have）** | 補的是「沒人動任何東西但服務自己掛了」，機率低於「這次部署把東西弄壞」，且已經有 3.2 的健檢步驟覆蓋主要情境 |
| Instant Rollback 操作方式（Owner 要知道怎麼用、知道回退後的自動指派會被關掉） | **Public Beta 前 blocking**（純知識成本，零工程成本） | 出事當下的止血手段，且有一個容易忽略的坑（見 3.5），提前知道就不會踩 |
| Sentry 免費層（Python＋React SDK） | **Public Beta 前 blocking** | Hobby 的 Runtime Logs 只留 1 小時，陌生人踩到的 bug 若沒有 Sentry，事後幾乎無法追溯 |
| Email 作為通知路徑（Sentry 內建 ＋ GitHub 原生 workflow 失敗通知） | **Public Beta 前 blocking**（零額外建置成本） | 兩者都是已經在手邊的平台功能，不需要新建任何東西 |
| Slack incoming webhook | **Later（選用）** | 需要先有 workspace，目前沒有；email 已經覆蓋核心需求 |
| LINE Notify | **明確排除，非分級項目** | 官方已於 2025-03-31 終止服務，不存在「要不要用」的問題 |
| `/security-review` pre-PR（碰身份／cookie／credential／rate limiter 的每張票） | **貫穿整個施工過程 blocking** | 內建功能、零額外成本，每次改動當下抓最便宜 |
| `/security-review`＋ASVS Level 1 為主的整體 pre-release 檢查（每次擴大暴露面前各做一次） | **Controlled Beta 前與 Public Beta 前皆 blocking**（各做一次） | 對應本題舉例的「這批東西真的要上線」那個時間點 |
| 完整 ASVS Level 2／Level 3 清單 | **Later，且【判斷】可能永遠不需要** | 與本專案目前的風險（無金流、無高價值交易）不成比例 |
| ASVS 憑證儲存相關的少數 Level 2 控制項（因 `owner_credentials` 已存在） | **Public Beta 前 blocking** | 這項風險今天就存在，與 Beta 與否無關，不該被「還在 Beta」順勢降級 |
| Vercel／Neon 平台預設安全機制（TLS、DDoS 防護、高熵密碼、Neon Proxy 驗證） | 已經是現況，無需額外動作 | 平台預設，零成本、零設定 |
| Vercel「Ignored Build Step」查詢外部 CI 狀態的 hack | **明確不推薦** | 無官方支援、有真實 race condition，見 §2.2／第 7 節 |
| Neon IP allowlist | **不適用**（此方案不提供） | Hobby／Neon Free 沒有這項功能，需要才升級到 Scale 方案，非本階段考量 |

---

## 最推薦 / 次佳 / 明確不推薦

### 最推薦方案

1. 建一個 GitHub Actions workflow（`push`／`pull_request` 觸發），
   四個 job 平行跑：pytest 雙後端（Postgres service container，見
   §1.1）、Vitest、`tsc --noEmit && vite build`、Playwright 全套
   （不縮成 smoke-only，見 §1.4）。全部免費（公開 repo），
   【推估】總 wall-clock 8–15 分鐘量級。
2. 到 GitHub repo Settings → Branches 開一條 `master` 的 branch
   protection rule，勾選「Require status checks to pass before
   merging」指向上面四個 job；Owner 從此改用「開 PR → 等 CI 綠燈
   → 自己按合併」的流程，不再直接 `git push` 到 `master`——這樣
   Vercel 部署時吃到的 commit 永遠是已經過 CI 的。
3. 新增一個由 `deployment_status` 事件觸發的小 workflow，對
   production 部署 `curl` 既有的 `/api/health`，非 200 或
   `storage != "postgres"` 就發送通知（見下）。
4. 接上 Sentry 免費 Developer 方案（後端 FastAPI＋前端 React 各自的
   官方 SDK），用它內建的 email 通知作為「有人真的踩到未處理錯誤」
   的第一線警報；CI／部署失敗則交給 GitHub 原生的 workflow 失敗
   email 通知，兩者互不重疊、都零額外建置成本。
5. Owner 記住 Instant Rollback 在哪裡點、記住回退後要記得手動
   undo（否則之後的正常 push 會靜靜失效）。
6. `/security-review` 在每一張碰身份／cookie／credential／rate
   limiter 的票開 PR 前跑一次；另外在 controlled beta 開始前、
   public beta 開始前，各對「當時已合併的全部相關改動」整體跑一次
   ASVS Level 1（＋憑證儲存相關的幾條 Level 2 控制項）為骨架的
   pre-release 檢查。

### 次佳方案（若想再省一點設定時間）

- Controlled beta 階段（Owner 本來就在盯合成流量）可以先不接
  Sentry，只靠人工習慣「每次部署完手動看一次 `/api/health` 與
  Vercel Logs 頁」撐過去——但**進入 public beta 前一定要補上
  Sentry**，屆時 1 小時的 Runtime Logs 保留期就不再夠用。
- 若四個 CI job 平行跑造成的等待感覺太久，可以先只跑
  pytest＋Vitest＋build 三個較快的 job 在每次 push 上，把
  Playwright 全套移到排程（例如每天一次）或只在 PR 上跑——但依
  【推估】的耗時量級，這個專案的規模【判斷】應該還不需要走到這一步。

### 明確不推薦

- **用 Vercel 的「Ignored Build Step」自己寫 script 去查詢 GitHub
  Actions 狀態，藉此讓 Vercel 等 CI**：沒有官方支援、有真實 race
  condition（兩條 webhook 管線各自獨立觸發，沒有順序保證），而且
  branch protection 已經能達成幾乎一樣的效果、更簡單也更官方。
- **繼續假設 LINE Notify 還能用**：已於 2025-03-31 正式終止，這條路
  今天不存在。
- **只跑 CI、卻不設 branch protection、也不改掉直接 push master 的
  習慣**：CI 綠燈變成純粹的事後紀錄，跟今天手動跑測試貼在回報裡
  的效果幾乎一樣，沒有真正達成「擋住壞東西上線」的目的。
- **在這個階段就套用完整 OWASP ASVS Level 2 或 Level 3 清單**：
  對一個沒有金流、沒有高價值交易、單人維護的 Beta 階段產品而言，
  成本與實際風險不成比例；會拖慢真正該優先做的身份／濫用防護
  工作。
- **為了收錯誤通知而新建一個 Slack workspace**：Sentry 免費層自帶
  的 email 通知已經零成本覆蓋同樣的需求，沒有必要新增一塊此刻
  用不到的基礎設施。
