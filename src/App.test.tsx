/**
 * V1（#48）前端元件測試。
 *
 * mock 回應直接載入 `contracts/analysis_sample.json`——與後端 fixture
 * **同一份**契約樣本（spec #47 裁示），任一邊改動契約而沒同步，
 * 後端的 `test_contract_sample_matches_the_live_api_response` 會先爆。
 *
 * 只測外部行為（畫面呈現什麼、失敗時說什麼），不測實作細節。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import sample from "../contracts/analysis_sample.json";
import sampleRow from "../contracts/scenario_row_sample.json";
import { baselineTopCandidate, type AnalysisView } from "./api";

const view = sample as unknown as AnalysisView;

/**
 * V3 起 App 開站就會打 `/api/scenarios`，所以 mock 必須依 URL 分流——
 * 一個「不管問什麼都回同一份分析結果」的 stub 會讓劇本清單收到一份
 * 不是陣列的東西，測出來的東西也就不代表真實行為。
 */
function mockRoutes(
  routes: Record<string, Partial<Response> & { json: () => Promise<unknown> }>,
) {
  const spy = vi.fn(async (url: string, _init?: RequestInit) => {
    // 最長前綴優先：`/api/scenarios/s1/refresh` 也以 `/api/scenarios`
    // 開頭，先比對長的才不會被清單那條路由吃掉（V4／#52 起有子路徑）。
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.startsWith(k));
    if (key === undefined) throw new Error(`測試沒有為 ${url} 準備回應`);
    return { ok: true, status: 200, ...routes[key] };
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** 分析端點以外一律回空劇本清單——V1 遺留畫面的測試只關心分析。 */
function mockFetch(resp: Partial<Response> & { json: () => Promise<unknown> }) {
  return mockRoutes({
    "/api/scenarios": { json: async () => [] },
    "/api/analyze": resp,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("走通骨架畫面", () => {
  it("分析前不顯示任何結果數字", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    // 等開站的劇本清單載完，否則斷言會落在畫面還沒定下來的一瞬間
    await screen.findByText(/還沒有劇本/);

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

    // 開站的劇本清單請求也在裡面，挑出分析那一筆。
    const call = spy.mock.calls.find(([url]) => url === "/api/analyze")!;
    const body = JSON.parse(String(call[1]!.body));
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

  it("分析前不顯示候選池", async () => {
    mockFetch({ json: async () => view });
    render(<App />);
    await screen.findByText(/還沒有劇本/);

    expect(screen.queryByText("候選池")).not.toBeInTheDocument();
  });
});

describe("劇本庫（V3／#51）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.5,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };

  it("開站就載入劇本清單並畫成卡片", async () => {
    mockRoutes({
      "/api/scenarios": { json: async () => [row] },
      "/api/scenarios/": { json: async () => row },   // 開站的刷新（V4）
    });
    render(<App />);

    expect(await screen.findByText("TLT")).toBeInTheDocument();
    expect(screen.getByText("150.0%")).toBeInTheDocument();
    expect(screen.getByText("劇本庫")).toBeInTheDocument();
  });

  it("清單載不動時說明原因，不是空白的「還沒有劇本」", async () => {
    mockRoutes({
      "/api/scenarios": {
        ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
      },
    });
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("資料庫連不上");
  });

  it("建立後新劇本立刻出現在清單上", async () => {
    const created = { ...row, id: "s2", symbol: "SPY",
                      latest_analyzed_at: null, best_return: null };
    const spy = mockRoutes({
      "/api/scenarios": { json: async () => [] },
    });
    spy.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/scenarios" && init?.method === "POST") {
        return { ok: true, status: 201, json: async () => created };
      }
      if (url.endsWith("/refresh")) {
        // 建立後的刷新（V4／#52）：這個標的目前抓不到報價，因此卡片
        // 上的收益率仍是「—」——本測試要驗的正是那個。
        return { ok: false, status: 502,
                 json: async () => ({ detail: { stage: "fetch",
                                                message: "抓不到報價" } }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    render(<App />);

    await userEvent.type(await screen.findByLabelText("標的代號"), "spy");
    await userEvent.type(screen.getByLabelText("目標價位"), "700");
    await userEvent.type(screen.getByLabelText("目標年月"), "2028-05");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(await screen.findByText("SPY")).toBeInTheDocument();
    // 還沒分析過 → 收益率欄位是「—」，不是 0%
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("封存後卡片從清單消失", async () => {
    const spy = mockRoutes({ "/api/scenarios": { json: async () => [row] } });
    spy.mockImplementation(async (url: string) => {
      if (url.endsWith("/archive")) {
        return { ok: true, status: 200, json: async () => ({ archived: true }) };
      }
      if (url.endsWith("/refresh")) {
        return { ok: true, status: 200, json: async () => row };
      }
      return { ok: true, status: 200, json: async () => [row] };
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));

    expect(screen.queryByText("TLT")).not.toBeInTheDocument();
  });

  it("封存失敗時卡片回到清單上，並說明原因", async () => {
    const spy = mockRoutes({ "/api/scenarios": { json: async () => [row] } });
    spy.mockImplementation(async (url: string) => {
      if (url.endsWith("/archive")) {
        return { ok: false, status: 404,
                 json: async () => ({ detail: "劇本不存在" }) };
      }
      if (url.endsWith("/refresh")) {
        return { ok: true, status: 200, json: async () => row };
      }
      return { ok: true, status: 200, json: async () => [row] };
    });
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));

    // 樂觀移除必須可回復——否則畫面會宣稱一件沒發生的事
    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();
  });
});

describe("樂觀封存的併發（V3／#51 檢視回饋）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: null, best_return: null,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };

  it("A 封存失敗回滾時，不會讓已成功封存的 B 復活", async () => {
    const rowB = { ...row, id: "s2", symbol: "SPY" };
    let failA: (() => void) | null = null;
    const spy = vi.fn(async (url: string) => {
      if (url.includes("/s1/archive")) {
        // A 停在半空中，讓 B 先完成——回滾若存整份陣列就會蓋回 B
        await new Promise<void>((resolve) => { failA = resolve; });
        return { ok: false, status: 404, json: async () => ({ detail: "劇本不存在" }) };
      }
      if (url.includes("/s2/archive")) {
        return { ok: true, status: 200, json: async () => ({ archived: true }) };
      }
      if (url.endsWith("/refresh")) {
        const id = url.split("/").at(-2);
        return { ok: true, status: 200,
                 json: async () => (id === "s1" ? row : rowB) };
      }
      return { ok: true, status: 200, json: async () => [row, rowB] };
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "封存 TLT 2028-05" }));
    await userEvent.click(
      screen.getByRole("button", { name: "封存 SPY 2028-05" }));
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();

    failA!();

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();   // A 回來了
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();  // B 沒被復活
  });
});

describe("刷新與進度（V4／#52）", () => {
  const base = sampleRow as unknown as Record<string, unknown>;
  const card = (id: string, symbol: string, extra: Record<string, unknown> = {}) => ({
    ...base, id, symbol, target_price: 120, target_month: "2028-05",
    target_anchor: "2028-05-19", days_to_anchor: 653,
    latest_analyzed_at: null, best_return: null, ...extra,
  });

  /**
   * 劇本庫的路由：GET 清單、POST 單劇本刷新。`refresh` 由各測試決定
   * 每個 id 得到什麼回應（成功／失敗／停在半空中）。
   */
  function mockLibrary(
    rows: Record<string, unknown>[],
    refresh: (id: string) => Promise<Partial<Response> & { json: () => Promise<unknown> }>,
  ) {
    const spy = vi.fn(async (url: string, _init?: RequestInit) => {
      const hit = /\/api\/scenarios\/([^/]+)\/refresh$/.exec(url);
      if (hit) return refresh(hit[1]);
      if (url === "/api/scenarios") {
        return { ok: true, status: 200, json: async () => rows };
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    return spy;
  }

  const ok = (row: Record<string, unknown>) =>
    ({ ok: true, status: 200, json: async () => row });
  const fail = (status: number, stage: string, message: string) =>
    ({ ok: false, status, json: async () => ({ detail: { stage, message } }) });

  function refreshCalls(spy: ReturnType<typeof vi.fn>) {
    return spy.mock.calls
      .map(([url]) => /\/api\/scenarios\/([^/]+)\/refresh$/.exec(String(url))?.[1])
      .filter((id): id is string => id !== undefined);
  }

  it("開站後逐一刷新每個劇本，卡片換成刷新後的數字", async () => {
    const spy = mockLibrary(
      [card("s1", "TLT"), card("s2", "SPY")],
      async (id) => ok(card(id, id === "s1" ? "TLT" : "SPY", {
        latest_analyzed_at: new Date().toISOString(),
        best_return: id === "s1" ? 2.5 : 0.5,
      })),
    );
    render(<App />);

    expect(await screen.findByText("250.0%")).toBeInTheDocument();
    expect(await screen.findByText("50.0%")).toBeInTheDocument();
    expect(refreshCalls(spy).sort()).toEqual(["s1", "s2"]);
  });

  it("刷新中顯示第幾個／共幾個，完成後收起", async () => {
    let releaseFirst: (() => void) | null = null;
    const spy = mockLibrary(
      [card("s1", "TLT"), card("s2", "SPY")],
      async (id) => {
        if (id === "s1") {
          await new Promise<void>((resolve) => { releaseFirst = resolve; });
        }
        return ok(card(id, "X", { best_return: 1, latest_analyzed_at: "2026-08-04T09:30:00+00:00" }));
      },
    );
    render(<App />);

    // 第一個還在跑：0 個做完、總共 2 個
    expect(await screen.findByRole("status")).toHaveTextContent("0/2");
    // 逐一刷新，不是同時打兩個請求——第一個沒回來前不該有第二個
    expect(refreshCalls(spy)).toEqual(["s1"]);

    releaseFirst!();

    expect(await screen.findByText("重新整理")).toBeEnabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(refreshCalls(spy)).toEqual(["s1", "s2"]);
  });

  it("刷新進行中不能再按一次刷新", async () => {
    let release: (() => void) | null = null;
    mockLibrary([card("s1", "TLT")], async (id) => {
      await new Promise<void>((resolve) => { release = resolve; });
      return ok(card(id, "TLT", { best_return: 1 }));
    });
    render(<App />);

    expect(await screen.findByText("刷新中……")).toBeDisabled();
    release!();
    expect(await screen.findByText("重新整理")).toBeEnabled();
  });

  it("按功能列刷新鈕會重跑一輪", async () => {
    const spy = mockLibrary([card("s1", "TLT")], async (id) =>
      ok(card(id, "TLT", { best_return: 1 })));
    render(<App />);
    await screen.findByText("100.0%");
    expect(refreshCalls(spy)).toEqual(["s1"]);

    await userEvent.click(screen.getByRole("button", { name: "重新整理" }));

    expect(refreshCalls(spy)).toEqual(["s1", "s1"]);
  });

  it("一個劇本失敗不會中斷其他劇本的刷新", async () => {
    const spy = mockLibrary(
      [card("s1", "TLT"), card("s2", "SPY")],
      async (id) => id === "s1"
        ? fail(502, "fetch", "抓不到 TLT 的報價：來源無回應")
        : ok(card(id, "SPY", { best_return: 0.8,
                               latest_analyzed_at: "2026-08-04T09:30:00+00:00" })),
    );
    render(<App />);

    expect(await screen.findByText("80.0%")).toBeInTheDocument();
    expect(refreshCalls(spy)).toEqual(["s1", "s2"]);
    expect(screen.getByText(/抓不到報價/)).toBeInTheDocument();
    expect(screen.getByText(/來源無回應/)).toBeInTheDocument();
  });

  it("分析失敗與抓不到報價分屬不同訊息", async () => {
    mockLibrary([card("s1", "TLT")], async () =>
      fail(500, "analyze", "分析失敗：boom"));
    render(<App />);

    expect(await screen.findByText(/分析沒跑完/)).toBeInTheDocument();
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
  });

  it("重試只重打那一個劇本，成功後失敗訊息消失", async () => {
    let firstTry = true;
    const spy = mockLibrary(
      [card("s1", "TLT"), card("s2", "SPY")],
      async (id) => {
        if (id === "s1" && firstTry) {
          firstTry = false;
          return fail(502, "fetch", "抓不到 TLT 的報價：來源無回應");
        }
        return ok(card(id, id === "s1" ? "TLT" : "SPY", {
          best_return: id === "s1" ? 1.1 : 0.8,
          latest_analyzed_at: "2026-08-04T09:30:00+00:00" }));
      },
    );
    render(<App />);
    await screen.findByText(/抓不到報價/);

    await userEvent.click(
      screen.getByRole("button", { name: "重試 TLT 2028-05" }));

    expect(await screen.findByText("110.0%")).toBeInTheDocument();
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
    // 重試就是重試那一個，不是又刷一輪全部
    expect(refreshCalls(spy)).toEqual(["s1", "s2", "s1"]);
  });

  it("卡片上沒有第四種刷新管道——只有失敗時的重試", async () => {
    mockLibrary([card("s1", "TLT")], async (id) =>
      ok(card(id, "TLT", { best_return: 1,
                           latest_analyzed_at: "2026-08-04T09:30:00+00:00" })));
    render(<App />);
    await screen.findByText("100.0%");

    const buttons = within(screen.getByRole("listitem"))
      .getAllByRole("button").map((b) => b.textContent);
    expect(buttons).toEqual(["封存"]);
  });

  it("沒有任何劇本時不跑刷新，也不顯示進度", async () => {
    const spy = mockLibrary([], async () => ok({}));
    render(<App />);
    await screen.findByText(/還沒有劇本/);

    expect(refreshCalls(spy)).toEqual([]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
