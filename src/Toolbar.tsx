/**
 * 釘選功能列（V3／#51）：捲動時常駐頁面頂部。
 *
 * 刷新鈕與進度顯示在這一票只是**佔位**——真正的刷新流程、進度與失敗
 * 指引是 V4（#52）。佔位鈕刻意 disabled 並說明原因，而不是畫一顆按下去
 * 沒反應的按鈕：一顆看起來能按、按了沒事的按鈕比沒有按鈕更糟。
 */
export default function Toolbar({ count }: { count: number }) {
  return (
    <header className="toolbar">
      <div className="toolbar-row">
        <h1 className="toolbar-title">劇本庫</h1>
        <span className="caption">{count} 個</span>
      </div>
      <button className="button subtle" disabled title="刷新功能於 V4 接上">
        重新整理（尚未接上）
      </button>
    </header>
  );
}
