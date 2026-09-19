/**
 * 桌面版頂欄（UI-IMPL-002／#092，Main 板 `.topbar`）：品牌標記＋頂層
 * 導覽（劇本庫／垃圾桶／設定）＋目前角色徽章。**桌面專屬**——手機版
 * 對應的導覽是畫面底部的 `BottomNav`，兩者是設計稿本來就分開的兩種
 * chrome（`.topbar` vs `.mtop`＋`.mtabs`），不是同一個元件的兩種顯示
 * 模式。
 *
 * 這是本輪新增的**視覺**導覽列，疊在既有 `Toolbar`（劇本庫頂端「＋
 * 建立劇本／重新整理」那一條，桌面／手機共用）之上——不取代它，既有
 * 的建立／刷新語意、`aria-expanded`／`aria-controls` 等既有測試鎖住
 * 的行為完全不動。角色徽章讀的是既有 `getAuthStatusCached()`（
 * `RoleLogin.tsx` 同一份快取），這裡純粹是多一個顯示消費端，不改變
 * 角色判斷或登入流程本身。
 */
import { useEffect, useState } from "react";

import { getAuthStatusCached } from "./fetchCache";
import { settingsHash, trashHash } from "./route";
import { type Role } from "./superuser";

const ROLE_LABELS: Record<Role, string> = {
  normal: "Normal User",
  superuser: "Super User",
  superadmin: "Super Admin",
};

function BrandMark() {
  return (
    <svg
      className="brand-mark"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" />
      <path
        d="M12 2.5v3M21.5 12h-3M12 21.5v-3M2.5 12h3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

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
   *  選填是為了讓既有沒有建立語意的呼叫端（若有）不必被迫補一個
   *  no-op；目前唯一呼叫端（`App.tsx` 桌面分支）一律會傳，連同下面
   *  兩個 `aria-*` 用的欄位。 */
  onOpenCreate?: () => void;
  /** 抽屜目前是否展開——供 `aria-expanded` 使用。按鈕本身文字不隨這個
   *  值改變（不是 toggle，見上），但輔助科技仍該知道它控制的區域現在
   *  是否展開，沿用既有 `MonthPicker`（`CreateForm.tsx`）同一套
   *  `aria-expanded`＋`aria-controls` 寫法。 */
  createOpen?: boolean;
  /** 抽屜的 DOM id（`App.tsx` 的 `createPanelId`），供 `aria-controls`
   *  指向它。 */
  createPanelId?: string;
}) {
  const [role, setRole] = useState<Role>("normal");

  useEffect(() => {
    let alive = true;
    const { promise, release } = getAuthStatusCached();
    promise.then((s) => alive && setRole(s.role)).catch(() => {});
    return () => {
      alive = false;
      release();
    };
  }, []);

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
      <nav className="nav">
        <a className={active === "library" ? "on" : undefined} href="#">
          劇本庫
        </a>
        <a className={active === "trash" ? "on" : undefined} href={trashHash()}>
          垃圾桶
        </a>
        <a className={active === "settings" ? "on" : undefined} href={settingsHash()}>
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
      {onOpenCreate && (
        <button
          type="button"
          className="btn"
          onClick={onOpenCreate}
          aria-expanded={createOpen}
          aria-controls={createPanelId}
        >
          ＋ 建立劇本
        </button>
      )}
    </div>
  );
}
