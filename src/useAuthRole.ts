import { useEffect, useState } from "react";

import { getAuthStatusCached } from "./fetchCache";
import { type Role } from "./superuser";

/**
 * OG-09（#319）：`TopBar.tsx`（桌面）與 `MobileTopBar.tsx`（手機）
 * 各自獨立掛載同一段「讀 `getAuthStatusCached()`、掛載時查一次目前
 * 角色」的 effect——兩份 chrome 是不同元件（桌面 `.topbar` vs 手機
 * `.mnav`，從不同時掛載），但角色查詢邏輯本身完全相同，抽成共用
 * hook 避免同一段程式碼漂移（比照 T16／#232 `findLeg()`／`legSide()`
 * 那一類「共通邏輯抽出」的既有先例）。角色判斷本身（AUTH-02／#309）
 * 不受影響，這裡純粹是多一個顯示消費端共用的讀取封裝。
 */
export function useAuthRole(): Role {
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

  return role;
}

export const ROLE_LABELS: Record<Role, string> = {
  normal: "Normal User",
  superuser: "Super User",
  superadmin: "Super Admin",
};
