/**
 * 分析報告（MVP V3／#105，spec #102 決策 G）：瘦身為四區塊——
 * Risk / Payoff → Position Sensitivity → Execution → Model & Assumptions
 * （預設收合）。整塊是詳細頁的「進階區」，本身也預設收合（沿用既有
 * QA1-12 慣例）。
 *
 * 四區塊固定內容（票上逐欄列明，不是舉例）：
 *   Risk / Payoff         Breakeven／Max Profit／Max Loss／
 *                         Execution Friction（實際數字）
 *   Position Sensitivity  Net Delta／Theta per day／Vega per 1 vol point／
 *                         Effective Leverage
 *   Execution             Buy Leg／Sell Leg 雙邊報價／Net Mid／
 *                         Net Worst（保守進場成本）／Volume・OI（低權重）
 *   Model & Assumptions   折疊：無風險利率四項（Rate used／Tenor／
 *                         Source／Curve date，MVP V3／#112）／股利殖利率
 *                         q 三項（q used／Dividend source／Data as of，
 *                         #123）／IV 情境／Delta 分級門檻／最低要求報酬率
 *
 * 依決策 G 明文從 Report UI 移除、不再渲染：baseline return、7 情境
 * 韌性表、劇本完成度曲線、filter／pair 統計（CandidatePool 已負責）、
 * 一句話結論與策略名（頁面上方「基準候選」已顯示，見 #103）、代價
 * （cons）／買價指引警示（guidance_warnings）、保本門檻、不漲保留率、
 * 剩餘天數、L2/L3 買價指引、`methodology_text` 大段散文。這不是刪除
 * 底層計算——欄位、CLI report.py 輸出、契約樣本原封不動，純屬本頁
 * UI 呈現層 cleanup（票上原文）。
 *
 * 免責聲明（`disclaimer_text`）維持獨立、不折疊：它是合規文字，不是
 * 四個資料區塊之一，不在「只保留四區塊」的裁減範圍內。
 *
 * 零金融計算：每個數字都是引擎已經算好的既有欄位，這裡只做重排與
 * 格式化，不重算任何一個數字。
 */
import type { AnalysisView, Candidate, Leg, StrategyResult } from "./api";
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
 * 無風險利率四項（MVP V3／#112，spec #102 決策 H）：Rate used／Tenor／
 * Source／Curve date——取代舊版只顯示「用了某條曲線」卻不給實際數值
 * 的模糊呈現。三態沿用既有語意（`rate_curve_used`／`rate_explicit`／
 * `rate_curve_stale`），不新造狀態機：
 *
 * - Rate used：一律讀 `candidate.rate_used`（後端 `leg_rate(p, expiry)`
 *   查表結果），不是 `params.rate` 這個可能沒被用在估值上的常數——曲線
 *   命中時，不同到期日的候選本來就該顯示不同數值。fallback 狀態下
 *   `leg_rate` 本身會落回 `params.rate`，因此三態下這裡讀到的數字
 *   自然一致，不必分支判斷。
 * - Tenor：`candidate.rate_tenor_years`，與 Rate used 同一次查表算出來
 *   的年期，前端只格式化成「X.XX 年」。
 * - Source／Curve date：純粹依既有三態旗標判斷是哪一種來源，不是
 *   新的財務計算——曲線命中显示 US Treasury＋曲線資料日（陳舊時附
 *   STALE）；明示利率显示「CLI 明示」、Curve date 留白；其餘 fallback
 *   显示常數來源與原因，同樣不掛任何市場資料日期。
 */
function RateRow({ candidate, params }: {
  candidate: Candidate; params: AnalysisView["params"];
}) {
  const source = params.rate_curve_used
    ? "US Treasury"
    : params.rate_explicit
    ? "CLI 明示"
    : "Fallback 常數";
  return (
    <>
      <Row label="Rate used">
        {formatReturn(candidate.rate_used)}
        {!params.rate_curve_used && !params.rate_explicit && (
          <span className="row-note">
            {" "}· FALLBACK／Treasury curve unavailable
            {params.rate_note && `（${params.rate_note}）`}
          </span>
        )}
      </Row>
      <Row label="Tenor">{candidate.rate_tenor_years.toFixed(2)} 年</Row>
      <Row label="Source">{source}</Row>
      <Row label="Curve date">
        {params.rate_curve_used ? (
          <>
            {params.rate_curve_date}
            {params.rate_curve_stale && (
              <span className="row-note"> · STALE（陳舊備援）</span>
            )}
          </>
        ) : "—"}
      </Row>
    </>
  );
}

/**
 * 股利殖利率 q 三項（#123，spec #117 §2）：q used／Dividend source／
 * Data as of——取代前一版「有沒有做股利調整」完全不顯示在畫面上的
 * 空白。三態沿用既有語意（`q_by_symbol`／`q_source`／`q_as_of`／
 * `q_stale`），跟 `RateRow` 同一套判斷方式，但欄位標籤刻意不重用
 * 「Source」／「Curve date」——兩個區塊在同一個 Model & Assumptions
 * 展開區裡先後渲染，重名會讓 `getByText` 之類的查詢無法唯一定位。
 *
 * q 是**單一數值**（標的的性質），不像利率逐到期日查表，所以只讀
 * `params`，不需要 `candidate`——這裡沒有 `RateRow` 那種「不同候選
 * 可能查到不同利率」的問題。
 */
function QRow({ params }: { params: AnalysisView["params"] }) {
  const noQ = params.q_by_symbol === null;
  return (
    <>
      <Row label="q used">
        {formatReturn(params.q_by_symbol ?? 0)}
        {noQ && (
          <span className="row-note">
            {" "}· NO DIVIDEND ADJUSTMENT
            {params.q_note && `（${params.q_note}）`}
          </span>
        )}
      </Row>
      <Row label="Dividend source">{noQ ? "—" : params.q_source}</Row>
      <Row label="Data as of">
        {noQ ? "—" : (
          <>
            {params.q_as_of}
            {params.q_stale && (
              <span className="row-note"> · STALE（陳舊備援）</span>
            )}
          </>
        )}
      </Row>
    </>
  );
}

/** Risk / Payoff：Breakeven／Max Profit／Max Loss／Execution Friction。 */
function RiskPayoff({ candidate }: { candidate: Candidate }) {
  return (
    <>
      <Row label="Breakeven">{money(candidate.breakeven)}</Row>
      <Row label="Max Profit">
        {candidate.max_profit === null ? "無上限" : money(candidate.max_profit)}
      </Row>
      {/* debit 策略（本站四種皆是）最大損失恆等於進場成本，見
          `store.py` 的 `max_loss_per_contract` 註解——不是巧合，是定義。 */}
      <Row label="Max Loss">{money(candidate.natural_cost)}</Row>
      <Row label="Execution Friction">
        {formatReturn(candidate.friction)}
        <span className="row-note">（{money(candidate.friction_amount)}/股）</span>
      </Row>
    </>
  );
}

/** Position Sensitivity：淨部位對現價／時間／IV 的敏感度四項。 */
function PositionSensitivity({ candidate }: { candidate: Candidate }) {
  return (
    <>
      <Row label="Net Delta">{candidate.net_delta.toFixed(2)}</Row>
      <Row label="Theta/day">{formatReturn(candidate.theta_day_rate)} / 天</Row>
      <Row label="Vega/1 vol point">{formatReturn(candidate.vega_per_pt)} / 1% IV</Row>
      <Row label="Effective Leverage">{candidate.effective_leverage.toFixed(1)}x</Row>
    </>
  );
}

/** 一隻腿的 Bid／Ask／IV／Volume／OI——逐腿報價要兩邊都給，不是只給
 *  「這隻腿最差成交會用到的那一邊」。單腿候選只有買腿，沒有最差成交
 *  以外的報價可比較，但價差兩腿都該看得到完整雙邊報價，才看得出買賣
 *  價差寬不寬——只印一邊等於把價差資訊藏起來。Volume／OI 依 MVP V3
 *  （#104）裁示降為中性 metadata，跟 IV 同樣走 `row-note`（低權重、
 *  無警示樣式），不獨立成一列搶視覺份量。 */
function LegRow({ label, leg }: { label: string; leg: Leg }) {
  return (
    <Row label={label}>
      Strike {leg.strike} Bid {money(leg.bid)} / Ask {money(leg.ask)}
      <span className="row-note">
        {" "}IV {leg.iv === null ? "—" : `${(leg.iv * 100).toFixed(0)}%`}
        {" "}· Volume {leg.volume} · OI {leg.open_interest}
      </span>
    </Row>
  );
}

/** Execution：逐腿雙邊報價／Net Mid／Net Worst（保守進場成本）。 */
function ExecutionSection({ candidate }: { candidate: Candidate }) {
  const [buy, sell] = candidate.legs;
  return (
    <>
      {buy && <LegRow label="Buy Leg" leg={buy} />}
      {sell && <LegRow label="Sell Leg" leg={sell} />}
      <Row label="Net Mid">{money(candidate.mid_cost)}</Row>
      <Row label="Net Worst（保守進場成本）">{money(candidate.natural_cost)}</Row>
    </>
  );
}

/**
 * Model & Assumptions：折疊，只留真正影響估值且可驗證的參數與資料
 * 來源——利率四項（決策 H）、IV 情境、Delta 分級門檻、最低要求報酬率。
 * 過濾／配對統計一行（CandidatePool 已負責）與 `methodology_text`
 * 大段散文依決策 G 不再渲染。
 */
function ModelAssumptions({ candidate, params }: {
  candidate: Candidate; params: AnalysisView["params"];
}) {
  return (
    <details className="report-methodology">
      <summary>Model &amp; Assumptions</summary>
      <RateRow candidate={candidate} params={params} />
      <QRow params={params} />
      <Row label="IV 情境">
        {params.iv_shifts.map((s) => (s === 0 ? "不變" : `${s > 0 ? "+" : ""}${(s * 100).toFixed(0)}%`)).join(" / ")}
      </Row>
      <Row label="Delta 分級門檻">
        {params.delta_bands[0]} / {params.delta_bands[1]}
      </Row>
      <Row label="最低要求報酬率">{formatReturn(params.min_return)}</Row>
    </details>
  );
}

export default function AnalysisReport({ view, result, candidate }: {
  view: AnalysisView;
  result: StrategyResult;
  candidate: Candidate | null;
}) {
  if (!candidate) return null;   // 無合格候選——跟主圖同樣的邊界（附錄A10.2）

  return (
    // 進階區（票上「詳細頁進階區兩個區塊」，QA1-12 舊 Streamlit 版的
    // 既有慣例）：預設收合，展開才看得到——內容比頁面其他區塊長得多，
    // 攤開常駐會把到期日結構與候選池診斷推到很下面。
    <details className="card">
      <summary className="section-title">📄 分析報告</summary>
      <h3 className="section-title report-subsection">Risk / Payoff</h3>
      <RiskPayoff candidate={candidate} />
      <h3 className="section-title report-subsection">Position Sensitivity</h3>
      <PositionSensitivity candidate={candidate} />
      <h3 className="section-title report-subsection">Execution</h3>
      <ExecutionSection candidate={candidate} />
      <ModelAssumptions candidate={candidate} params={view.params} />
      {/* 免責聲明：獨立、不折疊——不是四區塊之一，不能讓它看起來像
          Model & Assumptions 的延伸段落。 */}
      <p className="caption report-disclaimer">{result.disclaimer_text}</p>
    </details>
  );
}
