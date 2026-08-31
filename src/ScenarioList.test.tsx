import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ScenarioList from "./ScenarioList";
import sampleRow from "../contracts/scenario_row_sample.json";
import type { RefreshFailure, ScenarioSummary } from "./api";
import { formatAnalyzedAt } from "./scenarios";

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
    <ScenarioList
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

describe("劇本清單", () => {
  it("卡片含標的／目標價／目標年月／收益率／距到期天數", () => {
    list([row()]);

    expect(screen.getByText("TLT")).toBeInTheDocument();
    // 目標價與目標年月同在一列；`2028-05` 另外也出現在只給輔助技術讀的
    // 那段字裡，所以連著價格一起比對，鎖定的是畫面上那一列。
    expect(screen.getByText(/\$120\.00.*2028-05/)).toBeInTheDocument();
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
      .map((li) => li.querySelector(".compact-symbol")!.textContent);
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

describe("決策 K（#108）：桌面卡片瘦身後七項決策資訊一項不少", () => {
  it("卡片 DOM 同時含 Ticker／目標價＋目標年月／代表報酬／策略履約／" +
     "到期日／燈號／最後更新，只是不再各自佔一整列", () => {
    const r = row({
      symbol: "TLT", target_price: 120, target_month: "2028-05",
      best_return: 1.234,
      representative_candidate: {
        strategy: "bull-call-spread",
        legs: [{ strike: 118, option_type: "call", side: "buy" },
              { strike: 122, option_type: "call", side: "sell" }],
        expiry: "2026-09-18", baseline_return: 1.234,
      },
      latest_analyzed_at: "2026-08-04T09:30:00+00:00",
    });
    list([r]);
    const card = screen.getByRole("listitem");

    // 1. Ticker
    expect(within(card).getByText("TLT")).toBeInTheDocument();
    // 2. 目標價＋目標年月（同一列）
    expect(within(card).getByText(/\$120\.00.*2028-05/)).toBeInTheDocument();
    // 3. 代表報酬
    expect(within(card).getByText("123.4%")).toBeInTheDocument();
    // 4. 策略／買賣履約價
    expect(within(card).getByText(/Bull Call Spread/)).toBeInTheDocument();
    expect(within(card).getByText(/買 118 \/ 賣 122/)).toBeInTheDocument();
    // 5. 實際到期日
    expect(within(card).getByText(/2026-09-18/)).toBeInTheDocument();
    // 6. 燈號（顏色不是唯一管道，但圓點本身要在）
    expect(card.querySelector(".signal-dot")).toBeTruthy();
    // 7. 最後更新（資料時間）——直接拿純函式算預期字串，不在測試裡
    //    另外硬編一個跟時區綁死的字串。`toLocaleString` 在日期與時間
    //    之間塞的是 U+2009 THIN SPACE 不是普通空白，Testing Library
    //    只會正規化「畫面上找到的文字」、不會動我這邊算出來的比對字串
    //    ——兩邊都手動正規化過空白字元再比，才不會被這種看起來一樣、
    //    位元組不同的空白坑到。
    const normalizeSpace = (s: string) => s.trim().replace(/\s+/g, " ");
    const expectedAnalyzedAt = normalizeSpace(
      formatAnalyzedAt(r.latest_analyzed_at!));
    expect(within(card).getByText((text) =>
      normalizeSpace(text) === expectedAnalyzedAt)).toBeInTheDocument();
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

  it("點卡片是切換選取，不是導向詳細頁", async () => {
    const onToggleSelect = vi.fn();
    list([row({ id: "a", symbol: "AAA" })],
         { selectMode: true, onToggleSelect });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(onToggleSelect).toHaveBeenCalledWith("a");
  });

  it("已選 0 個時「移入垃圾桶」鈕停用，避免誤送空批次", () => {
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

describe("代表候選（MVP-v2／#77、#78）", () => {
  it("價差候選顯示策略名稱、買賣履約價與實際到期日", () => {
    list([row({
      representative_candidate: {
        strategy: "bull-call-spread",
        legs: [{ strike: 118, option_type: "call", side: "buy" },
              { strike: 122, option_type: "call", side: "sell" }],
        expiry: "2026-09-18", baseline_return: 1.234,
      },
    })]);

    expect(screen.getByText(/Bull Call Spread/)).toBeInTheDocument();
    expect(screen.getByText(/買 118 \/ 賣 122/)).toBeInTheDocument();
    // 決策 K（#108）：到期日併進第三層合併行，跟「Exp」字首同一個
    // text node，不再是獨立的「2026-09-18」，改用 regex 找子字串。
    expect(screen.getByText(/2026-09-18/)).toBeInTheDocument();
  });

  it("單腳候選只顯示一隻買腿，不憑空生出賣腿", () => {
    list([row({
      representative_candidate: {
        strategy: "long-call",
        legs: [{ strike: 118, option_type: "call", side: "buy" }],
        expiry: "2026-09-18", baseline_return: 0.29,
      },
    })]);

    const card = screen.getByRole("listitem");
    expect(within(card).getByText(/Long Call/)).toBeInTheDocument();
    expect(within(card).getByText(/買 118/)).toBeInTheDocument();
    // 卡片下方另有一句全站通用的口徑說明（含「賣腿 Bid」字樣），
    // 因此只在這張卡片範圍內斷言沒有賣腿，不對整個畫面找「賣」。
    expect(within(card).queryByText(/賣/)).not.toBeInTheDocument();
  });

  it("尚未分析（代表候選為 null）時策略與到期日都顯示「—」，不是假的候選", () => {
    list([row({ best_return: null, latest_analyzed_at: null,
                representative_candidate: null })]);

    // 「—」在這張卡上會出現不只一次（收益率、策略皆是），用
    // getAllByText 確認至少出現，不要求恰好一次；到期日的「—」跟
    // 「Exp」字首黏在同一個 text node 裡（決策 K／#108 第三層合併行），
    // 另外用 regex 單獨驗證同一句話。
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/^Exp —$/)).toBeInTheDocument();
  });

  it("卡片同時渲染報酬率與代表候選的履約價，兩者出自同一筆 API 回應", () => {
    // 後端已保證 best_return 與 representative_candidate.baseline_return
    // 逐位相同（M1a／#78 的口徑恆等測試）；這裡驗證前端元件把兩者一起
    // 畫出來，不會為了顯示其中一個而遺漏另一個。
    list([row({
      best_return: 3.33,
      representative_candidate: {
        strategy: "bull-call-spread",
        legs: [{ strike: 100, option_type: "call", side: "buy" },
              { strike: 105, option_type: "call", side: "sell" }],
        expiry: "2026-09-18", baseline_return: 3.33,
      },
    })]);

    expect(screen.getByText("333.0%")).toBeInTheDocument();
    expect(screen.getByText(/買 100 \/ 賣 105/)).toBeInTheDocument();
  });
});

describe("劇本級燈號（MVP-v2／#77、#80）", () => {
  it("正常劇本是綠燈", () => {
    list([row({ expired: false })]);
    expect(screen.getByTitle("狀態：正常")).toBeInTheDocument();
    expect(document.querySelector(".signal-dot.signal-green")).toBeTruthy();
  });

  it("目標月已過完是紅燈，即使同時帶著刷新失敗紀錄", () => {
    list([row({ id: "a", expired: true })], {
      failures: { a: { stage: "fetch", message: "抓不到" } },
    });
    expect(screen.getByTitle("狀態：已過期")).toBeInTheDocument();
    expect(document.querySelector(".signal-dot.signal-red")).toBeTruthy();
    expect(document.querySelector(".signal-dot.signal-yellow")).toBeFalsy();
  });

  it("本次刷新失敗且未過期是黃燈", () => {
    list([row({ id: "a", expired: false })], {
      failures: { a: { stage: "fetch", message: "抓不到" } },
    });
    expect(screen.getByTitle("狀態：刷新失敗")).toBeInTheDocument();
    expect(document.querySelector(".signal-dot.signal-yellow")).toBeTruthy();
  });

  it("每張卡片只有一個燈號圓點", () => {
    list([row({ id: "a", expired: true })], {
      failures: { a: { stage: "fetch", message: "抓不到" } },
    });
    expect(document.querySelectorAll(".signal-dot").length).toBe(1);
  });

  it("紅燈的劇本沉到清單最後，即使報酬率最高", () => {
    list([
      row({ id: "a", symbol: "AAA", best_return: 9.9, expired: true }),
      row({ id: "b", symbol: "BBB", best_return: 0.1, expired: false }),
    ]);
    const symbols = screen.getAllByRole("listitem")
      .map((li) => li.querySelector(".compact-symbol")!.textContent);
    expect(symbols).toEqual(["BBB", "AAA"]);
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

describe("過期劇本不再刷新（#68）", () => {
  it("目標月已過的劇本標出來，且與「舊資料」不是同一句話", () => {
    list([row({ expired: true })]);
    expect(screen.getByText("已過期，不再刷新")).toBeInTheDocument();
  });

  it("目標月還沒過的劇本沒有這個標記", () => {
    list([row({ expired: false })]);
    expect(screen.queryByText("已過期，不再刷新")).not.toBeInTheDocument();
  });

  it("已過期的劇本即使帶著舊的失敗紀錄，也不顯示刷新失敗與重試——" +
     "兩種狀態同時出現會讓使用者搞不清楚現在是哪一種", () => {
    list([row({ id: "a", expired: true })], {
      failures: { a: { stage: "fetch", message: "抓不到報價" } },
    });

    expect(screen.getByText("已過期，不再刷新")).toBeInTheDocument();
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重試/ })).not.toBeInTheDocument();
  });

  it("既有分析結果照常顯示，過期只是不再刷新，不是把資料藏起來", () => {
    list([row({ expired: true, best_return: 1.234 })]);
    expect(screen.getByText("123.4%")).toBeInTheDocument();
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

describe("更新中徽章＋鎖定（T08／#196 P1 首次引入；PC-05／#202 恢復反灰＋" +
        "不可點入）", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("更新中的卡片標「更新中」、反灰，但仍顯示上一輪的舊資料（徽章與資料" +
     "本身不受這張票影響）", () => {
    const { container } = list([row({ id: "a", best_return: 2.5 })],
                               { updatingIds: new Set(["a"]) });

    expect(screen.getByText("更新中")).toBeInTheDocument();
    expect(container.querySelector(".compact-card.locked")).toBeInTheDocument();
    // 上一輪的舊數字仍顯示，不會因為更新中就消失或變成「—」：
    expect(screen.getByText("250.0%")).toBeInTheDocument();
  });

  it("PC-05（#202）：點更新中的卡片不會導向詳細頁——href 仍在（連結" +
     "語意保留：長按可複製、螢幕閱讀器認得），但點擊被攔截", async () => {
    window.location.hash = "";
    list([row({ id: "a", symbol: "AAA" })], { updatingIds: new Set(["a"]) });

    const link = screen.getByRole("link", { name: /AAA/ });
    expect(link).toHaveAttribute("href", "#/s/a");
    await userEvent.click(link);

    expect(window.location.hash).toBe("");
  });

  it("不是更新中的卡片點下去正常導向詳細頁（對照組：證明上一條測試真的" +
     "是攔截生效，不是 jsdom 本來就不會跳轉）", async () => {
    window.location.hash = "";
    list([row({ id: "a", symbol: "AAA" })], { updatingIds: new Set() });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(window.location.hash).toBe("#/s/a");
  });

  it("不是更新中的卡片顯示一般燈號，不是「更新中」，也不帶 locked class", () => {
    const { container } = list([row({ id: "a" })], { updatingIds: new Set() });
    expect(screen.queryByText("更新中")).not.toBeInTheDocument();
    expect(container.querySelector(".locked")).not.toBeInTheDocument();
  });

  it("更新中的劇本用它上一輪的舊收益率正常參與排序，不獨立排到後面", () => {
    list([
      row({ id: "a", symbol: "AAA", best_return: 0.5 }),
      row({ id: "b", symbol: "BBB", best_return: 9.0 }),
    ], { updatingIds: new Set(["b"]) });

    const symbols = screen.getAllByRole("listitem")
      .map((li) => li.querySelector(".compact-symbol")!.textContent);
    expect(symbols).toEqual(["BBB", "AAA"]);
  });

  it("批次選取模式下，更新中的卡片一樣點得到 checkbox 切換選取——既有" +
     "批次選取互動不受這張票影響", async () => {
    const onToggleSelect = vi.fn();
    list([row({ id: "a", symbol: "AAA" })], {
      updatingIds: new Set(["a"]), selectMode: true, onToggleSelect,
    });

    await userEvent.click(screen.getByRole("link", { name: /AAA/ }));

    expect(onToggleSelect).toHaveBeenCalledWith("a");
  });
});

describe("劇本庫的概覽欄位（QA 修正，桌面版與手機版同一套語意）", () => {
  it("現價跟目標價並排，最高／最低有填就顯示", () => {
    list([row({ spot: 82.11, best_price: 120, worst_price: 100 })]);
    const card = screen.getByRole("listitem");
    expect(card.querySelector(".compact-spot")!.textContent).toBe("$82.11");
    const range = card.querySelector(".compact-range")!;
    expect(range.textContent).toContain("最低 $100.00");
    expect(range.textContent).toContain("最高 $120.00");
  });

  it("兩端都沒填就整行不畫", () => {
    list([row({ best_price: null, worst_price: null })]);
    expect(screen.getByRole("listitem").querySelector(".compact-range"))
      .toBeNull();
  });
});
