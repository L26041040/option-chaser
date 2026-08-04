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
import ExpiryStructure from "./ExpiryStructure";
import Heatmap from "./Heatmap";
import {
  baselineTopCandidate,
  getScenario,
  primaryResult,
  type AnalysisView,
  type Candidate,
  type ScenarioDetail as Detail,
} from "./api";
import { candidateTitle, catchupView, formatMove, strategyLabel } from "./detail";
import { isThinPool, validPairsForExpiry } from "./expiry";
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
function Catchup({ view, candidate }: { view: AnalysisView; candidate: Candidate | null }) {
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

function Chart({ view, candidate }: { view: AnalysisView; candidate: Candidate | null }) {
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
  // 主圖這組的名次是在 **baseline 期**的池子裡排出來的，所以這句提醒得
  // 跟著主圖走。只掛在下面那份會切換的清單上的話，使用者一切到別期，
  // 主圖仍是這一組、警語卻跟著跑掉，頭條數字就沒人幫它說話。
  const pool = validPairsForExpiry(primaryResult(view)!, view.baseline_expiry);
  return (
    <section className="card">
      <h2 className="section-title">劇本主圖</h2>
      <div className="row">
        <span className="row-value big">{candidateTitle(candidate)}</span>
        <span
          className={`metric ${candidate.baseline_return >= 0 ? "positive" : "negative"}`}
        >
          {formatReturn(candidate.baseline_return)}
        </span>
      </div>
      <Row label="到期日">{view.baseline_expiry}</Row>
      {isThinPool(pool) && (
        <p className="notice warn">
          <span aria-hidden="true">⚠ </span>
          這一期只有 {pool} 組候選通過品質過濾，主圖這組可能只是「整池剩下
          的那一個」。
        </p>
      )}
      <Heatmap matrix={candidate.matrix} />
    </section>
  );
}

function Summary({ view, analyzedAt }: { view: AnalysisView; analyzedAt: string | null }) {
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
      <Row label="資料時間">{formatAnalyzedAt(analyzedAt)}</Row>
      {/* 資料來源不是裝飾：`cboe` ＝ 打得到主源、`yfinance` ＝ 走了備援。
          部署後要確認雲端出口對 Cboe 的可達性，看的就是這一行。 */}
      <Row label="資料來源">{view.meta.source}</Row>
    </section>
  );
}

/** 有結果時的頁面主體。baseline 期第 1 名只在這裡取一次，三個區塊共用。 */
function DetailBody({ view, analyzedAt }: {
  view: AnalysisView;
  analyzedAt: string | null;
}) {
  const candidate = baselineTopCandidate(view);
  const result = primaryResult(view);
  return (
    <>
      <Summary view={view} analyzedAt={analyzedAt} />
      <Chart view={view} candidate={candidate} />
      <Catchup view={view} candidate={candidate} />
      {/* 到期日結構（V6／#54）接在主圖之下。切換到期日只換這一塊的清單，
          主圖不動——主圖固定是 baseline 期第 1 名（QA1-06 的既有裁示）。 */}
      {result && (
        <ExpiryStructure result={result} baselineExpiry={view.baseline_expiry} />
      )}
      {/* 候選池診斷（FB4-01／#60）：第 1 名如果是整池僅存者，那個名次
          沒有意義。它本來掛在 V1 的一次性分析畫面上，隨那塊一起搬進
          詳細頁——池子本來就是「這個劇本這次分析」的事。 */}
      <CandidatePool view={view} />
    </>
  );
}

export default function ScenarioDetail({
  id,
  refreshedAt = null,
}: {
  id: string;
  /**
   * 這個劇本在劇本庫那份清單上的資料時間。開站的刷新輪跑完之後它會變，
   * 詳細頁跟著重新取一次——否則直接開 `#/s/{id}` 的人會永遠停在刷新
   * 前的那份快照上：詳細頁沒有功能列、也沒有第四種刷新管道可按。
   */
  refreshedAt?: string | null;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    getScenario(id)
      .then((d) => { if (live) setDetail(d); })
      .catch((e) => {
        // 換頁後才回來的舊請求不該蓋掉新畫面
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => { live = false; };
  }, [id, refreshedAt]);

  // 換劇本時先清空，免得新劇本的標題底下短暫掛著上一個劇本的數字。
  // 刷新造成的重取不清空——那只是同一個劇本換一份較新的數字。
  useEffect(() => { setDetail(null); }, [id]);

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
        <DetailBody view={detail.latest_result}
                    analyzedAt={detail.latest_analyzed_at} />
      )}
    </div>
  );
}
