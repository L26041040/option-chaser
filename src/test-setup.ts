import "@testing-library/jest-dom/vitest";

// jsdom 沒有實作 `window.matchMedia`——桌面／手機版面判斷（#72）靠它。
// 預設值 `matches: false`（＝手機）：本專案手機優先，既有測試全部
// 假設手機版行為，不必逐一改動就能繼續通過。桌面情境的測試自行用
// `vi.stubGlobal("matchMedia", ...)` 覆寫成 `matches: true`。
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
