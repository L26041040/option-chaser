/**
 * 編輯劇本（#132）——沿用建立表單的編輯模式。
 *
 * 守三件需求方點名的事：標的不可改、取消隨時可按且什麼都不寫、儲存維持
 * 同一個劇本身分（走 PATCH，不是刪除＋重建）。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import sampleRow from "../contracts/scenario_row_sample.json";
import type { ScenarioSummary } from "./api";

function card(over: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    ...(sampleRow as unknown as ScenarioSummary),
    id: "s1", symbol: "TLT", target_price: 105, target_month: "2028-06",
    best_price: null, worst_price: null,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 1.0,
    archived_at: null, expired: false,
    target_anchor: "2028-06-16", days_to_anchor: 673,
    ...over,
  };
}

/** 記錄每一個請求，讓「取消不寫入」與「走 PATCH 不是重建」可斷言。 */
function mockApi(onPatch?: (body: unknown) => ScenarioSummary) {
  const calls: { url: string; method: string; body?: unknown }[] = [];
  // 儲存後 app 會沿既有佇列重新分析那個劇本；`/refresh` 得回傳**更新後**
  // 的那一列，否則是 mock 自己把卡片打回舊值，測到的不是 app 的行為。
  let current = card();
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ url, method, body });
    if (method === "PATCH") {
      current = onPatch?.(body) ?? card({ ...(body as object) } as never);
      return { ok: true, status: 200, json: async () => current } as Response;
    }
    // 開站觸發的是批次端點（T08／#196）——`"/refresh-run"` 本身也含
    // `"/refresh"` 子字串，這條分支得排在下面那條泛用 `/refresh` 判斷
    // 之前，否則會被吃掉、回錯形狀（一份 `ScenarioSummary` 而不是
    // `{results, remaining}`）。
    if (url === "/api/scenarios/refresh-run" && method === "POST") {
      return { ok: true, status: 200, json: async () => (
        { results: [{ scenario_id: current.id, ok: true, row: current }],
         remaining: [] }) } as Response;
    }
    if (url.includes("/refresh")) {
      return { ok: true, status: 200, json: async () => current } as Response;
    }
    return { ok: true, status: 200, json: async () => [current] } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return calls;
}

async function openEditor() {
  render(<App />);
  await screen.findByRole("button", { name: /編輯 TLT/ });
  await userEvent.click(screen.getByRole("button", { name: /編輯 TLT/ }));
  await screen.findByText("編輯劇本");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("入口", () => {
  it("卡片上有編輯入口，就在封存旁邊", async () => {
    mockApi();
    render(<App />);
    const row = await screen.findByRole("listitem");
    const actions = within(row).getAllByRole("button")
      .map((b) => b.getAttribute("aria-label"));
    expect(actions).toEqual(["編輯 TLT 2028-06", "封存 TLT 2028-06"]);
  });

  it("點編輯是把既有表單切成編輯模式，不是另開一套表單", async () => {
    mockApi();
    await openEditor();
    // 同一張表單：標題換了，但欄位還是那組
    expect(screen.queryByText("建立劇本")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("標的代號")).toHaveLength(1);
    expect(screen.getAllByLabelText("目標價位")).toHaveLength(1);
  });

  it("預填原資料", async () => {
    mockApi();
    await openEditor();
    expect(screen.getByLabelText("標的代號")).toHaveValue("TLT");
    expect(screen.getByLabelText("目標價位")).toHaveValue("105");
  });
});

describe("標的不可改", () => {
  it("標的欄位反灰且不可編輯", async () => {
    mockApi();
    await openEditor();
    expect(screen.getByLabelText("標的代號")).toBeDisabled();
  });

  it("送出時不帶 symbol——後端也沒有那個欄位可以收", async () => {
    const calls = mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.click(screen.getByRole("button", { name: "儲存變更" }));

    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH");
      expect(patch).toBeTruthy();
      expect(patch!.body).not.toHaveProperty("symbol");
    });
  });
});

describe("取消隨時可按", () => {
  it("什麼都沒改也能取消", async () => {
    const calls = mockApi();
    await openEditor();
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByText("編輯劇本")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("改到一半、內容還不合法時也能取消", async () => {
    const calls = mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByText("編輯劇本")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("取消後表單回到建立模式，且不留著剛剛打的內容", async () => {
    mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "999");
    await userEvent.click(screen.getByRole("button", { name: "取消" }));

    await userEvent.click(screen.getByRole("button", { name: /新增劇本/ }));
    await screen.findByText("建立劇本");
    expect(screen.getByLabelText("目標價位")).toHaveValue("");
    expect(screen.getByLabelText("標的代號")).toBeEnabled();
  });

  it("取消不動原劇本——卡片上的數字原封不動", async () => {
    mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "999");
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.getByRole("listitem")).toHaveTextContent("105"));
  });
});

describe("儲存", () => {
  it("走 PATCH 到同一個劇本，不是刪除＋重建", async () => {
    const calls = mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.click(screen.getByRole("button", { name: "儲存變更" }));

    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH");
      expect(patch?.url).toBe("/api/scenarios/s1");
    });
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(calls.some((c) => c.method === "POST"
      && c.url === "/api/scenarios")).toBe(false);
  });

  it("儲存後回到建立模式，卡片換成新數字", async () => {
    mockApi((body) => card({ ...(body as object), id: "s1",
                             symbol: "TLT" } as never));
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.click(screen.getByRole("button", { name: "儲存變更" }));

    await waitFor(() =>
      expect(screen.queryByText("編輯劇本")).not.toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByRole("listitem")).toHaveTextContent("120"));
  });

  it("thesis 改了之後重新分析一次——不留著對不上的舊結果", async () => {
    const calls = mockApi();
    await openEditor();
    await userEvent.clear(screen.getByLabelText("目標價位"));
    await userEvent.type(screen.getByLabelText("目標價位"), "120");
    await userEvent.click(screen.getByRole("button", { name: "儲存變更" }));

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/api/scenarios/s1/refresh")))
        .toBe(true));
  });
});
