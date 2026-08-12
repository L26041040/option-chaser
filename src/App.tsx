/**
 * 主畫面（V3／#51）：劇本庫。V4（#52）在此接上刷新編排。
 *
 * 桌面與手機是兩套 responsive layout（MVP-v2／#77 §8），共用同一份資料
 * 與狀態、各自的版面結構：
 * - 桌面（#72／#75）：頂部釘選功能列（含建立入口）→ 建立表單 →
 *   劇本卡片清單（`ScenarioList`，#108 起改用與手機版同一套 compact
 *   row 密度），左側常駐、右側是詳細頁。
 * - 手機（#81／#82）：Dashboard 佔位 → 就地展開的新增劇本入口 → 高密度
 *   劇本清單（`CompactScenarioList`，三層 compact row，依最新收益率
 *   排序、紅燈沉底），點卡片整頁替換成詳細頁。
 *
 * 兩套清單元件刻意分開、不共用同一個渲染路徑：`ScenarioList.tsx`
 * 只服務桌面、`CompactScenarioList.tsx` 只服務手機——這樣手機版的密度
 * 改動在結構上不可能牽動桌面版現狀（spec #77 硬紅線一）。
 *
 * 點卡片進詳細頁（`ScenarioDetail`，V5／#53）；V1 的一次性分析畫面
 * 隨詳細頁落地一併移除，候選池診斷搬進詳細頁。
 *
 * 刷新時機只有三種（沿用 QA1-07／#34 的既有裁示）：開站、建立劇本後、
 * 功能列的刷新鈕。卡片上的「重試」不是第四種——它重跑的是**那一次
 * 失敗的刷新**，範圍是單一劇本。
 *
 * 這一層只做編排與狀態：排序、格式化在 `./scenarios`，驗證在
 * `./CreateForm`，金融計算全部在後端引擎。
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import CompactScenarioList from "./CompactScenarioList";
import CreateEntry from "./CreateEntry";
import CreateForm, {
  type DraftScenario,
  type EditTarget,
} from "./CreateForm";
import Dashboard from "./Dashboard";
import ScenarioDetail from "./ScenarioDetail";
import ScenarioList from "./ScenarioList";
import Settings from "./Settings";
import Toolbar, { type RefreshProgress } from "./Toolbar";
import TrashView from "./TrashView";
import { GearIcon } from "./icons";
import {
  archiveScenario,
  createScenario,
  editScenario,
  listScenarios,
  refreshScenario,
  toFailure,
  type RefreshFailure,
  type ScenarioSummary,
} from "./api";
import {
  isSettingsHash,
  isTrashHash,
  scenarioIdFromHash,
  settingsHash,
  trashHash,
} from "./route";

// 桌面／手機斷點——與 `styles.css` 的 `@media (min-width: 1100px)` 同一個
// 數字，兩邊各自維護一份（CSS 沒辦法直接讀 JS 常數），改動時要一起改。
// 1100 不是隨手取的：`styles.css` 的 20/80 版面下限（220px）恰好是
// 1100 的 20%，斷點與下限彼此對齊，比例才會在整個桌面寬度範圍內都
// 貼近「約 20%」，而不是被下限卡死在一個更寬的固定值上。
const DESKTOP_QUERY = "(min-width: 1100px)";

/**
 * 桌面版真正的 master/detail（#72）：桌面寬度下劇本庫常駐、詳細頁另開
 * 一欄；手機寬度維持既有的整頁替換。用 `matchMedia` 而不是只用 CSS
 * 隱藏——手機版「選了劇本後建立表單／劇本庫不在畫面上」是既有行為
 * 的一部分，CSS `display:none` 只藏視覺，元件仍會掛載並佔用資源。
 */
function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => window.matchMedia(DESKTOP_QUERY).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY);
    const sync = () => setIsDesktop(mql.matches);
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);
  return isDesktop;
}

export default function App() {
  const [rows, setRows] = useState<ScenarioSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<RefreshProgress | null>(null);
  const [failures, setFailures] = useState<Record<string, RefreshFailure>>({});
  // #75：建立劇本表單預設收合，靠工具列的膠囊鈕展開／收合——不再是
  // 掛在全部劇本卡片下面、永遠展開的表單。
  const [showCreateForm, setShowCreateForm] = useState(false);
  // #132：非 null ＝表單現在是編輯模式。編輯沿用同一張表單，不另開一套。
  const [editing, setEditing] = useState<EditTarget | null>(null);
  // code review 跟進：面板一律掛著、用 `hidden` 屬性切換可見度，不是
  // 條件渲染整個卸載重掛——否則使用者打到一半不小心點到收合鈕，剛打的
  // 字就白打了。`hidden` 原生語意會連帶讓輔助技術忽略內容，不必額外
  // 補 `aria-hidden`。`aria-controls` 沿用 `MonthPicker`（同檔案）
  // 既有的「展開鈕指向自己控制的面板」寫法，兩處手法一致。
  const createPanelId = useId();
  // 刷新是「一條佇列、一個跑者」：同時跑兩輪只會讓同一批劇本各被抓
  // 兩次、進度互相蓋掉。用佇列而不是「進行中就不理」——三種時機會重疊
  // （開站那一輪還沒跑完就建立了劇本），直接丟掉的話新劇本會靜靜地
  // 永遠停在「尚未分析」。
  const queue = useRef<string[]>([]);
  const running = useRef(false);
  // 事件處理器裡拿得到「此刻」的 rows：狀態閉包停在該次渲染，而刷新
  // 佇列隨時在更新 rows。
  const rowsRef = useRef<ScenarioSummary[]>(rows);
  rowsRef.current = rows;

  const reload = useCallback(async (): Promise<ScenarioSummary[] | null> => {
    try {
      const fresh = await listScenarios();
      setRows(fresh);
      setError(null);
      return fresh;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, []);

  /** 刷新單一劇本。失敗只記在那張卡上，不中斷整輪。 */
  const refreshOne = useCallback(async (id: string) => {
    try {
      const row = await refreshScenario(id);
      setRows((prev) => prev.map((r) => (r.id === id ? row : r)));
      setFailures((prev) => {
        if (!(id in prev)) return prev;
        const { [id]: _gone, ...rest } = prev;
        return rest;
      });
    } catch (e) {
      setFailures((prev) => ({ ...prev, [id]: toFailure(e) }));
    }
  }, []);

  /**
   * 排入刷新佇列並確保有人在跑。依序（不併發）：一次一趟網路往返，
   * 進度才有意義，也不會同時對資料源打 N 個請求。
   *
   * 跑到一半被追加的劇本會一起跑完，總數隨之變大——那是實話，好過
   * 讓進度停在一個早就不對的分母上。
   */
  const enqueue = useCallback(
    async (ids: string[]) => {
      for (const id of ids) {
        if (!queue.current.includes(id)) queue.current.push(id);
      }
      if (running.current || queue.current.length === 0) return;

      running.current = true;
      let done = 0;
      try {
        while (queue.current.length > 0) {
          // 1-based：顯示的是「正在跑第幾個」，不是「跑完幾個」——
          // 功能列寫的是「第幾個／共幾個」。
          setProgress({ current: done + 1, total: done + queue.current.length });
          await refreshOne(queue.current.shift()!);
          done += 1;
        }
      } finally {
        // 刻意不清空佇列：真有東西沒跑完（例如迴圈裡爆了），留著讓下一次
        // enqueue 接手，而不是照著「不靜靜丟掉」的註解反其道而行。
        running.current = false;
        setProgress(null);
      }
    },
    [refreshOne],
  );

  /** 時機一與時機三共用：先取回最新清單（別台裝置可能加過劇本），
   *  再逐一刷新。
   *
   * 目標月已過完的劇本（#68）不排進去——後端 `refresh` 端點本身也會擋
   * （唯一真正的擋點，任何入口都繞不過），這裡先篩掉純粹是不浪費一趟
   * 網路往返，讓進度的分母從一開始就是對的。
   */
  const reloadAndRefresh = useCallback(async () => {
    const fresh = await reload();
    if (fresh) await enqueue(fresh.filter((r) => !r.expired).map((r) => r.id));
  }, [reload, enqueue]);

  // 時機一：開站。只跑一次——`StrictMode` 在開發模式下會把 effect 跑
  // 兩遍，沒有這道閘的話每個劇本開站就被分析兩次（各一趟抓鏈＋一次引擎
  // 計算），而且畫面會出現兩輪進度。
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void reloadAndRefresh();
  }, [reloadAndRefresh]);

  // 網址 hash ＝ 目前在哪一頁（見 `./route`）。監聽 hashchange 而不是
  // 自己記狀態，返回手勢與返回鍵才會如使用者預期地運作。
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const sync = () => setHash(window.location.hash);
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const detailId = scenarioIdFromHash(hash);
  // TR6（#91）：垃圾桶畫面路由——跟詳細頁同一套 hash 慣例。
  const showTrash = isTrashHash(hash);
  // Settings（#124）：同一套 hash 慣例。
  const showSettings = isSettingsHash(hash);
  const isDesktop = useIsDesktop();

  // 手機版返回劇本庫要停在原本的捲動位置（MVP-v2／#77、#83）：手機版
  // 進詳細頁時劇本庫整個卸載（#72 既有行為，桌面版兩欄常駐、不會卸載、
  // 不需要這段），瀏覽器不會自己記得「回來後要停在哪」。
  //
  // 記錄與還原分成兩個獨立 effect：記錄用一般 `useEffect` 掛
  // `scroll` 監聽器，只在「手機版、劇本庫本身在畫面上」時才掛著，隨時
  // 把最新捲動位置寫進 ref；還原用 `useLayoutEffect`（在瀏覽器繪製前
  // 同步跑），在剛從詳細頁回到劇本庫的那一刻把捲動位置調回去，避免先
  // 畫出「捲到頂」的一瞬間再跳過去的閃爍。
  const libraryScrollY = useRef(0);
  useEffect(() => {
    if (isDesktop || detailId !== null) return;
    const onScroll = () => {
      libraryScrollY.current = window.scrollY;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isDesktop, detailId]);
  useLayoutEffect(() => {
    if (isDesktop || detailId !== null) return;
    window.scrollTo(0, libraryScrollY.current);
  }, [isDesktop, detailId]);

  // 新鮮度會隨時間變舊，所以「現在」要自己走。只在渲染時取一次的話，
  // 頁面開著放到隔天，那份 12 小時前的資料永遠不會長出「舊資料」標記
  // ——而那正是最需要它的情況。門檻是 12 小時，5 分鐘一跳綽綽有餘。
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 5 * 60_000);
    return () => clearInterval(tick);
  }, []);

  async function create(draft: DraftScenario) {
    setBusy(true);
    let created: ScenarioSummary;
    try {
      // 建立端點回傳的形狀與清單列相同，直接併進畫面——不必為了看到
      // 剛建立的那一張卡再打一次清單。
      created = await createScenario(draft);
    } finally {
      setBusy(false);
    }
    // 函式式更新，不是 `[...rows, created]`：`rows` 是 await 之前那次
    // 渲染的閉包，而建立的這段期間刷新佇列很可能正在跑並且已經
    // `setRows` 過——用舊陣列蓋回去會把剛刷新好的卡片打回未分析的樣子。
    // 與 `archive()` 的回滾同一個道理，做法要一致。
    setRows((prev) => [...prev, created]);
    setError(null);
    // 時機二：建立劇本後。刻意不 await——表單要立刻清空並可再輸入，
    // 不該被後面 N 趟刷新綁住。既有清單裡目標月已過完的劇本（#68）
    // 一併篩掉——剛建立的這個不可能過期（後端建立時就擋了），不必篩。
    void enqueue([
      ...rowsRef.current.filter((r) => !r.expired).map((r) => r.id),
      created.id,
    ]);
  }

  /** 點卡片上的編輯：把原資料交給既有表單並展開它。 */
  function startEdit(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setEditing({
      id: row.id, symbol: row.symbol, target_price: row.target_price,
      target_month: row.target_month, best_price: row.best_price,
      worst_price: row.worst_price,
    });
    setShowCreateForm(true);
    setError(null);
  }

  /** 取消：**隨時**可按。只丟掉表單狀態，不寫入任何東西、不動原劇本。
   *  表單的預填 effect 會在 `editing` 變回 null 時把欄位清空並回到建立
   *  模式，所以這裡不需要（也不該）自己去碰那些欄位。 */
  function cancelEdit() {
    setEditing(null);
    setShowCreateForm(false);
  }

  async function saveEdit(id: string, draft: DraftScenario) {
    setBusy(true);
    let updated: ScenarioSummary;
    try {
      updated = await editScenario(id, draft);
    } finally {
      setBusy(false);
    }
    // 函式式更新：編輯這段期間刷新佇列很可能正在跑並且已經 setRows 過。
    setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    setEditing(null);
    setShowCreateForm(false);
    setError(null);
    // thesis 改了的話後端已經清掉舊結果（#132），這裡把它重新分析一次
    // ——沿用既有的單一佇列，不是第四種刷新管道。
    void enqueue([id]);
  }

  async function archive(id: string) {
    // 樂觀移除：封存是軟刪除，後端保留資料與紀錄，畫面先反應。失敗時
    // 把它放回去並說明原因——不能讓一張其實還在的卡片就這樣消失。
    //
    // 回滾只還原**那一列**，而不是把整份陣列存起來蓋回去：存整份的話，
    // 「封存 A（未回應）→ 封存 B（成功）→ A 失敗」會讓已封存的 B 復活，
    // 「封存 A（未回應）→ 建立 C → A 失敗」會讓剛建好的 C 消失。
    const removed = rows.find((r) => r.id === id);
    setRows((prev) => prev.filter((r) => r.id !== id));
    try {
      await archiveScenario(id);
    } catch (e) {
      if (removed) {
        setRows((prev) =>
          prev.some((r) => r.id === id) ? prev : [...prev, removed]);
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  /**
   * TR4（#92）：垃圾桶還原後把那個劇本交回主清單。`TrashView` 自己的
   * 清單狀態獨立於這裡的 `rows`（它是另一個畫面、另一份資料），還原
   * 成功不會自動同步，得靠這個回呼把資料交回去——`TrashView` 呼叫
   * 還原端點前本來就已經有那一列完整資料，不必為此再打一次清單查詢。
   * 函式式更新＋去重（`some` 檢查）：跟 `create()` 同一個理由，`rows`
   * 可能在還原這段期間被進行中的刷新佇列更新過。
   */
  function restoreFromTrash(row: ScenarioSummary) {
    // `archived_at` 清空：`row` 是從 `TrashView` 的封存清單讀來的，
    // 還帶著封存時間戳；還原成功後後端已經清掉它，主清單這份副本也
    // 得跟著清掉，否則主清單裡會混進一列「archived_at 非 null 但其實
    // 沒被封存」的過期資料。
    const restored: ScenarioSummary = { ...row, archived_at: null };
    setRows((prev) =>
      (prev.some((r) => r.id === restored.id) ? prev : [...prev, restored]));
  }

  // ---------- 批次選取移入垃圾桶（TR6／#91） ----------
  //
  // 沒有新增後端批次端點：依序（不併發）呼叫既有單筆 `/archive`，跟
  // `enqueue` 刷新佇列同一種「一次一趟網路往返」的理由——批次操作本身
  // 不搶進行中的刷新佇列（archive 與 refresh 是不同端點，天生不衝突，
  // 這裡的序列只是不讓 N 個請求同時炸出去）。每完成一筆就立刻從畫面
  // 移除那一列，個別失敗不中斷其餘筆——跟單筆 `archive()` 的樂觀更新
  // 同一個原則，只是失敗時不回滾（使用者仍在選取模式裡，看得到哪些
  // 還留著、旁邊的錯誤說明解釋為什麼）。
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchArchiveErrors, setBatchArchiveErrors] =
    useState<Record<string, string>>({});

  function enterSelectMode() {
    setSelectMode(true);
    setSelectedIds(new Set());
    setBatchArchiveErrors({});
  }

  function cancelSelectMode() {
    setSelectMode(false);
    setSelectedIds(new Set());
    setBatchArchiveErrors({});
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function confirmBatchArchive() {
    const ids = [...selectedIds];
    const errors: Record<string, string> = {};
    for (const id of ids) {
      try {
        await archiveScenario(id);
        setRows((prev) => prev.filter((r) => r.id !== id));
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      } catch (e) {
        errors[id] = e instanceof Error ? e.message : String(e);
      }
    }
    // 全部成功才自動離開選取模式——有失敗的話留在選取模式裡，讓使用者
    // 看得到哪些還沒處理成功、為什麼，而不是靜靜地退出、下次得自己
    // 重新想起哪些沒成功。
    if (Object.keys(errors).length === 0) {
      setSelectMode(false);
      setBatchArchiveErrors({});
    } else {
      setBatchArchiveErrors(errors);
    }
  }

  // 詳細頁（V5／#53）。所有 hook 都在這一行之前跑完，順序不受影響。
  // 手機寬度維持既有行為：整頁替換成詳細頁，劇本庫（含建立表單）
  // 整個不掛載。桌面寬度改走下面 #72 的 master/detail 版面。
  const detailProps = detailId !== null ? {
    id: detailId,
    // 把該劇本在清單上的資料時間一起交出去：開站那輪刷新完成後它會變，
    // 詳細頁據此重新取一次，直接開詳細頁網址的人才不會停在舊快照上。
    refreshedAt: rows.find((r) => r.id === detailId)?.latest_analyzed_at ?? null,
    // #70：詳細頁的刷新走 App 既有的那條單一佇列——`busy` 沿用
    // `Toolbar` 同一個判準（任何刷新進行中都算），`onRefresh` 就是
    // `enqueue([這個劇本])`，不是另開一條管道。
    busy: progress !== null,
    failure: failures[detailId],
    onRefresh: () => void enqueue([detailId]),
  } : null;

  // TR6（#91）：批次移入垃圾桶時個別失敗的說明——列在「哪個劇本、
  // 為什麼」，不是只說「有些失敗了」。手機／桌面共用同一段生成邏輯，
  // 各自决定放在畫面的哪裡。
  const batchArchiveErrorNotice = Object.keys(batchArchiveErrors).length > 0 && (
    <div className="notice error" role="alert">
      {Object.entries(batchArchiveErrors).map(([id, message]) => {
        const who = rows.find((r) => r.id === id)?.symbol ?? id;
        return <p key={id} className="caption">{who}：{message}</p>;
      })}
    </div>
  );

  // 手機版：設定是整頁替換（跟垃圾桶、詳細頁同樣的既有模式）。排在
  // 垃圾桶之前只是順序，兩個 hash 互斥。
  if (!isDesktop && showSettings) {
    return <Settings />;
  }

  if (!isDesktop && showTrash) {
    return <TrashView onRestore={restoreFromTrash} />;
  }

  if (!isDesktop && detailProps) {
    return <ScenarioDetail {...detailProps} />;
  }

  if (!isDesktop) {
    // 手機首頁（MVP-v2／#77、#81、#82）：Dashboard 佔位 → 就地展開的
    // 新增劇本入口 → 高密度劇本庫，由上而下三段。與桌面版（下方
    // `library`）是兩個獨立的 JSX 分支，不共用同一段標記——這樣手機版
    // 的版面決定不會意外牽動桌面版現狀（#72／#75，spec #77 硬紅線一）。
    //
    // 工具列不重複顯示建立入口（`showCreateButton={false}`）：入口已經
    // 在下面的 `CreateEntry`，兩個地方各放一次只會讓人不確定該點哪個。
    return (
      <div className="screen">
        <Toolbar
          count={rows.length}
          progress={progress}
          showCreateButton={false}
          // 時機三：功能列刷新鈕
          onRefresh={() => void reloadAndRefresh()}
          onOpenTrash={() => { window.location.hash = trashHash(); }}
          // #124：手機版的設定入口＝工作區右上角的齒輪。桌面版不傳這個
          // 回呼，它的入口在 sidebar 最下方。
          onOpenSettings={() => { window.location.hash = settingsHash(); }}
        />

        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {batchArchiveErrorNotice}

        <Dashboard />

        {/* #81：手機版專屬的建立入口，位置固定在 Dashboard 下方、劇本庫
            上方——不是桌面版工具列膠囊鈕的重複，是同一個 `showCreateForm`
            狀態的另一個進入點（切換裝置寬度時開合狀態不會跟著重置）。 */}
        <CreateEntry
          open={showCreateForm}
          panelId={createPanelId}
          onToggle={() => setShowCreateForm((v) => !v)}
        >
          <CreateForm onCreate={create} onSaveEdit={saveEdit}
                    onCancelEdit={cancelEdit} editing={editing}
                    busy={busy} today={now} />
        </CreateEntry>

        {/* #82：券商 App 式的高密度三層 compact row，取代大卡片——一個
            手機螢幕能掃過多個劇本。下方 `library` 的 `ScenarioList` 是
            完全獨立的元件與渲染路徑，這裡的手機密度改動不會結構性牽動
            它（#108 起兩者視覺密度趨同純屬各自沿用同一組 CSS class，
            不是共用了元件）。 */}
        <CompactScenarioList
          rows={rows}
          failures={failures}
          now={now}
          onArchive={archive}
          onEdit={startEdit}
          // 重試不是第四種刷新時機——它重跑的就是那一次失敗的刷新，而且
          // 走同一條佇列，不會與進行中的那一輪搶資料源。
          onRetry={(id) => void enqueue([id])}
          selectMode={selectMode}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelected}
          onEnterSelectMode={enterSelectMode}
          onCancelSelectMode={cancelSelectMode}
          onConfirmBatchArchive={() => void confirmBatchArchive()}
        />
      </div>
    );
  }

  // 桌面版（#72／#75 現狀，MVP-v2／#77 手機施工不動它）：頂部釘選功能列
  // （含建立入口）→ 建立表單 → 劇本卡片清單。
  // TR6（#91）：垃圾桶開著時，左側面板內容整個換成 `TrashView`（需求方
  // 核准版面 D2），右側 `detail-pane` 邏輯完全不動——跟現有「選劇本
  // 切換右側」的機制平行、不衝突。
  const library = showTrash ? <TrashView onRestore={restoreFromTrash} /> : (
    <div className="screen">
      <Toolbar
        count={rows.length}
        progress={progress}
        showCreateButton
        createOpen={showCreateForm}
        createPanelId={createPanelId}
        onToggleCreate={() => setShowCreateForm((v) => !v)}
        // 時機三：功能列刷新鈕
        onRefresh={() => void reloadAndRefresh()}
        onOpenTrash={() => { window.location.hash = trashHash(); }}
      />

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {batchArchiveErrorNotice}

      {/* #75：建立劇本收攏成工作區正上方的入口——跟著工具列一起釘住，
          不再是掛在全部劇本卡片下面、永遠展開、得捲過整份清單才看得到
          的表單。一律掛著、用 `hidden` 切換可見度（見上方 `createPanelId`
          註解），因此永遠排在 `ScenarioList` 之前，不會因為開／關而
          改變它在畫面結構上「在清單上方」這件事。年月選擇器（#71）的
          「今年」／「本月」跟全站同一個時鐘——不讓它自己另外算一次
          `new Date()`，那樣會跟 `ScenarioList` 的新鮮度判斷用著兩個
          不同步的「現在」。 */}
      <div id={createPanelId} hidden={!showCreateForm}>
        <CreateForm onCreate={create} onSaveEdit={saveEdit}
                    onCancelEdit={cancelEdit} editing={editing}
                    busy={busy} today={now} />
      </div>

      <ScenarioList
        rows={rows}
        failures={failures}
        now={now}
        onArchive={archive}
        onEdit={startEdit}
        // 重試不是第四種刷新時機——它重跑的就是那一次失敗的刷新，而且
        // 走同一條佇列，不會與進行中的那一輪搶資料源。
        onRetry={(id) => void enqueue([id])}
        // #72：桌面版清單裡標出目前選中的劇本；手機版此時本來就不會
        // 渲染這份清單（上面已整頁替換掉），傳了也無害。
        selectedId={detailId}
        selectMode={selectMode}
        selectedIds={selectedIds}
        onToggleSelect={toggleSelected}
        onEnterSelectMode={enterSelectMode}
        onCancelSelectMode={cancelSelectMode}
        onConfirmBatchArchive={() => void confirmBatchArchive()}
      />
    </div>
  );

  // #72：桌面版真正的 master/detail——左側劇本庫常駐，右側是詳細頁；
  // 沒選劇本時右側顯示空狀態，而不是留白或報錯。
  // #124：桌面版的設定入口固定在 sidebar **最下方**——清單本身在
  // `.library-scroll` 裡自己捲動，這個連結因此永遠看得到，不必先捲到
  // 劇本清單的底部。設定內容顯示在右側工作區（`.detail-pane`），與
  // 「選劇本切換右側」是同一個機制。
  return (
    <div className="workspace">
      <div className="library-pane">
        <div className="library-scroll">{library}</div>
        <a
          className={`sidebar-settings${showSettings ? " active" : ""}`}
          href={settingsHash()}
        >
          <GearIcon /> 設定
        </a>
      </div>
      <div className="detail-pane">
        {showSettings ? (
          <Settings />
        ) : detailProps ? (
          <ScenarioDetail {...detailProps} />
        ) : (
          <div className="screen">
            <p className="caption">選擇左側的劇本查看詳細內容。</p>
          </div>
        )}
      </div>
    </div>
  );
}
