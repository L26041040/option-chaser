// V2-07（#409）：約 500 檔（S&P 500）「真實資料」本機驗收——Agent 可執行的部分。
//
// 和 `live402_acceptance.mjs` 同一套安全作法，換成 V2 的掃描股票範圍與 #405 定稿名稱：
//
//   起本機驗證站（`scripts/opportunity_live_verify_server.py`：`dist/` 前端＋同一個
//   FastAPI app；分析師資料＝真實 Yahoo `upgradeDowngradeHistory`；選擇權報價＝既有
//   預設路徑 Cboe → Yahoo 直連 → yfinance（有裝才用）；資料庫＝本機 Postgres，
//   DSN 寫死 127.0.0.1），用真 Chromium（`--no-proxy-server`＋金絲雀）。
//
// 分三段跑（`OC_409_PHASE`），同一個瀏覽器設定檔（`OUT/profile`）→ 同一個本機
// 身分；每段重啟驗證站（同一個資料庫）：
//
//   build    掃描股票範圍（S&P 500）經真實 cron 端點逐次續跑 → 最後一段由 SU 在
//            畫面按「繼續更新」→ 同日重跑不重抓 → 兩組門檻（設定頁）→ 冷卻後的重試
//            時段。
//   search   兩組門檻各搜尋一次選擇權（畫面按鈕）→ 三種排序前 5 → 存成劇本 2 列並
//            與詳細頁逐欄比對（每股／每口）。
//   persist  重新整理＋重啟後端（同一資料庫）→ 共識快取、劇本都在；手機／桌面
//            ⓘ（懸停／點按）、無橫向捲動、#405 定稿名稱、沒有舊名稱；沒有 fixture。
//
//   PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium SSL_CERT_FILE=/root/.ccr/ca-bundle.crt \
//     OC_409_DB=oc409 OC_409_OUT=/path/to/outdir OC_409_PHASE=build node scripts/live409_acceptance.mjs
//
// ⚠ 安全：瀏覽器不走 proxy、寫入前先過金絲雀、驗證站只連本機 Postgres、SU／SA 密碼與
// cron 授權值每次隨機產生（只活在這個行程與它啟動的驗證站裡），不印出、不寫檔。不截圖。
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, devices } from "@playwright/test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PG = { host: "127.0.0.1", port: "55432", user: "postgres" };
const DB = process.env.OC_409_DB ?? "oc409";
const DSN = `postgresql://${PG.user}@${PG.host}:${PG.port}/${DB}`;
const PORT = Number(process.env.OC_VERIFY_PORT ?? 8479);
const BASE = `https://127.0.0.1:${PORT}`;
const OUT = process.env.OC_409_OUT;
const PHASE = process.env.OC_409_PHASE ?? "build";
const RESUME = process.env.OC_409_RESUME === "1";   // build 中途接續（cron 段已在 build.log）
const SU_TAIL = Number(process.env.OC_409_SU_TAIL ?? 40);      // cron 跑到剩這麼多檔時交給 SU
const LOOSE = { pr: Number(process.env.OC_409_LOOSE_PR ?? 50), d: Number(process.env.OC_409_LOOSE_D ?? 20) };
const LOOSE_MAX_BATCHES = Number(process.env.OC_409_LOOSE_MAX_BATCHES ?? 1);
const PYTHON = process.env.OC_VERIFY_PYTHON
  ?? [join(ROOT, ".venv/bin/python"), "/home/user/option-chaser/.venv/bin/python"]
    .find((p) => existsSync(p)) ?? "python3";
const SLOW_SECONDS = 45;
const ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"];

const report = { phase: PHASE, started_tw: null, db: DB, checks: [], phases: {} };
const checks = report.checks;
function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok), detail: detail ?? null });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail === undefined ? "" : "  " + JSON.stringify(detail).slice(0, 600)}`);
  return Boolean(ok);
}
function abort(message) {
  console.error(`ABORT  ${message}`);
  throw Object.assign(new Error(message), { abort: true });
}
const tw = (d = new Date()) =>
  `${d.toLocaleString("sv-SE", { timeZone: "Asia/Taipei" }).slice(0, 19)} (台灣)`;
const twIso = (iso) => (iso ? tw(new Date(iso)) : null);
const info = (label, obj) => console.log(`INFO  ${label} ${JSON.stringify(obj).slice(0, 1500)}`);
const save = () => {
  if (OUT) writeFileSync(join(OUT, `live409_${PHASE}_raw.json`), JSON.stringify(report, null, 2));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const pgArgs = ["-h", PG.host, "-p", PG.port, "-U", PG.user];
const sql = (query) => execFileSync("psql", ["-X", "-qtA", ...pgArgs, "-d", DB, "-c", query],
                                    { encoding: "utf8" }).trim();
const sqlRows = (query) => sql(query).split("\n").filter(Boolean).map((l) => l.split("|"));

const secrets = {
  OC_VERIFY_SU_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_SA_PASSWORD: randomBytes(18).toString("base64url"),
  OC_VERIFY_CRON_SECRET: randomBytes(18).toString("base64url"),
  OC_VERIFY_NONCE: randomBytes(12).toString("hex"),
};

function startServer(args) {
  const env = { ...process.env, ...secrets, PYTHONPATH: ROOT };
  for (const k of ["DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL",
                   "DATABASE_URL_POOLED", "POSTGRES_URL_NON_POOLING", "CRON_SECRET",
                   "SUPERUSER_PASSWORD", "SUPERADMIN_PASSWORD"]) delete env[k];
  const child = spawn(PYTHON, [join(ROOT, "scripts/opportunity_live_verify_server.py"), ...args],
                      { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  const exited = new Promise((r) => child.on("exit", r));
  const ready = new Promise((resolveReady, reject) => {
    const onData = (chunk) => {
      log += chunk.toString();
      if (log.length > 400000) log = log.slice(-200000);
      if (log.includes("Uvicorn running on")) resolveReady();
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.on("exit", (code) => reject(new Error(`驗證站提早結束（${code}）：\n${log.slice(-2000)}`)));
    setTimeout(() => reject(new Error(`驗證站 60 秒內沒有起來：\n${log.slice(-2000)}`)), 60000);
  });
  return { child, ready, exited, log: () => log };
}

async function api(page, method, path, { body, headers } = {}) {
  return page.evaluate(async ([m, p, b, h]) => {
    const t0 = performance.now();
    const r = await fetch(p, { method: m,
      headers: { ...(b ? { "Content-Type": "application/json" } : {}), ...(h ?? {}) },
      body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json, ms: Math.round(performance.now() - t0) };
  }, [method, path, body, headers]);
}
const stats = async (page) => (await api(page, "GET", "/__verify/stats")).body;

async function canary(ctx, { write }) {
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
  const out = { at_tw: tw(), nonce_ok: true, label: s.label, health_storage: health.storage,
                health_commit: health.backend.commit, health_opportunity: health.opportunity ?? null };
  if (write) {
    const before = Number(sql("SELECT count(*) FROM scenarios"));
    const created = await api(page, "POST", "/api/scenarios", { body: {
      symbol: "ZZCANARY", target_price: 120, target_month: "2027-12",
      strategies: ["vertical-spread"] } });
    if (created.status !== 201 || Number(sql("SELECT count(*) FROM scenarios")) !== before + 1) {
      abort(`金絲雀失敗：試寫入沒有出現在本機資料庫（status ${created.status}）。`);
    }
    out.canary_scenario_id = created.body.id;
  }
  console.log(`OK    金絲雀：瀏覽器連到本次的本機驗證站（${s.label}）`);
  await page.close();
  return out;
}

// ---------- 小工具 ----------

async function login(page) {
  const role0 = (await api(page, "GET", "/api/auth/status")).body?.role;
  if (role0 === "superuser") return role0;
  await page.goto(`${BASE}/#/settings`);
  const input = page.locator("input[type=password]:visible").first();
  await input.waitFor();
  await input.fill(secrets.OC_VERIFY_SU_PASSWORD);
  const reloaded = page.waitForEvent("load");
  await page.locator("button:visible", { hasText: /^登入$/ }).first().click();
  await reloaded;
  // 開 app 會觸發既有的 Refresh Run（背景抓鏈），不等 networkidle。
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1500);
  return (await api(page, "GET", "/api/auth/status")).body?.role;
}

async function settingsSection(page) {
  await page.goto(`${BASE}/#/settings/opportunity`);
  const section = page.getByRole("region", { name: "機會搜尋" });
  const tab = page.getByRole("tab", { name: "機會搜尋" });
  await Promise.race([section.waitFor(), tab.waitFor()]);
  if (!(await section.isVisible()) && (await tab.isVisible())) await tab.click();
  await section.waitFor();
  return section;
}

/** 設定頁以 PR 輸入第一道門檻、分歧率上限輸入第二道；回傳存回的 API 值與 UI 生效耗時。 */
async function setThresholds(page, pr, dMax) {
  const section = await settingsSection(page);
  const sp = section.getByRole("radio", { name: /S&P 500 成分股/ });
  const spChecked = await sp.isChecked();
  if (!spChecked) await sp.check();
  await section.locator("#opp-percentile_max").fill(String(pr));
  await section.locator("#opp-dispersion_max").fill(String(dMax));
  const t0 = Date.now();
  await section.getByRole("button", { name: "儲存" }).click();
  await section.getByRole("status").filter({ hasText: "已儲存" }).waitFor();
  const savedMs = Date.now() - t0;
  const got = (await api(page, "GET", "/api/settings")).body.opportunity_search;
  return { ...got, sp500_was_checked: spChecked, save_ms: savedMs };
}

async function openOpportunity(page) {
  // 已經在 #/opportunity 時 goto 同一個 hash 不會重新載入（畫面會停在舊狀態），一律 reload。
  await page.goto(`${BASE}/#/opportunity`);
  await page.reload();
  const region = page.getByRole("region", { name: "符合條件的股票" });
  await region.waitFor({ timeout: 30000 });
  return region;
}

/** 畫面上的「符合條件的股票」清單＋每檔顯示的 PR、股價、目標漲跌幅文字。 */
async function uiSelected(page) {
  const t0 = Date.now();
  const region = await openOpportunity(page);
  await page.waitForFunction(() => /符合條件的股票（\d+ 檔）/.test(
    document.querySelector('[aria-label="符合條件的股票"] h2')?.textContent ?? ""), null, { timeout: 30000 });
  const ms = Date.now() - t0;
  const heading = await region.locator("h2").first().innerText();
  const items = await region.locator("ul.opp-list > li.opp-item").evaluateAll((xs) => xs.map((x) => ({
    symbol: x.getAttribute("aria-label"), text: x.querySelector(".opp-facts")?.textContent ?? "" })));
  const weak = await page.locator('[aria-label="不符合條件"] ul.opp-list > li.opp-item')
    .evaluateAll((xs) => xs.map((x) => ({ symbol: x.getAttribute("aria-label"),
                                         text: x.querySelector(".opp-reasons")?.textContent ?? "" })));
  return { heading, ms_to_list: ms, symbols: items.map((i) => i.symbol), items, weak };
}

const prDisplay = (p) => Math.floor(100 - p * 100 + 1e-9);

function gateSummary(consensus) {
  const items = consensus.items;
  const byStatus = {};
  for (const i of items) byStatus[i.status] = (byStatus[i.status] ?? 0) + 1;
  const ok = items.filter((i) => i.status === "ok");
  const selected = items.filter((i) => i.gate.selected).map((i) => i.symbol);
  const prThr = 100 - consensus.thresholds.percentile_max;
  // 資料品質不是 ok 的（stale／insufficient_*）本來就因資料狀態不入選，畫面列在「資料不足」、
  // 不顯示通過；只檢查 status=ok 的。非 ok 但有百分位的另外記數。
  const nonOkWithHighPr = items.filter((i) => i.status !== "ok" && i.percentile !== null
    && prDisplay(i.percentile) >= prThr).length;
  const displayPassButFail = ok.filter((i) => i.percentile !== null
    && prDisplay(i.percentile) >= prThr && !i.gate.first)
    .map((i) => ({ symbol: i.symbol, percentile: i.percentile, pr: prDisplay(i.percentile) }));
  const borderline = ok.filter((i) => i.percentile !== null
    && Math.abs((100 - i.percentile * 100) - prThr) < 1)
    .map((i) => ({ symbol: i.symbol, raw_pr: 100 - i.percentile * 100, shown: prDisplay(i.percentile),
                   first: i.gate.first }));
  return {
    thresholds: consensus.thresholds, pr_threshold: prThr,
    selected_count: selected.length, selected,
    status_counts: byStatus,
    status_ok: ok.length,
    not_eligible_count: ok.length - selected.length,
    failed_first_only: ok.filter((i) => !i.gate.first && i.gate.second).length,
    failed_second_only: ok.filter((i) => i.gate.first && !i.gate.second).length,
    failed_both: ok.filter((i) => !i.gate.first && !i.gate.second).length,
    display_pass_but_backend_fail: displayPassButFail,
    non_ok_status_with_shown_pr_at_or_above_threshold: nonOkWithHighPr,
    borderline_within_1pr: borderline,
    non_ok_with_gate_selected: items.filter((i) => i.status !== "ok" && i.gate.selected).map((i) => i.symbol),
  };
}

const legText = (legs) => legs.map((l) =>
  `${l.side === "buy" ? "+" : "-"}${l.quantity}x${l.strike}${/^c/i.test(l.option_type) ? "C" : "P"}`).join(" ");
const rowView = (r) => ({
  symbol: r.symbol, family: r.family, subtype: r.subtype, expiry: r.expiry,
  legs: legText(r.legs),
  cost_per_share: r.entry_cost, cost_per_contract: Math.round(r.entry_cost * 100 * 100) / 100,
  max_loss_per_share: r.max_loss_per_contract / 100, max_loss_per_contract: r.max_loss_per_contract,
  strategy_return_at_target: r.target_return, breakeven: r.breakeven,
  stock_price: r.consensus?.price ?? null, stock_price_date: r.consensus?.price_date ?? null,
  stock_target_upside_pct: r.consensus?.target_upside_pct ?? null,
  stock_target_upside_reason: r.consensus?.target_upside_reason ?? null,
  mean_target: r.scenario.target_price, target_month: r.target_month,
  candidate_key: r.candidate_key });

function countBy(xs, f) {
  const o = {};
  for (const x of xs) { const k = f(x); o[k] = (o[k] ?? 0) + 1; }
  return o;
}
const deltaMap = (a = {}, b = {}) => Object.fromEntries(
  [...new Set([...Object.keys(a), ...Object.keys(b)])].map((k) => [k, (b[k] ?? 0) - (a[k] ?? 0)])
    .filter(([, v]) => v !== 0));

// ---------- build ----------

async function cronCall(page) {
  const s0 = await stats(page);
  const started = new Date();
  const r = await api(page, "GET", "/api/cron/consensus-refresh",
                      { headers: { Authorization: `Bearer ${secrets.OC_VERIFY_CRON_SECRET}` } });
  const s1 = await stats(page);
  const b = r.body ?? {};
  return { started_tw: tw(started), http_status: r.status, seconds: Math.round(r.ms / 100) / 10,
           processed: b.processed, succeeded: b.succeeded, failed: b.failed,
           processed_symbols: b.processed_symbols, remaining: b.remaining?.length,
           skipped: b.skipped?.length, stopped_reason: b.stopped_reason ?? null, message: b.message ?? null,
           rate_limited_until: b.rate_limited_until ?? null,
           upstream_calls_today: b.upstream_calls_today, daily_cap: b.daily_cap,
           analyst_fetches: s1.analyst_fetches - s0.analyst_fetches,
           analyst_http_requests: s1.analyst_http_requests - s0.analyst_http_requests,
           yahoo_http_status: deltaMap(s0.yahoo_http_status, s1.yahoo_http_status) };
}

async function statusFacts(page) {
  const panel = page.getByRole("region", { name: "分析師資料" });
  const facts = panel.getByRole("list", { name: "資料狀態" });
  await facts.getByRole("listitem", { name: "已建立" }).waitFor({ timeout: 30000 });
  const out = {};
  for (const name of ["掃描股票範圍", "資料來源", "資料日期", "已建立", "符合條件", "今日更新",
                      "今日上游呼叫", "排程"]) {
    const li = facts.getByRole("listitem", { name, exact: true });
    out[name] = (await li.count()) ? (await li.innerText()).replace(/\s+/g, " ") : null;
  }
  return out;
}

async function phaseBuild(page) {
  const phase = { started_tw: tw() };
  await openOpportunity(page);
  phase.facts_before = await statusFacts(page);
  const status0 = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  phase.status_before = { today: status0.today, progress: status0.progress, cron: status0.cron,
                          policy: status0.policy, daily_cap: status0.daily_cap };
  const s0 = await stats(page);
  const t0 = Date.now();
  // 1. cron：像 Vercel Cron 一樣一次一次打（每次 45 秒預算）。
  const calls = [];
  let lockDemo = null;
  phase.resumed = RESUME;
  for (let n = 1; n <= (RESUME ? 0 : 40); n++) {
    let c;
    if (n === 2) {
      // 排程時段浮動可能重疊：同時打兩次，全站單一執行鎖讓第二次立刻回 another_run_active。
      const first = cronCall(page);
      await sleep(1500);
      const second = await cronCall(page);
      c = await first;
      lockDemo = { first: { processed: c.processed, stopped_reason: c.stopped_reason, seconds: c.seconds },
                   overlapping: second };
    } else {
      c = await cronCall(page);
    }
    c.n = n;
    calls.push(c);
    phase.cron_calls = calls;
    report.phases.b1_build_partial = phase;
    console.log(`cron #${n} ${c.started_tw} ${c.seconds}s processed=${c.processed} ok=${c.succeeded} fail=${c.failed} remaining=${c.remaining} http=${c.analyst_http_requests} status=${JSON.stringify(c.yahoo_http_status)} stopped=${c.stopped_reason}`);
    save();
    if (c.stopped_reason === "rate_limited") {
      phase.rate_limited = { at_tw: tw(), until: c.rate_limited_until, message: c.message };
      const waitMs = Math.max(0, Date.parse(c.rate_limited_until) - Date.now()) + 5000;
      if (waitMs > 40 * 60000) { phase.rate_limited.gave_up = true; break; }
      console.log(`429：來源暫停到 ${c.rate_limited_until}，等待 ${Math.round(waitMs / 1000)}s（不硬打）`);
      await sleep(waitMs);
      continue;
    }
    if (c.stopped_reason && c.stopped_reason !== "another_run_active") break;
    if (c.remaining <= SU_TAIL || c.processed === 0) break;
  }
  phase.cron_calls = calls;
  phase.run_lock_demo = lockDemo;
  phase.cron_wall_seconds = Math.round((Date.now() - t0) / 100) / 10;

  // 2. SU 在畫面按「繼續更新」（前端依 remaining 自動續跑，每次後端一批 10 檔）。
  await openOpportunity(page);
  const panel = page.getByRole("region", { name: "分析師資料" });
  phase.facts_before_su = await statusFacts(page);
  const btn = panel.getByRole("button", { name: /^(繼續更新|開始建立|更新分析師資料)$/ });
  await btn.waitFor({ timeout: 30000 });
  await page.waitForFunction(() => !/載入中/.test(document.querySelector('[aria-label="分析師資料"]')?.textContent ?? ""), null, { timeout: 30000 });
  phase.su_button_label = await btn.innerText();
  phase.su_phase_text = await panel.locator(".opp-phase").innerText();
  check("資料建立中時，SU 的按鈕名稱是「繼續更新」", phase.su_button_label === "繼續更新",
        { label: phase.su_button_label, phase: phase.su_phase_text });
  const updates = [];
  const pending = new Map();
  const onReq = (rq) => { if (rq.url().endsWith("/api/opportunity/consensus/update")) pending.set(rq, Date.now()); };
  const onResp = async (r) => {
    if (!r.url().endsWith("/api/opportunity/consensus/update")) return;
    const t = pending.get(r.request());
    let body = null;
    try { body = await r.json(); } catch { /* */ }
    updates.push({ at_tw: tw(), status: r.status(), seconds: t ? Math.round((Date.now() - t) / 100) / 10 : null,
                   processed: body?.processed, succeeded: body?.succeeded, failed: body?.failed,
                   processed_symbols: body?.processed_symbols,
                   remaining: body?.remaining?.length, stopped_reason: body?.stopped_reason,
                   upstream_calls_today: body?.upstream_calls_today, progress: body?.progress });
  };
  page.on("request", onReq);
  page.on("response", onResp);
  const sSu0 = await stats(page);
  const tSu = Date.now();
  phase.su_started_tw = tw();
  await btn.click();
  // SU 這批正在跑（持有全站單一執行鎖）時，排程時段剛好觸發：應該立刻回 another_run_active、不打上游。
  await sleep(2500);
  phase.run_lock_demo_during_su = await cronCall(page);
  await page.getByText(/更新完成|已停止/).first().waitFor({ timeout: 1800000 });
  phase.su_wall_seconds = Math.round((Date.now() - tSu) / 100) / 10;
  phase.su_finished_tw = tw();
  phase.su_end_text = await page.getByText(/更新完成|已停止/).first().innerText();
  await page.waitForTimeout(1500);
  page.off("request", onReq);
  page.off("response", onResp);
  const sSu1 = await stats(page);
  phase.su_updates = updates;
  phase.su_analyst_fetches = sSu1.analyst_fetches - sSu0.analyst_fetches;
  phase.su_analyst_http_requests = sSu1.analyst_http_requests - sSu0.analyst_http_requests;
  phase.finished_tw = tw();
  phase.total_wall_seconds = Math.round((Date.now() - t0) / 100) / 10;
  const s1 = await stats(page);
  phase.totals = {
    analyst_fetches: s1.analyst_fetches - s0.analyst_fetches,
    analyst_http_requests: s1.analyst_http_requests - s0.analyst_http_requests,
    yahoo_http_by_kind: deltaMap(s0.yahoo_http, s1.yahoo_http),
    yahoo_http_status: deltaMap(s0.yahoo_http_status, s1.yahoo_http_status),
    http_429: (s1.yahoo_http_status["429"] ?? 0) - (s0.yahoo_http_status["429"] ?? 0),
    blocked_connections: s1.blocked_connections,
  };
  phase.analyst_log = s1.analyst_log;
  return phase;
}

async function consensusSnapshot(page) {
  const status = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
  const items = consensus.items.map((i) => ({
    symbol: i.symbol, status: i.status, reasons: i.reasons, n_analysts: i.n_analysts,
    mean: i.mean, dispersion: i.dispersion, percentile: i.percentile, history_points: i.history_points,
    as_of: i.as_of, refresh_error: i.refresh_error, target_month: i.target_month,
    price: i.price, price_date: i.price_date, price_at: i.price_at, price_kind: i.price_kind,
    target_upside_pct: i.target_upside_pct, target_upside_reason: i.target_upside_reason,
    gate: i.gate }));
  const failed = status.symbols.filter((s) => s.error);
  return {
    at_tw: tw(), today: status.today, data_as_of: status.data_as_of, progress: status.progress,
    upstream_calls_today: status.upstream_calls_today, daily_cap: status.daily_cap,
    rate_limited_until: status.rate_limited_until ?? null, cron: status.cron, policy: status.policy,
    source: consensus.source, universe: consensus.universe, rules: consensus.rules,
    thresholds: consensus.thresholds,
    status_counts: countBy(items, (i) => i.status),
    status_reasons: Object.fromEntries(Object.entries(countBy(items, (i) => i.status))
      .filter(([k]) => k !== "ok").map(([k]) => [k, items.filter((i) => i.status === k)
        .map((i) => ({ symbol: i.symbol, reasons: i.reasons, refresh_error: i.refresh_error }))])),
    refresh_failures: failed.map((s) => ({ symbol: s.symbol, error: s.error, state: s.state,
      retries_today: s.retries_today, next_retry_at: s.next_retry_at })),
    refresh_state_counts: countBy(status.symbols, (s) => s.state),
    retries_today: status.symbols.reduce((a, s) => a + (s.retries_today ?? 0), 0),
    upside_reason_counts: countBy(items, (i) => i.target_upside_reason ?? (i.target_upside_pct === null ? "(null)" : "has_value")),
    price_kind_counts: countBy(items, (i) => i.price_kind ?? "(none)"),
    price_date_counts: countBy(items, (i) => i.price_date ?? "(none)"),
    items,
  };
}

async function phaseSameDayRerun(page) {
  const out = {};
  const st0 = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  const doneBefore = new Set(st0.symbols.filter((s) => s.state === "done").map((s) => s.symbol));
  out.done_before = doneBefore.size;
  out.state_counts_before = countBy(st0.symbols, (s) => s.state);
  out.cron = await cronCall(page);
  await openOpportunity(page);
  const panel = page.getByRole("region", { name: "分析師資料" });
  const btn = panel.getByRole("button", { name: /更新分析師資料|繼續更新/ });
  out.button_label = await btn.first().innerText();
  const s0 = await stats(page);
  const resp = page.waitForResponse((r) => r.url().endsWith("/api/opportunity/consensus/update"));
  await btn.first().click();
  const r = await resp;
  const body = await r.json().catch(() => null);
  await page.getByText(/更新完成|已停止/).first().waitFor({ timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1000);
  const s1 = await stats(page);
  out.su = { status: r.status(), processed: body?.processed, processed_symbols: body?.processed_symbols,
             skipped: body?.skipped?.length,
             stopped_reason: body?.stopped_reason, remaining: body?.remaining?.length,
             analyst_fetches: s1.analyst_fetches - s0.analyst_fetches,
             analyst_http_requests: s1.analyst_http_requests - s0.analyst_http_requests };
  out.refetched_already_succeeded = [...(out.cron.processed_symbols ?? []), ...(out.su.processed_symbols ?? [])]
    .filter((s) => doneBefore.has(s));
  check(`同一交易日再跑（cron＋SU 按鈕）：今天已成功的 ${doneBefore.size} 檔一檔都不重抓`,
        out.refetched_already_succeeded.length === 0
        && out.cron.analyst_fetches === (out.cron.processed ?? 0) && out.su.analyst_fetches === (out.su.processed ?? 0),
        { cron: [out.cron.processed, out.cron.analyst_http_requests], su: [out.su.processed, out.su.analyst_http_requests] });
  return out;
}

async function phaseSelection(page, settings) {
  const out = [];
  const s0 = await stats(page);
  for (const [pr, d] of settings) {
    const saved = await setThresholds(page, pr, d);
    const t0 = Date.now();
    const ui = await uiSelected(page);
    const msAfterSave = Date.now() - t0;
    const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
    const g = gateSummary(consensus);
    const same = JSON.stringify(ui.symbols) === JSON.stringify(g.selected);
    // 畫面上的 PR：符合條件的每一檔顯示 ≥ 門檻；不符合條件、因第一道沒過的每一檔顯示 < 門檻。
    const shownPr = (t) => { const m = /PR(\d+)/.exec(t); return m ? Number(m[1]) : null; };
    const selPr = ui.items.map((i) => ({ symbol: i.symbol, shown: shownPr(i.text) }));
    const weakFirst = ui.weak.filter((w) => /未達門檻/.test(w.text))
      .map((w) => ({ symbol: w.symbol, shown: shownPr(w.text) }));
    const selBad = selPr.filter((x) => x.shown === null || x.shown < pr);
    const weakBad = weakFirst.filter((x) => x.shown !== null && x.shown >= pr);
    check(`門檻 PR≥${pr}／分歧率≤${d}%（設定頁）：存回 percentile_max=${100 - pr}；畫面清單＝API（${g.selected_count} 檔）`,
          same && saved.percentile_max === 100 - pr && saved.dispersion_max === d && saved.universe_id === "sp500",
          { ui: ui.symbols.length, api: g.selected_count });
    check(`門檻 PR≥${pr}：畫面顯示 PR 沒有「顯示通過、實際沒過」（API ${g.display_pass_but_backend_fail.length}、符合條件清單 ${selBad.length}、不符合條件清單 ${weakBad.length}）`,
          g.display_pass_but_backend_fail.length === 0 && selBad.length === 0 && weakBad.length === 0,
          { selBad, weakBad: weakBad.slice(0, 5) });
    out.push({ pr, dispersion_max: d, saved, changed_at_tw: tw(), ui_heading: ui.heading,
               ui_ms_after_save: msAfterSave, ui_symbols: ui.symbols, ui_matches_api: same,
               ui_selected_pr: selPr, ui_weak_first_gate_pr: weakFirst,
               ui_weak_count: ui.weak.length, ...g });
  }
  const s1 = await stats(page);
  const changed = new Set(out.map((g) => g.selected.join(","))).size > 1;
  check("改門檻後符合條件清單立即改變，且不打上游（分析師抓取次數不變）",
        changed && s1.analyst_fetches === s0.analyst_fetches,
        { analyst_fetches_delta: s1.analyst_fetches - s0.analyst_fetches, counts: out.map((o) => o.selected_count) });
  return out;
}

async function phaseRetrySlot(page, snap) {
  const cooling = snap.refresh_failures.filter((f) => f.next_retry_at);
  if (!cooling.length) return { skipped: "no failed symbols waiting for retry" };
  const at = Math.max(...cooling.map((f) => Date.parse(f.next_retry_at)));
  const nyMidnight = (() => {   // 下一個紐約午夜（UTC）
    const now = new Date();
    for (let h = 0; h <= 30; h++) {
      const t = new Date(Math.ceil(now.getTime() / 3600000) * 3600000 + h * 3600000);
      const hh = Number(t.toLocaleString("en-US", { timeZone: "America/New_York", hour: "2-digit", hour12: false }));
      if (hh === 0 || hh === 24) return t.getTime();
    }
    return Infinity;
  })();
  const waitMs = Math.max(0, at - Date.now()) + 5000;
  if (Date.now() + waitMs + 120000 > nyMidnight) {
    return { skipped: "retry time would cross New York midnight (new trading day)", next_retry_at: new Date(at).toISOString() };
  }
  console.log(`等冷卻：${Math.round(waitMs / 1000)}s 後打一次 cron（重試時段）`);
  await sleep(waitMs);
  const c = await cronCall(page);
  return { waited_seconds: Math.round(waitMs / 1000), cooling_before: cooling, cron: c };
}

// ---------- search ----------

const guard = { stopped_for_429: false };
async function runSearchRound(page, buttonLocator, selectedCount) {
  const t0 = Date.now();
  const base429 = (await stats(page)).yahoo_http_status["429"] ?? 0;
  await buttonLocator.click();
  // 上游一回 429 就按「停止」，不硬打（Yahoo 選擇權鏈沒有全站暫停機制，這裡替它踩煞車）。
  let done = false;
  const watcher = (async () => {
    while (!done) {
      await sleep(10000);
      if (done) break;
      const n = (await stats(page).catch(() => null))?.yahoo_http_status?.["429"] ?? 0;
      if (n > base429) {
        guard.stopped_for_429 = true;
        console.log(`429 出現（${n - base429} 次）：按停止`);
        await page.getByRole("button", { name: "停止" }).click().catch(() => {});
        break;
      }
    }
  })();
  await page.waitForFunction(() => /已搜尋 (\d+) \/ \1 檔/.test(document.body.innerText)
                             || /已停止|繼續搜尋剩下/.test(document.body.innerText), null,
                             { timeout: 120000 * Math.max(1, selectedCount) });
  done = true;
  await watcher;
  await page.getByRole("button", { name: "搜尋選擇權" }).and(page.locator(":enabled"))
    .waitFor({ timeout: 300000 });
  await page.waitForTimeout(800);
  return Date.now() - t0;
}

async function phaseSearch(page, label, selectedCount, maxBatches) {
  const phase = { label, started_tw: tw() };
  await openOpportunity(page);
  const responses = [];
  const pending = new Map();
  const onReq = (rq) => { if (rq.url().endsWith("/api/opportunity/search")) pending.set(rq, { t: Date.now(), body: rq.postData() }); };
  const onResp = async (r) => {
    if (!r.url().endsWith("/api/opportunity/search")) return;
    const p = pending.get(r.request());
    let body = null;
    try { body = await r.json(); } catch { /* */ }
    responses.push({ status: r.status(), ms: p ? Date.now() - p.t : null,
                     request: p?.body ?? null, endTime: Date.now(), body });
  };
  page.on("request", onReq);
  page.on("response", onResp);
  const s0 = await stats(page);
  let batches = 0;
  phase.round_ms = [];
  phase.round_ms.push(await runSearchRound(page, page.getByRole("button", { name: "搜尋選擇權" }), Math.min(selectedCount, 50)));
  batches++;
  for (;;) {
    const more = page.getByRole("button", { name: /^搜尋未搜尋的 \d+ 檔$/ });
    if (!(await more.count())) break;
    phase.deferred_left = Number(/\d+/.exec(await more.innerText())[0]);
    if (batches >= maxBatches || guard.stopped_for_429) break;
    phase.round_ms.push(await runSearchRound(page, more, Math.min(phase.deferred_left, 50)));
    batches++;
    phase.deferred_left = 0;
  }
  phase.batches = batches;
  phase.stopped_for_429 = guard.stopped_for_429;
  phase.wall_seconds = Math.round(phase.round_ms.reduce((a, b) => a + b, 0) / 100) / 10;
  phase.finished_tw = tw();
  page.off("request", onReq);
  page.off("response", onResp);
  const s1 = await stats(page);
  const chainLog = s1.chain_log.slice(s0.chain_log.length);
  phase.chain_attempt_counts = countBy(chainLog, (c) => `${c.attempt}:${c.ok ? "ok" : "fail"}`);
  phase.chain_source_counts = countBy(chainLog.filter((c) => c.ok), (c) => c.source);
  phase.chain_errors = countBy(chainLog.filter((c) => !c.ok), (c) => `${c.attempt}: ${c.error.replace(/（[A-Z.\-]+）/g, "（SYM）").slice(0, 140)}`);
  phase.yahoo_http = deltaMap(s0.yahoo_http, s1.yahoo_http);
  phase.yahoo_http_status = deltaMap(s0.yahoo_http_status, s1.yahoo_http_status);
  const rows = [], failures = [], incomplete = [], perSymbol = [];
  for (const r of responses) {
    if (r.status !== 200) {
      failures.push({ symbol: "*", reason: `http_${r.status}`, message: JSON.stringify(r.body).slice(0, 300) });
      continue;
    }
    const b = r.body;
    rows.push(...b.rows);
    failures.push(...b.failures);
    incomplete.push(...(b.incomplete ?? []));
    for (const sym of b.processed) {
      const mine = chainLog.filter((c) => c.symbol === sym);
      const ok = mine.find((c) => c.ok);
      const fam = b.rows.filter((x) => x.symbol === sym).map((x) => x.family).sort();
      perSymbol.push({ symbol: sym, request_seconds: Math.round(r.ms / 100) / 10,
                       over_45s: r.ms / 1000 > SLOW_SECONDS, processed_in_request: b.processed.length,
                       fetch_seconds: Math.round(mine.reduce((a, c) => a + c.seconds, 0) * 100) / 100,
                       attempts: mine.map((c) => `${c.attempt}:${c.ok ? "ok" : "fail"}`),
                       source: ok?.source ?? null, contracts: ok?.contracts ?? null,
                       expiries: ok?.expiries ?? null, chain_spot: ok?.spot ?? null,
                       families: fam, family_count: fam.length,
                       failure: b.failures.find((f) => f.symbol === sym) ?? null,
                       incomplete: (b.incomplete ?? []).find((f) => f.symbol === sym) ?? null });
    }
    if (b.stopped_reason) failures.push({ symbol: "*", reason: b.stopped_reason, message: b.message });
  }
  phase.request_count = responses.length;
  phase.sort_options = responses.find((r) => r.body?.sort_options)?.body.sort_options ?? [];
  phase.per_symbol = perSymbol;
  phase.searched = perSymbol.length;
  phase.searchable = [...new Set(rows.map((r) => r.symbol))];
  phase.searchable_count = phase.searchable.length;
  phase.zero_candidate = perSymbol.filter((p) => !p.failure && p.family_count === 0).map((p) => p.symbol);
  phase.failures = failures;
  phase.failure_reason_counts = countBy(failures, (f) => f.reason);
  phase.failure_stage_counts = countBy(failures, (f) => `${f.reason}/${f.stage ?? "-"}`);
  phase.incomplete = incomplete.map((i) => ({ symbol: i.symbol, families: i.families, message: i.message }));
  phase.family_count_hist = countBy(perSymbol, (p) => p.family_count);
  const secs = perSymbol.map((p) => p.request_seconds).sort((a, b) => a - b);
  phase.per_stock_seconds = secs.length ? { min: secs[0], median: secs[Math.floor(secs.length / 2)],
    p90: secs[Math.floor(secs.length * 0.9)], max: secs[secs.length - 1],
    mean: Math.round(secs.reduce((a, b) => a + b, 0) / secs.length * 10) / 10 } : null;
  phase.slow_over_45s = perSymbol.filter((p) => p.over_45s).map((p) => ({ symbol: p.symbol, seconds: p.request_seconds, contracts: p.contracts, expiries: p.expiries }));
  phase.slowest5 = [...perSymbol].sort((a, b) => b.request_seconds - a.request_seconds).slice(0, 5)
    .map((p) => ({ symbol: p.symbol, seconds: p.request_seconds, contracts: p.contracts, expiries: p.expiries, source: p.source }));
  phase.row_count = rows.length;
  phase.rows = rows.map(rowView);
  // 搜尋列的股價是共識更新時存下的，不是這次搜尋抓到的 chain spot。
  const spotDiff = perSymbol.filter((p) => p.chain_spot).map((p) => {
    const r = rows.find((x) => x.symbol === p.symbol);
    return r ? { symbol: p.symbol, row_price: r.consensus?.price, row_price_date: r.consensus?.price_date,
                 chain_spot: p.chain_spot } : null;
  }).filter(Boolean);
  phase.row_price_vs_chain_spot = { compared: spotDiff.length,
    different: spotDiff.filter((x) => x.row_price !== x.chain_spot).length, sample: spotDiff.slice(0, 10) };

  // 排序：畫面下拉選單（後端 sort_options）各取前 5，欄位用 #405／#408 定稿名稱。
  const results = page.getByRole("region", { name: "搜尋結果" });
  phase.ui_row_count = await results.locator("tbody tr[data-family]").count();
  check(`${label}：搜尋結果表列數＝API 列數（${rows.length}）`, phase.ui_row_count === rows.length);
  const select = results.locator("select");
  phase.rankings = {};
  const keyOf = { return: (r) => -r.target_return, cost: (r) => r.entry_cost,
                  max_loss: (r) => r.max_loss_per_contract };
  for (const opt of phase.sort_options) {
    await select.selectOption(opt.id);
    await page.waitForTimeout(400);
    const uiTop = await results.locator("tbody tr[data-family]").evaluateAll((trs) => trs.slice(0, 5).map((tr) => {
      const cell = (l) => tr.querySelector(`td[data-label="${l}"]`)?.innerText?.replace(/\s+/g, " ").trim() ?? null;
      return { stock: cell("標的"), strategy: cell("策略"), legs: cell("履約價"),
               cost: cell("成本（每股／每口）"), max_loss: cell("最大損失（每股／每口）"),
               strategy_return: cell("股價達標時的策略報酬"), family: tr.getAttribute("data-family") };
    }));
    const apiTop = [...rows].sort((a, b) => (keyOf[opt.id](a) - keyOf[opt.id](b))
      || (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0)
      || (a.family < b.family ? -1 : a.family > b.family ? 1 : 0)).slice(0, 5).map(rowView);
    const match = uiTop.every((u, i) => u.stock?.startsWith(apiTop[i]?.symbol) && u.family === apiTop[i]?.family);
    check(`${label}：排序「${opt.label}」畫面前 5＝依同一欄位排序的 API 列`, match && uiTop.length === Math.min(5, rows.length),
          uiTop.map((u) => `${u.stock?.split(" ")[0]}/${u.family}`));
    phase.rankings[opt.id] = { label: opt.label, ui_top5: uiTop, top5: apiTop, ui_matches: match };
  }
  await select.selectOption("return");
  info(`搜尋 ${label}`, { searched: phase.searched, searchable: phase.searchable_count,
                         failures: phase.failure_reason_counts, sources: phase.chain_source_counts,
                         slow: phase.slow_over_45s.length });
  phase._rows_full = rows;
  return phase;
}

async function waitAnalyzed(page, id) {
  for (let i = 0; i < 120; i++) {
    const d = (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
    if (d?.latest_result && d?.representative_candidate) return d;
    await page.waitForTimeout(1500);
  }
  return (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
}

async function saveRowFromUi(page, row) {
  const results = page.getByRole("region", { name: "搜尋結果" });
  const tr = results.locator(`tbody tr[data-family="${row.family}"]`)
    .filter({ has: page.locator("td.opp-symbol", { hasText: new RegExp(`^${row.symbol.replace(".", "\\.")}\\b`) }) });
  const before = Number(sql("SELECT count(*) FROM scenarios"));
  const rowCells = await tr.first().evaluate((el) => Object.fromEntries([...el.querySelectorAll("td[data-label]")]
    .map((td) => [td.getAttribute("data-label"), td.innerText.replace(/\s+/g, " ").trim()])));
  await tr.first().getByRole("button", { name: "存成劇本" }).click();
  await page.waitForURL(/#\/s\/[^/]+$/, { timeout: 120000 });
  const id = decodeURIComponent(page.url().split("#/s/")[1]);
  const detail = await waitAnalyzed(page, id);
  await page.waitForTimeout(2500);
  const text = (await page.locator("body").innerText()).replace(/\s+/g, " ");
  return { id, saved_tw: tw(), db_scenarios_delta: Number(sql("SELECT count(*) FROM scenarios")) - before,
           result_row_cells: rowCells, detail_text: text, detail };
}

function championOf(detail) {
  const rc = detail.representative_candidate;
  const pool = detail.latest_result?.candidate_pool ?? {};
  return { rc, full: rc ? pool[rc.candidate_key] : null };
}

const money = (x) => `$${Number(x).toFixed(2)}`;
const moneyComma = (x) => `$${Number(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function compareSaved(row, saved) {
  const c = championOf(saved.detail);
  const full = c.full ?? {};
  const fields = {
    candidate_key: [row.candidate_key, c.rc?.candidate_key],
    expiry: [row.expiry, c.rc?.expiry],
    legs: [legText(row.legs), c.rc ? legText(c.rc.legs) : null],
    strategy_return_at_target: [row.target_return, c.rc?.baseline_return],
    cost_per_share: [row.entry_cost, full.natural_cost],
    cost_per_contract: [Math.round(row.entry_cost * 10000) / 100, full.natural_cost != null ? Math.round(full.natural_cost * 10000) / 100 : null],
    max_loss_per_contract: [row.max_loss_per_contract, full.max_loss_per_contract],
    max_loss_per_share: [row.max_loss_per_contract / 100, full.max_loss_per_contract != null ? full.max_loss_per_contract / 100 : null],
    breakeven: [row.breakeven, full.breakeven],
    target_price: [row.scenario.target_price, saved.detail.target_price],
    target_month: [row.target_month, saved.detail.target_month],
    symbol: [row.symbol, saved.detail.symbol],
  };
  const mismatches = Object.entries(fields).filter(([, [a, b]]) =>
    !(a === b || (typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 1e-6)))
    .map(([k, [a, b]]) => ({ field: k, result_row: a, scenario_detail: b }));
  // 詳細頁畫面上看得到同一組數字（每股成本、每口成本、每口最大損失、報酬）。
  const t = saved.detail_text;
  const pct = `${(row.target_return * 100).toFixed(1)}%`;
  const ui = {
    symbol: t.includes(row.symbol),
    strategy_return: t.includes(pct),
    cost_per_share: t.includes(money(row.entry_cost)),
    cost_per_contract: t.includes(moneyComma(row.entry_cost * 100)) || t.includes(money(row.entry_cost * 100)),
    max_loss_per_contract: t.includes(moneyComma(row.max_loss_per_contract)) || t.includes(money(row.max_loss_per_contract)),
  };
  // 劇本的冠軍是跨家族報酬最高的那組；結果列若不是該檔報酬最高的家族，冠軍會不同。
  // 另外比對劇本候選池裡「同一個 candidate_key」的數字（資料層一致性）。
  const same = (saved.detail.latest_result?.candidate_pool ?? {})[row.candidate_key] ?? null;
  const sameKey = same ? {
    in_saved_pool: true,
    cost_per_share: [row.entry_cost, same.natural_cost],
    max_loss_per_contract: [row.max_loss_per_contract, same.max_loss_per_contract],
    breakeven: [row.breakeven, same.breakeven],
  } : { in_saved_pool: false };
  const champion_is_row = c.rc?.candidate_key === row.candidate_key;
  return { fields, mismatches, detail_page_text_contains: ui, champion_is_row, same_key_in_saved_pool: sameKey };
}


// ---------- resave（6de8f02 之後：存成劇本只帶該列家族） ----------

const RESAVE_SYMBOLS = (process.env.OC_409_RESAVE_SYMBOLS ?? "DVN,GOOG,JPM,BAC").split(",");

async function setCustomUniverse(page, symbols, pr, dMax) {
  const section = await settingsSection(page);
  await section.getByRole("radio", { name: /自訂清單/ }).check();
  await section.locator("#opp-custom-symbols").fill(symbols.join(", "));
  await section.locator("#opp-percentile_max").fill(String(pr));
  await section.locator("#opp-dispersion_max").fill(String(dMax));
  await section.getByRole("button", { name: "儲存" }).click();
  await section.getByRole("status").filter({ hasText: "已儲存" }).waitFor();
  return (await api(page, "GET", "/api/settings")).body.opportunity_search;
}

/** 畫面按「搜尋選擇權」跑完一輪，回傳 API 列（攔截回應）。 */
async function uiSearchRows(page) {
  await openOpportunity(page);
  const rows = [];
  const onResp = async (r) => {
    if (!r.url().endsWith("/api/opportunity/search")) return;
    try { rows.push(...(await r.json()).rows); } catch { /* */ }
  };
  page.on("response", onResp);
  await runSearchRound(page, page.getByRole("button", { name: "搜尋選擇權" }), RESAVE_SYMBOLS.length);
  page.off("response", onResp);
  return rows;
}

const sortTop5 = (rows) => {
  const keyOf = { return: (r) => -r.target_return, cost: (r) => r.entry_cost,
                  max_loss: (r) => r.max_loss_per_contract };
  return Object.fromEntries(Object.entries(keyOf).map(([id, k]) => [id, [...rows].sort((a, b) => (k(a) - k(b))
    || (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0)
    || (a.family < b.family ? -1 : a.family > b.family ? 1 : 0)).slice(0, 5)
    .map((r) => ({ symbol: r.symbol, family: r.family, candidate_key: r.candidate_key,
                   cost: r.entry_cost ?? r.cost_per_share, max_loss: r.max_loss_per_contract,
                   ret: r.target_return ?? r.strategy_return_at_target }))]));
};

/** 從畫面存一列 → 詳細頁：頭條（代表候選）、每股／每口成本、每口最大損失、報酬都要等於這一列。 */
async function resaveOne(page, row, device) {
  const results = page.getByRole("region", { name: "搜尋結果" });
  const tr = results.locator(`tbody tr[data-family="${row.family}"]`)
    .filter({ has: page.locator("td.opp-symbol", { hasText: new RegExp(`^${row.symbol.replace(".", "\\.")}\\b`) }) });
  const matches = await tr.count();
  await tr.first().getByRole("button", { name: "存成劇本" }).click();
  await page.waitForURL(/#\/s\/[^/]+$/, { timeout: 120000 });
  const id = decodeURIComponent(page.url().split("#/s/")[1]);
  const d = await waitAnalyzed(page, id);
  await page.waitForTimeout(2500);
  const text = (await page.locator("body").innerText()).replace(/\s+/g, " ");
  const rc = d.representative_candidate;
  const full = (d.latest_result?.candidate_pool ?? {})[rc?.candidate_key] ?? {};
  const pct = `${(row.target_return * 100).toFixed(1)}%`;
  const strikes = row.legs.map((l) => String(l.strike));
  const out = {
    device, id, saved_tw: tw(), row_matches_in_table: matches,
    row: { symbol: row.symbol, family: row.family, subtype: row.subtype, legs: legText(row.legs),
           candidate_key: row.candidate_key, cost_per_share: row.entry_cost,
           cost_per_contract: Math.round(row.entry_cost * 10000) / 100,
           max_loss_per_contract: row.max_loss_per_contract, return: row.target_return,
           scenario_strategies: row.scenario.strategies },
    scenario: { strategies: d.strategies, champion_key: rc?.candidate_key, champion_strategy: rc?.strategy,
                natural_cost: full.natural_cost, max_loss_per_contract: full.max_loss_per_contract,
                baseline_return: rc?.baseline_return, breakeven: full.breakeven, target_price: d.target_price,
                target_month: d.target_month },
    page: { has_return: text.includes(pct), has_cost_per_share: text.includes(money(row.entry_cost)),
            has_cost_per_contract: text.includes(money(row.entry_cost * 100)),
            has_max_loss_per_contract: text.includes(money(row.max_loss_per_contract)),
            has_all_strikes: strikes.every((k) => text.includes(k)) },
  };
  const near = (a, b) => typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 1e-6;
  out.data_match = rc?.candidate_key === row.candidate_key && near(full.natural_cost, row.entry_cost)
    && near(full.max_loss_per_contract, row.max_loss_per_contract) && near(rc?.baseline_return, row.target_return)
    && JSON.stringify(d.strategies) === JSON.stringify([row.family]);
  check(`[${device}] 存成劇本 ${row.symbol} ${row.subtype}：詳細頁頭條＝這一列（${row.candidate_key}），成本 ${money(row.entry_cost)}/股＝${money(row.entry_cost * 100)}/口、最大損失 ${money(row.max_loss_per_contract)}/口、報酬 ${pct}`,
        out.data_match && Object.values(out.page).every(Boolean), { scenario: out.scenario, page: out.page });
  return out;
}

async function phaseResave(ctx, page, device, picks) {
  const out = { device };
  out.settings = await setCustomUniverse(page, RESAVE_SYMBOLS, LOOSE.pr, LOOSE.d);
  const sel = await uiSelected(page);
  out.selected = sel.symbols;
  out.saves = [];
  let rows = null;
  for (const pick of picks) {
    rows = await uiSearchRows(page);
    out.search_rows ??= rows.map(rowView);
    const row = pick(rows);
    if (!row) { out.saves.push({ missing: String(pick) }); continue; }
    out.saves.push(await resaveOne(page, row, device));
  }
  return out;
}

// ---------- persist / UI ----------

async function persistenceSnapshot(page) {
  const status = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
  const list = (await api(page, "GET", "/api/scenarios")).body;
  const details = {};
  for (const s of list) {
    const d = (await api(page, "GET", `/api/scenarios/${encodeURIComponent(s.id)}`)).body;
    const c = championOf(d);
    details[s.id] = { champion: c.rc?.candidate_key ?? null, natural_cost: c.full?.natural_cost ?? null,
                      max_loss_per_contract: c.full?.max_loss_per_contract ?? null,
                      baseline_return: c.rc?.baseline_return ?? null };
  }
  return {
    at_tw: tw(),
    role: (await api(page, "GET", "/api/auth/status")).body?.role,
    data_as_of: status.data_as_of, progress: status.progress,
    consensus_status_counts: countBy(consensus.items, (i) => i.status),
    selected: consensus.items.filter((i) => i.gate.selected).map((i) => i.symbol),
    thresholds: consensus.thresholds,
    scenarios: list.map((s) => ({ id: s.id, symbol: s.symbol, target_price: s.target_price,
                                  target_month: s.target_month, best_return: s.best_return,
                                  analyzed_at: s.analyzed_at, ...details[s.id] }))
      .sort((a, b) => (a.id < b.id ? -1 : 1)),
    db: {
      consensus_snapshots: sql("SELECT count(*) FROM consensus_snapshots"),
      consensus_details: sql("SELECT count(*) FROM consensus_details"),
      consensus_refresh_state: sql("SELECT count(*) FROM consensus_refresh_state"),
      scenarios: sql("SELECT count(*) FROM scenarios"),
    },
  };
}

const OLD_NAMES = [
  ["搜尋母體／母體", /母體/],
  ["百分位", /百分位/],
  ["分歧度（單獨、分歧度 D、每月分歧度、分歧度門檻）", /分歧度(?!歷史排序)/],
  ["D 符號", /(^|[^A-Za-z])D [\d—]/],
  ["有效分析師", /有效分析師/],
  ["入選／入選股／未入選", /入選/],
  ["共識不夠", /共識不夠/],
  ["沒通過門檻", /沒通過門檻/],
  ["目標價情境報酬", /目標價情境報酬/],
  ["淨成本", /淨成本/],
  ["資料日（→ 資料日期）", /資料日(?!期)/],
];
const NEW_NAMES = ["掃描股票範圍", "分歧度歷史排序", "分析師分歧率", "有效券商數", "符合條件的股票",
                   "不符合條件", "股價達標時的策略報酬", "成本（每股／每口）", "最大損失（每股／每口）",
                   "資料日期", "目前股價", "目標漲跌幅"];
const SETTINGS_NEW = ["掃描股票範圍", "分歧度歷史排序門檻：PR ≥", "分析師分歧率上限（%）", "S&P 500 成分股"];

async function visibleText(page) {
  return page.evaluate(() => {
    const root = document.body;
    const attrs = [...root.querySelectorAll("[aria-label], [data-label], [title], [placeholder]")]
      .flatMap((el) => ["aria-label", "data-label", "title", "placeholder"].map((a) => el.getAttribute(a) ?? ""));
    const options = [...root.querySelectorAll("option")].map((o) => o.textContent ?? "");
    return [root.innerText ?? "", root.textContent ?? "", ...attrs, ...options].join("\n");
  });
}

function oldNameHits(text) {
  return OLD_NAMES.filter(([, re]) => re.test(text)).map(([name, re]) => {
    const m = text.match(re);
    return `${name}：…${text.slice(Math.max(0, m.index - 25), m.index + 25).replace(/\s+/g, " ")}…`;
  });
}

const noHScroll = (page) => page.evaluate(() => ({
  scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
  ok: document.documentElement.scrollWidth <= window.innerWidth }));

async function tooltipOf(page, button) {
  await page.waitForFunction((el) => el.getAttribute("aria-expanded") === "true", await button.elementHandle(), { timeout: 5000 });
  const id = await button.getAttribute("aria-describedby");
  const tip = page.locator(`[id="${id}"]`);
  await tip.waitFor({ timeout: 5000 });
  const box = await tip.boundingBox();
  const vp = await page.evaluate(() => ({ vw: document.documentElement.clientWidth, vh: window.innerHeight }));
  const role = await tip.getAttribute("role");
  const text = (await tip.innerText()).replace(/\s+/g, " ");
  return { role, text: text.slice(0, 300), inside: box && box.x >= 0 && box.x + box.width <= vp.vw + 0.5
           && box.y >= 0 && box.y + box.height <= vp.vh + 0.5, box, vp };
}

/** 一個裝置（桌面懸停／手機點按）的 UI 走查：ⓘ、橫向捲動、定稿名稱、舊名稱。 */
async function uiAudit(ctx, label, isDesktop, searchSymbols) {
  const page = await ctx.newPage();
  const out = { device: label };
  // 機會搜尋頁＋一次真實搜尋（一檔，畫面結果表才會出現）＋展開一檔共識詳細。
  await page.goto(`${BASE}/#/opportunity`);
  const selected = page.getByRole("region", { name: "符合條件的股票" });
  await selected.waitFor({ timeout: 30000 });
  await page.waitForFunction(() => /符合條件的股票（\d+ 檔）/.test(document.body.innerText), null, { timeout: 30000 });
  out.no_hscroll_opportunity = await noHScroll(page);
  const tips = [];
  for (const name of ["分析師分歧率說明", "分歧度歷史排序（PR）說明", "平均目標價說明", "目標漲跌幅說明",
                      "目前股價說明", "有效券商數說明", "資料日期說明"]) {
    const b = selected.getByRole("button", { name }).first();
    if (!(await b.count())) { tips.push({ name, present: false }); continue; }
    await b.scrollIntoViewIfNeeded();
    if (isDesktop) await b.hover(); else await b.tap();
    let t;
    try { t = await tooltipOf(page, b); } catch (e) { t = { error: String(e.message).split("\n")[0] }; }
    const closeHow = isDesktop ? "mouse-away" : "tap-again";
    if (isDesktop) await page.mouse.move(1, 1); else await b.tap();
    await page.waitForTimeout(250);
    const closed = (await page.getByRole("tooltip").count()) === 0;
    tips.push({ name, present: true, opened_by: isDesktop ? "hover" : "tap", ...t,
                has_three_sections: t.text ? /定義/.test(t.text) && /方向/.test(t.text) && /計算口徑/.test(t.text) : false,
                closed_by: closeHow, closed, no_hscroll: (await noHScroll(page)).ok });
  }
  if (!isDesktop) {
    const b = selected.getByRole("button", { name: "分析師分歧率說明" }).first();
    await b.tap();
    const opened = (await page.getByRole("tooltip").count()) === 1;
    await page.getByRole("heading", { name: "機會搜尋" }).first().tap();
    await page.waitForTimeout(250);
    out.mobile_tap_outside_closes = opened && (await page.getByRole("tooltip").count()) === 0;
  } else {
    // 桌面：點按不需要（懸停即開）；鍵盤 Enter／Esc 也測一次。
    const b = page.getByRole("button", { name: "掃描股票範圍說明" }).first();
    await b.focus();
    const focusOpen = (await page.getByRole("tooltip").count()) === 1;
    await page.keyboard.press("Escape");
    const escClosed = (await page.getByRole("tooltip").count()) === 0;
    await page.keyboard.press("Enter");
    const enterOpen = (await page.getByRole("tooltip").count()) === 1;
    await page.keyboard.press("Escape");
    out.keyboard = { focusOpen, escClosed, enterOpen };
  }
  out.tooltips = tips;
  const textOpp = await visibleText(page);
  // 一次真實搜尋：前端只搜符合條件清單，限一輪就停（停止鍵）——只要結果表出現。
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await page.getByRole("region", { name: "搜尋結果" }).waitFor({ timeout: 180000 }).catch(() => {});
  const stop = page.getByRole("button", { name: "停止" });
  if (await stop.count()) await stop.click().catch(() => {});
  await page.getByRole("button", { name: "搜尋選擇權" }).and(page.locator(":enabled")).waitFor({ timeout: 300000 });
  const results = page.getByRole("region", { name: "搜尋結果" });
  if (await results.count()) {
    out.no_hscroll_results = await noHScroll(page);
    const resTips = [];
    for (const name of ["目標漲跌幅說明", "股價達標時的策略報酬說明", "成本、最大損失說明", "目前股價說明"]) {
      const b = results.locator(".opp-help-results").getByRole("button", { name }).first();
      if (!(await b.count())) { resTips.push({ name, present: false }); continue; }
      await b.scrollIntoViewIfNeeded();
      if (isDesktop) await b.hover(); else await b.tap();
      let t;
      try { t = await tooltipOf(page, b); } catch (e) { t = { error: String(e.message).split("\n")[0] }; }
      if (isDesktop) await page.mouse.move(1, 1); else await b.tap();
      await page.waitForTimeout(250);
      resTips.push({ name, present: true, ...t, closed: (await page.getByRole("tooltip").count()) === 0 });
    }
    out.result_tooltips = resTips;
    // 展開第一列的共識詳細（明細列裡的 PR ⓘ）
    const detBtn = results.getByRole("button", { name: /共識詳細資料$/ }).first();
    await detBtn.click();
    await page.waitForTimeout(1500);
    const pr = results.getByRole("list", { name: "共識數值" }).getByRole("button", { name: "分歧度歷史排序（PR）說明" }).first();
    if (await pr.count()) {
      if (isDesktop) await pr.hover(); else await pr.tap();
      try { out.detail_pr_tooltip = await tooltipOf(page, pr); } catch (e) { out.detail_pr_tooltip = { error: String(e.message).split("\n")[0] }; }
      if (isDesktop) await page.mouse.move(1, 1); else await pr.tap();
    }
    out.no_hscroll_with_detail = await noHScroll(page);
    out.result_card_labels = await results.locator("tbody tr[data-family]").first().evaluate((tr) =>
      [...tr.querySelectorAll("td[data-label]")].map((td) => td.getAttribute("data-label")));
  }
  const textRes = await visibleText(page);
  const all = `${textOpp}\n${textRes}`;
  out.old_name_hits_opportunity = oldNameHits(all);
  out.new_names_present_opportunity = Object.fromEntries(NEW_NAMES.map((n) => [n, all.includes(n)]));
  // 設定頁
  const section = await settingsSection(page);
  out.no_hscroll_settings = await noHScroll(page);
  const sText = await section.evaluate((el) => {
    const attrs = [...el.querySelectorAll("[aria-label], [data-label], [title], [placeholder]")]
      .flatMap((e) => ["aria-label", "data-label", "title", "placeholder"].map((a) => e.getAttribute(a) ?? ""));
    return [el.innerText, el.textContent, ...attrs].join("\n");
  });
  out.old_name_hits_settings = oldNameHits(sText);
  out.new_names_present_settings = Object.fromEntries(SETTINGS_NEW.map((n) => [n, sText.includes(n)]));
  const sTip = section.getByRole("button", { name: "分歧度歷史排序（PR）說明" }).first();
  if (await sTip.count()) {
    if (isDesktop) await sTip.hover(); else await sTip.tap();
    try { out.settings_pr_tooltip = await tooltipOf(page, sTip); } catch (e) { out.settings_pr_tooltip = { error: String(e.message).split("\n")[0] }; }
    if (isDesktop) await page.mouse.move(1, 1); else await sTip.tap();
  }
  // 劇本詳細頁（存成劇本的那幾檔）
  const list = (await api(page, "GET", "/api/scenarios")).body.filter((s) => s.symbol !== "ZZCANARY");
  out.scenario_pages = [];
  for (const s of list.slice(0, 2)) {
    await page.goto(`${BASE}/#/s/${encodeURIComponent(s.id)}`);
    await page.waitForTimeout(3000);
    out.scenario_pages.push({ id: s.id, symbol: s.symbol, no_hscroll: await noHScroll(page) });
  }
  await page.close();
  return out;
}

function fixtureEvidence() {
  return {
    consensus_snapshots_by_source: sqlRows("SELECT source, is_fixture, count(*) FROM consensus_snapshots GROUP BY 1,2")
      .map(([source, is_fixture, n]) => ({ source, is_fixture, n: Number(n) })),
    consensus_details_by_source: sqlRows("SELECT source, count(*) FROM consensus_details GROUP BY 1")
      .map(([source, n]) => ({ source, n: Number(n) })),
    refresh_state_by_source: sqlRows("SELECT source, count(*), count(error) FROM consensus_refresh_state GROUP BY 1")
      .map(([source, n, errors]) => ({ source, n: Number(n), errors: Number(errors) })),
    results_by_snapshot_source: sqlRows("SELECT coalesce(snapshot_source,'(null)'), count(*) FROM results GROUP BY 1")
      .map(([source, n]) => ({ source, n: Number(n) })),
  };
}

// ---------- main ----------

async function main() {
  if (!OUT) abort("需要 OC_409_OUT");
  mkdirSync(OUT, { recursive: true });
  if (!existsSync(join(ROOT, "dist/index.html"))) abort("找不到 dist/：先跑 npm run build");
  const tables = Number(sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'"));
  if (PHASE === "build" && !RESUME && tables !== 0) abort(`資料庫 ${DB} 不是空的（${tables} 張表）；build 只在全新的庫上跑`);
  if (PHASE !== "build" && tables === 0) abort(`資料庫 ${DB} 是空的；先跑 build`);
  report.started_tw = tw();
  report.dsn = { host: PG.host, port: PG.port, db: DB,
                 server_addr: sql("SELECT inet_server_addr()::text || ' / ' || current_database()") };
  const tmp = mkdtempSync(join(tmpdir(), "oc-409-"));
  const cert = join(tmp, "cert.pem"), key = join(tmp, "key.pem");
  execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                           "-out", cert, "-days", "1", "-subj", "/CN=127.0.0.1"], { stdio: "ignore" });
  const serverArgs = ["--dsn", DSN, "--port", String(PORT), "--cert", cert, "--key", key];
  let server = startServer(serverArgs);
  let ctx;
  let aborted = false;
  try {
    await server.ready;
    ctx = await chromium.launchPersistentContext(join(OUT, "profile"), {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined, args: ARGS,
      ignoreHTTPSErrors: true, viewport: { width: 1360, height: 900 } });
    report.browser_args = ARGS;
    report.canary = await canary(ctx, { write: PHASE === "build" && !RESUME });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/#/`);
    check("SU 登入（拋棄式密碼，只在本機行程內）", (await login(page)) === "superuser");

    if (PHASE === "build") {
      const saved0 = await setThresholds(page, 80, 10);
      report.phases.settings_default = saved0;
      check("設定頁：掃描股票範圍預設＝S&P 500 成分股；PR≥80 存回 percentile_max=20、分歧率上限 10",
            saved0.sp500_was_checked && saved0.universe_id === "sp500"
            && saved0.percentile_max === 20 && saved0.dispersion_max === 10, saved0);
      report.phases.b1_build = await phaseBuild(page); save();
      report.phases.b2_snapshot = await consensusSnapshot(page); save();
      await openOpportunity(page);
      report.phases.b2_facts_after = await statusFacts(page);
      const snap = report.phases.b2_snapshot;
      check("建置完成：S&P 500 全部有結果，來源 yahoo-udh、is_fixture=false",
            snap.progress.total >= 500 && snap.items.length === snap.progress.total
            && snap.source.name === "yahoo-udh" && snap.source.is_fixture === false,
            { progress: snap.progress, source: snap.source });
      report.phases.b3_same_day = await phaseSameDayRerun(page); save();
      report.phases.b4_selection = await phaseSelection(page, [[80, 10], [LOOSE.pr, LOOSE.d], [80, 10]]); save();
      report.phases.b5_retry_slot = await phaseRetrySlot(page, snap); save();
      report.phases.b6_snapshot_final = await consensusSnapshot(page);
      await openOpportunity(page);
      report.phases.b6_facts_final = await statusFacts(page);
      const s = await stats(page);
      report.phases.server_totals = { analyst_fetches: s.analyst_fetches, analyst_http_requests: s.analyst_http_requests,
        yahoo_http: s.yahoo_http, yahoo_http_status: s.yahoo_http_status, blocked_connections: s.blocked_connections };
    } else if (PHASE === "search") {
      const out = {};
      await setThresholds(page, 80, 10);
      const selDefault = (await uiSelected(page)).symbols.length;
      const sA = await phaseSearch(page, `PR≥80/10%`, selDefault, 99);
      const rowsA = sA._rows_full; delete sA._rows_full;
      out.search_default = sA; report.phases = out; save();
      const rowA = [...rowsA].sort((a, b) => b.target_return - a.target_return)[0];
      const savedA = await saveRowFromUi(page, rowA);
      await setThresholds(page, LOOSE.pr, LOOSE.d);
      const selLoose = (await uiSelected(page)).symbols.length;
      const sB = await phaseSearch(page, `PR≥${LOOSE.pr}/${LOOSE.d}%`, selLoose, LOOSE_MAX_BATCHES);
      const rowsB = sB._rows_full; delete sB._rows_full;
      sB.selected_count = selLoose;
      out.search_loose = sB; save();
      const rankedB = [...rowsB].sort((a, b) => a.max_loss_per_contract - b.max_loss_per_contract);
      const rowB = rankedB.find((r) => r.symbol !== rowA.symbol && r.family !== rowA.family)
        ?? rankedB.find((r) => r.symbol !== rowA.symbol);
      const savedB = await saveRowFromUi(page, rowB);
      out.save_compare = [savedA, savedB].map((sv, i) => {
        const row = i === 0 ? rowA : rowB;
        const cmp = compareSaved(row, sv);
        check(`存成劇本 ${row.symbol} ${row.family}：詳細頁的成本（每股／每口）、最大損失（每口）、報酬與結果列一致`,
              cmp.mismatches.length === 0 && Object.values(cmp.detail_page_text_contains).every(Boolean)
              && sv.db_scenarios_delta === 1, { mismatches: cmp.mismatches, ui: cmp.detail_page_text_contains });
        const { detail_text: _t, detail: d, ...rest } = sv;
        return { row: rowView(row), ...rest, snapshot_source: d.latest_result?.snapshot?.source ?? null, ...cmp };
      });
      await setThresholds(page, 80, 10);
      const s = await stats(page);
      out.server_totals = { yahoo_http: s.yahoo_http, yahoo_http_status: s.yahoo_http_status,
                            chain_attempts: s.chain_attempts, chain_sources: s.chain_sources,
                            blocked_connections: s.blocked_connections, analyst_fetches: s.analyst_fetches };
      report.phases = out;
    } else if (PHASE === "resave") {
      const out = { head: process.env.OC_409_HEAD ?? null };
      const byRet = (rs, sym) => [...rs].filter((r) => r.symbol === sym).sort((a, b) => b.target_return - a.target_return);
      const pickFam = (sym, fam) => Object.assign((rs) => rs.find((r) => r.symbol === sym && r.family === fam),
                                                  { toString: () => `${sym}/${fam}` });
      const pickTop = (sym) => Object.assign((rs) => byRet(rs, sym)[0], { toString: () => `${sym}/top` });
      const picks = [pickFam("DVN", "vertical-spread"), pickFam("DVN", "single-leg"), pickTop("GOOG"),
                     pickFam("GOOG", "vertical-spread"), pickFam("JPM", "vertical-spread"), pickFam("BAC", "single-leg")];
      out.desktop = await phaseResave(ctx, page, "desktop 1360x900", picks);
      // 搜尋排名：與修正前（live409_search_raw.json 的 PR≥50/20% 那一輪）同 4 檔的前 5 比較。
      const pre = JSON.parse(readFileSync(join(OUT, "live409_search_raw.json"), "utf8")).phases.search_loose.rows
        .filter((r) => RESAVE_SYMBOLS.includes(r.symbol));
      const preTop = sortTop5(pre.map((r) => ({ ...r, entry_cost: r.cost_per_share,
                                                target_return: r.strategy_return_at_target })));
      const postTop = sortTop5(out.desktop.search_rows.map((r) => ({ ...r, entry_cost: r.cost_per_share,
                                                                      target_return: r.strategy_return_at_target })));
      out.ranking = { pre_fix: preTop, post_fix: postTop };
      for (const id of Object.keys(preTop)) {
        const same = JSON.stringify(preTop[id]) === JSON.stringify(postTop[id]);
        check(`排名「${id}」前 5（${RESAVE_SYMBOLS.join("/")}）修正前後完全相同（代號、家族、候選、成本、最大損失、報酬）`, same,
              { pre: preTop[id].map((x) => `${x.symbol}/${x.family}`), post: postTop[id].map((x) => `${x.symbol}/${x.family}`) });
      }
      const preRows = Object.fromEntries(pre.map((r) => [`${r.symbol}|${r.family}`, r]));
      out.row_diffs = out.desktop.search_rows.map((r) => {
        const p = preRows[`${r.symbol}|${r.family}`];
        return { key: `${r.symbol}|${r.family}`, pre: p ? [p.candidate_key, p.cost_per_share, p.max_loss_per_contract, p.strategy_return_at_target] : null,
                 post: [r.candidate_key, r.cost_per_share, r.max_loss_per_contract, r.strategy_return_at_target] };
      }).filter((x) => JSON.stringify(x.pre) !== JSON.stringify(x.post));
      await ctx.close();
      const iphone = devices["iPhone 13"];
      ctx = await chromium.launchPersistentContext(join(OUT, "profile-resave-mobile"), {
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined, args: ARGS,
        ignoreHTTPSErrors: true, viewport: iphone.viewport, deviceScaleFactor: iphone.deviceScaleFactor,
        isMobile: true, hasTouch: true, userAgent: iphone.userAgent });
      out.canary_mobile = await canary(ctx, { write: false });
      const mpage = await ctx.newPage();
      await mpage.goto(`${BASE}/#/`);
      check("手機：SU 登入", (await login(mpage)) === "superuser");
      out.mobile = await phaseResave(ctx, mpage, "iPhone 13 390x844", [pickFam("DVN", "vertical-spread")]);
      out.mobile.no_hscroll_detail = await noHScroll(mpage);
      // 掃描股票範圍改回 S&P 500、PR≥80／10%。
      await setThresholds(mpage, 80, 10);
      report.phases = out;
    } else if (PHASE === "persist") {
      const out = {};
      out.before = await persistenceSnapshot(page);
      await page.goto(`${BASE}/#/opportunity`);
      await page.reload();
      await page.waitForTimeout(2000);
      out.after_reload = await persistenceSnapshot(page);
      server.child.kill("SIGTERM");
      await server.exited;
      out.restarted_at_tw = tw();
      secrets.OC_VERIFY_NONCE = randomBytes(12).toString("hex");
      server = startServer(serverArgs);
      await server.ready;
      out.canary_after_restart = await canary(ctx, { write: false });
      await page.reload();
      await page.waitForTimeout(3000);
      out.after_restart = await persistenceSnapshot(page);
      const key = (x) => JSON.stringify({ d: x.data_as_of, p: x.progress, c: x.consensus_status_counts,
        sel: x.selected, s: x.scenarios.filter((sc) => sc.symbol !== "ZZCANARY").map((sc) =>
          [sc.id, sc.symbol, sc.target_price, sc.target_month, sc.best_return, sc.champion,
           sc.natural_cost, sc.max_loss_per_contract, sc.baseline_return]),
        db: [x.db.consensus_snapshots, x.db.consensus_details, x.db.consensus_refresh_state, x.db.scenarios] });
      check("重新整理後：共識快取（資料日期、各狀態檔數、符合條件）與劇本（含每股／每口數字）不變",
            key(out.before) === key(out.after_reload));
      check("重啟後端（同一資料庫）後：仍是 SU，共識快取與劇本不變",
            out.after_restart.role === "superuser" && key(out.before) === key(out.after_restart));
      // UI：桌面（懸停）＋手機（點按），同一個身分（同一個瀏覽器設定檔的 cookie）。
      out.ui_desktop = await uiAudit(ctx, "desktop 1360x900", true);
      await ctx.close();
      const iphone = devices["iPhone 13"];
      ctx = await chromium.launchPersistentContext(join(OUT, "profile"), {
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined, args: ARGS,
        ignoreHTTPSErrors: true, viewport: iphone.viewport, deviceScaleFactor: iphone.deviceScaleFactor,
        isMobile: true, hasTouch: true, userAgent: iphone.userAgent });
      out.canary_mobile = await canary(ctx, { write: false });
      out.ui_mobile = await uiAudit(ctx, "iPhone 13 390x844", false);
      for (const u of [out.ui_desktop, out.ui_mobile]) {
        const tipsOk = [...u.tooltips, ...(u.result_tooltips ?? [])].filter((t) => t.present)
          .every((t) => t.role === "tooltip" && t.inside && t.closed !== false);
        check(`${u.device}：ⓘ 以${u.device.startsWith("desktop") ? "懸停" : "點按"}開啟、role=tooltip、在視窗內、可關閉`,
              tipsOk, [...u.tooltips, ...(u.result_tooltips ?? [])].filter((t) => !(t.role === "tooltip" && t.inside)).map((t) => t.name));
        check(`${u.device}：沒有橫向捲動（機會搜尋、結果表、設定頁、劇本詳細）`,
              u.no_hscroll_opportunity.ok && (u.no_hscroll_results?.ok ?? true) && (u.no_hscroll_with_detail?.ok ?? true)
              && u.no_hscroll_settings.ok && u.scenario_pages.every((p) => p.no_hscroll.ok),
              { opp: u.no_hscroll_opportunity, res: u.no_hscroll_results, set: u.no_hscroll_settings });
        check(`${u.device}：#405 定稿名稱都在、沒有任何舊名稱`,
              u.old_name_hits_opportunity.length === 0 && u.old_name_hits_settings.length === 0
              && Object.values(u.new_names_present_opportunity).every(Boolean)
              && Object.values(u.new_names_present_settings).every(Boolean),
              { old: [...u.old_name_hits_opportunity, ...u.old_name_hits_settings].slice(0, 5),
                missing: Object.entries({ ...u.new_names_present_opportunity, ...u.new_names_present_settings }).filter(([, v]) => !v).map(([k]) => k) });
      }
      check("手機：點外面關閉說明", out.ui_mobile.mobile_tap_outside_closes);
      check("桌面：鍵盤聚焦開、Esc 關、Enter 開", out.ui_desktop.keyboard?.focusOpen && out.ui_desktop.keyboard?.escClosed
            && out.ui_desktop.keyboard?.enterOpen, out.ui_desktop.keyboard);
      const page2 = await ctx.newPage();
      await page2.goto(`${BASE}/#/`);
      const fx = fixtureEvidence();
      const st = await stats(page2);
      const consensus = (await api(page2, "GET", "/api/opportunity/consensus")).body;
      out.no_fixture = { api_source: consensus.source, db: fx, server_chain_sources_this_process: st.chain_sources,
                         server_blocked_connections: st.blocked_connections,
                         page_has_fixture_label: (await page2.getByText("測試資料，非真實市場資料").count()) > 0 };
      check("沒有 fixture：API 來源 yahoo-udh／is_fixture=false；DB 共識列全部 yahoo-udh 且 is_fixture=false",
            consensus.source.name === "yahoo-udh" && consensus.source.is_fixture === false
            && fx.consensus_snapshots_by_source.length === 1
            && fx.consensus_snapshots_by_source[0].source === "yahoo-udh"
            && fx.consensus_snapshots_by_source[0].is_fixture === "f", fx.consensus_snapshots_by_source);
      report.phases = out;
    }
  } catch (e) {
    aborted = Boolean(e.abort);
    if (!e.abort) {
      console.error(e);
      console.error(server.log().slice(-3000));
    }
    check("流程沒有中途出錯", false, String(e.message ?? e).split("\n")[0]);
  } finally {
    await ctx?.close().catch(() => {});
    server.child.kill("SIGTERM");
    rmSync(tmp, { recursive: true, force: true });
    report.finished_tw = tw();
    const failed = checks.filter((r) => !r.ok);
    report.summary = { checks: checks.length, passed: checks.length - failed.length, failed: failed.length,
                       failed_names: failed.map((f) => f.name) };
    save();
    console.log(JSON.stringify(report.summary, null, 2));
    process.exit(aborted ? 3 : failed.length ? 1 : 0);
  }
}

await main();
