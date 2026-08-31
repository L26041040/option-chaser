import { describe, expect, it } from "vitest";

import { candidateTitle, formatMove, strategyLabel } from "./detail";
import type { Candidate, Leg } from "./api";

function leg(overrides: Partial<Leg> = {}): Leg {
  return { strike: 118, option_type: "call", expiry: "2026-09-18",
          ask: 5, bid: 4.8, iv: 0.24, volume: 100, open_interest: 500,
          side: "buy", quantity: 1, ...overrides };
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

describe("候選標題（T12／#228：不再解構固定兩個變數）", () => {
  it("單腳只寫「買 X」", () => {
    const c = { legs: [leg({ strike: 118, side: "buy" })] } as unknown as Candidate;
    expect(candidateTitle(c)).toBe("買 118");
  });

  it("價差寫成「買 X / 賣 Y」，既有兩腿行為逐字不變", () => {
    const c = {
      legs: [leg({ strike: 118, side: "buy" }),
            leg({ strike: 122, side: "sell" })],
    } as unknown as Candidate;
    expect(candidateTitle(c)).toBe("買 118 / 賣 122");
  });

  it("三隻腿一隻都不丟——合成資料（Butterfly 產生器要等 T15）", () => {
    const c = {
      legs: [leg({ strike: 100, side: "buy" }),
            leg({ strike: 105, side: "sell" }),
            leg({ strike: 110, side: "buy" })],
    } as unknown as Candidate;
    expect(candidateTitle(c)).toBe("買 100 / 賣 105 / 買 110");
  });

  it("T16（#232）：口數 > 1 的腿標出倍數，中腿口數不再隱形", () => {
    const c = {
      legs: [leg({ strike: 100, side: "buy", quantity: 1 }),
            leg({ strike: 106, side: "sell", quantity: 2 }),
            leg({ strike: 115, side: "buy", quantity: 1 })],
    } as unknown as Candidate;
    expect(candidateTitle(c)).toBe("買 100 / 賣 2×106 / 買 115");
  });
});
