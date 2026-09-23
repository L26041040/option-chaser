import { useEffect, useSyncExternalStore } from "react";

import { getUsageSummary, type UsageSummary } from "./api";

/**
 * SW-13-USAGE-SUMMARY-REFRESH-001（PR #344 P2 review）：首頁「進行中
 * 劇本／最佳報酬」摘要的共用來源——手機 `MobileStatsStrip` 與桌面
 * `ScenarioList.tsx::UsageStatsStrip` 共讀這一份。
 *
 * 在這之前兩個元件各自「掛載時抓一次、之後不再抓」：`App` 開站那輪
 * 自動刷新、建立／編輯／封存／還原、手動刷新都不會讓它們重新 mount，
 * 數字就停在操作前的舊值，要整頁重新整理才對得上。
 *
 * 修法是「改動端自己說」（同 `fetchCache.invalidateScenarioCache()` 的
 * 既有原則）：`App` 在 mutation／刷新**成功**那一刻呼叫
 * `invalidateUsageSummary()`，這裡負責其餘一切——
 *
 * - 有元件掛著 → 立刻重抓一次，兩個 strip 一起更新（手機／桌面同一份）。
 * - 沒有元件掛著（例如人在垃圾桶頁還原）→ 只標記過期、不發請求，
 *   下一次掛載才抓。
 * - 沒有 invalidate 過 → 重新掛載（切頁回來）沿用手上這份，不重抓——
 *   單純切頁、展開卡片、切 family 不會多出任何 usage-summary 請求。
 * - 請求進行中又被 invalidate → 丟掉那份（它是操作前的快照），結束後
 *   再抓一次；同一時間最多一個請求在飛，回應不會亂序蓋掉新值。
 * - 重抓失敗 → 保留上一份成功的數字（它仍是最後一份已知的後端真相），
 *   標記過期等下一次再試；只有從來沒成功過才顯示錯誤。
 *
 * 不引入外部套件，沿用 `fetchCache.ts` 的模組層級單例做法；但不直接
 * 套 `cachedFetch()`——它沒有「進行中被失效就丟棄並補抓」與「失敗保留
 * 上一份」這兩條語意，硬套反而要在外面再包一層。訂閱改用 React 內建的
 * `useSyncExternalStore`（`useAuthRole.ts` 的 `useState`＋`useEffect`
 * 訂閱在併發渲染下可能讀到撕裂的快照，這裡兩個讀者要保證同一份）。
 */

export interface UsageSummaryState {
  usage: UsageSummary | null;
  error: string | null;
}

const INITIAL: UsageSummaryState = { usage: null, error: null };

let state: UsageSummaryState = INITIAL;
/** 手上這份（或還沒有的那份）需要重抓。 */
let stale = true;
/** 每次 invalidate／reset 遞增——請求結束時比對，判斷它是不是已經過時。 */
let epoch = 0;
let inFlight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: UsageSummaryState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

function load(): void {
  if (!stale || inFlight) return;
  stale = false;
  const startedAt = epoch;
  const request: Promise<void> = getUsageSummary()
    .then(
      (usage) => {
        if (epoch === startedAt) publish({ usage, error: null });
      },
      (e) => {
        if (epoch !== startedAt) return;
        stale = true;
        if (state.usage === null) {
          publish({ usage: null, error: e instanceof Error ? e.message : String(e) });
        }
      },
    )
    .finally(() => {
      if (inFlight !== request) return;   // 中途被 reset 過，不是這一輪的事
      inFlight = null;
      if (epoch !== startedAt && listeners.size > 0) load();
    });
  inFlight = request;
}

/** 會改變摘要的操作**成功後**呼叫（見檔頭）；失敗的操作不要呼叫。 */
export function invalidateUsageSummary(): void {
  epoch += 1;
  stale = true;
  if (!inFlight && listeners.size > 0) load();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): UsageSummaryState {
  return state;
}

export function useUsageSummary(): UsageSummaryState {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot);
  useEffect(() => {
    load();
  }, []);
  return snapshot;
}

/** 測試專用：回到「從沒抓過」的初始狀態，避免測試之間互相汙染。 */
export function _resetUsageSummaryForTests(): void {
  epoch += 1;
  stale = true;
  inFlight = null;
  state = INITIAL;
}
