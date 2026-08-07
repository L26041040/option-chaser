/**
 * 手刻 SVG 圖示（TR6／#91）：取代 emoji／純文字符號。需求方核准的手繪
 * 版面預覽提供三種風格比較（線條／實心／開蓋），採用線條風格——跟 app
 * 既有的細線視覺語彙（膠囊鈕、回上頁箭頭）同一種克制風格，全站統一
 * 套用這一款，不另外做風格切換。
 */

function TrashPath() {
  return (
    <>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </>
  );
}

/** 垃圾桶圖示。`aria-hidden`：圖示本身不帶語意，可及名稱一律交給外層
 *  按鈕的 `aria-label`（沿用既有「封存 TLT 2028-05」那套慣例）。 */
export function TrashIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="icon-glyph"
    >
      <TrashPath />
    </svg>
  );
}

/** 打勾圖示（批次選取模式的 checkbox 內容）。 */
export function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="icon-glyph"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
