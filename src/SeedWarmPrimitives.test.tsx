import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

/**
 * SW-01（#331）AC：「每個 primitive 至少一個元件測試證明可渲染且
 * ARIA 正確」——`.pnav`／`.pseg`／`.ptag`／`.pbar`／`.pbtn` 是純 CSS
 * class（尚無專屬消費元件，後續 SW-02～SW-05 各票會在真實畫面裡用
 * 它們），這裡驗的是消費端必須遵守的 ARIA 契約本身，不是任何一個
 * 特定畫面的行為——真正的畫面行為測試在各自票裡（例如 SW-03 會測
 * 「劇本庫的方向 segment 有 role=group」）。
 */
describe("Seed Warm primitives 的 ARIA 契約（SW-01／#331）", () => {
  it("pill segment 容器是 role=group，選中項用 aria-current 標示", () => {
    render(
      <div className="pseg" role="group" aria-label="依方向篩選">
        <button type="button" aria-current="true" className="on">
          全部
        </button>
        <button type="button">看漲</button>
      </div>,
    );

    const group = screen.getByRole("group", { name: "依方向篩選" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "看漲" })).not.toHaveAttribute(
      "aria-current",
    );
  });

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

  it("inline 比例條是 role=progressbar 並帶 aria-valuenow", () => {
    render(
      <div
        className="pbar"
        role="progressbar"
        aria-valuenow={62}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="相對最佳劇本報酬"
      >
        <i style={{ width: "62%" }} />
      </div>,
    );

    const bar = screen.getByRole("progressbar", { name: "相對最佳劇本報酬" });
    expect(bar).toHaveAttribute("aria-valuenow", "62");
  });

  it("ptag 四種狀態各自有可辨識的文字內容（不是純顏色傳遞語意）", () => {
    render(
      <ul>
        <li>
          <span className="ptag up">看漲</span>
        </li>
        <li>
          <span className="ptag down">看跌</span>
        </li>
        <li>
          <span className="ptag warn">更新中</span>
        </li>
        <li>
          <span className="ptag flat">持平</span>
        </li>
      </ul>,
    );

    for (const text of ["看漲", "看跌", "更新中", "持平"]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
  });
});
