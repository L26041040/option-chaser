/**
 * 手機首頁的高密度劇本庫（MVP-v2／#77、#82）：三層 compact row，
 * 取代舊的大型 `.card`。#108 起桌面版 `ScenarioList.tsx` 的卡片也改用
 * 同一組 CSS class（視覺密度趨同），但那是獨立的元件與檔案，本檔的
 * `CompactScenarioCard` 本身不動、不被桌面版共用。
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
import { CheckIcon, EditIcon, TrashIcon } from "./icons";
import { detailHash } from "./route";
import {
  cardFailureHeadline,
  cardFailureVariant,
  failureLabel,
  formatAnalyzedAt,
  formatDaysLeft,
  formatRepresentativeExpiry,
  formatRepresentativeSummary,
  formatReturn,
  hasPriceRange,
  hasResult,
  isRetryDisabledByRateLimit,
  isStale,
  money,
  moneyOrDash,
  rateLimitDetailText,
  scenarioSignal,
  signalLabel,
  sortScenarios,
} from "./scenarios";
import { useCountdownSeconds } from "./useCountdown";

function CompactScenarioCard({
  row,
  failure,
  now,
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
  /** 這個劇本正在被刷新（PC-05／#202，spec #198：恢復 T08／#196 P1
   *  當時拿掉的鎖定——反灰＋不可點入，避免使用者在更新過程中點進去
   *  看到一份即將被取代的舊資料卻不知道畫面正在改變）：標「更新中」
   *  徽章、列項反灰、點擊不導向詳細頁。這個劇本自己的結果一落地
   *  （成功或失敗）就立刻從 `updatingIds` 移除、解鎖，不等同批其他
   *  劇本跑完。 */
  updating: boolean;
  onArchive: (id: string) => void;
  onEdit: (id: string) => void;
  onRetry: (id: string) => void;
  /** TR6（#91）：批次選取模式——checkbox 取代單筆刪除鈕，整列改成點下
   *  去是選取而不是進詳細頁。 */
  selectMode: boolean;
  isChecked: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const ran = hasResult(row);
  const stale = isStale(row.latest_analyzed_at, now);
  const who = `${row.symbol} ${row.target_month}`;
  const signal = scenarioSignal(row, failure);
  const rep = row.representative_candidate;
  // REPAIR-05（#242，OD-03）：刷新失敗的兩態——`updating` 與 `failure`
  // 是兩個獨立 state，`cardFailureVariant` 已經把兩者互斥的判準收進
  // 純函式，這裡只讀結果決定要不要反灰、顯示哪一句頭條。
  const failureVariant = cardFailureVariant(row, failure, updating);
  // SCALE-05（#260，AC-3）：只在限流失敗時才有倒數可言。
  const rateLimitRemaining = useCountdownSeconds(
    failure?.rateLimit?.blocked_until ?? null);
  const cardClass = [
    "compact-card", updating && "locked", failureVariant && "failed",
  ].filter(Boolean).join(" ");

  return (
    // 這裡的 `isChecked` 是批次選取狀態，跟桌面版 `.card.selected`
    // （master/detail 目前選中的劇本）是不同概念——compact row 沒有
    // 對應的常駐詳細頁高亮，選取狀態完全交給下面的 checkbox 外觀表達，
    // 不重用會撞名的 class。
    <li className={cardClass}>
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
            完全不用重寫一份（沿用 `ScenarioList.tsx` 同一種做法）。
            PC-05（#202）：`updating` 時同樣攔截點擊、不導向詳細頁——但
            `selectMode` 優先判斷（AC：既有批次選取互動不受這張票影響，
            更新中的列項一樣勾得起來）。`href` 仍然保留，CSS 用
            `opacity` 反灰而不是 `pointer-events: none`——Playwright
            一般點擊才驗證得出「按下去沒有導航」。 */}
        <a className="compact-card-tap" href={detailHash(row.id)}
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
                不多佔一列高度——沒有現價當基準，一排目標價只是孤立
                數字，劇本庫就失去概覽的作用。 */}
            <span className="compact-target">
              <span className="compact-spot">{moneyOrDash(row.spot)}</span>
              {" → "}
              {money(row.target_price)}　{row.target_month}
            </span>
            {/* T08／#196 P1：燈號講的是上一輪的結果，更新中時換成
                「更新中」徽章，不讓舊燈號看起來像這一輪的狀態。 */}
            {updating ? (
              <span className="tag updating-tag">更新中</span>
            ) : (
              <span
                className={`signal-dot signal-${signal}`}
                title={signalLabel(signal)}
                aria-hidden="true"
              />
            )}
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
              {formatRepresentativeSummary(rep)}
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

          {/* 最高／最低只在使用者真的填了才畫——兩端都空就不該憑空多
              佔一列（compact row 的整個設計目的就是密度）。 */}
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

        {/* 封存入口不搶戲——疊在 tap 區右下角的圖示鈕，不佔用行高，
            掃描時不會被誤讀成金融資訊；要用時仍找得到（判準見 spec
            #77 六）。TR6（#91）：批次選取模式下 tier1 已經有 checkbox，
            不同時顯示兩種「選它」的方式。 */}
        {/* #132：編輯入口排在垃圾桶旁，同樣是不搶戲的圖示鈕——視覺層級
            不該高於劇本本身。手機只給圖示，可及名稱交給 aria-label。 */}
        {!selectMode && (
          <div className="compact-actions">
            <button
              className="icon-button"
              onClick={() => onEdit(row.id)}
              aria-label={`編輯 ${who}`}
            >
              <EditIcon />
            </button>
            <button
              className="icon-button"
              onClick={() => onArchive(row.id)}
              aria-label={`封存 ${who}`}
            >
              <TrashIcon />
            </button>
          </div>
        )}
      </div>

      {/* #68：已過期優先於刷新失敗；REPAIR-05（#242）：`updating` 期間
          同樣不顯示（沿用詳細頁 `ScenarioDetail.tsx` 既有的
          `!updating && failure` 互斥判斷，`cardFailureVariant` 已經
          把三個條件收進同一個純函式）。頭條文案依兩態不同（曾成功過
          ／從未成功過），技術性的分層說明仍照舊附在下面。 */}
      {/* `failureVariant && failure` 而非只判斷前者：`cardFailureVariant`
          回傳非 null 時 `failure` 邏輯上必為真，但 TS 看不出兩者的
          關聯——這裡讓型別系統自己窄化，下面才不必逐處補 `failure!`
          非空斷言。 */}
      {failureVariant && failure && (
        <div className="notice error compact-notice" role="alert">
          <span className="compact-notice-text">
            <span className="compact-notice-headline">
              {cardFailureHeadline(failureVariant)}
            </span>
            <span className="compact-notice-detail">
              {/* SCALE-05（#260，AC-2）：限流失敗改講「誰的問題、還要
                  等多久」（結構化倒數，不是解析 message 字串）。 */}
              {failure.stage === "rate_limited" && failure.rateLimit
                ? rateLimitDetailText(failure.rateLimit, rateLimitRemaining ?? 0)
                : `${failureLabel(failure.stage)}：${failure.message}`}
            </span>
          </span>
          <button
            className="text-button"
            onClick={() => onRetry(row.id)}
            aria-label={`重試 ${who}`}
            disabled={isRetryDisabledByRateLimit(failure, rateLimitRemaining)}
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
  updatingIds,
  now,
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
  onArchive: (id: string) => void;
  onEdit: (id: string) => void;
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
    return <p className="caption">還沒有劇本，用上面的「＋ 新增劇本」建立。</p>;
  }
  // T08／#196 P1：正在更新的劇本照樣參與排序（用它上一輪的
  // `best_return`），不再像舊版 `partitionByLock`（V4 跟進票／#136，
  // 已隨本票移除）那樣獨立排在後面——見 `./scenarios` 的
  // `sortScenarios` 說明。
  const sorted = sortScenarios(rows);
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
        {sorted.map((row) => (
          <CompactScenarioCard
            key={row.id}
            row={row}
            failure={failures[row.id]}
            now={now}
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
