import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

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
      legs: [{ strike: 118, option_type: "call", side: "buy", quantity: 1 },
            { strike: 122, option_type: "call", side: "sell", quantity: 1 }],
      expiry: "2026-09-18", baseline_return: 1.234,
    },
    ...overrides,
  };
}

function list(
  rows: ScenarioSummary[],
  props: {
    failures?: Record<string, RefreshFailure>;
    updatingIds?: ReadonlySet<string>;
    onArchive?: (id: string) => void;
    onEdit?: (id: string) => void;
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
      updatingIds={props.updatingIds ?? new Set()}
      onArchive={props.onArchive ?? vi.fn()}
      onEdit={props.onEdit ?? vi.fn()}
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
      // QA 修正：現價擠進同一行的目標價前面（`現價 → 目標`）。
      expect(card.querySelector(".compact-target")!.textContent)
        .toBe("$100.00 → $120.00　2028-05");
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

  // OPTION-CHASER-CLOSEOUT-001／002：手機版 compact row 與桌面版共用
  // 同一份 `formatRepresentativeSummary()`，這裡鏡射
  // ScenarioList.test.tsx 的同一條回歸——Butterfly champion 卡片顯示
  // 緊湊格式「Butterfly 106 / 109 / 112」，不換行不撐高卡片；詳細頁
  // 才顯示完整買賣履約價與口數（見 `detail.test.ts`）。
  it("Butterfly champion 卡片上顯示緊湊格式「Butterfly 106 / 109 / 112」，不換行不撐高卡片", () => {
    list([row({
      best_return: 5.67,
      representative_candidate: {
        strategy: "call-fly",
        legs: [
          { strike: 106, option_type: "call", side: "buy", quantity: 1 },
          { strike: 109, option_type: "call", side: "sell", quantity: 2 },
          { strike: 112, option_type: "call", side: "buy", quantity: 1 },
        ],
        expiry: "2026-09-18", baseline_return: 5.67,
      },
    })]);
    const card = screen.getByRole("listitem");
    expect(within(card).getByText("Butterfly 106 / 109 / 112")).toBeInTheDocument();
    expect(within(card).queryByText(/Call Butterfly/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/買|賣|2×/)).not.toBeInTheDocument();
  });

  it("Single-leg champion 維持完整格式不變（OPTION-CHASER-CLOSEOUT-002）", () => {
    list([row({
      best_return: 0.82,
      representative_candidate: {
        strategy: "long-call",
        legs: [{ strike: 100, option_type: "call", side: "buy", quantity: 1 }],
        expiry: "2026-09-18", baseline_return: 0.82,
      },
    })]);
    const card = screen.getByRole("listitem");
    expect(within(card).getByText(/Long Call/)).toBeInTheDocument();
    expect(within(card).getByText(/買 100/)).toBeInTheDocument();
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

describe("更新中徽章＋鎖定（T08／#196 P1 首次引入；PC-05／#202 恢復反灰＋" +
        "不可點入）", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("更新中的列項標「更新中」、反灰，但仍顯示上一輪的舊資料", () => {
    const { container } = list([row({ id: "a", best_return: 2.5 })],
                               { updatingIds: new Set(["a"]) });

    expect(screen.getByText("更新中")).toBeInTheDocument();
    expect(container.querySelector(".compact-card.locked")).toBeInTheDocument();
    expect(screen.getByText("250.0%")).toBeInTheDocument();
  });

  it("PC-05（#202）：點更新中的列項不會導向詳細頁——href 仍在，但點擊" +
     "被攔截", async () => {
    window.location.hash = "";
    list([row({ id: "a", symbol: "AAA" })], { updatingIds: new Set(["a"]) });

    const link = screen.getByRole("link", { name: /AAA/ });
    expect(link).toHaveAttribute("href", "#/s/a");
    await userEvent.click(link);

    expect(window.location.hash).toBe("");
  });

  it("不是更新中的列項點下去正常導向詳細頁（對照組）", async () => {
    window.location.hash = "";
    list([row({ id: "a", symbol: "AAA" })], { updatingIds: new Set() });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(window.location.hash).toBe("#/s/a");
  });

  it("不是更新中的列項顯示一般燈號，不是「更新中」，也不帶 locked class", () => {
    const { container } = list([row({ id: "a" })], { updatingIds: new Set() });
    expect(screen.queryByText("更新中")).not.toBeInTheDocument();
    expect(container.querySelector(".locked")).not.toBeInTheDocument();
  });

  it("批次選取模式下，更新中的列項一樣點得到 checkbox 切換選取", async () => {
    const onToggleSelect = vi.fn();
    list([row({ id: "a", symbol: "AAA" })], {
      updatingIds: new Set(["a"]), selectMode: true, onToggleSelect,
    });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(onToggleSelect).toHaveBeenCalledWith("a");
  });
});

describe("刷新失敗卡片兩態（OD-03／#242，REPAIR-05）", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("A：曾經至少成功分析過——卡片反灰、頭條說明是舊結果、仍可點入" +
     "詳細頁、保留重試", async () => {
    window.location.hash = "";
    const { container } = list(
      [row({ id: "a", symbol: "AAA", best_return: 1.5 })],
      { failures: { a: { stage: "fetch", message: "抓不到 AAA 的報價" } } },
    );

    expect(container.querySelector(".compact-card.failed")).toBeInTheDocument();
    // 更新中那個 `.locked` 不該同時出現——updating 與 failure 是兩個
    // 獨立 state，這裡壓根沒有 updating。
    expect(container.querySelector(".compact-card.locked")).not.toBeInTheDocument();
    expect(screen.getByText("更新失敗，目前顯示上一次成功結果"))
      .toBeInTheDocument();
    expect(screen.getByText(/抓不到 AAA 的報價/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重試/ })).toBeInTheDocument();

    // 仍是完全可點的連結——舊結果本身還在，點進去看得到。
    const link = screen.getByRole("link", { name: /AAA/ });
    expect(link).toHaveAttribute("href", "#/s/a");
    await userEvent.click(link);
    expect(window.location.hash).toBe("#/s/a");
  });

  it("B：從未成功分析過——卡片反灰、頭條說明尚無可用結果、仍可點入" +
     "詳細頁（落到既有「尚未分析」空狀態）、保留重試", async () => {
    window.location.hash = "";
    const { container } = list(
      [row({ id: "a", symbol: "AAA", best_return: null,
            latest_analyzed_at: null, representative_candidate: null })],
      { failures: { a: { stage: "fetch", message: "抓不到 AAA 的報價" } } },
    );

    expect(container.querySelector(".compact-card.failed")).toBeInTheDocument();
    expect(screen.getByText("尚無可用分析結果")).toBeInTheDocument();
    expect(screen.getByText(/抓不到 AAA 的報價/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重試/ })).toBeInTheDocument();

    // 沒有既有結果可看，但連結沒有被停用——落到詳細頁既有的「尚未
    // 分析」空狀態（`ScenarioDetail.tsx`），不是死路。
    const link = screen.getByRole("link", { name: /AAA/ });
    expect(link).toHaveAttribute("href", "#/s/a");
    await userEvent.click(link);
    expect(window.location.hash).toBe("#/s/a");
  });

  it("更新中時即使留著舊的失敗紀錄，也不顯示失敗兩態——這次嘗試還沒有" +
     "結論", () => {
    const { container } = list(
      [row({ id: "a", symbol: "AAA", best_return: 1.5 })],
      {
        failures: { a: { stage: "fetch", message: "抓不到 AAA 的報價" } },
        updatingIds: new Set(["a"]),
      },
    );

    expect(container.querySelector(".compact-card.failed")).not.toBeInTheDocument();
    expect(screen.queryByText("更新失敗，目前顯示上一次成功結果"))
      .not.toBeInTheDocument();
    expect(screen.queryByText(/抓不到 AAA 的報價/)).not.toBeInTheDocument();
    expect(screen.getByText("更新中")).toBeInTheDocument();
  });

  it("已過期時不顯示失敗兩態——沿用 #68 紅燈優先於黃燈", () => {
    const { container } = list(
      [row({ id: "a", symbol: "AAA", expired: true })],
      { failures: { a: { stage: "fetch", message: "抓不到 AAA 的報價" } } },
    );

    expect(container.querySelector(".compact-card.failed")).not.toBeInTheDocument();
    expect(screen.queryByText(/抓不到 AAA 的報價/)).not.toBeInTheDocument();
  });
});

describe("劇本庫的概覽欄位（QA 修正）", () => {
  it("現價跟目標價並排——卡片上要有比較基準，不然一排目標價沒有意義", () => {
    list([row({ spot: 82.11 })]);
    const card = screen.getByRole("listitem");
    expect(card.querySelector(".compact-spot")!.textContent).toBe("$82.11");
  });

  it("還沒分析過（沒有現價）顯示破折號，不是 0", () => {
    list([row({ spot: null, latest_analyzed_at: null, best_return: null,
                representative_candidate: null })]);
    const card = screen.getByRole("listitem");
    expect(card.querySelector(".compact-spot")!.textContent).toBe("—");
  });

  it("有填最高／最低就顯示出來", () => {
    list([row({ spot: 82.11, best_price: 120, worst_price: 100 })]);
    const card = screen.getByRole("listitem");
    const range = card.querySelector(".compact-range")!;
    expect(range.textContent).toContain("最低 $100.00");
    expect(range.textContent).toContain("最高 $120.00");
  });

  it("只填一端時另一端顯示破折號，那一行仍然出現", () => {
    list([row({ best_price: 120, worst_price: null })]);
    const range = screen.getByRole("listitem").querySelector(".compact-range")!;
    expect(range.textContent).toContain("最高 $120.00");
    expect(range.textContent).toContain("最低 —");
  });

  it("兩端都沒填就整行不畫——compact row 的密度不該被空資料吃掉", () => {
    list([row({ best_price: null, worst_price: null })]);
    expect(screen.getByRole("listitem").querySelector(".compact-range"))
      .toBeNull();
  });
});
