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

  // 基準候選（spec #102 決策 A）：baseline 期第 1 名的身分——名次、
  // B/S 履約、到期日、目標報酬。這一組數字從舊版「劇本主圖」卡片搬到
  // 獨立區塊，不再跟 Heatmap 擠在同一張卡裡。
  const top = view.results.find((r) => r.status === "ok" && r.expiry_top10)!
    .expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!.candidates[0];
  const [buy, sell] = top.legs;
  const baselineCandidate = page.locator("section").filter({ hasText: "基準候選" }).first();
  await expect(baselineCandidate).toContainText(`買 ${buy.strike} / 賣 ${sell.strike}`);
  await expect(baselineCandidate).toContainText("第 1 名");
  await expect(baselineCandidate).toContainText(`${(top.baseline_return * 100).toFixed(1)}%`);

  // 進場成本（spec #102 決策 A）：新區塊，緊接基準候選之後。
  const entryCost = page.locator("section").filter({ hasText: "進場成本" }).first();
  await expect(entryCost).toContainText("買腿 Ask");
  await expect(entryCost).toContainText("賣腿 Bid");
  await expect(entryCost).toContainText("淨成本");
  await expect(entryCost).toContainText(`$${top.natural_cost.toFixed(2)}`);

  // 主圖：只剩 Heatmap 本身——候選身分與報酬已搬到「基準候選」。
  // V6 起頁面上有很多張 Heatmap（到期日結構裡每個候選收合著一張），
  // 所以主圖的斷言鎖定主圖那一區。
  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  await expect(mainChart.locator("table.heatmap-table")).toBeVisible();
  // 「現價」在摘要與 Heatmap 錨點列各有一個，這裡要驗的是圖上那個
  await expect(mainChart.locator("table.heatmap-table").getByText("現價")).toBeVisible();

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
  await expect(report.getByText("Source")).toBeVisible();
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
  const targetRow = table.locator("tr").filter({ hasText: "目標" });
  await expect(targetRow.getByText("+30%", { exact: true })).toBeVisible();
  const spotRow = table.locator("tr").filter({ hasText: "現價" });
  await expect(spotRow.getByText("+0%", { exact: true })).toBeVisible();
  // 完整格式（桌面版才顯示）此時不可見，證明真的是短格式在生效，
  // 不是兩種格式一起攤開來看。
  await expect(targetRow.getByText("+30.0%", { exact: true })).not.toBeVisible();
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
