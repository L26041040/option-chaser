import { describe, expect, it } from "vitest";

import sample from "../contracts/analysis_sample.json";
import { baselineTopCandidate, type AnalysisView, type Candidate } from "./api";
import { breakevenDistancePct, catchupContractLabel, catchupView,
        completionThresholdText, costPctOfSpot, formatMove, maxPayoutRatioText,
        reportConclusion, strategyLabel } from "./detail";

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
                            expiry: "2028-01-21", bid: 1, ask: 1.2, iv: 0.3 }))
      .toBe("28/1 110 Long Call");
  });

  it("半檔履約價保留小數，整數不拖著 .0", () => {
    expect(catchupContractLabel({ strike: 122.5, option_type: "call",
                            expiry: "2026-08-07", bid: 1, ask: 1.2, iv: 0.3 }))
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

describe("分析報告①交易摘要的一句話結論（V8／#56，spec R1 §2.3）", () => {
  it("單腳：買 + 到期 + 履約 + 結構名稱 + 成本 → 損益兩平 → 最大獲利（無上限）", () => {
    const c = candidate({
      legs: [{ strike: 120, option_type: "call", expiry: "2026-08-21",
              bid: 5.0, ask: 5.2, iv: 0.3 }],
      natural_cost: 5.2, breakeven: 125.2, max_profit: null,
    });
    expect(reportConclusion(c, "long-call")).toBe(
      "買 120 2026-08-21 到期 Long Call，成本 $5.20 → 損益兩平 $125.20 → 最大獲利 無上限");
  });

  it("價差：買/賣兩腿 + 到期 + 結構名稱 + 成本 → 損益兩平 → 最大獲利（有上限）", () => {
    const c = candidate({
      legs: [
        { strike: 100, option_type: "call", expiry: "2026-08-21", bid: 6.0, ask: 6.2, iv: 0.3 },
        { strike: 120, option_type: "call", expiry: "2026-08-21", bid: 0.9, ask: 1.0, iv: 0.25 },
      ],
      natural_cost: 5.2, breakeven: 105.2, max_profit: 14.8,
    });
    expect(reportConclusion(c, "bull-call-spread")).toBe(
      "買 100 / 賣 120 2026-08-21 到期 Bull Call Spread，" +
      "成本 $5.20 → 損益兩平 $105.20 → 最大獲利 $14.80");
  });
});

describe("max payout ratio（V8／#56，spec R1 §2.3 GS 慣例）", () => {
  it("有上限：最大獲利／成本，一位小數＋x", () => {
    const c = candidate({ natural_cost: 5.2, max_profit: 14.8 });
    expect(maxPayoutRatioText(c)).toBe("2.8x");
  });

  it("Long Call 無上限：顯示「無上限」，不是硬湊一個假倍數", () => {
    const c = candidate({ natural_cost: 5.2, max_profit: null });
    expect(maxPayoutRatioText(c)).toBe("無上限");
  });
});

describe("成本佔現價／損益兩平距現價（V8／#56，spec R1 §3.2）", () => {
  it("成本佔現價：純除法，恆正", () => {
    const c = candidate({ natural_cost: 5.2 });
    expect(costPctOfSpot(c, 100)).toBeCloseTo(0.052, 6);
  });

  it("損益兩平距現價：帶正負號——高於現價為正、低於為負", () => {
    const above = candidate({ breakeven: 125.2 });
    expect(breakevenDistancePct(above, 100)).toBeCloseTo(0.252, 6);
    const below = candidate({ breakeven: 75.0 });
    expect(breakevenDistancePct(below, 100)).toBeCloseTo(-0.25, 6);
  });
});

describe("保本門檻三態（V8／#56，對照 report.py 既有邏輯）", () => {
  it("null：劇本全成仍不保本", () => {
    expect(completionThresholdText(null)).toBe("劇本全成仍不保本");
  });

  it("<=0：已保本，不顯示負的完成度", () => {
    expect(completionThresholdText(0)).toBe("0%（已保本）");
    expect(completionThresholdText(-0.05)).toBe("0%（已保本）");
  });

  it("正值：完成 X% 才保本", () => {
    expect(completionThresholdText(0.437)).toBe("完成 43.7%");
  });
});
