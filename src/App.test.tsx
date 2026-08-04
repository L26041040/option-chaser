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
import { baselineTopCandidate, type AnalysisView } from "./api";

const view = sample as unknown as AnalysisView;

function mockFetch(resp: Partial<Response> & { json: () => Promise<unknown> }) {
  const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, ...resp });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("走通骨架畫面", () => {
  it("分析前不顯示任何結果數字", () => {
    render(<App />);
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

    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/analyze");
    const body = JSON.parse(init.body);
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

  it("分析前不顯示候選池", () => {
    render(<App />);
    expect(screen.queryByText("候選池")).not.toBeInTheDocument();
  });
});
