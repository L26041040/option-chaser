import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MobileStatsStrip from "./MobileStatsStrip";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockUsageSummary(json: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => json,
  } as Response);
}

describe("MobileStatsStrip（SW-04／#333 → SW-10／#340）", () => {
  it("讀到 usage-summary 後畫出進行中劇本／最佳報酬兩項欄位（節流相關欄位已整段移除）", async () => {
    mockUsageSummary({
      active_scenarios: 3,
      max_active_scenarios: 10,
      quota_exempt: false,
      last_activity_at: "2026-09-20T09:41:00+00:00",
      best_return: 0.855,
      best_return_symbol: "XYZ",
      best_return_strategy: "bull-call-spread",
      best_return_target_month: "2026-09",
    });
    render(<MobileStatsStrip />);

    expect(await screen.findByText("進行中劇本")).toBeInTheDocument();
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
    expect(screen.getByText("最佳報酬")).toBeInTheDocument();
    expect(screen.getByText("85.5%")).toBeInTheDocument();
    expect(screen.getByText(/XYZ.*Bull Call Spread/)).toBeInTheDocument();
    expect(screen.queryByText("最近活動")).not.toBeInTheDocument();
    expect(screen.queryByText("刷新節流間隔")).not.toBeInTheDocument();
  });

  it("豁免角色：進行中劇本顯示「豁免」", async () => {
    mockUsageSummary({
      active_scenarios: 2,
      max_active_scenarios: 10,
      quota_exempt: true,
      last_activity_at: null,
      best_return: null,
      best_return_symbol: null,
      best_return_strategy: null,
      best_return_target_month: null,
    });
    render(<MobileStatsStrip />);

    expect(await screen.findByText("豁免")).toBeInTheDocument();
    expect(screen.getByText("最佳報酬")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("讀取失敗時顯示錯誤訊息，不搶頁面既有的 role=alert", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));
    render(<MobileStatsStrip />);

    expect(await screen.findByText(/network down/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
