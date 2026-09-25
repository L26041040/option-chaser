/**
 * Codex P1（PR #346）：首訪並發寫入共用的 bootstrap token。
 *
 * 第一次造訪、還沒有 owner cookie 的瀏覽器同時送出多個寫入（連點、重試、
 * 兩個分頁）時，伺服器分不出它們來自同一個瀏覽器，會各自建立一個 owner，
 * 最後只有一個留得住。這裡在瀏覽器本機存一顆隨機 token（同源分頁共用、
 * 重試沿用），寫入請求放在 `X-OC-Owner-Bootstrap` header；伺服器沒有有效
 * cookie 時就用它綁定，同一顆 token 只會得到一個 owner。
 *
 * **跨分頁原子性**：「讀→沒有就產生→寫回」必須對所有分頁互斥，否則兩個
 * 分頁同時首訪會各自產生不同的 token。localStorage 沒有 compare-and-set，
 * 所以放在 IndexedDB 的單一 readwrite transaction 裡做——規格保證同一個
 * origin 上 scope 重疊的 readwrite transaction 依序執行（跨分頁、跨
 * connection），後到的分頁一定讀到先到的那顆。IndexedDB 不能用（部分
 * 隱私模式）時退回 localStorage，再不行就回 `null`（不帶 header，沿用
 * 既有行為）。
 *
 * 伺服器回應帶 `X-OC-Owner-Bound: 1`（cookie 已綁定）時就清掉，這個分頁
 * 之後不再帶、也不再碰 IndexedDB。伺服器只在綁定後很短的時間內接受已綁定
 * 的 token（重試用），所以它不會變成 cookie 之外的第二個身分。
 */
export const OWNER_BOOTSTRAP_HEADER = "X-OC-Owner-Bootstrap";
export const OWNER_BOUND_HEADER = "X-OC-Owner-Bound";
const STORAGE_KEY = "oc_owner_bootstrap";
const DB_NAME = "oc-owner-bootstrap";
const STORE = "kv";

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

// 這個分頁的狀態：`bound` 之後（伺服器說 cookie 已經綁定）就不再需要
// bootstrap token，也不再碰 IndexedDB；`loading` 讓同一個分頁的並發呼叫
// 共用同一次讀取，之後直接用記憶體裡的值——每個分頁最多讀一次 IndexedDB。
let bound = false;
let loading: Promise<string | null> | null = null;

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

/** 寫入請求要帶的 bootstrap token；已綁定（或本機儲存都不能用）時回
 * `null`。 */
export function ownerBootstrapToken(): Promise<string | null> {
  if (bound) return Promise.resolve(null);
  loading ??= loadToken();
  return loading;
}

/** 伺服器回應帶著 `X-OC-Owner-Bound: 1`＝owner cookie 已經綁定：token 功成
 * 身退，清掉本機儲存，這個分頁之後的寫入都不再帶 header。 */
export async function markOwnerBound(): Promise<void> {
  if (bound) return;
  bound = true;
  loading = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 讀不到 localStorage 就本來也沒有東西可清。
  }
  if (typeof indexedDB !== "undefined") {
    try {
      await inTransaction<void>((store, done) => {
        store.delete(STORAGE_KEY);
        done(undefined);
      });
    } catch {
      // 清不掉只代表 IndexedDB 裡留著一顆已綁定的 token；伺服器只在綁定後
      // 很短的時間內接受它，之後就不算身分。
    }
  }
}

/** 測試用：回到「還沒綁定、還沒讀過」的初始狀態。 */
export async function resetOwnerBootstrapForTests(): Promise<void> {
  bound = false;
  loading = null;
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
