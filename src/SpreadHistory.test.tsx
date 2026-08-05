/**
 * Spread 淨成本走勢圖（V9／#57）元件測試。用真實契約樣本的候選當底
 * （已有正確的 `candidate_key`／兩隻腿），歷史資料本身手刻——這個
 * 元件不關心候選細節，只關心它傳給 `getSpreadHistory` 的 key 對不對、
 * 拿到資料後日／週／月切換與斷點呈現對不對。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import sample from "../contracts/analysis_sample.json";
import SpreadHistory from "./SpreadHistory";
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

describe("單腳候選沒有 Spread 身份鍵——整塊不顯示", () => {
  it("candidate 為 null 時不渲染", () => {
    const { container } = render(
      <SpreadHistory scenarioId="s1" candidate={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("單腳候選（只有一隻腿）不渲染——T9 附錄A13 既有 MVP 範圍", () => {
    const singleLeg: Candidate = { ...spreadCandidate,
      legs: [spreadCandidate.legs[0]] };
    const { container } = render(
      <SpreadHistory scenarioId="s1" candidate={singleLeg} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("展開才抓，帶正確的身份鍵", () => {
  it("展開才打 /history，query 帶候選自己的 candidate_key", async () => {
    const spy = mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    expect(spy).toHaveBeenCalledWith(
      `/api/scenarios/s1/history?candidate_key=${
        encodeURIComponent(spreadCandidate.candidate_key)}`,
      expect.anything());
  });

  it("渲染時不主動打請求", () => {
    const spy = mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("日／週／月切換", () => {
  it("預設「日」，三個選項都在，可以切換", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByText("日");

    const day = screen.getByText("日");
    const week = screen.getByText("週");
    expect(screen.getByText("月")).toBeInTheDocument();
    expect(day).toHaveAttribute("aria-pressed", "true");
    expect(week).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(week);
    expect(week).toHaveAttribute("aria-pressed", "true");
    expect(day).toHaveAttribute("aria-pressed", "false");
  });

  it("切換粒度不重新打 API——資料已經在手上，只是換一種分組方式", async () => {
    const spy = mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByText("日");

    await userEvent.click(screen.getByText("月"));

    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("圖表：斷點如實顯示", () => {
  it("三筆資料畫出三個點，中間斷點那筆仍有座標但折線在那裡斷開", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    const svg = await screen.findByRole("img");
    // 三筆裡兩筆有效值——只有兩個點畫得出來，斷點那筆不貢獻一個點。
    expect(svg.querySelectorAll("circle")).toHaveLength(2);
    // 斷點把序列切成兩段，各自一條 <polyline>，不是一條連通的折線。
    expect(svg.querySelectorAll("polyline")).toHaveLength(2);
  });

  it("全部缺席時說明沒有可畫的資料，不是空白或報錯", async () => {
    mockFetch({ entries: [
      { analyzed_at: "2026-07-01T21:30:00-04:00", spot: 100.0, cost: null,
       baseline_return: null, rank_in_expiry: null },
    ] });
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    expect(await screen.findByText(/沒有可畫的資料/)).toBeInTheDocument();
  });

  it("從未分析過（空歷史）時如實說明", async () => {
    mockFetch({ entries: [] });
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    expect(await screen.findByText(/還沒有歷史紀錄/)).toBeInTheDocument();
  });
});

describe("錯誤處理", () => {
  it("請求失敗時如實顯示錯誤，不是一片空白", async () => {
    mockFetch({ detail: "劇本不存在：s1" }, false, 404);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    expect(await screen.findByText(/劇本不存在/)).toBeInTheDocument();
  });
});
