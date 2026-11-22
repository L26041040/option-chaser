/**
 * OS-05（#394）：機會搜尋頁 e2e。手機（iPhone）與桌面（Desktop）兩個
 * project 都跑這一份（`playwright.config.ts`）。API 全部以 route 攔截回
 * `contracts/` 的後端樣本——不打任何真實後端。
 *
 * 主流程：從導覽進頁 → 看到入選清單 → 搜尋 → 結果逐檔出現（第二檔是
 * 續跑回來的）→ 切換排序 → 存成劇本 → 進詳細頁；另測來源未設定、
 * 後端 403、Normal 直接打網址，以及兩種寬度都沒有水平捲動。
 */
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function contract(name: string): any {
  return JSON.parse(readFileSync(
    fileURLToPath(new URL(`../contracts/${name}`, import.meta.url)), "utf-8"));
}

const consensus = contract("opportunity_consensus_sample.json");
const search = contract("opportunity_search_sample.json");
const detail = contract("opportunity_detail_sample.json");
const sampleRow = contract("scenario_row_sample.json");
const refreshStatus = contract("opportunity_consensus_status_sample.json");
const refreshUpdate = contract("opportunity_consensus_update_sample.json");

const isDesktop = () => test.info().project.name === "Desktop";

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function routeBase(page: Page, role: "normal" | "superuser" | "superadmin") {
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: { results: [], remaining: [] } }));
  await page.route("**/api/me/usage-summary", (route) =>
    route.fulfill({ json: {
      active_scenarios: 0, max_active_scenarios: 10, quota_exempt: role !== "normal",
      last_activity_at: null, best_return: null, best_return_symbol: null,
      best_return_strategy: null, best_return_target_month: null,
    } }));
  await page.route("**/api/auth/status", (route) => route.fulfill({ json: { role } }));
  // LIVE-T3（#398）分析師資料區塊的狀態（更新流程另有專門的測試）。
  await page.route("**/api/opportunity/consensus/status", (route) =>
    route.fulfill({ json: refreshStatus }));
}

/** 首次搜尋回 AAA（三個家族各一列）並把 EEE 留在 `remaining`；續跑回 EEE 的抓鏈失敗。 */
async function routeSearch(page: Page) {
  const bodies: unknown[] = [];
  await page.route("**/api/opportunity/search", (route) => {
    const body = route.request().postDataJSON();
    bodies.push(body);
    const first = bodies.length === 1;
    return route.fulfill({ json: first
      ? { ...search, failures: [], processed: ["AAA"], remaining: ["EEE"], fetches_used: 1 }
      : { ...search, rows: [], processed: ["EEE"], remaining: [], fetches_used: 1 } });
  });
  return bodies;
}

async function openFromNav(page: Page) {
  await page.goto("/");
  if (isDesktop()) {
    await page.getByRole("navigation", { name: "主導覽" })
      .getByRole("link", { name: "機會搜尋" }).click();
  } else {
    await page.getByRole("navigation", { name: "主要導覽" })
      .getByRole("link", { name: /機會/ }).click();
  }
  await expect(page).toHaveURL(/#\/opportunity$/);
  await expect(page.getByRole("heading", { name: "機會搜尋" })).toBeVisible();
}

test("SU：導覽進頁 → 入選清單 → 搜尋（續跑）→ 切換排序 → 存成劇本 → 詳細頁", async ({ page }) => {
  await routeBase(page, "superuser");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({ json: consensus }));
  const bodies = await routeSearch(page);
  const created = { ...sampleRow, id: "opp-new", symbol: "AAA", target_price: 120,
                    target_month: "2027-09", latest_analyzed_at: null, best_return: null };
  const posted: unknown[] = [];
  await page.route("**/api/scenarios", (route) => {
    if (route.request().method() === "POST") {
      posted.push(route.request().postDataJSON());
      return route.fulfill({ status: 201, json: created });
    }
    return route.fulfill({ json: posted.length ? [created] : [] });
  });
  await page.route("**/api/scenarios/opp-new", (route) =>
    route.fulfill({ json: { ...created, latest_result: null } }));

  await openFromNav(page);

  // 測試資料標示常駐頁首。
  await expect(page.getByRole("banner", { name: "機會搜尋頁首" })
    .getByText("測試資料，非真實市場資料")).toBeVisible();
  const selected = page.getByRole("region", { name: "入選股" });
  await expect(selected.getByRole("listitem", { name: "AAA" })).toBeVisible();
  await expect(selected.getByRole("listitem", { name: "EEE" })).toBeVisible();
  await expect(page.getByRole("region", { name: "共識不夠" })
    .getByRole("listitem", { name: "BBB" })).toBeVisible();
  await expect(page.getByRole("region", { name: "資料不足" })
    .getByRole("listitem", { name: "DDD" })).toBeVisible();
  await noHorizontalScroll(page);

  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  const results = page.getByRole("region", { name: "搜尋結果" });
  await expect(results.getByRole("row", { name: /^AAA / })).toHaveCount(3);
  await expect(page.getByText("已搜尋 2 / 2 檔")).toBeVisible();
  await expect(page.getByRole("region", { name: "搜尋失敗" })
    .getByRole("listitem", { name: "EEE" })).toContainText("抓不到報價");
  expect(bodies).toEqual([{}, { symbols: ["EEE"] }]);
  await expect(page.getByText(
    "此報酬是『分析師平均目標價在目標月份成立時』的條件情境報酬，不是期望值或勝率")).toBeVisible();

  const families = () => results.locator("tbody tr").evaluateAll(
    (rows) => rows.map((r) => r.getAttribute("data-family")));
  expect(await families()).toEqual(["vertical-spread", "single-leg", "butterfly"]);
  await results.getByRole("combobox", { name: "排序" }).selectOption("max_loss");
  expect(await families()).toEqual(["vertical-spread", "butterfly", "single-leg"]);
  expect(bodies).toHaveLength(2);
  await noHorizontalScroll(page);

  const longCall = results.getByRole("row", { name: /^AAA Long Call/ });
  await expect(longCall).toContainText("$5.60");
  // 最大損失與既有詳細頁同口徑：每股（後端每口 560 ÷ 100），不是 $560.00（#395）。
  await expect(longCall.locator('td[data-label="最大損失 / 股"]')).toHaveText("$5.60");
  await expect(longCall).not.toContainText("$560.00");
  await longCall.getByRole("button", { name: "存成劇本" }).click();

  await expect(page).toHaveURL(/#\/s\/opp-new$/);
  expect(posted).toEqual([search.rows[1].scenario]);
  await expect(page.getByRole("heading", { name: "機會搜尋" })).toHaveCount(0);
});

test("超過單次上限：顯示尚有幾檔未搜尋，按鈕對那些檔發起新的一次搜尋", async ({ page }) => {
  await routeBase(page, "superuser");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({ json: consensus }));
  const bodies: unknown[] = [];
  await page.route("**/api/opportunity/search", (route) => {
    bodies.push(route.request().postDataJSON());
    return route.fulfill({ json: bodies.length === 1
      ? { ...search, failures: [], processed: ["AAA"], remaining: [], fetches_used: 1,
          fetch_cap: 1, truncated: true, deferred: ["EEE"] }
      : { ...search, rows: [], processed: ["EEE"], remaining: [], fetches_used: 1 } });
  });

  await page.goto("/#/opportunity");
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await expect(page.getByText("超過單次上限，尚有 1 檔未搜尋")).toBeVisible();
  await expect(page.getByRole("region", { name: "搜尋結果" })
    .getByRole("row", { name: /^AAA / })).toHaveCount(3);
  expect(bodies).toEqual([{}]);
  await noHorizontalScroll(page);

  await page.getByRole("button", { name: "搜尋未搜尋的 1 檔" }).click();
  await expect(page.getByRole("region", { name: "搜尋失敗" })
    .getByRole("listitem", { name: "EEE" })).toBeVisible();
  expect(bodies).toEqual([{}, { symbols: ["EEE"] }]);
  await expect(page.getByText(/超過單次上限/)).toHaveCount(0);
  await expect(page.getByText("已搜尋 2 / 2 檔")).toBeVisible();
});

test("個股詳細資料（#399）：入選與資料不足的列都能打開，有效目標價與每月序列，無水平捲動", async ({ page }) => {
  await routeBase(page, "superuser");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({ json: consensus }));
  const asked: string[] = [];
  await page.route("**/api/opportunity/consensus-detail/*", (route) => {
    const symbol = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop()!);
    asked.push(symbol);
    return route.fulfill({ json: { ...detail, symbol, item: { ...detail.item, symbol } } });
  });

  await page.goto("/#/opportunity");
  const selected = page.getByRole("region", { name: "入選股" });
  await selected.getByRole("button", { name: "AAA 詳細資料" }).click();
  const panel = selected.getByRole("region", { name: "AAA 共識明細" });
  await expect(panel.getByRole("list", { name: "共識數值" })).toContainText("平均目標價$252.86");
  const targets = panel.getByRole("list", { name: /^有效目標價/ });
  await expect(targets.getByRole("listitem")).toHaveCount(detail.effective.length);
  await expect(targets.getByRole("listitem", { name: "Bernstein" })).toContainText("$200.00");
  await expect(panel.getByRole("list", { name: "每月分歧度" }).getByRole("listitem"))
    .toHaveCount(detail.series.length);
  await expect(panel.getByText(`每月分歧度（合格 ${detail.qualified_points} / ${detail.series.length} 個月）`))
    .toBeVisible();
  await noHorizontalScroll(page);

  const thin = page.getByRole("region", { name: "資料不足" });
  await thin.getByRole("button", { name: "DDD 詳細資料" }).click();
  await expect(thin.getByRole("region", { name: "DDD 共識明細" })
    .getByRole("list", { name: "共識數值" })).toBeVisible();
  await noHorizontalScroll(page);
  expect(asked).toEqual(["AAA", "DDD"]);

  await selected.getByRole("button", { name: "AAA 詳細資料" }).click();
  await expect(panel).toHaveCount(0);
});

test("來源未設定：顯示「尚未設定分析師資料來源」，沒有搜尋按鈕，不打搜尋端點", async ({ page }) => {
  await routeBase(page, "superadmin");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({ json: {
    ...consensus,
    source: { configured: false, name: null, is_fixture: false },
    universe: { ...consensus.universe, with_data: 0, insufficient: 0,
                coverage: { complete: 0, partial: 0, unknown: 0 }, as_of: null },
    items: [],
    message: "尚未設定分析師資料來源",
  } }));
  let searched = 0;
  await page.route("**/api/opportunity/search", (route) => {
    searched += 1;
    return route.fulfill({ status: 409, json: { detail: "尚未設定分析師資料來源" } });
  });

  await page.goto("/#/opportunity");
  await expect(page.getByRole("heading", { name: "尚未設定分析師資料來源" })).toBeVisible();
  await expect(page.getByRole("button", { name: "搜尋選擇權" })).toHaveCount(0);
  await expect(page.getByText("測試資料，非真實市場資料")).toHaveCount(0);
  await noHorizontalScroll(page);
  expect(searched).toBe(0);
});

test("後端拒絕（403）：照實顯示後端訊息，沒有清單也沒有搜尋按鈕", async ({ page }) => {
  await routeBase(page, "superuser");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({
    status: 403, json: { detail: "機會搜尋目前只開放 Super User／Super Admin" } }));

  await page.goto("/#/opportunity");
  await expect(page.getByRole("alert"))
    .toContainText("機會搜尋目前只開放 Super User／Super Admin");
  await expect(page.getByRole("region", { name: "入選股" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "搜尋選擇權" })).toHaveCount(0);
});

test("Normal：導覽沒有機會搜尋入口；直接打網址導回首頁、不打機會搜尋端點", async ({ page }) => {
  await routeBase(page, "normal");
  let hit = 0;
  await page.route("**/api/opportunity/**", (route) => {
    hit += 1;
    return route.fulfill({ status: 403, json: { detail: "forbidden" } });
  });

  await page.goto("/#/opportunity");
  await expect(page).toHaveURL(/#\/$/);
  const nav = isDesktop()
    ? page.getByRole("navigation", { name: "主導覽" })
    : page.getByRole("navigation", { name: "主要導覽" });
  await expect(nav.getByRole("link", { name: "劇本庫" })).toBeVisible();
  await expect(nav.getByRole("link", { name: /機會/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "機會搜尋" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "更新分析師資料" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /重試/ })).toHaveCount(0);
  expect(hit).toBe(0);
});

// ---------- LIVE-T3（#398）：更新分析師資料與重試 ----------

test("SU：更新分析師資料依 remaining 自動續跑到完；冷卻中的重試停用、時間到按下真的重試", async ({ page }) => {
  // GGG 在樣本裡 12:53:20 失敗、13:08:20 才能重試。
  await page.clock.install({ time: new Date("2026-09-28T13:00:00Z") });
  await routeBase(page, "superuser");
  let consensusLoads = 0;
  await page.route("**/api/opportunity/consensus", (route) => {
    consensusLoads += 1;
    return route.fulfill({ json: consensus });
  });
  const bodies: unknown[] = [];
  await page.route("**/api/opportunity/consensus/update", (route) => {
    bodies.push(route.request().postDataJSON());
    const n = bodies.length;
    return route.fulfill({ json: n === 1
      ? refreshUpdate
      : { ...refreshUpdate, remaining: [],
          progress: { ...refreshUpdate.progress, done: 56, failed: 1, pending: 0 } } });
  });

  await page.goto("/#/opportunity");
  const panel = page.getByRole("region", { name: "分析師資料" });
  await expect(panel.getByText("今日 已完成 24／57 檔、失敗 1 檔")).toBeVisible();
  await expect(panel.getByText("資料日 2026-09-28")).toBeVisible();
  await noHorizontalScroll(page);

  await panel.getByRole("button", { name: "更新分析師資料" }).click();
  await expect(panel.getByText("更新完成：已完成 56／57 檔、失敗 1 檔")).toBeVisible();
  expect(bodies).toEqual([{}, {}]);
  await expect.poll(() => consensusLoads).toBe(2);   // 完成後重讀共識清單

  const ggg = panel.getByRole("listitem", { name: "GGG" });
  const retry = ggg.getByRole("button", { name: "重試 GGG" });
  await expect(retry).toBeDisabled();
  await expect(ggg).toContainText("上次失敗，冷卻中，還要約 8 分 20 秒才能重試");
  await noHorizontalScroll(page);

  await page.clock.fastForward("08:21");
  await expect(retry).toBeEnabled();
  await retry.click();
  await expect.poll(() => bodies).toEqual([{}, {}, { symbols: ["GGG"] }]);
});

test("SU：每日上限時更新停下並說明原因；後端拒絕重試時在那一檔下照實顯示", async ({ page }) => {
  await routeBase(page, "superadmin");
  await page.route("**/api/opportunity/consensus", (route) => route.fulfill({ json: consensus }));
  const ready = { ...refreshStatus, symbols: refreshStatus.symbols.map((s: any) =>
    s.symbol === "GGG" ? { ...s, state: "retry_ready", next_retry_at: null,
                            retryable_now: true } : s) };
  await page.route("**/api/opportunity/consensus/status", (route) =>
    route.fulfill({ json: ready }));
  const message = "今日分析師資料的上游呼叫已達每日上限，下一個交易日自動恢復";
  await page.route("**/api/opportunity/consensus/update", (route) => {
    const body = route.request().postDataJSON();
    return body.symbols
      ? route.fulfill({ status: 429, json: { detail: { stage: "consensus_daily_cap", message } } })
      : route.fulfill({ json: { ...refreshUpdate, stopped_reason: "daily_cap", message } });
  });

  await page.goto("/#/opportunity");
  const panel = page.getByRole("region", { name: "分析師資料" });
  await panel.getByRole("button", { name: "更新分析師資料" }).click();
  await expect(panel.getByRole("alert")).toContainText(`已停止（已完成 24／57 檔、失敗 1 檔）：${message}`);

  const ggg = panel.getByRole("listitem", { name: "GGG" });
  await ggg.getByRole("button", { name: "重試 GGG" }).click();
  await expect(ggg.getByRole("alert")).toContainText(message);
  await noHorizontalScroll(page);
});
