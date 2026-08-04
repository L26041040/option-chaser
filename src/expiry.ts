/**
 * 到期日結構的純函式（V6／#54）。
 *
 * 零金融計算：每期的最高收益就是引擎排好序後該期的第 1 名，有效組數是
 * 引擎的 `expiry_counts`，腿價直接取自合約報價，淨成本是引擎算好的
 * `natural_cost`（最差成交假設：買腿 Ask − 賣腿 Bid）。這裡只做挑選與
 * 併攏，不做任何加減。
 */
import type { Candidate, StrategyResult } from "./api";

/** 低於這個組數就警示——沿用 Streamlit 版 FB3-02（#45）的門檻。 */
export const THIN_POOL = 3;

export interface ExpiryOption {
  expiry: string;
  /** 該期最高收益＝該期第 1 名的劇本報酬。沒有候選時為 null。 */
  bestReturn: number | null;
  /** 該期通過品質過濾的有效組數（引擎的 `expiry_counts`）。
   *  找不到該期＝null，那是「不知道」，與「0 組」不同。 */
  count: number | null;
  candidates: Candidate[];
}

/**
 * 每個到期日一個選項，順序照引擎給的（`expiry_top10`）。
 *
 * 按鈕上的數字與點開後清單的第 1 名必然一致——兩者取自同一個陣列，
 * 而不是各自去別的欄位撈（`expiry_best` 是另一份，容易對不上）。
 */
export function expiryOptions(result: StrategyResult): ExpiryOption[] {
  return (result.expiry_top10 ?? []).map((group) => ({
    expiry: group.expiry,
    bestReturn: group.candidates[0]?.baseline_return ?? null,
    count: validPairsForExpiry(result, group.expiry),
    candidates: group.candidates,
  }));
}

/**
 * 某一期通過品質過濾的有效組數（FB4-01／#60）。找不到該期回傳 null——
 * 「不知道」與「0 組」是不同的事，不能混為一談。
 *
 * 到期日結構與候選池診斷都問這一件事，所以只有這一份實作。
 */
export function validPairsForExpiry(
  result: StrategyResult,
  expiry: string | null,
): number | null {
  if (expiry === null) return null;
  const hit = result.expiry_counts.find(([e]) => e === expiry);
  return hit ? hit[1] : null;
}

/** 這個組數是否少到讓名次失去參考價值。null（不知道）不算。 */
export function isThinPool(count: number | null): boolean {
  return count !== null && count < THIN_POOL;
}

export interface LegPrices {
  /** 買腿買入價（Ask）。 */
  buyAsk: number | null;
  /** 賣腿賣出價（Bid）。單腳候選沒有賣腿＝null。 */
  sellBid: number | null;
  /** Spread 淨成本（引擎的 `natural_cost`，最差成交口徑）。 */
  net: number;
}

export function legPrices(candidate: Candidate): LegPrices {
  const [buy, sell] = candidate.legs;
  return {
    buyAsk: buy ? buy.ask : null,
    sellBid: sell ? sell.bid : null,
    net: candidate.natural_cost,
  };
}

/**
 * 目前該顯示哪一期：使用者選的那期若還在（換了一次分析後可能消失），
 * 就用它；否則退回 baseline 期，再不然第一期。回傳 null ＝ 一期都沒有。
 */
export function resolveExpiry(
  options: ExpiryOption[],
  selected: string | null,
  baseline: string | null,
): string | null {
  const has = (e: string | null) => e !== null && options.some((o) => o.expiry === e);
  if (has(selected)) return selected;
  if (has(baseline)) return baseline;
  return options[0]?.expiry ?? null;
}
