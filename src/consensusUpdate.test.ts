import { describe, expect, it } from "vitest";

import consensusSample from "../contracts/opportunity_consensus_sample.json";
import statusSample from "../contracts/opportunity_consensus_status_sample.json";
import type {
  ConsensusRefreshStatusResponse,
  ConsensusRefreshSymbol,
  OpportunityConsensusResponse,
} from "./api";
import {
  builtCount,
  cronText,
  dataPhase,
  formatWait,
  isFailed,
  nextAutoUpdate,
  outOfScopeText,
  progressText,
  retryGate,
} from "./consensusUpdate";

const CONSENSUS = consensusSample as unknown as OpportunityConsensusResponse;
const STATUS = statusSample as unknown as ConsensusRefreshStatusResponse;

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
      .toBe("今天的重試次數已用完，明天自動更新");
    expect(retryGate(sym({ state: "in_progress" }), NOW).reason)
      .toBe("另一個更新正在處理這一檔");
    expect(retryGate(sym({ state: "done" }), NOW).enabled).toBe(false);
  });

  it("用完時依美東日期說「明天」或「下週一」自動更新", () => {
    expect(retryGate(sym({ state: "exhausted" }), NOW, { today: "2026-09-25" }).reason)
      .toBe("今天的重試次數已用完，下週一自動更新");
  });

  it("今日上游呼叫已達每日上限：失敗與待更新的都停用，說明明天自動更新", () => {
    const cap = { capReached: true, today: "2026-09-28" };
    for (const state of ["retry_ready", "cooling", "pending"] as const) {
      expect(retryGate(sym({ state, next_retry_at: null }), NOW, cap)).toEqual({
        enabled: false, remainingSeconds: null,
        reason: "今日上游呼叫已達每日上限，明天自動更新" });
    }
  });

  it("來源限流（429）暫停中：失敗與待更新的都停用，說明還要等多久", () => {
    const ctx = { rateLimitedUntil: "2026-09-28T13:20:00Z" };
    for (const state of ["retry_ready", "cooling", "pending"] as const) {
      expect(retryGate(sym({ state, next_retry_at: null }), NOW, ctx)).toEqual({
        enabled: false, remainingSeconds: 1200,
        reason: "資料來源限流中（429），還要約 20 分 00 秒才會再更新" });
    }
    expect(retryGate(sym({ state: "retry_ready", next_retry_at: null }),
                     Date.parse("2026-09-28T13:20:00Z"), ctx).enabled).toBe(true);
  });

  it("讀不懂的時間視同到期，不把按鈕永久鎖住", () => {
    expect(retryGate(sym({ next_retry_at: "garbage" }), NOW).enabled).toBe(true);
  });
});

describe("nextAutoUpdate（排程只在平日跑）", () => {
  it("明天是平日：明天；明天是週末：下週一", () => {
    expect(nextAutoUpdate("2026-09-28")).toBe("明天自動更新");   // 週一
    expect(nextAutoUpdate("2026-09-24")).toBe("明天自動更新");   // 週四
    expect(nextAutoUpdate("2026-09-25")).toBe("下週一自動更新"); // 週五
    expect(nextAutoUpdate("2026-09-26")).toBe("下週一自動更新"); // 週六
    expect(nextAutoUpdate("2026-09-27")).toBe("明天自動更新");   // 週日
  });

  it("沒有日期或讀不懂：照樣說明天", () => {
    expect(nextAutoUpdate(undefined)).toBe("明天自動更新");
    expect(nextAutoUpdate("garbage")).toBe("明天自動更新");
  });

  it("排程有執行紀錄：照樣說明天／下週一自動更新", () => {
    const ran = { runs_today: 0, symbols_today: 0, last_run_day: "2026-09-25",
                  lookback_days: 30 };
    expect(nextAutoUpdate("2026-09-28", ran)).toBe("明天自動更新");
    expect(nextAutoUpdate("2026-09-25", ran)).toBe("下週一自動更新");
  });

  it("排程尚未執行（沒有任何授權成功的紀錄）：不說會自動更新", () => {
    const never = { runs_today: 0, symbols_today: 0, last_run_day: null, lookback_days: 30 };
    expect(nextAutoUpdate("2026-09-28", never))
      .toBe("排程尚未執行，不會自動更新，明天請手動「繼續更新」");
    expect(nextAutoUpdate("2026-09-25", never))
      .toBe("排程尚未執行，不會自動更新，下週一請手動「繼續更新」");
  });

  it("無法確認排程狀態（known: false）：不承諾自動更新", () => {
    const unknown = { known: false, runs_today: null, symbols_today: null,
                      last_run_day: null, lookback_days: 30 };
    expect(nextAutoUpdate("2026-09-28", unknown))
      .toBe("無法確認排程狀態，明天請手動「繼續更新」");
  });
});

describe("cronText（排程實際執行情形，只依授權成功的紀錄）", () => {
  it("今天跑過：次數與檔數", () => {
    expect(cronText({ runs_today: 3, symbols_today: 84, last_run_day: "2026-09-28",
                      lookback_days: 30 }))
      .toBe("今天已執行 3 次（處理 84 檔）");
  });

  it("今天還沒跑：說最近一次是哪天", () => {
    expect(cronText({ runs_today: 0, symbols_today: 0, last_run_day: "2026-09-25",
                      lookback_days: 30 }))
      .toBe("今天尚未執行；最近一次在 2026-09-25");
  });

  it("從沒跑過：排程尚未執行", () => {
    expect(cronText({ runs_today: 0, symbols_today: 0, last_run_day: null,
                      lookback_days: 30 }))
      .toBe("排程尚未執行（近 30 天沒有紀錄）");
  });

  it("後端沒回報（舊版）：不猜", () => {
    expect(cronText(undefined)).toBeNull();
  });

  it("後端無法確認（觀測指標關閉，known: false）：照實說無法確認，不說尚未執行", () => {
    expect(cronText({ known: false, runs_today: null, symbols_today: null,
                      last_run_day: null, lookback_days: 30 }))
      .toBe("無法確認排程狀態");
  });
});

describe("retryGate 在排程尚未執行時", () => {
  it("重試用完：不說明天自動更新", () => {
    const never = { runs_today: 0, symbols_today: 0, last_run_day: null, lookback_days: 30 };
    expect(retryGate(sym({ state: "exhausted" }), NOW, { today: "2026-09-28", cron: never })
      .reason).toBe("今天的重試次數已用完，排程尚未執行，不會自動更新，明天請手動「繼續更新」");
  });
});

const noFailures: ConsensusRefreshStatusResponse = {
  ...STATUS, upstream_calls_today: 10,
  progress: { ...STATUS.progress, failed: 0, pending: 0 },
  symbols: STATUS.symbols.map((s) => ({ ...s, state: "done", error: null })),
};
const withUniverse = (over: Partial<OpportunityConsensusResponse["universe"]>,
                      items = CONSENSUS.items): OpportunityConsensusResponse =>
  ({ ...CONSENSUS, universe: { ...CONSENSUS.universe, ...over }, items });

describe("dataPhase：就緒／建立中／失敗／已達上限", () => {
  it("全部建立、沒有失敗：就緒", () => {
    expect(dataPhase(withUniverse({ not_built: 0 }), noFailures)).toEqual({ kind: "ready" });
  });

  it("還有沒建立的：建立中（失敗也照樣先算建立中）", () => {
    expect(dataPhase(withUniverse({ not_built: 2 }), STATUS)).toEqual({ kind: "building" });
  });

  it("都建立了但有失敗的股票：失敗，帶失敗檔數", () => {
    expect(dataPhase(withUniverse({ not_built: 0 }), STATUS)).toEqual({ kind: "failed", failed: 1 });
  });

  it("今日上游呼叫已達上限、還有沒做完的：已達上限（優先於建立中）", () => {
    const capped = { ...STATUS, upstream_calls_today: 400, daily_cap: 400 };
    expect(dataPhase(withUniverse({ not_built: 2 }), capped))
      .toEqual({ kind: "capped", calls: 400, cap: 400 });
  });

  it("已達上限但今天都做完了：就緒（上限不影響已有資料）", () => {
    expect(dataPhase(withUniverse({ not_built: 0 }), { ...noFailures, upstream_calls_today: 400, daily_cap: 400 }))
      .toEqual({ kind: "ready" });
  });

  it("來源限流（429）暫停中、還有沒做完的：限流中，帶結束時間（優先於建立中）", () => {
    const paused = { ...STATUS, rate_limited_until: "2026-09-28T13:20:00Z" };
    expect(dataPhase(withUniverse({ not_built: 2 }), paused, NOW))
      .toEqual({ kind: "rate_limited", until: "2026-09-28T13:20:00Z" });
    // 暫停已結束（用自己的時鐘）：照常判斷。
    expect(dataPhase(withUniverse({ not_built: 2 }), paused,
                     Date.parse("2026-09-28T13:20:00Z"))).toEqual({ kind: "building" });
  });

  it("超出每日更新範圍的股票不會被建立：不讓頁面停在建立中", () => {
    // 後端 `not_built` 已不含它們；只剩超出範圍的沒建立 → 就緒。
    expect(dataPhase(withUniverse({ not_built: 0, out_of_scope: 3 }), noFailures))
      .toEqual({ kind: "ready" });
  });

  it("狀態還沒讀到：只看共識清單", () => {
    expect(dataPhase(withUniverse({ not_built: 1 }), null)).toEqual({ kind: "building" });
    expect(dataPhase(withUniverse({ not_built: 0 }), null)).toEqual({ kind: "ready" });
  });
});

describe("outOfScopeText", () => {
  it("有超出每日更新範圍的：一句話說明；沒有：不顯示", () => {
    expect(outOfScopeText(withUniverse({ out_of_scope: 3 })))
      .toBe("3 檔超出每日更新範圍，不會更新");
    expect(outOfScopeText(withUniverse({ out_of_scope: 0 }))).toBeNull();
    const { out_of_scope: _drop, ...older } = CONSENSUS.universe;
    expect(outOfScopeText({ ...CONSENSUS, universe: older })).toBeNull();
  });
});

describe("builtCount", () => {
  it("超出每日更新範圍的不算進已建立", () => {
    expect(builtCount(withUniverse({ out_of_scope: 1, out_of_scope_symbols: ["AAA"] })))
      .toBe(5);
  });

  it("扣掉還沒建立與抓取失敗（source_error）的；只有共識值（no_data）也算已建立", () => {
    // 樣本 7 檔：GGG source_error，其餘 6 檔都已建立。
    expect(builtCount(CONSENSUS)).toBe(6);
    const notBuilt = CONSENSUS.items.map((i) => i.symbol === "AAA"
      ? { ...i, status: "no_data" as const, reasons: ["no_data: 尚未更新"] } : i);
    expect(builtCount({ ...CONSENSUS, items: notBuilt })).toBe(5);
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
