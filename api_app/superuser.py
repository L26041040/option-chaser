"""User Level（軸二，PB-09／#298，Anonymous Public Beta）：Super User
capability——與軸一（Owner Identity／owner_id，`api_app/identity.py`）
完全獨立的第二段判斷。

```
軸一（所有人共用，含 Owner 自己）：
  Browser Identity（cookie）→ owner_id → product data

軸二（獨立於軸一）：
  Authenticated context → User Level（normal | superuser）→ capability
```

這個模組**只回答「這次請求的呼叫端有沒有證明自己是 Super User」**，
從不讀取、不參與、不影響 owner_id 的解析——`is_superuser()` 的唯一
輸入是 `Request` 本身的 `Authorization` 標頭與已解析好的
`admin_secret` 設定值，不接觸 `identity.py` 的任何函式、ContextVar
或中間結果。反過來，`identity.py`／cookie middleware 也完全不 import
這個模組。兩段程式碼各自獨立，呼叫端（`api_app/main.py` 的 HTTP
handler）分別呼叫兩者各自取得答案，這是 spec §19 明文要求的結構
（不得共用同一個函式或同一個中間結果）。

**單一驗證機制**（spec §6 第 1 點）：全站只有一把 `ADMIN_SECRET`，
用它就能使用全部 Super User 介面與操作——不像 `CRON_SECRET`／
`OPS_SECRET` 那樣依信任邊界各自獨立（那兩把是 machine-to-machine
service credential，服務不同的呼叫者，本來就該各自獨立；這裡服務的
是同一個人類 Owner，要求他為不同後台功能重新輸入不同 secret 是
明確禁止的體驗）。

沿用本站既有的 `CRON_SECRET`／`OPS_SECRET`「`Authorization: Bearer
<secret>`、逐字比對、fail-closed 401」慣例（`main.py` 的
`cron_warm_rate_cache()`／舊版 `ops_metrics()`），但改用
`secrets.compare_digest()` 做常數時間比對——這是全輪授權面第二寬的
邊界（僅次於軸一 cookie 本身），值得比既有兩把 service credential
多一分防護。

**「知道某個 owner_id」不等於「取得 Super User」**——這件事在這個
模組裡是結構性成立的，不是靠約定：`is_superuser()` 的簽章裡根本
沒有 `owner_id` 這個參數，它完全無法讀取呼叫端的 owner_id 是什麼，
自然也就無從「根據 owner_id 判斷」。

---

**三層角色模型（AUTH-01／AUTH-02，spec #307，2026-09-17）**：上面的
`is_superuser()`／`require_superuser()`／`ADMIN_SECRET` 是 PB-09 當時
唯二層級（Normal／Super User）留下的既有機制，**本票（AUTH-02）刻意
一行都不動**——AUTH-03（#310）才是把既有 `/api/superuser/*`／
`/api/ops/metrics`／憑證 CRUD 端點從 `require_superuser()` 換成下面
新的 `require_role()` 並退役 `ADMIN_SECRET` 的那一票；在那之前，兩套
機制必須同時有效，避免切換窗口內任何一邊突然失效。

下面新增的 `Role`／`resolve_role()`／`require_role()` 是**單一**取代
既有二值判斷的新判斷點，服務 `normal < superuser < superadmin` 三層。
與上面 `is_superuser()` 同一種正交保證：函式簽章裡沒有 `owner_id`，
模組不 import `identity.py`——`resolve_role()` 額外接受一個
`resolve_session` callable（呼叫端傳入 `Storage.resolve_role_session`
本身，而非整個 `Storage` 型別），維持這個模組除了 `AUTH-01` 的
`RoleSession` 資料形狀外，不依賴任何更大的抽象。

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
import secrets
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
    不區分「沒帶 cookie」與「帶了但角色不夠」（比照 `require_
    superuser()` 既有精神）。本票（AUTH-02）刻意不替換任何既有呼叫點
    ——這是新工具，接線是 AUTH-03（#310）的範圍。"""
    if resolve_role(request, resolve_session=resolve_session) < minimum:
        raise HTTPException(status_code=401, detail="unauthorized")


def is_superuser(request: Request, *, admin_secret: str | None) -> bool:
    """單一 Super User 判斷點。`admin_secret` 未設定（`None`／空字串）
    時**一律回 `False`**——fail-closed，不存在「祕密沒設定就等於誰都
    是 Super User」這種退化狀態。"""
    if not admin_secret:
        return False
    provided = request.headers.get("authorization")
    if not provided:
        return False
    return secrets.compare_digest(provided, f"Bearer {admin_secret}")


def require_superuser(request: Request, *, admin_secret: str | None) -> None:
    """HTTP handler 用的 fail-closed 守門——比照既有 `cron_secret`／
    `ops_secret` 端點「驗證失敗一律 401」的既有慣例，不區分「沒帶
    憑證」與「帶錯憑證」（兩者對外都應該看起來一樣，不洩漏哪一種
    情況成立）。"""
    if not is_superuser(request, admin_secret=admin_secret):
        raise HTTPException(status_code=401, detail="unauthorized")
