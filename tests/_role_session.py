"""OPTION-CHASER-UNIFIED-IDENTITY-001 起，權限是 user 記錄的一個欄位
（`owners.role`）——測試要扮演 Super User／Super Admin，就是建立（或指定）
一個 user、把它的權限寫好，再用它的憑證 cookie 發請求。不必真的打一次
`POST /api/auth/login`：那條路徑本身（密碼比對、fail-closed、只升不降）由
`tests/test_auth02_login_role.py` 覆蓋；本站既有慣例本來就是測試直接寫入
storage 建立前提狀態。

回傳的 cookie 字典可以塞給 `TestClient(..., cookies=...)`（構造時）或
`client.get(path, cookies=...)`（單次請求）——httpx 對這樣注入的 cookie
一律當成非 Secure，`http://`／`https://` base_url 都會送出（見
`docs/pb02-cookie-testing-notes.md`）。

用 DI 覆寫身分（`create_app(identity_resolver=lambda: "solo")`）的測試：
權限就是被注入那個 owner 的權限，傳 `owner_id="solo"` 把權限授給它（cookie
在 DI 模式下用不到）。
"""
from __future__ import annotations

import secrets

from api_app.main import _OWNER_COOKIE_NAME
from api_app.storage import BrowserIdentity, Owner

_CREATED_AT = "2026-01-01T00:00:00+00:00"


def grant_role(storage, role: str, *, owner_id: str | None = None) -> str:
    """把 `owner_id`（沒給就新建一個 user）的權限設成 `role`，回傳一顆憑證
    token。新建的 user 這顆 token 就指向它。

    CROSS-DEVICE-ACCOUNT-001 起權限看**憑證**：這裡把這個 user 名下每一顆
    裝置憑證的權限都設成 `role`（等於這個 user 的每台裝置都用那把密碼登入
    過），同時寫 owner 層級的權限（DI 覆寫身分的測試讀的是它）。`owner_id`
    已存在時回傳的 token 不指向任何人（DI 測試用）。"""
    owner_id = owner_id or f"role-{secrets.token_hex(8)}"
    token = secrets.token_urlsafe(32)
    if storage.get_owner(owner_id) is None:
        storage.create_owner_with_token(
            Owner(owner_id=owner_id, created_at=_CREATED_AT),
            BrowserIdentity(token=token, owner_id=owner_id,
                            issued_at=_CREATED_AT, last_seen_at=_CREATED_AT))
    for device in owner_tokens(storage, owner_id):
        storage.set_credential_role(device, None if role == "normal" else role)
    storage.set_owner_role(owner_id, role)
    return token


def owner_tokens(storage, owner_id: str) -> list[str]:
    """這個 owner 名下全部裝置憑證（測試用，直接讀兩個後端的底層）。"""
    if hasattr(storage, "_browser_identities"):
        return [t for t, bi in storage._browser_identities.items()
                if bi.owner_id == owner_id]
    with storage._connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT token FROM browser_identities WHERE owner_id = %s",
            (owner_id,))]


def role_cookies(storage, role: str, *, owner_id: str | None = None) -> dict[str, str]:
    """`grant_role()` 的薄殼——直接回傳 cookie 字典。"""
    return {_OWNER_COOKIE_NAME: grant_role(storage, role, owner_id=owner_id)}


def superuser_cookies(storage, *, owner_id: str | None = None) -> dict[str, str]:
    return role_cookies(storage, "superuser", owner_id=owner_id)


def superadmin_cookies(storage, *, owner_id: str | None = None) -> dict[str, str]:
    return role_cookies(storage, "superadmin", owner_id=owner_id)
