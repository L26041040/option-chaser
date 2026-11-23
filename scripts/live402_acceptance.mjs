// LIVE-T6（#402）：約 50 檔「真實資料」本機驗收——產出 #402 驗收條件 1–7 的數字。
//
// 起本機驗證站（`scripts/opportunity_live_verify_server.py`：`dist/` 前端＋同一個
// FastAPI app；分析師資料＝真實 Yahoo `upgradeDowngradeHistory`；選擇權報價＝既有
// 預設路徑 Cboe → yfinance；資料庫＝本機 Postgres，DSN 寫死 127.0.0.1），用真
// Chromium（`--no-proxy-server`＋金絲雀）走：
//
//   1. SU 登入 → 設定頁：母體＝大型股樣本、門檻 20／10 → 機會搜尋頁「開始建立」
//      （#398 的正式更新路徑，前端依 `remaining` 自動續跑）→ 每檔狀態、原因、
//      合格歷史點數、上游呼叫數、耗時、續跑次數。
//   2. 兩道門檻：20／10、50／20、更緊的 10／8、100／100，全部從**設定頁**改，
//      回機會搜尋頁讀入選清單（畫面＝API），且改門檻不打上游。
//   3. 20／10 與 50／20 各搜尋一次選擇權（畫面按鈕，真實 chain）：每檔耗時、
//      家族數、零候選／失敗原因、報價來源。
//   4. 三種排序（後端 `sort_options`）各取畫面前 5 列。
//   5. 從畫面「存成劇本」兩列（不同 symbol），再以既有 `POST /api/scenarios`
//      ＋`/refresh` 手動建立同參數劇本（目標價＝共識清單的 mean、同目標月、
//      同家族），逐欄比對。
//   6. 重新整理＋重啟後端（同一個資料庫）：共識快取與劇本都還在。
//   7. 沒有 fixture：來源名稱、DB 的 is_fixture、報價來源。
//
//   PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium SSL_CERT_FILE=/root/.ccr/ca-bundle.crt \
//     OC_402_DB=oc402 OC_402_OUT=/path/to/outdir node scripts/live402_acceptance.mjs
//
// 資料庫必須事先建立且是空的（本腳本不 drop、不 create，避免碰到別人的庫）。
// ⚠ 安全：同 `opportunity_live_verify.mjs`——瀏覽器不走 proxy、寫入前先過金絲雀、
// 驗證站只連本機 Postgres、SU／SA 密碼每次隨機產生、不印出不寫檔。不截圖。
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PG = { host: "127.0.0.1", port: "55432", user: "postgres" };
const DB = process.env.OC_402_DB ?? "oc402";
const DSN = `postgresql://${PG.user}@${PG.host}:${PG.port}/${DB}`;
const PORT = Number(process.env.OC_VERIFY_PORT ?? 8472);
const BASE = `https://127.0.0.1:${PORT}`;
const OUT = process.env.OC_402_OUT;
const PYTHON = process.env.OC_VERIFY_PYTHON
  ?? [join(ROOT, ".venv/bin/python"), "/home/user/option-chaser/.venv/bin/python"]
    .find((p) => existsSync(p)) ?? "python3";
const SLOW_SECONDS = 45;

const report = { started_tw: null, db: DB, checks: [], phases: {} };
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
const info = (label, obj) => console.log(`INFO  ${label} ${JSON.stringify(obj).slice(0, 1500)}`);
const save = () => {
  if (OUT) writeFileSync(join(OUT, "live402_raw.json"), JSON.stringify(report, null, 2));
};

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
                   "DATABASE_URL_POOLED", "POSTGRES_URL_NON_POOLING"]) delete env[k];
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

async function api(page, method, path, { body } = {}) {
  return page.evaluate(async ([m, p, b]) => {
    const t0 = performance.now();
    const r = await fetch(p, { method: m,
      headers: b ? { "Content-Type": "application/json" } : {},
      body: b ? JSON.stringify(b) : undefined });
    let json = null;
    try { json = await r.json(); } catch { /* 204 */ }
    return { status: r.status, body: json, ms: Math.round(performance.now() - t0) };
  }, [method, path, body]);
}
const stats = async (page) => (await api(page, "GET", "/__verify/stats")).body;

async function canary(browser, { write }) {
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
  const out = { nonce_ok: true, label: s.label, health_storage: health.storage,
                health_commit: health.backend.commit };
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
  await ctx.close();
  return out;
}

// ---------- 小工具 ----------

async function login(page) {
  await page.goto(`${BASE}/#/`);
  await page.goto(`${BASE}/#/settings`);
  const input = page.locator("input[type=password]:visible").first();
  await input.waitFor();
  await input.fill(secrets.OC_VERIFY_SU_PASSWORD);
  const reloaded = page.waitForEvent("load");
  await page.locator("button:visible", { hasText: /^登入$/ }).first().click();
  await reloaded;
  await page.waitForLoadState("networkidle");
  return (await api(page, "GET", "/api/auth/status")).body?.role;
}

async function setThresholds(page, pMax, dMax) {
  await page.goto(`${BASE}/#/settings/opportunity`);
  const section = page.getByRole("region", { name: "機會搜尋" });
  // 桌面版設定頁是分頁（subnav）：已經在設定頁時改 hash 不會換分頁，點「機會搜尋」分頁。
  const tab = page.getByRole("tab", { name: "機會搜尋" });
  await Promise.race([section.waitFor(), tab.waitFor()]);
  if (!(await section.isVisible()) && (await tab.isVisible())) await tab.click();
  await section.waitFor();
  const sample = section.getByRole("radio", { name: /大型股樣本/ });
  if (!(await sample.isChecked())) await sample.check();
  await section.getByLabel("分歧度歷史百分位門檻（%）").fill(String(pMax));
  await section.getByLabel("分歧度門檻（%）").fill(String(dMax));
  await section.getByRole("button", { name: "儲存" }).click();
  await section.getByRole("status").filter({ hasText: "已儲存" }).waitFor();
  const got = (await api(page, "GET", "/api/settings")).body.opportunity_search;
  return got;
}

async function openOpportunity(page) {
  await page.goto(`${BASE}/#/opportunity`);
  const region = page.getByRole("region", { name: "入選股" });
  await region.waitFor({ timeout: 30000 });
  return region;
}

async function uiSelected(page) {
  const region = await openOpportunity(page);
  await page.waitForFunction(() => /入選股（\d+ 檔）/.test(
    document.querySelector('[aria-label="入選股"] h2')?.textContent ?? ""), null, { timeout: 30000 });
  const heading = await region.locator("h2").innerText();
  const symbols = await region.locator("li.opp-item").evaluateAll(
    (xs) => xs.map((x) => x.getAttribute("aria-label")));
  return { heading, symbols };
}

function gateSummary(consensus) {
  const items = consensus.items;
  const byStatus = {};
  for (const i of items) byStatus[i.status] = (byStatus[i.status] ?? 0) + 1;
  const ok = items.filter((i) => i.status === "ok");
  const selected = items.filter((i) => i.gate.selected).map((i) => i.symbol);
  const failFirst = ok.filter((i) => !i.gate.first).map((i) => i.symbol);
  const failSecond = ok.filter((i) => !i.gate.second).map((i) => i.symbol);
  const both = ok.filter((i) => !i.gate.first && !i.gate.second).map((i) => i.symbol);
  return {
    thresholds: consensus.thresholds,
    selected_count: selected.length, selected,
    excluded_by_data_status: Object.fromEntries(
      Object.entries(byStatus).filter(([k]) => k !== "ok")),
    excluded_by_data_status_symbols: Object.fromEntries(
      Object.keys(byStatus).filter((k) => k !== "ok").map((k) =>
        [k, items.filter((i) => i.status === k).map((i) => i.symbol)])),
    status_ok: ok.length,
    excluded_rule1_percentile: failFirst.length,
    excluded_rule2_dispersion: failSecond.length,
    excluded_both_rules: both.length,
    excluded_rule1_only: failFirst.length - both.length,
    excluded_rule2_only: failSecond.length - both.length,
    rule1_fail_symbols: failFirst, rule2_fail_symbols: failSecond,
    non_ok_with_gate_selected: items.filter((i) => i.status !== "ok" && i.gate.selected)
      .map((i) => i.symbol),
  };
}

const legText = (legs) => legs.map((l) =>
  `${l.side === "buy" ? "+" : "-"}${l.quantity}x${l.strike}${/^c/i.test(l.option_type) ? "C" : "P"}`).join(" ");
const rowView = (r) => ({
  symbol: r.symbol, family: r.family, subtype: r.subtype, expiry: r.expiry,
  legs: legText(r.legs), entry_cost: r.entry_cost,
  max_loss_per_share: r.max_loss_per_contract / 100,
  max_loss_per_contract: r.max_loss_per_contract,
  target_return: r.target_return, breakeven: r.breakeven,
  target_price: r.scenario.target_price, target_month: r.target_month,
  candidate_key: r.candidate_key });

function intrinsicAt(legs, spot) {
  let v = 0;
  for (const l of legs) {
    const call = /^c/i.test(l.option_type);
    const iv = call ? Math.max(0, spot - l.strike) : Math.max(0, l.strike - spot);
    v += (l.side === "buy" ? 1 : -1) * l.quantity * iv;
  }
  return v;
}

function anomalies(rows, spots) {
  const out = [];
  for (const r of rows) {
    const spot = spots[r.symbol];
    const notes = [];
    if (spot) {
      const intrinsic = intrinsicAt(r.legs, spot);
      if (intrinsic > 0.5 && r.entry_cost < 0.9 * intrinsic) {
        notes.push(`淨成本 ${r.entry_cost.toFixed(2)} 低於現價 ${spot} 下的內含價值 ${intrinsic.toFixed(2)}`);
      }
    }
    const ml = r.max_loss_per_contract / 100;
    if (r.entry_cost > 0 && ml > 3 * r.entry_cost) {
      notes.push(`最大損失/股 ${ml.toFixed(2)} > 3× 淨成本 ${r.entry_cost.toFixed(2)}（不對稱翼）`);
    }
    if (r.target_return > 10) notes.push(`目標價情境報酬 ${(r.target_return * 100).toFixed(0)}%（>1000%）`);
    if (notes.length) out.push({ ...rowView(r), spot: spot ?? null, notes });
  }
  return out;
}

// ---------- 階段 ----------

async function phaseConsensusBuild(page) {
  const phase = {};
  const region = await openOpportunity(page);
  phase.before_ui_building = /資料建立中/.test(await region.innerText());
  check("建立前：入選股區塊顯示「資料建立中」", phase.before_ui_building);
  const panel = page.getByRole("region", { name: "分析師資料" });
  const facts = panel.getByRole("list", { name: "資料狀態" });
  await facts.getByRole("listitem", { name: "今日更新" }).waitFor({ timeout: 20000 });
  phase.before_facts = {
    資料來源: await facts.getByRole("listitem", { name: "資料來源" }).innerText(),
    已建立: await facts.getByRole("listitem", { name: "已建立" }).innerText() };

  const updates = [];
  const pending = new Map();
  const onReq = (rq) => { if (rq.url().endsWith("/api/opportunity/consensus/update")) pending.set(rq, Date.now()); };
  const onResp = async (r) => {
    if (!r.url().endsWith("/api/opportunity/consensus/update")) return;
    const t = pending.get(r.request());
    let body = null;
    try { body = await r.json(); } catch { /* */ }
    updates.push({ status: r.status(), ms: t ? Date.now() - t : null,
                   processed: body?.processed, succeeded: body?.succeeded, failed: body?.failed,
                   processed_symbols: body?.processed_symbols,
                   remaining: body?.remaining?.length, stopped_reason: body?.stopped_reason,
                   upstream_calls_today: body?.upstream_calls_today, progress: body?.progress });
  };
  page.on("request", onReq);
  page.on("response", onResp);
  const s0 = await stats(page);
  phase.started_tw = tw();
  const t0 = Date.now();
  await panel.getByRole("button", { name: "開始建立" }).click();
  await page.getByText(/更新完成/).waitFor({ timeout: 900000 });
  phase.wall_seconds = Math.round((Date.now() - t0) / 100) / 10;
  phase.finished_tw = tw();
  await page.waitForTimeout(1500);
  page.off("request", onReq);
  page.off("response", onResp);
  const s1 = await stats(page);
  phase.update_calls = updates.length;
  phase.continuation_calls = Math.max(0, updates.length - 1);
  phase.update_responses = updates;
  phase.analyst_fetches = s1.analyst_fetches - s0.analyst_fetches;
  phase.analyst_http_requests = s1.analyst_http_requests - s0.analyst_http_requests;
  phase.analyst_log = s1.analyst_log;

  const status = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  phase.status = { today: status.today, data_as_of: status.data_as_of,
                   progress: status.progress, upstream_calls_today: status.upstream_calls_today,
                   daily_cap: status.daily_cap, policy: status.policy, source: status.source,
                   failed: status.symbols.filter((s) => s.error).map((s) => ({ symbol: s.symbol, error: s.error, state: s.state })),
                   retries: status.symbols.reduce((a, s) => a + s.retries_today, 0) };
  const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
  phase.rules = consensus.rules;
  phase.universe = consensus.universe;
  phase.source = consensus.source;
  const hMin = consensus.rules.h_min;
  const details = {};
  for (const i of consensus.items) {
    const d = (await api(page, "GET", `/api/opportunity/consensus-detail/${i.symbol}`)).body;
    details[i.symbol] = { qualified_points: d.qualified_points, months: d.series.length,
                          effective_firms: d.effective.length, detail_available: d.detail_available };
  }
  phase.items = consensus.items.map((i) => ({
    symbol: i.symbol, status: i.status, reasons: i.reasons, n_analysts: i.n_analysts,
    mean: i.mean, stdev: i.stdev, dispersion: i.dispersion, percentile: i.percentile,
    history_points: i.history_points, coverage: i.coverage, freshness_share: i.freshness_share,
    target_month: i.target_month, as_of: i.as_of, refresh_error: i.refresh_error,
    ...details[i.symbol] }));
  const byStatus = {};
  for (const i of phase.items) {
    byStatus[i.status] ??= { count: 0, symbols: [] };
    byStatus[i.status].count += 1;
    byStatus[i.status].symbols.push({ symbol: i.symbol, reasons: i.reasons });
  }
  phase.status_breakdown = byStatus;
  const n = phase.items.length;
  const qual = phase.items.map((i) => i.qualified_points);
  const enough = phase.items.filter((i) => i.qualified_points >= hMin);
  const withData = phase.items.filter((i) => !["no_data", "source_error"].includes(i.status));
  phase.coverage = {
    h_min: hMin, universe: n,
    fetch_success: n - phase.status.failed.length,
    with_data: withData.length,
    stocks_with_qualified_ge_hmin: enough.length,
    share_ge_hmin: Math.round((enough.length / n) * 1000) / 1000,
    mean_qualified_points: Math.round((qual.reduce((a, b) => a + b, 0) / n) * 100) / 100,
    history_points_equals_qualified: phase.items.every((i) => i.history_points === i.qualified_points),
    below_hmin: phase.items.filter((i) => i.qualified_points < hMin)
      .map((i) => ({ symbol: i.symbol, qualified: i.qualified_points, status: i.status })),
  };
  check("共識建立：50 檔全部有結果（成功＋失敗＝母體），來源 yahoo-udh 非測試資料",
        status.progress.total === n && consensus.source.name === "yahoo-udh"
        && consensus.source.is_fixture === false && phase.analyst_fetches > 0,
        { progress: status.progress, analyst_fetches: phase.analyst_fetches });
  // 畫面資料狀態
  await page.waitForFunction((k) => (document.querySelector('[aria-label="已建立"]')?.textContent ?? "")
    .includes(`${k}／${k} 檔`), n, { timeout: 30000 }).catch(() => {});
  phase.after_facts = {
    標題: await panel.getByRole("heading", { name: /^分析師資料/ }).innerText(),
    資料來源: await facts.getByRole("listitem", { name: "資料來源" }).innerText(),
    資料日: await facts.getByRole("listitem", { name: "資料日" }).innerText(),
    已建立: await facts.getByRole("listitem", { name: "已建立" }).innerText(),
    入選: await facts.getByRole("listitem", { name: "入選" }).innerText() };
  info("共識建立", { wall: phase.wall_seconds, calls: phase.update_calls, coverage: phase.coverage });
  return phase;
}

async function phaseGates(page) {
  const settings = [[20, 10], [50, 20], [10, 8], [100, 100], [20, 10]];
  const out = [];
  const s0 = await stats(page);
  for (const [p, d] of settings) {
    const saved = await setThresholds(page, p, d);
    const ui = await uiSelected(page);
    const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
    const g = gateSummary(consensus);
    const same = JSON.stringify(ui.symbols) === JSON.stringify(g.selected);
    check(`門檻 ${p}／${d}（設定頁）：機會搜尋頁入選清單＝API 入選清單（${g.selected_count} 檔）`,
          same && saved.percentile_max === p && saved.dispersion_max === d,
          { ui: ui.symbols, api: g.selected });
    out.push({ ...g, ui_heading: ui.heading, ui_symbols: ui.symbols, ui_matches_api: same,
               changed_at_tw: tw() });
  }
  const s1 = await stats(page);
  const changed = new Set(out.map((g) => g.selected.join(","))).size > 1;
  check("改門檻後入選名單立即改變，且不打上游（分析師抓取次數不變）",
        changed && s1.analyst_fetches === s0.analyst_fetches,
        { analyst_fetches_delta: s1.analyst_fetches - s0.analyst_fetches });
  return { settings: out, analyst_fetches_during_gate_changes: s1.analyst_fetches - s0.analyst_fetches };
}

async function phaseSearch(page, label, selectedCount) {
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
  const t0 = Date.now();
  await page.getByRole("button", { name: "搜尋選擇權" }).click();
  await page.waitForFunction(
    () => /已搜尋 (\d+) \/ \1 檔/.test(document.body.innerText), null,
    { timeout: 120000 * Math.max(1, selectedCount) });
  await page.getByRole("button", { name: "搜尋選擇權" }).and(page.locator(":enabled"))
    .waitFor({ timeout: 120000 });
  await page.waitForTimeout(1000);
  phase.wall_seconds = Math.round((Date.now() - t0) / 100) / 10;
  phase.finished_tw = tw();
  page.off("request", onReq);
  page.off("response", onResp);
  const s1 = await stats(page);
  const chainLog = s1.chain_log.slice(s0.chain_log.length);
  phase.chain_log = chainLog;
  phase.chain_attempt_counts = {};
  phase.chain_source_counts = {};
  for (const c of chainLog) {
    const k = `${c.attempt}:${c.ok ? "ok" : "fail"}`;
    phase.chain_attempt_counts[k] = (phase.chain_attempt_counts[k] ?? 0) + 1;
    if (c.ok) phase.chain_source_counts[c.source] = (phase.chain_source_counts[c.source] ?? 0) + 1;
  }
  phase.cboe_errors = [...new Set(chainLog.filter((c) => !c.ok).map((c) => c.error))];
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
                       over_45s: r.ms / 1000 > SLOW_SECONDS,
                       fetch_seconds: Math.round(mine.reduce((a, c) => a + c.seconds, 0) * 100) / 100,
                       attempts: mine.map((c) => `${c.attempt}:${c.ok ? "ok" : "fail"}`),
                       source: ok?.source ?? null, contracts: ok?.contracts ?? null,
                       expiries: ok?.expiries ?? null, spot: ok?.spot ?? null,
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
  phase.failures = failures;
  phase.failure_reason_counts = failures.reduce((a, f) => ({ ...a, [f.reason]: (a[f.reason] ?? 0) + 1 }), {});
  phase.incomplete = incomplete.map((i) => ({ symbol: i.symbol, families: i.families, message: i.message }));
  phase.families_per_stock = Object.fromEntries(perSymbol.map((p) => [p.symbol, p.family_count]));
  phase.family_count_hist = perSymbol.reduce((a, p) => ({ ...a, [p.family_count]: (a[p.family_count] ?? 0) + 1 }), {});
  phase.slow_over_45s = perSymbol.filter((p) => p.over_45s).map((p) => ({ symbol: p.symbol, seconds: p.request_seconds }));
  phase.row_count = rows.length;
  phase.rows = rows.map(rowView);
  const spots = Object.fromEntries(perSymbol.filter((p) => p.spot).map((p) => [p.symbol, p.spot]));
  phase.spots = spots;
  phase.anomalies = anomalies(rows, spots);

  // 排序：畫面下拉選單（後端 sort_options）各取前 5。
  const results = page.getByRole("region", { name: "搜尋結果" });
  phase.ui_row_count = await results.locator("tbody tr[data-family]").count();
  check(`${label}：搜尋結果表列數＝API 列數（${rows.length}）`, phase.ui_row_count === rows.length);
  const select = results.locator("select");
  phase.rankings = {};
  const keyOf = { return: (r) => -r.target_return, cost: (r) => r.entry_cost,
                  max_loss: (r) => r.max_loss_per_contract };
  for (const opt of phase.sort_options) {
    await select.selectOption(opt.id);
    await page.waitForTimeout(300);
    const uiTop = await results.locator("tbody tr[data-family]").evaluateAll((trs) => trs.slice(0, 5).map((tr) => {
      const cell = (l) => tr.querySelector(`td[data-label="${l}"]`)?.textContent?.trim() ?? null;
      return { symbol: cell("標的"), strategy: cell("策略"), legs: cell("履約價"),
               cost: cell("淨成本 / 股"), max_loss: cell("最大損失 / 股"),
               target_return: cell("目標價情境報酬"), family: tr.getAttribute("data-family") };
    }));
    const apiTop = [...rows].sort((a, b) => (keyOf[opt.id](a) - keyOf[opt.id](b))
      || (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0)
      || (a.family < b.family ? -1 : a.family > b.family ? 1 : 0)).slice(0, 5).map(rowView);
    const match = uiTop.every((u, i) => u.symbol === apiTop[i]?.symbol && u.family === apiTop[i]?.family);
    check(`${label}：排序「${opt.label}」畫面前 5＝依同一欄位排序的 API 列`, match && uiTop.length === Math.min(5, rows.length),
          uiTop.map((u) => `${u.symbol}/${u.family}`));
    phase.rankings[opt.id] = { label: opt.label, ui_top5: uiTop, top5: apiTop, ui_matches: match };
  }
  await select.selectOption("return");
  info(`搜尋 ${label}`, { searched: phase.searched, searchable: phase.searchable_count,
                         failures: phase.failure_reason_counts, sources: phase.chain_source_counts,
                         slow: phase.slow_over_45s });
  phase._rows_full = rows;
  return phase;
}

async function saveRowFromUi(page, row) {
  const results = page.getByRole("region", { name: "搜尋結果" });
  const tr = results.locator(`tbody tr[data-family="${row.family}"]`)
    .filter({ has: page.locator("td.opp-symbol", { hasText: new RegExp(`^${row.symbol}$`) }) });
  const before = Number(sql("SELECT count(*) FROM scenarios"));
  await tr.getByRole("button", { name: "存成劇本" }).click();
  await page.waitForURL(/#\/s\/[^/]+$/, { timeout: 120000 });
  const id = decodeURIComponent(page.url().split("#/s/")[1]);
  await page.getByText("淨成本 / 股").first().waitFor({ timeout: 180000 });
  const detail = await waitAnalyzed(page, id);
  const text = await page.locator("body").innerText();
  const pct = (x) => `${(x * 100).toFixed(1)}%`;
  const money = (x) => `$${x.toFixed(2)}`;
  const uiOk = text.includes(row.symbol) && text.includes(pct(row.target_return))
    && text.includes(money(row.entry_cost));
  return { id, saved_tw: tw(), db_scenarios_delta: Number(sql("SELECT count(*) FROM scenarios")) - before,
           detail_page_shows_row_numbers: uiOk, detail };
}

async function waitAnalyzed(page, id) {
  for (let i = 0; i < 120; i++) {
    const d = (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
    if (d?.latest_result && d?.representative_candidate) return d;
    await page.waitForTimeout(1500);
  }
  return (await api(page, "GET", `/api/scenarios/${encodeURIComponent(id)}`)).body;
}

function championOf(detail) {
  const rc = detail.representative_candidate;
  const pool = detail.latest_result?.candidate_pool ?? {};
  const full = rc ? pool[rc.candidate_key] : null;
  return { rc, full };
}

function diff(a, b, path = "", out = [], ignore = new Set()) {
  if (ignore.has(path.split(".").pop())) return out;
  if (a === b) return out;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") {
    if (typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 1e-9) return out;
    out.push({ path, a, b });
    return out;
  }
  if (Array.isArray(a) !== Array.isArray(b)) { out.push({ path, a: "array?", b: "array?" }); return out; }
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) diff(a[k], b[k], path ? `${path}.${k}` : k, out, ignore);
  return out;
}

async function phaseCompare(page, saved, row, consensusItems) {
  const item = consensusItems.find((i) => i.symbol === row.symbol);
  const settings = (await api(page, "GET", "/api/settings")).body.opportunity_search;
  const manualReq = { symbol: row.symbol, target_price: item.mean, target_month: item.target_month,
                      strategies: settings.strategies };
  const created = await api(page, "POST", "/api/scenarios", { body: manualReq });
  const refreshed = await api(page, "POST", `/api/scenarios/${encodeURIComponent(created.body.id)}/refresh`);
  const manual = await waitAnalyzed(page, created.body.id);
  const a = saved.detail, b = manual;
  const ca = championOf(a), cb = championOf(b);
  const fields = (d, c) => ({
    symbol: d.symbol, target_price: d.target_price, target_month: d.target_month,
    strategies: d.strategies, best_return: d.best_return, spot: d.spot,
    champion_key: c.rc?.candidate_key, champion_strategy: c.rc?.strategy, expiry: c.rc?.expiry,
    legs: c.rc ? legText(c.rc.legs) : null, baseline_return: c.rc?.baseline_return,
    natural_cost: c.full?.natural_cost, max_loss_per_contract: c.full?.max_loss_per_contract,
    breakeven: c.full?.breakeven, buffer_days: c.full?.buffer_days,
    leg_quotes: c.full?.legs?.map((l) => ({ k: l.strike, t: l.option_type, side: l.side, q: l.quantity,
                                            bid: l.bid, ask: l.ask, oi: l.open_interest, vol: l.volume })),
  });
  const fa = fields(a, ca), fb = fields(b, cb);
  const fieldDiff = diff(fa, fb);
  // 整份 latest_result（去掉時間戳與 id）逐欄比對。
  const ignore = new Set(["analyzed_at", "fetched_at", "scenario_id", "id", "created_at",
                          "updated_at", "as_of_ts", "generated_at", "computed_at", "ts"]);
  const fullDiff = diff(a.latest_result, b.latest_result, "latest_result", [], ignore);
  // 劇本 vs 搜尋列
  const rowVsSaved = diff({ candidate_key: row.candidate_key, expiry: row.expiry, legs: legText(row.legs),
                            target_return: row.target_return, entry_cost: row.entry_cost,
                            max_loss_per_contract: row.max_loss_per_contract, breakeven: row.breakeven,
                            target_price: row.scenario.target_price, target_month: row.target_month },
                          { candidate_key: fa.champion_key, expiry: fa.expiry, legs: fa.legs,
                            target_return: fa.baseline_return, entry_cost: fa.natural_cost,
                            max_loss_per_contract: fa.max_loss_per_contract, breakeven: fa.breakeven,
                            target_price: fa.target_price, target_month: fa.target_month });
  // 該列家族的代表候選（劇本裡）
  const famRep = (d) => {
    const reps = d.latest_result?.representative_by_family ?? d.latest_result?.family_representatives ?? null;
    return reps;
  };
  const out = {
    row: rowView(row), saved_id: saved.id, manual_id: created.body.id,
    manual_request: manualReq, manual_create_status: created.status, manual_refresh_status: refreshed.status,
    saved_fields: fa, manual_fields: fb, saved_vs_manual_mismatches: fieldDiff,
    full_latest_result_mismatches: fullDiff.slice(0, 50), full_latest_result_mismatch_count: fullDiff.length,
    row_vs_saved_champion_mismatches: rowVsSaved,
    saved_snapshot_source: a.latest_result?.snapshot?.source ?? null,
    family_reps_present: Boolean(famRep(a)),
    detail_page_shows_row_numbers: saved.detail_page_shows_row_numbers,
  };
  check(`存成劇本 ${row.symbol} ${row.family}：與手動建立同參數劇本逐欄一致`,
        fieldDiff.length === 0, fieldDiff.slice(0, 5));
  return out;
}

async function persistenceSnapshot(page) {
  const status = (await api(page, "GET", "/api/opportunity/consensus/status")).body;
  const consensus = (await api(page, "GET", "/api/opportunity/consensus")).body;
  const list = (await api(page, "GET", "/api/scenarios")).body;
  return {
    at_tw: tw(),
    role: (await api(page, "GET", "/api/auth/status")).body?.role,
    data_as_of: status.data_as_of, progress: status.progress,
    upstream_calls_today: status.upstream_calls_today,
    consensus_status_counts: consensus.items.reduce((a, i) => ({ ...a, [i.status]: (a[i.status] ?? 0) + 1 }), {}),
    selected: consensus.items.filter((i) => i.gate.selected).map((i) => i.symbol),
    universe: consensus.universe,
    scenarios: list.map((s) => ({ id: s.id, symbol: s.symbol, target_price: s.target_price,
                                  target_month: s.target_month, best_return: s.best_return,
                                  analyzed_at: s.analyzed_at })).sort((a, b) => (a.id < b.id ? -1 : 1)),
    db: {
      consensus_snapshots: sql("SELECT count(*) FROM consensus_snapshots"),
      consensus_details: sql("SELECT count(*) FROM consensus_details"),
      consensus_refresh_state: sql("SELECT count(*) FROM consensus_refresh_state"),
      scenarios: sql("SELECT count(*) FROM scenarios"),
      results: sql("SELECT count(*) FROM results"),
    },
  };
}

async function uiFacts(page, expectSymbols = []) {
  await openOpportunity(page);
  const panel = page.getByRole("region", { name: "分析師資料" });
  const facts = panel.getByRole("list", { name: "資料狀態" });
  await facts.getByRole("listitem", { name: "資料日" }).waitFor({ timeout: 30000 });
  const sel = await uiSelected(page);
  const out = {
    標題: await panel.getByRole("heading", { name: /^分析師資料/ }).innerText(),
    資料日: await facts.getByRole("listitem", { name: "資料日" }).innerText(),
    已建立: await facts.getByRole("listitem", { name: "已建立" }).innerText(),
    入選: await facts.getByRole("listitem", { name: "入選" }).innerText(),
    入選清單: sel.symbols };
  // 劇本庫首頁：開 app 會觸發既有的 Refresh Run（背景抓鏈），不等 networkidle，
  // 等到卡片清單出現即可。
  await page.goto(`${BASE}/#/`);
  await page.waitForFunction((syms) => syms.every((x) => document.body.innerText.includes(x)),
                             expectSymbols, { timeout: 60000 }).catch(() => {});
  const body = await page.locator("body").innerText();
  return { ...out, home_body_excerpt_len: body.length, home_body: body };
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
    snapshot_rules_versions: sqlRows("SELECT snapshot->>'rules_version', count(*) FROM consensus_snapshots GROUP BY 1")
      .map(([v, n]) => ({ rules_version: v, n: Number(n) })),
  };
}

async function main() {
  if (!OUT) abort("需要 OC_402_OUT");
  mkdirSync(OUT, { recursive: true });
  if (!existsSync(join(ROOT, "dist/index.html"))) abort("找不到 dist/：先跑 npm run build");
  const tables = Number(execFileSync("psql", ["-X", "-qtA", ...pgArgs, "-d", DB, "-c",
    "SELECT count(*) FROM pg_tables WHERE schemaname='public'"], { encoding: "utf8" }).trim());
  if (tables !== 0) abort(`資料庫 ${DB} 不是空的（${tables} 張表）；本腳本只在全新的庫上跑`);
  report.started_tw = tw();
  report.dsn = { host: PG.host, port: PG.port, db: DB,
                 server_addr: sql("SELECT inet_server_addr()::text || ' / ' || current_database()") };
  report.env_db_vars_cleared = ["DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL",
                                "DATABASE_URL_POOLED", "POSTGRES_URL_NON_POOLING"];
  const tmp = mkdtempSync(join(tmpdir(), "oc-402-"));
  const cert = join(tmp, "cert.pem"), key = join(tmp, "key.pem");
  execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                           "-out", cert, "-days", "1", "-subj", "/CN=127.0.0.1"], { stdio: "ignore" });
  const serverArgs = ["--dsn", DSN, "--port", String(PORT), "--cert", cert, "--key", key];
  let server = startServer(serverArgs);
  let browser;
  let aborted = false;
  try {
    await server.ready;
    browser = await chromium.launch({
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"],
    });
    report.browser_args = ["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"];
    report.canary = await canary(browser, { write: true });
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1360, height: 900 } });
    const page = await ctx.newPage();
    check("SU 登入", (await login(page)) === "superuser");
    const saved0 = await setThresholds(page, 20, 10);
    check("設定頁：母體＝大型股樣本、門檻 20／10", saved0.universe_id === "sample-large-cap"
          && saved0.percentile_max === 20 && saved0.dispersion_max === 10, saved0);

    report.phases.c1_consensus = await phaseConsensusBuild(page); save();
    report.phases.c2_gates = await phaseGates(page); save();

    // 3／4：20／10 搜尋（畫面），存第一列
    const g = report.phases.c2_gates.settings;
    const sel2010 = g[0].selected_count;
    const search2010 = await phaseSearch(page, "20/10", sel2010);
    const rows2010 = search2010._rows_full; delete search2010._rows_full;
    report.phases.c3_search_20_10 = search2010; save();
    const consensusItems = (await api(page, "GET", "/api/opportunity/consensus")).body.items;
    const rowA = [...rows2010].sort((a, b) => b.target_return - a.target_return)[0];
    const savedA = await saveRowFromUi(page, rowA);

    // 50／20：設定頁改門檻 → 搜尋（畫面）→ 存第二列（不同 symbol）
    await setThresholds(page, 50, 20);
    const sel5020 = (await uiSelected(page)).symbols.length;
    const search5020 = await phaseSearch(page, "50/20", sel5020);
    const rows5020 = search5020._rows_full; delete search5020._rows_full;
    report.phases.c3_search_50_20 = search5020; save();
    const consensusItems5020 = (await api(page, "GET", "/api/opportunity/consensus")).body.items;
    const ranked = [...rows5020].sort((a, b) => b.target_return - a.target_return);
    const rowB = ranked.find((r) => r.symbol !== rowA.symbol && r.family !== rowA.family)
      ?? ranked.find((r) => r.symbol !== rowA.symbol);
    const savedB = await saveRowFromUi(page, rowB);

    report.phases.c5_save_compare = [
      await phaseCompare(page, savedA, rowA, consensusItems),
      await phaseCompare(page, savedB, rowB, consensusItems5020),
    ];
    save();

    // 6：重新整理＋重啟後端
    const before = await persistenceSnapshot(page);
    await page.goto(`${BASE}/#/opportunity`);
    await page.reload();
    const afterReload = await persistenceSnapshot(page);
    const expectSymbols = [...new Set(before.scenarios.filter((x) => x.symbol !== "ZZCANARY")
      .map((x) => x.symbol))];
    const uiAfterReload = await uiFacts(page, expectSymbols);
    const scenarioSymbolsOnHome = before.scenarios.filter((s) => s.symbol !== "ZZCANARY")
      .map((s) => s.symbol).filter((sym) => uiAfterReload.home_body.includes(sym));
    delete uiAfterReload.home_body;
    server.child.kill("SIGTERM");
    await server.exited;
    const restartedAt = tw();
    secrets.OC_VERIFY_NONCE = randomBytes(12).toString("hex");
    server = startServer(serverArgs);
    await server.ready;
    const canary2 = await canary(browser, { write: false });
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(3000);
    const afterRestart = await persistenceSnapshot(page);
    const uiAfterRestart = await uiFacts(page, expectSymbols);
    const scenarioSymbolsOnHomeAfterRestart = expectSymbols.filter((sym) => uiAfterRestart.home_body.includes(sym));
    delete uiAfterRestart.home_body;
    const reupdate = await api(page, "POST", "/api/opportunity/consensus/update", { body: {} });
    const sAfter = await stats(page);
    // 劇本比對 id／symbol／目標價／目標月／best_return；`results` 列數與 analyzed_at
    // 另外記錄（開 app 的既有刷新時機可能替從沒分析過的金絲雀劇本再試一次）。
    const key = (x) => JSON.stringify({ d: x.data_as_of, p: x.progress, c: x.consensus_status_counts,
      sel: x.selected, s: x.scenarios.map((sc) => [sc.id, sc.symbol, sc.target_price,
                                                   sc.target_month, sc.best_return]),
      db: [x.db.consensus_snapshots, x.db.consensus_details, x.db.consensus_refresh_state,
           x.db.scenarios] });
    const same = (x, y) => key(x) === key(y);
    report.phases.c6_persistence = {
      before, after_reload: afterReload, ui_after_reload: uiAfterReload,
      scenario_symbols_visible_on_home_after_reload: scenarioSymbolsOnHome,
      restarted_at_tw: restartedAt, canary_after_restart: canary2,
      after_restart: afterRestart, ui_after_restart: uiAfterRestart,
      scenario_symbols_visible_on_home_after_restart: scenarioSymbolsOnHomeAfterRestart,
      update_after_restart: { status: reupdate.status, processed: reupdate.body?.processed,
                              skipped: reupdate.body?.skipped?.length,
                              analyst_fetches_new_process: sAfter.analyst_fetches,
                              analyst_http_requests_new_process: sAfter.analyst_http_requests },
    };
    check("重新整理後：共識快取（資料日、各狀態檔數、入選）與劇本不變", same(before, afterReload));
    check("重啟後端（同一資料庫）後：仍是 SU、共識快取與劇本不變",
          afterRestart.role === "superuser" && same(before, afterRestart));
    check("重啟後再按更新：同一天已成功的不重抓（0 次分析師抓取）",
          reupdate.status === 200 && sAfter.analyst_fetches === 0,
          { processed: reupdate.body?.processed, fetches: sAfter.analyst_fetches });

    // 7：fixture
    const fx = fixtureEvidence();
    const allChain = [...report.phases.c3_search_20_10.chain_log, ...report.phases.c3_search_50_20.chain_log];
    report.phases.c7_no_fixture = {
      api_source: report.phases.c1_consensus.source,
      db: fx,
      chain_sources_all_searches: allChain.filter((c) => c.ok).reduce((a, c) => ({ ...a, [c.source]: (a[c.source] ?? 0) + 1 }), {}),
      server_blocked_connections: sAfter.blocked_connections,
      page_has_fixture_label: (await page.getByText("測試資料，非真實市場資料").count()) > 0,
    };
    check("沒有 fixture：DB 共識列全部 yahoo-udh 且 is_fixture=false",
          fx.consensus_snapshots_by_source.length === 1
          && fx.consensus_snapshots_by_source[0].source === "yahoo-udh"
          && fx.consensus_snapshots_by_source[0].is_fixture === "f", fx.consensus_snapshots_by_source);
    await ctx.close();
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
    report.finished_tw = tw();
    const failed = checks.filter((r) => !r.ok);
    report.summary = { checks: checks.length, passed: checks.length - failed.length, failed: failed.length };
    save();
    console.log(JSON.stringify(report.summary, null, 2));
    process.exit(aborted ? 3 : failed.length ? 1 : 0);
  }
}

await main();
