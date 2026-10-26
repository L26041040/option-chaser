// OPTION-CHASER-IDENTITY-RELIABILITY-IMPROVEMENT-001（IRI-07／NIR-08）：
// Normal User 身分的真瀏覽器＋真 Postgres 酷刑測試。
//
// 跟正式站同形狀的本機全站（`scripts/cross_device_verify_server.py`：
// `npm run build` 的 dist/ ＋ 同一個 `create_app()` ＋ 真 Postgres，HTTPS 自簽
// 憑證），Chromium 真的開分頁、真的關掉重開（persistent context）。每個情境
// 都斷言同一件事：**owner 數沒有多、劇本還在、身分狀態是 bound**。
//
//   # 專用資料庫（不要跟 pytest 共用 octest）
//   createdb -h /tmp -p 55432 -U postgres ocidentity
//   DSN=postgresql://postgres@127.0.0.1:55432/ocidentity
//   python scripts/cross_device_verify_server.py --dsn $DSN --seed
//   OC_VERIFY_SU_PASSWORD=su-test OC_VERIFY_SA_PASSWORD=sa-test \
//     python scripts/cross_device_verify_server.py --dsn $DSN --cert cert.pem --key key.pem --port 8443 &
//   BASE_URL=https://127.0.0.1:8443 OC_DSN=$DSN OC_SU_PASSWORD=su-test \
//   OC_SERVER_CMD="…同上的啟動指令…" node scripts/identity_torture.mjs
//
// `OC_SERVER_CMD`（選用）：給了才跑「重新部署」情境——腳本會把它當 shell 指令
// 重新起一個同 port 的 instance（先 kill 舊的）。密碼只從環境變數讀，不印出。
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "https://127.0.0.1:8443";
const DSN = process.env.OC_DSN;
const SU = process.env.OC_SU_PASSWORD;
const SERVER_CMD = process.env.OC_SERVER_CMD;
if (!DSN) throw new Error("需要 OC_DSN（跟伺服器同一個 Postgres）");

const NEW = { symbol: "XYZ", target_price: 130, target_month: "2027-01",
              strategies: ["vertical-spread"] };
const COOKIE = "__Host-oc_owner";
const LOCAL_KEY = "oc_owner_bootstrap";
const launchArgs = ["--no-sandbox", "--disable-dev-shm-usage"];
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail === undefined ? "" : "  " + JSON.stringify(detail)}`);
}

// ---------- Postgres（唯讀計數＋唯一的「時間旅行」寫入） ----------
function sql(query, ...params) {
  const args = ["-X", "-qtA", "-F", "\t", DSN, "-c", query];
  const out = execFileSync("psql", args, { encoding: "utf8", input: params.join("\n") });
  return out.trim().split("\n").filter(Boolean).map((l) => l.split("\t"));
}
const ownersCount = () => Number(sql("SELECT count(*) FROM owners")[0][0]);
const ownerOf = (token) => sql(
  `SELECT owner_id FROM browser_identities WHERE token = '${token.replace(/'/g, "''")}'`)[0]?.[0] ?? null;
const cookieIssuedAt = (token) => sql(
  `SELECT cookie_issued_at FROM browser_identities WHERE token = '${token.replace(/'/g, "''")}'`)[0]?.[0] ?? null;
function ageCookie(token, days) {
  sql(`UPDATE browser_identities SET cookie_issued_at = to_char(now() - interval '${days} days', 'YYYY-MM-DD"T"HH24:MI:SS+00:00')
       WHERE token = '${token.replace(/'/g, "''")}'`);
}

/** 模擬 retention 清理把一顆憑證作廢：留墓碑、刪 identity、刪 owner 與它的劇本
 *  （跟 `delete_owner(reason="retention_expired")` 同一個結果）。 */
function revokeServerSide(token) {
  const hash = createHash("sha256").update(token, "utf8").digest("hex");
  const owner = ownerOf(token);
  const q = token.replace(/'/g, "''");
  sql(`INSERT INTO identity_tombstones (token_hash, reason, deleted_at)
       VALUES ('${hash}', 'retention_expired', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS+00:00'))
       ON CONFLICT (token_hash) DO UPDATE SET reason = EXCLUDED.reason, deleted_at = EXCLUDED.deleted_at`);
  if (owner) {
    sql(`DELETE FROM results WHERE scenario_id IN (SELECT id FROM scenarios WHERE owner_id = '${owner}')`);
    sql(`DELETE FROM current_results WHERE owner_id = '${owner}'`);
    sql(`DELETE FROM scenarios WHERE owner_id = '${owner}'`);
    sql(`DELETE FROM browser_identities WHERE token = '${q}'`);
    sql(`DELETE FROM owners WHERE owner_id = '${owner}'`);
  }
  return owner;
}
const scenariosOfOwner = (owner) => Number(sql(`SELECT count(*) FROM scenarios WHERE owner_id = '${owner}'`)[0][0]);

// ---------- 瀏覽器 ----------
const MOBILE = { width: 390, height: 844 };   // 跟 smoke e2e 一樣走手機版面
async function newContext(browser, opts = {}) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: MOBILE, ...opts });
  return context;
}
async function openApp(context, path = "/#/") {
  const page = await context.newPage();
  await page.goto(`${BASE}${path}`);
  await page.waitForLoadState("networkidle");
  return page;
}
/** 透過 SPA 自己的 `send()`（不是 raw fetch）建立劇本——走跟 `e2e/smoke.spec.ts`
 *  同一條真 UI 路徑（手機版面：標題列的「＋ 建立劇本」入口）。 */
async function createViaUi(page, symbol = "XYZ") {
  await page.goto(`${BASE}/#/`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "＋ 建立劇本" }).click();
  await page.getByLabel("標的代號").fill(symbol);
  await page.getByLabel("目標價位").fill("130");
  // 年月選擇器預設停在今年：直接選 12 月（對 2026-10 的判定日而言仍在未來），
  // 不碰年份欄位——實測 fill 年份會被元件逐字處理成錯的值。
  await page.getByLabel("目標年月").click();
  await page.getByRole("button", { name: "12 月", exact: true }).click();
  await page.getByRole("checkbox", { name: "Call / Put" }).check();
  await page.getByRole("button", { name: "建立", exact: true }).click();
  await page.getByRole("listitem").filter({ hasText: "-12" }).first().waitFor({ timeout: 15000 });
}
/** raw fetch 版（同源，cookie 自動帶；本機那份用 localStorage 的值帶上）——用在
 *  不需要經過 SPA 收斂邏輯的斷言。 */
async function api(page, method, path, body) {
  return page.evaluate(async ([m, p, b, key]) => {
    const local = localStorage.getItem(key);
    const headers = { ...(b ? { "Content-Type": "application/json" } : {}),
                      ...(local ? { "X-OC-Credential": local } : {}) };
    const r = await fetch(p, { method: m, headers, body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json,
             identity: r.headers.get("X-OC-Owner-Identity"),
             reason: r.headers.get("X-OC-Owner-Identity-Reason"),
             bound: r.headers.get("X-OC-Owner-Bound"),
             echo: r.headers.get("X-OC-Credential") };
  }, [method, path, body, LOCAL_KEY]);
}
async function legs(context, page) {
  const cookie = (await context.cookies()).find((c) => c.name === COOKIE);
  const local = await page.evaluate((k) => localStorage.getItem(k), LOCAL_KEY);
  const idb = await page.evaluate(() => new Promise((resolve) => {
    try {
      const req = indexedDB.open("oc-owner-bootstrap", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("kv");
      req.onsuccess = () => {
        const db = req.result;
        const get = db.transaction("kv").objectStore("kv").get("oc_owner_bootstrap");
        get.onsuccess = () => { db.close(); resolve(get.result ?? null); };
        get.onerror = () => { db.close(); resolve(null); };
      };
      req.onerror = () => resolve(null);
      setTimeout(() => resolve("timeout"), 2000);
    } catch { resolve(null); }
  }));
  return { cookie: cookie?.value ?? null, local, idb };
}
async function listViaUi(page) {
  await page.goto(`${BASE}/#/`);
  await page.waitForLoadState("networkidle");
  return page.getByText("XYZ", { exact: false }).first();
}

// ---------- 伺服器重啟（選用） ----------
async function restartServer() {
  if (!SERVER_CMD) return false;
  // 只殺 python 那個 process（regex 錨在 cmdline 開頭）：啟動指令本身也含同樣
  // 字串，用寬鬆的 pattern 會連自己的 shell 一起殺掉。
  try { execFileSync("pkill", ["-f", "^[^ ]*python[0-9.]* scripts/cross_device_verify_server.py"]); } catch { /* 沒在跑 */ }
  await new Promise((r) => setTimeout(r, 800));
  const child = spawn("sh", ["-c", SERVER_CMD], { stdio: "ignore", detached: true });
  child.unref();
  for (let i = 0; i < 60; i++) {
    try {
      const probe = await fetch(`${BASE}/api/health`, { dispatcher: undefined }).catch(() => null);
      if (probe && probe.ok) return true;
    } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("重啟後的伺服器沒有在 30 秒內就緒");
}

process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";   // 只對本機自簽憑證的 health 探測
const browser = await chromium.launch({ executablePath, args: launchArgs });
const owners0 = ownersCount();

try {
  // ===== 1. 首訪＋首寫：兩腿同一顆、一個 owner =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    const first = await api(page, "GET", "/api/scenarios");
    check("1a 首訪讀取：identity=none、不建 owner", first.identity === "none" && ownersCount() === owners0, first);
    const w = await api(page, "POST", "/api/scenarios", NEW);
    const l = await legs(ctx, page);
    check("1b 首寫：201、兩腿同一顆、owner +1", w.status === 201 && l.cookie && l.cookie === l.local && ownersCount() === owners0 + 1, l);
    const again = await api(page, "GET", "/api/scenarios");
    check("1c 之後讀取 bound，劇本 1 筆", again.identity === "bound" && again.body.length === 1);
    await ctx.close();
  }

  // ===== 2. 關閉瀏覽器重開（persistent context）=====
  const profile = mkdtempSync(join(tmpdir(), "oc-torture-profile-"));
  let token2;
  {
    let ctx = await chromium.launchPersistentContext(profile, { executablePath, args: launchArgs, ignoreHTTPSErrors: true, viewport: MOBILE });
    let page = await openApp(ctx);
    const w = await api(page, "POST", "/api/scenarios", NEW);
    token2 = (await legs(ctx, page)).cookie;
    await ctx.close();                                           // 整個瀏覽器關掉
    ctx = await chromium.launchPersistentContext(profile, { executablePath, args: launchArgs, ignoreHTTPSErrors: true, viewport: MOBILE });
    page = await openApp(ctx);
    const r = await api(page, "GET", "/api/scenarios");
    const l = await legs(ctx, page);
    check("2 關閉重開：同一顆 token、同一個 owner、劇本還在", w.status === 201 && l.cookie === token2 && l.local === token2 && r.identity === "bound" && r.body.length === 1, { r: r.identity, n: r.body?.length });
    await ctx.close();
  }

  // ===== 3a. 只清 cookie → 本機那份補回；3b. 只清 site data → cookie 補回 =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const tok = (await legs(ctx, page)).cookie;
    await ctx.clearCookies();
    check("3a-pre 只清 cookie 後 cookie 腿空", (await legs(ctx, page)).cookie === null);
    const r = await api(page, "GET", "/api/scenarios");
    const l = await legs(ctx, page);
    check("3a 只清 cookie：本機那份補回同一顆 cookie、bound、劇本在", r.identity === "bound" && r.body.length === 1 && l.cookie === tok, { cookie: l.cookie === tok });
    await page.evaluate(() => { localStorage.clear(); indexedDB.deleteDatabase("oc-owner-bootstrap"); });
    await page.reload(); await page.waitForLoadState("networkidle");   // SPA 重新產生一顆本機 token，cookie 還在
    const r2 = await api(page, "GET", "/api/scenarios");
    const l2 = await legs(ctx, page);
    check("3b 只清 site data：cookie 補回本機那份（echo）、bound、劇本在", r2.identity === "bound" && r2.body.length === 1 && l2.cookie === tok && l2.local === tok, { local: l2.local === tok });
    await ctx.close();
  }

  // ===== 4a. 兩分頁同時首寫（IndexedDB 可用）；4b. IndexedDB 不可用 =====
  for (const [label, opts] of [["4a IndexedDB 可用", {}], ["4b IndexedDB 不可用", { noIdb: true }]]) {
    const ctx = await newContext(browser);
    if (opts.noIdb) await ctx.addInitScript(() => Object.defineProperty(window, "indexedDB", { value: undefined, configurable: true }));
    const before = ownersCount();
    const p1 = await openApp(ctx); const p2 = await openApp(ctx);
    // 讓兩個分頁的 SPA 都讀過本機儲存（首訪請求），再同時透過 SPA 寫入。
    const [a, b] = await Promise.all([createViaUi(p1, "XYZ").then(() => "ok", (e) => e.message),
                                      createViaUi(p2, "QQQ").then(() => "ok", (e) => e.message)]);
    const l1 = await legs(ctx, p1);
    const n = ownersCount() - before;
    check(`${label}：兩分頁同時首寫只多一個 owner`, n === 1 && l1.cookie, { n, a, b });
    await ctx.close();
  }

  // ===== 5. IndexedDB open 卡死：首頁仍在 3 秒內列出劇本（cookie 腿完好） =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    await page.close();
    await ctx.addInitScript(() => {
      const hang = () => ({ result: undefined, error: null, onsuccess: null, onerror: null, onupgradeneeded: null, onblocked: null });
      Object.defineProperty(window, "indexedDB", { value: { open: hang, deleteDatabase: hang }, configurable: true });
    });
    const p = await ctx.newPage();
    const t0 = Date.now();
    await p.goto(`${BASE}/#/`);
    let seen = false;
    try { await p.getByText("XYZ", { exact: false }).first().waitFor({ timeout: 6000 }); seen = true; } catch { seen = false; }
    const dt = Date.now() - t0;
    check("5 IndexedDB 卡死：首頁仍列出劇本（<6s）", seen, { ms: dt });
    await ctx.close();
  }

  // ===== 6. 重新部署（同 port 重啟 instance）=====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const tok = (await legs(ctx, page)).cookie;
    const restarted = await restartServer();
    if (restarted) {
      const r = await api(page, "GET", "/api/scenarios");
      check("6 重啟 instance：同 owner、bound、劇本在", r.identity === "bound" && r.body.length === 1 && ownerOf(tok) !== null);
    } else {
      check("6 重啟 instance：略過（沒有 OC_SERVER_CMD）", true);
    }
    await ctx.close();
  }

  // ===== 7a. 第 31 天：同顆續簽；7b. cookie 過期（清掉）→ 本機腿補回 =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const tok = (await legs(ctx, page)).cookie;
    ageCookie(tok, 31);
    const before = cookieIssuedAt(tok);
    const r = await api(page, "GET", "/api/scenarios");
    const after = cookieIssuedAt(tok);
    const l = await legs(ctx, page);
    check("7a 簽發滿 31 天：同一顆 token 續簽、cookie_issued_at 更新", r.identity === "bound" && after > before && l.cookie === tok, { before, after });
    await ctx.clearCookies();                 // 模擬第 400 天真的過期
    const r2 = await api(page, "GET", "/api/scenarios");
    check("7b cookie 過期：本機腿補回、同 owner", r2.identity === "bound" && (await legs(ctx, page)).cookie === tok);
    await ctx.close();
  }

  // ===== 8. 伺服器 5xx／網路中斷不清任一腿 =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const before = await legs(ctx, page);
    await ctx.route("**/api/scenarios", (route) => route.fulfill({ status: 500, body: "boom" }));
    await page.reload(); await page.waitForLoadState("networkidle");
    await ctx.unroute("**/api/scenarios");
    await ctx.route("**/api/**", (route) => route.abort("connectionfailed"));
    await page.reload(); await page.waitForLoadState("networkidle").catch(() => {});
    await ctx.unroute("**/api/**");
    const after = await legs(ctx, page);
    check("8 5xx／斷線後兩腿原封不動", after.cookie === before.cookie && after.local === before.local, { before, after });
    const r = await api(page, "GET", "/api/scenarios");
    check("8b 恢復後 bound、劇本在", r.identity === "bound" && r.body.length === 1);
    await ctx.close();
  }

  // ===== 9. 自刪：回應立刻換兩腿；重載後是乾淨首訪；舊 token 讀 unknown =====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const old = (await legs(ctx, page)).cookie;
    await page.goto(`${BASE}/#/settings`); await page.waitForLoadState("networkidle");
    await page.locator("button.text-button.danger").first().click();
    const reloaded = page.waitForEvent("load");
    await page.locator("button:has-text('確定刪除')").first().click();
    await reloaded; await page.waitForLoadState("networkidle");
    const l = await legs(ctx, page);
    const r = await api(page, "GET", "/api/scenarios");
    check("9a 自刪：兩腿都換成新 token、首訪 none、無劇本", l.cookie && l.cookie !== old && l.local === l.cookie && r.identity === "none" && r.body.length === 0, { r: r.identity });
    const stale = await page.evaluate(async ([p, t]) => {
      const x = await fetch(p, { headers: { "X-OC-Credential": t } });
      return { identity: x.headers.get("X-OC-Owner-Identity"), reason: x.headers.get("X-OC-Owner-Identity-Reason") };
    }, ["/api/scenarios", old]);
    check("9b 舊 token 讀 unknown／self_deleted", stale.identity === "unknown" && stale.reason === "self_deleted", stale);
    await ctx.close();
  }

  // ===== 10. SU 登出後兩分頁同時首寫只產生一個 owner（需要 OC_SU_PASSWORD） =====
  if (SU) {
    const ctx = await newContext(browser);
    const a = await openApp(ctx, "/#/settings");
    const input = a.locator("input[type=password]:visible").first();
    await input.waitFor(); await input.fill(SU);
    const reloaded = a.waitForEvent("load");
    await a.locator("button:visible", { hasText: /^登入$/ }).first().click();
    await reloaded; await a.waitForLoadState("networkidle");
    const b = await openApp(ctx);                                  // 第二個分頁，記憶體裡是主帳號憑證
    await a.goto(`${BASE}/#/settings`); await a.waitForLoadState("networkidle");
    const out = a.waitForEvent("load");
    await a.locator("button:visible", { hasText: "重設為 Normal User" }).first().click();
    await out; await a.waitForLoadState("networkidle");             // 登出：新的未綁定憑證
    const before = ownersCount();
    const [ra, rb] = await Promise.all([createViaUi(a, "XYZ").then(() => "ok", (e) => e.message),
                                        createViaUi(b, "QQQ").then(() => "ok", (e) => e.message)]);
    const n = ownersCount() - before;
    check("10 SU 登出後兩分頁同時首寫只多一個 owner", n === 1 && ra === "ok" && rb === "ok", { n, ra, rb });
    await ctx.close();
  } else {
    check("10 SU 登出雙分頁：略過（沒有 OC_SU_PASSWORD）", true);
  }

  // ===== 11. 重放已作廢憑證（TOKEN-REPLAY-FIX-001）=====
  {
    const ctx = await newContext(browser);
    const page = await openApp(ctx);
    await api(page, "POST", "/api/scenarios", NEW);
    const a = (await legs(ctx, page)).cookie;
    // A 作廢（自刪），瀏覽器拿到 B；用 B 建 owner X
    await page.goto(`${BASE}/#/settings`); await page.waitForLoadState("networkidle");
    await page.locator("button.text-button.danger").first().click();
    const reloaded = page.waitForEvent("load");
    await page.locator("button:has-text('確定刪除')").first().click();
    await reloaded; await page.waitForLoadState("networkidle");
    await api(page, "POST", "/api/scenarios", NEW);
    const b = (await legs(ctx, page)).cookie;
    const x = ownerOf(b);
    check("11-pre A 作廢、B 已綁 owner X", a && b && a !== b && x, { x: Boolean(x) });
    const before = ownersCount();
    // 另一個「只拿著 A」的分頁重放
    const attacker = await newContext(browser);
    const ap = await attacker.newPage(); await ap.goto(`${BASE}/#/`); await ap.waitForLoadState("networkidle");
    const replay = await ap.evaluate(async ([p, t]) => {
      const r = await fetch(p, { headers: { "X-OC-Credential": t } });
      const w = await fetch(p, { method: "POST", headers: { "X-OC-Credential": t, "Content-Type": "application/json" },
                              body: JSON.stringify({ symbol: "QQQ", target_price: 130, target_month: "2027-01", strategies: ["vertical-spread"] }) });
      return { read: { identity: r.headers.get("X-OC-Owner-Identity"), echo: r.headers.get("X-OC-Credential"), n: (await r.json()).length },
               write: { status: w.status, identity: w.headers.get("X-OC-Owner-Identity"), echo: w.headers.get("X-OC-Credential") } };
    }, ["/api/scenarios", a]);
    check("11a 重放 A 讀：unknown、空、換發的新憑證不是 A 也不是 B",
          replay.read.identity === "unknown" && replay.read.n === 0 && replay.read.echo && ![a, b].includes(replay.read.echo), replay.read);
    check("11b 重放 A 寫：409、不綁、不碰 X", replay.write.status === 409 && replay.write.identity === "unknown"
          && ownersCount() === before && scenariosOfOwner(x) === 1 && ownerOf(a) === null, replay.write);
    // B 也作廢後，重放 A 與 B 都一樣
    revokeServerSide(b);
    for (const t of [a, b]) {
      const again = await ap.evaluate(async ([p, tok]) => {
        const r = await fetch(p, { headers: { "X-OC-Credential": tok } });
        return { identity: r.headers.get("X-OC-Owner-Identity"), echo: r.headers.get("X-OC-Credential") };
      }, ["/api/scenarios", t]);
      check(`11c A、B 先後作廢後重放 ${t === a ? "A" : "B"}：unknown、新憑證不是 A/B`,
            again.identity === "unknown" && again.echo && ![a, b].includes(again.echo), again);
    }
    check("11d A、B 都沒有被重綁", ownerOf(a) === null && ownerOf(b) === null);
    await attacker.close(); await ctx.close();
  }

  // ===== 12. 兩個分頁同時拿著失效憑證建立劇本 → 只多一個 owner、兩分頁收斂 =====
  // ===== 13. 四個分頁高並發 =====
  for (const tabs of [2, 4]) {
    const ctx = await newContext(browser);
    const pages = [await openApp(ctx)];
    await api(pages[0], "POST", "/api/scenarios", NEW);                 // 綁定
    for (let i = 1; i < tabs; i++) pages.push(await openApp(ctx));      // 其餘分頁載入時都是 bound
    const tok = (await legs(ctx, pages[0])).cookie;
    revokeServerSide(tok);                                              // 伺服器端作廢（分頁不知道）
    const before = ownersCount();
    const outcomes = await Promise.all(pages.map((p, i) =>
      createViaUi(p, i % 2 ? "QQQ" : "XYZ").then(() => "ok", (e) => e.message.split("\n")[0])));
    const n = ownersCount() - before;
    const l = await Promise.all(pages.map((p) => legs(ctx, p)));
    const owners = new Set(l.map((x) => ownerOf(x.local)));
    check(`${tabs === 2 ? "12" : "13"} ${tabs} 個分頁拿著失效憑證同時建立：只多一個 owner、全部收斂到同一顆憑證`,
          n === 1 && outcomes.every((o) => o === "ok") && owners.size === 1 && l.every((x) => x.cookie === l[0].cookie)
          && scenariosOfOwner([...owners][0]) === tabs,
          { n, outcomes, distinctOwners: owners.size, scenarios: scenariosOfOwner([...owners][0]) });
    check(`${tabs === 2 ? "12b" : "13b"} 作廢的 token 沒有被重綁`, ownerOf(tok) === null);
    await ctx.close();
  }

  rmSync(profile, { recursive: true, force: true });
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
