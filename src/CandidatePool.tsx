/**
 * FB4-01（#60）：候選池診斷。
 *
 * 為什麼要有這個區塊：排名第一的候選看起來永遠很正常，但如果整池只
 * 剩它一個，那個名次沒有意義。使用者必須看得到池子的實際狀態，才不會
 * 被「倖存者」誤導——這正是需求方遇到「盤後跑出買77/賣85」時，畫面上
 * 完全沒有線索的那個問題。
 *
 * 數字全部由引擎算好（`filter_stages`／`quality_flags`／`pair_report`／
 * `expiry_counts`），這裡只做計數加總與呈現，零金融計算。
 *
 * V6（#54）起「該期組數過少」的**警示**不在這裡：它已經貼在到期日結構
 * 那份清單旁邊（`ExpiryStructure`），而且跟著使用者切換的到期日走。同一
 * 句話在一頁上出現兩次，第二次就只是噪音。這裡保留「該期有效組數」那
 * 一列數字，因為它是整份池子診斷的一部分。
 *
 * FB5-04（#65，spec #61）：`filter_stages`（A／B 兩類，紅色「−」）與
 * `quality_flags`（C 類，橙色計數）刻意分成兩個小節、用不同顏色——前者
 * 是「排除」（這幾筆真的不在合格池裡了），後者是「標示」（合格池裡有
 * 這麼多筆帶著品質疑慮，但一筆都沒少）。混在同一個列表裡，使用者會分
 * 不出哪個數字代表候選變少、哪個只是備註。
 */
import { primaryResult, type AnalysisView } from "./api";
import { validPairsForExpiry } from "./expiry";

export default function CandidatePool({ view }: { view: AnalysisView }) {
  const result = primaryResult(view);
  if (!result) return null;

  if (result.status !== "ok") {
    return (
      <div className="card">
        <h2 className="section-title">候選池</h2>
        <p className="caption">{result.message || "這個策略沒有產生結果。"}</p>
      </div>
    );
  }

  const counts = result.filter_report;
  const pairs = result.pair_report;
  const validPairs = validPairsForExpiry(result, view.baseline_expiry);

  return (
    <div className="card">
      <h2 className="section-title">候選池</h2>

      {/* 不是「整條鏈抓到幾筆」——引擎的 FilterReport.total 已經先篩過
          策略對應的買賣權別（filters.apply_filters）與選定到期日
          （timeframe.select_expiries），標籤必須說清楚是哪一群。 */}
      <div className="row">
        <span className="row-label">選定到期日的合約</span>
        <span className="row-value">
          {counts === null ? "—" : `${counts.total} 筆`}
        </span>
      </div>

      {result.filter_stages.map((stage) => (
        <div
          className="row sub"
          key={stage.label}
          // T05（#226，Initial V2，`/code-review` Spec 軸回饋）：被這一關
          // 剔除掉的候選身份範例——瀏覽器原生 tooltip，不佔額外畫面空間，
          // 沒有範例（這關沒砍到人）就不掛這個屬性。
          title={
            stage.removed_examples.length > 0
              ? `例：${stage.removed_examples.join(", ")}`
              : undefined
          }
        >
          <span className="row-label">{stage.label}</span>
          <span className="row-value">
            {/* FB5-04（#65，spec #61）：這關屬於哪一類（A＝資料健全性、
                B＝數學前提），跟著被排除的筆數一起顯示——`row-note` 用
                次要色，不搶「−N」那個真正要看的數字。 */}
            <span className="row-note">{stage.filter_class} 類 </span>
            <span className={stage.removed > 0 ? "negative" : undefined}>
              {stage.removed > 0 ? `−${stage.removed}` : "0"}
            </span>
          </span>
        </div>
      ))}

      <div className="row">
        <span className="row-label">通過品質過濾</span>
        <span className="row-value">
          {counts === null ? "—" : `${counts.passed} 筆`}
        </span>
      </div>

      {/* FB5-04（#65，spec #61）：C 類品質標示——上面通過品質過濾的筆數
          裡，有幾筆帶著這些疑慮。橙色計數，跟上面「排除」的紅色「−」
          刻意不同色，避免使用者誤以為這些筆數也被刪掉了。 */}
      {result.quality_flags.some((f) => f.count > 0) && (
        <>
          <div className="row sub">
            <span className="row-label">品質標示（不影響入選）</span>
          </div>
          {result.quality_flags.map((flag) => (
            <div className="row sub" key={flag.label}>
              <span className="row-label">{flag.label}</span>
              <span className={flag.count > 0 ? "row-value flagged" : "row-value"}>
                {flag.count} 筆
              </span>
            </div>
          ))}
        </>
      )}

      {pairs && (
        <>
          <div className="row">
            <span className="row-label">配對</span>
            <span className="row-value">{pairs.total_pairs} 組</span>
          </div>
          {/* 合理性檢查（淨成本 ≤ 0、最壞成本 ≥ 價差寬度）也是一道殺手，
              少了它，「配對 780 → 680」中間那 100 組會沒有交代。 */}
          <div className="row sub">
            <span className="row-label">合理性不通過</span>
            <span
              className={
                pairs.removed_sanity > 0 ? "row-value negative" : "row-value"
              }
            >
              {pairs.removed_sanity > 0 ? `−${pairs.removed_sanity}` : "0"}
            </span>
          </div>
          {/* T05（#226，Initial V2，`/code-review` Spec 軸回饋）：B 層
              （導出層數學安全網）獨立於上面的合理性檢查，各自一列——
              先前只序列化沒渲染，這裡補上，跟單腳路徑（上方 filter_stages
              已經通用渲染 B 層那關）享有同等的可見度。 */}
          <div
            className="row sub"
            title={
              pairs.b_layer_removed_examples.length > 0
                ? `例：${pairs.b_layer_removed_examples.join(", ")}`
                : undefined
            }
          >
            <span className="row-label">成本或報酬為不可能值（B 層）</span>
            <span
              className={
                pairs.b_layer_removed > 0 ? "row-value negative" : "row-value"
              }
            >
              {pairs.b_layer_removed > 0 ? `−${pairs.b_layer_removed}` : "0"}
            </span>
          </div>
          <div className="row">
            <span className="row-label">有效組合</span>
            <span className="row-value">{pairs.passed} 組</span>
          </div>
        </>
      )}

      <div className="row">
        <span className="row-label">該期有效組數</span>
        <span className="row-value">
          {validPairs === null ? "—" : `${validPairs} 組`}
        </span>
      </div>

    </div>
  );
}
