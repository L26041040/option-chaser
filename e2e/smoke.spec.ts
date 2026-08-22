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
  results: {
    status: string;
    expiry_top10?: {
      expiry: string;
      candidates: {
        baseline_return: number;
        natural_cost: number;
        legs: { strike: number; ask: number; bid: number }[];
      }[];
    }[];
  }[];
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

test("清單 → 詳細頁：摘要、基準候選、進場成本、主圖、候選池（MVP V3／#103 資訊階層重整）",
   async ({ page }) => {
  const row = libraryRow();
  await routeLibrary(page, row);

  await page.goto("/");
  await page.getByRole("link", { name: /XYZ/ }).click();

  // 摘要：現價與目標（含所需漲幅）、資料來源——最後這行就是雲端
  // 對 Cboe 可達性的驗證方式
  await expect(page.getByText(`$${view.meta.spot.toFixed(2)}`)).toBeVisible();
  // 決策 M（#109）之後，「+30.0%」這個字串在頁面上不再唯一——每一張
  // Heatmap（劇本主圖＋到期日結構裡各候選收合著的那些）的「目標」列
  // 右側標註都會是同一個數字（同一組 spot／target）。摘要那一句用
  // `.row-note` scope 回去，不是隨便挑一個「+30.0%」。
  await expect(page.locator(".row-note").filter({ hasText: "+30.0%" }))
    .toBeVisible();
  await expect(page.getByText(view.meta.source, { exact: true })).toBeVisible();

  // QA 修正：基準候選與進場成本不再是兩張獨立卡片，跟劇本摘要合成
  // 同一張高密度卡。數字一項沒少，只是換了位置。
  const top = view.results.find((r) => r.status === "ok" && r.expiry_top10)!
    .expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!.candidates[0];
  const [buy, sell] = top.legs;
  const summary = page.getByRole("region", { name: "劇本摘要" });
  await expect(summary).toContainText(`買 ${buy.strike} / 賣 ${sell.strike}`);
  await expect(summary).toContainText("第 1 名");
  await expect(summary).toContainText(`${(top.baseline_return * 100).toFixed(1)}%`);
  await expect(summary).toContainText("買腿 Ask");
  await expect(summary).toContainText("賣腿 Bid");
  await expect(summary).toContainText("淨成本");
  await expect(summary).toContainText(`$${top.natural_cost.toFixed(2)}`);
  // 真的只剩一張卡——舊的兩張獨立卡片不存在了
  await expect(page.getByRole("heading", { name: "基準候選" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "進場成本" })).toHaveCount(0);

  // 主圖：只剩 Heatmap 本身——候選身分與報酬已搬到「基準候選」。
  // V6 起頁面上有很多張 Heatmap（到期日結構裡每個候選收合著一張），
  // 所以主圖的斷言鎖定主圖那一區。
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  await expect(mainChart.locator("table.heatmap-table")).toBeVisible();
  // 「現價」在摘要與 Heatmap 錨點列各有一個，這裡要驗的是圖上那個。
  // `exact` 是必要的：QA-FIX-1 之後表頭多了一欄「vs 現價」，非精確
  // 比對會同時命中欄標題與錨點標籤。
  await expect(mainChart.locator("table.heatmap-table")
    .getByText("現價", { exact: true })).toBeVisible();

  // 舊「Long Call 追平價格」獨立卡片已依 spec 決策 E 移除（#103）。
  await expect(page.getByText(/Long Call 追平價格/)).toHaveCount(0);
  await expect(page.getByText(/即勝過此 Spread/)).toHaveCount(0);

  // 候選池診斷跟著搬進詳細頁（FB4-01／#60）
  await expect(page.getByText("候選池")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("參考價值有限");

  // FB5-04（#65，spec #61）：C 類品質標示——契約樣本本身帶著一筆「買賣
  // 價差偏大」，整條流程（後端契約 → API → 詳細頁）走一次就看得到。
  // 鎖定候選池那張卡以求穩定，不依賴全頁只有一個元素帶這段文字。
  const candidatePool = page.locator(".card").filter({ hasText: "候選池" }).first();
  await expect(candidatePool.getByText("品質標示（不影響入選）")).toBeVisible();
  await expect(candidatePool.getByText("買賣價差偏大")).toBeVisible();

  // 返回劇本庫
  await page.getByRole("link", { name: /劇本庫/ }).click();
  await expect(page.getByRole("heading", { name: "劇本庫" })).toBeVisible();
});

test("進階區：分析報告與原始資料展開才載入（V8／#56，MVP V3／#105 四區塊）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.goto("/#/s/s1");

  // 分析報告：預設收合，展開才看得到內容（不需要額外打 API，資料已在
  // 詳細頁的 view 裡）。四區塊固定：Risk / Payoff → Position
  // Sensitivity → Execution → Model & Assumptions（本身也預設收合）。
  const report = page.locator(".card").filter({ hasText: "📄 分析報告" }).first();
  await expect(report.getByText("Risk / Payoff")).not.toBeVisible();
  await report.getByText("📄 分析報告").click();
  await expect(report.getByText("Risk / Payoff")).toBeVisible();
  await expect(report.getByText("Position Sensitivity")).toBeVisible();
  // 精確比對——「Execution」是「Execution Friction」列標籤的子字串。
  await expect(report.getByText("Execution", { exact: true })).toBeVisible();
  await expect(report.getByText("Model & Assumptions")).toBeVisible();
  // Model & Assumptions 是巢狀收合區，外層展開不代表它也展開。
  await expect(report.getByText("Rate used")).not.toBeVisible();
  await report.getByText("Model & Assumptions").click();
  // MVP V3（#112，決策 H）：利率四項——實際數值，不是只說「用了曲線」。
  await expect(report.getByText("Rate used")).toBeVisible();
  await expect(report.getByText("Tenor")).toBeVisible();
  // `exact` 是必要的：同一區塊裡還有「Dividend source」，非精確比對會
  // 同時命中兩個元素而觸發 strict mode violation。
  await expect(report.getByText("Source", { exact: true })).toBeVisible();
  await expect(report.getByText("Curve date")).toBeVisible();
  // 免責聲明獨立、不折疊——展開整個進階區就看得到，不必再點一層。
  await expect(report.getByText(/選擇權交易涉及重大風險/)).toBeVisible();

  // 原始資料：展開才打 `/raw-data`，二層收合（MVP V3／#107 決策 J）——
  // 第一層只有摘要＋CSV 連結，逐筆合約表格要再展開第二層才看得到。
  const rawData = page.locator(".card")
    .filter({ hasText: "原始資料（當次快照）" }).first();
  await rawData.getByText("原始資料（當次快照）").click();
  await expect(rawData.getByText("cboe")).toBeVisible();
  await expect(rawData.getByText("1 筆")).toBeVisible();
  await expect(rawData.getByText("XYZ261016C00110000")).not.toBeVisible();
  const downloadLink = rawData.getByRole("link", { name: "下載 CSV" });
  // #69：網址帶著這次分析的時間戳當快取破壞參數，換一輪分析換一個
  // URL，瀏覽器快取不會拿舊 CSV 原樣吐回來。
  await expect(downloadLink).toHaveAttribute(
    "href", `/api/scenarios/s1/raw-data.csv?t=${
      encodeURIComponent("2026-08-04T09:30:00+00:00")}`);
  await expect(downloadLink).toHaveAttribute("download", "");

  await rawData.getByText("查看逐筆合約資料").click();
  await expect(rawData.getByText("XYZ261016C00110000")).toBeVisible();
});

test("Spread 淨成本走勢：展開才抓，日／週／月可切換（V9／#57，MVP V3／#106 補刻度）",
   async ({ page }) => {
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

  // Y 軸單位與刻度、X 軸日期刻度都在（#106 AC）。
  await expect(chart.getByText("Net Cost ($/share)")).toBeVisible();
  await expect(chart.getByText("2026-07-01")).toBeVisible();
  await expect(chart.getByText("2026-07-15")).toBeVisible();

  // 手機 tap 資料點：顯示含日期與淨成本的 tooltip（#106 AC，手機
  // viewport）。這個專案（`iPhone`）本身就是觸控裝置模擬，點擊觸發的
  // 是與真機點按同一條 `onClick` 路徑——不用 `.tap()`（需要額外的
  // `hasTouch` 事件鏈，本專案觸控裝置上點擊本來就走 click，不特別
  // 區分手勢來源）。
  await expect(chart.getByText(/日期 2026-07-01/)).not.toBeVisible();
  await chart.getByRole("button", { name: /2026-07-01/ }).click();
  await expect(chart.getByText(/日期 2026-07-01/)).toBeVisible();
  await expect(chart.getByText(/淨成本 \$5\.00/)).toBeVisible();

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

  // QA-FIX-1 sticky 兩端：手機視窗一定捲得動（上面剛驗過），捲到最右
  // 之後左側價格與最右 ±% 都必須還在可視範圍內。
  await mainChart.locator(".heatmap-scroll")
    .evaluate((el) => { el.scrollLeft = el.scrollWidth; });
  const viewport = (await mainChart.locator(".heatmap-scroll").boundingBox())!;
  const firstRow = mainChart.locator("table.heatmap-table tbody tr").first();
  const priceBox = (await firstRow.locator("th.heatmap-price").boundingBox())!;
  const moveBox = (await firstRow.locator("td.heatmap-move-pct").boundingBox())!;
  expect(priceBox.x).toBeGreaterThanOrEqual(viewport.x - 1);
  expect(moveBox.x + moveBox.width)
    .toBeLessThanOrEqual(viewport.x + viewport.width + 1);
});

test("Heatmap 價格列右側 ±% 標註：手機 viewport 不需額外互動就看得到" +
     "（短格式，決策 M／#109）", async ({ page }) => {
  await routeLibrary(page, libraryRow());

  await page.goto("/#/s/s1");
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  // 不點、不長按——AC 明文手機 viewport 下這個資訊「不需額外互動」
  // 就看得到；手機優先預設顯示短格式（CSS 媒體查詢切換，見
  // `styles.css` 的 `.heatmap-move-pct-short`），數字取自契約樣本
  // baseline 候選的 `matrix.prices`（spot=100、target=130 → +30%）。
  // 完整／短格式兩個 span 都在 DOM 裡（CSS 切換顯示），所以斷言要指名
  // 看得見的那一個——對整個 `<td>` 下 toHaveText 會拿到兩者相連的
  // textContent。
  const moveCellOf = (tag: string) =>
    table.locator("tr").filter({ hasText: tag }).locator("td.heatmap-move-pct");
  const shortOf = (tag: string) =>
    moveCellOf(tag).locator(".heatmap-move-pct-short");
  await expect(shortOf("目標")).toHaveText("+30%");
  await expect(shortOf("目標")).toBeVisible();
  await expect(shortOf("現價")).toHaveText("+0%");
  // 完整格式（桌面版才顯示）此時不可見，證明真的是短格式在生效，
  // 不是兩種格式一起攤開來看。
  await expect(moveCellOf("目標").locator(".heatmap-move-pct-full"))
    .not.toBeVisible();

  // QA-FIX-1：手機版同樣是「價格 → 日期格 → ±%」，±% 在最右邊，
  // 不是塞在左側價格欄裡。
  const firstRow = table.locator("tbody tr").first();
  const priceBox = (await firstRow.locator("th.heatmap-price").boundingBox())!;
  const moveBox = (await firstRow.locator("td.heatmap-move-pct").boundingBox())!;
  expect(moveBox.x).toBeGreaterThan(priceBox.x);
});

test("Crossover Boundary（#116）：手機 viewport 不需額外互動就看得到圖例與邊界標示，" +
     "既有橫向捲動不受影響", async ({ page }) => {
  await routeLibrary(page, libraryRow());

  await page.goto("/#/s/s1");
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  // 不點、不長按——契約樣本 baseline 候選是 Spread，`comparator` 非 null，
  // 圖例與邊界標示直接渲染，不需要任何互動觸發。
  await expect(mainChart.getByText(/格子是 Spread 報酬率/)).toBeVisible();
  await expect(mainChart.getByText(/報酬相等的分界/)).toBeVisible();
  await expect(mainChart.getByText(/Long Call|Long Put/).first()).toBeVisible();
  // QA 修正：兩側各是誰較高必須明講，而且方向由實際矩陣算出來
  // ——所以只鎖「X 較高，Y 較高」這個句型，不寫死是哪一端。
  await expect(mainChart.locator(".crossover-sides")).toBeVisible();
  await expect(mainChart.locator(".crossover-sides"))
    .toHaveText(/Spread 較高，.*(Long Call|Long Put) 較高/);
  await expect(table.locator("td.heatmap-crossover-cell").first()).toBeVisible();

  // 疊加邊界標示不能破壞既有的橫向捲動與兩端 sticky 欄位行為
  // （同上一個測試「詳細頁的 Heatmap 可橫向滑動」）。
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

  // 手機版（MVP-v2／#77、#81）：建立劇本入口在 Dashboard 佔位區下方，
  // 不在工具列——#75 的工具列頂部入口自此縮限成桌面現狀。預設收合。
  await page.getByRole("button", { name: "＋ 新增劇本" }).click();
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

test("批次選取移入垃圾桶：勾兩個、確認後兩者都消失（TR6／#91）", async ({ page }) => {
  const rowA = libraryRow({ id: "s1", symbol: "TLT" });
  const rowB = libraryRow({ id: "s2", symbol: "SPY" });
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [rowA, rowB] }));
  await page.route("**/api/scenarios/s1/refresh", (route) =>
    route.fulfill({ json: rowA }));
  await page.route("**/api/scenarios/s2/refresh", (route) =>
    route.fulfill({ json: rowB }));
  await page.route("**/api/scenarios/*/archive", (route) =>
    route.fulfill({ json: { archived: true } }));

  await page.goto("/");
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "選取要移入垃圾桶的劇本" }).click();
  await page.getByRole("link", { name: /TLT/ }).click();
  await page.getByRole("link", { name: /SPY/ }).click();
  await expect(page.getByText("已選 2 個")).toBeVisible();
  await page.getByRole("button", { name: "移入垃圾桶" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(0);
});

test("垃圾桶入口可以點進去，返回鍵回到劇本庫（TR6／#91）", async ({ page }) => {
  const rowA = libraryRow({ id: "s1", symbol: "TLT" });
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [rowA] }));
  await page.route("**/api/scenarios/s1/refresh", (route) =>
    route.fulfill({ json: rowA }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: [] }));

  await page.goto("/");
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  await expect(page.getByRole("heading", { name: "垃圾桶" })).toBeVisible();
  await expect(page.getByText("垃圾桶是空的。")).toBeVisible();

  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
});

test("垃圾桶：還原一個、永久刪除另一個（TR4／#92）", async ({ page }) => {
  const trashedA = libraryRow({
    id: "s1", symbol: "TLT", target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" });
  const trashedB = libraryRow({
    id: "s2", symbol: "SPY", target_month: "2028-06",
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
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();

  // 還原 TLT：從垃圾桶消失，回到劇本庫能看到它
  await page.getByRole("button", { name: "還原 TLT 2028-05" }).click();
  await expect(page.getByText("TLT", { exact: true })).not.toBeVisible();
  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();

  // 永久刪除 SPY：需要二次確認，確認畫面列出具體 ticker 與 target month
  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "永久刪除 SPY 2028-06" }).click();
  const sheet = page.getByRole("alertdialog");
  await expect(sheet).toContainText("SPY");
  await expect(sheet).toContainText("2028-06");
  await sheet.getByRole("button", { name: "永久刪除" }).click();

  await expect(page.getByText("SPY", { exact: true })).not.toBeVisible();
  await expect(page.getByText("垃圾桶是空的。")).toBeVisible();
});

test("垃圾桶批次操作：全選後批次永久刪除，確認畫面列出全部待刪清單與數量（TR5／#93）",
   async ({ page }) => {
  const trashedA = libraryRow({
    id: "s1", symbol: "TLT", target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" });
  const trashedB = libraryRow({
    id: "s2", symbol: "SPY", target_month: "2028-06",
    archived_at: "2026-08-04T00:00:00+00:00" });
  let archived = [trashedA, trashedB];

  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [] }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: archived }));
  await page.route("**/api/scenarios/s1", (route) => {
    archived = archived.filter((r) => r.id !== "s1");
    return route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/scenarios/s2", (route) => {
    archived = archived.filter((r) => r.id !== "s2");
    return route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "垃圾桶", exact: true }).click();
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "全選" }).click();
  await expect(page.getByText("已選 2 個")).toBeVisible();
  await page.getByRole("button", { name: "永久刪除已選" }).click();

  const sheet = page.getByRole("alertdialog");
  await expect(sheet).toContainText("2 個劇本");
  await expect(sheet).toContainText("TLT");
  await expect(sheet).toContainText("2028-05");
  await expect(sheet).toContainText("SPY");
  await expect(sheet).toContainText("2028-06");

  await sheet.getByRole("button", { name: "永久刪除" }).click();
  await expect(page.getByText("垃圾桶是空的。")).toBeVisible();
});

test("垃圾桶批次操作：全選後批次還原，兩者都回到劇本庫（TR5／#93）",
   async ({ page }) => {
  const trashedA = libraryRow({
    id: "s1", symbol: "TLT", target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" });
  const trashedB = libraryRow({
    id: "s2", symbol: "SPY", target_month: "2028-06",
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
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "全選" }).click();
  await expect(page.getByText("已選 2 個")).toBeVisible();
  await page.getByRole("button", { name: "還原已選" }).click();

  await expect(page.getByText("垃圾桶是空的。")).toBeVisible();
  await page.getByText("‹ 劇本庫").click();
  await expect(page.getByText("TLT", { exact: true })).toBeVisible();
  await expect(page.getByText("SPY", { exact: true })).toBeVisible();
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

  // 釘住還不夠——捲到底時按下去要真的送出請求，功能列才算能用。
  // 手機版（MVP-v2／#77、#81）工具列上只剩刷新這一個入口——建立劇本
  // 移到 Dashboard 下方、不隨工具列釘住，因此不在這條測試斷言範圍內
  // （#75 的「同一個固定操作列兩個入口」自此是桌面版現狀，見
  // `desktop.spec.ts`／`App.test.tsx` 對應案例）。
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

test("Compact row 刷新失敗時，封存鈕不會疊在重試鈕上（code review 跟進，MVP-v2／#77、#82）",
  async ({ page }) => {
    // 回歸防護：封存鈕原本相對整張卡片定位，`.compact-notice`（失敗
    // 說明＋重試）撐高卡片後，封存鈕會飄到 notice 的右下角、疊在
    // 「重試」上，使用者想點重試卻可能誤觸封存。這裡直接量兩顆按鈕
    // 的真實 bounding box，斷言不重疊——這是唯一能真正抓到這類幾何
    // 回歸的測法，jsdom 不會算真實版面。
    await page.route("**/api/scenarios", (route) =>
      route.fulfill({ json: [pendingRow] }));
    await page.route("**/api/scenarios/*/refresh", (route) =>
      route.fulfill({ status: 502, json: { detail: {
        stage: "fetch", message: "抓不到 TLT 的報價：來源無回應" } } }));

    await page.goto("/");
    const retry = page.getByRole("button", { name: "重試 TLT 2028-05" });
    const archive = page.getByRole("button", { name: "封存 TLT 2028-05" });
    await expect(retry).toBeVisible();
    await expect(archive).toBeVisible();

    const retryBox = (await retry.boundingBox())!;
    const archiveBox = (await archive.boundingBox())!;
    const overlaps = !(
      retryBox.x + retryBox.width <= archiveBox.x ||
      archiveBox.x + archiveBox.width <= retryBox.x ||
      retryBox.y + retryBox.height <= archiveBox.y ||
      archiveBox.y + archiveBox.height <= retryBox.y
    );
    expect(overlaps).toBe(false);
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

test("手機首頁版面順序：Dashboard 佔位 → 新增劇本入口 → 劇本庫（MVP-v2／#77、#81）",
  async ({ page }) => {
    await routeLibrary(page, libraryRow());

    await page.goto("/");
    await expect(page.getByRole("listitem")).toBeVisible();

    const dashboard = page.getByLabel("Dashboard");
    const createToggle = page.getByRole("button", { name: "＋ 新增劇本" });
    // 手機版清單用 compact 版式的容器（`.compact-list`，MVP-v2／#77、
    // #82）。#108 起桌面版 `ScenarioList.tsx` 也沿用同一組 class，但
    // 這個測試檔固定跑在手機 viewport 專案（見 `playwright.config.ts`
    // 的 `testIgnore: /desktop\.spec\.ts$/`），不會抓到桌面版那份。
    const list = page.locator("ul.compact-list");

    await expect(dashboard).toBeVisible();
    await expect(createToggle).toBeVisible();
    await expect(list).toBeVisible();

    // 三段由上而下的順序——不是同時存在就好，順序本身是規格的一部分。
    expect(await dashboard.evaluate((el, other) =>
      !!(el.compareDocumentPosition(other as Node) &
         Node.DOCUMENT_POSITION_FOLLOWING),
      await createToggle.elementHandle())).toBe(true);
    expect(await createToggle.evaluate((el, other) =>
      !!(el.compareDocumentPosition(other as Node) &
         Node.DOCUMENT_POSITION_FOLLOWING),
      await list.elementHandle())).toBe(true);

    // Dashboard 佔位區不放任何數字（需求方裁示：不要自行發明 KPI）。
    await expect(dashboard).not.toContainText(/\d/);
  });

test("新增劇本：點擊就地展開，不換頁、不彈出 modal（MVP-v2／#77、#81）",
  async ({ page }) => {
    await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));

    await page.goto("/");
    const urlBefore = page.url();

    await expect(page.getByLabel("標的代號")).not.toBeVisible();
    await page.getByRole("button", { name: "＋ 新增劇本" }).click();
    await expect(page.getByLabel("標的代號")).toBeVisible();

    // 就地展開：網址沒變、Dashboard 與工具列仍在同一頁上。
    expect(page.url()).toBe(urlBefore);
    await expect(page.getByLabel("Dashboard")).toBeVisible();
    await expect(page.getByText("劇本庫")).toBeVisible();

    // 收合再展開，內容還在（沿用 #75 的既有教訓：面板一律掛著只切換
    // 可見度，不是條件渲染整個卸載重掛）。
    await page.getByLabel("標的代號").fill("tlt");
    await page.getByRole("button", { name: "收合建立表單" }).click();
    await expect(page.getByLabel("標的代號")).not.toBeVisible();
    await page.getByRole("button", { name: "＋ 新增劇本" }).click();
    await expect(page.getByLabel("標的代號")).toHaveValue("tlt");
  });

test("Compact row 的密度：一個手機視窗至少看得到 4 個劇本，不必先捲動（MVP-v2／#77、#82）",
  async ({ page }) => {
    // 只驗結構性密度（能不能在一屏塞進足夠多列），不驗任何像素間距數值
    // ——那種驗法會把設計凍結在這一輪（spec #77〈Testing Decisions〉
    // 明確不做的測試）。舊的大卡片版式一屏通常只放得下 2～3 張。
    const rows = Array.from({ length: 8 }, (_, i) =>
      libraryRow({ id: `s${i}`, symbol: `SYM${i}`,
                   latest_analyzed_at: null, best_return: null }));
    await page.route("**/api/scenarios", (route) => route.fulfill({ json: rows }));
    await page.route("**/api/scenarios/*/refresh", (route, req) =>
      route.fulfill({ json: rows.find((r) => req.url().includes(`/${r.id}/`)) }));

    await page.goto("/");
    await expect(page.getByRole("listitem").first()).toBeVisible();

    const viewportHeight = page.viewportSize()!.height;
    const cards = await page.locator("li.compact-card").all();
    let visibleWithoutScrolling = 0;
    for (const card of cards) {
      const box = await card.boundingBox();
      if (box && box.y >= 0 && box.y + box.height <= viewportHeight) {
        visibleWithoutScrolling += 1;
      }
    }

    expect(visibleWithoutScrolling).toBeGreaterThanOrEqual(4);
  });

test("劇本庫卡片有概覽用的價格欄位：現價／最高／最低（QA 修正）",
   async ({ page }) => {
  // 有填區間的劇本：現價與最高／最低都要在卡片上讀得到，不必點進去
  await page.route("**/api/scenarios", (route) => route.fulfill({
    json: [libraryRow({ spot: 82.11, best_price: 120, worst_price: 100 })] }));
  await page.goto("/");

  const card = page.getByRole("listitem").first();
  await expect(card.locator(".compact-spot")).toHaveText("$82.11");
  await expect(card.locator(".compact-range")).toContainText("最低 $100.00");
  await expect(card.locator(".compact-range")).toContainText("最高 $120.00");
});

test("沒填區間的劇本不會多出一列空的區間行（密度不被空資料吃掉）",
   async ({ page }) => {
  await page.route("**/api/scenarios", (route) => route.fulfill({
    json: [libraryRow({ spot: 82.11, best_price: null, worst_price: null })] }));
  await page.goto("/");

  const card = page.getByRole("listitem").first();
  await expect(card.locator(".compact-spot")).toHaveText("$82.11");
  await expect(card.locator(".compact-range")).toHaveCount(0);
});

test("Compact row 逐項齊全：spec §5 必要欄位一個都沒少（MVP-v2／#77、#82）",
  async ({ page }) => {
    await routeLibrary(page, libraryRow());

    await page.goto("/");
    const card = page.getByRole("listitem").first();
    await expect(card).toBeVisible();

    // 標的／目標價／目標年月／燈號
    await expect(card).toContainText("XYZ");
    await expect(card.locator(".signal-dot")).toBeAttached();
    // 報酬率／策略／買賣履約價
    await expect(card).toContainText("567.0%");
    // 實際到期日／距到期天數／最後更新時間
    await expect(card).toContainText("Exp");
    await expect(card).toContainText("45 天");
    // 封存入口仍在，不因為 compact 而消失。
    await expect(card.getByRole("button", { name: /封存/ })).toBeAttached();
  });

test("返回劇本庫時停在原本捲動的位置，不必重新往下找（MVP-v2／#77、#83）",
  async ({ page }) => {
    const rows = Array.from({ length: 10 }, (_, i) =>
      libraryRow({ id: `s${i}`, symbol: `SYM${i}`,
                   latest_analyzed_at: null, best_return: null }));
    await page.route("**/api/scenarios", (route) => route.fulfill({ json: rows }));
    await page.route("**/api/scenarios/*/refresh", (route, req) =>
      route.fulfill({ json: rows.find((r) => req.url().includes(`/${r.id}/`)) }));
    // 詳細頁路由：任一劇本 id 都指回同一份形狀，測試只在乎「回得去、
    // 回去後畫面上是原本那份清單」，不在乎詳細頁內容本身。
    await page.route("**/api/scenarios/s*", (route, req) => {
      const id = req.url().split("/").pop();
      const found = rows.find((r) => r.id === id);
      return route.fulfill({ json: { ...found, latest_result: null } });
    });

    await page.goto("/");
    await expect(page.getByRole("listitem").first()).toBeVisible();

    // 捲到清單中段，記住這個位置。
    await page.evaluate(() => window.scrollTo(0, 400));
    const scrollBefore = await page.evaluate(() => window.scrollY);
    expect(scrollBefore).toBeGreaterThan(0);

    // 點一張捲動範圍內才看得到的卡片進詳細頁，再用返回入口回劇本庫
    // ——不是重新整理，是同一個 App 內的 hash 導覽（#72 既有機制）。
    await page.getByRole("link", { name: /SYM5/ }).click();
    await expect(page.getByRole("link", { name: "‹ 劇本庫" })).toBeVisible();
    await page.getByRole("link", { name: "‹ 劇本庫" }).click();

    await expect(page.getByRole("listitem").first()).toBeVisible();
    // 允許些微誤差（不同時機的 layout 抖動），但必須明顯不是又跳回頂端
    // ——那正是這張票要修的舊行為。
    await expect.poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(scrollBefore - 20);
  });

test("手機詳細頁不受桌面密度壓縮影響（QA-FIX-3／QA-01 的 Mobile 護欄）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.goto("/#/s/s1");
  await expect(page.locator(".card").first()).toBeVisible();

  // QA-FIX-3 的規則全部掛在 `.detail-pane` 底下，而那是桌面專屬 DOM
  // （`App.tsx` 手機分支在 `<div className="workspace">` 之前就 return）。
  // 這條測試把「手機拿不到那個作用域」釘死：手機版根本沒有 detail-pane，
  // 一般卡片內距維持原本的 16px，不是桌面壓縮後的 12px。
  await expect(page.locator(".detail-pane")).toHaveCount(0);
  await expect(page.locator(".card:not(.summary-card)").first())
    .toHaveCSS("padding", "16px");

  // 摘要卡是 QA 修正明文要壓的那一張，手機也要壓——它自己的內距比
  // 一般卡片小，而且統計格線在手機就已經是兩欄（不是桌面才生效）。
  const summary = page.locator(".summary-card");
  await expect(summary).toHaveCSS("padding", "12px");
  const stats = summary.locator(".stat");
  const a = (await stats.nth(0).boundingBox())!;
  const b = (await stats.nth(1).boundingBox())!;
  expect(Math.abs(a.y - b.y)).toBeLessThan(2);
  expect(b.x).toBeGreaterThan(a.x);
  // 但手機只有兩欄，不是桌面的四欄——第三格要換行到下一列去。
  const c = (await stats.nth(2).boundingBox())!;
  expect(c.y).toBeGreaterThan(a.y + 1);
});

test("手機垃圾桶：全選後批次動作立刻在視窗內可操作（QA-FIX-4／QA-01）",
   async ({ page }) => {
  const trashed = Array.from({ length: 8 }, (_, i) => libraryRow({
    id: `s${i}`, symbol: `SYM${i}`, target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" }));
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: trashed }));

  await page.goto("/#/trash");
  await page.getByRole("button", { name: "全選" }).click();
  await expect(page.getByText("已選 8 個")).toBeVisible();

  // 用 boundingBox 對照 viewport，不用 isVisible()——後者對捲到畫面外
  // 的元素照樣回報 true（QA-01 第 5 項就是被這一點掩蓋住的）。
  const bar = page.locator(".batch-action-bar");
  const vh = page.viewportSize()!.height;
  const box = (await bar.boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(vh + 1);
});

/* ---------- 設定頁（Settings／#124） ---------- */

const SETTINGS_VIEW = {
  supported_providers: [{ id: "marketdata-app", label: "Market Data App" }],
  market_data: { mode: "default", provider: null, default_label: "Cboe" },
  historical_iv: { mode: "default", provider: null, default_label: "無" },
  credentials: {
    "marketdata-app": {
      configured: false, masked: null, updated_at: null,
      status: "unset", reason: null, checked_at: null,
    },
  },
  market_data_effective: { source: "Cboe", fallback: false, reason: null },
  historical_iv_enabled: false,
  updated_at: null,
};

const SETTINGS_SAVED = {
  ...SETTINGS_VIEW,
  historical_iv: {
    mode: "custom", provider: "marketdata-app", default_label: "無",
  },
  credentials: {
    "marketdata-app": {
      configured: true, masked: "••••••••abcd",
      updated_at: "2026-08-12T00:00:00+00:00",
      status: "unverified", reason: null, checked_at: null,
    },
  },
};

async function routeSettingsMobile(page: import("@playwright/test").Page) {
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  let saved = false;
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PUT") saved = true;
    return route.fulfill({ json: saved ? SETTINGS_SAVED : SETTINGS_VIEW });
  });
  await page.route("**/api/settings/credentials/**", (route) => {
    saved = true;
    return route.fulfill({ json: SETTINGS_SAVED });
  });
  // Settings 現在也掛著 Diagnostics 區塊（DG-06／#149），它自己會打
  // `/api/diagnostics`——這裡預設回空清單，個別測試需要非空清單時
  // 自己再覆蓋這個 route。
  await page.route("**/api/diagnostics*", (route) => route.fulfill({ json: [] }));
}

test("手機版：工作區右上角的齒輪進得去設定，返回回得來（Settings／#124）", async ({ page }) => {
  await routeSettingsMobile(page);
  await page.goto("/");

  const gear = page.getByRole("button", { name: "設定" });
  await expect(gear).toBeVisible();

  // 「右上角」：齒輪落在視窗右半邊、且在頂部功能列內。
  const box = (await gear.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.x).toBeGreaterThan(viewport.width / 2);
  expect(box.y).toBeLessThan(120);

  await gear.click();
  await expect(page.getByText("Data / API")).toBeVisible();
  // 設定是整頁替換：劇本庫的功能列此時不在畫面上
  await expect(page.getByRole("button", { name: "重新整理" })).toHaveCount(0);

  await page.getByRole("link", { name: "‹ 劇本庫" }).click();
  await expect(page.getByRole("button", { name: "重新整理" })).toBeVisible();
});

test("手機版：Historical IV 切自訂、存 token，只看得到遮罩（Settings／#124）", async ({ page }) => {
  await routeSettingsMobile(page);
  await page.goto("/#/settings");

  const iv = page.getByRole("region", { name: "Historical IV" });
  // 預設是「無」——這正是 #126 讓整個 IV 模組不出現的那個狀態
  await expect(iv.getByText("預設：無")).toBeVisible();

  await iv.getByRole("radio", { name: "自訂" }).click();
  await expect(iv.getByText("目前支援：Market Data App")).toBeVisible();
  await expect(iv.getByText("需自行申請 API Token")).toBeVisible();
  // 文案裁示：不出現「推薦」
  await expect(page.locator("body")).not.toContainText("推薦");

  await iv.getByLabel("API Token").fill("tok-secret-abcd");
  await iv.getByRole("button", { name: "儲存" }).click();

  await expect(iv.getByText("已儲存 ••••••••abcd")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("tok-secret-abcd");
});

/* ---------- Diagnostics / 報錯紀錄（DG-06／#149） ---------- */

const DIAG_EVENT_E2E = {
  event_id: "evt-e2e-1", correlation_id: "cid-e2e-1",
  ts: "2026-08-15T00:00:00+00:00", subsystem: "historical_iv",
  stage: "payload_parse", severity: "warning",
  message: "raw_rows > 0 but parsed rows are 0",
  context: { raw_rows: 5, parsed_call_rows: 0 },
};

test("手機版：Settings 的 Diagnostics 區塊可讀可操作（DG-06／#149）",
   async ({ page }) => {
  await routeSettingsMobile(page);
  let events: unknown[] = [DIAG_EVENT_E2E];
  await page.route("**/api/diagnostics*", (route) => {
    if (route.request().method() === "DELETE") {
      events = [];
      return route.fulfill({ json: { cleared: 1 } });
    }
    return route.fulfill({ json: events });
  });

  await page.goto("/#/settings");

  const section = page.getByRole("region", { name: "Diagnostics" });
  await expect(section).toBeVisible();
  // 可讀：清單欄位看得到
  await expect(section.getByText("payload_parse")).toBeVisible();
  await expect(section.getByText("警告")).toBeVisible();
  await expect(section.getByText("raw_rows > 0 but parsed rows are 0"))
    .toBeVisible();

  // 可操作：點一筆展開完整 details
  await section.getByText("raw_rows > 0 but parsed rows are 0").click();
  await expect(section.getByText("事件 ID")).toBeVisible();
  await expect(section.getByText("evt-e2e-1")).toBeVisible();
  await expect(section.getByText("cid-e2e-1")).toBeVisible();

  // 可操作：Clear diagnostics 兩段式確認
  await section.getByRole("button", { name: "Clear diagnostics" }).click();
  await section.getByRole("button", { name: "確定清除" }).click();
  await expect(section.getByText("目前沒有紀錄")).toBeVisible();
});

/* ---------- Historical IV Position 與閘門（#114／#126／一年走勢圖＋
   Δ4w：#140，缺資料狀態全景 E2E：#141；exact-contract 逐腿卡片：
   HIVT-02–05／#153–156，spec #151） ----------
 *
 * **Long Call 模式的範圍說明**：這份 E2E 走的是真實前端＋route 攔截，
 * 頁面用哪個候選是 `baselineTopCandidate(view)` 決定的（`src/api.ts`），
 * 而它只認 `expiry_top10`——單腳策略（Long Call）恆為空（T9 附錄A7）。
 * 這正是 #139 施工中發現的同一個上層限制的另一面：不只後端
 * `find_candidate` 曾經找不到單腳候選，連前端「這頁該顯示哪個候選」
 * 的邏輯也是同一套 Spread-only 假設。往上一層看，Scenario 流程本身
 * （`_MVP_STRATEGIES = ("bull-call-spread",)`）從來不會為 Scenario 跑
 * long-call 分析，所以無論怎麼調整候選判別，真實 App 導覽路徑今天都
 * 走不到 Long Call 模式——不是本輪任何一張票能單獨解開的範圍。Long
 * Call 版型的渲染邏輯已在 Vitest 元件測試（`IvHistory.test.tsx`／
 * `IvTrend.test.tsx` 直接餵單腳 `legs` prop）驗證過，那是目前唯一構造
 * 得出這個狀態的層級；E2E 這裡只驗證真實 App 導覽路徑實際會走到的
 * Spread 模式（買／賣腿都在）。
 *
 * **回應形狀（HIVT-04／05 之後）**：不再有共用的 `points`／
 * `metrics.{buy,sell,atm}_iv`——Normalized Skew 家族只剩
 * `normalized_skew_points`／`metrics.normalized_skew`；買／賣腿改成
 * `legs.buy`／`legs.sell` 兩份各自獨立的 exact-contract 序列
 * （`src/IvTrend.tsx`），每一份自己的 `points`／`moving_average`／
 * `bollinger_upper`／`bollinger_lower`／`current_percentile`／
 * `current_zscore`／`delta_4w`／`observation_count`／`history_span_days`／
 * `status`／`note`。兩個家族的假資料因此分開建構，不再共用同一組
 * `points`。
 */

/** 貼近真實密度（引擎 `sampling_schedule` 全年約 55–75 點），不是隨便
 *  湊一個「夠多」的數字——250 點塞進一張手機寬度的走勢圖，相鄰資料點
 *  的可點擊圓圈會嚴重疊在一起，連自動化都點不準特定的那一個，這不是
 *  測試技巧問題，是真實使用者在窄螢幕上也會遇到的密度問題。日期用
 *  單調遞增、彼此不重複的序列（真實觀測本來就是逐日累積，不會重複）。 */
function ivDates() {
  const start = new Date("2025-08-15T00:00:00Z");
  return Array.from({ length: 66 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + Math.round(i * 365 / 65));
    return d.toISOString().slice(0, 10);
  });
}

/** Normalized Skew 家族自己的一年走勢圖資料（(tenor,delta) 逐日重錨定，
 *  `IvHistory.tsx` 頭條）。 */
function normalizedSkewPoints() {
  return ivDates().map((date, i) => ({ date, normalized_skew: 0.08 + i * 0.0001 }));
}

function normalizedSkewMetric(points: ReturnType<typeof normalizedSkewPoints>) {
  const last = points[points.length - 1];
  return { value: last ? last.normalized_skew : null, percentile: 0.62, count: 45,
          trend_4w: 0.006, trend_base_count: 6 };
}

function statSeries(dates: string[], value: number) {
  return dates.map((date) => ({ date, value }));
}

/** 一隻腳（買腿或賣腿）的完整 exact-contract 歷史 IV（`legs.buy`／
 *  `legs.sell`，HIVT-02／03／#153／#154）。預設值對齊舊版 `buy_iv` 那組
 *  假資料（percentile 0.41、Δ4w -0.012），呼叫端只需要覆寫 `contract`
 *  跟少數幾個要驗證的欄位。 */
function legHistoricalIv(overrides: Record<string, unknown> = {}) {
  const dates = ivDates();
  const points = dates.map((date, i) => ({ date, iv: 0.2 + (i % 20) * 0.001 }));
  return {
    contract: { underlying: "XYZ", expiration: "2026-09-18", strike: 118,
               option_type: "call", contract_symbol: "XYZ260918C00118000" },
    points,
    moving_average: statSeries(dates, 0.21),
    bollinger_upper: statSeries(dates, 0.25),
    bollinger_lower: statSeries(dates, 0.17),
    current_percentile: 0.41,
    current_zscore: 0.3,
    delta_4w: -0.012,
    observation_count: points.length,
    history_span_days: 365,
    lookback_days_config: 30,
    status: "ok",
    note: null,
    ...overrides,
  };
}

/** 賣腿身份——固定跟買腿（履約價 118）不同一張合約（履約價 125），
 *  避免兩隻腳意外撞成同一份資料。 */
const SELL_CONTRACT = { underlying: "XYZ", expiration: "2026-09-18", strike: 125,
                        option_type: "call", contract_symbol: "XYZ260918C00125000" };

/** 完全沒有歷史觀測的那隻腳——`points` 等序列全空、統計量全 `null`，
 *  誠實對應「沒有可比較觀測」這個狀態（不是把 `legHistoricalIv()` 的
 *  假資料留著只清掉統計量，那樣走勢圖還是畫得出來，測不到真正的
 *  「沒有東西可畫」）。 */
function emptyLegHistoricalIv(overrides: Record<string, unknown> = {}) {
  return legHistoricalIv({
    points: [], moving_average: [], bollinger_upper: [], bollinger_lower: [],
    current_percentile: null, current_zscore: null, delta_4w: null,
    observation_count: 0, history_span_days: 0,
    ...overrides,
  });
}

/** 一份「一切正常」的完整 Historical IV 回應——兩腿都有完整歷史，
 *  Normalized Skew 也有完整歷史。個別測試需要 diagnostics events／
 *  partial 資料時，直接展開這個物件覆寫要驗的欄位即可。 */
function fullIvResponse(overrides: Record<string, unknown> = {}) {
  const skewPoints = normalizedSkewPoints();
  return {
    candidate_key: "k", status: "ok",
    normalized_skew_points: skewPoints,
    metrics: { normalized_skew: normalizedSkewMetric(skewPoints) },
    observations: skewPoints.length, note: null,
    diagnostics: { correlation_id: "cid-e2e", events: [] },
    legs: {
      buy: legHistoricalIv(),
      sell: legHistoricalIv({ contract: SELL_CONTRACT, current_percentile: 0.55,
                             delta_4w: -0.004 }),
    },
    ...overrides,
  };
}

async function routeDetailWithIv(page: import("@playwright/test").Page,
                                 enabled: boolean) {
  await routeLibrary(page, libraryRow());
  const ivCalls: string[] = [];
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: enabled } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    ivCalls.push(route.request().url());
    return route.fulfill({ json: fullIvResponse() });
  });
  return ivCalls;
}

/** 點開 Advanced／Diagnostics 收合區（SIG-02／#173）——z-score 文字、
 *  Normalized Skew 整組、inline diagnostics 都收在裡面，預設收合時對
 *  Playwright 是真正的 `display: none`（不像 jsdom 那樣忽略），既有
 *  測試裡驗這些內容可見，都得先點開才看得到。 */
async function openAdvanced(block: import("@playwright/test").Locator) {
  await block.getByText("Advanced／Diagnostics").click();
}

/** 一隻掛牌不滿一年的腿——`spanDays` 天前才有第一筆觀測，日期陣列本身
 *  真的只跨那麼長（不是掛著一個大陣列只改 `history_span_days` 這個
 *  數字充數）。`history_span_days` 直接從產生出來的日期陣列頭尾反推，
 *  跟 `observation_count` 一樣是「這批假資料自己量出來的」，不是另外
 *  手動湊的常數——HIVT-07／#158 明文要求這裡不能只換 caption 文字（見
 *  票上 Scope 第 2 點）。觀測數固定在 5～20 筆之間：太少會落進
 *  `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS` 門檻讓 MA／帶整段 unavailable
 *  （這不是本測試要驗的東西），太多則跟真實密度脫節。 */
function partialHistoryLeg(spanDays: number,
                           overrides: Record<string, unknown> = {}) {
  const end = new Date("2026-08-16T00:00:00Z");
  const count = Math.max(5, Math.min(20, Math.round(spanDays / 7) + 1));
  const dates = Array.from({ length: count }, (_, i) => {
    const d = new Date(end);
    d.setUTCDate(d.getUTCDate() - spanDays + Math.round(i * spanDays / (count - 1)));
    return d.toISOString().slice(0, 10);
  });
  const actualSpanDays = Math.round(
    (new Date(dates[dates.length - 1]).getTime() - new Date(dates[0]).getTime())
    / 86_400_000);
  const points = dates.map((date, i) => ({ date, iv: 0.20 + (i % 5) * 0.005 }));
  return legHistoricalIv({
    points,
    moving_average: statSeries(dates, 0.205),
    bollinger_upper: statSeries(dates, 0.23),
    bollinger_lower: statSeries(dates, 0.18),
    observation_count: points.length,
    history_span_days: actualSpanDays,
    ...overrides,
  });
}

/** 只給單腳（買腿）掛部分歷史的分析頁 route——涵蓋時間／觀測筆數這幾張
 *  測試只在乎買腿卡片本身的呈現，賣腿沿用一般完整歷史即可，不需要每個
 *  案例都重新建構整份 spread 回應。 */
async function routePartialHistory(
  page: import("@playwright/test").Page,
  buyLeg: ReturnType<typeof legHistoricalIv>,
) {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      legs: { buy: buyLeg,
             sell: legHistoricalIv({ contract: SELL_CONTRACT }) },
    }) }));
}

test("Historical IV 未解鎖：分析頁完全沒有這個模組，也不發任何 IV 請求（#126）",
   async ({ page }) => {
  const ivCalls = await routeDetailWithIv(page, false);
  await page.goto("/#/s/s1");

  // 頁面其餘部分照常渲染——閘門只擋這一塊
  await expect(page.getByText("劇本主圖")).toBeVisible();
  // 這一塊連節點都沒有：不是空卡片、不是「尚未啟用」提示
  await expect(page.getByText("IV 相對位置")).toHaveCount(0);
  await expect(page.getByText("Normalized Skew")).toHaveCount(0);
  expect(ivCalls).toEqual([]);
});

test("Historical IV 解鎖：買／賣腿各自一張卡為主要內容，Normalized Skew 收進" +
     "預設收合的 Advanced（#114／HIVT-05／SIG-02／#173）",
   async ({ page }) => {
  await routeDetailWithIv(page, true);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  // HIVT-04（#155）之後舊的「買腿 IV」／「賣腿 IV」次要顯示已移除，
  // 改由 `IvTrend.tsx` 逐腿卡片供應，標籤簡化成「買腿」／「賣腿」——
  // 這兩張卡是主要內容，不必展開任何東西就看得到。
  await expect(block.getByText("買腿", { exact: true })).toBeVisible();
  await expect(block.getByText("賣腿", { exact: true })).toBeVisible();

  // Normalized Skew 整組（SIG-02／#173）搬進預設收合的 Advanced／
  // Diagnostics 區塊——展開前不可見，展開後才看得到。
  await expect(block.getByText("Normalized Skew")).not.toBeVisible();
  await openAdvanced(block);
  await expect(block.getByText("Normalized Skew")).toBeVisible();
  await expect(block.getByText(/第 62 百分位/)).toBeVisible();

  // HIVT-05（#156）之後，買／賣腿卡片（`.iv-trend-card`）不再是「次於
  // Normalized Skew 頭條」的次層小字顯示——`IvTrend.tsx` 每隻腳都是
  // 獨立正確的完整卡片，現值一律用 `.iv-value-primary`，舊版「頭條
  // 字級大於次層」的階層（靠 `.iv-value`／`.iv-value-primary` 兩種
  // class 區分）已經不在了。這裡改成驗證這個新事實：三個現值
  // （Normalized Skew／買腿／賣腿）字級一致，不是驗證一個已經不存在
  // 的大小差異。
  const primarySizes = await block.locator(".iv-value-primary").evaluateAll(
    (els) => els.map((el) => parseFloat(getComputedStyle(el).fontSize)));
  expect(primarySizes).toHaveLength(3);
  expect(new Set(primarySizes).size).toBe(1);

  // #135 曾要求這一區「壓到合理最低」（門檻曾是 60% 視窗高）；本輪
  // （spec #137／#140）需求方明確改裁示「走勢圖為主體」，三張真正的
  // 走勢圖取代 18px sparkline，這個區塊因此**理應**比 #135 那版更高
  // ——這不是需要修的迴歸，是新裁示要的樣子（#140 施工中確認：門檻
  // 放寬到接近整頁高度）。這裡只守一個很寬鬆的上限，抓的是「SVG 沒有
  // 隨容器縮放、整張圖用原始 viewBox 像素數硬畫」這種真正的破版，不是
  // 卡住這次刻意做大的正常尺寸。
  //
  // 門檻本身在 HIVT-05（#156）後又往上調過一次：買／賣腿卡片
  // （`.iv-trend-card`）比舊版的次層 `.iv-metric` 內容更豐富——現值→
  // 走勢圖→百分位／Z-score／Δ4w／涵蓋時間共四行 caption，兩張腿卡疊
  // 起來比舊版「兩腿共用一份 reanchored 資料、擠在雙欄 grid 裡各一行
  // 摘要」明顯高上不少（實測約 1.85 倍視窗高），這同樣是新設計刻意
  // 的結果（每隻腳都是獨立完整呈現，不是頭條的縮寫附屬），不是需要
  // 修的迴歸，因此把上限一併放寬，留給真正的破版足夠的容錯空間。
  const box = (await block.boundingBox())!;
  expect(box.height).toBeLessThan(page.viewportSize()!.height * 2.5);
});

test("Historical IV：一年走勢圖在手機 viewport 完整可讀、寬度貼齊卡片（#140／#141）",
   async ({ page }) => {
  await routeDetailWithIv(page, true);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  // 幾何驗證，不是文字存在性或 isVisible()（QA-FIX-1／QA-FIX-4 教訓）：
  // 走勢圖要真的畫在卡片內、寬度貼近卡片寬度——不是被裁切、也不是縮成
  // 一個看不出路徑的小點。
  const chart = block.locator(".iv-trend-chart").first();
  await expect(chart).toBeVisible();
  const chartBox = (await chart.boundingBox())!;
  const cardBox = (await block.boundingBox())!;
  expect(chartBox.width).toBeGreaterThan(cardBox.width * 0.8);
  expect(chartBox.x).toBeGreaterThanOrEqual(cardBox.x - 1);
  expect(chartBox.x + chartBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
  // 有實際高度可畫路徑——不是塌成一條線（走勢圖為主體的核心驗收）。
  expect(chartBox.height).toBeGreaterThan(30);

  // 三張圖（Normalized Skew、買腿、賣腿）都各自有一張走勢圖，不是只有
  // 頭條有——舊版買／賣腿共用一份 reanchored 資料只算一張圖，新版兩隻
  // 腳各自 fetch 各自的 exact-contract 序列，因此仍然是 3 張（巧合
  // 同數，不是同一套資料換皮）。
  await expect(block.locator(".iv-trend-chart")).toHaveCount(3);
});

test("Historical IV：Δ4w 帶正負號與單位，跟 percentile／涵蓋時間同一套事實敘述（#140／HIVT-05）",
   async ({ page }) => {
  await routeDetailWithIv(page, true);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  // 買腿：delta_4w = -0.012 → 「-1.2 pts」（主要區塊，不必展開 Advanced）
  await expect(block.getByText(/4週 -1\.2 pts/)).toBeVisible();
  // Normalized Skew：trend_4w = 0.006 → 「+0.01」（無因次小數，不是
  // pts）——SIG-02（#173）後這一項在 Advanced 裡，先展開才看得到。
  await openAdvanced(block);
  await expect(block.getByText(/4週 \+0\.01/)).toBeVisible();
  await expect(block.getByText(/4週 \+0\.6 pts/)).toHaveCount(0);
});

test("Historical IV：手機點按圖表任意位置顯示 tooltip，位置落在走勢圖範圍內" +
     "（#140／#141；整張圖是單一 scrubber 介面，需求方 2026-08-22 反饋——" +
     "不再要求使用者精準點中某顆逐點命中圓點）",
   async ({ page }) => {
  await routeDetailWithIv(page, true);
  await page.goto("/#/s/s1");

  const chart = page.locator(".iv-history .iv-trend-chart").first();
  await expect(chart).toBeVisible();
  await expect(chart.getByRole("button")).toHaveCount(0);

  // 點在圖表任意位置（預設中心點）就該找到最近的資料點，不必點準
  // 哪一顆隱形圓點。
  await chart.click();
  const tooltip = chart.locator(".chart-tooltip");
  await expect(tooltip).toBeVisible();

  // 幾何驗證：tooltip 落在走勢圖的座標範圍內，不是飄到卡片外面。
  const tooltipBox = (await tooltip.boundingBox())!;
  const chartBox = (await chart.boundingBox())!;
  expect(tooltipBox.x).toBeGreaterThanOrEqual(chartBox.x - 1);
  expect(tooltipBox.x + tooltipBox.width)
    .toBeLessThanOrEqual(chartBox.x + chartBox.width + 1);
});

test("Historical IV 今日額度用完：percentile／Δ4w 照樣顯示，只多一行附加說明（#133／#140）",
   async ({ page }) => {
  // 需求方 2026-08-12 二次修正：backfill 狀態（今天補不補得動）跟資料
  // 能不能看是兩件事——quota 不再讓整塊變成「不畫百分位」的短訊息卡，
  // 已快取的觀測算出的 percentile／Δ4w 照常顯示。這裡只讓頂層 `status`
  // （Normalized Skew 家族自己的 backfill 狀態）落在 quota；兩腿各自的
  // `status` 維持 `ok`——HIVT-02（#153）之後兩個家族的 backfill 狀態
  // 本來就各自獨立，不是同一顆旗標，這裡刻意只驗其中一個家族，符合
  // 「只多一行附加說明」的原始斷言意圖。
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    const skewPoints = normalizedSkewPoints().slice(0, 12);   // 只補了一部分
    return route.fulfill({ json: {
      candidate_key: "k", status: "quota",
      normalized_skew_points: skewPoints,
      metrics: { normalized_skew: normalizedSkewMetric(skewPoints) },
      observations: skewPoints.length,
      note: "Market Data App 今日額度已用完",
      diagnostics: { correlation_id: "cid-e2e", events: [] },
      legs: { buy: legHistoricalIv(), sell: legHistoricalIv({
        contract: SELL_CONTRACT, current_percentile: 0.55, delta_4w: -0.004 }) },
    } });
  });

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  // 頂層 status（Normalized Skew 家族）的附加說明跟著它一起搬進
  // Advanced（SIG-02／#173）——先展開才看得到。
  await openAdvanced(block);
  await expect(block.getByText(/今日 API 額度已用完/)).toBeVisible();

  // percentile 沒有被藏起來——鎖定 Normalized Skew 那一項精確的組合
  // 文字，不會跟兩腿卡片各自的百分位撞在一起。
  await expect(block.getByText("第 62 百分位・45 筆觀測")).toBeVisible();
  // Δ4w 同樣不受 backfill 狀態影響——買腿卡片自己的 Δ4w 照樣顯示。
  await expect(block.getByText(/4週 -1\.2 pts/)).toBeVisible();
  // 走勢圖也照樣畫得出來（Normalized Skew 只有 12 筆部分資料＋兩腿各自
  // 完整的走勢圖，不是空白）。
  await expect(block.locator(".iv-trend-chart")).toHaveCount(3);

  // 主分析頁其餘部分照常
  await expect(page.getByText("劇本主圖")).toBeVisible();
});

test("Historical IV 完全沒有可比較觀測：誠實顯示沒有歷史資料，不硬湊（#133／#140／HIVT-05）",
   async ({ page }) => {
  // 兩個家族各自獨立 fetch（HIVT-02／#153），因此「完全沒有觀測」要
  // 分開讓 Normalized Skew 與兩隻腳都落在各自的空資料狀態，才是真的
  // 「整頁都沒有歷史資料」，不是只清空其中一個家族。
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    const emptyMetric = { value: null, percentile: null, count: 0,
                          trend_4w: null, trend_base_count: 0 };
    return route.fulfill({ json: {
      candidate_key: "k", status: "ok",
      normalized_skew_points: [],
      metrics: { normalized_skew: emptyMetric },
      observations: 0, note: null,
      diagnostics: { correlation_id: "cid-e2e", events: [] },
      legs: { buy: emptyLegHistoricalIv(),
             sell: emptyLegHistoricalIv({ contract: SELL_CONTRACT }) },
    } });
  });

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  await expect(block.getByText("沒有歷史資料").first()).toBeVisible();
  // 沒有觀測就沒有東西可畫——三張走勢圖（Normalized Skew＋買／賣腿）
  // 都不畫，不是空白外框。
  await expect(block.locator(".iv-trend-chart")).toHaveCount(0);
  // Normalized Skew 沒有數字可秀（`metricCaption` 整句換成「沒有歷史
  // 資料」）。兩腿卡片則是 HIVT-03（#154）明文要求的逐項 graceful
  // degradation——`IvTrend.tsx` 每一項（百分位／Z-score／Δ4w）各自
  // 印出「百分位：沒有歷史資料」「Z-score：觀測數不足」「4週 —」，
  // 字面上本來就會出現「百分位」「Z-score」「4週」這些詞——這不是舊版
  // 「整塊被沒有資料取代掉」的邏輯，是新版刻意的逐項誠實呈現，所以
  // 這裡改成鎖定「有沒有捏造出帶正負號或具體百分位數字的假讀數」，
  // 而不是鎖定這些欄位名稱字面本身是否出現。
  await expect(block).not.toContainText(/第 \d+ 百分位/);
  await expect(block).not.toContainText(/Z-score [+\-]/);
  await expect(block).not.toContainText(/4週 [+\-]\d/);
  await expect(page.getByText("劇本主圖")).toBeVisible();
});

test("Historical IV：兩腿各自獨立——買腿有完整歷史，賣腿完全沒有觀測，互不污染" +
     "（#133／#140；HIVT-02／03：兩隻腳是各自獨立 fetch 的 exact contract，" +
     "spec #151 §2／AC 明文「絕不合成一條 Spread IV」）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    const skewPoints = normalizedSkewPoints();
    return route.fulfill({ json: {
      candidate_key: "k", status: "ok",
      normalized_skew_points: skewPoints,
      metrics: { normalized_skew: normalizedSkewMetric(skewPoints) },
      observations: skewPoints.length, note: null,
      diagnostics: { correlation_id: "cid-e2e", events: [] },
      legs: { buy: legHistoricalIv(),
             sell: emptyLegHistoricalIv({ contract: SELL_CONTRACT }) },
    } });
  });

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  const cards = block.locator(".iv-trend-card");
  await expect(cards).toHaveCount(2);
  // 賣腿：誠實說沒有資料，不畫圖
  const sellCard = cards.filter({ hasText: "賣腿" });
  await expect(sellCard.getByText(/沒有歷史資料/)).toBeVisible();
  await expect(sellCard.locator(".iv-trend-chart")).toHaveCount(0);
  // 買腿：完整資料照常顯示，不受賣腿沒資料影響
  const buyCard = cards.filter({ hasText: "買腿" });
  await expect(buyCard.getByText(/第 41 百分位/)).toBeVisible();
  await expect(buyCard.locator(".iv-trend-chart")).toHaveCount(1);
});

/* ---------- HIVT-07（#158）全面回歸／E2E 最終驗收：補齊 spec #151
   34 項 User Stories／Implementation Decisions 裡，既有 75 條 E2E 尚未
   逐一肉眼可見驗證到的幾個缺口。 ---------- */

test("Historical IV：買／賣腿讀到的是各自 exact contract 的真實觀測——現值與百分位" +
     "在 DOM 上讀出兩個確實不同的數字，不是共用同一份序列複製兩份（HIVT-07／" +
     "#158，story #1–#4：不跨 strike／不跨 expiration 替代，要看得見）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      legs: {
        // 買／賣腿的原始 IV 序列本身就不同（不只覆寫 percentile／Δ4w
        // 這些衍生統計量）——履約價 118 的買腿 vs 履約價 125 的賣腿，
        // 兩張真正不同的合約本來就該有不同的市場報價。
        buy: legHistoricalIv({ points: ivDates().map((date, i) =>
          ({ date, iv: 0.20 + (i % 20) * 0.001 })) }),
        sell: legHistoricalIv({ contract: SELL_CONTRACT,
          points: ivDates().map((date, i) => ({ date, iv: 0.32 + (i % 20) * 0.001 })),
          current_percentile: 0.55, delta_4w: -0.004 }),
      },
    }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  const cards = block.locator(".iv-trend-card");
  const buyCard = cards.filter({ hasText: "買腿" });
  const sellCard = cards.filter({ hasText: "賣腿" });

  // 現值（`.iv-value-primary`）：買腿最後一筆 0.20+(65%20)*0.001=20.5%，
  // 賣腿最後一筆 0.32+(65%20)*0.001=32.5%——實際從兩張卡各自讀出來的
  // 兩個數字，不是只驗證兩張卡「存在」。
  const buyValue = await buyCard.locator(".iv-value-primary").textContent();
  const sellValue = await sellCard.locator(".iv-value-primary").textContent();
  expect(buyValue).toBe("20.5%");
  expect(sellValue).toBe("32.5%");
  expect(buyValue).not.toBe(sellValue);

  // 百分位同樣讀出兩個不同數字（41 vs 55），跟現值是各自獨立的兩條
  // 驗證線，不是同一個斷言重複兩次。
  await expect(buyCard.getByText(/第 41 百分位/)).toBeVisible();
  await expect(sellCard.getByText(/第 55 百分位/)).toBeVisible();
});

test("Historical IV：掛牌僅約 3 週的合約，涵蓋時間如實顯示「近 3 週」，不是" +
     "「近 1 個月」也不是「近 1 年」（HIVT-07／#158，story #5／#6）",
   async ({ page }) => {
  const leg = partialHistoryLeg(21);
  await routePartialHistory(page, leg);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  const buyCard = block.locator(".iv-trend-card").filter({ hasText: "買腿" });
  await expect(buyCard.getByText(
    new RegExp(`近 3 週・${leg.observation_count} 個觀測`))).toBeVisible();
  await expect(buyCard.getByText(/近 1 個月/)).toHaveCount(0);
  await expect(buyCard.getByText(/近 1 年/)).toHaveCount(0);
});

test("Historical IV：掛牌約 5 個月的合約，涵蓋時間如實顯示「近 5 個月」" +
     "（HIVT-07／#158，story #5／#6）",
   async ({ page }) => {
  const leg = partialHistoryLeg(150);
  await routePartialHistory(page, leg);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  const buyCard = block.locator(".iv-trend-card").filter({ hasText: "買腿" });
  await expect(buyCard.getByText(
    new RegExp(`近 5 個月・${leg.observation_count} 個觀測`))).toBeVisible();
  await expect(buyCard.getByText(/近 1 年/)).toHaveCount(0);
});

test("Historical IV：掛牌約 11 個月的合約，涵蓋時間如實顯示「近 11 個月」，" +
     "不會被籠統講成「近 1 年」——這正是需求方在票上點名的驗收陷阱" +
     "（HIVT-07／#158，story #5／#6）",
   async ({ page }) => {
  const leg = partialHistoryLeg(330);
  await routePartialHistory(page, leg);
  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  const buyCard = block.locator(".iv-trend-card").filter({ hasText: "買腿" });
  await expect(buyCard.getByText(
    new RegExp(`近 11 個月・${leg.observation_count} 個觀測`))).toBeVisible();
  // 修正前的 bug：`spanLabel()` 對 >=300 天一律回「近 1 年」，330 天
  // （11 個月，仍在 `IV_TREND_MAX_HISTORY_DAYS=365` 之內）會被錯誤地
  // 併入這個分支——這裡鎖死絕不能再回來。
  await expect(buyCard.getByText(/近 1 年/)).toHaveCount(0);
});

test("Historical IV：z-score／moving average／Bollinger 帶三項統計量在頁面上" +
     "真的可見（geometry／caption 斷言），不只 Vitest 元件測試覆蓋過" +
     "（HIVT-07／#158，story #8／#9／#10／#11／#12）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  const dates = ivDates();
  // 刻意用有斜率的序列，不是固定常數——固定值的移動平均線在圖上是一條
  // 完全水平的折線，bounding box 高度天生是 0，Playwright 的
  // `toBeVisible()` 對零面積元素判定不穩定，跟這條線「有沒有真的畫出來」
  // 是兩件事。有斜率才是這裡真正要驗的：線段確實佔有實際的寬與高。
  const slopedMa = dates.map((date, i) => ({ date, value: 0.19 + (i % 10) * 0.003 }));
  const slopedUpper = dates.map((date, i) => ({ date, value: 0.23 + (i % 10) * 0.003 }));
  const slopedLower = dates.map((date, i) => ({ date, value: 0.15 + (i % 10) * 0.003 }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      legs: {
        buy: legHistoricalIv({ moving_average: slopedMa,
          bollinger_upper: slopedUpper, bollinger_lower: slopedLower }),
        sell: legHistoricalIv({ contract: SELL_CONTRACT,
          moving_average: slopedMa, bollinger_upper: slopedUpper,
          bollinger_lower: slopedLower,
          current_percentile: 0.55, delta_4w: -0.004 }),
      },
    }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  // z-score caption：買／賣腿預設 current_zscore 都是 0.3 → "+0.30"——
  // SIG-02（#173）後這一項搬進 Advanced，先展開才看得到。
  await openAdvanced(block);
  await expect(block.getByText(/Z-score \+0\.30/).first()).toBeVisible();

  // moving average／Bollinger band 是各自獨立的 SVG 元素，不是只靠
  // `.iv-trend-chart` 存在就能證明這兩條疊加序列真的畫出來了——各自量
  // 出實際佔用的寬／高都大於 0。
  const maLine = block.locator(".iv-trend-ma-line").first();
  await expect(maLine).toBeVisible();
  const maBox = (await maLine.boundingBox())!;
  expect(maBox.width).toBeGreaterThan(0);
  expect(maBox.height).toBeGreaterThan(0);

  const band = block.locator(".iv-trend-band").first();
  await expect(band).toBeVisible();
  const bandBox = (await band.boundingBox())!;
  expect(bandBox.width).toBeGreaterThan(0);
  expect(bandBox.height).toBeGreaterThan(0);

  expect(await block.locator(".iv-trend-ma-line").count()).toBeGreaterThan(0);
  expect(await block.locator(".iv-trend-band").count()).toBeGreaterThan(0);
});

test("Historical IV：買／賣腿各自的 vendor／quota 狀態獨立顯示，不受 Normalized " +
     "Skew 家族自己的 status 影響，也不擋住頁面其他部分（HIVT-07／#158，" +
     "story #32；spec #151 §4「兩個家族的 backfill 狀態各自獨立」）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      status: "ok",   // 頂層（Normalized Skew 家族）維持 ok
      legs: {
        buy: legHistoricalIv({ status: "quota" }),
        sell: legHistoricalIv({ contract: SELL_CONTRACT, status: "vendor",
          current_percentile: 0.55, delta_4w: -0.004 }),
      },
    }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  const cards = block.locator(".iv-trend-card");
  const buyCard = cards.filter({ hasText: "買腿" });
  const sellCard = cards.filter({ hasText: "賣腿" });

  await expect(buyCard.getByText("今日 API 額度已用完，將於後續使用時繼續補齊"))
    .toBeVisible();
  await expect(sellCard.getByText("資料源暫時無法連線，將於後續使用時繼續補齊"))
    .toBeVisible();
  // Normalized Skew 家族自己沒有落在非 ok 狀態，不該多印一行說明——這行
  // 文字只會來自兩腿卡片各自的 status，不是被頂層 status 帶出來的。
  await expect(block.getByText(/今日 API 額度已用完/)).toHaveCount(1);

  // 已快取的統計量不因為今天 backfill 沒補到而被藏起來（既有 quota
  // 慣例延伸到腿層級），走勢圖照常渲染，頁面其餘部分也不受影響。
  await expect(block.locator(".iv-trend-chart")).toHaveCount(3);
  await expect(page.getByText("劇本主圖")).toBeVisible();
});

/* ---------- Inline diagnostics（DG-05／#148） ---------- */

test("Historical IV 請求失敗：頁面不 crash，精簡狀態列可見，可展開可收起（DG-05／#148）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({
      status: 502,
      headers: { "X-Correlation-Id": "cid-e2e-fail" },
      json: { detail: "額度用盡" },
    }));

  await page.goto("/#/s/s1");

  // 卡片本身仍在，頁面其餘部分照常——一個 enrichment 區塊的故障不
  // 拖垮整頁。
  await expect(page.getByText("劇本主圖")).toBeVisible();
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  const summary = block.getByText("Historical IV 資料取得失敗 · 查看詳情");
  await expect(summary).toBeVisible();

  const details = block.locator(".iv-diagnostics");
  const isOpen = () => details.evaluate(
    (el) => (el as HTMLDetailsElement).open);
  expect(await isOpen()).toBe(false);

  await summary.click();
  expect(await isOpen()).toBe(true);
  await expect(block.getByText(/cid-e2e-fail/)).toBeVisible();

  await summary.click();
  expect(await isOpen()).toBe(false);
});

test("Historical IV 200 但帶 warning events：一樣觸發診斷區塊，資料照常渲染（DG-05／#148）",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      diagnostics: { correlation_id: "cid-e2e-warn", events: [DIAG_EVENT_E2E] },
    }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  // 主要區塊（買／賣腿卡片）不必展開任何東西就照常渲染——診斷區塊是
  // additive，不是取代掉資料本身。
  await expect(block.getByText("買腿", { exact: true })).toBeVisible();
  // inline diagnostics 展開內容搬進 Advanced（SIG-02／#173），先展開
  // 才看得到。
  await openAdvanced(block);
  await expect(block.getByText("Historical IV 診斷資訊 · 查看詳情"))
    .toBeVisible();
  // 主資料已成功（買／賣腿卡片照常渲染）——不能出現誤導使用者以為主圖
  // 壞掉的「資料取得失敗」（需求方 2026-08-22 反饋）。
  await expect(block.getByText("Historical IV 資料取得失敗")).toHaveCount(0);
  await expect(block.getByText("Normalized Skew")).toBeVisible();
});

/* ---------- 固定版位＋Inline Diagnostics Copy 按鈕（QA 反饋，2026-08-16） ---------- */

test("手機版：Historical IV 卡片一開始就在，loading 時原位顯示骨架，資料回來後原位換成走勢圖" +
     "（不因 request 完成才決定要不要出現）", async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));

  // 卡在 pending，直到測試自己放行——這是唯一能穩定觀察到 loading
  // 這個瞬間狀態的辦法（沿用 Vitest 元件測試同一種手法）。
  let releaseIv!: () => void;
  const ivGate = new Promise<void>((resolve) => { releaseIv = resolve; });
  await page.route("**/api/scenarios/*/iv-history*", async (route) => {
    await ivGate;
    return route.fulfill({ json: fullIvResponse() });
  });

  await page.goto("/#/s/s1");

  // 卡片版位一開始就在，裡面是骨架，不是空白、也不是整塊還沒出現。
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  await expect(block.getByText("IV 相對位置")).toBeVisible();
  await expect(block.locator(".iv-skeleton")).toBeVisible();
  const cardCountDuringLoading = await page.locator(".card").count();

  releaseIv();
  // 骨架換成真正的主要內容（買腿卡片，SIG-02／#173 後不必展開 Advanced
  // 就看得到）——不是靠 Normalized Skew（現在收在 Advanced 裡）判斷。
  await expect(block.getByText("買腿", { exact: true })).toBeVisible();
  await expect(block.locator(".iv-skeleton")).toHaveCount(0);
  // 換成有資料的內容後，卡片總數沒有變化——不是骨架消失後又多長出一張。
  await expect(page.locator(".card")).toHaveCount(cardCountDuringLoading);
});

test("手機版：Inline Diagnostics 的 Copy 按鈕——版面順序、複製內容、收合展開行為" +
     "（DG-05／#148 延伸，QA 反饋 2026-08-16）", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      diagnostics: { correlation_id: "cid-e2e-copy", events: [DIAG_EVENT_E2E] },
    }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  // inline diagnostics 展開內容搬進 Advanced（SIG-02／#173），先展開
  // 才看得到 summary。
  await openAdvanced(block);
  const summary = block.getByText("Historical IV 診斷資訊 · 查看詳情");
  await expect(summary).toBeVisible();
  await summary.click();

  const copyButton = block.getByRole("button", { name: "Copy diagnostics" });
  await expect(copyButton).toBeVisible();
  const fieldLabel = block.getByText("事件 ID");
  await expect(fieldLabel).toBeVisible();

  // 版面順序：Copy 按鈕在完整 diagnostic details 之前（需求方裁示
  // 「錯誤摘要 → Copy diagnostics 按鈕 → 下方完整 diagnostic details」）。
  const copyBox = (await copyButton.boundingBox())!;
  const fieldBox = (await fieldLabel.boundingBox())!;
  expect(copyBox.y).toBeLessThan(fieldBox.y);

  await copyButton.click();
  await expect(block.getByRole("button", { name: "已複製" })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  const parsed = JSON.parse(copied);
  expect(parsed.correlation_id).toBe("cid-e2e-copy");
  expect(parsed.events[0].event_id).toBe("evt-e2e-1");

  // 收合／展開行為保留。
  const details = block.locator(".iv-diagnostics");
  const isOpen = () => details.evaluate((el) => (el as HTMLDetailsElement).open);
  expect(await isOpen()).toBe(true);
  await summary.click();
  expect(await isOpen()).toBe(false);
});

/* ---------- 編輯劇本（#132） ---------- */

async function routeEditable(page: import("@playwright/test").Page) {
  let current: any = libraryRow({ id: "s1", symbol: "TLT", target_price: 105,
                                  target_month: "2028-06" });
  const patched: any[] = [];
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [current] }));
  await page.route("**/api/scenarios/s1", (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON();
      patched.push(body);
      current = { ...current, ...body };
      return route.fulfill({ json: current });
    }
    return route.fulfill({ json: current });
  });
  await page.route("**/api/scenarios/s1/refresh", (route) =>
    route.fulfill({ json: current }));
  return patched;
}

test("手機版：編輯劇本沿用同一張表單，標的反灰不可改（#132）", async ({ page }) => {
  await routeEditable(page);
  await page.goto("/");

  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await expect(page.getByText("編輯劇本")).toBeVisible();
  await expect(page.getByLabel("標的代號")).toHaveValue("TLT");
  await expect(page.getByLabel("標的代號")).toBeDisabled();
  await expect(page.getByLabel("目標價位")).toHaveValue("105");
});

test("手機版：編輯 → 儲存變更，卡片換成新目標價（#132）", async ({ page }) => {
  const patched = await routeEditable(page);
  await page.goto("/");

  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await page.getByLabel("目標價位").fill("120");
  await page.getByRole("button", { name: "儲存變更" }).click();

  await expect(page.getByText("編輯劇本")).toHaveCount(0);
  await expect(page.getByRole("listitem").first()).toContainText("120");
  // 走 PATCH，而且不帶 symbol
  expect(patched).toHaveLength(1);
  expect(patched[0]).not.toHaveProperty("symbol");
});

test("手機版：編輯 → 取消，原劇本完全不變、不寫入任何東西（#132）",
   async ({ page }) => {
  const patched = await routeEditable(page);
  await page.goto("/");

  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await page.getByLabel("目標價位").fill("999");
  await page.getByRole("button", { name: "取消" }).click();

  await expect(page.getByText("編輯劇本")).toHaveCount(0);
  await expect(page.getByRole("listitem").first()).toContainText("105");
  expect(patched).toEqual([]);
});

/* ---------- SIG-04（#175）：Mobile 紅線鎖定 ---------- */

/** Spread IV Gap（SIG-01／#172）的完整回應區塊——跟 `legHistoricalIv()`
 *  同一套「貼近真實密度」的假資料哲學，各測試需要 unavailable 狀態時
 *  直接覆寫 `points`／統計量欄位。 */
function spreadGapFixture(overrides: Record<string, unknown> = {}) {
  const dates = ivDates();
  const points = dates.map((date, i) => ({ date, gap: 0.05 + (i % 20) * 0.001 }));
  return {
    points,
    moving_average: statSeries(dates, 0.06),
    bollinger_upper: statSeries(dates, 0.09),
    bollinger_lower: statSeries(dates, 0.03),
    current_percentile: 0.6,
    delta_4w: 0.02,
    delta_4w_ratio: 0.4,
    delta_4w_status: "ok",
    observation_count: points.length,
    shared_history_span_days: 365,
    ...overrides,
  };
}

test("SIG-04（#175）Mobile 紅線：IV Gap／買腿／賣腿三個走勢圖全部存在、可見、" +
     "非空，沒有一個在收合的 Advanced 裡，也不是 sparkline",
   async ({ page }) => {
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({ spread_gap: spreadGapFixture() }) }));

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  // 三個圖表元素：Spread Summary（IV Gap）＋ 買／賣腿逐腿卡片，全部不必
  // 展開任何東西就可見——`.iv-trend-legs` 底下正是買／賣兩張，跟
  // Advanced 裡收合的 Normalized Skew 圖分屬不同容器。
  const spreadChart = block.locator(".iv-spread-summary .iv-trend-chart");
  const legCharts = block.locator(".iv-trend-legs .iv-trend-chart");
  await expect(spreadChart).toBeVisible();
  await expect(legCharts).toHaveCount(2);
  await expect(legCharts.nth(0)).toBeVisible();
  await expect(legCharts.nth(1)).toBeVisible();

  // 三者都是完整走勢圖，不是縮成看不出路徑的 sparkline、也不是只剩
  // 數字——各自有實際佔用的寬與高，以及至少一條真的畫出來的折線。
  for (const chart of [spreadChart, legCharts.nth(0), legCharts.nth(1)]) {
    const box = (await chart.boundingBox())!;
    expect(box.width).toBeGreaterThan(100);
    expect(box.height).toBeGreaterThan(30);
    expect(await chart.locator("polyline").count()).toBeGreaterThan(0);
  }

  // 三者沒有一個在收合的 Advanced／Diagnostics 裡：全部走勢圖一共 4 張
  // （IV Gap＋買＋賣＋Advanced 裡收合的 Normalized Skew），Advanced 容器
  // 底下只有那 1 張——代表紅線點名的三張都在外面。
  await expect(block.locator(".iv-trend-chart")).toHaveCount(4);
  await expect(block.locator(".iv-advanced .iv-trend-chart")).toHaveCount(1);
});

/* ---------- SIG-04（#175）：既有隔離測試涵蓋確認 ---------- */

test("SIG-04（#175）：Spread IV Gap 對齊只讀兩腿各自 reconstructed 的市場 IV，" +
     "vendor_iv 完全不影響——迴歸鎖住 SIG-01（#172）新模組同一條紅線",
   async ({ page }) => {
  // 端到端層級不重新驗證後端反解本身（那是 tests/test_ivspread.py 的
  // 範圍），這裡只確認前端把 spread_gap.points 原樣呈現，不夾帶任何
  // 本地重算——現值直接是 points 最後一筆的 gap，不因為別的欄位而變。
  await routeLibrary(page, libraryRow());
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({ spread_gap: spreadGapFixture({
      points: [{ date: "2026-08-01", gap: 0.1234 }],
      observation_count: 1, shared_history_span_days: 0,
    }) }) }));

  await page.goto("/#/s/s1");

  const summary = page.locator(".iv-spread-summary");
  await expect(summary.locator(".iv-value-primary")).toHaveText("12.3%");
});
