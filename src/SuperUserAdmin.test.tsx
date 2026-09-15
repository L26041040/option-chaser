/**
 * Super User 系統／管理操作面板（PB-10／#301，Anonymous Public Beta）。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listOwnersMock = vi.fn();
const listOwnerScenariosMock = vi.fn();
const getOwnerScenarioMock = vi.fn();
const deleteOwnerMock = vi.fn();
const batchDeleteOwnersMock = vi.fn();
const setOwnerProtectedMock = vi.fn();
const getAuditLogMock = vi.fn();

vi.mock("./api", () => ({
  superuserListOwners: (...args: unknown[]) => listOwnersMock(...args),
  superuserListOwnerScenarios: (...args: unknown[]) =>
    listOwnerScenariosMock(...args),
  superuserGetOwnerScenario: (...args: unknown[]) => getOwnerScenarioMock(...args),
  superuserDeleteOwner: (...args: unknown[]) => deleteOwnerMock(...args),
  superuserBatchDeleteOwners: (...args: unknown[]) => batchDeleteOwnersMock(...args),
  superuserSetOwnerProtected: (...args: unknown[]) => setOwnerProtectedMock(...args),
  superuserGetAuditLog: (...args: unknown[]) => getAuditLogMock(...args),
}));

import SuperUserAdmin from "./SuperUserAdmin";

const OWNER_A = {
  owner_id: "owner-a",
  created_at: "2026-09-01T00:00:00+00:00",
  last_activity_at: "2026-09-10T00:00:00+00:00",
  protected: false,
};
const OWNER_B = {
  owner_id: "owner-b",
  created_at: "2026-09-02T00:00:00+00:00",
  last_activity_at: null,
  protected: true,
};

describe("SuperUserAdmin", () => {
  beforeEach(() => {
    listOwnersMock.mockReset().mockResolvedValue([OWNER_A, OWNER_B]);
    listOwnerScenariosMock.mockReset().mockResolvedValue([]);
    getOwnerScenarioMock.mockReset();
    deleteOwnerMock.mockReset().mockResolvedValue({ deleted: true, counts: {} });
    batchDeleteOwnersMock.mockReset().mockResolvedValue({ deleted: [], counts: {} });
    setOwnerProtectedMock.mockReset().mockResolvedValue({
      owner_id: "owner-a",
      protected: true,
    });
    getAuditLogMock.mockReset().mockResolvedValue([]);
  });

  it("loads and shows every owner on mount", async () => {
    render(<SuperUserAdmin />);
    expect(await screen.findByText("owner-a")).toBeInTheDocument();
    expect(screen.getByText("owner-b")).toBeInTheDocument();
    expect(listOwnersMock).toHaveBeenCalledTimes(1);
  });

  it("shows a protected tag only for owners that are protected", async () => {
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    const rowB = screen.getByText("owner-b").closest("li") as HTMLElement;
    expect(within(rowA).queryByText("protected")).not.toBeInTheDocument();
    expect(within(rowB).getByText("protected")).toBeInTheDocument();
  });

  it("shows a friendly empty state when there are no owners at all", async () => {
    listOwnersMock.mockReset().mockResolvedValue([]);
    render(<SuperUserAdmin />);
    expect(await screen.findByText("目前沒有任何 owner。")).toBeInTheDocument();
  });

  it("surfaces a load error instead of crashing", async () => {
    listOwnersMock.mockReset().mockRejectedValue(new Error("網路壞了"));
    render(<SuperUserAdmin />);
    expect(await screen.findByRole("alert")).toHaveTextContent("網路壞了");
  });

  it("expands an owner's scenario list on demand, not eagerly", async () => {
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    expect(listOwnerScenariosMock).not.toHaveBeenCalled();

    const user = userEvent.setup();
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(within(rowA).getByRole("button", { name: "查看劇本" }));

    await waitFor(() => expect(listOwnerScenariosMock).toHaveBeenCalledWith("owner-a"));
  });

  it("shows a scenario's full content only after clicking it", async () => {
    listOwnerScenariosMock.mockResolvedValue([
      { id: "s1", symbol: "TLT", target_month: "2028-05", best_return: 1.2 },
    ]);
    getOwnerScenarioMock.mockResolvedValue({ id: "s1", symbol: "TLT",
      latest_result: { note: "full detail" } });
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(within(rowA).getByRole("button", { name: "查看劇本" }));

    const scenarioButton = await within(rowA).findByRole(
      "button", { name: /TLT · 2028-05/ });
    expect(screen.queryByText(/full detail/)).not.toBeInTheDocument();

    await user.click(scenarioButton);
    expect(await screen.findByText(/full detail/)).toBeInTheDocument();
    expect(getOwnerScenarioMock).toHaveBeenCalledWith("owner-a", "s1");
  });

  it("toggling protected calls the API and reloads the owner list", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;

    await user.click(within(rowA).getByRole("button", { name: "設為 protected" }));

    await waitFor(() =>
      expect(setOwnerProtectedMock).toHaveBeenCalledWith("owner-a", true));
    expect(listOwnersMock).toHaveBeenCalledTimes(2); // 初始一次＋操作後重新載入一次
  });

  it("delete requires a confirmation dialog before calling the API", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;

    await user.click(
      within(rowA).getByRole("button", { name: "永久刪除全部資料" }));

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(deleteOwnerMock).not.toHaveBeenCalled();
  });

  it("cancelling the delete confirmation calls nothing", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(
      within(rowA).getByRole("button", { name: "永久刪除全部資料" }));
    await user.click(screen.getByRole("button", { name: "取消" }));

    expect(deleteOwnerMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("confirming delete calls the API with the target owner and reloads", async () => {
    listOwnersMock
      .mockResolvedValueOnce([OWNER_A, OWNER_B])
      .mockResolvedValueOnce([OWNER_B]);
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(
      within(rowA).getByRole("button", { name: "永久刪除全部資料" }));
    await user.click(screen.getByRole("button", { name: "永久刪除" }));

    await waitFor(() =>
      expect(deleteOwnerMock).toHaveBeenCalledWith("owner-a", "owner-a"));
    await waitFor(() => expect(screen.queryByText("owner-a")).not.toBeInTheDocument());
  });

  it("selecting several owners shows a batch action bar that lists them for confirmation", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");

    await user.click(screen.getByRole("checkbox", { name: "選取 owner owner-a" }));
    await user.click(screen.getByRole("checkbox", { name: "選取 owner owner-b" }));
    expect(screen.getByText("已選 2 個 owner")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "永久刪除已選" }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("owner-a")).toBeInTheDocument();
    expect(within(dialog).getByText("owner-b")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "永久刪除" }));
    await waitFor(() =>
      expect(batchDeleteOwnersMock).toHaveBeenCalledWith(["owner-a", "owner-b"]));
  });

  it("the audit trail is collapsed by default and only fetched when opened", async () => {
    getAuditLogMock.mockResolvedValue([
      { event_id: "a1", ts: "2026-09-14T00:00:00+00:00", actor: "superuser",
        action: "delete_owner", target_owner_id: "owner-a", detail: {} },
    ]);
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    expect(getAuditLogMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "查看 audit trail" }));
    expect(await screen.findByText(/delete_owner/)).toBeInTheDocument();
    expect(screen.getByText(/目標 owner-a/)).toBeInTheDocument();
  });

  it("an empty audit trail says so instead of showing nothing", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    await user.click(screen.getByRole("button", { name: "查看 audit trail" }));
    expect(
      await screen.findByText("目前沒有任何高風險操作紀錄。"),
    ).toBeInTheDocument();
  });
});
