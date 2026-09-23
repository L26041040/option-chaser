/**
 * 品牌標記（SW-01／#331，Seed Warm）——取代 OG-09（#319）的
 * currentColor 十字準星圖示。Direction A artifact（#330）的 `.mark`
 * 是「terracotta 圓角方形徽章 + 白色折線圖示」，不是一枚純線條
 * icon：徽章本身的底色／圓角在 `styles.css` 的 `.brand-mark` 規則
 * （primitives 區），這裡固定畫白色折線，不再吃 `currentColor`——
 * 徽章底色已經是 accent，圖示只能是白色，沒有第二種情境需要它跟著
 * 外層文字色變。桌面 `TopBar`／手機 `MobileTopBar` 共用同一份（沿用
 * OG-09 已經抽出來的既有理由：兩處視覺必須是同一個標記，不重複
 * 定義第二份）。
 */
export default function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4 18l6-8 4 4 6-9" />
        <path d="M16 5h4v4" />
      </svg>
    </span>
  );
}
