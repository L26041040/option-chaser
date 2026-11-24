/**
 * OS-05（#394）：機會搜尋頁。共識清單與搜尋回應直接載入 `contracts/` 的
 * 後端樣本（與後端測試同一份），只在續跑／失敗情境覆寫測試在意的欄位。
 *
 * 守的事：SU/SA 才看得到（Normal 導回首頁、不打機會搜尋端點）；來源未設定
 * 時沒有能按的搜尋；測試資料標示常駐頁首；搜尋依 `remaining` 自動續跑、
 * 逐檔出現、合併不重複；「停止」真的不再續跑、之後能接著跑；failures／
 * 熔斷／409 照實顯示後端訊息；排序切換不重新搜尋；「存成劇本」原封不動
 * 送 `scenario`、成功才導到詳細頁、額度失敗顯示既有訊息。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import consensusSample from "../contracts/opportunity_consensus_sample.json";
import detailSample from "../contracts/opportunity_detail_sample.json";
import statusSample from "../contracts/opportunity_consensus_status_sample.json";
import searchSample from "../contracts/opportunity_search_sample.json";
import OpportunityPage from "./OpportunityPage";
import {
  ApiError,
  type ConsensusRefreshStatusResponse,
  type OpportunityConsensusResponse,
  type OpportunitySearchResponse,
} from "./api";
import type { Role } from "./superuser";

const CONSENSUS = consensusSample as unknown as OpportunityConsensusResponse;
const SEARCH = searchSample as unknown as OpportunitySearchResponse;
const STATUS = statusSample as unknown as ConsensusRefreshStatusResponse;

const NOT_CONFIGURED: OpportunityConsensusResponse = {
  ...CONSENSUS,
  source: { configured: false, name: null, is_fixture: false },
  universe: { ...CONSENSUS.universe, with_data: 0, insufficient: 0,
              coverage: { complete: 0, partial: 0, unknown: 0 }, as_of: null },
  items: [],
  message: "尚未設定分析師資料來源",
};

type Reply = { status: number; body: unknown } | Promise<{ status: number; body: unknown }>;

function res(status: number, body: unknown): Response {
  return { ok: status < 400, status, headers: new Headers(),
           json: async () => body } as Response;
}

/** `search` 依序回下一個（最後一個重複）。 */
function mockApi({
  role = "superuser" as Role,
  consensus = { status: 200, body: CONSENSUS } as Reply,
  search = [{ status: 200, body: SEARCH }] as Reply[],
} = {}) {
  let i = 0;
  const spy = vi.fn(async (url: string, _init?: RequestInit) => {
    const u = String(url);
    if (u.startsWith("/api/auth/status")) return res(200, { role });
    if (u.startsWith("/api/opportunity/consensus-detail/")) {
      const symbol = decodeURIComponent(u.split("/").pop() ?? "");
      return res(200, { ...detailSample, symbol,
                        item: { ...detailSample.item, symbol } });
    }
    // LIVE-T3（#398）的分析師資料區塊：本檔不測它（見 AnalystUpdatePanel.test.tsx）。
    if (u.startsWith("/api/opportunity/consensus/status")) return res(200, STATUS);
    if (u.startsWith("/api/opportunity/consensus")) {
      const r = await consensus;
      return res(r.status, r.body);
    }
    if (u.startsWith("/api/opportunity/search")) {
      const r = await search[Math.min(i, search.length - 1)];
      i += 1;
      return res(r.status, r.body);
    }
    return res(404, { detail: "not mocked" });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const callsTo = (spy: ReturnType<typeof mockApi>, path: string) =>
  spy.mock.calls.filter(([u]) => String(u).startsWith(path));
const searchBodies = (spy: ReturnType<typeof mockApi>) =>
  callsTo(spy, "/api/opportunity/search").map(([, init]) => JSON.parse(String(init?.body)));

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

const noSave = () => Promise.reject(new Error("unused"));

beforeEach(() => {
  window.location.hash = "#/opportunity";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function renderReady(opts: Parameters<typeof mockApi>[0] = {},
                           onSave = vi.fn(noSave)) {
  const spy = mockApi(opts);
  render(<OpportunityPage onSaveAsScenario={onSave} />);
  await screen.findByRole("heading", { name: "機會搜尋" });
  return { spy, onSave };
}

describe("OpportunityPage：權限", () => {
  it("Normal 直接打網址：導回首頁、不打任何機會搜尋端點", async () => {
    const spy = mockApi({ role: "normal" });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    await waitFor(() => expect(window.location.hash).toBe("#/"));
    expect(callsTo(spy, "/api/opportunity")).toEqual([]);
    expect(screen.queryByRole("button", { name: "搜尋選擇權" })).not.toBeInTheDocument();
  });

  it.each(["superuser", "superadmin"] as const)("%s 看得到共識清單", async (role) => {
    await renderReady({ role });
    expect(await screen.findByRole("region", { name: "符合條件的股票" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/opportunity");
  });

  it("後端拒絕（403）時顯示後端訊息，不顯示清單", async () => {
    mockApi({ consensus: { status: 403,
                           body: { detail: "機會搜尋目前只開放 Super User／Super Admin" } } });
    render(<OpportunityPage onSaveAsScenario={vi.fn(noSave)} />);
    expect(await screen.findByRole("alert"))
      .toHaveTextContent("機會搜尋目前只開放 Super User／Super Admin");
    expect(screen.queryByRole("region", { name: "符合條件的股票" })).not.toBeInTheDocument();
  });
});

describe("OpportunityPage：資料來源狀態與共識清單", () => {
  it("來源關閉（緊急關閉開關）：說明已關閉、不說「尚未設定」，沒有搜尋按鈕", async () => {
    const { spy } = await renderReady({ consensus: { status: 200, body: NOT_CONFIGURED } });
    expect(await screen.findByRole("heading", { name: "分析師資料來源已關閉" })).toBeInTheDocument();
    expect(screen.queryByText(/尚未設定/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜尋選擇權" })).not.toBeInTheDocument();
    expect(screen.queryByText("測試資料，非真實市場資料")).not.toBeInTheDocument();
    expect(callsTo(spy, "/api/opportunity/search")).toEqual([]);
  });

  it("測試資料來源：頁首固定標示「測試資料，非真實市場資料」", async () => {
    await renderReady();
    const header = await screen.findByRole("banner", { name: "機會搜尋頁首" });
    expect(within(header).getByText("測試資料，非真實市場資料")).toBeInTheDocument();
  });

  it("掃描股票範圍資訊：名稱、有資料／資料不足檔數、as_of、覆蓋率警示；門檻連到設定頁", async () => {
    await renderReady();
    const universe = await screen.findByRole("region", { name: "掃描股票範圍" });
    expect(universe).toHaveTextContent("自訂清單");
    expect(universe).toHaveTextContent("共 7 檔");
    expect(universe).toHaveTextContent("有資料 5 檔");
    expect(universe).toHaveTextContent("資料不足 1 檔");
    expect(universe).toHaveTextContent("2026-09-28");
    // coverage：partial 2 ＋ unknown 2
    expect(universe).toHaveTextContent("4 檔分析師覆蓋不完整");
    expect(universe).toHaveTextContent("資料日期 2026-09-28");
    // 第一道門檻以 PR 顯示（V2-03／#405）：已存的 20 ↔ PR ≥ 80。
    expect(universe).toHaveTextContent("分歧度歷史排序 PR ≥ 80");
    expect(universe).not.toHaveTextContent("百分位");
    expect(universe).toHaveTextContent("分析師分歧率 ≤ 10%");
    expect(within(universe).getByRole("link", { name: "調整門檻" }))
      .toHaveAttribute("href", "#/settings/opportunity");
  });

  it("符合條件的股票逐檔顯示 mean、有效券商數、分析師分歧率、分歧度歷史排序（PR）、歷史點數、資料日期", async () => {
    await renderReady();
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    const aaa = within(selected).getByRole("listitem", { name: "AAA" });
    expect(aaa).toHaveTextContent("$120.00");
    expect(aaa).toHaveTextContent("有效券商數 7");
    expect(aaa).toHaveTextContent("分析師分歧率 9.0%");
    // 原百分位 13.6% → PR 86.4 → 向下取整 PR86（前 14%）。
    expect(aaa).toHaveTextContent("分歧度歷史排序 PR86（前 14%）");
    expect(aaa).toHaveTextContent("44 個歷史點");
    expect(aaa).toHaveTextContent("資料日期 2026-09-28");
    expect(within(selected).getByRole("listitem", { name: "EEE" })).toBeInTheDocument();
    expect(within(selected).queryByRole("listitem", { name: "BBB" })).not.toBeInTheDocument();
  });

  it("符合條件的股票顯示目前股價（帶報價日期）與目標漲跌幅；不能算時寫原因（V2-05／#407）", async () => {
    await renderReady();
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    const aaa = within(selected).getByRole("listitem", { name: "AAA" });
    // fixture：平均目標價 120、股價 100（2026-09-25 收盤）→ +20.0%
    expect(aaa).toHaveTextContent("目前股價 $100.00（2026-09-25 收盤）");
    expect(aaa).toHaveTextContent("目標漲跌幅 +20.0%");
    const eee = within(selected).getByRole("listitem", { name: "EEE" });
    expect(eee).toHaveTextContent("目前股價 $440.00（2025-05-30 收盤）");
    expect(eee).toHaveTextContent("目標漲跌幅 — · 分割基準不一致，暫不計算");
  });

  it("不符合條件與資料不足分開列，不符合條件的附上哪一道門檻沒過", async () => {
    await renderReady();
    const weak = await screen.findByRole("region", { name: "不符合條件" });
    expect(within(weak).getByRole("listitem", { name: "BBB" }))
      .toHaveTextContent("分析師分歧率 15.1%，高於上限 10%");
    expect(within(weak).getByRole("listitem", { name: "BBB" }))
      .not.toHaveTextContent("分歧度歷史排序");
    expect(within(weak).getByRole("listitem", { name: "CCC" }))
      .toHaveTextContent("分歧度歷史排序 PR0（前 100%），未達門檻 PR ≥ 80");
    const thin = screen.getByRole("region", { name: "資料不足" });
    expect(within(thin).getByRole("listitem", { name: "DDD" }))
      .toHaveTextContent("有效券商數 3 < N_min 5");
    expect(within(thin).getByRole("listitem", { name: "FFF" }))
      .toHaveTextContent("來源僅有共識值，沒有個別目標價");
    expect(within(thin).getByRole("listitem", { name: "GGG" })).toHaveTextContent("來源失敗");
    expect(within(weak).queryByRole("listitem", { name: "DDD" })).not.toBeInTheDocument();
  });
});

describe("OpportunityPage：資料建立中（LIVE-T4／#400）", () => {
  const notBuiltItem = (i: OpportunityConsensusResponse["items"][number]) => ({
    ...i, status: "no_data" as const, as_of: null, mean: null, stdev: null,
    dispersion: null, percentile: null, n_analysts: 0, history_points: 0,
    coverage: null, reasons: ["no_data: 尚未更新"],
    gate: { first: false, second: false, selected: false, reasons: ["no_data: 尚未更新"] },
  });
  const NOT_BUILT: OpportunityConsensusResponse = {
    ...CONSENSUS,
    universe: { ...CONSENSUS.universe, with_data: 0, insufficient: 0, not_built: 7,
                coverage: { complete: 0, partial: 0, unknown: 0 }, as_of: null },
    items: CONSENSUS.items.map(notBuiltItem),
  };

  it("一檔都還沒建立：顯示「資料建立中」，不顯示「沒有符合條件的股票」的空結果，搜尋按鈕停用", async () => {
    const { spy } = await renderReady({ consensus: { status: 200, body: NOT_BUILT } });
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    expect(selected).toHaveTextContent("資料建立中");
    expect(selected).toHaveTextContent("7 檔");
    expect(selected).not.toHaveTextContent("目前沒有同時通過兩道門檻的股票");
    expect(selected).not.toHaveTextContent("沒有符合條件的股票");
    expect(screen.queryByRole("region", { name: "資料不足" })).not.toBeInTheDocument();
    expect(within(selected).getByRole("button", { name: "搜尋選擇權" })).toBeDisabled();
    expect(callsTo(spy, "/api/opportunity/search")).toEqual([]);
  });

  it("部分建立：照常列出符合條件的股票，並說明還有幾檔在建立中、清單可能不完整", async () => {
    const partial: OpportunityConsensusResponse = {
      ...CONSENSUS,
      universe: { ...CONSENSUS.universe, not_built: 2 },
      items: CONSENSUS.items.map((i) =>
        ["FFF", "GGG"].includes(i.symbol) ? notBuiltItem(i) : i),
    };
    await renderReady({ consensus: { status: 200, body: partial } });
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    expect(within(selected).getByRole("listitem", { name: "AAA" })).toBeInTheDocument();
    expect(selected).toHaveTextContent("資料建立中：還有 2 檔尚未建立");
    expect(within(selected).getByRole("button", { name: "搜尋選擇權" })).toBeEnabled();
  });

  it("全部建立後不出現「資料建立中」", async () => {
    await renderReady();
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    await within(selected).findByRole("listitem", { name: "AAA" });
    expect(screen.queryByText(/資料建立中/)).not.toBeInTheDocument();
  });
});

describe("OpportunityPage：個股詳細資料（LIVE-T2／#399）", () => {
  it("符合、不符合條件與資料不足的每一列都能打開詳細資料；按下才讀那一檔", async () => {
    const user = userEvent.setup();
    const { spy } = await renderReady();
    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    const thin = screen.getByRole("region", { name: "資料不足" });
    const weak = screen.getByRole("region", { name: "不符合條件" });
    for (const [region, symbol] of [[selected, "AAA"], [weak, "BBB"], [thin, "DDD"]] as const) {
      expect(within(region).getByRole("button", { name: `${symbol} 詳細資料` }))
        .toBeInTheDocument();
    }
    expect(callsTo(spy, "/api/opportunity/consensus-detail/")).toHaveLength(0);
    await user.click(within(thin).getByRole("button", { name: "DDD 詳細資料" }));
    const panel = await within(thin).findByRole("region", { name: "DDD 共識明細" });
    expect(await within(panel).findByRole("list", { name: "每月分析師分歧率" })).toBeInTheDocument();
    expect(callsTo(spy, "/api/opportunity/consensus-detail/").map(([u]) => String(u)))
      .toEqual(["/api/opportunity/consensus-detail/DDD"]);
  });
});

describe("OpportunityPage：結果列的共識詳細資料（LIVE-T5／#401）", () => {
  it("每一列都能打開該股的共識明細（整列寬、按下才讀），再按收起；存成劇本仍在同一列", async () => {
    const user = userEvent.setup();
    const { spy } = await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await user.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const rows = await within(results).findAllByRole("row", { name: /^AAA / });
    for (const row of rows) {
      expect(within(row).getByRole("button", { name: "AAA 共識詳細資料" })).toBeInTheDocument();
      expect(within(row).getByRole("button", { name: "存成劇本" })).toBeInTheDocument();
    }
    const before = callsTo(spy, "/api/opportunity/consensus-detail/").length;
    const row = within(results).getByRole("row", { name: /^AAA Long Call/ });
    const toggle = within(row).getByRole("button", { name: "AAA 共識詳細資料" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = await within(results).findByRole("region", { name: "AAA 共識明細" });
    expect(await within(panel).findByRole("list", { name: "共識數值" }))
      .toHaveTextContent("平均目標價");
    expect(panel.closest("td")).toHaveAttribute("colspan", "10");
    expect(callsTo(spy, "/api/opportunity/consensus-detail/").slice(before).map(([u]) => String(u)))
      .toEqual(["/api/opportunity/consensus-detail/AAA"]);

    await user.click(toggle);
    expect(within(results).queryByRole("region", { name: "AAA 共識明細" })).not.toBeInTheDocument();
  });

  it("每一列都看得到共識更新時存下的目前股價、報價日期與目標漲跌幅（V2-05／#407）", async () => {
    const user = userEvent.setup();
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await user.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const rows = await within(results).findAllByRole("row", { name: /^AAA / });
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      const cell = within(row).getByText("AAA").closest("td")!;
      expect(cell).toHaveTextContent("目前股價 $100.00");
      expect(cell).toHaveTextContent("2026-09-25 收盤");
      expect(cell).toHaveTextContent("目標漲跌幅 +20.0%");
    }
  });
});

const AAA_ONLY: OpportunitySearchResponse = {
  ...SEARCH, failures: [], processed: ["AAA"], remaining: ["EEE"], fetches_used: 1,
};
const EEE_FAILED: OpportunitySearchResponse = {
  ...SEARCH, rows: [], processed: ["EEE"], remaining: [], fetches_used: 1,
};

describe("OpportunityPage：搜尋與續跑", () => {
  it("依 remaining 自動續跑，結果逐檔出現；再回來的同一列不重複", async () => {
    const second = deferred<{ status: number; body: unknown }>();
    const { spy } = await renderReady({
      search: [{ status: 200, body: AAA_ONLY }, second.promise],
    });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));

    // 第一檔的結果在第二次呼叫回來之前就已經出現。
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    await waitFor(() => expect(within(results).getAllByRole("row", { name: /^AAA/ })).toHaveLength(3));
    expect(screen.getByText("已搜尋 1 / 2 檔")).toBeInTheDocument();

    second.resolve({ status: 200, body: { ...EEE_FAILED, rows: [SEARCH.rows[0]] } });
    await waitFor(() => expect(screen.getByText("已搜尋 2 / 2 檔")).toBeInTheDocument());
    expect(searchBodies(spy)).toEqual([{}, { symbols: ["EEE"] }]);
    expect(within(results).getAllByRole("row", { name: /^AAA/ })).toHaveLength(3);
  });

  it("failures 逐檔顯示原因與後端訊息", async () => {
    await renderReady({ search: [{ status: 200, body: AAA_ONLY },
                                 { status: 200, body: EEE_FAILED }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const failures = await screen.findByRole("region", { name: "搜尋失敗" });
    const eee = within(failures).getByRole("listitem", { name: "EEE" });
    expect(eee).toHaveTextContent("抓不到報價");
    expect(eee).toHaveTextContent("抓不到 EEE 的報價：測試資料模擬上游失敗");
  });

  it("有結果但缺了某個家族：照實列出缺哪個家族與引擎的原因（LIVE-T4／#400）", async () => {
    const message = "AAA 的 Butterfly 沒有結果：Call Butterfly：分析耗時超過安全上限，已估值 10／20 組候選後中止（異常輸入的優雅降級，非常態）。";
    const partial: OpportunitySearchResponse = {
      ...SEARCH, failures: [], processed: ["AAA"], remaining: [],
      rows: SEARCH.rows.filter((r) => r.symbol === "AAA" && r.family !== "butterfly"),
      incomplete: [{ symbol: "AAA", families: ["butterfly"], message,
                     strategies: [{ strategy: "call-fly", status: "timed_out",
                                    n_qualified: 0, message: "…" }] }],
    };
    await renderReady({ search: [{ status: 200, body: partial }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const region = await screen.findByRole("region", { name: "部分家族沒有結果" });
    const aaa = within(region).getByRole("listitem", { name: "AAA" });
    expect(aaa).toHaveTextContent("Butterfly");
    expect(aaa).toHaveTextContent(message);
    // 不是失敗：其他家族的結果照樣列出。
    expect(screen.queryByRole("region", { name: "搜尋失敗" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "搜尋結果" }))
      .getAllByRole("row", { name: /^AAA/ })).toHaveLength(2);
  });

  it("「停止」之後不再續跑；剩下的檔可以接著搜尋", async () => {
    const first = deferred<{ status: number; body: unknown }>();
    const { spy } = await renderReady({
      search: [first.promise, { status: 200, body: EEE_FAILED }],
    });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    await userEvent.click(await screen.findByRole("button", { name: "停止" }));
    first.resolve({ status: 200, body: AAA_ONLY });

    const resume = await screen.findByRole("button", { name: "繼續搜尋剩下 1 檔" });
    expect(screen.getByText(/已停止/)).toBeInTheDocument();
    expect(searchBodies(spy)).toEqual([{}]);
    // 停止前那一次已經回來的結果照樣顯示（額度已經花了）。
    expect(within(screen.getByRole("region", { name: "搜尋結果" }))
      .getAllByRole("row", { name: /^AAA/ })).toHaveLength(3);

    await userEvent.click(resume);
    await waitFor(() => expect(searchBodies(spy)).toEqual([{}, { symbols: ["EEE"] }]));
    expect(await screen.findByRole("region", { name: "搜尋失敗" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /繼續搜尋/ })).not.toBeInTheDocument();
  });

  it("熔斷：顯示後端的降級訊息並停止，剩下的檔留著可以稍後接著搜尋", async () => {
    const fused: OpportunitySearchResponse = {
      ...SEARCH, rows: [], failures: [], processed: [], remaining: ["AAA", "EEE"],
      fetches_used: 1, stopped_reason: "fused",
      message: "今日全站報價查詢預算已用完，畫面沿用既有資料，請稍後或明天再試",
    };
    const { spy } = await renderReady({ search: [{ status: 200, body: fused }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    expect(await screen.findByRole("alert"))
      .toHaveTextContent("今日全站報價查詢預算已用完");
    expect(screen.getByRole("button", { name: "繼續搜尋剩下 2 檔" })).toBeInTheDocument();
    expect(searchBodies(spy)).toEqual([{}]);
  });

  it("超過單次上限：照實說還有幾檔沒搜，按鈕對那些檔發起新的一次搜尋（不自動續跑）", async () => {
    const capped: OpportunitySearchResponse = {
      ...SEARCH, failures: [], processed: ["AAA"], remaining: [], fetches_used: 1,
      fetch_cap: 1, truncated: true, deferred: ["EEE"],
    };
    const { spy } = await renderReady({
      search: [{ status: 200, body: capped }, { status: 200, body: EEE_FAILED }],
    });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    expect(await screen.findByText("超過單次上限，尚有 1 檔未搜尋")).toBeInTheDocument();
    expect(searchBodies(spy)).toEqual([{}]);                 // 沒有自動續跑

    await userEvent.click(screen.getByRole("button", { name: "搜尋未搜尋的 1 檔" }));
    await waitFor(() => expect(searchBodies(spy)).toEqual([{}, { symbols: ["EEE"] }]));
    expect(await screen.findByRole("region", { name: "搜尋失敗" })).toBeInTheDocument();
    // 前一次的結果保留；這次沒有再超過上限，提示與按鈕都消失。
    expect(within(screen.getByRole("region", { name: "搜尋結果" }))
      .getAllByRole("row", { name: /^AAA/ })).toHaveLength(3);
    expect(screen.queryByText(/超過單次上限/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /搜尋未搜尋/ })).not.toBeInTheDocument();
    expect(screen.getByText("已搜尋 2 / 2 檔")).toBeInTheDocument();
  });

  it("排序選項的文字來自後端回應", async () => {
    const labelled: OpportunitySearchResponse = {
      ...SEARCH, remaining: [],
      sort_options: [{ id: "return", label: "報酬（後端文字）" },
                     { id: "cost", label: "成本（後端文字）" },
                     { id: "max_loss", label: "損失（後端文字）" }],
    };
    await renderReady({ search: [{ status: 200, body: labelled }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const select = within(results).getByRole("combobox", { name: "排序" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent))
      .toEqual(["報酬（後端文字）", "成本（後端文字）", "損失（後端文字）"]);
  });

  it("409（來源未設定）：顯示後端訊息，不顯示任何結果", async () => {
    await renderReady({ search: [{ status: 409, body: { detail: "尚未設定分析師資料來源" } }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("尚未設定分析師資料來源");
    expect(screen.queryByRole("region", { name: "搜尋結果" })).not.toBeInTheDocument();
  });

  it("切換排序只在前端重排，不重新搜尋", async () => {
    const { spy } = await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const order = () => within(results).getAllByRole("row", { name: /^AAA/ })
      .map((r) => r.getAttribute("data-family"));
    await waitFor(() => expect(order()).toEqual(["vertical-spread", "single-leg", "butterfly"]));

    await userEvent.selectOptions(within(results).getByRole("combobox", { name: "排序" }), "max_loss");
    expect(order()).toEqual(["vertical-spread", "butterfly", "single-leg"]);
    await userEvent.selectOptions(within(results).getByRole("combobox", { name: "排序" }), "cost");
    expect(order()).toEqual(["vertical-spread", "butterfly", "single-leg"]);
    expect(searchBodies(spy)).toHaveLength(1);
  });

  it("結果列顯示策略、履約價、到期日、目標月份、成本（每股）、最大損失（每股）、報酬、損益兩平", async () => {
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const spread = await within(results).findByRole("row", { name: /^AAA Bull Call Spread/ });
    expect(spread).toHaveTextContent("買 112 / 賣 115");
    expect(spread).toHaveTextContent("2026-12-18");
    expect(spread).toHaveTextContent("2027-09");
    expect(spread).toHaveTextContent("$0.81");
    expect(spread).toHaveTextContent("270.4%");
    expect(spread).toHaveTextContent("$112.81");
  });

  it("最大損失與詳細頁同一口徑：每股（後端每口 ÷ 100），欄名如實寫每股", async () => {
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    expect(within(results).getByRole("columnheader", { name: "最大損失 / 股" })).toBeInTheDocument();
    expect(within(results).queryByRole("columnheader", { name: /每口|\/ 口/ })).not.toBeInTheDocument();
    const maxLoss = (name: RegExp) => within(results).getByRole("row", { name })
      .querySelector('td[data-label="最大損失 / 股"]')?.textContent;
    // 樣本：max_loss_per_contract 81 / 560 / 259（每口，100 股）。
    expect(maxLoss(/^AAA Bull Call Spread/)).toBe("$0.81");
    expect(maxLoss(/^AAA Long Call/)).toBe("$5.60");
    expect(maxLoss(/^AAA Call Butterfly/)).toBe("$2.59");
    expect(results).not.toHaveTextContent("$560.00");
  });
});

describe("OpportunityPage：文案", () => {
  it("固定一句策略報酬說明；不出現期望報酬、預期獲利，勝率只出現在那句否定說明裡", async () => {
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] });
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    // 連資料狀態、失敗清單與打開的共識明細一起檢查。
    await screen.findByRole("listitem", { name: "今日更新" });
    const row = within(results).getByRole("row", { name: /^AAA Long Call/ });
    await userEvent.click(within(row).getByRole("button", { name: "AAA 共識詳細資料" }));
    await within(results).findByRole("list", { name: "共識數值" });
    const disclaimer = "此報酬是『股價在目標月份達到分析師平均目標價時』的策略報酬，不是期望值或勝率";
    expect(screen.getByText(disclaimer)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/期望報酬|預期獲利/);
    expect(text.replace(disclaimer, "")).not.toMatch(/勝率/);
  });
});

describe("OpportunityPage：存成劇本", () => {
  it("用該列的 scenario 原封不動呼叫建立劇本，成功後導到詳細頁", async () => {
    const onSave = vi.fn(async () => ({ id: "new-1" }));
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] }, onSave);
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const row = await within(results).findByRole("row", { name: /^AAA Long Call/ });
    await userEvent.click(within(row).getByRole("button", { name: "存成劇本" }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(SEARCH.rows[1].scenario);
    await waitFor(() => expect(window.location.hash).toBe("#/s/new-1"));
  });

  it("超過額度：顯示既有的額度訊息，不導頁、不顯示成功", async () => {
    const quota = "目前有 10 個進行中劇本，已達上限（10 個）。請先封存或刪除既有劇本後再建立新的。";
    const onSave = vi.fn(async () => { throw new ApiError(quota); });
    await renderReady({ search: [{ status: 200, body: { ...SEARCH, remaining: [] } }] }, onSave);
    await userEvent.click(await screen.findByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const row = await within(results).findByRole("row", { name: /^AAA Long Call/ });
    await userEvent.click(within(row).getByRole("button", { name: "存成劇本" }));

    expect(await within(results).findByRole("alert")).toHaveTextContent(quota);
    expect(window.location.hash).toBe("#/opportunity");
    expect(within(row).getByRole("button", { name: "存成劇本" })).toBeEnabled();
    expect(screen.queryByText(/已存成劇本|已建立劇本|劇本已建立/)).not.toBeInTheDocument();
  });
});
