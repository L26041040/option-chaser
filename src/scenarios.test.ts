import { describe, expect, it } from "vitest";

import sampleRow from "../contracts/scenario_row_sample.json";
import type { ScenarioSummary } from "./api";
import {
  STALE_AFTER_HOURS,
  failureLabel,
  formatDaysLeft,
  formatRepresentativeExpiry,
  formatRepresentativeLegs,
  formatReturn,
  isStale,
  sortScenarios,
} from "./scenarios";

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

describe("代表候選格式（MVP-v2／#77、#78）", () => {
  it("價差寫成「買 X / 賣 Y」，買腿在前、賣腿在後", () => {
    expect(formatRepresentativeLegs({
      strategy: "bull-call-spread",
      legs: [{ strike: 118, option_type: "call" },
            { strike: 122, option_type: "call" }],
      expiry: "2026-09-18", baseline_return: 1.5,
    })).toBe("買 118 / 賣 122");
  });

  it("單腳只寫「買 X」，不憑空生出賣腿", () => {
    expect(formatRepresentativeLegs({
      strategy: "long-call",
      legs: [{ strike: 118, option_type: "call" }],
      expiry: "2026-09-18", baseline_return: 0.3,
    })).toBe("買 118");
  });

  it("沒有代表候選時說「—」，不是編一組假的候選", () => {
    expect(formatRepresentativeLegs(null)).toBe("—");
  });

  it("實際到期日原樣顯示，沒有代表候選時說「—」", () => {
    expect(formatRepresentativeExpiry({
      strategy: "bull-call-spread",
      legs: [{ strike: 118, option_type: "call" },
            { strike: 122, option_type: "call" }],
      expiry: "2026-09-18", baseline_return: 1.5,
    })).toBe("2026-09-18");
    expect(formatRepresentativeExpiry(null)).toBe("—");
  });
});

describe("資料新鮮度（V4／#52）", () => {
  const at = "2026-08-04T12:00:00+00:00";
  const hoursLater = (h: number) =>
    new Date(Date.parse(at) + h * 3_600_000);

  it("剛刷新過的不算舊", () => {
    expect(isStale(at, hoursLater(1))).toBe(false);
  });

  it("超過門檻就算舊——卡片上的數字不該讓人以為是現在的", () => {
    expect(isStale(at, hoursLater(STALE_AFTER_HOURS + 1))).toBe(true);
  });

  it("剛好在門檻上還算新鮮，跨過去才算舊", () => {
    expect(isStale(at, hoursLater(STALE_AFTER_HOURS))).toBe(false);
  });

  it("尚未分析不算「舊」——卡片已經說了「尚未分析」，那是另一回事", () => {
    expect(isStale(null, hoursLater(999))).toBe(false);
  });

  it("讀不懂的時間戳當成可疑，不當成新鮮", () => {
    expect(isStale("not-a-timestamp", hoursLater(0))).toBe(true);
  });
});

describe("刷新失敗分層（V4／#52）", () => {
  it("抓不到報價與分析失敗說的不是同一句話", () => {
    expect(failureLabel("fetch")).not.toBe(failureLabel("analyze"));
    expect(failureLabel("fetch")).not.toBe(failureLabel("params"));
  });

  it("後端沒給分層時仍說得出一句話，不是空白", () => {
    expect(failureLabel(null)).toBeTruthy();
  });
});
