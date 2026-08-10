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

/**
 * 格子文字：QA-01 後續（#121）改成純數字，不帶正負號、不帶 `%`——
 * `+128%` 這種寫法在每一格都重複印一次單位，擠掉日期欄能用的橫向
 * 寬度；顏色與位置已經講清楚漲跌方向，正負號只留在數字本身（負值的
 * `-` 是數字的一部分，不是額外裝飾）。單位改成只在下方 caption 講一次
 * （`render.ts` 的 caption 文字，見 `Heatmap.tsx`）。
 *
 * `Math.round` 而非 `toFixed`：避免 `(-0.4).toFixed(0)` 印出容易讓人
 * 誤讀的 `"-0"`——四捨五入到 0 的負值一律顯示成 `"0"`（`-0 === 0`
 * 對 `===` 比較成立，但轉成字串前必須先攔下來）。
 */
export function formatCell(ret: number): string {
  const pct = Math.round(ret * 100);
  return pct === 0 ? "0" : String(pct);
}

/** 日期欄標題：MM/DD，最後一欄補「到期」——那一欄的語意跟其他欄不同。 */
export function columnLabel(iso: string, isLast: boolean): string {
  return `${iso.slice(5, 7)}/${iso.slice(8, 10)}${isLast ? " 到期" : ""}`;
}

/**
 * 右側 ±% 標註（決策 M／#109）：跟左側絕對價格同一個 price row 的
 * annotation，不是獨立座標軸。`movePct` 是引擎給的變動分數，這裡只
 * 格式化——一律帶正負號，跟 `formatCell` 同一套「正負號永遠印出來」
 * 的慣例（含 0 本身，`<現價>` 那一列會顯示「+0.0%」，與 `formatCell(0)`
 * 顯示「+0%」是同一個既有決定，非本票新發明）。
 */
export function formatMovePct(movePct: number): string {
  const pct = movePct * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

/**
 * 短格式（Mobile，AC 明文允許）：四捨五入到整數百分比，省下的寬度
 * 讓給 sticky 價格欄旁邊還要橫向捲動的日期欄。跟完整格式一樣一律
 * 帶正負號，只是不縮到「完全省略」或「要長按才看得到」。
 */
export function formatMovePctShort(movePct: number): string {
  const pct = movePct * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
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
