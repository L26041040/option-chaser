/**
 * SW-09（#339）全站文案掃描新增覆蓋：`RoleLogin.tsx` 本身原本沒有任何
 * 專屬測試檔（`Settings.test.tsx` 只是把它當子元件間接渲染），這裡只
 * 補這一項——不是要補齊 RoleLogin 完整行為測試（那不是這張票的範圍，
 * 既有的 `Settings.test.tsx`／後端 `AUTH-*` 測試已經覆蓋登入/重設權限流程）。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BANNED_JARGON } from "./bannedCopy";

vi.mock("./api", () => ({
  login: vi.fn(),
  resetRole: vi.fn(),
}));
vi.mock("./accountSwitch", () => ({
  reloadAfterAccountSwitch: vi.fn(),
}));
vi.mock("./fetchCache", () => ({
  getAuthStatusCached: () => ({
    promise: new Promise(() => {}), // 永遠不 resolve，測試不關心掛載後的查詢結果
    release: () => {},
  }),
  setAuthStatusCache: vi.fn(),
}));

import { reloadAfterAccountSwitch } from "./accountSwitch";
import { login, resetRole } from "./api";
import RoleLogin from "./RoleLogin";

describe("文案去術語（SW-09／#339 全站掃描）", () => {
  it("Normal User 未登入時的登入表單文字不含開發者詞彙", () => {
    const { container } = render(<RoleLogin role="normal" onChange={vi.fn()} />);
    const text = container.textContent ?? "";
    for (const banned of BANNED_JARGON) {
      expect(text).not.toContain(banned);
    }
  });

  it("已登入（Super User）狀態下的文字也不含開發者詞彙", () => {
    const { container } = render(<RoleLogin role="superuser" onChange={vi.fn()} />);
    const text = container.textContent ?? "";
    for (const banned of BANNED_JARGON) {
      expect(text).not.toContain(banned);
    }
  });
});

describe("基本渲染（補齊零覆蓋缺口）", () => {
  it("未登入時顯示密碼欄與登入鈕", () => {
    render(<RoleLogin role="normal" onChange={vi.fn()} />);
    expect(screen.getByLabelText("密碼")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登入" })).toBeInTheDocument();
  });

  it("已登入時顯示目前身分與重設權限鈕，不顯示密碼欄", () => {
    render(<RoleLogin role="superadmin" onChange={vi.fn()} />);
    expect(screen.getByText(/目前身分：Super Admin/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重設為 Normal User" })).toBeInTheDocument();
    expect(screen.queryByLabelText("密碼")).not.toBeInTheDocument();
  });

  it("密碼欄留白時登入鈕維持 disabled", async () => {
    render(<RoleLogin role="normal" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "登入" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("密碼"), "x");
    expect(screen.getByRole("button", { name: "登入" })).toBeEnabled();
  });
});

describe("登入／登出主帳號後整頁換身分（CROSS-DEVICE-ACCOUNT-001）", () => {
  it("登入成功：更新角色後整頁重新載入", async () => {
    vi.mocked(login).mockResolvedValueOnce({ role: "superuser" });
    vi.mocked(reloadAfterAccountSwitch).mockClear();
    const onChange = vi.fn();
    render(<RoleLogin role="normal" onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("密碼"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(login).toHaveBeenCalledWith("pw");
    expect(onChange).toHaveBeenCalledWith("superuser");
    expect(reloadAfterAccountSwitch).toHaveBeenCalledTimes(1);
  });

  it("密碼錯誤：顯示錯誤、不重新載入", async () => {
    vi.mocked(login).mockRejectedValueOnce(new Error("unauthorized"));
    vi.mocked(reloadAfterAccountSwitch).mockClear();
    render(<RoleLogin role="normal" onChange={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("密碼"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unauthorized");
    expect(reloadAfterAccountSwitch).not.toHaveBeenCalled();
  });

  it("重設（登出主帳號）：回到 Normal 後整頁重新載入", async () => {
    vi.mocked(resetRole).mockResolvedValueOnce({ role: "normal" });
    vi.mocked(reloadAfterAccountSwitch).mockClear();
    const onChange = vi.fn();
    render(<RoleLogin role="superuser" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "重設為 Normal User" }));
    expect(onChange).toHaveBeenCalledWith("normal");
    expect(reloadAfterAccountSwitch).toHaveBeenCalledTimes(1);
  });
});
