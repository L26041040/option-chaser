"""OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001：跨裝置的單一主帳號。

UNIFIED-IDENTITY-001 把權限掛在「這個瀏覽器的 user」上，結果是：在另一台
裝置（或另一個網域——cookie／本機儲存是 per-origin 的）輸入 SU 密碼，只會
把那台裝置自己的匿名 user 升權，於是每台裝置各長出一個 SU owner，劇本各自
分散。改成：

```
主帳號（main_account 持久對應 → 一個 owner_id）
  ├─ 裝置憑證 A（role = superuser，用 SU 密碼登入的那台）
  ├─ 裝置憑證 B（role = superadmin，用 SA 密碼登入的那台）
  └─ …一個 owner 可以綁任意多顆裝置憑證
匿名裝置 → 各自的匿名 owner（不必註冊，行為不變）
```

- 登入（`POST /api/auth/login`）：任何裝置輸入正確的 SU／SA 密碼都登入同一個
  主帳號——發一顆**新的**裝置憑證給主帳號（舊的那顆作廢＝重新登入時輪替），
  這台裝置原本的匿名 owner 若有資料就安全併進主帳號
  （`Storage.absorb_owner()`），不會建立第二個 SU owner。
- 權限看**憑證**：SU 密碼登入的裝置是 superuser、SA 密碼登入的是
  superadmin，兩者互不污染。
- 重設為 Normal（`POST /api/auth/reset-role`）＝這台裝置登出主帳號，回到
  全新的匿名身分；主帳號與其他裝置不受影響。

主帳號第一次建立對應的來源（`resolve()`）：

1. 已經有對應、而且那個 owner 還在 → 直接用；
2. 否則找 owner_id 以 `SEED_OWNER_PREFIX` 開頭的唯一 owner（Owner 指定的
   Production 主帳號；寫入的是完整 owner_id，之後就不再看前綴）；
3. 都沒有（全新部署、測試）→ 回 `None`，由登入端點把正在登入的這台裝置的
   owner 指定為主帳號。
"""
from __future__ import annotations

from .storage import Storage

# Owner 指定（2026-10-25，台灣）：Production 唯一的主帳號是 owner_id 以這段
# 開頭的那個 owner（OWNER-CONSOLIDATION-001 把全部舊 Owner 併進去的那一個）。
SEED_OWNER_PREFIX = "Tcf2_BUR"


def resolve(db: Storage, *, now: str) -> str | None:
    """主帳號的完整 owner_id；還無從決定時回 `None`（見檔頭）。"""
    current = db.get_main_account()
    if current is not None and db.get_owner(current) is not None:
        return current
    seeds = db.owners_with_id_prefix(SEED_OWNER_PREFIX)
    if len(seeds) == 1:
        return designate(db, seeds[0].owner_id, now=now, stale=current)
    return None


def designate(db: Storage, owner_id: str, *, now: str,
              stale: str | None) -> str:
    """把 `owner_id` 設成主帳號（compare-and-set，`stale` 是目前那筆已經
    失效的對應或 `None`），並確保它被當成特權帳號：匿名清理與 Beta Reset
    跳過它（`role` 不是 normal）、而且受保護。回傳實際的主帳號——並發下
    另一台裝置先建好的話就是它。"""
    winner = db.set_main_account(owner_id, now=now, expected=stale)
    owner = db.get_owner(winner)
    if owner is not None:
        if owner.role == "normal":
            db.set_owner_role(winner, "superuser")
        if not owner.protected:
            db.set_owner_protected(winner, True)
    return winner
