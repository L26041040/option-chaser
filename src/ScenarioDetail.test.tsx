import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ScenarioDetail from "./ScenarioDetail";
import sample from "../contracts/analysis_sample.json";
import sampleRow from "../contracts/scenario_row_sample.json";
import { baselineTopCandidate, type AnalysisView } from "./api";

const view = sample as unknown as AnalysisView;
const row = sampleRow as unknown as Record<string, unknown>;

/** 契約樣本本身：目標價 130、baseline 候選買 118／賣 122。 */
function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...row, id: "s1", symbol: "XYZ", target_price: view.params.target_price,
    target_month: view.params.target_month,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 5.67,
    latest_result: view, ...overrides,
  };
}

/** 改寫 baseline 期第 1 名候選的某些欄位，其餘契約原樣。
 *
 * T09（#191）：完整內容集中在 `candidate_pool`，容器只留 key 引用——
 * 這裡只需要 patch 池子裡那一筆，`expiry_top10[].candidate_keys` 完全不用
 * 動（就算 patch 改了候選自己的 `candidate_key` 欄位值，容器裡引用它
 * 的那個 dict key 字串本身仍是原來的，`resolveCandidate()` 靠 dict key
 * 找到它、回傳的物件內容才是 patch 過的那份，跟 `baselineTopCandidate()`
 * 的既有讀取路徑一致）。 */
function withTopCandidate(patch: Record<string, unknown>): AnalysisView {
  const result = view.results[0];
  const group = result.expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!;
  const key = group.candidate_keys[0];
  return {
    ...view,
    candidate_pool: {
      ...view.candidate_pool,
      [key]: { ...view.candidate_pool![key], ...patch },
    },
  };
}

/**
 * 主圖那一張表。V6（#54）之後頁面上有很多張 Heatmap（到期日結構裡每個
 * 候選收合著一張），所以這裡的斷言一律鎖定主圖那一區，不用全頁查找。
 *
 * MVP V3（#103）起，主圖只剩 Heatmap 本身——候選身分／名次／目標報酬
 * 在頂部摘要卡，見 `summarySection()`。
 */
function mainChart() {
  return within(screen.getByRole("heading", { name: "劇本主圖" })
    .closest("section")!);
}

/**
 * 頂部摘要卡（QA 修正後三卡合一）：劇本設定（現價／目標／年月／策略／
 * 資料時間／來源）、基準候選身分（履約、到期日、名次、劇本報酬）與
 * 進場成本（買腿 Ask／賣腿 Bid／淨成本）全部在這一張，外加候選池
 * 過少的警語。
 */
function summarySection() {
  return within(screen.getByRole("region", { name: "劇本摘要" }));
}

function mockDetail(body: unknown, ok = true, status = 200) {
  const spy = vi.fn(async () => ({ ok, status, json: async () => body }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("詳細頁摘要（QA 修正：劇本摘要／基準候選／進場成本三卡合一）", () => {
  it("顯示現價、目標價與所需漲幅、目標年月、策略", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(`$${view.meta.spot.toFixed(2)}`)).toBeInTheDocument();
    const summary = summarySection();
    expect(summary.getByText(`$${view.params.target_price.toFixed(2)}`)).toBeInTheDocument();
    // 所需漲幅寫在目標價旁的括號裡，所以用子字串比對
    expect(summary.getByText(`+${(view.meta.target_move * 100).toFixed(1)}%`,
                            { exact: false })).toBeInTheDocument();
    expect(summary.getByText(view.params.target_month)).toBeInTheDocument();
    expect(summary.getByText("Bull Call Spread")).toBeInTheDocument();
  });

  it("資料時間與資料來源沒有在合併過程中被弄丟", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const summary = summarySection();
    expect(summary.getByText("資料時間")).toBeInTheDocument();
    expect(summary.getByText("資料來源")).toBeInTheDocument();
    expect(summary.getByText(view.meta.source)).toBeInTheDocument();
  });

  it("基準候選身分同卡呈現：B/S 履約、名次、到期日與目標報酬", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    const top = baselineTopCandidate(view)!;
    const buy = top.legs.find((leg) => leg.side === "buy")!;
    const sell = top.legs.find((leg) => leg.side === "sell")!;
    await screen.findByText(/劇本主圖/);
    const summary = summarySection();
    expect(summary.getByText(`買 ${buy.strike} / 賣 ${sell.strike}`))
      .toBeInTheDocument();
    expect(summary.getByText("第 1 名")).toBeInTheDocument();
    expect(summary.getByText(view.baseline_expiry!)).toBeInTheDocument();
    // 這組候選的劇本報酬——引擎算好的那個數字，口徑與合併前相同
    expect(summary.getByText(`${(top.baseline_return * 100).toFixed(1)}%`))
      .toBeInTheDocument();
  });

  it("進場成本三項同卡呈現：買腿 Ask／賣腿 Bid／淨成本，口徑與到期日結構清單相同",
     async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    const top = baselineTopCandidate(view)!;
    const buy = top.legs.find((leg) => leg.side === "buy")!;
    const sell = top.legs.find((leg) => leg.side === "sell")!;
    await screen.findByText(/劇本主圖/);
    const summary = summarySection();
    expect(summary.getByText("買腿 Ask")).toBeInTheDocument();
    expect(summary.getByText("賣腿 Bid")).toBeInTheDocument();
    expect(summary.getByText("淨成本")).toBeInTheDocument();
    expect(summary.getByText(`$${buy.ask.toFixed(2)}`)).toBeInTheDocument();
    expect(summary.getByText(`$${sell.bid.toFixed(2)}`)).toBeInTheDocument();
    expect(summary.getByText(`$${top.natural_cost.toFixed(2)}`)).toBeInTheDocument();
  });

  it("最高／最低同卡呈現——它們是 Heatmap 價格軸上下限的來源（QA 修正）",
     async () => {
    mockDetail(detail({ latest_result: {
      ...view,
      params: { ...view.params, best_price: 150.0, worst_price: 90.0 },
    } }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const summary = summarySection();
    expect(summary.getByText("最高")).toBeInTheDocument();
    expect(summary.getByText("最低")).toBeInTheDocument();
    expect(summary.getByText("$150.00")).toBeInTheDocument();
    expect(summary.getByText("$90.00")).toBeInTheDocument();
  });

  it("沒填最高／最低時那兩格顯示破折號，不是整格消失", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const summary = summarySection();
    const stat = (label: string) =>
      summary.getByText(label).closest(".stat")!;
    expect(stat("最高").textContent).toContain("—");
    expect(stat("最低").textContent).toContain("—");
  });

  it("原本的三張獨立卡片不再存在——真的合併了，不是把舊卡藏起來", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(screen.queryByRole("heading", { name: "基準候選" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "進場成本" })).not.toBeInTheDocument();
  });

  it("有回劇本庫的入口", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("link", { name: /劇本庫/ }))
      .toHaveAttribute("href", "#/");
  });
});

describe("詳細頁主圖（Payoff Heatmap）", () => {
  it("畫出 baseline 期第 1 名候選的 Heatmap", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(mainChart().getByRole("table")).toBeInTheDocument();
  });
});

describe("追平價格區塊已移除（spec 決策 E／#103）", () => {
  it("不再渲染追平價格卡片，任何相關文案都不出現", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(screen.queryByText(/Long Call 追平價格/)).not.toBeInTheDocument();
    expect(screen.queryByText(/即勝過此 Spread/)).not.toBeInTheDocument();
    expect(screen.queryByText(/超出目標價|低於目標價/)).not.toBeInTheDocument();
    expect(screen.queryByText(/無法計算/)).not.toBeInTheDocument();
  });
});

describe("區塊順序（spec #102 決策 A／#103）", () => {
  it("依決策 A 定義的順序渲染；IV History 插槽尚未上線，不輸出任何內容", async () => {
    const ladder = [
      { label: "worst", price: 110, return: -1 },
      { label: "target", price: 130, return: 5.667 },
    ];
    mockDetail(detail({ latest_result: withTopCandidate({ price_ladder: ladder }) }));
    const { container } = render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    // 每張卡片自己的區塊標題（該卡裡第一個 `.section-title`），依 DOM
    // 順序——用「每張卡取第一個」而不是「全部 .section-title」，這樣
    // 才不會被分析報告內部的子標題（情境分析／風險與代價……）污染，
    // 那些是 #105 的責任範圍，不是這裡要鎖的東西。
    const titles = Array.from(container.querySelectorAll(".card"))
      .map((card) => card.querySelector(".section-title")?.textContent ?? null)
      .filter((t): t is string => t !== null);

    expect(titles).toEqual([
      "劇本主圖", "到期日",
      "候選池", "📄 分析報告", "Spread 淨成本走勢", "原始資料（當次快照）",
    ]);

    // IV History 插槽本身不輸出任何 DOM 節點——不是一張空卡片，直接就
    // 不存在於 DOM 裡。卡片總數固定為上面 6 張加上摘要卡（無 section
    // -title，改用 aria-label），插槽若渲染出任何東西（哪怕只是空卡），
    // 這裡就會多一張。
    expect(container.querySelectorAll(".card")).toHaveLength(7);
    expect(screen.queryByText(/Historical IV|IV Position/)).not.toBeInTheDocument();
  });
});

describe("詳細頁的空狀態", () => {
  it("還沒分析過就說還沒分析，不畫一張空圖", async () => {
    mockDetail(detail({ latest_result: null, latest_analyzed_at: null,
                        best_return: null }));
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(/尚未分析/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();   // 整頁都沒有
  });

  it("baseline 期沒有合格候選時明說，不拿別期的冒充", async () => {
    mockDetail(detail({
      latest_result: { ...view, baseline_expiry: "2099-01-01" },
    }));
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText("無合格候選")).toBeInTheDocument();
    // 主圖那一區沒有表；到期日結構仍照常列出各期候選
    expect(mainChart().queryByRole("table")).not.toBeInTheDocument();
  });

  it("載不動時說明原因，不是白畫面", async () => {
    mockDetail({ detail: "劇本不存在：s1" }, false, 404);
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
  });
});

describe("刷新完成後詳細頁跟著更新（V5／#53 檢視回饋）", () => {
  it("直接開詳細頁網址時，不會永遠停在刷新前的那份快照", async () => {
    // 開站的刷新輪跑在背景，詳細頁沒有功能列也沒有刷新入口——不跟著
    // 重取的話，直接開 `#/s/{id}` 的人看到的永遠是刷新前的數字。
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, status: 200,
      json: async () => (call++ === 0
        ? detail({ latest_result: null, latest_analyzed_at: null })
        : detail()),
    })));

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    expect(await screen.findByText(/尚未分析/)).toBeInTheDocument();

    // 劇本庫那一列的資料時間變了＝這個劇本剛剛被刷新過
    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);

    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();
    expect(mainChart().getByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/尚未分析/)).not.toBeInTheDocument();
  });

  it("T03（#187）：同一輪內反覆進出詳細頁，同一份資料不重新下載", async () => {
    // `mockDetail` 對任何 URL 都回同一份 body（含 IvHistory 自己的
    // settings 請求）——這裡只數打到 scenario detail 端點本身的次數。
    const spy = mockDetail(detail());
    const detailCalls = () =>
      (spy.mock.calls as unknown as [string][])
        .filter(([url]) => url.includes("/api/scenarios/s1")).length;

    const { unmount } = render(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);
    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();
    expect(detailCalls()).toBe(1);

    unmount();
    render(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);
    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();

    // 離開又進來，analyzedAt 沒變——快取命中，底層請求次數不變。
    expect(detailCalls()).toBe(1);
  });
});

describe("詳細頁刷新入口（#70）", () => {
  it("有明確的刷新按鈕，位置與劇本庫一致（標題列右側膠囊鈕）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("button", { name: "重新整理" }))
      .toBeInTheDocument();
  });

  it("點擊呼叫傳入的 onRefresh，且只帶這個劇本的身分（呼叫端決定範圍）", async () => {
    mockDetail(detail());
    const onRefresh = vi.fn();
    render(<ScenarioDetail id="s1" onRefresh={onRefresh} />);

    await userEvent.click(await screen.findByRole("button", { name: "重新整理" }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("刷新進行中按鈕停用並顯示忙碌文字，不能重複觸發", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" busy />);

    expect(await screen.findByRole("button", { name: "刷新中……" }))
      .toBeDisabled();
  });

  it("這個劇本正在被刷新（T08／#196 P1）：明確提示，搶在其他內容之前，" +
     "不能讓桌面右側常駐面板的舊內容看起來像已經更新完成", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" updating />);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(/排隊中或進行中/);
    expect(notice).toHaveTextContent(/上一輪的舊資料/);
  });

  it("沒有更新中時不顯示這個提示", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(screen.queryByText(/排隊中或進行中/)).not.toBeInTheDocument();
  });

  it("更新中又剛好帶著上一次的失敗紀錄時，先顯示更新中提示——這次嘗試還" +
     "沒有結論，失敗提示要等它解決後才有意義", async () => {
    mockDetail(detail());
    render(
      <ScenarioDetail
        id="s1"
        updating
        failure={{ stage: "fetch", message: "抓不到報價" }}
      />,
    );

    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("失敗時顯示分層指引，重試按鈕也走同一個 onRefresh", async () => {
    mockDetail(detail());
    const onRefresh = vi.fn();
    render(
      <ScenarioDetail
        id="s1"
        onRefresh={onRefresh}
        failure={{ stage: "fetch", message: "抓不到 XYZ 的報價：來源無回應" }}
      />,
    );

    expect(await screen.findByText(/抓不到報價/)).toBeInTheDocument();
    expect(screen.getByText(/來源無回應/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "重試" }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("沒有失敗紀錄時不顯示失敗提示", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("已過期的劇本：刷新按鈕停用並顯示與劇本庫一致的文案（#68 既有語彙）", async () => {
    mockDetail(detail({ expired: true }));
    render(<ScenarioDetail id="s1" />);

    const button = await screen.findByRole("button", { name: "已過期，不再刷新" });
    expect(button).toBeDisabled();
  });

  it("已過期的劇本即使帶著舊的失敗紀錄，也不顯示重試——" +
     "兩種狀態同時出現會讓使用者搞不清楚現在是哪一種（比照 ScenarioList）", async () => {
    mockDetail(detail({ expired: true }));
    render(
      <ScenarioDetail
        id="s1"
        failure={{ stage: "fetch", message: "抓不到報價" }}
      />,
    );

    await screen.findByRole("button", { name: "已過期，不再刷新" });
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重試" })).not.toBeInTheDocument();
  });
});

describe("進階區隨新分析失效，不混用新舊 cache（#69）", () => {
  const HISTORY = { entries: [
    { analyzed_at: "2026-08-01T00:00:00+00:00", spot: 100.0, cost: 5.0,
     baseline_return: 0.3, rank_in_expiry: 1 },
  ] };
  const RAW = {
    meta: { symbol: "XYZ", spot: 100.0, fetched_at: "2026-08-04T09:00:00+00:00",
           source: "cboe", contract_count: 1 },
    contracts: [{ contract_symbol: "XYZ261016C00110000", option_type: "call",
                 strike: 110.0, expiry: "2026-10-16", bid: 3.0, ask: 3.25,
                 last: 3.1, volume: 10, open_interest: 20, implied_volatility: 0.3 }],
  };

  /** 精準控制第二次 `getScenario`何時回來，不靠 race 猜時機。 */
  function mockDetailSequence(first: unknown, second: unknown) {
    let scenarioCalls = 0;
    let resolveSecond: (() => void) | null = null;
    const historyCalls: string[] = [];
    const rawDataCalls: string[] = [];
    const spy = vi.fn(async (url: string) => {
      if (url.startsWith("/api/scenarios/s1/history")) {
        historyCalls.push(url);
        return { ok: true, status: 200, json: async () => HISTORY };
      }
      if (url.startsWith("/api/scenarios/s1/raw-data")) {
        rawDataCalls.push(url);
        return { ok: true, status: 200, json: async () => RAW };
      }
      if (url === "/api/scenarios/s1") {
        scenarioCalls += 1;
        if (scenarioCalls === 1) {
          return { ok: true, status: 200, json: async () => first };
        }
        return new Promise((resolve) => {
          resolveSecond = () =>
            resolve({ ok: true, status: 200, json: async () => second });
        });
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    return { historyCalls, rawDataCalls, resolveSecond: () => resolveSecond!() };
  }

  it("刷新後，先前展開過的兩區都收合，不再顯示上一輪的內容", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);

    // 新一輪還沒回來之前，既有規則「刷新造成的重取不清空」仍成立——
    // 先前展開的內容不該憑空消失。
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.getByText("XYZ261016C00110000")).toBeInTheDocument();

    resolveSecond();

    // 新一輪真的落地之後，兩區才收合、內部狀態一起重置。
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.queryByText("XYZ261016C00110000")).not.toBeInTheDocument();
  });

  it("收合後再展開，是真的重新取得，不是沿用上一輪的舊資料", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { historyCalls, rawDataCalls, resolveSecond } =
      mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");
    expect(historyCalls).toHaveLength(1);
    expect(rawDataCalls).toHaveLength(1);

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");

    // 各自又多打了一次——不是沿用元件裡「已經抓過」的舊旗標。
    expect(historyCalls).toHaveLength(2);
    expect(rawDataCalls).toHaveLength(2);
  });

  it("原始資料的 CSV 下載連結跟著換一個網址（#69：不讓瀏覽器快取原樣吐回舊檔）", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    const before = (await screen.findByText("下載 CSV") as HTMLAnchorElement)
      .getAttribute("href");

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByText("下載 CSV")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    const after = (await screen.findByText("下載 CSV") as HTMLAnchorElement)
      .getAttribute("href");

    expect(after).not.toBe(before);
  });

  it("主圖候選因新分析換掉時，歷史走勢跟著換成新候選的序列（AC2）", async () => {
    const originalKey = baselineTopCandidate(view)!.candidate_key;
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({
      latest_analyzed_at: "2026-08-04T10:00:00+00:00",
      latest_result: withTopCandidate({ candidate_key: "different-candidate" }),
    });
    const { historyCalls, resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    expect(historyCalls[0]).toContain(
      `candidate_key=${encodeURIComponent(originalKey)}`);

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");

    // 換一輪之後再展開，帶的是新候選自己的身份鍵，不是沿用第一輪那個。
    expect(historyCalls).toHaveLength(2);
    expect(historyCalls[1]).toContain(
      `candidate_key=${encodeURIComponent("different-candidate")}`);
  });
});

describe("基準候選的候選池警語（V6／#54 檢視回饋，隨 QA 修正搬進摘要卡）", () => {
  it("警語跟著基準候選走，不會因為把清單切到別期就消失", async () => {
    // 基準候選固定是 baseline 期第 1 名。警語只掛在下面那份會切換的
    // 清單上的話，使用者一切到別期，頭條數字就沒人幫它說「這只是整池
    // 僅存者」。
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(summarySection().getByText(/只有 1 組候選/)).toBeInTheDocument();

    const other = view.results[0].expiry_top10!
      .find((g) => g.expiry !== view.baseline_expiry)!;
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(other.expiry) }));

    expect(summarySection().getByText(/只有 1 組候選/)).toBeInTheDocument();
  });
});
