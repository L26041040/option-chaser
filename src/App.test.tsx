/**
 * 劇本庫畫面的元件測試。
 *
 * mock 用的劇本列直接載入 `contracts/scenario_row_sample.json`——與後端
 * fixture **同一份**契約樣本（spec #47 裁示），任一邊改動契約而沒同步，
 * 後端的 `test_scenario_row_sample_matches_the_live_list_response` 會先爆。
 *
 * 只測外部行為（畫面呈現什麼、失敗時說什麼），不測實作細節。
 * 詳細頁本身的測試在 `ScenarioDetail.test.tsx`。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import sampleRow from "../contracts/scenario_row_sample.json";

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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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

    // 正在跑第一個、總共 2 個
    expect(await screen.findByRole("status")).toHaveTextContent("1/2");
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

describe("過期劇本不再進入批次刷新（#68）", () => {
  const base = sampleRow as unknown as Record<string, unknown>;
  const card = (id: string, symbol: string, extra: Record<string, unknown> = {}) => ({
    ...base, id, symbol, target_price: 120, target_month: "2020-01",
    target_anchor: "2020-01-17", days_to_anchor: -2000,
    latest_analyzed_at: null, best_return: null, ...extra,
  });

  it("開站批次刷新跳過已過期的劇本，分母也不算它", async () => {
    const spy = mockLibrary(
      [card("s1", "OLD", { expired: true }), card("s2", "SPY", {
        target_month: "2028-05", expired: false })],
      async (id) => ok(card(id, "SPY", {
        target_month: "2028-05", expired: false,
        best_return: 0.5, latest_analyzed_at: new Date().toISOString() })),
    );
    render(<App />);

    expect(await screen.findByText("50.0%")).toBeInTheDocument();
    // 過期的那個從沒被排進去——佇列只跑了 s2
    expect(refreshCalls(spy)).toEqual(["s2"]);
  });

  it("已過期的劇本顯示標記，且不落在「尚未分析」的樣子上", async () => {
    mockLibrary([card("s1", "OLD", { expired: true })], async () => ok({}));
    render(<App />);

    expect(await screen.findByText("已過期，不再刷新")).toBeInTheDocument();
    expect(screen.queryByText("尚未分析")).toBeInTheDocument();  // 沒分析過，兩件事並存
  });

  it("建立劇本後刷新，清單裡既有的過期劇本不會被排進那一輪", async () => {
    const created = card("s2", "SPY", { target_month: "2028-05", expired: false,
                                        latest_analyzed_at: null, best_return: null });
    const spy = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/scenarios" && init?.method === "POST") {
        return { ok: true, status: 201, json: async () => created };
      }
      if (url === "/api/scenarios") {
        return { ok: true, status: 200, json: async () => [card("s1", "OLD", { expired: true })] };
      }
      if (url.endsWith("/refresh")) {
        const id = url.split("/").at(-2);
        if (id === "s1") throw new Error("過期劇本不該被刷新");
        return { ok: true, status: 200, json: async () => created };
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    await userEvent.type(await screen.findByLabelText("標的代號"), "spy");
    await userEvent.type(screen.getByLabelText("目標價位"), "700");
    await userEvent.type(screen.getByLabelText("目標年月"), "2028-05");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(await screen.findByText("SPY")).toBeInTheDocument();
    expect(refreshCalls(spy)).toEqual(["s2"]);
  });

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

  function refreshCalls(spy: ReturnType<typeof vi.fn>) {
    return spy.mock.calls
      .map(([url]) => /\/api\/scenarios\/([^/]+)\/refresh$/.exec(String(url))?.[1])
      .filter((id): id is string => id !== undefined);
  }
});

describe("建立與刷新同時發生（V4／#52 檢視回饋）", () => {
  const base = sampleRow as unknown as Record<string, unknown>;
  const card = (id: string, symbol: string, extra: Record<string, unknown> = {}) => ({
    ...base, id, symbol, target_price: 120, target_month: "2028-05",
    target_anchor: "2028-05-19", days_to_anchor: 653,
    latest_analyzed_at: null, best_return: null, ...extra,
  });

  it("建立劇本不會把建立期間刷新好的卡片打回未分析", async () => {
    // 建立的請求飛在半空中時，開站那一輪剛好把 s1 刷新完。若建立完成後
    // 用「送出前那份 rows」蓋回去，s1 就會退回未分析的樣子——使用者看到
    // 的是一個剛剛才有過的數字憑空消失。
    let releaseRefresh: (() => void) | null = null;
    let releaseCreate: (() => void) | null = null;
    let s1Calls = 0;

    const spy = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/scenarios" && init?.method === "POST") {
        await new Promise<void>((resolve) => { releaseCreate = resolve; });
        return { ok: true, status: 201, json: async () => card("s2", "SPY") };
      }
      if (url === "/api/scenarios") {
        return { ok: true, status: 200, json: async () => [card("s1", "TLT")] };
      }
      if (url.endsWith("/s1/refresh")) {
        s1Calls += 1;
        if (s1Calls === 1) {
          await new Promise<void>((resolve) => { releaseRefresh = resolve; });
          return { ok: true, status: 200, json: async () => card("s1", "TLT", {
            best_return: 2.0, latest_analyzed_at: "2026-08-04T09:30:00+00:00" }) };
        }
        // 第二趟失敗：否則「重刷一次就恢復」會把回歸蓋掉，測不出東西
        return { ok: false, status: 502, json: async () => ({
          detail: { stage: "fetch", message: "抓不到報價" } }) };
      }
      if (url.endsWith("/s2/refresh")) {
        return { ok: true, status: 200, json: async () => card("s2", "SPY", {
          best_return: 0.3, latest_analyzed_at: "2026-08-04T09:30:00+00:00" }) };
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    await userEvent.type(await screen.findByLabelText("標的代號"), "spy");
    await userEvent.type(screen.getByLabelText("目標價位"), "700");
    await userEvent.type(screen.getByLabelText("目標年月"), "2028-05");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    releaseRefresh!();                       // 建立還沒回來，s1 先刷新完
    expect(await screen.findByText("200.0%")).toBeInTheDocument();

    releaseCreate!();

    expect(await screen.findByText("30.0%")).toBeInTheDocument();
    expect(screen.getByText("200.0%")).toBeInTheDocument();
  });
});

describe("詳細頁刷新入口與劇本庫共用同一條佇列（#70）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.5,
    target_anchor: "2028-05-19", days_to_anchor: 653, expired: false,
  };

  afterEach(() => { window.location.hash = ""; });

  it("在詳細頁按刷新，打的是同一個劇本的 refresh 端點", async () => {
    // 開站本身也會自動刷新這唯一的劇本一次——這條測試要驗的是「按鈕
    // 點擊本身」有沒有另外觸發一次，所以要先等開站那輪跑完，再比對
    // 點擊前後的呼叫次數，不能只看「有沒有打過 /refresh」（那樣點不
    // 點都會通過）。
    window.location.hash = "#/s/s1";
    const refreshCalls: string[] = [];
    const spy = vi.fn(async (url: string) => {
      if (url === "/api/scenarios") {
        return { ok: true, status: 200, json: async () => [row] };
      }
      if (url === "/api/scenarios/s1") {
        return { ok: true, status: 200, json: async () => ({ ...row, latest_result: null }) };
      }
      if (url.endsWith("/s1/refresh")) {
        refreshCalls.push(url);
        return { ok: true, status: 200, json: async () => ({
          ...row, best_return: 9.9, latest_analyzed_at: "2026-08-04T10:00:00+00:00" }) };
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    // 開站那輪跑完＝按鈕從「刷新中……」變回可按
    await screen.findByRole("button", { name: "重新整理" });
    const before = refreshCalls.length;

    await userEvent.click(screen.getByRole("button", { name: "重新整理" }));

    await waitFor(() => expect(refreshCalls.length).toBe(before + 1));
  });

  it("批次刷新進行中，詳細頁的刷新按鈕也停用——同一條忙碌狀態", async () => {
    window.location.hash = "#/s/s1";
    let releaseRefresh: (() => void) | null = null;
    const spy = vi.fn(async (url: string) => {
      if (url === "/api/scenarios") {
        return { ok: true, status: 200, json: async () => [row] };
      }
      if (url === "/api/scenarios/s1") {
        return { ok: true, status: 200, json: async () => ({ ...row, latest_result: null }) };
      }
      if (url.endsWith("/s1/refresh")) {
        await new Promise<void>((resolve) => { releaseRefresh = resolve; });
        return { ok: true, status: 200, json: async () => row };
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    render(<App />);

    // 開站那輪刷新正在跑（s1 是清單裡唯一的劇本，卡在 refresh 半路）
    expect(await screen.findByRole("button", { name: "刷新中……" })).toBeDisabled();

    releaseRefresh!();
    // 讓那一趟真的跑完再結束測試，不留一個未 act 包裹的狀態更新在後頭
    expect(await screen.findByRole("button", { name: "重新整理" })).toBeEnabled();
  });
});

describe("清單 → 詳細頁（V5／#53）", () => {
  const row = {
    ...(sampleRow as unknown as Record<string, unknown>),
    id: "s1", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.5,
    target_anchor: "2028-05-19", days_to_anchor: 653,
  };

  afterEach(() => {
    window.location.hash = "";
  });

  it("卡片本身就是進詳細頁的連結，帶著那個劇本的身分", async () => {
    mockRoutes({
      "/api/scenarios": { json: async () => [row] },
      "/api/scenarios/": { json: async () => row },
    });
    render(<App />);

    const link = await screen.findByRole("link", { name: /TLT 2028-05/ });
    expect(link).toHaveAttribute("href", "#/s/s1");
  });

  it("網址指向某個劇本時直接顯示詳細頁，不是劇本庫", async () => {
    window.location.hash = "#/s/s1";
    mockRoutes({
      "/api/scenarios": { json: async () => [row] },
      "/api/scenarios/s1": { json: async () => ({ ...row, latest_result: null }) },
    });
    render(<App />);

    // 詳細頁在畫面上（返回入口＋該劇本的標的），建立表單不在
    expect(await screen.findByRole("link", { name: /劇本庫/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("標的代號")).not.toBeInTheDocument();
  });

  it("hash 變回劇本庫就回到清單——返回鍵要能用", async () => {
    window.location.hash = "#/s/s1";
    mockRoutes({
      "/api/scenarios": { json: async () => [row] },
      "/api/scenarios/s1": { json: async () => ({ ...row, latest_result: null }) },
    });
    render(<App />);
    await screen.findByRole("link", { name: /劇本庫/ });

    window.location.hash = "#/";
    // jsdom 的 hashchange 是非同步派送的，等畫面自己跟上
    expect(await screen.findByRole("heading", { name: "劇本庫" }))
      .toBeInTheDocument();
  });
});
