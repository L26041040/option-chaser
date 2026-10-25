# 瀏覽器儲存耐久性矩陣（Browser Storage Durability Matrix）研究

**issue #365**（`L26041040/option-chaser`，母票 **#359** Wayfinder map）。**本文只研究、不施工、不裁決**——`src/`／`api_app/` 零改動，未修改任何 GitHub issue。全部「存取日期」皆為 **2026-10-25**。

本文只回答這一個問題：Option Chaser 把**同一顆**匿名憑證存成兩份——(1) 伺服器簽的 HttpOnly `__Host-oc_owner` cookie（`Secure`、`SameSite=Lax`、`Max-Age` 400 天，簽一次就不再重簽）；(2) 瀏覽器本機副本（IndexedDB 為主、localStorage 鏡像，每個請求放在 `X-OC-Credential` header 帶上）——**在使用者沒有明確動手清除的情況下，每一份各自會在什麼條件下消失**。

**證據分級**（依每個結論標記）：

- 【Primary】——瀏覽器廠商官方文件、WebKit／Chromium／Mozilla 部落格與 bug tracker、瀏覽器原始碼、IETF 草案
- 【MDN】——MDN 條目。MDN 由 Mozilla 維護，講 **Firefox** 行為時視同 Mozilla 官方文件；講 Safari／Chrome 時只當佐證，不當唯一依據
- 【推論】——從 Primary 事實對 Option Chaser 現況做的推理，不是文件原文
- 【UNVERIFIED】——找不到 Primary 來源，或來源抓不到（HTTP 403／Client Challenge）。全部集中列在最後一節，正文中也會就地標記

---

## 給 Owner 看的白話摘要

這張票問的是：**使用者什麼都沒做，我們存在他瀏覽器裡的「身分」會不會自己不見**。身分存了兩份——一份是伺服器發的 cookie（JavaScript 碰不到），一份是網頁自己寫進瀏覽器資料庫（IndexedDB）並鏡像到 localStorage 的副本。兩份互相補回，任何一份還在，身分就不會掉。所以真正要回答的是：**有沒有哪種情況會「同時」吃掉兩份**，以及**每一份各自最弱的地方在哪**。

查完三家瀏覽器的第一手資料後，結論分四句：

1. **Safari 上，本機副本那一份很弱、cookie 那一份很強。** Safari 的 ITP 會在「使用者連續 7 個 Safari 使用日都沒有在我們網站上點過任何東西」之後，把網頁用 script 寫的所有東西（IndexedDB、localStorage 都在名單上）整個刪掉——**每個網站都適用，不是只有被判定為 tracker 的網站**。但伺服器用 `Set-Cookie` 發的 cookie 不在這條規則裡（WebKit 明文說 HttpOnly 的驗證 cookie 不受影響）。所以 Safari 使用者隔兩週回來，本機那份幾乎必定已經不在，是 cookie 把他認回來的。這正是「兩份」設計要保的情境，目前設計是對的。
2. **Chrome 上，cookie 那一份有一條硬期限：發出去之後 400 天。** Chrome 104 起任何 cookie 最多活 400 天；我們的 cookie **只簽一次、不重簽**，所以不管使用者多常來，第 400 天它一定到期。Chrome 官方的解法就是「使用者每次回來就用同名重設一次 cookie，期限就會重新起算」。Firefox 140 起也有同一條 400 天上限。這是目前設計裡**最值得補的一個小洞**，而且後端已經記著「上次簽發時間」，加一個「超過 N 天就重簽」的門檻是很小的改動。
3. **沒有任何「非使用者動作」會同時殺掉兩份。** 會一起消失的情境，全都是使用者自己設定或動手的：Chrome／Firefox 的「關閉所有視窗就清除 cookie 與網站資料」、Safari 的「Block All Cookies」（Apple 文件明說會立刻刪掉所有既有 cookie 與網站資料）、手動 Remove All Website Data、以及各家的私密瀏覽模式（關閉就清）。磁碟空間不足時 Chrome／Firefox／Safari 17 都會用「最久沒用的網站先刪」的方式清本機資料，但 cookie 另外存、不在這套 quota 系統裡，所以 cookie 那份會活下來。
4. **IndexedDB 真的有過「打開之後永遠不回應」的瀏覽器 bug**（Safari 14.1.1／iOS 14.6，Apple 在 iOS 14.7 修掉），而我們現在的程式**每個 API 請求都會先等 IndexedDB 回應才送出**，等待本身沒有時間上限（90 秒的 timeout 只管 fetch 本身）。在那種瀏覽器上，整個分頁的所有請求會永遠卡住、而且不會退回 localStorage。這類 bug 已修、受影響機器也越來越少，但加一個幾秒的 open timeout 再退回 localStorage 幾乎沒有成本，本文建議做。至於 `navigator.storage.persist()`，Chrome 對我們這種低互動網站幾乎一定靜默拒絕、Firefox 會跳一個使用者看不懂的權限提示、Safari 只對加到主畫面的 web app 放行——對目前的兩腿設計幫助很小，不建議現在做。

**本文推翻／複雜化的兩個直覺**：第一，很多第三方文章把 Safari 的 7 天上限寫成「7 天後 cookie 就沒了」——WebKit 原文的範圍是「**script 寫的**東西」：`document.cookie` 寫的 cookie、IndexedDB、localStorage 等，伺服器 `Set-Cookie` 發的 cookie 從 2019 年 ITP 2.1 起就明文排除。第二，「cookie 設 400 天就是 400 天內不會掉」只對「使用者這段期間都不回來」成立——真正的語義是「**從最後一次 Set-Cookie 起算** 400 天」，而我們目前從不重設，所以是「從第一次簽發起算」。

---

## 目前 Option Chaser 的起點（研究依據，非外部引用）

後面每一題的「對我們的意義」都回頭引用這裡的事實：

- **cookie 腿**：`api_app/main.py` 以 `response.set_cookie(_OWNER_COOKIE_NAME, token, max_age=_OWNER_COOKIE_MAX_AGE_SECONDS, httponly=True, secure=True, samesite="lax", path="/")` 簽發，`_OWNER_COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60`。**只在 `credential["issue"]` 為真時才簽**——即請求帶來的 cookie 對不上查到的 token（`token != cookie_token`）、或這顆憑證從未簽過 cookie（`resolved.cookie_issued_at is None`）。帶著有效 cookie 的正常請求**不會**收到 `Set-Cookie`（IDENTITY-FIX-002 的「簽一次、固定到期」）。簽發時間已經落庫：`_db().mark_owner_cookie_issued(token, now=...)`。
- **本機腿**：`src/credentialStore.ts`。IndexedDB（DB `oc-owner-bootstrap`、store `kv`、key `oc_owner_bootstrap`）為主，`localStorage` 同 key 為鏡像；`loadToken()` 在 `indexedDB` 存在時先走 `idbGetOrCreate()`，**拋錯**才退回 `localStorageGetOrCreate()`，再不行回 `null`（只剩 cookie）。`openDb()` 對 `onerror`／`onblocked` 會 reject，**沒有任何 timeout**；`credential()` 把第一次的 promise 記在模組變數 `loading` 裡，之後整個分頁共用這一個 promise。
- **請求路徑**：`src/api.ts` `send()` 第 827–833 行：`const known = loadedCredential(); const token = known !== undefined ? known : await credential();`，**然後才**建立 `AbortSignal.timeout(REQUEST_TIMEOUT_MS)`（90 000 ms）去 fetch。也就是：request timeout 只涵蓋網路，不涵蓋等 IndexedDB 的那一段。
- **互補機制**：伺服器依序用 cookie、再用 header 查；查到時 `issue`＝cookie 不在或對不上 → 補發 cookie；`echo`＝header 不在或對不上 → 回應以 `X-OC-Credential` 交回正確 token，前端 `storeCredential()` 存回 IndexedDB＋localStorage。任何一份還在，另一份下一個請求就補回。
- **部署形狀**：SPA 與 `/api/*` 由同一個 Vercel 專案、同一個 host 提供（CLAUDE.md 與 `docs/research/anonymous-identity-session-patterns.md` 已記錄的 `vercel.json` rewrite）——API 回應對瀏覽器來說是**同 host 的 first-party 子資源**，不是跨站、也不是另一個 CNAME 的子網域。這點在第 1.4 節（CNAME cloaking）會用到。

---

## 1. Safari／WebKit：ITP 的「7-Day Cap on All Script-Writeable Storage」

### 1.1 範圍：每個 first-party 網站都適用，不限 tracker-classified domain

這條規則經過三個版本，範圍一路放寬，要分開看：

- **ITP 2.1（2019-02-21，Safari 12.1／iOS 12.2 beta）**只管 `document.cookie`：「With ITP 2.1, all persistent client-side cookies, i.e. persistent cookies created through document.cookie, are capped to a seven day expiry」；「Only cookies created through document.cookie are affected by this change」；「The change covers cookies created in first-party contexts as well as in third-party iframes」（[WebKit Blog — Intelligent Tracking Prevention 2.1](https://webkit.org/blog/8613/intelligent-tracking-prevention-2-1/)，2026-10-25 存取）【Primary】。這一版就已經是**所有 first-party 網站**都適用，沒有 tracker 分類條件。
- **ITP 2.3（2019-09-23，Safari 13／iOS 13）**把 non-cookie 的 script 儲存也納入，但**有條件**：「website.example will be marked for non-cookie website data deletion if the user is navigated from a domain classified with cross-site tracking capabilities to a final URL with a query string and/or a fragment identifier」，然後「After seven days of Safari use without the user interacting with a webpage on website.example, all of website.example's non-cookie website data is deleted」（[WebKit Blog — Intelligent Tracking Prevention 2.3](https://webkit.org/blog/9521/intelligent-tracking-prevention-2-3/)，2026-10-25 存取）【Primary】。這一版的 IndexedDB／localStorage 刪除只在「從 tracker 帶 link decoration 跳過來」之後才會啟動。
- **2020-03-24（Safari 13.1／iOS 13.4）拿掉了那個條件**：「Now ITP has aligned the remaining script-writable storage forms with the existing client-side cookie restriction, deleting all of a website's script-writable storage after seven days of Safari use without user interaction on the site」（[WebKit Blog — Full Third-Party Cookie Blocking and More](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/)，2026-10-25 存取）【Primary】。原文沒有任何 classification 條件；WebKit 的 Tracking Prevention Policy 頁也用同樣無條件的寫法：「ITP deletes all cookies created in JavaScript and all other script-writeable storage after 7 days of no user interaction with the website」（[WebKit — Tracking Prevention in WebKit](https://webkit.org/tracking-prevention/)，2026-10-25 存取）【Primary】。

**結論**：自 Safari 13.1／iOS 13.4 起，7 天上限適用於**每一個** first-party 網站（Option Chaser 包含在內），不需要被判定為 tracker。這和 §1.5 的「30 天 tracker 清除」（只對 classified domain）是兩條不同的規則，不要混。

### 1.2 「7 天」是「7 天的 Safari 使用日」，不是日曆天

WebKit 原文一律寫 **「seven days of Safari use」**（[WebKit Blog 10218](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/)，2026-10-25 存取）；主畫面 web app 的那一段把「使用日計數器」講得更明白：「Web applications added to the home screen are not part of Safari and thus have their own counter of days of use. Their days of use will match actual use of the web application which resets the timer」（同上）【Primary】。Tracking Prevention Policy 頁對 30 天規則也用「in the last 30 days of browser use」（[WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/)，2026-10-25 存取）【Primary】。

什麼算「user interaction」：「User interaction is a user click, tap, or keyboard entry on a website」、「Scrolling is not considered user interaction」（同上）【Primary】。

**對我們的意義**【推論】：一個每天都用 Safari、但兩週才開一次 Option Chaser 的人，會在第二次回來之前剛好跨過 7 個使用日——本機腿**預期會被刪**。相反地，一個兩週不碰 Safari 的人，使用日計數器不動，本機腿還在。「什麼構成一個 Safari 使用日」WebKit 沒有正式定義（見 UNVERIFIED #1）。

### 1.3 刪的是什麼：IndexedDB 與 localStorage 都在名單上

被刪的「script-writable storage forms」WebKit 明列：「Indexed DB」、「LocalStorage」、「Media keys」、「SessionStorage」、「Service Worker registrations and cache」（[WebKit Blog 10218](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/)；[WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/)，皆 2026-10-25 存取）【Primary】。也就是 `credentialStore.ts` 的主儲存與鏡像**兩者同時**在名單上——本機腿的兩層在 Safari 上不是互相備援，是同一次刪除的對象。

### 1.4 伺服器 `Set-Cookie`（含 HttpOnly）不受 7 天上限影響——例外只有 CNAME cloaking

- ITP 2.1 原文直接回答了這題：「Cookies can either be set in HTTP responses or through the document.cookie API, the latter sometimes referred to as client-side cookies」，上限「Only cookies created through document.cookie are affected」，並特別點名驗證 cookie：「Cookies created through document.cookie cannot be HttpOnly which means authentication cookies should not be affected by the lifetime cap」——建議的做法就是在 HTTP 回應設定、加 `Secure` 與 `HttpOnly`（[WebKit Blog — ITP 2.1](https://webkit.org/blog/8613/intelligent-tracking-prevention-2-1/)，2026-10-25 存取）【Primary】。2020 年擴大到所有 script 儲存時，範圍定義仍是「script-writable」，HTTP 回應設的 cookie 不在定義內（[WebKit Blog 10218](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/)，2026-10-25 存取）【Primary】。MDN 的描述一致：「Cookies set by server are exempt from this eviction」（[MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)，頁面標示 2026-01-05 修訂，2026-10-25 存取）【MDN，佐證】。
- **唯一例外：third-party CNAME cloaking**。Safari 14／iOS 14（2020-11-12）起「ITP now detects third-party CNAME cloaking requests and caps the expiry of any cookies set in the HTTP response to 7 days」，判定條件是「a first-party subresource that resolves through a CNAME that differs from the first-party domain」且也不同於 top frame host 自己的 CNAME；原文**沒有**要求該 CNAME 目標被分類為 tracker，也沒有提到 HttpOnly 是否例外（[WebKit Blog — CNAME Cloaking and Bounce Tracking Defense](https://webkit.org/blog/11338/cname-cloaking-and-bounce-tracking-defense/)，2026-10-25 存取）【Primary】。Tracking Prevention 頁同樣寫「caps the expiry of any cookies set in the HTTP response to 7 days」（2026-10-25 存取）【Primary】。
- **對我們的意義**【推論】：我們的 `Set-Cookie` 來自與 top frame **同一個 host** 的 `/api/*` 回應，子資源的 CNAME 鏈與 top frame host 的 CNAME 鏈相同（同一個 host），不符合「differs from the top frame host's CNAME」——CNAME cloaking 規則**不**適用。這個推論成立的前提是 API 永遠與頁面同 host；若未來把 API 搬到另一個 CNAME 指向第三方的子網域（例如 `api.example` CNAME 到某 PaaS），就會踩到這條。

### 1.5 其他會刪掉 Safari 資料的機制

- **30 天 tracker 清除（含 HTTP cookie，但只對 classified domain）**：「All website data is deleted for classified domains」that「have not received user interaction as first-party」or「been granted storage access as third party through the Storage Access API」在「the last 30 days of browser use」之內（[WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/)，2026-10-25 存取）【Primary】；ITP 1.0 原文：「example.com website data and cookies are immediately purged」（[WebKit Blog — Intelligent Tracking Prevention](https://webkit.org/blog/7675/intelligent-tracking-prevention/)，2017-06-05，2026-10-25 存取）【Primary】。這是**唯一**會動到 HttpOnly cookie 的 ITP 規則，但前提是 domain 被 on-device 演算法判定有 cross-site tracking 能力。Option Chaser 不以第三方身分出現在別的網站上，理論上不會被分類（【推論】；分類是裝置端演算法，本文無法從外部確認，見 UNVERIFIED #3）。
- **Safari 17 的 quota／eviction（與 ITP 無關）**：2023-08-10 起「Starting in Safari 17.0, and in WebKit apps for iOS 17, iPadOS 17 and macOS Sonoma」，瀏覽器 app 每個 origin quota「up to 60% of the total disk space」、整體「up to 80%」；「Eviction means automatic website data deletion that is not initiated by the user or website」，觸發條件列了超過整體 quota、系統儲存壓力、長期無使用者互動三種；「WebKit normally evicts data on an origin basis: the data of an origin will be deleted as a whole」、「The ordering of origins to be deleted is decided using a least-recently-used policy」、「Origin might be excluded from eviction if it has active page at the time of eviction, or its storage is in persistent mode」、「By default, all origins use a best-effort mode」（[WebKit Blog — Updates to Storage Policy](https://webkit.org/blog/14403/updates-to-storage-policy/)，2026-10-25 存取）【Primary】。這套 eviction 管的是 website data（IndexedDB 等），cookie 由 CFNetwork 另外保管、不在此列（【推論】，WebKit 原文沒逐字排除 cookie）。
- **`navigator.storage.persist()` 在 Safari**：同一篇寫「WebKit currently grants a request based on heuristics like whether the website is opened as a Home Screen Web App」（同上）【Primary】；web.dev 標示 Safari 15.2 起支援此 API（[web.dev — Persistent storage](https://web.dev/articles/persistent-storage)，2026-10-25 存取）【Primary，Google 文件】。對一般 Safari 分頁裡的 Option Chaser 等於拿不到。

### 1.6 iOS vs macOS

- **規則本身一致**：Tracking Prevention 頁把預設 cookie 政策套用到「iOS, macOS, iPadOS, tvOS, and watchOS」，沒有描述任何 iOS／macOS 在 7 天或 30 天規則上的差異（[WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/)，2026-10-25 存取）【Primary】。
- **主畫面 web app 豁免（iOS；macOS Sonoma 的 Dock web app 共用同一套 quota）**：「the first-party domain is exempt from ITP's 7-day cap on all script-writeable storage」、資料「is kept isolated from Safari」（同上）；Storage Policy 一文把「Home Screen Web App on iOS or Web App added to dock on macOS」並列（[WebKit Blog 14403](https://webkit.org/blog/14403/updates-to-storage-policy/)，2026-10-25 存取）【Primary】。對我們：只有「加到主畫面」的使用者在 Safari 上保得住本機腿。
- **iOS 上的第三方瀏覽器也在 ITP 底下**：App Store 審查指南 2.5.6「Apps that browse the web must use the appropriate WebKit framework and WebKit JavaScript. You may apply for an entitlement to use an alternative web browser engine in your app」（EU 與日本可申請例外）（[App Store Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)，2026-10-25 存取）【Primary】；WWDC20「Discover WKWebView enhancements」逐字稿：「in iOS 14 and macOS Big Sur, ITP is enabled by default on all WKWebView apps」（[WWDC20 session 10188](https://developer.apple.com/videos/play/wwdc2020/10188/)，2026-10-25 存取）【Primary】。所以 iOS 上的 Chrome／Firefox 使用者**也**處在 ITP 之下；7 天上限是否在 WKWebView 中逐條生效，WebKit 文件沒有單獨說明（UNVERIFIED #2）。
- **CNAME cloaking 防禦在 macOS 上限 Big Sur**：「this enhancement is specific to Big Sur」（[WebKit Blog 11338](https://webkit.org/blog/11338/cname-cloaking-and-bounce-tracking-defense/)，2026-10-25 存取）【Primary】——對我們不適用（§1.4），僅記錄。
- **Safari private browsing**：IndexedDB 與 localStorage 都是記憶體後端，見 §4.2。

---

## 2. Chromium

### 2.1 400 天 cookie 上限（M104+），重設同名 cookie 會重新計時

- **規範**：draft-ietf-httpbis-rfc6265bis-22（2025-12-01）§5.5：「The limit SHOULD NOT be greater than 400 days (34560000 seconds) in the future」，指定更長壽命的屬性「MUST be reduced to the limit」；Max-Age 與 Expires 的處理步驟各自註記「(which SHOULD be 400 days or less, see Section 5.5)」（[draft-ietf-httpbis-rfc6265bis](https://datatracker.ietf.org/doc/html/draft-ietf-httpbis-rfc6265bis)，2026-10-25 存取）【Primary，IETF 草案】。
- **Chrome 實作**：Chrome Platform Status「Cookie Expires/Max-Age attribute upper limit」：「the value will now be capped to no more than 400 days in the future」，shipped **desktop 104、Android 104**（[chromestatus.com/feature/4887741241229312](https://chromestatus.com/feature/4887741241229312)，2026-10-25 存取）【Primary】。Chrome 官方部落格：「As of Chrome release M104 (August 2022) cookies can no longer set an expiration date more than 400 days in the future」（[Chrome Developers — Cookie Expires and Max-Age attributes now have upper limit](https://developer.chrome.com/blog/cookie-max-age-expires)，頁面標示 2023-01-12 更新，2026-10-25 存取）【Primary】。
- **重設同名 cookie 會不會重新計時——會**。Chrome 部落格明說：「Developers have the ability to extend the expiration any time the user visits the site again: by setting a new cookie with the same name」（同上）【Primary】。規範層面，§5.7 Storage Model 規定遇到同 name／domain／host-only-flag／path 的既有 cookie 時：若新 cookie 來自非 HTTP API 而舊 cookie 是 http-only 就忽略新 cookie；否則把舊 cookie 的 creation-time 複製給新 cookie、移除舊 cookie、插入新 cookie（[draft-ietf-httpbis-rfc6265bis §5.7](https://datatracker.ietf.org/doc/html/draft-ietf-httpbis-rfc6265bis)，2026-10-25 存取）【Primary】——保留的是 creation-time，**expiry-time 以新的 Set-Cookie 重算**。
- **回溯套用（M118）**：blink-dev「Intent to Prototype & Ship: Cookie Expires/Max-Age attribute upper limit for prior storage」（2023-08-01）：「This same limit will now be retroactively applied to cookies already in storage」，既有超長 cookie 的到期被設成 M118 首次啟動並完成一次性 migration 之後 400 天（[blink-dev thread](https://groups.google.com/a/chromium.org/g/blink-dev/c/blQFS8L3Drw)，2026-10-25 存取）【Primary】。
- **對我們的意義**【推論】：我們的 cookie 只在「cookie 不在／對不上／從未簽過」時簽一次，之後**永不重設**。所以在 Chrome 104+（以及 §3.4 的 Firefox 140+）上，cookie 腿的壽命就是「第一次簽發起 400 天」，與使用者多常回來無關。同一段時間裡本機腿若也被清掉（例如使用者換了設定、或 Safari 的 7 天規則——不過 Safari 是另一題），身分就掉了。Chrome 官方給的解法就是回訪時重設。

### 2.2 cookie jar 本身的數量上限（另一種會吃掉 cookie 腿的驅逐）

- 規範 §6.1：一般用途的 user agent「SHOULD」提供「At least 50 cookies per domain」、「At least 3000 cookies total」，並「may evict any cookie at any time (whether at the request of the user or due to implementation limitations)」；§5.7 超量時的驅逐順序：先過期的、再非 secure 且同 domain 超過上限的、再同 domain 超過上限的、最後所有 cookie，同一優先級內「MUST evict the cookie with the earliest last-access-time first」（[draft-ietf-httpbis-rfc6265bis](https://datatracker.ietf.org/doc/html/draft-ietf-httpbis-rfc6265bis)，2026-10-25 存取）【Primary】。
- Chromium 實際常數（`net/cookies/cookie_monster.cc`）：`kDomainMaxCookies = 180`、`kDomainPurgeCookies = 30`、`kMaxCookies = 3300`、`kPurgeCookies = 300`、`kSafeFromGlobalPurgeDays = 30`；每 domain 的清理依 priority 分六輪（low non-secure → low secure → medium non-secure → high non-secure → medium secure → high secure），每輪內依最久未存取先刪（`LRACookieSorter`）；全域清理「we want to preserve cookies accessed in kSafeFromGlobalPurgeDays, otherwise evict」（[chromium/chromium `net/cookies/cookie_monster.cc`（GitHub mirror）](https://raw.githubusercontent.com/chromium/chromium/main/net/cookies/cookie_monster.cc)，2026-10-25 存取）【Primary，原始碼】。
- **對我們的意義**【推論】：我們只設一顆 cookie，單靠自己碰不到 180 顆。但「同一個 key（registrable domain）下的 cookie 數」是共用的——若同 host 上未來加了會大量寫 cookie 的第三方 script，我們這顆 `Secure` 且 30 天內有存取的 cookie 會排在最後一輪才被動到，風險低但不是零。

### 2.3 儲存壓力下的 LRU 驅逐（吃掉本機腿、不碰 cookie）

- **觸發與順序**：「Chromium-based browsers will begin to evict data when the browser runs out of space, clearing all site data from the least recently used origin first, then the next, until the browser is no longer over the limit」；quota「Chrome allows the browser to use up to 80% of total disk space. An origin can use up to 60% of the total disk space」；超過 quota 時「further attempts to write data will fail」、IndexedDB 丟 `QuotaExceededError`（[web.dev — Storage for the web](https://web.dev/articles/storage-for-the-web)，Pete LePage，頁面標示 2024-09-23 更新，2026-10-25 存取）【Primary，Google 文件】。
- **原始碼裡的門檻**（`storage/browser/quota/quota_settings.cc` 與 `quota_features.cc`）：`PoolSizeRatio` 預設 `0.8`；`kDefaultPerStorageKeyRatio = 0.75`（0.8 × 0.75 ＝ 60% disk，與上面一致）；「should remain available」＝ min(2 GB, 10%)：「If there is less than this amount of storage free on the device, Chrome will grant 0 quota to origins」；「must remain available」＝ min(1 GB, 1%)：「The amount of the device's storage the browser attempts to keep free at all costs. Data will be aggressively evicted」（[`quota_settings.cc`](https://raw.githubusercontent.com/chromium/chromium/main/storage/browser/quota/quota_settings.cc)；[`quota_features.cc`](https://raw.githubusercontent.com/chromium/chromium/main/storage/browser/quota/quota_features.cc)，2026-10-25 存取）【Primary，原始碼】。
- **範圍是「整個 origin 的 site data」**，而 cookie 不在這套系統裡：MDN 說明這套 storage management 管的是「IndexedDB, Cache API, or File System API」等，並明寫「Because cookies should not be used for storing data in the browser, cookie storage browser limits are not covered here」（[MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)，2026-10-25 存取）【MDN】；Chromium 的 cookie 上限是 §2.2 那套獨立的 CookieMonster 規則【Primary】。
- **這種驅逐有多常見**：Google 自己的說法是「data is very rarely cleared automatically by Chrome. It is far more common for users to manually clear storage」（[web.dev — Persistent storage](https://web.dev/articles/persistent-storage)，2026-10-25 存取）【Primary，Google 文件】。
- **localStorage 是否同在 quota eviction 之內**：MDN 只給 Web Storage 自己的固定上限（「limited to 10 MiB of data maximum on all browsers」），沒有明說 localStorage 是否隨 origin 一起被 quota eviction 清掉（同上 MDN）；web.dev 寫的是「clearing **all site data** from the least recently used origin」【Primary】。本文採「all site data」的字面（含 localStorage），但標記為 UNVERIFIED #6。

### 2.4 `navigator.storage.persist()`：不提示、靜默依 heuristics 決定

- **官方描述**：Chrome「automatically handle the permission request, and do not show any prompts to the user」；依據是「How high is the level of site engagement?」、「Has the site been installed or bookmarked?」、「Has the site been granted permission to show notifications?」；拒絕不會被記住，「it can be requested again later and will be evaluated using the same heuristics」；一旦 persistent，「the browser won't evict data」、「It's only deleted if the user chooses to remove it using their site settings」（[web.dev — Persistent storage](https://web.dev/articles/persistent-storage)，2020-05-12，2026-10-25 存取）【Primary，Google 文件】。
- **原始碼裡的實際條件**（`chrome/browser/storage/persistent_storage_permission_context.cc`）：只授予 top-level origin（「Durable is only allowed to be granted to the top-level origin」）；「Don't grant durable for session-only storage, since it won't be persisted」；「Don't grant durable if we can't write cookies」；registrable domain 在已安裝 web app 清單中、或在「important sites」前 `kMaxImportantResults = 10` 名之內才 `kAllow`，其餘 `kNone` 且不持久化；整個 `DecidePermission` 沒有任何 prompt 路徑（[`persistent_storage_permission_context.cc`](https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/storage/persistent_storage_permission_context.cc)，2026-10-25 存取）【Primary，原始碼】。「important sites」的定義（`chrome/browser/engagement/important_sites_util.cc`）：site engagement 至少 `MEDIUM`；`NOTIFICATIONS` 已允許；`installed_bonus > 0`（HOME_SCREEN）；書籤——「These are the maximum # of bookmarks we can use as signals」、`static const int kMaxBookmarks = 5`（書籤超過 5 個時，依 engagement 排序只取前 5）；既有 `PERSISTENT_STORAGE` 權限（[`important_sites_util.cc`](https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/engagement/important_sites_util.cc)，2026-10-25 存取）【Primary，原始碼】。
- **對我們的意義**【推論】：一個偶爾造訪、沒加書籤、沒安裝、沒開通知的匿名使用者，`persist()` 幾乎必定被靜默拒絕。而且「session-only storage 不授予」那一條意味著：使用者若開了 §5.1 的「關閉所有視窗就刪除」，`persist()` 同樣拿不到——它救不了那個情境。

### 2.5 Android Chrome

- 400 天上限 Android 與 desktop 同為 M104（[chromestatus](https://chromestatus.com/feature/4887741241229312)，2026-10-25 存取）【Primary】。
- `important_sites_util.cc` 與 `persistent_storage_permission_context.cc` 皆無 `#if BUILDFLAG(IS_ANDROID)` 分支（兩檔原始碼，2026-10-25 存取）【Primary】——persist 的 heuristics 桌面／Android 一致（Android 的「加到主畫面」走同一個 `installed_bonus`／HOME_SCREEN 訊號）。
- Android OS 層的「清除應用程式儲存空間」、系統儲存空間不足時對 Chrome 資料的影響：本次未查到 Primary 來源（UNVERIFIED #7）。

### 2.6 Incognito、與「被封鎖」時 IndexedDB／localStorage 的行為（都是錯誤、不是卡住）

- **Incognito**：Chrome Help——cookie 與 site data 在 session 期間暫存，「This information is removed when the Incognito session ends」、「Your Incognito session ends when you close all Incognito windows」（[Chrome Help — Browse in private](https://support.google.com/chrome/answer/95464)，2026-10-25 存取）【Primary】。Incognito 的 quota pool 是系統記憶體的一部分：`kIncognitoQuotaRatioLowerBound = 0.15`、`kIncognitoQuotaRatioUpperBound = 0.2`（「The incognito pool size is a fraction of the amount of system memory」），每個 storage key 取 pool 的三分之一（[`quota_settings.cc`](https://raw.githubusercontent.com/chromium/chromium/main/storage/browser/quota/quota_settings.cc)，2026-10-25 存取）【Primary，原始碼】。web.dev 寫的「approximately 5% of the total disk space」與原始碼不一致，以原始碼為準（UNVERIFIED #8 記錄這個差異）。
- **使用者封鎖該站儲存時，IndexedDB 怎麼失敗**（`third_party/blink/renderer/modules/indexeddb/idb_factory.cc`）：`open()` 先同步檢查 `CanAccessDatabase()`，不通過就**同步丟** `SecurityError`「access to the Indexed Database API is denied in this context.」（opaque origin／sandbox）；若是使用者層級的權限拒絕，`open()` 正常回傳 `IDBOpenDBRequest`，稍後**非同步**以 `UnknownError` DOMException「The user denied permission to access the database.」觸發 request 的 error（[`idb_factory.cc`](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/modules/indexeddb/idb_factory.cc)，2026-10-25 存取）【Primary，原始碼】。
- **localStorage 被封鎖時**（`third_party/blink/renderer/modules/storage/dom_window_storage.cc`）：getter 檢查 `CanAccessStorage()`，不通過就 `ThrowSecurityError(StorageArea::kAccessDeniedMessage)`；sandbox 走 `kAccessSandboxedMessage`、`data:` URL 走 `kAccessDataMessage`；另有兩個路徑直接回 `nullptr`（`GetLocalStorageEnabled()` 為假、或 `IsDomStorageDisabled()`）（[`dom_window_storage.cc`](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/modules/storage/dom_window_storage.cc)，2026-10-25 存取）【Primary，原始碼】。
- **對我們的意義**【推論】：Chromium 的所有「不可用」路徑都是**同步丟錯或非同步 error event**，`credentialStore.ts` 的 `openDb()`（`onerror` → reject）與 `localStorage` 的 try/catch 都能接到；沒有查到 Chromium 有「`open()` 永不回應」的已知情境。

---

## 3. Firefox

### 3.1 quota 與驅逐（吃掉本機腿、不碰 cookie）

- best-effort 模式下每個 origin 的上限是「10% of the total disk size where the profile of the user is stored」與「10 GiB, which is the group limit that Firefox applies to all origins that are part of the same site」取小者；persistent 模式「can store up to 50% of the total disk size, capped at 8 TiB, and are not subject to the group limit」；驅逐採 LRU：「The data from the least recently used origin is deleted. If storage pressure continues, the browser moves on to the second least recently used origin」（[MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)，2026-01-05 修訂，2026-10-25 存取）【MDN＝Mozilla 文件】。web.dev 的描述一致：「Firefox will begin to evict data when the available disk space is filled up, clearing all site data from the least recently used origin first」（[web.dev — Storage for the web](https://web.dev/articles/storage-for-the-web)，2026-10-25 存取）【Primary，Google 文件】。
- 和 Chromium 一樣，cookie 不在這套 quota 系統裡（MDN 同頁「cookie storage browser limits are not covered here」）【MDN】。

### 3.2 `persist()` 會跳提示（Firefox 是三家裡唯一會問使用者的）

- 文件：「In Firefox, when a site chooses to use persistent storage, the user is notified with a UI popup that their permission is requested」（[MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)，2026-10-25 存取）【MDN＝Mozilla 文件】；web.dev：「Firefox delegates the permission request to the user」、「it prompts the user with a UI popup asking if they will allow the site to store data in persistent storage」（[web.dev — Persistent storage](https://web.dev/articles/persistent-storage)，2026-10-25 存取）【Primary，Google 文件】。
- 原始碼：`dom/quota/StorageManager.cpp` 的 persist 請求以 `"persistent-storage"` 權限走 `nsContentPermissionUtils::AskPermission(this, mWindow)`；private browsing 直接取消、不提示（「// In private browsing mode, no permission prompt.」→ `request->Cancel()`），失敗一律 resolve 成 `false` 而非 reject（[`StorageManager.cpp`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/dom/quota/StorageManager.cpp)，2026-10-25 存取）【Primary，原始碼】。前端 `browser/modules/PermissionUI.sys.mjs` 的 `PersistentStoragePermissionPrompt`：`permissionKey` 為 `"persistent-storage"`、訊息字串 `persistentStorage.allowWithSite2`、`requiresUserInput` 沿用基底預設 `false`（基底註解：「If true, the prompt will be cancelled automatically unless request.hasValidTransientUserGestureActivation is true」——也就是 persist 的提示**不需要**使用者手勢就會跳出來）、動作為 Allow（`SCOPE_PERSISTENT`）／Block，非 private 視窗附「記住」勾選（[`PermissionUI.sys.mjs`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/modules/PermissionUI.sys.mjs)，2026-10-25 存取）【Primary，原始碼】。提示文字：`persistentStorage.allowWithSite2=Allow %S to store data in persistent storage?`、按鈕 `Allow`／`Block`（[`browser.properties`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/locales/en-US/chrome/browser/browser.properties)，2026-10-25 存取）【Primary，原始碼】。此提示自 Firefox 55 存在（[Bugzilla 1309123 — Show persistent-storage permission request notification](https://bugzilla.mozilla.org/show_bug.cgi?id=1309123)，RESOLVED FIXED，target Firefox 55，2026-10-25 存取）【Primary】。

### 3.3 Redirect tracking protection 只清 tracker、不清一般 first-party

Firefox 的 redirect tracking protection 會清掉一個 origin 的 cookie 與「DOM Quota Storage (localStorage, IndexedDB, ServiceWorkers, DOM Cache, etc.)」等，但**三個條件須同時成立**：(1) 72 小時內存過 cookie 或動過 storage；(2)「The origin is classified as a tracker in our Tracking Protection list」；(3) 同一 registrable domain 下沒有任何 origin 持有 user-interaction 權限（「granted to an origin for 45 days once a user interacts with a top-level document from that origin. 'Interacting' includes scrolling」）；且只在 `network.cookie.cookieBehavior` 為 4 或 5 時運作（[MDN — Redirect tracking protection](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Redirect_tracking_protection)，2026-01-05 修訂，2026-10-25 存取）【MDN＝Mozilla 文件】。Option Chaser 不在 Tracking Protection 名單上（【推論】），條件 (2) 不成立，不受影響。

### 3.4 Firefox 也有 400 天上限了（140 起，含 Max-Age）

- Mozilla 的標準立場：mozilla/standards-positions #592 標籤「position: positive」（2024-10-18 加上）；annevk 2021-11-11 留言「having a limit here seems reasonable to us」（[mozilla/standards-positions#592](https://github.com/mozilla/standards-positions/issues/592)，2026-10-25 存取）【Primary】。
- 實作：Bugzilla 1964943「Reduce to 400-days the max-age attribute value」，RESOLVED FIXED，Target Milestone **140 Branch**，描述（2025-05-07）：「We do it for the `expires` but not the `max-age` attribute values」，2025-05-08 併入 mozilla-central（rev `76d772b34ddb`）（[Bugzilla 1964943](https://bugzilla.mozilla.org/show_bug.cgi?id=1964943)，2026-10-25 存取）【Primary】；同系列 Bugzilla 1962986「Reduce the expiry attribute value to max 400 days in CookieStore API」（140 Branch）、1973024「Implement nsICookieManager::maybeCapExpiry」（142 Branch）、1974394（WebDriver 也套同一上限，142 Branch）（各自 Bugzilla 頁，2026-10-25 存取）【Primary】。Firefox 140 發布日 2025-06-24（[MDN — Firefox 140 for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/140)，2026-10-25 存取）【MDN】。
- 1964943 的描述證實 `Expires` 在這之前就已經被上限了，但本次沒找到那條 `Expires` 上限的原始 bug（UNVERIFIED #4）。對我們而言兩者等價：我們用 `Max-Age`（Starlette `set_cookie(max_age=...)` 同時輸出 `Max-Age` 與 `expires`），**Firefox 140+ 與 Chrome 104+ 都會把它鎖在 400 天**。
- 重設同名 cookie 是否重新計時：規範層面同 §2.1（Storage Model）【Primary】；Firefox 是否完全依規範實作重算 expiry，本次未查原始碼（UNVERIFIED #5），但沒有理由認為會偏離。

### 3.5 Private window：115 之前 IndexedDB 直接報錯，115 起可用（不會 hang）

- 115 之前：Bugzilla 781982「IndexedDB does not function in private browsing mode」——回報的錯誤是 `InvalidStateError`「A mutation operation was attempted on a database that did not allow mutations」；留言對「同步丟錯」還是「`onerror` 事件」說法不一（comment 27：「throws an uncatchable error, and doesn't fire the request's onerror」；comment 31：`onerror` 收到 `InvalidStateError`），但**沒有任何回報說它會卡住不回應**（[Bugzilla 781982](https://bugzilla.mozilla.org/show_bug.cgi?id=781982)；[Bugzilla 1639542（meta）](https://bugzilla.mozilla.org/show_bug.cgi?id=1639542)，2026-10-25 存取）【Primary】。
- 115 起：Firefox 115.0 release notes（2023-07-04）：「IndexedDB is now also supported in private browsing without memory limits thanks to encrypted storage on disk」（[Firefox 115.0 Release Notes](https://www.firefox.com/en-US/firefox/115.0/releasenotes/)，2026-10-25 存取）【Primary】；session 結束時清除由 Bugzilla 1639548「Purge private browsing mode storage on private browsing mode session end」處理（RESOLVED FIXED，見 1639542 meta 頁）【Primary】。
- **對我們的意義**【推論】：Firefox < 115 的 private window 會讓 `openDb()` reject（或同步丟錯——兩者 `loadToken()` 的 try/catch 都接得到）→ 退回 localStorage；Firefox ≥ 115 正常可用，但關掉 private session 就全清（cookie 也是 session 性質）——這是「兩腿同時消失」的使用者選擇情境之一。

---

## 4. IndexedDB 不可用／卡死：哪些 THROW、哪些 HANG

這一題直接決定 `credentialStore.ts` 的 `credential()` 要不要加 timeout 退路。

### 4.1 真正會 HANG 的：Safari 14.1.1（macOS 11.4）／iOS 14.6

WebKit Bugzilla 226547「indexedDB.open() sometimes hangs forever in pending state on first page load in iOS 14.6」（2021-06-02 回報）：頁面第一個 `indexedDB.open()` 的 request 永遠停在 `pending`，**success／error／blocked 三個事件都不會觸發**；重新整理就好了；Apple 工程師 Sihui Liu 說明原因「some IndexedDB messages are received in another process (network process) before it is ready」，修正「was shipped in iOS 14.7 beta 4」（comment 50；bug 標為 224623 的 duplicate）；另有一則回報 iOS 14.7.1 仍遇到，WebKit 要求另開新 bug（[WebKit Bugzilla 226547](https://bugs.webkit.org/show_bug.cgi?id=226547)，2026-10-25 存取）【Primary】。社群的 workaround 套件 README 記錄「fixed in Safari 14.7」（[jakearchibald/safari-14-idb-fix](https://github.com/jakearchibald/safari-14-idb-fix)，2026-10-25 存取；此為第三方，只作症狀佐證）。

**對我們的意義**【推論】：這是**唯一**查到的「`open()` 永不回應」Primary 證據。在這種裝置上，`openDb()` 的 promise 永遠 pending → `idbGetOrCreate()` 永不 settle → **不會**退回 localStorage（退路只在拋錯時啟動）→ `credential()` 把這顆 pending promise 存進 `loading` → `send()` 第 828 行 `await credential()` 永遠不回來 → **該分頁所有 API 請求都送不出去**，而 `REQUEST_TIMEOUT_MS` 完全管不到（它包的是 fetch）。受影響版本已由 Apple 修正，但這個失效模式與「IndexedDB 任何一次 open 慢到不可接受」是同一類，見本節 4.4。

### 4.2 報錯（不 hang）的情境

| 情境 | 行為 | 來源 |
|---|---|---|
| Safari private browsing（現代 WebKit） | IndexedDB **可用**，走記憶體後端：2016 年 Modern IDB 把 ephemeral session 的 backing store 換成 `MemoryIDBBackingStore`（`IDBServer::createBackingStore` 二選一：`MemoryIDBBackingStore::create` vs `SQLiteIDBBackingStore`），WebKit 工程師確認「the -private.html versions are using the in-memory backing store, and are also passing」；WebKit 至今維護整組 `LayoutTests/imported/w3c/IndexedDB-private-browsing/` 測試 | [WebKit changeset 199230](https://trac.webkit.org/changeset/199230/webkit)（2016-04-08）；[WebKit Bugzilla 153323](https://bugs.webkit.org/show_bug.cgi?id=153323)（comment 2016-02-02）；[WebKit/WebKit `LayoutTests/imported/w3c/IndexedDB-private-browsing`](https://github.com/WebKit/WebKit/tree/main/LayoutTests/imported/w3c/IndexedDB-private-browsing)，皆 2026-10-25 存取【Primary】。首次出貨的 Safari 版本未查到（UNVERIFIED #9） |
| Safari private browsing：存 Blob | iOS 12.3.1 private 模式存 Blob 失敗（`DataCloneError`「BlobURLs are not yet supported」），已修 | [WebKit Bugzilla 198278](https://bugs.webkit.org/show_bug.cgi?id=198278)，2026-10-25 存取【Primary】。我們只存字串，不受影響 |
| Safari private browsing：`indexedDB.databases()` | 2021-07-28 之前在 private 模式回空陣列（「no databases are returned in private browsing (since there is no file created)」），已修 | [WebKit changeset 280410](https://trac.webkit.org/changeset/280410/webkit)（bug 228554），2026-10-25 存取【Primary】。與 safari-14-idb-fix 那類「先呼叫 `databases()` 探測」的 workaround 有關 |
| Safari private browsing：localStorage | 舊版 `setItem` 丟 `QuotaExceededError`（WebKit Bugzilla 157010，2016-04-25 回報），2017-04-12 以 r215315 改為 ephemeral session 走記憶體；出貨版本未明（有人回報 Safari 10.1.2 仍受影響） | [WebKit Bugzilla 157010](https://bugs.webkit.org/show_bug.cgi?id=157010)，2026-10-25 存取【Primary】。`mirrorToLocalStorage()`／`localStorageGetOrCreate()` 的 try/catch 已涵蓋（UNVERIFIED #9 一併記出貨版本） |
| iOS 17.4／17.5（部分 18.x） | `open()` 以 error 失敗：「UnknownError: Connection to Indexed Database server lost. Refresh the page to try again.」；Apple（Brady Eidson）說是 Networking process crash；reload 無效、要重開機；Apple 2024-07-25 表示 iOS 17.6／18 beta 已由「an OS change outside WebKit」修正；2025-10 仍有新回報 | [WebKit Bugzilla 273827](https://bugs.webkit.org/show_bug.cgi?id=273827)（RESOLVED CONFIGURATION CHANGED），2026-10-25 存取【Primary】。**是 error event，不是 hang** → `openDb()` reject → 退回 localStorage |
| Firefox < 115 private window | `InvalidStateError`（同步丟錯或 `onerror`，說法不一），不 hang | §3.5【Primary】 |
| Chromium：使用者封鎖該站 | 非同步 `UnknownError`「The user denied permission to access the database.」 | §2.6【Primary，原始碼】 |
| Chromium：opaque origin／sandbox | 同步 `SecurityError`「access to the Indexed Database API is denied in this context.」 | §2.6【Primary，原始碼】 |
| Chromium Incognito | 可用，記憶體 pool，關閉所有 Incognito 視窗即清 | §2.6【Primary】 |

### 4.3 交易層面的長時間阻塞（不是 open hang，但對 `inTransaction()` 有意義）

Safari Technology Preview 248（2026-07-22）release notes：「Fixed an issue where IndexedDB transactions could be blocked for an extended period before starting when another page's transaction was suspended in the background」（bug 178769599，commit 315609@main）（[WebKit Blog — Release Notes for Safari Technology Preview 248](https://webkit.org/blog/18162/release-notes-for-safari-technology-preview-248/)，2026-10-25 存取）【Primary】。`credentialStore.ts` 刻意把「讀→產生→寫」放在**單一 readwrite transaction** 裡換取跨分頁原子性；在這個 bug 修正前的 Safari 上，另一個分頁掛起中的 transaction 可以讓我們的 transaction「extended period」才開始——`inTransaction()` 的 promise 同樣沒有 timeout。

### 4.4 對 `credential()` 的意義【推論】

- **會 hang 的 Primary 證據只有一例（Safari 14.6／14.1.1），且已修正**；其他所有「不可用」情境都是同步丟錯或 error event，現有 try/catch＋localStorage 退路已能接住。
- 但現有程式把「IndexedDB 永不回應」放大成「整個分頁所有 API 請求永遠送不出」，而且因為 `loading` 記住了那顆 pending promise，連重試都沒有——這與「任何一份還在身分就不會掉」的設計初衷相反：cookie 明明在，請求卻送不出去。
- 加 timeout 的代價是：超時後退回 localStorage 產生／讀取 token，而 IndexedDB 那份可能稍後才回應——`credentialStore.ts` 檔頭已經規定「以 localStorage 為準、把 IndexedDB 對齊過去」，這條既有規則剛好能吸收 timeout 造成的雙邊不一致。詳見「意涵」一節。

---

## 5. 使用者層級設定：關閉視窗就清除——清的是 cookie、site data、還是兩者

### 5.1 Chrome：兩者

Chrome 現在把這個設定放在「On-device site data」：三個選項「Allow sites to save data on your device」／「**Delete data sites have saved to your device when you close all windows**」（說明「Sites will probably work as you expect but are less likely to remember you from one visit to the next」）／「Don't allow sites to save data on your device (not recommended)」；路徑 Settings → Privacy and security → Site settings → Additional content settings → On-device site data（[Chrome Help — Learn about on-device site data in Chrome](https://support.google.com/chrome/answer/14114868)，2026-10-25 存取）【Primary】。Google 的頁面沒有逐項列出「site data」包含哪些技術；Chromium 原始碼把這個狀態視為「session-only storage」並以 `IsCookieSessionOnly()` 檢查（「Don't grant durable for session-only storage, since it won't be persisted」，[`persistent_storage_permission_context.cc`](https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/storage/persistent_storage_permission_context.cc)，2026-10-25 存取）【Primary，原始碼】；web.dev 另提到開啟此設定時 Chrome 把 quota 降到約 300 MB（[web.dev — Storage for the web](https://web.dev/articles/storage-for-the-web)，2026-10-25 存取）【Primary，Google 文件】。本文結論：**cookie 與 site data（含 IndexedDB／localStorage）一起清**——選項名稱與原始碼都指向「整組 site data」；逐項清單的 Primary 列舉見 UNVERIFIED #10。第三個選項「Don't allow」等於 §2.6 的「被封鎖」路徑：IndexedDB 非同步 `UnknownError`、localStorage 同步 `SecurityError`。

### 5.2 Firefox：兩者（並尊重例外清單）

- 設定字串（`browser/locales/en-US/browser/preferences/preferences.ftl`）：`sitedata-delete-on-close2` `.label = Clear cookies and site data every time you close { -brand-short-name }`；說明 `sitedata-delete-on-close-private-browsing3` `.message = Based on your history settings, { -brand-short-name } deletes cookies and site data from your session when you close the browser.`；例外按鈕 `sitedata-cookies-exceptions` `.label = Manage Exceptions…`（[`preferences.ftl`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/locales/en-US/browser/preferences/preferences.ftl)，2026-10-25 存取）【Primary，原始碼】。
- 清什麼：`browser/modules/Sanitizer.sys.mjs` 的 `cookiesAndStorage` 項目呼叫 `CLEAR_COOKIES_AND_SITE_DATA`；關機路徑逐 principal 清除——「On shutdown we clear by principal to be able to honor the users exceptions」，持有 `persist-data-on-shutdown` ALLOW 權限的站點保留（[`Sanitizer.sys.mjs`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/browser/modules/Sanitizer.sys.mjs)，2026-10-25 存取）【Primary，原始碼】。`CLEAR_COOKIES_AND_SITE_DATA = CLEAR_COOKIES | CLEAR_DOM_STORAGES | CLEAR_HSTS | CLEAR_EME | CLEAR_AUTH_TOKENS | CLEAR_AUTH_CACHE | CLEAR_FINGERPRINTING_PROTECTION_STATE | CLEAR_BOUNCE_TRACKING_PROTECTION_STATE | CLEAR_STORAGE_PERMISSIONS | CLEAR_MESSAGING_LAYER_SECURITY_STATE | CLEAR_TLS_TOKEN_CACHE`，註解「This flag groups state that we consider site data from the user perspective」、「This flag does not clear caches」；`CLEAR_DOM_STORAGES` 的註解「LocalStorage, IndexedDB, ServiceWorkers, DOM Cache and so on」（[`nsIClearDataService.idl`](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/toolkit/components/cleardata/nsIClearDataService.idl)，2026-10-25 存取）【Primary，原始碼】。
- Mozilla 支援中心的對應頁面本次抓取被「Client Challenge」擋下（UNVERIFIED #11），上面以原始碼字串代替。

### 5.3 Safari：沒有「關閉就清」的開關；有的開關會兩者一起清

- **macOS**：General 設定「Remove history items — Choose when to remove items from the history」；該頁**完全沒提**cookie 或 website data（[Apple Support — Change General settings in Safari on Mac](https://support.apple.com/guide/safari/general-ibrw1072/mac)，2026-10-25 存取）【Primary】。它是否連帶清 site data，Apple 文件沉默（UNVERIFIED #12）。Privacy 設定「Manage Website Data → Remove / Remove All」是手動操作；「Removing cookies and website data in Safari may change or remove them in other apps」（[Apple Support — Manage cookies in Safari on Mac](https://support.apple.com/guide/safari/manage-cookies-sfri11471/mac)，2026-10-25 存取）【Primary】。「Clear History」頁列出的清除項目（歷史、frequently visited、icons、snapshots…）同樣沒有 cookie 這一項（[Apple Support — Clear your browsing history in Safari on Mac](https://support.apple.com/guide/safari/clear-your-browsing-history-sfri47acf5d6/mac)，2026-10-25 存取）【Primary】。
- **iOS／iPadOS**：「Clear History and Website Data」清歷史、cookie、快取；只清網站資料保留歷史走 Settings → Apps → Safari → Advanced → Website Data → Remove All Website Data（說明：「clears data that's used for tracking and by websites to save login information」）；**「Block All Cookies」一打開：「This removes all existing cookies and website data. Safari quits, and your tabs are reloaded」**（[Apple Support — Delete history, cache, and cookies in Safari on iPhone or iPad](https://support.apple.com/en-us/105082)，2026-10-25 存取）【Primary】。這是本文找到的、**單一動作同時殺掉兩腿**最直接的 Primary 證據。
- **「Prevent cross-site tracking」**：WebKit 說 ITP 的 cookie 政策「still in effect today as part of the "Prevent cross-site tracking" setting」（[WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/)，2026-10-25 存取）【Primary】；Apple 的 macOS 說明頁只描述它對第三方內容供應商的效果（「their cookies and website data are deleted」除非以 first-party 身分互動過）（[Apple Support — Prevent cross-site tracking in Safari on Mac](https://support.apple.com/guide/safari/prevent-cross-site-tracking-sfri40732/mac)，2026-10-25 存取）【Primary】。關掉它是否同時關掉 7 天上限，兩份文件都沒有明說（UNVERIFIED #13）。
- **Private Browsing**：IndexedDB／localStorage 走記憶體後端（§4.2），cookie 也是 session 性質——關閉即清。

---

## 矩陣：瀏覽器 × 儲存腿 × 什麼會讓它消失（使用者沒有明確動手清除的前提下）

「使用者設定」欄指使用者**事先**選了某個設定，之後的消失不需要再動手；「手動清除」（Remove All Website Data、Clear browsing data 等）不在本矩陣範圍，因為那就是明確動作。

| 瀏覽器 | 腿 ① HttpOnly `__Host-oc_owner` cookie（伺服器 `Set-Cookie`） | 腿 ② IndexedDB（主） | 腿 ②′ localStorage（鏡像） |
|---|---|---|---|
| **Safari macOS**（13.1+） | 到期：`Max-Age` 400 天（我們從不重設 → 首次簽發起算）。CFNetwork 是否另外上限 400 天：UNVERIFIED #14。ITP 7 天上限**不適用**（HTTP 設定）；CNAME cloaking 7 天上限不適用（同 host，§1.4）；30 天 tracker 清除只對 classified domain。使用者設定：Block All Cookies（立即全清）。不在 quota eviction 範圍 | **ITP 7 天上限：7 個 Safari 使用日無 click／tap／鍵盤互動即刪，每個網站都適用**；Safari 17+ quota eviction（整 origin、LRU、超過整體 quota／系統儲存壓力／長期無互動）；Block All Cookies 一起清 | 與腿 ② **同一份名單、同一次刪除**（ITP 列 LocalStorage）；其餘同腿 ② |
| **Safari iOS／iPadOS**（13.4+；含 WKWebView 內的第三方瀏覽器，iOS 14+ ITP 預設開） | 同 macOS。「Block All Cookies」文件明寫「removes all existing cookies and website data」 | 同 macOS；**加到主畫面的 web app 豁免 7 天上限**（獨立使用日計數器、與 Safari 隔離） | 同腿 ② |
| **Chrome desktop**（104+） | **到期：首次簽發起 400 天硬上限**（M104；M118 起回溯套用既有 cookie）。重設同名 cookie 會重算到期。CookieMonster 數量驅逐（180／key、3300 全域，LRA，30 天內存取者全域清理時保留）——我們只有一顆，風險低。不在 quota eviction 範圍。使用者設定：「Delete data sites have saved to your device when you close all windows」 | 磁碟壓力 LRU 驅逐（整 origin；free space < min(2 GB, 10%) 時 quota 歸零、< min(1 GB, 1%) 時「aggressively evicted」）；Google 自述「very rarely」。`persist()` 靜默依 heuristics（engagement ≥ MEDIUM／安裝／≤5 書籤／通知）；session-only 設定下一律拒絕。使用者設定：關閉所有視窗即清；Incognito 關閉即清 | 「all site data」隨 origin 一起清（UNVERIFIED #6 標記 localStorage 是否逐字在 quota eviction 內）；其餘同腿 ② |
| **Chrome Android**（104+） | 同 desktop（400 天 Android 104 同步） | 同 desktop；persist heuristics 無 Android 分支。OS 層「清除儲存空間」：UNVERIFIED #7 | 同腿 ② |
| **Firefox desktop**（140+ 有 400 天上限；115+ private window 有 IndexedDB） | **到期：首次簽發起 400 天**（140 起 `Max-Age` 也上限）。Redirect tracking protection 只清 Tracking Protection 名單上的 tracker。使用者設定：「Clear cookies and site data every time you close Firefox」（含例外清單） | 磁碟壓力 LRU 驅逐（整 origin）；best-effort 上限 min(10% disk, 10 GiB group)。`persist()` **跳提示**「Allow X to store data in persistent storage?」（無需手勢；private window 不提示直接 false）。關閉即清設定：`CLEAR_DOM_STORAGES` 明列 LocalStorage、IndexedDB | 同腿 ②（`CLEAR_DOM_STORAGES` 同一面旗） |
| **所有瀏覽器的 private／Incognito 模式** | session 結束即清 | 記憶體後端（Safari：MemoryIDBBackingStore；Firefox 115+：加密暫存；Chrome：記憶體 pool），session 結束即清；Firefox < 115 直接報錯 | 同腿 ② |

**唯一會同時殺掉兩腿、又不需要使用者當下動手的情境**：使用者**事先**開了「關閉視窗就清除」類設定或使用 private 模式；再加上 Safari「Block All Cookies」（一次動作、但效果是永久封鎖）。瀏覽器自動行為（ITP、quota eviction、400 天到期）**每一項只打到一腿**——ITP 與 quota eviction 只打本機腿，400 天到期只打 cookie 腿。

---

## 對 Option Chaser 兩腿設計的意涵

### 哪一腿在哪裡比較弱

- **Safari（macOS／iOS、含 iOS 上所有第三方瀏覽器）：本機腿弱、cookie 腿強。** 7 個 Safari 使用日沒互動就刪，對「偶爾回來看一下」的使用者是常態，不是邊緣案例；IndexedDB 與 localStorage 一起刪，鏡像在這裡**不是**備援。cookie 腿只怕 400 天到期（見下）與使用者自己 Block All Cookies。現有「cookie 在 → 回應以 `X-OC-Credential` 補回本機腿」的機制正好對應這個情境，**設計方向正確、不需改**。
- **Chrome／Firefox：cookie 腿有唯一的硬期限，本機腿反而比較耐。** 本機腿只在磁碟壓力 LRU（Google 自述罕見）或使用者設定下消失；cookie 腿則**無論使用者多活躍，第 400 天必到期**，因為我們從不重設。到期當下若本機腿還在，下一個請求伺服器會補發 cookie（`issue` 路徑），身分不掉——所以真正的風險窗口是「cookie 到期 **且** 本機腿恰好也不在」。本機腿在 Chrome／Firefox 上消失的機率低，但在 Safari 上（7 天規則）高——Safari 使用者第 400 天之後回來，若剛好超過 7 個使用日沒互動，**兩腿同時不在，身分掉**。這是目前設計裡唯一一個「不需要使用者動手」就會發生的全失情境，發生時點可以精確預測：首次簽發後 400 天。

### 門檻式 cookie 重簽（例如每 30 天）值得嗎——值得，而且便宜

- **效果**：規範與 Chrome 官方都確認同名重設會重算 expiry（§2.1）。只要使用者在 400 天內回來過一次、而那次請求觸發了重簽，cookie 腿就再活 400 天。這把「首次簽發起 400 天」改成「最後一次活躍起 400 天」，與資料保留政策（`last_seen_at` 清理錨點）的精神一致。
- **成本**：後端已經有 `cookie_issued_at`（`mark_owner_cookie_issued()`），`credential["issue"]` 的判斷式只要多一個條件「`cookie_issued_at` 早於 now − N 天」。每次重簽都會寫一次 `cookie_issued_at`，N 取 30 天時每個活躍使用者每月多一次寫入，可忽略。回應會多一個 `Set-Cookie` header，`Cache-Control: private, no-store` 已經在。
- **N 怎麼選**：N 不影響安全性（同一顆 token，不是輪換），只影響「使用者至少要在哪個間隔內回來一次」——任何 N < 400 都把保證改成「最後活躍起 400 天」，差別只在寫入頻率。30 天是合理的工程數字；7 天也可以但沒有額外好處。
- **不是 SECURITY-FIX-01 那種滑動窗的回歸**：IDENTITY-FIX-002 拿掉的是「每個請求都 Set-Cookie」；門檻式重簽每 N 天才一次，且仍是固定 400 天期限，不是「永遠不到期」。

### `navigator.storage.persist()` 值得嗎——目前不值得

- **Chrome**：對沒加書籤、沒安裝、沒開通知、engagement 不到 MEDIUM 的匿名使用者幾乎必定靜默拒絕（§2.4）；而且它只防「磁碟壓力 LRU 驅逐」這一件 Google 自己說「very rarely」的事，對 400 天到期、對使用者設定（session-only 時連授權都不給）都無效。
- **Firefox**：一呼叫就跳「Allow X to store data in persistent storage?」，不需要使用者手勢（`requiresUserInput` 為 false）——對一個還沒建立任何東西的匿名訪客，這是一個解釋不了的權限對話框，體驗成本大於收益。
- **Safari**：heuristics 以「是否為 Home Screen Web App」為主，瀏覽器分頁基本拿不到；而 Safari 上真正會刪本機腿的是 ITP 7 天規則，persist 不在那條規則的豁免條件裡（豁免只有主畫面 web app）。
- **結論**：cookie 腿本來就不在任何 quota eviction 系統裡，兩腿設計已經覆蓋了 persist 想防的那件事。若日後要做，只該在 Chromium 上、在使用者完成某個有意義的動作（建立第一個劇本）之後呼叫，並接受多半被拒絕。

### IndexedDB open timeout 需要嗎——需要，但要連 `loading` 快取一起改

- **理由**：Primary 證據只有 Safari 14.6／14.1.1 這一例會真的 hang（§4.1），且已修；但現有程式把「一次 open 不回應」放大成「分頁內所有 API 請求永遠送不出、且 cookie 腿形同不存在」，與兩腿設計的初衷相反。另外 STP 248 修正前的 Safari 有「transaction 被另一分頁掛起的 transaction 長時間阻塞」（§4.3），對 `inTransaction()` 是同一類風險。
- **形狀**（研究建議，非施工）：(1) `openDb()`／`inTransaction()` 以 `Promise.race` 加一個數秒級 timeout，超時視同「IndexedDB 暫時不可用」→ 走既有的 localStorage 退路（檔頭已規定 localStorage 為準、IndexedDB 對齊，雙邊不一致可被吸收）；(2) `credential()` 不要把超時失敗的結果永久記在 `loading`——至少讓 `storeCredential()`（伺服器 echo 回來時）能重新嘗試寫 IndexedDB，現有 `storeCredential()` 已經會這麼做；(3) timeout 時長要大於正常冷啟動的 IndexedDB open（行動裝置上可達數百毫秒），數秒是安全範圍；精確數字留給實作票量測。
- **不需要**為 Chromium／Firefox 的「不可用」路徑另外處理——它們都是同步丟錯或 error event，現有 try/catch 已涵蓋（§2.6、§3.5）。

---

## UNVERIFIED（本文誠實列出、可能重要的未查證項目）

1. **「一個 Safari 使用日」的精確定義**——WebKit 原文一致使用「days of Safari use」／「days of browser use」並說主畫面 web app 有「their own counter of days of use」，但沒有定義「使用」的門檻（開啟 Safari？載入任何頁面？）。本文採字面「有使用 Safari 的日曆日才計一天」。
2. **7 天上限是否在 WKWebView（iOS 上的 Chrome／Firefox 等）中逐條生效**——WWDC20 只說 ITP「enabled by default on all WKWebView apps」，WebKit Tracking Prevention 頁未單獨討論 WKWebView；本文假設 ITP 整組生效。
3. **Option Chaser 的 production domain 不會被 ITP 分類為具 cross-site tracking 能力**——分類是裝置端演算法，無法從外部確認；依產品形狀（不以第三方身分出現在他站）推論不會。
4. **Firefox 把 `Expires` 上限在 400 天的原始 bug 編號與版本**——Bugzilla 1964943 描述「We do it for the `expires` but not the `max-age`」證實在 140 之前已存在，但本次以 REST 查詢未找到該 bug。
5. **Firefox 重設同名 cookie 時是否完全依 RFC 6265bis Storage Model 重算 expiry**——未讀 Firefox cookie service 原始碼；規範要求如此，沒有理由認為偏離。
6. **Chromium／Firefox 的 quota eviction 是否逐字包含 localStorage**——web.dev 寫「all site data」，MDN 只給 Web Storage 固定上限而未明說；本文採「包含」。
7. **Android OS 層（「清除儲存空間」、系統空間不足）對 Chrome Android 站點資料的影響**——未查 Android 文件。
8. **Chrome Incognito quota 的數字**——web.dev（2024-09-23）寫「approximately 5% of the total disk space」，`quota_settings.cc` 寫系統記憶體的 15–20%；本文以原始碼為準，差異未向 Google 文件確認。
9. **Safari 首次在 private browsing 中支援 IndexedDB／不再對 localStorage 丟 `QuotaExceededError` 的出貨版本**——WebKit trunk 分別於 2016-04（Modern IDB in-memory backing store）與 2017-04（r215315）變更，但對應的 Safari 版本未在 WebKit 文件中查到（157010 有人回報 Safari 10.1.2 仍受影響）。
10. **Chrome「Delete data sites have saved to your device when you close all windows」逐項清除清單的 Primary 列舉**——Google 說明頁只說「data sites have saved to your device」；本文以選項語義＋Chromium「session-only storage」註解判定為 cookie＋site data 皆清，未逐檔讀 Chromium 的 session data deleter。
11. **Mozilla 支援中心「Clear cookies and site data in Firefox」頁面**——兩次抓取都被「Client Challenge」擋下；本文以 Firefox 原始碼字串（`preferences.ftl`、`Sanitizer.sys.mjs`、`nsIClearDataService.idl`）代替。
12. **Safari macOS「Remove history items」自動清歷史時是否連帶清 cookie／website data**——Apple General 設定頁與 Clear History 頁都未提及 cookie；本文傾向「只清歷史」但無 Primary 明文。
13. **關掉 Safari「Prevent cross-site tracking」是否連 7 天上限一起關掉**——WebKit 只說 cookie 政策是該設定的一部分，Apple 說明頁只講第三方內容；未找到明文。
14. **Safari／CFNetwork 是否實際強制 400 天 cookie 上限**——webkit-dev 2022-01 的 WebKit 立場信（John Wilander：Apple WebKit 與 CFNetwork「support a 400-day max-age upper limit with some caveats」）兩個 URL 均回 HTTP 403 無法直接讀取，只在搜尋摘要中看到；Chrome 部落格 2023-01 時寫「neither has implemented as of writing」。W3C TAG review #729（2022-04-26）確認該 webkit-dev 串存在（[w3ctag/design-reviews#729](https://github.com/w3ctag/design-reviews/issues/729)，2026-10-25 存取）。對我們而言差別不大：我們本來就只要 400 天。
15. **Chrome Platform Status 頁面本體**——HTML 版為 JS 渲染、抓不到內容，本文改讀其 JSON API（`/api/v0/features/4887741241229312`）取得 milestone 104（desktop／Android）。
