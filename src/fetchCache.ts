/**
 * 前端取數紀律（T03／#187）：以資料身分為鍵的 fetch 快取＋in-flight
 * 去重＋reference-counted abort。
 *
 * 消滅的是 deep-link 開詳細頁的 refetch cascade（架構調查回報#025）：
 * 每個元件各自 mount 各自抓、零共享零去重——這裡把「同一份資料只抓
 * 一次」這件事收進一個地方，呼叫端只需要決定 key 是什麼。
 *
 * 設計刻意簡單：一個 `Map<key, Entry>`，key 是呼叫端決定的資料身分
 * 字串（不是 URL、不是渲染時機）。不引入任何外部套件（react-query／
 * SWR 之類）——維持前端目前只依賴 react／react-dom 的現狀。
 */
import { getScenario, getSettings, ivHistory,
        type IvHistoryView, type ScenarioDetail, type SettingsView } from "./api";

interface Entry<T> {
  promise: Promise<T>;
  controller: AbortController;
  refCount: number;
  settled: boolean;
}

const cache = new Map<string, Entry<unknown>>();

export interface CachedFetch<T> {
  /** 這次呼叫要 await 的 promise——可能是全新發出的，也可能是共用
   *  中的既有 in-flight 或已完成結果。 */
  promise: Promise<T>;
  /** 呼叫端不再需要這份資料時呼叫一次（通常在 `useEffect` 的清理
   *  函式裡）。只有當最後一個仍在等待這個 key 的呼叫端都 release
   *  之後，若這個 fetch 仍未完成，才會真的 abort 底層請求——別的
   *  呼叫端還在等的話不會被提前打斷。 */
  release: () => void;
}

/**
 * 以 `key` 為資料身分快取一次 fetch 的結果，並在同一個 key 上做
 * in-flight 去重。`fetcher(signal)` 只在 key 沒有快取（或已被
 * `invalidate` 清掉）時才會真的被呼叫一次；同一個 key 的並發呼叫
 * 全部共用同一個 promise。
 *
 * 失敗不快取——這次失敗只讓呼叫端這次拿到 rejected promise，下一次
 * 呼叫（同一個 key）會重新真的嘗試，不會永遠卡在一次失敗的結果上。
 */
export function cachedFetch<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
): CachedFetch<T> {
  let entry = cache.get(key) as Entry<T> | undefined;
  if (!entry) {
    const controller = new AbortController();
    const created: Entry<T> = {
      controller,
      refCount: 0,
      settled: false,
      promise: undefined as unknown as Promise<T>,
    };
    created.promise = fetcher(controller.signal)
      .then((value) => {
        created.settled = true;
        return value;
      })
      .catch((e) => {
        if (cache.get(key) === (created as Entry<unknown>)) cache.delete(key);
        throw e;
      });
    cache.set(key, created as Entry<unknown>);
    entry = created;
  }
  entry.refCount += 1;
  const bound = entry;
  return {
    promise: bound.promise,
    release: () => {
      bound.refCount -= 1;
      if (bound.refCount <= 0 && !bound.settled) {
        bound.controller.abort();
        if (cache.get(key) === (bound as Entry<unknown>)) cache.delete(key);
      }
    },
  };
}

/** 清掉一個 key 的快取——下一次 `cachedFetch` 會真的重新抓。不影響
 *  正在進行中的 in-flight 呼叫（它們仍會拿到原本那個 promise 的結果，
 *  只是這次結果不再被存進快取）。 */
export function invalidate(key: string): void {
  cache.delete(key);
}

/** 把一個已知的值直接寫進快取（例如 mutation 端點回傳的最新狀態），
 *  不透過 fetch。後續同一個 key 的呼叫直接拿到這個值，不必重抓。 */
export function setCached<T>(key: string, value: T): void {
  cache.set(key, {
    controller: new AbortController(),
    refCount: 0,
    settled: true,
    promise: Promise.resolve(value),
  });
}

// ---------- 具體案例：Scenario detail／Settings／iv-history ----------

const scenarioKey = (id: string) => `scenario:${id}`;

/** 這個 scenario id 目前快取的內容實際對應哪個 `analyzed_at`——用來
 *  判斷呼叫端給的 `hintAnalyzedAt` 是「已經有」還是「比手上的新」。 */
const scenarioAnalyzedAt = new Map<string, string | null>();

/**
 * Scenario 詳細頁的資料——快取鍵是 `id`，不是 `(id, analyzedAt)`：
 * 呼叫端（`ScenarioDetail`）常常在還不知道正確 `analyzedAt` 之前就要
 * 先拿到資料（劇本庫清單還沒回來、開站刷新還沒跑完），這時候
 * `hintAnalyzedAt` 是 `null`——只要**任何**已快取的結果就夠用，不必
 * 為了「還沒對上版本」硬是重抓一次。
 *
 * 只有在 `hintAnalyzedAt` 非 `null` 且與目前快取的 `analyzed_at` 真的
 * 不同時，才視為資料已經比手上這份新、判定快取過期並重抓——這正是
 * deep-link cascade（3 次全量下載）裡唯一「真的需要」的那一次。
 */
export function getScenarioCached(
  id: string,
  hintAnalyzedAt: string | null,
): CachedFetch<ScenarioDetail> {
  const key = scenarioKey(id);
  const known = scenarioAnalyzedAt.get(id);
  if (known !== undefined && hintAnalyzedAt !== null && known !== hintAnalyzedAt) {
    invalidate(key);
  }
  return cachedFetch(key, async (signal) => {
    const detail = await getScenario(id, signal);
    scenarioAnalyzedAt.set(id, detail.latest_analyzed_at);
    return detail;
  });
}

const SETTINGS_KEY = "settings";

/** Settings——單一全站狀態，鍵是固定字串。多個元件（`IvHistory`／
 *  `Settings` 頁）各自 mount 時呼叫，只有第一個真的發請求。 */
export function getSettingsCached(): CachedFetch<SettingsView> {
  return cachedFetch(SETTINGS_KEY, (signal) => getSettings(signal));
}

/** Settings 的任何 mutation 端點都會回傳一份新的 `SettingsView`——直接
 *  拿它更新快取，不必讓下一個讀者重新打一次 `GET /api/settings`。 */
export function setSettingsCache(view: SettingsView): void {
  setCached(SETTINGS_KEY, view);
}

const ivHistoryKey = (scenarioId: string, candidateKey: string, analyzedAt: string | null) =>
  `iv-history:${scenarioId}:${candidateKey}:${analyzedAt ?? ""}`;

/** IV 歷史——鍵含 `analyzedAt`：新分析一到，即使候選 key 不變，vendor
 *  端的報價也可能已經更新，這裡刻意跟 scenario detail 的「容忍舊
 *  hint」邏輯不同（`IvHistory` 既有的重新嘗試語意本來就要求跟上
 *  `analyzedAt`，見該元件 effect 的既有依賴陣列）。 */
export function getIvHistoryCached(
  scenarioId: string,
  candidateKey: string,
  analyzedAt: string | null,
): CachedFetch<IvHistoryView> {
  return cachedFetch(
    ivHistoryKey(scenarioId, candidateKey, analyzedAt),
    (signal) => ivHistory(scenarioId, candidateKey, signal),
  );
}

/** T11（#194，兩段式補建 P3-a）：Legacy 家族的補建（`ivHistoryBackfill`）
 *  完成後，這個候選的 iv-history 快取已經過期——下一次 `getIvHistoryCached`
 *  該真的重抓，不是繼續沿用補建前拿到的那份 `backfill_pending: true`。 */
export function invalidateIvHistoryCache(
  scenarioId: string,
  candidateKey: string,
  analyzedAt: string | null,
): void {
  invalidate(ivHistoryKey(scenarioId, candidateKey, analyzedAt));
}

/** 測試專用：清空整個快取，避免測試之間互相汙染。 */
export function _resetCacheForTests(): void {
  cache.clear();
  scenarioAnalyzedAt.clear();
}
