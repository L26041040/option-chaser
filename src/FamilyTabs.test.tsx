/**
 * T11（#229，Initial V2）：Strategy Family 分頁——每個啟用的 family
 * 各一個分頁，內部維持既有依到期日分組的結構；不可選／零候選的 family
 * 顯示原因；單一 family 時完全不畫分頁列（AC 明文：不出現多餘 UI）。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import FamilyTabs from "./FamilyTabs";
import type { AnalysisView, Candidate, FamilyEligibility, StrategyResult } from "./api";

function candidate(key: string, strategy: string, ret: number): Candidate {
  return {
    candidate_key: key,
    strategy,
    baseline_return: ret,
    natural_cost: 1,
    mid_cost: 1,
    breakeven: 100,
    breakeven_points: [100],
    days_to_expiry: 30,
    max_profit: null,
    max_loss_per_contract: 100,
    net_delta: 0.5,
    effective_leverage: 1,
    theta_day_rate: 0,
    rate_used: 0.04,
    rate_tenor_years: 0.1,
    vega_per_pt: 0,
    scenario_vector: { entries: [], worst_code: "flat", worst_return: 0 },
    completion_curve: [],
    completion_threshold: null,
    retention: 0,
    l2: 0,
    l3: 0,
    cons: [],
    guidance_warnings: [],
    catchup_price: null,
    wide_spread_warning: false,
    monotonicity_warning: false,
    legs: [{ strike: 100, option_type: "call", expiry: "2026-09-18",
            ask: 1, bid: 1, iv: 0.2, volume: 1, open_interest: 1,
            side: "buy", quantity: 1 }],
    matrix: { prices: [], dates: [], cells: [] },
    comparator: null,
  };
}

function result(
  strategy: string,
  status: "ok" | "skipped_direction" | "empty",
  perExpiry: Record<string, string[]> = {},
  message = "",
): StrategyResult {
  return {
    strategy,
    status,
    message: message || (status === "ok" ? "" : `${strategy} 沒有產生結果`),
    n_qualified: Object.values(perExpiry).flat().length,
    filter_report: null,
    filter_stages: [],
    quality_flags: [],
    pair_report: null,
    expiry_counts: Object.entries(perExpiry).map(
      ([expiry, keys]) => [expiry, keys.length] as [string, number]),
    expiry_top10: Object.entries(perExpiry).map(
      ([expiry, keys]) => ({ expiry, candidate_keys: keys })),
    disclaimer_text: "",
  };
}

function view(
  results: StrategyResult[],
  pool: Record<string, Candidate>,
  familyEligibility: Record<string, FamilyEligibility> = {},
): AnalysisView {
  return {
    meta: { symbol: "XYZ", spot: 100, fetched_at: "", source: "cboe",
            target_move: 0 },
    params: { target_price: 110, target_month: "2026-09",
              strategy: results[0]?.strategy ?? "long-call",
              best_price: null, worst_price: null, rate: 0.04, rate_note: "",
              rate_curve_used: false, rate_curve_date: null,
              rate_curve_stale: false, rate_explicit: false,
              q_by_symbol: null, q_source: null, q_as_of: null,
              q_stale: false, q_note: "", iv_shifts: [],
              delta_bands: [0.35, 0.65], min_return: 0 },
    baseline_expiry: "2026-09-18",
    results,
    candidate_pool: pool,
    family_eligibility: familyEligibility,
  };
}

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
      {
        "single-leg": { family: "single-leg", eligible: true, reason: null },
        "vertical-spread": { family: "vertical-spread", eligible: true, reason: null },
        "butterfly": { family: "butterfly", eligible: false,
                       reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
      },
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
      { "single-leg": { family: "single-leg", eligible: true, reason: null } },
    );
    render(<FamilyTabs view={v} strategies={["single-leg"]} />);
    expect(screen.getByText("目前沒有符合流動性與報價條件的合約。"))
      .toBeInTheDocument();
  });

  it("方向不合被跳過時，顯示閘門給的訊息", () => {
    const v = view(
      [result("long-call", "skipped_direction", {}, "目前劇本方向為「看跌」，因此未執行 Long Call。")],
      {},
      { "single-leg": { family: "single-leg", eligible: false,
                        reason: "旗下 subtype 都不適用目前這個方向。" } },
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
    const v = view([], {}, {
      "butterfly": { family: "butterfly", eligible: false,
                     reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
    });
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
