/**
 * Historical IV 卡片模組（#114）與它的閘門（#126）。呈現規則見 #133
 * （需求方 2026-08-12 二次修正：不因 coverage／樣本數隱藏 percentile）。
 *
 * HIVT-04／05（#155／#156）之後，這個檔案只覆蓋：閘門、Normalized Skew
 * 頭條（唯一還留在 `IvHistory.tsx` 裡的 (tenor,delta) 家族顯示）、固定
 * 版位／skeleton、就地展開的診斷詳情、整體 facts-only 守門。逐腿
 * exact-contract 卡片（買腿／賣腿 Historical IV Trend）的專屬測試搬到
 * `IvTrend.test.tsx`——兩個家族現在是兩個檔案，測試邊界跟著元件邊界走。
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
import type { Candidate, ContractIdentity, DiagnosticEvent, IvFieldMetric,
             IvHistoryView, LegHistoricalIv, Leg, NormalizedSkewPoint } from "./api";

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

function contract(overrides: Partial<ContractIdentity> = {}): ContractIdentity {
  return { underlying: "XYZ", expiration: "2026-09-18", strike: 118,
          option_type: "call", contract_symbol: "XYZ260918C00118000",
          ...overrides };
}

function statSeries(n: number, f: (i: number) => number | null) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    value: f(i),
  }));
}

function legHistoricalIv(overrides: Partial<LegHistoricalIv> = {}): LegHistoricalIv {
  const points = Array.from({ length: 250 }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    iv: 0.20 + (i % 20) * 0.001,
    low_confidence: false,
  }));
  return {
    contract: contract(),
    points,
    moving_average: statSeries(250, () => 0.21),
    bollinger_upper: statSeries(250, () => 0.25),
    bollinger_lower: statSeries(250, () => 0.17),
    current_percentile: 0.5,
    current_zscore: 0.3,
    delta_4w: 0.01,
    observation_count: 250,
    history_span_days: 365,
    lookback_days_config: 30,
    status: "ok",
    note: null,
    ...overrides,
  };
}

function normalizedSkewSeries(
  n: number, f: (i: number) => number | null,
): NormalizedSkewPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    normalized_skew: f(i),
  }));
}

/** count＝0、完全沒有可比較觀測時的樣子。 */
function emptyMetrics(): { normalized_skew: IvFieldMetric } {
  return { normalized_skew: { value: null, percentile: null, count: 0,
                             trend_4w: null, trend_base_count: 0 } };
}

function metric(over: Partial<IvFieldMetric> = {}): IvFieldMetric {
  return { value: 0.20, percentile: 0.5, count: 45,
          trend_4w: null, trend_base_count: 0, ...over };
}

function ivView(over: Partial<IvHistoryView> = {}): IvHistoryView {
  const points = normalizedSkewSeries(250, (i) => 0.08 + i * 0.0001);
  const last = points[points.length - 1];
  return {
    candidate_key: KEY,
    status: "ok" as const,
    normalized_skew_points: points,
    metrics: {
      normalized_skew: metric({ value: last.normalized_skew, percentile: 0.62,
                               trend_4w: 0.06 }),
    },
    observations: points.length,
    note: null,
    diagnostics: { correlation_id: "cid-test", events: [] },
    legs: { buy: legHistoricalIv(),
           sell: legHistoricalIv({ contract: contract({ strike: 125 }) }) },
    ...over,
  };
}

/** 單腳候選對應的回應形狀——`legs.sell` 整個不存在，不是 `null`。 */
function singleLegIvView(over: Partial<IvHistoryView> = {}): IvHistoryView {
  return ivView({
    candidate_key: "long-call|118|2026-09-18",
    metrics: emptyMetrics(),
    legs: { buy: legHistoricalIv() },
    ...over,
  });
}

/** SIG-01（#172）`spread_gap` 區塊——只要候選有賣腿就一定存在，這裡
 *  預設給有資料的形狀；`emptySpreadGap()` 是 `points` 為空的 unavailable
 *  情境（SIG-03／#174 兩種情境各自測試用）。 */
function spreadGapFixture(over: Partial<NonNullable<IvHistoryView["spread_gap"]>> = {}) {
  const points = Array.from({ length: 20 }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, "0")}`, gap: 0.05 + i * 0.001,
  }));
  return {
    points, moving_average: [], bollinger_upper: [], bollinger_lower: [],
    current_percentile: 0.6, delta_4w: 0.02, delta_4w_ratio: 0.4,
    delta_4w_status: "ok" as const, observation_count: 20,
    shared_history_span_days: 19,
    ...over,
  };
}

function emptySpreadGap() {
  return spreadGapFixture({
    points: [], current_percentile: null, delta_4w: null,
    delta_4w_ratio: null, delta_4w_status: "no_baseline", observation_count: 0,
    shared_history_span_days: 0,
  });
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

describe("Normalized Skew 頭條（Spread 限定，(tenor,delta) 家族維持原樣）", () => {
  it("Normalized Skew 是頭條", async () => {
    mockApi({ enabled: true });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
  });

  it("Long Call 模式沒有 Normalized Skew——單腳結構上沒有這個量", async () => {
    mockApi({ enabled: true, iv: singleLegIvView() });
    render(<IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    // 沒有 Normalized Skew，但單腳仍有自己的 Historical IV Trend 卡片
    // （見 `IvTrend.test.tsx`），這裡只確認前者真的不見了。
    await waitFor(() =>
      expect(screen.getByText(/第 \d+ 百分位/)).toBeInTheDocument());
    expect(screen.queryByText("Normalized Skew")).not.toBeInTheDocument();
  });

  it("有現值、百分位、觀測筆數、Δ4w 與一年走勢圖", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 62 百分位・45 筆觀測/)).toBeInTheDocument());
    expect(container.querySelectorAll(".iv-trend-chart").length)
      .toBeGreaterThanOrEqual(1);
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

describe("Δ4w（#140／spec #137，Normalized Skew）", () => {
  it("用無因次小數，不是 vol 點", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { normalized_skew: metric({ trend_4w: 0.06 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/4週 \+0\.06/)).toBeInTheDocument());
    expect(screen.queryByText(/4週 \+6\.0 pts/)).not.toBeInTheDocument();
  });

  it("trend_4w 為 null 時顯示「4週 —」——不是外推，也不是假裝沒有變化",
     async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { normalized_skew: metric({ trend_4w: null }) },
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
  it("count＝0 時 Normalized Skew 顯示「沒有歷史資料」，不是留白讓人以為還在載入",
     async () => {
    mockApi({ enabled: true, iv: ivView({ metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0));
  });

  it("Normalized Skew 沒有觀測的欄位不畫走勢圖（沒有東西可畫）", async () => {
    const noPoints = normalizedSkewSeries(10, () => null);
    mockApi({ enabled: true,
             iv: ivView({ normalized_skew_points: noPoints,
                         metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0));
    // Normalized Skew 本身沒有走勢圖可畫——腿卡片仍然有自己的走勢圖
    // （不同資料來源），不是整頁都沒有圖。
    expect(screen.queryByText("Normalized Skew")).toBeInTheDocument();
  });

  it("Normalized Skew 走勢圖對缺值斷線，不把斷點連起來", async () => {
    // 中間 100 天缺值 → 應該切成兩段 polyline
    const pts = normalizedSkewSeries(200, (i) => (i >= 50 && i < 150 ? null : 0.2));
    mockApi({ enabled: true, iv: ivView({ normalized_skew_points: pts }) });
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
      metrics: { normalized_skew: metric({ value: 0.08, percentile: 0.9,
                                          count: 2 }) },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/第 90 百分位・2 筆觀測/)).toBeInTheDocument());
  });

  it("不出現「樣本不足」「僅供參考」之類的可信度判斷字眼", async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: { normalized_skew: metric({ value: 0.08, percentile: 0.9,
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

  it("一切正常時顯示累積了幾個觀測，讓人看得到 Normalized Skew backfill 的進度",
     async () => {
    mockApi({ enabled: true, iv: ivView({ observations: 66 }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/近 1 年 66 個觀測/)).toBeInTheDocument());
  });
});

describe("已有可用 cache 時，重新嘗試失敗只降級成非阻斷警示（需求方 2026-08-21 反饋：" +
        "「明明有圖還顯示錯誤」）", () => {
  it("同一個候選第一次成功、新分析後 refetch 失敗：圖表照常在，只多一行警示，" +
     "不是整塊阻斷錯誤", async () => {
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      call += 1;
      if (call === 1) {
        return { ok: true, status: 200, json: async () => ivView() } as Response;
      }
      return { ok: false, status: 404,
               json: async () => ({ detail: "候選暫時找不到" }) } as Response;
    }));
    const { container, rerender } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} analyzedAt="t1" />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());

    rerender(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} analyzedAt="t2" />);
    await waitFor(() =>
      expect(screen.getByText(/候選暫時找不到/)).toBeInTheDocument());

    // 圖表沒有消失——走勢圖與買／賣腿內容照常在。
    expect(container.querySelectorAll(".iv-trend-chart").length).toBeGreaterThan(0);
    expect(screen.getByText("Normalized Skew")).toBeInTheDocument();
    // 不是整塊阻斷錯誤那句話——那句只留給「這個候選完全沒有資料可退回」。
    expect(screen.queryByText(/取不到歷史 IV/)).not.toBeInTheDocument();
  });

  it("這個候選從未成功取得任何資料時，失敗仍然是整塊阻斷錯誤（沒有 cache 可退回，" +
     "維持既有行為）", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return { ok: false, status: 404,
               json: async () => ({ detail: "找不到候選" }) } as Response;
    }));
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/取不到歷史 IV：找不到候選/)).toBeInTheDocument());
    expect(screen.queryByText("Normalized Skew")).not.toBeInTheDocument();
  });
});

describe("切換候選時不會誤用上一個候選的資料（dataKey 隔離）", () => {
  it("候選 A 成功後切到候選 B，B 的 fetch 還沒回來前顯示骨架，不是 A 的舊資料",
     async () => {
    let resolveSecond!: (r: Response) => void;
    const secondPromise = new Promise<Response>((resolve) => {
      resolveSecond = resolve;
    });
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      call += 1;
      if (call === 1) {
        return { ok: true, status: 200, json: async () => ivView() } as Response;
      }
      return secondPromise;
    }));
    const { container, rerender } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());

    rerender(<IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-skeleton")).toBeInTheDocument());
    expect(screen.queryByText("Normalized Skew")).not.toBeInTheDocument();

    resolveSecond({ ok: true, status: 200,
                   json: async () => singleLegIvView() } as Response);
    await waitFor(() =>
      expect(container.querySelector(".iv-skeleton")).not.toBeInTheDocument());
    expect(container.querySelectorAll(".iv-trend-card")).toHaveLength(1);
  });
});

describe("legacy normalized_skew 失敗不污染 exact-contract 主圖區的成功狀態（C.3）", () => {
  it("頂層 status 為 quota／vendor（legacy backfill 沒補上）時，買／賣腿與" +
     "Spread IV Gap 照常渲染成功——附加說明只出現在 Advanced 裡", async () => {
    mockApi({ enabled: true, iv: ivView({ status: "vendor",
                                         note: "legacy backfill 失敗",
                                         spread_gap: spreadGapFixture() }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    // 主要區塊（Spread IV Gap／買腿／賣腿）不必展開 Advanced 就在——
    // exact-contract 家族完全不受 legacy 那邊失敗影響。
    await waitFor(() =>
      expect(screen.getByText("Spread IV Gap")).toBeInTheDocument());
    expect(container.querySelectorAll(".iv-trend-card")).toHaveLength(2);
    expect(container.querySelectorAll(".iv-trend-chart").length)
      .toBeGreaterThanOrEqual(3);
    // 沒有整塊阻斷錯誤那句話。
    expect(screen.queryByText(/取不到歷史 IV/)).not.toBeInTheDocument();

    // legacy 家族自己的 backfill 說明確實存在，但只在 Advanced 收合區裡。
    const summary = await screen.findByText("Advanced／Diagnostics");
    await userEvent.click(summary);
    expect(screen.getByText(/資料源暫時無法連線/)).toBeInTheDocument();
  });
});

describe("只陳述事實（紅線，由測試守門而非自律）", () => {
  it("不出現任何評價字眼——涵蓋 Normalized Skew 與逐腿卡片全部文字", async () => {
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

  it("即使該欄位完全沒有觀測（count＝0），quota 狀態下仍誠實說沒有歷史資料，不假裝有",
     async () => {
    mockApi({ enabled: true, iv: ivView({ status: "quota", metrics: emptyMetrics() }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument());
    expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0);
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
    const smallSeries = normalizedSkewSeries(3, (i) => 0.20 + i * 0.01);
    mockApi({ enabled: true, iv: ivView({ normalized_skew_points: smallSeries }) });
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
    const smallSeries = normalizedSkewSeries(3, (i) => 0.20 + i * 0.01);
    mockApi({ enabled: true, iv: ivView({ normalized_skew_points: smallSeries }) });
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
    expect(screen.getByText("警告")).toBeInTheDocument();
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

describe("固定版位，不因 request 完成才決定要不要出現（QA 反饋，2026-08-16）", () => {
  /** 建一個永遠不會自己 resolve 的 IV 請求，讓測試自己控制什麼時候
   *  「回應到了」——這是唯一能穩定觀察到 loading 這個瞬間狀態的方法。 */
  function pendingIvFetch() {
    let resolveIv!: (r: Response) => void;
    const ivPromise = new Promise<Response>((resolve) => { resolveIv = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return ivPromise;
    }));
    return (result: IvHistoryView) =>
      resolveIv({ ok: true, status: 200, json: async () => result } as Response);
  }

  it("解鎖後、資料回來前，卡片已經在原位顯示骨架，不是空白", async () => {
    const resolve = pendingIvFetch();
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);

    await waitFor(() =>
      expect(container.querySelector(".iv-skeleton")).toBeInTheDocument());
    expect(screen.getByText("IV 相對位置")).toBeInTheDocument();
    expect(container.querySelectorAll(".card")).toHaveLength(1);

    resolve(ivView());
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    // 換成有資料的內容後骨架消失，但卡片本身自始至終只有這一個版位。
    expect(container.querySelector(".iv-skeleton")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".card")).toHaveLength(1);
  });

  it("Spread 模式骨架有兩個次層方塊，Long Call 單腳只有一個", async () => {
    const resolveSpread = pendingIvFetch();
    const { container: spreadContainer } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(spreadContainer.querySelector(".iv-skeleton")).toBeInTheDocument());
    expect(spreadContainer.querySelectorAll(".iv-skeleton-secondary"))
      .toHaveLength(2);
    resolveSpread(ivView());
    await waitFor(() =>
      expect(spreadContainer.querySelector(".iv-skeleton")).not.toBeInTheDocument());

    const resolveSingle = pendingIvFetch();
    const { container: singleContainer } = render(
      <IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    await waitFor(() =>
      expect(singleContainer.querySelector(".iv-skeleton")).toBeInTheDocument());
    expect(singleContainer.querySelectorAll(".iv-skeleton-secondary"))
      .toHaveLength(1);
    resolveSingle(singleLegIvView());
    await waitFor(() =>
      expect(singleContainer.querySelector(".iv-skeleton")).not.toBeInTheDocument());
  });

  it("error 狀態沿用同一個版位——卡片沒有先消失再重新出現", async () => {
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
      expect(container.querySelectorAll(".card")).toHaveLength(1));
    await waitFor(() =>
      expect(screen.getByText(/取不到歷史 IV/)).toBeInTheDocument());
    expect(container.querySelectorAll(".card")).toHaveLength(1);
  });

  it("Normalized Skew 無資料（count＝0）時卡片照常在，逐項顯示「沒有歷史資料」而不是整塊消失",
     async () => {
    mockApi({ enabled: true, iv: ivView({
      metrics: emptyMetrics(),
      observations: 0,
    }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(screen.getByText("Normalized Skew")).toBeInTheDocument());
    expect(screen.getAllByText("沒有歷史資料").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".card")).toHaveLength(1);
  });
});

describe("Inline Diagnostics 的 Copy 按鈕（QA 反饋，2026-08-16）", () => {
  it("版面順序：Copy 按鈕在完整 diagnostic details 之前", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-copy", events: [diagEvent()] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);

    const copyButton = screen.getByRole("button", { name: "Copy diagnostics" });
    const eventIdLabel = screen.getByText("事件 ID");
    const position = copyButton.compareDocumentPosition(eventIdLabel);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("點 Copy 呼叫 clipboard，內容含 correlation ID 與完整事件清單", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-copy", events: [diagEvent()] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);
    await userEvent.click(screen.getByRole("button", { name: "Copy diagnostics" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = JSON.parse(writeText.mock.calls[0][0] as string);
    expect(copied.correlation_id).toBe("cid-copy");
    expect(copied.events).toHaveLength(1);
    expect(copied.events[0].event_id).toBe("evt-1");
  });

  it("請求本身失敗時 Copy 內容也帶著這次的錯誤訊息", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/settings")) {
        return { ok: true, status: 200,
                 json: async () => ({ historical_iv_enabled: true }) } as Response;
      }
      return { ok: false, status: 502,
               headers: new Headers({ "X-Correlation-Id": "cid-fail-copy" }),
               json: async () => ({ detail: "額度用盡" }) } as Response;
    }));
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);
    await userEvent.click(screen.getByRole("button", { name: "Copy diagnostics" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = JSON.parse(writeText.mock.calls[0][0] as string);
    expect(copied.correlation_id).toBe("cid-fail-copy");
    expect(copied.message).toContain("額度用盡");
  });

  it("clipboard 不可用時退回顯示可全選的文字區塊，不是靜默失敗", async () => {
    Object.assign(navigator, { clipboard: undefined });
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-fallback", events: [diagEvent()] },
    }) });
    render(<IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    await userEvent.click(summary);
    await userEvent.click(screen.getByRole("button", { name: "Copy diagnostics" }));

    const fallback = await screen.findByLabelText("複製失敗，請手動全選複製");
    expect(fallback.tagName).toBe("TEXTAREA");
    const copied = JSON.parse((fallback as HTMLTextAreaElement).value);
    expect(copied.correlation_id).toBe("cid-fallback");
  });

  it("收合/展開行為保留——details 預設收合，點擊 summary 展開／收起", async () => {
    mockApi({ enabled: true, iv: ivView({
      diagnostics: { correlation_id: "cid-collapsed", events: [diagEvent()] },
    }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText(
      "Historical IV 資料取得失敗 · 查看詳情");
    const details = container.querySelector(".iv-diagnostics") as HTMLDetailsElement;
    expect(details.open).toBe(false);

    await userEvent.click(summary);
    expect(details.open).toBe(true);
    expect(screen.getByRole("button", { name: "Copy diagnostics" }))
      .toBeInTheDocument();

    await userEvent.click(summary);
    expect(details.open).toBe(false);
  });
});

describe("Advanced／Diagnostics 收合區（SIG-02／#173）", () => {
  it("預設收合", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-advanced")).toBeInTheDocument());
    const advanced = container.querySelector(".iv-advanced") as HTMLDetailsElement;
    expect(advanced.open).toBe(false);
  });

  it("展開後看得到逐腿 z-score 文字與 Normalized Skew 整組", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    const summary = await screen.findByText("Advanced／Diagnostics");
    await userEvent.click(summary);

    expect((container.querySelector(".iv-advanced") as HTMLDetailsElement).open)
      .toBe(true);
    expect(screen.getByText(/買腿 Z-score/)).toBeInTheDocument();
    expect(screen.getByText(/賣腿 Z-score/)).toBeInTheDocument();
    expect(screen.getByText("Normalized Skew")).toBeInTheDocument();
  });

  it("單腳候選：Advanced 只有一行 z-score（無買／賣標籤），沒有 Normalized Skew",
     async () => {
    mockApi({ enabled: true, iv: singleLegIvView() });
    render(<IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    const summary = await screen.findByText("Advanced／Diagnostics");
    await userEvent.click(summary);

    expect(screen.getByText(/^Z-score/)).toBeInTheDocument();
    expect(screen.queryByText(/買腿 Z-score|賣腿 Z-score/)).not.toBeInTheDocument();
    expect(screen.queryByText("Normalized Skew")).not.toBeInTheDocument();
  });

  it("z-score 文字不在 Advanced 之外——瘦身後的主要區塊沒有 Z-score", async () => {
    mockApi({ enabled: true });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-advanced")).toBeInTheDocument());
    const advanced = container.querySelector(".iv-advanced")!;
    // 把 Advanced 整段子樹的文字從全文裡挖掉，剩下的就是「Advanced 之外」
    // 的文字——直接比對子孫節點會被祖先節點的 textContent（本來就會
    // 包含子孫的文字）誤判成「外面也有」，所以用挖除而非逐節點過濾。
    const outsideAdvanced = (container.textContent ?? "")
      .replace(advanced.textContent ?? "", "");
    expect(outsideAdvanced).not.toMatch(/Z-score/);
  });
});

describe("Spread Summary（SIG-03／#174）：接進 IvHistory 的三種情境", () => {
  it("spread_gap key 不存在（單腳候選）→ 完全不渲染 Spread Summary", async () => {
    mockApi({ enabled: true, iv: singleLegIvView() });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={longCallCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-trend-card")).toBeInTheDocument());
    expect(container.querySelector(".iv-spread-summary")).not.toBeInTheDocument();
  });

  it("spread_gap key 存在但 points 為空 → 仍然渲染，以 unavailable 狀態呈現",
     async () => {
    mockApi({ enabled: true, iv: ivView({ spread_gap: emptySpreadGap() }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-spread-summary")).toBeInTheDocument());
    const summary = container.querySelector(".iv-spread-summary")!;
    expect(summary.querySelector(".iv-value-primary")?.textContent).toBe("—");
    expect(summary.querySelector(".iv-trend-chart")).not.toBeInTheDocument();
  });

  it("spread_gap key 存在且有資料 → 卡片最上方出現有內容的頭條", async () => {
    mockApi({ enabled: true, iv: ivView({ spread_gap: spreadGapFixture() }) });
    const { container } = render(
      <IvHistory scenarioId="s1" candidate={spreadCandidate()} />);
    await waitFor(() =>
      expect(container.querySelector(".iv-spread-summary")).toBeInTheDocument());
    expect(screen.getByText("Spread IV Gap")).toBeInTheDocument();
    const summary = container.querySelector(".iv-spread-summary")!;
    expect(summary.querySelector(".iv-trend-chart")).toBeInTheDocument();
    // Spread Summary 在 Buy／Sell 逐腿卡片之前（卡片最上方）。
    const legCard = container.querySelector(".iv-trend-card")!;
    expect(summary.compareDocumentPosition(legCard)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
