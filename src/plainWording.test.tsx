/**
 * V2-03（#405）：介面白話化的守門——#405 的新舊名稱對照表是唯一依據。
 *
 * 把五個區域（搜尋、設定、共識詳細、資料狀態、結果表）實際渲染出來，
 * 打開共識詳細（符合條件、不符合條件、資料不足各一檔）與結果列明細，
 * 再掃整頁的文字與 aria-label／data-label：舊名稱一個都不能出現，新名稱
 * 都要出現。後端給的文字（不符合原因、排序選項）走 `contracts/` 樣本，
 * 與後端同一份，所以後端那邊的用語也一起鎖住。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import consensusSample from "../contracts/opportunity_consensus_sample.json";
import detailSample from "../contracts/opportunity_detail_sample.json";
import searchSample from "../contracts/opportunity_search_sample.json";
import statusSample from "../contracts/opportunity_consensus_status_sample.json";
import OpportunityPage from "./OpportunityPage";
import OpportunitySearchSettings from "./OpportunitySearchSettings";
import type { ConsensusItem, OpportunitySearchSettings as Opp, SettingsView } from "./api";

/** #405 對照表的「舊」欄（加上它們在畫面上的變體）。 */
const OLD_NAMES: Array<[string, RegExp]> = [
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

/** 畫面上看得到或讀得到的文字：文字節點＋無障礙名稱＋手機卡片欄名。 */
function visibleText(root: HTMLElement): string {
  const attrs = [...root.querySelectorAll("[aria-label], [data-label], [title], [placeholder]")]
    .flatMap((el) => ["aria-label", "data-label", "title", "placeholder"]
      .map((a) => el.getAttribute(a) ?? ""));
  const options = [...root.querySelectorAll("option")].map((o) => o.textContent ?? "");
  return [root.textContent ?? "", ...attrs, ...options].join("\n");
}

function expectNoOldNames(text: string) {
  const hits = OLD_NAMES.filter(([, re]) => re.test(text))
    .map(([name, re]) => `${name}：…${text.match(re)?.input?.slice(
      Math.max(0, (text.match(re)?.index ?? 0) - 20), (text.match(re)?.index ?? 0) + 20)}…`);
  expect(hits).toEqual([]);
}

function res(status: number, body: unknown): Response {
  return { ok: status < 400, status, headers: new Headers(),
           json: async () => body } as Response;
}

const ITEMS = consensusSample.items as unknown as ConsensusItem[];

function mockApi() {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    if (u.startsWith("/api/auth/status")) return res(200, { role: "superuser" });
    if (u.startsWith("/api/opportunity/consensus-detail/")) {
      const symbol = decodeURIComponent(u.split("/").pop() ?? "");
      const item = ITEMS.find((i) => i.symbol === symbol) ?? detailSample.item;
      return res(200, { ...detailSample, symbol, item: { ...item, symbol } });
    }
    if (u.startsWith("/api/opportunity/consensus/status")) return res(200, statusSample);
    if (u.startsWith("/api/opportunity/consensus")) return res(200, consensusSample);
    if (u.startsWith("/api/opportunity/search")) {
      return res(200, { ...searchSample, remaining: [] });
    }
    return res(404, { detail: "not mocked" });
  }));
}

beforeEach(() => {
  window.location.hash = "#/opportunity";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("搜尋頁、資料狀態、結果表、共識詳細：只用 #405 定稿名稱", () => {
  it("整頁（含三種共識詳細與結果列明細）沒有任何舊名稱，新名稱都在", async () => {
    mockApi();
    const user = userEvent.setup();
    const { container } = render(<OpportunityPage onSaveAsScenario={vi.fn()} />);
    await screen.findByRole("heading", { name: "機會搜尋" });
    await screen.findByRole("list", { name: "資料狀態" });

    const selected = await screen.findByRole("region", { name: "符合條件的股票" });
    await user.click(within(selected).getByRole("button", { name: "AAA 詳細資料" }));
    const failed = screen.getByRole("region", { name: "不符合條件" });
    await user.click(within(failed).getByRole("button", { name: "CCC 詳細資料" }));
    const thin = screen.getByRole("region", { name: "資料不足" });
    await user.click(within(thin).getByRole("button", { name: "DDD 詳細資料" }));

    await user.click(within(selected).getByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    const row = within(results).getByRole("row", { name: /^AAA Long Call/ });
    await user.click(within(row).getByRole("button", { name: "AAA 共識詳細資料" }));

    // 四份詳細資料都讀完（符合、不符合、資料不足、結果列）。
    await waitFor(() =>
      expect(screen.getAllByRole("list", { name: "共識數值" })).toHaveLength(4));
    // 不符合條件的詳細資料有原因清單（附上哪一道門檻沒過）。
    await screen.findAllByRole("list", { name: "不符合條件的原因" });

    const text = visibleText(container);
    expectNoOldNames(text);
    for (const name of [
      "掃描股票範圍", "符合條件的股票", "不符合條件", "分歧度歷史排序", "PR",
      "分析師分歧率", "有效券商數", "每月分析師分歧率", "股價達標時的策略報酬",
      "資料日期",
    ]) {
      expect(text, name).toContain(name);
    }
  });
});

const DEFAULTS: Opp = {
  universe_id: "sample-large-cap", custom_symbols: [], percentile_max: 20,
  dispersion_max: 10, strategies: ["single-leg", "vertical-spread", "butterfly"],
  sort: "return",
};

const SETTINGS: SettingsView = {
  supported_providers: [],
  market_data: { mode: "default", provider: null, default_label: "Cboe" },
  historical_iv: { mode: "default", provider: null, default_label: "無" },
  credentials: {},
  market_data_effective: { source: "Cboe", fallback: false, reason: null },
  historical_iv_enabled: false,
  opportunity_search: DEFAULTS,
  opportunity_search_options: {
    universes: [{ id: "custom", label: "自訂清單", provisional: false, symbol_count: null }],
    strategies: ["single-leg", "vertical-spread", "butterfly"],
    sorts: [{ id: "return", label: "股價達標時的策略報酬（高→低）" }],
    custom_symbols_max: 50,
    defaults: DEFAULTS,
  },
  updated_at: null,
};

describe("設定頁：只用 #405 定稿名稱", () => {
  it("沒有任何舊名稱，新名稱都在", () => {
    const { container } = render(
      <OpportunitySearchSettings view={SETTINGS} onSaved={() => {}} />);
    const text = visibleText(container);
    expectNoOldNames(text);
    for (const name of ["掃描股票範圍", "分歧度歷史排序門檻", "PR ≥", "分析師分歧率上限（%）"]) {
      expect(text, name).toContain(name);
    }
  });
});
