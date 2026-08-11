/**
 * Spread 淨成本走勢圖（V9／#57）元件測試。用真實契約樣本的候選當底
 * （已有正確的 `candidate_key`／兩隻腿），歷史資料本身手刻——這個
 * 元件不關心候選細節，只關心它傳給 `getSpreadHistory` 的 key 對不對、
 * 拿到資料後日／週／月切換與斷點呈現對不對。
 */
import { render, screen, within } from "@testing-library/react";
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

    expect(await screen.findByText(/這段期間沒有資料/)).toBeInTheDocument();
  });

  it("從未分析過（空歷史）時如實說明", async () => {
    mockFetch({ entries: [] });
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));

    expect(await screen.findByText(/還沒有歷史紀錄/)).toBeInTheDocument();
  });
});

describe("圖表：Y 軸刻度與單位（MVP V3／#106）", () => {
  it("顯示 Net Cost ($/share) 單位標籤與三個刻度（低／中／高，固定範圍）", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");

    expect(within(svg).getByText("Net Cost ($/share)")).toBeInTheDocument();
    // y 軸範圍固定＝[最低×0.85, 最高×1.15]（既有 yAxisDomain 公式），
    // 這份 fixture 有效值是 5.0／5.5，低與高兩端的刻度必須讀得到。
    expect(within(svg).getByText("$4.25")).toBeInTheDocument();
    expect(within(svg).getByText("$6.32")).toBeInTheDocument();
  });
});

describe("圖表：X 軸日期刻度（MVP V3／#106）", () => {
  it("顯示日期刻度，涵蓋序列頭尾", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");

    expect(within(svg).getByText("2026-07-01")).toBeInTheDocument();
    expect(within(svg).getByText("2026-07-15")).toBeInTheDocument();
  });
});

describe("圖表：tooltip（MVP V3／#106，桌面 hover／手機 tap 共用同一套狀態）", () => {
  it("桌面 hover 資料點顯示含日期與淨成本的 tooltip，移開後消失", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");
    const point = within(svg).getByRole("button", { name: /2026-07-01/ });

    expect(within(svg).queryByText(/日期 2026-07-01/)).not.toBeInTheDocument();

    await userEvent.hover(point);
    expect(within(svg).getByText(/日期 2026-07-01/)).toBeInTheDocument();
    expect(within(svg).getByText(/淨成本 \$5\.00/)).toBeInTheDocument();

    await userEvent.unhover(point);
    expect(within(svg).queryByText(/日期 2026-07-01/)).not.toBeInTheDocument();
  });

  it("手機 tap（點按）資料點顯示同樣內容的 tooltip", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");
    const point = within(svg).getByRole("button", { name: /2026-07-15/ });

    await userEvent.click(point);
    expect(within(svg).getByText(/日期 2026-07-15/)).toBeInTheDocument();
    expect(within(svg).getByText(/淨成本 \$5\.50/)).toBeInTheDocument();
  });

  it("點按另一個資料點，tooltip 內容跟著換成那一點的日期與淨成本", async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");

    await userEvent.click(within(svg).getByRole("button", { name: /2026-07-01/ }));
    expect(within(svg).getByText(/日期 2026-07-01/)).toBeInTheDocument();

    await userEvent.click(within(svg).getByRole("button", { name: /2026-07-15/ }));
    expect(within(svg).queryByText(/日期 2026-07-01/)).not.toBeInTheDocument();
    expect(within(svg).getByText(/日期 2026-07-15/)).toBeInTheDocument();
  });

  it("斷點那一筆沒有畫出資料點，不會出現一個永遠拿不到內容的 tooltip 觸發點",
     async () => {
    mockFetch(HISTORY);
    render(<SpreadHistory scenarioId="s1" candidate={spreadCandidate} />);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    const svg = await screen.findByRole("img");

    expect(within(svg).queryByRole("button", { name: /2026-07-08/ }))
      .not.toBeInTheDocument();
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
