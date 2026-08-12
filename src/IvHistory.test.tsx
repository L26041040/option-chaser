/**
 * Historical IV Position 模組（#114）與它的閘門（#126）。
 *
 * 兩條紅線在這裡守：鎖著時**零 DOM、零 IV 請求**；文案**只陳述事實**，
 * 出現任何評價字眼就紅燈。
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import IvHistory from "./IvHistory";
import type { Candidate, IvHistoryView } from "./api";

const KEY = "bull-call-spread|118C|125C|2026-09-18";

function candidate(): Candidate {
  return { candidate_key: KEY, legs: [] } as unknown as Candidate;
}

function series(n: number, f: (i: number) => number | null) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    buy_iv: f(i),
    sell_iv: f(i) === null ? null : (f(i) as number) + 0.02,
    atm_iv: 0.25,
    normalized_skew: f(i) === null ? null : 0.08 + i * 0.0001,
  }));
}

function ivView(over: Partial<IvHistoryView> = {}): IvHistoryView {
  const points = series(250, (i) => 0.20 + (i % 20) * 0.001);
  return {
    candidate_key: KEY,
    window_days: 365,
    points,
    current: points[points.length - 1],
    percentiles: { normalized_skew: 0.62, buy_iv: 0.41, sell_iv: 0.55,
                   atm_iv: 0.5 },
    out_of_grid: false,
    note: null,
    ...over,
  };
}

/** 記錄每一個被打到的 URL，讓「鎖著時零 IV 請求」變成可斷言的事實。 */
function mockApi({ enabled, iv }: { enabled: boolean; iv?: IvHistoryView }) {
  const urls: string[] = [];
  const spy = vi.fn(async (url: string) => {
    urls.push(url);
    if (url.startsWith("/api/settings")) {
      return { ok: true, status: 200,
               json: async () => ({ historical_iv_enabled: enabled }) } as Response;
    }
    return { ok: true, status: 200,
             json: async () => iv ?? ivView() } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return urls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ivCalls = (urls: string[]) => urls.filter((u) => u.includes("iv-history"));

describe("閘門（#126）", () => {
  it("未解鎖時不輸出任何 DOM 節點", async () => {
    mockApi({ enabled: false });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("未解鎖時一個 IV 請求都不發", async () => {
    const urls = mockApi({ enabled: false });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() => expect(urls.some((u) => u.includes("/api/settings")))
      .toBe(true));
    expect(ivCalls(urls)).toEqual([]);
  });

  it("設定讀不到時當成鎖著，不對 vendor 試手氣", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url);
      return { ok: false, status: 500,
               json: async () => ({ detail: "掛了" }) } as Response;
    }));
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(ivCalls(urls)).toEqual([]);
  });

  it("解鎖後才發 IV 請求，且帶著候選的身份鍵", async () => {
    const urls = mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() => expect(ivCalls(urls)).toHaveLength(1));
    expect(ivCalls(urls)[0]).toContain(encodeURIComponent(KEY));
  });

  it("沒有候選時不發請求也不渲染", async () => {
    const urls = mockApi({ enabled: true });
    const { container } = render(<IvHistory scenarioId="s1" candidate={null} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(ivCalls(urls)).toEqual([]);
  });
});

describe("資訊階層", () => {
  it("Normalized Skew 是頭條", async () => {
    mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
  });

  it("兩腿 IV 是明顯次一層（不與頭條同級）", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() => expect(screen.getByText("買腿 IV")).toBeInTheDocument());
    expect(screen.getByText("賣腿 IV")).toBeInTheDocument();
    // 頭條掛 `iv-primary`，兩腿沒有——階層是結構上的，不是只靠字級
    const primary = container.querySelectorAll(".iv-primary");
    expect(primary).toHaveLength(1);
    expect(primary[0].textContent).toContain("Normalized Skew");
  });

  it("每一項都有現值、1 年百分位與 sparkline", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 62 百分位/)).toBeInTheDocument());
    expect(screen.getByText(/第 41 百分位/)).toBeInTheDocument();
    expect(container.querySelectorAll(".iv-spark").length).toBeGreaterThanOrEqual(3);
  });

  it("整塊維持 compact：只有一張卡，手機不長出第二張", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(container.querySelectorAll(".card")).toHaveLength(1);
  });
});

describe("超出可比網格：留白並標明，不外插", () => {
  it("沒有百分位時明說超出可比網格", async () => {
    mockApi({
      enabled: true,
      iv: ivView({ percentiles: { normalized_skew: null, buy_iv: null,
                                  sell_iv: null, atm_iv: null } }),
    });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("超出可比網格").length).toBeGreaterThan(0));
  });

  it("整段出界時另外說明原因，不是靜靜留白", async () => {
    mockApi({ enabled: true, iv: ivView({ out_of_grid: true }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/超出資料源的可比網格/)).toBeInTheDocument());
  });

  it("sparkline 對缺值斷線，不把斷點連起來", async () => {
    // 中間 100 天缺值 → 應該切成兩段 polyline
    const pts = series(200, (i) => (i >= 50 && i < 150 ? null : 0.2));
    mockApi({ enabled: true, iv: ivView({ points: pts, current: pts[199] }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-spark")).toBeInTheDocument());
    const first = container.querySelector(".iv-spark")!;
    expect(first.querySelectorAll("polyline").length).toBe(2);
  });
});

describe("vendor 失敗", () => {
  it("說明原因，而且不拖垮頁面其餘部分", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return { ok: false, status: 502,
               json: async () => ({ detail: "額度用盡" }) } as Response;
    }));
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/額度用盡/)).toBeInTheDocument());
  });

  it("部分天數缺漏時如實說出來", async () => {
    mockApi({ enabled: true, iv: ivView({ note: "有 12 天取不到資料：逾時" }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/有 12 天取不到資料/)).toBeInTheDocument());
  });
});

describe("只陳述事實（紅線，由測試守門而非自律）", () => {
  it("不出現任何評價字眼", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(container.textContent).not.toMatch(
      /便宜|貴|划算|超值|好進場|進場點|推薦|建議|值得|機會|偏低|偏高|過高|過低/);
  });

  it("vendor 失敗的說明同樣不帶評價", async () => {
    mockApi({ enabled: true, iv: ivView({ out_of_grid: true }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/超出資料源的可比網格/)).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/便宜|貴|推薦|建議|值得/);
  });
});
