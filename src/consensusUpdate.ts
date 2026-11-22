/**
 * LIVE-T3（#398）「更新分析師資料」的純函式：重試鈕能不能按、為什麼不能、
 * 還要等多久，以及進度句。元件（`AnalystUpdatePanel.tsx`）只負責呼叫與畫面。
 *
 * 能不能重試的唯一依據是後端給的 `state`＋`next_retry_at`（絕對時間）：冷卻
 * 倒數用使用者自己的時鐘減去 `next_retry_at`，歸零就可以按——按下去後端
 * 仍會再判斷一次（冷卻、重試次數、每日上限、別人正在抓），不靠前端擋。
 */
import type { ConsensusRefreshProgress, ConsensusRefreshSymbol } from "./api";

export interface RetryGate {
  enabled: boolean;
  /** 不能按的原因（可以按時為 `null`）。 */
  reason: string | null;
  /** 冷卻還剩幾秒（只有冷卻中才有）。 */
  remainingSeconds: number | null;
}

/** 失敗（需要重試鈕）的狀態。 */
export const FAILED_STATES = ["cooling", "retry_ready", "exhausted"] as const;

export function isFailed(s: ConsensusRefreshSymbol): boolean {
  return (FAILED_STATES as readonly string[]).includes(s.state);
}

export function secondsUntil(iso: string | null, nowMs: number): number {
  if (iso === null) return 0;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return 0;
  return Math.max(0, Math.ceil((at - nowMs) / 1000));
}

/** 「14 分 05 秒」／「45 秒」。 */
export function formatWait(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m} 分 ${String(s).padStart(2, "0")} 秒`;
}

export function retryGate(s: ConsensusRefreshSymbol, nowMs: number): RetryGate {
  switch (s.state) {
    case "pending":
    case "retry_ready":
      return { enabled: true, reason: null, remainingSeconds: null };
    case "cooling": {
      const left = secondsUntil(s.next_retry_at, nowMs);
      return left > 0
        ? { enabled: false, reason: `上次失敗，冷卻中，還要約 ${formatWait(left)}才能重試`,
            remainingSeconds: left }
        : { enabled: true, reason: null, remainingSeconds: 0 };
    }
    case "exhausted":
      return { enabled: false, reason: "今天的重試次數已用完，下一個交易日自動再試",
               remainingSeconds: null };
    case "in_progress":
      return { enabled: false, reason: "另一個更新正在處理這一檔", remainingSeconds: null };
    case "done":
      return { enabled: false, reason: "今天已經更新成功", remainingSeconds: null };
  }
}

export function progressText(p: ConsensusRefreshProgress): string {
  return `已完成 ${p.done}／${p.total} 檔、失敗 ${p.failed} 檔`;
}
