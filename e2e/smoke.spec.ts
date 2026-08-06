import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Playwright 的 ESM 載入器要求 JSON import attribute；直接讀檔避免版本差異。
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

const view = sample as unknown as {
  meta: { spot: number; source: string; target_move: number };
  params: { target_price: number; target_month: string };
  baseline_expiry: string;
  results: { status: string; expiry_top10?: { expiry: string; candidates: { baseline_return: number }[] }[] }[];
};

test.beforeEach(async ({ page }) => {
  // V3 起開站就打劇本清單。E2E 沒有後端，預設回空清單；需要劇本的
  // 測試自己覆寫這條路由。
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
});

/** 劇本清單列：形狀取自前後端共用的契約樣本，只覆寫測試在意的欄位。 */
function libraryRow(overrides: Record<string, unknown> = {}) {
  return {
    ...sampleRow,
    id: "s1", symbol: "XYZ",
    target_price: view.params.target_price,
    target_month: view.params.target_month,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 5.67,
    target_anchor: "2026-09-18", days_to_anchor: 45,
    ...overrides,
  };
}

/** V8（#56）：原始資料查看區的假回應——不必跟 `sample` 的候選欄位對齊，
 *  只要形狀正確（`store.raw_snapshot_json` 的既有結構）即可渲染。 */
const RAW_DATA = {
  meta: { symbol: "XYZ", spot: view.meta.spot, fetched_at: "2026-08-04T09:30:00-04:00",
         source: "cboe", contract_count: 1 },
  contracts: [{ contract_symbol: "XYZ261016C00110000", option_type: "call",
               strike: 110.0, expiry: "2026-10-16", bid: 3.0, ask: 3.25,
               last: 3.1, volume: 152, open_interest: 830,
               implied_volatility: 0.38 }],
};

/** V9（#57）：Spread 淨成本走勢——三筆假歷史，中間一筆缺席（斷點）。 */
const SPREAD_HISTORY = {
  entries: [
    { analyzed_at: "2026-07-01T21:30:00-04:00", spot: 100.0, cost: 5.0,
     baseline_return: 0.3, rank_in_expiry: 2 },
    { analyzed_at: "2026-07-08T21:30:00-04:00", spot: 101.0, cost: null,
     baseline_return: null, rank_in_expiry: null },
    { analyzed_at: "2026-07-15T21:30:00-04:00", spot: 99.0, cost: 5.5,
     baseline_return: 0.5, rank_in_expiry: 1 },
  ],
};

/** 詳細頁測試共用的路由：清單、單一劇本、刷新、原始資料、Spread 歷史。 */
async function routeLibrary(page: import("@playwright/test").Page, row: unknown) {
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [row] }));
  await page.route("**/api/scenarios/s1", (route) =>
    route.fulfill({ json: { ...(row as object), latest_result: sample } }));
  await page.route("**/api/scenarios/*/refresh", (route) =>
    route.fulfill({ json: row }));
  await page.route("**/api/scenarios/*/raw-data", (route) =>
    route.fulfill({ json: RAW_DATA }));
  await page.route("**/api/scenarios/*/history*", (route) =>
    route.fulfill({ json: SPREAD_HISTORY }));
}

test("清單 → 詳細頁：摘要、主圖、追平價格、候選池（V5／#53）", async ({ page }) => {
  const row = libraryRow();
  await routeLibrary(page, row);

  await page.goto("/");
  await page.getByRole("link", { name: /XYZ/ }).click();

  // 摘要：現價與目標（含所需漲幅）、資料來源——最後這行就是雲端
  // 對 Cboe 可達性的驗證方式
  await expect(page.getByText(`$${view.meta.spot.toFixed(2)}`)).toBeVisible();
  await expect(page.getByText(/\+30\.0%/)).toBeVisible();
  await expect(page.getByText(view.meta.source, { exact: true })).toBeVisible();

  // 主圖：baseline 期第 1 名候選的 Heatmap
  const top = view.results.find((r) => r.status === "ok" && r.expiry_top10)!
    .expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!.candidates[0];
  // V6 起頁面上有很多張 Heatmap（到期日結構裡每個候選收合著一張），
  // 所以主圖的斷言鎖定主圖那一區。
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  await expect(mainChart).toContainText(`${(top.baseline_return * 100).toFixed(1)}%`);
  await expect(mainChart.locator("table.heatmap-table")).toBeVisible();
  // 「現價」在摘要與 Heatmap 錨點列各有一個，這裡要驗的是圖上那個
  await expect(mainChart.locator("table.heatmap-table").getByText("現價")).toBeVisible();

  // 追平價格：契約樣本的 S* 低於目標價＝醒目那一態
  await expect(page.getByText(/Long Call 追平價格/)).toBeVisible();
  await expect(page.getByText(/即勝過此 Spread/)).toBeVisible();

  // 候選池診斷跟著搬進詳細頁（FB4-01／#60）
  await expect(page.getByText("候選池")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("參考價值有限");

  // FB5-04（#65，spec #61）：C 類品質標示——契約樣本本身帶著一筆「買賣
  // 價差偏大」，整條流程（後端契約 → API → 詳細頁）走一次就看得到。
  // 鎖定候選池那張卡：V8（#56）的分析報告區塊（評語／方法論全文）也
  // 提到同一個詞，全頁搜尋會撞到不只一個元素。
  const candidatePool = page.locator(".card").filter({ hasText: "候選池" }).first();
  await expect(candidatePool.getByText("品質標示（不影響入選）")).toBeVisible();
  await expect(candidatePool.getByText("買賣價差偏大")).toBeVisible();

  // 返回劇本庫
  await page.getByRole("link", { name: /劇本庫/ }).click();
  await expect(page.getByRole("heading", { name: "劇本庫" })).toBeVisible();
});

test("進階區：分析報告與原始資料展開才載入（V8／#56）", async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.goto("/#/s/s1");

  // 分析報告：預設收合，展開才看得到內容（不需要額外打 API，資料已在
  // 詳細頁的 view 裡）。
  const report = page.locator(".card").filter({ hasText: "📄 分析報告" }).first();
  await expect(report.getByText("情境分析")).not.toBeVisible();
  await report.getByText("📄 分析報告").click();
  await expect(report.getByText("情境分析")).toBeVisible();
  await expect(report.getByText("風險與代價")).toBeVisible();
  await expect(report.getByText("進場執行")).toBeVisible();
  // ⑦ 免責聲明獨立、不折疊——展開整個進階區就看得到，不必再點一層。
  await expect(report.getByText(/選擇權交易涉及重大風險/)).toBeVisible();

  // 原始資料：展開才打 `/raw-data`，回應內容如實顯示，CSV 連結接得上
  // 後端下載端點。
  const rawData = page.locator(".card")
    .filter({ hasText: "原始資料（當次快照）" }).first();
  await rawData.getByText("原始資料（當次快照）").click();
  await expect(rawData.getByText("cboe")).toBeVisible();
  await expect(rawData.getByText("1 筆")).toBeVisible();
  await expect(rawData.getByText("XYZ261016C00110000")).toBeVisible();
  const downloadLink = rawData.getByRole("link", { name: "下載 CSV" });
  // #69：網址帶著這次分析的時間戳當快取破壞參數，換一輪分析換一個
  // URL，瀏覽器快取不會拿舊 CSV 原樣吐回來。
  await expect(downloadLink).toHaveAttribute(
    "href", `/api/scenarios/s1/raw-data.csv?t=${
      encodeURIComponent("2026-08-04T09:30:00+00:00")}`);
  await expect(downloadLink).toHaveAttribute("download", "");
});

test("Spread 淨成本走勢：展開才抓，日／週／月可切換（V9／#57）", async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.goto("/#/s/s1");

  const history = page.locator(".card").filter({ hasText: "Spread 淨成本走勢" }).first();
  await expect(history.locator("svg")).toHaveCount(0);

  await history.getByText("Spread 淨成本走勢").click();

  // 三筆歷史裡一筆缺席（斷點）——只有兩個資料點畫得出來，折線在缺席
  // 那裡斷開成兩段，不連過去、不畫成 0。
  const chart = history.locator("svg");
  await expect(chart).toBeVisible();
  await expect(chart.locator("circle")).toHaveCount(2);
  await expect(chart.locator("polyline")).toHaveCount(2);

  // 日／週／月切換：預設「日」，點「月」後樣式跟著換，且不重新打 API
  // （sinceRequests 只在展開當下打過一次）。
  const day = history.getByRole("button", { name: "日" });
  const month = history.getByRole("button", { name: "月" });
  await expect(day).toHaveAttribute("aria-pressed", "true");
  await month.click();
  await expect(month).toHaveAttribute("aria-pressed", "true");
  await expect(day).toHaveAttribute("aria-pressed", "false");
});

test("到期日結構：切換到期日 → 就地展開候選（V6／#54）", async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.goto("/#/s/s1");

  const chips = page.locator(".chip-strip button");
  await expect(chips).toHaveCount(view.results[0].expiry_top10!.length);

  // 預設選中 baseline 期，按鈕上帶著該期最高收益
  await expect(page.getByRole("button", { pressed: true }))
    .toContainText(view.baseline_expiry);

  // 切到另一期：清單換成那一期的候選
  const other = view.results[0].expiry_top10!
    .find((g) => g.expiry !== view.baseline_expiry)!;
  await page.getByRole("button", { name: new RegExp(other.expiry) }).click();
  await expect(page.getByRole("button", { pressed: true })).toContainText(other.expiry);

  const row = page.getByRole("listitem").first();
  // 三個價格在收合狀態就看得到
  await expect(row).toContainText("淨成本");
  await expect(row).toContainText("買 $");
  await expect(row).toContainText("賣 $");

  // 就地展開該候選的 Heatmap：主圖不受影響、頁面不跳動
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const before = await mainChart.locator("table").innerText();

  // 先把那一列捲進視野內再量。少了這一步，Playwright 點擊前的自動捲動
  // 本身就會改變 scrollY，量到的兩個值必然相等——那條斷言就永遠是綠的。
  await row.locator("summary").scrollIntoViewIfNeeded();
  const scrollBefore = await page.evaluate(() => window.scrollY);
  expect(scrollBefore).toBeGreaterThan(0);

  await expect(row.locator("table")).toBeHidden();
  await row.locator("summary").click();
  await expect(row.locator("table")).toBeVisible();

  expect(await mainChart.locator("table").innerText()).toBe(before);
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
});

test("到期日按鈕真的橫向並排可滑動，不是換行成好幾列（V6／#54）", async ({ page }) => {
  // 契約樣本只有三期，在手機寬度下塞得下——塞得下就證明不了「可滑動」。
  // 這裡把分組複製成十二期，逼出真正的橫向捲動。
  const group = sample.results[0].expiry_top10[0];
  const many = Array.from({ length: 12 }, (_, i) => ({
    ...group,
    expiry: `2027-${String(i + 1).padStart(2, "0")}-15`,
  }));
  const wide = {
    ...sample,
    baseline_expiry: many[0].expiry,
    results: [{ ...sample.results[0], expiry_top10: many,
                expiry_counts: many.map((g) => [g.expiry, 25]) }],
  };
  const row = libraryRow();
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [row] }));
  await page.route("**/api/scenarios/s1", (route) =>
    route.fulfill({ json: { ...row, latest_result: wide } }));

  await page.goto("/#/s/s1");
  await expect(page.getByRole("button", { pressed: true })).toBeVisible();

  const strip = page.locator(".chip-strip");
  const box = await strip.evaluate((el) => ({
    scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
    height: el.getBoundingClientRect().height,
    chip: (el.firstElementChild as HTMLElement).getBoundingClientRect().height,
  }));
  // 內容比容器寬＝真的要捲；而且整條的高度就是一顆按鈕的高度＝沒有換行
  expect(box.scrollWidth).toBeGreaterThan(box.clientWidth);
  expect(box.height).toBeLessThan(box.chip * 1.6);
  // 頁面本身仍然不橫向捲動
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("詳細頁的 Heatmap 可橫向滑動（手機塞不下七欄）", async ({ page }) => {
  await routeLibrary(page, libraryRow());

  await page.goto("/#/s/s1");
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  await expect(mainChart.locator("table.heatmap-table")).toBeVisible();

  // 內容真的比容器寬（否則「可捲動」是空話），而且頁面本身沒有橫向捲動
  const box = await mainChart.locator(".heatmap-scroll").evaluate((el) => ({
    scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
  }));
  expect(box.scrollWidth).toBeGreaterThan(box.clientWidth);
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
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

  // #75：建立劇本收攏成工具列的頂部入口，預設收合。
  await page.getByRole("button", { name: "＋ 建立劇本" }).click();
  await page.getByLabel("標的代號").fill("tlt");
  await page.getByLabel("目標價位").fill("120");
  // 年月選擇器（#71）不是原生 input：點欄位就地展開，輸入四碼年份，
  // 點月份鈕選定並收合。
  await page.getByLabel("目標年月").click();
  await page.getByLabel("年份").fill("2028");
  await page.getByRole("button", { name: "5 月" }).click();
  // `exact: true`——Playwright 預設子字串比對，"收合建立表單"（頂部
  // 入口的收合態文字，#75）也含「建立」兩字，會撞名。
  await page.getByRole("button", { name: "建立", exact: true }).click();

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
  // 頁面要夠長才捲得動——V5 移除頁面下方的 V1 遺留區塊後，空清單的
  // 劇本庫只有一屏高，捲不動就測不到「釘住」。
  const rows = Array.from({ length: 8 }, (_, i) =>
    libraryRow({ id: `s${i}`, symbol: `SYM${i}`,
                 latest_analyzed_at: null, best_return: null }));
  let listCalls = 0;
  await page.route("**/api/scenarios", (route) => {
    listCalls += 1;
    return route.fulfill({ json: rows });
  });
  await page.route("**/api/scenarios/*/refresh", (route, req) =>
    route.fulfill({ json: rows.find((r) => req.url().includes(`/${r.id}/`)) }));

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

  // #75：建立劇本跟刷新是同一個固定操作列裡的兩個入口——捲到底時
  // 也要按得下去，不能只驗其中一個。
  await page.getByRole("button", { name: "＋ 建立劇本" }).click();
  await expect(page.getByLabel("標的代號")).toBeVisible();
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

  await expect(page.getByRole("status")).toHaveText("1/1");
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
