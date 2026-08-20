/**
 * 劇本清單的純函式（V3／#51）：排序與格式化。
 *
 * 這裡沒有金融計算——`best_return` 是引擎算好的（`store.best_return`，
 * 與詳細頁主圖同一口徑），`days_to_anchor` 也是後端依「該月第三個星期五」
 * 與紐約日曆算好的。本檔只決定「怎麼排、怎麼寫」。
 */
import type {
  FailureStage,
  RefreshFailure,
  RepresentativeCandidate,
  ScenarioSummary,
} from "./api";

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
 * 整輪刷新期間的漸進解鎖（V4 跟進票／#136）：把清單拆成「已完成」（照
 * 舊規則排序）與「還在排隊／刷新中」兩段。
 *
 * 鎖著的那段刻意**不**參與排序：它們的 `best_return` 可能是上一輪的
 * 舊數字，跟著已完成的候選混排會讓一張還沒刷新完的卡片，單純因為舊
 * 收益率夠高就跑到清單很前面——使用者以為那是「這一輪」的名次，其實
 * 只是巧合。鎖著的維持傳入順序（佇列先後），已完成的才套用既有排序。
 */
export function partitionByLock(
  rows: ScenarioSummary[],
  lockedIds: ReadonlySet<string>,
): { unlocked: ScenarioSummary[]; locked: ScenarioSummary[] } {
  const unlocked: ScenarioSummary[] = [];
  const locked: ScenarioSummary[] = [];
  for (const row of rows) {
    (lockedIds.has(row.id) ? locked : unlocked).push(row);
  }
  return { unlocked: sortScenarios(unlocked), locked };
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
 * 詳細頁 `detail.candidateTitle` 既有的「買腿在前、賣腿在後」慣例，同一個
 * 表達方式在清單卡片與詳細頁不該長得不一樣。單腳候選只有一隻腿，寫成
 * 「買 118」——硬湊一個賣腿會憑空生出一隻不存在的腿。
 *
 * `null`（尚未分析、或該期零合格候選）說「—」，不是編一組假的候選。
 */
export function formatRepresentativeLegs(
  rep: RepresentativeCandidate | null,
): string {
  if (rep === null) return "—";
  const [buy, sell] = rep.legs;
  if (!buy) return "—";
  return sell ? `買 ${buy.strike} / 賣 ${sell.strike}` : `買 ${buy.strike}`;
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
    default:
      return "刷新失敗";
  }
}
