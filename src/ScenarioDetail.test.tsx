import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ScenarioDetail from "./ScenarioDetail";
import sample from "../contracts/analysis_sample.json";
import sampleRow from "../contracts/scenario_row_sample.json";
import { baselineTopCandidate, type AnalysisView } from "./api";

const view = sample as unknown as AnalysisView;
const row = sampleRow as unknown as Record<string, unknown>;

/** 契約樣本本身：目標價 130、追平價 125.33（＝低於目標價的醒目態）。 */
function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...row, id: "s1", symbol: "XYZ", target_price: view.params.target_price,
    target_month: view.params.target_month,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 5.67,
    latest_result: view, ...overrides,
  };
}

/** 改寫 baseline 期第 1 名候選的某些欄位，其餘契約原樣。 */
function withTopCandidate(patch: Record<string, unknown>): AnalysisView {
  const result = view.results[0];
  const groups = result.expiry_top10!.map((g) =>
    g.expiry === view.baseline_expiry
      ? { ...g, candidates: [{ ...g.candidates[0], ...patch }, ...g.candidates.slice(1)] }
      : g);
  return { ...view, results: [{ ...result, expiry_top10: groups }] };
}

/**
 * 主圖那一張表。V6（#54）之後頁面上有很多張 Heatmap（到期日結構裡每個
 * 候選收合著一張），所以這裡的斷言一律鎖定主圖那一區，不用全頁查找。
 */
function mainChart() {
  return within(screen.getByRole("heading", { name: "劇本主圖" })
    .closest("section")!);
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

describe("詳細頁摘要", () => {
  it("顯示現價、目標價與所需漲幅、目標年月、策略", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(`$${view.meta.spot.toFixed(2)}`)).toBeInTheDocument();
    expect(screen.getByText(`$${view.params.target_price.toFixed(2)}`)).toBeInTheDocument();
    // 所需漲幅寫在目標價旁的括號裡，所以用子字串比對
    expect(screen.getByText(`+${(view.meta.target_move * 100).toFixed(1)}%`,
                            { exact: false })).toBeInTheDocument();
    expect(screen.getByText(view.params.target_month)).toBeInTheDocument();
    expect(screen.getByText("Bull Call Spread")).toBeInTheDocument();
  });

  it("有回劇本庫的入口", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("link", { name: /劇本庫/ }))
      .toHaveAttribute("href", "#/");
  });
});

describe("詳細頁主圖", () => {
  it("畫出 baseline 期第 1 名候選的 Heatmap，並標明是哪一組", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    const top = baselineTopCandidate(view)!;
    const [buy, sell] = top.legs;
    await screen.findByText(/劇本主圖/);
    expect(mainChart().getByText(`買 ${buy.strike} / 賣 ${sell.strike}`))
      .toBeInTheDocument();
    expect(mainChart().getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByText(view.baseline_expiry!).length).toBeGreaterThan(0);
    // 主圖旁就是這組候選的劇本報酬——引擎算好的那個數字
    expect(mainChart().getByText(`${(top.baseline_return * 100).toFixed(1)}%`))
      .toBeInTheDocument();
  });
});

describe("追平價格三態", () => {
  it("正常：比較對象、追平價格、離目標多遠", async () => {
    // 追平價 200 遠高於目標價 130 ＝ 一般情況（Spread 仍有優勢）
    mockDetail(detail({ latest_result: withTopCandidate({ catchup_price: 200 }) }));
    render(<ScenarioDetail id="s1" />);

    const top = baselineTopCandidate(view)!;
    const [buy] = top.legs;
    expect(await screen.findByText(new RegExp(`${buy.strike} Long Call`)))
      .toBeInTheDocument();
    expect(screen.getByText(/\$200\.00/)).toBeInTheDocument();
    expect(screen.getByText(/超出目標價/)).toBeInTheDocument();
    expect(screen.queryByText(/即勝過此 Spread/)).not.toBeInTheDocument();
  });

  it("醒目：S* ≤ 目標價時明說 Long Call 在本劇本內就贏了", async () => {
    mockDetail(detail());   // 契約樣本本身就是這一態
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(/即勝過此 Spread/)).toBeInTheDocument();
    expect(screen.getByText(/低於目標價/)).toBeInTheDocument();
  });

  it("無法計算：同履約價 Call 報價缺失時如實說，不報錯也不留白", async () => {
    mockDetail(detail({ latest_result: withTopCandidate({ catchup_price: null }) }));
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(/無法計算/)).toBeInTheDocument();
    // 頁面其他部分照常可讀
    expect(mainChart().getByRole("table")).toBeInTheDocument();
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
});

describe("主圖的候選池警語（V6／#54 檢視回饋）", () => {
  it("警語跟著主圖走，不會因為把清單切到別期就消失", async () => {
    // 主圖固定是 baseline 期第 1 名。警語只掛在下面那份會切換的清單上
    // 的話，使用者一切到別期，頭條數字就沒人幫它說「這只是整池僅存者」。
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(mainChart().getByText(/只有 1 組候選/)).toBeInTheDocument();

    const other = view.results[0].expiry_top10!
      .find((g) => g.expiry !== view.baseline_expiry)!;
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(other.expiry) }));

    expect(mainChart().getByText(/只有 1 組候選/)).toBeInTheDocument();
  });
});

describe("劇本區間三價位對照（V7／#55）", () => {
  const LADDER = [
    { label: "worst", price: 110, return: -1 },
    { label: "target", price: 130, return: 5.667 },
    { label: "best", price: 150, return: 5.667 },
  ];

  function renderWithLadder(ladder: unknown) {
    mockDetail(detail({ latest_result: withTopCandidate({ price_ladder: ladder }) }));
    render(<ScenarioDetail id="s1" />);
  }

  function ladderSection() {
    return within(screen.getByRole("heading", { name: "劇本區間對照" })
      .closest("section")!);
  }

  it("三個價位並列，由最差到最好", async () => {
    renderWithLadder(LADDER);
    await screen.findByRole("heading", { name: "劇本區間對照" });

    const section = ladderSection();
    expect(section.getByText("最差 $110.00")).toBeInTheDocument();
    expect(section.getByText("目標 $130.00")).toBeInTheDocument();
    expect(section.getByText("最好 $150.00")).toBeInTheDocument();
  });

  it("只設定一端時，另一端不顯示也不留空格", async () => {
    renderWithLadder(LADDER.slice(1));
    await screen.findByRole("heading", { name: "劇本區間對照" });

    const section = ladderSection();
    expect(section.queryByText(/最差/)).not.toBeInTheDocument();
    expect(section.getByText("最好 $150.00")).toBeInTheDocument();
  });

  it("兩端都沒設定時整區不出現——不畫一個只有目標價的對照表", async () => {
    renderWithLadder([{ label: "target", price: 130, return: 5.667 }]);
    await screen.findByRole("heading", { name: "劇本主圖" });

    expect(screen.queryByRole("heading", { name: "劇本區間對照" }))
      .not.toBeInTheDocument();
  });

  it("舊資料沒有這個欄位時不會壞（欄位是 V7 才加的）", async () => {
    renderWithLadder(undefined);
    await screen.findByRole("heading", { name: "劇本主圖" });

    expect(screen.queryByRole("heading", { name: "劇本區間對照" }))
      .not.toBeInTheDocument();
  });
});
