import type { ReactNode } from "react";

/**
 * 手機首頁「＋ 新增劇本」就地展開入口（MVP-v2／#77、#81）。
 *
 * 桌面版的建立入口仍在工具列（#75 現狀，本票不動）；這裡是手機版專屬
 * 的第二個位置——Dashboard 佔位區下方，收合時只是一列 compact 的
 * 「＋ 新增劇本」，點擊在**原位置向下展開**成完整表單，不用 modal、
 * 不換頁（`docs/Mvp-v2.md` §3 稱之為 inline expandable composer）。
 *
 * 面板一律掛著、用 `hidden` 屬性切換可見度，不是條件渲染整個卸載重掛
 * ——沿用 #75 的既有教訓：使用者打到一半不小心點到收合鈕，剛打的字
 * 不會被清空。`aria-expanded`／`aria-controls` 沿用 `Toolbar`／
 * `MonthPicker` 既有的「展開鈕指向自己控制的面板」寫法，全站一致。
 */
export default function CreateEntry({
  open,
  panelId,
  onToggle,
  children,
}: {
  open: boolean;
  panelId: string;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="create-entry">
      <button
        className="create-entry-toggle"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
      >
        {open ? "收合建立表單" : "＋ 新增劇本"}
      </button>
      <div id={panelId} hidden={!open}>
        {children}
      </div>
    </div>
  );
}
