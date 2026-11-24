/**
 * OS-05（#394）：機會搜尋頁的純邏輯——跨標的排序與續跑合併。
 * 排序的期望值逐列手寫（不是用同一套比較式重算），tie-break 對齊後端
 * `opportunity_search.sort_rows()`：(排序鍵, symbol, family)。
 */
import { describe, expect, it } from "vitest";

import type { OpportunityRow } from "./api";
import { mergeSearchRows, rankOpportunities } from "./opportunity";

function row(
  symbol: string,
  family: string,
  o: { ret: number; cost: number; loss: number },
): OpportunityRow {
  return {
    symbol, family, subtype: "long-call", candidate_key: `${symbol}|${family}`,
    legs: [{ strike: 100, option_type: "call", side: "buy", quantity: 1 }],
    expiry: "2026-12-18", target_month: "2027-09", buffer_days: -273,
    entry_cost: o.cost, max_loss_per_contract: o.loss, target_return: o.ret,
    breakeven: 101,
    consensus: { mean: 120, n_analysts: 7, dispersion: 0.09, percentile: 0.1,
                 as_of: "2026-09-28", coverage: "partial" },
    scenario: { symbol, target_price: 120, target_month: "2027-09",
                strategies: ["single-leg"] },
  };
}

const ids = (rows: OpportunityRow[]) => rows.map((r) => `${r.symbol}/${r.family}`);

const ROWS = [
  row("BBB", "vertical-spread", { ret: 1.5, cost: 2.0, loss: 300 }),
  row("AAA", "single-leg", { ret: 2.7, cost: 5.6, loss: 560 }),
  row("CCC", "butterfly", { ret: 0.4, cost: 0.5, loss: 90 }),
  row("AAA", "butterfly", { ret: 1.5, cost: 2.0, loss: 300 }),
];

describe("rankOpportunities", () => {
  it("return：股價達標時的策略報酬由高到低，同值依 symbol 再 family", () => {
    expect(ids(rankOpportunities(ROWS, "return"))).toEqual([
      "AAA/single-leg", "AAA/butterfly", "BBB/vertical-spread", "CCC/butterfly",
    ]);
  });

  it("cost：投入成本由低到高，同值依 symbol 再 family", () => {
    expect(ids(rankOpportunities(ROWS, "cost"))).toEqual([
      "CCC/butterfly", "AAA/butterfly", "BBB/vertical-spread", "AAA/single-leg",
    ]);
  });

  it("max_loss：最大損失由低到高，同值依 symbol 再 family", () => {
    expect(ids(rankOpportunities(ROWS, "max_loss"))).toEqual([
      "CCC/butterfly", "AAA/butterfly", "BBB/vertical-spread", "AAA/single-leg",
    ]);
  });

  it("同 symbol 同排序值時 family 以字串順序決定（butterfly < single-leg < vertical-spread）", () => {
    const tied = [
      row("AAA", "vertical-spread", { ret: 1, cost: 1, loss: 100 }),
      row("AAA", "single-leg", { ret: 1, cost: 1, loss: 100 }),
      row("AAA", "butterfly", { ret: 1, cost: 1, loss: 100 }),
    ];
    for (const sort of ["return", "cost", "max_loss"] as const) {
      expect(ids(rankOpportunities(tied, sort))).toEqual([
        "AAA/butterfly", "AAA/single-leg", "AAA/vertical-spread",
      ]);
    }
  });

  it("結果與輸入順序無關，且不改動輸入陣列", () => {
    const input = [...ROWS];
    const reversed = [...ROWS].reverse();
    expect(ids(rankOpportunities(input, "return")))
      .toEqual(ids(rankOpportunities(reversed, "return")));
    expect(input).toEqual(ROWS);
  });
});

describe("mergeSearchRows（續跑合併）", () => {
  it("新回來的列接在後面；同一個 symbol＋family 再回來時以新的取代、不重複", () => {
    const first = [ROWS[1], ROWS[3]];
    const again = row("AAA", "single-leg", { ret: 9, cost: 9, loss: 900 });
    const merged = mergeSearchRows(first, [again, ROWS[0]]);
    expect(ids(merged)).toEqual(["AAA/single-leg", "AAA/butterfly", "BBB/vertical-spread"]);
    expect(merged[0].target_return).toBe(9);
  });
});
