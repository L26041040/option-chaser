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

export interface StrategyResult {
  strategy: string;
  status: string;
  message: string;
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

export class ApiError extends Error {}

export async function analyze(req: AnalyzeRequest): Promise<AnalysisView> {
  const resp = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const detail = await resp
      .json()
      .then((b) => b?.detail)
      .catch(() => null);
    // FastAPI 的驗證錯誤（422）detail 是物件陣列，直接丟進畫面會變成
    // [object Object]；只有字串才拿來當人看的訊息。
    const message =
      typeof detail === "string" ? detail : `分析失敗（HTTP ${resp.status}）`;
    throw new ApiError(message);
  }
  return resp.json();
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
  const ok = view.results.find((r) => r.status === "ok" && r.expiry_top10);
  if (!ok?.expiry_top10) return null;
  const group = ok.expiry_top10.find((g) => g.expiry === view.baseline_expiry);
  return group?.candidates[0] ?? null;
}
