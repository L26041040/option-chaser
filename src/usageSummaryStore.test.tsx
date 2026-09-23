import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MobileStatsStrip from "./MobileStatsStrip";
import { invalidateUsageSummary, useUsageSummary } from "./usageSummaryStore";

/**
 * SW-13（PR #344 P2）：`usageSummaryStore` 的失效／合併／失敗語意。
 * App 層級「哪個操作成功後會更新」的行為測試在 `App.test.tsx`
 * （SW-13 那一組），這裡只鎖 store 自己的規則。
 */

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function summary(active: number) {
  return {
    active_scenarios: active, max_active_scenarios: 10, quota_exempt: false,
    last_activity_at: null, best_return: null, best_return_symbol: null,
    best_return_strategy: null, best_return_target_month: null,
  };
}

type Pending = { resolve: (v: unknown) => void; reject: (e: unknown) => void };

/** 每次 usage-summary 請求都掛起，由測試手動決定何時、以什麼結果回應。 */
function deferredFetch() {
  const pending: Pending[] = [];
  const spy = vi.fn(() => new Promise((resolve, reject) => {
    pending.push({ resolve, reject });
  }));
  vi.stubGlobal("fetch", spy);
  const respond = async (i: number, body: unknown) => {
    await act(async () => {
      pending[i].resolve({ ok: true, status: 200, json: async () => body });
    });
  };
  const fail = async (i: number) => {
    await act(async () => {
      pending[i].reject(new Error("network down"));
    });
  };
  return { spy, respond, fail };
}

/** 模擬桌面 strip 的另一個讀者——驗證兩個讀者共用同一份、同一個請求。 */
function SecondReader() {
  const { usage } = useUsageSummary();
  return <p data-testid="second">{usage ? usage.active_scenarios : "…"}</p>;
}

describe("usageSummaryStore（SW-13）", () => {
  it("兩個讀者同時掛著只打一次請求；失效後兩邊一起更新，仍只打一次", async () => {
    const { spy, respond } = deferredFetch();
    render(<><MobileStatsStrip /><SecondReader /></>);
    expect(spy).toHaveBeenCalledTimes(1);
    await respond(0, summary(1));
    expect(screen.getByText("1 / 10")).toBeInTheDocument();
    expect(screen.getByTestId("second")).toHaveTextContent("1");

    act(() => invalidateUsageSummary());
    expect(spy).toHaveBeenCalledTimes(2);
    await respond(1, summary(2));
    expect(screen.getByText("2 / 10")).toBeInTheDocument();
    expect(screen.getByTestId("second")).toHaveTextContent("2");
  });

  it("沒失效過：卸載再掛載沿用手上這份，不重抓", async () => {
    const { spy, respond } = deferredFetch();
    const first = render(<MobileStatsStrip />);
    await respond(0, summary(1));
    first.unmount();

    render(<MobileStatsStrip />);
    expect(screen.getByText("1 / 10")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("沒有讀者掛著時失效只標記過期、不發請求；下一次掛載才抓", async () => {
    const { spy, respond } = deferredFetch();
    const first = render(<MobileStatsStrip />);
    await respond(0, summary(1));
    first.unmount();

    invalidateUsageSummary();
    invalidateUsageSummary();
    expect(spy).toHaveBeenCalledTimes(1);

    render(<MobileStatsStrip />);
    expect(spy).toHaveBeenCalledTimes(2);
    await respond(1, summary(3));
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
  });

  it("請求進行中又被失效：丟掉那份舊快照，結束後只補抓一次，最後顯示新值", async () => {
    const { spy, respond } = deferredFetch();
    render(<MobileStatsStrip />);
    act(() => {
      invalidateUsageSummary();
      invalidateUsageSummary();
    });
    expect(spy).toHaveBeenCalledTimes(1);   // 同時最多一個在飛

    await respond(0, summary(1));           // 操作前的快照
    expect(screen.queryByText("1 / 10")).not.toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(2);   // 兩次失效合併成一次補抓

    await respond(1, summary(2));
    expect(screen.getByText("2 / 10")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("重抓失敗：保留上一份成功的數字，不換成錯誤訊息；下一次失效再試", async () => {
    const { spy, respond, fail } = deferredFetch();
    render(<MobileStatsStrip />);
    await respond(0, summary(1));

    act(() => invalidateUsageSummary());
    await fail(1);
    expect(screen.getByText("1 / 10")).toBeInTheDocument();
    expect(screen.queryByText(/network down/)).not.toBeInTheDocument();

    act(() => invalidateUsageSummary());
    expect(spy).toHaveBeenCalledTimes(3);
    await respond(2, summary(4));
    await waitFor(() =>
      expect(within(document.body).getByText("4 / 10")).toBeInTheDocument());
  });
});
