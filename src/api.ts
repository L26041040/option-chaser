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

/** 一隻腿。契約裡還有 iv／open_interest 等欄位，畫面用到再加。 */
export interface Leg {
  strike: number;
  option_type: string;
  expiry: string;
  /** 買這隻腿要付的價（最差成交假設用 Ask）。 */
  ask: number;
  /** 賣這隻腿收得到的價（最差成交假設用 Bid）。 */
  bid: number;
}

/**
 * 價格×日期報酬矩陣（引擎的 `MatrixView`）。`prices`／`dates` 的第二欄是
 * **引擎給的**錨點標籤，GUI 只讀不算（v4 spec §4.3 的既有原則）。
 */
export interface Matrix {
  prices: [number, string][];
  dates: [string, string][];
  cells: number[][];
}

/** 一個劇本價位與該候選在那個價位上的報酬（口徑同 `baseline_return`）。 */
export interface PricePoint {
  label: "worst" | "target" | "best";
  price: number;
  return: number;
}

export interface Candidate {
  candidate_key: string;
  baseline_return: number;
  natural_cost: number;
  /** Long Call 追平價格 S*。同履約價 Call 報價缺失時為 null＝無法計算。 */
  catchup_price: number | null;
  /**
   * V7（#55）劇本區間三價位對照，由最差到最好排序。目標價恆在其中；
   * 兩端只在使用者設定時才出現，所以長度是 1～3。
   * 選填是因為 V7 之前落盤的結果沒有這個欄位。
   */
  price_ladder?: PricePoint[];
  /** 引擎標記的報價品質疑慮（⚠ 徽章）。 */
  quote_warning: boolean;
  legs: Leg[];
  matrix: Matrix;
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

/** 這次分析用的劇本參數（引擎回填的那一份，非前端送出的原樣）。 */
export interface AnalysisParams {
  target_price: number;
  target_month: string;
  strategy: string;
}

export interface AnalysisView {
  meta: AnalysisMeta;
  params: AnalysisParams;
  baseline_expiry: string | null;
  results: StrategyResult[];
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

/**
 * 詳細頁要的東西：清單列的所有欄位，外加最新一次的完整分析結果。
 * `latest_result` 為 null ＝ 還沒跑過分析，詳細頁據此說「尚未分析」，
 * 而不是畫一張空圖。
 */
export interface ScenarioDetail extends ScenarioSummary {
  latest_result: AnalysisView | null;
}

export interface CreateScenarioRequest {
  symbol: string;
  target_price: number;
  target_month: string;
  /** V7（#55）劇本區間兩端，選填——沒設定就不送這兩個鍵。 */
  best_price?: number;
  worst_price?: number;
}

function stageOf(value: unknown): FailureStage {
  return STAGES.includes(value as (typeof STAGES)[number])
    ? (value as FailureStage)
    : null;
}

/**
 * 一趟請求最多等多久。刷新是逐一排隊跑的：沒有上限的話，一個永遠不回來
 * 的請求（行動網路切換、連線被中途丟掉）會讓整條佇列卡死——按鈕一直
 * disabled、後面的劇本永遠輪不到，而且畫面上什麼都不會說。
 *
 * 90 秒的理由：serverless 函式自己的上限是 60 秒（`vercel.json`），
 * 留一點餘裕給網路來回；比它短的話會把還在正常跑的分析誤判成逾時。
 */
const REQUEST_TIMEOUT_MS = 90_000;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (e) {
    // 逾時／連線斷掉：說「等不到回應」，而不是把 DOMException 的英文
    // 原文丟到手機畫面上。分層是 null——我們並不知道伺服器跑到哪一段。
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new ApiError("等太久沒有回應（逾時），請重試");
    }
    throw new ApiError(
      `連不到伺服器：${e instanceof Error ? e.message : String(e)}`);
  }
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

/** 詳細頁用（V5／#53）：整份 view 只有這裡會拖，清單列不帶。 */
export function getScenario(id: string): Promise<ScenarioDetail> {
  return request<ScenarioDetail>(`/api/scenarios/${encodeURIComponent(id)}`);
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
 * 該次分析要顯示的那個策略（MVP 只請求一個）。摘要卡與候選池診斷都走
 * 這個函式——兩處各自挑一個 result 的話，畫面會出現「第 1 名講 A 策略、
 * 池子講 B 策略」的自相矛盾。
 */
export function primaryResult(view: AnalysisView): StrategyResult | null {
  return view.results[0] ?? null;
}
