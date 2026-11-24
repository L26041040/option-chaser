import { describe, expect, it } from "vitest";

import {
  formatUpside,
  priceDateLabel,
  priceText,
  upsideText,
  UPSIDE_REASON_LABELS,
} from "./targetUpside";

const close = {
  price: 125.53,
  price_date: "2026-11-20",
  price_at: "2026-11-20T21:00:01+00:00",
  price_kind: "close" as const,
  target_upside_pct: 12.3,
  target_upside_reason: null,
};

describe("formatUpside（後端已四捨五入到小數一位）", () => {
  it("正值帶 +、負值帶 -、零不帶正負號", () => {
    expect(formatUpside(20)).toBe("+20.0%");
    expect(formatUpside(-9.1)).toBe("-9.1%");
    expect(formatUpside(0)).toBe("0.0%");
    expect(formatUpside(-0)).toBe("0.0%");
    expect(formatUpside(0.1)).toBe("+0.1%");
    expect(formatUpside(-66.7)).toBe("-66.7%");
  });
});

describe("股價與報價日期", () => {
  it("收盤價標「收盤」，盤中價標「盤中」", () => {
    expect(priceDateLabel(close)).toBe("2026-11-20 收盤");
    expect(priceDateLabel({ ...close, price_date: "2026-11-24", price_kind: "intraday" }))
      .toBe("2026-11-24 盤中");
  });

  it("目前股價一律帶報價日期", () => {
    expect(priceText(close)).toBe("$125.53（2026-11-20 收盤）");
  });

  it("沒有股價時顯示 — 加原因", () => {
    const none = { ...close, price: null, price_date: null, price_at: null, price_kind: null,
                   target_upside_pct: null, target_upside_reason: "no_price" as const };
    expect(priceText(none)).toBe("— · 尚未取得股價");
    expect(upsideText(none)).toBe("— · 尚未取得股價");
  });

  it("舊後端沒有這些欄位時當成尚未取得股價", () => {
    expect(priceText({})).toBe("— · 尚未取得股價");
    expect(upsideText({})).toBe("— · 尚未取得股價");
  });
});

describe("目標漲跌幅的缺資料原因", () => {
  it.each([
    ["no_price", "尚未取得股價"],
    ["price_stale", "股價過舊（超過 3 個交易日）"],
    ["no_mean", "沒有平均目標價（資料不足）"],
    ["split_mismatch", "分割基準不一致，暫不計算"],
  ] as const)("%s → %s", (reason, label) => {
    expect(UPSIDE_REASON_LABELS[reason]).toBe(label);
    expect(upsideText({ ...close, target_upside_pct: null, target_upside_reason: reason }))
      .toBe(`— · ${label}`);
  });

  it("有數字就照實顯示", () => {
    expect(upsideText(close)).toBe("+12.3%");
    expect(upsideText({ ...close, target_upside_pct: -4.5 })).toBe("-4.5%");
  });

  it("股價過舊時股價照樣帶日期顯示（真實數字），只是不算漲跌幅", () => {
    const stale = { ...close, target_upside_pct: null, target_upside_reason: "price_stale" as const };
    expect(priceText(stale)).toBe("$125.53（2026-11-20 收盤）");
  });
});
