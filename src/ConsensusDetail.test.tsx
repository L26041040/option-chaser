/**
 * LIVE-T2（#399）：個股共識詳細資料。回應直接載入 `contracts/` 的後端樣本
 * （真實 NVDA 樣本、評估日 2026-11-21，與後端測試同一份），只在測試在意的
 * 情境覆寫欄位。
 *
 * 守的事：按下才打詳細資料端點（只打一次、收起再開不重打）；顯示每位券商
 * 的原始目標價、發布日、分割換算後的值；平均／標準差／分析師分歧率／分歧度
 * 歷史排序（PR，V2-03／#405）與每月序列、合格點數；不符合條件時哪一道門檻
 * 沒過、資料不足的原因；明細尚未就緒、錯誤、來源未設定都照實說。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import detailSample from "../contracts/opportunity_detail_sample.json";
import ConsensusDetailToggle from "./ConsensusDetail";
import type { OpportunityConsensusDetail } from "./api";

const DETAIL = detailSample as unknown as OpportunityConsensusDetail;

function res(status: number, body: unknown): Response {
  return { ok: status < 400, status, headers: new Headers(),
           json: async () => body } as Response;
}

function mockDetail(status = 200, body: unknown = DETAIL) {
  const spy = vi.fn(async (_url: string) => res(status, body));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function open(symbol = "NVDA") {
  const user = userEvent.setup();
  render(<ConsensusDetailToggle symbol={symbol} />);
  const button = screen.getByRole("button", { name: `${symbol} 詳細資料` });
  expect(button).toHaveAttribute("aria-expanded", "false");
  await user.click(button);
  expect(button).toHaveAttribute("aria-expanded", "true");
  const panel = await screen.findByRole("region", { name: `${symbol} 共識明細` });
  return { user, button, panel };
}

describe("ConsensusDetail：開啟與讀取", () => {
  it("收合時不打任何端點；打開才讀這一檔的詳細資料，收起再開不重打", async () => {
    const spy = mockDetail();
    const { user, button } = await open();
    await screen.findByText("Bernstein");
    expect(spy).toHaveBeenCalledTimes(1);
    expect(String(spy.mock.calls[0][0])).toBe("/api/opportunity/consensus-detail/NVDA");
    await user.click(button);
    expect(screen.queryByRole("region", { name: "NVDA 共識明細" })).not.toBeInTheDocument();
    await user.click(button);
    await screen.findByText("Bernstein");
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("ConsensusDetail：共識怎麼算出來的", () => {
  it("平均、標準差、分析師分歧率、分歧度歷史排序（PR）、合格歷史點數、有效券商數", async () => {
    mockDetail();
    const { panel } = await open();
    const facts = await within(panel).findByRole("list", { name: "共識數值" });
    expect(facts).toHaveTextContent("平均目標價$252.86");
    expect(facts).toHaveTextContent("標準差$71.84");
    expect(facts).toHaveTextContent("分析師分歧率（標準差 ÷ 平均）28.4%");
    // 原百分位 96.7% → PR 3.3 → 向下取整 PR3（前 97%）。
    expect(facts).toHaveTextContent("分歧度歷史排序PR3（前 97%）");
    expect(facts).toHaveTextContent("合格歷史點60 / 60 個月");
    expect(facts).toHaveTextContent("有效券商數35");
    expect(facts).toHaveTextContent("資料日期2026-11-21");
    // 歷史比較的口徑：60 個月、月底最後一個交易日、至少 24 個有效月份。
    expect(panel).toHaveTextContent(/過去 60 個月.*最後一個交易日.*24 個有效月份/);
  });

  it("目前股價帶報價日期、目標漲跌幅（V2-05／#407）", async () => {
    mockDetail();
    const { panel } = await open();
    const facts = await within(panel).findByRole("list", { name: "共識數值" });
    // 真實 NVDA 樣本：股價 125.53（2026-11-20 收盤）、平均目標價 252.857… → +101.4%
    expect(facts).toHaveTextContent("目前股價$125.53（2026-11-20 收盤）");
    expect(facts).toHaveTextContent("目標漲跌幅+101.4%");
  });

  it("目標漲跌幅不能算時顯示 — 與原因", async () => {
    mockDetail(200, { ...DETAIL, item: { ...DETAIL.item!, target_upside_pct: null,
                                          target_upside_reason: "price_stale" } });
    const { panel } = await open();
    const facts = await within(panel).findByRole("list", { name: "共識數值" });
    expect(facts).toHaveTextContent("目前股價$125.53（2026-11-20 收盤）");
    expect(facts).toHaveTextContent("目標漲跌幅— · 股價過舊（超過 3 個交易日）");
  });

  it("不符合條件：寫出哪一道門檻沒過（以 PR 與分歧率上限說明）", async () => {
    mockDetail();
    const { panel } = await open();
    const why = await within(panel).findByRole("list", { name: "不符合條件的原因" });
    expect(within(why).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "分歧度歷史排序 PR3（前 97%），未達門檻 PR ≥ 80",
      "分析師分歧率 28.4%，高於上限 10%",
    ]);
  });

  it("每位券商一列：券商、目標價、發布日；同券商只列最新一筆", async () => {
    mockDetail();
    const { panel } = await open();
    const list = await within(panel).findByRole("list", { name: "有效目標價（35 位）" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(35);
    const bernstein = within(list).getByRole("listitem", { name: "Bernstein" });
    expect(bernstein).toHaveTextContent("$200.00");
    expect(bernstein).toHaveTextContent("2026-11-12");
    expect(bernstein).toHaveTextContent("前值 $400.00");
    expect(within(list).getAllByRole("listitem", { name: "Morgan Stanley" })).toHaveLength(1);
  });

  it("分割換算過的目標價同時顯示原始值與換算後的值", async () => {
    const effective = DETAIL.effective.map((e) => e.firm === "Bernstein"
      ? { ...e, target_price: 800, adjusted_price: 200 } : e);
    mockDetail(200, { ...DETAIL, effective });
    const { panel } = await open();
    const row = await within(panel).findByRole("listitem", { name: "Bernstein" });
    expect(row).toHaveTextContent("$800.00");
    expect(row).toHaveTextContent("分割換算後 $200.00");
    const other = within(panel).getByRole("listitem", { name: "Morgan Stanley" });
    expect(other).not.toHaveTextContent("分割換算後");
  });

  it("每月序列由新到舊；不合格的月份寫出原因", async () => {
    const series = DETAIL.series.map((p, i) => i === DETAIL.series.length - 1
      ? { ...p, qualified: false, reason: "split_unresolved" } : p);
    mockDetail(200, { ...DETAIL, series, qualified_points: 59 });
    const { panel } = await open();
    const months = await within(panel).findByRole("list", { name: "每月分析師分歧率" });
    const items = within(months).getAllByRole("listitem");
    expect(items).toHaveLength(60);
    expect(items[0]).toHaveTextContent("2026-10-30");
    expect(items[0]).toHaveTextContent("不計入：股票分割無法判定");
    expect(items[1]).toHaveTextContent("2026-09-30");
    expect(items[1]).toHaveTextContent(/\d+ 位/);
    expect(items[1]).toHaveTextContent(/分歧率 \d+\.\d%/);
    expect(within(panel).getByText("每月分析師分歧率（合格 59 / 60 個月）")).toBeInTheDocument();
  });
});

describe("ConsensusDetail：資料不足與異常", () => {
  it("資料不足：寫出具體原因，並說明無法判斷是否符合條件", async () => {
    const item = { ...DETAIL.item!, status: "insufficient_analysts" as const,
                   reasons: ["insufficient_analysts: 有效券商數 1 < N_min 5",
                             "stale: 近 90 天更新比例 0.0000 < 0.5"],
                   gate: { first: false, second: false, selected: false, reasons: [] } };
    mockDetail(200, { ...DETAIL, item });
    const { panel } = await open();
    const why = await within(panel).findByRole("list", { name: "資料不足的原因" });
    expect(within(panel).getByText(/分析師人數不足/)).toBeInTheDocument();
    expect(why).toHaveTextContent("有效券商數 1 < N_min 5");
    expect(why).toHaveTextContent("近 90 天更新比例 0.0000 < 0.5");
    expect(panel).toHaveTextContent("資料不足，無法判斷是否符合條件");
  });

  it("明細尚未就緒：照實說，摘要數字照常", async () => {
    mockDetail(200, { ...DETAIL, effective: [], series: [], qualified_points: 0,
                      detail_available: false });
    const { panel } = await open();
    expect(await within(panel).findByText(/明細尚未產生/)).toBeInTheDocument();
    expect(within(panel).getByRole("list", { name: "共識數值" }))
      .toHaveTextContent("平均目標價$252.86");
  });

  it("後端錯誤：顯示後端訊息", async () => {
    mockDetail(403, { detail: "機會搜尋目前只開放 Super User／Super Admin" });
    const { panel } = await open();
    expect(await within(panel).findByRole("alert"))
      .toHaveTextContent("機會搜尋目前只開放 Super User／Super Admin");
  });

  it("來源未設定：顯示後端訊息", async () => {
    mockDetail(200, { ...DETAIL, item: null, effective: [], series: [],
                      qualified_points: 0, detail_available: false,
                      source: { configured: false, name: null, is_fixture: false },
                      message: "尚未設定分析師資料來源" });
    const { panel } = await open();
    expect(await within(panel).findByText("尚未設定分析師資料來源")).toBeInTheDocument();
  });
});
