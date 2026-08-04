/**
 * V1（#48）前端元件測試。
 *
 * mock 回應直接載入 `contracts/analysis_sample.json`——與後端 fixture
 * **同一份**契約樣本（spec #47 裁示），任一邊改動契約而沒同步，
 * 後端的 `test_contract_sample_matches_the_live_api_response` 會先爆。
 *
 * 只測外部行為（畫面呈現什麼、失敗時說什麼），不測實作細節。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import sample from "../contracts/analysis_sample.json";
import sampleRow from "../contracts/scenario_row_sample.json";
import { baselineTopCandidate, type AnalysisView } from "./api";

const view = sample as unknown as AnalysisView;

/**
 * V3 起 App 開站就會打 `/api/scenarios`，所以 mock 必須依 URL 分流——
 * 一個「不管問什麼都回同一份分析結果」的 stub 會讓劇本清單收到一份
 * 不是陣列的東西，測出來的東西也就不代表真實行為。
 */
function mockRoutes(
  routes: Record<string, Partial<Response> & { json: () => Promise<unknown> }>,
) {
  const spy = vi.fn(async (url: string, _init?: RequestInit) => {
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    if (key === undefined) throw new Error(`測試沒有為 ${url} 準備回應`);
    return { ok: true, status: 200, ...routes[key] };
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** 分析端點以外一律回空劇本清單——V1 遺留畫面的測試只關心分析。 */
function mockFetch(resp: Partial<Response> & { json: () => Promise<unknown> }) {
  return mockRoutes({
    "/api/scenarios": { json: async () => [] },
    "/api/analyze": resp,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("走通骨架畫面", () => {
  it("分析前不顯示任何結果數字", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    // 等開站的劇本清單載完，否則斷言會落在畫面還沒定下來的一瞬間
    await screen.findByText(/還沒有劇本/);

    expect(screen.getByRole("button", { name: "跑一次分析" })).toBeEnabled();
    expect(screen.queryByText("現價")).not.toBeInTheDocument();
  });

  it("分析後顯示現價、baseline 到期日與該期第 1 名收益率", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));

    const top = baselineTopCandidate(view)!;
    expect(await screen.findByText("現價")).toBeInTheDocument();
    expect(
      screen.getByText(`$${view.meta.spot.toFixed(2)}`),
    ).toBeInTheDocument();
    expect(screen.getByText(view.baseline_expiry!)).toBeInTheDocument();
    expect(
      screen.getByText(`${(top.baseline_return * 100).toFixed(1)}%`),
    ).toBeInTheDocument();
  });

  it("顯示資料來源——Cboe 可達性就看這一行", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));
    expect(
      await screen.findByText(new RegExp(`資料來源 ${view.meta.source}`)),
    ).toBeInTheDocument();
  });

  it("呼叫 API 時送出的是分析請求的必要欄位", async () => {
    const spy = mockFetch({ json: async () => view });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));
    await screen.findByText("現價");

    // 開站的劇本清單請求也在裡面，挑出分析那一筆。
    const call = spy.mock.calls.find(([url]) => url === "/api/analyze")!;
    const body = JSON.parse(String(call[1]!.body));
    expect(body).toMatchObject({
      symbol: expect.any(String),
      target_price: expect.any(Number),
      target_month: expect.stringMatching(/^\d{4}-\d{2}$/),
      strategies: expect.arrayContaining([expect.any(String)]),
    });
  });

  it("上游報價來源掛掉時顯示後端給的原因，不是白畫面", async () => {
    mockFetch({
      ok: false,
      status: 502,
      json: async () => ({ detail: "兩個資料源都抓不到" }),
    });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "兩個資料源都抓不到",
    );
    expect(screen.queryByText("現價")).not.toBeInTheDocument();
  });
});

describe("baseline 期零合格候選（附錄A10.2 的邊界）", () => {
  it("不拿別期的第 1 名冒充，明說無合格候選", async () => {
    const degenerate = {
      ...view,
      baseline_expiry: "2099-01-01", // 該期不在 expiry_top10 裡＝零合格候選
    } as AnalysisView;
    mockFetch({ json: async () => degenerate });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));

    // 頁面照樣可讀（現價、到期日都在），但第 1 名欄位如實說沒有——
    // 不能顯示另一個到期日的候選，那是誤導。
    expect(await screen.findByText("現價")).toBeInTheDocument();
    expect(screen.getByText("2099-01-01")).toBeInTheDocument();
    expect(screen.getByText("無合格候選")).toBeInTheDocument();
    expect(screen.queryByText("劇本報酬")).not.toBeInTheDocument();
  });

  it("完全沒有合格候選時明說，不顯示假數字", async () => {
    const empty = {
      ...view,
      results: [{ strategy: "bull-call-spread", status: "empty", message: "" }],
    } as AnalysisView;
    mockFetch({ json: async () => empty });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));

    expect(await screen.findByText("無合格候選")).toBeInTheDocument();
  });
});

describe("候選池診斷（FB4-01／#60）", () => {
  it("分析後一併顯示候選池狀態，讓「第 1 名」有脈絡可讀", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "跑一次分析" }));

    expect(await screen.findByText("候選池")).toBeInTheDocument();
    expect(screen.getByText("通過品質過濾")).toBeInTheDocument();
  });

  it("分析前不顯示候選池", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    await screen.findByText(/還沒有劇本/);

    expect(screen.queryByText("候選池")).not.toBeInTheDocument();
  });
});

describe("劇本庫（V3／#51）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.5,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };

  it("開站就載入劇本清單並畫成卡片", async () => {
    mockRoutes({ "/api/scenarios": { json: async () => [row] } });
    render(<App />);

    expect(await screen.findByText("TLT")).toBeInTheDocument();
    expect(screen.getByText("150.0%")).toBeInTheDocument();
    expect(screen.getByText("劇本庫")).toBeInTheDocument();
  });

  it("清單載不動時說明原因，不是空白的「還沒有劇本」", async () => {
    mockRoutes({
      "/api/scenarios": {
        ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
      },
    });
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("資料庫連不上");
  });

  it("建立後新劇本立刻出現在清單上", async () => {
    const created = { ...row, id: "s2", symbol: "SPY",
                      latest_analyzed_at: null, best_return: null };
    const spy = mockRoutes({
      "/api/scenarios": { json: async () => [] },
    });
    spy.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/scenarios" && init?.method === "POST") {
        return { ok: true, status: 201, json: async () => created };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    render(<App />);

    await userEvent.type(await screen.findByLabelText("標的代號"), "spy");
    await userEvent.type(screen.getByLabelText("目標價位"), "700");
    await userEvent.type(screen.getByLabelText("目標年月"), "2028-05");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(await screen.findByText("SPY")).toBeInTheDocument();
    // 還沒分析過 → 收益率欄位是「—」，不是 0%
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("封存後卡片從清單消失", async () => {
    const spy = mockRoutes({ "/api/scenarios": { json: async () => [row] } });
    spy.mockImplementation(async (url: string) => {
      if (url.endsWith("/archive")) {
        return { ok: true, status: 200, json: async () => ({ archived: true }) };
      }
      return { ok: true, status: 200, json: async () => [row] };
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));

    expect(screen.queryByText("TLT")).not.toBeInTheDocument();
  });

  it("封存失敗時卡片回到清單上，並說明原因", async () => {
    const spy = mockRoutes({ "/api/scenarios": { json: async () => [row] } });
    spy.mockImplementation(async (url: string) => {
      if (url.endsWith("/archive")) {
        return { ok: false, status: 404,
                 json: async () => ({ detail: "劇本不存在" }) };
      }
      return { ok: true, status: 200, json: async () => [row] };
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));

    // 樂觀移除必須可回復——否則畫面會宣稱一件沒發生的事
    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();
  });
});

describe("樂觀封存的併發（V3／#51 檢視回饋）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: null, best_return: null,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };

  it("A 封存失敗回滾時，不會讓已成功封存的 B 復活", async () => {
    const rowB = { ...row, id: "s2", symbol: "SPY" };
    let failA: (() => void) | null = null;
    const spy = vi.fn(async (url: string) => {
      if (url.includes("/s1/archive")) {
        // A 停在半空中，讓 B 先完成——回滾若存整份陣列就會蓋回 B
        await new Promise<void>((resolve) => { failA = resolve; });
        return { ok: false, status: 404, json: async () => ({ detail: "劇本不存在" }) };
      }
      if (url.includes("/s2/archive")) {
        return { ok: true, status: 200, json: async () => ({ archived: true }) };
      }
      return { ok: true, status: 200, json: async () => [row, rowB] };
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));
    await userEvent.click(
      screen.getByRole("button", { name: "封存 SPY 2028-05" }));
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();

    failA!();

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();   // A 回來了
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();  // B 沒被復活
  });
});
