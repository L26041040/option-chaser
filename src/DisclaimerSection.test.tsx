/**
 * SW-10（#340，Owner 真機驗收回饋）：免責聲明——取代原本常駐首頁的
 * `BetaNotice.test.tsx`，斷言改成「這個 section 是設定頁的一個獨立
 * 分頁，不是首頁常駐區塊」的新語意，事實斷言本身盡量沿用舊測試。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DisclaimerSection, {
  ANONYMOUS_RETENTION_DAYS,
  ANONYMOUS_GRACE_PERIOD_DAYS,
} from "./DisclaimerSection";

describe("DisclaimerSection（SW-10／#340）", () => {
  it("提到這是 Beta、非投資建議", () => {
    render(<DisclaimerSection />);
    expect(screen.getByText(/Beta/)).toBeInTheDocument();
    expect(screen.getByText(/非投資建議/)).toBeInTheDocument();
  });

  it("提到資料存在瀏覽器 cookie 裡，兩個天數直接來自具名常數", () => {
    render(<DisclaimerSection />);
    const text = screen.getByRole("region", { name: "免責聲明" }).textContent!;
    expect(text).toContain("cookie");
    expect(text).toContain(String(ANONYMOUS_RETENTION_DAYS));
    expect(text).toContain(String(ANONYMOUS_GRACE_PERIOD_DAYS));
    expect(text).toMatch(/清除/);
  });

  it("提到劇本報酬以最差成交價計算——原本首頁清單頂端的口徑說明搬到這裡", () => {
    render(<DisclaimerSection />);
    expect(screen.getByText(/以最差成交價計算/)).toBeInTheDocument();
  });

  it("連到完整的隱私與資料政策頁面", () => {
    render(<DisclaimerSection />);
    expect(screen.getByRole("link", { name: "隱私與資料政策" }))
      .toHaveAttribute("href", "#/privacy");
  });

  it("是靜態內容區塊，不是可關閉的彈窗——沒有任何『關閉』／『知道了』按鈕", () => {
    render(<DisclaimerSection />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
