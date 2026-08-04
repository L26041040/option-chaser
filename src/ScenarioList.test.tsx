import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ScenarioList from "./ScenarioList";
import sampleRow from "../contracts/scenario_row_sample.json";
import type { RefreshFailure, ScenarioSummary } from "./api";

/** 卡片上的「資料時間」都以這個時刻為基準判斷新鮮度。 */
const NOW = new Date("2026-08-04T10:00:00+00:00");

function row(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    ...(sampleRow as unknown as ScenarioSummary),
    id: "a", symbol: "TLT", target_price: 120, target_month: "2028-05",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.234,
    target_anchor: "2028-05-19", days_to_anchor: 653,
    ...overrides,
  };
}

function list(
  rows: ScenarioSummary[],
  props: {
    failures?: Record<string, RefreshFailure>;
    onArchive?: (id: string) => void;
    onRetry?: (id: string) => void;
    now?: Date;
  } = {},
) {
  return render(
    <ScenarioList
      rows={rows}
      failures={props.failures ?? {}}
      onArchive={props.onArchive ?? vi.fn()}
      onRetry={props.onRetry ?? vi.fn()}
      now={props.now ?? NOW}
    />,
  );
}

describe("劇本清單", () => {
  it("卡片含標的／目標價／目標年月／收益率／距到期天數", () => {
    list([row()]);

    expect(screen.getByText("TLT")).toBeInTheDocument();
    expect(screen.getByText(/\$120\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2028-05/)).toBeInTheDocument();
    expect(screen.getByText("123.4%")).toBeInTheDocument();
    expect(screen.getByText("653 天")).toBeInTheDocument();
  });

  it("依收益率降序，沒跑過的排最後並顯示「—」", () => {
    list([
      row({ id: "a", symbol: "AAA", best_return: 0.2 }),
      row({ id: "b", symbol: "BBB", best_return: null,
            latest_analyzed_at: null }),
      row({ id: "c", symbol: "CCC", best_return: 2.0 }),
    ]);

    const symbols = screen.getAllByRole("listitem")
      .map((li) => li.querySelector(".big")!.textContent);
    expect(symbols).toEqual(["CCC", "AAA", "BBB"]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("沒跑過時資料時間說「尚未分析」，不留白也不顯示舊時間", () => {
    list([row({ best_return: null, latest_analyzed_at: null })]);
    expect(screen.getByText("尚未分析")).toBeInTheDocument();
  });

  it("已過期的劇本說過期幾天，不是 0 天", () => {
    list([row({ days_to_anchor: -3 })]);
    expect(screen.getByText("已過期 3 天")).toBeInTheDocument();
  });

  it("負收益率用負向顏色，正的用正向", () => {
    list([row({ best_return: -0.4 })]);
    expect(screen.getByText("-40.0%")).toHaveClass("negative");
  });

  it("封存按鈕帶著劇本身分，一次點擊只封存那一個", async () => {
    const onArchive = vi.fn();
    list([row({ id: "a", symbol: "AAA" }), row({ id: "b", symbol: "BBB" })],
         { onArchive });

    await userEvent.click(
      screen.getByRole("button", { name: "封存 BBB 2028-05" }));

    expect(onArchive).toHaveBeenCalledTimes(1);
    expect(onArchive).toHaveBeenCalledWith("b");
  });

  it("一個劇本都沒有時給明確指引，不是空白畫面", () => {
    list([]);
    expect(screen.getByText(/還沒有劇本/)).toBeInTheDocument();
  });
});

describe("收益率口徑（V4／#52）", () => {
  it("畫面上寫明收益率怎麼算的——最差成交價", () => {
    list([row()]);
    const note = screen.getByText(/最差成交價/);
    expect(note).toHaveTextContent(/買腿 Ask/);
    expect(note).toHaveTextContent(/賣腿 Bid/);
  });
});

describe("資料新鮮度提示（V4／#52）", () => {
  it("久未刷新的卡片標出來，不讓舊數字看起來像現在的", () => {
    list([row({ latest_analyzed_at: "2026-08-01T09:30:00+00:00" })]);
    expect(screen.getByText("舊資料")).toBeInTheDocument();
  });

  it("剛刷新過的卡片沒有提示", () => {
    list([row({ latest_analyzed_at: "2026-08-04T09:30:00+00:00" })]);
    expect(screen.queryByText("舊資料")).not.toBeInTheDocument();
  });

  it("尚未分析不標「舊資料」——卡片已經說了尚未分析", () => {
    list([row({ latest_analyzed_at: null, best_return: null })]);
    expect(screen.queryByText("舊資料")).not.toBeInTheDocument();
  });
});

describe("刷新失敗的分層與重試入口（V4／#52）", () => {
  it("抓不到報價時說是哪一段失敗，並附後端給的原因", () => {
    list([row()], {
      failures: { a: { stage: "fetch", message: "抓不到 TLT 的報價：來源無回應" } },
    });

    const card = screen.getByRole("listitem");
    expect(within(card).getByText(/抓不到報價/)).toBeInTheDocument();
    expect(within(card).getByText(/來源無回應/)).toBeInTheDocument();
  });

  it("分析失敗與抓不到報價講的不是同一句話", () => {
    list([row()], {
      failures: { a: { stage: "analyze", message: "分析失敗：boom" } },
    });
    expect(screen.getByText(/分析沒跑完/)).toBeInTheDocument();
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
  });

  it("重試按鈕只重試那一個劇本", async () => {
    const onRetry = vi.fn();
    list([row({ id: "a", symbol: "AAA" }), row({ id: "b", symbol: "BBB" })], {
      failures: { b: { stage: "fetch", message: "抓不到" } },
      onRetry,
    });

    await userEvent.click(screen.getByRole("button", { name: "重試 BBB 2028-05" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledWith("b");
  });

  it("沒失敗的卡片不長出重試按鈕", () => {
    list([row()]);
    expect(screen.queryByRole("button", { name: /重試/ })).not.toBeInTheDocument();
  });

  it("刷新失敗時卡片仍顯示上一次的數字，並標成舊資料", () => {
    list([row({ latest_analyzed_at: "2026-08-01T09:30:00+00:00" })], {
      failures: { a: { stage: "fetch", message: "抓不到" } },
    });

    // 失敗不該讓已經算出來的東西消失——那是使用者目前唯一有的資訊，
    // 只要旁邊誠實標明它是舊的。
    expect(screen.getByText("123.4%")).toBeInTheDocument();
    expect(screen.getByText("舊資料")).toBeInTheDocument();
  });
});
