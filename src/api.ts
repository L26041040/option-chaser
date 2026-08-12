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

export interface Leg {
  strike: number;
  option_type: string;
  expiry: string;
  /** 買這隻腿要付的價（最差成交假設用 Ask）。 */
  ask: number;
  /** 賣這隻腿收得到的價（最差成交假設用 Bid）。 */
  bid: number;
  iv: number | null;
  /** MVP V3（#105，spec #102 決策 G）：Analysis Report → Execution 區
   *  中性 metadata（低權重、無警示樣式），與 #104 的顯示旗標無關。 */
  volume: number;
  open_interest: number;
}

/** 代表候選（MVP-v2／#77、#78）：劇本清單卡片要的候選完整身分——只到
 *  「顯示要用」這一層，不是完整的 `Candidate`／`Leg`（報價、IV、量能等
 *  欄位留在詳細頁）。`legs[0]` 是買腿，`legs[1]`（若有）是賣腿——沿用
 *  後端序列化層既有的 `[0]=long, [1]=short` 慣例。單腳策略只有一隻腿；
 *  結構上不假設腿數固定，未來策略種類增加不必改型別。
 *
 *  `baseline_return` 與卡片列的 `best_return` 必為同一個數字（後端
 *  `store.best_return` 由這個結構導出，口徑恆等）——前端不重算、只顯示。
 */
export interface RepresentativeCandidateLeg {
  strike: number;
  option_type: string;
}

export interface RepresentativeCandidate {
  strategy: string;
  legs: RepresentativeCandidateLeg[];
  expiry: string;
  baseline_return: number;
}

/**
 * 價格×日期報酬矩陣（引擎的 `MatrixView`）。`prices`／`dates` 的第二欄是
 * **引擎給的**錨點標籤，GUI 只讀不算（v4 spec §4.3 的既有原則）。
 *
 * 決策 M（#109）：`prices` 第三欄是 `move_pct`——該價位相對現價（spot）
 * 的變動分數，跟 cell 值同源同時點算出來，GUI 只格式化顯示，不重算。
 */
export interface Matrix {
  prices: [number, string, number][];
  dates: [string, string][];
  cells: number[][];
}

/** 一個劇本價位與該候選在那個價位上的報酬（口徑同 `baseline_return`）。 */
export interface PricePoint {
  label: "worst" | "target" | "best";
  price: number;
  return: number;
}

/**
 * #115（spec #117 §4）：Crossover 對照——就是這組 Spread 買腿本身。
 * `option_type` 讓前端直接顯示「Long Call」／「Long Put」，不必自己從
 * strategy 反推（後端 `ComparatorView` docstring：三欄直接複製自買腿，
 * 沒有分支邏輯可以讓它們偏離買腿本身）。`matrix` 與該候選自己的
 * `matrix` 同一組 price×date grid、同形狀，#116 的 Crossover Boundary
 * overlay 靠這個保證才能直接逐格比較兩個矩陣。
 */
export interface Comparator {
  option_type: "call" | "put";
  strike: number;
  expiry: string;
  cost: number;
  matrix: Matrix;
}

/** 引擎的 `ScenarioVector`（7 個固定壓力情境，Mid 口徑）。 */
export interface ScenarioVectorView {
  entries: [string, number][];
  worst_code: string;
  worst_return: number;
}

export interface Candidate {
  candidate_key: string;
  baseline_return: number;
  natural_cost: number;
  /** MVP V3（#105）：Mid 口徑進場成本——Analysis Report → Execution
   *  的「Net Mid」，與 `natural_cost`（Net Worst，最差成交口徑）並列
   *  對照。序列化早就存在（`store._candidate` 的 `mid_cost`），本票起
   *  前端才開始讀它。 */
  mid_cost: number;
  breakeven: number;
  /** 距這組候選自己的到期日還有幾天（V8／#56，spec R1 §4.2 B「剩餘
   *  天數」——早就序列化了，純文字報告沒印）。 */
  days_to_expiry: number;
  /** Long Call 無上限＝null；其餘策略是每股金額。 */
  max_profit: number | null;
  max_loss_per_contract: number;
  net_delta: number;
  effective_leverage: number;
  /** 佔成本比率（Mid 口徑）——不是原始美元 Greeks，見 R1 §4.2 注意事項。 */
  theta_day_rate: number;
  /**
   * MVP V3（#112，spec #102 決策 H）：這組候選估值實際用到的利率與
   * 年期——後端 `leg_rate(p, expiry)` 查表結果，與 `rate_by_expiry`
   * 建表同一條年期公式，前端只格式化、不查表、不換算。
   */
  rate_used: number;
  rate_tenor_years: number;
  vega_per_pt: number;
  scenario_vector: ScenarioVectorView;
  completion_curve: [number, number][];
  completion_threshold: number | null;
  retention: number;
  friction: number;
  friction_amount: number;
  /**
   * V8（#56，spec R1 §4.2 A2）：買價指引天花板——純文字報告早就在印，
   * 這裡補上序列化。單腿的 L1（＝保守底線）依票上 A2 表範圍不補。
   */
  l2: number;
  l3: number;
  /** 評語「代價」——「優點」pros 依 R1 §4.2 C 裁示不補序列化。 */
  cons: string[];
  /** 買 Ask 超過哪些天花板的警示句（`valuation.guidance_judgments`）。 */
  guidance_warnings: string[];
  /** Long Call 追平價格 S*。同履約價 Call 報價缺失時為 null＝無法計算。 */
  catchup_price: number | null;
  /**
   * V7（#55）劇本區間三價位對照，由最差到最好排序。目標價恆在其中；
   * 兩端只在使用者設定時才出現，所以長度是 1～3。
   * 選填是因為 V7 之前落盤的結果沒有這個欄位。
   */
  price_ladder?: PricePoint[];
  /**
   * MVP V3（#104，spec #102 決策 F）：⚠ 徽章與候選池文案唯一該接的
   * 顯示旗標——僅 Bid/Ask 過寬（`is_spread_wide`）。零成交量、
   * Execution friction 超過 25% 都不再觸發顯示。舊的複合旗標
   * `quote_warning`（選取閘門用，含 zero_vol／friction 兩項）不對外
   * 序列化，此契約裡不會出現這個鍵。
   */
  wide_spread_warning: boolean;
  /**
   * FB5-03（#64）：無套利一致性違反——同到期日、同類型的相鄰履約價
   * 報價不單調，疑似陳舊報價。獨立於 `wide_spread_warning`：成因與
   * 嚴重性都不同（配對關係違反，不是單一數值超標），不合併成同一個
   * 布林值。
   */
  monotonicity_warning: boolean;
  legs: Leg[];
  matrix: Matrix;
  /**
   * #115（spec #117 §4）：Crossover 對照——只有 Spread 候選有值；單腿
   * 恆為 `null`（沒有「跟自己比較」的概念）。Spread 候選理論上也可能
   * 是 `null`（買腿報價缺失，結構上不該發生的防禦性 case）——#116 的
   * overlay 必須誠實處理這個缺席狀態，不能假造一條線。
   */
  comparator: Comparator | null;
}

export interface ExpiryTop10 {
  expiry: string;
  candidates: Candidate[];
}

/** 一道品質過濾關卡砍掉的筆數（引擎的 `FilterReport.stages`）。 */
export interface FilterStage {
  label: string;
  removed: number;
  /**
   * FB5-04（#65，spec #61）：這一關屬於三分類的哪一類——"A"＝資料健全性、
   * "B"＝數學前提，兩者都是硬門檻（會排除候選）。C 類（品質標示）從不
   * 出現在這裡，見 `QualityFlag`。
   */
  filter_class: string;
}

/**
 * FB5-04（#65，spec #61）：C 類品質標示在整個合格池裡的計數（引擎的
 * `filters.quality_flag_counts()`）——跟 `FilterStage` 的差別是「排除」
 * 跟「標示」：這裡的候選一個都沒被刪掉，只是被記下「這筆不夠好看」。
 */
export interface QualityFlag {
  label: string;
  count: number;
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
  quality_flags: QualityFlag[];
  pair_report: PairReport | null;
  /** [到期日, 該期通過配對的有效候選組數]，引擎的 `expiry_counts`。 */
  expiry_counts: [string, number][];
  expiry_top10?: ExpiryTop10[];
  /**
   * V8（#56，spec R1 §4.1）：新版型「⑥ 方法與假設」——`report.py` 的
   * `methodology_lines()`，與純文字報告同一個事實來源，只是拆出獨立
   * 欄位。多行文字，前端逐行呈現或原樣顯示皆可。
   */
  methodology_text: string;
  /** 新版型「⑦ 免責聲明」——獨立、不折疊的擴充版本（R1 §4.4.4）。 */
  disclaimer_text: string;
}

/** 這次分析用的劇本參數（引擎回填的那一份，非前端送出的原樣）。 */
export interface AnalysisParams {
  target_price: number;
  target_month: string;
  strategy: string;
  /**
   * 劇本區間兩端，建立劇本時選填（顯示文字為「最高／最低」，欄位名沿用
   * 既有契約）。`null` ＝ 使用者沒填。它們決定 Heatmap 的價格軸上下限，
   * 詳細頁摘要卡也直接顯示——沒有它們，圖上的 `<最高>`／`<最低>` 錨點
   * 使用者對不上是哪來的數字。
   */
  best_price: number | null;
  worst_price: number | null;
  /**
   * V8（#56，spec R1 §4.2 A）：新版型「⑥ 方法與假設」要的模型參數——
   * 利率、IV 情境、Delta 分級門檻、要求報酬上限。原本只活在
   * `report_text` 的 `[模型假設]` 區塊，早就在契約裡（`AnalysisParams`
   * 全欄位序列化），只是舊 TS 型別沒宣告。
   */
  rate: number;
  rate_note: string;
  /**
   * RC1（#87）：結構化三態訊號，獨立於 `rate_by_expiry` 是否非空——
   * 後者在曲線成功但鏈上零合約時仍會是空陣列，不能拿來判斷是否為
   * fallback。`rate_curve_used` 為 `false` 時 `rate` 才是真正被用在
   * 估值上的常數；為 `true` 時 `rate_curve_date` 是曲線資料日，
   * `rate_curve_stale` 標示是否為陳舊備援窗沿用的舊曲線。
   */
  rate_curve_used: boolean;
  rate_curve_date: string | null;
  rate_curve_stale: boolean;
  /** 使用者透過 CLI `--rate` 明示指定的利率——目前 MVP 網頁路徑不可達
   *  （只有 CLI 會設起），但欄位本來就在契約裡，型別跟著宣告，
   *  `RateRow` 才能跟後端 `report.py::_rate_line` 同一套三態判斷，不
   *  會在明示利率也顯示成 FALLBACK。 */
  rate_explicit: boolean;
  /**
   * #123（spec #117 §2）：股利殖利率 q 的三態揭露——形狀逐一對應
   * `rate_curve_used`／`rate_curve_date`／`rate_curve_stale`／
   * `rate_note`，`QRow` 與 `RateRow` 同一套判斷方式。`q_by_symbol`
   * 為 `null` 時（q 管線未接、或 fetch 失敗且無可用快取）走今天的
   * 完整行為，`q_source`／`q_as_of` 同為 `null`；有值時 `q_source`
   * 是實際取得資料的 vendor（"yahoo"／"fmp"／"nasdaq"），`q_stale`
   * 獨立於 `q_by_symbol is null`——陳舊備援窗內仍可能算出一個值。
   */
  q_by_symbol: number | null;
  q_source: string | null;
  q_as_of: string | null;
  q_stale: boolean;
  q_note: string;
  iv_shifts: number[];
  delta_bands: [number, number];
  min_return: number;
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
export type FailureStage = "fetch" | "analyze" | "params" | "archived" | null;

const STAGES = ["fetch", "analyze", "params", "archived"] as const;

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
  /**
   * 劇本區間兩端，建立劇本時選填（QA 修正後顯示文字為「最高／最低」，
   * 欄位名沿用既有契約）。`null` ＝ 使用者沒填。
   */
  best_price: number | null;
  worst_price: number | null;
  /**
   * 最近一次分析當下的標的現價（QA 修正）。劇本庫卡片要有它，目標價與
   * 最高／最低才有比較基準。`null` ＝ 這個劇本還沒成功分析過。
   */
  spot: number | null;
  created_at: string;
  archived_at: string | null;
  latest_analyzed_at: string | null;
  best_return: number | null;
  /** 目標月的到期錨點（該月第三個星期五）與距今天數，皆由後端算好。
   *  負數＝已過期，不夾成 0。 */
  target_anchor: string;
  days_to_anchor: number;
  /**
   * 目標年月最後一天是否已過完（#68，後端 `timeframe.month_is_over`）。
   * 與 `days_to_anchor < 0` 是不同的判準——後者以日曆錨點（第三個星期五）
   * 為準，會提早轉負。這個欄位才是後端用來擋批次刷新的那個判準，前端
   * 據此在排入刷新佇列前先篩掉，畫面上也用它顯示「已過期，不再刷新」。
   */
  expired: boolean;
  /**
   * 產生 `best_return` 的那組候選完整身分（MVP-v2／#77、#78）：策略、
   * 各腿履約價、實際到期日——沒有它，卡片上的報酬率無法被判讀出自
   * 哪一個 option combination。`null` ＝ 尚未分析、或該期零合格候選，
   * 與 `best_return === null` 同步（後端同一次走訪算出來，不會只有
   * 一邊是 null）。
   */
  representative_candidate: RepresentativeCandidate | null;
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
      throw new ApiError("伺服器逾時沒有回應，請重試");
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
  // TR3（#90）：永久刪除回 204 No Content——沒有主體可解析，`.json()`
  // 對空字串會直接炸掉。204 一律沒有主體（HTTP 語意），呼叫端此時
  // 期待的型別是 `void`，回 `undefined` 即可。
  if (resp.status === 204) return undefined as T;
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

/** TR6／TR4（#91／#92）：垃圾桶畫面用——後端 `include_archived=true`
 *  回傳全部劇本，這裡篩出已封存者。不新增一個「只回封存者」的後端
 *  端點：清單本身不大，篩選留在前端比多一個查詢參數組合更簡單。 */
export async function listArchivedScenarios(): Promise<ScenarioSummary[]> {
  const all = await request<ScenarioSummary[]>(
    "/api/scenarios?include_archived=true");
  return all.filter((s) => s.archived_at !== null);
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

/** TR2（#89）：垃圾桶單筆還原。批量走既有序列佇列模式（比照批次
 *  刷新／TR6 批次移入垃圾桶），對選中的每個劇本各呼叫一次這個函式，
 *  不是另一個批次端點。 */
export function restoreScenario(id: string): Promise<{ restored: boolean }> {
  return request<{ restored: boolean }>(
    `/api/scenarios/${encodeURIComponent(id)}/restore`,
    { method: "POST" },
  );
}

/**
 * TR3（#90）：垃圾桶單筆永久刪除——連同 results／snapshots／events 一併
 * cascade 清除，不是軟刪除。後端安全閘門只允許刪除已封存的劇本（未封存
 * 回 409），呼叫端（TR4／#92）在此之前一定要先經過二次確認畫面，不能
 * 讓使用者一鍵誤刪。批量同 `restoreScenario`，前端序列佇列逐一呼叫。
 */
export function deleteScenario(id: string): Promise<void> {
  return request<void>(`/api/scenarios/${encodeURIComponent(id)}`,
    { method: "DELETE" });
}

/** V8（#56）：原始資料表（當次快照）的合約列——逐筆合約完整原樣，
 *  不是候選腿的精簡子集，欄位跟 CSV 下載一致。 */
export interface RawContract {
  contract_symbol: string;
  option_type: string;
  strike: number;
  expiry: string;
  bid: number | null;
  ask: number | null;
  last: number | null;
  volume: number;
  open_interest: number;
  implied_volatility: number | null;
}

export interface RawSnapshotMeta {
  symbol: string;
  spot: number;
  fetched_at: string;
  source: string;
  contract_count: number;
}

export interface RawSnapshot {
  meta: RawSnapshotMeta;
  contracts: RawContract[];
}

/** 原始資料表用（V8／#56）：跟著劇本最新一次分析走，沒分析過時 404。 */
export function getRawData(id: string): Promise<RawSnapshot> {
  return request<RawSnapshot>(
    `/api/scenarios/${encodeURIComponent(id)}/raw-data`);
}

/**
 * CSV 下載連結——純 GET＋`Content-Disposition: attachment`，直接當
 * `<a href>` 用，不需要額外的 JS 下載邏輯。
 *
 * `analyzedAt` 帶了就附成快取破壞參數（#69）：這是一個靜態連結，不像
 * `getRawData()` 走 React state 控制的 fetch——換一輪新分析之後，同一個
 * URL 若被瀏覽器的 HTTP 快取命中，點下去會原樣吐回上一輪的舊 CSV，
 * React 這邊完全不知情、也管不到。網址本身跟著分析換掉，快取自然
 * 命中不了。後端不認得這個參數、也不必認得——純粹只是換一個 URL。
 */
export function rawDataCsvUrl(id: string, analyzedAt?: string | null): string {
  const base = `/api/scenarios/${encodeURIComponent(id)}/raw-data.csv`;
  return analyzedAt ? `${base}?t=${encodeURIComponent(analyzedAt)}` : base;
}

/**
 * V9（#57，T11／#25 既有語意）：一個 Spread 身份鍵（`candidate_key`）
 * 跨這個劇本全部歷史結果的淨成本時間序列。缺席快照如實回傳斷點
 * （`cost` 等三欄為 null），不插值、不跳過。
 */
export interface HistoryEntry {
  analyzed_at: string;
  spot: number;
  cost: number | null;
  baseline_return: number | null;
  rank_in_expiry: number | null;
}

export function getSpreadHistory(
  id: string, candidateKey: string,
): Promise<{ entries: HistoryEntry[] }> {
  return request<{ entries: HistoryEntry[] }>(
    `/api/scenarios/${encodeURIComponent(id)}/history` +
    `?candidate_key=${encodeURIComponent(candidateKey)}`);
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

// ---------- 設定：資料源與 Provider credential（Settings／#124） ----------

/** 使用者可選的自訂資料源。清單由後端白名單給（`api_app/providers.py`），
 *  前端不自己維護一份——兩邊各記一份遲早會對不上。 */
export interface ProviderOption {
  id: string;
  label: string;
}

/** `Data / API` 其中一列的現況。`default_label` 是「預設」那顆選項要顯示
 *  什麼（Market Data 是 Cboe、Historical IV 是「無」），由後端給。 */
export interface UsageView {
  mode: "default" | "custom";
  provider: string | null;
  default_label: string;
}

/** 某個 Provider 的 credential 狀態。**沒有完整 token 這個欄位**——後端
 *  只給遮罩形式，這是 #124 的硬性紅線。 */
/** 測試連線的三態（#125）——外加「有 token 但還沒測過」。
 *  刻意不把沒測過當成已連線：那是在替使用者宣稱一件沒驗證過的事。 */
export type CredentialState = "unset" | "unverified" | "ok" | "failed";

export interface CredentialStatus {
  configured: boolean;
  masked: string | null;
  updated_at: string | null;
  status: CredentialState;
  /** 失敗原因，給人看的整句話。成功或未測時為 null。 */
  reason: string | null;
  checked_at: string | null;
}

/** Market Data 這一列實際生效的來源（#125）。`fallback` 為真時
 *  `reason` 說明為什麼用的不是使用者選的那家——不靜默退回。 */
export interface EffectiveSource {
  source: string;
  fallback: boolean;
  reason: string | null;
}

export interface SettingsView {
  supported_providers: ProviderOption[];
  market_data: UsageView;
  historical_iv: UsageView;
  /** key ＝ provider id，不是資料用途——兩列選同一個 Provider 時看到的
   *  是同一筆，使用者因此不必輸入同一把 token 兩次。 */
  credentials: Record<string, CredentialStatus>;
  market_data_effective: EffectiveSource;
  updated_at: string | null;
}

/** 送出時只需要模式與 provider，`default_label` 是後端給的顯示用資訊。 */
export interface UsageChoice {
  mode: "default" | "custom";
  provider: string | null;
}

export function getSettings(): Promise<SettingsView> {
  return request<SettingsView>("/api/settings");
}

export function saveSettings(body: {
  market_data: UsageChoice;
  historical_iv: UsageChoice;
}): Promise<SettingsView> {
  return request<SettingsView>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function saveCredential(
  provider: string,
  token: string,
): Promise<SettingsView> {
  return request<SettingsView>(
    `/api/settings/credentials/${encodeURIComponent(provider)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    },
  );
}

/** 測試連線（#125）：驗證失敗仍是 200——「這把 token 不能用」是預期內的
 *  答案，狀態在回傳的 view 裡，不必為了讀它去 catch。 */
export function testCredential(provider: string): Promise<SettingsView> {
  return request<SettingsView>(
    `/api/settings/credentials/${encodeURIComponent(provider)}/test`,
    { method: "POST" },
  );
}

export function clearCredential(provider: string): Promise<SettingsView> {
  return request<SettingsView>(
    `/api/settings/credentials/${encodeURIComponent(provider)}`,
    { method: "DELETE" },
  );
}
