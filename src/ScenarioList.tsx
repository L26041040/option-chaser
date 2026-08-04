/**
 * 劇本清單（V3／#51；V4／#52 加上新鮮度與失敗分層）。
 *
 * 每張卡片顯示標的／目標價／目標年月／最新收益率／距到期天數／資料時間，
 * 並有封存入口（軟刪除：清單消失、資料與紀錄保留）。
 *
 * V4 的兩個新東西都貼在卡片上，而不是全域一顆燈：資料太舊標「舊資料」，
 * 刷新失敗說明是哪一段失敗、旁邊就是重試入口——失敗是**單一劇本**的事，
 * 訊息離它愈近愈好。
 *
 * 排序與格式化都在 `./scenarios` 的純函式裡，這裡只負責畫。
 */
import type { RefreshFailure, ScenarioSummary } from "./api";
import {
  failureLabel,
  formatAnalyzedAt,
  formatDaysLeft,
  formatReturn,
  isStale,
  money,
  sortScenarios,
} from "./scenarios";

function ScenarioCard({
  row,
  failure,
  now,
  onArchive,
  onRetry,
}: {
  row: ScenarioSummary;
  failure: RefreshFailure | undefined;
  now: Date;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  const ran = row.best_return !== null;
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
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
            這張卡上的數字是新的。久未刷新則明講「舊資料」：數字還是
            上一次算出來的真數字，只是不能當成現在的。 */}
        <span className="row-value">
          {formatAnalyzedAt(row.latest_analyzed_at)}
          {stale && <span className="tag warn">舊資料</span>}
        </span>
      </div>

      {failure && (
        <div className="notice error" role="alert">
          <div className="row-value">{failureLabel(failure.stage)}</div>
          <p className="caption">{failure.message}</p>
          <button
            className="button subtle"
            onClick={() => onRetry(row.id)}
            aria-label={`重試 ${who}`}
          >
            重試
          </button>
        </div>
      )}

      <button
        className="button subtle"
        onClick={() => onArchive(row.id)}
        aria-label={`封存 ${who}`}
      >
        封存
      </button>
    </li>
  );
}

export default function ScenarioList({
  rows,
  failures,
  now,
  onArchive,
  onRetry,
}: {
  rows: ScenarioSummary[];
  failures: Record<string, RefreshFailure>;
  now: Date;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  if (rows.length === 0) {
    return <p className="caption">還沒有劇本。用下面的表單建立第一個。</p>;
  }
  return (
    <>
      {/* 收益率口徑就寫在數字旁邊（V4／#52）。放進說明頁等於沒寫——
          看數字的人不會為了一個百分比先去翻說明。 */}
      <p className="caption">
        收益率以最差成交價計算（買腿 Ask − 賣腿 Bid）
      </p>
      <ul className="list">
        {sortScenarios(rows).map((row) => (
          <ScenarioCard
            key={row.id}
            row={row}
            failure={failures[row.id]}
            now={now}
            onArchive={onArchive}
            onRetry={onRetry}
          />
        ))}
      </ul>
    </>
  );
}
