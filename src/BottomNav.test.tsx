/**
 * BottomNav（UI-IMPL-002／#092 既有元件）——本檔案是 code review 跟進
 * （OG-09／#319，Spec 軸）新增：AC「底部四 tab 各自導向正確 hash，
 * 當前 tab 有金色指示」先前只有「hash 正確」半邊有測試（散落在
 * `App.test.tsx` 的各種導覽流程裡），「當前 tab 金色指示」
 * （`.mtab.on` class ＋ `aria-current="page"`）全站零測試涵蓋
 * ——即使機制本身（`className={active === X ? "mtab on" : "mtab"}`，
 * CSS `.mtab.on { color: var(--accent-text) }`）在 OG-09 之前就已經
 * 正確存在。這裡直接測 `BottomNav` 這個小型展示元件本身，不必透過
 * 整個 `App` 掛載。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BottomNav, { type BottomNavActive } from "./BottomNav";

const ALL: BottomNavActive[] = ["library", "create", "trash", "settings"];
const LABEL: Record<BottomNavActive, string> = {
  library: "劇本庫",
  create: "建立",
  trash: "垃圾桶",
  settings: "設定",
};

describe("BottomNav：當前 tab 金色指示（OG-09／#319 code review 跟進）", () => {
  it.each(ALL)("active=%s 時只有那一個 tab 帶 .mtab.on 與 aria-current=\"page\"", (active) => {
    render(<BottomNav active={active} onOpenCreate={vi.fn()} />);
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

  it("四個 tab 各自的 href／點擊行為正確——劇本庫與建立是 in-page 動作，垃圾桶與設定是真實 hash 連結", () => {
    const onOpenCreate = vi.fn();
    render(<BottomNav active="library" onOpenCreate={onOpenCreate} />);

    expect(screen.getByRole("link", { name: /垃圾桶/ })).toHaveAttribute("href", "#/trash");
    expect(screen.getByRole("link", { name: /設定/ })).toHaveAttribute("href", "#/settings");

    screen.getByRole("link", { name: /建立/ }).click();
    expect(onOpenCreate).toHaveBeenCalledTimes(1);
  });

  it("導覽本身有 aria-label 可辨識", () => {
    render(<BottomNav active="library" onOpenCreate={vi.fn()} />);
    expect(screen.getByRole("navigation", { name: "主要導覽" })).toBeInTheDocument();
  });
});
