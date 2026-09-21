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
// OG-11（#322）：新增的系統指標方塊（`OpsStats`）掛載時無條件呼叫這個
// client——既有測試沒有一條在乎它回什麼，預設給一份最小、全部欄位
// 都存在的假體，讓既有斷言不受這個新元件的非同步 effect 干擾。
const getOpsMetricsMock = vi.fn();

vi.mock("./api", () => ({
  superuserListOwners: (...args: unknown[]) => listOwnersMock(...args),
  superuserListOwnerScenarios: (...args: unknown[]) =>
    listOwnerScenariosMock(...args),
  superuserGetOwnerScenario: (...args: unknown[]) => getOwnerScenarioMock(...args),
  superuserDeleteOwner: (...args: unknown[]) => deleteOwnerMock(...args),
  superuserBatchDeleteOwners: (...args: unknown[]) => batchDeleteOwnersMock(...args),
  superuserSetOwnerProtected: (...args: unknown[]) => setOwnerProtectedMock(...args),
  superuserGetAuditLog: (...args: unknown[]) => getAuditLogMock(...args),
  getOpsMetrics: (...args: unknown[]) => getOpsMetricsMock(...args),
}));

import SuperUserAdmin from "./SuperUserAdmin";

const OWNER_A = {
  owner_id: "owner-a",
  created_at: "2026-09-01T00:00:00+00:00",
  last_activity_at: "2026-09-10T00:00:00+00:00",
  protected: false,
  is_synthetic: false,
};
const OWNER_B = {
  owner_id: "owner-b",
  created_at: "2026-09-02T00:00:00+00:00",
  last_activity_at: null,
  protected: true,
  is_synthetic: false,
};

/** 最小、全部欄位都存在的 `OpsMetrics` 假體——本檔案的既有測試不驗證
 *  這個新元件的內容，只需要它不 throw、不讓 effect 掛掉。 */
const EMPTY_OPS_METRICS = {
  chain_fetch_count: [], chain_429_count: [], stale_serve_count: [],
  cold_miss_count: [], refresh_duration_ms: [], history_read_volume: [],
  abandoned_owner_cleanup_count: [],
  table_size: {},
  anonymous_owners: { active: 0, abandoned: 0, eligible_for_hard_delete: 0,
                     protected: 0, total: 0 },
  scenarios: { total: 0, average_per_owner: 0 },
  alerts: [],
  // SW-03（#334，Seed Warm）：`OpsStats` 新增讀取這個既有欄位（原本
  // 只有劇本庫頁首的 `OpsSuperAdminStats` 讀，現在搬來這裡）。
  vendor_fuse: { used: 0, budget: null },
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
    getOpsMetricsMock.mockReset().mockResolvedValue(EMPTY_OPS_METRICS);
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

  it("OG-11（#322）：確認鈕預設停用，直到打對目標 owner id 才能按——" +
     "不預填，打錯或打一半都還是停用", async () => {
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(
      within(rowA).getByRole("button", { name: "永久刪除全部資料" }));

    const dialog = screen.getByRole("alertdialog");
    const input = within(dialog).getByRole("textbox", { name: "輸入以確認" });
    const confirmButton = within(dialog).getByRole("button", { name: "永久刪除" });

    // 不預填：一打開輸入框是空的，確認鈕停用。
    expect(input).toHaveValue("");
    expect(confirmButton).toBeDisabled();

    await user.type(input, "owner-b");
    expect(confirmButton).toBeDisabled();

    await user.clear(input);
    await user.type(input, "owner-a");
    expect(confirmButton).not.toBeDisabled();
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

  it("confirming delete calls the API with the target owner and reloads" +
     "（OG-11／#322：確認值＝使用者實際打的那一串，不是前端自動代填）",
     async () => {
    listOwnersMock
      .mockResolvedValueOnce([OWNER_A, OWNER_B])
      .mockResolvedValueOnce([OWNER_B]);
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    await user.click(
      within(rowA).getByRole("button", { name: "永久刪除全部資料" }));
    const dialog = screen.getByRole("alertdialog");
    await user.type(
      within(dialog).getByRole("textbox", { name: "輸入以確認" }), "owner-a");
    await user.click(within(dialog).getByRole("button", { name: "永久刪除" }));

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

    const confirmButton = within(dialog).getByRole("button", { name: "永久刪除" });
    const input = within(dialog).getByRole("textbox", { name: "輸入以確認" });
    // OG-11（#322）：批次確認鈕預設停用，要打對「刪除 N 個」才能按。
    expect(confirmButton).toBeDisabled();
    await user.type(input, "刪除 2 個");
    expect(confirmButton).not.toBeDisabled();

    await user.click(confirmButton);
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

describe("OG-11（#322）：owners 表狀態篩選（純前端，不打新請求）", () => {
  const SYNTHETIC_OWNER = {
    owner_id: "owner-c",
    created_at: "2026-09-03T00:00:00+00:00",
    last_activity_at: null,
    protected: false,
    is_synthetic: true,
  };

  it("預設『全部』顯示全部 owner；synthetic tag 只在對應 owner 顯示", async () => {
    listOwnersMock.mockReset()
      .mockResolvedValue([OWNER_A, OWNER_B, SYNTHETIC_OWNER]);
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");

    expect(screen.getByText("owner-b")).toBeInTheDocument();
    expect(screen.getByText("owner-c")).toBeInTheDocument();
    const rowC = screen.getByText("owner-c").closest("li") as HTMLElement;
    expect(within(rowC).getByText("synthetic")).toBeInTheDocument();
    const rowA = screen.getByText("owner-a").closest("li") as HTMLElement;
    expect(within(rowA).queryByText("synthetic")).not.toBeInTheDocument();
  });

  it("點 Protected chip 只留下 protected 的 owner，不打任何新請求", async () => {
    listOwnersMock.mockReset()
      .mockResolvedValue([OWNER_A, OWNER_B, SYNTHETIC_OWNER]);
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");

    await user.click(
      within(screen.getByRole("group", { name: "依狀態篩選 owner" }))
        .getByRole("button", { name: "Protected" }));

    expect(screen.queryByText("owner-a")).not.toBeInTheDocument();
    expect(screen.getByText("owner-b")).toBeInTheDocument();
    expect(screen.queryByText("owner-c")).not.toBeInTheDocument();
    expect(listOwnersMock).toHaveBeenCalledTimes(1);
  });

  it("點 Synthetic chip 只留下 synthetic 的 owner", async () => {
    listOwnersMock.mockReset()
      .mockResolvedValue([OWNER_A, OWNER_B, SYNTHETIC_OWNER]);
    const user = userEvent.setup();
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");

    await user.click(
      within(screen.getByRole("group", { name: "依狀態篩選 owner" }))
        .getByRole("button", { name: "Synthetic" }));

    expect(screen.queryByText("owner-a")).not.toBeInTheDocument();
    expect(screen.queryByText("owner-b")).not.toBeInTheDocument();
    expect(screen.getByText("owner-c")).toBeInTheDocument();
  });
});

describe("OG-11（#322）：系統指標方塊（既有 GET /api/ops/metrics，只顯示聚合數字）", () => {
  it("顯示彙整後的聚合數字，不逐 bucket 攤開", async () => {
    listOwnersMock.mockReset().mockResolvedValue([OWNER_A, OWNER_B]);
    getOpsMetricsMock.mockReset().mockResolvedValue({
      ...EMPTY_OPS_METRICS,
      chain_fetch_count: [
        { bucket: "2026-09-17", source: "cboe", symbol: null, count: 3, total: 3, max_value: null },
        { bucket: "2026-09-18", source: "cboe", symbol: null, count: 2, total: 2, max_value: null },
      ],
      refresh_duration_ms: [
        { bucket: "2026-09-18", source: null, symbol: null, count: 2, total: 400, max_value: 300 },
      ],
      table_size: { results: { row_count: 42, total_bytes: 1000,
                              avg_row_bytes: 23.8, max_row_bytes: 99 },
                   snapshots: { row_count: 7, total_bytes: 500,
                              avg_row_bytes: 71.4, max_row_bytes: 80 } },
      anonymous_owners: { active: 5, abandoned: 1, eligible_for_hard_delete: 0,
                        protected: 2, total: 8 },
      scenarios: { total: 20, average_per_owner: 2.5 },
      alerts: [{ key: "storage", triggered: true, message: "儲存空間逼近上限" }],
    });
    render(<SuperUserAdmin />);
    await screen.findByText("owner-a");
    await screen.findByText("系統指標");

    // Chain Fetch 累計＝3+2=5；刷新耗時平均＝400/2=200ms。
    const chainFetchStat =
      screen.getByText("Chain Fetch（累計）").closest(".pstat") as HTMLElement;
    expect(within(chainFetchStat).getByText("5")).toBeInTheDocument();
    expect(screen.getByText("200 ms")).toBeInTheDocument();
    expect(screen.getByText("42 列")).toBeInTheDocument();
    expect(screen.getByText("儲存空間逼近上限")).toBeInTheDocument();
  });
});
