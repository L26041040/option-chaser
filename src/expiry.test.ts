import { describe, expect, it } from "vitest";

import sample from "../contracts/analysis_sample.json";
import { primaryResult, resolveCandidate, type AnalysisView, type Candidate, type StrategyResult } from "./api";
import { expiryOptions, legPriceEntries, legPrices, resolveExpiry } from "./expiry";

const view = sample as unknown as AnalysisView;
const result = primaryResult(view)!;

describe("到期日選項", () => {
  it("每個到期日一個選項，順序照引擎給的", () => {
    const options = expiryOptions(view, result);
    expect(options.map((o) => o.expiry))
      .toEqual(result.expiry_top10!.map((g) => g.expiry));
  });

  it("按鈕上的最高收益＝該期清單的第 1 名，兩者不可能對不上", () => {
    for (const option of expiryOptions(view, result)) {
      expect(option.bestReturn).toBe(option.candidates[0].baseline_return);
    }
  });

  it("有效組數取自引擎的 expiry_counts", () => {
    const counts = new Map(result.expiry_counts);
    for (const option of expiryOptions(view, result)) {
      expect(option.count).toBe(counts.get(option.expiry));
    }
  });

  it("引擎沒給該期組數時是 null——「不知道」不等於「0 組」", () => {
    const patched = { ...result, expiry_counts: [] } as StrategyResult;
    expect(expiryOptions(view, patched)[0].count).toBeNull();
  });

  it("完全沒有分組時回空陣列，不是拋錯", () => {
    expect(expiryOptions(view, { ...result, expiry_top10: undefined })).toEqual([]);
  });
});

describe("腿價與淨成本", () => {
  it("買腿取 Ask、賣腿取 Bid、淨成本取引擎的最差成交成本", () => {
    const candidate = resolveCandidate(view, result.expiry_top10![0].candidate_keys[0])!;
    const prices = legPrices(candidate);
    const buy = candidate.legs.find((leg) => leg.side === "buy")!;
    const sell = candidate.legs.find((leg) => leg.side === "sell")!;
    expect(prices.buyAsk).toBe(buy.ask);
    expect(prices.sellBid).toBe(sell.bid);
    expect(prices.net).toBe(candidate.natural_cost);
  });

  it("單腳候選沒有賣腿——說 null，不是 0", () => {
    const candidate = resolveCandidate(view, result.expiry_top10![0].candidate_keys[0])!;
    const buy = candidate.legs.find((leg) => leg.side === "buy")!;
    const single: Candidate = { ...candidate, legs: [buy] };
    expect(legPrices(single).sellBid).toBeNull();
  });
});

describe("T16（#232，Initial V2）：逐腿最差成交價（三腿以上不靠固定買/賣兩個變數）", () => {
  it("兩腿候選：兩筆條目，各自買腿 Ask／賣腿 Bid，口數 1 不標倍數", () => {
    const candidate = resolveCandidate(view, result.expiry_top10![0].candidate_keys[0])!;
    const buy = candidate.legs.find((leg) => leg.side === "buy")!;
    const sell = candidate.legs.find((leg) => leg.side === "sell")!;
    const entries = legPriceEntries(candidate);
    expect(entries).toEqual([
      { label: "買", price: buy.ask },
      { label: "賣", price: sell.bid },
    ]);
  });

  it("三腿候選（Butterfly）：一隻腿都不丟，中腿口數 2 標成 2×", () => {
    const base = resolveCandidate(view, result.expiry_top10![0].candidate_keys[0])!;
    const leg1 = base.legs[0]!;
    const threeLegs: [typeof leg1, typeof leg1, typeof leg1] = [
      { ...leg1, strike: 100, side: "buy", quantity: 1 },
      { ...leg1, strike: 106, side: "sell", quantity: 2 },
      { ...leg1, strike: 115, side: "buy", quantity: 1 },
    ];
    const three: Candidate = { ...base, legs: threeLegs };
    expect(legPriceEntries(three)).toEqual([
      { label: "買", price: threeLegs[0].ask },
      { label: "賣 2×", price: threeLegs[1].bid },
      { label: "買", price: threeLegs[2].ask },
    ]);
  });
});

describe("該顯示哪一期", () => {
  const options = expiryOptions(view, result);

  it("預設是 baseline 期——與主圖同一口徑", () => {
    expect(resolveExpiry(options, null, view.baseline_expiry)).toBe(view.baseline_expiry);
  });

  it("使用者選過就用他選的", () => {
    const other = options.find((o) => o.expiry !== view.baseline_expiry)!;
    expect(resolveExpiry(options, other.expiry, view.baseline_expiry)).toBe(other.expiry);
  });

  it("選過的那期在新一次分析後消失，就退回 baseline，不是空白", () => {
    expect(resolveExpiry(options, "2099-01-01", view.baseline_expiry))
      .toBe(view.baseline_expiry);
  });

  it("連 baseline 都不在候選裡就退回第一期", () => {
    expect(resolveExpiry(options, null, "2099-01-01")).toBe(options[0].expiry);
  });

  it("一期都沒有時回 null", () => {
    expect(resolveExpiry([], null, "2026-08-07")).toBeNull();
  });
});
