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
  // QA 修正後劇本庫卡片也印現價，同一個數字在左欄每張卡上都有一份
  // ——要驗的是右側詳細頁那個，locator 必須 scope 回 detail-pane。
  await expect(page.locator(".detail-pane")
    .getByText(`$${sample.meta.spot.toFixed(2)}`).first()).toBeVisible();
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

/* ---------- Historical IV 一年走勢圖：桌面版（#140／#141） ---------- */

/** 貼近真實密度（引擎 `sampling_schedule` 全年約 55–75 點）——見
 *  `smoke.spec.ts` 同名函式的說明：250 點塞進走勢圖會讓相鄰資料點的
 *  可點擊圓圈嚴重疊在一起，連自動化都點不準。 */
function ivPoints() {
  const start = new Date("2025-08-15T00:00:00Z");
  return Array.from({ length: 66 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + Math.round(i * 365 / 65));
    return {
      date: d.toISOString().slice(0, 10),
      buy_iv: 0.2 + (i % 20) * 0.001,
      sell_iv: 0.22 + (i % 20) * 0.001,
      atm_iv: 0.25,
      normalized_skew: 0.08 + i * 0.0001,
    };
  });
}

function ivMetrics(points: ReturnType<typeof ivPoints>) {
  const last = points[points.length - 1];
  return {
    normalized_skew: { value: last.normalized_skew, percentile: 0.62,
                       count: 45, trend_4w: 0.006, trend_base_count: 6 },
    buy_iv: { value: last.buy_iv, percentile: 0.41, count: 45,
             trend_4w: -0.012, trend_base_count: 6 },
    sell_iv: { value: last.sell_iv, percentile: 0.55, count: 45,
              trend_4w: -0.004, trend_base_count: 6 },
    atm_iv: { value: last.atm_iv, percentile: 0.5, count: 45,
             trend_4w: 0, trend_base_count: 6 },
  };
}

test("Historical IV 一年走勢圖：桌面 hover 資料點顯示 tooltip（#140）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    const points = ivPoints();
    return route.fulfill({ json: {
      candidate_key: "k", status: "ok", points,
      metrics: ivMetrics(points),
      observations: points.length, note: null,
    } });
  });

  await page.goto("/#/s/s1");
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  const chart = block.locator(".iv-trend-chart").first();
  await expect(chart).toBeVisible();
  const point = chart.getByRole("button").first();

  await expect(chart.locator(".chart-tooltip")).toHaveCount(0);
  await point.hover();
  await expect(chart.locator(".chart-tooltip")).toBeVisible();

  await page.mouse.move(0, 0);
  await expect(chart.locator(".chart-tooltip")).toHaveCount(0);
});

test("Historical IV 一年走勢圖：桌面寬螢幕下三張圖（Ĝ＋買腿＋賣腿）都完整可讀（#140／#141）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) => {
    const points = ivPoints();
    return route.fulfill({ json: {
      candidate_key: "k", status: "ok", points,
      metrics: ivMetrics(points),
      observations: points.length, note: null,
    } });
  });

  await page.goto("/#/s/s1");
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  const charts = block.locator(".iv-trend-chart");
  await expect(charts).toHaveCount(3);

  // 幾何驗證：頭條（Ĝ）的圖比次層（買／賣腿）寬——主位大圖、次層較小
  // 但資訊完整，是 spec #137 §5 的資訊層級規格，不是只靠字級表現。
  const primaryBox = (await block.locator(".iv-primary .iv-trend-chart")
    .boundingBox())!;
  const secondaryBoxes = await charts.evaluateAll((els) =>
    els.filter((el) => !el.closest(".iv-primary"))
      .map((el) => el.getBoundingClientRect().width));
  expect(secondaryBoxes).toHaveLength(2);
  for (const w of secondaryBoxes) {
    expect(primaryBox.width).toBeGreaterThan(w);
  }

  // 每張圖都落在卡片邊界內——桌面寬版面下不會被裁切或溢出。
  const cardBox = (await block.boundingBox())!;
  for (const chart of await charts.all()) {
    const box = (await chart.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(cardBox.x - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
  }
});

test("Heatmap ±% 在最右欄：桌面 viewport 每一列都看得到完整格式" +
     "（決策 M／#109，位置修正 QA-FIX-1／QA-01）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  // QA-FIX-1：欄順序＝價格 → 日期格 → ±%。用實際的幾何位置驗證，
  // 不是只看文字存在——這正是原本漏掉、讓 ±% 誤掛在左側價格欄裡
  // 也能通過的那一種斷言。
  const firstRow = table.locator("tbody tr").first();
  const priceBox = (await firstRow.locator("th.heatmap-price").boundingBox())!;
  const moveBox = (await firstRow.locator("td.heatmap-move-pct").boundingBox())!;
  const lastCellBox = (await firstRow.locator("td:not(.heatmap-move-pct)")
    .last().boundingBox())!;
  expect(moveBox.x).toBeGreaterThan(priceBox.x);
  expect(moveBox.x).toBeGreaterThan(lastCellBox.x);
  // 欄標題也要在，否則語意表格的欄數對不上
  await expect(table.locator("th.heatmap-move-head")).toHaveText("vs 現價");

  // 數字取自契約樣本 baseline 候選的 `matrix.prices`（spot=100、
  // target=130 → +30.0%／+0.0%）。QA 修正拿掉了「深跌」那個標記，
  // 最低那一列改用「最後一列」定位，不再靠標記字串找列。
  // 完整／短格式兩個 span 都在 DOM 裡（CSS 切換顯示），所以斷言要指名
  // 看得見的那一個——對整個 `<td>` 下 toHaveText 會拿到兩者相連的
  // textContent（"+30.0%+30%"）。
  const moveCellOf = (tag: string) =>
    table.locator("tr").filter({ hasText: tag }).locator("td.heatmap-move-pct");
  const fullOf = (tag: string) =>
    moveCellOf(tag).locator(".heatmap-move-pct-full");
  await expect(fullOf("目標")).toHaveText("+30.0%");
  await expect(fullOf("目標")).toBeVisible();
  await expect(fullOf("現價")).toHaveText("+0.0%");
  await expect(table.locator("tbody tr").last()
    .locator("td.heatmap-move-pct .heatmap-move-pct-full"))
    .toHaveText("-10.0%");
  // 「超標」「深跌」兩個標記已從引擎移除，整張表不該再出現
  await expect(table.getByText("超標")).toHaveCount(0);
  await expect(table.getByText("深跌")).toHaveCount(0);
  // 短格式（Mobile 才用）此時不可見，證明桌面版真的換成完整格式。
  await expect(moveCellOf("目標").locator(".heatmap-move-pct-short"))
    .not.toBeVisible();

  // 不只錨點列——每一列（含沒有特殊標記的內插列）都有自己的 ±% 欄。
  const rows = await table.locator("tbody tr").all();
  expect(rows.length).toBeGreaterThan(4);
  for (const row of rows) {
    await expect(row.locator("td.heatmap-move-pct")).toBeVisible();
  }
});

test("Crossover Boundary（#116）：桌面 viewport 圖例與邊界標示可見，" +
     "既有 ±% 欄與橫向捲動不受影響", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  // 圖例：格子仍是 Spread 報酬、邊界是兩者相等處、comparator 標籤與成本。
  await expect(mainChart.getByText(/格子是 Spread 報酬率/)).toBeVisible();
  await expect(mainChart.getByText(/報酬相等的分界/)).toBeVisible();
  await expect(mainChart.getByText(/Long Call|Long Put/).first()).toBeVisible();
  // QA 修正：兩側各是誰較高必須明講，而且方向由實際矩陣算出來
  // ——所以只鎖「X 較高，Y 較高」這個句型，不寫死是哪一端。
  await expect(mainChart.locator(".crossover-sides")).toBeVisible();
  await expect(mainChart.locator(".crossover-sides"))
    .toHaveText(/Spread 較高，.*(Long Call|Long Put) 較高/);

  // 邊界確實畫在網格上（契約樣本的 baseline 候選有真實交叉）——不是
  // 每次都落在「網格外」那個分支。
  const marked = table.locator("td.heatmap-crossover-cell");
  await expect(marked.first()).toBeVisible();

  // #109／QA-FIX-1 的 ±% 欄仍在、仍是每列最右邊——overlay 沒有蓋掉它。
  await expect(table.locator("th.heatmap-move-head")).toHaveText("vs 現價");
  const firstRow = table.locator("tbody tr").first();
  const moveBox = (await firstRow.locator("td.heatmap-move-pct").boundingBox())!;
  const lastCellBox = (await firstRow.locator("td:not(.heatmap-move-pct)")
    .last().boundingBox())!;
  expect(moveBox.x).toBeGreaterThan(lastCellBox.x);

  // 格子文字（報酬率數字）沒有被 overlay 蓋掉或改寫。
  await expect(firstRow.locator("td:not(.heatmap-move-pct)").first())
    .toHaveText(/^-?\d+$/);
});

test("Heatmap 密度（#121）：去掉 +／% 縮小 padding 後，固定容器寬度下" +
     "看得到的日期欄數真的變多", async ({ page }) => {
  // 實測基準（本票施工時量到，git stash 對照修正前後）：容器
  // clientWidth 876px 不變，平均欄寬 60.92px→45.65px，可見欄數
  // 14→19。門檻抓 17（介於兩者之間留餘裕，避免慢速機器像素微差
  // 誤判），能通過就代表密度確實提升，不是感覺上變窄。
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  const firstRow = table.locator("tbody tr").first();
  const dateCells = firstRow.locator("td:not(.heatmap-move-pct)");
  const n = await dateCells.count();
  const firstBox = (await dateCells.first().boundingBox())!;
  const lastBox = (await dateCells.nth(n - 1).boundingBox())!;
  const avgCellWidth = (lastBox.x + lastBox.width - firstBox.x) / n;
  const containerWidth = await mainChart.locator(".heatmap-scroll")
    .evaluate((el) => (el as HTMLElement).clientWidth);

  const columnsVisible = Math.floor(containerWidth / avgCellWidth);
  expect(columnsVisible).toBeGreaterThanOrEqual(17);

  // 每一格文字本身確實不再帶 +／%（否認式：格式沒改回去，密度提升
  // 不是靠別的手法湊出來的）。
  const cellText = (await dateCells.first().textContent())!;
  expect(cellText).not.toMatch(/[+%]/);
});

test("Heatmap 橫向捲到底時，左側價格與最右 ±% 都還釘在畫面上" +
     "（QA-FIX-1 sticky 兩端）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");

  const mainChart = page.locator("section").filter({ hasText: "劇本主圖" }).first();
  const scroll = mainChart.locator(".heatmap-scroll");
  const table = mainChart.locator("table.heatmap-table");
  await expect(table).toBeVisible();

  const box = await scroll.evaluate((el) => ({
    scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
  // 內容比容器寬才談得上「捲動後還看不看得到」——不夠寬就跳過，
  // 不假裝驗過（桌面 detail-pane 較寬，欄少時可能塞得下）。
  if (box.scrollWidth > box.clientWidth) {
    await scroll.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
    const firstRow = table.locator("tbody tr").first();
    const viewport = (await scroll.boundingBox())!;
    const priceBox = (await firstRow.locator("th.heatmap-price").boundingBox())!;
    const moveBox = (await firstRow.locator("td.heatmap-move-pct").boundingBox())!;
    // 兩端都仍落在可視容器範圍內
    expect(priceBox.x).toBeGreaterThanOrEqual(viewport.x - 1);
    expect(moveBox.x + moveBox.width).toBeLessThanOrEqual(
      viewport.x + viewport.width + 1);
  }
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
  // QA 修正後劇本庫卡片也印現價，同一個數字在左欄每張卡上都有一份
  // ——要驗的是右側詳細頁那個，locator 必須 scope 回 detail-pane。
  await expect(page.locator(".detail-pane")
    .getByText(`$${sample.meta.spot.toFixed(2)}`).first()).toBeVisible();

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
  // QA 修正後劇本庫卡片也印現價，同一個數字在左欄每張卡上都有一份
  // ——要驗的是右側詳細頁那個，locator 必須 scope 回 detail-pane。
  await expect(page.locator(".detail-pane")
    .getByText(`$${sample.meta.spot.toFixed(2)}`).first()).toBeVisible();
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

test("詳細頁密度：桌面一屏能看到的比例明顯提高（QA-FIX-3／QA-01）",
     async ({ page }) => {
  await routeTwoScenarios(page);
  await page.goto("/#/s/s1");
  await expect(page.locator(".detail-pane .card").first()).toBeVisible();

  // 只驗結構性密度，不驗任何像素間距數值——跟 #108 劇本庫瘦身、
  // #82 手機 compact row 同一套測試哲學。
  // QA-01 量測基準：同一份契約樣本下 scrollHeight 2668px ÷ 800px
  // 視窗 ＝ 3.33 螢幕，該輪壓到 3.00。QA 修正把頂部三卡合一之後實測
  // 2402px→1989px ＝ 2.49 螢幕，門檻跟著收到 2.70（介於兩者之間留
  // 餘裕），把這一輪的改善釘住、不讓它日後被無聲吃回去。
  const vh = page.viewportSize()!.height;
  const total = await page.locator(".detail-pane .screen")
    .evaluate((el) => el.scrollHeight);
  expect(total / vh).toBeLessThan(2.70);

  // 資訊一項不減少：QA 修正把「劇本摘要／基準候選／進場成本」三張卡
  // 合成一張，十一項全部都要還在——合併是為了壓高度，不是砍資訊。
  const summary = page.locator(".detail-pane .summary-card").first();
  for (const label of ["策略", "現價", "目標價", "目標年月",
                      "買腿 Ask", "賣腿 Bid", "淨成本",
                      "資料時間", "資料來源"]) {
    await expect(summary.getByText(label, { exact: true })).toBeVisible();
  }
  // 候選身分與名次在標頭那一行，跟著一起搬過來了。`exact` 是必要的：
  // 候選池過少的警語同一張卡裡也提到「第 1 名」。
  await expect(summary.getByText("第 1 名", { exact: true })).toBeVisible();
  await expect(summary.locator(".summary-title")).toBeVisible();

  // 真的排成多欄（同一視覺列的兩格 y 相同、x 不同），不是只是變窄。
  const stats = summary.locator(".stat");
  const a = (await stats.nth(0).boundingBox())!;
  const b = (await stats.nth(1).boundingBox())!;
  expect(Math.abs(a.y - b.y)).toBeLessThan(2);
  expect(b.x).toBeGreaterThan(a.x);

  // Heatmap 格子字級：QA 修正明文要求「格子再縮小、降低 padding」，
  // 13px→12px 是那一輪刻意調的值，不是被密度壓縮波及的副作用。12px
  // 同時是這張表的可讀性下限——再小就不該無聲往下調。
  await expect(page.locator(".detail-pane .heatmap-table td").first())
    .toHaveCSS("font-size", "12px");
});

/**
 * QA-FIX-4（QA-01）：批次操作列在桌面必須吸底。
 *
 * 刻意用 boundingBox 對照 viewport 幾何，**不用** `isVisible()`——
 * 後者只代表「有版面框、非 display:none」，元素捲到畫面外一千像素
 * 它照樣回報 true，這正是原本 e2e 沒抓到這個問題的原因。
 */
async function expectBatchBarInViewport(page: import("@playwright/test").Page) {
  const bar = page.locator(".batch-action-bar");
  await expect(bar).toBeVisible();
  const vh = page.viewportSize()!.height;
  const box = (await bar.boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(vh + 1);
}

test("桌面垃圾桶：全選後批次動作立刻在視窗內可操作（QA-FIX-4／QA-01）",
   async ({ page }) => {
  // 夠多筆才會把批次列推到一屏之外——這正是回報的情境。
  const trashed = Array.from({ length: 8 }, (_, i) => libraryRow({
    id: `s${i}`, symbol: `SYM${i}`, target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00" }));
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/scenarios?include_archived=true", (route) =>
    route.fulfill({ json: trashed }));

  await page.goto("/#/trash");
  await page.getByRole("button", { name: "全選" }).click();
  await expect(page.getByText("已選 8 個")).toBeVisible();

  await expectBatchBarInViewport(page);
  // 兩顆動作鈕本身也要在視窗內，不是只有那條列勉強露出來
  const vh = page.viewportSize()!.height;
  for (const name of ["還原已選", "永久刪除已選"]) {
    const btn = (await page.getByRole("button", { name }).boundingBox())!;
    expect(btn.y + btn.height).toBeLessThanOrEqual(vh + 1);
  }
});

test("桌面主劇本庫：批次選取後動作列同樣吸底（QA-FIX-4／QA-01）",
   async ({ page }) => {
  const rows = Array.from({ length: 10 }, (_, i) =>
    libraryRow({ id: `s${i}`, symbol: `SYM${i}`,
                 latest_analyzed_at: null, best_return: null }));
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: rows }));
  await page.route("**/api/scenarios/*/refresh", (route, req) =>
    route.fulfill({ json: rows.find((r) => req.url().includes(`/${r.id}/`)) }));

  await page.goto("/");
  await expect(page.getByRole("listitem").first()).toBeVisible();
  await page.getByRole("button", { name: "選取要移入垃圾桶的劇本" }).click();
  await page.getByRole("link", { name: /SYM0/ }).click();
  await expect(page.getByText("已選 1 個")).toBeVisible();

  await expectBatchBarInViewport(page);
});

/* ---------- 設定頁（Settings／#124） ---------- */

const settingsView = {
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

const settingsSaved = {
  ...settingsView,
  market_data: { mode: "custom", provider: "marketdata-app", default_label: "Cboe" },
  credentials: {
    "marketdata-app": {
      configured: true, masked: "••••••••abcd",
      updated_at: "2026-08-12T00:00:00+00:00",
      status: "unverified", reason: null, checked_at: null,
    },
  },
};

async function routeSettings(page: import("@playwright/test").Page) {
  await routeTwoScenarios(page);
  let saved = false;
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PUT") saved = true;
    return route.fulfill({ json: saved ? settingsSaved : settingsView });
  });
  await page.route("**/api/settings/credentials/**", (route) => {
    saved = true;
    return route.fulfill({ json: settingsSaved });
  });
  // Settings 現在也掛著 Diagnostics 區塊（DG-06／#149）——預設回空
  // 清單，需要非空清單的測試自己再覆蓋這個 route。
  await page.route("**/api/diagnostics*", (route) => route.fulfill({ json: [] }));
}

test("桌面版的設定入口固定在 sidebar 最下方，內容開在右側工作區", async ({ page }) => {
  await routeSettings(page);
  await page.goto("/");

  const entry = page.getByRole("link", { name: "設定" });
  await expect(entry).toBeVisible();

  // 「最下方」：入口的位置在左欄劇本清單之下。
  const list = page.locator(".library-scroll");
  const entryBox = (await entry.boundingBox())!;
  const listBox = (await list.boundingBox())!;
  expect(entryBox.y).toBeGreaterThanOrEqual(listBox.y + listBox.height - 1);

  await entry.click();
  await expect(page.getByText("Data / API")).toBeVisible();
  // 左欄劇本庫仍在（右側工作區才是被替換的那一邊）
  await expect(page.getByRole("link", { name: /ABC/ })).toBeVisible();
});

test("桌面版：切到自訂、存 token，畫面只顯示遮罩", async ({ page }) => {
  await routeSettings(page);
  await page.goto("/#/settings");

  const md = page.getByRole("region", { name: "Market Data" });
  await expect(md.getByText("預設：Cboe")).toBeVisible();
  await md.getByRole("radio", { name: "自訂" }).click();

  await expect(md.getByText("目前支援：Market Data App")).toBeVisible();
  await expect(md.getByText("需自行申請 API Token")).toBeVisible();

  await md.getByLabel("API Token").fill("tok-secret-abcd");
  await md.getByRole("button", { name: "儲存" }).click();

  await expect(md.getByText("已儲存 ••••••••abcd")).toBeVisible();
  // 完整 token 不得留在畫面上
  await expect(page.locator("body")).not.toContainText("tok-secret-abcd");
});

test("桌面版：測試連線走完未設定 → 尚未驗證 → 已連線（Settings／#125）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  const base = {
    supported_providers: [{ id: "marketdata-app", label: "Market Data App" }],
    market_data: {
      mode: "custom", provider: "marketdata-app", default_label: "Cboe",
    },
    historical_iv: { mode: "default", provider: null, default_label: "無" },
    updated_at: null,
  };
  const unset = {
    ...base,
    credentials: {
      "marketdata-app": {
        configured: false, masked: null, updated_at: null,
        status: "unset", reason: null, checked_at: null,
      },
    },
    market_data_effective: {
      source: "Cboe", fallback: true,
      reason: "Market Data App 尚未設定 token，改用預設來源",
    },
  };
  const unverified = {
    ...base,
    credentials: {
      "marketdata-app": {
        configured: true, masked: "••••••••abcd",
        updated_at: "2026-08-12T00:00:00+00:00",
        status: "unverified", reason: null, checked_at: null,
      },
    },
    market_data_effective: {
      source: "Cboe", fallback: true,
      reason: "Market Data App 尚未測試連線，改用預設來源",
    },
  };
  const connected = {
    ...base,
    credentials: {
      "marketdata-app": {
        configured: true, masked: "••••••••abcd",
        updated_at: "2026-08-12T00:00:00+00:00",
        status: "ok", reason: null,
        checked_at: "2026-08-12T01:00:00+00:00",
      },
    },
    market_data_effective: {
      source: "Market Data App", fallback: false, reason: null,
    },
  };

  // 三個階段的形狀相同、欄位值不同；`any` 沿用本檔案既有慣例
  // （見檔頭的 `const sample: any`），不讓 TS 從第一個字面值
  // 推出過窄的型別。
  let stage: any = unset;
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: stage }));
  await page.route("**/api/settings/credentials/*/test", (route) => {
    stage = connected;
    return route.fulfill({ json: connected });
  });
  await page.route("**/api/settings/credentials/marketdata-app", (route) => {
    stage = unverified;
    return route.fulfill({ json: unverified });
  });
  await page.route("**/api/diagnostics*", (route) => route.fulfill({ json: [] }));

  await page.goto("/#/settings");
  const md = page.getByRole("region", { name: "Market Data" });

  // 狀態列鎖定 `.settings-status`：fallback 提示裡也有「尚未設定 token」
  // 字樣，用純文字比對會同時命中兩處。
  const status = md.locator(".settings-status");

  // 未設定：測試連線按不下去，而且已經誠實說明現在其實用的是 Cboe
  await expect(status).toContainText("未設定");
  await expect(md.getByRole("button", { name: "測試連線" })).toBeDisabled();
  await expect(md.getByText(/目前使用 Cboe/)).toBeVisible();

  // 存了 token → 尚未驗證（不是「已連線」）
  await md.getByLabel("API Token").fill("tok-secret-abcd");
  await md.getByRole("button", { name: "儲存" }).click();
  await expect(status).toContainText("尚未驗證");

  // 測試連線 → 已連線，fallback 提示消失
  await md.getByRole("button", { name: "測試連線" }).click();
  await expect(status).toContainText("已連線");
  await expect(md.getByText(/目前使用 Cboe/)).toHaveCount(0);
});

test("桌面版：Settings 的 Diagnostics 區塊可讀可操作（DG-06／#149）",
   async ({ page }) => {
  await routeSettings(page);
  let events: unknown[] = [{
    event_id: "evt-e2e-desktop", correlation_id: "cid-e2e-desktop",
    ts: "2026-08-15T00:00:00+00:00", subsystem: "historical_iv",
    stage: "vendor_fetch", severity: "error",
    message: "vendor 連線失敗", context: { http_status: 429 },
  }];
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
  await expect(section.getByText("vendor_fetch")).toBeVisible();
  await expect(section.getByText("錯誤")).toBeVisible();
  await expect(section.getByText("vendor 連線失敗")).toBeVisible();

  await section.getByText("vendor 連線失敗").click();
  await expect(section.getByText("evt-e2e-desktop")).toBeVisible();
  await expect(section.getByText("http_status")).toBeVisible();

  await section.getByRole("button", { name: "Clear diagnostics" }).click();
  await section.getByRole("button", { name: "確定清除" }).click();
  await expect(section.getByText("目前沒有紀錄")).toBeVisible();
});

test("桌面版：編輯劇本沿用工作區上方的既有表單，取消隨時可按（#132）",
   async ({ page }) => {
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

  await page.goto("/");
  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await expect(page.getByText("編輯劇本")).toBeVisible();
  await expect(page.getByLabel("標的代號")).toBeDisabled();

  // 打到一半、內容不合法時仍然可以取消
  await page.getByLabel("目標價位").fill("abc");
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByText("編輯劇本")).toHaveCount(0);
  expect(patched).toEqual([]);

  // 再進去改一次並存檔
  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await page.getByLabel("目標價位").fill("120");
  await page.getByRole("button", { name: "儲存變更" }).click();
  await expect(page.getByText("編輯劇本")).toHaveCount(0);
  expect(patched).toHaveLength(1);
});
