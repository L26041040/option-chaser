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
  formatRunSummary,
  hasPriceRange,
  isStale,
  moneyOrDash,
  scenarioSignal,
  signalLabel,
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

describe("紅燈沉底（MVP-v2／#77、#80）", () => {
  it("已過期的劇本一律排在未過期的之後，即使報酬率更高", () => {
    const sorted = sortScenarios([
      { ...row("1", 9.9), expired: true },
      { ...row("2", 0.1), expired: false },
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["2", "1"]);
  });

  it("多個紅燈劇本之間仍依報酬率降序，不是隨意順序", () => {
    const sorted = sortScenarios([
      { ...row("1", 0.5), expired: true },
      { ...row("2", 2.0), expired: false },
      { ...row("3", 3.0), expired: true },
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["2", "3", "1"]);
  });

  it("紅燈組內未跑過的一樣沉到紅燈組的最後", () => {
    const sorted = sortScenarios([
      { ...row("1", null), expired: true },
      { ...row("2", 1.0), expired: true },
      { ...row("3", 5.0), expired: false },
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["3", "2", "1"]);
  });
});

describe("劇本級燈號（MVP-v2／#77、#80，附錄 A12）", () => {
  it("目標月已過完 → 紅燈，優先於是否有刷新失敗", () => {
    const expired = { ...row("1", 1.0), expired: true };
    expect(scenarioSignal(expired, undefined)).toBe("red");
    expect(scenarioSignal(
      expired, { stage: "fetch", message: "抓不到" })).toBe("red");
  });

  it("本次刷新失敗且未過期 → 黃燈", () => {
    const active = { ...row("1", 1.0), expired: false };
    expect(scenarioSignal(
      active, { stage: "fetch", message: "抓不到" })).toBe("yellow");
  });

  it("其餘（含尚未分析）→ 綠燈", () => {
    const active = { ...row("1", 1.0), expired: false };
    expect(scenarioSignal(active, undefined)).toBe("green");
    const neverRun = { ...row("1", null), expired: false };
    expect(scenarioSignal(neverRun, undefined)).toBe("green");
  });

  it("三種燈號各有一句不同的可及文字，不是空字串", () => {
    const labels = [signalLabel("red"), signalLabel("yellow"),
                    signalLabel("green")];
    expect(new Set(labels).size).toBe(3);
    labels.forEach((l) => expect(l).toBeTruthy());
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

  it("垃圾桶擋點（TR1／#88）有自己的說法，不是通用的刷新失敗", () => {
    expect(failureLabel("archived")).not.toBe(failureLabel(null));
    expect(failureLabel("archived")).toContain("垃圾桶");
  });
});

describe("劇本庫卡片的價格欄位（QA 修正）", () => {
  it("沒有值時顯示破折號，不是 0", () => {
    expect(moneyOrDash(null)).toBe("—");
    expect(moneyOrDash(undefined)).toBe("—");
    expect(moneyOrDash(82.11)).toBe("$82.11");
  });

  it("兩端都沒填就不畫區間那一行——compact row 的密度不該被空資料吃掉", () => {
    expect(hasPriceRange({ best_price: null, worst_price: null })).toBe(false);
    expect(hasPriceRange({ best_price: 120, worst_price: null })).toBe(true);
    expect(hasPriceRange({ best_price: null, worst_price: 100 })).toBe(true);
    expect(hasPriceRange({ best_price: 120, worst_price: 100 })).toBe(true);
  });
});

describe("更新中的劇本照樣參與排序（T08／#196 P1，取代 #136 partitionByLock）", () => {
  it("正在更新的劇本用它上一輪的舊 best_return 正常排序，不獨立排到後面", () => {
    // B 正在更新、舊收益率 9.0 遠高於 A（0.5）——它照樣排在最前面，因為
    // `sortScenarios` 根本不知道、也不需要知道誰在更新中（P1：更新中
    // 只是徽章顯示，不是排序輸入）。
    const rows = [row("1", 0.5), row("2", 9.0)];
    expect(sortScenarios(rows).map((r) => r.id)).toEqual(["2", "1"]);
  });
});

describe("一輪刷新摘要（T08／#196 P2）", () => {
  it("全部成功時只講成功數，不硬湊一個「0 失敗」", () => {
    expect(formatRunSummary(3, 0)).toBe("3 成功");
  });

  it("有失敗時兩個數字並列", () => {
    expect(formatRunSummary(2, 1)).toBe("2 成功／1 失敗");
  });

  it("全部失敗時仍講「0 成功」，不是省略成功那一半", () => {
    expect(formatRunSummary(0, 3)).toBe("0 成功／3 失敗");
  });
});
