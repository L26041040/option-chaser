/**
 * OG-04（#323）：桌面劇本庫「淨成本走勢」欄——冠軍候選最近幾次刷新的
 * 淨成本序列，純 SVG 手刻（沿用本專案既有慣例，不引圖表函式庫，見
 * `SpreadHistory.tsx` 檔頭同一句話）。跟詳細頁底部完整走勢圖
 * （`DesktopSpreadHistory.tsx`）刻意不同：沒有刻度、沒有 hover
 * tooltip——那是完整走勢圖的職責，這裡只是清單一格裡的縮圖，看得出
 * 「大致方向」就夠了。
 *
 * 手機列不掛這個元件（`CompactScenarioList.tsx` 沒有這一欄，artifact
 * Mobile 劇本庫板本來就沒有這格）。
 *
 * SW-08（#338）`/code-review` Spec 軸跟進：票面 AC「桌面與手機詳細頁
 * heatmap／sparkline 可見且無水平溢出」逐字讀會要求「手機 sparkline」
 * 的 e2e 覆蓋，但這個元件本來就只掛在桌面（上面這段既有裁示），手機
 * 上不存在任何 sparkline 可以測——這裡不是漏補 e2e，是這個資料點在
 * 手機上結構上就不存在，硬湊一個假的手機 sparkline 覆蓋只會是無意義
 * 的測試。既有 `desktop.spec.ts` 已覆蓋桌面 sparkline 可見度，
 * `smoke.spec.ts` 已覆蓋手機 heatmap 無水平溢出，兩個元件×兩個平台
 * 的交集裡唯一有意義的四種組合都已經測過。
 */
import { sparklineDirection, sparklineDots, sparklineRuns,
        type SparklinePoint } from "./sparkline";

const WIDTH = 64;
const HEIGHT = 24;
const PAD_Y = 3;

export default function CostSparkline({ points }: { points: SparklinePoint[] | null }) {
  // `points` 型別上恆非 `undefined`（`ScenarioSummary.cost_sparkline`
  // 是必填欄位），但既有 e2e／舊快取回應仍可能缺這個鍵（尚未跟著這次
  // 後端契約更新）——`!points` 而非嚴格 `=== null` 對兩種情況一視同仁，
  // 誠實顯示「—」而不是讓 `undefined.length` 直接炸掉整張卡片。
  if (!points || points.length === 0) {
    return <span className="lib-cell lib-cell-sparkline muted">—</span>;
  }

  const dots = sparklineDots(points);
  const runs = sparklineRuns(dots);
  const direction = sparklineDirection(points);

  // 全部都是缺席快照（沒有任何一筆有成本可畫）——如實顯示「—」，
  // 不是硬畫一條攤平在中線的假折線。
  if (runs.length === 0) {
    return <span className="lib-cell lib-cell-sparkline muted">—</span>;
  }

  const plotHeight = HEIGHT - PAD_Y * 2;
  const toPixel = (d: { x: number; y: number }) =>
    `${(d.x * WIDTH).toFixed(1)},${(PAD_Y + d.y * plotHeight).toFixed(1)}`;

  return (
    <span className="lib-cell lib-cell-sparkline">
      <svg
        className={`sparkline sparkline-${direction}`}
        width={WIDTH} height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`淨成本走勢，${
          direction === "up" ? "上升" : direction === "down" ? "下降" : "持平"}`}
      >
        {runs.map((run, i) => (
          <polyline
            key={i}
            fill="none"
            strokeWidth={2}
            strokeLinecap="round"
            points={run.map((d) => toPixel(d as { x: number; y: number })).join(" ")}
          />
        ))}
      </svg>
    </span>
  );
}
