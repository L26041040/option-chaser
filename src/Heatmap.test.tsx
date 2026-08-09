import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Heatmap from "./Heatmap";
import sample from "../contracts/analysis_sample.json";
import { baselineTopCandidate, type AnalysisView, type Matrix } from "./api";

const view = sample as unknown as AnalysisView;
const matrix = baselineTopCandidate(view)!.matrix;

describe("主圖 Heatmap", () => {
  it("欄是日期、最後一欄講明是到期日", () => {
    render(<Heatmap matrix={matrix} />);

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers[0]).toBe("價格");
    expect(headers).toHaveLength(matrix.dates.length + 1);
    expect(headers.at(-1)).toMatch(/到期$/);
  });

  it("列由高價到低價——漲在上、跌在下，與看盤軟體一致", () => {
    render(<Heatmap matrix={matrix} />);

    const prices = screen.getAllByRole("rowheader")
      .map((h) => Number.parseFloat(h.textContent!));
    expect(prices).toEqual([...prices].sort((a, b) => b - a));
    expect(prices).toHaveLength(matrix.prices.length);
  });

  it("錨點列標出現價／目標，而且是引擎給的標籤、不是自己算的", () => {
    render(<Heatmap matrix={matrix} />);

    expect(screen.getByText("現價")).toBeInTheDocument();
    expect(screen.getByText("目標")).toBeInTheDocument();
    // 契約樣本的現價是 100.00，錨點標記必須跟它同一列
    const row = screen.getByText("現價").closest("tr")!;
    expect(within(row).getByRole("rowheader")).toHaveTextContent("100.00");
  });

  it("每一格都是帶正負號的報酬率，且格數＝價格數×日期數", () => {
    render(<Heatmap matrix={matrix} />);

    const cells = screen.getAllByRole("cell");
    expect(cells).toHaveLength(matrix.prices.length * matrix.dates.length);
    for (const cell of cells) expect(cell.textContent).toMatch(/^[+-]\d+%$/);
  });

  it("賺賠上不同的底色，中性帶不上色", () => {
    const tiny: Matrix = {
      prices: [[100, "<現價>", 0]],
      dates: [["2026-08-07", ""]],
      cells: [[0.0]],
    };
    const { rerender } = render(<Heatmap matrix={tiny} />);
    expect(screen.getByRole("cell")).toHaveStyle({ background: "transparent" });

    rerender(<Heatmap matrix={{ ...tiny, cells: [[0.8]] }} />);
    expect(screen.getByRole("cell")).not.toHaveStyle({ background: "transparent" });
  });

  it("表格有可及名稱——底下那段說明是兄弟節點，輔助技術不會當成標題", () => {
    render(<Heatmap matrix={matrix} />);
    expect(screen.getByRole("table", { name: /報酬率/ })).toBeInTheDocument();
  });

  // 「可橫向滑動」在 jsdom 測不到（沒有版面，也沒載入 CSS）：拿
  // `querySelector(".heatmap-scroll")` 當斷言的話，把 `overflow-x` 刪掉
  // 測試照樣綠。真正的守門在 E2E（實測 scrollWidth > clientWidth）。
});

describe("價格右側 ±% 標註（決策 M／#109）", () => {
  it("每一個 price row 都有對應且正確的 ±% 標註，值取自 matrix.prices 第三欄"+
     "（引擎給的，不是前端重算）", () => {
    render(<Heatmap matrix={matrix} />);

    const rowHeaders = screen.getAllByRole("rowheader");
    expect(rowHeaders).toHaveLength(matrix.prices.length);
    // 由高價到低價渲染（既有規則），逐列核對完整格式的 ±% 文字。
    const sorted = [...matrix.prices].sort((a, b) => b[0] - a[0]);
    rowHeaders.forEach((th, i) => {
      const [, , movePct] = sorted[i];
      const pct = movePct * 100;
      const expected = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
      expect(within(th).getByText(expected)).toBeInTheDocument();
    });
  });

  it("現價那一列標註恆為 +0.0%——跟自己比不可能有變動", () => {
    render(<Heatmap matrix={matrix} />);
    const row = screen.getByText("現價").closest("tr")!;
    expect(within(row).getByText("+0.0%")).toBeInTheDocument();
  });

  it("完整格式與短格式（Mobile）兩種文字同時畫進 DOM——不靠 JS 判斷" +
     "視窗寬度，用 CSS 切換顯示，手機視窗不需要額外互動也看得到", () => {
    const tiny: Matrix = {
      prices: [[105, "", 0.136]],
      dates: [["2026-08-07", ""]],
      cells: [[0.0]],
    };
    render(<Heatmap matrix={tiny} />);

    const th = screen.getByRole("rowheader");
    expect(within(th).getByText("+13.6%")).toBeInTheDocument();
    expect(within(th).getByText("+14%")).toBeInTheDocument();
  });

  it("深跌／超標兩端的正負號方向跟價格相對現價的位置一致", () => {
    // 契約樣本是 bullish：深跌在現價之下（負）、超標在現價之上（正）。
    const row = (tag: string) => screen.getByText(tag).closest("tr")!;
    render(<Heatmap matrix={matrix} />);

    const adverseText = within(row("深跌")).getByText(/^[+-]\d+\.\d%$/);
    const overshootText = within(row("超標")).getByText(/^[+-]\d+\.\d%$/);
    expect(adverseText.textContent).toMatch(/^-/);
    expect(overshootText.textContent).toMatch(/^\+/);
  });
});
