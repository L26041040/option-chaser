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
  /**
   * 這條邊的兩格裡，哪一格是 Spread 較高的那一側——`"near"` 是
   * (row,col) 自己，`"far"` 是相鄰的那一格。線就畫在這一側，使用者
   * 才能直接從圖上讀出方向，而不是靠「邊界通常在左上／右下」這種
   * 對實際矩陣沒有保證的假設。相等時（兩格差值一樣）回 `"near"`。
   */
  spreadHigher: "near" | "far";
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
  const higher = (a: number, b: number): "near" | "far" => (b > a ? "far" : "near");
  for (let i = 0; i < nRows; i++) {
    for (let j = 0; j < nCols; j++) {
      if (i + 1 < nRows && sign(diff[i][j]) !== sign(diff[i + 1][j])) {
        edges.push({ row: i, col: j, orientation: "vertical",
                    spreadHigher: higher(diff[i][j], diff[i + 1][j]) });
      }
      if (j + 1 < nCols && sign(diff[i][j]) !== sign(diff[i][j + 1])) {
        edges.push({ row: i, col: j, orientation: "horizontal",
                    spreadHigher: higher(diff[i][j], diff[i][j + 1]) });
      }
    }
  }
  return edges;
}

/** 一格的哪一條邊要畫線。 */
export type CrossoverSide = "top" | "bottom" | "left" | "right";

/**
 * 把邊界轉成「哪一格的哪一條邊要畫線」——線一律畫在 **Spread 較高的
 * 那一側**，使用者不必看圖例就能從線的位置讀出方向。
 *
 * 需要留意表格的列是**反著畫**的（`Heatmap.tsx` 由高價到低價，漲在
 * 上）：`row + 1`（價格較高）渲染在 `row` 的**上方**，所以兩者之間那條
 * 邊，對 `row` 而言是 `top`、對 `row + 1` 而言是 `bottom`。欄則是正序，
 * `col + 1` 在 `col` 右邊。
 *
 * 回傳 `"<row>-<col>"` → 該格要畫的邊。同一格可能同時吃到兩條邊
 * （邊界在這裡轉角），所以值是陣列而不是單一邊。
 */
export function crossoverCellSides(
  edges: CrossoverEdge[]
): Map<string, CrossoverSide[]> {
  const sides = new Map<string, CrossoverSide[]>();
  const put = (row: number, col: number, side: CrossoverSide) => {
    const key = `${row}-${col}`;
    const cur = sides.get(key);
    if (cur) { if (!cur.includes(side)) cur.push(side); }
    else sides.set(key, [side]);
  };
  for (const e of edges) {
    if (e.orientation === "vertical") {
      if (e.spreadHigher === "near") put(e.row, e.col, "top");
      else put(e.row + 1, e.col, "bottom");
    } else {
      if (e.spreadHigher === "near") put(e.row, e.col, "right");
      else put(e.row, e.col + 1, "left");
    }
  }
  return sides;
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

/** 把兩側分得最開的那一軸，以及 Spread 較高的是該軸上哪一端。 */
export interface CrossoverSides {
  /** `price`＝分界主要沿標的價；`date`＝主要沿日期。 */
  axis: "price" | "date";
  /** 在 `axis` 上，Spread 較高的是數值較小（`low`）還是較大（`high`）的一端。 */
  spreadSide: "low" | "high";
}

/**
 * 邊界兩側各是誰較高——**完全由實際矩陣算出來**，不預設「左上是
 * Spread、右下是 Long Call」這種對真實資料沒有保證的方位。
 *
 * 作法是純幾何的重心比較：把「Spread 較高」與「comparator 較高」兩群
 * 格子各自的平均列（價格）與平均欄（日期）算出來，兩軸各自正規化成
 * 0–1（否則 30 欄的日期軸會單純因為索引比較大而永遠勝出），取分得比較
 * 開的那一軸當主軸，再看 Spread 那一群落在該軸的哪一端。
 *
 * 兩群其中一群是空的（邊界整條落在網格外）或矩陣形狀不一致時回 `null`
 * ——那種情況沒有「兩側」可言，呼叫端該改講「整張圖都在某一側」。
 */
export function crossoverSides(
  spreadCells: number[][], comparatorCells: number[][]
): CrossoverSides | null {
  const nRows = spreadCells.length;
  if (nRows === 0 || comparatorCells.length !== nRows) return null;
  const nCols = spreadCells[0].length;
  if (comparatorCells.some((row) => row.length !== nCols)
      || spreadCells.some((row) => row.length !== nCols)) return null;

  let sRows = 0, sCols = 0, sN = 0;
  let cRows = 0, cCols = 0, cN = 0;
  for (let i = 0; i < nRows; i++) {
    for (let j = 0; j < nCols; j++) {
      const d = spreadCells[i][j] - comparatorCells[i][j];
      if (d > 0) { sRows += i; sCols += j; sN++; }
      else if (d < 0) { cRows += i; cCols += j; cN++; }
    }
  }
  if (sN === 0 || cN === 0) return null;

  // 正規化：單格的軸（nRows 或 nCols 為 1）沒有可比的展開方向，分離度算 0。
  const rowSpan = nRows > 1 ? nRows - 1 : 0;
  const colSpan = nCols > 1 ? nCols - 1 : 0;
  const rowGap = sRows / sN - cRows / cN;
  const colGap = sCols / sN - cCols / cN;
  const priceSep = rowSpan ? Math.abs(rowGap) / rowSpan : 0;
  const dateSep = colSpan ? Math.abs(colGap) / colSpan : 0;

  // 平手時取價格軸：Heatmap 的縱軸就是價格，使用者讀圖時的第一直覺。
  const axis = priceSep >= dateSep ? "price" : "date";
  const gap = axis === "price" ? rowGap : colGap;
  return { axis, spreadSide: gap < 0 ? "low" : "high" };
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
