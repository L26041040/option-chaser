/**
 * LIVE-T2（#399）：個股共識詳細資料。回應直接載入 `contracts/` 的後端樣本
 * （真實 NVDA 樣本、評估日 2026-11-21，與後端測試同一份），只在測試在意的
 * 情境覆寫欄位。
 *
 * 守的事：按下才打詳細資料端點（只打一次、收起再開不重打）；顯示每位券商
 * 的原始目標價、發布日、分割換算後的值；平均／標準差／D／百分位與每月序列、
 * 合格點數；資料不足的原因；明細尚未就緒、錯誤、來源未設定都照實說。
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
    expect(String(spy.mock.calls[0][0])).toBe("/api/opportunity/consensus/NVDA");
    await user.click(button);
    expect(screen.queryByRole("region", { name: "NVDA 共識明細" })).not.toBeInTheDocument();
    await user.click(button);
    await screen.findByText("Bernstein");
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("ConsensusDetail：共識怎麼算出來的", () => {
  it("平均、標準差、D、自身歷史百分位、合格歷史點數", async () => {
    mockDetail();
    const { panel } = await open();
    const facts = await within(panel).findByRole("list", { name: "共識數值" });
    expect(facts).toHaveTextContent("平均目標價$252.86");
    expect(facts).toHaveTextContent("標準差$71.84");
    expect(facts).toHaveTextContent("分歧度 D28.4%");
    expect(facts).toHaveTextContent("自身歷史百分位96.7%");
    expect(facts).toHaveTextContent("合格歷史點60 / 60 個月");
    expect(facts).toHaveTextContent("資料日2026-11-21");
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
    const months = await within(panel).findByRole("list", { name: "每月分歧度" });
    const items = within(months).getAllByRole("listitem");
    expect(items).toHaveLength(60);
    expect(items[0]).toHaveTextContent("2026-10-30");
    expect(items[0]).toHaveTextContent("不計入：股票分割無法判定");
    expect(items[1]).toHaveTextContent("2026-09-30");
    expect(items[1]).toHaveTextContent(/\d+ 位/);
    expect(items[1]).toHaveTextContent(/D \d+\.\d%/);
    expect(within(panel).getByText("每月分歧度（合格 59 / 60 個月）")).toBeInTheDocument();
  });
});

describe("ConsensusDetail：資料不足與異常", () => {
  it("資料不足：寫出具體原因，並說明不會入選", async () => {
    const item = { ...DETAIL.item!, status: "insufficient_analysts" as const,
                   reasons: ["insufficient_analysts: 有效分析師 1 < N_min 5",
                             "stale: 近 90 天更新比例 0.0000 < 0.5"],
                   gate: { first: false, second: false, selected: false, reasons: [] } };
    mockDetail(200, { ...DETAIL, item });
    const { panel } = await open();
    const why = await within(panel).findByRole("list", { name: "未入選原因" });
    expect(within(panel).getByText(/分析師人數不足/)).toBeInTheDocument();
    expect(why).toHaveTextContent("有效分析師 1 < N_min 5");
    expect(why).toHaveTextContent("近 90 天更新比例 0.0000 < 0.5");
    expect(panel).toHaveTextContent("資料不足的股票不會入選");
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
