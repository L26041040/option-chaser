/**
 * OG-04（#323）：劇本庫「淨成本走勢」sparkline 純函式。
 *
 * 跟 `spreadHistory.ts` 刻意不共用同一份型別——`HistoryEntry` 要求
 * `spot`／`baseline_return`／`rank_in_expiry` 皆非 null（詳細頁完整
 * 走勢圖的刻度／tooltip 要用到），這裡的輸入只有後端截尾過的
 * `[analyzed_at, cost]` 序列，硬套 `HistoryEntry` 得為這三個欄位
 * 捏造假值，反而更容易誤導。正規化與斷點切段的精神跟
 * `spreadHistory.ts::chartPoints()`／`contiguousRuns()` 一致（缺席即
 * 斷點、不插值），只是縮圖不需要 y 軸 ±15% padding（沒有刻度可讀，
 * 留白只會讓線看起來更平）。
 */
export type SparklinePoint = [string, number | null];

export interface SparklineDot {
  /** 0（最左）～1（最右），沿 x 軸等距分布。 */
  x: number;
  /** 0（頂）～1（底）；`null`＝這一點是斷點，不畫。 */
  y: number | null;
}

/** 把序列換算成 0～1 相對座標；域值取序列自身非缺席成本的最小最大值
 *  （不像詳細頁完整走勢圖留 ±15% padding——sparkline 沒有刻度可讀，
 *  留白只會讓線看起來更平，縮圖要的是「線真的看得出高低起伏」）。 */
export function sparklineDots(points: SparklinePoint[]): SparklineDot[] {
  const n = points.length;
  const costs = points.map(([, cost]) => cost).filter((c): c is number => c !== null);
  const domain = costs.length > 0 ? [Math.min(...costs), Math.max(...costs)] : null;
  return points.map(([, cost], i) => {
    const x = n <= 1 ? 0.5 : i / (n - 1);
    if (cost === null || domain === null) return { x, y: null };
    const [min, max] = domain;
    const span = max - min;
    return { x, y: span === 0 ? 0.5 : 1 - (cost - min) / span };
  });
}

/** 依斷點切成連續片段，段與段之間不連線——跟
 *  `spreadHistory.ts::contiguousRuns()` 同一個判準。 */
export function sparklineRuns(dots: SparklineDot[]): SparklineDot[][] {
  const runs: SparklineDot[][] = [];
  let current: SparklineDot[] = [];
  for (const dot of dots) {
    if (dot.y === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push(dot);
    }
  }
  if (current.length) runs.push(current);
  return runs;
}

export type SparklineDirection = "up" | "down" | "flat";

/** 線色依首尾方向（artifact／票面明文）：比較序列裡第一個與最後一個
 *  **非缺席**成本——缺席快照本身沒有成本可比較，跳過它們找真正的頭尾。
 *  不足兩個有效點（全部缺席，或只有一個有效點）時方向沒有意義，回
 *  `"flat"`（呼叫端據此用中性色，不是硬猜一個方向）。 */
export function sparklineDirection(points: SparklinePoint[]): SparklineDirection {
  const costs = points.map(([, cost]) => cost).filter((c): c is number => c !== null);
  if (costs.length < 2) return "flat";
  const first = costs[0];
  const last = costs[costs.length - 1];
  if (last > first) return "up";
  if (last < first) return "down";
  return "flat";
}
