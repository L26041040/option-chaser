/**
 * 主畫面（V3／#51）：劇本庫。
 *
 * 頂部釘選功能列 → 劇本卡片清單（依最新收益率排序）→ 建立表單。
 * 詳細頁是 V5（#53）；在它落地之前，頁面最下方保留 V1 的一次性分析
 * （`DemoAnalysis`），那是目前唯一看得到候選池診斷的地方。
 *
 * 這一層只做編排與狀態：排序、格式化在 `./scenarios`，驗證在
 * `./CreateForm`，金融計算全部在後端引擎。
 */
import { useCallback, useEffect, useState } from "react";

import CreateForm, { type DraftScenario } from "./CreateForm";
import DemoAnalysis from "./DemoAnalysis";
import ScenarioList from "./ScenarioList";
import Toolbar from "./Toolbar";
import {
  archiveScenario,
  createScenario,
  listScenarios,
  type ScenarioSummary,
} from "./api";

export default function App() {
  const [rows, setRows] = useState<ScenarioSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setRows(await listScenarios());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function create(draft: DraftScenario) {
    setBusy(true);
    try {
      // 建立端點回傳的形狀與清單列相同，直接併進畫面——不必為了看到
      // 剛建立的那一張卡再打一次清單。
      const created = await createScenario(draft);
      setRows((prev) => [...prev, created]);
      setError(null);
    } finally {
      setBusy(false);
    }
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
      <Toolbar count={rows.length} />

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      <ScenarioList rows={rows} onArchive={archive} />
      <CreateForm onCreate={create} busy={busy} />
      <DemoAnalysis />
    </div>
  );
}
