/**
 * Heatmap 的純顯示函式（V5／#53）。
 *
 * 這裡沒有金融計算——格子裡的報酬率是引擎算好的（`matrix.cells`），
 * 價格軸的錨點標記也是引擎給的（`matrix.prices` 第二欄）。本檔只決定
 * 「長什麼樣」：配色、格式、標籤文字。與舊 Streamlit 版
 * `webapp/render.py` 的 `cell_color`／`_price_tag` 同一份語意。
 */

/** |報酬率| 小於這個值視為中性（不上色）。沿用既有 5% 口徑。 */
export const NEUTRAL_BAND = 0.05;

/** 顏色濃度到此封頂：±100% 以上一律最濃。 */
export const COLOR_CAP = 1.0;

// iOS 系統綠／紅（`styles.css` 的 --green／--red 淺色值）。
const GAIN = [52, 199, 89];
const LOSS = [255, 59, 48];

/**
 * 格子底色。刻意回傳**半透明**色而不是實色：實色要嘛在淺色模式好看、
 * 要嘛在深色模式好看，不可能兩者兼顧（舊版是往白色混，深色底下會變成
 * 一片刺眼的亮塊）。半透明疊在卡片底色上，兩種模式都成立。
 */
export function cellColor(ret: number): string {
  if (Math.abs(ret) < NEUTRAL_BAND) return "transparent";
  const t = Math.min(Math.abs(ret), COLOR_CAP);
  const [r, g, b] = ret > 0 ? GAIN : LOSS;
  return `rgba(${r}, ${g}, ${b}, ${(t * 0.8).toFixed(3)})`;
}

/** 格子文字：一律帶正負號，四捨五入到整數百分比（同舊版 `+.0f`）。 */
export function formatCell(ret: number): string {
  const pct = ret * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
}

/** 日期欄標題：MM/DD，最後一欄補「到期」——那一欄的語意跟其他欄不同。 */
export function columnLabel(iso: string, isLast: boolean): string {
  return `${iso.slice(5, 7)}/${iso.slice(8, 10)}${isLast ? " 到期" : ""}`;
}

const TAGS: Record<string, string> = {
  "<現價>": "現價", "<目標>": "目標", "<超標>": "超標", "<深跌>": "深跌",
};

/**
 * 價格列的錨點標記。GUI 只讀引擎給的標籤字串，永遠不自己重算哪個價格
 * 是現價／目標（v4 spec §4.3 的既有原則）。
 */
export function priceTags(label: string): string[] {
  return Object.entries(TAGS)
    .filter(([marker]) => label.includes(marker))
    .map(([, text]) => text);
}
