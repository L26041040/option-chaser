import "@testing-library/jest-dom/vitest";

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
