/**
 * 個股共識詳細資料（LIVE-T2／#399）：機會搜尋頁共識清單每一列的「詳細資料」。
 *
 * 讓使用者看到共識是怎麼算出來的——目前有效的個別券商目標價（原始值、發布
 * 日、分割換算後的值）、平均／標準差／D／自身歷史百分位、每月 D 序列與合格
 * 點數、資料不足的具體原因。數字全是後端原值（`GET /api/opportunity/
 * consensus-detail/{symbol}`，只讀全站快取），這裡只格式化。
 *
 * - 收合時不打端點；第一次打開才讀，之後收起再開沿用同一份（不重打）。
 * - 全部用直排清單（不用寬表格），手機寬度下不出現水平捲動；每月序列放在
 *   限高、可垂直捲動的框裡。
 */
import { useEffect, useId, useRef, useState } from "react";

import {
  getOpportunityConsensusDetail,
  type ConsensusEffectiveTarget,
  type ConsensusItem,
  type ConsensusSeriesPoint,
  type OpportunityConsensusDetail,
} from "./api";
import { ratioPct, reasonText, STATUS_LABELS } from "./opportunity";
import { money } from "./scenarios";

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ok"; data: OpportunityConsensusDetail };

/** 打開／收起與讀取（LIVE-T5／#401 起，搜尋結果列也用同一套：按鈕與明細
 *  分開放在表格的兩列裡）。 */
export function useConsensusDetail(symbol: string) {
  const [open, setOpen] = useState(false);
  const [load, setLoad] = useState<Load | null>(null);
  const ctrl = useRef<AbortController | null>(null);
  const panelId = useId();
  useEffect(() => () => ctrl.current?.abort(), []);

  // 在點擊事件裡讀（不是 effect）：只有使用者第一次打開才打端點，
  // StrictMode 的重複掛載也不會多打一次。
  function toggle() {
    setOpen((v) => !v);
    if (load !== null) return;
    setLoad({ state: "loading" });
    ctrl.current = new AbortController();
    const signal = ctrl.current.signal;
    getOpportunityConsensusDetail(symbol, signal)
      .then((data) => setLoad({ state: "ok", data }))
      .catch((e: unknown) => {
        if (signal.aborted) return;
        setLoad({ state: "error", message: e instanceof Error ? e.message : String(e) });
      });
  }

  return { open, load, toggle, panelId };
}

export type ConsensusDetailState = ReturnType<typeof useConsensusDetail>;

/** 明細本體；收起或還沒讀時不渲染。 */
export function ConsensusDetailPanel({
  symbol, detail,
}: {
  symbol: string;
  detail: ConsensusDetailState;
}) {
  const { open, load, panelId } = detail;
  if (!open || load === null) return null;
  return (
    <section id={panelId} className="opp-detail-panel" aria-label={`${symbol} 共識明細`}>
      {load.state === "loading" && <p className="caption">載入中……</p>}
      {load.state === "error" && (
        <div className="notice error" role="alert">{load.message}</div>
      )}
      {load.state === "ok" && <DetailBody data={load.data} />}
    </section>
  );
}

export default function ConsensusDetailToggle({ symbol }: { symbol: string }) {
  const detail = useConsensusDetail(symbol);
  return (
    <div className="opp-detail">
      <button
        type="button"
        className="pbtn sm line opp-detail-toggle"
        aria-label={`${symbol} 詳細資料`}
        aria-expanded={detail.open}
        aria-controls={detail.panelId}
        onClick={detail.toggle}
      >
        {detail.open ? "收起詳細資料" : "詳細資料"}
      </button>
      <ConsensusDetailPanel symbol={symbol} detail={detail} />
    </div>
  );
}

function DetailBody({ data }: { data: OpportunityConsensusDetail }) {
  const item = data.item;
  if (item === null) {
    return <p className="caption">{data.message ?? "沒有這一檔的共識資料"}</p>;
  }
  return (
    <>
      <Facts item={item} data={data} />
      <Why item={item} />
      {data.detail_available ? (
        <>
          <Effective rows={data.effective} />
          <Series points={data.series} qualified={data.qualified_points} />
        </>
      ) : (
        <p className="caption">明細尚未產生：下一次共識更新後才有個別券商與每月序列。</p>
      )}
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <li>
      <span className="opp-detail-label">{label}</span>
      <strong className="num">{value}</strong>
    </li>
  );
}

const moneyOrDash = (x: number | null) => (x === null ? "—" : money(x));

function Facts({ item, data }: { item: ConsensusItem; data: OpportunityConsensusDetail }) {
  const months = data.detail_available ? data.series.length : null;
  return (
    <ul className="opp-detail-facts" aria-label="共識數值">
      <Fact label="平均目標價" value={moneyOrDash(item.mean)} />
      <Fact label="標準差" value={moneyOrDash(item.stdev)} />
      <Fact label="分歧度 D" value={ratioPct(item.dispersion)} />
      <Fact label="自身歷史百分位" value={ratioPct(item.percentile)} />
      <Fact
        label="合格歷史點"
        value={months === null ? `${item.history_points}` : `${item.history_points} / ${months} 個月`}
      />
      <Fact label="有效分析師" value={`${item.n_analysts} 位`} />
      <Fact label="資料日" value={item.as_of ?? "—"} />
    </ul>
  );
}

function Why({ item }: { item: ConsensusItem }) {
  if (item.gate.selected) return null;
  if (item.status !== "ok") {
    return (
      <div className="opp-detail-why">
        <p className="caption">
          {STATUS_LABELS[item.status] ?? item.status}：資料不足的股票不會入選。
        </p>
        <ul className="opp-reasons" aria-label="未入選原因">
          {item.reasons.map((r, i) => <li key={i}>{reasonText(r)}</li>)}
        </ul>
      </div>
    );
  }
  return (
    <div className="opp-detail-why">
      <p className="caption">資料足夠，但沒通過門檻。</p>
      <ul className="opp-reasons" aria-label="未入選原因">
        {item.gate.reasons.map((r, i) => <li key={i}>{reasonText(r)}</li>)}
      </ul>
    </div>
  );
}

const sameValue = (a: number, b: number) => Math.abs(a - b) < 1e-9;

function Effective({ rows }: { rows: ConsensusEffectiveTarget[] }) {
  return (
    <div className="opp-detail-block">
      <h3 className="opp-detail-title">有效目標價（{rows.length} 位）</h3>
      <ul className="opp-detail-targets" aria-label={`有效目標價（${rows.length} 位）`}>
        {rows.map((e) => (
          <li key={e.analyst_key} aria-label={e.firm}>
            <span className="opp-detail-firm">{e.firm}</span>
            <strong className="num">{money(e.target_price)}</strong>
            {!sameValue(e.target_price, e.adjusted_price) && (
              <span className="num">分割換算後 {money(e.adjusted_price)}</span>
            )}
            <span className="row-note">
              {e.published_on}
              {e.action ? ` · ${e.action}` : ""}
              {e.prior_target !== null ? ` · 前值 ${money(e.prior_target)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Series({ points, qualified }: { points: ConsensusSeriesPoint[]; qualified: number }) {
  const newestFirst = [...points].reverse();
  return (
    <div className="opp-detail-block">
      <h3 className="opp-detail-title">
        每月分歧度（合格 {qualified} / {points.length} 個月）
      </h3>
      <ol className="opp-detail-series" aria-label="每月分歧度">
        {newestFirst.map((p) => (
          <li key={p.on} className={p.qualified ? undefined : "muted"}>
            <span className="num">{p.on}</span>
            <span className="num">{p.n_analysts} 位</span>
            <span className="num">D {ratioPct(p.dispersion)}</span>
            {!p.qualified && (
              <span>不計入：{STATUS_LABELS[p.reason ?? ""] ?? p.reason}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
