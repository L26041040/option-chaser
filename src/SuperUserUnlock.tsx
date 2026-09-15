/**
 * Super User 解鎖入口（PB-09／#298，Anonymous Public Beta）：軸二
 * （User Level）唯一的驗證機制——打一把 `ADMIN_SECRET`，整個瀏覽器
 * 分頁內即可使用全部 Super User 介面，不必為不同功能各自再輸入一次。
 *
 * 與軸一（Browser Identity，一般使用者的 owner cookie）完全獨立：
 * 這支元件不讀、不寫任何 owner_id 相關狀態，只管「這個分頁現在算不算
 * Super User」。密鑰存在 `sessionStorage`（見 `./superuser.ts` 檔頭的
 * 理由），分頁關閉即清除。
 *
 * 目前唯一的消費端是 `Settings.tsx`（決定要不要顯示自訂 provider
 * token 輸入），PB-10／PB-11 上線後會有更多畫面需要同一個「目前是不是
 * Super User」狀態。
 */
import { useEffect, useState } from "react";

import { getSuperUserStatus } from "./api";
import { getAdminSecret, setAdminSecret } from "./superuser";

export default function SuperUserUnlock({
  isSuperUser,
  onChange,
}: {
  isSuperUser: boolean;
  onChange: (isSuperUser: boolean) => void;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 分頁內若已經記著一把密鑰（例如稍早解鎖過、或同一分頁換頁回來），
  // 開頁就先問一次伺服器現在算不算數——不必等使用者手動再按一次。
  useEffect(() => {
    if (!getAdminSecret()) return;
    let alive = true;
    getSuperUserStatus()
      .then((r) => alive && onChange(r.is_superuser))
      .catch(() => {
        // 查詢本身失敗（逾時、連不上）不等於密鑰無效——維持現況，
        // 不因為一次網路問題就把人踢回 Normal User。
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function unlock(e: React.FormEvent) {
    e.preventDefault();
    const typed = input.trim();
    if (!typed) return;
    setBusy(true);
    setError(null);
    setAdminSecret(typed);
    try {
      const r = await getSuperUserStatus();
      if (r.is_superuser) {
        onChange(true);
        setInput("");
      } else {
        // 密鑰打錯——不留著一把確定無效的密鑰，下次解鎖乾淨重來。
        setAdminSecret(null);
        setError("密鑰不正確");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function lock() {
    setAdminSecret(null);
    onChange(false);
  }

  return (
    <section className="card settings-section" aria-label="Super User">
      <h2 className="section-title">Super User</h2>
      {isSuperUser ? (
        <>
          <p className="caption">目前已解鎖。</p>
          <button type="button" className="text-button" onClick={lock}>
            鎖回 Normal User
          </button>
        </>
      ) : (
        <form onSubmit={(e) => void unlock(e)}>
          <label className="settings-field">
            <span className="caption">密鑰</span>
            <input
              className="settings-input"
              type="password"
              autoComplete="off"
              value={input}
              onChange={(ev) => setInput(ev.target.value)}
            />
          </label>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <div className="settings-actions">
            <button className="pill" type="submit" disabled={busy || !input.trim()}>
              {busy ? "驗證中……" : "解鎖"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
