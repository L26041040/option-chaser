/**
 * 分析報告新版型（V8／#56）：對齊
 * `docs/research/option-strategy-report-conventions.md`（R1／#49）建議的
 * 章節骨架與呈現方式——結論先行、方法論墊底，關鍵指標走表格。整塊是
 * 詳細頁的「進階區」，預設收合（票上「詳細頁進階區兩個區塊」）。
 *
 * 章節骨架（依 R1 §4.1，實際合併／精簡如下）：
 *   ①＋② 交易摘要   一句話結論句（含策略名）＋ 關鍵指標（成本／損益
 *                   兩平／最大獲利／最大損失）
 *   ③ 情境分析      韌性 7 情境表 ＋ 劇本完成度曲線
 *   ④ 風險與代價    情境最壞＋劇本報酬並排、保本門檻、不漲保留率、
 *                   Bid-Ask Spread、代價與警示 ＋「部位敏感度」小區
 *   ⑤ 進場執行      逐腿報價、買價指引 L2/L3
 *   ⑥ 方法與假設    折疊，`methodology_text` 原樣顯示
 *   ⑦ 免責聲明      不折疊，`disclaimer_text`
 *
 * 與 R1 §4.1 骨架的刻意差異——凡是頁面上方已經無條件顯示過的數字，這裡
 * 都不再重複一次（分析報告是使用者主動展開才看得到的進階區塊，原樣
 * 再印一次只是噪音，不是 R1 說的「結論先行」）：
 * - 原②「目標月/目標價/距現價/追平價格 S*」併入一句話結論，不獨立成
 *   段——`Summary`／`Catchup` 兩個既有元件已經顯示同一組數字。
 * - 「策略」本身不獨立成一列——既有 `Summary` 元件已經有一列「策略」，
 *   一句話結論裡也含策略名（`reportConclusion`），不必再列第三次。
 * - ③ 刻意不重畫 P/L 矩陣／Heatmap——劇本主圖（`Chart`）已經在頁面上方
 *   畫過同一組候選的 Heatmap，R1 §3.4「同一份報告不重複畫同一件事」。
 *
 * 零金融計算：每個數字都是引擎已經算好的欄位（`Candidate`／
 * `StrategyResult` 既有或本票新增的欄位），這裡只做重排＋除法／百分比
 * 等呈現層算術（R1 §4.2 B）。
 */
import type { AnalysisView, Candidate, StrategyResult } from "./api";
import { breakevenDistancePct, completionThresholdText, costPctOfSpot,
        formatMove, maxPayoutRatioText, reportConclusion, SCENARIO_NAMES,
        } from "./detail";
import { formatReturn, money } from "./scenarios";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="row">
      <span className="row-label">{label}</span>
      <span className="row-value">{children}</span>
    </div>
  );
}

/**
 * ①＋② 交易摘要／劇本與論據合併：一句話結論 ＋ 三件套（成本／損益兩平／
 * 最大獲利）＋最大損失 ＋ 策略。R1 §1 第 3 點：最大獲利與最大損失必須
 * 同框，不可拆散。
 *
 * R1 §4.1 原骨架把「目標月/目標價/距現價」「追平價格 S*」也放進②，
 * 這裡刻意不重複——本頁摘要區（`Summary`）與追平價格區（`Catchup`）
 * 已經在頁面上方無條件顯示同一組數字，分析報告是使用者主動展開才看得
 * 到的進階區塊，再說一次同一件事只是噪音，不是「結論先行」。
 */
function Summary({ candidate, strategy, spot }: {
  candidate: Candidate; strategy: string; spot: number;
}) {
  return (
    <>
      <p className="report-conclusion">{reportConclusion(candidate, strategy)}</p>
      <Row label="成本">
        {money(candidate.natural_cost)}
        <span className="row-note">
          （佔現價 {formatReturn(costPctOfSpot(candidate, spot))}）
        </span>
      </Row>
      <Row label="損益兩平">
        {money(candidate.breakeven)}
        <span className="row-note">
          （{formatMove(breakevenDistancePct(candidate, spot))} 現價）
        </span>
      </Row>
      <Row label="最大獲利">
        {candidate.max_profit === null ? "無上限" : money(candidate.max_profit)}
        <span className="row-note">（{maxPayoutRatioText(candidate)}）</span>
      </Row>
      {/* debit 策略（本站四種皆是）最大損失恆等於進場成本，見
          `store.py` 的 `max_loss_per_contract` 註解——不是巧合，是定義。 */}
      <Row label="最大損失">
        {money(candidate.natural_cost)}
        <span className="row-note">（＝進場成本）</span>
      </Row>
    </>
  );
}

/** ③ 情境分析：韌性 7 情境表 ＋ 劇本完成度曲線。 */
function Scenarios({ candidate }: { candidate: Candidate }) {
  const { entries, worst_code } = candidate.scenario_vector;
  return (
    <>
      <table className="report-table">
        <caption className="sr-only">韌性向量：7 個固定壓力情境（Mid 口徑）</caption>
        <thead>
          <tr><th scope="col">情境</th><th scope="col">報酬率</th></tr>
        </thead>
        <tbody>
          {entries.map(([code, ret]) => (
            <tr key={code} className={code === worst_code ? "worst" : undefined}>
              <th scope="row">
                {code} {SCENARIO_NAMES[code] ?? code}
                {code === worst_code && <span className="row-note"> ◀ 情境最壞</span>}
              </th>
              <td className={ret >= 0 ? "positive" : "negative"}>{formatReturn(ret)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption">
        劇本完成度:{" "}
        {candidate.completion_curve
          .map(([k, ret]) => `${(k * 100).toFixed(0)}%→${formatReturn(ret)}`)
          .join(" | ")}
      </p>
    </>
  );
}

/** ④ 風險與代價：情境最壞＋劇本報酬並排（R1 §2.5 平衡原則：報酬數字
 *  不得單獨出現）、保本門檻、不漲保留率、Bid-Ask Spread、代價與警示，
 *  ＋「部位敏感度」小區。 */
function Risk({ candidate }: { candidate: Candidate }) {
  return (
    <>
      <Row label="劇本報酬（情境最壞並排）">
        <span className={candidate.baseline_return >= 0 ? "positive" : "negative"}>
          {formatReturn(candidate.baseline_return)}
        </span>
        <span className="row-note">
          （情境最壞 {formatReturn(candidate.scenario_vector.worst_return)}）
        </span>
      </Row>
      <Row label="保本門檻">
        {completionThresholdText(candidate.completion_threshold)}
      </Row>
      <Row label="不漲保留率">{formatReturn(candidate.retention)}</Row>
      <Row label="Bid-Ask Spread">
        {formatReturn(candidate.friction)}
        <span className="row-note">（{money(candidate.friction_amount)}/股）</span>
      </Row>
      {(candidate.cons.length > 0 || candidate.guidance_warnings.length > 0) && (
        <div className="report-warnings">
          {candidate.cons.map((c) => <p className="notice warn" key={c}>{c}</p>)}
          {candidate.guidance_warnings.map((w) => (
            <p className="notice warn" key={w}>{w}</p>
          ))}
        </div>
      )}
      <h3 className="section-title report-subsection">部位敏感度</h3>
      <Row label="淨 Delta">{candidate.net_delta.toFixed(2)}</Row>
      <Row label="Theta（佔成本比率，Mid 口徑）">
        {formatReturn(candidate.theta_day_rate)} / 天
      </Row>
      <Row label="Vega（佔成本比率，Mid 口徑）">
        {formatReturn(candidate.vega_per_pt)} / 1% IV
      </Row>
      <Row label="Lambda 有效槓桿">{candidate.effective_leverage.toFixed(1)}x</Row>
    </>
  );
}

/** ⑤ 進場執行：逐腿報價 ＋ 買價指引 L2/L3。 */
function Execution({ candidate }: { candidate: Candidate }) {
  const [buy, sell] = candidate.legs;
  return (
    <>
      {buy && (
        <Row label="買腿">
          Strike {buy.strike} Ask {money(buy.ask)}
          <span className="row-note">
            {" "}IV {buy.iv === null ? "—" : `${(buy.iv * 100).toFixed(0)}%`}
          </span>
        </Row>
      )}
      {sell && (
        <Row label="賣腿">
          Strike {sell.strike} Bid {money(sell.bid)}
          <span className="row-note">
            {" "}IV {sell.iv === null ? "—" : `${(sell.iv * 100).toFixed(0)}%`}
          </span>
        </Row>
      )}
      <Row label="L2 保守上限（最保守 IV 情境）">{money(candidate.l2)}</Row>
      <Row label={`L3 要求報酬上限`}>{money(candidate.l3)}</Row>
    </>
  );
}

/** ⑥ 方法與假設：折疊，過濾／配對統計壓成一行 ＋ `methodology_text` 原樣。 */
function Methodology({ result }: { result: StrategyResult }) {
  const fr = result.filter_report;
  const pr = result.pair_report;
  return (
    <details className="report-methodology">
      <summary>方法與假設</summary>
      {fr && (
        <p className="caption">
          掃描 {fr.total} 張 → 合格 {fr.passed} 張
          {pr && ` → 配對 ${pr.total_pairs} 組 → 有效 ${pr.passed} 組`}
        </p>
      )}
      <pre className="report-methodology-text">{result.methodology_text}</pre>
    </details>
  );
}

export default function AnalysisReport({ view, result, candidate }: {
  view: AnalysisView;
  result: StrategyResult;
  candidate: Candidate | null;
}) {
  if (!candidate) return null;   // 無合格候選——跟主圖同樣的邊界（附錄A10.2）
  const spot = view.meta.spot;

  return (
    // 進階區（票上「詳細頁進階區兩個區塊」，QA1-12 舊 Streamlit 版的
    // 既有慣例）：預設收合，展開才看得到——內容比頁面其他區塊長得多，
    // 攤開常駐會把到期日結構與候選池診斷推到很下面。
    <details className="card">
      <summary className="section-title">📄 分析報告</summary>
      <Summary candidate={candidate} strategy={result.strategy} spot={spot} />
      <h3 className="section-title report-subsection">情境分析</h3>
      <Scenarios candidate={candidate} />
      <h3 className="section-title report-subsection">風險與代價</h3>
      <Risk candidate={candidate} />
      <h3 className="section-title report-subsection">進場執行</h3>
      <Execution candidate={candidate} />
      <Methodology result={result} />
      {/* ⑦ 免責聲明：獨立、不折疊（R1 §4.4.4）——不折疊指的是相對於
          ⑥ 方法論的獨立小節，不是整個進階區塊。 */}
      <p className="caption report-disclaimer">{result.disclaimer_text}</p>
    </details>
  );
}
