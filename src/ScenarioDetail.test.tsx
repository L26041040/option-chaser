import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BANNED_JARGON } from "./bannedCopy";
import ScenarioDetail from "./ScenarioDetail";
import sample from "../contracts/analysis_sample.json";
import sampleRow from "../contracts/scenario_row_sample.json";
import { candidate, result, view as buildView } from "./family.fixtures";
import { fakeMediaQueryList } from "./test-setup";
import {
  baselineTopCandidate,
  type AnalysisView, type CandidateLegs, type Leg,
} from "./api";

const view = sample as unknown as AnalysisView;
const row = sampleRow as unknown as Record<string, unknown>;

/** 契約樣本本身：目標價 130、baseline 候選買 118／賣 122。 */
function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...row, id: "s1", symbol: "XYZ", target_price: view.params.target_price,
    target_month: view.params.target_month,
    latest_analyzed_at: "2026-08-04T09:30:00+00:00", best_return: 5.67,
    latest_result: view, ...overrides,
  };
}

/** 改寫 baseline 期第 1 名候選的某些欄位，其餘契約原樣。
 *
 * T09（#191）：完整內容集中在 `candidate_pool`，容器只留 key 引用——
 * 這裡只需要 patch 池子裡那一筆，`expiry_top10[].candidate_keys` 完全不用
 * 動（就算 patch 改了候選自己的 `candidate_key` 欄位值，容器裡引用它
 * 的那個 dict key 字串本身仍是原來的，`resolveCandidate()` 靠 dict key
 * 找到它、回傳的物件內容才是 patch 過的那份，跟 `baselineTopCandidate()`
 * 的既有讀取路徑一致）。 */
function withTopCandidate(patch: Record<string, unknown>): AnalysisView {
  const result = view.results[0];
  const group = result.expiry_top10!.find((g) => g.expiry === view.baseline_expiry)!;
  const key = group.candidate_keys[0];
  return {
    ...view,
    candidate_pool: {
      ...view.candidate_pool,
      [key]: { ...view.candidate_pool![key], ...patch },
    },
  };
}

/**
 * 主圖那一張表。V6（#54）之後頁面上有很多張 Heatmap（到期日結構裡每個
 * 候選收合著一張），所以這裡的斷言一律鎖定主圖那一區，不用全頁查找。
 *
 * MVP V3（#103）起，主圖只剩 Heatmap 本身——候選身分／名次／目標報酬
 * 在手機頭條 Hero 卡／桌面身分列，見 `heroSection()`。
 */
function mainChart() {
  return within(screen.getByRole("heading", { name: "劇本主圖" })
    .closest("section")!);
}

/**
 * SW-10（#340，Owner 真機驗收）：`ScenarioContext`（劇本設定卡）／
 * `Summary`（摘要卡）已整段刪除——逐項比對後跟手機版 `MobileHero`
 * （這裡）／桌面版 `.toolbar` 身分列（見 OG-06 describe block 自己的
 * `header()` helper）全部重複，不是兩張獨立卡片各自的內容。這個檔案
 * 的測試預設在手機分支下執行（沒有 stub `matchMedia` 時 `useIsDesktop()`
 * 回 `false`），因此這裡固定指向 `MobileHero` 的 `aria-label="劇本
 * 頭條"` 區塊；桌面分支的等價查詢在各自的 describe block 裡用
 * `header()`。 */
function heroSection() {
  return within(screen.getByRole("region", { name: "劇本頭條" }));
}

function mockDetail(body: unknown, ok = true, status = 200) {
  const spy = vi.fn(async () => ({ ok, status, json: async () => body }));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("手機頭條 Hero 卡承接原「劇本設定」獨有欄位（OPTION-CHASER-" +
        "CLOSEOUT-001，項目 2；SW-10／#340 起 `ScenarioContext` 整段刪除）", () => {
  it("顯示標的、目標價、目標年月、方向、啟用的策略類型——使用者原本" +
     "建立劇本時填的東西，不是最佳策略的內容", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.getByText(view.meta.symbol)).toBeInTheDocument();
    expect(hero.getByText(new RegExp(
      `目標 .?\\$?${view.params.target_price.toFixed(2)} · ${view.params.target_month}`)))
      .toBeInTheDocument();
    // 契約樣本 target=130 高於 spot，方向應為看漲。
    expect(hero.getByText("看漲")).toBeInTheDocument();
    // 契約樣本劇本只啟用 Vertical Spread 這一個 family。
    expect(hero.getByText(/啟用的策略類型：Vertical Spread/)).toBeInTheDocument();
  });

  it("啟用多個 family 時全部列出", async () => {
    mockDetail(detail({ strategies: ["single-leg", "butterfly"] }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.getByText(/啟用的策略類型：Call \/ Put、Butterfly/)).toBeInTheDocument();
  });

  it("舊存 View 沒有 direction 欄位時顯示「—」，不假裝算得出方向", async () => {
    const { direction: _drop, ...withoutDirection } = view;
    mockDetail(detail({ latest_result: withoutDirection }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.getByText("—")).toBeInTheDocument();
  });
});

describe("手機頭條 Hero 卡（SW-10／#340 起併吞 `Summary` 摘要卡的識別／" +
        "報酬欄位，進場成本與確切策略子類則留在既有的下方區塊）", () => {
  it("顯示現價、還需（所需漲幅）、目標價與目標年月", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    // SW-10 起頁面上只剩這一處會顯示現價／目標價（`ScenarioContext`／
    // `Summary` 已刪除），不必再刻意縮小範圍避免撞出「找到多個」。
    const hero = heroSection();
    expect(hero.getByText(`$${view.meta.spot.toFixed(2)}`)).toBeInTheDocument();
    expect(hero.getByText(new RegExp(
      `目標 .?\\$?${view.params.target_price.toFixed(2)} · ${view.params.target_month}`)))
      .toBeInTheDocument();
    expect(hero.getByText(`+${(view.meta.target_move * 100).toFixed(1)}%`,
                          { exact: false })).toBeInTheDocument();
  });

  it("候選身分＝跨 family 冠軍：劇本報酬與所屬 family（確切策略子類仍在" +
     "下方到期日排名表，見「候選窄列」既有測試）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const top = baselineTopCandidate(view)!;
    const hero = heroSection();
    expect(hero.getByText(`${(top.baseline_return * 100).toFixed(1)}%`))
      .toBeInTheDocument();
    expect(hero.getByText(/劇本報酬 · Vertical Spread/)).toBeInTheDocument();
  });

  it("資料時間與資料來源沒有在刪除摘要卡的過程中被弄丟", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.getByText(view.meta.source)).toBeInTheDocument();
  });

  it("最高／最低（原 `Summary` 唯一的獨有欄位）條件式顯示——它們是" +
     "Heatmap 價格軸上下限的來源（QA 修正既有裁示，沿用到新位置）",
     async () => {
    mockDetail(detail({ latest_result: {
      ...view,
      params: { ...view.params, best_price: 150.0, worst_price: 90.0 },
    } }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.getByText("最高")).toBeInTheDocument();
    expect(hero.getByText("最低")).toBeInTheDocument();
    expect(hero.getByText("$150.00")).toBeInTheDocument();
    expect(hero.getByText("$90.00")).toBeInTheDocument();
  });

  it("沒填最高／最低時那兩格整個不畫——跟劇本庫卡片 `.compact-range`" +
     "同一個既有慣例（沒填就不畫，不是顯示假的破折號）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = heroSection();
    expect(hero.queryByText("最高")).not.toBeInTheDocument();
    expect(hero.queryByText("最低")).not.toBeInTheDocument();
  });

  it("原本的『劇本設定』『劇本摘要』獨立卡片不再存在——真的刪除了，" +
     "不是把舊卡藏起來", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(screen.queryByRole("region", { name: "劇本設定" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "劇本摘要" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "基準候選" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "進場成本" })).not.toBeInTheDocument();
  });

  it("有回劇本庫的入口", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("link", { name: /劇本庫/ }))
      .toHaveAttribute("href", "#/");
  });
});

describe("詳細頁主圖（Payoff Heatmap）", () => {
  it("畫出 baseline 期第 1 名候選的 Heatmap", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(mainChart().getByRole("table")).toBeInTheDocument();
  });
});

describe("OG-10（#327）：手機版三價位階梯／進場面板（artifact「Mobile 劇本" +
         "詳細」板，桌面 OG-06／OG-07 之前一直沒有的兩塊手機內容）", () => {
  it("劇本主圖卡片內緊接著三價位階梯（最差／目標／最好），同一組冠軍候選",
     async () => {
    const ladder = [
      { label: "worst" as const, price: 90, return: -1 },
      { label: "target" as const, price: 130, return: 5.667 },
      { label: "best" as const, price: 150, return: 8.2 },
    ];
    mockDetail(detail({ latest_result: withTopCandidate({ price_ladder: ladder }) }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const priceLadder = within(screen.getByLabelText("劇本區間三價位"));
    expect(priceLadder.getByText("最差")).toBeInTheDocument();
    expect(priceLadder.getByText("目標")).toBeInTheDocument();
    expect(priceLadder.getByText("最好")).toBeInTheDocument();
    expect(priceLadder.getByText("$150.00")).toBeInTheDocument();
  });

  it("`price_ladder` 是空陣列時三價位階梯不輸出任何節點——不是空表格",
     async () => {
    mockDetail(detail({ latest_result: withTopCandidate({ price_ladder: [] }) }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(screen.queryByLabelText("劇本區間三價位")).not.toBeInTheDocument();
  });

  it("進場面板：逐腿最差成交價、淨成本，跟桌面 EntryTab 同一句格式化" +
     "（`${legSide} ${legQuantityPrefix}${strike}`）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const entryPanel = within(
      screen.getByRole("heading", { name: "進場 · 以最差成交價計算" }).closest("section")!);
    const champion = baselineTopCandidate(view)!;
    for (const leg of champion.legs) {
      expect(entryPanel.getByText(new RegExp(`^(買|賣).*${leg.strike}$`)))
        .toBeInTheDocument();
    }
    expect(entryPanel.getByText("淨成本 / 股")).toBeInTheDocument();
  });

  it("進場面板重用既有 `RiskPayoff`／`PositionSensitivity`——Max Loss／" +
     "Net Delta 這兩項既有內容都在，不是只有逐腿價格", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const entryPanel = within(
      screen.getByRole("heading", { name: "進場 · 以最差成交價計算" }).closest("section")!);
    expect(entryPanel.getByText("Max Loss")).toBeInTheDocument();
    expect(entryPanel.getByText("Net Delta")).toBeInTheDocument();
  });

  it("沒有合格候選（冠軍為 null）時，進場面板不輸出任何節點", async () => {
    const empty: AnalysisView = {
      ...view,
      results: view.results.map((r) => ({ ...r, status: "empty" as const,
                                          expiry_top10: [], expiry_counts: [] })),
    };
    mockDetail(detail({ latest_result: empty }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText("無合格候選");

    expect(screen.queryByText("進場 · 以最差成交價計算")).not.toBeInTheDocument();
  });
});

describe("追平價格區塊已移除（spec 決策 E／#103）", () => {
  it("不再渲染追平價格卡片，任何相關文案都不出現", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(screen.queryByText(/Long Call 追平價格/)).not.toBeInTheDocument();
    expect(screen.queryByText(/即勝過此 Spread/)).not.toBeInTheDocument();
    expect(screen.queryByText(/超出目標價|低於目標價/)).not.toBeInTheDocument();
    expect(screen.queryByText(/無法計算/)).not.toBeInTheDocument();
  });
});

describe("區塊順序（spec #102 決策 A／#103）", () => {
  it("OG-10（#327）起依 artifact「Mobile 劇本詳細」板重排的順序渲染；" +
     "Historical IV 未解鎖時不輸出任何內容", async () => {
    const ladder = [
      { label: "worst", price: 110, return: -1 },
      { label: "target", price: 130, return: 5.667 },
    ];
    mockDetail(detail({ latest_result: withTopCandidate({ price_ladder: ladder }) }));
    const { container } = render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    // 每張卡片自己的區塊標題（該卡裡第一個 `.section-title`），依 DOM
    // 順序——用「每張卡取第一個」而不是「全部 .section-title」，這樣
    // 才不會被分析報告內部的子標題（情境分析／風險與代價……）污染，
    // 那些是 #105 的責任範圍，不是這裡要鎖的東西。
    const titles = Array.from(container.querySelectorAll(".card"))
      .map((card) => card.querySelector(".section-title")?.textContent ?? null)
      .filter((t): t is string => t !== null);

    // SW-10（#340，Owner 真機驗收）：「劇本主圖」常駐 Heatmap 排回
    // Family tabs／到期日／排名表（`FamilyTabs` 內部，含既有候選池／
    // 分析報告）之前——OG-10（#327）當時的順序依據是已退休的
    // Obsidian Gold artifact（見 issue #327 本文與 `ScenarioDetail.tsx`
    // 檔頭說明），不是現在的 source of truth；Owner 真機驗收明文指出
    // 「第二區原本應該有最佳劇本熱力圖，目前不見」，這裡把它排回來。
    // 「進場」面板緊接在排名表之後，Historical IV（此測試未解鎖，不
    // 輸出節點）與底部兩張收合卡排在最後不變。
    expect(titles).toEqual([
      // SW-06（#335）文案去術語：「候選池」→「候選策略」、「最差成交
      // 口徑」→「以最差成交價計算」，語意不變，僅順序本身鎖定的既有
      // 斷言跟著新文案更新。
      "劇本主圖", "到期日", "候選策略", "📄 分析報告",
      "進場 · 以最差成交價計算",
      "Spread 淨成本走勢", "原始資料（當次快照）",
    ]);

    // IV History 插槽本身不輸出任何 DOM 節點——不是一張空卡片，直接就
    // 不存在於 DOM 裡。卡片總數固定為上面 7 張加上 SW-06（#335）新增的
    // Hero 白卡（無 section-title，改用 aria-label）——SW-10（#340，
    // Owner 真機驗收）起原本另外兩張無 title 的卡（`ScenarioContext`
    // 劇本設定卡／`Summary` 摘要卡）已整段刪除，總數因此從 10 降到 8，
    // 插槽若渲染出任何東西（哪怕只是空卡），這裡就會多一張。
    expect(container.querySelectorAll(".card")).toHaveLength(8);
    expect(screen.queryByText(/Historical IV|IV Position/)).not.toBeInTheDocument();
  });
});

describe("詳細頁的空狀態", () => {
  it("還沒分析過就說還沒分析，不畫一張空圖", async () => {
    mockDetail(detail({ latest_result: null, latest_analyzed_at: null,
                        best_return: null }));
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText(/尚未分析/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();   // 整頁都沒有
  });

  it("baseline 期沒有合格候選時明說，不拿別期的冒充", async () => {
    mockDetail(detail({
      latest_result: { ...view, baseline_expiry: "2099-01-01" },
    }));
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByText("無合格候選")).toBeInTheDocument();
    // 主圖那一區沒有表；到期日結構仍照常列出各期候選
    expect(mainChart().queryByRole("table")).not.toBeInTheDocument();
  });

  it("載不動時說明原因，不是白畫面", async () => {
    mockDetail({ detail: "劇本不存在：s1" }, false, 404);
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("劇本不存在");
  });
});

describe("刷新完成後詳細頁跟著更新（V5／#53 檢視回饋）", () => {
  it("直接開詳細頁網址時，不會永遠停在刷新前的那份快照", async () => {
    // 開站的刷新輪跑在背景，詳細頁沒有功能列也沒有刷新入口——不跟著
    // 重取的話，直接開 `#/s/{id}` 的人看到的永遠是刷新前的數字。
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, status: 200,
      json: async () => (call++ === 0
        ? detail({ latest_result: null, latest_analyzed_at: null })
        : detail()),
    })));

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    expect(await screen.findByText(/尚未分析/)).toBeInTheDocument();

    // 劇本庫那一列的資料時間變了＝這個劇本剛剛被刷新過
    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);

    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();
    expect(mainChart().getByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/尚未分析/)).not.toBeInTheDocument();
  });

  it("T03（#187）：同一輪內反覆進出詳細頁，同一份資料不重新下載", async () => {
    // `mockDetail` 對任何 URL 都回同一份 body（含 IvHistory 自己的
    // settings 請求）——這裡只數打到 scenario detail 端點本身的次數。
    const spy = mockDetail(detail());
    const detailCalls = () =>
      (spy.mock.calls as unknown as [string][])
        .filter(([url]) => url.includes("/api/scenarios/s1")).length;

    const { unmount } = render(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);
    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();
    expect(detailCalls()).toBe(1);

    unmount();
    render(<ScenarioDetail id="s1" refreshedAt="2026-08-04T09:30:00+00:00" />);
    expect(await screen.findByText(/劇本主圖/)).toBeInTheDocument();

    // 離開又進來，analyzedAt 沒變——快取命中，底層請求次數不變。
    expect(detailCalls()).toBe(1);
  });
});

describe("詳細頁刷新入口（#70）", () => {
  it("有明確的刷新按鈕，位置與劇本庫一致（標題列右側膠囊鈕）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    expect(await screen.findByRole("button", { name: "重新整理" }))
      .toBeInTheDocument();
  });

  it("點擊呼叫傳入的 onRefresh，且只帶這個劇本的身分（呼叫端決定範圍）", async () => {
    mockDetail(detail());
    const onRefresh = vi.fn();
    render(<ScenarioDetail id="s1" onRefresh={onRefresh} />);

    await userEvent.click(await screen.findByRole("button", { name: "重新整理" }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("刷新進行中按鈕停用並顯示忙碌文字，不能重複觸發", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" busy />);

    expect(await screen.findByRole("button", { name: "刷新中……" }))
      .toBeDisabled();
  });

  it("這個劇本正在被刷新（T08／#196 P1）：明確提示，搶在其他內容之前，" +
     "不能讓桌面右側常駐面板的舊內容看起來像已經更新完成", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" updating />);

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(/排隊中或進行中/);
    expect(notice).toHaveTextContent(/上一輪的舊資料/);
  });

  it("沒有更新中時不顯示這個提示", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(screen.queryByText(/排隊中或進行中/)).not.toBeInTheDocument();
  });

  it("更新中又剛好帶著上一次的失敗紀錄時，先顯示更新中提示——這次嘗試還" +
     "沒有結論，失敗提示要等它解決後才有意義", async () => {
    mockDetail(detail());
    render(
      <ScenarioDetail
        id="s1"
        updating
        failure={{ stage: "fetch", message: "抓不到報價" }}
      />,
    );

    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("失敗時顯示分層指引，重試按鈕也走同一個 onRefresh", async () => {
    mockDetail(detail());
    const onRefresh = vi.fn();
    render(
      <ScenarioDetail
        id="s1"
        onRefresh={onRefresh}
        failure={{ stage: "fetch", message: "抓不到 XYZ 的報價：來源無回應" }}
      />,
    );

    expect(await screen.findByText(/抓不到報價/)).toBeInTheDocument();
    expect(screen.getByText(/來源無回應/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "重試" }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("沒有失敗紀錄時不顯示失敗提示", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);

    await screen.findByText(/劇本主圖/);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("已過期的劇本：刷新按鈕停用並顯示與劇本庫一致的文案（#68 既有語彙）", async () => {
    mockDetail(detail({ expired: true }));
    render(<ScenarioDetail id="s1" />);

    const button = await screen.findByRole("button", { name: "已過期，不再刷新" });
    expect(button).toBeDisabled();
  });

  it("已過期的劇本即使帶著舊的失敗紀錄，也不顯示重試——" +
     "兩種狀態同時出現會讓使用者搞不清楚現在是哪一種（比照 ScenarioList）", async () => {
    mockDetail(detail({ expired: true }));
    render(
      <ScenarioDetail
        id="s1"
        failure={{ stage: "fetch", message: "抓不到報價" }}
      />,
    );

    await screen.findByRole("button", { name: "已過期，不再刷新" });
    expect(screen.queryByText(/抓不到報價/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重試" })).not.toBeInTheDocument();
  });

  it("限流失敗（SCALE-05／#260）：結構化倒數取代 message 原文、視窗內" +
     "重試鈕 disabled", async () => {
    // 刻意不用假時鐘——`findByText` 的內部輪詢依賴真實計時器，跟
    // `vi.useFakeTimers()` 混用會讓它永遠等不到（`setInterval` 被
    // 攔截、fake timers 沒有手動推進就不會觸發），進而拖垮整個測試檔
    // 案的其餘測試。改用相對真實「現在」的 `blocked_until`，容忍測試
    // 執行耗時造成的一兩秒誤差（比照既有 `test_parse_retry_after_
    // http_date` 的容忍窗手法）。
    mockDetail(detail());
    render(
      <ScenarioDetail
        id="s1"
        failure={{
          stage: "rate_limited", message: "XYZ 的報價來源目前受限流",
          rateLimit: {
            blocked_until: new Date(Date.now() + 60_000).toISOString(),
            retry_after_seconds: 60, remaining_seconds: 60,
            last_success_at: null, incident: false,
          },
        }}
      />,
    );

    expect(await screen.findByText(/Cboe 資料來源目前限流中/))
      .toBeInTheDocument();
    expect(screen.getByText(/還要等約 (5[5-9]|60) 秒才能重試/))
      .toBeInTheDocument();
    expect(screen.queryByText(/XYZ 的報價來源目前受限流/))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重試" })).toBeDisabled();
  });
});

describe("進階區隨新分析失效，不混用新舊 cache（#69）", () => {
  const HISTORY = { entries: [
    { analyzed_at: "2026-08-01T00:00:00+00:00", spot: 100.0, cost: 5.0,
     baseline_return: 0.3, rank_in_expiry: 1 },
  ] };
  const RAW = {
    meta: { symbol: "XYZ", spot: 100.0, fetched_at: "2026-08-04T09:00:00+00:00",
           source: "cboe", contract_count: 1 },
    contracts: [{ contract_symbol: "XYZ261016C00110000", option_type: "call",
                 strike: 110.0, expiry: "2026-10-16", bid: 3.0, ask: 3.25,
                 last: 3.1, volume: 10, open_interest: 20, implied_volatility: 0.3 }],
  };

  /** 精準控制第二次 `getScenario`何時回來，不靠 race 猜時機。 */
  function mockDetailSequence(first: unknown, second: unknown) {
    let scenarioCalls = 0;
    let resolveSecond: (() => void) | null = null;
    const historyCalls: string[] = [];
    const rawDataCalls: string[] = [];
    const spy = vi.fn(async (url: string) => {
      if (url.startsWith("/api/scenarios/s1/history")) {
        historyCalls.push(url);
        return { ok: true, status: 200, json: async () => HISTORY };
      }
      if (url.startsWith("/api/scenarios/s1/raw-data")) {
        rawDataCalls.push(url);
        return { ok: true, status: 200, json: async () => RAW };
      }
      if (url === "/api/scenarios/s1") {
        scenarioCalls += 1;
        if (scenarioCalls === 1) {
          return { ok: true, status: 200, json: async () => first };
        }
        return new Promise((resolve) => {
          resolveSecond = () =>
            resolve({ ok: true, status: 200, json: async () => second });
        });
      }
      throw new Error(`測試沒有為 ${url} 準備回應`);
    });
    vi.stubGlobal("fetch", spy);
    return { historyCalls, rawDataCalls, resolveSecond: () => resolveSecond!() };
  }

  it("刷新後，先前展開過的兩區都收合，不再顯示上一輪的內容", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);

    // 新一輪還沒回來之前，既有規則「刷新造成的重取不清空」仍成立——
    // 先前展開的內容不該憑空消失。
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.getByText("XYZ261016C00110000")).toBeInTheDocument();

    resolveSecond();

    // 新一輪真的落地之後，兩區才收合、內部狀態一起重置。
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.queryByText("XYZ261016C00110000")).not.toBeInTheDocument();
  });

  it("收合後再展開，是真的重新取得，不是沿用上一輪的舊資料", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { historyCalls, rawDataCalls, resolveSecond } =
      mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");
    expect(historyCalls).toHaveLength(1);
    expect(rawDataCalls).toHaveLength(1);

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    await screen.findByText("XYZ261016C00110000");

    // 各自又多打了一次——不是沿用元件裡「已經抓過」的舊旗標。
    expect(historyCalls).toHaveLength(2);
    expect(rawDataCalls).toHaveLength(2);
  });

  it("原始資料的 CSV 下載連結跟著換一個網址（#69：不讓瀏覽器快取原樣吐回舊檔）", async () => {
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({ latest_analyzed_at: "2026-08-04T10:00:00+00:00" });
    const { resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    const before = (await screen.findByText("下載 CSV") as HTMLAnchorElement)
      .getAttribute("href");

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByText("下載 CSV")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("原始資料（當次快照）"));
    const after = (await screen.findByText("下載 CSV") as HTMLAnchorElement)
      .getAttribute("href");

    expect(after).not.toBe(before);
  });

  it("主圖候選因新分析換掉時，歷史走勢跟著換成新候選的序列（AC2）", async () => {
    const originalKey = baselineTopCandidate(view)!.candidate_key;
    const first = detail({ latest_analyzed_at: "2026-08-04T09:00:00+00:00" });
    const second = detail({
      latest_analyzed_at: "2026-08-04T10:00:00+00:00",
      latest_result: withTopCandidate({ candidate_key: "different-candidate" }),
    });
    const { historyCalls, resolveSecond } = mockDetailSequence(first, second);

    const { rerender } = render(<ScenarioDetail id="s1" refreshedAt={null} />);
    await screen.findByText(/劇本主圖/);
    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");
    expect(historyCalls[0]).toContain(
      `candidate_key=${encodeURIComponent(originalKey)}`);

    rerender(<ScenarioDetail id="s1" refreshedAt="2026-08-04T10:00:00+00:00" />);
    resolveSecond();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());

    await userEvent.click(screen.getByText("Spread 淨成本走勢"));
    await screen.findByRole("img");

    // 換一輪之後再展開，帶的是新候選自己的身份鍵，不是沿用第一輪那個。
    expect(historyCalls).toHaveLength(2);
    expect(historyCalls[1]).toContain(
      `candidate_key=${encodeURIComponent("different-candidate")}`);
  });
});

describe("基準候選的候選池警語（V6／#54 檢視回饋；SW-10／#340 起原本" +
        "搬進去的摘要卡整段刪除，改由 `ExpiryStructure` 自己那句同樣" +
        "的提示覆蓋——baseline 到期日本來就是預設選中的 chip，回到它" +
        "身上警語自然還在，不需要另外維護一份固定黏著 baseline 的副本）",
        () => {
  function expirySection() {
    return within(screen.getByRole("heading", { name: "到期日" })
      .closest("section") as HTMLElement);
  }

  it("baseline 到期日顯示候選池過少的警語，切走再切回來還在", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    expect(expirySection().getByText(/僅 1 組候選/)).toBeInTheDocument();

    const other = view.results[0].expiry_top10!
      .find((g) => g.expiry !== view.baseline_expiry)!;
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(other.expiry) }));
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(view.baseline_expiry!) }));

    expect(expirySection().getByText(/僅 1 組候選/)).toBeInTheDocument();
  });
});

// ---------- T11（#229，Initial V2）：多 family 並存 ----------

describe("多 family 並存（T11／#229）", () => {
  /** 手造一份包含兩個 family 的 view——真實契約樣本恆為單一策略，測不出
   *  「頭條數字＝跨 family 冠軍」與「results[0] 不保證是冠軍」這兩件事。
   *  刻意讓報酬較高的候選（bull-call-spread）不是 `results[0]`，逼出
   *  T11 真正要修的那個坑：舊版 `primaryResult(view) = results[0]` 在
   *  這個排列下會挑到錯的策略。 */
  function multiFamilyDetail() {
    const params = {
      target_price: 130, target_month: "2026-09", strategy: "long-call",
      best_price: null, worst_price: null, rate: 0.04, rate_note: "",
      rate_curve_used: false, rate_curve_date: null, rate_curve_stale: false,
      rate_explicit: false, q_by_symbol: null, q_source: null, q_as_of: null,
      q_stale: false, q_note: "", iv_shifts: [-0.2, 0, 0.2],
      delta_bands: [0.35, 0.65] as [number, number], min_return: 0,
    };
    const leg = (strike: number, side: "buy" | "sell" = "buy"): Leg => ({
      strike, option_type: "call", expiry: "2026-09-18", ask: 1, bid: 1,
      iv: 0.2, volume: 1, open_interest: 1, side, quantity: 1,
    });
    // 冠軍（bull-call-spread）給兩隻腿——標題會是「買 100 / 賣 105」，
    // 跟 long-call 那組候選的「買 100」（單腿）文字上不會撞在一起，
    // 兩者才測得出「分頁切換不影響頭條」而不是巧合湊出同一句文字。
    const candidate = (
      key: string, strategy: string, ret: number,
      legs: CandidateLegs = [leg(100)],
    ) => ({
      candidate_key: key, strategy, baseline_return: ret, natural_cost: 1,
      mid_cost: 1, breakeven: 100, breakeven_points: [100], profit_region: null,
      days_to_expiry: 30, max_profit: null, max_loss_per_contract: 100,
      net_delta: 0.5, effective_leverage: 1, theta_day_rate: 0,
      rate_used: 0.04, rate_tenor_years: 0.1, vega_per_pt: 0,
      scenario_vector: { entries: [], worst_code: "flat", worst_return: 0 },
      completion_curve: [], completion_threshold: null, retention: 0,
      l2: 0, l3: 0, cons: [], guidance_warnings: [], catchup_price: null,
      wide_spread_warning: false, monotonicity_warning: false,
      legs, matrix: { prices: [], dates: [], cells: [] },
      comparator: null,
    });
    const resultOf = (strategy: string, status: "ok" | "skipped_direction",
                      keys: string[]) => ({
      strategy, status, message: status === "ok" ? "" : `${strategy} 跳過`,
      n_qualified: keys.length, filter_report: null, filter_stages: [],
      quality_flags: [], pair_report: null,
      expiry_counts: keys.length ? [["2026-09-18", keys.length] as [string, number]] : [],
      expiry_top10: keys.length
        ? [{ expiry: "2026-09-18", candidate_keys: keys }] : [],
      disclaimer_text: "",
    });
    // `results[0]` 是被方向閘門擋掉的 bear-put-spread；真正的冠軍
    // （bull-call-spread，報酬 0.9）在陣列後面——這正是既有 T06 家族
    // 展開會產生、T11 之前的舊 `primaryResult()` 邏輯會挑錯的排列。
    const multiView: AnalysisView = {
      meta: { symbol: "XYZ", spot: 100, fetched_at: "2026-08-04T09:30:00+00:00",
              source: "cboe", target_move: 0.3 },
      params,
      baseline_expiry: "2026-09-18",
      results: [
        resultOf("bear-put-spread", "skipped_direction", []),
        resultOf("bull-call-spread", "ok", ["champ"]),
        resultOf("long-call", "ok", ["lc"]),
      ],
      candidate_pool: {
        champ: candidate("champ", "bull-call-spread", 0.9,
                         [leg(100, "buy"), leg(105, "sell")]),
        lc: candidate("lc", "long-call", 0.4),
      },
      family_eligibility: {
        "single-leg": { family: "single-leg", eligible: true, reason: null },
        "vertical-spread": { family: "vertical-spread", eligible: true, reason: null },
        "butterfly": { family: "butterfly", eligible: false,
                       reason: "這個策略家族目前還沒有任何已啟用的具體結構。" },
      },
    };
    return detail({
      strategies: ["single-leg", "vertical-spread"],
      family_eligibility: multiView.family_eligibility,
      latest_result: multiView,
    });
  }

  it("頭條數字＝跨 family 冠軍，不是 results[0]（真實回歸：舊邏輯在這個"
     + "排列下會挑到 skipped_direction 那筆、顯示無合格候選）", async () => {
    mockDetail(multiFamilyDetail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    // SW-10（#340）起頭條 Hero 卡顯示的是冠軍所屬的 family（跟已刪除的
    // `Summary` 摘要卡不同——那張卡顯示的是確切策略子類「Bull Call
    // Spread」，這裡改用 family 層級的「Vertical Spread」，確切子類仍
    // 在下面到期日排名表的 #1 名那一列，見下一條斷言）。
    const hero = heroSection();
    expect(hero.getByText(/劇本報酬 · Vertical Spread/)).toBeInTheDocument();
    expect(hero.getByText("90.0%")).toBeInTheDocument();
    expect(screen.queryByText("無合格候選")).not.toBeInTheDocument();

    const expiryStructure = screen.getByRole("heading", { name: "到期日" })
      .closest("section") as HTMLElement;
    expect(within(expiryStructure).getByText("Bull Call Spread")).toBeInTheDocument();
  });

  it("分頁列出兩個啟用的 family，預設打開冠軍所屬的 Vertical Spread", async () => {
    mockDetail(multiFamilyDetail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const tabs = screen.getByRole("group", { name: "策略家族" });
    expect(within(tabs).getAllByRole("button")).toHaveLength(2);
    expect(within(tabs).getByRole("button", { name: "Vertical Spread" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("切到 Call / Put 分頁只換排名內容，頭條數字仍是冠軍不變", async () => {
    mockDetail(multiFamilyDetail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    await userEvent.click(screen.getByRole("button", { name: "Call / Put" }));

    // 分頁內容換成 long-call 自己的候選——縮小到「到期日」排名表本身
    // （OG-10／#327 起頁面上新增的進場面板固定顯示冠軍，逐腿列也會印出
    // 「買 100」這個買腿 strike 標籤，含 regex 或不縮小範圍的
    // `screen.getByText` 會連帶命中那裡，變成「找到多個」的假失敗，
    // 這裡改成 `within` 只找排名表自己的候選列，不是同一句文字剛好
    // 撞名）。
    const expiryStructure = screen.getByRole("heading", { name: "到期日" })
      .closest("section") as HTMLElement;
    expect(within(expiryStructure).getByText("買 100")).toBeInTheDocument();
    // 頭條（Hero 卡）依然是 Bull Call Spread 所屬 family 的冠軍報酬，
    // 不隨分頁切換而改變。
    const hero = heroSection();
    expect(hero.getByText(/劇本報酬 · Vertical Spread/)).toBeInTheDocument();
    expect(hero.getByText("90.0%")).toBeInTheDocument();
  });
});

describe("OG-06（#321）：桌面詳細頁身分列——方向 tag／編輯入口／Logo 404", () => {
  function desktopMultiFamilyDetail() {
    const champ = candidate("champ", "bull-call-spread", 0.9);
    const lc = candidate("lc", "long-call", 0.4);
    const v = buildView(
      [result("bull-call-spread", "ok", { "2026-09-18": ["champ"] }),
       result("long-call", "ok", { "2026-09-18": ["lc"] })],
      { champ, lc },
      { direction: "bullish" },
    );
    return detail({ strategies: ["single-leg", "vertical-spread"], latest_result: v });
  }

  /** 身分列本身——桌面新增的方向 tag／編輯鈕只加在這裡。SW-10（#340）
   *  起唯一顯示「看漲」這個字的地方已經只剩這裡（`ScenarioContext`／
   *  `Summary` 已整段刪除），仍縮小到這個容器查詢，純粹是保守，不是
   *  真的還有第二個位置會撞名。 */
  function header(container: HTMLElement) {
    return container.querySelector(".toolbar") as HTMLElement;
  }

  it("桌面：身分列顯示方向 tag，點編輯入口呼叫 onEdit，切換 family 分頁" +
     "不影響頭條（跟頭條固定顯示冠軍是同一條既有原則，本票延伸到桌面" +
     "新的三欄外殼）", async () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    const onEdit = vi.fn();
    mockDetail(desktopMultiFamilyDetail());
    const { container } = render(<ScenarioDetail id="s1" onEdit={onEdit} />);
    await screen.findByText(/劇本主圖/);

    expect(within(header(container)).getByText("看漲")).toBeInTheDocument();
    // `/code-review` Spec 軸跟進（OG-06）＋ SW-05（#337）收成跟手機版
    // `MobileHero` 同一組四格：身分列票面明文要求的現價／目標價（含所需
    // 漲跌幅）／目標年月／資料時間／資料來源都要在這一列，不能只留在
    // 下方的 `Summary` 卡；SW-05 起額外要求冠軍報酬大字＋family 副標。
    // 假體預設值（`family.fixtures.ts::view()`）：spot 100／target_price
    // 110／target_move 0／target_month "2026-09"／source "cboe"／
    // days_to_anchor 653（`scenario_row_sample.json`）。
    expect(within(header(container)).getByText(/目標 \$110\.00 · 2026-09/))
      .toBeInTheDocument();
    expect(within(header(container)).getByText("90.0%")).toBeInTheDocument();
    expect(within(header(container)).getByText(/劇本報酬 · Vertical Spread/))
      .toBeInTheDocument();
    expect(within(header(container)).getByText(/現價 \$100\.00/)).toBeInTheDocument();
    expect(within(header(container)).getByText(/還需 \+0\.0%/)).toBeInTheDocument();
    expect(within(header(container)).getByText("距目標 653 天")).toBeInTheDocument();
    expect(within(header(container)).getByText(/cboe/)).toBeInTheDocument();

    await userEvent.click(within(header(container))
      .getByRole("button", { name: "編輯" }));
    expect(onEdit).toHaveBeenCalledTimes(1);

    const tabs = screen.getByRole("group", { name: "策略家族" });
    await userEvent.click(within(tabs).getByRole("button", { name: "Call / Put" }));

    expect(within(header(container)).getByText(/劇本報酬 · Vertical Spread/))
      .toBeInTheDocument();
    expect(within(header(container)).getByText("90.0%")).toBeInTheDocument();
  });

  it("桌面：Logo.dev 對假造代號回 404 後，身分列的 <img> 整個從 DOM 消失" +
     "（UI-IMPL-002／#092 既有契約，延伸到身分列這個新位置）", async () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    mockDetail(desktopMultiFamilyDetail());
    const { container } = render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const img = header(container).querySelector("img")!;
    expect(img).not.toBeNull();
    fireEvent.error(img);

    expect(header(container).querySelector("img")).toBeNull();
  });

  it("手機版（預設 matchMedia）：身分列不出現方向 tag 與編輯入口——這兩項" +
     "是桌面限定的加法，不是手機版本來就有的東西（手機版零改動）。" +
     "SW-06（#335）起手機版連 `.toolbar` 本身都不存在——換成獨立的" +
     "60px `.detail-bar`，兩者結構上互斥，不是同一個 header 藏了不同" +
     "內容", async () => {
    const onEdit = vi.fn();
    mockDetail(desktopMultiFamilyDetail());
    const { container } = render(<ScenarioDetail id="s1" onEdit={onEdit} />);
    await screen.findByText(/劇本主圖/);

    expect(container.querySelector(".toolbar")).not.toBeInTheDocument();
    const mobileBar = within(container.querySelector(".detail-bar") as HTMLElement);
    expect(mobileBar.queryByText("看漲")).not.toBeInTheDocument();
    expect(mobileBar.queryByRole("button", { name: "編輯" })).not.toBeInTheDocument();
  });
});

describe("SW-06（#335，Seed Warm）：手機詳細頁 60px header／Hero 白卡", () => {
  it("60px header：回劇本庫、代號、刷新——桌面 `.toolbar` 完全不掛載", async () => {
    mockDetail(detail());
    const { container } = render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const bar = container.querySelector(".detail-bar") as HTMLElement;
    expect(bar).toBeInTheDocument();
    expect(container.querySelector(".toolbar")).not.toBeInTheDocument();
    expect(within(bar).getByRole("link", { name: /劇本庫/ }))
      .toHaveAttribute("href", "#/");
    expect(within(bar).getByText("XYZ")).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "重新整理" })).toBeInTheDocument();
  });

  it("Hero 白卡：logo＋代號＋方向 pill、冠軍報酬與 family 副標、" +
     "目標價＋目標月、四格關鍵指標（現價／還需／距目標／來源＋時間）", async () => {
    mockDetail(detail());
    render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const hero = within(screen.getByRole("region", { name: "劇本頭條" }));
    const top = baselineTopCandidate(view)!;
    expect(hero.getByText(view.meta.symbol)).toBeInTheDocument();
    expect(hero.getByText("看漲")).toBeInTheDocument();
    expect(hero.getByText(`${(top.baseline_return * 100).toFixed(1)}%`))
      .toBeInTheDocument();
    expect(hero.getByText(/劇本報酬 · Vertical Spread/)).toBeInTheDocument();
    expect(hero.getByText(new RegExp(
      `目標 \\$${view.params.target_price.toFixed(2)} · ${view.params.target_month}`,
    ))).toBeInTheDocument();
    expect(hero.getByText("現價")).toBeInTheDocument();
    expect(hero.getByText("還需")).toBeInTheDocument();
    expect(hero.getByText("距目標")).toBeInTheDocument();
    // 契約樣本 `scenario_row_sample.json`：days_to_anchor = 653
    expect(hero.getByText("653 天")).toBeInTheDocument();
    expect(hero.getByText("來源")).toBeInTheDocument();
    expect(hero.getByText(view.meta.source)).toBeInTheDocument();
  });

  it("沒有合格候選（冠軍為 null）時，Hero 白卡不輸出任何節點", async () => {
    const empty: AnalysisView = {
      ...view,
      results: view.results.map((r) => ({ ...r, status: "empty" as const,
                                          expiry_top10: [], expiry_counts: [] })),
    };
    mockDetail(detail({ latest_result: empty }));
    render(<ScenarioDetail id="s1" />);
    await screen.findByText("無合格候選");

    expect(screen.queryByRole("region", { name: "劇本頭條" })).not.toBeInTheDocument();
  });

  it("文案去術語：手機詳細頁全頁文字不含開發者詞彙" +
     "（SW-09／#339 收斂成共用清單 BANNED_JARGON，取代原本各票自帶的" +
     "小清單）", async () => {
    mockDetail(detail({ strategies: ["single-leg", "vertical-spread", "butterfly"] }));
    const { container } = render(<ScenarioDetail id="s1" />);
    await screen.findByText(/劇本主圖/);

    const text = container.textContent ?? "";
    for (const banned of BANNED_JARGON) {
      expect(text).not.toContain(banned);
    }
  });
});
