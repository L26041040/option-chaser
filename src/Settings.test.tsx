/**
 * 設定頁元件測試（Settings／#124）。
 *
 * 除了一般行為，這裡守三條需求方裁示：文案不得出現「推薦」／vendor 比較
 * ／未來規劃；自訂只能挑白名單、不能填任意 endpoint；同一 Provider 的
 * token 不要求輸入兩次。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import Settings from "./Settings";
import type { SettingsView } from "./api";

const PROVIDER = "marketdata-app";

function view(overrides: Partial<SettingsView> = {}): SettingsView {
  return {
    supported_providers: [{ id: PROVIDER, label: "Market Data App" }],
    market_data: { mode: "default", provider: null, default_label: "Cboe" },
    historical_iv: { mode: "default", provider: null, default_label: "無" },
    credentials: {
      [PROVIDER]: {
        configured: false, masked: null, updated_at: null,
        status: "unset", reason: null, checked_at: null,
      },
    },
    market_data_effective: { source: "Cboe", fallback: false, reason: null },
    historical_iv_enabled: false,
    updated_at: null,
    ...overrides,
  };
}

const CONFIGURED = {
  [PROVIDER]: {
    configured: true,
    masked: "••••••••abcd",
    updated_at: "2026-08-12T00:00:00+00:00",
    status: "ok" as const,
    reason: null,
    checked_at: "2026-08-12T00:00:00+00:00",
  },
};

/** 依序回應：每次 fetch 取下一個 view（不足時重複最後一個）。 */
function mockApi(views: SettingsView[]) {
  let i = 0;
  const spy = vi.fn(async (_url: string, _init?: RequestInit) => {
    const body = views[Math.min(i, views.length - 1)];
    i += 1;
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** 那一列（`aria-label` ＝ 資料用途名稱）。 */
function section(name: string) {
  return screen.getByRole("region", { name }) as HTMLElement;
}

async function ready(name = "Market Data") {
  await waitFor(() => expect(section(name)).toBeInTheDocument());
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("兩列與預設值", () => {
  it("Data / API 底下就是 Market Data 與 Historical IV 兩列", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    expect(screen.getByText("Data / API")).toBeInTheDocument();
    expect(section("Market Data")).toBeInTheDocument();
    expect(section("Historical IV")).toBeInTheDocument();
  });

  it("預設值分別是 Cboe 與「無」", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    expect(within(section("Market Data")).getByText("預設：Cboe")).toBeInTheDocument();
    expect(within(section("Historical IV")).getByText("預設：無")).toBeInTheDocument();
  });

  it("預設模式下不顯示 Provider 與 Token 欄位", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    expect(md.queryByLabelText("API Token")).not.toBeInTheDocument();
    expect(md.queryByLabelText("資料源")).not.toBeInTheDocument();
  });

  it("選了自訂才展開 Provider 與 Token 欄位", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    expect(md.getByLabelText("API Token")).toBeInTheDocument();
    expect(md.getByLabelText("資料源")).toBeInTheDocument();
  });
});

describe("文案裁示（需求方明示）", () => {
  it("寫「目前支援」，不寫「推薦」", async () => {
    mockApi([view()]);
    const { container } = render(<Settings />);
    await ready();
    await userEvent.click(
      within(section("Market Data")).getByRole("radio", { name: "自訂" }));
    expect(screen.getByText(/目前支援：Market Data App/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/推薦/);
  });

  it("提示使用者需自行申請 API Token", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    await userEvent.click(
      within(section("Market Data")).getByRole("radio", { name: "自訂" }));
    expect(screen.getByText("需自行申請 API Token")).toBeInTheDocument();
  });

  it("不出現 vendor 比較或未來規劃的字眼", async () => {
    mockApi([view()]);
    const { container } = render(<Settings />);
    await ready();
    await userEvent.click(
      within(section("Market Data")).getByRole("radio", { name: "自訂" }));
    await userEvent.click(
      within(section("Historical IV")).getByRole("radio", { name: "自訂" }));
    // 比較級／規劃用語：出現任何一個都代表文案又長回去了。
    expect(container.textContent).not.toMatch(
      /推薦|建議使用|最佳|首選|比較|即將|未來|敬請期待|規劃中|支援中/);
  });
});

describe("自訂只能挑白名單", () => {
  it("資料源是下拉選單，不是可以填任意網址的輸入框", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    const select = md.getByLabelText("資料源");
    expect(select.tagName).toBe("SELECT");
  });

  it("選項就是後端給的白名單，前端不自己多列一家", async () => {
    mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    const options = within(md.getByLabelText("資料源") as HTMLElement)
      .getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Market Data App"]);
  });
});

describe("儲存", () => {
  it("送出模式選擇到 /api/settings", async () => {
    const spy = mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    await userEvent.click(md.getByRole("button", { name: "儲存" }));

    await waitFor(() => {
      const put = spy.mock.calls.find(
        ([url, init]) => url === "/api/settings" && init?.method === "PUT");
      expect(put).toBeTruthy();
      expect(JSON.parse(put![1]!.body as string)).toEqual({
        market_data: { mode: "custom", provider: PROVIDER },
        historical_iv: { mode: "default", provider: null },
      });
    });
  });

  it("有打 token 才連 credential 一起送", async () => {
    const spy = mockApi([view()]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    await userEvent.type(md.getByLabelText("API Token"), "tok-secret-1234");
    await userEvent.click(md.getByRole("button", { name: "儲存" }));

    await waitFor(() => {
      const cred = spy.mock.calls.find(
        ([url]) => url === `/api/settings/credentials/${PROVIDER}`);
      expect(cred).toBeTruthy();
      expect(JSON.parse(cred![1]!.body as string)).toEqual({
        token: "tok-secret-1234",
      });
    });
  });

  it("沒打 token 就不動 credential——只改模式不該清掉已存的那把", async () => {
    const spy = mockApi([view({ credentials: CONFIGURED })]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    await userEvent.click(md.getByRole("button", { name: "儲存" }));

    await waitFor(() =>
      expect(spy.mock.calls.some(([url, init]) =>
        url === "/api/settings" && init?.method === "PUT")).toBe(true));
    expect(spy.mock.calls.some(
      ([url]) => String(url).includes("/credentials/"))).toBe(false);
  });

  it("送出後輸入框就地清空，完整 token 不留在畫面上", async () => {
    mockApi([
      view(),
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        credentials: CONFIGURED,
      }),
    ]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    await userEvent.type(md.getByLabelText("API Token"), "tok-secret-1234");
    await userEvent.click(md.getByRole("button", { name: "儲存" }));
    await waitFor(() =>
      expect(md.getByLabelText("API Token")).toHaveValue(""));
  });
});

describe("已儲存的狀態", () => {
  it("顯示遮罩形式，不顯示完整 token", async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        credentials: CONFIGURED,
      }),
    ]);
    const { container } = render(<Settings />);
    await ready();
    expect(screen.getByText(/已儲存 ••••••••abcd/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/SECRET|tok-/);
  });

  it("未設定時說「未設定」", async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
      }),
    ]);
    render(<Settings />);
    await ready();
    expect(within(section("Market Data")).getByText(/未設定/)).toBeInTheDocument();
  });

  it("已設定時可以清除，回到未設定", async () => {
    const spy = mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        credentials: CONFIGURED,
      }),
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
      }),
    ]);
    render(<Settings />);
    await ready();
    await userEvent.click(
      within(section("Market Data")).getByRole("button", { name: "清除 token" }));
    await waitFor(() =>
      expect(spy.mock.calls.some(([url, init]) =>
        url === `/api/settings/credentials/${PROVIDER}`
        && init?.method === "DELETE")).toBe(true));
  });
});

describe("同一 Provider 的 token 只輸入一次", () => {
  it("兩列都選同一家且已設定時，第二列說共用、不再要求輸入", async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        historical_iv: { mode: "custom", provider: PROVIDER, default_label: "無" },
        credentials: CONFIGURED,
      }),
    ]);
    render(<Settings />);
    await ready();
    const iv = within(section("Historical IV"));
    expect(iv.getByText("與 Market Data 共用同一把 token")).toBeInTheDocument();
    expect(iv.queryByLabelText("API Token")).not.toBeInTheDocument();
  });

  it("尚未設定過時兩列都給輸入框——還沒有可共用的東西", async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        historical_iv: { mode: "custom", provider: PROVIDER, default_label: "無" },
      }),
    ]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Historical IV")).getByLabelText("API Token"),
    ).toBeInTheDocument();
  });

  it("另一列是預設時不算共用，這一列照常要求輸入", async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        credentials: CONFIGURED,
      }),
    ]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Market Data")).getByLabelText("API Token"),
    ).toBeInTheDocument();
  });
});

describe("錯誤", () => {
  it("載入失敗時說明原因，不是空白畫面", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
    } as Response)));
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("資料庫連不上"));
  });
});

/* ---------- 測試連線與 fallback（#125） ---------- */

function cred(over: Partial<SettingsView["credentials"][string]> = {}) {
  return {
    [PROVIDER]: {
      configured: true,
      masked: "••••••••abcd",
      updated_at: "2026-08-12T00:00:00+00:00",
      status: "unverified" as const,
      reason: null,
      checked_at: null,
      ...over,
    },
  };
}

const CUSTOM_MD = {
  market_data: {
    mode: "custom" as const, provider: PROVIDER, default_label: "Cboe",
  },
};

describe("測試連線的三態", () => {
  it("還沒存 token：未設定", async () => {
    mockApi([view(CUSTOM_MD)]);
    render(<Settings />);
    await ready();
    expect(within(section("Market Data")).getByText(/未設定/)).toBeInTheDocument();
  });

  it("存了但沒測過：尚未驗證，不是「已連線」", async () => {
    mockApi([view({ ...CUSTOM_MD, credentials: cred() })]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    expect(md.getByText(/尚未驗證/)).toBeInTheDocument();
    expect(md.queryByText(/已連線/)).not.toBeInTheDocument();
  });

  it("測試成功：已連線", async () => {
    mockApi([view({ ...CUSTOM_MD, credentials: cred({ status: "ok" }) })]);
    render(<Settings />);
    await ready();
    expect(within(section("Market Data")).getByText(/已連線/)).toBeInTheDocument();
  });

  it("測試失敗：顯示驗證失敗與可讀原因", async () => {
    mockApi([view({
      ...CUSTOM_MD,
      credentials: cred({ status: "failed", reason: "認證被拒——請確認 token" }),
    })]);
    render(<Settings />);
    await ready();
    const md = within(section("Market Data"));
    expect(md.getByText(/驗證失敗/)).toBeInTheDocument();
    expect(md.getByText(/認證被拒——請確認 token/)).toBeInTheDocument();
  });

  it("按測試連線會打驗證端點", async () => {
    const spy = mockApi([view({ ...CUSTOM_MD, credentials: cred() })]);
    render(<Settings />);
    await ready();
    await userEvent.click(
      within(section("Market Data")).getByRole("button", { name: "測試連線" }));
    await waitFor(() =>
      expect(spy.mock.calls.some(([url, init]) =>
        url === `/api/settings/credentials/${PROVIDER}/test`
        && init?.method === "POST")).toBe(true));
  });

  it("沒有 token 時測試連線不可按——沒有東西可測", async () => {
    mockApi([view(CUSTOM_MD)]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Market Data")).getByRole("button", { name: "測試連線" }),
    ).toBeDisabled();
  });
});

describe("fallback 誠實顯示", () => {
  it("自訂不可用時說出現在用的是哪家、為什麼", async () => {
    mockApi([view({
      ...CUSTOM_MD,
      credentials: cred({ status: "failed", reason: "額度用盡" }),
      market_data_effective: {
        source: "Cboe", fallback: true,
        reason: "Market Data App 額度用盡，改用預設來源",
      },
    })]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Market Data"))
        .getByText(/目前使用 Cboe：Market Data App 額度用盡，改用預設來源/),
    ).toBeInTheDocument();
  });

  it("自訂正常運作時不顯示 fallback 提示", async () => {
    mockApi([view({
      ...CUSTOM_MD,
      credentials: cred({ status: "ok" }),
      market_data_effective: {
        source: "Market Data App", fallback: false, reason: null,
      },
    })]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Market Data")).queryByText(/目前使用/),
    ).not.toBeInTheDocument();
  });

  it("Historical IV 那一列不顯示 Market Data 的 fallback 提示", async () => {
    mockApi([view({
      ...CUSTOM_MD,
      historical_iv: {
        mode: "custom", provider: PROVIDER, default_label: "無",
      },
      credentials: cred({ status: "failed", reason: "額度用盡" }),
      market_data_effective: {
        source: "Cboe", fallback: true, reason: "Market Data App 額度用盡",
      },
    })]);
    render(<Settings />);
    await ready();
    expect(
      within(section("Historical IV")).queryByText(/目前使用/),
    ).not.toBeInTheDocument();
  });
});
