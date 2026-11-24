/**
 * V2-04（#406）：易誤會指標旁的 ⓘ 有掛上，而且打開後的說明卡文字來自
 * `metricHelp.ts`（不是各畫面自己寫一份）。
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import consensusSample from "../contracts/opportunity_consensus_sample.json";
import detailSample from "../contracts/opportunity_detail_sample.json";
import searchSample from "../contracts/opportunity_search_sample.json";
import statusSample from "../contracts/opportunity_consensus_status_sample.json";
import { METRIC_HELP, metricHelpLabel, type MetricHelpKey } from "./metricHelp";
import OpportunityPage from "./OpportunityPage";
import OpportunitySearchSettings from "./OpportunitySearchSettings";
import type { ConsensusItem, OpportunitySearchSettings as Opp, SettingsView } from "./api";

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

/** 打開 scope 裡名為「X說明」的 ⓘ，回傳它的說明卡。 */
function openHelp(scope: HTMLElement, key: MetricHelpKey): HTMLElement {
  const button = within(scope).getByRole("button", { name: metricHelpLabel(key) });
  fireEvent.click(button, { detail: 0 });
  const id = button.getAttribute("aria-describedby");
  expect(id, key).toBeTruthy();
  return document.getElementById(id!)!;
}

function expectHelp(scope: HTMLElement, key: MetricHelpKey) {
  const tip = openHelp(scope, key);
  expect(tip).toHaveAttribute("role", "tooltip");
  expect(tip).toHaveTextContent(METRIC_HELP[key].basis);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(document.getElementById(tip.id)).toBeNull();
}

beforeEach(() => {
  window.location.hash = "#/opportunity";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("機會搜尋頁的 ⓘ", () => {
  it("掃描股票範圍、清單指標、資料狀態、共識詳細、結果表都有說明", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<OpportunityPage onSaveAsScenario={vi.fn()} />);

    const universe = await screen.findByRole("region", { name: "掃描股票範圍" });
    expectHelp(universe, "scanUniverse");

    const panel = await screen.findByRole("region", { name: "分析師資料" });
    const status = await within(panel).findByRole("list", { name: "資料狀態" });
    expectHelp(status, "dataDate");
    await waitFor(() =>
      within(status).getByRole("button", { name: metricHelpLabel("dailyCap") }));
    expectHelp(status, "dailyCap");
    expectHelp(panel, "rateLimitPause");
    expectHelp(panel, "rotatingUpdate");

    const selected = screen.getByRole("region", { name: "符合條件的股票" });
    for (const key of ["meanTarget", "validBrokerCount", "dispersionRate",
                       "dispersionRank", "dataDate"] as const) {
      expectHelp(selected, key);
    }

    await user.click(within(selected).getByRole("button", { name: "AAA 詳細資料" }));
    const facts = await within(selected).findByRole("list", { name: "共識數值" });
    for (const key of ["meanTarget", "dispersionRate", "dispersionRank",
                       "validBrokerCount", "dataDate"] as const) {
      expectHelp(facts, key);
    }
    // 圖示不是文字：數值清單的文字跟加圖示之前一樣（標籤緊接數值）。
    expect(facts).toHaveTextContent("有效券商數7資料日期");

    await user.click(within(selected).getByRole("button", { name: "搜尋選擇權" }));
    const results = await screen.findByRole("region", { name: "搜尋結果" });
    // 結果表的說明：鍵盤與螢幕報讀器用區塊頂端的說明列（桌面、手機都顯示）；
    // 表頭裡的 ⓘ 只給滑鼠（aria-hidden），欄位的無障礙名稱不會混進「…說明」。
    const thead = results.querySelector("thead") as HTMLElement;
    const helpRow = results.querySelector(".opp-help-results") as HTMLElement;
    for (const key of ["currentPrice", "targetUpside", "costAndMaxLoss", "scenarioReturn"] as const) {
      expectHelp(helpRow, key);
    }
    expect(within(thead).queryAllByRole("button")).toHaveLength(0);
    expect(within(thead).getAllByRole("button", { hidden: true })).toHaveLength(4);
    for (const header of within(thead).getAllByRole("columnheader")) {
      expect(header).not.toHaveAccessibleName(/說明/);
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

describe("設定頁的 ⓘ", () => {
  it("兩道門檻與掃描股票範圍都有說明；輸入框與選項群組的名稱不含圖示名稱", () => {
    const { container } = render(
      <OpportunitySearchSettings view={SETTINGS} onSaved={() => {}} />);
    expectHelp(container, "dispersionRank");
    expectHelp(container, "dispersionRate");
    expectHelp(container, "scanUniverse");
    expect(screen.getByRole("spinbutton", { name: "分歧度歷史排序門檻：PR ≥" }))
      .toBeInTheDocument();
    expect(screen.getByRole("group", { name: "掃描股票範圍" })).toBeInTheDocument();
  });
});
