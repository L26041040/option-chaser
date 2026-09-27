# CLAUDE-DB-LIFECYCLE-AUDIT-001 — Production Data Lifecycle / Garbage Audit

- 日期：2026-09-27
- 範圍：`master` @ `95cb0e3`（含已 merge 的 PR #344、#346）。本輪**只做 audit**：沒有改任何 code、沒有碰 Production、沒有碰 #269 / SCALE-18。
- Production `DATABASE_URL`：**這個環境沒有**。所以 Phase 4 **沒有**在 Production 上執行，改成產出 [`db-lifecycle-production-audit.sql`](./db-lifecycle-production-audit.sql)：一個 SELECT-only 的單一 statement，貼進 Neon SQL Editor 跑一次，就會得到一張依 Q01…Q19 排好的結果表。本報告所有「Production 數字」都標成 **待 SQL**，一律不猜。
- SQL 的驗證方式：在本地臨時 Postgres 用 `PostgresStorage` 建好 schema、灌入 fixture，再放進 `BEGIN TRANSACTION READ ONLY; … ROLLBACK;` 裡跑一次。132 列結果，沒有錯誤，也證明整份 SQL 沒有任何寫入。
- 證據來源：`api_app/storage/postgres.py`（`_SCHEMA`／`_MIGRATIONS`、所有 Storage methods）、`api_app/storage/memory.py`、`api_app/main.py`（routes、cron、cookie middleware）、`api_app/anonymous_lifecycle.py`、`api_app/identity.py`、`api_app/superuser.py`、`api_app/abuse_control.py`、`api_app/metrics.py`、`scripts/migrate_solo_to_owner.py`、`scripts/backfill_settings_to_owner.py`、`vercel.json`、`src/api.ts`（前端消費端）、`docs/spec/scaling-foundation.md`（OD-06）、`docs/research/storage-optimization-audit.md`。

---

## 1. Executive Summary

| 問題 | 答案 |
|---|---|
| Production table 總數（code 定義） | **25**。`narrow_history` 已退役、已 DROP，不計入；實際 DB 請以 Q01 為準，Q01 也會列出 schema 裡存在、但 code 不認得的表 |
| 有 retention 的 table 數 | 有自動清理路徑的 **13** 張。其中**與 owner 是否活躍無關**、真正以時間或筆數為界的只有 **3** 張：`diagnostics`、`operational_metrics`、`rate_limits`。另外 10 張只在「整個匿名 owner 被 cron 刪掉」時才會一起消失 |
| 無 retention 且會持續增長 | **7** 張：`snapshots`、`results`、`events`、`iv_observations`、`contract_iv_history`、`superuser_audit_log`、`role_sessions` |
| Confirmed true orphan | **code 路徑：穩態下 0 個結構性產生源**；有 2 個罕見的 race／crash 窗口（P2-6）。**Production 實際列數待 SQL**（Q04b、Q06 `unregistered`、Q07a–d） |
| Logical orphan | **3 類**：① `solo` lineage（9 張 owner-scoped 表）② `owner_id IS NULL` 的舊列（如果 SCALE-06 backfill 沒跑完）③ legacy singleton 三表（`data_source_settings`／`provider_credentials`／`provider_verifications`，只有 `solo` 讀得到）。列數待 SQL（Q06、Q08、Q12） |
| `solo` lineage 有多少資料 | **待 SQL**（Q06 `…/ solo`、Q08 `solo` 列、Q12）。code 可以證明：PB-02 之後 production **沒有任何路徑再寫入 `solo`**，所以這批資料是凍結、不再增長的 |
| AUTH-07 能否解掉大部分 logical orphan | **能解掉第 ① 類（主體）**，但有條件：先修 P1-A，且 Q12 要確認 legacy 設定已經複製進 `owner_*('solo')`。**第 ② 類解不掉**，因為 `migrate_owner` 只搬 `= 'solo'`、不搬 `IS NULL`。**第 ③ 類會在遷移後從 logical orphan 變成 true orphan**，其中可能還留著 vendor token |
| P0 | **沒有** |
| P1 | **3 個**：P1-A、P1-B 會阻礙 AUTH-07；P1-C 是需要 Owner 決策的無界成長 |
| P2 | 8 個，都可以延後 |

---

## 2. Complete Table Inventory

下表的「frontend reachable」以 `src/api.ts` 實際呼叫的端點為準。

| # | table | producer | consumer | owner scoped? | frontend reachable? | retention | cleanup | delete cascade/path | expected growth | risk |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `scenarios` | `POST /api/scenarios`（`_persistent_owner()`） | 清單、detail、refresh、SA owner 檢視 | ✅ `owner_id` | ✅ | 無（使用者自己的資料） | 使用者 archive→delete；匿名 owner 閒置 187 天 | `delete_scenario`（只刪已封存）；`delete_owner` | 依使用者建立數 | 低 |
| 2 | `results`（fact ledger） | `_refresh_and_save` 每次刷新 `save_result(view=None)` | `result_timestamps()` → `GET /results`（**前端沒呼叫**）；`table_size_metrics` | ✅ | ❌（沒有 UI 讀取端） | **無** | `clear_results`（編輯）、`delete_scenario`、`delete_owner` | 同左 | **每次刷新每個 live scenario +1 列**；SCALE-16 之後每列很小，但舊列仍帶完整 `view` | P1-C、P2-1 |
| 3 | `current_results` | `save_current_result` 每次刷新 upsert | `latest_result`／`latest_summaries`：清單、detail、raw-data 錨點 | ✅ | ✅ | 自然有界（每 scenario 1 列） | 同上 | 同上 | 有界 | 低 |
| 4 | `snapshots` | `_refresh_and_save` 每次刷新 `save_snapshot` | `get_snapshot()` **只讀最新一份**（`_load_raw_snapshot` 綁在 `latest_result().analyzed_at`）；`result_timestamps` 只讀 PK | ✅ | 最新一份 ✅；**歷史份 ❌** | **無**（OD-06：永久） | `clear_results`、`delete_scenario`、`delete_owner` | 同左 | **每次刷新每個 live scenario +1 列，MB 級原始 payload**（TOAST 壓縮後實際大小見 Q09c） | **P1-C** |
| 5 | `events` | create／edit／archive／restore／`ANALYSIS_COMPLETED` | `GET /scenarios/{id}/events`（**前端沒呼叫**） | ✅ | ❌ | **無** | `delete_scenario`、`delete_owner` | 同左 | 每次刷新 +1 列（約 177 B） | P2-2 |
| 6 | `diagnostics` | `diagnostics.emit()` warning／error | `GET /api/diagnostics`（前端有） | ✅（pending 請求寫 NULL） | ✅（自己的） | **全域最新 200 列**（trim-on-write） | `DELETE /api/diagnostics`、`delete_owner` | 同左 | 有界 ≤200 | 低 |
| 7 | `owner_settings` | `PUT /api/settings`；`solo` read-through write-through | `GET /api/settings` | ✅ PK | ✅ | 有界（每 owner 1 列） | `delete_owner` | 同左 | 有界 | P1-A（遷移時 PK 衝突） |
| 8 | `owner_credentials` | `PUT /settings/credentials/{p}` | IV 相關 vendor 呼叫、設定頁 | ✅ PK | ✅（遮罩後） | 有界 | `DELETE credential`、`delete_owner` | 同左 | 有界 | P1-A |
| 9 | `owner_verifications` | `POST …/test` | 設定頁 | ✅ PK | ✅ | 有界 | 隨 credential 刪除、`delete_owner` | 同左 | 有界 | P1-A |
| 10 | `owners` | `claim_browser_token()`（只在第一次持久化寫入時才建立） | cookie 解析、cron、SA 清單、`usage-summary` | 本身就是 registry | 間接 | 由 cron 管理 | cron `delete_owner`；`DELETE /api/me`；SA delete | `delete_owner` 在同一個 transaction 裡 | 依使用者數 | 低 |
| 11 | `browser_identities` | 同上（與 `owners` 同一個 transaction） | `resolve_owner_by_token`、`touch_browser_identity`（lifecycle 錨點） | FK 語意 → owner | 間接 | 同上 | 同上 | 同上 | 每 owner 1 列 | 低 |
| 12 | `role_sessions` | `POST /api/auth/login` | `resolve_role_session`（每個受保護端點） | ❌ | 只有 SU/SA | **無**（Owner 裁示不做 server-side expiry） | 只有 logout 會標 `revoked_at`，**從不刪** | 無 | 每次登入 +1 列（極少） | P2-5 |
| 13 | `superuser_audit_log` | `_record_audit`（SA 刪除 owner／改 protected） | `GET /api/superuser/audit-log`（SA UI） | ❌（`target_owner_id` 刻意保留） | SA only | **刻意無上限**（PB-10） | 無 | 無 | 每次 SA 動作 +1 列（極少） | Keep |
| 14 | `rate_limits` | `rate_limit_consume()`（vendor quota、source burst、new-owner tier、login） | 同一個函式 | ❌（`owner_quota` 的 key＝owner_id） | ❌ | **window 結束後 +1h** | cron `purge_rate_limits`（每日）；`delete_owner` 刪 owner quota 列 | 同左 | 有界（約 ≤2 天的視窗列） | 低 |
| 15 | `operational_metrics` | `_record_metric`（14 類） | `/api/ops/metrics`、daily digest、cron 健康檢查 | ❌ | SA only | **每個 metric 30 天**（trim-on-write） | 同左 | — | 有界 | 低（見 P2-8） |
| 16 | `iv_observations` | legacy IV backfill（`ivpipeline.backfill_iv`） | `iv-history`（前端有） | ❌ shared | ✅ | **無** | 無（`delete_owner` 刻意不碰） | — | 約 66 列／symbol／年，只有開過 IV 的 symbol 會長 | P2-4 |
| 17 | `iv_backfill_runs` | 同上 | 同上（「今天跑過了嗎」） | ❌ | 間接 | 有界（每 symbol 1 列） | 無 | — | 有界 | Keep |
| 18 | `contract_iv_history` | `ensure_contract_history`（exact-contract IV） | `iv-history` | ❌ | ✅ | **無** | 無 | — | 每個曾經查過的 OCC 合約 1 列，`points` append-only；**合約到期後永遠不會再讀** | P2-3 |
| 19 | `rate_cache` | `rate_cache.py`＋cron warm | 每次分析 | ❌ | 間接 | 1 列（`CHECK id=1`） | — | — | 有界 | Keep |
| 20 | `dividend_cache` | `dividend_cache.py` | 每次分析 | ❌ | 間接 | 每 symbol 1 列 | 無 | — | 依 symbol 數 | Keep |
| 21 | `treasury_year_cache` | `treasury_cache.py` | 歷史 reconstruction | ❌ | 間接 | 每年 1 列 | 無 | — | 有界 | Keep |
| 22 | `chain_backoff` | `chain_backoff.py`（Cboe 429） | fetch 前檢查、ops | ❌ | 間接 | 每個 source 1 列 | — | — | 有界（2） | Keep |
| 23 | `data_source_settings`（legacy） | **已凍結**（SCALE-13 起不再寫） | 只有 `owner == 'solo'` 的 read-through 會讀；`backfill_settings_to_owner` | 結構上沒有 owner（隱含 = solo） | ❌（PB-02 後沒有請求會解析成 solo） | — | **沒有任何刪除路徑** | — | 0（凍結） | P1-B、P2-7 |
| 24 | `provider_credentials`（legacy） | 已凍結 | 同上；只有 `owner == 'solo'` 的 `delete_credential` 會刪 | 同上 | ❌ | — | 同上 | — | 0 | P1-B、P2-7（可能含 token） |
| 25 | `provider_verifications`（legacy） | 已凍結 | 同上 | 同上 | ❌ | — | 同上 | — | 0 | P2-7 |
| — | `narrow_history` | **已退役**（SW-12 #342），code 完全不讀寫 | — | — | — | — | Owner 已 DROP（LEGACY-CLEANUP-003） | — | — | Q01 會確認已不存在 |

---

## 3. Producer → Storage → Consumer map（依 request 路徑）

```
首訪（沒有 cookie）──讀取──▶ pending:<random> 佔位 owner（每個請求都不同）→ 什麼都讀不到；不寫 owners/identities
             └─第一次寫入（建劇本／存設定／存 credential）─▶ claim_browser_token()：同一個 transaction 裡寫 browser_identities + owners
每次請求（已綁定的 cookie）──▶ touch_browser_identity(last_seen_at) ← anonymous lifecycle 的唯一錨點
開站／刷新鈕／建立劇本 ─▶ POST /scenarios/refresh-run ─▶ 每個 live scenario：
        results(+1, view=NULL) + current_results(upsert) + snapshots(+1, MB 級) + events(+1)
        + operational_metrics(refresh_duration_ms, chain_fetch_count…)  ← SW-10 已移除 30 分鐘節流
詳細頁 ─▶ current_results（view）＋ snapshots[latest]（raw-data）＋ iv-history（iv_observations / contract_iv_history / owner_credentials）
設定頁 ─▶ owner_settings / owner_credentials / owner_verifications（solo 才會 read-through legacy 三表）
SU/SA 登入 ─▶ role_sessions(+1) ；SA 刪除／改 protected ─▶ superuser_audit_log(+1)
Vendor 呼叫前 ─▶ rate_limits(upsert, FOR UPDATE)
Cron 11:00 UTC 平日 ─▶ warm-rate-cache ─▶ rate_cache / treasury_year_cache
Cron 12:00 UTC 每日 ─▶ cleanup-abandoned-owners ─▶ delete_owner()×≤200 ＋ purge_rate_limits ＋ 2 個 metrics
Cron 13:00 UTC 每日 ─▶ daily-digest（只讀）
```

---

## 4. Reachability classification

| 類別 | Tables／資料切片 |
|---|---|
| **A. Live product data** | `scenarios`、`current_results`、**最新一份** `snapshots`、`owner_settings`、`owner_credentials`、`owner_verifications`、`diagnostics`（自己的）、`owners`／`browser_identities`（間接）、`iv_observations`／`contract_iv_history`（未到期合約） |
| **B. Admin-only data** | `superuser_audit_log`、`operational_metrics`、`role_sessions`；透過 SA API 可以看任何 owner_id 的 scenarios（SA UI 只能從 `list_owners()` 點進去） |
| **C. Logical orphan** | `solo` lineage（9 張表的 `owner_id='solo'` 列：沒有任何 cookie 會解析成 `solo`；`owners` 沒有 `solo` 列 ⇒ **SA UI 清單也看不到**，cron 也碰不到）；`owner_id IS NULL` 的舊列；legacy singleton 三表 |
| **D. True orphan** | 穩態下 code 不會產生（見 §5）。Production 列數待 Q04b／Q06／Q07 |
| **E. Operational garbage** | revoked `role_sessions`、超過 cookie Max-Age 400 天的 active `role_sessions`；到期合約的 `contract_iv_history`；SCALE-16 之前 `results.view` 的完整 payload（已沒有讀取端）；`diagnostics` 的 NULL-owner 列（有界，Keep） |
| **Write-only history（依 OD-06 Keep，但前提已變，見 P1-C）** | 非最新的 `snapshots`、`results` 的 fact 列、`events` |
| **F. Shared system facts／cache** | `rate_cache`、`dividend_cache`、`treasury_year_cache`、`chain_backoff`、`iv_observations`、`iv_backfill_runs`、`contract_iv_history`（未到期） |

「Super Admin 看得到、普通 owner 永遠看不到」（invariant 12）：嚴格說只有 **`solo` lineage**，而且只能透過直接呼叫 `/api/superuser/owners/solo/scenarios` 這種 API 才看得到，UI 清單列不出來。其餘都是 A 類，或是 SA 專屬的 ops 資料。

---

## 5. Orphan checks（Phase 3 invariants 1–14）

| # | Invariant | 結論 | 證據 |
|---|---|---|---|
| 1 | 刪 owner 時 owner-scoped data 全部消失 | ✅ 成立 | `delete_owner` 在單一 `conn.transaction()` 裡刪 `_OWNER_SCOPED_TABLES`（9 張）＋ owner quota `rate_limits` ＋ `browser_identities` ＋ `owners`。`test_no_table_with_an_owner_id_column_is_silently_left_out_of_the_lifecycle` 是 drift guard。刻意保留：`superuser_audit_log`、shared caches |
| 2 | 不會留下 identity → 不存在的 owner | ✅ code 成立 | `claim_browser_token` 在同一個 transaction 裡先寫 identity、再寫 owner；`delete_owner` 在同一個 transaction 裡一起刪。`create_owner_with_token`（不在 transaction 裡）只有 tests 會呼叫。Production 待 Q04b |
| 3 | 不會留下 scenario child → 不存在的 scenario | ⚠ **大致成立，有 2 個窗口** | `delete_scenario`／`clear_results` 是逐條 autocommit，沒有包 transaction：function 在中途被砍掉，就會留下 child。refresh 與 delete 同時發生時，`save_result`／`save_snapshot`／`append_event` 可能在 scenario 刪掉之後才寫進去。這些 child 帶著 owner_id，所以 `delete_owner` 最後仍會清掉。→ P2-6，Production 待 Q07 |
| 4 | anonymous cleanup 不會 starvation | ✅ 成立 | SECURITY-FIX-01 改成先 classify、再取 batch（`main.py:1883-1897`），活躍的 owner 不會佔 batch 名額。batch=200／日；只有「每天新增的 eligible 數 > 200」時才會積壓，deferred creation 之後 empty owner 已經很少。Q05／Q17b 可以驗證 |
| 5 | empty owner cleanup 正常 | ✅ 成立 | `has_data` = scenarios ∨ owner_settings ∨ owner_credentials；empty 1 天後可刪。錨點：identity 的 `last_seen_at`，沒有時退回 `created_at`。Q03e／Q05 |
| 6 | rate-limit rows 最終一定 purge | ✅ 成立（前提：cron 有跑） | `purge_rate_limits(window_end < now-1h)` 每天跑一次；最長的 window 是 DAY ⇒ 一列最多活 ~2 天。cron 失聯有 `cleanup_missed_days` 告警。Q15b |
| 7 | revoked/expired role sessions 永久累積？ | ❌ **會累積**（量極小） | 沒有任何 DELETE；`revoked_at` 只做標記；沒有 server-side expiry（Owner 裁示）。→ P2-5 |
| 8 | audit log 無界？ | 是，**刻意**（PB-10） | 增長只來自 SA 手動操作 ⇒ Keep |
| 9 | metrics 有 retention？ | ✅ 30 天，per metric trim-on-write | 注意：trim 只在「同一個 metric 又被寫入」時才會觸發，所以已退休的 metric 名稱會永遠留著。目前 catalogue 沒有退休項目。→ P2-8（條件式）；Q17a `in_catalogue` |
| 10 | cache/history 是刻意保留，不是忘了清？ | 部分是 | `snapshots` 是刻意的（OD-06）；`iv_observations`／`contract_iv_history` 在既有研究（`storage-optimization-audit.md` §5）已經標成 "accidentally unbounded" → P2-3／P2-4；`events` 是 "append-only，永不修剪（零前端消費端）" → P2-2 |
| 11 | 已退休功能仍在寫資料？ | ✅ 沒有 | `narrow_history` 的寫入點已經移除（`main.py:2879` 的註解）；PB-05 節流沒有表；`ADMIN_SECRET` 沒有表。殘留的是**已退休功能的讀取側資料**：SCALE-16 之前 `results.view` 的 payload（P2-1）、legacy singleton 三表（P2-7） |
| 12 | SA 看得到、普通 owner 永遠看不到 | `solo` lineage（只能靠 API）| 見 §4 |
| 13 | AUTH-07 影響哪些 table | 見 §8 | |
| 14 | 遷移後還會剩下哪些真正垃圾 | 見 §8、§9 | |

---

## 6. Retention / cleanup coverage

| 機制 | 覆蓋 tables | 觸發 |
|---|---|---|
| Time／size retention（跟 owner 無關） | `diagnostics`（200 列）、`operational_metrics`（30 天）、`rate_limits`（window+1h） | 寫入時／每日 cron |
| Anonymous owner lifecycle（`delete_owner`） | 9 張 owner-scoped 表 ＋ `owners` ＋ `browser_identities` ＋ owner quota 的 `rate_limits` | 每日 cron：有資料的 owner 180+7 天、empty owner 1 天，以最後一次帶 cookie 的請求起算；protected 永遠排除 |
| 使用者主動 | `delete_scenario`、`clear_results`、`DELETE /api/me`、`DELETE /api/diagnostics`、`DELETE credential` | UI |
| SA 主動 | `delete_owner`／batch-delete | SA UI |
| 以 key upsert 自然有界 | `current_results`、`owner_*`、`rate_cache`、`dividend_cache`、`treasury_year_cache`、`chain_backoff`、`iv_backfill_runs` | — |
| **完全沒有** | `snapshots`／`results`／`events`（活躍 owner 與 protected owner 的部分）、`iv_observations`、`contract_iv_history`、`role_sessions`、`superuser_audit_log`、legacy singleton 三表 | — |

**Protected Owner（AUTH-07 之後）＝ 永遠不會被 cron 清掉**：它名下的 `snapshots`／`results`／`events` 會隨每一次開站無限增長。這是 P1-C 最直接的受害者。

---

## 7. Production counts

**未執行**：這個環境沒有 Production `DATABASE_URL`，所以沒有假裝完成。

請 Owner 把 `docs/audits/db-lifecycle-production-audit.sql` 整份貼進 Neon SQL Editor 跑一次，然後把結果表整份貼回來。要看的欄位與本報告的對應如下：

| 這份報告的問題 | 看 SQL 哪一列 |
|---|---|
| table 總數／大小／schema 有但 code 沒有的表 | Q01（`in_code=NO`） |
| oldest／newest | Q02 |
| owners total／protected／synthetic／with scenarios／empty／沒有 identity | Q03 |
| identities 指向不存在的 owner | Q04b |
| lifecycle 分布、cron 是否跟得上 | Q05 ＋ Q17b |
| `solo`／NULL／unregistered／pending 列數（逐表） | Q06 |
| child → 不存在的 scenario、owner 不一致 | Q07 |
| per-owner 資料量 top 20 | Q08 |
| 歷史 snapshot 占比、每日成長、單列大小 | Q09 |
| SCALE-16 之前的 `results.view` payload | Q10a |
| events 依種類 | Q11 |
| legacy 設定有沒有複製進 `owner_*('solo')` | Q12d–f |
| AUTH-07 PK 衝突預檢 | Q13 |
| role sessions | Q14 |
| rate-limit 已過期但還沒 purge | Q15b |
| audit log | Q16 |
| metrics retention、cron 每日有沒有跑 | Q17 |
| shared caches、到期合約 | Q19 |

---

## 8. AUTH-07 migration impact

`scripts/migrate_solo_to_owner.py` → `migrate_owner(from='solo', to=<target>)` → 對 `_OWNER_SCOPED_TABLES` 裡 9 張表逐一 `UPDATE … SET owner_id=target WHERE owner_id='solo'` → `set_owner_protected(target, True)`。

**會受影響**：`scenarios`、`results`、`current_results`、`snapshots`、`events`、`diagnostics`、`owner_settings`、`owner_credentials`、`owner_verifications`，以及 `owners.protected`。

**不會受影響，但跟遷移相關**：
- `owner_id IS NULL` 的列：**不會被搬**。要先跑 `scripts/backfill_owner_ids.py`（NULL→solo），Q06 `…/ NULL` 必須是 0。
- legacy singleton 三表：**不會被搬**。只有在 `owner_settings`／`owner_credentials` 已經有 `solo` 列（曾經 read-through，或跑過 `backfill_settings_to_owner.py`）時，Owner 的舊設定／舊 credential 才會跟著走。PB-02 之後不會再有請求解析成 `solo`，read-through 永遠不會再被觸發。→ Q12d–f。
- `browser_identities`／`owners`：不需要處理，因為沒有 `solo` 的 owners 列（Q03j）。

**遷移後還會剩下的真正垃圾**：legacy singleton 三表（變成 true orphan，`provider_credentials` 可能含 token）、NULL-owner 列（如果有）、`solo` 常數與 read-through 分支（code 層的 dead path）。

---

## 9. Confirmed garbage（code 已證明；列數待 SQL）

1. SCALE-16 之前 `results` 列上的完整 `view` JSONB：`latest_result` 已經改讀 `current_results`，`result_history()` 在 app 裡沒有任何呼叫者；只剩 `backfill_result_fact_context.py`（一次性腳本）和 `table_size_metrics`（只量大小）會碰它。→ Q10a
2. 已到期合約的 `contract_iv_history`：OCC 到期日 < today 的合約，不可能再被任何 live scenario 查到。→ Q19d
3. revoked 的 `role_sessions`，以及 `issued_at` 超過 400 天的 active session（瀏覽器 cookie 已經過期）。→ Q14c／d
4. AUTH-07 之後的 legacy singleton 三表。
5. （條件式）Q07a–d 的非零列、Q04b 的非零列、Q06 的 `unregistered`／`pending:*` 列。

---

## 10. False positives / intentional retained data

- `superuser_audit_log` 無上限：PB-10 的刻意設計；`target_owner_id` 指向已刪除的 owner 也是預期行為（Q16c）。**Keep**。
- `diagnostics` 的 NULL-owner 列：沒有人讀得到，但全域上限 200 列。**Keep**。
- `owners.last_activity_at`：不再參與 cleanup 判定，但 SA 清單仍會顯示。**Keep**。
- `iv_backfill_runs`、`rate_cache`、`dividend_cache`、`treasury_year_cache`、`chain_backoff`：以 key 自然有界的 shared facts。**Keep**。
- `current_results`：每個 scenario 恆定一列。**Keep**。
- `rate_limits`：看起來會長，但每天都會 purge。**Keep**。
- 最新一份 `snapshot`：raw-data／CSV 的唯一來源。**Keep**。
- 「`solo` 資料 cron 永遠清不到」：這不是 bug，反而是它在 AUTH-07 之前沒被誤刪的原因（cron 只走 `owners` 表）。

---

## 11. Findings

### P0

**沒有。** 沒有找到正在發生的資料毀損或安全事故。

### P1

**P1-A　`migrate_owner()` 不處理衝突，也不是原子操作，會阻礙 AUTH-07（已在本地 Postgres 實證）**
- 位置：`api_app/storage/postgres.py:1142-1150`
- 現象：9 張表逐條 autocommit `UPDATE`，沒有包 transaction。`owner_settings`（PK=`owner_id`）、`owner_credentials`／`owner_verifications`（PK=`owner_id, provider`）上，如果目標 owner 已經有列，就會 `UniqueViolation`。
- 實證：在本地臨時 DB 讓 `solo` 與 `target` 各有一筆 `owner_settings`、`solo` 有 1 個 scenario，然後呼叫 `migrate_owner`。
  - Postgres：拋出 `UniqueViolation`，而且 **`scenarios` 已經搬到 target、`owner_settings` 仍然卡在 solo**（半遷移）。重跑還是會在同一個地方失敗。
  - `MemoryStorage`：不報錯，**直接用 solo 的設定覆蓋 target 的設定**。
  - 兩個 backend 行為不一致，contract test（`test_storage_contract.py:1187-1224`）也沒有覆蓋「target 已經有資料」的情境。
- 為什麼真的會發生：見 P1-B。依照 runbook 取得 target owner 最自然的方式之一就是「存一次設定」，而這正好會製造衝突。
- 預檢：Q13。

**P1-B　AUTH-07 runbook 與實際行為不一致，而且遷移範圍有缺口**
1. `scripts/migrate_solo_to_owner.py` 檔頭的 HITL 步驟寫著「造訪首頁劇本清單，middleware 會自動建立 owner」。但 SECURITY-FIX-01 改成 deferred owner creation 之後，**只有寫入**（建立劇本、`PUT /api/settings`、`PUT credential`）才會建立 owner（`main.py:1424-1428`、`2562`、`3542`、`3569`）。照舊 runbook 做，會找不到 owner（腳本的 `get_owner` 會安全擋下）；如果改用「存設定」來建立 owner，就會撞上 P1-A。
2. legacy singleton 三表不在搬遷範圍，NULL-owner 列也不在（見 §8）。Owner 的舊資料源設定／舊 credential，只有在事先複製成 `owner_*('solo')` 時才會跟著走。
3. 腳本結尾印「solo 底下 10 張表」，實際是 9 張（文字小誤，順手更正即可）。
- 預檢：Q06（NULL）、Q12（legacy 是否已複製）、Q13。

**P1-C　每次刷新的 history ledger 無界成長；它的保留理由（OD-06）已經被後續決策改變（需要 Owner 決策，不是 code bug）**
- Producer：`_refresh_and_save`（`main.py:2875-2889`）每次刷新，每個 live scenario 各寫 1 份 snapshot、1 列 results、1 列 events。**SW-10（#340）移除了 30 分鐘節流**，所以現在每一次開站、每一次按刷新都會寫。Run 內同 symbol 的 K 個劇本會寫 K 份一模一樣的 snapshot（RL-28 還沒施工）。
- Consumer：只有**最新一份** snapshot 有讀取路徑（`main.py:3094-3103`）。歷史 snapshot／`results` fact 列／`events` 都沒有任何前端呼叫者；`snapshot_replay.py` 也已經沒有任何 import。
- Retention：無。匿名 owner 閒置 187 天後會連同 owner 一起刪掉；**活躍 owner 和 protected Owner 會一直長下去**。
- 前提改變：OD-06（`docs/spec/scaling-foundation.md:124-131`）把「永久保存」的理由升級成「歷史 net cost 唯一的完整來源」，但 **Spread net-cost history 已經在 SW-12（#342）整個退役**。同一份 spec 也寫著：「Neon Free 0.5 GB ⇒ TLT 約 1,000 次／SPY 約 200 次刷新後仍會滿」（`:245-247`）。`STORAGE_ALERT_CAP_BYTES` 預設 512 MiB。
- 結論：現在是「每次開站 × 每個 live scenario × MB 級原始 payload」在無界累積，而原本最強的保留理由已經不存在。**要不要保留、保留多少，需要 Owner 重新裁示**。可選方向：只留最新 N 份或 N 天、RL-28 去重、搬到 archival／object storage、或重新確認 OD-06 維持永久。實際成長速度看 Q09c／Q09d。

### P2（可以延後）

- **P2-1** SCALE-16 之前 `results.view` 的完整 payload：已經沒有讀取端，可回收的空間可能是整個 DB 最大的一塊（研究實測 3.17 MB／列）。前提是先確認 `backfill_result_fact_context` 已經補齊（Q10c = 0），再把 `view` 設成 NULL。不會再增長。
- **P2-2** `events` 無界、而且前端不讀。單列很小，建議跟 P1-C 一起決定 retention。
- **P2-3** `contract_iv_history`：到期合約從不 GC（Q19d）。
- **P2-4** `iv_observations`：沒有 retention，每個 symbol 每年約 66 列；只要還有 live scenario 就還有用，孤兒 symbol 可以清（Q19b）。
- **P2-5** `role_sessions`：revoked 列、以及超過 cookie 400 天的 active 列會永久累積（Q14）。量極小；清掉這些列不會改變任何有效 session 的行為。
- **P2-6** `delete_scenario`／`clear_results` 沒有包 transaction，再加上 refresh 與 delete 的 race，可能留下 child orphan。最終會被 `delete_owner` 收掉，protected Owner 的則不會（Q07）。
- **P2-7** legacy singleton 三表：AUTH-07 之後變成 true orphan（`provider_credentials` 可能含 vendor token），連同 `solo` read-through 分支一起退役。
- **P2-8**（條件式）`operational_metrics` 裡已退休的 metric 名稱永遠不會被 trim。目前沒有退休項目；Q17a 如果出現 `in_catalogue=f` 才成立。

### Keep
見 §10。

---

## 12. Recommended cleanup order

1. **Owner 跑一次 `db-lifecycle-production-audit.sql`**，把本報告裡「待 SQL」的數字補上。重點看 Q06、Q12、Q13。
2. **在執行 AUTH-07 之前修 P1-A＋P1-B**（code＋runbook）：
   - `migrate_owner` 改成單一 transaction，並處理衝突（先定好 solo 與 target 誰優先）；
   - `MemoryStorage` 跟著對齊，補一條「target 已有資料」的 contract test；
   - runbook 改成「用寫入建立 owner」，並把「先跑 `backfill_owner_ids.py`、`backfill_settings_to_owner.py`，再跑 Q12／Q13 預檢」列為前置步驟。
3. **Owner HITL：AUTH-07**（dry-run → confirm → 冪等重跑）。完成後 Q06 的 `solo`／NULL 應該全為 0。
4. **Owner 對 P1-C 重新裁示 OD-06**，然後依裁示實作 snapshot／results／events 的 retention 或去重。
5. P2-1：先確認 Q10c=0，再把 legacy `results.view` 設成 NULL（回收空間需要 Owner 另外決定是否 `VACUUM FULL`）。
6. P2-7：確認 AUTH-07 穩定後，退役 legacy singleton 三表與 `solo` read-through code。
7. P2-3／P2-4：IV cache 加上到期 GC／孤兒 symbol GC。
8. P2-5：cleanup cron 順便 purge revoked／過期的 `role_sessions`。
9. P2-6：`delete_scenario`／`clear_results` 包進 transaction。

> 本輪到此為止：**不做任何 cleanup implementation**，等 Owner／PM 決定。
