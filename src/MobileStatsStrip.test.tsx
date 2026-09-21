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

describe("MobileStatsStrip（SW-04／#333）", () => {
  it("讀到 usage-summary 後畫出進行中劇本／最近活動／刷新節流間隔三項既有欄位", async () => {
    mockUsageSummary({
      active_scenarios: 3,
      max_active_scenarios: 10,
      quota_exempt: false,
      refresh_min_interval_minutes: 30,
      throttle_exempt: false,
      last_activity_at: "2026-09-20T09:41:00+00:00",
    });
    render(<MobileStatsStrip />);

    expect(await screen.findByText("進行中劇本")).toBeInTheDocument();
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
    expect(screen.getByText("最近活動")).toBeInTheDocument();
    expect(screen.getByText("刷新節流間隔")).toBeInTheDocument();
    expect(screen.getByText("30 分鐘")).toBeInTheDocument();
  });

  it("豁免角色：進行中劇本／節流間隔顯示「豁免」", async () => {
    mockUsageSummary({
      active_scenarios: 2,
      max_active_scenarios: 10,
      quota_exempt: true,
      refresh_min_interval_minutes: 30,
      throttle_exempt: true,
      last_activity_at: null,
    });
    render(<MobileStatsStrip />);

    expect(await screen.findByText("最近活動")).toBeInTheDocument();
    expect(screen.getAllByText("豁免")).toHaveLength(2);
  });

  it("讀取失敗時顯示錯誤訊息，不搶頁面既有的 role=alert", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));
    render(<MobileStatsStrip />);

    expect(await screen.findByText(/network down/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
