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

test("選中劇本時，左側劇本庫（含建立劇本入口）與右側詳細頁同時可見", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  // 右側詳細頁的內容
  await expect(page.getByText(`$${sample.meta.spot.toFixed(2)}`)).toBeVisible();
  // 左側劇本庫：另一個劇本的卡片、以及建立劇本入口都還在——不是整頁
  // 替換。建立劇本表單本身收合（#75），要按過頂部入口才看得到欄位。
  await expect(page.getByRole("link", { name: /ABC/ })).toBeVisible();
  await page.getByRole("button", { name: "＋ 建立劇本" }).click();
  await expect(page.getByLabel("標的代號")).toBeVisible();
});

test("Spread 淨成本走勢：桌面 hover 資料點顯示 tooltip（MVP V3／#106）", async ({ page }) => {
  await routeTwoScenarios(page);
  const history = {
    entries: [
      { analyzed_at: "2026-07-01T21:30:00-04:00", spot: 100.0, cost: 5.0,
       baseline_return: 0.3, rank_in_expiry: 2 },
      { analyzed_at: "2026-07-15T21:30:00-04:00", spot: 99.0, cost: 5.5,
       baseline_return: 0.5, rank_in_expiry: 1 },
    ],
  };
  await page.route("**/api/scenarios/*/history*", (route) =>
    route.fulfill({ json: history }));

  await page.goto("/#/s/s1");
  const chart = page.locator(".card").filter({ hasText: "Spread 淨成本走勢" }).first();
  await chart.getByText("Spread 淨成本走勢").click();
  const point = chart.getByRole("button", { name: /2026-07-01/ });
  await expect(point).toBeVisible();

  // 桌面滑鼠移到資料點上（hover，非點擊）就該看到 tooltip；移開後消失。
  await expect(chart.getByText(/日期 2026-07-01/)).not.toBeVisible();
  await point.hover();
  await expect(chart.getByText(/日期 2026-07-01/)).toBeVisible();
  await expect(chart.getByText(/淨成本 \$5\.00/)).toBeVisible();

  await page.mouse.move(0, 0);
  await expect(chart.getByText(/日期 2026-07-01/)).not.toBeVisible();
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

test("左右比例約 20/80，不是置中的窄直欄", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/");

  const library = await page.locator(".library-pane").boundingBox();
  const detail = await page.locator(".detail-pane").boundingBox();
  if (!library || !detail) throw new Error("版面沒有渲染出兩欄");

  // 「約」20/80——不要求精確到小數點，但要跟置中窄直欄（原本兩側大片
  // 空白、內容欄遠小於 20%）明顯不同，也不該被 CSS 下限卡死成遠超過
  // 20% 的固定寬度（回歸測試：#72 code review 抓到的原始寫法在 900～
  // 1400px 這段桌面寬度會被 280px 下限卡到超過 30%）。
  const ratio = library.width / (library.width + detail.width);
  expect(ratio).toBeGreaterThan(0.15);
  expect(ratio).toBeLessThan(0.28);
});

test("瀏覽器上一頁／下一頁在桌面版仍然正確切換劇本", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/");
  await expect(page.getByText(/選擇左側的劇本/)).toBeVisible();

  await page.getByRole("link", { name: /XYZ/ }).click();
  await expect(page).toHaveURL(/#\/s\/s1$/);
  await page.getByRole("link", { name: /ABC/ }).click();
  await expect(page).toHaveURL(/#\/s\/s2$/);

  await page.goBack();
  await expect(page).toHaveURL(/#\/s\/s1$/);
  await expect(page.getByRole("link", { name: /XYZ/ }))
    .toHaveAttribute("aria-current", "page");

  await page.goBack();
  await expect(page).not.toHaveURL(/#\/s\//);
  await expect(page.getByText(/選擇左側的劇本/)).toBeVisible();

  await page.goForward();
  await expect(page).toHaveURL(/#\/s\/s1$/);
  await expect(page.getByText(`$${sample.meta.spot.toFixed(2)}`)).toBeVisible();
});

test("工具列順序：建立劇本 → 垃圾桶 → 重新整理（TR6／#91 需求方核准版面）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/");
  // 等開站那輪批次刷新跑完，避免撞上「刷新中……」互斥文字的瞬間。
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /重新整理|刷新中/ }))
    .toHaveText("重新整理");

  const buttons = await page.locator("header.toolbar button").allTextContents();
  expect(buttons.map((t) => t.trim())).toEqual(["＋ 建立劇本", "垃圾桶", "重新整理"]);
});

test("垃圾桶：左側面板整個換成垃圾桶清單（TR6／#91）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();

  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();

  // 左側面板整個換成垃圾桶清單——不是彈出新視窗或新分頁。
  await expect(page.locator(".library-pane").getByRole("heading", { name: "垃圾桶" }))
    .toBeVisible();
  await expect(page.getByRole("link", { name: /XYZ/ })).not.toBeVisible();
  // 右側工作區沿用既有「有沒有選中劇本」的邏輯——垃圾桶本身不是劇本，
  // 網址不再指向任何劇本 id，右側自然落回既有空狀態，不是被特別接管。
  await expect(page.getByText(/選擇左側的劇本/)).toBeVisible();

  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
});

test("桌面版批次選取移入垃圾桶：勾兩個、確認後兩者都消失（TR6／#91）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/scenarios/*/archive", (route) =>
    route.fulfill({ json: { archived: true } }));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /ABC/ })).toBeVisible();

  await page.getByRole("button", { name: "選取要移入垃圾桶的劇本" }).click();
  await page.getByRole("link", { name: /XYZ/ }).click();
  await page.getByRole("link", { name: /ABC/ }).click();
  await expect(page.getByText("已選 2 個")).toBeVisible();
  await page.getByRole("button", { name: "移入垃圾桶" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(0);
});

test("桌面版垃圾桶：還原一個、永久刪除另一個（TR4／#92）", async ({ page }) => {
  const trashedA = libraryRow({
    id: "s1", symbol: "XYZ", target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" });
  const trashedB = libraryRow({
    id: "s2", symbol: "ABC", target_month: "2028-06",
    archived_at: "2026-08-04T00:00:00+00:00" });
  let archived = [trashedA, trashedB];

  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [] }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: archived }));
  await page.route("**/api/scenarios/s1/restore", (route) => {
    archived = archived.filter((r) => r.id !== "s1");
    return route.fulfill({ json: { restored: true } });
  });
  await page.route("**/api/scenarios/s2", (route) => {
    archived = archived.filter((r) => r.id !== "s2");
    return route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/");
  await expect(page.getByText(/還沒有劇本/)).toBeVisible();
  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  const library = page.locator(".library-pane");
  await expect(library.getByText("XYZ", { exact: true })).toBeVisible();
  await expect(library.getByText("ABC", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "還原 XYZ 2028-05" }).click();
  await expect(library.getByText("XYZ", { exact: true })).not.toBeVisible();
  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();

  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  await page.getByRole("button", { name: "永久刪除 ABC 2028-06" }).click();
  const sheet = page.getByRole("alertdialog");
  await expect(sheet).toContainText("ABC");
  await expect(sheet).toContainText("2028-06");
  await sheet.getByRole("button", { name: "永久刪除" }).click();

  await expect(library.getByText("垃圾桶是空的。")).toBeVisible();
});

test("桌面版垃圾桶批次操作：全選後批次還原（TR5／#93）", async ({ page }) => {
  const trashedA = libraryRow({
    id: "s1", symbol: "XYZ", target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" });
  const trashedB = libraryRow({
    id: "s2", symbol: "ABC", target_month: "2028-06",
    archived_at: "2026-08-04T00:00:00+00:00" });
  let archived = [trashedA, trashedB];

  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [] }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: archived }));
  await page.route("**/api/scenarios/s1/restore", (route) => {
    archived = archived.filter((r) => r.id !== "s1");
    return route.fulfill({ json: { restored: true } });
  });
  await page.route("**/api/scenarios/s2/restore", (route) => {
    archived = archived.filter((r) => r.id !== "s2");
    return route.fulfill({ json: { restored: true } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  const library = page.locator(".library-pane");
  await expect(library.getByText("XYZ", { exact: true })).toBeVisible();
  await expect(library.getByText("ABC", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "全選" }).click();
  await expect(page.getByText("已選 2 個")).toBeVisible();
  await page.getByRole("button", { name: "還原已選" }).click();

  await expect(library.getByText("垃圾桶是空的。")).toBeVisible();
  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByRole("link", { name: /XYZ/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /ABC/ })).toBeVisible();
});

test("劇本庫卡片瘦身：固定左側欄視窗一次看到的劇本數比舊版大卡片多" +
     "（決策 K／#108）", async ({ page }) => {
  // 只驗結構性密度（能不能在左側欄一屏塞進更多列），不驗任何像素間距
  // 數值——跟手機版 smoke.spec.ts「Compact row 的密度」那條案例同一套
  // 測試哲學（spec #77〈Testing Decisions〉）。舊版 `.card`（padding
  // 16px、六列各自 12px 分隔線）在這個 20% 左側欄寬度、800px 高的桌面
  // 視窗下，一屏通常只放得下 2～3 張；決策 K 改用跟手機版一樣的三層
  // compact row 後應該明顯更多，門檻取一個舊版無論如何都到不了、但
  // 留有安全餘裕的數字。
  const rows = Array.from({ length: 12 }, (_, i) =>
    libraryRow({ id: `s${i}`, symbol: `SYM${i}`,
                 latest_analyzed_at: null, best_return: null }));
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: rows }));
  await page.route("**/api/scenarios/*/refresh", (route, req) =>
    route.fulfill({ json: rows.find((r) => req.url().includes(`/${r.id}/`)) }));

  await page.goto("/");
  await expect(page.getByRole("listitem").first()).toBeVisible();

  const library = (await page.locator(".library-pane").boundingBox())!;
  const cards = await page.locator("li.compact-card").all();
  let visibleWithoutScrolling = 0;
  for (const card of cards) {
    const box = await card.boundingBox();
    if (box && box.y >= library.y
        && box.y + box.height <= library.y + library.height) {
      visibleWithoutScrolling += 1;
    }
  }

  expect(visibleWithoutScrolling).toBeGreaterThanOrEqual(5);
});
