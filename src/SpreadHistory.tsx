/**
 * Spread 淨成本走勢圖（V9／#57）：對齊一般行情網站的日／週／月切換，
 * y 軸固定在序列最高最低價位各 ±15% 的範圍內，不隨互動改變。
 *
 * 跟隨主圖那組候選（`baselineTopCandidate`，QA1-06 既有裁示：主圖就是
 * 主圖），不是另外選一組——這是「這個劇本現在在追蹤的那組 Spread」的
 * 走勢，跟頁面其他區塊講的是同一組候選。單腳候選（`legs.length < 2`）
 * 沒有 Spread 身份鍵可查（T9 附錄A13 既有 MVP 範圍：`all_candidates`
 * 只有價差策略填入），整塊不顯示。
 *
 * 零金融計算：`cost` 是引擎算好的（`spread_cost_history`），這裡只做
 * 降採樣分組與座標換算（`./spreadHistory` 的純函式）。手刻 SVG 折線圖
 * ——本專案沒有裝圖表函式庫（`package.json` 沒有相依），比引入一個
 * 完整圖表庫來畫一條折線更輕；沒有縮放／平移手勢，y 軸固定的驗收
 * 標準因此無從被互動破壞，不是額外做了什麼防護。
 */
import { useState } from "react";

import { getSpreadHistory, type Candidate, type HistoryEntry } from "./api";
import { money } from "./scenarios";
import { chartPoints, contiguousRuns, downsampleHistory, yAxisDomain,
        type Granularity } from "./spreadHistory";

const GRANULARITIES: { key: Granularity; label: string }[] = [
  { key: "day", label: "日" },
  { key: "week", label: "週" },
  { key: "month", label: "月" },
];

const CHART_WIDTH = 320;
const CHART_HEIGHT = 140;
const PAD = 8;

function Chart({ entries }: { entries: HistoryEntry[] }) {
  const domain = yAxisDomain(entries);
  if (domain === null) {
    return <p className="caption">這段期間沒有可畫的資料（全數缺席）。</p>;
  }
  const points = chartPoints(entries, domain);
  const runs = contiguousRuns(points);
  const toPixel = (p: { x: number; y: number }) => ({
    px: PAD + p.x * (CHART_WIDTH - 2 * PAD),
    py: PAD + (p.y as number) * (CHART_HEIGHT - 2 * PAD),
  });

  return (
    <svg
      className="spread-history-chart"
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      role="img"
      aria-label={`淨成本走勢，y 軸範圍 ${money(domain[0])} 至 ${money(domain[1])}`}
    >
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
            return <circle key={p.label} cx={px} cy={py} r={2.5} fill="var(--tint)" />;
          })}
        </g>
      ))}
    </svg>
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

  // 單腳候選沒有 Spread 身份鍵——這一區對它沒有意義（跟 `Catchup`／
  // `PriceLadder` 同樣的邊界判斷）。
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
