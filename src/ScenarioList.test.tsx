import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ScenarioList from "./ScenarioList";
import type { ScenarioSummary } from "./api";

function row(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: "a", symbol: "TLT", target_price: 120, target_month: "2028-05",
    created_at: "2026-08-01T00:00:00+00:00", archived_at: null,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.234,
    target_anchor: "2028-05-19", days_to_anchor: 653,
    ...overrides,
  };
}

describe("劇本清單", () => {
  it("卡片含標的／目標價／目標年月／收益率／距到期天數", () => {
    render(<ScenarioList rows={[row()]} onArchive={vi.fn()} />);

    expect(screen.getByText("TLT")).toBeInTheDocument();
    expect(screen.getByText(/\$120\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2028-05/)).toBeInTheDocument();
    expect(screen.getByText("123.4%")).toBeInTheDocument();
    expect(screen.getByText("653 天")).toBeInTheDocument();
  });

  it("依收益率降序，沒跑過的排最後並顯示「—」", () => {
    render(
      <ScenarioList
        rows={[
          row({ id: "a", symbol: "AAA", best_return: 0.2 }),
          row({ id: "b", symbol: "BBB", best_return: null,
                latest_analyzed_at: null }),
          row({ id: "c", symbol: "CCC", best_return: 2.0 }),
        ]}
        onArchive={vi.fn()}
      />,
    );

    const symbols = screen.getAllByRole("listitem")
      .map((li) => li.querySelector(".big")!.textContent);
    expect(symbols).toEqual(["CCC", "AAA", "BBB"]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("沒跑過時資料時間說「尚未分析」，不留白也不顯示舊時間", () => {
    render(<ScenarioList rows={[row({ best_return: null,
                                      latest_analyzed_at: null })]}
                         onArchive={vi.fn()} />);
    expect(screen.getByText("尚未分析")).toBeInTheDocument();
  });

  it("已過期的劇本說過期幾天，不是 0 天", () => {
    render(<ScenarioList rows={[row({ days_to_anchor: -3 })]}
                         onArchive={vi.fn()} />);
    expect(screen.getByText("已過期 3 天")).toBeInTheDocument();
  });

  it("負收益率用負向顏色，正的用正向", () => {
    render(<ScenarioList rows={[row({ best_return: -0.4 })]}
                         onArchive={vi.fn()} />);
    expect(screen.getByText("-40.0%")).toHaveClass("negative");
  });

  it("封存按鈕帶著劇本身分，一次點擊只封存那一個", async () => {
    const onArchive = vi.fn();
    render(
      <ScenarioList
        rows={[row({ id: "a", symbol: "AAA" }),
               row({ id: "b", symbol: "BBB" })]}
        onArchive={onArchive}
      />,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "封存 BBB 2028-05" }));

    expect(onArchive).toHaveBeenCalledTimes(1);
    expect(onArchive).toHaveBeenCalledWith("b");
  });

  it("一個劇本都沒有時給明確指引，不是空白畫面", () => {
    render(<ScenarioList rows={[]} onArchive={vi.fn()} />);
    expect(screen.getByText(/還沒有劇本/)).toBeInTheDocument();
  });
});
