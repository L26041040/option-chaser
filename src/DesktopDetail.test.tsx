/**
 * 桌面詳細頁三欄外殼（OG-06／#321）：`DesktopDetailBody` 元件測試。
 * 只測這個元件自己的職責——family tabs／到期日 chip／排名表／中央
 * Heatmap 跟著選取——不重覆測 `FamilyTabs.tsx`／`ExpiryStructure.tsx`
 * 既有的手機版行為（那兩份測試檔已經覆蓋，本檔零改動它們）。
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BANNED_JARGON } from "./bannedCopy";
import DesktopDetailBody from "./DesktopDetail";
import { candidate, result, view } from "./family.fixtures";
import type { Candidate } from "./api";
import type { Role } from "./superuser";

// OG-07（#325）：`DesktopDetailBody` 曾經常駐掛載底部「淨成本走勢」
// tab（`DesktopSpreadHistory`），一掛載就打 `getSpreadHistory()`——
// 當時直接 stub 全域 `fetch`，不是讓測試環境真的打一次網路（jsdom
// 沒有真的伺服器可打，行為不可預期）。SW-12（#342）：該 tab 隨 Spread
// 淨成本走勢功能整個退休移除，但這裡的全域 `fetch` stub 保留——
// `showIvPanel` 分支掛載的 `<IvHistory>` 仍可能觸發網路呼叫，拿掉
// stub 有殘留風險，不因為原始理由消失就順手一併移除。
function mockFetch(body: unknown = { entries: [] }) {
  const spy = vi.fn(async () => ({ ok: true, status: 200, json: async () => body }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => {
  mockFetch();
});

/** 讓掛載後任何非同步 state 更新（含尚未確認是否還存在的 fetch 副
 *  作用）有機會在測試本體結束前 resolve 完——不然它在測試本體結束後
 *  才 resolve，state 更新落在 `act()` 邊界外，React 會噴 `not wrapped
 *  in act` 警告（不影響斷言結果，但吵）。 */
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
/** 兩腿候選——`family.fixtures.ts::candidate()` 預設只給 1 隻腿（那份
 *  fixture 本來就不在乎 `legs.length`，服務的是排名表／Heatmap 這些
 *  跟腿數無關的既有測試），OG-08 起「這個候選是不是單腿」變成右欄要
 *  問的真問題，因此這裡另外覆寫一份 2 腿版本，不能沿用預設值假裝是
 *  Vertical Spread。 */
function twoLegged(c: Candidate): Candidate {
  return {
    ...c,
    legs: [
      { strike: 100, option_type: "call", expiry: "2026-09-18",
       ask: 1, bid: 1, iv: 0.2, volume: 1, open_interest: 1,
       side: "buy", quantity: 1 },
      { strike: 106, option_type: "call", expiry: "2026-09-18",
       ask: 1, bid: 1, iv: 0.2, volume: 1, open_interest: 1,
       side: "sell", quantity: 1 },
    ],
  };
}

/** OG-08（#326）：右欄「這次要畫哪一種面板」問的是 `useIvHistoryAccess()`
 *  ——跟 `IvHistory.test.tsx::mockApi()` 同一套路由風格，`/iv-history`
 *  本身故意回傳一個永遠不 resolve 的 promise：這裡只關心「掛的是
 *  `<IvHistory>` 還是 `<CandidatePanel>`」這個外層決定，不需要真的把
 *  完整資料餵給 `IvHistoryContent`（那是 `IvHistory.test.tsx` 自己的
 *  職責），停在 `CardSkeleton` 狀態就足夠斷言。 */
function routeIvAccess({ enabled, role }: { enabled: boolean; role: Role }) {
  const spy = vi.fn(async (url: string) => {
    if (url.startsWith("/api/auth/status")) {
      return { ok: true, status: 200, json: async () => ({ role }) };
    }
    if (url.startsWith("/api/settings")) {
      return { ok: true, status: 200,
               json: async () => ({ historical_iv_enabled: enabled }) };
    }
    if (url.includes("iv-history")) {
      return new Promise(() => {}); // 故意不 resolve，停在 skeleton
    }
    return { ok: true, status: 200, json: async () => ({ entries: [] }) };
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

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

  it("SW-12（#342，Owner 真機驗收）：Bid/Ask 過寬與單調性旗標即使皆為真，⚠／🚩" +
     "徽章在排名列與右欄「進場」tab 都完全不顯示——不是 SW-10／#340 那種" +
     "「移到進場 tab」，是整個退出使用者 UI；底層兩個欄位與 eligibility 計算" +
     "不受影響", async () => {
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

    expect(rankingList().queryByTitle("Bid/Ask 過寬")).not.toBeInTheDocument();
    expect(rankingList().queryByTitle("報價與鄰近履約價不一致，疑似陳舊報價"))
      .not.toBeInTheDocument();
    // OG-07（#325）起右欄「進場」tab 預設顯示、選取這一列即可見——這裡
    // 曾經是徽章唯一還看得到的地方（SW-10／#340），SW-12 起也不畫了。
    expect(screen.queryByTitle("Bid/Ask 過寬")).not.toBeInTheDocument();
    expect(screen.queryByTitle("報價與鄰近履約價不一致，疑似陳舊報價"))
      .not.toBeInTheDocument();
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

describe("DesktopDetailBody：底部三個 tab（OG-07／#325；SW-12／#342 起" +
        "原第四個「淨成本走勢」tab 隨該功能整個退休移除）", () => {
  it("預設「候選策略」，其餘兩個 tab 內容常駐掛載但 hidden", async () => {
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
    // SW-05（#337）文案去術語：底部 tab 名稱與 `CandidatePool.tsx`
    // 共用元件自己的標題（SW-06／#335 已改）現在是同一句「候選策略」，
    // 不再是兩個獨立字串。
    expect(panels.getByRole("tab", { name: "候選策略" })).toHaveAttribute(
      "aria-selected", "true");
    const poolHeading = panels.getByText("候選策略", { selector: "h2" });
    expect(poolHeading.closest("[hidden]")).toBeNull();
    // 「分析報告」這個時候已經在 DOM 裡（常駐掛載），只是 hidden。
    const reportTab = panels.getByRole("tab", { name: "分析報告" });
    expect(reportTab).toHaveAttribute("aria-selected", "false");
  });

  it("切到候選策略 tab：內容從 hidden 變成可見，分析報告只有這一份", async () => {
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
    await userEvent.click(panels.getByRole("tab", { name: "候選策略" }));
    expect(panels.getByText("候選策略", { selector: "h2" }).closest("[hidden]")).toBeNull();

    // AC：「分析報告在同一頁只完整渲染一份」——不論目前在哪個底部
    // tab，DOM 裡永遠只有一個 `📄 分析報告`（右欄「報告」tab 只放
    // 精簡摘要，不是第二份完整元件）。
    expect(screen.getAllByText("📄 分析報告")).toHaveLength(1);
  });
});

describe("DesktopDetailBody：右欄 Historical IV 面板（OG-08／#326）", () => {
  it("角色 ≥ Super User 且已解鎖且選取列是單腿候選：右欄整個換成 " +
     "<IvHistory>，不再是 <CandidatePanel>（進場／Payoff／Greeks／" +
     "報告那組 tab 消失）", async () => {
    routeIvAccess({ enabled: true, role: "superuser" });
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);

    const rightPanel = () => within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await waitFor(() => expect(
      rightPanel().getByRole("heading", { name: "IV 相對位置" })).toBeInTheDocument());
    expect(rightPanel().queryByRole("tab", { name: "進場" })).not.toBeInTheDocument();
  });

  it("Normal User：即使選取列是單腿候選，右欄仍是既有 <CandidatePanel>，" +
     "不打 iv-history 請求（自我閘門，跟 IvHistory.tsx 同一套規則）", async () => {
    const spy = routeIvAccess({ enabled: true, role: "normal" });
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);

    const rightPanel = () => within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await waitFor(() => expect(
      rightPanel().getByRole("tab", { name: "進場" })).toBeInTheDocument());
    expect(rightPanel().queryByRole("heading", { name: "IV 相對位置" }))
      .not.toBeInTheDocument();
    expect(spy.mock.calls.map((c) => c[0]).some((u: string) => u.includes("iv-history")))
      .toBe(false);
  });

  it("角色達標且已解鎖，但選取列是兩腿以上候選（Vertical／Butterfly）：" +
     "右欄仍是既有 <CandidatePanel>——既有退場裁示延伸到右欄面板選擇", async () => {
    routeIvAccess({ enabled: true, role: "superuser" });
    const cand = twoLegged(withMatrix(candidate("v1", "bull-call-spread", 0.4), 0.4));
    const v = view(
      [result("bull-call-spread", "ok", { "2026-09-18": ["v1"] })],
      { v1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["vertical-spread"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);

    const rightPanel = () => within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await waitFor(() => expect(
      rightPanel().getByRole("tab", { name: "進場" })).toBeInTheDocument());
    expect(rightPanel().queryByRole("heading", { name: "IV 相對位置" }))
      .not.toBeInTheDocument();
  });

  it("Historical IV 未解鎖（`historical_iv_enabled: false`）：即使角色達標" +
     "且候選單腿，右欄仍是既有 <CandidatePanel>", async () => {
    routeIvAccess({ enabled: false, role: "superuser" });
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand}
                              scenarioId="s1" analyzedAt={null} />);

    const rightPanel = () => within(
      document.querySelector(".detail-col-right") as HTMLElement);
    await waitFor(() => expect(
      rightPanel().getByRole("tab", { name: "進場" })).toBeInTheDocument());
    expect(rightPanel().queryByRole("heading", { name: "IV 相對位置" }))
      .not.toBeInTheDocument();
  });

  it("跟著排名表選取列切換，不是固定看冠軍：多 family 劇本切到單腿分頁" +
     "才出現 <IvHistory>，冠軍是 Vertical 時預設分頁仍是 <CandidatePanel>",
   async () => {
    routeIvAccess({ enabled: true, role: "superuser" });
    const champ = twoLegged(withMatrix(candidate("v1", "bull-call-spread", 0.4), 0.4));
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

    // 預設分頁＝冠軍所屬的 Vertical Spread（2 腿）——右欄仍是
    // `CandidatePanel`，等這件事先穩定下來，避免 `useIvHistoryAccess()`
    // 兩道非同步閘門還沒解完就搶著斷言造成偽陰性。
    await waitFor(() => expect(
      screen.getByRole("tab", { name: "進場" })).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "IV 相對位置" }))
      .not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Call / Put" }));

    await waitFor(() => expect(
      screen.getByRole("heading", { name: "IV 相對位置" })).toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: "進場" })).not.toBeInTheDocument();
  });
});

describe("DesktopDetailBody：文案去術語（SW-09／#339 全站掃描）", () => {
  it("多 family＋底部候選策略常駐掛載時，全頁文字不含開發者詞彙", async () => {
    const champ = withMatrix(candidate("v1", "bull-call-spread", 0.4), 0.4);
    const singleLeg = withMatrix(candidate("s1", "long-call", 0.1), 0.1);
    const v = view(
      [
        result("bull-call-spread", "ok", { "2026-09-18": ["v1"] }),
        result("long-call", "ok", { "2026-09-18": ["s1"] }),
      ],
      { v1: champ, s1: singleLeg },
    );
    const { container } = render(
      <DesktopDetailBody view={v} strategies={["single-leg", "vertical-spread"]}
                          champion={champ} scenarioId="s1" analyzedAt={null} />);
    await flush();

    const text = container.textContent ?? "";
    for (const banned of BANNED_JARGON) {
      expect(text).not.toContain(banned);
    }
  });
});
