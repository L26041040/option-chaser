/**
 * 劇本主圖（V5／#53）：價格×日期的報酬率 Heatmap。
 *
 * 每一格都是引擎算好的報酬率（`matrix.cells`），錨點列也是引擎標的
 * （`matrix.prices` 第二欄）——這裡零金融計算，只負責畫。配色與格式在
 * `./heatmap` 的純函式裡。
 *
 * 手機優先的兩個決定：
 * - 價格欄 `position: sticky` 釘在左側，橫向捲動時才知道自己在看哪一列
 * - 整張表包在可橫向捲動的容器裡，不縮字級硬塞——七欄擠進 390px 只會
 *   讓數字小到讀不出來
 *
 * 決策 M（#109）＋ QA-FIX-1（QA-01）：±% 是表格**最右邊一欄**——每一
 * price row 在全部日期格之後的 annotation 欄，不是塞在左側價格欄裡。
 * 值取自 `matrix.prices` 第三欄 `move_pct`（引擎給的，不在這裡重算），
 * 它不是獨立 scale：同一列的絕對價格與 ±% 講的是同一件事的兩種寫法。
 * 左側價格欄 `sticky left`、右側 ±% 欄 `sticky right`，橫向捲動時兩端
 * 都留在畫面上，中間的日期格才是捲動的部分。候選展開後的 Heatmap 用的
 * 是同一個元件，不需要另外接線。
 *
 * Crossover Boundary（#116，spec #117 §4）：`comparator` 選填——傳入時
 * 疊一層「這組 Spread 報酬 vs 直接買買腿本身」的邊界標示在同一張表上，
 * 不畫第二張表、不遮蓋既有格值。邊界計算（`crossoverEdges`／
 * `crossoverFavoredSide`，見 `./heatmap`）是純幾何：逐格比較兩個矩陣
 * 哪裡符號翻轉，不解任何金融方程式。`comparator` 為 `null`（單腿候選、
 * 或買腿報價缺失）時顯示一行誠實的缺席原因，不假造一條線。
 */
import type { Comparator, Matrix } from "./api";
import {
  cellColor, columnLabel, crossoverEdges, crossoverFavoredSide, formatCell,
  formatMovePct, formatMovePctShort, priceTags,
} from "./heatmap";
import { money } from "./scenarios";

/** Comparator 標籤：「2028/12 105 Long Call」——直接讀 `option_type`，
 *  不從 strategy 反推（後端已經把型別放進契約，前端只格式化）。 */
function comparatorLabel(c: Comparator): string {
  const [, month, day] = c.expiry.split("-");
  const kind = c.option_type === "call" ? "Long Call" : "Long Put";
  return `${month}/${day} ${c.strike} ${kind}`;
}

/** 邊界格 key（`"row-col"`）集合——vertical／horizontal 兩種邊各自的
 *  兩端都算「邊界附近」，不只標其中一格，這樣一個 edge 至少在畫面上
 *  留下兩個相鄰、彼此靠著的高亮格，才看得出「線」的走向。 */
function boundaryCellKeys(edges: ReturnType<typeof crossoverEdges>): Set<string> {
  const keys = new Set<string>();
  for (const e of edges) {
    keys.add(`${e.row}-${e.col}`);
    if (e.orientation === "vertical") keys.add(`${e.row + 1}-${e.col}`);
    else keys.add(`${e.row}-${e.col + 1}`);
  }
  return keys;
}

function CrossoverLegend({ comparator, edges, favoredSide }: {
  comparator: Comparator;
  edges: ReturnType<typeof crossoverEdges>;
  favoredSide: ReturnType<typeof crossoverFavoredSide>;
}) {
  const label = comparatorLabel(comparator);
  return (
    <p className="caption crossover-legend">
      格子仍是 Spread 報酬率；<span className="crossover-swatch" /> 標示的格子
      是邊界所在——在那裡 Spread 與直接買{" "}
      <strong>{label}</strong>（成本 {money(comparator.cost)}）報酬相等。
      {edges.length === 0 && (
        <>
          {" "}此圖顯示範圍內邊界不在網格上：
          {favoredSide === "spread"
            ? "全部落在 Spread 較優的一側。"
            : favoredSide === "comparator"
            ? `全部落在直接買 ${label} 較優的一側。`
            : "資料不足以判定哪一側較優。"}
        </>
      )}
    </p>
  );
}

export default function Heatmap({ matrix, comparator }: {
  matrix: Matrix;
  comparator?: Comparator | null;
}) {
  const { prices, dates, cells } = matrix;
  // 由高價到低價，與看盤軟體一致（漲在上、跌在下）
  const order = prices.map((_, i) => i).reverse();

  const edges = comparator ? crossoverEdges(cells, comparator.matrix.cells) : [];
  const favoredSide = comparator
    ? crossoverFavoredSide(cells, comparator.matrix.cells)
    : "mixed";
  const boundaryCells = boundaryCellKeys(edges);

  return (
    <div className="heatmap">
      <div className="heatmap-scroll">
        <table className="heatmap-table">
          {/* 表格要有可及名稱。底下那段說明是 `<p>`、與表格只是兄弟關係，
              輔助技術不會把它當成這張表的標題。 */}
          <caption className="sr-only">標的價格×日期的模型報酬率</caption>
          <thead>
            <tr>
              <th scope="col" className="heatmap-price-head">
                價格
              </th>
              {dates.map(([iso], j) => (
                <th scope="col" key={iso}>
                  {columnLabel(iso, j === dates.length - 1)}
                </th>
              ))}
              {/* QA-FIX-1：最右欄要有自己的欄標題，否則欄數與 <tbody>
                  對不上，語意表格對輔助技術會壞掉。 */}
              <th scope="col" className="heatmap-move-head">
                vs 現價
              </th>
            </tr>
          </thead>
          <tbody>
            {order.map((i) => {
              const [price, label, movePct] = prices[i];
              const tags = priceTags(label);
              return (
                <tr key={price} className={tags.length ? "anchor" : undefined}>
                  <th scope="row" className="heatmap-price">
                    {price.toFixed(2)}
                    {tags.map((t) => (
                      <span className="tag" key={t}>
                        {t}
                      </span>
                    ))}
                  </th>
                  {cells[i].map((value, j) => (
                    <td
                      key={dates[j][0]}
                      style={{ background: cellColor(value) }}
                      className={boundaryCells.has(`${i}-${j}`)
                        ? "heatmap-crossover-cell" : undefined}
                    >
                      {formatCell(value)}
                    </td>
                  ))}
                  {/* QA-FIX-1：±% 在全部日期格之後。完整／短格式兩者都畫
                      進 DOM，用 CSS 依版面寬度切換，不是 JS 判斷視窗寬度
                      （沿用 #109 既有做法，只換掛載位置）。 */}
                  <td className="heatmap-move-pct">
                    <span className="heatmap-move-pct-full">
                      {formatMovePct(movePct)}
                    </span>
                    <span className="heatmap-move-pct-short">
                      {formatMovePctShort(movePct)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="caption">
        以最差進場成本（買付 Ask、賣收 Bid）進場，在各標的價與日期下的模型
        報酬率（單位：%）。標記列為錨點價格，其餘為等距內插。
      </p>
      {/* `comparator === undefined`（呼叫端根本沒傳，見 `ScenarioDetail.tsx`／
          `ExpiryStructure.tsx`——單腿候選不傳這個 prop）＝這個候選沒有
          Crossover 概念，不顯示任何區塊，不是「缺席」；`null`（呼叫端
          傳了，但值是 null）才是 AC 講的「comparator 的報價缺失」那個
          需要誠實揭露原因的狀態，兩者不能用同一句話混著講。 */}
      {comparator === undefined ? null : comparator === null ? (
        <p className="caption crossover-legend crossover-absent">
          Crossover 對照缺席：無法取得買腿報價，本頁不顯示邊界。
        </p>
      ) : (
        <CrossoverLegend comparator={comparator} edges={edges} favoredSide={favoredSide} />
      )}
    </div>
  );
}
