import { describe, expect, it } from "vitest";

import type { HistoryEntry } from "./api";
import { bucketKey, chartPoints, contiguousRuns, downsampleHistory,
        xAxisTicks, yAxisDomain, type ChartPoint } from "./spreadHistory";

function entry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return { analyzed_at: "2026-07-15T21:30:00-04:00", spot: 100.0,
          cost: 5.2, baseline_return: 0.4, rank_in_expiry: 1, ...overrides };
}

describe("bucketKey", () => {
  it("day：年月日", () => {
    expect(bucketKey("2026-07-15T21:30:00-04:00", "day")).toBe("2026-07-15");
  });

  it("month：年月", () => {
    expect(bucketKey("2026-07-15T21:30:00-04:00", "month")).toBe("2026-07");
  });

  it("week：往回推到當週星期一（ISO 週起始）", () => {
    // 2026-07-15 是星期三
    expect(bucketKey("2026-07-15T21:30:00-04:00", "week")).toBe("2026-07-13");
    // 星期一自己就是週起始
    expect(bucketKey("2026-07-13T00:00:00-04:00", "week")).toBe("2026-07-13");
    // 星期日歸屬上一週
    expect(bucketKey("2026-07-19T00:00:00-04:00", "week")).toBe("2026-07-13");
  });
});

describe("downsampleHistory：同一日多筆快照取最後一筆", () => {
  it("同一天兩筆——只留最後一筆（票上明列的口徑）", () => {
    const entries = [
      entry({ analyzed_at: "2026-07-15T09:30:00-04:00", cost: 5.0 }),
      entry({ analyzed_at: "2026-07-15T15:30:00-04:00", cost: 5.5 }),
    ];
    const result = downsampleHistory(entries, "day");
    expect(result).toHaveLength(1);
    expect(result[0].cost).toBe(5.5);
    expect(result[0].analyzed_at).toBe("2026-07-15T15:30:00-04:00");
  });

  it("不同天各自成組，順序保留升冪", () => {
    const entries = [
      entry({ analyzed_at: "2026-07-15T09:30:00-04:00", cost: 5.0 }),
      entry({ analyzed_at: "2026-07-16T09:30:00-04:00", cost: 5.5 }),
    ];
    const result = downsampleHistory(entries, "day");
    expect(result.map((e) => e.cost)).toEqual([5.0, 5.5]);
  });

  it("斷點（cost=null）不特別偏袒——該組最後一筆是斷點，組的結果就是斷點", () => {
    const entries = [
      entry({ analyzed_at: "2026-07-15T09:30:00-04:00", cost: 5.0 }),
      entry({ analyzed_at: "2026-07-15T15:30:00-04:00", cost: null }),
    ];
    const result = downsampleHistory(entries, "day");
    expect(result).toHaveLength(1);
    expect(result[0].cost).toBeNull();
  });

  it("週／月降採樣同樣取最後一筆", () => {
    const entries = [
      entry({ analyzed_at: "2026-07-13T09:30:00-04:00", cost: 5.0 }),  // 週一
      entry({ analyzed_at: "2026-07-17T09:30:00-04:00", cost: 5.9 }),  // 同週五
      entry({ analyzed_at: "2026-08-01T09:30:00-04:00", cost: 6.2 }),  // 下個月
    ];
    expect(downsampleHistory(entries, "week").map((e) => e.cost)).toEqual([5.9, 6.2]);
    expect(downsampleHistory(entries, "month").map((e) => e.cost)).toEqual([5.9, 6.2]);
  });

  it("空序列回傳空序列", () => {
    expect(downsampleHistory([], "day")).toEqual([]);
  });
});

describe("yAxisDomain：固定 [最低×0.85, 最高×1.15]", () => {
  it("依非缺席的 cost 算範圍", () => {
    const entries = [entry({ cost: 4.0 }), entry({ cost: 6.0 }), entry({ cost: null })];
    expect(yAxisDomain(entries)).toEqual([4.0 * 0.85, 6.0 * 1.15]);
  });

  it("全部缺席時回傳 null，不硬湊一個 [0,0]", () => {
    expect(yAxisDomain([entry({ cost: null }), entry({ cost: null })])).toBeNull();
  });

  it("只有一筆有效值時，範圍以那一筆為準（min===max 也是合法範圍）", () => {
    expect(yAxisDomain([entry({ cost: 5.0 })])).toEqual([5.0 * 0.85, 5.0 * 1.15]);
  });
});

describe("chartPoints：座標換算＋斷點保留", () => {
  it("依序均分 x 座標，y 依固定範圍線性換算", () => {
    const entries = [entry({ cost: 4.0 }), entry({ cost: 6.0 })];
    const points = chartPoints(entries, [4.0, 6.0]);
    expect(points[0].x).toBe(0);
    expect(points[1].x).toBe(1);
    expect(points[0].y).toBe(1);   // 最低值在底部（y=1）
    expect(points[1].y).toBe(0);   // 最高值在頂部（y=0）
  });

  it("斷點的 y 是 null，不是 0——不能被畫成谷底", () => {
    const entries = [entry({ cost: 5.0 }), entry({ cost: null })];
    const points = chartPoints(entries, [4.0, 6.0]);
    expect(points[1].y).toBeNull();
  });

  it("單點序列 x 置中，不除以零", () => {
    const points = chartPoints([entry({ cost: 5.0 })], [4.0, 6.0]);
    expect(points[0].x).toBe(0.5);
  });
});

describe("xAxisTicks：X 軸日期刻度均勻取樣（MVP V3／#106）", () => {
  function point(label: string): ChartPoint {
    return { x: 0, y: 0.5, label };
  }

  it("空序列回傳空陣列", () => {
    expect(xAxisTicks([])).toEqual([]);
  });

  it("單點：只有一個刻度，就是它自己", () => {
    expect(xAxisTicks([point("a")])).toEqual([{ index: 0, label: "a" }]);
  });

  it("點數不超過 4 個：每個點都是刻度，不省略任何一個", () => {
    const points = [point("a"), point("b"), point("c")];
    expect(xAxisTicks(points)).toEqual([
      { index: 0, label: "a" }, { index: 1, label: "b" }, { index: 2, label: "c" },
    ]);
  });

  it("點數超過 4 個：最多 4 個刻度，且一定含頭尾", () => {
    const points = Array.from({ length: 12 }, (_, i) => point(`p${i}`));
    const ticks = xAxisTicks(points);
    expect(ticks.length).toBeLessThanOrEqual(4);
    expect(ticks[0]).toEqual({ index: 0, label: "p0" });
    expect(ticks[ticks.length - 1]).toEqual({ index: 11, label: "p11" });
  });

  it("刻度的 index 嚴格遞增——不會前後顛倒或重複", () => {
    const points = Array.from({ length: 20 }, (_, i) => point(`p${i}`));
    const indices = xAxisTicks(points).map((t) => t.index);
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThan(indices[i - 1]);
    }
  });
});

describe("contiguousRuns：依斷點切段，段間不連線", () => {
  it("沒有斷點時是一整段", () => {
    const points = [{ x: 0, y: 0.5, label: "a" }, { x: 1, y: 0.3, label: "b" }];
    expect(contiguousRuns(points)).toEqual([points]);
  });

  it("斷點把序列切成兩段，斷點本身不出現在任何一段裡", () => {
    const a = { x: 0, y: 0.5, label: "a" };
    const gap = { x: 0.5, y: null, label: "gap" };
    const b = { x: 1, y: 0.3, label: "b" };
    expect(contiguousRuns([a, gap, b])).toEqual([[a], [b]]);
  });

  it("連續多個斷點不會產生空段", () => {
    const a = { x: 0, y: 0.5, label: "a" };
    const gap1 = { x: 0.3, y: null, label: "g1" };
    const gap2 = { x: 0.6, y: null, label: "g2" };
    const b = { x: 1, y: 0.3, label: "b" };
    expect(contiguousRuns([a, gap1, gap2, b])).toEqual([[a], [b]]);
  });

  it("開頭或結尾就是斷點，仍正確切段", () => {
    const gap = { x: 0, y: null, label: "gap" };
    const a = { x: 0.5, y: 0.5, label: "a" };
    expect(contiguousRuns([gap, a])).toEqual([[a]]);
  });

  it("全部都是斷點時回傳空陣列", () => {
    expect(contiguousRuns([{ x: 0, y: null, label: "g" }])).toEqual([]);
  });
});
