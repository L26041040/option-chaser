/**
 * 垃圾桶畫面（TR6／#91 起步：唯讀清單＋入口；TR4／#92 補上單筆還原與
 * 永久刪除；TR5／#93 補上批次操作）。
 *
 * 手機／桌面共用同一個元件、同一份標記——差別只在誰把它放在哪裡：
 * 手機整頁替換（`App.tsx` 的 `!isDesktop && showTrash` 分支）；桌面
 * （OG-02／#318 起）同樣是整頁替換，跟劇本庫／詳細頁／設定共用同一個
 * 全寬頁面容器（`.page`），不再是「左側面板整個切換、右側維持不動」
 * 的側欄語意（需求方核准版面 D2 的精神——整塊切換、不是彈出新視窗
 * ——在頁面級導覽下依然成立，只是「整塊」現在是整個頁面）。
 *
 * 列表本身用既有 `GET /api/scenarios?include_archived=true` 篩出已
 * 封存者（`api.ts` 的 `listArchivedScenarios()`），不新增後端端點。
 *
 * TR5（#93）：這個畫面本身就是「管理垃圾桶」的畫面，不像主清單
 * （`ScenarioList.tsx`／`CompactScenarioList.tsx`）預設是瀏覽模式、
 * 得先點圖示才進批次選取——這裡每列的 checkbox 與單筆「還原」「永久
 * 刪除」鈕本來就同時存在，不必切換模式：反正這個畫面裡的列本來就沒有
 * 「點下去進詳細頁」這件事，checkbox 不會跟其他手勢搶戲。
 *
 * OG-ALL-001 跟進 OG-03（#320）：桌面版清單改成 Markets 式全寬資料表
 * 後，票面「垃圾桶頁同款表格換皮」這條 AC 原本漏做（`/code-review`
 * Spec 軸抓到）——這裡補上，但這個元件本來就是手機／桌面共用同一份
 * 標記（見上），不能像 `ScenarioList.tsx`／`CompactScenarioList.tsx`
 * 那樣「兩個檔案本來就分開、互不影響」，所以改用既有的
 * `useIsDesktop()`（`IvTrend.tsx` 等處已在用的同一個斷點判斷）在渲染
 * 層直接分流：`isDesktop` 時走新的 `TrashRowTable`（沿用
 * `ScenarioList.tsx` 已建立的 `.lib-table`／`.lib-thead`／`.lib-cell`
 * primitives，欄位為 checkbox／標的／目標／封存於／最後收益率／
 * 操作——跟主清單不同，沒有方向／冠軍策略／劇本報酬這些只有「還活著」
 * 的劇本才有意義的欄位）；`!isDesktop` 時維持 `TrashRowCard`，跟改版
 * 前逐位元組相同的卡片標記，確保手機版零改動（`e2e/smoke.spec.ts`
 * 既有垃圾桶測試把關）。兩者共用同一組 state／還原／刪除／批次函式，
 * 只有「怎麼畫一列」這件事分成兩份；二次確認 modal
 * （`ConfirmDeleteOne`／`ConfirmDeleteBatch`）與批次動作列在兩個平台
 * 逐字共用，不重複。
 */
import { useEffect, useState } from "react";

import {
  deleteScenario,
  listArchivedScenarios,
  restoreScenario,
  type ScenarioSummary,
} from "./api";
import { CheckIcon } from "./icons";
import { formatArchivedAt, formatReturn, money } from "./scenarios";
import StockLogo from "./StockLogo";
import { useIsDesktop } from "./useIsDesktop";

/**
 * 永久刪除二次確認畫面：單筆時明確列出該劇本的 ticker＋target month
 * （例如「永久刪除 TLT · 2028-05？」），不是複數句型。
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
        <p>無法復原，這個劇本的分析歷史與報價快照會一併刪除。</p>
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

/**
 * 批量永久刪除二次確認（TR5／#93）：列出全部待刪劇本＋數量，跟單筆
 * 版本刻意用不同措辭（票上明文要求：批量時列出所有待刪劇本／數量，
 * 不是單筆句型的複數化）。
 */
function ConfirmDeleteBatch({
  rows,
  busy,
  onCancel,
  onConfirm,
}: {
  rows: ScenarioSummary[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="confirm-overlay">
      <div className="confirm-sheet" role="alertdialog" aria-modal="true"
           aria-labelledby="confirm-batch-delete-heading">
        <h2 id="confirm-batch-delete-heading">
          永久刪除 {rows.length} 個劇本？
        </h2>
        <p>無法復原，這些劇本的分析歷史與報價快照會一併刪除。</p>
        <ul className="confirm-list">
          {rows.map((row) => (
            <li key={row.id}>{row.symbol} · {row.target_month}</li>
          ))}
        </ul>
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

interface TrashRowProps {
  row: ScenarioSummary;
  busy: boolean;
  checked: boolean;
  onToggleSelected: (id: string) => void;
  onRestore: (row: ScenarioSummary) => void;
  onRequestDelete: (id: string) => void;
}

/** 手機版列——跟 OG-ALL-001 之前逐位元組相同的卡片標記，確保手機版
 *  零改動（見檔頭說明）。 */
function TrashRowCard({
  row, busy, checked, onToggleSelected, onRestore, onRequestDelete,
}: TrashRowProps) {
  const who = `${row.symbol} ${row.target_month}`;
  return (
    <li className="card">
      <div className="row">
        <span className="symbol-group">
          <button
            type="button"
            className={checked ? "row-checkbox checked" : "row-checkbox"}
            onClick={() => onToggleSelected(row.id)}
            aria-pressed={checked}
            aria-label={`選取 ${who}`}
          >
            {checked && <CheckIcon />}
          </button>
          <span className="row-value big">{row.symbol}</span>
        </span>
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
          onClick={() => void onRestore(row)}
          disabled={busy}
          aria-label={`還原 ${who}`}
        >
          還原
        </button>
        <button
          className="text-button danger"
          onClick={() => onRequestDelete(row.id)}
          disabled={busy}
          aria-label={`永久刪除 ${who}`}
        >
          永久刪除
        </button>
      </div>
    </li>
  );
}

/** 桌面版頭列——純顯示、`aria-hidden`，與 `ScenarioList.tsx` 的
 *  `LibTableHead()` 同一種既有慣例（欄位標籤不是操作）。 */
function TrashTableHead() {
  return (
    <div className="lib-thead trash-row-grid" aria-hidden="true">
      <span className="lib-cell lib-cell-check" />
      <span className="lib-cell">標的</span>
      <span className="lib-cell r">目標</span>
      <span className="lib-cell">封存於</span>
      <span className="lib-cell r">最後收益率</span>
      <span className="lib-cell">操作</span>
    </div>
  );
}

/**
 * 桌面版列（OG-ALL-001 跟進 OG-03／#320）：沿用 `ScenarioList.tsx`
 * 已建立的 `.lib-cell` 系表格 primitives，欄位組成見檔頭說明。這個
 * 畫面裡的列從來就不是導覽入口（見檔頭），因此不套用主清單那組鎖定
 * `<a>` 的 `.compact-card-tap.lib-row-tap` 複合選擇器，改用專屬的
 * `.trash-row`／`.trash-row-grid`（見 `styles.css`）。
 */
function TrashRowTable({
  row, busy, checked, onToggleSelected, onRestore, onRequestDelete,
}: TrashRowProps) {
  const who = `${row.symbol} ${row.target_month}`;
  return (
    <li className="trash-row trash-row-grid">
      <span className="lib-cell lib-cell-check">
        <button
          type="button"
          className={checked ? "row-checkbox checked" : "row-checkbox"}
          onClick={() => onToggleSelected(row.id)}
          aria-pressed={checked}
          aria-label={`選取 ${who}`}
        >
          {checked && <CheckIcon />}
        </button>
      </span>

      {/* 標的：跟主清單一樣真實品牌 Logo，找不到就整個消失
          （UI-IMPL-002／#092，Logo.dev `fallback=404` 契約——「同款
          表格換皮」既然連 Logo 24px 都是主表格的視覺語言之一，這裡
          不該另外長出一份「只有文字」的特例）。 */}
      <span className="lib-cell lib-cell-symbol">
        <StockLogo symbol={row.symbol} size="s" />
        <span className="compact-symbol">{row.symbol}</span>
      </span>

      <span className="lib-cell lib-cell-target r">
        <span>{money(row.target_price)}　{row.target_month}</span>
      </span>

      <span className="lib-cell">{formatArchivedAt(row.archived_at!)}</span>

      <span className="lib-cell r">{formatReturn(row.best_return)}</span>

      <span className="lib-cell lib-cell-actions">
        <button
          className="text-button"
          onClick={() => void onRestore(row)}
          disabled={busy}
          aria-label={`還原 ${who}`}
        >
          還原
        </button>
        <button
          className="text-button danger"
          onClick={() => onRequestDelete(row.id)}
          disabled={busy}
          aria-label={`永久刪除 ${who}`}
        >
          永久刪除
        </button>
      </span>
    </li>
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
  const isDesktop = useIsDesktop();
  const [rows, setRows] = useState<ScenarioSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // ---------- 批次選取（TR5／#93） ----------
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchErrors, setBatchErrors] = useState<Record<string, string>>({});

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

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const all = rows ?? [];
    setSelectedIds((prev) =>
      prev.size === all.length ? new Set() : new Set(all.map((r) => r.id)));
  }

  /** 批量還原：沿用主清單批次移入垃圾桶（TR6／#91）同一種序列佇列
   *  模式——依序呼叫既有單筆端點，個別失敗不中斷其餘筆，成功者立刻
   *  從清單移除並交回 `onRestore`，失敗者留著並在下方列出原因。 */
  async function batchRestore() {
    const targets = (rows ?? []).filter((r) => selectedIds.has(r.id));
    setBatchBusy(true);
    const errors: Record<string, string> = {};
    for (const row of targets) {
      try {
        await restoreScenario(row.id);
        setRows((prev) => (prev ?? []).filter((r) => r.id !== row.id));
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(row.id);
          return next;
        });
        onRestore(row);
      } catch (e) {
        errors[row.id] = e instanceof Error ? e.message : String(e);
      }
    }
    setBatchErrors(errors);
    setBatchBusy(false);
  }

  async function batchDelete() {
    const targets = (rows ?? []).filter((r) => selectedIds.has(r.id));
    setBatchBusy(true);
    const errors: Record<string, string> = {};
    for (const row of targets) {
      try {
        await deleteScenario(row.id);
        setRows((prev) => (prev ?? []).filter((r) => r.id !== row.id));
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(row.id);
          return next;
        });
      } catch (e) {
        errors[row.id] = e instanceof Error ? e.message : String(e);
      }
    }
    setBatchErrors(errors);
    setBatchBusy(false);
    setConfirmBatchDelete(false);
  }

  const toDelete = rows?.find((r) => r.id === confirmDeleteId) ?? null;
  const batchDeleteTargets = (rows ?? []).filter((r) => selectedIds.has(r.id));

  return (
    <div className="screen">
      <div className="toolbar toolbar-flush">
        <div className="toolbar-row">
          <a className="nav-back" href="#/">‹ 劇本庫</a>
          {rows !== null && rows.length > 0 && (
            <button className="text-button" onClick={toggleSelectAll}>
              {selectedIds.size === rows.length ? "取消全選" : "全選"}
            </button>
          )}
        </div>
        <div className="toolbar-row">
          <h1 className="toolbar-title">垃圾桶</h1>
        </div>
        <span className="caption">
          這裡的劇本不再刷新報價，可還原或永久刪除。
          {rows !== null && `${rows.length} 個劇本`}
        </span>
      </div>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {Object.keys(batchErrors).length > 0 && (
        <div className="notice error" role="alert">
          {Object.entries(batchErrors).map(([id, message]) => {
            const who = rows?.find((r) => r.id === id)?.symbol ?? id;
            return <p key={id} className="caption">{who}：{message}</p>;
          })}
        </div>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <p className="caption empty-trash">垃圾桶是空的。</p>
      )}

      {rows !== null && rows.length > 0 && (
        isDesktop ? (
          <div className="lib-table trash-table">
            <TrashTableHead />
            <ul className="compact-list lib-tbody">
              {rows.map((row) => (
                <TrashRowTable
                  key={row.id}
                  row={row}
                  busy={busyId === row.id}
                  checked={selectedIds.has(row.id)}
                  onToggleSelected={toggleSelected}
                  onRestore={restore}
                  onRequestDelete={setConfirmDeleteId}
                />
              ))}
            </ul>
          </div>
        ) : (
          <ul className="list">
            {rows.map((row) => (
              <TrashRowCard
                key={row.id}
                row={row}
                busy={busyId === row.id}
                checked={selectedIds.has(row.id)}
                onToggleSelected={toggleSelected}
                onRestore={restore}
                onRequestDelete={setConfirmDeleteId}
              />
            ))}
          </ul>
        )
      )}

      {rows !== null && rows.length > 0 && (
        <div className="batch-action-bar">
          <span className="caption">已選 {selectedIds.size} 個</span>
          <div className="trash-batch-actions">
            <button
              className="batch-pill"
              disabled={selectedIds.size === 0 || batchBusy}
              onClick={() => void batchRestore()}
            >
              還原已選
            </button>
            <button
              className="batch-pill danger"
              disabled={selectedIds.size === 0 || batchBusy}
              onClick={() => setConfirmBatchDelete(true)}
            >
              永久刪除已選
            </button>
          </div>
        </div>
      )}

      {toDelete && (
        <ConfirmDeleteOne
          row={toDelete}
          busy={busyId === toDelete.id}
          onCancel={() => setConfirmDeleteId(null)}
          onConfirm={() => void confirmDelete(toDelete)}
        />
      )}

      {confirmBatchDelete && (
        <ConfirmDeleteBatch
          rows={batchDeleteTargets}
          busy={batchBusy}
          onCancel={() => setConfirmBatchDelete(false)}
          onConfirm={() => void batchDelete()}
        />
      )}
    </div>
  );
}
