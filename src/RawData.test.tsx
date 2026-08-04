/**
 * 原始資料（當次快照，V8／#56）元件測試——「免得你亂掰我卻查不到證據」
 * （QA1-10／#37 原話）。CSV 內容正確性由既有純函式
 * `data.snapshot.snapshot_to_csv` 的測試覆蓋，這裡只驗接線：展開才抓、
 * 表格與下載連結接得上後端回應。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RawData from "./RawData";

const SAMPLE = {
  meta: { symbol: "XYZ", spot: 100.0, fetched_at: "2026-07-15T21:30:00-04:00",
         source: "cboe", contract_count: 2 },
  contracts: [
    { contract_symbol: "XYZ261016C00110000", option_type: "call", strike: 110.0,
     expiry: "2026-10-16", bid: 3.0, ask: 3.25, last: 3.1, volume: 152,
     open_interest: 830, implied_volatility: 0.38 },
    { contract_symbol: "XYZ261016C00120000", option_type: "call", strike: 120.0,
     expiry: "2026-10-16", bid: null, ask: null, last: null, volume: 0,
     open_interest: 0, implied_volatility: null },
  ],
};

function mockFetch(body: unknown, ok = true, status = 200) {
  const spy = vi.fn(async () => ({ ok, status, json: async () => body }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("原始資料：展開才抓，不主動打", () => {
  it("渲染時不打任何請求——只有展開才抓，省掉平常瀏覽不需要的流量", () => {
    const spy = mockFetch(SAMPLE);
    render(<RawData scenarioId="s1" />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("展開後才打 /raw-data，並顯示 meta 與逐筆合約", async () => {
    const spy = mockFetch(SAMPLE);
    render(<RawData scenarioId="s1" />);

    await userEvent.click(screen.getByText("原始資料（當次快照）"));

    expect(spy).toHaveBeenCalledWith(
      "/api/scenarios/s1/raw-data", expect.anything());
    expect(await screen.findByText("XYZ")).toBeInTheDocument();
    expect(screen.getByText("cboe")).toBeInTheDocument();
    expect(screen.getByText("2 筆")).toBeInTheDocument();
    expect(screen.getByText("XYZ261016C00110000")).toBeInTheDocument();
    expect(screen.getByText("XYZ261016C00120000")).toBeInTheDocument();
  });

  it("再次展開／收合不重複打請求——資料已經在手上了", async () => {
    const spy = mockFetch(SAMPLE);
    render(<RawData scenarioId="s1" />);
    const summary = screen.getByText("原始資料（當次快照）");

    await userEvent.click(summary);   // 展開：抓一次
    await screen.findByText("XYZ");
    await userEvent.click(summary);   // 收合
    await userEvent.click(summary);   // 再展開

    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("CSV 下載連結", () => {
  it("指向 raw-data.csv、帶 download 屬性——純瀏覽器原生下載，不走 JS blob", async () => {
    mockFetch(SAMPLE);
    render(<RawData scenarioId="s1" />);
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ");

    const link = screen.getByText("下載 CSV") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/api/scenarios/s1/raw-data.csv");
    expect(link).toHaveAttribute("download");
  });
});

describe("缺席報價原樣顯示「—」，不假裝有數字", () => {
  it("bid/ask/last/iv 為 null 時顯示「—」", async () => {
    mockFetch(SAMPLE);
    render(<RawData scenarioId="s1" />);
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00120000");

    const row = screen.getByText("XYZ261016C00120000").closest("tr")!;
    // bid／ask／last／iv 四欄皆缺席
    expect(row.textContent?.match(/—/g)?.length).toBe(4);
  });
});

describe("錯誤處理", () => {
  it("尚未分析（404）時如實說明，不是一片空白", async () => {
    mockFetch({ detail: "劇本尚未分析，無原始資料：s1" }, false, 404);
    render(<RawData scenarioId="s1" />);

    await userEvent.click(screen.getByText("原始資料（當次快照）"));

    expect(await screen.findByText(/劇本尚未分析/)).toBeInTheDocument();
  });
});
