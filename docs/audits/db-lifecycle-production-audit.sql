-- =====================================================================
-- CLAUDE-DB-LIFECYCLE-AUDIT-001 — Production read-only audit (Neon)
-- =====================================================================
-- 用法：整份貼進 Neon SQL Editor，按一次 Run。
--
-- * 單一 SELECT 敘述、單一結果表（欄位：q / item / val / note），依
--   q（Q01、Q02…）再依 item 排序。整份結果可直接複製回報。
-- * 100% read-only：只有 SELECT、系統目錄查詢、pg_size 函式，以及
--   query_to_xml() 動態執行的 `SELECT count(*)`。沒有任何 INSERT /
--   UPDATE / DELETE / ALTER / DROP / VACUUM / 會寫入的函式。
-- * 不輸出任何 token / credential / password / cookie / IP / payload。
--   owner_id 只輸出前 8 碼（protected owner 與 'solo' 除外，AUTH-07
--   遷移需要完整值）。provider 名稱是公開常數（非 secret）。
-- * 時間欄位在這個 schema 是 ISO 字串（`now_utc_iso()`），比較前以
--   regex 防呆再轉 timestamptz。
-- * `rate_limits` 是 #346 最新加的表，以 to_regclass 防呆：部署後若還沒
--   有任何請求讓 app 建表，該列會顯示 'table missing' 而不是整份失敗。
--
-- 對照報告：docs/audits/db-lifecycle-audit-2026-09.md
-- =====================================================================
SELECT q, item, val, note FROM (

-- ---------------------------------------------------------------------
-- Q01  全部 public tables：精確列數＋大小＋是否為目前程式碼認得的表
--      （in_code=NO 代表 schema 有、程式完全沒讀寫 → 候選 legacy）
-- ---------------------------------------------------------------------
SELECT 'Q01 table inventory' AS q, c.relname::text AS item,
       (xpath('/row/c/text()', query_to_xml(
           format('SELECT count(*) AS c FROM public.%I', c.relname),
           false, true, '')))[1]::text AS val,
       format('total=%s heap=%s toast+idx=%s in_code=%s',
              pg_size_pretty(pg_total_relation_size(c.oid)),
              pg_size_pretty(pg_relation_size(c.oid)),
              pg_size_pretty(pg_total_relation_size(c.oid) - pg_relation_size(c.oid)),
              CASE WHEN c.relname = ANY (ARRAY[
                'scenarios','results','snapshots','events','rate_cache',
                'dividend_cache','treasury_year_cache','chain_backoff',
                'data_source_settings','provider_credentials',
                'provider_verifications','iv_observations','iv_backfill_runs',
                'contract_iv_history','diagnostics','operational_metrics',
                'owner_settings','owner_credentials','owner_verifications',
                'current_results','owners','browser_identities',
                'superuser_audit_log','role_sessions','rate_limits'])
                   THEN 'yes' ELSE 'NO' END) AS note
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')

UNION ALL
SELECT 'Q01 table inventory', '~ database total', pg_size_pretty(pg_database_size(current_database())),
       'pg_database_size（Neon 計費口徑近似值）'
UNION ALL
SELECT 'Q01 table inventory', '~ retired narrow_history still present?',
       (to_regclass('public.narrow_history') IS NOT NULL)::text,
       'LEGACY-CLEANUP-003 應為 false'

-- ---------------------------------------------------------------------
-- Q02  每張表 oldest / newest 時間戳（TEXT ISO 欄位，字典序＝時間序）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q02 oldest/newest', 'scenarios.created_at', min(created_at), max(created_at) FROM scenarios
UNION ALL SELECT 'Q02 oldest/newest', 'results.analyzed_at', min(analyzed_at), max(analyzed_at) FROM results
UNION ALL SELECT 'Q02 oldest/newest', 'current_results.analyzed_at', min(analyzed_at), max(analyzed_at) FROM current_results
UNION ALL SELECT 'Q02 oldest/newest', 'snapshots.analyzed_at', min(analyzed_at), max(analyzed_at) FROM snapshots
UNION ALL SELECT 'Q02 oldest/newest', 'events.ts', min(ts), max(ts) FROM events
UNION ALL SELECT 'Q02 oldest/newest', 'diagnostics.ts', min(ts), max(ts) FROM diagnostics
UNION ALL SELECT 'Q02 oldest/newest', 'owners.created_at', min(created_at), max(created_at) FROM owners
UNION ALL SELECT 'Q02 oldest/newest', 'owners.last_activity_at', min(last_activity_at), max(last_activity_at) FROM owners
UNION ALL SELECT 'Q02 oldest/newest', 'browser_identities.issued_at', min(issued_at), max(issued_at) FROM browser_identities
UNION ALL SELECT 'Q02 oldest/newest', 'browser_identities.last_seen_at', min(last_seen_at), max(last_seen_at) FROM browser_identities
UNION ALL SELECT 'Q02 oldest/newest', 'role_sessions.issued_at', min(issued_at), max(issued_at) FROM role_sessions
UNION ALL SELECT 'Q02 oldest/newest', 'superuser_audit_log.ts', min(ts), max(ts) FROM superuser_audit_log
UNION ALL SELECT 'Q02 oldest/newest', 'operational_metrics.bucket', min(bucket), max(bucket) FROM operational_metrics
UNION ALL SELECT 'Q02 oldest/newest', 'owner_settings.updated_at', min(updated_at), max(updated_at) FROM owner_settings
UNION ALL SELECT 'Q02 oldest/newest', 'owner_credentials.updated_at', min(updated_at), max(updated_at) FROM owner_credentials
UNION ALL SELECT 'Q02 oldest/newest', 'owner_verifications.checked_at', min(checked_at), max(checked_at) FROM owner_verifications
UNION ALL SELECT 'Q02 oldest/newest', 'data_source_settings.updated_at (legacy)', min(updated_at), max(updated_at) FROM data_source_settings
UNION ALL SELECT 'Q02 oldest/newest', 'provider_credentials.updated_at (legacy)', min(updated_at), max(updated_at) FROM provider_credentials
UNION ALL SELECT 'Q02 oldest/newest', 'provider_verifications.checked_at (legacy)', min(checked_at), max(checked_at) FROM provider_verifications
UNION ALL SELECT 'Q02 oldest/newest', 'iv_observations.observed_on', min(observed_on), max(observed_on) FROM iv_observations
UNION ALL SELECT 'Q02 oldest/newest', 'iv_backfill_runs.ran_on', min(ran_on), max(ran_on) FROM iv_backfill_runs
UNION ALL SELECT 'Q02 oldest/newest', 'contract_iv_history.last_attempt_on', min(last_attempt_on), max(last_attempt_on) FROM contract_iv_history
UNION ALL SELECT 'Q02 oldest/newest', 'dividend_cache.fetched_at', min(fetched_at), max(fetched_at) FROM dividend_cache
UNION ALL SELECT 'Q02 oldest/newest', 'treasury_year_cache.year', min(year)::text, max(year)::text FROM treasury_year_cache
UNION ALL SELECT 'Q02 oldest/newest', 'rate_cache.fetched_at', min(fetched_at), max(fetched_at) FROM rate_cache
UNION ALL SELECT 'Q02 oldest/newest', 'chain_backoff.observed_at', min(observed_at), max(observed_at) FROM chain_backoff
UNION ALL SELECT 'Q02 oldest/newest', 'rate_limits.window_start',
       CASE WHEN to_regclass('public.rate_limits') IS NULL THEN 'table missing' ELSE
         (xpath('/row/c/text()', query_to_xml(
           'SELECT to_timestamp(min(window_start))::text AS c FROM rate_limits', false, true, '')))[1]::text END,
       CASE WHEN to_regclass('public.rate_limits') IS NULL THEN '' ELSE
         (xpath('/row/c/text()', query_to_xml(
           'SELECT to_timestamp(max(window_start))::text AS c FROM rate_limits', false, true, '')))[1]::text END

-- ---------------------------------------------------------------------
-- Q03  owners 總覽（registry）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q03 owners', 'a. owners total', count(*)::text, '' FROM owners
UNION ALL SELECT 'Q03 owners', 'b. protected', count(*)::text, '' FROM owners WHERE protected
UNION ALL SELECT 'Q03 owners', 'c. synthetic (PB-07)', count(*)::text, '' FROM owners WHERE is_synthetic
UNION ALL SELECT 'Q03 owners', 'd. with >=1 scenario', count(*)::text, '' FROM owners o
  WHERE EXISTS (SELECT 1 FROM scenarios s WHERE s.owner_id = o.owner_id)
UNION ALL SELECT 'Q03 owners', 'e. empty (no scenario/settings/credential = has_data false)', count(*)::text,
       'empty_retention_days=1：非 protected 的應在 cron 後 ≤2 天內消失' FROM owners o
  WHERE NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.owner_id = o.owner_id)
    AND NOT EXISTS (SELECT 1 FROM owner_settings st WHERE st.owner_id = o.owner_id)
    AND NOT EXISTS (SELECT 1 FROM owner_credentials cr WHERE cr.owner_id = o.owner_id)
UNION ALL SELECT 'Q03 owners', 'f. without any browser_identity', count(*)::text,
       '非 synthetic 卻沒有 identity ＝ 永遠無法由 cookie 到達（logical orphan）' FROM owners o
  WHERE NOT EXISTS (SELECT 1 FROM browser_identities b WHERE b.owner_id = o.owner_id)
UNION ALL SELECT 'Q03 owners', 'g. without identity AND not synthetic AND not protected', count(*)::text, '' FROM owners o
  WHERE NOT o.is_synthetic AND NOT o.protected
    AND NOT EXISTS (SELECT 1 FROM browser_identities b WHERE b.owner_id = o.owner_id)
UNION ALL SELECT 'Q03 owners', 'h. with >1 browser_identity', count(*)::text, 'claim_browser_token 每 owner 只建 1 顆' FROM (
  SELECT owner_id FROM browser_identities GROUP BY owner_id HAVING count(*) > 1) x
UNION ALL SELECT 'Q03 owners', 'i. protected owner id (full)', owner_id,
       format('created=%s last_activity=%s', created_at, last_activity_at) FROM owners WHERE protected
UNION ALL SELECT 'Q03 owners', 'j. owners row for ''solo'' exists?', (count(*) > 0)::text, '' FROM owners WHERE owner_id = 'solo'

-- ---------------------------------------------------------------------
-- Q04  browser_identities
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q04 browser_identities', 'a. total', count(*)::text, '' FROM browser_identities
UNION ALL SELECT 'Q04 browser_identities', 'b. owner missing (TRUE ORPHAN)', count(*)::text, '' FROM browser_identities b
  WHERE NOT EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = b.owner_id)
UNION ALL SELECT 'Q04 browser_identities', 'c. last_seen older than 187d', count(*)::text, '' FROM browser_identities
  WHERE last_seen_at ~ '^\d{4}-\d{2}-\d{2}T' AND last_seen_at::timestamptz < now() - interval '187 days'

-- ---------------------------------------------------------------------
-- Q05  匿名 lifecycle 分類（重現 anonymous_lifecycle.classify()，預設
--      180/7/1 天；protected 另計）。eligible 持續 >0 且 Q17 cron 有跑
--      ＝ batch 不夠大或刪除失敗。
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q05 lifecycle (defaults 180/7/1)', state, count(*)::text, '' FROM (
  SELECT CASE
    WHEN o.protected THEN 'protected (excluded)'
    WHEN anchor IS NULL THEN 'unparseable anchor (treated active)'
    WHEN NOT has_data AND now() - anchor >= interval '1 day' THEN 'eligible_for_hard_delete (empty)'
    WHEN NOT has_data THEN 'active (empty, <1d)'
    WHEN now() - anchor >= interval '187 days' THEN 'eligible_for_hard_delete (with data)'
    WHEN now() - anchor >= interval '180 days' THEN 'abandoned'
    ELSE 'active (with data)' END AS state
  FROM (
    SELECT o.owner_id, o.protected,
      (EXISTS (SELECT 1 FROM scenarios s WHERE s.owner_id = o.owner_id)
       OR EXISTS (SELECT 1 FROM owner_settings st WHERE st.owner_id = o.owner_id)
       OR EXISTS (SELECT 1 FROM owner_credentials cr WHERE cr.owner_id = o.owner_id)) AS has_data,
      CASE WHEN coalesce(bi.last_seen, o.created_at) ~ '^\d{4}-\d{2}-\d{2}T'
           THEN coalesce(bi.last_seen, o.created_at)::timestamptz END AS anchor
    FROM owners o
    LEFT JOIN (SELECT owner_id, max(last_seen_at) AS last_seen
               FROM browser_identities GROUP BY owner_id) bi ON bi.owner_id = o.owner_id
  ) o
) z GROUP BY state

-- ---------------------------------------------------------------------
-- Q06  9 張 owner-scoped 表：owner_id 歸屬分類
--      registered＝在 owners 表；solo＝legacy lineage；NULL＝SCALE-06
--      backfill 沒跑；pending:%＝不該存在；unregistered＝owner 不存在
--      （TRUE/LOGICAL ORPHAN，cron 與 SA 清單都看不到）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q06 owner_id class', t || ' / ' || cls, count(*)::text, '' FROM (
  SELECT 'scenarios' t, owner_id FROM scenarios
  UNION ALL SELECT 'results', owner_id FROM results
  UNION ALL SELECT 'current_results', owner_id FROM current_results
  UNION ALL SELECT 'snapshots', owner_id FROM snapshots
  UNION ALL SELECT 'events', owner_id FROM events
  UNION ALL SELECT 'diagnostics', owner_id FROM diagnostics
  UNION ALL SELECT 'owner_settings', owner_id FROM owner_settings
  UNION ALL SELECT 'owner_credentials', owner_id FROM owner_credentials
  UNION ALL SELECT 'owner_verifications', owner_id FROM owner_verifications
) r
CROSS JOIN LATERAL (SELECT CASE
    WHEN r.owner_id IS NULL THEN 'NULL'
    WHEN r.owner_id = 'solo' THEN 'solo'
    WHEN r.owner_id LIKE 'pending:%' THEN 'pending:*'
    WHEN EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = r.owner_id) THEN 'registered'
    ELSE 'unregistered' END AS cls) c
GROUP BY t, cls

-- ---------------------------------------------------------------------
-- Q07  scenario child rows → parent scenario 不存在（TRUE ORPHAN）
--      與 child/parent owner_id 不一致
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q07 scenario children', 'a. results without scenario', count(*)::text, '' FROM results r
  WHERE NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = r.scenario_id)
UNION ALL SELECT 'Q07 scenario children', 'b. current_results without scenario', count(*)::text, '' FROM current_results r
  WHERE NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = r.scenario_id)
UNION ALL SELECT 'Q07 scenario children', 'c. snapshots without scenario', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(snapshot)), 0)) FROM snapshots r
  WHERE NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = r.scenario_id)
UNION ALL SELECT 'Q07 scenario children', 'd. events without scenario (scenario_id not null)', count(*)::text, '' FROM events r
  WHERE r.scenario_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = r.scenario_id)
UNION ALL SELECT 'Q07 scenario children', 'e. events with scenario_id NULL', count(*)::text, '' FROM events WHERE scenario_id IS NULL
UNION ALL SELECT 'Q07 scenario children', 'f. results owner != scenario owner', count(*)::text, '' FROM results r
  JOIN scenarios s ON s.id = r.scenario_id WHERE r.owner_id IS DISTINCT FROM s.owner_id
UNION ALL SELECT 'Q07 scenario children', 'g. snapshots owner != scenario owner', count(*)::text, '' FROM snapshots r
  JOIN scenarios s ON s.id = r.scenario_id WHERE r.owner_id IS DISTINCT FROM s.owner_id
UNION ALL SELECT 'Q07 scenario children', 'h. current_results owner != scenario owner', count(*)::text, '' FROM current_results r
  JOIN scenarios s ON s.id = r.scenario_id WHERE r.owner_id IS DISTINCT FROM s.owner_id
UNION ALL SELECT 'Q07 scenario children', 'i. scenarios analysed but no current_results', count(*)::text,
       'SCALE-16 前的舊劇本若從未再刷新會出現在這裡' FROM scenarios s
  WHERE EXISTS (SELECT 1 FROM results r WHERE r.scenario_id = s.id)
    AND NOT EXISTS (SELECT 1 FROM current_results c WHERE c.scenario_id = s.id)

-- ---------------------------------------------------------------------
-- Q08  每個 owner 的資料量（前 20 名，依 snapshot bytes）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q08 per-owner volume', item, val, note FROM (
  SELECT CASE WHEN s.owner_id IS NULL THEN '(NULL)'
              WHEN s.owner_id = 'solo' OR o.protected THEN s.owner_id
              ELSE left(s.owner_id, 8) || '…' END AS item,
         format('scenarios=%s', count(DISTINCT s.id)) AS val,
         format('archived=%s expired_month=%s snapshots=%s snap_bytes=%s results=%s events=%s registered=%s protected=%s',
                count(DISTINCT s.id) FILTER (WHERE s.archived_at IS NOT NULL),
                count(DISTINCT s.id) FILTER (WHERE s.target_month < to_char(now() AT TIME ZONE 'America/New_York', 'YYYY-MM')),
                max(sn.n), pg_size_pretty(max(sn.b)), max(rs.n), max(ev.n),
                (o.owner_id IS NOT NULL), coalesce(o.protected, false)) AS note,
         max(sn.b) AS sort_b
  FROM scenarios s
  LEFT JOIN owners o ON o.owner_id = s.owner_id
  LEFT JOIN (SELECT owner_id, count(*) n, sum(pg_column_size(snapshot)) b FROM snapshots GROUP BY owner_id) sn
         ON sn.owner_id IS NOT DISTINCT FROM s.owner_id
  LEFT JOIN (SELECT owner_id, count(*) n FROM results GROUP BY owner_id) rs
         ON rs.owner_id IS NOT DISTINCT FROM s.owner_id
  LEFT JOIN (SELECT owner_id, count(*) n FROM events GROUP BY owner_id) ev
         ON ev.owner_id IS NOT DISTINCT FROM s.owner_id
  GROUP BY s.owner_id, o.owner_id, o.protected
  ORDER BY sort_b DESC NULLS LAST LIMIT 20
) top

-- ---------------------------------------------------------------------
-- Q09  snapshots：latest（有讀取路徑）vs 歷史（唯一讀取端只讀最新）
--      與最近 14 天每日成長
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q09 snapshots', 'a. latest per scenario (= current_results.analyzed_at)', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(sn.snapshot)), 0)) FROM snapshots sn
  JOIN current_results c ON c.scenario_id = sn.scenario_id AND c.analyzed_at = sn.analyzed_at
UNION ALL SELECT 'Q09 snapshots', 'b. historical (not latest; no UI read path)', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(sn.snapshot)), 0)) FROM snapshots sn
  WHERE NOT EXISTS (SELECT 1 FROM current_results c
                    WHERE c.scenario_id = sn.scenario_id AND c.analyzed_at = sn.analyzed_at)
UNION ALL SELECT 'Q09 snapshots', 'c. avg / max compressed bytes per row',
       pg_size_pretty(coalesce(avg(pg_column_size(snapshot)), 0)::bigint),
       pg_size_pretty(coalesce(max(pg_column_size(snapshot)), 0)::bigint) FROM snapshots
UNION ALL SELECT 'Q09 snapshots', 'd. day ' || d, n::text, pg_size_pretty(b) FROM (
  SELECT left(analyzed_at, 10) d, count(*) n, sum(pg_column_size(snapshot)) b
  FROM snapshots WHERE analyzed_at >= to_char(now() - interval '14 days', 'YYYY-MM-DD')
  GROUP BY 1) g
UNION ALL SELECT 'Q09 snapshots', 'e. max snapshots for a single scenario', coalesce(max(n), 0)::text, '' FROM (
  SELECT count(*) n FROM snapshots GROUP BY scenario_id) g

-- ---------------------------------------------------------------------
-- Q10  results ledger：SCALE-16 前的舊列仍帶完整 view（已無任何讀取端）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q10 results ledger', 'a. rows with view NOT NULL (pre-SCALE-16 legacy payload)', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(view)), 0)) FROM results WHERE view IS NOT NULL
UNION ALL SELECT 'Q10 results ledger', 'b. rows with view NULL (fact-only)', count(*)::text, '' FROM results WHERE view IS NULL
UNION ALL SELECT 'Q10 results ledger', 'c. rows missing fact context (resolved_params NULL)', count(*)::text,
       'backfill_result_fact_context.py 未補齊的列' FROM results WHERE resolved_params IS NULL
UNION ALL SELECT 'Q10 results ledger', 'd. current_results view bytes', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(view)), 0)) FROM current_results

-- ---------------------------------------------------------------------
-- Q11  events：依事件種類（零前端消費端）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q11 events by type', event, count(*)::text,
       pg_size_pretty(sum(pg_column_size(payload))::bigint) FROM events GROUP BY event

-- ---------------------------------------------------------------------
-- Q12  solo lineage 與 legacy singleton 表（AUTH-07 輸入）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q12 solo / legacy', 'a. legacy data_source_settings rows', count(*)::text,
       '只在 owner==solo 時被 read-through；AUTH-07 後永遠讀不到' FROM data_source_settings
UNION ALL SELECT 'Q12 solo / legacy', 'b. legacy provider_credentials providers', count(*)::text,
       coalesce(string_agg(provider, ','), '') FROM provider_credentials
UNION ALL SELECT 'Q12 solo / legacy', 'c. legacy provider_verifications providers', count(*)::text,
       coalesce(string_agg(provider, ','), '') FROM provider_verifications
UNION ALL SELECT 'Q12 solo / legacy', 'd. owner_settings has solo row?', (count(*) > 0)::text,
       'false 且 a>0 ⇒ migrate_owner 不會帶走 legacy 設定' FROM owner_settings WHERE owner_id = 'solo'
UNION ALL SELECT 'Q12 solo / legacy', 'e. owner_credentials solo providers', count(*)::text,
       coalesce(string_agg(provider, ','), '') FROM owner_credentials WHERE owner_id = 'solo'
UNION ALL SELECT 'Q12 solo / legacy', 'f. legacy credential providers NOT yet copied to solo', count(*)::text,
       coalesce(string_agg(provider, ','), '') FROM provider_credentials p
  WHERE NOT EXISTS (SELECT 1 FROM owner_credentials c WHERE c.owner_id = 'solo' AND c.provider = p.provider)

-- ---------------------------------------------------------------------
-- Q13  AUTH-07 PK 衝突預檢：migrate_owner() 是逐表 autocommit UPDATE，
--      目標 owner 若已有 owner_settings／同 provider 的 credential／
--      verification，Postgres 會 UniqueViolation 並留下半遷移狀態。
--      下列列出「每個已登記、非 solo 的 owner」中會撞 PK 的數量。
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q13 AUTH-07 conflict precheck', 'a. solo has owner_settings AND N other owners also have one',
       count(*)::text, '若 AUTH-07 目標 owner 在這群裡 ⇒ migrate 會失敗' FROM owner_settings
  WHERE owner_id <> 'solo' AND EXISTS (SELECT 1 FROM owner_settings WHERE owner_id = 'solo')
UNION ALL SELECT 'Q13 AUTH-07 conflict precheck', 'b. protected/target owner ' || o.owner_id,
       format('settings=%s cred_overlap=%s verif_overlap=%s',
         EXISTS (SELECT 1 FROM owner_settings st WHERE st.owner_id = o.owner_id)
           AND EXISTS (SELECT 1 FROM owner_settings st WHERE st.owner_id = 'solo'),
         (SELECT count(*) FROM owner_credentials a JOIN owner_credentials b
            ON a.provider = b.provider WHERE a.owner_id = o.owner_id AND b.owner_id = 'solo'),
         (SELECT count(*) FROM owner_verifications a JOIN owner_verifications b
            ON a.provider = b.provider WHERE a.owner_id = o.owner_id AND b.owner_id = 'solo')),
       '任一非 false/0 ⇒ 需先處理衝突再跑 migrate_solo_to_owner.py' FROM owners o WHERE o.protected

-- ---------------------------------------------------------------------
-- Q14  role_sessions（無 server-side 到期；cookie Max-Age 400 天）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q14 role_sessions', 'a. total', count(*)::text, '' FROM role_sessions
UNION ALL SELECT 'Q14 role_sessions', 'b. active (revoked_at NULL) by role ' || role, count(*)::text, '' FROM role_sessions
  WHERE revoked_at IS NULL GROUP BY role
UNION ALL SELECT 'Q14 role_sessions', 'c. revoked (dead rows)', count(*)::text, '' FROM role_sessions WHERE revoked_at IS NOT NULL
UNION ALL SELECT 'Q14 role_sessions', 'd. active but older than cookie Max-Age 400d', count(*)::text,
       '瀏覽器已不會再送出，但 server 仍視為有效' FROM role_sessions
  WHERE revoked_at IS NULL AND issued_at ~ '^\d{4}-\d{2}-\d{2}T' AND issued_at::timestamptz < now() - interval '400 days'
UNION ALL SELECT 'Q14 role_sessions', 'e. oldest active issued_at', coalesce(min(issued_at), ''), '' FROM role_sessions WHERE revoked_at IS NULL

-- ---------------------------------------------------------------------
-- Q15  rate_limits（purge：cleanup cron 每日，保留 window 結束後 1h）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q15 rate_limits', 'a. total rows',
       CASE WHEN to_regclass('public.rate_limits') IS NULL THEN 'table missing' ELSE
         (xpath('/row/c/text()', query_to_xml('SELECT count(*) AS c FROM rate_limits', false, true, '')))[1]::text END, ''
UNION ALL SELECT 'Q15 rate_limits', 'b. expired-but-not-purged (window end + 1h < now)',
       CASE WHEN to_regclass('public.rate_limits') IS NULL THEN 'table missing' ELSE
         (xpath('/row/c/text()', query_to_xml(
           'SELECT count(*) AS c FROM rate_limits WHERE window_start + window_seconds < extract(epoch FROM now())::bigint - 3600',
           false, true, '')))[1]::text END,
       '每日 cron 之間最多累積 ~1 天；遠大於此代表 cron 沒跑'
UNION ALL SELECT 'Q15 rate_limits', 'c. rows by scope',
       CASE WHEN to_regclass('public.rate_limits') IS NULL THEN 'table missing' ELSE
         coalesce((xpath('/row/c/text()', query_to_xml(
           'SELECT string_agg(scope || ''='' || n, '', '') AS c FROM (SELECT scope, count(*) n FROM rate_limits GROUP BY scope) x',
           false, true, '')))[1]::text, '(empty)') END, 'key 不輸出（owner_id / HMAC）'

-- ---------------------------------------------------------------------
-- Q16  superuser_audit_log（刻意無 retention）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q16 audit log', 'a. total', count(*)::text,
       format('oldest=%s newest=%s', min(ts), max(ts)) FROM superuser_audit_log
UNION ALL SELECT 'Q16 audit log', 'b. action ' || action, count(*)::text, '' FROM superuser_audit_log GROUP BY action
UNION ALL SELECT 'Q16 audit log', 'c. target owner no longer exists', count(*)::text,
       '預期：delete_owner 的紀錄本來就指向已刪 owner（Keep）' FROM superuser_audit_log a
  WHERE target_owner_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = a.target_owner_id)

-- ---------------------------------------------------------------------
-- Q17  operational_metrics（trim-on-write 30 天，per metric）＋cron 健康
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q17 metrics', 'a. metric ' || metric, count(*)::text,
       format('buckets %s..%s older_than_30d=%s in_catalogue=%s', min(bucket), max(bucket),
              count(*) FILTER (WHERE bucket < to_char(now() - interval '31 days', 'YYYY-MM-DD')),
              metric = ANY (ARRAY['chain_fetch_count','chain_429_count','stale_serve_count',
                'cold_miss_count','refresh_duration_ms','abandoned_owner_cleanup_count',
                'new_owner_count','empty_owner_cleanup_count','owner_quota_block_count',
                'source_burst_block_count','new_owner_tier_block_count',
                'global_fuse_block_count','login_rate_limit_block_count']))
  FROM operational_metrics GROUP BY metric
UNION ALL SELECT 'Q17 metrics', 'b. cleanup cron ran on ' || bucket, sum(count)::text,
       format('owners_deleted=%s rows_deleted=%s', sum(count), sum(total)) FROM operational_metrics
  WHERE metric IN ('abandoned_owner_cleanup_count', 'empty_owner_cleanup_count')
    AND bucket >= to_char(now() - interval '10 days', 'YYYY-MM-DD')
  GROUP BY bucket
UNION ALL SELECT 'Q17 metrics', 'c. new owners on ' || bucket, sum(count)::text, '' FROM operational_metrics
  WHERE metric = 'new_owner_count' AND bucket >= to_char(now() - interval '10 days', 'YYYY-MM-DD')
  GROUP BY bucket

-- ---------------------------------------------------------------------
-- Q18  diagnostics（全域 trim 200 列）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q18 diagnostics', 'a. total (expect <= 200)', count(*)::text, '' FROM diagnostics
UNION ALL SELECT 'Q18 diagnostics', 'b. owner_id NULL (no reader)', count(*)::text, '' FROM diagnostics WHERE owner_id IS NULL

-- ---------------------------------------------------------------------
-- Q19  Shared market facts / caches（無 owner）
-- ---------------------------------------------------------------------
UNION ALL SELECT 'Q19 shared caches', 'a. iv_observations', count(*)::text,
       format('symbols=%s bytes=%s', count(DISTINCT symbol), pg_size_pretty(coalesce(sum(pg_column_size(surface)), 0)))
  FROM iv_observations
UNION ALL SELECT 'Q19 shared caches', 'b. iv_observations symbols with no live scenario', count(DISTINCT symbol)::text,
       '' FROM iv_observations i WHERE NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.symbol = i.symbol AND s.archived_at IS NULL)
UNION ALL SELECT 'Q19 shared caches', 'c. contract_iv_history', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(points)), 0)) FROM contract_iv_history
UNION ALL SELECT 'Q19 shared caches', 'd. contract_iv_history EXPIRED contracts (OCC YYMMDD < today)', count(*)::text,
       pg_size_pretty(coalesce(sum(pg_column_size(points)), 0)) FROM contract_iv_history
  WHERE substring(contract_symbol FROM '(\d{6})[CP]\d{8}$') IS NOT NULL
    AND '20' || substring(contract_symbol FROM '(\d{6})[CP]\d{8}$') < to_char(now(), 'YYYYMMDD')
UNION ALL SELECT 'Q19 shared caches', 'e. contract_iv_history unparseable OCC symbol', count(*)::text, '' FROM contract_iv_history
  WHERE substring(contract_symbol FROM '(\d{6})[CP]\d{8}$') IS NULL
UNION ALL SELECT 'Q19 shared caches', 'f. iv_backfill_runs', count(*)::text, '' FROM iv_backfill_runs
UNION ALL SELECT 'Q19 shared caches', 'g. dividend_cache symbols', count(*)::text,
       format('no_live_scenario=%s', count(*) FILTER (WHERE NOT EXISTS (
         SELECT 1 FROM scenarios s WHERE s.symbol = d.symbol AND s.archived_at IS NULL)))
  FROM dividend_cache d
UNION ALL SELECT 'Q19 shared caches', 'h. treasury_year_cache years', count(*)::text, '' FROM treasury_year_cache
UNION ALL SELECT 'Q19 shared caches', 'i. rate_cache rows (expect 1)', count(*)::text, '' FROM rate_cache
UNION ALL SELECT 'Q19 shared caches', 'j. chain_backoff sources', count(*)::text, coalesce(string_agg(source, ','), '') FROM chain_backoff

) audit
ORDER BY q, item;
