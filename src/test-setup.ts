import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";
import { _resetCacheForTests } from "./fetchCache";

// T03（#187）：`fetchCache` 是模組層級的單例快取，會在測試之間持續
// 存在——不清空的話，前一個測試 mock 的回應會被後一個測試沿用，兩者
// 互相汙染。每個測試結束都清空，回到「這個測試自己決定 mock 什麼」
// 的既有假設。
afterEach(() => {
  _resetCacheForTests();
});

/**
 * jsdom 沒有實作 `window.matchMedia`——桌面／手機版面判斷（#72）靠它。
 * 這裡是唯一一份假的 `MediaQueryList` 實作，`App.test.tsx` 要模擬桌面
 * 寬度時呼叫這個工廠而不是自己重寫一份，兩邊才不會各自維護一份
 * 「同一個 mock 物件形狀」而悄悄長歪。
 */
export function fakeMediaQueryList(matches: boolean, query = ""): MediaQueryList {
  return {
    matches,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  } as unknown as MediaQueryList;
}

// 預設值 `matches: false`（＝手機）：本專案手機優先，既有測試全部
// 假設手機版行為，不必逐一改動就能繼續通過。桌面情境的測試自行用
// `vi.stubGlobal("matchMedia", ...)` 覆寫成 `matches: true`
// （見 `fakeMediaQueryList`）。
if (!window.matchMedia) {
  window.matchMedia = ((query: string) =>
    fakeMediaQueryList(false, query)) as unknown as typeof window.matchMedia;
}

// jsdom 的 `window.scrollTo` 只是個會在 stderr 噴 "Not implemented" 警告
// 的樁——手機版返回劇本庫還原捲動位置（MVP-v2／#77、#83）會呼叫它。
// 換成真的無副作用函式，雜訊才不會蓋掉測試輸出裡真正的錯誤。
window.scrollTo = (() => {}) as typeof window.scrollTo;
