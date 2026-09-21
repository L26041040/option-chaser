/**
 * 手機版底部導覽（UI-IMPL-002／#092，Mobile-Library／Mobile-Detail 板
 * `.mtabs`）：劇本庫／垃圾桶／設定，三個固定分頁。**手機專屬**——
 * 桌面版對應的導覽是 `TopBar` 的 `.pnav`。
 *
 * SW-04（#333，Seed Warm）：拿掉原本的「建立」第四分頁——VISUAL-
 * IDENTITY-001／SEED-WARM-SPEC-001（#330）Owner 明確裁示「手機不要
 * 同時存在兩個主要『建立劇本』入口」，唯一入口收斂到劇本庫首頁標題
 * 列的「＋ 建立劇本」CTA（見 `App.tsx` 手機首頁分支）。垃圾桶／設定／
 * 詳細頁不再有第二個建立入口——想建立劇本，先回劇本庫首頁再按標題
 * 列的按鈕，多一次點擊換來「全站只有一個入口」，是這次 redesign 的
 * 明確取捨，不是遺漏。
 *
 * 「劇本庫」分頁在詳細頁時仍標記為 active（貼齊設計稿 Mobile-Detail
 * 板：進了某個劇本的詳細頁，仍視為「在劇本庫這個大分類底下」）。
 */
import { GearIcon, HomeIcon, TrashIcon } from "./icons";
import { settingsHash, trashHash } from "./route";

export type BottomNavActive = "library" | "trash" | "settings";

export default function BottomNav({ active }: { active: BottomNavActive }) {
  return (
    <nav className="mtabs" aria-label="主要導覽">
      <a
        className={active === "library" ? "mtab on" : "mtab"}
        href="#"
        aria-current={active === "library" ? "page" : undefined}
      >
        <HomeIcon />
        劇本庫
      </a>
      <a
        className={active === "trash" ? "mtab on" : "mtab"}
        href={trashHash()}
        aria-current={active === "trash" ? "page" : undefined}
      >
        <TrashIcon />
        垃圾桶
      </a>
      <a
        className={active === "settings" ? "mtab on" : "mtab"}
        href={settingsHash()}
        aria-current={active === "settings" ? "page" : undefined}
      >
        <GearIcon />
        設定
      </a>
    </nav>
  );
}
