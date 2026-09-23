import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import InfoTooltip from "./InfoTooltip";

describe("InfoTooltip（SW-01／#331 primitives）", () => {
  it("按鈕鍵盤可 focus，focus 後說明卡對可及性樹可見（aria-describedby 連結）", async () => {
    render(
      <InfoTooltip label="關於資料保存">
        Beta，非投資建議。資料存在瀏覽器 cookie。
      </InfoTooltip>,
    );

    const button = screen.getByRole("button", { name: "關於資料保存" });
    const panel = screen.getByRole("tooltip");

    expect(button).toHaveAttribute("aria-describedby", panel.id);
    expect(panel).toHaveTextContent(
      "Beta，非投資建議。資料存在瀏覽器 cookie。",
    );

    // 鍵盤（Tab）可以 focus 到按鈕——不靠滑鼠 hover 也能觸發
    // `:focus-within` 展開（CSS 行為本身在 `styles.css` 驗證，這裡只
    // 驗證按鈕本身確實是鍵盤可到達的原生互動元素）。
    await userEvent.tab();
    expect(button).toHaveFocus();
  });

  it("每個 InfoTooltip 有獨立的 id，多顆同時存在不會互相蓋掉 aria-describedby", () => {
    render(
      <>
        <InfoTooltip label="說明一">內容一</InfoTooltip>
        <InfoTooltip label="說明二">內容二</InfoTooltip>
      </>,
    );

    const [firstButton, secondButton] = screen.getAllByRole("button");
    const [firstPanel, secondPanel] = screen.getAllByRole("tooltip");

    expect(firstButton.getAttribute("aria-describedby")).toBe(firstPanel.id);
    expect(secondButton.getAttribute("aria-describedby")).toBe(secondPanel.id);
    expect(firstPanel.id).not.toBe(secondPanel.id);
  });
});
