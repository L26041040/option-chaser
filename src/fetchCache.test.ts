/**
 * fetchCache 模組本身的測試（T03／#187）：in-flight 去重、快取重用、
 * reference-counted abort 三個核心保證，獨立於任何元件渲染。
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import type { getScenario } from "./api";
import { _resetCacheForTests, cachedFetch, getScenarioCached, invalidate,
        invalidateScenarioCache, setCached } from "./fetchCache";

afterEach(() => {
  _resetCacheForTests();
});

describe("cachedFetch", () => {
  it("同一個 key 的並發呼叫只真的發一次底層請求（in-flight 去重）", async () => {
    let calls = 0;
    const fetcher = vi.fn(async () => {
      calls += 1;
      return "value";
    });

    const a = cachedFetch("k", fetcher);
    const b = cachedFetch("k", fetcher);

    expect(await a.promise).toBe("value");
    expect(await b.promise).toBe("value");
    expect(calls).toBe(1);
    expect(fetcher).toHaveBeenCalledTimes(1);

    a.release();
    b.release();
  });

  it("結果已完成後，同一個 key 的新呼叫直接拿快取，不重新發請求", async () => {
    let calls = 0;
    const fetcher = vi.fn(async () => {
      calls += 1;
      return calls;
    });

    const first = cachedFetch("k", fetcher);
    expect(await first.promise).toBe(1);
    first.release();

    const second = cachedFetch("k", fetcher);
    expect(await second.promise).toBe(1);   // 還是第一次的結果
    second.release();

    expect(calls).toBe(1);
  });

  it("不同 key 各自獨立發請求", async () => {
    const fetcher = vi.fn(async () => "value");
    const a = cachedFetch("k1", fetcher);
    const b = cachedFetch("k2", fetcher);
    await a.promise;
    await b.promise;
    expect(fetcher).toHaveBeenCalledTimes(2);
    a.release();
    b.release();
  });

  it("最後一個呼叫端 release 時，若仍未完成就 abort 底層請求", async () => {
    let capturedSignal: AbortSignal | undefined;
    let resolveFetch: (() => void) | undefined;
    const fetcher = vi.fn((signal: AbortSignal) => {
      capturedSignal = signal;
      return new Promise<string>((resolve) => {
        resolveFetch = () => resolve("value");
      });
    });

    const a = cachedFetch("k", fetcher);
    const b = cachedFetch("k", fetcher);

    // 兩個呼叫端都還在等——release 一個不該 abort。
    a.release();
    expect(capturedSignal?.aborted).toBe(false);

    // 最後一個也 release，且這次呼叫仍未完成——才真的 abort。
    b.release();
    expect(capturedSignal?.aborted).toBe(true);

    resolveFetch?.();
  });

  it("還有其他呼叫端在等時，不會因為某一個 release 就 abort", async () => {
    let capturedSignal: AbortSignal | undefined;
    const fetcher = vi.fn((signal: AbortSignal) => {
      capturedSignal = signal;
      return new Promise<string>(() => {});   // 故意不 resolve
    });

    const a = cachedFetch("k", fetcher);
    const b = cachedFetch("k", fetcher);

    a.release();
    expect(capturedSignal?.aborted).toBe(false);   // b 還在等

    b.release();
    expect(capturedSignal?.aborted).toBe(true);
  });

  it("已完成的結果 release 後不會被 abort（沒有意義，也不該發生）", async () => {
    let capturedSignal: AbortSignal | undefined;
    const fetcher = vi.fn(async (signal: AbortSignal) => {
      capturedSignal = signal;
      return "value";
    });

    const a = cachedFetch("k", fetcher);
    await a.promise;
    a.release();

    expect(capturedSignal?.aborted).toBe(false);
  });

  it("失敗不快取——下一次呼叫真的重新嘗試", async () => {
    let attempt = 0;
    const fetcher = vi.fn(async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("boom");
      return "ok";
    });

    const first = cachedFetch("k", fetcher);
    await expect(first.promise).rejects.toThrow("boom");
    first.release();

    const second = cachedFetch("k", fetcher);
    expect(await second.promise).toBe("ok");
    second.release();

    expect(attempt).toBe(2);
  });
});

describe("invalidate／setCached", () => {
  it("invalidate 後，下一次呼叫真的重新發請求", async () => {
    const fetcher = vi.fn(async () => "value");
    const a = cachedFetch("k", fetcher);
    await a.promise;
    a.release();

    invalidate("k");

    const b = cachedFetch("k", fetcher);
    await b.promise;
    b.release();

    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("setCached 寫入的值可以直接被 cachedFetch 讀到，不觸發 fetcher", async () => {
    setCached("k", "known-value");
    const fetcher = vi.fn(async () => "should-not-be-called");

    const result = cachedFetch("k", fetcher);
    expect(await result.promise).toBe("known-value");
    expect(fetcher).not.toHaveBeenCalled();
    result.release();
  });
});

describe("invalidateScenarioCache（ARCH-REVIEW-001／#343）", () => {
  /** `getScenarioCached()` 內部打的是 `api.getScenario()`，這裡把它換成
   *  一個計次的假實作，才能斷言「有沒有真的重抓」。 */
  function mockDetail(analyzedAt: string | null) {
    return { id: "s1", latest_analyzed_at: analyzedAt } as unknown as
      Awaited<ReturnType<typeof getScenario>>;
  }

  it("編輯清空結果後（hint 為 null），詳細頁不再沿用舊快取——這正是 "
   + "hintAnalyzedAt 分辨不出來的那個情境", async () => {
    const spy = vi.spyOn(api, "getScenario")
      .mockResolvedValue(mockDetail("2026-09-01T00:00:00Z"));

    // 1. 先看過一次詳細頁——快取裡現在有一份「有結果」的版本。
    const first = getScenarioCached("s1", null);
    await first.promise;
    first.release();
    expect(spy).toHaveBeenCalledTimes(1);

    // 2. 使用者編輯 thesis：後端 `clear_results()`，PATCH 回來的
    //    `latest_analyzed_at` 是 null。沒有這一行的話，下面那次
    //    `hintAnalyzedAt === null` 會被當成「還不知道版本」而沿用快取。
    invalidateScenarioCache("s1");
    spy.mockResolvedValue(mockDetail(null));

    // 3. 接著使用者（在刷新失敗、或刷新還在飛的時候）打開詳細頁。
    const second = getScenarioCached("s1", null);
    expect(await second.promise).toMatchObject({ latest_analyzed_at: null });
    second.release();

    expect(spy).toHaveBeenCalledTimes(2);
    spy.mockRestore();
  });

  it("沒有 mutation 時，hint 為 null 仍照舊沿用快取（不因為這次修正 "
   + "而退化成每次都重抓）", async () => {
    const spy = vi.spyOn(api, "getScenario")
      .mockResolvedValue(mockDetail("2026-09-01T00:00:00Z"));

    const first = getScenarioCached("s1", null);
    await first.promise;
    first.release();

    const second = getScenarioCached("s1", null);
    await second.promise;
    second.release();

    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});
