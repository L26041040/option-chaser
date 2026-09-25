/**
 * Codex P1（PR #346）：首訪並發寫入共用的 bootstrap token。
 *
 * 第一次造訪、還沒有 owner cookie 的瀏覽器同時送出多個寫入（連點、重試、
 * 兩個分頁）時，伺服器分不出它們來自同一個瀏覽器，會各自建立一個 owner，
 * 最後只有一個留得住。這裡在 localStorage 放一顆隨機 token（同源分頁共用、
 * 重試沿用），寫入請求放在 `X-OC-Owner-Bootstrap` header；伺服器沒有有效
 * cookie 時就用它綁定，同一顆 token 只會得到一個 owner。
 *
 * 寫入成功後就清掉：那時 cookie 已經是真正的身分，這顆 token 沒有用了。
 * 伺服器也只在綁定後很短的時間內接受已綁定的 token（重試用），所以它
 * 不會變成 cookie 之外的第二個身分。localStorage 不能用（隱私模式、被
 * 封鎖）時回 `null`，退回沒有 header 的既有行為。
 */
export const OWNER_BOOTSTRAP_HEADER = "X-OC-Owner-Bootstrap";
const STORAGE_KEY = "oc_owner_bootstrap";

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function ownerBootstrapToken(): string | null {
  try {
    let token = localStorage.getItem(STORAGE_KEY);
    if (!token) {
      token = randomToken();
      localStorage.setItem(STORAGE_KEY, token);
    }
    return token;
  } catch {
    return null;
  }
}

export function clearOwnerBootstrapToken(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 讀不到 localStorage 就本來也沒有東西可清。
  }
}
