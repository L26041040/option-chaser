import { describe, expect, it } from "vitest";

import { costAndMaxLoss, perShareText, perContractText, SHARES_PER_CONTRACT } from "./contractUnits";

describe("每股／每口（V2-06／#408）：1 口 = 100 股，只換單位、不重算", () => {
  it("1 口 = 100 股", () => {
    expect(SHARES_PER_CONTRACT).toBe(100);
  });

  it("成本：每股取 entry_cost，每口 = 每股 × 100", () => {
    const u = costAndMaxLoss({ entry_cost: 0.81, max_loss_per_contract: 81 });
    expect(u.cost.perShare).toBe(0.81);
    expect(u.cost.perContract).toBeCloseTo(81, 10);
    expect(perShareText(u.cost.perShare)).toBe("$0.81 / 股");
    expect(perContractText(u.cost.perContract)).toBe("$81.00 / 口");
  });

  it("最大損失：每口直接取 max_loss_per_contract，每股 = 每口 ÷ 100", () => {
    // broken-wing Butterfly：最大損失（每口 $120）不等於成本 × 100（$50）——
    // 最大損失不從成本推，照後端每口原值。
    const u = costAndMaxLoss({ entry_cost: 0.5, max_loss_per_contract: 120 });
    expect(u.maxLoss.perContract).toBe(120);
    expect(u.maxLoss.perShare).toBeCloseTo(1.2, 10);
    expect(perShareText(u.maxLoss.perShare)).toBe("$1.20 / 股");
    expect(perContractText(u.maxLoss.perContract)).toBe("$120.00 / 口");
    expect(perContractText(u.cost.perContract)).toBe("$50.00 / 口");
  });

  it("樣本列（Long Call）：成本 $5.60 / 股 → $560.00 / 口；最大損失 $560.00 / 口 → $5.60 / 股", () => {
    const u = costAndMaxLoss({ entry_cost: 5.6, max_loss_per_contract: 560 });
    expect(perShareText(u.cost.perShare)).toBe("$5.60 / 股");
    expect(perContractText(u.cost.perContract)).toBe("$560.00 / 口");
    expect(perShareText(u.maxLoss.perShare)).toBe("$5.60 / 股");
    expect(perContractText(u.maxLoss.perContract)).toBe("$560.00 / 口");
  });
});
