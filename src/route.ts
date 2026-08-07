/**
 * 路由（V5／#53）：只有兩個畫面（劇本庫、劇本詳細頁），用網址 hash 表示。
 *
 * 不引進路由套件，也不用一個 `useState` 記「現在在哪一頁」：hash 進了
 * 瀏覽歷史，手機上的返回手勢／返回鍵就自然可用，詳細頁的網址也能直接
 * 貼給自己（重新整理後仍在同一頁）。純狀態版本這三件事全都做不到。
 */

/** 劇本詳細頁的 hash。 */
export function detailHash(id: string): string {
  return `#/s/${encodeURIComponent(id)}`;
}

/**
 * 從 hash 解出要顯示的劇本 id；不是詳細頁就回 null（＝劇本庫）。
 * 認不得的 hash 一律當成劇本庫，不留在一個空白畫面上。
 */
export function scenarioIdFromHash(hash: string): string | null {
  const hit = /^#\/s\/(.+)$/.exec(hash);
  return hit ? decodeURIComponent(hit[1]) : null;
}

/** 垃圾桶畫面的 hash（TR6／#91）。跟詳細頁同一套「進了瀏覽歷史」的
 *  理由：返回手勢／返回鍵可用，網址可以直接貼給自己。 */
export function trashHash(): string {
  return "#/trash";
}

/** 目前是不是在垃圾桶畫面。 */
export function isTrashHash(hash: string): boolean {
  return hash === trashHash();
}
