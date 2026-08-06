/**
 * 劇本清單的純函式（V3／#51）：排序與格式化。
 *
 * 這裡沒有金融計算——`best_return` 是引擎算好的（`store.best_return`，
 * 與詳細頁主圖同一口徑），`days_to_anchor` 也是後端依「該月第三個星期五」
 * 與紐約日曆算好的。本檔只決定「怎麼排、怎麼寫」。
 */
import type {
  FailureStage,
  RepresentativeCandidate,
  ScenarioSummary,
} from "./api";

/**
 * 依最新收益率降序；還沒跑過分析的（`best_return === null`）一律排最後。
 *
 * 沒跑過 ≠ 收益率 0：拿 0 代入排序會讓一個未知的劇本插在虧損劇本前面，
 * 憑空得到一個它沒有的名次。同為 null 者維持傳入順序（`sort` 穩定），
 * 也就是後端的 created_at 順序。
 *
 * 與 Streamlit 版 `workspace.sort_cards()` 的差異：那邊還會把紅燈
 * （刷新失敗）沉底，而燈號屬 V4（#52）刷新與失敗分層的範圍，本票沒有。
 */
export function sortScenarios(rows: ScenarioSummary[]): ScenarioSummary[] {
  return [...rows].sort((a, b) => {
    if (a.best_return === null && b.best_return === null) return 0;
    if (a.best_return === null) return 1;
    if (b.best_return === null) return -1;
    return b.best_return - a.best_return;
  });
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
 * 資料時間。後端給的是 UTC 的 ISO 字串（25 字元），直接印在手機卡片上
 * 又長又不是使用者關心的時區——全站的領域時鐘是紐約（`ny_today`），
 * 這裡也用紐約時間顯示，口徑才一致。
 *
 * 尚未分析（null）說「尚未分析」，不是留白也不是一個舊時間。
 */
export function formatAnalyzedAt(iso: string | null): string {
  if (iso === null) return "尚未分析";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;   // 看不懂就原樣顯示，不假裝
  return at.toLocaleString("zh-TW", {
    timeZone: "America/New_York",
    month: "numeric", day: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

export function money(x: number): string {
  return `$${x.toFixed(2)}`;
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
    default:
      return "刷新失敗";
  }
}
