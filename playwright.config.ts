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
  // PR #344：CI 的 `Playwright smoke subset` 連三次（跨兩個不同 commit
  // ＋一次明確重跑）都在同一支測試（`smoke.spec.ts:1476`）以同一種
  // 錯誤（30 秒 timeout，`<div id="root">` 攔截 pointer event）失敗，
  // 本地用完全相同的指令與程式碼重現超過 10 次、每次都過——已排除是
  // 這個 diff 造成的回歸（母分支 master 自己乾淨的 CI baseline 也印證
  // 這個 job 平常會過）。沒能在既有的 job log（沒有 screenshot／trace
  // 可看）之外找到更直接的證據釘死根因，但這個失敗形狀（只在 CI
  // 環境、本地完全重現不了）符合 CI runner 資源緊繃下的畫面/事件時序
  // 類問題，不是測試邏輯錯誤。`retries` 原本沒設（預設 0），先前
  // `trace: "on-first-retry"` 因此形同虛設——一次都沒有 retry 可觸發。
  // 這裡讓 CI 環境下真的重試一次：一支測試真的壞掉不會只靠重跑就過，
  // 這裡增加的是對 CI 環境雜訊的容忍，不是放寬斷言或跳過測試本身。
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    // 同一輪順便補上：之前沒有任何失敗現場證據（本輪這次調查完全
    // 只能看純文字 log），下次再發生同類問題時至少有張圖可看。
    screenshot: "only-on-failure",
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
    // 真因（PR #306 第二輪 CI，stdout 接出來後才看見）：不加 `--host`
    // 時 Vite 只綁定 `localhost` 這個名字實際解析到的那一個位址；在
    // GitHub Actions 的 `ubuntu-latest` runner 上 Node 把 `localhost`
    // 解成 IPv6 `::1`，Vite 因此只聽 IPv6，而下面 `url` 與整份測試
    // 套件共用的 `use.baseURL` 都是純 IPv4 的 `127.0.0.1`——健康檢查
    // 連的是完全沒有人在聽的介面，不管等多久都連不上（log 證實 Vite
    // 自己 188ms 就回報「ready」，卡住的是 Playwright 那一端的連線
    // 探測，不是啟動慢）。本機沙箱這次沒踩到是因為這裡 `localhost`
    // 剛好解到 IPv4。明確加 `--host 127.0.0.1` 讓它必定聽在測試套件
    // 實際會打的那個位址上，不依賴任何環境的 DNS 解析順序。
    command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    // 上面這個位址問題修好之後，本機／CI 兩邊啟動都應該在一秒內完成，
    // 但保留 CI 下較寬裕的上限當防禦性餘裕（例如 runner 一時吃緊），
    // 不依賴這個數字本身當唯一防線。
    timeout: process.env.CI ? 120_000 : 60_000,
    // 逾時或啟動失敗時，Playwright 預設不會把 webServer 的 stdout／
    // stderr 印進 job log——這正是本輪能找到上面那個真因的原因，繼續
    // 保留供未來診斷用，不影響任何測試斷言本身。
    stdout: process.env.CI ? "pipe" : "ignore",
    stderr: "pipe",
  },
});
