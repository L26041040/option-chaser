/**
 * 三層角色登入入口（AUTH-06／#313，Anonymous Public Beta）：取代已
 * 退役的 sessionStorage 機制 `SuperUserUnlock.tsx`（PB-09／#298）。
 *
 * 單一密碼輸入框——沒有 username、沒有角色選單。打
 * `POST /api/auth/login`（AUTH-02／#309），由伺服器依密碼命中哪一把
 * （`SUPERADMIN_PASSWORD` 或 `SUPERUSER_PASSWORD`）決定角色，這裡只
 * 負責顯示結果與登出，不自行判斷角色高低（比較邏輯集中在
 * `./superuser`）。
 *
 * 掛載位置與既有 `SuperUserUnlock` 相同（Settings 頁）。角色狀態的
 * 唯一真相來源是 `GET /api/auth/status`（`__Host-oc_role` cookie，
 * `HttpOnly`，前端 JS 讀不到也不需要讀）——持久 cookie 讓重新整理
 * 頁面（模擬瀏覽器重啟）仍維持登入狀態，不需要使用者重新輸入密碼。
 * 密碼本身絕不寫進 `localStorage`／`sessionStorage`，只活在這次
 * `submit` 呼叫的請求 body 裡。
 */
import { useEffect, useState } from "react";

import { login, logout } from "./api";
import { getAuthStatusCached, setAuthStatusCache } from "./fetchCache";
import { roleAtLeast, type Role } from "./superuser";

const ROLE_LABELS: Record<Role, string> = {
  normal: "Normal User",
  superuser: "Super User",
  superadmin: "Super Admin",
};

export default function RoleLogin({
  role,
  onChange,
}: {
  role: Role;
  onChange: (role: Role) => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 掛載時查一次現況——不必等使用者按什麼才知道自己現在是誰。
  useEffect(() => {
    let alive = true;
    const { promise, release } = getAuthStatusCached();
    promise
      .then((s) => alive && onChange(s.role))
      .catch(() => {
        // 查詢本身失敗（逾時、連不上）不等於已登出——維持現況，不因為
        // 一次網路問題就把人踢回 Normal User。
      });
    return () => {
      alive = false;
      release();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const typed = password.trim();
    if (!typed) return;
    setBusy(true);
    setError(null);
    try {
      const status = await login(typed);
      setAuthStatusCache(status);
      onChange(status.role);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function doLogout() {
    setBusy(true);
    setError(null);
    try {
      const status = await logout();
      setAuthStatusCache(status);
      onChange(status.role);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card settings-section" aria-label="登入">
      <h2 className="section-title">登入</h2>
      {roleAtLeast(role, "superuser") ? (
        <>
          <p className="caption">目前身分：{ROLE_LABELS[role]}。</p>
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => void doLogout()}
          >
            {busy ? "登出中……" : "登出"}
          </button>
        </>
      ) : (
        <form onSubmit={(ev) => void submit(ev)}>
          <label className="settings-field">
            <span className="caption">密碼</span>
            <input
              className="settings-input"
              type="password"
              autoComplete="off"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
            />
          </label>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <div className="settings-actions">
            <button className="pill" type="submit" disabled={busy || !password.trim()}>
              {busy ? "登入中……" : "登入"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
