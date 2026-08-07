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
import { CheckIcon, TrashIcon } from "./icons";
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
  selectMode,
  isChecked,
  onToggleSelect,
}: {
  row: ScenarioSummary;
  failure: RefreshFailure | undefined;
  now: Date;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取模式——checkbox 取代單筆刪除鈕，整列改成點下
   *  去是選取而不是進詳細頁。 */
  selectMode: boolean;
  isChecked: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const ran = row.best_return !== null;
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
  const signal = scenarioSignal(row, failure);
  const rep = row.representative_candidate;

  return (
    // 這裡的 `isChecked` 是批次選取狀態，跟桌面版 `.card.selected`
    // （master/detail 目前選中的劇本）是不同概念——compact row 沒有
    // 對應的常駐詳細頁高亮，選取狀態完全交給下面的 checkbox 外觀表達，
    // 不重用會撞名的 class。
    <li className="compact-card">
      {/* 封存鈕疊在「這一塊」（tap 區）的右下角，而不是整張 `<li>` 的
          右下角——code review 抓到的真實回歸：`.compact-notice`（刷新
          失敗時才出現）是接在 tap 區後面的正常流內容，會把卡片整體
          撐高；封存鈕若相對整張卡片定位，失敗時就會飄到 notice 的
          右下角，正好疊在「重試」鈕上，使用者想點重試卻誤觸封存。
          `position: relative` 收在這層 wrapper，封存鈕的錨點永遠是
          tap 區本身的高度，跟 notice 在不在完全無關。 */}
      <div className="compact-card-tap-area">
        {/* 不掛 `aria-label`：那會取代連結內容當成可及名稱，螢幕閱讀器
            就只聽得到症狀簡述，三層資訊全部被吃掉。改在結尾補一段只有
            輔助技術讀得到的字（沿用 `ScenarioList.tsx` 既有寫法）。 */}
        {/* TR6（#91）：批次選取模式時整列攔截點擊改成切換選取，不導向
            詳細頁——`preventDefault` 而不是換成 `<button>`，內容結構
            完全不用重寫一份（沿用 `ScenarioList.tsx` 同一種做法）。 */}
        <a className="compact-card-tap" href={detailHash(row.id)}
           onClick={(e) => {
             if (selectMode) {
               e.preventDefault();
               onToggleSelect(row.id);
             }
           }}>
          <div className="compact-tier1">
            {selectMode && (
              <span
                className={isChecked ? "row-checkbox checked" : "row-checkbox"}
                aria-hidden="true"
              >
                {isChecked && <CheckIcon />}
              </span>
            )}
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

        {/* 封存入口不搶戲——疊在 tap 區右下角的圖示鈕，不佔用行高，
            掃描時不會被誤讀成金融資訊；要用時仍找得到（判準見 spec
            #77 六）。TR6（#91）：批次選取模式下 tier1 已經有 checkbox，
            不同時顯示兩種「選它」的方式。 */}
        {!selectMode && (
          <button
            className="icon-button compact-archive"
            onClick={() => onArchive(row.id)}
            aria-label={`封存 ${who}`}
          >
            <TrashIcon />
          </button>
        )}
      </div>

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
    </li>
  );
}

export default function CompactScenarioList({
  rows,
  failures,
  now,
  onArchive,
  onRetry,
  selectMode,
  selectedIds,
  onToggleSelect,
  onEnterSelectMode,
  onCancelSelectMode,
  onConfirmBatchArchive,
}: {
  rows: ScenarioSummary[];
  failures: Record<string, RefreshFailure>;
  now: Date;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取移入垃圾桶，語意同 `ScenarioList.tsx`。 */
  selectMode: boolean;
  selectedIds: ReadonlySet<string>;
  onToggleSelect: (id: string) => void;
  onEnterSelectMode: () => void;
  onCancelSelectMode: () => void;
  onConfirmBatchArchive: () => void;
}) {
  if (rows.length === 0) {
    return <p className="caption">還沒有劇本。用上面的「＋ 新增劇本」建立第一個。</p>;
  }
  return (
    <>
      {/* 收益率口徑就寫在數字旁邊（V4／#52 既有裁示），沿用大卡片版式
          同一句話，compact 版不因為省空間就把它拿掉。TR6（#91）：批次
          選取入口貼在同一列右側。 */}
      <div className="yield-note-row">
        <p className="caption">
          收益率以最差成交價計算（買腿 Ask − 賣腿 Bid）
        </p>
        {!selectMode && (
          <button
            className="icon-button"
            onClick={onEnterSelectMode}
            title="選取要移入垃圾桶的劇本"
            aria-label="選取要移入垃圾桶的劇本"
          >
            <TrashIcon />
          </button>
        )}
      </div>

      {selectMode && (
        <div className="select-mode-bar">
          <span className="caption">選取要移入垃圾桶的劇本</span>
          <button className="text-button" onClick={onCancelSelectMode}>
            取消
          </button>
        </div>
      )}

      <ul className="compact-list">
        {sortScenarios(rows).map((row) => (
          <CompactScenarioCard
            key={row.id}
            row={row}
            failure={failures[row.id]}
            now={now}
            onArchive={onArchive}
            onRetry={onRetry}
            selectMode={selectMode}
            isChecked={selectedIds.has(row.id)}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </ul>

      {selectMode && (
        <div className="batch-action-bar">
          <span className="caption">已選 {selectedIds.size} 個</span>
          <button
            className="batch-pill"
            disabled={selectedIds.size === 0}
            onClick={onConfirmBatchArchive}
          >
            移入垃圾桶
          </button>
        </div>
      )}
    </>
  );
}
