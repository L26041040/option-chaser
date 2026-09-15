import { defineConfig, devices } from "@playwright/test";

/**
 * V1（#48）：E2E 打本機 dev server，API 以 route 攔截回契約樣本
 * （spec #47：前端 mock 與後端 fixture 共用同一份）。
 * 手機優先產品 → 預設就在手機 viewport 跑。
 *
 * 注意：`devices["iPhone 13"]` 的 `defaultBrowserType` 是 webkit；這裡
 * 明確覆寫成 chromium（本專案只保證 Chromium 可跑），只沿用它的視窗
 * 尺寸／DPR／touch／UA 等手機特性。
 */
// 容器內無 user namespace、/dev/shm 偏小；沙箱/CI 預先安裝的 Chromium
// （`PLAYWRIGHT_CHROMIUM_PATH`）版本編號未必與本專案 pin 的
// `@playwright/test` 相符，有指定就用它，沒指定就走 Playwright 自帶的
// 那份。兩個 project 都要這份設定，抽成一個共用值以免各自維護一份
// 而悄悄長歪。
const chromiumLaunchOptions = {
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
  ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
    : {}),
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "iPhone",
      // 桌面版面的驗收（#72）另開一個專案跑寬螢幕，手機這條沿用既有
      // 全頁替換的假設，兩邊不該互相污染。
      testIgnore: /desktop\.spec\.ts$/,
      use: {
        ...devices["iPhone 13"],
        browserName: "chromium",
        launchOptions: chromiumLaunchOptions,
      },
    },
    {
      // 桌面版真正的 master/detail（#72）：寬度需跨過 `styles.css`／
      // `App.tsx` 共用的 1100px 斷點，才驗得到左庫右工作區的版面，
      // 不是手機那種整頁替換。只跑 `desktop.spec.ts`——其餘既有案例
      // 是手機版行為的假設（例如選劇本後建立表單應該不見），套用在
      // 這個寬螢幕專案上會誤判成迴歸。
      name: "Desktop",
      testMatch: /desktop\.spec\.ts$/,
      use: {
        ...devices["Desktop Chrome"],
        browserName: "chromium",
        viewport: { width: 1280, height: 800 },
        launchOptions: chromiumLaunchOptions,
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    // PB-13（#293）新增的 GitHub Actions job（`.github/workflows/
    // ci.yml`）是這份設定第一次真正在冷開機的 CI runner 上跑—沙箱
    // 裡量到的 60 秒對熱機環境夠用，但沒有任何證據證明對冷開機的
    // ubuntu-latest runner 也夠。改為 CI 下給更寬裕的上限，本機／
    // 沙箱維持原值不變。
    timeout: process.env.CI ? 120_000 : 60_000,
    // 逾時或啟動失敗時，Playwright 預設不會把 webServer 的 stdout／
    // stderr 印進 job log——上一次真正卡住時完全看不出 Vite 死在
    // 哪一步。CI 下把兩者都接出來，純粹是可觀測性，不影響任何測試
    // 斷言本身。
    stdout: process.env.CI ? "pipe" : "ignore",
    stderr: "pipe",
  },
});
