/**
 * 共用測試假體（T11／#229，`/code-review` Standards 軸回饋：`family.
 * test.ts`／`FamilyTabs.test.tsx` 兩份測試原本各自複製一份逐字相同的
 * `candidate()`／`result()`／`view()`——這裡抽出來只服務這兩個檔案
 * （不是全站共用 test utils，其餘測試檔各自的假體需求不同，仍照既有
 * 慣例各自維護，不必為了「共用」而互相遷就）。
 *
 * 手造最小 fixture 以完全控制 `results[]` 的順序與 `status`——真實
 * 契約樣本恆為單一策略，測不出多 family／多 subtype 才會出現的排序
 * 陷阱（見 `family.ts::championCandidate()` 檔頭說明）。
 */
import type {
  AnalysisView, Candidate, FamilyEligibility, StrategyResult,
} from "./api";

export function candidate(key: string, strategy: string, ret: number): Candidate {
  return {
    candidate_key: key,
    strategy,
    baseline_return: ret,
    natural_cost: 1,
    mid_cost: 1,
    breakeven: 100,
    breakeven_points: [100],
    profit_region: null,
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

export function result(
  strategy: string,
  status: "ok" | "skipped_direction" | "empty",
  perExpiry: Record<string, string[]> = {},
  message = "",
): StrategyResult {
  return {
    strategy,
    status,
    message: message || (status === "ok" ? "" : `${strategy} 沒有產生結果`),
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

export function view(
  results: StrategyResult[],
  pool: Record<string, Candidate>,
  overrides: Partial<AnalysisView> & {
    familyEligibility?: Record<string, FamilyEligibility>;
  } = {},
): AnalysisView {
  const { familyEligibility, ...rest } = overrides;
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
    family_eligibility: familyEligibility,
    ...rest,
  };
}
