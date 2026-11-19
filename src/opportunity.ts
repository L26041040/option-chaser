/**
 * OS-05（#394）：機會搜尋頁的純邏輯。只排序、合併既有欄位——每個數字
 * 都是後端（既有引擎）給的原值，這裡不算任何報酬、成本或損失。
 */
import type { OpportunityRow, OpportunitySearchSettings } from "./api";

export type OpportunitySort = OpportunitySearchSettings["sort"];

/** 排序鍵：越小越前面。與後端 `opportunity_search._SORT_KEYS` 同一套。 */
const SORT_KEY: Record<OpportunitySort, (r: OpportunityRow) => number> = {
  // 目標價情境報酬由高到低（同既有 Scenario Bet Ranking 口徑）。
  return: (r) => -r.target_return,
  cost: (r) => r.entry_cost,
  max_loss: (r) => r.max_loss_per_contract,
};

function cmp<T>(a: T, b: T): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * 跨標的合併排序（#389 §5.4）。同值依 (symbol, family) 的字串順序決定，
 * 與後端 `sort_rows()` 的 tie-break 相同——前端換排序不必重新搜尋，結果
 * 與輸入順序無關。回傳新陣列，不改動輸入。
 */
export function rankOpportunities(
  rows: readonly OpportunityRow[],
  sort: OpportunitySort,
): OpportunityRow[] {
  const key = SORT_KEY[sort];
  return [...rows].sort(
    (a, b) => cmp(key(a), key(b)) || cmp(a.symbol, b.symbol) || cmp(a.family, b.family),
  );
}

/** 一列的身分：一個 symbol＋family 只有一列（合併、React key、存檔狀態
 *  都用這一個）。 */
export const opportunityRowKey = (r: OpportunityRow) => `${r.symbol}\u0000${r.family}`;

/**
 * 續跑（`remaining`）回來的一批列併進既有結果：一個 symbol＋family 只留
 * 一列（同一列再回來時以新的取代、位置不變），其餘依序接在後面。
 */
export function mergeSearchRows(
  existing: readonly OpportunityRow[],
  incoming: readonly OpportunityRow[],
): OpportunityRow[] {
  const merged = [...existing];
  const index = new Map(merged.map((r, i) => [opportunityRowKey(r), i]));
  for (const r of incoming) {
    const at = index.get(opportunityRowKey(r));
    if (at === undefined) {
      index.set(opportunityRowKey(r), merged.length);
      merged.push(r);
    } else {
      merged[at] = r;
    }
  }
  return merged;
}
