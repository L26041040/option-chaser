/**
 * OPTION-CHASER-UNIFIED-IDENTITY-001：這個瀏覽器的持久身分憑證。
 *
 * 比照 Supabase／Firebase 的匿名身分：一個 user、一份持久憑證存在瀏覽器裡，
 * 只有明確清除才會遺失；權限（Normal／SU／SA）也掛在同一個 user 上。同一顆
 * token 存兩份：
 *
 * - 伺服器簽的 HttpOnly cookie（`__Host-oc_owner`，JS 讀不到）；
 * - 這裡管理的本機副本：IndexedDB 為主、localStorage 為鏡像。
 *
 * 每個 API 請求都把本機副本放在 `X-OC-Credential` header（`src/api.ts` 的
 * `send()`）。伺服器先認 cookie、再認 header：cookie 不在就用這份並補發
 * cookie；這份不在或不一樣，回應就用同名 header 交回正確的值，由
 * `storeCredential()` 存起來。兩份每次回應都會收斂成同一顆——任何一份還在，
 * 身分就不會掉。舊版（綁定後就刪掉本機副本、只剩 cookie）正是單點故障。
 *
 * 首次造訪還沒有 user 時，這顆 token 就是第一次會建立 user 的請求（建立
 * 劇本、存設定、輸入 SU／SA 密碼）要綁的那顆；所有分頁共用同一份本機副本，
 * 所以只會得到一個 user。
 *
 * **跨分頁原子性**：「讀→沒有就產生→寫回」放在 IndexedDB 的單一 readwrite
 * transaction 裡——規格保證同一個 origin 上 scope 重疊的 readwrite
 * transaction 依序執行，後到的分頁一定讀到先到的那顆。IndexedDB 不能用時
 * 退回 localStorage，再不行就回 `null`（只剩 cookie 那一份）。
 *
 * **還沒綁定前，會建立 user 的請求跨分頁排隊**（`withOwnerBindingLock`，
 * Web Locks）：退回 localStorage 時兩個分頁可能各自產生不同的 token，
 * 依序進行後，先到的綁定、cookie 進了共用的 cookie jar，後到的帶著那顆
 * cookie，伺服器以 cookie 為準，並把正確的 token 交回給它存。請求有逾時
 * （`REQUEST_TIMEOUT_MS`），鎖不會被卡住的請求永久佔住。
 */
export const CREDENTIAL_HEADER = "X-OC-Credential";
export const OWNER_BOUND_HEADER = "X-OC-Owner-Bound";
// 儲存位置沿用舊名：舊版前端留下、還沒綁定的那顆 token 會被直接沿用。
const STORAGE_KEY = "oc_owner_bootstrap";
const DB_NAME = "oc-owner-bootstrap";
const STORE = "kv";
const BINDING_LOCK = "oc-owner-binding";

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () => reject(new Error("indexedDB blocked"));
  });
}

/** 在單一 readwrite transaction 裡跑 `body`，transaction 真的 commit
 * 之後才 resolve（`oncomplete`）。 */
async function inTransaction<T>(body: (store: IDBObjectStore, done: (v: T) => void) => void): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      let value: T;
      body(tx.objectStore(STORE), (v) => { value = v; });
      tx.oncomplete = () => resolve(value);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error ?? new Error("transaction aborted"));
    });
  } finally {
    db.close();
  }
}

const TOKEN_SHAPE = /^[A-Za-z0-9_-]{22,128}$/;

/** localStorage 裡既有的合法 token；讀不到或形狀不對回 `null`。 */
function existingLocalStorageToken(): string | null {
  try {
    const token = localStorage.getItem(STORAGE_KEY);
    return token && TOKEN_SHAPE.test(token) ? token : null;
  } catch {
    return null;
  }
}

function mirrorToLocalStorage(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // localStorage 不能用：之後也不會退回它，不必鏡像。
  }
}

/**
 * IndexedDB 是主儲存，localStorage 是它的鏡像（IndexedDB 暫時失敗時的
 * 退路讀的就是這份）。平常兩邊相同；會不同只有兩種來源：前一版只用
 * localStorage，或這個瀏覽器曾經退回 localStorage 產生過一顆——那顆可能
 * 已經被綁定、正等著重試，所以**以 localStorage 為準**，把 IndexedDB 對齊
 * 過去，不是把它蓋掉。整段在同一個 readwrite transaction 裡，跨分頁原子性
 * 不變：後到的分頁讀到的 localStorage 不是空的就是先到那顆的鏡像。
 */
function idbGetOrCreate(): Promise<string> {
  return inTransaction<string>((store, done) => {
    const get = store.get(STORAGE_KEY);
    get.onsuccess = () => {
      const stored = typeof get.result === "string" && TOKEN_SHAPE.test(get.result)
        ? get.result : null;
      const token = existingLocalStorageToken() ?? stored ?? randomToken();
      if (token !== stored) store.put(token, STORAGE_KEY);
      mirrorToLocalStorage(token);
      done(token);
    };
  });
}

function localStorageGetOrCreate(): string | null {
  try {
    let token = localStorage.getItem(STORAGE_KEY);
    // 形狀不對的值伺服器會直接拒絕（換一顆隨機的綁定），重試就對不上——
    // 跟 IndexedDB 路徑一樣先驗形狀，不對就換一顆新的存回去。
    if (!token || !TOKEN_SHAPE.test(token)) {
      token = randomToken();
      localStorage.setItem(STORAGE_KEY, token);
    }
    return token;
  } catch {
    return null;
  }
}

// 這個分頁的狀態：`bound`＝伺服器說這個瀏覽器已經有 user（之後會建立 user
// 的請求不必再排隊）；`loading` 讓同一個分頁的並發呼叫共用同一次讀取，之後
// 直接用記憶體裡的值——每個分頁最多讀一次 IndexedDB。
let bound = false;
let loading: Promise<string | null> | null = null;
// 讀過之後的值（`null`＝本機儲存都不能用）；`undefined`＝這個分頁還沒讀過。
// 讓 `send()` 在第一次之後同步取用，不必每個請求都多等一輪。
let cached: string | null | undefined;

async function loadToken(): Promise<string | null> {
  if (typeof indexedDB !== "undefined") {
    try {
      return await idbGetOrCreate();
    } catch {
      // 退回 localStorage。
    }
  }
  return localStorageGetOrCreate();
}

/**
 * 會建立 owner 的寫入在還沒綁定前，放在跨分頁獨佔鎖裡跑（見檔頭）。已綁定、
 * 或瀏覽器沒有 Web Locks 時直接跑。鎖 API 本身出錯（`body` 還沒開始跑）
 * 就不上鎖照舊跑；`body` 自己拋的錯照樣往外拋、不會重跑一次。
 */
export async function withOwnerBindingLock<T>(body: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (bound || !locks || typeof locks.request !== "function") return body();
  let started = false;
  try {
    return await locks.request(BINDING_LOCK, () => {
      started = true;
      return body();
    });
  } catch (e) {
    if (started) throw e;
    return body();
  }
}

/** 每個請求要帶的本機憑證；本機儲存都不能用時回 `null`（只剩 cookie）。 */
export function credential(): Promise<string | null> {
  loading ??= loadToken().then((token) => (cached = token));
  return loading;
}

/** 已經讀過的本機憑證（同步）；還沒讀過回 `undefined`，呼叫端改等
 * `credential()`。 */
export function loadedCredential(): string | null | undefined {
  return cached;
}

/** 伺服器在 `X-OC-Credential` 交回正確的憑證（本機副本不在或不一樣）：存進
 * IndexedDB＋localStorage，這個分頁之後的請求就帶它。形狀不對的值不收。 */
export async function storeCredential(token: string): Promise<void> {
  if (!TOKEN_SHAPE.test(token)) return;
  cached = token;
  loading = Promise.resolve(token);
  mirrorToLocalStorage(token);
  if (typeof indexedDB !== "undefined") {
    try {
      await inTransaction<void>((store, done) => {
        store.put(token, STORAGE_KEY);
        done(undefined);
      });
    } catch {
      // IndexedDB 寫不進去：localStorage 那份還在，下次讀取以它為準。
    }
  }
}

/** 伺服器回應帶著 `X-OC-Owner-Bound: 1`＝這個瀏覽器已經有 user：之後會建立
 * user 的請求不必再排隊。本機憑證**不刪**——它就是持久身分的其中一份。 */
export function markOwnerBound(): void {
  bound = true;
}

/** 測試用：回到「還沒綁定、還沒讀過」的初始狀態。 */
export async function resetCredentialStoreForTests(): Promise<void> {
  bound = false;
  loading = null;
  cached = undefined;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 同上。
  }
  if (typeof indexedDB !== "undefined") {
    try {
      await inTransaction<void>((store, done) => {
        store.delete(STORAGE_KEY);
        done(undefined);
      });
    } catch {
      // 同上。
    }
  }
}
