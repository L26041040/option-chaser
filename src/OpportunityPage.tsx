/**
 * 機會搜尋頁（OS-05／#394，母票 #389 §5.3–5.4、C13–C14）。
 *
 * 共識清單（只讀全站共識快取）→「搜尋選擇權」對入選股逐檔跑**既有**
 * 引擎（`POST /api/opportunity/search`，一次一檔、依 `remaining` 續跑）→
 * 前端跨標的排序（`rankOpportunities()`）→ 任一列「存成劇本」走既有建立
 * 劇本流程（`onSaveAsScenario`，App 的同一條 create＋refresh 路徑）。
 *
 * 幾條刻意的決定：
 *
 * - 守門：資料顯示授權未確認前只給 Super User／Super Admin（#389 §7）。
 *   角色未確認前只顯示載入中、不打任何機會搜尋端點；不是 SU/SA 一律
 *   `replace` 回首頁（比照 `AdminPage`）。後端 403 是第二道防線，萬一
 *   走到也照實顯示後端訊息。
 * - 來源未設定（`source.configured=false`）就沒有搜尋按鈕——不假裝能搜。
 *   測試資料來源（`is_fixture`）在頁首常駐標示，不隨捲動或狀態消失。
 * - 「停止」是真的不再續跑：已經送出的那一次照樣等它回來並顯示（上游
 *   額度已經花了），之後不再送下一次；剩下的檔留著，可以「繼續搜尋」。
 * - 超過單次上限（`fetch_cap`）的檔不會被默默丟掉：後端放在 `deferred`、
 *   這頁照實說「尚有 N 檔未搜尋」，使用者按鈕才對那些檔發起新的一輪
 *   （同樣受上限約束）——不自動續跑，否則上限形同虛設。
 * - 排序選項的文字由後端給（搜尋回應的 `sort_options`，與設定頁同一份）。
 * - 每個數字都是後端原值，這裡只排序與格式化。單位照實標，而且跟既有
 *   詳細頁同一口徑（#395）：投入成本是每股（`entry_cost`）；最大損失也顯示
 *   每股＝`max_loss_per_contract / 100`（後端欄位是每口、100 股；既有詳細頁
 *   的 Max Loss 也是這樣 ÷100 顯示），存成劇本後詳細頁與這一列是同一個數字。
 *   排序仍用後端的每口原值（÷100 是單調的，順序不變）。
 * - 文案只說「目標價情境報酬」，並固定一句它不是期望值或勝率。
 * - 來源已設定時，頁首下方是「分析師資料」區塊（`AnalystUpdatePanel`，
 *   LIVE-T3／#398）：更新／重試結束後重讀共識清單。
 */
import { useEffect, useRef, useState } from "react";

import AnalystUpdatePanel from "./AnalystUpdatePanel";

import {
  formatLegs,
  getAuthStatus,
  getOpportunityConsensus,
  searchOpportunities,
  type ConsensusItem,
  type CreateScenarioRequest,
  type OpportunityConsensusResponse,
  type OpportunityRow,
  type OpportunitySearchFailure,
  type OpportunitySearchRequest,
  type SortOption,
} from "./api";
import { strategyLabel } from "./detail";
import { setAuthStatusCache, subscribeAuthStatus } from "./fetchCache";
import ConsensusDetailToggle from "./ConsensusDetail";
import {
  mergeSearchRows,
  opportunityRowKey as rowKey,
  rankOpportunities,
  ratioPct,
  reasonText,
  STATUS_LABELS,
  type OpportunitySort,
} from "./opportunity";
import { detailHash, opportunitySettingsHash } from "./route";
import { formatReturn, money } from "./scenarios";
import { roleAtLeast, type Role } from "./superuser";

export const RETURN_DISCLAIMER =
  "此報酬是『分析師平均目標價在目標月份成立時』的條件情境報酬，不是期望值或勝率";

const COVERAGE_LABELS: Record<string, string> = {
  complete: "完整",
  partial: "部分",
  unknown: "未知",
};

const FAILURE_LABELS: Record<OpportunitySearchFailure["reason"], string> = {
  fetch_failed: "抓不到報價",
  no_candidates: "沒有合格候選",
  invalid_month: "目標月份無效",
  analysis_failed: "分析失敗",
};

function expiryDistance(bufferDays: number): string {
  if (bufferDays === 0) return "與目標月份同日到期";
  return bufferDays < 0
    ? `比目標月份早 ${-bufferDays} 天到期`
    : `比目標月份晚 ${bufferDays} 天到期`;
}

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ok"; data: OpportunityConsensusResponse };

interface SearchState {
  rows: OpportunityRow[];
  failures: OpportunitySearchFailure[];
  processed: string[];
  total: number;
  remaining: string[];
  /** 超過單次上限、這一輪沒搜的檔（後端 `deferred`）。不自動續跑。 */
  deferred: string[];
  /** 排序選項（含文字）照後端給的；還沒搜過時是空的（下拉選單只在有結果時出現）。 */
  sortOptions: SortOption[];
}

const EMPTY_SEARCH: SearchState = {
  rows: [], failures: [], processed: [], total: 0, remaining: [],
  deferred: [], sortOptions: [],
};

/** `new`：重新搜尋入選股；`resume`：接續 `remaining`（同一輪）；
 *  `deferred`：對超過上限而沒搜的檔發起新的一輪（同樣受上限約束），
 *  先前的結果保留。 */
type RunMode = "new" | "resume" | "deferred";

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function OpportunityPage({
  onSaveAsScenario,
}: {
  /** 既有建立劇本流程（`App.tsx`：`createScenario` → 併入清單 → 刷新）。
   *  失敗時往外拋（例如既有的額度訊息），這頁照實顯示。 */
  onSaveAsScenario: (scenario: CreateScenarioRequest) => Promise<{ id: string }>;
}) {
  // `null`＝還不知道角色——不能預設 Normal，否則 SU/SA 會先被導走。
  const [role, setRole] = useState<Role | null>(null);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    // 進這頁一定重新問伺服器（比照 `AdminPage`）：共用快取只會被同一分頁
    // 的登入／登出更新。拿到的新角色寫回快取，讓導覽列一起跟上。
    getAuthStatus(controller.signal)
      .then((s) => {
        if (!alive) return;
        setRole(s.role);
        setAuthStatusCache(s);
      })
      .catch(() => alive && setRole("normal"));
    const unsubscribe = subscribeAuthStatus((s) => alive && setRole(s.role));
    return () => {
      alive = false;
      controller.abort();
      unsubscribe();
    };
  }, []);
  const allowed = role !== null && roleAtLeast(role, "superuser");

  useEffect(() => {
    if (role !== null && !allowed) window.location.replace("#/");
  }, [role, allowed]);

  const [consensus, setConsensus] = useState<Load>({ state: "loading" });
  // 「更新分析師資料」／重試結束後加一，重讀共識清單（LIVE-T3／#398）。
  const [consensusVersion, setConsensusVersion] = useState(0);
  useEffect(() => {
    if (!allowed) return;
    const controller = new AbortController();
    getOpportunityConsensus(controller.signal)
      .then((data) => setConsensus({ state: "ok", data }))
      .catch((e) => {
        if (!controller.signal.aborted) {
          setConsensus({ state: "error", message: errorMessage(e) });
        }
      });
    return () => controller.abort();
  }, [allowed, consensusVersion]);

  const [search, setSearch] = useState<SearchState>(EMPTY_SEARCH);
  const [started, setStarted] = useState(false);
  const [running, setRunning] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [sort, setSort] = useState<OpportunitySort>("return");
  const stopRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function run(mode: RunMode) {
    stopRef.current = false;
    setStopRequested(false);
    setStopped(false);
    setNotice(null);
    setRunning(true);
    setStarted(true);
    let body: OpportunitySearchRequest =
      mode === "resume" ? { symbols: search.remaining }
        : mode === "deferred" ? { symbols: search.deferred }
          : {};
    if (mode === "new") setSearch(EMPTY_SEARCH);
    // 一輪的第一次回應決定這一輪的總數與 `deferred`；續跑只是同一輪的後半。
    let first = mode !== "resume";
    try {
      for (;;) {
        const r = await searchOpportunities(body);
        if (!mounted.current) return;
        const isFirst = first;
        first = false;
        if (isFirst && mode === "new") setSort(r.sort);
        setSearch((prev) => {
          const processed = [...new Set([...prev.processed, ...r.processed])];
          return {
            rows: mergeSearchRows(prev.rows, r.rows),
            failures: [
              ...prev.failures.filter((f) => !r.failures.some((g) => g.symbol === f.symbol)),
              ...r.failures,
            ],
            processed,
            total: isFirst ? processed.length + r.remaining.length : prev.total,
            remaining: r.remaining,
            deferred: isFirst ? r.deferred : prev.deferred,
            sortOptions: r.sort_options,
          };
        });
        if (r.stopped_reason === "fused") {
          setNotice(r.message ?? "今日報價查詢已暫停，請稍後再試");
          break;
        }
        if (r.remaining.length === 0) break;
        if (stopRef.current) {
          setStopped(true);
          break;
        }
        body = { symbols: r.remaining };
      }
    } catch (e) {
      if (mounted.current) setNotice(errorMessage(e));
    } finally {
      if (mounted.current) setRunning(false);
    }
  }

  function stop() {
    stopRef.current = true;
    setStopRequested(true);
  }

  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  async function save(row: OpportunityRow) {
    const key = rowKey(row);
    setSavingKey(key);
    setSaveErrors((prev) => {
      const { [key]: _drop, ...rest } = prev;
      return rest;
    });
    try {
      // `scenario` 原封不動：與手動建立同參數劇本完全相同（#389 C5）。
      const created = await onSaveAsScenario(row.scenario);
      window.location.hash = detailHash(created.id);
    } catch (e) {
      if (mounted.current) setSaveErrors((prev) => ({ ...prev, [key]: errorMessage(e) }));
    } finally {
      if (mounted.current) setSavingKey(null);
    }
  }

  const data = consensus.state === "ok" ? consensus.data : null;
  const isFixture = data?.source.is_fixture ?? false;

  const header = (
    <header className="settings-head opp-head" aria-label="機會搜尋頁首">
      <a className="nav-back" href="#/">
        ‹ 劇本庫
      </a>
      <h1 className="toolbar-title">機會搜尋</h1>
      {isFixture && (
        <p className="opp-fixture" role="note">
          測試資料，非真實市場資料
        </p>
      )}
    </header>
  );

  if (!allowed) {
    return (
      <div className="screen opp-page">
        {role === null && <p className="caption">載入中……</p>}
      </div>
    );
  }

  return (
    <div className="screen opp-page">
      {header}

      {consensus.state === "loading" && <p className="caption">載入中……</p>}
      {consensus.state === "error" && (
        <div className="notice error" role="alert">
          {consensus.message}
        </div>
      )}

      {data && !data.source.configured && (
        <section className="card" aria-label="資料來源">
          <h2 className="section-title">尚未設定分析師資料來源</h2>
          <p className="caption">
            要有提供個別分析師目標價的資料來源，才能算出共識並搜尋選擇權。設定好之前這裡不會有任何清單或搜尋結果。
          </p>
        </section>
      )}

      {data && data.source.configured && (
        <AnalystUpdatePanel onUpdated={() => setConsensusVersion((v) => v + 1)} />
      )}

      {data && data.source.configured && (
        <ConfiguredBody
          data={data}
          search={search}
          started={started}
          running={running}
          stopRequested={stopRequested}
          stopped={stopped}
          notice={notice}
          sort={sort}
          onSort={setSort}
          onSearch={() => {
            setSaveErrors({});
            void run("new");
          }}
          onResume={() => void run("resume")}
          onSearchDeferred={() => void run("deferred")}
          onStop={stop}
          savingKey={savingKey}
          saveErrors={saveErrors}
          onSave={(row) => void save(row)}
        />
      )}
    </div>
  );
}

function ConfiguredBody({
  data, search, started, running, stopRequested, stopped, notice, sort, onSort,
  onSearch, onResume, onSearchDeferred, onStop, savingKey, saveErrors, onSave,
}: {
  data: OpportunityConsensusResponse;
  search: SearchState;
  started: boolean;
  running: boolean;
  stopRequested: boolean;
  stopped: boolean;
  notice: string | null;
  sort: OpportunitySort;
  onSort: (s: OpportunitySort) => void;
  onSearch: () => void;
  onResume: () => void;
  onSearchDeferred: () => void;
  onStop: () => void;
  savingKey: string | null;
  saveErrors: Record<string, string>;
  onSave: (row: OpportunityRow) => void;
}) {
  const selected = data.items.filter((i) => i.gate.selected);
  const weak = data.items.filter((i) => !i.gate.selected && i.status === "ok");
  const thin = data.items.filter((i) => i.status !== "ok");
  const ranked = rankOpportunities(search.rows, sort);

  return (
    <>
      <UniverseCard data={data} />

      <section className="card" aria-label="入選股">
        <h2 className="section-title">入選股（{selected.length} 檔）</h2>
        {selected.length === 0 ? (
          <p className="caption">目前沒有同時通過兩道門檻的股票。</p>
        ) : (
          <ul className="opp-list">
            {selected.map((item) => (
              <li key={item.symbol} aria-label={item.symbol} className="opp-item">
                <ItemSummary item={item} />
                <ConsensusDetailToggle symbol={item.symbol} />
              </li>
            ))}
          </ul>
        )}

        <div className="opp-actions">
          <button
            type="button"
            className="pbtn"
            onClick={onSearch}
            disabled={running || selected.length === 0}
          >
            搜尋選擇權
          </button>
          {running && (
            <button
              type="button"
              className="pbtn line"
              onClick={onStop}
              disabled={stopRequested}
            >
              {stopRequested ? "停止中……" : "停止"}
            </button>
          )}
          {!running && search.remaining.length > 0 && (
            <button type="button" className="pbtn line" onClick={onResume}>
              繼續搜尋剩下 {search.remaining.length} 檔
            </button>
          )}
          {!running && search.remaining.length === 0 && search.deferred.length > 0 && (
            <button type="button" className="pbtn line" onClick={onSearchDeferred}>
              搜尋未搜尋的 {search.deferred.length} 檔
            </button>
          )}
        </div>
        {selected.length === 0 && (
          <p className="caption">沒有入選股，所以沒有可以搜尋的標的。</p>
        )}
        {started && search.total > 0 && (
          <p className="caption opp-progress" aria-live="polite">
            <span>已搜尋 {search.processed.length} / {search.total} 檔</span>
            {running && <span>搜尋中……</span>}
          </p>
        )}
        {stopped && (
          <p className="caption">已停止，剩下的檔還沒搜尋。</p>
        )}
        {search.deferred.length > 0 && (
          <p className="caption">超過單次上限，尚有 {search.deferred.length} 檔未搜尋</p>
        )}
        {notice && (
          <div className="notice error" role="alert">
            {notice}
          </div>
        )}
      </section>

      {search.failures.length > 0 && (
        <section className="card" aria-label="搜尋失敗">
          <h2 className="section-title">搜尋失敗（{search.failures.length} 檔）</h2>
          <ul className="opp-list">
            {search.failures.map((f) => (
              <li key={f.symbol} aria-label={f.symbol} className="opp-item">
                <strong>{f.symbol}</strong>
                <span className="tag warn">{FAILURE_LABELS[f.reason] ?? f.reason}</span>
                <p className="caption">{f.message}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {search.rows.length > 0 && (
        <section className="card" aria-label="搜尋結果">
          <div className="opp-results-head">
            <h2 className="section-title">搜尋結果（{search.rows.length} 列）</h2>
            <label className="opp-sort">
              排序
              <select
                value={sort}
                onChange={(e) => onSort(e.target.value as OpportunitySort)}
              >
                {search.sortOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="caption opp-disclaimer">{RETURN_DISCLAIMER}</p>
          <table className="tbl opp-table">
            <thead>
              <tr>
                <th scope="col">標的</th>
                <th scope="col">策略</th>
                <th scope="col">履約價</th>
                <th scope="col">到期日</th>
                <th scope="col">目標月份</th>
                <th scope="col" className="r">淨成本 / 股</th>
                <th scope="col" className="r">最大損失 / 股</th>
                <th scope="col" className="r">目標價情境報酬</th>
                <th scope="col" className="r">損益兩平</th>
                <th scope="col"><span className="sr-only">動作</span></th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((row) => {
                const key = rowKey(row);
                const err = saveErrors[key];
                return (
                  <tr
                    key={key}
                    aria-label={`${row.symbol} ${strategyLabel(row.subtype)}`}
                    data-family={row.family}
                  >
                    <td data-label="標的" className="opp-symbol">{row.symbol}</td>
                    <td data-label="策略">{strategyLabel(row.subtype)}</td>
                    <td data-label="履約價">
                      {formatLegs(row.legs)}
                    </td>
                    <td data-label="到期日">
                      {row.expiry}
                      <span className="row-note">{expiryDistance(row.buffer_days)}</span>
                    </td>
                    <td data-label="目標月份">{row.target_month}</td>
                    <td data-label="淨成本 / 股" className="r num">{money(row.entry_cost)}</td>
                    <td data-label="最大損失 / 股" className="r num">
                      {money(row.max_loss_per_contract / 100)}
                    </td>
                    <td data-label="目標價情境報酬" className="r num opp-return">
                      {formatReturn(row.target_return)}
                    </td>
                    <td data-label="損益兩平" className="r num">
                      {row.breakeven === null ? "—" : money(row.breakeven)}
                    </td>
                    <td className="opp-save">
                      <button
                        type="button"
                        className="pbtn sm line"
                        onClick={() => onSave(row)}
                        disabled={savingKey !== null}
                      >
                        {savingKey === key ? "儲存中……" : "存成劇本"}
                      </button>
                      {err && (
                        <div className="notice error" role="alert">
                          {err}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {started && !running && search.rows.length === 0 && search.failures.length > 0 && (
        <p className="caption">這次沒有任何標的產生候選。</p>
      )}

      <NotSelected
        label="共識不夠"
        hint="資料足夠，但沒通過門檻"
        items={weak}
        reasons={(item) => weakReasons(item, data.thresholds)}
      />
      <NotSelected
        label="資料不足"
        hint="資料不足或沒有資料，無法判斷共識"
        items={thin}
        reasons={(item) => [
          STATUS_LABELS[item.status] ?? item.status,
          ...item.reasons.map(reasonText),
        ]}
      />
    </>
  );
}

function weakReasons(
  item: ConsensusItem,
  t: OpportunityConsensusResponse["thresholds"],
): string[] {
  const out: string[] = [];
  if (!item.gate.first) {
    out.push(`分歧度歷史百分位 ${ratioPct(item.percentile)} 高於門檻 ${t.percentile_max}%`);
  }
  if (!item.gate.second) {
    out.push(`分歧度 ${ratioPct(item.dispersion)} 高於門檻 ${t.dispersion_max}%`);
  }
  return out.length > 0 ? out : item.gate.reasons.map(reasonText);
}

function UniverseCard({ data }: { data: OpportunityConsensusResponse }) {
  const u = data.universe;
  const incomplete = (u.coverage.partial ?? 0) + (u.coverage.unknown ?? 0);
  return (
    <section className="card" aria-label="搜尋母體">
      <h2 className="section-title">
        {u.label}
        {u.provisional && <span className="tag warn">暫定</span>}
      </h2>
      <p className="opp-facts">
        <span>共 {u.symbols} 檔</span>
        <span>有資料 {u.with_data} 檔</span>
        <span>資料不足 {u.insufficient} 檔</span>
        <span>資料日 {u.as_of ?? "—"}</span>
      </p>
      {incomplete > 0 && (
        <p className="notice">
          {incomplete} 檔分析師覆蓋不完整（部分或未知），這些股票的共識可能少算了分析師。
        </p>
      )}
      {data.rules.provisional && (
        <p className="caption">資料品質規則目前是暫定值。</p>
      )}
      <p className="opp-thresholds">
        目前門檻：分歧度歷史百分位 ≤ {data.thresholds.percentile_max}%、分歧度 ≤ {data.thresholds.dispersion_max}%
        <a href={opportunitySettingsHash()}>調整門檻</a>
      </p>
    </section>
  );
}

function ItemSummary({ item }: { item: ConsensusItem }) {
  return (
    <>
      <div className="opp-item-head">
        <strong>{item.symbol}</strong>
        <span className="num">平均目標價 {item.mean === null ? "—" : money(item.mean)}</span>
      </div>
      <p className="opp-facts">
        <span>{item.n_analysts} 位分析師</span>
        <span>分歧度 {ratioPct(item.dispersion)}</span>
        <span>歷史百分位 {ratioPct(item.percentile)}</span>
        <span>{item.history_points} 個歷史點</span>
        <span>資料日 {item.as_of ?? "—"}</span>
        {item.coverage && item.coverage !== "complete" && (
          <span>覆蓋{COVERAGE_LABELS[item.coverage] ?? item.coverage}</span>
        )}
      </p>
      {item.refresh_error && (
        <p className="caption">
          最新一次更新失敗（{item.refresh_error.day}），沿用 {item.as_of ?? "上一份"} 的資料。
        </p>
      )}
    </>
  );
}

function NotSelected({
  label, hint, items, reasons,
}: {
  label: string;
  hint: string;
  items: ConsensusItem[];
  reasons: (item: ConsensusItem) => string[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="card" aria-label={label}>
      <h2 className="section-title">
        未入選：{label}（{items.length} 檔）
      </h2>
      <p className="caption">{hint}</p>
      <ul className="opp-list">
        {items.map((item) => (
          <li key={item.symbol} aria-label={item.symbol} className="opp-item">
            <div className="opp-item-head">
              <strong>{item.symbol}</strong>
              {item.mean !== null && (
                <span className="num">平均目標價 {money(item.mean)}</span>
              )}
            </div>
            <ul className="opp-reasons">
              {reasons(item).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <ConsensusDetailToggle symbol={item.symbol} />
          </li>
        ))}
      </ul>
    </section>
  );
}
