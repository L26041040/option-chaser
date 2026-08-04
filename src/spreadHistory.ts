/**
 * Spread 淨成本走勢圖的純函式（V9／#57）。
 *
 * 零金融計算：`cost`／`baseline_return` 都是引擎算好的（T11／#25 既有
 * `spread_cost_history` 聚合語意，經 HTTP 走 `GET .../history`），這裡
 * 只做「怎麼分組、怎麼換算成畫布座標」的呈現層工作。
 *
 * 缺席快照的 `cost` 是 `null`——**如實呈現斷點，不插值**（票上明列的
 * 驗收標準）：`downsampleHistory` 保留 null，`chartPoints` 把 null 轉成
 * 一個「沒有 y 座標」的點，畫圖層據此把折線斷開，不畫成 0、不連過去。
 */
import type { HistoryEntry } from "./api";

export type Granularity = "day" | "week" | "month";

/**
 * 分組鍵——同一天／週／月的快照歸成同一組。週以 ISO 週一為週起始日
 * （台灣／多數行情網站的慣例），不是美式週日起始。
 */
export function bucketKey(iso: string, granularity: Granularity): string {
  const d = new Date(iso);
  if (granularity === "month") return iso.slice(0, 7);   // YYYY-MM
  if (granularity === "day") return iso.slice(0, 10);     // YYYY-MM-DD
  // week：往回推到當週星期一（UTC 曆，跟 iso 字串本身的日期部分一致）
  const utcDay = new Date(Date.UTC(
    d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dow = (utcDay.getUTCDay() + 6) % 7;   // 0=一 … 6=日
  utcDay.setUTCDate(utcDay.getUTCDate() - dow);
  return utcDay.toISOString().slice(0, 10);
}

/**
 * 日／週／月降採樣：同一組裡取最後一筆（票上原話「同一日多筆快照的
 * 日粒度聚合口徑（取最後一筆）屬工程判斷，票內記錄即可」）——不特別
 * 偏袒有數字的那一筆，該組最後一次更新是什麼狀態就呈現什麼狀態，這是
 * 票上明講的簡化，不是遺漏。`entries` 必須依 `analyzed_at` 升冪排列
 * （後端 `result_history()` 既有保證），最後一筆才會覆蓋到正確的值。
 */
export function downsampleHistory(
  entries: HistoryEntry[], granularity: Granularity,
): HistoryEntry[] {
  const buckets = new Map<string, HistoryEntry>();
  for (const e of entries) {
    // Map.set 對已存在的 key 只更新值，不改變原本的插入順序——升冪
    // 輸入因此保證輸出仍是升冪的分組序列。
    buckets.set(bucketKey(e.analyzed_at, granularity), e);
  }
  return [...buckets.values()];
}

/**
 * y 軸固定範圍：序列最高最低價位各 ±15%（票上明列公式），不隨互動
 * 滑動改變。只看非缺席的 `cost`；全部缺席時沒有範圍可言，回傳 null，
 * 呼叫端據此顯示「沒有可畫的資料」而不是硬畫一個 [0,0] 的圖。
 */
export function yAxisDomain(entries: HistoryEntry[]): [number, number] | null {
  const costs = entries
    .map((e) => e.cost)
    .filter((c): c is number => c !== null);
  if (costs.length === 0) return null;
  const min = Math.min(...costs);
  const max = Math.max(...costs);
  return [min * 0.85, max * 1.15];
}

export interface ChartPoint {
  /** 0（最左）～1（最右），沿 x 軸等距分布——分組後的序列本來就已經是
   *  「一組一個點」，不需要照時間長度比例分布。 */
  x: number;
  /** 0（頂／y 軸上限）～1（底／y 軸下限）；null＝這一點是斷點，不畫。 */
  y: number | null;
  label: string;
}

/** 把降採樣後的序列換算成畫布座標（0～1 相對座標，SVG 層自己乘上實際
 *  寬高）。斷點（`cost === null`）保留在陣列裡但 `y` 是 null——呼叫端
 *  據此把折線在該處斷開，不是把陣列過濾掉導致 x 軸間距跟著跳動。 */
export function chartPoints(
  entries: HistoryEntry[], domain: [number, number],
): ChartPoint[] {
  const [lo, hi] = domain;
  const span = hi - lo;
  const n = entries.length;
  return entries.map((e, i) => ({
    x: n <= 1 ? 0.5 : i / (n - 1),
    y: e.cost === null || span === 0 ? null : 1 - (e.cost - lo) / span,
    label: e.analyzed_at.slice(0, 10),
  }));
}

/**
 * 把一串點依斷點切成連續片段——每段各自畫一條折線，段與段之間不連線
 * （票上驗收標準：斷點如實顯示，不連線、不畫成 0）。單點片段也保留
 * （畫一個點，不是被當成無法連線而丟棄）。
 */
export function contiguousRuns(points: ChartPoint[]): ChartPoint[][] {
  const runs: ChartPoint[][] = [];
  let current: ChartPoint[] = [];
  for (const p of points) {
    if (p.y === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) runs.push(current);
  return runs;
}
