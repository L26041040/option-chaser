import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * 桌面版真正的 master/detail（#72）：左側劇本庫常駐、右側工作區顯示
 * 詳細內容，約 20/80。只在這個檔案跑（見 `playwright.config.ts` 的
 * `Desktop` 專案），驗證的是寬螢幕特有的行為——手機版整頁替換的既有
 * 假設仍由 `smoke.spec.ts`／`iPhone` 專案負責，兩邊不共用案例。
 */
const sample: any = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../contracts/analysis_sample.json", import.meta.url)),
    "utf-8",
  ),
);

const sampleRow = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../contracts/scenario_row_sample.json", import.meta.url)),
    "utf-8",
  ),
);

function libraryRow(overrides: Record<string, unknown> = {}) {
  return {
    ...sampleRow,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 5.67,
    target_anchor: "2026-09-18", days_to_anchor: 45,
    ...overrides,
  };
}

const rowA = libraryRow({ id: "s1", symbol: "XYZ" });
const rowB = libraryRow({ id: "s2", symbol: "ABC", best_return: 1.23 });

async function routeTwoScenarios(page: import("@playwright/test").Page) {
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [rowA, rowB] }));
  await page.route("**/api/scenarios/s1", (route) =>
    route.fulfill({ json: { ...rowA, latest_result: sample } }));
  await page.route("**/api/scenarios/s2", (route) =>
    route.fulfill({ json: { ...rowB, latest_result: sample } }));
  // 開站的批次刷新（時機一）兩個劇本各打一次 /refresh——各自回傳
  // 自己那筆，不能共用同一個回應：那樣兩個劇本的清單列會被同一份
  // 資料蓋掉，其中一個劇本的卡片就從清單上「消失」了。
  await page.route("**/api/scenarios/s1/refresh", (route) =>
    route.fulfill({ json: rowA }));
  await page.route("**/api/scenarios/s2/refresh", (route) =>
    route.fulfill({ json: rowB }));
}

test("選中劇本時，左側劇本庫（含建立表單）與右側詳細頁同時可見", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  // 右側詳細頁的內容
  await expect(page.getByText(`$${sample.meta.spot.toFixed(2)}`)).toBeVisible();
  // 左側劇本庫：另一個劇本的卡片、以及建立表單都還在——不是整頁替換
  await expect(page.getByRole("link", { name: /ABC/ })).toBeVisible();
  await expect(page.getByLabel("標的代號")).toBeVisible();
});

test("目前選中的劇本在左側清單有明確的選中狀態", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  const selected = page.getByRole("link", { name: /XYZ/ });
  const other = page.getByRole("link", { name: /ABC/ });
  await expect(selected).toHaveAttribute("aria-current", "page");
  await expect(other).not.toHaveAttribute("aria-current", "page");
});

test("未選任何劇本時，右側工作區顯示空狀態；左側清單仍可操作", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/");

  await expect(page.getByText(/選擇左側的劇本/)).toBeVisible();
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
});

test("可以直接點另一個劇本切換，不必先返回劇本庫", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");
  await expect(page.getByText(`$${sample.meta.spot.toFixed(2)}`)).toBeVisible();

  await page.getByRole("link", { name: /ABC/ }).click();

  await expect(page).toHaveURL(/#\/s\/s2$/);
  // 切換後左側清單依然完整（沒有被整頁替換掉），且選中狀態換了一個
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /ABC/ }))
    .toHaveAttribute("aria-current", "page");
});
