/**
 * 劇本清單的純函式（V3／#51）：排序與格式化。
 *
 * 這裡沒有金融計算——`best_return` 是引擎算好的（`store.best_return`，
 * 與詳細頁主圖同一口徑），`days_to_anchor` 也是後端依「該月第三個星期五」
 * 與紐約日曆算好的。本檔只決定「怎麼排、怎麼寫」。
 */
import type { ScenarioSummary } from "./api";

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
