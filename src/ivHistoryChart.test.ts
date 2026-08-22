/**
 * IV 相對位置走勢圖純函式（#140）。`contiguousRuns`／`xAxisTicks` 是
 * 從 `./spreadHistory` 沿用的既有幾何函式，這裡不重測——已有
 * `spreadHistory.test.ts` 覆蓋。只測本檔案新增的 `ivYAxisDomain`／
 * `ivChartPoints`。
 */
import { describe, expect, it } from "vitest";

import { ivChartPoints, ivYAxisDomain, nearestIndexForClientX,
        projectOntoDomain } from "./ivHistoryChart";

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

describe("nearestIndexForClientX（Firstrade 風格整張圖 scrubber 的座標數學，" +
        "需求方 2026-08-22 反饋）", () => {
  const VIEWBOX_WIDTH = 300;
  const PAD_LEFT = 34;
  const PAD_RIGHT = 6;

  it("游標在繪圖區左邊界時找到第一個點", () => {
    const idx = nearestIndexForClientX(
      PAD_LEFT, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(0);
  });

  it("游標在繪圖區右邊界時找到最後一個點", () => {
    const idx = nearestIndexForClientX(
      VIEWBOX_WIDTH - PAD_RIGHT, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(9);
  });

  it("游標在繪圖區正中央時找到中間附近的點", () => {
    const plotWidth = VIEWBOX_WIDTH - PAD_LEFT - PAD_RIGHT;
    const idx = nearestIndexForClientX(
      PAD_LEFT + plotWidth / 2, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(5); // round(0.5 * 9) = round(4.5) = 5
  });

  it("游標超出圖表右側時夾在最後一個點，不是找不到", () => {
    const idx = nearestIndexForClientX(
      1000, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(9);
  });

  it("游標在圖表左側之外（負座標）時夾在第一個點", () => {
    const idx = nearestIndexForClientX(
      -100, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(0);
  });

  it("SVG 實際渲染寬度（CSS width:100%）跟 viewBox 座標不同時仍正確換算——" +
     "這裡渲染寬度是 viewBox 的兩倍", () => {
    const rect = { left: 20, width: VIEWBOX_WIDTH * 2 };
    const plotWidth = VIEWBOX_WIDTH - PAD_LEFT - PAD_RIGHT;
    // viewBox 座標系裡繪圖區中點；換算回螢幕座標要乘上縮放比例、再加
    // 上 rect.left 的位移。
    const midViewBoxX = PAD_LEFT + plotWidth / 2;
    const clientX = rect.left + midViewBoxX * 2;
    const idx = nearestIndexForClientX(
      clientX, rect, VIEWBOX_WIDTH, PAD_LEFT, PAD_RIGHT, 10);
    expect(idx).toBe(5);
  });

  it("只有一個資料點時永遠指向那一個點", () => {
    const idx = nearestIndexForClientX(
      PAD_LEFT, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 1);
    expect(idx).toBe(0);
  });

  it("沒有資料點時回傳 null", () => {
    expect(nearestIndexForClientX(
      150, { left: 0, width: VIEWBOX_WIDTH }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 0)).toBeNull();
  });

  it("量到的渲染寬度是 0（元素還沒真的佈局）時回傳 null，不除以零", () => {
    expect(nearestIndexForClientX(
      150, { left: 0, width: 0 }, VIEWBOX_WIDTH,
      PAD_LEFT, PAD_RIGHT, 10)).toBeNull();
  });
});

describe("projectOntoDomain（HIVT-05／#156：四條疊加序列共用同一個 x 軸）", () => {
  const domainDates = ["2026-01-01", "2026-01-02", "2026-01-03"];

  it("依日期把值投影到共用的日期軸上，不是照自己的長度排位置", () => {
    const series = [
      { date: "2026-01-01", value: 0.10 },
      { date: "2026-01-02", value: 0.20 },
      { date: "2026-01-03", value: 0.30 },
    ];
    expect(projectOntoDomain(domainDates, series)).toEqual([0.10, 0.20, 0.30]);
  });

  it("比主軸稀疏的序列（例如 moving average 起始端還沒有值）缺的日期回 null，"
     + "不是把陣列往前擠", () => {
    // 只有最後一天有值——起始兩天視窗觀測數不足。
    const series = [{ date: "2026-01-03", value: 0.25 }];
    expect(projectOntoDomain(domainDates, series)).toEqual([null, null, 0.25]);
  });

  it("序列裡某天的值本身就是 null（統計量 unavailable）——投影後仍是 null，"
     + "不會被誤判成「這天沒有這筆觀測」", () => {
    const series = [
      { date: "2026-01-01", value: null },
      { date: "2026-01-02", value: 0.20 },
      { date: "2026-01-03", value: null },
    ];
    expect(projectOntoDomain(domainDates, series)).toEqual([null, 0.20, null]);
  });

  it("空序列投影到任何日期軸上全部是 null", () => {
    expect(projectOntoDomain(domainDates, [])).toEqual([null, null, null]);
  });
});
