/**
 * V2-03（#405）：「分歧度歷史排序」以 PR 顯示。
 *
 * 期望值是 #405 驗收條件逐條手寫的字面值；「顯示 ≥ 門檻 ⇒ 實際通過」的
 * 性質測試用的「實際通過」是**後端**的判斷式（`option_chaser/consensus.py`
 * `evaluate_gate`：`percentile <= percentile_max / 100 + 1e-9`），在這裡獨立
 * 寫一份當 oracle，不呼叫被測模組的任何換算。
 */
import { describe, expect, it } from "vitest";

import {
  percentileMaxFromPrInput,
  prDisplay,
  prInputFromPercentileMax,
  prLabel,
  prThresholdLabel,
} from "./dispersionRank";

/** 後端第一道門檻（照抄 `evaluate_gate` 的判斷式，0–1 比例、EPSILON 1e-9）。 */
function backendPasses(percentile: number, percentileMax: number): boolean {
  return percentile <= percentileMax / 100 + 1e-9;
}

describe("PR 換算（#405 驗收條件）", () => {
  it("12% → PR88（前 12%）", () => {
    expect(prDisplay(0.12)).toBe(88);
    expect(prLabel(0.12)).toBe("PR88（前 12%）");
  });

  it("0% → PR100；100% → PR0", () => {
    expect(prDisplay(0)).toBe(100);
    expect(prDisplay(1)).toBe(0);
    expect(prLabel(0)).toBe("PR100（前 0%）");
    expect(prLabel(1)).toBe("PR0（前 100%）");
  });

  it("20.4% → 顯示 PR79（向下取整），在預設門檻下不入選", () => {
    expect(prDisplay(0.204)).toBe(79);
    expect(prDisplay(0.204)).toBeLessThan(80);
    expect(backendPasses(0.204, 20)).toBe(false);
  });

  it("20.0% → 顯示 PR80，在預設門檻下入選", () => {
    expect(prDisplay(0.2)).toBe(80);
    expect(backendPasses(0.2, 20)).toBe(true);
  });

  it("浮點誤差不會把整數 PR 少算一級（0.12 × 100 不是剛好 12）", () => {
    for (const pct of [1, 7, 12, 29, 57, 58, 70, 99]) {
      expect(prDisplay(pct / 100)).toBe(100 - pct);
    }
  });

  it("沒有百分位（資料不足）時顯示 —", () => {
    expect(prLabel(null)).toBe("—");
  });
});

describe("顯示 ≥ 門檻 ⇒ 實際通過（性質測試）", () => {
  // 決定性的偽亂數（mulberry32），失敗時可重現。
  function rng(seed: number): () => number {
    let a = seed;
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const percentiles: number[] = [0, 1, 0.2, 0.204, 0.1999999999, 0.2000000001, 0.12, 0.5];
  // 整數百分點與其上下極小偏移（取整邊界）。
  for (let i = 0; i <= 100; i++) {
    const p = i / 100;
    percentiles.push(p, Math.max(0, p - 1e-12), Math.min(1, p + 1e-12),
                     Math.max(0, p - 1e-6), Math.min(1, p + 1e-6));
  }
  // midrank 百分位的實際形狀：(below + 0.5·equal) / n，n = 24…60。
  for (let n = 24; n <= 60; n++) {
    for (let k = 0; k <= 2 * n; k++) percentiles.push(k / (2 * n));
  }
  const next = rng(405);
  for (let i = 0; i < 5000; i++) percentiles.push(next());

  // 已存的門檻（原百分位 %）：整數、常見小數，以及從 PR 輸入換算回來的值。
  const maxes: number[] = [0, 100, 20, 10, 20.5, 33.3, 12.25];
  for (let i = 0; i <= 100; i++) maxes.push(i);
  for (const pr of [80, 79.5, 66.7, 87.75, 0, 100, 99.9, 0.1]) {
    maxes.push(percentileMaxFromPrInput(String(pr)) as number);
  }
  for (let i = 0; i < 200; i++) maxes.push(Math.round(next() * 1000) / 10);

  it("任意百分位 × 任意門檻：畫面上的 PR ≥ 門檻 PR 時，後端一定判通過", () => {
    let checked = 0;
    const violations: string[] = [];
    for (const max of maxes) {
      const threshold = prInputFromPercentileMax(max);
      for (const p of percentiles) {
        if (prDisplay(p) >= threshold) {
          checked++;
          if (!backendPasses(p, max)) violations.push(`p=${p} max=${max}`);
        }
      }
    }
    expect(violations.slice(0, 5)).toEqual([]);
    expect(checked).toBeGreaterThan(10000);
  });
});

describe("設定頁門檻：PR 輸入 ↔ 已存的原百分位", () => {
  it("舊值 20 ↔ PR ≥ 80", () => {
    expect(prInputFromPercentileMax(20)).toBe(80);
    expect(percentileMaxFromPrInput("80")).toBe(20);
    expect(prThresholdLabel(20)).toBe("PR ≥ 80");
  });

  it("小數不帶浮點雜訊：PR 79.9 ↔ 20.1", () => {
    expect(percentileMaxFromPrInput("79.9")).toBe(20.1);
    expect(prInputFromPercentileMax(20.1)).toBe(79.9);
    expect(prThresholdLabel(20.1)).toBe("PR ≥ 79.9");
  });

  it("兩端：PR 100 ↔ 0、PR 0 ↔ 100", () => {
    expect(percentileMaxFromPrInput("100")).toBe(0);
    expect(percentileMaxFromPrInput("0")).toBe(100);
  });

  it("空白或不是數字：原字串照送，讓後端回它的驗證訊息", () => {
    expect(percentileMaxFromPrInput("")).toBe("");
    expect(percentileMaxFromPrInput("abc")).toBe("abc");
  });

  it("超出 0–100 的 PR 換算後也超出範圍（交給後端擋）", () => {
    expect(percentileMaxFromPrInput("120")).toBe(-20);
    expect(percentileMaxFromPrInput("-5")).toBe(105);
  });
});
