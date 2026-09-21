/**
 * BottomNav（UI-IMPL-002／#092 既有元件）——本檔案是 code review 跟進
 * （OG-09／#319，Spec 軸）新增：AC「底部分頁各自導向正確 hash，當前
 * tab 有指示」先前只有「hash 正確」半邊有測試（散落在 `App.test.tsx`
 * 的各種導覽流程裡），「當前 tab 指示」（`.mtab.on` class ＋
 * `aria-current="page"`）全站零測試涵蓋——即使機制本身在 OG-09 之前
 * 就已經正確存在。這裡直接測 `BottomNav` 這個小型展示元件本身，不必
 * 透過整個 `App` 掛載。
 *
 * SW-04（#333，Seed Warm）：「建立」分頁移除——見 `BottomNav.tsx`
 * 檔頭說明，唯一建立入口收斂到劇本庫首頁標題列。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BottomNav, { type BottomNavActive } from "./BottomNav";

const ALL: BottomNavActive[] = ["library", "trash", "settings"];
const LABEL: Record<BottomNavActive, string> = {
  library: "劇本庫",
  trash: "垃圾桶",
  settings: "設定",
};

describe("BottomNav：三格、當前 tab 指示（OG-09／#319；SW-04／#333 起無建立分頁）", () => {
  it.each(ALL)("active=%s 時只有那一個 tab 帶 .mtab.on 與 aria-current=\"page\"", (active) => {
    render(<BottomNav active={active} />);
    for (const tab of ALL) {
      const link = screen.getByRole("link", { name: new RegExp(LABEL[tab]) });
      if (tab === active) {
        expect(link.className).toBe("mtab on");
        expect(link).toHaveAttribute("aria-current", "page");
      } else {
        expect(link.className).toBe("mtab");
        expect(link).not.toHaveAttribute("aria-current");
      }
    }
  });

  it("只有三個分頁，沒有第二個建立入口", () => {
    render(<BottomNav active="library" />);
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(screen.queryByRole("link", { name: /建立/ })).not.toBeInTheDocument();
  });

  it("垃圾桶與設定是真實 hash 連結", () => {
    render(<BottomNav active="library" />);
    expect(screen.getByRole("link", { name: /垃圾桶/ })).toHaveAttribute("href", "#/trash");
    expect(screen.getByRole("link", { name: /設定/ })).toHaveAttribute("href", "#/settings");
  });

  it("導覽本身有 aria-label 可辨識", () => {
    render(<BottomNav active="library" />);
    expect(screen.getByRole("navigation", { name: "主要導覽" })).toBeInTheDocument();
  });
});
