/**
 * PB-12（#302，Anonymous Public Beta）：全站常駐頁尾——「非投資建議」
 * ＋「Beta，資料存在瀏覽器 cookie」的合併文字，外加隱私頁與回報問題
 * 兩個連結。`App.tsx` 把它掛在全部既有渲染分支的既有整合測試在
 * `App.test.tsx`；這裡只管「這個元件自己畫出什麼」。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Footer from "./Footer";

describe("Footer（PB-12／#302）", () => {
  it("同時陳述『非投資建議』與『Beta，資料存在瀏覽器』", () => {
    render(<Footer />);
    const text = screen.getByRole("contentinfo").textContent!;
    expect(text).toContain("非投資建議");
    expect(text).toMatch(/Beta.*資料存在.*瀏覽器/);
  });

  it("隱私政策連結指向隱私頁的 hash 路由", () => {
    render(<Footer />);
    expect(screen.getByRole("link", { name: "隱私與資料政策" }))
      .toHaveAttribute("href", "#/privacy");
  });

  it("回報問題連到本 repo 的 GitHub issues，且在新分頁開啟", () => {
    render(<Footer />);
    const link = screen.getByRole("link", { name: "回報問題" });
    expect(link).toHaveAttribute(
      "href", "https://github.com/L26041040/option-chaser/issues");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
