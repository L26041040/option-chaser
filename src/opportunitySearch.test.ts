import { afterEach, describe, expect, it, vi } from "vitest";

import sample from "../contracts/opportunity_search_sample.json";
import { searchOpportunities, type OpportunitySearchResponse } from "./api";

// 形狀取自前後端共用的契約樣本（OS-04／#393）；後端改欄位時後端的
// `test_opportunity_search_sample_matches_the_live_response` 會先紅。
const typed: OpportunitySearchResponse = sample as OpportunitySearchResponse;

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });
}

describe("searchOpportunities", () => {
  it("POSTs the overrides and returns the response as-is", async () => {
    const spy = vi.fn(async () => jsonResponse(sample));
    vi.stubGlobal("fetch", spy);

    const got = await searchOpportunities({ symbols: ["AAA"], sort: "cost" });

    expect(spy).toHaveBeenCalledTimes(1);
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toBe("/api/opportunity/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ symbols: ["AAA"], sort: "cost" });
    expect(got).toEqual(typed);
  });

  it("sends an empty body by default (= the current selected list)", async () => {
    const spy = vi.fn(async () => jsonResponse(sample));
    vi.stubGlobal("fetch", spy);

    await searchOpportunities();

    const [, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({});
  });

  it("surfaces the 409 message when no analyst source is configured", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(
      { detail: "尚未設定分析師資料來源" }, 409)));

    await expect(searchOpportunities()).rejects.toThrow("尚未設定分析師資料來源");
  });
});

describe("contract sample", () => {
  it("has one row per family whose scenario can be saved as-is", () => {
    expect(typed.rows.map((r) => r.family).sort()).toEqual(
      ["butterfly", "single-leg", "vertical-spread"]);
    for (const row of typed.rows) {
      expect(row.scenario).toEqual({
        symbol: row.symbol, target_price: row.consensus.mean,
        // 只帶這一列的家族：存成劇本後詳細頁的冠軍＝被點的那一列（#408）。
        target_month: row.target_month, strategies: [row.family],
      });
    }
  });

  it("isolates the failed symbol and finishes in one call", () => {
    expect(typed.failures.map((f) => [f.symbol, f.reason])).toEqual([["EEE", "fetch_failed"]]);
    expect(typed.processed).toEqual(["AAA", "EEE"]);
    expect(typed.remaining).toEqual([]);
    expect(typed.stopped_reason).toBeNull();
  });

  it("uses no expected / probability / win wording in field names", () => {
    const keys: string[] = [];
    const walk = (x: unknown): void => {
      if (Array.isArray(x)) x.forEach(walk);
      else if (x && typeof x === "object") {
        for (const [k, v] of Object.entries(x)) { keys.push(k); walk(v); }
      }
    };
    walk(sample);
    expect(keys.filter((k) => /expected|probability|win/i.test(k))).toEqual([]);
  });
});
