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

// PR #344 真因（三次 CI 失敗＋一次帶 retry 仍失敗後，撈到失敗截圖才
// 抓到）：Playwright 近版本 headless 模式預設改用「Chromium Headless
// Shell」——一個跟一般 Chromium 分開打包、行為不完全相同的精簡二進位
// 檔。CI 沒有設定 `PLAYWRIGHT_CHROMIUM_PATH`，`launch()` 因此吃
// Playwright 自己的預設值，選中的正是這個 headless shell；本地沙箱
// 因為一路明確指定 `PLAYWRIGHT_CHROMIUM_PATH` 指向完整版 Chromium，
// 從頭到尾沒有踩過這個分支，這也是「本地重現十幾次全過、CI 每次都
// 倒」的真正原因。
//
// 失敗截圖證實了後果：`iPhone` project 的頁面渲染成明顯寬於 390px 的
// 版面（文字被裁切、stats 卡片橫向占滿寬版面）——headless shell 底下
// `devices["iPhone 13"]` 的裝置模擬（viewport／DPR／touch）沒有正確
// 套用，整頁事實上是用桌面寬度畫的，`.mtabs` 與其子元素的實際版面
// 因此跟測試預期的手機窄版面完全不同，才會讓點擊座標踩進被 `#root`
// 攔截的區域。
//
// 修法是明確要求 Playwright 用一般 Chromium 這個 channel、退出「自動
// 選 headless shell」的預設行為——`channel` 與 `executablePath`
// 互斥，只在沒有指定本地覆寫路徑時才加這個 channel（有指定路徑時，
// 那個路徑本身就是完整版 Chromium，channel 沒有意義）。
const chromiumChannel = process.env.PLAYWRIGHT_CHROMIUM_PATH
  ? {}
  : { channel: "chromium" as const };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: process.env.CI ? "line" : "list",
  // PR #344：CI 的 `Playwright smoke subset` 連續 4 次失敗（跨兩個
  // commit、一次明確重跑、外加加了 retry 後原始嘗試＋retry 都失敗）
  // 才逼出真因，見上面 `chromiumChannel` 的完整說明——headless shell
  // 底下 iPhone 裝置模擬失真，不是這個 diff 的邏輯回歸，也不是單純
  // CI 資源雜訊。這裡的 `retries: 1` 留著當一般防禦（真正壞掉的測試
  // 不會因為多重試一次就穩定變綠），但這次的根因已經在瀏覽器選擇上
  // 修掉了，不是靠這個 retry 撐過去的。
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
        ...chromiumChannel,
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
        ...chromiumChannel,
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
