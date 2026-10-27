/**
 * #362 單一正式網址（CANONICAL-REDIRECT-FIX-001）。
 *
 * 同一個人從不同網址進站是不同的 origin、各有各的 cookie 與本機憑證，也就是不同的
 * Normal User。把兩個別名網址的**新訪客**送去正式網址，他們從一開始就只有一個
 * origin；但舊使用者的劇本掛在別名 origin 的身分上，轉走就是孤兒。
 *
 * 為什麼不是 `vercel.json` 的 `redirects`：邊緣只看得到 cookie，看不到 IndexedDB／
 * localStorage——cookie 被清掉、本機憑證還在的舊使用者會被誤導走。所以決定放在
 * 前端、App 掛載之前、身分確認之後。
 *
 * 只有同時成立才離開：
 * 1. 現在在別名網址上（正式網址、Preview、部署專屬網址都不動）；
 * 2. 本機兩份儲存都**讀成功**而且都沒有憑證，或有一顆但伺服器沒綁定它（見 3）；
 * 3. 伺服器明確回答 `X-OC-Owner-Identity: none`（cookie 與本機憑證都沒對應到
 *    user）。`bound`（要留）、`unknown`（以前有過身分，要留）、缺 header、
 *    非 2xx、逾時、網路斷線、儲存讀不到——一律留在原網址，不冒險。
 *
 * 不傳任何 token：離開時只帶路徑、查詢參數與 hash。這個請求只讀，不建立
 * user、不產生憑證，帶著本機憑證是為了讓伺服器認得「cookie 掉了但本機還在」。
 */
import { CREDENTIAL_HEADER, peekCredential, type CredentialPeek } from "./credentialStore";

export const CANONICAL_ORIGIN = "https://option-chaser.vercel.app";
/** 已確認會把使用者帶進來的別名 Production 網址（完全比對）。 */
export const ALIAS_HOSTS: readonly string[] = [
  "option-chaser-ofriedoriceo-5352s-projects.vercel.app",
  "option-chaser-git-master-ofriedoriceo-5352s-projects.vercel.app",
];
/** 與 `src/api.ts` 的 `IDENTITY_STATE_HEADER` 同一個伺服器 header。 */
const IDENTITY_STATE_HEADER = "X-OC-Owner-Identity";
const PROBE_URL = "/api/me/usage-summary";
/** 確認身分最多等這麼久；超過就照常顯示 App，晚到的答案不再轉址。 */
export const CHECK_TIMEOUT_MS = 5000;

export interface LocationLike {
  host: string;
  pathname: string;
  search: string;
  hash: string;
  replace(url: string): void;
}

export interface CanonicalDeps {
  location: LocationLike;
  fetchFn: typeof fetch;
  peek: () => Promise<CredentialPeek>;
  timeoutMs: number;
}

/** 這個位置該去的正式網址 URL；不在別名網址上回 `null`。保留路徑、查詢參數、hash。 */
export function canonicalTarget(loc: Pick<LocationLike, "host" | "pathname" | "search" | "hash">): string | null {
  if (!ALIAS_HOSTS.includes(loc.host)) return null;
  return `${CANONICAL_ORIGIN}${loc.pathname}${loc.search}${loc.hash}`;
}

async function serverSaysNoIdentity(
  fetchFn: typeof fetch, token: string | null, signal: AbortSignal,
): Promise<boolean> {
  try {
    const resp = await fetchFn(PROBE_URL, {
      cache: "no-store",
      headers: token ? { [CREDENTIAL_HEADER]: token } : {},
      signal,
    });
    return resp.ok && resp.headers.get(IDENTITY_STATE_HEADER) === "none";
  } catch {
    return false;
  }
}

/**
 * 在別名網址上確認這個瀏覽器沒有既有身分就轉去正式網址。回傳 `true`＝已經
 * 下了轉址（呼叫端不必再掛載 App）；`false`＝照常掛載。永遠不 reject。
 */
export async function redirectToCanonicalIfNoIdentity(
  overrides: Partial<CanonicalDeps> = {},
): Promise<boolean> {
  const deps: CanonicalDeps = {
    location: window.location,
    fetchFn: (...args) => fetch(...args),
    peek: peekCredential,
    timeoutMs: CHECK_TIMEOUT_MS,
    ...overrides,
  };
  const target = canonicalTarget(deps.location);
  if (!target) return false;

  const abort = new AbortController();
  let expired = false;
  const deadline = setTimeout(() => { expired = true; abort.abort(); }, deps.timeoutMs);
  try {
    const peeked = await deps.peek();
    if (peeked.state === "unreadable") return false;
    const token = peeked.state === "present" ? peeked.token : null;
    const none = await serverSaysNoIdentity(deps.fetchFn, token, abort.signal);
    if (!none || expired) return false;
    deps.location.replace(target);
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(deadline);
  }
}
