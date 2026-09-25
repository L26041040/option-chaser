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
