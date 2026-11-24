import { describe, expect, it } from "vitest";

import { prDisplay, prLabel } from "./dispersionRank";
import {
  METRIC_HELP,
  metricHelpLabel,
  targetUpsideLabel,
  targetUpsidePct,
  type MetricHelpKey,
} from "./metricHelp";
import { ratioPct } from "./opportunity";
import { money } from "./scenarios";

const allText = (key: MetricHelpKey) => {
  const h = METRIC_HELP[key];
  return `${h.name}${h.definition}${h.direction}${h.basis}`;
};

describe("指標說明（V2-04／#406）：集中管理、名稱照 #405 定稿", () => {
  it("名稱與 #405 定稿一致", () => {
    expect(METRIC_HELP.dispersionRank.name).toBe("分歧度歷史排序（PR）");
    expect(METRIC_HELP.dispersionRate.name).toBe("分析師分歧率");
    expect(METRIC_HELP.validBrokerCount.name).toBe("有效券商數");
    expect(METRIC_HELP.meanTarget.name).toBe("平均目標價");
    expect(METRIC_HELP.currentPrice.name).toBe("目前股價");
    expect(METRIC_HELP.targetUpside.name).toBe("目標漲跌幅");
    expect(METRIC_HELP.scenarioReturn.name).toBe("股價達標時的策略報酬");
    expect(METRIC_HELP.costAndMaxLoss.name).toBe("成本、最大損失");
    expect(METRIC_HELP.scanUniverse.name).toBe("掃描股票範圍");
    expect(METRIC_HELP.dataDate.name).toBe("資料日期");
    expect(METRIC_HELP.dailyCap.name).toBe("每日上限");
    expect(METRIC_HELP.rateLimitPause.name).toBe("限流暫停");
    expect(METRIC_HELP.rotatingUpdate.name).toBe("輪替更新");
  });

  it("每則都有定義、方向、計算口徑三段，圖示的 aria-label 是「名稱＋說明」", () => {
    for (const key of Object.keys(METRIC_HELP) as MetricHelpKey[]) {
      const h = METRIC_HELP[key];
      expect(h.definition.length, key).toBeGreaterThan(0);
      expect(h.direction.length, key).toBeGreaterThan(0);
      expect(h.basis.length, key).toBeGreaterThan(0);
      expect(metricHelpLabel(key)).toBe(`${h.name}說明`);
    }
  });

  it("不使用舊名稱，也不使用「期望值」「勝率」「保證」", () => {
    for (const key of Object.keys(METRIC_HELP) as MetricHelpKey[]) {
      const text = allText(key);
      for (const banned of ["期望值", "勝率", "保證", "自身歷史百分位", "分歧度 D",
                            "有效分析師", "目標價情境報酬", "搜尋母體", "入選股"]) {
        expect(text, `${key} 含「${banned}」`).not.toContain(banned);
      }
    }
  });
});

describe("說明裡的範例數字與程式口徑一致", () => {
  it("PR：原百分位 12% → PR88（前 12%）；20.4% → PR79（向下取整）", () => {
    const text = allText("dispersionRank");
    expect(prLabel(0.12)).toBe("PR88（前 12%）");
    expect(text).toContain("PR88");
    expect(text).toContain("前 12%");
    expect(text).toContain("比過去 88% 的月份更集中");
    expect(prDisplay(0.204)).toBe(79);
    expect(text).toContain("原百分位 20.4% → PR79");
    // 口徑：60 個月、月底最後一個平日、嚴格早於資料日期、至少 24 個有效月份、midrank。
    expect(text).toMatch(/60 個月/);
    expect(text).toMatch(/最後一個平日/);
    expect(text).toMatch(/早於資料日期/);
    expect(text).toMatch(/至少 24 個有效月份/);
    expect(text).toMatch(/midrank/);
  });

  it("分析師分歧率：平均 $200、標準差 $18 → 9.0%；有效期 12 個月、統一分割基準", () => {
    const text = allText("dispersionRate");
    expect(ratioPct(18 / 200)).toBe("9.0%");
    expect(text).toContain(`平均 ${money(200)}、標準差 ${money(18)} → 分歧率 9.0%`);
    expect(text).toMatch(/標準差 ÷ 平均/);
    expect(text).toMatch(/12 個月/);
    expect(text).toMatch(/分割/);
  });

  it("有效券商數：至少 5 家才計算", () => {
    expect(allText("validBrokerCount")).toMatch(/至少 5 家/);
    expect(allText("validBrokerCount")).toMatch(/12 個月/);
  });

  it("平均目標價：分割前 $400、1 拆 4 → $100", () => {
    expect(money(400 / 4)).toBe("$100.00");
    expect(allText("meanTarget")).toContain(`${money(400)} → ${money(100)}`);
  });

  it("目標漲跌幅 = (平均目標價 ÷ 目前股價 − 1) × 100%；$120 ÷ $100 → +20.0%", () => {
    expect(targetUpsidePct(120, 100)).toBeCloseTo(20, 10);
    expect(targetUpsidePct(90, 120)).toBeCloseTo(-25, 10);
    expect(targetUpsidePct(null, 100)).toBeNull();
    expect(targetUpsidePct(120, null)).toBeNull();
    expect(targetUpsidePct(120, 0)).toBeNull();
    expect(targetUpsideLabel(targetUpsidePct(120, 100))).toBe("+20.0%");
    expect(targetUpsideLabel(targetUpsidePct(90, 120))).toBe("-25.0%");
    expect(targetUpsideLabel(null)).toBe("—");
    const text = allText("targetUpside");
    expect(text).toContain("(平均目標價 ÷ 目前股價 − 1) × 100%");
    expect(text).toContain(`平均目標價 ${money(120)}、目前股價 ${money(100)} → +20.0%`);
    expect(text).toMatch(/股價日期/);
    expect(allText("currentPrice")).toMatch(/股價日期/);
  });

  it("成本、最大損失：1 口 = 100 股，每股 $1.25 → 每口 $125.00", () => {
    const text = allText("costAndMaxLoss");
    expect(text).toContain("1 口 = 100 股");
    expect(money(1.25 * 100)).toBe("$125.00");
    expect(text).toContain(`每股 ${money(1.25)} → 每口 ${money(125)}`);
  });

  it("股價達標時的策略報酬：條件式情境報酬，不是機率", () => {
    const text = allText("scenarioReturn");
    expect(text).toMatch(/目標月份/);
    expect(text).toMatch(/平均目標價/);
    expect(text).toMatch(/情境/);
    expect(text).toMatch(/機率/);
  });
});
