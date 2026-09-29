/**
 * 意見回饋表單（CLAUDE-BETA-LAUNCH-FINAL-001）。
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const submitMock = vi.fn();

vi.mock("./api", () => ({
  FEEDBACK_NAME_MAX: 40,
  FEEDBACK_CONTENT_MAX: 2000,
  submitFeedback: (...args: unknown[]) => submitMock(...args),
}));

import FeedbackForm from "./FeedbackForm";

describe("FeedbackForm", () => {
  beforeEach(() => {
    submitMock.mockReset().mockResolvedValue({ ok: true });
  });

  it("只有稱呼與反饋內容兩個欄位，沒有分類、星等、email", () => {
    render(<FeedbackForm />);
    const region = screen.getByRole("region", { name: "意見回饋" });
    expect(screen.getByRole("textbox", { name: "稱呼" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "反饋內容" })).toBeInTheDocument();
    expect(region.querySelectorAll("input, textarea, select")).toHaveLength(2);
  });

  it("兩欄都要填（只有空白不算）才能送出", async () => {
    const user = userEvent.setup();
    render(<FeedbackForm />);
    const send = screen.getByRole("button", { name: "送出" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "稱呼" }), "小明");
    await user.type(screen.getByRole("textbox", { name: "反饋內容" }), "   ");
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "反饋內容" }), "好用");
    expect(send).not.toBeDisabled();
  });

  it("送出成功顯示感謝、清空內容欄、保留稱呼", async () => {
    const user = userEvent.setup();
    render(<FeedbackForm />);
    await user.type(screen.getByRole("textbox", { name: "稱呼" }), " 小明 ");
    await user.type(screen.getByRole("textbox", { name: "反饋內容" }), " 很好用 ");
    await user.click(screen.getByRole("button", { name: "送出" }));

    await waitFor(() => expect(submitMock).toHaveBeenCalledWith("小明", "很好用"));
    expect(await screen.findByRole("status")).toHaveTextContent("收到，謝謝你的回饋。");
    expect(screen.getByRole("textbox", { name: "反饋內容" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "稱呼" })).toHaveValue(" 小明 ");
  });

  it("送出失敗顯示錯誤、保留內容讓使用者重送", async () => {
    submitMock.mockRejectedValue(new Error("送出太頻繁，請稍後再試"));
    const user = userEvent.setup();
    render(<FeedbackForm />);
    await user.type(screen.getByRole("textbox", { name: "稱呼" }), "小明");
    await user.type(screen.getByRole("textbox", { name: "反饋內容" }), "內容");
    await user.click(screen.getByRole("button", { name: "送出" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("送出太頻繁");
    expect(screen.getByRole("textbox", { name: "反饋內容" })).toHaveValue("內容");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("輸入框有和後端一致的長度上限", () => {
    render(<FeedbackForm />);
    expect(screen.getByRole("textbox", { name: "稱呼" })).toHaveAttribute("maxLength", "40");
    expect(screen.getByRole("textbox", { name: "反饋內容" })).toHaveAttribute("maxLength", "2000");
  });
});
