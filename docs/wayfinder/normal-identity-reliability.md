# Normal User 身分可靠性 — 現況評估、風險缺口、方案與施工拆解

> **OPTION-CHASER-NORMAL-IDENTITY-RELIABILITY-001 ／ 回報#137 ／ 2026-10-25（台灣）**
>
> 狀態：**研究＋設計＋規劃，本輪不施工。** Wayfinder 地圖 **#359**；決策票 #360～#364、研究票 #365／#366、Task 票 #367（Production 稽核）。本文件是地圖 Destination 指向的規格草案——§4 的施工票（NIR-01～NIR-10）在 §9 的決策票關閉後才開成 GitHub issue，以免被尚未裁示的決定改寫。「老弟建議」不是 Owner Decision，任何未來 session 不得混用。
>
> 依據：`api_app/main.py`（`_resolve_owner_for_request`／`_call_within_owner_scope_inner`／`_login_main_account`／`auth_reset_role`／`delete_my_data`／`cron_cleanup_abandoned_owners`）、`api_app/identity.py`、`api_app/anonymous_lifecycle.py`、`api_app/storage/{__init__,postgres}.py`、`src/credentialStore.ts`、`src/api.ts`、`tests/test_identity_*.py`、`tests/test_unified_identity_001.py`、`tests/test_cross_device_account.py`、`e2e/owner-bootstrap.spec.ts`、`docs/research/anonymous-identity-session-patterns.md`、PR #346／#355／#358、回報#136。

---

## 0. 一頁摘要（給 Owner）

- **現有架構是對的，不需要推翻。** 「不透明 token＋伺服器查表、同一顆 token 存兩份（HttpOnly cookie＋本機副本）、每次回應收斂、第一次寫入才建立 user、PK 原子綁定」這套骨架已經涵蓋九種完成標準裡的七種半（§1d）。過去三輪分裂（每次請求重簽 cookie、本機副本綁定後被刪、權限掛 owner 導致每台裝置一個 SU）都已在 PR #346／#355／#358 修掉。
- **真正剩下的缺口是「邊緣」而不是「骨架」**（§2）：① 身分遺失與首訪無法區分、不可觀測；② cookie 簽一次固定 400 天＝第 400 天斷崖，而本機副本是較弱的一腿；③ 本機副本沒有要求持久化、IndexedDB 卡住會讓整站停住；④ 三個 Production 網址各自一個身分；⑤ 查無此 token 時沿用舊 token 綁新 owner，讓診斷失真。
- **方案**（§3）：保留骨架，補五件事——憑證耐久性（門檻式續簽、IndexedDB 逾時退路；`persist()` 經 #365 查證不採用）、單一正式網址、身分狀態訊號＋墓碑、身分健康指標、真瀏覽器持久性酷刑測試。十張施工票（§4），其中五張不等任何決策就能開工。兩張研究票都已回填：#366——不加 BroadcastChannel，改修分頁快取失效的單一根因（§3.7）；#365——Safari ITP 只吃本機腿、400 天上限只吃 cookie 腿，**唯一無需使用者動作的全損窗口是「第 400 天且本機腿已失」**，門檻式續簽值得、`navigator.storage.persist()` 現在不值得、IndexedDB 逾時退路必做。
- **能力邊界**（§7）：兩份憑證皆遺失、瀏覽器完全封鎖 cookie 與 site data、資料庫回復到更早時點——這三種系統**不可能**自動恢復；本輪建議維持「不做找回機制」（#361），把力氣放在「不要同時遺失」。
- **需要 Owner 裁示的只有五題**（§9），每題都附老弟建議；三題（#360、#361、#362）現在就能答，一題（#363）等研究票 #365 的瀏覽器事實，一題（#364）等前兩題。

---

## 1. 現有架構評估

### 1a. 元件與資料模型

```
瀏覽器（一個 origin）                         伺服器（FastAPI on Vercel）          Neon Postgres
┌──────────────────────────────┐   每個請求   ┌──────────────────────────────┐   ┌────────────────────────┐
│ 腿 A  HttpOnly cookie        │ ──────────▶ │ _resolve_owner_for_request() │──▶│ browser_identities     │
│   __Host-oc_owner=<token>    │  cookie      │  1. cookie token 查表          │   │  token PK → owner_id   │
│   Secure, SameSite=Lax,      │              │  2. 否則 header token 查表      │   │  issued_at             │
│   Max-Age 400d, 簽一次        │              │  3. 都查不到 → pending 佔位     │   │  last_seen_at（清理錨點）│
│                              │              │     + materializer（首次寫入） │   │  cookie_issued_at      │
│ 腿 B  本機副本               │ ──────────▶ │                              │   │  role（SU／SA 裝置用）  │
│   IndexedDB oc-owner-        │ X-OC-        │ 回應：                        │   ├────────────────────────┤
│   bootstrap（主）＋           │ Credential   │  issue → Set-Cookie 補腿 A     │   │ owners                 │
│   localStorage 鏡像           │ ◀────────── │  echo  → X-OC-Credential 補腿 B│   │  owner_id PK           │
│   每個分頁一次讀入記憶體       │  echo        │  X-OC-Owner-Bound: 1          │   │  created_at,           │
│   跨分頁：IDB 單一 readwrite   │              │  Cache-Control: private,      │   │  last_activity_at,     │
│   transaction + Web Locks     │              │     no-store                  │   │  protected, role,      │
└──────────────────────────────┘              └──────────────────────────────┘   │  is_synthetic          │
                                                                                   └────────────────────────┘
```

- **token**：`secrets.token_urlsafe(32)`（256 bit）或前端 `crypto.getRandomValues` 32 bytes base64url；形狀 `^[A-Za-z0-9_-]{22,128}$`，不合形狀視同沒帶。token 與 `owner_id` 刻意是兩個值（owner_id 永不出現在任何回應）。
- **user 建立時機**：只有 `_persistent_owner()`（建立劇本、存設定、存 provider credential、輸入 SU／SA 密碼）會呼叫 `materialize_owner()` → `claim_browser_token()`（`INSERT … ON CONFLICT (token) DO NOTHING RETURNING`），多個 serverless instance 同時首寫只會得到一個 owner。純讀取永不建 user（SECURITY-FIX-01 deferred creation）。
- **權限**：掛在憑證（`browser_identities.role`），Normal 一律 `NULL`→`normal`；SU／SA 登入換發新憑證綁到主帳號並 `absorb_owner()` 併入這台裝置的匿名資料（PR #358）。
- **生命週期**：錨點＝該 owner 全部憑證的 `max(last_seen_at)`（每個帶有效憑證的請求都會推）；180 天→abandoned（衍生狀態，不落盤）、再 7 天→`delete_owner()`；空 owner 1 天；`protected`／`role != normal` 在查詢層就排除。每日 Vercel Cron `cleanup-abandoned-owners`。
- **路由白名單**：只有 `/api/health`、`/api/cron/*` 不解析身分；其餘一律解析但不建立。

### 1b. 請求時序（關鍵分支）

| 來的憑證 | 伺服器判定 | 回應動作 |
|---|---|---|
| cookie 可解析 | 以 cookie 為準（不看 header 是否一致） | header 不一樣→`echo`；`cookie_issued_at IS NULL`（舊滑動窗 cookie）→補簽一次 |
| cookie 不在／不認得，header 可解析 | 以 header 為準 | `issue`（補發 cookie）；若 header≠cookie 也 `echo` |
| 兩者皆不認得（含形狀不合） | pending 佔位（每請求隨機、讀取天然為空） | 首次寫入時 `materialize`：**candidate = header > cookie > 隨機**，綁到新 owner；`issue`＋（必要時）`echo` |
| 白名單路由 | 不碰身分 | 無 |

### 1c. 已經做對、本輪不動的事

1. **不透明 token＋查表**（可單方作廢；研究 #275 的結論），`__Host-`／`HttpOnly`／`Secure`／`SameSite=Lax`。
2. **延遲建立**：bot、監控、只看不寫的訪客不會洗出 owner。
3. **PK 原子綁定**：跨 instance、跨分頁同時首寫只會一個 owner（`e2e/owner-bootstrap.spec.ts` 30 輪真瀏覽器搶奪＋IndexedDB 不可用時 Web Locks 排隊皆已鎖住）。
4. **兩腿每回應收斂**：任何一腿還在，身分就不會掉；404／409 回應不會改動一顆可解析的 cookie（`test_identity_root_cause_001.py` 第一類測試）。
5. **DB-backed、無程序內狀態**：重新部署、冷啟動、多 instance 都不影響（同一顆 cookie 跨 app instance 在 Postgres 上解析到同一 owner，已有測試）。
6. **`Cache-Control: private, no-store`**：帶憑證的回應不會被任何共享快取吃掉。
7. **匿名→SU／SA**：`absorb_owner()` 單一交易併入、衝突設定存 `owner_merge_archive`、不改綁舊憑證（PR #358 三瀏覽器實測）。
8. **伺服器錯誤不刪憑證**：`send()` 對 5xx／逾時／網路中斷只拋 `ApiError`，任何路徑都不會清除任一腿（Firebase #10438——啟動時一個暫時 5xx 清掉已持久化 user——是本產品要明文避免的反例，#366）。本輪把它升格為不變量並加否定測試（NIR-08）。

### 1d. 九種完成標準情境 vs 現況

| # | 情境 | 現況 | 判定 |
|---|---|---|---|
| 1 | 首次使用、首次建立劇本 | 兩腿同一顆 token；首寫原子綁定 | ✅ |
| 2 | 關閉瀏覽器後重進 | cookie 400 天、IDB／localStorage 持久 | ✅（但見 G-C：本機副本未要求持久化） |
| 3 | 閒置數天～數週 | 180 天保留；錨點是任何請求 | ✅（Safari 7 天上限只傷腿 B，腿 A 補回——待 #365 確認） |
| 4 | 同時多分頁 | IDB 原子＋Web Locks＋cookie 優先收斂 | ✅（記憶體副本不即時同步，靠下一回應收斂——可接受，見 G-L） |
| 5 | cookie 或本機儲存單邊失效 | 另一腿補回 | ✅ |
| 6 | 兩腿不一致／請求競態 | cookie 優先；echo 收斂；PK 保證單一 owner | ✅ |
| 7 | 重新部署／後端重啟 | 無程序內狀態 | ✅ |
| 8 | 多次建立、編輯、刷新 | 已綁定後每請求只查表＋touch | ✅ |
| 9 | 匿名後登入 SU／SA | PR #358 | ✅（本輪只納入驗收） |
| — | **兩腿皆遺失** | 與首訪無法區分；舊 owner 成孤兒 187 天 | ❌ 不可恢復（能力邊界），但**可偵測、可觀測、可提示**——目前三者皆無（G-A／G-G／G-H） |
| — | **長期使用者第 400 天** | cookie 不續簽→斷崖，只剩較弱的腿 B | ⚠️ G-B |
| — | **從另一個 Production 網址進站** | per-origin→另一個人 | ❌ G-E |

---

## 2. 主要風險與能力缺口

每條：現象 → 觸發 → 影響 → 證據／位置。嚴重度：🔴 會讓正常使用者失去劇本；🟠 讓遺失不可見或變難處理；🟡 品質／可觀測。

**G-A 🟠 身分遺失與首訪無法區分、不可觀測。** 形狀合法但查無此 token 的憑證進來，回應與首訪完全一樣（200、`[]`、無訊號）；前端畫成「還沒有劇本」，下一次寫入默默鑄新 owner。`tests/test_identity_root_cause_001.py` 兩條 `xfail(strict=True)` 在等裁示（#360）。沒有任何指標記錄這件事發生過幾次。

**G-B 🔴 cookie 第 400 天斷崖。** IDENTITY-FIX-002 改成簽一次、固定 400 天、之後**永不**再 `Set-Cookie`（`credential["issue"]` 只在 token≠cookie 或 `cookie_issued_at IS NULL` 時為真）。每天都在用的人也會在簽發後第 400 天失去腿 A；只剩腿 B。配上 G-C，長期忠實使用者反而是最可能整個遺失的一群。`CONTEXT.md`「每次來訪續命」已與程式碼漂移。（#363）#365 查證：Chrome 104（M118 回溯）與 **Firefox 140 起都封頂 400 天**，且重設同名 cookie 會重新計算到期（RFC 6265bis §5.7）——門檻式續簽在三家瀏覽器都有效。

**G-C 🟠 本機副本是較弱的一腿。** #365 查證：Safari ITP「7-Day Cap on All Script-Writeable Storage」自 13.1／iOS 13.4 起適用**每一個** first-party 站（不限 tracker）、以 **7 個 Safari 使用日**計、只有 click／tap／鍵盤算互動、**IndexedDB 與 localStorage 都刪**；iOS 14 起所有 WKWebView（含 iOS Chrome／Firefox）皆在 ITP 下。伺服器 `Set-Cookie`（含 HttpOnly）**不受**此上限。Chrome／Firefox 的 quota 驅逐只在磁碟壓力下整個 origin LRU、不碰 cookie。結論：Safari 上「兩腿互補」實際接近「只有腿 A」，腿 A 的續簽（G-B）因此是關鍵；`navigator.storage.persist()` **不採用**——Chrome 對一般站靜默拒絕、Firefox 跳提示（違反零負擔）、Safari 只有加到主畫面才算，且對 ITP 與 400 天兩個真風險皆無效。

**G-D 🔴 IndexedDB 開啟卡住＝整站卡住。** `credential()` 第一次 `await idbGetOrCreate()`，`openDb()` 只處理 `onerror`／`onblocked`，**沒有逾時**；而 `send()` 在建立 90 秒 `AbortSignal.timeout` **之前**就 `await credential()`，且 `credential()` 把 pending promise 記在 `loading`——一次卡住就讓這個分頁**所有** API 請求永遠等待、永不退回 localStorage，即使 cookie 腿完好。#365 查證：真正會 hang 的只有 WebKit bug 226547（Safari 14.1.1／iOS 14.6，14.7 修）；其餘不可用情境（Firefox <115 私密視窗、iOS 17.4 連線中斷、Chromium 封鎖儲存）都是**報錯**，既有 catch 已處理。發生率低但後果是整站不可用，且修法便宜。（`src/credentialStore.ts` `openDb`／`loadToken`；`src/api.ts` `send`）

**G-E 🔴 三個 Production 網址各自一個身分。** `option-chaser.vercel.app`、`option-chaser-<team>.vercel.app`、`option-chaser-git-master-<team>.vercel.app` 同時可用（回報#136）；cookie 與 site storage 都是 per-origin。同一人換個網址＝新人。這正是 CROSS-DEVICE-ACCOUNT-001 根因 2，當時只替 SU／SA 用主帳號解掉。（#362）

**G-F 🟠 查無此 token 時沿用舊 token 綁新 owner。** `candidate = stored_token or cookie_token or random`：一顆曾屬於 owner A（已被清理／自刪／併入）的 token 會被重新綁到新 owner B。安全上無害（同一瀏覽器），但讓「這顆 token 的歷史」不可追、墓碑與指標失真。應改為 unknown→鑄新 token。（#360 順帶定案）

**G-G 🟠 沒有墓碑。** `delete_owner()`（retention、`DELETE /api/me`、SA 刪除、Beta Reset）與 `absorb_owner()` 刪掉 `browser_identities` 列後不留任何痕跡；unknown 無法再分成「180 天未用被清」「自己刪的」「併入主帳號」「真的不認得」。（#360）

**G-H 🟡 身分健康零可觀測。** `METRIC_CATALOGUE` 只有 `new_owner_count`。沒有：腿 A 從腿 B 補回次數、腿 B 從腿 A 補回次數、unknown token 出現次數（依墓碑 reason 分）、unknown 後鑄新 owner 次數。Owner 今天無法回答「身分分裂還在不在發生」。

**G-I 🟡 孤兒 owner 的清理錨點退回 `created_at`。** `anonymous_lifecycle.classify()`：沒有任何 identity 列時用 `created_at`——一個 200 天前建立、昨天才成為孤兒的 owner 下一次 cron 就被刪。今天沒有任何找回路徑所以無害；若日後 #361 翻盤，錨點必須改為「成為孤兒的時間」。本輪只記錄。

**G-J ❌ 兩腿皆遺失→不可恢復。** 這是純 bearer 匿名身分的定義，不是缺陷（Supabase 對自家匿名使用者的描述一字不差）。Owner Beta 裁示不做找回機制；本輪要**明確再確認**（#361）並把邊界寫進規格與驗收。

**G-K 🟡 缺真瀏覽器＋真後端的 Normal 持久性測試。** `e2e/*` 全部 mock `/api/*`；後端測試用 `TestClient`。沒有一條測試在真 Chromium 上做「關閉重開（persistent context）→只清 cookie→只清 site data→兩分頁→換 instance」對真 FastAPI。SU 的 `scripts/cross_device_verify*.{py,mjs}` 已證明這種 harness 可行。

**G-L 🟡 跨分頁記憶體副本不即時同步。** 分頁 B 的 `cached`／`bound` 不會因分頁 A 收到新憑證而更新；靠「cookie 優先＋下一回應 echo」收斂。#366 回填：分析 SDK 無一用 BroadcastChannel 處理身分，PostHog 同樣是「下一次活動前重讀 storage」；真正會分裂的只有**雙重故障**——另一分頁剛登入／登出輪替憑證**且** cookie 不在，或 SU 登出後兩分頁同時首寫、過期的 `bound` 跳過鎖（兩分頁各帶不同 candidate → 兩個 owner）。Normal User 本身不會走登入／登出路徑，但 SU 裝置會。修法見 §3.7（不加 BroadcastChannel）。

**G-M（範圍外，記錄）** 腿 B 可被 JS 讀到，XSS 即身分外洩；CSP 無 `script-src`。安全強化軌另案。

**G-N ❌ 瀏覽器完全封鎖 cookie 與 site data。** 兩腿每次都是新的；每次寫入一個新 owner（空 owner 1 天清掉，有劇本的留 187 天）。不可恢復，但可用「上一回應簽了 cookie、下一請求卻沒帶」的啟發式計數成指標。

**G-O ❌ 資料庫回復到更早時點。** 回復點之後簽的 token 全部消失。不可恢復；寫進邊界。

---

## 3. 推薦的完整解決方案

**原則**：保留「不透明 token＋查表、兩腿收斂、延遲建立、PK 原子綁定」骨架；**不**引入帳號、簽章 token、第三腿或新的身分建立路徑；每一項改動都是 additive、可單獨回滾、可被既有測試形狀覆蓋。

### 3.1 憑證耐久性（修 G-B／G-C／G-D）

- **門檻式續簽**（#363 建議 (b)）：`_call_within_owner_scope_inner()` 在「已解析到 owner」且 `now − cookie_issued_at ≥ RENEW_AFTER_DAYS`（建議 30）時，以**同一顆 token** 重新 `Set-Cookie`（新的 400 天）並更新 `cookie_issued_at`。pending 請求永不簽；永不把可解析的 cookie 改成別顆。斷崖消失、`Set-Cookie` 頻率有上界（每顆 token 每 30 天一次）。
- **`navigator.storage.persist()`：不採用**（#365）：Chrome 對一般站靜默拒絕、Firefox 跳權限提示、Safari 只對主畫面 app 有意義，且對 ITP 7 日上限與 400 天 cookie 皆無效。日後若做 PWA 再議。
- **IndexedDB 逾時退路**：`loadToken()` 把 `idbGetOrCreate()` 與一個短逾時（建議 1500 ms）賽跑；逾時→走 `localStorageGetOrCreate()`（再不行→`null`＝只剩腿 A）；**逾時的 promise 不得被 `loading` 永久快取**（下一次 `credential()` 重試 IDB）；IDB 之後若醒來，`storeCredential()` 照舊寫回。整站不再因 IDB 卡住而掛死。

### 3.2 單一正式網址（修 G-E）

`vercel.json` `redirects`：`has: [{type: "host", value: "<非正式網址>"}]` 且 `source` 排除 `/api/(.*)` → 308 到正式網址同路徑。`/api/health` 三個網址皆保留可達（部署驗證在用）。零程式碼、可在 Vercel 設定頁驗證。（#362 選正式網址）

### 3.3 身分狀態訊號、鑄新 token、墓碑（修 G-A／G-F／G-G）

- **訊號**（IRI-04 已落地）：所有解析身分的回應加 `X-OC-Owner-Identity: bound | none | unknown`；`unknown` 另附 `X-OC-Owner-Identity-Reason`；`/api/me/usage-summary` 加 `identity`／`identity_reason`。**三態定義（施工時修正）**：`bound`＝解析到 user；`unknown`＝帶來的 token **有墓碑**（我們自己作廢過＝這個瀏覽器以前有身分）；`none`＝沒帶，或帶的 token 沒有墓碑——正式站首訪一定帶著前端自己產生、還沒綁定的 token，它**必須**是 `none` 並原樣綁定，跨分頁共用同一顆才能靠 PK 只建一個 owner。
- **鑄新 token**：`unknown` 時候選＝從舊 token **決定性導出**（`sha256("oc-identity-rebind:"+stale)`），不是每個請求各自隨機——兩個分頁帶同一顆舊 token 同時首寫會算出同一顆新 token，PK 仍收斂成一個 owner；首寫回應 `echo`＋`issue` 讓兩腿同步換新；舊 token 永不重綁。`DELETE /api/me` 的回應則立刻把兩腿換成一顆全新未綁定憑證（與登出主帳號同一套）。
- **墓碑**：`identity_tombstones(token_hash TEXT PK, reason TEXT, deleted_at TEXT)`，`reason ∈ {retention_expired, empty_owner_cleanup, self_deleted, admin_deleted, beta_reset, absorbed_into_main, rotated, logged_out, deleted}`（`IDENTITY_TOMBSTONE_REASONS`，兩後端寫入前驗證）；由 `delete_owner(reason=)`／`delete_browser_identity(reason=)`／`absorb_owner()`／`reset_beta_data()` 在同一交易內寫入（`delete_owner()` 回傳的列數含 `identity_tombstones`）；只在兩份都查不到的路徑查一次；保留 400 天後由 `run_retention()` 清掉。token 只存 SHA-256，不存明文、不存 owner_id。
- **前端行為**（#360 裁示）：建議只在 `unknown` 且 reason＝`retention_expired` 顯示一行可關閉說明；其他一律沉默。

### 3.4 身分健康可觀測（修 G-H／G-N）

`METRIC_CATALOGUE` 新增五類：`identity_heal_cookie_from_local`、`identity_heal_local_from_cookie`、`identity_unknown_token`（依 reason 分 source）、`identity_new_owner_after_unknown`、`identity_renew_cookie`（施工時拿掉原列的第六類 `identity_cookie_not_returned`：啟發式且需要跨請求狀態，#373 以五類為準）。`/api/ops/metrics` 自動涵蓋；每日摘要加一列「身分健康」。

### 3.5 驗證（修 G-K）

真 Chromium＋真 FastAPI（HTTPS，自簽憑證＋`ignoreHTTPSErrors`，或沿用 `scripts/cross_device_verify_server.py` 的本機全站）的「持久性酷刑測試」：persistent context 關閉重開、只清 cookie、只清 site data、兩分頁同時首寫、停用 IndexedDB、模擬 IDB 卡住、換 app instance、第 400 天（時鐘注入）、別名網址進站（本機以 host header 模擬）。每一條斷言 owner 不變、劇本一致、`new_owner_count` 不增。

### 3.6 邊界與詞彙

§7 的不可恢復清單進規格與隱私頁（#364）；§8 詞彙進 `CONTEXT.md`。

### 3.7 分頁快取失效（修 G-L；#366 已裁，取代 BroadcastChannel）

- (a) `send()` 收到的回應**沒有** `X-OC-Owner-Bound: 1` 時，重置該分頁的 `cached`／`bound`（回到「還沒讀過」），下一次 `send()` 重讀 IndexedDB；這讓剛被別的分頁登出／自刪的分頁在第一個讀取回應後就追上。
- (b) 對 localStorage 鏡像鍵 `oc_owner_bootstrap` 掛 `storage` listener：事件到達只觸發「重讀 storage」，**不信 `event.newValue`**（PostHog PR #4659 的做法）；這補掉 (a) 追不到的「第一個請求就是寫入」的競態。
- 不引入 BroadcastChannel：它解「狀態自行輪替」的問題（Supabase／Firebase 每小時換 token），本產品沒有；多一個狀態來源就多一組競態。只有日後引入週期性憑證輪替時才重新考慮。

---

## 4. 施工任務拆解、依賴與驗收條件

> 全部為 additive；每票獨立 commit＋`/code-review`；後端票需 Postgres 契約測試；前端票需 `npm run typecheck && npm test && npm run build`。施工票在對應決策票關閉後開成 issue。

### 依賴圖

```
#365 研究：儲存耐久性（已回填）──▶ #363 Cookie 續命 ──▶ NIR-03
#360 可見性＋墓碑 ──▶ NIR-01（UI 半邊）、NIR-02、NIR-06（reason 維度）
#361 找回邊界 ─┐
#360 ─────────┴─▶ #364 天數＋文案 ──▶ NIR-09
#362 正式網址 ──▶ NIR-05
（不等任何決策）：NIR-01 後端半邊、NIR-04（#365 已裁）、NIR-06 基本指標、NIR-07、NIR-08 骨架、NIR-10（#366 已裁）
NIR-01～05、NIR-10 ──▶ NIR-08 完整跑
```

### NIR-01 身分狀態訊號＋unknown 鑄新 token（後端＋前端）
- **改動**：`_resolve_owner_for_request()` 回傳 identity state；middleware 加 `X-OC-Owner-Identity`；`usage-summary` 加 `identity`；unknown→`candidate = random`。前端 `send()` 讀 header，依 #360 決定是否顯示。
- **依賴**：後端半邊無；前端提示半邊等 #360。
- **驗收**：`test_identity_root_cause_001.py` 兩條 `xfail` 移除後全綠；新測試：unknown 後首寫的 owner 憑證 token ≠ 原 token，且回應 `echo`＋`issue` 兩腿同步；`none`／`bound`／`unknown` 三態各一條；白名單路由不帶該 header；owner_id 仍不出現在任何回應。

### NIR-02 身分墓碑
- **改動**：DDL `identity_tombstones`；`Storage` 新方法 `write_identity_tombstones(tokens, reason, now)`／`lookup_identity_tombstone(token)`；`delete_owner()`／`absorb_owner()`／cleanup／Beta Reset／SA 刪除各帶 reason；unknown 路徑查一次；`run_retention()` 清 400 天前的墓碑。
- **依賴**：#360（是否做；reason 清單）。
- **驗收**：記憶體與 Postgres 兩後端契約測試一致；六個 reason 各一條「刪→帶舊憑證回來→訊號帶 reason」；墓碑只存 hash（測試斷言表內無任何列等於明文 token）；400 天後被 retention 清掉；`delete_owner()` 回傳列數涵蓋墓碑寫入；主帳號 `DELETE /api/me` 409 時不寫墓碑。

### NIR-03 門檻式 cookie 續簽
- **改動**：`credential["issue"]` 多一條件 `resolved.cookie_issued_at` 早於 `now − RENEW_AFTER_DAYS`；續簽同 token；`mark_owner_cookie_issued()` 更新時間；`create_app(cookie_renew_after_days=…)` 可注入。
- **依賴**：#363（含 N）。
- **驗收**：`test_identity_fix_002.py`「後續請求不再 Set-Cookie」改寫為「30 天內不再、滿 30 天恰簽一次且 token 相同、再 30 天內不再」；佔位（pending）請求仍不簽；404／409 只可能發生同顆續簽、永不改顆（施工時定案：續簽與回應狀態碼無關，簡單且安全）；`test_identity_root_cause_001.py` 的「不改動可解析 cookie」改為「不改成別顆」；`CONTEXT.md` 條目更新。

### NIR-04 前端耐久性：IndexedDB 逾時退路（`persist()` 經 #365 不採用）
- **改動**：`credentialStore.ts` `loadToken()` 與 1500 ms 逾時賽跑；逾時不快取 pending promise；`inTransaction()` 同樣加逾時（STP 248 之前的交易阻塞情境）；結果以 `console.info` 與指標回報，不顯示 UI。
- **依賴**：無（#365 已回填）。
- **驗收**：vitest：模擬 `indexedDB.open` 永不回應→`credential()` 在逾時內 resolve 為 localStorage 的 token，且下一次 `credential()` 會再嘗試 IDB；IDB 之後成功→下次 `storeCredential()` 寫入 IDB；`e2e/owner-bootstrap.spec.ts` 既有兩條仍綠；新 e2e：注入卡死的 `indexedDB.open`，首頁仍能在 2 秒內列出劇本（cookie 腿完好）。

### NIR-05 單一正式網址
- **改動**：`vercel.json` `redirects`（host 條件、排除 `/api/`）；`docs/deploy-vercel.md` 說明。
- **依賴**：#362。
- **驗收**：部署後對兩個非正式網址 `GET /` 與 `GET /#/settings` 回 308 到正式網址同路徑；三個網址 `GET /api/health` 皆 200；正式網址無迴圈；Playwright 以 host header 驗證本機規則（若 Vercel 規則不可本機重現，則部署後 curl 驗證寫進票）。

### NIR-06 身分健康指標＋每日摘要
- **改動**：`METRIC_CATALOGUE` 新六類；middleware 在 heal／unknown／renew／mint 各記一次；`digest.py` 加一列。
- **依賴**：reason 維度等 NIR-02；基本四類不等。
- **驗收**：每類各一條測試觸發→`/api/ops/metrics` 可見；`enable_metrics=False` 全 no-op；摘要信含該列且不含任何 token／owner_id。

### NIR-07 Production 身分健康稽核（唯讀）
- **改動**：`docs/audits/identity-health-audit.sql`（Task 票的六題）；Owner 執行、數字回填票。
- **依賴**：無。
- **驗收**：SQL 在測試 Postgres 上可執行且對 `tests/` 既有 fixture 回合理值；票上有數字與台灣時間；不含任何明文 token／完整 owner_id。

### NIR-08 真瀏覽器持久性酷刑測試
- **改動**：`e2e/identity-persistence.spec.ts`＋本機全站 harness（沿用 `scripts/cross_device_verify_server.py`）；CI 以獨立 job 跑（需 Postgres service）。
- **依賴**：骨架不等；完整情境等 NIR-01～05。
- **驗收**：§3.5 列出的每一情境一條測試；每條斷言 `owners` 計數不變、劇本 id 集合相同、`X-OC-Owner-Identity: bound`；至少在 Chromium 跑過；WebKit 若 Playwright 可用則加跑（否則票上明寫 UNVERIFIED）。

### NIR-09 邊界文案＋`CONTEXT.md` 詞彙
- **改動**：隱私頁一行（#364 定稿）；`CONTEXT.md` 新增 §8 四個詞條、修正「每次來訪續命」；`docs/` 邊界章節。
- **依賴**：#364。
- **驗收**：`PrivacyPage.test.tsx` 斷言該行存在；`CONTEXT.md` 無與程式碼矛盾的敘述（code review 逐條對照）。

### NIR-10 分頁快取失效（取代 BroadcastChannel；#366 已裁）
- **改動**：`credentialStore.ts` 新增 `invalidateTabCache()`；`send()` 在回應缺 `X-OC-Owner-Bound: 1` 時呼叫；`storage` listener（鍵 `oc_owner_bootstrap`）只觸發重讀、不信 `event.newValue`；`bound` 被重置後，會建立 user 的寫入重新進 Web Locks 排隊。
- **依賴**：無（#366 已回填）；由 NIR-08 驗證。
- **驗收**：vitest：模擬回應無 Owner-Bound → 下一次 `send()` 重讀 IDB 並帶新 token；`storage` 事件帶偽造 `newValue` 時仍以 storage 實際內容為準；e2e（NIR-08）：SU 在分頁 A 登出後分頁 B 的下一請求已帶新憑證，且兩分頁同時首寫只產生一個 owner（`owners` 計數＋1）。

---

## 5. 各任務驗收條件

見 §4 每票的「驗收」小節；共同條件：

1. 不得改變 §1c 列出的七項既有保證（每票 code review 逐項勾選）。
2. `tests/test_cross_device_account.py`、`test_unified_identity_001.py`、`test_identity_fix_002.py`（依 NIR-03 改寫後）、`test_identity_root_cause_001.py`（xfail 移除後）全綠；Postgres 契約半邊必跑。
3. 前端 `npm run typecheck && npm test && npm run build`；e2e 既有兩條 owner-bootstrap 仍綠。
4. 任何回應、日誌、指標、摘要信、墓碑表不含 owner_id 全文或明文 token。
5. `/security-review` 一次（碰身分／cookie 的票，依 H10）。

---

## 6. 整體 Definition of Done

地圖 #359 關閉的條件（全部成立）：

1. **決策**：#360～#364 皆有 resolution comment 並關閉；研究票 #365／#366 的文件在 `docs/research/`；Task 票的基線數字已回填。
2. **規格**：本文件依裁示修訂為定稿（移除「建議」字眼、填入 Owner Decision）。
3. **施工票**：NIR-01～NIR-09（NIR-10 視 #366）開成 GitHub issue、`Blocked by` 排好、每票有驗收；按 CLAUDE.md 規則逐票 implement→tests→`/code-review`→commit→push。
4. **九情境**：§1d 的九種完成標準各有至少一條自動化測試（後端契約或 NIR-08 e2e）證明「owner 不變、劇本一致」。
5. **邊界**：§7 三種不可恢復情境各有一條否定測試（證明系統行為是「乾淨的新身分＋正確訊號／墓碑 reason」，而不是半套狀態），且文案依 #364 上線。
6. **可觀測**：Production 部署後連續 7 天 `identity_unknown_token` 與 `identity_new_owner_after_unknown` 可在 `/api/ops/metrics` 讀到，Owner 看過一次每日摘要的「身分健康」列。
7. **Production 驗證**：三個網址的重導與 `/api/health` 驗過（NIR-05）；Owner 用自己的日常瀏覽器（Normal 身分）完成「關閉重開／兩分頁／隔天回來」真機驗收並回報；SU／SA 三裝置回歸（`scripts/cross_device_verify*`）仍過。
8. `CONTEXT.md` 詞彙定稿、CLAUDE.md 檢查點更新為一到兩行。

---

## 7. 能力邊界（不可自動恢復的情境）

| 情境 | 系統行為（目標狀態） | 使用者可見 |
|---|---|---|
| 兩腿皆遺失（清除瀏覽資料、Chrome／Firefox「關閉時清除」、iOS「封鎖所有 Cookie」、換瀏覽器、無痕結束、裝置重灌；#365：沒有任何**自動**瀏覽器行為會同時殺兩腿） | 下次寫入＝乾淨的新匿名身分；舊 owner 依 180＋7 天清理；若舊憑證**仍被帶來**（只清了一腿不在此列）才會有 unknown 訊號 | 依 #360：預設沉默 |
| 瀏覽器完全封鎖 cookie 與 site data | 每次來訪都是新人；每次寫入一個 owner；空 owner 1 天清 | 沉默；`identity_cookie_not_returned` 指標供 Owner 觀察 |
| 資料庫回復到更早時點 | 回復點後簽的 token **沒有墓碑**→讀成 `none`、首寫原樣綁定（跟首訪一樣，不猜配對） | 沉默；Owner 只能從 `new_owner_count` 突增得知（已明寫為能力邊界，`test_tokens_deleted_outside_the_storage_primitives_read_as_none`） |
| 使用者自己 `DELETE /api/me` | 墓碑 `self_deleted`；下次寫入新身分 | 沉默（是本人意圖） |
| 匿名裝置登入 SU／SA 後重設為 Normal | 劇本已併入主帳號（by design，PR #358）；裝置回到全新匿名 | 既有登入頁說明 |

這些**不是**本地圖要修的 bug，是純 bearer 匿名身分的定義；本輪的責任是「盡量不同時遺失」（§3.1／3.2）與「遺失時行為乾淨、可觀測、必要時可提示」（§3.3／3.4）。

---

## 8. 詞彙（提案，待 #363／#364 關閉後寫入 `CONTEXT.md`）

- **Credential Leg（憑證腿）**：同一顆 Browser Identity token 的其中一份存放處。**Cookie leg**＝伺服器簽的 HttpOnly `__Host-oc_owner`；**Local leg**＝IndexedDB／localStorage 副本（請求以 `X-OC-Credential` 帶上）。任何一腿可解析即為同一 user。
- **Identity State（身分狀態）**：一次請求的身分判定結果，三態：`bound`（解析到 owner）、`none`（未帶合法憑證，或帶的是沒有墓碑的 token＝首訪／前端剛產生還沒綁定）、`unknown`（帶來的 token 有墓碑＝這個瀏覽器以前有過身分、已被作廢）。
- **Identity Tombstone（身分墓碑）**：憑證被我們自己作廢時留下的「token hash → 原因 → 時間」紀錄，是 `unknown` 的唯一判據，也是指標的維度（`retention_expired`／`empty_owner_cleanup`／`self_deleted`／`admin_deleted`／`beta_reset`／`absorbed_into_main`／`rotated`／`logged_out`／`deleted`）；保留 400 天；不含明文 token、不含 owner_id。
- **Cookie Renewal（cookie 續簽）**：對已解析的請求，在 cookie 簽發滿 N 天後以**同一顆** token 重新 `Set-Cookie`。取代 `CONTEXT.md` 現行「每次來訪續命」一句。
- **Canonical Host（正式網址）**：唯一承載 SPA 的 origin；其他 Production 網址只做 308 重導（`/api/*` 除外）。

---

## 9. 待 Owner 裁示（決策票）

| 票 | 問題 | 老弟建議 | 可答時機 |
|---|---|---|---|
| #360 | 身分遺失可見性＋墓碑＋unknown 鑄新 token | 訊號做；墓碑最小版做；前端只在 `retention_expired` 一行提示；鑄新 token 採納 | 現在 |
| #361 | 找回機制範圍 | 維持不做（(a)）；schema 已預留 | 現在 |
| #362 | 單一正式網址 | 做；`option-chaser.vercel.app`；只重導非 `/api/*` | 現在 |
| #363 | Cookie 續命政策 | 門檻式續簽 N＝30 天（(b)）——#365 已證實三家瀏覽器都封頂 400 天且重設會重新計時 | 現在（#365 已回填） |
| #364 | 天數相容性＋邊界文案 | 天數不動；空 owner 清除永遠沉默；隱私頁一行 | 等 #360／#361 |

---

## 10. 不在範圍（地圖 Out of scope）

SU／SA 跨裝置機制本身；正式帳號／email／密碼；找回碼／claim link（除非 #361 翻盤→新 effort）；XSS／CSP 強化；保留天數政策性變更；SCALE-18／#269。
