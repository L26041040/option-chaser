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

  it("代價（cons）與買價指引警示（guidance_warnings）分開標示，不是同一堆" +
     "看不出差別的清單——CLI 報告本來就分別叫「代價」跟「警示」", async () => {
    const withWarnings = candidate({
      cons: ["獲利上限 = 寬度 − 淨成本"],
      guidance_warnings: ["以 Ask 進場達不到你設定的最低報酬"],
    });
    render(<AnalysisReport view={view} result={result} candidate={withWarnings} />);
    await expand();
    expect(screen.getByText("代價: 獲利上限 = 寬度 − 淨成本")).toBeInTheDocument();
    expect(screen.getByText("警示: 以 Ask 進場達不到你設定的最低報酬"))
      .toBeInTheDocument();
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

describe("⑤ 進場執行：逐腿雙邊報價 ＋ 剩餘天數 ＋ 買價指引 L2/L3", () => {
  it("買腿與 L2/L3 都顯示", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("買腿")).toBeInTheDocument();
    expect(screen.getByText(/L2 保守上限/)).toBeInTheDocument();
    expect(screen.getByText(/L3 要求報酬上限/)).toBeInTheDocument();
  });

  it("每一腿雙邊報價都在——只印最差成交那一邊會把買賣價差資訊藏起來"
     + "（R1 §4.2 A：逐腿 Bid/Ask/IV）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const [buy, sell] = real.legs;
    const buyRow = screen.getByText("買腿").closest(".row")!;
    expect(buyRow).toHaveTextContent(`Bid $${buy.bid.toFixed(2)}`);
    expect(buyRow).toHaveTextContent(`Ask $${buy.ask.toFixed(2)}`);
    if (sell) {
      const sellRow = screen.getByText("賣腿").closest(".row")!;
      expect(sellRow).toHaveTextContent(`Bid $${sell.bid.toFixed(2)}`);
      expect(sellRow).toHaveTextContent(`Ask $${sell.ask.toFixed(2)}`);
    }
  });

  it("剩餘天數顯示（R1 §4.2 B：早就序列化，純文字報告沒印）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(`${real.days_to_expiry} 天`)).toBeInTheDocument();
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

  it("模型參數（利率／IV情境／Delta門檻／要求報酬）都在——R1 §4.2 A "
     + "把「[模型假設]」重排到⑥，不是整段消失", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("無風險利率")).toBeInTheDocument();
    const minReturnRow = screen.getByText("最低要求報酬率").closest(".row")!;
    expect(minReturnRow).toHaveTextContent(
      `${(view.params.min_return * 100).toFixed(1)}%`);
    expect(screen.getByText(
      `${view.params.delta_bands[0]} / ${view.params.delta_bands[1]}`,
    )).toBeInTheDocument();
  });

  it("免責聲明獨立於方法論折疊區之外——不需要再展開一層就看得到", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(result.disclaimer_text)).toBeVisible();
  });
});

describe("無風險利率三態顯示（RC1／#87）", () => {
  it("真正 fallback（無曲線）只顯示常數與 FALLBACK 標籤，不掛任何日期",
     async () => {
    const fallbackView = {
      ...view,
      params: { ...view.params, rate_curve_used: false,
                rate_curve_date: null, rate_curve_stale: false,
                rate: 0.04, rate_note: "曲線不可得" },
    };
    render(<AnalysisReport view={fallbackView} result={result} candidate={real} />);
    await expand();
    const row = screen.getByText("無風險利率").closest(".row")!;
    expect(row).toHaveTextContent("4.0%");
    expect(row).toHaveTextContent("FALLBACK");
    expect(row).toHaveTextContent("Treasury curve unavailable");
    expect(row).not.toHaveTextContent("STALE");
    // 不得出現任何看起來像日期的字串（曲線資料日只在真的用了曲線時才顯示）。
    expect(row).not.toHaveTextContent(/\d{4}-\d{2}-\d{2}/);
  });

  it("真正曲線且新鮮：顯示 curve date，不帶 STALE 標記", async () => {
    const curveView = {
      ...view,
      params: { ...view.params, rate_curve_used: true,
                rate_curve_date: "2026-07-31", rate_curve_stale: false },
    };
    render(<AnalysisReport view={curveView} result={result} candidate={real} />);
    await expand();
    const row = screen.getByText("無風險利率").closest(".row")!;
    expect(row).toHaveTextContent("2026-07-31");
    expect(row).not.toHaveTextContent("FALLBACK");
    expect(row).not.toHaveTextContent("STALE");
  });

  it("真正曲線但陳舊備援：顯示 curve date 且明確標示 STALE", async () => {
    const staleView = {
      ...view,
      params: { ...view.params, rate_curve_used: true,
                rate_curve_date: "2026-07-20", rate_curve_stale: true },
    };
    render(<AnalysisReport view={staleView} result={result} candidate={real} />);
    await expand();
    const row = screen.getByText("無風險利率").closest(".row")!;
    expect(row).toHaveTextContent("2026-07-20");
    expect(row).toHaveTextContent("STALE");
    expect(row).not.toHaveTextContent("FALLBACK");
  });

  it("使用者明示利率（CLI --rate，rate_explicit）：乾淨顯示，不貼 FALLBACK 標籤",
     async () => {
    // 目前網頁路徑打不到這一態（`rate_explicit` 只有 CLI 會設起），
    // 但前端邏輯要跟後端 report.py::_rate_line 同一套三態判斷對得上，
    // 不能只在後端正確、前端漏了這一態。
    const explicitView = {
      ...view,
      params: { ...view.params, rate_curve_used: false, rate_curve_date: null,
                rate_curve_stale: false, rate_explicit: true, rate: 0.07,
                rate_note: "" },
    };
    render(<AnalysisReport view={explicitView} result={result} candidate={real} />);
    await expand();
    const row = screen.getByText("無風險利率").closest(".row")!;
    expect(row).toHaveTextContent("7.0%");
    expect(row).not.toHaveTextContent("FALLBACK");
    expect(row).not.toHaveTextContent("STALE");
  });
});

describe("不重複頁面上方已經無條件顯示過的東西（R1 §3.4／設計取捨）", () => {
  it("不含追平價格區塊的重複內容——那已經是頁面上方的獨立區塊", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/追平價格/)).not.toBeInTheDocument();
  });
});
