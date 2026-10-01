import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { injectStylesheet, mockElementWidths } from "./layout.fixtures";
import { FIT_TEXT_MIN_PX, useFitText } from "./useFitText";

/**
 * 字寬模型：文字寬 = 字數 × 字級 × 0.6，可視寬固定 `BOX_PX`——讓 hook
 * 的「量 → 縮 → 再量」迴圈有真實的回饋可以收斂。起始字級由樣式表提供
 * （hook 從 computed style 讀，不寫死）。
 */
const BOX_PX = 100;
let restores: Array<() => void> = [];

afterEach(() => {
  restores.forEach((restore) => restore());
  restores = [];
});

function Probe({ text }: { text: string }) {
  const ref = useFitText<HTMLSpanElement>(text);
  return <div><span className="fit" ref={ref}>{text}</span></div>;
}

function mount(text: string) {
  // 先掛版面模型再 render：hook 在 layout effect（commit 當下）就量。
  restores.push(injectStylesheet(".fit { font-size: 12px; }"));
  restores.push(mockElementWidths((el) => {
    if (!el.classList.contains("fit")) return null;
    const px = parseFloat(getComputedStyle(el).fontSize);
    const textWidth = Math.ceil((el.textContent ?? "").length * px * 0.6);
    return { scrollWidth: textWidth, clientWidth: Math.min(BOX_PX, textWidth) };
  }));
  const result = render(<Probe text={text} />);
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

  it("還原函式真的把 jsdom 的寬度 getter 還回去（不污染同檔後續測試）", () => {
    const restore = mockElementWidths(() => ({ scrollWidth: 500, clientWidth: 100 }));
    expect(document.createElement("span").scrollWidth).toBe(500);
    restore();
    expect(document.createElement("span").scrollWidth).toBe(0);
    expect(Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth"))
      .toBeUndefined();
  });
});
