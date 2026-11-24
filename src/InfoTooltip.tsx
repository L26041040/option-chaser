import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { createPortal } from "react-dom";

/**
 * Info affordance（SW-01／#331，Seed Warm primitives）：把原本鋪在畫面上的
 * 大段常駐說明文字收進標題旁一顆可 focus 的小圖示（ⓘ）——SEED-WARM-SPEC-001
 * （#330）「文案降級」的共用元件，各畫面消費同一份，不是各自兜一顆 tooltip。
 *
 * V2-04（#406）起改由 JS 控制開合（原本純 CSS `:hover`／`:focus-within`
 * 做不到「手機點一下開、再點一下關、Esc 關」）：
 *
 * - 桌面：滑鼠懸停展開（只認 `pointerType === "mouse"`，手機點按不會被
 *   當成懸停）；移開後稍等一下才收，讓滑鼠能移進說明卡。
 * - 手機：點按切換開關；點說明卡以外的地方關閉。
 * - 鍵盤：Tab 聚焦即展開（沿用 SW-01 的行為）；Enter／Space 打開（不是切換）；
 *   Esc 關閉，焦點留在圖示上；Tab 離開就收起。
 * - 無障礙：圖示是原生 `<button>`、`aria-label`＝說明名稱、`aria-expanded`；
 *   展開時 `aria-describedby` 指向 `role="tooltip"` 的說明卡。說明卡不收
 *   焦點（焦點始終在圖示上），收起時不渲染。給了 `description`（純文字）時，
 *   收起狀態的 `aria-describedby` 指向一段常駐、`hidden` 的同內容文字——
 *   Tab 第一次聚焦的那一刻說明卡還沒渲染，螢幕報讀器仍能念出說明。那段
 *   文字掛在 `document.body`，不混進周圍元素的文字內容。
 * - 版面：說明卡用 portal 掛在 `document.body`、`position: fixed`，依圖示
 *   位置擺放並夾在視窗內（左右各留 16px），不會被捲動容器或表格裁切，
 *   也不會撐出橫向捲動；下方放不下時改放上方。
 */
const VIEWPORT_GUTTER = 16;
const GAP = 8;
const HOVER_CLOSE_DELAY_MS = 120;

export default function InfoTooltip({
  label,
  description,
  decorative = false,
  children,
}: {
  label: string;
  /** 只給滑鼠的視覺提示：圖示 `aria-hidden`、`tabIndex=-1`（放在 `<th>` 裡時，
   *  按鈕名稱才不會混進欄位名稱）；同一則說明必須另有一顆一般的圖示。 */
  decorative?: boolean;
  /** 說明卡的純文字版（給 `aria-describedby`，見上方「無障礙」）。 */
  description?: string;
  children: React.ReactNode;
}) {
  const id = useId();
  const descId = `${id}-desc`;
  const [hover, setHover] = useState(false);
  const [active, setActive] = useState(false);
  const open = hover || active;

  const wrapRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLSpanElement>(null);
  // 這次 focus 是不是由指標（滑鼠／手指）按下造成的：是的話交給 click
  // 切換，不要在 focus 時先打開（否則點一下會「開了又關」）。
  const pointerDown = useRef(false);
  const hoverTimer = useRef<number | null>(null);

  const clearHoverTimer = () => {
    if (hoverTimer.current !== null) {
      window.clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
    }
  };
  useEffect(() => clearHoverTimer, []);

  const close = useCallback(() => {
    clearHoverTimer();
    setHover(false);
    setActive(false);
  }, []);

  // 展開時：Esc 關閉、點外面關閉。
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Node | null;
      if (t && (wrapRef.current?.contains(t) || panelRef.current?.contains(t))) return;
      close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);

  // 擺位：fixed、夾在視窗內；捲動或縮放時跟著圖示走。
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const btn = buttonRef.current;
      const panel = panelRef.current;
      if (!btn || !panel) return;
      const r = btn.getBoundingClientRect();
      const vw = document.documentElement.clientWidth || window.innerWidth;
      const vh = window.innerHeight;
      const w = panel.offsetWidth;
      const h = panel.offsetHeight;
      const maxLeft = Math.max(VIEWPORT_GUTTER, vw - VIEWPORT_GUTTER - w);
      const left = Math.min(Math.max(r.left, VIEWPORT_GUTTER), maxLeft);
      const below = r.bottom + GAP;
      const above = r.top - GAP - h;
      const top = below + h > vh - VIEWPORT_GUTTER && above >= VIEWPORT_GUTTER ? above : below;
      panel.style.left = `${left}px`;
      panel.style.top = `${top}px`;
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  const onPointerEnter = (e: ReactPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    clearHoverTimer();
    setHover(true);
  };
  const onPointerLeave = (e: ReactPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    clearHoverTimer();
    hoverTimer.current = window.setTimeout(() => {
      hoverTimer.current = null;
      setHover(false);
    }, HOVER_CLOSE_DELAY_MS);
  };

  return (
    <span
      ref={wrapRef}
      className="pinfo"
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <button
        ref={buttonRef}
        type="button"
        className="pinfo-btn"
        aria-label={label}
        aria-hidden={decorative || undefined}
        tabIndex={decorative ? -1 : undefined}
        aria-expanded={open}
        aria-describedby={open ? id : description ? descId : undefined}
        onPointerDown={() => {
          pointerDown.current = true;
        }}
        onFocus={() => {
          if (!pointerDown.current) setActive(true);
          pointerDown.current = false;
        }}
        onBlur={(e) => {
          const next = e.relatedTarget as Node | null;
          if (next && panelRef.current?.contains(next)) return;
          setActive(false);
        }}
        onClick={(e) => {
          const fromPointer = pointerDown.current || e.detail > 0;
          pointerDown.current = false;
          if (fromPointer) {
            // 滑鼠已經懸停展開時，點一下是「釘住」；再點一下才收。
            if (hover && !active) setActive(true);
            else if (active) close();
            else setActive(true);
          } else {
            setActive(true);
          }
        }}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8h.01M11 12h1v4h1" />
        </svg>
      </button>
      {description &&
        createPortal(
          <span id={descId} hidden>
            {description}
          </span>,
          document.body,
        )}
      {open &&
        createPortal(
          <span
            ref={panelRef}
            id={id}
            role="tooltip"
            className="pinfo-panel"
            onPointerEnter={onPointerEnter}
            onPointerLeave={onPointerLeave}
            // 點說明卡本身不搶走圖示的焦點（否則 blur 會把它收起來）。
            onMouseDown={(e) => e.preventDefault()}
          >
            {children}
          </span>,
          document.body,
        )}
    </span>
  );
}
