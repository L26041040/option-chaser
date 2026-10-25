# 匿名身分的雙寫同步與部分遺失處理研究（PostHog／Segment／Amplitude／Supabase／Firebase／WebAuthn）

**issue #366**（`L26041040/option-chaser`，Wayfinder map **#359** 的子票）。**本文只研究、不施工、不裁決**——`option_chaser/`／`api_app/`／`src/` 零改動，未修改任何 GitHub issue。全部「存取日期」皆為 **2026-10-25**。既有 `docs/research/anonymous-identity-session-patterns.md` 已涵蓋 cookie 形狀、Mullvad／Excalidraw／claim link、Firebase／Supabase 升級帳號——本文**不重做**，只補票面五題。

**證據分級**（依每個結論標記）：

- 【業界慣例】——主流 SDK／平台的實際做法，非強制，但被廣泛採用
- 【規格／安全必要】——有規格文字（W3C／WHATWG）或可觀察的安全後果撐著
- 【Option Chaser 產品選擇】——結論成立與否取決於這個 repo 現有架構或 Owner 已裁示的硬約束

**來源等級**：一手來源只有三種——官方文件、GitHub 上的開源 SDK 原始碼（`raw.githubusercontent.com` 的 `main`／`master` 分支，讀取日即 2026-10-25）、官方 changelog／issue／PR。凡是從 issue 回報者或 PR 描述（而非維護者文件或程式碼）取得的事實，正文會標「回報者說法」。

---

## 給 Owner 看的白話摘要

這張票問的是：**我們把同一顆匿名憑證存兩份（伺服器簽的 HttpOnly cookie＋瀏覽器本機的 IndexedDB／localStorage 副本），每次回應把兩份對齊——這種「雙寫＋收斂」的做法，業界真的在瀏覽器裡維護匿名 id 的那些 SDK 是怎麼做的？會不會有我們沒想到的坑？**

五題的一句話答案：

1. **雙寫與和解**：三家分析 SDK 裡只有 PostHog 真的雙寫（`localStorage+cookie`），Segment 是「多個 store 依優先序讀、全部 store 一起寫」，Amplitude **只存一份**（預設 cookie）。真正的教訓是：**PostHog 與 Segment 都曾因「兩份不一致時誰贏」選錯而出過真實的身分分裂 bug**——兩家原本都讓「只屬於這個 origin 的 localStorage」贏過「跨子網域共用的 cookie」，結果子網域之間同一個人被拆成兩個人；Segment 在 2026 年 9 月把規則改成「cookie 永遠贏、其他 store 全部重新對齊」，PostHog 加了 `cookieWinsOnConflict` 開關。**三家都只在「兩份都讀不到」時才產生新 id**，`reset()` 是唯一刻意產生新 id 的入口。這跟 Option Chaser 現在「伺服器先認 cookie、再認 header、兩份都不認得才（在真的要寫入時）建新 user」的規則，形狀一致。
2. **跨分頁一致**：**分析 SDK 不做即時同步**——Segment 每次用到 anonymousId 都重新讀儲存（沒有記憶體副本可以過期）；PostHog 2026 年 9 月才為 feature flag 加上 `storage` event 監聽，身分（cookie）則是「在下一次 capture／寫入之前重讀 cookie」，官方文件明講是「on the tab's next PostHog activity, not immediately」；Amplitude 把身分讀進記憶體後就不再回頭看儲存。**真正做即時同步的是兩家 auth SDK**：Supabase 用 BroadcastChannel 廣播 auth 事件＋Web Locks 防止多分頁同時 refresh，Firebase 用每 800 ms 輪詢 IndexedDB。它們需要同步的理由是 **token 每小時輪替**、多分頁同時 refresh 會互相踩——我們的憑證除了登入／登出之外從不改變，沒有這個壓力。
3. **匿名 session 的續命**：Supabase 的 refresh token「永不過期、只能用一次」，存在 `localStorage` 的 `sb-<ref>-auth-token`；Firebase 的 refresh token 存在 IndexedDB 裡的 user 物件，只在「user 被刪／停用／重大帳號變更／管理員撤銷」時失效。**兩家都沒有「這個匿名使用者遺失了」的專屬事件**：Supabase 在 refresh 失敗且不是網路錯誤時發 `SIGNED_OUT`（並廣播到其他分頁）；Firebase 在 `auth/user-token-expired`／`auth/user-disabled` 時自動 `signOut()`，`onAuthStateChanged` 收到 `null`——跟首訪一模一樣。Firebase 甚至在 2026 年 10 月才修掉「暫時性 5xx 就把持久化的 user 清掉」這個 **SDK 自己造成身分遺失**的 bug。
4. **部分遺失的可觀測性**：分析 SDK 的伺服器端**不會拒絕任何 client 自己產生的 id**，所以沒有「曾有 id 但現在不認得」這個概念；auth SDK 在協定層分得出（Supabase 的 `SIGNED_OUT`-without-user-action；Firebase 的 invalidation 錯誤碼），但都把「要不要告訴使用者」留給 app——Supabase 文件直接寫「使用者若登出、清除瀏覽資料或換裝置就無法再存取帳號」。**本次沒有找到任何產品把「你的匿名身分遺失了」主動告訴使用者**。**Option Chaser 的伺服器其實今天就分得出這兩種情況**（有帶 token 但查不到 vs. 完全沒帶 token），只是沒有記成指標。
5. **WebAuthn／passkey 作為零註冊的裝置身分錨點**：規格層面可行（user handle 本來就「MUST NOT contain personally identifying information」，可以是隨機值），而且 passkey 經 iCloud Keychain／Google Password Manager 同步能順帶拿到跨裝置——**但每一次 `get()` 都「MUST include a test of user presence」、使用者不同意就是 `NotAllowedError`、規格明講 passkey「always require user interaction」**，所以回訪時無法靜默恢復身分，一定會跳出生物辨識／裝置鎖提示。這與「零使用者負擔」直接衝突。**沒有找到任何產品用 passkey 當匿名身分的恢復錨**；最接近的先例是 Cloudflare 的 Cryptographic Attestation of Personhood——它刻意只拿 WebAuthn 證明「是人」，明講「we're not interested in *which* human you are」，而且每次都要使用者按一下金鑰。

**對「跨分頁即時同步要不要做」的建議**（本文第 6 節有完整論證）：**不建議為此引入 BroadcastChannel**。理由是：業界用 BroadcastChannel／輪詢的是「state 會自己變（token 每小時換）」的 auth SDK，我們的憑證只在登入／登出時變、而且 cookie jar 是所有分頁共用的，現有「cookie 優先＋回應 echo」已經讓絕大多數 stale 分頁在下一次回應就收斂。本文找到的唯一真實缺口是**「分頁的記憶體副本永遠不重讀本機儲存」**——這剛好是 PostHog 2026 年用 `storage` event 補、Segment 用「每次都重讀」避開的同一個坑。補法只需沿用瀏覽器免費提供、本產品已經在用 Web Locks 的同一代 API（`storage` event 或「伺服器說未綁定就重讀 IndexedDB」），不需要 BroadcastChannel。

---

## 目前 Option Chaser 的起點（研究依據，非外部引用）

後面每一題的「對 Option Chaser 的含義」都會回頭引用這裡：

- **兩份、同一顆 token**：`src/credentialStore.ts` 檔頭註解明寫「同一顆 token 存兩份：伺服器簽的 HttpOnly cookie（`__Host-oc_owner`，JS 讀不到）；這裡管理的本機副本：IndexedDB 為主、localStorage 為鏡像」，每個請求放在 `X-OC-Credential` header。
- **本機兩份的優先序**：`idbGetOrCreate()` 的註解——「**以 localStorage 為準**，把 IndexedDB 對齊過去，不是把它蓋掉」，理由是 localStorage 那份可能是「這個瀏覽器曾經退回 localStorage 產生過一顆」、已被綁定、正等著重試。整段在單一 IndexedDB `readwrite` transaction 裡，「規格保證同一個 origin 上 scope 重疊的 readwrite transaction 依序執行，後到的分頁一定讀到先到的那顆」。
- **跨分頁的現況**：`withOwnerBindingLock()` 用 **Web Locks**（`navigator.locks.request("oc-owner-binding")`）讓「還沒綁定前會建立 user 的請求」跨分頁排隊。但每個分頁的記憶體狀態（`bound`／`loading`／`cached`）**只讀一次**：「每個分頁最多讀一次 IndexedDB」、「讓 `send()` 在第一次之後同步取用」。`grep` 實測：`src/` 下沒有任何 `addEventListener("storage")` 或 `BroadcastChannel`。
- **伺服器的和解規則**（`api_app/main.py` `_resolve_owner_for_request()`）：`for token in dict.fromkeys(t for t in (cookie_token, stored_token) if t)`——**cookie 先、header 後**，第一個查得到的贏；查到時 `issue = token != cookie_token or resolved.cookie_issued_at is None`（cookie 不對就補發 cookie）、`echo = token != stored_token`（本機那份不對就在回應的 `X-OC-Credential` 交回正確值）。兩份都查不到：**不建立 user**，回每個請求各自隨機的佔位 owner，`candidate = stored_token or cookie_token or secrets.token_urlsafe(32)`——注意這裡**header 優先於 cookie**（跟查詢順序相反，理由寫在 docstring：「它活在本機儲存，所有分頁共用」）；只有會寫入的端點（`_persistent_owner()`）才用 `claim_browser_token()` 把它原子地綁到新 user（靠 `browser_identities.token` PK，「多個 instance 同時首次寫入也只會得到一個 owner」）。
- **憑證只在兩個時刻改變**：SU／SA 登入（`db.delete_browser_identity(credential["token"])` 作廢舊顆，`add_browser_identity` 綁新顆到主帳號，`credential.update(token=token, bound=True, issue=True, echo=True)`——「兩份同時換成新憑證」）；`POST /api/auth/reset-role` 登出（作廢這顆，`credential.update(token=secrets.token_urlsafe(32), bound=False, issue=True, echo=True)`——換一顆**還沒綁定**的新憑證）。
- **現有指標**（`_record_metric` 名稱，`grep` 實測）：`new_owner_count`、`abandoned_owner_cleanup_count`、`empty_owner_cleanup_count`、`cold_miss_count`、`stale_serve_count`、各種 `*_block_count`——**沒有**任何一個記錄「有帶 token 但查不到」。

---

## 摘要表

| | 存幾份 | 讀取優先序 | 不一致時誰贏 | 何時產生新 id | 跨分頁 |
|---|---|---|---|---|---|
| **PostHog** `localStorage+cookie` | 2（localStorage 全部＋cookie 存 `distinct_id`／`$device_id`／`$session_id` 等少數鍵） | 寫入先寫 localStorage（durable），cookie 是 best-effort mirror | **預設 localStorage 贏**；`cookieWinsOnConflict: true`（≥1.418.0）才 cookie 贏 | 初始化時兩份都讀不到；`reset()`；`disable_persistence`；（bug）consent 流程回歸 1.434.18–1.435.3 | localStorage：`storage` event（1.423.0 起，先用於 flags）；cookie：下一次 capture／寫入前重讀；無 BroadcastChannel／Web Locks |
| **Segment** analytics-next | 3 個 store 一起寫（LocalStorage、Cookie、Memory） | 讀：陣列順序（預設 LocalStorage → Cookie → Memory） | **`getConsistent()`：非空的 cookie 永遠贏，再把贏家寫回所有 store**（1.84.2 opt-in → 1.84.3 預設） | `getConsistent()` 回 null 且無 legacy `_sio` 時 `uuid()`；`reset()` | **無**任何監聽；但 `anonymousId()` 沒有記憶體副本、每次都重讀儲存 |
| **Amplitude** Browser SDK 2 | **1**（`identityStorage`：cookie 預設／localStorage／sessionStorage／none） | 啟動時讀一次 `previousCookies`，之後走記憶體 getter | 不適用（單一 store） | 啟動時 config／URL 參數／cookie 都沒有 → `UUID()`；`reset()`；`none` 每次造訪 | **無**；setter 呼叫 `updateStorage()` 整包覆寫（last writer wins）【從原始碼推論，見 UNVERIFIED】 |
| **Supabase** auth-js | 1（`localStorage` 的 `sb-<ref>-auth-token`，含 refresh token） | — | — | 不產生；refresh 失敗（非網路／非 502-504）→ `_removeSession()` → `SIGNED_OUT` | **BroadcastChannel**（頻道名＝storageKey，廣播 `{event, session}`）＋**Web Locks**（`navigator.locks`）＋`visibilitychange` 時重新 recover |
| **Firebase** Auth | 1（IndexedDB `firebaseLocalStorageDb`，user 物件內含 `stsTokenManager.refreshToken`） | 預設 persistence 順序 IndexedDB → localStorage → sessionStorage | — | 不產生；`auth/user-token-expired`／`auth/user-disabled` → `signOut()` → `onAuthStateChanged(null)` | **IndexedDB 每 800 ms 輪詢**；localStorage 後端用 `storage` event＋行動瀏覽器 1000 ms 輪詢 |
| **Option Chaser** | 2（HttpOnly cookie＋IndexedDB/localStorage 本機副本） | 伺服器：cookie → header；本機：localStorage → IndexedDB | **伺服器第一個查得到的贏**，回應補發 cookie／echo header | 兩份都查不到**且**發生寫入時（`claim_browser_token`） | IndexedDB transaction 原子＋Web Locks 排隊綁定；**記憶體副本不重讀** |

---

## 1. 雙寫與和解：PostHog／Segment／Amplitude

### PostHog JS（`persistence: 'localStorage+cookie'`）

**成熟做法**：

- **預設就是雙寫**：「By default, PostHog uses `localStorage+cookie` persistence」；這個模式下「Limited things are stored in the cookie such as the distinctID and the sessionID, and everything else in the browser's localStorage」；cookie 名為 `ph_<project_token>_posthog`、「expires after `365` days」（[PostHog Docs — JavaScript web persistence and cookies](https://posthog.com/docs/libraries/js/persistence)，2026-10-25 存取）。原始碼 `createLocalPlusCookieStore()` 列出進 cookie 的鍵：`DEVICE_ID`、`DISTINCT_ID`、`SESSION_ID`、`SESSION_RECORDING_IS_SAMPLED`、`ENABLE_PERSON_PROCESSING`、`INITIAL_PERSON_INFO`、`PERSISTENCE_FACEBOOK_CLICK_ID`、`USER_STATE`；feature flag 與 person property 留在 localStorage，檔內註解說是為了避免 cookie header 過大（[posthog-js `packages/browser/src/storage.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/storage.ts)，2026-10-25 存取）。
- **寫入順序**：`_set` 先寫 localStorage（`const stored = localStore._set(name, value, ...)`），**localStorage 是 durable store，cookie 是 best-effort mirror**，cookie 寫失敗不改變回傳值（同上 `storage.ts`）。
- **讀取時誰贏**：`_parse` 的合併——預設 `value = extend(cookieProperties, localStorageData)`（**localStorage 蓋 cookie**）；`preferCookieOnConflict` 為真時 `value = extend(localStorageData, safeCookieProperties)`（cookie 蓋 localStorage，且先濾掉 null／空字串的 cookie 值）（同上 `storage.ts`）。官方文件的說法一致：「When `cookieWinsOnConflict` is disabled, the stale `localStorage` value wins this conflict」（`defaults` 未設時的預設）；「Set `cookieWinsOnConflict: true` to make the shared cookie authoritative for the keys it contains」，需要 posthog-js **1.418.0** 以上，且只適用於 `localStorage+cookie`（[PostHog Docs — persistence](https://posthog.com/docs/libraries/js/persistence)，2026-10-25 存取）。Changelog 1.418.0：「Add `cookieWinsOnConflict` to keep shared cross-subdomain identity and session state ahead of stale per-origin localStorage」（[posthog-js `packages/browser/CHANGELOG.md`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/CHANGELOG.md)，2026-10-25 存取）。
- **何時產生新 `distinct_id`**（`posthog-core.ts`）：(1) `_init` 裡 `else if (!this.get_distinct_id())`——persistence 載入後兩份都沒有 id，才 `const uuid = this.config.get_device_id(uuidv7())` 並 `register_once({ distinct_id: uuid, $device_id: uuid }, '')`；(2) `reset()` → `_reset()`：`const uuid = this.config.get_device_id(uuidv7())`，而 `$device_id: reset_device_id ? uuid : device_id`——**預設保留 `$device_id`、只換 `distinct_id`**；(3) cookieless 模式用哨兵值 `COOKIELESS_SENTINEL_VALUE` 佔位、同意後才 mint。程式註解明寫判斷匿名的方法：「distinct id == $device_id is a proxy for an anonymous user」（[posthog-js `packages/browser/src/posthog-core.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-core.ts)，2026-10-25 存取）。文件：「Without a stable bootstrapped ID, PostHog creates a new anonymous ID on every page load」（`disable_persistence: true` 的情況）（[PostHog Docs — persistence](https://posthog.com/docs/libraries/js/persistence)，2026-10-25 存取）。

**代價（真實發生過的身分分裂）**：

- **「localStorage 贏」是錯的預設，PostHog 自己承認**：PR #5030（「fix(browser): warn when a cookie-set distinct_id is discarded」）的描述說，某個 A/B 實驗因為「the server and browser used different IDs」被算成兩個人，原因是 `createLocalPlusCookieStore._parse`「lets localStorage win every key the cookie also carries」，所以 redirect middleware 寫進 cookie 的 `distinct_id` 會被丟掉；PR 描述還說 `cookieWinsOnConflict`「defaults on only for `defaults >= '2026-08-29'`」。這個 PR **沒有被合併**（2026-09-18 開、2026-10-05 被 stale bot 關閉）（[posthog-js PR #5030](https://github.com/PostHog/posthog-js/pull/5030)，2026-10-25 存取；PR 描述屬回報者說法，見 UNVERIFIED #3）。
- **consent 流程回歸造成跨子網域分裂**：issue #5166「Bug report: users split across subdomains after cookie consent in 1.434.18+」——在第二個子網域 opt-in 後，共用 cookie「overwritten with a new `distinct_id` and `$device_id`」，兩個子網域的事件歸到不同的人；回報者分析根因是 PR #5125 讓 disabled 旗標在 `load()` 之前就設好，`load()` 提早回傳空 props，於是記憶體裡 mint 了新 UUID，opt-in 時 `set_disabled(false)` 沒先讀儲存就把它存下去蓋掉 cookie；1.434.17 以前正常（[posthog-js issue #5166](https://github.com/PostHog/posthog-js/issues/5166)，2026-10-25 存取）。修正 PR #5175「fix(browser): preserve shared identity after cookie consent」2026-10-01 合併，做法是「Restore the existing identity in memory before disabled initialization clears storage」（[posthog-js PR #5175](https://github.com/PostHog/posthog-js/pull/5175)，2026-10-25 存取）。**教訓**：身分分裂往往不是和解規則本身寫錯，而是**某條初始化路徑在「讀儲存」之前就先「產生並寫入」**。
- **session 連續性仍是開放問題**：issue #3130「Session continuity across consent state changes」（從 `memory` 切到 `localStorage+cookie` 時「A new `$session_id` is generated, breaking session continuity」）截至存取日仍 Open，維護者回覆「I agree this should/can be fixed then」（[posthog-js issue #3130](https://github.com/PostHog/posthog-js/issues/3130)，2026-10-25 存取）。

**對 Option Chaser 的含義**：

- 我們的「伺服器先查 cookie」等價於 PostHog 的 `cookieWinsOnConflict: true`／Segment 的 `getConsistent()`——**選對了邊**：cookie 是伺服器簽發、HttpOnly、所有分頁共用的那份，本機副本才是「可能過期的那份」。PostHog 與 Segment 兩家都是從「本機贏」改成「共用那份贏」，沒有反方向的案例。【業界慣例】
- 本機兩份之間我們反而讓 **localStorage 贏 IndexedDB**（`idbGetOrCreate()`）。這跟 PostHog 的「durable store 贏 mirror」是**相反方向**，但理由不同：PostHog 的 cookie 是 mirror，而我們的 localStorage 可能是「退回路徑產生、已被綁定、等著重試」的那顆。這個理由在 `credentialStore.ts` 註解寫清楚了，本文不評價對錯——只提醒：**本機兩份不一致時無論誰贏，伺服器都會以 cookie 為準再把正確值 echo 回來**，所以本機的優先序只影響「cookie 不存在時用哪一顆去綁」，不影響已綁定身分。【Option Chaser 產品選擇】
- PostHog #5166 那種「初始化路徑在讀之前就寫」的坑，對應到我們是 `localStorageGetOrCreate()` 的形狀驗證：「形狀不對就換一顆新的存回去」。這是 IndexedDB 不可用時的退路，目前有「先驗形狀」護欄；本文沒有找到它會在 IndexedDB 可用時被走到的路徑。【Option Chaser 產品選擇】

### Segment analytics.js（analytics-next）

**成熟做法**：

- **多 store、一起寫、依序讀**：官方文件——「The `storage` property takes an array of `localStorage`, `cookie`, and `memory`, listed in priority order」，預設「LocalStorage -> Cookie -> InMemory」，cookie 是「a fallback when localStorage is unavailable or unpopulated」；cookie `maxage` 預設「1 year」，並提醒「Chrome caps cookie lifetime at 400 days」（[Twilio Segment Docs — Client-side persistence in Analytics.js](https://www.twilio.com/docs/segment/connections/sources/catalog/libraries/website/javascript/cookie-validity-update)，2026-10-25 存取）。原始碼預設 `stores = [StoreType.LocalStorage, StoreType.Cookie, StoreType.Memory]`（[analytics-next `packages/browser/src/core/user/index.ts`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/src/core/user/index.ts)，2026-10-25 存取）；cookie 預設 `maxage: ONE_YEAR`（`const ONE_YEAR = 365`）、`path: '/'`、`sameSite: 'Lax'`、`domain: tld(window.location.href)`（[analytics-next `cookieStorage.ts`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/src/core/storage/cookieStorage.ts)，2026-10-25 存取）。
- **`UniversalStorage.set()` 寫到每一個 store**（各自 try/catch，一個失敗不擋其他）；**`getConsistent()` 的和解規則**：讀所有 store、濾掉 `undefined`／`null`／空字串（註解：「a blanked-but-not-deleted cookie can't win」）、**第一個有值的 `CookieStorage` 贏**，沒有才取陣列順序第一個有值的，然後把贏家 `set()` 回所有 store。註解說明理由：cookie 值「wins a disagreement, since only it can carry a value across subdomains (see #706)」（[analytics-next `universalStorage.ts`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/src/core/storage/universalStorage.ts)，2026-10-25 存取）。
- **何時產生新 anonymousId**：`anonymousId()` 無參數時 `const val = this.identityStore.getConsistent(this.anonKey) ?? this.legacySIO()?.[0]`，有值就回；沒有才 `this.identityStore.set(this.anonKey, id ?? uuid())`；`reset()` 會 `clear` 掉 `anonKey`（[analytics-next `user/index.ts`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/src/core/user/index.ts)，2026-10-25 存取）。文件：「If the cookie expires and the user returns, Analytics.js looks for an old ID in localStorage and writes it into the new cookie」；「Clearing both cookies and localStorage removes all IDs and generates a new anonymous ID on the next visit」（[Twilio Segment Docs — Client-side persistence](https://www.twilio.com/docs/segment/connections/sources/catalog/libraries/website/javascript/cookie-validity-update)，2026-10-25 存取）。

**代價（真實發生過的身分分裂）**：

- issue #706「Cross-domain tracking and clearing of LocalStorage」（2022-12-01 開）：回報者在預設設定下看到 `ajs_anonymous_id` 在子網域之間分歧，因為讀取順序「Local Storage => Cookies for TLD => In-Memory」讓**過期的 localStorage 值蓋掉共用 cookie**，「seems to lead to breaking cross-domain tracking for users that at some point deleted their Local Storage」；2023-02-28 另一位使用者稱「This is urgent, as this can break our websites tracking」；**直到 2026-09-10** 才有修正 commit（「fix: anonymousId does not resync once localStorage and the shared coo…」、「fix: make anonymousId cross-subdomain reconciliation the default (#1400)」）；issue 截至存取日仍標示 Open（[analytics-next issue #706](https://github.com/segmentio/analytics-next/issues/706)，2026-10-25 存取）。
- Changelog：**1.84.2**「fixes `anonymousId` diverging between subdomains of the same site (see #706)」，先以 opt-in 旗標出貨，並解釋根因是 localStorage「sits ahead of the shared, cross-subdomain cookie in the default store priority」；**1.84.3** 移除旗標、改為預設：「when the cookie and localStorage disagree on `anonymousId`, the cookie always wins and every store is resynced to it」（[analytics-next `packages/browser/CHANGELOG.md`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/CHANGELOG.md)，2026-10-25 存取）。**一個 2022 年回報的身分分裂 bug，花了近四年才把預設改掉**。

**對 Option Chaser 的含義**：

- Segment 1.84.3 的規則——「authoritative 的那份贏，然後把贏家寫回所有 store」——**就是我們 `issue`／`echo` 兩個旗標做的事**（cookie 不對就 `Set-Cookie`、本機不對就 `X-OC-Credential`）。差別只在 Segment 在 client 端做、我們在伺服器端做；伺服器端做的好處是「贏家」不是任何一份本機副本，而是**資料庫裡真的存在的那顆**。【業界慣例】
- Segment 的 `getConsistent()` 還有一條我們沒有的細節：**「空字串但沒刪掉的 cookie 不能贏」**。我們的對應護欄是 `_well_formed()`（形狀不對「一律當作沒帶 cookie」）——形狀相同的問題、不同層次的解法。【Option Chaser 產品選擇】

### Amplitude Browser SDK 2

**成熟做法**：

- **單一 store，不雙寫**：`identityStorage` 選項「Sets storage API for user identity」，值為 `cookie`（預設，用 `document.cookie`）、`localStorage`、`sessionStorage`、`none`（不持久化身分）；`cookieOptions.expiration` 預設 365 天、`sameSite` 預設 `Lax`、`secure` 預設 `false`（[Amplitude Docs — Browser SDK 2](https://amplitude.com/docs/sdks/analytics/browser/browser-sdk-2)，2026-10-25 存取）。cookie 名為 `AMP_{first_ten_digits_API_KEY}`，內含 `deviceId`（「A random string that persists until the user clears cookies or browses in private mode」）、`sessionId`、`userId`（Base64）、`optOut`、`lastEventTime`、`lastEventId`（同上）；consent 文件補充還有 `pageCounter`、`cookieDomain`，且 `identityStorage: 'none'` 時「Amplitude creates a new `device_id` for that user every time they visit your site because the SDK can't find an existing ID」（[Amplitude Docs — Cookies and consent management](https://amplitude.com/docs/sdks/analytics/browser/cookies-and-consent-management)，2026-10-25 存取）。
- **原始碼的 store 選擇與 deviceId 來源**：`createCookieStorage` 依 `identityStorage` 回傳 `LocalStorage`／`SessionStorage`／`MemoryStorage`／`CookieStorage`（預設）；`useBrowserConfig` 啟動時**讀一次** `previousCookies`，deviceId 的來源鏈結尾是 `options.deviceId ?? (isWithinTimeLimit ? queryParams.ampDeviceId ?? queryParams.deviceId : undefined) ?? ... ?? UUID()`（[Amplitude-TypeScript `packages/analytics-browser/src/config.ts`](https://raw.githubusercontent.com/amplitude/Amplitude-TypeScript/main/packages/analytics-browser/src/config.ts)，2026-10-25 存取）。文件把優先序寫明：「A device ID set in the SDK configuration takes precedence over the URL parameter」，URL 參數自 v2.21.1 起可帶 `ampTimestamp` 限制有效期，過期後「falls back to new values or stored cookie values」（[Amplitude Docs — Browser SDK 2](https://amplitude.com/docs/sdks/analytics/browser/browser-sdk-2)，2026-10-25 存取）。
- **何時產生新 deviceId**：啟動時三個來源都沒有 → `UUID()`；`reset()`「sets `deviceId` to a new UUID」，使用者會「appear to Amplitude as a new user」（[Amplitude Docs — Cookies and consent management](https://amplitude.com/docs/sdks/analytics/browser/cookies-and-consent-management)，2026-10-25 存取）。

**代價**：單一 store 沒有和解問題，代價是**沒有第二份可以救**——cookie 一清就是新人（文件自己說 deviceId「persists until the user clears cookies or browses in private mode」）。Amplitude 選擇把「跨裝置／跨清除」的連結交給 **identity resolution**（登入後用 userId 把多個 device_id 併起來），而不是靠多存一份。

**對 Option Chaser 的含義**：Amplitude 是「不雙寫」陣營的代表，它的答案是「掉了就掉了，靠登入併回來」。這等於 Option Chaser 沒有本機副本之前的狀態（`credentialStore.ts` 註解：「舊版（綁定後就刪掉本機副本、只剩 cookie）正是單點故障」）——UNIFIED-IDENTITY-001 已經刻意離開這個陣營，本文沒有找到回頭的理由。【Option Chaser 產品選擇】

---

## 2. 跨分頁一致：BroadcastChannel／`storage` event／Web Locks，還是靠下一次回應收斂？

### 先把三個瀏覽器原語釘住（規格層）

- **`storage` event**：「The event is _not_ fired on the window that made the change」；對 `localStorage`，「the event is fired in all other browsing contexts that are in the same origin as the initiating document. This includes other tabs with the same origin」（[MDN — Window: storage event](https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event)，2026-10-25 存取）。**它只涵蓋 Web Storage，不涵蓋 cookie 與 IndexedDB**——posthog-js 註解直接寫「Cookies do not emit cross-origin storage events」（[posthog-js `posthog-persistence.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-persistence.ts)，2026-10-25 存取）；IndexedDB 沒有變更事件，所以 Firebase 選擇輪詢（見下）。
- **BroadcastChannel**：「allows basic communication between browsing contexts (that is, _windows_, _tabs_, _frames_, or _iframes_) and workers on the same origin」，精確地說是同一個 storage partition；「Baseline Widely available … available across browsers since March 2022」（[MDN — Broadcast Channel API](https://developer.mozilla.org/en-US/docs/Web/API/Broadcast_Channel_API)，2026-10-25 存取）。HTML 規格 `postMessage()` 第 7 步：「Remove source from destinations」——**發送者自己收不到**（[HTML Living Standard — Web messaging, Broadcasting to other browsing contexts](https://html.spec.whatwg.org/multipage/web-messaging.html)，2026-10-25 存取）。
- **Web Locks**：「While held, no other script executing in the same origin can acquire the same lock, which allows a web app running in multiple tabs or workers to coordinate work」；模式 `exclusive`（預設）／`shared`；Baseline 同樣是 2022 年 3 月（[MDN — Web Locks API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API)，2026-10-25 存取）。規格：「When an agent terminates, terminate remaining locks and requests with the agent」——分頁關掉或崩潰，鎖會釋放；`steal` 選項「Use the steal option with caution」（[W3C Web Locks API](https://w3c.github.io/web-locks/)，2026-10-25 存取）。

### 成熟做法（五家各自的選擇）

**PostHog**：
- **每個分頁有自己的記憶體快照**——PR #4659「feat(browser): sync feature flags across tabs」（2026-09-01 合併，changelog 1.423.0「Synchronize feature flag and early access enrollment persistence across browser tabs」）承認「each tab keeps its own in-memory persistence snapshot」，一個分頁的變更對另一個分頁不可見；修法是監聽 `storage` event，而且**重讀儲存而不是用 `event.newValue`**，因為「queued events can be stale」（[posthog-js PR #4659](https://github.com/PostHog/posthog-js/pull/4659)，2026-10-25 存取；[CHANGELOG](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/CHANGELOG.md)，2026-10-25 存取）。原始碼：`addEventListener(window, 'storage', this._onStorage)`，註解「A queued storage event can be older than the value currently on disk」；另一條註解坦承限制：「localStorage has no atomic read/merge/write operation. This reconciliation …」（[posthog-js `posthog-persistence.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-persistence.ts)，2026-10-25 存取）。
- **身分（cookie）不靠事件，靠「用之前重讀」**：`_writeNow()` 寫入前呼叫 `syncCookieProperties()`（註解「Reconcile immediately before writing as well as before capture」），`register`／`register_once`／`unregister` 也先同步；`identify()` 註解「Adopt any sibling identity first, then make this explicit identify authoritative until its complete replacement cookie is published」；`_reset()` 註解「Publish the reset identity as one complete cookie before another sibling tab can resurrect the pre-reset state」並有 `_beginCookieSyncSuppression()`／`_endCookieSyncSuppression()`（[posthog-js `posthog-core.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-core.ts)、[`posthog-persistence.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-persistence.ts)，2026-10-25 存取）。官方文件的描述：「In an open tab, PostHog checks for shared-cookie changes before captures and persistence writes」，同步發生在「on the tab's next PostHog activity, not immediately」（[PostHog Docs — persistence](https://posthog.com/docs/libraries/js/persistence)，2026-10-25 存取）。Changelog 1.418.7 也記錄了一個跨分頁 consent 的坑：「A tab that missed a cross-tab consent flip could emit the sentinel as a durable distinct_id」，修成「adopts the identity persisted by the tab that handled consent」；1.434.4：「Fix `$session_id` being sent as `null` when a sibling tab resets the session before this tab captures its first event」（[CHANGELOG](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/CHANGELOG.md)，2026-10-25 存取）。
- **沒有 BroadcastChannel、沒有 navigator.locks**（`storage.ts`、`posthog-persistence.ts`、`posthog-core.ts` 可見部分皆無）。

**Segment**：**什麼都不監聽**——`user/index.ts` 沒有 `storage` 監聽、沒有 BroadcastChannel；但 `User` 類別**不把 anonymousId 放在記憶體欄位**，`anonymousId()` 每次呼叫都走 `identityStore.getConsistent()` 重讀儲存（[analytics-next `user/index.ts`](https://raw.githubusercontent.com/segmentio/analytics-next/master/packages/browser/src/core/user/index.ts)，2026-10-25 存取）。這是「用之前重讀」的極致版：**沒有可以過期的記憶體副本，就不需要同步**。

**Amplitude**：啟動時讀一次 `previousCookies`，之後 `BrowserConfig` 的 getter「only return private fields」（`get deviceId() { return this._deviceId; }`），setter 寫入欄位後呼叫 `updateStorage()`，由 `this.cookieStorage.set(getCookieName(this.apiKey), cache)` **整包覆寫**（[Amplitude-TypeScript `config.ts`](https://raw.githubusercontent.com/amplitude/Amplitude-TypeScript/main/packages/analytics-browser/src/config.ts)，2026-10-25 存取）；`browser-client.ts` 判斷新 session 用的是 `this.config.lastEventTime`（記憶體），沒有從儲存重讀（[Amplitude-TypeScript `browser-client.ts`](https://raw.githubusercontent.com/amplitude/Amplitude-TypeScript/main/packages/analytics-browser/src/browser-client.ts)，2026-10-25 存取）。本文在這兩個檔案與官方文件中**都沒有找到**任何跨分頁機制——結論是「無同步、last writer wins」，但這是從原始碼缺席推論的負面結論（UNVERIFIED #4）。

**Supabase auth-js**（真正做即時同步的一家）：
- **BroadcastChannel**：條件 `if (isBrowser() && globalThis.BroadcastChannel && this.persistSession && this.storageKey)` 時 `this.broadcastChannel = new globalThis.BroadcastChannel(this.storageKey)`；廣播內容只有 `{ event, session }`；收到時 `await this._notifyAllSubscribers(event.data.event, event.data.session, false)`，註解「broadcast = false so we don't get an endless loop of messages」；建立失敗時警告「Failed to create a new BroadcastChannel, multi-tab state changes will not be available」（[auth-js `src/GoTrueClient.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/GoTrueClient.ts)，2026-10-25 存取）。
- **Web Locks**：`else if (isBrowser() && globalThis?.navigator?.locks)` → `this.lock = navigatorLock`，否則 `lockNoOp`；建構子警告多實例「may produce undefined behavior when used concurrently under the same storage key」（同上）。
- **只有可見分頁跑 refresh ticker**：註解說 ticker「runs only on focused tabs」以「prevents race conditions」；`visibilitychange` 從 hidden→visible 時「we need to see if the session should be recovered immediately... but to do that we need to acquire the lock first asynchronously」（同上）。

**Firebase Auth**（另一家做即時同步，用的是輪詢）：
- 官方文件：「Any attempt to sign in using `local` persistence will be detected and synchronized on all tabs」（[Firebase Docs — Authentication State Persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence)，2026-10-25 存取）。
- 實作：IndexedDB 後端 `export const _POLLING_INTERVAL_MS = 800;`，`_poll()` 讀出 object store 全部紀錄、用 `JSON.stringify` 比對本機快取、不同就 `notifyListeners`，有 pending write 時跳過這一輪（註解「If we have pending writes in progress abort, we'll get picked up on the next poll」）；service worker 情境另用 `Sender`／`Receiver` postMessage，因為「IndexedDB events do not propagate from the main window to the worker context」（[firebase-js-sdk `platform_browser/persistence/indexed_db.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/platform_browser/persistence/indexed_db.ts)，2026-10-25 存取）。localStorage 後端用 `window.addEventListener('storage', this.boundEventHandler)`，但行動瀏覽器改用 1000 ms 輪詢，註解「Whether browser can detect storage event when it had already been pushed to the background」（iOS 7.x 時代的觀察）（[firebase-js-sdk `local_storage.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/platform_browser/persistence/local_storage.ts)，2026-10-25 存取）。`auth_impl.ts` 的 `_onStorageEvent` 註解：「If the persistence is changed in another window, the user manager will let us know」（[firebase-js-sdk `core/auth/auth_impl.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/core/auth/auth_impl.ts)，2026-10-25 存取）。

### 代價

- **即時同步的理由跟「state 會不會自己變」成正比**。Supabase／Firebase 同步的是**每小時輪替的 token 與登入／登出事件**（Firebase ID token「last for an hour」、refresh 前 30 秒 buffer；Supabase 每 30 秒 tick、提前 3 個 tick refresh——見第 3 題），多分頁同時 refresh 會踩到一次性 refresh token。分析 SDK 的身分值幾乎不變，所以兩家都只做「用之前重讀」。
- **即時同步自己也有坑**：PostHog 必須重讀儲存而不能信 `event.newValue`（事件可能過期）；Supabase 要用 `broadcast=false` 防迴圈；Firebase 要處理「pending write 期間跳過輪詢」與 service worker 不收 IndexedDB 事件。每一個都是**多一個狀態來源就多一組競態**。

### 對 Option Chaser 的含義

- 我們的憑證**只在登入／登出時改變**（第 0 節），所以我們的情境比較像 PostHog／Segment 的「身分值幾乎不變」，不像 Supabase／Firebase 的「token 每小時換」。【Option Chaser 產品選擇】
- 我們**已經在用 Web Locks**（`withOwnerBindingLock`）處理「還沒綁定前的並發寫入」——這正是 Supabase 用 `navigator.locks` 解的同一類問題（多分頁同時做會改變身分的寫入）。這部分跟業界一致。【業界慣例】
- 我們**沒有**的，是 PostHog 1.423.0 之後補上的那一塊：**分頁的記憶體副本（`cached`／`bound`）永遠不重讀本機儲存**。在「cookie jar 共用」的前提下，這通常無害（stale 分頁送舊 header，伺服器以新 cookie 為準並 echo 正確值）。本文能找到它會出問題的場景只有一種雙重故障：另一個分頁登入／登出**換了憑證**（舊 token 已被 `delete_browser_identity`），**且** cookie 不在（被清、或請求沒帶上）——此時 stale 分頁的請求兩份都查不到，被當成未綁定，`candidate = stored_token`（它記憶體裡那顆**已作廢**的舊 token），而且回應不會 echo（`echo=False`）、也不會帶 `X-OC-Owner-Bound`，所以它**永遠學不到正確的憑證**；它的下一次寫入會把舊 token 綁到一個新 user——這就是身分分裂。另一個較溫和的變體是登出後兩個分頁同時第一次寫入：stale 分頁的 `bound` 旗標仍為 true，跳過 `withOwnerBindingLock`，兩邊各自 `claim_browser_token` 不同的 token、建出兩個匿名 user，之後靠共用 cookie 收斂到最後一個 `Set-Cookie` 的那個，另一個成為孤兒。兩個場景都窄，但都是**「記憶體副本不重讀」**這一個根因。第 6 節的建議就針對它。【Option Chaser 產品選擇】

---

## 3. 匿名 session 的續命：Supabase anonymous sign-ins 與 Firebase Anonymous Auth

### Supabase

**成熟做法**：

- **存哪裡**：預設 `this.storage = globalThis.localStorage`（`supportsLocalStorage()` 為真時），否則退回記憶體 adapter；supabase-js 把 key 設為 `` `sb-${baseUrl.hostname.split('.')[0]}-auth-token` ``（[auth-js `GoTrueClient.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/GoTrueClient.ts)；[supabase-js `packages/core/supabase-js/src/SupabaseClient.ts`](https://raw.githubusercontent.com/supabase/supabase-js/master/packages/core/supabase-js/src/SupabaseClient.ts)，2026-10-25 存取）。預設 `autoRefreshToken: true, persistSession: true, detectSessionInUrl: true, flowType: 'implicit'`（[supabase-js `lib/constants.ts`](https://raw.githubusercontent.com/supabase/supabase-js/master/packages/core/supabase-js/src/lib/constants.ts)，2026-10-25 存取）。存進去的 session 必須有 `access_token`、`refresh_token`、`expires_at` 三個鍵才算有效（`_isValidSession`）（[auth-js `GoTrueClient.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/GoTrueClient.ts)，2026-10-25 存取）。
- **過期規則**：型別註解——`refresh_token`：「A one-time used refresh token that never expires」（[auth-js `src/lib/types.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/lib/types.ts)，2026-10-25 存取）。Sessions 文件：refresh tokens「never expire but can only be used once」；預設 session「last indefinitely」；refresh 有 10 秒 reuse interval，在此之外重用「terminates the whole session and revokes all of its refresh tokens」；Pro 以上可設 time-box／inactivity timeout／single session，「Expired sessions are deleted from the database 24 hours after they expire」（[Supabase Docs — User sessions](https://supabase.com/docs/guides/auth/sessions)，2026-10-25 存取）。Client 端每 `AUTO_REFRESH_TICK_DURATION_MS = 30 * 1000` 檢查一次、提前 `AUTO_REFRESH_TICK_THRESHOLD = 3` 個 tick refresh（[auth-js `src/lib/constants.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/lib/constants.ts)，2026-10-25 存取）。
- **匿名使用者的特別規則**：JWT 帶 `is_anonymous` claim；**沒有自動清理**，文件給的是手動 SQL `delete from auth.users where is_anonymous is true and created_at < now() - interval '30 days'`（**以建立時間、不以活動時間**計）；匿名登入端點有「An IP-based rate limit is enforced at 30 requests per hour」；文件明講後果：「the user can't access their account if they sign out, clear browsing data, or use another device」（[Supabase Docs — Anonymous Sign-Ins](https://supabase.com/docs/guides/auth/auth-anonymous)，2026-10-25 存取）。
- **被清掉時 SDK 的行為與事件**：`_recoverAndRefresh` 對 refresh 失敗的分支——`if (!isAuthRetryableFetchError(error))` → log「refresh failed with a non-retryable error, removing the session」→ `await this._removeSession()`；`_callRefreshToken` 同樣規則。`_removeSession()` 移除 `storageKey`、`-code-verifier`、`-user`，然後 `await this._notifyAllSubscribers('SIGNED_OUT', null)`——`broadcast` 預設 true，所以**其他分頁也收到 `SIGNED_OUT`**（[auth-js `GoTrueClient.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/GoTrueClient.ts)，2026-10-25 存取）。「可重試」的定義很窄：fetch 本身失敗（註解「fetch failed, likely due to a network or CORS error」）或 `NETWORK_ERROR_CODES = [502, 503, 504]`；其他一律是 `AuthApiError`（[auth-js `src/lib/fetch.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/lib/fetch.ts)，2026-10-25 存取）。對應的伺服器錯誤碼：`refresh_token_not_found`「Session containing the refresh token not found」、`session_not_found`「Session to which the API request relates no longer exists」、`user_not_found`「User to which the API request relates no longer exists」（[Supabase Docs — Error Codes](https://supabase.com/docs/guides/auth/debugging/error-codes)，2026-10-25 存取）。
- **首訪長什麼樣**：`onAuthStateChange` 訂閱後由 `_emitInitialSession` 發 `INITIAL_SESSION`，有 session 帶 session、沒有帶 `null`（[auth-js `GoTrueClient.ts`](https://raw.githubusercontent.com/supabase/auth-js/master/src/GoTrueClient.ts)，2026-10-25 存取）。

**代價**：refresh token 永不過期聽起來像「永久匿名身分」，但它活在 localStorage——清除站台資料就沒了，且匿名 user 若被上面那段 SQL 刪掉，client 下一次 refresh 拿到 4xx → `SIGNED_OUT`。**沒有「這是匿名使用者遺失」的專屬事件**，app 只能從「我沒有呼叫 `signOut()` 卻收到 `SIGNED_OUT`」推論。

### Firebase

**成熟做法**：

- **存哪裡**：web 預設 persistence 順序 `[indexedDBLocalPersistence, browserLocalPersistence, browserSessionPersistence]`（[firebase-js-sdk `platform_browser/index.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/platform_browser/index.ts)，2026-10-25 存取）；IndexedDB 名稱 `firebaseLocalStorageDb`、object store `firebaseLocalStorage`（[`indexed_db.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/platform_browser/persistence/indexed_db.ts)，2026-10-25 存取）；持久化的 user 物件內含 `stsTokenManager.toJSON()` ＝ `{ refreshToken, accessToken, expirationTime }`，提前 `Buffer.TOKEN_REFRESH = 30_000` ms 換新（[`core/user/token_manager.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/core/user/token_manager.ts)，2026-10-25 存取）。
- **過期規則**：ID token「short lived and last for an hour」；refresh token「expire only when one of the following occurs」——user 被刪除、被停用、「A major account change is detected」（密碼／email 更新）、管理員呼叫 `revokeRefreshTokens`；「On revocation, the user is signed out and prompted to reauthenticate」（[Firebase Docs — Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)，2026-10-25 存取）。
- **匿名帳號的自動清理**：僅限升級到 Identity Platform 的專案可開啟，「anonymous accounts older than 30 days will be automatically deleted」；已連結任何登入方式的帳號不會被刪；開啟後匿名帳號不計入用量上限（[Firebase Docs — Authenticate with Firebase Anonymously](https://firebase.google.com/docs/auth/web/anonymous-auth)，2026-10-25 存取）。
- **被清掉時 SDK 的行為**：`_logoutIfInvalidated()` 包住 `getIdToken`／`delete`，`_isUserInvalidated()` 只認兩個錯誤碼：`auth/user-disabled` 與 `auth/user-token-expired`，命中就 `await user.auth.signOut()`（[firebase-js-sdk `core/user/invalidation.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/core/user/invalidation.ts)，2026-10-25 存取）。伺服器錯誤對應表把 `TOKEN_EXPIRED` **與 `USER_NOT_FOUND` 都映射到 `AuthErrorCode.TOKEN_EXPIRED`**（[`api/errors.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/api/errors.ts)，2026-10-25 存取），即 `'user-token-expired'`，訊息「The user's credential is no longer valid. The user must sign in again.」（[`core/errors.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/core/errors.ts)，2026-10-25 存取）——所以**匿名 user 被 30 天清理刪掉後，下一次 refresh 會讓 SDK 自動登出**，`onAuthStateChanged` 收到 `null`。
- **啟動時的「被誤殺」史**：issue #10438「a transient 5xx (UNAVAILABLE) on the initial accounts:lookup still clears the persisted user」——首次 `accounts:lookup` 回 503 時「`onAuthStateChanged` emits `null` and the persisted user is removed from IndexedDB」，任何非 `auth/network-request-failed` 的錯誤都會觸發；前一個修正 #10418（2026-10-02 合併）只豁免 quota／too-many-requests；#10438 於 2026-10-08 由 PR #10462「fix(auth): only clear persisted user on invalidation errors during in…」關閉（[firebase-js-sdk issue #10438](https://github.com/firebase/firebase-js-sdk/issues/10438)，2026-10-25 存取）。`main` 分支現在的 `reloadAndSetCurrentUserOrClear`：`if (_isUserInvalidated(e)) { // Something's wrong with the user's token. Log them out and remove them from storage ... return this.directlySetCurrentUser(null); }`，其他錯誤保留 user（[`core/auth/auth_impl.ts`](https://raw.githubusercontent.com/firebase/firebase-js-sdk/main/packages/auth/src/core/auth/auth_impl.ts)，2026-10-25 存取）。

**代價**：一個成熟到極致的 SDK，**直到 2026 年 10 月都還會因為一次暫時性 503 把持久化的匿名身分刪掉**。這是「client 端一收到任何錯誤就清本機副本」的反面教材——與 Option Chaser 伺服器端「兩份都查不到也**不建立**、也不清除」的 deferred creation 形成對照。

### 對 Option Chaser 的含義

- 兩家都把 refresh token 存在**單一**本機儲存（localStorage／IndexedDB）、沒有 HttpOnly cookie 那份。我們多了 cookie 那份，所以「清除站台資料」在我們這裡要同時清掉 cookie 與 IndexedDB／localStorage 才會失去身分——瀏覽器的「清除站台資料」通常一起清，但「只清 cookie」或「只清儲存」的路徑在我們這裡仍能存活，在兩家 auth SDK 都不能。【Option Chaser 產品選擇】
- 兩家的「匿名使用者遺失」事件都是**從既有的登出事件推論**（Supabase `SIGNED_OUT`、Firebase `onAuthStateChanged(null)`），沒有專屬事件；要當指標，都得在 app 層記「我剛才有沒有主動登出」。我們若要做指標，**伺服器端比 client 端更適合**——見第 4 題。【業界慣例】
- Firebase #10438 的教訓直接適用於 `credentialStore.ts`：**任何「收到錯誤就清本機副本」的邏輯都是身分遺失的來源**。目前 `storeCredential()` 只在伺服器 echo 時寫入、沒有任何清除路徑；本文建議維持這個性質。【Option Chaser 產品選擇】

---

## 4. 部分遺失的可觀測性：分得出「首訪」與「曾有 id 但現在不認得」嗎？有人告訴使用者嗎？

**成熟做法**：

- **分析 SDK：結構上分不出來**。三家的 id 都由 client 自己 mint（PostHog `uuidv7()`、Segment `uuid()`、Amplitude `UUID()`，見第 1 題），伺服器端沒有「已核發 id 的登錄表」可以拒絕；PostHog 唯一的區分是「匿名 vs 已 identify」（`USER_STATE`，「distinct id == $device_id is a proxy for an anonymous user」，[posthog-js `posthog-core.ts`](https://raw.githubusercontent.com/PostHog/posthog-js/main/packages/browser/src/posthog-core.ts)，2026-10-25 存取），**不是**「首訪 vs 遺失」。它們把身分遺失當成分析誤差（issue #706「breaking cross-domain tracking」、#5166「users split」），修法是改和解規則，不是偵測。
- **Auth SDK：協定層分得出，但不包裝成專屬事件**。Supabase 首訪只會收到 `INITIAL_SESSION` + `null`；「曾有 session、refresh 被拒」會收到 `SIGNED_OUT`（並廣播其他分頁），且錯誤碼能區分 `refresh_token_not_found`／`session_not_found`／`user_not_found`（第 3 題）。Firebase 首訪 `onAuthStateChanged(null)`；「曾有 user、token 失效」是 `_isUserInvalidated` → `signOut()` → **同樣 `null`**，差別只在 `getIdToken()` 拋出的錯誤碼（`auth/user-token-expired`）——app 不接那個錯誤就看不出差別（第 3 題）。
- **有沒有產品告訴使用者**：Supabase 文件把它寫成使用者須知（「can't access their account if they sign out, clear browsing data, or use another device」），Firebase 文件說「the user is signed out and prompted to reauthenticate」（那是登入制產品的做法，不是匿名）。本文以多組關鍵字搜尋**沒有找到任何匿名優先產品在 UI 上主動說「你之前的匿名資料找不到了」**（UNVERIFIED #9）。

**代價**：不區分「首訪」與「遺失」，代價是**bug 與正常流量混在同一個數字裡**——Firebase #10438 那種「SDK 自己把 user 清掉」的回歸，在 `onAuthStateChanged(null)` 的層次上完全不可見，要靠使用者抱怨才發現。

**對 Option Chaser 的含義**：

- **我們的伺服器今天就分得出三種情況，而且不花一分錢**：`_resolve_owner_for_request()` 的「都查不到」分支裡，`cookie_token`／`stored_token` 兩者皆 `None` ＝ 真正首訪；任一者非空但 `resolve_credential()` 都回 `None` ＝「client 自以為有身分、伺服器不認得」。後者又分兩類：登出剛換發的**未綁定**新 token（預期、`issue=True, echo=True` 當下就已經交回去）與**真正遺失**（資料庫沒有這顆、client 也不是剛登出）。目前這個分支只在 `materialize()` 真的建 user 時記 `new_owner_count`。一個 `unknown_credential_count`（或拆成 cookie-only／header-only／both 三個維度）就是 Firebase／Supabase 都沒有、而我們能免費擁有的「遺失指標」。這是**唯一**本文建議立刻做的觀測項（不是功能、不改語意）。【Option Chaser 產品選擇】
- 要不要告訴使用者：業界沒有先例可抄。本文的判斷是，**在有上面那個指標之前不要做 UI**——沒有數字，不知道這件事多常發生、也無法驗證 UI 文案有沒有幫助。【Option Chaser 產品選擇】

---

## 5. WebAuthn／passkey 作為零註冊的裝置身分錨點

> 票面要求「只要結論與代價，不要實作細節」。本節不含任何 API 呼叫形狀。

**成熟做法／規格允許什麼**：

- **匿名的 user handle 是規格本意**：「A user handle is an opaque byte sequence with a maximum size of 64 bytes, and is not meant to be displayed to the user」，且「MUST NOT contain personally identifying information about the user」（§5.4.3，[W3C Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/)，2026-10-25 存取）。所以「用一顆隨機值當 handle、不綁任何帳號」在規格上是正統用法，不是 hack。
- **跨裝置同步由平台提供**：Apple——「Because passkeys are synced with iCloud Keychain, they're available across Apple devices」、「In iCloud Keychain, passkeys are end-to-end encrypted, so even Apple can't read them」、「Passkeys are intrinsically linked with the app or website they were created for」（[Apple Developer — Passkeys](https://developer.apple.com/passkeys/)，2026-10-25 存取）。規格層把這叫 multi-device credential（「A backup eligible public key credential source is referred to as a multi-device credential」，BE／BS 旗標）（[WebAuthn L3 §4](https://www.w3.org/TR/webauthn-3/)，2026-10-25 存取）。
- **最接近的真實先例是「匿名地用 WebAuthn」，不是「用 WebAuthn 當身分」**：Cloudflare 的 Cryptographic Attestation of Personhood 用「WebAuthn registration process」的 attestation 取代 CAPTCHA，明講「we're not interested in *which* human you are」，攻擊面刻意限制在「your key looks like all other keys in the batch」（FIDO 要求每批「100,000 or more keys」）、「A constant value is used for the username field to protect against deanonymization」，整個流程「at most three clicks」、「five seconds」對比 CAPTCHA 32 秒（[Cloudflare Blog — Introducing Cryptographic Attestation of Personhood](https://blog.cloudflare.com/introducing-cryptographic-attestation-of-personhood/)，2026-10-25 存取）。開發者文件（2026-09-04 更新）仍列為可用，支援 Touch ID／Face ID／Android 指紋／Windows Hello 等平台 authenticator，並說明「biometric data stays on the device」，但 Cloudflare 會收到「the manufacturer and a batch identifier」（[Cloudflare Docs — Cryptographic Attestation of Personhood](https://developers.cloudflare.com/fundamentals/reference/cryptographic-personhood/)，2026-10-25 存取）。**它刻意不把 WebAuthn 當身分錨——正因為一旦當身分錨，就必須存下可以關聯回訪的 credential ID**。
- **用 passkey 當匿名身分錨的產品**：本文以多組關鍵字搜尋，**沒有找到**任何一個（UNVERIFIED #10）。

**代價（規格層面，無法繞過）**：

- **每次回訪一定要使用者動手**：`authenticatorGetAssertion`——「Authorization gestures MUST include a test of user presence when requireUserPresence is true」；使用者不同意即回 `NotAllowedError`（§6.3.3）；規格在 Credential Management 整合處明講 `preventSilentAccess()` 對 PublicKeyCredential 沒有作用，「since they always require user interaction」，且「this specification requires an authorization gesture to create any assertions」（[WebAuthn L3](https://www.w3.org/TR/webauthn-3/)，2026-10-25 存取）。即使把 `userVerification` 設成 `discouraged`（不要生物辨識），**user presence（按一下、點一下）仍不可免**；平台 authenticator 實務上就是 Face ID／Touch ID／裝置鎖對話框（Apple：「signing in with passkeys uses AutoFill and Face ID or Touch ID for biometric verification」，[Apple Developer — Passkeys](https://developer.apple.com/passkeys/)，2026-10-25 存取）。
- **「靜默建立」存在，但前提是已經有密碼登入**：Chrome 的 Conditional Create「lets your site request a passkey for the user without requiring any action from them」，但前提是「The user has a saved password in their default password manager」且「The password was used recently」，建立結果的「User Verified」為 false（[Chrome Developers — Conditional Create](https://developer.chrome.com/docs/identity/webauthn-conditional-create)，2026-10-25 存取）。匿名使用者沒有密碼、沒有 password manager 紀錄，這條路不適用；而且它只省掉**建立**時的提示，**回訪的 `get()` 仍受上一條約束**。
- **UX 指南本身就反對在非帳號情境打斷使用者**：FIDO／passkeycentral 原則 1——「When people are already in an account management mindset … they are more likely to perceive the option to create a passkey as a relevant enhancement to their site experience … rather than an unwelcome interruption or barrier to accomplishing other core site tasks, such as shopping」；原則 3——「Before triggering the passkeys OS dialogs, display passkeys messages, icons, and actions」（[Passkey Central — Design Guidelines: Principles](https://www.passkeycentral.org/design-guidelines/principles)，2026-10-25 存取）。Google 同樣建議把建立提示放在「account-related tasks」旁（登入後、安全設定、帳號復原、重新驗證）（[Google Identity — Passkeys user journeys](https://developers.google.com/identity/passkeys/ux/user-journeys)，2026-10-25 存取）。**一個沒有帳號概念的匿名工具，連「帳號管理心態」這個觸發點都不存在**。
- **「跨裝置」是雙面刃**：passkey 的跨裝置來自使用者的 Apple／Google 帳號同步。對一個標榜匿名的產品，這代表「匿名身分」的可恢復性**實際上綁在使用者的平台帳號上**；在沒有同步（例如硬體金鑰、或關閉 iCloud Keychain）的裝置上，它是 device-bound，掉了就掉了——跟 cookie 沒有差別，卻多了每次按一下的成本。

**結論**：passkey 在規格上**能**當匿名錨（隨機 user handle 合法、同步免費），但**與「零使用者負擔」不相容**——每次恢復都要一個授權手勢，這是規格的 MUST，不是實作選擇；而且沒有任何產品先例，最接近的 Cloudflare 案例刻意避開「當身分」這個用途。它適合的位置是**「使用者主動要求的跨裝置恢復」**（取代 claim link 的一種選項，屆時再與既有研究的 claim link 比較），不是預設的身分儲存。【規格／安全必要】＋【Option Chaser 產品選擇】

---

## 6. 建議：跨分頁即時同步（BroadcastChannel）要不要做？

**建議：不要為此引入 BroadcastChannel；要補的是「分頁記憶體副本不重讀本機儲存」這一個缺口，而且用更便宜的原語就夠。**

論證（每一條都回指上面的證據）：

1. **業界做即時同步的是「state 會自己變」的 SDK**。Supabase／Firebase 要同步的是每小時輪替的 token 與登入／登出事件，而且多分頁同時 refresh 會踩到一次性 refresh token（第 3 題：Supabase 的 refresh token「can only be used once」、10 秒 reuse interval 外就「terminates the whole session」）。我們的憑證**只在登入／登出時變**，沒有週期性輪替，沒有「兩個分頁同時 refresh」這個競態。BroadcastChannel 解的主要問題，我們沒有。【Option Chaser 產品選擇】
2. **身分值幾乎不變的 SDK，兩家都選「用之前重讀」而非廣播**。Segment 乾脆不留記憶體副本（`anonymousId()` 每次走 `getConsistent()`）；PostHog 2026 年用 `storage` event 補同步、cookie 身分則是「before captures and persistence writes」重讀，文件明說是「on the tab's next PostHog activity, not immediately」（第 2 題）。**沒有任何一家分析 SDK 用 BroadcastChannel 同步身分。**【業界慣例】
3. **我們現有的收斂機制已經覆蓋多數 stale 分頁情境**，因為 cookie jar 是所有分頁共用的：stale 分頁送舊 header＋新 cookie → 伺服器 cookie 優先 → echo 正確值 → `storeCredential()`。這等價於 Segment 1.84.3 的「cookie 贏、其他 store 重新對齊」。【Option Chaser 產品選擇】
4. **真正的缺口只有一個根因**（第 2 題末）：`credentialStore.ts` 的 `cached`／`bound` 在分頁生命週期內永不重讀。它在「另一分頁換了憑證 **且** cookie 不在」時讓 stale 分頁永遠學不到正確憑證，進而可能把已作廢的 token 綁到新 user；在「登出後兩分頁同時首次寫入」時讓 stale 分頁跳過 `withOwnerBindingLock`。這兩個都是 PostHog PR #4659 承認的同一句話：「each tab keeps its own in-memory persistence snapshot」。
5. **補這個缺口不需要 BroadcastChannel**。兩個候選，都是瀏覽器免費提供、與我們已在用的 Web Locks 同一代（Baseline 2022-03）的原語，而且**不新增任何狀態來源**（BroadcastChannel 會多一個訊息通道，等於多一組「訊息 vs 儲存誰新」的競態——Supabase 得用 `broadcast=false` 防迴圈、PostHog 得重讀儲存不能信 `event.newValue`）：
   - **(a) 伺服器說「未綁定」就重讀**：回應沒有 `X-OC-Owner-Bound: 1` 時，把這個分頁的 `cached`／`bound` 設回未讀狀態，下一次 `send()` 重新走 `credential()` 讀 IndexedDB（另一分頁 `storeCredential()` 寫進去的新值就在那裡）。零新 API、零事件、只改 `src/credentialStore.ts`／`src/api.ts` 的分頁內狀態機；代價是 stale 分頁要多一次請求才收斂（跟 PostHog「下一次活動時同步」同級）。
   - **(b) 監聽 localStorage 鏡像鍵的 `storage` event**：`oc_owner_bootstrap` 鍵在另一分頁被 `mirrorToLocalStorage()` 改寫時，本分頁收到事件 → 重讀（**重讀儲存、不信 `event.newValue`**，照 PostHog 的教訓）→ 更新 `cached`、把 `bound` 設回 false。代價是多一個監聽器與「事件可能過期」的處理；好處是收斂不必等下一次請求。
   - 本文傾向 **(a) 先做、(b) 視指標再說**——理由是 (a) 直接對應第 4 題建議的 `unknown_credential_count` 指標：有了指標才知道這個缺口多常被踩到，再決定 (b) 值不值得。
6. **做 BroadcastChannel 的唯一正當理由**是未來若憑證開始**週期性輪替**（例如 OWASP 式的定期 rotation，既有研究第 3 題已把它標為「業界慣例的延伸，不是 OWASP 字面要求」）。到那時 Supabase 的形狀（頻道名＝storage key、只廣播 `{event, token}`、收到就重讀、`broadcast=false` 防迴圈、Web Locks 包住輪替）是現成可抄的；在那之前，它是為一個我們沒有的問題付成本。【Option Chaser 產品選擇】

**不在本建議範圍內、但第 4 題已提出的零成本項**：伺服器端 `unknown_credential_count`（有帶 token 但查不到）——它同時是這個建議的驗收指標。

---

## UNVERIFIED（本文誠實列出、可能重要的未查證項目）

1. **WebAuthn L3 §14 Privacy Considerations 的逐字內容**（「User Handle Contents」、「Anonymous, Scoped, Non-correlatable Public Key Credentials」、「Credential ID Unsigned」等）——本次工具對 `w3.org/TR/webauthn-3/` 與 `w3c.github.io/webauthn/` 的擷取都在約 503k 字元處截斷於 §7.2，§14 無法逐字讀到。本文對 user handle 的引用改取 §5.4.3 的規範文字（「MUST NOT contain personally identifying information about the user」，該節並明確指向 §14.6.1）。§14 是否有本文未納入、會改變第 5 題結論的內容，本次未查證。
2. **posthog-js 的 cookie 身分同步機制（`syncCookieProperties()`、`_cpm` sidecar cookie、sync suppression）首次出現的版本**——以上皆讀自 `main` 分支原始碼（2026-10-25），changelog 前 200k 字元只找到 1.418.0（`cookieWinsOnConflict`）、1.418.7（跨分頁 consent）、1.423.0（flags `storage` event）、1.434.4（sibling tab reset）四條相關紀錄；`syncCookieProperties` 本身的版本未定位。
3. **PostHog `cookieWinsOnConflict` 對 `defaults >= '2026-08-29'` 預設開啟**——此說法來自**未合併、被 stale bot 關閉**的 PR #5030 描述；官方文件只說 `defaults` 未設時預設關閉。兩者可以同時為真，但「新 defaults 預設開」這一點本次只有 PR 描述這個來源。
4. **Amplitude Browser SDK 2 沒有任何跨分頁同步機制**——這是從 `config.ts`／`browser-client.ts` 原始碼與官方文件都**缺席**推論的負面結論；本次搜尋也沒有找到相關 GitHub issue。未排除有其他檔案（例如 session 相關 plugin）處理此事。
5. **Segment analytics-next 1.84.2／1.84.3 是否已發佈至 npm**——changelog 讀自 `master` 分支且**不含日期**；issue #706 截至存取日仍 Open，修正 commit 日期為 2026-09-10。
6. **Firebase securetoken 端點對「已刪除的使用者」實際回傳 `USER_NOT_FOUND` 還是 `TOKEN_EXPIRED`**——SDK 端兩者都映射到 `auth/user-token-expired`（已驗證），所以結論（會自動登出）不受影響，但伺服器端的實際錯誤碼未查證。
7. **Firebase PR #10462 的發佈版本**——issue 頁面只顯示 2026-10-08 關閉，未標版本；回報時的版本是 Firebase JS SDK 12.19.0／`@firebase/auth` 1.13.6。
8. **Supabase GoTrue 伺服器對 `refresh_token_not_found`／`user_not_found` 回傳的 HTTP 狀態碼**——本文假設為 4xx（因此落在 `isAuthRetryableFetchError` 之外、觸發 `SIGNED_OUT`），這與錯誤碼文件的語意一致，但未從 GoTrue 伺服器原始碼確認。
9. **「沒有任何產品把匿名身分遺失告訴使用者」**——負面結論，基於多組英文關鍵字搜尋皆無命中；不排除有本次搜尋範圍外的產品。
10. **「沒有任何產品用 passkey 當匿名身分的恢復錨」**——同樣是負面搜尋結論。
11. **Chrome Conditional Create 的首發版本**——官方頁面未標版本，只連到「New in Chrome 136」文章，本文據此推論為 136。
12. **FIDO Alliance passkey UX 研究的參與者人數（搜尋摘要稱 26 人）**——passkeycentral 頁面只寫「60 to 90-minute one-on-one remote interviews via Zoom」、重複四輪、受訪者 18–70 歲美國消費者，未標人數；本文正文因此不引用人數。
13. **Supabase access token 的預設壽命**——本次只確認 sessions 文件說 access token「short-lived」，未直接讀取 CLI config 參考頁上的預設秒數，正文不引用具體數字。
