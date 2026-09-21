/**
 * 劇本詳細頁（MVP V3／#103，資訊階層依 spec #102 決策 A 重整；OG-10／
 * #327 起手機版整頁順序依 artifact「Mobile 劇本詳細」板重排，桌面版
 * 這份順序描述與 `DesktopDetailBody` 自己的檔頭各自獨立維護）：
 *
 * **共用（`isDesktop` 分流之前，兩邊都渲染）**：劇本設定
 * （OPTION-CHASER-CLOSEOUT-001：使用者原本建立的 context——標的／目標
 * 價／目標年月／方向／啟用的 family）→ 摘要（含基準候選與進場成本，
 * QA 修正後三卡合一）。
 *
 * **手機分支**（OG-10／#327）：Family tabs／到期日 chip／排名表
 * （`FamilyTabs`，含既有「就地展開候選看 Heatmap」native `<details>`
 * 機制不動）→ 劇本主圖（常駐 Heatmap＋三價位階梯，跨 family 冠軍）→
 * 進場面板（逐腿最差價＋Payoff／Greeks 摘要，同一組冠軍）→ Historical
 * IV → Spread 淨成本走勢／原始資料（兩張收合卡）。
 *
 * **桌面分支**：`DesktopDetailBody`（OG-06／#321 起的三欄外殼），順序
 * 見該檔案自己的檔頭。
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

import { PositionSensitivity, RiskPayoff, Row } from "./AnalysisReport";
import DesktopDetailBody from "./DesktopDetail";
import FamilyTabs from "./FamilyTabs";
import IvHistory from "./IvHistory";
import Heatmap from "./Heatmap";
import PriceLadder from "./PriceLadder";
import RawData from "./RawData";
import SpreadHistory from "./SpreadHistory";
import StockLogo from "./StockLogo";
import {
  legQuantityPrefix, legSide,
  type AnalysisView,
  type Candidate,
  type RefreshFailure,
  type ScenarioDetail as Detail,
  type StrategyResult,
} from "./api";
import { candidateTitle, directionLabel, formatMove, strategyLabel } from "./detail";
import { championCandidate, FAMILY_LABELS, familyOf, resultForStrategy } from "./family";
import { isThinPool, legPrices, validPairsForExpiry } from "./expiry";
import { heatmapProps } from "./heatmap";
import { getScenarioCached } from "./fetchCache";
import {
  directionTagClass, failureLabel, formatAnalyzedAt, formatDaysLeft, formatReturn,
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
 * `/code-review` Standards 軸跟進：桌面身分列（OG-06／#321）與 SW-06
 * 新增的手機 `MobileHero` 各自組出同一顆方向 pill，`className`／子節點
 * 完全同一句拼法——抽成這個小元件讓兩處只有一份渲染邏輯，不是兩份
 * 各自維護、以後改一邊漏了另一邊。 */
function DirectionTag({ direction }: { direction: string | undefined }) {
  return (
    <span className={`tag ${directionTagClass(narrowDirectionTag(direction))}`}>
      {directionLabel(direction)}
    </span>
  );
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
      {/* OG-10（#327）：手機版之前一直沒有渲染三價位階梯（桌面
          OG-06／#321 起才第一次真的畫出這個既有欄位）——同一張卡、
          Heatmap 正下方，跟桌面中央欄 Heatmap＋PriceLadder 同一個
          相對位置，不是另外開一張卡。 */}
      <PriceLadder points={candidate.price_ladder ?? []} />
    </section>
  );
}

/**
 * 進場面板（OG-10／#327，artifact「進場 · 最差成交口徑」卡）：手機版
 * 沒有桌面 OG-07 那種右欄分頁介面（進場／Payoff／Greeks／報告四個
 * tab），把 Entry／Payoff／Greeks 三塊內容攤平成同一張連續捲動的卡片
 * ——逐腿最差成交價的格式化沿用桌面 `DesktopDetail.tsx::EntryTab` 同一句
 * `${legSide(leg)} ${legQuantityPrefix(leg)}${leg.strike}`（順序也對齊：
 * 逐腿列在前、淨成本在後），Payoff／Greeks 兩段直接重用
 * `AnalysisReport.tsx` 既有 export 的 `RiskPayoff`／`PositionSensitivity`
 * （跟桌面 `PayoffTab`／`GreeksTab` 同一份純函式），不重新發明第二套
 * 格式化規則或另外算一次 Max Profit／Breakeven／Greeks（那些既有的
 * 策略分支——例如 Butterfly 不對稱獲利區間、CLOSEOUT-004 的「$X 以上」
 * 寫法——只有一份實作，這裡繼續共用）。
 *
 * `/code-review` Standards 軸跟進：這裡只印「最差成交會用到的那一邊」
 * 一個數字，不像 `EntryTab` 逐腿雙邊 Bid／Ask／IV／過寬與陳舊報價警示
 * 都印——跟 artifact「進場 · 最差成交口徑」卡本身的版位一致（也只有
 * 單邊價格），這兩項警示在同一頁上方 `FamilyTabs` 的排名列本來就會顯示
 * （`ExpiryStructure.tsx::CandidateRow` 既有的 ⚠／🚩 tag），刻意不在
 * 這裡重複第二份，不是漏掉。「最差成交要用哪一邊」這句
 * `leg.side === "buy" ? leg.ask : leg.bid` 三元運算式跟 `expiry.ts::
 * legPrices()`／`legPriceEntries()`、`EntryTab` 的 CSS class 選邊，
 * 已是第三個各自獨立的既有寫法（跟 OG-08 檔頭記錄過的「單腿候選判準
 * 散落 4 處」同一種既知不一致，本票不在範圍內統一，避免動到桌面既有
 * 呈現）。
 *
 * 固定顯示**跨 family 冠軍**（跟 `Summary`／`Chart` 同一組候選，QA1-06
 * 既有原則：主圖／進場面板不隨下方 `FamilyTabs` 切換的分頁而改變）。
 */
function EntryPanel({ candidate }: { candidate: Candidate | null }) {
  if (!candidate) return null;
  return (
    <section className="card">
      {/* SW-06（#335）文案去術語：「口徑」是內部工程詞彙，一般使用者
          不需要懂——語意不變（仍是「以最差成交價假設」這件事），只是
          换成看得懂的講法。 */}
      <h2 className="section-title">進場 · 以最差成交價計算</h2>
      {candidate.legs.map((leg, i) => (
        <Row key={i} label={`${legSide(leg)} ${legQuantityPrefix(leg)}${leg.strike}`}>
          {money(leg.side === "buy" ? leg.ask : leg.bid)}
        </Row>
      ))}
      <Row label="淨成本 / 股">{money(candidate.natural_cost)}</Row>
      <RiskPayoff candidate={candidate} />
      <PositionSensitivity candidate={candidate} />
    </section>
  );
}

/**
 * SW-06（#335）手機詳細頁 Hero 白卡：artifact「手機劇本詳細」板頂部
 * ——logo＋代號＋方向 pill＋「目標 X · 目標月」，右側冠軍報酬大字＋
 * 「劇本報酬 · family」副標，下方四格關鍵指標（現價／還需／距目標／
 * 來源＋時間）。
 *
 * 刻意獨立於下面既有的 `ScenarioContext`／`Summary` 兩張卡，不是把
 * 它們拆掉重組：那兩張卡承載的完整資訊（買腿 Ask／賣腿 Bid／淨成本／
 * 最高／最低……）與既有測試斷言都逐位元不變（跟 OG-06 桌面身分列同一
 * 個既有前例——`view.meta`／`candidate.baseline_return` 在畫面上出現
 * 兩次是刻意的重複呈現，不是資料來源分裂：兩處都讀同一份既有欄位）。
 * 只在手機分支渲染（呼叫端已經在 `!isDesktop` 底下），桌面身分列維持
 * OG-06 原樣不受影響。
 *
 * 「距目標」讀 `days_to_anchor`（既有欄位，`ScenarioSummary` 契約，
 * `ScenarioList`／`CompactScenarioList` 已經在用同一個
 * `formatDaysLeft()`），不是這裡重新算日期——後端已經用「目標月第三個
 * 星期五」這個既有錨點算好，前端不重算第二份。
 *
 * 揭露的落差：artifact 這裡還畫了「代號旁的公司名」，但站上目前唯一的
 * 標的識別資料源（Logo.dev ticker endpoint，`StockLogo.tsx`）只回傳
 * 圖片、沒有公司全名這個欄位，後端 `ScenarioSummary` 契約也沒有這個
 * 欄位——沒有這一格就等於編造文字，違反 Logo 政策「找不到就不顯示，
 * 絕不替代」延伸到文字的精神，這裡刻意只留代號本身。
 */
function MobileHero({ view, candidate, analyzedAt, daysToAnchor }: {
  view: AnalysisView;
  candidate: Candidate | null;
  analyzedAt: string | null;
  daysToAnchor: number;
}) {
  if (!candidate) return null;
  const family = familyOf(candidate.strategy);
  return (
    <section className="card mobile-hero" aria-label="劇本頭條">
      <div className="mobile-hero-top">
        <span className="mobile-hero-id">
          <StockLogo symbol={view.meta.symbol} size="l" />
          <span className="mobile-hero-symbol">{view.meta.symbol}</span>
          <DirectionTag direction={view.direction} />
        </span>
        <span className="mobile-hero-return-block">
          <span
            className={`mobile-hero-return ${
              candidate.baseline_return >= 0 ? "positive" : "negative"
            }`}
          >
            {formatReturn(candidate.baseline_return)}
          </span>
          <span className="caption">
            劇本報酬 · {FAMILY_LABELS[family] ?? family}
          </span>
        </span>
      </div>
      <p className="cell-sub mobile-hero-target">
        目標 {money(view.params.target_price)} · {view.params.target_month}
      </p>
      <div className="mobile-hero-stats">
        <Stat label="現價">{money(view.meta.spot)}</Stat>
        <Stat label="還需">{formatMove(view.meta.target_move)}</Stat>
        <Stat label="距目標">{formatDaysLeft(daysToAnchor)}</Stat>
        <Stat label="來源">
          <span className="mobile-hero-source">
            <span>{view.meta.source}</span>
            <span className="row-note">{formatAnalyzedAt(analyzedAt)}</span>
          </span>
        </Stat>
      </div>
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
function DetailBody({ scenarioId, view, analyzedAt, strategies, daysToAnchor }: {
  scenarioId: string;
  view: AnalysisView;
  analyzedAt: string | null;
  strategies: readonly string[];
  daysToAnchor: number;
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
      {/* OG-06（#321）：桌面版把「劇本主圖＋Strategy Family 分頁」換成
          Binance trade page 式的三欄外殼（`DesktopDetail.tsx`）——左欄
          family tabs／到期日 chip／排名表，中央欄常駐 Heatmap 跟著
          排名表目前選取的那一列。手機版走的是完全不同的一條渲染路徑
          （`DesktopDetailBody` 只在 `isDesktop` 為真時掛載，兩條路徑
          完全不相交，跟 `ScenarioList.tsx`／`CompactScenarioList.tsx`
          刻意分開是同一種策略），本票（OG-10／#327）只重排手機分支
          內部的順序，桌面這個分支逐位元組不變。 */}
      {isDesktop ? (
        // OG-07（#325）：桌面版的 Spread 淨成本走勢／原始資料搬進
        // `DesktopDetailBody` 底部 tab（`scenarioId`／`analyzedAt` 因此
        // 改由這裡往下傳），不再跟手機版共用這裡全域掛載的那兩份。
        <DesktopDetailBody view={view} strategies={strategies} champion={candidate}
                            scenarioId={scenarioId} analyzedAt={analyzedAt} />
      ) : (
        <>
          {/* SW-06（#335）：Hero 白卡放在手機分支最前面，OG-10 既有
              「FamilyTabs → Chart → PriceLadder → EntryPanel → IvHistory
              → 後續連結」這段順序完全不動，Hero 只是加在它們之前，不是
              插進中間或取代任何一段。 */}
          <MobileHero view={view} candidate={candidate} analyzedAt={analyzedAt}
                      daysToAnchor={daysToAnchor} />
          {/* OG-10（#327）：手機整頁順序依 artifact「Mobile 劇本詳細」
              板重排——Family tabs／到期日 chip／排名表（`FamilyTabs`
              內部，含既有「就地展開候選看 Heatmap」native `<details>`
              機制，逐位元組不動：AC 明文「候選展開零請求」既有斷言不得
              刪減弱化）排在「劇本主圖」常駐 Heatmap／三價位階梯／進場
              面板之前，Historical IV 排在進場面板之後、兩個底部收合卡
              （淨成本走勢／原始資料）之前。跟票面「三個收合列」的唯一
              揭露落差：候選池診斷／分析報告依然留在 `FamilyTabs` 內部
              （T11／#229 既有的「跟著目前選中的 family」語意，不是
              跟著整頁固定不變）——沒有硬拉出來跟淨成本走勢／原始資料
              湊成三個位置相鄰的列，因為那兩塊本來就是 family-scoped
              資料，跟著整頁固定的淨成本走勢／原始資料語意上是兩件事，
              強行拉平成同一組「三列」會混淆這個既有區分（見 issue #327
              收尾留言的完整說明）。 */}
          <FamilyTabs view={view} strategies={strategies} />
          <Chart view={view} candidate={candidate} />
          <EntryPanel candidate={candidate} />
          {/* OG-08（#326）：桌面版的 Historical IV 改掛進
              `DesktopDetailBody` 右欄（跟著排名表選取列，不是這裡的跨
              family 冠軍）——這份全域掛載點只留給手機版。OG-10（#327）
              把它從「劇本主圖之前」移到「進場面板之後」，對齊 artifact
              的手機版順序；既有 17 條 Historical IV e2e 全部只用
              `.iv-history` 定位、不斷言跟其他區塊的相對順序，位置搬動
              不影響任何既有斷言。 */}
          <IvHistory scenarioId={scenarioId} candidate={candidate} analyzedAt={analyzedAt} />
          {/* #69：`key` 綁定這次分析的身分——新分析一到，React 直接卸載
              重掛這兩個元件，內部 state（已抓到的資料、`<details
              open>`）連同歸零，不會在畫面上混用新舊 cache。刷新後收合、
              下次展開重新取得（需求方裁示接受，資料正確性優先）。
              `analyzedAt` 為 null 的情況實務上不會發生於此（本區塊只在
              `latest_result` 非 null 時渲染，兩者恆同時有值），仍給個
              穩定佔位字串應付型別。兩個 key 各自加前綴——這兩個元件是
              同一層的相鄰手足，若共用同一個 key 字串，React 會把它們
              當成同一組鍵而發出「key 重複」警告，重掛的保證也就不可靠
              了。 */}
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
      {isDesktop ? (
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
              {/* OG-06（#321）身分列方向 tag。`detail.latest_result` 尚未
                  載入（載入中／尚未分析）時沒有 `direction` 可讀，不畫。 */}
              {detail?.latest_result && (
                <DirectionTag direction={detail.latest_result.direction} />
              )}
            </span>
            <span className="toolbar-actions">
              {/* OG-06（#321）：身分列的「編輯」入口——桌面走 OG-02 既有
                  抽屜（`onEdit` 即 `App.tsx::startEdit`）。手機版編輯入口
                  在劇本庫卡片上，這裡（桌面分支）不重複一份。 */}
              {onEdit && (
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

          {/* SW-05（#337）：identity row 補上冠軍報酬大字＋family 副標
              （artifact「右側冠軍報酬 800 大字」），跟手機版 `MobileHero`
              同一組既有欄位、同一套格式化函式——這裡刻意重複渲染同一個
              `championCandidate(view)`，不是另外重新選一次冠軍。 */}
          {detail?.latest_result && (() => {
            const champion = championCandidate(detail.latest_result);
            if (!champion) return null;
            const family = familyOf(champion.strategy);
            return (
              <div className="toolbar-row detail-identity-return-row">
                <span className="cell-sub">
                  目標 {money(detail.latest_result.params.target_price)}
                  {" · "}{detail.latest_result.params.target_month}
                </span>
                <span className="detail-identity-return-block">
                  <span className={`detail-identity-return ${
                    champion.baseline_return >= 0 ? "positive" : "negative"
                  }`}>
                    {formatReturn(champion.baseline_return)}
                  </span>
                  <span className="caption">
                    劇本報酬 · {FAMILY_LABELS[family] ?? family}
                  </span>
                </span>
              </div>
            );
          })()}

          {/* OG-06（#321）`/code-review` Spec 軸跟進：身分列票面明文要求
              現價／目標價（含所需漲跌幅）／目標年月／資料時間／資料來源
              都在同一列——先前一版只加了 Logo／方向 tag／編輯鈕，把這五
              項留在下方 `Summary` 卡裡就當作滿足了，Spec 審查抓到這是
              未揭露的落地縮水，這裡補齊。SW-05（#337）起收成跟手機版
              `MobileHero` 同一組四格（現價／還需／距目標／來源＋時間）
              ——「目標年月」搬進上面新增的那一行（跟目標價同一句），
              不再獨立佔一格；跟 `Summary` 顯示同樣的數字是刻意的重複，
              不是資料來源分裂：兩處都直接讀 `view.meta`／`view.params`／
              既有 `days_to_anchor` 欄位，同一套既有格式化函式（`money`／
              `formatMove`／`formatAnalyzedAt`／`formatDaysLeft`）。 */}
          {detail?.latest_result && (
            <div className="toolbar-row detail-identity-meta">
              <span className="cell-sub">
                現價 {moneyOrDash(detail.latest_result.meta.spot)}
              </span>
              <span className="cell-sub">
                還需 {formatMove(detail.latest_result.meta.target_move)}
              </span>
              <span className="cell-sub">
                距目標 {formatDaysLeft(detail.days_to_anchor)}
              </span>
              <span className="cell-sub">
                {detail.latest_result.meta.source}
                {" · "}{formatAnalyzedAt(detail.latest_analyzed_at)}
              </span>
            </div>
          )}
        </header>
      ) : (
        /**
         * SW-06（#335）：60px 手機詳細頁 header——返回、代號、刷新，
         * 沿用 `.mnav`（`MobileTopBar.tsx`）同一套「60px、sticky、單列
         * flex」既有視覺語言，不是重新發明一個新高度。
         *
         * 揭露的落差：artifact 這一列還有「公司名」與「更多」——公司名
         * 沒有資料源（見 `MobileHero` 檔頭同一句說明）；「更多」在
         * artifact 上沒有指定要放哪些動作，站上目前也沒有任何一個
         * 「還沒地方放」的手機詳細頁級動作（編輯入口本來就在劇本庫卡片
         * 上、垃圾桶動作也不在這頁），無中生有一顆空選單只會是誤導使用
         * 者的裝飾按鈕，這裡刻意不畫。 */
        <header className="detail-bar">
          <a className="nav-back" href="#/">
            ‹ 劇本庫
          </a>
          <span className="detail-bar-title">{detail?.symbol ?? "劇本"}</span>
          <span className="detail-bar-spacer" />
          <button className="pbtn line sm" onClick={onRefresh}
                 disabled={busy || detail?.expired}>
            {detail?.expired ? "已過期，不再刷新" : busy ? "刷新中……" : "重新整理"}
          </button>
        </header>
      )}

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
                    strategies={detail.strategies}
                    daysToAnchor={detail.days_to_anchor} />
      )}
    </div>
  );
}
