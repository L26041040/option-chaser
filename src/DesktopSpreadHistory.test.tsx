/**
 * OG-07（#325）：桌面「淨成本走勢」底部 tab 元件測試。
 *
 * 跟 `SpreadHistory.test.tsx` 共用同一份 mock fetch 慣例，但兩個關鍵
 * 差異各自對應一個測試：(1) 掛載就抓，不用像 `<details>` 先展開；
 * (2) 單腿候選也渲染——這正是這個新元件相對舊版存在的理由。
 */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import sample from "../contracts/analysis_sample.json";
import DesktopSpreadHistory from "./DesktopSpreadHistory";
import { baselineTopCandidate, type AnalysisView, type Candidate } from "./api";

const view = sample as unknown as AnalysisView;
const spreadCandidate = baselineTopCandidate(view)!;

const HISTORY = {
  entries: [
    { analyzed_at: "2026-07-01T21:30:00-04:00", spot: 100.0, cost: 5.0,
     baseline_return: 0.3, rank_in_expiry: 2 },
    { analyzed_at: "2026-07-08T21:30:00-04:00", spot: 101.0, cost: null,
     baseline_return: null, rank_in_expiry: null },
    { analyzed_at: "2026-07-15T21:30:00-04:00", spot: 99.0, cost: 5.5,
     baseline_return: 0.5, rank_in_expiry: 1 },
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

describe("candidate 為 null", () => {
  it("顯示「無合格候選」，不打任何請求", () => {
    const spy = mockFetch(HISTORY);
    render(<DesktopSpreadHistory scenarioId="s1" candidate={null} />);
    expect(screen.getByText("無合格候選")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("單腿候選也支援（OG-07 明文，相對舊版 SpreadHistory 的關鍵放寬）", () => {
  it("單腿候選一樣掛載圖表區、打帶自己 candidate_key 的 /history", async () => {
    const singleLeg: Candidate = { ...spreadCandidate,
      legs: [spreadCandidate.legs[0]] };
    const spy = mockFetch(HISTORY);
    await act(async () => {
      render(<DesktopSpreadHistory scenarioId="s1" candidate={singleLeg} />);
    });
    expect(spy).toHaveBeenCalledWith(
      `/api/scenarios/s1/history?candidate_key=${
        encodeURIComponent(singleLeg.candidate_key)}`,
      expect.anything());
    expect(await screen.findByText("日")).toBeInTheDocument();
  });
});

describe("掛載就抓，不需要先展開", () => {
  it("渲染後不用任何互動就打了 /history", async () => {
    const spy = mockFetch(HISTORY);
    await act(async () => {
      render(<DesktopSpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    });
    expect(spy).toHaveBeenCalledWith(
      `/api/scenarios/s1/history?candidate_key=${
        encodeURIComponent(spreadCandidate.candidate_key)}`,
      expect.anything());
  });
});

describe("日／週／月切換", () => {
  it("切換粒度不重新打 API", async () => {
    const spy = mockFetch(HISTORY);
    await act(async () => {
      render(<DesktopSpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    });
    await screen.findByText("日");

    await userEvent.click(screen.getByText("月"));

    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("右側統計面板（artifact：今日／N 次刷新區間／缺席快照／首次出現）", () => {
  it("四項數字對齊未降採樣的原始 entries", async () => {
    mockFetch(HISTORY);
    await act(async () => {
      render(<DesktopSpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    });
    await screen.findByText("日");

    // 圖表本身的 x 軸刻度也會印日期文字，統計面板的查詢一律縮小到
    // `.spread-history-panel-stats` 容器，避免跟圖表刻度撞出「找到
    // 多個」的假失敗。
    const stats = within(
      document.querySelector(".spread-history-panel-stats") as HTMLElement);
    expect(stats.getByText("今日")).toBeInTheDocument();
    expect(stats.getByText("$5.50")).toBeInTheDocument();
    expect(stats.getByText("3 次刷新區間")).toBeInTheDocument();
    expect(stats.getByText("$5.00 – $5.50")).toBeInTheDocument();
    expect(stats.getByText("缺席快照")).toBeInTheDocument();
    expect(stats.getByText("1")).toBeInTheDocument();
    expect(stats.getByText("首次出現")).toBeInTheDocument();
    expect(stats.getByText("2026-07-01")).toBeInTheDocument();
  });
});
