/**
 * OG-07（#325）：桌面「淨成本走勢」底部 tab——`SpreadHistory.tsx` 的
 * 桌面換皮版，換成常駐面板（artifact：進了這個 tab 就直接看得到圖，
 * 不用再展開一次 `<details>`）＋右側統計摘要，不是另一份圖表邏輯：
 * 折線本身直接重用 `SpreadHistory.tsx` 匯出的 `Chart`／`GRANULARITIES`。
 *
 * 跟隨冠軍候選（`champion`），不是目前排名表選取的那一列——維持
 * `ScenarioDetail.tsx` 既有「主圖／走勢圖固定顯示冠軍」的既有原則
 * （QA1-06），OG-06／#321 的 `selectedCandidate` 只影響中央 Heatmap
 * 與右欄候選面板，這裡不是它的消費端。
 *
 * 單腿也支援（OG-07 票面明文）：既有 `SpreadHistory.tsx` 的
 * `legs.length < 2` 排除是 T9 附錄A13 對 `all_candidates`（另一份資料
 * 結構）的 MVP 範圍限制；narrow history 的讀取路徑
 * （`narrow_history_for_candidate()`／`resolve_historical_cost()`）
 * 本身是純字串 `candidate_key` 查詢，不分腿數（`parse_candidate_key()`／
 * `cost_from_snapshot()` 通用於任意策略形狀）——這裡不重複那個過時的
 * 前端限制，讓單腿候選第一次也能看到走勢圖。`SpreadHistory.tsx`
 * 本身（含它的 `legs.length < 2` 排除）逐位元組不變，手機版渲染路徑
 * 完全沒受影響，這個放寬只發生在桌面這個新元件裡。
 *
 * fetch 時機跟既有 `SpreadHistory` 不同：既有版本是 `<details onToggle>`
 * 展開才抓；這裡沒有收合可言（tab 本身的顯示／隱藏由
 * `DesktopDetailBody` 的 CSS 決定，元件不會因為使用者切到別的 tab 而
 * 卸載），因此改成掛載／候選换人時就抓一次，不是等一個不存在的展開
 * 事件。
 */
import { useEffect, useState } from "react";

import { Row } from "./AnalysisReport";
import { getSpreadHistory, type Candidate, type HistoryEntry } from "./api";
import { money } from "./scenarios";
import { Chart, GRANULARITIES } from "./SpreadHistory";
import {
  downsampleHistory, historySummaryStats, type Granularity,
} from "./spreadHistory";

export default function DesktopSpreadHistory({ scenarioId, candidate }: {
  scenarioId: string;
  candidate: Candidate | null;
}) {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [granularity, setGranularity] = useState<Granularity>("day");

  useEffect(() => {
    if (!candidate) return;
    let alive = true;
    setLoading(true);
    setError(null);
    getSpreadHistory(scenarioId, candidate.candidate_key)
      .then((r) => { if (alive) setEntries(r.entries); })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // 候選換人（切了冠軍——理論上不會在同一份 view 裡發生，但保守起見
    // 依 candidate_key 而非物件參照重抓）或劇本換人都要重抓一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, candidate?.candidate_key]);

  if (!candidate) {
    return <p className="caption">無合格候選</p>;
  }

  const shown = entries ? downsampleHistory(entries, granularity) : null;
  const stats = entries ? historySummaryStats(entries) : null;

  return (
    <div className="spread-history-panel">
      <div className="spread-history-panel-chart">
        {loading && <p className="caption">載入中……</p>}
        {error && <p className="notice error">{error}</p>}

        {shown && (
          <>
            <div className="segmented" role="group" aria-label="時間粒度">
              {GRANULARITIES.map((g) => (
                <button
                  key={g.key}
                  type="button"
                  className={g.key === granularity ? "segmented-option selected" : "segmented-option"}
                  aria-pressed={g.key === granularity}
                  onClick={() => setGranularity(g.key)}
                >
                  {g.label}
                </button>
              ))}
            </div>

            {shown.length === 0 ? (
              <p className="caption">這個劇本還沒有歷史紀錄。</p>
            ) : (
              <Chart entries={shown} />
            )}
          </>
        )}
      </div>

      {stats && (
        <div className="spread-history-panel-stats">
          <Row label="今日">{stats.latest === null ? "—" : money(stats.latest)}</Row>
          <Row label={`${stats.count} 次刷新區間`}>
            {stats.range === null ? "—" : `${money(stats.range[0])} – ${money(stats.range[1])}`}
          </Row>
          <Row label="缺席快照">
            {stats.gapCount} <span className="row-note">（斷點不插值）</span>
          </Row>
          <Row label="首次出現">
            {stats.firstSeen === null ? "—" : stats.firstSeen.slice(0, 10)}
          </Row>
        </div>
      )}
    </div>
  );
}
