/**
 * 桌面劇本庫（V3／#51；V4／#52 加上新鮮度與失敗分層；決策 K／#108
 * 卡片瘦身；OG-03／#320 起改為 Binance Markets 式全寬資料表）。
 *
 * 每一列顯示標的／方向／現價／目標價／冠軍策略與買賣履約價／劇本
 * 報酬／淨成本走勢（OG-04／#323：`CostSparkline.tsx` 手刻 SVG 縮圖，
 * 綠紅依首尾方向、缺點斷線，`null` 顯示「—」）／到期／狀態／更新
 * 時間，並有封存入口（軟刪除：清單消失、資料與紀錄保留）。
 *
 * OG-03（#320）把原本分屬 `Toolbar.tsx`（標題／劇本數／刷新）與這裡
 * （收益率口徑說明／批次選取入口）兩處的頁首資訊收斂成同一個
 * `.lib-header`——artifact 的桌面劇本庫板頁首本來就是同一個區塊；
 * `Toolbar.tsx` 隨之零呼叫端、已刪除（見 `App.tsx` 對應說明）。新增
 * 兩組純前端篩選 chip（方向／狀態，`./scenarios::filterScenarios()`），
 * 不打任何新請求、後端與 API 契約零改動。
 *
 * **一處票面字面與現有契約不符，記錄於此、依既有欄位落地**：票面
 * 「方向 tag（衍生三態，讀既有 `direction` 欄位）」——`ScenarioSummary`
 * 上沒有這個欄位（OG-09／#319 code review 的 Spec 軸已查證過同一件
 * 事），沿用 OG-09 已建好的 `deriveDirectionTag(spot, target_price)`
 * 純前端衍生，語意相同、只是計算方式不同。
 *
 * 目標價「所需漲跌幅小字」（OG-ALL-001 對 OG-03 code review 的跟進）：
 * `ScenarioSummary`（清單列）沒有 detail view 才有的 `target_move`
 * 欄位，但 `spot`／`target_price` 兩個顯示數字本來就都在，因此改用
 * `./scenarios::requiredMovePct()` 做單純呈現用的比例計算（不是新增
 * 引擎能力，見該函式 docstring），而不是像先前一版那樣整欄省略。
 *
 * 表格內部的 CSS Grid 版面（`.lib-row-tap`）刻意用複合選擇器
 * `.compact-card-tap.lib-row-tap` 而非取代既有 `.compact-card-tap`
 * 規則——`CompactScenarioList.tsx`（手機版）沿用同一個基底 class 名，
 * 必須維持零改動；本票新增的欄位化排版只在多了 `lib-row-tap` 這個
 * 額外 class 時才生效（見 `styles.css` 對應區塊）。`.compact-card`／
 * `.compact-card-tap`／`.compact-symbol`／`.compact-spot`／
 * `.compact-range`／`.compact-strategy`／`.signal-dot`／`.compact-
 * notice` 等既有 class 逐一保留在原本代表的那塊內容上，既有 Desktop
 * e2e／`ScenarioList.test.tsx` 因此絕大多數零改動即可通過——只有少數
 * 直接依賴「三層堆疊」DOM 形狀本身（而非文字／class 存在性）的測試
 * 需要跟著改寫，改寫處皆附理由註解。
 */
import { useEffect, useState } from "react";
import { getUsageSummary,
        type RefreshFailure, type ScenarioSummary,
        type UsageSummary } from "./api";
import CostSparkline from "./CostSparkline";
import { CheckIcon, EditIcon, TrashIcon } from "./icons";
import { formatMove, strategyLabel } from "./detail";
import { detailHash } from "./route";
import StockLogo from "./StockLogo";
import {
  cardFailureHeadline,
  cardFailureVariant,
  directionTagClass,
  directionTagLabel,
  deriveDirectionTag,
  failureLabel,
  filterScenarios,
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
  requiredMovePct,
  returnBarWidthPct,
  scenarioRowDomId,
  scenarioSignal,
  signalLabel,
  sortScenarios,
  type DirectionFilter,
  type StatusFilter,
} from "./scenarios";
import { useCountdownSeconds } from "./useCountdown";

const DIRECTION_FILTER_OPTIONS: { value: DirectionFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "bullish", label: "看漲" },
  { value: "bearish", label: "看跌" },
  { value: "flat", label: "持平" },
];

const STATUS_FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "normal", label: "正常" },
  { value: "stale", label: "舊資料" },
  { value: "expired", label: "已過期" },
  { value: "failed", label: "失敗" },
];

function ScenarioCard({
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
  // OG-09（#319）：純顯示衍生方向，spot 為 null（尚未分析）時不畫。
  const direction = deriveDirectionTag(row.spot, row.target_price);
  // OG-ALL-001 跟進 OG-03：所需漲跌幅小字，spot 為 null 時同樣不畫
  // （見 `requiredMovePct()` docstring）。
  const requiredMove = requiredMovePct(row.spot, row.target_price);
  // REPAIR-05（#242，OD-03）：刷新失敗的兩態——`updating` 與 `failure`
  // 是兩個獨立 state，`cardFailureVariant` 已經把兩者互斥的判準收進
  // 純函式，這裡只讀結果決定要不要反灰、顯示哪一句頭條。
  const failureVariant = cardFailureVariant(row, failure, updating);
  // SCALE-05（#260，AC-3）：只在限流失敗時才有倒數可言；`blocked_until`
  // 不變就不會啟動計時器（見 `useCountdownSeconds`）。
  const rateLimitRemaining = useCountdownSeconds(
    failure?.rateLimit?.blocked_until ?? null);
  const barWidth = ran ? returnBarWidthPct(row.best_return!) : 0;

  const cardClass = [
    "compact-card", "lib-row",
    updating && "locked", failureVariant && "failed",
    // SW-03（#334）：已過期整列淡化——沿用 #68「已過期優先於刷新
    // 失敗」的既有判斷，`row.expired` 為真時 `failureVariant` 結構上
    // 不會同時成立（見 `cardFailureVariant` docstring），三個修飾
    // class 因此互斥，不會疊加成更暗的 opacity。
    row.expired && "expired",
  ].filter(Boolean).join(" ");

  return (
    // A2：`id` 供 `App.tsx` 建立成功後查找、捲動並聚焦這張卡片——
    // 只是一個 DOM 錨點，不影響任何既有渲染或排序邏輯。
    <li className={cardClass} id={scenarioRowDomId(row.id)}>
      <div className="compact-card-tap-area">
        {/* 整列就是進詳細頁的入口。用真的 `<a>` 而不是掛 onClick 的
            div：長按可以複製連結、返回手勢可用、鍵盤與螢幕閱讀器也
            認得。封存／編輯鈕留在連結外面——按鈕不能包在連結裡，這也
            是 `.compact-actions` 維持是 `.compact-card-tap-area` 的
            手足而非子元素的理由，OG-03 的欄位化排版沒有改變這個結構。
            不掛 `aria-label`：那會**取代**連結內容當成可及名稱，改在
            結尾補一段只有輔助技術讀得到的字。 */}
        <a className="compact-card-tap lib-row-tap" href={detailHash(row.id)}
           onClick={(e) => {
             if (selectMode) {
               e.preventDefault();
               onToggleSelect(row.id);
             } else if (updating) {
               e.preventDefault();
             }
           }}>
          <span className="lib-cell lib-cell-check">
            {selectMode && (
              <span
                className={isChecked ? "row-checkbox checked" : "row-checkbox"}
                aria-hidden="true"
              >
                {isChecked && <CheckIcon />}
              </span>
            )}
          </span>

          {/* 標的：真實品牌 Logo，找不到就整個消失、只留代號文字
              （UI-IMPL-002／#092，Logo.dev `fallback=404` 契約）。 */}
          <span className="lib-cell lib-cell-symbol">
            <StockLogo symbol={row.symbol} size="s" />
            <span className="compact-symbol">{row.symbol}</span>
          </span>

          <span className="lib-cell lib-cell-direction">
            {direction && (
              <span className={`tag ${directionTagClass(direction)}`}>
                {directionTagLabel(direction)}
              </span>
            )}
          </span>

          {/* SW-03（#334，Seed Warm）：現價／目標價合併一欄——「現價
              → 目標價」＋下方一行「還需 ±x% · 目標月」，取代原本兩個
              各自獨立的欄位。`.compact-spot` class 沿用（既有測試
              `ScenarioList.test.tsx` 直接查這個 class 讀現價文字）。 */}
          <span className="lib-cell lib-cell-price r">
            <span>
              <span className="compact-spot">{moneyOrDash(row.spot)}</span>
              <span className="price-arrow" aria-hidden="true"> → </span>
              {money(row.target_price)}　{row.target_month}
            </span>
            {requiredMove !== null && (
              <span className="cell-sub">還需 {formatMove(requiredMove)}</span>
            )}
          </span>

          <span className="lib-cell lib-cell-champion">
            <span className="compact-strategy compact-strategy-pill">
              {formatRepresentativeSummary(rep)}
            </span>
          </span>

          {/* 劇本報酬＋inline 比例條（OG-03／#320，artifact「劇本報酬」
              欄：綠紅＋比例條，純視覺標示，見 `returnBarWidthPct()`
              docstring）。 */}
          <span className="lib-cell lib-cell-return r">
            <span
              className={
                ran ? `metric compact-metric ${row.best_return! >= 0 ? "positive" : "negative"}`
                    : "metric compact-metric muted"
              }
            >
              {formatReturn(row.best_return)}
            </span>
            {ran && (
              <span className="bar" aria-hidden="true">
                <i className={row.best_return! >= 0 ? "g" : "r"}
                   style={{ width: `${barWidth}%` }} />
              </span>
            )}
          </span>

          {/* 淨成本走勢（OG-04／#323）：冠軍候選最近幾次刷新的淨成本
              序列，後端已批次查好、截尾——這裡純渲染，零計算。 */}
          <CostSparkline points={row.cost_sparkline} />

          <span className="lib-cell lib-cell-expiry">
            <span>Exp {formatRepresentativeExpiry(rep)}</span>
            <span className="cell-sub">{formatDaysLeft(row.days_to_anchor)}</span>
          </span>

          {/* 狀態：燈號＋文字＋更新時間，三者合併一欄（SW-03／#334
              起「更新時間」不再是獨立欄位）。失敗兩態的完整說明另外
              在下方 `.compact-notice` 區塊，這裡只給狀態本身一個一致
              的位置，不重複那段文字。T08／#196 P1：更新中時燈號位置
              換成「更新中」徽章——這一刻的燈號講的是上一輪的結果，
              這一輪還沒有結論，繼續顯示舊燈號會誤導成「這是這次的
              狀態」。PC-05（#202）起卡片本身反灰＋不可點入（見
              `cardClass`／`onClick`），徽章維持不變。 */}
          <span className="lib-cell lib-cell-status">
            <span className="lib-status-line">
              {updating ? (
                <span className="tag updating-tag">更新中</span>
              ) : (
                // 顏色不是唯一的資訊管道：`title` 給滑鼠停留時看得到
                // 的文字、圓點本身 `aria-hidden`，可及名稱另外交給
                // sr-only 那段字；`signalLabel` 本身就是可讀文字，
                // SW-03 起直接印在畫面上，不再只靠 title tooltip。
                <>
                  <span
                    className={`signal-dot signal-${signal}`}
                    title={signalLabel(signal)}
                    aria-hidden="true"
                  />
                  <span className="cell-sub">{signalLabel(signal)}</span>
                </>
              )}
            </span>
            {!updating && (
              <span className="cell-sub">
                {formatAnalyzedAt(row.latest_analyzed_at)}
              </span>
            )}
            {/* 久未刷新明講「舊資料」：數字還是上一次算出來的真數字，
                只是不能當成現在的。 */}
            {stale && <span className="tag warn">舊資料</span>}
            {/* #68：目標月已過完的劇本不再花資源刷新，卡片上要看得出
                「不是刷新失敗、也不是還沒分析過」，是第三種、刻意的
                狀態——見下面失敗提示的互斥處理。 */}
            {row.expired && <span className="tag">已過期，不再刷新</span>}
          </span>

          {/* 最高／最低只在使用者真的填了才畫，附在整列下方——這個
              資訊權重低於任何一個主欄位，不佔用固定欄位寬度。 */}
          {hasPriceRange(row) && (
            <span className="lib-cell lib-cell-range compact-range">
              最低 {moneyOrDash(row.worst_price)} · 最高 {moneyOrDash(row.best_price)}
            </span>
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
          <div className="compact-actions lib-row-actions">
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
              {/* SCALE-05（#260，AC-2）：限流失敗改講「誰的問題、還要等
                  多久」（結構化倒數，不是解析 message 字串），其餘失敗
                  沿用既有分層說明。 */}
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

/** 表格頭列——欄位順序與資料列的 `.lib-cell-*` 一一對應（見
 *  `styles.css` 的共用 `grid-template-columns`）。純顯示、`aria-hidden`
 *  ——欄位標籤本身不是操作，畫面上的真正資訊在每一列各自的內容裡，
 *  螢幕閱讀器逐列讀取即可理解每格代表什麼（沿用既有 `.compact-*`
 *  卡片一路的作法：不強加一層 ARIA table 語意）。 */
/**
 * OG-05（#324）：劇本庫頁首 stats strip——「我自己」的使用量，數字
 * 全部由 `GET /api/me/usage-summary` 一次給、前端零推算（票面明文）。
 * 掛載即抓、不快取（跟 `SuperUserAdmin.tsx::OpsStats()` 同一套簡單
 * 慣例——這是操作性統計，不是需要跨頁面共用或需要失效機制的資料）。
 *
 * SW-03（#334，Seed Warm）：原本 Super Admin 額外看到的「Vendor 每日
 * 預算」／「429 事故」兩格（`OpsSuperAdminStats`）整個搬到 Super
 * Admin 後台（`SuperUserAdmin.tsx::OpsStats()`，SW-07／#336 落地）
 * ——SEED-WARM-SPEC-001（#330）「劇本庫只留真正跟這個使用者有關的
 * 數字」的裁示。三格改用 SW-01（#331）`.pstat` primitive，不再借用
 * `SuperUserAdmin.tsx` 的 `Stat`（那是 Super Admin 後台自己的視覺
 * 語彙，兩邊各自換皮、互不牽動）。
 */
function UsageStatsStrip() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getUsageSummary()
      .then((u) => alive && setUsage(u))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => { alive = false; };
  }, []);

  if (error) {
    // 刻意不用 `role="alert"`——這是一個背景 stats 方塊讀取失敗，不是
    // 需要立刻打斷螢幕閱讀器的緊急狀態，也不該跟頁面上真正的表單驗證
    // 警示（例如建立劇本沒勾任何 family）搶同一個 ARIA 語意角色，讓
    // `getByRole("alert")` 之類的查詢誤判成兩個警示同時存在。
    return <p className="notice error">{error}</p>;
  }
  if (!usage) {
    return <p className="caption">用量摘要載入中……</p>;
  }

  return (
    <div className="lib-stats-strip">
      <div className="pstat">
        <span className="pstat-k">進行中劇本</span>
        <span className="pstat-v">
          {usage.quota_exempt
            ? "豁免"
            : usage.max_active_scenarios === null
            ? `${usage.active_scenarios}`
            : `${usage.active_scenarios} / ${usage.max_active_scenarios}`}
        </span>
      </div>
      <div className="pstat">
        <span className="pstat-k">最佳劇本報酬</span>
        {usage.best_return === null ? (
          <span className="pstat-v muted">—</span>
        ) : (
          <>
            <span className={`pstat-v ${usage.best_return >= 0 ? "up" : "down"}`}>
              {formatReturn(usage.best_return)}
            </span>
            <span className="pstat-d">
              {usage.best_return_symbol}
              {usage.best_return_strategy &&
                ` · ${strategyLabel(usage.best_return_strategy)}`}
              {usage.best_return_target_month &&
                ` · ${usage.best_return_target_month}`}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * SW-03（#334，Seed Warm）：欄位從 11 欄收成 9 欄——「現價」／
 * 「目標價」合併成「現價 → 目標價」一欄（見 `ScenarioCard` 的
 * `.lib-cell-price`），「更新時間」併入「狀態」欄（狀態欄本身已經是
 * 色點＋文字，多帶一段時間戳不需要獨立欄位寬度）。
 */
function LibTableHead() {
  return (
    <div className="lib-thead lib-row-tap" aria-hidden="true">
      <span className="lib-cell lib-cell-check" />
      <span className="lib-cell">標的</span>
      <span className="lib-cell">方向</span>
      <span className="lib-cell r">現價 → 目標價</span>
      <span className="lib-cell">冠軍策略</span>
      <span className="lib-cell r">劇本報酬</span>
      <span className="lib-cell">淨成本走勢</span>
      <span className="lib-cell">到期</span>
      <span className="lib-cell">狀態</span>
    </div>
  );
}

export default function ScenarioList({
  rows,
  failures,
  updatingIds,
  now,
  busy,
  runSummary,
  onRefresh,
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
  /** OG-03（#320）：原本 `Toolbar.tsx` 的三個 prop 併入這裡——桌面
   *  劇本庫頁首（標題／劇本數／篩選／刷新）現在是單一元件，不再是
   *  兩個各自獨立渲染、各自維護一部分狀態的 chrome。 */
  busy: boolean;
  runSummary: string | null;
  onRefresh: () => void;
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
  // OG-03（#320）：純前端篩選狀態，不打任何請求——`filterScenarios()`
  // 只是在已載入的 `rows` 上再篩一層，`sortScenarios()` 既有排序邏輯
  // 完全不受影響（篩選在排序之後套用，順序仍由收益率＋紅燈沉底決定）。
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // T08／#196 P1：正在更新的劇本照樣參與排序（用它上一輪的
  // `best_return`），不再像舊版 `partitionByLock`（V4 跟進票／#136，
  // 已隨本票移除）那樣獨立排在後面——見 `./scenarios` 的
  // `sortScenarios` 說明。
  const sorted = sortScenarios(rows);
  const filtered = filterScenarios(
    sorted, failures, now, directionFilter, statusFilter);

  // SW-03（#334）：標題列副標「上次整批更新 HH:MM」——純前端從已經
  // 拿到手的 `rows` 算 max，跟 SW-04（#333）手機首頁同一個判斷，零
  // 新增請求。
  const lastAnalyzedAt = rows.reduce<string | null>((latest, row) => {
    if (row.latest_analyzed_at === null) return latest;
    if (latest === null || row.latest_analyzed_at > latest) {
      return row.latest_analyzed_at;
    }
    return latest;
  }, null);

  return (
    <div className="lib-page">
      <div className="lib-header">
        <div className="lib-header-row">
          <div>
            <h1 className="lib-title">劇本庫</h1>
            <span className="caption">
              {rows.length} 個劇本
              {lastAnalyzedAt !== null &&
                ` · 上次整批更新 ${formatAnalyzedAt(lastAnalyzedAt)}`}
              {runSummary && ` · ${runSummary}`}
            </span>
          </div>
          <div className="lib-header-actions">
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
            <button className="pbtn line sm" onClick={onRefresh} disabled={busy}>
              {busy ? "刷新中……" : "重新整理"}
            </button>
          </div>
        </div>

        {/* OG-05（#324）：stats strip——放在標題列之後、篩選 chip 之前，
            讀的是「這個頁面的身分／用量」，不是列表篩選的一部分。 */}
        <UsageStatsStrip />

        {rows.length > 0 && (
          <div className="lib-filters">
            <div className="seg" role="group" aria-label="依方向篩選">
              {DIRECTION_FILTER_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={directionFilter === opt.value ? "on" : ""}
                  onClick={() => setDirectionFilter(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="依狀態篩選">
              {STATUS_FILTER_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={statusFilter === opt.value ? "on" : ""}
                  onClick={() => setStatusFilter(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* SW-10（#340，Owner 真機驗收）：這句計算口徑說明（V4／#52
            既有裁示）移除——主流程不塞解釋式文案，完整說法收進設定→
            免責聲明（`DisclaimerSection.tsx`）。 */}

        {/* role="status"：螢幕閱讀器會唸出變化，而不是讓使用者自己不斷
            回頭看畫面。進行中優先顯示「更新中」（不論是 Refresh Run 或
            單一劇本刷新），跑完才換成上一輪的「N 成功／M 失敗」摘要——
            兩者互斥，不會同時出現造成「這句話是現在還是剛才」的混淆。 */}
        {busy ? (
          <span className="caption progress" role="status">更新中……</span>
        ) : runSummary && (
          <span className="caption progress" role="status">{runSummary}</span>
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

      {rows.length === 0 ? (
        <p className="caption">還沒有劇本，按右上角「＋ 建立劇本」開始。</p>
      ) : (
        <div className="lib-table">
          <LibTableHead />
          <ul className="compact-list lib-tbody">
            {filtered.map((row) => (
              <ScenarioCard
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
        </div>
      )}

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
    </div>
  );
}
