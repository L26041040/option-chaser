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

// ---------- Crossover Boundary（#116，spec #117 §4） ----------
//
// 「derived on the frontend from the two matrices... using only equality
// comparison and interpolation. No financial computation in the frontend」
// ——這裡做的是純幾何：逐格比較兩個矩陣（Spread 自己的 vs comparator
// 的）哪裡符號翻轉，翻轉處＝兩者報酬率相等的邊界。不解任何金融方程式，
// 不重算任何報酬率，只讀已經算好的 cell 值。
//
// 邊界用「哪兩個相鄰格子之間符號不同」表示，不是連續曲線座標——表格
// 本質是離散格點，用格子邊界畫線（CSS border）比另外量測像素位置畫
// SVG 更穩（不受橫向捲動／sticky 欄影響），也天然滿足「可能是分段線」
// 的要求。掃描兩個方向（vertical＝同一欄、相鄰價格列之間；horizontal＝
// 同一價格列、相鄰日期欄之間），才能抓到邊界沿任一軸移動的情況，不是
// 只假設它只沿價格軸或只沿日期軸走。

export interface CrossoverEdge {
  row: number;   // matrix.cells 的列索引（價格軸，未反轉的原始順序）
  col: number;   // matrix.cells 的欄索引（日期軸）
  /** vertical：邊界在 (row,col) 與 (row+1,col) 之間（同一天、相鄰價位）。
   *  horizontal：邊界在 (row,col) 與 (row,col+1) 之間（同一價位、相鄰日期）。 */
  orientation: "vertical" | "horizontal";
}

function sign(x: number): number {
  return x > 0 ? 1 : x < 0 ? -1 : 0;
}

/**
 * 兩個矩陣逐格相減（Spread − comparator），在符號翻轉的相鄰格邊界上
 * 各記一筆。矩陣形狀不一致（理論上不該發生，後端 `_matrix_view` 保證
 * 同一組 grid——這裡仍防禦性核對，形狀不符直接回空陣列，不猜、不半算）
 * 時回傳空陣列，讓呼叫端走「無法判定」而非拋錯，畫面才能誠實顯示原因。
 */
export function crossoverEdges(
  spreadCells: number[][], comparatorCells: number[][]
): CrossoverEdge[] {
  const nRows = spreadCells.length;
  if (nRows === 0 || comparatorCells.length !== nRows) return [];
  const nCols = spreadCells[0].length;
  if (comparatorCells.some((row) => row.length !== nCols)
      || spreadCells.some((row) => row.length !== nCols)) return [];

  const diff = spreadCells.map((row, i) => row.map((v, j) => v - comparatorCells[i][j]));
  const edges: CrossoverEdge[] = [];
  for (let i = 0; i < nRows; i++) {
    for (let j = 0; j < nCols; j++) {
      if (i + 1 < nRows && sign(diff[i][j]) !== sign(diff[i + 1][j])) {
        edges.push({ row: i, col: j, orientation: "vertical" });
      }
      if (j + 1 < nCols && sign(diff[i][j]) !== sign(diff[i][j + 1])) {
        edges.push({ row: i, col: j, orientation: "horizontal" });
      }
    }
  }
  return edges;
}

export type CrossoverFavoredSide = "spread" | "comparator" | "mixed";

/**
 * 整個 grid 有沒有一致的贏家——只在 `crossoverEdges` 回空陣列（整張表
 * 沒有任何符號翻轉）時才有意義：這代表邊界整條落在網格之外，圖例要
 * 說清楚「這張表全部落在哪一側」，不能讓使用者把「沒畫線」誤讀成
 * 「沒有 Crossover」。
 */
export function crossoverFavoredSide(
  spreadCells: number[][], comparatorCells: number[][]
): CrossoverFavoredSide {
  let sawPositive = false;
  let sawNegative = false;
  for (let i = 0; i < spreadCells.length; i++) {
    for (let j = 0; j < spreadCells[i].length; j++) {
      const d = spreadCells[i][j] - (comparatorCells[i]?.[j] ?? NaN);
      if (d > 0) sawPositive = true;
      if (d < 0) sawNegative = true;
    }
  }
  if (sawPositive && !sawNegative) return "spread";
  if (sawNegative && !sawPositive) return "comparator";
  return "mixed";
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
