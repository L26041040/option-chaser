# 匿名使用者資料生命週期——業界成熟做法研究

研究日期：2026-09-11／issue #276／分支 `claude/implement-tfm9oa`。**本文只整理
「別人怎麼做、代價是什麼」，不替 Owner 選任何具體天數、不修改任何 production
code、不動 #269。** 供後續一張獨立的 grilling 票（第 8 節）使用。

## 給 Owner 的白話摘要

這篇要回答的不是「匿名使用者資料要留幾天」，是「業界通常怎麼想這件事、
用什麼訊號判斷『這個人不會回來了』、怎麼分段刪、哪些東西該跟著這個人
一起刪、哪些不該，以及技術上怎麼刪才不會把資料庫弄慢」。三個最值得先
知道的結論：

1. **「30 天」其實是業界最常出現的數字，不是憑空拍腦袋**——Firebase 匿名
   帳號自動清除、Supabase 官方建議的手動清除查詢、StackBlitz 帳號關閉後
   刪除個資的政策上限，三個互不相關的產品都停在 30 天。但這不代表 30 天
   就是「正解」——真實區間從幾小時（Neon 免費版的還原視窗）到 14 個月
   （Google Analytics 4 使用者資料保留上限）都有正當理由，取決於你要拿
   那份資料做什麼。
2. **幾乎所有「先觀察、後刪除」的設計都是三段式**（先標記凍結／過期
   →留一段可以回來救的緩衝期→真的刪掉），而且**「回訪要不要讓時鐘
   重新開始算」這件事本身就是一個會左右整套設計的關鍵開關**——選錯
   （尤其選成「任何活動都續命」）的後果是資料永遠不會被清掉，等於沒做。
   另一個容易被忽略的事實：**這段「先留著給你救」的緩衝期不是免費的**
   ——Google Cloud、Neon 這類廠商的官方文件都明講，緩衝期內的資料照樣
   全額計費，你是在花錢買一個「使用者可能回來」的保險，不是省錢。
3. **Option Chaser 現在沒有「刪掉一個匿名使用者及其全部資料」這個操作**
   ——不是缺一個小角，是從資料庫層級就沒有任何 owner 範圍的刪除路徑（除
   了逐一劇本的 `delete_scenario()`，且它本身還漏了一張表）。這件事在
   「全世界只有一個人用」時完全不痛，在 Public Beta 對任何路過的匿名
   訪客開放的那一天起，才是真的風險——尤其是資料庫裡永遠留著一個可能
   仍然有效的第三方 API token 這種情況，那已經不只是「省 storage」的
   問題，是安全問題。

以下逐題整理成「常見區間」與選項，每個結論標示屬於【業界慣例】、
【法規／安全必要】，還是純粹是【Option Chaser 產品選擇】——後者代表
沒有標準答案，是 Owner 自己要決定的事。

---

## 目錄

1. 多久沒活動算 abandoned：業界的常見區間
2. 分段刪的設計：soft-expire → grace period → hard delete
3. 哪些資料該跟著 owner 一起刪、哪些不該（含 GDPR）
4. 技術上怎麼刪才不會把 DB 弄慢
5. 排程在哪裡跑
6. 附帶一提：controlled beta 的 synthetic／load-test 資料
7. 這對 Option Chaser 意味著什麼
8. 資料生命週期 grilling 票應該問 Owner 的選項（OD-R1～OD-R7）
9. 附錄：查證方式與 UNVERIFIED 項目

---

## 1. 多久沒活動算 abandoned：業界的常見區間

先講清楚一個容易混淆的地方：下面這些例子，「觸發條件」並不都是同一種
「abandoned」——有些是**帳號從建立那天就沒人管**（Firebase／Supabase），
有些是**使用者主動關閉帳號後的資料下架期**（StackBlitz，跟「棄置」是
兩件不同的事，這裡列出是因為它同樣示範了「刪除前留一段緩衝期」），有些
是**環境／產物本身閒置沒被存取**（CodeSandbox、GitHub Codespaces、CI
artifact、Vercel deployment）。整理時已經分開標註。

| 平台／服務 | 觸發訊號 | 常見視窗 | 可否調整 | 類別 |
|---|---|---|---|---|
| Firebase Auth（Identity Platform）匿名帳號 | 帳號**建立**日起算（非最後使用） | 30 天後才「有資格」被刪，非保證立即刪 | 功能整體開關（enable／disable），視窗本身不可調 | 【業界慣例】 |
| Supabase 匿名使用者 | 帳號**建立**日起算 | 官方建議的手動 SQL 用 30 天 | 官方**沒有**自動化機制，天數是文件裡的建議值、可自訂 | 【業界慣例】 |
| StackBlitz 帳號關閉後 | 使用者**主動關閉帳號**（不是偵測棄置） | 「commercially reasonable period... not to exceed thirty days」＝上限 30 天，非固定值 | 政策承諾的是上限，實際可能更短 | 【法規／安全必要】（隱私政策承諾） |
| CodeSandbox 記憶體快照 | Sandbox 停止後未被恢復／fork | 預設約 7 天（依方案與磁碟壓力可延長） | 依付費方案 | 【業界慣例】（見附錄，此條僅經搜尋摘要確認） |
| CodeSandbox 磁碟快照 | 超過約 2 週未啟動 | 約 2 週後把檔案提交進 `/persisted`（Git 追蹤的封存），磁碟本身才被刪 | 依付費方案 | 同上 |
| CodeSandbox 封存（`/persisted`） | — | 官方文件稱「過去 4 年從未刪除過封存」，未承諾永久 | 不可調（目前無刪除機制） | 同上 |
| GitHub Codespaces | 停止後閒置 | 預設 **30 天**，可調 0～30 天（0＝停止即刪） | 使用者自己可調，且**每次連線會重置倒數** | 【業界慣例】 |
| GitHub Actions artifacts／logs | 上傳後起算（非「棄置」，是單純保留期） | 預設 **90 天** | Public repo 可調 1～90 天；Private/Internal 可調 1～400 天 | 【業界慣例】 |
| Vercel Deployment（Hobby） | 部署完成後起算 | 一律 30 天 | 專案層級可設定 | 【業界慣例】 |
| Vercel Deployment（Pro／Enterprise） | 同上，依部署狀態分四類 | Canceled 30 天／Errored 90 天／Pre-Production 180 天／Production **1 年** | 團隊或專案層級可覆寫 | 【業界慣例】 |
| Google Analytics 4 | 使用者層資料，依「重設」開關決定是固定還是滑動 | **2 個月**或 **14 個月**（事件層資料另有 GA360 付費版 26／38／50 個月選項） | 使用者自選，且有「每次新事件重設倒數」開關 | 【業界慣例】 |
| Google Cloud Storage soft delete | 物件被刪除的那一刻起算 | 預設 **7 天**，可調 **7～90 天**，可設 0 停用 | 逐 bucket 可調 | 【業界慣例】 |
| Stripe 測試模式（test mode）訂閱 | 訂閱**建立**日起算 | 90 天後自動取消，再 30 天後**真正刪除**（可標記豁免） | 個別物件可標記排除 | 【業界慣例】 |

**小結（常見區間，不是單一答案）**：把上面全部攤開，短的落在「幾天到
兩週」量級（CodeSandbox 快照、GCP soft delete 預設值），中間最密集的
落點是「一個月上下」（Firebase／Supabase／GitHub Codespaces／Vercel
Hobby 部署皆為 30 天），再往上是「一季到半年」（GitHub Actions 私有
repo 上限、Vercel Pre-Production 180 天），最長的是「將近一年到超過
一年」（Vercel Production 部署 1 年、GA4 付費版最長 50 個月）。**這個
分佈本身告訴我們的是：視窗長度幾乎完全取決於「這份資料被拿去做什麼、
重新取得它有多貴」，不是有一個業界公認的「正確」數字。**

Sources：
- Firebase — [Authenticate with Firebase Anonymously Using JavaScript](https://firebase.google.com/docs/auth/web/anonymous-auth)（含 Android 版交叉核對），存取於 2026-09-11：「Any anonymous accounts created after enabling automatic clean-up might be automatically deleted any time after 30 days post-creation.」「If you 'upgrade' an anonymous account by linking it to any sign-in method, the account will not get automatically deleted.」
- Supabase — [Anonymous Sign-Ins](https://supabase.com/docs/guides/auth/auth-anonymous)，存取於 2026-09-11：「Automatic cleanup of anonymous users is currently not available.」建議查詢：`delete from auth.users where is_anonymous is true and created_at < now() - interval '30 days';`
- StackBlitz — [Privacy Policy](https://stackblitz.com/privacy-policy)，存取於 2026-09-11：「We will delete or anonymize such data within a commercially reasonable period following account closure not to exceed thirty days, subject to backup retention, legal obligations, and security requirements.」
- CodeSandbox — [Persistence](https://codesandbox.io/docs/sdk/persistence)（**本輪僅經 WebSearch 摘要確認，直接 WebFetch／curl 皆被 Cloudflare bot 驗證擋下（403），見附錄**），存取嘗試於 2026-09-11。
- Glitch — 官方 archiving 說明文章目前 DNS 已解析不到（`help.glitch.com` 不可達，與其平台已於 2025-07-08 停止代管一致，見下方 Glitch 關站來源），數字**僅經 WebSearch 摘要確認、未直接核對原文**：「In order to keep Glitch free for as many people as possible, Glitch disables apps that appear to have been abandoned」——沒有給出具體天數。Glitch 關站本身已直接核對：[Important changes are coming to Glitch](https://blog.glitch.com/post/changes-are-coming-to-glitch)，存取於 2026-09-11，關站原因是「運行數百萬個 app 的成本隨平台老化與濫用增加而大幅上升」，2025-07-08 停止代管與使用者頁面。
- GitHub Codespaces — [Configuring automatic deletion of your codespaces](https://docs.github.com/en/enterprise-cloud@latest/codespaces/setting-your-user-preferences/configuring-automatic-deletion-of-your-codespaces)，存取於 2026-09-11：「By default, GitHub Codespaces are automatically deleted after they have been stopped and have remained inactive for 30 days.」「The retention period is reset every time you connect to a codespace」「If you set a retention period of more than a day, you'll be sent an email notification one day prior to its deletion.」
- GitHub Actions artifacts — [Removing workflow artifacts](https://docs.github.com/en/actions/managing-workflow-runs/removing-workflow-artifacts) ＋ [Configuring the retention period for GitHub Actions artifacts and logs in your organization](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization)，存取於 2026-09-11：「By default, GitHub stores build logs and artifacts for 90 days」；public repo「between 1 day or 90 days」，private「between 1 day or 400 days」。
- Vercel Deployment Retention — [Deployment Retention](https://vercel.com/docs/deployment-retention)（`last_updated: 2026-08-21`），存取於 2026-09-11：Hobby 全為 30 天；Pro/Enterprise「Canceled 30 days／Errored 90 days／Pre-Production 180 days／Production 1 year」。
- Google Analytics 4 — [Data retention 官方說明](https://support.google.com/analytics/answer/7667196)，存取於 2026-09-11：「you can set the retention period of user-level data to: 2 months [or] 14 months」；「Turn this option ON to reset the retention period of the user identifier with each new event from that user」；「When data reaches the end of the retention period, it is deleted automatically on a monthly basis.」
- Google Cloud Storage — [About soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)，存取於 2026-09-11：「Soft delete is enabled by default for all buckets that support it, with a default retention duration of 7 days.」可調「anywhere between 7 to 90 days」。
- Stripe — [Test mode subscription data retention](https://support.stripe.com/questions/test-mode-subscription-data-retention)，存取於 2026-09-11：「Stripe automatically cancels subscriptions created in a sandbox or in test mode. This happens 90 days after the subscription is created.」「The subscription and related objects are deleted after a further 30 days.」

---

## 2. 分段刪的設計：soft-expire → grace period → hard delete

### 2.1 三個階段各自在做什麼

- **soft-expire（軟過期／標記凍結）**：資料還在，但功能上被當作「已經
  不存在」——使用者（或外部世界）看到的是「找不到」或明確的過期提示，
  不是正常內容。
- **grace period（緩衝期）**：軟過期之後、真的刪除之前的一段時間，通常
  只有「內部／管理員」還能把它救回來。
- **hard delete（真的刪除）**：緩衝期結束，資源／關聯全部真的清掉，
  通常不可逆。

**這個三段式最貼切的範例，剛好就是這個產品現在跑的平台自己**——Vercel
自己的 Deployment Retention 文件把這三段講得非常具體：一個部署「過期」
後，公開存取會看到 **HTTP 410**（軟過期），但在 **30 天的復原期**內
仍可以在後台「Restore」回來；30 天一過，才「所有關聯資源永久移除，
無法再復原」（硬刪除）。原文：「The origin deployment would expire on
03/01/2024, entering the recovery period, and users accessing it would
see a 410 status code. If required, you could still restore it until
03/31/2024, when all associated resources are permanently removed and
restoring the deployment is no longer possible.」——來源：
[Deployment Retention](https://vercel.com/docs/deployment-retention)，
存取於 2026-09-11。

Stripe 的測試模式訂閱是另一個乾淨的三段式範例，而且多了一個「豁免」
機制：**建立 90 天後自動取消（軟過期）→ 再 30 天的緩衝期（此時仍可在
Dashboard 手動標記「排除」來取消排定的刪除）→ 過了緩衝期才真正刪除**。
來源同上（見第 1 節）。

GCP Cloud Storage 的 soft delete 也是同一個形狀，只是換了說法：物件被
`DELETE` 之後不會馬上消失，而是進入「soft-deleted」狀態，可在保留視窗
內用「restore」找回來，視窗結束才真正清除——來源：
[About soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)，
存取於 2026-09-11。

### 2.2 續命規則：sliding（滑動／每次回訪重置）vs fixed（固定時鐘）

這是這一節真正的關鍵決策點，而且業界做法明確分成兩派，各有官方文件
可查：

| 模式 | 範例 | 官方原文 |
|---|---|---|
| **Fixed（固定時鐘，不因使用而續命）** | Firebase 匿名帳號 | 「Any anonymous accounts created after enabling automatic clean-up might be automatically deleted any time after 30 days post-creation.」文件通篇**沒有**任何一句提到日常使用會延長這個時限；唯一能避免被刪的方法是把帳號**升級**（連結到一個真正的登入方式），這是「脫離匿名池」而不是「續命」。來源同第 1 節。 |
| **Sliding（滑動，每次活動重置）** | GitHub Codespaces | 「The retention period is reset every time you connect to a codespace」——明確、無條件、每次連線就重置整個倒數。 |
| **可選（兩種都支援，使用者自己決定）** | Google Analytics 4 | 「Turn this option ON to reset the retention period of the user identifier with each new event from that user」——預設關閉（固定視窗），使用者可以主動打開變成滑動。 |
| **用「排除清單」取代單純的續命規則** | Vercel Deployment Retention | 不是簡單的「最後存取時間 + N 天」，而是一整套例外規則：只要是「最近 10 次部署之一」「最近 20 次 Ready 的 production 部署之一」「有 alias 指向它」「是目前還活著的分支的最新 preview」等任一條件成立，就不會被清——這是把「還有沒有人在用」拆成好幾個具體、可查詢的條件，而不是單一個時間戳。 |

**滑動續命的副作用（GA4 官方文件本身就點出了這個 trade-off，不是本文
猜測）**：「Reset user data on new activity」這個選項存在的理由，正是
讓「還活躍的使用者」的資料不會因為視窗到期就被清掉——但反過來說，
**只要使用者持續有任何活動，這份資料就永遠不會被清除**。這正是題目
要問的「副作用（永遠續命＝永遠不清）」——它不是隱藏風險，是這個機制
設計出來就要達成的效果，取決於你要不要接受這個效果。

### 2.3 通知機制：大多數範例的使用者「找得到」，Option Chaser 的匿名
使用者「找不到」

GitHub Codespaces 在緩衝期開始前一天會發 email；Vercel、Stripe、GCP
的使用者都是登入過的帳號持有者，管理後台隨時能看到「這個東西快被清了」
的提示。**這些範例背後的共同前提是：平台知道怎麼聯絡到這個使用者，或
使用者自己隨時能回頭檢查後台狀態。**

這一點對 Option Chaser 不成立——目前的匿名 owner 身份（`SOLO_OWNER`
固定值／未來若换成 per-session 匿名 id）沒有 email、沒有登入後台，唯一
「回來查看」的管道就是使用者自己記得那個瀏覽器／那個網址。這代表：
- Grace period 期間**沒有辦法主動通知**使用者「你的東西快被清了」；
- 唯一可能的「軟提示」只能是**使用者真的自己回來時**，在畫面上看到
  類似「這批資料已標記為即將清除／已封存，可以在期限內恢復」的訊息
  ——跟 Vercel「已過期會看到 410、但後台仍可救回」的做法比較接近，
  而不是 GitHub Codespaces 那種主動 email 提醒。

這一段是【Option Chaser 產品選擇】層級的推論（依現有匿名身份模型
推導），不是外部查到的事實，特此標明。

---

## 3. 哪些資料該跟著 owner 一起刪、哪些不該（含 GDPR）

### 3.1 GDPR 的 storage limitation 原則到底要求什麼

先講清楚一個常見誤解：**GDPR 沒有規定任何具體的保留天數**。官方英國
監管機關 ICO 的白話說明：「The UK GDPR does not set specific time
limits for different types of data. This is up to you, and will depend
on how long you need the data for your specified purposes.」它要求的是
**有一套寫下來的、可以對外說明理由的保留政策，定期覆核，過期就刪除或
匿名化**：「You need a policy setting standard retention periods
wherever possible... You should also periodically review the data you
hold, and erase or anonymise it when you no longer need it.」——來源：
[ICO：Storage limitation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/storage-limitation/)
（**本輪僅經 WebSearch 摘要確認，直接 WebFetch 被目標站回 403，見附錄**），
存取嘗試於 2026-09-11。

GDPR 條文本身（Regulation (EU) 2016/679 第 5 條第 1 項 e 款）：「Personal
data shall be kept in a form which permits identification of data
subjects for no longer than is necessary for the purposes for which the
personal data are processed... ('storage limitation')」——第 2 項要求
資料控管者能「證明」自己遵守了這條原則（accountability，不是嘴上說
說）。來源：[Art. 5 GDPR](https://gdpr-info.eu/art-5-gdpr/)（EUR-Lex 官方
規章文字的公開鏡像站，逐條收錄無刪節），存取於 2026-09-11。

**換句話說：Owner 不准拍腦袋定「30 天」，這件事本身是對的直覺，但
GDPR 本身也「沒有」規定 30 天或任何其他數字——它要求的是「有一個你能
說明得出道理、而且真的照做（刪除或匿名化）的政策」，而不是「選對
數字」。**這跟本文第 1 節整理出的「業界常見區間很廣」是一致的：業界
沒有共識數字，法規也沒有要求特定數字，兩者都要求的是「有意識地選一個
形狀、寫下理由」。

### 3.2 匿名化（anonymisation）是刪除以外的第二條路

歐盟 GDPR 的定義下，**真正被匿名化過的資料，就不再是「個人資料」，
GDPR 整套規則直接不適用**——這是 ICO 官方立場：「data protection law
does not apply to anonymous information」。但這裡有一個常見混淆：
**假名化（pseudonymisation，例如把姓名換成一個編號）不等於匿名化**——
被假名化的資料，只要有辦法（不論是誰、透過什麼額外資訊）能連回原本
的人，仍然算是個人資料，仍受 GDPR 規範。ICO 官方對這兩者的區分：
「Properly anonymised data falls outside the scope of the UK GDPR,
whereas pseudonymised data remains personal data」（來源：WebSearch
摘要整理 ICO
[Introduction to anonymisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/introduction-to-anonymisation/)
與
[Pseudonymisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/pseudonymisation/)
兩頁，**本輪未直接 WebFetch 這兩頁，僅經搜尋摘要確認**，存取嘗試於
2026-09-11）。

這件事對 Option Chaser 的意義：如果一個 owner 的市場分析內容（劇本、
候選、成本序列）在刪除之前先被剝除掉任何「能連回這個具體瀏覽器／
session／IP」的欄位，理論上就已經不再是個人資料——這給了「不一定要
整批物理刪除，也可以考慮匿名化保留（例如純粹拿去做匿名的產品使用
統計）」這條路留了一個口子，但**這需要法律／隱私專業判斷這個瀏覽器
id／owner id 本身算不算「可識別」，本文不下這個結論**（見下一小節）。

### 3.3 一個灰色地帶：匿名的 session id／IP 算不算「個人資料」

GDPR 前言第 26 點與 ICO 對「識別子」的說明明確把「online identifiers」
（含 IP 位址、cookie id、裝置代碼）列入「個人資料」的範疇——只要有
「合理可能被用來」把它連回一個具體人，就算：「The UK GDPR specifically
includes the term 'online identifiers' within the definition of what
constitutes personal data.」（來源：WebSearch 摘要整理 GDPR Recital 26
與 ICO
[What are identifiers and related factors?](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/personal-information-what-is-it/what-is-personal-data/what-are-identifiers-and-related-factors/)，
**本輪未直接 WebFetch，僅經搜尋摘要確認**，存取嘗試於 2026-09-11）。

也就是說：**「這個使用者沒有帳號、沒有 email，所以他的資料不算個人
資料」這個假設不一定站得住腳**——如果 owner id 綁著一個持久的瀏覽器
指紋或 IP，理論上仍可能落入 GDPR 的個人資料定義。反過來，GDPR 第 3
條第 2 項的境外適用範圍是「向歐盟境內人士提供服務或監控其行為」時
才適用（「This Regulation applies to the processing of personal data
of data subjects who are in the Union by a controller or processor not
established in the Union, where the processing activities are related
to...」，來源：[Art. 3 GDPR](https://gdpr-info.eu/art-3-gdpr/)，存取於
2026-09-11）——如果 Option Chaser 的使用者實際上都在歐盟／英國境外，
這條法規未必直接適用。**這兩件事都不是本文能下判斷的地方（需要真正
的法律意見），只把已查到的官方定義原樣列出，供 Owner 或律師參考。**

### 3.4 判準：這筆資料「描述的是誰」

拋開法規細節，業界處理多租戶／多使用者系統的資料分類，實務上收斂到
一個很簡單的問題：**這筆資料的內容，是在描述一個具體的人（或這個人
做的具體選擇），還是在描述一個跟這個人無關、任何人查都會得到同樣
答案的客觀事實？**

- 「這個人在 2026-09-10 建立了一個劇本、設定的目標價是多少」→ 描述
  這個人的行為與選擇 → **個人資料，owner 刪除時應該一起清**。
- 「TLT 在 2026-09-10 的殖利率曲線是多少」→ 客觀市場事實，跟是誰查
  的完全無關，一千個使用者查到的答案完全一樣 → **不是個人資料，
  不該因為某個 owner 被刪就跟著刪**（其他還活著的 owner 之後可能還
  要用同一份）。

對照到 Option Chaser 現有的表（依題目給定事實）：

| 表 | 描述的是誰 | 分類 | owner 被刪時 |
|---|---|---|---|
| `scenarios` | 這個人設定的劇本 | 個人 | 應清 |
| `results` / `current_results` | 這個人的分析結果 | 個人 | 應清 |
| `snapshots` | 這個人那次分析抓到的原始報價快照（per-scenario，**不是**跨使用者共用） | 個人 | 應清 |
| `narrow_history` | 這個人劇本的歷史候選成本序列 | 個人 | **目前漏清**（見第 7 節） |
| `events` | 這個人劇本的事件紀錄 | 個人 | 應清 |
| `diagnostics` | 這個人操作觸發的除錯事件 | 個人（雖然是運維用途，但目前有 `owner_id` 標記） | **目前完全沒有清理路徑** |
| `owner_settings` / `owner_credentials` / `owner_verifications` | 這個人的偏好設定與第三方 token | 個人（`owner_credentials` 更是**敏感個人資料**） | **目前完全沒有清理路徑** |
| `rate_cache` / `treasury_year_cache` / `dividend_cache` | 市場事實（利率曲線、股利） | 共用，跟誰查無關 | **不該**因單一 owner 被刪而清 |
| `chain_backoff` | Cboe 429 限流狀態，是 provider 全站狀態 | 共用 | 不該清 |
| `operational_metrics` | 全站運維指標，已有 30 天 trim | 共用 | 不該清 |
| `contract_iv_history` / `iv_observations` / `iv_backfill_runs` | 個別合約的歷史 IV 觀測，理論上跨 owner 可重用 | 共用（既有未裁的議題，不在本文展開） | 不該因單一 owner 被刪而清 |

---

## 4. 技術上怎麼刪才不會把 DB 弄慢

### 4.1 為什麼 `DELETE` 不會馬上釋放空間

PostgreSQL 官方文件講得很直白：`UPDATE`／`DELETE` **不會**立刻移除舊
版本的資料列——這是 MVCC（多版本並行控制）機制的必要代價，因為在那個
瞬間，其他還在跑的交易可能還「看得到」那一列：「an `UPDATE` or
`DELETE` of a row does not immediately remove the old version of the
row... eventually, an outdated or deleted row version is no longer of
interest to any transaction. The space it occupies must then be
reclaimed for reuse by new rows... This is done by running `VACUUM`.」
——來源：
[PostgreSQL 官方文件：Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)，
存取於 2026-09-11。

**普通 `VACUUM` 跟 `VACUUM FULL` 的差別，官方文件也講得很明確**：普通
`VACUUM` 把空間標記成「可重複使用」，但**不會**還給作業系統；`VACUUM
FULL` 才會真的把整個表重寫一份、把空間還給作業系統，但代價是需要
`ACCESS EXCLUSIVE` 鎖（等於整張表被鎖住，其他人都不能用），所以官方
建議「一般情況下應該用普通 VACUUM，避免用 VACUUM FULL」：「The
standard form of VACUUM... will not return the space to the operating
system... VACUUM FULL... requires an ACCESS EXCLUSIVE lock... Generally,
therefore, administrators should strive to use standard VACUUM and
avoid VACUUM FULL.」同上來源。

**自動化交給 autovacuum 是官方預設、也是官方建議的做法**：「PostgreSQL
has an optional but highly recommended feature called autovacuum...
In the default configuration, autovacuuming is enabled」，觸發門檻是
一個公式（累積的死列數超過門檻就自動跑）：`vacuum threshold =
Minimum(vacuum max threshold, vacuum base threshold + vacuum scale
factor × number of tuples)`。同上來源。

### 4.2 長交易會卡住整個回收機制

官方文件也點名了一個容易忽略的陷阱：**只要有任何一個交易還沒結束
（不管它在幹什麼），PostgreSQL 就不能回收在那之後產生的死列**——因為
理論上那個舊交易仍可能需要「看到」舊版本。官方建議的排查方法是查
`pg_stat_activity` 找出 `age(backend_xid)` 或 `age(backend_xmin)`
異常大的交易，該結束就結束掉：「End long-running open transactions.
You can find these by checking pg_stat_activity for rows where
age(backend_xid) or age(backend_xmin) is large.」同上來源。這對「批量
清除 abandoned owner 的資料」的直接含意是：**清除工作本身如果包在一個
超大的單一交易裡跑，不但慢，還會讓自己製造出來的死列一直卡著、無法被
autovacuum 回收**——這正是下一小節要處理的問題。

### 4.3 分批刪除：業界共識做法（社群慣例，非官方硬性規定）

「用 `LIMIT` 分批刪、避免單一超長交易」是 PostgreSQL 社群廣泛採用的
做法，但**這一段本身不是官方文件的硬性規定，是社群一致性很高的實務
共識**，本文誠實標示為社群慣例：

- 典型寫法是每批刪 1,000～5,000 筆，用子查詢加 `LIMIT` 圈出這一批的
  主鍵，再對這批主鍵做 `DELETE`（例如 `DELETE FROM t WHERE id IN
  (SELECT id FROM t WHERE <條件> LIMIT 5000)`），每批各自成一個短交易；
- 大量刪除進行中，適時手動跑一次 `VACUUM`（而非全部刪完才跑一次）
  能讓空間更快被回收，但要注意 `VACUUM` 本身不能在一個顯式交易區塊
  （`BEGIN...COMMIT`）內執行。

（來源：本輪 WebSearch 對社群文章的摘要整理，非單一權威來源逐字引用，
列為【業界慣例】層級但非官方文件等級，供參考。）

**題目特別點名的 `ctid` 分批模式，官方文件其實有一段明確的警告**：
`ctid`（資料列在檔案裡的物理位置）確實可以拿來當一種「免費」的定位
方式，但官方文件明講它**不穩定**——只要那一列被 `UPDATE` 過，或整張表
被 `VACUUM FULL` 搬動過，`ctid` 就會變：「although the ctid can be
used to locate the row version very quickly, a row's ctid will change
if it is updated or moved by VACUUM FULL. Therefore ctid should not be
used as a row identifier. A primary key should be used to identify
logical rows.」——來源：
[PostgreSQL 官方文件：System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html)，
存取於 2026-09-11。**换句話說：`ctid` 分批模式在「短交易、清完一批就
放手」的情境下是安全、快的（社群大量案例佐證），但不該把它當成跨交易
持久保存的識別鍵；用主鍵範圍（例如 `id > :last_id ORDER BY id LIMIT
N`）分批，是官方文件立場更一致、更不容易踩雷的替代方案。**

### 4.4 在 Neon 上，刪掉的資料什�麼時候「真的」不再佔空間、不再計費

這是題目問得最細、也最容易被忽略的一點：**Neon 把 storage 拆成兩個
分開計費的項目**——「Storage」（目前資料庫實際大小）跟「History」
（為了支援即時還原、Time Travel 查詢、從過去某個時間點開分支，而
保留的 WAL／異動紀錄）。這兩者的生命週期不一樣：

- 資料被 `DELETE` 之後，要先等 autovacuum（或手動 `VACUUM`）把死列
  標記回收，「Storage」這個數字才會真的變小；
- 但即使 Storage 變小了，**描述「這筆資料曾經存在過、後來被刪掉」這
  件事本身的 WAL 紀錄，還會在「History window」設定的視窗內持續被
  保留、持續計費**——直到超出視窗才會被真正清掉，停止計費：「WAL
  records that fall outside the configured history window are
  automatically removed and stop contributing to your project's
  storage costs.」

各方案的 History window 預設值與上限：

| 方案 | 預設 | 上限 |
|---|---|---|
| Free | 6 小時 | 6 小時（額外設 1 GB 上限） |
| Launch | 1 天 | 7 天 |
| Scale | 1 天 | 30 天 |

（Business／Enterprise 方案未在本輪查到的文件頁面列出。）

計費方式：「The more history you retain, the more storage you use, and
the higher those charges.」付費方案是 $0.20/GB-month，Free 方案封頂
1 GB、不額外收費。——來源：
[Neon：Restore window](https://neon.com/docs/introduction/restore-window)
＋
[Neon：History window](https://neon.com/docs/introduction/history-window)，
存取於 2026-09-11。

**這對 Option Chaser 的直接含意**：本輪批量清除一批 abandoned owner
的資料之後，實際反映到帳單上的「storage 真的變小了」這件事，**要看
你這個 Neon 方案的 History window 設多長**——window 越長，清除的
即時效益越會被延後看到（因為 WAL 紀錄還在算 History 費用），這跟這個
repo 自己在 SCALE-16／#267 那一輪已經實測過的教訓（一次性連續覆寫
如果沒有中途跑 VACUUM，MVCC 膨脹可以到「真實需要空間的 5.7 倍」）是
同一類陷阱的兩個不同面向：**「刪了」跟「storage 帳單真的降下來」之間
永遠隔著一段 autovacuum／History window 的時間差，規劃清理排程時不能
假設它是瞬間生效的。**（Neon 官方 blog 對這個主題也有相符的一般性
建議：「Postgres autovacuum automates the process of reclaiming
storage space after rows are updated or deleted」，並建議依交易量
調整 autovacuum 排程頻率——來源：
[6 tips to optimize storage costs for your Postgres databases](https://neon.com/blog/6-tips-to-optimize-storage-costs-for-your-postgres-databases)，
存取於 2026-09-11。）

---

## 5. 排程在哪裡跑

### 5.1 Vercel Cron（這個 repo 已有一支）

Vercel 官方文件把各方案的頻率上限講得非常明確：

| 方案 | 每個專案 cron 數上限 | 最小間隔 | 排程精確度 |
|---|---|---|---|
| Hobby | 100 個 | **一天一次** | 以小時為單位（±59 分鐘） |
| Pro | 100 個 | 一分鐘一次 | 以分鐘為單位 |
| Enterprise | 100 個 | 一分鐘一次 | 以分鐘為單位 |

Hobby 方案想排「每小時跑一次」這種頻率會直接在部署時失敗：「Hobby
accounts are limited to cron jobs that run once per day. Cron
expressions that would run more frequently will fail during
deployment... Hobby accounts are limited to daily cron jobs. This cron
expression would run more than once per day.」而且即使是「一天一次」，
Vercel 也**不保證精確時間**：「a cron job configured as 0 1 * * *
(every day at 1 am) will trigger anywhere between 1:00 am and 1:59
am.」——來源：
[Usage & Pricing for Cron Jobs](https://vercel.com/docs/cron-jobs/usage-and-pricing)
（`last_updated: 2026-07-15`），存取於 2026-09-11。

**關鍵的相容性事實**：cron job 本身就是在呼叫一個 Vercel Function
——「Cron jobs invoke Vercel Functions. This means the same usage and
pricing limits will apply.」同上來源。也就是說，**cron 觸發的清理
邏輯，跟這個 repo 任何一個普通 API endpoint 一樣，受同一個
`maxDuration` 限制**。這個 repo 現有的 `vercel.json` 目前把
`api/index.py` 的 `maxDuration` 明確寫死成 **60 秒**（獨立於 Vercel
平台近期把 Fluid Compute 預設開啟後、平台本身 Hobby 方案函式時長上限
已經可以到 300 秒這件事——來源：
[Configuring Maximum Duration for Vercel Functions](https://vercel.com/docs/functions/configuring-functions/duration)
（`last_updated: 2026-08-24`），存取於 2026-09-11：Hobby 預設與上限
皆為「300s (5 minutes)」，Pro／Enterprise 預設 300s、上限 800s、
延伸上限 1800s（beta）——**但這個 repo 自己在設定檔裡選擇維持保守
的 60 秒，不是被平台強制**）。已有的 `POST /api/scenarios/refresh-run`
早就用「時間預算＋Continuation（未做完的部分回傳 `remaining`，前端
自動再呼叫直到清空）」這套機制在 60 秒限制下安全處理「可能跑很久的
批次工作」——**這正是清除大量 abandoned owner 資料若跑不完一次
invocation 時，該直接沿用的既有樣板，不需要另外發明一套。**

### 5.2 Neon `pg_cron`

`pg_cron` 是跑在資料庫**內部**的排程器，不透過 HTTP request，因此
完全不受 Vercel Function 的 60 秒限制。但它有一個對 serverless／
scale-to-zero 架構特別致命的限制，Neon 官方文件明講：**`pg_cron` 的
排程只在 compute 醒著的時候才會被觸發，一旦你的資料庫因為閒置而
scale-to-zero，排定的工作就是靜靜地不會執行，不會報錯、不會有任何
提示**：「pg_cron jobs will only run when your compute is active. We
therefore recommend only using pg_cron on computes that run 24/7 or
where you have disabled scale to zero.」——來源：
[Neon：The pg_cron extension](https://neon.com/docs/extensions/pg_cron)，
存取於 2026-09-11。額外限制：`cron.schedule_in_database()`（跨資料庫
排程）在 Neon 上不支援；啟用需透過 Neon API 設定
`cron.database_name` 參數，不是單純 SQL；相關設定參數因為由 Neon 代管，
一般使用者無法自行 `ALTER` 修改。

**這對 Option Chaser 的意義**：如果現在（或 Public Beta 早期）是用
Neon 免費層／低成本方案且啟用了 scale-to-zero 省錢，`pg_cron` 排定的
清理工作很可能會在使用量低的時段（也就是最該清理的時段）悄悄不執行
——除非願意讓 compute 保持 24/7 醒著（等於放棄 scale-to-zero 省下的
成本）。這比「60 秒限制」本身更值得注意，因為它是**靜默失效**，不是
會報錯讓人發現的那種失敗。

### 5.3 手動腳本（這個 repo 已有慣例）

這個 repo 已經有 `scripts/backfill_owner_ids.py`／
`backfill_result_fact_context.py`／`backfill_settings_to_owner.py`
三支既有的手動腳本慣例——不受任何 serverless 時長限制（在本機或 CI
runner 上跑，想跑多久都行），但**不是自動排程**，需要人／CI pipeline
記得去觸發。過去這類正確性攸關的批次工作，這個團隊一直傾向「人工
觸發、可重跑、可安全中斷」而非盲目自動化——這是一個已經存在、被
反覆驗證過的操作哲學，適合用在「第一次上線、需要謹慎跑一次確認安全」
的清理工作，但不適合作為長期、要求「必須自動、持續發生」的保障
機制。

### 5.4 三者相容性小結

| 方式 | 受 60 秒限制？ | 主要風險 | 適合階段 |
|---|---|---|---|
| Vercel Cron | 是（cron 呼叫的就是一個 Function） | Hobby 方案只能一天一次；需要沿用既有 Continuation／budget 樣板才能處理大量資料 | 長期、需要「自動、持續」保障的正式機制 |
| Neon `pg_cron` | 否（DB 內部背景工作） | scale-to-zero 時**靜默不執行**，比逾時更難察覺 | 只適合 compute 保持常駐醒著的情境 |
| 手動腳本 | 否 | 需要人／CI 記得觸發，不是持續保障 | 第一次上線前的驗證跑、或低頻率的人工維運 |

---

## 6. 附帶一提：controlled beta 的 synthetic／load-test 資料

Owner 提到 controlled beta 階段會刻意用 synthetic users／bots 模擬不同
匿名身份與使用頻率去壓測——這批「用完即丟」的測試資料，業界确实有一個
獨立於「一般使用者 retention」的成熟慣例可以參考：**把測試流量放進一個
結構上就跟正式資料分開的獨立空間，事後一鍵整批清空，而不是等它自然
「abandoned」後走一般清理流程**。

Stripe 的測試模式（test mode／sandbox）就是這個模式的官方範例：測試
物件跟正式資料**完全隔離**（「API objects in one mode aren't
accessible to the other」），且提供一個 Dashboard 按鈕「Delete test
data」可以一次刪光目前 sandbox 裡的全部測試物件（「To delete all of
your test data from your Stripe account... Click Delete test data to
initiate the deletion process. You can't undo the deletion of your
test data.」）——來源：
[Stripe：Testing use cases](https://docs.stripe.com/test-mode)，
存取於 2026-09-11。

**這對 Option Chaser 的意義**：如果 controlled beta 一開始就替 synthetic
owner 打上一個可查詢的標記（例如一個獨立的 `is_synthetic` 欄位，或
乾脆讓 synthetic owner 的 `owner_id` 落在一個保留的命名空間），事後
「這一輪壓測跑完了，全部清掉重來」可以是一個跟一般 abandoned-cleanup
邏輯完全獨立、更粗暴、更即時的操作（就像 Stripe 那顆按鈕），不需要
等它符合「棄置 N 天」的判準才被清——**這不是本文的新研究題目，只是
研究過程中順手記下的一個現成、被驗證過的模式，供 controlled beta 開始
前參考。**

---

## 7. 這對 Option Chaser 意味著什麼

逐條對照題目給定的既有事實：

1. **`delete_scenario()` 漏了 `narrow_history`**——這是一個具體、
   範圍很小、幾乎可以直接當成 bug 修的缺口（不是需要 Owner 裁示的
   價值判斷）。目前的後果是「使用者自己在垃圾桶按下永久刪除」這個
   既有操作，會在 `narrow_history` 留下永遠沒有 `scenarios` 那一列
   可以對應的孤兒資料——單一 owner 使用時量體小、幾乎看不出來，但
   在 Public Beta 下每一次刪除都會累積一點洩漏，長期會變成一張只會
   長大、永遠不會變小的表。

2. **沒有『刪掉一個 owner 及其全部資料』這個操作，比「漏一張表」
   嚴重得多**——`owner_settings`／`owner_credentials`／
   `owner_verifications`／`diagnostics` 這四張表**連「單一 owner
   範圍」的刪除路徑都不存在**（`delete_scenario()` 是 per-scenario
   的，不是 per-owner 的）。這代表即使 Owner 現在就想清理一批
   abandoned 使用者，**技術上也還沒有一個可以呼叫的原語**——第一步
   永遠是先補上這個「給定一個 owner_id，橫跨全部相關表清乾淨」的
   操作本身，這不是「要不要清」的價值判斷，是「想清就得先有這個
   工具」的前提工程工作。

3. **`owner_credentials` 是這裡面優先序最不該跟其他資料混在一起討論
   的一塊**——裡面放的是第三方 API（例如 Market Data App）的存取
   token。一個被判定 abandoned 的匿名使用者，如果他的 token 永遠
   留在資料庫裡，這不是「省不省 storage」的問題，是**安全曝險**：
   萬一發生資料庫外洩，這些 token 若仍然有效，攻擊者可能直接拿去
   打第三方 API、產生實際的財務或濫用後果，而且原始使用者完全不會
   知道。這件事的優先序建議跟「一般匿名使用者資料要留多久」分開
   決定——即使 Owner 決定「暫時不清一般使用者資料，先觀察」，
   `owner_credentials` 這塊仍值得優先處理（見第 8 節 OD-R4）。

4. **`snapshots` 現在是 per-scenario／per-owner 的，不是共用的**——
   OD-06「原始快照永久保留」這條裁示，是在「全世界只有一個人用」
   的前提下做的。多使用者的 Public Beta 下，**這條裁示的實際成本會
   隨使用者數線性放大**：以前「永久保留」等於「一個人的資料量永遠
   在長大」，現在等於「N 個人的資料量各自永遠在長大，加總起來」。
   反過來，`rate_cache`／`treasury_year_cache`／`dividend_cache`／
   `chain_backoff`／`operational_metrics` 這些**共用**市場事實表，
   結構上跟使用者數無關（不會因為多了一個 owner 就多一份，本身已經
   有 dedup 的設計），這是兩種資料在 Public Beta 情境下風險完全不同
   的關鍵差異——值得重新意識到，OD-06 當年沒有、也不需要考慮這個
   維度。

5. **controlled beta 的 synthetic 使用者，如果現在不先決定怎麼標記，
   之後會比 Stripe 那種「一鍵清空 sandbox」難做很多**——目前的資料
   模型裡沒有任何欄位區分「這是真人的匿名 session」還是「這是壓測
   bot 產生的」。如果 controlled beta 一開始跑，兩種資料混在一起，
   將來要單獨清掉壓測資料（而暫時保留真人資料觀察行為）會變成一次
   困難的資料考古，而不是像 Stripe 那樣的一次性操作。

**綜合來說：本輪研究沒有發現任何「必須現在决定retention 天數才能
進 Public Beta」的硬性阻擋（除了第 2、3 點那種「工具本身不存在」的
前提工程工作）。真正該優先動的是「補上 owner 範圍的刪除原語」與
「credential 清理」這兩塊工程缺口，跟「abandoned 判定要多少天」這個
價值題完全獨立，不需要等 Owner 想清楚天數才能動工。**

---

## 8. 資料生命週期 grilling 票應該問 Owner 的選項

以下每題只列選項與代價，**不推薦具體天數**。

### OD-R1：用什麼訊號判斷「這個匿名使用者不會回來了」

這題其實在決定什麼：不同的「活動」定義，會讓同一個天數在實務上代表
完全不同的寬鬆程度——選得太寬（例如任何一次頁面載入都算），幾乎沒有
使用者會真的「過期」；選得太窄，可能誤殺還在用、只是用得不頻繁的人。

A：**任何 HTTP 請求都算活動**（包含自動背景刷新、健康檢查式的載入）。
最寬鬆，最不容易誤殺真實使用者，但如果產品本身有「開站自動刷新」這類
背景行為，一個開著沒關的分頁可能永遠續命。
B：**只有明確的使用者動作算活動**（建立劇本、手動點刷新、編輯設定），
不含自動背景刷新。比較貼近「這個人真的還在用」，但實作上需要區分
「使用者觸發」與「系統自動觸發」的請求，多一點工程成本。
C：**只看某個固定時間點（例如帳號建立或上次分析）**，訪問本身完全不
續命（比照 Firebase 匿名帳號的做法）。最簡單、最容易保證資料真的會被
清掉，但對「偶爾回來看一下、沒有再操作」的使用者不友善。

你的建議：先確定「活動」的定義比先確定天數更重要——這是先決條件,
選錯會讓後面訂的任何天數都失去意義。傾向 B 或 C 這種「有明確訊號才算
活躍」的形狀，比 A 更能保證清理機制真的會生效。

不現在決定會卡住什麼：不會卡任何工程工作——补 owner 範圍刪除原語（見
第 7 節）跟這題完全獨立,可以先做。只有「真正排程開始跑」那一刻才需要
這題有答案。

---

### OD-R2：要不要有續命（回訪就重置倒數），還是固定時鐘

這題其實在決定什麼：一旦選了「續命」，就要接受這個機制的本質後果是
「持續活躍的使用者永遠不會被清」——這不是 bug，是這個設計本來就會
做到的事,關鍵是要不要接受。

A：**完全續命（sliding）**：每次符合 OD-R1 定義的活動，倒數整個重置
（比照 GitHub Codespaces）。對使用者最友善,但如果 OD-R1 選得太寬,清理
機制可能形同沒有。
B：**完全不續命（fixed）**：從某個固定時間點（建立、或上次分析）
算，之後不管有沒有活動都照原定時間到期（比照 Firebase 匿名帳號）。
保證資料一定會被清,但可能誤殺「偶爾回來、活動頻率低於判定窗口」的
使用者。
C：**續命但有上限**（例如最多續命 N 次，或最多再撑 M 天,不論怎麼
活動都會在某個絕對上限之後被清）：介於兩者之間，工程複雜度較高。

你的建議：先選「形狀」再選數字——如果選 A,強烈建議至少搭配某種上限
（即 C 的變體），避免真的變成「事實上永久保留」；如果不確定,B 比較
安全、也比較容易解釋給自己與未來的自己。

不現在決定會卡住什麼：跟 OD-R1 一樣不擋前置工程工作,只擋「排程真正
開始清」這一步。

---

### OD-R3：要幾段式（軟過期 → 緩衝期 → 硬刪除），還是直接一段刪掉

這題其實在決定什麼：Option Chaser 的匿名使用者沒有 email、沒有登入
後台,「緩衝期」在這裡的意義跟大多數業界範例（使用者收到 email 提醒）
不一樣——只能靠使用者自己記得回來查看,而且緩衝期本身要花額外的
storage 成本（GCP／Neon 的官方文件都證實了這一點：緩衝期內的資料
照樣全額計費）。

A：**三段式**（先軟過期標記/凍結 → 一段緩衝期，使用者若回來仍能看到
並救回 → 緩衝期過了才真的刪除，比照 Vercel 自己的部署 retention）。
使用者體驗最好、給自己留犯錯空間，但多一段狀態要維護,且緩衝期本身
持續佔用付費的 storage。
B：**兩段式**（軟過期即視覺上「消失」，但延遲一段時間才真的物理刪除，
中間**不對外提供任何救回入口**,只是內部延遲清除以防意外)。比三段式
簡單,犧牲的是使用者主動救回的機會。
C：**一段式**（判定條件成立就直接刪，沒有觀察期）。最簡單、最快省下
storage,但完全沒有犯錯容錯空間,誤判就是真的沒了。

你的建議：至少要有內部層級的緩衝（即 B 的下限）——理由是這個判定
邏輯第一次上線幾乎不可能一次寫對,直接一刀真刪（C）在還沒驗證過判定
邏輯之前風險偏高。是否要做到 A 的「使用者自己能看到、能救回」這一層
UX,取決於 Owner 覺得這件事值不值得投入。

不現在決定會卡住什麼：會卡「排程真正上線」,但不擋補齊刪除原語本身
（先把「怎麼刪乾淨」做對,晚一點再決定「分幾段刪」）。

---

### OD-R4：`owner_credentials` 裡的第三方 token，要不要跟一般資料分開、
優先處理

這題其實在決定什麼：這不是「省 storage」的題目，是安全曝險的題目——
一個 abandoned owner 的第三方 API token 如果一直有效地留在資料庫裡,
資料庫外洩時會變成真實的濫用管道。

A：**跟其他個人資料一視同仁，等一般清理排程一起處理**。最簡單，不需要
額外工程,但代表 credential 曝險的時間窗口跟「abandoned 判定天數」
綁在一起——如果一般清理設得寬鬆（例如半年才判定 abandoned），token
就曝險半年。
B：**獨立、更短的清理節奏**（例如 owner 判定為 abandoned 之前，先讓
credential 這一塊單獨提前失效或清除，跟劇本/結果分開排程）。多一組
獨立邏輯,但把曝險窗口跟一般資料保留天數脫鉤。
C：**主動撤銷而不只是刪除本地紀錄**（呼叫第三方 API 讓 token 本身
失效,而不只是從自己的資料庫刪掉那一列）。安全性最高,但取決於該
第三方 API 是否提供撤銷端點,工程成本因供應商而異。

你的建議：這題的優先序建議獨立於「一般匿名使用者要留多久」之外先
決定——即使 Owner 決定一般資料先不清、觀察再說,credential 這塊仍
建議提前處理,B 或 C 都比 A 更負責任。

不現在決定會卡住什麼：不影響其他清理工作的排程設計,可以獨立、更快
先動工。

---

### OD-R5：要不要有使用者自己主動要求「立刻刪光我的全部資料」的入口

這題其實在決定什麼：這是跟「系統自動判定 abandoned 而清除」完全不同
的一條路——業界範例（Stripe「刪除全部測試資料」按鈕、StackBlitz／
Glitch 的手動刪除申請）大多兩條路都有，這題在決定 Option Chaser 要
不要也做這一條。

A：**現在就做**：提供一個入口（例如設定頁的一顆按鈕），使用者自己
按下去就立刻清光他名下全部資料,不必等任何 abandoned 判定。這同時也
是回應「使用者主動要求刪除」這類請求最直接的方式,不論 GDPR 是否
直接適用都是一個負責任的產品姿態。
B：**先不做，只靠系統自動判定 abandoned**。工程成本較低（本輪要補的
owner 範圍刪除原語一次到位、兩條路都能共用),但使用者無法主動清除
自己的資料,必須等系統判定或等 Owner 手動處理。
C：**先做「軟性」版本**（例如匿名的「清空我在這台裝置上的紀錄」，
只清本地識別、不保證後端立刻物理刪除,類似很多網站的「登出並清除
cookie」而非真的刪帳號）。介於兩者之間,使用者體感有清除,但後端清理
邏輯仍可以晚一點做。

你的建議：既然第 7 節已經指出「owner 範圍的刪除原語」是無論如何都要
先補的前提工程,A 的邊際成本其實不高（同一個原語,多接一個由使用者
自己觸發的入口）,值得考慮跟修 bug 一起做掉。

不現在決定會卡住什麼：不影響第 7 節的前提工程動工,但影響前提工程
做完之後,第一個接上它的功能入口是什麼。

---

### OD-R6：排程要用哪一種（自動排程 vs 隨手觸發 vs 手動腳本）

這題其實在決定什麼：三種方式在「保證會執行」與「維運心力」之間的
權衡完全不同,且 Neon `pg_cron` 有一個容易被忽略的靜默失效風險
（scale-to-zero 時排定的工作根本不會被觸發,不會報錯）。

A：**Vercel Cron，排定排程自動跑**。最省心,但 Hobby 方案只能一天
一次、且時間精確度只到「小時」量級；若清理邏輯可能跑超過 60 秒,
需要沿用既有的 Continuation／budget 樣板分批處理。
B：**Neon `pg_cron`，排定排程跑在資料庫內部**。不受 Vercel 60 秒
限制,但只在 compute 醒著時才會執行——若使用 scale-to-zero 省成本,
清理工作可能在最該執行的低流量時段被靜默跳過,且沒有任何錯誤提示會
讓人發現這件事發生了。
C：**沿用既有 `scripts/backfill_*.py` 慣例，人工／CI 手動觸發**。
最安全（每次執行都是有人決定要跑）,不受任何時長限制,但不是持續、
自動的保障機制,需要有人記得定期跑。

你的建議：清理邏輯第一次上線,建議先用 C 手動跑幾輪確認判定邏輯與
刪除範圍都正確,穩定之後再切換成 A（同時因為這個 repo 已經有
`CRON_SECRET` 這套既有驗證慣例可以直接套用）。B 除非確定 compute
會維持常駐,否則不建議作為主要機制。

不現在決定會卡住什麼：不擋前提工程（補齊刪除原語、判定邏輯),只影響
「排程正式常態化」那一步,可以先用 C 邊做邊觀察,晚一點再拍板 A 或 B。

---

### OD-R7：controlled beta 的 synthetic／bot 資料，要不要獨立標記、
獨立清理節奏

這題其實在決定什麼：如果現在不決定怎麼標記合成流量,之後要把壓測
資料跟真人（即使匿名）資料分開清理,會比一開始就標記困難得多——這題
不影響一般使用者 retention 的決定,但影響 controlled beta 本身怎麼
收尾。

A：**現在就加一個標記欄位**（例如 `is_synthetic` 或保留的 owner id
命名空間),controlled beta 結束後可以像 Stripe 那樣一鍵整批清空,不必
等它符合一般 abandoned 判準。
B：**先不特別標記，跟真人匿名使用者用同一套清理邏輯**。省下這次的
工程成本,但事後要單獨清掉壓測資料會變成一次資料考古,且壓測資料
在此之前會跟真人資料一起佔用同一套 retention 判準的觀察樣本。
C：**用完全獨立的資料庫／schema／環境跑 controlled beta**（比照
Stripe test mode 那種結構性隔離,不只是加一個欄位)。隔離最乾淨,但
工程成本最高,且事後若要分析「synthetic 流量對系統的真實影響」會
需要額外把兩邊資料接起來看。

你的建議：A 是成本效益最好的選項——只是一個欄位,換來事後清理的巨大
方便,而且不影響 controlled beta 本身要驗證的東西（Scenario 建立／
refresh／DB growth／vendor quota／rate limit 這些壓力測試,標記本身
不會干擾）。

不現在決定會卡住什麼：只要在 controlled beta **正式開始建立第一批
synthetic owner 之前**決定就不算晚；已經開始之後再補標記,就會需要
額外的資料考古工作去回溯哪些是合成的。

---

## 9. 附錄：查證方式與 UNVERIFIED 項目

**環境限制**：本沙箱的 `WebFetch` 工具對 `web.archive.org` 有內建
拒絕（非網路層問題，工具本身直接回覆「unable to fetch」）；對
`help.glitch.com` 是 DNS 無法解析（`getaddrinfo ENOTFOUND`），與 Glitch
已於 2025-07-08 停止代管、可能已收回該子網域一致；`codesandbox.io`
的文件頁面（`/docs/sdk/persistence`）被 Cloudflare 的機器人驗證頁擋下
（`WebFetch` 與直接 `curl` 皆回 403／"Just a moment..." 驗證頁），
`archive.org` 的可用性 API（`archive.org/wayback/available`）可透過
`curl` 存取，但實際存檔頁面內容（`web.archive.org/web/...`）被本環境
的 egress 政策直接拒絕（「Blocked by egress policy」）。ICO
（`ico.org.uk`）多個頁面對 `WebFetch` 直接回 403。

以下項目**僅經 `WebSearch` 工具回傳的摘要確認，未能以 `WebFetch` 或
`curl` 直接取得原始頁面內容逐字核對**，标记为較低確信度（`WebSearch`
本身是基於真實索引內容產生摘要，非憑空生成，但本文無法對其逐字核對）：

- CodeSandbox `/docs/sdk/persistence` 的具體天數（記憶體快照 7 天、
  磁碟快照 2 週、封存「過去 4 年未刪除」）；
- Glitch `help.glitch.com` 的「Archiving Projects」文章原文（自動
  封存「appear to have been abandoned」的判準與天數，該頁面本身現已
  無法直接存取核對）；
- ICO：Storage limitation 頁面（本文引用的「沒有規定具體天數」等
  說法）、Introduction to anonymisation／Pseudonymisation 兩頁、
  What are identifiers and related factors 頁；
- GDPR Recital 26（線上識別碼是否算個人資料）的說明文字，經由第三方
  對 Recital 原文的轉述取得，未直接核對 Recital 26 官方逐字原文
  （已核對過的是 Article 3、Article 5 的官方逐字條文，Recital 部分
  屬前言說明，未逐字核對）；
- AWS S3 lifecycle expiration／transition 的行為說明（過期物件如何
  被非同步移除、多重規則的優先序），本輪僅經 `WebSearch` 摘要確認，
  未直接 `WebFetch` `docs.aws.amazon.com` 原頁。

以上項目若要在正式決策文件中逐字引用，建議在有更好的網路存取環境時
重新直接核對原文。其餘本文引用的官方文件（Firebase／Supabase／
StackBlitz／GitHub／Vercel／Google Analytics／Google Cloud Storage／
Stripe／PostgreSQL／Neon）皆已透過 `WebFetch` 直接取得頁面內容並逐字
核對過引號內文字。
