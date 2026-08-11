/**
 * 劇本清單（V3／#51；V4／#52 加上新鮮度與失敗分層）。
 *
 * 每張卡片顯示標的／目標價／目標年月／最新收益率／代表候選的策略與買賣
 * 履約價／實際到期日／距到期天數／資料時間（MVP-v2／#77、#78 補上策略／
 * 履約價／實際到期日三項——沒有它們，卡片上的報酬率無法被判讀出自哪一個
 * option combination），並有封存入口（軟刪除：清單消失、資料與紀錄保留）。
 *
 * V4 的兩個新東西都貼在卡片上，而不是全域一顆燈：資料太舊標「舊資料」，
 * 刷新失敗說明是哪一段失敗、旁邊就是重試入口——失敗是**單一劇本**的事，
 * 訊息離它愈近愈好。
 *
 * 排序與格式化都在 `./scenarios` 的純函式裡，這裡只負責畫。
 *
 * 決策 K（#108）：卡片版式改沿用 `CompactScenarioList.tsx` 那組三層
 * compact row class（`.compact-card`／`.compact-tier1/2/3` 等）壓縮留白、
 * 重複 label 與過大字級——七項決策資訊一項不少，只是不再各自佔一整列。
 * 桌面／手機仍是兩個獨立元件、各自的檔案（原因見 `App.tsx` 說明），這裡
 * 只共用 CSS class 命名與視覺密度，不共用渲染路徑，手機版改動不會結構性
 * 牽動這個檔案。
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

function ScenarioCard({
  row,
  failure,
  now,
  selected,
  onArchive,
  onRetry,
  selectMode,
  isChecked,
  onToggleSelect,
}: {
  row: ScenarioSummary;
  failure: RefreshFailure | undefined;
  now: Date;
  selected: boolean;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取模式——checkbox 取代單筆刪除鈕，整張卡改成
   *  點下去是選取而不是進詳細頁。 */
  selectMode: boolean;
  isChecked: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const ran = row.best_return !== null;
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
  // MVP-v2（#77、#80）：劇本級燈號，紅＞黃＞綠、一張卡只有一個燈。
  const signal = scenarioSignal(row, failure);
  const rep = row.representative_candidate;

  return (
    <li className={selected ? "compact-card selected" : "compact-card"}>
      {/* 封存鈕疊在「這一塊」（tap 區）的右下角，而不是整張 `<li>` 的
          右下角——沿用 `CompactScenarioList.tsx` 既有教訓：`.compact-notice`
          （刷新失敗時才出現）是接在 tap 區後面的正常流內容，會把卡片
          整體撐高，封存鈕若相對整張卡片定位就會飄到 notice 右下角、疊在
          「重試」鈕上。`position: relative` 收在這層 wrapper，封存鈕的
          錨點永遠是 tap 區本身的高度，跟 notice 在不在無關。 */}
      <div className="compact-card-tap-area">
        {/* 整張卡就是進詳細頁的入口。用真的 `<a>` 而不是掛 onClick 的
            div：長按可以複製連結、返回手勢可用、鍵盤與螢幕閱讀器也認得。
            封存鈕留在連結外面——按鈕不能包在連結裡。 */}
        {/* 不掛 `aria-label`：那會**取代**連結內容當成可及名稱，螢幕閱讀器
            就只聽得到「TLT 2028-05 詳細」，收益率／目標／到期日／資料
            時間全部被吃掉。改在結尾補一段只有輔助技術讀得到的字。 */}
        {/* #72：桌面版左側清單常駐，`aria-current` 讓螢幕閱讀器也認得
            「目前選中的是哪一個」，不只是視覺上的高亮（手機版
            `CompactScenarioCard` 沒有這個常駐 detail pane，不需要這個
            屬性）。
            TR6（#91）：批次選取模式時整張卡攔截點擊改成切換選取，不導向
            詳細頁——`preventDefault` 而不是換成 `<button>`，內容結構完全
            不用重寫一份。 */}
        <a className="compact-card-tap" href={detailHash(row.id)}
           aria-current={selected ? "page" : undefined}
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
            {/* 顏色不是唯一的資訊管道：`title` 給滑鼠停留時看得到的文字、
                圓點本身 `aria-hidden`，可及名稱另外交給 sr-only 那段字。 */}
            <span
              className={`signal-dot signal-${signal}`}
              title={signalLabel(signal)}
              aria-hidden="true"
            />
          </div>

          {/* 第二層是全卡最醒目的資訊：報酬率＋策略＋買賣履約價
              （MVP-v2／#77、#78：沒有策略／履約價，報酬率無法被判讀出自
              哪一個 option combination）。`null` 代表尚未分析或該期零
              合格候選，說「—」而不是編一組假的候選。 */}
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

          {/* 第三層：低權重資訊合併一行——實際到期日／距到期天數／資料
              時間，不再各自佔一整列。每個格式化值各自一個 span、分隔號
              是獨立文字節點，`formatAnalyzedAt("尚未分析")` 之類的完整
              字串不會被分隔號黏成一段查不到精確文字的字串。 */}
          <div className="compact-tier3">
            <span>Exp {formatRepresentativeExpiry(rep)}</span>
            {" · "}
            <span>{formatDaysLeft(row.days_to_anchor)}</span>
            {" · "}
            <span>{formatAnalyzedAt(row.latest_analyzed_at)}</span>
            {/* 久未刷新明講「舊資料」：數字還是上一次算出來的真數字，
                只是不能當成現在的。 */}
            {stale && <span className="tag warn">舊資料</span>}
            {/* #68：目標月已過完的劇本不再花資源刷新，卡片上要看得出
                「不是刷新失敗、也不是還沒分析過」，是第三種、刻意的
                狀態——見下面失敗提示的互斥處理。 */}
            {row.expired && <span className="tag">已過期，不再刷新</span>}
          </div>

          <span className="sr-only">
            {signalLabel(signal)}；查看 {who} 詳細
          </span>
        </a>

        {/* TR6（#91）：單筆刪除改圖示，批次選取模式下 checkbox 已經在上面
            出現，不同時顯示兩種「選它」的方式。 */}
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

      {/* #68：已過期優先於刷新失敗——月份過完的劇本不會因為留著一筆
          舊的失敗紀錄，就在「已過期，不再刷新」旁邊又冒出一個「重試」
          （重試也只會被後端當成無害的 no-op，按了等於沒按，不該讓它
          看起來像有用）。與舊 Streamlit workspace 的紅燈優先於黃燈是
          同一個判斷。 */}
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

export default function ScenarioList({
  rows,
  failures,
  now,
  selectedId = null,
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
  /** 桌面版 master/detail（#72）目前選中的劇本；手機版不傳，恆不標記。 */
  selectedId?: string | null;
  onArchive: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取移入垃圾桶。`selectMode` 開著時清單項目變成
   *  可勾選，`onConfirmBatchArchive` 依序（沿用既有序列佇列模式）把
   *  `selectedIds` 全部移入垃圾桶。 */
  selectMode: boolean;
  selectedIds: ReadonlySet<string>;
  onToggleSelect: (id: string) => void;
  onEnterSelectMode: () => void;
  onCancelSelectMode: () => void;
  onConfirmBatchArchive: () => void;
}) {
  if (rows.length === 0) {
    return <p className="caption">還沒有劇本，用下面的表單建立。</p>;
  }
  const sorted = sortScenarios(rows);
  return (
    <>
      {/* 收益率口徑就寫在數字旁邊（V4／#52）。放進說明頁等於沒寫——
          看數字的人不會為了一個百分比先去翻說明。TR6（#91）：批次選取
          入口貼在同一列右側——需求方核准版面的位置。 */}
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
        {sorted.map((row) => (
          <ScenarioCard
            key={row.id}
            row={row}
            failure={failures[row.id]}
            now={now}
            selected={row.id === selectedId}
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
            className="batch-pill danger"
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
