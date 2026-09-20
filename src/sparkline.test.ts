import { describe, expect, it } from "vitest";

import { sparklineDirection, sparklineDots, sparklineRuns,
        type SparklinePoint } from "./sparkline";

describe("sparklineDots", () => {
  it("正規化到 0～1，最低成本在底（y=1）、最高在頂（y=0）", () => {
    const points: SparklinePoint[] = [
      ["2026-01-01", 1], ["2026-01-02", 3], ["2026-01-03", 2],
    ];
    const dots = sparklineDots(points);
    expect(dots[0].y).toBe(1);     // 最低
    expect(dots[1].y).toBe(0);     // 最高
    expect(dots[2].y).toBeCloseTo(0.5);
  });

  it("x 沿序列位置等距分布", () => {
    const points: SparklinePoint[] = [
      ["2026-01-01", 1], ["2026-01-02", 2], ["2026-01-03", 3],
    ];
    const dots = sparklineDots(points);
    expect(dots.map((d) => d.x)).toEqual([0, 0.5, 1]);
  });

  it("缺席快照（cost=null）的點 y 是 null，不參與域值計算", () => {
    const points: SparklinePoint[] = [
      ["2026-01-01", 1], ["2026-01-02", null], ["2026-01-03", 5],
    ];
    const dots = sparklineDots(points);
    expect(dots[1].y).toBeNull();
    expect(dots[0].y).toBe(1);
    expect(dots[2].y).toBe(0);
  });

  it("全部同一個成本（span=0）——每個有效點落在正中間，不是除以零", () => {
    const points: SparklinePoint[] = [["2026-01-01", 5], ["2026-01-02", 5]];
    const dots = sparklineDots(points);
    expect(dots.every((d) => d.y === 0.5)).toBe(true);
  });

  it("單點序列——落在正中間，x 也是 0.5", () => {
    const dots = sparklineDots([["2026-01-01", 5]]);
    expect(dots).toEqual([{ x: 0.5, y: 0.5 }]);
  });

  it("全部缺席——每個點 y 都是 null（沒有域值可正規化）", () => {
    const points: SparklinePoint[] = [["2026-01-01", null], ["2026-01-02", null]];
    const dots = sparklineDots(points);
    expect(dots.every((d) => d.y === null)).toBe(true);
  });
});

describe("sparklineRuns：斷點如實顯示，不連線", () => {
  it("中間一個缺席，切成兩段", () => {
    const runs = sparklineRuns([
      { x: 0, y: 0.2 }, { x: 0.5, y: null }, { x: 1, y: 0.8 },
    ]);
    expect(runs).toEqual([[{ x: 0, y: 0.2 }], [{ x: 1, y: 0.8 }]]);
  });

  it("沒有缺席——整段是一條線", () => {
    const runs = sparklineRuns([{ x: 0, y: 0.2 }, { x: 1, y: 0.8 }]);
    expect(runs).toEqual([[{ x: 0, y: 0.2 }, { x: 1, y: 0.8 }]]);
  });

  it("全部缺席——沒有任何一段", () => {
    expect(sparklineRuns([{ x: 0, y: null }, { x: 1, y: null }])).toEqual([]);
  });
});

describe("sparklineDirection：線色依首尾方向", () => {
  it("最後一筆高於第一筆——上升", () => {
    expect(sparklineDirection([["a", 1], ["b", 2]])).toBe("up");
  });

  it("最後一筆低於第一筆——下降", () => {
    expect(sparklineDirection([["a", 2], ["b", 1]])).toBe("down");
  });

  it("首尾相等——持平", () => {
    expect(sparklineDirection([["a", 1], ["b", 3], ["c", 1]])).toBe("flat");
  });

  it("忽略缺席快照找真正的頭尾——最後一筆缺席時往前找有效值", () => {
    expect(sparklineDirection([["a", 1], ["b", 2], ["c", null]])).toBe("up");
  });

  it("不足兩個有效點——持平（方向沒有意義）", () => {
    expect(sparklineDirection([["a", 1]])).toBe("flat");
    expect(sparklineDirection([["a", null], ["b", null]])).toBe("flat");
    expect(sparklineDirection([])).toBe("flat");
  });
});
