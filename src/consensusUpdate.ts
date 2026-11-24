/**
 * LIVE-T3（#398）「更新分析師資料」的純函式：重試鈕能不能按、為什麼不能、
 * 還要等多久，以及進度句。元件（`AnalystUpdatePanel.tsx`）只負責呼叫與畫面。
 *
 * 能不能重試的唯一依據是後端給的 `state`＋`next_retry_at`（絕對時間）：冷卻
 * 倒數用使用者自己的時鐘減去 `next_retry_at`，歸零就可以按——按下去後端
 * 仍會再判斷一次（冷卻、重試次數、每日上限、別人正在抓），不靠前端擋。
 */
import type {
  ConsensusCronStatus,
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

/** 美東「明天」是不是週末（排程只在平日跑）；讀不懂的日期當平日。 */
function nextDayWord(today: string | undefined): "明天" | "下週一" {
  const at = today ? Date.parse(`${today}T00:00:00Z`) : NaN;
  if (Number.isNaN(at)) return "明天";
  const tomorrow = new Date(at + 86_400_000).getUTCDay();
  return tomorrow === 0 || tomorrow === 6 ? "下週一" : "明天";
}

/**
 * 下一次自動更新是什麼時候（LIVE-T5／#401）。每日排程只在平日跑
 * （`vercel.json` 的 cron `1-5`），所以美東「明天」是週六／週日時說下週一。
 * `today` 是後端狀態 API 的美東日期；沒有或讀不懂時照樣說明天。
 *
 * V2-02（#403）：`cron` 是排程實際執行的紀錄。沒有任何一次授權成功的執行
 * （`last_run_day: null`，例如正式站還沒設 `CRON_SECRET`）時不說「會自動
 * 更新」——照實說排程尚未執行、要手動繼續。後端無法確認排程狀態
 * （`known: false`）時同樣不承諾，說「無法確認排程狀態」。
 */
export function nextAutoUpdate(today: string | undefined,
                               cron?: ConsensusCronStatus): string {
  const day = nextDayWord(today);
  if (cron && cron.known === false) {
    return `${CRON_UNKNOWN}，${day}請手動「繼續更新」`;
  }
  if (cron && cron.last_run_day === null) {
    return `排程尚未執行，不會自動更新，${day}請手動「繼續更新」`;
  }
  return `${day}自動更新`;
}

/** 後端沒有排程執行紀錄可查（觀測指標關閉，`known: false`）時的說法。 */
const CRON_UNKNOWN = "無法確認排程狀態";

/** 排程實際執行情形的一句話（V2-02／#403）；後端沒回報時不猜（`null`）；
 *  後端無法確認（`known: false`）時照實說無法確認。 */
export function cronText(cron: ConsensusCronStatus | undefined): string | null {
  if (!cron) return null;
  if (cron.known === false) return CRON_UNKNOWN;
  if ((cron.runs_today ?? 0) > 0) {
    return `今天已執行 ${cron.runs_today} 次（處理 ${cron.symbols_today} 檔）`;
  }
  if (cron.last_run_day === null) return `排程尚未執行（近 ${cron.lookback_days} 天沒有紀錄）`;
  return `今天尚未執行；最近一次在 ${cron.last_run_day}`;
}

export interface RetryContext {
  /** 今日上游呼叫已達每日上限（`upstream_calls_today >= daily_cap`）。 */
  capReached?: boolean;
  /** 狀態 API 的美東日期（`today`），用來說「明天」或「下週一」。 */
  today?: string;
  /** 來源回 429 後的全站暫停結束時間（`rate_limited_until`）；暫停中什麼都
   *  不會打上游。 */
  rateLimitedUntil?: string | null;
  /** 排程實際執行的紀錄（V2-02／#403）：從沒執行過就不說「會自動更新」。 */
  cron?: ConsensusCronStatus;
}

function rateLimitedReason(seconds: number): string {
  return `資料來源限流中（429），還要約 ${formatWait(seconds)}才會再更新`;
}

export function retryGate(s: ConsensusRefreshSymbol, nowMs: number,
                          ctx: RetryContext = {}): RetryGate {
  if (ctx.capReached && (s.state === "pending" || isFailed(s))) {
    return { enabled: false, reason: `今日上游呼叫已達每日上限，${nextAutoUpdate(ctx.today, ctx.cron)}`,
             remainingSeconds: null };
  }
  const paused = secondsUntil(ctx.rateLimitedUntil ?? null, nowMs);
  if (paused > 0 && (s.state === "pending" || isFailed(s))) {
    return { enabled: false, reason: rateLimitedReason(paused), remainingSeconds: paused };
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
      return { enabled: false, reason: `今天的重試次數已用完，${nextAutoUpdate(ctx.today, ctx.cron)}`,
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
 * - `rate_limited`：來源回 429 後的全站暫停還沒結束（用自己的時鐘比對
 *   `rate_limited_until`），而且還有沒做完的——什麼都不能按，冷卻結束後再更新。
 * - `capped`：今日上游呼叫已達上限，而且還有沒做完的（沒建立、失敗或今天
 *   還沒更新）——什麼都不能按，明天自動更新。優先於其他狀態，因為此時
 *   「繼續更新」或「重試」都會被後端拒絕。
 * - `building`：母體裡還有沒建立過的股票（`universe.not_built`，後端已扣掉
 *   超出每日更新範圍、永遠不會建立的 `out_of_scope`）——「繼續更新」。
 * - `failed`：都試過了，但有股票更新失敗——列出原因，依冷卻／次數重試。
 * - `ready`：可以直接搜尋選擇權。
 *
 * `status` 是 `GET /api/opportunity/consensus/status`，還沒讀到時只看共識清單。
 */
export type DataPhase =
  | { kind: "ready" }
  | { kind: "building" }
  | { kind: "failed"; failed: number }
  | { kind: "rate_limited"; until: string }
  | { kind: "capped"; calls: number; cap: number };

export function dataPhase(consensus: OpportunityConsensusResponse,
                          status: ConsensusRefreshStatusResponse | null,
                          nowMs: number = Date.now()): DataPhase {
  const notBuilt = consensus.universe.not_built ?? 0;
  const failed = status ? status.symbols.filter(isFailed).length : 0;
  const outstanding = notBuilt > 0 || failed > 0 || (status?.progress.pending ?? 0) > 0;
  const until = status?.rate_limited_until ?? null;
  if (until !== null && secondsUntil(until, nowMs) > 0 && outstanding) {
    return { kind: "rate_limited", until };
  }
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
 *  `no_data` 也算抓過）；還沒建立、抓取失敗（`source_error`）與超出每日更新
 *  範圍（`out_of_scope_symbols`）的不算。 */
export function builtCount(consensus: OpportunityConsensusResponse): number {
  const outside = new Set(consensus.universe.out_of_scope_symbols ?? []);
  return consensus.items.filter((i) => i.status !== "source_error" && !isNotBuilt(i)
                                       && !outside.has(i.symbol)).length;
}

/** 母體中在每日更新範圍內的檔數（「已建立 N／T」的 T）。 */
export function inScopeTotal(consensus: OpportunityConsensusResponse): number {
  return consensus.universe.symbols - (consensus.universe.out_of_scope ?? 0);
}

/** 使用者母體裡超出每日更新範圍（後端更新母體有上限）的檔數說明；沒有就 `null`。 */
export function outOfScopeText(consensus: OpportunityConsensusResponse): string | null {
  const n = consensus.universe.out_of_scope ?? 0;
  return n > 0 ? `${n} 檔超出每日更新範圍，不會更新` : null;
}
