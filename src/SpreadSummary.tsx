/**
 * Spread Summary——卡片頭條（SIG-03／#174，spec #171）：把 SIG-01
 * （#172）新增的 `spread_gap` API 區塊接進 SIG-02（#173）留的空版位。
 *
 * 渲染條件是「回應裡有 `spread_gap` 這個 key」，不是「`spread_gap.
 * points` 非空」——呼叫端（`./IvHistory`）只在 `data.spread_gap` 存在
 * 時掛載這個元件；`points` 為空（Vertical Spread 候選但目前沒有共同
 * 有效觀測）時這個元件仍然渲染，以 unavailable 狀態呈現（現值／百分位
 * 顯示「—」／「沒有歷史資料」、Δ4w 顯示「4週 —」、走勢圖不畫空框），
 * 不是整段消失——這是跟「這個候選結構上沒有 Spread 概念」（單腳候選，
 * key 完全不存在）不同的兩種情境。
 *
 * IV Gap 現值：`spread_gap.points`（API 契約保證的遞增排序）取最後
 * 一筆的 `gap`，不是重新掃描找最新非 null——Gap 序列本來就沒有 null
 * 值（SIG-01／#172 契約：任一腿缺席那天整筆不存在），`points[-1]` 是
 * 正式契約保證的現值來源。
 *
 * 走勢圖重用既有 `IvTrendChart` 幾何（`./IvTrend`），不重寫繪圖邏輯——
 * `spread_gap.points` 的 `{date, gap}` 映成 `{date, iv}` 餵進去，其餘
 * （moving_average／bollinger_upper／bollinger_lower／涵蓋天數）欄位
 * 名稱與逐腿卡片的形狀一致，直接傳。
 */
import type { IvHistoryLegs, SpreadGap, SpreadGapDeltaStatus } from "./api";
import { valueLabel } from "./IvHistory";
import { IvTrendChart, spanLabel, type IvTrendChartSeries } from "./IvTrend";

const SPREAD_PERCENTILE_CAPTION =
  "Spread Percentile：目前兩腿 IV 差距，在這兩張 exact contracts 共同"
  + "存在的歷史期間中位於什麼位置。";

/** `points[-1]` 是正式契約保證的現值來源——`points` 為空時沒有現值。 */
function currentGap(spreadGap: SpreadGap): number | null {
  const { points } = spreadGap;
  return points.length ? points[points.length - 1].gap : null;
}

/** Δ4w 絕對值（vol-point）——四種 `delta_4w_status` 下都正常顯示，不受
 *  狀態影響；`null`（`"no_baseline"`）時跟既有逐腿卡片同一種「4週 —」
 *  留白慣例。 */
function delta4wMagnitudeCaption(delta4w: number | null): string {
  if (delta4w === null) return "4週 —";
  const sign = delta4w >= 0 ? "+" : "-";
  return `4週 ${sign}${Math.abs(delta4w * 100).toFixed(1)} pts`;
}

/** guardrail 狀態的 UI 文案——後端只給 machine-readable 的 ratio／
 *  status，這一層決定四種狀態各自怎麼講：`"ok"` 換算成百分比（例如
 *  `+40%`）；`"no_baseline"`／`"near_zero_base"` 顯示「—」；
 *  `"sign_flip"` 顯示「方向翻轉」。 */
function delta4wRatioCaption(ratio: number | null,
                             status: SpreadGapDeltaStatus): string {
  if (status === "ok" && ratio !== null) {
    const pct = Math.round(ratio * 100);
    return `${pct >= 0 ? "+" : ""}${pct}%`;
  }
  if (status === "sign_flip") return "方向翻轉";
  return "—"; // no_baseline／near_zero_base
}

/** 百分位——`null`（沒有歷史觀測可比）時的文案跟既有逐腿卡片
 *  `percentileCaption` 同一種說法，維持一致。 */
function percentileCaption(percentile: number | null): string {
  if (percentile === null) return "百分位：沒有歷史資料";
  return `第 ${Math.round(percentile * 100)} 百分位`;
}

/** 小字涵蓋揭露：買／賣腿各自觀測筆數（既有 `legs.buy/sell.
 *  observation_count`，不變動）＋Gap 重疊筆數（`spread_gap.
 *  observation_count`）＋涵蓋時間（`spread_gap.shared_history_span_
 *  days`，不是既有 leg 專屬的 `history_span_days`——語意不同，不得
 *  混用）。`legs.sell` 在這個元件被掛載時必然存在——後端只在候選有
 *  賣腿時才會回傳 `spread_gap`（SIG-01／#172 契約），這裡直接讀取。 */
function coverageCaption(spreadGap: SpreadGap, legs: IvHistoryLegs): string {
  const sell = legs.sell;
  const sellCount = sell ? sell.observation_count : 0;
  const span = spanLabel(spreadGap.shared_history_span_days);
  const parts = [
    `Buy ${legs.buy.observation_count}`,
    `Sell ${sellCount}`,
    `Shared ${spreadGap.observation_count}`,
  ];
  if (span) parts.push(span);
  return parts.join("・");
}

export default function SpreadSummary({ spreadGap, legs }: {
  spreadGap: SpreadGap;
  legs: IvHistoryLegs;
}) {
  const chartSeries: IvTrendChartSeries = {
    points: spreadGap.points.map((p) => ({ date: p.date, iv: p.gap })),
    moving_average: spreadGap.moving_average,
    bollinger_upper: spreadGap.bollinger_upper,
    bollinger_lower: spreadGap.bollinger_lower,
    history_span_days: spreadGap.shared_history_span_days,
  };

  return (
    <div className="iv-spread-summary">
      <div className="row-label iv-trend-card-label">Spread IV Gap</div>
      <span className="iv-value-primary">
        {valueLabel(currentGap(spreadGap), "vol-pts")}
      </span>
      {spreadGap.points.length > 0 && (
        <IvTrendChart leg={chartSeries} width={300} height={130}
                     seriesLabel="Spread IV Gap" />
      )}
      <p className="caption">{percentileCaption(spreadGap.current_percentile)}</p>
      <p className="caption">{delta4wMagnitudeCaption(spreadGap.delta_4w)}</p>
      <p className="caption">
        {delta4wRatioCaption(spreadGap.delta_4w_ratio, spreadGap.delta_4w_status)}
      </p>
      <p className="caption">{coverageCaption(spreadGap, legs)}</p>
      <p className="caption">{SPREAD_PERCENTILE_CAPTION}</p>
    </div>
  );
}
