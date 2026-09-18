/**
 * User Level（軸二，AUTH-01～03／#308–310、AUTH-06／#313，Anonymous
 * Public Beta，spec #307）：三層角色（`normal < superuser < superadmin`）
 * 前端最小應用。
 *
 * PB-09（#298）當年的 sessionStorage＋`Authorization: Bearer <secret>`
 * 機制已被 AUTH-02／AUTH-03 整組後端退役（cookie-based role session
 * 取代，見 `POST /api/auth/login`）——這個模組本身不再存放任何密鑰，
 * 前端也不再需要自己組 `Authorization` 標頭：伺服器簽發的
 * `__Host-oc_role` cookie 是 `HttpOnly`，同源請求會自動帶上，前端 JS
 * 完全讀不到、也不需要讀到它。
 *
 * 與軸一（Owner Identity，瀏覽器 cookie，由伺服器 middleware 自動
 * 處理、前端零碰觸）完全獨立——這裡只管「目前這個角色值是什麼」與
 * 「角色高低怎麼比」，不觸碰 owner_id、劇本資料的任何讀寫路徑。
 *
 * **前端不得自行判斷角色高低**（票面 Implementation constraints）——
 * 唯一允許的比較邏輯集中在這裡，其餘元件一律呼叫 `roleAtLeast()`，
 * 不得自己寫字串比較或另建一份排序表。
 */

/** 與後端 `api_app/superuser.py::Role` 的三個值逐字對應。 */
export type Role = "normal" | "superuser" | "superadmin";

const RANK: Record<Role, number> = { normal: 0, superuser: 1, superadmin: 2 };

/** `role` 是否達到 `minimum` 這一層——全站唯一允許的角色高低判斷式。 */
export function roleAtLeast(role: Role, minimum: Role): boolean {
  return RANK[role] >= RANK[minimum];
}
