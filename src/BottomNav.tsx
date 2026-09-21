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
 *
 * SW-11（#341，Owner 真機驗收）：`.mtabs` 從 `position: sticky` 改成
 * `position: fixed`——root cause 是 iOS Safari「動態瀏覽器 chrome」
 * （下滑收合、上滑展開的底部工具列）跟 `position: sticky; bottom: 0`
 * 疊在一起時，WebKit 對 sticky 容器邊界的重算會跟工具列的高度動畫
 * 打架，實機上就是 Owner 回報的「icon 隨捲動方向忽隱忽現」——這跟
 * 頂部 `.mnav` 沿用 sticky（見 `styles.css` 該規則註解）不是同一個
 * 情境：頂部工具列不受 iOS 底部動態 chrome 影響，`.mtabs` 才會。
 * `position: fixed` 直接釘住 layout viewport、不經過 sticky 那套邊界
 * 重算，才是穩定整個 bottom nav（不是只給 icon 打 patch）的修法。
 *
 * 副作用是 `fixed` 元素會脫離文件流——原本 `sticky` 版本仍佔一份
 * `.screen` flex 版面的高度，拿掉後 `Footer` 會被蓋住。這裡直接在
 * `BottomNav` 自己內部補一個等高 `.mtabs-spacer`，讓四個既有呼叫端
 * （`App.tsx` 兩處／`Settings.tsx`／`TrashView.tsx`／
 * `ScenarioDetail.tsx`，皆是「渲染 `<BottomNav>` 就要保留版面空間」）
 * 完全不用跟著改——沒有 `<BottomNav>` 的頁面（例如 `PrivacyPage`）
 * 也就不會多出這段空白。
 */
import { GearIcon, HomeIcon, TrashIcon } from "./icons";
import { settingsHash, trashHash } from "./route";

export type BottomNavActive = "library" | "trash" | "settings";

export default function BottomNav({ active }: { active: BottomNavActive }) {
  return (
    <>
      <div className="mtabs-spacer" aria-hidden="true" />
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
    </>
  );
}
