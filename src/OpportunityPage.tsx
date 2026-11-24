/**
 * 機會搜尋頁（OS-05／#394，母票 #389 §5.3–5.4、C13–C14）。
 *
 * 共識清單（只讀全站共識快取）→「搜尋選擇權」對符合條件的股票逐檔跑**既有**
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
 * - 來源關閉（`source.configured=false`）就沒有任何按鈕——不假裝能搜。部署環境
 *   預設啟用真實來源（#397），會走到這裡只有緊急關閉開關生效時，所以文案說
 *   「已關閉」，不說「尚未設定」（LIVE-T5／#401）。
 *   測試資料來源（`is_fixture`）在頁首常駐標示，不隨捲動或狀態消失。
 * - 「停止」是真的不再續跑：已經送出的那一次照樣等它回來並顯示（上游
 *   額度已經花了），之後不再送下一次；剩下的檔留著，可以「繼續搜尋」。
 * - 超過單次上限（`fetch_cap`）的檔不會被默默丟掉：後端放在 `deferred`、
 *   這頁照實說「尚有 N 檔未搜尋」，使用者按鈕才對那些檔發起新的一輪
 *   （同樣受上限約束）——不自動續跑，否則上限形同虛設。
 * - 排序選項的文字由後端給（搜尋回應的 `sort_options`，與設定頁同一份）。
 * - 每個數字都是後端原值，這裡只排序與格式化。V2-06（#408）：成本與最大損失
 *   都同時顯示**每股與每口**（1 口 = 100 股；換算只在 `contractUnits.ts`）——
 *   成本每股＝`entry_cost`、每口＝× 100；最大損失每口＝`max_loss_per_contract`
 *   原值、每股＝÷ 100，不重新計算。劇本詳細頁用同一個 helper 顯示同兩種單位，
 *   存成劇本後兩邊是同一組數字。排序仍用後端原值（只改呈現，名次不變，
 *   `contracts/opportunity_ranking_cases.json` 前後端一起鎖住）。
 * - V2-06（#408）：兩種「漲幅／報酬」分開放——**股票目標漲跌幅**是股票層級，
 *   跟代號、目前股價與報價日期放在「標的」那一格（不參與排序）；**股價達標時
 *   的策略報酬**是策略層級、自己一欄。兩者各有標題與 ⓘ（桌面在表頭；手機版
 *   表頭隱藏，改在區塊頂端的說明列），不共用欄位或標題。
 * - 文案只說「股價達標時的策略報酬」，並固定一句它不是期望值或勝率。
 * - 用語照 #405（V2-03）的定稿對照表；「分歧度歷史排序」以 PR 顯示
 *   （`dispersionRank.ts`，向下取整），篩選仍只看後端的 `gate`。
 * - 來源已設定時，頁首下方是「分析師資料」區塊（`AnalystUpdatePanel`，
 *   LIVE-T3／#398）：更新／重試結束後重讀共識清單。
 * - 共識資料還沒建立（`universe.not_built`，LIVE-T4／#400）：一檔都還沒建立
 *   時「符合條件的股票」區塊只說「資料建立中」、搜尋停用——不顯示「沒有符合條件的股票」的空
 *   結果；部分建立時照常列出並說明還有幾檔在建立中。
 * - 資料狀態（來源、資料日期、已建立／掃描範圍、符合條件）與就緒／建立中／失敗的下一步
 *   都在「分析師資料」區塊（LIVE-T5／#401）；結果表每一列都能打開那一檔的
 *   共識明細（`ResultRow`），與存成劇本並排。
 * - 搜尋失敗與「部分家族沒有結果」（`incomplete`）的訊息由後端組好（引擎
 *   自己對每個策略的原因、基準到期日），這裡照實顯示。
 */
import { useEffect, useRef, useState } from "react";

import AnalystUpdatePanel from "./AnalystUpdatePanel";
import MetricInfo, { MetricHelpRow } from "./MetricInfo";

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
  type OpportunitySearchIncomplete,
  type OpportunitySearchRequest,
  type SortOption,
} from "./api";
import { strategyLabel } from "./detail";
import { FAMILY_LABELS } from "./family";
import { setAuthStatusCache, subscribeAuthStatus } from "./fetchCache";
import ConsensusDetailToggle, {
  ConsensusDetailPanel,
  useConsensusDetail,
} from "./ConsensusDetail";
import { isNotBuilt } from "./consensusUpdate";
import {
  mergeSearchRows,
  opportunityRowKey as rowKey,
  gateFailureReasons,
  rankOpportunities,
  ratioPct,
  reasonText,
  STATUS_LABELS,
  type OpportunitySort,
} from "./opportunity";
import { prLabel, prThresholdLabel } from "./dispersionRank";
import { detailHash, opportunitySettingsHash } from "./route";
import { formatReturn, money } from "./scenarios";
import { costAndMaxLoss, perContractText, perShareText } from "./contractUnits";
import { roleAtLeast, type Role } from "./superuser";
import { priceDateLabel, priceText, upsideText } from "./targetUpside";

export const RETURN_DISCLAIMER =
  "此報酬是『股價在目標月份達到分析師平均目標價時』的策略報酬，不是期望值或勝率";

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
  /** 有結果但缺了某個家族的股票（LIVE-T4／#400）：不是失敗，照實說原因。 */
  incomplete: OpportunitySearchIncomplete[];
  processed: string[];
  total: number;
  remaining: string[];
  /** 超過單次上限、這一輪沒搜的檔（後端 `deferred`）。不自動續跑。 */
  deferred: string[];
  /** 排序選項（含文字）照後端給的；還沒搜過時是空的（下拉選單只在有結果時出現）。 */
  sortOptions: SortOption[];
}

const EMPTY_SEARCH: SearchState = {
  rows: [], failures: [], incomplete: [], processed: [], total: 0, remaining: [],
  deferred: [], sortOptions: [],
};

/** `new`：重新搜尋符合條件的股票；`resume`：接續 `remaining`（同一輪）；
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
            incomplete: [
              ...prev.incomplete.filter((f) => !r.processed.includes(f.symbol)),
              ...(r.incomplete ?? []),
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
          <h2 className="section-title">分析師資料來源已關閉</h2>
          <p className="caption">
            緊急關閉開關生效中：暫停抓取分析師資料，也不能搜尋選擇權。重新開啟後，這裡會恢復資料狀態與搜尋。
          </p>
        </section>
      )}

      {data && data.source.configured && (
        <AnalystUpdatePanel consensus={data}
                            onUpdated={() => setConsensusVersion((v) => v + 1)} />
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
  // 還沒建立的檔（LIVE-T4／#400）不算「資料不足」：它們不是資料有問題，
  // 是還沒抓——在符合條件的股票區塊以「資料建立中」說明，不混進原因清單。
  const thin = data.items.filter((i) => i.status !== "ok" && !isNotBuilt(i));
  const notBuilt = data.universe.not_built ?? 0;
  // 超出每日更新範圍的（`out_of_scope`）不會被建立，不算進「一檔都還沒建立」。
  const nothingBuilt = notBuilt > 0
    && notBuilt >= data.universe.symbols - (data.universe.out_of_scope ?? 0);
  const ranked = rankOpportunities(search.rows, sort);

  return (
    <>
      <UniverseCard data={data} />

      <section className="card" aria-label="符合條件的股票">
        <h2 className="section-title">
          {nothingBuilt ? "符合條件的股票" : `符合條件的股票（${selected.length} 檔）`}
        </h2>
        {nothingBuilt ? (
          <p className="notice" role="status">
            資料建立中：{notBuilt} 檔的分析師資料還沒建立，建立完成後才會知道哪些股票符合條件。請用上方「分析師資料」的「開始建立」。
          </p>
        ) : selected.length === 0 ? (
          <p className="caption">目前沒有同時通過兩道門檻的股票。</p>
        ) : (
          <>
            <MetricHelpRow metrics={CONSENSUS_HELP} />
            <ul className="opp-list">
              {selected.map((item) => (
                <li key={item.symbol} aria-label={item.symbol} className="opp-item">
                  <ItemSummary item={item} />
                  <ConsensusDetailToggle symbol={item.symbol} />
                </li>
              ))}
            </ul>
          </>
        )}

        <div className="opp-actions">
          <button
            type="button"
            className="pbtn"
            onClick={onSearch}
            disabled={running || nothingBuilt || selected.length === 0}
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
        {!nothingBuilt && notBuilt > 0 && (
          <p className="notice" role="status">
            資料建立中：還有 {notBuilt} 檔尚未建立，符合條件的股票可能還沒列全。
          </p>
        )}
        {!nothingBuilt && selected.length === 0 && (
          <p className="caption">沒有符合條件的股票，所以沒有可以搜尋的標的。</p>
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

      {search.incomplete.length > 0 && (
        <section className="card" aria-label="部分家族沒有結果">
          <h2 className="section-title">部分家族沒有結果（{search.incomplete.length} 檔）</h2>
          <ul className="opp-list">
            {search.incomplete.map((f) => (
              <li key={f.symbol} aria-label={f.symbol} className="opp-item">
                <strong>{f.symbol}</strong>
                {f.families.map((family) => (
                  <span key={family} className="tag warn">{FAMILY_LABELS[family] ?? family}</span>
                ))}
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
          {/* 結果表的指標說明列（桌面、手機都顯示）是鍵盤與螢幕報讀器的唯一
              入口。表頭各欄的 ⓘ 只給滑鼠懸停（`decorative`：`aria-hidden`、
              不進 Tab 順序）——按鈕名稱混進 `<th>`，每一格都會被念成
              「成本、最大損失說明」；手機版表頭又是隱藏的。 */}
          <MetricHelpRow metrics={RESULT_HELP} className="opp-help-results" />
          <table className="tbl opp-table">
            <thead>
              <tr>
                <th scope="col" className="opp-th-stock">
                  <span className="opp-th-main">標的</span>
                  <span className="opp-th-sub">
                    <span className="metric-help-item">目前股價<MetricInfo metric="currentPrice" decorative /></span>
                    <span className="metric-help-item">目標漲跌幅<MetricInfo metric="targetUpside" decorative /></span>
                  </span>
                </th>
                <th scope="col">策略</th>
                <th scope="col">履約價</th>
                <th scope="col">到期日</th>
                <th scope="col">目標月份</th>
                <th scope="col" className="r">
                  {COST_LABEL}
                  <MetricInfo metric="costAndMaxLoss" decorative />
                </th>
                <th scope="col" className="r">{MAX_LOSS_LABEL}</th>
                <th scope="col" className="r">
                  {RETURN_LABEL}
                  <MetricInfo metric="scenarioReturn" decorative />
                </th>
                <th scope="col" className="r">損益兩平</th>
                <th scope="col"><span className="sr-only">動作</span></th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((row) => {
                const key = rowKey(row);
                return (
                  <ResultRow
                    key={key}
                    row={row}
                    saving={savingKey === key}
                    saveDisabled={savingKey !== null}
                    error={saveErrors[key]}
                    onSave={() => onSave(row)}
                  />
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
        label="不符合條件"
        hint="資料足夠，但有門檻沒過（下方列出是哪一道）"
        items={weak}
        reasons={(item) => gateFailureReasons(item, data.thresholds)}
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

const RESULT_COLUMNS = 10;
const COST_LABEL = "成本（每股／每口）";
const MAX_LOSS_LABEL = "最大損失（每股／每口）";
const RETURN_LABEL = "股價達標時的策略報酬";

/** V2-04（#406）：清單／結果表每列都重複的數字，說明只在區塊頂端放一次。 */
const CONSENSUS_HELP = [
  "meanTarget", "currentPrice", "targetUpside", "validBrokerCount", "dispersionRate",
  "dispersionRank", "dataDate",
] as const;
const RESULT_HELP = ["currentPrice", "targetUpside", "costAndMaxLoss", "scenarioReturn"] as const;

/**
 * 結果表的一列＋（打開時）它下面的一列共識明細（LIVE-T5／#401）：每一列都能
 * 看到那一檔的共識是怎麼來的，再決定要不要存成劇本。明細列橫跨整張表；
 * 手機版的卡片排版裡同樣是整寬，不出現水平捲動。
 */
function ResultRow({
  row, saving, saveDisabled, error, onSave,
}: {
  row: OpportunityRow;
  saving: boolean;
  saveDisabled: boolean;
  error: string | undefined;
  onSave: () => void;
}) {
  const detail = useConsensusDetail(row.symbol);
  const units = costAndMaxLoss(row);
  return (
    <>
      <tr aria-label={`${row.symbol} ${strategyLabel(row.subtype)}`} data-family={row.family}>
        <td data-label="標的" className="opp-symbol">
          {row.symbol}
          <RowQuote q={row.consensus} />
        </td>
        <td data-label="策略">{strategyLabel(row.subtype)}</td>
        <td data-label="履約價">
          {formatLegs(row.legs)}
        </td>
        <td data-label="到期日">
          {row.expiry}
          <span className="row-note">{expiryDistance(row.buffer_days)}</span>
        </td>
        <td data-label="目標月份">{row.target_month}</td>
        <td data-label={COST_LABEL} className="r num">
          <span className="opp-unit">{perShareText(units.cost.perShare)}</span>
          <span className="opp-unit">{perContractText(units.cost.perContract)}</span>
        </td>
        <td data-label={MAX_LOSS_LABEL} className="r num">
          <span className="opp-unit">{perShareText(units.maxLoss.perShare)}</span>
          <span className="opp-unit">{perContractText(units.maxLoss.perContract)}</span>
        </td>
        <td data-label={RETURN_LABEL} className="r num opp-return">
          {formatReturn(row.target_return)}
        </td>
        <td data-label="損益兩平" className="r num">
          {row.breakeven === null ? "—" : money(row.breakeven)}
        </td>
        <td className="opp-save">
          <div className="opp-row-actions">
            <button
              type="button"
              className="pbtn sm line"
              aria-label={`${row.symbol} 共識詳細資料`}
              aria-expanded={detail.open}
              aria-controls={detail.panelId}
              onClick={detail.toggle}
            >
              {detail.open ? "收起共識" : "共識詳細"}
            </button>
            <button
              type="button"
              className="pbtn sm line"
              onClick={onSave}
              disabled={saveDisabled}
            >
              {saving ? "儲存中……" : "存成劇本"}
            </button>
          </div>
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
        </td>
      </tr>
      {detail.open && (
        <tr className="opp-detail-row" data-detail-for={row.symbol}>
          <td colSpan={RESULT_COLUMNS}>
            <ConsensusDetailPanel symbol={row.symbol} detail={detail} />
          </td>
        </tr>
      )}
    </>
  );
}

/** 結果列「標的」格裡的目前股價／報價日期／目標漲跌幅（V2-05／#407）：
 *  共識更新時存下的報價，不是這次選擇權搜尋的 spot。分三行放，不加寬表格。
 *  這是股票層級的數字（V2-06／#408），跟策略報酬分開，不進排序。 */
function RowQuote({ q }: { q: OpportunityRow["consensus"] }) {
  const hasPrice = q.price !== null && q.price !== undefined;
  return (
    <span className="opp-quote">
      <span>目前股價 {hasPrice ? money(q.price!) : priceText(q)}</span>
      {hasPrice && <span>{priceDateLabel(q)}</span>}
      <span>目標漲跌幅 {upsideText(q)}</span>
    </span>
  );
}

function UniverseCard({ data }: { data: OpportunityConsensusResponse }) {
  const u = data.universe;
  const incomplete = (u.coverage.partial ?? 0) + (u.coverage.unknown ?? 0);
  return (
    <section className="card" aria-label="掃描股票範圍">
      <h2 className="section-title">
        {u.label}
        {u.provisional && <span className="tag warn">暫定</span>}
        <MetricInfo metric="scanUniverse" />
      </h2>
      <p className="opp-facts">
        <span>共 {u.symbols} 檔</span>
        {u.version_date && <span>版本 {u.version_date}</span>}
        <span>有資料 {u.with_data} 檔</span>
        <span>資料不足 {u.insufficient} 檔</span>
        <span>資料日期 {u.as_of ?? "—"}</span>
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
        目前門檻：分歧度歷史排序 {prThresholdLabel(data.thresholds.percentile_max)}、分析師分歧率 ≤ {data.thresholds.dispersion_max}%
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
        <span>有效券商數 {item.n_analysts}</span>
        <span>分析師分歧率 {ratioPct(item.dispersion)}</span>
        <span>分歧度歷史排序 {prLabel(item.percentile)}</span>
        <span>{item.history_points} 個歷史點</span>
        <span>資料日期 {item.as_of ?? "—"}</span>
        <span>目前股價 {priceText(item)}</span>
        <span>目標漲跌幅 {upsideText(item)}</span>
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
        {label}（{items.length} 檔）
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
