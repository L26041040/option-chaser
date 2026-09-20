/**
 * 手機頂欄（OG-09／#319，Mobile-Library 板 `.mnav`，52px）：品牌字＋
 * 右側角色 chip（三態同桌面，`useAuthRole()` 與桌面 `TopBar` 共用同一份
 * 讀取邏輯）＋刷新入口（既有頂部刷新 trigger——三種刷新時機之一，見
 * `App.tsx` 檔頭；不新增觸發時機，只是把既有按鈕換個位置）。
 *
 * 退役手機首頁原本沿用的 `Toolbar`（iOS Large Title 風格，見
 * `Toolbar.tsx`）——那個元件現在只服務桌面版劇本庫頁面。垃圾桶／設定
 * 這兩個原本疊在 `Toolbar` 上的入口，本來就已經在 `BottomNav`
 * （UI-IMPL-002／#092 既有）重複出現過一次，這裡拿掉的是重複的那份，
 * 不是拿掉功能本身——導覽能力沒有減少，只是不再有兩個地方各放一次。
 *
 * 「N 個劇本」與刷新狀態（`role="status"`，既有 Vitest／e2e 直接鎖住
 * 精確文字「更新中……」／「N 成功」）維持在 `Toolbar.tsx` 原本的同一種
 * 標記與語意，只是換了容器——52px 的 `.mnav` 放不下兩行，改成緊接在
 * 下方一條細狀態列（`.mnav-status-row`），桌面寬度同樣隱藏。
 */
import BrandMark from "./BrandMark";
import { RefreshIcon } from "./icons";
import { ROLE_LABELS, useAuthRole } from "./useAuthRole";

export default function MobileTopBar({
  count,
  busy,
  runSummary,
  onRefresh,
}: {
  count: number;
  busy: boolean;
  /** 上一輪 Refresh Run 結束後的「N 成功／M 失敗」摘要——`null` 表示
   *  還沒有任何一輪跑完過，或正在跑（`busy` 時優先顯示「更新中」）。 */
  runSummary: string | null;
  onRefresh: () => void;
}) {
  const role = useAuthRole();

  return (
    <>
      <div className="mnav">
        <span className="brand">
          <BrandMark />
          Option Chaser
        </span>
        {/* Artifact 的 `.mnav` 中間留了一個給頁面標題用的空位，劇本庫
            板刻意留白（品牌字本身已經夠）——這裡不新增可見文字，但保留
            一個 `sr-only` 的 `<h1>` landmark：手機首頁在拿掉 `Toolbar`
            的 `<h1 class="toolbar-title">劇本庫</h1>` 之後，需要某個地方
            仍然可以被 `getByRole("heading", {name:"劇本庫"})` 找到（既有
            測試拿它確認「現在確實在劇本庫首頁」），螢幕閱讀器也需要一個
            頁面標題可以唸。 */}
        <h1 className="sr-only">劇本庫</h1>
        <span className="spacer" />
        {/* 同桌面 TopBar 既有裁示：Normal User 不顯示角色徽章。 */}
        {role !== "normal" && (
          <span className={`role role-${role}`}>
            <span className="dot" aria-hidden="true" />
            {ROLE_LABELS[role]}
          </span>
        )}
        <button
          type="button"
          className="mnav-refresh"
          onClick={onRefresh}
          disabled={busy}
        >
          <RefreshIcon size={14} />
          {busy ? "刷新中……" : "重新整理"}
        </button>
      </div>
      <div className="mnav-status-row">
        <span className="caption">{count} 個劇本</span>
        {/* role="status"：螢幕閱讀器會唸出變化。進行中優先顯示「更新
            中」（不論是 Refresh Run 或單一劇本刷新），跑完才換成上一輪
            的「N 成功／M 失敗」摘要——兩者互斥。 */}
        {busy ? (
          <span className="caption progress" role="status">更新中……</span>
        ) : runSummary && (
          <span className="caption progress" role="status">{runSummary}</span>
        )}
      </div>
    </>
  );
}
