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
import { detailHash } from "./route";
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
  selected,
  onArchive,
  onRetry,
}: {
  row: ScenarioSummary;
  failure: RefreshFailure | undefined;
  now: Date;
  selected: boolean;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  const ran = row.best_return !== null;
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
  return (
    <li className={selected ? "card selected" : "card"}>
      {/* 整張卡就是進詳細頁的入口。用真的 `<a>` 而不是掛 onClick 的
          div：長按可以複製連結、返回手勢可用、鍵盤與螢幕閱讀器也認得。
          封存鈕留在連結外面——按鈕不能包在連結裡。 */}
      {/* 不掛 `aria-label`：那會**取代**連結內容當成可及名稱，螢幕閱讀器
          就只聽得到「TLT 2028-05 詳細」，收益率／目標／距到期／資料時間
          全部被吃掉。改在結尾補一段只有輔助技術讀得到的字。 */}
      {/* #72：桌面版左側清單常駐，`aria-current` 讓螢幕閱讀器也認得
          「目前選中的是哪一個」，不只是視覺上的高亮。 */}
      <a className="card-tap" href={detailHash(row.id)}
         aria-current={selected ? "page" : undefined}>
        <div className="row">
          <span className="row-value big">{row.symbol}</span>
          <span className="metric-group">
            <span
              className={
                ran ? `metric ${row.best_return! >= 0 ? "positive" : "negative"}`
                    : "metric muted"
              }
            >
              {formatReturn(row.best_return)}
            </span>
            <span className="chevron" aria-hidden="true">
              ›
            </span>
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
          <span className="row-value">
            {formatDaysLeft(row.days_to_anchor)}
            {/* #68：目標月已過完的劇本不再花資源刷新，卡片上要看得出
                「不是刷新失敗、也不是還沒分析過」，是第三種、刻意的
                狀態——見下面失敗提示的互斥處理。 */}
            {row.expired && <span className="tag">已過期，不再刷新</span>}
          </span>
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
        <span className="sr-only">查看 {who} 詳細</span>
      </a>

      {/* #68：已過期優先於刷新失敗——月份過完的劇本不會因為留著一筆
          舊的失敗紀錄，就在「已過期，不再刷新」旁邊又冒出一個「重試」
          （重試也只會被後端當成無害的 no-op，按了等於沒按，不該讓它
          看起來像有用）。與舊 Streamlit workspace 的紅燈優先於黃燈是
          同一個判斷。 */}
      {failure && !row.expired && (
        <div className="notice error" role="alert">
          <div className="row-value">{failureLabel(failure.stage)}</div>
          <p className="caption">{failure.message}</p>
          <button
            className="text-button"
            onClick={() => onRetry(row.id)}
            aria-label={`重試 ${who}`}
          >
            重試
          </button>
        </div>
      )}

      <div className="card-actions">
        <button
          className="text-button"
          onClick={() => onArchive(row.id)}
          aria-label={`封存 ${who}`}
        >
          封存
        </button>
      </div>
    </li>
  );
}

export default function ScenarioList({
  rows,
  failures,
  now,
  selectedId = null,
  onArchive,
  onRetry,
}: {
  rows: ScenarioSummary[];
  failures: Record<string, RefreshFailure>;
  now: Date;
  /** 桌面版 master/detail（#72）目前選中的劇本；手機版不傳，恆不標記。 */
  selectedId?: string | null;
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
            selected={row.id === selectedId}
            onArchive={onArchive}
            onRetry={onRetry}
          />
        ))}
      </ul>
    </>
  );
}
