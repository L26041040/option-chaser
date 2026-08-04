import { describe, expect, it } from "vitest";

import {
  COLOR_CAP,
  NEUTRAL_BAND,
  cellColor,
  columnLabel,
  formatCell,
  priceTags,
} from "./heatmap";

function alphaOf(color: string): number {
  const hit = /rgba\([^)]*,\s*([\d.]+)\)/.exec(color);
  return hit ? Number(hit[1]) : 0;
}

describe("格子配色", () => {
  it("中性帶內不上色——±5% 以內的差別不值得用顏色喊", () => {
    expect(cellColor(0)).toBe("transparent");
    expect(cellColor(NEUTRAL_BAND - 0.001)).toBe("transparent");
    expect(cellColor(-(NEUTRAL_BAND - 0.001))).toBe("transparent");
  });

  it("賺賠用不同顏色，而且愈極端愈濃", () => {
    expect(cellColor(0.5)).not.toBe(cellColor(-0.5));
    expect(alphaOf(cellColor(0.8))).toBeGreaterThan(alphaOf(cellColor(0.2)));
  });

  it("超過 ±100% 濃度封頂，不會愈畫愈黑", () => {
    expect(cellColor(COLOR_CAP)).toBe(cellColor(5));
  });

  it("用半透明疊色，深淺兩種模式才能共用一套", () => {
    expect(cellColor(0.5)).toMatch(/^rgba\(/);
  });
});

describe("格子文字", () => {
  it("一律帶正負號，看得出方向", () => {
    expect(formatCell(0.5666)).toBe("+57%");
    expect(formatCell(-1)).toBe("-100%");
    expect(formatCell(0)).toBe("+0%");
  });
});

describe("軸標籤", () => {
  it("日期只顯示月／日，最後一欄講明是到期", () => {
    expect(columnLabel("2026-08-07", false)).toBe("08/07");
    expect(columnLabel("2026-08-07", true)).toBe("08/07 到期");
  });

  it("錨點標記照引擎給的標籤翻譯，不自己判斷哪個價是現價", () => {
    expect(priceTags("<現價>")).toEqual(["現價"]);
    expect(priceTags("")).toEqual([]);
    // 同一個價格同時是現價與目標時兩個都要在
    expect(priceTags("<現價><目標>")).toEqual(["現價", "目標"]);
  });
});
