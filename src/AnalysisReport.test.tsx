/**
 * 分析報告四區塊（MVP V3／#105，spec #102 決策 G）元件測試。用真實
 * 契約樣本當底——`Candidate`／`StrategyResult` 欄位很多，手刻假資料
 * 容易漏欄位或漏值，真樣本才保證每個欄位都存在且形狀正確。
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
    expect(screen.queryByText("Risk / Payoff")).not.toBeVisible();

    await expand();

    expect(screen.getByText("Risk / Payoff")).toBeVisible();
  });
});

describe("四區塊固定存在（決策 G：只保留四塊）", () => {
  it("Risk / Payoff、Position Sensitivity、Execution、Model & Assumptions 都在",
     async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("Risk / Payoff")).toBeInTheDocument();
    expect(screen.getByText("Position Sensitivity")).toBeInTheDocument();
    expect(screen.getByText("Execution")).toBeInTheDocument();
    expect(screen.getByText("Model & Assumptions")).toBeInTheDocument();
  });
});

describe("Risk / Payoff", () => {
  it("Breakeven／Max Profit／Max Loss 都顯示實際數字", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const breakevenRow = screen.getByText("Breakeven").closest(".row")!;
    expect(breakevenRow).toHaveTextContent(`$${real.breakeven_points[0].toFixed(2)}`);
    const maxLossRow = screen.getByText("Max Loss").closest(".row")!;
    expect(maxLossRow).toHaveTextContent(
      `$${(real.max_loss_per_contract / 100).toFixed(2)}`);
  });

  it("T16（#232）：既有四策略 max_loss_per_contract／natural_cost 逐位元" +
     "相同——Max Loss 改讀前者不改變既有畫面數字", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const maxLossRow = screen.getByText("Max Loss").closest(".row")!;
    expect(maxLossRow).toHaveTextContent(`$${real.natural_cost.toFixed(2)}`);
  });

  it("T16（#232）：Butterfly 兩個損益兩平點都顯示，並附獲利區間說明", async () => {
    const two = candidate({
      breakeven: null, breakeven_points: [100.49, 111.51],
      profit_region: [100.49, 111.51],
    });
    render(<AnalysisReport view={view} result={result} candidate={two} />);
    await expand();
    const breakevenRow = screen.getByText("Breakeven").closest(".row")!;
    expect(breakevenRow).toHaveTextContent("$100.49");
    expect(breakevenRow).toHaveTextContent("$111.51");
    const regionRow = screen.getByText("獲利區間").closest(".row")!;
    expect(regionRow).toHaveTextContent("$100.49");
    expect(regionRow).toHaveTextContent("$111.51");
  });

  it("CLOSEOUT-004（Finding 1）：broken-wing Butterfly 的獲利區間在上方" +
     "沒有界時顯示「$X 以上」，且不得說「區間外無法獲利」", async () => {
    // call-fly 100/110/115、成本 4.00：K3 之外 payoff 恆為 5.00，
    // 永遠賺 1.00——上界不存在，損益兩平點只有一個。
    const openUp = candidate({
      breakeven: 104.0, breakeven_points: [104.0],
      profit_region: [104.0, null],
    });
    render(<AnalysisReport view={view} result={result} candidate={openUp} />);
    await expand();
    const breakevenRow = screen.getByText("Breakeven").closest(".row")!;
    expect(breakevenRow).toHaveTextContent("$104.00");
    const regionRow = screen.getByText("獲利區間").closest(".row")!;
    expect(regionRow).toHaveTextContent("$104.00 以上");
    expect(regionRow).toHaveTextContent("更高的標的價到期時一樣獲利");
    // 這才是真正要擋的東西：不能對使用者說一個不存在的上界，也不能
    // 說區間外不賺。修正前這裡會是「$104.00 ~ $115.00（標的落在這個
    // 範圍內，到期時為正報酬）」。
    expect(regionRow).not.toHaveTextContent("~");
    expect(regionRow).not.toHaveTextContent("落在這個範圍內");
  });

  it("CLOSEOUT-004（Finding 1）：put-fly 的鏡射——下方沒有界時顯示" +
     "「$X 以下」", async () => {
    const openDown = candidate({
      breakeven: 111.0, breakeven_points: [111.0],
      profit_region: [null, 111.0],
    });
    render(<AnalysisReport view={view} result={result} candidate={openDown} />);
    await expand();
    const regionRow = screen.getByText("獲利區間").closest(".row")!;
    expect(regionRow).toHaveTextContent("$111.00 以下");
    expect(regionRow).toHaveTextContent("更低的標的價到期時一樣獲利");
    expect(regionRow).not.toHaveTextContent("~");
  });

  it("T16（#232）：Butterfly 到期時任何價位都無法獲利時，Breakeven 誠實" +
     "顯示「無」，不假造一個數字，也不顯示獲利區間列", async () => {
    const none = candidate({ breakeven: null, breakeven_points: [], profit_region: null });
    render(<AnalysisReport view={view} result={result} candidate={none} />);
    await expand();
    const breakevenRow = screen.getByText("Breakeven").closest(".row")!;
    expect(breakevenRow).toHaveTextContent("無（到期時任何價位都無法獲利）");
    expect(screen.queryByText("獲利區間")).not.toBeInTheDocument();
  });

  it("T16（#232）：broken-wing Butterfly 的 Max Loss 可能超過進場成本" +
     "（natural_cost）——讀 max_loss_per_contract 才是誠實的數字", async () => {
    const brokenWing = candidate({
      natural_cost: 0.49, max_loss_per_contract: 349.0,
    });
    render(<AnalysisReport view={view} result={result} candidate={brokenWing} />);
    await expand();
    const maxLossRow = screen.getByText("Max Loss").closest(".row")!;
    expect(maxLossRow).toHaveTextContent("$3.49");
    expect(maxLossRow).not.toHaveTextContent("$0.49");
  });

  it("T04（#220，#217 決策 D）：Execution Friction 這一列已移除，不再顯示", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText("Execution Friction")).not.toBeInTheDocument();
  });

  it("Long Call 無上限時 Max Profit 顯示「無上限」，不是留白或 0", async () => {
    render(<AnalysisReport view={view} result={result}
                          candidate={candidate({ max_profit: null })} />);
    await expand();
    const row = screen.getByText("Max Profit").closest(".row")!;
    expect(row).toHaveTextContent("無上限");
  });

  it("Max Profit 有上限時顯示金額", async () => {
    render(<AnalysisReport view={view} result={result}
                          candidate={candidate({ max_profit: 14.8 })} />);
    await expand();
    const row = screen.getByText("Max Profit").closest(".row")!;
    expect(row).toHaveTextContent("$14.80");
  });
});

describe("Position Sensitivity", () => {
  it("Net Delta／Theta/day／Vega/1 vol point／Effective Leverage 都在", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText("Net Delta")).toBeInTheDocument();
    expect(screen.getByText("Theta/day")).toBeInTheDocument();
    expect(screen.getByText("Vega/1 vol point")).toBeInTheDocument();
    const leverageRow = screen.getByText("Effective Leverage").closest(".row")!;
    expect(leverageRow).toHaveTextContent(`${real.effective_leverage.toFixed(1)}x`);
  });
});

describe("Execution", () => {
  it("逐腿雙邊報價都在——只印最差成交那一邊會把買賣價差資訊藏起來", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const [buy, sell] = real.legs;
    const buyRow = screen.getByText("Buy Leg").closest(".row")!;
    expect(buyRow).toHaveTextContent(`Bid $${buy.bid.toFixed(2)}`);
    expect(buyRow).toHaveTextContent(`Ask $${buy.ask.toFixed(2)}`);
    if (sell) {
      const sellRow = screen.getByText("Sell Leg").closest(".row")!;
      expect(sellRow).toHaveTextContent(`Bid $${sell.bid.toFixed(2)}`);
      expect(sellRow).toHaveTextContent(`Ask $${sell.ask.toFixed(2)}`);
    }
  });

  it("Net Mid 與 Net Worst 並列，兩個成本口徑都看得到", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const midRow = screen.getByText("Net Mid").closest(".row")!;
    expect(midRow).toHaveTextContent(`$${real.mid_cost.toFixed(2)}`);
    const worstRow = screen.getByText(/Net Worst/).closest(".row")!;
    expect(worstRow).toHaveTextContent(`$${real.natural_cost.toFixed(2)}`);
  });

  it("Volume／OI 低權重顯示，不帶警示樣式（MVP V3／#104 裁示：中性 metadata）",
     async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    const [buy] = real.legs;
    const buyRow = screen.getByText("Buy Leg").closest(".row")!;
    expect(buyRow).toHaveTextContent(`Volume ${buy.volume}`);
    expect(buyRow).toHaveTextContent(`OI ${buy.open_interest}`);
    // 低權重＝跟著 IV 走同一個 `row-note`，不是獨立一列、不帶 notice/warn 樣式。
    expect(buyRow.querySelector(".notice")).toBeNull();
    expect(buyRow.querySelector(".row-note")).not.toBeNull();
  });

  it("T12（#228）：三隻腿的候選完整渲染，一隻都不丟——合成資料（Butterfly 產生器要等 T15）",
     async () => {
    const leg1 = real.legs[0];
    const leg2 = real.legs.find((l) => l.side === "sell")!;
    const legThree = { ...leg1, strike: 130, side: "buy" as const };
    const three = candidate({ legs: [leg1, leg2, legThree] });
    render(<AnalysisReport view={view} result={result} candidate={three} />);
    await expand();

    // 兩個買腿都在，各自帶編號區分；賣腿維持單一不編號。
    const buy1Row = screen.getByText("Buy Leg 1").closest(".row")!;
    const buy2Row = screen.getByText("Buy Leg 2").closest(".row")!;
    const sellRow = screen.getByText("Sell Leg").closest(".row")!;
    expect(buy1Row).toHaveTextContent(`Strike ${leg1.strike}`);
    expect(buy2Row).toHaveTextContent(`Strike ${legThree.strike}`);
    expect(sellRow).toHaveTextContent(`Strike ${leg2.strike}`);
  });
});

describe("Model & Assumptions", () => {
  it("預設收合，需另外展開才看得到參數細節（決策 G）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText("Rate used")).not.toBeVisible();

    await userEvent.click(screen.getByText("Model & Assumptions"));

    expect(screen.getByText("Rate used")).toBeVisible();
  });

  it("模型參數（利率四項／IV情境／Delta門檻／要求報酬）都在", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    await userEvent.click(screen.getByText("Model & Assumptions"));
    expect(screen.getByText("Rate used")).toBeInTheDocument();
    expect(screen.getByText("Tenor")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Curve date")).toBeInTheDocument();
    const minReturnRow = screen.getByText("最低要求報酬率").closest(".row")!;
    expect(minReturnRow).toHaveTextContent(
      `${(view.params.min_return * 100).toFixed(1)}%`);
    expect(screen.getByText(
      `${view.params.delta_bands[0]} / ${view.params.delta_bands[1]}`,
    )).toBeInTheDocument();
  });
});

describe("免責聲明：獨立、不折疊（不是四區塊之一）", () => {
  it("即使外層收合區未展開，也不需要再展開就看得到（在 DOM 裡）", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.getByText(result.disclaimer_text)).toBeVisible();
  });
});

describe("無風險利率四項顯示（RC1／#87 三態語意，MVP V3／#112 決策 H：Rate used／" +
   "Tenor／Source／Curve date）", () => {
  async function expandModelAssumptions() {
    await expand();
    await userEvent.click(screen.getByText("Model & Assumptions"));
  }

  it("Tenor 一律讀 candidate.rate_tenor_years，前端不查表不換算", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expandModelAssumptions();
    const row = screen.getByText("Tenor").closest(".row")!;
    expect(row).toHaveTextContent(`${real.rate_tenor_years.toFixed(2)} 年`);
  });

  it("真正 fallback（無曲線）：Rate used 顯示 candidate.rate_used 與 FALLBACK 標籤，" +
     "Source 標示常數來源，Curve date 是「—」不掛任何日期", async () => {
    const fallbackView = {
      ...view,
      params: { ...view.params, rate_curve_used: false,
                rate_curve_date: null, rate_curve_stale: false,
                rate: 0.04, rate_note: "曲線不可得" },
    };
    const fallbackCandidate = candidate({ rate_used: 0.04 });
    render(<AnalysisReport view={fallbackView} result={result}
                          candidate={fallbackCandidate} />);
    await expandModelAssumptions();

    const rateRow = screen.getByText("Rate used").closest(".row")!;
    expect(rateRow).toHaveTextContent("4.0%");
    expect(rateRow).toHaveTextContent("FALLBACK");
    expect(rateRow).toHaveTextContent("Treasury curve unavailable");
    expect(rateRow).not.toHaveTextContent("STALE");

    const sourceRow = screen.getByText("Source").closest(".row")!;
    expect(sourceRow).toHaveTextContent("Fallback 常數");

    const curveDateRow = screen.getByText("Curve date").closest(".row")!;
    expect(curveDateRow).toHaveTextContent("—");
    // 不得出現任何看起來像日期的字串（曲線資料日只在真的用了曲線時才顯示）。
    expect(curveDateRow).not.toHaveTextContent(/\d{4}-\d{2}-\d{2}/);
  });

  it("真正曲線且新鮮：Rate used 顯示該候選自己查表算出的數值（可能跟其他候選不同），" +
     "Source 是 US Treasury，Curve date 顯示曲線資料日、不帶 STALE 標記", async () => {
    const curveView = {
      ...view,
      params: { ...view.params, rate_curve_used: true,
                rate_curve_date: "2026-07-31", rate_curve_stale: false },
    };
    const curveCandidate = candidate({ rate_used: 0.041 });
    render(<AnalysisReport view={curveView} result={result}
                          candidate={curveCandidate} />);
    await expandModelAssumptions();

    const rateRow = screen.getByText("Rate used").closest(".row")!;
    expect(rateRow).toHaveTextContent("4.1%");
    expect(rateRow).not.toHaveTextContent("FALLBACK");

    const sourceRow = screen.getByText("Source").closest(".row")!;
    expect(sourceRow).toHaveTextContent("US Treasury");

    const curveDateRow = screen.getByText("Curve date").closest(".row")!;
    expect(curveDateRow).toHaveTextContent("2026-07-31");
    expect(curveDateRow).not.toHaveTextContent("STALE");
  });

  it("真正曲線但陳舊備援：Curve date 明確標示 STALE，Rate used 不帶 FALLBACK", async () => {
    const staleView = {
      ...view,
      params: { ...view.params, rate_curve_used: true,
                rate_curve_date: "2026-07-20", rate_curve_stale: true },
    };
    render(<AnalysisReport view={staleView} result={result} candidate={real} />);
    await expandModelAssumptions();

    const curveDateRow = screen.getByText("Curve date").closest(".row")!;
    expect(curveDateRow).toHaveTextContent("2026-07-20");
    expect(curveDateRow).toHaveTextContent("STALE");

    const rateRow = screen.getByText("Rate used").closest(".row")!;
    expect(rateRow).not.toHaveTextContent("FALLBACK");
  });

  it("使用者明示利率（CLI --rate，rate_explicit）：Rate used 乾淨顯示、不貼 FALLBACK，" +
     "Source 標示「CLI 明示」，Curve date 是「—」", async () => {
    // 目前網頁路徑打不到這一態（`rate_explicit` 只有 CLI 會設起），
    // 但前端邏輯要跟後端 report.py::_rate_line 同一套三態判斷對得上，
    // 不能只在後端正確、前端漏了這一態。
    const explicitView = {
      ...view,
      params: { ...view.params, rate_curve_used: false, rate_curve_date: null,
                rate_curve_stale: false, rate_explicit: true, rate: 0.07,
                rate_note: "" },
    };
    const explicitCandidate = candidate({ rate_used: 0.07 });
    render(<AnalysisReport view={explicitView} result={result}
                          candidate={explicitCandidate} />);
    await expandModelAssumptions();

    const rateRow = screen.getByText("Rate used").closest(".row")!;
    expect(rateRow).toHaveTextContent("7.0%");
    expect(rateRow).not.toHaveTextContent("FALLBACK");
    expect(rateRow).not.toHaveTextContent("STALE");

    const sourceRow = screen.getByText("Source").closest(".row")!;
    expect(sourceRow).toHaveTextContent("CLI 明示");

    const curveDateRow = screen.getByText("Curve date").closest(".row")!;
    expect(curveDateRow).toHaveTextContent("—");
  });
});

describe("股利殖利率 q 三項顯示（#123：q used／Dividend source／Data as of）", () => {
  async function expandModelAssumptions() {
    await expand();
    await userEvent.click(screen.getByText("Model & Assumptions"));
  }

  it("q 管線未接（q_by_symbol 為 null）：q used 顯示 0.0% 與 NO DIVIDEND " +
     "ADJUSTMENT 標籤，Dividend source／Data as of 皆為「—」", async () => {
    const noQView = {
      ...view,
      params: { ...view.params, q_by_symbol: null, q_source: null,
                q_as_of: null, q_stale: false, q_note: "配息資料不可得" },
    };
    render(<AnalysisReport view={noQView} result={result} candidate={real} />);
    await expandModelAssumptions();

    const qRow = screen.getByText("q used").closest(".row")!;
    expect(qRow).toHaveTextContent("0.0%");
    expect(qRow).toHaveTextContent("NO DIVIDEND ADJUSTMENT");
    expect(qRow).toHaveTextContent("配息資料不可得");

    const sourceRow = screen.getByText("Dividend source").closest(".row")!;
    expect(sourceRow).toHaveTextContent("—");
    const asOfRow = screen.getByText("Data as of").closest(".row")!;
    expect(asOfRow).toHaveTextContent("—");
    expect(asOfRow).not.toHaveTextContent(/\d{4}-\d{2}-\d{2}/);
  });

  it("q 成功取得且新鮮：q used 顯示實際百分比，Dividend source 顯示 vendor，" +
     "Data as of 顯示資料截至日、不帶 STALE", async () => {
    const qView = {
      ...view,
      params: { ...view.params, q_by_symbol: 0.046, q_source: "yahoo",
                q_as_of: "2026-08-10", q_stale: false, q_note: "" },
    };
    render(<AnalysisReport view={qView} result={result} candidate={real} />);
    await expandModelAssumptions();

    const qRow = screen.getByText("q used").closest(".row")!;
    expect(qRow).toHaveTextContent("4.6%");
    expect(qRow).not.toHaveTextContent("NO DIVIDEND ADJUSTMENT");

    const sourceRow = screen.getByText("Dividend source").closest(".row")!;
    expect(sourceRow).toHaveTextContent("yahoo");

    const asOfRow = screen.getByText("Data as of").closest(".row")!;
    expect(asOfRow).toHaveTextContent("2026-08-10");
    expect(asOfRow).not.toHaveTextContent("STALE");
  });

  it("q 陳舊備援：Data as of 明確標示 STALE，q used 仍是實際數值（不是 0）",
     async () => {
    const staleQView = {
      ...view,
      params: { ...view.params, q_by_symbol: 0.045, q_source: "yahoo",
                q_as_of: "2026-06-01", q_stale: true, q_note: "" },
    };
    render(<AnalysisReport view={staleQView} result={result} candidate={real} />);
    await expandModelAssumptions();

    const asOfRow = screen.getByText("Data as of").closest(".row")!;
    expect(asOfRow).toHaveTextContent("2026-06-01");
    expect(asOfRow).toHaveTextContent("STALE");

    const qRow = screen.getByText("q used").closest(".row")!;
    expect(qRow).toHaveTextContent("4.5%");
    expect(qRow).not.toHaveTextContent("NO DIVIDEND ADJUSTMENT");
  });

  it("q 與利率兩個區塊的標籤不互相碰撞——Source／Curve date 各自唯一可定位",
     async () => {
    const bothView = {
      ...view,
      params: { ...view.params, rate_curve_used: true,
                rate_curve_date: "2026-07-31", rate_curve_stale: false,
                q_by_symbol: 0.046, q_source: "yahoo", q_as_of: "2026-08-10",
                q_stale: false, q_note: "" },
    };
    render(<AnalysisReport view={bothView} result={result} candidate={real} />);
    await expandModelAssumptions();

    // 兩者都能被唯一定位，不會因為文字重名而拿到超過一個元素。
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Dividend source")).toBeInTheDocument();
    expect(screen.getByText("Curve date")).toBeInTheDocument();
    expect(screen.getByText("Data as of")).toBeInTheDocument();
  });
});

describe("依決策 G 移除、不再渲染的項目（負向斷言）", () => {
  it("不含一句話結論或重複的策略／候選身分——「基準候選」區塊已經顯示（#103）",
     async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(document.querySelector(".report-conclusion")).not.toBeInTheDocument();
    expect(screen.queryByText(/到期.*成本.*損益兩平/)).not.toBeInTheDocument();
  });

  it("不含追平價格區塊的重複內容——那已經是頁面上方的獨立區塊", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/追平價格/)).not.toBeInTheDocument();
  });

  it("不含 baseline return 與情境最壞並排（劇本主圖與基準候選已顯示過報酬）",
     async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/劇本報酬（情境最壞並排）/)).not.toBeInTheDocument();
  });

  it("不含 7 情境韌性表與劇本完成度曲線", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText("情境分析")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/劇本完成度:/)).not.toBeInTheDocument();
    for (const [code] of real.scenario_vector.entries) {
      expect(screen.queryByText(new RegExp(`^${code} `))).not.toBeInTheDocument();
    }
  });

  it("不含 filter／pair 統計一行——CandidatePool 已負責", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/掃描.*張.*合格.*張/)).not.toBeInTheDocument();
  });

  it("不含大段 methodology 散文原文", async () => {
    // T04（#188）：`methodology_text` 已從契約移除（前端零引用），這裡
    // 只剩「沒有這個 DOM 節點」可斷言——契約層級已經保證這段散文
    // 不會出現在 payload 裡，不需要再對照一個不存在的欄位值。
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    await userEvent.click(screen.getByText("Model & Assumptions"));
    expect(document.querySelector(".report-methodology-text")).not.toBeInTheDocument();
  });

  it("不含保本門檻、不漲保留率——未在四區塊清單內", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText("保本門檻")).not.toBeInTheDocument();
    expect(screen.queryByText("不漲保留率")).not.toBeInTheDocument();
  });

  it("不含代價（cons）與買價指引警示（guidance_warnings）——未在四區塊清單內",
     async () => {
    const withWarnings = candidate({
      cons: ["獲利上限 = 寬度 − 淨成本"],
      guidance_warnings: ["以 Ask 進場達不到你設定的最低報酬"],
    });
    render(<AnalysisReport view={view} result={result} candidate={withWarnings} />);
    await expand();
    expect(screen.queryByText(/代價: /)).not.toBeInTheDocument();
    expect(screen.queryByText(/警示: /)).not.toBeInTheDocument();
    expect(document.querySelector(".report-warnings")).not.toBeInTheDocument();
  });

  it("不含剩餘天數與買價指引 L2/L3——未在四區塊清單內", async () => {
    render(<AnalysisReport view={view} result={result} candidate={real} />);
    await expand();
    expect(screen.queryByText(/剩餘天數/)).not.toBeInTheDocument();
    expect(screen.queryByText(/L2 保守上限/)).not.toBeInTheDocument();
    expect(screen.queryByText(/L3 要求報酬上限/)).not.toBeInTheDocument();
  });
});
