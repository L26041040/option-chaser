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
