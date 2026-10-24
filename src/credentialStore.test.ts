import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createScenario, listScenarios, login, refreshRun } from "./api";
import {
  credential, CREDENTIAL_HEADER, markOwnerBound, OWNER_BOUND_HEADER,
  resetCredentialStoreForTests,
} from "./credentialStore";

const BODY = { symbol: "XYZ", target_price: 1, target_month: "2027-01",
               strategies: ["vertical-spread"] };
const OTHER = "B".repeat(43);

function reply(body: unknown, { bound = false, echo }: { bound?: boolean; echo?: string } = {}) {
  const headers = new Headers();
  if (bound) headers.set(OWNER_BOUND_HEADER, "1");
  if (echo) headers.set(CREDENTIAL_HEADER, echo);
  return { ok: true, status: 200, json: async () => body, headers };
}

function headerOf(init: RequestInit | undefined): string | undefined {
  const h = init?.headers;
  if (!h) return undefined;
  if (h instanceof Headers) return h.get(CREDENTIAL_HEADER) ?? undefined;
  return (h as Record<string, string>)[CREDENTIAL_HEADER];
}

// jsdom 沒有 IndexedDB：這裡測的是 localStorage 退路、分頁內的快取與
// `send()` 的接線；IndexedDB 路徑的跨分頁原子性在真瀏覽器裡測（e2e
// `owner-bootstrap.spec.ts`，兩個分頁同時搶）。
describe("持久身分憑證（OPTION-CHASER-UNIFIED-IDENTITY-001）", () => {
  beforeEach(async () => {
    localStorage.clear();
    await resetCredentialStoreForTests();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("是一顆穩定的 base64url 隨機 token；綁定後照樣保留（它就是持久身分）", async () => {
    const t = await credential();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(await credential()).toBe(t);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
    markOwnerBound();
    expect(await credential()).toBe(t);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
  });

  it("本機存的值形狀不對（伺服器會拒絕）時換一顆新的並存回去", async () => {
    localStorage.setItem("oc_owner_bootstrap", "bad value");
    const t = await credential();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
  });

  it("每個請求都帶本機憑證——讀取、刷新、寫入都一樣（分頁第一個請求也等它讀完）", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => reply([]));
    vi.stubGlobal("fetch", fetchMock);
    await listScenarios();                       // 這個分頁的第一個請求
    await refreshRun(["a"], false);
    await createScenario(BODY as never);
    const t = await credential();
    const sent = fetchMock.mock.calls.map((c) => headerOf(c[1]));
    expect(sent).toEqual([t, t, t]);
  });

  it("伺服器交回不同的憑證（本機那份不在或不一樣）時存起來，之後改帶它", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply([], { bound: true, echo: OTHER }))
      .mockResolvedValue(reply([], { bound: true }));
    vi.stubGlobal("fetch", fetchMock);
    await listScenarios();
    await listScenarios();
    expect(headerOf(fetchMock.mock.calls[1][1] as RequestInit)).toBe(OTHER);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(OTHER);
    expect(await credential()).toBe(OTHER);
  });

  it("交回的值形狀不對就不收，本機那份不變", async () => {
    const t = await credential();
    vi.stubGlobal("fetch", vi.fn(async () => reply([], { echo: "short" })));
    await listScenarios();
    expect(await credential()).toBe(t);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
  });

  // Codex P2（PR #346）：還沒綁定前，會建立 owner 的寫入跨分頁排隊（Web Locks）。
  function fakeLocks() {
    const held: string[] = [];
    let inside = false;
    const request = vi.fn(async (name: string, cb: () => Promise<unknown>) => {
      held.push(name);
      inside = true;
      try {
        return await cb();
      } finally {
        inside = false;
      }
    });
    vi.stubGlobal("navigator", { ...navigator, locks: { request } });
    return { held, isInside: () => inside };
  }

  it("有 Web Locks 時，建立 owner 的寫入在跨分頁獨佔鎖裡送出；綁定後不再上鎖", async () => {
    const locks = fakeLocks();
    const sentInside: boolean[] = [];
    vi.stubGlobal("fetch", vi.fn(async () => {
      sentInside.push(locks.isInside());
      return reply({ id: "s1" }, { bound: true });
    }));
    await createScenario(BODY as never);            // 綁定前：鎖裡送出
    await createScenario(BODY as never);            // 已綁定：不上鎖
    expect(locks.held).toEqual(["oc-owner-binding"]);
    expect(sentInside).toEqual([true, false]);
  });

  it("不會建立 owner 的寫入（例如刷新）不上鎖", async () => {
    const locks = fakeLocks();
    vi.stubGlobal("fetch", vi.fn(async () => reply({ results: [], remaining: [] })));
    await refreshRun(["a"], false);
    expect(locks.held).toEqual([]);
  });

  it("Web Locks 本身出錯時照舊送出；請求本身的錯誤不會重送", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      locks: { request: vi.fn(async () => { throw new Error("SecurityError"); }) },
    });
    const fetchOk = vi.fn(async () => reply({ id: "s1" }));
    vi.stubGlobal("fetch", fetchOk);
    await createScenario(BODY as never);
    expect(fetchOk).toHaveBeenCalledTimes(1);

    fakeLocks();
    const fetchDown = vi.fn(async () => { throw new TypeError("network down"); });
    vi.stubGlobal("fetch", fetchDown);
    await expect(createScenario(BODY as never)).rejects.toThrow();
    expect(fetchDown).toHaveBeenCalledTimes(1);
  });

  it("輸入 SU／SA 密碼也是可能建立 user 的請求：綁定前一樣排隊", async () => {
    const locks = fakeLocks();
    vi.stubGlobal("fetch", vi.fn(async () => reply({ role: "superuser" }, { bound: true })));
    await login("pw");
    expect(locks.held).toEqual(["oc-owner-binding"]);
  });
});
