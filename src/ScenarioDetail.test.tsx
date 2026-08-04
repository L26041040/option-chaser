import { render, screen, within } from "@testing-library/react";
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
