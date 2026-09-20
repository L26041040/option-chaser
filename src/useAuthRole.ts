import { useEffect, useState } from "react";

import { getAuthStatusCached, subscribeAuthStatus } from "./fetchCache";
import { type Role } from "./superuser";

/**
 * OG-09（#319）：`TopBar.tsx`（桌面）與 `MobileTopBar.tsx`（手機）
 * 各自獨立掛載同一段「讀 `getAuthStatusCached()`、掛載時查一次目前
 * 角色」的 effect——兩份 chrome 是不同元件（桌面 `.topbar` vs 手機
 * `.mnav`，從不同時掛載），但角色查詢邏輯本身完全相同，抽成共用
 * hook 避免同一段程式碼漂移（比照 T16／#232 `findLeg()`／`legSide()`
 * 那一類「共通邏輯抽出」的既有先例）。角色判斷本身（AUTH-02／#309）
 * 不受影響，這裡純粹是多一個顯示消費端共用的讀取封裝。
 *
 * 外部審查（PR #329）跟進：這兩個 chrome 元件跨頁常駐不卸載（OG-02／
 * #318 的常駐頂欄／底部導覽本來就是這個設計目的），使用者若在
 * Settings 頁登入／登出，這裡不能只靠掛載時查一次——`fetchCache.ts`
 * 的 `subscribeAuthStatus()` 讓角色改變當下就更新，不必等使用者手動
 * 整頁重新整理或剛好觸發重新 mount。
 */
export function useAuthRole(): Role {
  const [role, setRole] = useState<Role>("normal");

  useEffect(() => {
    let alive = true;
    const { promise, release } = getAuthStatusCached();
    promise.then((s) => alive && setRole(s.role)).catch(() => {});
    const unsubscribe = subscribeAuthStatus((status) => {
      if (alive) setRole(status.role);
    });
    return () => {
      alive = false;
      release();
      unsubscribe();
    };
  }, []);

  return role;
}

export const ROLE_LABELS: Record<Role, string> = {
  normal: "Normal User",
  superuser: "Super User",
  superadmin: "Super Admin",
};
