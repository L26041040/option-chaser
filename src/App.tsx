/**
 * V1（#48）走通骨架的畫面：呼叫 API 跑一次真實分析，顯示現價、baseline
 * 期第 1 名收益率、以及資料來源。
 *
 * 資料來源那一行不是裝飾——它就是 Vercel 出口對 Cboe 可達性的驗證方式
 * （`cboe` ＝ 打得到主源；`yfinance` ＝ 走了備援）。
 *
 * 這一版刻意只有一個畫面：劇本庫、建立表單、詳細頁等是後續票（#51 起）。
 */
import { useState } from "react";
import {
  analyze,
  baselineTopCandidate,
  type AnalysisView,
  type Candidate,
} from "./api";

const DEMO_REQUEST = {
  symbol: "TLT",
  target_price: 120,
  target_month: "2028-05",
  strategies: ["bull-call-spread"],
};

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

function money(x: number): string {
  return `$${x.toFixed(2)}`;
}

function legLabel(cand: Candidate): string {
  const [long, short] = cand.legs;
  if (!long) return "—";
  return short
    ? `買 ${long.strike} / 賣 ${short.strike}`
    : `K=${long.strike}`;
}

export default function App() {
  const [view, setView] = useState<AnalysisView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setView(await analyze(DEMO_REQUEST));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setView(null);
    } finally {
      setLoading(false);
    }
  }

  const top = view ? baselineTopCandidate(view) : null;

  return (
    <div className="screen">
      <h1 className="title">Option Chaser</h1>
      <p className="caption">
        {DEMO_REQUEST.symbol}　目標 {money(DEMO_REQUEST.target_price)}
        {DEMO_REQUEST.target_month}
      </p>

      <button className="button" onClick={run} disabled={loading}>
        {loading ? "分析中……" : "跑一次分析"}
      </button>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {view && (
        <div className="card">
          <div className="row">
            <span className="row-label">現價</span>
            <span className="row-value">{money(view.meta.spot)}</span>
          </div>
          <div className="row">
            <span className="row-label">到期日（baseline）</span>
            <span className="row-value">{view.baseline_expiry ?? "—"}</span>
          </div>
          {top ? (
            <>
              <div className="row">
                <span className="row-label">該期第 1 名</span>
                <span className="row-value">{legLabel(top)}</span>
              </div>
              <div className="row">
                <span className="row-label">劇本報酬</span>
                <span
                  className={`metric ${
                    top.baseline_return >= 0 ? "positive" : "negative"
                  }`}
                >
                  {pct(top.baseline_return)}
                </span>
              </div>
            </>
          ) : (
            <div className="row">
              <span className="row-label">該期第 1 名</span>
              <span className="row-value">無合格候選</span>
            </div>
          )}
          <p className="caption">
            資料來源 {view.meta.source}　·　{view.meta.fetched_at}
          </p>
        </div>
      )}
    </div>
  );
}
