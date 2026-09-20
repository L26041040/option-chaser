/**
 * 手機版底部導覽（UI-IMPL-002／#092，Mobile-Library／Mobile-Detail 板
 * `.mtabs`）：劇本庫／建立／垃圾桶／設定，四個固定分頁。**手機專屬**
 * ——桌面版對應的導覽是 `TopBar` 的頂層 `.nav`。
 *
 * 「建立」分頁不是新的路由（本站至今只有詳細頁／垃圾桶／設定／隱私頁
 * 四個 hash 路由，見 `./route`），而是既有「劇本庫首頁的就地展開建立
 * 入口」（`CreateEntry`／`App.tsx` 的 `showCreateForm`）的另一個入口：
 * 先回劇本庫（清空 hash），再展開表單——不新增第二套建立流程，也不
 * 從其他畫面（詳細頁／垃圾桶／設定）直接彈出表單，那需要新的跨畫面
 * 狀態管線，超出本輪「視覺 redesign、不動產品語意」的範圍。
 *
 * 「劇本庫」分頁在詳細頁時仍標記為 active（貼齊設計稿 Mobile-Detail
 * 板：進了某個劇本的詳細頁，仍視為「在劇本庫這個大分類底下」）。
 */
import { CreateIcon, GearIcon, HomeIcon, TrashIcon } from "./icons";
import { settingsHash, trashHash } from "./route";

export type BottomNavActive = "library" | "create" | "trash" | "settings";

export default function BottomNav({
  active,
  onOpenCreate,
}: {
  active: BottomNavActive;
  /** 「建立」分頁：回劇本庫首頁並展開建立表單。 */
  onOpenCreate: () => void;
}) {
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
        className={active === "create" ? "mtab on" : "mtab"}
        href="#"
        aria-current={active === "create" ? "page" : undefined}
        onClick={(ev) => {
          ev.preventDefault();
          onOpenCreate();
        }}
      >
        <CreateIcon />
        建立
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
