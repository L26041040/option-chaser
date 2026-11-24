import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import MetricInfo, { MetricHelpRow } from "./MetricInfo";
import { METRIC_HELP, metricHelpDescription } from "./metricHelp";

describe("MetricInfo（V2-04／#406）", () => {
  it("圖示 aria-label 是「名稱說明」；打開後依序是名稱、定義、方向、計算口徑", async () => {
    render(<MetricInfo metric="dispersionRate" />);
    const button = screen.getByRole("button", { name: "分析師分歧率說明" });
    await userEvent.setup().click(button);
    const tip = screen.getByRole("tooltip");
    const h = METRIC_HELP.dispersionRate;
    expect(tip).toHaveTextContent(
      `${h.name}定義${h.definition}方向${h.direction}計算口徑${h.basis}`);
  });

  it("第一次聚焦（說明卡還沒渲染）時就有無障礙描述；打開後改指向說明卡", async () => {
    const { container } = render(<p>分歧率<MetricInfo metric="dispersionRate" /></p>);
    const button = screen.getByRole("button", { name: "分析師分歧率說明" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(button).toHaveAccessibleDescription(metricHelpDescription("dispersionRate"));
    expect(metricHelpDescription("dispersionRate"))
      .toContain(METRIC_HELP.dispersionRate.basis);
    // 常駐描述不混進周圍的文字內容。
    expect(container).toHaveTextContent(/^分歧率$/);
    await userEvent.setup().tab();
    expect(button).toHaveFocus();
    const tip = screen.getByRole("tooltip");
    expect(button).toHaveAttribute("aria-describedby", tip.id);
  });

  it("MetricHelpRow：每個指標一個名稱＋圖示，文字不含說明卡內容（收起時不渲染）", () => {
    const { container } = render(
      <MetricHelpRow metrics={["meanTarget", "validBrokerCount"]} />);
    expect(screen.getByRole("button", { name: "平均目標價說明" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "有效券商數說明" })).toBeInTheDocument();
    expect(container).toHaveTextContent(/^指標說明平均目標價有效券商數$/);
  });
});
