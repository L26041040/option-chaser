import { describe, expect, it } from "vitest";

import {
  COLOR_CAP,
  NEUTRAL_BAND,
  cellColor,
  columnLabel,
  crossoverCellSides,
  crossoverEdges,
  crossoverFavoredSide,
  crossoverSides,
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
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "vertical",
                                 spreadHigher: "near" });
  });

  it("同一列裡符號翻轉——抓到 horizontal 邊界", () => {
    const spread = [[0.2, -0.3]];
    const comparator = [[0.1, -0.2]];
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "horizontal",
                                 spreadHigher: "near" });
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
    // 不比對整個物件——`spreadHigher` 是另一組測試的責任，這裡問的是
    // 「有沒有抓到這條邊」。否認式斷言尤其不能比整個物件：多一個欄位
    // 就會讓 `not.toContainEqual` 無論如何都通過，等於沒驗。
    const has = (row: number, col: number, orientation: string) =>
      edges.some((e) => e.row === row && e.col === col
                        && e.orientation === orientation);
    expect(has(0, 0, "vertical")).toBe(true);
    expect(has(0, 0, "horizontal")).toBe(true);
    expect(has(0, 1, "vertical")).toBe(false);
    expect(has(1, 0, "horizontal")).toBe(false);
  });

  it("恰好相等（diff=0）算作邊界——0 本身就是那個等值點", () => {
    const spread = [[0.3], [0.1]];
    const comparator = [[0.3], [0.5]];
    // diff = [0.0, -0.4] → sign 0 與 sign -1 不同，算翻轉
    const edges = crossoverEdges(spread, comparator);
    expect(edges).toContainEqual({ row: 0, col: 0, orientation: "vertical",
                                 spreadHigher: "near" });
  });

  it("邊界線畫在 Spread 較高的那一側——依實際差值判定，不是固定某一端",
     () => {
    // diff = [-0.4, +0.4]：較高的是 row1（far 端）
    const edgesFar = crossoverEdges([[0.1], [0.9]], [[0.5], [0.5]]);
    expect(edgesFar[0].spreadHigher).toBe("far");

    // 同一組資料上下對調 → 較高的變成 row0（near 端）。同一支函式在
    // 兩種排列下給出相反答案，就是「不預設方位」的證據。
    const edgesNear = crossoverEdges([[0.9], [0.1]], [[0.5], [0.5]]);
    expect(edgesNear[0].spreadHigher).toBe("near");
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

describe("Crossover 邊界線落在哪一格的哪一條邊（QA 修正：線不是整格粗框）", () => {
  it("垂直邊界、Spread 在下方那格：線畫在該格的上緣", () => {
    // 表格由高價到低價渲染，row+1 在 row 的「上方」，所以 row 這一格
    // 與上鄰之間的那條邊，對 row 而言是 top。
    const sides = crossoverCellSides(
      [{ row: 0, col: 2, orientation: "vertical", spreadHigher: "near" }]);
    expect(sides.get("0-2")).toEqual(["top"]);
    expect(sides.has("1-2")).toBe(false);
  });

  it("垂直邊界、Spread 在上方那格：線改畫在上面那格的下緣", () => {
    const sides = crossoverCellSides(
      [{ row: 0, col: 2, orientation: "vertical", spreadHigher: "far" }]);
    expect(sides.get("1-2")).toEqual(["bottom"]);
    expect(sides.has("0-2")).toBe(false);
  });

  it("水平邊界：near 畫右緣、far 畫右鄰那格的左緣", () => {
    expect(crossoverCellSides(
      [{ row: 1, col: 0, orientation: "horizontal", spreadHigher: "near" }])
      .get("1-0")).toEqual(["right"]);
    expect(crossoverCellSides(
      [{ row: 1, col: 0, orientation: "horizontal", spreadHigher: "far" }])
      .get("1-1")).toEqual(["left"]);
  });

  it("邊界在同一格轉角時兩條邊都畫，不是後面那條蓋掉前面那條", () => {
    const sides = crossoverCellSides([
      { row: 1, col: 1, orientation: "vertical", spreadHigher: "near" },
      { row: 1, col: 1, orientation: "horizontal", spreadHigher: "near" },
    ]);
    expect(sides.get("1-1")).toEqual(["top", "right"]);
  });

  it("完全沒有邊界時不標任何格子", () => {
    expect(crossoverCellSides([]).size).toBe(0);
  });
});

describe("Crossover 兩側歸屬（QA 修正：依實際矩陣判定，不預設左上／右下）", () => {
  const flat = (rows: number, cols: number, v: number) =>
    Array.from({ length: rows }, () => Array.from({ length: cols }, () => v));

  it("分界沿價格軸、Spread 在低價端", () => {
    // row 0（低價）Spread 贏、row 1（高價）comparator 贏
    const spread = [[0.9, 0.9], [0.1, 0.1]];
    expect(crossoverSides(spread, flat(2, 2, 0.5)))
      .toEqual({ axis: "price", spreadSide: "low" });
  });

  it("同一組資料上下翻轉，答案跟著翻——不是寫死某一端", () => {
    const spread = [[0.1, 0.1], [0.9, 0.9]];
    expect(crossoverSides(spread, flat(2, 2, 0.5)))
      .toEqual({ axis: "price", spreadSide: "high" });
  });

  it("分界沿日期軸時主軸判成 date，不會誤報成 price", () => {
    // 每一列都是「左邊 Spread 贏、右邊 comparator 贏」：價格軸上兩群
    // 重心相同（分離度 0），日期軸才是真正把兩群分開的那一軸。
    const spread = [[0.9, 0.1], [0.9, 0.1]];
    expect(crossoverSides(spread, flat(2, 2, 0.5)))
      .toEqual({ axis: "date", spreadSide: "low" });
  });

  it("左右翻轉時日期軸的答案也跟著翻", () => {
    const spread = [[0.1, 0.9], [0.1, 0.9]];
    expect(crossoverSides(spread, flat(2, 2, 0.5)))
      .toEqual({ axis: "date", spreadSide: "high" });
  });

  it("日期欄數遠多於價格列數時不會單純因為索引大就判成 date——" +
     "兩軸都正規化過", () => {
    // 20 欄日期、2 列價格，分界純粹沿價格軸。未正規化的話日期軸的
    // 索引尺度會壓過價格軸，主軸就會判錯。
    const spread = [
      Array.from({ length: 20 }, () => 0.9),
      Array.from({ length: 20 }, () => 0.1),
    ];
    expect(crossoverSides(spread, flat(2, 20, 0.5)))
      .toEqual({ axis: "price", spreadSide: "low" });
  });

  it("整張圖只有一側時回 null——那沒有「兩側」可講，呼叫端該改口徑", () => {
    expect(crossoverSides(flat(2, 2, 0.9), flat(2, 2, 0.1))).toBeNull();
    expect(crossoverSides(flat(2, 2, 0.1), flat(2, 2, 0.9))).toBeNull();
  });

  it("矩陣形狀不一致時回 null，不猜、不半算", () => {
    expect(crossoverSides([[0.1, 0.2], [0.3, 0.4]], [[0.1, 0.2]])).toBeNull();
    expect(crossoverSides([[0.1, 0.2]], [[0.1]])).toBeNull();
  });
});
