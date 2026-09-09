import { useEffect, useState } from "react";

import { rateLimitRemainingSeconds } from "./scenarios";

/**
 * SCALE-05（#260，AC-3）：從現在起到 `deadlineIso` 還剩幾秒，每秒
 * 重新計算一次——來源永遠是同一個固定的絕對時間點（`deadlineIso`），
 * 不是遞減的本地 state，因此 rerender／props 沒變不會意外重設倒數：
 * 每一次計算都是「現在的 `Date.now()` 減去那個固定時間點」，不是
 * 「上一次顯示的數字再減一」。
 *
 * `deadlineIso` 為 `null` 時回傳 `null`（沒有倒數可言，呼叫端據此
 * 判斷要不要顯示這個區塊），也不會啟動計時器——不必要的
 * `setInterval` 只會浪費電量，且會在測試裡留下懸置的 timer。
 */
export function useCountdownSeconds(deadlineIso: string | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (deadlineIso === null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [deadlineIso]);
  if (deadlineIso === null) return null;
  return rateLimitRemainingSeconds(deadlineIso, now);
}
