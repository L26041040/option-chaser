/**
 * User Level（軸二，PB-09／#298，Anonymous Public Beta）：Super User
 * 前端最小應用。
 *
 * 與軸一（Owner Identity，瀏覽器 cookie，由伺服器 middleware 自動
 * 處理、前端零碰觸）完全獨立——這裡只管「這個分頁有沒有記著一把可能
 * 有效的 `ADMIN_SECRET`」，不觸碰 owner_id、劇本資料的任何讀寫路徑，
 * 也不 import 任何跟 owner cookie 相關的模組。
 *
 * 存放位置刻意選 `sessionStorage`（分頁關閉即清除），不用
 * `localStorage`——降低裝置共用情境下殘留的曝險窗。這裡快取的是
 * **密鑰本身**，不是一個伺服器會盲目信任的權限旗標：每一次受保護的
 * 請求，後端都會用這把密鑰重新比對一次（`api_app/superuser.py::
 * is_superuser()`），前端把它存在哪裡、怎麼存，都改變不了「密鑰對
 * 不對」這件事本身——竄改 sessionStorage 頂多讓下一次請求帶錯密鑰，
 * 不會讓伺服器誤判成 Super User。
 */

const STORAGE_KEY = "oc_admin_secret";

export function getAdminSecret(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // 私密瀏覽模式等情境下 sessionStorage 可能整個不可用——退回
    // 「這次沒有記住的密鑰」，不讓整個功能因此掛掉。
    return null;
  }
}

export function setAdminSecret(secret: string | null): void {
  try {
    if (secret) {
      sessionStorage.setItem(STORAGE_KEY, secret);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // 同上——寫不進去就算了，不拋錯。
  }
}

/** 附加到受 Super User 保護的請求上的標頭。沒有記住密鑰時回傳空
 *  物件——請求會像沒登入一樣被伺服器擋下（401），不是前端自己先擋。 */
export function adminAuthHeaders(): Record<string, string> {
  const secret = getAdminSecret();
  return secret ? { Authorization: `Bearer ${secret}` } : {};
}
