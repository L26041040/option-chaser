import { expect, test, type Page } from "@playwright/test";

// Codex P1（PR #346）：兩個首訪分頁同時要 bootstrap token 時，必須拿到
// **同一顆**——否則兩個寫入會各自綁到不同 owner。jsdom 沒有 IndexedDB，
// 跨分頁原子性只能在真瀏覽器裡驗：同一個 browser context 開兩個分頁
// （同源、共用儲存），同時呼叫真正的 `src/ownerBootstrap.ts`（dev server
// 直接提供原始模組），反覆搶很多輪。
const MODULE = "/src/ownerBootstrap.ts";

function call(page: Page, fn: "ownerBootstrapToken" | "resetOwnerBootstrapForTests") {
  return page.evaluate(
    async ([path, name]) => {
      const mod = await import(/* @vite-ignore */ path);
      return mod[name]();
    },
    [MODULE, fn] as const,
  );
}

test("兩個分頁同時首訪只會產生一顆 bootstrap token（跨分頁原子）", async ({ context, page }) => {
  await page.goto("/");
  const other = await context.newPage();
  await other.goto("/");
  for (let round = 0; round < 30; round++) {
    // 兩個分頁都回到「還沒讀過」（各自的記憶體快取也清掉），再同時搶。
    await Promise.all([call(page, "resetOwnerBootstrapForTests"),
                       call(other, "resetOwnerBootstrapForTests")]);
    const [a, b] = await Promise.all([
      call(page, "ownerBootstrapToken"),
      call(other, "ownerBootstrapToken"),
    ]);
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(b).toBe(a);
  }
});

test("IndexedDB 不能用時，兩個分頁同時首次建立劇本會排隊送出，後到的帶著先到的 cookie", async ({ browser }) => {
  // Codex P2（PR #346）：退回 localStorage 時兩個分頁可能各自產生不同 token
  // （Chromium 的 localStorage 跨 renderer 是非同步同步的，上鎖也擋不住讀到
  // 舊值）。所以改成：還沒綁定前，會建立 owner 的寫入跨分頁排隊（Web
  // Locks），後到的請求送出時 cookie jar 已經有先到那顆 cookie——伺服器以
  // cookie 為準。這裡用假後端記錄兩個請求的時間與 cookie。
  const context = await browser.newContext();
  await context.addInitScript(() => {
    Object.defineProperty(window, "indexedDB", { value: undefined, configurable: true });
  });
  const log: { start: number; end: number; cookie: string | undefined }[] = [];
  await context.route("**/api/scenarios", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const entry = { start: Date.now(), end: 0, cookie: route.request().headers()["cookie"] };
    log.push(entry);
    await new Promise((r) => setTimeout(r, 400));
    entry.end = Date.now();
    await route.fulfill({
      status: 200, contentType: "application/json",
      headers: { "Set-Cookie": "oc_e2e_owner=first-bound; Path=/", "X-OC-Owner-Bound": "1" },
      body: JSON.stringify({ id: `s${log.length}` }),
    });
  });
  const page = await context.newPage();
  await page.goto("/");
  const other = await context.newPage();
  await other.goto("/");
  expect(await page.evaluate(() => typeof indexedDB)).toBe("undefined");

  const create = (p: Page) => p.evaluate(async (path) => {
    const mod = await import(/* @vite-ignore */ path);
    await mod.createScenario({ symbol: "XYZ", target_price: 1, target_month: "2027-01",
                               strategies: ["vertical-spread"] });
  }, "/src/api.ts");
  await Promise.all([create(page), create(other)]);

  expect(log).toHaveLength(2);
  const [first, second] = [...log].sort((a, b) => a.start - b.start);
  expect(second.start).toBeGreaterThanOrEqual(first.end);   // 沒有重疊：排隊送出
  expect(first.cookie ?? "").not.toContain("oc_e2e_owner");
  expect(second.cookie ?? "").toContain("oc_e2e_owner=first-bound");
  await context.close();
});

test("IndexedDB 還沒有 token 時沿用 localStorage 既有的那顆（可能正等著重試）", async ({ page }) => {
  await page.goto("/");
  await call(page, "resetOwnerBootstrapForTests");
  const legacy = "L".repeat(43);
  await page.evaluate((t) => localStorage.setItem("oc_owner_bootstrap", t), legacy);
  expect(await call(page, "ownerBootstrapToken")).toBe(legacy);
});

test("IndexedDB 已有 token、但 localStorage 有退路期間產生的另一顆時，以 localStorage 為準", async ({ page }) => {
  await page.goto("/");
  await call(page, "resetOwnerBootstrapForTests");
  const fromIndexedDb = await call(page, "ownerBootstrapToken");
  // IndexedDB 路徑拿到的 token 會同步鏡像到 localStorage（退路讀的就是它）
  expect(await page.evaluate(() => localStorage.getItem("oc_owner_bootstrap")))
    .toBe(fromIndexedDb);
  // 模擬：IndexedDB 暫時失敗期間，退回 localStorage 產生了另一顆（可能已綁定、等著重試）
  const fromFallback = "F".repeat(43);
  await page.evaluate((t) => localStorage.setItem("oc_owner_bootstrap", t), fromFallback);
  await page.reload();                       // 新的分頁生命週期：記憶體快取歸零
  expect(await call(page, "ownerBootstrapToken")).toBe(fromFallback);
  await page.reload();                       // IndexedDB 已經對齊，下次讀也是它
  await page.evaluate(() => localStorage.removeItem("oc_owner_bootstrap"));
  expect(await call(page, "ownerBootstrapToken")).toBe(fromFallback);
});

test("伺服器說過期的 token 從 IndexedDB 與 localStorage 移除，只刪那一顆（compare-and-delete）", async ({ page }) => {
  // Codex P2（PR #346）：409 stale 之後換新 token 重送——舊的要真的從
  // IndexedDB 移除（不然下次讀到的還是它），但別的分頁剛換好的新 token 不能被誤刪。
  await page.goto("/");
  await call(page, "resetOwnerBootstrapForTests");
  const discard = (t: string) => page.evaluate(async ([path, token]) => {
    const mod = await import(/* @vite-ignore */ path);
    await mod.discardOwnerBootstrapToken(token);
  }, [MODULE, t] as const);
  const current = await call(page, "ownerBootstrapToken");
  await discard("N".repeat(43));                         // 不是現在那顆：不動
  expect(await call(page, "ownerBootstrapToken")).toBe(current);
  await discard(current);                                // 是那顆：兩邊都刪，下次換新的
  expect(await page.evaluate(() => localStorage.getItem("oc_owner_bootstrap"))).toBeNull();
  await page.reload();
  const replaced = await call(page, "ownerBootstrapToken");
  expect(replaced).toMatch(/^[A-Za-z0-9_-]{43}$/);
  expect(replaced).not.toBe(current);
});
