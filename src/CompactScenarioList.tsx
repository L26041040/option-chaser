/**
 * 手機首頁的高密度劇本庫（MVP-v2／#77、#82）：三層 compact row，
 * 取代舊的大型 `.card`（`ScenarioList.tsx`，桌面版仍在用、本檔不動它）。
 *
 * 三層資訊分工（spec #77〈Implementation Decisions〉六）：
 * - 第一層：標的 · 目標價 · 目標年月 · 燈號
 * - 第二層（最醒目）：報酬率 · 策略 · 買賣履約價
 * - 第三層（最小字級）：實際到期日 · 距到期天數 · 最後更新時間
 *
 * 壓縮的是留白、裝飾與重複標籤，不是金融資訊——距到期天數、舊資料
 * 標記、刷新失敗與重試、封存入口全部保留，只是不再各自佔一整列高度。
 *
 * 整列仍是真正的連結（不是掛 `onClick` 的 div）：長按可複製、返回手勢
 * 可用、鍵盤與螢幕閱讀器也認得，沿用 V5／#53 既有的決定。封存鈕不能
 * 巢狀在 `<a>` 裡（互動元素不可巢狀互動元素），因此是 `<a>` 的手足、
 * 用 CSS 疊在卡片右下角，不佔用行高。
 */
import type { RefreshFailure, ScenarioSummary } from "./api";
import { strategyLabel } from "./detail";
import { detailHash } from "./route";
import {
  failureLabel,
  formatAnalyzedAt,
  formatDaysLeft,
  formatRepresentativeExpiry,
  formatRepresentativeLegs,
  formatReturn,
  isStale,
  money,
  scenarioSignal,
  signalLabel,
  sortScenarios,
} from "./scenarios";

function CompactScenarioCard({
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
  const signal = scenarioSignal(row, failure);
  const rep = row.representative_candidate;

  return (
    <li className="compact-card">
      {/* 不掛 `aria-label`：那會取代連結內容當成可及名稱，螢幕閱讀器
          就只聽得到症狀簡述，三層資訊全部被吃掉。改在結尾補一段只有
          輔助技術讀得到的字（沿用 `ScenarioList.tsx` 既有寫法）。 */}
      <a className="compact-card-tap" href={detailHash(row.id)}>
        <div className="compact-tier1">
          <span className="compact-symbol">{row.symbol}</span>
          <span className="compact-target">
            {money(row.target_price)}　{row.target_month}
          </span>
          <span
            className={`signal-dot signal-${signal}`}
            title={signalLabel(signal)}
            aria-hidden="true"
          />
        </div>

        <div className="compact-tier2">
          <span
            className={
              ran ? `metric compact-metric ${row.best_return! >= 0 ? "positive" : "negative"}`
                  : "metric compact-metric muted"
            }
          >
            {formatReturn(row.best_return)}
          </span>
          <span className="compact-strategy">
            {rep
              ? `${strategyLabel(rep.strategy)}　${formatRepresentativeLegs(rep)}`
              : "—"}
          </span>
        </div>

        {/* 每個格式化值各自一個 span、分隔號是獨立文字節點：跟桌面版
            `ScenarioList.tsx` 一樣讓 `formatAnalyzedAt("尚未分析")` 之類
            的完整字串各自佔一個節點，不會被分隔號黏成「· 尚未分析」而
            查不到精確文字。 */}
        <div className="compact-tier3">
          <span>Exp {formatRepresentativeExpiry(rep)}</span>
          {" · "}
          <span>{formatDaysLeft(row.days_to_anchor)}</span>
          {" · "}
          <span>{formatAnalyzedAt(row.latest_analyzed_at)}</span>
          {stale && <span className="tag warn">舊資料</span>}
          {/* #68：已過期優先於刷新失敗，同一套判斷沿用 `ScenarioList.tsx`。 */}
          {row.expired && <span className="tag">已過期，不再刷新</span>}
        </div>

        <span className="sr-only">
          {signalLabel(signal)}；查看 {who} 詳細
        </span>
      </a>

      {failure && !row.expired && (
        <div className="notice error compact-notice" role="alert">
          <span>{failureLabel(failure.stage)}：{failure.message}</span>
          <button
            className="text-button"
            onClick={() => onRetry(row.id)}
            aria-label={`重試 ${who}`}
          >
            重試
          </button>
        </div>
      )}

      {/* 封存入口不搶戲——疊在卡片右下角的小字按鈕，不佔用行高，掃描
          時不會被誤讀成金融資訊；要用時仍找得到（判準見 spec #77 六）。 */}
      <button
        className="text-button compact-archive"
        onClick={() => onArchive(row.id)}
        aria-label={`封存 ${who}`}
      >
        封存
      </button>
    </li>
  );
}

export default function CompactScenarioList({
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
    return <p className="caption">還沒有劇本。用上面的「＋ 新增劇本」建立第一個。</p>;
  }
  return (
    <>
      {/* 收益率口徑就寫在數字旁邊（V4／#52 既有裁示），沿用大卡片版式
          同一句話，compact 版不因為省空間就把它拿掉。 */}
      <p className="caption">
        收益率以最差成交價計算（買腿 Ask − 賣腿 Bid）
      </p>
      <ul className="compact-list">
        {sortScenarios(rows).map((row) => (
          <CompactScenarioCard
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
