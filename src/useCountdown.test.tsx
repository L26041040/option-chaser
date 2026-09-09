import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCountdownSeconds } from "./useCountdown";

/** 純粹把 hook 的回傳值印出來，方便斷言——這個 hook 本身不能直接在
 *  測試裡呼叫（React hook 規則），需要一個宿主元件。 */
function Probe({ deadline }: { deadline: string | null }) {
  const remaining = useCountdownSeconds(deadline);
  return <span data-testid="remaining">{remaining === null ? "null" : remaining}</span>;
}

describe("useCountdownSeconds（SCALE-05／#260，AC-3）", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("deadline 為 null 時不倒數、也不啟動計時器", () => {
    vi.setSystemTime(new Date("2026-09-06T12:00:00Z"));
    render(<Probe deadline={null} />);
    expect(screen.getByTestId("remaining").textContent).toBe("null");
    // 沒有計時器可跑——推進時間不該讓它拋錯或憑空冒出數字。
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("null");
  });

  it("每秒重新計算一次，時間流逝時倒數往下走——來源是固定的絕對時間點，" +
     "不是遞減的本地 state", () => {
    vi.setSystemTime(new Date("2026-09-06T12:00:00Z"));
    render(<Probe deadline="2026-09-06T12:00:10Z" />);
    expect(screen.getByTestId("remaining").textContent).toBe("10");

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("7");

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("4");
  });

  it("到期後可重新嘗試：倒數歸零並停在 0，不會變成負數", () => {
    vi.setSystemTime(new Date("2026-09-06T12:00:00Z"));
    render(<Probe deadline="2026-09-06T12:00:05Z" />);
    expect(screen.getByTestId("remaining").textContent).toBe("5");

    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("0");

    // 繼續推進不會變成負數。
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("0");
  });

  it("rerender（deadline 不變）不會重設倒數——同一個元件重新渲染多次，" +
     "答案仍然只取決於現在的時間，不會被打回原始值", () => {
    vi.setSystemTime(new Date("2026-09-06T12:00:00Z"));
    const { rerender } = render(<Probe deadline="2026-09-06T12:00:10Z" />);
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.getByTestId("remaining").textContent).toBe("6");

    // 用同一個 deadline 重新渲染（模擬 props 沒變但父層重繪）。
    rerender(<Probe deadline="2026-09-06T12:00:10Z" />);
    expect(screen.getByTestId("remaining").textContent).toBe("6");
  });
});
