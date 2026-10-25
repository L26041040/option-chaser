/**
 * 三層角色登入入口（AUTH-06／#313，Anonymous Public Beta）：取代已
 * 退役的 sessionStorage 機制 `SuperUserUnlock.tsx`（PB-09／#298）。
 *
 * 單一密碼輸入框——沒有 username、沒有角色選單。打
 * `POST /api/auth/login`（AUTH-02／#309），由伺服器依密碼命中哪一把
 * （`SUPERADMIN_PASSWORD` 或 `SUPERUSER_PASSWORD`）決定角色，這裡只
 * 負責顯示結果與重設權限，不自行判斷角色高低（比較邏輯集中在
 * `./superuser`）。
 *
 * 掛載位置與既有 `SuperUserUnlock` 相同（Settings 頁）。角色狀態的
 * 唯一真相來源是 `GET /api/auth/status`。OPTION-CHASER-CROSS-DEVICE-
 * ACCOUNT-001 起：任何裝置輸入正確密碼都登入**同一個主帳號**（這台裝置原本
 * 的匿名劇本一併併進去），權限依這次輸入的密碼掛在這台裝置的憑證上；按
 * 「重設為 Normal User」＝這台裝置登出主帳號。兩者都換了身分，成功後整頁
 * 重新載入（`reloadAfterAccountSwitch()`）。
 * 密碼本身絕不寫進 `localStorage`／`sessionStorage`，只活在這次
 * `submit` 呼叫的請求 body 裡。
 *
 * OG-11（#322）當時把像素級樣式對齊留到後續驗收票處理——SW-07（#336，
 * Seed Warm）就是那張票：登入按鈕換成 `.pbtn`，其餘結構（單一密碼欄／
 * 無 username／無角色選單、`.settings-section`／`.settings-field` 版面）
 * 逐位元組不變，密碼欄位行為（不記錄、不回顯、只活在這次 submit 的
 * request body 裡）同樣不變。
 */
import { useEffect, useState } from "react";

import { reloadAfterAccountSwitch } from "./accountSwitch";
import { login, resetRole } from "./api";
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
      reloadAfterAccountSwitch();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function doReset() {
    setBusy(true);
    setError(null);
    try {
      const status = await resetRole();
      setAuthStatusCache(status);
      onChange(status.role);
      reloadAfterAccountSwitch();
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
          <p className="caption">
            這台裝置已登入主帳號：任何裝置輸入同一組密碼，看到的都是同一份劇本。按下面的重設，這台裝置就登出主帳號，回到匿名的 Normal User。
          </p>
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => void doReset()}
          >
            {busy ? "重設中……" : "重設為 Normal User"}
          </button>
        </>
      ) : (
        <form onSubmit={(ev) => void submit(ev)}>
          <label className="settings-field">
            <span className="caption">密碼</span>
            {/* `.pinp` primitive 刻意不套在這裡——理由同 `CreateForm.tsx`
                頭部同一句說明：`.settings-input` 既有的 16px 字級是 iOS
                Safari 防止整頁縮放的既有保護，兩者顏色／圓角本來就一致
                （都讀 Seed Warm token），不是漏改。 */}
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
            <button className="pbtn" type="submit" disabled={busy || !password.trim()}>
              {busy ? "登入中……" : "登入"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
