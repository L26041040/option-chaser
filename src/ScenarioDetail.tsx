/**
 * 劇本詳細頁（MVP V3／#103，資訊階層依 spec #102 決策 A 重整）：
 * 摘要（含基準候選與進場成本，QA 修正後三卡合一）→〔Historical IV
 * Position 插槽〕→ Payoff Heatmap → Price Ladder → Expiry Structure
 * → Advanced（候選池／分析報告／Spread 歷史／原始資料）。
 *
 * 資料只從 `GET /api/scenarios/{id}` 來，畫面上每個數字都是引擎算好的：
 * 現價與所需漲幅在 `meta`、目標在 `params`、報酬矩陣在候選的 `matrix`。
 * 格式化在 `./detail` 與 `./heatmap` 的純函式裡，這一層只做編排。
 *
 * 基準候選固定是 baseline 期的第 1 名（沿用既有「預設選中」語意，
 * QA1-06：主圖就是主圖，不跟著別處的互動改變）——「第 1 名」是
 * `baselineTopCandidate` 的定義本身（該期 `candidates[0]`），不是另外
 * 算出來的名次欄位。
 *
 * 舊「Long Call 追平價格」獨立區塊已依 spec 決策 E 移除（Crossover
 * Boundary 後續票將取代它）：後端序列化欄位與計算函式維持不動，僅供
 * migration／regression 測試使用，不在本頁任何位置渲染。
 */
import { useEffect, useState } from "react";

import AnalysisReport from "./AnalysisReport";
import CandidatePool from "./CandidatePool";
import ExpiryStructure from "./ExpiryStructure";
import Heatmap from "./Heatmap";
import RawData from "./RawData";
import SpreadHistory from "./SpreadHistory";
import {
  baselineTopCandidate,
  getScenario,
  primaryResult,
  type AnalysisView,
  type Candidate,
  type RefreshFailure,
  type ScenarioDetail as Detail,
} from "./api";
import { candidateTitle, formatMove, priceLadderView, strategyLabel } from "./detail";
import { isThinPool, legPrices, validPairsForExpiry } from "./expiry";
import { failureLabel, formatAnalyzedAt, formatReturn, money } from "./scenarios";

/**
 * 摘要格線裡的一格：標籤在上、數字在下。跟站上其他地方的 `.row`
 * （label／value 左右對開、佔滿整行）刻意不同——上下疊放才排得進
 * 兩欄／四欄格線，一行塞得下兩到四項，這正是把頂部高度壓下來的關鍵。
 */
function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{children}</span>
    </div>
  );
}

/**
 * Historical IV Position 的結構化插槽（spec #102 決策 A／B，#111 待
 * 施工）：只占這個位置，內容由後續 IV History 票填入。功能上線前不得
 * 渲染任何可見 UI——不是空卡片、不是「Coming Soon」、不是灰階
 * placeholder，就是不輸出任何 DOM 節點。
 */
function IVPositionSlot() {
  return null;
}

/**
 * 劇本區間三價位對照（V7／#55）。兩端都沒設定就整區不出現——見
 * `priceLadderView`。排名口徑不變（仍以目標價），這一區純粹是「同一組
 * 候選在我的劇本區間兩端各會怎樣」。
 */
function PriceLadder({ candidate }: { candidate: Candidate | null }) {
  const ladder = candidate && priceLadderView(candidate);
  if (!ladder) return null;

  return (
    <section className="card" aria-label="劇本區間對照">
      <h2 className="section-title">劇本區間對照</h2>
      <p className="caption">同一組候選在區間各價位的到期報酬。</p>
      <div className="ladder">
        {ladder.map((p) => (
          <div className="ladder-point" key={p.label}>
            <span className="row-label">{p.label}</span>
            <span className={`metric ${p.ret >= 0 ? "positive" : "negative"}`}>
              {formatReturn(p.ret)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * Payoff Heatmap（spec #102 決策 A）：候選身分、名次、目標報酬與候選池
 * 過少警語已搬到上方的「基準候選」區塊——這裡只剩圖本身。
 */
function Chart({ candidate }: { candidate: Candidate | null }) {
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
      <h2 className="section-title">劇本主圖</h2>
      {/* Crossover Boundary（#116）：只有 Spread 候選（兩條腿）有這個
          概念——單腿候選（買腿本身就是持倉，沒有「跟自己比較」的
          Crossover 概念）刻意不傳這個 prop，讓 `Heatmap` 完全不渲染
          相關區塊，不是渲染成「缺席」。 */}
      <Heatmap matrix={candidate.matrix}
               comparator={candidate.legs.length === 2 ? candidate.comparator : undefined} />
    </section>
  );
}

/**
 * 頂部摘要（QA 修正：三卡合一）。
 *
 * 原本是「劇本摘要／基準候選／進場成本」三張各自獨立的卡片，光是三圈
 * 卡片內距、兩道卡片間距與每張卡內部的 `.row` 分隔線就吃掉頂部大半
 * 高度，真正的數字反而被推到第一屏之外。這裡合成一張：候選身分與劇本
 * 報酬當標頭，其餘全部進統計格線（手機兩欄、桌面四欄）。
 *
 * **數字一項沒少**——現價、目標價（含所需漲幅）、目標年月、策略、
 * 到期日、名次、買腿 Ask、賣腿 Bid、淨成本、資料時間、資料來源，連
 * 候選池過少的警語都跟著搬過來。壓掉的是留白，不是資訊。
 */
function Summary({ view, candidate, analyzedAt }: {
  view: AnalysisView;
  candidate: Candidate | null;
  analyzedAt: string | null;
}) {
  const strategy = primaryResult(view)?.strategy ?? view.params.strategy;
  const pool = validPairsForExpiry(primaryResult(view)!, view.baseline_expiry);
  const prices = candidate ? legPrices(candidate) : null;
  return (
    <section className="card summary-card" aria-label="劇本摘要">
      {/* 標頭：這一頁在講哪一組候選、它的劇本報酬是多少。候選池過少的
          警語跟著這裡走，不掛在下面會切換到期日的清單上——使用者切到
          別期，這一區仍是 baseline 那組，警語得跟著它。 */}
      {candidate && (
        <div className="summary-hero">
          <span className="summary-id">
            <span className="summary-title">{candidateTitle(candidate)}</span>
            <span className="summary-meta">
              <span>{view.baseline_expiry}</span>
              <span>第 1 名</span>
            </span>
          </span>
          <span
            className={`metric ${candidate.baseline_return >= 0 ? "positive" : "negative"}`}
          >
            {formatReturn(candidate.baseline_return)}
          </span>
        </div>
      )}

      <div className="summary-grid">
        <Stat label="策略">{strategyLabel(strategy)}</Stat>
        <Stat label="現價">{money(view.meta.spot)}</Stat>
        <Stat label="目標價">
          {money(view.params.target_price)}
          {/* 所需漲幅是引擎給的 `target_move`，不是這裡拿兩個價格相減 */}
          <span className="row-note">（{formatMove(view.meta.target_move)}）</span>
        </Stat>
        <Stat label="目標年月">{view.params.target_month}</Stat>
        {/* 進場成本三項與到期日結構清單裡每一列候選同一口徑（`legPrices`） */}
        {prices && (
          <Stat label="買腿 Ask">
            {prices.buyAsk === null ? "—" : money(prices.buyAsk)}
          </Stat>
        )}
        {prices && (
          <Stat label="賣腿 Bid">
            {prices.sellBid === null ? "—" : money(prices.sellBid)}
          </Stat>
        )}
        {prices && <Stat label="淨成本">{money(prices.net)}</Stat>}
        <Stat label="資料時間">{formatAnalyzedAt(analyzedAt)}</Stat>
        {/* 資料來源不是裝飾：`cboe` ＝ 打得到主源、`yfinance` ＝ 走了備援。 */}
        <Stat label="資料來源">{view.meta.source}</Stat>
      </div>

      {candidate && isThinPool(pool) && (
        <p className="notice warn">
          <span aria-hidden="true">⚠ </span>
          這一期只有 {pool} 組候選通過品質過濾，第 1 名參考價值有限。
        </p>
      )}
    </section>
  );
}

/** 有結果時的頁面主體。baseline 期第 1 名只在這裡取一次，三個區塊共用。 */
function DetailBody({ scenarioId, view, analyzedAt }: {
  scenarioId: string;
  view: AnalysisView;
  analyzedAt: string | null;
}) {
  const candidate = baselineTopCandidate(view);
  const result = primaryResult(view);
  return (
    <>
      {/* spec #102 決策 A 的資訊階層不變，只是前三格（劇本摘要／基準
          候選／進場成本）合併成同一張高密度卡：摘要 →〔IV History
          插槽〕→ Payoff Heatmap → Price Ladder，全部圍繞同一組
          baseline 候選。 */}
      <Summary view={view} candidate={candidate} analyzedAt={analyzedAt} />
      <IVPositionSlot />
      <Chart candidate={candidate} />
      <PriceLadder candidate={candidate} />
      {/* 到期日結構（V6／#54）接在 Price Ladder 之下。切換到期日只換這
          一塊的清單，基準候選不動——固定是 baseline 期第 1 名（QA1-06
          的既有裁示）。 */}
      {result && (
        <ExpiryStructure result={result} baselineExpiry={view.baseline_expiry} />
      )}
      {/* 候選池診斷（FB4-01／#60）：第 1 名如果是整池僅存者，那個名次
          沒有意義。它本來掛在 V1 的一次性分析畫面上，隨那塊一起搬進
          詳細頁——池子本來就是「這個劇本這次分析」的事。 */}
      <CandidatePool view={view} />
      {/* 進階區（V8／#56、V9／#57）：分析報告新版型＋Spread 淨成本走勢
          ＋原始資料，接在候選池診斷之後——這幾塊是「想深入研究這個
          劇本」才會打開的東西，不該搶在主圖與到期日結構之前。 */}
      {result && (
        <AnalysisReport view={view} result={result} candidate={candidate} />
      )}
      {/* #69：`key` 綁定這次分析的身分——新分析一到，React 直接卸載重掛
          這兩個元件，內部 state（已抓到的資料、`<details open>`）連同
          歸零，不會在畫面上混用新舊 cache。刷新後收合、下次展開重新
          取得（需求方裁示接受，資料正確性優先）。`analyzedAt` 為 null
          的情況實務上不會發生於此（本區塊只在 `latest_result` 非 null
          時渲染，兩者恆同時有值），仍給個穩定佔位字串應付型別。兩個
          key 各自加前綴——這兩個元件是同一層的相鄰手足，若共用同一個
          key 字串，React 會把它們當成同一組鍵而發出「key 重複」警告，
          重掛的保證也就不可靠了。 */}
      <SpreadHistory key={`spread-history-${analyzedAt ?? "none"}`}
                     scenarioId={scenarioId} candidate={candidate} />
      <RawData key={`raw-data-${analyzedAt ?? "none"}`}
               scenarioId={scenarioId} analyzedAt={analyzedAt} />
    </>
  );
}

export default function ScenarioDetail({
  id,
  refreshedAt = null,
  busy = false,
  failure,
  onRefresh = () => {},
}: {
  id: string;
  /**
   * 這個劇本在劇本庫那份清單上的資料時間。開站的刷新輪跑完之後它會變，
   * 詳細頁跟著重新取一次——否則直接開 `#/s/{id}` 的人會永遠停在刷新
   * 前的那份快照上：詳細頁沒有功能列、也沒有第四種刷新管道可按。
   */
  refreshedAt?: string | null;
  /**
   * 詳細頁刷新入口（#70）：三者皆由 `App` 傳入，直接就是它既有的全域
   * 刷新狀態與那條唯一佇列——不在這裡另開一條刷新管道。`busy` 沿用
   * `Toolbar` 同一個判準（`progress !== null`，任何刷新進行中都算），
   * 不是「只有這個劇本在跑」才算忙碌：一條佇列、一個跑者，重複觸發
   * 只會讓同一個劇本排兩次。
   */
  busy?: boolean;
  failure?: RefreshFailure;
  onRefresh?: () => void;
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
        <div className="toolbar-row">
          <h1 className="toolbar-title">{detail?.symbol ?? "劇本"}</h1>
          {/* #70：與劇本庫功能列同一個視覺語言（標題列右側膠囊鈕），
              走 App 既有的那條刷新佇列——不是第四種獨立管道。已過期
              （#68）沿用清單卡片同一句文案並停用——後端會把它當無害
              no-op，按了等於沒按，不該讓它看起來還有用。 */}
          <button className="pill" onClick={onRefresh}
                 disabled={busy || detail?.expired}>
            {detail?.expired ? "已過期，不再刷新" : busy ? "刷新中……" : "重新整理"}
          </button>
        </div>
      </header>

      {/* 上次刷新失敗時沿用劇本庫卡片同一套分層指引與就地重試
          （V4／#52 既有語彙），不是重新發明一套說法。已過期優先於刷新
          失敗（#68 既有判斷）：兩種狀態同時出現會讓使用者搞不清楚現在
          是哪一種。 */}
      {failure && !detail?.expired && (
        <div className="notice error" role="alert">
          <div className="row-value">{failureLabel(failure.stage)}</div>
          <p className="caption">{failure.message}</p>
          <button className="text-button" onClick={onRefresh}>
            重試
          </button>
        </div>
      )}

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      {!detail && !error && <p className="caption">載入中……</p>}

      {detail && detail.latest_result === null && (
        <section className="card">
          <p className="row-value">尚未分析</p>
          <p className="caption">回劇本庫按「重新整理」取得報價。</p>
        </section>
      )}

      {detail && detail.latest_result && (
        <DetailBody scenarioId={id} view={detail.latest_result}
                    analyzedAt={detail.latest_analyzed_at} />
      )}
    </div>
  );
}
