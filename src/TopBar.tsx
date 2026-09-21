/**
 * 桌面版頂欄（UI-IMPL-002／#092，Main 板 `.topbar`）：品牌標記＋頂層
 * 導覽（劇本庫／垃圾桶／設定）＋目前角色徽章＋建立劇本入口。**桌面
 * 專屬**——手機版對應的導覽是 52px `MobileTopBar`＋畫面底部的
 * `BottomNav`（OG-09／#319），兩者是設計稿本來就分開的兩種 chrome
 * （`.topbar` vs `.mnav`＋`.mtabs`），不是同一個元件的兩種顯示模式；
 * `BrandMark`（`./BrandMark`）與角色查詢（`./useAuthRole`）是兩者
 * 共用的部分，已抽成獨立檔案。
 *
 * OG-02（#318）起是桌面版**唯一**的導覽與建立劇本入口——原本疊在下面
 * 的 `Toolbar`（劇本庫頁面自己的釘選列）已不再重複顯示垃圾桶／建立
 * 按鈕（見 `Toolbar.tsx`），只剩重新整理（擺位由 OG-03 決定）。角色
 * 徽章讀的是既有 `getAuthStatusCached()`（`RoleLogin.tsx` 同一份快取），
 * 這裡純粹是多一個顯示消費端，不改變角色判斷或登入流程本身。
 *
 * SW-02（#332，Seed Warm）：68px 暖米色頂列、pill 導覽（`.pnav`，
 * SW-01／#331 primitive）＋`aria-current="page"` 標示目前頁、CTA 改
 * `.pbtn`（terracotta pill）。導覽與建立劇本的*行為*（連結目標、
 * `onOpenCreate`/`aria-expanded`/`aria-controls` 語意）完全不動，只換
 * 形狀語言。
 */
import BrandMark from "./BrandMark";
import { settingsHash, trashHash } from "./route";
import { ROLE_LABELS, useAuthRole } from "./useAuthRole";

export default function TopBar({
  active,
  onOpenCreate,
  createOpen,
  createPanelId,
}: {
  active: "library" | "trash" | "settings";
  /** OG-02（#318）：頂欄「建立劇本」primary 按鈕——開既有右側抽屜
   *  （`App.tsx` 的 `showCreateForm`），不是 toggle：抽屜自己的
   *  `.drawer-close` 與遮罩點擊已經是既有的關閉手段，這裡只負責開。
   *  必填——`TopBar` 目前只有桌面分支這一個呼叫端，一律會傳，連同下面
   *  兩個 `aria-*` 用的欄位；沒有理由留一個永遠不會缺席的可選欄位。 */
  onOpenCreate: () => void;
  /** 抽屜目前是否展開——供 `aria-expanded` 使用。按鈕本身文字不隨這個
   *  值改變（不是 toggle，見上），但輔助科技仍該知道它控制的區域現在
   *  是否展開，沿用既有 `MonthPicker`（`CreateForm.tsx`）同一套
   *  `aria-expanded`＋`aria-controls` 寫法。 */
  createOpen: boolean;
  /** 抽屜的 DOM id（`App.tsx` 的 `createPanelId`），供 `aria-controls`
   *  指向它。 */
  createPanelId: string;
}) {
  const role = useAuthRole();

  // 用 `<div>` 不用 `<header>`：既有 `Toolbar` 本身就是這個頁面唯一的
  // `<header>`（ARIA banner landmark），這裡是疊加的次要 chrome，不是
  // 頁面本身的 banner——兩個 `<header>` 會讓輔助技術與
  // `getByRole("banner")` 這類查詢都碰到「找到不只一個」的真實模糊性，
  // 不是視覺差異。
  return (
    <div className="topbar">
      <span className="brand">
        <BrandMark />
        Option Chaser
      </span>
      <nav className="pnav" aria-label="主導覽">
        <a
          aria-current={active === "library" ? "page" : undefined}
          href="#"
        >
          劇本庫
        </a>
        <a
          aria-current={active === "trash" ? "page" : undefined}
          href={trashHash()}
        >
          垃圾桶
        </a>
        <a
          aria-current={active === "settings" ? "page" : undefined}
          href={settingsHash()}
        >
          設定
        </a>
      </nav>
      <span className="spacer" />
      {/* OG-02（#318）：Normal User 不顯示角色徽章——一般使用者不需要
          被提醒「你現在是 Normal」，這個徽章只在有實際提升權限時才是
          有意義的資訊。Super User／Super Admin 兩態才顯示。 */}
      {role !== "normal" && (
        <span className={`role role-${role}`}>
          <span className="dot" aria-hidden="true" />
          {ROLE_LABELS[role]}
        </span>
      )}
      <button
        type="button"
        className="pbtn"
        onClick={onOpenCreate}
        aria-expanded={createOpen}
        aria-controls={createPanelId}
      >
        ＋ 建立劇本
      </button>
    </div>
  );
}
