/**
 * jsdom 沒有版面：`scrollWidth`／`clientWidth` 一律是 0、也不會自己載入
 * `styles.css`。量測型的測試（CLAUDE-MOBILE-TEXT-FIT-001 的 `useFitText`）
 * 用這兩個 helper 補上最小的版面模型；兩者都回傳還原函式，呼叫端在
 * `afterEach`／`finally` 裡呼叫。
 */

export interface ElementWidths {
  scrollWidth: number;
  clientWidth: number;
}

const WIDTH_PROPS = ["scrollWidth", "clientWidth"] as const;

/** 讓 `measure` 決定每個元素的寬度；回傳 `null` 的元素維持 jsdom 的 0。
 *  jsdom 把這兩個 getter 定義在 `Element.prototype`，這裡疊在
 *  `HTMLElement.prototype` 上，還原時刪掉疊上去的那層即可。 */
export function mockElementWidths(
  measure: (el: HTMLElement) => ElementWidths | null,
): () => void {
  const proto = HTMLElement.prototype;
  const saved = WIDTH_PROPS.map(
    (prop) => [prop, Object.getOwnPropertyDescriptor(proto, prop)] as const);
  for (const prop of WIDTH_PROPS) {
    Object.defineProperty(proto, prop, {
      configurable: true,
      get(this: HTMLElement) { return measure(this)?.[prop] ?? 0; },
    });
  }
  return () => {
    for (const [prop, descriptor] of saved) {
      if (descriptor) Object.defineProperty(proto, prop, descriptor);
      else delete (proto as unknown as Record<string, unknown>)[prop];
    }
  };
}

/** 把一段 CSS 掛進 jsdom 的 `<head>`，讓 `getComputedStyle` 讀得到字級。 */
export function injectStylesheet(css: string): () => void {
  const sheet = document.createElement("style");
  sheet.textContent = css;
  document.head.appendChild(sheet);
  return () => sheet.remove();
}

/** 手機劇本卡的兩個縮字 target（`.compact-target`／`.compact-strategy-pill`）
 *  一律放不下（內容 500px、可視 100px），其餘元素維持 0；起始字級由呼叫端
 *  傳入的真正 `styles.css` 提供。用來驗證縮字機制掛在哪些 DOM target 上。 */
export function mockOverflowingCardText(stylesCss: string): () => void {
  const removeSheet = injectStylesheet(stylesCss);
  const restoreWidths = mockElementWidths((el) =>
    el.matches(".compact-target, .compact-strategy-pill")
      ? { scrollWidth: 500, clientWidth: 100 } : null);
  return () => {
    restoreWidths();
    removeSheet();
  };
}
