import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import InfoTooltip from "./InfoTooltip";

function setup() {
  render(
    <>
      <InfoTooltip label="關於資料保存">
        Beta，非投資建議。資料存在瀏覽器 cookie。
      </InfoTooltip>
      <button type="button">外面的按鈕</button>
    </>,
  );
  return screen.getByRole("button", { name: "關於資料保存" });
}

const tooltip = () => screen.queryByRole("tooltip");

describe("InfoTooltip（SW-01／#331 primitives；V2-04／#406 互動）", () => {
  it("預設收起；圖示是有 aria-label 的原生按鈕", () => {
    const button = setup();
    expect(button).toHaveAttribute("aria-label", "關於資料保存");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(tooltip()).toBeNull();
  });

  it("鍵盤：Tab 聚焦即展開（aria-describedby 指向 role=tooltip），Esc 關閉、焦點留在圖示，Enter 再打開", async () => {
    const user = userEvent.setup();
    const button = setup();

    await user.tab();
    expect(button).toHaveFocus();
    const panel = screen.getByRole("tooltip");
    expect(panel).toHaveTextContent("Beta，非投資建議。資料存在瀏覽器 cookie。");
    expect(button).toHaveAttribute("aria-describedby", panel.id);
    expect(button).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");
    expect(tooltip()).toBeNull();
    expect(button).toHaveFocus();
    expect(button).not.toHaveAttribute("aria-describedby");

    await user.keyboard("{Enter}");
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    // Enter 是「打開」，不是切換：再按一次仍開著。
    await user.keyboard("{Enter}");
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    // Tab 離開就收起。
    await user.tab();
    expect(tooltip()).toBeNull();
  });

  it("手機：點按切換開關，點外面關閉", async () => {
    const user = userEvent.setup();
    const button = setup();

    await user.pointer({ keys: "[TouchA]", target: button });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    await user.pointer({ keys: "[TouchA]", target: button });
    expect(tooltip()).toBeNull();

    await user.pointer({ keys: "[TouchA]", target: button });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    await user.pointer({ keys: "[TouchA]", target: document.body });
    expect(tooltip()).toBeNull();
  });

  it("點說明卡本身不會關閉", async () => {
    const user = userEvent.setup();
    const button = setup();
    await user.pointer({ keys: "[TouchA]", target: button });
    await user.pointer({ keys: "[TouchA]", target: screen.getByRole("tooltip") });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("桌面：滑鼠懸停展開，移開收起", async () => {
    const user = userEvent.setup();
    const button = setup();
    await user.hover(button);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    await user.unhover(button);
    // 移開後有一小段延遲（讓滑鼠能移進說明卡），之後收起。
    await act(() => new Promise((r) => setTimeout(r, 250)));
    expect(tooltip()).toBeNull();
  });

  it("懸停時按 Esc 也會關閉", async () => {
    const user = userEvent.setup();
    const button = setup();
    await user.hover(button);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(tooltip()).toBeNull();
  });

  it("每個 InfoTooltip 有獨立的 id，多顆同時打開不會互相蓋掉 aria-describedby", () => {
    render(
      <>
        <InfoTooltip label="說明一">內容一</InfoTooltip>
        <InfoTooltip label="說明二">內容二</InfoTooltip>
      </>,
    );
    const first = screen.getByRole("button", { name: "說明一" });
    const second = screen.getByRole("button", { name: "說明二" });
    fireEvent.click(first, { detail: 0 });
    fireEvent.click(second, { detail: 0 });
    const [firstPanel, secondPanel] = screen.getAllByRole("tooltip");
    expect(first.getAttribute("aria-describedby")).toBe(firstPanel.id);
    expect(second.getAttribute("aria-describedby")).toBe(secondPanel.id);
    expect(firstPanel.id).not.toBe(secondPanel.id);
  });
});
