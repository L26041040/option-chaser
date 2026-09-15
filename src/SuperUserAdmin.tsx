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
  superuserBatchDeleteOwners,
  superuserDeleteOwner,
  superuserGetAuditLog,
  superuserGetOwnerScenario,
  superuserListOwners,
  superuserListOwnerScenarios,
  superuserSetOwnerProtected,
  type ScenarioDetail,
  type ScenarioSummary,
  type SuperUserAuditEntry,
  type SuperUserOwnerInfo,
} from "./api";
import { formatArchivedAt, formatReturn } from "./scenarios";

type ConfirmTarget =
  | { kind: "delete-one"; ownerId: string }
  | { kind: "delete-batch"; ownerIds: string[] };

function ConfirmHighRiskAction({
  target,
  busy,
  onCancel,
  onConfirm,
}: {
  target: ConfirmTarget;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
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
        <div className="confirm-actions">
          <button className="text-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="batch-pill danger" onClick={onConfirm} disabled={busy}>
            {busy ? "刪除中……" : "永久刪除"}
          </button>
        </div>
      </div>
    </div>
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

  async function confirmDelete() {
    if (!confirmTarget) return;
    setBusy(true);
    try {
      if (confirmTarget.kind === "delete-one") {
        await superuserDeleteOwner(confirmTarget.ownerId, confirmTarget.ownerId);
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

  return (
    <section className="card settings-section" aria-label="Super User 管理面板">
      <h2 className="section-title">Super User 管理面板</h2>
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
          <ul className="superuser-owner-list">
            {owners.map((owner) => (
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
          onConfirm={() => void confirmDelete()}
        />
      )}
    </section>
  );
}
