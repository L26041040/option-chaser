/**
 * FB4-01（#60）：候選池診斷。
 *
 * 為什麼要有這個區塊：排名第一的候選看起來永遠很正常，但如果整池只
 * 剩它一個，那個名次沒有意義。使用者必須看得到池子的實際狀態，才不會
 * 被「倖存者」誤導——這正是需求方遇到「盤後跑出買77/賣85」時，畫面上
 * 完全沒有線索的那個問題。
 *
 * 數字全部由引擎算好（`filter_stages`／`pair_report`／`expiry_counts`），
 * 這裡只做計數加總與呈現，零金融計算。
 */
import { primaryResult, validPairsForExpiry, type AnalysisView } from "./api";

/** 低於這個組數就警示——沿用 Streamlit 版 FB3-02（#45）的門檻。 */
const THIN_POOL = 3;

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
        <div className="row sub" key={stage.label}>
          <span className="row-label">{stage.label}</span>
          <span className={stage.removed > 0 ? "row-value negative" : "row-value"}>
            {stage.removed > 0 ? `−${stage.removed}` : "0"}
          </span>
        </div>
      ))}

      <div className="row">
        <span className="row-label">通過品質過濾</span>
        <span className="row-value">
          {counts === null ? "—" : `${counts.passed} 筆`}
        </span>
      </div>

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

      {validPairs !== null && validPairs < THIN_POOL && (
        <div className="notice" role="status">
          <span aria-hidden="true">⚠ </span>
          該期僅 {validPairs} 組候選通過品質過濾，排名參考價值有限——
          名次第一可能只是「整池剩下的那一個」。
        </div>
      )}
    </div>
  );
}
