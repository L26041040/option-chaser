import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

/**
 * SW-01（#331）AC：「每個 primitive 至少一個元件測試證明可渲染且
 * ARIA 正確」——`.pnav`／`.pseg`／`.ptag`／`.pbar`／`.pbtn` 當時是純
 * CSS class（尚無專屬消費元件，SW-01 檔頭原本設想後續 SW-02～SW-05
 * 各票會在真實畫面裡用它們），這裡驗的是消費端必須遵守的 ARIA 契約
 * 本身，不是任何一個特定畫面的行為。
 *
 * SW-09（#339）contract 階段收尾時盤點：`.pnav`／`.pbtn` 確實被真實
 * 畫面採用（`TopBar.tsx`／全站按鈕），但 `.pseg`／`.ptag`／`.pbar`
 * 到 SW-08 為止從未被任何畫面消費——方向 segment／狀態徽章／比例條
 * 這三個位置，SW-02～SW-08 全程沿用「既有 primitives 對照表」指名的
 * 既有 `.seg`／`.tag.up`／`.down`／`.flat`，不是這裡新造的三個
 * class，`styles.css` 已把這三組宣告當成死 CSS 一併刪除。這裡只保留
 * 真的被採用的 `.pnav`／`.pbtn` 兩組 ARIA 契約測試；`.pseg`／`.ptag`／
 * `.pbar` 原本要驗的 ARIA 模式（`role=group`＋`aria-current`、
 * `role=progressbar`＋`aria-valuenow`、可辨識文字而非純顏色）仍然是
 * 正確的通用寫法，只是不再綁著這三個已經刪除的 class 名稱示範。
 */
describe("Seed Warm primitives 的 ARIA 契約（SW-01／#331）", () => {
  it("pill 導覽的目前頁用 aria-current=page 標示", () => {
    render(
      <nav className="pnav" aria-label="主導覽">
        <a href="#library" aria-current="page">
          劇本庫
        </a>
        <a href="#trash">垃圾桶</a>
      </nav>,
    );

    expect(screen.getByRole("link", { name: "劇本庫" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "垃圾桶" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("pbtn 停用狀態用原生 disabled，不是只有視覺變灰", () => {
    render(
      <button type="button" className="pbtn dis" disabled>
        移入垃圾桶
      </button>,
    );

    expect(screen.getByRole("button", { name: "移入垃圾桶" })).toBeDisabled();
  });
});
