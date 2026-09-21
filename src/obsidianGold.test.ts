/**
 * OG-01（#317）Foundations 驗收——已於 SW-01（#331，Seed Warm）取代。
 * 原本逐一比對 `:root`（深色）／`@media (prefers-color-scheme: light)`
 * （淺色）兩個區塊的 token hex，兩個前提本票都不再成立：Seed Warm
 * 只有單一 `:root`，`prefers-color-scheme` 分支整個移除（見
 * SEED-WARM-SPEC-001／#330 Implementation Decisions「淺色唯一」）。
 *
 * 依 SW-01（#331）AC「obsidianGold.test.ts 標記為待 SW-09 刪除（本票
 * 不刪，避免 expand 階段紅燈），但其中與淺色分支相關的斷言先移除」
 * ——保留檔案（歷史沿革可追溯）但清空到不再斷言任何已作廢的顏色
 * 假設，SW-09 contract 階段會整份刪除。新的 token 驗收見
 * `seedWarm.test.ts`。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("OG-01：Obsidian Gold token 值（已作廢，待 SW-09 刪除）", () => {
  it("已由 seedWarm.test.ts 取代——這裡只確認 styles.css 仍然存在", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");
    expect(css.length).toBeGreaterThan(0);
  });
});
