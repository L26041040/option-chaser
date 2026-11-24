/**
 * V2-05（#407）：目前股價、報價日期與目標漲跌幅的畫面文字——**純格式化**。
 *
 * 數字全是後端原值（`ConsensusItem` 與搜尋結果列 `consensus` 上的
 * `price`…`target_upside_reason`）：股價是股票掃描階段（分析師共識更新）
 * 存下的 Yahoo 報價，不是選擇權搜尋的 spot；目標漲跌幅 =
 * (平均目標價 ÷ 目前股價 − 1) × 100，後端以 Decimal 算好並四捨五入到小數
 * 一位（一半遠離零）。分割基準不一致、股價過舊（超過 3 個交易日）等情況
 * 後端不給數字、只給原因代碼，這裡照原因顯示「—」。
 *
 * V2-06（#408）：前端只有這一套公式（`targetUpsidePct`）與小數位規則
 * （`roundUpside`），跟後端 `api_app/price_quote.py::target_upside_pct` 讀同一份
 * 案例（`contracts/target_upside_rounding_cases.json`）。畫面顯示的一律是後端的
 * `target_upside_pct`；`targetUpsidePct` 只用來驗證 ⓘ 說明（`metricHelp.ts`）
 * 裡的範例數字跟程式口徑一致。
 */
import type { QuoteFields, UpsideReason } from "./api";
import { money } from "./scenarios";

/** 與後端 `api_app/price_quote.py` 的 `STALE_AFTER_TRADING_DAYS` 相同；兩邊的測試都
 *  比對 `contracts/price_stale_threshold.json`（唯一一份）。 */
export const STALE_AFTER_TRADING_DAYS = 3;

export const UPSIDE_REASON_LABELS: Record<UpsideReason, string> = {
  no_price: "尚未取得股價",
  price_stale: `股價過舊（超過 ${STALE_AFTER_TRADING_DAYS} 個交易日）`,
  no_mean: "沒有平均目標價（資料不足）",
  split_mismatch: "分割基準不一致，暫不計算",
};

const missing = (reason: UpsideReason) => `— · ${UPSIDE_REASON_LABELS[reason]}`;

/**
 * 四捨五入到小數一位，整好一半時遠離零（後端 `ROUND_HALF_UP`），不會有 -0。
 * 先把浮點誤差收掉（12 位有效數字）再進位：(100.05 ÷ 100 − 1) × 100 在浮點是
 * 0.04999…，照 Decimal 口徑應該是整好一半 → 0.1。
 */
export function roundUpside(pct: number): number {
  const tenths = Math.round(Number((Math.abs(pct) * 10).toPrecision(12))) / 10;
  return tenths === 0 ? 0 : Math.sign(pct) * tenths;
}

/** 目標漲跌幅（%）＝(平均目標價 ÷ 目前股價 − 1) × 100，小數位照 `roundUpside`；
 *  缺值或股價 ≤ 0 時 null。 */
export function targetUpsidePct(
  meanTarget: number | null | undefined,
  price: number | null | undefined,
): number | null {
  if (meanTarget == null || price == null || !(price > 0)) return null;
  return roundUpside((meanTarget / price - 1) * 100);
}

/** 「+20.0%」／「-9.1%」／「0.0%」。 */
export function formatUpside(pct: number): string {
  const rounded = roundUpside(pct);
  if (rounded === 0) return "0.0%";
  return `${rounded > 0 ? "+" : "-"}${Math.abs(rounded).toFixed(1)}%`;
}

/** 「2026-11-20 收盤」／「2026-11-24 盤中」。 */
export function priceDateLabel(q: QuoteFields): string {
  return `${q.price_date ?? "—"} ${q.price_kind === "intraday" ? "盤中" : "收盤"}`;
}

/** 目前股價（一律帶報價日期）；沒有股價時「— · 尚未取得股價」。 */
export function priceText(q: QuoteFields): string {
  if (q.price === null || q.price === undefined) return missing("no_price");
  return `${money(q.price)}（${priceDateLabel(q)}）`;
}

/** 目標漲跌幅；不能算時「— · 原因」。 */
export function upsideText(q: QuoteFields): string {
  if (q.target_upside_pct !== null && q.target_upside_pct !== undefined) {
    return formatUpside(q.target_upside_pct);
  }
  return missing(q.target_upside_reason ?? "no_price");
}
