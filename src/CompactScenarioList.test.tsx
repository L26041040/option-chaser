import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CompactScenarioList from "./CompactScenarioList";
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
    representative_candidate: {
      strategy: "bull-call-spread",
      legs: [{ strike: 118, option_type: "call" },
            { strike: 122, option_type: "call" }],
      expiry: "2026-09-18", baseline_return: 1.234,
    },
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
    selectMode?: boolean;
    selectedIds?: ReadonlySet<string>;
    onToggleSelect?: (id: string) => void;
    onEnterSelectMode?: () => void;
    onCancelSelectMode?: () => void;
    onConfirmBatchArchive?: () => void;
  } = {},
) {
  return render(
    <CompactScenarioList
      rows={rows}
      failures={props.failures ?? {}}
      onArchive={props.onArchive ?? vi.fn()}
      onRetry={props.onRetry ?? vi.fn()}
      now={props.now ?? NOW}
      selectMode={props.selectMode ?? false}
      selectedIds={props.selectedIds ?? new Set()}
      onToggleSelect={props.onToggleSelect ?? vi.fn()}
      onEnterSelectMode={props.onEnterSelectMode ?? vi.fn()}
      onCancelSelectMode={props.onCancelSelectMode ?? vi.fn()}
      onConfirmBatchArchive={props.onConfirmBatchArchive ?? vi.fn()}
    />,
  );
}

describe("Compact 劇本列（MVP-v2／#77、#82）", () => {
  it("三層都在：標的/目標/年月/燈號、報酬率/策略/履約價、到期日/距到期/更新時間",
    () => {
      list([row()]);
      const card = screen.getByRole("listitem");

      // 第一層。目標價／年月跟 sr-only 摘要都含「2028-05」字樣，用
      // class 鎖定畫面上那個節點，不靠文字比對消歧義。
      expect(within(card).getByText("TLT")).toBeInTheDocument();
      expect(card.querySelector(".compact-target")!.textContent)
        .toBe("$120.00　2028-05");
      expect(within(card).getByTitle("狀態：正常")).toBeInTheDocument();

      // 第二層
      expect(within(card).getByText("123.4%")).toBeInTheDocument();
      expect(within(card).getByText(/Bull Call Spread/)).toBeInTheDocument();
      expect(within(card).getByText(/買 118 \/ 賣 122/)).toBeInTheDocument();

      // 第三層
      expect(within(card).getByText(/Exp 2026-09-18/)).toBeInTheDocument();
      expect(within(card).getByText("653 天")).toBeInTheDocument();
      expect(within(card).getByText("8/4 05:30")).toBeInTheDocument();
    });

  it("代表候選為 null 時報酬率與策略欄都顯示「—」，不是編一組假的候選", () => {
    list([row({ best_return: null, latest_analyzed_at: null,
                representative_candidate: null })]);
    const card = screen.getByRole("listitem");
    // 報酬率與策略欄剛好都是「—」，兩處都要出現才算數。
    expect(within(card).getAllByText("—")).toHaveLength(2);
    expect(card.querySelector(".compact-strategy")!.textContent).toBe("—");
  });

  it("依收益率降序、紅燈沉底，沿用 scenarios.sortScenarios 同一套規則", () => {
    list([
      row({ id: "a", symbol: "AAA", best_return: 0.2 }),
      row({ id: "b", symbol: "BBB", best_return: 9.9, expired: true }),
      row({ id: "c", symbol: "CCC", best_return: 2.0 }),
    ]);
    const symbols = screen.getAllByRole("listitem")
      .map((li) => li.querySelector(".compact-symbol")!.textContent);
    expect(symbols).toEqual(["CCC", "AAA", "BBB"]);
  });

  it("距到期天數保留但併入第三層，不獨立成一列", () => {
    list([row({ days_to_anchor: -3 })]);
    const card = screen.getByRole("listitem");
    expect(within(card).getByText("已過期 3 天")).toBeInTheDocument();
    // 三層仍是三個區塊，不是四個——沒有第四個獨立的「距到期」區塊。
    expect(card.querySelectorAll(
      ".compact-tier1, .compact-tier2, .compact-tier3").length).toBe(3);
  });

  it("整列是真正的連結，可及名稱不被 aria-label 取代掉列上內容", () => {
    list([row()]);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "#/s/a");
    expect(link).not.toHaveAttribute("aria-label");
    // 可及名稱仍包含卡片上的關鍵資訊（symbol、報酬率），不是只有一句
    // 「查看詳細」——沿用 V5／#53 既有教訓。
    expect(link).toHaveAccessibleName(/TLT/);
    expect(link).toHaveAccessibleName(/123\.4%/);
  });

  it("封存鈕不巢狀在連結裡（互動元素不可巢狀互動元素），但仍可操作", async () => {
    const onArchive = vi.fn();
    list([row({ id: "a", symbol: "AAA" })], { onArchive });
    const card = screen.getByRole("listitem");
    const link = within(card).getByRole("link");
    const archiveButton = within(card).getByRole("button", { name: /封存/ });

    expect(link).not.toContainElement(archiveButton);
    await userEvent.click(archiveButton);
    expect(onArchive).toHaveBeenCalledWith("a");
  });

  it("刷新失敗顯示分層說明與重試入口，但過期劇本不重複顯示", () => {
    list([row({ id: "a", expired: false })], {
      failures: { a: { stage: "fetch", message: "抓不到 TLT 的報價" } },
    });
    expect(screen.getByText(/抓不到報價/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重試/ })).toBeInTheDocument();
  });

  it("已過期的劇本不顯示刷新失敗與重試", () => {
    list([row({ id: "a", expired: true })], {
      failures: { a: { stage: "fetch", message: "抓不到" } },
    });
    expect(screen.getByText("已過期，不再刷新")).toBeInTheDocument();
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重試/ })).not.toBeInTheDocument();
  });

  it("久未刷新標「舊資料」，跟燈號並存、不互相取代", () => {
    list([row({ latest_analyzed_at: "2026-08-01T09:30:00+00:00" })]);
    const card = screen.getByRole("listitem");
    expect(within(card).getByText("舊資料")).toBeInTheDocument();
    expect(within(card).getByTitle("狀態：正常")).toBeInTheDocument();
  });

  it("一個劇本都沒有時指引使用者往上面的新增入口，不是空白畫面", () => {
    list([]);
    expect(screen.getByText(/還沒有劇本/)).toBeInTheDocument();
    expect(screen.getByText(/新增劇本/)).toBeInTheDocument();
  });

  it("畫面上寫明收益率的口徑（V4／#52 既有裁示，compact 版沿用）", () => {
    list([row()]);
    const note = screen.getByText(/最差成交價/);
    expect(note).toHaveTextContent(/買腿 Ask/);
    expect(note).toHaveTextContent(/賣腿 Bid/);
  });
});

describe("批次選取移入垃圾桶（TR6／#91）", () => {
  it("一般狀態：垃圾桶批次選取入口在，封存鈕維持圖示可及名稱", () => {
    list([row()]);
    expect(screen.getByRole("button", { name: "選取要移入垃圾桶的劇本" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "封存 TLT 2028-05" }))
      .toBeInTheDocument();
  });

  it("選取模式：封存鈕不見了，換成 checkbox；批次操作列顯示已選數量",
     () => {
    list([row({ id: "a", symbol: "AAA" }), row({ id: "b", symbol: "BBB" })],
         { selectMode: true, selectedIds: new Set(["a"]) });

    expect(screen.queryByRole("button", { name: "封存 AAA 2028-05" }))
      .not.toBeInTheDocument();
    expect(screen.getByText("已選 1 個")).toBeInTheDocument();
  });

  it("點整列是切換選取，不是導向詳細頁", async () => {
    const onToggleSelect = vi.fn();
    list([row({ id: "a", symbol: "AAA" })],
         { selectMode: true, onToggleSelect });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(onToggleSelect).toHaveBeenCalledWith("a");
  });

  it("已選 0 個時「移入垃圾桶」鈕停用", () => {
    list([row()], { selectMode: true });
    expect(screen.getByRole("button", { name: "移入垃圾桶" })).toBeDisabled();
  });

  it("確認批次移入垃圾桶會呼叫回呼", async () => {
    const onConfirmBatchArchive = vi.fn();
    list([row({ id: "a" })],
         { selectMode: true, selectedIds: new Set(["a"]), onConfirmBatchArchive });

    await userEvent.click(screen.getByRole("button", { name: "移入垃圾桶" }));

    expect(onConfirmBatchArchive).toHaveBeenCalledTimes(1);
  });

  it("取消選取模式會呼叫回呼", async () => {
    const onCancelSelectMode = vi.fn();
    list([row()], { selectMode: true, onCancelSelectMode });

    await userEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(onCancelSelectMode).toHaveBeenCalledTimes(1);
  });
});
