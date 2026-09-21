import { expect, test } from "@playwright/test";

/** Seed Warm 頁面底色／主文字色的 `rgb(...)` 字面值——`--bg`／
 *  `--text` 兩個 token（`src/styles.css`）的計算值，#FBF7F0／#231F1B
 *  換算而來。淺色唯一，不再有深色一組數字。 */
const SEED_WARM_BG = "rgb(251, 247, 240)";
const SEED_WARM_TEXT = "rgb(35, 31, 27)";

/**
 * SW-01（#331）AC：「document.fonts 載入 Plus Jakarta Sans 與 Noto
 * Sans TC」——jsdom（Vitest）不會真的下載／套用 web font，這條驗收
 * 只能在真瀏覽器裡做，因此獨立成一個 e2e 檔案而非塞進元件測試。只需
 * 驗證一次、與 viewport 無關（純字型載入行為，不是版面），比照既有
 * 慣例（HIVT-07）不在 Desktop 專案重複驗證。
 *
 * `--proxy-server`：只在這個檔案（`test.use()`，不動全站共用的
 * `playwright.config.ts`）、只在 `HTTPS_PROXY` 這個環境變數存在時
 * 才加上——Chromium 不像 curl／shell 工具會自動讀 `HTTPS_PROXY`，
 * 這個沙箱本身對 Google Fonts CDN 的網路政策就是要走這個代理才通；
 * 真實 CI（GitHub Actions runner）沒有這個環境變數，這裡的條件式
 * 判斷會直接跳過、拿到跟其餘既有 e2e 完全相同的預設直連行為
 * ——不影響任何既有測試。 */
test.use({
  launchOptions: {
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      ...(process.env.HTTPS_PROXY
        ? [
            `--proxy-server=${process.env.HTTPS_PROXY}`,
            // 這個沙箱的出口代理對 HTTPS 做憑證代理（見系統環境說明的
            // CA bundle），沒有這個旗標時到 fonts.gstatic.com 的 TLS
            // 握手會失敗、字型檔靜默載入失敗（`document.fonts.load()`
            // 回空陣列，不是拋錯，很容易誤判成「字體真的沒設好」）。
            "--ignore-certificate-errors",
          ]
        : []),
    ],
    // `test.use({ launchOptions })` 整個覆蓋、不會跟
    // `playwright.config.ts` 專案層級的 `launchOptions` 深度合併
    // ——這裡必須重新帶一次 `executablePath`，否則會掉回 Playwright
    // 內建、這個沙箱沒下載過的瀏覽器版本。
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : {}),
  },
});

test.beforeEach(async ({ page }) => {
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/scenarios/refresh-run", (route) =>
    route.fulfill({ json: { results: [], remaining: [] } }));
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { role: "normal" } }));
});

test("Plus Jakarta Sans 與 Noto Sans TC 兩個 web font 真的 loaded（不是退回系統字）", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const statuses = await page.evaluate(async () => {
    // 主動 `load()` 兩個字重（400 拉丁、400 中文）比被動等頁面自然
    // 渲染觸發更確定——不必猜這個瞬間畫面上到底有沒有出現對應字元。
    const [jakarta, noto] = await Promise.all([
      document.fonts.load('400 16px "Plus Jakarta Sans"'),
      document.fonts.load('400 16px "Noto Sans TC"'),
    ]);
    return {
      jakartaLoadedAny: jakarta.length > 0,
      notoLoadedAny: noto.length > 0,
      jakarta: document.fonts.check('400 16px "Plus Jakarta Sans"'),
      noto: document.fonts.check('400 16px "Noto Sans TC"'),
    };
  });

  expect(statuses.jakartaLoadedAny).toBe(true);
  expect(statuses.notoLoadedAny).toBe(true);
  expect(statuses.jakarta).toBe(true);
  expect(statuses.noto).toBe(true);
});

test("body 實際套用的字型堆疊以 Plus Jakarta Sans 開頭，不是舊的 Geist", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const bodyFontFamily = await page.evaluate(
    () => getComputedStyle(document.body).fontFamily,
  );
  expect(bodyFontFamily).toContain("Plus Jakarta Sans");
  expect(bodyFontFamily).not.toContain("Geist");
});

test("body 實際套用的背景色與文字色是 Seed Warm token（token 換血生效）", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const tokens = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { bg: cs.backgroundColor, color: cs.color };
  });
  expect(tokens.bg).toBe(SEED_WARM_BG);
  expect(tokens.color).toBe(SEED_WARM_TEXT);
});

/* ---------- SW-01（#331）：淺色唯一，`prefers-color-scheme: dark`
   模擬下仍然是同一組暖色 token，證明不是靠無頭瀏覽器剛好強制淺色才
   測得到 ---------- */

test("SW-01（#331）：`prefers-color-scheme: dark` 下仍然套用 Seed Warm 的唯一一份淺色 token", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await page.waitForSelector(".screen");

  const tokens = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { bg: cs.backgroundColor, color: cs.color };
  });
  expect(tokens.bg).toBe(SEED_WARM_BG);
  expect(tokens.color).toBe(SEED_WARM_TEXT);
});
