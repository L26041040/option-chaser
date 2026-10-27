// OPTION-CHASER-CANONICAL-REDIRECT-FIX-001：別名網址 → 正式網址轉址的真瀏覽器＋真 Postgres 驗證。
//
// 用 Chromium 的 `--host-resolver-rules` 把所有 `*.vercel.app` 對映到本機測試站
// （`scripts/cross_device_verify_server.py`，HTTPS 自簽憑證）：別名網址、正式網址、
// Preview 網址因此是真的不同 origin，cookie／IndexedDB／localStorage 的隔離跟
// Production 一樣。「舊使用者」在別名 origin 的 `/api/health`（不是 SPA、不經過轉址
// 閘門）用真 API 建立身分與劇本，再依情境拿掉 cookie 或某一份本機憑證，最後載入別名
// 網址的 SPA。每個情境都斷言：轉址行為、Owner 數、劇本數。
//
//   createdb -h /tmp -p 55432 -U postgres occanon
//   DSN=postgresql://postgres@127.0.0.1:55432/occanon
//   OC_VERIFY_SU_PASSWORD=su-test OC_VERIFY_SA_PASSWORD=sa-test \
//     python scripts/cross_device_verify_server.py --dsn $DSN --cert cert.pem --key key.pem --port 8443 &
//   OC_DSN=$DSN OC_SU_PASSWORD=su-test node scripts/canonical_redirect_verify.mjs
//
// 密碼只從環境變數讀（測試用假密碼），不印出。
//
// ⚠ 安全閘（2026-10-27 事故後加入）：這個環境有 `HTTPS_PROXY`，Chromium 在 Linux 會沿用它，
// 走代理時 `--host-resolver-rules` 的對映**不生效**，請求會打到真正的 Production。
// 所以：(1) 一律加 `--no-proxy-server`；(2) 開跑前先對一個**不存在**的子網域做金絲雀
// 檢查，回來的必須是本機測試站（`backend.commit` 為 null、而且本機資料庫看得到我們剛寫的
// 那一筆），否則在送出任何寫入之前就中止；(3) 每次種「舊使用者」後再確認本機 Owner 數
// 真的 +1。
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";

import { chromium } from "@playwright/test";

const PORT = process.env.OC_PORT ?? "8443";
const DSN = process.env.OC_DSN;
const SU = process.env.OC_SU_PASSWORD;
if (!DSN) throw new Error("需要 OC_DSN（跟伺服器同一個 Postgres）");

const ALIAS = "option-chaser-ofriedoriceo-5352s-projects.vercel.app";
const ALIAS2 = "option-chaser-git-master-ofriedoriceo-5352s-projects.vercel.app";
const CANON = "option-chaser.vercel.app";
const PREVIEW = "option-chaser-git-claude-con-3844be-ofriedoriceo-5352s-projects.vercel.app";
const DEPLOY = "option-chaser-99b8z6mt7-ofriedoriceo-5352s-projects.vercel.app";

const NEW = { symbol: "XYZ", target_price: 130, target_month: "2027-01",
              strategies: ["vertical-spread"] };
const COOKIE = "__Host-oc_owner";
const LOCAL_KEY = "oc_owner_bootstrap";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
const MOBILE = { width: 390, height: 844 };
const GATE_WAIT_MS = 6500;   // 閘門最久 5 秒（CHECK_TIMEOUT_MS）+ 餘裕

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail === undefined ? "" : "  " + JSON.stringify(detail)}`);
}

function sql(query) {
  const out = execFileSync("psql", ["-X", "-qtA", "-F", "\t", DSN, "-c", query], { encoding: "utf8" });
  return out.trim().split("\n").filter(Boolean).map((l) => l.split("\t"));
}
const ownersCount = () => Number(sql("SELECT count(*) FROM owners")[0][0]);
const scenariosCount = () => Number(sql("SELECT count(*) FROM scenarios")[0][0]);
const snapshot = () => ({ owners: ownersCount(), scenarios: scenariosCount() });

const url = (host, path = "/") => `https://${host}${path}`;
const token43 = () => randomBytes(32).toString("base64url");

async function newContext(browser) {
  return browser.newContext({ ignoreHTTPSErrors: true, viewport: MOBILE });
}

/** 在 `host` 這個 origin 上、不經過 SPA 閘門，用真 API 建立「舊使用者」：
 *  本機兩份憑證（localStorage＋IndexedDB）＋ cookie ＋ 一個劇本。回傳 token。 */
async function seedOldUser(context, host) {
  const page = await context.newPage();
  await page.goto(url(host, "/api/health"));
  const token = token43();
  await page.evaluate(async ([key, t]) => {
    localStorage.setItem(key, t);
    await new Promise((resolve, reject) => {
      const req = indexedDB.open("oc-owner-bootstrap", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("kv");
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction("kv", "readwrite");
        tx.objectStore("kv").put(t, key);
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
      req.onerror = () => reject(req.error);
    });
  }, [LOCAL_KEY, token]);
  const ownersBefore = ownersCount();
  const created = await rawApi(page, "POST", "/api/scenarios", NEW, token);
  if (created.status >= 300) throw new Error(`seed 失敗：${created.status}`);
  assertSeededLocally(ownersBefore);
  return { page, token };
}

async function rawApi(page, method, path, body, token) {
  return page.evaluate(async ([m, p, b, t]) => {
    const headers = { ...(b ? { "Content-Type": "application/json" } : {}),
                      ...(t ? { "X-OC-Credential": t } : {}) };
    const r = await fetch(p, { method: m, headers, body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json, identity: r.headers.get("X-OC-Owner-Identity") };
  }, [method, path, body, token]);
}

const dropCookie = (context) => context.clearCookies();
const dropLocal = (page) => page.evaluate((k) => localStorage.removeItem(k), LOCAL_KEY);
const dropIdb = (page) => page.evaluate(() => new Promise((resolve) => {
  const req = indexedDB.deleteDatabase("oc-owner-bootstrap");
  req.onsuccess = req.onerror = req.onblocked = () => resolve();
}));
const hasCookie = async (context) => (await context.cookies()).some((c) => c.name === COOKIE);

/** 載入 `target`，等到「確定停在原地」或「轉到別的 origin」，回傳最後的 URL。 */
async function visit(context, target, { waitMs = 1500 } = {}) {
  const page = await context.newPage();
  const startHost = new URL(target).host;
  await page.goto(target, { waitUntil: "domcontentloaded" }).catch(() => {});
  // 轉址是 location.replace：給閘門（含探測請求）時間跑完。
  await page.waitForFunction((h) => location.host !== h, startHost, { timeout: waitMs })
    .catch(() => {});
  await page.waitForLoadState("networkidle").catch(() => {});
  return page;
}
const hostOf = (page) => new URL(page.url()).host;
const appMounted = (page) => page.locator("#root *").first().isVisible().catch(() => false);

/** 金絲雀：確認 `*.vercel.app` 真的對映到本機測試站，而不是真正的 Vercel。用一個
 *  不存在的隨機子網域——萬一對映失效，這個請求打到的是 Vercel 的 404，不是任何真實部署。 */
async function canary(browser) {
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  const host = `zz-canary-${randomBytes(6).toString("hex")}.vercel.app`;
  const before = ownersCount();
  const resp = await page.goto(url(host, "/api/health"), { timeout: 15000 }).catch(() => null);
  let health = null;
  try { health = await resp?.json(); } catch { /* 不是 JSON → 不是本機站 */ }
  const local = health?.storage === "postgres" && health?.backend?.commit === null;
  if (!local) {
    console.error(`ABORT  金絲雀失敗：${host} 沒有對映到本機測試站（${resp?.status()}）。沒有送出任何寫入。`);
    process.exit(3);
  }
  const t = token43();
  const created = await page.evaluate(async ([tok, body]) => {
    const r = await fetch("/api/scenarios", { method: "POST",
      headers: { "Content-Type": "application/json", "X-OC-Credential": tok },
      body: JSON.stringify(body) });
    return r.status;
  }, [t, NEW]);
  if (created >= 300 || ownersCount() !== before + 1) {
    console.error(`ABORT  金絲雀失敗：本機資料庫沒有看到寫入（status ${created}）。`);
    process.exit(3);
  }
  console.log("OK    金絲雀：*.vercel.app 對映到本機測試站，寫入落在本機資料庫");
  await ctx.close();
}
/** 每次種使用者後：本機 Owner 數必須 +1，否則立刻中止。 */
function assertSeededLocally(before) {
  if (ownersCount() !== before + 1) {
    console.error("ABORT  種下的使用者沒有出現在本機資料庫——請求可能沒有打到本機測試站。");
    process.exit(3);
  }
}

async function main() {
  const browser = await chromium.launch({
    executablePath,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server",
           `--host-resolver-rules=MAP *.vercel.app 127.0.0.1:${PORT}`],
  });
  await canary(browser);
  let ctx;

  // ---- 1. 首次訪客：兩份憑證都不存在 → 轉去正式網址，路徑／參數／hash 保留 ----
  for (const host of [ALIAS, ALIAS2]) {
    ctx = await newContext(browser);
    const before = snapshot();
    const page = await visit(ctx, url(host, "/some/path?ref=abc&x=1#/trash"));
    check(`1 首次訪客（${host === ALIAS ? "別名一" : "別名二"}）→ 正式網址，保留路徑／參數／hash`,
      page.url() === url(CANON, "/some/path?ref=abc&x=1#/trash"), { url: page.url() });
    const after = snapshot();
    check("1b 轉址沒有多出 Owner／劇本", after.owners === before.owners && after.scenarios === before.scenarios, { before, after });
    await ctx.close();
  }

  // ---- 2. Cookie 存在（兩份本機憑證也在）→ 不轉址、Owner 不增加、劇本還在 ----
  ctx = await newContext(browser);
  let { page: api, token } = await seedOldUser(ctx, ALIAS);
  let before = snapshot();
  let page = await visit(ctx, url(ALIAS, "/#/"));
  check("2 Cookie 存在 → 停在別名網址、App 已掛載", hostOf(page) === ALIAS && await appMounted(page), { host: hostOf(page) });
  let list = await rawApi(page, "GET", "/api/scenarios", null, token);
  check("2b 劇本還在、Owner 不增加", list.body?.length >= 1 && snapshot().owners === before.owners, { n: list.body?.length, owners: snapshot().owners, was: before.owners });
  await ctx.close();

  // ---- 3. Cookie 遺失、IndexedDB＋localStorage 有效 → 先恢復原身分，不轉址 ----
  for (const [label, drop] of [
    ["3 Cookie 遺失、IndexedDB 與 localStorage 皆有效", async () => {}],
    ["4 Cookie 遺失、僅 localStorage 有效（IndexedDB 被清）", async (p) => { await dropIdb(p); }],
    ["5 Cookie 遺失、僅 IndexedDB 有效（localStorage 被清）", async (p) => { await dropLocal(p); }],
  ]) {
    ctx = await newContext(browser);
    ({ page: api, token } = await seedOldUser(ctx, ALIAS));
    await drop(api);
    await dropCookie(ctx);
    before = snapshot();
    page = await visit(ctx, url(ALIAS, "/#/"));
    check(`${label} → 不轉址、App 已掛載`, hostOf(page) === ALIAS && await appMounted(page), { host: hostOf(page) });
    const status = await rawApi(page, "GET", "/api/me/usage-summary", null, token);
    check(`${label.split("、")[0]} …身分恢復（bound）、Cookie 補發`,
      status.identity === "bound" && await hasCookie(ctx), { identity: status.identity });
    const now = snapshot();
    check(`${label.split("、")[0]} …Owner 不增加、劇本不遺失`,
      now.owners === before.owners && now.scenarios === before.scenarios, { before, now });
    await ctx.close();
  }

  // ---- 6. IndexedDB 故障（open 丟錯／永遠不回應）：不冒險轉址 ----
  for (const [label, script] of [
    ["6a IndexedDB.open 丟例外", `indexedDB.open = () => { throw new Error("denied"); };`],
    ["6b IndexedDB.open 永遠不回應", `indexedDB.open = () => ({});`],
  ]) {
    // 舊使用者（憑證只在 IndexedDB）：不能因為讀不到就當成沒有身分
    ctx = await newContext(browser);
    ({ page: api, token } = await seedOldUser(ctx, ALIAS));
    await dropLocal(api);
    await dropCookie(ctx);
    await ctx.addInitScript(script);
    before = snapshot();
    page = await visit(ctx, url(ALIAS, "/#/"), { waitMs: GATE_WAIT_MS });
    check(`${label}（舊使用者，憑證只在 IndexedDB）→ 不轉址`, hostOf(page) === ALIAS, { host: hostOf(page) });
    check(`${label} …Owner／劇本不變`, JSON.stringify(snapshot()) === JSON.stringify(before), snapshot());
    await ctx.close();
    // 首次訪客 + 故障的 IndexedDB：無法確認 → 同樣不轉址
    ctx = await newContext(browser);
    await ctx.addInitScript(script);
    page = await visit(ctx, url(ALIAS, "/#/"), { waitMs: GATE_WAIT_MS });
    check(`${label}（首次訪客，無法確認）→ 不轉址`, hostOf(page) === ALIAS, { host: hostOf(page) });
    await ctx.close();
  }

  // ---- 7. 網路中斷／探測逾時：不轉址 ----
  ctx = await newContext(browser);
  await ctx.route("**/api/me/usage-summary", (route) => route.abort("connectionrefused"));
  page = await visit(ctx, url(ALIAS, "/#/"), { waitMs: 3000 });
  check("7a 探測請求網路中斷 → 不轉址、仍掛載 App", hostOf(page) === ALIAS && await appMounted(page), { host: hostOf(page) });
  await ctx.close();

  ctx = await newContext(browser);
  let release;
  const gate = new Promise((r) => { release = r; });
  await ctx.route("**/api/me/usage-summary", async (route) => {
    if (!release.fired) { release.fired = true; await gate; }
    route.continue().catch(() => {});
  });
  const t0 = Date.now();
  page = await visit(ctx, url(ALIAS, "/#/"), { waitMs: GATE_WAIT_MS });
  const elapsed = Date.now() - t0;
  release();
  check("7b 探測請求卡住 → 約 5 秒後放行、不轉址、App 掛載",
    hostOf(page) === ALIAS && await appMounted(page) && elapsed >= 4500, { host: hostOf(page), elapsed });
  await page.waitForTimeout(500);
  check("7b …晚到的答案不會事後轉址", hostOf(page) === ALIAS, { host: hostOf(page) });
  await ctx.close();

  // ---- 8. 多分頁同時開啟舊網址 ----
  ctx = await newContext(browser);
  ({ page: api, token } = await seedOldUser(ctx, ALIAS));
  await dropCookie(ctx);
  before = snapshot();
  const tabs = await Promise.all([1, 2, 3, 4].map(() => visit(ctx, url(ALIAS, "/#/"))));
  check("8a 舊使用者（cookie 遺失）同時開 4 個分頁 → 全部不轉址",
    tabs.every((p) => hostOf(p) === ALIAS), tabs.map(hostOf));
  const afterTabs = snapshot();
  check("8a …Owner 不增加、劇本不遺失", afterTabs.owners === before.owners && afterTabs.scenarios === before.scenarios, { before, afterTabs });
  await ctx.close();

  ctx = await newContext(browser);
  before = snapshot();
  const fresh = await Promise.all([1, 2, 3, 4].map(() => visit(ctx, url(ALIAS, "/#/"))));
  check("8b 首次訪客同時開 4 個分頁 → 全部到正式網址", fresh.every((p) => hostOf(p) === CANON), fresh.map(hostOf));
  check("8b …沒有產生任何 Owner", snapshot().owners === before.owners, snapshot());
  await ctx.close();

  // ---- 9. 範圍：正式網址、Preview、部署專屬網址不動；/api/* 不轉址 ----
  for (const [label, host] of [["正式網址", CANON], ["Preview 網址", PREVIEW], ["部署專屬網址", DEPLOY]]) {
    ctx = await newContext(browser);
    page = await visit(ctx, url(host, "/#/"));
    check(`9 ${label}（首次訪客）→ 不轉址`, hostOf(page) === host && await appMounted(page), { host: hostOf(page) });
    await ctx.close();
  }
  ctx = await newContext(browser);
  const apiPage = await ctx.newPage();
  const resp = await apiPage.goto(url(ALIAS, "/api/health"));
  check("9 別名網址的 /api/health 不轉址、回 200", resp.status() === 200 && hostOf(apiPage) === ALIAS, { status: resp.status() });
  await ctx.close();

  // ---- 10. SU：在別名 origin 登入主帳號後，cookie 遺失也不被導走，權限還在 ----
  if (SU) {
    ctx = await newContext(browser);
    const p = await ctx.newPage();
    await p.goto(url(ALIAS, "/api/health"));
    const t = token43();
    await p.evaluate(([k, v]) => localStorage.setItem(k, v), [LOCAL_KEY, t]);
    const login = await p.evaluate(async ([pw, tok]) => {
      const r = await fetch("/api/auth/login", { method: "POST",
        headers: { "Content-Type": "application/json", "X-OC-Credential": tok },
        body: JSON.stringify({ password: pw }) });
      return { status: r.status, echo: r.headers.get("X-OC-Credential") };
    }, [SU, t]);
    if (login.echo) await p.evaluate(([k, v]) => localStorage.setItem(k, v), [LOCAL_KEY, login.echo]);
    await dropCookie(ctx);
    before = snapshot();
    page = await visit(ctx, url(ALIAS, "/#/"));
    const role = await rawApi(page, "GET", "/api/auth/status", null, login.echo ?? t);
    check("10 SU（cookie 遺失、本機憑證在）→ 不轉址、角色仍是 superuser",
      login.status === 200 && hostOf(page) === ALIAS && role.body?.role === "superuser", { host: hostOf(page), role: role.body?.role });
    check("10 …Owner 不增加", snapshot().owners === before.owners, snapshot());
    await ctx.close();
  } else {
    console.log("SKIP  10（沒有 OC_SU_PASSWORD）");
  }

  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
