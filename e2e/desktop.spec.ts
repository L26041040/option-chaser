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
  // 開站的批次刷新（時機一，T08／#196）打的是 Refresh Run，一次帶兩個
  // id、一次回應涵蓋兩筆——不是各自打一次 `/refresh`。
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: {
      results: [{ scenario_id: "s1", ok: true, row: rowA },
               { scenario_id: "s2", ok: true, row: rowB }],
      remaining: [],
    } }));
  // 卡片重試／詳細頁手動刷新走的是單一劇本端點，維持原樣。
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

/* ---------- Historical IV 一年走勢圖：桌面版（#140／#141；exact-contract
   逐腿卡片：HIVT-02–05／#153–156，spec #151） ---------- */

/** 貼近真實密度（引擎 `sampling_schedule` 全年約 55–75 點）——見
 *  `smoke.spec.ts` 同名函式的說明：250 點塞進走勢圖會讓相鄰資料點的
 *  可點擊圓圈嚴重疊在一起，連自動化都點不準。
 *
 *  **回應形狀（HIVT-04／05 之後）**：不再有共用的 `points`／
 *  `metrics.{buy,sell,atm}_iv`——Normalized Skew 家族只剩
 *  `normalized_skew_points`／`metrics.normalized_skew`；買／賣腿改成
 *  `legs.buy`／`legs.sell` 兩份各自獨立的 exact-contract 序列
 *  （`src/IvTrend.tsx`）。跟 `smoke.spec.ts` 同一套建構函式，各自維護
 *  一份是因為兩個檔案本來就不共用 fixture（見各自檔頭說明）。 */
function ivDates() {
  const start = new Date("2025-08-15T00:00:00Z");
  return Array.from({ length: 66 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + Math.round(i * 365 / 65));
    return d.toISOString().slice(0, 10);
  });
}

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

/** 一隻腳（買腿或賣腿）的完整 exact-contract 歷史 IV。預設值對齊舊版
 *  `buy_iv` 那組假資料（percentile 0.41、Δ4w -0.012）。 */
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

const SELL_CONTRACT = { underlying: "XYZ", expiration: "2026-09-18", strike: 125,
                        option_type: "call", contract_symbol: "XYZ260918C00125000" };

/** 一份「一切正常」的完整 Historical IV 回應——兩腿都有完整歷史，
 *  Normalized Skew 也有完整歷史。 */
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

/** 點開 Advanced／Diagnostics 收合區（SIG-02／#173）——z-score 文字、
 *  Normalized Skew 整組、inline diagnostics 都收在裡面，預設收合時
 *  Playwright 判定為真正的 `display: none`，既有測試裡驗這些內容可見，
 *  都得先點開才看得到。 */
async function openAdvanced(block: import("@playwright/test").Locator) {
  await block.getByText("Advanced／Diagnostics").click();
}

test("Historical IV 一年走勢圖：桌面滑鼠移動時顯示 tooltip（#140；整張圖是單一" +
     "scrubber 介面，需求方 2026-08-22 反饋——不再靠逐點命中）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse() }));

  await page.goto("/#/s/s1");
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  const chart = block.locator(".iv-trend-chart").first();
  await expect(chart).toBeVisible();
  // 不再有逐點命中圓點——整張 SVG 是互動介面，滑鼠移到圖上任何位置都該
  // 找到最近的資料點。
  await expect(chart.getByRole("button")).toHaveCount(0);

  await expect(chart.locator(".chart-tooltip")).toHaveCount(0);
  await chart.hover();
  await expect(chart.locator(".chart-tooltip")).toBeVisible();

  await page.mouse.move(0, 0);
  await expect(chart.locator(".chart-tooltip")).toHaveCount(0);
});

test("Historical IV：桌面買／賣腿卡片並排、兩張走勢圖等寬且落在卡片邊界內" +
     "（#140／#141；SIG-02／#173 起 Normalized Skew 移出主要區塊、改用" +
     "買／賣腿驗證桌面並排幾何——Advanced 裡的 Normalized Skew 圖收合時" +
     "不佔版面，不計入這裡）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse() }));

  await page.goto("/#/s/s1");
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  // 買／賣腿卡片是主要區塊，不必展開 Advanced 就看得到——只算
  // `.iv-trend-legs` 底下的兩張圖，Advanced 裡收合的 Normalized Skew
  // 圖不計入（那張圖本身仍在 DOM 裡，只是收合、不佔版面）。
  const charts = block.locator(".iv-trend-legs .iv-trend-chart");
  await expect(charts).toHaveCount(2);

  const widths = await charts.evaluateAll((els) =>
    els.map((el) => el.getBoundingClientRect().width));
  expect(widths).toHaveLength(2);
  expect(Math.abs(widths[0] - widths[1])).toBeLessThan(1);

  // 桌面既有斷點（SIG-02／#173）：買／賣卡片並排——同一列（y 相近）、
  // 不同欄（賣腿在買腿右邊）。
  const legCards = block.locator(".iv-trend-card");
  const buyBox = (await legCards.nth(0).boundingBox())!;
  const sellBox = (await legCards.nth(1).boundingBox())!;
  expect(Math.abs(buyBox.y - sellBox.y)).toBeLessThan(2);
  expect(sellBox.x).toBeGreaterThan(buyBox.x);

  // 每張圖都落在卡片邊界內——桌面寬版面下不會被裁切或溢出。
  const cardBox = (await block.boundingBox())!;
  for (const chart of await charts.all()) {
    const box = (await chart.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(cardBox.x - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
  }
});

/* ---------- 固定版位＋Inline Diagnostics Copy 按鈕（QA 反饋，2026-08-16） ---------- */

test("桌面版：Historical IV 卡片一開始就在，loading 時原位顯示骨架，資料回來後原位換成走勢圖" +
     "（不因 request 完成才決定要不要出現）", async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));

  let releaseIv!: () => void;
  const ivGate = new Promise<void>((resolve) => { releaseIv = resolve; });
  await page.route("**/api/scenarios/*/iv-history*", async (route) => {
    await ivGate;
    return route.fulfill({ json: fullIvResponse() });
  });

  await page.goto("/#/s/s1");

  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();
  await expect(block.getByText("IV 相對位置")).toBeVisible();
  await expect(block.locator(".iv-skeleton")).toBeVisible();

  releaseIv();
  // 骨架換成真正的主要內容（買腿卡片，SIG-02／#173 後不必展開 Advanced
  // 就看得到）——不是靠 Normalized Skew（現在收在 Advanced 裡）判斷。
  await expect(block.getByText("買腿", { exact: true })).toBeVisible();
  await expect(block.locator(".iv-skeleton")).toHaveCount(0);
});

test("桌面版：Inline Diagnostics 的 Copy 按鈕——版面順序、複製內容、收合展開行為" +
     "（DG-05／#148 延伸，QA 反饋 2026-08-16）", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  const diagEvent = {
    event_id: "evt-e2e-1", correlation_id: "cid-e2e-1",
    ts: "2026-08-15T00:00:00+00:00", subsystem: "historical_iv",
    stage: "payload_parse", severity: "warning",
    // PC-03（#201）：`user_facing` 鏡射 severity——這是餵進
    // `IvHistory` 的 `notableEvents` 過濾，缺這個欄位會讓 Inline
    // Diagnostics 面板失去觸發條件。
    user_facing: true,
    message: "raw_rows > 0 but parsed rows are 0",
    context: { raw_rows: 5, parsed_call_rows: 0 },
  };
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      diagnostics: { correlation_id: "cid-e2e-copy", events: [diagEvent] },
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

  const copyBox = (await copyButton.boundingBox())!;
  const fieldBox = (await fieldLabel.boundingBox())!;
  expect(copyBox.y).toBeLessThan(fieldBox.y);

  await copyButton.click();
  await expect(block.getByRole("button", { name: "已複製" })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  const parsed = JSON.parse(copied);
  expect(parsed.correlation_id).toBe("cid-e2e-copy");
  expect(parsed.events[0].event_id).toBe("evt-e2e-1");

  const details = block.locator(".iv-diagnostics");
  const isOpen = () => details.evaluate((el) => (el as HTMLDetailsElement).open);
  expect(await isOpen()).toBe(true);
  await summary.click();
  expect(await isOpen()).toBe(false);
});

/* ---------- HIVT-07（#158）桌面 viewport 對等補齊：smoke.spec.ts 已有
   對應的手機版斷言，這裡補桌面版，兩邊各自獨立驗證同一批事實。 ---------- */

test("桌面版 Historical IV：買／賣腿讀到的是各自 exact contract 的真實觀測——現值與百分位" +
     "在 DOM 上讀出兩個確實不同的數字，不是共用同一份序列複製兩份（HIVT-07／" +
     "#158，story #1–#4：不跨 strike／不跨 expiration 替代，要看得見）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      legs: {
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

  const buyValue = await buyCard.locator(".iv-value-primary").textContent();
  const sellValue = await sellCard.locator(".iv-value-primary").textContent();
  expect(buyValue).toBe("20.5%");
  expect(sellValue).toBe("32.5%");
  expect(buyValue).not.toBe(sellValue);

  await expect(buyCard.getByText(/第 41 百分位/)).toBeVisible();
  await expect(sellCard.getByText(/第 55 百分位/)).toBeVisible();
});

test("桌面版 Historical IV：z-score／moving average／Bollinger 帶三項統計量在頁面上" +
     "真的可見（geometry／caption 斷言），寬版面下線段一樣量得出實際寬高" +
     "（HIVT-07／#158，story #8／#9／#10／#11／#12）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  const dates = ivDates();
  // 跟 smoke.spec.ts 同理：用有斜率的序列，避免固定值移動平均線在圖上
  // 塌成零高度的水平線，讓幾何斷言不穩定。
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
  // z-score 文字搬進 Advanced（SIG-02／#173），先展開才看得到。
  await openAdvanced(block);
  await expect(block.getByText(/Z-score \+0\.30/).first()).toBeVisible();

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

test("桌面版 Historical IV：買／賣腿各自的 vendor／quota 狀態獨立顯示，不受 Normalized " +
     "Skew 家族自己的 status 影響，也不擋住頁面其他部分（HIVT-07／#158，" +
     "story #32；spec #151 §4「兩個家族的 backfill 狀態各自獨立」）",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({
      status: "ok",
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
  await expect(block.getByText(/今日 API 額度已用完/)).toHaveCount(1);

  await expect(block.locator(".iv-trend-chart")).toHaveCount(3);
  await expect(page.getByText("劇本主圖")).toBeVisible();
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

test("PC-05（#202）：鎖定卡片點下去路由不變——桌面版", async ({ page }) => {
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [rowA, rowB] }));
  await page.route("**/api/scenarios/s1", (route) =>
    route.fulfill({ json: { ...rowA, latest_result: sample } }));
  await page.route("**/api/scenarios/s2", (route) =>
    route.fulfill({ json: { ...rowB, latest_result: sample } }));
  await page.route("**/api/scenarios/refresh-run", async (route) => {
    // 刻意延遲，讓「更新中」＋反灰的狀態真的看得到，才點得下去測試。
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.fulfill({ json: {
      results: [{ scenario_id: "s1", ok: true, row: rowA },
               { scenario_id: "s2", ok: true, row: rowB }],
      remaining: [],
    } });
  });

  await page.goto("/");

  const abcLink = page.getByRole("link", { name: /ABC/ });
  await expect(abcLink).toBeVisible();
  const abcCard = page.locator(".compact-card").filter({ hasText: "ABC" });
  await expect(abcCard).toHaveClass(/locked/);

  const before = page.url();
  await abcLink.click();

  // 沒有導向詳細頁：網址沒變，右側工作區也還是空狀態，不是 s2 的內容。
  expect(page.url()).toBe(before);
  await expect(page.getByText(/選擇左側的劇本/)).toBeVisible();

  // 這一輪跑完後解鎖、正常可點——確認上面攔截到的是真的鎖定，不是這個
  // 候選本身結構上就到不了詳細頁。
  await expect(abcCard).not.toHaveClass(/locked/);
  await abcLink.click();
  await expect(page).toHaveURL(/#\/s\/s2$/);
});

test("2026-08-26 真機驗收：Refresh Run 逐張完成、逐張立即可用——桌面版",
  async ({ page }) => {
  const rowFor = (id: string, symbol: string) => libraryRow({
    id, symbol, latest_analyzed_at: null, best_return: null,
  });
  const rows = [rowFor("a", "AAA"), rowFor("b", "BBB"), rowFor("c", "CCC")];

  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: rows }));
  // 對齊真實後端的 Refresh Run Group Limit（預設 1）——同一套三階段
  // 劇本，桌面版驗一次確認不是只有手機版才有這個行為。
  await page.route("**/api/scenarios/refresh-run", async (route, req) => {
    const body = req.postDataJSON() as { scenario_ids: string[] };
    const ids = body.scenario_ids;
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (ids.length === 3) {
      return route.fulfill({ json: {
        results: [{ scenario_id: "a", ok: true,
          row: { ...rows[0], best_return: 1,
                 latest_analyzed_at: new Date().toISOString() } }],
        remaining: ["b", "c"],
      } });
    }
    if (ids.length === 2) {
      return route.fulfill({ json: {
        results: [{ scenario_id: "b", ok: false,
          stage: "fetch", message: "抓不到 BBB 的報價" }],
        remaining: ["c"],
      } });
    }
    return route.fulfill({ json: {
      results: [{ scenario_id: "c", ok: true,
        row: { ...rows[2], best_return: 0.25,
               latest_analyzed_at: new Date().toISOString() } }],
      remaining: [],
    } });
  });

  await page.goto("/");

  const aCard = page.locator(".compact-card").filter({ hasText: "AAA" });
  const bCard = page.locator(".compact-card").filter({ hasText: "BBB" });
  const cCard = page.locator(".compact-card").filter({ hasText: "CCC" });

  await expect(page.getByText("100.0%")).toBeVisible();
  await expect(aCard).not.toHaveClass(/locked/);
  await expect(bCard).toHaveClass(/locked/);
  await expect(cCard).toHaveClass(/locked/);

  await expect(page.getByText("抓不到 BBB 的報價")).toBeVisible();
  await expect(bCard).not.toHaveClass(/locked/);
  await expect(cCard).toHaveClass(/locked/);
  await expect(aCard).not.toHaveClass(/locked/);

  await expect(page.getByText("25.0%")).toBeVisible();
  await expect(cCard).not.toHaveClass(/locked/);
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
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: {
      results: rows.map((r) => ({ scenario_id: (r as { id: string }).id, ok: true, row: r })),
      remaining: [],
    } }));
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
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: {
      results: rows.map((r) => ({ scenario_id: (r as { id: string }).id, ok: true, row: r })),
      remaining: [],
    } }));
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
    stage: "vendor_fetch", severity: "error", user_facing: true,
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
  // 開站那一輪走批次端點（T08／#196）。
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: { results: [{ scenario_id: "s1", ok: true,
      row: current }], remaining: [] } }));

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

/* ---------- Strategy Family 勾選與 eligibility（T10／#227） ---------- */

test("桌面版：建立劇本一個 family 都沒勾就送出，擋在前端並說明原因（T10／#227）",
   async ({ page }) => {
  let postCount = 0;
  await page.route("**/api/scenarios", (route) => {
    if (route.request().method() === "POST") {
      postCount += 1;
      return route.fulfill({ status: 422, json: { detail: "不該送到這裡" } });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.getByText(/還沒有劇本/)).toBeVisible();

  await page.getByRole("button", { name: "＋ 建立劇本" }).click();
  await page.getByLabel("標的代號").fill("tlt");
  await page.getByLabel("目標價位").fill("120");
  await page.getByLabel("目標年月").click();
  await page.getByLabel("年份").fill("2028");
  await page.getByRole("button", { name: "5 月" }).click();
  await expect(page.getByRole("checkbox", { name: "Call / Put" }))
    .not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Vertical Spread" }))
    .not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Butterfly" }))
    .not.toBeChecked();

  await page.getByRole("button", { name: "建立", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("請至少勾選一個策略類型");
  await expect(page.getByText(/還沒有劇本/)).toBeVisible();
  expect(postCount).toBe(0);
});

test("桌面版：編輯表單顯示不可選的 family 與原因，checkbox 仍可勾選——" +
   "不做推薦／不推薦（T10／#227）", async ({ page }) => {
  const row = {
    ...libraryRow({ id: "s1", symbol: "TLT" }),
    strategies: ["vertical-spread"],
    family_eligibility: {
      "single-leg": { family: "single-leg", eligible: true, reason: null },
      "vertical-spread": { family: "vertical-spread", eligible: true,
                          reason: null },
      "butterfly": { family: "butterfly", eligible: false,
                    reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
    },
  };
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: [row] }));
  await page.route("**/api/scenarios/s1", (route) => route.fulfill({ json: row }));
  await page.route("**/api/scenarios/s1/refresh", (route) =>
    route.fulfill({ json: row }));
  await page.goto("/");

  await page.getByRole("button", { name: /編輯 TLT/ }).click();
  await expect(page.getByText("編輯劇本")).toBeVisible();

  await expect(page.getByRole("checkbox", { name: "Vertical Spread" }))
    .toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Call / Put" }))
    .not.toBeChecked();

  await expect(page.getByText(
    "這個策略家族目前還沒有任何已啟用的具體結構。")).toBeVisible();
  const butterflyBox = page.getByRole("checkbox", { name: /Butterfly/ });
  await expect(butterflyBox).toBeEnabled();
  await butterflyBox.check();
  await expect(butterflyBox).toBeChecked();

  for (const banned of ["推薦", "較適合", "Weak Fit"]) {
    await expect(page.getByText(banned)).toHaveCount(0);
  }
});

test("桌面版：編輯可以增減 family，儲存後送出目前完整的勾選集合（T10／#227）",
   async ({ page }) => {
  let current: any = { ...libraryRow({ id: "s1", symbol: "TLT" }),
                       strategies: ["vertical-spread"] };
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
  await page.getByRole("checkbox", { name: "Call / Put" }).check();
  await page.getByRole("button", { name: "儲存變更" }).click();

  await expect(page.getByText("編輯劇本")).toHaveCount(0);
  expect(patched).toHaveLength(1);
  expect(patched[0].strategies).toEqual(["vertical-spread", "single-leg"]);
});

/* ---------- T11（#229）：Strategy Family 分頁 ---------- */

/** 手造一份包含兩個 family 的 view——見 `smoke.spec.ts` 同名函式的
 *  說明，這裡是桌面版對照組，`results[0]` 同樣刻意是被方向閘門擋掉的
 *  那筆（真實回歸情境）。 */
function multiFamilyView() {
  const champKey = sample.results[0].expiry_top10[0].candidate_keys[0];
  const champ = sample.candidate_pool[champKey];
  const buyLeg = champ.legs.find((l: any) => l.side === "buy");
  const lc = {
    ...champ, candidate_key: "lc-key", strategy: "long-call",
    baseline_return: 0.2, comparator: null, legs: [buyLeg],
  };
  return {
    ...sample,
    results: [
      { strategy: "bear-put-spread", status: "skipped_direction", message: "跳過",
       n_qualified: 0, filter_report: null, filter_stages: [], quality_flags: [],
       pair_report: null, expiry_counts: [], expiry_top10: [], disclaimer_text: "" },
      ...sample.results,
      { strategy: "long-call", status: "ok", message: "", n_qualified: 1,
       filter_report: { total: 1, passed: 1 }, filter_stages: [], quality_flags: [],
       pair_report: null,
       expiry_counts: [[sample.baseline_expiry, 1]],
       expiry_top10: [{ expiry: sample.baseline_expiry, candidate_keys: ["lc-key"] }],
       disclaimer_text: "" },
    ],
    candidate_pool: { ...sample.candidate_pool, "lc-key": lc },
    family_eligibility: {
      "single-leg": { family: "single-leg", eligible: true, reason: null },
      "vertical-spread": { family: "vertical-spread", eligible: true, reason: null },
      "butterfly": { family: "butterfly", eligible: false,
                    reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
    },
  };
}

test("桌面版：多 family 並存——分頁列出、預設打開冠軍所屬 family、切換分頁"
     + "只換排名內容不影響頭條（T11／#229，Call/Put 端到端可用）",
   async ({ page }) => {
  const row = { ...libraryRow({ id: "s1", symbol: "XYZ" }),
               strategies: ["single-leg", "vertical-spread"] };
  const multi = multiFamilyView();
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [row] }));
  await page.route("**/api/scenarios/s1", (route) =>
    route.fulfill({ json: { ...row, latest_result: multi } }));
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: { results: [{ scenario_id: "s1", ok: true, row }],
                            remaining: [] } }));
  await page.goto("/#/s/s1");

  const detail = page.locator(".detail-pane");
  await expect(detail.getByText(/劇本主圖/)).toBeVisible();

  const tabs = detail.getByRole("group", { name: "策略家族" });
  await expect(tabs.getByRole("button")).toHaveCount(2);
  await expect(tabs.getByRole("button", { name: "Vertical Spread" }))
    .toHaveAttribute("aria-pressed", "true");

  const summary = detail.getByRole("region", { name: "劇本摘要" });
  await expect(summary.getByText("Bull Call Spread")).toBeVisible();

  await tabs.getByRole("button", { name: "Call / Put" }).click();
  await expect(tabs.getByRole("button", { name: "Call / Put" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(detail.getByText("Long Call").first()).toBeVisible();

  // 分頁切走了，頭條依然是冠軍，不隨分頁切換而改變。
  await expect(summary.getByText("Bull Call Spread")).toBeVisible();
});

/* ---------- SIG-04（#175）：Desktop 紅線鎖定 ---------- */

/** Spread IV Gap（SIG-01／#172）的完整回應區塊——跟這個檔案既有
 *  `legHistoricalIv()` 同一套「貼近真實密度」的假資料哲學。 */
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

test("SIG-04（#175）Desktop 紅線：買／賣腿卡片並排、Spread Summary 是第一層、" +
     "Advanced 預設收合，主要資訊不必展開就完整可見",
   async ({ page }) => {
  await routeTwoScenarios(page);
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { historical_iv_enabled: true } }));
  await page.route("**/api/scenarios/*/iv-history*", (route) =>
    route.fulfill({ json: fullIvResponse({ spread_gap: spreadGapFixture() }) }));

  await page.goto("/#/s/s1");
  const block = page.locator(".iv-history");
  await expect(block).toBeVisible();

  // Spread Summary 是卡片第一層——在 Buy／Sell 逐腿卡片之上。
  const summary = block.locator(".iv-spread-summary");
  const legCards = block.locator(".iv-trend-card");
  await expect(summary).toBeVisible();
  const summaryBox = (await summary.boundingBox())!;
  const legBox = (await legCards.first().boundingBox())!;
  expect(summaryBox.y).toBeLessThan(legBox.y);

  // 買／賣腿卡片並排：同一列（y 相近）、不同欄（賣腿在買腿右邊）。
  const buyBox = (await legCards.nth(0).boundingBox())!;
  const sellBox = (await legCards.nth(1).boundingBox())!;
  expect(Math.abs(buyBox.y - sellBox.y)).toBeLessThan(2);
  expect(sellBox.x).toBeGreaterThan(buyBox.x);

  // Advanced／Diagnostics 預設收合。
  const advanced = block.locator(".iv-advanced");
  const isOpen = () => advanced.evaluate((el) => (el as HTMLDetailsElement).open);
  expect(await isOpen()).toBe(false);

  // 主要資訊（Spread Summary＋Buy／Sell 層）不需要展開 Advanced 就完整
  // 可見——現值／走勢圖全部在外面，不必先點開任何東西。
  await expect(summary.locator(".iv-value-primary")).toBeVisible();
  await expect(summary.locator(".iv-trend-chart")).toBeVisible();
  await expect(legCards.nth(0).locator(".iv-value-primary")).toBeVisible();
  await expect(legCards.nth(1).locator(".iv-value-primary")).toBeVisible();
});
