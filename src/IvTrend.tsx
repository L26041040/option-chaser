/**
 * Historical IV Trend——逐腿 exact-contract 卡片（HIVT-05／#156，
 * spec #151 §6）。
 *
 * 每隻腳一張卡：Long Call／Put 一張；Vertical Spread 買／賣各一張，
 * 兩張各自獨立正確，絕不合成一條「Spread IV」（spec #151 §2／AC）。
 *
 * 每張卡瘦身後的資訊順序（SIG-02／#173，spec #171）：現值 → 走勢圖
 * （raw + MA + Bollinger bands，帶狀區域視覺淡化）→ percentile → Δ4w →
 * 涵蓋時間與觀測筆數。z-score 文字已搬進 `./IvHistory` 的 Advanced／
 * Diagnostics 收合區，不再是這裡的一項。任何一項統計量不可用（觀測數
 * 低於 `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS`）只有那一項顯示
 * unavailable，不隱藏整張卡（HIVT-03／#154 AC，這裡是它在前端的呈現）。
 *
 * 這裡的卡片沒有自己的 loading／error 狀態，也不各自渲染診斷區塊——
 * `legs` 是 `./IvHistory` 那次 fetch 已經拿到手的資料，固定版位骨架
 * （`CardSkeleton`）與診斷 Copy／展開（`InlineDiagnostics`）掛在
 * `./IvHistory` 卡片層級，一次涵蓋 Normalized Skew 與這裡兩個家族全部
 * 事件，不是每張逐腿卡片各自重複一份 UX（見 `./IvHistory` 檔頭說明）。
 * 這裡只 import 這個元件真正需要的幾何／格式化建置塊
 * （`ChartTooltip`／`toPixel`／版面常數等），原樣複用、不重寫第二份。
 */
import type { IvHistoryLegs, IvTrendStatPoint, LegHistoricalIv } from "./api";
import { BACKFILL_NOTES, ChartTooltip, PAD_BOTTOM, PAD_LEFT,
        PAD_TOP, roundPercentile, tickLabel, toPixel, useChartScrubber,
        valueLabel } from "./IvHistory";
import { contiguousRuns, ivChartPoints, ivYAxisDomain, projectOntoDomain,
        xAxisTicks, type ChartPoint } from "./ivHistoryChart";
import { useIsDesktop } from "./useIsDesktop";

/** 走勢圖固定寬度（viewBox 座標，跟卡片寬度無關——CSS `width:100%` 負責
 *  縮放）。手機版高度明顯壓低（Firstrade 風格的瘦長折線圖，不是肥大的
 *  正方形圖表），桌面維持原本的高度不變——手機優先的瘦身不該連帶改動
 *  桌面既有外觀。`useIsDesktop`（跟 `App.tsx` 的 20/80 版面判斷同一個
 *  斷點）由呼叫端（`IvTrendCard`／`./SpreadSummary`）決定要哪一組高度，
 *  這裡的繪圖幾何本身不關心斷點，純粹照傳入的 `height` 畫圖。 */
export const CHART_WIDTH = 300;
export const LEG_CHART_HEIGHT_DESKTOP = 110;
// 手機再瘦身一輪（需求方 2026-08-22 反饋：整張卡片仍然太高）：68 → 54，
// 落在裁示範圍（約 50–56px）內。桌面常數不動。
export const LEG_CHART_HEIGHT_MOBILE = 54;
export const SPREAD_CHART_HEIGHT_DESKTOP = 130;
// 同上，Spread Gap 圖落在裁示範圍（約 60–64px）內。
export const SPREAD_CHART_HEIGHT_MOBILE = 62;

/** spec #151 §6 逐字原文——固定文案，不是每張卡各自改寫一次。 */
const IV_TREND_CAPTION =
  "比較同一張 option 自己的歷史 IV；僅供歷史位置參考，不代表未來 IV 方向。";

/** PC-01（#199，spec #198）；2026-08-26 真機驗收後改寫為白話句——需求方
 *  反饋原本的技術性說法（「百分位：…高於…多少比例的…觀測」）讀起來還是
 *  不夠直覺。現在直接把「第 N 百分位」翻譯成一句話，把 N 帶進句子裡
 *  （跟旁邊 `percentileCaption()` 顯示的數字是同一個來源、同一種
 *  `Math.round(percentile*100)` 換算，兩處讀到的數字保證一致），不需要
 *  使用者自己在腦中做「百分位＝多少比例」這一步轉換，並保留單日讀數
 *  會隨市場報價波動的提醒，避免被誤讀成系統算錯或「這張合約很貴」。
 *  演算法／裁窗／exact-contract 身份規則本身完全不受影響，純文字改寫。
 *  `./SpreadSummary`、`./IvHistory` 各自有語彙微調過的姊妹函式，三者
 *  事實一致、措辭各自貼合家族語言。 */
export function ivPercentileExplanation(percentile: number | null): string {
  if (percentile === null) return "目前沒有足夠的歷史觀測可以比較。";
  const pct = roundPercentile(percentile);
  return `現在的 IV 比過去一年大約 ${pct}% 的有效歷史觀測都高。單日數字可能隨市場報價波動。`;
}

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
 *  缺席原因）。SIG-02（#173）起搬進 Advanced／Diagnostics 收合區，
 *  不再是逐腿卡片主要區塊的一項——export 給 `./IvHistory` 的 Advanced
 *  區塊使用，計算本身完全未變。 */
export function zscoreCaption(leg: LegHistoricalIv): string {
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
 *  呈現，不是補齊或隱藏）。export 給 `./SpreadSummary`（SIG-03／#174）
 *  的涵蓋揭露小字複用同一套天數→文字換算，不重寫第二份。 */
export function spanLabel(days: number): string {
  if (days <= 0) return "";
  // 週／月的分界用天數本身（< 30 天），不是先湊出月數再看月數是否
  // >= 1——後者在 15–29 天這段會被四捨五入成 1 個月（例如 21 天／3 週
  // 的合約，round(21/30)=1，會被誤報成「近 1 個月」），不是掛牌 3 週
  // 合約使用者看到的真實時間長度（HIVT-07／#158 E2E 撈出的既有 bug，
  // spec #151 story #5／#6 明文要求如實呈現）。
  if (days < 30) {
    const weeks = Math.max(1, Math.round(days / 7));
    return `近 ${weeks} 週`;
  }
  const months = Math.round(days / 30);
  // 同一個道理用在月／年的分界：固定 300 天的門檻會把「11 個月」
  // （約 330 天，未達 `IV_TREND_MAX_HISTORY_DAYS=365`）錯報成「近 1
  // 年」。改成看四捨五入後的月數是否滿 12 個月，跟週／月分界用同一套
  // 「先算出使用者看得懂的單位、再看那個單位是否進位」的邏輯，11 個月
  // 的合約才會真的顯示「近 11 個月」。
  if (months >= 12) return "近 1 年";
  return `近 ${months} 個月`;
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

/** `IvTrendChart` 真正需要讀的欄位——`LegHistoricalIv` 結構上滿足這個
 *  介面（欄位是它的子集），SIG-03（#174）的 Spread IV Gap 也另外組一個
 *  滿足這個形狀的物件餵進來（`points` 把 `gap` 映成 `iv`），兩者共用
 *  同一份繪圖幾何，不重寫第二份。 */
export interface IvTrendChartSeries {
  points: { date: string; iv: number | null }[];
  moving_average: IvTrendStatPoint[];
  bollinger_upper: IvTrendStatPoint[];
  bollinger_lower: IvTrendStatPoint[];
  history_span_days: number;
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
 *
 * `seriesLabel`：aria-label 裡「這是什麼量」的字眼——逐腿卡片講「市場
 * IV」，Spread Summary（SIG-03／#174）講「Spread IV Gap」，圖本身完全
 * 是同一份繪圖邏輯，只有這一個字串不同。
 */
export function IvTrendChart({ leg, width, height, seriesLabel = "市場 IV" }: {
  leg: IvTrendChartSeries;
  width: number;
  height: number;
  seriesLabel?: string;
}) {
  const dates = leg.points.map((p) => p.date);
  const raw = leg.points.map((p) => p.iv);
  const asStatSeries = (s: IvTrendStatPoint[]) =>
    s.map((p) => ({ date: p.date, value: p.value }));
  const ma = projectOntoDomain(dates, asStatSeries(leg.moving_average));
  const upper = projectOntoDomain(dates, asStatSeries(leg.bollinger_upper));
  const lower = projectOntoDomain(dates, asStatSeries(leg.bollinger_lower));

  const domain = ivYAxisDomain([...raw, ...ma, ...upper, ...lower]);
  const rawPts = domain === null ? [] : ivChartPoints(dates, raw, domain);
  const { svgRef, activeIndex, interactionProps } =
    useChartScrubber(rawPts.length, width);
  if (domain === null) return null;

  const maPts = ivChartPoints(dates, ma, domain);
  const upperPts = ivChartPoints(dates, upper, domain);
  const lowerPts = ivChartPoints(dates, lower, domain);

  const rawRuns = contiguousRuns(rawPts);
  const maRuns = contiguousRuns(maPts);
  const bands = bandRuns(upperPts, lowerPts);

  const [lo, hi] = domain;
  const yTicks: [number, number][] = [[0, hi], [0.5, (lo + hi) / 2], [1, lo]];
  const xTicks = xAxisTicks(rawPts);
  const active = activeIndex === null ? null : rawPts[activeIndex];
  const activeValue = activeIndex === null ? null : raw[activeIndex];
  // 跟卡片下方的 `spanCaption` 講同一件事實——掛牌不滿一年的合約，
  // 螢幕報讀者不該聽到跟畫面上文字矛盾的「近 1 年」（HIVT-07／#158 E2E
  // 撈出的既有 bug：這裡原本無論實際涵蓋多長都固定寫死同一句）。
  const spanText = spanLabel(leg.history_span_days) || "涵蓋期間過短";

  return (
    <svg
      ref={svgRef}
      className="iv-trend-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${seriesLabel} 走勢，含移動平均與 Bollinger 帶，${spanText}，` +
        "可用滑鼠移動、觸控拖曳或方向鍵瀏覽逐日數值"}
      {...interactionProps}
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

      {/* 原始市場 IV——主線，不再帶逐點互動熱區：整張 SVG 就是互動介面
          （`./IvHistory` 的 `useChartScrubber`），命中判定不必靠每個
          資料點各自的圓點。 */}
      {rawRuns.map((run, i) => (
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
            <line x1={px} y1={PAD_TOP} x2={px} y2={height - PAD_BOTTOM}
                 className="chart-scrub-line" />
            <circle cx={px} cy={py} r={4} className="chart-point chart-point-active" />
          </>
        );
      })()}

      {active && activeValue !== null && (
        <ChartTooltip point={active} value={activeValue} unit="vol-pts"
                     width={width} height={height} />
      )}
    </svg>
  );
}

/** 一隻腳的瘦身卡片：主要文字只剩四項——現值、完整走勢圖、歷史百分位、
 *  4 週 Δ（SIG-02／#173，spec #171）。z-score 文字已搬進 Advanced／
 *  Diagnostics 收合區（`./IvHistory` 的 `IvAdvanced`），Bollinger 數值
 *  不以文字形式出現在任何地方——走勢圖上的視覺帶狀區域原樣保留，只是
 *  改成視覺淡化（見 `styles.css` 的 `.iv-trend-band`／`.iv-trend-ma-line`）。
 *  `label` 只在 Vertical Spread 才有（「買腿」／「賣腿」）——單腳候選
 *  只有一張卡，不需要標籤區分。
 *
 *  手機再瘦身一輪（需求方 2026-08-22 反饋）：桌面版面（標籤／現值／
 *  百分位／Δ4w 各自一行）完全不動；手機版改成「標籤＋現值合併一行、
 *  百分位＋Δ4w 合併一行」，涵蓋時間小字維持獨立一行不變——文字內容
 *  （沿用既有 `percentileCaption`／`delta4wCaption`／`spanCaption`
 *  的既有措辭與計算，只是排版合併，沒有換一套新詞彙）與資訊量都沒有
 *  減少，只是行數變少。用 `useIsDesktop()` 分流兩套 JSX 而不是純 CSS
 *  重排，因為「兩個既有元素合併成同一行」需要一個共同的 flex 容器，
 *  純 CSS 選不到「把兩個不相鄰 sibling 包進同一行」這件事。 */
function IvTrendCard({ label, leg }: { label?: string; leg: LegHistoricalIv }) {
  const isDesktop = useIsDesktop();
  const height = isDesktop ? LEG_CHART_HEIGHT_DESKTOP : LEG_CHART_HEIGHT_MOBILE;
  const chart = <IvTrendChart leg={leg} width={CHART_WIDTH} height={height} />;
  const backfillNote = leg.status !== "ok" && (
    <p className="caption">{BACKFILL_NOTES[leg.status]}</p>
  );

  if (!isDesktop) {
    return (
      <div className="iv-trend-card">
        <div className="iv-compact-head">
          {label && <span className="row-label iv-trend-card-label">{label}</span>}
          <span className="iv-value-primary">
            {valueLabel(currentIv(leg), "vol-pts")}
          </span>
        </div>
        <p className="caption iv-compact-stats">
          {percentileCaption(leg)}・{delta4wCaption(leg)}
        </p>
        <p className="caption">{ivPercentileExplanation(leg.current_percentile)}</p>
        {chart}
        <p className="caption">{spanCaption(leg)}</p>
        {backfillNote}
      </div>
    );
  }

  // PC-06（#203，spec #198）：桌面版資訊順序對齊手機版——現值 → 百分位
  // → Δ4w → 走勢圖（AC 逐字列出的四項），百分位說明句（PC-01／#199）
  // 緊接在 Δ4w 之後、走勢圖之前，跟手機版「percentile+Δ4w 合併行 →
  // 說明句 → 走勢圖」同一個相對位置；涵蓋時間與 backfill 說明維持在
  // 走勢圖之後（低優先度的頁尾資訊，AC 沒有把它們納入排序範圍）。圖表
  // 資料／scrubber／responsive 高度切換／任何計算或 props 完全不變，
  // 純粹是 JSX 元素順序重排。
  return (
    <div className="iv-trend-card">
      {label && <div className="row-label iv-trend-card-label">{label}</div>}
      <span className="iv-value-primary">
        {valueLabel(currentIv(leg), "vol-pts")}
      </span>
      <p className="caption">{percentileCaption(leg)}</p>
      <p className="caption">{delta4wCaption(leg)}</p>
      <p className="caption">{ivPercentileExplanation(leg.current_percentile)}</p>
      {chart}
      <p className="caption">{spanCaption(leg)}</p>
      {backfillNote}
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
