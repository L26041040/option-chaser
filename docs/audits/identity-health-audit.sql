-- Identity health audit（唯讀）— OPTION-CHASER-IDENTITY-RELIABILITY-IMPROVEMENT-001 / #367
--
-- 用法：在 Neon console（或 psql）對 Production 執行；全部是 SELECT，不改任何資料。
-- 回填到 #367 時只貼計數與 owner_id 前 6 碼 hint，不得貼任何 token、完整 owner_id。
-- 比照 docs/audits/db-lifecycle-production-audit.sql 的格式：每題一段、標題即問題。

-- Q1 owners 總數；protected／特權（role != normal）／主帳號各幾個
SELECT
  count(*)                                               AS owners_total,
  count(*) FILTER (WHERE protected)                      AS owners_protected,
  count(*) FILTER (WHERE role <> 'normal')               AS owners_privileged,
  (SELECT count(*) FROM main_account)                    AS main_account_rows,
  (SELECT left(main_owner_id, 6) FROM main_account WHERE id = 1) AS main_owner_hint
FROM owners;

-- Q2 孤兒 owner：有資料（劇本／設定／credential）但零顆憑證——歷史上「身分遺失後再也存取不到」的資料
SELECT count(*) AS orphan_owners_with_data,
       coalesce(sum(n_scenarios), 0) AS orphan_scenarios
FROM (
  SELECT o.owner_id,
         (SELECT count(*) FROM scenarios s WHERE s.owner_id = o.owner_id) AS n_scenarios
  FROM owners o
  WHERE NOT EXISTS (SELECT 1 FROM browser_identities bi WHERE bi.owner_id = o.owner_id)
    AND (EXISTS (SELECT 1 FROM scenarios s WHERE s.owner_id = o.owner_id)
      OR EXISTS (SELECT 1 FROM owner_settings st WHERE st.owner_id = o.owner_id)
      OR EXISTS (SELECT 1 FROM owner_credentials c WHERE c.owner_id = o.owner_id))
) t;

-- Q3 每個 Normal owner 的憑證顆數分佈（Normal 正常應恰為 1；>1 代表曾分裂後收斂、或 bug）
SELECT n_identities, count(*) AS owners
FROM (
  SELECT o.owner_id, count(bi.token) AS n_identities
  FROM owners o LEFT JOIN browser_identities bi ON bi.owner_id = o.owner_id
  WHERE o.role = 'normal' AND NOT o.protected
  GROUP BY o.owner_id
) t
GROUP BY n_identities ORDER BY n_identities;

-- Q4 還沒升級成固定期限 cookie 的舊憑證列（IDENTITY-FIX-002 之前簽的）
SELECT count(*) AS identities_without_cookie_issued_at
FROM browser_identities WHERE cookie_issued_at IS NULL;

-- Q5 活躍分佈：最近 7／30／90／180 天各有幾個 Normal owner 有任何憑證回訪
-- （last_seen_at 是 UTC 的 ISO 字串，字典序即時間序；比較基準也固定用 UTC，
--  不依賴 session 的 TimeZone 設定）
WITH last_seen AS (
  SELECT o.owner_id, max(bi.last_seen_at) AS seen
  FROM owners o JOIN browser_identities bi ON bi.owner_id = o.owner_id
  WHERE o.role = 'normal' AND NOT o.protected
  GROUP BY o.owner_id
)
SELECT
  count(*) FILTER (WHERE seen >= to_char((now() AT TIME ZONE 'UTC') - interval '7 days',   'YYYY-MM-DD"T"HH24:MI:SS')) AS active_7d,
  count(*) FILTER (WHERE seen >= to_char((now() AT TIME ZONE 'UTC') - interval '30 days',  'YYYY-MM-DD"T"HH24:MI:SS')) AS active_30d,
  count(*) FILTER (WHERE seen >= to_char((now() AT TIME ZONE 'UTC') - interval '90 days',  'YYYY-MM-DD"T"HH24:MI:SS')) AS active_90d,
  count(*) FILTER (WHERE seen >= to_char((now() AT TIME ZONE 'UTC') - interval '180 days', 'YYYY-MM-DD"T"HH24:MI:SS')) AS active_180d
FROM last_seen;

-- Q6 無主劇本：scenarios.owner_id 在 owners 裡沒有對應列（db-hygiene 不變量，預期 0）
SELECT count(*) AS ownerless_scenarios,
       count(DISTINCT owner_id) AS ownerless_owner_ids
FROM scenarios s
WHERE s.owner_id IS NULL OR NOT EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = s.owner_id);

-- Q7（IRI-04 之後）身分墓碑：各原因幾顆、最舊一顆多久以前
SELECT reason, count(*) AS tombstones, min(deleted_at) AS oldest
FROM identity_tombstones GROUP BY reason ORDER BY tombstones DESC;
