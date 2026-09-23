/**
 * SW-08（#338）：靜態掃描——圖表／資料視覺元件的原始碼（不是
 * `styles.css`，那份檔案裡的舊名稱本來就依 SW-01 的 expand 策略保留
 * 給其他還沒輪到換皮的畫面用）不再直接引用任何 OG（Obsidian Gold）
 * 時代的 CSS 變數名稱，也不含任何寫死的「gold」字面色。手法沿用既有
 * `obsidianGold.test.ts`／`seedWarm.test.ts`：直接讀原始碼文字比對，
 * 不依賴 jsdom 真的解析 CSS 變數鏈。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** SW-08 票面點名的圖表／資料視覺元件；純函式檔案（`heatmap.ts` 等）
 *  一併掃，色彩邏輯常常寫在那裡而不是渲染元件本身。 */
// SW-12（#342）：`CostSparkline.tsx`／`sparkline.ts`／`SpreadHistory.tsx`／
// `DesktopSpreadHistory.tsx`／`spreadHistory.ts` 五個檔案隨 Spread 淨
// 成本走勢功能整個退休移除，已從這份清單移除。
const CHART_FILES = [
  "src/Heatmap.tsx", "src/heatmap.ts",
  "src/PriceLadder.tsx",
  "src/IvHistory.tsx", "src/IvTrend.tsx", "src/ivHistoryChart.ts",
  "src/CandidatePool.tsx",
  "src/RawData.tsx",
  "src/Diagnostics.tsx",
];

/** 舊（OG）時代名稱——見 `styles.css` `:root` 區塊「既有消費端讀的
 *  舊名稱」那一段（`--bg-elevated`／`--separator`／`--label`／
 *  `--label-secondary`／`--label-tertiary`／`--tint`／`--green`／
 *  `--red`／`--orange`／`--yellow`），加上更早一輪的 base primitives
 *  （`--panel`／`--panel-2`／`--panel-3`／`--text`／`--text-2`／
 *  `--text-3`）與裸 `--accent`（新 primitives 一律讀 `--acc`，`--accent`
 *  只留給尚未輪到換皮的舊 class 消費，圖表元件不該再直接讀它）。全部
 *  用 `var\\(--x\\)` 精確比對，避免 `--accent` 誤命中
 *  `--accent-text`／`--accent-soft`／`--accent-hover`／`--on-accent`
 *  這些合法的既有延伸名稱。 */
const OG_TOKENS = [
  "--bg-elevated", "--separator", "--label", "--label-secondary",
  "--label-tertiary", "--tint", "--green", "--red", "--orange", "--yellow",
  "--panel", "--panel-2", "--panel-3", "--text", "--text-2", "--text-3",
  "--accent",
];

describe("SW-08（#338）：圖表元件原始碼不再直接引用 OG token 名", () => {
  for (const path of CHART_FILES) {
    const src = readFileSync(resolve(process.cwd(), path), "utf-8");

    it(`${path} 不含任何 gold 字面色`, () => {
      expect(src.toLowerCase()).not.toMatch(/gold/);
    });

    for (const token of OG_TOKENS) {
      it(`${path} 不直接引用 var(${token})`, () => {
        const pattern = new RegExp(`var\\(${token}(?:[,)])`);
        expect(src).not.toMatch(pattern);
      });
    }
  }
});
