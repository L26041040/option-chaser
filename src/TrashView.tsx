/**
 * 垃圾桶畫面（TR6／#91 起步；TR4／#92 補上單筆還原與永久刪除；
 * TR5／#93 補上批次操作）。
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

import { listArchivedScenarios, type ScenarioSummary } from "./api";
import { formatArchivedAt, formatReturn, money } from "./scenarios";

export default function TrashView() {
  const [rows, setRows] = useState<ScenarioSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          {rows.map((row) => (
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
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
