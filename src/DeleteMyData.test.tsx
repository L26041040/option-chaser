/**
 * 自助刪除入口（PB-04／#296，Anonymous Public Beta）。
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const deleteMyDataMock = vi.fn();

vi.mock("./api", () => ({
  deleteMyData: (...args: unknown[]) => deleteMyDataMock(...args),
}));

import DeleteMyData from "./DeleteMyData";

describe("DeleteMyData", () => {
  beforeEach(() => {
    deleteMyDataMock.mockReset();
    window.location.hash = "";
  });

  it("does not show the confirmation dialog by default", () => {
    render(<DeleteMyData />);
    expect(
      screen.queryByRole("alertdialog"),
    ).not.toBeInTheDocument();
  });

  it("opens a confirmation dialog before deleting anything", async () => {
    const user = userEvent.setup();
    render(<DeleteMyData />);

    await user.click(screen.getByRole("button", { name: "立刻刪除我的所有資料" }));

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(/無法復原/)).toBeInTheDocument();
    expect(deleteMyDataMock).not.toHaveBeenCalled();
  });

  it("cancelling the dialog does not call the API", async () => {
    const user = userEvent.setup();
    render(<DeleteMyData />);
    await user.click(screen.getByRole("button", { name: "立刻刪除我的所有資料" }));

    await user.click(screen.getByRole("button", { name: "取消" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(deleteMyDataMock).not.toHaveBeenCalled();
  });

  it("confirming calls deleteMyData and reloads the page", async () => {
    deleteMyDataMock.mockResolvedValue(undefined);
    // jsdom 的 `location.reload` 屬性描述子是 read-only、連
    // `vi.spyOn`／直接指派都重新定義不了（`test-setup.ts` 的樁也一樣
    // 設不進去，靜靜被吞掉）——呼叫它本身不會拋錯，只會在 stderr 印一句
    // "Not implemented" 警告，因此這裡不斷言「reload 被呼叫過」，只
    // 斷言真正重要的行為：API 真的被呼叫、hash 被重設回首頁。
    const user = userEvent.setup();
    render(<DeleteMyData />);
    await user.click(screen.getByRole("button", { name: "立刻刪除我的所有資料" }));

    await user.click(screen.getByRole("button", { name: "確定刪除" }));

    await waitFor(() => expect(deleteMyDataMock).toHaveBeenCalledTimes(1));
    expect(window.location.hash).toBe("#/");
  });

  it("shows an inline error and keeps the dialog open when the request fails", async () => {
    deleteMyDataMock.mockRejectedValue(new Error("network down"));
    const user = userEvent.setup();
    render(<DeleteMyData />);
    await user.click(screen.getByRole("button", { name: "立刻刪除我的所有資料" }));

    await user.click(screen.getByRole("button", { name: "確定刪除" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("刪除失敗"),
    );
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});
