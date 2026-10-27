import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createScenario, listScenarios, login, refreshRun } from "./api";
import {
  credential, CREDENTIAL_HEADER, IDB_TIMEOUT_MS, loadedCredential, markOwnerBound,
  OWNER_BOUND_HEADER, peekCredential, resetCredentialStoreForTests, storeCredential,
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

// IRI-01／NIR-04（研究 #365）：Safari 14.1.1／iOS 14.6 的 `indexedDB.open()`
// 會永遠 pending。jsdom 沒有 IndexedDB，這裡用一個「永遠不觸發任何事件」的
// 假 `indexedDB` 重現，驗證逾時後退回 localStorage、而且 `send()` 不會掛死。
describe("IndexedDB 逾時退路（IRI-01）", () => {
  function hangingIndexedDB() {
    const open = vi.fn(() => ({
      result: undefined, error: null,
      onsuccess: null, onerror: null, onupgradeneeded: null, onblocked: null,
    }));
    vi.stubGlobal("indexedDB", { open });
    return open;
  }

  beforeEach(async () => {
    localStorage.clear();
    await resetCredentialStoreForTests();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("open() 永遠不回應時，恰在 IDB_TIMEOUT_MS 退回 localStorage 的 token", async () => {
    const open = hangingIndexedDB();
    let settled = false;
    const pending = credential().then((t) => { settled = true; return t; });
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS - 1);
    expect(settled).toBe(false);                 // 逾時前真的在等 IndexedDB
    await vi.advanceTimersByTimeAsync(2);
    const t = await pending;
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(t);
    expect(open).toHaveBeenCalledTimes(1);
  });

  it("逾時後的 storeCredential 先同步鏡像到 localStorage、再試 IndexedDB，呼叫端不會被卡住", async () => {
    const open = hangingIndexedDB();
    const first = credential();
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS + 1);
    await first;
    const store = storeCredential(OTHER);
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(OTHER);
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS + 1);
    await store;                                  // 逾時 → resolve，不是永遠 pending
    expect(open).toHaveBeenCalledTimes(2);        // 卡住的結果沒有被永久快取：又試了一次
    expect(await credential()).toBe(OTHER);
  });

  it("send() 不因卡住的 IndexedDB 而掛死：分頁第一個請求在逾時後照常帶著憑證送出", async () => {
    hangingIndexedDB();
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => reply([]));
    vi.stubGlobal("fetch", fetchMock);
    const call = listScenarios();
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS + 1);
    await call;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(headerOf(fetchMock.mock.calls[0][1])).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });
});

// IRI-02／NIR-10（研究 #366）：分頁的記憶體副本會過期（另一分頁登入／登出
// 換了憑證）。兩個修法都只是「讓下一次請求重讀本機儲存」。
describe("分頁快取失效（IRI-02）", () => {
  const FORGED = "F".repeat(43);

  beforeEach(async () => {
    localStorage.clear();
    await resetCredentialStoreForTests();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("曾經綁定的分頁收到沒有 X-OC-Owner-Bound 的回應 → 重讀本機儲存、建立 user 的寫入重新排隊", async () => {
    const locks = fakeLocksShared();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply({ id: "s1" }, { bound: true }))   // 綁定
      .mockResolvedValueOnce(reply([]))                              // 另一分頁登出後：伺服器說沒綁定
      .mockResolvedValue(reply({ id: "s2" }));
    vi.stubGlobal("fetch", fetchMock);
    await createScenario(BODY as never);
    const original = await credential();
    // 另一個分頁登出主帳號、換了一顆新憑證，鏡像寫進共用的 localStorage。
    localStorage.setItem("oc_owner_bootstrap", OTHER);
    await listScenarios();                       // 回應沒有 Owner-Bound → 快取重置
    expect(loadedCredential()).toBeUndefined();
    await createScenario(BODY as never);
    expect(headerOf(fetchMock.mock.calls[2][1] as RequestInit)).toBe(OTHER);
    expect(headerOf(fetchMock.mock.calls[2][1] as RequestInit)).not.toBe(original);
    expect(locks.held).toEqual(["oc-owner-binding", "oc-owner-binding"]);  // 重新排隊
  });

  it("從未綁定的分頁收到沒有 Owner-Bound 的回應不會每次重讀（首訪的正常狀態）", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply([])));
    await listScenarios();
    const t = loadedCredential();
    expect(t).toMatch(/^[A-Za-z0-9_-]{43}$/);
    await listScenarios();
    expect(loadedCredential()).toBe(t);
  });

  it("另一個分頁改了 localStorage 鏡像（storage 事件）→ 重讀本機儲存，不信 event.newValue", async () => {
    const t = await credential();
    localStorage.setItem("oc_owner_bootstrap", OTHER);
    window.dispatchEvent(new StorageEvent("storage", {
      key: "oc_owner_bootstrap", oldValue: t, newValue: FORGED,
    }));
    expect(loadedCredential()).toBeUndefined();
    expect(await credential()).toBe(OTHER);       // 本機儲存的實際內容，不是事件帶的值
  });

  it("另一個分頁 localStorage.clear()（key 為 null）也重置；無關的 key 不重置", async () => {
    const t = await credential();
    window.dispatchEvent(new StorageEvent("storage", { key: "something-else", newValue: "x" }));
    expect(loadedCredential()).toBe(t);
    window.dispatchEvent(new StorageEvent("storage", { key: null }));
    expect(loadedCredential()).toBeUndefined();
  });
});

function fakeLocksShared() {
  const held: string[] = [];
  const request = vi.fn(async (name: string, cb: () => Promise<unknown>) => {
    held.push(name);
    return cb();
  });
  vi.stubGlobal("navigator", { ...navigator, locks: { request } });
  return { held };
}

// TOKEN-REPLAY-FIX-001：帶著已作廢憑證建立 user 被 409 拒絕時，伺服器已換發新憑證；
// 只重送一次、重新排隊（Web Locks）——多分頁同時拿著同一顆作廢憑證不會各建一個 owner。
describe("已作廢憑證的 409 重送（TOKEN-REPLAY-FIX-001）", () => {
  const FRESH = "G".repeat(43);
  function refusal(echo: string) {
    const headers = new Headers();
    headers.set("X-OC-Owner-Identity", "unknown");
    headers.set(CREDENTIAL_HEADER, echo);
    return { ok: false, status: 409, json: async () => ({ detail: "身分已失效" }), headers };
  }

  beforeEach(async () => {
    localStorage.clear();
    await resetCredentialStoreForTests();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("409＋unknown：存下新憑證、重置綁定狀態、在鎖裡重送一次並帶新憑證", async () => {
    const locks = fakeLocksShared();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply({ id: "s0" }, { bound: true }))      // 先綁定（鎖一次）
      .mockResolvedValueOnce(refusal(FRESH))                            // 之後憑證被作廢 → 409
      .mockResolvedValueOnce(reply({ id: "s1" }, { bound: true }));     // 重送成功
    vi.stubGlobal("fetch", fetchMock);
    await createScenario(BODY as never);
    const stale = await credential();
    const created = await createScenario(BODY as never);
    expect(created).toEqual({ id: "s1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(headerOf(fetchMock.mock.calls[1][1] as RequestInit)).toBe(stale);
    expect(headerOf(fetchMock.mock.calls[2][1] as RequestInit)).toBe(FRESH);  // 重送帶新憑證
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe(FRESH);
    expect(locks.held).toEqual(["oc-owner-binding", "oc-owner-binding"]);  // 重送重新排隊
  });

  it("只重送一次：連續兩個 409 就把錯誤丟給呼叫端", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(refusal(FRESH))
      .mockResolvedValueOnce(refusal("H".repeat(43))));
    await expect(createScenario(BODY as never)).rejects.toThrow();
  });

  it("其他 409（例如額度）或非建立 user 的請求不重送", async () => {
    const quota = { ok: false, status: 409, json: async () => ({ detail: "額度" }),
                    headers: new Headers([["X-OC-Owner-Identity", "bound"]]) };
    const fetchMock = vi.fn().mockResolvedValue(quota);
    vi.stubGlobal("fetch", fetchMock);
    await expect(createScenario(BODY as never)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("遲到的 unknown 回應不得蓋掉別的分頁剛換好的憑證（TOKEN-REPLAY-FIX-001）", () => {
  beforeEach(async () => { localStorage.clear(); await resetCredentialStoreForTests(); });
  afterEach(() => vi.unstubAllGlobals());

  it("送出後本機副本已被換掉（另一分頁）→ unknown 回應的 echo 被忽略；bound 的 echo 照存", async () => {
    const original = await credential();
    let resolveFetch: (v: unknown) => void = () => {};
    const slow = new Promise((r) => { resolveFetch = r; });
    vi.stubGlobal("fetch", vi.fn(() => slow));
    const inflight = listScenarios();
    // 另一個分頁換發並綁定了 C1，鏡像寫進 localStorage → storage 事件 → 本分頁快取重置
    localStorage.setItem("oc_owner_bootstrap", "C".repeat(43));
    window.dispatchEvent(new StorageEvent("storage", { key: "oc_owner_bootstrap", newValue: "C".repeat(43) }));
    const headers = new Headers([["X-OC-Owner-Identity", "unknown"], [CREDENTIAL_HEADER, "Z".repeat(43)]]);
    resolveFetch({ ok: true, status: 200, json: async () => [], headers });
    await inflight;
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe("C".repeat(43));   // 沒被 Z 蓋掉
    expect(original).not.toBe("C".repeat(43));
    // 同樣情境但回應是 bound：伺服器解析到的身分，照存
    vi.stubGlobal("fetch", vi.fn(async () => reply([], { bound: true, echo: "D".repeat(43) })));
    await listScenarios();
    expect(localStorage.getItem("oc_owner_bootstrap")).toBe("D".repeat(43));
  });
});

// CANONICAL-REDIRECT-FIX-001：`peekCredential()` 只看、不建立；「空」與「讀不到」
// 必須分得出來，轉址決定才不會把讀取失敗當成沒有身分。
describe("peekCredential（只讀，區分空與讀不到）", () => {
  const TOKEN = "C".repeat(43);

  /** 最小的假 IndexedDB：`open()` 成功，`get` 回 `value`，交易 commit。 */
  function fakeIdb(value: unknown) {
    const open = vi.fn(() => {
      const req: Record<string, unknown> = {};
      queueMicrotask(() => {
        req.result = {
          close: () => {},
          transaction: () => {
            const tx: Record<string, unknown> = {};
            tx.objectStore = () => ({
              get: () => {
                const g = { result: value } as { result: unknown };
                queueMicrotask(() => (tx.oncomplete as () => void)());
                return g;
              },
            });
            return tx;
          },
        };
        (req.onsuccess as () => void)();
      });
      return req;
    });
    vi.stubGlobal("indexedDB", { open });
    return open;
  }

  beforeEach(async () => {
    localStorage.clear();
    await resetCredentialStoreForTests();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("兩份都沒有 → empty，而且什麼都不寫（不像 credential() 會產生一顆）", async () => {
    vi.stubGlobal("indexedDB", undefined);
    expect(await peekCredential()).toEqual({ state: "empty" });
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();
  });

  it("只有 localStorage 有 → present", async () => {
    localStorage.setItem("oc_owner_bootstrap", TOKEN);
    expect(await peekCredential()).toEqual({ state: "present", token: TOKEN });
  });

  it("只有 IndexedDB 有（localStorage 被清）→ present", async () => {
    fakeIdb(TOKEN);
    expect(await peekCredential()).toEqual({ state: "present", token: TOKEN });
    expect(localStorage.getItem("oc_owner_bootstrap")).toBeNull();
  });

  it("IndexedDB 與 localStorage 都讀成功而且都沒有 → empty", async () => {
    fakeIdb(undefined);
    expect(await peekCredential()).toEqual({ state: "empty" });
  });

  it("形狀不對的值不算憑證", async () => {
    localStorage.setItem("oc_owner_bootstrap", "bad value");
    fakeIdb("also bad");
    expect(await peekCredential()).toEqual({ state: "empty" });
  });

  it("IndexedDB 報錯、localStorage 空 → unreadable（不是 empty）", async () => {
    vi.stubGlobal("indexedDB", { open: () => {
      const req: Record<string, unknown> = { error: new Error("denied") };
      queueMicrotask(() => (req.onerror as () => void)());
      return req;
    } });
    expect(await peekCredential()).toEqual({ state: "unreadable" });
  });

  it("IndexedDB 永遠不回應 → 逾時後 unreadable；但 localStorage 有就仍是 present", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("indexedDB", { open: () => ({ onsuccess: null, onerror: null }) });
    const hung = peekCredential();
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS + 1);
    expect(await hung).toEqual({ state: "unreadable" });
    localStorage.setItem("oc_owner_bootstrap", TOKEN);
    const second = peekCredential();
    await vi.advanceTimersByTimeAsync(IDB_TIMEOUT_MS + 1);
    expect(await second).toEqual({ state: "present", token: TOKEN });
  });

  it("localStorage 丟例外、IndexedDB 空 → unreadable", async () => {
    fakeIdb(undefined);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(await peekCredential()).toEqual({ state: "unreadable" });
    vi.restoreAllMocks();
  });
});
