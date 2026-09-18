"""User Level（軸二，AUTH-01／AUTH-02／AUTH-03，spec #307，Anonymous
Public Beta）：Super User／Super Admin capability——與軸一（Owner
Identity／owner_id，`api_app/identity.py`）完全獨立的第二段判斷。

```
軸一（所有人共用，含 Owner 自己）：
  Browser Identity（cookie）→ owner_id → product data

軸二（獨立於軸一）：
  Authenticated context → User Level（normal < superuser < superadmin）
  → capability
```

這個模組**只回答「這次請求的 role session cookie 對應到哪一層角色」**，
從不讀取、不參與、不影響 owner_id 的解析——`resolve_role()`／
`require_role()` 的唯一輸入是 `Request` 本身的 cookie 與呼叫端傳入的
`resolve_session` 查詢函式，不接觸 `identity.py` 的任何函式、
ContextVar 或中間結果。反過來，`identity.py`／cookie middleware 也
完全不 import 這個模組。兩段程式碼各自獨立，呼叫端（`api_app/main.py`
的 HTTP handler）分別呼叫兩者各自取得答案，這是 spec §19 明文要求的
結構（不得共用同一個函式或同一個中間結果）。

**單一驗證機制、逐層各自一把密碼**（spec #307 §6）：`POST /api/
auth/login` 依序比對 `SUPERADMIN_PASSWORD` → `SUPERUSER_PASSWORD`
（`main.py::auth_login()`），成功即簽發對應角色的持久 role session
（AUTH-01）；本模組之後只認 session 對應的角色，不再重新比對任何
密碼字串——與 `CRON_SECRET` 用途正交（那是 machine-to-machine，這裡
服務的是人類 Owner）、與軸一的 owner cookie 也正交。

**「知道某個 owner_id」不等於「取得 Super User／Super Admin」**——
這件事在這個模組裡是結構性成立的，不是靠約定：`resolve_role()`／
`require_role()` 的簽章裡根本沒有 `owner_id` 這個參數，它完全無法
讀取呼叫端的 owner_id 是什麼，自然也就無從「根據 owner_id 判斷」。

---

**AUTH-03（#310）正式退役舊機制**：PB-09 當時唯二層級（Normal／
Super User）留下的 `is_superuser()`／`require_superuser()`／
`ADMIN_SECRET` 已於本票整組移除——`api_app/main.py` 全部改用下面的
`require_role(..., minimum=Role.SUPERADMIN)`。`ADMIN_SECRET` 環境
變數即使還留在部署環境裡也不再被任何程式碼讀取（純死配置，Owner
可安全移除）；`SUPERADMIN_PASSWORD` 是它唯一的正式後繼者。

下面的 `Role`／`resolve_role()`／`require_role()` 是**單一**授權
判斷點，服務 `normal < superuser < superadmin` 三層。`resolve_role()`
接受一個 `resolve_session` callable（呼叫端傳入 `Storage.resolve_
role_session` 本身，而非整個 `Storage` 型別），維持這個模組除了
`AUTH-01` 的 `RoleSession` 資料形狀外，不依賴任何更大的抽象。

角色比較全部四個運算子（`<`／`<=`／`>`／`>=`）皆逐一手寫、**不用**
`functools.total_ordering`——踩過一個真陷阱才確認：`Role` 繼承
`str`，而 `str` 本身早就有 `__le__`／`__gt__`／`__ge__`，
`total_ordering` 的偵測邏輯是「這三個是不是還等於 `object` 的預設值」，
不是也不會判斷「這三個是不是我要的等級排序」——`str` 提供的那三個
會被判定成「已經定義過了」而完全不被覆寫，於是 `Role.SUPERADMIN >=
Role.SUPERUSER` 會用字典序比較（`"superadmin" < "superuser"`，因為
`a < u`）算出 `False`，跟等級排序完全相反卻不會有任何錯誤或警告。
手動定義全部四個，`require_role()` 用 `<` 做「未達最低等級」判斷，
不區分「沒帶 cookie」與「帶了但角色不夠」，兩者對外都是同一個
401（fail-closed，同既有 `require_superuser()` 精神）。

Session 一旦簽發即長期有效，直到 `logout` 或 server-side 明確撤銷
（AUTH-01 的 `revoke_role_session()`）——**沒有任何密碼變更偵測／
指紋／session versioning**（Owner 明確裁示取消 password rotation，
見 #307 Further Notes、#309 2026-09-17 修正）。`resolve_role()` 找到
一筆 `revoked_at is None` 的 session 就直接信任它的 `role` 欄位，
不做任何與密碼相關的二次驗證——這個設計本身就是 AC 要求的行為，不是
待補的漏洞。
"""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Callable

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from .storage import RoleSession

# ---------- 三層角色模型（AUTH-02／#309） ----------

# 與 `_OWNER_COOKIE_NAME`（`main.py`）同一組 `__Host-` 前綴慣例，名字
# 放在這個模組（而非 `main.py`）——`identity.py` 是不認識 HTTP cookie
# 的 ContextVar 層，owner cookie 的名字因此活在 `main.py`；這個模組
# 本身就是「cookie token → 角色」的擁有者，把名字放在這裡讓
# `resolve_role()`／`require_role()` 不需要呼叫端額外傳入它。
ROLE_COOKIE_NAME = "__Host-oc_role"

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


# `resolve_session` 是呼叫端傳入的 `Storage.resolve_role_session`
# 本身（一個 bound method，簽章即 `(token: str) -> RoleSession |
# None`）——刻意只依賴這一個窄函式而非整個 `Storage` 型別，模組因此
# 不需要 import `Storage`（避免任何不必要的抽象依賴，也讓單元測試
# 可以直接塞一個 lambda 而不必造一份完整假體）。
ResolveRoleSession = Callable[[str], "RoleSession | None"]


def resolve_role(request: Request, *,
                 resolve_session: ResolveRoleSession) -> Role:
    """單一角色判斷點——沒有 cookie、cookie 查不到 session、或 session
    已被撤銷，一律回 `Role.NORMAL`（三種情況對外觀察不到差異，這正是
    fail-closed 的意思：不透露是哪一種原因造成)。找到未撤銷的 session
    後，只讀它的 `role` 欄位——不做任何密碼相關的二次驗證。"""
    token = request.cookies.get(ROLE_COOKIE_NAME)
    if not token:
        return Role.NORMAL
    session = resolve_session(token)
    if session is None:
        return Role.NORMAL
    try:
        return Role(session.role)
    except ValueError:
        return Role.NORMAL


def require_role(request: Request, minimum: Role, *,
                 resolve_session: ResolveRoleSession) -> None:
    """HTTP handler 用的 fail-closed 守門——未達 `minimum` 一律 401，
    不區分「沒帶 cookie」與「帶了但角色不夠」（比照舊 `require_
    superuser()`——AUTH-03 已整組移除——同一種精神：兩種情況對外
    看起來一致，不洩漏哪一種成立）。**全站唯一的授權判斷點**——
    `main.py` 的每個受保護端點都直接呼叫這個函式，不得自行重新比對
    密碼或角色字串。"""
    if resolve_role(request, resolve_session=resolve_session) < minimum:
        raise HTTPException(status_code=401, detail="unauthorized")
