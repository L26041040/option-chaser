/**
 * 桌面版劇本庫頁面自己的釘選列（V3／#51；V4／#52 接上刷新與進度；
 * T08／#196 改接 Refresh Run，進行中不再是「第幾個／共幾個」——一輪
 * 刷新是一次批次請求（可能含 Continuation），沒有「正在跑第幾個」這件
 * 事可講，改成跑完後顯示「N 成功／M 失敗」摘要，見 `App.tsx` 的
 * `runSummary`）。
 *
 * **OG-09（#319）起桌面專屬**：垃圾桶／設定兩個入口（原本的
 * `onOpenTrash`／`onOpenSettings` 選填 prop）已隨手機版換裝為
 * `MobileTopBar`＋既有 `BottomNav` 而整個退場——這裡是唯一呼叫端
 * （桌面 `App.tsx`）也從未傳過這兩個值，OG-02（#318）起桌面的垃圾桶／
 * 設定導覽早就收進常駐的 `TopBar`；本票確認手機版同樣改用 `BottomNav`
 * 後，兩個 prop 在全站沒有任何呼叫端會傳，移除死碼。剩下的
 * 「N 個劇本」＋重新整理是桌面劇本庫頁面目前唯一還沒被 `TopBar`
 * 收編的部分（擺位最終由 OG-03 決定）。
 *
 * 刷新是全站三種時機之一（另兩種是開站與建立劇本）。
 */
export default function Toolbar({
  count,
  busy,
  runSummary,
  onRefresh,
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
}) {
  return (
    <header className="toolbar">
      <div className="toolbar-row">
        <h1 className="toolbar-title">劇本庫</h1>
        <div className="toolbar-actions">
          <button className="pill" onClick={onRefresh} disabled={busy}>
            {busy ? "刷新中……" : "重新整理"}
          </button>
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
