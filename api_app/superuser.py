"""三層權限（Normal／Super User／Super Admin）。

OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001 起，權限掛在**每一顆裝置憑證**上
（`browser_identities.role`），不再是 owner 記錄的欄位，也不是獨立的第二套
session：

```
主帳號（`main_account` 持久對應 → 一個 owner_id，見 `main_account.py`）
  ├─ 裝置憑證（HttpOnly cookie＋本機儲存，兩份互相補回，見 `main.py`）
  │    └─ role：用哪一把密碼登入的就是哪一級（superuser／superadmin）
  └─ 劇本、設定、provider credential（owner-scoped 資料）
匿名裝置 → 各自的匿名 owner，憑證 role 是 normal
```

- 登入：`POST /api/auth/login` 輸入正確的 SU／SA 密碼 → 這台裝置登入主帳號
  （換發一顆新憑證、舊的作廢；原本的匿名資料併進主帳號），新憑證的權限＝這次
  命中的那一級。同一個主帳號的 SU 裝置與 SA 裝置互不污染。
- 降回 Normal：只有使用者主動按「重設權限」（`POST /api/auth/reset-role`）＝
  這台裝置登出主帳號。重新整理、關閉重開、跨分頁、重新部署都不影響。
- 判斷：`main.py` 的 middleware 解析憑證時一次查齊 user 與這顆憑證的權限，
  放進 `identity` 的 ContextVar；`current_role()`／`require_role()` 是全站
  唯一的讀取點，端點不得自行比對密碼或角色字串。
- `owners.role` 只剩「這是特權帳號」的標記（匿名清理與 Beta Reset 跳過它）；
  只有 DI 覆寫身分的測試路徑仍以它當權限。

AUTH-01／AUTH-02（#308／#309）的 role session 與 `__Host-oc_role` cookie
已退役：沒有任何權限判斷讀它們；舊 cookie 只會被 middleware 清掉，舊列只
剩保留期清理（`data_lifecycle`）。
"""
from __future__ import annotations

import enum

from fastapi import HTTPException

from . import identity

# 退役的 AUTH-02 role cookie 名稱：只用來在回應裡把瀏覽器手上的舊 cookie
# 清掉，任何權限判斷都不讀它。
LEGACY_ROLE_COOKIE_NAME = "__Host-oc_role"
# 舊 role session 的最長壽命（當時 cookie 的固定 Max-Age）。`data_lifecycle`
# 用它清掉瀏覽器已不可能再送出的舊列。
LEGACY_ROLE_SESSION_MAX_AGE_SECONDS = 400 * 24 * 60 * 60

_ROLE_RANK = {"normal": 0, "superuser": 1, "superadmin": 2}


class Role(str, enum.Enum):
    """有序、可比較的三層角色。繼承 `str` 讓 FastAPI／pydantic 直接
    把 `.value` 序列化進 JSON 回應，不需要額外的轉接層。

    **四個比較運算子全部手寫**（不用 `functools.total_ordering`，
    見上方檔頭說明的陷阱）——`str` 這個 mixin 基底本身已經提供
    `__le__`／`__gt__`／`__ge__`，若只手寫 `__lt__` 交給
    `total_ordering` 補齊其餘三個，它會判定那三個「已經有定義」而
    完全不覆寫，讓字典序而非等級排序悄悄生效。"""

    NORMAL = "normal"
    SUPERUSER = "superuser"
    SUPERADMIN = "superadmin"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return _ROLE_RANK[self.value] < _ROLE_RANK[other.value]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return _ROLE_RANK[self.value] <= _ROLE_RANK[other.value]

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return _ROLE_RANK[self.value] > _ROLE_RANK[other.value]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return _ROLE_RANK[self.value] >= _ROLE_RANK[other.value]


def current_role() -> Role:
    """這次請求的 user 權限——還沒有 user（第一次來、尚未建立）、不在請求
    裡，或資料庫裡的值不認得，一律 `Role.NORMAL`（fail-closed）。"""
    try:
        return Role(identity.resolved_role())
    except ValueError:
        return Role.NORMAL


def require_role(minimum: Role) -> None:
    """HTTP handler 用的 fail-closed 守門——未達 `minimum` 一律 401，不區分
    「沒有 user」與「權限不夠」（對外看起來一致，不洩漏哪一種成立）。"""
    if current_role() < minimum:
        raise HTTPException(status_code=401, detail="unauthorized")
