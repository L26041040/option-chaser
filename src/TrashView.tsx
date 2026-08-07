/**
 * 垃圾桶畫面（TR6／#91 起步：唯讀清單＋入口；TR4／#92 補上單筆還原與
 * 永久刪除；TR5／#93 補上批次操作）。
 *
 * 手機／桌面共用同一個元件、同一份標記——差別只在誰把它放在哪裡：
 * 手機整頁替換（`App.tsx` 的 `!isDesktop && showTrash` 分支），桌面
 * 替換左側 `library-pane` 的內容、右側 `detail-pane` 維持既有邏輯
 * 不動（需求方核准版面 D2：左側面板整個切換，不是彈出新視窗）。
 *
 * 列表本身用既有 `GET /api/scenarios?include_archived=true` 篩出已
 * 封存者（`api.ts` 的 `listArchivedScenarios()`），不新增後端端點。
 */
import { useEffect, useState } from "react";

import {
  deleteScenario,
  listArchivedScenarios,
  restoreScenario,
  type ScenarioSummary,
} from "./api";
import { formatArchivedAt, formatReturn, money } from "./scenarios";

/**
 * 永久刪除二次確認畫面（TR4／#92）：單筆時明確列出該劇本的 ticker＋
 * target month（例如「永久刪除 TLT · 2028-05？」），不是複數句型——
 * 批量版本（TR5）另外走複數清單＋總數的措辭，不共用這個元件。
 */
function ConfirmDeleteOne({
  row,
  busy,
  onCancel,
  onConfirm,
}: {
  row: ScenarioSummary;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="confirm-overlay">
      <div className="confirm-sheet" role="alertdialog" aria-modal="true"
           aria-labelledby="confirm-delete-heading">
        <h2 id="confirm-delete-heading">
          永久刪除 {row.symbol} · {row.target_month}？
        </h2>
        <p>此動作無法復原，將一併刪除這個劇本的分析歷史與原始報價快照。</p>
        <div className="confirm-actions">
          <button className="text-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="batch-pill" onClick={onConfirm} disabled={busy}>
            {busy ? "刪除中……" : "永久刪除"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function TrashView({
  onRestore,
}: {
  /** TR4（#92）：還原成功時把這個劇本交回 `App.tsx`，重新出現在主清單
   *  ——`TrashView` 自己的清單狀態獨立於 `App` 的 `rows`，還原不會
   *  自動同步，得靠這個回呼把資料交回去（沿用回傳值本身就是那一列
   *  完整資料的既有慣例，不必為此另打一次清單查詢）。 */
  onRestore: (row: ScenarioSummary) => void;
}) {
  const [rows, setRows] = useState<ScenarioSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listArchivedScenarios()
      .then((r) => { if (!cancelled) setRows(r); })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => { cancelled = true; };
  }, []);

  async function restore(row: ScenarioSummary) {
    setBusyId(row.id);
    setError(null);
    try {
      await restoreScenario(row.id);
      setRows((prev) => (prev ?? []).filter((r) => r.id !== row.id));
      onRestore(row);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function confirmDelete(row: ScenarioSummary) {
    setBusyId(row.id);
    setError(null);
    try {
      await deleteScenario(row.id);
      setRows((prev) => (prev ?? []).filter((r) => r.id !== row.id));
      setConfirmDeleteId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  const toDelete = rows?.find((r) => r.id === confirmDeleteId) ?? null;

  return (
    <div className="screen">
      <div className="toolbar" style={{ paddingBottom: 0 }}>
        <div className="toolbar-row">
          <a className="nav-back" href="#/">‹ 劇本庫</a>
        </div>
        <div className="toolbar-row">
          <h1 className="toolbar-title">垃圾桶</h1>
        </div>
        <span className="caption">
          封存於此的劇本不會再刷新報價，可還原或永久刪除。
          {rows !== null && `${rows.length} 個劇本`}
        </span>
      </div>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <p className="caption">垃圾桶是空的。</p>
      )}

      {rows !== null && rows.length > 0 && (
        <ul className="list">
          {rows.map((row) => {
            const who = `${row.symbol} ${row.target_month}`;
            const busy = busyId === row.id;
            return (
              <li key={row.id} className="card">
                <div className="row">
                  <span className="row-value big">{row.symbol}</span>
                  <span className="tag">垃圾桶</span>
                </div>
                <div className="row">
                  <span className="row-label">目標</span>
                  <span className="row-value">
                    {money(row.target_price)}　{row.target_month}
                  </span>
                </div>
                <div className="row">
                  <span className="row-label">封存於</span>
                  <span className="row-value">
                    {formatArchivedAt(row.archived_at!)}
                  </span>
                </div>
                <div className="row">
                  <span className="row-label">最後收益率</span>
                  <span className="row-value">{formatReturn(row.best_return)}</span>
                </div>
                <div className="card-actions trash-row-actions">
                  <button
                    className="text-button"
                    onClick={() => void restore(row)}
                    disabled={busy}
                    aria-label={`還原 ${who}`}
                  >
                    還原
                  </button>
                  <button
                    className="text-button danger"
                    onClick={() => setConfirmDeleteId(row.id)}
                    disabled={busy}
                    aria-label={`永久刪除 ${who}`}
                  >
                    永久刪除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {toDelete && (
        <ConfirmDeleteOne
          row={toDelete}
          busy={busyId === toDelete.id}
          onCancel={() => setConfirmDeleteId(null)}
          onConfirm={() => void confirmDelete(toDelete)}
        />
      )}
    </div>
  );
}
