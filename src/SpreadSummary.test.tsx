/**
 * Spread Summary（SIG-03／#174，spec #171）：`spread_gap` API 區塊
 * 接進卡片頭條。元件層測試——不透過 `IvHistory` 的 fetch 生命週期，
 * 直接餵 props（跟 `IvTrend.test.tsx` 同一種邊界慣例）。
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ContractIdentity, IvHistoryLegs, LegHistoricalIv,
             SpreadGap, SpreadGapDeltaStatus } from "./api";
import SpreadSummary, { SpreadSummaryAdvanced } from "./SpreadSummary";
import { SPREAD_CHART_HEIGHT_DESKTOP, SPREAD_CHART_HEIGHT_MOBILE } from "./IvTrend";
import { fakeMediaQueryList } from "./test-setup";

afterEach(() => {
  vi.unstubAllGlobals();
});

function contract(overrides: Partial<ContractIdentity> = {}): ContractIdentity {
  return { underlying: "XYZ", expiration: "2026-09-18", strike: 118,
          option_type: "call", contract_symbol: "XYZ260918C00118000",
          ...overrides };
}

function legHistoricalIv(overrides: Partial<LegHistoricalIv> = {}): LegHistoricalIv {
  return {
    contract: contract(),
    points: [],
    moving_average: [],
    bollinger_upper: [],
    bollinger_lower: [],
    current_percentile: 0.5,
    current_zscore: 0.3,
    delta_4w: 0.01,
    observation_count: 184,
    history_span_days: 240,
    lookback_days_config: 30,
    status: "ok",
    note: null,
    ...overrides,
  };
}

function legs(overrides: Partial<IvHistoryLegs> = {}): IvHistoryLegs {
  return {
    buy: legHistoricalIv({ observation_count: 184 }),
    sell: legHistoricalIv({
      observation_count: 176, contract: contract({ strike: 125 }),
    }),
    ...overrides,
  };
}

function spreadGap(overrides: Partial<SpreadGap> = {}): SpreadGap {
  const points = Array.from({ length: 161 }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    gap: 0.05 + (i % 20) * 0.0005,
  }));
  return {
    points,
    moving_average: [],
    bollinger_upper: [],
    bollinger_lower: [],
    current_percentile: 0.6,
    delta_4w: 0.02,
    delta_4w_ratio: 0.4,
    delta_4w_status: "ok",
    observation_count: 161,
    shared_history_span_days: 240,
    ...overrides,
  };
}

describe("IV Gap 現值：points[-1] 是正式契約保證的現值來源", () => {
  it("取最後一筆的 gap，不是掃描找最新非 null", () => {
    const sg = spreadGap({ points: [
      { date: "2026-01-01", gap: 0.10 },
      { date: "2026-01-02", gap: 0.13 },
    ] });
    render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(screen.getByText("13.0%")).toBeInTheDocument();
    expect(screen.queryByText("10.0%")).not.toBeInTheDocument();
  });

  it("points 為空時現值顯示沒有資料", () => {
    const sg = spreadGap({ points: [], current_percentile: null,
                           delta_4w: null, delta_4w_ratio: null,
                           delta_4w_status: "no_baseline", observation_count: 0,
                           shared_history_span_days: 0 });
    const { container } = render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(container.querySelector(".iv-value-primary")?.textContent).toBe("—");
  });
});

describe("完整 IV Gap 走勢圖：重用既有多序列走勢圖幾何", () => {
  it("points 非空時畫出走勢圖", () => {
    const { container } = render(
      <SpreadSummary spreadGap={spreadGap()} legs={legs()} />);
    expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument();
  });

  it("points 為空時不畫空框", () => {
    const sg = spreadGap({ points: [] });
    const { container } = render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(container.querySelector(".iv-trend-chart")).not.toBeInTheDocument();
  });
});

describe("四種 delta_4w_status 狀態各自的文案（手機文字瘦身後搬進 SpreadSummaryAdvanced）", () => {
  const cases: [SpreadGapDeltaStatus, number | null, string][] = [
    ["ok", 0.40, "+40%"],
    ["no_baseline", null, "—"],
    ["near_zero_base", null, "—"],
    ["sign_flip", null, "方向翻轉"],
  ];

  it.each(cases)("status=%s → %s", (status, ratio, expected) => {
    const sg = spreadGap({ delta_4w_status: status, delta_4w_ratio: ratio,
                           delta_4w: status === "no_baseline" ? null : 0.02 });
    render(<SpreadSummaryAdvanced spreadGap={sg} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("ok 狀態下負的 ratio 換算成帶負號的百分比", () => {
    const sg = spreadGap({ delta_4w_status: "ok", delta_4w_ratio: -0.15,
                           delta_4w: -0.03 });
    render(<SpreadSummaryAdvanced spreadGap={sg} />);
    expect(screen.getByText("-15%")).toBeInTheDocument();
  });

  it("四種狀態下 delta_4w（絕對值 vol-point）都正常顯示，不受 status 影響", () => {
    for (const status of ["ok", "near_zero_base", "sign_flip"] as const) {
      const sg = spreadGap({ delta_4w_status: status, delta_4w: 0.025 });
      const { unmount } = render(<SpreadSummary spreadGap={sg} legs={legs()} />);
      expect(screen.getByText("4週 +2.5 pts")).toBeInTheDocument();
      unmount();
    }
  });

  it("主卡片（SpreadSummary）不再顯示 ratio 版本的 Δ4w——瘦身後只留一個 4 週數字", () => {
    const sg = spreadGap({ delta_4w_status: "ok", delta_4w_ratio: 0.40,
                           delta_4w: 0.02 });
    render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(screen.queryByText("+40%")).not.toBeInTheDocument();
  });
});

describe("百分位：直接顯示 spread_gap.current_percentile", () => {
  it("有值時格式化成第 N 百分位", () => {
    const sg = spreadGap({ current_percentile: 0.62 });
    render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(screen.getByText("第 62 百分位")).toBeInTheDocument();
  });

  it("為 null 時顯示沒有歷史資料，跟既有逐腿卡片同一種說法", () => {
    const sg = spreadGap({ current_percentile: null });
    render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(screen.getByText(/沒有歷史資料/)).toBeInTheDocument();
  });
});

describe("涵蓋揭露小字：讀 shared_history_span_days，不是 history_span_days", () => {
  it("組成 Buy／Sell／Shared／涵蓋時間", () => {
    const sg = spreadGap({ observation_count: 161, shared_history_span_days: 240 });
    render(<SpreadSummary spreadGap={sg} legs={legs({
      buy: legHistoricalIv({ observation_count: 184 }),
      sell: legHistoricalIv({ observation_count: 176 }),
    })} />);
    expect(screen.getByText("Buy 184・Sell 176・Shared 161・近 8 個月"))
      .toBeInTheDocument();
  });

  it("shared_history_span_days 為 0 時（observation_count 0／1）不附涵蓋時間片段",
     () => {
    const sg = spreadGap({ observation_count: 0, shared_history_span_days: 0 });
    render(<SpreadSummary spreadGap={sg} legs={legs()} />);
    expect(screen.getByText(/^Buy \d+・Sell \d+・Shared 0$/)).toBeInTheDocument();
  });
});

describe("手機版圖高度明顯縮小（Historical IV 圖表改版），桌面維持原高度", () => {
  it("手機（預設 matchMedia 假體＝手機）走勢圖用較矮的高度", () => {
    const { container } = render(
      <SpreadSummary spreadGap={spreadGap()} legs={legs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("viewBox"))
      .toBe(`0 0 300 ${SPREAD_CHART_HEIGHT_MOBILE}`);
  });

  it("桌面斷點下維持既有較高的高度", () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    const { container } = render(
      <SpreadSummary spreadGap={spreadGap()} legs={legs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("viewBox"))
      .toBe(`0 0 300 ${SPREAD_CHART_HEIGHT_DESKTOP}`);
  });
});

describe("固定 facts-only 說明文字（手機文字瘦身後搬進 SpreadSummaryAdvanced）", () => {
  it("SpreadSummaryAdvanced 解釋 Spread Percentile 語意，不下判斷、不預測", () => {
    render(<SpreadSummaryAdvanced spreadGap={spreadGap()} />);
    expect(screen.getByText(
      /Spread Percentile：目前兩腿 IV 差距，在這兩張 exact contracts 共同存在的歷史期間中位於什麼位置。/,
    )).toBeInTheDocument();
  });

  it("主卡片（SpreadSummary）不再顯示這句解釋——瘦身後只留主要事實", () => {
    render(<SpreadSummary spreadGap={spreadGap()} legs={legs()} />);
    expect(screen.queryByText(/Spread Percentile：/)).not.toBeInTheDocument();
  });
});
