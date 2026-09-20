/**
 * 桌面詳細頁三欄外殼（OG-06／#321）：`DesktopDetailBody` 元件測試。
 * 只測這個元件自己的職責——family tabs／到期日 chip／排名表／中央
 * Heatmap 跟著選取——不重覆測 `FamilyTabs.tsx`／`ExpiryStructure.tsx`
 * 既有的手機版行為（那兩份測試檔已經覆蓋，本檔零改動它們）。
 */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DesktopDetailBody from "./DesktopDetail";
import { candidate, result, view } from "./family.fixtures";
import type { Candidate } from "./api";

// OG-07（#325）：`DesktopDetailBody` 現在常駐掛載底部「淨成本走勢」
// tab（`DesktopSpreadHistory`），一掛載就打 `getSpreadHistory()`——
// 跟 `SpreadHistory.test.tsx` 同一套做法直接 stub 全域 `fetch`，不是
// 讓測試環境真的打一次網路（jsdom 沒有真的伺服器可打，行為不可預期）。
// 這個檔案原本零筆測試需要 mock 任何東西，OG-06 落地時 `CandidatePool`／
// `AnalysisReport` 都是純 prop 渲染，這是本票唯一新增的 side effect。
function mockFetch(body: unknown = { entries: [] }) {
  const spy = vi.fn(async () => ({ ok: true, status: 200, json: async () => body }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => {
  mockFetch();
});

/** 掛載後讓 `DesktopSpreadHistory` 的 `getSpreadHistory()` 這次 mock
 *  fetch 有機會 resolve 完——不然它在測試本體結束後才 resolve，state
 *  更新落在 `act()` 邊界外，React 會噴 `not wrapped in act` 警告
 *  （不影響斷言結果，但吵）。這個檔案本身不斷言走勢圖 tab 的內容
 *  （那是 `DesktopSpreadHistory.test.tsx` 的職責），這裡只是把它排乾淨。 */
async function flush() {
  await act(async () => {});
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 排名表本身——這個元件同時渲染 `CandidatePool`／`AnalysisReport`
 *  （見 `DesktopDetail.tsx` 檔頭：暫時維持原位不消失），兩者對同一組
 *  候選會顯示同一個報酬率文字，`screen.getByRole("button", ...)` 若
 *  不縮小範圍會連帶命中那邊、變成「找到多個」的假失敗——排名列查詢
 *  一律先縮小到這個容器。 */
function rankingList() {
  return within(document.querySelector(".detail-rank-list") as HTMLElement);
}

/** 給候選一組單一格的 Heatmap 矩陣，格值不同即可從畫面上的數字分辨出
 *  中央 Heatmap 現在顯示的是哪一組候選——不需要真的模擬完整報酬矩陣，
 *  `formatCell()` 只是把比例轉成整數百分比文字（`heatmap.test.ts`
 *  既有覆蓋），這裡借用同一個轉換當「這是候選 A 還是候選 B」的指紋。 */
function withMatrix(c: Candidate, cellValue: number): Candidate {
  return {
    ...c,
    matrix: {
      prices: [[100, "100", 0]],
      dates: [["2026-09-18", "9/18"]],
      cells: [[cellValue]],
    },
  };
}

describe("DesktopDetailBody：單一 family（OG-06／#321）", () => {
  it("單一 family 時不畫策略家族分頁——跟 FamilyTabs.tsx 同一條 AC", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    expect(screen.queryByRole("group", { name: "策略家族" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "到期日" })).toBeInTheDocument();
  });

  it("排名表顯示名次、subtype 標籤、腿位 pill、劇本報酬", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const row = rankingList().getByRole("button", { name: /Long Call/ });
    expect(within(row).getByText("#1")).toBeInTheDocument();
    expect(within(row).getByText("20.0%")).toBeInTheDocument();
  });

  it("Bid/Ask 過寬與單調性警示 tag 沿用手機版同一套 title 文案", async () => {
    const cand = withMatrix(
      { ...candidate("k1", "long-call", 0.2), wide_spread_warning: true,
        monotonicity_warning: true },
      0.1,
    );
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    // OG-07（#325）起，右欄「進場」tab 預設顯示、也重複這兩句警示文案
    // （票面 AC 明文要求）——跟排名列同一份判準、不同容器，這裡照
    // 這個檔案自己的既有慣例（`rankingList()`）縮小到排名列本身，
    // 避免「找到多個」的假失敗。
    expect(rankingList().getByTitle("Bid/Ask 過寬")).toBeInTheDocument();
    expect(rankingList().getByTitle("報價與鄰近履約價不一致，疑似陳舊報價"))
      .toBeInTheDocument();
  });

  it("中央 Heatmap 預設顯示這組唯一候選（不用先展開）", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.42);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    expect(screen.getByText("42")).toBeInTheDocument();
  });
});

describe("DesktopDetailBody：排名表選取跟中央 Heatmap（OG-06／#321 核心行為）", () => {
  it("預設選取該到期日第 1 名——這裡恰好就是冠軍，中央 Heatmap 顯示它", async () => {
    const champ = withMatrix(candidate("k1", "long-call", 0.5), 0.5);
    const second = withMatrix(candidate("k2", "long-call", 0.3), 0.3);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1", "k2"] })],
      { k1: champ, k2: second },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={champ}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.queryByText("30")).not.toBeInTheDocument();
    expect(rankingList().getByRole("button", { name: /50\.0%/ })).toHaveAttribute(
      "aria-pressed", "true");
  });

  it("點第 2 名那一列：中央 Heatmap 換成它，第 1 名不再是選取狀態" +
     "——不觸發任何額外資料請求（純 state 切換既有記憶體裡的候選）", async () => {
    const champ = withMatrix(candidate("k1", "long-call", 0.5), 0.5);
    const second = withMatrix(candidate("k2", "long-call", 0.3), 0.3);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1", "k2"] })],
      { k1: champ, k2: second },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={champ}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    await userEvent.click(rankingList().getByRole("button", { name: /30\.0%/ }));

    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.queryByText("50")).not.toBeInTheDocument();
    expect(rankingList().getByRole("button", { name: /30\.0%/ })).toHaveAttribute(
      "aria-pressed", "true");
    expect(rankingList().getByRole("button", { name: /50\.0%/ })).toHaveAttribute(
      "aria-pressed", "false");
  });
});

describe("DesktopDetailBody：多 family（OG-06／#321，T11／#229 既有裁示延伸）", () => {
  it("預設打開冠軍所屬 family，切換分頁只換排名表內容", async () => {
    const champ = withMatrix(candidate("v1", "bull-call-spread", 0.4), 0.4);
    const singleLeg = withMatrix(candidate("s1", "long-call", 0.1), 0.1);
    const v = view(
      [
        result("bull-call-spread", "ok", { "2026-09-18": ["v1"] }),
        result("long-call", "ok", { "2026-09-18": ["s1"] }),
      ],
      { v1: champ, s1: singleLeg },
    );
    render(<DesktopDetailBody view={v}
                              strategies={["single-leg", "vertical-spread"]}
                              champion={champ}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const tabs = screen.getByRole("group", { name: "策略家族" });
    expect(within(tabs).getByRole("button", { name: "Vertical Spread" }))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("40")).toBeInTheDocument();

    await userEvent.click(within(tabs).getByRole("button", { name: "Call / Put" }));

    expect(within(tabs).getByRole("button", { name: "Call / Put" }))
      .toHaveAttribute("aria-pressed", "true");
    // 切走冠軍所屬分頁後，中央 Heatmap 跟著換成目前分頁自己的第 1 名
    // ——不是繼續顯示冠軍（冠軍固定顯示在 `ScenarioDetail.tsx` 的
    // `Summary`，不是這裡）。
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.queryByText("40")).not.toBeInTheDocument();
  });

  it("不可選的 family 一樣有分頁、點得進去看得到原因（facts-only）", async () => {
    const champ = withMatrix(candidate("v1", "bull-call-spread", 0.4), 0.4);
    const v = view(
      [result("bull-call-spread", "ok", { "2026-09-18": ["v1"] })],
      { v1: champ },
      { familyEligibility: {
        "single-leg": { family: "single-leg", eligible: false,
                       reason: "這個策略家族目前無法分析。" },
      } },
    );
    render(<DesktopDetailBody view={v}
                              strategies={["single-leg", "vertical-spread"]}
                              champion={champ}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    await userEvent.click(
      screen.getByRole("button", { name: "Call / Put" }));

    expect(screen.getByText("這個策略家族目前無法分析。")).toBeInTheDocument();
  });
});

describe("DesktopDetailBody：右欄候選面板（OG-07／#325）", () => {
  it("預設「進場」tab，顯示逐腿最差成交價表與淨成本", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    expect(rightPanel.getByRole("tab", { name: "進場" })).toHaveAttribute(
      "aria-selected", "true");
    const costRow = rightPanel.getByText("淨成本 / 股").closest(".row") as HTMLElement;
    expect(within(costRow).getByText("$1.00")).toBeInTheDocument();
  });

  it("「報告」tab 精簡摘要仍顯示免責聲明（`/code-review` Spec 軸跟進：" +
     "檔頭原本只有註解，實際沒接資料）", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const okResult = { ...result("long-call", "ok", { "2026-09-18": ["k1"] }),
                       disclaimer_text: "測試免責聲明文字" };
    const v = view([okResult], { k1: cand });
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await userEvent.click(rightPanel.getByRole("tab", { name: "報告" }));

    expect(rightPanel.getByText("測試免責聲明文字")).toBeInTheDocument();
  });

  it("CSV 下載連結常駐在右欄，不分四個 tab 切到哪一個（票面「報告」bullet" +
     "明文、artifact 畫成頁尾常駐按鈕）", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt="2026-09-18T00:00:00Z" />);
    await flush();

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    const link = rightPanel.getByRole("link", { name: "下載原始資料 CSV" });
    expect(link).toHaveAttribute("href",
      "/api/scenarios/s1/raw-data.csv?t=2026-09-18T00%3A00%3A00Z");

    await userEvent.click(rightPanel.getByRole("tab", { name: "Greeks" }));
    expect(rightPanel.getByRole("link", { name: "下載原始資料 CSV" })).toBeInTheDocument();
  });

  it("切換右欄 tab 不觸發任何額外請求（純同步換內容）", async () => {
    const spy = mockFetch();
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();
    const before = spy.mock.calls.length;

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await userEvent.click(rightPanel.getByRole("tab", { name: "Payoff" }));
    await userEvent.click(rightPanel.getByRole("tab", { name: "Greeks" }));
    await userEvent.click(rightPanel.getByRole("tab", { name: "報告" }));

    expect(spy.mock.calls.length).toBe(before);
    expect(rightPanel.getByText(/完整的 Risk \/ Payoff/)).toBeInTheDocument();
  });

  it("右欄跟著排名表選取列切換——不是固定顯示第 1 名", async () => {
    const champ = withMatrix(candidate("k1", "long-call", 0.5), 0.5);
    const second = { ...withMatrix(candidate("k2", "long-call", 0.3), 0.3),
                     natural_cost: 9.99 };
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1", "k2"] })],
      { k1: champ, k2: second },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={champ}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    await userEvent.click(rankingList().getByRole("button", { name: /30\.0%/ }));

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    expect(rightPanel.getByText("$9.99")).toBeInTheDocument();
  });

  it("完成度門檻（單調 family）與獲利區間（Butterfly）互斥呈現", async () => {
    const monotonic = withMatrix(
      { ...candidate("k1", "long-call", 0.2), completion_threshold: 0.4 }, 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: monotonic },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={monotonic}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await userEvent.click(rightPanel.getByRole("tab", { name: "Payoff" }));

    expect(rightPanel.getByText("完成度門檻")).toBeInTheDocument();
    expect(rightPanel.getByText("完成 40%（保本）")).toBeInTheDocument();
    expect(rightPanel.queryByText("獲利區間")).not.toBeInTheDocument();
  });

  it("Butterfly 不顯示完成度門檻——就算 completion_threshold 剛好非 null", async () => {
    const fly = withMatrix(
      { ...candidate("k1", "call-fly", 0.2), completion_threshold: 0.4,
        profit_region: [90, 110] }, 0.1);
    const v = view(
      [result("call-fly", "ok", { "2026-09-18": ["k1"] })],
      { k1: fly },
    );
    render(<DesktopDetailBody view={v} strategies={["butterfly"]} champion={fly}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const rightPanel = within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await userEvent.click(rightPanel.getByRole("tab", { name: "Payoff" }));

    expect(rightPanel.queryByText("完成度門檻")).not.toBeInTheDocument();
    expect(rightPanel.getByText("獲利區間")).toBeInTheDocument();
  });
});

describe("DesktopDetailBody：底部四個 tab（OG-07／#325）", () => {
  it("預設「淨成本走勢」，其餘三個 tab 內容常駐掛載但 hidden", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const bottom = document.querySelector(".detail-bottom-tabs") as HTMLElement;
    const panels = within(bottom);
    expect(panels.getByRole("tab", { name: "淨成本走勢" })).toHaveAttribute(
      "aria-selected", "true");
    // 候選池診斷這個時候已經在 DOM 裡（常駐掛載），只是 hidden。
    const poolHeading = panels.getByText("候選池");
    expect(poolHeading.closest("[hidden]")).not.toBeNull();
  });

  it("切到候選池診斷 tab：內容從 hidden 變成可見，分析報告只有這一份", async () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);
    await flush();

    const bottom = document.querySelector(".detail-bottom-tabs") as HTMLElement;
    const panels = within(bottom);
    await userEvent.click(panels.getByRole("tab", { name: "候選池診斷" }));
    expect(panels.getByText("候選池").closest("[hidden]")).toBeNull();

    // AC：「分析報告在同一頁只完整渲染一份」——不論目前在哪個底部
    // tab，DOM 裡永遠只有一個 `📄 分析報告`（右欄「報告」tab 只放
    // 精簡摘要，不是第二份完整元件）。
    expect(screen.getAllByText("📄 分析報告")).toHaveLength(1);
  });
});
