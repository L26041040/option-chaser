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

/**
 * `showCreateButton` 與其餘建立相關欄位綁在一起（判別聯合）：桌面版
 * （#75 現狀）傳 `true` 並帶齊三個欄位；手機版（#81）傳 `false`——
 * 建立入口已經在 `Dashboard` 下方的 `CreateEntry`，工具列不重複顯示，
 * 型別上直接讓「傳 false 卻還帶著 createOpen」變成編譯錯誤。
 */
type CreateButtonProps =
  | {
      showCreateButton: true;
      /** 建立劇本表單目前是否展開（#75）。 */
      createOpen: boolean;
      /** 展開鈕控制的面板 id（#75 code review 跟進），與 `CreateForm.tsx`
       *  裡 `MonthPicker` 的 `aria-expanded`＋`aria-controls` 同一套寫法。 */
      createPanelId: string;
      onToggleCreate: () => void;
    }
  | { showCreateButton: false };

export default function Toolbar({
  count,
  busy,
  runSummary,
  onRefresh,
  onOpenTrash,
  onOpenSettings,
  ...createProps
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
   *  「主要工作區右上角」，而這個工具列正在那裡。桌面版不傳：那邊的
   *  指定位置是 sidebar 最下方（見 `App.tsx`），兩邊各放一個會變成同一
   *  個入口出現兩次。 */
  onOpenSettings?: () => void;
  /** TR6（#91）：垃圾桶畫面入口，貼齊「劇本庫」標題的工具列——需求方
   *  核准版面：桌面順序「＋ 建立劇本 → 🗑 垃圾桶 → 重新整理」，手機版
   *  沒有建立鈕（入口在 Dashboard 下方），順序自然是「🗑 垃圾桶 →
   *  重新整理」，兩種寬度共用同一段 JSX，不必分支。 */
  onOpenTrash: () => void;
} & CreateButtonProps) {
  return (
    <header className="toolbar">
      <div className="toolbar-row">
        <h1 className="toolbar-title">劇本庫</h1>
        {/* 動作放在標題列右側的膠囊鈕（iOS 導覽列慣例），不是自成一列的
            整寬按鈕——功能列是釘住的，每多一列就少一列看得到卡片。
            #75：建立劇本原本是掛在全部劇本卡片下面、永遠展開的表單，
            捲過長長的清單才看得到；改成跟刷新同一列的膠囊鈕，兩個主要
            入口位置一致、且跟著這個 `<header>` 一起常駐釘住。這是桌面版
            現狀，手機版（#81）建立入口移到 Dashboard 下方，不重複。 */}
        <div className="toolbar-actions">
          {createProps.showCreateButton && (
            <button className="pill" onClick={createProps.onToggleCreate}
                   aria-expanded={createProps.createOpen}
                   aria-controls={createProps.createPanelId}>
              {createProps.createOpen ? "收合建立表單" : "＋ 建立劇本"}
            </button>
          )}
          <button className="pill pill-trash" onClick={onOpenTrash}>
            <TrashIcon /> 垃圾桶
          </button>
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
