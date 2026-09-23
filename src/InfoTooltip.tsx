import { useId } from "react";

/**
 * Info affordance（SW-01／#331，Seed Warm primitives）：把原本鋪在
 * 畫面上的大段常駐說明文字（Beta／資料保存／免責）收進標題旁一顆
 * 可 focus 的小圖示，hover 或鍵盤 focus 才展開說明卡——SEED-WARM-
 * SPEC-001（#330）「文案降級」的共用元件，SW-03／SW-04／SW-07 皆會
 * 消費同一份，不是各自兜一顆 tooltip。
 *
 * 純 CSS 控制顯示（`.pinfo:hover`／`.pinfo:focus-within`，見
 * `styles.css`），不用 JS 開關狀態——按 Tab 鍵盤就能 focus 到
 * `.pinfo-btn`（原生 `<button>`），瀏覽器內建的 focus 事件即會觸發
 * `:focus-within`，不需要額外的 `onFocus`／`onBlur` handler、也不會
 * 有「JS 狀態與 CSS 顯示狀態兜不起來」的問題。`aria-describedby`
 * 讓螢幕報讀器在 focus 到按鈕時就唸出說明卡內容，不必等使用者真的
 * 觸發任何開合動作。
 */
export default function InfoTooltip({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <span className="pinfo">
      <button type="button" className="pinfo-btn" aria-describedby={id}>
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
        <span className="sr-only">{label}</span>
      </button>
      <span id={id} role="tooltip" className="pinfo-panel">
        {children}
      </span>
    </span>
  );
}
