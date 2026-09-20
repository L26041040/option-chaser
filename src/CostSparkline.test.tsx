import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CostSparkline from "./CostSparkline";

describe("CostSparkline", () => {
  it("null——顯示佔位符「—」，不畫任何 SVG", () => {
    render(<CostSparkline points={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("空陣列——同樣顯示佔位符（跟 null 是同一種「沒東西可畫」）", () => {
    render(<CostSparkline points={[]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("undefined（既有 e2e／舊快取回應可能缺這個鍵）——不炸掉，顯示佔位符", () => {
    // @ts-expect-error 刻意傳型別上不該出現、但 runtime 可能發生的值
    render(<CostSparkline points={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("全部缺席快照——沒有任何一段可畫，顯示佔位符而不是硬畫一條假線", () => {
    render(<CostSparkline points={[["2026-01-01", null], ["2026-01-02", null]]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("上升——SVG 有 aria-label 講「上升」與對應 class", () => {
    render(<CostSparkline points={[["2026-01-01", 1], ["2026-01-02", 2]]} />);
    const svg = screen.getByRole("img", { name: /淨成本走勢，上升/ });
    expect(svg).toHaveClass("sparkline-up");
  });

  it("下降——SVG 有 aria-label 講「下降」與對應 class", () => {
    render(<CostSparkline points={[["2026-01-01", 2], ["2026-01-02", 1]]} />);
    const svg = screen.getByRole("img", { name: /淨成本走勢，下降/ });
    expect(svg).toHaveClass("sparkline-down");
  });

  it("持平——SVG 有 aria-label 講「持平」與對應 class", () => {
    render(<CostSparkline points={[["2026-01-01", 1], ["2026-01-02", 1]]} />);
    const svg = screen.getByRole("img", { name: /淨成本走勢，持平/ });
    expect(svg).toHaveClass("sparkline-flat");
  });

  it("中間缺席快照斷成兩段折線，不連過去", () => {
    const { container } = render(<CostSparkline points={[
      ["2026-01-01", 1], ["2026-01-02", null], ["2026-01-03", 3],
    ]} />);
    const polylines = container.querySelectorAll("polyline");
    expect(polylines).toHaveLength(2);
  });

  it("沒有斷點——只有一段折線", () => {
    const { container } = render(<CostSparkline points={[
      ["2026-01-01", 1], ["2026-01-02", 2], ["2026-01-03", 3],
    ]} />);
    expect(container.querySelectorAll("polyline")).toHaveLength(1);
  });
});
