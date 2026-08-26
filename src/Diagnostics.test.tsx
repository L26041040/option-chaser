/**
 * Settings 的 `Diagnostics / 報錯紀錄` 區塊（DG-06／#149）。
 *
 * 前端零解讀邏輯是這裡的紅線：清單順序、欄位內容全部照單全收後端給的
 * 字串，不重新排序、不重新判斷該不該顯示——那些規則只在後端測一次
 * （`test_diagnostics.py`／`test_storage_contract.py`）。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import Diagnostics from "./Diagnostics";
import type { DiagnosticEvent } from "./api";

function event(over: Partial<DiagnosticEvent> = {}): DiagnosticEvent {
  const severity = over.severity ?? "warning";
  return {
    event_id: "evt-1", correlation_id: "cid-1", ts: "2026-08-15T00:00:00+00:00",
    subsystem: "historical_iv", stage: "payload_parse", severity,
    // PC-03（#201）：省略時鏡射 `severity`，跟 `emit()` 同一套預設規則
    // ——這個頁面（Settings／Diagnostics）本身不讀這個欄位，純粹是為了
    // 讓假體形狀誠實，不因為固定寫死而跟 severity 對不上。
    user_facing: severity === "warning" || severity === "error",
    message: "raw_rows > 0 but parsed rows are 0",
    context: { raw_rows: 5, parsed_call_rows: 0 },
    ...over,
  };
}

/** 依 URL 分流：`/api/diagnostics` 走 events，其餘（DELETE 也算）用
 *  同一個假體處理。 */
function mockApi({ events, clearedCount = 0 }: {
  events: DiagnosticEvent[];
  clearedCount?: number;
}) {
  let current = events;
  const spy = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "DELETE") {
      current = [];
      return { ok: true, status: 200,
               json: async () => ({ cleared: clearedCount }) } as Response;
    }
    return { ok: true, status: 200, json: async () => current } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("空清單", () => {
  it("沒有任何紀錄時明說「目前沒有紀錄」", async () => {
    mockApi({ events: [] });
    render(<Diagnostics />);
    await waitFor(() =>
      expect(screen.getByText("目前沒有紀錄")).toBeInTheDocument());
  });
});

describe("清單", () => {
  it("每列顯示 timestamp／subsystem／stage／severity／簡短 message", async () => {
    mockApi({ events: [event()] });
    render(<Diagnostics />);
    await waitFor(() =>
      expect(screen.getByText("2026-08-15T00:00:00+00:00")).toBeInTheDocument());
    expect(screen.getByText("historical_iv")).toBeInTheDocument();
    expect(screen.getByText("payload_parse")).toBeInTheDocument();
    expect(screen.getByText("警告")).toBeInTheDocument();
    expect(screen.getByText("raw_rows > 0 but parsed rows are 0"))
      .toBeInTheDocument();
  });

  it("依後端給的順序渲染，不自己重新排序", async () => {
    mockApi({ events: [
      event({ event_id: "e-newest", message: "newest" }),
      event({ event_id: "e-oldest", message: "oldest" }),
    ] });
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByText("newest")).toBeInTheDocument());
    const rows = screen.getAllByText(/newest|oldest/);
    expect(rows.map((r) => r.textContent)).toEqual(["newest", "oldest"]);
  });

  it("點一筆展開完整 details，再點一次收起", async () => {
    mockApi({ events: [event({
      context: { raw_rows: 5, parsed_call_rows: 0, vendor_status: "ok" },
    })] });
    render(<Diagnostics />);
    const row = await screen.findByText("raw_rows > 0 but parsed rows are 0");

    expect(screen.queryByText("事件 ID")).not.toBeInTheDocument();
    await userEvent.click(row);
    expect(screen.getByText("事件 ID")).toBeInTheDocument();
    expect(screen.getByText("evt-1")).toBeInTheDocument();
    expect(screen.getByText("cid-1")).toBeInTheDocument();
    expect(screen.getByText("raw_rows")).toBeInTheDocument();
    expect(screen.getByText("vendor_status")).toBeInTheDocument();

    await userEvent.click(row);
    expect(screen.queryByText("事件 ID")).not.toBeInTheDocument();
  });
});

describe("Copy diagnostic info", () => {
  it("點 Copy 呼叫 clipboard 並帶完整內容", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    mockApi({ events: [event()] });
    render(<Diagnostics />);
    const row = await screen.findByText("raw_rows > 0 but parsed rows are 0");
    await userEvent.click(row);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = JSON.parse(writeText.mock.calls[0][0] as string);
    expect(copied.event_id).toBe("evt-1");
    expect(copied.context).toEqual({ raw_rows: 5, parsed_call_rows: 0 });
    expect(screen.getByRole("button", { name: "已複製" })).toBeInTheDocument();
  });

  it("clipboard 不可用時退回顯示可全選的文字區塊，不是靜默失敗", async () => {
    Object.assign(navigator, { clipboard: undefined });
    mockApi({ events: [event()] });
    render(<Diagnostics />);
    const row = await screen.findByText("raw_rows > 0 but parsed rows are 0");
    await userEvent.click(row);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    const fallback = await screen.findByLabelText("複製失敗，請手動全選複製");
    expect(fallback.tagName).toBe("TEXTAREA");
    const copied = JSON.parse((fallback as HTMLTextAreaElement).value);
    expect(copied.event_id).toBe("evt-1");
  });
});

describe("Clear diagnostics", () => {
  it("需要二次確認才真的送出", async () => {
    const spy = mockApi({ events: [event()] });
    render(<Diagnostics />);
    await screen.findByText("raw_rows > 0 but parsed rows are 0");

    await userEvent.click(screen.getByRole("button", { name: "Clear diagnostics" }));
    expect(spy.mock.calls.some(([, init]) => init?.method === "DELETE"))
      .toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "確定清除" }));
    await waitFor(() =>
      expect(spy.mock.calls.some(([, init]) => init?.method === "DELETE"))
        .toBe(true));
  });

  it("取消後不送出，清單維持原狀", async () => {
    const spy = mockApi({ events: [event()] });
    render(<Diagnostics />);
    await screen.findByText("raw_rows > 0 but parsed rows are 0");

    await userEvent.click(screen.getByRole("button", { name: "Clear diagnostics" }));
    await userEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(spy.mock.calls.some(([, init]) => init?.method === "DELETE"))
      .toBe(false);
    expect(screen.getByText("raw_rows > 0 but parsed rows are 0"))
      .toBeInTheDocument();
  });

  it("清完清單變空，顯示「目前沒有紀錄」", async () => {
    mockApi({ events: [event()] });
    render(<Diagnostics />);
    await screen.findByText("raw_rows > 0 but parsed rows are 0");

    await userEvent.click(screen.getByRole("button", { name: "Clear diagnostics" }));
    await userEvent.click(screen.getByRole("button", { name: "確定清除" }));

    await waitFor(() =>
      expect(screen.getByText("目前沒有紀錄")).toBeInTheDocument());
  });
});

describe("錯誤", () => {
  it("讀取失敗時說明原因", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
    } as Response)));
    render(<Diagnostics />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("資料庫連不上"));
  });
});

describe("結構", () => {
  it("Settings 頁的 Diagnostics 區塊掛在同一個可見性下（跟其他區塊一樣是 <section class=\"card\">）",
     async () => {
    mockApi({ events: [] });
    const { container } = render(<Diagnostics />);
    await waitFor(() =>
      expect(screen.getByText("目前沒有紀錄")).toBeInTheDocument());
    const section = within(container).getByLabelText("Diagnostics");
    expect(section.tagName).toBe("SECTION");
    expect(section.className).toContain("card");
  });
});
