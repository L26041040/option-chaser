/**
 * Super Admin 管理中心（CLAUDE-SETTINGS-ROLE-IA-001）。
 *
 * 原本是 Settings 裡的「管理後台」分頁，和「刪除我的資料」「免責聲明」
 * 擺在同一層並不合理——這裡把它升格成獨立頁面（`#/admin`），**只換
 * 頁面層級，內容照舊直接掛載既有的 `SuperUserAdmin`**，API、資料模型與
 * 管理功能都不動（Dashboard 重新設計是之後另一張票）。
 *
 * 守門：角色未確認前只顯示載入中、不掛載 `SuperUserAdmin`（也就不打任何
 * `/api/superuser/*`／`/api/ops/*` 請求）；確認不是 Super Admin——包括
 * 直接打網址進來的 Normal／Super User，以及在這頁期間登出——一律
 * `replace` 回設定頁，不留下可操作的管理畫面，也不在瀏覽歷史裡留一格
 * 會把人彈回來的 `#/admin`。伺服器端的 Super Admin gate 仍是第二道防線。
 */
import { useEffect, useState } from "react";

import { getAuthStatus } from "./api";
import { setAuthStatusCache, subscribeAuthStatus } from "./fetchCache";
import { settingsHash } from "./route";
import SuperUserAdmin from "./SuperUserAdmin";
import { type Role } from "./superuser";

export default function AdminPage() {
  // `null`＝還不知道角色。不能像 `useAuthRole()` 那樣預設 `"normal"`：
  // 那會讓真正的 Super Admin 在查詢回來之前就先被導走。
  const [role, setRole] = useState<Role | null>(null);

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    // 進這頁一定重新問伺服器，不吃 `getAuthStatusCached()` 的快取：快取
    // 只會被同一分頁的登入／登出更新，在另一個分頁登出後這裡的舊
    // `superadmin` 還會留著。拿到的新角色順手寫回共用快取並廣播，
    // 讓 TopBar／Settings 也一起跟上。
    getAuthStatus(controller.signal)
      .then((s) => {
        if (!alive) return;
        setRole(s.role);
        setAuthStatusCache(s);
      })
      // 查不到角色就當作沒有權限——這裡 fail closed，跟 `RoleLogin`
      // 「查詢失敗維持現況」不同：管理畫面不該在不確定時開著。
      .catch(() => alive && setRole("normal"));
    // 登出（或在別處改變角色）當下就反應，不等重新整理。
    const unsubscribe = subscribeAuthStatus((status) => {
      if (alive) setRole(status.role);
    });
    return () => {
      alive = false;
      controller.abort();
      unsubscribe();
    };
  }, []);

  const allowed = role === "superadmin";

  useEffect(() => {
    if (role !== null && !allowed) window.location.replace(settingsHash());
  }, [role, allowed]);

  return (
    <div className="screen admin-page">
      <div className="settings-head">
        <a className="nav-back" href={settingsHash()}>
          ← 設定
        </a>
        <div className="admin-page-title">
          <p className="admin-page-eyebrow">Super Admin</p>
          <h1 className="toolbar-title">管理中心</h1>
        </div>
      </div>

      {role === null ? (
        <p className="caption">載入中……</p>
      ) : allowed ? (
        <SuperUserAdmin />
      ) : null}
    </div>
  );
}
