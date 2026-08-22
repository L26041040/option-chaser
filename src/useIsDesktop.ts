import { useEffect, useState } from "react";

// 桌面／手機斷點——與 `styles.css` 的 `@media (min-width: 1100px)` 同一個
// 數字，兩邊各自維護一份（CSS 沒辦法直接讀 JS 常數），改動時要一起改。
// 1100 不是隨手取的：`styles.css` 的 20/80 版面下限（220px）恰好是
// 1100 的 20%，斷點與下限彼此對齊，比例才會在整個桌面寬度範圍內都
// 貼近「約 20%」，而不是被下限卡死在一個更寬的固定值上。
export const DESKTOP_QUERY = "(min-width: 1100px)";

/**
 * 桌面／手機斷點判斷（#72 起）——原本只活在 `App.tsx` 裡（真正的
 * master/detail 版面），Historical IV 手機圖表瘦身（`./IvTrend`）需要
 * 同一個判斷來決定走勢圖高度，因此抽成共用模組，不重寫第二份
 * `matchMedia` 邏輯。用 `matchMedia` 而不是只用 CSS：呼叫端有時需要在
 * JS 層面（例如 SVG `viewBox` 的實際高度）依斷點分流，CSS `display:none`
 * 隱藏不了「同一個元件在兩種斷點畫出不同高度的圖」這件事。
 */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => window.matchMedia(DESKTOP_QUERY).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY);
    const sync = () => setIsDesktop(mql.matches);
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);
  return isDesktop;
}
