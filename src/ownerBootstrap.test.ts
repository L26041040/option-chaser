import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createScenario, listScenarios } from "./api";
import {
  clearOwnerBootstrapToken, OWNER_BOOTSTRAP_HEADER, ownerBootstrapToken,
} from "./ownerBootstrap";

function okJson(body: unknown) {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() };
}

function headerOf(init: RequestInit | undefined): string | undefined {
  const h = init?.headers;
  if (!h) return undefined;
  if (h instanceof Headers) return h.get(OWNER_BOOTSTRAP_HEADER) ?? undefined;
  return (h as Record<string, string>)[OWNER_BOOTSTRAP_HEADER];
}

describe("owner bootstrap token（Codex P1：首訪並發寫入共用同一顆）", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("是一顆穩定的 base64url 隨機 token，直到被清掉", () => {
    const t = ownerBootstrapToken();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(ownerBootstrapToken()).toBe(t);
    clearOwnerBootstrapToken();
    expect(ownerBootstrapToken()).not.toBe(t);
  });

  it("並發寫入帶同一顆 token；讀取不帶", async () => {
    const calls: RequestInit[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      calls.push(init ?? {});
      if ((init?.method ?? "GET") !== "GET") await gate;
      return okJson(init?.method === "POST" ? { id: "s1" } : []);
    }));
    const body = { symbol: "XYZ", target_price: 1, target_month: "2027-01",
                   strategies: ["vertical-spread"] };
    const a = createScenario(body as never);
    const b = createScenario(body as never);
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

  it("寫入成功後清掉；失敗時保留給重試", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 503, json: async () => ({ detail: "暫時失敗" }),
      headers: new Headers() })));
    const body = { symbol: "XYZ", target_price: 1, target_month: "2027-01",
                   strategies: ["vertical-spread"] };
    await expect(createScenario(body as never)).rejects.toThrow();
    const kept = localStorage.getItem("oc_owner_bootstrap");
    expect(kept).toBeTruthy();

    const seen: (string | undefined)[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
      seen.push(headerOf(init));
      return okJson({ id: "s1" });
    }));
    await createScenario(body as never);
    expect(seen).toEqual([kept]);                 // 重試沿用同一顆
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();
  });
});
