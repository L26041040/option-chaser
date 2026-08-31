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
  /**
   * T12（#228，Initial V2）：這隻腿的買賣方向——取代「陣列位置＝方向」
   * 的隱性慣例（過去 `legs[0]` 恆是買腿、`legs[1]` 恆是賣腿，前端到處
   * 靠 `const [buy, sell] = candidate.legs` 這樣猜）。三腿以上的候選
   * （Butterfly，T15／#230）陣列位置不再天然對應方向，前端一律讀這個
   * 欄位判斷，不再靠位置。
   */
  side: "buy" | "sell";
  /** 這隻腿的口數。既有兩腿策略恆為 1；Butterfly 中腿為 2（#217 決策 H）。 */
  quantity: number;
}

/**
 * T12（#228，Initial V2）：candidate 的腿位陣列，canonical boundary
 * `1 <= len(legs) <= 4`——型別本身就是這個容量邊界，不是註解裡的一句
 * 提醒。今天實際只會出現 1 或 2 腿（Initial V2 啟用到 3 腿，見 #228）；
 * 4 腿僅為 data-shape 容量，本輪不啟用任何四腿 strategy。
 */
export type CandidateLegs =
  | readonly [Leg]
  | readonly [Leg, Leg]
  | readonly [Leg, Leg, Leg]
  | readonly [Leg, Leg, Leg, Leg];

/**
 * T12（#228，Initial V2）：找出這組腿位陣列裡第一隻符合方向的腿——
 * 取代散在 `expiry.ts`／`scenarios.ts`／`detail.ts`／`AnalysisReport.tsx`
 * 四處各自重複一次的 `.find(leg => leg.side === ...)`（`/code-review`
 * Standards 軸抓到，Rule of Three 已超過）。找不到回 `null`（單腳候選
 * 找賣腿、或未來多買腿候選找「第一個買腿」以外的其他買腿都可能落空），
 * 不是拋錯——沒有這個方向的腿是正常狀態，不是資料錯誤。泛型是因為
 * `Candidate.legs`（`CandidateLegs`，完整 `Leg`）與
 * `RepresentativeCandidate.legs`（`RepresentativeCandidateLeg[]`，
 * 精簡子集）都需要同一個查找邏輯，兩者共通的只有 `side` 這個欄位。
 */
export function findLeg<T extends { side: "buy" | "sell" }>(
  legs: readonly T[], side: "buy" | "sell",
): T | null {
  return legs.find((leg) => leg.side === side) ?? null;
}

/** 代表候選（MVP-v2／#77、#78）：劇本清單卡片要的候選完整身分——只到
 *  「顯示要用」這一層，不是完整的 `Candidate`／`Leg`（報價、IV、量能等
 *  欄位留在詳細頁）。T12（#228，Initial V2）起每一腿帶顯式 `side`，
 *  前端讀這個欄位判斷買賣方向，不再靠陣列位置猜（`[0]`/`[1]` 只是
 *  今天兩腿策略剛好等於 buy/sell 的順序，Butterfly 之後不成立）。
 *
 *  `baseline_return` 與卡片列的 `best_return` 必為同一個數字（後端
 *  `store.best_return` 由這個結構導出，口徑恆等）——前端不重算、只顯示。
 */
export interface RepresentativeCandidateLeg {
  strike: number;
  option_type: string;
  side: "buy" | "sell";
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
  /**
   * T12（#228，Initial V2）：損益兩平的**傳輸格式**——1～2 點的陣列，
   * 容量預留給 Butterfly（T15／#230）未來用。既有四策略恆是單點、
   * 值等於上面的 `breakeven`——這是新增的傳輸容量，不是 `breakeven`
   * 的替代品，本票（T12）不消費它、不新增任何 UI。
   */
  breakeven_points: number[];
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
   * 顯示旗標——僅 Bid/Ask 過寬（`is_spread_wide`）。零成交量都不再
   * 觸發顯示。舊的複合旗標 `quote_warning`（選取閘門用，含 zero_vol／
   * wide_spread 兩項，T04／#220 起 friction 已自 canonical model 退場）
   * 不對外序列化，此契約裡不會出現這個鍵。
   */
  wide_spread_warning: boolean;
  /**
   * FB5-03（#64）：無套利一致性違反——同到期日、同類型的相鄰履約價
   * 報價不單調，疑似陳舊報價。獨立於 `wide_spread_warning`：成因與
   * 嚴重性都不同（配對關係違反，不是單一數值超標），不合併成同一個
   * 布林值。
   */
  monotonicity_warning: boolean;
  legs: CandidateLegs;
  matrix: Matrix;
  /**
   * #115（spec #117 §4）：Crossover 對照——只有 Spread 候選有值；單腿
   * 恆為 `null`（沒有「跟自己比較」的概念）。Spread 候選理論上也可能
   * 是 `null`（買腿報價缺失，結構上不該發生的防禦性 case）——#116 的
   * overlay 必須誠實處理這個缺席狀態，不能假造一條線。
   */
  comparator: Comparator | null;
}

/**
 * T09（#191）：同一個 `Candidate` 過去在 `candidates`／`expiry_best`／
 * `expiry_top10`／`expiry_groups[].rows[]` 四個容器裡各自完整重複一份，
 * 現在集中存在這裡（頂層，鍵＝`candidate_key`，跨策略共用一份——
 * `candidate_key` 本身已含策略前綴，天生不衝突），四個容器改存 key
 * 字串。`CandidateMap`（不叫 `CandidatePool`——那個名字已經是
 * `./CandidatePool` 這個既有元件在用，避免同名混淆）。
 */
export type CandidateMap = Record<string, Candidate>;

export interface ExpiryTop10 {
  expiry: string;
  candidate_keys: string[];
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
  /** 新版型「⑦ 免責聲明」——獨立、不折疊的擴充版本（R1 §4.4.4）。
   *  T04（#188）：`methodology_text`／`report_text` 前端零引用，已從
   *  View payload 移除，型別同步拿掉。 */
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
  /** T09（#191）：完整候選內容的單一來源，見 `CandidateMap` 說明。
   *  可選——舊存的 View（schema_version < 3）沒有這個欄位，`resolveCandidate()`
   *  對此誠實回傳 `null`，不假造內容。 */
  candidate_pool?: CandidateMap;
}

/**
 * 依 key 查出候選的完整內容（T09／#191，取代過去容器裡的內嵌字典）。
 * 舊 schema（沒有 `candidate_pool`，或 key 不在裡面）一律回傳 `null`——
 * 舊存的 View 這幾個位置本就已經不會再產生（下一次刷新就是新 schema），
 * 不值得為了過渡期另外撐一套內嵌解析邏輯。
 */
export function resolveCandidate(
  view: AnalysisView, key: string | undefined,
): Candidate | null {
  if (key === undefined) return null;
  return view.candidate_pool?.[key] ?? null;
}

/**
 * 失敗發生在哪一個環節（後端 `_fail` 的 `stage`，V4／#52）。
 * `null` ＝ 後端沒說（例如 422 之類的驗證錯誤），畫面退回通用說法。
 */
export type FailureStage = "fetch" | "analyze" | "params" | "archived" | null;

const STAGES = ["fetch", "analyze", "params", "archived"] as const;

export class ApiError extends Error {
  readonly stage: FailureStage;
  /** 這次失敗的 request 對得回 Vercel runtime logs 的哪一次
   *  （DG-02／#145）。請求整個失敗、連回應都沒有時仍是 `null`——那種
   *  情況下伺服器端從未產生過 correlation id 可言。 */
  readonly correlationId: string | null;

  constructor(message: string, stage: FailureStage = null,
             correlationId: string | null = null) {
    super(message);
    this.stage = stage;
    this.correlationId = correlationId;
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

/**
 * T03（#187）：合併兩個 `AbortSignal`——任一個先觸發都算數。手寫而非
 * 用 `AbortSignal.any`（2023 年才進主流瀏覽器，jsdom 測試環境與部分
 * 舊版行動瀏覽器都還沒有），這個小函式在所有支援 `AbortController`
 * 的環境都能跑。已經 aborted 的來源直接同步觸發，不必等事件。
 */
function combineSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  const controller = new AbortController();
  const abort = (signal: AbortSignal) => controller.abort(signal.reason);
  if (a.aborted) return a;
  if (b.aborted) return b;
  a.addEventListener("abort", () => abort(a), { once: true });
  b.addEventListener("abort", () => abort(b), { once: true });
  return controller.signal;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    // `init.signal`（呼叫端要求可被中途取消）與既有的逾時 signal
    // 合併——任一個先觸發都算數，兩者不互相取代。
    const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    resp = await fetch(url, {
      ...init,
      signal: init?.signal
        ? combineSignals(init.signal, timeoutSignal)
        : timeoutSignal,
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
    // 每個回應都帶（DG-02／#145，含錯誤回應）——連結不到某次特定失敗
    // 的細節時，這仍是使用者手上唯一能拿去對 Vercel runtime logs 的
    // 東西。`?.`：既有測試大量用簡化的物件字面量假冒 `Response`（省略
    // `headers`），這裡不因此連帶炸掉那些跟 correlation id 無關的測試。
    const correlationId = resp.headers?.get("X-Correlation-Id") ?? null;
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
        throw new ApiError(body.message, stageOf(body.stage), correlationId);
      }
    }
    const message =
      typeof detail === "string" ? detail : `請求失敗（HTTP ${resp.status}）`;
    throw new ApiError(message, null, correlationId);
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

/** 編輯劇本（#132）。**不送 symbol**——標的不可改，後端也沒有那個欄位。 */
export function editScenario(
  id: string,
  draft: CreateScenarioRequest,
): Promise<ScenarioSummary> {
  const { symbol: _ignored, ...thesis } = draft;
  return request<ScenarioSummary>(`/api/scenarios/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(thesis),
  });
}

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

/**
 * 一輪刷新（T08／#196，接上後端 T06／#190＋T07／#193）：批次版的
 * `refreshScenario`，接受一組 id（`null` ＝全部未過期劇本，後端
 * 決定範圍）。成功項帶完整卡片列（與 `refreshScenario` 同形狀），
 * 失敗項沿用既有 `{stage, message}` 失敗分層——跟單一劇本刷新完全
 * 同一套語彙，不是另一套錯誤格式。
 *
 * `remaining` 非空代表 server 端時間預算耗盡、還有劇本沒處理到
 * （T07 的 Continuation）；呼叫端（`App.tsx`）拿它原樣再打一次這個
 * 端點即可接續，直到 `remaining` 為空。
 */
export type RefreshRunResult =
  | { scenario_id: string; ok: true; row: ScenarioSummary }
  | { scenario_id: string; ok: false; stage: FailureStage; message: string };

export interface RefreshRunResponse {
  results: RefreshRunResult[];
  remaining: string[];
}

export function refreshRun(
  scenarioIds: string[] | null,
): Promise<RefreshRunResponse> {
  return request<RefreshRunResponse>(
    "/api/scenarios/refresh-run",
    POST_JSON({ scenario_ids: scenarioIds }),
  );
}

/** 詳細頁用（V5／#53）：整份 view 只有這裡會拖，清單列不帶。 */
export function getScenario(
  id: string,
  signal?: AbortSignal,
): Promise<ScenarioDetail> {
  return request<ScenarioDetail>(
    `/api/scenarios/${encodeURIComponent(id)}`, { signal });
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
  return resolveCandidate(view, group?.candidate_keys[0]);
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
  /** Historical IV 模組解不解鎖（#126）。**由後端算好**——前端不自己
   *  重推這條規則，推兩份遲早漂移，而漂移的後果正好是 AC 禁止的
   *  「畫面以為鎖著、其實已經發了請求」。 */
  historical_iv_enabled: boolean;
  updated_at: string | null;
}

/** 送出時只需要模式與 provider，`default_label` 是後端給的顯示用資訊。 */
export interface UsageChoice {
  mode: "default" | "custom";
  provider: string | null;
}

export function getSettings(signal?: AbortSignal): Promise<SettingsView> {
  return request<SettingsView>("/api/settings", { signal });
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

// ---------- Historical IV 歷史序列（#126／#114，HIVT-02–04／#153–155） ----------

/** Normalized Skew 自己一年走勢圖的一天（HIVT-04／#155：舊 `points` 的
 *  `buy_iv`／`sell_iv`／`atm_iv` 子欄位已隨那三個次要顯示欄位一起移除，
 *  這裡只留 Normalized Skew 自己需要的那一項）。`null`＝那天在可比網格
 *  之外——是斷點，不是零。 */
export interface NormalizedSkewPoint {
  date: string;
  normalized_skew: number | null;
}

/** 只描述**這次 backfill 嘗試**的結果，不代表資料能不能看——那是兩件
 *  事（需求方 2026-08-12 二次修正裁示）。`unset`（provider 未設定）與
 *  `invalid`（credential 驗證失敗）不會走到這裡——那兩種在閘門就 403，
 *  畫面連模組都不渲染（#126 既有行為）。 */
export type IvHistoryStatus = "ok" | "quota" | "vendor";

/** Normalized Skew 這一項的現值／百分位／筆數／Δ4w。
 *
 *  百分位**不設任何 coverage 或樣本數門檻**——只要 `count >= 1` 就給。
 *  `count` 是這個百分位背後有幾筆有效觀測撐著，讓使用者自己判斷這個
 *  數字站不站得住腳，產品不替他下「樣本不足所以不值得看」的判斷。
 *
 *  `percentile` 為 `null` 的**唯一**情況是 `count === 0`——這個欄位完全
 *  沒有可比較的歷史觀測，`value` 此時也是 `null`。
 *
 *  `trend_4w`／`trend_base_count`（#140／spec #137）：Δ4w＝最新觀測減去
 *  約四週前水準（[今天-42天, 今天-21天] 窗內觀測的中位數），純加法欄位。
 *  基準窗內一筆觀測都沒有時 `trend_4w` 為 `null`（`trend_base_count` 隨
 *  之為 0）——跟 `percentile`／`value` 一樣，湊不出來就誠實說沒有，不
 *  外推、不拿別的數字頂替。`trend_base_count` 揭露這個趨勢數字背後有
 *  幾筆觀測撐著，跟 `count` 同精神。 */
export interface IvFieldMetric {
  value: number | null;
  percentile: number | null;
  count: number;
  trend_4w: number | null;
  trend_base_count: number;
}

/**
 * 一筆診斷事件（DG-02／#145）。`context` 是後端已經套過 whitelist
 * redaction 與「丟掉 `None`」的 sanitized dict——前端逐 key 渲染即可，
 * 不必也不該自己再判斷哪些欄位該顯示。
 */
export interface DiagnosticEvent {
  event_id: string;
  correlation_id: string;
  ts: string;
  subsystem: string;
  stage: string;
  severity: "info" | "warning" | "error";
  /** PC-03（#201，spec #198）：獨立於 `severity` 的軸——這件事該不該讓
   *  一般使用者看到。卡片就地展開的 inline diagnostics 依這個欄位決定
   *  要不要顯示；Settings／Diagnostics 頁（工程用介面）繼續完整依
   *  `severity` 列出全部事件，不讀這個欄位。 */
  user_facing: boolean;
  message: string;
  context: Record<string, string | number | boolean>;
}

/** 這次 request 產生的診斷事件（DG-03／#146）——跟資料一起回，前端
 *  不必為了查詳情另猜一次 correlation id。 */
export interface IvHistoryDiagnostics {
  correlation_id: string;
  events: DiagnosticEvent[];
}

/** Exact contract 的身份（HIVT-02／#153，spec #151 §1）——underlying／
 *  expiration／strike／option_type 四項，不同其中任何一項就是不同的
 *  合約，不同的歷史序列。 */
export interface ContractIdentity {
  underlying: string;
  expiration: string;
  strike: number;
  option_type: string;
  contract_symbol: string;
}

/** 這張合約單日的市場 IV。`iv` 為 `null`＝vendor 對這天沒有值（缺席
 *  觀測，不是 0）。`low_confidence`＝這天距到期日少於後端具名門檻
 *  （近到期反解病態，HIVR-08／#167）——純資訊品質標記，這個點依然
 *  在序列裡、依然餵進統計量，不影響 ranking／filtering／candidate
 *  selection。 */
export interface IvTrendPoint {
  date: string;
  iv: number | null;
  low_confidence: boolean;
}

/** 統計量序列上的一天（moving average／Bollinger 上下界，HIVT-03／
 *  #154）。`value` 為 `null`＝那天視窗內觀測數不足
 *  `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS`，回報 unavailable——不是沒有
 *  資料，是這個統計量在那天不成立。 */
export interface IvTrendStatPoint {
  date: string;
  value: number | null;
}

/**
 * 一隻腳（買腿或賣腿）的完整 exact-contract 歷史 IV（HIVT-02／03／
 * #153／#154，spec #151 §4）——原始序列＋統計量套組。
 *
 * `current_percentile`／`current_zscore`／`delta_4w` 個別可能是
 * `null`：percentile 只在完全沒有歷史觀測時才會是 `null`（無最低門檻）；
 * `current_zscore` 在視窗觀測數不足 `IV_TREND_MIN_OBSERVATIONS_FOR_
 * BANDS` 時是 `null`；`delta_4w` 在 `[today-42d, today-21d]` 基準窗內
 * 沒有觀測時是 `null`。三者互不影響彼此，也不影響 `points` 本身。
 */
export interface LegHistoricalIv {
  contract: ContractIdentity;
  points: IvTrendPoint[];
  moving_average: IvTrendStatPoint[];
  bollinger_upper: IvTrendStatPoint[];
  bollinger_lower: IvTrendStatPoint[];
  current_percentile: number | null;
  current_zscore: number | null;
  delta_4w: number | null;
  observation_count: number;
  history_span_days: number;
  lookback_days_config: number;
  status: IvHistoryStatus;
  note: string | null;
}

/** 單腳候選（Long Call／Put）只有 `buy`；Vertical Spread 兩腿都有
 *  （HIVT-02／#153，spec #151 §4：單腳的 `sell` 整個省略這個 key，
 *  不是設成 `null`）。 */
export interface IvHistoryLegs {
  buy: LegHistoricalIv;
  sell?: LegHistoricalIv;
}

/** Spread IV Gap 序列上的一天（SIG-01／#172，spec #171）。命名鎖死
 *  ——`{date, gap}`，不是 `{date, iv}` 也不是 `{date, value}`。`gap`
 *  永遠是 `number`，絕不是 `null`：只有兩腿同一天都有值才會產生這一筆
 *  observation，任一腿缺席那天整筆不存在，不是留一筆 `gap: null`。 */
export interface SpreadGapPoint {
  date: string;
  gap: number;
}

/** `spread_gap.delta_4w_ratio` 的四態 guardrail 狀態（SIG-01／#172）：
 *  `"ok"` 才有非 null 的 `delta_4w_ratio`；其餘三態 `delta_4w_ratio`
 *  恆為 `null`，`delta_4w`（絕對值 vol-point）不受影響、四態都正常
 *  顯示。 */
export type SpreadGapDeltaStatus =
  "ok" | "no_baseline" | "near_zero_base" | "sign_flip";

/**
 * Vertical Spread 候選的 Spread IV Gap 完整資料（SIG-01／#172，spec
 * #171）——Sell 腿 reconstructed IV − Buy 腿 reconstructed IV，只保留
 * 兩腿同一天都有值的觀測。只要候選有賣腿這個 key 就一定存在，即使
 * `observation_count` 是 0（兩腿目前沒有任何重疊有效觀測）——那種情況
 * 下 `points`／`moving_average`／`bollinger_upper`／`bollinger_lower`
 * 是空陣列，`current_percentile`／`delta_4w`／`delta_4w_ratio` 是
 * `null`，`delta_4w_status` 是 `"no_baseline"`，`shared_history_span_
 * days` 是 0——形狀永遠完整，前端據此渲染 unavailable 狀態而不是整段
 * 隱藏（SIG-03／#174）。
 *
 * `points[-1]`（依 date 嚴格遞增排序後的最後一筆）是「目前 IV Gap
 * 現值」的正式資料來源，不是碰巧依賴目前的排序。
 *
 * 跟既有 `LegHistoricalIv` 的刻意契約差異：不含 `current_zscore`；不含
 * `status`／`note`；不含 `rolling_window_days`（施工前最終裁示：前端
 * 不需要讀這個值）；涵蓋時間欄位叫 `shared_history_span_days`，不是
 * `history_span_days`——那個名稱專屬既有 leg 欄位，語意不同，不得混用。
 */
export interface SpreadGap {
  points: SpreadGapPoint[];
  moving_average: IvTrendStatPoint[];
  bollinger_upper: IvTrendStatPoint[];
  bollinger_lower: IvTrendStatPoint[];
  current_percentile: number | null;
  delta_4w: number | null;
  delta_4w_ratio: number | null;
  delta_4w_status: SpreadGapDeltaStatus;
  observation_count: number;
  shared_history_span_days: number;
}

export interface IvHistoryView {
  candidate_key: string;
  status: IvHistoryStatus;
  /** Normalized Skew 自己的一年走勢圖資料（HIVT-04／#155：欄位改名，
   *  子欄位窄化，計算本身完全未變）。 */
  normalized_skew_points: NormalizedSkewPoint[];
  /** HIVT-04（#155）後只剩 `normalized_skew` 一項——買／賣腿的 reanchored
   *  次要顯示已被 `legs` 取代。 */
  metrics: { normalized_skew: IvFieldMetric };
  /** 這個 symbol 已經累積了幾天觀測（progressive backfill 的進度，
   *  Normalized Skew 這條 (tenor,delta) 家族路徑專用）。 */
  observations: number;
  /** 只在 `status` 不是 `ok` 時有值，說明今天的 backfill 遇到什麼——
   *  與要不要顯示 percentile 無關，那從來就只看各欄位自己的 `count`。 */
  note: string | null;
  diagnostics: IvHistoryDiagnostics;
  /** exact-contract 家族（HIVT-02／03／#153／#154）——跟上面的
   *  Normalized Skew 家族資料語意完全獨立。 */
  legs: IvHistoryLegs;
  /** Spread IV Gap（SIG-01／#172）：只要候選有賣腿就一定存在這個 key，
   *  單腳候選整個省略（不是設成 `undefined` 以外的假值）——跟 `legs.
   *  sell` 同一種「key 存在與否即結構性事實」的慣例。 */
  spread_gap?: SpreadGap;
  /** T11（#194，兩段式補建 P3-a）：Legacy (tenor,delta) 家族今天還沒
   *  補建過一批——`true` 時畫面該顯示「歷史資料補建中」並呼叫
   *  `ivHistoryBackfill()`，完成後重打一次這個端點取得補全後的資料。
   *  Exact-Contract 家族（`legs`／`spread_gap`）不受這個欄位影響，
   *  已經是這個回應裡最新的資料。 */
  backfill_pending: boolean;
}

export function ivHistory(
  scenarioId: string,
  candidateKey: string,
  signal?: AbortSignal,
): Promise<IvHistoryView> {
  return request<IvHistoryView>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/iv-history`
    + `?candidate_key=${encodeURIComponent(candidateKey)}`,
    { signal },
  );
}

export interface IvHistoryBackfillResult {
  outcome: string;
  note: string | null;
  diagnostics: IvHistoryDiagnostics;
}

/** T11（#194，兩段式補建 P3-a）：Legacy 家族冷 backfill 的獨立觸發
 *  端點——`ivHistory()` 不再同步跑這件事，只回報 `backfill_pending`。
 *  呼叫這裡完成後，重打一次 `ivHistory()` 就能看到補全後的資料。 */
export function ivHistoryBackfill(
  scenarioId: string,
  candidateKey: string,
  signal?: AbortSignal,
): Promise<IvHistoryBackfillResult> {
  return request<IvHistoryBackfillResult>(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/iv-history/backfill`
    + `?candidate_key=${encodeURIComponent(candidateKey)}`,
    { method: "POST", signal },
  );
}

// ---------- Application diagnostics（DG-02／#145，畫面見 DG-06／#149） ----------

/** 近期診斷事件，最新在最上——沒有 pagination，`limit` 就是能看到的上限。 */
export function getDiagnostics(limit = 50): Promise<DiagnosticEvent[]> {
  return request<DiagnosticEvent[]>(
    `/api/diagnostics?limit=${encodeURIComponent(String(limit))}`);
}

/** 清空，回傳清掉的筆數——呼叫端據此更新畫面，不必再打一次 GET。 */
export function clearDiagnostics(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>("/api/diagnostics", { method: "DELETE" });
}
