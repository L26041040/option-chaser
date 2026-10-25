/**
 * OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001：這台裝置換了身分（登入主帳號、或
 * 登出主帳號回到匿名 Normal User）之後，劇本、設定、用量全部屬於另一個
 * user——整頁重新載入（停在原本這一頁），不留上一個身分的任何快取。新的
 * 憑證在這之前已經由 `src/api.ts` 的 `send()` 存進本機（`X-OC-Credential`），
 * HttpOnly cookie 也已經換好，重新載入後的第一個請求就是新身分。
 *
 * 獨立成一個模組，測試才能替換（jsdom 的 `location.reload` 不能被監聽）。
 */
export function reloadAfterAccountSwitch(): void {
  window.location.reload();
}
