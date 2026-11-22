/**
 * LIVE-T3（#398）「更新分析師資料」的純函式：重試鈕能不能按、為什麼不能、
 * 還要等多久，以及進度句。元件（`AnalystUpdatePanel.tsx`）只負責呼叫與畫面。
 *
 * 能不能重試的唯一依據是後端給的 `state`＋`next_retry_at`（絕對時間）：冷卻
 * 倒數用使用者自己的時鐘減去 `next_retry_at`，歸零就可以按——按下去後端
 * 仍會再判斷一次（冷卻、重試次數、每日上限、別人正在抓），不靠前端擋。
 */
import type {
  ConsensusItem,
  ConsensusRefreshProgress,
  ConsensusRefreshStatusResponse,
  ConsensusRefreshSymbol,
  OpportunityConsensusResponse,
} from "./api";

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

/**
 * 下一次自動更新是什麼時候（LIVE-T5／#401）。每日排程只在平日跑
 * （`vercel.json` 的 cron `1-5`），所以美東「明天」是週六／週日時說下週一。
 * `today` 是後端狀態 API 的美東日期；沒有或讀不懂時照樣說明天。
 */
export function nextAutoUpdate(today: string | undefined): string {
  const at = today ? Date.parse(`${today}T00:00:00Z`) : NaN;
  if (Number.isNaN(at)) return "明天自動更新";
  const tomorrow = new Date(at + 86_400_000).getUTCDay();
  return tomorrow === 0 || tomorrow === 6 ? "下週一自動更新" : "明天自動更新";
}

export interface RetryContext {
  /** 今日上游呼叫已達每日上限（`upstream_calls_today >= daily_cap`）。 */
  capReached?: boolean;
  /** 狀態 API 的美東日期（`today`），用來說「明天」或「下週一」。 */
  today?: string;
}

export function retryGate(s: ConsensusRefreshSymbol, nowMs: number,
                          ctx: RetryContext = {}): RetryGate {
  if (ctx.capReached && (s.state === "pending" || isFailed(s))) {
    return { enabled: false, reason: `今日上游呼叫已達每日上限，${nextAutoUpdate(ctx.today)}`,
             remainingSeconds: null };
  }
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
      return { enabled: false, reason: `今天的重試次數已用完，${nextAutoUpdate(ctx.today)}`,
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

/** 今日上游呼叫是否已達每日上限。 */
export function capReached(status: ConsensusRefreshStatusResponse | null): boolean {
  return status !== null && status.upstream_calls_today >= status.daily_cap;
}

/**
 * 分析師資料的整體狀態（LIVE-T5／#401），決定頁面該叫使用者做什麼：
 *
 * - `capped`：今日上游呼叫已達上限，而且還有沒做完的（沒建立、失敗或今天
 *   還沒更新）——什麼都不能按，明天自動更新。優先於其他狀態，因為此時
 *   「繼續更新」或「重試」都會被後端拒絕。
 * - `building`：母體裡還有沒建立過的股票（`universe.not_built`）——「繼續更新」。
 * - `failed`：都試過了，但有股票更新失敗——列出原因，依冷卻／次數重試。
 * - `ready`：可以直接搜尋選擇權。
 *
 * `status` 是 `GET /api/opportunity/consensus/status`，還沒讀到時只看共識清單。
 */
export type DataPhase =
  | { kind: "ready" }
  | { kind: "building" }
  | { kind: "failed"; failed: number }
  | { kind: "capped"; calls: number; cap: number };

export function dataPhase(consensus: OpportunityConsensusResponse,
                          status: ConsensusRefreshStatusResponse | null): DataPhase {
  const notBuilt = consensus.universe.not_built ?? 0;
  const failed = status ? status.symbols.filter(isFailed).length : 0;
  const outstanding = notBuilt > 0 || failed > 0 || (status?.progress.pending ?? 0) > 0;
  if (status && capReached(status) && outstanding) {
    return { kind: "capped", calls: status.upstream_calls_today, cap: status.daily_cap };
  }
  if (notBuilt > 0) return { kind: "building" };
  if (failed > 0) return { kind: "failed", failed };
  return { kind: "ready" };
}

/** 還沒建立共識資料：沒有快取、也還沒失敗過（後端固定原因字串，與
 *  `universe.not_built` 同一個判準）。 */
const NOT_BUILT_REASON = "no_data: 尚未更新";
export function isNotBuilt(item: ConsensusItem): boolean {
  return item.reasons.length === 1 && item.reasons[0] === NOT_BUILT_REASON;
}

/** 已建立的檔數：母體中抓過、有結果的（只有共識值、沒有個別目標價的
 *  `no_data` 也算抓過）；還沒建立與抓取失敗（`source_error`）的不算。 */
export function builtCount(consensus: OpportunityConsensusResponse): number {
  return consensus.items.filter((i) => i.status !== "source_error" && !isNotBuilt(i)).length;
}
