/**
 * 機會搜尋頁的「分析師資料」區塊（LIVE-T3／#398）：SU／SA 一鍵建立／更新
 * 全站共用的分析師資料，以及失敗檔的單檔重試。
 *
 * - 「更新分析師資料」＝`POST /api/opportunity/consensus/update`，依 `remaining`
 *   自動續跑（比照劇本 Refresh Run），即時顯示「已完成 N／T 檔、失敗 M 檔」；
 *   每日上限已滿時後端回 `stopped_reason: "daily_cap"`，這裡停下並照實說。
 * - 「重試」＝同一端點帶 `symbols: [那一檔]`，是真的會打上游的操作。冷卻中
 *   停用並顯示剩餘時間與原因（倒數以後端給的絕對時間 `next_retry_at` 為準），
 *   歸零後可按；重試用完／別人正在處理也停用並說明。後端仍會再判斷一次，
 *   拒絕時（409／429）照實顯示後端訊息。
 * - 只在 SU／SA 才會被渲染（`OpportunityPage` 的守門）；每次更新或重試結束
 *   都重讀狀態，並通知頁面重讀共識清單（`onUpdated`）。
 * - LIVE-T5（#401）：區塊頂端是「資料狀態」——資料來源（真實或測試）、資料日期、
 *   已建立／掃描範圍檔數、符合條件檔數——與目前的狀態（`dataPhase()`：就緒／建立中／
 *   更新失敗／已達今日上限）。每個狀態一句話說下一步，主按鈕跟著狀態換字：
 *   建立中是「開始建立」或「繼續更新」，已達今日上限時停用並說明何時自動更新；
 *   就緒時主要動作是下方符合條件的股票的「搜尋選擇權」，這裡的更新鈕退為次要樣式。
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import MetricInfo, { MetricHelpRow } from "./MetricInfo";
import type { MetricHelpKey } from "./metricHelp";

import {
  getConsensusRefreshStatus,
  updateConsensus,
  type ConsensusCronStatus,
  type ConsensusRefreshProgress,
  type ConsensusRefreshStatusResponse,
  type ConsensusRefreshSymbol,
  type OpportunityConsensusResponse,
} from "./api";
import {
  builtCount,
  capReached,
  cronText,
  dataPhase,
  formatWait,
  inScopeTotal,
  isFailed,
  nextAutoUpdate,
  outOfScopeText,
  progressText,
  retryGate,
  secondsUntil,
  type DataPhase,
  type RetryContext,
} from "./consensusUpdate";

type StatusLoad =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ok"; data: ConsensusRefreshStatusResponse };

type Run =
  | { state: "idle" }
  | { state: "running"; progress: ConsensusRefreshProgress | null }
  | { state: "finished"; progress: ConsensusRefreshProgress }
  | { state: "stopped"; progress: ConsensusRefreshProgress; message: string }
  | { state: "failed"; message: string };

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** 每秒重新讀一次時鐘（只在有冷卻倒數時才開計時器）。 */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

const PHASE_LABELS: Record<DataPhase["kind"], string> = {
  ready: "就緒",
  building: "建立中",
  failed: "更新失敗",
  rate_limited: "來源限流中",
  capped: "已達今日上限",
};

export default function AnalystUpdatePanel({
  consensus, onUpdated,
}: {
  /** 共識清單（頁面已讀好的同一份）：資料來源、掃描範圍、已建立與符合條件檔數。 */
  consensus: OpportunityConsensusResponse;
  onUpdated: () => void;
}) {
  const [status, setStatus] = useState<StatusLoad>({ state: "loading" });
  const [run, setRun] = useState<Run>({ state: "idle" });
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reload = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getConsensusRefreshStatus(signal);
      if (mounted.current) setStatus({ state: "ok", data });
    } catch (e) {
      if (mounted.current && !signal?.aborted) {
        setStatus({ state: "error", message: errorMessage(e) });
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [reload]);

  const data = status.state === "ok" ? status.data : null;
  const failed = data ? data.symbols.filter(isFailed) : [];
  const pausedUntil = data?.rate_limited_until ?? null;
  const now = useNow(failed.some((s) => s.state === "cooling")
                     || secondsUntil(pausedUntil, Date.now()) > 0);
  const busy = run.state === "running" || retrying !== null;
  const phase = dataPhase(consensus, data, now);
  const retryCtx: RetryContext = { capReached: capReached(data), today: data?.today,
                                   rateLimitedUntil: pausedUntil, cron: data?.cron };
  const schedule = cronText(data?.cron);
  const built = builtCount(consensus);
  const total = inScopeTotal(consensus);
  const outOfScope = outOfScopeText(consensus);
  const selected = consensus.items.filter((i) => i.gate.selected).length;
  const updateLabel = phase.kind !== "building" ? "更新分析師資料"
    : built === 0 ? "開始建立" : "繼續更新";

  async function update() {
    setRun({ state: "running", progress: null });
    try {
      for (;;) {
        const r = await updateConsensus();
        if (!mounted.current) return;
        if (r.stopped_reason === "daily_cap" || r.stopped_reason === "rate_limited") {
          setRun({ state: "stopped", progress: r.progress,
                   message: r.message ?? (r.stopped_reason === "daily_cap"
                     ? "今日上游呼叫已達每日上限" : "資料來源限流（429）") });
          break;
        }
        // 沒有可續跑的、或這次一檔都沒處理（防無窮迴圈）就結束。
        if (r.remaining.length === 0 || r.processed === 0) {
          setRun({ state: "finished", progress: r.progress });
          break;
        }
        setRun({ state: "running", progress: r.progress });
      }
    } catch (e) {
      if (mounted.current) setRun({ state: "failed", message: errorMessage(e) });
    }
    if (!mounted.current) return;
    await reload();
    onUpdated();
  }

  async function retry(symbol: string) {
    setRetrying(symbol);
    setRetryErrors(({ [symbol]: _drop, ...rest }) => rest);
    try {
      await updateConsensus([symbol]);
    } catch (e) {
      if (mounted.current) setRetryErrors((prev) => ({ ...prev, [symbol]: errorMessage(e) }));
    }
    if (!mounted.current) return;
    setRetrying(null);
    await reload();
    onUpdated();
  }

  return (
    <section className="card" aria-label="分析師資料">
      <h2 className="section-title">
        分析師資料
        <span className={`tag ${phase.kind === "ready" ? "up" : "warn"}`}>
          {PHASE_LABELS[phase.kind]}
        </span>
      </h2>
      <ul className="opp-detail-facts opp-status-facts" aria-label="資料狀態">
        <StatusFact label="掃描股票範圍">
          {consensus.universe.label}
          {consensus.universe.version_date && `（版本 ${consensus.universe.version_date}）`}
        </StatusFact>
        <StatusFact label="資料來源">
          {consensus.source.is_fixture ? "測試資料（非真實市場資料）" : "真實分析師資料"}
        </StatusFact>
        <StatusFact label="資料日期" help="dataDate">{consensus.universe.as_of ?? data?.data_as_of ?? "—"}</StatusFact>
        <StatusFact label="已建立">{built}／{total} 檔</StatusFact>
        <StatusFact label="符合條件">{selected} 檔</StatusFact>
        {data && <StatusFact label="今日更新">{progressText(data.progress)}</StatusFact>}
        {data && (
          <StatusFact label="今日上游呼叫" help="dailyCap">
            {data.upstream_calls_today}／{data.daily_cap} 次
          </StatusFact>
        )}
        {schedule && <StatusFact label="排程">{schedule}</StatusFact>}
      </ul>
      {status.state === "loading" && <p className="caption">載入中……</p>}
      {status.state === "error" && (
        <div className="notice error" role="alert">
          {status.message}
        </div>
      )}
      <p className={`notice opp-phase${phase.kind === "ready" ? "" : " warn"}`} role="status">
        {phaseText(phase, { built, total, selected, today: data?.today, now,
                            cron: data?.cron })}
      </p>
      {outOfScope && <p className="caption">{outOfScope}</p>}
      <div className="opp-actions">
        <button
          type="button"
          className={phase.kind === "ready" ? "pbtn line" : "pbtn"}
          onClick={() => void update()}
          disabled={busy || data === null || phase.kind === "capped"
                    || phase.kind === "rate_limited"}
        >
          {run.state === "running" ? "更新中……" : updateLabel}
        </button>
      </div>
      <p className="caption">
        今天已成功的股票不會重抓；失敗的會在冷卻後重試。全站共用，多人同時按也不會重複抓。
      </p>
      <MetricHelpRow metrics={["rateLimitPause", "rotatingUpdate"]} />
      <RunLine run={run} />
      {failed.length > 0 && (
        <ul className="opp-list" aria-label="更新失敗的股票">
          {failed.map((s) => (
            <FailedItem
              key={s.symbol}
              item={s}
              now={now}
              busy={busy}
              retrying={retrying === s.symbol}
              ctx={retryCtx}
              error={retryErrors[s.symbol]}
              onRetry={() => void retry(s.symbol)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function StatusFact({
  label, help, children,
}: {
  label: string;
  help?: MetricHelpKey;
  children: ReactNode;
}) {
  return (
    <li aria-label={label}>
      <span className="opp-detail-label-row">
        <span className="opp-detail-label">{label}</span>
        {help && <MetricInfo metric={help} />}
      </span>
      <strong className="num">{children}</strong>
    </li>
  );
}

/** 每個狀態一句話：現在怎樣、下一步做什麼。 */
function phaseText(
  phase: DataPhase,
  { built, total, selected, today, now, cron }:
    { built: number; total: number; selected: number; today: string | undefined;
      now: number; cron: ConsensusCronStatus | undefined },
): string {
  switch (phase.kind) {
    case "ready":
      return selected > 0
        ? "資料已就緒，可以直接用下方的「搜尋選擇權」搜尋符合條件的股票。"
        : "資料已就緒，但目前沒有股票同時通過兩道門檻，可以調整門檻後再看。";
    case "building":
      return built === 0
        ? `資料建立中：掃描股票範圍內 ${total} 檔都還沒建立。按「開始建立」抓取分析師資料，建好後才知道哪些股票符合條件。`
        : `資料建立中：已建立 ${built}／${total} 檔。按「繼續更新」接著建立；已建立且符合條件的股票現在就可以搜尋。`;
    case "failed":
      return `${phase.failed} 檔更新失敗：原因與重試方式列在下方。其餘股票照常可以搜尋。`;
    case "rate_limited":
      return `資料來源限流（429），所有更新暫停，還要約 ${formatWait(secondsUntil(phase.until, now))}才會再更新或重試。已建立的資料照常可以搜尋。`;
    case "capped":
      return `今日上游呼叫已達每日上限（${phase.calls}／${phase.cap} 次），今天不能再更新或重試，${nextAutoUpdate(today, cron)}。已建立的資料照常可以搜尋。`;
  }
}

function RunLine({ run }: { run: Run }) {
  switch (run.state) {
    case "idle":
      return null;
    case "running":
      return (
        <p className="caption opp-progress" aria-live="polite">
          <span>{run.progress ? progressText(run.progress) : "開始更新……"}</span>
          <span>更新中……</span>
        </p>
      );
    case "finished":
      return (
        <p className="caption opp-progress" aria-live="polite">
          更新完成：{progressText(run.progress)}
        </p>
      );
    case "stopped":
      return (
        <div className="notice error" role="alert">
          已停止（{progressText(run.progress)}）：{run.message}
        </div>
      );
    case "failed":
      return (
        <div className="notice error" role="alert">
          更新失敗：{run.message}
        </div>
      );
  }
}

function FailedItem({
  item, now, busy, retrying, ctx, error, onRetry,
}: {
  item: ConsensusRefreshSymbol;
  now: number;
  busy: boolean;
  retrying: boolean;
  ctx: RetryContext;
  error: string | undefined;
  onRetry: () => void;
}) {
  const gate = retryGate(item, now, ctx);
  return (
    <li aria-label={item.symbol} className="opp-item">
      <div className="opp-item-head">
        <strong>{item.symbol}</strong>
        <button
          type="button"
          className="pbtn sm line"
          aria-label={`重試 ${item.symbol}`}
          onClick={onRetry}
          disabled={busy || !gate.enabled}
        >
          {retrying ? "重試中……" : "重試"}
        </button>
      </div>
      <p className="caption">{item.error}</p>
      <p className="opp-facts">
        <span>今日已重試 {item.retries_today} 次</span>
        {item.as_of && <span>沿用 {item.as_of} 的資料</span>}
      </p>
      {gate.reason && <p className="caption">{gate.reason}</p>}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
    </li>
  );
}
