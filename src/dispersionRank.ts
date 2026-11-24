/**
 * V2-03（#405）：「分歧度歷史排序」的 PR 顯示與輸入換算——**純前端**。
 *
 * 後端的 midrank 百分位（0–1 比例，`ConsensusItem.percentile`）、第一道門檻
 * 的判斷、Settings 存的 `percentile_max`（原百分位 %，預設 20）與 API 欄位
 * 全都不變；這裡只把它們換成使用者看的 PR：
 *
 * - PR = 100 − 原百分位（%）。原百分位 12% → PR88（前 12%）。
 * - 畫面上的 PR 一律**向下取整**，所以「畫面顯示 ≥ 門檻 ⇒ 後端實際通過」
 *   永遠成立（20.4% → PR 79.6 → 顯示 PR79，不入選）。篩選本身只看後端
 *   未取整的原值，前端不重判。
 * - 取整前加 1e-9（PR 單位）只吸收浮點誤差（0.12 × 100 ≠ 12）；後端的
 *   容差是 1e-9 比例＝1e-7 PR，比這個寬，上面那條性質不受影響。
 * - 設定頁以 PR 輸入門檻，存回 `percentile_max = 100 − PR`：舊值 20 ↔ PR ≥ 80，
 *   新舊前端讀寫同一個欄位、同一個單位。
 */

const FLOAT_SLACK = 1e-9;

/** 去掉 `100 − x` 的浮點雜訊（79.9 而不是 79.89999999999999）。 */
function clean(x: number): number {
  return Number(x.toFixed(10));
}

/** 原百分位（0–1 比例）→ 畫面上的整數 PR（向下取整）。 */
export function prDisplay(percentile: number): number {
  return Math.floor(100 - percentile * 100 + FLOAT_SLACK);
}

/** 「PR88（前 12%）」；沒有百分位（資料不足）時「—」。 */
export function prLabel(percentile: number | null): string {
  if (percentile === null) return "—";
  const pr = prDisplay(percentile);
  return `PR${pr}（前 ${100 - pr}%）`;
}

/** 已存的門檻（原百分位 %）→ PR 門檻值（設定頁輸入框的值）。 */
export function prInputFromPercentileMax(percentileMax: number): number {
  return clean(100 - percentileMax);
}

/** 已存的門檻 → 「PR ≥ 80」。 */
export function prThresholdLabel(percentileMax: number): string {
  return `PR ≥ ${prInputFromPercentileMax(percentileMax)}`;
}

/** 設定頁的 PR 輸入 → 要存的 `percentile_max`。不是數字就原字串照送，
 *  讓後端回它的驗證訊息（與另一道門檻同一套作法）；超出 0–100 的 PR
 *  換算後同樣超出 0–100，也交給後端擋。 */
export function percentileMaxFromPrInput(text: string): number | string {
  const n = Number(text);
  return text.trim() !== "" && Number.isFinite(n) ? clean(100 - n) : text;
}

/** 設定頁 PR 輸入的整數檢查。畫面上的 PR 一律向下取整（`prDisplay()`），門檻
 *  若是小數（例如 79.9），「畫面顯示 ≥ 門檻 ⇔ 實際通過」就不再成立，所以門檻
 *  只收整數。是數字但不是整數時回錯誤訊息；整數（含超出 0–100）、空白與不是
 *  數字的回 `null`，照舊交給後端驗證。存的值仍是 `percentile_max = 100 − PR`。 */
export function prInputError(text: string): string | null {
  const n = Number(text);
  if (text.trim() === "" || !Number.isFinite(n) || Number.isInteger(n)) return null;
  return "分歧度歷史排序門檻：PR 門檻必須是整數（例如 80）";
}

/** 歷史比較的口徑（`lookback_points=60`、`h_min=24`、月底取樣；演算法不在
 *  這裡，只是說明文字）。 */
export const PR_HISTORY_EXPLAINER =
  "分歧度歷史排序：今天的分析師分歧率放進這檔股票自己過去 60 個月的紀錄裡排序（取每月最後一個平日，不含資料日期當天），至少要有 24 個有效月份才排序。PR 越高代表分歧越小、共識越集中；PR88＝前 12%。";
