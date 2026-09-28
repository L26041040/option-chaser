/**
 * Super Admin 管理中心（CLAUDE-SETTINGS-ROLE-IA-001）：獨立頁面的角色守門。
 * 管理面板本身的行為由 `SuperUserAdmin.test.tsx` 覆蓋，這裡只測「誰能
 * 掛載它、誰會被導回設定頁、有沒有打管理端點」。
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "./AdminPage";
import { _resetCacheForTests, setAuthStatusCache } from "./fetchCache";
import type { Role } from "./superuser";

const EMPTY_OPS_METRICS = {
  chain_fetch_count: [], chain_429_count: [], stale_serve_count: [],
  cold_miss_count: [], refresh_duration_ms: [],
  abandoned_owner_cleanup_count: [],
  table_size: {},
  anonymous_owners: { active: 0, abandoned: 0, eligible_for_hard_delete: 0,
                     protected: 0, total: 0 },
  scenarios: { total: 0, average_per_owner: 0 },
  alerts: [],
  vendor_fuse: { used: 0, budget: null },
};

function mockApi({ role, authFails = false }: { role: Role; authFails?: boolean }) {
  const spy = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.startsWith("/api/auth/status")) {
      return authFails
        ? ({ ok: false, status: 500, json: async () => ({ detail: "down" }) } as Response)
        : ({ ok: true, status: 200, json: async () => ({ role }) } as Response);
    }
    if (u.startsWith("/api/ops/metrics")) {
      return { ok: true, status: 200, json: async () => EMPTY_OPS_METRICS } as Response;
    }
    return { ok: true, status: 200, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const adminCalls = (spy: ReturnType<typeof mockApi>) =>
  spy.mock.calls.filter(([u]) => /^\/api\/(superuser|ops)\//.test(String(u)));

beforeEach(() => {
  window.location.hash = "#/admin";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  _resetCacheForTests();
  window.location.hash = "";
});

describe("AdminPage", () => {
  it("Super Admin：顯示管理中心頁首並掛載既有的管理面板", async () => {
    const spy = mockApi({ role: "superadmin" });
    render(<AdminPage />);

    expect(screen.getByRole("heading", { name: "管理中心" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "‹ 設定" })).toHaveAttribute("href", "#/settings");
    expect(await screen.findByRole("region", { name: "Super User 管理面板" }))
      .toBeInTheDocument();
    expect(adminCalls(spy).length).toBeGreaterThan(0);
    expect(window.location.hash).toBe("#/admin");
  });

  it.each(["normal", "superuser"] as const)(
    "%s 直接打 #/admin：不掛載管理面板、不打管理端點，導回設定頁",
    async (role) => {
      const spy = mockApi({ role });
      render(<AdminPage />);

      await waitFor(() => expect(window.location.hash).toBe("#/settings"));
      expect(screen.queryByRole("region", { name: "Super User 管理面板" }))
        .not.toBeInTheDocument();
      expect(adminCalls(spy)).toEqual([]);
    });

  it("角色查詢失敗：fail closed，一樣導回設定頁", async () => {
    const spy = mockApi({ role: "superadmin", authFails: true });
    render(<AdminPage />);

    await waitFor(() => expect(window.location.hash).toBe("#/settings"));
    expect(adminCalls(spy)).toEqual([]);
  });

  it("角色確認前只顯示載入中，不先掛載管理面板", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<AdminPage />);

    expect(screen.getByText("載入中……")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Super User 管理面板" }))
      .not.toBeInTheDocument();
  });

  it("Super Admin 在這頁期間登出：管理面板立刻卸載並導回設定頁", async () => {
    mockApi({ role: "superadmin" });
    render(<AdminPage />);
    await screen.findByRole("region", { name: "Super User 管理面板" });

    act(() => setAuthStatusCache({ role: "normal" }));

    await waitFor(() => expect(window.location.hash).toBe("#/settings"));
    expect(screen.queryByRole("region", { name: "Super User 管理面板" }))
      .not.toBeInTheDocument();
  });
});
