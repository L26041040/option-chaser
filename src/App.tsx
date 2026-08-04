/**
 * 主畫面（V3／#51）：劇本庫。V4（#52）在此接上刷新編排。
 *
 * 頂部釘選功能列 → 劇本卡片清單（依最新收益率排序）→ 建立表單。
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
import { useCallback, useEffect, useRef, useState } from "react";

import CreateForm, { type DraftScenario } from "./CreateForm";
import ScenarioDetail from "./ScenarioDetail";
import ScenarioList from "./ScenarioList";
import Toolbar, { type RefreshProgress } from "./Toolbar";
import {
  archiveScenario,
  createScenario,
  listScenarios,
  refreshScenario,
  toFailure,
  type RefreshFailure,
  type ScenarioSummary,
} from "./api";
import { scenarioIdFromHash } from "./route";

export default function App() {
  const [rows, setRows] = useState<ScenarioSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<RefreshProgress | null>(null);
  const [failures, setFailures] = useState<Record<string, RefreshFailure>>({});
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
   *  再逐一刷新。 */
  const reloadAndRefresh = useCallback(async () => {
    const fresh = await reload();
    if (fresh) await enqueue(fresh.map((r) => r.id));
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
    // 不該被後面 N 趟刷新綁住。
    void enqueue([...rowsRef.current.map((r) => r.id), created.id]);
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

  // 詳細頁（V5／#53）。所有 hook 都在這一行之前跑完，順序不受影響。
  if (detailId !== null) return <ScenarioDetail id={detailId} />;

  return (
    <div className="screen">
      <Toolbar
        count={rows.length}
        progress={progress}
        // 時機三：功能列刷新鈕
        onRefresh={() => void reloadAndRefresh()}
      />

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      <ScenarioList
        rows={rows}
        failures={failures}
        now={now}
        onArchive={archive}
        // 重試不是第四種刷新時機——它重跑的就是那一次失敗的刷新，而且
        // 走同一條佇列，不會與進行中的那一輪搶資料源。
        onRetry={(id) => void enqueue([id])}
      />
      <CreateForm onCreate={create} busy={busy} />
    </div>
  );
}
