/**
 * 桌面詳細頁三欄外殼的左欄與中央欄（OG-06／#321，artifact 的 Desktop
 * 劇本詳細板：trade page 三欄版面）。右欄與底部 tab 區本票只留空容器
 * （OG-07／#325 填）。
 *
 * 這個元件只在桌面 viewport 掛載（`ScenarioDetail.tsx` 的 `DetailBody`
 * 用 `useIsDesktop()` 分流，手機仍走既有 `FamilyTabs`／`ExpiryStructure`
 * 那條渲染路徑，逐位元組不變）——因此可以放心引入跟手機版不同的互動
 * 模型，不必顧慮手機測試會不會被牽動。
 *
 * 與手機版 `FamilyTabs.tsx`／`ExpiryStructure.tsx` 的關鍵差異：
 * 手機版每一列候選各自用原生 `<details>` 收合／展開自己的 Heatmap
 * （QA1-06 既有裁示：純瀏覽器行為，不觸發重繪）；桌面版改成 Binance
 * trade page 的樣子——**只有一個常駐的中央 Heatmap**，跟著左欄排名表
 * 目前選取的那一列（預設＝目前 family／到期日底下的第 1 名；由於冠軍
 * 候選定義上就是冠軍所屬 family 在 baseline 到期日的第 1 名，初始狀態
 * 下這兩個預設值自然重合，不必額外寫一條「先看是不是冠軍」的特判）。
 * 點選一列只是更新這裡的 `selectedKey` state，不重新抓取任何資料
 * ——`view` 早就把整份候選池帶回來了（T09／#191 `CandidateMap`），
 * 切換純粹是換一個已經在記憶體裡的物件參照。
 *
 * 頭條（跨 family 冠軍的策略／報酬／淨成本）不在這裡——那些固定顯示在
 * `ScenarioDetail.tsx` 的 `Summary`，不隨這個元件內部的任何選取變動
 * 而改變，兩者是完全獨立的 state（沿用 T11／#229 既有原則，只是這裡
 * 第一次真的有「選取」這個新維度需要保持獨立）。
 *
 * Family tabs／空狀態文案／到期日 chip／候選池過少警語的組成邏輯直接
 * 重用 `FamilyTabs.tsx`（`resolveFamily`／`emptyFamilyMessage`，本票
 * 起兩者 `export`）與 `family.ts`／`expiry.ts` 既有純函式，不重寫一份
 * 規則；候選池診斷（`CandidatePool`）與分析報告（`AnalysisReport`）
 * 暫時維持在 `ScenarioDetail.tsx` 原本的相對位置渲染（緊接在這個元件
 * 之後），不因為外殼改版而消失——它們何時真正搬進 OG-07 的右欄／底部
 * tab，留給那張票決定。
 */
import { useState } from "react";

import AnalysisReport from "./AnalysisReport";
import CandidatePool from "./CandidatePool";
import Heatmap from "./Heatmap";
import PriceLadder from "./PriceLadder";
import type { AnalysisView, Candidate } from "./api";
import { candidateTitle, strategyLabel } from "./detail";
import { emptyFamilyMessage, resolveFamily } from "./FamilyTabs";
import {
  FAMILY_LABELS, enabledFamilies, familyBaselineTopCandidate, familyOf,
  mergedExpiryTop10, resultsByFamily,
} from "./family";
import { expiryOptions, isThinPool, resolveExpiry } from "./expiry";
import { heatmapProps } from "./heatmap";
import { formatReturn, returnBarWidthPct } from "./scenarios";

/**
 * 排名表的一列（artifact：名次、subtype 標籤、腿位 pill ×1·2·1、劇本
 * 報酬＋inline 比例條、Bid/Ask 過寬 tag、⚑ 單調性警示）。
 *
 * 「腿位 pill」直接重用 `detail.ts::candidateTitle()`——跟手機版
 * `ExpiryStructure.tsx` 的 `<span className="candidate-title">` 是
 * 同一份格式化函式、同一段文字（三腿以上逐腿列出、口數 >1 標
 * 「2×」，T16／#232 既有語意），不是為桌面另外發明一套摘要格式。
 * OG-03（#320）的檔頭已記錄過同一個判斷：詳細頁（不像清單卡片）版面
 * 夠寬，不需要 Butterfly 專屬的緊湊縮寫分支。
 *
 * 整列是一顆按鈕而不是 `<details>`——點擊語意從「展開看這一組的圖」
 * 變成「把中央 Heatmap 換成這一組」，`aria-pressed` 標示目前選取的
 * 是哪一列（單選語意，跟既有 `.chip`／`role="group"` 的 `aria-pressed`
 * 用法一致，不新發明一種可及性模式）。
 */
function DesktopCandidateRow({
  candidate, rank, selected, onSelect,
}: {
  candidate: Candidate;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={selected ? "detail-rank-row selected" : "detail-rank-row"}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span className="rank">#{rank}</span>
        <span className="candidate-subtype">{strategyLabel(candidate.strategy)}</span>
        {/* 兩個徽章與 `title` 文案逐字沿用手機版 `ExpiryStructure.tsx`
            的 `CandidateRow`——同一組資料、同一句解釋，桌面版只是換了
            容器（按鈕而非 `<details><summary>`），語意不變。 */}
        {candidate.wide_spread_warning && (
          <span className="tag warn" title="Bid/Ask 過寬">⚠</span>
        )}
        {candidate.monotonicity_warning && (
          <span className="tag suspect"
                title="報價與鄰近履約價不一致，疑似陳舊報價">
            🚩
          </span>
        )}
        <span className="candidate-title compact-strategy-pill">
          {candidateTitle(candidate)}
        </span>
        <span className="detail-rank-return">
          <span
            className={
              candidate.baseline_return >= 0
                ? "candidate-return positive" : "candidate-return negative"
            }
          >
            {formatReturn(candidate.baseline_return)}
          </span>
          <span className="bar" aria-hidden="true">
            <i className={candidate.baseline_return >= 0 ? "g" : "r"}
               style={{ width: `${returnBarWidthPct(candidate.baseline_return)}%` }} />
          </span>
        </span>
      </button>
    </li>
  );
}

export default function DesktopDetailBody({
  view, strategies, champion,
}: {
  view: AnalysisView;
  strategies: readonly string[];
  /** 跨 family 冠軍（`family.ts::championCandidate`）——只用來算
   *  「目前 family 沒切過時該預設選誰」與「這個 family 一組候選都沒有
   *  時，中央 Heatmap 還能不能顯示點什麼」，不是這個元件自己重新選一
   *  次冠軍。 */
  champion: Candidate | null;
}) {
  const [pickedFamily, setPickedFamily] = useState<string | null>(null);
  const [pickedExpiry, setPickedExpiry] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const families = enabledFamilies(strategies, view);
  // 單一 family 時完全不畫分頁列——跟 `FamilyTabs.tsx` 同一條 AC
  // （沒有選擇可言的地方硬要畫一排只有一顆的按鈕是純噪音），但這裡
  // 排名表／Heatmap 本身仍要顯示，因此只有「families 一個都沒有」
  // （理論上不會發生，`strategies` 必填）才整個不畫。
  if (families.length === 0) return null;

  const championFamily = champion ? familyOf(champion.strategy) : null;
  const currentFamily = resolveFamily(families, pickedFamily, championFamily);
  const grouped = resultsByFamily(view);
  const group = currentFamily !== null ? (grouped.get(currentFamily) ?? []) : [];
  const okResults = group.filter((r) => r.status === "ok");
  const merged = okResults.length > 0 ? mergedExpiryTop10(view, okResults) : null;
  const options = merged ? expiryOptions(view, merged) : [];
  const currentExpiry = resolveExpiry(options, pickedExpiry, view.baseline_expiry);
  const shown = options.find((o) => o.expiry === currentExpiry) ?? null;

  // 中央 Heatmap 跟著目前選取的那一列：選中的 key 若還在目前這份清單
  // 裡就用它；否則（剛切了 family／到期日，或初始狀態根本還沒選過）
  // 退回這份清單的第 1 名；清單本身是空的（這個 family／到期日沒有
  // 任何合格候選）才退回冠軍——保證中央欄永遠有東西可畫，不會因為
  // 使用者正在瀏覽一個空的 family 分頁就跟著開天窗。
  const selectedCandidate =
    shown?.candidates.find((c) => c.candidate_key === selectedKey)
    ?? shown?.candidates[0]
    ?? champion;

  // 切 family／切到期日這兩個動作共用同一個不變量：範圍一變，先前選
  // 的排名列不再保證還在新範圍裡，一律清空、交回上面的預設規則決定
  // （`/code-review` Standards 軸抓到：原本兩個函式各自重複同一段
  // 「設值＋清空 selectedKey」，這裡收成一個工廠函式，不變量只寫一次）。
  function selectingResetsRanking<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setSelectedKey(null);
    };
  }
  const selectFamily = selectingResetsRanking(setPickedFamily);
  const selectExpiry = selectingResetsRanking(setPickedExpiry);

  const diagnosticsResult = okResults[0] ?? null;
  const familyCandidate = merged ? familyBaselineTopCandidate(view, merged) : null;

  return (
    <>
    <div className="detail-shell">
      <div className="detail-col-left">
        {families.length > 1 && (
          <div className="chip-strip" role="group" aria-label="策略家族">
            {families.map((family) => (
              <button
                key={family}
                aria-pressed={family === currentFamily}
                className={family === currentFamily ? "chip selected" : "chip"}
                onClick={() => selectFamily(family)}
              >
                <span className="chip-label">{FAMILY_LABELS[family] ?? family}</span>
              </button>
            ))}
          </div>
        )}

        {currentFamily !== null && group.length === 0 && (
          <section className="card">
            <h2 className="section-title">{FAMILY_LABELS[currentFamily] ?? currentFamily}</h2>
            <p className="caption">
              {view.family_eligibility?.[currentFamily]?.reason
                ?? "這個策略家族目前無法分析。"}
            </p>
          </section>
        )}

        {currentFamily !== null && group.length > 0 && okResults.length === 0 && (
          <section className="card">
            <h2 className="section-title">{FAMILY_LABELS[currentFamily] ?? currentFamily}</h2>
            <p className="caption">{emptyFamilyMessage(group)}</p>
          </section>
        )}

        {currentFamily !== null && okResults.length > 0 && (
          <section className="card">
            <h2 className="section-title">到期日</h2>
            <div className="chip-strip" role="group" aria-label="到期日">
              {options.map((option) => (
                <button
                  key={option.expiry}
                  aria-pressed={option.expiry === currentExpiry}
                  className={option.expiry === currentExpiry ? "chip selected" : "chip"}
                  onClick={() => selectExpiry(option.expiry)}
                >
                  <span className="chip-date">{option.expiry}</span>
                  <span className="chip-return">{formatReturn(option.bestReturn)}</span>
                </button>
              ))}
            </div>

            <div className="notice warn" role="status">
              {shown && isThinPool(shown.count) && (
                <>
                  <span aria-hidden="true">⚠ </span>
                  該期僅 {shown.count} 組候選通過品質過濾，排名參考價值有限。
                </>
              )}
            </div>

            {shown && (
              <ul className="candidate-list detail-rank-list">
                {shown.candidates.map((candidate, i) => (
                  <DesktopCandidateRow
                    key={candidate.candidate_key}
                    candidate={candidate}
                    rank={i + 1}
                    selected={candidate.candidate_key === selectedCandidate?.candidate_key}
                    onSelect={() => setSelectedKey(candidate.candidate_key)}
                  />
                ))}
              </ul>
            )}
          </section>
        )}
      </div>

      <div className="detail-col-center">
        <section className="card heatmap-panel">
          <h2 className="section-title">劇本主圖</h2>
          {selectedCandidate ? (
            <>
              {/* Crossover Boundary（#116）：同 `ScenarioDetail.tsx`／
                  `ExpiryStructure.tsx` 一致的判準，`heatmapProps()`
                  已經把「單腿候選不傳 comparator」收進純函式。 */}
              <Heatmap {...heatmapProps(view, selectedCandidate)} />
              <PriceLadder points={selectedCandidate.price_ladder ?? []} />
            </>
          ) : (
            <p className="caption">無合格候選</p>
          )}
        </section>
      </div>

      {/* OG-07（#325）填：右欄先留空容器，本票不渲染任何內容。 */}
      <div className="detail-col-right" aria-hidden="true" />
    </div>

    {/* 候選池診斷／分析報告：暫時維持在外殼改版前的相對位置（緊接在
        三欄外殼之後），資料來源與 `FamilyTabs.tsx` 完全相同——同一個
        `currentFamily`、同一份 `okResults[0]`、同一個
        `familyBaselineTopCandidate()`。這兩塊的內容與既有 Desktop
        e2e／Vitest 斷言（分析報告 Breakeven／獲利區間等）因此不受
        外殼改版影響；它們何時真正搬進 OG-07（#325）的右欄／底部 tab，
        留給那張票決定，本票只先留一個空的底部 tab 容器佔位。 */}
    {diagnosticsResult && (
      <>
        <CandidatePool view={view} result={diagnosticsResult} />
        <AnalysisReport view={view} result={diagnosticsResult} candidate={familyCandidate} />
      </>
    )}

    {/* OG-07（#325）填：底部 tab 區先留空容器。 */}
    <div className="detail-tabs-placeholder" aria-hidden="true" />
    </>
  );
}
