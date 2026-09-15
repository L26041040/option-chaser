/**
 * PB-12（#302，Anonymous Public Beta）：首頁 Beta 說明——四項事實
 * 齊全（AC9 明文）：這是 Beta／資料存在瀏覽器 cookie（清掉即無法
 * 找回）／閒置 30+7 天會被清除／不是投資建議。
 *
 * 文案刻意壓到最短（單行、10px）——這一區塊佔用手機首頁 `.screen`
 * 的 flex gap 預算，MVP-v2／#77、#82 既有硬性密度要求「一屏至少看得到
 * 4 個劇本」不因本票新增區塊而退步（e2e `smoke.spec.ts` 的既有測試
 * 把關，實測曾一度只差 0.6px 才通過，已加大安全餘裕）。兩段緩衝期在
 * 這裡合寫成「30+7 天」、換瀏覽器風險合寫成「遺失不可復原」，完整的
 * 兩段式解釋（閒置 30 天→再 7 天緩衝→清除／清除或換瀏覽器的具體後果）
 * 留給 `PrivacyPage.tsx`「留多久」「清除瀏覽器 cookie 的後果」兩節，
 * 不在這個精簡摘要裡重複。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BetaNotice, {
  ANONYMOUS_ABANDONED_AFTER_DAYS,
  ANONYMOUS_GRACE_PERIOD_DAYS,
} from "./BetaNotice";

describe("BetaNotice（PB-12／#302）", () => {
  it("提到這是 Beta", () => {
    render(<BetaNotice />);
    expect(screen.getByText(/Beta/)).toBeInTheDocument();
  });

  it("提到資料存在瀏覽器 cookie 裡，遺失即無法找回", () => {
    render(<BetaNotice />);
    const text = screen.getByRole("region", { name: "Beta 版本說明" }).textContent!;
    expect(text).toMatch(/資料存在.*瀏覽器/);
    expect(text).toContain("cookie");
    expect(text).toMatch(/遺失|無法.*找回/);
  });

  it("兩個天數直接來自具名常數，不是憑空寫死的另一個數字", () => {
    render(<BetaNotice />);
    const text = screen.getByRole("region", { name: "Beta 版本說明" }).textContent!;
    expect(text).toContain(String(ANONYMOUS_ABANDONED_AFTER_DAYS));
    expect(text).toContain(String(ANONYMOUS_GRACE_PERIOD_DAYS));
    expect(text).toMatch(/清除/);
  });

  it("明確聲明不是投資建議", () => {
    render(<BetaNotice />);
    expect(screen.getByText(/非投資建議/)).toBeInTheDocument();
  });

  it("是常駐區塊，不是可關閉的彈窗——沒有任何『關閉』／『知道了』按鈕", () => {
    render(<BetaNotice />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
