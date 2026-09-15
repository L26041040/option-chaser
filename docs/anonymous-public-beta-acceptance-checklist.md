# Anonymous Public Beta（spec #291）驗收清單——給 Owner 真機走一遍

依專案規則，視覺驗收（好不好看、版面順不順眼）不做截圖比對，由 Owner
自己在畫面上判斷；這份清單只負責告訴你「每一條該去哪裡看、看什麼」，
以及哪些是自動化測試已經守住、哪些必須你親自確認。

**圖例**：✅ 已完成，自動化測試覆蓋（後端 pytest／前端 Vitest／
Playwright e2e）｜ ⚠ 已完成但**必須**你親自用真機／真實瀏覽器確認（自
動化測試結構上做不到的那部分，例如「兩個真的不同瀏覽器」「真的清掉
cookie」這種跨行程的狀態）。

---

## 匿名身份與資料隔離

**1. 兩個不同瀏覽器（或一個瀏覽器＋一個無痕視窗）各自建立劇本，互相
看不到對方** ⚠
自動化只能模擬「兩個不同的 cookie」（`test_pb02_cookie_identity.py::
test_two_different_browsers_see_completely_isolated_data`、PB-07
harness 的多 synthetic owner 隔離測試），無法自動化「真的開兩個不同
瀏覽器」這件事本身——這條需要你親自拿 Chrome＋Firefox（或 Chrome
一般視窗＋無痕視窗）各自建一個劇本，確認 A 看不到 B 的清單。

**2. 清除瀏覽器 cookie（或換一個瀏覽器）後重新打開網站，看到的是空
的劇本庫，不是舊資料，也不會報錯** ⚠
自動化覆蓋「沒帶 cookie 的請求會拿到全新身份」（`test_pb02_cookie_
identity.py::test_a_request_carrying_an_unknown_token_gets_a_brand_
new_owner`），但「你自己的瀏覽器清 cookie 前後」這個真實操作需要你
親自做一次。

**3. 打開 `GET /api/health`、造訪首頁前不帶任何 cookie，不會意外
產生一堆用不到的匿名身份** ✅
自動化：`test_pb02_cookie_identity.py::test_health_does_not_create_
an_owner`／`test_repeated_health_probes_never_accumulate_owners`。

---

## 首頁 Beta 說明與全站頁尾

**4. 首頁一進來就看得到一段常駐的 Beta 說明（不是彈出視窗、沒有
「關閉」按鈕），內容包含：這是 Beta、資料存在這個瀏覽器的 cookie、
清掉／換瀏覽器會找不回來、閒置一段時間後會被清除、不是投資建議** ✅
自動化：`BetaNotice.test.tsx`、`betaCopy.test.tsx`（禁詞掃描）、
`e2e/smoke.spec.ts`／`desktop.spec.ts`「首頁 Beta 說明常駐可見」。

**5. 不管在劇本庫、詳細頁、垃圾桶、設定頁的哪一個畫面，捲到最下面
都看得到同一行頁尾：「非投資建議」＋隱私頁連結＋回報問題連結** ✅
自動化：`Footer.test.tsx`、`App.test.tsx` 新增五條分別驗證五個畫面。

**6. 點頁尾「隱私與資料政策」連結，打得開一個獨立頁面，列出六件事：
存了什麼、留多久、怎麼刪、清 cookie 的後果、不是投資建議、Beta
狀態** ✅
自動化：`PrivacyPage.test.tsx`、e2e 完整首次進站流程。

**7. 隱私頁「怎麼刪」那一段點得進去，真的到達設定頁的「刪除我的全部
資料」按鈕（不是死連結）** ✅
自動化：e2e 驗證連結 `href` 與點擊後真的到達 `#/settings`。

**8. 點頁尾「回報問題」連結，會在新分頁打開 GitHub issues 頁面** ✅
自動化：`Footer.test.tsx` 驗證 `target="_blank"`＋正確網址。

---

## 自助刪除

**9. 在設定頁按「刪除我的全部資料」，會先跳出二次確認，取消不會刪除
任何東西** ✅
自動化：`DeleteMyData.test.tsx`。

**10. 確認刪除後，頁面重新整理，劇本庫變成全新的空狀態（不是報錯、
不是卡住）** ✅
自動化：`DeleteMyData.test.tsx`、e2e「PB-04」相關測試。

---

## Super User（Owner 自己的後台）

**11. 在設定頁輸入正確的 Super User 密鑰後，一次就能看到全部後台
功能（credential 測試按鈕、Super User 管理面板），不需要為不同功能
分別再輸入一次密鑰** ✅
自動化：`test_pb09_superuser.py::test_the_same_admin_secret_unlocks_
every_protected_endpoint`、`SuperUserUnlock` 相關測試。

**12. 用同一個瀏覽器（帶著自己的 owner cookie），先用一般身份操作
（建立劇本），再輸入 Super User 密鑰查看後台，不會把自己的劇本身份
搞混或消失** ✅
自動化：`test_pb09_superuser.py::test_admin_secret_presence_does_
not_change_which_owner_a_cookie_resolves_to`、新增
`test_superuser_credentials_can_still_do_every_normal_user_thing`。

**13. Super User 面板能看到全站有幾個匿名使用者、各自的劇本數，並
且能點進某一個使用者看到他實際的劇本內容** ✅
自動化：`test_pb10_superuser_admin.py::test_superuser_can_list_
every_owner_across_the_site`／`test_superuser_can_view_another_
owners_scenario_list_and_detail`。

**14. 在 Super User 面板刪除某個使用者的資料，會先要求輸入正確的
確認文字，打錯或留白都不會真的刪除** ✅
自動化：`test_pb10_superuser_admin.py` 三條確認相關測試。

**15. 每一次高風險操作（刪除他人資料、標記 protected）事後都在
audit log 裡留下紀錄，看得出誰、做了什麼、對誰、什麼時候** ✅
自動化：`test_pb10_superuser_admin.py::test_audit_log_records_who_
what_target_and_when_for_high_risk_actions`。

---

## Quota 與節流

**16. 同一個匿名身份建到第 11 個劇本會被擋下，錯誤訊息看得懂（不是
一串技術術語），封存一個舊劇本後又能建立新的** ✅
自動化：`test_pb05_quota_and_throttle.py`。

**17. 30 分鐘內對同一個劇本重複按「刷新」，不會真的重新去抓一次
報價（可以觀察：資料時間戳不會變）** ✅
自動化：`test_pb05_quota_and_throttle.py` 節流窗測試。

**18. 全站當日 vendor 呼叫量觸頂時，刷新會顯示「額度已用盡，稍後
再試」這類清楚訊息，而不是白屏或伺服器錯誤** ✅
自動化：`test_pb06_global_vendor_fuse.py`。

---

## 資料生命週期

**19. Owner 自己的劇本不會被匿名清理排程動到（即使刻意讓它看起來
很久沒有活動）** ✅
自動化：`test_pb08_anonymous_lifecycle.py::test_protected_owner_
survives_even_when_long_overdue`；PB-03 遷移腳本已把 Owner 的
`solo` 資料標記為 protected（`scripts/migrate_solo_to_owner.py`）。

**20. 清理排程（Vercel Cron）每天至少跑一次，這件事本身可以在
Vercel 後台的 Cron 執行紀錄裡看到** ⚠
需要 Owner 在 Vercel Dashboard 的 Cron Jobs 頁面自行確認排程有沒有
真的照表操課——這是平台自己的執行紀錄，agent 本地測試看不到。

---

## 觀測與告警

**21. 設定過免費 SMTP 帳號後，每天會收到一封營運摘要信（活躍匿名
使用者數、清理了幾個、有沒有觸發任何告警）** ⚠
需要 Owner 依 `docs/pb11-owner-setup-checklist.md` 設定 SMTP 環境
變數後，親自等一天收信確認；自動化只能驗證信件內容組裝邏輯與
「未設定就不寄」的行為（`test_pb11_ops_digest.py`）。

**22. 設定過 Sentry 後，前端或後端真的出錯時，Owner 的信箱會收到
通知** ⚠
需要 Owner 依 `docs/pb13-owner-setup-checklist.md` 設定 Sentry
DSN＋Alert Rules 後，親自觸發一次錯誤（或等真實錯誤發生）確認。

---

## CI／部署

**23. 開一個 PR 到 master，會自動跑後端／前端測試，紅燈會擋住
「合併」按鈕** ⚠
需要 Owner 在 GitHub repo 設定裡把 `.github/workflows/ci.yml` 的
三個 job 設成 branch protection 的 required status checks（admin
權限操作，agent 做不到，見 `docs/pb13-owner-setup-checklist.md`）；
設定後開一個測試 PR 確認紅燈真的擋得住。

**24. 部署完成後，`/api/health` 會被自動打一次確認網站活著；設定
UptimeRobot 後，網站掛掉會收到通知** ⚠
需要 Owner 依 `docs/pb13-owner-setup-checklist.md` 設定 UptimeRobot
免費帳號監控 production 網址。

---

## 空狀態與文案

**25. 全新的匿名身份第一次進站，劇本庫顯示的是「還沒有劇本，用……
建立」這種引導文字，不會自動生出一個示範劇本** ✅
自動化：`App.test.tsx::空清單顯示引導文字，不自動建立示範劇本`。

**26. 全站找不到任何「推薦」「建議您」這類投資建議暗示的字眼；提到
「不構成投資建議」的地方措辭一致** ✅
自動化：`betaCopy.test.tsx`、既有 `tests/test_redlines.py`。

---

## 尚未涵蓋、留給下一階段（Line 2 之後，本輪明確不做）

- 帳號系統／找回碼／跨裝置同步
- 廣告／完整 Analytics
- IP 層限流／WAF／bot challenge／裝置指紋
- 付費市場資料源升級
- Cross-Scenario／Holdings／Portfolio

以上皆為 spec #291 §2／§21 明文的 Non-goals，不在本輪驗收範圍內。
