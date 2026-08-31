/**
 * T11（#229，Initial V2）：Strategy Family 分組與跨 subtype 排名池
 * 合併——純函式層測試，手造最小 fixture 以完全控制 `results[]` 的
 * 順序與 `status`（真實契約樣本恆為單一策略，測不出多 family／多
 * subtype 才會出現的排序陷阱）。
 */
import { describe, expect, it } from "vitest";

import type { AnalysisView, Candidate, StrategyResult } from "./api";
import {
  FAMILIES, FAMILY_LABELS, championCandidate, enabledFamilies, familyOf,
  familyBaselineTopCandidate, mergedExpiryTop10, resultForStrategy,
  resultsByFamily,
} from "./family";

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
): StrategyResult {
  return {
    strategy,
    status,
    message: status === "ok" ? "" : `${strategy} 不適用`,
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
  overrides: Partial<AnalysisView> = {},
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
    ...overrides,
  };
}

describe("familyOf", () => {
  it("四個既有 subtype 各自映射到正確的 family", () => {
    expect(familyOf("long-call")).toBe("single-leg");
    expect(familyOf("long-put")).toBe("single-leg");
    expect(familyOf("bull-call-spread")).toBe("vertical-spread");
    expect(familyOf("bear-put-spread")).toBe("vertical-spread");
  });

  it("未知 subtype 原樣回傳，不假造一個 family", () => {
    expect(familyOf("call-fly")).toBe("call-fly");
  });
});

describe("enabledFamilies", () => {
  it("依 canonical 順序輸出，不受 `enabled` 傳入順序影響", () => {
    expect(enabledFamilies(["butterfly", "single-leg"], view([], {})))
      .toEqual(["single-leg", "butterfly"]);
  });

  it("去重", () => {
    expect(enabledFamilies(["vertical-spread", "vertical-spread"], view([], {})))
      .toEqual(["vertical-spread"]);
  });

  it("`enabled` 為空時從 `view.results` 反推，不讓詳細頁開天窗", () => {
    const v = view([result("long-call", "ok", { "2026-09-18": ["k1"] })],
                    { k1: candidate("k1", "long-call", 0.5) });
    expect(enabledFamilies([], v)).toEqual(["single-leg"]);
  });

  it("FAMILIES 詞彙表本身就是三個 canonical 值", () => {
    expect(FAMILIES).toEqual(["single-leg", "vertical-spread", "butterfly"]);
    expect(Object.keys(FAMILY_LABELS).sort()).toEqual([...FAMILIES].sort());
  });
});

describe("resultsByFamily", () => {
  it("依 subtype→family 分組，同一 family 底下多筆保留原順序", () => {
    const results = [
      result("bull-call-spread", "ok", { "2026-09-18": ["k1"] }),
      result("bear-put-spread", "skipped_direction"),
      result("long-call", "ok", { "2026-09-18": ["k2"] }),
    ];
    const grouped = resultsByFamily(view(results, {}));
    expect(grouped.get("vertical-spread")!.map((r) => r.strategy))
      .toEqual(["bull-call-spread", "bear-put-spread"]);
    expect(grouped.get("single-leg")!.map((r) => r.strategy))
      .toEqual(["long-call"]);
    expect(grouped.has("butterfly")).toBe(false);
  });
});

describe("championCandidate（跨 family 冠軍）", () => {
  it("單一 ok 結果——與舊版 primaryResult 的候選相同", () => {
    const v = view(
      [result("bull-call-spread", "ok", { "2026-09-18": ["k1"] })],
      { k1: candidate("k1", "bull-call-spread", 0.4) },
    );
    expect(championCandidate(v)?.candidate_key).toBe("k1");
  });

  it("真實回歸：results[0] 是被方向閘門擋掉的 skipped_direction，"
     + "冠軍仍要正確解到 results[1] 的候選（2026-08-30 用真實 HTTP "
     + "路徑重現過這個情境，見 family.ts 檔頭說明）", () => {
    const v = view(
      [
        result("bull-call-spread", "skipped_direction"),
        result("bear-put-spread", "ok", { "2026-09-18": ["k1"] }),
      ],
      { k1: candidate("k1", "bear-put-spread", 3.0) },
    );
    expect(championCandidate(v)?.candidate_key).toBe("k1");
    expect(championCandidate(v)?.strategy).toBe("bear-put-spread");
  });

  it("跨 family 比大小——較高報酬的那個勝出，不論它在陣列裡的位置", () => {
    const v = view(
      [
        result("long-call", "ok", { "2026-09-18": ["k1"] }),
        result("bull-call-spread", "ok", { "2026-09-18": ["k2"] }),
      ],
      {
        k1: candidate("k1", "long-call", 0.3),
        k2: candidate("k2", "bull-call-spread", 0.9),
      },
    );
    expect(championCandidate(v)?.candidate_key).toBe("k2");
  });

  it("同分時，`results` 較前面（展開順序較前）的那個勝出", () => {
    const v = view(
      [
        result("long-call", "ok", { "2026-09-18": ["k1"] }),
        result("bull-call-spread", "ok", { "2026-09-18": ["k2"] }),
      ],
      {
        k1: candidate("k1", "long-call", 0.5),
        k2: candidate("k2", "bull-call-spread", 0.5),
      },
    );
    expect(championCandidate(v)?.candidate_key).toBe("k1");
  });

  it("全部方向不合／零候選時回傳 null，不是硬湊一個假冠軍", () => {
    const v = view(
      [result("long-call", "skipped_direction"), result("long-put", "empty")],
      {},
    );
    expect(championCandidate(v)).toBeNull();
  });
});

describe("resultForStrategy", () => {
  it("找得到就回傳那一筆，找不到回 null", () => {
    const results = [result("long-call", "ok", { "2026-09-18": ["k1"] })];
    const v = view(results, { k1: candidate("k1", "long-call", 0.2) });
    expect(resultForStrategy(v, "long-call")?.strategy).toBe("long-call");
    expect(resultForStrategy(v, "bull-call-spread")).toBeNull();
  });
});

describe("mergedExpiryTop10（同一排名池，AC 明文要求）", () => {
  it("單一 ok subtype——原樣透傳（今天恆為此情況）", () => {
    const results = [result("bull-call-spread", "ok",
      { "2026-09-18": ["k1", "k2"] })];
    const v = view(results, {
      k1: candidate("k1", "bull-call-spread", 0.5),
      k2: candidate("k2", "bull-call-spread", 0.3),
    });
    const merged = mergedExpiryTop10(v, results);
    expect(merged.expiry_top10).toEqual(
      [{ expiry: "2026-09-18", candidate_keys: ["k1", "k2"] }]);
    expect(merged.expiry_counts).toEqual([["2026-09-18", 2]]);
  });

  it("兩個同時 ok 的 subtype（T15／#230 之後才會真的發生）：候選"
     + "合併進同一個排名池，依 baseline_return 重新排序、不依 subtype 分區",
    () => {
      const callFly = result("call-fly", "ok", { "2026-09-18": ["a1", "a2"] });
      const putFly = result("put-fly", "ok", { "2026-09-18": ["b1"] });
      const v = view([callFly, putFly], {
        a1: candidate("a1", "call-fly", 0.2),
        a2: candidate("a2", "call-fly", 0.6),
        b1: candidate("b1", "put-fly", 0.9),
      });
      const merged = mergedExpiryTop10(v, [callFly, putFly]);
      expect(merged.expiry_top10).toEqual(
        [{ expiry: "2026-09-18", candidate_keys: ["b1", "a2", "a1"] }]);
      // 「有效組數」是這個 family 整體的事，逐到期日加總。
      expect(merged.expiry_counts).toEqual([["2026-09-18", 3]]);
    });

  it("每個到期日各自取前十，不是全域截斷", () => {
    const keys = Array.from({ length: 12 }, (_, i) => `k${i}`);
    const pool = Object.fromEntries(
      keys.map((k, i) => [k, candidate(k, "long-call", 1 - i * 0.01)]));
    const r = result("long-call", "ok", { "2026-09-18": keys });
    const merged = mergedExpiryTop10(view([r], pool), [r]);
    expect(merged.expiry_top10[0].candidate_keys).toHaveLength(10);
    expect(merged.expiry_top10[0].candidate_keys[0]).toBe("k0");
  });

  it("到期日依日期字串排序，不受哪個 subtype 先跑到而定", () => {
    const early = result("long-put", "ok", { "2026-08-21": ["p1"] });
    const late = result("long-call", "ok", { "2026-09-18": ["c1"] });
    const v = view([late, early], {
      p1: candidate("p1", "long-put", 0.1),
      c1: candidate("c1", "long-call", 0.2),
    });
    const merged = mergedExpiryTop10(v, [late, early]);
    expect(merged.expiry_top10.map((g) => g.expiry))
      .toEqual(["2026-08-21", "2026-09-18"]);
  });

  it("candidate_pool 裡找不到的 key 被安全濾掉，不會讓整組壞掉", () => {
    const r = result("long-call", "ok", { "2026-09-18": ["ghost"] });
    const merged = mergedExpiryTop10(view([r], {}), [r]);
    expect(merged.expiry_top10).toEqual([{ expiry: "2026-09-18", candidate_keys: [] }]);
  });
});

describe("familyBaselineTopCandidate", () => {
  it("解回合併後排名池裡 baseline 到期日的第 1 名", () => {
    const r = result("bull-call-spread", "ok",
      { "2026-09-18": ["k1", "k2"] });
    const v = view([r], {
      k1: candidate("k1", "bull-call-spread", 0.5),
      k2: candidate("k2", "bull-call-spread", 0.3),
    });
    const merged = mergedExpiryTop10(v, [r]);
    expect(familyBaselineTopCandidate(v, merged)?.candidate_key).toBe("k1");
  });

  it("baseline 到期日不在合併後的排名池裡時回傳 null", () => {
    const r = result("long-call", "ok", { "2099-01-01": ["k1"] });
    const v = view([r], { k1: candidate("k1", "long-call", 0.5) });
    const merged = mergedExpiryTop10(v, [r]);
    expect(familyBaselineTopCandidate(v, merged)).toBeNull();
  });
});
