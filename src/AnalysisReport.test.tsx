/**
 * 分析報告新版型（V8／#56）元件測試。用真實契約樣本當底——`Candidate`／
 * `StrategyResult` 欄位很多，手刻假資料容易漏欄位或漏值，真樣本才保證
 * 每個欄位都存在且形狀正確。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import sample from "../contracts/analysis_sample.json";
import AnalysisReport from "./AnalysisReport";
import { baselineTopCandidate, primaryResult, type AnalysisView, type Candidate,
        type StrategyResult } from "./api";

const view = sample as unknown as AnalysisView;
const result = primaryResult(view) as StrategyResult;
const real = baselineTopCandidate(view)!;

function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return { ...real, ...overrides };
}

async function expand() {
  await userEvent.click(screen.getByText("📄 分析報告"));
}

describe("分析報告：無候選時整塊不顯示", () => {
  it("candidate 為 null 時不渲染（跟主圖同樣的邊界，附錄A10.2）", () => {
    const { container } = render(
      <AnalysisReport view={view} result={result} candidate={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("分析報告：預設收合，展開才看得到內容", () => {
  it("展開前內容不可見，展開後才看得到", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    expect(screen.queryByText(/情境分析/)).not.toBeVisible();

    await expand();

    expect(screen.getByText("情境分析")).toBeVisible();
  });
});

describe("① 交易摘要", () => {
  it("一句話結論含成本、損益兩平、最大獲利", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const conclusion = document.querySelector(".report-conclusion")!;
    expect(conclusion.textContent).toContain(`成本 $${real.natural_cost.toFixed(2)}`);
    expect(conclusion.textContent).toContain("損益兩平");
    expect(conclusion.textContent).toContain("最大獲利");
  });

  it("最大獲利與最大損失同框（R1 §1 第 3 點）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("最大獲利")).toBeInTheDocument();
    expect(screen.getByText("最大損失")).toBeInTheDocument();
  });

  it("Long Call 無上限時顯示「無上限」，不是留白或 0", async () => {
    render(<AnalysisReport view={view} result={result}
                          candidate={candidate({ max_profit: null })} />);
    await expand();
    expect(screen.getAllByText(/無上限/).length).toBeGreaterThan(0);
  });
});

describe("③ 情境分析：韌性 7 情境表", () => {
  it("列出 7 個情境，情境最壞標記在對應那一列", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const worstRow = screen.getByText(
      new RegExp(`^${real.scenario_vector.worst_code} `)).closest("tr")!;
    expect(worstRow).toHaveTextContent("◀ 情境最壞");
  });

  it("劇本完成度曲線逐點列出", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(/劇本完成度:/)).toBeInTheDocument();
  });
});

describe("④ 風險與代價", () => {
  it("劇本報酬與情境最壞並排（R1 §2.5 平衡原則）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const row = screen.getByText("劇本報酬（情境最壞並排）").closest(".row")!;
    expect(row).toHaveTextContent("情境最壞");
  });

  it("代價（cons）與買價指引警示都顯示", async () => {
    const withWarnings = candidate({
      cons: ["獲利上限 = 寬度 − 淨成本"],
      guidance_warnings: ["以 Ask 進場達不到你設定的最低報酬"],
    });
    render(<AnalysisReport view={view} result={result} candidate={withWarnings} />);
    await expand();
    expect(screen.getByText("獲利上限 = 寬度 − 淨成本")).toBeInTheDocument();
    expect(screen.getByText("以 Ask 進場達不到你設定的最低報酬")).toBeInTheDocument();
  });

  it("沒有代價或警示時不留一個空區塊", async () => {
    const clean = candidate({ cons: [], guidance_warnings: [] });
    render(<AnalysisReport view={view} result={result} candidate={clean} />);
    await expand();
    expect(document.querySelector(".report-warnings")).not.toBeInTheDocument();
  });

  it("Theta／Vega 標明是佔成本比率（Mid 口徑），不能寫成裸 Greeks", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(/Theta（佔成本比率，Mid 口徑）/)).toBeInTheDocument();
    expect(screen.getByText(/Vega（佔成本比率，Mid 口徑）/)).toBeInTheDocument();
  });
});

describe("⑤ 進場執行：逐腿報價 ＋ 買價指引 L2/L3", () => {
  it("買腿與 L2/L3 都顯示", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("買腿")).toBeInTheDocument();
    expect(screen.getByText(/L2 保守上限/)).toBeInTheDocument();
    expect(screen.getByText(/L3 要求報酬上限/)).toBeInTheDocument();
  });
});

describe("⑥⑦ 方法與假設／免責聲明", () => {
  it("方法論全文與免責段落都在頁面上（即使收合區未展開也在 DOM 裡）",
     async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(/OPTION CHASER|估值: Black-Scholes/))
      .toBeInTheDocument();
    expect(screen.getByText(result.disclaimer_text)).toBeInTheDocument();
  });

  it("免責聲明獨立於方法論折疊區之外——不需要再展開一層就看得到", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(result.disclaimer_text)).toBeVisible();
  });
});

describe("不重複頁面上方已經無條件顯示過的東西（R1 §3.4／設計取捨）", () => {
  it("不含追平價格區塊的重複內容——那已經是頁面上方的獨立區塊", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/追平價格/)).not.toBeInTheDocument();
  });
});
