-- ANTI-ABUSE-PRODUCTION-001 Phase 1：Production 真實數據校準（READ ONLY）
--
-- 用法：Neon Console → SQL Editor，逐段貼上執行（每段是獨立的一個
-- SELECT），把每段的結果表貼回來即可。
--
-- 安全性：
-- - 全部都是 SELECT，沒有任何 INSERT／UPDATE／DELETE／DDL。
-- - 只輸出聚合數字，不輸出任何 owner_id、cookie token、credential。
--   `provider_credentials`／`owner_credentials`／`browser_identities.token`
--   完全沒有被查詢。
-- - 想再多一層保險，可以在每段前面加一行 `SET TRANSACTION READ ONLY;`
--   （Neon SQL Editor 每次執行是一個 transaction）。
--
-- 資料來源與限制（解讀結果前請先看）：
-- - `operational_metrics`：真正打上游的次數（`chain_fetch_count`），
--   只有「天」這個粒度、只保留 30 天、**沒有 owner 維度**（AC-7 紅線）。
-- - `events` 的 `ANALYSIS_COMPLETED`：每次分析成功各一筆，有 owner_id
--   與精確時間。用它估算 per-owner、per-minute／per-hour 的抓鏈次數：
--   同一個 owner、同一個 symbol、同一分鐘內的分析，視為同一次抓鏈
--   （Refresh Run 會讓同 symbol 的劇本共用一次抓取）。
--   ⚠ 抓了但分析失敗的那次不會有 event → 這是**下限**估計；Q2 會把它
--   跟 operational_metrics 的真實總數並列，讓大哥看出兩者差多少。
-- - Production 從來沒有記錄過 IP——source/IP 層的門檻無法從歷史資料
--   直接量測，只能由 per-owner 分布推（見報告）。
-- - PB-07 合成壓測如果在 production 跑過，`owners.is_synthetic = true`
--   的 owner 會被排除；但 operational_metrics 無法排除（沒有 owner 維度）。


-- ============================================================
-- Q0. 資料涵蓋範圍（先確認每張表有幾天資料可用）
-- 回傳：來源、最早、最晚、筆數
-- ============================================================
SELECT 'operational_metrics.chain_fetch_count' AS source,
       min(bucket) AS earliest, max(bucket) AS latest, count(*) AS n_rows
FROM operational_metrics WHERE metric = 'chain_fetch_count'
UNION ALL
SELECT 'events.ANALYSIS_COMPLETED', min(ts), max(ts), count(*)
FROM events WHERE event = 'ANALYSIS_COMPLETED'
UNION ALL
SELECT 'owners', min(created_at), max(created_at), count(*)
FROM owners;


-- ============================================================
-- Q1. 每日實際 vendor fetch（真實上游次數）＋ 距離 fuse 2000 多遠
-- 回傳：每天一列——總上游、cboe、yfinance、429 次數、佔 fuse 百分比
-- ============================================================
SELECT bucket AS day,
       sum(count) FILTER (WHERE metric = 'chain_fetch_count')                      AS vendor_fetches,
       sum(count) FILTER (WHERE metric = 'chain_fetch_count' AND source = 'cboe')     AS cboe,
       sum(count) FILTER (WHERE metric = 'chain_fetch_count' AND source = 'yfinance') AS yfinance,
       coalesce(sum(count) FILTER (WHERE metric = 'chain_429_count'), 0)           AS http_429,
       round(100.0 * sum(count) FILTER (WHERE metric = 'chain_fetch_count') / 2000, 1) AS pct_of_fuse_2000
FROM operational_metrics
WHERE metric IN ('chain_fetch_count', 'chain_429_count')
GROUP BY bucket
ORDER BY bucket;


-- ============================================================
-- Q2. 每日 active owner 數＋ 估算抓鏈（events）vs 真實上游（metrics）
-- 回傳：每天一列——active owner、分析次數、估算抓鏈、真實上游、覆蓋率
-- active owner＝當天至少有一次分析成功（開站自動刷新也算）的 owner
-- ============================================================
WITH a AS (
  SELECT e.owner_id,
         (e.ts::timestamptz AT TIME ZONE 'UTC')::date AS d,
         s.symbol,
         date_trunc('minute', e.ts::timestamptz) AS m
  FROM events e
  JOIN scenarios s ON s.id = e.scenario_id
  LEFT JOIN owners o ON o.owner_id = e.owner_id
  WHERE e.event = 'ANALYSIS_COMPLETED'
    AND e.ts::timestamptz >= now() - interval '30 days'
    AND coalesce(o.is_synthetic, false) = false
), per_day AS (
  SELECT d, count(DISTINCT owner_id) AS active_owners, count(*) AS analyses,
         count(DISTINCT (owner_id, symbol, m)) AS est_fetches
  FROM a GROUP BY d
), metric AS (
  SELECT bucket::date AS d, sum(count) AS vendor_fetches
  FROM operational_metrics WHERE metric = 'chain_fetch_count' GROUP BY bucket
)
SELECT coalesce(p.d, m.d) AS day, p.active_owners, p.analyses, p.est_fetches,
       m.vendor_fetches,
       round(100.0 * p.est_fetches / nullif(m.vendor_fetches, 0), 1) AS est_coverage_pct
FROM per_day p FULL JOIN metric m ON m.d = p.d
ORDER BY day;


-- ============================================================
-- Q3. 每 owner 每日 vendor fetch 分布（估算，排除 synthetic）
-- 回傳：一列一個族群——owner-day 數、median、p90、p95、p99、max
-- 另外把 protected owner（Owner 本人遷移後的那個，若已遷移）分開列
-- ============================================================
WITH a AS (
  SELECT e.owner_id, coalesce(o.protected, false) AS is_protected,
         (e.ts::timestamptz AT TIME ZONE 'UTC')::date AS d,
         s.symbol, date_trunc('minute', e.ts::timestamptz) AS m
  FROM events e
  JOIN scenarios s ON s.id = e.scenario_id
  LEFT JOIN owners o ON o.owner_id = e.owner_id
  WHERE e.event = 'ANALYSIS_COMPLETED'
    AND e.ts::timestamptz >= now() - interval '30 days'
    AND coalesce(o.is_synthetic, false) = false
), owner_day AS (
  SELECT owner_id, is_protected, d, count(DISTINCT (symbol, m)) AS fetches
  FROM a GROUP BY owner_id, is_protected, d
)
SELECT CASE WHEN is_protected THEN 'protected owner' ELSE 'anonymous owners' END AS population,
       count(*) AS owner_days,
       count(DISTINCT owner_id) AS owners,
       percentile_cont(0.50) WITHIN GROUP (ORDER BY fetches) AS median,
       percentile_cont(0.90) WITHIN GROUP (ORDER BY fetches) AS p90,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY fetches) AS p95,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY fetches) AS p99,
       max(fetches) AS max
FROM owner_day
GROUP BY is_protected;


-- ============================================================
-- Q4. 每分鐘／每小時峰值（per-owner 與全站，估算）
-- 回傳：四列——(per-owner｜site-wide) × (minute｜hour) 的 p99 與 max
-- ============================================================
WITH a AS (
  SELECT e.owner_id, s.symbol,
         date_trunc('minute', e.ts::timestamptz) AS m,
         date_trunc('hour', e.ts::timestamptz) AS h
  FROM events e
  JOIN scenarios s ON s.id = e.scenario_id
  LEFT JOIN owners o ON o.owner_id = e.owner_id
  WHERE e.event = 'ANALYSIS_COMPLETED'
    AND e.ts::timestamptz >= now() - interval '30 days'
    AND coalesce(o.is_synthetic, false) = false
), f AS (SELECT DISTINCT owner_id, symbol, m, h FROM a),
owner_min  AS (SELECT count(*) AS n FROM f GROUP BY owner_id, m),
owner_hour AS (SELECT count(*) AS n FROM f GROUP BY owner_id, h),
site_min   AS (SELECT count(*) AS n FROM f GROUP BY m),
site_hour  AS (SELECT count(*) AS n FROM f GROUP BY h)
SELECT 'per-owner / minute' AS scope, percentile_cont(0.99) WITHIN GROUP (ORDER BY n) AS p99, max(n) AS max FROM owner_min
UNION ALL SELECT 'per-owner / hour', percentile_cont(0.99) WITHIN GROUP (ORDER BY n), max(n) FROM owner_hour
UNION ALL SELECT 'site-wide / minute', percentile_cont(0.99) WITHIN GROUP (ORDER BY n), max(n) FROM site_min
UNION ALL SELECT 'site-wide / hour', percentile_cont(0.99) WITHIN GROUP (ORDER BY n), max(n) FROM site_hour;


-- ============================================================
-- Q5. symbol concentration（真實上游次數，最近 30 天）
-- 回傳：前 20 名 symbol 的次數、佔比、累積佔比；最後一列（rank 9999）是 distinct symbol 總數
-- （symbol 是公開的股票代號，不是個資）
-- ============================================================
WITH per_symbol AS (
  SELECT symbol, sum(count) AS fetches
  FROM operational_metrics
  WHERE metric = 'chain_fetch_count' AND symbol <> ''
  GROUP BY symbol
), ranked AS (
  SELECT symbol, fetches,
         round(100.0 * fetches / sum(fetches) OVER (), 1) AS share_pct,
         round(100.0 * sum(fetches) OVER (ORDER BY fetches DESC, symbol)
               / sum(fetches) OVER (), 1) AS cumulative_pct,
         row_number() OVER (ORDER BY fetches DESC, symbol) AS rnk
  FROM per_symbol
)
SELECT rnk AS rank, symbol, fetches, share_pct, cumulative_pct FROM ranked WHERE rnk <= 20
UNION ALL
SELECT 9999, 'TOTAL: ' || count(*) || ' distinct symbols', sum(fetches), 100.0, 100.0 FROM per_symbol
ORDER BY 1;


-- ============================================================
-- Q6. anonymous owner growth（每日新增、空 owner 比例、有劇本比例）
-- 回傳：每天一列——新增 owner、有劇本（含已封存）、空 owner、空 owner %、synthetic
-- ============================================================
WITH sc AS (SELECT owner_id, count(*) AS n FROM scenarios GROUP BY owner_id)
SELECT (o.created_at::timestamptz AT TIME ZONE 'UTC')::date AS day,
       count(*) AS new_owners,
       count(*) FILTER (WHERE coalesce(sc.n, 0) > 0) AS with_scenarios,
       count(*) FILTER (WHERE coalesce(sc.n, 0) = 0) AS empty_owners,
       round(100.0 * count(*) FILTER (WHERE coalesce(sc.n, 0) = 0) / count(*), 1) AS empty_pct,
       count(*) FILTER (WHERE o.is_synthetic) AS synthetic
FROM owners o LEFT JOIN sc ON sc.owner_id = o.owner_id
GROUP BY day
ORDER BY day;


-- ============================================================
-- Q7. owner 年齡／last_seen 分布＋現行 cleanup 規則下的風險
-- 回傳：一列一個年齡區間——owner 數、有劇本數、protected 數、
--       「現行規則下已算 abandoned（≥30 天無手動操作）但最近 7 天其實有回訪」數
-- 最後一列 'ALL' 附上最老 owner 的天數，驗證是否已有接近 180 天的資料
-- ============================================================
WITH sc AS (SELECT owner_id, count(*) AS n FROM scenarios GROUP BY owner_id),
seen AS (SELECT owner_id, max(last_seen_at::timestamptz) AS last_seen
         FROM browser_identities GROUP BY owner_id),
o AS (
  SELECT extract(epoch FROM now() - ow.created_at::timestamptz) / 86400 AS age_days,
         coalesce(sc.n, 0) > 0 AS has_sc,
         ow.protected,
         coalesce(ow.last_activity_at, ow.created_at)::timestamptz AS lifecycle_anchor,
         seen.last_seen
  FROM owners ow
  LEFT JOIN sc ON sc.owner_id = ow.owner_id
  LEFT JOIN seen ON seen.owner_id = ow.owner_id
  WHERE NOT ow.is_synthetic
)
SELECT CASE WHEN age_days < 7 THEN '0-6d' WHEN age_days < 30 THEN '7-29d'
            WHEN age_days < 37 THEN '30-36d' WHEN age_days < 90 THEN '37-89d'
            WHEN age_days < 180 THEN '90-179d' ELSE '180d+' END AS age_bucket,
       count(*) AS owners,
       count(*) FILTER (WHERE has_sc) AS with_scenarios,
       count(*) FILTER (WHERE protected) AS protected,
       count(*) FILTER (WHERE NOT protected AND has_sc
                          AND lifecycle_anchor < now() - interval '30 days'
                          AND last_seen >= now() - interval '7 days') AS abandoned_by_rule_but_seen_7d,
       NULL::numeric AS oldest_age_days
FROM o GROUP BY 1
UNION ALL
SELECT 'ALL', count(*), count(*) FILTER (WHERE has_sc), count(*) FILTER (WHERE protected),
       count(*) FILTER (WHERE NOT protected AND has_sc
                          AND lifecycle_anchor < now() - interval '30 days'
                          AND last_seen >= now() - interval '7 days'),
       round(max(age_days)::numeric, 1)
FROM o
ORDER BY 1;


-- ============================================================
-- Q8. cleanup 是否已經刪過東西（cron 每日紀錄，最近 30 天）
-- 回傳：每天一列——hard delete 的 owner 數、連帶刪掉的列數
-- 沒有任何列＝cron 沒跑過或 metrics 沒寫入
-- ============================================================
SELECT bucket AS day, sum(count) AS owners_hard_deleted, sum(total) AS rows_deleted
FROM operational_metrics
WHERE metric = 'abandoned_owner_cleanup_count'
GROUP BY bucket
ORDER BY bucket;
