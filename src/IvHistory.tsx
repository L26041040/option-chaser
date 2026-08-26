/**
 * Historical IV 卡片（#114，資料層見 #126／#130／#133；一年走勢圖為主體
 * ＋Δ4w：#140／spec #137；exact-contract 逐腿卡片：HIVT-02–05／
 * #153–156，spec #151）。
 *
 * 這個檔案現在服務**兩個並存、互不取代**的功能（spec #151 §0）：
 *
 * 1. **Normalized Skew**（(tenor, delta) 逐日重錨定家族，`ivhistory.py`
 *    供應）——只在 Vertical Spread 候選出現，比較買賣兩腳「當下」結構
 *    是否偏斜。維持原樣，完全不受 HIVT 系列影響。
 * 2. **Historical IV Trend**（exact contract 家族，`ivtrend.py` 供應，
 *    `./IvTrend`）——每一隻腳（Long Call／Put 一張；Vertical Spread
 *    買／賣各一張）各自的市場 IV 走勢＋moving average／Bollinger／
 *    z-score／percentile／Δ4w，追蹤的是**這一張、且只有這一張** exact
 *    listed option contract，不是重錨定座標。
 *
 * 舊的買腿 IV／賣腿 IV／ATM IV 次要顯示（reanchored 家族）已在
 * HIVT-04（#155）從後端回應移除，被上面第 2 點的逐腿卡片取代
 * （spec #151 §0 的裁決：畫面不同時出現兩種方法論算出的「這隻腳的
 * IV」，沒有說明是哪一種）。
 *
 * **閘門（#126 AC）**：Historical IV 沒解鎖時，這支元件不輸出任何 DOM
 * 節點，也**不發任何 IV 請求**——不是空卡片、不是「尚未啟用」提示。
 * 解不解鎖讀後端算好的 `historical_iv_enabled`，前端不自己重推規則。
 *
 * **backfill 狀態只是附加說明，不取代資料**：今天補不補得動（quota／
 * vendor）跟資料能不能看是兩件事——已經算出來的 percentile／Δ4w 不因為
 * 今天撞額度就被藏起來，只是額外多一行「今日額度已用完」之類的說明。
 * 兩個家族（Normalized Skew／逐腿 Historical IV Trend）的 backfill 狀態
 * 各自獨立（各自的 `status`／`note`），不是同一個旗標。
 *
 * **只陳述事實**：現值、百分位、觀測筆數、Δ4w、一年走勢圖。不寫「便宜」
 * 「貴」「好進場點」「推薦」——那些都是替使用者做判斷；**也不寫任何
 * 預測語句**（「預期還會再跌」「可能觸底」之類）——facts-only 紅線延伸
 * 涵蓋 forecast，是比評價字眼更嚴格的一種越界。有測試守門，不是靠自律。
 *
 * **enrich-only**：這塊拿掉，每個候選的命運與順序一模一樣（#118 守門）。
 * 它不參與排序、不參與過濾、不影響 baseline 或 Top 10。
 *
 * 零金融計算：`value`／`percentile`／`trend_4w`／`points`／
 * `moving_average`／`bollinger_*`／`current_zscore`／`delta_4w` 全部是
 * 後端算好的，這裡只做座標換算與呈現（`./ivHistoryChart` 的純函式，
 * 沿用 Spread 淨成本走勢圖已驗證的手刻 SVG 作法，不引入圖表函式庫）。
 *
 * **共用建置塊**（HIVT-05／#156，spec #151 §6／§7 明文要求 export）：
 * `ChartTooltip`／`toPixel`／版面常數／格式化函式從這裡 export，
 * `./IvTrend` 的多序列走勢圖直接原樣複用同一套幾何與 tooltip，不是
 * 另外造一份平行實作。`CardSkeleton`／`InlineDiagnostics` 也一併
 * export，但 `./IvTrend` 本身**不需要**再各自 import 一份——這兩者服務
 * 的是「整張卡片」這個版位（loading 骨架、診斷區塊），兩個家族共用
 * 同一次 fetch、同一個 loading／error 狀態，所以固定版位與診斷展開
 * 只在這裡（`IvHistory`／`IvHistoryContent`）出現一次，涵蓋兩個家族
 * 全部的事件，不是每張逐腿卡片各自重複一份。診斷 Copy／展開的 UX
 * 因此仍然是同一套、同一份程式碼（#156 AC），只是掛在卡片層級，不是
 * 逐卡層級。
 */
import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  ivHistoryBackfill,
  type Candidate,
  type DiagnosticEvent,
  type IvFieldMetric,
  type IvHistoryStatus,
  type IvHistoryView,
  type NormalizedSkewPoint,
} from "./api";
import { CopyDiagnosticButton, DiagnosticEventFieldList } from "./DiagnosticDetail";
import { getIvHistoryCached, getSettingsCached, invalidateIvHistoryCache } from "./fetchCache";
import IvTrend, { zscoreCaption } from "./IvTrend";
import { contiguousRuns, ivChartPoints, ivYAxisDomain, nearestIndexForClientX,
        xAxisTicks, type ChartPoint } from "./ivHistoryChart";
import SpreadSummary, { SpreadSummaryAdvanced } from "./SpreadSummary";

/**
 * 今天的 backfill 遇到什麼——一行附加說明，**不取代**下面的 percentile。
 * `unset`／`invalid` 不在這張表：那兩種在閘門就擋掉了，整個模組不渲染。
 */
export const BACKFILL_NOTES: Record<Exclude<IvHistoryStatus, "ok">, string> = {
  quota: "今日 API 額度已用完，將於後續使用時繼續補齊",
  vendor: "資料源暫時無法連線，將於後續使用時繼續補齊",
};

/** 這個欄位的量該用什麼單位呈報——市場 IV／ATM IV 是 vol 點（百分比），
 *  Normalized Skew 無因次，現值與 Δ4w 都印小數（spec #137 §7.5 逐字
 *  範例：`Normalized Skew 0.50 ... 4週 +0.06`，不是 `50% ... +6.0%`）。 */
export type TrendUnit = "vol-pts" | "unitless";

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 現值的呈現——單位隨欄位而定（見 `TrendUnit`）。Normalized Skew 改用
 *  無因次小數而不是既有 `num()` 的百分比格式：跟同一欄位新增的 Δ4w
 *  用同一種語言，避免「現值 8.0% 但變化量 +0.06」這種同一個量卻兩套
 *  單位並列的困惑——這個混淆是新增 Δ4w 才會出現的，不是延續既有行為。 */
export function valueLabel(value: number | null, unit: TrendUnit): string {
  if (value === null) return "—";
  return unit === "vol-pts" ? num(value) : value.toFixed(2);
}

/** 帶正負號的 Δ4w，量自身單位——不是預測，只是「最新減基準」這件事實
 *  的呈報。`trend_4w` 為 `null`（基準窗內無觀測）時印 em dash，不外推、
 *  不假裝沒有變化（那會把「沒有基準可比」跟「比較完發現剛好沒變」
 *  混為一談，兩者是不同的事實）。 */
function trendLabel(m: IvFieldMetric, unit: TrendUnit): string {
  if (m.trend_4w === null) return "4週 —";
  const sign = m.trend_4w >= 0 ? "+" : "-";
  const magnitude = unit === "vol-pts"
    ? `${Math.abs(m.trend_4w * 100).toFixed(1)} pts`
    : Math.abs(m.trend_4w).toFixed(2);
  return `4週 ${sign}${magnitude}`;
}

/**
 * 百分位＋觀測筆數＋Δ4w 的複合標籤——這是需求方要求的「揭露 percentile
 * 建立在多少筆觀測上」的具體呈現，跟著現值一起讀，不必另外點開什麼。
 * `count === 0`（唯一容許沒有百分位的情況）時誠實說沒有歷史資料，
 * **不是**判斷「資料不夠可信」——那個判斷留給使用者自己做。
 */
function metricCaption(m: IvFieldMetric, unit: TrendUnit): string {
  if (m.count === 0 || m.percentile === null) return "沒有歷史資料";
  return `第 ${Math.round(m.percentile * 100)} 百分位・${m.count} 筆觀測・${
    trendLabel(m, unit)}`;
}

/** PC-01（#199，spec #198）：跟 `./IvTrend`／`./SpreadSummary` 的姊妹
 *  常數同一個目的——講清楚百分位的定義＋提醒單日讀數會隨市場報價波動。
 *  Normalized Skew 沿用既有「偏斜」語彙、不硬套「IV」字樣（這個家族量
 *  的是買賣兩腳結構是否偏斜，不是單一 IV 水準）。 */
export const SKEW_PERCENTILE_EXPLANATION =
  "百分位：目前偏斜程度高於近一年內多少比例的有效歷史觀測；單日讀數可能隨市場報價而波動。";

export const PAD_TOP = 12;
export const PAD_RIGHT = 6;
export const PAD_BOTTOM = 16;
export const PAD_LEFT = 34;

/** `y` 容許 `null`（X 軸刻度只需要 `px`，那個呼叫端不保證 `y` 非空）
 *  ——呼叫端若真的需要 `py` 一定是從 `runs`（已篩掉 `null` 的片段）
 *  取來的點，`y` 屆時已經是 `number`。 */
export function toPixel(p: { x: number; y: number | null }, width: number,
                        height: number) {
  const plotWidth = width - PAD_LEFT - PAD_RIGHT;
  const plotHeight = height - PAD_TOP - PAD_BOTTOM;
  return { px: PAD_LEFT + p.x * plotWidth,
          py: PAD_TOP + (p.y ?? 0) * plotHeight };
}

/** 這個欄位一年走勢圖的 y 軸刻度怎麼寫成文字——沿用現值同一套單位，
 *  刻度與現值講同一種語言，不會讓人在同一張圖裡看到兩套不一致的數字。 */
export function tickLabel(value: number, unit: TrendUnit): string {
  return unit === "vol-pts" ? num(value) : value.toFixed(2);
}

/**
 * Firstrade 風格整張圖 scrubber（需求方 2026-08-22 反饋）：原本每個
 * observation 各自一顆透明命中圓點（外加 `tabIndex=0 role=button`，
 * 一年走勢圖動輒兩三百個焦點停駐點），改成整張 SVG 是單一
 * pointer／touch／keyboard 互動介面，依游標／觸點的畫面 X 座標找最近
 * 的 observation——座標數學是 `./ivHistoryChart` 的純函式
 * `nearestIndexForClientX`，這裡只是接 DOM 事件、量
 * `getBoundingClientRect()`、把結果餵進 `activeIndex` 狀態。
 * `./IvTrend` 的 `IvTrendChart` 原樣複用，不重寫第二份。
 *
 * 桌面滑鼠：`pointermove` 對滑鼠本來就在懸停時連續觸發，不需要按住
 * 就能連續 scrub，移出圖表（`pointerleave`）才清掉。手機觸控：
 * `pointerdown` 起手（單純點一下就直接顯示那個點，不必先拖曳）＋
 * `setPointerCapture`（環境不支援——包含測試用的 jsdom——就靜默跳過，
 * 不影響其餘互動）讓手指拖過去時 `pointermove` 依然持續送達同一個
 * SVG，貼合手指移動。**放開手指（`pointerup`）刻意不清除**——觸控沒有
 * 「移出」這個中間狀態，鬆開手指是唯一的訊號，若鬆開就清掉，畫面會
 * 在單純點一下（down→up 幾乎同時發生）的當下就把剛顯示的 marker／
 * tooltip 立刻擦掉，使用者根本來不及看到，等於整個 tap-to-view 失效；
 * 沿用舊版「tap 直接設定、維持到下一次互動」的既有行為。只有
 * `pointercancel`（互動被系統手勢等中斷）才清除，因為那代表這次
 * 互動整個作廢，不是使用者選定了一個點。鍵盤：SVG 本身可 focus（一個
 * 容器一個 tab stop，取代原本「每個資料點各自一個 tabIndex」），方向
 * 鍵左右移動 `activeIndex`，Escape／失焦清除——鍵盤使用者不會因為這次
 * 改版失去逐點瀏覽的能力，只是入口從兩三百個變成一個。
 */
export function useChartScrubber(pointCount: number, viewBoxWidth: number) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const setFromClientX = (clientX: number) => {
    const svg = svgRef.current;
    if (!svg || pointCount === 0) return;
    const rect = svg.getBoundingClientRect();
    const idx = nearestIndexForClientX(
      clientX, rect, viewBoxWidth, PAD_LEFT, PAD_RIGHT, pointCount);
    if (idx !== null) setActiveIndex(idx);
  };

  const clear = () => setActiveIndex(null);
  const releaseCapture = (e: React.PointerEvent<SVGSVGElement>) => {
    const target = e.currentTarget;
    if (typeof target.releasePointerCapture === "function") {
      try { target.releasePointerCapture(e.pointerId); } catch { /* 環境不支援就算了 */ }
    }
  };

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    setFromClientX(e.clientX);
    const target = e.currentTarget;
    if (typeof target.setPointerCapture === "function") {
      try { target.setPointerCapture(e.pointerId); } catch { /* 環境不支援就算了 */ }
    }
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    setFromClientX(e.clientX);
  };
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    releaseCapture(e);
  };
  const onPointerCancel = (e: React.PointerEvent<SVGSVGElement>) => {
    releaseCapture(e);
    clear();
  };
  const onKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    if (pointCount === 0) return;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(pointCount - 1, (i ?? -1) + 1));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, (i ?? pointCount) - 1));
    } else if (e.key === "Escape") {
      clear();
    }
  };

  return {
    svgRef,
    activeIndex,
    interactionProps: {
      tabIndex: 0,
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
      onPointerLeave: clear,
      onKeyDown,
      onBlur: clear,
    },
  };
}

/**
 * 一年走勢圖——取代原本 18px 的 sparkline，成為這一區塊的主要視覺
 * （#140／spec #137：percentile 給位置、圖給路徑、Δ4w 給最近速度，
 * 三者互補）。y 軸固定域不隨互動改變；x 軸日期刻度均勻取樣涵蓋頭尾；
 * 缺值斷線不插值；tooltip 桌面 hover／手機 tap 共用同一套狀態（沿用
 * Spread 淨成本走勢圖 #106 已驗證的手刻 SVG 作法，不引入圖表函式庫，
 * 不加 zoom／pan——y 軸固定的驗收標準因此無從被互動破壞）。
 *
 * `points` 全 `null`（`ivYAxisDomain` 回 `null`）時不畫任何東西——呼叫
 * 端的「沒有歷史資料」文案已經交代過這個狀態，不需要一個空白的圖表
 * 外框重複說一次同一件事。
 *
 * 只服務 Normalized Skew（單一序列）——`./IvTrend` 的四序列疊加圖是
 * 不同的幾何需求，另外實作，不硬套這個單序列版本。
 */
function TrendChart({ label, unit, points, width, height }: {
  label: string;
  unit: TrendUnit;
  points: { date: string; value: number | null }[];
  width: number;
  height: number;
}) {
  const values = points.map((p) => p.value);
  const domain = ivYAxisDomain(values);
  const chartPts = domain === null ? [] : ivChartPoints(
    points.map((p) => p.date), values, domain);
  const { svgRef, activeIndex, interactionProps } =
    useChartScrubber(chartPts.length, width);
  if (domain === null) return null;

  const runs = contiguousRuns(chartPts);
  const [lo, hi] = domain;
  const yTicks: [number, number][] = [[0, hi], [0.5, (lo + hi) / 2], [1, lo]];
  const xTicks = xAxisTicks(chartPts);
  const active = activeIndex === null ? null : chartPts[activeIndex];
  const activeValue = activeIndex === null ? null : values[activeIndex];

  return (
    <svg
      ref={svgRef}
      className="iv-trend-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${label}走勢，近 1 年，可用滑鼠移動、觸控拖曳或方向鍵瀏覽逐日數值`}
      {...interactionProps}
    >
      {/* Y 軸：三個刻度（低／中／高，固定範圍，不隨互動變動），單位隨
          欄位而定，與現值同一套語言。 */}
      {yTicks.map(([frac, value]) => {
        const py = PAD_TOP + frac * (height - PAD_TOP - PAD_BOTTOM);
        return (
          <g key={frac}>
            <line x1={PAD_LEFT - 3} y1={py} x2={PAD_LEFT} y2={py}
                 className="chart-tick-mark" />
            <text x={PAD_LEFT - 5} y={py + 3} textAnchor="end"
                 className="chart-tick-label">
              {tickLabel(value, unit)}
            </text>
          </g>
        );
      })}

      {/* X 軸：日期刻度，均勻取樣（含首尾），不是每個資料點都印一個。 */}
      {xTicks.map(({ index, label: dateLabel }) => {
        const { px } = toPixel(chartPts[index], width, height);
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

      {/* 每段各自一條折線——段與段之間刻意不連線，斷點如實顯示，不畫成
          連續、也不畫成 0。折線本身不再帶任何逐點互動熱區——整張 SVG
          就是互動介面（見上方 `useChartScrubber`），命中判定不必靠
          每個資料點各自的圓點。 */}
      {runs.map((run, i) => (
        <polyline
          key={i}
          fill="none"
          stroke="var(--tint)"
          strokeWidth={1.5}
          points={run.map((p) => {
            const { px, py } = toPixel(p, width, height);
            return `${px},${py}`;
          }).join(" ")}
        />
      ))}

      {active && activeValue !== null && (() => {
        const { px, py } = toPixel(active, width, height);
        return (
          <>
            {/* 貼著游標／觸點的垂直參考線——沿著它從資料點對回 X 軸日期
                刻度，Firstrade 一類走勢圖 scrubber 的標準視覺。 */}
            <line x1={px} y1={PAD_TOP} x2={px} y2={height - PAD_BOTTOM}
                 className="chart-scrub-line" />
            <circle cx={px} cy={py} r={4} className="chart-point chart-point-active" />
          </>
        );
      })()}

      {active && activeValue !== null && (
        <ChartTooltip point={active} value={activeValue} unit={unit}
                     width={width} height={height} />
      )}
    </svg>
  );
}

/** 桌面 hover／手機 tap 共用的同一個 tooltip——固定含日期與這一項的值。
 *  位置貼著資料點，靠左右邊緣時往內收，不出界（沿用 Spread 淨成本走勢
 *  圖既有作法）。export 給 `./IvTrend` 的多序列走勢圖原樣複用。 */
export function ChartTooltip({ point, value, unit, width, height }: {
  point: ChartPoint;
  value: number;
  unit: TrendUnit;
  width: number;
  height: number;
}) {
  const { px, py } = toPixel(point, width, height);
  const boxWidth = 84;
  const boxHeight = 30;
  const x = Math.min(Math.max(px - boxWidth / 2, PAD_LEFT),
                     width - PAD_RIGHT - boxWidth);
  const y = Math.max(py - boxHeight - 8, 0);
  return (
    <g className="chart-tooltip">
      <rect x={x} y={y} width={boxWidth} height={boxHeight} rx={5} />
      <text x={x + boxWidth / 2} y={y + 12} textAnchor="middle">
        {point.label}
      </text>
      <text x={x + boxWidth / 2} y={y + 24} textAnchor="middle">
        {valueLabel(value, unit)}
      </text>
    </g>
  );
}

function normalizedSkewSeries(
  points: NormalizedSkewPoint[],
): { date: string; value: number | null }[] {
  return points.map((p) => ({ date: p.date, value: p.normalized_skew }));
}

/**
 * 一項指標的完整呈現：標籤＋現值＋百分位／筆數／Δ4w 複合標籤＋一年
 * 走勢圖。目前只有 Normalized Skew 這一項還在用（HIVT-04 後買／賣腿／
 * ATM 次要顯示已移除，改由 `./IvTrend` 供應）。
 */
function Metric({ label, metric, points, unit, primary = false, explanation }: {
  label: string;
  metric: IvFieldMetric;
  points: { date: string; value: number | null }[];
  unit: TrendUnit;
  primary?: boolean;
  /** PC-01（#199）：常駐可見的百分位說明，掛在「這一項指標」旁邊——
   *  目前只有 Normalized Skew 這一個呼叫端會傳，選填不影響其他潛在
   *  呼叫端的既有行為（不傳就不渲染這一行，跟今天完全一樣）。 */
  explanation?: string;
}) {
  const width = primary ? 300 : 200;
  const height = primary ? 104 : 60;
  return (
    <div className={primary ? "iv-metric iv-primary" : "iv-metric"}>
      <div className="iv-metric-head">
        <span className="row-label">{label}</span>
        <span className="caption">{metricCaption(metric, unit)}</span>
      </div>
      {explanation && <p className="caption">{explanation}</p>}
      <span className={primary ? "iv-value-primary" : "iv-value"}>
        {valueLabel(metric.value, unit)}
      </span>
      <TrendChart label={label} unit={unit} points={points}
                 width={width} height={height} />
    </div>
  );
}

/**
 * 就地展開的診斷詳情（DG-05／#148，資料層見 #145／#146／#147）：卡片
 * 本身照常存在，這只是多出來的一條精簡狀態，預設收合，點開才看得到
 * 完整內容，再點一次收回去——用 `<details>`／`<summary>`，沿用
 * `AnalysisReport.tsx` 已在用的收合慣例，不必自己寫展開狀態機。
 *
 * **前端零解讀邏輯**：severity／stage／message／context 全是後端已經
 * sanitize 過的字串，這裡只做格式化與呈現，不判斷「這個欄位該不該
 * 顯示」——`context` 裡沒有的 key 本來就不會出現在這裡（DG-02 的
 * redaction 在產生時就把 `None` 拿掉了），天然滿足「只顯示實際存在的
 * 欄位」，不需要前端另外過濾。export 給 `./IvTrend` 原樣複用
 * （HIVT-05／#156，spec #151 §6 明文要求）。
 */
export function InlineDiagnostics({ correlationId, events, message, variant }: {
  correlationId: string | null;
  events: DiagnosticEvent[];
  /** 請求層級的錯誤訊息（catch 到的 `Error.message`）——單腳事件清單
   *  可能是空的（純網路／HTTP 失敗沒有後端 diagnostics 事件可看），但
   *  「一鍵複製這次 inline error 的完整 diagnostics」不該因此就沒東西
   *  可複製，所以連同這句一起放進複製內容（QA 反饋，2026-08-16）。 */
  message?: string;
  /** 這塊診斷內容代表什麼語意（需求方 2026-08-22 反饋：API 200、三張
   *  exact-contract 圖正常時，summary 卻硬寫「資料取得失敗」，使用者
   *  會誤以為主圖壞了）——由呼叫端明講，這裡不猜：
   *  `"failure"`＝主 Historical IV 完全沒有資料可顯示（`IvHistory` 整塊
   *  阻斷錯誤分支），才是真的「取得失敗」；`"info"`＝主資料已經成功
   *  （`IvAdvanced` 掛載的前提就是 `currentData` 存在），這裡只是額外
   *  附帶的 vendor／legacy 警示或錯誤事件，不代表主圖有問題，摘要改用
   *  中性文案，不能讓使用者誤判整塊失敗。 */
  variant: "failure" | "info";
}) {
  const copyText = JSON.stringify(
    { correlation_id: correlationId, message: message ?? null, events },
    null, 2,
  );
  const summaryClass = variant === "failure"
    ? "iv-diagnostics-summary" : "iv-diagnostics-summary iv-diagnostics-summary-info";
  const summaryText = variant === "failure"
    ? "Historical IV 資料取得失敗 · 查看詳情"
    : "Historical IV 診斷資訊 · 查看詳情";
  return (
    <details className="iv-diagnostics">
      <summary className={summaryClass}>
        {summaryText}
      </summary>
      {/* 版面依需求方裁示：錯誤摘要（上面卡片本體那句／summary 本身）
          → Copy 按鈕 → 下方完整 diagnostic details。複製邏輯整套重用
          Settings Diagnostics 已完成的 `CopyDiagnosticButton`，不另外
          做第二套格式（QA 反饋，2026-08-16）。 */}
      <CopyDiagnosticButton text={copyText} label="Copy diagnostics" />
      {correlationId && (
        <p className="caption iv-diagnostics-correlation">
          Correlation ID：{correlationId}
        </p>
      )}
      {events.map((event) => (
        <DiagnosticEventFieldList key={event.event_id} event={event} />
      ))}
    </details>
  );
}

/**
 * Loading 佔位骨架（QA 反饋，2026-08-16；HIVT-05／#156 一併 export，
 * 取代原本模組內私有的 `IvHistorySkeleton`）：版位形狀跟真正內容
 * 同構——Vertical Spread 有 Normalized Skew 頭條區塊＋兩張次層卡片
 * （買／賣腿）；Long Call／Put 單腳沒有頭條、只有一張——資料回來前後
 * 卡片高度不整個跳動。純視覺佔位，不讀秒數、不做進度預測，也不宣稱
 * 任何尚未確定的事。整張卡片（含逐腿卡片的版位）共用同一次 fetch、
 * 同一個 loading 狀態，`./IvTrend` 因此不需要、也沒有自己另一份骨架。
 */
export function CardSkeleton({ isSingleLeg }: { isSingleLeg: boolean }) {
  return (
    <div className="iv-skeleton" role="status" aria-live="polite">
      <span className="sr-only">Historical IV 載入中……</span>
      {!isSingleLeg && (
        <div className="iv-skeleton-block iv-skeleton-primary" aria-hidden="true" />
      )}
      <div className={isSingleLeg ? "iv-legs single" : "iv-legs"} aria-hidden="true">
        <div className="iv-skeleton-block iv-skeleton-secondary" />
        {!isSingleLeg && <div className="iv-skeleton-block iv-skeleton-secondary" />}
      </div>
    </div>
  );
}

export default function IvHistory({ scenarioId, candidate, analyzedAt = null }: {
  scenarioId: string;
  candidate: Candidate | null;
  /** 這個劇本最新一次分析完成的時間戳（`ScenarioDetail` 既有的
   *  `analyzedAt`，跟 `./SpreadHistory`／`./RawData` 同一個來源）——只當
   *  成下面 effect 的觸發訊號，值本身不進畫面。新分析一到、同一個候選
   *  （`key` 不變）也該重新問一次 vendor 才能跟上最新報價；跟 `#69` 那兩
   *  個元件用它強制卸載重掛、把舊 state 沖乾淨不同，這裡刻意保留舊
   *  資料——重新嘗試如果失敗，才有「已有可用 cache」的東西可以退回
   *  顯示（見下方 `currentData` 與 `error` 的優先序）。 */
  analyzedAt?: string | null;
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [data, setData] = useState<IvHistoryView | null>(null);
  // 這份 `data` 是哪一個候選的——切候選時 `key` 立刻變了，但新結果要
  // 等 fetch 回來才會覆蓋，這段空窗期 `dataKey !== key`，畫面據此知道
  // 手上這份資料還不能當成「這個候選」的東西來畫（見下方 `currentData`）。
  const [dataKey, setDataKey] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  // T11（#194，兩段式補建 P3-a）：`backfillTick` 只是拿來讓下面的主
  // fetch effect 在補建完成後重新跑一次（配合 `invalidateIvHistoryCache`
  // 清掉舊快取）——值本身沒有意義，純粹是個觸發訊號。
  const [backfillTick, setBackfillTick] = useState(0);
  const [backfillInFlight, setBackfillInFlight] = useState(false);
  // 同一個 (scenario, candidate) 這個掛載期間只嘗試一次補建——避免
  // POST 本身失敗（例如網路根本打不通，連後端的「今天已經跑過」短路
  // 都沒機會生效）時，`backfill_pending` 永遠是 `true`、每次重抓又
  // 立刻再觸發一次，變成無限重試迴圈。
  const backfillAttempted = useRef<Set<string>>(new Set());

  const key = candidate?.candidate_key ?? null;

  // 先問解不解鎖。鎖著就到此為止——**不發 IV 請求**。T03（#187）：走
  // 快取（settings 是單一全站狀態，鍵固定），跟 Settings 頁自己那次
  // 讀取共用同一份結果，不各自 mount 各抓一次。
  useEffect(() => {
    let alive = true;
    const { promise, release } = getSettingsCached();
    promise
      .then((s) => alive && setEnabled(s.historical_iv_enabled))
      // 設定讀不到時當成鎖著：寧可少顯示一塊 enrichment，也不要在狀態
      // 不明時對 vendor 發請求。
      .catch(() => alive && setEnabled(false));
    return () => {
      alive = false;
      release();
    };
  }, []);

  useEffect(() => {
    if (enabled !== true || !key) return;
    let alive = true;
    // 每次重新嘗試（換候選、或新分析完成後同一個候選要跟著問一次）都
    // 先清掉上一輪的錯誤——這次嘗試還沒有結論，不該讓使用者看到跟這次
    // 請求無關的舊錯誤訊息。`data`／`dataKey` 刻意不在這裡清空：換候選
    // 時 `dataKey === key` 這個判斷式（見下方 render）已經足夠避免「別的
    // 候選的資料被誤認成這個候選的」，同一個候選重新嘗試時則正是要保留
    // 舊資料，讓失敗降級成非阻斷警示而不是整塊消失。
    setError(null);
    const { promise, release } = getIvHistoryCached(scenarioId, key, analyzedAt);
    promise
      .then((v) => {
        if (!alive) return;
        setData(v);
        setDataKey(key);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      });
    return () => {
      alive = false;
      release();
    };
    // `backfillTick` 刻意列進相依陣列：補建完成後靠它讓這個 effect 重新
    // 跑一次，拿到補建後的新資料（配合下面那個 effect 先 invalidate 掉
    // 舊快取，這裡才會真的重抓而不是繼續吃快取裡那份 `backfill_pending`）。
  }, [enabled, key, scenarioId, analyzedAt, backfillTick]);

  // T11（#194，兩段式補建 P3-a）：`GET .../iv-history` 回的
  // `backfill_pending` 說「Legacy 家族今天還沒補過一批」——這裡另外
  // 呼叫 `POST .../iv-history/backfill` 觸發，完成後（不論成功或失敗，
  // 後端的「今天已跑過」短路兩種情況都會記一筆，不會無限重試）invalidate
  // 快取＋重新整份請求一次，讓補全後的資料自動出現，不必使用者手動
  // 重新整理。Exact-Contract 家族（`legs`／`spread_gap`）完全不受影響
  // ——那半資料已經在這次回應裡是最新的。
  useEffect(() => {
    // 這裡是這個元件裡唯一在早退（`enabled !== true || !key`）之前就
    // 需要判斷「這份資料是不是這個候選的」的地方，所以自己重算一次
    // `dataKey === key`——跟下面 render 用的 `currentData` 是同一條
    // 判斷式，只是那個變數宣告在早退之後、這裡的 hooks 呼叫不到它。
    const pendingData = dataKey === key ? data : null;
    if (!pendingData?.backfill_pending || !key) return;
    const attemptKey = `${scenarioId}:${key}`;
    if (backfillAttempted.current.has(attemptKey)) return;
    backfillAttempted.current.add(attemptKey);

    let alive = true;
    setBackfillInFlight(true);
    ivHistoryBackfill(scenarioId, key)
      .catch(() => { /* 失敗也要往下走：仍然重抓一次讓畫面反映最新狀態 */ })
      .finally(() => {
        if (!alive) return;
        setBackfillInFlight(false);
        invalidateIvHistoryCache(scenarioId, key, analyzedAt);
        setBackfillTick((t) => t + 1);
      });
    return () => {
      alive = false;
      // 不論是同一個候選重新觸發（`data`／`dataKey` 更新）還是切到別的
      // 候選，這個 effect 實例都被淘汰了——一律把「補建中」旗標收掉，
      // 避免它卡在 `true` 一路帶到不相干的候選畫面上。若真的是同一個
      // 候選還沒補完就被這個 cleanup 打斷，`backfillAttempted` 已經記過
      // 這個 key，不會重新觸發第二次；使用者頂多提早看不到這句文字，
      // 不會看到錯的候選卡著這句文字。
      setBackfillInFlight(false);
    };
  }, [data, dataKey, key, scenarioId, analyzedAt]);

  // 鎖著、還沒問完、或這個候選根本沒有身份鍵 → 不輸出任何節點（#126
  // AC——這條紅線原封不動，跟下面「卡片固定版位」是兩件事：鎖著時連
  // 卡片外框都不該出現）。`!candidate` 這條分支實務上不會單獨發生
  // （`key` 已經蘊含 `candidate` 存在），寫出來純粹是讓 TS 把下面的
  // `candidate.legs` 收窄成非 null。
  if (enabled !== true || !key || !candidate) return null;

  // 從這裡開始卡片本身固定存在——loading／error／有資料（含「資料是空
  // 的」）三種狀態都在同一個版位裡切換，不再因為請求還沒回來就整塊
  // 消失（QA 反饋，2026-08-16：避免 late layout shift）。「無資料」不是
  // 獨立分支：`count === 0` 由既有 `metricCaption()` 逐項顯示「沒有歷史
  // 資料」，資料物件本身照常存在、卡片照常渲染。
  const isSingleLeg = candidate.legs.length < 2;
  // 只信任屬於「這個候選」的資料——`dataKey` 跟目前的 `key` 對得上才
  // 拿來畫，避免切換候選時畫面短暫誤用上一個候選留下來的舊資料。這個
  // 判斷跟下面「有 cache 就不整塊顯示錯誤」防的是兩件不同的事：這裡防
  // 的是「畫錯候選」，下面防的是「明明有得畫卻整塊消失」。
  const currentData = dataKey === key ? data : null;

  return (
    <section className="card iv-history" aria-label="IV 相對位置">
      <h2 className="section-title">IV 相對位置</h2>

      {currentData ? (
        <>
          {/* 這個候選已經有能看的資料（哪怕是上一輪嘗試留下來的）——
              一次新的嘗試失敗（例如 vendor 一時 404／額度用盡）只降級成
              一條不擋內容的警示，不能讓使用者以為整塊都壞了，三張圖明明
              還畫得出來。真正「這個候選完全沒有資料可退回」才走下面的
              整塊錯誤分支。 */}
          {error && (
            <p className="caption iv-history-stale-warning" role="status">
              ⚠ 最新資料更新失敗，目前顯示先前取得的快取資料：{error.message}
            </p>
          )}
          <IvHistoryContent
            data={currentData}
            isSingleLeg={isSingleLeg}
            backfillInFlight={backfillInFlight}
          />
        </>
      ) : error ? (
        // 這個候選目前真的沒有任何資料可退回顯示，才整塊改成錯誤狀態
        // （#126 AC——卡片本身仍在，只是多一條就地展開的診斷詳情
        // （DG-05／#148），不是整段文字替換掉）。
        <>
          <p className="caption">取不到歷史 IV：{error.message}</p>
          <InlineDiagnostics
            variant="failure"
            correlationId={error instanceof ApiError ? error.correlationId : null}
            events={[]}
            message={error.message}
          />
        </>
      ) : (
        <CardSkeleton isSingleLeg={isSingleLeg} />
      )}
    </section>
  );
}

/**
 * Advanced／Diagnostics 收合區（SIG-02／#173，spec #171）：預設收合，
 * 內容含 z-score 文字說明（逐腿）、Normalized Skew 整組（原封不動搬過來，
 * 計算與呈現細節完全不變）、既有的 inline diagnostics 展開內容——三者
 * 原本散在 `IvHistoryContent` 各處，這裡只是搬 JSX 位置，不改任何一項
 * 的資料來源或算法。單腳候選（`isSingleLeg`）沒有 Normalized Skew，這裡
 * 跟搬移前一樣用同一個判斷式跳過；z-score 文字只讀 `legs`，單腳一樣有。
 */
function IvAdvanced({ data, isSingleLeg, notableEvents }: {
  data: IvHistoryView;
  isSingleLeg: boolean;
  notableEvents: DiagnosticEvent[];
}) {
  return (
    <details className="iv-advanced">
      <summary className="section-title">Advanced／Diagnostics</summary>

      <p className="caption">
        {(data.legs.sell ? "買腿 " : "") + zscoreCaption(data.legs.buy)}
      </p>
      {data.legs.sell && (
        <p className="caption">{`賣腿 ${zscoreCaption(data.legs.sell)}`}</p>
      )}

      {/* Spread IV Gap 的次要文字（Δ4w guardrail ratio＋Spread Percentile
          語意說明句，手機文字瘦身裁示搬出主畫面）——只在候選有賣腿
          （`data.spread_gap` 存在）才有意義，跟 `IvHistoryContent` 掛載
          `./SpreadSummary` 主卡片用同一個判斷式。 */}
      {data.spread_gap && <SpreadSummaryAdvanced spreadGap={data.spread_gap} />}

      {!isSingleLeg && (
        <>
          {/* Normalized Skew 這個家族自己的 backfill 狀態——單腳候選結構
              上沒有 Normalized Skew，這行說明沒有意義，不顯示（逐腿卡片
              有各自的狀態說明，見 `./IvTrend`）。 */}
          {data.status !== "ok" && (
            <p className="caption">{BACKFILL_NOTES[data.status]}</p>
          )}
          <Metric
            primary
            label="Normalized Skew"
            unit="unitless"
            metric={data.metrics.normalized_skew}
            points={normalizedSkewSeries(data.normalized_skew_points)}
            explanation={SKEW_PERCENTILE_EXPLANATION}
          />
          <p className="caption">
            近 1 年 {data.observations} 個觀測，依候選的到期天數與 delta 座標
            逐日重錨定
          </p>
          {/* 方法論註記（#140／spec #137 §7.5）：Δ4w 的定義＋等待進場的
              誠實帳本，兩句事實，不下判斷、不預測。 */}
          <p className="caption">
            4週變化＝與約四週前（21–42 天窗內觀測中位數）之差；等待進場另有
            已知的 theta 成本與標的價格風險，本區塊僅描述 volatility 結構。
          </p>
        </>
      )}

      {notableEvents.length > 0 && (
        <InlineDiagnostics
          variant="info"
          correlationId={data.diagnostics.correlation_id}
          events={notableEvents}
        />
      )}
    </details>
  );
}

/** 有資料時的卡片內容——從 `IvHistory` 拆出來純粹是讓上面那段「四種
 *  狀態同一個版位切換」的分支讀起來一眼看懂，不是新的分層原則。
 *
 *  三層順序（SIG-02／#173＋SIG-03／#174，spec #171）：Spread Summary
 *  （`./SpreadSummary`，只在 `spread_gap` 這個 key 存在時掛載）→
 *  Buy／Sell 逐腿卡片（`./IvTrend`）→ Advanced／Diagnostics 預設收合區
 *  （`IvAdvanced`）。 */
function IvHistoryContent({ data, isSingleLeg, backfillInFlight }: {
  data: IvHistoryView;
  isSingleLeg: boolean;
  /** T11（#194，兩段式補建 P3-a）：這個候選的 Legacy 家族今天觸發了一次
   *  補建、還沒跑完——卡片標一句話讓使用者知道資料還在補齊，不必猜為
   *  什麼 Normalized Skew 那半看起來還沒更新。 */
  backfillInFlight: boolean;
}) {
  // 200 但資料是空的——目前最常見的症狀，只看 HTTP 狀態碼看不出來。
  // `user_facing`（PC-03／#201）是唯一能指出這件事的地方——獨立於
  // `severity` 的第二個維度，回答「這件事該不該讓一般使用者看到」，
  // 不是「這件事有多嚴重」。預設鏡射 severity（warning／error 為
  // true），PC-04 起後端在幾個已知的良性情境（例如兩段式 backfill
  // 進行中的暫時空缺）會顯式覆寫成 false，這裡不需要跟著改一行——
  // 過濾條件本身已經正確表達意圖，覆寫發生在資料源那端。`?.`／`?? []`：
  // `diagnostics` 是後端純加法新增的欄位，這裡不因為回應剛好沒帶它
  // （例如手造的測試假體）就整塊炸掉。這批事件涵蓋 Normalized Skew
  // 與逐腿 Historical IV Trend 兩個家族——兩者共用同一個 per-request
  // 診斷收集層（HIVT-02／#153）。
  const notableEvents = (data.diagnostics?.events ?? []).filter(
    (e) => e.user_facing === true);

  return (
    <>
      {backfillInFlight && (
        <p className="caption iv-history-backfill-pending" role="status">
          歷史資料補建中……
        </p>
      )}
      {/* 渲染條件是「回應裡有 spread_gap 這個 key」，不是「points 非
          空」——單腳候選這個 key 整個不存在，`data.spread_gap &&`
          天然只在有賣腿的候選才掛載；`points` 為空時 `SpreadSummary`
          自己渲染 unavailable 狀態，不是在這裡就被擋掉（SIG-03／
          #174）。 */}
      {data.spread_gap && (
        <SpreadSummary spreadGap={data.spread_gap} legs={data.legs} />
      )}
      <IvTrend legs={data.legs} />
      <IvAdvanced data={data} isSingleLeg={isSingleLeg} notableEvents={notableEvents} />
    </>
  );
}
