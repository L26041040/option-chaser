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
import { CheckIcon, EditIcon, TrashIcon } from "./icons";
import { detailHash } from "./route";
import {
  cardFailureHeadline,
  cardFailureVariant,
  failureLabel,
  formatAnalyzedAt,
  formatDaysLeft,
  formatRepresentativeExpiry,
  formatRepresentativeLegs,
  formatReturn,
  hasPriceRange,
  hasResult,
  isStale,
  money,
  moneyOrDash,
  scenarioSignal,
  signalLabel,
  sortScenarios,
} from "./scenarios";

function ScenarioCard({
  row,
  failure,
  now,
  selected,
  updating,
  onArchive,
  onEdit,
  onRetry,
  selectMode,
  isChecked,
  onToggleSelect,
}: {
  row: ScenarioSummary;
  failure: RefreshFailure | undefined;
  now: Date;
  selected: boolean;
  /** 這個劇本正在被刷新（PC-05／#202，spec #198：恢復 T08／#196 P1
   *  當時拿掉的鎖定——反灰＋不可點入，避免使用者在更新過程中點進去
   *  看到一份即將被取代的舊資料卻不知道畫面正在改變）：標「更新中」
   *  徽章、卡片反灰、點擊不導向詳細頁。這個劇本自己的結果一落地
   *  （成功或失敗）就立刻從 `updatingIds` 移除、解鎖，不等同批其他
   *  劇本跑完。 */
  updating: boolean;
  onArchive: (id: string) => void;
  onEdit: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取模式——checkbox 取代單筆刪除鈕，整張卡改成
   *  點下去是選取而不是進詳細頁。 */
  selectMode: boolean;
  isChecked: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const ran = hasResult(row);
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
  // MVP-v2（#77、#80）：劇本級燈號，紅＞黃＞綠、一張卡只有一個燈。
  const signal = scenarioSignal(row, failure);
  const rep = row.representative_candidate;
  // REPAIR-05（#242，OD-03）：刷新失敗的兩態——`updating` 與 `failure`
  // 是兩個獨立 state，`cardFailureVariant` 已經把兩者互斥的判準收進
  // 純函式，這裡只讀結果決定要不要反灰、顯示哪一句頭條。
  const failureVariant = cardFailureVariant(row, failure, updating);

  const cardClass = [
    "compact-card", selected && "selected",
    updating && "locked", failureVariant && "failed",
  ].filter(Boolean).join(" ");

  return (
    <li className={cardClass}>
      {/* 封存鈕疊在「這一塊」（tap 區）的右下角，而不是整張 `<li>` 的
          右下角——沿用 `CompactScenarioList.tsx` 既有教訓：`.compact-notice`
          （刷新失敗時才出現）是接在 tap 區後面的正常流內容，會把卡片
          整體撐高，封存鈕若相對整張卡片定位就會飄到 notice 右下角、疊在
          「重試」鈕上。`position: relative` 收在這層 wrapper，封存鈕的
          錨點永遠是 tap 區本身的高度，跟 notice 在不在無關。 */}
      <div className="compact-card-tap-area">
        {/* 整張卡就是進詳細頁的入口。用真的 `<a>` 而不是掛 onClick 的
            div：長按可以複製連結、返回手勢可用、鍵盤與螢幕閱讀器也認得。
            封存鈕留在連結外面——按鈕不能包在連結裡。
            PC-05（#202）：更新中的卡片仍然給 `href`（結構不變），但
            `onClick` 會 `preventDefault()`——點下去不導向詳細頁，見
            下方 `onClick` 實作與 `.compact-card.locked` CSS。 */}
        {/* 不掛 `aria-label`：那會**取代**連結內容當成可及名稱，螢幕閱讀器
            就只聽得到「TLT 2028-05 詳細」，收益率／目標／到期日／資料
            時間全部被吃掉。改在結尾補一段只有輔助技術讀得到的字。 */}
        {/* #72：桌面版左側清單常駐，`aria-current` 讓螢幕閱讀器也認得
            「目前選中的是哪一個」，不只是視覺上的高亮（手機版
            `CompactScenarioCard` 沒有這個常駐 detail pane，不需要這個
            屬性）。
            TR6（#91）：批次選取模式時整張卡攔截點擊改成切換選取，不導向
            詳細頁——`preventDefault` 而不是換成 `<button>`，內容結構完全
            不用重寫一份。
            PC-05（#202）：`updating` 時同樣攔截點擊、不導向詳細頁——但
            `selectMode` 優先判斷（AC：既有批次選取互動不受這張票影響，
            更新中的卡片一樣勾得起來）。`href` 仍然保留（跟 `selectMode`
            同一種手法：CSS 用 `opacity` 反灰，不是 `pointer-events:
            none`，Playwright 一般點擊才驗證得出「按下去沒有導航」）。 */}
        <a className="compact-card-tap" href={detailHash(row.id)}
           aria-current={selected ? "page" : undefined}
           onClick={(e) => {
             if (selectMode) {
               e.preventDefault();
               onToggleSelect(row.id);
             } else if (updating) {
               e.preventDefault();
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
            {/* QA 修正：現價擠進同一行的目標價前面（`現價 → 目標`），
                不多佔一列高度。與 `CompactScenarioList.tsx` 同一種寫法
                ——兩份清單是同一個東西的兩種版面。 */}
            <span className="compact-target">
              <span className="compact-spot">{moneyOrDash(row.spot)}</span>
              {" → "}
              {money(row.target_price)}　{row.target_month}
            </span>
            {/* T08／#196 P1：更新中時燈號位置換成「更新中」徽章——這一刻
                的燈號（紅／黃／綠）講的是上一輪的結果，這一輪還沒有
                結論，繼續顯示舊燈號會誤導成「這是這次的狀態」。PC-05
                （#202）起卡片本身反灰＋不可點入（見 `cardClass`／
                `onClick`），徽章維持不變（AC 明文：徽章本身不變）。 */}
            {updating ? (
              <span className="tag updating-tag">更新中</span>
            ) : (
              // 顏色不是唯一的資訊管道：`title` 給滑鼠停留時看得到的
              // 文字、圓點本身 `aria-hidden`，可及名稱另外交給 sr-only
              // 那段字。
              <span
                className={`signal-dot signal-${signal}`}
                title={signalLabel(signal)}
                aria-hidden="true"
              />
            )}
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

          {/* 最高／最低只在使用者真的填了才畫，兩端都空就不多佔一列。 */}
          {hasPriceRange(row) && (
            <div className="compact-range">
              <span>最低 {moneyOrDash(row.worst_price)}</span>
              {" · "}
              <span>最高 {moneyOrDash(row.best_price)}</span>
            </div>
          )}

          <span className="sr-only">
            {updating ? `更新中；查看 ${who} 詳細（顯示上一輪的舊資料）`
                      : `${signalLabel(signal)}；查看 ${who} 詳細`}
          </span>
        </a>

        {/* TR6（#91）：單筆刪除改圖示，批次選取模式下 checkbox 已經在上面
            出現，不同時顯示兩種「選它」的方式。 */}
        {/* #132：編輯入口排在垃圾桶旁。桌面帶 `title` 當 tooltip，
            視覺層級與封存同級——都不該高於劇本本身。 */}
        {!selectMode && (
          <div className="compact-actions">
            <button
              className="icon-button"
              onClick={() => onEdit(row.id)}
              aria-label={`編輯 ${who}`}
              title="編輯劇本"
            >
              <EditIcon />
            </button>
            <button
              className="icon-button"
              onClick={() => onArchive(row.id)}
              aria-label={`封存 ${who}`}
              title="移入垃圾桶"
            >
              <TrashIcon />
            </button>
          </div>
        )}
      </div>

      {/* #68：已過期優先於刷新失敗——月份過完的劇本不會因為留著一筆
          舊的失敗紀錄，就在「已過期，不再刷新」旁邊又冒出一個「重試」
          （重試也只會被後端當成無害的 no-op，按了等於沒按，不該讓它
          看起來像有用）。與舊 Streamlit workspace 的紅燈優先於黃燈是
          同一個判斷。REPAIR-05（#242）：`updating` 期間同樣不顯示
          （這次嘗試還沒有結論，沿用詳細頁 `ScenarioDetail.tsx` 既有的
          `!updating && failure` 互斥判斷，`cardFailureVariant` 已經
          把三個條件收進同一個純函式）。頭條文案依兩態不同（曾成功過
          ／從未成功過），技術性的分層說明仍照舊附在下面。 */}
      {failureVariant && (
        <div className="notice error compact-notice" role="alert">
          <span className="compact-notice-text">
            <span className="compact-notice-headline">
              {cardFailureHeadline(failureVariant)}
            </span>
            <span className="compact-notice-detail">
              {failureLabel(failure!.stage)}：{failure!.message}
            </span>
          </span>
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
  updatingIds,
  now,
  selectedId = null,
  onArchive,
  onEdit,
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
  /** 正在被刷新的劇本（T08／#196 P1）——標「更新中」徽章，一完成
   *  （成功或失敗）立刻從這裡移除。 */
  updatingIds: ReadonlySet<string>;
  now: Date;
  /** 桌面版 master/detail（#72）目前選中的劇本；手機版不傳，恆不標記。 */
  selectedId?: string | null;
  onArchive: (id: string) => void;
  onEdit: (id: string) => void;
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
  // T08／#196 P1：正在更新的劇本照樣參與排序（用它上一輪的
  // `best_return`），不再像舊版 `partitionByLock`（V4 跟進票／#136，
  // 已隨本票移除）那樣獨立排在後面——見 `./scenarios` 的
  // `sortScenarios` 說明。
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
            updating={updatingIds.has(row.id)}
            onArchive={onArchive}
            onEdit={onEdit}
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
