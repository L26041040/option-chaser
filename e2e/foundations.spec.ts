import { expect, test } from "@playwright/test";

/** Obsidian Gold 頁面底色／主文字色的 `rgb(...)` 字面值——深色與淺色各
 *  一組，`--bg`／`--text` 兩個 token（`src/styles.css`）的計算值。兩條
 *  既有測試（字型換血驗證那條、下面 OG-12 新增的淺色驗證）都要拿同一組
 *  數字比對，抽成具名常數只寫一次，不是巧合各自敲對同一串數字
 *  （`/code-review` Standards 軸跟進）。 */
const OBSIDIAN_GOLD_DARK_BG = "rgb(11, 14, 17)";
const OBSIDIAN_GOLD_LIGHT_BG = "rgb(245, 245, 245)";
const OBSIDIAN_GOLD_LIGHT_TEXT = "rgb(30, 35, 41)";

/**
 * OG-01（#317）AC：「Geist＋Noto Sans TC 以網頁字型載入；用瀏覽器
 * `document.fonts` 可驗證兩者皆 loaded」——jsdom（Vitest）不會真的
 * 下載／套用 web font，這條驗收只能在真瀏覽器裡做，因此獨立成一個
 * e2e 檔案而非塞進元件測試。只需驗證一次、與 viewport 無關（純字型
 * 載入行為，不是版面），比照既有慣例（HIVT-07）不在 Desktop 專案
 * 重複驗證。
 *
 * `--proxy-server`：只在這個檔案（`test.use()`，不動全站共用的
 * `playwright.config.ts`）、只在 `HTTPS_PROXY` 這個環境變數存在時
 * 才加上——Chromium 不像 curl／shell 工具會自動讀 `HTTPS_PROXY`，
 * 這個沙箱本身對 Google Fonts CDN 的網路政策就是要走這個代理才通；
 * 真實 CI（GitHub Actions runner）沒有這個環境變數，這裡的條件式
 * 判斷會直接跳過、拿到跟其餘 131 條既有 e2e 完全相同的預設直連行為
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

test("Geist 與 Noto Sans TC 兩個 web font 真的 loaded（不是退回系統字）", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const statuses = await page.evaluate(async () => {
    // 主動 `load()` 兩個字重（400 拉丁、400 中文）比被動等頁面自然
    // 渲染觸發更確定——不必猜這個瞬間畫面上到底有沒有出現對應字元。
    const [geist, noto] = await Promise.all([
      document.fonts.load('400 16px "Geist"'),
      document.fonts.load('400 16px "Noto Sans TC"'),
    ]);
    return {
      geistLoadedAny: geist.length > 0,
      notoLoadedAny: noto.length > 0,
      geist: document.fonts.check('400 16px "Geist"'),
      noto: document.fonts.check('400 16px "Noto Sans TC"'),
    };
  });

  expect(statuses.geistLoadedAny).toBe(true);
  expect(statuses.notoLoadedAny).toBe(true);
  expect(statuses.geist).toBe(true);
  expect(statuses.noto).toBe(true);
});

test("body 實際套用的字型堆疊以 Geist 開頭，不是舊的 IBM Plex Sans", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const bodyFontFamily = await page.evaluate(
    () => getComputedStyle(document.body).fontFamily,
  );
  expect(bodyFontFamily).toContain("Geist");
  expect(bodyFontFamily).not.toContain("IBM Plex");
});

test("body 實際套用的背景色是 Obsidian Gold 的頁面底色（token 換血生效）", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForSelector(".toolbar-title, .screen");

  const bg = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  // 深色優先：#0B0E11。系統若在真無頭瀏覽器強制淺色，這裡就會是
  // #F5F5F5——兩者都是本輪 Obsidian Gold token，任一個都證明換血
  // 生效；舊系統的 #101318／#F4F6F9 兩者皆不應出現。
  expect([OBSIDIAN_GOLD_DARK_BG, OBSIDIAN_GOLD_LIGHT_BG]).toContain(bg);
});

/* ---------- OG-12（#328）：淺色模式明確驗證，不靠無頭瀏覽器剛好強制
   淺色才測得到 ---------- */

test("OG-12（#328）：`prefers-color-scheme: light` 下真的套用淺色 token" +
     "（背景／文字色跟深色版不同，不是媒體查詢沒生效），桌面與手機" +
     "兩種 chrome 皆同一份 token 表", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.route("**/api/scenarios", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/auth/status",
    (route) => route.fulfill({ json: { role: "normal" } }));

  await page.goto("/");
  await page.waitForSelector(".screen");

  const tokens = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { bg: cs.backgroundColor, color: cs.color };
  });
  // artifact `.root.light` token：`--bg0: #F5F5F5`（背景）／
  // `--t1: #1E2329`（主文字）——跟深色版 `#0B0E11`／`#EAECEF` 明顯不同，
  // 不是同一組數字剛好在兩種 color-scheme 下都適用。
  expect(tokens.bg).toBe(OBSIDIAN_GOLD_LIGHT_BG);
  expect(tokens.color).toBe(OBSIDIAN_GOLD_LIGHT_TEXT);
});
