/**
 * LIVE-T3（#398）：機會搜尋頁的「分析師資料」區塊。狀態與更新回應直接載入
 * `contracts/` 的後端樣本（與後端測試同一份），只覆寫情境需要的欄位。
 *
 * 守的事：「更新分析師資料」依 `remaining` 自動續跑、即時顯示進度、完成後
 * 重讀狀態與共識清單；每日上限停下並照實說；「重試」真的送出那一檔；冷卻中
 * 停用並顯示剩餘時間與原因、時間到可以按；後端拒絕照實顯示；Normal 看不到。
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import consensusSample from "../contracts/opportunity_consensus_sample.json";
import statusSample from "../contracts/opportunity_consensus_status_sample.json";
import updateSample from "../contracts/opportunity_consensus_update_sample.json";
import searchSample from "../contracts/opportunity_search_sample.json";
import OpportunityPage from "./OpportunityPage";
import type {
  ConsensusRefreshStatusResponse,
  ConsensusUpdateResponse,
  OpportunityConsensusResponse,
} from "./api";
import type { Role } from "./superuser";

const CONSENSUS = consensusSample as unknown as OpportunityConsensusResponse;
const STATUS = statusSample as unknown as ConsensusRefreshStatusResponse;
/** 排程有授權成功的執行紀錄（V2-02／#403）——只有這時才說「明天自動更新」。 */
const CRON_RAN = { runs_today: 2, symbols_today: 56, last_run_day: "2026-09-28", lookback_days: 30 };
const UPDATE = updateSample as unknown as ConsensusUpdateResponse;

type Reply = { status: number; body: unknown };

function res(status: number, body: unknown): Response {
  return { ok: status < 400, status, headers: new Headers(),
           json: async () => body } as Response;
}

/** `update`／`status`／`consensus` 依序回下一個（最後一個重複）。 */
function mockApi({
  role = "superuser" as Role,
  status = [{ status: 200, body: STATUS }] as Reply[],
  update = [{ status: 200, body: { ...UPDATE, remaining: [] } }] as Reply[],
  consensus = [CONSENSUS] as OpportunityConsensusResponse[],
} = {}) {
  let u = 0;
  let s = 0;
  let c = 0;
  const spy = vi.fn(async (url: string, _init?: RequestInit) => {
    const path = String(url);
    if (path.startsWith("/api/auth/status")) return res(200, { role });
    if (path.startsWith("/api/opportunity/consensus/status")) {
      const r = status[Math.min(s++, status.length - 1)];
      return res(r.status, r.body);
    }
    if (path.startsWith("/api/opportunity/consensus/update")) {
      const r = update[Math.min(u++, update.length - 1)];
      return res(r.status, r.body);
    }
    if (path.startsWith("/api/opportunity/consensus")) {
      return res(200, consensus[Math.min(c++, consensus.length - 1)]);
    }
    if (path.startsWith("/api/opportunity/search")) {
      return res(200, { ...searchSample, remaining: [] });
    }
    return res(404, { detail: "not mocked" });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const callsTo = (spy: ReturnType<typeof mockApi>, path: string) =>
  spy.mock.calls.filter(([url]) => String(url) === path);
const updateBodies = (spy: ReturnType<typeof mockApi>) =>
  callsTo(spy, "/api/opportunity/consensus/update")
    .map(([, init]) => JSON.parse(String(init?.body)));

const noSave = () => Promise.reject(new Error("unused"));

async function renderPanel(opts: Parameters<typeof mockApi>[0] = {}) {
  const spy = mockApi(opts);
  render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
  const panel = await screen.findByRole("region", { name: "分析師資料" });
  await within(panel).findByRole("listitem", { name: "今日更新" });
  return { spy, panel };
}

function withSymbol(symbol: string, over: object): ConsensusRefreshStatusResponse {
  return { ...STATUS,
           symbols: STATUS.symbols.map((x) => (x.symbol === symbol ? { ...x, ...over } : x)) };
}

beforeEach(() => {
  window.location.hash = "#/opportunity";
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("分析師資料：權限", () => {
  it("Normal：看不到更新／重試按鈕，也不打狀態或更新端點", async () => {
    const spy = mockApi({ role: "normal" });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    await waitFor(() => expect(window.location.hash).toBe("#/"));
    expect(screen.queryByRole("button", { name: "更新分析師資料" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重試/ })).not.toBeInTheDocument();
    expect(callsTo(spy, "/api/opportunity/consensus/status")).toEqual([]);
    expect(callsTo(spy, "/api/opportunity/consensus/update")).toEqual([]);
  });

  it.each(["superuser", "superadmin"] as const)("%s 看得到狀態與更新按鈕", async (role) => {
    const { panel } = await renderPanel({ role });
    const facts = within(panel).getByRole("list", { name: "資料狀態" });
    expect(within(facts).getByRole("listitem", { name: "資料日期" })).toHaveTextContent("2026-09-28");
    expect(within(facts).getByRole("listitem", { name: "今日更新" }))
      .toHaveTextContent("已完成 24／57 檔、失敗 1 檔");
    expect(within(facts).getByRole("listitem", { name: "今日上游呼叫" }))
      .toHaveTextContent("25／900 次");
    // 契約樣本沒有任何授權成功的排程執行：照實說排程尚未執行（V2-02／#403）。
    expect(within(facts).getByRole("listitem", { name: "排程" }))
      .toHaveTextContent("排程尚未執行（近 30 天沒有紀錄）");
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeEnabled();
  });
});

describe("分析師資料：更新（自動續跑）", () => {
  it("依 remaining 續跑到完，顯示進度與完成，並重讀狀態與共識清單", async () => {
    const first = { ...UPDATE, progress: { ...UPDATE.progress, done: 25, failed: 0 } };
    let finish!: (r: Reply) => void;
    const second = new Promise<Reply>((resolve) => { finish = resolve; });
    const spy = mockApi();
    const replies: (Reply | Promise<Reply>)[] = [{ status: 200, body: first }, second];
    let n = 0;
    spy.mockImplementation(async (url: string) => {
      const path = String(url);
      if (path.startsWith("/api/auth/status")) return res(200, { role: "superuser" });
      if (path.startsWith("/api/opportunity/consensus/status")) return res(200, STATUS);
      if (path.startsWith("/api/opportunity/consensus/update")) {
        const r = await replies[Math.min(n++, replies.length - 1)];
        return res(r.status, r.body);
      }
      return res(200, CONSENSUS);
    });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    const panel = await screen.findByRole("region", { name: "分析師資料" });
    await within(panel).findByRole("listitem", { name: "今日更新" });
    const consensusBefore = callsTo(spy, "/api/opportunity/consensus").length;

    await userEvent.click(within(panel).getByRole("button", { name: "更新分析師資料" }));
    expect(await within(panel).findByText("已完成 25／57 檔、失敗 0 檔")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "更新中……" })).toBeDisabled();

    finish({ status: 200, body: { ...UPDATE, remaining: [],
                                  progress: { ...UPDATE.progress, done: 56, failed: 1,
                                              pending: 0 } } });
    expect(await within(panel).findByText("更新完成：已完成 56／57 檔、失敗 1 檔"))
      .toBeInTheDocument();
    expect(updateBodies(spy)).toEqual([{}, {}]);
    await waitFor(() => {
      expect(callsTo(spy, "/api/opportunity/consensus/status").length).toBe(2);
      expect(callsTo(spy, "/api/opportunity/consensus").length).toBe(consensusBefore + 1);
    });
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeEnabled();
  });

  it("每日上限：停下、照實顯示原因，不再續跑", async () => {
    const { spy, panel } = await renderPanel({ update: [{ status: 200, body: {
      ...UPDATE, stopped_reason: "daily_cap",
      message: "今日分析師資料的上游呼叫已達每日上限，下一個交易日自動恢復" } }] });
    await userEvent.click(within(panel).getByRole("button", { name: "更新分析師資料" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "已停止（已完成 24／57 檔、失敗 1 檔）：今日分析師資料的上游呼叫已達每日上限");
    expect(updateBodies(spy)).toEqual([{}]);
  });

  it("來源限流（429）：立刻停下、照實顯示原因，不再續跑", async () => {
    const { spy, panel } = await renderPanel({ update: [{ status: 200, body: {
      ...UPDATE, stopped_reason: "rate_limited", rate_limited_until: "2099-01-01T00:00:00+00:00",
      message: "資料來源回應限流（429），所有分析師資料更新暫停到冷卻結束，期間不會再呼叫來源" } }] });
    await userEvent.click(within(panel).getByRole("button", { name: "更新分析師資料" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "已停止（已完成 24／57 檔、失敗 1 檔）：資料來源回應限流（429）");
    expect(updateBodies(spy)).toEqual([{}]);
  });

  it("另一個更新正在執行（排程或其他 SU）：停下、照實說明，不再續跑", async () => {
    const { spy, panel } = await renderPanel({ update: [{ status: 200, body: {
      ...UPDATE, processed: 0, processed_symbols: [], remaining: [],
      stopped_reason: "another_run_active",
      message: "另一個分析師資料更新（排程或其他 SU）正在執行，這次沒有更新；請稍後再按「繼續更新」" } }] });
    await userEvent.click(within(panel).getByRole("button", { name: "更新分析師資料" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "另一個分析師資料更新（排程或其他 SU）正在執行");
    expect(updateBodies(spy)).toEqual([{}]);
  });

  it("後端拒絕：顯示後端訊息", async () => {
    const { panel } = await renderPanel({ update: [{ status: 409,
      body: { detail: "尚未設定分析師資料來源" } }] });
    await userEvent.click(within(panel).getByRole("button", { name: "更新分析師資料" }));
    expect(await within(panel).findByRole("alert"))
      .toHaveTextContent("更新失敗：尚未設定分析師資料來源");
  });
});

describe("分析師資料：重試", () => {
  it("冷卻中停用並顯示剩餘時間與原因；時間到可以按，按下真的送出那一檔", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-09-28T13:00:00Z"));   // GGG 13:08:20 才能重試
    const after = withSymbol("GGG", { state: "done", error: null, retries_today: 1,
                                      next_retry_at: null, as_of: "2026-09-28" });
    const { spy, panel } = await renderPanel({
      status: [{ status: 200, body: STATUS }, { status: 200, body: after }],
      update: [{ status: 200, body: { ...UPDATE, processed_symbols: ["GGG"],
                                      remaining: [] } }] });
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    const button = within(item).getByRole("button", { name: "重試 GGG" });
    expect(button).toBeDisabled();
    expect(item).toHaveTextContent("逾時（測試資料模擬上游失敗）");
    expect(item).toHaveTextContent("上次失敗，冷卻中，還要約 8 分 20 秒才能重試");

    act(() => { vi.advanceTimersByTime(501_000); });
    await waitFor(() => expect(button).toBeEnabled());
    expect(item).not.toHaveTextContent("冷卻中");

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(button);
    await waitFor(() => expect(updateBodies(spy)).toEqual([{ symbols: ["GGG"] }]));
    await waitFor(() =>
      expect(within(panel).queryByRole("listitem", { name: "GGG" })).not.toBeInTheDocument());
  });

  it("後端拒絕重試（例如每日上限）：在那一檔下照實顯示", async () => {
    const ready = withSymbol("GGG", { state: "retry_ready", next_retry_at: null,
                                      retryable_now: true });
    const { panel } = await renderPanel({
      status: [{ status: 200, body: ready }],
      update: [{ status: 429, body: { detail: {
        stage: "consensus_daily_cap",
        message: "今日分析師資料的上游呼叫已達每日上限，下一個交易日自動恢復" } } }] });
    await userEvent.click(within(panel).getByRole("button", { name: "重試 GGG" }));
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(await within(item).findByRole("alert"))
      .toHaveTextContent("今日分析師資料的上游呼叫已達每日上限");
  });

  it("重試用完：停用並說明明天自動更新", async () => {
    const { panel } = await renderPanel({ status: [{ status: 200, body: { ...withSymbol("GGG", {
      state: "exhausted", retries_today: 3,
      next_retry_at: "2026-09-29T04:00:00+00:00" }), cron: CRON_RAN } }] });
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(within(item).getByRole("button", { name: "重試 GGG" })).toBeDisabled();
    expect(item).toHaveTextContent("今日已重試 3 次");
    expect(item).toHaveTextContent("今天的重試次數已用完，明天自動更新");   // 美東 9/28 是週一
    expect(fact(panel, "排程")).toHaveTextContent("今天已執行 2 次（處理 56 檔）");
  });

  it("排程尚未執行（V2-02／#403）：重試用完時不說會自動更新", async () => {
    const { panel } = await renderPanel({ status: [{ status: 200, body: withSymbol("GGG", {
      state: "exhausted", retries_today: 3,
      next_retry_at: "2026-09-29T04:00:00+00:00" }) }] });
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(item).toHaveTextContent(
      "今天的重試次數已用完，排程尚未執行，不會自動更新，明天請手動「繼續更新」");
    expect(item).not.toHaveTextContent("明天自動更新");
  });
});

// ---------- LIVE-T5（#401）：資料狀態與三種狀態的畫面與按鈕 ----------

/** 今天全部更新成功、沒有失敗的狀態。 */
const ALL_DONE: ConsensusRefreshStatusResponse = {
  ...STATUS, upstream_calls_today: 57,
  progress: { total: 57, done: 57, failed: 0, pending: 0, in_progress: 0 },
  symbols: STATUS.symbols.map((x) => ({ ...x, state: "done", error: null, next_retry_at: null,
                                        retryable_now: false, as_of: "2026-09-28" })),
};
const REAL: OpportunityConsensusResponse = {
  ...CONSENSUS, source: { configured: true, name: "yahoo-udh", is_fixture: false },
};
/** 掃描範圍 7 檔中 `symbols` 這幾檔還沒建立（後端 `not_built` 的同一判準）。 */
function building(base: OpportunityConsensusResponse, symbols: string[]): OpportunityConsensusResponse {
  const items = base.items.map((i) => symbols.includes(i.symbol)
    ? { ...i, status: "no_data" as const, mean: null, dispersion: null, percentile: null,
        n_analysts: 0, history_points: 0, as_of: null, reasons: ["no_data: 尚未更新"],
        gate: { first: false, second: false, selected: false, reasons: [] } }
    : i);
  return { ...base, items, universe: { ...base.universe, not_built: symbols.length } };
}
const phaseTag = (panel: HTMLElement) =>
  within(panel).getByRole("heading", { name: /^分析師資料/ });
const fact = (panel: HTMLElement, name: string) =>
  within(within(panel).getByRole("list", { name: "資料狀態" })).getByRole("listitem", { name });

describe("資料狀態（LIVE-T5／#401）", () => {
  it("就緒：顯示真實來源、資料日期、已建立／掃描範圍、符合條件檔數；直接「搜尋選擇權」會真的搜尋", async () => {
    const { spy, panel } = await renderPanel({ consensus: [REAL],
                                               status: [{ status: 200, body: ALL_DONE }] });
    expect(phaseTag(panel)).toHaveTextContent("就緒");
    expect(fact(panel, "資料來源")).toHaveTextContent("真實分析師資料");
    expect(fact(panel, "資料日期")).toHaveTextContent("2026-09-28");
    expect(fact(panel, "已建立")).toHaveTextContent("6／7 檔");   // GGG 抓取失敗不算
    expect(fact(panel, "符合條件")).toHaveTextContent("2 檔");
    expect(within(panel).getByRole("status"))
      .toHaveTextContent("資料已就緒，可以直接用下方的「搜尋選擇權」搜尋符合條件的股票。");
    expect(screen.queryByText("測試資料，非真實市場資料")).not.toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "搜尋選擇權" }));
    expect(await screen.findByRole("region", { name: "搜尋結果" })).toBeInTheDocument();
    expect(callsTo(spy, "/api/opportunity/search")).toHaveLength(1);
  });

  it("測試資料：資料來源寫明測試資料，頁首常駐標示", async () => {
    const { panel } = await renderPanel({ status: [{ status: 200, body: ALL_DONE }] });
    expect(fact(panel, "資料來源")).toHaveTextContent("測試資料（非真實市場資料）");
    expect(screen.getByRole("banner", { name: "機會搜尋頁首" }))
      .toHaveTextContent("測試資料，非真實市場資料");
  });

  it("建立中（一檔都沒建）：「開始建立」真的送出更新，建好後變成就緒、可以搜尋", async () => {
    const empty = building(REAL, REAL.items.map((i) => i.symbol));
    const { spy, panel } = await renderPanel({
      consensus: [empty, REAL],
      status: [{ status: 200, body: { ...STATUS, symbols: [], progress:
        { total: 7, done: 0, failed: 0, pending: 7, in_progress: 0 }, upstream_calls_today: 0 } },
               { status: 200, body: ALL_DONE }] });
    expect(phaseTag(panel)).toHaveTextContent("建立中");
    expect(fact(panel, "已建立")).toHaveTextContent("0／7 檔");
    expect(within(panel).getByRole("status")).toHaveTextContent("掃描股票範圍內 7 檔都還沒建立");
    expect(screen.getByRole("button", { name: "搜尋選擇權" })).toBeDisabled();

    await userEvent.click(within(panel).getByRole("button", { name: "開始建立" }));
    await waitFor(() => expect(phaseTag(panel)).toHaveTextContent("就緒"));
    expect(updateBodies(spy)).toEqual([{}]);
    expect(fact(panel, "已建立")).toHaveTextContent("6／7 檔");
    expect(screen.getByRole("button", { name: "搜尋選擇權" })).toBeEnabled();
  });

  it("建立中（部分建立）：顯示進度與「繼續更新」，依 remaining 續跑並即時顯示進度", async () => {
    const partial = building(REAL, ["BBB", "CCC"]);
    let finish!: (r: Reply) => void;
    const second = new Promise<Reply>((resolve) => { finish = resolve; });
    const spy = mockApi({ consensus: [partial, REAL] });
    const replies: (Reply | Promise<Reply>)[] = [
      { status: 200, body: { ...UPDATE, remaining: ["CCC"],
                             progress: { total: 7, done: 5, failed: 1, pending: 1, in_progress: 0 } } },
      second];
    let n = 0;
    const base = spy.getMockImplementation()!;
    spy.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).startsWith("/api/opportunity/consensus/update")) {
        const r = await replies[Math.min(n++, replies.length - 1)];
        return res(r.status, r.body);
      }
      return base(url, init);
    });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    const panel = await screen.findByRole("region", { name: "分析師資料" });
    await within(panel).findByRole("listitem", { name: "今日更新" });
    expect(phaseTag(panel)).toHaveTextContent("建立中");
    expect(fact(panel, "已建立")).toHaveTextContent("4／7 檔");
    expect(within(panel).getByRole("status")).toHaveTextContent(
      "資料建立中：已建立 4／7 檔。按「繼續更新」接著建立；已建立且符合條件的股票現在就可以搜尋。");
    // 已建立且符合條件的股票（AAA、EEE）照常可以搜尋。
    expect(screen.getByRole("button", { name: "搜尋選擇權" })).toBeEnabled();

    await userEvent.click(within(panel).getByRole("button", { name: "繼續更新" }));
    expect(await within(panel).findByText("已完成 5／7 檔、失敗 1 檔")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "更新中……" })).toBeDisabled();
    finish({ status: 200, body: { ...UPDATE, remaining: [],
                                  progress: { total: 7, done: 6, failed: 1, pending: 0, in_progress: 0 } } });
    expect(await within(panel).findByText("更新完成：已完成 6／7 檔、失敗 1 檔")).toBeInTheDocument();
    expect(updateBodies(spy)).toEqual([{}, {}]);
  });

  it("失敗（冷卻中）：狀態說幾檔失敗，重試停用並顯示剩餘時間；更新鈕仍可按", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-09-28T13:00:00Z"));
    const { panel } = await renderPanel({ consensus: [REAL] });
    expect(phaseTag(panel)).toHaveTextContent("更新失敗");
    expect(within(panel).getByRole("status"))
      .toHaveTextContent("1 檔更新失敗：原因與重試方式列在下方。其餘股票照常可以搜尋。");
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(item).toHaveTextContent("逾時（測試資料模擬上游失敗）");
    expect(within(item).getByRole("button", { name: "重試 GGG" })).toBeDisabled();
    expect(item).toHaveTextContent("還要約 8 分 20 秒才能重試");
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "搜尋選擇權" })).toBeEnabled();
  });

  it("已達今日上限：更新與重試都停用，說明明天自動更新，不送任何更新請求", async () => {
    const capped = withSymbol("GGG", { state: "retry_ready", next_retry_at: null,
                                       retryable_now: true });
    const { spy, panel } = await renderPanel({ consensus: [REAL], status: [{ status: 200,
      body: { ...capped, upstream_calls_today: 400, daily_cap: 400, cron: CRON_RAN } }] });
    expect(phaseTag(panel)).toHaveTextContent("已達今日上限");
    expect(within(panel).getByRole("status")).toHaveTextContent(
      "今日上游呼叫已達每日上限（400／400 次），今天不能再更新或重試，明天自動更新。");
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeDisabled();
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(within(item).getByRole("button", { name: "重試 GGG" })).toBeDisabled();
    expect(item).toHaveTextContent("今日上游呼叫已達每日上限，明天自動更新");
    expect(updateBodies(spy)).toEqual([]);
    // 已建立的資料照常可以搜尋。
    expect(screen.getByRole("button", { name: "搜尋選擇權" })).toBeEnabled();
  });

  it("來源限流（429）暫停中：更新與重試都停用，說明還要等多久，不送更新請求", async () => {
    const paused = withSymbol("GGG", { state: "retry_ready", next_retry_at: null,
                                       retryable_now: true });
    const until = new Date(Date.now() + 20 * 60_000).toISOString();
    const { spy, panel } = await renderPanel({ consensus: [REAL], status: [{ status: 200,
      body: { ...paused, rate_limited_until: until } }] });
    expect(phaseTag(panel)).toHaveTextContent("來源限流中");
    expect(within(panel).getByRole("status")).toHaveTextContent("資料來源限流（429）");
    expect(within(panel).getByRole("button", { name: "更新分析師資料" })).toBeDisabled();
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(within(item).getByRole("button", { name: "重試 GGG" })).toBeDisabled();
    expect(updateBodies(spy)).toEqual([]);
  });

  it("超出每日更新範圍：一句話說明，已建立只算範圍內，不停在建立中", async () => {
    const outside = building(REAL, ["FFF"]);
    const consensus = { ...outside, universe: { ...outside.universe, not_built: 0,
                                                out_of_scope: 1, out_of_scope_symbols: ["FFF"] } };
    const { panel } = await renderPanel({ consensus: [consensus],
                                          status: [{ status: 200, body: ALL_DONE }] });
    expect(phaseTag(panel)).toHaveTextContent("就緒");
    expect(within(panel).getByText("1 檔超出每日更新範圍，不會更新")).toBeInTheDocument();
    expect(fact(panel, "已建立")).toHaveTextContent("5／6 檔");   // FFF 不在範圍、GGG 失敗
    expect(screen.queryByText(/資料建立中/)).not.toBeInTheDocument();
  });

  it("已達今日上限且當天是美東週五：說下週一自動更新", async () => {
    const { panel } = await renderPanel({ consensus: [REAL], status: [{ status: 200,
      body: { ...STATUS, today: "2026-09-25", upstream_calls_today: 400, daily_cap: 400,
              cron: CRON_RAN } }] });
    expect(within(panel).getByRole("status")).toHaveTextContent("下週一自動更新");
  });

  it("緊急關閉：說明來源已關閉，沒有任何更新、重試或搜尋按鈕，也不打狀態端點", async () => {
    const off: OpportunityConsensusResponse = {
      ...CONSENSUS, source: { configured: false, name: null, is_fixture: false }, items: [],
      universe: { ...CONSENSUS.universe, with_data: 0, insufficient: 0, not_built: 0, as_of: null },
      message: "尚未設定分析師資料來源" };
    const spy = mockApi({ consensus: [off] });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    expect(await screen.findByRole("heading", { name: "分析師資料來源已關閉" })).toBeInTheDocument();
    expect(screen.getByText(/緊急關閉開關生效中/)).toBeInTheDocument();
    expect(screen.queryByText(/尚未設定/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(callsTo(spy, "/api/opportunity/consensus/status")).toEqual([]);
  });
});

// ---------- V2-01（#404）：資料狀態顯示目前使用的掃描股票範圍 ----------

describe("資料狀態：掃描股票範圍（V2-01／#404）", () => {
  it("自訂清單：顯示範圍名稱，沒有版本日期", async () => {
    const { panel } = await renderPanel();
    expect(fact(panel, "掃描股票範圍")).toHaveTextContent(/^掃描股票範圍自訂清單$/);
  });

  it("S&P 500 成分股：顯示名稱與清單版本日期", async () => {
    const sp500: OpportunityConsensusResponse = {
      ...CONSENSUS,
      universe: { ...CONSENSUS.universe, id: "sp500", label: "S&P 500 成分股",
                  version_date: "2026-11-08" },
    };
    const { panel } = await renderPanel({ consensus: [sp500] });
    expect(fact(panel, "掃描股票範圍"))
      .toHaveTextContent("S&P 500 成分股（版本 2026-11-08）");
  });
});
