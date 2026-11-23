// LIVE-T4（#400）：機會搜尋接**真實上游**的真瀏覽器＋本機後端驗證。
//
// 起一個本機驗證站（`scripts/opportunity_live_verify_server.py`）：`dist/` 前端＋同一個
// FastAPI app，分析師資料是真實 Yahoo、選擇權報價走既有預設路徑（Cboe → yfinance）、
// 資料庫是每次重建的本機 Postgres `oclivebrowser`。真 Chromium（手機 viewport）走完：
// SU 登入 → 設定頁存門檻與自訂清單 → 機會搜尋頁先顯示「資料建立中」且不能搜 →
// 資料狀態（LIVE-T5／#401）：真實來源、建立中、已建立 0／N →
// 按「開始建立」（真實 Yahoo）→ 已建立 N／N、入選清單出現 → 搜尋選擇權（真實 chain）→
// 報酬最高的一列打開共識詳細資料（平均目標價＝劇本目標價）→「存成劇本」→
// 詳細頁頭條與該列一致（逐欄）。每個畫面都檢查手機寬度沒有水平捲動。
//
//   npm run build
//   PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium \
//     SSL_CERT_FILE=/root/.ccr/ca-bundle.crt node scripts/opportunity_live_verify.mjs JPM BAC WFC
//
// ⚠ 安全（回報#141 的教訓）：
//   (1) Chromium 一律 `--no-proxy-server`：瀏覽器只連本機驗證站；
//   (2) 任何寫入之前先做金絲雀：`/__verify/stats` 必須回本次隨機 nonce、`/api/health`
//       必須是 postgres 且沒有部署 commit、一筆試寫入必須出現在本機資料庫；不符就中止
//       （exit 3），什麼都不寫；
//   (3) 驗證站只連本機 Postgres（DSN 寫死 127.0.0.1），殼層裡的資料庫連線字串一律清掉；
//       驗證站行程本身經沙箱 HTTPS proxy 連真實上游（Yahoo），任何直連都被網路閘擋下；
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
const DB = "oclivebrowser";
const DSN = `postgresql://${PG.user}@${PG.host}:${PG.port}/${DB}`;
const PORT = Number(process.env.OC_VERIFY_PORT ?? 8471);
const BASE = `https://127.0.0.1:${PORT}`;
const PYTHON = process.env.OC_VERIFY_PYTHON
  ?? [join(ROOT, ".venv/bin/python"), "/home/user/option-chaser/.venv/bin/python"]
    .find((p) => existsSync(p)) ?? "python3";
const SYMBOLS = process.argv.slice(2).length ? process.argv.slice(2) : ["JPM", "BAC", "WFC"];
const PHONE = { ...devices["iPhone 13"] };
delete PHONE.defaultBrowserType;

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

const pgArgs = ["-h", PG.host, "-p", PG.port, "-U", PG.user];
const sql = (query) => execFileSync("psql", ["-X", "-qtA", ...pgArgs, "-d", DB, "-c", query],
                                    { encoding: "utf8" }).trim();

const secrets = {
  OC_VERIFY_SU_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_SA_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_CRON_SECRET: randomBytes(18).toString("base64url"),
  OC_VERIFY_NONCE: randomBytes(12).toString("hex"),
};

function startServer(args) {
  // 驗證站行程要經沙箱 proxy 連真實上游，proxy 變數保留；資料庫連線字串一律清掉。
  const env = { ...process.env, ...secrets, PYTHONPATH: ROOT };
  for (const k of ["DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL",
                   "DATABASE_URL_POOLED", "POSTGRES_URL_NON_POOLING"]) delete env[k];
  const child = spawn(PYTHON, [join(ROOT, "scripts/opportunity_live_verify_server.py"), ...args],
                      { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  const ready = new Promise((resolveReady, reject) => {
    const onData = (chunk) => {
      log += chunk.toString();
      if (log.includes("Uvicorn running on")) resolveReady();
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.on("exit", (code) => reject(new Error(`驗證站提早結束（${code}）：\n${log.slice(-2000)}`)));
    setTimeout(() => reject(new Error(`驗證站 60 秒內沒有起來：\n${log.slice(-2000)}`)), 60000);
  });
  return { child, ready, log: () => log };
}

async function api(page, method, path, { body } = {}) {
  return page.evaluate(async ([m, p, b]) => {
    const r = await fetch(p, { method: m,
      headers: b ? { "Content-Type": "application/json" } : {},
      body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json };
  }, [method, path, body]);
}
const stats = async (page) => (await api(page, "GET", "/__verify/stats")).body;
const noHorizontalScroll = (page) => page.evaluate(
  () => document.documentElement.scrollWidth <= window.innerWidth);
const money = (x) => `$${x.toFixed(2)}`;
const pct = (x) => `${(x * 100).toFixed(1)}%`;

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
    symbol: "ZZCANARY", target_price: 120, target_month: "2027-12",
    strategies: ["vertical-spread"] } });
  if (created.status !== 201 || Number(sql("SELECT count(*) FROM scenarios")) !== before + 1) {
    abort(`金絲雀失敗：試寫入沒有出現在本機資料庫（status ${created.status}）。`);
  }
  console.log(`OK    金絲雀：瀏覽器連到本次的本機驗證站，寫入落在本機資料庫 ${DB}`);
  await ctx.close();
}

async function flow(browser) {
  const ctx = await browser.newContext({ ...PHONE, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/#/`);
  await page.goto(`${BASE}/#/settings`);
  const input = page.locator("input[type=password]:visible").first();
  await input.waitFor();
  await input.fill(secrets.OC_VERIFY_SU_PASSWORD);
  const reloaded = page.waitForEvent("load");
  await page.locator("button:visible", { hasText: /^登入$/ }).first().click();
  await reloaded;
  await page.waitForLoadState("networkidle");
  check("SU 登入", (await api(page, "GET", "/api/auth/status")).body?.role === "superuser");

  // 設定頁：預設門檻 20／10、自訂清單。
  await page.goto(`${BASE}/#/settings/opportunity`);
  const section = page.getByRole("region", { name: "機會搜尋" });
  await section.waitFor().catch(async (e) => {
    console.error("DEBUG regions: " + JSON.stringify(await page.locator("section[aria-label]")
      .evaluateAll((xs) => xs.map((x) => x.getAttribute("aria-label")))));
    console.error("DEBUG url: " + page.url());
    throw e;
  });
  await section.getByLabel("分歧度歷史百分位門檻（%）").fill("20");
  await section.getByLabel("分歧度門檻（%）").fill("10");
  await section.getByRole("radio", { name: "自訂清單" }).check();
  await section.getByLabel("Ticker 清單").fill(SYMBOLS.join(", "));
  await section.getByRole("button", { name: "儲存" }).click();
  await section.getByRole("status").filter({ hasText: "已儲存" }).waitFor();

  // 共識還沒建立：「資料建立中」、搜尋停用。
  await page.goto(`${BASE}/#/opportunity`);
  const selectedRegion = page.getByRole("region", { name: "入選股" });
  await selectedRegion.waitFor({ timeout: 20000 });
  check("共識還沒建立：入選股區塊顯示「資料建立中」，不顯示「沒有入選股」",
        /資料建立中/.test(await selectedRegion.innerText())
        && !/目前沒有同時通過兩道門檻的股票/.test(await selectedRegion.innerText()));
  check("共識還沒建立：搜尋按鈕停用",
        await selectedRegion.getByRole("button", { name: "搜尋選擇權" }).isDisabled());
  const panel = page.getByRole("region", { name: "分析師資料" });
  const facts = panel.getByRole("list", { name: "資料狀態" });
  const fact = (name) => facts.getByRole("listitem", { name }).innerText();
  await facts.getByRole("listitem", { name: "今日更新" }).waitFor({ timeout: 20000 });
  check("資料狀態（#401）：建立中、真實分析師資料、已建立 0／N、入選 0",
        /建立中/.test(await panel.getByRole("heading", { name: /^分析師資料/ }).innerText())
        && /真實分析師資料/.test(await fact("資料來源"))
        && (await fact("已建立")).includes(`0／${SYMBOLS.length} 檔`)
        && (await fact("入選")).includes("0 檔"),
        { 資料來源: await fact("資料來源"), 已建立: await fact("已建立") });
  check("資料狀態（手機）：無水平捲動", await noHorizontalScroll(page));

  // 開始建立（真實 Yahoo，#398 的更新路徑；母體＝樣本 ∪ 自訂清單）。
  const t0 = Date.now();
  await panel.getByRole("button", { name: "開始建立" }).click();
  await page.getByText(/更新完成/).waitFor({ timeout: 300000 });
  const afterUpdate = await stats(page);
  check("更新分析師資料：真的呼叫了 Yahoo（真實來源）",
        afterUpdate.analyst_fetches > 0, { analyst_fetches: afterUpdate.analyst_fetches,
                                           seconds: Math.round((Date.now() - t0) / 1000) });
  await page.waitForFunction(() => !/資料建立中/.test(
    document.querySelector('[aria-label="入選股"]')?.textContent ?? ""), null, { timeout: 30000 });
  const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
  const selected = consensus.items.filter((i) => i.gate.selected);
  console.log("INFO  入選：" + JSON.stringify(selected.map((i) => ({
    symbol: i.symbol, mean: i.mean, dispersion: i.dispersion, percentile: i.percentile }))));
  check("入選股全部是真實共識 status ok、兩關都過，來源是 yahoo-udh（非測試資料）",
        selected.length > 0 && selected.every((i) => i.status === "ok" && i.gate.first && i.gate.second)
        && consensus.source.name === "yahoo-udh" && consensus.source.is_fixture === false,
        selected.map((i) => i.symbol));
  check("頁面沒有「測試資料」標示", (await page.getByText("測試資料，非真實市場資料").count()) === 0);
  await page.waitForFunction((n) => (document.querySelector('[aria-label="已建立"]')?.textContent ?? "")
    .includes(`${n}／${n} 檔`), SYMBOLS.length, { timeout: 30000 });
  const phase = await panel.getByRole("heading", { name: /^分析師資料/ }).innerText();
  check("資料狀態（#401）：建好後不再是建立中，已建立 N／N、入選檔數＝共識清單、資料日＝共識資料日",
        !/建立中/.test(phase) && (await fact("入選")).includes(`${selected.length} 檔`)
        && (await fact("資料日")).includes(consensus.universe.as_of),
        { phase, 入選: await fact("入選"), 資料日: await fact("資料日") });

  // 搜尋選擇權（真實 chain，逐檔續跑）。
  const responses = [];
  page.on("response", async (r) => {
    if (r.url().endsWith("/api/opportunity/search")) responses.push(await r.json());
  });
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await page.getByText(`已搜尋 ${selected.length} / ${selected.length} 檔`)
    .waitFor({ timeout: 120000 * selected.length });
  await page.getByRole("button", { name: "搜尋選擇權" }).and(page.locator(":enabled")).waitFor();
  const rows = responses.flatMap((r) => r.rows);
  const failures = responses.flatMap((r) => r.failures);
  const s = await stats(page);
  console.log("INFO  搜尋：" + JSON.stringify({
    rows: rows.length, failures: failures.map((f) => [f.symbol, f.reason, f.message]),
    chain_attempts: s.chain_attempts, chain_sources: s.chain_sources }));
  check("搜尋有結果（真實 chain）", rows.length > 0);
  check("網路閘：沒有任何被擋的直連", s.blocked_connections === 0, s.blocked_targets);

  // 存成劇本：報酬最高的一列。
  const results = page.getByRole("region", { name: "搜尋結果" });
  const top = [...rows].sort((a, b) => b.target_return - a.target_return)[0];
  console.log("INFO  頭條列：" + JSON.stringify({ symbol: top.symbol, family: top.family,
    subtype: top.subtype, expiry: top.expiry, target_return: top.target_return,
    entry_cost: top.entry_cost, max_loss_per_contract: top.max_loss_per_contract,
    breakeven: top.breakeven, target_price: top.scenario.target_price,
    target_month: top.target_month }));
  const topRow = results.locator(`tbody tr[data-family="${top.family}"]`)
    .filter({ has: page.locator("td.opp-symbol", { hasText: top.symbol }) });
  check("結果表（手機）：無水平捲動", await noHorizontalScroll(page));

  // 共識詳細資料（#401：每一列都能打開）。
  await topRow.getByRole("button", { name: `${top.symbol} 共識詳細資料` }).click();
  const detailPanel = results.getByRole("region", { name: `${top.symbol} 共識明細` });
  const numbers = detailPanel.getByRole("list", { name: "共識數值" });
  await numbers.waitFor({ timeout: 30000 });
  const numbersText = await numbers.innerText();
  check("結果列的共識詳細資料：平均目標價＝劇本目標價，有每月序列",
        numbersText.replace(/\s+/g, "").includes(`平均目標價${money(top.scenario.target_price)}`)
        && (await detailPanel.getByRole("list", { name: "每月分歧度" }).getByRole("listitem").count()) > 0,
        { numbers: numbersText.replace(/\s+/g, " ") });
  check("共識詳細資料（手機）：無水平捲動", await noHorizontalScroll(page));
  const before = Number(sql("SELECT count(*) FROM scenarios"));
  await topRow.getByRole("button", { name: "存成劇本" }).click();
  await page.waitForURL(/#\/s\/[^/]+$/, { timeout: 120000 });
  const id = decodeURIComponent(page.url().split("#/s/")[1]);
  check("存成劇本：本機資料庫多一個劇本、導到詳細頁",
        Number(sql("SELECT count(*) FROM scenarios")) === before + 1, { id });
  await page.getByText("淨成本 / 股").first().waitFor({ timeout: 120000 });
  const text = await page.locator("body").innerText();
  check("詳細頁頭條：同一檔、目標價情境報酬、淨成本 / 股、最大損失（每股）與該列相同",
        text.includes(top.symbol) && text.includes(pct(top.target_return))
        && text.includes(money(top.entry_cost)) && text.includes(money(top.max_loss_per_contract / 100)),
        { want: [top.symbol, pct(top.target_return), money(top.entry_cost),
                 money(top.max_loss_per_contract / 100)] });
  check("詳細頁：目標價＝共識平均、目標月份相同",
        text.includes(money(top.scenario.target_price)) && text.includes(top.target_month));
  const detail = (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
  const champion = detail?.representative_candidate;
  const legKey = (l) => [l.side, l.option_type, l.strike, l.quantity].join(":");
  check("詳細資料（API）：劇本冠軍＝該列（候選、到期日、各腿、報酬逐欄相同）",
        detail?.symbol === top.symbol && champion?.candidate_key === top.candidate_key
        && champion.expiry === top.expiry && champion.baseline_return === top.target_return
        && detail.best_return === top.target_return
        && JSON.stringify(champion.legs.map(legKey)) === JSON.stringify(top.legs.map(legKey)),
        { champion: champion && { key: champion.candidate_key, ret: champion.baseline_return },
          row: { key: top.candidate_key, ret: top.target_return } });
  const final = await stats(page);
  console.log("INFO  全程報價來源：" + JSON.stringify({ attempts: final.chain_attempts,
                                                     sources: final.chain_sources }));
  check("全程網路閘：沒有任何被擋的直連", final.blocked_connections === 0, final.blocked_targets);
  await ctx.close();
}

async function main() {
  if (!existsSync(join(ROOT, "dist/index.html"))) abort("找不到 dist/：先跑 npm run build");
  execFileSync("dropdb", [...pgArgs, "--if-exists", DB]);
  execFileSync("createdb", [...pgArgs, DB]);
  const tmp = mkdtempSync(join(tmpdir(), "oc-opp-live-verify-"));
  const cert = join(tmp, "cert.pem"), key = join(tmp, "key.pem");
  execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                           "-out", cert, "-days", "1", "-subj", "/CN=127.0.0.1"], { stdio: "ignore" });
  const server = startServer(["--dsn", DSN, "--port", String(PORT), "--cert", cert, "--key", key]);
  let browser;
  let aborted = false;
  try {
    await server.ready;
    browser = await chromium.launch({
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"],
    });
    await canary(browser);
    await flow(browser);
  } catch (e) {
    aborted = Boolean(e.abort);
    if (!e.abort) {
      console.error(e);
      console.error(server.log().slice(-3000));
    }
    check("流程沒有中途出錯", false, String(e.message ?? e).split("\n")[0]);
  } finally {
    await browser?.close();
    server.child.kill("SIGTERM");
    rmSync(tmp, { recursive: true, force: true });
  }
  const failed = checks.filter((r) => !r.ok);
  console.log(JSON.stringify({ checks: checks.length, passed: checks.length - failed.length,
                               failed: failed.length }, null, 2));
  process.exit(aborted ? 3 : failed.length ? 1 : 0);
}

await main();
