/**
 * Super Admin 意見回饋 inbox（CLAUDE-BETA-LAUNCH-FINAL-001）。
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listMock = vi.fn();

vi.mock("./api", () => ({
  superuserListFeedback: (...args: unknown[]) => listMock(...args),
}));

import FeedbackInbox from "./FeedbackInbox";

const ROWS = [
  { feedback_id: "f2", display_name: "乙", content: "第二行\n換行了",
    created_at: "2026-09-28T02:00:00+00:00", owner_hint: "abc123…" },
  { feedback_id: "f1", display_name: "<b>甲</b>", content: "<script>alert(1)</script>",
    created_at: "2026-09-28T01:00:00+00:00", owner_hint: null },
];

describe("FeedbackInbox", () => {
  beforeEach(() => {
    listMock.mockReset().mockResolvedValue(ROWS);
  });

  it("依後端順序（最新在最上）列出稱呼、內容與 owner 前綴", async () => {
    render(<FeedbackInbox />);
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("乙");
    expect(items[0]).toHaveTextContent("abc123…");
    expect(items[1]).toHaveTextContent("<b>甲</b>");
  });

  it("內容當純文字 render，不解析 HTML", async () => {
    const { container } = render(<FeedbackInbox />);
    expect(await screen.findByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("沒有回饋時顯示空狀態", async () => {
    listMock.mockResolvedValue([]);
    render(<FeedbackInbox />);
    expect(await screen.findByText("目前還沒有任何回饋。")).toBeInTheDocument();
  });

  it("reloadKey 變動時重讀一次", async () => {
    const { rerender } = render(<FeedbackInbox reloadKey={0} />);
    await screen.findAllByRole("listitem");
    listMock.mockResolvedValue([]);
    rerender(<FeedbackInbox reloadKey={1} />);
    expect(await screen.findByText("目前還沒有任何回饋。")).toBeInTheDocument();
    expect(listMock).toHaveBeenCalledTimes(2);
  });
});
