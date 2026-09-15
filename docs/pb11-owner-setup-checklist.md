# PB-11（#303）Owner 手動設定清單

施工端（agent）已把 ops metrics 擴充、四條 alert 判準、daily digest
的組信與寄信邏輯全部做到「不需要任何帳號權限就能驗證」的程度——
`GET /api/cron/daily-digest` 在完全沒有 SMTP 設定時仍會正常回應
（`sent: false`），全套自動化測試不依賴任何真實信箱。

以下這件事需要一個真實的免費 SMTP 帳號，只能由 Owner 親自申請、
設定——這是 PB-11 票面 §7 明文要求的免費層寄信機制，不是遺漏。

## 設定每日摘要信真正寄出

1. 準備一個能開 SMTP 的免費信箱。最簡單的選項是既有 Gmail 帳號＋
   [App Password](https://myaccount.google.com/apppasswords)（不是
   帳號本身的密碼——Google 帳號需先開啟兩步驟驗證才能產生 App
   Password）；任何其他提供免費 SMTP relay 的信箱皆可，程式碼
   （`api_app/digest.py`）沒有寫死特定 vendor。
2. 在 Vercel 專案設定裡新增以下環境變數（Production 環境即可，
   Preview 視需要另外決定）：
   - `DIGEST_SMTP_HOST`（例如 Gmail 是 `smtp.gmail.com`）
   - `DIGEST_SMTP_PORT`（Gmail 是 `587`，STARTTLS）
   - `DIGEST_SMTP_USER`（登入帳號，例如完整 Gmail 地址）
   - `DIGEST_SMTP_PASSWORD`（App Password，**不是**帳號密碼本身）
   - `DIGEST_EMAIL_FROM`（寄件顯示地址，通常與 `DIGEST_SMTP_USER`
     相同）
   - `DIGEST_EMAIL_TO`（Owner 想收信的地址，可以跟上面同一個信箱）
3. **六項缺一即整段 no-op**——`GET /api/cron/daily-digest` 仍然會
   200、算完整份聚合快照，只是 `sent` 欄位會誠實回 `false`，不會讓
   Vercel Cron 因此報錯或整條刷新流程掛掉。設定完成後下一次
   `0 13 * * *`（UTC）觸發時就會真的收到信；也可以在 Vercel 後台
   手動觸發一次 cron 立即驗證。
4. **全程免費**——一般個人信箱的免費 SMTP relay 額度（Gmail 個人
   帳號每日數百封）遠超這個每日一封摘要信的用量，不涉及任何付費
   方案（FREE-FIRST，spec §13）。

## 三個 alert 判準的數值門檻（選用，有保守預設值）

不設定以下環境變數時，`api_app/ops_alerts.py` 用內建的保守預設值
（詳見該模組檔頭）；需要調整時可在 Vercel 專案設定裡新增：

- `STORAGE_ALERT_CAP_BYTES`（預設約 512 MiB，對齊 Neon Free 官方
  記載的儲存上限）
- `CLEANUP_MISSED_DAYS_THRESHOLD`（預設 2 天）
- `CHAIN_ERROR_RATE_THRESHOLD`（預設 0.10，即 10%）

第四條判準（429 持續性事故）沿用既有 `chain_backoff.
INCIDENT_THRESHOLD_FAILURES`（3 次），不在這裡另外設定。
