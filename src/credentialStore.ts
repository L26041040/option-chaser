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
 *
 * **IndexedDB 永遠不能卡住整站**（IRI-01／NIR-04，研究 #365）：已知
 * Safari 14.1.1／iOS 14.6 的 `indexedDB.open()` 會永遠 pending、不觸發任何
 * 事件；而 `send()` 在自己的請求逾時之前就先等本機憑證。沒有逾時的話，
 * 一個卡住的 open 會讓這個分頁**所有** API 請求永遠等待——即使 cookie
 * 那一腿完好。所以每一次 IndexedDB 操作（讀取、寫入）都跟 `IDB_TIMEOUT_MS`
 * 賽跑：逾時就當它不可用，退回 localStorage（再不行就只剩 cookie），下一次
 * 寫入照樣再試 IndexedDB——卡住的 promise 不會被永久快取成這個分頁的答案。
 *
 * **分頁快取會失效，不會永遠相信自己**（IRI-02／NIR-10，研究 #366）：每個
 * 分頁只在第一次讀一次本機儲存，之後用記憶體裡的 `cached`／`bound`。另一個
 * 分頁登入或登出主帳號、或刪除自己的資料時，憑證換了一顆，這個分頁的
 * 記憶體副本就過期了——正常情況下靠「伺服器以 cookie 為準、回應 echo 正確
 * 的值」收斂，但「cookie 剛好不在＋另一分頁剛換過憑證」或「登出後兩分頁同時
 * 首寫、過期的 `bound` 跳過排隊」這類雙重故障會各綁一個 owner。兩個便宜的
 * 修法，都只是「讓下一次請求重讀本機儲存」、不新增任何狀態來源：
 *
 * - 回應**沒有** `X-OC-Owner-Bound: 1` 而這個分頁以為自己已綁定 → 重置快取
 *   （`noteOwnerBound(false)`）；下一次 `send()` 重讀 IndexedDB，會建立 user 的
 *   寫入重新排隊。
 * - 其他分頁改了 localStorage 鏡像（`storage` 事件）→ 同樣只重置快取，**不**
 *   拿 `event.newValue` 當憑證（PostHog PR #4659 的做法）：下一次讀的是本機
 *   儲存的實際內容。
 *
 * 不用 BroadcastChannel：它解的是「憑證會自己定期輪替」的問題（Supabase／
 * Firebase 每小時換 token），本產品沒有；多一個狀態來源就多一組競態。
 */
export const CREDENTIAL_HEADER = "X-OC-Credential";
export const OWNER_BOUND_HEADER = "X-OC-Owner-Bound";
// 儲存位置沿用舊名：舊版前端留下、還沒綁定的那顆 token 會被直接沿用。
const STORAGE_KEY = "oc_owner_bootstrap";
const DB_NAME = "oc-owner-bootstrap";
const STORE = "kv";
const BINDING_LOCK = "oc-owner-binding";
/** 任何一次 IndexedDB 操作最多等這麼久；超過就視為不可用、走退路（見檔頭）。
 *  比 `src/api.ts` 的請求逾時短很多：這裡等的是本機磁碟，不是網路。 */
export const IDB_TIMEOUT_MS = 1500;

/** `promise` 在 `ms` 內沒有定案就 reject。計時器在定案後清掉，不留懸掛的
 *  timer（測試用 fake timers 時也乾淨）。 */
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`indexedDB operation timed out after ${ms}ms`)), ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); });
  });
}

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
 * 之後才 resolve（`oncomplete`）。開啟與交易合起來受 `IDB_TIMEOUT_MS`
 * 約束：逾時 reject，呼叫端走退路；若 IndexedDB 之後才醒來，連線照樣
 * 關掉、不留懸掛。 */
function inTransaction<T>(body: (store: IDBObjectStore, done: (v: T) => void) => void): Promise<T> {
  const run = (async () => {
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
  })();
  // 逾時後 `run` 若仍 reject，沒有人在聽——避免 unhandled rejection。
  run.catch(() => {});
  return withTimeout(run, IDB_TIMEOUT_MS);
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
// 直接用記憶體裡的值——每個分頁最多讀一次 IndexedDB，直到快取被重置
// （`invalidateTabCache()`，見檔頭）。
let bound = false;
let loading: Promise<string | null> | null = null;
// 讀過之後的值（`null`＝本機儲存都不能用）；`undefined`＝這個分頁還沒讀過。
// 讓 `send()` 在第一次之後同步取用，不必每個請求都多等一輪。
let cached: string | null | undefined;
// `storage` 事件監聯只掛一次（第一次 `credential()` 時）；測試的 reset 不拆它。
let crossTabSyncInstalled = false;

/** 忘掉這個分頁記憶體裡的憑證與綁定狀態：下一次 `send()` 重讀本機儲存，
 *  會建立 user 的寫入重新排隊。不碰本機儲存本身。 */
export function invalidateTabCache(): void {
  bound = false;
  loading = null;
  cached = undefined;
}

function installCrossTabSync(): void {
  if (crossTabSyncInstalled || typeof window === "undefined") return;
  crossTabSyncInstalled = true;
  window.addEventListener("storage", (event: StorageEvent) => {
    // `key === null`＝另一個分頁 `localStorage.clear()`。只重置、不讀
    // `event.newValue`：值一律以本機儲存的實際內容為準。
    if (event.key === null || event.key === STORAGE_KEY) invalidateTabCache();
  });
}

async function loadToken(): Promise<string | null> {
  if (typeof indexedDB !== "undefined") {
    try {
      return await idbGetOrCreate();
    } catch {
      // 報錯或逾時（`IDB_TIMEOUT_MS`）都一樣：退回 localStorage。
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
  installCrossTabSync();
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
      // IndexedDB 寫不進去或逾時：localStorage 那份還在，下次讀取以它為準。
    }
  }
}

/** 伺服器在每個解析身分的回應裡說了這次請求的憑證有沒有綁到 user
 * （`X-OC-Owner-Bound: 1` 有／沒有這個 header 沒有）。有：之後會建立 user
 * 的請求不必再排隊；本機憑證**不刪**——它就是持久身分的其中一份。沒有、
 * 而這個分頁以為自己已綁定：記憶體副本過期了（另一個分頁換過憑證），重置
 * 快取讓下一次請求重讀本機儲存（見檔頭）。首訪（本來就沒綁定）什麼都不做。 */
export function noteOwnerBound(isBound: boolean): void {
  if (isBound) {
    bound = true;
  } else if (bound) {
    invalidateTabCache();
  }
}

/** `noteOwnerBound(true)` 的舊名，既有測試在用。 */
export function markOwnerBound(): void {
  noteOwnerBound(true);
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
