/**
 * Strategy Family 分頁（T11／#229，Initial V2）：詳細頁第一次同時呈現
 * 多個 Family——每個使用者啟用的 family 各一個分頁，分頁內部維持既有
 * 「依到期日分組」結構與版面完全不變（`ExpiryStructure` 零改動複用）。
 * 同一個 family 底下不同 subtype 的候選在同一個排名池裡競爭
 * （`family.ts::mergedExpiryTop10`），畫面上不依 subtype 分區；每個
 * 候選標示它實際的 subtype（`ExpiryStructure` 的 `CandidateRow` 已
 * 補上，見該檔）。
 *
 * 只有一個 family 時完全不畫分頁列——沒有選擇可言的地方硬要畫一排
 * 只有一顆的按鈕，是純噪音（AC 明文：single family 時不出現多餘 UI）。
 * 這也是既有單一 family 劇本（Initial V2 之前建立的全部劇本）在視覺上
 * 逐位元維持不變的保證：`families.length === 1` 時，這個元件的輸出
 * 就是原本那個 family 的內容本身，沒有任何額外包裝。
 *
 * 分頁選取與**主圖／劇本摘要無關**：那兩處固定顯示跨 family 冠軍
 * （`family.ts::championCandidate`），不隨分頁切換而改變——沿用
 * QA1-06「主圖就是主圖，不跟著別處的互動改變」的既有原則，延伸到
 * family 這個新維度（CONTEXT.md「Family Tab」一節）。預設打開的分頁
 * 是冠軍所屬 family，使用者可以切到別的分頁單純瀏覽排名，不影響上方
 * 固定顯示的冠軍。
 *
 * 不可選的 family（`family_eligibility[family].eligible === false`）
 * 分頁一樣存在、一樣點得進去，內容顯示原因——facts-only，不是把它
 * 藏起來或反灰擋住（沿用 CreateForm.tsx 既有的 eligibility 呈現裁示）。
 */
import { useState } from "react";

import AnalysisReport from "./AnalysisReport";
import CandidatePool from "./CandidatePool";
import ExpiryStructure from "./ExpiryStructure";
import type { AnalysisView, StrategyResult } from "./api";
import {
  FAMILY_LABELS, championCandidate, enabledFamilies, familyBaselineTopCandidate,
  familyOf, mergedExpiryTop10, resultsByFamily,
} from "./family";

/** 目前該顯示哪個 family：使用者選的那個若還在（換了一次分析後可能
 *  消失）就用它；否則退回冠軍所屬 family，再不然第一個——與
 *  `expiry.ts::resolveExpiry` 同一種「使用者選擇優先、退回預設」寫法。 */
function resolveFamily(
  families: string[], picked: string | null, championFamily: string | null,
): string | null {
  if (picked !== null && families.includes(picked)) return picked;
  if (championFamily !== null && families.includes(championFamily)) {
    return championFamily;
  }
  return families[0] ?? null;
}

/** 這個 family 底下、真的產生候選的 subtype 一個都沒有時的說明——優先
 *  用非 `skipped_direction` 的那個（它的訊息才是真正解釋「為什麼零
 *  候選」的那句，例如過濾器砍光了），沒有的話才退回任何一個既有訊息。 */
function emptyFamilyMessage(group: StrategyResult[]): string {
  const preferred = group.find((r) => r.status !== "skipped_direction");
  const message = (preferred ?? group[0])?.message;
  return message || "這個策略沒有產生結果。";
}

export default function FamilyTabs({
  view, strategies,
}: {
  view: AnalysisView;
  strategies: readonly string[];
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const families = enabledFamilies(strategies, view);
  if (families.length === 0) return null;

  const champion = championCandidate(view);
  const championFamily = champion ? familyOf(champion.strategy) : null;
  const current = resolveFamily(families, picked, championFamily);
  const grouped = resultsByFamily(view);
  const group = current !== null ? (grouped.get(current) ?? []) : [];
  const okResults = group.filter((r) => r.status === "ok");

  return (
    <>
      {families.length > 1 && (
        <div className="chip-strip" role="group" aria-label="策略家族">
          {families.map((family) => (
            <button
              key={family}
              aria-pressed={family === current}
              className={family === current ? "chip selected" : "chip"}
              onClick={() => setPicked(family)}
            >
              <span className="chip-date">{FAMILY_LABELS[family] ?? family}</span>
            </button>
          ))}
        </div>
      )}

      {current !== null && group.length === 0 && (
        <section className="card">
          <h2 className="section-title">{FAMILY_LABELS[current] ?? current}</h2>
          <p className="caption">
            {view.family_eligibility?.[current]?.reason
              ?? "這個策略家族目前無法分析。"}
          </p>
        </section>
      )}

      {current !== null && group.length > 0 && okResults.length === 0 && (
        <section className="card">
          <h2 className="section-title">{FAMILY_LABELS[current] ?? current}</h2>
          <p className="caption">{emptyFamilyMessage(group)}</p>
        </section>
      )}

      {current !== null && okResults.length > 0 && (() => {
        const merged = mergedExpiryTop10(view, okResults);
        const diagnosticsResult = okResults[0];
        const familyCandidate = familyBaselineTopCandidate(view, merged);
        return (
          <>
            <ExpiryStructure view={view} result={merged}
                             baselineExpiry={view.baseline_expiry} />
            <CandidatePool view={view} result={diagnosticsResult} />
            <AnalysisReport view={view} result={diagnosticsResult}
                           candidate={familyCandidate} />
          </>
        );
      })()}
    </>
  );
}
