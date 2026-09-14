# PB-13（#293）Owner 手動設定清單

施工端（agent）已把「CI 真的擋得住 merge」與「錯誤／存活監控」的
程式面做到最完整、agent 可獨立完成的程度。以下五件事需要 repo
admin／第三方帳號權限，只能由 Owner 親自操作——這是 PB-13 票面 §4
明文列出的 HITL 步驟，不是遺漏。

## 1. GitHub Branch Protection（required status checks）

1. 打開 repo → Settings → Branches → Add branch protection rule。
2. Branch name pattern 填 `master`。
3. 勾選「Require status checks to pass before merging」，把 CI
   workflow 的三個 job（`Backend (memory + Postgres)`／
   `Frontend (typecheck / vitest / build)`／`Playwright smoke
   subset`）加進必要清單（第一次要先讓 workflow 在任一個 PR 上跑過
   一次，GitHub 才找得到這些 job 名稱可勾）。
4. 建議一併勾選「Require a pull request before merging」——這樣
   `git push` 直接推 `master` 會被擋下，逼所有變更都走
   branch → PR → CI → merge。
5. 公開 repo 的 branch protection 是免費功能，不涉及付費方案。

## 2. Sentry（免費層，5,000 events/月）

1. [sentry.io](https://sentry.io) 註冊免費帳號（不要選付費 plan）。
2. 建立一個 Python（FastAPI）專案，拿到它的 DSN。
3. 在 Vercel 專案設定裡新增環境變數 `SENTRY_DSN`＝那個 DSN
   （Production／Preview 皆可勾）。
4. 建立第二個 JavaScript（Browser／React）專案，拿到另一個 DSN。
5. 在 Vercel 專案設定裡新增環境變數 `VITE_SENTRY_DSN`＝那個 DSN
   （**注意 `VITE_` 前綴**——Vite 只會把這個前綴的環境變數打進前端
   bundle）。
6. 兩邊 Alert Rules 都設成「有新 issue 時寄 email」，收件人填 Owner
   自己的信箱。
7. **不用設定** `traces_sample_rate`／performance／replay 相關付費
   功能——程式碼已經把它們關掉（`traces_sample_rate=0`／
   `tracesSampleRate: 0`），維持免費層額度。

未設定這兩個環境變數時，後端與前端的 Sentry 初始化都是 no-op——不會
因為忘記設定而讓 production 掛掉或行為改變。

## 3. UptimeRobot（或 Better Stack，免費層）

1. 免費註冊 [uptimerobot.com](https://uptimerobot.com)。
2. 新增一個 HTTP(s) Monitor，URL 填正式站
   `https://option-chaser.vercel.app/api/health`，檢查間隔用免費層
   允許的最短間隔（通常 5 分鐘）。
3. Alert Contact 設成 Owner email。

## 4. 確認 Vercel × GitHub 的 deployment 事件正常送達

`.github/workflows/deploy-smoke.yml` 依賴 Vercel 官方 GitHub 整合在
每次部署完成後發出的 `deployment_status` webhook——這是 Vercel × GitHub
整合本身就有的行為，不需要另外設定 webhook secret。第一次部署後
到 repo 的 Actions 分頁確認有看到「Deploy smoke」這個 workflow 跑起來
（`deployment_status` 事件觸發），若沒看到，檢查 Vercel 專案設定裡
GitHub 整合是否啟用。

## 5.（可選）第一次真實 PR 驗收 CI 真的擋得住紅燈

PB-13 的 AC 要求「至少一次真實 PR 走完 branch→PR→CI→merge 全流程」
——這需要 Owner 親自開一次 PR 操作（`.claude` 專案規則與這條票 AC
在「agent 可否主動開 PR」上互相衝突；本次施工遵守專案既有的「全部
ticket 做完才開 PR、不主動開」規則，不代 Owner 開這個 PR）。等
14 張票全部做完，Owner 決定要開 PR 時，這一步就會自然發生並驗證到
這條 AC。
