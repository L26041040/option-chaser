import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FIT_TEXT_MIN_PX, useFitText } from "./useFitText";

/**
 * jsdom 沒有版面：`scrollWidth`／`clientWidth` 一律是 0。這裡用一個很單純的
 * 字寬模型取代——文字寬 = 字數 × 字級 × 0.6，可視寬固定 `BOX_PX`——讓
 * hook 的「量 → 縮 → 再量」迴圈有真實的回饋可以收斂。起始字級由樣式表
 * 提供（hook 從 computed style 讀，不寫死）。
 */
const BOX_PX = 100;
let style: HTMLStyleElement;
let restoreLayout = () => {};

beforeEach(() => {
  style = document.createElement("style");
  style.textContent = ".fit { font-size: 12px; }";
  document.head.appendChild(style);
});
afterEach(() => {
  restoreLayout();
  style.remove();
});

function Probe({ text }: { text: string }) {
  const ref = useFitText<HTMLSpanElement>(text);
  return <div><span className="fit" ref={ref}>{text}</span></div>;
}

function mount(text: string) {
  // 先掛 layout 模型再 render：hook 在 layout effect（commit 當下）就量。
  const proto = HTMLElement.prototype;
  const sw = Object.getOwnPropertyDescriptor(proto, "scrollWidth");
  const cw = Object.getOwnPropertyDescriptor(proto, "clientWidth");
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      if (!this.classList.contains("fit")) return 0;
      const px = parseFloat(getComputedStyle(this).fontSize);
      return Math.ceil((this.textContent ?? "").length * px * 0.6);
    },
  });
  Object.defineProperty(proto, "clientWidth", {
    configurable: true,
    get(this: HTMLElement) {
      if (!this.classList.contains("fit")) return 0;
      return Math.min(BOX_PX, this.scrollWidth);
    },
  });
  const result = render(<Probe text={text} />);
  restoreLayout = () => {
    if (sw) Object.defineProperty(proto, "scrollWidth", sw);
    if (cw) Object.defineProperty(proto, "clientWidth", cw);
    restoreLayout = () => {};
  };
  return { ...result, el: result.container.querySelector(".fit") as HTMLElement };
}

describe("useFitText（CLAUDE-MOBILE-TEXT-FIT-001）", () => {
  it("放得下就不動：不寫 inline font-size，維持樣式表的字級", () => {
    const { el } = mount("x".repeat(10)); // 10×12×0.6 = 72 ≤ 100
    expect(el.style.fontSize).toBe("");
  });

  it("放不下就逐步縮字，停在剛好放得下的那一級（不縮過頭、不先溢出）", () => {
    // 15 字：12px 需要 108；11.5px 需要 104；11px 需要 99 → 停在 11px。
    const { el } = mount("x".repeat(15));
    expect(el.style.fontSize).toBe("11px");
    expect(el.scrollWidth).toBeLessThanOrEqual(el.clientWidth);
  });

  it(`縮到下限 ${FIT_TEXT_MIN_PX}px 仍放不下就停在下限，剩下交給 ellipsis`, () => {
    const { el } = mount("x".repeat(40)); // 10px 仍需 240
    expect(el.style.fontSize).toBe(`${FIT_TEXT_MIN_PX}px`);
    expect(el.scrollWidth).toBeGreaterThan(el.clientWidth);
  });

  it("內容變短時重新量：清掉先前縮的字級，回到樣式表原始大小", () => {
    const { el, rerender } = mount("x".repeat(40));
    expect(el.style.fontSize).toBe(`${FIT_TEXT_MIN_PX}px`);
    rerender(<Probe text={"x".repeat(5)} />);
    expect(el.style.fontSize).toBe("");
  });
});
