/**
 * 劇本詳細頁（MVP V3／#103，資訊階層依 spec #102 決策 A 重整）：
 * 劇本設定（OPTION-CHASER-CLOSEOUT-001：使用者原本建立的 context——
 * 標的／目標價／目標年月／方向／啟用的 family）→ 摘要（含基準候選與
 * 進場成本，QA 修正後三卡合一）→〔Historical IV Position 插槽〕→
 * Payoff Heatmap → Strategy Family 分頁（依到期日分組的 Expiry
 * Structure／候選池／分析報告，見 `FamilyTabs`）→ Spread 歷史／
 * 原始資料。
 *
 * 資料只從 `GET /api/scenarios/{id}` 來，畫面上每個數字都是引擎算好的：
 * 現價與所需漲幅在 `meta`、目標在 `params`、報酬矩陣在候選的 `matrix`。
 * 格式化在 `./detail` 與 `./heatmap` 的純函式裡，這一層只做編排。
 *
 * T11（#229，Initial V2）：摘要卡與主圖固定顯示**跨 family 冠軍**
 * （`family.ts::championCandidate`，CONTEXT.md「Per-family
 * Representative」／「Family Tab」兩節記錄的口徑升級），不隨
 * `FamilyTabs` 的分頁切換而改變——沿用既有「主圖就是主圖，不跟著別處
 * 的互動改變」原則（QA1-06 對到期日切換的裁示，這裡延伸到 family 這個
 * 新維度）。單一 family 的既有劇本（Initial V2 之前建立的全部劇本）
 * 冠軍恆等於該 family 唯一候選，畫面逐位元不變。
 *
 * 舊「Long Call 追平價格」獨立區塊已依 spec 決策 E 移除（Crossover
 * Boundary 後續票將取代它）：後端序列化欄位與計算函式維持不動，僅供
 * migration／regression 測試使用，不在本頁任何位置渲染。
 */
import { useEffect, useState } from "react";

import DesktopDetailBody from "./DesktopDetail";
import FamilyTabs from "./FamilyTabs";
import IvHistory from "./IvHistory";
import Heatmap from "./Heatmap";
import RawData from "./RawData";
import SpreadHistory from "./SpreadHistory";
import StockLogo from "./StockLogo";
import {
  type AnalysisView,
  type Candidate,
  type RefreshFailure,
  type ScenarioDetail as Detail,
  type StrategyResult,
} from "./api";
import { candidateTitle, directionLabel, formatMove, strategyLabel } from "./detail";
import { championCandidate, FAMILY_LABELS, resultForStrategy } from "./family";
import { isThinPool, legPrices, validPairsForExpiry } from "./expiry";
import { heatmapProps } from "./heatmap";
import { getScenarioCached } from "./fetchCache";
import {
  directionTagClass, failureLabel, formatAnalyzedAt, formatReturn,
  isRetryDisabledByRateLimit, money, moneyOrDash, rateLimitCountdownText,
  rateLimitHeadline, type DirectionTag,
} from "./scenarios";
import { useCountdownSeconds } from "./useCountdown";
import { useIsDesktop } from "./useIsDesktop";

/**
 * OG-06（#321）身分列方向 tag：`view.direction` 是後端算好的既有欄位
 * （`option_chaser/store.py::serialize_result()`，字面值與
 * `scenarios.ts::DirectionTag` 三態相同），這裡窄化型別才能重用既有
 * `directionTagClass()`（`.tag.up`／`.down`／`.flat`），不新增第二份
 * 「看漲／看跌／持平對應什麼顏色」規則——跟 `ScenarioList.tsx` 的
 * `deriveDirectionTag()` 是不同的事：那裡是清單列沒有這個欄位、只能
 * 前端衍生；這裡是引擎已經給了值，只是型別是寬鬆的 `string`，需要
 * 窄化成 `DirectionTag` 才能餵給共用的顏色對照函式。未知代碼（理論上
 * 不會發生）與 `undefined`（尚未分析）一律當「持平」處理，不猜方向。
 */
function narrowDirectionTag(direction: string | undefined): DirectionTag {
  return direction === "bullish" || direction === "bearish" ? direction : "flat";
}

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

/**
 * Payoff Heatmap（spec #102 決策 A）：候選身分、名次、目標報酬與候選池
 * 過少警語已搬到上方的「基準候選」區塊——這裡只剩圖本身。
 */
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
  return (
    <section className="card">
      <h2 className="section-title">劇本主圖</h2>
      {/* Crossover Boundary（#116）：只有 Spread 候選（兩條腿）有這個
          概念——單腿候選（買腿本身就是持倉，沒有「跟自己比較」的
          Crossover 概念）刻意不傳這個 prop，讓 `Heatmap` 完全不渲染
          相關區塊，不是渲染成「缺席」。 */}
      <Heatmap {...heatmapProps(view, candidate)} />
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
 *
 * T11（#229，Initial V2）：`candidate`／`result` 改由呼叫端傳入跨
 * family 冠軍（`family.ts::championCandidate`）與冠軍自己的
 * `StrategyResult`——這是 AC 明文要求的「口徑升級」本身（詳見
 * CONTEXT.md「Per-family Representative」／「Family Tab」兩節）：
 * 「策略」這一格與候選池過少警語現在說的是冠軍所屬的那個 subtype，
 * 不再是 `results[0]`（多 family 之後只是「第一個被展開的 subtype」，
 * 不保證是冠軍）。既有單一 family 劇本的 `championCandidate` 恆等於
 * 舊版 `primaryResult` 的候選，數字逐位元不變。
 */
/**
 * 劇本設定（OPTION-CHASER-CLOSEOUT-001，項目 2）：使用者原本建立這個
 * 劇本時填的東西——標的、目標價、目標年月、系統依此推導出的方向、
 * 以及使用者勾選啟用的 Strategy Family。放在 `Summary`（哪一組候選
 * 表現最好）之前，讓使用者先確認「我現在看的劇本是什麼」，再看這個
 * 劇本下的最佳策略——兩件事分屬不同的卡片，不要混在同一張裡。
 *
 * 零金融計算：`direction` 是後端 `derive_direction()` 算好、與
 * `family_eligibility` 同一個判準的既有欄位（見 `option_chaser/
 * store.py::serialize_result()`），這裡只格式化顯示；`strategies`
 * 是使用者建立／編輯劇本時勾選的既有欄位（`ScenarioDetail.strategies`，
 * `FamilyTabs` 也讀同一個 prop），不是重新計算出來的。
 */
function ScenarioContext({ view, strategies }: {
  view: AnalysisView;
  strategies: readonly string[];
}) {
  return (
    <section className="card summary-card" aria-label="劇本設定">
      <div className="summary-grid">
        <Stat label="標的">{view.meta.symbol}</Stat>
        <Stat label="目標價">{money(view.params.target_price)}</Stat>
        <Stat label="目標年月">{view.params.target_month}</Stat>
        <Stat label="方向">{directionLabel(view.direction)}</Stat>
        <Stat label="啟用的策略類型">
          {strategies.length > 0
            ? strategies.map((code) => FAMILY_LABELS[code] ?? code).join("、")
            : "—"}
        </Stat>
      </div>
    </section>
  );
}

function Summary({ view, candidate, result, analyzedAt }: {
  view: AnalysisView;
  candidate: Candidate | null;
  result: StrategyResult | null;
  analyzedAt: string | null;
}) {
  const strategy = candidate?.strategy ?? view.params.strategy;
  const pool = result ? validPairsForExpiry(result, view.baseline_expiry) : null;
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
        {/* QA 修正：最高／最低就是 Heatmap 價格軸上下限的來源，也是
            圖上那兩個錨點標記的數字——不放在這裡，使用者對不上。
            沒填就顯示「—」，不是把整格藏起來（藏起來會讓人以為這個
            劇本沒有這個概念）。 */}
        <Stat label="最高">{moneyOrDash(view.params.best_price)}</Stat>
        <Stat label="最低">{moneyOrDash(view.params.worst_price)}</Stat>
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

/**
 * 有結果時的頁面主體。
 *
 * T11（#229，Initial V2）：`candidate`／`result` 只取一次、全域共用
 * ——但取的是**跨 family 冠軍**（`championCandidate`），不是舊版的
 * `baselineTopCandidate`／`primaryResult`。摘要（Summary）、Historical
 * IV、主圖（Chart）、Spread 淨成本走勢（SpreadHistory）四塊固定顯示
 * 冠軍，不隨下方 `FamilyTabs` 的分頁切換而改變——沿用 QA1-06「主圖就是
 * 主圖，不跟著別處的互動改變」的既有原則，延伸到 family 這個新維度。
 * 「依到期日分組」的排名內容（`ExpiryStructure`／`CandidatePool`／
 * `AnalysisReport`）改由 `FamilyTabs` 依目前選中的分頁各自決定，不再
 * 全域固定於冠軍所屬的那個 family——這樣使用者切到別的分頁才看得到
 * *那個* family 自己的候選，不是冠軍的候選重複顯示三次。
 */
function DetailBody({ scenarioId, view, analyzedAt, strategies }: {
  scenarioId: string;
  view: AnalysisView;
  analyzedAt: string | null;
  strategies: readonly string[];
}) {
  const isDesktop = useIsDesktop();
  const candidate = championCandidate(view);
  const result = candidate ? resultForStrategy(view, candidate.strategy) : null;
  return (
    <>
      {/* OPTION-CHASER-CLOSEOUT-001：劇本設定（使用者原本建立的
          context）排在最佳策略內容之前——先知道「這是什麼劇本」，
          再看「這個劇本下最好的候選」。 */}
      <ScenarioContext view={view} strategies={strategies} />
      {/* spec #102 決策 A 的資訊階層不變，只是前三格（劇本摘要／基準
          候選／進場成本）合併成同一張高密度卡：摘要 →〔IV History
          插槽〕→ Payoff Heatmap，全部圍繞同一組
          baseline 候選。 */}
      <Summary view={view} candidate={candidate} result={result} analyzedAt={analyzedAt} />
      <IvHistory scenarioId={scenarioId} candidate={candidate} analyzedAt={analyzedAt} />
      {/* OG-06（#321）：桌面版把「劇本主圖＋Strategy Family 分頁」換成
          Binance trade page 式的三欄外殼（`DesktopDetail.tsx`）——左欄
          family tabs／到期日 chip／排名表，中央欄常駐 Heatmap 跟著
          排名表目前選取的那一列。手機版走的仍是原本這兩個元件，逐
          位元組不變（`DesktopDetailBody` 只在 `isDesktop` 為真時掛載，
          兩條渲染路徑完全不相交，跟 `ScenarioList.tsx`／
          `CompactScenarioList.tsx` 刻意分開是同一種策略）。 */}
      {isDesktop ? (
        // OG-07（#325）：桌面版的 Spread 淨成本走勢／原始資料搬進
        // `DesktopDetailBody` 底部 tab（`scenarioId`／`analyzedAt` 因此
        // 改由這裡往下傳），不再跟手機版共用這裡全域掛載的那兩份。
        <DesktopDetailBody view={view} strategies={strategies} champion={candidate}
                            scenarioId={scenarioId} analyzedAt={analyzedAt} />
      ) : (
        <>
          <Chart view={view} candidate={candidate} />
          {/* Strategy Family 分頁（T11／#229）：到期日結構／候選池／
              分析報告依目前選中的 family 各自呈現，單一 family 時完全
              不畫分頁列（視覺上與 T11 之前逐位元相同）。 */}
          <FamilyTabs view={view} strategies={strategies} />
          {/* #69：`key` 綁定這次分析的身分——新分析一到，React 直接卸載
              重掛這兩個元件，內部 state（已抓到的資料、`<details
              open>`）連同歸零，不會在畫面上混用新舊 cache。刷新後收合、
              下次展開重新取得（需求方裁示接受，資料正確性優先）。
              `analyzedAt` 為 null 的情況實務上不會發生於此（本區塊只在
              `latest_result` 非 null 時渲染，兩者恆同時有值），仍給個
              穩定佔位字串應付型別。兩個 key 各自加前綴——這兩個元件是
              同一層的相鄰手足，若共用同一個 key 字串，React 會把它們
              當成同一組鍵而發出「key 重複」警告，重掛的保證也就不可靠
              了。OG-07（#325）：這兩行只搬進手機分支、位置與既有輸出
              順序不變（先前也是緊接在 `Chart`／`FamilyTabs` 之後），
              手機畫面逐位元組不變。 */}
          <SpreadHistory key={`spread-history-${analyzedAt ?? "none"}`}
                         scenarioId={scenarioId} candidate={candidate} />
          <RawData key={`raw-data-${analyzedAt ?? "none"}`}
                   scenarioId={scenarioId} analyzedAt={analyzedAt} />
        </>
      )}
    </>
  );
}

/**
 * SCALE-05（#260）：抽成獨立元件才能在裡面呼叫 `useCountdownSeconds()`
 * ——這個 hook 只在限流失敗（有 `blocked_until` 可倒數）時才需要跑，
 * 但它掛在整份 `ScenarioDetail` 主體裡會變成「有時候呼叫、有時候不」
 * 的條件式 hook（違反 React hook 規則）；獨立成子元件後，呼叫與否
 * 變成「這個元件有沒有被掛載」，hook 本身在它自己的函式體內永遠是
 * 無條件呼叫一次，合法。
 */
function RefreshFailureNotice({ failure, onRefresh }: {
  failure: RefreshFailure;
  onRefresh?: () => void;
}) {
  const rateLimit = failure.stage === "rate_limited" ? failure.rateLimit : null;
  const remaining = useCountdownSeconds(rateLimit?.blocked_until ?? null);
  return (
    <div className="notice error" role="alert">
      <div className="row-value">
        {rateLimit ? rateLimitHeadline(rateLimit.incident) : failureLabel(failure.stage)}
      </div>
      <p className="caption">
        {/* SCALE-05（#260，AC-2）：限流失敗改講結構化倒數，不解析
            `message` 字串；其餘失敗沿用既有訊息原文。 */}
        {rateLimit ? rateLimitCountdownText(remaining ?? 0) : failure.message}
      </p>
      <button className="text-button" onClick={onRefresh}
             disabled={isRetryDisabledByRateLimit(failure, remaining)}>
        重試
      </button>
    </div>
  );
}

export default function ScenarioDetail({
  id,
  refreshedAt = null,
  busy = false,
  failure,
  onRefresh = () => {},
  updating = false,
  onEdit,
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
  /**
   * 這個劇本正在被刷新（T08／#196 P1「更新中徽章」，前身是 V4 跟進票
   * ／#136 的整段鎖定）：桌面 master/detail 常駐，右側開著的劇本若正在
   * 被 Refresh Run 或單一劇本刷新處理，畫面上的數字是上一輪的舊快照，
   * 不能讓它看起來像已經是這一輪的結果——比 `busy`（任何劇本在跑都算）
   * 更精確，`busy` 只影響按鈕文案／停用，這個才是「這一個劇本」的狀態。
   * 純資訊性提示，不影響頁面其餘內容是否可瀏覽。
   */
  updating?: boolean;
  /**
   * OG-06（#321）：桌面身分列的「編輯」入口——桌面走 OG-02 既有抽屜
   * （`App.tsx::startEdit`，跟劇本庫卡片編輯鈕開的是同一個表單、同一份
   * `editing` state）。手機版沒有這個按鈕（既有編輯入口在
   * `CompactScenarioList.tsx` 的卡片上，這裡不重複一份）——因此下面
   * render 時額外用 `isDesktop` 二次守門，不只靠「呼叫端傳不傳這個
   * prop」決定手機要不要出現：`App.tsx` 的 `detailProps` 手機／桌面
   * 共用同一份，兩邊都會拿到這個 callback，傳了也無害。
   */
  onEdit?: () => void;
}) {
  const isDesktop = useIsDesktop();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // T03（#187）：以 (id, refreshedAt) 為資料身分快取——`refreshedAt`
  // 還沒對上目前劇本庫清單的最新值（null）時容忍沿用已有快取，真的
  // 對上新版本才重抓；deep-link 開頁常見的三次重複下載因此收斂成
  // 有意義的一到兩次。`release()` 掛在清理函式：換頁或 id／refreshedAt
  // 再變都算「不再需要」，最後一個等待者離開時才真的 abort。
  useEffect(() => {
    let live = true;
    setError(null);
    const { promise, release } = getScenarioCached(id, refreshedAt);
    promise
      .then((d) => { if (live) setDetail(d); })
      .catch((e) => {
        // 換頁後才回來的舊請求不該蓋掉新畫面
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => { live = false; release(); };
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
          <span className="id">
            {/* UI-IMPL-002（#092，Identity 板）：真實品牌 Logo，找不到
                就整個消失、只留標題文字——`StockLogo` 自己處理三種狀態。
                桌面 40px（`size="l"`），身分列 Logo 尺寸 AC 明文要求
                （OG-06／#321）與這裡既有的 `size="l"` 本來就是同一個
                數字，不必另外調整。 */}
            {detail?.symbol && <StockLogo symbol={detail.symbol} size="l" />}
            <h1 className="toolbar-title">{detail?.symbol ?? "劇本"}</h1>
            {/* OG-06（#321）身分列方向 tag，桌面限定。`detail.latest_
                result` 尚未載入（載入中／尚未分析）時沒有 `direction`
                可讀，不畫。 */}
            {isDesktop && detail?.latest_result && (
              <span className={`tag ${directionTagClass(
                narrowDirectionTag(detail.latest_result.direction))}`}>
                {directionLabel(detail.latest_result.direction)}
              </span>
            )}
          </span>
          <span className="toolbar-actions">
            {/* OG-06（#321）：身分列的「編輯」入口，桌面限定——桌面走
                OG-02 既有抽屜（`onEdit` 即 `App.tsx::startEdit`）。手機
                版編輯入口在劇本庫卡片上，這裡不重複一份。 */}
            {isDesktop && onEdit && (
              <button className="pill secondary" onClick={onEdit}>
                編輯
              </button>
            )}
            {/* #70：與劇本庫功能列同一個視覺語言（標題列右側膠囊鈕），
                走既有的單一劇本刷新端點——不是第四種獨立管道。已過期
                （#68）沿用清單卡片同一句文案並停用——後端會把它當無害
                no-op，按了等於沒按，不該讓它看起來還有用。 */}
            <button className="pill" onClick={onRefresh}
                   disabled={busy || detail?.expired}>
              {detail?.expired ? "已過期，不再刷新" : busy ? "刷新中……" : "重新整理"}
            </button>
          </span>
        </div>

        {/* OG-06（#321）`/code-review` Spec 軸跟進：身分列票面明文要求
            現價／目標價（含所需漲跌幅）／目標年月／資料時間／資料來源
            都在同一列——先前一版只加了 Logo／方向 tag／編輯鈕，把這五
            項留在下方 `Summary` 卡裡就當作滿足了，Spec 審查抓到這是
            未揭露的落地縮水，這裡補齊。跟 `Summary` 顯示同樣的數字是
            刻意的重複，不是資料來源分裂：兩處都直接讀 `view.meta`／
            `view.params`，同一份既有欄位、同一套既有格式化函式
            （`money`／`formatMove`／`formatAnalyzedAt`），只是身分列這裡
            用更精簡的一行、`Summary` 保留完整統計格線（買賣腿價格等身分
            列裝不下的細節）。桌面限定——手機版沒有這一行，資訊仍只在
            `Summary`（既有位置，逐位元組不變）。 */}
        {isDesktop && detail?.latest_result && (
          <div className="toolbar-row detail-identity-meta">
            <span className="cell-sub">
              現價 {moneyOrDash(detail.latest_result.meta.spot)}
            </span>
            <span className="cell-sub">
              目標 {money(detail.latest_result.params.target_price)}
              （{formatMove(detail.latest_result.meta.target_move)}）
            </span>
            <span className="cell-sub">{detail.latest_result.params.target_month}</span>
            <span className="cell-sub">{formatAnalyzedAt(detail.latest_analyzed_at)}</span>
            <span className="cell-sub">{detail.latest_result.meta.source}</span>
          </div>
        )}
      </header>

      {/* T08／#196 P1：正在被刷新（Refresh Run 或單一劇本刷新）——桌面
          右側常駐面板最容易讓使用者誤以為畫面已經更新完，所以放在最
          上面、搶在其他任何內容之前。純資訊性提示，不影響下面內容是否
          可瀏覽（P1 明文：全程可瀏覽、可進詳細頁）。刻意跟下面的失敗
          提示互斥判斷分開：更新中時失敗提示還沒有意義（這次嘗試根本
          還沒有結論），等它解決後若真的失敗，下面那段才會出現。 */}
      {updating && (
        <div className="notice warn" role="status">
          本輪刷新排隊中或進行中，以下暫時是上一輪的舊資料。
        </div>
      )}

      {/* 上次刷新失敗時沿用劇本庫卡片同一套分層指引與就地重試
          （V4／#52 既有語彙），不是重新發明一套說法。已過期優先於刷新
          失敗（#68 既有判斷）：兩種狀態同時出現會讓使用者搞不清楚現在
          是哪一種。 */}
      {!updating && failure && !detail?.expired && (
        <RefreshFailureNotice failure={failure} onRefresh={onRefresh} />
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
                    analyzedAt={detail.latest_analyzed_at}
                    strategies={detail.strategies} />
      )}
    </div>
  );
}
