import { describe, expect, it } from "vitest";

import sampleRow from "../contracts/scenario_row_sample.json";
import type { ScenarioSummary } from "./api";
import { formatDaysLeft, formatReturn, sortScenarios } from "./scenarios";

// 形狀取自前後端共用的契約樣本；後端改欄位時後端的
// `test_scenario_row_sample_matches_the_live_list_response` 會先紅。
const base = sampleRow as unknown as ScenarioSummary;

function row(id: string, best_return: number | null): ScenarioSummary {
  return {
    ...base,
    id, symbol: "TLT",
    created_at: `2026-08-0${id}T00:00:00+00:00`,
    latest_analyzed_at: best_return === null ? null : "2026-08-04T00:00:00+00:00",
    best_return,
  };
}

describe("劇本清單排序", () => {
  it("依最新收益率降序", () => {
    const sorted = sortScenarios([row("1", 0.5), row("2", 2.5), row("3", 1.0)]);
    expect(sorted.map((r) => r.id)).toEqual(["2", "3", "1"]);
  });

  it("還沒跑過的排最後，不是當成 0", () => {
    // 若把 null 當 0，未分析的劇本會插在虧損劇本前面，憑空得到名次。
    const sorted = sortScenarios([row("1", null), row("2", -0.3), row("3", 0.1)]);
    expect(sorted.map((r) => r.id)).toEqual(["3", "2", "1"]);
  });

  it("同樣沒跑過時維持傳入順序（後端的建立順序）", () => {
    const sorted = sortScenarios([row("1", null), row("2", null), row("3", 0.1)]);
    expect(sorted.map((r) => r.id)).toEqual(["3", "1", "2"]);
  });

  it("不就地改動傳入的陣列", () => {
    const input = [row("1", 0.1), row("2", 0.9)];
    sortScenarios(input);
    expect(input.map((r) => r.id)).toEqual(["1", "2"]);
  });
});

describe("卡片格式", () => {
  it("沒跑過顯示「—」而不是 0%", () => {
    expect(formatReturn(null)).toBe("—");
    expect(formatReturn(0)).toBe("0.0%");
  });

  it("負收益率如實顯示", () => {
    expect(formatReturn(-0.325)).toBe("-32.5%");
  });

  it("已過期說成過期幾天，不夾到 0", () => {
    expect(formatDaysLeft(12)).toBe("12 天");
    expect(formatDaysLeft(0)).toBe("0 天");
    expect(formatDaysLeft(-5)).toBe("已過期 5 天");
  });
});
