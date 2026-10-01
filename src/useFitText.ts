import { useLayoutEffect, useRef } from "react";

/** 手機劇本卡的縮字下限：再小就難以閱讀，寧可交給 CSS 的 ellipsis。 */
export const FIT_TEXT_MIN_PX = 10;
const STEP_PX = 0.5;

/**
 * 把單行文字縮到剛好放得下：先量 `scrollWidth > clientWidth`，放不下時把
 * 字級從 CSS 定義的大小開始每次縮 `STEP_PX`，直到放得下或到達 `minPx`。
 * 縮到下限仍放不下時保留下限字級，剩下的交給元素既有的
 * `overflow:hidden；text-overflow:ellipsis` 收尾。
 *
 * - 起始字級一律從 CSS 讀（先清掉 inline `font-size` 再讀 computed
 *   style），樣式表仍是字級的唯一來源，這裡只負責在空間不足時往下調。
 * - 容器寬度變了（旋轉、視窗縮放）或 web font 載入完成（字寬改變）都
 *   重新量一次。觀察的是父元素：元素自己的寬度會隨字級變動
 *   （例如 inline-block 的 pill），觀察它會自己觸發自己。
 * - `contentKey` 變了（文字內容不同）也重新量。
 *
 * 元素必須是單行（`white-space:nowrap`）且 `overflow` 非 visible，
 * `scrollWidth` 才量得出溢出量。
 */
export function useFitText<T extends HTMLElement>(
  contentKey: string, minPx: number = FIT_TEXT_MIN_PX,
) {
  const ref = useRef<T>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const fit = () => {
      el.style.fontSize = "";
      let size = parseFloat(getComputedStyle(el).fontSize);
      if (!Number.isFinite(size)) return;
      while (el.scrollWidth > el.clientWidth && size - STEP_PX >= minPx) {
        size -= STEP_PX;
        el.style.fontSize = `${size}px`;
      }
    };

    fit();
    let cancelled = false;
    document.fonts?.ready.then(() => { if (!cancelled) fit(); });
    const parent = el.parentElement;
    const observer = parent && typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(fit) : null;
    if (observer && parent) observer.observe(parent);
    return () => {
      cancelled = true;
      observer?.disconnect();
    };
  }, [contentKey, minPx]);

  return ref;
}
