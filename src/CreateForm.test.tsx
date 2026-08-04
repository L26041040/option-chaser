import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CreateForm, { validateDraft } from "./CreateForm";

describe("建立表單的驗證", () => {
  it("三欄都必填，訊息明確指出缺哪一欄", () => {
    expect(validateDraft("", "120", "2028-05")).toEqual({
      ok: false, error: "請填標的代號（例如 TLT）",
    });
    expect(validateDraft("TLT", "", "2028-05")).toEqual({
      ok: false, error: "請填目標價位",
    });
    expect(validateDraft("TLT", "120", "")).toEqual({
      ok: false, error: "請選目標年月",
    });
  });

  it("目標價位必須是大於 0 的數字", () => {
    expect(validateDraft("TLT", "abc", "2028-05")).toEqual({
      ok: false, error: "目標價位要是數字",
    });
    expect(validateDraft("TLT", "0", "2028-05")).toEqual({
      ok: false, error: "目標價位要大於 0",
    });
    expect(validateDraft("TLT", "-5", "2028-05")).toEqual({
      ok: false, error: "目標價位要大於 0",
    });
  });

  it("標的代號限制與後端同一套字元集", () => {
    expect(validateDraft("TL T", "120", "2028-05").ok).toBe(false);
    expect(validateDraft("BRK.B", "120", "2028-05").ok).toBe(true);
  });

  it("標的代號自動去空白並轉大寫", () => {
    const checked = validateDraft("  tlt ", "120.5", "2028-05");
    expect(checked).toEqual({
      ok: true,
      draft: { symbol: "TLT", target_price: 120.5, target_month: "2028-05" },
    });
  });
});

describe("建立表單的畫面", () => {
  it("三欄全部留白，沒有任何預設值", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    for (const label of ["標的代號", "目標價位", "目標年月"]) {
      expect(screen.getByLabelText(label)).toHaveValue("");
    }
  });

  it("目標年月是年月欄位，沒有「日」", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    // type=month 在手機上就是系統的年月選擇器；自刻彈窗只會更難用。
    expect(screen.getByLabelText("目標年月")).toHaveAttribute("type", "month");
  });

  it("驗證沒過就不送出，並顯示訊息", async () => {
    const onCreate = vi.fn();
    render(<CreateForm onCreate={onCreate} />);

    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("請填標的代號");
  });

  it("填好送出後把欄位清空，避免重複建立同一個劇本", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<CreateForm onCreate={onCreate} />);

    await userEvent.type(screen.getByLabelText("標的代號"), "tlt");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.type(screen.getByLabelText("目標年月"), "2028-05");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).toHaveBeenCalledWith({
      symbol: "TLT", target_price: 120, target_month: "2028-05",
    });
    expect(screen.getByLabelText("標的代號")).toHaveValue("");
    expect(screen.getByLabelText("目標價位")).toHaveValue("");
  });

  it("建立失敗時顯示後端訊息，且不清空使用者填的東西", async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error("目標月已經過完了"));
    render(<CreateForm onCreate={onCreate} />);

    await userEvent.type(screen.getByLabelText("標的代號"), "TLT");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.type(screen.getByLabelText("目標年月"), "2020-01");
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(screen.getByRole("alert")).toHaveTextContent("目標月已經過完了");
    expect(screen.getByLabelText("標的代號")).toHaveValue("TLT");
  });
});

describe("建立表單驗證的邊界（V3／#51 檢視回饋）", () => {
  it("目標年月格式不對時明講格式，不丟一個看不懂的 422 回來", () => {
    // 桌面 Safari／Firefox 的 type="month" 會退化成純文字框
    expect(validateDraft("TLT", "120", "May 2028")).toEqual({
      ok: false, error: "目標年月格式為 YYYY-MM（例如 2028-05）",
    });
    expect(validateDraft("TLT", "120", "2028-5").ok).toBe(false);
  });

  it("不把十六進位／科學記號讀成價格", () => {
    // Number("0x1f") 是 31、Number("1e5") 是 100000——都不是使用者
    // 以為自己填的那個價格
    expect(validateDraft("TLT", "0x1f", "2028-05")).toEqual({
      ok: false, error: "目標價位要是數字",
    });
    expect(validateDraft("TLT", "1e5", "2028-05")).toEqual({
      ok: false, error: "目標價位要是數字",
    });
  });
});
