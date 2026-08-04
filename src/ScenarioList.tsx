/**
 * 劇本清單（V3／#51）：iOS 卡片式，依最新收益率排序。
 *
 * 每張卡片顯示標的／目標價／目標年月／最新收益率／距到期天數／資料時間，
 * 並有封存入口（軟刪除：清單消失、資料與紀錄保留）。
 *
 * 排序與格式化都在 `./scenarios` 的純函式裡，這裡只負責畫。
 */
import type { ScenarioSummary } from "./api";
import {
  formatAnalyzedAt,
  formatDaysLeft,
  formatReturn,
  money,
  sortScenarios,
} from "./scenarios";

function ScenarioCard({
  row,
  onArchive,
}: {
  row: ScenarioSummary;
  onArchive: (id: string) => void;
}) {
  const ran = row.best_return !== null;
  return (
    <li className="card">
      <div className="row">
        <span className="row-value big">{row.symbol}</span>
        <span
          className={
            ran ? `metric ${row.best_return! >= 0 ? "positive" : "negative"}`
                : "metric muted"
          }
        >
          {formatReturn(row.best_return)}
        </span>
      </div>

      <div className="row">
        <span className="row-label">目標</span>
        <span className="row-value">
          {money(row.target_price)}　{row.target_month}
        </span>
      </div>

      <div className="row">
        <span className="row-label">距到期</span>
        <span className="row-value">{formatDaysLeft(row.days_to_anchor)}</span>
      </div>

      <div className="row">
        <span className="row-label">資料時間</span>
        {/* 還沒跑過就說還沒跑過——顯示一個空白或舊時間都會讓人以為
            這張卡上的數字是新的。 */}
        <span className="row-value">
          {formatAnalyzedAt(row.latest_analyzed_at)}
        </span>
      </div>

      <button
        className="button subtle"
        onClick={() => onArchive(row.id)}
        aria-label={`封存 ${row.symbol} ${row.target_month}`}
      >
        封存
      </button>
    </li>
  );
}

export default function ScenarioList({
  rows,
  onArchive,
}: {
  rows: ScenarioSummary[];
  onArchive: (id: string) => void;
}) {
  if (rows.length === 0) {
    return <p className="caption">還沒有劇本。用下面的表單建立第一個。</p>;
  }
  return (
    <ul className="list">
      {sortScenarios(rows).map((row) => (
        <ScenarioCard key={row.id} row={row} onArchive={onArchive} />
      ))}
    </ul>
  );
}
