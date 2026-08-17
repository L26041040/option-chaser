/**
 * Historical IV Trend——逐腿 exact-contract 卡片（HIVT-05／#156，
 * spec #151 §6）。
 *
 * 每隻腳一張卡：Long Call／Put 一張；Vertical Spread 買／賣各一張，
 * 兩張各自獨立正確，絕不合成一條「Spread IV」（spec #151 §2／AC）。
 *
 * 每張卡的資訊順序完全比照 spec #151 §6：現值 → 走勢圖（raw + MA +
 * Bollinger bands）→ percentile → z-score → Δ4w → 涵蓋時間與觀測筆數。
 * 任何一項統計量不可用（觀測數低於 `IV_TREND_MIN_OBSERVATIONS_FOR_
 * BANDS`）只有那一項顯示 unavailable，不隱藏整張卡（HIVT-03／#154 AC，
 * 這裡是它在前端的呈現）。
 *
 * 與 `./IvHistory` 的 Normalized Skew 頭條共用同一套 fixed-layout-slot／
 * skeleton／`InlineDiagnostics`／診斷 Copy 行為（原樣 import，見
 * `./IvHistory` 檔頭說明），不另造第二套 UX。
 */
import { useState } from "react";

import type { IvHistoryLegs, IvTrendStatPoint, LegHistoricalIv } from "./api";
import { BACKFILL_NOTES, ChartTooltip, PAD_BOTTOM, PAD_LEFT,
        PAD_TOP, tickLabel, toPixel, valueLabel } from "./IvHistory";
import { contiguousRuns, ivChartPoints, ivYAxisDomain, projectOntoDomain,
        xAxisTicks, type ChartPoint } from "./ivHistoryChart";

/** spec #151 §6 逐字原文——固定文案，不是每張卡各自改寫一次。 */
const IV_TREND_CAPTION =
  "比較同一張 option 自己的歷史 IV；僅供歷史位置參考，不代表未來 IV 方向。";

/** 這隻腳最新一筆非 null 的市場 IV——`points` 的最後一天可能剛好是
 *  null（vendor 對那天沒有值），要找的是「最新一筆有值」，不是「最後
 *  一筆」。 */
function currentIv(leg: LegHistoricalIv): number | null {
  for (let i = leg.points.length - 1; i >= 0; i -= 1) {
    const iv = leg.points[i].iv;
    if (iv !== null) return iv;
  }
  return null;
}

/** 百分位無最低觀測門檻（spec AC14）——`null` 只代表「完全沒有歷史
 *  觀測可比」。 */
function percentileCaption(leg: LegHistoricalIv): string {
  if (leg.current_percentile === null) return "百分位：沒有歷史資料";
  return `第 ${Math.round(leg.current_percentile * 100)} 百分位`;
}

/** z-score 在視窗觀測數不足 `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS`
 *  （後端常數，前端不重複判斷門檻本身）時為 `null`——誠實說觀測數
 *  不足，不是「沒有這個量」（跟 percentile 的「沒有歷史資料」是不同的
 *  缺席原因）。 */
function zscoreCaption(leg: LegHistoricalIv): string {
  if (leg.current_zscore === null) return "Z-score：觀測數不足";
  const sign = leg.current_zscore >= 0 ? "+" : "";
  return `Z-score ${sign}${leg.current_zscore.toFixed(2)}`;
}

/** 帶正負號的 Δ4w，vol 點單位——`null`（基準窗內無觀測）印 em dash，
 *  不外推、不假裝沒有變化。 */
function delta4wCaption(leg: LegHistoricalIv): string {
  if (leg.delta_4w === null) return "4週 —";
  const sign = leg.delta_4w >= 0 ? "+" : "-";
  return `4週 ${sign}${Math.abs(leg.delta_4w * 100).toFixed(1)} pts`;
}

/** 這張合約實際涵蓋多長時間——掛牌不滿一年就照實際天數換算，不是永遠
 *  講「近 1 年」（story #5／#6：掛牌 3 週／5 個月／11 個月都要如實
 *  呈現，不是補齊或隱藏）。 */
function spanLabel(days: number): string {
  if (days <= 0) return "";
  if (days >= 300) return "近 1 年";
  const months = Math.round(days / 30);
  if (months >= 1) return `近 ${months} 個月`;
  const weeks = Math.max(1, Math.round(days / 7));
  return `近 ${weeks} 週`;
}

function spanCaption(leg: LegHistoricalIv): string {
  const span = spanLabel(leg.history_span_days);
  return span
    ? `${span}・${leg.observation_count} 個觀測`
    : `${leg.observation_count} 個觀測`;
}

/** Bollinger 帶的連續片段——`upper`／`lower` 由同一份 rolling window
 *  算出（後端 `ivtrend.bollinger_bands()`），null 的位置天生同步，這裡
 *  仍然逐點檢查兩者都非 null 才算進同一段，不假設這個同步關係一定
 *  成立。 */
function bandRuns(
  upperPts: ChartPoint[], lowerPts: ChartPoint[],
): [ChartPoint, ChartPoint][][] {
  const runs: [ChartPoint, ChartPoint][][] = [];
  let current: [ChartPoint, ChartPoint][] = [];
  for (let i = 0; i < upperPts.length; i += 1) {
    const u = upperPts[i];
    const l = lowerPts[i];
    if (u.y === null || l.y === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push([u, l]);
    }
  }
  if (current.length) runs.push(current);
  return runs;
}

/** 一段 Bollinger 帶片段的填色路徑——上界正向、下界反向，收成一個
 *  封閉多邊形。 */
function bandPathD(
  run: [ChartPoint, ChartPoint][], width: number, height: number,
): string {
  const upperPix = run.map(([u]) => toPixel(u, width, height));
  const lowerPix = [...run].reverse().map(([, l]) => toPixel(l, width, height));
  const forward = upperPix.map(({ px, py }) => `${px},${py}`).join(" L ");
  const backward = lowerPix.map(({ px, py }) => `${px},${py}`).join(" L ");
  return `M ${forward} L ${backward} Z`;
}

/**
 * 四條序列疊在同一個 y-domain 上（raw、moving average、Bollinger
 * 上／下界，spec #151 §6：擴充既有 `ivHistoryChart.ts` 的點映射／
 * y-domain／斷線邏輯，不重寫第二份幾何）。raw 是主線，帶互動點與
 * tooltip；MA 是次要疊加線；Bollinger 帶用半透明填色區域表示範圍，
 * 三者都用 `projectOntoDomain` 投影到 raw 序列的日期軸上，確保 x 座標
 * 對得起來（各序列起訖點數可能不同——MA／帶起始端天然有空窗）。
 *
 * `raw` 全 `null`（`ivYAxisDomain` 回 `null`）時不畫任何東西——跟既有
 * `TrendChart` 同一種「沒有資料就不畫空框」的處置。
 */
function IvTrendChart({ leg, width, height }: {
  leg: LegHistoricalIv;
  width: number;
  height: number;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const dates = leg.points.map((p) => p.date);
  const raw = leg.points.map((p) => p.iv);
  const asStatSeries = (s: IvTrendStatPoint[]) =>
    s.map((p) => ({ date: p.date, value: p.value }));
  const ma = projectOntoDomain(dates, asStatSeries(leg.moving_average));
  const upper = projectOntoDomain(dates, asStatSeries(leg.bollinger_upper));
  const lower = projectOntoDomain(dates, asStatSeries(leg.bollinger_lower));

  const domain = ivYAxisDomain([...raw, ...ma, ...upper, ...lower]);
  if (domain === null) return null;

  const rawPts = ivChartPoints(dates, raw, domain);
  const maPts = ivChartPoints(dates, ma, domain);
  const upperPts = ivChartPoints(dates, upper, domain);
  const lowerPts = ivChartPoints(dates, lower, domain);

  const rawRuns = contiguousRuns(rawPts);
  const maRuns = contiguousRuns(maPts);
  const bands = bandRuns(upperPts, lowerPts);
  const indexOf = new Map(rawPts.map((p, i) => [p, i]));

  const [lo, hi] = domain;
  const yTicks: [number, number][] = [[0, hi], [0.5, (lo + hi) / 2], [1, lo]];
  const xTicks = xAxisTicks(rawPts);
  const active = activeIndex === null ? null : rawPts[activeIndex];
  const activeValue = activeIndex === null ? null : raw[activeIndex];

  return (
    <svg
      className="iv-trend-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="市場 IV 走勢，含移動平均與 Bollinger 帶，近 1 年"
    >
      {yTicks.map(([frac, value]) => {
        const py = PAD_TOP + frac * (height - PAD_TOP - PAD_BOTTOM);
        return (
          <g key={frac}>
            <line x1={PAD_LEFT - 3} y1={py} x2={PAD_LEFT} y2={py}
                 className="chart-tick-mark" />
            <text x={PAD_LEFT - 5} y={py + 3} textAnchor="end"
                 className="chart-tick-label">
              {tickLabel(value, "vol-pts")}
            </text>
          </g>
        );
      })}

      {xTicks.map(({ index, label: dateLabel }) => {
        const { px } = toPixel(rawPts[index], width, height);
        const bottom = height - PAD_BOTTOM;
        return (
          <g key={index}>
            <line x1={px} y1={bottom} x2={px} y2={bottom + 3}
                 className="chart-tick-mark" />
            <text x={px} y={height - 3} textAnchor="middle"
                 className="chart-tick-label">
              {dateLabel}
            </text>
          </g>
        );
      })}

      {/* Bollinger 帶先畫，墊在其他線下面。 */}
      {bands.map((run, i) => (
        <path key={i} d={bandPathD(run, width, height)}
             className="iv-trend-band" />
      ))}

      {/* Moving average——樸素折線，不帶互動點（互動只掛在 raw 上）。 */}
      {maRuns.map((run, i) => (
        <polyline
          key={i}
          fill="none"
          className="iv-trend-ma-line"
          points={run.map((p) => {
            const { px, py } = toPixel(p, width, height);
            return `${px},${py}`;
          }).join(" ")}
        />
      ))}

      {/* 原始市場 IV——主線＋互動點＋tooltip，沿用 Normalized Skew
          走勢圖已驗證的手刻互動作法。 */}
      {rawRuns.map((run, i) => (
        <g key={i}>
          <polyline
            fill="none"
            stroke="var(--tint)"
            strokeWidth={1.5}
            points={run.map((p) => {
              const { px, py } = toPixel(p, width, height);
              return `${px},${py}`;
            }).join(" ")}
          />
          {run.map((p) => {
            const { px, py } = toPixel(p, width, height);
            const idx = indexOf.get(p)!;
            return (
              <circle
                key={idx}
                cx={px} cy={py} r={4}
                className="chart-point"
                tabIndex={0}
                role="button"
                aria-label={`${p.label}，市場 IV ${
                  valueLabel(raw[idx], "vol-pts")}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseLeave={() => setActiveIndex(null)}
                onFocus={() => setActiveIndex(idx)}
                onBlur={() => setActiveIndex(null)}
                onClick={() => setActiveIndex(idx)}
              />
            );
          })}
        </g>
      ))}

      {active && activeValue !== null && (
        <ChartTooltip point={active} value={activeValue} unit="vol-pts"
                     width={width} height={height} />
      )}
    </svg>
  );
}

/** 一隻腳的完整卡片：現值 → 走勢圖 → percentile → z-score → Δ4w →
 *  涵蓋時間＋觀測筆數（spec #151 §6 指定順序）。`label` 只在 Vertical
 *  Spread 才有（「買腿」／「賣腿」）——單腳候選只有一張卡，不需要標籤
 *  區分。 */
function IvTrendCard({ label, leg }: { label?: string; leg: LegHistoricalIv }) {
  return (
    <div className="iv-trend-card">
      {label && <div className="row-label iv-trend-card-label">{label}</div>}
      <span className="iv-value-primary">
        {valueLabel(currentIv(leg), "vol-pts")}
      </span>
      <IvTrendChart leg={leg} width={300} height={110} />
      <p className="caption">{percentileCaption(leg)}</p>
      <p className="caption">{zscoreCaption(leg)}</p>
      <p className="caption">{delta4wCaption(leg)}</p>
      <p className="caption">{spanCaption(leg)}</p>
      {leg.status !== "ok" && (
        <p className="caption">{BACKFILL_NOTES[leg.status]}</p>
      )}
    </div>
  );
}

/**
 * Historical IV Trend 整塊：單腳一張卡（無標籤）；Vertical Spread 兩張
 * （買腿／賣腿，spec #151 §2／AC——各自獨立正確，這裡沒有任何路徑把
 * 兩腿的觀測合成一條序列，`legs.buy`／`legs.sell` 本來就是後端各自
 * fetch 好的兩份獨立資料，前端只是分別渲染）。
 */
export default function IvTrend({ legs }: { legs: IvHistoryLegs }) {
  const hasSell = !!legs.sell;
  return (
    <>
      <div className="iv-trend-legs">
        <IvTrendCard label={hasSell ? "買腿" : undefined} leg={legs.buy} />
        {legs.sell && <IvTrendCard label="賣腿" leg={legs.sell} />}
      </div>
      <p className="caption iv-trend-caption">{IV_TREND_CAPTION}</p>
    </>
  );
}
