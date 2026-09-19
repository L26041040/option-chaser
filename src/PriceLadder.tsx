/**
 * 劇本區間三價位階梯（OG-06／#321，桌面詳細頁中央欄，artifact 板
 * 「三價位階梯」）：最差／目標／最好，讀既有 `Candidate.price_ladder`
 * （V7／#55 早就序列化——目標價恆在其中，兩端只在使用者設定時才出現，
 * 長度 1～3——只是前端直到本票才第一次渲染它，之前一直只顯示原始的
 * `best_price`／`worst_price`／`target_price` 三個獨立 `Stat` 格）。
 *
 * 零金融計算：每一列的價格與對應報酬都是引擎算好的既有欄位，這裡只
 * 排版、不重算。
 */
import type { PricePoint } from "./api";
import { formatReturn, money } from "./scenarios";

const LADDER_LABELS: Record<PricePoint["label"], string> = {
  worst: "最差",
  target: "目標",
  best: "最好",
};

export default function PriceLadder({ points }: { points: PricePoint[] }) {
  // 沒有資料時不畫任何東西——不是空表格，見既有專案慣例（例如
  // `IvHistory` 插槽的「功能上線前不輸出任何 DOM 節點」）。
  if (points.length === 0) return null;
  return (
    <ul className="price-ladder" aria-label="劇本區間三價位">
      {points.map((point) => (
        <li key={point.label} className="price-ladder-row">
          <span className="price-ladder-label">{LADDER_LABELS[point.label]}</span>
          <span className="price-ladder-price">{money(point.price)}</span>
          <span className={point.return >= 0 ? "metric positive" : "metric negative"}>
            {formatReturn(point.return)}
          </span>
        </li>
      ))}
    </ul>
  );
}
