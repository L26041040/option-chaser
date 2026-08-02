import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Playwright 的 ESM 載入器要求 JSON import attribute；直接讀檔避免版本差異。
const sample = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../contracts/analysis_sample.json", import.meta.url)),
    "utf-8",
  ),
);

const view = sample as unknown as {
  meta: { spot: number; source: string };
  baseline_expiry: string;
  results: { status: string; expiry_top10?: { expiry: string; candidates: { baseline_return: number }[] }[] }[];
};

test("手機開站 → 跑分析 → 顯示引擎算出的數字", async ({ page }) => {
  await page.route("**/api/analyze", (route) =>
    route.fulfill({ json: view }),
  );

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Option Chaser" })).toBeVisible();

  await page.getByRole("button", { name: "跑一次分析" }).click();

  await expect(page.getByText(`$${view.meta.spot.toFixed(2)}`)).toBeVisible();
  await expect(page.getByText(view.baseline_expiry)).toBeVisible();

  const top = view.results.find((r) => r.status === "ok" && r.expiry_top10)!
    .expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!.candidates[0];
  await expect(
    page.getByText(`${(top.baseline_return * 100).toFixed(1)}%`),
  ).toBeVisible();

  // 資料來源可見＝部署後一眼確認 Cboe 是否打得通
  await expect(page.getByText(new RegExp(`資料來源 ${view.meta.source}`))).toBeVisible();
});

test("上游掛掉時顯示錯誤，不是白畫面", async ({ page }) => {
  await page.route("**/api/analyze", (route) =>
    route.fulfill({ status: 502, json: { detail: "兩個資料源都抓不到" } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "跑一次分析" }).click();
  await expect(page.getByRole("alert")).toContainText("兩個資料源都抓不到");
});
