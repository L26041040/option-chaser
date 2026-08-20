/**
 * Spread 淨成本走勢圖（V9／#57，補刻度與 tooltip：MVP V3／#106，
 * spec #102 決策 I）：對齊一般行情網站的日／週／月切換，y 軸固定在
 * 序列最高最低價位各 ±15% 的範圍內，不隨互動改變。
 *
 * 跟隨主圖那組候選（`baselineTopCandidate`，QA1-06 既有裁示：主圖就是
 * 主圖），不是另外選一組——這是「這個劇本現在在追蹤的那組 Spread」的
 * 走勢，跟頁面其他區塊講的是同一組候選。單腳候選（`legs.length < 2`）
 * 沒有 Spread 身份鍵可查（T9 附錄A13 既有 MVP 範圍：`all_candidates`
 * 只有價差策略填入），整塊不顯示。
 *
 * 零金融計算：`cost` 是引擎算好的（`spread_cost_history`），這裡只做
 * 降採樣分組、座標換算與刻度／tooltip 呈現（`./spreadHistory` 的純
 * 函式）。手刻 SVG 折線圖——本專案沒有裝圖表函式庫（`package.json` 沒有
 * 相依），比引入一個完整圖表庫來畫一條折線更輕；沒有縮放／平移手勢，
 * y 軸固定的驗收標準因此無從被互動破壞，不是額外做了什麼防護（#106
 * AC 明文不加 zoom／pan）。
 *
 * 刻度與 tooltip（#106）：Y 軸三個刻度（低／中／高，依 `yAxisDomain`
 * 算出的固定範圍）＋單位標籤；X 軸最多四個日期刻度，均勻取樣涵蓋頭尾。
 * 資料點桌面 `onMouseEnter`／手機 `onClick`（觸控裝置點按會合成 click
 * 事件，不必分別處理 touch）都能觸發同一個 tooltip，內容固定含日期與
 * 淨成本——兩種輸入方式共用同一份狀態與呈現，不是兩套邏輯。
 */
import { useState } from "react";

import { getSpreadHistory, type Candidate, type HistoryEntry } from "./api";
import { money } from "./scenarios";
import { chartPoints, contiguousRuns, xAxisTicks, yAxisDomain,
        downsampleHistory, type ChartPoint, type Granularity } from "./spreadHistory";

const GRANULARITIES: { key: Granularity; label: string }[] = [
  { key: "day", label: "日" },
  { key: "week", label: "週" },
  { key: "month", label: "月" },
];

const CHART_WIDTH = 320;
const CHART_HEIGHT = 160;
const PAD_TOP = 16;
const PAD_RIGHT = 8;
const PAD_BOTTOM = 22;
const PAD_LEFT = 42;
const PLOT_WIDTH = CHART_WIDTH - PAD_LEFT - PAD_RIGHT;
const PLOT_HEIGHT = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM;

function toPixel(p: { x: number; y: number }) {
  return { px: PAD_LEFT + p.x * PLOT_WIDTH, py: PAD_TOP + p.y * PLOT_HEIGHT };
}

function Chart({ entries }: { entries: HistoryEntry[] }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const domain = yAxisDomain(entries);
  if (domain === null) {
    return <p className="caption">這段期間沒有資料。</p>;
  }
  const points = chartPoints(entries, domain);
  const runs = contiguousRuns(points);
  const indexOf = new Map(points.map((p, i) => [p, i]));
  const [lo, hi] = domain;
  const yTicks: [number, number][] = [[0, hi], [0.5, (lo + hi) / 2], [1, lo]];
  const xTicks = xAxisTicks(points);
  const active = activeIndex === null ? null : points[activeIndex];
  const activeCost = activeIndex === null ? null : entries[activeIndex].cost;

  return (
    <svg
      className="spread-history-chart"
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      role="img"
      aria-label={`淨成本走勢，y 軸範圍 ${money(domain[0])} 至 ${money(domain[1])}`}
    >
      {/* Y 軸：單位標籤＋三個刻度（低／中／高，固定範圍，不隨互動變動）。 */}
      <text x={2} y={10} className="chart-axis-unit">Net Cost ($/share)</text>
      {yTicks.map(([frac, value]) => {
        const py = PAD_TOP + frac * PLOT_HEIGHT;
        return (
          <g key={frac}>
            <line x1={PAD_LEFT - 4} y1={py} x2={PAD_LEFT} y2={py} className="chart-tick-mark" />
            <text x={PAD_LEFT - 6} y={py + 3} textAnchor="end" className="chart-tick-label">
              {money(value)}
            </text>
          </g>
        );
      })}

      {/* X 軸：日期刻度，均勻取樣（含首尾），不是每個資料點都印一個。 */}
      {xTicks.map(({ index, label }) => {
        const px = PAD_LEFT + points[index].x * PLOT_WIDTH;
        const bottom = PAD_TOP + PLOT_HEIGHT;
        return (
          <g key={index}>
            <line x1={px} y1={bottom} x2={px} y2={bottom + 4} className="chart-tick-mark" />
            <text x={px} y={CHART_HEIGHT - 4} textAnchor="middle" className="chart-tick-label">
              {label}
            </text>
          </g>
        );
      })}

      {runs.map((run, i) => (
        <g key={i}>
          {/* 每段各自一條折線——段與段之間刻意不連線，斷點如實顯示。 */}
          <polyline
            fill="none"
            stroke="var(--tint)"
            strokeWidth={2}
            points={run.map((p) => {
              const { px, py } = toPixel(p as { x: number; y: number });
              return `${px},${py}`;
            }).join(" ")}
          />
          {run.map((p) => {
            const { px, py } = toPixel(p as { x: number; y: number });
            const idx = indexOf.get(p)!;
            return (
              <circle
                key={p.label}
                cx={px} cy={py} r={5}
                className="chart-point"
                tabIndex={0}
                role="button"
                aria-label={`${p.label}，淨成本 ${money(entries[idx].cost!)}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseLeave={() => setActiveIndex(null)}
                onFocus={() => setActiveIndex(idx)}
                onBlur={() => setActiveIndex(null)}
                // 手機 tap 沒有 hover 狀態，click 是唯一訊號——直接設定
                // 而不是切換：真實觸控會先合成一輪 hover 事件再送出
                // click，切換邏輯在那個當下會誤判成「已經開著、這次點擊
                // 是要關掉」，點了等於沒點。
                onClick={() => setActiveIndex(idx)}
              />
            );
          })}
        </g>
      ))}

      {active && activeCost !== null && (
        <Tooltip point={active} cost={activeCost} />
      )}
    </svg>
  );
}

/** 桌面 hover／手機 tap 共用的同一個 tooltip——固定含日期與淨成本
 *  （#106 AC 逐字要求）。位置貼著資料點，靠左右邊緣時往內收，不出界。 */
function Tooltip({ point, cost }: { point: ChartPoint; cost: number }) {
  const { px, py } = toPixel(point as { x: number; y: number });
  const boxWidth = 96;
  const boxHeight = 34;
  const x = Math.min(Math.max(px - boxWidth / 2, PAD_LEFT), CHART_WIDTH - PAD_RIGHT - boxWidth);
  const y = Math.max(py - boxHeight - 10, 0);
  return (
    <g className="chart-tooltip">
      <rect x={x} y={y} width={boxWidth} height={boxHeight} rx={6} />
      <text x={x + boxWidth / 2} y={y + 14} textAnchor="middle">日期 {point.label}</text>
      <text x={x + boxWidth / 2} y={y + 27} textAnchor="middle">淨成本 {money(cost)}</text>
    </g>
  );
}

export default function SpreadHistory({ scenarioId, candidate }: {
  scenarioId: string;
  candidate: Candidate | null;
}) {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [granularity, setGranularity] = useState<Granularity>("day");

  function onToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || entries || loading || !candidate) return;
    setLoading(true);
    setError(null);
    getSpreadHistory(scenarioId, candidate.candidate_key)
      .then((r) => setEntries(r.entries))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  // 單腳候選沒有 Spread 身份鍵——這一區對它沒有意義（跟 `PriceLadder`
  // 同樣的邊界判斷，#103 之後追平價格區塊已整個移除）。
  if (!candidate || candidate.legs.length < 2) return null;

  const shown = entries ? downsampleHistory(entries, granularity) : null;

  return (
    <details className="card" onToggle={onToggle}>
      <summary className="section-title">Spread 淨成本走勢</summary>

      {loading && <p className="caption">載入中……</p>}
      {error && <p className="notice error">{error}</p>}

      {shown && (
        <>
          <div className="segmented" role="group" aria-label="時間粒度">
            {GRANULARITIES.map((g) => (
              <button
                key={g.key}
                type="button"
                className={g.key === granularity ? "segmented-option selected" : "segmented-option"}
                aria-pressed={g.key === granularity}
                onClick={() => setGranularity(g.key)}
              >
                {g.label}
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <p className="caption">這個劇本還沒有歷史紀錄。</p>
          ) : (
            <Chart entries={shown} />
          )}
        </>
      )}
    </details>
  );
}
