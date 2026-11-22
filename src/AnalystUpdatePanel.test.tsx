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
import OpportunityPage from "./OpportunityPage";
import type {
  ConsensusRefreshStatusResponse,
  ConsensusUpdateResponse,
  OpportunityConsensusResponse,
} from "./api";
import type { Role } from "./superuser";

const CONSENSUS = consensusSample as unknown as OpportunityConsensusResponse;
const STATUS = statusSample as unknown as ConsensusRefreshStatusResponse;
const UPDATE = updateSample as unknown as ConsensusUpdateResponse;

type Reply = { status: number; body: unknown };

function res(status: number, body: unknown): Response {
  return { ok: status < 400, status, headers: new Headers(),
           json: async () => body } as Response;
}

/** `update`／`status` 依序回下一個（最後一個重複）。 */
function mockApi({
  role = "superuser" as Role,
  status = [{ status: 200, body: STATUS }] as Reply[],
  update = [{ status: 200, body: { ...UPDATE, remaining: [] } }] as Reply[],
} = {}) {
  let u = 0;
  let s = 0;
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
    if (path.startsWith("/api/opportunity/consensus")) return res(200, CONSENSUS);
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
  await within(panel).findByText(/資料日/);
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
    expect(within(panel).getByText("資料日 2026-09-28")).toBeInTheDocument();
    expect(within(panel).getByText("今日 已完成 24／57 檔、失敗 1 檔")).toBeInTheDocument();
    expect(within(panel).getByText("今日上游呼叫 25／400 次")).toBeInTheDocument();
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
    await within(panel).findByText(/資料日/);
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

  it("重試用完：停用並說明下一個交易日再試", async () => {
    const { panel } = await renderPanel({ status: [{ status: 200, body: withSymbol("GGG", {
      state: "exhausted", retries_today: 3,
      next_retry_at: "2026-09-29T04:00:00+00:00" }) }] });
    const item = within(panel).getByRole("listitem", { name: "GGG" });
    expect(within(item).getByRole("button", { name: "重試 GGG" })).toBeDisabled();
    expect(item).toHaveTextContent("今日已重試 3 次");
    expect(item).toHaveTextContent("今天的重試次數已用完，下一個交易日自動再試");
  });
});
