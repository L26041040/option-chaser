/**
 * 桌面詳細頁三欄外殼（OG-06／#321）：`DesktopDetailBody` 元件測試。
 * 只測這個元件自己的職責——family tabs／到期日 chip／排名表／中央
 * Heatmap 跟著選取——不重覆測 `FamilyTabs.tsx`／`ExpiryStructure.tsx`
 * 既有的手機版行為（那兩份測試檔已經覆蓋，本檔零改動它們）。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import DesktopDetailBody from "./DesktopDetail";
import { candidate, result, view } from "./family.fixtures";
import type { Candidate } from "./api";

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
  it("單一 family 時不畫策略家族分頁——跟 FamilyTabs.tsx 同一條 AC", () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand} />);

    expect(screen.queryByRole("group", { name: "策略家族" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "到期日" })).toBeInTheDocument();
  });

  it("排名表顯示名次、subtype 標籤、腿位 pill、劇本報酬", () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.1);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand} />);

    const row = rankingList().getByRole("button", { name: /Long Call/ });
    expect(within(row).getByText("#1")).toBeInTheDocument();
    expect(within(row).getByText("20.0%")).toBeInTheDocument();
  });

  it("Bid/Ask 過寬與單調性警示 tag 沿用手機版同一套 title 文案", () => {
    const cand = withMatrix(
      { ...candidate("k1", "long-call", 0.2), wide_spread_warning: true,
        monotonicity_warning: true },
      0.1,
    );
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand} />);

    expect(screen.getByTitle("Bid/Ask 過寬")).toBeInTheDocument();
    expect(screen.getByTitle("報價與鄰近履約價不一致，疑似陳舊報價")).toBeInTheDocument();
  });

  it("中央 Heatmap 預設顯示這組唯一候選（不用先展開）", () => {
    const cand = withMatrix(candidate("k1", "long-call", 0.2), 0.42);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1"] })],
      { k1: cand },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={cand} />);

    expect(screen.getByText("42")).toBeInTheDocument();
  });
});

describe("DesktopDetailBody：排名表選取跟中央 Heatmap（OG-06／#321 核心行為）", () => {
  it("預設選取該到期日第 1 名——這裡恰好就是冠軍，中央 Heatmap 顯示它", () => {
    const champ = withMatrix(candidate("k1", "long-call", 0.5), 0.5);
    const second = withMatrix(candidate("k2", "long-call", 0.3), 0.3);
    const v = view(
      [result("long-call", "ok", { "2026-09-18": ["k1", "k2"] })],
      { k1: champ, k2: second },
    );
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={champ} />);

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
    render(<DesktopDetailBody view={v} strategies={["single-leg"]} champion={champ} />);

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
                              champion={champ} />);

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
                              champion={champ} />);

    await userEvent.click(
      screen.getByRole("button", { name: "Call / Put" }));

    expect(screen.getByText("這個策略家族目前無法分析。")).toBeInTheDocument();
  });
});
