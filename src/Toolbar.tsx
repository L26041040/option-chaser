/**
 * 釘選功能列（V3／#51；V4／#52 接上刷新與進度）。
 *
 * 刷新是全站三種時機之一（另兩種是開站與建立劇本）。進行中顯示
 * 「第幾個／共幾個」——刷新是逐一跑的，一個劇本一趟網路往返，只給一顆
 * 轉圈的話使用者無從判斷是快好了還是卡住了。
 */
export interface RefreshProgress {
  /** 正在刷新第幾個（1-based）。 */
  current: number;
  total: number;
}

export default function Toolbar({
  count,
  progress,
  onRefresh,
}: {
  count: number;
  progress: RefreshProgress | null;
  onRefresh: () => void;
}) {
  const busy = progress !== null;
  return (
    <header className="toolbar">
      <div className="toolbar-row">
        <h1 className="toolbar-title">劇本庫</h1>
        {/* 動作放在標題列右側的膠囊鈕（iOS 導覽列慣例），不是自成一列的
            整寬按鈕——功能列是釘住的，每多一列就少一列看得到卡片。 */}
        <button className="pill" onClick={onRefresh} disabled={busy}>
          {busy ? "刷新中……" : "重新整理"}
        </button>
      </div>
      <div className="toolbar-row">
        <span className="caption">{count} 個劇本</span>
        {/* 進度用 role="status"：螢幕閱讀器會唸出變化，而不是讓使用者
            自己不斷回頭看畫面。 */}
        {progress && (
          <span className="caption progress" role="status">
            {progress.current}/{progress.total}
          </span>
        )}
      </div>
    </header>
  );
}
