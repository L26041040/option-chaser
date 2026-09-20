/**
 * Super User 系統／管理操作面板（PB-10／#301，Anonymous Public Beta）。
 *
 * 正式落地 SUPERUSER-007 對舊 OD-6 的 supersede：Super User 是 Normal
 * User 完整權限超集合——這裡讓它能查看其他 owner 的資料、刪除他人資料
 * （含批次）、runtime 設定／取消 `protected` lifecycle 旗標。
 *
 * **刻意不做豪華 Dashboard**（票面 §5 Non-goals）：單一可捲動表格＋
 * 就地展開的劇本清單／劇本內容＋二次確認 modal，沒有圖表、沒有分頁、
 * 沒有搜尋。高風險操作（刪除、批次刪除、變更 protected）一律經過
 * `ConfirmHighRiskAction`（比照 `TrashView.tsx` 既有的 `ConfirmDeleteOne`／
 * `ConfirmDeleteBatch` modal 慣例）——**前端這層 modal 只是 UX**，真正
 * 的護欄是伺服器端逐字比對 `confirm_owner_id`（見 `api.ts` 的
 * `superuserDeleteOwner()`／`superuserSetOwnerProtected()`）。
 *
 * 只在 `Settings.tsx` 判定 `isSuperUser` 為真時掛載；掛載時立刻讀一次
 * owner 清單，不必額外按鈕觸發。
 */
import { useEffect, useState } from "react";

import {
  getOpsMetrics,
  superuserBatchDeleteOwners,
  superuserDeleteOwner,
  superuserGetAuditLog,
  superuserGetOwnerScenario,
  superuserListOwners,
  superuserListOwnerScenarios,
  superuserSetOwnerProtected,
  type OpsMetricBucket,
  type OpsMetrics,
  type ScenarioDetail,
  type ScenarioSummary,
  type SuperUserAuditEntry,
  type SuperUserOwnerInfo,
} from "./api";
import { formatArchivedAt, formatReturn } from "./scenarios";

type ConfirmTarget =
  | { kind: "delete-one"; ownerId: string }
  | { kind: "delete-batch"; ownerIds: string[] };

/** 這個高風險操作要求使用者打對什麼才能啟用確認鈕——單筆是目標
 *  owner id 本身（伺服器端真正比對的那個值，見 `api.ts::
 *  superuserDeleteOwner()` docstring）；批次是「刪除 N 個」這句話
 *  （N＝這次要刪的數量）。**批次這句話本身不送到伺服器**——伺服器
 *  端 `confirm_owner_ids` 比對的仍是 owner id 集合本身（既有測試
 *  零改動，見 `main.py::superuser_batch_delete_owners()`），這句話
 *  純粹是前端多一道「使用者真的看清楚要刪幾個」的門檻。 */
function requiredConfirmPhrase(target: ConfirmTarget): string {
  return target.kind === "delete-one"
    ? target.ownerId
    : `刪除 ${target.ownerIds.length} 個`;
}

/**
 * 高風險操作二次確認（OG-11／#322 跟進：從純按鈕確認換成 type-to-
 * confirm）——單筆要求打對目標 owner id，批次要求打對「刪除 N 個」
 * 字樣，打對才點得下確認鈕。**這只是前端 UX**，伺服器端既有
 * `confirm_owner_id`／`confirm_owner_ids` 逐字比對照舊是唯一防線
 * （票面明文）；`onConfirm` 把使用者實際打的那一串原樣交給呼叫端，
 * 不由這裡預填或替換成別的值（票面：「modal 送出的 confirm 值就是
 * 使用者輸入的那一串」）。
 */
function ConfirmHighRiskAction({
  target,
  busy,
  onCancel,
  onConfirm,
}: {
  target: ConfirmTarget;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (typedConfirm: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const required = requiredConfirmPhrase(target);
  const canConfirm = typed === required;
  const heading =
    target.kind === "delete-one"
      ? `永久刪除 owner ${target.ownerId} 的全部資料？`
      : `永久刪除 ${target.ownerIds.length} 個 owner 的全部資料？`;
  return (
    <div className="confirm-overlay">
      <div
        className="confirm-sheet"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="superuser-confirm-heading"
      >
        <h2 id="superuser-confirm-heading">{heading}</h2>
        <p>無法復原——該 owner 名下的全部劇本、分析歷史、報價快照、
          設定與 credential 會一併刪除。</p>
        {target.kind === "delete-batch" && (
          <ul className="confirm-list">
            {target.ownerIds.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        )}
        <label className="settings-field">
          <span className="caption">
            {target.kind === "delete-one"
              ? "請輸入目標 owner id 以確認："
              : `請輸入「${required}」以確認：`}
          </span>
          <input
            className="settings-input"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={required}
            aria-label="輸入以確認"
          />
        </label>
        <div className="confirm-actions">
          <button className="text-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            className="batch-pill danger"
            onClick={() => onConfirm(typed)}
            disabled={busy || !canConfirm}
          >
            {busy ? "刪除中……" : "永久刪除"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** owner 清單的前端純過濾（OG-11／#322，AC：「owners 表篩選純前端」）
 *  ——`protected`／`is_synthetic` 都是既有欄位（後者本票才第一次
 *  宣告型別，見 `api.ts::SuperUserOwnerInfo`），不打任何新請求。
 *  票面原話還提到「lifecycle 狀態」篩選，但 owner 清單端點沒有回傳
 *  這個欄位——真正的分類邏輯（`anonymous_lifecycle.classify()`）依賴
 *  可被環境變數覆寫的門檻天數，前端沒有管道知道目前生效值，重寫一份
 *  只會做出可能跟後端清理排程對不上的假分類（違反「不重寫可能漂移
 *  的複本」既有原則，`_anonymous_owner_distribution()` docstring
 *  自己也是這樣說的）。這裡只篩前端誠實掌握、逐字符合後端真相的兩個
 *  欄位；彙整後的 active／abandoned／待清理人數已經在上面的系統指標
 *  區塊顯示（`anonymous_owners`），沒有漏掉這個資訊，只是不做成
 *  「看起來像逐列都算得出來」的假象。 */
type OwnerFilter = "all" | "protected" | "synthetic";

const OWNER_FILTER_OPTIONS: { value: OwnerFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "protected", label: "Protected" },
  { value: "synthetic", label: "Synthetic" },
];

function filterOwners(
  owners: SuperUserOwnerInfo[], filter: OwnerFilter,
): SuperUserOwnerInfo[] {
  if (filter === "protected") return owners.filter((o) => o.protected);
  if (filter === "synthetic") return owners.filter((o) => o.is_synthetic);
  return owners;
}

/** 桶狀指標（`OpsMetricBucket[]`）加總——`count` 是次數本身；桌面
 *  stats 方塊只顯示「累計次數」，不逐 bucket／source／symbol 攤開
 *  （票面既有裁示：刻意不做豪華 Dashboard，沒有圖表）。 */
function sumMetricCount(buckets: OpsMetricBucket[]): number {
  return buckets.reduce((sum, b) => sum + b.count, 0);
}

/** 刷新耗時的平均值（ms）——`total` 是耗時毫秒總和，`count` 是次數，
 *  一次除法就是平均，不是新的計算規則，跟後端註解「count／total／
 *  max_value 供算平均與量級」逐字對應。一次都沒發生過時顯示「—」。 */
function avgRefreshDurationMs(buckets: OpsMetricBucket[]): number | null {
  const count = sumMetricCount(buckets);
  if (count === 0) return null;
  const total = buckets.reduce((sum, b) => sum + b.total, 0);
  return total / count;
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{children}</span>
    </div>
  );
}

/** 系統指標方塊（OG-11／#322，AC：「stats 讀既有 ops metrics 端點且
 *  只顯示聚合數字」）——`getOpsMetrics()` 是既有 `GET /api/ops/
 *  metrics` 端點（S0／SCALE-08 起就在）的前端 client，本票才第一次
 *  包。這個元件只在 `SuperUserAdmin` 掛載時才 mount（外層已經 gate 在
 *  `role === superadmin`），非 Super Admin 不會發出這個請求。 */
function OpsStats() {
  const [metrics, setMetrics] = useState<OpsMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getOpsMetrics()
      .then((m) => alive && setMetrics(m))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => { alive = false; };
  }, []);

  if (error) {
    return (
      <p className="notice error" role="alert">{error}</p>
    );
  }
  if (!metrics) {
    return <p className="caption">系統指標載入中……</p>;
  }

  const avgRefresh = avgRefreshDurationMs(metrics.refresh_duration_ms);
  const triggeredAlerts = metrics.alerts.filter((a) => a.triggered);

  return (
    <section className="card settings-section" aria-label="系統指標">
      <h3 className="settings-usage-title">系統指標</h3>
      <div className="summary-grid">
        <Stat label="Chain Fetch（累計）">
          {sumMetricCount(metrics.chain_fetch_count)}
        </Stat>
        <Stat label="429 限流（累計）">
          {sumMetricCount(metrics.chain_429_count)}
        </Stat>
        <Stat label="陳舊備援（累計）">
          {sumMetricCount(metrics.stale_serve_count)}
        </Stat>
        <Stat label="Cold Miss（累計）">
          {sumMetricCount(metrics.cold_miss_count)}
        </Stat>
        <Stat label="刷新耗時（平均）">
          {avgRefresh === null ? "—" : `${Math.round(avgRefresh)} ms`}
        </Stat>
        <Stat label="History 讀取量（累計）">
          {sumMetricCount(metrics.history_read_volume)}
        </Stat>
        <Stat label="Results 資料表">
          {(metrics.table_size.results?.row_count ?? "—")} 列
        </Stat>
        <Stat label="Snapshots 資料表">
          {(metrics.table_size.snapshots?.row_count ?? "—")} 列
        </Stat>
        <Stat label="匿名 Owner：Active">{metrics.anonymous_owners.active}</Stat>
        <Stat label="匿名 Owner：Abandoned">{metrics.anonymous_owners.abandoned}</Stat>
        <Stat label="匿名 Owner：待清理">
          {metrics.anonymous_owners.eligible_for_hard_delete}
        </Stat>
        <Stat label="Protected Owner">{metrics.anonymous_owners.protected}</Stat>
        <Stat label="劇本總數">{metrics.scenarios.total}</Stat>
        <Stat label="平均每人劇本數">
          {metrics.scenarios.average_per_owner.toFixed(1)}
        </Stat>
        <Stat label="清理排程（累計）">
          {sumMetricCount(metrics.abandoned_owner_cleanup_count)}
        </Stat>
      </div>
      {triggeredAlerts.length > 0 && (
        <ul className="notice warn">
          {triggeredAlerts.map((a) => <li key={a.key}>{a.message}</li>)}
        </ul>
      )}
    </section>
  );
}

export default function SuperUserAdmin() {
  const [owners, setOwners] = useState<SuperUserOwnerInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedOwner, setExpandedOwner] = useState<string | null>(null);
  const [scenariosByOwner, setScenariosByOwner] = useState<
    Record<string, ScenarioSummary[]>
  >({});
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);
  const [detailByScenario, setDetailByScenario] = useState<
    Record<string, ScenarioDetail>
  >({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [audit, setAudit] = useState<SuperUserAuditEntry[] | null>(null);
  // OG-11（#322）：owners 表狀態篩選，純前端過濾，不打任何新請求
  // （見 `filterOwners()` docstring：為什麼只有這兩個篩選值）。
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>("all");

  async function load() {
    try {
      const rows = await superuserListOwners();
      setOwners(rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleScenarios(ownerId: string) {
    if (expandedOwner === ownerId) {
      setExpandedOwner(null);
      return;
    }
    setExpandedOwner(ownerId);
    if (!scenariosByOwner[ownerId]) {
      try {
        const rows = await superuserListOwnerScenarios(ownerId);
        setScenariosByOwner((prev) => ({ ...prev, [ownerId]: rows }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function toggleDetail(ownerId: string, scenarioId: string) {
    if (expandedScenario === scenarioId) {
      setExpandedScenario(null);
      return;
    }
    setExpandedScenario(scenarioId);
    if (!detailByScenario[scenarioId]) {
      try {
        const detail = await superuserGetOwnerScenario(ownerId, scenarioId);
        setDetailByScenario((prev) => ({ ...prev, [scenarioId]: detail }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function toggleProtected(ownerId: string, next: boolean) {
    setBusy(true);
    try {
      await superuserSetOwnerProtected(ownerId, next);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(ownerId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ownerId)) next.delete(ownerId);
      else next.add(ownerId);
      return next;
    });
  }

  /** `typedConfirm`：使用者在 `ConfirmHighRiskAction` 裡實際打的那一串
   *  （單筆＝目標 owner id、批次＝「刪除 N 個」字樣）。單筆直接原樣
   *  交給 `superuserDeleteOwner()` 當伺服器端真正比對的 `confirm_
   *  owner_id`——不再像舊版那樣由這裡自動代填 `ownerId`，票面明文
   *  「送出的 confirm 值就是使用者輸入的那一串」。批次維持既有語意
   *  不變：伺服器端 `confirm_owner_ids` 比對的是 owner id 集合本身
   *  （`superuserBatchDeleteOwners()` 內部仍自動帶 `ownerIds`），
   *  `typedConfirm`（那句「刪除 N 個」）只在 `ConfirmHighRiskAction`
   *  自己判斷要不要讓確認鈕可按，不送到伺服器、也不影響這裡的呼叫。 */
  async function confirmDelete(typedConfirm: string) {
    if (!confirmTarget) return;
    setBusy(true);
    try {
      if (confirmTarget.kind === "delete-one") {
        await superuserDeleteOwner(confirmTarget.ownerId, typedConfirm);
      } else {
        await superuserBatchDeleteOwners(confirmTarget.ownerIds);
      }
      setConfirmTarget(null);
      setSelected(new Set());
      setExpandedOwner(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleAudit() {
    if (!auditOpen) {
      try {
        setAudit(await superuserGetAuditLog());
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
    setAuditOpen((v) => !v);
  }

  const shownOwners = owners ? filterOwners(owners, ownerFilter) : [];

  return (
    <section className="card settings-section" aria-label="Super User 管理面板">
      <h2 className="section-title">Super User 管理面板</h2>
      <OpsStats />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {owners === null ? (
        <p className="caption">載入中……</p>
      ) : owners.length === 0 ? (
        <p className="caption">目前沒有任何 owner。</p>
      ) : (
        <>
          <div className="seg" role="group" aria-label="依狀態篩選 owner">
            {OWNER_FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={ownerFilter === opt.value ? "on" : ""}
                onClick={() => setOwnerFilter(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {selected.size > 0 && (
            <div className="batch-action-bar">
              <span className="caption">已選 {selected.size} 個 owner</span>
              <button
                className="batch-pill danger"
                onClick={() =>
                  setConfirmTarget({
                    kind: "delete-batch",
                    ownerIds: Array.from(selected),
                  })
                }
              >
                永久刪除已選
              </button>
            </div>
          )}
          {shownOwners.length === 0 ? (
            <p className="caption">沒有符合篩選條件的 owner。</p>
          ) : (
          <ul className="superuser-owner-list">
            {shownOwners.map((owner) => (
              <li key={owner.owner_id} className="superuser-owner-row">
                <div className="superuser-owner-head">
                  <input
                    type="checkbox"
                    aria-label={`選取 owner ${owner.owner_id}`}
                    checked={selected.has(owner.owner_id)}
                    onChange={() => toggleSelect(owner.owner_id)}
                  />
                  <code className="superuser-owner-id">{owner.owner_id}</code>
                  {owner.protected && <span className="tag">protected</span>}
                  {owner.is_synthetic && <span className="tag">synthetic</span>}
                </div>
                <p className="caption">
                  建立於 {formatArchivedAt(owner.created_at)}
                  {owner.last_activity_at
                    ? `・最近活動 ${formatArchivedAt(owner.last_activity_at)}`
                    : "・尚無記錄的活動"}
                </p>
                <div className="settings-actions">
                  <button
                    className="text-button"
                    onClick={() => void toggleScenarios(owner.owner_id)}
                  >
                    {expandedOwner === owner.owner_id ? "收合劇本" : "查看劇本"}
                  </button>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void toggleProtected(owner.owner_id, !owner.protected)
                    }
                  >
                    {owner.protected ? "取消 protected" : "設為 protected"}
                  </button>
                  <button
                    className="text-button danger"
                    onClick={() =>
                      setConfirmTarget({ kind: "delete-one", ownerId: owner.owner_id })
                    }
                  >
                    永久刪除全部資料
                  </button>
                </div>
                {expandedOwner === owner.owner_id && (
                  <ul className="superuser-scenario-list">
                    {(scenariosByOwner[owner.owner_id] ?? []).length === 0 ? (
                      <li className="caption">這個 owner 沒有任何劇本。</li>
                    ) : (
                      (scenariosByOwner[owner.owner_id] ?? []).map((row) => (
                        <li key={row.id}>
                          <button
                            className="text-button"
                            onClick={() => void toggleDetail(owner.owner_id, row.id)}
                          >
                            {row.symbol} · {row.target_month}
                            {row.best_return !== null &&
                              `（${formatReturn(row.best_return)}）`}
                          </button>
                          {expandedScenario === row.id && detailByScenario[row.id] && (
                            <pre className="superuser-scenario-detail">
                              {JSON.stringify(detailByScenario[row.id], null, 2)}
                            </pre>
                          )}
                        </li>
                      ))
                    )}
                  </ul>
                )}
              </li>
            ))}
          </ul>
          )}
        </>
      )}
      <div className="settings-actions">
        <button className="text-button" onClick={() => void toggleAudit()}>
          {auditOpen ? "收合 audit trail" : "查看 audit trail"}
        </button>
      </div>
      {auditOpen && (
        <ul className="superuser-audit-list">
          {(audit ?? []).length === 0 ? (
            <li className="caption">目前沒有任何高風險操作紀錄。</li>
          ) : (
            (audit ?? []).map((e) => (
              <li key={e.event_id} className="caption">
                {formatArchivedAt(e.ts)}・{e.actor}・{e.action}
                {e.target_owner_id && `・目標 ${e.target_owner_id}`}
              </li>
            ))
          )}
        </ul>
      )}
      {confirmTarget && (
        <ConfirmHighRiskAction
          target={confirmTarget}
          busy={busy}
          onCancel={() => setConfirmTarget(null)}
          onConfirm={(typed) => void confirmDelete(typed)}
        />
      )}
    </section>
  );
}
