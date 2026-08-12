/**
 * Historical IV Position 模組（#114）與它的閘門（#126）。呈現規則見 #133
 * （需求方 2026-08-12 二次修正：不因 coverage／樣本數隱藏 percentile）。
 *
 * 紅線都在這裡守：鎖著時**零 DOM、零 IV 請求**；backfill 狀態
 * （quota／vendor）只是附加說明、**不隱藏**已經算出來的 percentile；
 * 只有 count＝0（完全沒有可比較觀測）才不給 percentile；文案**只陳述
 * 事實**，出現任何評價或可信度判斷字眼就紅燈。
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import IvHistory from "./IvHistory";
import type { Candidate, IvFieldMetric, IvHistoryView } from "./api";

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

/** count＝0、完全沒有可比較觀測時的樣子——四個欄位都一樣。 */
function emptyMetrics(): Record<string, IvFieldMetric> {
  const empty = { value: null, percentile: null, count: 0 };
  return {
    normalized_skew: empty, buy_iv: empty, sell_iv: empty, atm_iv: empty,
  };
}

function ivView(over: Partial<IvHistoryView> = {}): IvHistoryView {
  const points = series(250, (i) => 0.20 + (i % 20) * 0.001);
  const last = points[points.length - 1];
  return {
    candidate_key: KEY,
    status: "ok" as const,
    points,
    metrics: {
      normalized_skew: { value: last.normalized_skew, percentile: 0.62, count: 45 },
      buy_iv: { value: last.buy_iv, percentile: 0.41, count: 45 },
      sell_iv: { value: last.sell_iv, percentile: 0.55, count: 45 },
      atm_iv: { value: last.atm_iv, percentile: 0.5, count: 45 },
    },
    observations: points.length,
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

  it("每一項都有現值、百分位、觀測筆數與 sparkline", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 62 百分位・45 筆觀測/)).toBeInTheDocument());
    expect(screen.getByText(/第 41 百分位・45 筆觀測/)).toBeInTheDocument();
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

describe("完全沒有可比較觀測時：誠實留白，不外插、不硬湊（#133）", () => {
  it("count＝0 時顯示「沒有歷史資料」，不是留白讓人以為還在載入", async () => {
    mockApi({ enabled: true, iv: ivView({ metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0));
  });

  it("sparkline 對缺值斷線，不把斷點連起來", async () => {
    // 中間 100 天缺值 → 應該切成兩段 polyline
    const pts = series(200, (i) => (i >= 50 && i < 150 ? null : 0.2));
    mockApi({ enabled: true, iv: ivView({ points: pts }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-spark")).toBeInTheDocument());
    const first = container.querySelector(".iv-spark")!;
    expect(first.querySelectorAll("polyline").length).toBe(2);
  });
});

describe("不因樣本數或 coverage 隱藏 percentile（需求方 2026-08-12 二次修正）", () => {
  it("只要有觀測，即使只有一兩筆，也顯示 percentile 並揭露筆數", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...emptyMetrics(),
                normalized_skew: { value: 0.08, percentile: 0.9, count: 2 } },
    }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 90 百分位・2 筆觀測/)).toBeInTheDocument());
  });

  it("不出現「樣本不足」「僅供參考」之類的可信度判斷字眼", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...emptyMetrics(),
                normalized_skew: { value: 0.08, percentile: 0.9, count: 1 } },
    }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 90 百分位/)).toBeInTheDocument());
    expect(container.textContent).not.toMatch(
      /樣本不足|資料太少|不夠可信|僅供參考|信心不足|不建議|謹慎參考/);
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

  it("一切正常時顯示累積了幾個觀測，讓人看得到 backfill 的進度", async () => {
    mockApi({ enabled: true, iv: ivView({ observations: 66 }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/近 1 年 66 個觀測/)).toBeInTheDocument());
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

  it("backfill 說明同樣不帶評價", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota" }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/便宜|貴|推薦|建議|值得/);
  });
});

/* ---------- backfill 狀態只是附加說明，不隱藏 percentile（#133） ---------- */

describe("backfill 狀態不隱藏已經算出來的 percentile（需求方 2026-08-12 二次修正）", () => {
  it("額度用完：percentile 照樣顯示，另外多一行附加說明", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota" }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument();
    expect(screen.getByText(/第 62 百分位/)).toBeInTheDocument();
  });

  it("vendor 暫時失敗：與額度用完是不同的說法，percentile 一樣不受影響",
     async () => {
    mockApi({ enabled: true, iv: ivView({ status: "vendor" }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/資料源暫時無法連線/)).toBeInTheDocument());
    expect(screen.queryByText(/今日 API 額度已用完/)).not.toBeInTheDocument();
    expect(screen.getByText(/第 62 百分位/)).toBeInTheDocument();
  });

  it("status 為 ok 時不顯示任何 backfill 附加說明", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "ok" }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.queryByText(/今日 API 額度已用完/)).not.toBeInTheDocument();
    expect(screen.queryByText(/資料源暫時無法連線/)).not.toBeInTheDocument();
  });

  it("即使該欄位完全沒有觀測（count＝0），quota／vendor 狀態下仍誠實說沒有歷史資料，不假裝有",
     async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota", metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={candidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument());
    expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0);
  });

  it("backfill 說明同樣不帶評價字眼", async () => {
    for (const status of ["quota", "vendor"] as const) {
      const { container, unmount } = render(
        <IvHistory scenarioId="s1" candidate={candidate()} />);
      mockApi({ enabled: true, iv: ivView({ status }) });
      await waitFor(() => expect(container).toBeDefined());
      expect(container.textContent).not.toMatch(/便宜|貴|推薦|建議|值得|偏低|偏高/);
      unmount();
    }
  });
});
