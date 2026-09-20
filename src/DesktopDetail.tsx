/**
 * 桌面詳細頁三欄外殼（OG-06／#321 起，右欄與底部 tab 由 OG-07／#325
 * 補齊）：artifact 的 Desktop 劇本詳細板：trade page 三欄版面＋底部
 * 走勢／診斷／報告／原始資料四個 tab。
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
 * 規則。
 *
 * OG-07（#325）右欄／底部 tab 的兩個關鍵語意決定：
 *
 * 1. 右欄候選面板（進場／Payoff／Greeks／報告）跟著**排名表目前選取的
 *    那一列**（`selectedCandidate`，跟中央 Heatmap 同一個資料來源）；
 *    底部「淨成本走勢」跟 OG-06 之前一樣固定跟著**冠軍候選**
 *    （`champion`，走 `ScenarioDetail.tsx` 既有 QA1-06「主圖／走勢圖
 *    不隨選取改變」原則），底部「候選池診斷」跟著**目前 family／到期日**
 *    （`diagnosticsResult`，跟 OG-06 之前的相對位置同一份資料），底部
 *    「原始資料」是整份劇本層級的當次快照，不分候選。四個 tab 各自
 *    跟著哪個維度，逐一對齊 artifact 與票面文字，不是全部劃一改成
 *    「跟著選取列」。
 *
 * 2. 「報告」在 artifact 上同時是右欄一個 tab、也是底部一個 tab，但
 *    票面明文「同一份資料，桌面只在底部完整展開一次即可——擇一擺位，
 *    避免同頁重複兩份」；`AnalysisReport` 因此只在底部 tab 完整渲染
 *    一份（且改跟 `selectedCandidate`，不是 OG-06 之前暫時綁的
 *    `familyCandidate`——右欄四個 tab 既然都跟著選取列，底部這份唯一
 *    的完整報告沒有理由講另一個候選的故事），右欄「報告」tab 只放
 *    精簡摘要＋一個跳到底部分頁的連結，不掛第二份 `<AnalysisReport>`。
 *
 * OG-08（#326）第三個判斷：右欄在「這一列選取的候選是單腿（Long
 * Call／Long Put）且角色 ≥ Super User 且 Historical IV 已解鎖」時，
 * 整個換成 `<IvHistory>`（既有元件、既有 class／內容不動，只是掛載
 * 位置搬進這個 grid slot），取代 `<CandidatePanel>`——不是兩者並列
 * （artifact「Desktop TSLA Long Call＋Historical IV」板：右欄 360px
 * 整塊就是 Historical IV，沒有 Entry／Payoff／Greeks／Report 那組
 * tab），也不是額外多開第四欄（右欄仍是同一個 grid slot，`.detail-shell`
 * 的三欄結構不變）。這個決定跟著**選取列**（`selectedCandidate`），
 * 不是跨 family 冠軍（`champion`）——右欄從 OG-07 起本來就是「跟著排名表
 * 目前選取的那一列」這個既有慣例（見上面點 1），使用者切到別的 family／
 * 到期日、選取列換成非單腿候選時，右欄理當跟著換回 `CandidatePanel`，
 * 不能讓右欄卡在一個跟中央 Heatmap／左欄排名表已經不同步的候選上；跟
 * 底部「淨成本走勢」固定跟著冠軍（QA1-06 頭條原則）是不同的既有慣例，
 * 這裡刻意選右欄自己的既有慣例，不是套錯規則。票面「單腿冠軍」四字是
 * 描述這張票服務的典型情境（單一 family 劇本的冠軍恆等於排名表唯一
 * 候選，兩者天然重合），不是要求改成冠軍鎖定——多 family 劇本才會讓
 * 這兩個既有維度出現差異，此時沿用右欄自己的既有選取慣例才是內部
 * 一致的答案。
 *
 * 是否顯示 `<IvHistory>` 由 `IvHistory.tsx` export 的
 * `useIvHistoryAccess()`／`supportsIvHistory()` 決定——跟 `<IvHistory>`
 * 元件自己內部用的是同一套函式，不是另外重新推一次規則；`enabled`／
 * `roleReady` 兩個閘門變數在這裡仍各自獨立比對（AUTH-04／AUTH-06 既有
 * 裁示：不合併成共用判斷式），只是恰好都要通過才決定「畫哪一種右欄」。
 */
import { useState } from "react";

import AnalysisReport, {
  PositionSensitivity, QRow, RateRow, Row, RiskPayoff,
} from "./AnalysisReport";
import CandidatePool from "./CandidatePool";
import DesktopSpreadHistory from "./DesktopSpreadHistory";
import Heatmap from "./Heatmap";
import IvHistory, {
  isSuperUserRole, supportsIvHistory, useIvHistoryAccess,
} from "./IvHistory";
import PriceLadder from "./PriceLadder";
import RawData from "./RawData";
import {
  legQuantityPrefix, legSide, rawDataCsvUrl, type AnalysisView, type Candidate,
} from "./api";
import { candidateTitle, strategyLabel } from "./detail";
import { emptyFamilyMessage, resolveFamily } from "./FamilyTabs";
import {
  FAMILY_LABELS, enabledFamilies, familyOf, mergedExpiryTop10, resultsByFamily,
} from "./family";
import { expiryOptions, isThinPool, resolveExpiry } from "./expiry";
import { heatmapProps } from "./heatmap";
import { formatReturn, money, returnBarWidthPct } from "./scenarios";

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
 * 整列是一顆按鈕而不是 `<details>`，點擊語意從「展開看這一組的圖」
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

type RightTab = "entry" | "payoff" | "greeks" | "report";

const RIGHT_TABS: { key: RightTab; label: string }[] = [
  { key: "entry", label: "進場" },
  { key: "payoff", label: "Payoff" },
  { key: "greeks", label: "Greeks" },
  { key: "report", label: "報告" },
];

/**
 * 進場 tab（artifact：最差成交口徑表——逐腿 Bid／Ask／IV，最差成交會
 * 用到的那一邊字重加粗；淨成本／資本或最大損失；Bid/Ask 過寬與單調性
 * 警示）。逐腿方向與口數標示重用 `legSide()`／`legQuantityPrefix()`
 * （`./api`），跟排名列的 `candidateTitle()`、`AnalysisReport.tsx` 的
 * `ExecutionSection` 同一套規則，不是第三份格式。
 */
function EntryTab({ candidate }: { candidate: Candidate }) {
  return (
    <div className="candidate-panel-section">
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
      <h3 className="h3">最差成交口徑（買 Ask · 賣 Bid）</h3>
      <table className="tbl entry-leg-table">
        <thead>
          <tr>
            <th scope="col">腿</th>
            <th scope="col" className="r">Bid</th>
            <th scope="col" className="r">Ask</th>
            <th scope="col" className="r">IV</th>
          </tr>
        </thead>
        <tbody>
          {candidate.legs.map((leg, i) => (
            <tr key={i}>
              <td>{legSide(leg)} {legQuantityPrefix(leg)}{leg.strike}</td>
              <td className={leg.side === "sell" ? "r num entry-leg-worst" : "r num"}>
                {money(leg.bid)}
              </td>
              <td className={leg.side === "buy" ? "r num entry-leg-worst" : "r num"}>
                {money(leg.ask)}
              </td>
              <td className="r num">
                {leg.iv === null ? "—" : `${(leg.iv * 100).toFixed(0)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Row label="淨成本 / 股">{money(candidate.natural_cost)}</Row>
      {/* 資本／最大損失獨立一列、不是「淨成本」的別名：既有四策略兩者
          恆相等，Butterfly（broken-wing）可能不相等——`RiskPayoff` 的
          Max Loss 同一套讀法（`max_loss_per_contract`，每口＝÷100）。 */}
      <Row label="資本／最大損失（每口）">{money(candidate.max_loss_per_contract / 100)}</Row>
    </div>
  );
}

/**
 * 完成度門檻／獲利區間互斥呈現（artifact；票面「完成度門檻（單調
 * family）／獲利區間（Butterfly）互斥呈現」）。判準用 `familyOf()`，
 * 不是 `profit_region !== null`——Butterfly 峰值連成本都賺不回來時
 * `profit_region` 本身也是 `null`（`service.py` 既有語意：這不代表
 * 它變成單調家族），這裡要問的是「這組候選屬於哪個 family」，不是
 * 「這個欄位這次剛好有沒有值」。獲利區間本身已經在 `RiskPayoff`
 * （沿用 `AnalysisReport.tsx::BreakevenRow`）渲染過，這裡只補單調
 * family 專屬的完成度門檻——兩者不會同時出現。
 *
 * 文案逐字對齊既有 CLI `report.py::_resilience_lines()` 的既有三態
 * （`k is None`／`k <= 0`／其餘），不是另外發明一套說法；CLI 版多印的
 * 「錨點日保本價 $X」在 `Candidate` 契約裡沒有對應欄位可讀，這裡誠實
 * 省略，不憑空編一個數字。
 */
function CompletionThresholdRow({ candidate }: { candidate: Candidate }) {
  if (familyOf(candidate.strategy) === "butterfly") return null;
  const k = candidate.completion_threshold;
  return (
    <Row label="完成度門檻">
      {k === null
        ? <span className="down">— ⚠ 劇本全成仍不保本</span>
        : k <= 0
        ? "0%（已保本）"
        : `完成 ${(k * 100).toFixed(0)}%（保本）`}
    </Row>
  );
}

function PayoffTab({ candidate }: { candidate: Candidate }) {
  return (
    <div className="candidate-panel-section">
      <h3 className="h3">Payoff（到期）</h3>
      <RiskPayoff candidate={candidate} />
      <CompletionThresholdRow candidate={candidate} />
      <Row label="距到期">{candidate.days_to_expiry} 天</Row>
    </div>
  );
}

function GreeksTab({ candidate, view }: { candidate: Candidate; view: AnalysisView }) {
  return (
    <div className="candidate-panel-section">
      <h3 className="h3">Greeks（比率）</h3>
      <PositionSensitivity candidate={candidate} />
      <RateRow candidate={candidate} params={view.params} />
      <QRow params={view.params} />
    </div>
  );
}

/**
 * 報告 tab：只放精簡摘要＋一個切到底部「分析報告」分頁的連結，不掛
 * 第二份 `<AnalysisReport>`（見檔頭「報告只完整渲染一份」的裁示）。
 *
 * `/code-review` Spec 軸抓到：這裡原本只有註解說「免責聲明沿用
 * `result.disclaimer_text`」，實際上沒有把它傳進來、畫面上也真的沒有
 * ——票面「報告」bullet 明文「免責聲明獨立不折疊」是這個 tab 的一部分
 * 要求，不是只有底部那份才要顯示。免責聲明本身只是一段合規文字（讀
 * `result.disclaimer_text` 這個既有欄位兩次，不是把整個 `<AnalysisReport>`
 * 元件掛兩次），跟「分析報告只完整渲染一份」的裁示不衝突。
 */
function ReportTab({
  disclaimerText, onJumpToFullReport,
}: {
  disclaimerText: string;
  onJumpToFullReport: () => void;
}) {
  return (
    <div className="candidate-panel-section">
      <p className="caption">
        完整的 Risk / Payoff、Position Sensitivity、Execution 與 Model &amp;
        Assumptions 明細，收在底部「分析報告」分頁——同一份資料只在那裡
        完整展開一次。
      </p>
      <button type="button" className="text-button" onClick={onJumpToFullReport}>
        查看完整分析報告 ↓
      </button>
      {disclaimerText && (
        <p className="caption report-disclaimer">{disclaimerText}</p>
      )}
    </div>
  );
}

/** 右欄「候選面板」：跟著左欄排名表目前選取的那一列。
 *
 * CSV 下載連結（票面「報告」bullet 明文、artifact 畫成不分頁一律
 * 常駐的頁尾按鈕）獨立於四個 tab 切換之外——不是「報告」tab 專屬內容，
 * 沿用既有 `rawDataCsvUrl()`（`RawData.tsx` 同一個 helper，同一套
 * `analyzedAt` 快取破壞參數），不是另外發明一條下載路徑。 */
function CandidatePanel({
  candidate, view, scenarioId, analyzedAt, disclaimerText, onJumpToFullReport,
}: {
  candidate: Candidate | null;
  view: AnalysisView;
  scenarioId: string;
  analyzedAt: string | null;
  /** 底部「分析報告」tab 那份 `StrategyResult.disclaimer_text`——「報告」
   *  tab 的精簡摘要仍要顯示這句合規文字，不是只有完整版才有。 */
  disclaimerText: string;
  onJumpToFullReport: () => void;
}) {
  const [tab, setTab] = useState<RightTab>("entry");
  return (
    <div className="detail-col-right panel">
      <div className="panel-h">
        {/* 沿用 OG-11（#322）`Settings.tsx` 桌面 subnav 已經立下的既有
            慣例——`role="tab"`／`.chip`／`.chip selected`，不是另外
            發明一套 tab 樣式（本檔案裡另一組 `.tabs`／`.tabs a` CSS
            規則是 OG-03 換皮時從 artifact 原樣抄進來、目前沒有任何
            TSX 元件真的在用的死規則，不該再多一個真正的消費端延續它）。 */}
        <nav className="chip-strip" role="tablist" aria-label="候選面板">
          {RIGHT_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={tab === t.key ? "chip selected" : "chip"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="candidate-panel-body">
        {candidate === null ? (
          <p className="caption">無合格候選</p>
        ) : (
          <>
            {tab === "entry" && <EntryTab candidate={candidate} />}
            {tab === "payoff" && <PayoffTab candidate={candidate} />}
            {tab === "greeks" && <GreeksTab candidate={candidate} view={view} />}
            {tab === "report" && (
              <ReportTab disclaimerText={disclaimerText}
                        onJumpToFullReport={onJumpToFullReport} />
            )}
            <a className="button raw-data-download"
              href={rawDataCsvUrl(scenarioId, analyzedAt)} download>
              下載原始資料 CSV
            </a>
          </>
        )}
      </div>
    </div>
  );
}

type BottomTab = "history" | "pool" | "report" | "raw";

const BOTTOM_TABS: { key: BottomTab; label: string }[] = [
  { key: "history", label: "淨成本走勢" },
  { key: "pool", label: "候選池診斷" },
  { key: "report", label: "分析報告" },
  { key: "raw", label: "原始資料" },
];

export default function DesktopDetailBody({
  view, strategies, champion, scenarioId, analyzedAt,
}: {
  view: AnalysisView;
  strategies: readonly string[];
  /** 跨 family 冠軍（`family.ts::championCandidate`）——只用來算
   *  「目前 family 沒切過時該預設選誰」、「這個 family 一組候選都沒有
   *  時，中央 Heatmap 還能不能顯示點什麼」，以及底部「淨成本走勢」
   *  固定跟著哪一組（QA1-06），不是這個元件自己重新選一次冠軍。 */
  champion: Candidate | null;
  /** OG-07（#325）：底部「淨成本走勢」／「原始資料」需要，取代
   *  `ScenarioDetail.tsx` 先前直接全域掛載這兩個元件的位置。 */
  scenarioId: string;
  analyzedAt: string | null;
}) {
  const [pickedFamily, setPickedFamily] = useState<string | null>(null);
  const [pickedExpiry, setPickedExpiry] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<BottomTab>("history");
  // OG-08（#326）：Hooks 規則——這支 hook 必須排在下面
  // `families.length === 0` 提前 return 之前呼叫，跟其餘 `useState` 放
  // 在一起，即使目前這個分支理論上不會真的觸發那個提前 return。判斷式
  // 本身（`showIvPanel`）留在下面 `selectedCandidate` 算完之後才組出來。
  const { enabled: ivEnabled, role: ivRole } = useIvHistoryAccess();

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

  // 中央 Heatmap／右欄候選面板跟著目前選取的那一列：選中的 key 若還在
  // 目前這份清單裡就用它；否則（剛切了 family／到期日，或初始狀態根本
  // 還沒選過）退回這份清單的第 1 名；清單本身是空的（這個 family／
  // 到期日沒有任何合格候選）才退回冠軍——保證中央欄與右欄永遠有東西
  // 可畫，不會因為使用者正在瀏覽一個空的 family 分頁就跟著開天窗。
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

  // OG-08（#326）：右欄「這次要畫哪一種面板」——見檔頭第三個判斷的完整
  // 理由。`enabled`／`roleReady` 兩道閘門刻意各自保留成獨立變數才做
  // `&&`，不是先合併成一個共用旗標（AUTH-04／AUTH-06 既有裁示）；跟
  // `<IvHistory>` 元件自己內部用的是同一份 `useIvHistoryAccess()`／
  // `supportsIvHistory()`，不是重新推一次規則。
  const ivRoleReady = isSuperUserRole(ivRole);
  const showIvPanel =
    ivEnabled === true && ivRoleReady && supportsIvHistory(selectedCandidate);

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

      {/* OG-07（#325）：右欄「候選面板」，跟著上面排名表的選取列。
          OG-08（#326）：選取列是單腿候選且角色 ≥ Super User 且 Historical
          IV 已解鎖時，整個換成 `<IvHistory>`（見檔頭第三個判斷）——同一個
          grid slot 只會有其中一個，不會兩者疊加。`<IvHistory>` 自己內部
          仍有一套完全相同的閘門（`enabled`／`roleReady`／
          `supportsIvHistory`），這裡的 `showIvPanel` 只決定「這個 slot
          要不要嘗試掛載它」，真正的顯示／隱藏語意仍由元件自己負責，跟
          `CandidatePanel` 分支互斥、不重複判斷同一件事兩次的方式不同：
          這裡是「選哪個元件掛」，`<IvHistory>` 内部是「掛了以後要不要
          畫東西」。 */}
      {showIvPanel ? (
        <div className="detail-col-right">
          <IvHistory
            scenarioId={scenarioId}
            candidate={selectedCandidate}
            analyzedAt={analyzedAt}
          />
        </div>
      ) : (
        <CandidatePanel
          candidate={selectedCandidate}
          view={view}
          scenarioId={scenarioId}
          analyzedAt={analyzedAt}
          disclaimerText={diagnosticsResult?.disclaimer_text ?? ""}
          onJumpToFullReport={() => setBottomTab("report")}
        />
      )}
    </div>

    {/* OG-07（#325）：底部四個 tab——淨成本走勢（跟著冠軍，QA1-06）／
        候選池診斷（跟著目前 family／到期日，OG-06 之前的相對位置同一份
        資料）／分析報告（跟著選取列，唯一一份完整渲染）／原始資料
        （劇本層級當次快照，不分候選）。 */}
    <section className="panel detail-bottom-tabs">
      <div className="panel-h">
        <nav className="chip-strip" role="tablist" aria-label="劇本詳細底部資訊">
          {BOTTOM_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={bottomTab === t.key}
              className={bottomTab === t.key ? "chip selected" : "chip"}
              onClick={() => setBottomTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      {/* 四個分頁全部常駐掛載，用 `hidden` 切換可見度，不是切一次卸載
          重掛一次——`DesktopSpreadHistory` 掛載就抓資料（artifact：
          預設分頁就看得到圖，不是要使用者再展開一次），若改成條件式
          卸載重掛，使用者每切一次分頁就會重新打一次 API，白白浪費流量
          也違背「切換零網路請求」的既有精神（AC 原文只講右欄，但同一個
          原則沒有理由不適用底部）。`RawData` 自己內層仍是使用者要點開
          才抓（它自己的 `<details onToggle>` 不受這裡影響），常駐掛載
          不會讓它變得更早發送請求。 */}
      <div className="detail-bottom-tab-body">
        <div hidden={bottomTab !== "history"}>
          <DesktopSpreadHistory scenarioId={scenarioId} candidate={champion}
                                analyzedAt={analyzedAt} />
        </div>
        <div hidden={bottomTab !== "pool"}>
          <CandidatePool view={view} result={diagnosticsResult} />
        </div>
        {diagnosticsResult && (
          <div hidden={bottomTab !== "report"}>
            <AnalysisReport view={view} result={diagnosticsResult} candidate={selectedCandidate} />
          </div>
        )}
        {/* #69：`key` 綁定這次分析的身分——新分析一到，React 直接卸載
            重掛，內部 state（已抓到的資料、`<details open>`）連同歸零，
            跟 `ScenarioDetail.tsx` 先前對這個元件的既有保證一致，只是
            掛載位置搬進了這個 tab。 */}
        <div hidden={bottomTab !== "raw"}>
          <RawData key={`raw-data-${analyzedAt ?? "none"}`}
                   scenarioId={scenarioId} analyzedAt={analyzedAt} />
        </div>
      </div>
    </section>
    </>
  );
}
