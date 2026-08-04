/**
 * 劇本詳細頁（V5／#53）：摘要 → 主圖 Heatmap → Long Call 追平價格。
 *
 * 資料只從 `GET /api/scenarios/{id}` 來，畫面上每個數字都是引擎算好的：
 * 現價與所需漲幅在 `meta`、目標在 `params`、報酬矩陣在候選的 `matrix`、
 * 追平價格在 `catchup_price`。格式化在 `./detail` 與 `./heatmap` 的純
 * 函式裡，這一層只做編排。
 *
 * 主圖固定顯示 baseline 期的第 1 名候選（沿用既有「預設選中」語意，
 * QA1-06：主圖就是主圖，不跟著別處的互動改變）。
 */
import { useEffect, useState } from "react";

import CandidatePool from "./CandidatePool";
import Heatmap from "./Heatmap";
import {
  baselineTopCandidate,
  getScenario,
  primaryResult,
  type ScenarioDetail as Detail,
} from "./api";
import { candidateTitle, catchupView, formatMove, strategyLabel } from "./detail";
import { formatAnalyzedAt, formatReturn, money } from "./scenarios";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="row">
      <span className="row-label">{label}</span>
      <span className="row-value">{children}</span>
    </div>
  );
}

/** 追平價格區塊。三態各自有話說，沒有一態是留白或拋錯。 */
function Catchup({ detail }: { detail: Detail }) {
  const view = detail.latest_result!;
  const candidate = baselineTopCandidate(view);
  const catchup = candidate && catchupView(candidate, view.params.target_price);
  if (!catchup) return null;

  return (
    <section className="card">
      <h2 className="section-title">Long Call 追平價格</h2>
      <p className="caption">
        標的要漲到這個價格，同履約價的 Long Call 到期報酬率才追得上這組
        Spread。
      </p>

      <Row label={catchup.contract}>
        {catchup.price === null ? (
          <span className="muted">無法計算</span>
        ) : (
          <>
            {catchup.price}
            <span className="row-note">（{catchup.gap}）</span>
          </>
        )}
      </Row>

      {catchup.price === null && (
        <p className="caption">同履約價 Call 報價缺失，這一組算不出追平價格。</p>
      )}

      {/* 這是分析結論，不是狀態更新——不掛 role="status"：詳細頁只渲染
          一次，把靜態內容宣告成 live region 只會讓螢幕閱讀器把它跟真正
          會變的東西（候選池警示）混為一談。 */}
      {catchup.beatsTarget && (
        <p className="notice warn">Long Call 在本劇本內即勝過此 Spread</p>
      )}
    </section>
  );
}

function Chart({ detail }: { detail: Detail }) {
  const view = detail.latest_result!;
  const candidate = baselineTopCandidate(view);
  if (!candidate) {
    return (
      <section className="card">
        <h2 className="section-title">劇本主圖</h2>
        {/* 不拿別期的第 1 名冒充——那會在標著 baseline 到期日的地方顯示
            另一個到期日的候選（附錄A10.2 的既有邊界）。 */}
        <p className="caption">無合格候選</p>
      </section>
    );
  }
  return (
    <section className="card">
      <div className="row">
        <span className="row-value big">{candidateTitle(candidate)}</span>
        <span
          className={`metric ${candidate.baseline_return >= 0 ? "positive" : "negative"}`}
        >
          {formatReturn(candidate.baseline_return)}
        </span>
      </div>
      <Row label="到期日">{view.baseline_expiry}</Row>
      <Heatmap matrix={candidate.matrix} />
    </section>
  );
}

function Summary({ detail }: { detail: Detail }) {
  const view = detail.latest_result!;
  const strategy = primaryResult(view)?.strategy ?? view.params.strategy;
  return (
    <section className="card">
      <Row label="現價">{money(view.meta.spot)}</Row>
      <Row label="目標價">
        {money(view.params.target_price)}
        {/* 所需漲幅是引擎給的 `target_move`，不是這裡拿兩個價格相減 */}
        <span className="row-note">（{formatMove(view.meta.target_move)}）</span>
      </Row>
      <Row label="目標年月">{view.params.target_month}</Row>
      <Row label="策略">{strategyLabel(strategy)}</Row>
      <Row label="資料時間">{formatAnalyzedAt(detail.latest_analyzed_at)}</Row>
      {/* 資料來源不是裝飾：`cboe` ＝ 打得到主源、`yfinance` ＝ 走了備援。
          部署後要確認雲端出口對 Cboe 的可達性，看的就是這一行。 */}
      <Row label="資料來源">{view.meta.source}</Row>
    </section>
  );
}

export default function ScenarioDetail({ id }: { id: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setDetail(null);
    setError(null);
    getScenario(id)
      .then((d) => { if (live) setDetail(d); })
      .catch((e) => {
        // 換頁後才回來的舊請求不該蓋掉新畫面
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => { live = false; };
  }, [id]);

  return (
    <div className="screen">
      <header className="toolbar">
        <div className="toolbar-row">
          <a className="nav-back" href="#/">
            ‹ 劇本庫
          </a>
        </div>
        <h1 className="toolbar-title">{detail?.symbol ?? "劇本"}</h1>
      </header>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {!detail && !error && <p className="caption">載入中……</p>}

      {detail && detail.latest_result === null && (
        <section className="card">
          <p className="row-value">尚未分析</p>
          <p className="caption">
            這個劇本還沒跑過分析。回劇本庫按「重新整理」即可取得最新報價。
          </p>
        </section>
      )}

      {detail && detail.latest_result && (
        <>
          <Summary detail={detail} />
          <Chart detail={detail} />
          <Catchup detail={detail} />
          {/* 候選池診斷（FB4-01／#60）：第 1 名如果是整池僅存者，那個
              名次沒有意義。它本來掛在 V1 的一次性分析畫面上，隨那塊一起
              搬進詳細頁——池子本來就是「這個劇本這次分析」的事。 */}
          <CandidatePool view={detail.latest_result} />
        </>
      )}
    </div>
  );
}
