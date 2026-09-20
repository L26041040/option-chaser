/**
 * 劇本清單的純函式（V3／#51）：排序與格式化。
 *
 * 這裡沒有金融計算——`best_return` 是引擎算好的（`store.best_return`，
 * 與詳細頁主圖同一口徑），`days_to_anchor` 也是後端依「該月第三個星期五」
 * 與紐約日曆算好的。本檔只決定「怎麼排、怎麼寫」。
 */
import {
  formatLegs,
  type FailureStage,
  type RateLimitInfo,
  type RefreshFailure,
  type RepresentativeCandidate,
  type ScenarioSummary,
} from "./api";
import { directionLabel, strategyLabel } from "./detail";
import { FAMILY_LABELS, familyOf } from "./family";

/**
 * 依最新收益率降序；還沒跑過分析的（`best_return === null`）一律排最後；
 * 紅燈（`expired`，目標月已過完）一律沉底，排在所有綠燈與黃燈之後——
 * MVP-v2（#77、#80）補上這條鍵，紅燈組內部仍沿用同一套報酬率排序。
 *
 * 理由：已經不會再更新的劇本若因報酬率高就佔住高密度清單的頂端，是
 * 主動誤導（見附錄 A：舊 Streamlit 版 `workspace.sort_cards()` 早就有
 * 這條規則，React 版直到本輪才補上）。
 *
 * 沒跑過 ≠ 收益率 0：拿 0 代入排序會讓一個未知的劇本插在虧損劇本前面，
 * 憑空得到一個它沒有的名次。同為 null 者維持傳入順序（`sort` 穩定），
 * 也就是後端的 created_at 順序。
 *
 * 一輪刷新（T08／#196，P1「更新中徽章」取代整段灰化鎖定）進行中的
 * 劇本**照樣參與排序**，用它上一輪的 `best_return`（卡片同時顯示
 * Updating 徽章與舊資料時間戳，見 `App.tsx`）——不像舊版
 * `partitionByLock`（V4 跟進票／#136，已隨本票移除）那樣把它們獨立
 * 排在後面。理由：使用者現在看得到、點得進去的正是這份舊資料，讓它
 * 消失在清單順序裡才是誤導；新結果一到，它自然依新數字重新排列。
 */
export function sortScenarios(rows: ScenarioSummary[]): ScenarioSummary[] {
  return [...rows].sort((a, b) => {
    if (a.expired !== b.expired) return a.expired ? 1 : -1;
    if (a.best_return === null && b.best_return === null) return 0;
    if (a.best_return === null) return 1;
    if (b.best_return === null) return -1;
    return b.best_return - a.best_return;
  });
}

/**
 * 劇本級燈號（MVP-v2／#77、#80，沿用附錄 A12 語意）：紅 > 黃 > 綠，
 * 一張卡只有一個燈。
 *
 * - 紅：目標月已過完（`expired`）——不會再刷新了，優先於其他一切狀態。
 * - 黃：本次刷新失敗（`failure` 存在）——沿用上一份成功快照的數字與
 *   時間；「舊資料」標記與燈號並存，各自說各自的事（久沒刷新 ≠ 刷新
 *   失敗）。
 * - 綠：其餘，含尚未分析（附錄 A10.2：綠燈＋「—」，不是失敗）。
 *
 * 判準與資料全部沿用既有欄位（`row.expired`、呼叫端的 `failures` map），
 * 不新增任何端點。
 */
export type Signal = "red" | "yellow" | "green";

export function scenarioSignal(
  row: ScenarioSummary,
  failure: RefreshFailure | undefined,
): Signal {
  if (row.expired) return "red";
  if (failure) return "yellow";
  return "green";
}

/**
 * 燈號的可及文字——只給螢幕閱讀器／`title`，顏色本身不能是唯一的資訊
 * 管道。刻意加「狀態：」前綴、且不逐字複述卡片上既有的「已過期，不再
 * 刷新」標籤或失敗提示——那兩處各自的完整說明還在原本的位置，這裡只是
 * 讓燈號本身也讀得出來，兩者疊在一起念也不會變成同一句話重複兩次。
 */
export function signalLabel(signal: Signal): string {
  switch (signal) {
    case "red":
      return "狀態：已過期";
    case "yellow":
      return "狀態：刷新失敗";
    case "green":
      return "狀態：正常";
  }
}

/** 收益率；沒跑過就是「—」，不是 0%。 */
export function formatReturn(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

/**
 * 劇本方向衍生標籤（OG-09／#319）：純顯示用途，鏡射後端
 * `derive_direction()`（`option_chaser/models.py`，T08／#225 既有
 * 語意——目標價相對現價、無容忍帶）同一條規則，不落盤、不回寫、不
 * 參與任何排序或選取邏輯，只是把「這個劇本現在算看漲還是看跌」畫在
 * 清單卡片上。`spot`（`ScenarioSummary.spot`）為 `null`（劇本尚未
 * 成功分析過）時方向無從判斷，回傳 `null`——呼叫端不畫任何標籤，跟
 * 卡片其餘欄位「尚未分析顯示『—』或整行不畫」的既有慣例一致。
 */
export type DirectionTag = "bullish" | "bearish" | "flat";

export function deriveDirectionTag(
  spot: number | null, target: number,
): DirectionTag | null {
  if (spot === null) return null;
  if (target > spot) return "bullish";
  if (target < spot) return "bearish";
  return "flat";
}

/**
 * 目標價所需漲跌幅（OG-03／#320 跟進，OG-ALL-001 核准）：純呈現用的
 * 比例計算 `(target - spot) / spot`——跟 `deriveDirectionTag` 同一種
 * 性質，清單列本來就顯示 `spot`／`target_price` 這兩個數字，這裡只是
 * 把兩者換算成一個百分比給人看，不產生新的財務結論、不影響
 * valuation／ranking／候選挑選（那些仍然完全由引擎決定，這裡不碰）。
 * 與 `ScenarioDetail.tsx` 的 `view.meta.target_move`（引擎算好、放進
 * 分析結果 view 的欄位，只存在於 detail view）刻意分開來源：清單列
 * 用的 `ScenarioSummary` 從未帶過 `target_move`，這裡不冒充那個欄位、
 * 只是拿兩個已知顯示數字做最單純的百分比呈現運算。`spot` 為 `null`
 * （尚未分析）或 `0`（理論上不會發生，防呆用，避免除以零）時無法算，
 * 回傳 `null`，呼叫端不畫這段小字——與 `deriveDirectionTag` 遇到同樣
 * 情況時的既有慣例一致。
 */
export function requiredMovePct(
  spot: number | null, target: number,
): number | null {
  if (spot === null || spot === 0) return null;
  return (target - spot) / spot;
}

/** 方向標籤的中文字＋對應既有 `.tag` 色彩修飾類（OG-01 既有
 *  primitives：`.tag.up`／`.tag.down`／`.tag.flat`，跟詳細頁摘要卡
 *  同一套視覺語言）。字彙本身直接重用 `./detail.ts::directionLabel()`
 *  （後端 `DIRECTION_LABELS` 同一份、有漂移測試把關的既有字彙）——
 *  這裡衍生的是「算不算看漲」這件事本身（無容忍帶純比較，
 *  `deriveDirectionTag` 見上），不是「看漲要顯示成什麼字」，兩者不該
 *  各自維護一份中文字串（code review／OG-09 跟進，避免第二份
 *  「看漲／看跌／持平」拷貝跟原本那份字彙漂移）。 */
export function directionTagLabel(tag: DirectionTag): string {
  return directionLabel(tag);
}

export function directionTagClass(tag: DirectionTag): string {
  return tag === "bullish" ? "up" : tag === "bearish" ? "down" : "flat";
}

/**
 * 狀態四分類（OG-03／#320，桌面劇本庫表格「狀態」篩選 chip 用）：
 * 與劇本級燈號（`scenarioSignal`）同一組輸入、但拆得更細——燈號只分
 * 紅／黃／綠三色，這裡把綠燈再依「舊資料」拆成正常／舊資料兩種，因為
 * 篩選列上使用者想單獨挑出「有跑過、但很久沒刷新」這種狀態，跟純粹
 * 「剛跑完、一切正常」是不同的篩選意圖。四類互斥、涵蓋全部劇本：
 * 優先序沿用既有「紅燈優先於黃燈」（#68）＋失敗優先於單純舊資料。
 */
export type ScenarioStatusCategory = "expired" | "failed" | "stale" | "normal";

export function scenarioStatusCategory(
  row: { expired: boolean; latest_analyzed_at: string | null },
  failure: RefreshFailure | undefined,
  now: Date,
): ScenarioStatusCategory {
  if (row.expired) return "expired";
  if (failure) return "failed";
  if (isStale(row.latest_analyzed_at, now)) return "stale";
  return "normal";
}

/** 篩選 chip 的可能值——`"all"` 是兩組篩選各自的預設值（不篩）。 */
export type DirectionFilter = "all" | DirectionTag;
export type StatusFilter = "all" | ScenarioStatusCategory;

/**
 * 純前端篩選（OG-03／#320 AC：「篩選 chip 純前端過濾、不發請求」）——
 * 兩組篩選以 AND 合併，各自預設 `"all"` 時不參與過濾。不改變傳入陣列
 * 的順序，呼叫端仍需自行套用 `sortScenarios()`。
 */
export function filterScenarios(
  rows: ScenarioSummary[],
  failures: Record<string, RefreshFailure>,
  now: Date,
  direction: DirectionFilter,
  status: StatusFilter,
): ScenarioSummary[] {
  return rows.filter((r) => {
    if (direction !== "all" &&
        deriveDirectionTag(r.spot, r.target_price) !== direction) {
      return false;
    }
    if (status !== "all" &&
        scenarioStatusCategory(r, failures[r.id], now) !== status) {
      return false;
    }
    return true;
  });
}

/**
 * 劇本報酬旁的 inline 比例條寬度（OG-03／#320，artifact 桌面劇本庫表格
 * 「劇本報酬」欄）——純視覺標示、不是新的財務指標，只是把已經算好的
 * `best_return` 數值映成 0–100 的長度，讓報酬率在表格裡多一個一眼掃過
 * 的視覺線索（沿用既有 `.bar` primitive，OG-01）。100% 上限單純是視覺
 * 裁切，不是任何門檻或警示。
 */
export function returnBarWidthPct(value: number): number {
  return Math.min(100, Math.abs(value) * 100);
}

/**
 * 距目標月到期日還有幾天。已經過了就說過期幾天——這種劇本還留在清單上
 * 是有意義的資訊，顯示成「0 天」會讓它看起來還有救。
 */
export function formatDaysLeft(days: number): string {
  return days < 0 ? `已過期 ${-days} 天` : `${days} 天`;
}

/**
 * 時間戳的顯示格式。後端給的是 UTC 的 ISO 字串（25 字元），直接印在
 * 手機卡片上又長又不是使用者關心的時區——全站的領域時鐘是紐約
 * （`ny_today`），這裡也用紐約時間顯示，口徑才一致。看不懂的字串原樣
 * 顯示，不假裝。
 */
function formatTimestamp(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString("zh-TW", {
    timeZone: "America/New_York",
    month: "numeric", day: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/**
 * 資料時間。尚未分析（null）說「尚未分析」，不是留白也不是一個舊時間。
 */
export function formatAnalyzedAt(iso: string | null): string {
  if (iso === null) return "尚未分析";
  return formatTimestamp(iso);
}

/** TR6（#91）：垃圾桶清單的「封存於」時間戳，同一套格式。 */
export function formatArchivedAt(iso: string): string {
  return formatTimestamp(iso);
}

export function money(x: number): string {
  return `$${x.toFixed(2)}`;
}

/** 尚未分析（`spot` 為 null）或使用者沒填該端時顯示「—」，不是 0。 */
export function moneyOrDash(x: number | null | undefined): string {
  return x === null || x === undefined ? "—" : money(x);
}

/**
 * 劇本庫卡片要不要多畫一行區間（QA 修正）：兩端都沒填就不畫——那一行
 * 會憑空多佔一列高度，而 compact row 的整個設計目的就是密度。
 */
export function hasPriceRange(
  row: { best_price: number | null; worst_price: number | null },
): boolean {
  return row.best_price !== null || row.worst_price !== null;
}

/**
 * 超過幾小時沒刷新就視為舊資料（V4／#52）。
 *
 * 12 小時的理由：美股一個交易時段是 6.5 小時，12 小時代表「這份報價
 * 已經是上一個時段的了」——是一條說得出口的線，不是隨手取的整數。
 */
export const STALE_AFTER_HOURS = 12;

/**
 * 這張卡上的數字是不是舊資料。`now` 由呼叫端傳入（同一次渲染共用一個
 * 「現在」，而且可測），沿用後端 `_timing_json(today=...)` 的做法。
 *
 * 兩個邊界都刻意不含糊：
 * - 從未分析（null）**不算**舊——卡片已經寫著「尚未分析」，再標一次
 *   「舊資料」只會讓人以為有一份過期的數字在那裡。
 * - 讀不懂的時間戳算舊。無法判斷新鮮度時說「新鮮」是最糟的預設值。
 */
export function isStale(iso: string | null, now: Date): boolean {
  if (iso === null) return false;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return true;
  return now.getTime() - at > STALE_AFTER_HOURS * 3_600_000;
}

/**
 * 代表候選的買賣履約價——「買 118 / 賣 122」（MVP-v2／#77、#78），沿用
 * 詳細頁 `detail.candidateTitle()` 既有的「逐腿列出」慣例，同一個表達
 * 方式在清單卡片與詳細頁不該長得不一樣。單腳候選只有一隻腿，寫成
 * 「買 118」——硬湊一個賣腿會憑空生出一隻不存在的腿。
 *
 * OPTION-CHASER-CLOSEOUT-001：原本用 `findLeg()` 各抓一隻 buy／sell
 * 腿畫成固定兩腿字串，對三腿的 Butterfly champion（買／賣 2 口／買）
 * 會靜默丟掉第二隻 buy 腿，讓卡片看起來像一組舊的兩腿 Vertical
 * Spread——這正是「strategy 名稱是新的、legs／strikes 卻對不上」的
 * 根因：`rep.strategy` 與 `rep.legs` 其實同源自同一個 `rep` 物件，
 * 只是舊版格式化函式本身把第三隻腿弄丟了，不是兩個資料來源不同步。
 * 改為逐腿迭代，對既有兩腿／單腿候選輸出逐字不變（`quantity` 恆為 1
 * 時口數標示回傳空字串），三腿以上的候選才會多印出中腿的口數標示。
 * 迭代邏輯本身與 `detail.ts::candidateTitle()` 逐字相同，抽成
 * `api.ts::formatLegs()` 共用（`/code-review` Standards 軸抓到）。
 *
 * `null`（尚未分析、或該期零合格候選）說「—」，不是編一組假的候選。
 */
export function formatRepresentativeLegs(
  rep: RepresentativeCandidate | null,
): string {
  if (rep === null) return "—";
  return formatLegs(rep.legs);
}

/**
 * OPTION-CHASER-CLOSEOUT-002：Butterfly champion 在劇本庫卡片上的緊湊
 * 履約價字串——「Butterfly 106 / 109 / 112」，只列三個履約價、不帶
 * 買賣方向與口數標示。`formatRepresentativeLegs()` 的完整格式（「買
 * 106 / 賣 2×109 / 買 112」）在卡片固定寬度下容易換行、把卡片撐高
 * （卡片寬高與版面不得變動，見票面明文），詳細頁沒有這個限制、維持
 * 完整格式不變（`detail.candidateTitle()` 沒有 Butterfly 分支）。
 *
 * 用 `FAMILY_LABELS.butterfly`（"Butterfly"）而非 `strategyLabel()`
 * 給的 subtype 名稱（「Call Butterfly」／「Put Butterfly」）當前綴
 * ——票面給的範例格式就是單一個「Butterfly」，不分 call／put，卡片上
 * 已經有履約價可以判斷方向，不需要再重複一次。
 *
 * 履約價順序沿用 `rep.legs` 既有排列（後端 `store.py::_candidate()`
 * 建構 Butterfly 的 `legs` 時已經是 `[low_leg, mid_leg, high_leg]`
 * 由小到大——見 `option_chaser/store.py` 的 `_leg(v.low_leg, ...)`／
 * `_leg(v.mid_leg, ...)`／`_leg(v.high_leg, ...)` 三行），這裡不重新
 * 排序、不做任何金融判斷，純粹格式化既有欄位。
 */
function formatButterflyStrikes(rep: RepresentativeCandidate): string {
  return `${FAMILY_LABELS.butterfly} ${rep.legs.map((leg) => leg.strike).join(" / ")}`;
}

/**
 * 劇本庫卡片第二層「策略＋履約價」那句完整字串（MVP-v2／#77、#78 起
 * 的既有格式）。`ScenarioList.tsx`／`CompactScenarioList.tsx` 原本
 * 各自重複同一句 `${strategyLabel(rep.strategy)}
 * ${formatRepresentativeLegs(rep)}` 三元運算式，這裡收斂成一個函式
 * 共用；OPTION-CHASER-CLOSEOUT-002 起 Butterfly champion 走
 * `formatButterflyStrikes()` 緊湊分支，Single-leg／Vertical Spread
 * 維持原本「策略名稱＋完整買賣履約價」格式逐字不變。
 */
export function formatRepresentativeSummary(
  rep: RepresentativeCandidate | null,
): string {
  if (rep === null) return "—";
  if (familyOf(rep.strategy) === "butterfly") return formatButterflyStrikes(rep);
  return `${strategyLabel(rep.strategy)}　${formatRepresentativeLegs(rep)}`;
}

/**
 * 代表候選的實際到期日（MVP-v2／#77、#78）——與劇本的「目標年月」是
 * 兩件不同的事：前者是引擎在候選池裡選中的那一天，後者是使用者當初
 * 設定的假設。兩者格式故意不同（這裡原樣印 `YYYY-MM-DD`、目標年月是
 * `YYYY-MM`），降低卡片上被讀錯成同一件事的機會。
 */
export function formatRepresentativeExpiry(
  rep: RepresentativeCandidate | null,
): string {
  return rep === null ? "—" : rep.expiry;
}

/** 這個劇本是否至少成功分析過一次——`best_return` 由已落盤的
 *  `ResultRecord` 導出，非 null 就代表存在至少一份可看的結果。 */
export function hasResult(row: { best_return: number | null }): boolean {
  return row.best_return !== null;
}

/**
 * 刷新失敗卡片的兩態（OD-03／#242，REPAIR-05）：
 * - `"known"`——曾經至少成功分析過，卡片目前顯示的是上一次成功結果。
 * - `"unknown"`——從未成功分析過（含新建劇本首次刷新即失敗），沒有
 *   任何結果可看。
 *
 * `updating` 與 `failure` 是兩個獨立 state，不得混用——回傳 `null`
 * 代表這個時間點不該顯示失敗狀態，交給更新中徽章或正常燈號表達：
 * 正在刷新（`updating`，這次嘗試還沒有結論）、已過期（`row.expired`，
 * #68 既有規則：紅燈優先於黃燈，不再花力氣區分兩態）、或根本沒有
 * `failure` 這三種情況皆回 `null`。
 */
export type CardFailureVariant = "known" | "unknown";

export function cardFailureVariant(
  row: { best_return: number | null; expired: boolean },
  failure: RefreshFailure | undefined,
  updating: boolean,
): CardFailureVariant | null {
  if (updating || !failure || row.expired) return null;
  return hasResult(row) ? "known" : "unknown";
}

/** 兩態各自的頭條文案——技術性的 `failureLabel`／`failure.message`
 *  仍照舊顯示在旁邊，這句話回答的是使用者最先想知道的事：「我現在
 *  看到的這個東西，是不是可以相信？」 */
export function cardFailureHeadline(variant: CardFailureVariant): string {
  return variant === "known"
    ? "更新失敗，目前顯示上一次成功結果"
    : "尚無可用分析結果";
}

/**
 * 刷新失敗的分層標題（V4／#52）。後端 `detail.stage` 已經說明是哪一個
 * 環節出的事，這裡把它翻成使用者能據以行動的一句話——只寫「刷新失敗」
 * 的話，重試有沒有意義使用者無從判斷。
 */
export function failureLabel(stage: FailureStage): string {
  switch (stage) {
    case "fetch":
      return "抓不到報價（可稍後重試）";
    case "analyze":
      return "分析沒跑完（重試多半無效，請回報）";
    case "params":
      return "這個劇本的參數目前無法分析";
    case "archived":
      return "劇本已在垃圾桶，不再刷新";
    case "rate_limited":
      return "資料來源目前限流中";
    case "vendor_budget_exhausted":
      return "今日查詢預算已用完，稍後或明天再試";
    default:
      return "刷新失敗";
  }
}

/**
 * SCALE-05（#260，AC-3）：backoff 視窗還剩幾秒——用戶端自己的時鐘
 * （`nowMs` 通常來自 `useCountdownSeconds()` 每秒重新讀一次的
 * `Date.now()`）減去伺服器給的絕對時間點 `blockedUntil`，不是從伺服器
 * 回應當下算出的 `remaining_seconds` 往下數；rerender／props 沒變不會
 * 重設倒數，因為來源永遠是同一個固定的絕對時間點。解析失敗（讀不懂的
 * 時間字串）視同已經到期，不讓一個壞掉的時間戳把重試鈕永久鎖住。
 */
export function rateLimitRemainingSeconds(
  blockedUntil: string, nowMs: number,
): number {
  const deadline = Date.parse(blockedUntil);
  if (Number.isNaN(deadline)) return 0;
  return Math.max(0, Math.ceil((deadline - nowMs) / 1000));
}

/** 倒數本身的顯示句——歸零時換成「可以重試了」，不是顯示「0 秒」。 */
export function rateLimitCountdownText(remainingSeconds: number): string {
  return remainingSeconds > 0
    ? `還要等約 ${remainingSeconds} 秒才能重試`
    : "可以重試了";
}

/**
 * 持續性事故（`incident`）與偶發限流用不同文案（票面：「sustained
 * incident 使用明確 data-source 文案，與 scenario params/analyze
 * failure 分開」）——都指名 Cboe，讓使用者知道這不是這個劇本本身的
 * 問題，而是資料來源那一端的事，不是自己劇本的參數或分析出了錯。
 */
export function rateLimitHeadline(incident: boolean): string {
  return incident
    ? "Cboe 資料來源持續受限，非本站或這個劇本本身的問題"
    : "Cboe 資料來源目前限流中";
}

/**
 * 卡片／詳細頁三處共用的限流狀態詳情句——`remainingSeconds` 由呼叫端
 * 透過 `useCountdownSeconds(rateLimit.blocked_until)` 算好傳入（純
 * 函式本身不能呼叫 hook），避免三處各自重寫「headline＋倒數」怎麼
 * 拼句子的邏輯。
 */
export function rateLimitDetailText(
  rateLimit: RateLimitInfo, remainingSeconds: number,
): string {
  return `${rateLimitHeadline(rateLimit.incident)}：` +
    rateLimitCountdownText(remainingSeconds);
}

/**
 * 限流視窗內重試鈕該不該 disabled（AC-3：到期後可重新嘗試；Regression
 * Red Line：不允許 backoff window 內 client retry storm）。非限流失敗
 * 一律不受影響——沿用既有「隨時可按重試」行為。`remainingSeconds` 為
 * `null`（`useCountdownSeconds` 對 `blockedUntil=null` 的回傳）視同
 * 沒有倒數在跑，不擋。
 */
export function isRetryDisabledByRateLimit(
  failure: RefreshFailure | undefined, remainingSeconds: number | null,
): boolean {
  return failure?.stage === "rate_limited" && (remainingSeconds ?? 0) > 0;
}

/**
 * 一輪刷新（T08／#196，P2）結束後的摘要——「N 成功／M 失敗」。全部
 * 成功時省略失敗那一半（沒有失敗可講時不必硬湊一個「0 失敗」）。
 */
export function formatRunSummary(succeeded: number, failed: number): string {
  return failed > 0 ? `${succeeded} 成功／${failed} 失敗` : `${succeeded} 成功`;
}

/**
 * A2：劇本卡片的 DOM `id`——`App.tsx` 建立成功後用它查找那張卡片
 * 好捲動並聚焦（`document.getElementById`）；`ScenarioList.tsx`／
 * `CompactScenarioList.tsx` 把它掛在各自的 `<li>` 上。三處共用同一個
 * 函式而不是各自寫死同一段字串模板——`/code-review` Standards 軸抓到
 * 的 judgement call，這是本專案第一次出現跨元件 DOM id 約定，值得跟
 * 既有 `fetchCache.ts`／`route.ts` 一樣抽成單一事實來源，不必等到
 * 出現第三個獨立寫法才回頭修。 */
export function scenarioRowDomId(id: string): string {
  return `scenario-row-${id}`;
}
