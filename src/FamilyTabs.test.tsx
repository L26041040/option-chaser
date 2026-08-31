/**
 * T11（#229，Initial V2）：Strategy Family 分頁——每個啟用的 family
 * 各一個分頁，內部維持既有依到期日分組的結構；不可選／零候選的 family
 * 顯示原因；單一 family 時完全不畫分頁列（AC 明文：不出現多餘 UI）。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import FamilyTabs from "./FamilyTabs";
import { candidate, result, view } from "./family.fixtures";

describe("單一 family——不出現多餘 UI（AC 明文）", () => {
  it("沒有分頁列，直接顯示這個 family 的到期日結構與候選池", () => {
    const v = view(
      [result("bull-call-spread", "ok", { "2026-09-18": ["k1"] })],
      { k1: candidate("k1", "bull-call-spread", 0.5) },
    );
    render(<FamilyTabs view={v} strategies={["vertical-spread"]} />);

    expect(screen.queryByRole("group", { name: "策略家族" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "到期日" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "候選池" })).toBeInTheDocument();
  });
});

describe("多 family——分頁切換", () => {
  function multiView() {
    return view(
      [
        result("long-call", "ok", { "2026-09-18": ["lc"] }),
        result("bull-call-spread", "ok", { "2026-09-18": ["bc"] }),
      ],
      {
        lc: candidate("lc", "long-call", 0.3),
        bc: candidate("bc", "bull-call-spread", 0.9),
      },
      { familyEligibility: {
        "single-leg": { family: "single-leg", eligible: true, reason: null },
        "vertical-spread": { family: "vertical-spread", eligible: true, reason: null },
        "butterfly": { family: "butterfly", eligible: false,
                       reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
      } },
    );
  }

  it("每個啟用的 family 各一顆分頁按鈕", () => {
    render(<FamilyTabs view={multiView()} strategies={["single-leg", "vertical-spread"]} />);
    const tabs = screen.getByRole("group", { name: "策略家族" });
    expect(within(tabs).getAllByRole("button")).toHaveLength(2);
    expect(within(tabs).getByText("Call / Put")).toBeInTheDocument();
    expect(within(tabs).getByText("Vertical Spread")).toBeInTheDocument();
  });

  it("預設打開冠軍所屬 family（本例冠軍是 bull-call-spread，報酬較高）", () => {
    render(<FamilyTabs view={multiView()} strategies={["single-leg", "vertical-spread"]} />);
    const tabs = screen.getByRole("group", { name: "策略家族" });
    expect(within(tabs).getByRole("button", { name: "Vertical Spread" }))
      .toHaveAttribute("aria-pressed", "true");
    // 冠軍 family 的內容已經在畫面上——候選池顯示這個 family 的資料。
    expect(screen.getByRole("heading", { name: "到期日" })).toBeInTheDocument();
  });

  it("T16（#232）：冠軍是 Butterfly 時預設打開 Butterfly 分頁——"
     + "`family.ts::SUBTYPE_FAMILY` 若漏掉 call-fly／put-fly 這裡會退回"
     + "第一個 family 而不是冠軍所屬的那個", () => {
    const v = view(
      [
        result("long-call", "ok", { "2026-09-18": ["lc"] }),
        result("call-fly", "ok", { "2026-09-18": ["cf"] }),
      ],
      {
        lc: candidate("lc", "long-call", 0.3),
        cf: candidate("cf", "call-fly", 0.9),
      },
      { familyEligibility: {
        "single-leg": { family: "single-leg", eligible: true, reason: null },
        "butterfly": { family: "butterfly", eligible: true, reason: null },
      } },
    );
    render(<FamilyTabs view={v} strategies={["single-leg", "butterfly"]} />);
    const tabs = screen.getByRole("group", { name: "策略家族" });
    expect(within(tabs).getByRole("button", { name: "Butterfly" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("切到另一個分頁只換排名內容，不是整頁重載", async () => {
    render(<FamilyTabs view={multiView()} strategies={["single-leg", "vertical-spread"]} />);
    await userEvent.click(screen.getByRole("button", { name: "Call / Put" }));

    expect(screen.getByRole("button", { name: "Call / Put" }))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Vertical Spread" }))
      .toHaveAttribute("aria-pressed", "false");
    // 換成 single-leg 自己的候選（買 100，長格式標題）
    expect(screen.getByText(/買 100/)).toBeInTheDocument();
  });

  it("不可選的 family 也有分頁，點進去顯示原因（facts-only，不是隱藏或反灰）", async () => {
    render(<FamilyTabs view={multiView()} strategies={["single-leg", "vertical-spread", "butterfly"]} />);
    await userEvent.click(screen.getByRole("button", { name: "Butterfly" }));

    expect(screen.getByText("這個策略家族目前還沒有任何已啟用的具體結構。"))
      .toBeInTheDocument();
    // 不可選分頁不渲染排名內容
    expect(screen.queryByRole("heading", { name: "候選池" })).not.toBeInTheDocument();
  });
});

describe("family 有結果條目但這次零候選——顯示既有的訊息，不是 eligibility 原因", () => {
  it("方向合適但過濾器砍光了（status=empty），顯示該筆結果自己的 message", () => {
    const v = view(
      [result("long-call", "empty", {}, "目前沒有符合流動性與報價條件的合約。")],
      {},
      { familyEligibility:
        { "single-leg": { family: "single-leg", eligible: true, reason: null } } },
    );
    render(<FamilyTabs view={v} strategies={["single-leg"]} />);
    expect(screen.getByText("目前沒有符合流動性與報價條件的合約。"))
      .toBeInTheDocument();
  });

  it("方向不合被跳過時，顯示閘門給的訊息", () => {
    const v = view(
      [result("long-call", "skipped_direction", {}, "目前劇本方向為「看跌」，因此未執行 Long Call。")],
      {},
      { familyEligibility:
        { "single-leg": { family: "single-leg", eligible: false,
                          reason: "旗下 subtype 都不適用目前這個方向。" } } },
    );
    render(<FamilyTabs view={v} strategies={["single-leg"]} />);
    // 優先取非 skipped_direction 的訊息；這裡只有一筆、且是 skipped，
    // 因此退回它自己的訊息——與既有 CandidatePool 單一策略時的行為一致。
    expect(screen.getByText("目前劇本方向為「看跌」，因此未執行 Long Call。"))
      .toBeInTheDocument();
  });
});

describe("family 完全沒有任何 subtype（今天只有 butterfly）", () => {
  it("顯示 eligibility 給的原因，不需要任何 StrategyResult 存在", () => {
    const v = view([], {}, { familyEligibility: {
      "butterfly": { family: "butterfly", eligible: false,
                     reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
    } });
    render(<FamilyTabs view={v} strategies={["butterfly"]} />);
    expect(screen.getByText("這個策略家族目前還沒有任何已啟用的具體結構。"))
      .toBeInTheDocument();
  });
});

describe("邊界", () => {
  it("`strategies` 為空、且 view.results 也沒東西時整塊不顯示", () => {
    const { container } = render(<FamilyTabs view={view([], {})} strategies={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
