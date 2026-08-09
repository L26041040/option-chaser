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
 * 決策 M（#109）：價格欄右側加一個 ±%（`matrix.prices` 第三欄
 * `move_pct`，同樣是引擎給的，不在這裡重算），跟左側絕對價格同一列、
 * 同一個 sticky 儲存格，橫向捲動時一起釘住。候選展開後的 Heatmap 用的
 * 是同一個元件，不需要另外接線。
 */
import type { Matrix } from "./api";
import {
  cellColor, columnLabel, formatCell, formatMovePct, formatMovePctShort,
  priceTags,
} from "./heatmap";

export default function Heatmap({ matrix }: { matrix: Matrix }) {
  const { prices, dates, cells } = matrix;
  // 由高價到低價，與看盤軟體一致（漲在上、跌在下）
  const order = prices.map((_, i) => i).reverse();

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
                    {/* 決策 M（#109）：右側 ±%，跟左側絕對價格同一列的
                        annotation，不是另一條座標軸——放在同一個 sticky
                        儲存格裡，橫向捲動時跟價格一起釘住，手機視窗不用
                        額外互動就看得到。完整／短格式兩者都畫進 DOM，用
                        CSS 依版面寬度切換，不是 JS 判斷視窗寬度。 */}
                    <span className="heatmap-move-pct">
                      <span className="heatmap-move-pct-full">
                        {formatMovePct(movePct)}
                      </span>
                      <span className="heatmap-move-pct-short">
                        {formatMovePctShort(movePct)}
                      </span>
                    </span>
                    {tags.map((t) => (
                      <span className="tag" key={t}>
                        {t}
                      </span>
                    ))}
                  </th>
                  {cells[i].map((value, j) => (
                    <td key={dates[j][0]} style={{ background: cellColor(value) }}>
                      {formatCell(value)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="caption">
        以最差進場成本（買付 Ask、賣收 Bid）進場，在各標的價與日期下的模型
        報酬率。標記列為錨點價格，其餘為等距內插。
      </p>
    </div>
  );
}
