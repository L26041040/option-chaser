/**
 * PB-12（#302，Anonymous Public Beta）：極簡隱私頁——六項內容齊全
 * （存了什麼、留多久、怎麼刪、清 cookie 的後果、不是投資建議、Beta
 * 狀態），「怎麼刪」連到真的可用的自助刪除入口（PB-04 的設定頁）。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BANNED_JARGON } from "./bannedCopy";
import PrivacyPage from "./PrivacyPage";
import {
  ANONYMOUS_RETENTION_DAYS,
  ANONYMOUS_GRACE_PERIOD_DAYS,
} from "./DisclaimerSection";

const SECTIONS = [
  "存了什麼", "留多久", "怎麼刪", "清除瀏覽器 cookie 的後果",
  "不是投資建議", "Beta 狀態",
];

describe("PrivacyPage（PB-12／#302）", () => {
  it("六項內容全部齊全", () => {
    render(<PrivacyPage />);
    for (const title of SECTIONS) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("『怎麼刪』連到設定頁的自助刪除入口，不是憑空一句話", () => {
    render(<PrivacyPage />);
    const links = screen.getAllByRole("link", { name: "設定頁" });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", "#/settings");
  });

  it("留多久的天數與 DisclaimerSection 共用同一份具名常數", () => {
    render(<PrivacyPage />);
    const text = screen.getByRole("heading", { name: "留多久" })
      .closest("section")!.textContent!;
    expect(text).toContain(String(ANONYMOUS_RETENTION_DAYS));
    expect(text).toContain(String(ANONYMOUS_GRACE_PERIOD_DAYS));
  });

  it("『刪除全部資料』與『清 cookie 找不回』兩件事講清楚是不同的事", () => {
    render(<PrivacyPage />);
    const cookieSection = screen
      .getByRole("heading", { name: "清除瀏覽器 cookie 的後果" })
      .closest("section")!.textContent!;
    expect(cookieSection).toMatch(/不同的事|兩件不同/);
  });

  it("明確聲明不是投資建議", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/不構成、也不應被視為投資建議/)).toBeInTheDocument();
  });

  it("回報問題連到 GitHub issue，且提醒不要貼敏感內容", () => {
    render(<PrivacyPage />);
    const link = screen.getByRole("link", { name: "回報到 GitHub issue" });
    expect(link).toHaveAttribute(
      "href", "https://github.com/L26041040/option-chaser/issues");
    expect(screen.getByText(/不要在裡面貼出/)).toBeInTheDocument();
  });

  it("文字不含開發者詞彙（SW-09／#339 收斂成共用清單 BANNED_JARGON）", () => {
    const { container } = render(<PrivacyPage />);
    const text = container.textContent ?? "";
    for (const banned of BANNED_JARGON) {
      expect(text).not.toContain(banned);
    }
  });
});
