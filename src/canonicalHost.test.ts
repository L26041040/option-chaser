import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import {
  ALIAS_HOSTS, CANONICAL_ORIGIN, canonicalTarget, CHECK_TIMEOUT_MS,
  redirectToCanonicalIfNoIdentity, type LocationLike,
} from "./canonicalHost";
import { type CredentialPeek } from "./credentialStore";

const ALIAS = ALIAS_HOSTS[0];
const TOKEN = "A".repeat(43);

type TestLocation = LocationLike & { replace: Mock<(url: string) => void> };

function loc(host: string, path = "/", search = "", hash = ""): TestLocation {
  return { host, pathname: path, search, hash, replace: vi.fn<(url: string) => void>() };
}

function answer(identity: string | null, { ok = true } = {}) {
  const headers = new Headers();
  if (identity) headers.set("X-OC-Owner-Identity", identity);
  return vi.fn(async (..._args: Parameters<typeof fetch>) =>
    ({ ok, status: ok ? 200 : 500, headers }) as Response);
}

async function run(opts: {
  location: TestLocation; peek: CredentialPeek | (() => Promise<CredentialPeek>);
  fetchFn: ReturnType<typeof answer>; timeoutMs?: number;
}) {
  const peek = typeof opts.peek === "function" ? opts.peek : async () => opts.peek as CredentialPeek;
  return redirectToCanonicalIfNoIdentity({
    location: opts.location, fetchFn: opts.fetchFn as unknown as typeof fetch,
    peek, timeoutMs: opts.timeoutMs ?? CHECK_TIMEOUT_MS,
  });
}

describe("canonicalTarget", () => {
  it("只有兩個已確認的別名網址會被指到正式網址，並保留路徑、查詢參數與 hash", () => {
    for (const host of ALIAS_HOSTS) {
      expect(canonicalTarget({ host, pathname: "/x/y", search: "?a=1&b=2", hash: "#/settings" }))
        .toBe(`${CANONICAL_ORIGIN}/x/y?a=1&b=2#/settings`);
    }
  });

  it("正式網址、Preview、部署專屬網址、localhost 都不動", () => {
    for (const host of [
      "option-chaser.vercel.app",
      "option-chaser-git-claude-con-3844be-ofriedoriceo-5352s-projects.vercel.app",
      "option-chaser-99b8z6mt7-ofriedoriceo-5352s-projects.vercel.app",
      "localhost:5173", "127.0.0.1:8443",
      `x.${ALIAS}`, `${ALIAS}:8443`,
    ]) {
      expect(canonicalTarget({ host, pathname: "/", search: "", hash: "" })).toBeNull();
    }
  });

  it("正式網址本身不在別名清單裡（不會無限轉址）", () => {
    expect(ALIAS_HOSTS).not.toContain(new URL(CANONICAL_ORIGIN).host);
  });
});

describe("redirectToCanonicalIfNoIdentity", () => {
  afterEach(() => vi.useRealTimers());

  it("首次訪客：兩份儲存都空、伺服器說 none → 轉址，帶路徑／參數／hash，不帶任何憑證", async () => {
    const location = loc(ALIAS, "/s/1", "?ref=x", "#/trash");
    const fetchFn = answer("none");
    expect(await run({ location, peek: { state: "empty" }, fetchFn })).toBe(true);
    expect(location.replace).toHaveBeenCalledWith(`${CANONICAL_ORIGIN}/s/1?ref=x#/trash`);
    const [, init] = fetchFn.mock.calls[0];
    expect((init?.headers as Record<string, string>)["X-OC-Credential"]).toBeUndefined();
    expect(String(location.replace.mock.calls[0][0])).not.toContain(TOKEN);
  });

  it("有一顆本機憑證但伺服器說 none（從沒綁定過）→ 轉址，且憑證只放 header、不進網址", async () => {
    const location = loc(ALIAS);
    const fetchFn = answer("none");
    expect(await run({ location, peek: { state: "present", token: TOKEN }, fetchFn })).toBe(true);
    const [, init] = fetchFn.mock.calls[0];
    expect((init?.headers as Record<string, string>)["X-OC-Credential"]).toBe(TOKEN);
    expect(location.replace).toHaveBeenCalledWith(`${CANONICAL_ORIGIN}/`);
  });

  it("cookie 掉了、本機憑證有效 → 伺服器認得（bound）→ 不轉址，先恢復原身分", async () => {
    const location = loc(ALIAS);
    expect(await run({ location, peek: { state: "present", token: TOKEN }, fetchFn: answer("bound") }))
      .toBe(false);
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("cookie 在、本機儲存是空的 → 伺服器說 bound → 不轉址", async () => {
    const location = loc(ALIAS);
    expect(await run({ location, peek: { state: "empty" }, fetchFn: answer("bound") })).toBe(false);
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("身分曾經存在但已作廢（unknown）→ 不轉址（不冒險）", async () => {
    const location = loc(ALIAS);
    expect(await run({ location, peek: { state: "present", token: TOKEN }, fetchFn: answer("unknown") }))
      .toBe(false);
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("本機儲存讀不到（IndexedDB 故障／逾時）→ 連請求都不送、不轉址", async () => {
    const location = loc(ALIAS);
    const fetchFn = answer("none");
    expect(await run({ location, peek: { state: "unreadable" }, fetchFn })).toBe(false);
    expect(fetchFn).not.toHaveBeenCalled();
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("網路中斷、非 2xx、缺 header、未知值 → 都不轉址", async () => {
    for (const fetchFn of [
      vi.fn(async () => { throw new TypeError("Failed to fetch"); }),
      answer("none", { ok: false }),
      answer(null),
      answer("weird"),
    ]) {
      const location = loc(ALIAS);
      expect(await run({ location, peek: { state: "empty" },
                         fetchFn: fetchFn as ReturnType<typeof answer> })).toBe(false);
      expect(location.replace).not.toHaveBeenCalled();
    }
  });

  it("peek 自己丟例外也不轉址、不 reject", async () => {
    const location = loc(ALIAS);
    const result = await run({ location, peek: async () => { throw new Error("boom"); },
                               fetchFn: answer("none") });
    expect(result).toBe(false);
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("確認超過期限：中止請求、照常顯示 App；晚到的 none 不會再轉址", async () => {
    vi.useFakeTimers();
    const location = loc(ALIAS);
    let release: (r: Response) => void = () => {};
    const fetchFn = vi.fn((_url: unknown, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
      release = resolve;
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    const pending = redirectToCanonicalIfNoIdentity({
      location, fetchFn: fetchFn as unknown as typeof fetch,
      peek: async () => ({ state: "empty" }), timeoutMs: CHECK_TIMEOUT_MS });
    await vi.advanceTimersByTimeAsync(CHECK_TIMEOUT_MS + 1);
    expect(await pending).toBe(false);
    release({ ok: true, headers: new Headers({ "X-OC-Owner-Identity": "none" }) } as Response);
    await vi.advanceTimersByTimeAsync(10);
    expect(location.replace).not.toHaveBeenCalled();
  });

  it("不在別名網址上：立即回 false，不讀儲存、不送請求", async () => {
    const peek = vi.fn(async () => ({ state: "empty" }) as CredentialPeek);
    const fetchFn = answer("none");
    const location = loc("option-chaser.vercel.app");
    expect(await run({ location, peek, fetchFn })).toBe(false);
    expect(peek).not.toHaveBeenCalled();
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
