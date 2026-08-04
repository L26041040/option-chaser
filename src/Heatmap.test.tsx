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
      prices: [[100, "<現價>"]],
      dates: [["2026-08-07", ""]],
      cells: [[0.0]],
    };
    const { rerender } = render(<Heatmap matrix={tiny} />);
    expect(screen.getByRole("cell")).toHaveStyle({ background: "transparent" });

    rerender(<Heatmap matrix={{ ...tiny, cells: [[0.8]] }} />);
    expect(screen.getByRole("cell")).not.toHaveStyle({ background: "transparent" });
  });

  it("整張表放在可橫向捲動的容器裡——手機塞不下七欄，不靠縮小字級硬擠", () => {
    const { container } = render(<Heatmap matrix={matrix} />);
    expect(container.querySelector(".heatmap-scroll")).toBeInTheDocument();
  });
});
