/**
 * IV 相對位置一年走勢圖的純函式（#140／spec #137）。
 *
 * y 軸／x 軸座標換算與缺值斷點——沿用 Spread 淨成本走勢圖
 * （`./spreadHistory`）建立的既有模式：手刻 SVG、缺值斷線不插值、y 軸
 * 固定不隨互動改變。`contiguousRuns`／`xAxisTicks` 兩個純幾何函式只吃
 * 通用的 `{x, y, label}` 形狀、跟資料語意無關，直接沿用那邊的實作，
 * 不重寫第二份。
 *
 * 與 Spread 淨成本走勢圖的差異：這裡的量（vol 點、無因次 skew）不是
 * 價格，固定 ±15% 沒有意義——改用序列自身的 min／max 各留 10% 邊界；
 * 全同值時給一個以該值為中心的小範圍，避免除以零把圖畫成一條無意義
 * 的水平線貼著邊界。
 */
import { contiguousRuns, xAxisTicks, type AxisTick,
        type ChartPoint } from "./spreadHistory";

export { contiguousRuns, xAxisTicks };
export type { AxisTick, ChartPoint };

/**
 * y 軸固定範圍：序列非空值的 min／max 各留 10% 邊界。全同值時範圍會
 * 塌成一個點——退回一個以該值為中心、寬度取值本身 10%（至少 0.01，
 * 避免值恰好是 0 時範圍也跟著塌成 0）的小範圍，讓那條水平線至少畫在
 * 圖的中間而不是貼著上或下邊界。空序列（一筆有效值都沒有）回 `null`。
 */
export function ivYAxisDomain(values: (number | null)[]): [number, number] | null {
  const known = values.filter((v): v is number => v !== null);
  if (known.length === 0) return null;
  const min = Math.min(...known);
  const max = Math.max(...known);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.1, 0.01);
    return [min - pad, max + pad];
  }
  const span = max - min;
  const pad = span * 0.1;
  return [min - pad, max + pad];
}

/**
 * 把（日期序列、值序列）換算成畫布座標（0～1 相對座標，SVG 層自己乘上
 * 實際寬高）。缺值（`null`）保留在陣列裡但 `y` 是 `null`——呼叫端據此
 * 把折線在該處斷開，不是把陣列過濾掉導致 x 軸間距跟著跳動（沿用
 * Spread 淨成本走勢圖的既有處置）。
 */
export function ivChartPoints(
  dates: string[], values: (number | null)[], domain: [number, number],
): ChartPoint[] {
  const [lo, hi] = domain;
  const span = hi - lo;
  const n = dates.length;
  return dates.map((d, i) => {
    const v = values[i];
    return {
      x: n <= 1 ? 0.5 : i / (n - 1),
      y: v === null || span === 0 ? null : 1 - (v - lo) / span,
      label: d.slice(0, 10),
    };
  });
}

/**
 * 把一條可能比主日期軸稀疏的序列（例如 moving average 起始端沒有值、
 * 或缺 IV 的日子不會出現在序列裡），投影到共用的 `domainDates`——四條
 * 疊加序列（raw／MA／上界／下界，HIVT-05／#156）用**同一份**日期軸，
 * 才不會各自依自己的長度算 x 位置而在畫面上錯位。`domainDates` 找不到
 * 的日期回 `null`（理論上不會發生：統計序列的日期本該是原始序列的
 * 子集）。
 */
export function projectOntoDomain(
  domainDates: string[],
  series: { date: string; value: number | null }[],
): (number | null)[] {
  const byDate = new Map(series.map((p) => [p.date, p.value]));
  return domainDates.map((d) => byDate.get(d) ?? null);
}

/**
 * Firstrade 風格整張圖 scrubber 的座標數學（需求方 2026-08-22 反饋：
 * 不要用每個 observation 一顆透明命中圓點，改成整張 SVG 是單一
 * pointer／touch 互動介面，依游標／觸點的畫面 X 座標找最近的
 * observation）。純函式、不碰 DOM——呼叫端（`./IvHistory` 的
 * `useChartScrubber`）負責量 `getBoundingClientRect()`、傳進來。
 *
 * 資料點沿 x 軸等距分布（`ivChartPoints`／`chartPoints` 既有假設），
 * 所以「最近的點」等於把游標位置換算成 0～1 的圖表內部座標
 * （扣掉左右留白），再乘上 `(count-1)` 四捨五入——不需要真的掃描逐點
 * 比較距離。
 */
export function nearestIndexForClientX(
  clientX: number,
  rect: { left: number; width: number },
  viewBoxWidth: number,
  padLeft: number,
  padRight: number,
  count: number,
): number | null {
  if (count === 0 || rect.width <= 0) return null;
  // 螢幕像素 → viewBox 內部座標：SVG 用 `width:100%` 縮放，實際渲染
  // 寬度（`rect.width`）跟 viewBox 座標系的比例換算。
  const viewBoxX = ((clientX - rect.left) / rect.width) * viewBoxWidth;
  const plotWidth = viewBoxWidth - padLeft - padRight;
  const frac = plotWidth <= 0 ? 0 : (viewBoxX - padLeft) / plotWidth;
  // 游標移到留白區（軸刻度文字那圈）或圖表外，夾在頭尾——貼著邊緣的
  // 那個資料點，不是「找不到」。
  const clamped = Math.min(1, Math.max(0, frac));
  return Math.round(clamped * (count - 1));
}
