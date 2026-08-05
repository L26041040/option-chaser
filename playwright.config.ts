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
        launchOptions: {
          // 容器內無 user namespace、/dev/shm 偏小
          args: ["--no-sandbox", "--disable-dev-shm-usage"],
          // 沙箱/CI 預先安裝的 Chromium（PLAYWRIGHT_CHROMIUM_PATH）版本編號
          // 未必與本專案 pin 的 @playwright/test 相符；有指定就用它，
          // 沒指定就走 Playwright 自帶的那份。
          ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
            : {}),
        },
      },
    },
    {
      // 桌面版真正的 master/detail（#72）：寬度需跨過 `styles.css`／
      // `App.tsx` 共用的 900px 斷點，才驗得到左庫右工作區的版面，
      // 不是手機那種整頁替換。只跑 `desktop.spec.ts`——其餘既有案例
      // 是手機版行為的假設（例如選劇本後建立表單應該不見），套用在
      // 這個寬螢幕專案上會誤判成迴歸。
      name: "Desktop",
      testMatch: /desktop\.spec\.ts$/,
      use: {
        ...devices["Desktop Chrome"],
        browserName: "chromium",
        viewport: { width: 1280, height: 800 },
        launchOptions: {
          args: ["--no-sandbox", "--disable-dev-shm-usage"],
          ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
            : {}),
        },
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
