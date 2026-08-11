import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Heatmap from "./Heatmap";
import sample from "../contracts/analysis_sample.json";
import { baselineTopCandidate, type AnalysisView, type Matrix } from "./api";

const view = sample as unknown as AnalysisView;
const matrix = baselineTopCandidate(view)!.matrix;

/** 報酬率格子＝日期欄那些 `<td>`，不含最右邊的 ±% annotation 欄
 *  （QA-FIX-1）。兩者都是 `<td>`，用 class 分開才不會把 annotation
 *  誤算成一格報酬率。 */
function valueCells(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>("td:not(.heatmap-move-pct)"));
}

describe("主圖 Heatmap", () => {
  it("欄是日期，日期欄之後才是 ±% 欄——價格在最左、±% 在最右", () => {
    render(<Heatmap matrix={matrix} />);

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    // 價格 + N 個日期 + ±%（QA-FIX-1：±% 有自己的欄標題，欄數才對得上）
    expect(headers).toHaveLength(matrix.dates.length + 2);
    expect(headers[0]).toBe("價格");
    expect(headers.at(-2)).toMatch(/到期$/);
    expect(headers.at(-1)).toBe("vs 現價");
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

  it("每一格都是純數字報酬率（#121：不帶 +／%），且格數＝價格數×日期數", () => {
    const { container } = render(<Heatmap matrix={matrix} />);

    const cells = valueCells(container);
    expect(cells).toHaveLength(matrix.prices.length * matrix.dates.length);
    for (const cell of cells) expect(cell.textContent).toMatch(/^-?\d+$/);
  });

  it("賺賠上不同的底色，中性帶不上色", () => {
    const tiny: Matrix = {
      prices: [[100, "<現價>", 0]],
      dates: [["2026-08-07", ""]],
      cells: [[0.0]],
    };
    const { container, rerender } = render(<Heatmap matrix={tiny} />);
    expect(valueCells(container)[0]).toHaveStyle({ background: "transparent" });

    rerender(<Heatmap matrix={{ ...tiny, cells: [[0.8]] }} />);
    expect(valueCells(container)[0])
      .not.toHaveStyle({ background: "transparent" });
  });

  it("表格有可及名稱——底下那段說明是兄弟節點，輔助技術不會當成標題", () => {
    render(<Heatmap matrix={matrix} />);
    expect(screen.getByRole("table", { name: /報酬率/ })).toBeInTheDocument();
  });

  // 「可橫向滑動」在 jsdom 測不到（沒有版面，也沒載入 CSS）：拿
  // `querySelector(".heatmap-scroll")` 當斷言的話，把 `overflow-x` 刪掉
  // 測試照樣綠。真正的守門在 E2E（實測 scrollWidth > clientWidth）。
});

describe("最右欄 ±% 標註（決策 M／#109，位置修正 QA-FIX-1／QA-01）", () => {
  it("DOM 順序：每一列是 價格 → 全部日期格 → ±%，±% 是最後一個子元素", () => {
    const { container } = render(<Heatmap matrix={matrix} />);

    const bodyRows = Array.from(
      container.querySelectorAll<HTMLElement>("tbody tr"));
    expect(bodyRows).toHaveLength(matrix.prices.length);

    for (const row of bodyRows) {
      const kids = Array.from(row.children);
      // 第一個是價格（sticky left），最後一個是 ±%（sticky right）
      expect(kids[0]).toHaveClass("heatmap-price");
      expect(kids.at(-1)).toHaveClass("heatmap-move-pct");
      // 中間全部是日期格，數量剛好等於日期欄數——±% 不佔用其中任何一格
      expect(kids).toHaveLength(matrix.dates.length + 2);
      for (const cell of kids.slice(1, -1)) {
        expect(cell).not.toHaveClass("heatmap-move-pct");
        expect(cell.textContent).toMatch(/^-?\d+$/);
      }
    }
  });

  it("±% 不再被塞進左側價格欄裡——價格欄只有價格與錨點標籤", () => {
    const { container } = render(<Heatmap matrix={matrix} />);

    for (const th of Array.from(
      container.querySelectorAll<HTMLElement>("th.heatmap-price"))) {
      // 價格欄不得出現帶一位小數的 ±%（那是 annotation 欄的格式）
      expect(th.textContent).not.toMatch(/[+-]\d+\.\d%/);
      expect(th.querySelector(".heatmap-move-pct")).toBeNull();
    }
  });

  it("每一個 price row 都有對應且正確的 ±%，值取自 matrix.prices 第三欄"+
     "（引擎給的，不是前端重算）", () => {
    const { container } = render(<Heatmap matrix={matrix} />);

    const annotations = Array.from(
      container.querySelectorAll<HTMLElement>("td.heatmap-move-pct"));
    expect(annotations).toHaveLength(matrix.prices.length);
    // 由高價到低價渲染（既有規則），逐列核對完整格式的 ±% 文字。
    const sorted = [...matrix.prices].sort((a, b) => b[0] - a[0]);
    annotations.forEach((td, i) => {
      const [, , movePct] = sorted[i];
      const pct = movePct * 100;
      const expected = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
      expect(within(td).getByText(expected)).toBeInTheDocument();
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
    const { container } = render(<Heatmap matrix={tiny} />);

    const td = container.querySelector<HTMLElement>("td.heatmap-move-pct")!;
    expect(within(td).getByText("+13.6%")).toBeInTheDocument();
    expect(within(td).getByText("+14%")).toBeInTheDocument();
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

describe("高密度日期軸（QA-FIX-5／QA-01）", () => {
  /** 2.4 年 LEAPS 在 GUI 軸下是 29 欄——契約樣本本身是短天期（7 欄），
   *  所以這裡自己造一份密的，確保渲染路徑撐得住欄數變多。 */
  function denseMatrix(cols: number): Matrix {
    const dates: [string, string][] = Array.from({ length: cols }, (_, i) => {
      const d = new Date(Date.UTC(2026, 7, 9) + i * 31 * 86400000);
      return [d.toISOString().slice(0, 10), ""];
    });
    const prices: [number, string, number][] = [
      [90, "<深跌>", -0.1], [100, "<現價>", 0], [130, "<目標>", 0.3],
    ];
    return {
      prices,
      dates,
      cells: prices.map((_, r) => dates.map((_, c) => (r + c) / 100)),
    };
  }

  it("29 欄日期照樣逐欄畫出來，前端不自己抽樣或截斷", () => {
    const m = denseMatrix(29);
    const { container } = render(<Heatmap matrix={m} />);

    // 欄標題：價格 + 29 個日期 + ±%
    expect(screen.getAllByRole("columnheader")).toHaveLength(31);
    // 每一列的報酬率格數＝日期數，一格不少
    expect(valueCells(container)).toHaveLength(3 * 29);
  });

  it("欄數變多不影響 ±% 仍是每列最後一個子元素（sticky 右欄的前提）", () => {
    const { container } = render(<Heatmap matrix={denseMatrix(29)} />);

    for (const row of Array.from(
      container.querySelectorAll<HTMLElement>("tbody tr"))) {
      expect(row.children[0]).toHaveClass("heatmap-price");
      expect(row.children[row.children.length - 1])
        .toHaveClass("heatmap-move-pct");
    }
  });
});

describe("Crossover Boundary overlay（#116，spec #117 §4）", () => {
  const baseMatrix: Matrix = {
    prices: [[90, "", -0.1], [110, "", 0.1]],
    dates: [["2026-08-07", ""], ["2026-09-07", ""]],
    cells: [[0.5, 0.6], [-0.3, -0.4]],
  };

  function callComparator(matrix: Matrix) {
    return {
      option_type: "call" as const, strike: 118, expiry: "2026-08-07",
      cost: 1.1, matrix,
    };
  }

  function putComparator(matrix: Matrix) {
    return {
      option_type: "put" as const, strike: 82, expiry: "2026-08-07",
      cost: 1.1, matrix,
    };
  }

  it("沒有傳 comparator（單腿候選）：不渲染任何 Crossover 區塊，" +
     "不是渲染成「缺席」", () => {
    render(<Heatmap matrix={baseMatrix} />);
    expect(screen.queryByText(/Crossover/)).not.toBeInTheDocument();
    expect(document.querySelector(".heatmap-crossover-cell")).toBeNull();
  });

  it("comparator 為 null（買腿報價缺失）：顯示一行誠實缺席原因，" +
     "不畫任何邊界、不崩潰", () => {
    render(<Heatmap matrix={baseMatrix} comparator={null} />);
    expect(screen.getByText(/Crossover 對照缺席/)).toBeInTheDocument();
    expect(screen.getByText(/無法取得買腿報價/)).toBeInTheDocument();
    expect(document.querySelector(".heatmap-crossover-cell")).toBeNull();
  });

  it("邊界存在：跨越邊界的格子被標示，圖例講清楚格子仍是 Spread 報酬、" +
     "邊界是兩者相等處，並附 comparator 標籤與成本", () => {
    const comparatorMatrix: Matrix = {
      ...baseMatrix,
      cells: [[0.1, 0.1], [0.1, 0.1]],
    };
    const { container } = render(
      <Heatmap matrix={baseMatrix} comparator={callComparator(comparatorMatrix)} />);

    // diff = [[0.4,0.5],[-0.4,-0.5]] → 兩欄都在 row0/row1 之間翻轉，
    // 四格全部緊鄰邊界。
    const marked = container.querySelectorAll(".heatmap-crossover-cell");
    expect(marked.length).toBeGreaterThan(0);

    expect(screen.getByText(/格子仍是 Spread 報酬率/)).toBeInTheDocument();
    expect(screen.getByText(/報酬相等/)).toBeInTheDocument();
    expect(screen.getByText(/08\/07 118 Long Call/)).toBeInTheDocument();
    expect(screen.getByText(/\$1\.10/)).toBeInTheDocument();
  });

  it("comparator 是 put 時標籤顯示 Long Put，不是 Long Call——直接讀" +
     "option_type，不是從策略反推", () => {
    const comparatorMatrix: Matrix = { ...baseMatrix, cells: [[0.1, 0.1], [0.1, 0.1]] };
    render(<Heatmap matrix={baseMatrix} comparator={putComparator(comparatorMatrix)} />);
    expect(screen.getByText(/08\/07 82 Long Put/)).toBeInTheDocument();
    expect(screen.queryByText(/Long Call/)).not.toBeInTheDocument();
  });

  it("邊界整條落在網格外（Spread 全贏）：不標任何格子，圖例明講" +
     "「全部落在 Spread 較優的一側」，不能讓使用者把「沒畫線」誤讀成" +
     "「沒有 Crossover」", () => {
    const comparatorMatrix: Matrix = {
      ...baseMatrix,
      cells: [[0.1, 0.1], [0.1, 0.1]],
    };
    const spreadAlwaysWins: Matrix = { ...baseMatrix, cells: [[0.5, 0.6], [0.3, 0.4]] };
    const { container } = render(
      <Heatmap matrix={spreadAlwaysWins}
               comparator={callComparator(comparatorMatrix)} />);

    expect(container.querySelectorAll(".heatmap-crossover-cell")).toHaveLength(0);
    expect(screen.getByText(/邊界不在網格上/)).toBeInTheDocument();
    expect(screen.getByText(/全部落在 Spread 較優的一側/)).toBeInTheDocument();
  });

  it("邊界整條落在網格外（comparator 全贏）：圖例明講另一側", () => {
    const comparatorAlwaysWins: Matrix = {
      ...baseMatrix,
      cells: [[0.9, 0.9], [0.9, 0.9]],
    };
    render(<Heatmap matrix={baseMatrix}
                    comparator={callComparator(comparatorAlwaysWins)} />);
    expect(screen.getByText(/全部落在直接買.*較優的一側/)).toBeInTheDocument();
  });

  it("regression：加了 comparator 之後，既有格值／欄數／±% 欄仍然不變" +
     "（overlay 是疊加，不是取代）", () => {
    const comparatorMatrix: Matrix = { ...baseMatrix, cells: [[0.1, 0.1], [0.1, 0.1]] };
    const { container } = render(
      <Heatmap matrix={baseMatrix} comparator={callComparator(comparatorMatrix)} />);

    const valueCells = Array.from(
      container.querySelectorAll<HTMLElement>("td:not(.heatmap-move-pct)"));
    expect(valueCells).toHaveLength(4);   // 2 價格 × 2 日期，不因 overlay 變多變少
    // 格子文字仍是原本的報酬率數字，overlay 沒有蓋掉或改寫它們。
    const texts = valueCells.map((c) => c.textContent).sort();
    expect(texts).toEqual(["-30", "-40", "50", "60"]);

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toHaveLength(baseMatrix.dates.length + 2);   // 不變
    expect(container.querySelectorAll("td.heatmap-move-pct")).toHaveLength(2);
  });
});
