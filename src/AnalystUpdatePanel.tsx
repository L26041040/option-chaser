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
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getConsensusRefreshStatus,
  updateConsensus,
  type ConsensusRefreshProgress,
  type ConsensusRefreshStatusResponse,
  type ConsensusRefreshSymbol,
} from "./api";
import { isFailed, progressText, retryGate } from "./consensusUpdate";

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

export default function AnalystUpdatePanel({ onUpdated }: { onUpdated: () => void }) {
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
  const now = useNow(failed.some((s) => s.state === "cooling"));
  const busy = run.state === "running" || retrying !== null;

  async function update() {
    setRun({ state: "running", progress: null });
    try {
      for (;;) {
        const r = await updateConsensus();
        if (!mounted.current) return;
        if (r.stopped_reason === "daily_cap") {
          setRun({ state: "stopped", progress: r.progress,
                   message: r.message ?? "今日上游呼叫已達每日上限" });
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
      <h2 className="section-title">分析師資料</h2>
      {status.state === "loading" && <p className="caption">載入中……</p>}
      {status.state === "error" && (
        <div className="notice error" role="alert">
          {status.message}
        </div>
      )}
      {data && (
        <p className="opp-facts">
          <span>資料日 {data.data_as_of ?? "—"}</span>
          <span>今日 {progressText(data.progress)}</span>
          <span>
            今日上游呼叫 {data.upstream_calls_today}／{data.daily_cap} 次
          </span>
        </p>
      )}
      <div className="opp-actions">
        <button
          type="button"
          className="pbtn"
          onClick={() => void update()}
          disabled={busy || data === null}
        >
          {run.state === "running" ? "更新中……" : "更新分析師資料"}
        </button>
      </div>
      <p className="caption">
        今天已成功的股票不會重抓；失敗的會在冷卻後重試。全站共用，多人同時按也不會重複抓。
      </p>
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
              error={retryErrors[s.symbol]}
              onRetry={() => void retry(s.symbol)}
            />
          ))}
        </ul>
      )}
    </section>
  );
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
  item, now, busy, retrying, error, onRetry,
}: {
  item: ConsensusRefreshSymbol;
  now: number;
  busy: boolean;
  retrying: boolean;
  error: string | undefined;
  onRetry: () => void;
}) {
  const gate = retryGate(item, now);
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
