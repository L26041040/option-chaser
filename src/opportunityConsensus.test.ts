import { afterEach, describe, expect, it, vi } from "vitest";

import sample from "../contracts/opportunity_consensus_sample.json";
import { getOpportunityConsensus, type OpportunityConsensusResponse } from "./api";

// 形狀取自前後端共用的契約樣本（OS-03／#392）；後端改欄位時後端的
// `test_opportunity_consensus_sample_matches_the_live_response` 會先紅。
const typed: OpportunityConsensusResponse = sample as OpportunityConsensusResponse;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getOpportunityConsensus", () => {
  it("reads the consensus list from the API and returns it as-is", async () => {
    const spy = vi.fn(async () => new Response(JSON.stringify(sample), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", spy);

    const got = await getOpportunityConsensus();

    expect(spy).toHaveBeenCalledTimes(1);
    expect(String((spy.mock.calls[0] as unknown[])[0])).toBe("/api/opportunity/consensus");
    expect(got).toEqual(typed);
  });

  it("surfaces the 403 message for Normal users", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ detail: "機會搜尋目前只開放 Super User／Super Admin" }),
      { status: 403, headers: { "Content-Type": "application/json" } })));

    await expect(getOpportunityConsensus()).rejects.toThrow(
      "機會搜尋目前只開放 Super User／Super Admin");
  });
});

describe("contract sample", () => {
  it("is fixture data and must be labelled as such", () => {
    expect(typed.source).toEqual({ configured: true, name: "fixture", is_fixture: true });
  });

  it("covers selected, partially passing, insufficient, no-data and failed symbols", () => {
    const bySymbol = Object.fromEntries(typed.items.map((i) => [i.symbol, i]));
    expect(bySymbol.AAA.gate.selected).toBe(true);
    expect([bySymbol.BBB.gate.first, bySymbol.BBB.gate.second]).toEqual([true, false]);
    expect([bySymbol.CCC.gate.first, bySymbol.CCC.gate.second]).toEqual([false, true]);
    expect(bySymbol.DDD.status).toBe("insufficient_analysts");
    expect(bySymbol.FFF.status).toBe("no_data");
    expect(bySymbol.GGG.status).toBe("source_error");
  });
});
