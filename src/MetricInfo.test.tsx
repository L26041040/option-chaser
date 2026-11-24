import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import MetricInfo, { MetricHelpRow } from "./MetricInfo";
import { METRIC_HELP } from "./metricHelp";

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

  it("MetricHelpRow：每個指標一個名稱＋圖示，文字不含說明卡內容（收起時不渲染）", () => {
    const { container } = render(
      <MetricHelpRow metrics={["meanTarget", "validBrokerCount"]} />);
    expect(screen.getByRole("button", { name: "平均目標價說明" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "有效券商數說明" })).toBeInTheDocument();
    expect(container).toHaveTextContent(/^指標說明平均目標價有效券商數$/);
  });
});
