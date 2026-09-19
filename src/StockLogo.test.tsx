/**
 * OG-01（#317）AC：StockLogo 的 `fallback=404` 契約與「失敗即留白」
 * 行為——假造代號不得出現任何替代圖示（不畫首字母、不畫通用圖示）。
 * 不需要真的打網路：`<img>` 的 `onLoad`／`onError` 直接用
 * `fireEvent` 觸發即可驗證元件邏輯本身，是否真的抓得到圖跟這裡的
 * 斷言無關（那是 Logo.dev 服務本身的責任，不是本元件的責任）。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StockLogo from "./StockLogo";

describe("StockLogo（OG-01／#317）", () => {
  it("symbol 為空字串時整個不渲染", () => {
    const { container } = render(<StockLogo symbol="" />);
    expect(container.firstChild).toBeNull();
  });

  it("初始渲染：<img> 帶 fallback=404，且是純裝飾（不重複唸代號）", () => {
    render(<StockLogo symbol="NVDA" />);
    const img = screen.getByRole("presentation", { hidden: true }) as HTMLImageElement;
    expect(img.tagName).toBe("IMG");
    expect(img.src).toContain("fallback=404");
    expect(img.src).toContain("ticker/NVDA");
    expect(img.alt).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
  });

  it("Logo.dev 對假造代號回 404（onError）後——<img> 整個從 DOM 消失，" +
    "不出現任何替代圖示（不是首字母、不是通用圖示）", () => {
    const { container } = render(<StockLogo symbol="ZZZZFAKE999" />);
    const img = container.querySelector("img")!;
    fireEvent.error(img);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).toBeNull();
    // 唯一允許留下的是外層容器本身（呼叫端自己會在它旁邊放代號文字，
    // 但 StockLogo 元件內部不得殘留任何內容）。
    const tile = container.querySelector(".tile")!;
    expect(tile).not.toBeNull();
    expect(tile.textContent).toBe("");
    expect(tile.className).toContain("none");
  });

  it("成功載入後不帶 .none 修飾", () => {
    const { container } = render(<StockLogo symbol="NVDA" />);
    const img = container.querySelector("img")!;
    Object.defineProperty(img, "naturalWidth", { value: 100, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 100, configurable: true });
    fireEvent.load(img);

    const tile = container.querySelector(".tile")!;
    expect(tile.className).not.toContain("none");
    expect(container.querySelector("img")).not.toBeNull();
  });

  it("寬版字標（寬高比 > 1.6）載入成功後加上 .wide 修飾", () => {
    const { container } = render(<StockLogo symbol="SPY" />);
    const img = container.querySelector("img")!;
    Object.defineProperty(img, "naturalWidth", { value: 200, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 100, configurable: true });
    fireEvent.load(img);

    expect(container.querySelector(".tile")!.className).toContain("wide");
  });

  it("換一個 symbol 會重新嘗試——上一個代號的失敗狀態不會沿用到新代號", () => {
    const { container, rerender } = render(<StockLogo symbol="ZZZZFAKE999" />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();

    rerender(<StockLogo symbol="NVDA" />);
    // 新代號重新進入 loading（loading 中同樣不顯示內容，`.none` 修飾
    // 沿用既有「避免先閃一個空框再消失」設計、不是本測試要驗的重點），
    // 但 <img> 一定要重新出現——舊代號的 error 狀態不能卡住新代號。
    const img = container.querySelector("img");
    expect(img).not.toBeNull();

    Object.defineProperty(img!, "naturalWidth", { value: 100, configurable: true });
    Object.defineProperty(img!, "naturalHeight", { value: 100, configurable: true });
    fireEvent.load(img!);
    expect(container.querySelector(".tile")!.className).not.toContain("none");
  });

  it.each([
    ["s", 20],
    ["m", 28],
    ["l", 40],
    ["xl", 56],
  ] as const)("size=%s 對應 Logo.dev 請求尺寸 %ipx（含高密度螢幕 2x）", (size, px) => {
    const { container } = render(<StockLogo symbol="NVDA" size={size} />);
    const img = container.querySelector("img")!;
    expect(img.src).toContain(`size=${px * 2}`);
  });
});
