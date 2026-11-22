import { describe, expect, it } from "vitest";

import type { ConsensusRefreshSymbol } from "./api";
import { formatWait, isFailed, progressText, retryGate } from "./consensusUpdate";

const NOW = Date.parse("2026-09-28T13:00:00Z");

function sym(over: Partial<ConsensusRefreshSymbol>): ConsensusRefreshSymbol {
  return { symbol: "GGG", state: "cooling", last_success_at: null,
           last_attempt_at: "2026-09-28T12:53:20+00:00", error: "逾時",
           retries_today: 0, next_retry_at: "2026-09-28T13:08:20+00:00",
           retryable_now: false, as_of: null, ...over };
}

describe("retryGate", () => {
  it("冷卻中：停用，說明剩餘時間與原因", () => {
    expect(retryGate(sym({}), NOW)).toEqual({
      enabled: false, remainingSeconds: 500,
      reason: "上次失敗，冷卻中，還要約 8 分 20 秒才能重試" });
  });

  it("冷卻時間一到（用自己的時鐘）：可以按", () => {
    expect(retryGate(sym({}), Date.parse("2026-09-28T13:08:20Z")).enabled).toBe(true);
  });

  it("後端說冷卻已過（retry_ready）：可以按", () => {
    expect(retryGate(sym({ state: "retry_ready", next_retry_at: null }), NOW))
      .toEqual({ enabled: true, reason: null, remainingSeconds: null });
  });

  it("重試用完、別人正在處理、今天已成功：停用並說明", () => {
    expect(retryGate(sym({ state: "exhausted" }), NOW).reason)
      .toBe("今天的重試次數已用完，下一個交易日自動再試");
    expect(retryGate(sym({ state: "in_progress" }), NOW).reason)
      .toBe("另一個更新正在處理這一檔");
    expect(retryGate(sym({ state: "done" }), NOW).enabled).toBe(false);
  });

  it("讀不懂的時間視同到期，不把按鈕永久鎖住", () => {
    expect(retryGate(sym({ next_retry_at: "garbage" }), NOW).enabled).toBe(true);
  });
});

describe("文字", () => {
  it("formatWait", () => {
    expect(formatWait(45)).toBe("45 秒");
    expect(formatWait(905)).toBe("15 分 05 秒");
  });

  it("progressText", () => {
    expect(progressText({ total: 50, done: 12, failed: 2, pending: 36, in_progress: 0 }))
      .toBe("已完成 12／50 檔、失敗 2 檔");
  });

  it("isFailed 只認失敗的三種狀態", () => {
    expect(["cooling", "retry_ready", "exhausted", "done", "pending", "in_progress"]
      .map((state) => isFailed(sym({ state: state as ConsensusRefreshSymbol["state"] }))))
      .toEqual([true, true, true, false, false, false]);
  });
});
