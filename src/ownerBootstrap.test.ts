import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createScenario, listScenarios, refreshRun } from "./api";
import {
  markOwnerBound, OWNER_BOOTSTRAP_HEADER, OWNER_BOUND_HEADER, ownerBootstrapToken,
  resetOwnerBootstrapForTests,
} from "./ownerBootstrap";

const BODY = { symbol: "XYZ", target_price: 1, target_month: "2027-01",
               strategies: ["vertical-spread"] };

function reply(body: unknown, { ok = true, bound = false } = {}) {
  const headers = new Headers();
  if (bound) headers.set(OWNER_BOUND_HEADER, "1");
  return { ok, status: ok ? 200 : 503, json: async () => body, headers };
}

function headerOf(init: RequestInit | undefined): string | undefined {
  const h = init?.headers;
  if (!h) return undefined;
  if (h instanceof Headers) return h.get(OWNER_BOOTSTRAP_HEADER) ?? undefined;
  return (h as Record<string, string>)[OWNER_BOOTSTRAP_HEADER];
}

// jsdom 沒有 IndexedDB：這裡測的是 localStorage 退路、分頁內的快取與
// request() 的接線；IndexedDB 路徑的跨分頁原子性在真瀏覽器裡測（e2e
// `owner-bootstrap.spec.ts`，兩個分頁同時搶）。
describe("owner bootstrap token（Codex P1：首訪並發寫入共用同一顆）", () => {
  beforeEach(async () => {
    localStorage.clear();
    await resetOwnerBootstrapForTests();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("是一顆穩定的 base64url 隨機 token；綁定後就不再提供", async () => {
    const t = await ownerBootstrapToken();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(await ownerBootstrapToken()).toBe(t);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
    await markOwnerBound();
    expect(await ownerBootstrapToken()).toBeNull();
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();
  });

  it("本機存的值形狀不對（伺服器會拒絕）時換一顆新的並存回去", async () => {
    localStorage.setItem("oc_owner_bootstrap", "bad value");
    const t = await ownerBootstrapToken();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
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

  it("並發寫入帶同一顆 token；讀取不帶", async () => {
    const calls: RequestInit[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      calls.push(init ?? {});
      if ((init?.method ?? "GET") !== "GET") await gate;
      return reply(init?.method === "POST" ? { id: "s1" } : []);
    }));
    const a = createScenario(BODY as never);
    const b = createScenario(BODY as never);
    await listScenarios();
    release();
    await Promise.all([a, b]);

    const writes = calls.filter((c) => c.method === "POST");
    const reads = calls.filter((c) => (c.method ?? "GET") === "GET");
    expect(writes).toHaveLength(2);
    expect(headerOf(writes[0])).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(headerOf(writes[1])).toBe(headerOf(writes[0]));
    expect(reads.every((c) => headerOf(c) === undefined)).toBe(true);
  });

  it("只有可能建立 owner 的寫入才帶；其他寫入（例如刷新）不帶", async () => {
    const seen: (string | undefined)[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
      seen.push(headerOf(init));
      return reply({ results: [], remaining: [] });
    }));
    await refreshRun(["a"], false);
    expect(seen).toEqual([undefined]);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();   // 根本沒讀
  });

  it("失敗時保留給重試；伺服器說已綁定後清掉、之後不再帶", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ detail: "暫時失敗" }, { ok: false })));
    await expect(createScenario(BODY as never)).rejects.toThrow();
    const kept = localStorage.getItem("oc_owner_bootstrap");
    expect(kept).toBeTruthy();

    const seen: (string | undefined)[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
      seen.push(headerOf(init));
      return reply({ id: "s1" }, { bound: seen.length === 2 });
    }));
    await createScenario(BODY as never);           // 成功但伺服器沒說綁定：保留
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(kept);
    await createScenario(BODY as never);           // 伺服器說已綁定：清掉
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();
    await createScenario(BODY as never);           // 之後的寫入不再帶
    expect(seen).toEqual([kept, kept, undefined]);
  });
});
