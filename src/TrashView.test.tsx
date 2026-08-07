/**
 * 垃圾桶畫面元件測試（TR6／#91 唯讀清單；TR4／#92 還原與永久刪除）。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import sampleRow from "../contracts/scenario_row_sample.json";
import TrashView from "./TrashView";
import type { ScenarioSummary } from "./api";

function row(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    ...(sampleRow as unknown as ScenarioSummary),
    id: "a", symbol: "TLT", target_price: 120, target_month: "2028-05",
    archived_at: "2026-08-05T00:00:00+00:00",
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.234,
    target_anchor: "2028-05-19", days_to_anchor: 653,
    ...overrides,
  };
}

function mockFetch(handler: (url: string, init?: RequestInit) => Promise<unknown>) {
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    const body = await handler(url, init);
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("垃圾桶清單（TR6／#91）", () => {
  it("列出已封存的劇本：標的／目標／封存時間／最後收益率", async () => {
    mockFetch(async () => [row()]);
    render(<TrashView onRestore={vi.fn()} />);

    expect(await screen.findByText("TLT")).toBeInTheDocument();
    expect(screen.getByText(/2028-05/)).toBeInTheDocument();
    expect(screen.getByText("123.4%")).toBeInTheDocument();
  });

  it("垃圾桶是空的時給明確指引", async () => {
    mockFetch(async () => []);
    render(<TrashView onRestore={vi.fn()} />);

    expect(await screen.findByText("垃圾桶是空的。")).toBeInTheDocument();
  });

  it("清單載不動時說明原因", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
    })));
    render(<TrashView onRestore={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("資料庫連不上");
  });
});

describe("單筆還原（TR4／#92）", () => {
  it("還原成功：從垃圾桶清單消失，並把那一列資料交回 onRestore", async () => {
    const onRestore = vi.fn();
    mockFetch(async (url) => {
      if (url.endsWith("/restore")) return { restored: true };
      return [row()];
    });
    render(<TrashView onRestore={onRestore} />);
    await screen.findByText("TLT");

    await userEvent.click(
      screen.getByRole("button", { name: "還原 TLT 2028-05" }));

    await waitFor(() => {
      expect(screen.queryByText("TLT")).not.toBeInTheDocument();
    });
    expect(onRestore).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });

  it("還原失敗：留在垃圾桶清單上，並說明原因", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/restore")) {
        return { ok: false, status: 404, json: async () => ({ detail: "劇本不存在" }) };
      }
      return { ok: true, status: 200, json: async () => [row()] };
    }));
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");

    await userEvent.click(
      screen.getByRole("button", { name: "還原 TLT 2028-05" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();
  });
});

describe("單筆永久刪除與二次確認（TR4／#92）", () => {
  it("點永久刪除先出現確認畫面，列出具體 ticker 與 target month，還不會呼叫刪除",
     async () => {
    const spy = vi.fn(async (_url: string, init?: RequestInit) => ({
      ok: true, status: 200,
      json: async () => (init?.method === "DELETE" ? undefined : [row()]),
    } as Response));
    vi.stubGlobal("fetch", spy);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");

    await userEvent.click(
      screen.getByRole("button", { name: "永久刪除 TLT 2028-05" }));

    const sheet = await screen.findByRole("alertdialog");
    expect(sheet).toHaveTextContent("TLT");
    expect(sheet).toHaveTextContent("2028-05");
    expect(spy.mock.calls.some(([, init]) =>
      (init as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("取消確認畫面：不呼叫刪除、劇本還在垃圾桶清單上", async () => {
    mockFetch(async () => [row()]);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(
      screen.getByRole("button", { name: "永久刪除 TLT 2028-05" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog"))
        .getByRole("button", { name: "取消" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("TLT")).toBeInTheDocument();
  });

  it("確認永久刪除：呼叫刪除端點，成功後從垃圾桶清單消失", async () => {
    const spy = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return { ok: true, status: 204, json: async () => undefined } as Response;
      }
      return { ok: true, status: 200, json: async () => [row()] } as Response;
    });
    vi.stubGlobal("fetch", spy);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(
      screen.getByRole("button", { name: "永久刪除 TLT 2028-05" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog"))
        .getByRole("button", { name: "永久刪除" }));

    await waitFor(() => {
      expect(screen.queryByText("TLT")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(spy.mock.calls.some(([, init]) =>
      (init as RequestInit | undefined)?.method === "DELETE")).toBe(true);
  });

  it("刪除失敗：確認畫面留著，說明失敗原因", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return { ok: false, status: 409,
                 json: async () => ({ detail: "劇本尚未移入垃圾桶" }) };
      }
      return { ok: true, status: 200, json: async () => [row()] };
    }));
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(
      screen.getByRole("button", { name: "永久刪除 TLT 2028-05" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog"))
        .getByRole("button", { name: "永久刪除" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本尚未移入垃圾桶");
    // 失敗時確認畫面留著，讓使用者看得到剛才按的是哪一個、可以重試或取消
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});

describe("批次選取（TR5／#93）", () => {
  it("勾選兩筆，「還原已選」變成可按，顯示已選數量", async () => {
    mockFetch(async () => [row({ id: "a", symbol: "TLT" }),
                            row({ id: "b", symbol: "SPY" })]);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    expect(screen.getByRole("button", { name: "還原已選" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "選取 TLT 2028-05" }));
    await userEvent.click(screen.getByRole("button", { name: "選取 SPY 2028-05" }));

    expect(screen.getByText("已選 2 個")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "還原已選" })).not.toBeDisabled();
  });

  it("全選／取消全選切換所有列", async () => {
    mockFetch(async () => [row({ id: "a", symbol: "TLT" }),
                            row({ id: "b", symbol: "SPY" })]);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");

    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    expect(screen.getByText("已選 2 個")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "取消全選" }));
    expect(screen.getByText("已選 0 個")).toBeInTheDocument();
  });
});

describe("批次還原（TR5／#93）", () => {
  it("批次還原成功：兩筆都從垃圾桶消失，各自交回 onRestore", async () => {
    const onRestore = vi.fn();
    mockFetch(async (url) => {
      if (url.endsWith("/restore")) return { restored: true };
      return [row({ id: "a", symbol: "TLT" }), row({ id: "b", symbol: "SPY" })];
    });
    render(<TrashView onRestore={onRestore} />);
    await screen.findByText("TLT");

    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "還原已選" }));

    await waitFor(() => {
      expect(screen.queryByText("TLT")).not.toBeInTheDocument();
      expect(screen.queryByText("SPY")).not.toBeInTheDocument();
    });
    expect(onRestore).toHaveBeenCalledTimes(2);
  });

  it("批次還原部分失敗：失敗的留著並說明原因，成功的照樣消失", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/a/restore")) {
        return { ok: false, status: 404, json: async () => ({ detail: "劇本不存在" }) };
      }
      if (url.endsWith("/restore")) {
        return { ok: true, status: 200, json: async () => ({ restored: true }) };
      }
      return { ok: true, status: 200,
               json: async () => [row({ id: "a", symbol: "TLT" }),
                                  row({ id: "b", symbol: "SPY" })] };
    }));
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");

    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "還原已選" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
    expect(screen.getByText("TLT")).toBeInTheDocument();          // 失敗的留著
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();    // 成功的消失
  });
});

describe("批次永久刪除（TR5／#93）", () => {
  it("確認畫面列出全部待刪劇本的 ticker＋target month 與總數", async () => {
    mockFetch(async () => [row({ id: "a", symbol: "TLT", target_month: "2028-05" }),
                            row({ id: "b", symbol: "SPY", target_month: "2028-06" })]);
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");

    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "永久刪除已選" }));

    const sheet = await screen.findByRole("alertdialog");
    expect(sheet).toHaveTextContent("2");
    expect(sheet).toHaveTextContent("TLT");
    expect(sheet).toHaveTextContent("2028-05");
    expect(sheet).toHaveTextContent("SPY");
    expect(sheet).toHaveTextContent("2028-06");
  });

  it("取消批次刪除確認：不呼叫刪除，兩筆都還在", async () => {
    const spy = mockFetch(async (_url, init) => {
      if (init?.method === "DELETE") throw new Error("不該被呼叫");
      return [row({ id: "a", symbol: "TLT" }), row({ id: "b", symbol: "SPY" })];
    });
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "永久刪除已選" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "取消" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("TLT")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(spy.mock.calls.some(([, init]) =>
      (init as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("確認後依序刪除，成功者從清單消失", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return { ok: true, status: 204, json: async () => undefined };
      }
      return { ok: true, status: 200,
               json: async () => [row({ id: "a", symbol: "TLT" }),
                                  row({ id: "b", symbol: "SPY" })] };
    }));
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "永久刪除已選" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "永久刪除" }));

    await waitFor(() => {
      expect(screen.queryByText("TLT")).not.toBeInTheDocument();
      expect(screen.queryByText("SPY")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("批次刪除部分失敗：失敗的留著並說明原因，成功的照樣消失", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "DELETE" && url.endsWith("/a")) {
        return { ok: false, status: 409,
                 json: async () => ({ detail: "劇本尚未移入垃圾桶" }) };
      }
      if (init?.method === "DELETE") {
        return { ok: true, status: 204, json: async () => undefined };
      }
      return { ok: true, status: 200,
               json: async () => [row({ id: "a", symbol: "TLT" }),
                                  row({ id: "b", symbol: "SPY" })] };
    }));
    render(<TrashView onRestore={vi.fn()} />);
    await screen.findByText("TLT");
    await userEvent.click(screen.getByRole("button", { name: "全選" }));
    await userEvent.click(screen.getByRole("button", { name: "永久刪除已選" }));
    await screen.findByRole("alertdialog");

    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "永久刪除" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本尚未移入垃圾桶");
    expect(screen.getByText("TLT")).toBeInTheDocument();          // 失敗的留著
    expect(screen.queryByText("SPY")).not.toBeInTheDocument();    // 成功的消失
  });
});
