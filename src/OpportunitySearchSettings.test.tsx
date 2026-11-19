/**
 * 設定頁「機會搜尋」區塊（OS-02／#391，母票 #389 §6）。
 *
 * 守四件事：區塊照後端給的值與選項渲染；「恢復預設」真的把那一道門檻存回
 * 預設（只動那一道）；「儲存」把整個區塊送到既有 `PUT /api/settings`、
 * 不碰資料來源那兩列；後端驗證失敗時照實顯示後端訊息，不顯示「已儲存」。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import OpportunitySearchSettings from "./OpportunitySearchSettings";
import type { OpportunitySearchSettings as Opp, SettingsView } from "./api";

const DEFAULTS: Opp = {
  universe_id: "sample-large-cap",
  custom_symbols: [],
  percentile_max: 20,
  dispersion_max: 10,
  strategies: ["single-leg", "vertical-spread", "butterfly"],
  sort: "return",
};

function view(opp: Partial<Opp> = {}): SettingsView {
  return {
    supported_providers: [{ id: "marketdata-app", label: "Market Data App" }],
    market_data: { mode: "custom", provider: "marketdata-app", default_label: "Cboe" },
    historical_iv: { mode: "default", provider: null, default_label: "無" },
    credentials: {},
    market_data_effective: { source: "Cboe", fallback: false, reason: null },
    historical_iv_enabled: false,
    opportunity_search: { ...DEFAULTS, ...opp },
    opportunity_search_options: {
      universes: [
        { id: "sample-large-cap", label: "大型股樣本（暫定，清單來源待 #382）",
          provisional: true, symbol_count: 50 },
        { id: "custom", label: "自訂清單", provisional: false, symbol_count: null },
      ],
      strategies: ["single-leg", "vertical-spread", "butterfly"],
      sorts: [{ id: "return", label: "排序甲（後端文字）" },
              { id: "cost", label: "排序乙（後端文字）" },
              { id: "max_loss", label: "排序丙（後端文字）" }],
      custom_symbols_max: 50,
      defaults: DEFAULTS,
    },
    updated_at: null,
  };
}

/** 每次 PUT 依序回 `responses` 的下一個（`Response` 形狀的最小假體）。 */
function mockPut(responses: Array<{ status: number; body: unknown }>) {
  let i = 0;
  const spy = vi.fn(async (_url: string, _init?: RequestInit) => {
    const r = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return {
      ok: r.status < 400, status: r.status, headers: new Headers(),
      json: async () => r.body,
    } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

function putBodies(spy: ReturnType<typeof mockPut>) {
  return spy.mock.calls
    .filter(([url, init]) => url === "/api/settings" && init?.method === "PUT")
    .map(([, init]) => JSON.parse(init!.body as string));
}

function block() {
  return within(screen.getByRole("region", { name: "機會搜尋" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("渲染", () => {
  it("顯示兩道門檻、母體、策略家族與排序的目前值", () => {
    render(<OpportunitySearchSettings view={view({ percentile_max: 35, sort: "cost" })}
                                      onSaved={() => {}} />);
    const b = block();
    expect(b.getByLabelText("分歧度歷史百分位門檻（%）")).toHaveValue(35);
    expect(b.getByLabelText("分歧度門檻（%）")).toHaveValue(10);
    expect(b.getByRole("radio", { name: "大型股樣本（暫定，清單來源待 #382）" })).toBeChecked();
    expect(b.getByRole("checkbox", { name: "Call / Put" })).toBeChecked();
    expect(b.getByRole("checkbox", { name: "Vertical Spread" })).toBeChecked();
    expect(b.getByRole("checkbox", { name: "Butterfly" })).toBeChecked();
    expect(b.getByLabelText("排序方式")).toHaveValue("cost");
    expect(b.getAllByRole("button", { name: "恢復預設" })).toHaveLength(2);
  });

  it("排序選項的文字來自後端（與搜尋頁同一份），前端不另寫一份", () => {
    render(<OpportunitySearchSettings view={view()} onSaved={() => {}} />);
    const select = block().getByLabelText("排序方式");
    expect(within(select).getAllByRole("option").map((o) => o.textContent))
      .toEqual(["排序甲（後端文字）", "排序乙（後端文字）", "排序丙（後端文字）"]);
  });

  it("母體文案絕不稱為 S&P 500", () => {
    const { container } = render(
      <OpportunitySearchSettings view={view()} onSaved={() => {}} />);
    expect(container.textContent).not.toMatch(/S&P|500/);
  });

  it("選自訂才出現 ticker 清單輸入框", async () => {
    render(<OpportunitySearchSettings view={view()} onSaved={() => {}} />);
    const b = block();
    expect(b.queryByLabelText("Ticker 清單")).not.toBeInTheDocument();
    await userEvent.click(b.getByRole("radio", { name: "自訂清單" }));
    expect(b.getByLabelText("Ticker 清單")).toBeInTheDocument();
  });
});

describe("恢復預設", () => {
  it("只把那一道門檻存回預設，另一道門檻與資料來源不動", async () => {
    const saved = view({ percentile_max: 20, dispersion_max: 4 });
    const spy = mockPut([{ status: 200, body: saved }]);
    const onSaved = vi.fn();
    render(<OpportunitySearchSettings view={view({ percentile_max: 35, dispersion_max: 4 })}
                                      onSaved={onSaved} />);
    const b = block();
    const [restorePercentile] = b.getAllByRole("button", { name: "恢復預設" });
    await userEvent.click(restorePercentile);

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(putBodies(spy)).toEqual([{
      market_data: { mode: "custom", provider: "marketdata-app" },
      historical_iv: { mode: "default", provider: null },
      opportunity_search: { percentile_max: 20 },
    }]);
    expect(b.getByLabelText("分歧度歷史百分位門檻（%）")).toHaveValue(20);
    expect(b.getByLabelText("分歧度門檻（%）")).toHaveValue(4);
    expect(b.getByRole("status")).toHaveTextContent("已恢復預設");
  });

  it("恢復預設不會吃掉另一道門檻尚未儲存的修改", async () => {
    mockPut([{ status: 200, body: view({ dispersion_max: 10 }) }]);
    render(<OpportunitySearchSettings view={view({ dispersion_max: 4 })} onSaved={() => {}} />);
    const b = block();
    const percentile = b.getByLabelText("分歧度歷史百分位門檻（%）");
    await userEvent.clear(percentile);
    await userEvent.type(percentile, "15");
    await userEvent.click(b.getAllByRole("button", { name: "恢復預設" })[1]);

    await waitFor(() => expect(b.getByLabelText("分歧度門檻（%）")).toHaveValue(10));
    expect(percentile).toHaveValue(15);
  });
});

describe("儲存", () => {
  it("把整個區塊送到既有 settings API，資料來源照已存的值帶上", async () => {
    const spy = mockPut([{ status: 200, body: view() }]);
    const onSaved = vi.fn();
    render(<OpportunitySearchSettings view={view()} onSaved={onSaved} />);
    const b = block();

    const percentile = b.getByLabelText("分歧度歷史百分位門檻（%）");
    await userEvent.clear(percentile);
    await userEvent.type(percentile, "12.5");
    await userEvent.click(b.getByRole("radio", { name: "自訂清單" }));
    await userEvent.type(b.getByLabelText("Ticker 清單"), "tsla, aapl\nnvda");
    await userEvent.click(b.getByRole("checkbox", { name: "Butterfly" }));
    await userEvent.selectOptions(b.getByLabelText("排序方式"), "max_loss");
    await userEvent.click(b.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(putBodies(spy)).toEqual([{
      market_data: { mode: "custom", provider: "marketdata-app" },
      historical_iv: { mode: "default", provider: null },
      opportunity_search: {
        universe_id: "custom",
        custom_symbols: ["TSLA", "AAPL", "NVDA"],
        percentile_max: 12.5,
        dispersion_max: 10,
        strategies: ["single-leg", "vertical-spread"],
        sort: "max_loss",
      },
    }]);
    expect(b.getByRole("status")).toHaveTextContent("已儲存");
  });

  it("後端驗證失敗時顯示後端訊息，不顯示已儲存", async () => {
    mockPut([{ status: 422, body: { detail: [{
      type: "value_error", loc: ["body", "opportunity_search", "percentile_max"],
      msg: "Value error, 分歧度歷史百分位門檻必須介於 0 到 100", input: 101 }] } }]);
    const onSaved = vi.fn();
    render(<OpportunitySearchSettings view={view()} onSaved={onSaved} />);
    const b = block();
    const percentile = b.getByLabelText("分歧度歷史百分位門檻（%）");
    await userEvent.clear(percentile);
    await userEvent.type(percentile, "101");
    await userEvent.click(b.getByRole("button", { name: "儲存" }));

    expect(await b.findByRole("alert")).toHaveTextContent("分歧度歷史百分位門檻必須介於 0 到 100");
    expect(b.queryByRole("status")).not.toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("輸入框清空時照樣送出，由後端判斷並回訊息（前端不自己吞掉）", async () => {
    const spy = mockPut([{ status: 422, body: { detail: [{
      type: "value_error", loc: ["body", "opportunity_search", "dispersion_max"],
      msg: "Value error, 分歧度門檻必須是數字", input: "" }] } }]);
    render(<OpportunitySearchSettings view={view()} onSaved={() => {}} />);
    const b = block();
    await userEvent.clear(b.getByLabelText("分歧度門檻（%）"));
    await userEvent.click(b.getByRole("button", { name: "儲存" }));

    expect(await b.findByRole("alert")).toHaveTextContent("分歧度門檻必須是數字");
    expect(putBodies(spy)[0].opportunity_search.dispersion_max).toBe("");
  });
});
