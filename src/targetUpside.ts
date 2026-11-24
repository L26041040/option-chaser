/**
 * V2-05（#407）：目前股價、報價日期與目標漲跌幅的畫面文字——**純格式化**。
 *
 * 數字全是後端原值（`ConsensusItem` 與搜尋結果列 `consensus` 上的
 * `price`…`target_upside_reason`）：股價是股票掃描階段（分析師共識更新）
 * 存下的 Yahoo 報價，不是選擇權搜尋的 spot；目標漲跌幅 =
 * (平均目標價 ÷ 目前股價 − 1) × 100，後端以 Decimal 算好並四捨五入到小數
 * 一位（一半遠離零）。分割基準不一致、股價過舊（超過 3 個交易日）等情況
 * 後端不給數字、只給原因代碼，這裡照原因顯示「—」。
 */
import type { QuoteFields, UpsideReason } from "./api";
import { money } from "./scenarios";

/** 與後端 `api_app/price_quote.py` 的 `STALE_AFTER_TRADING_DAYS` 相同。 */
export const STALE_AFTER_TRADING_DAYS = 3;

export const UPSIDE_REASON_LABELS: Record<UpsideReason, string> = {
  no_price: "尚未取得股價",
  price_stale: `股價過舊（超過 ${STALE_AFTER_TRADING_DAYS} 個交易日）`,
  no_mean: "沒有平均目標價（資料不足）",
  split_mismatch: "分割基準不一致，暫不計算",
};

const missing = (reason: UpsideReason) => `— · ${UPSIDE_REASON_LABELS[reason]}`;

/** 「+20.0%」／「-9.1%」／「0.0%」。 */
export function formatUpside(pct: number): string {
  const text = Math.abs(pct).toFixed(1);
  if (text === "0.0") return "0.0%";
  return `${pct > 0 ? "+" : "-"}${text}%`;
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
