/**
 * 到期日結構（V6／#54）：橫向到期日按鈕 → 該期 Top 10 窄列。
 *
 * 這是頁面上**唯一**的到期日結構——舊 Streamlit 版的「到期日分組比較」
 * 不搬遷（v3 #7' 裁示：與本層重複）。
 *
 * 兩個互動決定：
 * - 切換到期日只換下面的清單，**不動主圖**。主圖固定是 baseline 期的
 *   第 1 名（QA1-06 的既有裁示：主圖就是主圖）。
 * - 展開候選用原生 `<details>`：純瀏覽器行為，不觸發任何重繪、不跳動
 *   頁面位置，鍵盤與螢幕閱讀器也不必另外處理——這正是 QA1-06 當初把
 *   「選看」按鈕換掉的理由。
 */
import { useState } from "react";

import Heatmap from "./Heatmap";
import type { AnalysisView, Candidate } from "./api";
import { candidateTitle, strategyLabel } from "./detail";
import {
  expiryOptions, isThinPool, legPriceEntries, legPrices, resolveExpiry,
  type ExpiryBearing,
} from "./expiry";
import { heatmapProps } from "./heatmap";
import { formatReturn, money } from "./scenarios";

function CandidateRow({ view, candidate, rank }: {
  view: AnalysisView; candidate: Candidate; rank: number;
}) {
  const prices = legPrices(candidate);
  // T16（#232，Initial V2，`/code-review` Standards 軸抓到）：命名這個
  // 判準，不留一個沒有名字的 `> 2`——固定「買／賣」兩欄的收合摘要只
  // 服務兩腿以下候選，三腿以上（Butterfly）才需要逐腿列出。這條邊界
  // 是這個元件自己「摘要版式選哪一種」的規則，跟 `IvHistory.tsx` 的
  // `supportsIvHistory`（IV pipeline 結構上支援哪些腿數）是兩件不同
  // 的事，只是今天恰好同一個數字——沒有強行共用一個跨檔常數，避免
  // 兩個不相干的邊界被綁死在一起。
  const isMultiLeg = candidate.legs.length > 2;
  return (
    <li>
      <details className="candidate">
        <summary>
          {/* SW-10（#340，Owner 真機驗收）：`.candidate-title`（買 X／
              賣 Y 這句 legs 描述）原本跟 rank／subtype／return 擠在
              同一個 `align-items:baseline` 橫向列裡，自己卻沒有
              `white-space:nowrap` 保護——手機窄螢幕上四個元素爭同一行
              寬度，legs 描述常常是最長的那個，擠不下就在瀏覽器預設
              斷行規則下被硬拆成兩行，看起來就是 Owner 點名的「被擠成
              很奇怪的直向排列」。改成兩層：上排 rank／subtype／return
              維持橫向、彼此都是短字串不會擠；legs 描述改成獨立一整行
              （`.candidate-title` 現在有整行寬度可以用，不再需要跟
              別人搶），這樣 strategy name／legs／return 三者各自一層，
              視覺層級更清楚，也不必再靠犧牲可讀性的截斷來換取密度。 */}
          <span className="candidate-head">
            <span className="candidate-head-top">
              <span className="rank">#{rank}</span>
              {/* T11（#229，Initial V2）：這組候選實際跑的 subtype——多
                  family 並存後，同一個排名池裡的候選可能來自不同
                  subtype（今天仍恆為單一 subtype，見 `family.ts` 說明），
                  每一列都標示出來，不是等到真的混合時才補。 */}
              <span className="candidate-subtype">{strategyLabel(candidate.strategy)}</span>
              <span
                className={
                  candidate.baseline_return >= 0
                    ? "candidate-return positive"
                    : "candidate-return negative"
                }
              >
                {formatReturn(candidate.baseline_return)}
              </span>
            </span>
            <span className="candidate-title">{candidateTitle(candidate)}</span>
          </span>
          {/* 三個價格就在收合狀態下看得到——要比較幾組候選時，把每一組
              都展開一次才看得到成本是折磨。

              T16（#232，Initial V2）：三腿以上（Butterfly）改逐腿列出
              ——固定「買／賣」兩個欄位的既有版式會靜默丟掉中腿口數與
              第三隻腿，AC 明文禁止。既有兩腿／單腿候選走原本的格式，
              逐字不變。 */}
          <span className="candidate-prices">
            {isMultiLeg ? (
              legPriceEntries(candidate).map((entry, i) => (
                <span key={i}>{entry.label} {money(entry.price)}</span>
              ))
            ) : (
              <>
                <span>
                  買 {prices.buyAsk === null ? "—" : money(prices.buyAsk)}
                </span>
                <span>
                  賣 {prices.sellBid === null ? "—" : money(prices.sellBid)}
                </span>
              </>
            )}
            <span>淨成本 {money(prices.net)}</span>
          </span>
        </summary>
        {/* SW-10（#340，Owner 真機驗收）：⚠／🚩 徽章原本掛在上面收合就
            看得到的排名列，Owner 真機驗收明文點名「現在幾乎每筆都有，
            已失去資訊價值，只剩視覺噪音」——移除收合列上的徽章，改成
            展開候選細節時才看得到的完整說明，跟桌面版 `DesktopDetail.
            tsx::EntryTab`（OG-07／#325）同一份文案、同一個
            `.candidate-panel-warnings` 容器，只是換了觸發方式（桌面
            點選排名列＝選取；手機展開這個 `<details>`）。不是單純藏
            起來就不管：真的要下單前，資訊仍然找得到，只是不再對「幾乎
            每一列」都重複刷存在感。 */}
        {(candidate.wide_spread_warning || candidate.monotonicity_warning) && (
          <div className="candidate-panel-warnings">
            {candidate.wide_spread_warning && (
              <span className="tag warn" title="Bid/Ask 過寬">⚠ Bid/Ask 過寬</span>
            )}
            {candidate.monotonicity_warning && (
              <span className="tag suspect"
                    title="報價與鄰近履約價不一致，疑似陳舊報價">
                🚩 疑似陳舊報價
              </span>
            )}
          </div>
        )}
        {/* Crossover Boundary（#116）：同 `ScenarioDetail.tsx` 的判準
            ——單腿候選不傳 `comparator`，不是渲染成「缺席」。 */}
        <Heatmap {...heatmapProps(view, candidate)} />
      </details>
    </li>
  );
}

export default function ExpiryStructure({
  view,
  result,
  baselineExpiry,
}: {
  view: AnalysisView;
  /** T11（#229，Initial V2）：窄化為 `ExpiryBearing`——多 family 並存
   *  後，這裡收到的可能是 `family.ts::mergedExpiryTop10()` 合併多個
   *  subtype 排名池後的結果，不是完整的 `StrategyResult`。既有單一
   *  family 呼叫端（傳入真正的 `StrategyResult`）結構上仍然相容。 */
  result: ExpiryBearing;
  baselineExpiry: string | null;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const options = expiryOptions(view, result);
  // 選中的那期由純函式決定：重新分析後該期可能整個消失，此時退回
  // baseline 而不是留在一個空白清單上。
  const current = resolveExpiry(options, picked, baselineExpiry);
  const shown = options.find((o) => o.expiry === current);

  if (options.length === 0) return null;

  return (
    <section className="card">
      <h2 className="section-title">到期日</h2>

      {/* 真正橫向並排、可橫向滑動——不是換行成好幾列的按鈕堆。
          刻意**不用** `role="tablist"/"tab"`：那個模式還要求 tabpanel、
          aria-controls 與方向鍵巡覽，只掛角色名等於對輔助技術宣告一套
          自己沒實作的操作方式。一排 `aria-pressed` 的按鈕就是它真正的樣子。 */}
      <div className="chip-strip" role="group" aria-label="到期日">
        {options.map((option) => (
          <button
            key={option.expiry}
            aria-pressed={option.expiry === current}
            className={option.expiry === current ? "chip selected" : "chip"}
            onClick={() => setPicked(option.expiry)}
          >
            <span className="chip-date">{option.expiry}</span>
            <span className="chip-return">{formatReturn(option.bestReturn)}</span>
          </button>
        ))}
      </div>

      {/* 常駐的 live region：切到組數過少的那一期時，變的是**內容**，
          螢幕閱讀器才會唸出來。整塊連同容器一起掛上去的話，插入的瞬間
          內容就已經在了，播報與否各家實作不一。空的時候用 CSS 收起來。 */}
      <div className="notice warn" role="status">
        {shown && isThinPool(shown.count) && (
          <>
            <span aria-hidden="true">⚠ </span>
            該期僅 {shown.count} 組候選通過品質過濾，排名參考價值有限。
          </>
        )}
      </div>

      {shown && (
        <ul className="candidate-list">
          {shown.candidates.map((candidate, i) => (
            <CandidateRow
              key={candidate.candidate_key}
              view={view}
              candidate={candidate}
              rank={i + 1}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
