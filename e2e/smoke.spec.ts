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

const sampleRow = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../contracts/scenario_row_sample.json", import.meta.url)),
    "utf-8",
  ),
);

const view = sample as unknown as {
  meta: { spot: number; source: string };
  baseline_expiry: string;
  results: { status: string; expiry_top10?: { expiry: string; candidates: { baseline_return: number }[] }[] }[];
};

test.beforeEach(async ({ page }) => {
  // V3 起開站就打劇本清單。E2E 沒有後端，預設回空清單；需要劇本的
  // 測試自己覆寫這條路由。
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
});

test("手機開站 → 跑分析 → 顯示引擎算出的數字", async ({ page }) => {
  await page.route("**/api/analyze", (route) =>
    route.fulfill({ json: view }),
  );

  await page.goto("/");
  // V3 起頁面標題是當前畫面（劇本庫），符合 iOS 導覽列慣例；
  // 產品名留在瀏覽器分頁標題，不佔手機畫面高度。
  await expect(page.getByRole("heading", { name: "劇本庫" })).toBeVisible();

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

test("候選池狀態隨分析結果一併顯示（FB4-01／#60）", async ({ page }) => {
  await page.route("**/api/analyze", (route) => route.fulfill({ json: view }));
  await page.goto("/");
  await page.getByRole("button", { name: "跑一次分析" }).click();

  await expect(page.getByText("候選池")).toBeVisible();
  await expect(page.getByText("通過品質過濾", { exact: true })).toBeVisible();
  // 契約樣本實際是 9 筆抓到、8 筆通過、3 對配對。用 n_qualified（＝配對
  // 數 3）當合約數的話這兩個數字會變成 4／3——所以這是防呆的真斷言。
  await expect(page.getByText("9 筆", { exact: true })).toBeVisible();
  await expect(page.getByText("8 筆", { exact: true })).toBeVisible();
  // 每一道品質過濾關卡都要看得到，才知道是誰砍掉的
  for (const stage of ["報價異常", "IV 異常", "OI/成交量不足", "Spread 過寬"]) {
    await expect(page.getByText(stage, { exact: true })).toBeVisible();
  }
  // 契約樣本的 baseline 期只有 1 組有效候選——警示必須出現，
  // 這正是「第 1 名其實是整池僅存者」的情境。
  await expect(page.getByRole("status")).toContainText("參考價值有限");
});

test("劇本庫：建立 → 出現在清單 → 封存後消失（V3／#51）", async ({ page }) => {
  const created = {
    ...sampleRow,
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: null, best_return: null,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };
  // 這條路由要蓋掉 beforeEach 的空清單版本，因此得處理 GET 與 POST 兩種。
  await page.route("**/api/scenarios", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: created })
      : route.fulfill({ json: [] }),
  );
  await page.route("**/api/scenarios/*/archive", (route) =>
    route.fulfill({ json: { archived: true } }),
  );
  // 建立後會自動刷新（V4／#52 的三種時機之二）；這裡回同一列（尚未分析）
  await page.route("**/api/scenarios/*/refresh", (route) =>
    route.fulfill({ json: created }),
  );

  await page.goto("/");
  await expect(page.getByText("劇本庫")).toBeVisible();
  await expect(page.getByText(/還沒有劇本/)).toBeVisible();

  await page.getByLabel("標的代號").fill("tlt");
  await page.getByLabel("目標價位").fill("120");
  await page.getByLabel("目標年月").fill("2028-05");
  await page.getByRole("button", { name: "建立" }).click();

  // 頁面下方的 V1 遺留區塊也有 "TLT" 字樣，因此鎖定清單裡那一張卡。
  const card = page.getByRole("listitem").filter({ hasText: "2028-05" });
  await expect(card.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("653 天")).toBeVisible();
  // 還沒分析過：收益率是「—」、資料時間說尚未分析，而不是假的 0%
  await expect(page.getByText("尚未分析")).toBeVisible();

  await page.getByRole("button", { name: "封存 TLT 2028-05" }).click();
  await expect(page.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText(/還沒有劇本/)).toBeVisible();
});

test("功能列捲動時仍釘在頂部、而且按得到（V3／#51 驗收第 1 項）", async ({ page }) => {
  // 「可點」在 V3 驗不了——當時功能列上唯一的控制項是 disabled 佔位鈕。
  // V4（#52）把刷新接上之後才補得起來，所以這條測試在這一票才完整。
  let listCalls = 0;
  await page.route("**/api/scenarios", (route) => {
    listCalls += 1;
    return route.fulfill({ json: [] });
  });

  await page.goto("/");
  const toolbar = page.getByText("劇本庫");
  await expect(toolbar).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));

  // 先確認頁面真的捲動了——頁面短到不需要捲時，`toBeInViewport()` 恆真，
  // 這條測試就會在功能列根本沒釘住的情況下照樣綠。
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  // 量釘住的那個元素本身（`<header>`），不是裡面的標題——標題的 y 還含
  // 功能列自己的上內距（安全區），量它會得到一個不為 0 的正常值。
  const box = (await page.locator("header.toolbar").boundingBox())!;
  expect(box.y).toBeLessThan(2);
  await expect(toolbar).toBeInViewport();

  // 釘住還不夠——捲到底時按下去要真的送出請求，功能列才算能用
  const before = listCalls;
  await page.getByRole("button", { name: "重新整理" }).click();
  await expect.poll(() => listCalls).toBeGreaterThan(before);
});

/* ---------- V4（#52）：刷新、進度、失敗指引 ---------- */

const pendingRow = {
  ...sampleRow,
  id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
  latest_analyzed_at: null, best_return: null,
  target_anchor: "2028-05-19", days_to_anchor: 653,
};

/** 刷新成功後的同一列：有收益率、資料時間是剛剛。 */
function refreshedRow() {
  return { ...pendingRow, best_return: 2.5,
           latest_analyzed_at: new Date().toISOString() };
}

test("開站自動刷新：進度 → 卡片換成新數字（V4／#52）", async ({ page }) => {
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [pendingRow] }));
  await page.route("**/api/scenarios/*/refresh", async (route) => {
    // 刻意延遲，讓「刷新中」的進度真的看得到——秒回的話這條測試會在
    // 進度根本沒渲染的情況下照樣綠。
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.fulfill({ json: refreshedRow() });
  });

  await page.goto("/");

  await expect(page.getByRole("status")).toHaveText("0/1");
  await expect(page.getByRole("button", { name: "刷新中……" })).toBeDisabled();

  await expect(page.getByText("250.0%")).toBeVisible();
  await expect(page.getByRole("button", { name: "重新整理" })).toBeEnabled();
  await expect(page.getByRole("status")).toBeHidden();
  // 收益率口徑就寫在數字旁邊
  await expect(page.getByText(/最差成交價/)).toBeVisible();
});

test("刷新失敗說明是哪一段，重試就地重來（V4／#52）", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [pendingRow] }));
  await page.route("**/api/scenarios/*/refresh", (route) => {
    attempts += 1;
    return attempts === 1
      ? route.fulfill({ status: 502, json: { detail: {
          stage: "fetch", message: "抓不到 TLT 的報價：來源無回應" } } })
      : route.fulfill({ json: refreshedRow() });
  });

  await page.goto("/");

  // 黃燈不再只是一顆燈：哪一段失敗、為什麼、按哪裡重試，都在卡片上
  await expect(page.getByText("抓不到報價（可稍後重試）")).toBeVisible();
  await expect(page.getByText("來源無回應")).toBeVisible();

  await page.getByRole("button", { name: "重試 TLT 2028-05" }).click();

  await expect(page.getByText("250.0%")).toBeVisible();
  await expect(page.getByText("抓不到報價（可稍後重試）")).toBeHidden();
});

test("久未刷新的資料標成舊資料（V4／#52）", async ({ page }) => {
  const old = new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString();
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [{ ...pendingRow, best_return: 1.0,
                             latest_analyzed_at: old }] }));
  // 刷新一直失敗，所以卡片上留著的就是那份三天前的數字
  await page.route("**/api/scenarios/*/refresh", (route) =>
    route.fulfill({ status: 502, json: { detail: {
      stage: "fetch", message: "抓不到 TLT 的報價：來源無回應" } } }));

  await page.goto("/");

  await expect(page.getByText("100.0%")).toBeVisible();
  await expect(page.getByText("舊資料")).toBeVisible();
});
