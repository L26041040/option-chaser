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
import { _resetCacheForTests } from "./fetchCache";
import type { Role } from "./superuser";
import { fakeMediaQueryList } from "./test-setup";

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

/**
 * 依序回應：每次 fetch 取下一個 view（不足時重複最後一個）。
 *
 * `Settings` 現在也掛著 `<Diagnostics />`（DG-06／#149），它自己會打
 * `/api/diagnostics`——那條路徑分流成固定回空清單，不吃掉這裡的 view
 * 序列（否則每個既有測試的 view 對應關係都會被這個額外的請求打亂）。
 *
 * AUTH-06（#313）：`<RoleLogin />` 也會自己打 `GET /api/auth/status`
 * ——同一個理由分流成獨立回應，目前角色由 `role` 參數決定（預設
 * `"superadmin"`：credential CRUD 自 AUTH-03 起 gate 在 Super Admin，
 * 本檔案大多數測試關心的是 credential CRUD 業務邏輯本身，不是軸二
 * 守門機制，後者由本檔案末尾專屬的 describe block 負責，那裡會用
 * `"normal"` 覆寫）。
 */
/** OG-11（#322）：`<SuperUserAdmin />` 掛載時連帶掛的 `OpsStats` 一律
 *  打 `/api/ops/metrics`——這個檔案的既有測試不關心系統指標方塊本身
 *  （那由 `SuperUserAdmin.test.tsx` 專屬覆蓋），只需要一份全部欄位
 *  都存在的最小假體，讓這個新的非同步 effect 不會拋錯打斷其他斷言。 */
const EMPTY_OPS_METRICS = {
  chain_fetch_count: [], chain_429_count: [], stale_serve_count: [],
  cold_miss_count: [], refresh_duration_ms: [], history_read_volume: [],
  abandoned_owner_cleanup_count: [],
  table_size: {},
  anonymous_owners: { active: 0, abandoned: 0, eligible_for_hard_delete: 0,
                     protected: 0, total: 0 },
  scenarios: { total: 0, average_per_owner: 0 },
  alerts: [],
};

function mockApi(views: SettingsView[], { role = "superadmin" as Role } = {}) {
  let i = 0;
  const spy = vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).startsWith("/api/diagnostics")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url).startsWith("/api/auth/status")) {
      return { ok: true, status: 200, json: async () => ({ role }) } as Response;
    }
    // PB-10（#301）：`<SuperUserAdmin />` 在角色達到 Super Admin 後
    // 立刻打 `/api/superuser/owners`——同一個理由分流成固定的空清單／
    // 空紀錄，這個檔案的既有測試關心的是 credential CRUD，不是管理
    // 面板本身（那由 `SuperUserAdmin.test.tsx` 專屬覆蓋）。
    if (String(url).startsWith("/api/superuser/owners")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url).startsWith("/api/superuser/audit-log")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url).startsWith("/api/ops/metrics")) {
      return { ok: true, status: 200, json: async () => EMPTY_OPS_METRICS } as Response;
    }
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

const ROLE_LABEL: Record<Role, string> = {
  normal: "Normal User", superuser: "Super User", superadmin: "Super Admin",
};

/**
 * AUTH-06（#313）：`<RoleLogin />` 的角色狀態是跟 view 載入各自獨立
 * 完成的另一個非同步 effect——只等 `section(name)` 出現，不保證呼叫
 * 端接下來的斷言看到的是角色已經到位這個穩定狀態，而不是介於兩者
 * 之間的中繼畫面。`expectRole` 預設 `"superadmin"`（配合 `mockApi()`
 * 同一個預設值）；`"normal"` 時等的是登入表單本身（`RoleLogin` 在
 * 這個角色下不會顯示「目前身分」那句話，見該元件），其餘角色等對應
 * 的身分文字。
 */
async function ready(name = "Market Data",
    { expectRole = "superadmin" as Role } = {}) {
  await waitFor(() => expect(section(name)).toBeInTheDocument());
  if (expectRole === "normal") {
    await waitFor(() => expect(screen.getByLabelText("密碼")).toBeInTheDocument());
  } else {
    await waitFor(() =>
      expect(screen.getByText(`目前身分：${ROLE_LABEL[expectRole]}。`))
        .toBeInTheDocument());
  }
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

describe("同一 Provider 的 credential 只由一列持有（#127）", () => {
  it("兩列都自訂時，Historical IV 說共用、完全不要求輸入", async () => {
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
    expect(iv.getByText("與上方共用 credential")).toBeInTheDocument();
    expect(iv.queryByLabelText("API Token")).not.toBeInTheDocument();
  });

  it("**尚未設定過**時 Historical IV 一樣不給輸入框——這正是 #127 收掉的路徑",
     async () => {
    mockApi([
      view({
        market_data: { mode: "custom", provider: PROVIDER, default_label: "Cboe" },
        historical_iv: { mode: "custom", provider: PROVIDER, default_label: "無" },
      }),
    ]);
    render(<Settings />);
    await ready();
    const iv = within(section("Historical IV"));
    expect(iv.queryByLabelText("API Token")).not.toBeInTheDocument();
    expect(iv.getByText("與上方共用 credential")).toBeInTheDocument();
    // 輸入框在持有者那一列
    expect(
      within(section("Market Data")).getByLabelText("API Token"),
    ).toBeInTheDocument();
  });

  it("只有 Historical IV 自訂時，輸入框落在它自己那列——不會無處可設",
     async () => {
    mockApi([
      view({
        historical_iv: { mode: "custom", provider: PROVIDER, default_label: "無" },
      }),
    ]);
    render(<Settings />);
    await ready();
    const iv = within(section("Historical IV"));
    expect(iv.getByLabelText("API Token")).toBeInTheDocument();
    expect(iv.queryByText("與上方共用 credential")).not.toBeInTheDocument();
  });

  it("共用列沒有自己的「測試連線」與「清除 token」——那是同一把 credential 的操作",
     async () => {
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
    expect(iv.queryByRole("button", { name: "測試連線" })).not.toBeInTheDocument();
    expect(iv.queryByRole("button", { name: "清除 token" })).not.toBeInTheDocument();
    // 但模式選擇仍要存得起來
    expect(iv.getByRole("button", { name: "儲存" })).toBeInTheDocument();
    // 持有者那列照樣有
    expect(
      within(section("Market Data")).getByRole("button", { name: "測試連線" }),
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
    // 這個假體對所有路徑都回同一個失敗——`<Diagnostics />`（DG-06／
    // #149）自己也會打 `/api/diagnostics` 並顯示自己的 alert，因此畫面
    // 上會有不只一個 `role="alert"`，用 `getAllByRole` 找出這一個。
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "資料庫連不上" }),
    } as Response)));
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getAllByRole("alert").some(
        (a) => a.textContent === "資料庫連不上")).toBe(true));
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

/* ---------- AUTH-06（#313）：三層角色登入 ---------- */

const SUPERUSER_PASSWORD = "correct-superuser-secret";
const SUPERADMIN_PASSWORD = "correct-superadmin-secret";

/**
 * 登入／登出流程專屬的假體——`role` 是可變狀態（模擬伺服器端的
 * `RoleSession`），`POST /api/auth/login` 依密碼命中哪一把改變它，
 * `POST /api/auth/logout` 把它撥回 `normal`，`GET /api/auth/status`
 * 永遠回目前狀態——跟真實後端「單一真相來源」的語意一致。不透過
 * `Authorization` 標頭傳遞任何東西：`__Host-oc_role` 是 `HttpOnly`
 * cookie，前端 JS 讀不到也不需要讀到它，這個假體因此也不必（也不能）
 * 模擬 cookie 本身，只需要讓 `role` 這個伺服器端狀態正確反映請求
 * 順序即可。
 */
function mockApiWithLogin(views: SettingsView[],
    { initialRole = "normal" as Role } = {}) {
  let role: Role = initialRole;
  let i = 0;
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).startsWith("/api/diagnostics")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url) === "/api/auth/login") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { password: string };
      if (body.password === SUPERADMIN_PASSWORD) role = "superadmin";
      else if (body.password === SUPERUSER_PASSWORD) role = "superuser";
      else {
        return { ok: false, status: 401,
                 json: async () => ({ detail: "unauthorized" }) } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ role }) } as Response;
    }
    if (String(url) === "/api/auth/logout") {
      role = "normal";
      return { ok: true, status: 200, json: async () => ({ role }) } as Response;
    }
    if (String(url).startsWith("/api/auth/status")) {
      return { ok: true, status: 200, json: async () => ({ role }) } as Response;
    }
    if (String(url).startsWith("/api/superuser/owners")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url).startsWith("/api/superuser/audit-log")) {
      return { ok: true, status: 200, json: async () => [] } as Response;
    }
    if (String(url).startsWith("/api/ops/metrics")) {
      return { ok: true, status: 200, json: async () => EMPTY_OPS_METRICS } as Response;
    }
    const body = views[Math.min(i, views.length - 1)];
    i += 1;
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("三層角色登入（AUTH-06／#313）", () => {
  it("預設（未登入）看不到 API Token 輸入框，但模式選項照常可用", async () => {
    mockApiWithLogin([view()]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    expect(md.queryByLabelText("API Token")).not.toBeInTheDocument();
    expect(
      md.getByText("需要 Super Admin 身份才能設定 API Token"),
    ).toBeInTheDocument();
    // 模式選擇本身不是 credential 寫入路徑——不該因此一起被擋。
    expect(md.getByRole("radio", { name: "自訂" })).toBeChecked();
  });

  it("測試連線／清除 token 按鈕在未登入時不呈現", async () => {
    mockApiWithLogin(
      [view({ ...CUSTOM_MD, credentials: cred({ status: "ok" }) })]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });
    const md = within(section("Market Data"));
    expect(md.queryByRole("button", { name: "測試連線" })).not.toBeInTheDocument();
    expect(md.queryByRole("button", { name: "清除 token" })).not.toBeInTheDocument();
  });

  it("Super User 密碼登入後看得到身分，但仍看不到 credential CRUD", async () => {
    // AUTH-03 起 credential CRUD 收斂為 Super-Admin-only——Super User
    // 這一層的正確行為是「看得見自己已登入」但輸入框依然不出現。
    mockApiWithLogin([view()]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });

    await userEvent.type(screen.getByLabelText("密碼"), SUPERUSER_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "登入" }));

    await waitFor(() =>
      expect(screen.getByText("目前身分：Super User。")).toBeInTheDocument());
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    expect(md.queryByLabelText("API Token")).not.toBeInTheDocument();
    expect(
      md.getByText("需要 Super Admin 身份才能設定 API Token"),
    ).toBeInTheDocument();
  });

  it("Super Admin 密碼登入後，Token 輸入框出現", async () => {
    mockApiWithLogin([view()]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });

    await userEvent.type(screen.getByLabelText("密碼"), SUPERADMIN_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "登入" }));

    await waitFor(() =>
      expect(screen.getByText("目前身分：Super Admin。")).toBeInTheDocument());
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    expect(md.getByLabelText("API Token")).toBeInTheDocument();
  });

  it("密碼錯誤時顯示錯誤、不會誤登入", async () => {
    mockApiWithLogin([view()]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });

    await userEvent.type(screen.getByLabelText("密碼"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText(/目前身分：/)).not.toBeInTheDocument();
  });

  it("登出後回到 Normal User，Token 輸入框重新消失", async () => {
    mockApiWithLogin([view()], { initialRole: "superadmin" });
    render(<Settings />);
    await ready();

    await userEvent.click(screen.getByRole("button", { name: "登出" }));

    await waitFor(() => expect(screen.getByLabelText("密碼")).toBeInTheDocument());
    const md = within(section("Market Data"));
    await userEvent.click(md.getByRole("radio", { name: "自訂" }));
    expect(md.queryByLabelText("API Token")).not.toBeInTheDocument();
  });

  it("重新整理頁面（模擬瀏覽器重啟）仍保持登入狀態", async () => {
    // 持久登入的唯一機制是伺服器簽發的 cookie（`__Host-oc_role`）——
    // 真正的重新整理會把整個 JS 執行環境（含 `fetchCache` 模組層級
    // 快取）一起清空，只有伺服器端的 cookie 存活。這裡卸載＋
    // `_resetCacheForTests()`（清掉快取，模擬「JS 狀態歸零」）＋
    // 重新掛載，但**保留** `mockApiWithLogin()` 假體本身的 `role`
    // 狀態（模擬「cookie 沒被清掉」）——第二次掛載必須真的重新打一次
    // `GET /api/auth/status`、且答案仍是已登入，不需要使用者重新
    // 輸入密碼。
    mockApiWithLogin([view(), view()], { initialRole: "superadmin" });
    const { unmount } = render(<Settings />);
    await ready();
    unmount();
    _resetCacheForTests();

    render(<Settings />);
    await ready();
  });

  it("密碼絕不寫進 sessionStorage／localStorage（Security considerations）",
     async () => {
    mockApiWithLogin([view()]);
    render(<Settings />);
    await ready("Market Data", { expectRole: "normal" });

    await userEvent.type(screen.getByLabelText("密碼"), SUPERADMIN_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    await waitFor(() =>
      expect(screen.getByText("目前身分：Super Admin。")).toBeInTheDocument());

    for (let idx = 0; idx < sessionStorage.length; idx += 1) {
      const key = sessionStorage.key(idx)!;
      expect(sessionStorage.getItem(key)).not.toContain(SUPERADMIN_PASSWORD);
    }
    for (let idx = 0; idx < localStorage.length; idx += 1) {
      const key = localStorage.key(idx)!;
      expect(localStorage.getItem(key)).not.toContain(SUPERADMIN_PASSWORD);
    }
  });
});

describe("OG-11（#322）：桌面版左側 subnav（手機版單欄堆疊零改動）", () => {
  function goDesktop() {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
  }

  /** 桌面版預設分頁是「一般」，`ready()`（等 Market Data 出現）在這裡
   *  永遠等不到——「資料來源」分頁沒點開之前 Market Data 根本不在
   *  DOM 裡。改成等 subnav 本身（`role="tablist"`）出現，這才是桌面
   *  版無論停在哪個分頁都一定存在的東西。 */
  async function readyDesktop() {
    await waitFor(() => expect(screen.getByRole("tablist")).toBeInTheDocument());
  }

  it("桌面：預設分頁是「一般」，顯示登入區塊；「Data / API」收在" +
     "「資料來源」分頁，預設不可見", async () => {
    goDesktop();
    mockApi([view()]);
    render(<Settings />);
    await readyDesktop();

    expect(screen.getByRole("tab", { name: "一般" }))
      .toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Data / API")).not.toBeInTheDocument();
  });

  it("桌面：點「資料來源」分頁換成顯示 Data / API，登入區塊跟著隱藏", async () => {
    goDesktop();
    mockApi([view()]);
    render(<Settings />);
    await readyDesktop();

    await userEvent.click(screen.getByRole("tab", { name: "資料來源" }));

    await waitFor(() => expect(screen.getByText("Data / API")).toBeInTheDocument());
    expect(screen.queryByText(/目前身分：/)).not.toBeInTheDocument();
  });

  it("桌面：Super Admin 才看得到「管理後台」分頁，點下去顯示管理面板", async () => {
    goDesktop();
    mockApi([view()], { role: "superadmin" });
    render(<Settings />);
    await readyDesktop();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "管理後台" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("tab", { name: "管理後台" }));
    expect(await screen.findByText("Super User 管理面板")).toBeInTheDocument();
  });

  it("桌面：Normal User 看不到「管理後台」分頁——不是隱藏起來，是根本" +
     "不在 subnav 清單裡", async () => {
    goDesktop();
    mockApi([view()], { role: "normal" });
    render(<Settings />);
    await readyDesktop();
    await waitFor(() => expect(screen.getByLabelText("密碼")).toBeInTheDocument());

    expect(screen.queryByRole("tab", { name: "管理後台" })).not.toBeInTheDocument();
  });

  it("手機（預設 matchMedia）：不出現 subnav，全部區塊一次堆疊顯示" +
     "——手機版零改動", async () => {
    mockApi([view()], { role: "superadmin" });
    render(<Settings />);
    await ready();

    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.getByText("Data / API")).toBeInTheDocument();
    expect(screen.getByText("Super User 管理面板")).toBeInTheDocument();
  });
});
