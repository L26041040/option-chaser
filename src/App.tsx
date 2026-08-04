/**
 * 主畫面（V3／#51）：劇本庫。V4（#52）在此接上刷新編排。
 *
 * 頂部釘選功能列 → 劇本卡片清單（依最新收益率排序）→ 建立表單。
 * 詳細頁是 V5（#53）；在它落地之前，頁面最下方保留 V1 的一次性分析
 * （`DemoAnalysis`），那是目前唯一看得到候選池診斷的地方。
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
import DemoAnalysis from "./DemoAnalysis";
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
          setProgress({ done, total: done + queue.current.length });
          await refreshOne(queue.current.shift()!);
          done += 1;
        }
      } finally {
        running.current = false;
        queue.current = [];
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
    const next = [...rows, created];
    setRows(next);
    setError(null);
    // 時機二：建立劇本後。刻意不 await——表單要立刻清空並可再輸入，
    // 不該被後面 N 趟刷新綁住。
    void enqueue(next.map((r) => r.id));
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
        // 新鮮度以「這次渲染的當下」為基準；刷新完成會重新渲染，提示
        // 因此跟著消失。
        now={new Date()}
        onArchive={archive}
        // 重試不是第四種刷新時機——它重跑的就是那一次失敗的刷新，而且
        // 走同一條佇列，不會與進行中的那一輪搶資料源。
        onRetry={(id) => void enqueue([id])}
      />
      <CreateForm onCreate={create} busy={busy} />
      <DemoAnalysis />
    </div>
  );
}
