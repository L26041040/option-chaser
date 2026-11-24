// OS-06（#395）：機會搜尋的真瀏覽器＋本機真後端端到端驗證（固定測試資料）。
//
// 一支指令跑完：自己起兩個本機驗證站（`scripts/opportunity_verify_server.py`）——
//   A. 已設定來源：`FixtureAnalystSource`＋固定 chain＋本機測試 Postgres（每次重建一個
//      專用資料庫 `ocopportunity`，跟 pytest 用的 `octest` 分開）；
//   B. 未設定來源：MemoryStorage（＝正式站目前的狀態「尚未設定分析師資料來源」）。
// 再用真 Chromium（手機 viewport＋桌面）走完：SU 在設定頁調門檻 → 共識清單（入選／未入選
// 與原因、「測試資料」標示）→ 改門檻、清單跟著變且不重打上游 → 搜尋（逐檔續跑）→ 切換
// 排序 → 存成劇本 → 詳細頁頭條數字等於那一列 → Normal 看不到入口、網址被導走、API 403
// → 未設定站顯示「尚未設定」且不能搜尋 → 手機無水平捲動。
//
//   npm run build
//   PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium node scripts/opportunity_verify.mjs
//
// 環境：本機 Postgres 在 127.0.0.1:55432（`scripts/dev_env.sh`）、`.venv`（uvicorn）、
// `openssl`、`psql`／`createdb`／`dropdb`。可用 `OC_VERIFY_PYTHON` 指定 Python。
//
// ⚠ 安全（回報#141 的教訓）：
//   (1) Chromium 一律 `--no-proxy-server`（這個環境有 `HTTPS_PROXY`）；
//   (2) 任何寫入之前先做金絲雀：`/__verify/stats` 必須回本次隨機產生的 nonce、
//       `/api/health` 必須是 postgres 且沒有部署 commit、一筆試寫入必須出現在本機資料庫；
//       任何一項不符就中止（exit 3），什麼都不寫；
//   (3) 驗證站只連本機 Postgres（DSN 寫死 127.0.0.1），行程內有網路閘擋掉一切非 loopback
//       連線，結束時檢查被擋次數＝0、分析師／chain 都只走假資料；
//   (4) SU／SA 密碼與 cron secret 每次隨機產生、只給本機驗證站，不印出、不寫檔。
// 不截圖。
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, devices } from "@playwright/test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PG = { host: "127.0.0.1", port: "55432", user: "postgres" };
const DB = "ocopportunity";
const DSN = `postgresql://${PG.user}@${PG.host}:${PG.port}/${DB}`;
const PORT_A = Number(process.env.OC_VERIFY_PORT ?? 8461);
const PORT_B = PORT_A + 1;
const BASE = `https://127.0.0.1:${PORT_A}`;
const BASE_UNCONFIGURED = `https://127.0.0.1:${PORT_B}`;
const PYTHON = process.env.OC_VERIFY_PYTHON
  ?? [join(ROOT, ".venv/bin/python"), "/home/user/option-chaser/.venv/bin/python"]
    .find((p) => existsSync(p)) ?? "python3";
const CHAIN_DELAY = "1.2";   // 秒：讓「逐檔出現」在畫面上看得到中間狀態
const FIXTURE_SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"];
const PHONE = { ...devices["iPhone 13"] };
delete PHONE.defaultBrowserType;
const DESKTOP = { viewport: { width: 1280, height: 800 } };

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail === undefined ? "" : "  " + JSON.stringify(detail)}`);
  return Boolean(ok);
}
function abort(message) {
  console.error(`ABORT  ${message}`);
  throw Object.assign(new Error(message), { abort: true });
}

// ---------- 本機資料庫與驗證站 ----------

const pgArgs = ["-h", PG.host, "-p", PG.port, "-U", PG.user];
function sql(query) {
  return execFileSync("psql", ["-X", "-qtA", ...pgArgs, "-d", DB, "-c", query],
                      { encoding: "utf8" }).trim();
}
function resetDatabase() {
  execFileSync("dropdb", [...pgArgs, "--if-exists", DB]);
  execFileSync("createdb", [...pgArgs, DB]);
}

const secrets = {
  OC_VERIFY_SU_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_SA_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_CRON_SECRET: randomBytes(18).toString("base64url"),
  OC_VERIFY_NONCE: randomBytes(12).toString("hex"),
};

function startServer(args, label) {
  const env = { ...process.env, ...secrets, PYTHONPATH: ROOT };
  for (const k of ["HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY",
                   "all_proxy", "DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL",
                   "DATABASE_URL_POOLED", "POSTGRES_URL_NON_POOLING"]) delete env[k];
  const child = spawn(PYTHON, [join(ROOT, "scripts/opportunity_verify_server.py"), ...args],
                      { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  const ready = new Promise((resolveReady, reject) => {
    const onData = (chunk) => {
      log += chunk.toString();
      if (log.includes("Uvicorn running on")) resolveReady();
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.on("exit", (code) => reject(new Error(`${label} 驗證站提早結束（${code}）：\n${log.slice(-2000)}`)));
    setTimeout(() => reject(new Error(`${label} 驗證站 60 秒內沒有起來：\n${log.slice(-2000)}`)), 60000);
  });
  return { child, ready, log: () => log };
}

// ---------- 瀏覽器小工具 ----------

async function api(page, method, path, { body, headers } = {}) {
  return page.evaluate(async ([m, p, b, h]) => {
    const r = await fetch(p, { method: m,
      headers: { ...(b ? { "Content-Type": "application/json" } : {}), ...(h ?? {}) },
      body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json };
  }, [method, path, body, headers]);
}

const stats = async (page) => (await api(page, "GET", "/__verify/stats")).body;

async function noHorizontalScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
}

async function uiLogin(page, base, password) {
  await page.goto(`${base}/#/settings`);
  const input = page.locator("input[type=password]:visible").first();
  await input.waitFor();
  await input.fill(password);
  const reloaded = page.waitForEvent("load");
  await page.locator("button:visible", { hasText: /^登入$/ }).first().click();
  await reloaded;
  await page.waitForLoadState("networkidle");
}

const money = (x) => `$${x.toFixed(2)}`;
const pct = (x) => `${(x * 100).toFixed(1)}%`;

async function openOpportunityFromNav(page, desktop) {
  await page.goto(`${BASE}/#/`);
  const nav = desktop
    ? page.getByRole("navigation", { name: "主導覽" }).getByRole("link", { name: "機會搜尋" })
    : page.getByRole("navigation", { name: "主要導覽" }).getByRole("link", { name: /機會/ });
  await nav.click();
  await page.waitForURL(/#\/opportunity$/);
  await page.getByRole("region", { name: "掃描股票範圍" }).waitFor();
}

async function saveThresholds(page, { percentile, dispersion, symbols }) {
  await page.goto(`${BASE}/#/settings/opportunity`);
  const section = page.getByRole("region", { name: "機會搜尋" });
  await section.waitFor();
  // V2-03（#405）：第一道門檻以 PR 輸入（PR = 100 − 原百分位；存回的仍是原百分位）。
  await section.getByLabel("分歧度歷史排序門檻：PR ≥").fill(String(100 - percentile));
  await section.getByLabel("分析師分歧率上限（%）").fill(String(dispersion));
  if (symbols) {
    await section.getByRole("radio", { name: "自訂清單" }).check();
    await section.getByLabel("Ticker 清單").fill(symbols.join(", "));
  }
  await section.getByRole("button", { name: "儲存" }).click();
  await section.getByRole("status").filter({ hasText: "已儲存" }).waitFor();
}

async function listed(page, region) {
  const r = page.getByRole("region", { name: region });
  if (await r.count() === 0) return [];
  return r.locator(":scope > ul.opp-list > li").evaluateAll(
    (items) => items.map((li) => li.getAttribute("aria-label")));
}

// ---------- 主流程 ----------

async function canary(browser) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const resp = await page.goto(`${BASE}/__verify/stats`, { timeout: 15000 }).catch(() => null);
  let s = null;
  try { s = await resp?.json(); } catch { /* 不是 JSON → 不是本機驗證站 */ }
  if (s?.nonce !== secrets.OC_VERIFY_NONCE || s?.label !== `postgres:${DB}`) {
    abort("金絲雀失敗：瀏覽器連到的不是本次啟動的本機驗證站。沒有送出任何寫入。");
  }
  const health = (await api(page, "GET", "/api/health")).body;
  if (health?.storage !== "postgres" || health?.backend?.commit !== null) {
    abort(`金絲雀失敗：/api/health 不像本機站（${JSON.stringify(health?.backend)}）。`);
  }
  const before = Number(sql("SELECT count(*) FROM scenarios"));
  const created = await api(page, "POST", "/api/scenarios", { body: {
    symbol: "ZZCANARY", target_price: 120, target_month: "2027-01",
    strategies: ["vertical-spread"] } });
  if (created.status !== 201 || Number(sql("SELECT count(*) FROM scenarios")) !== before + 1) {
    abort(`金絲雀失敗：試寫入沒有出現在本機資料庫（status ${created.status}）。`);
  }
  console.log("OK    金絲雀：瀏覽器連到本次的本機驗證站，寫入落在本機資料庫 " + DB);
  await ctx.close();
}

async function suPhoneFlow(browser) {
  const ctx = await browser.newContext({ ...PHONE, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/#/`);
  await uiLogin(page, BASE, secrets.OC_VERIFY_SU_PASSWORD);
  check("手機 SU：登入後角色是 superuser",
        (await api(page, "GET", "/api/auth/status")).body?.role === "superuser");

  // 1) 設定頁：母體換成測試清單、門檻用預設值 20／10。
  await saveThresholds(page, { percentile: 20, dispersion: 10, symbols: FIXTURE_SYMBOLS });
  const settings = (await api(page, "GET", "/api/settings")).body.opportunity_search;
  check("手機 SU：設定頁存下門檻 20／10 與自訂母體",
        settings.percentile_max === 20 && settings.dispersion_max === 10
        && settings.universe_id === "custom", settings);

  // 2) 每日共識更新（cron；本機驗證站的拋棄式 cron secret），跑到沒有 remaining。
  for (let i = 0; i < 20; i++) {
    const r = await api(page, "GET", "/api/cron/consensus-refresh",
                        { headers: { Authorization: `Bearer ${secrets.OC_VERIFY_CRON_SECRET}` } });
    if (r.status !== 200) abort(`cron 失敗：${r.status}`);
    if (!r.body.remaining?.length) break;
  }
  const afterCron = await stats(page);
  check("共識更新只呼叫固定測試資料來源（有呼叫、沒有被擋的對外連線）",
        afterCron.analyst_fetches > 0 && afterCron.blocked_connections === 0,
        { analyst_fetches: afterCron.analyst_fetches });

  // 3) 從導覽進機會搜尋頁：測試資料標示、入選／未入選與原因。
  await openOpportunityFromNav(page, false);
  check("手機 SU：導覽有「機會」入口，點了進到 #/opportunity", true);
  check("手機：頁首常駐「測試資料，非真實市場資料」",
        await page.getByRole("banner", { name: "機會搜尋頁首" })
          .getByText("測試資料，非真實市場資料").isVisible());
  let selected = await listed(page, "符合條件的股票");
  check("預設門檻：符合條件 AAA、EEE", JSON.stringify(selected) === '["AAA","EEE"]', selected);
  const weak = page.getByRole("region", { name: "不符合條件" });
  check("不符合條件列出 BBB、CCC",
        JSON.stringify(await listed(page, "不符合條件")) === '["BBB","CCC"]',
        await listed(page, "不符合條件"));
  check("BBB 的原因：分析師分歧率高於上限 10%",
        /分析師分歧率 1\d\.\d%，高於上限 10%/.test(await weak.getByRole("listitem", { name: "BBB" }).innerText()));
  check("CCC 的原因：分歧度歷史排序未達門檻 PR ≥ 80",
        /分歧度歷史排序 PR\d+（前 \d+%），未達門檻 PR ≥ 80/.test(await weak.getByRole("listitem", { name: "CCC" }).innerText()));
  const thin = page.getByRole("region", { name: "資料不足" });
  check("資料不足列出 DDD、FFF、GGG 並寫原因",
        JSON.stringify(await listed(page, "資料不足")) === '["DDD","FFF","GGG"]'
        && /分析師人數不足/.test(await thin.getByRole("listitem", { name: "DDD" }).innerText())
        && /無資料/.test(await thin.getByRole("listitem", { name: "FFF" }).innerText())
        && /來源失敗/.test(await thin.getByRole("listitem", { name: "GGG" }).innerText()));
  check("手機：共識清單頁無水平捲動", await noHorizontalScroll(page));

  // 4) 改門檻（分歧度 16%）→ 清單改變，而且不重打上游。
  const beforeChange = await stats(page);
  await page.getByRole("link", { name: "調整門檻" }).click();
  await page.waitForURL(/#\/settings\/opportunity$/);
  await saveThresholds(page, { percentile: 20, dispersion: 16 });
  await openOpportunityFromNav(page, false);
  selected = await listed(page, "符合條件的股票");
  check("改分析師分歧率上限 16%：BBB 符合條件（AAA、BBB、EEE）",
        JSON.stringify(selected) === '["AAA","BBB","EEE"]', selected);
  check("改門檻後頁面顯示新門檻",
        /分析師分歧率 ≤ 16%/.test(await page.getByRole("region", { name: "掃描股票範圍" }).innerText()));
  const afterChange = await stats(page);
  check("改門檻沒有新的上游呼叫（分析師來源、chain 次數都不變）",
        afterChange.analyst_fetches === beforeChange.analyst_fetches
        && afterChange.chain_fetches === beforeChange.chain_fetches,
        { before: beforeChange.analyst_fetches, after: afterChange.analyst_fetches });

  // 5) 搜尋：逐檔續跑、逐檔出現。
  const responses = [];
  const requests = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/opportunity/search")) requests.push(r.postDataJSON());
  });
  page.on("response", async (r) => {
    if (r.url().endsWith("/api/opportunity/search")) responses.push(await r.json());
  });
  const chainBefore = (await stats(page)).chain_fetches;
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await page.getByText("已搜尋 1 / 3 檔").waitFor({ timeout: 15000 });
  const midRows = await page.getByRole("region", { name: "搜尋結果" })
    .locator("tbody tr").count().catch(() => 0);
  check("搜尋中：第一檔的結果已經出現、還在續跑（已搜尋 1 / 3 檔）",
        midRows > 0 && await page.getByText("搜尋中……").isVisible(), { midRows });
  await page.getByText("已搜尋 3 / 3 檔").waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: "搜尋選擇權" }).and(page.locator(":enabled")).waitFor();
  check("搜尋續跑三次、每次一檔，第二、三次只送 remaining",
        JSON.stringify(requests) === JSON.stringify([{}, { symbols: ["BBB", "EEE"] }, { symbols: ["EEE"] }])
        && responses.every((r) => r.processed.length === 1), { requests });
  const rows = responses.flatMap((r) => r.rows);
  // AAA（平均 120 > 現價 100）三個家族都有代表候選；BBB 平均 100＝現價（持平），
  // 既有方向規則只留 Butterfly——這是引擎本身的結果，不是搜尋器過濾的。
  const families = (sym) => rows.filter((r) => r.symbol === sym).map((r) => r.family).sort();
  check("逐檔結果：AAA 三個家族、BBB（持平）只有 Butterfly；EEE 抓鏈失敗列在「搜尋失敗」",
        JSON.stringify(families("AAA")) === '["butterfly","single-leg","vertical-spread"]'
        && JSON.stringify(families("BBB")) === '["butterfly"]' 
        && /抓不到報價/.test(await page.getByRole("region", { name: "搜尋失敗" })
          .getByRole("listitem", { name: "EEE" }).innerText()));
  const after = await stats(page);
  check("搜尋只打了 3 次 chain（假資料）、沒有被擋的對外連線",
        after.chain_fetches - chainBefore === 3 && after.blocked_connections === 0);

  const results = page.getByRole("region", { name: "搜尋結果" });
  const order = () => results.locator("tbody tr").evaluateAll(
    (trs) => trs.map((tr) => `${tr.querySelector("td")?.textContent}|${tr.getAttribute("data-family")}`));
  const keyOf = (r) => `${r.symbol}|${r.family}`;
  const sortedBy = (f, dir) => [...rows].sort((a, b) =>
    dir * (f(a) - f(b)) || a.symbol.localeCompare(b.symbol) || a.family.localeCompare(b.family)).map(keyOf);
  check("預設排序：股價達標時的策略報酬由高到低",
        JSON.stringify(await order()) === JSON.stringify(sortedBy((r) => r.target_return, -1)));
  const searchCalls = requests.length;
  await results.getByRole("combobox", { name: "排序" }).selectOption("cost");
  check("切換排序：投入成本由低到高",
        JSON.stringify(await order()) === JSON.stringify(sortedBy((r) => r.entry_cost, 1)));
  await results.getByRole("combobox", { name: "排序" }).selectOption("max_loss");
  check("切換排序：最大損失由低到高",
        JSON.stringify(await order()) === JSON.stringify(sortedBy((r) => r.max_loss_per_contract, 1)));
  check("切換排序沒有重新搜尋", requests.length === searchCalls);
  let cellsOk = true;
  for (const r of rows) {
    const tr = results.locator(`tbody tr[data-family="${r.family}"]`)
      .filter({ has: page.locator("td.opp-symbol", { hasText: r.symbol }) });
    const cost = await tr.locator('td[data-label="成本 / 股"]').innerText();
    const loss = await tr.locator('td[data-label="最大損失 / 股"]').innerText();
    cellsOk &&= cost === money(r.entry_cost) && loss === money(r.max_loss_per_contract / 100);
  }
  check("每列：成本 / 股＝entry_cost、最大損失 / 股＝max_loss_per_contract ÷ 100", cellsOk);
  check("手機：搜尋結果頁無水平捲動", await noHorizontalScroll(page));

  // 6) 存成劇本：報酬最高的一列（它也是該劇本跨家族的冠軍＝詳細頁頭條）。
  await results.getByRole("combobox", { name: "排序" }).selectOption("return");
  const top = [...rows].sort((a, b) => b.target_return - a.target_return)[0];
  const topRow = results.locator(`tbody tr[data-family="${top.family}"]`)
    .filter({ has: page.locator("td.opp-symbol", { hasText: top.symbol }) });
  const scenariosBefore = Number(sql("SELECT count(*) FROM scenarios"));
  await topRow.getByRole("button", { name: "存成劇本" }).click();
  await page.waitForURL(/#\/s\/[^/]+$/, { timeout: 30000 });
  const id = decodeURIComponent(page.url().split("#/s/")[1]);
  check("存成劇本：本機資料庫多一個劇本、導到它的詳細頁",
        Number(sql("SELECT count(*) FROM scenarios")) === scenariosBefore + 1, { id });
  const hero = page.getByRole("region", { name: "劇本頭條" });
  await hero.waitFor({ timeout: 30000 });
  const heroText = await hero.innerText();
  check("手機詳細頁頭條：同一檔、目標價情境報酬與該列相同",
        heroText.includes(top.symbol) && heroText.includes(pct(top.target_return)),
        { want: [top.symbol, pct(top.target_return)] });
  check("手機詳細頁頭條：目標價＝共識平均、目標月份相同",
        heroText.includes(`目標 ${money(top.scenario.target_price)} · ${top.target_month}`));
  const entry = page.locator("section.card", { hasText: "進場 · 以最差成交價計算" });
  const rowValue = async (label) => entry.locator(":scope > .row", {
    has: page.locator(".row-label", { hasText: new RegExp(`^${label}$`) }) })
    .first().locator(".row-value").innerText();
  check("手機詳細頁：淨成本 / 股＝該列", (await rowValue("淨成本 / 股")) === money(top.entry_cost));
  check("手機詳細頁：Max Loss＝該列的最大損失 / 股",
        (await rowValue("Max Loss")) === money(top.max_loss_per_contract / 100));
  check("手機詳細頁：Breakeven＝該列",
        top.breakeven === null || (await rowValue("Breakeven")).includes(money(top.breakeven)));
  const legLabels = (await entry.locator(":scope > .row .row-label").allInnerTexts())
    .slice(0, top.legs.length);
  const wantLegs = top.legs.map((l) => `${l.side === "buy" ? "買" : "賣"} ${l.quantity > 1 ? `${l.quantity}×` : ""}${l.strike}`);
  check("手機詳細頁：進場各腿履約價＝該列", JSON.stringify(legLabels) === JSON.stringify(wantLegs),
        { legLabels, wantLegs });
  const detail = (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
  const champion = detail?.representative_candidate;
  // Postgres JSONB 不保留鍵的順序，逐欄比較。
  const legKey = (l) => [l.side, l.option_type, l.strike, l.quantity].join(":");
  check("詳細資料（API）：劇本的冠軍代表候選＝該列（候選、到期日、各腿、報酬逐欄相同）",
        detail?.symbol === top.symbol && champion?.candidate_key === top.candidate_key
        && champion.expiry === top.expiry && champion.baseline_return === top.target_return
        && detail.best_return === top.target_return
        && JSON.stringify(champion.legs.map(legKey)) === JSON.stringify(top.legs.map(legKey)),
        { champion: champion && { key: champion.candidate_key, ret: champion.baseline_return } });
  check("手機：詳細頁無水平捲動", await noHorizontalScroll(page));
  await ctx.close();
  return { top, id, rowCount: rows.length };
}

async function suDesktopFlow(browser, saved) {
  const ctx = await browser.newContext({ ...DESKTOP, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/#/`);
  await uiLogin(page, BASE, secrets.OC_VERIFY_SU_PASSWORD);
  await openOpportunityFromNav(page, true);
  check("桌面 SU：主導覽有「機會搜尋」，清單沿用同一份門檻（AAA、BBB、EEE）",
        JSON.stringify(await listed(page, "符合條件的股票")) === '["AAA","BBB","EEE"]');
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await page.getByText("已搜尋 3 / 3 檔").waitFor({ timeout: 30000 });
  const results = page.getByRole("region", { name: "搜尋結果" });
  check("桌面：搜尋結果列數與手機相同", (await results.locator("tbody tr").count()) === saved.rowCount);
  check("桌面：搜尋結果頁無水平捲動", await noHorizontalScroll(page));
  const { top, id } = saved;
  await page.goto(`${BASE}/#/s/${encodeURIComponent(id)}`);
  const body = page.locator("body");
  await page.getByText("淨成本 / 股").first().waitFor({ timeout: 30000 });
  const text = await body.innerText();
  check("桌面詳細頁：顯示該列的報酬、淨成本 / 股、最大損失（每股值）",
        text.includes(pct(top.target_return)) && text.includes(money(top.entry_cost))
        && text.includes(money(top.max_loss_per_contract / 100)));
  check("桌面：詳細頁無水平捲動", await noHorizontalScroll(page));
  await ctx.close();
}

async function normalFlow(browser) {
  for (const [label, opts] of [["手機", PHONE], ["桌面", DESKTOP]]) {
    const ctx = await browser.newContext({ ...opts, ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    const opportunityCalls = [];
    page.on("request", (r) => { if (r.url().includes("/api/opportunity/")) opportunityCalls.push(r.url()); });
    await page.goto(`${BASE}/#/`);
    await page.waitForLoadState("networkidle");
    check(`${label} Normal：角色是 normal`,
          (await api(page, "GET", "/api/auth/status")).body?.role === "normal");
    check(`${label} Normal：導覽沒有機會搜尋入口`,
          (await page.getByRole("link", { name: /機會/ }).count()) === 0);
    await page.goto(`${BASE}/#/opportunity`);
    await page.waitForURL((u) => !u.hash.startsWith("#/opportunity"), { timeout: 10000 }).catch(() => {});
    check(`${label} Normal：直接打 #/opportunity 被導走、頁面沒打機會搜尋端點`,
          !new URL(page.url()).hash.startsWith("#/opportunity") && opportunityCalls.length === 0,
          { url: page.url(), calls: opportunityCalls.length });
    const consensus = await api(page, "GET", "/api/opportunity/consensus");
    const search = await api(page, "POST", "/api/opportunity/search", { body: {} });
    check(`${label} Normal：共識清單與搜尋 API 都回 403`,
          consensus.status === 403 && search.status === 403, [consensus.status, search.status]);
    const usage = { mode: "default", provider: null };
    const write = await api(page, "PUT", "/api/settings", { body: {
      market_data: usage, historical_iv: usage,
      opportunity_search: { universe_id: "custom", custom_symbols: ["NORMX"] } } });
    const view = (await api(page, "GET", "/api/settings")).body;
    check(`${label} Normal：寫 opportunity_search（自訂清單）被拒 403，讀回仍是預設`,
          write.status === 403 && view?.opportunity_search?.universe_id === "sp500"
          && view.opportunity_search.custom_symbols.length === 0,
          { status: write.status, universe: view?.opportunity_search?.universe_id });
    if (label === "手機") check("手機 Normal：首頁無水平捲動", await noHorizontalScroll(page));
    await ctx.close();
  }
}

async function unconfiguredFlow(browser) {
  const ctx = await browser.newContext({ ...PHONE, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const resp = await page.goto(`${BASE_UNCONFIGURED}/__verify/stats`);
  const s = await resp.json();
  if (s.nonce !== secrets.OC_VERIFY_NONCE || s.label !== "memory" || s.configured !== false) {
    abort("金絲雀失敗：未設定來源的驗證站不是本次啟動的那一個");
  }
  await page.goto(`${BASE_UNCONFIGURED}/#/`);
  await uiLogin(page, BASE_UNCONFIGURED, secrets.OC_VERIFY_SU_PASSWORD);
  await page.goto(`${BASE_UNCONFIGURED}/#/opportunity`);
  // LIVE-T5（#401）：部署環境預設啟用真實來源，沒有來源只會是緊急關閉開關生效。
  await page.getByRole("heading", { name: "分析師資料來源已關閉" }).waitFor({ timeout: 15000 });
  check("未設定來源：SU 看到「分析師資料來源已關閉」（緊急關閉），沒有任何按鈕",
        (await page.locator(".opp-page").getByRole("button").count()) === 0);
  check("未設定來源：沒有搜尋按鈕、沒有清單、沒有測試資料標示",
        (await page.getByRole("button", { name: "搜尋選擇權" }).count()) === 0
        && (await page.getByRole("region", { name: "符合條件的股票" }).count()) === 0
        && (await page.getByText("測試資料，非真實市場資料").count()) === 0);
  const search = await api(page, "POST", "/api/opportunity/search", { body: {} });
  check("未設定來源：搜尋 API 回 409「尚未設定分析師資料來源」",
        search.status === 409 && /尚未設定分析師資料來源/.test(JSON.stringify(search.body)));
  check("未設定來源（手機）：無水平捲動", await noHorizontalScroll(page));
  const final = await stats(page);
  check("未設定站：沒有任何分析師／chain 呼叫、沒有被擋的對外連線",
        final.analyst_fetches === 0 && final.chain_fetches === 0 && final.blocked_connections === 0);
  await ctx.close();
}

async function main() {
  if (!existsSync(join(ROOT, "dist/index.html"))) abort("找不到 dist/：先跑 npm run build");
  resetDatabase();
  const tmp = mkdtempSync(join(tmpdir(), "oc-opp-verify-"));
  const cert = join(tmp, "cert.pem"), key = join(tmp, "key.pem");
  execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                           "-out", cert, "-days", "1", "-subj", "/CN=127.0.0.1"], { stdio: "ignore" });
  const common = ["--cert", cert, "--key", key, "--chain-delay", CHAIN_DELAY];
  const servers = [
    startServer(["--dsn", DSN, "--port", String(PORT_A), ...common], "已設定"),
    startServer(["--memory", "--unconfigured", "--port", String(PORT_B), ...common], "未設定"),
  ];
  let browser;
  let aborted = false;
  try {
    await Promise.all(servers.map((s) => s.ready));
    browser = await chromium.launch({
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"],
    });
    await canary(browser);
    const saved = await suPhoneFlow(browser);
    await suDesktopFlow(browser, saved);
    await normalFlow(browser);
    await unconfiguredFlow(browser);
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/__verify/stats`);
    const final = await stats(page);
    check("已設定站全程：被擋的對外連線 0 次", final.blocked_connections === 0,
          { blocked: final.blocked_targets });
    await ctx.close();
  } catch (e) {
    aborted = Boolean(e.abort);
    if (!e.abort) {
      console.error(e);
      for (const s of servers) console.error(s.log().slice(-1500));
    }
    check("流程沒有中途出錯", false, String(e.message ?? e).split("\n")[0]);
  } finally {
    await browser?.close();
    for (const s of servers) s.child.kill("SIGTERM");
    rmSync(tmp, { recursive: true, force: true });
  }
  const failed = checks.filter((r) => !r.ok);
  console.log(JSON.stringify({ checks: checks.length, passed: checks.length - failed.length,
                               failed: failed.length }, null, 2));
  process.exit(aborted ? 3 : failed.length ? 1 : 0);
}

await main();
