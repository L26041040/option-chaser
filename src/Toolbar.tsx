/**
 * 釘選功能列（V3／#51；V4／#52 接上刷新與進度；MVP-v2／#77、#81 起
 * 建立入口在手機版搬到 Dashboard 下方，工具列本身不再重複一份；
 * T08／#196 改接 Refresh Run，進行中不再是「第幾個／共幾個」——一輪
 * 刷新是一次批次請求（可能含 Continuation），沒有「正在跑第幾個」這件
 * 事可講，改成跑完後顯示「N 成功／M 失敗」摘要，見 `App.tsx` 的
 * `runSummary`）。
 *
 * 刷新是全站三種時機之一（另兩種是開站與建立劇本）。
 */
import { GearIcon, TrashIcon } from "./icons";

export default function Toolbar({
  count,
  busy,
  runSummary,
  onRefresh,
  onOpenTrash,
  onOpenSettings,
}: {
  count: number;
  /** 有任何刷新（Refresh Run 或單一劇本刷新）進行中——沿用既有「一條
   *  忙碌狀態」判準，不分是哪一種刷新觸發的（`App.tsx` 的 `refreshBusy`，
   *  由 `updatingIds.size > 0` 導出）。 */
  busy: boolean;
  /** 上一輪 Refresh Run 結束後的「N 成功／M 失敗」摘要（T08／#196
   *  P2）——`null` 表示還沒有任何一輪跑完過，或正在跑（`busy` 時優先
   *  顯示「更新中」，不與舊摘要並存混淆）。 */
  runSummary: string | null;
  onRefresh: () => void;
  /** 設定入口（Settings／#124）。**只有手機版傳**——需求方指定的位置是
   *  「主要工作區右上角」，而這個工具列正在那裡。桌面版不傳：OG-02
   *  （#318）起設定入口在常駐 `TopBar` 導覽（見 `App.tsx`），兩邊各放
   *  一個會變成同一個入口出現兩次。 */
  onOpenSettings?: () => void;
  /** TR6（#91）：垃圾桶畫面入口，貼齊「劇本庫」標題的工具列——手機版
   *  沒有建立鈕（入口在 Dashboard 下方），順序自然是「🗑 垃圾桶 →
   *  重新整理」，一律傳。OG-02（#318）起**選填**：桌面版垃圾桶／建立
   *  劇本入口已搬進常駐的 `TopBar` 導覽，這裡再放一份同樣的入口只是
   *  重複，桌面呼叫端因此不再傳這個 prop——手機呼叫端維持原樣不動，
   *  型別放寬不改變手機版任何既有行為。 */
  onOpenTrash?: () => void;
}) {
  return (
    <header className="toolbar">
      <div className="toolbar-row">
        <h1 className="toolbar-title">劇本庫</h1>
        {/* 動作放在標題列右側的膠囊鈕（iOS 導覽列慣例），不是自成一列的
            整寬按鈕——功能列是釘住的，每多一列就少一列看得到卡片。
            OG-02（#318）起：建立劇本入口已不在這裡（手機版在 Dashboard
            下方的 `CreateEntry`，桌面版在常駐 `TopBar`），這個工具列
            只剩垃圾桶（選填，見 `onOpenTrash` 說明）與重新整理。 */}
        <div className="toolbar-actions">
          {onOpenTrash && (
            <button className="pill pill-trash" onClick={onOpenTrash}>
              <TrashIcon /> 垃圾桶
            </button>
          )}
          <button className="pill" onClick={onRefresh} disabled={busy}>
            {busy ? "刷新中……" : "重新整理"}
          </button>
          {/* 齒輪排在最右——需求方指定的「工作區右上角」。圖示本身
              `aria-hidden`，可及名稱交給 `aria-label`（沿用既有慣例）。 */}
          {onOpenSettings && (
            <button className="icon-button" onClick={onOpenSettings}
                   aria-label="設定">
              <GearIcon />
            </button>
          )}
        </div>
      </div>
      <div className="toolbar-row">
        <span className="caption">{count} 個劇本</span>
        {/* role="status"：螢幕閱讀器會唸出變化，而不是讓使用者自己不斷
            回頭看畫面。進行中優先顯示「更新中」（不論是 Refresh Run 或
            單一劇本刷新），跑完才換成上一輪的「N 成功／M 失敗」摘要——
            兩者互斥，不會同時出現造成「這句話是現在還是剛才」的混淆。 */}
        {busy ? (
          <span className="caption progress" role="status">更新中……</span>
        ) : runSummary && (
          <span className="caption progress" role="status">{runSummary}</span>
        )}
      </div>
    </header>
  );
}
