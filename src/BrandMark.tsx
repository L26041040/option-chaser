/**
 * OG-09（#319）：品牌標記 SVG，原本只在 `TopBar.tsx`（桌面）內部定義；
 * 手機頂欄（`MobileTopBar.tsx`）需要同一個標記，抽成共用元件而非複製
 * 第二份（OG-02 的 `/code-review` 已為 `topbarNav()` 這類重複建立過
 * 「抽共用 helper」的既有先例，這裡沿用同一種判斷、提前套用）。純呈現、
 * 無狀態、無 props。
 */
export default function BrandMark() {
  return (
    <svg
      className="brand-mark"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" />
      <path
        d="M12 2.5v3M21.5 12h-3M12 21.5v-3M2.5 12h3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
