// OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001：三個獨立瀏覽器登入同一個主帳號的
// 真瀏覽器驗證。
//
// 每台「裝置」是一個獨立的 Playwright browser context（各自的 cookie jar、
// IndexedDB、localStorage——跟三台不同的手機／電腦一樣互不相通），登入走真的
// 設定頁 UI（密碼欄＋「登入」鈕），之後的檢查用該裝置自己的 cookie 打 API。
//
//   BASE_URL=https://127.0.0.1:8443 OC_SU_PASSWORD=… OC_SA_PASSWORD=… \
//   OC_VERIFY_WRITE=1 node scripts/cross_device_verify.mjs
//
// `OC_VERIFY_WRITE=1`（本機驗證站）：A 先以匿名身分建 2 個劇本，驗證登入時
// 安全併入；最後 B 再建一個，驗證三台立刻一致。對正式站跑時**不要**設它——
// 只讀、不建任何劇本；結束時三台都按「重設」登出，不留下任何裝置憑證。
// 密碼只從環境變數讀，不印出、不寫檔。
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "https://127.0.0.1:8443";
const SU = process.env.OC_SU_PASSWORD;
const SA = process.env.OC_SA_PASSWORD;
const WRITE = process.env.OC_VERIFY_WRITE === "1";
if (!SU || !SA) throw new Error("需要 OC_SU_PASSWORD 與 OC_SA_PASSWORD");

const NEW = { symbol: "XYZ", target_price: 130, target_month: "2027-01",
              strategies: ["vertical-spread"] };
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail === undefined ? "" : "  " + JSON.stringify(detail)}`);
}

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

async function device(name) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true,
                                             viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto(`${BASE}/#/`);
  await page.waitForLoadState("networkidle");
  return { name, context, page };
}

async function api(d, method, path, body) {
  return d.page.evaluate(async ([m, p, b]) => {
    const r = await fetch(p, { method: m,
      headers: b ? { "Content-Type": "application/json" } : {},
      body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json };
  }, [method, path, body]);
}

async function credentialCopies(d) {
  const cookie = (await d.context.cookies()).find((c) => c.name === "__Host-oc_owner");
  const local = await d.page.evaluate(() => localStorage.getItem("oc_owner_bootstrap"));
  return { cookie: cookie?.value ?? null, local, httpOnly: cookie?.httpOnly ?? null,
           secure: cookie?.secure ?? null };
}

async function uiLogin(d, password) {
  await d.page.goto(`${BASE}/#/settings`);
  const input = d.page.locator("input[type=password]:visible").first();
  await input.waitFor();
  await input.fill(password);
  const reloaded = d.page.waitForEvent("load");
  await d.page.locator("button:visible", { hasText: /^登入$/ }).first().click();
  await reloaded;                      // 登入成功後整頁重新載入
  await d.page.waitForLoadState("networkidle");
}

async function uiReset(d) {
  await d.page.goto(`${BASE}/#/settings`);
  const button = d.page.locator("button:visible", { hasText: "重設為 Normal User" }).first();
  await button.waitFor();
  const reloaded = d.page.waitForEvent("load");
  await button.click();
  await reloaded;
  await d.page.waitForLoadState("networkidle");
}

async function scenarioIds(d) {
  const r = await api(d, "GET", "/api/scenarios?include_archived=true");
  return r.body.map((s) => s.id).sort();
}

const role = async (d) => (await api(d, "GET", "/api/auth/status")).body.role;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

try {
  const A = await device("A"), B = await device("B"), C = await device("C");
  const health = (await api(A, "GET", "/api/health")).body;
  check("health 回報後端指紋", health.backend !== undefined, health.backend);
  let mergedIds = [];
  if (WRITE) {
    for (let i = 0; i < 2; i++) {
      const r = await api(A, "POST", "/api/scenarios", NEW);
      mergedIds.push(r.body.id);
    }
    check("A 以匿名身分建了 2 個劇本", same((await scenarioIds(A)), [...mergedIds].sort()));
    check("A 匿名時是 normal", (await role(A)) === "normal");
  }
  const anonCookieA = (await credentialCopies(A)).cookie;

  await uiLogin(A, SU);
  await uiLogin(B, SU);
  await uiLogin(C, SA);

  const roles = [await role(A), await role(B), await role(C)];
  check("權限依各自登入的密碼：A=SU、B=SU、C=SA", same(roles, ["superuser", "superuser", "superadmin"]), roles);

  const [idsA, idsB, idsC] = [await scenarioIds(A), await scenarioIds(B), await scenarioIds(C)];
  check("三台裝置看到同一份劇本", same(idsA, idsB) && same(idsB, idsC), { count: idsA.length });
  if (WRITE) {
    check("A 的匿名劇本已併入主帳號", mergedIds.every((id) => idsA.includes(id)), { mergedIds });
  }

  const owners = await api(C, "GET", "/api/superuser/owners");
  const privileged = owners.body.filter((o) => o.role !== "normal");
  check("SA（C）看得到 owner 清單", owners.status === 200, { owners: owners.body.length });
  check("只有一個特權 owner（沒有第二個 SU owner）", privileged.length === 1,
        { privileged: privileged.length });
  check("A 原本的匿名 owner 已併入、不再存在",
        !WRITE || owners.body.length === 1, { owners: owners.body.length });
  const deniedA = await api(A, "GET", "/api/superuser/owners");
  const deniedB = await api(B, "GET", "/api/superuser/owners");
  check("SU（A、B）進不了 SA 專屬端點（權限沒有互相污染）",
        deniedA.status === 401 && deniedB.status === 401, [deniedA.status, deniedB.status]);

  for (const d of [A, B, C]) {
    const c = await credentialCopies(d);
    check(`${d.name}：cookie 與本機憑證是同一顆、HttpOnly＋Secure`,
          c.cookie && c.cookie === c.local && c.httpOnly && c.secure,
          { same: c.cookie === c.local, httpOnly: c.httpOnly, secure: c.secure });
  }
  const distinct = new Set(await Promise.all(
    [A, B, C].map(async (d) => (await credentialCopies(d)).cookie)));
  check("三台裝置各有自己的一顆憑證", distinct.size === 3);
  check("A 登入時換發了新憑證（匿名那顆作廢）",
        anonCookieA === null || anonCookieA !== (await credentialCopies(A)).cookie);

  if (WRITE) {
    const created = await api(B, "POST", "/api/scenarios", NEW);
    const sid = created.body.id;
    check("B 新增的劇本，A、C 立刻看得到",
          (await scenarioIds(A)).includes(sid) && (await scenarioIds(C)).includes(sid), { sid });
  }

  // 重新登入的憑證輪替：UI 上已登入的裝置要先「重設」（登出）再登入。
  const before = (await credentialCopies(A)).cookie;
  await uiReset(A);
  const loggedOut = (await credentialCopies(A)).cookie;
  await uiLogin(A, SU);
  const after = await credentialCopies(A);
  check("A 重新登入：換了一顆新憑證，cookie 與本機同步",
        after.cookie !== before && after.cookie !== loggedOut
        && after.cookie === after.local);
  check("A 重新登入後劇本仍一致", same(await scenarioIds(A), await scenarioIds(B)));
  const stale = await browser.newContext({ ignoreHTTPSErrors: true });
  const host = new URL(BASE).hostname;
  await stale.addCookies([{ name: "__Host-oc_owner", value: before, domain: host,
                            path: "/", secure: true, httpOnly: true, sameSite: "Lax" }]);
  const stalePage = await stale.newPage();
  await stalePage.goto(`${BASE}/#/`);
  const staleDevice = { name: "stale", context: stale, page: stalePage };
  check("A 舊的那顆憑證已作廢（拿到別台也沒有權限、看不到劇本）",
        (await role(staleDevice)) === "normal" && (await scenarioIds(staleDevice)).length === 0);
  await stale.close();

  // C 登出主帳號：只有 C 回到匿名 Normal，A、B 不受影響。
  const total = (await scenarioIds(B)).length;
  await uiReset(C);
  check("C 登出後是 normal、看不到主帳號劇本",
        (await role(C)) === "normal" && (await scenarioIds(C)).length === 0);
  check("A、B 不受 C 登出影響",
        (await role(A)) === "superuser" && (await role(B)) === "superuser"
        && (await scenarioIds(A)).length === total);

  if (!WRITE) {
    // 正式站：不留下任何裝置憑證。
    await uiReset(A);
    await uiReset(B);
  }
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(JSON.stringify({ base: BASE, write: WRITE, passed: results.length - failed.length,
                             failed: failed.length }, null, 2));
process.exit(failed.length ? 1 : 0);
