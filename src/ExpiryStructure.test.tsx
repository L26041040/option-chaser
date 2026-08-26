import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ExpiryStructure from "./ExpiryStructure";
import sample from "../contracts/analysis_sample.json";
import {
  primaryResult, resolveCandidate,
  type AnalysisView, type Candidate, type StrategyResult,
} from "./api";
import { legPrices } from "./expiry";

const view = sample as unknown as AnalysisView;
const result = primaryResult(view)!;
const groups = result.expiry_top10!;
const pool = view.candidate_pool!;

/** T09（#191）：`candidates[0]` 那種直接索引已經不成立——測試改用這個
 *  helper 透過 `resolveCandidate()` 解回完整內容，跟正式程式碼走同一條
 *  路徑，不另外自己挖 `candidate_pool`。 */
function firstCandidate(v: AnalysisView, expiry: string): Candidate {
  const group = v.candidate_pool
    ? (v.results[0].expiry_top10 ?? []).find((g) => g.expiry === expiry)
    : undefined;
  return resolveCandidate(v, group?.candidate_keys[0])!;
}

function show(
  overrides: Partial<StrategyResult> = {},
  poolPatch: Record<string, Candidate> = {},
) {
  const patchedView: AnalysisView = {
    ...view,
    candidate_pool: { ...pool, ...poolPatch },
  };
  return render(
    <ExpiryStructure view={patchedView} result={{ ...result, ...overrides }}
                     baselineExpiry={view.baseline_expiry} />,
  );
}

/** 把某一期塞進更多候選，好測「清單有很多列」與「組數夠多不警示」。
 *  回傳 `result` 覆寫（`expiry_top10`／`expiry_counts`）與新候選要併入
 *  `candidate_pool` 的部分——兩者必須一起傳給 `show()`，key 引用才解得
 *  回內容（T09／#191：候選內容不再內嵌在 `expiry_top10` 裡）。 */
function withCandidates(expiry: string, n: number, patchEach?: (c: Candidate, i: number) => Candidate) {
  const base = firstCandidate(view, expiry);
  const many = Array.from({ length: n }, (_, i) => {
    const c = { ...base, candidate_key: `${base.candidate_key}#${i}`,
               baseline_return: base.baseline_return - i * 0.1 };
    return patchEach ? patchEach(c, i) : c;
  });
  const poolPatch = Object.fromEntries(many.map((c) => [c.candidate_key, c]));
  const resultOverrides: Partial<StrategyResult> = {
    expiry_top10: groups.map((g) =>
      g.expiry === expiry
        ? { ...g, candidate_keys: many.map((c) => c.candidate_key) }
        : g),
    expiry_counts: result.expiry_counts.map(([e, c]) =>
      (e === expiry ? [e, n] : [e, c]) as [string, number]),
  };
  return { resultOverrides, poolPatch };
}

describe("到期日按鈕", () => {
  it("每個到期日一顆，並附該期最高收益", () => {
    show();

    const chips = screen.getAllByRole("button");
    expect(chips).toHaveLength(groups.length);
    for (const [i, group] of groups.entries()) {
      const top = firstCandidate(view, group.expiry);
      expect(chips[i]).toHaveTextContent(group.expiry);
      expect(chips[i]).toHaveTextContent(
        `${(top.baseline_return * 100).toFixed(1)}%`);
    }
  });

  it("預設選中 baseline 期——與主圖同一口徑", () => {
    show();
    expect(screen.getByRole("button", { pressed: true }))
      .toHaveTextContent(view.baseline_expiry!);
  });

  it("點另一顆就換那一期的清單", async () => {
    const other = groups.find((g) => g.expiry !== view.baseline_expiry)!;
    const top = firstCandidate(view, other.expiry);
    show();

    await userEvent.click(screen.getByRole("button", { name: new RegExp(other.expiry) }));

    expect(screen.getByRole("button", { pressed: true })).toHaveTextContent(other.expiry);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(other.candidate_keys.length);
    expect(rows[0]).toHaveTextContent(
      `${(top.baseline_return * 100).toFixed(1)}%`);
  });
});

describe("候選窄列", () => {
  it("每列顯示名次、策略履約與劇本報酬", () => {
    show();

    const row = screen.getAllByRole("listitem")[0];
    const top = firstCandidate(view, view.baseline_expiry!);
    expect(row).toHaveTextContent("#1");
    expect(row).toHaveTextContent(`買 ${top.legs[0].strike} / 賣 ${top.legs[1].strike}`);
    expect(row).toHaveTextContent(`${(top.baseline_return * 100).toFixed(1)}%`);
  });

  it("三個價格在收合狀態下就看得到：買腿買入價、賣腿賣出價、淨成本", () => {
    show();

    const top = firstCandidate(view, view.baseline_expiry!);
    const prices = legPrices(top);
    const row = screen.getAllByRole("listitem")[0];
    expect(row).toHaveTextContent(`買 $${prices.buyAsk!.toFixed(2)}`);
    expect(row).toHaveTextContent(`賣 $${prices.sellBid!.toFixed(2)}`);
    expect(row).toHaveTextContent(`淨成本 $${prices.net.toFixed(2)}`);
  });

  it("Bid/Ask 過寬的候選帶 ⚠ 徽章，文案明確寫「Bid/Ask 過寬」（MVP V3／#104）", () => {
    const expiry = view.baseline_expiry!;
    const { resultOverrides, poolPatch } = withCandidates(expiry, 2,
      (c, i) => ({ ...c, wide_spread_warning: i === 0 }));
    show(resultOverrides, poolPatch);

    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("⚠")).toBeInTheDocument();
    expect(within(rows[0]).getByTitle("Bid/Ask 過寬")).toBeInTheDocument();
    expect(within(rows[1]).queryByText("⚠")).not.toBeInTheDocument();
    // 舊泛稱字串不得復發（MVP V3／#104 AC：新舊字串皆需明文檢查封鎖）。
    expect(screen.queryByText(/報價品質有疑慮/)).not.toBeInTheDocument();
    expect(screen.queryByText(/報價非最新/)).not.toBeInTheDocument();
  });

  it("零成交量的候選不再帶 ⚠ 徽章（MVP V3／#104：LEAPS／冷門履約價零成交是常態）", () => {
    const expiry = view.baseline_expiry!;
    const { resultOverrides, poolPatch } = withCandidates(expiry, 2,
      (c) => ({ ...c, wide_spread_warning: false }));
    show(resultOverrides, poolPatch);

    const rows = screen.getAllByRole("listitem");
    for (const row of rows) {
      expect(within(row).queryByText("⚠")).not.toBeInTheDocument();
    }
  });

  it("單調性違反的候選帶獨立徽章，不跟 Bid/Ask 過寬的 ⚠ 混在一起", () => {
    // FB5-03（#64）：`monotonicity_warning` 是獨立欄位，成因與嚴重性都
    // 跟 `wide_spread_warning` 不同（配對關係違反 vs 單一數值超標），
    // 徽章要分得開，不能共用同一個符號，否則使用者無法分辨兩種警示。
    const expiry = view.baseline_expiry!;
    const { resultOverrides, poolPatch } = withCandidates(expiry, 2, (c, i) => ({
      ...c, wide_spread_warning: false, monotonicity_warning: i === 0,
    }));
    show(resultOverrides, poolPatch);

    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("🚩")).toBeInTheDocument();
    expect(within(rows[0]).queryByText("⚠")).not.toBeInTheDocument();
    expect(within(rows[1]).queryByText("🚩")).not.toBeInTheDocument();
  });

  it("引擎給幾筆就畫幾筆、名次照它排好的順序，前端不自己截斷", () => {
    const { resultOverrides, poolPatch } = withCandidates(view.baseline_expiry!, 12);
    show(resultOverrides, poolPatch);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(12);   // 引擎給幾筆就畫幾筆，不自己截斷
    expect(rows[0]).toHaveTextContent("#1");
    expect(rows.at(-1)).toHaveTextContent("#12");
  });
});

describe("就地展開", () => {
  it("預設收合；點一下才顯示那個候選的 Heatmap", async () => {
    show();

    expect(screen.queryByRole("table")).not.toBeVisible();

    await userEvent.click(screen.getAllByRole("listitem")[0].querySelector("summary")!);

    expect(screen.getByRole("table")).toBeVisible();
  });

  it("展開的是那一列自己的候選，不是別列的", async () => {
    // 三組候選各給一份一眼認得出來的矩陣；接錯列的話下面的斷言會抓到。
    const expiry = view.baseline_expiry!;
    const { resultOverrides, poolPatch } = withCandidates(expiry, 3, (c, i) => ({
      ...c,
      matrix: { prices: [[100 + i, "", 0.01 * i]] as [number, string, number][],
                dates: [["2026-08-07", ""]] as [string, string][],
                cells: [[0.5]] },
    }));
    show(resultOverrides, poolPatch);

    const rows = screen.getAllByRole("listitem");
    await userEvent.click(rows[1].querySelector("summary")!);

    expect(within(rows[1]).getByRole("rowheader")).toHaveTextContent("101.00");
    // 決策 M（#109）：候選展開後的 Heatmap 跟主圖是同一個元件，±% 標註
    // 不需要另外接線——這裡直接核對展開的是這一列自己的 move_pct
    // （0.01），不是別列的。QA-FIX-1 後 ±% 在最右欄（`td.heatmap-move-pct`），
    // 不再在價格 rowheader 裡。
    expect(rows[1].querySelector("td.heatmap-move-pct"))
      .toHaveTextContent("+1.0%");
  });
});

describe("候選池過少警示", () => {
  it("該期有效組數 < 3 時說明實際組數", () => {
    show();   // 契約樣本每期都只有 1 組
    expect(screen.getByRole("status")).toHaveTextContent("該期僅 1 組");
  });


  it("引擎沒給該期組數時不警示——「不知道」不是「太少」", () => {
    show({ expiry_counts: [] });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("組數足夠就沒話講——live region 常駐但空著", () => {
    const { resultOverrides, poolPatch } = withCandidates(view.baseline_expiry!, 5);
    show(resultOverrides, poolPatch);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("警示跟著切換的到期日走，不是固定講 baseline 那期", async () => {
    const other = groups.find((g) => g.expiry !== view.baseline_expiry)!;
    // baseline 期組數充足、另一期只有 1 組
    const { resultOverrides, poolPatch } = withCandidates(view.baseline_expiry!, 5);
    show(resultOverrides, poolPatch);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    await userEvent.click(screen.getByRole("button", { name: new RegExp(other.expiry) }));

    expect(screen.getByRole("status")).toHaveTextContent("該期僅 1 組");
  });
});

describe("邊界", () => {
  it("一期都沒有時整塊不顯示，而不是畫一個空殼", () => {
    const { container } = show({ expiry_top10: [] });
    expect(container).toBeEmptyDOMElement();
  });

});
