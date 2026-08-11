import { describe, expect, it } from "vitest";

import {
  COLOR_CAP,
  NEUTRAL_BAND,
  cellColor,
  columnLabel,
  crossoverEdges,
  crossoverFavoredSide,
  formatCell,
  formatMovePct,
  formatMovePctShort,
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

describe("格子文字（#121：去掉 +／% 換取橫向密度）", () => {
  it("純數字，不帶正負號、不帶百分號——顏色與位置已經講清楚方向", () => {
    expect(formatCell(0.5666)).toBe("57");
    expect(formatCell(-1)).toBe("-100");
    expect(formatCell(0)).toBe("0");
  });

  it("負值四捨五入到 0 時顯示 \"0\"，不是容易誤讀的 \"-0\"", () => {
    expect(formatCell(-0.004)).toBe("0");
  });
});

describe("價格右側 ±% 標註（決策 M／#109）", () => {
  it("完整格式：一律帶正負號、一位小數", () => {
    expect(formatMovePct(0.136)).toBe("+13.6%");
    expect(formatMovePct(-0.1)).toBe("-10.0%");
    expect(formatMovePct(0)).toBe("+0.0%");
  });

  it("短格式（Mobile 允許縮短）：一律帶正負號、四捨五入到整數，" +
     "不是完全省略", () => {
    expect(formatMovePctShort(0.136)).toBe("+14%");
    expect(formatMovePctShort(-0.1)).toBe("-10%");
    expect(formatMovePctShort(0)).toBe("+0%");
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

describe("Crossover Boundary 邊界偵測（#116：純幾何，不重算任何報酬率）", () => {
  it("整格 Spread 都贏：沒有邊界，favoredSide 回 spread", () => {
    const spread = [[0.5, 0.6], [0.7, 0.8]];
    const comparator = [[0.1, 0.1], [0.1, 0.1]];
    expect(crossoverEdges(spread, comparator)).toEqual([]);
    expect(crossoverFavoredSide(spread, comparator)).toBe("spread");
  });

  it("整格 comparator 都贏：沒有邊界，favoredSide 回 comparator", () => {
    const spread = [[0.1, 0.1], [0.1, 0.1]];
    const comparator = [[0.5, 0.6], [0.7, 0.8]];
    expect(crossoverEdges(spread, comparator)).toEqual([]);
    expect(crossoverFavoredSide(spread, comparator)).toBe("comparator");
  });

  it("同一欄裡符號翻轉——抓到 vertical 邊界", () => {
    // col 0：row0=+0.1, row1=-0.1 → 兩者之間翻轉
    const spread = [[0.2], [-0.3]];
    const comparator = [[0.1], [-0.2]];
    // diff = [0.1, -0.1] → 符號翻轉
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "vertical" });
  });

  it("同一列裡符號翻轉——抓到 horizontal 邊界", () => {
    const spread = [[0.2, -0.3]];
    const comparator = [[0.1, -0.2]];
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "horizontal" });
  });

  it("兩軸都有翻轉時兩種邊界都要抓到，不是只認一個方向", () => {
    const spread = [
      [0.5, -0.5],
      [-0.5, -0.6],
    ];
    const comparator = [
      [0.1, 0.1],
      [0.1, 0.1],
    ];
    // diff = [[0.4, -0.6], [-0.6, -0.7]]
    // vertical: col0 row0→row1 符號翻轉 (0.4→-0.6)；col1 沒有翻轉 (-0.6→-0.7)
    // horizontal: row0 col0→col1 翻轉 (0.4→-0.6)；row1 沒有翻轉 (-0.6→-0.7)
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "vertical" });
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "horizontal" });
    expect(edges).not.toContainEqual({ row: 0, col: 1, orientation: "vertical" });
    expect(edges).not.toContainEqual({ row: 1, col: 0, orientation: "horizontal" });
  });

  it("恰好相等（diff=0）算作邊界——0 本身就是那個等值點", () => {
    const spread = [[0.3], [0.1]];
    const comparator = [[0.3], [0.5]];
    // diff = [0.0, -0.4] → sign 0 與 sign -1 不同，算翻轉
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "vertical" });
  });

  it("矩陣形狀不一致時誠實回空陣列，不猜、不半算", () => {
    const spread = [[0.1, 0.2], [0.3, 0.4]];
    const comparatorWrongRows = [[0.1, 0.2]];
    expect(crossoverEdges(spread, comparatorWrongRows)).toEqual([]);

    const comparatorWrongCols = [[0.1], [0.3]];
    expect(crossoverEdges(spread, comparatorWrongCols)).toEqual([]);
  });

  it("真正混合但形狀不一致：favoredSide 用可用格子判斷，不假造缺格資料", () => {
    const spread = [[0.5]];
    const comparator = [[0.1, 0.1]];   // 多一欄，缺對應的第二欄 spread 值
    // spreadCells[0][1] undefined → d = undefined - 0.1 = NaN，NaN 比較恆 false
    expect(crossoverFavoredSide(spread, comparator)).toBe("spread");
  });
});
