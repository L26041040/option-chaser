import { describe, expect, it } from "vitest";

import { formatMove, strategyLabel } from "./detail";

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
