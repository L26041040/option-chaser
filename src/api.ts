/**
 * API 客戶端與型別（V1／#48）。
 *
 * 契約＝後端 `store.serialize_result` 的 view dict，樣本存在
 * `contracts/analysis_sample.json`（前後端共用同一份，見
 * `scripts/gen_contract_sample.py`）。型別刻意只宣告目前畫面用得到的
 * 欄位——view dict 很大，逐步加型別比一次抄完整份更不容易腐化。
 *
 * 本層與整個前端都不做金融計算：每個顯示數字都已由引擎算好。
 */

export interface AnalysisMeta {
  symbol: string;
  spot: number;
  fetched_at: string;
  source: string;
  target_move: number;
}

export interface Candidate {
  candidate_key: string;
  baseline_return: number;
  natural_cost: number;
  legs: { strike: number; option_type: string; expiry: string }[];
}

export interface ExpiryTop10 {
  expiry: string;
  candidates: Candidate[];
}

/** 一道品質過濾關卡砍掉的筆數（引擎的 `FilterReport.stages`）。 */
export interface FilterStage {
  label: string;
  removed: number;
}

/**
 * 合約層級的抓到／通過筆數（引擎的 `FilterReport`）。
 *
 * 這是唯一能拿來當「合約數」的來源。`n_qualified` 在 spread 路徑是
 * **配對數**（引擎 `_spread_result` 取 `pair_report.passed`），兩者
 * 意義不同，不可互推。
 */
export interface FilterReportCounts {
  total: number;
  passed: number;
}

export interface PairReport {
  total_pairs: number;
  removed_sanity: number;
  passed: number;
}

export interface StrategyResult {
  strategy: string;
  status: string;
  message: string;
  /** spread 路徑是**配對數**、單腳路徑才是合約數——顯示合約數請用
   *  `filter_report`。 */
  n_qualified: number;
  filter_report: FilterReportCounts | null;
  filter_stages: FilterStage[];
  pair_report: PairReport | null;
  /** [到期日, 該期通過配對的有效候選組數]，引擎的 `expiry_counts`。 */
  expiry_counts: [string, number][];
  expiry_top10?: ExpiryTop10[];
}

export interface AnalysisView {
  meta: AnalysisMeta;
  baseline_expiry: string | null;
  results: StrategyResult[];
}

export interface AnalyzeRequest {
  symbol: string;
  target_price: number;
  target_month: string;
  strategies: string[];
}

/**
 * 失敗發生在哪一個環節（後端 `_fail` 的 `stage`，V4／#52）。
 * `null` ＝ 後端沒說（例如 422 之類的驗證錯誤），畫面退回通用說法。
 */
export type FailureStage = "fetch" | "analyze" | "params" | null;

const STAGES = ["fetch", "analyze", "params"] as const;

export class ApiError extends Error {
  readonly stage: FailureStage;

  constructor(message: string, stage: FailureStage = null) {
    super(message);
    this.stage = stage;
  }
}

/** 一個劇本這次刷新失敗的原因（分層＋給人看的訊息）。 */
export interface RefreshFailure {
  stage: FailureStage;
  message: string;
}

/**
 * 任何丟出來的東西都收斂成可顯示的失敗。網路本身斷掉時 `fetch` 丟的是
 * TypeError，不帶分層——那也要有話講，不能讓卡片空著。
 */
export function toFailure(e: unknown): RefreshFailure {
  if (e instanceof ApiError) return { stage: e.stage, message: e.message };
  return { stage: null, message: e instanceof Error ? e.message : String(e) };
}

/**
 * 一個劇本在清單上的樣子。`latest_analyzed_at` 與 `best_return` 由清單
 * 端點一起帶回（後端 V3／#51），前端不必為每張卡再打一次 detail。
 * 兩者為 null ＝ 這個劇本還沒跑過分析，卡片顯示「—」。
 */
export interface ScenarioSummary {
  id: string;
  symbol: string;
  target_price: number;
  target_month: string;
  created_at: string;
  archived_at: string | null;
  latest_analyzed_at: string | null;
  best_return: number | null;
  /** 目標月的到期錨點（該月第三個星期五）與距今天數，皆由後端算好。
   *  負數＝已過期，不夾成 0。 */
  target_anchor: string;
  days_to_anchor: number;
}

export interface CreateScenarioRequest {
  symbol: string;
  target_price: number;
  target_month: string;
}

function stageOf(value: unknown): FailureStage {
  return STAGES.includes(value as (typeof STAGES)[number])
    ? (value as FailureStage)
    : null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const detail = await resp
      .json()
      .then((b) => b?.detail)
      .catch(() => null);
    // 三種 detail 形狀都可能出現，各自處理：
    // 1. `{stage, message}`——分析路徑的分層錯誤（V4／#52）
    // 2. 純字串——其他端點（404／建立時的月份驗證）
    // 3. FastAPI 驗證錯誤（422）的物件陣列，直接丟進畫面會變成
    //    [object Object]，所以退回帶狀態碼的通用訊息
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const body = detail as { stage?: unknown; message?: unknown };
      if (typeof body.message === "string") {
        throw new ApiError(body.message, stageOf(body.stage));
      }
    }
    const message =
      typeof detail === "string" ? detail : `請求失敗（HTTP ${resp.status}）`;
    throw new ApiError(message);
  }
  return resp.json();
}

const POST_JSON = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function analyze(req: AnalyzeRequest): Promise<AnalysisView> {
  return request<AnalysisView>("/api/analyze", POST_JSON(req));
}

export function listScenarios(): Promise<ScenarioSummary[]> {
  return request<ScenarioSummary[]>("/api/scenarios");
}

export function createScenario(
  req: CreateScenarioRequest,
): Promise<ScenarioSummary> {
  return request<ScenarioSummary>("/api/scenarios", POST_JSON(req));
}

/**
 * 刷新單一劇本（V4／#52）：後端抓鏈→分析→入庫，回傳的是**卡片列**，
 * 與清單同一形狀，所以拿到就能直接換掉清單裡那一列。
 */
export function refreshScenario(id: string): Promise<ScenarioSummary> {
  return request<ScenarioSummary>(
    `/api/scenarios/${encodeURIComponent(id)}/refresh`,
    { method: "POST" },
  );
}

export function archiveScenario(id: string): Promise<{ archived: boolean }> {
  return request<{ archived: boolean }>(
    `/api/scenarios/${encodeURIComponent(id)}/archive`,
    { method: "POST" },
  );
}

/**
 * baseline 到期日那一組的第 1 名候選。引擎已把各期候選依收益率排好序，
 * 這裡只是取出，不做任何排序或計算。
 *
 * baseline 期沒有任何合格候選時回傳 null（附錄A10.2 的既有邊界，引擎的
 * `baseline_selection` 同樣是 None）——刻意**不**退而取別期的第 1 名：
 * 那會在標著 baseline 到期日的欄位旁顯示另一個到期日的候選，是誤導。
 */
export function baselineTopCandidate(view: AnalysisView): Candidate | null {
  const ok = primaryResult(view);
  if (!ok?.expiry_top10) return null;
  const group = ok.expiry_top10.find((g) => g.expiry === view.baseline_expiry);
  return group?.candidates[0] ?? null;
}

/**
 * FB4-01（#60）：拿引擎已算好的每期有效組數。找不到該期回傳 null——
 * 「不知道」與「0 組」是不同的事，不能混為一談。
 */
export function validPairsForExpiry(
  result: StrategyResult,
  expiry: string | null,
): number | null {
  if (expiry === null) return null;
  const hit = result.expiry_counts.find(([e]) => e === expiry);
  return hit ? hit[1] : null;
}

/**
 * 該次分析要顯示的那個策略（MVP 只請求一個）。摘要卡與候選池診斷都走
 * 這個函式——兩處各自挑一個 result 的話，畫面會出現「第 1 名講 A 策略、
 * 池子講 B 策略」的自相矛盾。
 */
export function primaryResult(view: AnalysisView): StrategyResult | null {
  return view.results[0] ?? null;
}
