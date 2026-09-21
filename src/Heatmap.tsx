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
 * `crossoverCellSides`／`crossoverSides`／`crossoverFavoredSide`，見
 * `./heatmap`）是純幾何：逐格比較兩個矩陣哪裡符號翻轉，不解任何金融
 * 方程式。`comparator` 為 `null`（單腿候選、或買腿報價缺失）時顯示一行
 * 誠實的缺席原因，不假造一條線。
 *
 * QA 修正三點：標示改成畫在格子**單一邊**上的細線（不是整格粗框）、
 * 顏色改用琥珀（`--crossover`；藍會跟 `--acc-text` 的互動語意混淆、紅會被
 * 讀成警告），而且線一律畫在 **Spread 較高的那一側**——方向是從矩陣
 * 算出來的，不預設「左上是 Spread、右下是 Long Call」。
 */
import type { Matrix } from "./api";
import {
  cellColor, columnLabel, crossoverCellSides, crossoverEdges,
  crossoverFavoredSide, crossoverSides, formatCell, formatMovePct,
  formatMovePctShort, priceTags,
  type CrossoverSide, type CrossoverSides, type ResolvedComparator,
} from "./heatmap";
import InfoTooltip from "./InfoTooltip";
import { money } from "./scenarios";

/** 「Long Call」／「Long Put」——直接讀 `option_type`，不從 strategy
 *  反推（後端已經把型別放進契約，前端只格式化）。 */
function comparatorKind(c: ResolvedComparator): string {
  return c.option_type === "call" ? "Long Call" : "Long Put";
}

/** Comparator 完整標籤：「12/05 105 Long Call」。 */
function comparatorLabel(c: ResolvedComparator): string {
  const [, month, day] = c.expiry.split("-");
  return `${month}/${day} ${c.strike} ${comparatorKind(c)}`;
}

/** 一格要畫的邊 → inset box-shadow。用 box-shadow 而非 border：border
 *  會撐開格子尺寸、動到整張表的欄寬，inset 陰影純粹疊在格子上。 */
function edgeShadow(sides: CrossoverSide[] | undefined): string | undefined {
  if (!sides || sides.length === 0) return undefined;
  const offset: Record<CrossoverSide, string> = {
    top: "inset 0 2px 0 0", bottom: "inset 0 -2px 0 0",
    left: "inset 2px 0 0 0", right: "inset -2px 0 0 0",
  };
  return sides.map((s) => `${offset[s]} var(--crossover)`).join(", ");
}

/**
 * 兩側各是誰較高的那一句——`sides` 由實際矩陣算出來（見
 * `crossoverSides`），不是「左上是 Spread、右下是 Long Call」這種對真實
 * 資料沒有保證的方位假設。
 */
function sidesSentence(sides: CrossoverSides, kind: string): string {
  if (sides.axis === "price") {
    return sides.spreadSide === "low"
      ? `標的價較低的一側 Spread 較高，較高的一側 ${kind} 較高。`
      : `標的價較高的一側 Spread 較高，較低的一側 ${kind} 較高。`;
  }
  return sides.spreadSide === "low"
    ? `較早的日期 Spread 較高，越接近到期 ${kind} 較高。`
    : `越接近到期 Spread 較高，較早的日期 ${kind} 較高。`;
}

/**
 * SW-12（#342，Owner 真機驗收）：SW-11（#341）當時保留了這整段常駐
 * 說明——理由是既有 #116 硬性 AC「不需要額外互動就看得到圖例與邊界
 * 標示」，且 Owner 當時對 crossover 只用「若仍需要」的伸縮用詞。這輪
 * Owner 明講「主畫面最多保留一句，其餘（成本／comparator／兩側較優
 * 區域細節）收進 ⓘ」，並明文裁示「若舊測試或舊 issue AC（含 #116）
 * 要求完整說明常駐可見，這次修測試，不要為舊 AC 保留冗長 UI」——
 * 因此這裡改把 #116 那份既有 e2e AC 一併更新（見 `e2e/smoke.spec.ts`／
 * `e2e/desktop.spec.ts` 對應測試），不是繼續讓舊 AC 擋住這次精簡。
 * comparator 身分／成本／兩側各自較優的完整說明搬進 `InfoTooltip`
 * （跟主 caption 同一個既有元件），不是刪掉這些金融資訊。
 */
function CrossoverLegend({ comparator, edges, favoredSide, sides }: {
  comparator: ResolvedComparator;
  edges: ReturnType<typeof crossoverEdges>;
  favoredSide: ReturnType<typeof crossoverFavoredSide>;
  sides: CrossoverSides | null;
}) {
  const kind = comparatorKind(comparator);
  return (
    <p className="caption crossover-legend">
      <span className="crossover-swatch" aria-hidden="true" />
      <span>
        琥珀線為 Spread 與 {kind} 報酬相同的分界；線兩側表示各自較有利
        的區域。
      </span>
      <InfoTooltip label="分界怎麼算">
        <span>
          格子是 Spread 報酬率。琥珀線＝與直接買{" "}
          <strong>{comparatorLabel(comparator)}</strong>（成本{" "}
          {money(comparator.cost)}）報酬相等的分界。
        </span>
        {sides && <span className="crossover-sides">{sidesSentence(sides, kind)}</span>}
        {edges.length === 0 && (
          <span>
            {favoredSide === "spread"
              ? "此圖範圍內沒有分界：整張都是 Spread 較高。"
              : favoredSide === "comparator"
              ? `此圖範圍內沒有分界：整張都是 ${kind} 較高。`
              : "資料不足以判定哪一側較高。"}
          </span>
        )}
      </InfoTooltip>
    </p>
  );
}

export default function Heatmap({ matrix, comparator }: {
  matrix: Matrix;
  comparator?: ResolvedComparator | null;
}) {
  const { prices, dates, cells } = matrix;
  // 由高價到低價，與看盤軟體一致（漲在上、跌在下）
  const order = prices.map((_, i) => i).reverse();

  const edges = comparator ? crossoverEdges(cells, comparator.matrix.cells) : [];
  const favoredSide = comparator
    ? crossoverFavoredSide(cells, comparator.matrix.cells)
    : "mixed";
  const sides = comparator ? crossoverSides(cells, comparator.matrix.cells) : null;
  const boundaryCells = crossoverCellSides(edges);

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
              // SW-08（#338）：目標列高亮 terracotta、現價列高亮暖灰
              // ——兩個既有標籤字串各自對到一個 class，同一列可能兩個
              // tag 都有（使用者的目標價恰好等於現價），classList 直接
              // 都掛上去，CSS 決定疊色順序（見 styles.css 同名 class）。
              const rowClass = [
                tags.length > 0 && "anchor",
                tags.includes("目標") && "anchor-target",
                tags.includes("現價") && "anchor-spot",
              ].filter(Boolean).join(" ") || undefined;
              return (
                <tr key={price} className={rowClass}>
                  <th scope="row" className="heatmap-price">
                    {price.toFixed(2)}
                    {tags.map((t) => (
                      <span className="tag" key={t}>
                        {t}
                      </span>
                    ))}
                  </th>
                  {cells[i].map((value, j) => {
                    const edgeSides = boundaryCells.get(`${i}-${j}`);
                    return (
                      <td
                        key={dates[j][0]}
                        style={{ background: cellColor(value),
                                boxShadow: edgeShadow(edgeSides) }}
                        className={edgeSides ? "heatmap-crossover-cell" : undefined}
                        data-crossover-sides={edgeSides?.join(" ")}
                      >
                        {formatCell(value)}
                      </td>
                    );
                  })}
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
      {/* SW-11（#341，Owner 真機驗收）：主畫面只留使用者真正需要知道的
          看圖方式——格子是什麼、顏色深淺代表什麼、標記列是什麼；Ask／
          Bid 進場口徑與內插這種「怎麼算出來的」細節屬於進階說明，移入
          ⓘ（`InfoTooltip`），不是刪掉，滑鼠移過去／鍵盤 focus 到還是
          看得到完整口徑。 */}
      <p className="caption heatmap-caption">
        <span>格子為報酬率；顏色越深代表幅度越大；標記列為錨點價格。</span>
        <InfoTooltip label="報酬率怎麼算">
          以最差成交價（買付 Ask、賣收 Bid）進場的報酬率（%）；除錨點列
          （現價／目標價等）本身是引擎給的實際值外，其餘格子為內插。
        </InfoTooltip>
      </p>
      {/* `comparator === undefined`（呼叫端根本沒傳，見 `ScenarioDetail.tsx`／
          `ExpiryStructure.tsx`——單腿候選不傳這個 prop）＝這個候選沒有
          Crossover 概念，不顯示任何區塊，不是「缺席」；`null`（呼叫端
          傳了，但值是 null）才是 AC 講的「comparator 的報價缺失」那個
          需要誠實揭露原因的狀態，兩者不能用同一句話混著講。 */}
      {comparator === undefined ? null : comparator === null ? (
        <p className="caption crossover-legend crossover-absent">
          買腿沒有報價，無法標出分界。
        </p>
      ) : (
        <CrossoverLegend comparator={comparator} edges={edges}
                         favoredSide={favoredSide} sides={sides} />
      )}
    </div>
  );
}
