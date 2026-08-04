import { describe, expect, it } from "vitest";

import sample from "../contracts/analysis_sample.json";
import { baselineTopCandidate, type AnalysisView, type Candidate } from "./api";
import { catchupContractLabel, catchupView, formatMove, strategyLabel } from "./detail";

const view = sample as unknown as AnalysisView;
const real = baselineTopCandidate(view)!;

function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return { ...real, ...overrides };
}

describe("策略名稱", () => {
  it("用標準術語，不自創譯名", () => {
    expect(strategyLabel("bull-call-spread")).toBe("Bull Call Spread");
  });

  it("認不得的代號原樣顯示，不留白也不假裝", () => {
    expect(strategyLabel("something-new")).toBe("something-new");
  });
});

describe("漲幅格式", () => {
  it("帶正負號", () => {
    expect(formatMove(0.3)).toBe("+30.0%");
    expect(formatMove(-0.125)).toBe("-12.5%");
  });
});

describe("比較對象的寫法（v3 #9 指定格式）", () => {
  it("到期年月＋履約價＋Long Call", () => {
    expect(catchupContractLabel({ strike: 110, option_type: "call",
                            expiry: "2028-01-21", bid: 1, ask: 1.2 }))
      .toBe("28/1 110 Long Call");
  });

  it("半檔履約價保留小數，整數不拖著 .0", () => {
    expect(catchupContractLabel({ strike: 122.5, option_type: "call",
                            expiry: "2026-08-07", bid: 1, ask: 1.2 }))
      .toBe("26/8 122.5 Long Call");
  });
});

describe("追平價格三態", () => {
  it("正常：說出比較對象、追平價格、離目標多遠", () => {
    const v = catchupView(candidate({ catchup_price: 130 }), 120)!;
    expect(v.contract).toMatch(/Long Call$/);
    expect(v.price).toBe("$130.00");
    expect(v.gap).toBe("超出目標價 8.3%");
    expect(v.beatsTarget).toBe(false);
  });

  it("醒目：S* 低於目標價＝Long Call 在本劇本內就贏了", () => {
    const v = catchupView(candidate({ catchup_price: 110 }), 120)!;
    expect(v.beatsTarget).toBe(true);
    expect(v.gap).toBe("低於目標價 8.3%");
  });

  it("S* 正好等於目標價也算贏——追平就是追平，不是差一點", () => {
    expect(catchupView(candidate({ catchup_price: 120 }), 120)!.beatsTarget).toBe(true);
  });

  it("無法計算：同履約價 Call 報價缺失時不拋錯，比較對象照樣說得出來", () => {
    const v = catchupView(candidate({ catchup_price: null }), 120)!;
    expect(v.price).toBeNull();
    expect(v.gap).toBeNull();
    expect(v.contract).toMatch(/Long Call$/);
    expect(v.beatsTarget).toBe(false);
  });

  it("單腳候選整塊不顯示——跟 Long Call 比較就是跟自己比", () => {
    expect(catchupView(candidate({ legs: [real.legs[0]] }), 120)).toBeNull();
    expect(catchupView(candidate({ legs: [] }), 120)).toBeNull();
  });
});
