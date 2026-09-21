/**
 * SW-09（#339）全站文案掃描新增覆蓋：`RoleLogin.tsx` 本身原本沒有任何
 * 專屬測試檔（`Settings.test.tsx` 只是把它當子元件間接渲染），這裡只
 * 補這一項——不是要補齊 RoleLogin 完整行為測試（那不是這張票的範圍，
 * 既有的 `Settings.test.tsx`／後端 `AUTH-*` 測試已經覆蓋登入/登出流程）。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BANNED_JARGON } from "./bannedCopy";

vi.mock("./api", () => ({
  login: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("./fetchCache", () => ({
  getAuthStatusCached: () => ({
    promise: new Promise(() => {}), // 永遠不 resolve，測試不關心掛載後的查詢結果
    release: () => {},
  }),
  setAuthStatusCache: vi.fn(),
}));

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

  it("已登入時顯示目前身分與登出鈕，不顯示密碼欄", () => {
    render(<RoleLogin role="superadmin" onChange={vi.fn()} />);
    expect(screen.getByText(/目前身分：Super Admin/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登出" })).toBeInTheDocument();
    expect(screen.queryByLabelText("密碼")).not.toBeInTheDocument();
  });

  it("密碼欄留白時登入鈕維持 disabled", async () => {
    render(<RoleLogin role="normal" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "登入" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("密碼"), "x");
    expect(screen.getByRole("button", { name: "登入" })).toBeEnabled();
  });
});
