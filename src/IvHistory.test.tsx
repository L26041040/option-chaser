/**
 * Historical IV Position 模組（#114）與它的閘門（#126）。呈現規則見 #133
 * （需求方 2026-08-12 二次修正：不因 coverage／樣本數隱藏 percentile）。
 * 一年走勢圖為主體＋Δ4w、Long Call 單腳模式：#140（spec #137）。
 *
 * 紅線都在這裡守：鎖著時**零 DOM、零 IV 請求**；backfill 狀態
 * （quota／vendor）只是附加說明、**不隱藏**已經算出來的 percentile／
 * Δ4w；只有 count＝0（完全沒有可比較觀測）才不給 percentile；文案**只
 * 陳述事實**，出現任何評價或預測字眼就紅燈。
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import IvHistory from "./IvHistory";
import type { Candidate, DiagnosticEvent, IvFieldMetric, IvHistoryPoint,
             IvHistoryView, Leg } from "./api";

const KEY = "bull-call-spread|118C|125C|2026-09-18";

function leg(overrides: Partial<Leg> = {}): Leg {
  return { strike: 118, option_type: "call", expiry: "2026-09-18",
          ask: 5, bid: 4.8, iv: 0.24, volume: 100, open_interest: 500,
          ...overrides };
}

function spreadCandidate(): Candidate {
  return { candidate_key: KEY, legs: [leg(), leg({ strike: 125 })] } as
    unknown as Candidate;
}

function longCallCandidate(): Candidate {
  return { candidate_key: "long-call|118|2026-09-18", legs: [leg()] } as
    unknown as Candidate;
}

function series(n: number, f: (i: number) => number | null): IvHistoryPoint[] {
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
  const empty = { value: null, percentile: null, count: 0,
                 trend_4w: null, trend_base_count: 0 };
  return {
    normalized_skew: empty, buy_iv: empty, sell_iv: empty, atm_iv: empty,
  };
}

function metric(over: Partial<IvFieldMetric> = {}): IvFieldMetric {
  return { value: 0.20, percentile: 0.5, count: 45,
          trend_4w: null, trend_base_count: 0, ...over };
}

function ivView(over: Partial<IvHistoryView> = {}): IvHistoryView {
  const points = series(250, (i) => 0.20 + (i % 20) * 0.001);
  const last = points[points.length - 1];
  return {
    candidate_key: KEY,
    status: "ok" as const,
    points,
    metrics: {
      normalized_skew: metric({ value: last.normalized_skew, percentile: 0.62,
                               trend_4w: 0.06 }),
      buy_iv: metric({ value: last.buy_iv, percentile: 0.41,
                      trend_4w: -0.012 }),
      sell_iv: metric({ value: last.sell_iv, percentile: 0.55,
                       trend_4w: -0.004 }),
      atm_iv: metric({ value: last.atm_iv, percentile: 0.5, trend_4w: 0 }),
    },
    observations: points.length,
    note: null,
    diagnostics: { correlation_id: "cid-test", events: [] },
    ...over,
  };
}

function diagEvent(over: Partial<DiagnosticEvent> = {}): DiagnosticEvent {
  return {
    event_id: "evt-1", correlation_id: "cid-test", ts: "2026-08-15T00:00:00+00:00",
    subsystem: "historical_iv", stage: "payload_parse", severity: "warning",
    message: "raw_rows > 0 but parsed rows are 0",
    context: { raw_rows: 5, parsed_call_rows: 0 },
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
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("未解鎖時一個 IV 請求都不發", async () => {
    const urls = mockApi({ enabled: false });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
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
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(ivCalls(urls)).toEqual([]);
  });

  it("解鎖後才發 IV 請求，且帶著候選的身份鍵", async () => {
    const urls = mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
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

describe("Spread 模式：資訊階層", () => {
  it("Normalized Skew 是頭條", async () => {
    mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
  });

  it("兩腿 IV 是明顯次一層（不與頭條同級）", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() => expect(screen.getByText("買腿 IV")).toBeInTheDocument());
    expect(screen.getByText("賣腿 IV")).toBeInTheDocument();
    // 頭條掛 `iv-primary`，兩腿沒有——階層是結構上的，不是只靠字級
    const primary = container.querySelectorAll(".iv-primary");
    expect(primary).toHaveLength(1);
    expect(primary[0].textContent).toContain("Normalized Skew");
  });

  it("Long Call 模式沒有 Normalized Skew 也沒有賣腿——單腳的意思就是沒有這兩項",
     async () => {
    mockApi({ enabled: true, iv: ivView({
      candidate_key: "long-call|118|2026-09-18",
      metrics: { ...ivView().metrics,
                sell_iv: { value: null, percentile: null, count: 0,
                          trend_4w: null, trend_base_count: 0 },
                normalized_skew: { value: null, percentile: null, count: 0,
                                  trend_4w: null, trend_base_count: 0 } },
    }) });
    render(<IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    await waitFor(() => expect(screen.getByText("買腿 IV")).toBeInTheDocument());
    expect(screen.queryByText("Normalized Skew")).not.toBeInTheDocument();
    expect(screen.queryByText("賣腿 IV")).not.toBeInTheDocument();
    expect(screen.getByText("ATM IV")).toBeInTheDocument();
  });

  it("Long Call 模式買腿 IV 是頭條", async () => {
    mockApi({ enabled: true, iv: ivView() });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    await waitFor(() => expect(screen.getByText("買腿 IV")).toBeInTheDocument());
    const primary = container.querySelectorAll(".iv-primary");
    expect(primary).toHaveLength(1);
    expect(primary[0].textContent).toContain("買腿 IV");
  });

  it("每一項都有現值、百分位、觀測筆數、Δ4w 與一年走勢圖", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 62 百分位・45 筆觀測/)).toBeInTheDocument());
    expect(screen.getByText(/第 41 百分位・45 筆觀測/)).toBeInTheDocument();
    expect(container.querySelectorAll(".iv-trend-chart").length)
      .toBeGreaterThanOrEqual(3);
  });

  it("整塊維持一張卡，手機不長出第二張", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(container.querySelectorAll(".card")).toHaveLength(1);
  });
});

describe("Δ4w（#140／spec #137）", () => {
  it("腿 IV 用帶正負號的 vol 點顯示", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...ivView().metrics,
                buy_iv: metric({ trend_4w: -0.012 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/4週 -1\.2 pts/)).toBeInTheDocument());
  });

  it("正值帶正號", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...ivView().metrics,
                buy_iv: metric({ trend_4w: 0.018 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/4週 \+1\.8 pts/)).toBeInTheDocument());
  });

  it("Normalized Skew 用無因次小數，不是 vol 點", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...ivView().metrics,
                normalized_skew: metric({ trend_4w: 0.06 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/4週 \+0\.06/)).toBeInTheDocument());
    expect(screen.queryByText(/4週 \+6\.0 pts/)).not.toBeInTheDocument();
  });

  it("trend_4w 為 null 時顯示「4週 —」——不是外推，也不是假裝沒有變化",
     async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...ivView().metrics,
                buy_iv: metric({ trend_4w: null }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() => expect(screen.getByText(/4週 —/)).toBeInTheDocument());
  });

  it("方法論註記說明 Δ4w 的定義與基準窗", async () => {
    mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/4週變化＝與約四週前/)).toBeInTheDocument());
    expect(screen.getByText(/21–42 天窗內觀測中位數/)).toBeInTheDocument();
  });

  it("方法論註記誠實說明等待另有 theta 成本與標的價格風險", async () => {
    mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/theta 成本與標的價格風險/)).toBeInTheDocument());
    expect(screen.getByText(/本區塊僅描述 volatility 結構/)).toBeInTheDocument();
  });
});

describe("完全沒有可比較觀測時：誠實留白，不外插、不硬湊（#133）", () => {
  it("count＝0 時顯示「沒有歷史資料」，不是留白讓人以為還在載入", async () => {
    mockApi({ enabled: true, iv: ivView({ metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0));
  });

  it("沒有觀測的欄位不畫走勢圖（沒有東西可畫）", async () => {
    // 真正的「沒有可比較觀測」：`points` 每一筆都是 null，跟
    // `metrics.count === 0` 一致——後端 `field_metrics()` 的 `count`
    // 本來就是從同一份 `points` 直接算出來的，兩者不會對不上。
    const noPoints = series(10, () => null);
    mockApi({ enabled: true,
             iv: ivView({ points: noPoints, metrics: emptyMetrics() }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0));
    expect(container.querySelectorAll(".iv-trend-chart")).toHaveLength(0);
  });

  it("走勢圖對缺值斷線，不把斷點連起來", async () => {
    // 中間 100 天缺值 → 應該切成兩段 polyline
    const pts = series(200, (i) => (i >= 50 && i < 150 ? null : 0.2));
    mockApi({ enabled: true, iv: ivView({ points: pts }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument());
    const first = container.querySelector(".iv-trend-chart")!;
    expect(first.querySelectorAll("polyline").length).toBe(2);
  });
});

describe("不因樣本數或 coverage 隱藏 percentile／Δ4w（需求方 2026-08-12 二次修正）", () => {
  it("只要有觀測，即使只有一兩筆，也顯示 percentile 並揭露筆數", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...emptyMetrics(),
                normalized_skew: metric({ value: 0.08, percentile: 0.9,
                                         count: 2 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 90 百分位・2 筆觀測/)).toBeInTheDocument());
  });

  it("不出現「樣本不足」「僅供參考」之類的可信度判斷字眼", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { ...emptyMetrics(),
                normalized_skew: metric({ value: 0.08, percentile: 0.9,
                                         count: 1 }) },
    }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
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
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/額度用盡/)).toBeInTheDocument());
  });

  it("一切正常時顯示累積了幾個觀測，讓人看得到 backfill 的進度", async () => {
    mockApi({ enabled: true, iv: ivView({ observations: 66 }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/近 1 年 66 個觀測/)).toBeInTheDocument());
  });
});

describe("只陳述事實（紅線，由測試守門而非自律）", () => {
  it("不出現任何評價字眼", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(container.textContent).not.toMatch(
      /便宜|貴|划算|超值|好進場|進場點|推薦|建議|值得|機會|偏低|偏高|過高|過低/);
  });

  it("不出現任何預測語句——Δ4w 是事實不是預言", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(container.textContent).not.toMatch(
      /預期|預測|將會|可能觸底|即將|會再|會繼續|會回升|會下跌|趨勢將/);
  });

  it("backfill 說明同樣不帶評價", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota" }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/便宜|貴|推薦|建議|值得/);
  });
});

/* ---------- backfill 狀態只是附加說明，不隱藏 percentile／Δ4w（#133） ---------- */

describe("backfill 狀態不隱藏已經算出來的 percentile／Δ4w（需求方 2026-08-12 二次修正）", () => {
  it("額度用完：percentile／Δ4w 照樣顯示，另外多一行附加說明", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota" }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument();
    expect(screen.getByText(/第 62 百分位/)).toBeInTheDocument();
  });

  it("vendor 暫時失敗：與額度用完是不同的說法，percentile 一樣不受影響",
     async () => {
    mockApi({ enabled: true, iv: ivView({ status: "vendor" }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/資料源暫時無法連線/)).toBeInTheDocument());
    expect(screen.queryByText(/今日 API 額度已用完/)).not.toBeInTheDocument();
    expect(screen.getByText(/第 62 百分位/)).toBeInTheDocument();
  });

  it("status 為 ok 時不顯示任何 backfill 附加說明", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "ok" }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.queryByText(/今日 API 額度已用完/)).not.toBeInTheDocument();
    expect(screen.queryByText(/資料源暫時無法連線/)).not.toBeInTheDocument();
  });

  it("即使該欄位完全沒有觀測（count＝0），quota／vendor 狀態下仍誠實說沒有歷史資料，不假裝有",
     async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota", metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument());
    expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0);
  });

  it("backfill 說明同樣不帶評價字眼", async () => {
    for (const status of ["quota", "vendor"] as const) {
      const { container, unmount } = render(
        <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
      mockApi({ enabled: true, iv: ivView({ status }) });
      await waitFor(() => expect(container).toBeDefined());
      expect(container.textContent).not.toMatch(/便宜|貴|推薦|建議|值得|偏低|偏高/);
      unmount();
    }
  });
});

describe("走勢圖：Y 軸與 X 軸刻度", () => {
  it("走勢圖有 Y 軸刻度與 X 軸日期刻度", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument());
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.querySelectorAll(".chart-tick-label").length).toBeGreaterThan(0);
  });
});

describe("走勢圖：tooltip（桌面 hover／手機 tap 共用同一套狀態）", () => {
  it("桌面 hover 資料點顯示 tooltip，移開後消失", async () => {
    const smallSeries = series(3, (i) => 0.20 + i * 0.01);
    mockApi({ enabled: true, iv: ivView({ points: smallSeries }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument());
    const chart = container.querySelectorAll(".iv-trend-chart")[0];
    const point = chart.querySelectorAll<HTMLElement>("[role='button']")[0];

    await userEvent.hover(point);
    expect(chart.querySelectorAll(".chart-tooltip").length).toBeGreaterThan(0);

    await userEvent.unhover(point);
    expect(chart.querySelectorAll(".chart-tooltip")).toHaveLength(0);
  });

  it("手機 tap（點按）資料點顯示同樣的 tooltip", async () => {
    const smallSeries = series(3, (i) => 0.20 + i * 0.01);
    mockApi({ enabled: true, iv: ivView({ points: smallSeries }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument());
    const chart = container.querySelectorAll(".iv-trend-chart")[0];
    const point = chart.querySelectorAll<HTMLElement>("[role='button']")[0];

    await userEvent.click(point);
    expect(chart.querySelectorAll(".chart-tooltip").length).toBeGreaterThan(0);
  });
});

describe("就地展開的診斷詳情（DG-05／#148）", () => {
  it("請求失敗時卡片本身仍在，多一條精簡狀態列，預設收合", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return { ok: false, status: 502,
               headers: new Headers({ "X-Correlation-Id": "cid-fail" }),
               json: async () => ({ detail: "額度用盡" }) } as Response;
    }));
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("IV 相對位置")).toBeInTheDocument());
    // 卡片本身仍在（不是整段被錯誤訊息取代掉）。
    expect(container.querySelectorAll(".card")).toHaveLength(1);

    const summary = screen.getByText("Historical IV 資料取得失敗 · 查看詳情");
    expect(summary).toBeInTheDocument();
    const details = container.querySelector(".iv-diagnostics") as HTMLDetailsElement;
    expect(details.open).toBe(false);
  });

  it("點「查看詳情」展開，看得到 correlation ID；再點一次收起", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return { ok: false, status: 502,
               headers: new Headers({ "X-Correlation-Id": "cid-fail-2" }),
               json: async () => ({ detail: "額度用盡" }) } as Response;
    }));
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");

    await userEvent.click(summary);
    expect((container.querySelector(".iv-diagnostics") as HTMLDetailsElement).open)
      .toBe(true);
    expect(screen.getByText(/cid-fail-2/)).toBeInTheDocument();

    await userEvent.click(summary);
    expect((container.querySelector(".iv-diagnostics") as HTMLDetailsElement).open)
      .toBe(false);
  });

  it("200 但帶有 warning／error events 時也觸發診斷區塊——這是「資料是空的」" +
     "最常見的症狀，光看 HTTP 狀態碼看不出來", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-warn",
                    events: [diagEvent()] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() => expect(
      screen.getByText("Historical IV 資料取得失敗 · 查看詳情"),
    ).toBeInTheDocument());
    // 這是 additive 的一塊，資料本身（走勢圖／百分位）照常渲染。
    expect(screen.getByText("Normalized Skew")).toBeInTheDocument();
  });

  it("只有 info severity 的 events 時不觸發診斷區塊", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-info",
                    events: [diagEvent({ severity: "info" })] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.queryByText("Historical IV 資料取得失敗 · 查看詳情"))
      .not.toBeInTheDocument();
  });

  it("展開後看得到事件欄位：timestamp／stage／severity／context", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-fields",
                    events: [diagEvent({
                      context: { raw_rows: 5, parsed_call_rows: 0,
                                vendor_status: "ok" },
                    })] },
    }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);

    expect(screen.getByText("payload_parse")).toBeInTheDocument();
    expect(screen.getByText("warning")).toBeInTheDocument();
    expect(screen.getByText("2026-08-15T00:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByText("raw_rows")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("vendor_status")).toBeInTheDocument();
    void container;
  });

  it("只顯示實際存在的欄位——context 沒帶的 key 不會憑空冒出一列", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-sparse",
                    events: [diagEvent({ context: { raw_rows: 5 } })] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);

    expect(screen.getByText("raw_rows")).toBeInTheDocument();
    expect(screen.queryByText("http_status")).not.toBeInTheDocument();
    expect(screen.queryByText("vendor_errmsg")).not.toBeInTheDocument();
  });

  it("多筆 events 各自完整呈現，不是只顯示第一筆", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-multi",
                    events: [
                      diagEvent({ event_id: "evt-a", stage: "vendor_fetch",
                                context: { http_status: 429 } }),
                      diagEvent({ event_id: "evt-b", stage: "payload_parse",
                                context: { raw_rows: 5 } }),
                    ] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);

    expect(screen.getByText("vendor_fetch")).toBeInTheDocument();
    expect(screen.getByText("payload_parse")).toBeInTheDocument();
    expect(screen.getByText("429")).toBeInTheDocument();
  });
});
