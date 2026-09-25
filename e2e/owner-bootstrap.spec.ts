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
