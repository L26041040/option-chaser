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
 *   ⑤ 進場執行      逐腿雙邊報價（Bid/Ask/IV）、剩餘天數、買價指引 L2/L3
 *   ⑥ 方法與假設    折疊，模型參數（利率／IV情境／Delta門檻／要求報酬）
 *                   ＋ 過濾配對統計一行 ＋ `methodology_text` 原樣顯示
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
import type { AnalysisView, Candidate, Leg, StrategyResult } from "./api";
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
 * 無風險利率列（RC1／#87）：三態分流，不再不分青紅皂白顯示
 * `formatReturn(params.rate)` 加一句 `rate_note` 附註——那樣會在真的
 * 用了期限對齊曲線時，把常數 `rate`（此時其實沒被用在估值上）跟曲線
 * 資料日混在一起，看起來像「這個常數就是那個日期的曲線值」。
 *
 * - `rate_curve_used` 為真：顯示期限對齊曲線與其 `rate_curve_date`；
 *   `rate_curve_stale` 為真時額外標示 STALE，不得跟新鮮曲線同一種
 *   呈現方式。
 * - `rate_curve_used` 為假、`rate_explicit` 為真：使用者透過 CLI
 *   `--rate` 主動指定的利率——維持乾淨顯示，不貼 FALLBACK 標籤（那是
 *   使用者主動選擇，不是「本該有曲線卻失敗」）。跟後端
 *   `report.py::_rate_line` 同一套三態判斷，目前網頁路徑不可達
 *   （`rate_explicit` 只有 CLI 會設起），但兩邊邏輯要對得上，不能只在
 *   後端正確、前端漏了這一態。
 * - 其餘情況：真正的 fallback，只顯示常數＋明確的 FALLBACK 標籤與
 *   原因，**不掛任何市場資料日期**。
 */
function RateRow({ params }: { params: AnalysisView["params"] }) {
  if (params.rate_curve_used) {
    return (
      <Row label="無風險利率">
        期限對齊 Treasury 曲線 · {params.rate_curve_date}
        {params.rate_curve_stale && (
          <span className="row-note"> · STALE（沿用陳舊備援窗）</span>
        )}
      </Row>
    );
  }
  if (params.rate_explicit) {
    return <Row label="無風險利率">{formatReturn(params.rate)}</Row>;
  }
  return (
    <Row label="無風險利率">
      {formatReturn(params.rate)}
      <span className="row-note">
        {" "}· FALLBACK／Treasury curve unavailable
        {params.rate_note && `（${params.rate_note}）`}
      </span>
    </Row>
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
      {/* 代價（cons）跟買價指引警示（guidance_warnings）是兩種不同的
          關注點——CLI 純文字報告本來就分別標成「- 代價:」與「- 警示:」
          兩種前綴（`report.py` 的 `評語`／`買價指引` 兩段），這裡沿用
          同一個區分，不要攤成一堆看不出差別的警示列表。 */}
      {candidate.cons.length > 0 && (
        <div className="report-warnings">
          {candidate.cons.map((c) => (
            <p className="notice warn" key={c}>代價: {c}</p>
          ))}
        </div>
      )}
      {candidate.guidance_warnings.length > 0 && (
        <div className="report-warnings">
          {candidate.guidance_warnings.map((w) => (
            <p className="notice warn" key={w}>警示: {w}</p>
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

/** 一隻腿的 Bid／Ask／IV——R1 §4.2 A：逐腿報價要兩邊都給，不是只給
 *  「這隻腿最差成交會用到的那一邊」。單腿候選只有買腿，沒有最差成交
 *  以外的報價可比較，但價差兩腿都該看得到完整雙邊報價，才看得出買賣
 *  價差寬不寬——只印一邊等於把價差資訊藏起來。 */
function LegRow({ label, leg }: { label: string; leg: Leg }) {
  return (
    <Row label={label}>
      Strike {leg.strike} Bid {money(leg.bid)} / Ask {money(leg.ask)}
      <span className="row-note">
        {" "}IV {leg.iv === null ? "—" : `${(leg.iv * 100).toFixed(0)}%`}
      </span>
    </Row>
  );
}

/** ⑤ 進場執行：逐腿報價（雙邊）＋ 剩餘天數 ＋ 買價指引 L2/L3。 */
function Execution({ candidate }: { candidate: Candidate }) {
  const [buy, sell] = candidate.legs;
  return (
    <>
      {buy && <LegRow label="買腿" leg={buy} />}
      {sell && <LegRow label="賣腿" leg={sell} />}
      {/* R1 §4.2 B「剩餘天數」：早就序列化了，純文字報告沒印。 */}
      <Row label="剩餘天數（距到期）">{candidate.days_to_expiry} 天</Row>
      <Row label="L2 保守上限（最保守 IV 情境）">{money(candidate.l2)}</Row>
      <Row label={`L3 要求報酬上限`}>{money(candidate.l3)}</Row>
    </>
  );
}

/**
 * ⑥ 方法與假設：折疊，模型參數（R1 §4.2 A 的「[模型假設]」重排項——
 * 利率、IV 情境、Delta 門檻、要求報酬上限）＋ 過濾／配對統計壓成一行
 * ＋ `methodology_text` 原樣（估值公式等方法論散文，`report.py` 的
 * `[尾註]`）。
 */
function Methodology({ result, params }: {
  result: StrategyResult; params: AnalysisView["params"];
}) {
  const fr = result.filter_report;
  const pr = result.pair_report;
  return (
    <details className="report-methodology">
      <summary>方法與假設</summary>
      <RateRow params={params} />
      <Row label="IV 情境">
        {params.iv_shifts.map((s) => (s === 0 ? "不變" : `${s > 0 ? "+" : ""}${(s * 100).toFixed(0)}%`)).join(" / ")}
      </Row>
      <Row label="Delta 分級門檻">
        {params.delta_bands[0]} / {params.delta_bands[1]}
      </Row>
      <Row label="最低要求報酬率">{formatReturn(params.min_return)}</Row>
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
      <Methodology result={result} params={view.params} />
      {/* ⑦ 免責聲明：獨立、不折疊（R1 §4.4.4）——不折疊指的是相對於
          ⑥ 方法論的獨立小節，不是整個進階區塊。 */}
      <p className="caption report-disclaimer">{result.disclaimer_text}</p>
    </details>
  );
}
