/**
 * Strategy Family 分組與跨 subtype 排名池合併（T11／#229，Initial V2）。
 *
 * 零金融計算：每個候選的 `baseline_return` 都是引擎算好的既有欄位，
 * 這裡只做分組、選取、排序——跟後端 `expiry_top10` 自己「排序取前 N」
 * 是同一種操作，不是新的財務推導。
 *
 * `SUBTYPE_FAMILY` 是後端 `option_chaser/models.py::STRATEGY_FAMILY`
 * 的前端對應——同一份紅線後端也遵守（唯一一張對照表，沒有第二處硬
 * 編碼），只是前後端語言不共用型別，兩邊各自一份、內容必須逐字同步。
 * 新增 subtype（T15／#230 的 call-fly／put-fly）時記得同時更新這裡。
 */
import type { AnalysisView, Candidate, ExpiryTop10, StrategyResult } from "./api";
import { resolveCandidate } from "./api";
import type { ExpiryBearing } from "./expiry";

export const FAMILIES = ["single-leg", "vertical-spread", "butterfly"] as const;

export const FAMILY_LABELS: Record<string, string> = {
  "single-leg": "Call / Put",
  "vertical-spread": "Vertical Spread",
  "butterfly": "Butterfly",
};

const SUBTYPE_FAMILY: Record<string, string> = {
  "long-call": "single-leg",
  "long-put": "single-leg",
  "bull-call-spread": "vertical-spread",
  "bear-put-spread": "vertical-spread",
};

export function familyOf(subtype: string): string {
  return SUBTYPE_FAMILY[subtype] ?? subtype;
}

/**
 * 這個劇本實際啟用哪些 family，依 canonical 順序（`FAMILIES`）輸出，
 * 不受 `ScenarioDetail.strategies` 儲存順序（使用者勾選的先後）影響
 * ——分頁順序要穩定，不該隨使用者當初點的順序而每個劇本長得不一樣。
 *
 * `enabled` 通常就是 `ScenarioDetail.strategies`（必填欄位，理論上
 * 不會是空陣列）；萬一真的是空陣列，改從 `view.results` 反推，不讓
 * 詳細頁開天窗。
 */
export function enabledFamilies(
  enabled: readonly string[], view: AnalysisView,
): string[] {
  const set = new Set(
    enabled.length > 0 ? enabled : view.results.map((r) => familyOf(r.strategy)));
  return FAMILIES.filter((f) => set.has(f));
}

/** `view.results` 依 family 分組——同一個 family 底下可能有多筆
 *  （既有四個 subtype 兩兩方向互斥，今天恆為 1 個 ok＋1 個
 *  skipped_direction；Butterfly 尚無 subtype，不會出現在這裡）。 */
export function resultsByFamily(
  view: AnalysisView,
): Map<string, StrategyResult[]> {
  const map = new Map<string, StrategyResult[]>();
  for (const r of view.results) {
    const fam = familyOf(r.strategy);
    const list = map.get(fam) ?? [];
    list.push(r);
    map.set(fam, list);
  }
  return map;
}

/**
 * 跨 family 冠軍——劇本卡片頭條數字與詳細頁主圖的資料來源
 * （CONTEXT.md「Per-family Representative」／「Family Tab」兩節）。
 *
 * 與後端 `store.representative_candidate()` 同一個候選池、同一條
 * 規則：每個「有結果」（`status === "ok"`）的 subtype，各自在 baseline
 * 到期日的第 1 名候選互相比較，取 `baseline_return` 最高者，同分時
 * `view.results` 較前面（`request.strategies` 展開順序）的那個勝出
 * ——`>` 而非 `>=` 正是為了保留這個順序，跟後端 `expiry_groups[baseline]
 * .rows` 已排序好、`max()` 對平手保留第一筆是同一個效果。
 *
 * 舊版（Initial V2 之前）`baselineTopCandidate()` 只看 `results[0]`
 * ——那時 `_MVP_STRATEGIES` 恆為單一 family、`results[0]` 剛好就是
 * 唯一候選，兩者從未被觀察出差異。多 family 之後 `results[0]` 只是
 * 「第一個被展開的 subtype」，不再保證是冠軍：同一個 family 內就可能
 * 出現 `results[0]` 是被方向閘門擋掉的 `skipped_direction`（見
 * `src/family.test.ts` 對此的專屬回歸——已用真實 HTTP 路徑重現過這個
 * 情境：`view.results` 的第一筆恰好是被方向閘門擋掉的那個）。這正是
 * AC 明文要求
 * 記錄的「口徑升級」（CONTEXT.md「Per-family Representative」）——
 * `baselineTopCandidate()` 本身刻意不修改，這裡新增一個正確處理多
 * family／多 subtype 的獨立函式。
 */
export function championCandidate(view: AnalysisView): Candidate | null {
  let best: Candidate | null = null;
  for (const result of view.results) {
    if (result.status !== "ok") continue;
    const group = (result.expiry_top10 ?? [])
      .find((g) => g.expiry === view.baseline_expiry);
    const top = resolveCandidate(view, group?.candidate_keys[0]);
    if (top && (best === null || top.baseline_return > best.baseline_return)) {
      best = top;
    }
  }
  return best;
}

export function resultForStrategy(
  view: AnalysisView, strategy: string,
): StrategyResult | null {
  return view.results.find((r) => r.strategy === strategy) ?? null;
}

/**
 * 同一個 family 底下多個 subtype 的候選，合併進**同一個排名池**
 * （AC 明文要求：畫面上不依 subtype 分區）——依 `baseline_return`
 * 重新排序、各到期日各取前十，跟後端 `expiry_top10` 自己「排序取前
 * N」是同一種選取操作。`expiry_counts` 逐到期日加總——「該期有效
 * 組數」對使用者而言是這個 family 整體的事，不是某個 subtype 各自
 * 的事。
 *
 * 今天（Initial V2）任一 family 在給定方向下**恆為 0 或 1 個 ok
 * subtype**（既有四個 subtype 兩兩方向互斥；Butterfly 尚無 subtype）
 * ——因此這個函式今天永遠只是「原樣透傳唯一一筆」。T15／#230
 * （Butterfly 的 call-fly／put-fly 皆為 flat-only）會是第一次同一個
 * family、同一個方向下真的有兩個 ok subtype 同時存在，這裡的合併邏輯
 * 已經先寫好、有專屬單元測試覆蓋合成的多 subtype 情境，不是等到那時
 * 候才臨時補。
 */
export function mergedExpiryTop10(
  view: AnalysisView, okResults: StrategyResult[],
): { expiry_top10: ExpiryTop10[]; expiry_counts: [string, number][] } {
  const keysByExpiry = new Map<string, string[]>();
  const countsByExpiry = new Map<string, number>();
  for (const result of okResults) {
    for (const group of result.expiry_top10 ?? []) {
      const keys = keysByExpiry.get(group.expiry) ?? [];
      keys.push(...group.candidate_keys);
      keysByExpiry.set(group.expiry, keys);
    }
    for (const [expiry, count] of result.expiry_counts) {
      countsByExpiry.set(expiry, (countsByExpiry.get(expiry) ?? 0) + count);
    }
  }
  const expiries = [...keysByExpiry.keys()].sort();
  const expiry_top10 = expiries.map((expiry) => {
    const keys = keysByExpiry.get(expiry) ?? [];
    const ranked = keys
      .map((key) => ({ key, c: resolveCandidate(view, key) }))
      .filter((x): x is { key: string; c: Candidate } => x.c !== null)
      .sort((a, b) => b.c.baseline_return - a.c.baseline_return)
      .slice(0, 10)
      .map((x) => x.key);
    return { expiry, candidate_keys: ranked };
  });
  const expiry_counts: [string, number][] = [...countsByExpiry.entries()]
    .sort(([a], [b]) => a.localeCompare(b));
  return { expiry_top10, expiry_counts };
}

/**
 * 這個 family（合併後）在 baseline 到期日的第 1 名——`api.ts` 既有
 * `baselineTopCandidate()` 的 family-scoped 版本，同一條規則（該期
 * `candidate_keys[0]`），只是資料來源換成合併後的排名池。 */
export function familyBaselineTopCandidate(
  view: AnalysisView, merged: ExpiryBearing,
): Candidate | null {
  const group = (merged.expiry_top10 ?? [])
    .find((g) => g.expiry === view.baseline_expiry);
  return resolveCandidate(view, group?.candidate_keys[0]);
}
