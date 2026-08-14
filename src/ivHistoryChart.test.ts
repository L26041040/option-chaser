/**
 * IV 相對位置走勢圖純函式（#140）。`contiguousRuns`／`xAxisTicks` 是
 * 從 `./spreadHistory` 沿用的既有幾何函式，這裡不重測——已有
 * `spreadHistory.test.ts` 覆蓋。只測本檔案新增的 `ivYAxisDomain`／
 * `ivChartPoints`。
 */
import { describe, expect, it } from "vitest";

import { ivChartPoints, ivYAxisDomain } from "./ivHistoryChart";

describe("ivYAxisDomain", () => {
  it("非空值各留 10% 邊界", () => {
    const domain = ivYAxisDomain([0.10, 0.20, 0.30]);
    expect(domain).not.toBeNull();
    const [lo, hi] = domain!;
    // span = 0.2, pad = 0.02
    expect(lo).toBeCloseTo(0.08);
    expect(hi).toBeCloseTo(0.32);
  });

  it("忽略 null，只看非空值", () => {
    const domain = ivYAxisDomain([null, 0.10, null, 0.30, null]);
    const [lo, hi] = domain!;
    expect(lo).toBeCloseTo(0.08);
    expect(hi).toBeCloseTo(0.32);
  });

  it("全同值時給一個以該值為中心的小範圍，不塌成一個點", () => {
    const domain = ivYAxisDomain([0.20, 0.20, 0.20]);
    expect(domain).not.toBeNull();
    const [lo, hi] = domain!;
    expect(lo).toBeLessThan(0.20);
    expect(hi).toBeGreaterThan(0.20);
  });

  it("全同值且值為 0 時仍給一個非零寬度的範圍（避免除以零）", () => {
    const domain = ivYAxisDomain([0, 0, 0]);
    const [lo, hi] = domain!;
    expect(hi - lo).toBeGreaterThan(0);
  });

  it("全部是 null 時沒有範圍可言", () => {
    expect(ivYAxisDomain([null, null])).toBeNull();
  });

  it("空陣列沒有範圍可言", () => {
    expect(ivYAxisDomain([])).toBeNull();
  });

  it("單一非空值也能給出範圍", () => {
    const domain = ivYAxisDomain([0.15]);
    expect(domain).not.toBeNull();
  });
});

describe("ivChartPoints", () => {
  it("把值換算成 0～1 的 y 座標，值最高的點 y 最接近 0（畫布頂端）", () => {
    const dates = ["2026-01-01", "2026-01-02", "2026-01-03"];
    const values = [0.10, 0.20, 0.30];
    const points = ivChartPoints(dates, values, [0.10, 0.30]);
    expect(points[0].y).toBeCloseTo(1);   // 最低值貼底
    expect(points[2].y).toBeCloseTo(0);   // 最高值貼頂
    expect(points[1].y).toBeCloseTo(0.5);
  });

  it("x 座標沿序列等距分布 0～1", () => {
    const dates = ["2026-01-01", "2026-01-02", "2026-01-03"];
    const points = ivChartPoints(dates, [0.1, 0.2, 0.3], [0.1, 0.3]);
    expect(points.map((p) => p.x)).toEqual([0, 0.5, 1]);
  });

  it("缺值的點 y 為 null——呼叫端據此把折線斷開", () => {
    const dates = ["2026-01-01", "2026-01-02", "2026-01-03"];
    const values = [0.10, null, 0.30];
    const points = ivChartPoints(dates, values, [0.10, 0.30]);
    expect(points[1].y).toBeNull();
    // 缺值的點依然保留在陣列裡（不是被過濾掉），x 座標不因此跳動。
    expect(points).toHaveLength(3);
    expect(points[1].x).toBeCloseTo(0.5);
  });

  it("日期只取日期部分（切掉可能附帶的時間）", () => {
    const points = ivChartPoints(["2026-01-01T00:00:00Z"], [0.2], [0.1, 0.3]);
    expect(points[0].label).toBe("2026-01-01");
  });

  it("單一資料點置中", () => {
    const points = ivChartPoints(["2026-01-01"], [0.2], [0.1, 0.3]);
    expect(points[0].x).toBe(0.5);
  });

  it("domain 塌成一個點時（span=0）y 一律為 null，不除以零", () => {
    const points = ivChartPoints(["2026-01-01"], [0.2], [0.2, 0.2]);
    expect(points[0].y).toBeNull();
  });
});
