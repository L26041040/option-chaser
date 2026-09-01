import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CreateForm, { validateDraft } from "./CreateForm";

/** 走完整個選擇器互動：展開 → 直接輸入四碼年份 → 點月份鈕（收合）。 */
async function pickMonth(year: number, month: number) {
  await userEvent.click(screen.getByLabelText("目標年月"));
  const yearInput = screen.getByLabelText("年份");
  await userEvent.clear(yearInput);
  await userEvent.type(yearInput, String(year));
  await userEvent.click(screen.getByRole("button", { name: `${month} 月` }));
}

describe("建立表單的驗證", () => {
  it("三欄都必填，訊息明確指出缺哪一欄", () => {
    expect(validateDraft("", "120", "2028-05", [])).toEqual({
      ok: false, error: "請填標的代號（例如 TLT）",
    });
    expect(validateDraft("TLT", "", "2028-05", [])).toEqual({
      ok: false, error: "請填目標價位",
    });
    expect(validateDraft("TLT", "120", "", [])).toEqual({
      ok: false, error: "請選目標年月",
    });
  });

  it("目標價位必須是大於 0 的數字", () => {
    expect(validateDraft("TLT", "abc", "2028-05", [])).toEqual({
      ok: false, error: "目標價位要是數字",
    });
    expect(validateDraft("TLT", "0", "2028-05", [])).toEqual({
      ok: false, error: "目標價位要大於 0",
    });
    expect(validateDraft("TLT", "-5", "2028-05", [])).toEqual({
      ok: false, error: "目標價位要大於 0",
    });
  });

  it("標的代號限制與後端同一套字元集", () => {
    expect(validateDraft("TL T", "120", "2028-05", ["single-leg"]).ok).toBe(false);
    expect(validateDraft("BRK.B", "120", "2028-05", ["single-leg"]).ok).toBe(true);
  });

  it("標的代號自動去空白並轉大寫", () => {
    const checked = validateDraft("  tlt ", "120.5", "2028-05", ["single-leg"]);
    expect(checked).toEqual({
      ok: true,
      draft: { symbol: "TLT", target_price: 120.5, target_month: "2028-05",
              strategies: ["single-leg"] },
    });
  });

  it("T10（#227）：至少要選一個策略類型才能送出", () => {
    expect(validateDraft("TLT", "120", "2028-05", [])).toEqual({
      ok: false, error: "請至少勾選一個策略類型",
    });
  });
});

describe("建立表單的畫面", () => {
  it("三欄全部留白，沒有任何預設值", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    expect(screen.getByLabelText("標的代號")).toHaveValue("");
    expect(screen.getByLabelText("目標價位")).toHaveValue("");
    // 年月選擇器不是原生 input，沒有 value 可查——用佔位文案表示尚未
    // 選定，不是預先選好某個年月。
    expect(screen.getByText("20xx-xx")).toBeInTheDocument();
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
    await pickMonth(2028, 5);
    await userEvent.click(screen.getByRole("checkbox", { name: "Call / Put" }));
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).toHaveBeenCalledWith({
      symbol: "TLT", target_price: 120, target_month: "2028-05",
      strategies: ["single-leg"],
    });
    expect(screen.getByLabelText("標的代號")).toHaveValue("");
    expect(screen.getByLabelText("目標價位")).toHaveValue("");
    expect(screen.getByText("20xx-xx")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Call / Put" })).not.toBeChecked();
  });

  it("建立失敗時顯示後端訊息，且不清空使用者填的東西", async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error("目標月已經過完了"));
    render(<CreateForm onCreate={onCreate} />);

    await userEvent.type(screen.getByLabelText("標的代號"), "TLT");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await pickMonth(2020, 1);
    await userEvent.click(screen.getByRole("checkbox", { name: "Call / Put" }));
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(screen.getByRole("alert")).toHaveTextContent("目標月已經過完了");
    expect(screen.getByLabelText("標的代號")).toHaveValue("TLT");
    expect(screen.getByText("2020-01")).toBeInTheDocument();
    // 失敗不清空——連 checkbox 的勾選狀態也保留，使用者不必重選一次。
    expect(screen.getByRole("checkbox", { name: "Call / Put" })).toBeChecked();
  });
});

describe("建立表單驗證的邊界（V3／#51 檢視回饋）", () => {
  it("目標年月格式不對時明講格式，不丟一個看不懂的 422 回來", () => {
    // 桌面 Safari／Firefox 的 type="month" 會退化成純文字框
    expect(validateDraft("TLT", "120", "May 2028", [])).toEqual({
      ok: false, error: "目標年月格式為 YYYY-MM（例如 2028-05）",
    });
    expect(validateDraft("TLT", "120", "2028-5", []).ok).toBe(false);
  });

  it("不把十六進位／科學記號讀成價格", () => {
    // Number("0x1f") 是 31、Number("1e5") 是 100000——都不是使用者
    // 以為自己填的那個價格
    expect(validateDraft("TLT", "0x1f", "2028-05", [])).toEqual({
      ok: false, error: "目標價位要是數字",
    });
    expect(validateDraft("TLT", "1e5", "2028-05", [])).toEqual({
      ok: false, error: "目標價位要是數字",
    });
  });
});

describe("劇本區間兩端（V7／#55）", () => {
  it("兩端都是選填，留白照樣送得出去，且不出現在送出的資料裡", () => {
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "", "")).toEqual({
      ok: true,
      draft: { symbol: "TLT", target_price: 120, target_month: "2028-05",
              strategies: ["single-leg"] },
    });
  });

  it("只填一端也可以", () => {
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "150", "")).toEqual({
      ok: true,
      draft: {
        symbol: "TLT", target_price: 120, target_month: "2028-05",
        strategies: ["single-leg"], best_price: 150,
      },
    });
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "", "100")).toEqual({
      ok: true,
      draft: {
        symbol: "TLT", target_price: 120, target_month: "2028-05",
        strategies: ["single-leg"], worst_price: 100,
      },
    });
  });

  it("方向填反了要當場擋下，不要等後端回 422", () => {
    // 與後端 `_ends_must_straddle_the_target` 同一套規則：看漲劇本必然是
    // 最低 <= 目標 <= 最高。前端先擋只是為了省一趟往返，後端仍是權威。
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "110", "")).toEqual({
      ok: false, error: "最高價位不可低於目標價",
    });
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "", "130")).toEqual({
      ok: false, error: "最低價位不可高於目標價",
    });
  });

  it("兩端等於目標價是允許的（＝這一端沒有想像空間，是有意義的主張）", () => {
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "120", "120").ok)
      .toBe(true);
  });

  it("兩端也要是數字", () => {
    expect(validateDraft("TLT", "120", "2028-05", ["single-leg"], "abc", "")).toEqual({
      ok: false, error: "最高價位要是數字",
    });
  });

  it("畫面上兩端欄位同樣留白、且標示為選填", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    expect(screen.getByLabelText("最高價位（選填）")).toHaveValue("");
    expect(screen.getByLabelText("最低價位（選填）")).toHaveValue("");
  });
});

describe("Strategy Family 勾選（T10／#227，Initial V2）", () => {
  it("三個 family 都看得到，沒有預設勾選", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    for (const label of ["Call / Put", "Vertical Spread", "Butterfly"]) {
      const box = screen.getByRole("checkbox", { name: label });
      expect(box).toBeInTheDocument();
      expect(box).not.toBeChecked();
    }
  });

  it("可以同時勾選多個 family", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<CreateForm onCreate={onCreate} />);
    await userEvent.type(screen.getByLabelText("標的代號"), "TLT");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await pickMonth(2028, 5);
    await userEvent.click(screen.getByRole("checkbox", { name: "Call / Put" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Vertical Spread" }));
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      strategies: ["single-leg", "vertical-spread"],
    }));
  });

  it("再點一次可以取消勾選", async () => {
    render(<CreateForm onCreate={vi.fn()} />);
    const box = screen.getByRole("checkbox", { name: "Call / Put" });
    await userEvent.click(box);
    expect(box).toBeChecked();
    await userEvent.click(box);
    expect(box).not.toBeChecked();
  });

  it("一個都沒勾就送出，顯示明確的錯誤訊息、不呼叫 onCreate", async () => {
    const onCreate = vi.fn();
    render(<CreateForm onCreate={onCreate} />);
    await userEvent.type(screen.getByLabelText("標的代號"), "TLT");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await pickMonth(2028, 5);
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("請至少勾選一個策略類型");
  });

  it("建立模式沒有任何劇本可比對方向，不顯示任何不可選原因", () => {
    render(<CreateForm onCreate={vi.fn()} />);
    expect(screen.queryByText(/這個策略家族/)).not.toBeInTheDocument();
  });

  it("編輯模式預填目前勾選的 family", () => {
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={vi.fn()}
                       editing={{
                         id: "s1", symbol: "TLT", target_price: 120,
                         target_month: "2028-05", best_price: null,
                         worst_price: null,
                         strategies: ["vertical-spread"],
                         family_eligibility: null,
                       }} />);
    expect(screen.getByRole("checkbox", { name: "Call / Put" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Vertical Spread" })).toBeChecked();
  });

  it("編輯模式顯示不可選的 family 與原因——checkbox 本身仍可勾選，" +
     "不是禁止勾選（AC：只有可選／不可選兩種事實陳述，不是推薦）", () => {
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={vi.fn()}
                       editing={{
                         id: "s1", symbol: "TLT", target_price: 120,
                         target_month: "2028-05", best_price: null,
                         worst_price: null,
                         strategies: ["vertical-spread"],
                         family_eligibility: {
                           "single-leg": { family: "single-leg", eligible: true,
                                          reason: null },
                           "vertical-spread": { family: "vertical-spread",
                                               eligible: true, reason: null },
                           "butterfly": { family: "butterfly", eligible: false,
                                         reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
                         },
                       }} />);
    expect(screen.getByText(
      "這個策略家族目前還沒有任何已啟用的具體結構。")).toBeInTheDocument();
    const butterflyBox = screen.getByRole("checkbox", { name: /Butterfly/ });
    expect(butterflyBox).toBeEnabled();
    expect(butterflyBox).not.toBeChecked();
  });

  it("編輯模式下可選的 family 不顯示任何原因文字", () => {
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={vi.fn()}
                       editing={{
                         id: "s1", symbol: "TLT", target_price: 120,
                         target_month: "2028-05", best_price: null,
                         worst_price: null,
                         strategies: ["vertical-spread"],
                         family_eligibility: {
                           "single-leg": { family: "single-leg", eligible: true,
                                          reason: null },
                           "vertical-spread": { family: "vertical-spread",
                                               eligible: true, reason: null },
                           "butterfly": { family: "butterfly", eligible: false,
                                         reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
                         },
                       }} />);
    const singleLegLabel = screen.getByRole("checkbox", { name: "Call / Put" })
      .closest("label")!;
    expect(within(singleLegLabel).queryByText(/這個策略家族/)).not.toBeInTheDocument();
  });

  it("編輯模式下，舊劇本已正規化的 family 值不改動任何 checkbox 直接" +
     "送出，onSaveEdit 收到的仍是合法 family 代碼（REPAIR-02／#239 " +
     "round trip：正規化只做在讀取端，本元件消費到的 `editing.strategies` " +
     "必須已經是 family 代碼——checkbox 才會正確顯示已勾選，"+
     "不改動直接儲存才會送出合法值，不是前端自己再做一次 legacy→family " +
     "映射）", async () => {
    const onSaveEdit = vi.fn().mockResolvedValue(undefined);
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={onSaveEdit}
                       editing={{
                         id: "legacy-1", symbol: "XYZ", target_price: 130,
                         target_month: "2026-09", best_price: null,
                         worst_price: null,
                         strategies: ["vertical-spread"],
                         family_eligibility: null,
                       }} />);
    expect(screen.getByRole("checkbox", { name: "Vertical Spread" }))
      .toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "儲存變更" }));

    expect(onSaveEdit).toHaveBeenCalledWith("legacy-1",
      expect.objectContaining({ strategies: ["vertical-spread"] }));
  });

  it("`/code-review` Spec 軸的發現：正規化只在後端做一次，本元件收到" +
     "真正未正規化的 legacy subtype 字串（例如 \"bull-call-spread\"）" +
     "時不會自己再做一次映射——這是刻意的架構邊界（OD-01「只修讀取端」" +
     "＝後端），不是遺漏。這條測試把這個邊界寫成可執行的斷言：本元件" +
     "拿到真正的 legacy 字串，checkbox 顯示未勾選，證明沒有隱藏的第二套" +
     "正規化邏輯悄悄掩蓋掉後端萬一回歸的情況", () => {
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={vi.fn()}
                       editing={{
                         id: "legacy-1", symbol: "XYZ", target_price: 130,
                         target_month: "2026-09", best_price: null,
                         worst_price: null,
                         strategies: ["bull-call-spread"],
                         family_eligibility: null,
                       }} />);
    expect(screen.getByRole("checkbox", { name: "Vertical Spread" }))
      .not.toBeChecked();
  });

  it("畫面不出現任何推薦／不推薦字眼（AC：只有可選與不可選兩種狀態）", () => {
    render(<CreateForm onCreate={vi.fn()} onSaveEdit={vi.fn()}
                       editing={{
                         id: "s1", symbol: "TLT", target_price: 120,
                         target_month: "2028-05", best_price: null,
                         worst_price: null,
                         strategies: ["vertical-spread"],
                         family_eligibility: {
                           "single-leg": { family: "single-leg", eligible: true,
                                          reason: null },
                           "vertical-spread": { family: "vertical-spread",
                                               eligible: true, reason: null },
                           "butterfly": { family: "butterfly", eligible: false,
                                         reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
                         },
                       }} />);
    const text = document.body.textContent ?? "";
    for (const banned of ["推薦", "較適合", "Weak Fit", "Recommended"]) {
      expect(text).not.toContain(banned);
    }
  });
});

describe("自製年月選擇器（#71）", () => {
  // 固定「今天」才能決定性地驗證「展開預設今年」「當月有 current state」
  // ——沿用全站零 wall-clock 於元件內、由呼叫端傳入的既有原則。
  const TODAY = new Date("2026-08-05T12:00:00");

  function renderForm(onCreate = vi.fn()) {
    render(<CreateForm onCreate={onCreate} today={TODAY} />);
    return onCreate;
  }

  it("關閉狀態顯示 20xx 年份格式提示，不是空白也不是某個預設年月", () => {
    renderForm();
    expect(screen.getByText("20xx-xx")).toBeInTheDocument();
  });

  it("點欄位本身就在下方就地展開，不需要按任何圖示", async () => {
    renderForm();
    const toggle = screen.getByLabelText("目標年月");
    expect(screen.queryByRole("group", { name: "選擇年月" })).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);

    expect(screen.getByRole("group", { name: "選擇年月" })).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("再次點欄位可以手動收合", async () => {
    renderForm();
    const toggle = screen.getByLabelText("目標年月");
    await userEvent.click(toggle);
    await userEvent.click(toggle);

    expect(screen.queryByRole("group", { name: "選擇年月" })).not.toBeInTheDocument();
  });

  it("展開時預設落在今年", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    expect(screen.getByLabelText("年份")).toHaveValue("2026");
  });

  it("直接提供全部 12 個月份的按鈕", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    for (let m = 1; m <= 12; m++) {
      expect(screen.getByRole("button", { name: `${m} 月` })).toBeInTheDocument();
    }
  });

  it("本月有清楚的 current state，其餘月份沒有", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    expect(screen.getByRole("button", { name: "8 月" }))
      .toHaveAttribute("aria-current", "date");
    expect(screen.getByRole("button", { name: "7 月" }))
      .not.toHaveAttribute("aria-current");
  });

  it("點月份即選定並收合，欄位換成 YYYY-MM", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    await userEvent.click(screen.getByRole("button", { name: "5 月" }));

    expect(screen.queryByRole("group", { name: "選擇年月" })).not.toBeInTheDocument();
    expect(screen.getByText("2026-05")).toBeInTheDocument();
  });

  it("年份可用箭頭往前往後切換，沒有硬編的上下限", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));

    await userEvent.click(screen.getByRole("button", { name: "下一年" }));
    expect(screen.getByLabelText("年份")).toHaveValue("2027");

    for (let i = 0; i < 10; i++) {
      await userEvent.click(screen.getByRole("button", { name: "上一年" }));
    }
    expect(screen.getByLabelText("年份")).toHaveValue("2017");
  });

  it("年份可以直接輸入四碼跳到指定年份", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    const yearInput = screen.getByLabelText("年份");

    await userEvent.clear(yearInput);
    await userEvent.type(yearInput, "2030");
    await userEvent.click(screen.getByRole("button", { name: "1 月" }));

    expect(screen.getByText("2030-01")).toBeInTheDocument();
  });

  it("聚焦年份欄位時只選取後兩碼，打兩碼就換到另一個 20xx 年——" +
     "不必先刪掉前面的「20」", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    const yearInput = screen.getByLabelText("年份") as HTMLInputElement;

    yearInput.focus();
    expect(yearInput.selectionStart).toBe(2);
    expect(yearInput.selectionEnd).toBe(4);

    await userEvent.keyboard("30");
    expect(yearInput).toHaveValue("2030");
  });

  it("已有選定值時再次展開，回到那個值的年份，不是回到今年", async () => {
    renderForm();
    await userEvent.click(screen.getByLabelText("目標年月"));
    await userEvent.click(screen.getByRole("button", { name: "下一年" }));
    await userEvent.click(screen.getByRole("button", { name: "3 月" })); // 選定 2027-03

    await userEvent.click(screen.getByLabelText("目標年月")); // 再次展開

    expect(screen.getByLabelText("年份")).toHaveValue("2027");
    expect(screen.getByRole("button", { name: "3 月" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("鍵盤可以完成整個選取流程——展開、Tab 到月份鈕、Enter 選定", async () => {
    renderForm();
    const toggle = screen.getByLabelText("目標年月");
    toggle.focus();
    await userEvent.keyboard("{Enter}");

    await userEvent.tab(); // 上一年
    await userEvent.tab(); // 年份
    await userEvent.tab(); // 下一年
    await userEvent.tab(); // 1 月
    expect(screen.getByRole("button", { name: "1 月" })).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(screen.getByText("2026-01")).toBeInTheDocument();
  });

  it("選定後焦點回到欄位本身，不會掉到頁面最上方", async () => {
    renderForm();
    const toggle = screen.getByLabelText("目標年月");
    await userEvent.click(toggle);
    await userEvent.click(screen.getByRole("button", { name: "5 月" }));

    expect(toggle).toHaveFocus();
  });

  it("目標年月已過完的既有擋下規則不受影響——選過去的年月照樣送得出去，" +
     "由後端判斷是否拒絕", async () => {
    const onCreate = renderForm();
    await userEvent.type(screen.getByLabelText("標的代號"), "TLT");
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await pickMonth(2020, 1);
    await userEvent.click(screen.getByRole("checkbox", { name: "Call / Put" }));
    await userEvent.click(screen.getByRole("button", { name: "建立" }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ target_month: "2020-01" }));
  });
});
